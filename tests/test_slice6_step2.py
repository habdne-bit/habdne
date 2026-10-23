"""Slice 6 step 2: `getTasks` and `postTasksTaskIdComplete`.

Ref: `docs/gate/SLICE_6_PLAN.md` revision 6: §3.6, §3.7, G6-8 (i)-(vii) with
the completion's lock order (G6-8 (iv), F6-18), G6-9, §6.2 (I02, K05), §6.3;
CORRECTION-005; `services/tasks.py`, `api/routes/tasks.py`.

**The acceptance condition of the review of b6a08e7.** The completion locks
the task first, then the cited observation FOR SHARE, before it inserts the
event. Proven by:
- the lock order: while the task is held by another transaction, the
  waiting completion holds no lock on the observation;
- R2a-R2d, the four orders of a completion C and a change U of its
  observation, each with a `pg_blocking_pids` witness of the wait and the
  final rows asserted; R2d is the typed refusal, writing nothing, of an
  observation deleted while C waited.

**Isolation.** HTTP tests commit to the shared test database. Each builds
its own tasks and observations; matches come from the delivered Slice 4 run.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from tests.test_slice4_step7 import _all, _exec, _offer, _one
from tests.test_slice5_step2 import _match, _review
from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.auth.contract import effective_request_body
from turab.services import tasks as task_service

CODES = ("TASK_INFORMATION_OBTAINED", "TASK_INFORMATION_UNAVAILABLE",
         "TASK_PARTY_UNREACHABLE", "TASK_NO_LONGER_NEEDED")
BODY = "BODY-AT-CITATION"
CITED = "is the evidence of a task completion and cannot change"


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture
def lenient(engine):
    """A client that answers a server error as the client would see it."""
    from turab.app import create_app

    with TestClient(create_app(engine=engine), raise_server_exceptions=False) as c:
        yield c


# --- the world ------------------------------------------------------------------------

def _task(engine, *, task_type="VERIFY_DOCUMENT", priority="NORMAL", status="OPEN",
          payload=None, assigned=None, request=None):
    return _one(engine, """
        INSERT INTO turab.tasks (task_type, priority, status, title, request_id,
                                 assigned_account_id, payload)
        VALUES (CAST(:t AS turab.task_type), CAST(:p AS turab.task_priority),
                CAST(:s AS turab.task_status), 'fixture', :r, :a, CAST(:pl AS jsonb))
        RETURNING task_id""", t=task_type, p=priority, s=status, r=request, a=assigned,
        pl=json.dumps(payload or {}))


def _observation(engine, ids):
    return _one(engine, """
        INSERT INTO turab.observations (kind, raw_text, payload, recorded_by_account_id)
        VALUES ('CALL_NOTE', :b, '{"document": "LAND_BOOK"}', :a)
        RETURNING observation_id""", b=BODY, a=ids.ACC_OPERATOR)


def _complete(client, task_id, body, account, key=None):
    return client.post(f"/tasks/{task_id}/complete", json=body,
                       headers={"Authorization": f"Bearer {account}",
                                "Idempotency-Key": key or str(uuid.uuid4())})


def _list(client, account, **params):
    return client.get("/tasks", params=params, headers={"Authorization": f"Bearer {account}"})


def _state(engine, task_id, key=None):
    """Everything a completion could write, and the audit high-water mark."""
    task = _all(engine, "SELECT status::text AS status, completed_at FROM turab.tasks "
                        "WHERE task_id = :t", t=task_id)[0]
    return {
        "status": task["status"], "completed_at": task["completed_at"],
        "events": _one(engine, "SELECT count(*) FROM turab.task_completion_events "
                               "WHERE task_id = :t", t=task_id),
        "audit": _one(engine, "SELECT count(*) FROM turab.audit_log WHERE entity_id = :t "
                              "OR entity_id IN (SELECT task_completion_event_id FROM "
                              "turab.task_completion_events WHERE task_id = :t)", t=task_id),
        "key": None if key is None else _one(
            engine, "SELECT count(*) FROM turab.idempotency_records "
                    "WHERE idempotency_key = :k", k=key),
    }


def _event(engine, task_id):
    rows = _all(engine, """
        SELECT outcome_code, note, evidence_observation_id, completed_by_account_id,
               completed_at
          FROM turab.task_completion_events WHERE task_id = :t""", t=task_id)
    return rows[0] if len(rows) == 1 else rows


def _body_of(engine, observation_id):
    rows = _all(engine, "SELECT raw_text FROM turab.observations WHERE observation_id = :o",
                o=observation_id)
    return rows[0]["raw_text"] if rows else None


# ======================================================================================
# G6-8: the completion
# ======================================================================================

def test_a_completion_appends_its_event_and_marks_the_task_done(client, engine, ids):
    """§3.6, I02: the event keeps what was received, exactly; the task is DONE
    with the event's instant; the response is the contract's Task."""
    task, obs = _task(engine), _observation(engine, ids)
    r = _complete(client, task, {"outcome_code": "TASK_INFORMATION_OBTAINED",
                                 "note": "called the seller", "evidence_observation_id": str(obs)},
                  ids.ACC_OPERATOR)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["task_id"], body["status"]) == (str(task), "DONE")
    assert set(body) == {"task_id", "task_type", "priority", "status", "title", "reason_code",
                         "party_id", "request_id", "property_id", "match_id", "due_at",
                         "payload"}, "the contract's Task; the note is not returned (vi)"
    event = _event(engine, task)
    assert (event["outcome_code"], event["note"], event["evidence_observation_id"],
            event["completed_by_account_id"]) == (
        "TASK_INFORMATION_OBTAINED", "called the seller", obs, ids.ACC_OPERATOR)
    [done] = _all(engine, "SELECT completed_at FROM turab.tasks WHERE task_id = :t", t=task)
    assert done["completed_at"] == event["completed_at"]


@pytest.mark.parametrize("code", CODES)
def test_each_outcome_code_completes_a_task(client, engine, ids, code):
    task = _task(engine)
    r = _complete(client, task, {"outcome_code": code}, ids.ACC_REVIEWER)
    assert r.status_code == 200, r.text
    assert _event(engine, task)["outcome_code"] == code
    assert _event(engine, task)["evidence_observation_id"] is None


@pytest.mark.parametrize("status", ["OPEN", "IN_PROGRESS"])
def test_open_and_in_progress_are_completed(client, engine, ids, status):
    task = _task(engine, status=status)
    assert _complete(client, task, {"outcome_code": CODES[0]}, ids.ACC_ADMIN).status_code == 200


@pytest.mark.parametrize("status", ["DONE", "CANCELLED"])
def test_a_closed_task_is_409_and_nothing_is_written(client, engine, ids, status):
    """G6-8 (i). The refusal comes before the key is claimed."""
    task, key = _task(engine, status=status), str(uuid.uuid4())
    before = _state(engine, task, key)
    r = _complete(client, task, {"outcome_code": CODES[0]}, ids.ACC_OPERATOR, key)
    assert (r.status_code, r.json()["code"]) == (409, "TASK_NOT_OPEN"), r.text
    assert str(task) not in r.text
    assert _state(engine, task, key) == before


def test_a_done_task_stays_done(client, engine, ids):
    """G6-8 (vii): no path reopens it; a second completion changes nothing."""
    task = _task(engine)
    assert _complete(client, task, {"outcome_code": CODES[0]}, ids.ACC_OPERATOR).status_code \
        == 200
    first = _state(engine, task)
    r = _complete(client, task, {"outcome_code": CODES[1]}, ids.ACC_OPERATOR)
    assert (r.status_code, r.json()["code"]) == (409, "TASK_NOT_OPEN")
    assert _state(engine, task) == first and first["status"] == "DONE"


def test_an_unknown_evidence_observation_is_422_and_nothing_is_written(client, engine, ids):
    """G6-8 (iii)."""
    task, key, missing = _task(engine), str(uuid.uuid4()), uuid.uuid4()
    before = _state(engine, task, key)
    r = _complete(client, task, {"outcome_code": CODES[0],
                                 "evidence_observation_id": str(missing)},
                  ids.ACC_OPERATOR, key)
    assert (r.status_code, r.json()["code"]) == (422, "EVIDENCE_OBSERVATION_NOT_FOUND")
    assert str(missing) not in r.text
    assert _state(engine, task, key) == before


def test_an_unknown_task_is_403_and_the_denial_is_recorded(client, ids, sink):
    """The staff convention (`authorize_match_exists`): one answer for "not
    there" and "not yours", recorded (R6.3a)."""
    missing = uuid.uuid4()
    r = _complete(client, missing, {"outcome_code": CODES[0]}, ids.ACC_OPERATOR)
    assert (r.status_code, r.json()["code"]) == (403, "OBJECT_NOT_AUTHORIZED")
    [denied] = [x for x in sink.records if x.event.value == "DENIED"
                and x.operation_id == "postTasksTaskIdComplete"]
    assert (denied.resource_kind, denied.resource_id) == ("TASK", missing)


