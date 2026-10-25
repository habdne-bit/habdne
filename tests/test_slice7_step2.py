"""Slice 7 step 2: `postCommunicationThreads` and `postCommunicationThreadsThreadIdMessages`.

Ref: `docs/gate/SLICE_7_PLAN.md` revision 8: G7-3 (the thread reference),
G7-4 (the message identity), G7-6 (the links, mandatory test 3), G7-7 with
CORRECTION-006, G7-9 (content and consent), G7-11 (audit), G7-16 (i)-(vi)
(decided in the review of 0f423d2); RFC-001 R5.3b; `services/communication.py`,
`api/routes/communication.py`. CORRECTION-006's own tests are
`tests/test_correction_006.py`.

**What the review of 0f423d2 asked to see tested:** G7-16 (iv), the thread row
locked FOR UPDATE before the message is inserted, with two concurrent
messages of different times (`test_iv_two_concurrent_messages_*`); and
`field_errors` carrying no row id and no database text
(`test_no_refusal_carries_an_id_or_database_text`).

**Isolation.** HTTP tests commit to the shared test database. Each test builds
its own parties' threads and, where an opportunity is needed, its own world
through the real matching run and the real review. Migration 0008 refuses a
thread's or a message's DELETE, so nothing written here is removed.
"""
from __future__ import annotations

import json
import logging
import re
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.test_slice4_step7 import _all, _criterion, _exec, _offer, _one, _property, _run
from turab.auth.audit import AccessAuditor, RecordingAuditSink

UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
SECRET = "SECRET-BODY-7f3e"
AT = "2026-10-25T10:00:00Z"
CHANNELS = ("WHATSAPP", "PHONE", "SMS", "EMAIL", "WEB", "IN_PERSON", "OTHER")


def _service():
    """Imported where used, so that this file is collected on a tree without
    step 2's code and each test there fails on its own (the before record)."""
    from turab.services import communication

    return communication


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

def _headers(account, key=None):
    return {"Authorization": f"Bearer {account}",
            "Idempotency-Key": key or str(uuid.uuid4())}


def _thread(client, body, account, key=None):
    return client.post("/communication/threads", json=body, headers=_headers(account, key))


def _message(client, thread_id, body, account, key=None):
    return client.post(f"/communication/threads/{thread_id}/messages", json=body,
                       headers=_headers(account, key))


def _ok(response, status=201):
    assert response.status_code == status, response.text
    return response.json()


def _party(engine):
    return _one(engine, "INSERT INTO turab.parties (kind) VALUES ('PERSON') RETURNING party_id")


def _ref():
    return f"{uuid.uuid4().hex[:10]}:{uuid.uuid4().hex[:10]}"


def _new_thread(client, ids, engine, *, channel="PHONE", party=None, ref=None):
    body = {"channel": channel, "party_id": str(party or _party(engine))}
    if ref is not None:
        body["external_thread_ref"] = ref
    return uuid.UUID(_ok(_thread(client, body, ids.ACC_OPERATOR))["thread_id"])


def _footprint(engine, key=None):
    """Everything either command could write, and the key."""
    return {
        "threads": _one(engine, "SELECT count(*) FROM turab.communication_threads"),
        "messages": _one(engine, "SELECT count(*) FROM turab.communication_messages"),
        "audit": _one(engine, "SELECT count(*) FROM turab.audit_log WHERE entity_table IN "
                              "('communication_threads', 'communication_messages')"),
        "key": None if key is None else _one(
            engine, "SELECT count(*) FROM turab.idempotency_records "
                    "WHERE idempotency_key = :k", k=key),
    }


def _refused(engine, call, status, code):
    """The refusal, and nothing written: no thread, no message, no audit row,
    no key consumed. Returns the problem body."""
    key = str(uuid.uuid4())
    before = _footprint(engine, key)
    response = call(key)
    assert (response.status_code, response.json().get("code")) == (status, code), response.text
    assert _footprint(engine, key) == before, "a refusal writes nothing and consumes no key"
    return response.json()


def _sale_world(client, engine, ids, *, buyer=None):
    """One APPROVED SALE opportunity through the real run and the real review:
    the buyer's request (AMINA by default) against BRAHIM's offer, so the
    buyer and the seller are different parties."""
    buyer = buyer or ids.AMINA
    req = _one(engine, """
        INSERT INTO turab.requests (party_id, transaction_intent, status, management_mode,
                                    claim_status, budget_max_dzd, budget_importance,
                                    property_type_importance, last_confirmed_at)
        VALUES (:p, 'BUY', 'ACTIVE', 'ASSISTED', 'UNCLAIMED', 30000000, 'REQUIRED',
                'REQUIRED', now() - interval '1 day')
        RETURNING request_id""", p=buyer)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    prop = _property(engine)
    offer = _offer(engine, ids, prop)
    run = _run(client, ids, req, [prop])
    assert run.status_code == 201, run.text
    [m] = run.json()["matches"]
    approved = client.post(f"/matches/{m['match_id']}/review", json={"decision": "APPROVED"},
                           headers=_headers(ids.ACC_REVIEWER))
    assert approved.status_code == 200, approved.text
    return {"request": req, "property": prop, "offer": offer, "match": m["match_id"],
            "opportunity": uuid.UUID(approved.json()["opportunity"]["opportunity_id"]),
            "buyer": buyer, "seller": ids.BRAHIM}


def _archive_consent(engine, party, thread_id, *, scope="COMMUNICATION_ARCHIVE"):
    grant = _one(engine, """
        INSERT INTO turab.consent_grants (party_id, scope, channel, consent_version, granted_at)
        VALUES (:p, CAST(:s AS turab.consent_scope), 'WHATSAPP', 'v1',
                now() - interval '1 day')
        RETURNING consent_id""", p=party, s=scope)
    _exec(engine, """
        INSERT INTO turab.resource_consent_bindings (consent_id, purpose, thread_id, bound_at)
        VALUES (:c, CAST(:s AS turab.consent_scope), :t, now() - interval '1 hour')""",
          c=grant, s=scope, t=thread_id)
    return grant


