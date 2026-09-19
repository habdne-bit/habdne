# TURAB — Slice 0 Closure Pack

**Slice:** 0 — Application Skeleton / Security Boundaries
**Date:** 2026-09-19
**Baseline:** Handoff v1.0.1, technical baseline frozen at `f833fe7d05e160b048a6de1c4120f2c79015c3bb`
**Closure commit:** `85422bcd8c827c5a73ba1907d13c13bec1659f13`
**Branch:** `claude/postgresql-execution-gate-yqifk7`

---

## 1. Verification results

| Check | Result |
|---|---|
| Frozen pack integrity (`verify_handoff.py`) | **PASS** — 29/29, byte-identical to official v1.0.1 |
| PostgreSQL Execution Gate | **PASS** — 70/70 assertions, PostgreSQL 16.13 |
| Test suite | **PASS** — 211/211 |
| Authorization Evidence Matrix | **PASS** — 60 rules, 124 tests cited, none UNPROVEN |
| OpenAPI drift (generated inventory vs frozen contract) | **PASS** — no drift |
| Policy/contract cross-check (R10.2) | **PASS** — 64 operations, verified at startup and in tests |
| Generated app schema vs frozen contract (R14.2) | **PASS** |

### Frozen artifact digests — unchanged since the freeze

| Artifact | SHA-256 |
|---|---|
| `schema_v0.2.1.sql` | `9fac9fa2552d2963a8fc8c0745eea4c71a12c193c161268a073b64c216b42688` |
| `seed_master_data_v0.2.1.sql` | `c8edb576500e6726487deab121b85fc1f6b99f6a07cc3f87e557b123807409da` |
| `openapi_v0.2.yaml` | `8e4bd4fbf171adfb3724d6ebb1acdc5d72fac12503fdf67fa8aa2175bf294724` |

---

## 2. CI evidence

`.github/workflows/postgres-execution-gate.yml`, two jobs, on every push and PR.

**Job `gate`** — package integrity → static audit → clean database from zero →
schema → seed ×2 → 70 contract assertions → OpenAPI lint → API inventory
freshness → dev reset and fixture idempotency.

**Job `authorization`** (needs `gate`) — architecture tests first, with no
database, so a route-to-repository bypass fails before anything slower runs;
then the full suite with `--junitxml`; then the evidence matrix in `--check`
mode. `reports/junit.xml` and the matrix are uploaded as artifacts on every
run, pass or fail.

Locally reproduced at the closure commit: gate exit 0 (70/70), suite 211/211,
matrix check PASS, inventory check PASS.

---

## 3. Test breakdown

| Suite | Tests | Covers |
|---|---:|---|
| `test_architecture` | 8 | Route→repository bypass, loader signatures, relations never queried, contract not writable |
| `test_contract_policy` | 12 | R10.2 cross-check, closed public list, literal roles, maker–checker |
| `test_authorization_integration` | 25 | §4 predicates on the frozen schema, Q9, cross-account sweep |
| `test_inv1_claim_authority` | 12 | INV-1 read and write halves |
| `test_conflict_disclosure` | 13 | INV-1 disclosure: 409 to entitled, 404 to unrelated, no leakage |
| `test_inv2_separation` | 15 | INV-2 at assignment and in existing data |
| `test_audit` | 15 | Q4 read-audit rules and the metadata floor |
| `test_http_endpoints` | 16 | 404/403, problem shape, trace id, contract conformance |
| `test_error_contract` | 17 | Code catalogue, detail leak refusal, handlers |
| `test_idempotency` | 13 | Replay, conflict, per-actor/route scope, expiry |
| `test_concurrency` | 21 | If-Match parsing, stale rejection, versioned tables |
| `test_dto_boundaries` | 24 | Allow-lists vs frozen schemas, scope ladder, redaction |
| `test_observability` | 17 | JSON logs, redaction, health and readiness |
| `test_transaction_audit_context` | 3 | `app.account_id` reaches `audit_row_change()` |
| **Total** | **211** | |

---

## 4. Authorization Evidence Matrix

`docs/gate/AUTHORIZATION_EVIDENCE_MATRIX.md` — 60 rules, generated from
`reports/junit.xml`. A rule whose mapping matches no test is reported
**UNPROVEN** and fails the check; the detector was itself verified by injecting
a rule with no test. Current state: **no UNPROVEN, no FAIL**.

---

## 5. Accepted deviations

