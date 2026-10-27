"""The WhatsApp webhook: verification, the event store, its processing (Slice 7, step 3).

Ref: the contract's `postWebhooksWhatsapp` (unauthenticated, RFC-001 R10.4;
verified, R10.5), with CORRECTION-007 (500) and CORRECTION-008 (503);
`API_CONTRACTS_v0.2.md` §4.12, §8; `docs/gate/SLICE_7_PLAN.md`: G7-2 (the
boundary, T1 and T2, the replay table, the recovery), G7-3 (event types and
thread resolution), G7-4 (the identity), G7-5 (the delivery status), G7-9
(content and consent), G7-15 (the body limit), G7-16 (iv) (the thread locked
first), G7-17 (decided in the review of bf1fe3d).

**Before anything is written, in G7-17 (iii)'s order:** the body's size (400,
G7-15), then the secret (503, CORRECTION-008, G7-17 (ii)), then the relay's
signature (401), then the envelope and the keys of a known type (400). The
route reads the raw body under the limit; `verify` and `parse_envelope`
decide the rest.

**The relay's signature (G7-2 (ii), G7-17 (ii)).** `X-Turab-Relay-Signature:
sha256=<64 lowercase hex>`, the HMAC-SHA256 of the raw body under the secret
of `TURAB_RELAY_SIGNING_SECRET`, encoded UTF-8, compared in constant time
(`hmac.compare_digest`). It proves that the envelope comes from the holder of
the relay's key, unchanged. It is NOT a verification of Meta's signature: the
relay checks that, and TURAB trusts the relay for it (R-1, unmet).

**T1, the event (G7-2 (iv)).** The content-free payload of G7-9 (1) is
inserted alone and committed. A conflict on `(provider, provider_event_id)`
reads the stored status (G7-2 (v)): PROCESSED or IGNORED is a true replay
(200, nothing written, S42); RECEIVED or FAILED runs T2 again with the
replayed envelope, which carries the content again.

**T2, the processing.** READ COMMITTED, on one connection:
1. the claim, `FOR UPDATE NOWAIT` (the recovery command: `SKIP LOCKED`):
   55P03 is another processor (200, nothing written); no row is a final
   event (200);
2. `SAVEPOINT processing`;
3. resolution and its writes: the message, the thread's `last_message_at`,
   the audit rows (G7-17 (i): no `interactions` row in step 3);
4. the event's status, PROCESSED or IGNORED with its fixed code; COMMIT.
A failure inside step 3 rolls back to the savepoint, which keeps the claim's
row lock (PostgreSQL 16, §13.3), and records FAILED with `PROCESSING_FAILED`
in the same T2 (500, CORRECTION-007). A failure of step 4, of the COMMIT or
of the connection loses T2 whole: the event keeps its previous status, no
message is half-written, and the answer is the same 500.

**What an event never holds (G7-9).** `webhook_events.payload` is built from
an allow-list; the content (`body_text`, `media_ref`) and every unlisted key
are dropped before the first insert. A message's content is written only to
`communication_messages`, under the archive consent of the thread's party,
read `FOR SHARE` (`communication._archive_consent_holds`); otherwise the
message is stored without it, `content_withheld_reason: NO_ARCHIVE_CONSENT`.
No content, signature or secret reaches a log, an audit row or an answer.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from . import audit_rows, message_interactions
from .communication import MESSAGE_REF_KEY, PROVIDER, _archive_consent_holds

logger = logging.getLogger("turab.webhook")

OPERATION = "postWebhooksWhatsapp"
#: G7-15: 64 KiB, checked on Content-Length and while reading.
BODY_LIMIT = 64 * 1024
#: G7-17 (ii).
SECRET_VARIABLE = "TURAB_RELAY_SIGNING_SECRET"
SIGNATURE_HEADER = "X-Turab-Relay-Signature"
_SIGNATURE = re.compile(r"sha256=([0-9a-f]{64})")
#: G7-3's known event types and the keys each requires (G7-17 (iii)).
REQUIRED_KEYS = {
    "message": ("external_message_ref", "thread_ref", "occurred_at", "message_type"),
    "status": ("external_message_ref", "status", "occurred_at"),
}
OPTIONAL_CONTENT = ("body_text", "media_ref")
STATUSES = ("QUEUED", "SENT", "DELIVERED", "READ", "FAILED", "UNKNOWN")
#: G7-9 (1): the only keys `webhook_events.payload` ever holds.
STORED_KEYS = ("external_message_ref", "thread_ref", "occurred_at", "message_type",
               "status")
#: G7-17 (iv): the fixed codes written to `error_text`.
UNKNOWN_EVENT_TYPE = "UNKNOWN_EVENT_TYPE"
UNKNOWN_THREAD = "UNKNOWN_THREAD"
UNKNOWN_MESSAGE = "UNKNOWN_MESSAGE"
MESSAGE_REF_TAKEN = "MESSAGE_REF_TAKEN"
STATUS_TRANSITION_NOT_ACCEPTED = "STATUS_TRANSITION_NOT_ACCEPTED"
PROCESSING_FAILED = "PROCESSING_FAILED"
#: G7-5's order.
_ORDER = ("QUEUED", "SENT", "DELIVERED", "READ")


class EnvelopeRefused(Exception):
    """G7-17 (iii) steps 3 and 4: a 400 before T1, writing nothing. Its text
    names a key of the envelope, never a value the request carried."""


# --- before T1 -------------------------------------------------------------------------

def signing_secret() -> bytes | None:
    """The secret, read per request; absent or empty is None (CORRECTION-008)."""
    value = os.environ.get(SECRET_VARIABLE)
    return value.encode("utf-8") if value else None


def verify(raw: bytes, header: str | None, secret: bytes) -> bool:
    """G7-17 (ii). A header of any other form is a wrong signature."""
    match = _SIGNATURE.fullmatch(header or "")
    if match is None:
        return False
    expected = hmac.new(secret, raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, match.group(1))


#: RFC 3339 §5.6 `date-time`: the offset is required, so a time without a
#: zone is refused (G7-17 (iii)).
_RFC3339 = re.compile(
    r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}(\.\d+)?([Zz]|[+-]\d{2}:\d{2})")


def instant(value: str) -> datetime | None:
    """The instant `value` names, or None if it is not an RFC 3339 date-time."""
    if _RFC3339.fullmatch(value) is None:
        return None
    try:
        return datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True)
class Envelope:
    provider_event_id: str
    event_type: str
    payload: Mapping[str, Any]


def parse_envelope(raw: bytes) -> Envelope:
    """G7-17 (iii) steps 3 and 4: the envelope, then the keys of a known
    type. An unknown type passes, to be stored and IGNORED (G7-3)."""
    def refuse(detail: str) -> EnvelopeRefused:
        return EnvelopeRefused(detail)

    try:
        doc = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise refuse("the body is not a JSON document") from None
    if not isinstance(doc, dict):
        raise refuse("the envelope is not an object")
    event_id, event_type, payload = (doc.get("provider_event_id"), doc.get("event_type"),
                                     doc.get("payload"))
    if not (isinstance(event_id, str) and event_id):
        raise refuse("provider_event_id must be a non-empty string")
    if not isinstance(event_type, str):
        raise refuse("event_type must be a string")
    if not isinstance(payload, dict):
        raise refuse("payload must be an object")
    for key in REQUIRED_KEYS.get(event_type, ()):
        if not isinstance(payload.get(key), str):
            raise refuse(f"a {event_type} event needs {key} as a string")
    if event_type in REQUIRED_KEYS:
        if instant(payload["occurred_at"]) is None:
            raise refuse("occurred_at must be an RFC 3339 instant with a zone")
        if event_type == "status" and payload["status"] not in STATUSES:
            raise refuse("status must be one of the six delivery statuses")
        for key in OPTIONAL_CONTENT:
            if key in payload and not isinstance(payload[key], str):
                raise refuse(f"{key} must be a string")
    return Envelope(provider_event_id=event_id, event_type=event_type, payload=payload)


def content_free(envelope: Envelope) -> dict[str, Any]:
    """G7-9 (1): the event as stored. An allow-list: the content, and every
    key not listed, are dropped; two flags say that content existed."""
    kept = {k: envelope.payload[k] for k in STORED_KEYS
            if isinstance(envelope.payload.get(k), str)}
    return {"provider_event_id": envelope.provider_event_id,
            "event_type": envelope.event_type, **kept,
            "has_body": "body_text" in envelope.payload,
            "has_media": "media_ref" in envelope.payload}


def from_stored(event_type: str, stored: Mapping[str, Any]) -> tuple[Envelope, bool]:
    """The recovery command's envelope: the content-free payload, which never
    carries content. Returns it with whether content had existed."""
    payload = {k: stored[k] for k in STORED_KEYS if k in stored}
    return (Envelope(provider_event_id=stored.get("provider_event_id", ""),
                     event_type=event_type, payload=payload),
            bool(stored.get("has_body") or stored.get("has_media")))


# --- T2, step 3: resolution and its writes ---------------------------------------------

def _accepted(old: str, new: str) -> bool:
    """G7-5's table, checked before the UPDATE so an accepted flow never meets
    `0008` part B's refusal."""
    if old == "UNKNOWN":
        return new in _ORDER
    if new == "FAILED":
        return old in ("QUEUED", "SENT")
    if old in _ORDER and new in _ORDER:
        return _ORDER.index(new) > _ORDER.index(old)
    return False


