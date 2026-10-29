"""R-1 step 2: the transformation of Meta's notifications (duty 3), the
relay's signature (duty 4) and `thread_ref` (duty 6), each tested with
TURAB's own code.

Plan: `docs/gate/R1_RELAY_PLAN.md`, revision 5; step 2 authorized in the
review of `e9fac51`. Every notification is synthetic, built on the structures
Meta documents (`R1-META-SOURCES.txt`, E18-E26, E28-E52). The relay's output
is checked by **TURAB's own** `parse_envelope`, `verify`, `SCOPED` and
`_accepted`, not by a copy of their rules.

Not here (step 3): sending to TURAB, and the answer to Meta. Not here (step
4): the envelopes' sizes and OVERSIZE.
"""
from __future__ import annotations

import json

import pytest

from turab.services import communication, webhooks
from turab_relay import meta, transform
from turab_relay.transform import DROPPED, FORWARD, ISOLATED

BUSINESS = "106540352242922"
CUSTOMER = "16505551234"
WAMID = "wamid.HBgLMTY1MDM4Nzk0MzkVAgASGBQzQTRBNjU5OUFFRTAzODEwMTQ0RgA="
KEY = "relay-test-key-r1-step2"
CONTENT = "SECRET-CONTENT-r1s2"


def _notification(*, messages=None, statuses=None, contacts="default", errors=None,
                  business=BUSINESS, field="messages", obj="whatsapp_business_account"):
    value = {"messaging_product": "whatsapp",
             "metadata": {"display_phone_number": "15550783881", "phone_number_id": business}}
    if contacts == "default":
        contacts = [{"profile": {"name": "Synthetic"}, "wa_id": CUSTOMER}]
    if contacts is not None:
        value["contacts"] = contacts
    if messages is not None:
        value["messages"] = messages
    if statuses is not None:
        value["statuses"] = statuses
    if errors is not None:
        value["errors"] = errors
    return json.dumps({"object": obj, "entry": [{"id": "102290129340398", "changes": [
        {"value": value, "field": field}]}]}).encode()


def _message(meta_type="text", *, sender=CUSTOMER, wamid=WAMID, ts="1700000000", **extra):
    m = {"from": sender, "id": wamid, "timestamp": ts, "type": meta_type}
    if meta_type == "text":
        m["text"] = {"body": CONTENT}
    m.update(extra)
    return m


def _status(status="delivered", *, recipient=CUSTOMER, wamid=WAMID, ts="1700000000", **extra):
    s = {"id": wamid, "status": status, "timestamp": ts, "recipient_id": recipient}
    s.update(extra)
    return s


def _turab(element):
    """The forwarded envelope, as TURAB's own parser reads it."""
    assert element.cls == FORWARD and element.envelope is not None
    return webhooks.parse_envelope(element.envelope)


def _no_content(element):
    assert element.envelope is None
    assert CONTENT not in repr(element)


# --- duty 3: the transformation ----------------------------------------------------------

def test_r1_t3_1_a_text_message_is_one_envelope_turab_accepts():
    [e] = transform.elements(_notification(messages=[_message()]))
    env = _turab(e)
    assert (env.provider_event_id, env.event_type) == (f"message:{WAMID}", "message")
    assert env.payload == {"external_message_ref": WAMID,
                           "thread_ref": f"{BUSINESS}:{CUSTOMER}",
                           "occurred_at": "2023-11-14T22:13:20Z", "message_type": "TEXT",
                           "body_text": CONTENT}


def test_r1_t3_2_a_status_is_one_envelope_turab_accepts():
    [e] = transform.elements(_notification(statuses=[_status("read")], contacts=None))
    env = _turab(e)
    assert (env.provider_event_id, env.event_type) == (f"status:{WAMID}:read:1700000000",
                                                       "status")
    assert env.payload == {"external_message_ref": WAMID,
                           "thread_ref": f"{BUSINESS}:{CUSTOMER}", "status": "READ",
                           "occurred_at": "2023-11-14T22:13:20Z"}