| # | Deviation | Handling |
|---|---|---|
| D1 | **`If-Match` vs `If-Match-Version`.** API_CONTRACTS §2.4 names the header `If-Match-Version`; the frozen OpenAPI component `IfMatchVersion` declares `name: If-Match`. | Per the authority order in API_CONTRACTS §1, OpenAPI governs HTTP shape, so the wire header is `If-Match`. `If-Match-Version` is accepted as an alias so a client following the prose is not silently rejected. **Raised for the contract owner, not resolved unilaterally.** |
| D2 | **`parties` has no `version` column**, yet `PATCH /parties/{party_id}` requires `If-Match` in the frozen contract. | `parties` is deliberately absent from `VERSIONED_TABLES` and a version check against it raises rather than inventing a value. Closing this needs a schema change and is **a decision for Slice 1**, where PARTY is implemented. |
| D3 | **Read-access records go to the structured log stream**, not a dedicated table. | RFC-001 R6.3d left the destination open as explicitly non-blocking. The rules hold either way and the sink is swappable without touching a call site. |
| D4 | **Authentication treats the bearer as an opaque account id.** | Token issuance and signature verification are the authentication workstream. What is already final is that party, roles and status are read from the database per request (R3.2), so token design cannot widen authority. |
| D5 | **`getReasonCodes` policy has no contract counterpart.** | Decision 5 assigned it ADMIN/OPERATOR/REVIEWER; the contract declares no `x-roles`. Carried as the single named exception, and a test asserts it stays the only one. |

---

## 6. NOT IMPLEMENTED YET

Explicitly out of scope at Slice 0 closure. Nothing below is stubbed in a way
that could read as working.

**Domain (Slices 1–9), deliberately untouched**
- PARTY / CONTACT_POINT / USER_ACCOUNT / consent commands (Slice 1)
- REQUEST, criteria, freshness (Slice 2)
- PROPERTY / OFFER / SOURCE / truth / identity (Slice 3)
- Deterministic matching core (Slice 4)
- Human review → OPPORTUNITY (Slice 5)
- Diagnostic / information work (Slice 6)
- Communication / WhatsApp (Slice 7)
- External acquisition / assisted entry / self-service (Slice 8)
- AI assist (Slice 9, behind Stop Gate E)

**Slice 0 surface deliberately partial**
- Only 7 of 64 contract operations are wired: `/me/*` (4), `/reason-codes`,
  `/backoffice/queues/requests`, `/requests/{id}` (internal). The other 57 have
  policy entries and are denied by default until their slice implements them.
- `GET /requests/{request_id}` returns 501 after passing authorization: the
  staff projection is Slice 2.
- `GET /me/opportunities/{id}` renders the opportunity alone. Property and
  contact are not joined, so the scope ladder is exercised in unit tests but not
  yet end to end through a real opportunity — that is Slice 5.
- Idempotency and concurrency exist as services with full test coverage but are
  **not yet applied as middleware**, because the 34 idempotent and 4
  version-checked operations are all domain commands that do not exist yet.
- Alembic is not initialised. R14.4 fixes the approach — `schema_v0.2.1.sql` is
  the initial migration, stamped not autogenerated — and the first migration
  belongs with the first schema-touching change.
- No rate limiting, no RLS, no field-level encryption, no multi-tenancy
  (RFC-001 §16).
- Delegated authority and per-account claim revocation remain deferred by Design
  Ledger.

---

## 7. GO / NO-GO for Slice 1

### Recommendation: **GO**

**Why the core is ready.** Slice 1 implements PARTY, CONTACT_POINT,
USER_ACCOUNT and consent — the entities authorization is defined over. Those
predicates are in place and proved against the frozen schema, not against a
model of it: ownership, the claim gate, account-scoping, and the concealment
rules all hold under integration test. Slice 1 writes commands against a
boundary that already refuses the wrong caller, rather than retrofitting one.

The structural enforcement matters more here than the predicates. Slice 1 adds
its first real write paths; the architecture tests mean a new route physically
cannot reach a session, and deny-by-default means a new endpoint is unreachable
until someone writes its policy. The failure mode for a forgotten policy entry
is an outage, not a leak.

**What Slice 1 must carry with it**

1. **D2 first.** PATCH /parties/{id} requires `If-Match` and `parties` has no
   `version` column. This is a contract/schema contradiction that Slice 1 meets
   on day one, and per the authority policy it must be decided, not coded
   around. Options: add the column (schema change, new official package, gate
   re-run), or drop the If-Match requirement for parties (contract change).
   **This is the one item I would resolve before writing PATCH /parties.**
2. Apply the idempotency and concurrency services as middleware on the
   operations Slice 1 introduces; they are built and tested but unwired.
3. Consent binding is already enforced in the database by
   `enforce_consent_binding()`. The service must not re-implement a looser
   version of a rule the database enforces strictly (R7.2).
4. `POST /consents/bindings` is staff-only while `POST /consents/{id}/revoke`
   admits CUSTOMER. Revocation is deliberately easier than granting (R7.5).

**Residual risk**, stated plainly: the sharing-scope ladder and the
customer-facing opportunity render are unit-tested but not yet exercised through
a real opportunity, because no opportunity can exist before Slice 5. That is
sequencing, not a gap in Slice 0 — but it means the scope rules get their first
true end-to-end test late. I would re-run the DTO allow-list suite against real
joined data as soon as Slice 5 produces one, rather than treating the current
green as final proof of that specific rule.

No blocking issue was found. **GO**, with D2 resolved first.
