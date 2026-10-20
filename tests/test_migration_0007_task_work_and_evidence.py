"""0007 — task work and its evidence (Slice 6 step 1).

Ref: `db/migrations/versions/0007_task_work_and_evidence.py`;
`docs/gate/SLICE_6_PLAN.md` revision 4, §5.1 parts A–D (approved in the
review of bd54216), G6-4 (iii), G6-8 (ii) (a) and (iv) (a);
`docs/gate/evidence/SLICE6-PLAN-MEASUREMENTS.txt` §T4 and §E, and
`SLICE6-PLAN-MEASUREMENTS-R3.txt` R1, the measurements taken BEFORE this
revision.

The guards are in the DATABASE, so these tests write directly: they must hold
for every writer, not only for the Slice 6 commands, which do not exist yet.
Tasks, events and observations here are fixtures.

Each refused write is tested next to the writes that must still succeed. A
guard that refused everything would otherwise pass.

Proven at trigger level only, under the application role, which is a
superuser owning every table (EN-02). Not a claim about K06.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

#: `prevent_immutable_history_change()`, the frozen function part A reuses.
IMMUTABLE = "Historical TURAB record is immutable"
#: `prevent_cited_observation_change()`, part D.
CITED = "is the evidence of a task completion and cannot change"
INDEX = "ux_one_open_task_per_subject"

CODES = {
    "TASK_INFORMATION_OBTAINED": ("تم الحصول على المعلومة المطلوبة",
                                  "The information asked for was obtained"),
    "TASK_INFORMATION_UNAVAILABLE": ("تعذر الحصول على المعلومة المطلوبة",
                                     "The information asked for could not be obtained"),
    "TASK_PARTY_UNREACHABLE": ("تعذر الوصول إلى الطرف", "The party could not be reached"),
    "TASK_NO_LONGER_NEEDED": ("لم تعد المهمة لازمة", "The task is no longer needed"),
}


def _one(session, sql, **p):
    return session.execute(text(sql), p).scalar_one()


def _refused(session, sql, *messages, **p):
    """Run `sql` under a savepoint; it must be refused with one of `messages`."""
    savepoint = session.begin_nested()
    with pytest.raises(DBAPIError) as caught:
        session.execute(text(sql), p)
    savepoint.rollback()
    assert any(m in str(caught.value) for m in messages), caught.value
    return caught.value


def _accepted(session, sql, **p):
    savepoint = session.begin_nested()
    session.execute(text(sql), p)
    savepoint.commit()


def _observation(session, ids, *, source=None, party=None, recorded_by=None):
    return _one(session, """
        INSERT INTO turab.observations (source_id, kind, party_id, raw_text, payload,
                                        recorded_by_account_id)
        VALUES (:s, 'CALL_NOTE', :p, 'BODY-AT-CITATION', '{"document": "LAND_BOOK"}', :a)
        RETURNING observation_id""", s=source, p=party,
        a=ids.ACC_OPERATOR if recorded_by is None else recorded_by)


def _task(session, *, payload=None, status="OPEN", request=None):
    return _one(session, """
        INSERT INTO turab.tasks (task_type, priority, status, title, request_id, payload)
        VALUES ('VERIFY_DOCUMENT', 'HIGH', CAST(:s AS turab.task_status), 'fixture', :r,
                CAST(:p AS jsonb))
        RETURNING task_id""", s=status, r=request,
        p=json.dumps(payload or {}))


EVENT = """INSERT INTO turab.task_completion_events
               (task_id, outcome_code, note, evidence_observation_id, completed_by_account_id)
           VALUES (:t, :c, 'called the seller', :o, :a)
           RETURNING task_completion_event_id"""


def _event(session, ids, task, obs=None, code=None):
    """An event with no outcome code by default, which the frozen schema accepts,
    so that parts A and D are tested without depending on part B's codes."""
    return _one(session, EVENT, t=task, c=code, o=obs, a=ids.ACC_OPERATOR)


# ======================================================================================
# Part A — completion events are append-only
# ======================================================================================

