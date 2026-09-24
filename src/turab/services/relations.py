"""PARTY–PROPERTY RELATIONS — G3-6, Contract Delta revision 3a.

Ref: `docs/gate/CONTRACT_DELTA_G3-6_party_property_relations.md` (rev 3a,
re-confirmed); `docs/contract/addenda/ADD-G3-6_party_property_relations.yaml`;
RFC-001 R4.5, R4.6, R4.12; migrations `0003` (currency predicate) and `0004`
(overlap guard).

**A relation grants no authority whatsoever** (Delta §8). Nothing in this
module is read by any loader, and nothing here writes `record_claim_events`,
`properties.created_by_account_id` or anything else an authority rule reads.
A relation is eligibility-relevant data, not access.

Three operations, two of which mutate:

  * **create** — `valid_from` omitted -> the server clock (`now()`, the
    transaction timestamp, so the row is current for the rest of this
    transaction too); an explicit FUTURE `valid_from` is allowed and yields a
    relation that is not current until it starts (§5.1, rev 3a correction);
    `verification_level` is always the schema default `DECLARED` (§5);
  * **retrieve** — current only by default, using the ratified predicate and
    no other (§3.2);
  * **end** — sets `valid_to`; never a delete (§3.3).

**Audit is this module's job.** `party_property_relations` has no `audit_*`
trigger in the frozen schema (Delta §7), so `_audit` writes the same row
`audit_row_change()` would have written — actor and context from the
transaction settings the command set — alongside the provenance trail.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import provenance
from .provenance import UpdateChannel

#: The frozen schema's CHECK list, exactly seven (Delta §2, fact 1).
RELATION_CODES = (
    "OWNER_DECLARED", "BROKER", "AGENCY", "DEVELOPER", "OCCUPANT",
    "CONTACT_PERSON", "OTHER",
)

#: The ratified currency predicate (0003; Delta §3.2). Stated once.
CURRENT = ("valid_from IS NOT NULL AND valid_from <= now() "
           "AND (valid_to IS NULL OR now() < valid_to)")

PARTY_FK = "party_property_relations_party_id_fkey"
OVERLAP = "party_property_relations_no_overlap"

_COLUMNS = """party_property_relation_id, property_id, party_id, relation_code,
              verification_level::text AS verification_level,
              valid_from, valid_to, created_at"""


class RelationError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        self.code, self.detail = code, detail
        super().__init__(detail)


class PropertyNotFound(RelationError):
    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "no such property")


class RelationNotFound(RelationError):
    """One message whether the relation does not exist or belongs to another
    property: the path names both, and they must agree."""

    def __init__(self) -> None:
        super().__init__("NOT_FOUND", "no such relation on this property")


class UnknownParty(RelationError):
    def __init__(self, party_id) -> None:
        super().__init__("VALIDATION_FAILED", f"party_id {party_id} is not a known party")


class RelationOverlap(RelationError):
    """Rule 6a (Delta §6), enforced by `0004`: one period per
    (party, property, relation_code). Names the relation it collides with."""

    def __init__(self, existing: uuid.UUID | None) -> None:
        self.existing = existing
        named = f" {existing}" if existing else ""
        super().__init__(
            "RELATION_OVERLAP",
            f"this party already holds this relation_code on this property for "
            f"an overlapping period (relation{named}); end it first",
        )


class AlreadyEnded(RelationError):
    def __init__(self, valid_to: datetime) -> None:
        super().__init__(
            "RELATION_ALREADY_ENDED",
            f"this relation already has an end recorded ({valid_to.isoformat()})",
        )


class EndNotAfterStart(RelationError):
    def __init__(self, valid_from: datetime, valid_to: datetime) -> None:
        super().__init__(
            "VALIDATION_FAILED",
            f"valid_to ({valid_to.isoformat()}) must be after valid_from "
            f"({valid_from.isoformat()})",
        )


class UnknownReasonCode(RelationError):
    def __init__(self, code: str) -> None:
        super().__init__("VALIDATION_FAILED", f"{code!r} is not an active reason code")


def _row(session: Session, relation_id: uuid.UUID) -> Mapping[str, Any]:
    return session.execute(
        text(f"SELECT {_COLUMNS} FROM turab.party_property_relations "
             "WHERE party_property_relation_id = :r"),
        {"r": relation_id},
    ).mappings().one()


def _json_of(session: Session, relation_id: uuid.UUID) -> str:
    return session.execute(
        text("SELECT to_jsonb(r)::text FROM turab.party_property_relations r "
             "WHERE party_property_relation_id = :r"),
        {"r": relation_id},
    ).scalar_one()


def _audit(session: Session, relation_id: uuid.UUID, action: str,
           old: str | None, new: str | None) -> None:
    """The row `audit_row_change()` would write, had the table a trigger.

    Actor and context come from `app.account_id` / `app.audit_context`, which
    `audited_transaction` set for this command — the same source the trigger
    reads — so the record is indistinguishable in shape from every other
    audited table's.
    """
    session.execute(
        text(
            """INSERT INTO turab.audit_log
                      (entity_table, entity_id, action, old_row, new_row,
                       actor_account_id, context)
               VALUES ('party_property_relations', :id, :action,
                       CAST(:old AS jsonb), CAST(:new AS jsonb),
                       NULLIF(current_setting('app.account_id', true), '')::uuid,
                       COALESCE(NULLIF(current_setting('app.audit_context', true),
                                       '')::jsonb, '{}'::jsonb))"""
        ),
        {"id": relation_id, "action": action, "old": old, "new": new},
    )


def _require_property(session: Session, property_id: uuid.UUID) -> None:
    found = session.execute(
        text("SELECT 1 FROM turab.properties WHERE property_id = :p"),
        {"p": property_id},
    ).first()
    if found is None:
        raise PropertyNotFound()


def _overlapping(session: Session, *, party_id, property_id, relation_code,
                 valid_from) -> uuid.UUID | None:
    """The relation a refused insert collided with, for the 409's detail."""
    return session.execute(
        text(
            """SELECT party_property_relation_id
                 FROM turab.party_property_relations
                WHERE party_id = :party AND property_id = :prop
                  AND relation_code = :code
                  AND tstzrange(coalesce(valid_from, '-infinity'::timestamptz),
                                valid_to, '[)')
                      && tstzrange(coalesce(:vf, now()), NULL, '[)')
                ORDER BY created_at LIMIT 1"""
        ),
        {"party": party_id, "prop": property_id, "code": relation_code,
         "vf": valid_from},
    ).scalar_one_or_none()


