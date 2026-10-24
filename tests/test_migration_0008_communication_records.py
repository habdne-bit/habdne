"""0008 — communication records: identity, append-only rows, frozen threads
(Slice 7 step 1).

Ref: `db/migrations/versions/0008_communication_records.py`;
`docs/gate/SLICE_7_PLAN.md` revision 4, §5.1 parts E, A, B, C and D2
(approved in the review of 38281ab), G7-3, G7-4, G7-5, G7-2 (v), G7-12 (D2);
`docs/gate/evidence/SLICE7-PLAN-MEASUREMENTS.txt`, the measurements taken
BEFORE this revision.

The guards are in the DATABASE, so these tests write directly: they must hold
for every writer, not only for the Slice 7 commands, which do not exist yet.
Threads, messages and events here are fixtures.

Each refused write is tested next to the writes that must still succeed. A
guard that refused everything would otherwise pass.

Two kinds of database are used:
- the suite's database, at head, in a rolled-back session, for every guard;
- a scratch database, `turab_migration_0008_test`, for what only a migration
  run shows: the pre-check that refuses old non-conforming rows, and the
  downgrade.
The concurrency test commits its threads: the thread guard refuses their
DELETE, so they stay in the suite's database, under references of their own.

Proven at trigger level only, under the application role, which is a
superuser owning every table (EN-02). Not a claim about K06.
"""
from __future__ import annotations

import hashlib
import importlib.util
import itertools
import os
import pathlib
import re
import subprocess
import sys
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from tests.test_migration_0006_opportunity_history import world  # noqa: F401 (fixture)

ROOT = pathlib.Path(__file__).resolve().parents[1]
REVISION = "0008_communication_records"
MIGRATION = ROOT / "db" / "migrations" / "versions" / f"{REVISION}.py"
PLAN = ROOT / "docs" / "gate" / "SLICE_7_PLAN.md"

INDEX = "ux_whatsapp_thread_ref"
SCOPED = "ck_whatsapp_thread_ref_scoped"
THREAD_FROZEN = "a thread's links never change"
MESSAGE_FROZEN = "only delivery_status may change"
EVENT_FROZEN = "only the processing fields may change"
STATUSES = ("UNKNOWN", "QUEUED", "SENT", "DELIVERED", "READ", "FAILED")
ORDER = ("QUEUED", "SENT", "DELIVERED", "READ")


