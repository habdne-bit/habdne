"""Slice 4 step 5: the freshness gate, the permission gate, and eligibility.

Ref: `docs/gate/SLICE_4_PLAN.md` G4-10 and G4-11, decided in the review of
f789a59, with its conditions (PUBLIC_LISTING_ALLOWED counts for internal
matching of the same resource; a missing or revoked permission stays visible
under NEEDS_CONFIRMATION); `src/turab/matching/eligibility.py`,
`snapshots.freshness_snapshot`, `snapshots.permission_snapshot`; mandatory
test 3; spec M-05, M-06; red-team B04, C03, G01.

Every fixture lives in the rolled-back `session`. Instants are explicit: the
run's instant `as_of` is passed, never read from a clock inside the engine.
"""
from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import text

from turab.matching import (canonical, criteria, eligibility, hard_gate, policy, snapshots)
from turab.services import freshness as slice2_freshness

AS_OF = datetime(2026, 9, 29, 12, 0, 0, tzinfo=timezone.utc)
DAY = timedelta(days=1)


def _one(session, sql, **p):
    return session.execute(text(sql), p).scalar_one()


# --- builders -----------------------------------------------------------------------------

def _request(session, ids, confirmed=AS_OF - DAY, doc_required=False):
    req = _one(session, """
        INSERT INTO turab.requests (party_id, transaction_intent, status, management_mode,
                                    claim_status, budget_max_dzd, last_confirmed_at)
        VALUES (:p, 'BUY', 'ACTIVE', 'ASSISTED', 'UNCLAIMED', 30000000, :c)
        RETURNING request_id""", p=ids.BRAHIM, c=confirmed)
    if doc_required:
        session.execute(text("""
            INSERT INTO turab.request_criteria (request_id, criterion_code, importance,
                                                operator, value)
            VALUES (:r, 'DOCUMENT_TYPE', 'REQUIRED', 'EQ', '"LAND_BOOK"')"""), {"r": req})
    return req


def _property(session, confirmed=AS_OF - DAY, ptype="LAND"):
    return _one(session, """
        INSERT INTO turab.properties (property_type, supply_mode, management_mode, claim_status,
                                      availability_last_confirmed_at, current_availability)
        VALUES (CAST(:t AS turab.property_type), 'PUBLIC', 'ASSISTED', 'UNCLAIMED', :c,
                'AVAILABLE')
        RETURNING property_id""", t=ptype, c=confirmed)


def _offer(session, party, prop, terms=AS_OF - DAY, last=None, ask=20_000_000):
    return _one(session, """
        INSERT INTO turab.property_offers (property_id, party_id, transaction_type, status,
                                           asking_price_dzd, price_negotiable,
                                           commercial_terms_last_confirmed_at,
                                           last_confirmed_at)
        VALUES (:p, :party, 'SALE', 'ACTIVE', :ask, 'NO', :terms, :last)
        RETURNING offer_id""", p=prop, party=party, ask=ask, terms=terms, last=last)


def _grant(session, party, scope="PRIVATE_MATCHING_ONLY", granted_at=AS_OF - 2 * DAY):
    return _one(session, """
        INSERT INTO turab.consent_grants (party_id, scope, channel, consent_version, granted_at)
        VALUES (:party, CAST(:s AS turab.consent_scope), 'PHONE_CONFIRMED', 'v1', :at)
        RETURNING consent_id""", party=party, s=scope, at=granted_at)


def _bind(session, consent, purpose="PRIVATE_MATCHING_ONLY", offer=None, prop=None,
          bound_at=AS_OF - DAY):
    return _one(session, """
        INSERT INTO turab.resource_consent_bindings (consent_id, purpose, offer_id,
                                                     property_id, bound_at)
        VALUES (:c, CAST(:p AS turab.consent_scope), :o, :prop, :at)
        RETURNING consent_binding_id""", c=consent, p=purpose, o=offer, prop=prop, at=bound_at)