def _stored(engine, message_id):
    return _all(engine, """
        SELECT thread_id, provider, external_message_ref, direction::text AS direction,
               message_type, body_text, media_ref, delivery_status::text AS delivery_status,
               sent_by_account_id, metadata
          FROM turab.communication_messages WHERE message_id = :m""", m=message_id)[0]


def _thread_row(engine, thread_id):
    return _all(engine, """
        SELECT channel::text AS channel, party_id, request_id, property_id, opportunity_id,
               external_thread_ref, created_by_account_id, last_message_at
          FROM turab.communication_threads WHERE thread_id = :t""", t=thread_id)[0]


# ======================================================================================
# Who may call them (contract roles; RFC-001 R5.3b)
# ======================================================================================

@pytest.mark.parametrize("account", ["ACC_ADMIN", "ACC_OPERATOR"])
def test_admin_and_operator_create_a_thread_and_a_message(client, engine, ids, account):
    who = getattr(ids, account)
    party = _party(engine)
    body = _ok(_thread(client, {"channel": "PHONE", "party_id": str(party)}, who))
    assert set(body) == {"thread_id", "opened_at"}
    row = _thread_row(engine, body["thread_id"])
    assert (row["party_id"], row["created_by_account_id"]) == (party, who)
    sent = _ok(_message(client, body["thread_id"],
                        {"direction": "INTERNAL", "occurred_at": AT}, who))
    assert set(sent) == {"message_id", "delivery_status"}
    assert _stored(engine, sent["message_id"])["sent_by_account_id"] == who


@pytest.mark.parametrize("account", ["ACC_REVIEWER", "ACC_AMINA"])
def test_a_reviewer_and_a_customer_are_refused_both_writing_nothing(client, engine, ids,
                                                                    account):
    who = getattr(ids, account)
    thread = _new_thread(client, ids, engine)
    _refused(engine, lambda k: _thread(client, {"channel": "PHONE",
                                                "party_id": str(ids.AMINA)}, who, k),
             403, "ROLE_NOT_PERMITTED")
    _refused(engine, lambda k: _message(client, thread, {"direction": "INTERNAL",
                                                         "occurred_at": AT}, who, k),
             403, "ROLE_NOT_PERMITTED")


def test_an_anonymous_caller_is_refused_both(client, engine, ids):
    thread = _new_thread(client, ids, engine)
    assert client.post("/communication/threads",
                       json={"channel": "PHONE", "party_id": str(ids.AMINA)}).status_code == 401
    assert client.post(f"/communication/threads/{thread}/messages",
                       json={"direction": "INTERNAL", "occurred_at": AT}).status_code == 401


def test_an_unknown_thread_is_403_and_the_denial_is_recorded(client, engine, ids, sink):
    """RFC-001 R5.3b (plan revision 8): a failed staff object check is 403
    OBJECT_NOT_AUTHORIZED, recorded with its kind and id, not 404."""
    unknown = uuid.uuid4()
    _refused(engine, lambda k: _message(client, unknown, {"direction": "INTERNAL",
                                                          "occurred_at": AT},
                                        ids.ACC_OPERATOR, k),
             403, "OBJECT_NOT_AUTHORIZED")
    [denied] = [x for x in sink.records if x.event.value == "DENIED"
                and x.operation_id == "postCommunicationThreadsThreadIdMessages"]
    assert (denied.reason_code, denied.resource_kind, denied.resource_id) == (
        "OBJECT_NOT_AUTHORIZED", "COMMUNICATION_THREAD", unknown)


# ======================================================================================
# The thread: CORRECTION-006, G7-6 (mandatory test 3), G7-3
# ======================================================================================

@pytest.mark.parametrize("body", [
    {"channel": "PHONE"},
    {"channel": "PHONE", "party_id": None},
], ids=["absent", "null"])
def test_correction_006_a_thread_without_a_party_is_refused(client, engine, ids, body):
    problem = _refused(engine, lambda k: _thread(client, body, ids.ACC_OPERATOR, k),
                       422, "VALIDATION_FAILED")
    assert [e["field"] for e in problem["field_errors"]] == ["party_id"]


@pytest.mark.parametrize("field", ["party_id", "request_id", "property_id", "opportunity_id"])
def test_rule_4_an_id_naming_no_row_is_refused_by_field(client, engine, ids, field):
    body = {"channel": "PHONE", "party_id": str(_party(engine)), field: str(uuid.uuid4())}
    problem = _refused(engine, lambda k: _thread(client, body, ids.ACC_OPERATOR, k),
                       422, "LINKED_RECORD_NOT_FOUND")
    assert problem["field_errors"] == [{"field": field, "code": "NOT_FOUND",
                                        "message": "names no record"}]


def test_rule_0_a_named_opportunity_must_be_a_sale(client, engine, ids):
    """The type is CHECKED, not assumed (§0.2): the approved match's evaluated
    offer turned RENT, then the request's intent turned RENT, each refused.
    Both changes are fixtures; no SALE-only path produces them."""
    world = _sale_world(client, engine, ids)
    body = {"channel": "PHONE", "party_id": str(world["buyer"]),
            "opportunity_id": str(world["opportunity"])}
    _ok(_thread(client, body, ids.ACC_OPERATOR))
    _exec(engine, "UPDATE turab.property_offers SET transaction_type = 'RENT' "
                  "WHERE offer_id = :o", o=world["offer"])
    problem = _refused(engine, lambda k: _thread(client, body, ids.ACC_OPERATOR, k),
                       422, "OPPORTUNITY_NOT_SALE")
    assert [e["field"] for e in problem["field_errors"]] == ["opportunity_id"]
    _exec(engine, "UPDATE turab.property_offers SET transaction_type = 'SALE' "
                  "WHERE offer_id = :o", o=world["offer"])
    _exec(engine, "UPDATE turab.requests SET transaction_intent = 'RENT' "
                  "WHERE request_id = :r", r=world["request"])
    _refused(engine, lambda k: _thread(client, body, ids.ACC_OPERATOR, k),
             422, "OPPORTUNITY_NOT_SALE")


