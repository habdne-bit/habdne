"""Slice 7 step 4: one interaction per message, the backfill, the timeline's
`message`, and the phone decision's confirmation link.

Ref: `docs/gate/SLICE_7_PLAN.md` G7-8 (a), G7-10 (a), G7-11, G7-17 (i), and
G7-18 (i)-(ix), decided in the review of e18271a; §6.1 mandatory test 4 (and
mandatory test 1's "one interaction"); `services/message_interactions.py`,
`services/communication.py`, `services/timeline.py`,
`db/ops/backfill_message_interactions.py`.

**What the review of e18271a asked to see proven:**
- the item's exact keys, and the withholding of unarchived content, for each
  of the three roles (`test_vi_*`);
- the link's refusals before any write or idempotency key is consumed
  (`test_vii_*`, through `_refused`, whose footprint counts interactions
  too);
- the backfill run concurrently and re-run (`test_v_*`).

**What is not claimed.** "One interaction per message" holds within the
service's paths; it is not a constraint of the database (no `0009`). A
confirmation link is valid at its writing only: the observation it names is
not protected afterwards (0007's guard does not cover a message's metadata),
and the link has no legal value.

**Isolation.** HTTP tests commit to the shared test database; each test builds
its own parties and threads. The backfill reads every message of the
database, so its assertions name this test's messages.
"""
from __future__ import annotations

import json
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.test_slice4_step7 import _all, _exec, _one
from tests.test_slice7_step2 import (
    _archive_consent,
    _headers,
    _message,
    _new_thread,
    _ok,
    _party,
    _ref,
    _sale_world,
    _wait_until_blocked,
)
from turab.auth.audit import AccessAuditor, RecordingAuditSink

AT = "2026-10-25T10:00:00Z"
LATER = "2026-10-25T11:00:00Z"
EARLIER = "2026-10-25T09:00:00Z"
SECRET = "SECRET-BODY-c42e"
MEDIA = "media://SECRET-MEDIA-c42e"
CHANNELS = ("WHATSAPP", "PHONE", "SMS", "EMAIL", "WEB", "IN_PERSON", "OTHER")
TYPE = {"WHATSAPP": "WHATSAPP", "PHONE": "CALL", "SMS": "SMS", "EMAIL": "EMAIL",
        "WEB": "OTHER", "IN_PERSON": "IN_PERSON", "OTHER": "OTHER"}
#: Slice 1's exact item keys, unchanged for every item that is not a message's.
BASE_KEYS = {"interaction_id", "party_id", "interaction_type", "channel", "request_id",
             "property_id", "opportunity_id", "thread_id", "summary", "outcome_code",
             "occurred_at", "operator_account_id", "created_at"}
MESSAGE_KEYS = {"message_id", "direction", "message_type", "delivery_status",
                "occurred_at", "content_archived"}
ROLES = ("ACC_ADMIN", "ACC_OPERATOR", "ACC_REVIEWER")


def _svc():
    """Imported where used, so that this file is collected on a tree without
    step 4's code and each test there fails on its own (the before record)."""
    from turab.services import message_interactions

    return message_interactions


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# --- helpers --------------------------------------------------------------------------

def _interactions(engine, message_id):
    return _all(engine, """
        SELECT interaction_id, interaction_type::text AS interaction_type,
               channel::text AS channel, party_id, request_id, property_id,
               opportunity_id, thread_id, summary, outcome_code, occurred_at,
               operator_account_id, metadata, created_at
          FROM turab.interactions WHERE metadata->>'message_id' = :m""",
                m=str(message_id))


def _one_interaction(engine, message_id):
    rows = _interactions(engine, message_id)
    assert len(rows) == 1, rows
    return rows[0]


def _counts(engine):
    return {
        "messages": _one(engine, "SELECT count(*) FROM turab.communication_messages"),
        "interactions": _one(engine, "SELECT count(*) FROM turab.interactions"),
        "audit": _one(engine, "SELECT count(*) FROM turab.audit_log"),
    }


def _refused(engine, call, status, code):
    """The refusal, and nothing written: no message, no interaction, no audit
    row, no key consumed (the review of e18271a)."""
    key = str(uuid.uuid4())
    before = _counts(engine)
    response = call(key)
    assert (response.status_code, response.json().get("code")) == (status, code), \
        response.text
    assert _counts(engine) == before, "a refusal writes nothing"
    assert _one(engine, "SELECT count(*) FROM turab.idempotency_records "
                        "WHERE idempotency_key = :k", k=key) == 0, "no key consumed"
    return response.json()