@pytest.mark.parametrize("assignment", [
    "note = 'rewritten'",
    "note = NULL",
    "outcome_code = 'OTHER'",
    "outcome_code = NULL",
    "evidence_observation_id = NULL",
    "completed_by_account_id = :other",
    "completed_at = completed_at - interval '1 day'",
    "task_id = :other_task",
])
def test_a_completion_event_cannot_be_updated(session, ids, assignment):
    obs = _observation(session, ids)
    event = _event(session, ids, _task(session), obs)
    _refused(session, f"UPDATE turab.task_completion_events SET {assignment} "
                      "WHERE task_completion_event_id = :e", IMMUTABLE,
             e=event, other=ids.ACC_REVIEWER, other_task=_task(session))


def test_a_completion_event_cannot_be_deleted(session, ids):
    event = _event(session, ids, _task(session))
    _refused(session, "DELETE FROM turab.task_completion_events "
                      "WHERE task_completion_event_id = :e", IMMUTABLE, e=event)


def test_a_completion_event_can_still_be_appended(session, ids):
    """The guard refuses rewriting, never appending: a second event for the same
    task, with and without evidence, is accepted."""
    task = _task(session)
    _event(session, ids, task, _observation(session, ids))
    _accepted(session, EVENT, t=task, c=None, o=None, a=ids.ACC_OPERATOR)
    assert _one(session, "SELECT count(*) FROM turab.task_completion_events "
                         "WHERE task_id = :t", t=task) == 2


def test_part_a_alone_refuses_the_set_null_of_a_deleted_observation(session, ids):
    """Measured before this revision (F6-16, E2): with the event append-only, the
    FK's ON DELETE SET NULL is an UPDATE of the event, which part A refuses. Part
    D refuses the same DELETE first, with its own message, so part D is disabled
    here, inside this rolled-back transaction, to prove part A on its own.

    It uses the superuser's ability to disable a trigger (EN-02) to TEST a guard.
    It is not a claim about K06."""
    obs = _observation(session, ids)
    _event(session, ids, _task(session), obs)
    session.execute(text(
        "ALTER TABLE turab.observations DISABLE TRIGGER trg_cited_observation_unchanged"))
    _refused(session, "DELETE FROM turab.observations WHERE observation_id = :o",
             IMMUTABLE, o=obs)


# ======================================================================================
# Part B — the task outcome codes
# ======================================================================================

def test_the_four_task_outcome_codes_are_seeded_exactly(session):
    rows = session.execute(text("""
        SELECT code, label_ar, label_en, active FROM turab.reason_codes
         WHERE category = 'TASK_OUTCOME' ORDER BY code""")).all()
    assert {r.code: (r.label_ar, r.label_en) for r in rows} == CODES
    assert all(r.active for r in rows)


def test_no_task_outcome_code_existed_before_under_another_category(session):
    """Part B inserts with WHERE NOT EXISTS: a code already present under another
    category would be silently kept. None is."""
    assert _one(session, """SELECT count(*) FROM turab.reason_codes
                             WHERE code = ANY(:c) AND category <> 'TASK_OUTCOME'""",
                c=list(CODES)) == 0


@pytest.mark.parametrize("code", sorted(CODES))
def test_a_completion_event_accepts_each_outcome_code(session, ids, code):
    _accepted(session, EVENT, t=_task(session), c=code, o=None, a=ids.ACC_OPERATOR)


# ======================================================================================
# Part C — one open task per subject of work (diagnostic tasks only)
# ======================================================================================

def _subject(**overrides):
    subject = {"entity": "PROPERTY_OFFER", "id": str(uuid.uuid4()), "gate": "INFORMATION",
               "criterion": "BUDGET_MAX", "ordinal": 1,
               "basis": "PRICE_ABOVE_MAX_NEGOTIATION_UNCONFIRMED"}
    subject.update(overrides)
    return {k: v for k, v in subject.items() if v is not None}


def _diagnostic(subject, **extra):
    return {"source": "DIAGNOSTIC", "subject": subject, **extra}


def test_the_index_is_the_approved_text(session):
    definition = _one(session, """SELECT indexdef FROM pg_indexes
                                   WHERE schemaname = 'turab' AND indexname = :i""", i=INDEX)
    for part in ("CREATE UNIQUE INDEX ux_one_open_task_per_subject ON turab.tasks",
                 "'OPEN'", "'IN_PROGRESS'", "'source'::text", "'DIAGNOSTIC'::text",
                 "'entity'::text", "'id'::text", "'gate'::text", "'criterion'::text",
                 "'ordinal'::text", "'basis'::text", "request_id"):
        assert part in definition, (part, definition)