def test_both_rows_are_audited_and_the_note_is_withheld(client, engine, ids):
    """§3.7: the event and the task change each have an audit row; the note
    stays in its own row (R6.3b)."""
    task = _task(engine)
    note = "NOTE-" + uuid.uuid4().hex
    assert _complete(client, task, {"outcome_code": CODES[0], "note": note},
                     ids.ACC_OPERATOR).status_code == 200
    rows = _all(engine, """
        SELECT entity_table, action, old_row::text AS old_row, new_row::text AS new_row,
               actor_account_id
          FROM turab.audit_log
         WHERE entity_id = :t OR entity_id IN (SELECT task_completion_event_id
                 FROM turab.task_completion_events WHERE task_id = :t)
         ORDER BY audit_id""", t=task)
    assert [(r["entity_table"], r["action"]) for r in rows] == [
        ("task_completion_events", "INSERT"), ("tasks", "UPDATE")]
    assert all(r["actor_account_id"] == ids.ACC_OPERATOR for r in rows)
    event_row = json.loads(rows[0]["new_row"])
    assert "note" not in event_row and event_row["outcome_code"] == CODES[0]
    assert note not in json.dumps([dict(r) for r in rows], default=str)
    assert (json.loads(rows[1]["old_row"])["status"],
            json.loads(rows[1]["new_row"])["status"]) == ("OPEN", "DONE")
    assert _event(engine, task)["note"] == note, "the note is kept in the event"


