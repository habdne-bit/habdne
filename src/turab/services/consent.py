"""Consent grants and resource bindings — Slice 1.

Ref: ADR-04 (resource-bound consent); API_CONTRACTS v0.2 §4.2; RFC-001 §7;
red-team B01, B02, B03.

The database already enforces the hard part in `enforce_consent_binding()`:
the grant must exist and be GRANTED, its scope must equal the binding purpose,
and the consenting party must actually relate to the resource. RFC-001 R7.2
says the service must not re-implement a looser version of that, so this module
translates those failures into stable codes rather than re-checking them more
permissively.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, InternalError, ProgrammingError
from sqlalchemy.orm import Session

SCOPES = (
    "ASSISTED_ENTRY", "PUBLIC_LISTING_ALLOWED", "PRIVATE_MATCHING_ONLY",
    "CONTACT_BEFORE_SHARING", "COMMUNICATION_ARCHIVE",
)
CHANNELS = ("WHATSAPP", "SMS", "PHONE_CONFIRMED", "WEB", "IN_PERSON", "OTHER")

#: ConsentBindingInput.resource_type -> the column it binds to.
RESOURCE_COLUMNS = {
    "REQUEST": "request_id",
    "PROPERTY": "property_id",
    "PROPERTY_OFFER": "offer_id",
    "COMMUNICATION_THREAD": "thread_id",
}


class ConsentError(Exception):
    """Carries a stable problem code (API_CONTRACTS §2.5)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ConsentNotFound(ConsentError):
    def __init__(self, consent_id: uuid.UUID) -> None:
        super().__init__("NOT_FOUND", f"consent {consent_id} does not exist")


class ConsentRevoked(ConsentError):
    def __init__(self) -> None:
        super().__init__(
            "CONSENT_REVOKED",
            "this consent has been revoked and cannot authorize anything further",
        )


class ConsentBindingRejected(ConsentError):
    """The database refused the binding. Its reason is the authoritative one."""

    def __init__(self, detail: str) -> None:
        super().__init__("CONSENT_BINDING_REJECTED", detail)


def grant_consent(
    session: Session,
    *,
    party_id: uuid.UUID,
    scope: str,
    channel: str,
    consent_version: str,
    granted_at: datetime,
    evidence_observation_id: uuid.UUID | None = None,
    notes: str | None = None,
    created_by_account_id: uuid.UUID | None = None,
) -> Mapping[str, Any]:
    """Create a granular grant.

    §4.2: the grant "is not yet proof for a particular resource". Binding is a
    separate command, and that separation is the whole of ADR-04.
    """
    if scope not in SCOPES:
        raise ConsentError("VALIDATION_FAILED", f"scope must be one of {SCOPES}")
    if channel not in CHANNELS:
        raise ConsentError("VALIDATION_FAILED", f"channel must be one of {CHANNELS}")

    return session.execute(
        text(
            """
            INSERT INTO turab.consent_grants
                   (party_id, scope, status, channel, consent_version, granted_at,
                    evidence_observation_id, notes, created_by_account_id)
            VALUES (:party_id, CAST(:scope AS turab.consent_scope), 'GRANTED',
                    CAST(:channel AS turab.consent_channel), :consent_version,
                    :granted_at, :evidence, :notes, :actor)
            RETURNING consent_id, party_id, scope::text, status::text,
                      channel::text, consent_version, granted_at, revoked_at
            """
        ),
        {
            "party_id": party_id, "scope": scope, "channel": channel,
            "consent_version": consent_version, "granted_at": granted_at,
            "evidence": evidence_observation_id, "notes": notes,
            "actor": created_by_account_id,
        },
    ).mappings().one()


def read_grant(session: Session, consent_id: uuid.UUID) -> Mapping[str, Any]:
    row = session.execute(
        text(
            """SELECT consent_id, party_id, scope::text, status::text,
                      channel::text, granted_at, revoked_at
                 FROM turab.consent_grants WHERE consent_id = :id"""
        ),
        {"id": consent_id},
    ).mappings().first()
    if row is None:
        raise ConsentNotFound(consent_id)
    return row


