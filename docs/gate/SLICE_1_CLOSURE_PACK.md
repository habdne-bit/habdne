# TURAB — Slice 1 Closure Pack

**Slice 1 — PARTY / CONTACT_POINT / USER_ACCOUNT / CONSENT**
**Prepared:** 2026-09-19 · **Head:** `4f5714e` (plus this pack)
**Baseline:** Developer Handoff **v1.0.3**, technical pack **v0.2.3**, frozen.
**Status: feature-complete, submitted for closure review.**
The PASS declaration is the contract owner's, not the implementer's.

---

## 1. Verification results

| Check | Command | Result |
|---|---|---|
| Handoff package integrity | `docs/handoff/verify_handoff.py` | **PASS** — 36/36 files |
| Hardened static audit | gate step 1 | **PASS** — 131 FK refs, 0 errors, 0 warnings |
| Clean-DB schema + seed ×2 | gate steps 2–5 | **PASS** — idempotent re-seed |
| Database contract assertions | gate step 5 | **PASS** — 70/70 (T1–T12) |
| OpenAPI parse / lint | gate step 6 | **PASS** — 61 paths, 64 operations |
| Baseline version consistency | gate step 7 | **PASS** — 11/11 claims agree on `0.2.3` |
| **PostgreSQL Execution Gate** | `db/gate/run_gate.sh` | **PASS — 7/7** |
| Application suite | `pytest -q` | **PASS — 355/355** |
| OpenAPI drift | `generate_api_inventory.py --check` | **PASS** |
| Authorization evidence | `authorization_evidence.py --check` | **PASS — 97 rules, 0 UNPROVEN** |

Frozen artifact digests, unchanged since the v0.2.3 freeze:

```
schema_v0.2.3.sql            789841a1a41d869ca78de256879e62950f0672c9719c40a94408c549e28d98a0
seed_master_data_v0.2.3.sql  21b31c4ed338bb4aac24ea5d724b265e5e5b941bc54dd627f3953f3c2ff6cf10
openapi_v0.2.3.yaml          b3b1eb864836d14e275d58e312f960e0e45c7e5b80d2170b54c0e8b39c1f7b72
```

---

## 2. Deliverables against `IMPLEMENTATION_SLICES_v0.2.md`

| Handoff deliverable | Where | Status |
|---|---|---|
| create / read / update PARTY for staff | `services/parties.py`, `routes/parties.py` | **Done** — see D7 |
| verified phone control independent from account activation | `services/otp.py` | **Done** |
| attach one contact point to several parties without merging | `parties.attach_phone` | **Done** |
| activate account from a verified login contact point | `otp._activate_existing_account` | **Done** — activation only; see §5 |
| create / revoke consent grant | `services/consent.py` | **Done** |
| bind consent to a specific resource / purpose | `consent.bind_consent` | **Done** |

### Mandatory tests — all five, by name

| # | Handoff wording | Test |
|---|---|---|
| 1 | phone verification alone creates no account unless LOGIN is completed | `test_verify_phone_control_creates_no_account`, `test_login_purpose_creates_no_account_when_none_exists`, `test_login_activates_an_existing_invited_account` |
| 2 | same phone can be related to two PARTY records | `test_one_phone_can_reach_two_parties_without_merging` |
| 3 | revoked consent cannot authorize a new share/activation | `test_revoked_consent_cannot_bind` |
| 4 | consent for Party A cannot bind to Request of Party B | `test_consent_of_party_a_cannot_bind_to_request_of_party_b` |
| 5 | property consent requires an active Party↔Property relationship | `test_property_binding_requires_an_active_party_property_relation`, `test_an_expired_relation_does_not_authorize_a_property_binding` |

A sixth was added that the handoff does not list, because the five above leave
its question open. Test 1 proves verification creates no account; test 2 proves
a shared contact point never merges parties. Together they invite the inverse:
if a customer *attaches* a phone to their own party, does that phone now reach
their account? It does not — `party_contact_points` and
`user_accounts.login_contact_point_id` are different relationships and only the
second authenticates — and that is now asserted rather than reasoned:
`test_attaching_a_phone_to_a_party_creates_no_login_path` and
`test_a_shared_line_does_not_authenticate_as_the_party_that_shares_it`.

Both were confirmed to fail against the exact regression they describe: a
resolver joining `party_contact_points` instead of `login_contact_point_id` was
applied temporarily, both tests failed, and the mutation was reverted.

---

## 3. Contract surface

All **11** Slice 1 contract operations are wired; **18** of 64 in total; **zero**
operations are served that the frozen contract does not declare.