def _consented(session, ids, offer, purpose="PRIVATE_MATCHING_ONLY"):
    return _bind(session, _grant(session, ids.BRAHIM, purpose), purpose, offer=offer)


def _land_book(session, prop, value="LAND_BOOK"):
    session.execute(text("""
        INSERT INTO turab.property_attributes (property_id, attribute_definition_id, value)
        SELECT :p, attribute_definition_id, CAST(:v AS jsonb)
          FROM turab.attribute_definitions WHERE code = 'DOCUMENT_TYPE'"""),
        {"p": prop, "v": f'"{value}"'})


def _evaluate(session, req, prop, offer, as_of=AS_OF):
    """The whole of steps 4 and 5 for one candidate."""
    rs = snapshots.request_snapshot(session, req)
    plan = criteria.criteria_of(rs, criteria.read_vocabulary(session, rs))
    ps = snapshots.property_snapshot(session, prop)
    cs = snapshots.commercial_context_snapshot(session, offer)
    hard = hard_gate.evaluate(plan, rs, ps, cs)
    active = policy.load_active_policy(session)
    fs = snapshots.freshness_snapshot(rs, ps, cs, policy_version=active.version,
                                      threshold_days=active.freshness_threshold_days,
                                      as_of=as_of)
    perm = snapshots.permission_snapshot(session, offer, as_of=as_of)
    return eligibility.eligibility_of(hard, fs, perm), fs, perm


def _world(session, ids, **kw):
    """A candidate whose every criterion passes; its clocks and consent are
    set by the caller."""
    req = _request(session, ids, confirmed=kw.get("request_confirmed", AS_OF - DAY),
                   doc_required=kw.get("doc_required", False))
    prop = _property(session, confirmed=kw.get("property_confirmed", AS_OF - DAY))
    offer = _offer(session, ids.BRAHIM, prop, terms=kw.get("terms_confirmed", AS_OF - DAY))
    if kw.get("consent", True):
        _consented(session, ids, offer)
    return req, prop, offer


def _codes(result):
    return [r["reason_code"] for r in result.reasons]


# ======================================================================================
# Freshness (G4-11)
# ======================================================================================

@pytest.mark.parametrize("key", ["request", "property", "offer_terms"])
@pytest.mark.parametrize("age", [None, timedelta(days=0), "threshold", "threshold+1us"])
def test_freshness_agrees_with_the_slice_2_service_at_the_boundary(session, key, age):
    """The engine's pure comparison and `services.freshness.evaluate` give
    the same state on the same instant, at and just past the threshold."""
    days = policy.load_active_policy(session).freshness_threshold_days[key]
    delta = {"threshold": timedelta(days=days),
             "threshold+1us": timedelta(days=days, microseconds=1)}.get(age, age)
    last = None if delta is None else AS_OF - delta
    ours = snapshots._state(last, days, AS_OF)
    theirs = slice2_freshness.evaluate(session, last_confirmed_at=last, now=AS_OF, key=key)
    assert {"FRESH": "FRESH", "STALE": "STALE", "NEVER_CONFIRMED": "UNKNOWN"}[
        theirs.state.value] == ours["state"]
    assert ours["state"] == {None: "UNKNOWN", timedelta(0): "FRESH", "threshold": "FRESH",
                             "threshold+1us": "STALE"}[age]


