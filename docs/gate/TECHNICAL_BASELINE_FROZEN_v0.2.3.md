# TURAB — Technical Baseline Freeze Record, v0.2.3

**Status:** **FROZEN**
**Date:** 2026-09-19
**Supersedes:** the v0.2.2 record, which was never declared Frozen because D6
stood against it. Earlier records are retained as history.

---

## What is frozen

| | |
|---|---|
| **Handoff package** | TURAB Developer Handoff **v1.0.3** (official), vendored byte-for-byte, 36/36 |
| **Executable database authority** | `schema_v0.2.3.sql` + `seed_master_data_v0.2.3.sql` |
| **API contract** | `openapi_v0.2.3.yaml` |
| **Architecture / API semantics** | v0.2 — unchanged |
| **Product baseline** | Foundation v1.0 FINAL — unchanged |

### Frozen artifact digests (SHA-256)

| Artifact | SHA-256 |
|---|---|
| `04_DATABASE/schema_v0.2.3.sql` | `789841a1a41d869ca78de256879e62950f0672c9719c40a94408c549e28d98a0` |
| `04_DATABASE/seed_master_data_v0.2.3.sql` | `21b31c4ed338bb4aac24ea5d724b265e5e5b941bc54dd627f3953f3c2ff6cf10` |
| `05_API/openapi_v0.2.3.yaml` | `b3b1eb864836d14e275d58e312f960e0e45c7e5b80d2170b54c0e8b39c1f7b72` |

---

## D6 resolved

`schema_metadata.schema_version` now reads `0.2.3`, confirmed on a database
built from the frozen schema. The correction is exactly as narrow as promised —
the three diffs against v0.2.2 were read in full:

- **schema** — two lines: the header version, and `('schema_version','0.2.1')`
  → `('schema_version','0.2.3')`.
- **seed** — two header comment lines.
- **OpenAPI** — `info.version` and one line of the description.

No domain, API or authorization semantic change. The digests moved because the
version stamps moved; nothing behavioural did.

## The invariant is now enforcing

`verify_version_consistency.py` is **gate step 7** and runs in CI. It reads the
eleven places a package states its baseline version and requires them to agree:

```
schema filename · seed filename · openapi filename · static audit script
filename · static audit results filename · technical pack manifest filename ·
schema header · schema_metadata.schema_version · seed header ·
openapi info.version · HANDOFF_MANIFEST.technical_baseline
```

On v0.2.2 it reported ten agreeing and one not, which is how D6 was pinned to a
single defect. On v0.2.3 all eleven agree.

It was deliberately kept out of the gate until this adoption: wiring it earlier
would have turned the gate red on a baseline already accepted on its runtime
results, which relitigates a decision rather than protecting the next one. The
two tests that documented D6 were **deleted, not inverted** — the finding no
longer exists, so tests asserting it would be fiction. The remaining tests were
made version-agnostic, deriving the expected version from the package, so the
next bump needs no test edits.

## Verification at the freeze

| Check | Result |
|---|---|
| Package integrity | **PASS** — 36/36, byte-for-byte |
| Version consistency | **PASS** — 11/11 claims agree |
| D1/D2 acceptance (v0.2.2 checks re-run) | **PASS** — preserved |
| Hardened static audit | **PASS** — 0 errors, **131** FK references |
| Clean database from zero | **PASS** — PostgreSQL 16.13 |
| Schema + seed ×2 (idempotency) | **PASS** — 16 Adrar communes, 1 active policy |
| Expanded gate suite | **PASS** — **70/70** assertions |
| Full 7-step gate, twice | **PASS** — exit 0 both runs |
| Slice 0 suite | **PASS** — **227/227** |
| Authorization Evidence Matrix | **PASS** — 63 rules, none UNPROVEN |
| OpenAPI drift | **PASS** — generated inventory matches the contract |

### Live database

```
schema_version    0.2.3
parties.version   integer, trigger bump_version_and_timestamp
fk_constraints    131
tables            48
communes          16
```

---

## Open deviations

D1, D2 and D6 are **resolved**. What remains is unchanged from the Slice 0
Closure Pack and none of it blocks Slice 1.

| # | Deviation | Status |
|---|---|---|
| D3 | Read-access records go to the structured log stream, not a table | RFC-001 R6.3d left this open as non-blocking |
| D4 | Authentication treats the bearer as an opaque account id | Authentication workstream |
| D5 | `getReasonCodes` policy has no contract counterpart | Decision 5, the single named exception |

---

## Slice 1

The foundation phase closes here. Every baseline-hygiene finding raised in this
sequence — the duplicate FK, the semantic duplicate FK, the header name, the
PARTY version, the version stamp — is resolved and, in each case, the class of
defect is now caught mechanically rather than by inspection.

Slice 1 is **PARTY / CONTACT_POINT / USER_ACCOUNT / CONSENT**, per
`IMPLEMENTATION_SLICES_v0.2.md`.
