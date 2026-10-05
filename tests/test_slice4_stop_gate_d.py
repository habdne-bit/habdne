"""The STOP GATE D generator refuses what is not proven, and what is no
longer bound to the tree (Slice 4 step 8).

The experiments of the review of d0d58c3 (STOP GATE C) are repeated for
STOP GATE D, on a COPY of the tree, so the real evidence is never touched.
The generator runs as a subprocess, as a reviewer runs it, with its ROOT in
the copy. The copy first holds a bound, passing run, and `--check` must pass
on that baseline, so each refusal below comes from the experiment.

Ref: `db/gate/stop_gate_d_evidence.py`; `db/gate/run_binding.py`.
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
import stop_gate_d_evidence  # noqa: E402

REPORT = run_binding.REPORT
PROOFS = {name for _, name, _ in stop_gate_d_evidence.PROOFS}


def _case(qualified: str, status: str = "pass", counted: bool = True) -> str:
    module, name = qualified.split("::")
    body = ""
    if qualified in PROOFS and counted:
        body += ('<properties><property name="matches_written_by_this_test" value="8"/>'
                 '<property name="engine_matches_checked" value="101"/>'
                 '<property name="fixture_rows_not_engine_output" value="9"/></properties>')
    if status == "fail":
        body += '<failure message="boom">boom</failure>'
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
    args = [sys.executable, str(tree / "db/gate/stop_gate_d_evidence.py")]
    return subprocess.run(args + (["--check"] if check else []), cwd=tree,
                          capture_output=True, text=True)


@pytest.fixture
def tree(tmp_path) -> pathlib.Path:
    copy = tmp_path / "tree"
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache")
    for d in ("src", "tests", "db", "docs/gate"):
        shutil.copytree(ROOT / d, copy / d, ignore=ignore)
    shutil.copy(ROOT / "alembic.ini", copy / "alembic.ini")
    _bind(copy, _report([_case(n) for n in sorted(stop_gate_d_evidence.mapped_names())]))
    written = _gen(copy, check=False)
    assert written.returncode == 0, written.stderr
    baseline = _gen(copy)
    assert baseline.returncode == 0, f"the baseline must pass: {baseline.stderr}"
    return copy


def _regenerated_with(tree, cases, failures=0):
    _bind(tree, _report(cases, failures))
    _gen(tree, check=False)
    return _gen(tree)


def test_the_baseline_names_the_counts_the_run_recorded(tree):
    text = (tree / "docs/gate/SLICE_4_STOP_GATE_D.md").read_text()
    assert "| 101 (of which 8 written by the test itself; 9 hand-made fixture rows" in text
    assert "The digest each match was evaluated under (G4-19)." in text
    assert "is never substituted" in text


@pytest.mark.parametrize("victim", [
    "test_slice4_step8::test_every_stored_match_is_reconstructed_from_its_rows_alone",
    "test_slice4_step8::test_an_alias_is_never_a_candidate",
    "test_slice4_step7::test_two_identical_runs_race_and_store_one_match",
])
def test_a_mapped_test_that_is_absent_is_a_problem(tree, victim):
    names = sorted(stop_gate_d_evidence.mapped_names() - {victim})
    r = _regenerated_with(tree, [_case(n) for n in names])
    assert r.returncode == 1 and f"{victim} is MISSING" in r.stderr


def test_a_mapped_test_that_failed_is_a_problem(tree):
    victim = "test_slice4_step8::test_negotiable_above_max_is_unknown_not_pass"
    cases = [_case(n, "fail" if n == victim else "pass")
             for n in sorted(stop_gate_d_evidence.mapped_names())]
    r = _regenerated_with(tree, cases, failures=1)
    assert r.returncode == 1 and f"{victim} is FAIL" in r.stderr


def test_the_same_name_in_another_module_does_not_count(tree):
    """A planned name passing in the wrong module is not the mapped test:
    the key is module::name."""
    victim = "test_slice4_step8::test_a_hard_fail_is_rejected_whatever_the_soft_score"
    names = sorted(stop_gate_d_evidence.mapped_names() - {victim})
    cases = [_case(n) for n in names] + [
        _case("test_slice4_step6::test_a_hard_fail_is_rejected_whatever_the_soft_score")]
    r = _regenerated_with(tree, cases)
    assert r.returncode == 1 and f"{victim} is MISSING" in r.stderr


def test_a_proof_without_its_recorded_count_is_a_problem(tree):
    proof = "test_slice4_step8::test_every_stored_match_replays_its_criterion_results_and_input_hash"
    cases = [_case(n, counted=n != proof) for n in sorted(stop_gate_d_evidence.mapped_names())]
    r = _regenerated_with(tree, cases)
    assert r.returncode == 1 and "Replay: no recorded count" in r.stderr


def test_a_source_change_after_the_run_is_refused(tree):
    path = tree / "src/turab/matching/reconstruct.py"
    path.write_text(path.read_text() + "\n# changed after the run\n")
    r = _gen(tree)
    assert r.returncode == 1 and "fingerprint" in r.stderr


def test_a_new_writer_of_match_reviews_is_a_problem(tree):
    """Acceptance condition 6, computed: any file inserting into
    `match_reviews` is a problem (the binding is re-recorded, so the writer
    is the only change)."""
    path = tree / "src/turab/services/writer_probe.py"
    path.write_text('SQL = "INSERT INTO turab.match_reviews (match_id) VALUES (NULL)"\n')
    r = _regenerated_with(tree, [_case(n) for n in sorted(stop_gate_d_evidence.mapped_names())])
    assert r.returncode == 1 and "match_reviews written by" in r.stderr


def test_a_stale_document_is_a_problem(tree):
    doc = tree / "docs/gate/SLICE_4_STOP_GATE_D.md"
    doc.write_text(doc.read_text() + "edited by hand\n")
    r = _gen(tree)
    assert r.returncode == 1 and "is stale" in r.stderr