@pytest.mark.parametrize("meta_status, turab_status", [
    ("sent", "SENT"), ("delivered", "DELIVERED"), ("read", "READ"), ("failed", "FAILED")])
def test_r1_t3_2_each_meta_status_maps_to_turabs(meta_status, turab_status):
    [e] = transform.elements(_notification(statuses=[_status(meta_status)]))
    assert _turab(e).payload["status"] == turab_status
    assert turab_status in webhooks.STATUSES


def test_r1_t3_3_a_batch_gives_one_envelope_per_element_in_document_order():
    def change(business, messages, statuses):
        return {"field": "messages", "value": {
            "metadata": {"phone_number_id": business},
            "messages": messages, "statuses": statuses}}
    doc = {"object": "whatsapp_business_account", "entry": [
        {"changes": [change("111", [_message(wamid="w1"), _message(wamid="w2")],
                            [_status("sent", wamid="w9")]),
                     change("222", [_message(wamid="w3")], [])]},
        {"changes": [change("333", [], [_status("read", wamid="w8"),
                                        _status("delivered", wamid="w7")])]}]}
    out = transform.elements(json.dumps(doc).encode())
    assert [e.provider_event_id for e in out] == [
        "message:w1", "message:w2", "status:w9:sent:1700000000", "message:w3",
        "status:w8:read:1700000000", "status:w7:delivered:1700000000"]
    assert all(e.cls == FORWARD for e in out)
    assert [_turab(e).payload["thread_ref"].split(":")[0] for e in out] == [
        "111", "111", "111", "222", "333", "333"]


@pytest.mark.parametrize("kwargs, reason", [
    ({"field": "account_alerts"}, "FIELD_NOT_MESSAGES"),
    ({"obj": "page"}, "OBJECT_NOT_WHATSAPP"),
])
def test_r1_t3_4_another_field_or_object_is_dropped(kwargs, reason):
    out = transform.elements(_notification(messages=[_message()], **kwargs))
    assert [(e.cls, e.reason) for e in out] == [(DROPPED, reason)]
    _no_content(out[0])


#: §5.3's table, type by type: (Meta's message, stored type, the content keys).
MEDIA = {"id": "media-id-r1", "mime_type": "image/jpeg", "sha256": "abc", "url": "https://x"}
TABLE = [
    ({"type": "text", "text": {"body": CONTENT}}, "TEXT", {"body_text": CONTENT}),
    ({"type": "image", "image": {**MEDIA, "caption": CONTENT}}, "IMAGE",
     {"body_text": CONTENT, "media_ref": "media-id-r1"}),
    ({"type": "image", "image": MEDIA}, "IMAGE", {"media_ref": "media-id-r1"}),
    ({"type": "video", "video": {**MEDIA, "caption": CONTENT}}, "VIDEO",
     {"body_text": CONTENT, "media_ref": "media-id-r1"}),
    ({"type": "document", "document": {**MEDIA, "caption": CONTENT, "filename": "f.pdf"}},
     "DOCUMENT", {"body_text": CONTENT, "media_ref": "media-id-r1"}),
    # A caption Meta does not document on audio or a sticker is not carried:
    # §5.3 gives them no body_text.
    ({"type": "audio", "audio": {**MEDIA, "voice": True, "caption": CONTENT}}, "AUDIO",
     {"media_ref": "media-id-r1"}),
    ({"type": "sticker", "sticker": {**MEDIA, "animated": False, "caption": CONTENT}},
     "STICKER", {"media_ref": "media-id-r1"}),
    ({"type": "location", "location": {"latitude": 1, "longitude": 2, "name": CONTENT}},
     "OTHER", {}),
    ({"type": "contacts", "contacts": [{"name": {"formatted_name": CONTENT}}]}, "OTHER", {}),
    ({"type": "interactive", "interactive": {"type": "button_reply",
                                            "button_reply": {"id": "b", "title": CONTENT}}},
     "OTHER", {}),
    ({"type": "button", "button": {"payload": "p", "text": CONTENT}}, "OTHER", {}),
    ({"type": "reaction", "reaction": {"message_id": "w0", "emoji": CONTENT}}, "OTHER", {}),
    ({"type": "order", "order": {"catalog_id": "c", "text": CONTENT}}, "OTHER", {}),
    ({"type": "system", "system": {"body": CONTENT}}, "OTHER", {}),
    ({"type": "unsupported", "unsupported": {"type": "x"}, "errors": [{"title": CONTENT}]},
     "OTHER", {}),
    ({"type": "edit", "edit": {"original_message_id": "w0", "message": {"text": {
        "body": CONTENT}}}}, "OTHER", {}),
    ({"type": "revoke", "revoke": {"original_message_id": "w0"}}, "OTHER", {}),
    ({"type": "a_future_type", "a_future_type": {"body": CONTENT}}, "OTHER", {}),
]