def _module():
    spec = importlib.util.spec_from_file_location("migration_0008", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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


def _ref() -> str:
    return f"{uuid.uuid4().hex[:12]}:{uuid.uuid4().hex[:12]}"


def _party(session):
    return _one(session, "INSERT INTO turab.parties (kind) VALUES ('PERSON') RETURNING party_id")


def _account(session):
    return _one(session, "INSERT INTO turab.user_accounts (status) VALUES ('ACTIVATED') "
                         "RETURNING account_id")


def _thread(session, *, channel="WHATSAPP", ref=None, party=None, request=None,
            prop=None, opportunity=None, created_by=None):
    return _one(session, """
        INSERT INTO turab.communication_threads (channel, external_thread_ref, party_id,
               request_id, property_id, opportunity_id, created_by_account_id)
        VALUES (CAST(:c AS turab.communication_channel), :r, :p, :q, :pr, :o, :a)
        RETURNING thread_id""", c=channel, r=ref, p=party, q=request, pr=prop,
        o=opportunity, a=created_by)


def _message(session, thread, *, provider="whatsapp", ref=None, direction="INBOUND",
             status="UNKNOWN", sent_by=None):
    return _one(session, """
        INSERT INTO turab.communication_messages (thread_id, provider, external_message_ref,
               direction, delivery_status, occurred_at, sent_by_account_id)
        VALUES (:t, :p, :r, CAST(:d AS turab.message_direction),
                CAST(:s AS turab.delivery_status), now(), :a)
        RETURNING message_id""", t=thread, p=provider,
        r=ref if ref is not None else (f"wamid.{uuid.uuid4().hex}" if provider else None),
        d=direction, s=status, a=sent_by)


def _event(session, status="RECEIVED"):
    return _one(session, """
        INSERT INTO turab.webhook_events (provider, provider_event_id, event_type, payload,
                                          processing_status)
        VALUES ('whatsapp', :e, 'message', '{"k": 1}',
                CAST(:s AS turab.webhook_processing_status))
        RETURNING webhook_event_id""", e=f"evt.{uuid.uuid4().hex}", s=status)


# ======================================================================================
# The text: the migration executes the approved block of plan §5.1
# ======================================================================================

def _approved_statements() -> list[str]:
    plan = PLAN.read_text(encoding="utf-8")
    section = plan[plan.index("### 5.1 The text of migration `0008`"):
                   plan.index("### 5.2 CORRECTION-007")]
    block = section[section.index("```sql\n") + 7:]
    block = block[:block.index("\n```")]
    statements, current, dollars = [], [], 0
    for line in block.splitlines():
        if line.strip().startswith("--") and dollars % 2 == 0:
            continue
        if not current and not line.strip():
            continue
        current.append(line)
        dollars += line.count("$$")
        if line.rstrip().endswith(";") and dollars % 2 == 0:
            statements.append("\n".join(current).rstrip()[:-1])
            current = []
    assert not current, current
    return statements


def _normal(sql: str) -> str:
    return re.sub(r"\s+", " ", sql).strip()


def test_the_migration_executes_the_approved_text():
    """The review of 38281ab approved a text. `UPGRADE` is that text,
    statement by statement, in its order (whitespace aside)."""
    approved = [_normal(s) for s in _approved_statements()]
    executed = [_normal(s) for s in _module().UPGRADE]
    assert len(approved) == 14
    assert executed == approved


# ======================================================================================
# Part E — a WHATSAPP thread's reference is scoped and unique
# ======================================================================================

@pytest.mark.parametrize("ref", ["abc", ":x", "x:", "a:b:c", "", ":"])
def test_e_an_unscoped_whatsapp_reference_is_refused(session, ref):
    _refused(session, """INSERT INTO turab.communication_threads (channel, external_thread_ref)
                         VALUES ('WHATSAPP', :r)""", SCOPED, r=ref)


def test_e_a_scoped_reference_is_accepted(session):
    _accepted(session, """INSERT INTO turab.communication_threads (channel, external_thread_ref)
                          VALUES ('WHATSAPP', :r)""", r=_ref())


def test_e_a_second_whatsapp_thread_with_one_reference_is_refused(session):
    ref = _ref()
    _thread(session, ref=ref)
    error = _refused(session, """INSERT INTO turab.communication_threads (channel,
                                        external_thread_ref) VALUES ('WHATSAPP', :r)""",
                     INDEX, r=ref)
    assert error.orig.sqlstate == "23505" and error.orig.diag.constraint_name == INDEX


def test_e_other_channels_and_null_references_are_not_constrained(session):
    """The index is partial: a PHONE thread may carry any reference, the same
    one as a WHATSAPP thread included, and NULL references never conflict."""
    ref = _ref()
    _thread(session, ref=ref)
    for channel, value in (("PHONE", ref), ("PHONE", ref), ("SMS", "unscoped"),
                           ("WHATSAPP", None), ("WHATSAPP", None)):
        _accepted(session, """INSERT INTO turab.communication_threads (channel,
                                     external_thread_ref)
                              VALUES (CAST(:c AS turab.communication_channel), :r)""",
                  c=channel, r=value)


@pytest.fixture
def two_engines(database_url):
    a = create_engine(database_url, future=True)
    b = create_engine(database_url, future=True)
    yield a, b
    a.dispose()
    b.dispose()


def _watch(engine, pids, witnessed, out):
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        if "holder" in pids and "contender" in pids:
            with Session(bind=engine, future=True) as s:
                blockers = s.execute(text("SELECT pg_blocking_pids(:pid)"),
                                     {"pid": pids["contender"]}).scalar_one()
            if pids["holder"] in (blockers or []):
                out["blocked_by_holder"] = True
                witnessed.set()
                return
        time.sleep(0.02)
    out["blocked_by_holder"] = False
    witnessed.set()


@pytest.mark.parametrize("ending", ["commit", "rollback"])
def test_e_two_concurrent_threads_with_one_reference_make_one(two_engines, engine, ending):
    """Two transactions insert a WHATSAPP thread with one reference. The
    contender's insert WAITS on the holder's uncommitted row
    (`pg_blocking_pids` names the holder). After the holder's COMMIT it is
    refused 23505 on the index; after its ROLLBACK it is accepted. One thread
    holds the reference either way."""
    engine_a, engine_b = two_engines
    ref = _ref()
    insert = text("""INSERT INTO turab.communication_threads (channel, external_thread_ref)
                     VALUES ('WHATSAPP', :r)""")
    out: dict = {}
    pids: dict = {}
    holds, witnessed = threading.Event(), threading.Event()

    def holder():
        try:
            with Session(bind=engine_a, future=True) as s:
                pids["holder"] = s.execute(text("SELECT pg_backend_pid()")).scalar_one()
                s.execute(insert, {"r": ref})
                holds.set()
                assert witnessed.wait(timeout=30)
                getattr(s, ending)()
            out["holder"] = "ok"
        except Exception as exc:                      # pragma: no cover
            out["holder"] = f"raised {exc!r}"

    def contender():
        assert holds.wait(timeout=30)
        try:
            with Session(bind=engine_b, future=True) as s:
                pids["contender"] = s.execute(text("SELECT pg_backend_pid()")).scalar_one()
                s.execute(insert, {"r": ref})
                s.commit()
            out["contender"] = "ok"
        except DBAPIError as exc:
            out["contender"] = (exc.orig.sqlstate, exc.orig.diag.constraint_name)

    threads = [threading.Thread(target=holder), threading.Thread(target=contender),
               threading.Thread(target=_watch, args=(engine, pids, witnessed, out))]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in threads), "a worker never finished"
    assert out.get("blocked_by_holder") is True, out
    assert out.get("holder") == "ok", out
    assert out.get("contender") == ("ok" if ending == "rollback" else ("23505", INDEX)), out
    with Session(bind=engine, future=True) as s:
        assert s.execute(text("SELECT count(*) FROM turab.communication_threads "
                              "WHERE external_thread_ref = :r"), {"r": ref}).scalar_one() == 1


