# Slice 7 — closure evidence

**Generated** by `db/gate/slice7_evidence.py` from `docs/gate/evidence/junit-run.xml`. **Do not edit.**

> Slice 7, Communication / WhatsApp Record (plan §6.4, G7-19). **Not a STOP GATE.** **R-1 is UNMET: no real event may be received.** **K06 UNPROVEN.** **SALE only.** The limits of §6 are never PASS.

- The JUnit run is recorded at commit `50ad5c2c882cc62b40496d91d14d09cecefdc29e`, source fingerprint `7cd994f16f0ec9a81f7d1d7312adc330178fde416941aa521740b166d8310762`, report sha256 `df600574ae6189f3eb3865932a4097d882246c1bfff1cd4bc846dcc2b325e401`, test database `turab_authz_test` on host `127.0.0.1`, destination `host=127.0.0.1 hostaddr=- port=5432 dbname=turab_authz_test`, server reached `system_identifier=7697828029857667607 address=127.0.0.1 port=5432 database=turab_authz_test` (`docs/gate/evidence/TEST-RUN-PROVENANCE.txt`).
- Counted in the report: 3173 test cases, 0 failures, 0 errors, 0 skipped (none is required).
- Binding (`db/gate/run_binding.py`): the report's digest and counts are the recorded ones, and the current tree's source fingerprint is the run's and the gate run's.
- Tests are named `module::name`.
- These are our runs; nobody else has re-run them.

## 1. The four mandatory tests (plan §6.1)

The end-to-end tests (`test_slice7_step5`) are listed first; the earlier steps' tests follow. **What goes over HTTP:** the operations each test proves (the two staff commands, the webhook, the observation command, the timeline), and the run and the review that make the SALE opportunity. **What does not:** the rows they start from are set up directly in SQL: the fixture accounts and parties `tests/conftest.py` loads; and, through the helpers of `tests/test_slice7_step2.py`, `_party` (a party), `_archive_consent` (a consent grant and its thread binding) and `_sale_world` (the request, its criterion, the property with its attributes, and the offer, by `tests/test_slice4_step7.py`'s helpers). SQL also reads the results, and probes the schema's own refusals (`0008`), which no HTTP path reaches.

| # | Handoff wording | Test | Status |
|---|---|---|---|
| 1 | repeated provider webhook creates one message | `test_slice7_step5::test_mandatory_1_the_same_envelope_twice_makes_one_event_one_message_one_interaction` | PASS |
| 1 | repeated provider webhook creates one message | `test_slice7_step5::test_mandatory_1_concurrent_deliveries_make_one_event_one_message_one_interaction` | PASS |
| 1 | repeated provider webhook creates one message | `test_slice7_step5::test_mandatory_1_a_failed_event_is_completed_by_the_redelivery_once` | PASS |
| 1 | repeated provider webhook creates one message | `test_slice7_step3::test_mandatory_test_1_concurrent_deliveries_make_one_message` | PASS |
| 1 | repeated provider webhook creates one message | `test_slice7_step4::test_iv_a_webhook_replay_and_an_ignored_event_write_no_interaction` | PASS |
| 2 | same provider message id cannot be inserted into another thread | `test_slice7_step5::test_mandatory_2_staff_first_then_the_webhook_into_another_thread_writes_nothing` | PASS |
| 2 | same provider message id cannot be inserted into another thread | `test_slice7_step5::test_mandatory_2_the_webhook_first_then_staff_into_another_thread_is_409` | PASS |
| 2 | same provider message id cannot be inserted into another thread | `test_slice7_step5::test_mandatory_2_the_null_provider_path_is_refused_by_the_service_and_by_0008` | PASS |
| 2 | same provider message id cannot be inserted into another thread | `test_slice7_step2::test_g7_4_a_recorded_reference_is_409_in_any_thread` | PASS |
| 2 | same provider message id cannot be inserted into another thread | `test_slice7_step3::test_g7_4_mandatory_test_2_a_recorded_reference_is_ignored_in_any_thread` | PASS |
| 2 | same provider message id cannot be inserted into another thread | `test_migration_0008_communication_records::test_a_a_reference_needs_a_provider` | PASS |
| 2 | same provider message id cannot be inserted into another thread | `test_migration_0008_communication_records::test_a_the_global_identity_still_holds_across_threads` | PASS |
| 3 | thread/opportunity links are checked by service invariant | `test_slice7_step5::test_mandatory_3_the_sellers_thread_about_the_buyers_opportunity_is_accepted_and_frozen` | PASS |
| 3 | thread/opportunity links are checked by service invariant | `test_slice7_step2::test_rule_0_a_named_opportunity_must_be_a_sale` | PASS |
| 3 | thread/opportunity links are checked by service invariant | `test_slice7_step2::test_rule_1_the_opportunitys_buyer_and_seller_are_accepted_with_its_own_links` | PASS |
| 3 | thread/opportunity links are checked by service invariant | `test_slice7_step2::test_rule_1_a_link_the_opportunity_does_not_have_is_refused` | PASS |
| 3 | thread/opportunity links are checked by service invariant | `test_slice7_step2::test_rule_2_a_request_without_an_opportunity_needs_its_own_party` | PASS |
| 3 | thread/opportunity links are checked by service invariant | `test_slice7_step2::test_rule_3_a_property_without_an_opportunity_needs_one_of_its_offers_party` | PASS |
| 3 | thread/opportunity links are checked by service invariant | `test_slice7_step2::test_rule_4_an_id_naming_no_row_is_refused_by_field` | PASS |
| 3 | thread/opportunity links are checked by service invariant | `test_slice7_step2::test_the_links_are_frozen_after_creation` | PASS |
| 3 | thread/opportunity links are checked by service invariant | `test_migration_0008_communication_records::test_d_a_named_parent_cannot_be_deleted` | PASS |
| 4 | phone decision can be linked to later written confirmation observation | `test_slice7_step5::test_mandatory_4_over_http_the_decision_the_confirmation_the_link_and_the_timeline` | PASS |
| 4 | phone decision can be linked to later written confirmation observation | `test_slice7_step4::test_vii_mandatory_test_4_a_phone_decision_is_linked_to_a_later_written_confirmation` | PASS |

