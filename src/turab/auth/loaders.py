"""Actor-scoped, policy-checked loaders — stage 5/6 of the pipeline.

Ref: RFC-001 §4 (authority graph), §10 R10.3 (structural enforcement),
R5.2 (filter, never fetch-then-compare), R4.9 (canonical resolution);
implementation invariant INV-1.

Every loader issues ONE statement that already carries the authority predicate.
There is deliberately no `get_by_id(id)` here: a loader that takes an id alone
is the bypass these loaders exist to prevent, so the signature makes the
subject non-optional.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from .policy import DenyReason
from .subject import Subject


class ResourceKind(StrEnum):
    PARTY = "PARTY"
    REQUEST = "REQUEST"
    PROPERTY = "PROPERTY"
    OFFER = "PROPERTY_OFFER"
    OPPORTUNITY = "OPPORTUNITY"
    INTEREST = "INTEREST"
    CONSENT_GRANT = "CONSENT_GRANT"
    THREAD = "COMMUNICATION_THREAD"


@dataclass(frozen=True, slots=True)
class LoadResult:
    """Either a row the subject is authorized to see, or a denial."""

    kind: ResourceKind
    resource_id: uuid.UUID
    row: Mapping[str, Any] | None = None
    reason: DenyReason | None = None
    detail: str | None = None

    @property
    def authorized(self) -> bool:
        return self.row is not None


def _denied(
    kind: ResourceKind,
    resource_id: uuid.UUID,
    reason: DenyReason = DenyReason.OBJECT_NOT_AUTHORIZED,
    detail: str | None = None,
) -> LoadResult:
    return LoadResult(kind, resource_id, None, reason, detail)


# ---------------------------------------------------------------------------
# INV-1 — claim authority conflict
# ---------------------------------------------------------------------------

#: A resource claimed by more than one distinct account has ambiguous authority.
#: We grant it to nobody and require operational resolution, rather than pick
#: the earliest or latest claim: picking silently would hand one party another
#: party's record on the strength of a data defect.
_CLAIM_AUTHORITY_SQL = text(
    """
    SELECT DISTINCT claimed_by_account_id
      FROM turab.record_claim_events
     WHERE (:kind = 'PROPERTY' AND property_id = :resource_id)
        OR (:kind = 'REQUEST'  AND request_id  = :resource_id)
    """
)


def claim_authority_accounts(
    session: Session, kind: ResourceKind, resource_id: uuid.UUID
) -> frozenset[uuid.UUID]:
    """Every distinct account holding a claim on this resource."""
    if kind not in (ResourceKind.PROPERTY, ResourceKind.REQUEST):
        raise ValueError(f"claims apply to PROPERTY and REQUEST only, not {kind}")
    rows = session.execute(
        _CLAIM_AUTHORITY_SQL, {"kind": kind.value, "resource_id": resource_id}
    ).scalars().all()
    return frozenset(r for r in rows if r is not None)


class ClaimAuthorityConflict(Exception):
    """INV-1. Raised so the caller audits CLAIM_AUTHORITY_CONFLICT and denies."""

    def __init__(self, kind: ResourceKind, resource_id: uuid.UUID,
                 accounts: frozenset[uuid.UUID]) -> None:
        self.kind = kind
        self.resource_id = resource_id
        self.accounts = accounts
        super().__init__(
            f"{kind.value} {resource_id} is claimed by {len(accounts)} distinct "
            "accounts; authority is granted to none pending operational resolution"
        )


def _guard_claim_conflict(
    session: Session, kind: ResourceKind, resource_id: uuid.UUID
) -> None:
    accounts = claim_authority_accounts(session, kind, resource_id)
    if len(accounts) > 1:
        raise ClaimAuthorityConflict(kind, resource_id, accounts)


# ---------------------------------------------------------------------------
# Canonical resolution (R4.9)
# ---------------------------------------------------------------------------

def resolve_canonical_property(session: Session, property_id: uuid.UUID) -> uuid.UUID:
    """An alias resolves to its canonical property before any authority check.

    Identity resolution is non-destructive (ADR-03) and must not strip a real
    owner of access to their own property.
    """
    canonical = session.execute(
        text(
            """
            SELECT canonical_property_id
              FROM turab.property_identity_aliases
             WHERE alias_property_id = :property_id
            """
        ),
        {"property_id": property_id},
    ).scalar_one_or_none()
    return canonical or property_id


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_party(session: Session, subject: Subject, party_id: uuid.UUID) -> LoadResult:
    if not subject.has_party:
        return _denied(ResourceKind.PARTY, party_id, DenyReason.NO_PARTY)
    row = session.execute(
        text(
            """
            SELECT party_id, kind::text, status::text, display_name, version
              FROM turab.parties
             WHERE party_id = :party_id AND party_id = :subject_party
            """
        ),
        {"party_id": party_id, "subject_party": subject.party_id},
    ).mappings().first()
    return (
        LoadResult(ResourceKind.PARTY, party_id, row)
        if row
        else _denied(ResourceKind.PARTY, party_id)
    )


def load_request(session: Session, subject: Subject, request_id: uuid.UUID) -> LoadResult:
    """R4.8. Party match AND claimed state.

    `requests.party_id` is NOT NULL, so an assisted request already carries the
    subject's party. Party match alone would hand a customer a record staff are
    still operating.
    """
    if not subject.has_party:
        return _denied(ResourceKind.REQUEST, request_id, DenyReason.NO_PARTY)
    _guard_claim_conflict(session, ResourceKind.REQUEST, request_id)
    row = session.execute(
        text(
            """
            SELECT request_id, party_id, status::text, transaction_intent::text,
                   management_mode::text, claim_status::text, version
              FROM turab.requests
             WHERE request_id = :request_id
               AND party_id = :subject_party
               AND claim_status = 'CLAIMED'
            """
        ),
        {"request_id": request_id, "subject_party": subject.party_id},
    ).mappings().first()
    return (
        LoadResult(ResourceKind.REQUEST, request_id, row)
        if row
        else _denied(ResourceKind.REQUEST, request_id)
    )


def load_property(session: Session, subject: Subject, property_id: uuid.UUID) -> LoadResult:
    """R4.1. Creator account OR a recorded claim. Account-scoped (R4.2).

    Note what is absent: `party_property_relations` is never consulted
    (decision 1, R4.5). A relation is eligibility to claim, not authority.
    """
    canonical_id = resolve_canonical_property(session, property_id)
    _guard_claim_conflict(session, ResourceKind.PROPERTY, canonical_id)
    row = session.execute(
        text(
            """
            SELECT p.property_id, p.property_type::text, p.supply_mode::text,
                   p.management_mode::text, p.claim_status::text, p.version
              FROM turab.properties p
             WHERE p.property_id = :property_id
               AND (
                     (p.created_by_account_id IS NOT NULL
                      AND p.created_by_account_id = :account_id)
                  OR EXISTS (
                       SELECT 1 FROM turab.record_claim_events c
                        WHERE c.property_id = p.property_id
                          AND c.claimed_by_account_id = :account_id
                     )
                   )
            """
        ),
        {"property_id": canonical_id, "account_id": subject.account_id},
    ).mappings().first()
    return (
        LoadResult(ResourceKind.PROPERTY, canonical_id, row)
        if row
        else _denied(ResourceKind.PROPERTY, canonical_id)
    )


def load_offer(session: Session, subject: Subject, offer_id: uuid.UUID) -> LoadResult:
    """Q9 / §4.6. Creator account, OR (parent claim AND party match AND parent CLAIMED).

    The party match in the second branch is what stops a property claim from
    opening another party's offer on the same physical property (R4.13).
    """
    row = session.execute(
        text(
            """
            SELECT o.offer_id, o.property_id, o.party_id, o.transaction_type::text,
                   o.status::text, o.asking_price_dzd, o.price_visibility::text,
                   o.permission_scope::text, o.version
              FROM turab.property_offers o
              JOIN turab.properties p ON p.property_id = o.property_id
             WHERE o.offer_id = :offer_id
               AND (
                     -- condition 1: the actor created the offer
                     (o.created_by_account_id IS NOT NULL
                      AND o.created_by_account_id = :account_id)
                  OR -- condition 2: all three terms together
                     (:party_id IS NOT NULL
                      AND o.party_id = :party_id
                      AND p.claim_status = 'CLAIMED'
                      AND EXISTS (
                            SELECT 1 FROM turab.record_claim_events c
                             WHERE c.property_id = p.property_id
                               AND c.claimed_by_account_id = :account_id
                          ))
                   )
            """
        ),
        {
            "offer_id": offer_id,
            "account_id": subject.account_id,
            "party_id": subject.party_id,
        },
    ).mappings().first()
    return (
        LoadResult(ResourceKind.OFFER, offer_id, row)
        if row
        else _denied(ResourceKind.OFFER, offer_id)
    )


def load_opportunity(
    session: Session, subject: Subject, opportunity_id: uuid.UUID
) -> LoadResult:
    """Transitive: the opportunity's request must belong to the caller."""
    if not subject.has_party:
        return _denied(ResourceKind.OPPORTUNITY, opportunity_id, DenyReason.NO_PARTY)
    row = session.execute(
        text(
            """
            SELECT o.opportunity_id, o.request_id, o.property_id, o.status::text,
                   o.validity_status::text, o.sharing_scope::text, o.why_real,
                   o.known_differences, o.created_at, o.shared_at
              FROM turab.opportunities o
              JOIN turab.requests r ON r.request_id = o.request_id
             WHERE o.opportunity_id = :opportunity_id
               AND r.party_id = :subject_party
            """
        ),
        {"opportunity_id": opportunity_id, "subject_party": subject.party_id},
    ).mappings().first()
    return (
        LoadResult(ResourceKind.OPPORTUNITY, opportunity_id, row)
        if row
        else _denied(ResourceKind.OPPORTUNITY, opportunity_id)
    )