def test_the_freshness_snapshot_reads_the_three_clocks(session, ids):
    """The offer is judged on `commercial_terms_last_confirmed_at`, not on
    `last_confirmed_at` (Slice 3 §3.4): a fresh `last_confirmed_at` does not
    refresh stale terms."""
    prop = _property(session, confirmed=None)
    offer = _offer(session, ids.BRAHIM, prop, terms=AS_OF - 20 * DAY, last=AS_OF - DAY)
    req = _request(session, ids, confirmed=AS_OF - 40 * DAY)
    fs = snapshots.freshness_snapshot(
        snapshots.request_snapshot(session, req), snapshots.property_snapshot(session, prop),
        snapshots.commercial_context_snapshot(session, offer), policy_version="0.2.0",
        threshold_days={"request": 30, "property": 30, "offer_terms": 14}, as_of=AS_OF)
    assert (fs["request"]["state"], fs["property"]["state"], fs["offer"]["state"]) == (
        "STALE", "UNKNOWN", "STALE")
    assert fs["property"]["basis"] == "NEVER_CONFIRMED"


def test_no_evaluated_offer_is_not_applicable(session, ids):
    req, prop = _request(session, ids), _property(session)
    fs = snapshots.freshness_snapshot(
        snapshots.request_snapshot(session, req), snapshots.property_snapshot(session, prop),
        None, policy_version="0.2.0",
        threshold_days={"request": 30, "property": 30, "offer_terms": 14}, as_of=AS_OF)
    assert fs["offer"] == {"state": "NOT_APPLICABLE", "basis": "NO_EVALUATED_OFFER",
                           "confirmed_at": None}


def test_the_instant_is_not_in_the_snapshot_and_states_decide_the_hash(session, ids):
    """G4-13: the hash excludes `evaluated_at` and includes the derived
    states. Two instants that see the same states give identical bytes; an
    instant that turns a state STALE gives different bytes."""
    req, prop, offer = _world(session, ids)
    args = (snapshots.request_snapshot(session, req), snapshots.property_snapshot(session, prop),
            snapshots.commercial_context_snapshot(session, offer))
    kw = {"policy_version": "0.2.0",
          "threshold_days": {"request": 30, "property": 30, "offer_terms": 14}}
    a = snapshots.freshness_snapshot(*args, **kw, as_of=AS_OF)
    b = snapshots.freshness_snapshot(*args, **kw, as_of=AS_OF + 2 * DAY)
    c = snapshots.freshness_snapshot(*args, **kw, as_of=AS_OF + 20 * DAY)
    assert canonical.canonical_bytes(a) == canonical.canonical_bytes(b)
    assert canonical.canonical_bytes(a) != canonical.canonical_bytes(c)
    assert c["offer"]["state"] == "STALE"
    assert "as_of" not in canonical.canonical_bytes(a).decode()
    canonical.input_document(matching_policy_id=uuid.uuid4(), matching_policy_version="0.2.0",
                             rule_registry_digest="x", evaluated_offer_id=offer,
                             request_snapshot=args[0], property_snapshot=args[1],
                             commercial_context_snapshot=args[2], permission_snapshot={},
                             freshness_snapshot=a)


def test_a_naive_instant_is_refused(session, ids):
    req, prop, offer = _world(session, ids)
    with pytest.raises(ValueError, match="timezone-aware"):
        snapshots.permission_snapshot(session, offer, as_of=datetime(2026, 9, 29))
    with pytest.raises(ValueError, match="timezone-aware"):
        snapshots.freshness_snapshot(
            snapshots.request_snapshot(session, req), snapshots.property_snapshot(session, prop),
            None, policy_version="0.2.0",
            threshold_days={"request": 30, "property": 30, "offer_terms": 14},
            as_of=datetime(2026, 9, 29))


STATES = ("FRESH", "STALE", "UNKNOWN")


@pytest.mark.parametrize("request_state, property_state, offer_state",
                         list(itertools.product(STATES, STATES, STATES + ("NOT_APPLICABLE",))))