def _post_message(client, thread, body, account, key=None):
    return _message(client, thread, {"occurred_at": AT, **body}, account, key)


def _sent(client, thread, body, account):
    return uuid.UUID(_ok(_post_message(client, thread, body, account))["message_id"])


def _audit(engine, entity_id):
    return _all(engine, """
        SELECT action, actor_account_id, context, new_row::text AS new_row
          FROM turab.audit_log WHERE entity_table = 'interactions' AND entity_id = :e""",
                e=entity_id)


def _timeline(client, party, account):
    r = client.get(f"/parties/{party}/timeline", headers={"Authorization": f"Bearer {account}"},
                   params={"page_size": 100})
    assert r.status_code == 200, r.text
    return r.json()["items"]


def _item(client, party, account, message_id):
    [item] = [i for i in _timeline(client, party, account)
              if i.get("message", {}).get("message_id") == str(message_id)]
    return item


def _observation(engine, party, *, kind="MESSAGE", observed_at=LATER):
    return _one(engine, """
        INSERT INTO turab.observations (kind, party_id, observed_at, raw_text)
        VALUES (CAST(:k AS turab.observation_kind), :p, :at, 'a written confirmation')
        RETURNING observation_id""", k=kind, p=party, at=observed_at)


def _decision(client, ids, engine, *, party=None, at=AT):
    party = party or _party(engine)
    thread = _new_thread(client, ids, engine, channel="PHONE", party=party)
    decision = _sent(client, thread, {"direction": "INTERNAL", "message_type": "PHONE_DECISION",
                                      "occurred_at": at}, ids.ACC_OPERATOR)
    return party, thread, decision


def _link_body(decision, observation, **extra):
    return {"direction": "INTERNAL", "message_type": "CONFIRMATION_LINK",
            "occurred_at": LATER,
            "metadata": {"decision_message_id": str(decision),
                         "observation_id": str(observation)}, **extra}


# --- (i)-(iii): the interaction a message writes -------------------------------------------

@pytest.mark.parametrize("channel", CHANNELS)
def test_i_an_outbound_message_writes_its_channels_interaction(client, engine, ids, channel):
    party = _party(engine)
    thread = _new_thread(client, ids, engine, channel=channel, party=party,
                         ref=_ref() if channel == "WHATSAPP" else None)
    message = _sent(client, thread, {"direction": "OUTBOUND"}, ids.ACC_OPERATOR)
    row = _one_interaction(engine, message)
    assert (row["interaction_type"], row["channel"], row["summary"]) == (
        TYPE[channel], channel, "Outbound message")


@pytest.mark.parametrize("channel", CHANNELS)
def test_i_an_internal_message_is_a_note_in_every_channel(client, engine, ids, channel):
    thread = _new_thread(client, ids, engine, channel=channel,
                         ref=_ref() if channel == "WHATSAPP" else None)
    message = _sent(client, thread, {"direction": "INTERNAL"}, ids.ACC_OPERATOR)
    row = _one_interaction(engine, message)
    assert (row["interaction_type"], row["channel"], row["summary"]) == (
        "NOTE", channel, "Internal note")


def test_iii_the_interaction_carries_the_threads_links_and_the_messages_time(client, engine,
                                                                            ids):
    """With every link the thread can hold: the opportunity's buyer, request,
    property. `metadata` is exactly the message's id; no outcome; the operator
    is the sender; audited with the command's actor, the summary withheld."""
    world = _sale_world(client, engine, ids)
    thread = uuid.UUID(_ok(client.post("/communication/threads", json={
        "channel": "PHONE", "party_id": str(world["buyer"]),
        "opportunity_id": str(world["opportunity"]), "request_id": str(world["request"]),
        "property_id": str(world["property"])},
        headers=_headers(ids.ACC_OPERATOR)))["thread_id"])
    message = _sent(client, thread, {"direction": "OUTBOUND", "occurred_at": EARLIER},
                    ids.ACC_OPERATOR)
    row = _one_interaction(engine, message)
    assert (row["party_id"], row["request_id"], row["property_id"], row["opportunity_id"],
            row["thread_id"]) == (world["buyer"], world["request"], world["property"],
                                  world["opportunity"], thread)
    assert row["occurred_at"].isoformat() == "2026-10-25T09:00:00+00:00"
    assert (row["metadata"], row["outcome_code"], row["operator_account_id"]) == (
        {"message_id": str(message)}, None, ids.ACC_OPERATOR)
    [audit] = _audit(engine, row["interaction_id"])
    assert (audit["action"], audit["actor_account_id"]) == ("INSERT", ids.ACC_OPERATOR)
    assert audit["context"]["operation"] == "postCommunicationThreadsThreadIdMessages"
    assert "summary" not in json.loads(audit["new_row"])