def _process_message(session: Session, event_id: uuid.UUID, envelope: Envelope, *,
                     withheld_on_recovery: bool) -> tuple[str, str | None]:
    p = envelope.payload
    # G7-16 (iv): the thread, FOR UPDATE, before the message is inserted.
    thread = session.execute(text("""
        SELECT thread_id, party_id FROM turab.communication_threads
         WHERE channel = 'WHATSAPP' AND external_thread_ref = :r FOR UPDATE"""),
        {"r": p["thread_ref"]}).mappings().first()
    if thread is None:
        return "IGNORED", UNKNOWN_THREAD
    taken = session.execute(text("""
        SELECT 1 FROM turab.communication_messages
         WHERE provider = :p AND external_message_ref = :r"""),
        {"p": PROVIDER, "r": p["external_message_ref"]}).first()
    if taken is not None:
        return "IGNORED", MESSAGE_REF_TAKEN
    body, media = p.get("body_text"), p.get("media_ref")
    metadata: dict[str, Any] = {"content_archived": False,
                                "webhook_event_id": str(event_id)}
    if body is not None or media is not None:
        if _archive_consent_holds(session, thread_id=thread["thread_id"],
                                  party_id=thread["party_id"]):
            metadata["content_archived"] = True
        else:
            body = media = None
            metadata["content_withheld_reason"] = "NO_ARCHIVE_CONSENT"
    elif withheld_on_recovery:
        metadata["content_withheld_reason"] = "RECOVERED_WITHOUT_CONTENT"
    try:
        with session.begin_nested():
            message = session.execute(text("""
                INSERT INTO turab.communication_messages
                       (thread_id, provider, external_message_ref, direction, message_type,
                        body_text, media_ref, occurred_at, metadata)
                VALUES (:t, :p, :ref, 'INBOUND', :mt, :body, :media, :at,
                        CAST(:meta AS jsonb))
                RETURNING message_id"""),
                {"t": thread["thread_id"], "p": PROVIDER, "ref": p["external_message_ref"],
                 "mt": p["message_type"], "body": body, "media": media,
                 "at": instant(p["occurred_at"]), "meta": json.dumps(metadata)}).scalar_one()
    except IntegrityError as exc:
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) != \
                MESSAGE_REF_KEY:
            raise
        return "IGNORED", MESSAGE_REF_TAKEN
    audit_rows.write(session, "communication_messages", message, "INSERT", None,
                     audit_rows.row_json(session, "communication_messages", message))
    before = audit_rows.row_json(session, "communication_threads", thread["thread_id"])
    moved = session.execute(text("""
        UPDATE turab.communication_threads SET last_message_at = :at
         WHERE thread_id = :t AND (last_message_at IS NULL OR last_message_at < :at)
        RETURNING thread_id"""),
        {"t": thread["thread_id"], "at": instant(p["occurred_at"])}).first()
    if moved is not None:
        audit_rows.write(session, "communication_threads", thread["thread_id"], "UPDATE",
                         before, audit_rows.row_json(session, "communication_threads",
                                                     thread["thread_id"]))
    # G7-8 (a), G7-18 (i)-(iv): its interaction, inside the savepoint, so a
    # failure rolls it back with the message.
    message_interactions.write(session, message)
    return "PROCESSED", None