def test_rule_1_the_opportunitys_buyer_and_seller_are_accepted_with_its_own_links(
        client, engine, ids):
    world = _sale_world(client, engine, ids)
    for party in (world["buyer"], world["seller"]):
        body = {"channel": "PHONE", "party_id": str(party),
                "opportunity_id": str(world["opportunity"]),
                "request_id": str(world["request"]), "property_id": str(world["property"])}
        row = _thread_row(engine, _ok(_thread(client, body, ids.ACC_OPERATOR))["thread_id"])
        assert (row["party_id"], row["opportunity_id"], row["request_id"],
                row["property_id"]) == (party, world["opportunity"], world["request"],
                                        world["property"])


@pytest.mark.parametrize("change, field, code", [
    ("party", "party_id", "NOT_A_PARTY_OF_THE_OPPORTUNITY"),
    ("request", "request_id", "NOT_THE_OPPORTUNITYS_REQUEST"),
    ("property", "property_id", "NOT_THE_OPPORTUNITYS_PROPERTY"),
])
def test_rule_1_a_link_the_opportunity_does_not_have_is_refused(client, engine, ids,
                                                                change, field, code):
    world = _sale_world(client, engine, ids)
    body = {"channel": "PHONE", "party_id": str(world["buyer"]),
            "opportunity_id": str(world["opportunity"])}
    if change == "party":
        body["party_id"] = str(_party(engine))
    elif change == "request":
        body["request_id"] = str(ids.REQ_AMINA)
    else:
        body["property_id"] = str(_property(engine))
    problem = _refused(engine, lambda k: _thread(client, body, ids.ACC_OPERATOR, k),
                       422, "THREAD_LINKS_INCONSISTENT")
    assert [(e["field"], e["code"]) for e in problem["field_errors"]] == [(field, code)]


def test_rule_2_a_request_without_an_opportunity_needs_its_own_party(client, engine, ids):
    req = _one(engine, """
        INSERT INTO turab.requests (party_id, transaction_intent, status, management_mode,
                                    claim_status)
        VALUES (:p, 'BUY', 'ACTIVE', 'ASSISTED', 'UNCLAIMED') RETURNING request_id""",
               p=ids.AMINA)
    _ok(_thread(client, {"channel": "PHONE", "party_id": str(ids.AMINA),
                         "request_id": str(req)}, ids.ACC_OPERATOR))
    problem = _refused(engine, lambda k: _thread(
        client, {"channel": "PHONE", "party_id": str(ids.BRAHIM), "request_id": str(req)},
        ids.ACC_OPERATOR, k), 422, "THREAD_LINKS_INCONSISTENT")
    assert [(e["field"], e["code"]) for e in problem["field_errors"]] == [
        ("party_id", "NOT_THE_REQUESTS_PARTY")]


def test_rule_3_a_property_without_an_opportunity_needs_one_of_its_offers_party(
        client, engine, ids):
    """The party of one of the property's offers; a relation is not accepted
    as the reason (G7-6 rule 3)."""
    prop = _property(engine)
    _offer(engine, ids, prop)                       # BRAHIM's
    _ok(_thread(client, {"channel": "PHONE", "party_id": str(ids.BRAHIM),
                         "property_id": str(prop)}, ids.ACC_OPERATOR))
    related = _party(engine)
    _exec(engine, """
        INSERT INTO turab.party_property_relations (party_id, property_id, relation_code,
                                                    valid_from)
        VALUES (:party, :p, 'OWNER_DECLARED', now() - interval '1 day')""",
          party=related, p=prop)
    problem = _refused(engine, lambda k: _thread(
        client, {"channel": "PHONE", "party_id": str(related), "property_id": str(prop)},
        ids.ACC_OPERATOR, k), 422, "THREAD_LINKS_INCONSISTENT")
    assert [(e["field"], e["code"]) for e in problem["field_errors"]] == [
        ("party_id", "NOT_A_PARTY_OF_THE_PROPERTYS_OFFERS")]


def test_the_links_are_frozen_after_creation(client, engine, ids):
    """D2 (migration 0008, part D): what the service checked at creation
    cannot be changed afterwards, by any writer."""
    thread = _new_thread(client, ids, engine)
    with pytest.raises(Exception, match="a thread's links never change"):
        _exec(engine, "UPDATE turab.communication_threads SET party_id = :p "
                      "WHERE thread_id = :t", p=ids.AMINA, t=thread)


@pytest.mark.parametrize("ref", ["abc", ":x", "x:", "a:b:c", ""])
def test_g7_3_an_unscoped_whatsapp_reference_is_refused(client, engine, ids, ref):
    problem = _refused(engine, lambda k: _thread(
        client, {"channel": "WHATSAPP", "party_id": str(_party(engine)),
                 "external_thread_ref": ref}, ids.ACC_OPERATOR, k),
        422, "THREAD_REF_NOT_SCOPED")
    assert [e["field"] for e in problem["field_errors"]] == ["external_thread_ref"]


def test_g7_3_a_taken_whatsapp_reference_is_409_and_other_channels_are_free(client, engine,
                                                                          ids):
    ref = _ref()
    first = _new_thread(client, ids, engine, channel="WHATSAPP", ref=ref)
    assert _thread_row(engine, first)["external_thread_ref"] == ref
    _refused(engine, lambda k: _thread(
        client, {"channel": "WHATSAPP", "party_id": str(_party(engine)),
                 "external_thread_ref": ref}, ids.ACC_OPERATOR, k), 409, "THREAD_REF_TAKEN")
    for channel in ("PHONE", "SMS"):
        _new_thread(client, ids, engine, channel=channel, ref=ref)
    _new_thread(client, ids, engine, channel=channel, ref="not scoped")


