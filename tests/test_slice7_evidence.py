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

import os
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
DEST = {"dbname": "turab_authz_test", "host": "127.0.0.1", "hostaddr": "", "port": "5432"}
SERVER = {"system_identifier": "7000000000000000001", "address": "127.0.0.1", "port": "5432",
          "database": "turab_authz_test"}
#: Every variable that could choose a connection's destination (run_binding).
DEST_VARS = (*run_binding.DESTINATION_VARS.values(), *run_binding.SERVICE_VARS)


def _case(qualified: str, status: str = "pass") -> str:
    module, name = qualified.split("::")
    body = {"fail": '<failure message="boom">boom</failure>',
            "skip": '<skipped message="skip">skip</skipped>'}.get(status, "")
    return f'<testcase classname="tests.{module}" name="{name}" time="0.01">{body}</testcase>'


def _report(cases: list[str], failures: int = 0, skipped: int = 0) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><testsuites>'
            f'<testsuite name="pytest" errors="0" failures="{failures}" skipped="{skipped}" '
            f'tests="{len(cases)}" time="1.000" timestamp="2026-01-01T00:00:00+00:00" '
            f'hostname="test">{"".join(cases)}</testsuite></testsuites>')


def _sample(copy: pathlib.Path, **override) -> None:
    """The event-store sample, naming the copy's recorded run unless overridden."""
    recorded = run_binding.read_provenance((copy / run_binding.PROVENANCE).read_text())
    fields = dict(sampled_at="2026-01-01 00:00:05 UTC", run_recorded=RECORDED,
                  commit=recorded["commit"], fingerprint=recorded["fingerprint"],
                  report_sha256=recorded["report_sha256"],
                  destination=recorded.get("destination", DEST),
                  server=recorded.get("server", SERVER),
                  counts={"RECEIVED": 1, "PROCESSED": 7, "IGNORED": 3, "FAILED": 2},
                  failed={"PROCESSING_FAILED": 2})
    fields.update(override)
    (copy / COUNTS).write_text(slice7_event_store_counts.render(**fields))


def _bind(copy: pathlib.Path, report: str, destination=DEST, server=SERVER) -> None:
    """Record `report` as the run of the copy's CURRENT tree, then sample it."""
    (copy / REPORT).write_text(report)
    source = run_binding.fingerprint(copy)
    (copy / run_binding.PROVENANCE).write_text(run_binding.provenance_text(
        recorded=RECORDED, commit="0" * 40, source_fingerprint=source,
        report=copy / REPORT, report_name=REPORT.as_posix(), destination=destination,
        server=server))
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
    assert RECORDED in section and "`turab_authz_test` on host `127.0.0.1`" in section


def test_s7_the_end_to_end_tests_are_described_as_they_are(tree):
    """Review of 8dd7921: the operations proven go over HTTP; the rows they start
    from are set up in SQL, and the document says which."""
    text = (tree / DOC).read_text()
    assert "every business row" not in text
    section = text.split("## 1.")[1].split("| # |")[0]
    assert "**What goes over HTTP:** the operations each test proves" in section
    for helper in ("`_party` (a party)", "`_archive_consent` (a consent grant and its "
                   "thread binding)", "`_sale_world` (the request, its criterion, the "
                   "property with its attributes, and the offer"):
        assert helper in section
    assert "every business row" not in (ROOT / "tests/test_slice7_step5.py").read_text() \
        .split('"""')[1].replace('"every business row is made over HTTP"', "")


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


# --- reviews of 8dd7921 and 84280c0: the sample bound to where the suite's connections ----
# --- went, and to the server they reached; no skipped case -----------------------------------

def _real():
    """This suite's own destination and the server it reaches."""
    from tests.conftest import PGHOST, TEST_DB

    dest = {"dbname": TEST_DB, "host": PGHOST, "hostaddr": os.environ.get("PGHOSTADDR", ""),
            "port": os.environ.get("PGPORT", "5432")}
    with run_binding.connect(dest) as conn:
        return dest, run_binding.server_identity(conn)


