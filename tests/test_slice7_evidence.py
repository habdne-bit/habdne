"""The Slice 7 closure-evidence generator refuses what is not proven, and what
is no longer bound to the tree (Slice 7 step 5, plan §6.4, G7-19).

Slice 6's experiments (`tests/test_slice6_evidence.py`), repeated on a COPY
of the tree, so the real evidence is never touched. The generator runs as a
subprocess, as a reviewer runs it, with its ROOT in the copy. The copy first
holds a bound, passing run and an event-store sample naming that run, and
`--check` must pass on that baseline, so each refusal below comes from the
experiment.

Ref: `db/gate/slice7_evidence.py`; `db/gate/slice7_event_store_counts.py`;
`db/gate/run_binding.py`.
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
import slice7_event_store_counts  # noqa: E402
import slice7_evidence  # noqa: E402

REPORT = run_binding.REPORT
DOC = "docs/gate/SLICE_7_EVIDENCE.md"
COUNTS = "docs/gate/evidence/SLICE7-EVENT-STORE-COUNTS.txt"
RECORDED = "2026-01-01 00:00:00 UTC"


def _case(qualified: str, status: str = "pass") -> str:
    module, name = qualified.split("::")
    body = '<failure message="boom">boom</failure>' if status == "fail" else ""
    return f'<testcase classname="tests.{module}" name="{name}" time="0.01">{body}</testcase>'


def _report(cases: list[str], failures: int = 0) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><testsuites>'
            f'<testsuite name="pytest" errors="0" failures="{failures}" skipped="0" '
            f'tests="{len(cases)}" time="1.000" timestamp="2026-01-01T00:00:00+00:00" '
            f'hostname="test">{"".join(cases)}</testsuite></testsuites>')


def _sample(copy: pathlib.Path, **override) -> None:
    """The event-store sample, naming the copy's recorded run unless overridden."""
    recorded = run_binding.read_provenance((copy / run_binding.PROVENANCE).read_text())
    fields = dict(sampled_at="2026-01-01 00:00:05 UTC", run_recorded=RECORDED,
                  commit=recorded["commit"], fingerprint=recorded["fingerprint"],
                  report_sha256=recorded["report_sha256"], database="turab_authz_test",
                  counts={"RECEIVED": 1, "PROCESSED": 7, "IGNORED": 3, "FAILED": 2},
                  failed={"PROCESSING_FAILED": 2})
    fields.update(override)
    (copy / COUNTS).write_text(slice7_event_store_counts.render(**fields))


def _bind(copy: pathlib.Path, report: str) -> None:
    """Record `report` as the run of the copy's CURRENT tree, then sample it."""
    (copy / REPORT).write_text(report)
    source = run_binding.fingerprint(copy)
    (copy / run_binding.PROVENANCE).write_text(run_binding.provenance_text(
        recorded=RECORDED, commit="0" * 40, source_fingerprint=source,
        report=copy / REPORT, report_name=REPORT.as_posix()))
    gate = copy / "docs/gate/evidence/gate-run.txt"
    gate.write_text(re.sub(r"(Source fingerprint \(db/dev/source_fingerprint\.py\):\n\s+)[0-9a-f]{64}",
                           lambda m: m.group(1) + source, gate.read_text()))
    _sample(copy)


def _gen(tree: pathlib.Path, check: bool = True) -> subprocess.CompletedProcess:
    args = [sys.executable, str(tree / "db/gate/slice7_evidence.py")]
    return subprocess.run(args + (["--check"] if check else []), cwd=tree,
                          capture_output=True, text=True)


def _all_passing():
    return [_case(n) for n in sorted(slice7_evidence.mapped_names())]


@pytest.fixture
def tree(tmp_path) -> pathlib.Path:
    copy = tmp_path / "tree"
    ignore = shutil.ignore_patterns("__pycache__", ".pytest_cache")
    for d in ("src", "tests", "db", "docs/gate", "docs/contract"):
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


def _regenerated(tree):
    _gen(tree, check=False)
    return _gen(tree)


def test_s7_the_baseline_states_the_limits_and_never_passes_them(tree):
    text = (tree / DOC).read_text()
    assert "**Not a STOP GATE.**" in text and "**R-1 is UNMET" in text
    assert "**K06 UNPROVEN.**" in text and "**SALE only.**" in text
    assert "(trigger-level)" in text and "K06 | PASS" not in text
    assert "**The relay's signature proves the relay's origin, not Meta's**" in text
    assert "**Retention is not claimed** (OQ7-1)" in text
    for _, name in slice7_evidence.MEASURED_LIMITS:
        assert f"`{name}` measured (LIMIT)" in text
    limits = text.split("## 7. Limits")[1].split("## 8.")[0]
    assert "PASS" not in limits.replace("never PASS", "")
    assert "this generator reads neither" in limits
    for num, _, tests in slice7_evidence.MANDATORY:
        assert tests[0].startswith("test_slice7_step5::")
        assert f"| {num} |" in text and f"`{tests[0]}` | PASS |" in text
    for cid in slice7_evidence.APPROVED:
        assert f"**{cid}:** approved 2026-10-2" in text


