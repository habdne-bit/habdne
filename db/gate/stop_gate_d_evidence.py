#!/usr/bin/env python3
"""Generate the Slice 4 STOP GATE D evidence from a real test run.

STOP GATE D (`IMPLEMENTATION_SLICES_v0.2.md`, Slice 4): "A human reviewer
must be able to read a candidate and reconstruct every eligibility decision
without an LLM." Plan: `docs/gate/SLICE_4_PLAN.md` §6.2.

As STOP GATE C's generator does, this one takes every status from a JUnit
report: by default the one committed with the clean-tree run,
`docs/gate/evidence/junit-run.xml`. Before any provenance is claimed,
`run_binding.check` must find the report's digest and counted cases to be
the recorded ones, no failed case, and the current tree's source
fingerprint to be the run's and the gate run's. Any failure is a problem,
and `--check` exits non-zero. Nothing in the output is written by hand.

**Tests are named by module and name** (`test_slice4_step8::test_x`), not
by name alone: a planned name may exist in two modules (an engine half and
an HTTP half), and a bare name would merge them.

Mapped, each to named tests:
- the two proofs of §6.2, reconstruction and replay, with the counts the
  run recorded (JUnit properties), and the tests that show neither proof
  is vacuous;
- the ten mandatory tests (§6.1), two of them narrowed as the plan states;
- the reference scenarios (§6.2);
- the concurrency tests (§6.3).

The acceptance conditions (§7) come with what can be COMPUTED from the tree:
- which of the plan's three operations have a route;
- which files write the match tables, `match_reviews` and `opportunities`;
- which migrations exist.

Usage:
  db/gate/stop_gate_d_evidence.py [--junit PATH]           # write the document
  db/gate/stop_gate_d_evidence.py [--junit PATH] --check   # fail if stale or unproven
"""
from __future__ import annotations

import argparse
import pathlib
import re
import sys
import xml.etree.ElementTree as ET

import run_binding

ROOT = pathlib.Path(__file__).resolve().parents[2]
DEFAULT_JUNIT = ROOT / "docs" / "gate" / "evidence" / "junit-run.xml"
GATE_RUN = ROOT / "docs" / "gate" / "evidence" / "gate-run.txt"
OUT = ROOT / "docs" / "gate" / "SLICE_4_STOP_GATE_D.md"

S2, S3, S4, S5, S6, S7, S8 = (f"test_slice4_step{n}" for n in (2, 3, 4, 5, 6, 7, 8))

#: §6.2: (proof, test, what it re-derives).
PROOFS = (
    ("Reconstruction", f"{S8}::test_every_stored_match_is_reconstructed_from_its_rows_alone",
     "from the match row and its criterion rows only: each criterion's `blocking`; the three "
     "freshness states and every binding's state, re-derived from their raw fields and "
     "`evaluated_at` by the versions the snapshots name; the hard and information gates; "
     "the freshness and permission gates on the re-derived states, and the precedence, by "
     "the versions the match names; every reason; the soft score; the next action"),
    ("Replay", f"{S8}::test_every_stored_match_replays_its_criterion_results_and_input_hash",
     "each criterion re-run by the rule version its row names on the stored snapshots; the "
     "input hash recomputed from the five stored snapshots and the registry digest the match "
     "was evaluated under (recorded, or attributed by the history; otherwise UNPROVEN)"),
)

#: Each proof is shown able to fail.
NOT_VACUOUS = (
    f"{S8}::test_reconstruction_detects_a_stored_decision_that_was_not_derived",
    f"{S8}::test_reconstruction_detects_a_blocking_flag_that_was_not_derived",
    f"{S8}::test_replay_detects_a_result_its_snapshots_do_not_give",
    # review of c657bd9 (R-S4-8-01): a state derived wrongly, then hashed with
    # its wrong inputs, which replay cannot see
    f"{S8}::test_a_freshness_state_derived_wrongly_is_reported",
    f"{S8}::test_a_binding_state_derived_wrongly_is_reported",
)

