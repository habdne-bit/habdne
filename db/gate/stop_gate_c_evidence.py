#!/usr/bin/env python3
"""Generate the Slice 3 STOP GATE C evidence from a real test run.

The source of every status is a JUnit report: by default the one committed
with the clean-tree run, `docs/gate/evidence/junit-run.xml`, whose tree
`docs/gate/evidence/TEST-RUN-PROVENANCE.txt` binds (commit, fingerprint).
Nothing in the output is written by hand.

Mapped, each to named tests:
- the six STOP GATE C questions (plan §6);
- the seven mandatory tests (§6.1);
- the RFC-001 scenarios (§5.1);
- the four concurrency tests (§6.3).

The acceptance conditions (§7) come with what can be COMPUTED from the tree:
- which of the plan's operations have a route;
- which files write `match_candidates` or `record_claim_events`;
- which migrations exist.

The same discipline as the authorization matrix: a mapped test that is
absent, or that did not pass, fails `--check`. The ONLY absence tolerated is
a documented exception. It names why the planned test cannot be written, and
which tests answer the question instead; those tests must themselves pass.

Usage:
  db/gate/stop_gate_c_evidence.py [--junit PATH]           # write the document
  db/gate/stop_gate_c_evidence.py [--junit PATH] --check   # fail if stale or unproven
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_JUNIT = ROOT / "docs" / "gate" / "evidence" / "junit-run.xml"
PROVENANCE = ROOT / "docs" / "gate" / "evidence" / "TEST-RUN-PROVENANCE.txt"
OUT = ROOT / "docs" / "gate" / "SLICE_3_STOP_GATE_C.md"

#: (question, planned tests, documented exceptions:
#:   (planned name that cannot be written, why, tests that answer instead))
QUESTIONS = (
    ("What is the physical property?",
     ("test_a_property_is_created_with_its_type_location_and_supply_mode",
      "test_property_attributes_are_unique_per_definition"), ()),
    ("What offers exist for it?",
     ("test_owner_sale_broker_sale_and_rent_coexist_on_one_property",),
     (("test_listing_a_property_returns_all_of_its_offers",
       "Finding G3-16: the frozen contract declares no operation that lists a "
       "property's offers (`/properties/{property_id}/offers` has only POST). "
       "Offers are read one by one (`GET /offers/{id}`), and publicly only as "
       "the consented subset.",
       ("test_owner_sale_broker_sale_and_rent_coexist_on_one_property",
        "test_only_active_consented_offers_are_projected")),)),
    ("Who supplied each fact?",
     ("test_a_claim_must_carry_at_least_one_origin",
      "test_a_source_is_created_only_through_an_external_lead"),
     (("test_converting_a_lead_records_its_party_and_consent",
       "Decision G3-10: conversion is refused with a typed 409 until the "
       "conversion schema is decided. The refusal is what can be proven.",
       ("test_conversion_is_refused_with_a_typed_409_and_changes_nothing",)),)),
    ("What is current and what is historical?",
     ("test_only_one_resolved_value_is_current_per_attribute",
      "test_superseding_closes_the_previous_row_in_the_same_transaction",
      "test_a_stale_offer_is_reported_stale_on_its_commercial_terms_clock"), ()),
    ("What is declared and what is checked?",
     ("test_a_claim_is_born_declared",
      "test_only_a_confirmed_verification_event_raises_the_level",
      "test_a_non_confirmed_outcome_records_the_event_and_changes_nothing"), ()),
    ("Canonical or alias?",
     ("test_confirmed_same_writes_the_alias_before_the_status",
      "test_the_canonical_resolver_returns_the_canonical_for_an_alias",
      "test_confirming_same_raises_review_work_for_affected_open_records"), ()),
)

MANDATORY = (
    ("1", "Owner sale, broker sale and rent coexist on one property",
     ("test_owner_sale_broker_sale_and_rent_coexist_on_one_property",)),
    ("2", "Seller expectation absent from public and customer DTOs",
     ("test_seller_expectation_never_appears_in_a_public_or_customer_payload",
      "test_seller_expectation_never_appears_in_the_public_list")),
    ("3", "A claim cannot be created DOCUMENT_SEEN",
     ("test_a_claim_cannot_be_created_already_verified",)),
    ("4", "A verification event is required to raise the level",
     ("test_only_a_confirmed_verification_event_raises_the_level",)),
    ("5", "A resolution cannot cite a foreign claim",
     ("test_a_resolution_cannot_cite_a_claim_about_another_subject",
      "test_a_resolution_cannot_cite_a_claim_about_another_attribute")),
    ("6", "CONFIRMED_SAME without its alias fails",
     ("test_confirmed_same_without_a_canonical_id_is_refused",
      "test_the_canonical_must_be_one_of_the_candidate_pair",
      "test_the_trigger_refuses_a_same_status_without_its_alias")),
    ("7", "Matching inputs use canonical, not alias — NARROWED (plan §6.4): "
          "proven as a query; no matching input exists yet",
     ("test_the_canonical_resolver_returns_the_canonical_for_an_alias",
      "test_e02_a_new_match_on_the_alias_is_refused_by_the_schema")),
)

SCENARIOS = (
    ("S10", "customer reads a property they created — allow",
     "test_s10_a_customer_reads_a_property_they_created"),
    ("S11", "NULL creator — deny 404",
     "test_s11_a_property_whose_creator_is_null_is_denied_to_every_customer"),
    ("S12", "any relation_code, no claim, not creator — deny 404",
     "test_s12_a_relation_alone_grants_nothing"),
    ("S12 e2e", "a relation made through the G3-6 API — deny",
     "test_s12_end_to_end_a_relation_created_through_the_api_grants_nothing"),
    ("S13", "authorized on an alias reads the canonical — allow",
     "test_s13_authority_resolves_through_an_alias_to_the_canonical"),
    ("S14", "ASSISTED + UNCLAIMED — deny 404",
     "test_s14_a_customer_cannot_read_an_assisted_unclaimed_property"),
    ("S15", "the same record after a claim — allow",
     "test_s15_the_same_record_after_a_successful_claim_is_allowed"),
    ("S16", "relation DECLARED, claim exists — allow",
     "test_s16_a_declared_unverified_relation_does_not_block_a_claimant"),
    ("S16a", "claimed owner, relation expired — allow",
     "test_s16a_an_expired_relation_does_not_revoke_a_claimed_owner"),
    ("S16b", "second account of the same party — deny 404",
     "test_s16b_a_second_account_of_the_same_party_is_denied"),
    ("S16d", "owner who claimed reads their own offer — allow",
     "test_s16d_an_owner_who_claimed_the_property_commands_their_own_offer"),
    ("S16e", "the same owner, the broker's offer — deny 404",
     "test_s16e_the_same_owner_cannot_command_anothers_offer_on_that_property"),
    ("S16f", "broker reads the offer they created — allow",
     "test_s16f_a_creator_commands_their_offer_without_any_claim"),
    ("S16g", "party match, no parent claim, not creator — deny 404",
     "test_s16g_a_party_match_alone_grants_nothing"),
    ("S16h", "relations row only — deny 404",
     "test_s16h_a_relation_row_grants_nothing"),
    ("S16h e2e", "a relation made through the G3-6 API opens no offer",
     "test_s16h_end_to_end_a_relation_opens_no_offer"),
    ("S16i", "owner account later DISABLED — deny (401; RFC says 404: G3-15)",
     "test_s16i_an_owner_whose_account_is_later_disabled_is_denied"),
    ("S16j", "INVITED or SUSPENDED — deny (401; RFC says 404: G3-15)",
     "test_s16j_an_invited_or_suspended_account_is_denied"),
)

CONCURRENCY = (
    ("primary source links", "the parent offer row", "both succeed; one primary",
     "test_two_concurrent_primary_source_links_leave_exactly_one_primary"),
    ("resolutions of one attribute", "the subject row",
     "both succeed; one CURRENT; history kept",
     "test_two_concurrent_resolutions_of_one_attribute_yield_one_current_value"),
    ("generation of one pair", "the pair index (generators' FOR SHARE locks "
     "are compatible)", "both succeed; one candidate",
     "test_generating_the_same_pair_twice_concurrently_yields_one_candidate"),
    ("offer transitions from one state", "the offer row + `AND status = :expected`",
     "winner and loser (declared compare-and-set)",
     "test_two_concurrent_offer_transitions_from_one_state_do_not_both_apply"),
)


def parse(junit: pathlib.Path) -> dict[str, str]:
    """name -> PASS / FAIL / ERROR / SKIP; a parametrised test is PASS only
    if every case passed."""
    results: dict[str, str] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        name = (case.get("name") or "").split("[")[0]
        status = "PASS"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                status = {"failure": "FAIL", "error": "ERROR", "skipped": "SKIP"}[child.tag]
        if results.get(name, "PASS") == "PASS":
            results[name] = status
    return results


def _status(results, name, problems, where):
    status = results.get(name, "MISSING")
    if status != "PASS":
        problems.append(f"{where}: {name} is {status}")
    return status if status == "PASS" else f"**{status}**"


def _plan_operations() -> list[str]:
    text = (ROOT / "docs" / "gate" / "SLICE_3_PLAN.md").read_text()
    section = text[text.index("## 1. Operations in scope"):text.index("## 2. Deliverables")]
    return re.findall(r"^\| `([A-Za-z]+)` \|", section, re.M)


def _routed() -> set[str]:
    routes = ROOT / "src" / "turab" / "api" / "routes"
    return {m for p in routes.glob("*.py")
            for m in re.findall(r'operation_id="([A-Za-z]+)"', p.read_text())}


def _writers(table: str) -> list[str]:
    pattern = re.compile(rf"INSERT\s+INTO\s+turab\.{table}\b")
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")
                  if pattern.search(p.read_text()))


def render(results: dict[str, str], junit: pathlib.Path) -> tuple[str, list[str]]:
    problems: list[str] = []
    bound = junit == DEFAULT_JUNIT.resolve()
    shown = junit.relative_to(ROOT) if junit.is_relative_to(ROOT) else junit
    out = ["# Slice 3 — STOP GATE C evidence", "",
           "**Generated** by `db/gate/stop_gate_c_evidence.py` from "
           f"`{shown}`. **Do not edit.**", ""]
    if bound:
        # Provenance is claimed ONLY for the committed report, which
        # TEST-RUN-PROVENANCE.txt describes. Any other report is unbound.
        prov = PROVENANCE.read_text()
        commit = re.search(r"Commit      : (\S+)", prov)
        finger = re.search(r"Source fingerprint \(db/dev/source_fingerprint.py\):\n\s+(\S+)",
                           prov)
        totals = re.search(r"tests=(\d+) failures=(\d+) errors=(\d+)", prov)
        if not (commit and finger and totals):
            problems.append("TEST-RUN-PROVENANCE.txt lacks commit, fingerprint or totals")
        else:
            out += [f"- The JUnit run is bound to commit `{commit.group(1)}`, source "
                    f"fingerprint `{finger.group(1)}` "
                    "(`docs/gate/evidence/TEST-RUN-PROVENANCE.txt`).",
                    f"- That run: {totals.group(1)} test cases, {totals.group(2)} failures, "
                    f"{totals.group(3)} errors."]
    else:
        out += ["- **UNBOUND RUN**: this report is not the committed clean-tree run, and "
                "no commit or fingerprint is claimed for it."]
        problems.append("the report is not the committed run; the document is not evidence")
    out += ["- These are our runs; nobody else has re-run them.", ""]
    out += [
        "## 1. The six questions (plan §6)",
        "",
        "| Question | Planned test | Status |",
        "|---|---|---|",
    ]
    exceptions_text = []
    for question, tests, exceptions in QUESTIONS:
        for name in tests:
            out.append(f"| {question} | `{name}` | {_status(results, name, problems, question)} |")
        for planned, why, instead in exceptions:
            if planned in results:
                problems.append(f"{question}: {planned} now exists; remove the exception")
            answered = ", ".join(f"`{n}` {_status(results, n, problems, question)}"
                                 for n in instead)
            out.append(f"| {question} | `{planned}` | **NOT WRITTEN** (see below) |")
            exceptions_text.append(f"- **`{planned}`**: {why} Answered instead by: {answered}.")
    out += ["", "**Documented exceptions.**", "", *exceptions_text, "",
            "## 2. The seven mandatory tests (plan §6.1)", "",
            "| # | Test | Evidence | Status |", "|---|---|---|---|"]
    for num, what, tests in MANDATORY:
        for name in tests:
            out.append(f"| {num} | {what} | `{name}` | {_status(results, name, problems, 'mandatory ' + num)} |")
    out += ["", "## 3. RFC-001 scenarios (plan §5.1)", "",
            "| # | Scenario | Test | Status |", "|---|---|---|---|"]
    for sid, what, name in SCENARIOS:
        out.append(f"| {sid} | {what} | `{name}` | {_status(results, name, problems, sid)} |")
    out += ["", "## 4. Concurrency (plan §6.3)", "",
            "| Race | Serialises on | Expected | Test | Status |", "|---|---|---|---|---|"]
    for race, on, expected, name in CONCURRENCY:
        out.append(f"| {race} | {on} | {expected} | `{name}` | "
                   f"{_status(results, name, problems, race)} |")

    ops, routed = _plan_operations(), _routed()
    missing_routes = [o for o in ops if o not in routed]
    if missing_routes:
        problems.append(f"plan operations without a route: {missing_routes}")
    mc, rce = _writers("match_candidates"), _writers("record_claim_events")
    if mc:
        problems.append(f"match_candidates written by {mc}")
    migrations = sorted(p.name for p in (ROOT / "db" / "migrations" / "versions").glob("0*.py"))
    out += [
        "", "## 5. Acceptance conditions (plan §7): what is computed from the tree", "",
        f"- **Condition 1.** The plan names {len(ops)} operations; {len(ops) - len(missing_routes)} "
        f"have a route{'' if not missing_routes else '; WITHOUT: ' + ', '.join(missing_routes)}.",
        f"- **Condition 6.** Files inserting into `match_candidates`: "
        f"{mc if mc else 'none'}.",
        f"- **Condition 7.** Files inserting into `record_claim_events`: {rce}. PROPERTY "
        f"claims fail closed: `test_property_claiming_fails_closed` "
        f"{_status(results, 'test_property_claiming_fails_closed', problems, 'condition 7')}.",
        f"- **Condition 4.** Migrations present: {', '.join(migrations)}.",
        f"- **Condition 9.** `test_authorization_sql_never_reads_party_property_relations` "
        f"{_status(results, 'test_authorization_sql_never_reads_party_property_relations', problems, 'condition 9')}.",
        "",
        "The remaining conditions are argued in `docs/gate/SLICE_3_STEP8_DELIVERY.md`, which "
        "this document does not replace.",
    ]
    return "\n".join(out) + "\n", problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", type=pathlib.Path, default=DEFAULT_JUNIT)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    junit = args.junit.resolve()
    body, problems = render(parse(junit), junit)
    if args.check:
        current = OUT.read_text() if OUT.exists() else ""
        if current != body:
            problems.append(f"{OUT.relative_to(ROOT)} is stale; regenerate it")
    else:
        OUT.write_text(body)
        print(f"wrote {OUT}")
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
