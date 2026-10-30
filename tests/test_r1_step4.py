"""R-1 step 4: duty 7, the size of each envelope after its serialization,
the OVERSIZE class and the redelivery (R1-Q1 (a)).

Plan: `docs/gate/R1_RELAY_PLAN.md` (revision 10) §3 duty 7 (R1-T7.1 to
R1-T7.7), §5.1 (OVERSIZE), §5.4 (R1-Q1 decided (a)); step 4 authorized in
the review of `79c232b`.

**The limit is TURAB's:** `BODY_LIMIT`, 64 × 1024 = 65 536 bytes, a body
refused when larger (G7-15). **No field of Meta's has a documented maximum**
(§1 of the plan): the size is the serialized bytes the relay sends,
measured, never a content's length.

The double, the relay and TURAB's real application are step 3's fixtures
(`tests/test_r1_step3.py`). Every notification is synthetic.
"""
from __future__ import annotations

import json
import logging

import pytest

from tests.test_r1_step2 import BUSINESS, CUSTOMER, _message, _notification, _status
from tests.test_r1_step3 import (  # noqa: F401  (fixtures)
    _alerts, _conversation, _env, _event, _footprint, _from_meta, _messages, _no_secret_in_logs,
    _wamid, real, relay, turab)
from turab.services import webhooks
from turab_relay import app as relay_app
from turab_relay import transform

LIMIT = 64 * 1024
MARK = "SIZE-CONTENT-r1s4"


def _text(body: str, wamid: str = "w1", sender: str = CUSTOMER):
    return _message(wamid=wamid, sender=sender, text={"body": body})


def _one(body: str, **kw):
    """One text message's element; `contacts` absent (it is not in the
    envelope, and would isolate another sender)."""
    [element] = transform.elements(_notification(messages=[_text(body, **kw)], contacts=None))
    return element


def _cost(unit: str) -> int:
    """The bytes one `unit` takes in the serialized envelope."""
    return len(json.dumps(unit, ensure_ascii=False)[1:-1].encode("utf-8"))


def _body_for(target: int, unit: str = "a", **kw) -> str:
    """A text body whose message envelope serializes to exactly `target`
    bytes: `unit` repeated, then ASCII to make the count exact."""
    base = len(_one(MARK, **kw).envelope) - len(MARK)
    room = target - base
    n, pad = divmod(room - len(MARK), _cost(unit))
    return MARK + unit * n + "a" * pad


# --- the limit itself ----------------------------------------------------------------------

def test_the_relays_limit_is_turabs_body_limit():
    assert transform.ENVELOPE_LIMIT == webhooks.BODY_LIMIT == LIMIT


# --- R1-T7.1: exactly 65 536 bytes ------------------------------------------------------------

def test_r1_t7_1_an_envelope_of_exactly_65536_bytes_is_forwarded(relay, turab):
    body = _body_for(LIMIT)
    element = _one(body)
    assert element.cls == transform.FORWARD and len(element.envelope) == LIMIT
    r = _from_meta(relay, _notification(messages=[_text(body)]))
    assert r.status_code == 200
    assert [len(x["raw"]) for x in turab.received] == [LIMIT]


def test_r1_t7_1_turabs_real_route_accepts_exactly_65536_bytes(real, engine, ids):
    business, customer, _ = _conversation(real, engine, ids)
    wamid = _wamid()
    body = _body_for(LIMIT, wamid=wamid, sender=customer)
    raw = _notification(messages=[_text(body, wamid=wamid, sender=customer)],
                        contacts=[{"wa_id": customer}], business=business)
    [element] = transform.elements(raw)
    assert len(element.envelope) == LIMIT
    assert _from_meta(real, raw).status_code == 200
    assert _event(engine, f"message:{wamid}") == [("PROCESSED", None)]
    assert len(_messages(engine, wamid)) == 1


# --- R1-T7.2: one byte over, inside a batch (R1-Q1 (a)) ----------------------------------------

