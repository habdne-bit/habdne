"""R-1 step 3: duty 5 and §5.1's classes and answers.

Plan: `docs/gate/R1_RELAY_PLAN.md` (revision 7) §3 duty 5 (R1-T5.1 to
R1-T5.7), R1-T3.8, §5.1, R1-D2, R1-D3; step 3 authorized in the review of
`da3d778`. The relay: `relay/turab_relay/forward.py`, wired in `app.py`.

**Two kinds of TURAB:**
- **a test double** (`Turab`, an `httpx.MockTransport` handler): records each
  envelope the relay sends, with its signature, and answers as each test
  tells it;
- **TURAB's real application and test database** (R1-T5.6), served by
  uvicorn on the loopback interface; the relay reaches it over HTTP, with
  `trust_env=False` shown to hold under a proxy set in the environment.

Every notification is synthetic (step 2's builders) and signed with a test
app secret. No test uses Meta, a real number or a real customer.
"""
from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
import logging
import socket
import threading
import time
import uuid

import httpx
import pytest
from fastapi.testclient import TestClient

from tests.test_r1_step2 import CONTENT, CUSTOMER, _message, _notification, _status
from turab.services import webhooks
from turab_relay import app as relay_app
from turab_relay import forward, meta, transform

APP_SECRET = "meta-app-secret-r1-step3"
TOKEN = "verify-token-r1-step3"
KEY = "relay-key-r1-step3"
URL = "http://turab.test/webhooks/whatsapp"
PATH = relay_app.PATH
TIMEOUT = 0.3
TURAB_BODY = b"TURAB-ANSWER-BODY-r1s3"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    monkeypatch.setenv(meta.VERIFY_TOKEN_VARIABLE, TOKEN)
    monkeypatch.setenv(meta.APP_SECRET_VARIABLE, APP_SECRET)
    monkeypatch.setenv(transform.SIGNING_KEY_VARIABLE, KEY)
    monkeypatch.setenv(forward.TURAB_URL_VARIABLE, URL)


class Turab:
    """A test double of TURAB's webhook. `answers[event_id]` lists the
    answers to give that envelope, one per delivery, then 200; `"silent"`
    never answers."""

    def __init__(self):
        self.received: list[dict] = []
        self.answers: dict[str, list] = {}

    async def handle(self, request: httpx.Request) -> httpx.Response:
        raw = await request.aread()
        event_id = json.loads(raw)["provider_event_id"]
        self.received.append({"event_id": event_id, "raw": raw, "url": str(request.url),
                              "signature": request.headers.get(transform.SIGNATURE_HEADER),
                              "type": request.headers.get("content-type")})
        plan = self.answers.get(event_id)
        answer = plan.pop(0) if plan else 200
        if answer == "silent":
            await asyncio.sleep(30)
        if answer == 200:
            return httpx.Response(200)
        headers = {"location": "http://elsewhere.test/"} if 300 <= answer < 400 else {}
        return httpx.Response(answer, content=TURAB_BODY, headers=headers)

    @property
    def ids(self) -> list[str]:
        return [r["event_id"] for r in self.received]


@pytest.fixture
def turab():
    return Turab()


def _relay(transport=None, timeout=TIMEOUT):
    return relay_app.create_app(require_client_certificate=False, turab_timeout=timeout,
                                turab_transport=transport)


@pytest.fixture
def relay(turab):
    app = _relay(httpx.MockTransport(turab.handle))
    with TestClient(app) as c:
        c.counts = app.counts
        yield c


def _meta_signature(raw: bytes) -> str:
    return "sha256=" + hmac.new(APP_SECRET.encode(), raw, hashlib.sha256).hexdigest()


def _from_meta(client, raw: bytes):
    """Meta's POST: the same bytes and signature on every delivery (M7)."""
    return client.post(PATH, content=raw, headers={"X-Hub-Signature-256": _meta_signature(raw)})


def _alerts(caplog) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.name == "turab_relay.alert"]


def _batch():
    """Two messages and a status, forwarded; the three event ids in order."""
    raw = _notification(messages=[_message(wamid="w1"), _message(wamid="w2")],
                        statuses=[_status("delivered", wamid="w0")])
    return raw, ["message:w1", "message:w2", "status:w0:delivered:1700000000"]