#: G4-19, decided (a) in the review of c657bd9: the digest every match was
#: evaluated under.
DIGEST = (
    f"{S8}::test_a_new_match_records_the_digest_that_entered_its_hash",
    f"{S8}::test_a_stored_match_still_replays_after_a_rule_version_is_added",
    f"{S8}::test_an_old_match_without_the_digest_and_a_new_one_replay_after_a_version_is_added",
    f"{S8}::test_a_digest_that_cannot_be_attributed_is_reported_unproven",
    "test_slice4_registry_history::test_each_recorded_digest_is_the_sha256_of_its_recorded_pairs",
    "test_slice4_registry_history::test_every_recorded_pair_is_still_pinned_with_the_same_source",
    "test_slice4_registry_history::test_the_current_registry_is_recorded_in_the_history",
    "test_slice4_registry_history::test_format_1_is_attributed_to_the_registry_of_7a223d7_alone",
)

#: §6.1: (number, the handoff's wording, narrowing or None, tests).
MANDATORY = (
    ("1", "BUY request cannot evaluate RENT offer", None,
     (f"{S8}::test_a_buy_request_never_evaluates_a_rent_offer",
      f"{S3}::test_the_schema_refuses_a_buy_match_on_a_rent_offer")),
    ("2", "Hard FAIL always blocks Opportunity",
     "NARROWED: the API review is Slice 5; proven on the engine, over HTTP, and on the schema",
     (f"{S8}::test_a_hard_fail_is_rejected_whatever_the_soft_score",
      f"{S8}::test_the_schema_refuses_to_approve_a_rejected_match")),
    ("3", "Required UNKNOWN → Need More Information", None,
     (f"{S8}::test_a_required_unknown_is_need_more_information_never_pass_or_fail",)),
    ("4", "`negotiable=true` above max is not automatic PASS", None,
     (f"{S8}::test_negotiable_above_max_is_unknown_not_pass",)),
    ("5", "seller expectation supports price internally, unexposed", None,
     (f"{S8}::test_seller_expectation_can_pass_price_and_is_never_exposed",
      f"{S8}::test_no_customer_or_public_operation_returns_a_match_or_a_diagnostic")),
    ("6", "potential property without offer only with willingness context",
     "NARROWED (G4-9 (a)): no willingness context exists in the schema, so only the refusing "
     "half is proven",
     (f"{S8}::test_a_potential_property_without_willingness_context_is_not_evaluated",)),
    ("7", "old Match replayable after request, property and offer change", None,
     (f"{S8}::test_an_old_match_replays_from_its_snapshots_after_everything_changed",)),
    ("8", "match rows are immutable", None,
     (f"{S8}::test_match_rows_and_their_criterion_results_cannot_change",)),
    ("9", "alias property cannot receive a new Match", None,
     (f"{S8}::test_an_alias_is_never_a_candidate",
      f"{S8}::test_the_schema_refuses_a_match_on_an_alias")),
    ("10", "no valid match is a valid result", None,
     (f"{S7}::test_no_candidate_is_a_valid_run",)),
)

#: §6.2: (scenario, statement, tests).
SCENARIOS = (
    ("M-01", "Required location FAIL, everything else excellent: rejected, no opportunity",
     (f"{S8}::test_m01_a_required_location_fail_rejects_whatever_else",)),
    ("M-02", "Required document UNKNOWN: NEED_MORE_INFORMATION and its action (no task, D1)",
     (f"{S8}::test_m02_a_required_document_unknown_asks_for_the_document",)),
    ("M-03", "Asking above max, expectation within it: PASS, expectation not shown",
     (f"{S8}::test_seller_expectation_can_pass_price_and_is_never_exposed",)),
    ("M-04", "Negotiable only, price above max: UNKNOWN, no automatic PASS",
     (f"{S8}::test_negotiable_above_max_is_unknown_not_pass",)),
    ("M-05", "Property stale, every criterion PASS: NEEDS_CONFIRMATION",
     (f"{S8}::test_m05_a_stale_property_with_every_criterion_passing_needs_confirmation",)),
    ("M-06", "Request stale: NEEDS_CONFIRMATION before any opportunity",
     (f"{S8}::test_m06_a_stale_request_needs_confirmation",)),
    ("G01", "hard fail dominates", (f"{S8}::test_a_hard_fail_is_rejected_whatever_the_soft_score",)),
    ("G02", "negotiable is not automatic pass",
     (f"{S8}::test_negotiable_above_max_is_unknown_not_pass",)),
    ("G03", "evaluated offer identity",
     (f"{S8}::test_g03_each_match_names_its_evaluated_offer_and_version",)),
    ("G04", "immutable replay",
     (f"{S8}::test_an_old_match_replays_from_its_snapshots_after_everything_changed",)),
    ("G05", "rule/policy lineage",
     (f"{S8}::test_g05_a_match_names_an_existing_policy_and_its_version",
      f"{S7}::test_every_version_used_is_stored_and_no_version_1_rule_is_cited")),
    ("G06", "no-match is valid", (f"{S7}::test_no_candidate_is_a_valid_run",)),
    ("C01", "buy/rent isolation", (f"{S8}::test_a_buy_request_never_evaluates_a_rent_offer",)),
    ("C03", "required unknown",
     (f"{S8}::test_a_required_unknown_is_need_more_information_never_pass_or_fail",)),
    ("C04", "criteria versioning",
     (f"{S8}::test_c04_changing_criteria_makes_a_new_match_and_keeps_the_old",)),
    ("D02", "seller expectation privacy",
     (f"{S8}::test_seller_expectation_can_pass_price_and_is_never_exposed",
      f"{S7}::test_the_explanation_never_states_the_seller_expectation")),
    ("B04", "private matching only (its matching half)",
     (f"{S8}::test_b04_a_private_matching_only_binding_admits_internal_matching",)),
    ("E02", "matching aliases prohibited",
     (f"{S8}::test_an_alias_is_never_a_candidate",
      f"{S8}::test_the_schema_refuses_a_match_on_an_alias")),
)