@pytest.mark.parametrize("first,second", [
    ("OPEN", "OPEN"),
    ("OPEN", "IN_PROGRESS"),
    ("IN_PROGRESS", "OPEN"),
    ("IN_PROGRESS", "IN_PROGRESS"),
])
def test_the_same_open_work_is_refused(session, ids, first, second):
    subject = _subject()
    _task(session, payload=_diagnostic(subject), status=first, request=ids.REQ_AMINA)
    _refused(session, """INSERT INTO turab.tasks (task_type, status, title, request_id, payload)
                          VALUES ('CONFIRM_PRICE', CAST(:s AS turab.task_status), 't', :r,
                                  CAST(:p AS jsonb))""", INDEX,
             s=second, r=ids.REQ_AMINA, p=json.dumps(_diagnostic(subject)))


def test_moving_an_open_task_to_in_progress_keeps_its_work_taken(session, ids):
    """F6-15 (T4): with OPEN alone in the predicate, a task taken up let a second
    OPEN task in. Here the first moves to IN_PROGRESS, and a second is refused."""
    subject = _subject()
    task = _task(session, payload=_diagnostic(subject), request=ids.REQ_AMINA)
    _accepted(session, "UPDATE turab.tasks SET status = 'IN_PROGRESS' WHERE task_id = :t",
              t=task)
    _refused(session, """INSERT INTO turab.tasks (task_type, title, request_id, payload)
                          VALUES ('CONFIRM_PRICE', 't', :r, CAST(:p AS jsonb))""", INDEX,
             r=ids.REQ_AMINA, p=json.dumps(_diagnostic(subject)))


@pytest.mark.parametrize("closed", ["DONE", "CANCELLED"])
def test_work_closed_may_be_raised_again(session, ids, closed):
    subject = _subject()
    _task(session, payload=_diagnostic(subject), status=closed, request=ids.REQ_AMINA)
    _accepted(session, """INSERT INTO turab.tasks (task_type, title, request_id, payload)
                           VALUES ('CONFIRM_PRICE', 't', :r, CAST(:p AS jsonb))""",
              r=ids.REQ_AMINA, p=json.dumps(_diagnostic(subject)))


@pytest.mark.parametrize("component", [
    "request", "entity", "id", "gate", "criterion", "ordinal", "basis"])
def test_each_component_of_the_key_separates_two_subjects(session, ids, component):
    """F6-13: two offers of one property, or two reasons of one offer, are two
    subjects. Each component of the key, changed alone, admits a second task."""
    subject = _subject()
    _task(session, payload=_diagnostic(subject), request=ids.REQ_AMINA)
    other, request = dict(subject), ids.REQ_AMINA
    if component == "request":
        request = ids.REQ_KHADIJA
    elif component == "ordinal":
        other["ordinal"] = 2
    elif component == "entity":
        other["entity"] = "PROPERTY"
    elif component == "id":
        other["id"] = str(uuid.uuid4())
    elif component == "gate":
        other["gate"] = "FRESHNESS"
    elif component == "criterion":
        other["criterion"] = "DOCUMENT_TYPE"
    else:
        other["basis"] = "STALE"
    _accepted(session, """INSERT INTO turab.tasks (task_type, title, request_id, payload)
                           VALUES ('CONFIRM_PRICE', 't', :r, CAST(:p AS jsonb))""",
              r=request, p=json.dumps(_diagnostic(other)))


def test_a_subject_without_criterion_or_ordinal_is_still_one_key(session, ids):
    """A FRESHNESS or PERMISSION subject names no criterion. The coalesce makes
    two such subjects equal, rather than two NULLs that never conflict."""
    subject = _subject(gate="FRESHNESS", criterion=None, ordinal=None, basis="STALE")
    _task(session, payload=_diagnostic(subject), request=ids.REQ_AMINA)
    _refused(session, """INSERT INTO turab.tasks (task_type, title, request_id, payload)
                          VALUES ('CONFIRM_PRICE', 't', :r, CAST(:p AS jsonb))""", INDEX,
             r=ids.REQ_AMINA, p=json.dumps(_diagnostic(subject)))


