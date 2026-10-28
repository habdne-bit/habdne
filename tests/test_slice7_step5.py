"""Slice 7 step 5: the mandatory and red-team tests end to end.

Ref: `docs/gate/SLICE_7_PLAN.md` §6.1 (the four mandatory tests), §6.2 (J01,
J02, J03, S42, K05), §6.3, and G7-19 (decided in the review of d04d5c8),
which names two gaps of the earlier steps' tests to close here:
- mandatory test 1's concurrent delivery checked one event and one message,
  not one interaction (`test_mandatory_1_*`);
- K05's "another body on the key is 409" was not tested for either staff
  command (`test_k05_*`).

Every business row is made over HTTP (the staff commands, the webhook, the
observation command, the timeline); SQL is used only to read, and where the
plan's proof is a refusal by the schema itself (`0008`'s frozen links and
RESTRICT keys, the NULL-provider CHECK), which no HTTP path can reach.

**What is not claimed.** The relay's signature proves the relay's origin, not
Meta's; R-1 is UNMET. The guards of `0008` are trigger- and constraint-level,
never counted as K06. One interaction per message holds within the service's
paths. A confirmation link is valid at its writing only.
"""
from __future__ import annotations

import json
import threading
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
)
from tests.test_slice7_step3 import KEY, _msg, _post, _raw, _sign
from turab.auth.audit import AccessAuditor, RecordingAuditSink

AT = "2026-10-25T10:00:00Z"
LATER = "2026-10-25T11:00:00Z"
SECRET = "SECRET-BODY-5e75"


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("TURAB_RELAY_SIGNING_SECRET", KEY)


@pytest.fixture
def client(engine):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink()))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _whatsapp_thread(client, ids, engine, party=None):
    ref = _ref()
    return _new_thread(client, ids, engine, channel="WHATSAPP", party=party, ref=ref), ref


def _by_ref(engine, ref):
    """The message, its event and its interactions, for one provider reference."""
    messages = _all(engine, "SELECT message_id, thread_id, body_text FROM "
                            "turab.communication_messages WHERE provider = 'whatsapp' "
                            "AND external_message_ref = :r", r=ref)
    interactions = [i for m in messages for i in _all(
        engine, "SELECT interaction_id FROM turab.interactions "
                "WHERE metadata->>'message_id' = :m", m=str(m["message_id"]))]
    return messages, interactions


def _events(engine, provider_event_id):
    return _all(engine, "SELECT processing_status::text AS status FROM turab.webhook_events "
                        "WHERE provider = 'whatsapp' AND provider_event_id = :e",
                e=provider_event_id)


def _footprint(engine):
    return {t: _one(engine, f"SELECT count(*) FROM turab.{t}")
            for t in ("communication_threads", "communication_messages", "webhook_events",
                      "interactions", "audit_log")}


# --- mandatory test 1: "repeated provider webhook creates one message" (J01, S42) ---------

def test_mandatory_1_the_same_envelope_twice_makes_one_event_one_message_one_interaction(
        client, engine, ids):
    _, thread_ref = _whatsapp_thread(client, ids, engine)
    envelope = _msg(thread_ref)
    first = _post(client, envelope)
    assert first.status_code == 200 and first.content == b""
    before = _footprint(engine)
    again = _post(client, envelope)
    assert again.status_code == 200 and again.content == b""
    assert _footprint(engine) == before, "a replay of a completed event writes nothing"
    messages, interactions = _by_ref(engine, envelope["payload"]["external_message_ref"])
    assert len(_events(engine, envelope["provider_event_id"])) == 1
    assert len(messages) == 1 and len(interactions) == 1