# ======================================================================================
# Part A — a provider message identity is whole, and known
# ======================================================================================

def test_a_a_reference_needs_a_provider(session):
    thread = _thread(session, ref=_ref())
    _refused(session, """INSERT INTO turab.communication_messages (thread_id, provider,
                                external_message_ref, direction, occurred_at)
                         VALUES (:t, NULL, 'wamid.X', 'INBOUND', now())""",
             "ck_message_ref_needs_provider", t=thread)


@pytest.mark.parametrize("provider", ["sms-gateway", "WHATSAPP", "", "meta"])
def test_a_the_provider_is_whatsapp(session, provider):
    thread = _thread(session, ref=_ref())
    _refused(session, """INSERT INTO turab.communication_messages (thread_id, provider,
                                external_message_ref, direction, occurred_at)
                         VALUES (:t, :p, 'wamid.Y', 'INBOUND', now())""",
             "ck_message_provider_known", t=thread, p=provider)


def test_a_an_internal_message_has_no_reference(session):
    thread = _thread(session, ref=_ref())
    _refused(session, """INSERT INTO turab.communication_messages (thread_id, provider,
                                external_message_ref, direction, occurred_at)
                         VALUES (:t, 'whatsapp', 'wamid.Z', 'INTERNAL', now())""",
             "ck_internal_message_has_no_ref", t=thread)


@pytest.mark.parametrize("channel", ["PHONE", "SMS", "EMAIL", "WEB", "IN_PERSON", "OTHER"])
def test_a_a_provider_needs_a_whatsapp_thread(session, channel):
    thread = _thread(session, channel=channel)
    _refused(session, """INSERT INTO turab.communication_messages (thread_id, provider,
                                external_message_ref, direction, occurred_at)
                         VALUES (:t, 'whatsapp', :r, 'INBOUND', now())""",
             "provider whatsapp outside a WHATSAPP thread", t=thread,
             r=f"wamid.{uuid.uuid4().hex}")


def test_a_the_messages_the_rules_allow_are_accepted(session):
    whatsapp = _thread(session, ref=_ref())
    phone = _thread(session, channel="PHONE")
    _message(session, whatsapp)                                    # whatsapp, a reference
    _message(session, whatsapp, provider=None, direction="INTERNAL")  # a staff note
    _message(session, phone, provider=None)                        # no provider, no ref
    _message(session, phone, provider=None, direction="INTERNAL")
    assert _one(session, "SELECT count(*) FROM turab.communication_messages "
                         "WHERE thread_id IN (:a, :b)", a=whatsapp, b=phone) == 4


