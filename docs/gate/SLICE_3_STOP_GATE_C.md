# Slice 3 — STOP GATE C evidence

**Generated** by `db/gate/stop_gate_c_evidence.py` from `docs/gate/evidence/junit-run.xml`. **Do not edit.**

- The JUnit run is recorded at commit `0c97a6b30f07f94d24afc039debce9cb4d589bff`, source fingerprint `4aa193ccde1d416b0e8a9bc946ae8a64ea73b02996a29507c3d65ce9dca34e50`, report sha256 `6abeee1242268ece07b738b4f25bb324eec7f65de0f26949da743b987662f33a` (`docs/gate/evidence/TEST-RUN-PROVENANCE.txt`).
- Counted in the report: 1284 test cases, 0 failures, 0 errors, 0 skipped.
- Binding (`db/gate/run_binding.py`): the report's digest and counts are the recorded ones, and the current tree's source fingerprint is the run's and the gate run's.
- These are our runs; nobody else has re-run them.

## 1. The six questions (plan §6)

| Question | Planned test | Status |
|---|---|---|
| What is the physical property? | `test_a_property_is_created_with_its_type_location_and_supply_mode` | PASS |
| What is the physical property? | `test_property_attributes_are_unique_per_definition` | PASS |
| What offers exist for it? | `test_owner_sale_broker_sale_and_rent_coexist_on_one_property` | PASS |
| What offers exist for it? | `test_listing_a_property_returns_all_of_its_offers` | **NOT WRITTEN** (see below) |
| Who supplied each fact? | `test_a_claim_must_carry_at_least_one_origin` | PASS |
| Who supplied each fact? | `test_a_source_is_created_only_through_an_external_lead` | PASS |
| Who supplied each fact? | `test_converting_a_lead_records_its_party_and_consent` | **NOT WRITTEN** (see below) |
| What is current and what is historical? | `test_only_one_resolved_value_is_current_per_attribute` | PASS |
| What is current and what is historical? | `test_superseding_closes_the_previous_row_in_the_same_transaction` | PASS |
| What is current and what is historical? | `test_a_stale_offer_is_reported_stale_on_its_commercial_terms_clock` | PASS |
| What is declared and what is checked? | `test_a_claim_is_born_declared` | PASS |
| What is declared and what is checked? | `test_only_a_confirmed_verification_event_raises_the_level` | PASS |
| What is declared and what is checked? | `test_a_non_confirmed_outcome_records_the_event_and_changes_nothing` | PASS |
| Canonical or alias? | `test_confirmed_same_writes_the_alias_before_the_status` | PASS |
| Canonical or alias? | `test_the_canonical_resolver_returns_the_canonical_for_an_alias` | PASS |
| Canonical or alias? | `test_confirming_same_raises_review_work_for_affected_open_records` | PASS |

**Documented exceptions.**

- **`test_listing_a_property_returns_all_of_its_offers`**: Finding G3-16: the frozen contract declares no operation that lists a property's offers (`/properties/{property_id}/offers` has only POST). Offers are read one by one (`GET /offers/{id}`), and publicly only as the consented subset. Answered instead by: `test_owner_sale_broker_sale_and_rent_coexist_on_one_property` PASS, `test_only_active_consented_offers_are_projected` PASS.
- **`test_converting_a_lead_records_its_party_and_consent`**: Decision G3-10: conversion is refused with a typed 409 until the conversion schema is decided. The refusal is what can be proven. Answered instead by: `test_conversion_is_refused_with_a_typed_409_and_changes_nothing` PASS.

## 2. The seven mandatory tests (plan §6.1)

| # | Test | Evidence | Status |
|---|---|---|---|
| 1 | Owner sale, broker sale and rent coexist on one property | `test_owner_sale_broker_sale_and_rent_coexist_on_one_property` | PASS |
| 2 | Seller expectation absent from public and customer DTOs | `test_seller_expectation_never_appears_in_a_public_or_customer_payload` | PASS |
| 2 | Seller expectation absent from public and customer DTOs | `test_seller_expectation_never_appears_in_the_public_list` | PASS |
| 3 | A claim cannot be created DOCUMENT_SEEN | `test_a_claim_cannot_be_created_already_verified` | PASS |
| 4 | A verification event is required to raise the level | `test_only_a_confirmed_verification_event_raises_the_level` | PASS |
| 5 | A resolution cannot cite a foreign claim | `test_a_resolution_cannot_cite_a_claim_about_another_subject` | PASS |
| 5 | A resolution cannot cite a foreign claim | `test_a_resolution_cannot_cite_a_claim_about_another_attribute` | PASS |
| 6 | CONFIRMED_SAME without its alias fails | `test_confirmed_same_without_a_canonical_id_is_refused` | PASS |
| 6 | CONFIRMED_SAME without its alias fails | `test_the_canonical_must_be_one_of_the_candidate_pair` | PASS |
| 6 | CONFIRMED_SAME without its alias fails | `test_the_trigger_refuses_a_same_status_without_its_alias` | PASS |
| 7 | Matching inputs use canonical, not alias — NARROWED (plan §6.4): proven as a query; no matching input exists yet | `test_the_canonical_resolver_returns_the_canonical_for_an_alias` | PASS |
| 7 | Matching inputs use canonical, not alias — NARROWED (plan §6.4): proven as a query; no matching input exists yet | `test_e02_a_new_match_on_the_alias_is_refused_by_the_schema` | PASS |