def test_g7_3_a_reference_taken_after_the_check_is_the_same_409(client, engine, ids,
                                                                monkeypatch):
    """The concurrent case: a reference committed by another command between
    the pre-check and the INSERT. With the pre-check made blind, the index
    (0008, part E) refuses the INSERT, and the service answers the same typed
    409, not a 500. The transaction rolls back, the claim with it."""
    ref = _ref()
    _new_thread(client, ids, engine, channel="WHATSAPP", ref=ref)
    monkeypatch.setattr(_service(), "_refuse_taken_thread_ref",
                        lambda session, ref: None)
    _refused(engine, lambda k: _thread(
        client, {"channel": "WHATSAPP", "party_id": str(_party(engine)),
                 "external_thread_ref": ref}, ids.ACC_OPERATOR, k), 409, "THREAD_REF_TAKEN")


def test_a_thread_is_audited_and_a_replay_writes_nothing(client, engine, ids):
    key = str(uuid.uuid4())
    body = {"channel": "WHATSAPP", "party_id": str(_party(engine)),
            "external_thread_ref": _ref()}
    first = _ok(_thread(client, body, ids.ACC_OPERATOR, key))
    audit = _all(engine, """SELECT action, actor_account_id, new_row FROM turab.audit_log
                             WHERE entity_table = 'communication_threads'
                               AND entity_id = :t""", t=first["thread_id"])
    assert [(a["action"], a["actor_account_id"]) for a in audit] == [
        ("INSERT", ids.ACC_OPERATOR)]
    before = _footprint(engine, key)
    again = _ok(_thread(client, body, ids.ACC_OPERATOR, key))
    assert again == first
    assert _footprint(engine, key) == before


# ======================================================================================
# The message: G7-16 (i), (ii), (iii), (v); G7-4
# ======================================================================================

def test_i_inbound_is_refused(client, engine, ids):
    thread = _new_thread(client, ids, engine)
    problem = _refused(engine, lambda k: _message(
        client, thread, {"direction": "INBOUND", "occurred_at": AT}, ids.ACC_OPERATOR, k),
        422, "DIRECTION_NOT_ACCEPTED")
    assert [e["field"] for e in problem["field_errors"]] == ["direction"]


@pytest.mark.parametrize("status", ["QUEUED", "SENT", "DELIVERED", "READ", "FAILED",
                                    "UNKNOWN", None])
def test_ii_an_outbound_message_keeps_the_status_it_states(client, engine, ids, status):
    thread = _new_thread(client, ids, engine)
    body = {"direction": "OUTBOUND", "occurred_at": AT}
    if status is not None:
        body["delivery_status"] = status
    sent = _ok(_message(client, thread, body, ids.ACC_OPERATOR))
    assert sent["delivery_status"] == (status or "UNKNOWN")
    assert _stored(engine, sent["message_id"])["delivery_status"] == (status or "UNKNOWN")


@pytest.mark.parametrize("status", ["QUEUED", "SENT", "DELIVERED", "READ", "FAILED"])
def test_ii_an_internal_message_states_no_status_but_unknown(client, engine, ids, status):
    thread = _new_thread(client, ids, engine)
    _refused(engine, lambda k: _message(
        client, thread, {"direction": "INTERNAL", "occurred_at": AT,
                         "delivery_status": status}, ids.ACC_OPERATOR, k),
        422, "DELIVERY_STATUS_NOT_ACCEPTED")
    for body in ({"direction": "INTERNAL", "occurred_at": AT, "delivery_status": "UNKNOWN"},
                 {"direction": "INTERNAL", "occurred_at": AT}):
        assert _ok(_message(client, thread, body, ids.ACC_OPERATOR))[
            "delivery_status"] == "UNKNOWN"


def test_iii_metadata_is_absent_or_empty_and_the_service_writes_its_own(client, engine,
                                                                       ids):
    thread = _new_thread(client, ids, engine)
    for metadata in ({"x": 1}, {"content_archived": True}, {"note": SECRET}):
        _refused(engine, lambda k: _message(
            client, thread, {"direction": "INTERNAL", "occurred_at": AT,
                             "metadata": metadata}, ids.ACC_OPERATOR, k),
            422, "MESSAGE_METADATA_NOT_ACCEPTED")
    sent = _ok(_message(client, thread, {"direction": "INTERNAL", "occurred_at": AT,
                                         "metadata": {}}, ids.ACC_OPERATOR))
    assert _stored(engine, sent["message_id"])["metadata"] == {"content_archived": False}


@pytest.mark.parametrize("message_type", ["PHONE_DECISION", "CONFIRMATION_LINK"])
def test_v_the_types_g7_10_gives_a_meaning_are_reserved(client, engine, ids, message_type):
    thread = _new_thread(client, ids, engine)
    _refused(engine, lambda k: _message(
        client, thread, {"direction": "INTERNAL", "occurred_at": AT,
                         "message_type": message_type}, ids.ACC_OPERATOR, k),
        422, "MESSAGE_TYPE_RESERVED")


def test_v_any_other_type_is_free_text_and_text_is_the_default(client, engine, ids):
    thread = _new_thread(client, ids, engine)
    for given, stored in ((None, "TEXT"), ("CALL_SUMMARY", "CALL_SUMMARY"),
                          ("phone_decision", "phone_decision")):
        body = {"direction": "INTERNAL", "occurred_at": AT}
        if given is not None:
            body["message_type"] = given
        sent = _ok(_message(client, thread, body, ids.ACC_OPERATOR))
        assert _stored(engine, sent["message_id"])["message_type"] == stored


def test_g7_4_an_internal_message_carries_no_reference(client, engine, ids):
    thread = _new_thread(client, ids, engine, channel="WHATSAPP", ref=_ref())
    _refused(engine, lambda k: _message(
        client, thread, {"direction": "INTERNAL", "occurred_at": AT,
                         "external_message_ref": f"wamid.{uuid.uuid4().hex}"},
        ids.ACC_OPERATOR, k), 422, "INTERNAL_MESSAGE_REF_NOT_ACCEPTED")


