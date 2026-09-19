# TURAB — v0.2.3 / v1.0.3 Adoption Runbook

**Status:** WAITING FOR THE OFFICIAL PACKAGE.
**Blocking:** v0.2.2 is **not** declared Frozen, and Slice 1 does not open, until
this adoption completes.

v0.2.2 is adopted and every runtime test passes, but it is not frozen: D6 stands.
The frozen v0.2.2 package is **not patched locally**; `docs/handoff/` remains
byte-identical to the official v1.0.2 and `verify_handoff.py` reports 32/32.

---

## What v0.2.3 must change

One line, and nothing else:

```
schema_metadata.schema_version = '0.2.3'
```

No domain, API or authorization semantic change. The three digests will move
because the filenames and the seeded value move; nothing behavioural does.

---

## Step 1 — verify before adopting

```bash
db/gate/verify_version_consistency.py <unpacked-package-root>   # must PASS
db/gate/verify_v022_baseline.py       <unpacked-package-root>   # D1/D2 preserved
```

Then read the three diffs against v0.2.2 in full, as was done for v0.2.2:
a narrow correction should show the version markers and nothing else.

### The invariant that would have caught D6

`db/gate/verify_version_consistency.py` is new, and it exists because D6 was a
version stated in **eleven places and wrong in one**. Nothing executable reads
`schema_metadata.schema_version`, which is why every runtime test passed over
it and a human had to notice.

Run against the current v0.2.2 package it reports:

```
schema filename                      0.2.2
seed filename                        0.2.2
openapi filename                     0.2.2
static audit script filename         0.2.2
static audit results filename        0.2.2
technical pack manifest filename     0.2.2
schema header                        0.2.2
schema_metadata.schema_version       0.2.1   <-- D6
seed header                          0.2.2
openapi info.version                 0.2.2
HANDOFF_MANIFEST.technical_baseline  0.2.2

VERSION CONSISTENCY: FAIL
```

Ten claims agree and one does not, which is also the evidence that D6 is a
single defect rather than a systemically mis-versioned package.

`tests/test_version_consistency.py` proves the check in both directions: it
passes on a corrected copy, and firing is verified for drift introduced in each
of the six places independently, so no claim is decorative.

**It is deliberately not yet wired into `run_gate.sh`.** Doing so now would turn
the gate red on a baseline that was accepted as green on its runtime results.
It becomes step 7 of the gate **as part of this adoption**, when it passes —
see step 3.

## Step 2 — adopt

Replace `docs/handoff/` wholesale with the official package; `verify_handoff.py`
must pass. No local edit.

## Step 3 — code changes

Far smaller than v0.2.2, because the correction is narrow.

| # | File | Change |
|---|---|---|
| 1 | `db/gate/run_gate.sh`, `db/dev/reset_db.sh`, `tests/conftest.py`, `src/turab/auth/contract.py`, `db/gate/lint_openapi.py`, `tests/test_architecture.py`, CI workflow | Filename references `v0.2.2` → `v0.2.3` |
| 2 | `db/gate/run_gate.sh` | **Add the version-consistency invariant as step 7**, so the class of defect can never reach a freeze again |
| 3 | `.github/workflows/postgres-execution-gate.yml` | Run the invariant in CI |
| 4 | `tests/test_version_consistency.py` | **Delete** `test_the_adopted_package_still_carries_d6` and `test_d6_is_the_only_version_drift_in_the_package`: the finding will no longer exist, so the tests documenting it are removed rather than inverted |
| 5 | `db/gate/verify_v022_baseline.py` | Add the v0.2.3 digests alongside the v0.2.2 ones |
| 6 | `docs/gate/` | New freeze record for v0.2.3; D6 marked resolved |
| 7 | `README.md` | Baseline and package version |

No change to `concurrency.py`, the DTOs, the policy layer or any test of
authorization: v0.2.3 touches none of it.

## Step 4 — re-freeze verification

```bash
db/gate/run_gate.sh                                     # 7 steps now, 70/70
./.venv/bin/pytest -q
db/gate/generate_api_inventory.py docs/handoff/05_API/openapi_v0.2.3.yaml
./.venv/bin/python db/gate/authorization_evidence.py
db/gate/verify_version_consistency.py docs/handoff      # must PASS
(cd docs/handoff && python3 verify_handoff.py)
```

Then the new baseline commit and the three digests, and v0.2.3 is Frozen.

---

## Note for whoever authors the patch

`schema_metadata.schema_version` is at **line 128** of `schema_v0.2.2.sql`:

```sql
  ('schema_version','0.2.1'),
```

It must read `'0.2.3'`. The precedent is v0.2.1, which correctly bumped it from
`'0.2.0'`; v0.2.2 did not, and `TECHNICAL_PATCH_v0.2.2.md` did not mention it.

If the package also renames the schema/seed/OpenAPI to `v0.2.3`, the invariant
covers that automatically — it checks that every claim agrees, not that any
particular value was chosen.
