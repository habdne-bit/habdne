# Slice 4 — STOP GATE D evidence

**Generated** by `db/gate/stop_gate_d_evidence.py` from `docs/gate/evidence/junit-run.xml`. **Do not edit.**

> STOP GATE D: "A human reviewer must be able to read a candidate and reconstruct every eligibility decision without an LLM." (`IMPLEMENTATION_SLICES_v0.2.md`, Slice 4; plan §6.2)

- The JUnit run is recorded at commit `4446375322bc09617c3dfa2a87cc8c2d065fec0a`, source fingerprint `b72de094fc590ab6c7d3efaff8f05404167c1b0f154b3d1d90690fa37e16cba1`, report sha256 `1d9739095c36ba7eb59a2099335d82a2ab23f5312ac358404b9e10238e5eb76b` (`docs/gate/evidence/TEST-RUN-PROVENANCE.txt`).
- Counted in the report: 1945 test cases, 0 failures, 0 errors, 0 skipped.
- Binding (`db/gate/run_binding.py`): the report's digest and counts are the recorded ones, and the current tree's source fingerprint is the run's and the gate run's.
- Tests are named `module::name`.
- These are our runs; nobody else has re-run them.

## 1. The two proofs (plan §6.2)

| Proof | Test | Re-derives | Matches checked | Status |
|---|---|---|---|---|
| Reconstruction | `test_slice4_step8::test_every_stored_match_is_reconstructed_from_its_rows_alone` | from the match row and its criterion rows only: each criterion's `blocking`, the hard and information gates, the freshness and permission gates and the precedence by the versions the match names, every reason, the soft score, the next action, the three freshness states | 82 (of which 8 written by the test itself; 9 hand-made fixture rows, not engine output, excluded) | PASS |
| Replay | `test_slice4_step8::test_every_stored_match_replays_its_criterion_results_and_input_hash` | each criterion re-run by the rule version its row names on the stored snapshots; the input hash recomputed from the five stored snapshots | 90 (of which 8 written by the test itself; 9 hand-made fixture rows, not engine output, excluded) | PASS |

**Each proof can fail** (a stored decision or result altered in a copy of the rows is reported):

- `test_slice4_step8::test_reconstruction_detects_a_stored_decision_that_was_not_derived` PASS
- `test_slice4_step8::test_reconstruction_detects_a_blocking_flag_that_was_not_derived` PASS
- `test_slice4_step8::test_replay_detects_a_result_its_snapshots_do_not_give` PASS

**The replay proof's limit.** The input hash covers `REGISTRY.digest()` (G4-13), and the digest at evaluation time is not stored. Replay recomputes the hash with the CURRENT registry, the one every match in this run was evaluated under. Once a new rule version is registered, an older match's hash can no longer be recomputed from the database alone; its criterion results still replay, since each row names its own version. Raised for decision in `SLICE_4_STEP8_DELIVERY.md`.

## 2. The ten mandatory tests (plan §6.1)

| # | Handoff wording | Test | Status |
|---|---|---|---|
| 1 | BUY request cannot evaluate RENT offer | `test_slice4_step8::test_a_buy_request_never_evaluates_a_rent_offer` | PASS |
| 1 | BUY request cannot evaluate RENT offer | `test_slice4_step3::test_the_schema_refuses_a_buy_match_on_a_rent_offer` | PASS |
| 2 | Hard FAIL always blocks Opportunity | `test_slice4_step8::test_a_hard_fail_is_rejected_whatever_the_soft_score` | PASS |
| 2 | Hard FAIL always blocks Opportunity | `test_slice4_step8::test_the_schema_refuses_to_approve_a_rejected_match` | PASS |
| 3 | Required UNKNOWN → Need More Information | `test_slice4_step8::test_a_required_unknown_is_need_more_information_never_pass_or_fail` | PASS |
| 4 | `negotiable=true` above max is not automatic PASS | `test_slice4_step8::test_negotiable_above_max_is_unknown_not_pass` | PASS |
| 5 | seller expectation supports price internally, unexposed | `test_slice4_step8::test_seller_expectation_can_pass_price_and_is_never_exposed` | PASS |
| 5 | seller expectation supports price internally, unexposed | `test_slice4_step8::test_no_customer_or_public_operation_returns_a_match_or_a_diagnostic` | PASS |
| 6 | potential property without offer only with willingness context | `test_slice4_step8::test_a_potential_property_without_willingness_context_is_not_evaluated` | PASS |
| 7 | old Match replayable after request, property and offer change | `test_slice4_step8::test_an_old_match_replays_from_its_snapshots_after_everything_changed` | PASS |
| 8 | match rows are immutable | `test_slice4_step8::test_match_rows_and_their_criterion_results_cannot_change` | PASS |
| 9 | alias property cannot receive a new Match | `test_slice4_step8::test_an_alias_is_never_a_candidate` | PASS |
| 9 | alias property cannot receive a new Match | `test_slice4_step8::test_the_schema_refuses_a_match_on_an_alias` | PASS |
| 10 | no valid match is a valid result | `test_slice4_step7::test_no_candidate_is_a_valid_run` | PASS |

- **Test 2:** NARROWED: the API review is Slice 5; proven on the engine, over HTTP, and on the schema.
- **Test 6:** NARROWED (G4-9 (a)): no willingness context exists in the schema, so only the refusing half is proven.

## 3. Reference scenarios (plan §6.2)

