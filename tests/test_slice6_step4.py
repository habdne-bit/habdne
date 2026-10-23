"""Slice 6 step 4: the run writes the diagnostic's computed parts and raises its
tasks.

Ref: `docs/gate/SLICE_6_PLAN.md` revision 11: G6-4 (a) with (i)-(iii), (iv)
(a), (v), (vi); G6-10 (a); G6-11; §5.3 (OQ6-1's obligation); §7 condition
10; the review of `922a100` (two required experiments: a real format-2 row
replayed; the measured supersession of an older match after the registry
digest changed); `services/matching_run.py`.

**Isolation.** HTTP tests commit to the shared test database; each builds
its own request, properties and offers.
"""
from __future__ import annotations

import json
import re
import threading
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.conftest import REPO_ROOT
from tests.test_slice4_step7 import _criterion, _exec, _offer, _one, _request, _run
from tests.test_slice4_step8 import _registry_of
from tests.test_slice5_step2 import _prop, _review
from tests.test_slice6_step2 import _all, _complete, _in_thread, _watch
from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.matching import registry_history
from turab.services import diagnostic_replay, matching_run


@pytest.fixture
def client(engine):
    from turab.app import create_app

    with TestClient(create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink())),
                    raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def lenient(engine):
    from turab.app import create_app

    with TestClient(create_app(engine=engine), raise_server_exceptions=False) as c:
        yield c


def _ran(client, ids, req, props, **kw):
    r = _run(client, ids, req, props, **kw)
    assert r.status_code == 201, r.text
    return r.json()


def _document_world(engine, ids):
    """A candidate one fact away: its REQUIRED document is UNKNOWN, all else
    PASS. Its VERIFY_DOCUMENT suggestion is HIGH, so the run raises a task."""
    req = _request(engine, ids)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    prop = _prop(engine, document=None)
    offer = _offer(engine, ids, prop)
    return req, prop, offer


def _stored_row(engine, diagnostic_run_id):
    """The diagnostic row as the database holds it, read exactly."""
    from turab import exact_json

    return exact_json.loads(_one(engine, """
        SELECT jsonb_build_object('request_id', request_id, 'run_at', run_at,
                                  'blocker_summary', blocker_summary,
                                  'suggested_actions', suggested_actions,
                                  'relaxation_scenarios', relaxation_scenarios)::text
          FROM turab.match_diagnostic_runs WHERE diagnostic_run_id = :d""",
        d=diagnostic_run_id))


def _replay(engine, diagnostic_run_id):
    with engine.connect() as conn:
        return diagnostic_replay.replay(conn, _stored_row(engine, diagnostic_run_id))


def _diagnostic_tasks(engine, req):
    return _all(engine, """
        SELECT task_id, task_type::text AS task_type, priority::text AS priority,
               status::text AS status, title, reason_code, request_id, property_id, match_id,
               payload
          FROM turab.tasks WHERE request_id = :r AND payload ->> 'source' = 'DIAGNOSTIC'
         ORDER BY created_at, task_id""", r=req)


# ======================================================================================
# The review of 922a100, experiment 1: a real format-2 row, written, then replayed
# ======================================================================================