def test_iii_a_webhook_message_writes_an_inbound_interaction_with_no_operator(
        client, engine, ids, monkeypatch):
    from tests.test_slice7_step3 import KEY, _msg, _post, _whatsapp

    monkeypatch.setenv("TURAB_RELAY_SIGNING_SECRET", KEY)
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    envelope = _msg(thread_ref)
    assert _post(client, envelope).status_code == 200
    [message] = _all(engine, "SELECT message_id FROM turab.communication_messages WHERE "
                             "external_message_ref = :r",
                     r=envelope["payload"]["external_message_ref"])
    row = _one_interaction(engine, message["message_id"])
    assert (row["interaction_type"], row["channel"], row["summary"], row["party_id"],
            row["thread_id"], row["operator_account_id"]) == (
        "WHATSAPP", "WHATSAPP", "Inbound message", party, thread, None)
    [audit] = _audit(engine, row["interaction_id"])
    assert audit["actor_account_id"] is None
    assert audit["context"]["operation"] == "postWebhooksWhatsapp"


def test_iv_a_webhook_replay_and_an_ignored_event_write_no_interaction(client, engine, ids,
                                                                      monkeypatch):
    """Mandatory test 1's "one interaction": the same envelope again writes no
    second one; an IGNORED event writes none."""
    from tests.test_slice7_step3 import KEY, _msg, _post, _status, _whatsapp

    monkeypatch.setenv("TURAB_RELAY_SIGNING_SECRET", KEY)
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    assert _post(client, envelope).status_code == 200
    [message] = _all(engine, "SELECT message_id FROM turab.communication_messages WHERE "
                             "external_message_ref = :r",
                     r=envelope["payload"]["external_message_ref"])
    assert len(_interactions(engine, message["message_id"])) == 1, "the first wrote one"
    before = _counts(engine)["interactions"]
    for again in (envelope, _msg(_ref()), _status(f"wamid.{uuid.uuid4().hex}", "SENT")):
        assert _post(client, again).status_code == 200
    assert _counts(engine)["interactions"] == before


def test_iv_a_failed_webhook_processing_leaves_no_interaction(client, engine, ids,
                                                             monkeypatch):
    """The interaction is inside T2's savepoint: a failure after it rolls it
    back with the message."""
    from sqlalchemy import text

    from tests.test_slice7_step3 import KEY, _msg, _post, _whatsapp
    from turab.services import webhooks

    monkeypatch.setenv("TURAB_RELAY_SIGNING_SECRET", KEY)
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    real = webhooks.process

    def failing(session, event_id, env, **kw):
        outcome = real(session, event_id, env, **kw)
        session.execute(text("SELECT 1 / 0"))
        return outcome

    monkeypatch.setattr(webhooks, "process", failing)
    before = _counts(engine)["interactions"]
    assert _post(client, envelope).status_code == 500
    assert _counts(engine)["interactions"] == before
    monkeypatch.setattr(webhooks, "process", real)
    assert _post(client, envelope).status_code == 200
    assert _counts(engine)["interactions"] == before + 1, "the redelivery writes one"


def test_iv_a_refused_staff_message_writes_no_interaction(client, engine, ids):
    thread = _new_thread(client, ids, engine)
    _refused(engine, lambda k: _post_message(
        client, thread, {"direction": "OUTBOUND", "body_text": SECRET}, ids.ACC_OPERATOR, k),
        422, "CONTENT_NOT_ARCHIVABLE")
    accepted = _sent(client, thread, {"direction": "OUTBOUND"}, ids.ACC_OPERATOR)
    assert len(_interactions(engine, accepted)) == 1, "the same message, accepted, writes one"


def test_iv_a_replayed_staff_command_writes_no_second_interaction(client, engine, ids):
    thread = _new_thread(client, ids, engine)
    key = str(uuid.uuid4())
    first = _ok(_post_message(client, thread, {"direction": "OUTBOUND"}, ids.ACC_OPERATOR, key))
    before = _counts(engine)
    again = _post_message(client, thread, {"direction": "OUTBOUND"}, ids.ACC_OPERATOR, key)
    assert again.status_code == 201 and again.json() == first
    assert _counts(engine) == before
    assert len(_interactions(engine, first["message_id"])) == 1


# --- (v): the backfill ------------------------------------------------------------------------

