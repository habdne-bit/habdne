# Slice 6 — closure evidence

**Generated** by `db/gate/slice6_evidence.py` from `docs/gate/evidence/junit-run.xml`. **Do not edit.**

> Slice 6, Match Diagnostic / Information Work (plan §6.4). **Not a STOP GATE.** **Its stated limits: SALE only (G4-5R open); K06 UNPROVEN; the two limits of §5 below.**

- The JUnit run is recorded at commit `0cdc714105b6235d692ce2f223d798ecbc7453d6`, source fingerprint `2d11e774856f78ba9217880297422066ea03fb6d5592e315588d7c157c3c5563`, report sha256 `92388a364d5225b39110a70a443dfedbf431d531a7110d401a12ed7dcfe56331` (`docs/gate/evidence/TEST-RUN-PROVENANCE.txt`).
- Counted in the report: 2614 test cases, 0 failures, 0 errors, 0 skipped.
- Binding (`db/gate/run_binding.py`): the report's digest and counts are the recorded ones, and the current tree's source fingerprint is the run's and the gate run's.
- Tests are named `module::name`.
- These are our runs; nobody else has re-run them.

## 1. The three mandatory tests (plan §6.1)

The end-to-end test (`test_slice6_step5`, every business row made over HTTP) is listed first; the function-level tests of step 3 follow.

| # | Handoff wording | Test | Status |
|---|---|---|---|
| 1 | document UNKNOWN on otherwise exact candidate becomes higher-priority task than suggesting a new location | `test_slice6_step5::test_mandatory_1_over_http_the_document_task_outranks_the_new_location` | PASS |
| 1 | document UNKNOWN on otherwise exact candidate becomes higher-priority task than suggesting a new location | `test_slice6_step3::test_mandatory_1_the_document_unknown_ranks_above_the_location_scenario` | PASS |
| 2 | candidate failing three hard criteria does not receive high-priority task for an unrelated unknown | `test_slice6_step5::test_mandatory_2_over_http_three_hard_failures_raise_no_task` | PASS |
| 2 | candidate failing three hard criteria does not receive high-priority task for an unrelated unknown | `test_slice6_step3::test_mandatory_2_a_candidate_failing_three_hard_criteria_gets_no_action` | PASS |
| 2 | candidate failing three hard criteria does not receive high-priority task for an unrelated unknown | `test_slice6_step3::test_mandatory_2_over_a_real_run` | PASS |
| 3 | relaxation scenario reports magnitude (e.g. +150M centimes / adjacent area), not only 'remove criterion.' | `test_slice6_step5::test_mandatory_3_over_http_the_magnitudes_after_the_document_fails` | PASS |
| 3 | relaxation scenario reports magnitude (e.g. +150M centimes / adjacent area), not only 'remove criterion.' | `test_slice6_step3::test_mandatory_3_the_budget_magnitude_is_1_500_000_dzd` | PASS |
| 3 | relaxation scenario reports magnitude (e.g. +150M centimes / adjacent area), not only 'remove criterion.' | `test_slice6_step3::test_g6_6_the_location_measured_in_step_0` | PASS |

## 2. Red-team cases (plan §6.2)

