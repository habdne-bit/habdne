"""Slice 4 step 3: the candidate set (G4-8; G4-9 (a)).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-8 and G4-9, decided in the review of
4538a2d; `src/turab/matching/candidates.py`; mandatory tests 1, 6
(narrowed) and 9; red-team C01, D05, E02.

The function reads and never writes. Every fixture here is inserted inside
the rolled-back `session`, so each test sees only the world it built plus
the dev fixtures. The full-scan tests therefore assert about THEIR
properties, not about the whole set.
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from turab.matching import candidates as cs
from turab.matching.candidates import Exclusion


def _one(session, sql, **p):
    return session.execute(text(sql), p).scalar_one()


def _request(session, ids, intent="BUY", status="ACTIVE"):
    return _one(session, """
        INSERT INTO turab.requests (party_id, transaction_intent, status, management_mode,
                                    claim_status)
        VALUES (:p, CAST(:i AS turab.request_transaction_intent),
                CAST(:s AS turab.request_status), 'ASSISTED', 'UNCLAIMED')
        RETURNING request_id""", p=ids.BRAHIM, i=intent, s=status)


def _property(session, supply="PUBLIC", availability="AVAILABLE"):
    return _one(session, """
        INSERT INTO turab.properties (property_type, supply_mode, current_availability,
                                      management_mode, claim_status)
        VALUES ('APARTMENT', CAST(:s AS turab.supply_mode),
                CAST(:a AS turab.availability_status), 'ASSISTED', 'UNCLAIMED')
        RETURNING property_id""", s=supply, a=availability)


def _offer(session, ids, prop, kind="SALE", status="ACTIVE", offer_id=None):
    return _one(session, """
        INSERT INTO turab.property_offers (offer_id, property_id, party_id, transaction_type,
                                           status)
        VALUES (COALESCE(:id, gen_random_uuid()), :p, :party,
                CAST(:t AS turab.transaction_type), CAST(:s AS turab.offer_status))
        RETURNING offer_id""", id=offer_id, p=prop, party=ids.BRAHIM, t=kind, s=status)


def _alias(session, ids, alias, canonical):
    """The identity flow's writes, in its order: candidate, alias, status."""
    cid = _one(session, """INSERT INTO turab.property_identity_candidates
                                  (property_a_id, property_b_id)
                           VALUES (:a, :b) RETURNING identity_candidate_id""",
               a=alias, b=canonical)
    session.execute(text("""INSERT INTO turab.property_identity_aliases
                                   (alias_property_id, canonical_property_id,
                                    source_identity_candidate_id, resolved_by_account_id)
                            VALUES (:a, :c, :cid, :acct)"""),
                    {"a": alias, "c": canonical, "cid": cid, "acct": ids.ACC_REVIEWER})
    session.execute(text("""UPDATE turab.property_identity_candidates
                               SET review_status = 'CONFIRMED_SAME'
                             WHERE identity_candidate_id = :cid"""), {"cid": cid})


def _pairs(result):
    return {(c.property_id, c.offer_id) for c in result.candidates}


def _reasons(result):
    return {e.property_id: e.reason for e in result.excluded}


# --- transaction compatibility (mandatory test 1, C01) --------------------------------

@pytest.mark.parametrize("intent, qualifying, other", [("BUY", "SALE", "RENT"),
                                                        ("RENT", "RENT", "SALE")])
def test_a_request_evaluates_only_offers_of_its_transaction_type(session, ids, intent,
                                                                qualifying, other):
    req = _request(session, ids, intent=intent)
    prop = _property(session)
    good = _offer(session, ids, prop, kind=qualifying)
    _offer(session, ids, prop, kind=other)
    result = cs.candidate_set(session, req, [prop])
    assert _pairs(result) == {(prop, good)}
    assert result.offer_transaction_type == qualifying


def test_a_property_with_only_the_other_type_is_reported_not_evaluated(session, ids):
    req = _request(session, ids, intent="BUY")
    prop = _property(session)
    _offer(session, ids, prop, kind="RENT")
    result = cs.candidate_set(session, req, [prop])
    assert result.candidates == ()
    assert _reasons(result) == {prop: Exclusion.NO_QUALIFYING_OFFER}