def test_a_row_the_run_wrote_is_format_2_and_replays(client, engine, ids):
    req = _request(engine, ids, budget_max=24_000_000)
    _criterion(engine, req, "LOCATION", "IN", [_one(
        engine, "SELECT location_id::text FROM turab.locations WHERE code = 'ADR-NEW-TIL'")],
        "REQUIRED")
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED", sort_order=1)
    p1 = _prop(engine, document=None)
    p2 = _prop(engine)
    lonely = _prop(engine)
    for p, code in ((p1, "ADR-NEW-TIL"), (p2, "ADR-AIRPORT"), (lonely, "ADR-NEW-TIL")):
        _exec(engine, "UPDATE turab.properties SET canonical_location_id = (SELECT location_id "
                      "FROM turab.locations WHERE code = :c) WHERE property_id = :p", c=code, p=p)
    _offer(engine, ids, p1)
    _offer(engine, ids, p2)
    body = _ran(client, ids, req, [p1, p2, lonely])
    d = body["diagnostic"]
    row = _stored_row(engine, d["diagnostic_run_id"])
    summary = row["blocker_summary"]
    assert summary["format"] == "turab.blocker-summary/2"
    assert summary["versions"] == {"value": "diagnostic.value@1",
                                   "actions": "diagnostic.actions@1",
                                   "relaxation": "diagnostic.relaxation@1"}
    assert [e["stored"] for e in summary["evaluated"]] == ["NEW", "NEW"]
    assert row["suggested_actions"] and row["relaxation_scenarios"]
    assert summary["excluded_counts"] and summary["requested_location_chains"]
    assert d["suggested_actions"] == row["suggested_actions"], "the response is the row"
    assert _replay(engine, d["diagnostic_run_id"]) == {"R": [], "D": []}

    again = _ran(client, ids, req, [p1, p2, lonely])["diagnostic"]
    second = _stored_row(engine, again["diagnostic_run_id"])
    assert [e["stored"] for e in second["blocker_summary"]["evaluated"]] == [
        "EXISTING", "EXISTING"]
    assert _replay(engine, again["diagnostic_run_id"]) == {"R": [], "D": []}


def test_the_input_hash_covers_the_requested_chains(client, engine, ids):
    """`turab.diagnostic-input/2`: nothing but a requested location's chain
    changes between two runs, and the diagnostic's input hash changes."""
    new_til = _one(engine, "SELECT location_id::text FROM turab.locations "
                           "WHERE code = 'ADR-NEW-TIL'")
    req = _request(engine, ids)
    _criterion(engine, req, "LOCATION", "IN", [new_til], "REQUIRED")
    prop = _prop(engine)
    _offer(engine, ids, prop)

    def hash_of(body):
        return _one(engine, "SELECT input_hash FROM turab.match_diagnostic_runs "
                            "WHERE diagnostic_run_id = :d", d=body["diagnostic"]["diagnostic_run_id"])
    first = hash_of(_ran(client, ids, req, [prop]))
    assert hash_of(_ran(client, ids, req, [prop])) == first, "unchanged input, same hash"
    parent = _one(engine, "SELECT parent_id::text FROM turab.locations WHERE location_id = :l",
                  l=new_til)
    try:
        _exec(engine, "UPDATE turab.locations SET parent_id = (SELECT location_id FROM "
                      "turab.locations WHERE code = 'ADR-CENTER') WHERE location_id = :l",
              l=new_til)
        assert hash_of(_ran(client, ids, req, [prop])) != first
    finally:
        _exec(engine, "UPDATE turab.locations SET parent_id = :p WHERE location_id = :l",
              p=parent, l=new_til)


# ======================================================================================
# G6-4 (a): the tasks of the HIGH suggestions
# ======================================================================================