def test_a_the_global_identity_still_holds_across_threads(session):
    ref = f"wamid.{uuid.uuid4().hex}"
    _message(session, _thread(session, ref=_ref()), ref=ref)
    _refused(session, """INSERT INTO turab.communication_messages (thread_id, provider,
                                external_message_ref, direction, occurred_at)
                         VALUES (:t, 'whatsapp', :r, 'INBOUND', now())""",
             "communication_messages_provider_external_message_ref_key",
             t=_thread(session, ref=_ref()), r=ref)


# ======================================================================================
# Part B — messages are append-only; delivery_status moves forward
# ======================================================================================

def _decided(old: str, new: str) -> bool:
    """G7-5's table (plan revision 4), written independently of the trigger."""
    if old == "UNKNOWN":
        return new in ORDER
    if new == "FAILED":
        return old in ("QUEUED", "SENT")
    if old in ORDER and new in ORDER:
        return ORDER.index(new) > ORDER.index(old)
    return False


TRANSITIONS = [(a, b) for a, b in itertools.product(STATUSES, STATUSES) if a != b]


def test_b_the_table_has_twelve_accepted_moves_and_unknown_never_fails():
    accepted = [t for t in TRANSITIONS if _decided(*t)]
    assert len(TRANSITIONS) == 30 and len(accepted) == 12
    assert ("UNKNOWN", "FAILED") not in accepted


@pytest.mark.parametrize("old, new", TRANSITIONS)
def test_b_delivery_status_transitions_are_exactly_the_decided_ones(session, old, new):
    message = _message(session, _thread(session, ref=_ref()), status=old)
    sql = ("UPDATE turab.communication_messages SET delivery_status = "
           "CAST(:s AS turab.delivery_status) WHERE message_id = :m")
    if _decided(old, new):
        _accepted(session, sql, s=new, m=message)
        assert _one(session, "SELECT delivery_status::text FROM turab.communication_messages "
                             "WHERE message_id = :m", m=message) == new
    else:
        _refused(session, sql, f"delivery_status {old} -> {new} refused", s=new, m=message)


def test_b_an_update_that_changes_nothing_is_accepted(session):
    message = _message(session, _thread(session, ref=_ref()), status="SENT")
    _accepted(session, "UPDATE turab.communication_messages SET delivery_status = 'SENT' "
                       "WHERE message_id = :m", m=message)


@pytest.mark.parametrize("assignment", [
    "message_id = gen_random_uuid()",
    "thread_id = :other",
    "provider = NULL, external_message_ref = NULL",
    "external_message_ref = 'wamid.rewritten'",
    "direction = 'OUTBOUND'",
    "message_type = 'IMAGE'",
    "body_text = 'rewritten'",
    "media_ref = 'media://rewritten'",
    "occurred_at = occurred_at - interval '1 day'",
    "sent_by_account_id = :account",
    "metadata = '{\"x\": 1}'::jsonb",
    "created_at = created_at - interval '1 day'",
])
def test_b_no_other_column_of_a_message_changes(session, assignment):
    message = _message(session, _thread(session, ref=_ref()))
    other = _thread(session, ref=_ref())
    account = _account(session)
    params = {"m": message}
    if ":other" in assignment:
        params["other"] = other
    if ":account" in assignment:
        params["account"] = account
    _refused(session, f"UPDATE turab.communication_messages SET {assignment} "
                      "WHERE message_id = :m", MESSAGE_FROZEN, **params)


def test_b_a_message_without_a_provider_never_gains_one(session):
    """`provider` alone changing. Part A's CHECKs accept a message with
    `provider` 'whatsapp' and no reference, and the channel trigger runs on
    INSERT only, so on a WHATSAPP thread only the guard refuses this UPDATE.
    The case above that clears `provider` also clears `external_message_ref`,
    and so could not show it (mutation B6 survived the first full run)."""
    message = _message(session, _thread(session, ref=_ref()), provider=None)
    _refused(session, "UPDATE turab.communication_messages SET provider = 'whatsapp' "
                      "WHERE message_id = :m", MESSAGE_FROZEN, m=message)