def _process_status(session: Session, envelope: Envelope) -> tuple[str, str | None]:
    p = envelope.payload
    message = session.execute(text("""
        SELECT message_id, delivery_status::text AS delivery_status
          FROM turab.communication_messages
         WHERE provider = :p AND external_message_ref = :r FOR UPDATE"""),
        {"p": PROVIDER, "r": p["external_message_ref"]}).mappings().first()
    if message is None:
        return "IGNORED", UNKNOWN_MESSAGE
    if not _accepted(message["delivery_status"], p["status"]):
        return "IGNORED", STATUS_TRANSITION_NOT_ACCEPTED
    before = audit_rows.row_json(session, "communication_messages", message["message_id"])
    session.execute(text("""
        UPDATE turab.communication_messages
           SET delivery_status = CAST(:s AS turab.delivery_status)
         WHERE message_id = :m"""), {"s": p["status"], "m": message["message_id"]})
    audit_rows.write(session, "communication_messages", message["message_id"], "UPDATE",
                     before, audit_rows.row_json(session, "communication_messages",
                                                 message["message_id"]))
    return "PROCESSED", None


def process(session: Session, event_id: uuid.UUID, envelope: Envelope, *,
            withheld_on_recovery: bool = False) -> tuple[str, str | None]:
    """T2 step 3: the event's outcome, PROCESSED or IGNORED with its code."""
    if envelope.event_type == "message":
        return _process_message(session, event_id, envelope,
                                withheld_on_recovery=withheld_on_recovery)
    if envelope.event_type == "status":
        return _process_status(session, envelope)
    return "IGNORED", UNKNOWN_EVENT_TYPE