| Case | Statement | Test | Status |
|---|---|---|---|
| I01 | mandatory test 1 | `test_slice6_step5::test_mandatory_1_over_http_the_document_task_outranks_the_new_location` | PASS |
| I02 | a completion stores its outcome, note and evidence in one event and marks the task DONE, in one transaction; a failure between the two writes leaves neither | `test_slice6_step2::test_a_completion_appends_its_event_and_marks_the_task_done` | PASS |
| I02 | a completion stores its outcome, note and evidence in one event and marks the task DONE, in one transaction; a failure between the two writes leaves neither | `test_slice6_step2::test_i02_a_failure_between_the_two_writes_leaves_neither` | PASS |
| I03 | a run producing +1,500,000 DZD leaves the request, its version and its criteria unchanged; an explicit criterion changes it and the next run sees it | `test_slice6_step5::test_i03_a_scenario_changes_no_request_and_an_explicit_criterion_does` | PASS |
| D02 / R9.3 | an expectation between the maximum and the asking price: the magnitude is ask − max; the expectation reaches no diagnostic, task, task list or Slice 6 audit row; the staff match keeps it (F6-21, §6) | `test_slice6_step5::test_d02_the_expectation_reaches_no_diagnostic_task_or_slice_6_audit` | PASS |
| D02 / R9.3 | an expectation between the maximum and the asking price: the magnitude is ask − max; the expectation reaches no diagnostic, task, task list or Slice 6 audit row; the staff match keeps it (F6-21, §6) | `test_slice6_step3::test_the_seller_expectation_is_never_stated_nor_used` | PASS |
| D02 / R9.3 | an expectation between the maximum and the asking price: the magnitude is ask − max; the expectation reaches no diagnostic, task, task list or Slice 6 audit row; the staff match keeps it (F6-21, §6) | `test_slice6_step2::test_every_writers_task_is_listed_and_no_payload_carries_a_private_value` | PASS |
| K05 | a completion replayed with its key returns the first response and writes nothing | `test_slice6_step2::test_k05_a_replay_returns_the_first_response_and_writes_nothing` | PASS |
| G04 / G06 | replay (G6-11); a run with no candidate writes an empty, valid format 2 | `test_slice6_step5::test_g06_a_run_with_no_candidate_writes_an_empty_valid_format_2_that_replays` | PASS |
| G04 / G06 | replay (G6-11); a run with no candidate writes an empty, valid format 2 | `test_slice6_step4::test_a_row_the_run_wrote_is_format_2_and_replays` | PASS |
| G04 / G06 | replay (G6-11); a run with no candidate writes an empty, valid format 2 | `test_slice6_step3::test_g6_11_two_runs_one_reused_match_both_replay` | PASS |
| G04 / G06 | replay (G6-11); a run with no candidate writes an empty, valid format 2 | `test_slice6_step3::test_the_replay_never_reads_tasks` | PASS |

**K06 — UNPROVEN** (G6-12). The application role is a superuser and owns every table (EN-02). The refusals below are trigger-level, and are never counted as K06:

- `test_migration_0007_task_work_and_evidence::test_a_completion_event_cannot_be_updated` passes (trigger-level)
- `test_migration_0007_task_work_and_evidence::test_a_completion_event_cannot_be_deleted` passes (trigger-level)
- `test_migration_0007_task_work_and_evidence::test_a_cited_observation_cannot_be_updated` passes (trigger-level)
- `test_migration_0007_task_work_and_evidence::test_a_cited_observation_cannot_be_deleted` passes (trigger-level)

## 3. What the reviews of Slice 6 asked to be proven

| Review | Obligation | Test | Status |
|---|---|---|---|
| `b6a08e7` | OQ6-1's obligation: every diagnostic task has `request_id` and `entity`, `id`, `gate`, `basis` non-NULL, and `source` = `"DIAGNOSTIC"` exactly | `test_slice6_step4::test_a_high_suggestion_raises_one_task_with_its_subject` | PASS |
| `b6a08e7` | OQ6-1's obligation: every diagnostic task has `request_id` and `entity`, `id`, `gate`, `basis` non-NULL, and `source` = `"DIAGNOSTIC"` exactly | `test_slice6_step4::test_every_diagnostic_task_carries_a_complete_key` | PASS |
| `b6a08e7` | the completion locks the task, then the cited observation FOR SHARE, before its event | `test_slice6_step2::test_the_task_is_locked_before_the_observation` | PASS |
| `b6a08e7` | the completion locks the task, then the cited observation FOR SHARE, before its event | `test_slice6_step2::test_r2a_r2c_a_change_after_the_lock_waits_and_is_refused` | PASS |
| `b6a08e7` | the completion locks the task, then the cited observation FOR SHARE, before its event | `test_slice6_step2::test_r2b_an_update_before_the_lock_is_the_body_cited` | PASS |
| `b6a08e7` | the completion locks the task, then the cited observation FOR SHARE, before its event | `test_slice6_step2::test_r2d_a_delete_before_the_lock_is_refused_typed_writing_nothing` | PASS |
| `220573a` | the supersession of an older match, measured in the queue and at approval | `test_slice6_step4::test_an_older_match_is_superseded_in_the_queue_and_at_approval` | PASS |
| `922a100` | a real format-2 row written by the run, then replayed | `test_slice6_step4::test_a_row_the_run_wrote_is_format_2_and_replays` | PASS |
| `0fae42c` | a HIGH task shared by two candidates: `match_id` null, understood in `GET /tasks` | `test_slice6_step5::test_a_high_task_shared_by_two_offers_names_no_match_and_is_understood` | PASS |
| `0fae42c` | a HIGH task shared by two candidates: `match_id` null, understood in `GET /tasks` | `test_slice6_step5::test_a_high_task_shared_by_two_properties_names_only_the_request` | PASS |