def test_the_schema_refuses_a_buy_match_on_a_rent_offer(session, ids):
    """The backstop, labelled: the frozen trigger enforces C01 itself."""
    from sqlalchemy.exc import DBAPIError

    req = _request(session, ids, intent="BUY")
    prop = _property(session)
    rent = _offer(session, ids, prop, kind="RENT")
    policy_id, version = session.execute(text(
        "SELECT matching_policy_id, version FROM turab.matching_policies WHERE active")).one()
    savepoint = session.begin_nested()
    with pytest.raises(DBAPIError, match="Request transaction intent does not match"):
        session.execute(text("""
            INSERT INTO turab.match_candidates
              (request_id, property_id, evaluated_offer_id, matching_policy_id,
               matching_policy_version, request_version, property_version, offer_version,
               eligibility, hard_gate_status, information_gate_status, request_freshness,
               property_freshness, freshness_gate_status, permission_gate_status,
               request_snapshot, property_snapshot, input_hash)
            VALUES (:r, :p, :o, :pol, :v, 1, 1, 1, 'REJECTED', 'FAIL', 'PASS', 'FRESH',
                    'FRESH', 'PASS', 'PASS', '{}', '{}', 'fixture')"""),
            {"r": req, "p": prop, "o": rent, "pol": policy_id, "v": version})
    savepoint.rollback()


# --- one candidate per qualifying offer (G4-8) -----------------------------------------

def test_every_qualifying_offer_of_a_property_is_its_own_candidate(session, ids):
    req = _request(session, ids)
    prop = _property(session)
    first, second = _offer(session, ids, prop), _offer(session, ids, prop)
    result = cs.candidate_set(session, req, [prop])
    assert _pairs(result) == {(prop, first), (prop, second)}
    versions = {(c.property_version, c.offer_version) for c in result.candidates}
    assert versions == {(1, 1)}


@pytest.mark.parametrize("status", ["DRAFT", "PENDING_INFO", "PAUSED", "WITHDRAWN", "CLOSED"])
def test_an_offer_that_is_not_active_does_not_qualify(session, ids, status):
    req = _request(session, ids)
    prop = _property(session)
    _offer(session, ids, prop, status=status)
    result = cs.candidate_set(session, req, [prop])
    assert result.candidates == ()
    assert _reasons(result) == {prop: Exclusion.NO_QUALIFYING_OFFER}


# --- request status (G4-8) ---------------------------------------------------------------

@pytest.mark.parametrize("status", ["ACTIVE", "NEEDS_CONFIRMATION"])
def test_an_active_or_stale_request_is_matched(session, ids, status):
    req = _request(session, ids, status=status)
    prop = _property(session)
    offer = _offer(session, ids, prop)
    assert _pairs(cs.candidate_set(session, req, [prop])) == {(prop, offer)}


@pytest.mark.parametrize("status", ["RAW", "CONTACTED", "QUALIFIED", "PAUSED", "CLOSED"])
def test_any_other_request_status_is_refused(session, ids, status):
    req = _request(session, ids, status=status)
    with pytest.raises(cs.RequestNotMatchable) as refused:
        cs.candidate_set(session, req, [])
    assert refused.value.status == status


def test_a_missing_request_is_refused(session):
    with pytest.raises(cs.RequestNotFound):
        cs.candidate_set(session, uuid.uuid4(), [])


# --- canonical only (mandatory test 9, E02) ------------------------------------------------

def test_an_alias_is_never_a_candidate_and_is_reported_with_its_canonical(session, ids):
    req = _request(session, ids)
    canonical, alias = _property(session), _property(session)
    on_canonical = _offer(session, ids, canonical)
    _alias(session, ids, alias, canonical)
    result = cs.candidate_set(session, req, [alias, canonical])
    assert _pairs(result) == {(canonical, on_canonical)}
    [excluded] = result.excluded
    assert (excluded.property_id, excluded.reason) == (alias, Exclusion.IDENTITY_ALIAS)
    assert excluded.detail == {"canonical_property_id": canonical}


def test_a_qualifying_offer_on_an_alias_is_reported_as_unevaluable(session, ids):
    """The finding stated in candidates.py. The offer can be evaluated
    neither under the alias (the trigger forbids aliases) nor under its
    canonical record (the trigger requires the offer to belong to the matched
    property). It is reported, in a full scan too."""
    req = _request(session, ids)
    canonical, alias = _property(session), _property(session)
    stranded = _offer(session, ids, alias)
    _alias(session, ids, alias, canonical)
    for scope in ([alias], None):
        result = cs.candidate_set(session, req, scope)
        assert all(c.property_id != alias for c in result.candidates)
        entry = next(e for e in result.excluded if e.property_id == alias)
        assert entry.reason == Exclusion.OFFER_ON_ALIAS
        assert entry.detail == {"canonical_property_id": canonical, "offer_ids": [stranded]}


# --- availability (G4-8) --------------------------------------------------------------------

def test_an_unavailable_property_is_excluded_and_reported(session, ids):
    req = _request(session, ids)
    prop = _property(session, availability="UNAVAILABLE")
    _offer(session, ids, prop)
    for scope in ([prop], None):
        result = cs.candidate_set(session, req, scope)
        assert all(c.property_id != prop for c in result.candidates)
        assert _reasons(result)[prop] == Exclusion.PROPERTY_UNAVAILABLE