def _facts(engine):
    """A digest of every table a completion must not change (G6-8 (v))."""
    out = {}
    for table in ("properties", "property_attributes", "property_offers", "requests",
                  "request_criteria", "claims", "claim_evidence", "verification_events",
                  "resolved_values", "consent_grants", "resource_consent_bindings",
                  "match_candidates", "match_criterion_results", "match_reviews",
                  "match_diagnostic_runs", "opportunities", "observations"):
        rows = _one(engine, f"SELECT coalesce(string_agg(t::text, '|' ORDER BY t::text), '') "
                            f"FROM turab.{table} t")
        out[table] = hashlib.sha256(rows.encode()).hexdigest()
    return out


def test_information_obtained_changes_no_fact(client, engine, ids):
    """G6-8 (ii) (a) and (v): a VERIFY_DOCUMENT task completed with
    TASK_INFORMATION_OBTAINED and an evidence observation changes no
    property, attribute, offer, request, claim, verification level, resolved
    value, consent, match, review, diagnostic, opportunity or observation."""
    m = _match(client, engine, ids, "DOCUMENT_UNKNOWN")
    assert _review(client, m["match_id"], {"decision": "NEED_MORE_INFORMATION",
                                          "reason_code": "DOCUMENT_NOT_KNOWN"},
                   ids.ACC_REVIEWER).status_code == 200
    # The review's task; the run's own diagnostic task on the same match is an
    # independent record (G6-4 (iv) (a), from step 4).
    [task] = _all(engine, "SELECT task_id, task_type::text AS t FROM turab.tasks "
                          "WHERE match_id = :m AND payload ? 'match_review_id'",
                  m=m["match_id"])
    assert task["t"] == "VERIFY_DOCUMENT"
    obs = _observation(engine, ids)
    before = _facts(engine)
    r = _complete(client, task["task_id"], {"outcome_code": "TASK_INFORMATION_OBTAINED",
                                            "evidence_observation_id": str(obs)},
                  ids.ACC_OPERATOR)
    assert r.status_code == 200, r.text
    assert _facts(engine) == before


# --- K05 and I02 -------------------------------------------------------------------------

def test_k05_a_replay_returns_the_first_response_and_writes_nothing(client, engine, ids):
    task, key = _task(engine), str(uuid.uuid4())
    body = {"outcome_code": CODES[0], "note": "first"}
    first = _complete(client, task, body, ids.ACC_OPERATOR, key)
    after = _state(engine, task, key)
    again = _complete(client, task, body, ids.ACC_OPERATOR, key)
    assert (again.status_code, again.json()) == (first.status_code, first.json())
    assert _state(engine, task, key) == after and after["events"] == 1
    other = _complete(client, task, {**body, "note": "second"}, ids.ACC_OPERATOR, key)
    assert (other.status_code, other.json()["code"]) == (409, "IDEMPOTENCY_KEY_CONFLICT")
    assert _state(engine, task, key) == after


def test_the_key_is_required(client, engine, ids):
    task = _task(engine)
    r = client.post(f"/tasks/{task}/complete", json={"outcome_code": CODES[0]},
                    headers={"Authorization": f"Bearer {ids.ACC_OPERATOR}"})
    assert (r.status_code, r.json()["code"]) == (400, "IDEMPOTENCY_KEY_REQUIRED")