def finish(session: Session, event_id: uuid.UUID, status: str, code: str | None) -> None:
    """T2 step 4, and the FAILED record of step 5."""
    session.execute(text("""
        UPDATE turab.webhook_events
           SET processing_status = CAST(:s AS turab.webhook_processing_status),
               processed_at = now(), error_text = :code
         WHERE webhook_event_id = :e"""), {"s": status, "code": code, "e": event_id})


# --- T1 and T2 --------------------------------------------------------------------------

#: The audit context of the operator recovery command's transactions.
RECOVERY = "recoverWebhookEvents"
#: G7-2 (v): a RECEIVED event older than this is stuck.
RECOVERY_DELAY_SECONDS = 300


def _transaction(session: Session, trace_id: str, operation: str = OPERATION):
    from ..db.session import audited_transaction

    return audited_transaction(session, None, {"operation": operation, "trace_id": trace_id},
                               require_actor=False)


def store(session: Session, envelope: Envelope, trace_id: str) -> tuple[uuid.UUID, str]:
    """T1. Returns the event and its status: RECEIVED if new, else the stored
    status (G7-2 (v))."""
    with _transaction(session, trace_id) as s:
        created = s.execute(text("""
            INSERT INTO turab.webhook_events (provider, provider_event_id, event_type, payload)
            VALUES (:p, :e, :t, CAST(:payload AS jsonb))
            ON CONFLICT (provider, provider_event_id) DO NOTHING
            RETURNING webhook_event_id"""),
            {"p": PROVIDER, "e": envelope.provider_event_id, "t": envelope.event_type,
             "payload": json.dumps(content_free(envelope))}).scalar_one_or_none()
        if created is not None:
            return created, "RECEIVED"
        row = s.execute(text("""
            SELECT webhook_event_id, processing_status::text AS status
              FROM turab.webhook_events WHERE provider = :p AND provider_event_id = :e"""),
            {"p": PROVIDER, "e": envelope.provider_event_id}).mappings().one()
        return row["webhook_event_id"], row["status"]