| Operation | Method / path | Roles |
|---|---|---|
| `postParties` | POST `/parties` | ADMIN, OPERATOR *(see D7)* |
| `getPartiesPartyId` | GET `/parties/{party_id}` | ADMIN, OPERATOR, REVIEWER |
| `patchPartiesPartyId` | PATCH `/parties/{party_id}` | ADMIN, OPERATOR, CUSTOMER (own) |
| `getPartiesPartyIdTimeline` | GET `/parties/{party_id}/timeline` | ADMIN, OPERATOR, REVIEWER |
| `attachPartyPhoneContactPoint` | POST `/parties/{party_id}/contact-points/phone` | ADMIN, OPERATOR, CUSTOMER (own) |
| `postPartiesPartyIdConsents` | POST `/parties/{party_id}/consents` | ADMIN, OPERATOR, CUSTOMER (own) |
| `postConsentsBindings` | POST `/consents/bindings` | ADMIN, OPERATOR |
| `postConsentsConsentIdRevoke` | POST `/consents/{consent_id}/revoke` | ADMIN, OPERATOR, CUSTOMER (own) |
| `postAuthOtpStart` | POST `/auth/otp/start` | unauthenticated |
| `postAuthOtpVerify` | POST `/auth/otp/verify` | unauthenticated |
| `getMeParty` | GET `/me/party` | CUSTOMER |

Idempotency and optimistic concurrency are no longer services awaiting a
caller: both are now **applied**, with the requirement **derived** from the
frozen contract rather than transcribed — 34 operations declare
`Idempotency-Key`, 4 declare `If-Match-Version`, and `auth/contract.py` reads
those counts from the OpenAPI so the policy cannot drift from it.

---

## 4. Test breakdown — 355 cases, 280 distinct functions

| File | Cases | Covers |
|---|---:|---|
| `test_concurrency.py` | 26 | `If-Match-Version`, integer-only, no alias |
| `test_dto_boundaries.py` | 26 | Public / Customer / Internal allow-lists |
| `test_authorization_integration.py` | 25 | RFC-001 §4 object authority |
| `test_slice1_http.py` | 23 | the Slice 1 surface end to end |
| `test_slice1_mandatory.py` | 23 | the five mandatory tests + the login-path pair |
| `test_architecture.py` | 20 | Q6 structural rules, incl. the command object gate |
| `test_slice1_timeline.py` | 19 | scoping, allow-list, pagination, list audit |
| `test_error_contract.py` | 17 | §2.5 problem+json |
| `test_observability.py` | 17 | §8 health, readiness, redaction |
| `test_http_endpoints.py` | 16 | transport-level contract |
| `test_audit.py` | 15 | Q4 read auditing |
| `test_inv2_separation.py` | 15 | INV-2 |
| `test_conflict_disclosure.py` | 13 | concealment-safe conflict disclosure |
| `test_idempotency.py` | 13 | §2.3 |
| `test_contract_policy.py` | 12 | policy table ≡ frozen contract |
| `test_inv1_claim_authority.py` | 12 | INV-1 |
| `test_slice1_bola.py` | 11 | DEFECT-001, each exploit asserted closed |
| `test_version_consistency.py` | 9 | D6 baseline hygiene |
| `test_migrations.py` | 20 | R14.4–R14.7, structural fingerprint, stamp guard |
| `test_correction_001.py` | 20 | D7 acceptance criteria and the correction mechanism |
| `test_transaction_audit_context.py` | 3 | R6.2 actor attribution |
| **Total** | **355** | |

Counts are pytest CASES, taken from `reports/junit.xml`; a parametrised
function contributes one case per parameter, which is why they exceed the 280
distinct test functions.

Evidence per rule: `docs/gate/AUTHORIZATION_EVIDENCE_MATRIX.md`, generated
from `reports/junit.xml`. A rule matching no test is reported **UNPROVEN** and
fails the check; there are none.

---

## 5. Defects found and closed in this slice

### DEFECT-001 — BOLA on the command surface (critical, closed)

Slice 1 first shipped the role gate without the object gate on write paths. A
customer could rename any party, attach a phone to any party, and mint
owner-less parties. **Reproduced against the running application before any fix
was written**, then closed with two guards, an AST-level architecture test that
fails the build on any unguarded mutating route, and 10 regression tests.
Full record, including root cause: `docs/gate/DEFECT-001-command-surface-object-gate.md`.

The root cause is the part worth carrying forward. The object gate was made
structural for reads and left conventional for writes; no test failed because
no test asked. **The evidence matrix reported PASS on 73 rules and was silent
on the one that mattered** — an evidence matrix proves what it lists and says
nothing about what it lacks, and that silence, not the missing guard, is the
failure mode this slice should be remembered for.

### Two smaller corrections

- An `assert_no_forbidden_fields(..., INTERNAL)` call that **exempts INTERNAL
  by definition** was removed from the timeline route. It read as a check while
  doing nothing — the same failure mode at a smaller scale.
- The staff predicate in `revoke_consent` was `roles == {CUSTOMER}`, which
  calls a role-less subject "staff". It was correct only because the role gate
  runs first. Unified onto `CommandService.is_staff` so the question has one
  answer everywhere.

---

## 6. Open decisions