def test_the_freshness_gate_is_g4_11(request_state, property_state, offer_state):
    states = (request_state, property_state, offer_state)
    expected = ("FAIL" if "STALE" in states else
                "PASS" if all(s in ("FRESH", "NOT_APPLICABLE") for s in states) else "UNKNOWN")
    fs = {k: {"state": s, "basis": "NEVER_CONFIRMED" if s == "UNKNOWN" else s}
          for k, s in zip(("request", "property", "offer"), states)}
    status, reasons = eligibility.freshness_gate(fs)
    assert status == expected
    assert [(r["subject"], r["reason_code"]) for r in reasons] == [
        (k.upper(), {"STALE": f"{k.upper()}_STALE", "UNKNOWN": None}[s])
        for k, s in zip(("request", "property", "offer"), states) if s in ("STALE", "UNKNOWN")]


# ======================================================================================
# Permission (G4-10)
# ======================================================================================

@pytest.mark.parametrize("purpose", ["PRIVATE_MATCHING_ONLY", "PUBLIC_LISTING_ALLOWED"])
def test_a_current_matching_binding_on_the_offer_passes(session, ids, purpose):
    """B04 (PRIVATE_MATCHING_ONLY), and G4-10's decision: a valid
    PUBLIC_LISTING_ALLOWED binding counts for internal matching of the same
    offer. The sharing scope is recorded, and is not a matching input."""
    prop = _property(session)
    offer = _offer(session, ids.BRAHIM, prop)
    binding = _consented(session, ids, offer, purpose)
    perm = snapshots.permission_snapshot(session, offer, as_of=AS_OF)
    assert [(b["consent_binding_id"], b["bound_to"], b["state"]) for b in perm["bindings"]] == [
        (binding, "OFFER", "CURRENT")]
    assert perm["permission_scope"] == "SUMMARY_ONLY"
    assert eligibility.permission_gate(perm) == ("PASS", [])


def test_no_binding_is_unknown_with_the_next_action(session, ids):
    prop = _property(session)
    offer = _offer(session, ids.BRAHIM, prop)
    status, reasons = eligibility.permission_gate(
        snapshots.permission_snapshot(session, offer, as_of=AS_OF))
    assert status == "UNKNOWN"
    assert reasons == [{"gate": "PERMISSION", "subject": "OFFER",
                        "reason_code": "PERMISSION_MISSING", "basis": "NO_CURRENT_BINDING",
                        "next_action": "CONFIRM_PERMISSION"}]


@pytest.mark.parametrize("revocation", ["binding revoked", "grant REVOKED", "grant revoked_at"])
def test_only_revoked_bindings_fail_with_consent_revoked(session, ids, revocation):
    prop = _property(session)
    offer = _offer(session, ids.BRAHIM, prop)
    consent = _grant(session, ids.BRAHIM)
    binding = _bind(session, consent, offer=offer)
    if revocation == "binding revoked":
        session.execute(text("""UPDATE turab.resource_consent_bindings SET revoked_at = :at
                                 WHERE consent_binding_id = :b"""), {"at": AS_OF - DAY / 2,
                                                                     "b": binding})
    elif revocation == "grant REVOKED":
        session.execute(text("UPDATE turab.consent_grants SET status = 'REVOKED' "
                             "WHERE consent_id = :c"), {"c": consent})
    else:
        session.execute(text("UPDATE turab.consent_grants SET revoked_at = :at "
                             "WHERE consent_id = :c"), {"at": AS_OF + DAY, "c": consent})
    perm = snapshots.permission_snapshot(session, offer, as_of=AS_OF)
    assert [b["state"] for b in perm["bindings"]] == ["REVOKED"]
    status, reasons = eligibility.permission_gate(perm)
    assert (status, [r["reason_code"] for r in reasons]) == ("FAIL", ["CONSENT_REVOKED"])


def test_a_revoked_binding_beside_a_current_one_passes(session, ids):
    prop = _property(session)
    offer = _offer(session, ids.BRAHIM, prop)
    old = _bind(session, _grant(session, ids.BRAHIM), offer=offer)
    session.execute(text("UPDATE turab.resource_consent_bindings SET revoked_at = :at "
                         "WHERE consent_binding_id = :b"), {"at": AS_OF - DAY / 2, "b": old})
    _consented(session, ids, offer)
    assert eligibility.permission_gate(
        snapshots.permission_snapshot(session, offer, as_of=AS_OF))[0] == "PASS"