@pytest.mark.parametrize("override, field", [
    ({"destination": {**DEST, "dbname": "turab_other_db"}}, "database"),
    ({"destination": {**DEST, "host": "10.0.0.9"}}, "host"),
    ({"destination": {**DEST, "port": "5433"}}, "destination"),
    ({"destination": {**DEST, "hostaddr": "10.0.0.9"}}, "destination"),
    ({"server": {**SERVER, "system_identifier": "7000000000000000002"}}, "server"),
    ({"server": {**SERVER, "port": "5433"}}, "server"),
])
def test_s7_a_sample_of_another_destination_or_server_is_refused(tree, override, field):
    """The generator compares the sample's database, host, whole destination and
    the server it reached with the run's record."""
    _sample(tree, **override)
    r = _regenerated(tree)
    assert r.returncode == 1 and f"the event store's sample names {field}" in r.stderr


@pytest.mark.parametrize("missing, problem", [
    ({"destination": None, "server": None}, "the run's record names no test database"),
    ({"destination": None, "server": None}, "the run's record names no test destination"),
    ({"server": None}, "the run's record names no test server"),
])
def test_s7_a_run_record_naming_no_destination_or_server_is_refused(tree, missing, problem):
    _bind(tree, _report(_all_passing()), **missing)
    r = _regenerated(tree)
    assert r.returncode == 1 and problem in r.stderr


def test_s7_a_skipped_case_is_refused_by_the_generator(tree):
    cases = _all_passing() + [_case("test_slice7_step5::test_extra", "skip")]
    r = _regenerated_with(tree, cases)
    assert "the run skipped" not in _gen(tree, check=False).stdout
    assert r.returncode == 1 and "the run skipped 1 cases; Slice 7's evidence requires none" \
        in r.stderr


def _sample_tool(tree, **env) -> subprocess.CompletedProcess:
    base = {k: v for k, v in os.environ.items() if k not in DEST_VARS}
    return subprocess.run([sys.executable, str(tree / "db/gate/slice7_event_store_counts.py")],
                          cwd=tree, capture_output=True, text=True, env={**base, **env})


@pytest.mark.parametrize("env, problem", [
    ({"TURAB_TEST_DB": "turab_other_db"}, "TURAB_TEST_DB is 'turab_other_db'; the run used"),
    ({"PGHOST": "10.0.0.9"}, "PGHOST is '10.0.0.9'; the run used"),
    ({"PGPORT": "5433"}, "PGPORT is '5433'; the run used '1'"),
    ({"PGHOSTADDR": "10.0.0.9"}, "PGHOSTADDR is '10.0.0.9'; the run used '(none)'"),
    ({"PGSERVICE": "elsewhere"}, "PGSERVICE is set: a service file could send the sample"),
])
def test_s7_the_sample_tool_refuses_another_destination_before_connecting(tree, env, problem):
    """The record's destination is unreachable (port 1): a refusal that came
    after a connection attempt would name the failed connection instead. The
    tool writes nothing."""
    _bind(tree, _report(_all_passing()), destination={**DEST, "port": "1"})
    (tree / COUNTS).unlink()
    r = _sample_tool(tree, **env)
    assert r.returncode == 1 and problem in r.stderr
    assert "connection" not in r.stderr.lower()
    assert not (tree / COUNTS).exists()


@pytest.mark.parametrize("missing, problem", [
    ({"destination": None, "server": None}, "the run's record names no test destination or server"),
    ({"server": None}, "the run's record names no test server"),
])
def test_s7_the_sample_tool_refuses_a_record_naming_no_destination(tree, missing, problem):
    _bind(tree, _report(_all_passing()), **missing)
    (tree / COUNTS).unlink()
    r = _sample_tool(tree)
    assert r.returncode == 1 and problem in r.stderr
    assert not (tree / COUNTS).exists()


def test_s7_the_sample_tool_refuses_a_skipped_case(tree):
    _bind(tree, _report(_all_passing() + [_case("test_slice7_step5::test_extra", "skip")],
                        skipped=1))
    (tree / COUNTS).unlink()
    r = _sample_tool(tree)
    assert r.returncode == 1 and "the run skipped 1 cases" in r.stderr
    assert not (tree / COUNTS).exists()


