"""INV-1 — ambiguous claim authority fails closed.

Read half:  a resource claimed by more than one distinct account grants
            authority to none, and the condition is audited.
Write half: the claim command rejects a second claim on an already-claimed
            resource, except an idempotent replay by the same actor.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from turab.auth.audit import AccessEvent
from turab.auth.loaders import (
    ClaimAuthorityConflict,
    ResourceKind,
    claim_authority_accounts,
    load_property,
)
from turab.auth.policy import DenyReason
from turab.services.claims import (
    ClaimAuthorityConflictExists,
    ClaimOutcome,
    ClaimRejected,
    ResourceAlreadyClaimed,
    claim_record,
)


def _add_claim(session, property_id, account_id):
    session.execute(
        text(
            """INSERT INTO turab.record_claim_events
                 (property_id, claimed_by_account_id) VALUES (:p, :a)"""
        ),
        {"p": property_id, "a": account_id},
    )


# --- read half -------------------------------------------------------------

def test_single_claim_grants_authority(session, subject_of, ids):
    accounts = claim_authority_accounts(session, ResourceKind.PROPERTY, ids.CLAIMED_HOUSE)
    assert accounts == frozenset({ids.ACC_AMINA})
    assert load_property(session, subject_of(ids.ACC_AMINA), ids.CLAIMED_HOUSE).authorized


def test_two_distinct_claimants_grant_authority_to_nobody(session, subject_of, ids):
    """INV-1. Not 'first wins', not 'latest wins' — nobody."""
    _add_claim(session, ids.CLAIMED_HOUSE, ids.ACC_KHADIJA)
    assert len(claim_authority_accounts(session, ResourceKind.PROPERTY, ids.CLAIMED_HOUSE)) == 2

    for account in (ids.ACC_AMINA, ids.ACC_KHADIJA, ids.ACC_ADMIN):
        with pytest.raises(ClaimAuthorityConflict):
            load_property(session, subject_of(account), ids.CLAIMED_HOUSE)


def test_conflict_is_audited_and_surfaces_as_a_conflict(session, subject_of, ids,
                                                        access_for, auditor):
    """The condition must be diagnosable, so it is NOT concealed as a 404."""
    _add_claim(session, ids.CLAIMED_HOUSE, ids.ACC_KHADIJA)
    access = access_for(subject_of(ids.ACC_AMINA))
    result = access.read_resource(
        ResourceKind.PROPERTY, ids.CLAIMED_HOUSE, "getMePropertiesPropertyId"
    )
    assert not result.authorized
    assert result.reason is DenyReason.CLAIM_AUTHORITY_CONFLICT

    records = auditor.sink.of(AccessEvent.CLAIM_AUTHORITY_CONFLICT)
    assert len(records) == 1
    record = records[0]
    assert record.reason_code == "CLAIM_AUTHORITY_CONFLICT"
    assert record.extra["claim_account_count"] == 2
    assert record.extra["requires"] == "OPERATIONAL_RESOLUTION"


def test_duplicate_claim_rows_by_the_same_account_are_not_a_conflict(session, subject_of, ids):
    """Ambiguity is about DISTINCT accounts, not row count."""
    _add_claim(session, ids.CLAIMED_HOUSE, ids.ACC_AMINA)
    assert claim_authority_accounts(
        session, ResourceKind.PROPERTY, ids.CLAIMED_HOUSE
    ) == frozenset({ids.ACC_AMINA})
    assert load_property(session, subject_of(ids.ACC_AMINA), ids.CLAIMED_HOUSE).authorized


# --- write half ------------------------------------------------------------

def test_claiming_an_assisted_record_succeeds(session, ids):
    result = claim_record(
        session, kind=ResourceKind.REQUEST, resource_id=ids.REQ_KHADIJA_ASSISTED,
        account_id=ids.ACC_KHADIJA, verification_contact_point_id=ids.CP_KHADIJA,
    )
    assert result.outcome is ClaimOutcome.CLAIMED
    state = session.execute(
        text(
            """SELECT management_mode::text AS m, claim_status::text AS c
                 FROM turab.requests WHERE request_id=:p"""
        ),
        {"p": ids.REQ_KHADIJA_ASSISTED},
    ).mappings().one()
    assert state["m"] == "SHARED_MANAGEMENT" and state["c"] == "CLAIMED"


def test_second_claim_by_another_account_is_rejected(session, ids):
    """INV-1 write half. The second claim is refused, not layered on.

    Both accounts here are ELIGIBLE — two accounts bound to the same party
    (EC1). That matters now that eligibility is enforced: an ineligible second
    claimant would be refused by the contract's condition, and the test would
    be proving eligibility instead of INV-1.
    """
    claim_record(session, kind=ResourceKind.REQUEST,
                 resource_id=ids.REQ_AMINA_ASSISTED, account_id=ids.ACC_AMINA,
                 verification_contact_point_id=ids.CP_AMINA)
    with pytest.raises(ResourceAlreadyClaimed) as exc:
        claim_record(session, kind=ResourceKind.REQUEST,
                     resource_id=ids.REQ_AMINA_ASSISTED,
                     account_id=ids.ACC_AMINA_SECOND,
                     verification_contact_point_id=ids.CP_AMINA_SECOND)
    assert exc.value.code == "RESOURCE_ALREADY_CLAIMED"
    # and no ambiguity was created by the attempt
    assert len(claim_authority_accounts(
        session, ResourceKind.REQUEST, ids.REQ_AMINA_ASSISTED)) == 1


def test_replay_by_the_same_actor_is_idempotent(session, ids):
    """The one permitted exception: same actor, same resource."""
    first = claim_record(session, kind=ResourceKind.REQUEST,
                         resource_id=ids.REQ_KHADIJA_ASSISTED, account_id=ids.ACC_KHADIJA,
                         verification_contact_point_id=ids.CP_KHADIJA)
    before = session.execute(
        text("SELECT count(*) FROM turab.record_claim_events WHERE property_id=:p"),
        {"p": ids.REQ_KHADIJA_ASSISTED},
    ).scalar_one()

    replay = claim_record(session, kind=ResourceKind.REQUEST,
                          resource_id=ids.REQ_KHADIJA_ASSISTED, account_id=ids.ACC_KHADIJA,
                          verification_contact_point_id=ids.CP_KHADIJA)
    assert replay.outcome is ClaimOutcome.REPLAYED
    assert replay.claim_event_id == first.claim_event_id

    after = session.execute(
        text("SELECT count(*) FROM turab.record_claim_events WHERE property_id=:p"),
        {"p": ids.REQ_KHADIJA_ASSISTED},
    ).scalar_one()
    assert after == before, "a replay must not append a second claim event"


def test_claim_grants_authority_that_did_not_exist_before(session, subject_of, ids):
    """S14 -> S15. The claim event is what changes, and it is what grants.

    Moved from PROPERTY to REQUEST: PROPERTY claiming now fails closed until
    its eligibility rule is decided, so the only claim this suite can make is
    the one whose rule is adopted.
    """
    from turab.auth.loaders import load_request

    before = load_request(
        session, subject_of(ids.ACC_KHADIJA), ids.REQ_KHADIJA_ASSISTED
    )
    assert not before.authorized, "an UNCLAIMED assisted record grants nothing"
    claim_record(session, kind=ResourceKind.REQUEST,
                 resource_id=ids.REQ_KHADIJA_ASSISTED, account_id=ids.ACC_KHADIJA,
                 verification_contact_point_id=ids.CP_KHADIJA)
    after = load_request(
        session, subject_of(ids.ACC_KHADIJA), ids.REQ_KHADIJA_ASSISTED
    )
    assert after.authorized


def test_claiming_an_already_conflicted_resource_is_rejected(session, ids):
    """A claimant replaying must not make an ambiguous resource look settled."""
    _add_claim_for_request(session, ids.REQ_KHADIJA_ASSISTED, ids.ACC_KHADIJA)
    _add_claim_for_request(session, ids.REQ_KHADIJA_ASSISTED, ids.ACC_AMINA_SECOND)
    with pytest.raises(ClaimAuthorityConflictExists):
        claim_record(session, kind=ResourceKind.REQUEST,
                     resource_id=ids.REQ_KHADIJA_ASSISTED,
                     account_id=ids.ACC_KHADIJA,
                     verification_contact_point_id=ids.CP_KHADIJA)


def test_a_self_managed_record_is_not_claimable(session, ids):
    """Even by the account that rightfully holds it.

    The claimant here is ELIGIBLE — Amina's own account, her own party, her
    own verified login contact point — so the refusal comes from the record's
    STATE, not from the contract's eligibility condition. Using an ineligible
    claimant would have tested eligibility twice and this rule not at all.
    """
    with pytest.raises(ClaimRejected) as exc:
        claim_record(session, kind=ResourceKind.REQUEST,
                     resource_id=ids.REQ_AMINA, account_id=ids.ACC_AMINA,
                     verification_contact_point_id=ids.CP_AMINA)
    assert exc.value.code == "RESOURCE_NOT_CLAIMABLE"


def test_claiming_an_unknown_resource_is_rejected(session, ids):
    with pytest.raises(ClaimRejected) as exc:
        claim_record(session, kind=ResourceKind.PROPERTY,
                     resource_id=uuid.uuid4(), account_id=ids.ACC_KHADIJA)
    assert exc.value.code == "NOT_FOUND"


def test_requests_conflict_the_same_way_as_properties(session, subject_of, ids):
    """INV-1 names REQUEST and PROPERTY; both are covered."""
    from turab.auth.loaders import load_request

    for account in (ids.ACC_AMINA, ids.ACC_KHADIJA):
        session.execute(
            text(
                """INSERT INTO turab.record_claim_events
                     (request_id, claimed_by_account_id) VALUES (:r, :a)"""
            ),
            {"r": ids.REQ_AMINA, "a": account},
        )
    with pytest.raises(ClaimAuthorityConflict):
        load_request(session, subject_of(ids.ACC_AMINA), ids.REQ_AMINA)


def _add_claim_for_request(session, request_id, account_id) -> None:
    """Insert a raw claim event, bypassing the command, to build the ambiguous
    state INV-1 exists to detect in data that predates the guard."""
    session.execute(
        text(
            """INSERT INTO turab.record_claim_events
                      (request_id, claimed_by_account_id)
               VALUES (:r, :a)"""
        ),
        {"r": request_id, "a": account_id},
    )
    session.flush()
