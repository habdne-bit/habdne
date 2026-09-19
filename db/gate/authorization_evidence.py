#!/usr/bin/env python3
"""Generate the Authorization Evidence Matrix from a real test run.

Each RFC-001 rule and implementation invariant is mapped to the tests that
prove it. The status column comes from `reports/junit.xml`, so the matrix
reports what actually ran rather than what someone believed.

Two failure modes are treated as errors, because either makes the matrix a
claim instead of evidence:
  * a rule whose mapping matches no test  -> the rule is unproven;
  * a mapped test that failed or errored  -> the rule is disproven.

Usage:
  db/gate/authorization_evidence.py            # run tests, write the matrix
  db/gate/authorization_evidence.py --check    # regenerate and fail if stale
"""
from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass

ROOT = pathlib.Path(__file__).resolve().parents[2]
JUNIT = ROOT / "reports" / "junit.xml"
OUT = ROOT / "docs" / "gate" / "AUTHORIZATION_EVIDENCE_MATRIX.md"


@dataclass(frozen=True)
class Rule:
    ref: str
    statement: str
    tests: tuple[str, ...]


#: (rule reference, what it guarantees, substrings identifying its tests)
RULES: tuple[Rule, ...] = (
    # --- actor resolution --------------------------------------------------
    Rule("R3.1", "A null party matches nobody; explicit guard, not NULL semantics",
         ("test_customer_with_no_party_is_refused", "test_staff_account_has_no_party")),
    Rule("R3.2", "Party, roles and status are read per request, never from the token",
         ("test_subject_reads_party_and_roles_from_the_database",)),
    Rule("R3.3", "Mixed staff/customer roles are evaluated per operation",
         ("test_staff_cannot_use_me_endpoints", "test_customer_cannot_use_internal_endpoints")),
    Rule("R4.11a", "Only ACTIVATED accounts carry authority",
         ("test_non_activated_account_resolves_to_no_authority",)),
    # --- roles -------------------------------------------------------------
    Rule("R2.1 / INV-2", "OPERATOR+REVIEWER rejected at role-assignment time",
         ("test_granting_reviewer_to_an_operator_is_rejected",
          "test_granting_operator_to_a_reviewer_is_rejected",
          "test_rejected_grant_writes_nothing")),
    Rule("INV-2", "Existing anomalies fail closed for separation-sensitive actions",
         ("test_separation_sensitive_actions_fail_closed",
          "test_non_sensitive_operations_still_work_under_an_anomaly")),
    Rule("INV-2", "The configuration anomaly is audited",
         ("test_the_anomaly_is_audited", "test_anomaly_in_existing_data_is_detected")),
    Rule("R2.3 / decision 3", "Roles are literal; no ADMIN/REVIEWER/OPERATOR inheritance",
         ("test_roles_are_literal_with_no_inheritance",
          "test_invalid_role_combination_detection")),
    Rule("§2.1 / decision 8", "Maker-checker split preserved exactly",
         ("test_roles_are_literal_with_no_inheritance",
          "test_separation_sensitive_operations_all_exist")),
    # --- policy layer ------------------------------------------------------
    Rule("R10.1 / decision 7", "Deny by default: no policy entry, no access",
         ("test_unknown_operation_is_denied", "test_empty_policy_table_denies_everything")),
    Rule("R10.2", "Policy table equals the frozen contract, role for role",
         ("test_policy_matches_the_frozen_contract",
          "test_every_contract_operation_has_a_policy")),
    Rule("R10.3a / decision 5", "getReasonCodes: ADMIN/OPERATOR/REVIEWER, not CUSTOMER",
         ("test_reason_codes_is_the_only_role_exception",
          "test_customer_is_refused_reason_codes_and_staff_allowed",
          "test_customer_reason_codes_is_403_staff_is_200")),
    Rule("R10.4", "Unauthenticated operations are a closed list of six",
         ("test_unauthenticated_operations_are_a_closed_list_of_six",)),
    # --- object authority --------------------------------------------------
    Rule("R4.1", "PROPERTY authority: creator account OR a recorded claim",
         ("test_claim_event_grants_property_access",
          "test_claim_grants_authority_that_did_not_exist_before")),
    Rule("R4.2", "PROPERTY authority is account-scoped, not party-scoped",
         ("test_property_authority_is_account_scoped_not_party_scoped",)),
    Rule("R4.3", "A NULL creator matches nobody",
         ("test_orphan_property_with_null_creator_matches_nobody",)),
    Rule("R4.5 / decision 1", "Relations are never an authorization source",
         ("test_relationship_alone_never_grants_property_access",
          "test_authorization_sql_never_reads_party_property_relations",
          "test_the_relations_check_would_catch_a_violation")),
    Rule("R4.6", "An expired relation cannot revoke a claimed owner",
         ("test_expired_relation_does_not_revoke_a_claimed_owner",)),
    Rule("R4.8", "REQUEST needs party match AND CLAIMED",
         ("test_party_match_alone_is_not_enough_for_an_assisted_request",
          "test_customer_reads_own_claimed_request")),
    Rule("R4.9", "Aliases resolve to canonical before the authority check",
         ("test_alias_resolves_to_canonical_before_the_authority_check",)),
    Rule("R4.10", "ASSISTED+UNCLAIMED has no authorized customer",
         ("test_assisted_unclaimed_property_has_no_authorized_customer",)),
    # --- Q9 ----------------------------------------------------------------
    Rule("§4.6 cond.1 / Q9", "Offer creator account is authorized",
         ("test_offer_creator_is_authorized",)),
    Rule("§4.6 cond.2 / Q9", "Parent claim + party match + parent CLAIMED",
         ("test_claimant_reads_own_offer_on_claimed_property",
          "test_unclaimed_parent_blocks_condition_two")),
    Rule("R4.12 / Q9", "offer.party_id alone, and relations, never grant",
         ("test_offer_party_match_alone_never_grants",
          "test_relations_never_grant_offer_access")),
    Rule("R4.13 / Q9", "A property claim never opens another party's offer",
         ("test_property_claim_does_not_open_another_partys_offer",)),
    # --- INV-1 -------------------------------------------------------------
    Rule("INV-1 read", "Two distinct claimants grant authority to nobody",
         ("test_two_distinct_claimants_grant_authority_to_nobody",
          "test_duplicate_claim_rows_by_the_same_account_are_not_a_conflict",
          "test_requests_conflict_the_same_way_as_properties")),
    Rule("INV-1 audit", "CLAIM_AUTHORITY_CONFLICT is audited and surfaced",
         ("test_conflict_is_audited_and_surfaces_as_a_conflict",)),
    Rule("INV-1 write", "Second claim rejected; same-actor replay is idempotent",
         ("test_second_claim_by_another_account_is_rejected",
          "test_replay_by_the_same_actor_is_idempotent",
          "test_claiming_an_already_conflicted_resource_is_rejected")),
    # --- concealment -------------------------------------------------------
    Rule("R5.3 / decision 2", "404 conceals on /me/*; 403 only where the action is barred",
         ("test_another_customers_request_is_404_not_403",
          "test_a_nonexistent_id_is_indistinguishable_from_an_unowned_one",
          "test_customer_on_an_internal_endpoint_is_403")),
    Rule("K01 / K02", "No cross-account read by raw UUID, any resource",
         ("test_cross_account_uuid_access_is_refused_for_every_resource",
          "test_customer_cannot_read_another_customers_request")),
    # --- structural (Q6) ---------------------------------------------------
    Rule("R10.3 / Q6", "Routes import no session, repository or SQLAlchemy",
         ("test_routes_do_not_import_sessions_or_repositories",
          "test_routes_reach_data_only_through_the_access_service")),
    Rule("R10.3 / Q6", "No loader accepts an id without a subject",
         ("test_no_loader_accepts_an_id_without_a_subject",)),
    # --- audit (Q4) --------------------------------------------------------
    Rule("R6.3 / Q4", "Staff individual reads audited; customer self-reads are not",
         ("test_staff_read_of_an_individual_resource_is_audited",
          "test_customer_self_read_is_not_audited_as_a_staff_read")),
    Rule("R6.3a / Q4", "Denials audited for every actor class",
         ("test_denials_are_audited_for_every_actor_class", "test_denied_request_is_audited")),
    Rule("R6.3b / Q4", "Audit metadata carries references, never payloads",
         ("test_audit_metadata_cannot_carry_sensitive_payloads",
          "test_access_records_carry_references_not_content")),
    Rule("R6.3c / Q4", "A list is audited once, never per row",
         ("test_a_list_is_audited_once_not_per_row", "test_list_endpoint_audits_once")),
    Rule("R6.3 / Q4", "Public and master-data reads need no per-resource audit",
         ("test_public_and_master_data_reads_are_not_audited",)),
    # --- transactions / contract ------------------------------------------
    Rule("R6.2 / S23", "A write with no actor is refused, not recorded anonymously",
         ("test_write_without_an_actor_is_refused",
          "test_actor_and_context_are_visible_to_the_audit_trigger",
          "test_a_write_inside_the_wrapper_is_attributed")),
    Rule("R14.1-R14.2", "Generated OpenAPI is checked against the frozen contract",
         ("test_generated_paths_exist_in_the_frozen_contract",
          "test_nothing_writes_to_the_frozen_contract")),
    Rule("§12", "Problem responses carry the contract fields and leak no DB text",
         ("test_problem_responses_carry_the_required_fields",
          "test_problem_detail_never_leaks_database_text")),
    # --- INV-1 disclosure (clarification of 2026-09-19) --------------------
    Rule("INV-1 disclosure", "A conflicting claimant or staff may learn a conflict exists",
         ("test_conflicting_claimant_is_told", "test_the_other_claimant_is_also_told",
          "test_authorized_staff_are_told", "test_http_claimant_gets_409")),
    Rule("INV-1 disclosure", "An unrelated actor gets ordinary concealment (404)",
         ("test_an_unrelated_customer_is_not_told",
          "test_http_unrelated_customer_gets_404")),
    Rule("INV-1 disclosure", "The 409 reveals no claimant identity or conflict detail",
         ("test_the_409_body_discloses_no_claimant_and_no_details",
          "test_conflict_detail_is_a_fixed_string")),
    Rule("INV-1 disclosure", "Internally explicit regardless of what the caller saw",
         ("test_audit_is_full_even_when_the_caller_is_told_nothing",
          "test_audit_marks_when_the_caller_was_told",
          "test_conflict_is_audited_at_http_level")),
    # --- Slice 0 foundation ------------------------------------------------
    Rule("§2.5 / §8", "Error contract: stable codes, no DB or sensitive text",
         ("test_every_catalogued_code_has_one_status",
          "test_required_fields_match_the_frozen_problem_schema",
          "test_detail_refuses_implementation_and_sensitive_text",
          "test_an_unhandled_error_returns_a_code_and_a_trace_id")),
    Rule("§2.5", "Transport status is preserved, never rewritten from a code",
         ("test_transport_status_is_preserved_not_rewritten",
          "test_method_not_allowed_is_problem_json")),
    Rule("K04", "Validation echoes field locations, never input values",
         ("test_validation_errors_carry_field_errors_not_values",)),
    Rule("§2.3 / ADR-09", "Same key + same payload replays the stored result",
         ("test_same_key_same_payload_replays_the_result",
          "test_key_order_does_not_change_the_hash")),
    Rule("§2.3 / ADR-09", "Same key + different payload is a 409 conflict",
         ("test_same_key_different_payload_is_a_conflict",
          "test_a_claimed_but_incomplete_key_is_a_conflict")),
    Rule("§2.3", "Idempotency scope is per actor and per route",
         ("test_the_same_key_is_independent_per_actor",
          "test_the_same_key_is_independent_per_route",
          "test_the_record_lands_in_the_frozen_table")),
    Rule("§2.4", "If-Match required; stale version rejected with nothing applied",
         ("test_a_missing_header_is_rejected", "test_stale_version_is_rejected",
          "test_a_concurrent_bump_makes_the_held_version_stale")),
    Rule("§2.4 / D1", "Canonical header is If-Match-Version, integer-typed, no alias",
         ("test_header_name_follows_the_openapi_contract",
          "test_parse_accepts_a_version_integer",
          "test_etag_forms_are_no_longer_accepted",
          "test_the_old_if_match_alias_is_gone")),
    Rule("§2.4 / D2", "PARTY is versioned; the version is bumped and unforgeable",
         ("test_parties_is_now_versioned", "test_updating_a_party_bumps_its_version",
          "test_the_parties_version_check_constraint_holds",
          "test_a_client_cannot_forge_a_party_version")),
    Rule("D2", "CustomerPartyView exposes version so a CUSTOMER can PATCH",
         ("test_customer_party_view_exposes_version",)),
    Rule("ADR-06 / R9.1", "Public/Customer/Internal are separate types, extras refused",
         ("test_constructing_a_dto_with_an_internal_field_is_an_error",
          "test_no_dto_declares_a_forbidden_field")),
    Rule("R9.5 / K03", "DTO allow-lists are exact and match the frozen contract",
         ("test_dto_field_sets_are_exactly_the_allow_list",
          "test_the_public_schema_matches_the_frozen_contract",
          "test_a_new_column_does_not_silently_reach_the_public_dto")),
    Rule("D02", "Seller expectation never reaches a public or customer payload",
         ("test_public_offer_never_carries_seller_expectation",
          "test_public_render_from_a_real_property_row_leaks_nothing")),
    Rule("R9.4 / S35", "price_visibility redacts price independently of scope",
         ("test_price_is_redacted_when_visibility_is_not_public",
          "test_public_price_is_shown_when_visibility_is_public")),
    Rule("R8.2 / R8.2a", "Scope ladder adds; no scope lifts the never-serialized floor",
         ("test_summary_only_withholds_property_detail",
          "test_property_details_allowed_adds_the_customer_view",
          "test_no_scope_lifts_the_never_serialized_floor")),
    Rule("R8.3 / S34", "Contact released only after a recorded confirmation",
         ("test_contact_is_withheld_without_a_recorded_confirmation",
          "test_contact_is_released_after_a_recorded_confirmation")),
    Rule("§8", "Structured logs redact OTP codes and sensitive payloads",
         ("test_sensitive_keys_are_redacted", "test_redaction_reaches_nested_structures",
          "test_exceptions_log_type_and_message_not_a_traceback")),
    # --- Slice 1 --------------------------------------------------------
    Rule("Slice 1 / A02", "Phone verification alone creates no party and no account",
         ("test_verify_phone_control_creates_no_account",
          "test_login_purpose_creates_no_account_when_none_exists",
          "test_otp_is_unauthenticated_and_creates_nothing")),
    Rule("Slice 1 / provider boundary",
         "The provider owns the challenge; TURAB stores none of it",
         ("test_turab_stores_no_challenge_state",
          "test_challenge_id_is_the_providers_verification_id",
          "test_attempt_limits_belong_to_the_provider",
          "test_a_provider_outage_is_503_not_a_rejection")),
    Rule("Slice 1 / fail closed",
         "An unestablished purpose never yields a session",
         ("test_an_unestablished_purpose_fails_closed",
          "test_a_rejected_code_changes_nothing",
          "test_an_unknown_verification_is_rejected")),
    Rule("Slice 1", "LOGIN activates only an account that already exists",
         ("test_login_activates_an_existing_invited_account",
          "test_login_does_not_resurrect_a_disabled_account")),
    Rule("Slice 1 / A01", "One phone reaches two parties without merging them",
         ("test_one_phone_can_reach_two_parties_without_merging",
          "test_the_same_number_in_a_different_format_is_the_same_contact_point",
          "test_reusing_a_contact_point_does_not_transfer_its_verified_control")),
    Rule("Slice 1 / B03", "Revoked consent authorizes nothing new; history survives",
         ("test_revoked_consent_cannot_bind", "test_revocation_leaves_history_intact",
          "test_revoking_twice_is_not_an_error")),
    Rule("Slice 1 / B01-B02", "Consent binds only to its own party, scope and resource",
         ("test_consent_of_party_a_cannot_bind_to_request_of_party_b",
          "test_purpose_must_equal_the_granted_scope",
          "test_property_binding_requires_an_active_party_property_relation",
          "test_property_binding_succeeds_with_an_active_relation",
          "test_an_expired_relation_does_not_authorize_a_property_binding")),
    Rule("§2.3 applied", "Idempotency is enforced on the commands that declare it",
         ("test_missing_idempotency_key_is_rejected",
          "test_same_key_same_payload_replays",
          "test_same_key_different_payload_is_409",
          "test_a_replay_creates_no_second_row")),
    Rule("§2.4 applied", "If-Match-Version is enforced; a stale version applies nothing",
         ("test_patch_requires_the_version_header",
          "test_patch_with_the_current_version_succeeds_and_bumps_it",
          "test_patch_with_a_stale_version_is_409_and_changes_nothing",
          "test_the_old_if_match_header_is_not_accepted")),
    Rule("Slice 1 / K01, K04", "Role boundaries and typed PATCH hold on the new surface",
         ("test_customer_cannot_read_a_party_internally",
          "test_reviewer_can_read_but_not_create",
          "test_patch_rejects_an_undeclared_field",
          "test_customer_cannot_create_a_consent_binding",
          "test_customer_cannot_revoke_another_partys_consent")),
    # --- Slice 1 object gate on the command surface (defect of 2026-09-19) --
    Rule("R4.4 / K01 applied",
         "A CUSTOMER cannot mutate a party that is not their own",
         ("test_customer_cannot_patch_another_partys_record",
          "test_customer_cannot_attach_a_phone_to_another_party",
          "test_customer_cannot_grant_consent_on_another_party")),
    Rule("R10.1 applied / decision 4",
         "Party creation is staff-only; a CUSTOMER cannot mint a party",
         ("test_customer_cannot_create_an_arbitrary_party",
          "test_staff_may_still_create_parties")),
    Rule("R3.1 applied",
         "A CUSTOMER with no party is authorized over nothing, not everything",
         ("test_a_customer_with_no_party_can_act_on_nothing",)),
    Rule("R4.4 positive",
         "The object gate still permits the legitimate caller",
         ("test_customer_may_patch_their_own_party",
          "test_customer_may_grant_consent_on_their_own_party",
          "test_staff_may_act_on_any_party")),
    Rule("R6.3a applied", "Every command refusal is audited",
         ("test_every_refusal_is_audited",)),
    Rule("R10.3 / Q6 applied",
         "The object gate is structural: a command route without one fails the build",
         ("test_every_command_route_performs_an_object_check",
          "test_the_guard_check_is_not_vacuous",
          "test_there_are_command_routes_to_check")),
    # --- Slice 1 timeline ---------------------------------------------------
    Rule("Slice 1 / timeline scope",
         "A timeline holds one party's interactions and nobody else's",
         ("test_the_timeline_holds_only_that_partys_interactions",
          "test_an_orphaned_interaction_belongs_to_nobody",
          "test_a_party_with_no_interactions_gets_an_empty_page")),
    Rule("R4.4 / R5.3b applied",
         "A list about an object still runs that object's gate",
         ("test_an_unknown_party_is_refused_not_answered_empty",
          "test_a_customer_cannot_read_any_timeline",
          "test_a_reviewer_may_read_it",
          "test_the_timeline_is_not_reachable_unauthenticated")),
    Rule("R9.1 applied",
         "An open contract schema is delegation, not permission: the field set "
         "is an allow-list and interaction metadata is outside it",
         ("test_interaction_metadata_never_reaches_the_response",
          "test_the_item_field_set_is_exactly_the_allow_list",
          "test_a_new_column_does_not_silently_reach_the_response")),
    Rule("PageMeta / PageSize",
         "Pagination partitions the timeline, is totally ordered, and is capped",
         ("test_pages_partition_the_timeline_without_overlap",
          "test_the_ordering_is_total_so_pages_cannot_repeat_a_row",
          "test_pagination_outside_the_contracts_bounds_is_rejected",
          "test_the_page_size_cap_is_the_contracts_maximum")),
    Rule("R6.3c / R6.3b applied",
         "The page is audited once, by shape and count, never by row",
         ("test_the_page_is_audited_once_not_per_row",
          "test_the_audit_records_the_query_shape_not_the_rows")),
    Rule("Slice 1 / A01 x A02",
         "A party contact-point link is not a login path",
         ("test_attaching_a_phone_to_a_party_creates_no_login_path",
          "test_a_shared_line_does_not_authenticate_as_the_party_that_shares_it")),
    Rule("D6 / baseline hygiene",
         "Version drift in any single claim is caught mechanically",
         ("test_a_consistent_package_passes",
          "test_drift_in_any_single_place_is_caught",
          "test_a_missing_artifact_is_an_error")),
    # --- migrations (R14.4-R14.7) -------------------------------------------
    Rule("R14.4", "The frozen schema IS the initial migration; it rebuilds an "
                  "empty environment and stamps at head",
         ("test_a_migration_rebuilds_an_empty_environment",
          "test_there_is_exactly_one_head")),
    Rule("R14.4 / R14.7",
         "The migrated catalog agrees with the static audit's own parse",
         ("test_the_migrated_catalog_matches_the_static_audit",)),
    Rule("R14.6", "A baseline that is not the frozen one refuses to migrate",
         ("test_the_migration_refuses_a_baseline_that_is_not_the_frozen_one",
          "test_the_declared_digest_is_the_frozen_one")),
    Rule("R14.4 / R14.5",
         "Autogenerate is refused; there is no metadata to diff the baseline against",
         ("test_autogenerate_is_refused",
          "test_env_declares_no_metadata_to_diff_against",
          "test_there_is_no_downgrade_from_the_baseline")),
    Rule("R14.4 stamp",
         "A database built from the frozen SQL is stamped, so upgrade is a no-op",
         ("test_a_stamped_database_is_already_at_head",
          "test_upgrading_a_stamped_database_is_a_no_op",
          "test_the_dev_reset_script_stamps_through_the_guard")),
    # --- CORRECTION-001 / decision D7 ---------------------------------------
    Rule("D7 / CORRECTION-001",
         "POST /parties succeeds for ADMIN and OPERATOR only",
         ("test_an_authorized_staff_role_creates_a_party",
          "test_a_customer_is_refused_403",
          "test_an_unauthenticated_caller_is_refused_401",
          "test_a_reviewer_is_also_refused")),
    Rule("D7 acceptance",
         "A refusal creates no party, no account and no role, and frees its key",
         ("test_a_refusal_creates_no_party_no_account_and_no_role",
          "test_a_refusal_claims_no_idempotency_record_in_its_own_scope",
          "test_the_refusal_is_audited")),
    Rule("D7 acceptance",
         "Idempotency and the customer's own REQUEST path are unaffected",
         ("test_idempotency_is_unchanged_for_an_authorized_caller",
          "test_the_key_is_still_required",
          "test_the_customer_may_still_create_their_own_request",
          "test_no_other_operation_lost_a_role")),
    Rule("DL-03 / R14.1",
         "A correction may only narrow, must name a decision, and the frozen "
         "package is never edited",
         ("test_a_correction_may_only_narrow",
          "test_a_correction_must_name_a_decision",
          "test_a_correction_cannot_empty_an_operation",
          "test_the_committed_correction_describes_the_contract_as_it_stands",
          "test_the_frozen_contract_is_not_edited",
          "test_the_policy_table_still_matches_the_contract_as_corrected",
          "test_the_correction_touched_exactly_one_operation")),
    Rule("Effective contract",
         "Frozen package + approved corrections is derived, current, and "
         "equals what is enforced",
         ("test_the_effective_contract_is_current",
          "test_the_effective_contract_matches_the_policy_table",
          "test_the_effective_contract_changes_nothing_else",
          "test_annotations_appear_only_where_a_correction_names_them",
          "test_the_adopted_workflow_is_recorded_in_the_effective_contract",
          "test_every_corrected_operation_carries_its_correction_identity",
          "test_the_api_inventory_is_generated_from_the_effective_contract")),
    Rule("D7 defence in depth",
         "The object gate on party creation is retained, not deleted as redundant",
         ("test_the_object_gate_on_party_creation_is_still_present",
          "test_customer_cannot_create_an_arbitrary_party")),
    # --- migration structural evidence --------------------------------------
    Rule("R14.4 structural",
         "The migrated database is structurally identical to the frozen schema, "
         "function bodies included",
         ("test_the_migrated_database_is_structurally_identical_to_the_frozen_schema",
          "test_the_fingerprint_notices_a_changed_function_body",
          "test_the_version_table_is_pinned_to_public")),
    Rule("R14.4 stamp guard",
         "A database that is not the baseline cannot be stamped as if it were",
         ("test_stamping_a_database_that_is_not_the_baseline_is_refused",
          "test_stamping_the_real_baseline_succeeds",
          "test_the_dev_reset_script_stamps_through_the_guard")),
    # --- Slice 2 ------------------------------------------------------------
    Rule("Slice 2 mandatory 1", "INTEREST never silently creates a REQUEST",
         ("test_recording_an_interest_creates_no_request",
          "test_no_application_code_creates_a_request_from_an_interest")),
    Rule("Slice 2 mandatory 2", "Criteria mutation bumps the request version",
         ("test_adding_a_criterion_bumps_the_request_version",
          "test_the_criterion_is_actually_stored")),
    Rule("Slice 2 mandatory 3",
         "Required/Preferred/Flexible are the buyer's word; no code path chooses one",
         ("test_importance_is_restricted_to_the_three_declared_values",
          "test_no_code_path_rewrites_importance_from_an_inference",
          "test_patch_cannot_reach_importance_fields")),
    Rule("Slice 2 mandatory 4",
         "A stale ACTIVE request becomes NEEDS_CONFIRMATION per the active policy",
         ("test_a_stale_active_request_becomes_needs_confirmation",
          "test_a_fresh_request_is_left_alone",
          "test_only_active_requests_are_moved",
          "test_a_never_confirmed_request_is_not_stale")),
    Rule("Slice 2 / §15.1",
         "The freshness window is read from the active policy, never hard-coded",
         ("test_the_threshold_comes_from_the_active_policy_not_from_code",
          "test_a_request_past_the_window_is_stale",
          "test_a_missing_policy_is_an_error_not_a_default",
          "test_staff_read_carries_derived_freshness")),
    Rule("Slice 2 mandatory 5", "An assisted request cannot be CLAIMED",
         ("test_the_management_pair_is_refused_when_incoherent",
          "test_the_database_refuses_it_too",
          "test_an_assisted_request_is_created_unclaimed",
          "test_an_assisted_record_cannot_be_created_claimed")),
    Rule("CORRECTION-002 / §5.2",
         "The adopted transition table is enforced; undefined edges are refused",
         ("test_the_documented_path_works_end_to_end",
          "test_an_undefined_transition_is_refused_not_guessed",
          "test_an_undefined_transition_is_refused_over_http",
          "test_an_active_request_may_be_paused_or_closed_directly")),
    Rule("CORRECTION-002 / reactivation",
         "Reactivation is the state command itself; it refreshes no "
         "confirmation, and reconfirming never resurrects PAUSED or CLOSED",
         ("test_reactivation_is_the_explicit_command_itself",
          "test_reactivation_does_not_refresh_the_confirmation",
          "test_reconfirming_does_not_resurrect_a_paused_or_closed_request")),
    Rule("CORRECTION-002 / closure reasons",
         "Closing requires an adopted REQUEST_CLOSURE reason; OTHER needs a note",
         ("test_the_adopted_closure_reasons_exist",
          "test_closing_requires_a_reason",
          "test_a_reason_from_another_category_is_refused",
          "test_the_other_closure_reason_requires_a_note",
          "test_closing_is_not_a_substitute_for_staleness_or_pausing",
          "test_the_closure_reason_migration_is_additive_and_re_runnable")),
    Rule("G-1 corrected",
         "The actor is distinguished from the source: channel, asserted party, "
         "whether a source was recorded, and the previous value",
         ("test_a_self_service_change_is_attributed_to_the_party",
          "test_a_staff_recorded_change_asserts_nothing_about_the_party",
          "test_the_absence_of_a_source_is_recorded_as_such",
          "test_a_recorded_source_is_carried_when_one_exists",
          "test_the_previous_value_is_recorded",
          "test_no_update_raises_the_verification_level")),
    Rule("G-5 corrected",
         "The freshness pass is an administrative command that must be RUN; "
         "re-running is safe and reconfirmed requests are untouched",
         ("test_the_freshness_command_moves_stale_requests",
          "test_running_it_twice_moves_nothing_the_second_time",
          "test_a_reconfirmed_request_is_left_alone_by_the_pass",
          "test_the_dry_run_changes_nothing",
          "test_nothing_in_the_application_calls_the_pass_by_itself")),
    Rule("R14.4 / revision ids",
         "Every revision id fits alembic_version.version_num",
         ("test_every_revision_id_fits_the_version_column",)),
    Rule("Slice 2 separation",
         "Data update, state transition and reconfirmation are three commands",
         ("test_a_data_update_does_not_touch_status_or_confirmation",
          "test_a_state_transition_does_not_touch_the_data_or_confirmation",
          "test_a_reconfirmation_does_not_change_what_the_buyer_wants",
          "test_reconfirming_returns_a_needs_confirmation_request_to_active",
          "test_the_three_commands_are_three_endpoints")),
    Rule("Slice 2 provenance",
         "A typed update records who said what, when, one observation per update",
         ("test_a_typed_update_records_who_said_what_and_when",
          "test_each_changed_field_gets_its_own_claim",
          "test_one_update_is_one_observation",
          "test_a_state_change_is_also_recorded")),
    Rule("CORRECTION-003 / contract x-authorization",
         "Claim eligibility is enforced: own party, own verified login contact "
         "point, and that point reaches the record's party",
         ("test_the_rightful_claimant_converts_the_record_in_place",
          "test_an_account_of_a_different_party_cannot_claim",
          "test_a_contact_point_of_another_account_does_not_prove_control",
          "test_staff_roles_alone_do_not_confer_the_right_to_claim")),
    Rule("CORRECTION-003 / DL-02",
         "A phone shared by two parties does not make one party the other",
         ("test_a_shared_phone_does_not_make_one_party_the_other",
          "test_a_customer_cannot_create_a_request_for_another_party",
          "test_a_shared_line_does_not_authenticate_as_the_party_that_shares_it")),
    Rule("CORRECTION-003 / concurrency",
         "Eligibility and state are checked inside the write transaction, under "
         "a row lock; a race yields one claim and no ambiguity",
         ("test_two_concurrent_claims_produce_one_claim_and_no_ambiguity",
          "test_a_second_eligible_claim_is_still_rejected")),
    Rule("CORRECTION-003 / no blocking trace",
         "A refused claim writes no claim event and does not block the rightful "
         "claimant",
         ("test_a_refused_attempt_does_not_block_the_rightful_claimant",)),
    Rule("CORRECTION-003 / fail closed",
         "PROPERTY claiming is refused until its eligibility rule is decided",
         ("test_property_claiming_fails_closed",)),
    Rule("Slice 2 / K01 applied",
         "A customer commands only their own request; staff reads are audited",
         ("test_a_customer_cannot_command_another_partys_request",
          "test_a_customer_cannot_read_a_request_internally",
          "test_the_staff_read_is_audited",
          "test_a_stale_version_applies_nothing")),
    Rule("Slice 2 registry",
         "Criteria are structured: an unknown code is refused, not stored",
         ("test_an_unknown_criterion_code_is_a_typed_error",)),
    Rule("STOP GATE B",
         "An operator can state what the buyer wants, what is hard vs preferred, "
         "and when it was last confirmed — from one staff read",
         ("test_stop_gate_b_a_staff_operator_can_understand_the_request",
          "test_the_gate_scenario_would_fail_if_importance_were_not_carried")),
    Rule("Slice 0", "Health is liveness; readiness checks the database and fails 503",
         ("test_health_is_liveness_only", "test_readiness_checks_the_database",
          "test_readiness_reports_503_when_the_database_is_unreachable")),
)


