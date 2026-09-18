# TURAB — PostgreSQL Execution Gate: Run Report

**Date:** 2026-09-18
**Gate reference:** `docs/handoff/04_DATABASE/POSTGRES_EXECUTION_GATE.md`
**Engine:** PostgreSQL 16.13 (Ubuntu 24.04), clean database rebuilt from zero on every run
**Package under test:** **TURAB Developer Handoff v1.0.1** (official), vendored
**unmodified** under `docs/handoff/` — `verify_handoff.py` → PASS, 29/29 files
**Executable database authority:** `schema_v0.2.1.sql` + `seed_master_data_v0.2.1.sql`

---

## Verdict

> **POSTGRES RUNTIME GATE: PASS.**
>
> All six steps green on two consecutive full runs (`run_gate.sh`, exit 0 both
> times, 65/65 database assertions each). Both duplicate foreign keys are gone,
> the hardened static audit detects the class of defect that escaped v0.2, and
> the audit's reported figure now agrees exactly with what the server creates.
>
> The Pre-Slice Gate of `Master v1.0.1` §10 is satisfied. See
> `TECHNICAL_BASELINE_FROZEN.md` for the freeze record and the commit it pins.

---

## Step results

| # | Gate step | Result |
|---|---|---|
| 0 | Handoff package integrity (`verify_handoff.py`) | **PASS** — 29/29 files, checksums intact |
| 1 | Hardened static audit (`technical_pack_static_audit_v0.2.1.py`) | **PASS** — 0 errors, 0 warnings, **131** FK references |
| 2 | Clean database rebuilt from zero | **PASS** — PostgreSQL 16.13 |
| 3 | `psql -f schema_v0.2.1.sql` | **PASS** |
| 4 | `psql -f seed_master_data_v0.2.1.sql` ×2 (idempotency) | **PASS** — 16 Adrar communes, 1 active policy, stable across both runs |
| 5 | Database-level contract tests (11 required areas) | **PASS** — 65/65 assertions |
| 6 | OpenAPI parse / lint | **PASS** — 3.1.0, 61 paths, 64 operations, 527 `$ref` all resolve |

Every expectation set for this run was met: integrity PASS, enhanced static audit
PASS, **131** FK references, schema PASS, seed ×2 PASS, 65/65 assertions, OpenAPI
PASS, full gate PASS twice.

---

## Frozen artifact digests

SHA-256 as computed from the vendored files. Each value was cross-checked against
**both** `07_QA_ACCEPTANCE/TECHNICAL_PACK_MANIFEST_SHA256_v0.2.1.txt` and
`HANDOFF_MANIFEST.json`; all three agree, which confirms the gate ran against the
official artifacts unmodified.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| `04_DATABASE/schema_v0.2.1.sql` | 67,336 | `9fac9fa2552d2963a8fc8c0745eea4c71a12c193c161268a073b64c216b42688` |
| `04_DATABASE/seed_master_data_v0.2.1.sql` | 12,499 | `c8edb576500e6726487deab121b85fc1f6b99f6a07cc3f87e557b123807409da` |
| `05_API/openapi_v0.2.yaml` | 124,280 | `8e4bd4fbf171adfb3724d6ebb1acdc5d72fac12503fdf67fa8aa2175bf294724` |

The OpenAPI digest is **unchanged from v0.2**, confirming in evidence what
`TECHNICAL_PATCH_v0.2.1.md` asserts in prose: the patch touches the executable
database baseline only, never the API contract.

---

## Live database verification

Queried directly against the database left by the second run:

| Check | Value |
|---|---|
| Foreign-key constraints actually created | **131** |
| `schema_metadata.schema_version` | `0.2.1` |
| Base tables in schema `turab` | 48 |
| Communes seeded (Adrar) | 16 |
| Active matching policies | 1 |
| `%resolved_claim%` FK constraints | **1** |
| `%consent_evidence_observation%` FK constraints | **1** |

The static audit's 131 and the server's 131 now agree. Under v0.2 they did not:
the audit reported 133 textual `REFERENCES` occurrences while the server created
132 constraints and rejected the schema outright. Both formerly duplicated
foreign keys now exist exactly once.

---

## What v0.2.1 corrected

Two redundant declarations of the same relationship, both resolved by keeping the
late, centralized declaration and removing the earlier one.

**1 — Named duplicate (hard failure).**
`consent_grants.evidence_observation_id → observations.observation_id`, declared
twice under the identical name `fk_consent_evidence_observation`. PostgreSQL
rejected the second outright, so a clean database could not accept v0.2 at all.

**2 — Semantic duplicate (silent).**
`property_attributes.resolved_claim_id → claims.claim_id`, declared twice under
*different* names — `fk_property_attributes_resolved_claim` and
`fk_property_attribute_resolved_claim`. PostgreSQL accepts this: it creates two
constraints enforcing the same rule. It would not have failed the gate; it would
have shipped as redundant enforcement with no authoritative declaration.
`fk_property_attribute_resolved_claim` (remediation section) is retained.

