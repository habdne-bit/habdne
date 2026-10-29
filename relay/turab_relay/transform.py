"""Duties 3, 4 and 6: Meta's notification to TURAB's envelopes, the relay's
signature, and `thread_ref`.

Plan: `docs/gate/R1_RELAY_PLAN.md` (revision 6) §3 duties 3, 4 and 6; §5.1
(each element's class, by its kind); §5.3 (R1-D6's table); R1-D5, R1-D7,
R1-D8, R1-D12. Meta's structures are quoted in
`docs/gate/evidence/R1-META-SOURCES.txt` (E18-E59).

**What this module does:** given the bytes of a notification whose signature
was verified (duty 2), it returns one `Element` per message and per status,
in document order (of `entry`, of `changes`, and of the keys inside each
`value`), each placed in exactly one class:
- **FORWARD:** passes every check of its kind; carries its envelope's bytes;
- **ISOLATED:** fails a check of its kind; no envelope, and **no content
  anywhere**, not in the element, its reason or a log;
- **DROPPED:** documented and decided out of scope: `played` (R1-D5); a group
  message or a group status (R1-D7); `value.errors`; a `field` other than
  `messages`, or an `object` other than `whatsapp_business_account` (R1-D12).

**What it does not do (step 3):** send anything, or decide Meta's answer.
OVERSIZE (R1-Q1) is step 4's, with duty 7.

**The relay's signature (duty 4):** an HMAC-SHA256 of the envelope's exact
bytes with the relay's key, `TURAB_RELAY_SIGNING_SECRET`, the same variable
TURAB reads; in `X-Turab-Relay-Signature`. No key: nothing is signed (R1-T4.4).
The key equal to Meta's app secret: refused (R1-T4.3; G7-2 (ii) makes them
distinct).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime

from turab_relay import meta

SIGNING_KEY_VARIABLE = "TURAB_RELAY_SIGNING_SECRET"
SIGNATURE_HEADER = "X-Turab-Relay-Signature"
FORWARD, ISOLATED, DROPPED = "FORWARD", "ISOLATED", "DROPPED"
OBJECT = "whatsapp_business_account"

#: §5.3: Meta's `type` -> (stored `message_type`, the content each carries).
#: Content travels only in `body_text` and `media_ref` (TURAB's
#: `OPTIONAL_CONTENT`). Any other type is OTHER, without content.
TYPES = {
    "text": ("TEXT", "text"),
    "image": ("IMAGE", "media+caption"),
    "video": ("VIDEO", "media+caption"),
    "document": ("DOCUMENT", "media+caption"),
    "audio": ("AUDIO", "media"),
    "sticker": ("STICKER", "media"),
}
OTHER = "OTHER"
#: Meta's statuses (E22) -> TURAB's (`STATUSES`); `played` is DROPPED (R1-D5).
STATUSES = {"sent": "SENT", "delivered": "DELIVERED", "read": "READ", "failed": "FAILED"}
PLAYED = "played"


@dataclass(frozen=True)
class Element:
    kind: str                       # "message", "status", "change" or "object"
    cls: str                        # FORWARD, ISOLATED or DROPPED
    reason: str                     # a fixed code, never a value of the notification
    provider_event_id: str | None = None
    envelope: bytes | None = None   # FORWARD only


class RelayKeyRefused(RuntimeError):
    pass


def signing_key() -> bytes:
    """The relay's key; refused when absent, empty, or equal to Meta's app
    secret (R1-T4.3, R1-T4.4)."""
    key = os.environ.get(SIGNING_KEY_VARIABLE)
    if not key:
        raise RelayKeyRefused(f"{SIGNING_KEY_VARIABLE} is not set: nothing is signed")
    app_secret = os.environ.get(meta.APP_SECRET_VARIABLE)
    if app_secret and hmac.compare_digest(key.encode("utf-8"), app_secret.encode("utf-8")):
        raise RelayKeyRefused(f"{SIGNING_KEY_VARIABLE} equals Meta's app secret")
    return key.encode("utf-8")


def sign(envelope: bytes, key: bytes) -> str:
    """Duty 4: the header's value, over the exact bytes sent."""
    return "sha256=" + hmac.new(key, envelope, hashlib.sha256).hexdigest()


