#!/usr/bin/env python3
"""Generate the Slice 5 STOP GATE E evidence from a real test run.

STOP GATE E (`IMPLEMENTATION_SLICES_v0.2.md`, Slice 5). Plan:
`docs/gate/SLICE_5_PLAN.md` §6.3. STOP GATE D stays bound to the Slice 4
run and is not regenerated in Slice 5 (review of f5a9d88); this is the
document bound to Slice 5's own run.

As STOP GATE C's and D's generators do, this one takes every status from a
JUnit report: by default the one committed with the clean-tree run,
`docs/gate/evidence/junit-run.xml`. Before any provenance is claimed,
`run_binding.check` must find:
- the report's digest and counted cases to be the recorded ones;
- no failed case;
- the current tree's source fingerprint to be the run's and the gate
  run's.

Any failure is a problem, and `--check` exits non-zero. Nothing in the
output is written by hand.

**Tests are named by module and name** (`test_slice5_step3::test_x`).

**It refuses (plan §6.3) when:**
- a mapped test is missing or failed;
- the source changed after the run;
- the document is stale;
- an unapproved writer of `opportunities` or `match_reviews` exists;
- an unapproved writer of `interactions` exists (G5-8 (i), review of
  6c6e614).

It also refuses:
- when the proof's recorded properties are absent, or name another
  transaction type than SALE;
- when a Slice 5 operation of the plan has no route;
- when a general `POST /opportunities` is routed (H03).

**K06 is never PASS here** (plan §7, condition 9c; G5-13 (b)(ii)). The
trigger-level refusals are listed as trigger-level.

Usage:
  db/gate/stop_gate_e_evidence.py [--junit PATH]           # write the document
  db/gate/stop_gate_e_evidence.py [--junit PATH] --check   # fail if stale or unproven
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
OUT = ROOT / "docs" / "gate" / "SLICE_5_STOP_GATE_E.md"

S1, S2, S3, S4, S5, S6 = ("test_migration_0006_opportunity_history",
                          *(f"test_slice5_step{n}" for n in (2, 3, 4, 5, 6)))

#: §6.3: the one proof, over HTTP only.
PROOF = f"{S6}::test_stop_gate_e_a_sale_from_a_new_party_to_the_customer_view_over_http"
PROOF_WHAT = ("a seller party and its consent grant, the buyer's request and criterion "
              "(ACTIVE, confirmed), a property confirmed AVAILABLE, its SALE offer made ACTIVE "
              "and confirmed, the consent bound to the offer, the run (one ELIGIBLE match), the "
              "APPROVED review, the share, the internal read and the customer's read; then STOP "
              "GATE D's reconstruction and replay of the very match approved, with no problem")

#: §6.1: (number, the handoff's wording, tests).
MANDATORY = (
    ("1", "`NEED_MORE_INFORMATION → APPROVED` preserves both decisions",
     (f"{S3}::test_mandatory_1_nmi_then_approved_keeps_both_decisions",
      f"{S3}::test_mandatory_1_across_matches_of_one_pair")),
    ("2", "approval fails if any required gate is not PASS",
     (f"{S3}::test_mandatory_2_a_gate_not_pass_is_refused_before_any_write",
      f"{S3}::test_mandatory_2_the_schema_refuses_the_same_when_the_service_check_is_bypassed")),
    ("3", "Opportunity cannot be created through a generic endpoint",
     (f"{S3}::test_mandatory_3_there_is_no_generic_opportunity_creation",
      f"{S3}::test_the_approved_review_is_the_one_writer_of_opportunities")),
    ("4", "initial offer context equals evaluated match offer when an offer exists",
     (f"{S3}::test_approved_creates_one_opportunity_with_the_decided_content",
      f"{S3}::test_mandatory_4_the_schema_refuses_another_initial_offer")),
    ("5", "customer Opportunity never reveals private seller expectation/claims",
     (f"{S4}::test_no_private_value_reaches_the_customer_at_any_scope",
      f"{S4}::test_the_customer_body_is_the_frozen_type_at_each_scope",
      f"{S4}::test_a_budget_decided_by_the_expectation_leaves_no_trace",
      f"{S4}::test_a_claim_behind_the_document_changes_nothing_the_customer_sees",
      f"{S4}::test_a_claim_behind_the_rooms_changes_nothing_the_customer_sees",
      f"{S4}::test_free_location_text_never_reaches_the_customer")),
    ("6", "same Request + same canonical Property cannot have two open Opportunities",
     (f"{S3}::test_mandatory_6_a_second_offers_match_is_refused_while_one_is_open",
      f"{S3}::test_mandatory_6_two_concurrent_approvals_of_one_pair_make_one_opportunity",
      f"{S3}::test_mandatory_6_an_open_opportunity_on_an_alias_blocks_its_canonical",
      f"{S3}::test_mandatory_6_a_match_on_a_property_that_is_now_an_alias_is_refused",
      f"{S3}::test_mandatory_6_the_index_backstop_maps_to_the_same_refusal",
      f"{S5}::test_mandatory_6_the_real_close_frees_the_pair")),
)

#: §6.2: (case, the red-team statement, tests).
RED_TEAM = (
    ("B03, H05", "revoked consent after approval: the share is refused, the snapshot unchanged",
     (f"{S5}::test_b03_h05_a_share_after_a_revocation_is_refused_and_changes_nothing",)),
    ("H01", "review history: NMI then APPROVED, both rows remain",
     (f"{S3}::test_mandatory_1_nmi_then_approved_keeps_both_decisions",)),
    ("H02", "approval gate", (f"{S3}::test_mandatory_2_a_gate_not_pass_is_refused_before_any_write",)),
    ("H03", "no general opportunity create",
     (f"{S3}::test_mandatory_3_there_is_no_generic_opportunity_creation",)),
    ("H04", "one open opportunity per pair",
     (f"{S3}::test_mandatory_6_a_second_offers_match_is_refused_while_one_is_open",)),
    ("E04", "identity consolidation with open opportunities surfaces work and closes nothing",
     (f"{S6}::test_e04_consolidation_with_two_real_open_opportunities_surfaces_work_and_closes_none",
      "test_slice3_identity::test_e04_a_duplicate_open_opportunity_is_surfaced_not_closed")),
    ("K05", "idempotency replay of each Slice 5 POST; another body on the key is 409",
     (f"{S6}::test_k05_each_slice_5_post_replays_and_a_changed_body_is_409",
      f"{S2}::test_a_same_key_review_waiting_on_the_match_lock_is_answered_by_the_key")),
)

#: K06: listed, never PASS (plan §7, condition 9c).
K06_TRIGGER_LEVEL = (
    f"{S1}::test_the_frozen_delete_guard_is_unchanged",
    f"{S6}::test_trigger_level_a_review_row_cannot_be_changed_or_deleted",
)

#: S33–S36a (RFC-001 Appendix B), on the real route.
SCENARIOS = (
    ("S33", "opportunity at SUMMARY_ONLY: the four property fields, no area",
     (f"{S4}::test_the_customer_body_is_the_frozen_type_at_each_scope",)),
    ("S34", "CONTACT_AFTER_CONFIRMATION without confirmation: no contact",
     (f"{S4}::test_the_customer_body_is_the_frozen_type_at_each_scope",
      f"{S4}::test_free_location_text_never_reaches_the_customer")),
    ("S36a", "no internal pricing, private claim, staff note or source-private data at any scope",
     (f"{S4}::test_no_private_value_reaches_the_customer_at_any_scope",)),
)

#: The limits carried to step 6 (plan §8; review of 3a60b3b): each settled.
CARRIED = (
    ("L-S5-3a", "supersession across two policies",
     "PROVEN: a later match under another policy supersedes nothing; under the same "
     "policy it does",
     (f"{S6}::test_l_s5_3a_a_later_match_under_another_policy_supersedes_nothing",
      f"{S6}::test_l_s5_3a_a_later_match_under_the_same_policy_still_supersedes")),
    ("L-S5-3b", "a run committing between the approval's supersession check and its commit",
     "MEASURED, then CLOSED by the approval's `FOR UPDATE` on the request: a run waits for a "
     "held approval; an approval waits for a run in flight and is refused as superseded",
     (f"{S6}::test_l_s5_3b_a_run_while_an_approval_is_held_waits_for_it",
      f"{S6}::test_l_s5_3b_an_approval_waits_for_a_run_in_flight_and_is_refused_superseded")),
)

#: Concurrency (§3.1, §3.3, R-S5-5-01, L-S5-3b): (race, tests).
CONCURRENCY = (
    ("two reviews of one match", (f"{S2}::test_a5_the_waiting_review_committed_last_is_the_latest",
                                  f"{S2}::test_a3_twenty_sequences_end_with_the_last_decision")),
    ("two approvals of one pair",
     (f"{S3}::test_mandatory_6_two_concurrent_approvals_of_one_pair_make_one_opportunity",)),
    ("an approval and a writer of a fact",
     (f"{S3}::test_a_fact_being_changed_is_waited_for_and_read_after_its_commit",)),
    ("a share and a consent binding (R-S5-5-01)",
     (f"{S5}::test_r_s5_5_01_a_binding_created_while_a_share_is_held_waits_for_it",
      f"{S5}::test_r_s5_5_01_b_a_share_waits_for_a_binding_in_flight_and_reads_it")),
    ("a share and its neighbours (run, approval, share)",
     (f"{S5}::test_a_matching_run_on_the_property_waits_for_a_held_share_and_completes",
      f"{S5}::test_an_approval_on_the_same_property_waits_for_a_held_share_and_both_succeed",
      f"{S5}::test_two_shares_on_one_property_serialize_and_both_succeed")),
    ("a close and a holder of the opportunity",
     (f"{S5}::test_a_close_waits_for_a_command_holding_the_opportunity_and_reads_its_result",)),
    ("a revalidate and a writer of the request",
     (f"{S6}::test_a_revalidate_waits_for_a_request_writer_and_reads_its_commit",)),
)

#: The approved writers (plan §7, conditions 3 and 4; G5-8 (i)).
APPROVED_WRITERS = {
    "opportunities": ["src/turab/services/match_review.py"],
    "match_reviews": ["src/turab/services/match_review.py"],
    "interactions": ["src/turab/services/opportunity_commands.py"],
}


def mapped_names() -> set[str]:
    names = {PROOF} | set(K06_TRIGGER_LEVEL)
    for group in (MANDATORY, RED_TEAM, SCENARIOS):
        for *_, tests in group:
            names.update(tests)
    for *_, tests in CARRIED:
        names.update(tests)
    for _, tests in CONCURRENCY:
        names.update(tests)
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
    """The operations plan §1 assigns to Slice 5 (bold **5**)."""
    text = (ROOT / "docs" / "gate" / "SLICE_5_PLAN.md").read_text(encoding="utf-8")
    section = text[text.index("## 1. Operations"):text.index("## 2. What the schema")]
    return re.findall(r"^\| `([A-Za-z]+)` \|[^|]*\|[^|]*\| \*\*5\*\*", section, re.M)


def _routes() -> tuple[set[str], set[tuple[str, str]]]:
    """Every operation id a route declares (a literal, or a module constant the
    decorator names), and every (method, path) routed."""
    found: set[str] = set()
    paths: set[tuple[str, str]] = set()
    for path in (ROOT / "src" / "turab" / "api" / "routes").glob("*.py"):
        source = path.read_text()
        found.update(re.findall(r'operation_id="([A-Za-z]+)"', source))
        for const in re.findall(r"operation_id=([A-Z_]+)\b", source):
            found.update(re.findall(rf'^{const} = "([A-Za-z]+)"$', source, re.M))
        paths.update(re.findall(r'@router\.(get|post|patch|put|delete)\("([^"]+)"', source))
    return found, paths


def _writers(table: str) -> list[str]:
    pattern = re.compile(rf"INSERT\s+INTO\s+turab\.{table}\b")
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")
                  if pattern.search(p.read_text()))


def render(results: dict[str, str], properties: dict[str, dict[str, str]],
           junit: pathlib.Path) -> tuple[str, list[str]]:
    problems: list[str] = []
    bound = junit == DEFAULT_JUNIT.resolve()
    shown = junit.relative_to(ROOT) if junit.is_relative_to(ROOT) else junit
    out = ["# Slice 5 — STOP GATE E evidence", "",
           "**Generated** by `db/gate/stop_gate_e_evidence.py` from "
           f"`{shown}`. **Do not edit.**", "",
           "> STOP GATE E: Slice 5, human review to opportunity "
           "(`IMPLEMENTATION_SLICES_v0.2.md`, Slice 5; plan §6.3). "
           "**Its stated limit: SALE only. G4-5R is open.**", ""]
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

    recorded_props = properties.get(PROOF, {})
    commands = recorded_props.get("http_commands")
    kind = recorded_props.get("transaction_type")
    if commands is None or int(commands) < 1:
        problems.append("the proof: no recorded count of its HTTP commands")
    if kind != "SALE":
        problems.append(f"the proof: transaction type {kind!r}, not SALE")
    out += ["## 1. The proof (plan §6.3): one test, over HTTP only", "",
            "| Test | Proves | HTTP commands | Transaction | Approved match | Status |",
            "|---|---|---|---|---|---|",
            f"| `{PROOF}` | {PROOF_WHAT} | {commands} | {kind} | "
            f"`{recorded_props.get('approved_match_id')}` | "
            f"{_status(results, PROOF, problems, 'the proof')} |", "",
            "Every business row of the proof is made by the API. The seed's reference "
            "data (the location, the policy, the reason codes) and the test accounts are "
            "the only rows it does not make.", "",
            "## 2. The six mandatory tests (plan §6.1)", "",
            "| # | Handoff wording | Test | Status |", "|---|---|---|---|"]
    for num, wording, tests in MANDATORY:
        for name in tests:
            out.append(f"| {num} | {wording} | `{name}` | "
                       f"{_status(results, name, problems, 'mandatory ' + num)} |")
    out += ["", "Tests 2 and 4 each include one schema refusal with the service check "
            "bypassed, labelled as schema in its test.", "",
            "## 3. Red-team cases carried (plan §6.2)", "",
            "| Case | Statement | Test | Status |", "|---|---|---|---|"]
    for case, what, tests in RED_TEAM:
        for name in tests:
            out.append(f"| {case} | {what} | `{name}` | {_status(results, name, problems, case)} |")
    out += ["", "**K06 — UNPROVEN.** The application role is a superuser and owns every "
            "table (EN-02, G5-13). K06 needs a test under a role that is neither, which is "
            "G5-13 (b)(ii)'s separate step. The refusals below are trigger-level, and are "
            "never counted as K06:", ""]
    out += [f"- `{n}` {_status(results, n, problems, 'trigger-level')} (trigger-level)"
            for n in K06_TRIGGER_LEVEL]
    out += ["", "## 4. RFC-001 Appendix B scenarios, on the real route", "",
            "| Scenario | Statement | Test | Status |", "|---|---|---|---|"]
    for sid, what, tests in SCENARIOS:
        for name in tests:
            out.append(f"| {sid} | {what} | `{name}` | {_status(results, name, problems, sid)} |")
    out += ["", "## 5. The limits carried to step 6, settled (review of `3a60b3b`)", "",
            "| Limit | What | Settled | Test | Status |", "|---|---|---|---|---|"]
    for lid, what, settled, tests in CARRIED:
        for name in tests:
            out.append(f"| {lid} | {what} | {settled} | `{name}` | "
                       f"{_status(results, name, problems, lid)} |")
    out += ["", "## 6. Concurrency", "", "| Race | Test | Status |", "|---|---|---|"]
    for race, tests in CONCURRENCY:
        for name in tests:
            out.append(f"| {race} | `{name}` | {_status(results, name, problems, race)} |")

    ops, (routed, paths) = _plan_operations(), _routes()
    missing = [o for o in ops if o not in routed]
    if len(ops) != 8:
        problems.append(f"the plan's Slice 5 operations read as {ops}, not eight")
    if missing:
        problems.append(f"plan operations without a route: {missing}")
    general_create = ("post", "/opportunities") in paths
    if general_create:
        problems.append("a general POST /opportunities is routed (H03)")
    writers = {t: _writers(t) for t in APPROVED_WRITERS}
    for table, approved in APPROVED_WRITERS.items():
        if writers[table] != approved:
            problems.append(f"{table} written by {writers[table]}, not {approved}")
    migrations = sorted(p.name for p in (ROOT / "db" / "migrations" / "versions").glob("0*.py"))
    out += ["", "## 7. Acceptance conditions (plan §7): what is computed from the tree", "",
            f"- **The operations.** The plan assigns {len(ops)} operations to Slice 5 "
            f"({', '.join(f'`{o}`' for o in ops)}); {len(ops) - len(missing)} have a route"
            f"{'' if not missing else '; WITHOUT: ' + ', '.join(missing)}.",
            "- **Condition 3 (H03).** A general `POST /opportunities` is "
            + ("**ROUTED**." if general_create else "not routed."),
            "- **Conditions 3 and 4.** Files inserting into `opportunities`: "
            f"{writers['opportunities'] or 'none'}; into `match_reviews`: "
            f"{writers['match_reviews'] or 'none'}; into `interactions`: "
            f"{writers['interactions'] or 'none'}.",
            f"- **Condition 5.** Migrations present: {', '.join(migrations)}.",
            "- **Condition 9c.** K06 is UNPROVEN (§3).",
            "- **The limit.** SALE only: G4-5R is open, and no RENT path is claimed."]
    out += ["", "The remaining conditions are argued in "
            "`docs/gate/SLICE_5_STEP6_DELIVERY.md`, which this document does not replace."]
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