## 3. RFC-001 scenarios (plan §5.1)

| # | Scenario | Test | Status |
|---|---|---|---|
| S10 | customer reads a property they created — allow | `test_s10_a_customer_reads_a_property_they_created` | PASS |
| S11 | NULL creator — deny 404 | `test_s11_a_property_whose_creator_is_null_is_denied_to_every_customer` | PASS |
| S12 | any relation_code, no claim, not creator — deny 404 | `test_s12_a_relation_alone_grants_nothing` | PASS |
| S12 e2e | a relation made through the G3-6 API — deny | `test_s12_end_to_end_a_relation_created_through_the_api_grants_nothing` | PASS |
| S13 | authorized on an alias reads the canonical — allow | `test_s13_authority_resolves_through_an_alias_to_the_canonical` | PASS |
| S14 | ASSISTED + UNCLAIMED — deny 404 | `test_s14_a_customer_cannot_read_an_assisted_unclaimed_property` | PASS |
| S15 | the same record after a claim — allow | `test_s15_the_same_record_after_a_successful_claim_is_allowed` | PASS |
| S16 | relation DECLARED, claim exists — allow | `test_s16_a_declared_unverified_relation_does_not_block_a_claimant` | PASS |
| S16a | claimed owner, relation expired — allow | `test_s16a_an_expired_relation_does_not_revoke_a_claimed_owner` | PASS |
| S16b | second account of the same party — deny 404 | `test_s16b_a_second_account_of_the_same_party_is_denied` | PASS |
| S16d | owner who claimed reads their own offer — allow | `test_s16d_an_owner_who_claimed_the_property_commands_their_own_offer` | PASS |
| S16e | the same owner, the broker's offer — deny 404 | `test_s16e_the_same_owner_cannot_command_anothers_offer_on_that_property` | PASS |
| S16f | broker reads the offer they created — allow | `test_s16f_a_creator_commands_their_offer_without_any_claim` | PASS |
| S16g | party match, no parent claim, not creator — deny 404 | `test_s16g_a_party_match_alone_grants_nothing` | PASS |
| S16h | relations row only — deny 404 | `test_s16h_a_relation_row_grants_nothing` | PASS |
| S16h e2e | a relation made through the G3-6 API opens no offer | `test_s16h_end_to_end_a_relation_opens_no_offer` | PASS |
| S16i | owner account later DISABLED — deny 401 at authentication (G3-15) | `test_s16i_an_owner_whose_account_is_later_disabled_is_denied` | PASS |
| S16j | INVITED or SUSPENDED — deny 401 at authentication (G3-15) | `test_s16j_an_invited_or_suspended_account_is_denied` | PASS |

## 4. Concurrency (plan §6.3)

| Race | Serialises on | Expected | Test | Status |
|---|---|---|---|---|
| primary source links | the parent offer row | both succeed; one primary | `test_two_concurrent_primary_source_links_leave_exactly_one_primary` | PASS |
| resolutions of one attribute | the subject row | both succeed; one CURRENT; history kept | `test_two_concurrent_resolutions_of_one_attribute_yield_one_current_value` | PASS |
| generation of one pair | the pair index (generators' FOR SHARE locks are compatible) | both succeed; one candidate | `test_generating_the_same_pair_twice_concurrently_yields_one_candidate` | PASS |
| offer transitions from one state | the offer row + `AND status = :expected` | winner and loser (declared compare-and-set) | `test_two_concurrent_offer_transitions_from_one_state_do_not_both_apply` | PASS |

## 5. Acceptance conditions (plan §7): what is computed from the tree

- **Condition 1.** The plan names 22 operations; 22 have a route.
- **Condition 6.** Files inserting into `match_candidates`: none.
- **Condition 7.** Files inserting into `record_claim_events`: ['src/turab/services/claims.py']. PROPERTY claims fail closed: `test_property_claiming_fails_closed` PASS.
- **Condition 4.** Migrations present: 0001_frozen_baseline_v0_2_3.py, 0002_request_closure_reasons.py, 0003_consent_relation_currency.py, 0004_relation_overlap_guard.py.
- **Condition 9.** `test_authorization_sql_never_reads_party_property_relations` PASS.

The remaining conditions are argued in `docs/gate/SLICE_3_STEP8_DELIVERY.md`, which this document does not replace.
