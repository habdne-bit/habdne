"""Object authorization against the frozen schema.

Ref: RFC-001 §4 (R4.1-R4.15), §5 (R5.3), decisions 1, 2, 4; Q9; INV-1.
Scenario ids (S..) are the ones in RFC-001 §11.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from turab.auth.loaders import (
    ResourceKind,
    load_offer,
    load_opportunity,
    load_property,
    load_request,
)
from turab.auth.policy import DenyReason
from turab.auth.subject import AccountNotResolvable, resolve_subject

UNKNOWN = uuid.UUID("00000000-0000-4000-8000-0000000000ff")


# --- subject resolution ----------------------------------------------------

def test_subject_reads_party_and_roles_from_the_database(session, subject_of, ids):
    s = subject_of(ids.ACC_AMINA)
    assert s.party_id == ids.AMINA
    assert s.has_party and s.is_usable
    assert {r.value for r in s.roles} == {"CUSTOMER"}


def test_staff_account_has_no_party(session, subject_of, ids):
    """R3.1. Nullable party_id is real; staff accounts have none."""
    s = subject_of(ids.ACC_OPERATOR)
    assert s.party_id is None and not s.has_party


@pytest.mark.parametrize("status", ["DISABLED", "SUSPENDED", "INVITED"])
def test_non_activated_account_resolves_to_no_authority(session, ids, status):
    """S16i / S16j, R4.11a. Account status is the only lever that ends
    claim-derived authority, so it is enforced at resolution."""
    session.execute(
        text("UPDATE turab.user_accounts SET status = :s WHERE account_id = :a"),
        {"s": status, "a": ids.ACC_AMINA},
    )
    with pytest.raises(AccountNotResolvable):
        resolve_subject(session, ids.ACC_AMINA)


def test_unknown_account_is_not_resolvable(session):
    with pytest.raises(AccountNotResolvable):
        resolve_subject(session, UNKNOWN)


# --- REQUEST (R4.8) --------------------------------------------------------

def test_customer_reads_own_claimed_request(session, subject_of, ids):
    """S01."""
    result = load_request(session, subject_of(ids.ACC_AMINA), ids.REQ_AMINA)
    assert result.authorized and result.row["request_id"] == ids.REQ_AMINA


def test_customer_cannot_read_another_customers_request(session, subject_of, ids):
    """S02 / K02."""
    result = load_request(session, subject_of(ids.ACC_KHADIJA), ids.REQ_AMINA)
    assert not result.authorized
    assert result.reason is DenyReason.OBJECT_NOT_AUTHORIZED


def test_party_match_alone_is_not_enough_for_an_assisted_request(session, subject_of, ids):
    """S16c / R4.8. The agency's assisted request carries its party already."""
    row = session.execute(
        text("SELECT party_id, claim_status::text AS c FROM turab.requests WHERE request_id=:r"),
        {"r": ids.REQ_AGENCY_ASSISTED},
    ).mappings().one()
    assert row["party_id"] == ids.AGENCY and row["c"] == "UNCLAIMED"

    session.execute(
        text("UPDATE turab.user_accounts SET party_id=:p WHERE account_id=:a"),
        {"p": ids.AGENCY, "a": ids.ACC_KHADIJA},
    )
    subject = resolve_subject(session, ids.ACC_KHADIJA)
    assert subject.party_id == ids.AGENCY  # party matches...
    result = load_request(session, subject, ids.REQ_AGENCY_ASSISTED)
    assert not result.authorized  # ...and it is still refused


def test_customer_with_no_party_is_refused(session, subject_of, ids):
    """S05 / R3.1."""
    session.execute(
        text("UPDATE turab.user_accounts SET party_id = NULL WHERE account_id = :a"),
        {"a": ids.ACC_AMINA},
    )
    subject = resolve_subject(session, ids.ACC_AMINA)
    result = load_request(session, subject, ids.REQ_AMINA)
    assert not result.authorized and result.reason is DenyReason.NO_PARTY


# --- PROPERTY (decision 1, R4.1-R4.3) --------------------------------------