# --- R1-T5.1: every forwarded element 200 -> 200 to Meta ----------------------------------

def test_r1_t5_1_every_element_200_is_200_to_meta_in_document_order(relay, turab):
    raw, ids = _batch()
    r = _from_meta(relay, raw)
    assert (r.status_code, r.content) == (200, b"")
    assert turab.ids == ids
    sent = [e.envelope for e in transform.elements(raw) if e.cls == transform.FORWARD]
    assert [x["raw"] for x in turab.received] == sent, "the exact bytes of step 2"
    for x in turab.received:
        assert x["url"] == URL and x["type"] == "application/json"
        assert webhooks.verify(x["raw"], x["signature"], KEY.encode()), "TURAB's own verify"
        assert webhooks.parse_envelope(x["raw"]).provider_event_id == x["event_id"]


def test_r1_t5_1_the_order_sent_is_the_documents_inside_one_value(relay, turab):
    """The review of `ced7df7`'s case, through the delivery: `statuses`
    written before `messages` are sent first."""
    raw = (b'{"object":"whatsapp_business_account","entry":[{"changes":[{"field":"messages",'
           b'"value":{"statuses":[' + json.dumps(_status("read", wamid="w9")).encode()
           + b'],"messages":[' + json.dumps(_message(wamid="w1")).encode()
           + b'],"metadata":{"phone_number_id":"106540352242922"}}}]}]}')
    assert _from_meta(relay, raw).status_code == 200
    assert turab.ids == ["status:w9:read:1700000000", "message:w1"]


# --- R1-T5.2 to R1-T5.4: not completed -> not 200 -------------------------------------------

@pytest.mark.parametrize("answer, status, reason", [
    (500, 502, "TURAB_NOT_COMPLETED"), (503, 502, "TURAB_NOT_COMPLETED"),
    ("silent", 504, "TURAB_NO_ANSWER")])
def test_r1_t5_2_to_4_one_element_not_completed_is_not_200_and_stops_the_delivery(
        relay, turab, caplog, answer, status, reason):
    """The element after the one not completed is not sent in this attempt,
    so TURAB processes the elements in document order across attempts."""
    caplog.set_level(logging.INFO)
    raw, ids = _batch()
    turab.answers[ids[1]] = [answer]
    started = time.monotonic()
    r = _from_meta(relay, raw)
    assert r.status_code == status and r.status_code != 200
    assert turab.ids == ids[:2], "stopped at the element not completed"
    assert any(reason in m for m in (x.getMessage() for x in caplog.records
                                      if x.name == "turab_relay"))
    if answer == "silent":
        assert time.monotonic() - started < 5, "the deadline holds, not the double's 30 s"
    assert _alerts(caplog) == [], "a retryable answer is not an alert"


def test_r1_t5_4_a_connection_that_never_answers_is_504_within_the_deadline(monkeypatch):
    """A real socket that accepts the connection and never answers."""
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    monkeypatch.setenv(forward.TURAB_URL_VARIABLE,
                       f"http://127.0.0.1:{listener.getsockname()[1]}/webhooks/whatsapp")
    try:
        with TestClient(_relay()) as client:
            started = time.monotonic()
            r = _from_meta(client, _batch()[0])
            elapsed = time.monotonic() - started
    finally:
        listener.close()
    assert r.status_code == 504
    assert elapsed < 5


def test_r1_t5_4_no_connection_is_504(monkeypatch):
    closed = socket.socket()
    closed.bind(("127.0.0.1", 0))
    port = closed.getsockname()[1]
    closed.close()
    monkeypatch.setenv(forward.TURAB_URL_VARIABLE, f"http://127.0.0.1:{port}/webhooks/whatsapp")
    with TestClient(_relay()) as client:
        assert _from_meta(client, _batch()[0]).status_code == 504


# --- R1-T5.5: the redelivery, against the double ---------------------------------------------