def _serialize(envelope: dict) -> bytes:
    """The bytes sent: compact JSON, UTF-8, non-ASCII kept as UTF-8."""
    return json.dumps(envelope, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def _scoped(value) -> bool:
    """An identifier `thread_ref` can hold: a non-empty string without `:`,
    so `<business>:<customer>` matches TURAB's `SCOPED`."""
    return isinstance(value, str) and value != "" and ":" not in value


def _instant(timestamp) -> str | None:
    """Meta's Unix `timestamp` (a decimal string) as RFC 3339 in UTC."""
    if not (isinstance(timestamp, str) and timestamp.isascii() and timestamp.isdigit()):
        return None
    try:
        moment = datetime.fromtimestamp(int(timestamp), tz=UTC)
    except (OverflowError, OSError, ValueError):
        return None
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def _text(value) -> bool:
    return isinstance(value, str) and value != ""


def _content(message: dict, meta_type: str) -> tuple[str, dict]:
    """§5.3: the stored type and the content keys for one message."""
    stored, carries = TYPES.get(meta_type, (OTHER, None))
    content: dict = {}
    body = message.get(meta_type) if isinstance(message.get(meta_type), dict) else {}
    if carries == "text" and isinstance(body.get("body"), str):
        content["body_text"] = body["body"]
    if carries in ("media", "media+caption") and _text(body.get("id")):
        content["media_ref"] = body["id"]
    if carries == "media+caption" and isinstance(body.get("caption"), str):
        content["body_text"] = body["caption"]
    return stored, content


def _message(message, business: str | None, contacts) -> Element:
    if not isinstance(message, dict):
        return Element("message", ISOLATED, "MESSAGE_NOT_AN_OBJECT")
    sender, wamid, meta_type = message.get("from"), message.get("id"), message.get("type")
    if not (_text(sender) and _text(wamid) and _text(meta_type)
            and _text(message.get("timestamp"))) or business is None:
        return Element("message", ISOLATED, "MESSAGE_FIELD_MISSING")
    occurred = _instant(message.get("timestamp"))
    if occurred is None:
        return Element("message", ISOLATED, "MESSAGE_TIMESTAMP_NOT_VALID")
    if not (_scoped(sender) and _scoped(business)):
        return Element("message", ISOLATED, "IDENTIFIER_NOT_SCOPABLE")
    if contacts is not None:
        wa_ids = [c.get("wa_id") for c in contacts if isinstance(c, dict) and "wa_id" in c]
        if wa_ids and sender not in wa_ids:
            return Element("message", ISOLATED, "CONTACT_MISMATCH")
    if "group_id" in message:
        return Element("message", DROPPED, "GROUP_MESSAGE")
    stored, content = _content(message, meta_type)
    event_id = f"message:{wamid}"
    envelope = {"provider_event_id": event_id, "event_type": "message",
                "payload": {"external_message_ref": wamid,
                            "thread_ref": f"{business}:{sender}",
                            "occurred_at": occurred, "message_type": stored, **content}}
    return Element("message", FORWARD, "FORWARDED", event_id, _serialize(envelope))


def _status(status, business: str | None) -> Element:
    if not isinstance(status, dict):
        return Element("status", ISOLATED, "STATUS_NOT_AN_OBJECT")
    wamid, value, recipient = status.get("id"), status.get("status"), status.get("recipient_id")
    timestamp = status.get("timestamp")
    if not (_text(wamid) and _text(value) and _text(recipient)
            and _text(timestamp)) or business is None:
        return Element("status", ISOLATED, "STATUS_FIELD_MISSING")
    occurred = _instant(timestamp)
    if occurred is None:
        return Element("status", ISOLATED, "STATUS_TIMESTAMP_NOT_VALID")
    if not (_scoped(recipient) and _scoped(business)):
        return Element("status", ISOLATED, "IDENTIFIER_NOT_SCOPABLE")
    if status.get("recipient_type") == "group":
        return Element("status", DROPPED, "GROUP_STATUS")
    if value == PLAYED:
        return Element("status", DROPPED, "STATUS_PLAYED")
    if value not in STATUSES:
        return Element("status", ISOLATED, "STATUS_NOT_KNOWN")
    event_id = f"status:{wamid}:{value}:{timestamp}"
    envelope = {"provider_event_id": event_id, "event_type": "status",
                "payload": {"external_message_ref": wamid,
                            "thread_ref": f"{business}:{recipient}",
                            "status": STATUSES[value], "occurred_at": occurred}}
    return Element("status", FORWARD, "FORWARDED", event_id, _serialize(envelope))


def elements(raw: bytes) -> list[Element]:
    """Every element of a verified notification, in document order."""
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return [Element("object", ISOLATED, "NOTIFICATION_NOT_JSON")]
    if not isinstance(doc, dict) or doc.get("object") != OBJECT:
        return [Element("object", DROPPED, "OBJECT_NOT_WHATSAPP")]
    out: list[Element] = []
    entries = doc.get("entry") if isinstance(doc.get("entry"), list) else []
    for entry in entries:
        changes = entry.get("changes") if isinstance(entry, dict) else None
        for change in changes if isinstance(changes, list) else []:
            if not isinstance(change, dict) or change.get("field") != "messages":
                out.append(Element("change", DROPPED, "FIELD_NOT_MESSAGES"))
                continue
            value = change.get("value") if isinstance(change.get("value"), dict) else {}
            meta_data = value.get("metadata") if isinstance(value.get("metadata"), dict) else {}
            business = meta_data.get("phone_number_id")
            business = business if _text(business) else None
            contacts = value.get("contacts") if isinstance(value.get("contacts"), list) else None
            # In the order of `value`'s own keys, as received (the review of
            # `ced7df7`); `metadata` and `contacts` are read first, wherever
            # they are written.
            for key, items in value.items():
                if key not in ("errors", "messages", "statuses") or not isinstance(items, list):
                    continue
                for item in items:
                    if key == "errors":
                        out.append(Element("change", DROPPED, "VALUE_ERRORS"))
                    elif key == "messages":
                        out.append(_message(item, business, contacts))
                    else:
                        out.append(_status(item, business))
    return out
