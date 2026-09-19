"""The record-claim command.

Ref: RFC-001 §4.1, §4.5a; implementation invariant INV-1; the frozen
contract's own `x-authorization` on `postRecordsClaim`:

    "For customer, verified contact point and resource party relationship are
     mandatory. Command changes ASSISTED/UNCLAIMED to SHARED_MANAGEMENT/CLAIMED
     transactionally; no duplicate resource is created."

That sentence is a DECLARED AUTHORIZATION CONDITION, not a design question.
Slice 2 first shipped INV-1 (which governs conflicts BETWEEN claimants) while
leaving the eligibility half — whether this claimant is the right person at
all — unenforced. `assert_claim_eligibility` below is that half.

INV-1 itself has two halves. The loaders enforce the read half (a resource
with ambiguous claim authority grants authority to nobody). This module
enforces the write half: a second claim on an already-claimed resource is
rejected, except an idempotent replay by the same actor.

**Everything is checked inside the caller's write transaction, on a row locked
`FOR UPDATE`.** An eligibility check made earlier, on a separate read session,
says what was true then, not what is true at the moment the row changes; two
concurrent claims would both pass it.
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


class ClaimNotEligible(ClaimRejected):
    """The declared condition on `postRecordsClaim` is not met.

    One message for every failing reason, deliberately: distinguishing "not
    your party" from "that contact point is not yours" would let a caller
    map which requests belong to which party by probing.
    The audited detail is internal; the caller learns only that they may not
    claim this record.
    """

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(
            "CLAIM_NOT_ELIGIBLE",
            "this record cannot be claimed by this account; a customer may "
            "claim only their own party's assisted record, using a contact "
            "point they control that reaches that party",
        )


class PartyLinkageNeedsReview(ClaimRejected):
    """The claimant's party and the record's party disagree.

    Raised INSTEAD of re-linking or merging anything. Two parties that look
    like one person is an identity question for a human, and an automatic
    merge would destroy the evidence needed to answer it (ADR-07, DL-02).
    """

    def __init__(self, resource_id: uuid.UUID) -> None:
        super().__init__(
            "CLAIM_NOT_ELIGIBLE",
            "this record cannot be claimed by this account; a customer may "
            "claim only their own party's assisted record, using a contact "
            "point they control that reaches that party",
        )


class PropertyClaimUndecided(ClaimRejected):
    """PROPERTY claiming is refused until its eligibility rule is decided.

    The contract requires a "resource party relationship" for a customer
    claim. A REQUEST carries `party_id`, so the rule is exact. A PROPERTY does
    not: its party relationship is `party_property_relations`, and RFC-001
    decision 1 / R4.5 states that relations are never an authorization source.

    Rather than pick one of those two and call it the rule, this path refuses
    — per the standing instruction that an affected path must reject the cases
    whose eligibility it cannot prove.
    """

    def __init__(self, resource_id: uuid.UUID) -> None:
        super().__init__(
            "CLAIM_NOT_ELIGIBLE",
            "claiming a PROPERTY is not available in this version: the "
            "eligibility rule for a property's party relationship has not been "
            "decided, and this command will not assume one",
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


def assert_claim_eligibility(
    session: Session,
    *,
    kind: ResourceKind,
    resource_id: uuid.UUID,
    account_id: uuid.UUID,
    verification_contact_point_id: uuid.UUID | None,
) -> None:
    """The contract's declared condition, enforced.

    Called INSIDE the write transaction, after the resource row is locked, so
    what is checked is what is about to change.

    The four conditions, and why each is not the obvious weaker version:

    1. **The account is bound to a party.** A staff account has no party, and
       staff roles alone do not confer the right to claim another party's
       record under the staff member's own account — claiming records who
       holds a record, and an operator is not its holder. Acting for someone
       else is delegation, which is not defined in this version (RFC-001
       decision 4), so it has no path here.

    2. **`account.party_id = resource.party_id`.** The binding is read from
       `user_accounts`, which is established out of band today (Design Ledger
       DL-07) — never inferred from a phone number, which DL-02 forbids. A
       disagreement is raised for review, never repaired by re-linking or
       merging the parties.

    3. **The contact point is one the CLAIMANT controls.** Not merely one
       whose `control_status` is `VERIFIED_CONTROL`: that column says somebody
       proved control, not that this account did, and a shared line would
       otherwise let either party's account use the other's proof. The trusted
       link between an account and a contact point is
       `user_accounts.login_contact_point_id`, which the OTP LOGIN flow is
       what sets — so the claimant must present their OWN login contact point.

    4. **That contact point reaches the resource's party.** Condition 2 alone
       would let an account claim with a phone unrelated to the record.
       Together with 3, the claimant proves both who they are and that the
       number they hold is one the record's party is reachable on.
    """
    account = session.execute(
        text(
            """SELECT party_id, status::text AS status, login_contact_point_id
                 FROM turab.user_accounts WHERE account_id = :a"""
        ),
        {"a": account_id},
    ).mappings().first()
    if account is None or account["status"] != "ACTIVATED":
        raise ClaimNotEligible("account is not an activated account")
    if account["party_id"] is None:
        # Condition 1. Covers every staff account in this version.
        raise ClaimNotEligible("account is not bound to a party")

    if kind is ResourceKind.PROPERTY:
        # FAIL CLOSED. The adopted rule is for REQUEST claims, and it cannot
        # be transferred mechanically: `properties` has no `party_id` at all —
        # the party relationship for a property lives in
        # `party_property_relations`, which RFC-001 decision 1 / R4.5 forbids
        # as an authorization source. Reading the contract's "resource party
        # relationship" as that table would contradict a FINAL decision, and
        # reading it any other way would be inventing one.
        raise PropertyClaimUndecided(resource_id)

    resource_party = session.execute(
        text("SELECT party_id FROM turab.requests WHERE request_id = :r"),
        {"r": resource_id},
    ).scalar_one_or_none()
    if resource_party is None:
        raise ClaimRejected("NOT_FOUND", f"{kind.value} {resource_id} does not exist")

    if account["party_id"] != resource_party:
        # Condition 2. Not repaired here, and not silently tolerated.
        raise PartyLinkageNeedsReview(resource_id)

    if verification_contact_point_id is None:
        raise ClaimNotEligible("no verification contact point was presented")

    # Condition 3: the presented contact point must be THIS account's own
    # login contact point, the one the OTP flow verified for it.
    if account["login_contact_point_id"] != verification_contact_point_id:
        raise ClaimNotEligible(
            "the contact point is not this account's verified login contact point"
        )

    verified = session.execute(
        text(
            """SELECT control_status::text FROM turab.contact_points
                WHERE contact_point_id = :c"""
        ),
        {"c": verification_contact_point_id},
    ).scalar_one_or_none()
    if verified != "VERIFIED_CONTROL":
        raise ClaimNotEligible("the contact point is not verified")

    # Condition 4: and it must reach the resource's party.
    reaches = session.execute(
        text(
            """SELECT 1 FROM turab.party_contact_points
                WHERE party_id = :p AND contact_point_id = :c"""
        ),
        {"p": resource_party, "c": verification_contact_point_id},
    ).first()
    if reaches is None:
        raise ClaimNotEligible(
            "the contact point is not linked to the resource's party"
        )


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

    # Serialise concurrent claims on the SAME record. Without this lock, two
    # attempts can both read "unclaimed" and both insert, producing exactly
    # the ambiguous state INV-1 exists to prevent.
    lock_table = "properties" if kind is ResourceKind.PROPERTY else "requests"
    lock_column = "property_id" if kind is ResourceKind.PROPERTY else "request_id"
    locked = session.execute(
        text(f"SELECT 1 FROM turab.{lock_table} WHERE {lock_column} = :r FOR UPDATE"),
        {"r": resource_id},
    ).first()
    if locked is None:
        raise ClaimRejected("NOT_FOUND", f"{kind.value} {resource_id} does not exist")

    # The contract's declared condition, checked here and not earlier: an
    # eligibility check on a separate read session says what WAS true.
    assert_claim_eligibility(
        session, kind=kind, resource_id=resource_id, account_id=account_id,
        verification_contact_point_id=verification_contact_point_id,
    )

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