#: §6.3: (race, serialises on, expected, tests).
CONCURRENCY = (
    ("two identical runs", "the frozen UNIQUE of the match",
     "both succeed; one match; the loser reads it on a new connection",
     (f"{S7}::test_two_identical_runs_race_and_store_one_match",)),
    ("a run while the offer's price changes", "nothing: one snapshot",
     "the match records the state it read",
     (f"{S7}::test_a_run_racing_a_price_change_stores_the_state_it_read",)),
    ("one Idempotency-Key in two calls", "the key's UNIQUE",
     "the same body replays; another body is 409",
     (f"{S7}::test_one_key_and_one_body_in_two_concurrent_calls_return_the_original_result",
      f"{S7}::test_one_key_with_another_body_in_a_concurrent_call_is_409")),
)

#: Named in the computed acceptance conditions (§5 of the document).
CONDITIONS = (
    ("7", "matching changes no request, property, offer, consent or criterion",
     f"{S7}::test_the_run_changes_no_request_property_offer_consent_or_criterion"),
    ("8", "RULE_ENGINE, no AI trace, on every row",
     f"{S7}::test_a_run_stores_each_match_with_its_criteria_audit_and_one_diagnostic"),
    ("9", "no customer or public DTO carries a match field",
     f"{S8}::test_no_customer_or_public_operation_returns_a_match_or_a_diagnostic"),
    ("10", "relations are not read by matching",
     f"{S2}::test_the_matching_package_never_reads_party_property_relations"),
    ("11", "PROPERTY claims fail closed (G3-2 open)",
     "test_slice2_http::test_property_claiming_fails_closed"),
)

#: How the replay proof knows the digest (G4-19), stated in the document.
DIGEST_RULE = ("The input hash covers the rule-registry digest (G4-13). From explanation "
               "format 2, each match records the digest that entered its hash, computed once "
               "per run. Format-1 matches, written from `7a223d7` until format 2, carry none: "
               "the registry did not change in that range, and "
               "`registry_history.FORMAT_DIGESTS` attributes its one digest to them, with git "
               "evidence (`docs/gate/evidence/REGISTRY-HISTORY.txt`). A match whose digest can "
               "be neither read nor attributed is reported UNPROVEN; the current digest is "
               "never substituted.")


def mapped_names() -> set[str]:
    names = {t for _, t, _ in PROOFS} | set(NOT_VACUOUS) | set(DIGEST)
    for *_, tests in MANDATORY:
        names.update(tests)
    for *_, tests in SCENARIOS:
        names.update(tests)
    for *_, tests in CONCURRENCY:
        names.update(tests)
    names.update(t for *_, t in CONDITIONS)
    return names


def _qualified(case: ET.Element) -> str:
    module = (case.get("classname") or "").rsplit(".", 1)[-1]
    return f"{module}::{(case.get('name') or '').split('[')[0]}"