| # | Item | Status |
|---|---|---|
| **D7** | `POST /parties` is restricted to ADMIN and OPERATOR. | **CLOSED — ratified 2026-09-19.** Applied as `CORRECTION-001` through the contract-corrections overlay, which never edits the published package and can only narrow. Design Ledger DL-01. Acceptance criteria and evidence: `docs/contract/CORRECTION-001-post-parties-roles.md`. No database migration: the change is contract and permissions only. |
| D3 | Read-access records go to the structured log stream, not a table. | Carried from Slice 0; RFC-001 R6.3d left the destination open. |
| D4 | The bearer is an opaque account id; token issuance is the authentication workstream. | Carried. R3.2 already ensures token design cannot widen authority. |
| D5 | `getReasonCodes` has no contract `x-roles`; decision 5 governs. | Carried, with a test asserting it stays the only exception. |
| Q7 | Customer delegated authority. | Deferred to a later version by decision 4. |
| — | Per-account claim revocation. | Deferred by Design Ledger note. |

D1 and D2 are **closed**: the canonical header is `If-Match-Version`, integer
only, with no alias, and `parties.version` exists in v0.2.3.

---

## 7. NOT IMPLEMENTED YET

Nothing below is stubbed in a way that could read as working.

**The account gap, stated per path.** Corrected after review, which asked for
precision rather than a single sentence:

| Path | Status |
|---|---|
| Create a USER_ACCOUNT | **Not implemented.** No application code inserts into `user_accounts`. |
| Bind an account to a PARTY (`party_id`) | **Not implemented.** No application code writes the column. |
| Set the login contact point | **Not implemented.** The column is READ by the login flow and written nowhere. |
| **Activate an account** | **Implemented.** `INVITED → ACTIVATED` on a verified LOGIN; `SUSPENDED`/`DISABLED` untouched. This is the Slice 1 deliverable and it is delivered. |
| Assign a role | **Service exists, no caller.** `services/roles.py:grant_role` enforces INV-2 and is tested, but nothing invokes it, and it performs no actor authorization, no audit and no self-escalation check. |

**Impact.** An account can only be activated if it already exists, and nothing
in TURAB can bring one into existence: today accounts and roles reach the
database only through `db/fixtures/dev_fixtures.sql`. The frozen contract
declares no operation for any of it — zero across all 64 operations — so this
is not a deviation from the contract but a gap the contract carries.
Slice 2 development may proceed on controlled test accounts; **readiness for a
real pilot may not be declared on the strength of fixtures.**

Specification, not yet authorised for implementation:
`docs/contract/ACCOUNT_PROVISIONING_MINI_CONTRACT.md` (Design Ledger DL-07).

**Domain slices not begun** — REQUEST/criteria/freshness (2), PROPERTY/OFFER/
SOURCE/truth (3), deterministic matching (4), human review → OPPORTUNITY (5),
diagnostic work (6), communication/WhatsApp (7), external acquisition and
self-service (8), AI assist (9, behind Stop Gate E).

**Elsewhere**
- 46 of 64 contract operations remain unwired; each has a policy entry and is
  denied by default until its slice implements it.
- `GET /requests/{request_id}` returns 501 after passing authorization (Slice 2).
- `GET /me/opportunities/{id}` does not join property or contact, so the scope
  ladder is unit-tested but not yet exercised end to end (Slice 5).
- ~~Alembic is still not initialised.~~ **Done after this pack was drafted**,
  as the groundwork Slice 2 cannot proceed without: `db/migrations/` with
  `schema_v0.2.3.sql` as revision `0001`, digest-guarded, autogenerate refused,
  and `reset_db.sh` stamping. See `docs/gate/MIGRATION_POLICY.md`.
- No rate limiting, no RLS, no field-level encryption, no multi-tenancy
  (RFC-001 §16).
- `interactions` rows are written by nothing yet: the timeline endpoint reads a
  table that only Slice 7 will populate operationally. It is tested against
  inserted rows, and correct, but it will return empty pages in practice until
  then.

---

## 8. Recommendation

**Slice 1 is submitted as complete**, subject to two things that are the
contract owner's to settle and not the implementer's:

1. **Ratify or redirect D7.** Every other item above is carried, closed or
   deferred by an existing decision; D7 is the one live divergence.
2. **Note the account-provisioning gap (§7)** as product scope, so it is
   scheduled deliberately rather than discovered at pilot.

The one piece of groundwork that fell due regardless of the above —
**initialise Alembic with `schema_v0.2.3.sql` as the initial migration** — was
completed immediately after this pack was drafted, because Slice 2 adds
columns and doing it first keeps the frozen baseline and the migration history
honest with each other from the first change rather than reconstructing them
afterwards. It changes no domain model, workflow, permission or matching rule,
so it needed no approval. Policy and evidence:
`docs/gate/MIGRATION_POLICY.md`.

Nothing else is outstanding on the implementation side. **D7 is now closed and Slice 2 is
authorised to begin.**