@pytest.mark.parametrize("channel", [c for c in CHANNELS if c != "WHATSAPP"])
def test_g7_4_a_reference_outside_a_whatsapp_thread_is_refused(client, engine, ids, channel):
    thread = _new_thread(client, ids, engine, channel=channel)
    _refused(engine, lambda k: _message(
        client, thread, {"direction": "OUTBOUND", "occurred_at": AT,
                         "external_message_ref": f"wamid.{uuid.uuid4().hex}"},
        ids.ACC_OPERATOR, k), 422, "EXTERNAL_REF_WITHOUT_PROVIDER")


def test_g7_4_in_a_whatsapp_thread_the_service_sets_the_provider(client, engine, ids):
    thread = _new_thread(client, ids, engine, channel="WHATSAPP", ref=_ref())
    ref = f"wamid.{uuid.uuid4().hex}"
    with_ref = _ok(_message(client, thread, {"direction": "OUTBOUND", "occurred_at": AT,
                                             "external_message_ref": ref},
                            ids.ACC_OPERATOR))
    assert (_stored(engine, with_ref["message_id"])["provider"],
            _stored(engine, with_ref["message_id"])["external_message_ref"]) == ("whatsapp",
                                                                                ref)
    without = _ok(_message(client, thread, {"direction": "OUTBOUND", "occurred_at": AT},
                           ids.ACC_OPERATOR))
    assert _stored(engine, without["message_id"])["provider"] is None


def test_g7_4_a_recorded_reference_is_409_in_any_thread(client, engine, ids):
    """Mandatory test 2: the same provider message id cannot be inserted into
    another thread, nor twice into one."""
    ref = f"wamid.{uuid.uuid4().hex}"
    first = _new_thread(client, ids, engine, channel="WHATSAPP", ref=_ref())
    second = _new_thread(client, ids, engine, channel="WHATSAPP", ref=_ref())
    _ok(_message(client, first, {"direction": "OUTBOUND", "occurred_at": AT,
                                 "external_message_ref": ref}, ids.ACC_OPERATOR))
    for thread in (first, second):
        _refused(engine, lambda k: _message(
            client, thread, {"direction": "OUTBOUND", "occurred_at": AT,
                             "external_message_ref": ref}, ids.ACC_OPERATOR, k),
            409, "MESSAGE_REF_TAKEN")


def test_g7_4_a_reference_recorded_after_the_check_is_the_same_409(client, engine, ids,
                                                                   monkeypatch):
    ref = f"wamid.{uuid.uuid4().hex}"
    thread = _new_thread(client, ids, engine, channel="WHATSAPP", ref=_ref())
    _ok(_message(client, thread, {"direction": "OUTBOUND", "occurred_at": AT,
                                  "external_message_ref": ref}, ids.ACC_OPERATOR))
    monkeypatch.setattr(_service(), "_refuse_taken_message_ref",
                        lambda session, ref: None)
    _refused(engine, lambda k: _message(
        client, thread, {"direction": "OUTBOUND", "occurred_at": AT,
                         "external_message_ref": ref}, ids.ACC_OPERATOR, k),
        409, "MESSAGE_REF_TAKEN")


# ======================================================================================
# The message: G7-9, content and consent
# ======================================================================================

@pytest.mark.parametrize("content", [{"body_text": SECRET}, {"media_ref": "media://x"},
                                     {"body_text": ""}])
def test_g7_9_content_without_the_archive_consent_is_refused(client, engine, ids, content):
    thread = _new_thread(client, ids, engine)
    _refused(engine, lambda k: _message(
        client, thread, {"direction": "OUTBOUND", "occurred_at": AT, **content},
        ids.ACC_OPERATOR, k), 422, "CONTENT_NOT_ARCHIVABLE")


def test_g7_9_with_the_archive_consent_content_is_archived(client, engine, ids):
    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    sent = _ok(_message(client, thread, {"direction": "OUTBOUND", "occurred_at": AT,
                                         "body_text": SECRET, "media_ref": "media://x"},
                        ids.ACC_OPERATOR))
    row = _stored(engine, sent["message_id"])
    assert (row["body_text"], row["media_ref"], row["metadata"]) == (
        SECRET, "media://x", {"content_archived": True})


@pytest.mark.parametrize("case", ["revoked", "bound_to_another_thread",
                                  "bound_for_another_purpose", "binding_revoked"])