def run_tests() -> None:
    JUNIT.parent.mkdir(parents=True, exist_ok=True)
    python = ROOT / ".venv" / "bin" / "python"
    exe = [str(python), "-m", "pytest"] if python.exists() else [sys.executable, "-m", "pytest"]
    subprocess.run([*exe, "-q", f"--junitxml={JUNIT}"], cwd=ROOT, check=False)


def parse_junit() -> tuple[dict[str, str], tuple[int, int]]:
    """(name -> status, (cases_passed, cases_total)).

    Names are deduplicated because a parametrised test appears once per case,
    but the totals count CASES, so the headline figure matches what pytest
    reports rather than a smaller, flattering number.
    """
    if not JUNIT.exists():
        raise SystemExit(f"{JUNIT} not found; run the suite first")
    results: dict[str, str] = {}
    cases_total = cases_passed = 0
    for case in ET.parse(JUNIT).getroot().iter("testcase"):
        cases_total += 1
        name = (case.get("name") or "").split("[")[0]
        status = "PASS"
        for child in case:
            if child.tag == "failure":
                status = "FAIL"
            elif child.tag == "error":
                status = "ERROR"
            elif child.tag == "skipped":
                status = "SKIP"
        # A parametrised test is PASS only if every case passed.
        if name in results and results[name] == "PASS":
            results[name] = status if status != "PASS" else "PASS"
        elif name not in results:
            results[name] = status
        elif status != "PASS":
            results[name] = status
        if status == "PASS":
            cases_passed += 1
    return results, (cases_passed, cases_total)


