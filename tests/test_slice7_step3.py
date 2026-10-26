"""Slice 7 step 3: `postWebhooksWhatsapp`, the event store, its processing, the recovery.

Ref: `docs/gate/SLICE_7_PLAN.md`: G7-2 (the boundary, T1 and T2, the replay
table, the recovery, the four failure tests of (iv)), G7-3, G7-4, G7-5, G7-9,
G7-15, G7-16 (iv), G7-17 (decided in the review of bf1fe3d); §6.1 mandatory
tests 1 and 2; §6.2 J01, J02, J03, S41, S42; CORRECTION-007 and
CORRECTION-008 (their own tests: `tests/test_correction_007_008.py`);
`services/webhooks.py`, `api/routes/webhooks.py`,
`db/ops/recover_webhook_events.py`.

**What the review of bf1fe3d asked to see tested in step 3:** a 503 when the
secret is absent, with no event row
(`test_ii_a_missing_or_empty_secret_is_503_with_no_event_row`).

**What these tests prove, and what they do not.** The relay's signature
proves that the envelope comes, unchanged, from the holder of the relay's key
(S41). It does NOT prove Meta's signature: the relay checks that, and R-1 is
UNMET. No test here receives a real event.

**Isolation.** HTTP tests commit to the shared test database. Each test
builds its own threads and its own `provider_event_id`s. Migration 0008
refuses a DELETE of an event, a thread or a message, so nothing written here
is removed.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import threading
import uuid

import pytest
from fastapi.testclient import TestClient

from tests.test_slice4_step7 import _all, _exec, _one
from tests.test_slice7_step2 import _archive_consent, _message, _new_thread, _ok, _party, _ref
from turab.auth.audit import AccessAuditor, AccessEvent, RecordingAuditSink

KEY = "relay-test-key-5d1c"
SECRET = "SECRET-BODY-a91f"
MEDIA = "media://SECRET-MEDIA-a91f"
AT = "2026-10-25T10:00:00Z"
LATER = "2026-10-25T11:00:00+01:00"   # 10:00Z: the same instant as AT
URL = "/webhooks/whatsapp"


def _svc():
    """Imported where used, so that this file is collected on a tree without
    step 3's code and each test there fails on its own (the before record)."""
    from turab.services import webhooks

    return webhooks


@pytest.fixture(autouse=True)
def _secret(monkeypatch):
    monkeypatch.setenv("TURAB_RELAY_SIGNING_SECRET", KEY)


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

def _sign(raw: bytes, key: str = KEY) -> str:
    return "sha256=" + hmac.new(key.encode("utf-8"), raw, hashlib.sha256).hexdigest()


def _raw(envelope) -> bytes:
    return json.dumps(envelope).encode("utf-8")


def _post(client, envelope=None, *, raw=None, signature=None, sign=True, headers=None):
    raw = _raw(envelope) if raw is None else raw
    h = {"Content-Type": "application/json", **(headers or {})}
    if sign:
        h["X-Turab-Relay-Signature"] = signature if signature is not None else _sign(raw)
    return client.post(URL, content=raw, headers=h)


def _eid():
    return f"evt.{uuid.uuid4().hex}"


def _mref():
    return f"wamid.{uuid.uuid4().hex}"


def _msg(thread_ref, *, event_id=None, ref=None, at=AT, body=None, media=None, **extra):
    payload = {"external_message_ref": ref or _mref(), "thread_ref": thread_ref,
               "occurred_at": at, "message_type": "TEXT", **extra}
    if body is not None:
        payload["body_text"] = body
    if media is not None:
        payload["media_ref"] = media
    return {"provider_event_id": event_id or _eid(), "event_type": "message",
            "payload": payload}


def _status(ref, status, *, event_id=None, at=AT):
    return {"provider_event_id": event_id or _eid(), "event_type": "status",
            "payload": {"external_message_ref": ref, "status": status, "occurred_at": at}}


def _whatsapp(client, ids, engine, *, party=None):
    """A WHATSAPP thread and its reference."""
    ref = _ref()
    return _new_thread(client, ids, engine, channel="WHATSAPP", party=party, ref=ref), ref


def _event(engine, provider_event_id):
    rows = _all(engine, """
        SELECT webhook_event_id, provider, event_type, payload,
               processing_status::text AS status, processed_at, error_text
          FROM turab.webhook_events
         WHERE provider = 'whatsapp' AND provider_event_id = :e""", e=provider_event_id)
    assert len(rows) <= 1
    return rows[0] if rows else None


def _messages(engine, ref):
    return _all(engine, """
        SELECT message_id, thread_id, provider, direction::text AS direction, message_type,
               body_text, media_ref, delivery_status::text AS delivery_status,
               sent_by_account_id, occurred_at, metadata
          FROM turab.communication_messages
         WHERE provider = 'whatsapp' AND external_message_ref = :r""", r=ref)


def _audit(engine, table, entity_id):
    return _all(engine, """
        SELECT action, actor_account_id, context, old_row::text AS old_row,
               new_row::text AS new_row
          FROM turab.audit_log WHERE entity_table = :t AND entity_id = :e
         ORDER BY audit_id""", t=table, e=entity_id)


def _counts(engine):
    return {
        "events": _one(engine, "SELECT count(*) FROM turab.webhook_events"),
        "messages": _one(engine, "SELECT count(*) FROM turab.communication_messages"),
        "threads": _one(engine, "SELECT count(*) FROM turab.communication_threads"),
        "audit": _one(engine, "SELECT count(*) FROM turab.audit_log"),
    }


def _refused(client, engine, sink, status, code, outcome, **post):
    """A refusal before T1: the status, its code, nothing written, and one
    access record naming the outcome."""
    before = _counts(engine)
    sink.clear()
    r = _post(client, **post)
    assert (r.status_code, r.json()["code"]) == (status, code), r.text
    assert r.headers["content-type"].startswith("application/problem+json")
    assert _counts(engine) == before, "a refusal before T1 writes nothing"
    [record] = sink.records
    assert (record.event, record.reason_code, record.extra["http_status"],
            record.resource_id, record.decision) == (
        AccessEvent.WEBHOOK_ANSWERED, outcome, status, None, "DENY")
    return r


def _accepted(r):
    assert r.status_code == 200, r.text
    assert r.content == b"", "G7-17 (v): the 200 has no body"


# --- G7-17 (ii): the secret, and the signature (S41) -------------------------------------

@pytest.mark.parametrize("value", [None, ""])
def test_ii_a_missing_or_empty_secret_is_503_with_no_event_row(client, engine, ids, sink,
                                                               monkeypatch, caplog, value):
    """The test the review of bf1fe3d asked for. A correctly signed, valid
    envelope, with the secret absent or empty: 503 WEBHOOK_NOT_READY, no
    event row, nothing written, the fault logged without the body."""
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref, body=SECRET)
    raw = _raw(envelope)
    if value is None:
        monkeypatch.delenv("TURAB_RELAY_SIGNING_SECRET")
    else:
        monkeypatch.setenv("TURAB_RELAY_SIGNING_SECRET", value)
    caplog.set_level(logging.DEBUG)
    _refused(client, engine, sink, 503, "WEBHOOK_NOT_READY", "SECRET_NOT_CONFIGURED",
             raw=raw, signature=_sign(raw))
    assert _event(engine, envelope["provider_event_id"]) is None
    assert any("signing secret not configured" in r.getMessage() for r in caplog.records)
    _no_secret_in_logs(caplog, raw)


def test_ii_the_503_comes_after_the_size_and_before_the_signature(client, engine, sink,
                                                                  monkeypatch):
    monkeypatch.delenv("TURAB_RELAY_SIGNING_SECRET")
    big = b"{" + b" " * (64 * 1024) + b"}"
    _refused(client, engine, sink, 400, "WEBHOOK_BODY_TOO_LARGE", "BODY_TOO_LARGE",
             raw=big, signature="sha256=" + "0" * 64)
    _refused(client, engine, sink, 503, "WEBHOOK_NOT_READY", "SECRET_NOT_CONFIGURED",
             raw=b"{}", sign=False)