def create_relation(
    session: Session,
    *,
    property_id: uuid.UUID,
    party_id: uuid.UUID,
    relation_code: str,
    valid_from: datetime | None,
    note: str | None,
    recorded_by_account_id: uuid.UUID,
) -> Mapping[str, Any]:
    from sqlalchemy.exc import IntegrityError

    from .properties import AliasNotCanonical, refuse_alias

    if relation_code not in RELATION_CODES:
        raise RelationError("VALIDATION_FAILED",
                            f"relation_code must be one of {list(RELATION_CODES)}")
    _require_property(session, property_id)
    # Decision F-2: a new write on an identity alias is refused. Raised here,
    # inside the command — the route's gate is staff-only, so there is no
    # unauthorized caller for whom this could disclose anything.
    try:
        refuse_alias(session, property_id)
    except AliasNotCanonical as exc:
        raise RelationError(exc.code, exc.detail) from exc

    savepoint = session.begin_nested()
    try:
        relation_id = session.execute(
            text(
                """INSERT INTO turab.party_property_relations
                          (party_id, property_id, relation_code, valid_from)
                   VALUES (:party, :prop, :code, COALESCE(:vf, now()))
                RETURNING party_property_relation_id"""
            ),
            {"party": party_id, "prop": property_id, "code": relation_code,
             "vf": valid_from},
        ).scalar_one()
        savepoint.commit()
    except IntegrityError as exc:
        savepoint.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "")
        if constraint == PARTY_FK:
            raise UnknownParty(party_id) from exc
        if constraint == OVERLAP:
            raise RelationOverlap(_overlapping(
                session, party_id=party_id, property_id=property_id,
                relation_code=relation_code, valid_from=valid_from)) from exc
        raise

    row = _row(session, relation_id)
    provenance.record(
        session,
        subject=provenance.Subject.PROPERTY,
        subject_id=property_id,
        party_id=party_id,
        changes={"party_property_relation": {
            "event": "CREATED",
            "party_property_relation_id": str(relation_id),
            "party_id": str(party_id),
            "relation_code": relation_code,
            "valid_from": row["valid_from"].isoformat(),
            "valid_from_supplied": valid_from is not None,
        }},
        previous=None,
        recorded_by_account_id=recorded_by_account_id,
        channel=UpdateChannel.STAFF_RECORDED,
        note=note,
    )
    _audit(session, relation_id, "INSERT", None, _json_of(session, relation_id))
    return row