Verified diff of official `schema_v0.2.1.sql` against the original
`schema_v0.2.sql`: the two removals above, the header version, the seeded
`schema_version` value `0.2.0` → `0.2.1`, and one explanatory comment. Nothing
else. The seed differs by its two header comment lines only.

---

## Static-audit hardening, verified by negative test

v0.2.1 adds two checks to the audit: duplicate constraint names on a table, and
semantically redundant foreign keys enforcing the same local columns → referenced
table/columns/delete behaviour under different names.

The hardening was confirmed rather than assumed. Running the **v0.2.1 audit
against the old, defective v0.2 schema** returns `FAIL` and names all three
findings:

```
SQL_DUP_CONSTRAINT_NAME  Duplicate FK constraint name on consent_grants:
                         fk_consent_evidence_observation
SQL_DUP_FK_SEMANTICS     Redundant FK on consent_grants(evidence_observation_id)
                         -> observations(observation_id)
SQL_DUP_FK_SEMANTICS     Redundant FK on property_attributes(resolved_claim_id)
                         -> claims(claim_id),
                         constraints=['fk_property_attribute_resolved_claim',
                                      'fk_property_attributes_resolved_claim']
```

The same audit returns `PASS` with zero errors on `schema_v0.2.1.sql`. The
defect class that escaped v0.2 is now caught statically, before a database is
ever touched.

---

## Contract test coverage

`db/gate/postgres_execution_gate_tests.sql` — 65 assertions covering all eleven
areas the gate names. The suite runs in one transaction and rolls back, so it is
repeatable and leaves the database clean.

| Gate requirement | Assertions | Representative checks |
|---|---|---|
| Opportunity gate | 8 | no OPPORTUNITY without an APPROVED latest review; a hard-`FAIL` candidate cannot even be approved; request/property pair must equal the candidate's; `current_offer_id` must initially equal `evaluated_offer_id` |
| Latest append-only match review | 7 | `match_reviews` and `match_candidates` reject UPDATE and DELETE; a later `NEED_MORE_INFORMATION` supersedes an earlier `APPROVED` without erasing it; `latest_match_reviews` resolves to the newest decision |
| Resolution lineage | 5 | resolved value must match its source claim's attribute *and* subject; dangling claim rejected; one `CURRENT` resolution per subject × attribute |
| Verification upgrade path | 5 | claim starts `DECLARED`; only a `CONFIRMED` event raises the level; a lower-level event cannot downgrade it; `NOT_CONFIRMED` changes nothing; `CONFLICT_FOUND` marks the claim `CONFLICTING` |
| Consent resource binding | 7 | purpose must equal granted scope; another party's consent rejected; `REVOKED` grant cannot bind; property binding needs an active party–property relation; exactly one resource per binding; revocation retains history |
| Alias → canonical property | 6 | alias/canonical pair must match the identity candidate; `CONFIRMED_SAME` requires an alias mapping; a canonical cannot itself be an alias and vice-versa; **alias property keeps its offers** (non-destructive) |
| Match commercial context BUY/RENT | 8 | `BUY` request cannot evaluate a `RENT` offer and vice-versa; offer must belong to the matched property; non-`POTENTIAL` property requires an evaluated offer; `POTENTIAL` may omit it; `offer_version` must snapshot the live version; matches must target canonical, never an alias |
| Assisted claim-state checks | 5 | `ASSISTED` ⇒ `UNCLAIMED`, `SELF_MANAGED`/`SHARED_MANAGEMENT` ⇒ `CLAIMED`, on both `requests` and `properties`; property attribute must match its resolved claim's subject |
| Protected hard deletes | 6 | `requests`, `properties`, `property_offers`, `claims`, `resolved_values`, `opportunities` all refuse DELETE |
| One active matching policy | 3 | seed leaves exactly one active after a double run; a second active policy is rejected; inactive drafts allowed |
| One open opportunity per Request × canonical Property | 4 | second open opportunity on the same pair rejected; allowed again only after the first is `CLOSED`; the closed one is retained; one opportunity per approved match |
| Provenance / audit | 1 | `audit_log` captured mutations on the critical entities |

---

## Reproducing

```bash
db/gate/run_gate.sh          # needs PostgreSQL 16+ and PGHOST/PGUSER/... set
```

CI runs the identical script against a `postgres:16` service on every push and
pull request (`.github/workflows/postgres-execution-gate.yml`).

---

## Kickoff checklist — technical preflight

| Item | Status |
|---|---|
| Static audit returns PASS | Done — hardened v0.2.1 audit |
| PostgreSQL 16+ clean database accepts the schema | Done |
| Seed executes twice without failure | Done |
| PostgreSQL Execution Gate tests pass | Done — 65/65 |
| `openapi_v0.2.yaml` parses/lints in CI | Done |
| CI can rebuild a clean database from zero | Done |
| Object-level authorization tests included from Slice 0 | Slice 0 scope — now unblocked |
| Idempotency replay and conflict tests included from Slice 0 | Slice 0 scope — now unblocked |