## 2. Red-team cases (plan §6.2)

| Case | Statement | Test | Status |
|---|---|---|---|
| J01 | mandatory test 1 | `test_slice7_step5::test_mandatory_1_concurrent_deliveries_make_one_event_one_message_one_interaction` | PASS |
| J02 | mandatory test 2 | `test_slice7_step5::test_mandatory_2_staff_first_then_the_webhook_into_another_thread_writes_nothing` | PASS |
| J02 | mandatory test 2 | `test_slice7_step5::test_mandatory_2_the_webhook_first_then_staff_into_another_thread_is_409` | PASS |
| J03 | no content stored without a consent valid at write time, in messages, in the event store and in logs; retention not claimed | `test_slice7_step5::test_j03_content_reaches_the_timeline_only_under_the_consent` | PASS |
| J03 | no content stored without a consent valid at write time, in messages, in the event store and in logs; retention not claimed | `test_slice7_step3::test_g7_9_1_the_event_store_holds_the_allow_list_only` | PASS |
| J03 | no content stored without a consent valid at write time, in messages, in the event store and in logs; retention not claimed | `test_slice7_step3::test_j03_nothing_of_the_body_reaches_a_log_or_an_access_record` | PASS |
| J03 | no content stored without a consent valid at write time, in messages, in the event store and in logs; retention not claimed | `test_slice7_step2::test_g7_9_content_without_the_archive_consent_is_refused` | PASS |
| J03 | no content stored without a consent valid at write time, in messages, in the event store and in logs; retention not claimed | `test_slice7_step2::test_g7_11_the_content_never_reaches_the_audit_log_or_a_log` | PASS |
| J03 | no content stored without a consent valid at write time, in messages, in the event store and in logs; retention not claimed | `test_slice7_step4::test_vi_webhook_content_withheld_at_write_is_absent_for_every_role` | PASS |
| S41 | a wrong or missing relay signature is 401 before any write; it proves the relay's origin, not Meta's | `test_slice7_step5::test_s41_an_unsigned_or_missigned_delivery_writes_nothing` | PASS |
| S41 | a wrong or missing relay signature is 401 before any write; it proves the relay's origin, not Meta's | `test_slice7_step3::test_ii_s41_a_missing_or_wrong_signature_is_401_writing_nothing` | PASS |
| S42 | a replay of a completed event is 200, with no duplicate | `test_slice7_step5::test_mandatory_1_the_same_envelope_twice_makes_one_event_one_message_one_interaction` | PASS |
| S42 | a replay of a completed event is 200, with no duplicate | `test_slice7_step3::test_s42_a_replay_of_a_completed_event_is_200_and_writes_nothing` | PASS |
| G7-2 (iv) | the four failure tests, and the answers whose result is not confirmed | `test_slice7_step3::test_iv_1_a_failure_in_processing_is_failed_with_its_code_and_answers_500` | PASS |
| G7-2 (iv) | the four failure tests, and the answers whose result is not confirmed | `test_slice7_step3::test_iv_2_a_stop_after_t1_is_completed_by_a_redelivery` | PASS |
| G7-2 (iv) | the four failure tests, and the answers whose result is not confirmed | `test_slice7_step3::test_iv_3_a_failure_of_the_status_update_loses_t2_whole` | PASS |
| G7-2 (iv) | the four failure tests, and the answers whose result is not confirmed | `test_slice7_step3::test_iv_4_a_replay_while_t2_holds_the_claim_is_200_and_writes_nothing` | PASS |
| G7-2 (iv) | the four failure tests, and the answers whose result is not confirmed | `test_slice7_step3::test_iv_t1_failing_before_its_commit_is_503_then_a_redelivery_completes_it` | PASS |
| G7-2 (iv) | the four failure tests, and the answers whose result is not confirmed | `test_slice7_step3::test_iv_t1_whose_commit_answer_is_lost_is_503_then_a_redelivery_completes_it_once` | PASS |
| G7-2 (iv) | the four failure tests, and the answers whose result is not confirmed | `test_slice7_step3::test_iv_t2_whose_commit_answer_is_lost_is_500_then_a_redelivery_is_a_replay` | PASS |
| K05 | each staff POST replays with its key; another body on the key is 409 | `test_slice7_step5::test_k05_the_thread_command_replays_and_refuses_another_body_on_its_key` | PASS |
| K05 | each staff POST replays with its key; another body on the key is 409 | `test_slice7_step5::test_k05_the_message_command_replays_and_refuses_another_body_on_its_key` | PASS |