@pytest.mark.parametrize("payload", [
    # the same subject, without "source"
    lambda s: {"subject": s},
    # another source
    lambda s: {"source": "REVIEW", "subject": s},
    # Slice 5's NMI task: {match_review_id, next_action}
    lambda s: {"match_review_id": str(uuid.uuid4()),
               "next_action": {"type": "CONFIRM_PRICE", "subject": s}},
    # Slice 3's identity task
    lambda s: {"alias_property_id": str(uuid.uuid4()), "affected": "MATCH"},
], ids=["no-source", "other-source", "nmi-task", "identity-task"])
def test_tasks_of_the_other_writers_are_outside_the_index(session, ids, payload):
    """G6-4 (iii) and (iv) (a): only the run's tasks are deduplicated. An NMI task
    records a reviewer's request, and G5-4 (a) makes a repeated NMI a second
    task; Slice 3's tasks are unchanged."""
    subject = _subject()
    for _ in range(2):
        _accepted(session, """INSERT INTO turab.tasks (task_type, title, request_id, payload)
                               VALUES ('CONFIRM_PRICE', 't', :r, CAST(:p AS jsonb))""",
                  r=ids.REQ_AMINA, p=json.dumps(payload(subject)))


def test_a_diagnostic_task_with_no_request_is_not_deduplicated(session):
    """Pinned, not endorsed: the approved index does not use NULLS NOT DISTINCT,
    so two NULL request ids never conflict (PostgreSQL 16 documentation, §11.6).
    The run always sets `request_id` (its own request); step 4's tests assert
    it. This test keeps the property visible."""
    subject = _subject()
    for _ in range(2):
        _accepted(session, """INSERT INTO turab.tasks (task_type, title, payload)
                               VALUES ('CONFIRM_PRICE', 't', CAST(:p AS jsonb))""",
                  p=json.dumps(_diagnostic(subject)))


def test_a_diagnostic_subject_without_basis_is_not_deduplicated(session, ids):
    """Pinned, not endorsed (review of b6a08e7, M-1): only `criterion` and
    `ordinal` are coalesced, so a subject without `basis` has a NULL key
    component and never conflicts (PostgreSQL 16 documentation, §11.6).
    `entity`, `id` and `gate` are uncoalesced too; only `basis` is measured
    (`SLICE6-STEP1-ADDENDUM-INDEX-LIMITS.txt`). Step 4's tests assert that
    the run writes all four."""
    subject = _subject(basis=None)
    for _ in range(2):
        _accepted(session, """INSERT INTO turab.tasks (task_type, title, request_id, payload)
                               VALUES ('CONFIRM_PRICE', 't', :r, CAST(:p AS jsonb))""",
                  r=ids.REQ_AMINA, p=json.dumps(_diagnostic(subject)))


def test_a_source_spelled_otherwise_is_outside_the_index(session, ids):
    """Pinned, not endorsed (review of b6a08e7, M-1): the predicate compares
    `source` with 'DIAGNOSTIC' exactly, so 'diagnostic' puts the task outside
    the index. Step 4's tests assert that the run writes 'DIAGNOSTIC'."""
    subject = _subject()
    for _ in range(2):
        _accepted(session, """INSERT INTO turab.tasks (task_type, title, request_id, payload)
                               VALUES ('CONFIRM_PRICE', 't', :r, CAST(:p AS jsonb))""",
                  r=ids.REQ_AMINA, p=json.dumps({"source": "diagnostic", "subject": subject}))


@pytest.fixture
def two_engines(database_url):
    a = create_engine(database_url, future=True)
    b = create_engine(database_url, future=True)
    yield a, b
    a.dispose()
    b.dispose()


def _watch(engine, pids, holder, contender, witnessed, out):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if contender in pids and holder in pids:
            with Session(bind=engine, future=True) as s:
                blockers = s.execute(text("SELECT pg_blocking_pids(:pid)"),
                                     {"pid": pids[contender]}).scalar_one()
            if pids[holder] in (blockers or []):
                out["blocked_by_holder"] = True
                witnessed.set()
                return
        time.sleep(0.02)
    out["blocked_by_holder"] = False
    witnessed.set()