@pytest.mark.parametrize("late", ["bound_at", "granted_at"])
def test_a_binding_that_has_not_started_is_unknown_until_it_starts(session, ids, late):
    prop = _property(session)
    offer = _offer(session, ids.BRAHIM, prop)
    consent = _grant(session, ids.BRAHIM,
                     granted_at=AS_OF + DAY if late == "granted_at" else AS_OF - 2 * DAY)
    _bind(session, consent, offer=offer,
          bound_at=AS_OF + DAY if late == "bound_at" else AS_OF - DAY)
    before = snapshots.permission_snapshot(session, offer, as_of=AS_OF)
    after = snapshots.permission_snapshot(session, offer, as_of=AS_OF + 2 * DAY)
    assert [b["state"] for b in before["bindings"]] == ["NOT_STARTED"]
    status, reasons = eligibility.permission_gate(before)
    assert (status, reasons[0]["basis"]) == ("UNKNOWN", "NOT_STARTED")
    assert eligibility.permission_gate(after)[0] == "PASS"


def _relation(session, party, prop):
    session.execute(text("""
        INSERT INTO turab.party_property_relations (party_id, property_id, relation_code,
                                                    valid_from)
        VALUES (:party, :p, 'OWNER_DECLARED', :at)"""),
        {"party": party, "p": prop, "at": AS_OF - 10 * DAY})


def test_a_property_binding_counts_only_for_the_offers_own_party(session, ids):
    """G4-10: "the evaluated offer, or its property", and "the grant's party
    is the offer's party". The relation rows exist only because the frozen
    trigger requires one to WRITE a property binding; matching never reads
    them."""
    prop = _property(session)
    offer = _offer(session, ids.BRAHIM, prop)
    _relation(session, ids.AGENCY, prop)
    _bind(session, _grant(session, ids.AGENCY), prop=prop)
    perm = snapshots.permission_snapshot(session, offer, as_of=AS_OF)
    assert [(b["bound_to"], b["state"]) for b in perm["bindings"]] == [
        ("PROPERTY", "OTHER_PARTY")]
    assert eligibility.permission_gate(perm)[0] == "UNKNOWN"

    _relation(session, ids.BRAHIM, prop)
    _bind(session, _grant(session, ids.BRAHIM), prop=prop)
    perm = snapshots.permission_snapshot(session, offer, as_of=AS_OF)
    assert sorted(b["state"] for b in perm["bindings"]) == ["CURRENT", "OTHER_PARTY"]
    assert eligibility.permission_gate(perm)[0] == "PASS"


def test_a_grant_whose_scope_changed_after_binding_does_not_count(session, ids):
    prop = _property(session)
    offer = _offer(session, ids.BRAHIM, prop)
    consent = _grant(session, ids.BRAHIM)
    _bind(session, consent, offer=offer)
    session.execute(text("UPDATE turab.consent_grants SET scope = 'COMMUNICATION_ARCHIVE' "
                         "WHERE consent_id = :c"), {"c": consent})
    perm = snapshots.permission_snapshot(session, offer, as_of=AS_OF)
    assert [b["state"] for b in perm["bindings"]] == ["SCOPE_MISMATCH"]
    assert eligibility.permission_gate(perm)[0] == "UNKNOWN"


def test_other_purposes_are_not_matching_permission(session, ids):
    prop = _property(session)
    offer = _offer(session, ids.BRAHIM, prop)
    _consented(session, ids, offer, "CONTACT_BEFORE_SHARING")
    perm = snapshots.permission_snapshot(session, offer, as_of=AS_OF)
    assert perm["bindings"] == []
    assert eligibility.permission_gate(perm)[0] == "UNKNOWN"