@pytest.mark.parametrize("label, signature", [
    ("missing", None),
    ("empty", ""),
    ("bare hex", "HEX"),
    ("upper-case hex", "UPPER"),
    ("another algorithm", "sha1=HEX"),
    ("too short", "SHORT"),
    ("under another key", "OTHER_KEY"),
    ("of another body", "OTHER_BODY"),
    ("with a space", " SIGNED"),
])
def test_ii_s41_a_missing_or_wrong_signature_is_401_writing_nothing(client, engine, ids,
                                                                     sink, label, signature):
    """S41: refused before any write. The check proves the relay's origin,
    not Meta's."""
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    raw = _raw(envelope)
    good = _sign(raw)
    value = {None: None, "": "", "HEX": good.removeprefix("sha256="),
             "UPPER": "sha256=" + good.removeprefix("sha256=").upper(),
             "sha1=HEX": "sha1=" + good.removeprefix("sha256="), "SHORT": good[:-1],
             "OTHER_KEY": _sign(raw, "another-key"), "OTHER_BODY": _sign(raw + b" "),
             " SIGNED": " " + good}[signature]
    _refused(client, engine, sink, 401, "UNAUTHENTICATED", "SIGNATURE_NOT_VALID",
             raw=raw, signature=value, sign=signature is not None)
    assert _event(engine, envelope["provider_event_id"]) is None


def test_ii_the_signature_is_over_the_raw_bytes(client, engine, ids):
    """The same JSON with other whitespace is another body: its signature is
    its own, and the envelope's is refused for it."""
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    compact = json.dumps(envelope, separators=(",", ":")).encode()
    spaced = json.dumps(envelope, indent=2).encode()
    for other in (compact, _raw(envelope)):
        assert _post(client, raw=spaced, signature=_sign(other)).status_code == 401
    _accepted(_post(client, raw=spaced))


def test_ii_the_secret_is_read_as_utf_8(client, engine, ids, monkeypatch):
    monkeypatch.setenv("TURAB_RELAY_SIGNING_SECRET", "مفتاح-relay")
    _, thread_ref = _whatsapp(client, ids, engine)
    raw = _raw(_msg(thread_ref))
    _accepted(_post(client, raw=raw, signature=_sign(raw, "مفتاح-relay")))


def test_ii_the_signature_is_compared_in_constant_time(monkeypatch):
    """`hmac.compare_digest`, not `==`: observed by replacing it."""
    webhooks = _svc()
    seen = []
    monkeypatch.setattr(webhooks.hmac, "compare_digest",
                        lambda a, b: seen.append((a, b)) or a == b)
    raw = b'{"x":1}'
    assert webhooks.verify(raw, _sign(raw), KEY.encode()) is True
    assert webhooks.verify(raw, _sign(raw, "k2"), KEY.encode()) is False
    assert len(seen) == 2


# --- G7-15 and G7-17 (iii): the size, the envelope, a known type's keys ---------------------

def test_g7_15_a_body_over_64_kib_is_400_and_one_of_64_kib_is_read(client, engine, ids, sink):
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    base = len(_raw({**envelope, "pad": ""}))
    exact = _raw({**envelope, "pad": "x" * (64 * 1024 - base)})
    assert len(exact) == 64 * 1024
    _accepted(_post(client, raw=exact))
    over = _raw({**_msg(thread_ref), "pad": "x" * (64 * 1024 - base + 1)})
    assert len(over) == 64 * 1024 + 1
    _refused(client, engine, sink, 400, "WEBHOOK_BODY_TOO_LARGE", "BODY_TOO_LARGE", raw=over)


def test_g7_15_the_limit_holds_without_a_content_length(client, engine, sink):
    """A chunked body carries no `Content-Length`: the count while reading
    refuses it."""
    before = _counts(engine)
    sink.clear()
    chunks = [b"{" + b" " * 4096] * 17 + [b"}"]
    r = client.post(URL, content=iter(chunks),
                    headers={"Content-Type": "application/json",
                             "X-Turab-Relay-Signature": "sha256=" + "0" * 64})
    assert (r.status_code, r.json()["code"]) == (400, "WEBHOOK_BODY_TOO_LARGE")
    assert _counts(engine) == before
    assert [x.reason_code for x in sink.records] == ["BODY_TOO_LARGE"]


def test_g7_15_a_false_content_length_does_not_pass_the_limit(monkeypatch):
    """`Content-Length` is a first check, not the only one: a body longer than
    the length it declares is still counted while it is read."""
    import asyncio

    from turab.api.routes import webhooks as route

    class Request:
        headers = {"content-length": "10"}

        async def stream(self):
            for _ in range(17):
                yield b" " * 4096

    assert asyncio.run(route._read_limited(Request())) is None


def test_g7_15_a_declared_length_over_the_limit_is_refused_before_reading():
    """`Content-Length` over 64 KiB is refused without reading the body."""
    import asyncio

    from turab.api.routes import webhooks as route

    class Request:
        headers = {"content-length": str(64 * 1024 + 1)}

        async def stream(self):
            raise AssertionError("the body is read")
            yield b""

    assert asyncio.run(route._read_limited(Request())) is None


def test_iii_the_order_size_signature_envelope(client, engine, sink):
    """An oversized body with a wrong signature is 400 (size first); a body
    that is not JSON with a wrong signature is 401 (the signature before the
    envelope)."""
    _refused(client, engine, sink, 400, "WEBHOOK_BODY_TOO_LARGE", "BODY_TOO_LARGE",
             raw=b"x" * (64 * 1024 + 1), signature="sha256=" + "0" * 64)
    _refused(client, engine, sink, 401, "UNAUTHENTICATED", "SIGNATURE_NOT_VALID",
             raw=b"not json", signature="sha256=" + "0" * 64)
    _refused(client, engine, sink, 400, "WEBHOOK_ENVELOPE_NOT_VALID", "ENVELOPE_NOT_VALID",
             raw=b"not json")


@pytest.mark.parametrize("label, raw", [
    ("not JSON", b"{"),
    ("not UTF-8", b'{"provider_event_id": "\xff"}'),
    ("an array", b"[]"),
    ("a string", b'"x"'),
    ("no provider_event_id", b'{"event_type": "message", "payload": {}}'),
    ("an empty provider_event_id",
     b'{"provider_event_id": "", "event_type": "x", "payload": {}}'),
    ("a numeric provider_event_id",
     b'{"provider_event_id": 7, "event_type": "x", "payload": {}}'),
    ("no event_type", b'{"provider_event_id": "e", "payload": {}}'),
    ("a null event_type", b'{"provider_event_id": "e", "event_type": null, "payload": {}}'),
    ("no payload", b'{"provider_event_id": "e", "event_type": "x"}'),
    ("a list payload", b'{"provider_event_id": "e", "event_type": "x", "payload": []}'),
])
def test_iii_an_invalid_envelope_is_400_writing_nothing(client, engine, sink, label, raw):
    _refused(client, engine, sink, 400, "WEBHOOK_ENVELOPE_NOT_VALID", "ENVELOPE_NOT_VALID",
             raw=raw)


MESSAGE_KEYS = ("external_message_ref", "thread_ref", "occurred_at", "message_type")
STATUS_KEYS = ("external_message_ref", "status", "occurred_at")