**K06 — UNPROVEN.** The application role is a superuser and owns every table (EN-02). The refusals below are trigger- and constraint-level, and are never counted as K06:

- `test_migration_0008_communication_records::test_d_a_thread_never_changes_after_insert` passes (trigger-level)
- `test_migration_0008_communication_records::test_d_a_thread_cannot_be_deleted` passes (trigger-level)
- `test_migration_0008_communication_records::test_d_the_six_keys_are_restrict` passes (trigger-level)
- `test_migration_0008_communication_records::test_b_a_message_cannot_be_deleted` passes (trigger-level)
- `test_migration_0008_communication_records::test_b_delivery_status_transitions_are_exactly_the_decided_ones` passes (trigger-level)
- `test_migration_0008_communication_records::test_c_an_event_cannot_be_deleted` passes (trigger-level)
- `test_migration_0008_communication_records::test_c_processing_moves_only_from_received_or_failed` passes (trigger-level)

## 3. Authorization (plan §6.3)

| Rule | Test | Status |
|---|---|---|
| the two staff POSTs: ADMIN and OPERATOR allowed; REVIEWER and CUSTOMER 403, recorded; anonymous 401 | `test_slice7_step2::test_admin_and_operator_create_a_thread_and_a_message` | PASS |
| the two staff POSTs: ADMIN and OPERATOR allowed; REVIEWER and CUSTOMER 403, recorded; anonymous 401 | `test_slice7_step2::test_a_reviewer_and_a_customer_are_refused_both_writing_nothing` | PASS |
| the two staff POSTs: ADMIN and OPERATOR allowed; REVIEWER and CUSTOMER 403, recorded; anonymous 401 | `test_slice7_step2::test_an_anonymous_caller_is_refused_both` | PASS |
| the two staff POSTs: ADMIN and OPERATOR allowed; REVIEWER and CUSTOMER 403, recorded; anonymous 401 | `test_slice7_step2::test_an_unknown_thread_is_403_and_the_denial_is_recorded` | PASS |
| the webhook stays in the closed list of six, and reads no bearer | `test_slice7_step3::test_the_webhook_stays_in_the_closed_public_list_and_reads_no_bearer` | PASS |
| the timeline's widened item, by exact key sets, for ADMIN, OPERATOR and REVIEWER | `test_slice7_step4::test_vi_an_unarchived_message_shows_no_content_to_any_role` | PASS |
| the timeline's widened item, by exact key sets, for ADMIN, OPERATOR and REVIEWER | `test_slice7_step4::test_vi_archived_content_is_shown_to_every_role` | PASS |
| the timeline's widened item, by exact key sets, for ADMIN, OPERATOR and REVIEWER | `test_slice7_step4::test_vi_any_other_interaction_keeps_slice_1s_exact_keys` | PASS |

