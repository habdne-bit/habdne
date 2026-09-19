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
