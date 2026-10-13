# Slice 5 — STOP GATE E evidence

**Generated** by `db/gate/stop_gate_e_evidence.py` from `docs/gate/evidence/junit-run.xml`. **Do not edit.**

> STOP GATE E: Slice 5, human review to opportunity (`IMPLEMENTATION_SLICES_v0.2.md`, Slice 5; plan §6.3). **Its stated limit: SALE only. G4-5R is open.**

- The JUnit run is recorded at commit `975a448642a1da918255effd82d20649bd86c32b`, source fingerprint `9e6c68cc5c12971ff8d4e188b029e3c9b65266fe0802b00bee3cf5349ba584d7`, report sha256 `8ffc2de921ca280114b54e88fd1cff045f35738d5a53e8f71c66e5245b73a7e7` (`docs/gate/evidence/TEST-RUN-PROVENANCE.txt`).
- Counted in the report: 2367 test cases, 0 failures, 0 errors, 0 skipped.
- Binding (`db/gate/run_binding.py`): the report's digest and counts are the recorded ones, and the current tree's source fingerprint is the run's and the gate run's.
- Tests are named `module::name`.
- These are our runs; nobody else has re-run them.

## 1. The proof (plan §6.3): one test, over HTTP only

| Test | Proves | HTTP commands | Transaction | Approved match | Status |
|---|---|---|---|---|---|
| `test_slice5_step6::test_stop_gate_e_a_sale_from_a_new_party_to_the_customer_view_over_http` | a seller party and its consent grant, the buyer's request and criterion (ACTIVE, confirmed), a property confirmed AVAILABLE, its SALE offer made ACTIVE and confirmed, the consent bound to the offer, the run (one ELIGIBLE match), the APPROVED review, the share, the internal read and the customer's read; then STOP GATE D's reconstruction and replay of the very match approved, with no problem | 17 | SALE | `f56888bc-ff22-4ee8-bde1-397d40c5af1c` | PASS |

Every business row of the proof is made by the API. The seed's reference data (the location, the policy, the reason codes) and the test accounts are the only rows it does not make.

## 2. The six mandatory tests (plan §6.1)

| # | Handoff wording | Test | Status |
|---|---|---|---|
| 1 | `NEED_MORE_INFORMATION → APPROVED` preserves both decisions | `test_slice5_step3::test_mandatory_1_nmi_then_approved_keeps_both_decisions` | PASS |
| 1 | `NEED_MORE_INFORMATION → APPROVED` preserves both decisions | `test_slice5_step3::test_mandatory_1_across_matches_of_one_pair` | PASS |
| 2 | approval fails if any required gate is not PASS | `test_slice5_step3::test_mandatory_2_a_gate_not_pass_is_refused_before_any_write` | PASS |
| 2 | approval fails if any required gate is not PASS | `test_slice5_step3::test_mandatory_2_the_schema_refuses_the_same_when_the_service_check_is_bypassed` | PASS |
| 3 | Opportunity cannot be created through a generic endpoint | `test_slice5_step3::test_mandatory_3_there_is_no_generic_opportunity_creation` | PASS |
| 3 | Opportunity cannot be created through a generic endpoint | `test_slice5_step3::test_the_approved_review_is_the_one_writer_of_opportunities` | PASS |
| 4 | initial offer context equals evaluated match offer when an offer exists | `test_slice5_step3::test_approved_creates_one_opportunity_with_the_decided_content` | PASS |
| 4 | initial offer context equals evaluated match offer when an offer exists | `test_slice5_step3::test_mandatory_4_the_schema_refuses_another_initial_offer` | PASS |
| 5 | customer Opportunity never reveals private seller expectation/claims | `test_slice5_step4::test_no_private_value_reaches_the_customer_at_any_scope` | PASS |
| 5 | customer Opportunity never reveals private seller expectation/claims | `test_slice5_step4::test_the_customer_body_is_the_frozen_type_at_each_scope` | PASS |
| 5 | customer Opportunity never reveals private seller expectation/claims | `test_slice5_step4::test_a_budget_decided_by_the_expectation_leaves_no_trace` | PASS |
| 5 | customer Opportunity never reveals private seller expectation/claims | `test_slice5_step4::test_a_claim_behind_the_document_changes_nothing_the_customer_sees` | PASS |
| 5 | customer Opportunity never reveals private seller expectation/claims | `test_slice5_step4::test_a_claim_behind_the_rooms_changes_nothing_the_customer_sees` | PASS |
| 5 | customer Opportunity never reveals private seller expectation/claims | `test_slice5_step4::test_free_location_text_never_reaches_the_customer` | PASS |
| 6 | same Request + same canonical Property cannot have two open Opportunities | `test_slice5_step3::test_mandatory_6_a_second_offers_match_is_refused_while_one_is_open` | PASS |
| 6 | same Request + same canonical Property cannot have two open Opportunities | `test_slice5_step3::test_mandatory_6_two_concurrent_approvals_of_one_pair_make_one_opportunity` | PASS |
| 6 | same Request + same canonical Property cannot have two open Opportunities | `test_slice5_step3::test_mandatory_6_an_open_opportunity_on_an_alias_blocks_its_canonical` | PASS |
| 6 | same Request + same canonical Property cannot have two open Opportunities | `test_slice5_step3::test_mandatory_6_a_match_on_a_property_that_is_now_an_alias_is_refused` | PASS |
| 6 | same Request + same canonical Property cannot have two open Opportunities | `test_slice5_step3::test_mandatory_6_the_index_backstop_maps_to_the_same_refusal` | PASS |
| 6 | same Request + same canonical Property cannot have two open Opportunities | `test_slice5_step5::test_mandatory_6_the_real_close_frees_the_pair` | PASS |

