"""Communication record: the staff thread and the staff message (Slice 7, step 2).

Ref: the contract's `postCommunicationThreads` and
`postCommunicationThreadsThreadIdMessages` (ADMIN, OPERATOR; Idempotency-Key),
the former narrowed by CORRECTION-006; `API_CONTRACTS_v0.2.md` §4.12;
`docs/gate/SLICE_7_PLAN.md` revision 8: G7-3, G7-4, G7-6, G7-7, G7-9, G7-11,
G7-16 (decided in the review of 0f423d2); migration `0008`.

**Every refusal comes before any write.** `prepare_thread` and
`prepare_message` run before the idempotency claim (G4-15 D6) and only read
and lock, so a refusal writes no row, no audit row, and consumes no key. Two
refusals can only be met at the INSERT, when a concurrent command took the
same reference between the check and the write; they are raised there, after
the claim, and the command's one transaction rolls back with them, the claim
included.

**The thread (G7-6, G7-3, CORRECTION-006).** `party_id` is required (the
contract, as corrected). In this order:
1. a WHATSAPP reference has the form `<scope>:<id>` (422 THREAD_REF_NOT_SCOPED);
2. every id names a row (422 LINKED_RECORD_NOT_FOUND, rule 4);
3. a named opportunity is of a SALE: its approved match's evaluated offer is a
   SALE offer and its request's intent is BUY (422 OPPORTUNITY_NOT_SALE,
   rule 0). Checked, not assumed;
4. the links agree (422 THREAD_LINKS_INCONSISTENT, rules 1-3);
5. no WHATSAPP thread holds the reference (409 THREAD_REF_TAKEN).
The opportunity is read `FOR SHARE`, so its current offer, and with it its
seller, cannot change before the thread commits.

**The message (G7-4, G7-9, G7-16).** In this order:
1. the body alone: INBOUND refused (G7-16 (i)); `metadata` empty or absent
   (iii); `PHONE_DECISION` and `CONFIRMATION_LINK` reserved for step 4 (v); an
   INTERNAL message states no delivery status but UNKNOWN (ii) and carries no
   reference (G7-4);
2. **the thread, `FOR UPDATE`, as the FIRST statement on it** (G7-16 (iv)): two
   messages on one thread serialize here, so `last_message_at` moves to the
   later of the two whatever their order of commit;
3. a reference needs a WHATSAPP thread, whose provider is `whatsapp`, set
   here (G7-4); a reference already recorded is 409 MESSAGE_REF_TAKEN;
4. content (`body_text` or `media_ref`) needs the archive consent of the
   thread's party, read `FOR SHARE` (G7-9 (3)).

**The consent, as it actually holds (G7-9 (3)).** A row of
`resource_consent_bindings` bound to the thread for COMMUNICATION_ARCHIVE,
unrevoked, whose grant is the thread party's, of scope COMMUNICATION_ARCHIVE
and GRANTED, read `FOR SHARE OF b, g`. A revocation is an UPDATE of the grant
(`consent.revoke_consent`), which conflicts with FOR SHARE (PostgreSQL 16,
§13.3.2, Table 13.3): a revocation committing meanwhile is waited for, and
READ COMMITTED then re-checks the row, which no longer qualifies (§13.2.1).
A binding being created is serialized with the message by the thread row:
the binding's INSERT checks `fk_consent_binding_thread` with FOR KEY SHARE on
the thread, which conflicts with the message's FOR UPDATE (Table 13.3).
- A binding inserted and not yet committed makes the message wait at its
  thread lock. Once it commits, the consent check, a later statement under
  READ COMMITTED, sees it and the content is archived; rolled back, the
  message is refused.
- A message holding the thread makes a new binding wait until the message's
  transaction ends; the message does not see it.
Measured through both commands (R-S7-2-01, review of f7e5297;
`evidence/SLICE7-STEP2-R-S7-2-01.txt`). An earlier version of this text said
the binding table had no foreign key to the thread and that a binding in
flight was not waited for; that was wrong.

**What a message never writes (G7-9, G7-11).** `metadata` holds
`content_archived` only, written here. The audit row withholds `body_text`
and `media_ref`. No content reaches a log or a refusal.
"""
from __future__ import annotations