| Scenario | Statement | Test | Status |
|---|---|---|---|
| M-01 | Required location FAIL, everything else excellent: rejected, no opportunity | `test_slice4_step8::test_m01_a_required_location_fail_rejects_whatever_else` | PASS |
| M-02 | Required document UNKNOWN: NEED_MORE_INFORMATION and its action (no task, D1) | `test_slice4_step8::test_m02_a_required_document_unknown_asks_for_the_document` | PASS |
| M-03 | Asking above max, expectation within it: PASS, expectation not shown | `test_slice4_step8::test_seller_expectation_can_pass_price_and_is_never_exposed` | PASS |
| M-04 | Negotiable only, price above max: UNKNOWN, no automatic PASS | `test_slice4_step8::test_negotiable_above_max_is_unknown_not_pass` | PASS |
| M-05 | Property stale, every criterion PASS: NEEDS_CONFIRMATION | `test_slice4_step8::test_m05_a_stale_property_with_every_criterion_passing_needs_confirmation` | PASS |
| M-06 | Request stale: NEEDS_CONFIRMATION before any opportunity | `test_slice4_step8::test_m06_a_stale_request_needs_confirmation` | PASS |
| G01 | hard fail dominates | `test_slice4_step8::test_a_hard_fail_is_rejected_whatever_the_soft_score` | PASS |
| G02 | negotiable is not automatic pass | `test_slice4_step8::test_negotiable_above_max_is_unknown_not_pass` | PASS |
| G03 | evaluated offer identity | `test_slice4_step8::test_g03_each_match_names_its_evaluated_offer_and_version` | PASS |
| G04 | immutable replay | `test_slice4_step8::test_an_old_match_replays_from_its_snapshots_after_everything_changed` | PASS |
| G05 | rule/policy lineage | `test_slice4_step8::test_g05_a_match_names_an_existing_policy_and_its_version` | PASS |
| G05 | rule/policy lineage | `test_slice4_step7::test_every_version_used_is_stored_and_no_version_1_rule_is_cited` | PASS |
| G06 | no-match is valid | `test_slice4_step7::test_no_candidate_is_a_valid_run` | PASS |
| C01 | buy/rent isolation | `test_slice4_step8::test_a_buy_request_never_evaluates_a_rent_offer` | PASS |
| C03 | required unknown | `test_slice4_step8::test_a_required_unknown_is_need_more_information_never_pass_or_fail` | PASS |
| C04 | criteria versioning | `test_slice4_step8::test_c04_changing_criteria_makes_a_new_match_and_keeps_the_old` | PASS |
| D02 | seller expectation privacy | `test_slice4_step8::test_seller_expectation_can_pass_price_and_is_never_exposed` | PASS |
| D02 | seller expectation privacy | `test_slice4_step7::test_the_explanation_never_states_the_seller_expectation` | PASS |
| B04 | private matching only (its matching half) | `test_slice4_step8::test_b04_a_private_matching_only_binding_admits_internal_matching` | PASS |
| E02 | matching aliases prohibited | `test_slice4_step8::test_an_alias_is_never_a_candidate` | PASS |
| E02 | matching aliases prohibited | `test_slice4_step8::test_the_schema_refuses_a_match_on_an_alias` | PASS |

M-12 belongs to Slice 6; M-07 to M-11 belong to other slices.

## 4. Concurrency (plan §6.3)

| Race | Serialises on | Expected | Test | Status |
|---|---|---|---|---|
| two identical runs | the frozen UNIQUE of the match | both succeed; one match; the loser reads it on a new connection | `test_slice4_step7::test_two_identical_runs_race_and_store_one_match` | PASS |
| a run while the offer's price changes | nothing: one snapshot | the match records the state it read | `test_slice4_step7::test_a_run_racing_a_price_change_stores_the_state_it_read` | PASS |
| one Idempotency-Key in two calls | the key's UNIQUE | the same body replays; another body is 409 | `test_slice4_step7::test_one_key_and_one_body_in_two_concurrent_calls_return_the_original_result` | PASS |
| one Idempotency-Key in two calls | the key's UNIQUE | the same body replays; another body is 409 | `test_slice4_step7::test_one_key_with_another_body_in_a_concurrent_call_is_409` | PASS |

## 5. Acceptance conditions (plan §7): what is computed from the tree

- **Condition 1.** The plan names 3 Slice 4 operations (`postRequestsRequestIdMatchingRun`, `getMatchesMatchId`, `getRequestsRequestIdDiagnostic`); 3 have a route.
- **Condition 4.** Migrations present: 0001_frozen_baseline_v0_2_3.py, 0002_request_closure_reasons.py, 0003_consent_relation_currency.py, 0004_relation_overlap_guard.py, 0005_match_history_immutability.py.
- **Condition 6.** Files inserting into `match_reviews`: none; into `opportunities`: none. The three match tables are written by ['src/turab/services/matching_run.py'] alone.
- **Condition 7.** matching changes no request, property, offer, consent or criterion: `test_slice4_step7::test_the_run_changes_no_request_property_offer_consent_or_criterion` PASS.
- **Condition 8.** RULE_ENGINE, no AI trace, on every row: `test_slice4_step7::test_a_run_stores_each_match_with_its_criteria_audit_and_one_diagnostic` PASS.
- **Condition 9.** no customer or public DTO carries a match field: `test_slice4_step8::test_no_customer_or_public_operation_returns_a_match_or_a_diagnostic` PASS.
- **Condition 10.** relations are not read by matching: `test_slice4_step2::test_the_matching_package_never_reads_party_property_relations` PASS.
- **Condition 11.** PROPERTY claims fail closed (G3-2 open): `test_slice2_http::test_property_claiming_fails_closed` PASS.

The remaining conditions are argued in `docs/gate/SLICE_4_STEP8_DELIVERY.md`, which this document does not replace.
