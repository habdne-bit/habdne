# TURAB — Authorization Evidence Matrix

**Generated** by `db/gate/authorization_evidence.py` from `reports/junit.xml`.
**Do not edit.** The status column is a real test result, not an assertion.

- Rules and invariants covered: **60**
- Distinct tests cited: **124**
- Suite total: **211/211** test cases passing (162 distinct test functions)

A rule whose mapping matches no test is reported **UNPROVEN** and fails the
check: an evidence matrix that can silently lose its evidence is worse than no
matrix, because it reads as assurance.

| Ref | Guarantee | Evidence | Status |
|---|---|---|---|
| `R3.1` | A null party matches nobody; explicit guard, not NULL semantics | `test_customer_with_no_party_is_refused`<br>`test_staff_account_has_no_party` | PASS |
| `R3.2` | Party, roles and status are read per request, never from the token | `test_subject_reads_party_and_roles_from_the_database` | PASS |
| `R3.3` | Mixed staff/customer roles are evaluated per operation | `test_staff_cannot_use_me_endpoints`<br>`test_customer_cannot_use_internal_endpoints` | PASS |
| `R4.11a` | Only ACTIVATED accounts carry authority | `test_non_activated_account_resolves_to_no_authority` | PASS |
| `R2.1 / INV-2` | OPERATOR+REVIEWER rejected at role-assignment time | `test_granting_reviewer_to_an_operator_is_rejected`<br>`test_granting_operator_to_a_reviewer_is_rejected`<br>`test_rejected_grant_writes_nothing` | PASS |
| `INV-2` | Existing anomalies fail closed for separation-sensitive actions | `test_separation_sensitive_actions_fail_closed`<br>`test_non_sensitive_operations_still_work_under_an_anomaly` | PASS |
| `INV-2` | The configuration anomaly is audited | `test_the_anomaly_is_audited`<br>`test_anomaly_in_existing_data_is_detected` | PASS |
| `R2.3 / decision 3` | Roles are literal; no ADMIN/REVIEWER/OPERATOR inheritance | `test_roles_are_literal_with_no_inheritance`<br>`test_invalid_role_combination_detection` | PASS |
| `§2.1 / decision 8` | Maker-checker split preserved exactly | `test_roles_are_literal_with_no_inheritance`<br>`test_separation_sensitive_operations_all_exist` | PASS |
| `R10.1 / decision 7` | Deny by default: no policy entry, no access | `test_unknown_operation_is_denied`<br>`test_empty_policy_table_denies_everything` | PASS |
| `R10.2` | Policy table equals the frozen contract, role for role | `test_policy_matches_the_frozen_contract`<br>`test_every_contract_operation_has_a_policy` | PASS |
| `R10.3a / decision 5` | getReasonCodes: ADMIN/OPERATOR/REVIEWER, not CUSTOMER | `test_reason_codes_is_the_only_role_exception`<br>`test_customer_is_refused_reason_codes_and_staff_allowed`<br>`test_customer_reason_codes_is_403_staff_is_200` | PASS |
| `R10.4` | Unauthenticated operations are a closed list of six | `test_unauthenticated_operations_are_a_closed_list_of_six` | PASS |
| `R4.1` | PROPERTY authority: creator account OR a recorded claim | `test_claim_event_grants_property_access`<br>`test_claim_grants_authority_that_did_not_exist_before` | PASS |
| `R4.2` | PROPERTY authority is account-scoped, not party-scoped | `test_property_authority_is_account_scoped_not_party_scoped` | PASS |
| `R4.3` | A NULL creator matches nobody | `test_orphan_property_with_null_creator_matches_nobody` | PASS |
| `R4.5 / decision 1` | Relations are never an authorization source | `test_relationship_alone_never_grants_property_access`<br>`test_authorization_sql_never_reads_party_property_relations`<br>`test_the_relations_check_would_catch_a_violation` | PASS |
| `R4.6` | An expired relation cannot revoke a claimed owner | `test_expired_relation_does_not_revoke_a_claimed_owner` | PASS |
| `R4.8` | REQUEST needs party match AND CLAIMED | `test_party_match_alone_is_not_enough_for_an_assisted_request`<br>`test_customer_reads_own_claimed_request` | PASS |
| `R4.9` | Aliases resolve to canonical before the authority check | `test_alias_resolves_to_canonical_before_the_authority_check` | PASS |
| `R4.10` | ASSISTED+UNCLAIMED has no authorized customer | `test_assisted_unclaimed_property_has_no_authorized_customer` | PASS |
| `§4.6 cond.1 / Q9` | Offer creator account is authorized | `test_offer_creator_is_authorized` | PASS |
| `§4.6 cond.2 / Q9` | Parent claim + party match + parent CLAIMED | `test_claimant_reads_own_offer_on_claimed_property`<br>`test_unclaimed_parent_blocks_condition_two` | PASS |
| `R4.12 / Q9` | offer.party_id alone, and relations, never grant | `test_offer_party_match_alone_never_grants`<br>`test_relations_never_grant_offer_access` | PASS |
| `R4.13 / Q9` | A property claim never opens another party's offer | `test_property_claim_does_not_open_another_partys_offer` | PASS |
| `INV-1 read` | Two distinct claimants grant authority to nobody | `test_two_distinct_claimants_grant_authority_to_nobody`<br>`test_duplicate_claim_rows_by_the_same_account_are_not_a_conflict`<br>`test_requests_conflict_the_same_way_as_properties` | PASS |
| `INV-1 audit` | CLAIM_AUTHORITY_CONFLICT is audited and surfaced | `test_conflict_is_audited_and_surfaces_as_a_conflict` | PASS |
| `INV-1 write` | Second claim rejected; same-actor replay is idempotent | `test_second_claim_by_another_account_is_rejected`<br>`test_replay_by_the_same_actor_is_idempotent`<br>`test_claiming_an_already_conflicted_resource_is_rejected` | PASS |
| `R5.3 / decision 2` | 404 conceals on /me/*; 403 only where the action is barred | `test_another_customers_request_is_404_not_403`<br>`test_a_nonexistent_id_is_indistinguishable_from_an_unowned_one`<br>`test_customer_on_an_internal_endpoint_is_403` | PASS |
| `K01 / K02` | No cross-account read by raw UUID, any resource | `test_cross_account_uuid_access_is_refused_for_every_resource`<br>`test_customer_cannot_read_another_customers_request` | PASS |
| `R10.3 / Q6` | Routes import no session, repository or SQLAlchemy | `test_routes_do_not_import_sessions_or_repositories`<br>`test_routes_reach_data_only_through_the_access_service` | PASS |
| `R10.3 / Q6` | No loader accepts an id without a subject | `test_no_loader_accepts_an_id_without_a_subject` | PASS |
| `R6.3 / Q4` | Staff individual reads audited; customer self-reads are not | `test_staff_read_of_an_individual_resource_is_audited`<br>`test_customer_self_read_is_not_audited_as_a_staff_read` | PASS |
| `R6.3a / Q4` | Denials audited for every actor class | `test_denials_are_audited_for_every_actor_class`<br>`test_denied_request_is_audited` | PASS |
| `R6.3b / Q4` | Audit metadata carries references, never payloads | `test_audit_metadata_cannot_carry_sensitive_payloads`<br>`test_access_records_carry_references_not_content` | PASS |
| `R6.3c / Q4` | A list is audited once, never per row | `test_a_list_is_audited_once_not_per_row`<br>`test_list_endpoint_audits_once` | PASS |
| `R6.3 / Q4` | Public and master-data reads need no per-resource audit | `test_public_and_master_data_reads_are_not_audited` | PASS |
| `R6.2 / S23` | A write with no actor is refused, not recorded anonymously | `test_write_without_an_actor_is_refused`<br>`test_actor_and_context_are_visible_to_the_audit_trigger`<br>`test_a_write_inside_the_wrapper_is_attributed` | PASS |
| `R14.1-R14.2` | Generated OpenAPI is checked against the frozen contract | `test_generated_paths_exist_in_the_frozen_contract`<br>`test_nothing_writes_to_the_frozen_contract` | PASS |
| `§12` | Problem responses carry the contract fields and leak no DB text | `test_problem_responses_carry_the_required_fields`<br>`test_problem_detail_never_leaks_database_text` | PASS |
| `INV-1 disclosure` | A conflicting claimant or staff may learn a conflict exists | `test_conflicting_claimant_is_told`<br>`test_the_other_claimant_is_also_told`<br>`test_authorized_staff_are_told`<br>`test_http_claimant_gets_409` | PASS |
| `INV-1 disclosure` | An unrelated actor gets ordinary concealment (404) | `test_an_unrelated_customer_is_not_told`<br>`test_http_unrelated_customer_gets_404` | PASS |
| `INV-1 disclosure` | The 409 reveals no claimant identity or conflict detail | `test_the_409_body_discloses_no_claimant_and_no_details`<br>`test_conflict_detail_is_a_fixed_string` | PASS |
| `INV-1 disclosure` | Internally explicit regardless of what the caller saw | `test_audit_is_full_even_when_the_caller_is_told_nothing`<br>`test_audit_marks_when_the_caller_was_told`<br>`test_conflict_is_audited_at_http_level` | PASS |
| `§2.5 / §8` | Error contract: stable codes, no DB or sensitive text | `test_every_catalogued_code_has_one_status`<br>`test_required_fields_match_the_frozen_problem_schema`<br>`test_detail_refuses_implementation_and_sensitive_text`<br>`test_an_unhandled_error_returns_a_code_and_a_trace_id` | PASS |
| `§2.5` | Transport status is preserved, never rewritten from a code | `test_transport_status_is_preserved_not_rewritten`<br>`test_method_not_allowed_is_problem_json` | PASS |
| `K04` | Validation echoes field locations, never input values | `test_validation_errors_carry_field_errors_not_values` | PASS |
| `§2.3 / ADR-09` | Same key + same payload replays the stored result | `test_same_key_same_payload_replays_the_result`<br>`test_key_order_does_not_change_the_hash` | PASS |
| `§2.3 / ADR-09` | Same key + different payload is a 409 conflict | `test_same_key_different_payload_is_a_conflict`<br>`test_a_claimed_but_incomplete_key_is_a_conflict` | PASS |
| `§2.3` | Idempotency scope is per actor and per route | `test_the_same_key_is_independent_per_actor`<br>`test_the_same_key_is_independent_per_route`<br>`test_the_record_lands_in_the_frozen_table` | PASS |
| `§2.4` | If-Match required; stale version rejected with nothing applied | `test_a_missing_header_is_rejected`<br>`test_stale_version_is_rejected`<br>`test_a_concurrent_bump_makes_the_held_version_stale` | PASS |
| `§2.4 / §1` | Header name follows the OpenAPI contract, prose accepted as alias | `test_header_name_follows_the_openapi_contract`<br>`test_the_prose_header_name_is_accepted_as_an_alias`<br>`test_parties_is_not_versioned_in_the_frozen_schema` | PASS |
| `ADR-06 / R9.1` | Public/Customer/Internal are separate types, extras refused | `test_constructing_a_dto_with_an_internal_field_is_an_error`<br>`test_no_dto_declares_a_forbidden_field` | PASS |
| `R9.5 / K03` | DTO allow-lists are exact and match the frozen contract | `test_dto_field_sets_are_exactly_the_allow_list`<br>`test_the_public_schema_matches_the_frozen_contract`<br>`test_a_new_column_does_not_silently_reach_the_public_dto` | PASS |
| `D02` | Seller expectation never reaches a public or customer payload | `test_public_offer_never_carries_seller_expectation`<br>`test_public_render_from_a_real_property_row_leaks_nothing` | PASS |
| `R9.4 / S35` | price_visibility redacts price independently of scope | `test_price_is_redacted_when_visibility_is_not_public`<br>`test_public_price_is_shown_when_visibility_is_public` | PASS |
| `R8.2 / R8.2a` | Scope ladder adds; no scope lifts the never-serialized floor | `test_summary_only_withholds_property_detail`<br>`test_property_details_allowed_adds_the_customer_view`<br>`test_no_scope_lifts_the_never_serialized_floor` | PASS |
| `R8.3 / S34` | Contact released only after a recorded confirmation | `test_contact_is_withheld_without_a_recorded_confirmation`<br>`test_contact_is_released_after_a_recorded_confirmation` | PASS |
| `§8` | Structured logs redact OTP codes and sensitive payloads | `test_sensitive_keys_are_redacted`<br>`test_redaction_reaches_nested_structures`<br>`test_exceptions_log_type_and_message_not_a_traceback` | PASS |
| `Slice 0` | Health is liveness; readiness checks the database and fails 503 | `test_health_is_liveness_only`<br>`test_readiness_checks_the_database`<br>`test_readiness_reports_503_when_the_database_is_unreachable` | PASS |

## Reading this table

`Ref` cites RFC-001 revision 3 unless it names an implementation invariant
(`INV-1`, `INV-2`), which are the two fail-closed rules added at approval.

Coverage is by guarantee, not by line. Several rules are proved by more than
one test because the negative case and the positive case are both needed: that
a relation does **not** grant access is only meaningful alongside proof that a
claim **does**.