def test_a_high_suggestion_raises_one_task_with_its_subject(client, engine, ids):
    """G6-4 (ii), and OQ6-1's obligation (§5.3): the run's task has its
    request and the four keys entity, id, gate, basis non-NULL, and `source`
    is "DIAGNOSTIC" exactly; its payload is the diagnostic, the source and
    the six keys of the subject, nothing else."""
    req, prop, offer = _document_world(engine, ids)
    body = _ran(client, ids, req, [prop])
    [action] = [a for a in body["diagnostic"]["suggested_actions"] if a["priority"] == "HIGH"]
    [task] = _diagnostic_tasks(engine, req)
    assert (task["task_type"], task["priority"], task["status"], task["title"],
            task["reason_code"]) == ("VERIFY_DOCUMENT", "HIGH", "OPEN",
                                     "Verify the property's document", "DOCUMENT_NOT_KNOWN")
    assert (task["request_id"], task["property_id"], str(task["match_id"])) == (
        req, prop, body["matches"][0]["match_id"])
    payload = task["payload"]
    assert set(payload) == {"diagnostic_run_id", "source", "subject"}
    assert payload["source"] == "DIAGNOSTIC"
    assert payload["diagnostic_run_id"] == body["diagnostic"]["diagnostic_run_id"]
    assert set(payload["subject"]) == {"entity", "id", "gate", "criterion", "ordinal", "basis"}
    assert all(payload["subject"][k] is not None for k in ("entity", "id", "gate", "basis"))
    assert {k: payload["subject"][k] for k in payload["subject"]} == {
        k: action["subject"][k] for k in payload["subject"]}
    audited = _one(engine, "SELECT count(*) FROM turab.audit_log WHERE entity_table = 'tasks' "
                           "AND entity_id = :t AND action = 'INSERT'", t=task["task_id"])
    assert audited == 1


def test_every_diagnostic_task_carries_a_complete_key(client, engine, ids):
    """OQ6-1's obligation, over every diagnostic task the suite's runs wrote
    so far in this database, not only this file's (one is written here, so
    the check is never empty)."""
    req, prop, _ = _document_world(engine, ids)
    _ran(client, ids, req, [prop])
    rows = _all(engine, """
        SELECT request_id, payload FROM turab.tasks
         WHERE payload ? 'diagnostic_run_id' OR payload ->> 'source' ILIKE 'diagnostic'""")
    assert rows
    for row in rows:
        subject = row["payload"]["subject"]
        assert row["request_id"] is not None and row["payload"]["source"] == "DIAGNOSTIC"
        assert all(subject.get(k) is not None for k in ("entity", "id", "gate", "basis")), row


def test_normal_suggestions_raise_no_task(client, engine, ids):
    """G6-4 (a): NORMAL entries stay recommendations. Two unknowns: neither is
    high-value; both are suggested, NORMAL; no task."""
    req = _request(engine, ids)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    _criterion(engine, req, "ROOMS_MIN", "GTE", 3, "REQUIRED", sort_order=1)
    prop = _prop(engine, ptype="APARTMENT", document=None)
    _offer(engine, ids, prop)
    body = _ran(client, ids, req, [prop])
    assert {a["priority"] for a in body["diagnostic"]["suggested_actions"]} == {"NORMAL"}
    assert _diagnostic_tasks(engine, req) == []


def test_g6_4_re_run_writes_a_second_diagnostic_and_no_new_task(client, engine, ids):
    """G6-4 (iii): on unchanged facts the second run's suggestions are
    identical, no task is added, and the existing task still names the first
    diagnostic. Nothing is written about the work already open."""
    req, prop, _ = _document_world(engine, ids)
    first = _ran(client, ids, req, [prop])["diagnostic"]
    audit = _one(engine, "SELECT count(*) FROM turab.audit_log WHERE entity_table = 'tasks'")
    second = _ran(client, ids, req, [prop])["diagnostic"]
    assert second["suggested_actions"] == first["suggested_actions"]
    [task] = _diagnostic_tasks(engine, req)
    assert task["payload"]["diagnostic_run_id"] == first["diagnostic_run_id"]
    assert _one(engine, "SELECT count(*) FROM turab.audit_log "
                        "WHERE entity_table = 'tasks'") == audit
    assert _replay(engine, second["diagnostic_run_id"]) == {"R": [], "D": []}