def test_s7_the_sample_is_shown_as_measured_never_as_pass(tree):
    """G7-19 (i): the decided heading and wording, the bound run's identity,
    and counts only."""
    text = (tree / DOC).read_text()
    section = text.split("## 6.")[1].split("## 7.")[0]
    assert section.startswith(" The event store: a sample measured right after the run")
    assert "PASS" not in section.replace("**never a PASS**", "")
    assert "| FAILED | 2 |" in section and "| RECEIVED | 1 |" in section
    assert "`PROCESSING_FAILED` 2" in section
    assert "**No reception of a real event, and no proof of Meta's path, is claimed.**" in section
    assert "No real event" not in text and "no real event exists" not in text.lower()
    recorded = run_binding.read_provenance((tree / run_binding.PROVENANCE).read_text())
    for key in ("commit", "fingerprint", "report_sha256"):
        assert recorded[key] in section
    assert RECORDED in section and "`turab_authz_test`" in section


def test_s7_the_writes_table_names_the_insert_module_and_its_callers(tree):
    """G7-19 (ii)."""
    text = (tree / DOC).read_text()
    section = text.split("## 5.")[1].split("## 6.")[0]
    assert "**It is not a guarantee against a superuser's writes** (K06)" in section
    assert "NOT DECIDED" not in section
    assert ("| `webhook_events` | `error_text`, `processed_at`, `processing_status` | "
            "`error_text`, `processed_at`, `processing_status` |") in section
    assert ("- `message_interactions.write` (its INSERT in "
            "`src/turab/services/message_interactions.py`) is called by: "
            "`src/turab/services/communication.py`, `src/turab/services/webhooks.py`.") in section
    assert ("- `message_interactions.backfill` (its INSERT in "
            "`src/turab/services/message_interactions.py`) is called by: "
            "`db/ops/backfill_message_interactions.py`.") in section


@pytest.mark.parametrize("victim", [
    slice7_evidence.MANDATORY[0][2][1],
    slice7_evidence.MANDATORY[1][2][0],
    slice7_evidence.MANDATORY[3][2][0],
    slice7_evidence.RED_TEAM[-1][2][1],
    slice7_evidence.OBLIGATIONS[-2][2][0],
    slice7_evidence.MEASURED_LIMITS[0][1],
    slice7_evidence.K06_TRIGGER_LEVEL[0],
])
def test_s7_a_mapped_test_that_is_absent_is_a_problem(tree, victim):
    cases = [_case(n) for n in sorted(slice7_evidence.mapped_names()) if n != victim]
    r = _regenerated_with(tree, cases)
    assert r.returncode == 1 and f"{victim} is MISSING" in r.stderr


@pytest.mark.parametrize("victim", [
    slice7_evidence.RED_TEAM[2][2][0],
    slice7_evidence.MANDATORY[2][2][0],
])
def test_s7_a_mapped_test_that_failed_is_a_problem(tree, victim):
    cases = [_case(n, "fail" if n == victim else "pass")
             for n in sorted(slice7_evidence.mapped_names())]
    r = _regenerated_with(tree, cases, failures=1)
    assert r.returncode == 1 and f"{victim} is FAIL" in r.stderr


def test_s7_the_same_name_in_another_module_does_not_count(tree):
    victim = slice7_evidence.MANDATORY[0][2][0]
    cases = [_case(n) for n in sorted(slice7_evidence.mapped_names() - {victim})] + [
        _case(victim.replace("test_slice7_step5", "test_slice7_step3"))]
    r = _regenerated_with(tree, cases)
    assert r.returncode == 1 and f"{victim} is MISSING" in r.stderr


def test_s7_a_source_change_after_the_run_is_refused(tree):
    path = tree / "src/turab/services/webhooks.py"
    path.write_text(path.read_text() + "\n# changed after the run\n")
    r = _gen(tree)
    assert r.returncode == 1 and "fingerprint" in r.stderr


def test_s7_a_stale_document_is_a_problem(tree):
    doc = tree / DOC
    doc.write_text(doc.read_text() + "edited by hand\n")
    r = _gen(tree)
    assert r.returncode == 1 and "is stale" in r.stderr