Tests 2 and 4 each include one schema refusal with the service check bypassed, labelled as schema in its test.

## 3. Red-team cases carried (plan §6.2)

| Case | Statement | Test | Status |
|---|---|---|---|
| B03, H05 | revoked consent after approval: the share is refused, the snapshot unchanged | `test_slice5_step5::test_b03_h05_a_share_after_a_revocation_is_refused_and_changes_nothing` | PASS |
| H01 | review history: NMI then APPROVED, both rows remain | `test_slice5_step3::test_mandatory_1_nmi_then_approved_keeps_both_decisions` | PASS |
| H02 | approval gate | `test_slice5_step3::test_mandatory_2_a_gate_not_pass_is_refused_before_any_write` | PASS |
| H03 | no general opportunity create | `test_slice5_step3::test_mandatory_3_there_is_no_generic_opportunity_creation` | PASS |
| H04 | one open opportunity per pair | `test_slice5_step3::test_mandatory_6_a_second_offers_match_is_refused_while_one_is_open` | PASS |
| E04 | identity consolidation with open opportunities surfaces work and closes nothing | `test_slice5_step6::test_e04_consolidation_with_two_real_open_opportunities_surfaces_work_and_closes_none` | PASS |
| E04 | identity consolidation with open opportunities surfaces work and closes nothing | `test_slice3_identity::test_e04_a_duplicate_open_opportunity_is_surfaced_not_closed` | PASS |
| K05 | idempotency replay of each Slice 5 POST; another body on the key is 409 | `test_slice5_step6::test_k05_each_slice_5_post_replays_and_a_changed_body_is_409` | PASS |
| K05 | idempotency replay of each Slice 5 POST; another body on the key is 409 | `test_slice5_step2::test_a_same_key_review_waiting_on_the_match_lock_is_answered_by_the_key` | PASS |

**K06 — UNPROVEN.** The application role is a superuser and owns every table (EN-02, G5-13). K06 needs a test under a role that is neither, which is G5-13 (b)(ii)'s separate step. The refusals below are trigger-level, and are never counted as K06:

- `test_migration_0006_opportunity_history::test_the_frozen_delete_guard_is_unchanged` PASS (trigger-level)
- `test_slice5_step6::test_trigger_level_a_review_row_cannot_be_changed_or_deleted` PASS (trigger-level)

## 4. RFC-001 Appendix B scenarios, on the real route

| Scenario | Statement | Test | Status |
|---|---|---|---|
| S33 | opportunity at SUMMARY_ONLY: the four property fields, no area | `test_slice5_step4::test_the_customer_body_is_the_frozen_type_at_each_scope` | PASS |
| S34 | CONTACT_AFTER_CONFIRMATION without confirmation: no contact | `test_slice5_step4::test_the_customer_body_is_the_frozen_type_at_each_scope` | PASS |
| S34 | CONTACT_AFTER_CONFIRMATION without confirmation: no contact | `test_slice5_step4::test_free_location_text_never_reaches_the_customer` | PASS |
| S36a | no internal pricing, private claim, staff note or source-private data at any scope | `test_slice5_step4::test_no_private_value_reaches_the_customer_at_any_scope` | PASS |