def test_i02_a_failure_between_the_two_writes_leaves_neither(lenient, engine, ids,
                                                            monkeypatch):
    """The event and the DONE task land together or not at all: a failure
    injected after the event's insert and before the task's update leaves no
    event, an OPEN task, no audit row, and no key."""
    from turab.services import audit_rows

    task, key = _task(engine), str(uuid.uuid4())
    before = _state(engine, task, key)
    real = audit_rows.write

    def failing(session, table, *args, **kw):
        if table == "task_completion_events":
            real(session, table, *args, **kw)
            raise RuntimeError("injected between the event and the task")
        return real(session, table, *args, **kw)
    monkeypatch.setattr(audit_rows, "write", failing)
    r = _complete(lenient, task, {"outcome_code": CODES[0]}, ids.ACC_OPERATOR, key)
    assert (r.status_code, r.json()["code"]) == (500, "INTERNAL_ERROR")
    assert _state(engine, task, key) == before and before["status"] == "OPEN"


def test_a_guard_message_never_reaches_the_response(lenient, engine, ids, monkeypatch):
    """Part D's message carries the observation id (step 1, §1). Forced to
    fire inside the command, it leaves as INTERNAL_ERROR, with neither the
    id nor the message, and the command writes nothing."""
    task, obs, key = _task(engine), _observation(engine, ids), str(uuid.uuid4())
    before = _state(engine, task, key)
    real = task_service.record

    def rewriting(session, prepared, **kw):
        out = real(session, prepared, **kw)
        session.execute(text("UPDATE turab.observations SET raw_text = 'X' "
                             "WHERE observation_id = :o"), {"o": obs})
        return out
    monkeypatch.setattr(task_service, "record", rewriting)
    r = _complete(lenient, task, {"outcome_code": CODES[0],
                                  "evidence_observation_id": str(obs)}, ids.ACC_OPERATOR, key)
    assert (r.status_code, r.json()["code"]) == (500, "INTERNAL_ERROR")
    assert str(obs) not in r.text and CITED not in r.text
    assert _state(engine, task, key) == before and _body_of(engine, obs) == BODY


# ======================================================================================
# G6-8 (iv): the lock order, and the race with a change of the cited observation
# ======================================================================================

def _blocked_by(engine, pid):
    return [r["pid"] for r in _all(engine, """
        SELECT pid FROM pg_stat_activity
         WHERE pid <> :w AND wait_event_type = 'Lock'
           AND :w = ANY(pg_blocking_pids(pid))""", w=pid)]


def _watch(engine, pid, thread, seconds=60.0):
    """Until a backend waits on `pid`, or `thread` ends: True if one waited.

    The cap is a safety net, not the measure. An 8 s window once closed
    while the thread, delayed by a stall outside the database, had not yet
    reached its lock: the behaviour was right and the witness failed
    (`evidence/SLICE6-STEP2-R2D-WITNESS.txt`). A thread that takes no lock
    ends at once, so the witness is False at once (mutations L1-L3)."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _blocked_by(engine, pid):
            return True
        if not thread.is_alive():
            return False
        time.sleep(0.02)
    return False


def _in_thread(engine, out, name, call):
    from turab.app import create_app

    def run():
        with TestClient(create_app(engine=engine)) as c:
            out[name] = call(c)
    t = threading.Thread(target=run)
    t.start()
    return t


def _change_in_thread(engine, out, sql, obs):
    """U: one statement on the observation, in its own transaction."""
    def run():
        try:
            with engine.begin() as conn:
                out["u_pid"] = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
                conn.execute(text(sql), {"o": obs})
            out["u"] = "COMMITTED"
        except DBAPIError as exc:
            out["u"] = "REFUSED: " + str(exc.orig).splitlines()[0]
    t = threading.Thread(target=run)
    t.start()
    return t


UPDATE_BODY = "UPDATE turab.observations SET raw_text = 'CHANGED' WHERE observation_id = :o"
DELETE_IT = "DELETE FROM turab.observations WHERE observation_id = :o"


def _hold_after_the_observation_lock(monkeypatch, out, locked, release):
    real = task_service._lock_observation

    def held(session, observation_id):
        found = real(session, observation_id)
        out["c_pid"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        locked.set()
        assert release.wait(30), "the completion was never released"
        return found
    monkeypatch.setattr(task_service, "_lock_observation", held)


@pytest.mark.parametrize("change, label", [(UPDATE_BODY, "R2a"), (DELETE_IT, "R2c")])
def test_r2a_r2c_a_change_after_the_lock_waits_and_is_refused(engine, ids, monkeypatch,
                                                            change, label):
    """C first. C holds the observation FOR SHARE and has not committed. U, an
    UPDATE of the body (R2a) or a DELETE (R2c), must wait on C (witness), and
    once C commits, part D refuses it. The event cites the body C read.
    Without the FOR SHARE, R2a is R1a: U does not wait, both commit, and the
    cited body is changed after the citation."""
    task, obs = _task(engine), _observation(engine, ids)
    out, locked, release = {}, threading.Event(), threading.Event()
    _hold_after_the_observation_lock(monkeypatch, out, locked, release)
    c = _in_thread(engine, out, "c", lambda cl: _complete(
        cl, task, {"outcome_code": CODES[0], "evidence_observation_id": str(obs)},
        ids.ACC_OPERATOR))
    u = None
    try:
        assert locked.wait(30), "the completion never locked the observation"
        u = _change_in_thread(engine, out, change, obs)
        waited = _watch(engine, out["c_pid"], u)
        u_ended_while_held = not u.is_alive()
    finally:
        release.set()
        c.join(30)
        if u is not None:
            u.join(30)
    observed = {
        "u_waited_on_c": waited, "u_ended_while_c_held": u_ended_while_held,
        "c": out["c"].status_code, "u_refused_by_part_d": CITED in out.get("u", ""),
        "cited": _event(engine, task)["evidence_observation_id"] == obs,
        "body": _body_of(engine, obs),
    }
    assert observed == {"u_waited_on_c": True, "u_ended_while_c_held": False, "c": 200,
                        "u_refused_by_part_d": True, "cited": True, "body": BODY}, (
        label, observed)


def _u_first(engine, sql, obs):
    """U's transaction, opened and holding its row lock, not yet committed."""
    conn = engine.connect()
    tx = conn.begin()
    pid = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
    conn.execute(text(sql), {"o": obs})
    return conn, tx, pid


