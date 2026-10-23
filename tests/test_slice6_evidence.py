"""The Slice 6 closure-evidence generator refuses what is not proven, and what
is no longer bound to the tree (Slice 6 step 5, plan §6.4).

STOP GATE E's experiments (`tests/test_slice5_stop_gate_e.py`), repeated on a
COPY of the tree, so the real evidence is never touched. The generator runs
as a subprocess, as a reviewer runs it, with its ROOT in the copy. The copy
first holds a bound, passing run, and `--check` must pass on that baseline,
so each refusal below comes from the experiment.

Ref: `db/gate/slice6_evidence.py`; `db/gate/run_binding.py`.
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "db" / "gate"))
import run_binding  # noqa: E402
import slice6_evidence  # noqa: E402

REPORT = run_binding.REPORT
DOC = "docs/gate/SLICE_6_EVIDENCE.md"


def _case(qualified: str, status: str = "pass") -> str:
    module, name = qualified.split("::")
    body = '<failure message="boom">boom</failure>' if status == "fail" else ""
    return f'<testcase classname="tests.{module}" name="{name}" time="0.01">{body}</testcase>'


def _report(cases: list[str], failures: int = 0) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><testsuites>'
            f'<testsuite name="pytest" errors="0" failures="{failures}" skipped="0" '
            f'tests="{len(cases)}" time="1.000" timestamp="2026-01-01T00:00:00+00:00" '
            f'hostname="test">{"".join(cases)}</testsuite></testsuites>')


def _bind(copy: pathlib.Path, report: str) -> None:
    """Record `report` as the run of the copy's CURRENT tree."""
    (copy / REPORT).write_text(report)
    source = run_binding.fingerprint(copy)
    (copy / run_binding.PROVENANCE).write_text(run_binding.provenance_text(
        recorded="2026-01-01 00:00:00 UTC", commit="0" * 40, source_fingerprint=source,
        report=copy / REPORT, report_name=REPORT.as_posix()))
    gate = copy / "docs/gate/evidence/gate-run.txt"
    gate.write_text(re.sub(r"(Source fingerprint \(db/dev/source_fingerprint\.py\):\n\s+)[0-9a-f]{64}",
                           lambda m: m.group(1) + source, gate.read_text()))


def _gen(tree: pathlib.Path, check: bool = True) -> subprocess.CompletedProcess:
    args = [sys.executable, str(tree / "db/gate/slice6_evidence.py")]
    return subprocess.run(args + (["--check"] if check else []), cwd=tree,
                          capture_output=True, text=True)


def _all_passing():
    return [_case(n) for n in sorted(slice6_evidence.mapped_names())]


@pytest.fixture
def tree(tmp_path) -> pathlib.Path:
    copy = tmp_path / "tree"
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache")
    for d in ("src", "tests", "db", "docs/gate"):
        shutil.copytree(ROOT / d, copy / d, ignore=ignore)
    shutil.copy(ROOT / "alembic.ini", copy / "alembic.ini")
    _bind(copy, _report(_all_passing()))
    written = _gen(copy, check=False)
    assert written.returncode == 0, written.stderr
    baseline = _gen(copy)
    assert baseline.returncode == 0, f"the baseline must pass: {baseline.stderr}"
    return copy


def _regenerated_with(tree, cases, failures=0):
    _bind(tree, _report(cases, failures))
    _gen(tree, check=False)
    return _gen(tree)


def test_s6_the_baseline_states_the_limits_the_findings_and_k06(tree):
    text = (tree / DOC).read_text()
    assert "**Not a STOP GATE.**" in text and "SALE only (G4-5R open)" in text
    assert "**K06 — UNPROVEN** (G6-12)." in text and "(trigger-level)" in text
    assert "K06 | PASS" not in text
    assert "does not recompute the diagnostic's own `input_hash`" in text
    assert f"`{slice6_evidence.REPLAY_LIMIT}` measured (LIMIT)" in text
    assert "`explain.blocker_summary` is not pinned" in text
    assert "a pin naming `blocker_summary`: none." in text
    for fid, _, name in slice6_evidence.FINDINGS:
        assert f"| {fid} |" in text and f"`{name}` | measured |" in text
    assert "| UPDATE | `src/turab/services/tasks.py` | `src/turab/services/tasks.py` |" in text