## 5. The limits carried to step 6, settled (review of `3a60b3b`)

| Limit | What | Settled | Test | Status |
|---|---|---|---|---|
| L-S5-3a | supersession across two policies | PROVEN: a later match under another policy supersedes nothing; under the same policy it does | `test_slice5_step6::test_l_s5_3a_a_later_match_under_another_policy_supersedes_nothing` | PASS |
| L-S5-3a | supersession across two policies | PROVEN: a later match under another policy supersedes nothing; under the same policy it does | `test_slice5_step6::test_l_s5_3a_a_later_match_under_the_same_policy_still_supersedes` | PASS |
| L-S5-3b | a run committing between the approval's supersession check and its commit | MEASURED, then CLOSED by the approval's `FOR UPDATE` on the request: a run waits for a held approval; an approval waits for a run in flight and is refused as superseded | `test_slice5_step6::test_l_s5_3b_a_run_while_an_approval_is_held_waits_for_it` | PASS |
| L-S5-3b | a run committing between the approval's supersession check and its commit | MEASURED, then CLOSED by the approval's `FOR UPDATE` on the request: a run waits for a held approval; an approval waits for a run in flight and is refused as superseded | `test_slice5_step6::test_l_s5_3b_an_approval_waits_for_a_run_in_flight_and_is_refused_superseded` | PASS |

## 6. Concurrency

| Race | Test | Status |
|---|---|---|
| two reviews of one match | `test_slice5_step2::test_a5_the_waiting_review_committed_last_is_the_latest` | PASS |
| two reviews of one match | `test_slice5_step2::test_a3_twenty_sequences_end_with_the_last_decision` | PASS |
| two approvals of one pair | `test_slice5_step3::test_mandatory_6_two_concurrent_approvals_of_one_pair_make_one_opportunity` | PASS |
| an approval and a writer of a fact | `test_slice5_step3::test_a_fact_being_changed_is_waited_for_and_read_after_its_commit` | PASS |
| a share and a consent binding (R-S5-5-01) | `test_slice5_step5::test_r_s5_5_01_a_binding_created_while_a_share_is_held_waits_for_it` | PASS |
| a share and a consent binding (R-S5-5-01) | `test_slice5_step5::test_r_s5_5_01_b_a_share_waits_for_a_binding_in_flight_and_reads_it` | PASS |
| a share and its neighbours (run, approval, share) | `test_slice5_step5::test_a_matching_run_on_the_property_waits_for_a_held_share_and_completes` | PASS |
| a share and its neighbours (run, approval, share) | `test_slice5_step5::test_an_approval_on_the_same_property_waits_for_a_held_share_and_both_succeed` | PASS |
| a share and its neighbours (run, approval, share) | `test_slice5_step5::test_two_shares_on_one_property_serialize_and_both_succeed` | PASS |
| a close and a holder of the opportunity | `test_slice5_step5::test_a_close_waits_for_a_command_holding_the_opportunity_and_reads_its_result` | PASS |
| a revalidate and a writer of the request | `test_slice5_step6::test_a_revalidate_waits_for_a_request_writer_and_reads_its_commit` | PASS |

## 7. Acceptance conditions (plan §7): what is computed from the tree

- **The operations.** The plan assigns 8 operations to Slice 5 (`postMatchesMatchIdReview`, `getBackofficeQueuesMatches`, `getOpportunitiesOpportunityId`, `getMeOpportunitiesOpportunityId`, `postOpportunitiesOpportunityIdRevalidate`, `postOpportunitiesOpportunityIdShare`, `postOpportunitiesOpportunityIdClose`, `getBackofficeQueuesOpportunities`); 8 have a route.
- **Condition 3 (H03).** A general `POST /opportunities` is not routed.
- **Conditions 3 and 4.** Files inserting into `opportunities`: ['src/turab/services/match_review.py']; into `match_reviews`: ['src/turab/services/match_review.py']; into `interactions`: ['src/turab/services/opportunity_commands.py'].
- **Condition 5.** Migrations present: 0001_frozen_baseline_v0_2_3.py, 0002_request_closure_reasons.py, 0003_consent_relation_currency.py, 0004_relation_overlap_guard.py, 0005_match_history_immutability.py, 0006_opportunity_history.py.
- **Condition 9c.** K06 is UNPROVEN (§3).
- **The limit.** SALE only: G4-5R is open, and no RENT path is claimed.

The remaining conditions are argued in `docs/gate/SLICE_5_STEP6_DELIVERY.md`, which this document does not replace.