@pytest.mark.parametrize("availability", ["AVAILABLE", "POTENTIALLY_AVAILABLE",
                                          "UNDER_DISCUSSION", "TEMPORARILY_UNAVAILABLE",
                                          "NEEDS_CONFIRMATION", "UNKNOWN"])
def test_every_other_availability_is_evaluated(session, ids, availability):
    """Their effect belongs to the freshness gate (step 5), not to the set."""
    req = _request(session, ids)
    prop = _property(session, availability=availability)
    offer = _offer(session, ids, prop)
    assert _pairs(cs.candidate_set(session, req, [prop])) == {(prop, offer)}


# --- POTENTIAL without an offer (G4-9 (a); mandatory test 6, narrowed) ----------------------

def test_a_potential_property_without_willingness_context_is_not_evaluated(session, ids):
    """Mandatory test 6, its refusing half only: no willingness data exists
    in the schema, so a POTENTIAL property without an offer is reported,
    never evaluated."""
    req = _request(session, ids)
    prop = _property(session, supply="POTENTIAL")
    for scope in ([prop], None):
        result = cs.candidate_set(session, req, scope)
        assert all(c.property_id != prop for c in result.candidates)
        entry = next(e for e in result.excluded if e.property_id == prop)
        assert entry.reason == Exclusion.POTENTIAL_WITHOUT_OFFER
        assert "G4-9" in entry.detail["because"]


def test_a_potential_property_with_a_qualifying_offer_is_evaluated_through_it(session, ids):
    req = _request(session, ids)
    prop = _property(session, supply="POTENTIAL")
    offer = _offer(session, ids, prop)
    assert _pairs(cs.candidate_set(session, req, [prop])) == {(prop, offer)}


@pytest.mark.parametrize("supply", ["PUBLIC", "PRIVATE"])
def test_public_and_private_supply_are_both_matched(session, ids, supply):
    """B04: private supply takes part in internal matching."""
    req = _request(session, ids)
    prop = _property(session, supply=supply)
    offer = _offer(session, ids, prop)
    assert _pairs(cs.candidate_set(session, req, [prop])) == {(prop, offer)}


# --- property_ids, and what a full scan reports --------------------------------------------

def test_listed_ids_narrow_the_set_are_deduplicated_and_ordered(session, ids):
    req = _request(session, ids)
    a, b, c = (_property(session) for _ in range(3))
    offers = {p: _offer(session, ids, p) for p in (a, b, c)}
    missing = uuid.uuid4()
    result = cs.candidate_set(session, req, [c, a, a, missing])
    assert [x.property_id for x in result.candidates] == sorted([a, c])
    assert _pairs(result) == {(a, offers[a]), (c, offers[c])}
    assert _reasons(result) == {missing: Exclusion.PROPERTY_NOT_FOUND}


def test_an_empty_list_evaluates_nothing(session, ids):
    req = _request(session, ids)
    prop = _property(session)
    _offer(session, ids, prop)
    result = cs.candidate_set(session, req, [])
    assert result.candidates == () and result.excluded == ()


def test_a_full_scan_finds_every_qualifying_offer_and_stays_silent_on_the_rest(session, ids):
    req = _request(session, ids, intent="BUY")
    sale = _property(session)
    sale_offer = _offer(session, ids, sale)
    rental = _property(session)
    _offer(session, ids, rental, kind="RENT")
    result = cs.candidate_set(session, req)
    assert (sale, sale_offer) in _pairs(result)
    assert rental not in {c.property_id for c in result.candidates}
    assert rental not in _reasons(result), \
        "a property with no relevant offer is not enumerated by a full scan"


def test_the_candidate_set_is_deterministic(session, ids):
    """Offers are inserted with ids in DESCENDING order, so their physical
    order differs from the declared one: the order comes from the query's
    ORDER BY, not from the heap."""
    req = _request(session, ids)
    props = [_property(session) for _ in range(3)]
    for n, p in enumerate(props):
        for k in (9, 5, 1):
            _offer(session, ids, p, offer_id=uuid.UUID(int=(n + 1) * 1000 + k))
    first = cs.candidate_set(session, req, props)
    assert cs.candidate_set(session, req, list(reversed(props))) == first
    keys = [(c.property_id, c.offer_id) for c in first.candidates]
    assert keys == sorted(keys)


# --- read-only --------------------------------------------------------------------------------

def test_computing_the_set_writes_nothing(session, ids):
    req = _request(session, ids)
    prop = _property(session)
    _offer(session, ids, prop)
    tables = ("requests", "properties", "property_offers", "match_candidates",
              "match_criterion_results", "match_diagnostic_runs", "audit_log", "tasks")

    def counts():
        return {t: _one(session, f"SELECT count(*) FROM turab.{t}") for t in tables}

    before = counts()
    cs.candidate_set(session, req)
    cs.candidate_set(session, req, [prop])
    assert counts() == before
