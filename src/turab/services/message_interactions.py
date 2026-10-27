"""One `interactions` row per message, and the backfill (Slice 7, step 4).

Ref: `docs/gate/SLICE_7_PLAN.md` G7-8 (a), G7-11, G7-17 (i), and G7-18
(i)-(v) and (ix), decided in the review of e18271a.

**The row** (G7-18 (i)-(iii)):
- `interaction_type`: `NOTE` for every INTERNAL message; otherwise by the
  thread's channel (`TYPE_BY_CHANNEL`), `OTHER` for WEB and OTHER;
- `channel`, `party_id`, `request_id`, `property_id`, `opportunity_id`,
  `thread_id`: the thread's (its links are frozen, G7-12 (D));
- `summary`: a fixed text per direction (`SUMMARY_BY_DIRECTION`), naming no
  content and no reference; `outcome_code` NULL;
- `occurred_at`: the message's; `operator_account_id`: the message's
  `sent_by_account_id` (NULL for the webhook);
- `metadata`: exactly `{"message_id": "<uuid>"}`;
- audited by `audit_rows`, with the transaction's actor and context; the
  summary is withheld there as for every interaction (review of 6c6e614).

**One row per message: where the guarantee lives** (G7-18 (iv)). In the
service's paths, not in the database: the two writers of a message (the staff
command and the webhook's T2) call `write` in the message's own transaction,
and the backfill writes only for a message that has none. **It is not a
uniqueness constraint of the database** (no `0009`, review of e18271a): a
statement outside the service could write a second row.

**The backfill** (G7-18 (v)): `backfill`, run by
`db/ops/backfill_message_interactions.py`. One transaction, READ COMMITTED,
actor-less, under a transaction-level advisory lock taken by its first
statement: a second backfill waits for the first to end, then its next
statement reads what the first committed. A message committed before the
backfill's selection already has its interaction; one not yet committed is
invisible to it and brings its own. **For the messages that existed before
step 4, the atomicity of a message with its interaction does not hold
retroactively:** their interaction is written later, by the backfill; its
`created_at` is the backfill's time, its `occurred_at` the message's.
"""
from __future__ import annotations

import json
import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import audit_rows

#: G7-18 (i). INTERNAL is NOTE in any channel.
TYPE_BY_CHANNEL = {
    "WHATSAPP": "WHATSAPP", "PHONE": "CALL", "SMS": "SMS", "EMAIL": "EMAIL",
    "IN_PERSON": "IN_PERSON", "WEB": "OTHER", "OTHER": "OTHER",
}
#: G7-18 (ii).
SUMMARY_BY_DIRECTION = {
    "INBOUND": "Inbound message", "OUTBOUND": "Outbound message",
    "INTERNAL": "Internal note",
}
#: The audit context of the backfill's transaction.
BACKFILL = "backfillMessageInteractions"
#: The advisory lock's key: one backfill at a time (G7-18 (iv)).
BACKFILL_LOCK = 7_018_004


def interaction_type(direction: str, channel: str) -> str:
    return "NOTE" if direction == "INTERNAL" else TYPE_BY_CHANNEL[channel]


def write(session: Session, message_id: uuid.UUID) -> uuid.UUID:
    """The message's interaction, in the caller's transaction, audited."""
    m = session.execute(text("""
        SELECT m.direction::text AS direction, m.occurred_at, m.sent_by_account_id,
               t.thread_id, t.channel::text AS channel, t.party_id, t.request_id,
               t.property_id, t.opportunity_id
          FROM turab.communication_messages m
          JOIN turab.communication_threads t ON t.thread_id = m.thread_id
         WHERE m.message_id = :m"""), {"m": message_id}).mappings().one()
    interaction = session.execute(text("""
        INSERT INTO turab.interactions
               (interaction_type, channel, party_id, request_id, property_id,
                opportunity_id, thread_id, summary, occurred_at, operator_account_id,
                metadata)
        VALUES (CAST(:type AS turab.interaction_type),
                CAST(:channel AS turab.communication_channel), :party, :request,
                :property, :opportunity, :thread, :summary, :at, :operator,
                CAST(:meta AS jsonb))
        RETURNING interaction_id"""),
        {"type": interaction_type(m["direction"], m["channel"]), "channel": m["channel"],
         "party": m["party_id"], "request": m["request_id"], "property": m["property_id"],
         "opportunity": m["opportunity_id"], "thread": m["thread_id"],
         "summary": SUMMARY_BY_DIRECTION[m["direction"]], "at": m["occurred_at"],
         "operator": m["sent_by_account_id"],
         "meta": json.dumps({"message_id": str(message_id)})}).scalar_one()
    audit_rows.write(session, "interactions", interaction, "INSERT", None,
                     audit_rows.row_json(session, "interactions", interaction))
    return interaction


def backfill(session: Session, trace_id: str) -> int:
    """G7-18 (v): an interaction for every message that has none. Returns how
    many were written; a re-run writes none."""
    from ..db.session import audited_transaction

    with audited_transaction(session, None, {"operation": BACKFILL, "trace_id": trace_id},
                             require_actor=False) as s:
        s.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": BACKFILL_LOCK})
        missing = s.execute(text("""
            SELECT m.message_id FROM turab.communication_messages m
             WHERE NOT EXISTS (
                   SELECT 1 FROM turab.interactions i
                    WHERE i.metadata->>'message_id' = m.message_id::text)
             ORDER BY m.occurred_at, m.message_id""")).scalars().all()
        for message_id in missing:
            write(s, message_id)
        return len(missing)