def test_work_taken_up_is_not_raised_again_and_done_work_is(client, engine, ids):
    """G6-4 (iii), F6-15: the key covers OPEN and IN_PROGRESS; once DONE, a
    later run raises the work again."""
    req, prop, _ = _document_world(engine, ids)
    _ran(client, ids, req, [prop])
    [task] = _diagnostic_tasks(engine, req)
    _exec(engine, "UPDATE turab.tasks SET status = 'IN_PROGRESS' WHERE task_id = :t",
          t=task["task_id"])
    _ran(client, ids, req, [prop])
    assert len(_diagnostic_tasks(engine, req)) == 1
    assert _complete(client, task["task_id"], {"outcome_code": "TASK_NO_LONGER_NEEDED"},
                     ids.ACC_OPERATOR).status_code == 200
    third = _ran(client, ids, req, [prop])["diagnostic"]
    tasks = _diagnostic_tasks(engine, req)
    assert [t["status"] for t in tasks] == ["DONE", "OPEN"]
    assert tasks[1]["payload"]["diagnostic_run_id"] == third["diagnostic_run_id"]


def test_g6_10_a_task_whose_cause_has_gone_stays_open(client, engine, ids):
    """G6-10 (a): the document is recorded; the next run no longer suggests
    it, and the task stays OPEN, stating its work by itself."""
    req, prop, _ = _document_world(engine, ids)
    _ran(client, ids, req, [prop])
    _exec(engine, """
        INSERT INTO turab.property_attributes (property_id, attribute_definition_id, value)
        SELECT :p, attribute_definition_id, '"LAND_BOOK"'::jsonb
          FROM turab.attribute_definitions WHERE code = 'DOCUMENT_TYPE'""", p=prop)
    later = _ran(client, ids, req, [prop])
    assert not [a for a in later["diagnostic"]["suggested_actions"]
                if a["type"] == "VERIFY_DOCUMENT"]
    [task] = _diagnostic_tasks(engine, req)
    assert (task["status"], task["task_type"], task["payload"]["subject"]["criterion"]) == (
        "OPEN", "VERIFY_DOCUMENT", "DOCUMENT_TYPE")


def test_a_task_failure_other_than_open_work_fails_the_run_writing_nothing(
        lenient, engine, ids, monkeypatch):
    """G6-4 (iii): an attempt has two outcomes, created or refused by the
    index; anything else fails the whole run (no match, no diagnostic, no
    task, no key)."""
    from turab.services import audit_rows

    req, prop, _ = _document_world(engine, ids)
    key = str(uuid.uuid4())
    real = audit_rows.write

    def failing(session, table, *args, **kw):
        if table == "tasks":
            raise RuntimeError("injected at the task insert")
        return real(session, table, *args, **kw)
    monkeypatch.setattr(audit_rows, "write", failing)
    r = _run(lenient, ids, req, [prop], key=key)
    assert (r.status_code, r.json()["code"]) == (500, "INTERNAL_ERROR")
    for table in ("match_candidates", "match_diagnostic_runs", "tasks"):
        assert _one(engine, f"SELECT count(*) FROM turab.{table} WHERE request_id = :r",
                    r=req) == 0, table
    assert _one(engine, "SELECT count(*) FROM turab.idempotency_records "
                        "WHERE idempotency_key = :k", k=key) == 0


def test_an_nmi_task_and_a_diagnostic_task_are_independent_records(client, engine, ids):
    """G6-4 (iv) (a): the run does not consult NMI tasks; both name the same
    work, each its own source."""
    req, prop, _ = _document_world(engine, ids)
    [m] = _ran(client, ids, req, [prop])["matches"]
    assert _review(client, m["match_id"], {"decision": "NEED_MORE_INFORMATION",
                                          "reason_code": "DOCUMENT_NOT_KNOWN"},
                   ids.ACC_REVIEWER).status_code == 200
    _ran(client, ids, req, [prop])
    rows = _all(engine, "SELECT payload FROM turab.tasks WHERE match_id = :m "
                        "ORDER BY created_at", m=m["match_id"])
    assert len(rows) == 2
    assert ["source" in r["payload"] for r in rows] == [True, False]
    assert "match_review_id" in rows[1]["payload"]


# ======================================================================================
# G6-4 (iii) and (v): two concurrent runs on one subject, and what staff see
# ======================================================================================

