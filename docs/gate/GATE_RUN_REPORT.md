# TURAB — PostgreSQL Execution Gate: Run Report

**Date:** 2026-09-18
**Gate reference:** `docs/handoff/04_DATABASE/POSTGRES_EXECUTION_GATE.md`
**Engine:** PostgreSQL 16.13 (Ubuntu 24.04), clean database built from zero
**Package under test:** `TURAB Developer Handoff v1.0`, database baseline at patch
revision **v0.2.1** (`verify_handoff.py` → PASS, 27/27 files)

---

## Verdict

> **POSTGRES RUNTIME GATE: PASS.**
>
> All six steps green, twice in succession, on a database rebuilt from zero each
> time. The single blocker found on the first run — a duplicated constraint
> declaration in `schema_v0.2.sql` — was corrected under approval as
> **schema v0.2.1**.
>
> Per `Master v1.0` §10, the Pre-Slice Gate is satisfied and **Slice 0
> (Application Skeleton + Security Boundaries) may begin**. Slices must then
> follow `IMPLEMENTATION_SLICES_v0.2.md` in order, and no advanced AI work may
> start before the Core Hypothesis Stop Gate passes (§10, Stop Gate E).

---

## Step results

| # | Gate step | Result |
|---|---|---|
| 0 | Handoff package integrity (`verify_handoff.py`) | **PASS** — 27/27 files, checksums intact |
| 1 | Static audit (`technical_pack_static_audit_v0.2.py`) | **PASS** — see the note on `foreign_key_refs` below |
| 2 | Clean database rebuilt from zero | **PASS** |
| 3 | `psql -f schema_v0.2.1.sql` | **PASS** — v0.2 failed here; see the blocker below |
| 4 | `psql -f seed_master_data_v0.2.sql` ×2 (idempotency) | **PASS** — 16 Adrar communes and 1 active policy stable across both runs |
| 5 | Database-level contract tests (11 required areas) | **PASS** — 65/65 assertions |
| 6 | OpenAPI parse / lint | **PASS** — 3.1.0, 61 paths, 64 operations, 527 `$ref` all resolve, no duplicate `operationId` |

The full runner was executed twice end to end (`run_gate.sh`, exit 0 both times,
65/65 contract assertions each). The package is unchanged by a run:
`verify_handoff.py` still reports 27/27 afterwards.

---

## The blocker found on the first run (resolved in v0.2.1)

`docs/handoff/04_DATABASE/schema_v0.2.sql` declares the same foreign key **twice**:

- **Line 508–510** — in section 9, immediately after `CREATE TABLE observations`.
  This placement is *required*: `consent_grants` (line ~295) is created before
  `observations`, so the FK cannot be declared inline on the table and must be
  added once `observations` exists.
- **Line 1336–1337** — again in section 15, "LATE FKs / CROSS-SECTION CONSTRAINTS".

Both declarations are byte-for-byte equivalent in effect:

```sql
ALTER TABLE consent_grants
  ADD CONSTRAINT fk_consent_evidence_observation
  FOREIGN KEY (evidence_observation_id) REFERENCES observations(observation_id) ON DELETE SET NULL;
```

PostgreSQL rejects the second one:

```
psql:schema_v0.2.sql:1337: ERROR:  constraint "fk_consent_evidence_observation"
                                   for relation "consent_grants" already exists
```

### Why the static audit did not catch it

`technical_pack_static_audit_v0.2.py` counts `REFERENCES` occurrences in the file
text (133) rather than the constraints a server actually creates (132). A textual
duplicate is invisible to it. This is precisely the failure mode the gate exists
to catch, and is why `Master v1.0` §2 records the runtime gate as `PENDING`
despite a `PASS` static audit.

### Impact

Structural only, and **zero semantic impact on the domain model**: the constraint
is still created by the line-509 declaration, over the same column, against the
same target, with the same `ON DELETE SET NULL` action. Confirmed on the live
database — 132 foreign-key constraints, and `fk_consent_evidence_observation`
present and enforcing.

Nothing about the domain model, workflow, permissions or matching logic changed.

### Resolution (approved)

The **section 9** declaration was removed; the constraint keeps its home in
section 15, the file's own designated place for cross-section constraints. The
corrected artifact was issued as a patch revision, `schema_v0.2.1.sql`, leaving
nothing named v0.2 carrying altered content. Affected artifacts were updated in
the same change, as `Master v1.0` §13 requires: the static audit script and its
results, all three checksum manifests, and the filename references in the
operative documents. `99_REFERENCE_HISTORY/MIGRATION_NOTES_v0.1_TO_v0.2.md` was
deliberately left untouched — it records a past migration and is history, not an
implementation baseline. Full detail in
`docs/handoff/99_REFERENCE_HISTORY/CHANGELOG_v0.2.md`.

One documented figure moves as a result: `Master v1.0` §2 records **133**
foreign-key references from the static audit; it is now **132**. The database is
identical either way — the old number counted a textual duplicate that no server
ever created.

---

## Contract test coverage

`db/gate/postgres_execution_gate_tests.sql` — 65 assertions covering all eleven
areas the gate names. The suite runs in one transaction and rolls back, so it is
repeatable and leaves the database clean (verified: two consecutive runs, 65/65 each).

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
pull request (`.github/workflows/postgres-execution-gate.yml`), satisfying the
kickoff requirement that CI rebuild a clean database from zero.

---

## Kickoff checklist — technical preflight status

| Item | Status |
|---|---|
| `technical_pack_static_audit_v0.2.py` returns PASS | Done |
| PostgreSQL 16+ clean database accepts the schema | Done — at v0.2.1 |
| `seed_master_data_v0.2.sql` executes twice without failure | Done |
| PostgreSQL Execution Gate tests pass | Done — 65/65 |
| `openapi_v0.2.yaml` parses/lints in CI | Done |
| CI can rebuild a clean database from zero | Done |
| Object-level authorization tests included from Slice 0 | Not started — Slice 0 is gated |
| Idempotency replay and conflict tests included from Slice 0 | Not started — Slice 0 is gated |

The last two items belong to Slice 0, which is now unblocked and is where they
are to be implemented.