def parse(junit: pathlib.Path) -> tuple[dict[str, str], dict[str, dict[str, str]]]:
    """(module::name -> PASS / FAIL / ERROR / SKIP, module::name -> recorded
    properties). A parametrised test is PASS only if every case passed."""
    results: dict[str, str] = {}
    properties: dict[str, dict[str, str]] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        name = _qualified(case)
        status = "PASS"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                status = {"failure": "FAIL", "error": "ERROR", "skipped": "SKIP"}[child.tag]
            if child.tag == "properties":
                properties[name] = {p.get("name"): p.get("value") for p in child}
        if results.get(name, "PASS") == "PASS":
            results[name] = status
    return results, properties


def _status(results, name, problems, where):
    status = results.get(name, "MISSING")
    if status != "PASS":
        problems.append(f"{where}: {name} is {status}")
    return status if status == "PASS" else f"**{status}**"


def _plan_operations() -> list[str]:
    text = (ROOT / "docs" / "gate" / "SLICE_4_PLAN.md").read_text(encoding="utf-8")
    section = text[text.index("## 1. Operations in scope"):text.index("## 2. The engine")]
    return re.findall(r"^\| `([A-Za-z]+)` \|[^|]*\|[^|]*\| 4\b", section, re.M)


def _routed() -> set[str]:
    """Every operation id a route declares: a literal, or a module constant
    the decorator names (`operation_id=RUN`)."""
    found: set[str] = set()
    for path in (ROOT / "src" / "turab" / "api" / "routes").glob("*.py"):
        source = path.read_text()
        found.update(re.findall(r'operation_id="([A-Za-z]+)"', source))
        for const in re.findall(r"operation_id=([A-Z_]+)\b", source):
            found.update(re.findall(rf'^{const} = "([A-Za-z]+)"$', source, re.M))
    return found


def _writers(table: str) -> list[str]:
    pattern = re.compile(rf"INSERT\s+INTO\s+turab\.{table}\b")
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")
                  if pattern.search(p.read_text()))