@pytest.mark.parametrize("states, expected", [
    ((), "UNKNOWN"), (("CURRENT",), "PASS"), (("REVOKED",), "FAIL"),
    (("REVOKED", "REVOKED"), "FAIL"), (("REVOKED", "NOT_STARTED"), "UNKNOWN"),
    (("REVOKED", "CURRENT"), "PASS"), (("OTHER_PARTY",), "UNKNOWN"),
    (("OTHER_PARTY", "REVOKED"), "FAIL"), (("SCOPE_MISMATCH", "CURRENT"), "PASS"),
    (("SCOPE_MISMATCH",), "UNKNOWN"), (("NOT_STARTED",), "UNKNOWN"),
])
def test_the_permission_gate_is_g4_10(states, expected):
    status, _ = eligibility.permission_gate({"bindings": [{"state": s} for s in states]})
    assert status == expected


# ======================================================================================
# Eligibility (G4-11), and the review's condition
# ======================================================================================

def _hard(kind):
    """A HardGate from synthetic results: PASS; REQUIRED FAIL; REQUIRED
    UNKNOWN; or a soft UNKNOWN made blocking by `blocking_if_unknown`."""
    def result(code, importance, compatibility, blocking):
        return hard_gate.CriterionResult(
            request_criterion_id=None, criterion_code=code, ordinal=1, importance=importance,
            request_value={}, property_value=None, compatibility=compatibility,
            blocking=blocking, delta=None, evidence_level=None, evidence_claim_id=None,
            reason_code=None, rule_id="r", rule_version="1", explanation={})
    results = {"PASS": (result("A", "REQUIRED", "PASS", False),),
               "FAIL": (result("A", "REQUIRED", "FAIL", True),),
               "REQUIRED_UNKNOWN": (result("A", "REQUIRED", "UNKNOWN", True),),
               "SOFT_BLOCKING_UNKNOWN": (result("A", "REQUIRED", "PASS", False),
                                         result("B", "PREFERRED", "UNKNOWN", True))}[kind]
    return hard_gate.classify(results)


def _fresh(gate):
    state = {"PASS": "FRESH", "FAIL": "STALE", "UNKNOWN": "UNKNOWN"}[gate]
    return {"request": {"state": state, "basis": "NEVER_CONFIRMED" if gate == "UNKNOWN"
                        else state},
            "property": {"state": "FRESH", "basis": "FRESH"},
            "offer": {"state": "FRESH", "basis": "FRESH"}}


def _perm(gate):
    return {"bindings": [{"state": {"PASS": "CURRENT", "FAIL": "REVOKED"}[gate]}]
            if gate != "UNKNOWN" else []}


@pytest.mark.parametrize("hard_kind, fresh, perm", list(itertools.product(
    ("PASS", "FAIL", "REQUIRED_UNKNOWN", "SOFT_BLOCKING_UNKNOWN"),
    ("PASS", "FAIL", "UNKNOWN"), ("PASS", "FAIL", "UNKNOWN"))))
def test_eligibility_precedence_is_g4_11(hard_kind, fresh, perm):
    """All 36 combinations against G4-11's four lines, written here
    independently of the implementation."""
    result = eligibility.eligibility_of(_hard(hard_kind), _fresh(fresh), _perm(perm))
    if hard_kind == "FAIL":
        expected = "REJECTED"
    elif hard_kind in ("REQUIRED_UNKNOWN", "SOFT_BLOCKING_UNKNOWN"):
        expected = "NEED_MORE_INFORMATION"
    elif fresh != "PASS" or perm != "PASS":
        expected = "NEEDS_CONFIRMATION"
    else:
        expected = "ELIGIBLE"
    assert result.eligibility == expected
    assert (result.freshness_gate_status, result.permission_gate_status) == (fresh, perm)
    gates = [r["gate"] for r in result.reasons]
    # Every gate that is not PASS keeps its reason, whatever the eligibility.
    assert ("PERMISSION" in gates) == (perm != "PASS")
    assert ("FRESHNESS" in gates) == (fresh != "PASS")
    assert ("HARD" in gates) == (hard_kind == "FAIL")
    assert ("INFORMATION" in gates) == (hard_kind in ("REQUIRED_UNKNOWN",
                                                      "SOFT_BLOCKING_UNKNOWN"))