def test_two_concurrent_runs_raise_one_task(two_engines, engine, ids):
    """§5.1 part C under real contention, with the exact approved text (the
    `source` predicate included; T4 measured it without). Two REPEATABLE READ
    transactions, as the run is: the contender's insert waits on the holder's
    uncommitted row (`pg_blocking_pids` names the holder), then fails 23505 on
    the index once the holder commits. One task survives."""
    engine_a, engine_b = two_engines
    payload = json.dumps(_diagnostic(_subject()))
    insert = text("""INSERT INTO turab.tasks (task_type, priority, title, request_id, payload)
                     VALUES ('CONFIRM_PRICE', 'HIGH', 't', :r, CAST(:p AS jsonb))""")
    out: dict = {}
    pids: dict = {}
    holds, witnessed = threading.Event(), threading.Event()

    def holder():
        try:
            with Session(bind=engine_a, future=True) as s:
                s.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                pids["holder"] = s.execute(text("SELECT pg_backend_pid()")).scalar_one()
                s.execute(insert, {"r": ids.REQ_AMINA, "p": payload})
                holds.set()
                assert witnessed.wait(timeout=30)
                s.commit()
            out["holder"] = "ok"
        except Exception as exc:                      # pragma: no cover
            out["holder"] = f"raised {exc!r}"

    def contender():
        assert holds.wait(timeout=30)
        try:
            with Session(bind=engine_b, future=True) as s:
                s.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
                pids["contender"] = s.execute(text("SELECT pg_backend_pid()")).scalar_one()
                s.execute(insert, {"r": ids.REQ_AMINA, "p": payload})
                s.commit()
            out["contender"] = "ok"
        except DBAPIError as exc:
            out["contender"] = (exc.orig.sqlstate, exc.orig.diag.constraint_name)

    threads = [threading.Thread(target=holder), threading.Thread(target=contender),
               threading.Thread(target=_watch, args=(engine, pids, "holder", "contender",
                                                     witnessed, out))]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)
        assert not any(t.is_alive() for t in threads), "a worker never finished"
        assert out.get("blocked_by_holder") is True, out
        assert out.get("holder") == "ok", out
        assert out.get("contender") == ("23505", INDEX), out
        with Session(bind=engine, future=True) as s:
            assert s.execute(text("SELECT count(*) FROM turab.tasks "
                                  "WHERE payload = CAST(:p AS jsonb)"),
                             {"p": payload}).scalar_one() == 1
    finally:
        with Session(bind=engine, future=True) as s:
            s.execute(text("DELETE FROM turab.tasks WHERE payload = CAST(:p AS jsonb)"),
                      {"p": payload})
            s.commit()


# ======================================================================================
# Part D — a cited observation is kept as cited
# ======================================================================================

@pytest.mark.parametrize("assignment", [
    "raw_text = 'BODY-CHANGED'",
    "payload = '{}'::jsonb",
    "kind = 'TEXT'",
    "observed_at = now()",
    "source_id = NULL",
    "recorded_by_account_id = NULL",
])
def test_a_cited_observation_cannot_be_updated(session, ids, assignment):
    obs = _observation(session, ids)
    _event(session, ids, _task(session), obs)
    _refused(session, f"UPDATE turab.observations SET {assignment} "
                      "WHERE observation_id = :o", CITED, o=obs)


def test_a_cited_observation_cannot_be_deleted(session, ids):
    obs = _observation(session, ids)
    _event(session, ids, _task(session), obs)
    _refused(session, "DELETE FROM turab.observations WHERE observation_id = :o",
             CITED, o=obs)
    assert _one(session, "SELECT raw_text FROM turab.observations "
                         "WHERE observation_id = :o", o=obs) == "BODY-AT-CITATION"


def test_an_uncited_observation_stays_writable(session, ids):
    """Part D guards only observations a completion cites. An event without
    evidence cites nothing."""
    obs = _observation(session, ids)
    _event(session, ids, _task(session), None)
    _accepted(session, "UPDATE turab.observations SET raw_text = 'edited' "
                       "WHERE observation_id = :o", o=obs)
    _accepted(session, "DELETE FROM turab.observations WHERE observation_id = :o", o=obs)


def _party(session):
    return _one(session, "INSERT INTO turab.parties (kind) VALUES ('PERSON') "
                         "RETURNING party_id")


def _account(session):
    return _one(session, "INSERT INTO turab.user_accounts (status) VALUES ('INVITED') "
                         "RETURNING account_id")


def _source(session):
    return _one(session, "INSERT INTO turab.sources (kind) VALUES ('PHONE_CALL') "
                         "RETURNING source_id")


