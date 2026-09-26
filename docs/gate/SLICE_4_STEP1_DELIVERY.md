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

`docs/gate/SLICE_3_STOP_GATE_C.md` is evidence for the Slice 3 tree
(`96e36e6`, fingerprint `4aa193cc…4e50`). This step adds a migration and
changes the source. So `stop_gate_c_evidence.py --check` run against THIS
tree fails, by design:
- the migration list changes;
- the source fingerprint no longer matches the bound run.

The Slice 3 document is not regenerated. It stays the record of the tree it
was bound to.

## 5. What remains before step 2

Decisions **G4-2** (the rule registry) and **G4-13** (the input hash). Steps
3 to 8 need the decisions named in the plan's §8.