def revoke_consent(
    session: Session,
    *,
    consent_id: uuid.UUID,
    reason: str | None = None,
    evidence_observation_id: uuid.UUID | None = None,
) -> Mapping[str, Any]:
    """Revoke future authority.

    ADR-04 / §4.2: revocation blocks what comes next and erases nothing.
    Existing bindings are deliberately left in place — history survives, and
    the binding is inert because its grant is no longer GRANTED, which is what
    `enforce_consent_binding()` checks.

    Revoking twice is not an error: the caller's intent is already satisfied,
    and raising would make a retry look like a failure.

    `revoked_at` is `GREATEST(clock_timestamp(), granted_at)` rather than a
    bare `now()`. Two reasons, both real: `now()` is the TRANSACTION start
    time, which can precede a `granted_at` the caller computed moments before
    the statement; and a caller may legitimately record a grant with a
    client-side timestamp. Either would violate
    `CHECK (revoked_at IS NULL OR revoked_at >= granted_at)` and surface as a
    raw constraint violation instead of a domain outcome. You cannot revoke
    before you granted, so the floor is the grant.
    """
    current = read_grant(session, consent_id)
    if current["status"] == "REVOKED":
        return current

    return session.execute(
        text(
            """
            UPDATE turab.consent_grants
               SET status = 'REVOKED',
                   revoked_at = GREATEST(clock_timestamp(), granted_at),
                   notes = COALESCE(:reason, notes),
                   evidence_observation_id = COALESCE(:evidence, evidence_observation_id)
             WHERE consent_id = :id
            RETURNING consent_id, party_id, scope::text, status::text,
                      channel::text, granted_at, revoked_at
            """
        ),
        {"id": consent_id, "reason": reason, "evidence": evidence_observation_id},
    ).mappings().one()


def bind_consent(
    session: Session,
    *,
    consent_id: uuid.UUID,
    purpose: str,
    resource_type: str,
    resource_id: uuid.UUID,
    notes: str | None = None,
    bound_by_account_id: uuid.UUID | None = None,
) -> Mapping[str, Any]:
    """Bind a granted consent to exactly one resource for one purpose.

    B01, B02 and the property-relationship rule are all enforced by
    `enforce_consent_binding()` in the frozen schema. This does not re-check
    them; it surfaces the database's refusal with a stable code so the caller
    sees a domain error rather than a driver exception.
    """
    if resource_type not in RESOURCE_COLUMNS:
        raise ConsentError(
            "VALIDATION_FAILED",
            f"resource_type must be one of {sorted(RESOURCE_COLUMNS)}",
        )
    if purpose not in SCOPES:
        raise ConsentError("VALIDATION_FAILED", f"purpose must be one of {SCOPES}")

    column = RESOURCE_COLUMNS[resource_type]
    try:
        return session.execute(
            text(
                f"""
                INSERT INTO turab.resource_consent_bindings
                       (consent_id, purpose, {column}, notes, bound_by_account_id)
                VALUES (:consent_id, CAST(:purpose AS turab.consent_scope),
                        :resource_id, :notes, :actor)
                RETURNING consent_binding_id, consent_id, purpose::text,
                          request_id, property_id, offer_id, thread_id,
                          bound_at, revoked_at
                """
            ),
            {"consent_id": consent_id, "purpose": purpose,
             "resource_id": resource_id, "notes": notes,
             "actor": bound_by_account_id},
        ).mappings().one()
    except (InternalError, ProgrammingError) as exc:
        # RAISE EXCEPTION from enforce_consent_binding(). The trigger's message
        # is the authoritative reason; it is domain text, not database internals.
        raise ConsentBindingRejected(_trigger_message(exc)) from exc
    except IntegrityError as exc:
        raise ConsentBindingRejected(
            "this consent is already bound to that resource for that purpose"
        ) from exc


def _trigger_message(exc: Exception) -> str:
    """Extract the RAISE EXCEPTION text, without driver noise."""
    original = getattr(exc, "orig", None)
    message = str(getattr(original, "diag", None) and original.diag.message_primary
                  or original or exc)
    return message.strip().splitlines()[0][:200]