def test_s7_the_sample_tool_samples_the_recorded_destination_and_the_generator_accepts_it(
        tree, engine):
    """With no destination variable in its environment, the tool samples the
    destination the run's record names (this suite's), after finding the
    recorded server there; the generator accepts the sample."""
    dest, server = _real()
    _bind(tree, _report(_all_passing()), destination=dest, server=server)
    (tree / COUNTS).unlink()
    r = _sample_tool(tree)
    assert r.returncode == 0, r.stderr
    text = (tree / COUNTS).read_text()
    assert f"Test destination  : {run_binding.destination_line(dest)}\n" in text
    assert f"Server reached    : {run_binding.server_line(server)}\n" in text
    assert _regenerated(tree).returncode == 0


@pytest.mark.parametrize("field, value", [
    ("system_identifier", "7000000000000000002"), ("port", "5433"), ("database", "turab_other"),
])
def test_s7_the_sample_tool_refuses_a_server_that_is_not_the_runs(tree, engine, field, value):
    """The destination reaches a server; if it is not the one the run's record
    names, nothing is counted and nothing is written."""
    dest, server = _real()
    _bind(tree, _report(_all_passing()), destination=dest, server={**server, field: value})
    (tree / COUNTS).unlink()
    r = _sample_tool(tree)
    assert r.returncode == 1 and "the server reached is" in r.stderr
    assert "nothing is counted" in r.stderr and not (tree / COUNTS).exists()


@pytest.mark.parametrize("destination, named", [
    ({**DEST, "dbname": "turab_absent_db_s7"}, "turab_absent_db_s7"),
    ({**DEST, "port": "1"}, "port 1 failed"),
    ({**DEST, "hostaddr": "127.0.0.2"}, '"127.0.0.2", port 5432 failed'),
])
def test_s7_the_sample_tool_connects_to_the_recorded_destination_not_the_default(
        tree, destination, named):
    """With no destination variable set, libpq's defaults would reach the suite's
    own server; the tool must use what the record names instead. Each named
    destination is unreachable here, so the tool fails naming it, and writes
    nothing."""
    _bind(tree, _report(_all_passing()), destination=destination)
    (tree / COUNTS).unlink()
    r = _sample_tool(tree)
    assert r.returncode != 0 and named in r.stderr
    assert not (tree / COUNTS).exists()


def _recorder(tmp_path, monkeypatch, server=SERVER):
    import record_test_run

    calls = []

    def fake_run(args, cwd=None, env=None, **kw):
        calls.append((args, env))
        if args[0] == "git":
            return subprocess.CompletedProcess(args, 0, "0" * 40 + "\n" if "rev-parse" in args
                                               else "", "")
        (tmp_path / REPORT).parent.mkdir(parents=True, exist_ok=True)
        (tmp_path / REPORT).write_text(_report([_case("test_x::test_y")]))
        return subprocess.CompletedProcess(args, 0, "", "")

    class _Conn:
        def __init__(self, dest):
            calls.append(("connect", dest))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def identity(conn):
        if server is None:
            raise OSError("unreachable")
        return server

    monkeypatch.setattr(record_test_run, "ROOT", tmp_path)
    monkeypatch.setattr(record_test_run, "fingerprint", lambda root: "f" * 64)
    monkeypatch.setattr(record_test_run.subprocess, "run", fake_run)
    monkeypatch.setattr(record_test_run, "connect", _Conn)
    monkeypatch.setattr(record_test_run, "server_identity", identity)
    for var in DEST_VARS:
        monkeypatch.delenv(var, raising=False)
    return record_test_run, calls