def _load_party_owned(
    session: Session,
    subject: Subject,
    kind: ResourceKind,
    resource_id: uuid.UUID,
    sql: str,
) -> LoadResult:
    if not subject.has_party:
        return _denied(kind, resource_id, DenyReason.NO_PARTY)
    row = session.execute(
        text(sql), {"resource_id": resource_id, "subject_party": subject.party_id}
    ).mappings().first()
    return LoadResult(kind, resource_id, row) if row else _denied(kind, resource_id)


def load_interest(session: Session, subject: Subject, interest_id: uuid.UUID) -> LoadResult:
    return _load_party_owned(
        session, subject, ResourceKind.INTEREST, interest_id,
        """
        SELECT interest_id, party_id, property_id, status::text
          FROM turab.interests
         WHERE interest_id = :resource_id AND party_id = :subject_party
        """,
    )


def load_consent_grant(session: Session, subject: Subject, consent_id: uuid.UUID) -> LoadResult:
    return _load_party_owned(
        session, subject, ResourceKind.CONSENT_GRANT, consent_id,
        """
        SELECT consent_id, party_id, scope::text, status::text
          FROM turab.consent_grants
         WHERE consent_id = :resource_id AND party_id = :subject_party
        """,
    )


def load_thread(session: Session, subject: Subject, thread_id: uuid.UUID) -> LoadResult:
    return _load_party_owned(
        session, subject, ResourceKind.THREAD, thread_id,
        """
        SELECT thread_id, party_id, channel::text
          FROM turab.communication_threads
         WHERE thread_id = :resource_id AND party_id = :subject_party
        """,
    )


