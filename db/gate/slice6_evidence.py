#!/usr/bin/env python3
"""Generate the Slice 6 closure evidence from a real test run.

Plan: `docs/gate/SLICE_6_PLAN.md` §6.4 (revision 13). Slice 6 has no STOP
GATE; this document is **not** called one. It maps each mandatory test and
red-team case to its bound test, as STOP GATE E's generator does, and adds
what the reviews of Slice 6 asked the closure evidence to state.

As STOP GATE E's generator does, this one takes every status from a JUnit
report: by default the one committed with the clean-tree run,
`docs/gate/evidence/junit-run.xml`. Before any provenance is claimed,
`run_binding.check` must find:
- the report's digest and counted cases to be the recorded ones;
- no failed case;
- the current tree's source fingerprint to be the run's and the gate
  run's.

Any failure is a problem, and `--check` exits non-zero. Nothing in the
output is written by hand.

**Tests are named by module and name** (`test_slice6_step5::test_x`).

**It refuses when:**
- a mapped test is missing or failed, the tests of the decisions on F6-21
  and F6-22 and the limit's test included;
- the title F6-22 decided is not the one `matching_run.py` fixes for a
  CONFIRM_PRICE task on the REQUEST, or the record of the stored titles is
  absent;
- the source changed after the run, or the document is stale;
- a write to `tasks` is not one decided (plan §7 condition 10): INSERT by
  `identity.py`, `match_review.py` and `matching_run.py` only; UPDATE by
  `tasks.py` only, setting `status = 'DONE', completed_at = :at` and nothing
  else; no DELETE;
- `match_diagnostic_runs` is written other than by the run's INSERT, or
  `task_completion_events` other than by the completion's INSERT;
- a Slice 6 module writes `requests` or `request_criteria` (§3.1, I03);
- one of the two Slice 6 operations has no route;
- the three pins of step 3 are absent.

**Never PASS here:** K06 (UNPROVEN, G6-12; the refusals are listed as
trigger-level); the two stated limits (the replay and the diagnostic's own
`input_hash`; `explain.blocker_summary`, plan §5.4). The decisions on F6-21
and F6-22 (review of 3657973) are listed with the tests that hold them: the
boundary's witness for F6-21, the fix's tests for F6-22.

Usage:
  db/gate/slice6_evidence.py [--junit PATH]           # write the document
  db/gate/slice6_evidence.py [--junit PATH] --check   # fail if stale or unproven
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
OUT = ROOT / "docs" / "gate" / "SLICE_6_EVIDENCE.md"

M7, S2, S3, S4, S5 = ("test_migration_0007_task_work_and_evidence",
                      *(f"test_slice6_step{n}" for n in (2, 3, 4, 5)))

#: §6.1: (number, the handoff's wording, tests). The end-to-end test first.
MANDATORY = (
    ("1", "document UNKNOWN on otherwise exact candidate becomes higher-priority task than "
          "suggesting a new location",
     (f"{S5}::test_mandatory_1_over_http_the_document_task_outranks_the_new_location",
      f"{S3}::test_mandatory_1_the_document_unknown_ranks_above_the_location_scenario")),
    ("2", "candidate failing three hard criteria does not receive high-priority task for an "
          "unrelated unknown",
     (f"{S5}::test_mandatory_2_over_http_three_hard_failures_raise_no_task",
      f"{S3}::test_mandatory_2_a_candidate_failing_three_hard_criteria_gets_no_action",
      f"{S3}::test_mandatory_2_over_a_real_run")),
    ("3", "relaxation scenario reports magnitude (e.g. +150M centimes / adjacent area), not "
          "only 'remove criterion.'",
     (f"{S5}::test_mandatory_3_over_http_the_magnitudes_after_the_document_fails",
      f"{S3}::test_mandatory_3_the_budget_magnitude_is_1_500_000_dzd",
      f"{S3}::test_g6_6_the_location_measured_in_step_0")),
)

#: §6.2: (case, the red-team statement, tests).
RED_TEAM = (
    ("I01", "mandatory test 1",
     (f"{S5}::test_mandatory_1_over_http_the_document_task_outranks_the_new_location",)),
    ("I02", "a completion stores its outcome, note and evidence in one event and marks the "
            "task DONE, in one transaction; a failure between the two writes leaves neither",
     (f"{S2}::test_a_completion_appends_its_event_and_marks_the_task_done",
      f"{S2}::test_i02_a_failure_between_the_two_writes_leaves_neither")),
    ("I03", "a run producing +1,500,000 DZD leaves the request, its version and its criteria "
            "unchanged; an explicit criterion changes it and the next run sees it",
     (f"{S5}::test_i03_a_scenario_changes_no_request_and_an_explicit_criterion_does",)),
    ("D02 / R9.3", "an expectation between the maximum and the asking price: the magnitude is "
                   "ask − max; the expectation reaches no diagnostic, task, task list or "
                   "Slice 6 audit row; the staff match keeps it (F6-21, §6)",
     (f"{S5}::test_d02_the_expectation_reaches_no_diagnostic_task_or_slice_6_audit",
      f"{S3}::test_the_seller_expectation_is_never_stated_nor_used",
      f"{S2}::test_every_writers_task_is_listed_and_no_payload_carries_a_private_value")),
    ("K05", "a completion replayed with its key returns the first response and writes nothing",
     (f"{S2}::test_k05_a_replay_returns_the_first_response_and_writes_nothing",)),
    ("G04 / G06", "replay (G6-11); a run with no candidate writes an empty, valid format 2",
     (f"{S5}::test_g06_a_run_with_no_candidate_writes_an_empty_valid_format_2_that_replays",
      f"{S4}::test_a_row_the_run_wrote_is_format_2_and_replays",
      f"{S3}::test_g6_11_two_runs_one_reused_match_both_replay",
      f"{S3}::test_the_replay_never_reads_tasks")),
)

#: K06: listed, never PASS (G6-12; plan §6.2).
K06_TRIGGER_LEVEL = (
    f"{M7}::test_a_completion_event_cannot_be_updated",
    f"{M7}::test_a_completion_event_cannot_be_deleted",
    f"{M7}::test_a_cited_observation_cannot_be_updated",
    f"{M7}::test_a_cited_observation_cannot_be_deleted",
)

#: What each review of Slice 6 asked to be proven: (review, obligation, tests).
OBLIGATIONS = (
    ("`b6a08e7`", "OQ6-1's obligation: every diagnostic task has `request_id` and `entity`, "
                  "`id`, `gate`, `basis` non-NULL, and `source` = `\"DIAGNOSTIC\"` exactly",
     (f"{S4}::test_a_high_suggestion_raises_one_task_with_its_subject",
      f"{S4}::test_every_diagnostic_task_carries_a_complete_key")),
    ("`b6a08e7`", "the completion locks the task, then the cited observation FOR SHARE, "
                  "before its event",
     (f"{S2}::test_the_task_is_locked_before_the_observation",
      f"{S2}::test_r2a_r2c_a_change_after_the_lock_waits_and_is_refused",
      f"{S2}::test_r2b_an_update_before_the_lock_is_the_body_cited",
      f"{S2}::test_r2d_a_delete_before_the_lock_is_refused_typed_writing_nothing")),
    ("`220573a`", "the supersession of an older match, measured in the queue and at approval",
     (f"{S4}::test_an_older_match_is_superseded_in_the_queue_and_at_approval",)),
    ("`922a100`", "a real format-2 row written by the run, then replayed",
     (f"{S4}::test_a_row_the_run_wrote_is_format_2_and_replays",)),
    ("`0fae42c`", "a HIGH task shared by two candidates: `match_id` null, understood in "
                  "`GET /tasks`",
     (f"{S5}::test_a_high_task_shared_by_two_offers_names_no_match_and_is_understood",
      f"{S5}::test_a_high_task_shared_by_two_properties_names_only_the_request")),
)

#: Concurrency: (race, tests).
CONCURRENCY = (
    ("two runs raising one subject's work",
     (f"{S4}::test_g6_4_concurrent_runs_raise_one_task_and_staff_see_a_self_contained_task",
      f"{M7}::test_two_concurrent_runs_raise_one_task")),
    ("two completions of one task",
     (f"{S2}::test_a_second_concurrent_completion_waits_and_is_refused",)),
)

#: Decided in the review of 3657973: (id, decision, what holds it, tests).
DECISIONS = (
    ("F6-21", "documentary correction: §3.4 and §6.2's D02 bind what Slice 6 generates (the "
              "diagnostic, its tasks, their audit), not every output of the run; Slice 4 §3.5 "
              "keeps the expectation in the staff match's snapshot, and `API_CONTRACTS_v0.2.md` "
              "§8 forbids its serialization to public and customer DTOs",
     "the boundary's witness",
     (f"{S5}::test_f6_21_the_staff_match_keeps_the_expectation_the_boundary_witness",
      f"{S5}::test_d02_the_expectation_reaches_no_diagnostic_task_or_slice_6_audit")),
    ("F6-22", "the title by type and subject entity: CONFIRM_PRICE on the REQUEST is "
              "\"Confirm the request's maximum budget\"; on a PROPERTY_OFFER the offer's title "
              "stays; a row stored before keeps its old title, also after DONE (no path updates "
              "one); work raised again later is a new task, with the corrected title",
     "fixed (`matching_run.py`)",
     (f"{S5}::test_f6_22_the_request_tasks_title_names_the_request",
      f"{S5}::test_f6_22_an_offer_subject_keeps_the_offers_title",
      f"{S5}::test_f6_22_an_old_title_stays_after_done_and_new_work_gets_the_corrected_title",
      f"{S5}::test_a_high_task_shared_by_two_properties_names_only_the_request")),
)
#: F6-22's decided title, as `matching_run.py` must fix it.
F6_22_TITLE = ('("CONFIRM_PRICE", "REQUEST")', "Confirm the request's maximum budget")
#: The count of the tasks stored with the old title, before the fix.
STORED_TITLES = ROOT / "docs" / "gate" / "evidence" / "SLICE6-STEP5-F6-22-STORED-TITLES.txt"

#: The limit of the review of 0fae42c, measured.
REPLAY_LIMIT = f"{S5}::test_limit_the_replay_does_not_read_the_diagnostics_own_input_hash"

#: Plan §7 condition 10: the decided writes to `tasks`, by kind.
TASK_WRITES = {
    "INSERT": ["src/turab/services/identity.py", "src/turab/services/match_review.py",
               "src/turab/services/matching_run.py"],
    "UPDATE": ["src/turab/services/tasks.py"],
    "DELETE": [],
}
COMPLETION_SET = "status = 'DONE', completed_at = :at"
#: Condition 4, and the completion's one writer.
OTHER_WRITES = {
    ("INSERT", "match_diagnostic_runs"): ["src/turab/services/matching_run.py"],
    ("UPDATE", "match_diagnostic_runs"): [],
    ("DELETE", "match_diagnostic_runs"): [],
    ("INSERT", "task_completion_events"): ["src/turab/services/tasks.py"],
    ("UPDATE", "task_completion_events"): [],
    ("DELETE", "task_completion_events"): [],
}
#: §3.1, I03: the modules of Slice 6, none of which may write a request.
SLICE6_MODULES = ("src/turab/services/matching_run.py", "src/turab/services/tasks.py",
                  "src/turab/services/diagnostic_replay.py",
                  "src/turab/matching/diagnostic.py", "src/turab/matching/diagnostic_rules.py",
                  "src/turab/api/routes/tasks.py")
OPERATIONS = ("getTasks", "postTasksTaskIdComplete")
STEP3_PINS = ("diagnostic.value@1", "diagnostic.actions@1", "diagnostic.relaxation@1")


def mapped_names() -> set[str]:
    names = set(K06_TRIGGER_LEVEL) | {REPLAY_LIMIT}
    for group in (MANDATORY, RED_TEAM, OBLIGATIONS, DECISIONS):
        for *_, tests in group:
            names.update(tests)
    for _, tests in CONCURRENCY:
        names.update(tests)
    return names


def _qualified(case: ET.Element) -> str:
    module = (case.get("classname") or "").rsplit(".", 1)[-1]
    return f"{module}::{(case.get('name') or '').split('[')[0]}"


def parse(junit: pathlib.Path) -> dict[str, str]:
    """module::name -> PASS / FAIL / ERROR / SKIP. A parametrised test is PASS
    only if every case passed."""
    results: dict[str, str] = {}
    for case in ET.parse(junit).getroot().iter("testcase"):
        name = _qualified(case)
        status = "PASS"
        for child in case:
            if child.tag in ("failure", "error", "skipped"):
                status = {"failure": "FAIL", "error": "ERROR", "skipped": "SKIP"}[child.tag]
        if results.get(name, "PASS") == "PASS":
            results[name] = status
    return results


def _status(results, name, problems, where, shown="PASS"):
    status = results.get(name, "MISSING")
    if status != "PASS":
        problems.append(f"{where}: {name} is {status}")
        return f"**{status}**"
    return shown


_PATTERNS = {"INSERT": r"INSERT\s+INTO\s+turab\.{t}\b", "UPDATE": r"UPDATE\s+turab\.{t}\b",
             "DELETE": r"DELETE\s+FROM\s+turab\.{t}\b"}


def _writers(kind: str, table: str) -> list[str]:
    pattern = re.compile(_PATTERNS[kind].format(t=table))
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")
                  if pattern.search(p.read_text(encoding="utf-8")))


def _completion_sets() -> list[str]:
    source = (ROOT / "src/turab/services/tasks.py").read_text(encoding="utf-8")
    return [s.split("WHERE")[0].strip()
            for s in re.findall(r"UPDATE\s+turab\.tasks\s+SET\s+([^\n]*)", source)]


def _routed() -> set[str]:
    found: set[str] = set()
    for path in (ROOT / "src" / "turab" / "api" / "routes").glob("*.py"):
        source = path.read_text(encoding="utf-8")
        found.update(re.findall(r'operation_id="([A-Za-z]+)"', source))
        for const in re.findall(r"operation_id=([A-Z_]+)\b", source):
            found.update(re.findall(rf'^{const} = "([A-Za-z]+)"$', source, re.M))
    return found


def _pins() -> set[str]:
    source = (ROOT / "src/turab/matching/rule_pins.py").read_text(encoding="utf-8")
    return set(re.findall(r"^\s+'([a-z_.]+@\d+)':", source, re.M))


def render(results: dict[str, str], junit: pathlib.Path) -> tuple[str, list[str]]:
    problems: list[str] = []
    bound = junit == DEFAULT_JUNIT.resolve()
    shown = junit.relative_to(ROOT) if junit.is_relative_to(ROOT) else junit
    out = ["# Slice 6 — closure evidence", "",
           "**Generated** by `db/gate/slice6_evidence.py` from "
           f"`{shown}`. **Do not edit.**", "",
           "> Slice 6, Match Diagnostic / Information Work (plan §6.4). **Not a STOP "
           "GATE.** **Its stated limits: SALE only (G4-5R open); K06 UNPROVEN; the two "
           "limits of §5 below.**", ""]
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
            "- These are our runs; nobody else has re-run them.", "",
            "## 1. The three mandatory tests (plan §6.1)", "",
            "The end-to-end test (`test_slice6_step5`, every business row made over HTTP) "
            "is listed first; the function-level tests of step 3 follow.", "",
            "| # | Handoff wording | Test | Status |", "|---|---|---|---|"]
    for num, wording, tests in MANDATORY:
        for name in tests:
            out.append(f"| {num} | {wording} | `{name}` | "
                       f"{_status(results, name, problems, 'mandatory ' + num)} |")
    out += ["", "## 2. Red-team cases (plan §6.2)", "",
            "| Case | Statement | Test | Status |", "|---|---|---|---|"]
    for case, what, tests in RED_TEAM:
        for name in tests:
            out.append(f"| {case} | {what} | `{name}` | {_status(results, name, problems, case)} |")
    out += ["", "**K06 — UNPROVEN** (G6-12). The application role is a superuser and owns "
            "every table (EN-02). The refusals below are trigger-level, and are never "
            "counted as K06:", ""]
    out += [f"- `{n}` {_status(results, n, problems, 'trigger-level', 'passes')} "
            "(trigger-level)" for n in K06_TRIGGER_LEVEL]
    out += ["", "## 3. What the reviews of Slice 6 asked to be proven", "",
            "| Review | Obligation | Test | Status |", "|---|---|---|---|"]
    for review, what, tests in OBLIGATIONS:
        for name in tests:
            out.append(f"| {review} | {what} | `{name}` | "
                       f"{_status(results, name, problems, 'review ' + review)} |")
    out += ["", "## 4. Concurrency", "", "| Race | Test | Status |", "|---|---|---|"]
    for race, tests in CONCURRENCY:
        for name in tests:
            out.append(f"| {race} | `{name}` | {_status(results, name, problems, race)} |")

    pins = _pins()
    missing_pins = [p for p in STEP3_PINS if p not in pins]
    if missing_pins:
        problems.append(f"the pins of step 3 are absent: {missing_pins}")
    summary_pinned = sorted(p for p in pins if "blocker_summary" in p)
    out += ["", "## 5. Two stated limits (never PASS)", "",
            "**5.1 The replay does not recompute the diagnostic's own `input_hash`** "
            "(review of `0fae42c`; plan §5.4). The replay of G6-11 verifies the matches it "
            "names (R) and recomputes the decisions (D). It does not recompute the "
            "diagnostic row's `input_hash` (`turab.diagnostic-input/2`), nor compare it "
            "with the stored value. **A replay of `{\"R\": [], \"D\": []}` is not a proof "
            "that every input of that hash is sound.** Measured, as a limit:", "",
            f"- `{REPLAY_LIMIT}` "
            f"{_status(results, REPLAY_LIMIT, problems, 'the limit', 'measured')} (LIMIT)", "",
            "**5.2 `explain.blocker_summary` is not pinned** (review of `922a100`; plan "
            "§5.4). `by_reason`, `candidates_evaluated` and the summary's base come from "
            "Slice 4's format-1 builder. Computed from `src/turab/matching/rule_pins.py`: "
            f"the pins of step 3 ({', '.join(f'`{p}`' for p in STEP3_PINS)}) are "
            + ("present" if not missing_pins else "**ABSENT**")
            + "; a pin naming `blocker_summary`: "
            + (", ".join(f"`{p}`" for p in summary_pinned) if summary_pinned else "none")
            + ". The three pins do not cover it. A change of its output makes an old "
            "row fail (D), loudly; that failure is **not** a proof that the old row can be "
            "replayed. Before any later change of it that affects the summary: keep the "
            "historical computation (or a version of it), and test the replay of an old "
            "row and of a new row.", "",
            "## 6. Findings decided in the review of `3657973`", "",
            "| Finding | Decision | Held by | Test | Status |", "|---|---|---|---|---|"]
    for fid, decision, held, tests in DECISIONS:
        for name in tests:
            out.append(f"| {fid} | {decision} | {held} | `{name}` | "
                       f"{_status(results, name, problems, fid)} |")
    run_source = (ROOT / "src/turab/services/matching_run.py").read_text(encoding="utf-8")
    key, title = F6_22_TITLE
    fixed = re.search(rf'^\s+{re.escape(key)}: "{re.escape(title)}",$', run_source, re.M)
    if not fixed:
        problems.append(f"F6-22: matching_run.py does not fix {title!r} for {key}")
    out += ["", f"- **F6-22, computed from the tree:** `matching_run.py` fixes `{key}` → "
            + (f"\"{title}\"." if fixed else "**NOT the decided title**.")]
    if STORED_TITLES.exists():
        record = STORED_TITLES.read_text(encoding="utf-8")
        after = record[record.find("== AFTER"):record.find("READING")]
        stored = [line.strip() for line in after.splitlines()
                  if line.strip().startswith("CONFIRM_PRICE | REQUEST |")]
        out += ["- **F6-22, the tasks stored with the old title before the fix** "
                f"(`{STORED_TITLES.relative_to(ROOT)}`): "
                + ("; ".join(f"`{line}`" for line in stored) or "none")
                + ". Test data of the suite's database, dropped at its next session; no "
                "path updates a title, so such a row keeps its old title, also after "
                "it is DONE; a later run that raises the work again creates a new row "
                "with the corrected title "
                "(`test_f6_22_an_old_title_stays_after_done_and_new_work_gets_the_corrected_title`)."]
    else:
        problems.append(f"F6-22: the record {STORED_TITLES.relative_to(ROOT)} is absent")

    ops = _routed()
    missing_ops = [o for o in OPERATIONS if o not in ops]
    if missing_ops:
        problems.append(f"Slice 6 operations without a route: {missing_ops}")
    out += ["", "## 7. The writes, computed from the tree (plan §7)", "",
            "**Condition 10, the writes to `tasks` by kind:**", "",
            "| Kind | Decided | Found | |", "|---|---|---|---|"]
    for kind, approved in TASK_WRITES.items():
        found = _writers(kind, "tasks")
        if found != approved:
            problems.append(f"tasks {kind} by {found}, not {approved}")
        out.append(f"| {kind} | {', '.join(f'`{f}`' for f in approved) or 'none'} | "
                   f"{', '.join(f'`{f}`' for f in found) or 'none'} | "
                   f"{'as decided' if found == approved else '**NOT DECIDED**'} |")
    sets = _completion_sets()
    if sets != [COMPLETION_SET]:
        problems.append(f"the completion's UPDATE sets {sets}, not [{COMPLETION_SET!r}]")
    out += ["", f"- The completion's one UPDATE sets: "
            f"{'; '.join(f'`{s}`' for s in sets) or 'nothing found'} "
            f"({'as decided' if sets == [COMPLETION_SET] else '**NOT DECIDED**'}). "
            "`tasks.py` is in the inventory.", "",
            "**Condition 4 and the completion's events:**", "",
            "| Kind | Table | Decided | Found |", "|---|---|---|---|"]
    for (kind, table), approved in OTHER_WRITES.items():
        found = _writers(kind, table)
        if found != approved:
            problems.append(f"{table} {kind} by {found}, not {approved}")
        out.append(f"| {kind} | `{table}` | {', '.join(f'`{f}`' for f in approved) or 'none'} "
                   f"| {', '.join(f'`{f}`' for f in found) or 'none'} |")
    request_writers = sorted({f for kind in _PATTERNS for t in ("requests", "request_criteria")
                              for f in _writers(kind, t)})
    slice6_writing = [f for f in request_writers if f in SLICE6_MODULES]
    if slice6_writing:
        problems.append(f"a Slice 6 module writes a request: {slice6_writing}")
    out += ["", "**Condition 2 (§3.1, I03).** Files writing `requests` or `request_criteria`: "
            f"{', '.join(f'`{f}`' for f in request_writers) or 'none'}. Of the Slice 6 "
            f"modules: {', '.join(f'`{f}`' for f in slice6_writing) or 'none'}.", "",
            "**The operations.** "
            + ", ".join(f"`{o}`" + (" routed" if o in ops else " **NOT ROUTED**")
                        for o in OPERATIONS) + ".", "",
            "## 8. Carried, unchanged", "",
            "- **OQ6-1** (a CHECK on the diagnostic payload) and **OQ6-2** (an index on "
            "`task_completion_events.evidence_observation_id`) stay **open**; neither is a "
            "licence to change the schema. OQ6-1's obligation is proven by test (§3).",
            "- **K06 UNPROVEN** (§2). **G4-5R open:** the proof's scope is SALE only.",
            "- The remaining conditions are argued in `docs/gate/SLICE_6_STEP5_DELIVERY.md`, "
            "which this document does not replace."]
    return "\n".join(out) + "\n", problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--junit", type=pathlib.Path, default=DEFAULT_JUNIT)
    ap.add_argument("--check", action="store_true")
    args = ap.parse_args()
    junit = args.junit.resolve()
    body, problems = render(parse(junit), junit)
    if args.check:
        current = OUT.read_text(encoding="utf-8") if OUT.exists() else ""
        if current != body:
            problems.append(f"{OUT.relative_to(ROOT)} is stale; regenerate it")
    else:
        OUT.write_text(body, encoding="utf-8")
        print(f"wrote {OUT}")
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
