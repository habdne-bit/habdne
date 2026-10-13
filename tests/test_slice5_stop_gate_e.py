"""The STOP GATE E generator refuses what is not proven, and what is no
longer bound to the tree (Slice 5 step 6, plan §6.3).

STOP GATE D's experiments, repeated for STOP GATE E on a COPY of the tree, so
the real evidence is never touched. The generator runs as a subprocess, as a
reviewer runs it, with its ROOT in the copy. The copy first holds a bound,
passing run, and `--check` must pass on that baseline, so each refusal below
comes from the experiment.

Ref: `db/gate/stop_gate_e_evidence.py`; `db/gate/run_binding.py`.
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
import stop_gate_e_evidence  # noqa: E402

REPORT = run_binding.REPORT
PROOF = stop_gate_e_evidence.PROOF
DOC = "docs/gate/SLICE_5_STOP_GATE_E.md"


def _case(qualified: str, status: str = "pass", recorded: dict | None = None) -> str:
    module, name = qualified.split("::")
    body = ""
    if qualified == PROOF:
        props = {"http_commands": "17", "approved_match_id": "m-1",
                 "transaction_type": "SALE"} if recorded is None else recorded
        body += "<properties>" + "".join(
            f'<property name="{k}" value="{v}"/>' for k, v in props.items()) + "</properties>"
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
    args = [sys.executable, str(tree / "db/gate/stop_gate_e_evidence.py")]
    return subprocess.run(args + (["--check"] if check else []), cwd=tree,
                          capture_output=True, text=True)


def _all_passing(**proof):
    return [_case(n, recorded=proof or None) if n == PROOF else _case(n)
            for n in sorted(stop_gate_e_evidence.mapped_names())]


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


def test_e_the_baseline_states_the_proof_the_limit_and_k06(tree):
    text = (tree / DOC).read_text()
    assert f"| `{PROOF}` |" in text and "| 17 | SALE | `m-1` | PASS |" in text
    assert "**Its stated limit: SALE only. G4-5R is open.**" in text
    assert "**K06 — UNPROVEN.**" in text and "(trigger-level)" in text
    assert "K06 | PASS" not in text


@pytest.mark.parametrize("victim", [
    PROOF,
    "test_slice5_step3::test_mandatory_6_two_concurrent_approvals_of_one_pair_make_one_opportunity",
    "test_slice5_step6::test_l_s5_3a_a_later_match_under_another_policy_supersedes_nothing",
    "test_slice5_step6::test_l_s5_3b_a_run_while_an_approval_is_held_waits_for_it",
    "test_slice5_step5::test_r_s5_5_01_b_a_share_waits_for_a_binding_in_flight_and_reads_it",
])
def test_e_a_mapped_test_that_is_absent_is_a_problem(tree, victim):
    cases = [c for n, c in zip(sorted(stop_gate_e_evidence.mapped_names()), _all_passing())
             if n != victim]
    r = _regenerated_with(tree, cases)
    assert r.returncode == 1 and f"{victim} is MISSING" in r.stderr


def test_e_a_mapped_test_that_failed_is_a_problem(tree):
    victim = "test_slice5_step4::test_no_private_value_reaches_the_customer_at_any_scope"
    cases = [_case(n, "fail" if n == victim else "pass")
             if n != PROOF else _case(n) for n in sorted(stop_gate_e_evidence.mapped_names())]
    r = _regenerated_with(tree, cases, failures=1)
    assert r.returncode == 1 and f"{victim} is FAIL" in r.stderr


def test_e_the_same_name_in_another_module_does_not_count(tree):
    victim = "test_slice5_step6::test_e04_consolidation_with_two_real_open_opportunities_surfaces_work_and_closes_none"
    names = sorted(stop_gate_e_evidence.mapped_names() - {victim})
    cases = [_case(n) for n in names] + [_case(
        "test_slice5_step5::test_e04_consolidation_with_two_real_open_opportunities_surfaces_work_and_closes_none")]
    r = _regenerated_with(tree, cases)
    assert r.returncode == 1 and f"{victim} is MISSING" in r.stderr


def test_e_a_proof_without_its_recorded_properties_is_a_problem(tree):
    r = _regenerated_with(tree, _all_passing(nothing="recorded"))
    assert r.returncode == 1 and "no recorded count of its HTTP commands" in r.stderr


def test_e_a_proof_of_another_transaction_type_is_a_problem(tree):
    r = _regenerated_with(tree, _all_passing(http_commands="17", transaction_type="RENT"))
    assert r.returncode == 1 and "transaction type 'RENT', not SALE" in r.stderr


def test_e_a_source_change_after_the_run_is_refused(tree):
    path = tree / "src/turab/services/opportunity_commands.py"
    path.write_text(path.read_text() + "\n# changed after the run\n")
    r = _gen(tree)
    assert r.returncode == 1 and "fingerprint" in r.stderr


def test_e_a_stale_document_is_a_problem(tree):
    doc = tree / DOC
    doc.write_text(doc.read_text() + "edited by hand\n")
    r = _gen(tree)
    assert r.returncode == 1 and "is stale" in r.stderr


@pytest.mark.parametrize("table", ["opportunities", "match_reviews", "interactions"])
def test_e_a_new_writer_is_a_problem(tree, table):
    """Plan §6.3 and G5-8 (i): a file inserting into one of these tables, other
    than its approved writer, is a problem (the run is re-bound, so the
    writer is the only change)."""
    path = tree / "src/turab/services/writer_probe.py"
    path.write_text(f'SQL = "INSERT INTO turab.{table} (x) VALUES (NULL)"\n')
    r = _regenerated_with(tree, _all_passing())
    assert r.returncode == 1 and f"{table} written by" in r.stderr


def test_e_a_general_opportunity_create_is_a_problem(tree):
    path = tree / "src/turab/api/routes/probe_create.py"
    path.write_text('@router.post("/opportunities", operation_id="probe")\ndef f(): pass\n')
    r = _regenerated_with(tree, _all_passing())
    assert r.returncode == 1 and "a general POST /opportunities is routed" in r.stderr


def test_e_an_unbound_report_is_not_evidence(tree, tmp_path):
    other = tmp_path / "other.xml"
    other.write_text(_report(_all_passing()))
    r = subprocess.run([sys.executable, str(tree / "db/gate/stop_gate_e_evidence.py"),
                        "--junit", str(other), "--check"], cwd=tree, capture_output=True,
                       text=True)
    assert r.returncode == 1 and "not the committed run" in r.stderr