@pytest.mark.parametrize("referenced", ["source", "party", "recording account"])
def test_deleting_what_a_cited_observation_references_is_refused(session, ids, referenced):
    """The consequence plan §5.1 part D states as derived from the schema and
    not measured: `observations` references sources, parties and accounts ON
    DELETE SET NULL, so deleting one UPDATEs a cited observation, which part D
    refuses. Measured here. No application path deletes any of them."""
    target = {"source": _source, "party": _party, "recording account": _account}[referenced](
        session)
    kwargs = {"source": {"source": target}, "party": {"party": target},
              "recording account": {"recorded_by": target}}[referenced]
    obs = _observation(session, ids, **kwargs)
    _event(session, ids, _task(session), obs)
    table, column = {"source": ("sources", "source_id"), "party": ("parties", "party_id"),
                     "recording account": ("user_accounts", "account_id")}[referenced]
    _refused(session, f"DELETE FROM turab.{table} WHERE {column} = :x", CITED, x=target)


@pytest.mark.parametrize("referenced", ["source", "party", "recording account"])
def test_the_same_delete_is_accepted_when_the_observation_is_not_cited(session, ids,
                                                                     referenced):
    target = {"source": _source, "party": _party, "recording account": _account}[referenced](
        session)
    kwargs = {"source": {"source": target}, "party": {"party": target},
              "recording account": {"recorded_by": target}}[referenced]
    _observation(session, ids, **kwargs)
    table, column = {"source": ("sources", "source_id"), "party": ("parties", "party_id"),
                     "recording account": ("user_accounts", "account_id")}[referenced]
    _accepted(session, f"DELETE FROM turab.{table} WHERE {column} = :x", x=target)


def test_part_d_names_the_observation_in_its_message(session, ids):
    """The message carries the observation's id (plan §5.1 part D). Like every
    trigger message, it must never reach a response body: the completion
    command's tests (step 2) assert that."""
    obs = _observation(session, ids)
    _event(session, ids, _task(session), obs)
    error = _refused(session, "UPDATE turab.observations SET raw_text = 'x' "
                              "WHERE observation_id = :o", CITED, o=obs)
    assert str(obs) in error.orig.diag.message_primary


def test_the_guard_alone_does_not_see_an_uncommitted_citation(two_engines, engine, ids):
    """F6-18, R1a, pinned: part D alone does NOT keep the body cited at
    completion. A completion holding its event uncommitted does not stop a body
    UPDATE: the FK's FOR KEY SHARE does not conflict with the UPDATE's FOR NO
    KEY UPDATE (PostgreSQL 16 documentation, §13.3.2, Table 13.3), and the
    guard's EXISTS cannot see the uncommitted event. The UPDATE completes
    while the completion is still open.

    That is why the completion command locks the observation FOR SHARE before
    inserting the event (G6-8 (iv), step 2), and step 2's tests prove the
    lock. This test keeps the reason for that lock visible."""
    engine_a, engine_b = two_engines
    with Session(bind=engine, future=True) as s:
        obs = _observation(s, ids)
        task = _task(s)
        s.commit()
    out: dict = {}
    # The rows stay: the event is append-only and cites the observation. They
    # are fixture rows in the suite's own database, rebuilt every session.
    with Session(bind=engine_a, future=True) as c:
        c.execute(text(EVENT), {"t": task, "c": None, "o": obs, "a": ids.ACC_OPERATOR})

        def change():
            try:
                with Session(bind=engine_b, future=True) as u:
                    u.execute(text("SET lock_timeout = '5s'"))
                    u.execute(text("UPDATE turab.observations SET raw_text = 'BODY-CHANGED' "
                                   "WHERE observation_id = :o"), {"o": obs})
                    u.commit()
                out["change"] = "committed"
            except DBAPIError as exc:          # pragma: no cover
                out["change"] = exc.orig.sqlstate

        worker = threading.Thread(target=change)
        worker.start()
        worker.join(timeout=10)
        assert not worker.is_alive(), "the UPDATE waited: the race is not as measured"
        c.commit()
    assert out == {"change": "committed"}
    with Session(bind=engine, future=True) as s:
        assert s.execute(text("SELECT raw_text FROM turab.observations "
                              "WHERE observation_id = :o"), {"o": obs}).scalar_one() \
            == "BODY-CHANGED"
        assert s.execute(text("SELECT count(*) FROM turab.task_completion_events "
                              "WHERE evidence_observation_id = :o"),
                         {"o": obs}).scalar_one() == 1