## 4. What the reviews of Slice 7 asked to be proven

| Review | Obligation | Test | Status |
|---|---|---|---|
| `0f423d2` | G7-16 (iv): the thread locked before the insert, two concurrent messages; no refusal carries an id or database text | `test_slice7_step2::test_iv_two_concurrent_messages_serialize_on_the_thread_and_keep_the_later` | PASS |
| `0f423d2` | G7-16 (iv): the thread locked before the insert, two concurrent messages; no refusal carries an id or database text | `test_slice7_step2::test_no_refusal_carries_an_id_or_database_text` | PASS |
| `f7e5297` | R-S7-2-01: a binding in flight and a message, both orders, over HTTP | `test_slice7_step2::test_r_s7_2_01_a_message_holding_the_thread_makes_a_new_binding_wait` | PASS |
| `f7e5297` | R-S7-2-01: a binding in flight and a message, both orders, over HTTP | `test_slice7_step2::test_r_s7_2_01_a_binding_in_flight_makes_the_message_wait_then_is_seen` | PASS |
| `bf1fe3d` | a 503 when the secret is absent, with no event row | `test_slice7_step3::test_ii_a_missing_or_empty_secret_is_503_with_no_event_row` | PASS |
| `3dfb717` | T1 failing before its commit, T1's and T2's answers lost after it; `archived_at` read and tested | `test_slice7_step3::test_iv_t1_failing_before_its_commit_is_503_then_a_redelivery_completes_it` | PASS |
| `3dfb717` | T1 failing before its commit, T1's and T2's answers lost after it; `archived_at` read and tested | `test_slice7_step3::test_iv_t1_whose_commit_answer_is_lost_is_503_then_a_redelivery_completes_it_once` | PASS |
| `3dfb717` | T1 failing before its commit, T1's and T2's answers lost after it; `archived_at` read and tested | `test_slice7_step3::test_iv_t2_whose_commit_answer_is_lost_is_500_then_a_redelivery_is_a_replay` | PASS |
| `3dfb717` | T1 failing before its commit, T1's and T2's answers lost after it; `archived_at` read and tested | `test_slice7_step3::test_archived_at_alone_refuses_nothing` | PASS |
| `34d6122` | a Content-Length too long for int(): 400 unread, writing nothing; long leading zeros not refused | `test_slice7_step3::test_g7_15_the_declared_length_is_compared_without_an_unbounded_conversion` | PASS |
| `34d6122` | a Content-Length too long for int(): 400 unread, writing nothing; long leading zeros not refused | `test_slice7_step3::test_g7_15_an_overlong_declared_length_is_400_unread_and_writes_nothing` | PASS |
| `34d6122` | a Content-Length too long for int(): 400 unread, writing nothing; long leading zeros not refused | `test_slice7_step3::test_g7_15_a_small_body_under_an_odd_declared_length_is_processed` | PASS |
| `e18271a` | the item's exact keys and the withholding for the three roles; the link's refusals before any write or key; the backfill concurrent and re-run | `test_slice7_step4::test_vi_an_unarchived_message_shows_no_content_to_any_role` | PASS |
| `e18271a` | the item's exact keys and the withholding for the three roles; the link's refusals before any write or key; the backfill concurrent and re-run | `test_slice7_step4::test_vii_a_links_metadata_must_be_exactly_its_two_uuids` | PASS |
| `e18271a` | the item's exact keys and the withholding for the three roles; the link's refusals before any write or key; the backfill concurrent and re-run | `test_slice7_step4::test_vii_the_observation_must_be_linkable` | PASS |
| `e18271a` | the item's exact keys and the withholding for the three roles; the link's refusals before any write or key; the backfill concurrent and re-run | `test_slice7_step4::test_v_two_backfills_at_once_write_each_interaction_once` | PASS |
| `e18271a` | the item's exact keys and the withholding for the three roles; the link's refusals before any write or key; the backfill concurrent and re-run | `test_slice7_step4::test_v_the_backfill_writes_one_interaction_per_earlier_message_and_a_rerun_none` | PASS |
| `a659587` | R-S7-4-01: the backfill's actual level, on a REPEATABLE READ connection; the concurrent pair and the re-run; the refusal | `test_slice7_step4::test_v_the_backfill_runs_read_committed_whatever_the_connections_default` | PASS |
| `a659587` | R-S7-4-01: the backfill's actual level, on a REPEATABLE READ connection; the concurrent pair and the re-run; the refusal | `test_slice7_step4::test_v_two_backfills_on_a_repeatable_read_default_write_each_interaction_once` | PASS |
| `a659587` | R-S7-4-01: the backfill's actual level, on a REPEATABLE READ connection; the concurrent pair and the re-run; the refusal | `test_slice7_step4::test_v_the_backfill_refuses_to_write_under_another_level` | PASS |
| `d04d5c8` | the two gaps: mandatory test 1's interaction; K05's other body | `test_slice7_step5::test_mandatory_1_concurrent_deliveries_make_one_event_one_message_one_interaction` | PASS |
| `d04d5c8` | the two gaps: mandatory test 1's interaction; K05's other body | `test_slice7_step5::test_k05_the_thread_command_replays_and_refuses_another_body_on_its_key` | PASS |
| `d04d5c8` | the two gaps: mandatory test 1's interaction; K05's other body | `test_slice7_step5::test_k05_the_message_command_replays_and_refuses_another_body_on_its_key` | PASS |