@pytest.mark.parametrize("message, stored, content", TABLE,
                         ids=[f"{m['type']}-{i}" for i, (m, _, _) in enumerate(TABLE)])
def test_r1_t3_5_each_type_maps_exactly_as_section_5_3_states(message, stored, content):
    m = {"from": CUSTOMER, "id": WAMID, "timestamp": "1700000000", **message}
    [e] = transform.elements(_notification(messages=[m]))
    payload = dict(_turab(e).payload)
    assert payload.pop("message_type") == stored
    for key in ("external_message_ref", "thread_ref", "occurred_at"):
        payload.pop(key)
    assert payload == content
    if not content:
        assert CONTENT.encode() not in e.envelope


def test_r1_t3_5_no_stored_type_equals_an_internal_one():
    stored = {t for t, _ in transform.TYPES.values()} | {transform.OTHER}
    assert not stored & set(communication.LINK_TYPES)


def test_r1_t3_6_sent_then_read_without_delivered_is_accepted_by_turab_in_order():
    out = transform.elements(_notification(statuses=[_status("sent", ts="1"),
                                                     _status("read", ts="2")]))
    first, second = (_turab(e).payload["status"] for e in out)
    assert (first, second) == ("SENT", "READ")
    assert webhooks._accepted("UNKNOWN", first) and webhooks._accepted(first, second)


@pytest.mark.parametrize("ts, iso", [("0", "1970-01-01T00:00:00Z"),
                                     ("1700000000", "2023-11-14T22:13:20Z"),
                                     ("1749416383", "2025-06-08T20:59:43Z")])
def test_the_timestamp_becomes_rfc_3339_in_utc(ts, iso):
    [e] = transform.elements(_notification(messages=[_message(ts=ts)]))
    assert _turab(e).payload["occurred_at"] == iso


@pytest.mark.parametrize("ts", ["", "abc", "-1", "1.5", "1e9", " 17", "١٧٠٠", "9" * 5000,
                                "99999999999999999"])
def test_a_timestamp_that_is_not_unix_seconds_isolates_the_element(ts):
    for out in (transform.elements(_notification(messages=[_message(ts=ts)])),
                transform.elements(_notification(statuses=[_status(ts=ts)]))):
        [e] = out
        assert e.cls == ISOLATED
        _no_content(e)


# --- §5.1: the checks, by element kind ---------------------------------------------------

@pytest.mark.parametrize("drop", ["from", "id", "timestamp", "type"])
def test_a_message_missing_a_required_field_is_isolated(drop):
    m = _message()
    del m[drop]
    [e] = transform.elements(_notification(messages=[m]))
    assert (e.cls, e.reason) == (ISOLATED, "MESSAGE_FIELD_MISSING")
    _no_content(e)