def _bare_message(engine, thread, *, direction="OUTBOUND", at=AT, body=None):
    """A message as a database before step 4 holds it: no interaction."""
    return _one(engine, """
        INSERT INTO turab.communication_messages
               (thread_id, direction, occurred_at, body_text, metadata)
        VALUES (:t, CAST(:d AS turab.message_direction), :at, :b,
                CAST(:meta AS jsonb))
        RETURNING message_id""", t=thread, d=direction, at=at, b=body,
                meta=json.dumps({"content_archived": body is not None}))


def _run_backfill(engine, trace="backfill-test"):
    from sqlalchemy.orm import Session

    with Session(bind=engine) as session:
        return _svc().backfill(session, trace)


def test_v_the_backfill_writes_one_interaction_per_earlier_message_and_a_rerun_none(
        client, engine, ids):
    party = _party(engine)
    phone = _new_thread(client, ids, engine, channel="PHONE", party=party)
    outbound = _bare_message(engine, phone, at=EARLIER, body=SECRET)
    note = _bare_message(engine, phone, direction="INTERNAL")
    assert _interactions(engine, outbound) == _interactions(engine, note) == []
    assert _run_backfill(engine) >= 2
    first, second = _one_interaction(engine, outbound), _one_interaction(engine, note)
    assert (first["interaction_type"], first["summary"], first["party_id"],
            first["thread_id"], first["operator_account_id"]) == (
        "CALL", "Outbound message", party, phone, None)
    assert second["interaction_type"] == "NOTE"
    assert first["occurred_at"].isoformat() == "2026-10-25T09:00:00+00:00"
    assert first["created_at"] > first["occurred_at"], \
        "written at the backfill's time: the atomicity does not hold retroactively"
    assert SECRET not in json.dumps(first, default=str)
    [audit] = _audit(engine, first["interaction_id"])
    assert (audit["actor_account_id"], audit["context"]["operation"]) == (
        None, "backfillMessageInteractions")
    before = _counts(engine)
    assert _run_backfill(engine) == 0, "a re-run writes nothing"
    assert _counts(engine) == before