## 4. Concurrency

| Race | Test | Status |
|---|---|---|
| two runs raising one subject's work | `test_slice6_step4::test_g6_4_concurrent_runs_raise_one_task_and_staff_see_a_self_contained_task` | PASS |
| two runs raising one subject's work | `test_migration_0007_task_work_and_evidence::test_two_concurrent_runs_raise_one_task` | PASS |
| two completions of one task | `test_slice6_step2::test_a_second_concurrent_completion_waits_and_is_refused` | PASS |

## 5. Two stated limits (never PASS)

**5.1 The replay does not recompute the diagnostic's own `input_hash`** (review of `0fae42c`; plan §5.4). The replay of G6-11 verifies the matches it names (R) and recomputes the decisions (D). It does not recompute the diagnostic row's `input_hash` (`turab.diagnostic-input/2`), nor compare it with the stored value. **A replay of `{"R": [], "D": []}` is not a proof that every input of that hash is sound.** Measured, as a limit:

- `test_slice6_step5::test_limit_the_replay_does_not_read_the_diagnostics_own_input_hash` measured (LIMIT)

**5.2 `explain.blocker_summary` is not pinned** (review of `922a100`; plan §5.4). `by_reason`, `candidates_evaluated` and the summary's base come from Slice 4's format-1 builder. Computed from `src/turab/matching/rule_pins.py`: the pins of step 3 (`diagnostic.value@1`, `diagnostic.actions@1`, `diagnostic.relaxation@1`) are present; a pin naming `blocker_summary`: none. The three pins do not cover it. A change of its output makes an old row fail (D), loudly; that failure is **not** a proof that the old row can be replayed. Before any later change of it that affects the summary: keep the historical computation (or a version of it), and test the replay of an old row and of a new row.

## 6. Findings decided in the review of `3657973`

| Finding | Decision | Held by | Test | Status |
|---|---|---|---|---|
| F6-21 | documentary correction: §3.4 and §6.2's D02 bind what Slice 6 generates (the diagnostic, its tasks, their audit), not every output of the run; Slice 4 §3.5 keeps the expectation in the staff match's snapshot, and `API_CONTRACTS_v0.2.md` §8 forbids its serialization to public and customer DTOs | the boundary's witness | `test_slice6_step5::test_f6_21_the_staff_match_keeps_the_expectation_the_boundary_witness` | PASS |
| F6-21 | documentary correction: §3.4 and §6.2's D02 bind what Slice 6 generates (the diagnostic, its tasks, their audit), not every output of the run; Slice 4 §3.5 keeps the expectation in the staff match's snapshot, and `API_CONTRACTS_v0.2.md` §8 forbids its serialization to public and customer DTOs | the boundary's witness | `test_slice6_step5::test_d02_the_expectation_reaches_no_diagnostic_task_or_slice_6_audit` | PASS |
| F6-22 | the title by type and subject entity: CONFIRM_PRICE on the REQUEST is "Confirm the request's maximum budget"; on a PROPERTY_OFFER the offer's title stays; a row stored before keeps its old title, also after DONE (no path updates one); work raised again later is a new task, with the corrected title | fixed (`matching_run.py`) | `test_slice6_step5::test_f6_22_the_request_tasks_title_names_the_request` | PASS |
| F6-22 | the title by type and subject entity: CONFIRM_PRICE on the REQUEST is "Confirm the request's maximum budget"; on a PROPERTY_OFFER the offer's title stays; a row stored before keeps its old title, also after DONE (no path updates one); work raised again later is a new task, with the corrected title | fixed (`matching_run.py`) | `test_slice6_step5::test_f6_22_an_offer_subject_keeps_the_offers_title` | PASS |
| F6-22 | the title by type and subject entity: CONFIRM_PRICE on the REQUEST is "Confirm the request's maximum budget"; on a PROPERTY_OFFER the offer's title stays; a row stored before keeps its old title, also after DONE (no path updates one); work raised again later is a new task, with the corrected title | fixed (`matching_run.py`) | `test_slice6_step5::test_f6_22_an_old_title_stays_after_done_and_new_work_gets_the_corrected_title` | PASS |
| F6-22 | the title by type and subject entity: CONFIRM_PRICE on the REQUEST is "Confirm the request's maximum budget"; on a PROPERTY_OFFER the offer's title stays; a row stored before keeps its old title, also after DONE (no path updates one); work raised again later is a new task, with the corrected title | fixed (`matching_run.py`) | `test_slice6_step5::test_a_high_task_shared_by_two_properties_names_only_the_request` | PASS |

