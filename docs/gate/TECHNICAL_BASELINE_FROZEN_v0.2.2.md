# TURAB — Technical Baseline Freeze Record, v0.2.2

**Status:** **FROZEN**
**Date:** 2026-09-19
**Supersedes:** `TECHNICAL_BASELINE_FROZEN.md` (v0.2.1), retained as the record
of the previous freeze.

Authorised on the condition that the complete gate, the expanded gate suite,
the Slice 0 suite and the OpenAPI drift check all pass on the official v1.0.2
package. All did.

---

## What is frozen

| | |
|---|---|
| **Handoff package** | TURAB Developer Handoff **v1.0.2** (official), vendored unmodified, 32/32 |
| **Executable database authority** | `schema_v0.2.2.sql` + `seed_master_data_v0.2.2.sql` |
| **API contract** | `openapi_v0.2.2.yaml` |
| **Product baseline** | Foundation v1.0 FINAL — unchanged |

### Frozen artifact digests (SHA-256)

| Artifact | SHA-256 |
|---|---|
| `04_DATABASE/schema_v0.2.2.sql` | `eb1862b1984b7a62e29b1e58a490c2c6c4a1783cab01be66738cd1c97bb032ea` |
| `04_DATABASE/seed_master_data_v0.2.2.sql` | `132869b4b91a2c07925f352fdd71192cc26a90313a0a19a1844366141fedc553` |
| `05_API/openapi_v0.2.2.yaml` | `7e6187ce700c504060a0f0dc724174c35369b39ba6c24b99a64a06cf41005d07` |

---

## Acceptance before adoption

The package was checked against the D1 and D2 decisions **before** being
adopted, by two independent implementations that agree:

- `db/gate/verify_v022_baseline.py` (ours) → PASS
- `07_QA_ACCEPTANCE/verify_v022_baseline.py` (shipped in the package) → PASS

Diffs against v0.2.1 were read in full, not sampled:

- **schema** — header version/date, `version integer NOT NULL DEFAULT 1 CHECK
  (version > 0)` on `parties`, and `trg_parties_updated`/`set_updated_at()`
  replaced by `trg_parties_version`/`bump_version_and_timestamp()`. Nothing else.
- **seed** — two header comment lines only.
- **OpenAPI** — `info.version` 0.2.0 → 0.2.2; a patch note; the header renamed
  `If-Match` → `If-Match-Version` and retyped `string` → `integer, minimum: 1`;
  `version` added to `Party` and `CustomerPartyView`. Semantically: 64
  operations unchanged, no role changes, 59 schemas, none added or removed.

## Gate and suite results at the freeze

| Check | Result |
|---|---|
| Package integrity | **PASS** — 32/32 |
| Hardened static audit | **PASS** — 0 errors, **131** FK references |
| Clean database from zero | **PASS** — PostgreSQL 16.13 |
| `schema_v0.2.2.sql` | **PASS** |
| `seed_master_data_v0.2.2.sql` ×2 | **PASS** — 16 Adrar communes, 1 active policy |
| Expanded gate suite | **PASS** — 70/70 assertions |
| Full gate, twice | **PASS** — exit 0 both runs |
| Slice 0 suite | **PASS** — **218/218** |
| Authorization Evidence Matrix | **PASS** — 62 rules, none UNPROVEN |
| OpenAPI drift | **PASS** — generated inventory matches the contract |

### D2 verified on the live database

```
parties.version   integer NOT NULL default 1
parties check     CHECK ((version > 0))
parties trigger   trg_parties_version -> bump_version_and_timestamp
fk_constraints    131
tables            48
communes          16
```

---

## Deviations

D1 and D2 from the Slice 0 Closure Pack are **resolved** by this patch. One new
finding is recorded, not fixed locally.

| # | Finding | Status |
|---|---|---|
| **D6** | **`schema_metadata.schema_version` still reads `0.2.1` in `schema_v0.2.2.sql`.** A database built from the v0.2.2 schema identifies itself as 0.2.1. The v0.2.1 patch set the precedent by bumping this value from `0.2.0` to `0.2.1`; v0.2.2 does not, and `TECHNICAL_PATCH_v0.2.2.md` does not mention it. | **Open — raised, not patched.** No functional impact: no gate assertion, constraint, trigger or behaviour depends on it. It matters as the in-database marker of the deployed revision, which is what operations and any future Alembic stamp (R14.4) would read. Fixing it locally would breach the no-local-patch rule, so it is carried for an erratum or a v0.2.3. |
| D3 | Read-access records go to the structured log stream, not a table | Unchanged — RFC-001 R6.3d left this open as non-blocking |
| D4 | Authentication treats the bearer as an opaque account id | Unchanged — authentication workstream |
| D5 | `getReasonCodes` policy has no contract counterpart | Unchanged — decision 5, the single named exception |

### One judgement call, stated for the record

The contract now types the header `integer, minimum: 1`. v0.2.1 accepted
quoted and weak ETag forms (`"7"`, `W/"3"`) because `If-Match` conventionally
carries an ETag. `If-Match-Version` carries a version integer, so those forms
are **no longer accepted**: tolerating them would be a liberality the contract
does not describe. Tested both ways. Say so if you would rather they were kept.

---

## Slice 1

With D1 and D2 resolved, the blocker named in the Slice 0 Closure Pack is
cleared. `PATCH /parties/{party_id}` can now be version-checked as the contract
has always required, and `CustomerPartyView` exposes the `version` a customer
needs to satisfy it.