def test_r2b_an_update_before_the_lock_is_the_body_cited(engine, ids):
    """U first, an UPDATE, uncommitted. C must wait on U (witness). Once U
    commits, C reads the changed body and cites it; part D then refuses any
    later change."""
    task, obs = _task(engine), _observation(engine, ids)
    conn, tx, u_pid = _u_first(engine, UPDATE_BODY, obs)
    out = {}
    try:
        c = _in_thread(engine, out, "c", lambda cl: _complete(
            cl, task, {"outcome_code": CODES[0], "evidence_observation_id": str(obs)},
            ids.ACC_OPERATOR))
        waited = _watch(engine, u_pid, c)
        c_ended_while_u_held = not c.is_alive()
        tx.commit()
    finally:
        conn.close()
    c.join(30)
    later = _change_in_thread(engine, out, "UPDATE turab.observations SET raw_text = 'LATER' "
                                           "WHERE observation_id = :o", obs)
    later.join(30)
    observed = {
        "c_waited_on_u": waited, "c_ended_while_u_held": c_ended_while_u_held,
        "c": out["c"].status_code,
        "cited": _event(engine, task)["evidence_observation_id"] == obs,
        "body": _body_of(engine, obs), "later_refused": CITED in out["u"],
    }
    assert observed == {"c_waited_on_u": True, "c_ended_while_u_held": False, "c": 200,
                        "cited": True, "body": "CHANGED", "later_refused": True}, observed


def test_r2d_a_delete_before_the_lock_is_refused_typed_writing_nothing(engine, ids):
    """U first, a DELETE, uncommitted. C must wait on U (witness). Once U
    commits, C's read finds no row: 422 EVIDENCE_OBSERVATION_NOT_FOUND, no
    event, the task OPEN, no audit row, no key consumed."""
    task, obs, key = _task(engine), _observation(engine, ids), str(uuid.uuid4())
    before = _state(engine, task, key)
    conn, tx, u_pid = _u_first(engine, DELETE_IT, obs)
    out = {}
    try:
        c = _in_thread(engine, out, "c", lambda cl: _complete(
            cl, task, {"outcome_code": CODES[0], "evidence_observation_id": str(obs)},
            ids.ACC_OPERATOR, key))
        waited = _watch(engine, u_pid, c)
        c_ended_while_u_held = not c.is_alive()
        tx.commit()
    finally:
        conn.close()
    c.join(30)
    observed = {
        "c_waited_on_u": waited, "c_ended_while_u_held": c_ended_while_u_held,
        "c": (out["c"].status_code, out["c"].json()["code"]),
        "state_unchanged": _state(engine, task, key) == before,
        "observation_gone": _body_of(engine, obs) is None,
        "id_not_echoed": str(obs) not in out["c"].text,
    }
    assert observed == {"c_waited_on_u": True, "c_ended_while_u_held": False,
                        "c": (422, "EVIDENCE_OBSERVATION_NOT_FOUND"),
                        "state_unchanged": True, "observation_gone": True,
                        "id_not_echoed": True}, observed


