"""The record-claim command.

Ref: RFC-001 §4.1, §4.5a; implementation invariant INV-1.

INV-1 has two halves. The loaders enforce the read half (a resource with
ambiguous claim authority grants authority to nobody). This module enforces the
write half: a second claim on an already-claimed resource is rejected, except
an idempotent replay by the same actor.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.loaders import ResourceKind, claim_authority_accounts


class ClaimOutcome(StrEnum):
    CLAIMED = "CLAIMED"
    REPLAYED = "REPLAYED"


@dataclass(frozen=True, slots=True)
class ClaimResult:
    outcome: ClaimOutcome
    claim_event_id: uuid.UUID
    resource_kind: ResourceKind
    resource_id: uuid.UUID


class ClaimRejected(Exception):
    """The claim cannot proceed. Carries a stable reason code."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class ResourceAlreadyClaimed(ClaimRejected):
    """INV-1. Another account already holds the claim."""

    def __init__(self, kind: ResourceKind, resource_id: uuid.UUID,
                 holder: uuid.UUID) -> None:
        self.holder = holder
        super().__init__(
            "RESOURCE_ALREADY_CLAIMED",
            f"{kind.value} {resource_id} is already claimed by another account; "
            "a second claim is rejected rather than layered on top",
        )


class ClaimAuthorityConflictExists(ClaimRejected):
    """INV-1. The resource is already in the ambiguous state."""

    def __init__(self, kind: ResourceKind, resource_id: uuid.UUID, count: int) -> None:
        super().__init__(
            "CLAIM_AUTHORITY_CONFLICT",
            f"{kind.value} {resource_id} already has {count} distinct claim "
            "authorities; operational resolution is required before any further claim",
        )


def _existing_event(
    session: Session, kind: ResourceKind, resource_id: uuid.UUID, account_id: uuid.UUID
) -> uuid.UUID | None:
    return session.execute(
        text(
            """
            SELECT claim_event_id
              FROM turab.record_claim_events
             WHERE claimed_by_account_id = :account_id
               AND ((:kind = 'PROPERTY' AND property_id = :resource_id)
                 OR (:kind = 'REQUEST'  AND request_id  = :resource_id))
             ORDER BY claimed_at
             LIMIT 1
            """
        ),
        {"kind": kind.value, "resource_id": resource_id, "account_id": account_id},
    ).scalar_one_or_none()


def claim_record(
    session: Session,
    *,
    kind: ResourceKind,
    resource_id: uuid.UUID,
    account_id: uuid.UUID,
    verification_contact_point_id: uuid.UUID | None = None,
) -> ClaimResult:
    """Claim an assisted record, or replay an identical earlier claim.

    Must run inside `audited_transaction`, so the state change it makes is
    attributed. The ordering below matters: the conflict check comes before the
    replay check, because a resource that is already ambiguous must not be made
    to look settled by one of its claimants replaying.
    """
    if kind not in (ResourceKind.PROPERTY, ResourceKind.REQUEST):
        raise ValueError(f"only PROPERTY and REQUEST are claimable, not {kind}")

    holders = claim_authority_accounts(session, kind, resource_id)

    if len(holders) > 1:
        raise ClaimAuthorityConflictExists(kind, resource_id, len(holders))

    if holders:
        holder = next(iter(holders))
        if holder != account_id:
            # INV-1. Reject rather than create the second claim that would put
            # the resource into the ambiguous state.
            raise ResourceAlreadyClaimed(kind, resource_id, holder)
        # Idempotent replay by the same actor: no new event, no state change.
        event_id = _existing_event(session, kind, resource_id, account_id)
        assert event_id is not None  # holders came from this same table
        return ClaimResult(ClaimOutcome.REPLAYED, event_id, kind, resource_id)

    column = "property_id" if kind is ResourceKind.PROPERTY else "request_id"
    table = "properties" if kind is ResourceKind.PROPERTY else "requests"
    id_column = "property_id" if kind is ResourceKind.PROPERTY else "request_id"

    current = session.execute(
        text(
            f"""
            SELECT management_mode::text AS mode, claim_status::text AS claim
              FROM turab.{table} WHERE {id_column} = :resource_id
            """
        ),
        {"resource_id": resource_id},
    ).mappings().first()
    if current is None:
        raise ClaimRejected("NOT_FOUND", f"{kind.value} {resource_id} does not exist")
    if current["claim"] != "UNCLAIMED":
        # Claimed with no claim event: self-service record, not claimable.
        raise ClaimRejected(
            "RESOURCE_NOT_CLAIMABLE",
            f"{kind.value} {resource_id} is {current['mode']}/{current['claim']}; "
            "only an ASSISTED/UNCLAIMED record may be claimed",
        )

    event_id = session.execute(
        text(
            f"""
            INSERT INTO turab.record_claim_events
                   ({column}, claimed_by_account_id, verification_contact_point_id)
            VALUES (:resource_id, :account_id, :contact_point_id)
            RETURNING claim_event_id
            """
        ),
        {
            "resource_id": resource_id,
            "account_id": account_id,
            "contact_point_id": verification_contact_point_id,
        },
    ).scalar_one()

    session.execute(
        text(
            f"""
            UPDATE turab.{table}
               SET management_mode = 'SHARED_MANAGEMENT', claim_status = 'CLAIMED'
             WHERE {id_column} = :resource_id
            """
        ),
        {"resource_id": resource_id},
    )
    return ClaimResult(ClaimOutcome.CLAIMED, event_id, kind, resource_id)