def test_the_values_produced_are_the_schema_enums(session):
    def enum(name):
        return set(session.execute(text(f"SELECT enum_range(NULL::turab.{name})::text[]")
                                   ).scalar_one())
    verdicts, gates, freshness = set(), set(), set()
    for hard_kind, fresh, perm in itertools.product(
            ("PASS", "FAIL", "REQUIRED_UNKNOWN"), ("PASS", "FAIL", "UNKNOWN"),
            ("PASS", "FAIL", "UNKNOWN")):
        r = eligibility.eligibility_of(_hard(hard_kind), _fresh(fresh), _perm(perm))
        verdicts.add(r.eligibility)
        gates |= {r.hard_gate_status, r.information_gate_status, r.freshness_gate_status,
                  r.permission_gate_status}
        freshness |= {r.request_freshness, r.property_freshness, r.offer_freshness}
    assert verdicts == enum("match_eligibility")
    assert gates <= enum("gate_status")
    assert freshness <= enum("freshness_state") | {"NOT_APPLICABLE"}


def test_every_reason_code_emitted_is_seeded_in_its_category(session):
    seeded = dict(session.execute(text("SELECT code, category FROM turab.reason_codes")).all())
    emitted = {("FRESHNESS", c) for _, c in eligibility.FRESHNESS_SUBJECTS}
    emitted |= {("PERMISSION", "CONSENT_REVOKED"), ("PERMISSION", "PERMISSION_MISSING")}
    assert {(seeded[code], code) for _, code in emitted} == emitted


# --- end to end on PostgreSQL: mandatory test 3, G01, M-05, M-06 ---------------------------

def test_a_required_unknown_is_need_more_information_never_pass_or_fail(session, ids):
    """Mandatory test 3 (C03, M-02), completed: the REQUIRED document is
    UNKNOWN, so the candidate is NEED_MORE_INFORMATION. It is neither
    ELIGIBLE nor REJECTED, whatever freshness and permission say, and every
    other reason is still listed."""
    req, prop, offer = _world(session, ids, doc_required=True)
    _land_book(session, prop, "UNKNOWN")
    result, _, _ = _evaluate(session, req, prop, offer)
    assert (result.eligibility, result.hard_gate_status, result.information_gate_status) == (
        "NEED_MORE_INFORMATION", "UNKNOWN", "UNKNOWN")

    stale_req, stale_prop, bare_offer = _world(session, ids, doc_required=True,
                                               property_confirmed=AS_OF - 90 * DAY,
                                               consent=False)
    _land_book(session, stale_prop, "UNKNOWN")
    result, _, _ = _evaluate(session, stale_req, stale_prop, bare_offer)
    assert result.eligibility == "NEED_MORE_INFORMATION"
    assert _codes(result) == ["DOCUMENT_NOT_KNOWN", "PROPERTY_STALE", "PERMISSION_MISSING"]


def test_a_hard_fail_is_rejected_whatever_freshness_and_permission(session, ids):
    """G01 at eligibility. Mandatory test 2's planned name, "whatever the
    soft score", comes with step 6."""
    req, prop, offer = _world(session, ids, doc_required=True)
    _land_book(session, prop, "POSSESSION_CERTIFICATE")
    assert _evaluate(session, req, prop, offer)[0].eligibility == "REJECTED"
    req2, prop2, offer2 = _world(session, ids, doc_required=True,
                                 request_confirmed=AS_OF - 90 * DAY, consent=False)
    _land_book(session, prop2, "POSSESSION_CERTIFICATE")
    result, _, _ = _evaluate(session, req2, prop2, offer2)
    assert result.eligibility == "REJECTED"
    assert _codes(result) == ["DOCUMENT_MISMATCH", "REQUEST_STALE", "PERMISSION_MISSING"]