def test_r1_t5_5_metas_redelivery_sends_everything_again_in_order(relay, turab):
    """Meta redelivers the POST whole (M7): the completed element is sent
    again (TURAB answers it as a replay, writing nothing: R1-T5.6), then the
    rest, in order."""
    raw, ids = _batch()
    turab.answers[ids[1]] = [500]
    assert _from_meta(relay, raw).status_code == 502
    assert _from_meta(relay, raw).status_code == 200
    assert turab.ids == ids[:2] + ids
    first, again = turab.received[0], turab.received[2]
    assert (first["raw"], first["signature"]) == (again["raw"], again["signature"]), \
        "the same bytes, the same signature: S42's replay"


# --- R1-T5.7: TURAB's 400 or 401 (R1-D3 (a)) -------------------------------------------------

@pytest.mark.parametrize("answer", [400, 401, 403, 404, 302, 201])
def test_r1_t5_7_any_other_answer_is_not_200_and_an_alert(relay, turab, caplog, answer):
    caplog.set_level(logging.INFO)
    raw, ids = _batch()
    turab.answers[ids[0]] = [answer]
    r = _from_meta(relay, raw)
    assert r.status_code == 502
    assert turab.ids == ids[:1], "stopped; a redirect is not followed"
    assert [a.split(" trace=")[0] for a in _alerts(caplog)] == [
        f"alert TURAB_REFUSED {answer}"]
    _no_secret_in_logs(caplog, raw)


# --- R1-T3.8: §5.1's answers ------------------------------------------------------------------

def test_r1_t3_8_isolated_and_dropped_do_not_change_a_200(relay, turab, caplog):
    raw = _notification(
        messages=[_message(wamid="w1"), _message(wamid="w2", sender="other"),
                  _message(wamid="w3", group_id="g")],
        statuses=[_status("played", wamid="w4"), _status("deleted", wamid="w5"),
                  _status("read", wamid="w6")],
        contacts=[{"wa_id": CUSTOMER}], errors=[{"code": 1}])
    r = _from_meta(relay, raw)
    assert r.status_code == 200
    assert turab.ids == ["message:w1", "status:w6:read:1700000000"]
    alerts = [a.split(" trace=")[0] for a in _alerts(caplog)]
    assert alerts == ["alert ISOLATED CONTACT_MISMATCH", "alert ISOLATED STATUS_NOT_KNOWN"]


def test_r1_t3_8_no_forwarded_element_is_200_and_sends_nothing(relay, turab):
    raw = _notification(statuses=[_status("played")], errors=[{"code": 1}])
    assert _from_meta(relay, raw).status_code == 200
    assert _from_meta(relay, _notification(messages=[_message()], field="account_alerts")) \
        .status_code == 200
    assert turab.received == []


def test_r1_t3_8_an_isolated_element_does_not_rescue_a_failed_delivery(relay, turab):
    raw = _notification(messages=[_message(wamid="w1"), _message(wamid="w2", sender="x:y")])
    turab.answers["message:w1"] = [503]
    assert _from_meta(relay, raw).status_code == 502


def test_an_undocumented_status_is_counted_and_alerted(relay, turab, caplog):
    """The reading accepted in the review of `ced7df7`: ISOLATED,
    `STATUS_NOT_KNOWN`, counted and alerted, no envelope."""
    assert _from_meta(relay, _notification(statuses=[_status("deleted")])).status_code == 200
    assert relay.counts[(transform.ISOLATED, "STATUS_NOT_KNOWN")] == 1
    assert [a.split(" trace=")[0] for a in _alerts(caplog)] == [
        "alert ISOLATED STATUS_NOT_KNOWN"]
    assert turab.received == []


def test_each_element_and_each_delivery_is_counted(relay, turab):
    raw, ids = _batch()
    turab.answers[ids[1]] = [500]
    _from_meta(relay, raw)
    _from_meta(relay, _notification(messages=[_message(group_id="g")], errors=[{}]))
    assert dict(relay.counts) == {
        (transform.FORWARD, "FORWARDED"): 3,
        ("DELIVERY", forward.COMPLETED): 1, ("DELIVERY", forward.NOT_COMPLETED): 1,
        (transform.DROPPED, "GROUP_MESSAGE"): 1, (transform.DROPPED, "VALUE_ERRORS"): 1}


# --- fail closed: nothing sent ------------------------------------------------------------------

