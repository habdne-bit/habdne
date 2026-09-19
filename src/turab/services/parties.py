"""PARTY and CONTACT_POINT commands — Slice 1.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 1; API_CONTRACTS v0.2 §4.1;
ADR-07 (Contact Point != Party != Account); red-team A01, A03.

The rule this module exists to protect: a contact point is not a party. Two
people can share a phone, and recording that must never merge them.
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

#: The contract's own pattern for a phone number.
E164 = re.compile(r"^\+[1-9][0-9]{7,14}$")

PARTY_KINDS = ("PERSON", "BUSINESS")


class InvalidPhone(ValueError):
    """The number is not E.164 as the contract requires."""


class PartyNotFound(LookupError):
    pass


def normalize_phone(raw: str) -> str:
    """Normalise to E.164.

    Normalisation is what makes "the same phone" a meaningful idea: without
    it, `+213661000001` and `0661 00 00 01` would be different contact points
    and A01 could never be tested.
    """
    cleaned = re.sub(r"[\s\-().]", "", (raw or "").strip())
    if not E164.match(cleaned):
        raise InvalidPhone(f"phone must match {E164.pattern}")
    return cleaned


def create_party(
    session: Session,
    *,
    kind: str,
    display_name: str | None = None,
    legal_name: str | None = None,
    notes: str | None = None,
) -> Mapping[str, Any]:
    """Create a PARTY.

    A party starts DISCOVERED and has no account: ADR-07 and red-team A03 both
    require that a party can exist with no USER_ACCOUNT at all.
    """
    if kind not in PARTY_KINDS:
        raise ValueError(f"kind must be one of {PARTY_KINDS}")
    return session.execute(
        text(
            """
            INSERT INTO turab.parties (kind, status, display_name, legal_name, notes)
            VALUES (CAST(:kind AS turab.party_kind), 'DISCOVERED',
                    :display_name, :legal_name, :notes)
            RETURNING party_id, kind::text, status::text, display_name, legal_name,
                      version, created_at, updated_at
            """
        ),
        {"kind": kind, "display_name": display_name,
         "legal_name": legal_name, "notes": notes},
    ).mappings().one()


def read_party(session: Session, party_id: uuid.UUID) -> Mapping[str, Any]:
    row = session.execute(
        text(
            """
            SELECT party_id, kind::text, status::text, display_name, legal_name,
                   notes, version, created_at, updated_at
              FROM turab.parties WHERE party_id = :id
            """
        ),
        {"id": party_id},
    ).mappings().first()
    if row is None:
        raise PartyNotFound(str(party_id))
    return row


#: PartyPatch in the frozen contract. Only these three fields are patchable:
#: status, kind and version are not, so a typed PATCH cannot change identity
#: or state (API_CONTRACTS §7, red-team K04).
PATCHABLE = ("display_name", "legal_name", "notes")


def update_party(
    session: Session, party_id: uuid.UUID, changes: Mapping[str, Any]
) -> Mapping[str, Any]:
    """Typed projection update.

    The caller's version was already checked by the command boundary, and the
    `bump_version_and_timestamp` trigger advances it here, so a second writer
    holding the old version will now fail their own check.
    """
    unknown = set(changes) - set(PATCHABLE)
    if unknown:
        raise ValueError(f"not patchable: {sorted(unknown)}")
    if not changes:
        raise ValueError("PartyPatch requires at least one field")

    assignments = ", ".join(f"{f} = :{f}" for f in changes)
    row = session.execute(
        text(
            f"""
            UPDATE turab.parties SET {assignments}
             WHERE party_id = :id
            RETURNING party_id, kind::text, status::text, display_name, legal_name,
                      notes, version, created_at, updated_at
            """
        ),
        {"id": party_id, **changes},
    ).mappings().first()
    if row is None:
        raise PartyNotFound(str(party_id))
    return row


def attach_phone(
    session: Session,
    *,
    party_id: uuid.UUID,
    phone_e164: str,
    is_primary: bool = False,
    relationship_note: str | None = None,
) -> Mapping[str, Any]:
    """Create or REUSE a phone contact point, then link it to the party.

    A01 / ADR-07: the contact point is reused when the number already exists,
    and the parties are never merged. Reuse also preserves the existing
    `control_status`, so one party verifying a shared line does not silently
    hand verified control to another party's record — the link is shared, the
    verification travels with the contact point, and neither implies identity.
    """
    normalized = normalize_phone(phone_e164)

    contact = session.execute(
        text(
            """
            SELECT contact_point_id, kind::text, normalized_value, display_value,
                   control_status::text, control_verified_at, verification_method
              FROM turab.contact_points
             WHERE kind = 'PHONE' AND normalized_value = :value
            """
        ),
        {"value": normalized},
    ).mappings().first()

    if contact is None:
        contact = session.execute(
            text(
                """
                INSERT INTO turab.contact_points
                       (kind, normalized_value, display_value, control_status)
                VALUES ('PHONE', :value, :display, 'UNVERIFIED')
                RETURNING contact_point_id, kind::text, normalized_value,
                          display_value, control_status::text, control_verified_at,
                          verification_method
                """
            ),
            {"value": normalized, "display": phone_e164},
        ).mappings().one()

    if is_primary:
        # ux_party_primary_contact_kind allows one primary per party.
        session.execute(
            text(
                """UPDATE turab.party_contact_points SET is_primary = false
                    WHERE party_id = :p AND is_primary"""
            ),
            {"p": party_id},
        )

    session.execute(
        text(
            """
            INSERT INTO turab.party_contact_points
                   (party_id, contact_point_id, is_primary, relationship_note)
            VALUES (:party_id, :cp, :is_primary, :note)
            ON CONFLICT (party_id, contact_point_id) DO UPDATE
               SET is_primary = EXCLUDED.is_primary,
                   relationship_note = COALESCE(EXCLUDED.relationship_note,
                                                turab.party_contact_points.relationship_note)
            """
        ),
        {"party_id": party_id, "cp": contact["contact_point_id"],
         "is_primary": is_primary, "note": relationship_note},
    )
    return contact


def parties_sharing(session: Session, contact_point_id: uuid.UUID) -> list[uuid.UUID]:
    """Every party reachable on one contact point. A01 asserts this can be > 1."""
    return list(
        session.execute(
            text(
                """SELECT party_id FROM turab.party_contact_points
                    WHERE contact_point_id = :cp ORDER BY created_at"""
            ),
            {"cp": contact_point_id},
        ).scalars().all()
    )