def test_the_task_is_locked_before_the_observation(engine, ids):
    """G6-8 (iv)'s order. Another transaction holds the task FOR UPDATE. The
    completion waits on it (witness) and, while it waits, holds NO lock on
    the observation: an UPDATE of the observation under a 1 s lock timeout
    goes through at once (then rolled back). Released, the completion
    proceeds and cites the unchanged body."""
    task, obs = _task(engine), _observation(engine, ids)
    conn = engine.connect()
    tx = conn.begin()
    holder = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
    conn.execute(text("SELECT 1 FROM turab.tasks WHERE task_id = :t FOR UPDATE"), {"t": task})
    out = {}
    try:
        c = _in_thread(engine, out, "c", lambda cl: _complete(
            cl, task, {"outcome_code": CODES[0], "evidence_observation_id": str(obs)},
            ids.ACC_OPERATOR))
        waited = _watch(engine, holder, c)
        with engine.connect() as probe:
            ptx = probe.begin()
            probe.execute(text("SET LOCAL lock_timeout = '1s'"))
            try:
                probe.execute(text(UPDATE_BODY), {"o": obs})
                observation_free = True
            except DBAPIError:
                observation_free = False
            ptx.rollback()
        tx.rollback()
    finally:
        conn.close()
    c.join(30)
    assert {"waited_on_the_task": waited, "observation_free_while_waiting": observation_free,
            "c": out["c"].status_code, "body": _body_of(engine, obs)} == {
        "waited_on_the_task": True, "observation_free_while_waiting": True, "c": 200,
        "body": BODY}