@pytest.mark.parametrize("setup, reason", [
    (lambda m: m.delenv(transform.SIGNING_KEY_VARIABLE), "RELAY_KEY_REFUSED"),
    (lambda m: m.setenv(transform.SIGNING_KEY_VARIABLE, ""), "RELAY_KEY_REFUSED"),
    (lambda m: m.setenv(transform.SIGNING_KEY_VARIABLE, APP_SECRET), "RELAY_KEY_REFUSED"),
    (lambda m: m.delenv(forward.TURAB_URL_VARIABLE), "TURAB_URL_NOT_CONFIGURED"),
    (lambda m: m.setenv(forward.TURAB_URL_VARIABLE, ""), "TURAB_URL_NOT_CONFIGURED"),
])
def test_no_key_or_no_url_sends_nothing_and_is_503(relay, turab, caplog, monkeypatch, setup,
                                                    reason):
    setup(monkeypatch)
    r = _from_meta(relay, _batch()[0])
    assert r.status_code == 503
    assert turab.received == []
    assert [a.split(" trace=")[0] for a in _alerts(caplog)] == [f"alert {reason}"]


def test_metas_refusals_come_before_the_delivery(relay, turab):
    raw = _batch()[0]
    assert relay.post(PATH, content=raw, headers={"X-Hub-Signature-256": "sha256=" + "0" * 64}
                      ).status_code == 401
    assert turab.received == []


# --- no content in any log (R1-D9, R1-T2.7) ----------------------------------------------------

def _no_secret_in_logs(caplog, raw):
    envelopes = [e.envelope for e in transform.elements(raw) if e.envelope]
    signatures = [transform.sign(e, KEY.encode())[7:] for e in envelopes]
    text = "\n".join(r.getMessage() + " " + repr(r.__dict__) for r in caplog.records)
    for needle in [CONTENT, KEY, APP_SECRET, TURAB_BODY.decode(), _meta_signature(raw)[7:],
                   *signatures, *(e.decode() for e in envelopes)]:
        assert needle not in text


@pytest.mark.parametrize("answer", [200, 500, 400, "silent"])
def test_no_log_holds_content_an_envelope_a_signature_a_key_or_turabs_answer(
        relay, turab, caplog, answer):
    """Every logger, `httpx`'s included."""
    caplog.set_level(logging.DEBUG)
    raw = _notification(messages=[_message(wamid="w1"), _message(wamid="w2", sender="other")])
    turab.answers["message:w1"] = [answer]
    _from_meta(relay, raw)
    _no_secret_in_logs(caplog, raw)


# --- R1-T5.6: TURAB's real application and test database ---------------------------------------

@contextlib.contextmanager
def _served(app):
    """`app` behind uvicorn on the loopback interface; yields its port."""
    import uvicorn

    config = uvicorn.Config(app, log_level="critical", access_log=False, lifespan="on")
    server = uvicorn.Server(config)
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    deadline = time.time() + 10
    while not server.started and time.time() < deadline:
        time.sleep(0.02)
    assert server.started
    try:
        yield sock.getsockname()[1]
    finally:
        server.should_exit = True
        thread.join(10)


@pytest.fixture
def real(engine, monkeypatch):
    """TURAB's real application behind uvicorn, the relay pointed at it over
    the network, and a proxy in the environment the relay must not use."""
    from turab.app import create_app
    from turab.auth.audit import AccessAuditor, RecordingAuditSink

    turab_app = create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink()))
    setup = create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink()))
    with _served(turab_app) as port, TestClient(setup) as staff:
        monkeypatch.setenv(forward.TURAB_URL_VARIABLE,
                           f"http://127.0.0.1:{port}/webhooks/whatsapp")
        for proxy in ("HTTP_PROXY", "http_proxy", "ALL_PROXY", "all_proxy"):
            monkeypatch.setenv(proxy, "http://127.0.0.1:9")
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        relay_asgi = _relay(timeout=10)
        with TestClient(relay_asgi) as client:
            client.staff = staff
            yield client


def _digits() -> str:
    return str(uuid.uuid4().int)[:15]


def _wamid() -> str:
    return f"wamid.{uuid.uuid4().hex}"