def test_mandatory_1_concurrent_deliveries_make_one_event_one_message_one_interaction(
        client, engine, ids):
    """The gap G7-19 names: eight concurrent deliveries of one signed envelope,
    and the interaction counted too."""
    _, thread_ref = _whatsapp_thread(client, ids, engine)
    envelope = _msg(thread_ref)
    raw = _raw(envelope)
    barrier = threading.Barrier(8)
    answers: list = []

    def deliver():
        barrier.wait()
        answers.append(_post(client, raw=raw))

    threads = [threading.Thread(target=deliver) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(30)
    assert len(answers) == 8 and all(a.status_code == 200 for a in answers)
    messages, interactions = _by_ref(engine, envelope["payload"]["external_message_ref"])
    assert len(_events(engine, envelope["provider_event_id"])) == 1
    assert len(messages) == 1 and len(interactions) == 1


def test_mandatory_1_a_failed_event_is_completed_by_the_redelivery_once(client, engine, ids,
                                                                       monkeypatch):
    """A FAILED event, then the same envelope again: PROCESSED, one message, one
    interaction, and the content the redelivery carries."""
    from sqlalchemy import text

    from turab.services import webhooks

    party = _party(engine)
    thread, thread_ref = _whatsapp_thread(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    envelope = _msg(thread_ref, body=SECRET)
    real = webhooks.process

    def failing(session, event_id, env, **kw):
        outcome = real(session, event_id, env, **kw)
        session.execute(text("SELECT 1 / 0"))
        return outcome

    monkeypatch.setattr(webhooks, "process", failing)
    assert _post(client, envelope).status_code == 500
    assert [e["status"] for e in _events(engine, envelope["provider_event_id"])] == ["FAILED"]
    monkeypatch.setattr(webhooks, "process", real)
    assert _post(client, envelope).status_code == 200
    assert [e["status"] for e in _events(engine, envelope["provider_event_id"])] == [
        "PROCESSED"]
    messages, interactions = _by_ref(engine, envelope["payload"]["external_message_ref"])
    assert len(messages) == 1 and len(interactions) == 1
    assert messages[0]["body_text"] == SECRET


# --- mandatory test 2: "same provider message id cannot be inserted into another thread" ---

def test_mandatory_2_staff_first_then_the_webhook_into_another_thread_writes_nothing(
        client, engine, ids):
    first, _ = _whatsapp_thread(client, ids, engine)
    _, second_ref = _whatsapp_thread(client, ids, engine)
    ref = f"wamid.{uuid.uuid4().hex}"
    _ok(_message(client, first, {"direction": "OUTBOUND", "occurred_at": AT,
                                 "external_message_ref": ref}, ids.ACC_OPERATOR))
    before = _footprint(engine)
    envelope = _msg(second_ref, ref=ref)
    assert _post(client, envelope).status_code == 200
    assert _all(engine, "SELECT processing_status::text AS s, error_text FROM "
                        "turab.webhook_events WHERE provider_event_id = :e",
                e=envelope["provider_event_id"]) == [{"s": "IGNORED",
                                                      "error_text": "MESSAGE_REF_TAKEN"}]
    assert _footprint(engine) == {**before, "webhook_events": before["webhook_events"] + 1}
    messages, _ = _by_ref(engine, ref)
    assert [m["thread_id"] for m in messages] == [first]


def test_mandatory_2_the_webhook_first_then_staff_into_another_thread_is_409(client, engine,
                                                                            ids):
    first, first_ref = _whatsapp_thread(client, ids, engine)
    second, _ = _whatsapp_thread(client, ids, engine)
    ref = f"wamid.{uuid.uuid4().hex}"
    assert _post(client, _msg(first_ref, ref=ref)).status_code == 200
    before = _footprint(engine)
    key = str(uuid.uuid4())
    r = _message(client, second, {"direction": "OUTBOUND", "occurred_at": AT,
                                  "external_message_ref": ref}, ids.ACC_OPERATOR, key)
    assert (r.status_code, r.json()["code"]) == (409, "MESSAGE_REF_TAKEN")
    assert _footprint(engine) == before
    assert _one(engine, "SELECT count(*) FROM turab.idempotency_records "
                        "WHERE idempotency_key = :k", k=key) == 0
    messages, _ = _by_ref(engine, ref)
    assert [m["thread_id"] for m in messages] == [first]


def test_mandatory_2_the_null_provider_path_is_refused_by_the_service_and_by_0008(
        client, engine, ids):
    """A reference outside a WHATSAPP thread has no provider: the service
    refuses it (422), and 0008 part A refuses the row a path around the
    service would write (constraint level, not K06)."""
    from sqlalchemy.exc import DBAPIError

    phone = _new_thread(client, ids, engine)
    r = _message(client, phone, {"direction": "OUTBOUND", "occurred_at": AT,
                                 "external_message_ref": "wamid.x"}, ids.ACC_OPERATOR)
    assert (r.status_code, r.json()["code"]) == (422, "EXTERNAL_REF_WITHOUT_PROVIDER")
    with pytest.raises(DBAPIError):
        _exec(engine, """
            INSERT INTO turab.communication_messages
                   (thread_id, external_message_ref, direction, occurred_at)
            VALUES (:t, 'wamid.null-provider', 'OUTBOUND', now())""", t=phone)


# --- mandatory test 3: "thread/opportunity links are checked by service invariant" --------

def test_mandatory_3_the_sellers_thread_about_the_buyers_opportunity_is_accepted_and_frozen(
        client, engine, ids):
    """The seller's thread naming the buyer's SALE opportunity is accepted; an
    inconsistent link is refused writing nothing; the links never change
    afterwards (0008); the named parents' deletion is refused (D2)."""
    from sqlalchemy.exc import DBAPIError

    world = _sale_world(client, engine, ids)
    seller_thread = uuid.UUID(_ok(client.post("/communication/threads", json={
        "channel": "PHONE", "party_id": str(world["seller"]),
        "opportunity_id": str(world["opportunity"])},
        headers=_headers(ids.ACC_OPERATOR)))["thread_id"])
    before = _footprint(engine)
    stranger = _party(engine)
    r = client.post("/communication/threads", json={
        "channel": "PHONE", "party_id": str(stranger),
        "opportunity_id": str(world["opportunity"])}, headers=_headers(ids.ACC_OPERATOR))
    assert (r.status_code, r.json()["code"]) == (422, "THREAD_LINKS_INCONSISTENT")
    assert _footprint(engine) == {**before}
    with pytest.raises(DBAPIError, match="never change"):
        _exec(engine, "UPDATE turab.communication_threads SET party_id = :p "
                      "WHERE thread_id = :t", p=stranger, t=seller_thread)
    with pytest.raises(DBAPIError):
        _exec(engine, "DELETE FROM turab.opportunities WHERE opportunity_id = :o",
              o=world["opportunity"])
    assert _one(engine, "SELECT opportunity_id FROM turab.communication_threads "
                        "WHERE thread_id = :t", t=seller_thread) == world["opportunity"]


# --- mandatory test 4: "phone decision can be linked to later written confirmation" -------

def test_mandatory_4_over_http_the_decision_the_confirmation_the_link_and_the_timeline(
        client, engine, ids):
    """Every row over HTTP, then read back through the timeline: the decision,
    the observation, the link, each as a NOTE interaction of the party."""
    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    decision = _ok(_message(client, thread, {"direction": "INTERNAL", "occurred_at": AT,
                                             "message_type": "PHONE_DECISION"},
                            ids.ACC_OPERATOR))["message_id"]
    observed = client.post("/observations", json={
        "kind": "MESSAGE", "party_id": str(party), "observed_at": LATER,
        "raw_text": "confirmed in writing"}, headers=_headers(ids.ACC_OPERATOR))
    assert observed.status_code == 201, observed.text
    link = _ok(_message(client, thread, {
        "direction": "INTERNAL", "occurred_at": LATER, "message_type": "CONFIRMATION_LINK",
        "metadata": {"decision_message_id": decision,
                     "observation_id": observed.json()["observation_id"]}},
        ids.ACC_OPERATOR))["message_id"]
    items = client.get(f"/parties/{party}/timeline",
                       headers={"Authorization": f"Bearer {ids.ACC_REVIEWER}"}).json()["items"]
    shown = {i["message"]["message_id"]: i for i in items if "message" in i}
    assert set(shown) == {decision, link}
    assert {shown[m]["message"]["message_type"] for m in shown} == {"PHONE_DECISION",
                                                                     "CONFIRMATION_LINK"}
    assert all(shown[m]["interaction_type"] == "NOTE" for m in shown)


# --- J03: no content without a consent valid at write time, end to end --------------------

def test_j03_content_reaches_the_timeline_only_under_the_consent(client, engine, ids):
    """By webhook, without then with the archive consent: the event store holds
    no content in either case; the message holds it only under the consent;
    the timeline shows it only when archived."""
    party = _party(engine)
    thread, thread_ref = _whatsapp_thread(client, ids, engine, party=party)
    without = _msg(thread_ref, body=SECRET)
    assert _post(client, without).status_code == 200
    _archive_consent(engine, party, thread)
    with_consent = _msg(thread_ref, body=SECRET)
    assert _post(client, with_consent).status_code == 200
    payloads = _all(engine, "SELECT payload::text AS p FROM turab.webhook_events "
                            "WHERE provider_event_id IN (:a, :b)",
                    a=without["provider_event_id"], b=with_consent["provider_event_id"])
    assert len(payloads) == 2 and all(SECRET not in p["p"] for p in payloads)
    stored = {name: _by_ref(engine, env["payload"]["external_message_ref"])[0]
              for name, env in (("without", without), ("with", with_consent))}
    assert [m["body_text"] for m in stored["without"]] == [None], \
        "the message holds no content without the consent"
    assert [m["body_text"] for m in stored["with"]] == [SECRET]
    items = client.get(f"/parties/{party}/timeline",
                       headers={"Authorization": f"Bearer {ids.ACC_OPERATOR}"}).json()["items"]
    bodies = {i["message"].get("body_text") for i in items if "message" in i}
    assert bodies == {None, SECRET}
    archived = [i for i in items if i["message"]["content_archived"]]
    assert len(archived) == 1 and archived[0]["message"]["body_text"] == SECRET


# --- K05: each staff POST replays with its key; another body on the key is 409 ------------

def test_k05_the_thread_command_replays_and_refuses_another_body_on_its_key(client, engine,
                                                                          ids):
    """The gap G7-19 names, for the thread command."""
    party = str(_party(engine))
    key = str(uuid.uuid4())
    body = {"channel": "PHONE", "party_id": party}
    first = client.post("/communication/threads", json=body,
                        headers=_headers(ids.ACC_OPERATOR, key))
    assert first.status_code == 201
    before = _footprint(engine)
    replay = client.post("/communication/threads", json=body,
                         headers=_headers(ids.ACC_OPERATOR, key))
    assert (replay.status_code, replay.json()) == (201, first.json())
    other = client.post("/communication/threads", json={**body, "channel": "SMS"},
                        headers=_headers(ids.ACC_OPERATOR, key))
    assert (other.status_code, other.json()["code"]) == (409, "IDEMPOTENCY_KEY_CONFLICT")
    assert _footprint(engine) == before


def test_k05_the_message_command_replays_and_refuses_another_body_on_its_key(client, engine,
                                                                           ids):
    """The gap G7-19 names, for the message command."""
    thread = _new_thread(client, ids, engine)
    key = str(uuid.uuid4())
    body = {"direction": "OUTBOUND", "occurred_at": AT}
    first = _message(client, thread, body, ids.ACC_OPERATOR, key)
    assert first.status_code == 201
    before = _footprint(engine)
    replay = _message(client, thread, body, ids.ACC_OPERATOR, key)
    assert (replay.status_code, replay.json()) == (201, first.json())
    other = _message(client, thread, {**body, "direction": "INTERNAL"}, ids.ACC_OPERATOR, key)
    assert (other.status_code, other.json()["code"]) == (409, "IDEMPOTENCY_KEY_CONFLICT")
    assert _footprint(engine) == before


# --- S41: an unverified webhook writes nothing, the relay's origin only -------------------

def test_s41_an_unsigned_or_missigned_delivery_writes_nothing(client, engine, ids):
    """The check proves the relay's origin, never Meta's signature (R-1 UNMET)."""
    _, thread_ref = _whatsapp_thread(client, ids, engine)
    raw = _raw(_msg(thread_ref))
    before = _footprint(engine)
    for signature in (None, _sign(raw, "not-the-relay")):
        r = _post(client, raw=raw, signature=signature, sign=signature is not None)
        assert (r.status_code, r.json()["code"]) == (401, "UNAUTHENTICATED")
    assert _footprint(engine) == before