@pytest.mark.parametrize("victim", [
    "test_slice6_step5::test_mandatory_1_over_http_the_document_task_outranks_the_new_location",
    "test_slice6_step5::test_a_high_task_shared_by_two_offers_names_no_match_and_is_understood",
    "test_slice6_step4::test_an_older_match_is_superseded_in_the_queue_and_at_approval",
    "test_slice6_step2::test_the_task_is_locked_before_the_observation",
    slice6_evidence.REPLAY_LIMIT,
    slice6_evidence.FINDINGS[0][2],
])
def test_s6_a_mapped_test_that_is_absent_is_a_problem(tree, victim):
    cases = [_case(n) for n in sorted(slice6_evidence.mapped_names()) if n != victim]
    r = _regenerated_with(tree, cases)
    assert r.returncode == 1 and f"{victim} is MISSING" in r.stderr


@pytest.mark.parametrize("victim", [
    "test_slice6_step5::test_d02_the_expectation_reaches_no_diagnostic_task_or_slice_6_audit",
    slice6_evidence.FINDINGS[1][2],
])
def test_s6_a_mapped_test_that_failed_is_a_problem(tree, victim):
    cases = [_case(n, "fail" if n == victim else "pass")
             for n in sorted(slice6_evidence.mapped_names())]
    r = _regenerated_with(tree, cases, failures=1)
    assert r.returncode == 1 and f"{victim} is FAIL" in r.stderr


def test_s6_the_same_name_in_another_module_does_not_count(tree):
    victim = "test_slice6_step5::test_i03_a_scenario_changes_no_request_and_an_explicit_criterion_does"
    cases = [_case(n) for n in sorted(slice6_evidence.mapped_names() - {victim})] + [
        _case(victim.replace("test_slice6_step5", "test_slice6_step4"))]
    r = _regenerated_with(tree, cases)
    assert r.returncode == 1 and f"{victim} is MISSING" in r.stderr


def test_s6_a_source_change_after_the_run_is_refused(tree):
    path = tree / "src/turab/services/tasks.py"
    path.write_text(path.read_text() + "\n# changed after the run\n")
    r = _gen(tree)
    assert r.returncode == 1 and "fingerprint" in r.stderr


def test_s6_a_stale_document_is_a_problem(tree):
    doc = tree / DOC
    doc.write_text(doc.read_text() + "edited by hand\n")
    r = _gen(tree)
    assert r.returncode == 1 and "is stale" in r.stderr


@pytest.mark.parametrize("sql, problem", [
    ("INSERT INTO turab.tasks (x) VALUES (NULL)", "tasks INSERT by"),
    ("UPDATE turab.tasks SET priority = 'LOW'", "tasks UPDATE by"),
    ("DELETE FROM turab.tasks WHERE true", "tasks DELETE by"),
    ("UPDATE turab.match_diagnostic_runs SET near_match_count = 0", "match_diagnostic_runs UPDATE"),
    ("INSERT INTO turab.task_completion_events (x) VALUES (NULL)",
     "task_completion_events INSERT by"),
])
def test_s6_a_write_not_decided_is_a_problem(tree, sql, problem):
    """Plan §7 conditions 4 and 10: a file writing one of these tables, other
    than its decided writer, is a problem (the run is re-bound, so the writer
    is the only change)."""
    (tree / "src/turab/services/writer_probe.py").write_text(f'SQL = "{sql}"\n')
    r = _regenerated_with(tree, _all_passing())
    assert r.returncode == 1 and problem in r.stderr


def test_s6_the_completion_setting_another_column_is_a_problem(tree):
    path = tree / "src/turab/services/tasks.py"
    source = path.read_text()
    assert source.count("SET status = 'DONE', completed_at = :at") == 1
    path.write_text(source.replace("SET status = 'DONE', completed_at = :at",
                                   "SET status = 'DONE', completed_at = :at, priority = 'LOW'"))
    r = _regenerated_with(tree, _all_passing())
    assert r.returncode == 1 and "the completion's UPDATE sets" in r.stderr


def test_s6_a_slice_6_module_writing_a_request_is_a_problem(tree):
    path = tree / "src/turab/services/matching_run.py"
    path.write_text(path.read_text() + '\nSQL = "UPDATE turab.requests SET version = 1"\n')
    r = _regenerated_with(tree, _all_passing())
    assert r.returncode == 1 and "a Slice 6 module writes a request" in r.stderr


def test_s6_an_unbound_report_is_not_evidence(tree, tmp_path):
    other = tmp_path / "other.xml"
    other.write_text(_report(_all_passing()))
    r = subprocess.run([sys.executable, str(tree / "db/gate/slice6_evidence.py"),
                        "--junit", str(other), "--check"], cwd=tree, capture_output=True,
                       text=True)
    assert r.returncode == 1 and "not the committed run" in r.stderr