def test_s7_the_recorder_runs_the_suite_on_the_destination_it_records(tmp_path, monkeypatch):
    """`record_test_run.py` sets the whole destination it records in the suite's
    own environment, identifies the server with the same parameters, and records
    both (reviews of 8dd7921 and 84280c0)."""
    recorder, calls = _recorder(tmp_path, monkeypatch)
    for var, value in (("TURAB_TEST_DB", "turab_probe_db"), ("PGHOST", "10.0.0.7"),
                       ("PGHOSTADDR", "10.0.0.8"), ("PGPORT", "6543")):
        monkeypatch.setenv(var, value)
    assert recorder.main() == 0
    [env] = [c[1] for c in calls if c[0] not in ("connect",) and c[0][0] != "git"]
    want = {"dbname": "turab_probe_db", "host": "10.0.0.7", "hostaddr": "10.0.0.8",
            "port": "6543"}
    assert {k: env[v] for k, v in run_binding.DESTINATION_VARS.items()} == want
    assert [c[1] for c in calls if c[0] == "connect"] == [want]
    recorded = run_binding.read_provenance((tmp_path / run_binding.PROVENANCE).read_text())
    assert recorded["database"] == ("turab_probe_db", "10.0.0.7")
    assert recorded["destination"] == want and recorded["server"] == SERVER


def test_s7_the_recorder_runs_the_suite_with_no_host_address_when_none_is_set(tmp_path,
                                                                             monkeypatch):
    """No PGHOSTADDR: the suite's environment has none, and the record says none."""
    recorder, calls = _recorder(tmp_path, monkeypatch)
    assert recorder.main() == 0
    [env] = [c[1] for c in calls if c[0] not in ("connect",) and c[0][0] != "git"]
    assert "PGHOSTADDR" not in env and env["PGPORT"] == "5432"
    recorded = run_binding.read_provenance((tmp_path / run_binding.PROVENANCE).read_text())
    assert recorded["destination"]["hostaddr"] == ""


def test_s7_the_recorder_refuses_a_service(tmp_path, monkeypatch):
    recorder, calls = _recorder(tmp_path, monkeypatch)
    monkeypatch.setenv("PGSERVICE", "elsewhere")
    assert recorder.main() == 2
    assert [c for c in calls if c[0] != "connect" and c[0][0] != "git"] == []
    assert not (tmp_path / run_binding.PROVENANCE).exists()


def test_s7_the_recorder_writes_no_record_when_the_server_cannot_be_identified(
        tmp_path, monkeypatch):
    recorder, _ = _recorder(tmp_path, monkeypatch, server=None)
    assert recorder.main() == 2
    assert not (tmp_path / run_binding.PROVENANCE).exists()


def test_s7_the_server_identity_is_the_clusters_own(engine):
    """`server_identity` reads the cluster's system identifier, and the address,
    port and database the connection reached; the same cluster gives the same
    identifier through another database."""
    from sqlalchemy import text

    dest, server = _real()
    with engine.connect() as c:
        sid, port, db = c.execute(text(
            "SELECT system_identifier::text, inet_server_port()::text, current_database() "
            "FROM pg_control_system()")).one()
    assert server["system_identifier"] == sid and int(sid) != 0
    assert (server["port"], server["database"]) == (port, db) == (dest["port"], dest["dbname"])
    with run_binding.connect({**dest, "dbname": "postgres"}) as other:
        assert run_binding.server_identity(other)["system_identifier"] == sid


def test_s7_the_connection_is_not_redirected_by_an_environment_host_address(engine,
                                                                          monkeypatch):
    """A destination with no host address is sent with an explicit empty one: a
    PGHOSTADDR in the environment (here an address nothing answers on) does
    not redirect it."""
    dest, server = _real()
    if dest["hostaddr"]:
        pytest.skip("this environment sets a host address of its own")
    monkeypatch.setenv("PGHOSTADDR", "127.0.0.2")
    with run_binding.connect(dest) as conn:
        assert run_binding.server_identity(conn) == server


def test_s7_no_connection_is_made_while_a_service_is_set(monkeypatch):
    monkeypatch.setenv("PGSERVICE", "elsewhere")
    with pytest.raises(run_binding.ServiceSet, match="PGSERVICE is set"):
        run_binding.connect(DEST)