**Concurrency:**

| Race | Test | Status |
|---|---|---|
| two threads with one WHATSAPP reference | `test_migration_0008_communication_records::test_e_two_concurrent_threads_with_one_reference_make_one` | PASS |
| two messages on one thread | `test_slice7_step2::test_iv_two_concurrent_messages_serialize_on_the_thread_and_keep_the_later` | PASS |
| a revocation in flight | `test_slice7_step2::test_g7_9_a_revocation_in_flight_is_waited_for_then_seen` | PASS |
| a webhook holding the thread, and a new binding | `test_slice7_step3::test_g7_16_iv_a_webhook_holding_the_thread_makes_a_new_binding_wait` | PASS |
| a status change in flight | `test_slice7_step3::test_g7_5_a_status_change_in_flight_is_waited_for_then_seen` | PASS |
| a replay during the claim | `test_slice7_step3::test_iv_4_a_replay_while_t2_holds_the_claim_is_200_and_writes_nothing` | PASS |
| eight deliveries of one envelope | `test_slice7_step5::test_mandatory_1_concurrent_deliveries_make_one_event_one_message_one_interaction` | PASS |
| two backfills; a backfill and a message | `test_slice7_step4::test_v_two_backfills_on_a_repeatable_read_default_write_each_interaction_once` | PASS |
| two backfills; a backfill and a message | `test_slice7_step4::test_v_a_backfill_concurrent_with_a_message_makes_no_duplicate` | PASS |
| an observation changed while a link reads it | `test_slice7_step4::test_vii_a_change_to_the_observation_in_flight_is_waited_for_then_seen` | PASS |

## 5. The writes to the four tables, computed from the tree (plan §7 (9), G7-19 (ii))

An inventory of the application's statements under `src/`, read by this generator. **It is not a guarantee against a superuser's writes** (K06).

| Table | Kind | Decided | Found | |
|---|---|---|---|---|
| `communication_threads` | INSERT | `src/turab/services/communication.py` | `src/turab/services/communication.py` | as decided |
| `communication_threads` | UPDATE | `src/turab/services/communication.py`, `src/turab/services/webhooks.py` | `src/turab/services/communication.py`, `src/turab/services/webhooks.py` | as decided |
| `communication_threads` | DELETE | none | none | as decided |
| `communication_messages` | INSERT | `src/turab/services/communication.py`, `src/turab/services/webhooks.py` | `src/turab/services/communication.py`, `src/turab/services/webhooks.py` | as decided |
| `communication_messages` | UPDATE | `src/turab/services/webhooks.py` | `src/turab/services/webhooks.py` | as decided |
| `communication_messages` | DELETE | none | none | as decided |
| `webhook_events` | INSERT | `src/turab/services/webhooks.py` | `src/turab/services/webhooks.py` | as decided |
| `webhook_events` | UPDATE | `src/turab/services/webhooks.py` | `src/turab/services/webhooks.py` | as decided |
| `webhook_events` | DELETE | none | none | as decided |
| `interactions` | INSERT | `src/turab/services/message_interactions.py`, `src/turab/services/opportunity_commands.py` | `src/turab/services/message_interactions.py`, `src/turab/services/opportunity_commands.py` | as decided |
| `interactions` | UPDATE | none | none | as decided |
| `interactions` | DELETE | none | none | as decided |