def list_relations(
    session: Session,
    *,
    property_id: uuid.UUID,
    include_ended: bool,
    page: int,
    page_size: int,
) -> tuple[list[Mapping[str, Any]], int]:
    """Current relations by default; the full history with `include_ended`.

    "Current" is the ratified predicate `CURRENT` — a future-start relation is
    NOT listed as current, exactly as the consent gate refuses it.
    """
    _require_property(session, property_id)
    where = "property_id = :p" + ("" if include_ended else f" AND {CURRENT}")
    total = session.execute(
        text(f"SELECT count(*) FROM turab.party_property_relations WHERE {where}"),
        {"p": property_id},
    ).scalar_one()
    items = session.execute(
        text(f"""SELECT {_COLUMNS} FROM turab.party_property_relations
                  WHERE {where}
                  ORDER BY created_at, party_property_relation_id
                  LIMIT :limit OFFSET :offset"""),
        {"p": property_id, "limit": page_size, "offset": (page - 1) * page_size},
    ).mappings().all()
    return list(items), total


def end_relation(
    session: Session,
    *,
    property_id: uuid.UUID,
    relation_id: uuid.UUID,
    valid_to: datetime | None,
    reason_code: str | None,
    recorded_by_account_id: uuid.UUID,
) -> Mapping[str, Any]:
    """Record the end of a relation's validity. The row survives (§3.3)."""
    locked = session.execute(
        text(f"""SELECT {_COLUMNS} FROM turab.party_property_relations
                  WHERE party_property_relation_id = :r AND property_id = :p
                  FOR UPDATE"""),
        {"r": relation_id, "p": property_id},
    ).mappings().first()
    if locked is None:
        raise RelationNotFound()
    if locked["valid_to"] is not None:
        raise AlreadyEnded(locked["valid_to"])
    if reason_code is not None:
        known = session.execute(
            text("SELECT 1 FROM turab.reason_codes WHERE code = :c AND active"),
            {"c": reason_code},
        ).first()
        if known is None:
            raise UnknownReasonCode(reason_code)

    end = session.execute(text("SELECT COALESCE(:vt, now())"),
                          {"vt": valid_to}).scalar_one()
    # Checked before SQL so it is a typed 422, not the frozen CHECK surfacing
    # as a 500 (Delta §3.3). A row with no recorded start has nothing to be
    # before, which is what the CHECK itself says.
    if locked["valid_from"] is not None and not end > locked["valid_from"]:
        raise EndNotAfterStart(locked["valid_from"], end)

    old = _json_of(session, relation_id)
    session.execute(
        text("""UPDATE turab.party_property_relations SET valid_to = :end
                 WHERE party_property_relation_id = :r"""),
        {"end": end, "r": relation_id},
    )
    provenance.record(
        session,
        subject=provenance.Subject.PROPERTY,
        subject_id=property_id,
        party_id=locked["party_id"],
        changes={"party_property_relation": {
            "event": "ENDED",
            "party_property_relation_id": str(relation_id),
            "valid_to": end.isoformat(),
            "valid_to_supplied": valid_to is not None,
            "reason_code": reason_code,
        }},
        previous=None,
        recorded_by_account_id=recorded_by_account_id,
        channel=UpdateChannel.STAFF_RECORDED,
    )
    _audit(session, relation_id, "UPDATE", old, _json_of(session, relation_id))
    return _row(session, relation_id)


def view(row: Mapping[str, Any]) -> dict[str, Any]:
    """`PartyPropertyRelation`, and nothing beyond it (closed schema)."""
    return {
        "party_property_relation_id": str(row["party_property_relation_id"]),
        "property_id": str(row["property_id"]),
        "party_id": str(row["party_id"]),
        "relation_code": row["relation_code"],
        "verification_level": row["verification_level"],
        "valid_from": row["valid_from"].isoformat() if row["valid_from"] else None,
        "valid_to": row["valid_to"].isoformat() if row["valid_to"] else None,
        "created_at": row["created_at"].isoformat(),
    }