def test_b_a_message_cannot_be_deleted(session):
    message = _message(session, _thread(session, ref=_ref()))
    _refused(session, "DELETE FROM turab.communication_messages WHERE message_id = :m",
             "DELETE refused (append-only)", m=message)


# ======================================================================================
# Part C — a webhook event is immutable but for its processing
# ======================================================================================

@pytest.mark.parametrize("assignment", [
    "webhook_event_id = gen_random_uuid()",
    "provider = 'other'",
    "provider_event_id = 'evt.rewritten'",
    "event_type = 'status'",
    "payload = '{}'::jsonb",
    "received_at = received_at - interval '1 day'",
])
def test_c_the_immutable_fields_of_an_event_never_change(session, assignment):
    event = _event(session)
    _refused(session, f"UPDATE turab.webhook_events SET {assignment}, "
                      "processing_status = 'PROCESSED' WHERE webhook_event_id = :e",
             EVENT_FROZEN, e=event)


@pytest.mark.parametrize("old, new, accepted", [
    ("RECEIVED", "PROCESSED", True), ("RECEIVED", "IGNORED", True),
    ("RECEIVED", "FAILED", True), ("RECEIVED", "RECEIVED", False),
    ("FAILED", "PROCESSED", True), ("FAILED", "IGNORED", True),
    ("FAILED", "FAILED", True), ("FAILED", "RECEIVED", False),
    ("PROCESSED", "PROCESSED", False), ("PROCESSED", "FAILED", False),
    ("PROCESSED", "RECEIVED", False), ("PROCESSED", "IGNORED", False),
    ("IGNORED", "IGNORED", False), ("IGNORED", "PROCESSED", False),
    ("IGNORED", "FAILED", False), ("IGNORED", "RECEIVED", False),
])
def test_c_processing_moves_only_from_received_or_failed(session, old, new, accepted):
    event = _event(session, status=old)
    sql = ("UPDATE turab.webhook_events SET processing_status = "
           "CAST(:s AS turab.webhook_processing_status), processed_at = now(), "
           "error_text = 'CODE' WHERE webhook_event_id = :e")
    if accepted:
        _accepted(session, sql, s=new, e=event)
    else:
        _refused(session, sql, "event is final", f"{old} -> {new} refused", s=new, e=event)


def test_c_received_then_failed_then_processed_is_one_path(session):
    event = _event(session)
    for status in ("FAILED", "FAILED", "PROCESSED"):
        _accepted(session, "UPDATE turab.webhook_events SET processing_status = "
                           "CAST(:s AS turab.webhook_processing_status), processed_at = now() "
                           "WHERE webhook_event_id = :e", s=status, e=event)


def test_c_an_event_cannot_be_deleted(session):
    for status in ("RECEIVED", "FAILED", "PROCESSED", "IGNORED"):
        _refused(session, "DELETE FROM turab.webhook_events WHERE webhook_event_id = :e",
                 "webhook_events: DELETE refused", e=_event(session, status))


# ======================================================================================
# Part D (D2) — six keys RESTRICT; a thread never changes after INSERT
# ======================================================================================

SIX_KEYS = {
    ("communication_threads", "communication_threads_party_id_fkey"),
    ("communication_threads", "communication_threads_request_id_fkey"),
    ("communication_threads", "communication_threads_property_id_fkey"),
    ("communication_threads", "communication_threads_opportunity_id_fkey"),
    ("communication_threads", "communication_threads_created_by_account_id_fkey"),
    ("communication_messages", "communication_messages_sent_by_account_id_fkey"),
}


def test_d_the_six_keys_are_restrict(session):
    rows = session.execute(text("""
        SELECT c.conrelid::regclass::text, c.conname, c.confdeltype
          FROM pg_constraint c
         WHERE c.contype = 'f'
           AND c.conrelid IN ('turab.communication_threads'::regclass,
                              'turab.communication_messages'::regclass)""")).all()
    by_name = {(t.removeprefix("turab."), n): d for t, n, d in rows}
    assert {k for k, d in by_name.items() if d == "r"} == SIX_KEYS | {
        ("communication_messages", "communication_messages_thread_id_fkey")}
    assert {k for k, d in by_name.items() if d == "n"} == set(), "no SET NULL key remains"


