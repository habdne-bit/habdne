"""The STOP GATE C `--check` refuses a report that is no longer bound to the
tree it is presented for. Review of d0d58c3.

The reviewer ran two experiments on the delivered bundle, and `--check`
exited 0 on both:
1. a failing case, listed nowhere, appended to the saved JUnit report (1281
   cases, 1 failure), while the document still showed "1280, 0 failures",
   copied from the provenance record;
2. `FOR SHARE` changed to `FOR KEY SHARE` in `services/identity.py`, which
   changes the source fingerprint.

Both are repeated here on a COPY of the tree, so the real evidence is never
touched. The generator runs as a subprocess, exactly as a reviewer runs it,
with its ROOT in the copy. The copy is first given a bound, passing run, and
`--check` must pass on that baseline, so each refusal below comes from the
experiment and not from the setup.

Ref: `db/gate/run_binding.py`; `db/gate/stop_gate_c_evidence.py`.
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
import stop_gate_c_evidence  # noqa: E402

REPORT = run_binding.REPORT
LOCK = "WHERE property_id = ANY(:ids) ORDER BY property_id FOR SHARE"


def _synthetic_report(names) -> str:
    cases = "".join(f'<testcase classname="tests.synthetic" name="{n}" time="0.01"/>'
                    for n in sorted(names))
    return ('<?xml version="1.0" encoding="utf-8"?><testsuites>'
            f'<testsuite name="pytest" errors="0" failures="0" skipped="0" '
            f'tests="{len(names)}" time="1.000" timestamp="2026-01-01T00:00:00+00:00" '
            f'hostname="test">{cases}</testsuite></testsuites>')


def _check(tree: pathlib.Path, write: bool = False) -> subprocess.CompletedProcess:
    args = [sys.executable, str(tree / "db/gate/stop_gate_c_evidence.py")]
    return subprocess.run(args if write else args + ["--check"], cwd=tree,
                          capture_output=True, text=True)


@pytest.fixture
def tree(tmp_path) -> pathlib.Path:
    """A copy of the tree holding a bound, passing run, and the document
    generated from it."""
    copy = tmp_path / "tree"
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache")
    for d in ("src", "tests", "db", "docs/gate"):
        shutil.copytree(ROOT / d, copy / d, ignore=ignore)
    shutil.copy(ROOT / "alembic.ini", copy / "alembic.ini")
    (copy / REPORT).write_text(_synthetic_report(stop_gate_c_evidence.mapped_names()))
    source = run_binding.fingerprint(copy)
    (copy / run_binding.PROVENANCE).write_text(run_binding.provenance_text(
        recorded="2026-01-01 00:00:00 UTC", commit="0" * 40, source_fingerprint=source,
        report=copy / REPORT, report_name=REPORT.as_posix()))
    gate = copy / "docs/gate/evidence/gate-run.txt"
    gate.write_text(re.sub(r"(Source fingerprint \(db/dev/source_fingerprint\.py\):\n\s+)[0-9a-f]{64}",
                           lambda m: m.group(1) + source, gate.read_text()))
    written = _check(copy, write=True)
    assert written.returncode == 0, written.stderr
    baseline = _check(copy)
    assert baseline.returncode == 0, f"the baseline must pass: {baseline.stderr}"
    return copy


def test_a_failing_case_appended_to_the_saved_report_is_refused(tree):
    """Experiment 1: one failing case, listed nowhere, with the suite totals
    edited to match it (1 more case, 1 failure)."""
    report = tree / REPORT
    before = run_binding.counted(report)
    body = report.read_text()
    body = body.replace(f'failures="0" skipped="0" tests="{before.tests}"',
                        f'failures="1" skipped="0" tests="{before.tests + 1}"')
    body = body.replace("</testsuite>", '<testcase classname="tests.x" name="test_unlisted" '
                        'time="0.01"><failure message="boom">boom</failure></testcase>'
                        "</testsuite>")
    report.write_text(body)
    assert run_binding.counted(report) == run_binding.declared(report) \
        == run_binding.Counts(before.tests + 1, 1, 0, 0)

    r = _check(tree)
    assert r.returncode == 1
    problems = r.stderr
    assert "the report's sha256 is" in problems and "not the report of that run" in problems
    assert (f"the report holds tests={before.tests + 1} failures=1 errors=0 skipped=0; "
            f"the run recorded tests={before.tests} failures=0") in problems
    assert "the report has 1 failed and 0 errored cases" in problems
    # The regenerated document states what the report holds, not the record.
    _check(tree, write=True)
    document = (tree / "docs/gate/SLICE_3_STOP_GATE_C.md").read_text()
    assert f"Counted in the report: {before.tests + 1} test cases, 1 failures" in document
    assert "**FAILED**" in document


def test_a_source_change_after_the_run_is_refused(tree):
    """Experiment 2: `FOR SHARE` -> `FOR KEY SHARE` in generation's lock. The
    report and its record are untouched; only the tree they are presented
    for has changed."""
    identity = tree / "src/turab/services/identity.py"
    text = identity.read_text()
    assert text.count(LOCK) == 1
    identity.write_text(text.replace(LOCK, LOCK.replace("FOR SHARE", "FOR KEY SHARE")))

    r = _check(tree)
    assert r.returncode == 1
    assert "the current tree's source fingerprint is" in r.stderr
    assert "the report is not evidence for this tree" in r.stderr
    assert "gate-run.txt was recorded on source fingerprint" in r.stderr
    assert "sha256" not in r.stderr, "the report itself was not touched"


def test_a_report_whose_totals_disagree_with_its_cases_is_refused(tree):
    """The report's own `<testsuite>` totals are not trusted either: a
    failure element added without touching the totals is counted."""
    report = tree / REPORT
    body = report.read_text()
    first = re.search(r'<testcase [^>]*/>', body).group(0)
    report.write_text(body.replace(first, first[:-2] + '><failure message="x">x</failure>'
                                                      "</testcase>", 1))
    r = _check(tree)
    assert r.returncode == 1
    assert "the report's totals say" in r.stderr and "failures=0" in r.stderr
    assert "the report has 1 failed and 0 errored cases" in r.stderr


# --- review of 8c64c64: pytest's configuration is part of what a run is bound to ----------

def _bound_copy(tmp_path) -> pathlib.Path:
    """An isolated copy of everything the fingerprint reads, holding a bound,
    passing run; `run_binding.check` must accept it before any experiment."""
    copy = tmp_path / "bound"
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache")
    for d in ("src", "tests", "db", "relay"):
        shutil.copytree(ROOT / d, copy / d, ignore=ignore)
    for name in ("alembic.ini", "pyproject.toml"):
        shutil.copy(ROOT / name, copy / name)
    report = copy / REPORT
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(_synthetic_report(["test_one", "test_two"]))
    (copy / run_binding.PROVENANCE).write_text(run_binding.provenance_text(
        recorded="2026-01-01 00:00:00 UTC", commit="0" * 40,
        source_fingerprint=run_binding.fingerprint(copy), report=report,
        report_name=REPORT.as_posix()))
    _, problems = run_binding.check(copy)
    assert problems == [], f"the baseline must be bound: {problems}"
    return copy


@pytest.mark.parametrize("old, new", [
    ('pythonpath = ["src", "relay"]', 'pythonpath = ["src", "relay", "elsewhere"]'),
    ('pythonpath = ["src", "relay"]', 'pythonpath = ["src"]'),
    ('testpaths = ["tests"]', 'testpaths = ["tests", "relay"]'),
])
def test_a_change_to_pytests_configuration_after_the_run_is_refused(tmp_path, old, new):
    """The review of 8c64c64: `pyproject.toml`'s `pythonpath` decides whether
    the relay's tests are collected; changing it after the run must unbind the
    report."""
    copy = _bound_copy(tmp_path)
    config = copy / "pyproject.toml"
    assert config.read_text().count(old) == 1
    config.write_text(config.read_text().replace(old, new))
    _, problems = run_binding.check(copy)
    assert any("source fingerprint" in p and "not evidence for this tree" in p
               for p in problems), problems


@pytest.mark.parametrize("name", ["pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini",
                                  "tox.ini", "setup.cfg", "conftest.py"])
def test_a_pytest_configuration_file_added_after_the_run_is_refused(tmp_path, name):
    """Each file pytest reads for its configuration (its documentation lists
    them), and a root conftest.py, unbinds the report when it appears."""
    copy = _bound_copy(tmp_path)
    (copy / name).write_text("[pytest]\n" if not name.endswith(".py") else "# added\n")
    _, problems = run_binding.check(copy)
    assert any("source fingerprint" in p for p in problems), problems


def test_the_recipe_lists_pytests_configuration_files():
    sys.path.insert(0, str(ROOT / "db" / "dev"))
    import source_fingerprint

    assert {"pyproject.toml", "pytest.toml", ".pytest.toml", "pytest.ini", ".pytest.ini",
            "tox.ini", "setup.cfg", "conftest.py"} <= set(source_fingerprint.EXTRA)
    assert "relay" in source_fingerprint.TREES
    listed = {line.split("  ", 1)[1].strip() for line in source_fingerprint.lines(ROOT)}
    assert "pyproject.toml" in listed