# ---------------------------------------------------------------------------
# Staff reads
# ---------------------------------------------------------------------------
#
# Staff hold no ownership, so their object check has a different shape
# (RFC-001 §6): the role gate plus a recorded business purpose, which the audit
# record supplies. These still take a subject — both because the audit needs it
# and because a loader that accepts an id alone is the bypass the architecture
# test forbids.

def load_party_for_staff(
    session: Session, subject: Subject, party_id: uuid.UUID
) -> LoadResult:
    row = session.execute(
        text(
            """
            SELECT party_id, kind::text, status::text, display_name, legal_name,
                   notes, version, created_at, updated_at
              FROM turab.parties WHERE party_id = :party_id
            """
        ),
        {"party_id": party_id},
    ).mappings().first()
    return (
        LoadResult(ResourceKind.PARTY, party_id, row)
        if row
        else _denied(ResourceKind.PARTY, party_id)
    )


def load_request_for_staff(
    session: Session, subject: Subject, request_id: uuid.UUID
) -> LoadResult:
    """A staff read of any REQUEST, by role and recorded.

    Deliberately separate from `load_request`, which is the CUSTOMER loader
    and requires party match AND a claimed record (R4.8). Staff need neither,
    and merging the two would be one `if` away from handing a customer the
    staff query.
    """
    row = session.execute(
        text(
            """
            SELECT request_id, party_id, status::text AS status,
                   transaction_intent::text AS transaction_intent,
                   intent::text AS intent, payment::text AS payment,
                   desired_property_type::text AS desired_property_type,
                   property_type_importance::text AS property_type_importance,
                   primary_location_id,
                   location_importance::text AS location_importance,
                   local_location_detail, budget_target_dzd, budget_max_dzd,
                   budget_importance::text AS budget_importance,
                   budget_flexibility::text AS budget_flexibility,
                   last_confirmed_at,
                   management_mode::text AS management_mode,
                   claim_status::text AS claim_status,
                   version, created_at, updated_at
              FROM turab.requests WHERE request_id = :request_id
            """
        ),
        {"request_id": request_id},
    ).mappings().first()
    return (
        LoadResult(ResourceKind.REQUEST, request_id, row)
        if row
        else _denied(ResourceKind.REQUEST, request_id)
    )