def _thread_naming_everything(session, world_):
    """A thread naming a party, a request, a property, an opportunity and its
    creator, and a message naming its sender. The request and the property are
    the world's spare ones, which nothing else names: another key referencing
    the row would refuse its deletion first, and hide the key under test."""
    party, account = _party(session), _account(session)
    req, prop = world_["other_req"], world_["other_prop"]
    thread = _thread(session, ref=_ref(), party=party, request=req, prop=prop,
                     opportunity=world_["opp"], created_by=account)
    sender = _account(session)
    _message(session, thread, provider=None, direction="INTERNAL", sent_by=sender)
    return {"party": party, "account": account, "sender": sender, "request": req,
            "property": prop, "opportunity": world_["opp"], "thread": thread}


@pytest.mark.parametrize("parent, table, column, key, guard", [
    ("party", "parties", "party_id", "communication_threads_party_id_fkey", None),
    ("account", "user_accounts", "account_id",
     "communication_threads_created_by_account_id_fkey", None),
    ("sender", "user_accounts", "account_id",
     "communication_messages_sent_by_account_id_fkey", None),
    ("request", "requests", "request_id", "communication_threads_request_id_fkey",
     "prevent_delete_requests"),
    ("property", "properties", "property_id", "communication_threads_property_id_fkey",
     "prevent_delete_properties"),
    ("opportunity", "opportunities", "opportunity_id",
     "communication_threads_opportunity_id_fkey", "prevent_delete_opportunities"),
])
def test_d_a_named_parent_cannot_be_deleted(session, world, parent, table, column, key,
                                            guard):
    """Each of the six RESTRICT keys refuses the deletion of the row a thread or
    message names (23503, by the key's name). For requests, properties and
    opportunities, the frozen delete guard would refuse first, so it is
    disabled inside this rolled-back transaction, to test the key itself."""
    names = _thread_naming_everything(session, world)
    if guard:
        session.execute(text(f"ALTER TABLE turab.{table} DISABLE TRIGGER {guard}"))
    error = _refused(session, f"DELETE FROM turab.{table} WHERE {column} = :v", key,
                     v=names[parent])
    assert error.orig.sqlstate == "23503" and error.orig.diag.constraint_name == key


def test_d_an_unnamed_party_and_account_can_still_be_deleted(session):
    _accepted(session, "DELETE FROM turab.parties WHERE party_id = :p", p=_party(session))
    _accepted(session, "DELETE FROM turab.user_accounts WHERE account_id = :a",
              a=_account(session))


@pytest.mark.parametrize("assignment", [
    "thread_id = gen_random_uuid()",
    "channel = 'SMS'",
    "party_id = :other_party",
    "party_id = NULL",
    "request_id = NULL",
    "property_id = NULL",
    "opportunity_id = NULL",
    "created_by_account_id = NULL",
    "external_thread_ref = 'x:y'",
    "external_thread_ref = NULL",
    "opened_at = opened_at - interval '1 day'",
    "archived_at = now()",
])
def test_d_a_thread_never_changes_after_insert(session, world, assignment):
    names = _thread_naming_everything(session, world)
    _refused(session, f"UPDATE turab.communication_threads SET {assignment} "
                      "WHERE thread_id = :t", THREAD_FROZEN, t=names["thread"],
             other_party=_party(session))


def test_d_a_nested_update_is_refused_too(session):
    """D2's guarantee holds at any trigger depth, unlike D3's (review of
    58a0067): an UPDATE issued from inside another table's trigger
    (`pg_trigger_depth() = 2`) is refused like a direct one."""
    party = _party(session)
    thread = _thread(session, channel="PHONE", party=party)
    session.execute(text("""
        CREATE FUNCTION pg_temp.nested_thread_update() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
          UPDATE turab.communication_threads SET party_id = NULL
           WHERE party_id = NEW.party_id;
          RETURN NEW;
        END $$"""))
    session.execute(text("""CREATE TRIGGER nested_thread_update AFTER UPDATE ON turab.parties
                            FOR EACH ROW EXECUTE FUNCTION pg_temp.nested_thread_update()"""))
    _refused(session, "UPDATE turab.parties SET display_name = 'renamed' WHERE party_id = :p",
             THREAD_FROZEN, p=party)
    assert _one(session, "SELECT party_id FROM turab.communication_threads "
                         "WHERE thread_id = :t", t=thread) == party