def test_g7_9_a_consent_that_does_not_hold_archives_nothing(client, engine, ids, case):
    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    if case == "bound_to_another_thread":
        _archive_consent(engine, party, _new_thread(client, ids, engine, party=party))
    elif case == "bound_for_another_purpose":
        grant = _one(engine, """
            INSERT INTO turab.consent_grants (party_id, scope, channel, consent_version,
                                              granted_at)
            VALUES (:p, 'CONTACT_BEFORE_SHARING', 'WHATSAPP', 'v1', now() - interval '1 day')
            RETURNING consent_id""", p=party)
        _exec(engine, """INSERT INTO turab.resource_consent_bindings (consent_id, purpose,
                                                                     thread_id, bound_at)
                         VALUES (:c, 'CONTACT_BEFORE_SHARING', :t, now())""",
              c=grant, t=thread)
    else:
        grant = _archive_consent(engine, party, thread)
        if case == "revoked":
            _exec(engine, "UPDATE turab.consent_grants SET status = 'REVOKED', "
                          "revoked_at = now() WHERE consent_id = :c", c=grant)
        else:
            _exec(engine, "UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                          "WHERE consent_id = :c", c=grant)
    _refused(engine, lambda k: _message(
        client, thread, {"direction": "OUTBOUND", "occurred_at": AT, "body_text": SECRET},
        ids.ACC_OPERATOR, k), 422, "CONTENT_NOT_ARCHIVABLE")


def test_g7_9_an_internal_note_is_held_to_the_same_rule(client, engine, ids):
    """G7-10: an INTERNAL message carries staff text, so G7-9 applies to it."""
    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    _refused(engine, lambda k: _message(
        client, thread, {"direction": "INTERNAL", "occurred_at": AT, "body_text": SECRET},
        ids.ACC_OPERATOR, k), 422, "CONTENT_NOT_ARCHIVABLE")
    _archive_consent(engine, party, thread)
    _ok(_message(client, thread, {"direction": "INTERNAL", "occurred_at": AT,
                                  "body_text": SECRET}, ids.ACC_OPERATOR))


def test_g7_11_the_content_never_reaches_the_audit_log_or_a_log(client, engine, ids, caplog):
    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    caplog.set_level(logging.DEBUG)
    _message(client, thread, {"direction": "OUTBOUND", "occurred_at": AT,
                              "body_text": SECRET}, ids.ACC_OPERATOR)      # refused
    _archive_consent(engine, party, thread)
    sent = _ok(_message(client, thread, {"direction": "OUTBOUND", "occurred_at": AT,
                                         "body_text": SECRET, "media_ref": "media://y"},
                        ids.ACC_OPERATOR))
    rows = _all(engine, """SELECT new_row::text AS new_row FROM turab.audit_log
                            WHERE entity_table = 'communication_messages'
                              AND entity_id = :m""", m=sent["message_id"])
    assert len(rows) == 1
    new_row = json.loads(rows[0]["new_row"])
    assert "body_text" not in new_row and "media_ref" not in new_row
    assert new_row["metadata"] == {"content_archived": True}
    assert SECRET not in caplog.text and "media://y" not in caplog.text


def _blocked_by(engine, pid):
    return [r["pid"] for r in _all(engine, """
        SELECT pid FROM pg_stat_activity
         WHERE pid <> :w AND wait_event_type = 'Lock'
           AND :w = ANY(pg_blocking_pids(pid))""", w=pid)]


def _wait_until_blocked(engine, pid, thread, seconds=10.0):
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


@pytest.mark.parametrize("ending", ["commit", "rollback"])
def test_g7_9_a_revocation_in_flight_is_waited_for_then_seen(client, engine, ids, ending):
    """G7-9 (3): the consent is read FOR SHARE. A revocation holding the grant
    makes the message wait (witness); committed, it is seen and the content is
    refused; rolled back, the content is archived."""
    from sqlalchemy.orm import Session

    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    grant = _archive_consent(engine, party, thread)
    holder = Session(bind=engine)
    out: dict = {}
    try:
        pid = holder.execute(text("SELECT pg_backend_pid()")).scalar_one()
        holder.execute(text("UPDATE turab.consent_grants SET status = 'REVOKED', "
                            "revoked_at = now() WHERE consent_id = :c"), {"c": grant})
        sender = _in_thread(engine, out, "message", lambda c: _message(
            c, thread, {"direction": "OUTBOUND", "occurred_at": AT, "body_text": SECRET},
            ids.ACC_OPERATOR))
        waited = _wait_until_blocked(engine, pid, sender)
        answered_while_held = not sender.is_alive()
        getattr(holder, ending)()
    finally:
        holder.close()
    sender.join(30)
    assert (waited, answered_while_held) == (True, False)
    if ending == "commit":
        assert (out["message"].status_code, out["message"].json()["code"]) == (
            422, "CONTENT_NOT_ARCHIVABLE")
        assert _one(engine, "SELECT count(*) FROM turab.communication_messages "
                            "WHERE thread_id = :t", t=thread) == 0
    else:
        assert out["message"].status_code == 201, out["message"].text
        assert _stored(engine, out["message"].json()["message_id"])["body_text"] == SECRET


# ======================================================================================
# The message: G7-16 (iv), the thread locked before the message is inserted
# ======================================================================================

def test_iv_last_message_at_moves_to_the_later_time_only(client, engine, ids):
    thread = _new_thread(client, ids, engine)
    assert _thread_row(engine, thread)["last_message_at"] is None
    for at, expected in (("2026-10-25T10:00:00Z", "2026-10-25T10:00:00+00:00"),
                         ("2026-10-25T12:00:00Z", "2026-10-25T12:00:00+00:00"),
                         ("2026-10-25T11:00:00Z", "2026-10-25T12:00:00+00:00")):
        _ok(_message(client, thread, {"direction": "INTERNAL", "occurred_at": at},
                     ids.ACC_OPERATOR))
        assert _thread_row(engine, thread)["last_message_at"].isoformat() == expected
    moves = _all(engine, """SELECT action FROM turab.audit_log
                             WHERE entity_table = 'communication_threads'
                               AND entity_id = :t ORDER BY occurred_at""", t=thread)
    assert [m["action"] for m in moves] == ["INSERT", "UPDATE", "UPDATE"], \
        "a message that moves nothing writes no thread audit row"


@pytest.mark.parametrize("first_at, second_at", [
    ("2026-10-25T12:00:00Z", "2026-10-25T10:00:00Z"),
    ("2026-10-25T10:00:00Z", "2026-10-25T12:00:00Z"),
], ids=["later_holds", "earlier_holds"])
def test_iv_two_concurrent_messages_serialize_on_the_thread_and_keep_the_later(
        client, engine, ids, monkeypatch, first_at, second_at):
    """The review of 0f423d2: the thread row is locked FOR UPDATE before the
    message is inserted. The first message is held after its lock and its
    insert's start; the second, in another transaction, waits on the first
    (witness: pg_blocking_pids names the first's backend), and does not answer
    while the first is held. Both commit; `last_message_at` is the later of the
    two times, whichever was held."""
    thread = _new_thread(client, ids, engine)
    out: dict = {}
    held, release = threading.Event(), threading.Event()
    real = _service().record_message

    def holding(session, prepared, **kw):
        if prepared.occurred_at.isoformat().startswith(first_at[:19]) and "pid" not in out:
            out["pid"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
            held.set()
            assert release.wait(30), "the first message was never released"
        return real(session, prepared, **kw)
    monkeypatch.setattr(_service(), "record_message", holding)

    first = _in_thread(engine, out, "first", lambda c: _message(
        c, thread, {"direction": "INTERNAL", "occurred_at": first_at}, ids.ACC_OPERATOR))
    second = None
    try:
        assert held.wait(30), "the first message never reached its insert"
        second = _in_thread(engine, out, "second", lambda c: _message(
            c, thread, {"direction": "INTERNAL", "occurred_at": second_at},
            ids.ACC_OPERATOR))
        waited = _wait_until_blocked(engine, out["pid"], second)
        answered_while_held = not second.is_alive()
    finally:
        release.set()
        first.join(30)
        if second is not None:
            second.join(30)
    assert (waited, answered_while_held) == (True, False)
    assert (out["first"].status_code, out["second"].status_code) == (201, 201)
    assert _thread_row(engine, thread)["last_message_at"].isoformat() == \
        "2026-10-25T12:00:00+00:00"
    assert _one(engine, "SELECT count(*) FROM turab.communication_messages "
                        "WHERE thread_id = :t", t=thread) == 2


def test_a_message_and_its_thread_move_are_audited_and_a_replay_writes_nothing(
        client, engine, ids):
    thread = _new_thread(client, ids, engine)
    key = str(uuid.uuid4())
    body = {"direction": "OUTBOUND", "occurred_at": AT, "delivery_status": "SENT"}
    first = _ok(_message(client, thread, body, ids.ACC_OPERATOR, key))
    audit = _all(engine, """SELECT action, actor_account_id FROM turab.audit_log
                             WHERE entity_table = 'communication_messages'
                               AND entity_id = :m""", m=first["message_id"])
    assert [(a["action"], a["actor_account_id"]) for a in audit] == [
        ("INSERT", ids.ACC_OPERATOR)]
    before = _footprint(engine, key)
    assert _ok(_message(client, thread, body, ids.ACC_OPERATOR, key)) == first
    assert _footprint(engine, key) == before


# ======================================================================================
# G7-16 (vi): no refusal carries a row id or database text
# ======================================================================================

def test_no_refusal_carries_an_id_or_database_text(client, engine, ids, monkeypatch):
    """Every typed refusal of both commands, its whole body read: no uuid,
    no reference, no constraint or table name, no SQL text."""
    world = _sale_world(client, engine, ids)
    ref, mref = _ref(), f"wamid.{uuid.uuid4().hex}"
    wa = _new_thread(client, ids, engine, channel="WHATSAPP", ref=ref)
    _ok(_message(client, wa, {"direction": "OUTBOUND", "occurred_at": AT,
                              "external_message_ref": mref}, ids.ACC_OPERATOR))
    phone = _new_thread(client, ids, engine)
    party = str(_party(engine))
    calls = [
        lambda: _thread(client, {"channel": "WHATSAPP", "party_id": party,
                                 "external_thread_ref": "nope"}, ids.ACC_OPERATOR),
        lambda: _thread(client, {"channel": "WHATSAPP", "party_id": party,
                                 "external_thread_ref": ref}, ids.ACC_OPERATOR),
        lambda: _thread(client, {"channel": "PHONE", "party_id": str(uuid.uuid4())},
                        ids.ACC_OPERATOR),
        lambda: _thread(client, {"channel": "PHONE", "party_id": party,
                                 "opportunity_id": str(world["opportunity"])},
                        ids.ACC_OPERATOR),
        lambda: _message(client, phone, {"direction": "INBOUND", "occurred_at": AT},
                         ids.ACC_OPERATOR),
        lambda: _message(client, phone, {"direction": "OUTBOUND", "occurred_at": AT,
                                         "external_message_ref": mref}, ids.ACC_OPERATOR),
        lambda: _message(client, wa, {"direction": "OUTBOUND", "occurred_at": AT,
                                      "external_message_ref": mref}, ids.ACC_OPERATOR),
        lambda: _message(client, phone, {"direction": "OUTBOUND", "occurred_at": AT,
                                         "body_text": SECRET}, ids.ACC_OPERATOR),
        lambda: _message(client, phone, {"direction": "INTERNAL", "occurred_at": AT,
                                         "metadata": {"k": SECRET}}, ids.ACC_OPERATOR),
    ]
    monkeypatch.setattr(_service(), "_refuse_taken_thread_ref",
                        lambda session, ref: None)
    calls.append(lambda: _thread(client, {"channel": "WHATSAPP", "party_id": party,
                                          "external_thread_ref": ref}, ids.ACC_OPERATOR))
    for call in calls:
        response = call()
        assert response.status_code in (409, 422), response.text
        body = response.text
        found = set(UUID.findall(body)) - {response.json()["trace_id"]}
        assert not found, body
        for leaked in (ref, mref, SECRET, "turab.", "constraint", "violates", "SELECT",
                       "INSERT", "ux_", "_key", "_fkey"):
            assert leaked not in body, (leaked, body)


# ======================================================================================
# R-S7-2-01 (review of f7e5297): a binding being created and a message, in both orders
# ======================================================================================
#
# `resource_consent_bindings.thread_id` has a foreign key to the thread
# (`fk_consent_binding_thread`, schema_v0.2.3.sql). Its INSERT checks it with
# FOR KEY SHARE on the thread row, which conflicts with the message's FOR UPDATE
# (PostgreSQL 16, §13.3.2, Table 13.3). The delivery of f7e5297 said there was no
# such key and that the message would not wait for a binding in flight; it was
# wrong. Measured here through the two real HTTP commands.

def _bind(client, consent_id, thread_id, account, key=None):
    return client.post("/consents/bindings", headers=_headers(account, key), json={
        "consent_id": str(consent_id), "purpose": "COMMUNICATION_ARCHIVE",
        "resource_type": "COMMUNICATION_THREAD", "resource_id": str(thread_id)})


def _grant_only(engine, party):
    return _one(engine, """
        INSERT INTO turab.consent_grants (party_id, scope, channel, consent_version, granted_at)
        VALUES (:p, 'COMMUNICATION_ARCHIVE', 'WHATSAPP', 'v1', now() - interval '1 day')
        RETURNING consent_id""", p=party)


def _facts(engine, thread_id, message_key, binding_key):
    return {
        "messages": _one(engine, "SELECT count(*) FROM turab.communication_messages "
                                 "WHERE thread_id = :t", t=thread_id),
        "archived_bodies": _one(engine, "SELECT count(*) FROM turab.communication_messages "
                                        "WHERE thread_id = :t AND body_text = :b",
                                t=thread_id, b=SECRET),
        "bindings": _one(engine, "SELECT count(*) FROM turab.resource_consent_bindings "
                                 "WHERE thread_id = :t", t=thread_id),
        "message_key": _one(engine, "SELECT count(*) FROM turab.idempotency_records "
                                    "WHERE idempotency_key = :k", k=message_key),
        "binding_key": _one(engine, "SELECT count(*) FROM turab.idempotency_records "
                                    "WHERE idempotency_key = :k", k=binding_key),
    }


def test_r_s7_2_01_a_message_holding_the_thread_makes_a_new_binding_wait(
        client, engine, ids, monkeypatch):
    """Order A. The message holds the thread (FOR UPDATE), stopped before its
    consent check. The binding command, in another transaction, WAITS on it
    (witness) and does not answer while it is held. Released, the message
    reads no binding (none is committed) and is refused 422, writing nothing
    and consuming no key; its transaction ends, and the binding then commits."""
    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    grant = _grant_only(engine, party)
    out: dict = {}
    held, release = threading.Event(), threading.Event()
    service = _service()
    real = service._archive_consent_holds

    def holding(session, **kw):
        out["pid"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        held.set()
        assert release.wait(30), "the message was never released"
        return real(session, **kw)
    monkeypatch.setattr(service, "_archive_consent_holds", holding)
    message_key, binding_key = str(uuid.uuid4()), str(uuid.uuid4())
    sender = _in_thread(engine, out, "message", lambda c: _message(
        c, thread, {"direction": "OUTBOUND", "occurred_at": AT, "body_text": SECRET},
        ids.ACC_OPERATOR, message_key))
    binder = None
    try:
        assert held.wait(30), "the message never reached its consent check"
        binder = _in_thread(engine, out, "binding", lambda c: _bind(
            c, grant, thread, ids.ACC_OPERATOR, binding_key))
        waited = _wait_until_blocked(engine, out["pid"], binder)
        bound_while_held = not binder.is_alive()
    finally:
        release.set()
        sender.join(30)
        if binder is not None:
            binder.join(30)
    observed = {
        "binding_waited_on_the_message": waited,
        "binding_answered_while_the_message_held_the_thread": bound_while_held,
        "message": (out["message"].status_code, out["message"].json().get("code")),
        "binding": out["binding"].status_code,
        **_facts(engine, thread, message_key, binding_key),
    }
    assert observed == {
        "binding_waited_on_the_message": True,
        "binding_answered_while_the_message_held_the_thread": False,
        "message": (422, "CONTENT_NOT_ARCHIVABLE"), "binding": 200,
        "messages": 0, "archived_bodies": 0, "bindings": 1,
        "message_key": 0, "binding_key": 1,
    }, observed


@pytest.mark.parametrize("ending", ["commit", "rollback"])
def test_r_s7_2_01_a_binding_in_flight_makes_the_message_wait_then_is_seen(
        client, engine, ids, monkeypatch, ending):
    """Order B. The binding command has inserted its binding and is stopped
    before its commit. The message, in another transaction, WAITS on it at the
    thread's FOR UPDATE (witness) and does not answer while it is held.
    - committed: the message's consent check, a later statement under READ
      COMMITTED, sees the binding, and the content is archived (201);
    - rolled back (the binding command refused after its insert): the message
      sees no binding and is refused 422, writing nothing and consuming no key."""
    from turab.services import consent as consent_service

    party = _party(engine)
    thread = _new_thread(client, ids, engine, party=party)
    grant = _grant_only(engine, party)
    out: dict = {}
    held, release = threading.Event(), threading.Event()
    real = consent_service.bind_consent

    def holding(session, **kw):
        row = real(session, **kw)
        out["pid"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        held.set()
        assert release.wait(30), "the binding was never released"
        if ending == "rollback":
            raise consent_service.ConsentError("VALIDATION_FAILED", "refused after its insert")
        return row
    monkeypatch.setattr(consent_service, "bind_consent", holding)
    message_key, binding_key = str(uuid.uuid4()), str(uuid.uuid4())
    binder = _in_thread(engine, out, "binding", lambda c: _bind(
        c, grant, thread, ids.ACC_OPERATOR, binding_key))
    sender = None
    try:
        assert held.wait(30), "the binding was never inserted"
        sender = _in_thread(engine, out, "message", lambda c: _message(
            c, thread, {"direction": "OUTBOUND", "occurred_at": AT, "body_text": SECRET},
            ids.ACC_OPERATOR, message_key))
        waited = _wait_until_blocked(engine, out["pid"], sender)
        answered_while_held = not sender.is_alive()
    finally:
        release.set()
        binder.join(30)
        if sender is not None:
            sender.join(30)
    observed = {
        "message_waited_on_the_binding": waited,
        "message_answered_while_the_binding_was_held": answered_while_held,
        "binding": out["binding"].status_code,
        "message": (out["message"].status_code, out["message"].json().get("code")),
        **_facts(engine, thread, message_key, binding_key),
    }
    committed = ending == "commit"
    assert observed == {
        "message_waited_on_the_binding": True,
        "message_answered_while_the_binding_was_held": False,
        "binding": 200 if committed else 422,
        "message": (201, None) if committed else (422, "CONTENT_NOT_ARCHIVABLE"),
        "messages": 1 if committed else 0,
        "archived_bodies": 1 if committed else 0,
        "bindings": 1 if committed else 0,
        "message_key": 1 if committed else 0,
        "binding_key": 1 if committed else 0,
    }, observed