@pytest.mark.parametrize("event_type, key, value", [
    *[("message", k, None) for k in MESSAGE_KEYS],
    *[("message", k, 7) for k in MESSAGE_KEYS],
    *[("status", k, None) for k in STATUS_KEYS],
    *[("status", k, ["x"]) for k in STATUS_KEYS],
    ("message", "occurred_at", "2026-10-25T10:00:00"),
    ("message", "occurred_at", "2026-10-25 10:00:00Z"),
    ("message", "occurred_at", "2026-10-25T10:00Z"),
    ("message", "occurred_at", "2026-10-25"),
    ("message", "occurred_at", "20261025T100000Z"),
    ("message", "occurred_at", "2026-13-25T10:00:00Z"),
    ("message", "occurred_at", "yesterday"),
    ("status", "occurred_at", "2026-10-25T10:00:00"),
    ("status", "status", "BOUNCED"),
    ("status", "status", "read"),
    ("message", "body_text", 7),
    ("message", "media_ref", {"u": 1}),
])
def test_iii_a_known_type_with_a_missing_or_mistyped_key_is_400(client, engine, ids, sink,
                                                                event_type, key, value):
    """G7-17 (iii) step 4. The relay, which formed the envelope, sees its
    fault; nothing is stored."""
    if event_type == "message":
        envelope = _msg("a:b")
    else:
        envelope = _status(_mref(), "SENT")
    if value is None:
        envelope["payload"].pop(key)
    else:
        envelope["payload"][key] = value
    r = _refused(client, engine, sink, 400, "WEBHOOK_ENVELOPE_NOT_VALID",
                 "ENVELOPE_NOT_VALID", envelope=envelope)
    assert key in r.json()["detail"]
    assert _event(engine, envelope["provider_event_id"]) is None


@pytest.mark.parametrize("at", ["2026-10-25T10:00:00Z", "2026-10-25t10:00:00z",
                                "2026-10-25T10:00:00.123456+01:00",
                                "2026-10-25T10:00:00-00:00"])
def test_iii_an_rfc_3339_instant_with_a_zone_is_accepted(client, engine, ids, at):
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref, at=at)
    _accepted(_post(client, envelope))
    assert _event(engine, envelope["provider_event_id"])["status"] == "PROCESSED"


def test_iii_an_unknown_type_is_stored_then_ignored(client, engine, sink):
    envelope = {"provider_event_id": _eid(), "event_type": "reaction",
                "payload": {"anything": SECRET}}
    sink.clear()
    _accepted(_post(client, envelope))
    event = _event(engine, envelope["provider_event_id"])
    assert (event["event_type"], event["status"], event["error_text"]) == (
        "reaction", "IGNORED", "UNKNOWN_EVENT_TYPE")
    assert event["processed_at"] is not None
    assert event["payload"] == {"provider_event_id": envelope["provider_event_id"],
                                "event_type": "reaction", "has_body": False,
                                "has_media": False}
    [record] = sink.records
    assert (record.reason_code, record.resource_id, record.extra["http_status"]) == (
        "IGNORED", event["webhook_event_id"], 200)


# --- G7-9: the content-free event, and the content under consent (J03) ------------------

def test_g7_9_1_the_event_store_holds_the_allow_list_only(client, engine, ids):
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref, body=SECRET, media=MEDIA, extra_key=SECRET,
                    contact={"wa_id": SECRET})
    envelope["relay_note"] = SECRET
    _accepted(_post(client, envelope))
    event = _event(engine, envelope["provider_event_id"])
    p = envelope["payload"]
    assert event["payload"] == {
        "provider_event_id": envelope["provider_event_id"], "event_type": "message",
        "external_message_ref": p["external_message_ref"], "thread_ref": thread_ref,
        "occurred_at": AT, "message_type": "TEXT", "has_body": True, "has_media": True}
    assert SECRET not in json.dumps(event["payload"]) and MEDIA not in json.dumps(
        event["payload"])
    status = _status(p["external_message_ref"], "SENT")
    _accepted(_post(client, status))
    assert _event(engine, status["provider_event_id"])["payload"] == {
        "provider_event_id": status["provider_event_id"], "event_type": "status",
        "external_message_ref": p["external_message_ref"], "status": "SENT",
        "occurred_at": AT, "has_body": False, "has_media": False}


def test_g7_9_a_message_without_the_archive_consent_is_stored_without_content(
        client, engine, ids):
    thread, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref, body=SECRET, media=MEDIA)
    _accepted(_post(client, envelope))
    [m] = _messages(engine, envelope["payload"]["external_message_ref"])
    event = _event(engine, envelope["provider_event_id"])
    assert (m["thread_id"], m["direction"], m["body_text"], m["media_ref"]) == (
        thread, "INBOUND", None, None)
    assert m["metadata"] == {"content_archived": False,
                             "content_withheld_reason": "NO_ARCHIVE_CONSENT",
                             "webhook_event_id": str(event["webhook_event_id"])}


def test_g7_9_with_the_archive_consent_the_content_is_archived(client, engine, ids):
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    envelope = _msg(thread_ref, body=SECRET, media=MEDIA)
    _accepted(_post(client, envelope))
    [m] = _messages(engine, envelope["payload"]["external_message_ref"])
    assert (m["body_text"], m["media_ref"]) == (SECRET, MEDIA)
    assert m["metadata"] == {
        "content_archived": True,
        "webhook_event_id": str(_event(engine, envelope["provider_event_id"])[
            "webhook_event_id"])}


