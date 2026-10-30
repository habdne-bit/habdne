"""R1-T7.6: the room each envelope leaves for content, measured.

    .venv/bin/python db/dev/r1_envelope_room.py > docs/gate/evidence/R1-STEP4-ENVELOPE-ROOM.txt

Plan: `docs/gate/R1_RELAY_PLAN.md` §3 duty 7, R1-T7.6. The envelope's size
is measured on the bytes `transform.elements` produces, never computed from
a formula. Meta documents no maximum for any field (§1 of the plan), so the
room is stated for the synthetic identifiers of step 2's tests (lengths of
Meta's own examples), with what each identifier's length costs.

Deterministic: the same tree writes the same record.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path[:0] = [str(ROOT / "relay"), str(ROOT / "src")]

from turab_relay import transform  # noqa: E402

BUSINESS = "106540352242922"
CUSTOMER = "16505551234"
WAMID = "wamid.HBgLMTY1MDM4Nzk0MzkVAgASGBQzQTRBNjU5OUFFRTAzODEwMTQ0RgA="
MEDIA_ID = "1234567890123456"
LIMIT = transform.ENVELOPE_LIMIT


def _raw(message=None, status=None, business=BUSINESS):
    value = {"metadata": {"phone_number_id": business}}
    if message is not None:
        value["messages"] = [message]
    if status is not None:
        value["statuses"] = [status]
    return json.dumps({"object": "whatsapp_business_account",
                       "entry": [{"changes": [{"field": "messages", "value": value}]}]}).encode()


def _message(meta_type, content, wamid=WAMID, sender=CUSTOMER):
    m = {"from": sender, "id": wamid, "timestamp": "1700000000", "type": meta_type}
    if meta_type == "text":
        m["text"] = {"body": content}
    elif meta_type in ("image", "video", "document"):
        m[meta_type] = {"id": MEDIA_ID, "caption": content}
    else:
        m[meta_type] = {"id": content}
    return m


def _size(raw) -> int:
    [element] = transform.elements(raw)
    assert element.cls == transform.FORWARD, element
    return len(element.envelope)


def main() -> None:
    print("TURAB — R-1 step 4, R1-T7.6: the room each envelope leaves for content, measured")
    print("Written by db/dev/r1_envelope_room.py; sizes are the bytes transform.elements produces.")
    print(f"Limit: transform.ENVELOPE_LIMIT = {LIMIT} bytes (TURAB's BODY_LIMIT, G7-15).")
    print(f"Identifiers: phone_number_id {len(BUSINESS)} digits; from/recipient_id "
          f"{len(CUSTOMER)} digits; wamid {len(WAMID)} characters; media id {len(MEDIA_ID)} "
          "digits.")
    print()
    print(f"{'Meta type':<10} {'variable content':<26} {'envelope, 1 byte':>16} "
          f"{'room for content':>17}")
    for meta_type, field in [("text", "text.body"), ("image", "image.caption"),
                             ("video", "video.caption"), ("document", "document.caption"),
                             ("audio", "audio.id"), ("sticker", "sticker.id")]:
        one = _size(_raw(_message(meta_type, "a")))
        assert _size(_raw(_message(meta_type, "a" * 101))) == one + 100
        print(f"{meta_type:<10} {field:<26} {one:>16} {LIMIT - one + 1:>17}")
    status = {"id": WAMID, "status": "delivered", "timestamp": "1700000000",
              "recipient_id": CUSTOMER}
    print(f"{'(status)':<10} {'none':<26} {_size(_raw(status=status)):>16} {'—':>17}")
    print()
    print("What each identifier's length costs (measured on a text message, bytes per")
    print("added character):")
    base = _size(_raw(_message("text", "a")))
    for name, kw in [("wamid", {"wamid": WAMID + "X"}), ("from", {"sender": CUSTOMER + "1"})]:
        print(f"  {name:<16} {_size(_raw(_message('text', 'a', **kw))) - base}")
    print(f"  {'phone_number_id':<16} "
          f"{_size(_raw(_message('text', 'a'), business=BUSINESS + '1')) - base}")
    print()
    print("Reading:")
    print("- The room is the limit less the envelope with one byte of content, plus that byte.")
    print("- A content's bytes are its serialized bytes: a 2-, 3- or 4-byte UTF-8 character costs")
    print("  2, 3 or 4; \" and \\ cost 2; a control character costs 2 (\\n, \\t...) or 6 (\\u00XX).")
    print("- For image, video and document, the caption shares the room with nothing else that")
    print("  varies here; the media id is fixed at the example's length.")
    print("- For audio and sticker the only content is the media id, Meta's identifier.")
    print("- R1-T7.7: real envelopes are not measured. No real traffic exists (R1-D13 (a)).")


if __name__ == "__main__":
    main()