def test_g6_4_concurrent_runs_raise_one_task_and_staff_see_a_self_contained_task(
        client, engine, ids, monkeypatch):
    """Run A raises the task and is held before its commit. Run B, started
    later, inserts the same work: it waits on A's uncommitted task
    (`pg_blocking_pids` witness), then finds it open and commits last. One
    task, naming A's diagnostic; both diagnostics replay, their suggestions
    equal (G6-4 (iii)). Then what staff see (G6-4 (v), F6-12): the request's
    diagnostic is B's (later `run_at`); the task names A's, which no
    operation reads by id; the task states its work by itself; its match is
    readable."""
    req, prop, _ = _document_world(engine, ids)
    _ran(client, ids, req, [prop])                 # the matches exist, so neither run
    [first] = _diagnostic_tasks(engine, req)       # waits on a match row
    assert _complete(client, first["task_id"], {"outcome_code": "TASK_NO_LONGER_NEEDED"},
                     ids.ACC_OPERATOR).status_code == 200

    out, raised, release = {}, threading.Event(), threading.Event()
    real = matching_run._raise_tasks

    def held(session, prepared, diagnostic_id, actions, evaluated):
        created = real(session, prepared, diagnostic_id, actions, evaluated)
        if not raised.is_set():
            out["a_pid"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
            out["a_diagnostic"] = str(diagnostic_id)
            raised.set()
            assert release.wait(30), "run A was never released"
        return created
    monkeypatch.setattr(matching_run, "_raise_tasks", held)
    a = _in_thread(engine, out, "a", lambda c: _run(c, ids, req, [prop]))
    b = None
    try:
        assert raised.wait(30), "run A never raised its task"
        b = _in_thread(engine, out, "b", lambda c: _run(c, ids, req, [prop]))
        waited = _watch(engine, out["a_pid"], b)
        b_ended_while_a_held = not b.is_alive()
    finally:
        release.set()
        a.join(60)
        if b is not None:
            b.join(60)
    assert (waited, b_ended_while_a_held) == (True, False)
    da, db = out["a"].json()["diagnostic"], out["b"].json()["diagnostic"]
    assert (out["a"].status_code, out["b"].status_code) == (201, 201)
    open_tasks = [t for t in _diagnostic_tasks(engine, req) if t["status"] == "OPEN"]
    assert [t["payload"]["diagnostic_run_id"] for t in open_tasks] == [da["diagnostic_run_id"]]
    assert da["suggested_actions"] == db["suggested_actions"]
    for d in (da, db):
        assert _replay(engine, d["diagnostic_run_id"]) == {"R": [], "D": []}

    staff = {"Authorization": f"Bearer {ids.ACC_OPERATOR}"}
    latest = client.get(f"/requests/{req}/diagnostic", headers=staff).json()
    assert latest["diagnostic_run_id"] == db["diagnostic_run_id"], "F6-12: B's run_at is later"
    [task] = open_tasks
    listed = [t for t in client.get("/tasks", params={"status": "OPEN", "page_size": 100},
                                    headers=staff).json()["items"]
              if t["task_id"] == str(task["task_id"])]
    if not listed:   # a full list may page past it: read every page
        page, listed = 1, []
        while not listed:
            items = client.get("/tasks", params={"status": "OPEN", "page": page,
                                                 "page_size": 100}, headers=staff).json()["items"]
            assert items, "the task is listed"
            listed = [t for t in items if t["task_id"] == str(task["task_id"])]
            page += 1
    [shown] = listed
    assert shown["payload"]["diagnostic_run_id"] == da["diagnostic_run_id"]
    assert (shown["task_type"], shown["priority"], shown["reason_code"]) == (
        "VERIFY_DOCUMENT", "HIGH", "DOCUMENT_NOT_KNOWN")
    assert shown["payload"]["subject"]["criterion"] == "DOCUMENT_TYPE"
    assert client.get(f"/matches/{shown['match_id']}", headers=staff).status_code == 200


# ======================================================================================
# The review of 922a100, experiment 2: supersession after the digest changed
# ======================================================================================

def _queue_ids(client, ids):
    r = client.get("/backoffice/queues/matches",
                   headers={"Authorization": f"Bearer {ids.ACC_OPERATOR}"})
    assert r.status_code == 200, r.text
    return {i["id"] for i in r.json()["items"]}


def test_an_older_match_is_superseded_in_the_queue_and_at_approval(client, engine, ids,
                                                                   monkeypatch):
    """Measured, not derived (review of 220573a). A match written under
    `HISTORY[0]`'s registry (digest 7ddf…, before step 3), then a run under
    the current registry on UNCHANGED facts. The new run stores a NEW match
    (another digest, so another input hash). The match queue then shows the
    new match and not the old; approving the old one is refused 409
    MATCH_SUPERSEDED, writing nothing; the new one is approved."""
    req = _request(engine, ids)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    prop = _prop(engine)
    _offer(engine, ids, prop)
    with monkeypatch.context() as historical:
        historical.setattr(matching_run, "REGISTRY", _registry_of(registry_history.HISTORY[0]))
        [old] = _ran(client, ids, req, [prop])["matches"]
    assert old["explanation"]["engine"]["registry_digest"] == registry_history.HISTORY[0][
        "digest"]
    assert old["eligibility"] == "ELIGIBLE"
    assert old["match_id"] in _queue_ids(client, ids)

    [new] = _ran(client, ids, req, [prop])["matches"]
    assert new["match_id"] != old["match_id"], "the digest changed: a NEW match"
    assert new["explanation"]["engine"]["registry_digest"] != old["explanation"]["engine"][
        "registry_digest"]
    queue = _queue_ids(client, ids)
    assert (old["match_id"] in queue, new["match_id"] in queue) == (False, True)

    before = _one(engine, "SELECT count(*) FROM turab.match_reviews WHERE match_id = :m",
                  m=old["match_id"])
    r = _review(client, old["match_id"], {"decision": "APPROVED"}, ids.ACC_REVIEWER)
    assert (r.status_code, r.json()["code"]) == (409, "MATCH_SUPERSEDED"), r.text
    assert _one(engine, "SELECT count(*) FROM turab.match_reviews WHERE match_id = :m",
                m=old["match_id"]) == before
    approved = _review(client, new["match_id"], {"decision": "APPROVED"}, ids.ACC_REVIEWER)
    assert approved.status_code == 200, approved.text


# ======================================================================================
# §7 condition 10: the writes to `tasks`, by kind
# ======================================================================================

def _statements(kind):
    pattern = {"INSERT": r"INSERT\s+INTO\s+turab\.tasks\b",
               "UPDATE": r"UPDATE\s+turab\.tasks\b",
               "DELETE": r"DELETE\s+FROM\s+turab\.tasks\b"}[kind]
    return sorted(str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "src").rglob("*.py")
                  if re.search(pattern, p.read_text(encoding="utf-8")))


def test_the_writes_to_tasks_are_exactly_those_decided():
    """Plan §7 condition 10 (rewritten in the review of 315804b): creators by
    INSERT; the completion command by UPDATE; no DELETE. `tasks.py` is never
    left out of the inventory."""
    assert _statements("INSERT") == ["src/turab/services/identity.py",
                                     "src/turab/services/match_review.py",
                                     "src/turab/services/matching_run.py"]
    assert _statements("UPDATE") == ["src/turab/services/tasks.py"]
    assert _statements("DELETE") == []
    source = (REPO_ROOT / "src/turab/services/tasks.py").read_text(encoding="utf-8")
    [update] = re.findall(r"UPDATE\s+turab\.tasks\s+SET\s+([^\n]*)", source)
    assert update.split("WHERE")[0].strip() == "status = 'DONE', completed_at = :at"