def run_t2(session: Session, event_id: uuid.UUID, envelope: Envelope, trace_id: str, *,
           skip_locked: bool = False, withheld_on_recovery: bool = False,
           operation: str = OPERATION) -> str:
    """T2. Returns the outcome: PROCESSED, IGNORED, FAILED, IN_FLIGHT (55P03,
    or a row SKIP LOCKED passed over) or FINAL (no claimable row). An
    exception from step 4 or the COMMIT propagates: T2 is then lost whole."""
    lock = "FOR UPDATE SKIP LOCKED" if skip_locked else "FOR UPDATE NOWAIT"
    try:
        with _transaction(session, trace_id, operation) as s:
            claimed = s.execute(text(f"""
                SELECT webhook_event_id FROM turab.webhook_events
                 WHERE webhook_event_id = :e
                   AND processing_status IN ('RECEIVED', 'FAILED') {lock}"""),
                {"e": event_id}).first()
            if claimed is None:
                if not skip_locked:
                    return "FINAL"
                still = s.execute(text("""
                    SELECT 1 FROM turab.webhook_events WHERE webhook_event_id = :e
                       AND processing_status IN ('RECEIVED', 'FAILED')"""),
                    {"e": event_id}).first()
                return "IN_FLIGHT" if still is not None else "FINAL"
            savepoint = s.begin_nested()
            try:
                status, code = process(s, event_id, envelope,
                                       withheld_on_recovery=withheld_on_recovery)
            except Exception as exc:
                savepoint.rollback()
                # The cause stays on the server, under the trace id; never the
                # body, never the exception's text in the event.
                logger.error("webhook processing failed",
                             extra={"trace_id": trace_id, "webhook_event_id": str(event_id),
                                    "cause": type(exc).__name__})
                finish(s, event_id, "FAILED", PROCESSING_FAILED)
                return "FAILED"
            savepoint.commit()
            finish(s, event_id, status, code)
            return status
    except DBAPIError as exc:
        if getattr(exc.orig, "sqlstate", None) == "55P03":
            return "IN_FLIGHT"
        raise


def recover(session: Session, trace_id: str, *,
            delay_seconds: int = RECOVERY_DELAY_SECONDS) -> dict[str, int]:
    """G7-2 (v), the operator recovery command: T2 again on every event
    RECEIVED for longer than `delay_seconds`, and on every FAILED one,
    skipping a row another processor holds (`FOR UPDATE SKIP LOCKED`).

    **Its limit, accepted in the review of `58a0067`:** it recovers from the
    content-free payload, so a message whose content existed is stored
    without it (`RECOVERED_WITHOUT_CONTENT`). It is not a full recovery of the
    archive. Returns the count of each outcome; it reports nothing else.
    """
    with session.begin():
        rows = session.execute(text("""
            SELECT webhook_event_id, event_type, payload
              FROM turab.webhook_events
             WHERE provider = :p
               AND (processing_status = 'FAILED'
                    OR (processing_status = 'RECEIVED'
                        AND received_at < now() - make_interval(secs => :d)))
             ORDER BY received_at, webhook_event_id"""),
            {"p": PROVIDER, "d": delay_seconds}).mappings().all()
    outcomes: dict[str, int] = {}
    for row in rows:
        envelope, had_content = from_stored(row["event_type"], row["payload"])
        try:
            outcome = run_t2(session, row["webhook_event_id"], envelope, trace_id,
                             skip_locked=True, withheld_on_recovery=had_content,
                             operation=RECOVERY)
        except Exception as exc:
            logger.error("webhook recovery lost",
                         extra={"trace_id": trace_id,
                                "webhook_event_id": str(row["webhook_event_id"]),
                                "cause": type(exc).__name__})
            outcome = "PROCESSING_LOST"
        outcomes[outcome] = outcomes.get(outcome, 0) + 1
    return outcomes


class WebhookService:
    """The application service the webhook route talks to; it holds the
    session, so the route holds none. Its transactions run actor-less
    (`require_actor=False`): the webhook has no account, and the audit rows it
    writes carry a NULL actor and the context `postWebhooksWhatsapp`
    (G7-17 (vii)). The two transactions are two calls, so the route can tell
    an event never stored (no CORRECTION-007) from one stored and not
    processed (CORRECTION-007)."""

    def __init__(self, session: Session, auditor: Any, trace_id: str) -> None:
        self._session = session
        self._auditor = auditor
        self._trace_id = trace_id

    def store(self, envelope: Envelope) -> tuple[uuid.UUID, str]:
        """T1."""
        return store(self._session, envelope, self._trace_id)

    def process(self, event_id: uuid.UUID, envelope: Envelope) -> str:
        """T2. Its exceptions are T2 lost whole."""
        return run_t2(self._session, event_id, envelope, self._trace_id)

    def answered(self, status: int, outcome: str,
                 event_id: uuid.UUID | None = None) -> None:
        """G7-17 (vii): the one access record of this answer."""
        self._auditor.webhook_answered(trace_id=self._trace_id, status=status,
                                       outcome=outcome, webhook_event_id=event_id)