def test_relationship_alone_never_grants_property_access(session, subject_of, ids):
    """S12 / decision 1. Brahim is OWNER_DECLARED on the villa and is refused."""
    relations = session.execute(
        text(
            """SELECT relation_code FROM turab.party_property_relations
                WHERE party_id=:p AND property_id=:prop"""
        ),
        {"p": ids.BRAHIM, "prop": ids.VILLA_SELF_MANAGED},
    ).scalars().all()
    assert "OWNER_DECLARED" in relations  # the relation really exists

    session.execute(
        text("UPDATE turab.user_accounts SET party_id=:p WHERE account_id=:a"),
        {"p": ids.BRAHIM, "a": ids.ACC_KHADIJA},
    )
    subject = resolve_subject(session, ids.ACC_KHADIJA)
    result = load_property(session, subject, ids.VILLA_SELF_MANAGED)
    assert not result.authorized


def test_claim_event_grants_property_access(session, subject_of, ids):
    """S15 / R4.1. The claimed house differs from the villa only by the claim."""
    result = load_property(session, subject_of(ids.ACC_AMINA), ids.CLAIMED_HOUSE)
    assert result.authorized


def test_property_authority_is_account_scoped_not_party_scoped(session, subject_of, ids):
    """S16b / R4.2. A second account of the same party does not inherit."""
    first = subject_of(ids.ACC_AMINA)
    second = subject_of(ids.ACC_AMINA_SECOND)
    assert first.party_id == second.party_id == ids.AMINA
    assert load_property(session, first, ids.CLAIMED_HOUSE).authorized
    assert not load_property(session, second, ids.CLAIMED_HOUSE).authorized


def test_expired_relation_does_not_revoke_a_claimed_owner(session, subject_of, ids):
    """S16a / R4.6. A direct benefit of decision 1."""
    expired = session.execute(
        text(
            """SELECT count(*) FROM turab.party_property_relations
                WHERE property_id=:p AND valid_to IS NOT NULL AND valid_to < now()"""
        ),
        {"p": ids.CLAIMED_HOUSE},
    ).scalar_one()
    assert expired >= 1
    assert load_property(session, subject_of(ids.ACC_AMINA), ids.CLAIMED_HOUSE).authorized


def test_orphan_property_with_null_creator_matches_nobody(session, subject_of, ids):
    """S11 / R4.3. NULL must match nobody, not everybody."""
    for account in (ids.ACC_AMINA, ids.ACC_KHADIJA, ids.ACC_AMINA_SECOND):
        assert not load_property(session, subject_of(account), ids.ORPHAN_LAND).authorized


def test_assisted_unclaimed_property_has_no_authorized_customer(session, subject_of, ids):
    """S14 / R4.10."""
    for account in (ids.ACC_AMINA, ids.ACC_KHADIJA):
        assert not load_property(session, subject_of(account), ids.VILLA_SELF_MANAGED).authorized


def test_alias_resolves_to_canonical_before_the_authority_check(session, subject_of, ids):
    """S13 / R4.9. Identity resolution must not strip a real owner of access."""
    alias_id = uuid.UUID("f4000000-0000-4000-8000-0000000000b1")
    session.execute(
        text(
            """INSERT INTO turab.properties
                 (property_id, property_type, management_mode, claim_status)
               VALUES (:id, 'HOUSE_VILLA', 'ASSISTED', 'UNCLAIMED')"""
        ),
        {"id": alias_id},
    )
    candidate = uuid.uuid4()
    session.execute(
        text(
            """INSERT INTO turab.property_identity_candidates
                 (identity_candidate_id, property_a_id, property_b_id, review_status)
               VALUES (:c, :a, :b, 'PENDING_REVIEW')"""
        ),
        {"c": candidate, "a": alias_id, "b": ids.CLAIMED_HOUSE},
    )
    session.execute(
        text(
            """INSERT INTO turab.property_identity_aliases
                 (alias_property_id, canonical_property_id,
                  source_identity_candidate_id, resolved_by_account_id)
               VALUES (:alias, :canon, :c, :acct)"""
        ),
        {"alias": alias_id, "canon": ids.CLAIMED_HOUSE, "c": candidate,
         "acct": ids.ACC_OPERATOR},
    )
    result = load_property(session, subject_of(ids.ACC_AMINA), alias_id)
    assert result.authorized
    assert result.resource_id == ids.CLAIMED_HOUSE


# --- PROPERTY_OFFER (Q9 / §4.6) -------------------------------------------