def _oversize_batch():
    """w1 valid, w2 one byte over the limit, w3 valid, then a status."""
    over = _body_for(LIMIT) + "a"
    raw = _notification(messages=[_text("ok", "w1"), _text(over, "w2"), _text("ok", "w3")],
                        statuses=[_status("read", wamid="w0")])
    return raw, over


def test_r1_t7_2_an_oversize_element_is_classed_oversize_without_its_envelope():
    raw, over = _oversize_batch()
    classes = [(e.cls, e.provider_event_id) for e in transform.elements(raw)]
    assert classes[1] == (transform.OVERSIZE, "message:w2")
    oversize = transform.elements(raw)[1]
    assert oversize.envelope is None and over not in repr(oversize)


def test_r1_t7_2_not_sent_not_shortened_the_others_delivered_the_answer_not_200(
        relay, turab, caplog):
    caplog.set_level(logging.DEBUG)
    raw, over = _oversize_batch()
    r = _from_meta(relay, raw)
    assert r.status_code != 200
    assert turab.ids == ["message:w1", "message:w3", "status:w0:read:1700000000"], \
        "w2 neither sent nor shortened; the valid elements after it delivered"
    assert all(len(x["raw"]) <= LIMIT for x in turab.received)
    assert [a.split(" trace=")[0] for a in _alerts(caplog)] == ["alert OVERSIZE message"]
    assert relay.counts[(transform.OVERSIZE, "ENVELOPE_OVER_LIMIT")] == 1
    text = "\n".join(rec.getMessage() + " " + repr(rec.__dict__) for rec in caplog.records)
    assert MARK not in text, "no content in any log"
    _no_secret_in_logs(caplog, raw)


def test_r1_t7_2_metas_redelivery_writes_nothing_twice_and_is_oversize_again(
        real, engine, ids):
    """Against TURAB's real application: the first delivery completes the
    valid elements and answers not 200; Meta's redelivery replays them,
    writing nothing a second time, and the oversize element is OVERSIZE
    again: not 200 again."""
    business, customer, outbound = _conversation(real, engine, ids)
    w1, w2, w3 = _wamid(), _wamid(), _wamid()
    over = _body_for(LIMIT, wamid=w2, sender=customer) + "a"
    raw = _notification(messages=[_text("ok", w1, customer), _text(over, w2, customer),
                                  _text("ok", w3, customer)],
                        statuses=[_status("delivered", recipient=customer, wamid=outbound)],
                        contacts=[{"wa_id": customer}], business=business)
    before = _footprint(engine)
    assert _from_meta(real, raw).status_code != 200
    after = _footprint(engine)
    assert after["webhook_events"] == before["webhook_events"] + 3
    assert after["communication_messages"] == before["communication_messages"] + 2
    assert _event(engine, f"message:{w2}") == [] and _messages(engine, w2) == []
    assert _messages(engine, outbound)[0]["delivery_status"] == "DELIVERED"
    assert _from_meta(real, raw).status_code != 200, "OVERSIZE again"
    assert _footprint(engine) == after, "the replays write nothing a second time"


# --- R1-T7.3: the serialized bytes, not the content's length -----------------------------------

UNITS = [("é", 2), ("€", 3), ("😀", 4), ('"', 2), ("\\", 2), ("\n", 2), ("\x01", 6),
         ("\x1f", 6)]


@pytest.mark.parametrize("unit, cost", UNITS, ids=[repr(u) for u, _ in UNITS])
def test_r1_t7_3_each_case_at_65536_and_65537_bytes(relay, turab, unit, cost):
    assert _cost(unit) == cost
    at = _body_for(LIMIT, unit)
    assert len(at) < LIMIT, "the content's length is under the limit; its bytes are not"
    element = _one(at)
    assert element.cls == transform.FORWARD and len(element.envelope) == LIMIT
    assert _one(at + "a").cls == transform.OVERSIZE
    assert _from_meta(relay, _notification(messages=[_text(at)])).status_code == 200
    assert _from_meta(relay, _notification(messages=[_text(at + "a", "w2")])).status_code != 200
    assert [len(x["raw"]) for x in turab.received] == [LIMIT]