def test_a_stale_property_with_every_criterion_passing_needs_confirmation(session, ids):
    """M-05."""
    req, prop, offer = _world(session, ids, property_confirmed=AS_OF - 31 * DAY)
    result, fs, _ = _evaluate(session, req, prop, offer)
    assert (result.eligibility, result.hard_gate_status, result.freshness_gate_status) == (
        "NEEDS_CONFIRMATION", "PASS", "FAIL")
    assert (result.property_freshness, _codes(result)) == ("STALE", ["PROPERTY_STALE"])


def test_a_stale_request_needs_confirmation(session, ids):
    """M-06: no new opportunity before the request is reconfirmed."""
    req, prop, offer = _world(session, ids, request_confirmed=AS_OF - 31 * DAY)
    result, _, _ = _evaluate(session, req, prop, offer)
    assert (result.eligibility, result.request_freshness, _codes(result)) == (
        "NEEDS_CONFIRMATION", "STALE", ["REQUEST_STALE"])


@pytest.mark.parametrize("consent, code", [("missing", "PERMISSION_MISSING"),
                                           ("revoked", "CONSENT_REVOKED")])
def test_a_permission_reason_stays_visible_under_needs_confirmation(session, ids, consent,
                                                                    code):
    """The condition of the review of f789a59 on G4-11, on PostgreSQL."""
    req, prop, offer = _world(session, ids, consent=(consent == "revoked"))
    if consent == "revoked":
        session.execute(text("""UPDATE turab.consent_grants g SET status = 'REVOKED'
                                  FROM turab.resource_consent_bindings b
                                 WHERE b.consent_id = g.consent_id AND b.offer_id = :o"""),
                        {"o": offer})
    result, _, perm = _evaluate(session, req, prop, offer)
    assert (result.eligibility, result.permission_gate_status) == (
        "NEEDS_CONFIRMATION", "UNKNOWN" if consent == "missing" else "FAIL")
    [reason] = result.reasons
    assert (reason["gate"], reason["reason_code"]) == ("PERMISSION", code)


def test_every_gate_passing_is_eligible_with_no_reason(session, ids):
    """The only state in which `enforce_approved_review_gate` would let a
    review be APPROVED (all four gates PASS, ELIGIBLE)."""
    req, prop, offer = _world(session, ids)
    result, _, _ = _evaluate(session, req, prop, offer)
    assert result.eligibility == "ELIGIBLE" and result.reasons == ()
    assert {result.hard_gate_status, result.information_gate_status,
            result.freshness_gate_status, result.permission_gate_status} == {"PASS"}


def test_the_permission_snapshot_is_hashable_and_replays(session, ids):
    """The gates read the snapshots alone: the permission gate from the
    stored `jsonb` form gives the live result."""
    req, prop, offer = _world(session, ids)
    perm = snapshots.permission_snapshot(session, offer, as_of=AS_OF)
    stored = session.execute(text("SELECT CAST(:j AS jsonb)::text"), {
        "j": canonical.canonical_bytes(perm).decode()}).scalar_one()
    assert eligibility.permission_gate(snapshots.exact_json(stored)) == \
        eligibility.permission_gate(perm)


def test_evaluating_writes_nothing(session, ids):
    req, prop, offer = _world(session, ids)
    tables = ("consent_grants", "resource_consent_bindings", "property_offers", "properties",
              "requests", "match_candidates", "match_criterion_results",
              "match_diagnostic_runs", "audit_log", "tasks")

    def counts():
        return {t: _one(session, f"SELECT count(*) FROM turab.{t}") for t in tables}

    before = counts()
    _evaluate(session, req, prop, offer)
    assert counts() == before