def test_a_second_concurrent_completion_waits_and_is_refused(engine, ids, monkeypatch):
    """F6-17, E4, under READ COMMITTED. The first completion holds the task,
    DONE but uncommitted. The second waits on it (witness), then reads DONE:
    409 TASK_NOT_OPEN, one event, the second key not consumed."""
    task, key = _task(engine), str(uuid.uuid4())
    out, wrote, release = {}, threading.Event(), threading.Event()
    real = task_service.record

    def held(session, prepared, **kw):
        result = real(session, prepared, **kw)
        if not wrote.is_set():
            out["first_pid"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
            wrote.set()
            assert release.wait(30), "the first completion was never released"
        return result
    monkeypatch.setattr(task_service, "record", held)
    first = _in_thread(engine, out, "first", lambda cl: _complete(
        cl, task, {"outcome_code": CODES[0]}, ids.ACC_OPERATOR))
    second = None
    try:
        assert wrote.wait(30), "the first completion never wrote"
        second = _in_thread(engine, out, "second", lambda cl: _complete(
            cl, task, {"outcome_code": CODES[1]}, ids.ACC_REVIEWER, key))
        waited = _watch(engine, out["first_pid"], second)
    finally:
        release.set()
        first.join(30)
        if second is not None:
            second.join(30)
    state = _state(engine, task, key)
    assert {"waited": waited, "first": out["first"].status_code,
            "second": (out["second"].status_code, out["second"].json()["code"]),
            "events": state["events"], "key": state["key"],
            "outcome": _event(engine, task)["outcome_code"]} == {
        "waited": True, "first": 200, "second": (409, "TASK_NOT_OPEN"), "events": 1,
        "key": 0, "outcome": CODES[0]}


# ======================================================================================
# CORRECTION-005: the same bodies through the effective schema and the route
# ======================================================================================

_KEYWORDS = {"type", "additionalProperties", "properties", "required", "enum", "format"}


def _schema_accepts(schema, body) -> bool:
    """The effective schema's verdict, for the keywords it uses, and only
    those: the test below asserts it uses no other."""
    def of_type(value, declared):
        types = declared if isinstance(declared, list) else [declared]
        return any({"string": isinstance(value, str), "null": value is None,
                    "object": isinstance(value, dict)}[t] for t in types)

    def field_ok(field_schema, value):
        if not of_type(value, field_schema["type"]):
            return False
        if "enum" in field_schema and value not in field_schema["enum"]:
            return False
        if field_schema.get("format") == "uuid" and isinstance(value, str):
            try:
                uuid.UUID(value)
            except ValueError:
                return False
        return True
    if not of_type(body, schema["type"]):
        return False
    if any(f not in body for f in schema.get("required", [])):
        return False
    if schema.get("additionalProperties") is False and set(body) - set(schema["properties"]):
        return False
    return all(field_ok(schema["properties"][f], v) for f, v in body.items())


BODIES = [
    ("absent", {}),
    ("null", {"outcome_code": None}),
    ("an empty string", {"outcome_code": ""}),
    *[(code, {"outcome_code": code}) for code in CODES],
    ("a seeded general code", {"outcome_code": "OTHER"}),
    ("an opportunity code", {"outcome_code": "DEAL_CONFIRMED"}),
    ("an unknown code", {"outcome_code": "NOT_A_CODE"}),
    ("a number", {"outcome_code": 1}),
    ("an undeclared field", {"outcome_code": CODES[0], "extra": True}),
    ("a note of null", {"outcome_code": CODES[0], "note": None}),
    ("a malformed observation id", {"outcome_code": CODES[0],
                                    "evidence_observation_id": "not-a-uuid"}),
]


def test_the_effective_schema_uses_only_the_keywords_checked_here():
    schema = effective_request_body("postTasksTaskIdComplete")
    used = set(schema) | {k for f in schema["properties"].values() for k in f}
    assert used <= _KEYWORDS, used - _KEYWORDS


@pytest.mark.parametrize("label, body", BODIES, ids=[b[0] for b in BODIES])
def test_the_route_refuses_exactly_what_the_effective_schema_refuses(client, engine, ids,
                                                                    label, body):
    schema = effective_request_body("postTasksTaskIdComplete")
    task, key = _task(engine), str(uuid.uuid4())
    before = _state(engine, task, key)
    r = _complete(client, task, body, ids.ACC_OPERATOR, key)
    expected = _schema_accepts(schema, body)
    assert (r.status_code == 200) is expected, (label, r.status_code, r.text)
    if not expected:
        assert (r.status_code, r.json()["code"]) == (422, "VALIDATION_FAILED")
        assert _state(engine, task, key) == before
        if isinstance(body.get("outcome_code"), str) and body["outcome_code"]:
            assert body["outcome_code"] not in r.text, "the value is not echoed"


# ======================================================================================
# G6-9: the list
# ======================================================================================

def _all_pages(client, account, **params):
    items, page = [], 1
    while True:
        r = _list(client, account, page=page, page_size=100, **params)
        assert r.status_code == 200, r.text
        body = r.json()
        items += body["items"]
        if page * 100 >= body["meta"]["total"]:
            return items, body["meta"]
        page += 1


def test_the_list_is_ordered_by_priority_then_creation_then_id(client, engine, ids):
    mine = [_task(engine, priority=p) for p in ("LOW", "URGENT", "NORMAL", "HIGH", "URGENT")]
    items, meta = _all_pages(client, ids.ACC_OPERATOR)
    assert meta["total"] == len(items)
    rank = {"URGENT": 0, "HIGH": 1, "NORMAL": 2, "LOW": 3}
    created = {r["task_id"]: r["created_at"] for r in _all(
        engine, "SELECT task_id::text AS task_id, created_at FROM turab.tasks")}
    keys = [(rank[i["priority"]], created[i["task_id"]], i["task_id"]) for i in items]
    assert keys == sorted(keys)
    listed = [i["task_id"] for i in items if uuid.UUID(i["task_id"]) in mine]
    assert len(listed) == len(mine)


def test_status_and_priority_are_compared_as_text(client, engine, ids):
    """G6-9: a value naming no status or priority returns nothing, not a 422."""
    done = _task(engine, status="DONE", priority="LOW")
    for params in ({"status": "NOT_A_STATUS"}, {"priority": "nope"}, {"status": "done"}):
        r = _list(client, ids.ACC_OPERATOR, **params)
        assert r.status_code == 200 and r.json()["items"] == [], params
        assert r.json()["meta"]["total"] == 0
    items, _ = _all_pages(client, ids.ACC_OPERATOR, status="DONE", priority="LOW")
    assert {i["status"] for i in items} == {"DONE"} and {i["priority"] for i in items} == {
        "LOW"}
    assert str(done) in {i["task_id"] for i in items}


def test_assigned_to_me_keeps_the_callers_tasks_only(client, engine, ids):
    """No contract command assigns a task (F6-7); the assignment is a fixture
    written in SQL."""
    for_operator = _task(engine, assigned=ids.ACC_OPERATOR)
    for_reviewer = _task(engine, assigned=ids.ACC_REVIEWER)
    mine, _ = _all_pages(client, ids.ACC_OPERATOR, assigned_to_me="true")
    theirs, _ = _all_pages(client, ids.ACC_REVIEWER, assigned_to_me="true")
    assigned = {r["task_id"]: r["a"] for r in _all(
        engine, "SELECT task_id::text AS task_id, assigned_account_id AS a FROM turab.tasks")}
    assert {assigned[i["task_id"]] for i in mine} == {ids.ACC_OPERATOR}
    assert {assigned[i["task_id"]] for i in theirs} == {ids.ACC_REVIEWER}
    assert str(for_operator) in {i["task_id"] for i in mine}
    assert str(for_reviewer) not in {i["task_id"] for i in mine}


def test_paging_follows_the_contract(client, engine, ids):
    for _ in range(3):
        _task(engine, priority="URGENT")
    r = _list(client, ids.ACC_OPERATOR, page=2, page_size=2)
    body = r.json()
    assert r.status_code == 200 and len(body["items"]) == 2
    assert (body["meta"]["page"], body["meta"]["page_size"]) == (2, 2)
    for bad in ({"page": 0}, {"page_size": 0}, {"page_size": 101}):
        r = _list(client, ids.ACC_OPERATOR, **bad)
        assert (r.status_code, r.json()["code"]) == (422, "VALIDATION_FAILED"), bad


def test_the_list_read_is_audited_once_with_its_count(client, engine, ids, sink):
    _task(engine)
    r = _list(client, ids.ACC_REVIEWER, page_size=5)
    [listed] = [x for x in sink.records if x.event.value == "LIST"
                and x.operation_id == "getTasks"]
    assert listed.result_count == len(r.json()["items"]) and listed.resource_id is None
    assert listed.resource_kind == "TASK"


def test_every_writers_task_is_listed_and_no_payload_carries_a_private_value(
        client, engine, ids):
    """G6-9: tasks of every writer are returned. The NMI task is the review
    command's own; the identity task is `identity.raise_review_work`'s, called
    on a real open match; the diagnostic task is a fixture of step 4's
    payload shape (its writer is step 4's). No seller expectation, claim
    value or free text reaches the list."""
    from sqlalchemy.orm import Session

    from turab.services import identity

    m = _match(client, engine, ids, "DOCUMENT_UNKNOWN")
    expectation = 23_456_789
    _exec(engine, "UPDATE turab.property_offers SET seller_expectation_dzd = :e "
                  "WHERE offer_id = :o", e=expectation, o=m["evaluated_offer_id"])
    reason_text = "REASON-TEXT-" + uuid.uuid4().hex
    assert _review(client, m["match_id"], {"decision": "NEED_MORE_INFORMATION",
                                          "reason_code": "DOCUMENT_NOT_KNOWN",
                                          "reason_text": reason_text},
                   ids.ACC_REVIEWER).status_code == 200
    [nmi] = _all(engine, "SELECT task_id::text AS t FROM turab.tasks WHERE match_id = :m "
                         "AND payload ? 'match_review_id'", m=m["match_id"])
    with Session(bind=engine) as s, s.begin():
        [resolve] = identity.raise_review_work(
            s, alias=uuid.UUID(m["property_id"]), canonical=ids.ASSISTED_APARTMENT,
            candidate_id=uuid.uuid4())
    diagnostic = _task(engine, request=ids.REQ_AMINA, payload={
        "source": "DIAGNOSTIC", "subject": {"entity": "PROPERTY_OFFER", "id": str(uuid.uuid4()),
                                            "gate": "INFORMATION", "basis": "B"}})
    items, _ = _all_pages(client, ids.ACC_ADMIN)
    listed = {i["task_id"] for i in items}
    assert {nmi["t"], str(resolve), str(diagnostic)} <= listed
    rendered = json.dumps(items)
    for private in (reason_text, str(expectation), "23456789", "BODY-AT-CITATION"):
        assert private not in rendered, private


# ======================================================================================
# §6.3: authorization
# ======================================================================================

@pytest.mark.parametrize("who", ["ACC_ADMIN", "ACC_OPERATOR", "ACC_REVIEWER"])
def test_each_staff_role_lists_and_completes(client, engine, ids, who):
    assert _list(client, getattr(ids, who)).status_code == 200
    task = _task(engine)
    assert _complete(client, task, {"outcome_code": CODES[0]}, getattr(ids, who)
                     ).status_code == 200


def test_a_customer_is_refused_both_and_the_refusal_is_recorded(client, engine, ids, sink):
    task, key = _task(engine), str(uuid.uuid4())
    before = _state(engine, task, key)
    r = _list(client, ids.ACC_AMINA)
    assert (r.status_code, r.json()["code"]) == (403, "ROLE_NOT_PERMITTED")
    r = _complete(client, task, {"outcome_code": CODES[0]}, ids.ACC_AMINA, key)
    assert (r.status_code, r.json()["code"]) == (403, "ROLE_NOT_PERMITTED")
    assert _state(engine, task, key) == before
    denied = {x.operation_id for x in sink.records if x.event.value == "DENIED"
              and x.actor_account_id == ids.ACC_AMINA}
    assert {"getTasks", "postTasksTaskIdComplete"} <= denied


def test_an_anonymous_caller_is_refused_both(client, engine):
    task = _task(engine)
    assert client.get("/tasks").status_code == 401
    r = client.post(f"/tasks/{task}/complete", json={"outcome_code": CODES[0]},
                    headers={"Idempotency-Key": str(uuid.uuid4())})
    assert (r.status_code, r.json()["code"]) == (401, "UNAUTHENTICATED")