def _footprint(engine):
    from tests.test_slice4_step7 import _one

    return {t: _one(engine, f"SELECT count(*) FROM turab.{t}")
            for t in ("webhook_events", "communication_messages", "interactions", "audit_log")}


def _event(engine, provider_event_id):
    from tests.test_slice4_step7 import _all

    rows = _all(engine, """
        SELECT processing_status::text AS status, error_text FROM turab.webhook_events
         WHERE provider = 'whatsapp' AND provider_event_id = :e""", e=provider_event_id)
    return [(r["status"], r["error_text"]) for r in rows]


def _messages(engine, ref):
    from tests.test_slice4_step7 import _all

    return _all(engine, """
        SELECT message_id, direction::text AS direction,
               delivery_status::text AS delivery_status
          FROM turab.communication_messages
         WHERE provider = 'whatsapp' AND external_message_ref = :r""", r=ref)


def _interactions(engine, message_id):
    from tests.test_slice4_step7 import _one

    return _one(engine, "SELECT count(*) FROM turab.interactions "
                        "WHERE metadata->>'message_id' = :m", m=str(message_id))


def _conversation(real, engine, ids, status="SENT"):
    """A WHATSAPP thread `<business>:<customer>` in TURAB, and a staff
    OUTBOUND message in it, at `status`, that Meta's statuses will name."""
    from tests.test_slice7_step2 import _message as staff_message
    from tests.test_slice7_step2 import _new_thread, _ok

    business, customer = _digits(), _digits()
    thread = _new_thread(real.staff, ids, engine, channel="WHATSAPP",
                         ref=f"{business}:{customer}")
    outbound = _wamid()
    _ok(staff_message(real.staff, thread, {"direction": "OUTBOUND",
                                           "occurred_at": "2023-11-14T22:00:00Z",
                                           "external_message_ref": outbound,
                                           "delivery_status": status}, ids.ACC_OPERATOR))
    return business, customer, outbound


def _fail_once(monkeypatch, provider_event_id):
    """TURAB's T2 fails once for one event, after its writes, as Slice 7's
    tests make it fail: CORRECTION-007's 500, the event FAILED."""
    from sqlalchemy import text

    real_process = webhooks.process
    left = [1]

    def failing(session, event_id, envelope, **kw):
        outcome = real_process(session, event_id, envelope, **kw)
        if envelope.provider_event_id == provider_event_id and left:
            left.pop()
            session.execute(text("SELECT 1 / 0"))
        return outcome

    monkeypatch.setattr(webhooks, "process", failing)


def test_r1_t5_6_a_500_then_metas_redelivery_against_turabs_real_application(
        real, engine, ids, monkeypatch):
    """R1-T5.2 then R1-T5.5 against TURAB's real application and test
    database: one event, one message and one interaction per message."""
    business, customer, outbound = _conversation(real, engine, ids)
    w1, w2 = _wamid(), _wamid()
    raw = _notification(messages=[_message(sender=customer, wamid=w1),
                                  _message(sender=customer, wamid=w2)],
                        statuses=[_status("delivered", recipient=customer, wamid=outbound)],
                        contacts=[{"wa_id": customer}], business=business)
    status_id = f"status:{outbound}:delivered:1700000000"
    _fail_once(monkeypatch, f"message:{w2}")
    before = _footprint(engine)

    assert _from_meta(real, raw).status_code == 502, "TURAB's 500: not 200 to Meta"
    assert _event(engine, f"message:{w1}") == [("PROCESSED", None)]
    assert _event(engine, f"message:{w2}") == [("FAILED", "PROCESSING_FAILED")]
    assert _event(engine, status_id) == [], "stopped: the status was not sent"
    assert len(_messages(engine, w1)) == 1 and _messages(engine, w2) == []
    assert _messages(engine, outbound)[0]["delivery_status"] == "SENT"
    middle = _footprint(engine)
    assert middle["webhook_events"] == before["webhook_events"] + 2
    assert middle["interactions"] == before["interactions"] + 1

    assert _from_meta(real, raw).status_code == 200, "Meta's redelivery completes it"
    for event_id in (f"message:{w1}", f"message:{w2}", status_id):
        assert _event(engine, event_id) == [("PROCESSED", None)], event_id
    for ref in (w1, w2):
        [message] = _messages(engine, ref)
        assert message["direction"] == "INBOUND"
        assert _interactions(engine, message["message_id"]) == 1, "one interaction"
    assert _messages(engine, outbound)[0]["delivery_status"] == "DELIVERED"
    after = _footprint(engine)
    assert after["webhook_events"] == before["webhook_events"] + 3
    assert after["communication_messages"] == before["communication_messages"] + 2
    assert after["interactions"] == before["interactions"] + 2

    assert _from_meta(real, raw).status_code == 200, "a duplicate delivery (M7)"
    assert _footprint(engine) == after, "S42: the replays write nothing"