def test_v_two_backfills_at_once_write_each_interaction_once(client, engine, ids,
                                                            monkeypatch):
    """The first holds its advisory lock while writing; the second waits for
    it (witness: `pg_blocking_pids`), then finds nothing left to write."""
    from sqlalchemy import text

    svc = _svc()
    thread = _new_thread(client, ids, engine, channel="PHONE")
    messages = [_bare_message(engine, thread) for _ in range(3)]
    real = svc.write
    holding, release = threading.Event(), threading.Event()
    pid: dict = {}

    def slow(session, message_id):
        if not holding.is_set():
            pid["first"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
            holding.set()
            assert release.wait(20)
        return real(session, message_id)

    monkeypatch.setattr(svc, "write", slow)
    out: dict = {}
    first = threading.Thread(target=lambda: out.setdefault("first", _run_backfill(engine)))
    first.start()
    try:
        assert holding.wait(20)
        second = threading.Thread(
            target=lambda: out.setdefault("second", _run_backfill(engine, "second")))
        second.start()
        assert _wait_until_blocked(engine, pid["first"], second), "the second waits"
    finally:
        release.set()
        first.join(20)
    second.join(20)
    assert out["first"] >= 3 and out["second"] == 0
    for message in messages:
        assert len(_interactions(engine, message)) == 1


def test_v_a_backfill_concurrent_with_a_message_makes_no_duplicate(client, engine, ids,
                                                                  monkeypatch):
    """A staff message held in its transaction, its interaction written but not
    committed: the backfill does not see the message and writes nothing for
    it; the message commits with its own one."""
    from turab.services import communication

    thread = _new_thread(client, ids, engine)
    real = communication.message_interactions.write
    written, release = threading.Event(), threading.Event()
    held: dict = {}

    def holding(session, message_id):
        out = real(session, message_id)
        held["message"] = message_id
        written.set()
        assert release.wait(20)
        return out

    monkeypatch.setattr(communication.message_interactions, "write", holding)
    out: dict = {}
    t = threading.Thread(target=lambda: out.setdefault(
        "r", _post_message(client, thread, {"direction": "OUTBOUND"}, ids.ACC_OPERATOR)))
    t.start()
    try:
        assert written.wait(20)
        monkeypatch.setattr(communication.message_interactions, "write", real)
        _run_backfill(engine)
        assert _interactions(engine, held["message"]) == [], "not visible yet"
    finally:
        release.set()
        t.join(20)
    assert out["r"].status_code == 201
    assert len(_interactions(engine, held["message"])) == 1
    _run_backfill(engine)
    assert len(_interactions(engine, held["message"])) == 1


def test_v_the_backfill_script_prints_counts_only(engine, capsys, monkeypatch):
    import importlib.util
    import pathlib

    path = (pathlib.Path(__file__).resolve().parents[1]
            / "db/ops/backfill_message_interactions.py")
    spec = importlib.util.spec_from_file_location("backfill_message_interactions", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("TURAB_DATABASE_URL", engine.url.render_as_string(hide_password=False))
    assert module.main([]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert len(lines) == 2 and lines[0].startswith("trace_id backfill-")
    assert lines[1].split(" ")[0] == "written" and lines[1].split(" ")[1].isdigit()


# --- (vi): the timeline's `message` ------------------------------------------------------------

@pytest.mark.parametrize("role", ROLES)
def test_vi_an_unarchived_message_shows_no_content_to_any_role(client, engine, ids, role):
    """A webhook message without the archive consent (its content withheld at
    write), and a staff message without content: the item's exact keys, no
    `body_text`, no `media_ref`, for ADMIN, OPERATOR and REVIEWER."""
    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    message = _sent(client, thread, {"direction": "OUTBOUND"}, ids.ACC_OPERATOR)
    item = _item(client, party, getattr(ids, role), message)
    assert set(item) == BASE_KEYS | {"message"}
    assert set(item["message"]) == MESSAGE_KEYS
    assert item["message"] == {"message_id": str(message), "direction": "OUTBOUND",
                               "message_type": "TEXT", "delivery_status": "UNKNOWN",
                               "occurred_at": "2026-10-25T10:00:00+00:00",
                               "content_archived": False}
    assert "metadata" not in item


@pytest.mark.parametrize("role", ROLES)
def test_vi_webhook_content_withheld_at_write_is_absent_for_every_role(client, engine, ids,
                                                                     role, monkeypatch):
    from tests.test_slice7_step3 import KEY, _msg, _post, _whatsapp

    monkeypatch.setenv("TURAB_RELAY_SIGNING_SECRET", KEY)
    party = _party(engine)
    _, thread_ref = _whatsapp(client, ids, engine, party=party)
    envelope = _msg(thread_ref, body=SECRET, media=MEDIA)
    assert _post(client, envelope).status_code == 200
    items = [i for i in _timeline(client, party, getattr(ids, role)) if "message" in i]
    assert len(items) == 1 and set(items[0]["message"]) == MESSAGE_KEYS
    assert items[0]["message"]["content_archived"] is False
    assert SECRET not in json.dumps(items) and MEDIA not in json.dumps(items)


@pytest.mark.parametrize("role", ROLES)
def test_vi_archived_content_is_shown_to_every_role(client, engine, ids, role):
    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    message = _sent(client, thread, {"direction": "OUTBOUND", "body_text": SECRET,
                                     "media_ref": MEDIA}, ids.ACC_OPERATOR)
    item = _item(client, party, getattr(ids, role), message)
    assert set(item) == BASE_KEYS | {"message"}
    assert set(item["message"]) == MESSAGE_KEYS | {"body_text", "media_ref"}
    assert (item["message"]["content_archived"], item["message"]["body_text"],
            item["message"]["media_ref"]) == (True, SECRET, MEDIA)


def test_vi_an_archived_message_without_media_shows_both_keys(client, engine, ids):
    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    message = _sent(client, thread, {"direction": "OUTBOUND", "body_text": SECRET},
                    ids.ACC_OPERATOR)
    item = _item(client, party, ids.ACC_ADMIN, message)
    assert (item["message"]["body_text"], item["message"]["media_ref"]) == (SECRET, None)


def test_vi_any_other_interaction_keeps_slice_1s_exact_keys(client, engine, ids):
    """An interaction that names no message (Slice 5's share, or any other),
    and one whose `metadata.message_id` is not a uuid: Slice 1's keys, exactly,
    no `message`."""
    party = _party(engine)
    for meta in ({}, {"source": "x"}, {"message_id": "not-a-uuid"},
                 {"message_id": str(uuid.uuid4())}):
        _exec(engine, """
            INSERT INTO turab.interactions (interaction_type, party_id, summary, occurred_at,
                                            metadata)
            VALUES ('NOTE', :p, 'NOT-A-MESSAGE-ROW', now(), CAST(:m AS jsonb))""",
              p=party, m=json.dumps(meta))
    items = _timeline(client, party, ids.ACC_ADMIN)
    assert len(items) == 4
    for item in items:
        assert set(item) == BASE_KEYS


def test_vi_the_delivery_status_is_read_live(client, engine, ids, monkeypatch):
    from tests.test_slice7_step3 import KEY, _post, _status, _whatsapp

    monkeypatch.setenv("TURAB_RELAY_SIGNING_SECRET", KEY)
    party = _party(engine)
    thread, _ = _whatsapp(client, ids, engine, party=party)
    ref = f"wamid.{uuid.uuid4().hex}"
    message = _sent(client, thread, {"direction": "OUTBOUND", "external_message_ref": ref,
                                     "delivery_status": "SENT"}, ids.ACC_OPERATOR)
    assert _item(client, party, ids.ACC_OPERATOR, message)["message"]["delivery_status"] \
        == "SENT"
    assert _post(client, _status(ref, "READ")).status_code == 200
    assert _item(client, party, ids.ACC_OPERATOR, message)["message"]["delivery_status"] \
        == "READ"


def test_vi_a_customer_still_cannot_read_a_timeline(client, engine, ids):
    r = client.get(f"/parties/{ids.AMINA}/timeline",
                   headers={"Authorization": f"Bearer {ids.ACC_AMINA}"})
    assert r.status_code in (403, 404)


# --- (vii): the confirmation link (G7-10, mandatory test 4) ---------------------------------

def test_vii_mandatory_test_4_a_phone_decision_is_linked_to_a_later_written_confirmation(
        client, engine, ids):
    """End to end over HTTP: the decision, the confirmation by `POST
    /observations`, the link; nothing earlier updated."""
    party, thread, decision = _decision(client, ids, engine)
    observed = client.post("/observations", json={
        "kind": "MESSAGE", "party_id": str(party), "observed_at": LATER,
        "raw_text": "the party confirms in writing"}, headers=_headers(ids.ACC_OPERATOR))
    assert observed.status_code == 201, observed.text
    observation = observed.json()["observation_id"]
    decision_before = _all(engine, "SELECT * FROM turab.communication_messages "
                                   "WHERE message_id = :m", m=decision)
    link = _sent(client, thread, _link_body(decision, observation), ids.ACC_OPERATOR)
    stored = _all(engine, "SELECT message_type, direction::text AS direction, metadata "
                          "FROM turab.communication_messages WHERE message_id = :m",
                  m=link)[0]
    assert (stored["message_type"], stored["direction"]) == ("CONFIRMATION_LINK", "INTERNAL")
    assert stored["metadata"] == {"content_archived": False,
                                  "decision_message_id": str(decision),
                                  "observation_id": observation}
    assert _all(engine, "SELECT * FROM turab.communication_messages WHERE message_id = :m",
                m=decision) == decision_before, "nothing earlier is updated"
    assert _one_interaction(engine, link)["interaction_type"] == "NOTE"


def test_vii_an_observation_at_the_decisions_time_is_accepted_and_links_may_repeat(
        client, engine, ids):
    party, thread, decision = _decision(client, ids, engine)
    same_time = _observation(engine, party, observed_at=AT)
    later = _observation(engine, party)
    for observation in (same_time, later, later):
        _sent(client, thread, _link_body(decision, observation), ids.ACC_OPERATOR)


@pytest.mark.parametrize("label, metadata", [
    ("absent", None),
    ("empty", {}),
    ("one key", {"decision_message_id": "D"}),
    ("an extra key", {"decision_message_id": "D", "observation_id": "O", "x": "1"}),
    ("a decision not a uuid", {"decision_message_id": "nope", "observation_id": "O"}),
    ("an observation not a string", {"decision_message_id": "D", "observation_id": 7}),
])
def test_vii_a_links_metadata_must_be_exactly_its_two_uuids(client, engine, ids, label,
                                                           metadata):
    party, thread, decision = _decision(client, ids, engine)
    observation = _observation(engine, party)
    body = {"direction": "INTERNAL", "message_type": "CONFIRMATION_LINK", "occurred_at": LATER}
    if metadata is not None:
        body["metadata"] = {k: {"D": str(decision), "O": str(observation)}.get(v, v)
                            for k, v in metadata.items()}
    problem = _refused(engine, lambda k: _post_message(client, thread, body,
                                                       ids.ACC_OPERATOR, k),
                       422, "CONFIRMATION_LINK_NOT_ACCEPTED")
    assert str(decision) not in json.dumps(problem) and str(observation) not in json.dumps(
        problem)


def test_vii_metadata_on_any_other_type_is_still_refused(client, engine, ids):
    party, thread, decision = _decision(client, ids, engine)
    observation = _observation(engine, party)
    for message_type in ("TEXT", "PHONE_DECISION"):
        _refused(engine, lambda k: _post_message(client, thread, {
            "direction": "INTERNAL", "message_type": message_type,
            "metadata": {"decision_message_id": str(decision),
                         "observation_id": str(observation)}}, ids.ACC_OPERATOR, k),
            422, "MESSAGE_METADATA_NOT_ACCEPTED")


def test_vii_a_phone_decision_and_a_link_are_internal_and_phone_only(client, engine, ids):
    party, thread, decision = _decision(client, ids, engine)
    observation = _observation(engine, party)
    for body, code in (
            ({"direction": "OUTBOUND", "message_type": "PHONE_DECISION"},
             "PHONE_DECISION_NOT_ACCEPTED"),
            ({**_link_body(decision, observation), "direction": "OUTBOUND"},
             "CONFIRMATION_LINK_NOT_ACCEPTED")):
        _refused(engine, lambda k: _post_message(client, thread, body, ids.ACC_OPERATOR, k),
                 422, code)
    for channel in ("WHATSAPP", "SMS", "IN_PERSON"):
        other = _new_thread(client, ids, engine, channel=channel, party=party,
                            ref=_ref() if channel == "WHATSAPP" else None)
        _refused(engine, lambda k: _post_message(
            client, other, {"direction": "INTERNAL", "message_type": "PHONE_DECISION"},
            ids.ACC_OPERATOR, k), 422, "PHONE_DECISION_NOT_ACCEPTED")
        _refused(engine, lambda k: _post_message(
            client, other, _link_body(decision, observation), ids.ACC_OPERATOR, k),
            422, "CONFIRMATION_LINK_NOT_ACCEPTED")


def test_vii_the_decision_must_be_an_internal_phone_decision_of_this_thread(client, engine,
                                                                           ids):
    party, thread, decision = _decision(client, ids, engine)
    observation = _observation(engine, party)
    _, other_thread, other_decision = _decision(client, ids, engine, party=party)
    plain = _sent(client, thread, {"direction": "INTERNAL"}, ids.ACC_OPERATOR)
    outbound_decision = _one(engine, """
        INSERT INTO turab.communication_messages (thread_id, direction, message_type,
                                                  occurred_at)
        VALUES (:t, 'OUTBOUND', 'PHONE_DECISION', :at) RETURNING message_id""",
                             t=thread, at=AT)
    for named in (uuid.uuid4(), other_decision, plain, outbound_decision):
        problem = _refused(engine, lambda k: _post_message(
            client, thread, _link_body(named, observation), ids.ACC_OPERATOR, k),
            422, "DECISION_NOT_LINKABLE")
        assert [e["field"] for e in problem["field_errors"]] == [
            "metadata.decision_message_id"]
    assert other_thread != thread


def test_viii_an_inbound_phone_decision_is_never_linkable(client, engine, ids, monkeypatch):
    """The webhook stores the type as given (step 3); the meaning belongs to an
    INTERNAL message only."""
    from tests.test_slice7_step3 import KEY, _msg, _post, _whatsapp

    monkeypatch.setenv("TURAB_RELAY_SIGNING_SECRET", KEY)
    party, thread, _ = _decision(client, ids, engine)
    _, thread_ref = _whatsapp(client, ids, engine, party=party)
    envelope = _msg(thread_ref)
    envelope["payload"]["message_type"] = "PHONE_DECISION"
    assert _post(client, envelope).status_code == 200
    inbound = _one(engine, "SELECT message_id FROM turab.communication_messages "
                           "WHERE external_message_ref = :r",
                   r=envelope["payload"]["external_message_ref"])
    observation = _observation(engine, party)
    _refused(engine, lambda k: _post_message(client, thread, _link_body(inbound, observation),
                                             ids.ACC_OPERATOR, k),
             422, "DECISION_NOT_LINKABLE")


@pytest.mark.parametrize("case", ["missing", "another kind", "another party", "no party",
                                  "no time", "before the decision"])
def test_vii_the_observation_must_be_linkable(client, engine, ids, case):
    party, thread, decision = _decision(client, ids, engine)
    if case == "missing":
        observation = uuid.uuid4()
    elif case == "another kind":
        observation = _observation(engine, party, kind="TEXT")
    elif case == "another party":
        observation = _observation(engine, _party(engine))
    elif case == "no party":
        observation = _one(engine, "INSERT INTO turab.observations (kind, observed_at) "
                                   "VALUES ('MESSAGE', :at) RETURNING observation_id",
                           at=LATER)
    elif case == "no time":
        observation = _observation(engine, party, observed_at=None)
    else:
        observation = _observation(engine, party, observed_at=EARLIER)
    problem = _refused(engine, lambda k: _post_message(
        client, thread, _link_body(decision, observation), ids.ACC_OPERATOR, k),
        422, "OBSERVATION_NOT_LINKABLE")
    assert [e["field"] for e in problem["field_errors"]] == ["metadata.observation_id"]


def test_vii_a_link_with_content_needs_the_archive_consent(client, engine, ids):
    party, thread, decision = _decision(client, ids, engine)
    observation = _observation(engine, party)
    _refused(engine, lambda k: _post_message(
        client, thread, _link_body(decision, observation, body_text=SECRET),
        ids.ACC_OPERATOR, k), 422, "CONTENT_NOT_ARCHIVABLE")
    _archive_consent(engine, party, thread)
    _sent(client, thread, _link_body(decision, observation, body_text=SECRET),
          ids.ACC_OPERATOR)


def test_vii_a_change_to_the_observation_in_flight_is_waited_for_then_seen(client, engine,
                                                                          ids):
    """The observation is read FOR SHARE: an UPDATE moving its time before the
    decision, held, makes the link wait (witness); committed, the link is
    refused."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    party, thread, decision = _decision(client, ids, engine)
    observation = _observation(engine, party)
    holder = Session(bind=engine)
    out: dict = {}
    try:
        holder.execute(text("UPDATE turab.observations SET observed_at = :at "
                            "WHERE observation_id = :o"), {"at": EARLIER, "o": observation})
        pid = holder.execute(text("SELECT pg_backend_pid()")).scalar_one()
        key = str(uuid.uuid4())
        before = _counts(engine)
        t = threading.Thread(target=lambda: out.setdefault("r", _post_message(
            client, thread, _link_body(decision, observation), ids.ACC_OPERATOR, key)))
        t.start()
        assert _wait_until_blocked(engine, pid, t), "the link waits for the observation"
        holder.commit()
    finally:
        holder.close()
    t.join(20)
    assert (out["r"].status_code, out["r"].json()["code"]) == (422,
                                                               "OBSERVATION_NOT_LINKABLE")
    assert _counts(engine) == before
    assert _one(engine, "SELECT count(*) FROM turab.idempotency_records "
                        "WHERE idempotency_key = :k", k=key) == 0


def test_vii_the_link_is_valid_at_its_writing_only(client, engine, ids):
    """Stated, not prevented (review of e18271a): after the link, the
    observation it names can still change, as 0007's guard does not cover a
    message's metadata. The link is unchanged by it."""
    party, thread, decision = _decision(client, ids, engine)
    observation = _observation(engine, party)
    link = _sent(client, thread, _link_body(decision, observation), ids.ACC_OPERATOR)
    _exec(engine, "UPDATE turab.observations SET observed_at = :at WHERE observation_id = :o",
          at=EARLIER, o=observation)
    assert _one(engine, "SELECT metadata->>'observation_id' FROM turab.communication_messages "
                        "WHERE message_id = :m", m=link) == str(observation)


# --- (ix): the writers of `interactions` -------------------------------------------------------

def test_ix_no_message_has_two_interactions_and_each_names_an_existing_message(engine):
    """Over the whole test database, after every test above: within the
    service's paths, no message has two interactions, and every interaction
    that names a message by a uuid names one that exists. (The writers'
    inventory by kind is the delivery's; this pins what holds of their rows.)"""
    dangling = _one(engine, """
        SELECT count(*) FROM turab.interactions i
         WHERE i.metadata->>'message_id' ~
               '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
           AND i.summary IS DISTINCT FROM 'NOT-A-MESSAGE-ROW'
           AND NOT EXISTS (SELECT 1 FROM turab.communication_messages m
                            WHERE m.message_id::text = i.metadata->>'message_id')""")
    by_message = _one(engine, "SELECT count(*) FROM turab.interactions "
                              "WHERE metadata ? 'message_id' "
                              "AND summary IS DISTINCT FROM 'NOT-A-MESSAGE-ROW'")
    dup = _one(engine, """
        SELECT count(*) FROM (SELECT metadata->>'message_id' FROM turab.interactions
                               WHERE metadata ? 'message_id'
                               GROUP BY 1 HAVING count(*) > 1) d""")
    assert by_message > 0, "the tests above wrote message interactions"
    assert dangling == 0, "the rows test_vi_any_other_* writes on purpose are excluded"
    assert dup == 0, "no message has two interactions"