**The columns each UPDATE sets:**

| Table | Decided | Found |
|---|---|---|
| `communication_threads` | `last_message_at` | `last_message_at` |
| `communication_messages` | `delivery_status` | `delivery_status` |
| `webhook_events` | `error_text`, `processed_at`, `processing_status` | `error_text`, `processed_at`, `processing_status` |

**The module that holds the INSERT, and who calls it** (`interactions`):

- `message_interactions.write` (its INSERT in `src/turab/services/message_interactions.py`) is called by: `src/turab/services/communication.py`, `src/turab/services/webhooks.py`.
- `message_interactions.backfill` (its INSERT in `src/turab/services/message_interactions.py`) is called by: `db/ops/backfill_message_interactions.py`.
- `src/turab/services/opportunity_commands.py` holds Slice 5's INSERT (share, close, revalidate with a note).
- The operator scripts under `db/ops/` hold no statement on the four tables: none found.

## 6. The event store: a sample measured right after the run (G7-19 (i))

- **Sampled at** 2026-10-28 16:45:12 UTC, from the test database `turab_authz_test` on host `127.0.0.1` (destination `host=127.0.0.1 hostaddr=- port=5432 dbname=turab_authz_test`; server reached `system_identifier=7697828029857667607 address=127.0.0.1 port=5432 database=turab_authz_test`), the ones the run's record names, for the run recorded at 2026-10-28 16:31:48 UTC (commit `50ad5c2c882cc62b40496d91d14d09cecefdc29e`, source fingerprint `7cd994f16f0ec9a81f7d1d7312adc330178fde416941aa521740b166d8310762`, report sha256 `df600574ae6189f3eb3865932a4097d882246c1bfff1cd4bc846dcc2b325e401`), from `docs/gate/evidence/SLICE7-EVENT-STORE-COUNTS.txt`.

| `processing_status` | Count |
|---|---|
| RECEIVED | 1 |
| PROCESSED | 74 |
| IGNORED | 26 |
| FAILED | 0 |

FAILED, by `error_text`: none.

- **What this is, and is not:** a sample from the run's test database, taken after the run; not the state at the moment of the last test, and **never a PASS**. They are the suite's test events. **No reception of a real event, and no proof of Meta's path, is claimed.**

## 7. Limits (never PASS, G7-19 (iii))

- **R-1 UNMET.** The relay is not built, and its seven duties are untested (G7-2 (ii), (a2) decided). **The relay's signature proves the relay's origin, not Meta's**: Meta's verification is never counted as done in this slice. No reception of a real event is claimed.
- **K06 UNPROVEN** (EN-02): §2's refusals are trigger- and constraint-level.
- **Retention is not claimed** (OQ7-1): content archived under a consent stays after its revocation.

- **the content-less recovery (G7-2 (v), accepted in the review of `58a0067`): the operator command recovers a message without its content.** `test_slice7_step3::test_iv_2_a_stop_after_t1_is_completed_by_the_recovery_without_content` measured (LIMIT)
- **a confirmation link is valid at its writing only (G7-18 (vii)): the observation it names can still change afterwards; no legal value.** `test_slice7_step4::test_vii_the_link_is_valid_at_its_writing_only` measured (LIMIT)
- **one interaction per message within the service's paths (G7-18 (iv)): not a database constraint; a row written outside the service has none.** `test_slice7_step4::test_ix_no_message_has_two_interactions_and_each_names_an_existing_message` measured (LIMIT)
- **Slice 6's carried limits:** SALE only (G4-5R open); K06; and its two stated limits (§5 of `docs/gate/SLICE_6_EVIDENCE.md`), named here, not re-measured.
- **Slice 5's and Slice 6's evidence** (`SLICE_5_STOP_GATE_E.md`, `SLICE_6_EVIDENCE.md`) stay their trees' records; this generator reads neither.

## 8. The contract's corrections (plan §7 (1)) and the operations

- **CORRECTION-006:** approved 2026-10-25.
- **CORRECTION-007:** approved 2026-10-27.
- **CORRECTION-008:** approved 2026-10-27.
- **The operations:** `postCommunicationThreads` routed, `postCommunicationThreadsThreadIdMessages` routed, `postWebhooksWhatsapp` routed, `getPartiesPartyIdTimeline` routed.
- The remaining conditions are argued in the steps' delivery notes, which this document does not replace.