@pytest.mark.parametrize("drop", ["id", "status", "timestamp", "recipient_id"])
def test_a_status_missing_a_required_field_is_isolated(drop):
    s = _status()
    del s[drop]
    [e] = transform.elements(_notification(statuses=[s]))
    assert (e.cls, e.reason) == (ISOLATED, "STATUS_FIELD_MISSING")


def test_a_status_is_never_checked_for_from_nor_against_contacts():
    """§5.1, revision 3: `from` is a message's; a status has none."""
    [e] = transform.elements(_notification(
        statuses=[_status()], contacts=[{"wa_id": "someone-else"}]))
    assert e.cls == FORWARD and "from" not in _status()


def test_no_business_number_isolates_both_kinds():
    out = transform.elements(_notification(messages=[_message()], statuses=[_status()],
                                           business=None))
    assert [(e.kind, e.cls) for e in out] == [("message", ISOLATED), ("status", ISOLATED)]


def test_played_is_dropped():
    [e] = transform.elements(_notification(statuses=[_status("played")]))
    assert (e.cls, e.reason) == (DROPPED, "STATUS_PLAYED")


def test_a_status_value_meta_does_not_document_is_isolated():
    """Our reading (R1-STEP2 delivery §3): a value outside Meta's five would be
    refused by TURAB (400), so it is isolated, not forwarded."""
    [e] = transform.elements(_notification(statuses=[_status("deleted")]))
    assert (e.cls, e.reason) == (ISOLATED, "STATUS_NOT_KNOWN")


def test_value_errors_are_dropped_one_each():
    out = transform.elements(_notification(errors=[{"code": 1, "title": CONTENT},
                                                   {"code": 2}]))
    assert [(e.cls, e.reason) for e in out] == [(DROPPED, "VALUE_ERRORS")] * 2
    for e in out:
        _no_content(e)


@pytest.mark.parametrize("raw", [b"not json", b"\xff\xfe", b"[]", b"{}", b'{"object": 1}'])
def test_a_notification_not_on_whatsapp_business_account_forwards_nothing(raw):
    out = transform.elements(raw)
    assert len(out) == 1 and out[0].cls in (ISOLATED, DROPPED) and out[0].envelope is None


# --- duty 4: the relay's signature -------------------------------------------------------

def test_r1_t4_1_and_2_the_signature_is_over_the_exact_bytes_and_turab_verifies_it(
        monkeypatch):
    monkeypatch.setenv(transform.SIGNING_KEY_VARIABLE, KEY)
    monkeypatch.setenv(meta.APP_SECRET_VARIABLE, "meta-app-secret")
    [e] = transform.elements(_notification(messages=[_message()]))
    header = transform.sign(e.envelope, transform.signing_key())
    assert webhooks.verify(e.envelope, header, KEY.encode())
    assert not webhooks.verify(e.envelope, header, b"another-key")
    assert not webhooks.verify(e.envelope + b" ", header, KEY.encode())
    assert transform.SIGNATURE_HEADER.lower() == webhooks.SIGNATURE_HEADER.lower()
    assert transform.SIGNING_KEY_VARIABLE == webhooks.SECRET_VARIABLE


def test_r1_t4_3_a_key_equal_to_metas_app_secret_is_refused(monkeypatch):
    monkeypatch.setenv(transform.SIGNING_KEY_VARIABLE, "same-secret")
    monkeypatch.setenv(meta.APP_SECRET_VARIABLE, "same-secret")
    with pytest.raises(transform.RelayKeyRefused, match="equals Meta's app secret"):
        transform.signing_key()


@pytest.mark.parametrize("value", [None, ""])
def test_r1_t4_4_no_key_signs_nothing(monkeypatch, value):
    if value is None:
        monkeypatch.delenv(transform.SIGNING_KEY_VARIABLE, raising=False)
    else:
        monkeypatch.setenv(transform.SIGNING_KEY_VARIABLE, value)
    with pytest.raises(transform.RelayKeyRefused, match="is not set"):
        transform.signing_key()