def load_property_for_staff(
    session: Session, subject: Subject, property_id: uuid.UUID
) -> LoadResult:
    """A staff read of any PROPERTY, by role and recorded — Slice 3.

    Separate from `load_property`, which is the CUSTOMER loader and requires
    the creator account or a recorded claim (R4.1). Staff need neither, and
    merging the two would be one `if` away from handing a customer the staff
    query.

    It resolves through `property_identity_aliases` for the same reason the
    customer loader does (R4.9): an alias and its canonical are one physical
    property, so a staff read of either must reach the same record rather than
    two half-populated views of one thing.
    """
    canonical_id = resolve_canonical_property(session, property_id)
    row = session.execute(
        text(
            """
            SELECT property_id, property_type::text AS property_type,
                   canonical_location_id, local_location_detail,
                   land_area_m2, built_area_m2,
                   current_availability::text AS current_availability,
                   availability_last_confirmed_at,
                   supply_mode::text AS supply_mode,
                   management_mode::text AS management_mode,
                   claim_status::text AS claim_status,
                   version, created_by_account_id, created_at, updated_at
              FROM turab.properties WHERE property_id = :property_id
            """
        ),
        {"property_id": canonical_id},
    ).mappings().first()
    return (
        LoadResult(ResourceKind.PROPERTY, canonical_id, row)
        if row
        else _denied(ResourceKind.PROPERTY, canonical_id)
    )


STAFF_LOADERS = {
    ResourceKind.PARTY: load_party_for_staff,
    ResourceKind.REQUEST: load_request_for_staff,
    ResourceKind.PROPERTY: load_property_for_staff,
}


LOADERS = {
    ResourceKind.PARTY: load_party,
    ResourceKind.REQUEST: load_request,
    ResourceKind.PROPERTY: load_property,
    ResourceKind.OFFER: load_offer,
    ResourceKind.OPPORTUNITY: load_opportunity,
    ResourceKind.INTEREST: load_interest,
    ResourceKind.CONSENT_GRANT: load_consent_grant,
    ResourceKind.THREAD: load_thread,
}
