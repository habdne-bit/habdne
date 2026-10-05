# Slice 4 — Closure record

**Slice 4 — Deterministic Matching Core**
**Status: CLOSED at `58368d1`, within the approved scope**, on the review of
58368d1. That review also closed step 8.
**Baseline:** Developer Handoff v1.0.3, technical pack v0.2.3, frozen.
**Plan:** `docs/gate/SLICE_4_PLAN.md`, revision 20, its final revision.

The closing decision is the reviewer's. This record states it, and its
limits, as they were given. It adds no claim of its own.

---

## 1. The decision

> I accept the correction of R-S4-8-01 and the application of G4-19 (a),
> and close step 8 and Slice 4 within the approved scope. G4-5R stays open,
> and running matching for RENT stays refused.

What the review checked itself:
- **The bundle:**
  - its declared digest;
  - the 337 manifest entries;
  - `run_binding.py` (`bound`);
  - `stop_gate_d_evidence.py --check` (exit 0).
- **R-S4-8-01, both cases, run directly from the delivered code.** The
  re-derivation reported the STALE state that contradicts its confirmation
  time, and the CURRENT state that contradicts a revoked grant.
- **G4-19:**
  - the run uses one digest for the hash, the explanation and the
    diagnostic;
  - the 20 historical pairs match the rule pins and the current digest;
  - the four PostgreSQL-free history tests pass;
  - `replay` reports UNPROVEN for an unattributed format or digest, without
    substituting the current one.

## 2. The limits of the decision

These limits are part of the decision. They are not caveats added by the
implementer.

1. **The results are ours, bound to the tree.** The reviewer re-ran no
   PostgreSQL test and no mutation. Three results rest on our own runs:
   - the suite, 1957/1957;
   - the 76 mutations of steps 7 and 8;
   - the gate, 8/8.

   Each is bound to its tree by commit and source fingerprint; none is an
   independent run.
2. **The git evidence of the registry history is a saved record.**
   `docs/gate/evidence/REGISTRY-HISTORY.txt` cannot be re-extracted from
   the delivered archive, which carries no repository history. It is
   checkable only against the repository itself.
3. **G4-5R is open.** No rent period is defined, so running matching for a
   RENT request stays refused, with a typed 422 that names G4-5R.

## 3. The evidence the decision rests on

Every row below ran on the same source, fingerprint
`5906ae50ff1a21667f3c012dbfbb960e46f56b960020b4ed0851a7edb7ba4012`.

| Evidence | Result | Commit | Tree | Record |
|---|---|---|---|---|
| Application suite (`record_test_run.py`) | 1957 passed, 0 failed, 0 errors, 0 skipped | `333b5f7` | clean | `evidence/TEST-RUN-PROVENANCE.txt` |
| PostgreSQL execution gate (`record_gate_run.sh`) | 8/8 PASS; contract, inventory and policy table agree on 67 operations | `cbb82dd` | clean | `evidence/gate-run.txt` |
| Step 8 mutations | 25/25 fail, none survives | `1981f3a` | clean | `evidence/SLICE4-STEP8-MUTATIONS.txt` |
| Step 7 mutations | 51/51 fail, none survives | `1981f3a` | clean | `evidence/SLICE4-STEP7-MUTATIONS.txt` |
| STOP GATE D | generated from the run at `333b5f7`; `--check` exits 0. Reconstruction: 82 matches; replay: 90 | `58368d1` | clean | `SLICE_4_STOP_GATE_D.md` |
| Authorization matrix | 151 rules, 151 PASS, 0 UNPROVEN | `cbb82dd` | clean | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| Registry history | the pins at `7a223d7` give the recorded digest; no commit since touched the registry's files | `1981f3a` | clean | `evidence/REGISTRY-HISTORY.txt` |

The earlier steps' mutation records stay in git history, each at the commit
it was taken on.

## 4. What was delivered, by step

| Step | Content | Closed at |
|---|---|---|
| 1 | CORRECTION-004 (the policy version, required), migration `0005` (match history immutability) | `95f0732` |
| 2 | canonical JSON and the input hash; the rule registry and its pins; the policy loader; the request, property and commercial snapshots | `431e896` |
| 3 | the candidate set (G4-8, G4-9 (a)) | `6b833fb` |
| 4 | the criterion rules, the unknown classification, the hard and information gates | `3c4816c` |
| 5 | the freshness and permission gates, eligibility precedence | `a5ea6f5` |
| 6 | the soft score (G4-12, `score.soft@2`), the pinned gates | `ee7fbc0` |
| 7 | `POST /requests/{id}/matching/run`: persistence, audit, the diagnostic row, concurrency (G4-15 D1–D6) | `dcf834a` |
| 8 | `GET /matches/{id}`, `GET /requests/{id}/diagnostic`, the ten mandatory tests, the scenarios, STOP GATE D; G4-19 (a) | `58368d1` |

**Contract and schema changes:**
- **Contract:** CORRECTION-004 only, which narrows.
- **Migration:** `0005` only.
- **No new table, column or reason code** (acceptance condition 4).

## 5. Decisions, as recorded in the plan

| # | Decision |
|---|---|
| G4-1 | CORRECTION-004 |
| G4-2 | a code registry keyed by `(id, version)`, pinned, versions added beside; the gates pinned too |
| G4-3 | (b) |
| G4-4 | approved |
| G4-5 | SALE only. **G4-5R open:** the RENT refusal |
| G4-6, G4-7 | approved |
| G4-8, G4-9 | approved; G4-9 (a) |
| G4-10, G4-11 | approved, with PUBLIC_LISTING_ALLOWED; the permission reason kept visible |
| G4-12 | approved; the column target weighs 2, as PREFERRED |
| G4-13 | approved |
| G4-14 | migration `0005` |
| G4-15 | D1–D6, with constraints; the policy faults are two typed 500s |
| G4-17 | (a) |
| G4-18 | (b) |
| G4-19 | (a), with its historical conditions |
| G4-16 | not decided: Slice 2's criterion entry is unchanged, and the run refuses instead |

## 6. Carried forward, unchanged by this closure

- **G4-5R is open.** A RENT run is refused, and no rent price is ever
  compared.
- **The boundary with Slices 5 and 6 (G4-15 D1):**
  - no path writes `match_reviews`, `opportunities` or tasks;
  - `suggested_actions` and `relaxation_scenarios` are empty;
  - `next_action` is a recommendation only.
- **The near match (D2)** is a narrower, conservative operational reading of
  "fails one or two conditions". It does not claim every form of that
  phrase.
- **A new rule version needs an entry in `registry_history.HISTORY`, in the
  same change** (`test_the_current_registry_is_recorded_in_the_history`).
  Format-1 rows are attributed to the registry of `7a223d7` alone.
- **Carried from Slice 3, unchanged:**
  - relations are never an authorization source, nor a matching input;
  - G3-2 is open, and PROPERTY claims fail closed;
  - account provisioning (G3-5) and D4 are open.
- **`SLICE_3_STOP_GATE_C.md` is stale against the current tree,** as
  `SLICE_4_STEP1_DELIVERY.md` §4 records. Its generator's condition 6 now
  names the one approved writer of `match_candidates`.
- **The evidence discipline carries into the next slice:**
  - results are bound to commit and source fingerprint;
  - a defect is measured before it is fixed;
  - mutation evidence is taken on a clean tree;
  - every delivered document carries a sha256.

## 7. Next

Planning the next slice, when the reviewer directs it. No code for it until
its plan is approved.