import json
import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import audit_rows

#: The form `ck_whatsapp_thread_ref_scoped` (migration 0008, part E) enforces.
SCOPED = re.compile(r"^[^:]+:[^:]+$")
#: G7-4: the one provider defined, for WHATSAPP threads only.
PROVIDER = "whatsapp"
#: G7-16 (v): given their meaning by G7-10, in step 4.
RESERVED_TYPES = ("PHONE_DECISION", "CONFIRMATION_LINK")
#: The unique index of migration 0008, part E, and the frozen identity key.
THREAD_REF_INDEX = "ux_whatsapp_thread_ref"
MESSAGE_REF_KEY = "communication_messages_provider_external_message_ref_key"


class CommunicationRefused(Exception):
    """A typed refusal. `code` is a `ProblemCode` name; the route maps it.
    The detail and `field_errors` name fields, never an id, a reference or
    database text (G7-16 (vi))."""

    def __init__(self, code: str, detail: str,
                 field_errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.field_errors = field_errors


def _constraint(exc: IntegrityError) -> str | None:
    return getattr(getattr(exc.orig, "diag", None), "constraint_name", None)


# --- postCommunicationThreads ---------------------------------------------------------

@dataclass(frozen=True)
class PreparedThread:
    channel: str
    party_id: uuid.UUID
    request_id: uuid.UUID | None
    property_id: uuid.UUID | None
    opportunity_id: uuid.UUID | None
    external_thread_ref: str | None


_EXISTS = {
    "party_id": "SELECT 1 FROM turab.parties WHERE party_id = :v",
    "request_id": "SELECT 1 FROM turab.requests WHERE request_id = :v",
    "property_id": "SELECT 1 FROM turab.properties WHERE property_id = :v",
    "opportunity_id": "SELECT 1 FROM turab.opportunities WHERE opportunity_id = :v",
}


def _field(field: str, code: str, message: str) -> dict[str, str]:
    return {"field": field, "code": code, "message": message}


def prepare_thread(session: Session, *, channel: str, party_id: uuid.UUID,
                   request_id: uuid.UUID | None, property_id: uuid.UUID | None,
                   opportunity_id: uuid.UUID | None,
                   external_thread_ref: str | None) -> PreparedThread:
    """Every check of G7-6 and G7-3, read-only, before the idempotency claim."""
    if (channel == "WHATSAPP" and external_thread_ref is not None
            and not SCOPED.match(external_thread_ref)):
        raise CommunicationRefused(
            "THREAD_REF_NOT_SCOPED",
            "a WHATSAPP thread reference has the form <scope>:<id>",
            [_field("external_thread_ref", "NOT_SCOPED", "must be <scope>:<id>")])

    given = {"party_id": party_id, "request_id": request_id, "property_id": property_id,
             "opportunity_id": opportunity_id}
    missing = [f for f, v in given.items() if v is not None
               and session.execute(text(_EXISTS[f]), {"v": v}).first() is None]
    if missing:
        raise CommunicationRefused(
            "LINKED_RECORD_NOT_FOUND", "a linked record does not exist",
            [_field(f, "NOT_FOUND", "names no record") for f in missing])

    inconsistent: list[dict[str, str]] = []
    if opportunity_id is not None:
        opp = session.execute(text("""
            SELECT o.request_id, o.property_id, r.party_id AS buyer,
                   co.party_id AS seller,
                   r.transaction_intent::text AS intent,
                   eo.transaction_type::text AS evaluated_type
              FROM turab.opportunities o
              JOIN turab.requests r ON r.request_id = o.request_id
              JOIN turab.match_candidates m ON m.match_id = o.approved_match_id
              LEFT JOIN turab.property_offers eo ON eo.offer_id = m.evaluated_offer_id
              LEFT JOIN turab.property_offers co ON co.offer_id = o.current_offer_id
             WHERE o.opportunity_id = :o
               FOR SHARE OF o"""), {"o": opportunity_id}).mappings().one()
        if not (opp["evaluated_type"] == "SALE" and opp["intent"] == "BUY"):
            raise CommunicationRefused(
                "OPPORTUNITY_NOT_SALE", "the opportunity is not of a SALE",
                [_field("opportunity_id", "NOT_SALE", "is not a SALE opportunity")])
        if request_id is not None and request_id != opp["request_id"]:
            inconsistent.append(_field("request_id", "NOT_THE_OPPORTUNITYS_REQUEST",
                                       "is not the opportunity's request"))
        if property_id is not None and property_id != opp["property_id"]:
            inconsistent.append(_field("property_id", "NOT_THE_OPPORTUNITYS_PROPERTY",
                                       "is not the opportunity's property"))
        if party_id not in {opp["buyer"], opp["seller"]} - {None}:
            inconsistent.append(_field("party_id", "NOT_A_PARTY_OF_THE_OPPORTUNITY",
                                       "is neither the opportunity's buyer nor its seller"))
    else:
        if request_id is not None:
            buyer = session.execute(text(
                "SELECT party_id FROM turab.requests WHERE request_id = :r"),
                {"r": request_id}).scalar_one()
            if party_id != buyer:
                inconsistent.append(_field("party_id", "NOT_THE_REQUESTS_PARTY",
                                           "is not the request's party"))
        if property_id is not None:
            offered = session.execute(text("""
                SELECT 1 FROM turab.property_offers
                 WHERE property_id = :p AND party_id = :party LIMIT 1"""),
                {"p": property_id, "party": party_id}).first()
            if offered is None:
                inconsistent.append(_field("party_id", "NOT_A_PARTY_OF_THE_PROPERTYS_OFFERS",
                                           "is not the party of an offer of the property"))
    if inconsistent:
        raise CommunicationRefused("THREAD_LINKS_INCONSISTENT",
                                   "the thread's links do not agree", inconsistent)

    if channel == "WHATSAPP" and external_thread_ref is not None:
        _refuse_taken_thread_ref(session, external_thread_ref)
    return PreparedThread(channel=channel, party_id=party_id, request_id=request_id,
                          property_id=property_id, opportunity_id=opportunity_id,
                          external_thread_ref=external_thread_ref)


def _refuse_taken_thread_ref(session: Session, ref: str) -> None:
    taken = session.execute(text("""
        SELECT 1 FROM turab.communication_threads
         WHERE channel = 'WHATSAPP' AND external_thread_ref = :r"""), {"r": ref}).first()
    if taken is not None:
        raise CommunicationRefused("THREAD_REF_TAKEN",
                                   "a WHATSAPP thread already holds this reference")


def record_thread(session: Session, prepared: PreparedThread, *,
                  created_by_account_id: uuid.UUID) -> dict[str, Any]:
    """The INSERT, after the claim. A reference taken by a concurrent command
    since `prepare_thread` is refused by the index (0008, part E) and answered
    as the same 409; the transaction rolls back with it."""
    try:
        with session.begin_nested():
            row = session.execute(text("""
                INSERT INTO turab.communication_threads
                       (channel, party_id, request_id, property_id, opportunity_id,
                        external_thread_ref, created_by_account_id)
                VALUES (CAST(:c AS turab.communication_channel), :party, :req, :prop, :opp,
                        :ref, :acct)
                RETURNING thread_id, opened_at"""),
                {"c": prepared.channel, "party": prepared.party_id,
                 "req": prepared.request_id, "prop": prepared.property_id,
                 "opp": prepared.opportunity_id, "ref": prepared.external_thread_ref,
                 "acct": created_by_account_id}).mappings().one()
    except IntegrityError as exc:
        if _constraint(exc) != THREAD_REF_INDEX:
            raise
        raise CommunicationRefused("THREAD_REF_TAKEN",
                                   "a WHATSAPP thread already holds this reference") from None
    audit_rows.write(session, "communication_threads", row["thread_id"], "INSERT", None,
                     audit_rows.row_json(session, "communication_threads", row["thread_id"]))
    return {"thread_id": str(row["thread_id"]),
            "opened_at": row["opened_at"].isoformat()}


# --- postCommunicationThreadsThreadIdMessages ------------------------------------------

@dataclass(frozen=True)
class PreparedMessage:
    thread_id: uuid.UUID
    provider: str | None
    external_message_ref: str | None
    direction: str
    message_type: str
    body_text: str | None
    media_ref: str | None
    delivery_status: str
    occurred_at: datetime
    content_archived: bool


def check_message_body(*, direction: str, delivery_status: str | None,
                       metadata: Mapping[str, Any] | None, message_type: str,
                       external_message_ref: str | None) -> None:
    """The rules that read the body alone (G7-16 (i), (ii), (iii), (v); G7-4)."""
    if direction == "INBOUND":
        raise CommunicationRefused(
            "DIRECTION_NOT_ACCEPTED",
            "staff record OUTBOUND and INTERNAL messages; inbound ones come from the webhook",
            [_field("direction", "NOT_ACCEPTED", "INBOUND is not accepted here")])
    if metadata:
        raise CommunicationRefused(
            "MESSAGE_METADATA_NOT_ACCEPTED", "a staff message carries no metadata",
            [_field("metadata", "NOT_ACCEPTED", "must be absent or empty")])
    if message_type in RESERVED_TYPES:
        raise CommunicationRefused(
            "MESSAGE_TYPE_RESERVED", "this message type is not yet accepted",
            [_field("message_type", "RESERVED", "is reserved")])
    if direction == "INTERNAL" and delivery_status not in (None, "UNKNOWN"):
        raise CommunicationRefused(
            "DELIVERY_STATUS_NOT_ACCEPTED", "an INTERNAL message has no delivery status",
            [_field("delivery_status", "NOT_ACCEPTED", "must be absent or UNKNOWN")])
    if direction == "INTERNAL" and external_message_ref is not None:
        raise CommunicationRefused(
            "INTERNAL_MESSAGE_REF_NOT_ACCEPTED", "an INTERNAL message has no reference",
            [_field("external_message_ref", "NOT_ACCEPTED", "must be absent")])


def _archive_consent_holds(session: Session, *, thread_id: uuid.UUID,
                           party_id: uuid.UUID | None) -> bool:
    if party_id is None:
        return False
    return session.execute(text("""
        SELECT 1
          FROM turab.resource_consent_bindings b
          JOIN turab.consent_grants g ON g.consent_id = b.consent_id
         WHERE b.thread_id = :t
           AND b.purpose = 'COMMUNICATION_ARCHIVE'
           AND g.scope = 'COMMUNICATION_ARCHIVE'
           AND b.revoked_at IS NULL
           AND g.party_id = :party
           AND g.status = 'GRANTED'
         ORDER BY b.consent_binding_id
           FOR SHARE OF b, g"""), {"t": thread_id, "party": party_id}).first() is not None


def prepare_message(session: Session, *, thread_id: uuid.UUID, direction: str,
                    delivery_status: str | None, metadata: Mapping[str, Any] | None,
                    message_type: str, external_message_ref: str | None,
                    body_text: str | None, media_ref: str | None,
                    occurred_at: datetime) -> PreparedMessage:
    """Steps 1-4, before the idempotency claim; the locks are held to commit."""
    check_message_body(direction=direction, delivery_status=delivery_status,
                       metadata=metadata, message_type=message_type,
                       external_message_ref=external_message_ref)
    thread = session.execute(text("""
        SELECT channel::text AS channel, party_id
          FROM turab.communication_threads WHERE thread_id = :t FOR UPDATE"""),
        {"t": thread_id}).mappings().first()
    if thread is None:
        # The route checked existence first, and 0008 refuses a thread's
        # DELETE; the same answer, kept in case it is reached.
        raise CommunicationRefused("OBJECT_NOT_AUTHORIZED", "not an available thread")
    provider = None
    if external_message_ref is not None:
        if thread["channel"] != "WHATSAPP":
            raise CommunicationRefused(
                "EXTERNAL_REF_WITHOUT_PROVIDER",
                "no provider is defined for this thread's channel",
                [_field("external_message_ref", "NO_PROVIDER",
                        "is accepted in a WHATSAPP thread only")])
        provider = PROVIDER
        _refuse_taken_message_ref(session, external_message_ref)
    has_content = body_text is not None or media_ref is not None
    if has_content and not _archive_consent_holds(session, thread_id=thread_id,
                                                  party_id=thread["party_id"]):
        raise CommunicationRefused(
            "CONTENT_NOT_ARCHIVABLE",
            "the thread's party has no archive consent for this thread; send the "
            "message without content")
    return PreparedMessage(
        thread_id=thread_id, provider=provider, external_message_ref=external_message_ref,
        direction=direction, message_type=message_type, body_text=body_text,
        media_ref=media_ref,
        delivery_status=(delivery_status or "UNKNOWN") if direction == "OUTBOUND"
        else "UNKNOWN",
        occurred_at=occurred_at, content_archived=has_content)


def _refuse_taken_message_ref(session: Session, ref: str) -> None:
    taken = session.execute(text("""
        SELECT 1 FROM turab.communication_messages
         WHERE provider = :p AND external_message_ref = :r"""),
        {"p": PROVIDER, "r": ref}).first()
    if taken is not None:
        raise CommunicationRefused("MESSAGE_REF_TAKEN",
                                   "this provider message is already recorded")


def record_message(session: Session, prepared: PreparedMessage, *,
                   sent_by_account_id: uuid.UUID) -> dict[str, Any]:
    """The message, then the thread's `last_message_at`, after the claim, in
    the command's one transaction. Both writes are audited, the content
    withheld (G7-11)."""
    try:
        with session.begin_nested():
            row = session.execute(text("""
                INSERT INTO turab.communication_messages
                       (thread_id, provider, external_message_ref, direction, message_type,
                        body_text, media_ref, delivery_status, occurred_at,
                        sent_by_account_id, metadata)
                VALUES (:t, :p, :ref, CAST(:d AS turab.message_direction), :mt, :body,
                        :media, CAST(:ds AS turab.delivery_status), :at, :acct,
                        CAST(:meta AS jsonb))
                RETURNING message_id, delivery_status::text AS delivery_status"""),
                {"t": prepared.thread_id, "p": prepared.provider,
                 "ref": prepared.external_message_ref, "d": prepared.direction,
                 "mt": prepared.message_type, "body": prepared.body_text,
                 "media": prepared.media_ref, "ds": prepared.delivery_status,
                 "at": prepared.occurred_at, "acct": sent_by_account_id,
                 "meta": json.dumps({"content_archived": prepared.content_archived})},
            ).mappings().one()
    except IntegrityError as exc:
        if _constraint(exc) != MESSAGE_REF_KEY:
            raise
        raise CommunicationRefused("MESSAGE_REF_TAKEN",
                                   "this provider message is already recorded") from None
    audit_rows.write(session, "communication_messages", row["message_id"], "INSERT", None,
                     audit_rows.row_json(session, "communication_messages", row["message_id"]))
    before = audit_rows.row_json(session, "communication_threads", prepared.thread_id)
    moved = session.execute(text("""
        UPDATE turab.communication_threads SET last_message_at = :at
         WHERE thread_id = :t AND (last_message_at IS NULL OR last_message_at < :at)
        RETURNING thread_id"""),
        {"t": prepared.thread_id, "at": prepared.occurred_at}).first()
    if moved is not None:
        audit_rows.write(session, "communication_threads", prepared.thread_id, "UPDATE",
                         before, audit_rows.row_json(session, "communication_threads",
                                                     prepared.thread_id))
    return {"message_id": str(row["message_id"]),
            "delivery_status": row["delivery_status"]}