def test_d_last_message_at_moves_forward_only(session):
    thread = _thread(session, ref=_ref())
    sql = "UPDATE turab.communication_threads SET last_message_at = {} WHERE thread_id = :t"
    _accepted(session, sql.format("now() - interval '2 hours'"), t=thread)
    _accepted(session, sql.format("now() - interval '1 hour'"), t=thread)
    _refused(session, sql.format("now() - interval '3 hours'"),
             "last_message_at moves forward only", t=thread)
    _refused(session, sql.format("NULL"), "last_message_at moves forward only", t=thread)


def test_d_a_thread_cannot_be_deleted(session):
    _refused(session, "DELETE FROM turab.communication_threads WHERE thread_id = :t",
             "communication_threads: DELETE refused", t=_thread(session, ref=_ref()))


# ======================================================================================
# A migration run: the pre-check on old rows, and the downgrade
# ======================================================================================

PGHOST = os.environ.get("PGHOST", "127.0.0.1")
PGUSER = os.environ.get("PGUSER", "turab")
PGPASSWORD = os.environ.get("PGPASSWORD", "turab")
SCRATCH = os.environ.get("TURAB_MIGRATION_0008_DB", "turab_migration_0008_test")
SCRATCH_URL = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{SCRATCH}"
PREVIOUS = "0007_task_work_and_evidence"


def _alembic(*args):
    exe = ROOT / ".venv" / "bin" / "alembic"
    return subprocess.run([str(exe) if exe.exists() else "alembic", *args], cwd=ROOT,
                          capture_output=True, text=True,
                          env={**os.environ, "PGHOST": PGHOST, "PGUSER": PGUSER,
                               "PGPASSWORD": PGPASSWORD, "TURAB_DATABASE_URL": SCRATCH_URL})


@pytest.fixture(scope="module")
def scratch():
    """A scratch database rebuilt the way a real one is (`db/dev/reset_db.sh`:
    the frozen schema, the seed, stamped, then upgraded to head), dropped
    afterwards. Every test below leaves it at head."""
    env = {**os.environ, "PGDATABASE": SCRATCH, "PGHOST": PGHOST, "PGUSER": PGUSER,
           "PGPASSWORD": PGPASSWORD, "PATH": f"{ROOT / '.venv' / 'bin'}:{os.environ['PATH']}"}
    built = subprocess.run([str(ROOT / "db" / "dev" / "reset_db.sh")], env=env,
                           capture_output=True, text=True)
    assert built.returncode == 0, built.stdout + built.stderr
    eng = create_engine(SCRATCH_URL, future=True)
    yield eng
    eng.dispose()
    subprocess.run(["dropdb", "-h", PGHOST, "-U", PGUSER, "--if-exists", SCRATCH],
                   env={**os.environ, "PGPASSWORD": PGPASSWORD}, check=False)


def _error(output: str) -> str:
    """The database's error in an alembic run's output, or its last line."""
    found = re.findall(r"psycopg\.errors\.\w+\) .*", output)
    return found[0] if found else (output.strip().splitlines() or [""])[-1]


def _version(eng):
    with eng.connect() as c:
        return c.execute(text("SELECT version_num FROM public.alembic_version")).scalar_one()


