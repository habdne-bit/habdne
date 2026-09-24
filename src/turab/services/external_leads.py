"""SOURCE: external leads — Slice 3, step 3 (plan §1.5).

Ref: the effective contract's `ExternalLeadCreate`, `postExternalLeads`,
`postExternalLeadsLeadIdConvert`, `getBackofficeQueuesExternalLeads`;
API_CONTRACTS_v0.2 §4.3; Developer Reference Spec §5.5;
`docs/gate/G3-10_external_lead_conversion.md`.

**Why these are in Slice 3 at all.** `ExternalLeadCreate` is the ONLY
declared shape that creates a `sources` row (plan §1.5), and step 2's offer
source links need a source to exist. So capture is delivered here. The
acquisition WORKFLOW — contact attempts, consent capture, assisted entry —
is Slice 8 in IMPLEMENTATION_SLICES_v0.2.md, and the contract declares no
operation that records a contact attempt or moves a lead between its ten
statuses.

What that means for each operation:

  * **capture** is fully determined: a discovery record, never inventory
    (§4.3 "It is not an active REQUEST or PROPERTY");
  * **convert** is REFUSED with a typed error naming what is undecided
    (plan §7 condition 1). See `ConversionUndecided`;
  * **the queue** lists leads with the choices recorded in G3-10 §3, each of
    which is reversible and none of which writes anything.
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import audit_rows

LEAD_KINDS = ("PROPERTY", "REQUEST")
SOURCE_KINDS = (
    "USER_FORM", "EMPLOYEE_ENTRY", "FACEBOOK_POST", "OUEDKNISS_POST",
    "OTHER_WEB_POST", "WHATSAPP", "PHONE_CALL", "IN_PERSON", "BROKER",
    "DOCUMENT", "IMPORT", "OTHER",
)

#: Statuses after which a lead needs no further action. Listed rather than
#: inferred so the queue's filter is a stated rule (G3-10 §3, Q-3).
CLOSED_STATUSES = frozenset({"CONVERTED", "DECLINED", "CLOSED"})


class LeadError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(detail)


class LeadNotFound(LeadError):
    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "no such external lead")


class ConversionUndecided(LeadError):
    """Conversion is refused until the rules in G3-10 are decided.

    The contract permits it "only after contact/consent/data gates", but:

      * no operation records contact, so the contact gate has no input;
      * a PROPERTY conversion would need a property-scoped consent binding,
        which the database refuses without an active party–property relation
        — and inferring a relation from a conversion is forbidden;
      * `payload` is an open object whose mapping onto `RequestCreate` /
        `PropertyCreate` is not declared.

    Choosing answers to those here would be deciding a workflow in code.
    """

    def __init__(self) -> None:
        super().__init__(
            "EXTERNAL_LEAD_CONVERSION_UNDECIDED",
            "converting an external lead is not available in this version: its "
            "contact gate, its consent binding (for a PROPERTY, a binding the "
            "database refuses without a party-property relation) and its "
            "payload mapping are undecided (G3-10)",
        )


def capture(
    session: Session,
    *,
    lead_kind: str,
    source: Mapping[str, Any],
    raw_payload: Mapping[str, Any] | None,
    created_by_account_id: uuid.UUID,
) -> Mapping[str, Any]:
    """Write one `sources` row and one `external_leads` row, `DISCOVERED`.

    Nothing else: no party, no request, no property, no relation. A discovery
    is a record that something was seen, not a statement about who owns what.
    """
    source_id = session.execute(
        text(
            """INSERT INTO turab.sources
                      (kind, external_url, external_ref, title, raw_text,
                       captured_at, metadata, created_by_account_id)
               VALUES (CAST(:kind AS turab.source_kind), :url, :ref, :title, :raw,
                       :captured, CAST(:metadata AS jsonb), :account)
            RETURNING source_id"""
        ),
        {
            "kind": source["kind"],
            "url": source.get("external_url"),
            "ref": source.get("external_ref"),
            "title": source.get("title"),
            "raw": source.get("raw_text"),
            "captured": source.get("captured_at"),
            "metadata": json.dumps(source.get("metadata") or {}),
            "account": created_by_account_id,
        },
    ).scalar_one()
    lead_id = session.execute(
        text(
            """INSERT INTO turab.external_leads
                      (lead_kind, source_id, raw_payload, created_by_account_id)
               VALUES (CAST(:kind AS turab.external_lead_kind), :source,
                       CAST(:payload AS jsonb), :account)
            RETURNING external_lead_id"""
        ),
        {"kind": lead_kind, "source": source_id,
         "payload": json.dumps(raw_payload or {}), "account": created_by_account_id},
    ).scalar_one()

    audit_rows.write(session, "sources", source_id, "INSERT", None,
                     audit_rows.row_json(session, "sources", source_id))
    audit_rows.write(session, "external_leads", lead_id, "INSERT", None,
                     audit_rows.row_json(session, "external_leads", lead_id))
    return read(session, lead_id)


def read(session: Session, lead_id: uuid.UUID) -> Mapping[str, Any]:
    row = session.execute(
        text("""SELECT external_lead_id, lead_kind::text AS lead_kind,
                       status::text AS status, source_id, discovered_at
                  FROM turab.external_leads WHERE external_lead_id = :l"""),
        {"l": lead_id},
    ).mappings().first()
    if row is None:
        raise LeadNotFound()
    return row


def refuse_conversion(session: Session, lead_id: uuid.UUID) -> None:
    """404 for an unknown lead; otherwise the typed undecided refusal."""
    read(session, lead_id)
    raise ConversionUndecided()


def queue(session: Session) -> list[Mapping[str, Any]]:
    """Leads still needing action, oldest first, id as the tie-break.

    Deterministic by construction (the contract's own requirement): the order
    is total because `external_lead_id` is unique.
    """
    return session.execute(
        text("""SELECT external_lead_id, lead_kind::text AS lead_kind,
                       status::text AS status, discovered_at
                  FROM turab.external_leads
                 WHERE status::text <> ALL(:closed)
                 ORDER BY discovered_at, external_lead_id"""),
        {"closed": sorted(CLOSED_STATUSES)},
    ).mappings().all()


def queue_item(row: Mapping[str, Any]) -> dict[str, Any]:
    """`QueueItem`. `priority` is `NORMAL` for every lead: no priority rule
    exists, and any other value would invent one (G3-10 §3, Q-4)."""
    return {
        "id": str(row["external_lead_id"]),
        "kind": f"EXTERNAL_LEAD_{row['lead_kind']}",
        "priority": "NORMAL",
        "created_at": row["discovered_at"].isoformat(),
        "reason": row["status"],
    }