def render(results: dict[str, str], totals: tuple[int, int]) -> tuple[str, list[str]]:
    problems: list[str] = []
    rows: list[str] = []
    total_tests = 0

    for rule in RULES:
        statuses, matched = [], []
        for name in rule.tests:
            if name in results:
                matched.append(name)
                statuses.append(results[name])
            else:
                problems.append(f"{rule.ref}: no test named {name!r} — rule unproven")
        if not matched:
            verdict = "**UNPROVEN**"
        elif all(s == "PASS" for s in statuses):
            verdict = "PASS"
        else:
            verdict = "**FAIL**"
            problems.append(f"{rule.ref}: {[n for n, s in zip(matched, statuses) if s != 'PASS']}")
        total_tests += len(matched)
        evidence = "<br>".join(f"`{n}`" for n in rule.tests)
        rows.append(f"| `{rule.ref}` | {rule.statement} | {evidence} | {verdict} |")

    cases_passed, cases_total = totals
    body = f"""# TURAB — Authorization Evidence Matrix

**Generated** by `db/gate/authorization_evidence.py` from `reports/junit.xml`.
**Do not edit.** The status column is a real test result, not an assertion.

- Rules and invariants covered: **{len(RULES)}**
- Distinct tests cited: **{len({n for r in RULES for n in r.tests})}**
- Suite total: **{cases_passed}/{cases_total}** test cases passing ({len(results)} distinct test functions)

A rule whose mapping matches no test is reported **UNPROVEN** and fails the
check: an evidence matrix that can silently lose its evidence is worse than no
matrix, because it reads as assurance.

| Ref | Guarantee | Evidence | Status |
|---|---|---|---|
""" + "\n".join(rows) + """

## Reading this table

`Ref` cites RFC-001 revision 3 unless it names an implementation invariant
(`INV-1`, `INV-2`), which are the two fail-closed rules added at approval.

Coverage is by guarantee, not by line. Several rules are proved by more than
one test because the negative case and the positive case are both needed: that
a relation does **not** grant access is only meaningful alongside proof that a
claim **does**.
"""
    return body, problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true",
                    help="regenerate and fail if the committed matrix is stale")
    ap.add_argument("--no-run", action="store_true", help="use an existing junit.xml")
    args = ap.parse_args()

    if not args.no_run:
        run_tests()
    results, totals = parse_junit()
    body, problems = render(results, totals)

    if problems:
        print("EVIDENCE MATRIX PROBLEMS:", file=sys.stderr)
        for p in problems:
            print(f"  {p}", file=sys.stderr)
        return 1

    if args.check:
        if not OUT.exists() or OUT.read_text(encoding="utf-8") != body:
            print(f"FAIL: {OUT} is stale; regenerate it", file=sys.stderr)
            return 1
        print(f"PASS: {OUT} is current")
        return 0

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(body, encoding="utf-8")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