# --- R1-T7.4: each envelope measured on its own -------------------------------------------------

def test_r1_t7_4_a_batch_of_envelopes_near_the_limit(relay, turab):
    image = _message("image", wamid="w5", image={"id": "media-1", "caption": "c" * 65000})
    raw = _notification(messages=[_text(_body_for(LIMIT), "w1"), _text(_body_for(LIMIT - 1), "w2"),
                                  _text(_body_for(LIMIT) + "a", "w3"),
                                  _text(_body_for(LIMIT, "€"), "w4"), image])
    classes = [e.cls for e in transform.elements(raw)]
    assert classes[:4] == [transform.FORWARD, transform.FORWARD, transform.OVERSIZE,
                           transform.FORWARD]
    _from_meta(relay, raw)
    assert "message:w3" not in turab.ids
    assert all(len(x["raw"]) <= LIMIT for x in turab.received)
    sizes = {x["event_id"]: len(x["raw"]) for x in turab.received}
    assert sizes["message:w1"] == sizes["message:w4"] == LIMIT
    assert sizes["message:w2"] == LIMIT - 1


# --- R1-T7.5: Meta's request at 3 MiB, many elements -------------------------------------------

def test_r1_t7_5_a_post_of_exactly_3_mib_is_accepted_one_byte_more_is_413(relay, turab):
    body = "x" * 60_000
    messages = [_text(body, f"w{i}") for i in range(52)]
    raw = _notification(messages=messages)
    raw += b" " * (relay_app.INBOUND_LIMIT - len(raw))
    assert len(raw) == relay_app.INBOUND_LIMIT
    assert _from_meta(relay, raw).status_code == 200
    assert len(turab.received) == 52
    turab.received.clear()
    assert _from_meta(relay, raw + b" ").status_code == 413
    assert turab.received == []


# --- serialization: a string UTF-8 cannot encode --------------------------------------------------

@pytest.mark.parametrize("where", ["body", "from"])
def test_a_lone_surrogate_is_isolated_not_a_crash(relay, turab, caplog, where):
    """JSON may escape a lone surrogate (`"\\ud800"`); `json.loads` gives a
    string UTF-8 cannot encode. The element is ISOLATED, nothing is sent,
    and the other elements are delivered."""
    lone = "\\ud800"
    message = _text("before" if where == "from" else "x", "w2")
    raw = _notification(messages=[_text("ok", "w1"), message])
    if where == "body":
        raw = raw.replace(b'"body": "x"', b'"body": "a' + lone.encode() + b'b"')
    else:
        doc = json.loads(raw)
        doc["entry"][0]["changes"][0]["value"]["contacts"] = None
        raw = json.dumps(doc).encode().replace(
            f'"from": "{CUSTOMER}", "id": "w2"'.encode(),
            ('"from": "1' + lone + '", "id": "w2"').encode())
    assert lone.encode() in raw
    elements = transform.elements(raw)
    assert [(e.cls, e.reason) for e in elements][1] == (transform.ISOLATED,
                                                        "NOT_UTF8_ENCODABLE")
    r = _from_meta(relay, raw)
    assert r.status_code == 200
    assert turab.ids == ["message:w1"]
    assert [a.split(" trace=")[0] for a in _alerts(caplog)] == [
        "alert ISOLATED NOT_UTF8_ENCODABLE"]


def test_a_surrogate_pair_is_one_character_of_four_bytes():
    raw = _notification(messages=[_text("x")]).replace(b'"body": "x"',
                                                         b'"body": "\\ud83d\\ude00"')
    [element] = transform.elements(raw)
    assert element.cls == transform.FORWARD
    assert "😀".encode() in element.envelope


# --- R1-T7.6: the room left for content, per type -----------------------------------------------