@pytest.mark.parametrize("case", ["revoked", "bound_to_another_thread", "binding_revoked"])
def test_g7_9_a_webhook_content_under_a_consent_that_does_not_hold_is_withheld(
        client, engine, ids, case):
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    other, _ = _whatsapp(client, ids, engine, party=party)
    if case == "revoked":
        grant = _archive_consent(engine, party, thread)
        _exec(engine, "UPDATE turab.consent_grants SET status = 'REVOKED', "
                      "revoked_at = now() WHERE consent_id = :c", c=grant)
    elif case == "bound_to_another_thread":
        _archive_consent(engine, party, other)
    else:
        grant = _archive_consent(engine, party, thread)
        _exec(engine, "UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                      "WHERE consent_id = :c", c=grant)
    envelope = _msg(thread_ref, body=SECRET)
    _accepted(_post(client, envelope))
    [m] = _messages(engine, envelope["payload"]["external_message_ref"])
    assert (m["body_text"], m["metadata"]["content_withheld_reason"]) == (
        None, "NO_ARCHIVE_CONSENT")


def test_a_message_without_content_carries_no_withheld_reason(client, engine, ids):
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    _accepted(_post(client, envelope))
    [m] = _messages(engine, envelope["payload"]["external_message_ref"])
    assert set(m["metadata"]) == {"content_archived", "webhook_event_id"}


# --- G7-3, G7-4: the message's resolution ------------------------------------------------

def test_g7_3_a_message_is_an_inbound_message_of_its_whatsapp_thread(client, engine, ids,
                                                                     sink):
    thread, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    envelope["payload"]["message_type"] = "CONFIRMATION_LINK"
    sink.clear()
    _accepted(_post(client, envelope))
    event = _event(engine, envelope["provider_event_id"])
    assert (event["status"], event["error_text"]) == ("PROCESSED", None)
    assert event["processed_at"] is not None
    [m] = _messages(engine, envelope["payload"]["external_message_ref"])
    assert (m["thread_id"], m["provider"], m["direction"], m["message_type"],
            m["delivery_status"], m["sent_by_account_id"]) == (
        thread, "whatsapp", "INBOUND", "CONFIRMATION_LINK", "UNKNOWN", None)
    assert m["occurred_at"].isoformat() == "2026-10-25T10:00:00+00:00"
    [record] = sink.records
    assert (record.reason_code, record.resource_id, record.decision) == (
        "PROCESSED", event["webhook_event_id"], "ALLOW")


def test_g7_3_a_thread_ref_of_no_whatsapp_thread_is_ignored(client, engine, ids):
    """`UNKNOWN_THREAD`: no thread holds it, or only a thread of another
    channel does."""
    ref = _ref()
    _new_thread(client, ids, engine, channel="PHONE", ref=ref)
    for thread_ref in (ref, _ref()):
        before = _counts(engine)
        envelope = _msg(thread_ref, body=SECRET)
        _accepted(_post(client, envelope))
        event = _event(engine, envelope["provider_event_id"])
        assert (event["status"], event["error_text"]) == ("IGNORED", "UNKNOWN_THREAD")
        assert _counts(engine) == {**before, "events": before["events"] + 1}


def test_g7_4_mandatory_test_2_a_recorded_reference_is_ignored_in_any_thread(
        client, engine, ids):
    """Mandatory test 2, J02, by webhook: the same `(whatsapp, ref)`, recorded
    by staff in one thread, is IGNORED `MESSAGE_REF_TAKEN` in it and in a
    second thread, with no row; by webhook first, likewise."""
    first, first_ref = _whatsapp(client, ids, engine)
    _, second_ref = _whatsapp(client, ids, engine)
    staff_ref = _mref()
    _ok(_message(client, first, {"direction": "OUTBOUND", "occurred_at": AT,
                                 "external_message_ref": staff_ref}, ids.ACC_OPERATOR))
    hook_ref = _mref()
    _accepted(_post(client, _msg(first_ref, ref=hook_ref)))
    for ref in (staff_ref, hook_ref):
        for thread_ref in (first_ref, second_ref):
            before = _counts(engine)
            envelope = _msg(thread_ref, ref=ref, body=SECRET)
            _accepted(_post(client, envelope))
            event = _event(engine, envelope["provider_event_id"])
            assert (event["status"], event["error_text"]) == ("IGNORED", "MESSAGE_REF_TAKEN")
            assert _counts(engine) == {**before, "events": before["events"] + 1}
        assert len(_messages(engine, ref)) == 1


def test_g7_4_a_reference_recorded_after_the_check_is_the_same_ignored(client, engine, ids,
                                                                     monkeypatch):
    """The backstop: the reference is recorded between the check and the
    insert. The 23505 on the reference's key is `MESSAGE_REF_TAKEN`, not a
    failure."""
    from sqlalchemy import text

    webhooks = _svc()
    first, _ = _whatsapp(client, ids, engine)
    _, thread_ref = _whatsapp(client, ids, engine)
    ref = _mref()
    real = webhooks._archive_consent_holds

    def racing(session, **kw):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO turab.communication_messages
                       (thread_id, provider, external_message_ref, direction, occurred_at)
                VALUES (:t, 'whatsapp', :r, 'OUTBOUND', now())"""), {"t": first, "r": ref})
        return real(session, **kw)

    monkeypatch.setattr(webhooks, "_archive_consent_holds", racing)
    envelope = _msg(thread_ref, ref=ref, body=SECRET)
    _accepted(_post(client, envelope))
    event = _event(engine, envelope["provider_event_id"])
    assert (event["status"], event["error_text"]) == ("IGNORED", "MESSAGE_REF_TAKEN")
    assert [m["thread_id"] for m in _messages(engine, ref)] == [first]


def test_g7_16_iv_the_thread_moves_to_the_later_time_only(client, engine, ids):
    thread, thread_ref = _whatsapp(client, ids, engine)
    row = lambda: _one(engine, "SELECT last_message_at FROM turab.communication_threads "
                               "WHERE thread_id = :t", t=thread)
    _accepted(_post(client, _msg(thread_ref, at="2026-10-25T12:00:00Z")))
    later = row()
    _accepted(_post(client, _msg(thread_ref, at="2026-10-25T09:00:00Z")))
    assert row() == later
    _accepted(_post(client, _msg(thread_ref, at="2026-10-25T13:00:00Z")))
    assert row().isoformat() == "2026-10-25T13:00:00+00:00"


def test_g7_16_iv_the_thread_is_locked_before_the_message_is_inserted(client, engine, ids):
    """A session holding the thread FOR UPDATE makes the webhook wait before
    its insert (witness: `pg_blocking_pids`); released, the message is
    written."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from tests.test_slice7_step2 import _wait_until_blocked

    thread, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    holder = Session(bind=engine)
    try:
        holder.execute(text("SELECT 1 FROM turab.communication_threads WHERE thread_id = :t "
                            "FOR UPDATE"), {"t": thread})
        pid = holder.execute(text("SELECT pg_backend_pid()")).scalar_one()
        out: dict = {}
        t = threading.Thread(target=lambda: out.setdefault("r", _post(client, envelope)))
        t.start()
        assert _wait_until_blocked(engine, pid, t), "the webhook waits for the thread"
        assert _messages(engine, envelope["payload"]["external_message_ref"]) == []
    finally:
        holder.rollback()
        holder.close()
    t.join(10)
    _accepted(out["r"])
    assert len(_messages(engine, envelope["payload"]["external_message_ref"])) == 1


def test_g7_16_iv_a_webhook_holding_the_thread_makes_a_new_binding_wait(client, engine,
                                                                       ids, monkeypatch):
    """R-S7-2-01 by webhook. Held at the consent check, after the thread's
    FOR UPDATE and before the insert, the webhook makes a new binding of the
    thread wait (fk_consent_binding_thread's FOR KEY SHARE; witness:
    `pg_blocking_pids`). The message then stores no content; the binding
    commits after it."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from tests.test_slice7_step2 import _grant_only, _wait_until_blocked

    webhooks = _svc()
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    grant = _grant_only(engine, party)
    envelope = _msg(thread_ref, body=SECRET)
    real = webhooks._archive_consent_holds
    held, release = threading.Event(), threading.Event()
    pid: dict = {}

    def holding(session, **kw):
        pid["webhook"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        held.set()
        assert release.wait(20)
        return real(session, **kw)

    monkeypatch.setattr(webhooks, "_archive_consent_holds", holding)
    out: dict = {}
    t = threading.Thread(target=lambda: out.setdefault("r", _post(client, envelope)))
    t.start()
    binder = Session(bind=engine)
    bound: dict = {}

    def bind():
        binder.execute(text("""
            INSERT INTO turab.resource_consent_bindings (consent_id, purpose, thread_id,
                                                         bound_at)
            VALUES (:c, 'COMMUNICATION_ARCHIVE', :t, now())"""), {"c": grant, "t": thread})
        binder.commit()
        bound["done"] = True

    b = threading.Thread(target=bind)
    try:
        assert held.wait(20)
        b.start()
        assert _wait_until_blocked(engine, pid["webhook"], b), "the binding waits"
        assert "done" not in bound
    finally:
        release.set()
        t.join(20)
        b.join(20)
        binder.close()
    _accepted(out["r"])
    assert bound == {"done": True}
    [m] = _messages(engine, envelope["payload"]["external_message_ref"])
    assert (m["body_text"], m["metadata"]["content_withheld_reason"]) == (
        None, "NO_ARCHIVE_CONSENT")


# --- G7-11 and G7-17 (vii): the audit, with a NULL actor --------------------------------

def test_vii_the_message_and_the_thread_move_are_audited_with_a_null_actor(client, engine,
                                                                          ids):
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    envelope = _msg(thread_ref, body=SECRET, media=MEDIA)
    _accepted(_post(client, envelope))
    [m] = _messages(engine, envelope["payload"]["external_message_ref"])
    [inserted] = _audit(engine, "communication_messages", m["message_id"])
    assert (inserted["action"], inserted["actor_account_id"], inserted["old_row"]) == (
        "INSERT", None, None)
    assert inserted["context"]["operation"] == "postWebhooksWhatsapp"
    new_row = json.loads(inserted["new_row"])
    assert "body_text" not in new_row and "media_ref" not in new_row
    assert SECRET not in inserted["new_row"] and MEDIA not in inserted["new_row"]
    moves = [a for a in _audit(engine, "communication_threads", thread)
             if a["action"] == "UPDATE"]
    assert len(moves) == 1 and moves[0]["actor_account_id"] is None
    assert json.loads(moves[0]["new_row"])["last_message_at"].startswith("2026-10-25T10:00")
    event = _event(engine, envelope["provider_event_id"])
    assert _audit(engine, "webhook_events", event["webhook_event_id"]) == [], \
        "the event is its own record; it is not audited twice"


def test_vii_a_thread_not_moved_is_not_audited(client, engine, ids):
    thread, thread_ref = _whatsapp(client, ids, engine)
    _accepted(_post(client, _msg(thread_ref, at="2026-10-25T12:00:00Z")))
    _accepted(_post(client, _msg(thread_ref, at="2026-10-25T09:00:00Z")))
    assert len([a for a in _audit(engine, "communication_threads", thread)
                if a["action"] == "UPDATE"]) == 1


# --- G7-5: the delivery status -------------------------------------------------------------

def _outbound(client, engine, ids, status):
    """A staff OUTBOUND message in a WHATSAPP thread, at `status`."""
    thread, _ = _whatsapp(client, ids, engine)
    ref = _mref()
    body = {"direction": "OUTBOUND", "occurred_at": AT, "external_message_ref": ref}
    if status != "UNKNOWN":
        body["delivery_status"] = status
    sent = _ok(_message(client, thread, body, ids.ACC_OPERATOR))
    return uuid.UUID(sent["message_id"]), ref


ACCEPTED = [("UNKNOWN", "QUEUED"), ("UNKNOWN", "SENT"), ("UNKNOWN", "DELIVERED"),
            ("UNKNOWN", "READ"), ("QUEUED", "SENT"), ("QUEUED", "READ"),
            ("SENT", "DELIVERED"), ("DELIVERED", "READ"), ("QUEUED", "FAILED"),
            ("SENT", "FAILED")]
REFUSED = [("UNKNOWN", "FAILED"), ("UNKNOWN", "UNKNOWN"), ("QUEUED", "QUEUED"),
           ("SENT", "QUEUED"), ("READ", "SENT"), ("READ", "READ"), ("DELIVERED", "SENT"),
           ("DELIVERED", "FAILED"), ("READ", "FAILED"), ("FAILED", "READ"),
           ("FAILED", "FAILED"), ("SENT", "UNKNOWN")]


@pytest.mark.parametrize("old, new", ACCEPTED)
def test_g7_5_an_accepted_transition_updates_the_message_and_is_audited(client, engine,
                                                                       ids, old, new):
    message, ref = _outbound(client, engine, ids, old)
    envelope = _status(ref, new)
    _accepted(_post(client, envelope))
    event = _event(engine, envelope["provider_event_id"])
    assert (event["status"], event["error_text"]) == ("PROCESSED", None)
    assert _messages(engine, ref)[0]["delivery_status"] == new
    update = [a for a in _audit(engine, "communication_messages", message)
              if a["action"] == "UPDATE"]
    assert len(update) == 1 and update[0]["actor_account_id"] is None
    assert (json.loads(update[0]["old_row"])["delivery_status"],
            json.loads(update[0]["new_row"])["delivery_status"]) == (old, new)


@pytest.mark.parametrize("old, new", REFUSED)
def test_g7_5_another_transition_is_ignored_and_writes_nothing(client, engine, ids, old,
                                                              new):
    """Checked before the UPDATE, so 0008 part B's refusal is never met: the
    event is IGNORED, not FAILED. A same-status event is refused too."""
    message, ref = _outbound(client, engine, ids, old)
    before = _counts(engine)
    envelope = _status(ref, new)
    _accepted(_post(client, envelope))
    event = _event(engine, envelope["provider_event_id"])
    assert (event["status"], event["error_text"]) == ("IGNORED",
                                                      "STATUS_TRANSITION_NOT_ACCEPTED")
    assert _messages(engine, ref)[0]["delivery_status"] == old
    assert _counts(engine) == {**before, "events": before["events"] + 1}


def test_g7_5_the_table_is_the_triggers(engine):
    """The service's table refuses exactly what 0008 part B refuses: every
    pair of the six statuses, tried on the trigger inside a rolled-back
    transaction."""
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    webhooks = _svc()
    statuses = ("QUEUED", "SENT", "DELIVERED", "READ", "FAILED", "UNKNOWN")
    with engine.connect() as conn:
        thread = conn.execute(text("""
            INSERT INTO turab.communication_threads (channel) VALUES ('OTHER')
            RETURNING thread_id""")).scalar_one()
        for old in statuses:
            for new in statuses:
                if old == new:
                    continue
                savepoint = conn.begin_nested()
                m = conn.execute(text("""
                    INSERT INTO turab.communication_messages
                           (thread_id, direction, occurred_at, delivery_status)
                    VALUES (:t, 'OUTBOUND', now(), CAST(:s AS turab.delivery_status))
                    RETURNING message_id"""), {"t": thread, "s": old}).scalar_one()
                try:
                    with conn.begin_nested():
                        conn.execute(text("""
                            UPDATE turab.communication_messages
                               SET delivery_status = CAST(:s AS turab.delivery_status)
                             WHERE message_id = :m"""), {"s": new, "m": m})
                    trigger = True
                except DBAPIError:
                    trigger = False
                savepoint.rollback()
                assert webhooks._accepted(old, new) is trigger, (old, new)
        conn.rollback()


def test_g7_5_a_status_change_in_flight_is_waited_for_then_seen(client, engine, ids):
    """The message is read FOR UPDATE before the check. A change to READ held
    by another transaction makes the event wait (witness), then the event
    sees READ and is IGNORED. Read without the lock, it would check SENT,
    accept DELIVERED, and meet 0008 part B's refusal: FAILED."""
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    from tests.test_slice7_step2 import _wait_until_blocked

    message, ref = _outbound(client, engine, ids, "SENT")
    holder = Session(bind=engine)
    envelope = _status(ref, "DELIVERED")
    out: dict = {}
    try:
        holder.execute(text("UPDATE turab.communication_messages SET delivery_status = "
                            "'READ' WHERE message_id = :m"), {"m": message})
        pid = holder.execute(text("SELECT pg_backend_pid()")).scalar_one()
        t = threading.Thread(target=lambda: out.setdefault("r", _post(client, envelope)))
        t.start()
        assert _wait_until_blocked(engine, pid, t), "the event waits for the message"
        holder.commit()
    finally:
        holder.close()
    t.join(20)
    _accepted(out["r"])
    event = _event(engine, envelope["provider_event_id"])
    assert (event["status"], event["error_text"]) == ("IGNORED",
                                                      "STATUS_TRANSITION_NOT_ACCEPTED")
    assert _messages(engine, ref)[0]["delivery_status"] == "READ"


def test_g7_5_a_status_for_no_recorded_message_is_ignored(client, engine):
    before = _counts(engine)
    envelope = _status(_mref(), "DELIVERED")
    _accepted(_post(client, envelope))
    event = _event(engine, envelope["provider_event_id"])
    assert (event["status"], event["error_text"]) == ("IGNORED", "UNKNOWN_MESSAGE")
    assert _counts(engine) == {**before, "events": before["events"] + 1}


def test_g7_5_a_webhook_message_takes_its_statuses(client, engine, ids):
    _, thread_ref = _whatsapp(client, ids, engine)
    ref = _mref()
    _accepted(_post(client, _msg(thread_ref, ref=ref)))
    for status in ("SENT", "READ"):
        _accepted(_post(client, _status(ref, status)))
    assert _messages(engine, ref)[0]["delivery_status"] == "READ"


# --- G7-2 (v): the replay (S42, J01, mandatory test 1) ----------------------------------

def test_s42_a_replay_of_a_completed_event_is_200_and_writes_nothing(client, engine, ids,
                                                                    sink):
    """Mandatory test 1, J01, S42, sequentially: the same signed envelope
    twice, one event, one message. The replay carries other content: it is not
    read."""
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    envelope = _msg(thread_ref, body=SECRET)
    _accepted(_post(client, envelope))
    first = _event(engine, envelope["provider_event_id"])
    before = _counts(engine)
    sink.clear()
    envelope["payload"]["body_text"] = "another body"
    _accepted(_post(client, envelope))
    assert _counts(engine) == before
    assert _event(engine, envelope["provider_event_id"]) == first
    [m] = _messages(engine, envelope["payload"]["external_message_ref"])
    assert m["body_text"] == SECRET
    [record] = sink.records
    assert (record.reason_code, record.resource_id) == ("REPLAYED", first["webhook_event_id"])


def test_s42_a_replay_of_an_ignored_event_writes_nothing(client, engine, sink):
    envelope = _status(_mref(), "SENT")
    _accepted(_post(client, envelope))
    first = _event(engine, envelope["provider_event_id"])
    assert first["status"] == "IGNORED"
    before = _counts(engine)
    sink.clear()
    _accepted(_post(client, envelope))
    assert _counts(engine) == before and _event(engine, envelope["provider_event_id"]) == first
    assert [r.reason_code for r in sink.records] == ["REPLAYED"]


def test_mandatory_test_1_concurrent_deliveries_make_one_message(client, engine, ids):
    """The same signed envelope, eight times at once: one event, one message;
    every answer is an empty 200."""
    _, thread_ref = _whatsapp(client, ids, engine)
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
    assert len(answers) == 8
    for r in answers:
        _accepted(r)
    assert _event(engine, envelope["provider_event_id"])["status"] == "PROCESSED"
    assert len(_messages(engine, envelope["payload"]["external_message_ref"])) == 1


# --- G7-2 (iv): the four failure tests ------------------------------------------------------

def _no_trace_of(engine, envelope):
    """No message, no audit row of a message, for this envelope's reference."""
    assert _messages(engine, envelope["payload"]["external_message_ref"]) == []


def test_iv_1_a_failure_in_processing_is_failed_with_its_code_and_answers_500(
        client, engine, ids, sink, monkeypatch, caplog):
    """An SQL error after the message's writes: the savepoint undoes them all,
    the event is FAILED `PROCESSING_FAILED` in the same T2, and the answer is
    CORRECTION-007's 500. No exception text in the event, the answer or the
    log; the cause's type only, under the trace id. A redelivery then
    completes it once, with its content."""
    from sqlalchemy import text

    webhooks = _svc()
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    envelope = _msg(thread_ref, body=SECRET)
    real = webhooks.process
    audit_before = _one(engine, "SELECT count(*) FROM turab.audit_log")
    thread_before = _one(engine, "SELECT last_message_at FROM turab.communication_threads "
                                 "WHERE thread_id = :t", t=thread)

    def failing(session, event_id, env, **kw):
        outcome = real(session, event_id, env, **kw)
        session.execute(text("SELECT 1 / 0"))
        return outcome

    monkeypatch.setattr(webhooks, "process", failing)
    caplog.set_level(logging.DEBUG)
    sink.clear()
    r = _post(client, envelope)
    assert (r.status_code, r.json()["code"]) == (500, "WEBHOOK_PROCESSING_FAILED")
    assert "division" not in r.text.lower() and "zero" not in r.text.lower()
    event = _event(engine, envelope["provider_event_id"])
    assert (event["status"], event["error_text"]) == ("FAILED", "PROCESSING_FAILED")
    assert event["processed_at"] is not None
    _no_trace_of(engine, envelope)
    assert _one(engine, "SELECT count(*) FROM turab.audit_log") == audit_before
    assert _one(engine, "SELECT last_message_at FROM turab.communication_threads "
                        "WHERE thread_id = :t", t=thread) == thread_before
    [record] = sink.records
    assert (record.reason_code, record.extra["http_status"], record.resource_id) == (
        "FAILED", 500, event["webhook_event_id"])
    [failure] = [x for x in caplog.records if x.getMessage() == "webhook processing failed"]
    assert failure.cause == "DataError"
    assert "division" not in caplog.text.lower()
    _no_secret_in_logs(caplog, _raw(envelope))

    monkeypatch.setattr(webhooks, "process", real)
    _accepted(_post(client, envelope))
    assert _event(engine, envelope["provider_event_id"])["status"] == "PROCESSED"
    [m] = _messages(engine, envelope["payload"]["external_message_ref"])
    assert m["body_text"] == SECRET
    assert m["metadata"]["webhook_event_id"] == str(event["webhook_event_id"])


def test_iv_1_a_python_exception_in_processing_is_failed_likewise(client, engine, ids,
                                                                 monkeypatch):
    webhooks = _svc()
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    real = webhooks.process

    def failing(session, event_id, env, **kw):
        real(session, event_id, env, **kw)
        raise RuntimeError(SECRET)

    monkeypatch.setattr(webhooks, "process", failing)
    r = _post(client, envelope)
    assert (r.status_code, r.json()["code"]) == (500, "WEBHOOK_PROCESSING_FAILED")
    assert SECRET not in r.text
    event = _event(engine, envelope["provider_event_id"])
    assert (event["status"], event["error_text"]) == ("FAILED", "PROCESSING_FAILED")
    _no_trace_of(engine, envelope)


def test_iv_2_a_stop_after_t1_is_completed_by_a_redelivery(client, engine, ids):
    """T1 committed, T2 never run: the event stays RECEIVED. A redelivery
    completes it, PROCESSED, one message, with its content."""
    from sqlalchemy.orm import Session

    webhooks = _svc()
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    raw = _raw(_msg(thread_ref, body=SECRET))
    envelope = webhooks.parse_envelope(raw)
    with Session(bind=engine) as session:
        webhooks.WebhookService(session, AccessAuditor(RecordingAuditSink()), "t").store(
            envelope)
    assert _event(engine, envelope.provider_event_id)["status"] == "RECEIVED"
    _no_trace_of(engine, {"payload": envelope.payload})
    _accepted(_post(client, raw=raw))
    assert _event(engine, envelope.provider_event_id)["status"] == "PROCESSED"
    [m] = _messages(engine, envelope.payload["external_message_ref"])
    assert m["body_text"] == SECRET


def test_iv_2_a_stop_after_t1_is_completed_by_the_recovery_without_content(client, engine,
                                                                          ids):
    """The recovery command completes it, PROCESSED, WITHOUT its content
    (`RECOVERED_WITHOUT_CONTENT`), even under the archive consent: the
    accepted limit of G7-2 (v)."""
    from sqlalchemy.orm import Session

    webhooks = _svc()
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    with_content = webhooks.parse_envelope(_raw(_msg(thread_ref, body=SECRET)))
    without = webhooks.parse_envelope(_raw(_msg(thread_ref)))
    with Session(bind=engine) as session:
        service = webhooks.WebhookService(session, AccessAuditor(RecordingAuditSink()), "t")
        service.store(with_content)
        service.store(without)
    with Session(bind=engine) as session:
        webhooks.recover(session, "recovery-test", delay_seconds=0)
    for envelope in (with_content, without):
        assert _event(engine, envelope.provider_event_id)["status"] == "PROCESSED"
    [m] = _messages(engine, with_content.payload["external_message_ref"])
    assert (m["body_text"], m["media_ref"]) == (None, None)
    assert m["metadata"]["content_withheld_reason"] == "RECOVERED_WITHOUT_CONTENT"
    assert m["metadata"]["content_archived"] is False
    [n] = _messages(engine, without.payload["external_message_ref"])
    assert "content_withheld_reason" not in n["metadata"]
    [audit] = _audit(engine, "communication_messages", m["message_id"])
    assert audit["context"]["operation"] == "recoverWebhookEvents"
    assert audit["actor_account_id"] is None


def test_iv_3_a_failure_of_the_status_update_loses_t2_whole(client, engine, ids, sink,
                                                            monkeypatch):
    """Step 4's UPDATE fails: T2 is lost whole, the event keeps RECEIVED,
    nothing of step 3 remains, and the answer is CORRECTION-007's 500. A
    second failure keeps FAILED from a FAILED event."""
    webhooks = _svc()
    thread, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    real = webhooks.finish

    def failing(session, event_id, status, code):
        if status != "FAILED":
            raise RuntimeError("step 4 lost")
        return real(session, event_id, status, code)

    monkeypatch.setattr(webhooks, "finish", failing)
    audit_before = _one(engine, "SELECT count(*) FROM turab.audit_log")
    sink.clear()
    r = _post(client, envelope)
    assert (r.status_code, r.json()["code"]) == (500, "WEBHOOK_PROCESSING_FAILED")
    event = _event(engine, envelope["provider_event_id"])
    assert (event["status"], event["processed_at"], event["error_text"]) == (
        "RECEIVED", None, None)
    _no_trace_of(engine, envelope)
    assert _one(engine, "SELECT count(*) FROM turab.audit_log") == audit_before
    assert [x.reason_code for x in sink.records] == ["PROCESSING_LOST"]

    # From FAILED: the event fails once, then step 4 is lost; it stays FAILED.
    monkeypatch.setattr(webhooks, "finish", real)
    second = _msg(thread_ref)
    real_process = webhooks.process

    def once(session, event_id, env, **kw):
        raise RuntimeError("first attempt")

    monkeypatch.setattr(webhooks, "process", once)
    assert _post(client, second).status_code == 500
    assert _event(engine, second["provider_event_id"])["status"] == "FAILED"
    monkeypatch.setattr(webhooks, "process", real_process)
    monkeypatch.setattr(webhooks, "finish", failing)
    assert _post(client, second).status_code == 500
    assert _event(engine, second["provider_event_id"])["status"] == "FAILED"
    _no_trace_of(engine, second)
    monkeypatch.setattr(webhooks, "finish", real)
    _accepted(_post(client, envelope))
    assert _event(engine, envelope["provider_event_id"])["status"] == "PROCESSED"
    assert len(_messages(engine, envelope["payload"]["external_message_ref"])) == 1


def test_iv_4_a_replay_while_t2_holds_the_claim_is_200_and_writes_nothing(
        client, engine, ids, sink, monkeypatch):
    """The first delivery's T2 holds the claim (a barrier inside step 3). The
    replay's claim is refused 55P03; it answers 200 and writes nothing; the
    holder completes the event, one message."""
    webhooks = _svc()
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    real = webhooks.process
    claimed, release = threading.Event(), threading.Event()

    def holding(session, event_id, env, **kw):
        claimed.set()
        assert release.wait(20)
        return real(session, event_id, env, **kw)

    monkeypatch.setattr(webhooks, "process", holding)
    out: dict = {}
    t = threading.Thread(target=lambda: out.setdefault("r", _post(client, envelope)))
    t.start()
    try:
        assert claimed.wait(20)
        monkeypatch.setattr(webhooks, "process", real)
        before = _counts(engine)
        sink.clear()
        _accepted(_post(client, envelope))
        assert _counts(engine) == before
        assert _event(engine, envelope["provider_event_id"])["status"] == "RECEIVED"
        assert [x.reason_code for x in sink.records] == ["IN_FLIGHT"]
    finally:
        release.set()
        t.join(20)
    _accepted(out["r"])
    assert _event(engine, envelope["provider_event_id"])["status"] == "PROCESSED"
    assert len(_messages(engine, envelope["payload"]["external_message_ref"])) == 1


def _unconfirmed(r):
    """A retryable answer that claims nothing about the event's record."""
    assert (r.status_code, r.json()["code"]) == (503, "WEBHOOK_NOT_READY"), r.text
    assert "stored" not in r.json()["detail"] and "nothing" not in r.json()["detail"].lower()


def test_iv_t1_failing_before_its_commit_is_503_then_a_redelivery_completes_it(
        client, engine, ids, sink, monkeypatch):
    """The review of 3dfb717. T1 raises before it commits: nothing is stored,
    but the answer does not say so; it is CORRECTION-008's 503, never
    CORRECTION-007's 500, which would claim the event is stored. The
    redelivery stores and processes it, one message."""
    webhooks = _svc()
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    real = webhooks.store

    def lost(*a, **kw):
        raise RuntimeError("T1 lost before its commit")

    monkeypatch.setattr(webhooks, "store", lost)
    sink.clear()
    _unconfirmed(_post(client, envelope))
    assert _event(engine, envelope["provider_event_id"]) is None
    [record] = sink.records
    assert (record.reason_code, record.extra["http_status"], record.resource_id,
            record.decision) == ("ACCEPTANCE_NOT_CONFIRMED", 503, None, "ALLOW")
    monkeypatch.setattr(webhooks, "store", real)
    _accepted(_post(client, envelope))
    assert _event(engine, envelope["provider_event_id"])["status"] == "PROCESSED"
    assert len(_messages(engine, envelope["payload"]["external_message_ref"])) == 1


def test_iv_t1_whose_commit_answer_is_lost_is_503_then_a_redelivery_completes_it_once(
        client, engine, ids, monkeypatch):
    """T1 commits, and its answer is lost (the COMMIT took effect; the
    application sees an exception). The answer is the same 503: the event is
    in fact RECEIVED. The redelivery reads that record and processes it once:
    one event, one message."""
    webhooks = _svc()
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    real = webhooks.store

    def committed_then_lost(*a, **kw):
        real(*a, **kw)
        raise RuntimeError("the COMMIT's answer lost")

    monkeypatch.setattr(webhooks, "store", committed_then_lost)
    _unconfirmed(_post(client, envelope))
    assert _event(engine, envelope["provider_event_id"])["status"] == "RECEIVED"
    assert _messages(engine, envelope["payload"]["external_message_ref"]) == []
    monkeypatch.setattr(webhooks, "store", real)
    _accepted(_post(client, envelope))
    assert _event(engine, envelope["provider_event_id"])["status"] == "PROCESSED"
    assert len(_messages(engine, envelope["payload"]["external_message_ref"])) == 1
    assert _one(engine, "SELECT count(*) FROM turab.webhook_events WHERE provider = "
                        "'whatsapp' AND provider_event_id = :e",
                e=envelope["provider_event_id"]) == 1


def test_iv_t2_whose_commit_answer_is_lost_is_500_then_a_redelivery_is_a_replay(
        client, engine, ids, sink, monkeypatch):
    """T2 commits PROCESSED, and its answer is lost. The answer is
    CORRECTION-007's 500, which says only that the result is not confirmed.
    The redelivery reads PROCESSED: a replay, an empty 200, no second
    message, nothing written."""
    webhooks = _svc()
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    envelope = _msg(thread_ref, body=SECRET)
    real = webhooks.run_t2

    def committed_then_lost(*a, **kw):
        real(*a, **kw)
        raise RuntimeError("the COMMIT's answer lost")

    monkeypatch.setattr(webhooks, "run_t2", committed_then_lost)
    sink.clear()
    r = _post(client, envelope)
    assert (r.status_code, r.json()["code"]) == (500, "WEBHOOK_PROCESSING_FAILED")
    assert "could not be confirmed" in r.json()["detail"]
    assert [x.reason_code for x in sink.records] == ["PROCESSING_LOST"]
    assert _event(engine, envelope["provider_event_id"])["status"] == "PROCESSED"
    monkeypatch.setattr(webhooks, "run_t2", real)
    before = _counts(engine)
    sink.clear()
    _accepted(_post(client, envelope))
    assert _counts(engine) == before
    assert [x.reason_code for x in sink.records] == ["REPLAYED"]
    [m] = _messages(engine, envelope["payload"]["external_message_ref"])
    assert m["body_text"] == SECRET


def test_archived_at_alone_refuses_nothing(client, engine, ids):
    """The review of 3dfb717: `archived_at` has no command (F7-9) and no rule
    of the plan makes it a refusal. An archived WHATSAPP thread is resolved
    by its reference and its consent checked as any other; its `archived_at`
    is left as it was.

    Measured while writing this test: 0008's thread guard refuses an UPDATE
    of `archived_at` ("a thread's links never change"), so a thread carries
    one only from its insert. The thread is inserted so, directly."""
    party = _party(engine)
    thread_ref = _ref()
    thread = _one(engine, """
        INSERT INTO turab.communication_threads (channel, party_id, external_thread_ref,
                                                 archived_at)
        VALUES ('WHATSAPP', :p, :r, '2026-10-01T00:00:00Z') RETURNING thread_id""",
                  p=party, r=thread_ref)
    archived = lambda: _one(engine, "SELECT archived_at FROM turab.communication_threads "
                                    "WHERE thread_id = :t", t=thread)
    stamp = archived()
    without = _msg(thread_ref, body=SECRET)
    _accepted(_post(client, without))
    [m] = _messages(engine, without["payload"]["external_message_ref"])
    assert (m["thread_id"], m["body_text"], m["metadata"]["content_withheld_reason"]) == (
        thread, None, "NO_ARCHIVE_CONSENT")
    _archive_consent(engine, party, thread)
    with_consent = _msg(thread_ref, body=SECRET)
    _accepted(_post(client, with_consent))
    [n] = _messages(engine, with_consent["payload"]["external_message_ref"])
    assert n["body_text"] == SECRET
    assert archived() == stamp
    from sqlalchemy.exc import DBAPIError

    from tests.test_slice4_step7 import _exec
    with pytest.raises(DBAPIError, match="a thread's links never change"):
        _exec(engine, "UPDATE turab.communication_threads SET archived_at = NULL "
                      "WHERE thread_id = :t", t=thread)


# --- the recovery command -------------------------------------------------------------------

def test_recovery_completes_a_failed_event_and_skips_a_fresh_received_one(client, engine,
                                                                         ids, monkeypatch):
    from sqlalchemy.orm import Session

    webhooks = _svc()
    _, thread_ref = _whatsapp(client, ids, engine)
    failed = _msg(thread_ref)
    real = webhooks.process

    def failing(*a, **kw):
        raise RuntimeError("x")

    monkeypatch.setattr(webhooks, "process", failing)
    assert _post(client, failed).status_code == 500
    monkeypatch.setattr(webhooks, "process", real)
    fresh = webhooks.parse_envelope(_raw(_msg(thread_ref)))
    with Session(bind=engine) as session:
        webhooks.WebhookService(session, AccessAuditor(RecordingAuditSink()), "t").store(fresh)
    with Session(bind=engine) as session:
        outcomes = webhooks.recover(session, "recovery-test")
    assert outcomes.get("PROCESSED", 0) >= 1
    assert _event(engine, failed["provider_event_id"])["status"] == "PROCESSED"
    assert _event(engine, fresh.provider_event_id)["status"] == "RECEIVED", \
        "a RECEIVED event younger than 5 minutes is not stuck"


def test_recovery_skips_a_row_another_processor_holds(client, engine, ids):
    from sqlalchemy import text
    from sqlalchemy.orm import Session

    webhooks = _svc()
    _, thread_ref = _whatsapp(client, ids, engine)
    held = webhooks.parse_envelope(_raw(_msg(thread_ref)))
    with Session(bind=engine) as session:
        event_id, _ = webhooks.WebhookService(
            session, AccessAuditor(RecordingAuditSink()), "t").store(held)
    holder = Session(bind=engine)
    try:
        holder.execute(text("SELECT 1 FROM turab.webhook_events WHERE webhook_event_id = :e "
                            "FOR UPDATE"), {"e": event_id})
        with Session(bind=engine) as session:
            outcome = webhooks.run_t2(session, event_id, held, "t", skip_locked=True)
        assert outcome == "IN_FLIGHT"
    finally:
        holder.rollback()
        holder.close()
    assert _event(engine, held.provider_event_id)["status"] == "RECEIVED"
    with Session(bind=engine) as session:
        assert webhooks.run_t2(session, event_id, held, "t", skip_locked=True) == "PROCESSED"
        assert webhooks.run_t2(session, event_id, held, "t", skip_locked=True) == "FINAL"


def test_the_recovery_script_prints_counts_only(engine, capsys, monkeypatch):
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "db/ops/recover_webhook_events.py"
    spec = importlib.util.spec_from_file_location("recover_webhook_events", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setenv("TURAB_DATABASE_URL", engine.url.render_as_string(hide_password=False))
    assert module.main(["--delay-seconds", "3600"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0].startswith("trace_id recovery-") and lines[-1].startswith("total ")
    for line in lines[1:-1]:
        outcome, count = line.split(" ")
        assert outcome in {"PROCESSED", "IGNORED", "FAILED", "IN_FLIGHT", "FINAL",
                           "PROCESSING_LOST"} and count.isdigit()


# --- hygiene: no content, signature or secret in a log or an access record (J03) ------------

def _no_secret_in_logs(caplog, raw):
    signature = _sign(raw).removeprefix("sha256=")
    for record in caplog.records:
        dump = repr(record.__dict__)
        for needle in (SECRET, MEDIA, KEY, signature):
            assert needle not in dump, (needle, record.getMessage())


def test_j03_nothing_of_the_body_reaches_a_log_or_an_access_record(client, engine, ids, sink,
                                                                   caplog):
    """Every kind of answer, each recorded once (G7-17 (vii)), none carrying
    the body, the signature, the secret or a reference of the envelope."""
    party = _party(engine)
    thread, thread_ref = _whatsapp(client, ids, engine, party=party)
    _archive_consent(engine, party, thread)
    caplog.set_level(logging.DEBUG)
    sink.clear()
    envelope = _msg(thread_ref, body=SECRET, media=MEDIA)
    raw = _raw(envelope)
    answers = [
        _post(client, raw=raw),                                   # 200 PROCESSED
        _post(client, raw=raw),                                   # 200 REPLAYED
        _post(client, raw=raw, signature=_sign(raw, "x")),        # 401
        _post(client, raw=raw[:-1]),                              # 400 envelope
        _post(client, raw=raw + b" " * (64 * 1024)),              # 400 size
    ]
    assert [a.status_code for a in answers] == [200, 200, 401, 400, 400]
    assert [r.reason_code for r in sink.records] == [
        "PROCESSED", "REPLAYED", "SIGNATURE_NOT_VALID", "ENVELOPE_NOT_VALID",
        "BODY_TOO_LARGE"]
    refs = (envelope["provider_event_id"], envelope["payload"]["external_message_ref"],
            thread_ref)
    for record in sink.records:
        dump = json.dumps(record.as_dict(), default=str)
        for needle in (SECRET, MEDIA, KEY, *refs):
            assert needle not in dump
        assert set(record.extra) == {"http_status"}
    _no_secret_in_logs(caplog, raw)
    for needle in refs:
        assert needle not in caplog.text
    for a in answers:
        for needle in (SECRET, MEDIA, KEY, *refs):
            assert needle not in a.text


def test_the_webhook_stays_in_the_closed_public_list_and_reads_no_bearer(client, engine,
                                                                       ids):
    """R10.4: no subject is resolved. A bearer of a disabled or unknown
    account changes nothing; the signature alone decides."""
    from turab.auth.policy import PUBLIC_OPERATIONS

    assert "postWebhooksWhatsapp" in PUBLIC_OPERATIONS and len(PUBLIC_OPERATIONS) == 6
    _, thread_ref = _whatsapp(client, ids, engine)
    envelope = _msg(thread_ref)
    _accepted(_post(client, envelope, headers={"Authorization": f"Bearer {uuid.uuid4()}"}))
    assert _post(client, _msg(thread_ref), signature="sha256=" + "0" * 64,
                 headers={"Authorization": f"Bearer {ids.ACC_ADMIN}"}).status_code == 401
