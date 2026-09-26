# Slice 4 · step 1 — CORRECTION-004 and migration `0005`

**Approved scope:** G4-1 and G4-14 only, answered on 2026-09-26 ("approve
step 1 only"). **No matching code exists.** No candidate, gate, snapshot,
hash or run was written. Every other decision (G4-2 to G4-13, G4-15, G4-16)
is still open, and no later step starts until it is decided.

Basis: `docs/gate/SLICE_4_PLAN.md` revision 2, §4 (G4-1, G4-14) and §8
(step 1). The facts behind both decisions were measured before any code
(`docs/gate/evidence/SLICE4-PLAN-MEASUREMENTS.txt` §A–§C).

## 1. CORRECTION-004 (G4-1)

`docs/contract/CORRECTION-004-matching-policy-version.md` gives the full
statement.

**The change.**
- `postRequestsRequestIdMatchingRun` now requires `matching_policy_version`,
  and the default `0.1.0`, which names no policy, is removed.
- It is applied in the effective contract through a new, validated overlay
  kind: `request_body_narrowings`.
- The frozen package is unchanged.

**The validator.** `turab.auth.contract.load_request_body_narrowings` is
used by the application at startup and by the generator. It refuses every
shape that would not be a narrowing, or that would be stale against the
package.

**Not delivered: the runtime rule.** The value must be the active policy's
version, or the request gets a typed 422. It belongs to the run route, which
is step 7. The correction document says so, and so does the effective
contract (`runtime-rule`).

**An existing test was generalised.**
`test_correction_001.py::test_the_effective_contract_changes_nothing_else`
assumed that every correction is a role correction. For a narrowed
operation, it now builds the expected operation by applying exactly the
narrowing to the frozen one. Nothing else may differ. The check is no
weaker: it is exact for the new kind too.

## 2. Migration `0005_match_history_immutability` (G4-14)

| Object | Refuses | Measured before (evidence) | Proven after by |
|---|---|---|---|
| trigger `prevent_match_criterion_result_update` | UPDATE and DELETE of a criterion result | FAIL → PASS, and deleted (§B) | `test_a_criterion_result_cannot_be_turned_from_fail_to_pass`, `…cannot_be_deleted`; append still allowed |
| trigger `prevent_match_diagnostic_run_update` | UPDATE and DELETE of a diagnostic run | updated and deleted (§B) | `test_a_diagnostic_run_cannot_be_updated`, `…cannot_be_deleted` |
| function `enforce_matching_policy_immutability()` + trigger `trg_matching_policy_immutable` | a change to `version`, `name`, `rules` or `immutable` of an immutable policy | `rules` and `version` changed (§C) | `test_an_immutable_policy_cannot_change` (4 cases); activation still allowed; a mutable policy editable until made immutable |

**Other properties of `0005`:**
- It reuses the frozen `prevent_immutable_history_change()`. The refusal a
  criterion result gives is the one a match row already gives.
- **Downgrade is refused**, like `0003`'s
  (`test_0005_refuses_to_downgrade`).
- **Ledger.** The four objects are declared in `db/gate/migration_deltas.py`,
  each with its digest taken from the catalog. The head-delta check passes
  in both directions: nothing undeclared, nothing claimed that is absent.
  `test_the_declared_deltas_for_0005_are_exactly_its_four_guards` pins the
  approved scope.
- **Static-audit counts.** `0005` is the first revision to add functions and
  triggers in `turab`. The count test now expects the audit's count, plus
  the declared additions, minus the declared removals. The adjustment is
  derived from the ledger (`MIGRATION_POLICY.md` §1c).
- **The interaction declared before approval, now pinned.** Deleting a
  request criterion that a result cites is refused, because
  `ON DELETE SET NULL` is an UPDATE of a guarded row
  (`test_deleting_a_request_criterion_a_result_cites_is_refused`). No code
  path deletes criteria.

**Not covered, because the approval does not name them:** DELETE of a
policy, and changes to `created_at` or `matching_policy_id`. A policy that
a match cites is already held by `ON DELETE RESTRICT`.

**One existing test had to change, and that is the guard working.**
`test_slice3_step4.py::test_a_policy_without_an_offer_terms_threshold_is_refused_not_defaulted`
edited the `rules` of the active, immutable policy, in a rolled-back
session. That is the edit G4-14 forbids. It now deactivates that policy and
activates a NEW policy without the threshold. The intent is unchanged: a
policy lacking the threshold is refused, not defaulted.

## 3. Mutation evidence

Both runs are on a clean tree at `896b8c7`, source fingerprint
`2a97f06e…39d0`:
- `db/dev/mutate_0005.py`: **11 of 11 fail**, none survive
  (`SLICE4-STEP1-0005-MUTATIONS.txt`);
- `db/dev/mutate_correction_004.py`: **8 of 8 fail**, none survive
  (`SLICE4-STEP1-CORRECTION-004-MUTATIONS.txt`).

Every mutated file was restored and verified by sha256.

**A first run, kept and not hidden**
(`SLICE4-STEP1-0005-MUTATIONS-FIRST-RUN.txt`, at `fb6aa03`). Z1 and Z4
"survived" there.
- They had turned the guard into an `AFTER INSERT` trigger. That made the
  fixture's own insert raise, so the tests ERRORED rather than testing an
  unguarded table.
- The runner counts only failures as kills, so it rightly reported them.
- The defect was in the mutation, not the tests. Z1 and Z4 now remove the
  `CREATE TRIGGER` statement, and each fails its tests on an assertion
  ("DID NOT RAISE"): 3 tests for Z1 and 2 for Z4.

## 4. Slice 3's STOP GATE C evidence, after this step

`docs/gate/SLICE_3_STOP_GATE_C.md` is evidence for the Slice 3 tree (run at
`0c97a6b`, fingerprint `4aa193cc…4e50`). It is **not regenerated**: it stays
the record of the tree it was bound to.

**Measured on this step's tree** (after the bound run at `1c6f3d5`):
- `run_binding.py` reports `bound`: this step's report is bound to this
  tree.
- `stop_gate_c_evidence.py --check` exits 1, with one problem: the document
  is **stale**.
- Re-rendering differs from the committed document in exactly two places:
  - the run it names: commit, fingerprint, report digest, and 1284 → 1314
    cases;
  - condition 4's migration list, which now includes `0005`.
- No mapped test is missing or failing (`problems: []`).

So the Slice 3 check fails here because the Slice 3 document describes a
different tree, and for no other reason.

## 5. What remains before step 2

- G4-2 and G4-13 are **decided** in the review of aad9f34, and recorded in
  the plan's revision 3.
- Step 2 starts once step 1 is closed.
- Steps 3 to 8 still need the decisions named in the plan's §8.

## 6. The review of aad9f34: a blocker in the CORRECTION-004 validator

**The defect.** The loader refused a duplicated correction ID, but not a
duplicated OPERATION. The generator indexes narrowings by operation, so a
second entry with another id **replaced** the first. The reviewer's
experiment on a temporary copy produced this:
- the loader accepted both;
- the application started;
- the effective contract required only `property_ids`;
- `matching_policy_version` was optional again, with `default: 0.1.0`;
- the marker named the second correction alone.

This silently undoes the approved narrowing, while the startup guard passes.

**Reproduced first**, on a `git archive` copy of `aad9f34`
(`evidence/SLICE4-STEP1-DUPLICATE-NARROWING-BEFORE-FIX.txt`, harness
verbatim):
- all five of those facts, as reported;
- a second, related defect: a field listed twice in `require` was accepted,
  and produced `required: [matching_policy_version, matching_policy_version]`.

**The fix.**
- `load_request_body_narrowings` refuses a second narrowing of an operation
  already narrowed, naming the first. It also refuses a field listed twice
  in `require`.
- The generator checks again, on its own, that no entry would overwrite
  another before it builds its per-operation index. So a future bypass of
  the loader still cannot drop a narrowing silently.

**Tests** (`tests/test_correction_004.py`, 5 new). The reviewer's exact
experiment is refused at each of the three places:
- `test_a_second_narrowing_of_the_same_operation_is_refused_by_the_loader`;
- `test_the_application_refuses_to_start_on_a_second_narrowing`;
- `test_the_effective_contract_is_not_generated_from_a_second_narrowing`
  (which also asserts the committed effective contract is untouched);
- `test_the_generator_refuses_an_overwrite_even_if_the_loader_let_it_through`
  (the defence in depth);
- `test_a_field_listed_twice_in_require_is_refused`.

All five fail on the `aad9f34` code; the other 15 pass. Mutations C9 to C11
are added, one per new check.

**The same experiment on the fixed tree** (`811c67b`) is recorded in the
evidence file, in its second half, run with the same harness:
- the loader, startup and the generator each refuse, naming CORRECTION-004;
- the effective contract keeps `required: [matching_policy_version]`, with
  no default.

The generator now reports an invalid corrections file as `REFUSED: …` with
exit 1, where it previously printed a traceback.