# --- duty 6: thread_ref, and R1-D8 -------------------------------------------------------

def test_r1_t6_1_and_2_thread_ref_is_the_business_then_the_customer():
    out = transform.elements(_notification(messages=[_message()], statuses=[_status()]))
    assert [_turab(e).payload["thread_ref"] for e in out] == [f"{BUSINESS}:{CUSTOMER}"] * 2


def test_r1_t6_3_one_customer_writing_to_two_business_numbers_has_two_thread_refs():
    a, = transform.elements(_notification(messages=[_message()], business="111"))
    b, = transform.elements(_notification(messages=[_message()], business="222"))
    assert _turab(a).payload["thread_ref"] != _turab(b).payload["thread_ref"]


def test_r1_t6_4_every_thread_ref_matches_turabs_scoped():
    out = transform.elements(_notification(messages=[_message()], statuses=[_status()]))
    assert all(communication.SCOPED.match(_turab(e).payload["thread_ref"]) for e in out)


@pytest.mark.parametrize("field, value", [("sender", "165:0555"), ("sender", ""),
                                          ("business", "106:54"), ("business", "")])
def test_r1_t6_5_an_identifier_that_cannot_be_scoped_is_isolated(field, value):
    if field == "sender":
        doc = _notification(messages=[_message(sender=value)], contacts=None)
    else:
        doc = _notification(messages=[_message()], business=value)
    [e] = transform.elements(doc)
    assert e.cls == ISOLATED
    _no_content(e)


def test_r1_t6_5_a_status_recipient_that_cannot_be_scoped_is_isolated():
    [e] = transform.elements(_notification(statuses=[_status(recipient="1:2")]))
    assert (e.cls, e.reason) == (ISOLATED, "IDENTIFIER_NOT_SCOPABLE")


def test_r1_t6_6_group_messages_and_group_statuses_are_dropped():
    out = transform.elements(_notification(
        messages=[_message(group_id="HBgLMTY1MDM4Nzk0MzkVAgASGBQzQTRB")],
        statuses=[_status(recipient_type="group", recipient_participant_id=CUSTOMER)]))
    assert [(e.cls, e.reason) for e in out] == [(DROPPED, "GROUP_MESSAGE"),
                                               (DROPPED, "GROUP_STATUS")]
    for e in out:
        _no_content(e)


@pytest.mark.parametrize("contacts, cls", [
    (None, FORWARD),
    ([], FORWARD),
    ([{"profile": {"name": "n"}}], FORWARD),
    ([{"wa_id": CUSTOMER}], FORWARD),
    ([{"wa_id": "other-1"}, {"wa_id": CUSTOMER}], FORWARD),
    ([{"wa_id": "other-1"}], ISOLATED),
    ([{"wa_id": "other-1"}, {"wa_id": "other-2"}], ISOLATED),
])
def test_r1_t6_7_contacts_are_checked_as_r1_d8_states(contacts, cls):
    """`from` must equal one of the `wa_id`s present; the absence of contacts,
    or of any `wa_id`, does not isolate a message (review of `3d8b593`)."""
    [e] = transform.elements(_notification(messages=[_message()], contacts=contacts))
    assert e.cls == cls
    if cls == ISOLATED:
        assert e.reason == "CONTACT_MISMATCH"
        _no_content(e)
    else:
        _turab(e)


def test_no_element_ever_carries_content_unless_forwarded():
    doc = _notification(
        messages=[_message(), _message(sender="1:2"), _message(group_id="g")],
        statuses=[_status("played"), _status("deleted")],
        contacts=[{"wa_id": CUSTOMER}], errors=[{"title": CONTENT}])
    out = transform.elements(doc)
    assert [e.cls for e in out] == [DROPPED, FORWARD, ISOLATED, DROPPED, DROPPED, ISOLATED]
    for e in out:
        if e.cls != FORWARD:
            _no_content(e)