def test_r1_t5_6_stopping_keeps_two_statuses_of_one_message_in_order(real, engine, ids,
                                                                     monkeypatch):
    """Why the delivery stops at the first element not completed: `delivered`
    fails once, so `read` waits for the redelivery. Sent anyway, `read`
    would be processed first, and the redelivered `delivered` refused by
    G7-5 (IGNORED): TURAB's record out of the document's order."""
    business, customer, outbound = _conversation(real, engine, ids, status="QUEUED")
    raw = _notification(statuses=[_status("delivered", recipient=customer, wamid=outbound),
                                  _status("read", recipient=customer, wamid=outbound)],
                        contacts=None, business=business)
    delivered = f"status:{outbound}:delivered:1700000000"
    read = f"status:{outbound}:read:1700000000"
    _fail_once(monkeypatch, delivered)
    assert _from_meta(real, raw).status_code == 502
    assert _event(engine, read) == [], "read waits"
    assert _from_meta(real, raw).status_code == 200
    assert _event(engine, delivered) == _event(engine, read) == [("PROCESSED", None)]
    from tests.test_slice7_step3 import _audit

    [message] = _messages(engine, outbound)
    moves = [(json.loads(a["old_row"])["delivery_status"],
              json.loads(a["new_row"])["delivery_status"])
             for a in _audit(engine, "communication_messages", message["message_id"])
             if a["action"] == "UPDATE"]
    assert moves == [("QUEUED", "DELIVERED"), ("DELIVERED", "READ")]


def test_r1_t5_5_a_repeated_status_changes_nothing_against_turabs_real_application(
        real, engine, ids):
    """R1-F7: Meta's redelivery may keep a status's timestamp (the same
    event: a replay) or, undocumented, change it (another event: TURAB
    refuses the same status again by G7-5). Either way, nothing changes."""
    business, customer, outbound = _conversation(real, engine, ids)

    def status(ts):
        return _notification(statuses=[_status("read", recipient=customer, wamid=outbound,
                                                ts=ts)], contacts=None, business=business)

    assert _from_meta(real, status("1700000100")).status_code == 200
    assert _messages(engine, outbound)[0]["delivery_status"] == "READ"
    before = _footprint(engine)
    assert _from_meta(real, status("1700000100")).status_code == 200
    assert _footprint(engine) == before, "the same timestamp: a replay"
    assert _from_meta(real, status("1700000200")).status_code == 200
    assert _event(engine, f"status:{outbound}:read:1700000200") == [
        ("IGNORED", "STATUS_TRANSITION_NOT_ACCEPTED")]
    assert _footprint(engine) == {**before, "webhook_events": before["webhook_events"] + 1}
    assert _messages(engine, outbound)[0]["delivery_status"] == "READ"


def test_r1_t5_7_turabs_401_against_its_real_application(real, engine, ids, monkeypatch,
                                                        caplog):
    """The relay and TURAB holding different keys: TURAB's 401, not 200 to
    Meta, an alert, and nothing written."""
    business, customer, _ = _conversation(real, engine, ids)
    monkeypatch.setattr(webhooks, "signing_secret", lambda: b"another-key")
    raw = _notification(messages=[_message(sender=customer, wamid=_wamid())],
                        contacts=[{"wa_id": customer}], business=business)
    before = _footprint(engine)
    assert _from_meta(real, raw).status_code == 502
    assert _footprint(engine) == before
    assert [a.split(" trace=")[0] for a in _alerts(caplog)] == ["alert TURAB_REFUSED 401"]