@pytest.mark.parametrize("whatsapp_refs, unscoped, shared", [
    (("unscoped-ref", "one:ref"), 1, 0),
    (("shared:ref", "shared:ref", "one:ref"), 0, 1),
    (("unscoped-ref", "shared:ref", "shared:ref"), 1, 1),
])
def test_e_the_precheck_refuses_unscoped_and_shared_references(scratch, whatsapp_refs,
                                                               unscoped, shared):
    """Old rows that break part E's rules make the migration refuse, naming the
    counts, and leave the database at the previous revision. A PHONE thread
    carrying the shared reference, and one with an unscoped reference, are in
    every case and are counted by neither. Once the WHATSAPP rows are
    resolved, the migration applies.

    The rows are removed and the database brought back to head even when an
    assertion fails, so that each case, and the downgrade test, starts from
    head: a failure here is this case's, not a consequence of the one before."""
    assert _alembic("downgrade", PREVIOUS).returncode == 0
    assert _version(scratch) == PREVIOUS
    rows = [("WHATSAPP", r) for r in whatsapp_refs] + [("PHONE", "shared:ref"),
                                                        ("PHONE", "unscoped-ref")]
    try:
        with scratch.begin() as c:
            for channel, ref in rows:
                c.execute(text("INSERT INTO turab.communication_threads (channel, "
                               "external_thread_ref) VALUES "
                               "(CAST(:c AS turab.communication_channel), :r)"),
                          {"c": channel, "r": ref})
        refused = _alembic("upgrade", "head")
        output = refused.stdout + refused.stderr
        assert refused.returncode != 0, "the upgrade was accepted"
        assert (f"0008: {unscoped} WHATSAPP thread reference(s) not scoped, "
                f"{shared} reference(s) shared" in output), _error(output)
        assert _version(scratch) == PREVIOUS, "a refused upgrade must leave the version"
    finally:
        if _version(scratch) == PREVIOUS:
            with scratch.begin() as c:
                c.execute(text("DELETE FROM turab.communication_threads "
                               "WHERE external_thread_ref IN ('unscoped-ref', "
                               "'shared:ref', 'one:ref')"))
        applied = _alembic("upgrade", "head")
    assert applied.returncode == 0, _error(applied.stdout + applied.stderr)
    assert _version(scratch) == REVISION


def _digests(eng) -> dict[tuple[str, str], str | None]:
    sys.path.insert(0, str(ROOT / "db" / "dev"))
    sys.path.insert(0, str(ROOT / "db" / "gate"))
    from baseline_fingerprint import describe
    from migration_deltas import for_revision, split_row

    with eng.connect() as c:
        described = describe(c)
    found = {}
    for d in for_revision(REVISION):
        rows = dict(split_row(d.section, row) for row in described.get(d.section, []))
        definition = rows.get(d.object_name)
        found[(d.section, d.object_name)] = (
            None if definition is None else hashlib.sha256(definition.encode()).hexdigest())
    return found


def test_the_downgrade_restores_the_frozen_definitions_and_keeps_the_rows(scratch):
    """Down to 0007, every object of 0008 is back to its digest before 0008
    (absent if it is new, the frozen SET NULL definition for the six keys), and
    the rows written at head are kept. Up again, every object is as it was at
    head. That head matches the ledger's `digest_after` is proven by
    `test_head_is_the_baseline_plus_exactly_the_declared_deltas`, not here."""
    sys.path.insert(0, str(ROOT / "db" / "gate"))
    from migration_deltas import for_revision

    deltas = {(d.section, d.object_name): d for d in for_revision(REVISION)}
    assert _version(scratch) == REVISION
    at_head = _digests(scratch)
    assert None not in at_head.values(), at_head
    with scratch.begin() as c:
        thread = c.execute(text("""INSERT INTO turab.communication_threads (channel,
                                          external_thread_ref)
                                   VALUES ('WHATSAPP', :r) RETURNING thread_id"""),
                           {"r": _ref()}).scalar_one()
        c.execute(text("""INSERT INTO turab.communication_messages (thread_id, provider,
                                 external_message_ref, direction, occurred_at)
                          VALUES (:t, 'whatsapp', 'wamid.down', 'INBOUND', now())"""),
                  {"t": thread})
    down = _alembic("downgrade", PREVIOUS)
    assert down.returncode == 0, _error(down.stdout + down.stderr)
    assert _version(scratch) == PREVIOUS
    assert _digests(scratch) == {k: d.digest_before for k, d in deltas.items()}
    with scratch.connect() as c:
        assert c.execute(text("SELECT count(*) FROM turab.communication_messages "
                              "WHERE thread_id = :t"), {"t": thread}).scalar_one() == 1
        assert c.execute(text("""SELECT confdeltype FROM pg_constraint
                                  WHERE conname = 'communication_threads_party_id_fkey'""")
                         ).scalar_one() == "n"
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, _error(up.stdout + up.stderr)
    assert _version(scratch) == REVISION
    assert _digests(scratch) == at_head