- **F6-22, computed from the tree:** `matching_run.py` fixes `("CONFIRM_PRICE", "REQUEST")` → "Confirm the request's maximum budget".
- **F6-22, the tasks stored with the old title before the fix** (`docs/gate/evidence/SLICE6-STEP5-F6-22-STORED-TITLES.txt`): `CONFIRM_PRICE | REQUEST | Confirm the offer's price terms | OPEN | 2`. Test data of the suite's database, dropped at its next session; no path updates a title, so such a row keeps its old title, also after it is DONE; a later run that raises the work again creates a new row with the corrected title (`test_f6_22_an_old_title_stays_after_done_and_new_work_gets_the_corrected_title`).

## 7. The writes, computed from the tree (plan §7)

**Condition 10, the writes to `tasks` by kind:**

| Kind | Decided | Found | |
|---|---|---|---|
| INSERT | `src/turab/services/identity.py`, `src/turab/services/match_review.py`, `src/turab/services/matching_run.py` | `src/turab/services/identity.py`, `src/turab/services/match_review.py`, `src/turab/services/matching_run.py` | as decided |
| UPDATE | `src/turab/services/tasks.py` | `src/turab/services/tasks.py` | as decided |
| DELETE | none | none | as decided |

- The completion's one UPDATE sets: `status = 'DONE', completed_at = :at` (as decided). `tasks.py` is in the inventory.

**Condition 4 and the completion's events:**

| Kind | Table | Decided | Found |
|---|---|---|---|
| INSERT | `match_diagnostic_runs` | `src/turab/services/matching_run.py` | `src/turab/services/matching_run.py` |
| UPDATE | `match_diagnostic_runs` | none | none |
| DELETE | `match_diagnostic_runs` | none | none |
| INSERT | `task_completion_events` | `src/turab/services/tasks.py` | `src/turab/services/tasks.py` |
| UPDATE | `task_completion_events` | none | none |
| DELETE | `task_completion_events` | none | none |

**Condition 2 (§3.1, I03).** Files writing `requests` or `request_criteria`: `src/turab/services/requests.py`. Of the Slice 6 modules: none.

**The operations.** `getTasks` routed, `postTasksTaskIdComplete` routed.

## 8. Carried, unchanged

- **OQ6-1** (a CHECK on the diagnostic payload) and **OQ6-2** (an index on `task_completion_events.evidence_observation_id`) stay **open**; neither is a licence to change the schema. OQ6-1's obligation is proven by test (§3).
- **K06 UNPROVEN** (§2). **G4-5R open:** the proof's scope is SALE only.
- The remaining conditions are argued in `docs/gate/SLICE_6_STEP5_DELIVERY.md`, which this document does not replace.