@pytest.mark.parametrize("sql, problem", [
    ("INSERT INTO turab.communication_threads (x) VALUES (NULL)", "communication_threads INSERT by"),
    ("UPDATE turab.communication_threads SET last_message_at = now() WHERE true",
     "communication_threads UPDATE by"),
    ("DELETE FROM turab.communication_messages WHERE true", "communication_messages DELETE by"),
    ("INSERT INTO turab.webhook_events (x) VALUES (NULL)", "webhook_events INSERT by"),
    ("DELETE FROM turab.webhook_events WHERE true", "webhook_events DELETE by"),
    ("INSERT INTO turab.interactions (x) VALUES (NULL)", "interactions INSERT by"),
    ("UPDATE turab.interactions SET summary = '' WHERE true", "interactions UPDATE by"),
])
def test_s7_a_write_not_decided_is_a_problem(tree, sql, problem):
    """G7-19 (ii): a file writing one of the four tables, other than its decided
    writer, is a problem (the run is re-bound, so the writer is the only change)."""
    (tree / "src/turab/services/writer_probe.py").write_text(f'SQL = "{sql}"\n')
    r = _regenerated_with(tree, _all_passing())
    assert r.returncode == 1 and problem in r.stderr


@pytest.mark.parametrize("path, old, new, problem", [
    ("src/turab/services/webhooks.py", "SET delivery_status", "SET body_text = NULL, delivery_status",
     "communication_messages UPDATE sets"),
    ("src/turab/services/webhooks.py", "SET last_message_at", "SET thread_status = 'OPEN', last_message_at",
     "communication_threads UPDATE sets"),
    ("src/turab/services/webhooks.py", "SET processing_status", "SET payload = '{}', processing_status",
     "webhook_events UPDATE sets"),
])
def test_s7_an_update_setting_another_column_is_a_problem(tree, path, old, new, problem):
    target = tree / path
    source = target.read_text()
    assert old in source
    target.write_text(source.replace(old, new, 1))
    r = _regenerated_with(tree, _all_passing())
    assert r.returncode == 1 and problem in r.stderr


def test_s7_an_operator_script_writing_a_table_itself_is_a_problem(tree):
    path = tree / "db/ops/recover_webhook_events.py"
    path.write_text(path.read_text() + '\nSQL = "UPDATE turab.webhook_events SET error_text = NULL"\n')
    r = _regenerated_with(tree, _all_passing())
    assert r.returncode == 1 and "an operator script writes one of the four tables itself" in r.stderr


def test_s7_a_new_caller_of_the_interactions_insert_is_a_problem(tree):
    path = tree / "src/turab/services/timeline.py"
    path.write_text(path.read_text() + "\n\ndef _probe(s, m):\n    message_interactions.write(s, m)\n")
    r = _regenerated_with(tree, _all_passing())
    assert r.returncode == 1 and "message_interactions.write is called by" in r.stderr


def test_s7_the_sample_absent_is_a_problem(tree):
    (tree / COUNTS).unlink()
    r = _regenerated(tree)
    assert r.returncode == 1 and "is absent: no sample of the event store" in r.stderr


@pytest.mark.parametrize("field, value", [
    ("commit", "1" * 40),
    ("fingerprint", "a" * 64),
    ("report_sha256", "b" * 64),
    ("run_recorded", "2026-01-02 00:00:00 UTC"),
])
def test_s7_a_sample_of_another_run_is_refused(tree, field, value):
    """G7-19 (i): the generator refuses a sample whose run is not the bound one."""
    _sample(tree, **{field: value})
    r = _regenerated(tree)
    key = {"run_recorded": "run_recorded"}.get(field, field)
    assert r.returncode == 1 and f"the event store's sample names {key}" in r.stderr


def test_s7_a_sample_after_a_rebound_run_is_refused(tree):
    """A new run makes the old sample another run's."""
    old = (tree / COUNTS).read_text()
    _bind(tree, _report(_all_passing() + [_case("test_slice7_step5::test_extra")]))
    (tree / COUNTS).write_text(old)
    r = _regenerated(tree)
    assert r.returncode == 1 and "the event store's sample names report_sha256" in r.stderr


def test_s7_a_correction_without_its_approval_is_a_problem(tree):
    path = tree / "docs/contract/CONTRACT_CORRECTIONS.yaml"
    source = path.read_text()
    assert source.count('    approved: "2026-10-27"\n    operation_id: postWebhooksWhatsapp') == 2
    path.write_text(source.replace('    approved: "2026-10-27"\n', "", 1))
    r = _regenerated_with(tree, _all_passing())
    assert r.returncode == 1 and "carries no approval date" in r.stderr


def test_s7_an_unbound_report_is_not_evidence(tree, tmp_path):
    other = tmp_path / "other.xml"
    other.write_text(_report(_all_passing()))
    r = subprocess.run([sys.executable, str(tree / "db/gate/slice7_evidence.py"),
                        "--junit", str(other), "--check"], cwd=tree, capture_output=True,
                       text=True)
    assert r.returncode == 1 and "not the committed run" in r.stderr
