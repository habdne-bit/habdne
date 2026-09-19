# TURAB — v0.2.2 / v1.0.2 Adoption Runbook

**Status:** WAITING FOR THE OFFICIAL PACKAGE.
**Blocking:** Slice 1 (PARTY domain) does not begin until the re-freeze completes.

The v0.2.2 decisions are recorded; the package that implements them has not been
issued. Per the standing rule, the frozen v0.2.1 handoff is **not patched
locally** — `docs/handoff/` remains byte-identical to the official v1.0.1 and
`verify_handoff.py` still reports 29/29.

---

## The decisions this package must implement

**D1 — concurrency header.** The canonical header for TURAB v0.1 is
`If-Match-Version`. The OpenAPI component `IfMatchVersion` currently declares
`name: If-Match`; it must declare `name: If-Match-Version`. The undocumented
`If-Match` alias in our code is removed on adoption — there is no production
client needing backward compatibility.

**D2 — PARTY concurrency.** `parties` gains
`version integer NOT NULL DEFAULT 1 CHECK (version > 0)`, and its trigger
changes from the timestamp-only `set_updated_at()` to the existing
`bump_version_and_timestamp()`. `version` is added to the **internal** Party
response schema and to **CustomerPartyView**, so a CUSTOMER can obtain the
version that `PATCH /parties/{party_id}` requires.

---

## Step 1 — verify the package against the decisions, before adopting

```bash
db/gate/verify_v022_baseline.py <unpacked-package-root>
```

`db/gate/verify_v022_baseline.py` asserts D1 and D2 point by point and checks
that nothing else moved. A package is not adopted because it is labelled
v1.0.2; it is adopted because it does what was decided.

Run against the current v0.2.1 package it fails with exactly the eight deltas
the patch must close, which is how we know the check is not vacuous:

```
D1: header is named 'If-Match', expected 'If-Match-Version'
D1: parameters still declaring the old If-Match header: ['IfMatchVersion']
D2: parties must gain `version integer NOT NULL DEFAULT 1 CHECK (version > 0)`
D2: parties must use bump_version_and_timestamp(), none found
D2: the timestamp-only trigger must be replaced, still present: ['trg_parties_updated']
D2: CustomerPartyView must expose `version` …
D2: no internal Party response schema exposes `version` (looked at ['Party', 'PartyCreate', 'PartyPatch'])
the schema is byte-identical to v0.2.1: the patch changes nothing
```

It also checks the two v0.2.1 FK fixes have not regressed.

## Step 2 — adopt

Replace `docs/handoff/` wholesale with the official package, then
`verify_handoff.py`. No local edit, exactly as v1.0.1 was adopted.

## Step 3 — code changes that follow adoption

Each is a consequence of D1 or D2, listed so adoption is mechanical rather than
improvised. **None may be applied before the package lands**: several would
break against v0.2.1, which is correct — those tests are drift detectors.

| # | File | Change |
|---|---|---|
| 1 | `src/turab/services/concurrency.py` | `HEADER = "If-Match-Version"`; delete `HEADER_ALIAS` and the `alias` parameter of `parse_if_match` (D1) |
| 2 | `src/turab/services/concurrency.py` | `VERSIONED_TABLES` gains `"parties": "party_id"` (D2) |
| 3 | `src/turab/dto/boundaries.py` | `CustomerPartyView` gains `version: int` (D2) |
| 4 | `tests/test_concurrency.py` | `test_header_name_follows_the_openapi_contract` expects `If-Match-Version`; delete `test_the_prose_header_name_is_accepted_as_an_alias` |
| 5 | `tests/test_concurrency.py` | `test_parties_is_not_versioned_in_the_frozen_schema` **inverts**: `parties` is now versioned, and a version check against it succeeds |
| 6 | `tests/test_dto_boundaries.py` | Add `CustomerPartyView` to the allow-list parametrisation, including `version`, and to the frozen-schema comparison |
| 7 | `db/gate/authorization_evidence.py` | Retarget the D1/D2 rules at the new tests; regenerate the matrix |
| 8 | `docs/gate/SLICE_0_CLOSURE_PACK.md` | Remove D1 and D2 from accepted deviations; record them as resolved by v0.2.2 |
| 9 | `db/gate/verify_v022_baseline.py` | Update `FROZEN_V021` digests to the new baseline, so the script guards the next patch rather than the last |

## Step 4 — re-freeze verification

```bash
db/gate/run_gate.sh                                   # expect 70/70, PASS
./.venv/bin/pytest -q                                 # expect all green
db/gate/generate_api_inventory.py docs/handoff/05_API/openapi_v0.2*.yaml
./.venv/bin/python db/gate/authorization_evidence.py
(cd docs/handoff && python3 verify_handoff.py)
sha256sum docs/handoff/04_DATABASE/schema_v0.2.*.sql \
          docs/handoff/04_DATABASE/seed_master_data_v0.2.*.sql \
          docs/handoff/05_API/openapi_v0.2*.yaml
```

Then a new freeze record pinned to the new baseline commit, as
`TECHNICAL_BASELINE_FROZEN.md` did for v0.2.1.

---

## Notes for whoever authors the patch

These come from inspecting the current package; they are not new decisions.

1. **The internal Party schema is `Party`** (`party_id`, `kind`, `status`,
   `display_name`, `legal_name`, `created_at`, `updated_at`). It is the response
   of three operations. `PartyCreate` and `PartyPatch` are inputs and should
   **not** gain `version` — a client does not submit it.
2. **Expected FK count is unchanged at 131.** Adding a column adds no foreign
   key, so the hardened static audit should still report 131. A different number
   means something else moved.
3. **Nothing in the seed or fixtures updates `parties`**, so introducing a
   version-bumping trigger there changes no existing row's version. Verified by
   search across `db/`, `tests/`, `src/` and the SQL baseline.
4. **`bump_version_and_timestamp()` already exists** and does
   `NEW.version := OLD.version + 1; NEW.updated_at := now();`. D2 needs no new
   function, only the trigger swap the decision names.
5. `CustomerPartyView` in the frozen contract currently exposes
   `party_id`, `display_name`, `contact_points`. Adding `version` makes it four
   fields, and our DTO allow-list test compares against the contract, so the two
   must move together.