#: A media id of the length Meta's examples show (16 digits).
MEDIA_ID = "1234567890123456"


def _typed(meta_type: str, content: str, wamid: str = "w1"):
    """One message of `meta_type`, its variable content `content`: the text,
    or the caption of a medium that carries one; the id otherwise."""
    if meta_type == "text":
        return _text(content, wamid)
    if meta_type in ("image", "video", "document"):
        return _message(meta_type, wamid=wamid, **{meta_type: {"id": MEDIA_ID,
                                                               "caption": content}})
    return _message(meta_type, wamid=wamid, **{meta_type: {"id": content}})


def _size(meta_type: str, content: str) -> int:
    [element] = transform.elements(_notification(messages=[_typed(meta_type, content)]))
    assert element.cls == transform.FORWARD
    return len(element.envelope)


@pytest.mark.parametrize("meta_type", ["text", "image", "video", "document", "audio",
                                       "sticker"])
def test_r1_t7_6_the_room_left_for_content_is_measured_per_type(meta_type):
    """The envelope grows by exactly the content's serialized bytes, so the
    room is the limit less the envelope with one byte of content, plus one.
    For the types with a variable text, that room filled exactly is
    forwarded; one byte more is OVERSIZE. `db/dev/r1_envelope_room.py`
    writes the numbers (`evidence/R1-STEP4-ENVELOPE-ROOM.txt`)."""
    frame = _size(meta_type, "a") - 1
    assert _size(meta_type, "a" * 100) == frame + 100
    assert _size(meta_type, "é" * 100) == frame + 200
    room = LIMIT - frame
    assert 0 < room < LIMIT
    if meta_type in ("text", "image", "video", "document"):
        assert _size(meta_type, "a" * room) == LIMIT
        [over] = transform.elements(_notification(messages=[_typed(meta_type, "a" * (room + 1))]))
        assert over.cls == transform.OVERSIZE


# --- §4: the count check (R1-D14 (a)) ------------------------------------------------------------

def _counter():
    import importlib.util
    import pathlib

    path = pathlib.Path(__file__).resolve().parents[1] / "db" / "ops" / "count_webhook_events.py"
    spec = importlib.util.spec_from_file_location("count_webhook_events", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def server(engine, monkeypatch):
    """The suite's server in the standard PG* variables, as an operator
    would set them; no PGSERVICE or PGDATABASE."""
    url = engine.url
    monkeypatch.setenv("PGHOST", url.host or "127.0.0.1")
    monkeypatch.setenv("PGPORT", str(url.port or 5432))
    monkeypatch.setenv("PGUSER", url.username or "")
    monkeypatch.setenv("PGPASSWORD", url.password or "")
    for variable in ("PGSERVICE", "PGDATABASE", "PGHOSTADDR"):
        monkeypatch.delenv(variable, raising=False)
    return url.database


def test_the_count_check_prints_the_count_read_only_and_nothing_else(server, engine, capsys):
    import re

    from tests.test_slice4_step7 import _one as scalar

    expected = scalar(engine, "SELECT count(*) FROM turab.webhook_events")
    assert _counter().main([server]) == 0
    out = capsys.readouterr().out.splitlines()
    assert len(out) == 1
    assert re.fullmatch(rf"{server} host=\S+ read_only=on webhook_events={expected}", out[0])


def test_the_count_check_says_when_there_is_no_table(server, capsys):
    assert _counter().main(["postgres"]) == 0
    assert capsys.readouterr().out.strip().endswith("read_only=on webhook_events=NO_TABLE")


@pytest.mark.parametrize("variable", ["PGSERVICE", "PGDATABASE"])
def test_the_count_check_refuses_a_destination_it_was_not_given(server, capsys, monkeypatch,
                                                               variable):
    monkeypatch.setenv(variable, "elsewhere")
    assert _counter().main([server]) == 2
    captured = capsys.readouterr()
    assert captured.out == "" and variable in captured.err