def test_offer_creator_is_authorized(session, subject_of, ids):
    """S16f / §4.6 condition 1."""
    session.execute(
        text("UPDATE turab.property_offers SET created_by_account_id=:a WHERE offer_id=:o"),
        {"a": ids.ACC_KHADIJA, "o": ids.OFFER_BROKER_SALE},
    )
    assert load_offer(session, subject_of(ids.ACC_KHADIJA), ids.OFFER_BROKER_SALE).authorized


def test_claimant_reads_own_offer_on_claimed_property(session, subject_of, ids):
    """S16d / §4.6 condition 2. Amina claimed the house; the offer is her party's."""
    assert load_offer(session, subject_of(ids.ACC_AMINA), ids.OFFER_ON_CLAIMED).authorized


def test_property_claim_does_not_open_another_partys_offer(session, subject_of, ids):
    """S16e / R4.13. The rule that stands between a property claim and a
    competitor's commercial terms."""
    other = uuid.UUID("f6000000-0000-4000-8000-0000000000c1")
    session.execute(
        text(
            """INSERT INTO turab.property_offers
                 (offer_id, property_id, party_id, transaction_type, status,
                  asking_price_dzd, created_by_account_id)
               VALUES (:o, :p, :party, 'SALE', 'ACTIVE', 21000000, :creator)"""
        ),
        {"o": other, "p": ids.CLAIMED_HOUSE, "party": ids.AGENCY,
         "creator": ids.ACC_OPERATOR},
    )
    # Amina holds the claim on the parent property, but this offer is the
    # agency's and she did not create it.
    assert not load_offer(session, subject_of(ids.ACC_AMINA), other).authorized


def test_offer_party_match_alone_never_grants(session, subject_of, ids):
    """S16g / R4.12. Party match without a parent claim is not authority."""
    session.execute(
        text("UPDATE turab.user_accounts SET party_id=:p WHERE account_id=:a"),
        {"p": ids.BRAHIM, "a": ids.ACC_KHADIJA},
    )
    subject = resolve_subject(session, ids.ACC_KHADIJA)
    owner_offer = session.execute(
        text("SELECT party_id FROM turab.property_offers WHERE offer_id=:o"),
        {"o": ids.OFFER_OWNER_SALE},
    ).scalar_one()
    assert owner_offer == subject.party_id  # party matches...
    assert not load_offer(session, subject, ids.OFFER_OWNER_SALE).authorized  # ...refused


def test_relations_never_grant_offer_access(session, subject_of, ids):
    """S16h / R4.12."""
    session.execute(
        text("UPDATE turab.user_accounts SET party_id=:p WHERE account_id=:a"),
        {"p": ids.AGENCY, "a": ids.ACC_KHADIJA},
    )
    subject = resolve_subject(session, ids.ACC_KHADIJA)
    assert not load_offer(session, subject, ids.OFFER_OWNER_SALE).authorized


def test_unclaimed_parent_blocks_condition_two(session, subject_of, ids):
    """§4.6 condition 2 requires the parent to be CLAIMED."""
    session.execute(
        text(
            """UPDATE turab.properties
                  SET claim_status='UNCLAIMED', management_mode='ASSISTED'
                WHERE property_id=:p"""
        ),
        {"p": ids.CLAIMED_HOUSE},
    )
    assert not load_offer(session, subject_of(ids.ACC_AMINA), ids.OFFER_ON_CLAIMED).authorized


# --- OPPORTUNITY -----------------------------------------------------------

def test_unknown_opportunity_is_refused(session, subject_of, ids):
    """S09. Transitive ownership via the request."""
    assert not load_opportunity(session, subject_of(ids.ACC_AMINA), UNKNOWN).authorized


# --- cross-account sweep (R10.3b) -----------------------------------------

def test_cross_account_uuid_access_is_refused_for_every_resource(session, subject_of, ids):
    """R10.3b. The behavioural proof that the layering holds end to end."""
    intruder = subject_of(ids.ACC_KHADIJA)
    cases = [
        (load_request, ids.REQ_AMINA),
        (load_property, ids.CLAIMED_HOUSE),
        (load_offer, ids.OFFER_ON_CLAIMED),
        (load_property, ids.VILLA_SELF_MANAGED),
        (load_property, ids.ORPHAN_LAND),
    ]
    for loader, resource_id in cases:
        result = loader(session, intruder, resource_id)
        assert not result.authorized, f"{loader.__name__} leaked {resource_id}"