def render(results: dict[str, str], properties: dict[str, dict[str, str]],
           junit: pathlib.Path) -> tuple[str, list[str]]:
    problems: list[str] = []
    bound = junit == DEFAULT_JUNIT.resolve()
    shown = junit.relative_to(ROOT) if junit.is_relative_to(ROOT) else junit
    out = ["# Slice 4 — STOP GATE D evidence", "",
           "**Generated** by `db/gate/stop_gate_d_evidence.py` from "
           f"`{shown}`. **Do not edit.**", "",
           "> STOP GATE D: \"A human reviewer must be able to read a candidate and "
           "reconstruct every eligibility decision without an LLM.\" "
           "(`IMPLEMENTATION_SLICES_v0.2.md`, Slice 4; plan §6.2)", ""]
    if bound:
        recorded, binding = run_binding.check(ROOT)
        binding += run_binding.recorded_fingerprint_problems(GATE_RUN, ROOT)
        problems += binding
        cases = run_binding.counted(junit)
        out += [f"- The JUnit run is recorded at commit `{recorded.get('commit')}`, source "
                f"fingerprint `{recorded.get('fingerprint')}`, report sha256 "
                f"`{recorded.get('report_sha256')}` "
                "(`docs/gate/evidence/TEST-RUN-PROVENANCE.txt`).",
                f"- Counted in the report: {cases.tests} test cases, {cases.failures} "
                f"failures, {cases.errors} errors, {cases.skipped} skipped.",
                "- Binding (`db/gate/run_binding.py`): "
                + ("the report's digest and counts are the recorded ones, and the current "
                   "tree's source fingerprint is the run's and the gate run's."
                   if not binding else "**FAILED**: " + "; ".join(binding) + ".")]
    else:
        out += ["- **UNBOUND RUN**: this report is not the committed clean-tree run, and "
                "no commit or fingerprint is claimed for it."]
        problems.append("the report is not the committed run; the document is not evidence")
    out += ["- Tests are named `module::name`.",
            "- These are our runs; nobody else has re-run them.", ""]

    out += ["## 1. The two proofs (plan §6.2)", "",
            "| Proof | Test | Re-derives | Matches checked | Status |", "|---|---|---|---|---|"]
    for proof, name, what in PROOFS:
        counts = properties.get(name, {})
        checked = counts.get("engine_matches_checked")
        if checked is None or int(checked) < 1:
            problems.append(f"{proof}: no recorded count of the matches checked")
        out.append(f"| {proof} | `{name}` | {what} | {checked} "
                   f"(of which {counts.get('matches_written_by_this_test')} written by the "
                   f"test itself; {counts.get('fixture_rows_not_engine_output')} hand-made "
                   f"fixture rows, not engine output, excluded) | "
                   f"{_status(results, name, problems, proof)} |")
    out += ["", "**Each proof can fail** (a stored decision or result altered in a copy of the "
            "rows is reported):", ""]
    out += [f"- `{n}` {_status(results, n, problems, 'non-vacuity')}" for n in NOT_VACUOUS]
    out += ["", f"**The digest each match was evaluated under (G4-19).** {DIGEST_RULE}", ""]
    out += [f"- `{n}` {_status(results, n, problems, 'G4-19')}" for n in DIGEST]
    out += ["",
            "## 2. The ten mandatory tests (plan §6.1)", "",
            "| # | Handoff wording | Test | Status |", "|---|---|---|---|"]
    notes = []
    for num, wording, narrowed, tests in MANDATORY:
        for name in tests:
            out.append(f"| {num} | {wording} | `{name}` | "
                       f"{_status(results, name, problems, 'mandatory ' + num)} |")
        if narrowed:
            notes.append(f"- **Test {num}:** {narrowed}.")
    out += ["", *notes, "", "## 3. Reference scenarios (plan §6.2)", "",
            "| Scenario | Statement | Test | Status |", "|---|---|---|---|"]
    for sid, what, tests in SCENARIOS:
        for name in tests:
            out.append(f"| {sid} | {what} | `{name}` | {_status(results, name, problems, sid)} |")
    out += ["", "M-12 belongs to Slice 6; M-07 to M-11 belong to other slices.", "",
            "## 4. Concurrency (plan §6.3)", "",
            "| Race | Serialises on | Expected | Test | Status |", "|---|---|---|---|---|"]
    for race, on, expected, tests in CONCURRENCY:
        for name in tests:
            out.append(f"| {race} | {on} | {expected} | `{name}` | "
                       f"{_status(results, name, problems, race)} |")

    ops, routed = _plan_operations(), _routed()
    missing = [o for o in ops if o not in routed]
    if len(ops) != 3:
        problems.append(f"the plan's Slice 4 operations read as {ops}, not three")
    if missing:
        problems.append(f"plan operations without a route: {missing}")
    run = "src/turab/services/matching_run.py"
    writers = {t: _writers(t) for t in ("match_candidates", "match_criterion_results",
                                        "match_diagnostic_runs", "match_reviews",
                                        "opportunities")}
    for table in ("match_candidates", "match_criterion_results", "match_diagnostic_runs"):
        if writers[table] != [run]:
            problems.append(f"{table} written by {writers[table]}, not the run alone")
    for table in ("match_reviews", "opportunities"):
        if writers[table]:
            problems.append(f"{table} written by {writers[table]}")
    migrations = sorted(p.name for p in (ROOT / "db" / "migrations" / "versions").glob("0*.py"))
    out += ["", "## 5. Acceptance conditions (plan §7): what is computed from the tree", "",
            f"- **Condition 1.** The plan names {len(ops)} Slice 4 operations "
            f"({', '.join(f'`{o}`' for o in ops)}); {len(ops) - len(missing)} have a route"
            f"{'' if not missing else '; WITHOUT: ' + ', '.join(missing)}.",
            f"- **Condition 4.** Migrations present: {', '.join(migrations)}.",
            "- **Condition 6.** Files inserting into `match_reviews`: "
            f"{writers['match_reviews'] or 'none'}; into `opportunities`: "
            f"{writers['opportunities'] or 'none'}. The three match tables are written by "
            f"{sorted({w for t in ('match_candidates', 'match_criterion_results', 'match_diagnostic_runs') for w in writers[t]})} "
            "alone."]
    for num, what, name in CONDITIONS:
        out.append(f"- **Condition {num}.** {what}: `{name}` "
                   f"{_status(results, name, problems, 'condition ' + num)}.")
    out += ["", "The remaining conditions are argued in `docs/gate/SLICE_4_STEP8_DELIVERY.md`, "
            "which this document does not replace."]
    return "\n".join(out) + "\n", problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", type=pathlib.Path, default=DEFAULT_JUNIT)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    junit = args.junit.resolve()
    results, properties = parse(junit)
    body, problems = render(results, properties, junit)
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
