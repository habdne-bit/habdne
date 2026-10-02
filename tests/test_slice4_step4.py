"""Slice 4 step 4: the criterion rules, the unknown classification, and the
hard and information gates.

Ref: `docs/gate/SLICE_4_PLAN.md` G4-3 (b), G4-4, G4-5 (SALE), G4-6, G4-7,
decided in the review of cc3a7fe; G4-5R OPEN; `src/turab/matching/rules.py`,
`criteria.py`, `hard_gate.py`; Developer Spec §11, §12.1, §13.1; red-team C03,
G01, G02, D02; spec M-01, M-02, M-03, M-04; plan §0a evidence §E.

The rules are pure. Most tests here still build their world in PostgreSQL
and read it through the real snapshot builders, so the rules are proven on
the values the engine will actually read (numbers as Decimal, uuids as
canonical strings). Every fixture lives in the rolled-back `session`.

The rule pins are checked by step 2's
`test_the_production_registry_agrees_with_the_committed_pins`, NOT here:
mutating a rule would otherwise fail on its pin, and hide whether a
behavioural test catches the change.
"""
from __future__ import annotations

import builtins
import dis
import types
import uuid
from decimal import Decimal

import pytest
from sqlalchemy import text

from turab.matching import canonical, criteria, hard_gate, registry, rules, snapshots
from turab.matching.criteria import CriterionRefused


def _one(session, sql, **p):
    return session.execute(text(sql), p).scalar_one()


def _loc(session, code):
    return _one(session, "SELECT location_id FROM turab.locations WHERE code = :c", c=code)


# --- builders -----------------------------------------------------------------------------

def _request(session, ids, intent="BUY", ptype=None, pti="REQUIRED", loc=None, li="REQUIRED",
             bmax=None, bi="REQUIRED", target=None):
    return _one(session, """
        INSERT INTO turab.requests (party_id, transaction_intent, status, management_mode,
                                    claim_status, desired_property_type,
                                    property_type_importance, primary_location_id,
                                    location_importance, budget_max_dzd, budget_importance,
                                    budget_target_dzd)
        VALUES (:p, CAST(:i AS turab.request_transaction_intent), 'ACTIVE', 'ASSISTED',
                'UNCLAIMED', CAST(:t AS turab.property_type),
                CAST(:ti AS turab.criterion_importance), :loc,
                CAST(:li AS turab.criterion_importance), :bmax,
                CAST(:bi AS turab.criterion_importance), :target)
        RETURNING request_id""", p=ids.BRAHIM, i=intent, t=ptype, ti=pti, loc=loc, li=li,
        bmax=bmax, bi=bi, target=target)


def _row(session, req, code, operator, value, importance="REQUIRED", unit=None,
         blocking=False, sort=100):
    import json
    return _one(session, """
        INSERT INTO turab.request_criteria (request_id, criterion_code, importance, operator,
                                            value, unit, blocking_if_unknown, sort_order)
        VALUES (:r, :c, CAST(:i AS turab.criterion_importance),
                CAST(:o AS turab.criterion_operator), CAST(:v AS jsonb), :u, :b, :s)
        RETURNING request_criterion_id""", r=req, c=code, i=importance, o=operator,
        v=json.dumps(value), u=unit, b=blocking, s=sort)


def _property(session, ptype="APARTMENT", loc=None, land=None, built=None):
    return _one(session, """
        INSERT INTO turab.properties (property_type, supply_mode, management_mode, claim_status,
                                      canonical_location_id, land_area_m2, built_area_m2)
        VALUES (CAST(:t AS turab.property_type), 'PUBLIC', 'ASSISTED', 'UNCLAIMED', :loc,
                :land, :built)
        RETURNING property_id""", t=ptype, loc=loc, land=land, built=built)


def _offer(session, ids, prop, kind="SALE", ask=None, negotiable="UNKNOWN", expectation=None):
    return _one(session, """
        INSERT INTO turab.property_offers (property_id, party_id, transaction_type, status,
                                           asking_price_dzd, price_negotiable,
                                           seller_expectation_dzd)
        VALUES (:p, :party, CAST(:t AS turab.transaction_type), 'ACTIVE', :ask,
                CAST(:n AS turab.price_negotiability), :exp)
        RETURNING offer_id""", p=prop, party=ids.BRAHIM, t=kind, ask=ask, n=negotiable,
        exp=expectation)


def _attribute(session, prop, code, value, claim=None):
    import json
    session.execute(text("""
        INSERT INTO turab.property_attributes (property_id, attribute_definition_id, value,
                                               resolved_claim_id)
        SELECT :p, attribute_definition_id, CAST(:v AS jsonb), :c
          FROM turab.attribute_definitions WHERE code = :code"""),
        {"p": prop, "v": json.dumps(value), "c": claim, "code": code})


def _plan(session, req):
    rs = snapshots.request_snapshot(session, req)
    return rs, criteria.criteria_of(rs, criteria.read_vocabulary(session, rs))


def _gate(session, req, prop, offer):
    rs, plan = _plan(session, req)
    return hard_gate.evaluate(plan, rs, snapshots.property_snapshot(session, prop),
                              snapshots.commercial_context_snapshot(session, offer))


def _result(gate, code, ordinal=1):
    [r] = [r for r in gate.results if (r.criterion_code, r.ordinal) == (code, ordinal)]
    return r


def _refusal(session, req):
    with pytest.raises(CriterionRefused) as refused:
        _plan(session, req)
    return refused.value


# ======================================================================================
# The registry: every rule self-contained, every code accounted for
# ======================================================================================

def _globals_read(code: types.CodeType) -> set[str]:
    names = {i.argval for i in dis.get_instructions(code) if i.opname == "LOAD_GLOBAL"}
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            names |= _globals_read(const)
    return names


def test_every_rule_is_self_contained():
    """A rule's pin covers its own source only (G4-2), so a rule may read no
    module-level name but `Decimal` and the builtins."""
    criterion_rules = [r for r in registry.REGISTRY.rules()
                       if r.rule_id.startswith("criterion.")]
    offenders = {}
    for rule in criterion_rules:
        extra = {n for n in _globals_read(rule.evaluate.__code__)
                 if n != "Decimal" and not hasattr(builtins, n)}
        if extra:
            offenders[rule.key] = sorted(extra)
    assert offenders == {}
    # The pinned gates and the soft score (review of a5ea6f5) are checked by
    # step 6's `test_every_registered_function_is_self_contained`.
    assert len(criterion_rules) == 12


def test_the_detector_sees_a_module_constant():
    ns = {}
    exec("X = 1\ndef f(c, r, p, o):\n    return X\n", ns)
    assert _globals_read(ns["f"].__code__) == {"X"}


def test_every_seeded_code_has_a_rule_or_a_stated_treatment(session):
    seeded = set(session.execute(text("SELECT code FROM turab.criterion_definitions")).scalars())
    assert seeded == set(criteria.RULES) | set(criteria.DEFERRED) | {"CUSTOM_ATTRIBUTE"}
    for rule_id, version, _ in criteria.RULES.values():
        registry.REGISTRY.resolve(rule_id, version)
    registry.REGISTRY.resolve(*criteria.NO_RULE)


def test_the_property_type_list_is_the_schema_enum(session):
    enum = session.execute(text("SELECT enum_range(NULL::turab.property_type)::text[]")
                           ).scalar_one()
    assert tuple(enum) == criteria.PROPERTY_TYPES


def test_every_reason_code_a_rule_may_emit_is_a_seeded_match_code(session):
    seeded = set(session.execute(text(
        "SELECT code FROM turab.reason_codes WHERE category = 'MATCH' AND active")).scalars())
    assert hard_gate.MATCH_REASON_CODES <= seeded


# ======================================================================================
# G4-7: what the run refuses
# ======================================================================================

@pytest.mark.parametrize("code, operator, value", [
    ("BUDGET_MAX", "IN", ["a", "b"]),          # evidence §E, verbatim
    ("LOCATION", "GTE", 5),
    ("ROOMS_MIN", "EQ", 3),
    ("LAND_AREA_MIN", "BETWEEN", [100, 200]),
    ("PROPERTY_TYPE", "EXISTS", True),
    ("DOCUMENT_TYPE", "BOOL", True),
    ("BEDROOMS_MIN", "LTE", 2),
])
@pytest.mark.parametrize("importance", ["REQUIRED", "PREFERRED"])
def test_an_operator_that_does_not_suit_its_code_is_refused(session, ids, code, operator,
                                                             value, importance):
    req = _request(session, ids, bmax=10_000_000)
    rid = _row(session, req, code, operator, value, importance=importance)
    refused = _refusal(session, req)
    assert (refused.decision, refused.criterion_code) == ("G4-7", code)
    assert refused.request_criterion_id == str(rid)
    assert "does not suit" in refused.problem


@pytest.mark.parametrize("code, operator, value", [
    ("BUDGET_MAX", "LTE", "twenty million"),
    ("BUDGET_MAX", "LTE", -1),
    ("BUDGET_MAX", "LTE", 1500000.5),
    ("BUDGET_MAX", "LTE", True),
    ("ROOMS_MIN", "GTE", 2.5),
    ("BEDROOMS_MIN", "GTE", -1),
    ("LAND_AREA_MIN", "GTE", 0),
    ("BUILT_AREA_MIN", "GTE", "120"),
    ("PROPERTY_TYPE", "EQ", "CASTLE"),
    ("PROPERTY_TYPE", "IN", []),
    ("PROPERTY_TYPE", "IN", ["APARTMENT", 7]),
    ("DOCUMENT_TYPE", "EQ", "PASSPORT"),
    ("RIGHT_TYPE", "NOT_IN", "POSSESSION"),
    ("TRANSACTION_INTENT", "EQ", "LEASE"),
    ("LOCATION", "EQ", "not-a-uuid"),
    ("LOCATION", "IN", []),
])
def test_a_value_no_rule_can_read_is_refused(session, ids, code, operator, value):
    req = _request(session, ids, bmax=10_000_000)
    _row(session, req, code, operator, value, importance="PREFERRED")
    refused = _refusal(session, req)
    assert (refused.decision, refused.criterion_code) == ("G4-7", code)
    assert refused.problem == "a value its rule cannot read"


def test_a_location_naming_no_location_is_refused(session, ids):
    """Evidence §E, verbatim: a LOCATION naming a random uuid was accepted by
    Slice 2 (201). The run refuses it."""
    req = _request(session, ids, bmax=10_000_000)
    _row(session, req, "LOCATION", "EQ", str(uuid.uuid4()))
    assert _refusal(session, req).problem == "a value its rule cannot read"


@pytest.mark.parametrize("code, unit, refused", [
    ("BUDGET_MAX", "centimes", True), ("BUDGET_MAX", "DZD", False),
    ("LAND_AREA_MIN", "ha", True), ("LAND_AREA_MIN", "m2", False),
    ("ROOMS_MIN", "rooms", True), ("ROOMS_MIN", None, False),
])
def test_only_a_unit_the_rule_reads_is_accepted(session, ids, code, unit, refused):
    req = _request(session, ids, bmax=10_000_000)
    _row(session, req, code, "LTE" if code == "BUDGET_MAX" else "GTE", 200, unit=unit)
    if refused:
        assert _refusal(session, req).problem == "a unit its rule cannot read"
    else:
        _plan(session, req)


@pytest.mark.parametrize("code, operator", [("CUSTOM_ATTRIBUTE", "EQ"),
                                            ("PROPERTY_TYPE", "TEXT_SEMANTIC"),
                                            ("LOCATION", "TEXT_SEMANTIC")])
def test_a_required_criterion_without_a_deterministic_rule_is_refused(session, ids, code,
                                                                      operator):
    req = _request(session, ids, bmax=10_000_000)
    _row(session, req, code, operator, {"k": "near the market"})
    refused = _refusal(session, req)
    assert refused.decision == "G4-7" and "no deterministic rule" in refused.problem


@pytest.mark.parametrize("code, operator", [("CUSTOM_ATTRIBUTE", "EQ"),
                                            ("PROPERTY_TYPE", "TEXT_SEMANTIC")])
@pytest.mark.parametrize("importance", ["PREFERRED", "FLEXIBLE"])
def test_a_soft_criterion_without_a_rule_is_unknown_and_not_blocking(session, ids, code,
                                                                     operator, importance):
    req = _request(session, ids, bmax=30_000_000)
    rid = _row(session, req, code, operator, {"k": "quiet street"}, importance=importance)
    prop = _property(session)
    gate = _gate(session, req, prop, _offer(session, ids, prop, ask=20_000_000))
    [r] = [r for r in gate.results if r.request_criterion_id == str(rid)]
    assert (r.compatibility, r.blocking, r.rule_id) == (
        "UNKNOWN", False, "criterion.no_deterministic_rule")
    assert r.explanation == {"basis": "NO_DETERMINISTIC_RULE"}
    assert gate.information_gate_status == "PASS" and gate.hard_gate_status == "PASS"


def test_a_soft_criterion_without_a_rule_that_asks_to_block_is_refused(session, ids):
    """It would block every candidate and could never be resolved: the
    REQUIRED case again (G4-7)."""
    req = _request(session, ids, bmax=10_000_000)
    _row(session, req, "CUSTOM_ATTRIBUTE", "EQ", {"k": "v"}, importance="PREFERRED",
         blocking=True)
    assert "block for good" in _refusal(session, req).problem


def test_an_unregistered_code_is_treated_as_having_no_rule(session, ids):
    """A code added to `criterion_definitions` later has no rule here. It
    fails closed: REQUIRED is refused; a soft one is UNKNOWN."""
    session.execute(text("""INSERT INTO turab.criterion_definitions (code, label_ar, value_type)
                            VALUES ('TEST_POOL', 'مسبح', 'BOOLEAN')"""))
    req = _request(session, ids, bmax=10_000_000)
    _row(session, req, "TEST_POOL", "BOOL", True)
    assert "no deterministic rule" in _refusal(session, req).problem


def test_budget_target_is_deferred_to_the_soft_score_and_never_required(session, ids):
    req = _request(session, ids, bmax=30_000_000, target=25_000_000)
    rid = _row(session, req, "BUDGET_TARGET", "EQ", 24_000_000, importance="PREFERRED")
    _, plan = _plan(session, req)
    assert [(d["code"], d["source"], d["deferred_to"]) for d in plan.deferred] == [
        ("BUDGET_TARGET", "COLUMN", "step 6 (G4-12)"),
        ("BUDGET_TARGET", "ROW", "step 6 (G4-12)")]
    assert plan.deferred[1]["request_criterion_id"] == str(rid)
    assert all(c["code"] != "BUDGET_TARGET" for c in plan.criteria)

    req2 = _request(session, ids, bmax=30_000_000)
    _row(session, req2, "BUDGET_TARGET", "EQ", 24_000_000)
    assert "soft-only" in _refusal(session, req2).problem


def test_a_refusal_never_echoes_the_value(session, ids):
    req = _request(session, ids, bmax=10_000_000)
    _row(session, req, "DOCUMENT_TYPE", "EQ", "SECRET-VALUE-4711")
    refused = _refusal(session, req)
    assert "SECRET-VALUE-4711" not in str(refused)


def test_every_row_is_validated_before_any_contradiction_is_judged(session, ids):
    """The refusal a request receives does not depend on row order."""
    req = _request(session, ids, ptype="HOUSE_VILLA", bmax=10_000_000)
    _row(session, req, "PROPERTY_TYPE", "EQ", "APARTMENT", sort=1)   # a G4-3 contradiction
    _row(session, req, "ROOMS_MIN", "GTE", "three", sort=2)          # a G4-7 invalid value
    assert _refusal(session, req).decision == "G4-7"


# ======================================================================================
# G4-3 (b): a provable contradiction refuses; anything else is evaluated
# ======================================================================================

def test_a_required_row_disjoint_from_the_required_column_is_refused(session, ids):
    """Evidence §E, verbatim: a request whose column says HOUSE_VILLA, with a
    REQUIRED row `PROPERTY_TYPE EQ "APARTMENT"`."""
    req = _request(session, ids, ptype="HOUSE_VILLA", bmax=10_000_000)
    rid = _row(session, req, "PROPERTY_TYPE", "EQ", "APARTMENT")
    refused = _refusal(session, req)
    assert (refused.decision, refused.criterion_code, refused.request_criterion_id) == (
        "G4-3", "PROPERTY_TYPE", str(rid))


@pytest.mark.parametrize("column_importance, row_importance, row_operator, row_value", [
    ("REQUIRED", "REQUIRED", "IN", ["APARTMENT", "HOUSE_VILLA"]),   # intersects
    ("REQUIRED", "PREFERRED", "EQ", "APARTMENT"),                   # the row is soft
    ("PREFERRED", "REQUIRED", "EQ", "APARTMENT"),                   # the column is soft
    ("REQUIRED", "REQUIRED", "NOT_IN", ["HOUSE_VILLA"]),            # not an EQ/IN set
])
def test_anything_short_of_a_provable_contradiction_is_evaluated_both_ways(
        session, ids, column_importance, row_importance, row_operator, row_value):
    req = _request(session, ids, ptype="HOUSE_VILLA", pti=column_importance, bmax=30_000_000)
    _row(session, req, "PROPERTY_TYPE", row_operator, row_value, importance=row_importance)
    prop = _property(session, ptype="HOUSE_VILLA")
    gate = _gate(session, req, prop, _offer(session, ids, prop, ask=1))
    assert [r.criterion_code for r in gate.results].count("PROPERTY_TYPE") == 2


def test_disjoint_required_location_subtrees_are_refused_nested_ones_are_not(session, ids):
    adrar, tamest = _loc(session, "C-ADRAR"), _loc(session, "C-TAMEST")
    ksar = _loc(session, "ADR-KSAR-OUGDIM")
    req = _request(session, ids, loc=adrar, bmax=10_000_000)
    _row(session, req, "LOCATION", "EQ", str(tamest))
    assert _refusal(session, req).decision == "G4-3"

    nested = _request(session, ids, loc=adrar, bmax=10_000_000)
    _row(session, nested, "LOCATION", "EQ", str(ksar))
    _plan(session, nested)
    upward = _request(session, ids, loc=ksar, bmax=10_000_000)
    _row(session, upward, "LOCATION", "IN", [str(tamest), str(adrar)])
    _plan(session, upward)


def test_a_required_transaction_intent_row_against_the_request_is_refused(session, ids):
    req = _request(session, ids, bmax=10_000_000)
    _row(session, req, "TRANSACTION_INTENT", "EQ", "RENT")
    assert _refusal(session, req).decision == "G4-3"


def test_a_stricter_numeric_row_is_evaluated_and_prevails(session, ids):
    """G4-3: `BUDGET_MAX LTE 20000000` against a column of 25,000,000 is no
    contradiction. Both are evaluated; the stricter one decides."""
    req = _request(session, ids, bmax=25_000_000)
    _row(session, req, "BUDGET_MAX", "LTE", 20_000_000)
    prop = _property(session)
    gate = _gate(session, req, prop, _offer(session, ids, prop, ask=22_000_000,
                                             negotiable="NO"))
    assert (_result(gate, "BUDGET_MAX", 1).compatibility,
            _result(gate, "BUDGET_MAX", 2).compatibility) == ("PASS", "FAIL")
    assert gate.hard_gate_status == "FAIL"


# ======================================================================================
# G4-5R: no RENT price rule exists, so a RENT request is refused, not guessed
# ======================================================================================

@pytest.mark.parametrize("bmax, row", [(70_000, None), (None, None), (None, 70_000)])
def test_a_rent_request_is_refused_naming_g4_5r(session, ids, bmax, row):
    """No rent period is defined for the budget or the asking price, so no
    numeric PASS or FAIL exists, and none is invented (review of 6b833fb).
    D01's "RENT 70k/month" is the scenario's wording, not a decided period."""
    req = _request(session, ids, intent="RENT", bmax=bmax)
    rid = row and _row(session, req, "BUDGET_MAX", "LTE", row)
    refused = _refusal(session, req)
    assert (refused.decision, refused.criterion_code) == ("G4-5R", "BUDGET_MAX")
    assert refused.request_criterion_id == (str(rid) if rid else None)


def test_the_sale_price_rule_refuses_a_rent_offer_outright():
    """A backstop: were a RENT offer ever to reach it, the rule raises rather
    than compare two amounts of unknown period."""
    rule = registry.REGISTRY.resolve("criterion.budget_max_sale", "1")
    crit = {"code": "BUDGET_MAX", "operator": "LTE", "value": Decimal(100)}
    with pytest.raises(RuntimeError, match="G4-5R"):
        rule.evaluate(crit, {}, {}, {"transaction_type": "RENT", "asking_price_dzd": 1})


# ======================================================================================
# G4-5 for SALE: the approved table, row by row (M-03, M-04, G02; mandatory tests 4, 5)
# ======================================================================================

@pytest.mark.parametrize("bmax, ask, negotiable, expectation, compatibility, reason", [
    (None, 20_000_000, "NO", None, "UNKNOWN", None),                          # max is null
    (25_000_000, None, "NO", None, "UNKNOWN", "PRICE_NOT_KNOWN"),             # ask is null
    (25_000_000, 25_000_000, "NO", None, "PASS", None),                       # ask <= max
    (25_000_000, 27_000_000, "NO", 24_000_000, "PASS", None),                 # exp <= max
    (25_000_000, 27_000_000, "YES", None, "UNKNOWN", "PRICE_NEGOTIATION_UNCONFIRMED"),
    (25_000_000, 27_000_000, "NO", None, "FAIL", "BUDGET_EXCEEDED"),
    (25_000_000, 27_000_000, "UNKNOWN", None, "UNKNOWN", "PRICE_NEGOTIATION_UNCONFIRMED"),
    (25_000_000, 27_000_000, "NO", 26_000_000, "FAIL", "BUDGET_EXCEEDED"),   # exp > max
])
def test_the_sale_price_table(session, ids, bmax, ask, negotiable, expectation,
                              compatibility, reason):
    req = _request(session, ids, bmax=bmax)
    prop = _property(session)
    offer = _offer(session, ids, prop, ask=ask, negotiable=negotiable, expectation=expectation)
    r = _result(_gate(session, req, prop, offer), "BUDGET_MAX")
    assert (r.compatibility, r.reason_code) == (compatibility, reason)
    assert r.delta == (None if bmax is None or ask is None else {"dzd": Decimal(ask - bmax)})


def test_negotiable_above_max_is_unknown_not_pass(session, ids):
    """Mandatory test 4 (G02, M-04), at the criterion: YES is not a price."""
    req = _request(session, ids, bmax=25_000_000)
    prop = _property(session)
    offer = _offer(session, ids, prop, ask=26_000_000, negotiable="YES")
    gate = _gate(session, req, prop, offer)
    r = _result(gate, "BUDGET_MAX")
    assert r.compatibility == "UNKNOWN" and r.blocking
    assert gate.hard_gate_status == "UNKNOWN" and gate.information_gate_status == "UNKNOWN"


def test_seller_expectation_can_pass_price_and_is_never_in_the_criterion_result(session, ids):
    """Mandatory test 5 (M-03, D02, R9.3), at the criterion. A PASS decided by
    the expectation carries the same reason and explanation as a PASS on the
    asking price, and the expectation's value appears nowhere in the result.
    (The DTO half is step 8.)"""
    req = _request(session, ids, bmax=25_000_000)
    prop = _property(session)
    by_expectation = _offer(session, ids, prop, ask=27_000_000, negotiable="NO",
                            expectation=24_123_457)
    by_ask = _offer(session, ids, prop, ask=24_000_000, negotiable="NO")
    a = _result(_gate(session, req, prop, by_expectation), "BUDGET_MAX")
    b = _result(_gate(session, req, prop, by_ask), "BUDGET_MAX")
    assert a.compatibility == b.compatibility == "PASS"
    assert (a.reason_code, a.explanation) == (b.reason_code, b.explanation)
    text_of_a = canonical.canonical_bytes({
        "property_value": a.property_value, "delta": a.delta, "explanation": a.explanation,
        "reason_code": a.reason_code, "request_value": a.request_value}).decode()
    assert "24123457" not in text_of_a and "expectation" not in text_of_a.lower()


def test_no_rule_explanation_mentions_the_expectation():
    """Every explanation a rule can return, read from the rule sources: none
    names the expectation (R9.3, S36). The sources are the complete set of
    texts a rule can emit, because explanations are fixed codes."""
    import inspect
    for rule in registry.REGISTRY.rules():
        for const in _string_constants(rule.evaluate.__code__):
            if const.isupper():
                assert "EXPECT" not in const and "SELLER" not in const, (rule.key, const)
    assert "PRICE_COMPATIBLE" in inspect.getsource(rules.budget_max_sale_v1)


def _string_constants(code):
    for const in code.co_consts:
        if isinstance(const, str):
            yield const
        elif isinstance(const, types.CodeType):
            yield from _string_constants(const)


# ======================================================================================
# G4-6: location, the subtree of G3-14
# ======================================================================================

@pytest.mark.parametrize("requested, at, compatibility", [
    ("C-ADRAR", "ADR-KSAR-OUGDIM", "PASS"),        # a ksar inside the commune
    ("W-ADRAR", "ADR-KSAR-OUGDIM", "PASS"),        # inside the wilaya
    ("ADR-KSAR-OUGDIM", "ADR-KSAR-OUGDIM", "PASS"),  # the location itself
    ("C-TAMEST", "ADR-KSAR-OUGDIM", "FAIL"),       # another commune
    ("ADR-KSAR-OUGDIM", "C-ADRAR", "FAIL"),        # a property ABOVE the request is not inside
])
def test_location_is_the_requested_subtree(session, ids, requested, at, compatibility):
    req = _request(session, ids, loc=_loc(session, requested), bmax=30_000_000)
    prop = _property(session, loc=_loc(session, at))
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), "LOCATION")
    assert r.compatibility == compatibility
    assert r.reason_code == (None if compatibility == "PASS" else "LOCATION_MISMATCH")
    assert (r.evidence_claim_id, r.evidence_level) == (None, None)
    assert r.explanation["evidence"] == "NO_CLAIM_LINK"


def test_a_property_without_a_location_is_unknown(session, ids):
    req = _request(session, ids, loc=_loc(session, "C-ADRAR"), bmax=30_000_000)
    prop = _property(session)
    gate = _gate(session, req, prop, _offer(session, ids, prop, ask=1))
    r = _result(gate, "LOCATION")
    assert (r.compatibility, r.blocking) == ("UNKNOWN", True)


def test_a_location_in_list_passes_on_any_member(session, ids):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "LOCATION", "IN", [str(_loc(session, "C-TAMEST")),
                                          str(_loc(session, "ADR-KSOUR"))])
    prop = _property(session, loc=_loc(session, "ADR-KSAR-ADGHA"))
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), "LOCATION")
    assert r.compatibility == "PASS"


def test_the_location_rule_replays_from_the_snapshot_after_the_tree_changed(session, ids):
    """G4-6 reads `location_ancestry` from the snapshot, never the live tree.
    After the ksar is moved under another commune, the STORED snapshot still
    gives the stored result, and a fresh one gives the new answer."""
    adrar, tamest = _loc(session, "C-ADRAR"), _loc(session, "C-TAMEST")
    ksar = _one(session, """INSERT INTO turab.locations (code, parent_id, canonical_ar,
                                                         location_type)
                            VALUES (:c, :p, 'قصر', 'KSAR') RETURNING location_id""",
                c=f"TEST-KSAR-{uuid.uuid4().hex[:8]}", p=adrar)
    req = _request(session, ids, loc=adrar, bmax=30_000_000)
    prop = _property(session, loc=ksar)
    offer = _offer(session, ids, prop, ask=1)
    rs, plan = _plan(session, req)
    stored_prop = snapshots.stored_form(snapshots.property_snapshot(session, prop))
    stored_offer = snapshots.stored_form(snapshots.commercial_context_snapshot(session, offer))
    before = hard_gate.evaluate(plan, rs, stored_prop, stored_offer)

    session.execute(text("UPDATE turab.locations SET parent_id = :t WHERE location_id = :k"),
                    {"t": tamest, "k": ksar})
    replayed = hard_gate.evaluate(plan, rs, stored_prop, stored_offer)
    fresh = _gate(session, req, prop, offer)
    assert _result(before, "LOCATION").compatibility == "PASS"
    assert replayed == before
    assert _result(fresh, "LOCATION").compatibility == "FAIL"


def test_the_location_rule_refuses_a_snapshot_without_ancestry():
    rule = registry.REGISTRY.resolve("criterion.location", "1")
    here = str(uuid.uuid4())
    with pytest.raises(RuntimeError, match="no location ancestry"):
        rule.evaluate({"operator": "EQ", "value": here}, {},
                      {"canonical_location_id": here}, None)


def test_location_ancestry_is_nearest_first_and_survives_a_cycle(session):
    adrar, wilaya = _loc(session, "C-ADRAR"), _loc(session, "W-ADRAR")
    ksar = _loc(session, "ADR-KSAR-OUGDIM")
    assert snapshots.location_ancestry(session, ksar) == [
        ksar, _loc(session, "ADR-KSOUR"), adrar, wilaya]
    a = _one(session, """INSERT INTO turab.locations (code, canonical_ar, location_type)
                         VALUES (:c, 'أ', 'AREA') RETURNING location_id""",
             c=f"TEST-CYC-A-{uuid.uuid4().hex[:8]}")
    b = _one(session, """INSERT INTO turab.locations (code, parent_id, canonical_ar,
                                                      location_type)
                         VALUES (:c, :p, 'ب', 'AREA') RETURNING location_id""",
             c=f"TEST-CYC-B-{uuid.uuid4().hex[:8]}", p=a)
    session.execute(text("UPDATE turab.locations SET parent_id = :b WHERE location_id = :a"),
                    {"a": a, "b": b})
    assert snapshots.location_ancestry(session, a) == [a, b]
    assert snapshots.location_ancestry(session, None) == []


# ======================================================================================
# Property type, areas, counts, documents
# ======================================================================================

@pytest.mark.parametrize("operator, value, compatibility", [
    ("EQ", "APARTMENT", "PASS"), ("EQ", "LAND", "FAIL"),
    ("NEQ", "LAND", "PASS"), ("NEQ", "APARTMENT", "FAIL"),
    ("IN", ["LAND", "APARTMENT"], "PASS"), ("IN", ["LAND", "BUILDING"], "FAIL"),
    ("NOT_IN", ["LAND"], "PASS"), ("NOT_IN", ["APARTMENT", "LAND"], "FAIL"),
])
def test_property_type(session, ids, operator, value, compatibility):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "PROPERTY_TYPE", operator, value)
    prop = _property(session, ptype="APARTMENT")
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), "PROPERTY_TYPE")
    assert r.compatibility == compatibility
    assert r.reason_code == (None if compatibility == "PASS" else "PROPERTY_TYPE_MISMATCH")


@pytest.mark.parametrize("code, column", [("LAND_AREA_MIN", "land"), ("BUILT_AREA_MIN", "built")])
@pytest.mark.parametrize("area, compatibility", [(None, "UNKNOWN"), ("199.99", "FAIL"),
                                                 ("200.00", "PASS"), ("250.5", "PASS")])
def test_area_minimum(session, ids, code, column, area, compatibility):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, code, "GTE", 200)
    prop = _property(session, **{column: area})
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), code)
    assert r.compatibility == compatibility
    # REQUIRED: AREA_BELOW_PREFERENCE would name another importance (review of
    # f789a59), so the reason is null; the soft case is tested below.
    assert r.reason_code is None
    assert r.delta == (None if area is None else {"m2": Decimal(area) - 200})


@pytest.mark.parametrize("code, attribute", [("ROOMS_MIN", "ROOMS"), ("BEDROOMS_MIN", "BEDROOMS")])
def test_count_minimum_reads_the_resolved_attribute_and_its_evidence(session, ids, code,
                                                                     attribute):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, code, "GTE", 3)
    missing = _property(session)
    r = _result(_gate(session, req, missing, _offer(session, ids, missing, ask=1)), code)
    assert (r.compatibility, r.explanation["basis"]) == ("UNKNOWN", "ATTRIBUTE_NOT_RECORDED")

    prop = _property(session)
    claim = _one(session, """INSERT INTO turab.claims (property_id, attribute_code,
                                                       claimed_value)
                             VALUES (:p, :a, '2') RETURNING claim_id""", p=prop, a=attribute)
    _attribute(session, prop, attribute, 2, claim=claim)
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), code)
    assert (r.compatibility, r.property_value, r.delta) == ("FAIL", Decimal(2),
                                                           {"count": Decimal(-1)})
    assert (r.evidence_claim_id, r.evidence_level) == (str(claim), "DECLARED")

    enough = _property(session)
    _attribute(session, enough, attribute, 3)
    r = _result(_gate(session, req, enough, _offer(session, ids, enough, ask=1)), code)
    assert r.compatibility == "PASS"


@pytest.mark.parametrize("value, operator, wanted, compatibility, reason", [
    ("LAND_BOOK", "EQ", "LAND_BOOK", "PASS", None),
    ("POSSESSION_CERTIFICATE", "EQ", "LAND_BOOK", "FAIL", "DOCUMENT_MISMATCH"),
    ("UNKNOWN", "EQ", "LAND_BOOK", "UNKNOWN", "DOCUMENT_NOT_KNOWN"),
    ("UNSPECIFIED_DOCUMENT", "EQ", "LAND_BOOK", "UNKNOWN", "DOCUMENT_NOT_KNOWN"),
    ("UNKNOWN", "NOT_IN", ["POSSESSION_CERTIFICATE"], "UNKNOWN", "DOCUMENT_NOT_KNOWN"),
    ("LAND_BOOK", "NOT_IN", ["POSSESSION_CERTIFICATE"], "PASS", None),
    (None, "EQ", "LAND_BOOK", "UNKNOWN", "DOCUMENT_NOT_KNOWN"),
])
def test_document_type(session, ids, value, operator, wanted, compatibility, reason):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "DOCUMENT_TYPE", operator, wanted)
    prop = _property(session, ptype="LAND")
    if value is not None:
        _attribute(session, prop, "DOCUMENT_TYPE", value)
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), "DOCUMENT_TYPE")
    assert (r.compatibility, r.reason_code) == (compatibility, reason)


@pytest.mark.parametrize("value, compatibility", [("PRIVATE_OWNERSHIP", "PASS"),
                                                  ("POSSESSION", "FAIL"),
                                                  ("UNKNOWN", "UNKNOWN")])
def test_right_type_has_no_seeded_reason_code(session, ids, value, compatibility):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "RIGHT_TYPE", "EQ", "PRIVATE_OWNERSHIP")
    prop = _property(session, ptype="LAND")
    _attribute(session, prop, "RIGHT_TYPE", value)
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), "RIGHT_TYPE")
    assert (r.compatibility, r.reason_code) == (compatibility, None)


def test_an_attribute_of_the_wrong_json_type_is_unknown_not_compared():
    rule = registry.REGISTRY.resolve("criterion.count_min", "2")
    out = rule.evaluate({"code": "ROOMS_MIN", "value": Decimal(3), "importance": "REQUIRED"},
                        {}, {"property_type": "APARTMENT",
                             "attribute_applies_to": {"ROOMS": ["APARTMENT"]},
                             "attributes": [{"code": "ROOMS", "value": "four"}]}, None)
    assert (out["compatibility"], out["explanation"]["basis"]) == (
        "UNKNOWN", "ATTRIBUTE_UNREADABLE")
    rule = registry.REGISTRY.resolve("criterion.attribute_option", "2")
    out = rule.evaluate({"code": "DOCUMENT_TYPE", "operator": "EQ", "value": "LAND_BOOK",
                         "importance": "REQUIRED"}, {},
                        {"attributes": [{"code": "DOCUMENT_TYPE", "value": 7}]}, None)
    assert out["compatibility"] == "UNKNOWN"


def test_transaction_intent_is_recorded_against_the_evaluated_offer(session, ids):
    req = _request(session, ids, bmax=30_000_000)
    prop = _property(session)
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)),
                "TRANSACTION_INTENT")
    assert (r.compatibility, r.request_value["value"], r.property_value) == ("PASS", "BUY",
                                                                           "SALE")
    rule = registry.REGISTRY.resolve("criterion.transaction_intent", "1")
    crit = {"operator": "EQ", "value": "BUY"}
    assert rule.evaluate(crit, {}, {}, {"transaction_type": "RENT"})["compatibility"] == "FAIL"
    assert rule.evaluate(crit, {}, {}, None)["compatibility"] == "UNKNOWN"


# ======================================================================================
# The criteria a request yields, and their order
# ======================================================================================

def test_columns_come_first_then_rows_and_ordinals_count_per_code(session, ids):
    adrar = _loc(session, "C-ADRAR")
    req = _request(session, ids, ptype="APARTMENT", loc=adrar, bmax=30_000_000)
    r2 = _row(session, req, "PROPERTY_TYPE", "IN", ["APARTMENT", "HOUSE_VILLA"], sort=5)
    r1 = _row(session, req, "ROOMS_MIN", "GTE", 2, sort=1)
    _, plan = _plan(session, req)
    assert [(c["code"], c["ordinal"], c["source"], c["request_criterion_id"])
            for c in plan.criteria] == [
        ("TRANSACTION_INTENT", 1, "COLUMN", None), ("PROPERTY_TYPE", 1, "COLUMN", None),
        ("LOCATION", 1, "COLUMN", None), ("BUDGET_MAX", 1, "COLUMN", None),
        ("ROOMS_MIN", 1, "ROW", str(r1)), ("PROPERTY_TYPE", 2, "ROW", str(r2))]


def test_a_null_budget_column_yields_to_a_budget_row(session, ids):
    """"max is null" means no maximum is known. A BUDGET_MAX row gives one, so
    the null column adds no UNKNOWN beside it."""
    req = _request(session, ids)
    _row(session, req, "BUDGET_MAX", "LTE", 20_000_000)
    _, plan = _plan(session, req)
    assert [(c["code"], c["source"]) for c in plan.criteria if c["code"] == "BUDGET_MAX"] == [
        ("BUDGET_MAX", "ROW")]
    bare = _request(session, ids)
    _, plan = _plan(session, bare)
    [budget] = [c for c in plan.criteria if c["code"] == "BUDGET_MAX"]
    assert (budget["source"], budget["value"], budget["importance"]) == ("COLUMN", None,
                                                                        "REQUIRED")


def test_unset_type_and_location_columns_state_no_criterion(session, ids):
    req = _request(session, ids, bmax=1)
    _, plan = _plan(session, req)
    assert [c["code"] for c in plan.criteria] == ["TRANSACTION_INTENT", "BUDGET_MAX"]


# ======================================================================================
# G4-4 and the gates
# ======================================================================================

@pytest.mark.parametrize("importance", ["REQUIRED", "PREFERRED", "FLEXIBLE"])
@pytest.mark.parametrize("compatibility", ["PASS", "FAIL", "UNKNOWN"])
@pytest.mark.parametrize("flag", [False, True])
def test_blocking_is_g4_4(importance, compatibility, flag):
    expected = ((importance == "REQUIRED" and compatibility != "PASS")
                or (compatibility == "UNKNOWN" and flag))
    assert hard_gate.blocking(importance, compatibility, flag) is expected


def test_a_required_unknown_is_never_pass_or_fail_and_blocks(session, ids):
    """C03 and mandatory test 3, at the gate: the document is UNKNOWN, so the
    hard gate is UNKNOWN (not PASS, not FAIL) and the information gate is
    UNKNOWN. NEED_MORE_INFORMATION itself is eligibility, step 5 (G4-11)."""
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK")
    prop = _property(session, ptype="LAND")
    _attribute(session, prop, "DOCUMENT_TYPE", "UNKNOWN")
    gate = _gate(session, req, prop, _offer(session, ids, prop, ask=1))
    assert (gate.hard_gate_status, gate.information_gate_status) == ("UNKNOWN", "UNKNOWN")
    assert gate.blocking_unknowns == gate.actionable_unknowns == (("DOCUMENT_TYPE", 1),)
    assert gate.required_failures == ()


def test_a_hard_fail_dominates_and_leaves_no_actionable_unknown(session, ids):
    """G01 and M-01: a REQUIRED mismatch rejects whatever else passes. A
    blocking unknown beside it is not actionable: resolving it cannot make the
    candidate eligible (§13.1)."""
    req = _request(session, ids, loc=_loc(session, "C-TAMEST"), bmax=30_000_000)
    _row(session, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK")
    prop = _property(session, ptype="LAND", loc=_loc(session, "ADR-KSAR-OUGDIM"))
    gate = _gate(session, req, prop, _offer(session, ids, prop, ask=1))
    assert gate.hard_gate_status == "FAIL"
    assert gate.required_failures == (("LOCATION", 1),)
    assert gate.blocking_unknowns == (("DOCUMENT_TYPE", 1),)
    assert gate.actionable_unknowns == ()
    assert _result(gate, "LOCATION").blocking is True


def test_soft_criteria_never_decide_the_hard_gate(session, ids):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "ROOMS_MIN", "GTE", 9, importance="PREFERRED")
    _row(session, req, "BEDROOMS_MIN", "GTE", 9, importance="FLEXIBLE")
    prop = _property(session)
    _attribute(session, prop, "ROOMS", 2)
    gate = _gate(session, req, prop, _offer(session, ids, prop, ask=1))
    assert _result(gate, "ROOMS_MIN").compatibility == "FAIL"
    assert _result(gate, "BEDROOMS_MIN").compatibility == "UNKNOWN"
    assert (gate.hard_gate_status, gate.information_gate_status) == ("PASS", "PASS")
    assert not any(r.blocking for r in gate.results)


def test_blocking_if_unknown_adds_blocking_to_a_soft_criterion(session, ids):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "BEDROOMS_MIN", "GTE", 2, importance="PREFERRED", blocking=True)
    prop = _property(session)
    gate = _gate(session, req, prop, _offer(session, ids, prop, ask=1))
    assert _result(gate, "BEDROOMS_MIN").blocking is True
    assert (gate.hard_gate_status, gate.information_gate_status) == ("PASS", "UNKNOWN")
    assert gate.actionable_unknowns == (("BEDROOMS_MIN", 1),)


def test_everything_passing_passes_both_gates(session, ids):
    req = _request(session, ids, ptype="LAND", loc=_loc(session, "C-ADRAR"), bmax=30_000_000)
    _row(session, req, "DOCUMENT_TYPE", "IN", ["LAND_BOOK", "PUBLISHED_TITLE_DEED"])
    _row(session, req, "LAND_AREA_MIN", "GTE", 300, unit="m2")
    prop = _property(session, ptype="LAND", loc=_loc(session, "ADR-CENTER"), land=400)
    _attribute(session, prop, "DOCUMENT_TYPE", "LAND_BOOK")
    gate = _gate(session, req, prop, _offer(session, ids, prop, ask=29_000_000))
    assert [r.compatibility for r in gate.results] == ["PASS"] * 6
    assert (gate.hard_gate_status, gate.information_gate_status) == ("PASS", "PASS")
    assert gate.blocking_unknowns == gate.required_failures == ()


def test_a_rule_output_the_table_cannot_hold_is_refused():
    reg = registry.RuleRegistry()

    @reg.register("criterion.bad", "1")
    def bad(criterion, request, prop, offer):
        return {"compatibility": "MAYBE", "property_value": None, "delta": None,
                "evidence_level": None, "evidence_claim_id": None, "reason_code": None,
                "explanation": {}}

    @reg.register("criterion.invented_code", "1")
    def invented(criterion, request, prop, offer):
        return {"compatibility": "FAIL", "property_value": None, "delta": None,
                "evidence_level": None, "evidence_claim_id": None,
                "reason_code": "NOT_IN_THE_SEED", "explanation": {}}

    base = {"code": "X", "ordinal": 1, "importance": "REQUIRED", "operator": "EQ",
            "value": 1, "unit": None, "blocking_if_unknown": False,
            "request_criterion_id": None, "source": "ROW", "rule_version": "1"}
    for rule_id in ("criterion.bad", "criterion.invented_code"):
        plan = criteria.CriteriaPlan(({**base, "rule_id": rule_id},), ())
        with pytest.raises(hard_gate.RuleOutputInvalid):
            hard_gate.evaluate(plan, {}, {}, None, registry=reg)


# ======================================================================================
# Replay: the rules read the stored form, so stored rows give the same results
# ======================================================================================

def test_results_from_live_snapshots_equal_results_from_jsonb_round_trips(session, ids):
    """The snapshots go through PostgreSQL `jsonb` and back, as step 7 will
    store and step 8 will read them. The results are identical."""
    req = _request(session, ids, ptype="LAND", loc=_loc(session, "C-ADRAR"), bmax=30_000_000)
    _row(session, req, "LAND_AREA_MIN", "GTE", 250)
    _row(session, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK")
    prop = _property(session, ptype="LAND", loc=_loc(session, "ADR-CENTER"), land="250.50")
    _attribute(session, prop, "DOCUMENT_TYPE", "UNKNOWN")
    offer = _offer(session, ids, prop, ask=31_000_000, negotiable="YES")
    rs, plan = _plan(session, req)
    live = hard_gate.evaluate(plan, rs, snapshots.property_snapshot(session, prop),
                              snapshots.commercial_context_snapshot(session, offer))

    def via_jsonb(snapshot):
        stored = session.execute(text("SELECT CAST(:j AS jsonb)::text"), {
            "j": canonical.canonical_bytes(snapshot).decode()}).scalar_one()
        return snapshots.exact_json(stored)

    replayed = hard_gate.evaluate(
        plan, via_jsonb(rs), via_jsonb(snapshots.property_snapshot(session, prop)),
        via_jsonb(snapshots.commercial_context_snapshot(session, offer)))
    assert replayed == live
    # Columns first; then rows by (sort_order, code): DOCUMENT_TYPE, LAND_AREA_MIN.
    assert [(r.criterion_code, r.compatibility) for r in live.results] == [
        ("TRANSACTION_INTENT", "PASS"), ("PROPERTY_TYPE", "PASS"), ("LOCATION", "PASS"),
        ("BUDGET_MAX", "UNKNOWN"), ("DOCUMENT_TYPE", "UNKNOWN"), ("LAND_AREA_MIN", "PASS")]


def test_stored_form_is_idempotent(session, ids):
    snap = snapshots.property_snapshot(session, ids.ASSISTED_APARTMENT)
    once = snapshots.stored_form(snap)
    assert snapshots.stored_form(once) == once
    assert snap["format"] == "turab.property-snapshot/3" and "location_ancestry" in snap
    assert "attribute_applies_to" in snap


def test_evaluating_writes_nothing(session, ids):
    req = _request(session, ids, loc=_loc(session, "C-ADRAR"), bmax=30_000_000)
    prop = _property(session, loc=_loc(session, "ADR-CENTER"))
    offer = _offer(session, ids, prop, ask=1)
    tables = ("requests", "request_criteria", "properties", "property_offers",
              "property_attributes", "locations", "match_candidates",
              "match_criterion_results", "match_diagnostic_runs", "audit_log", "tasks")

    def counts():
        return {t: _one(session, f"SELECT count(*) FROM turab.{t}") for t in tables}

    before = counts()
    _gate(session, req, prop, offer)
    assert counts() == before


# ======================================================================================
# Review of f789a59: three defects, and G4-18 (b)
# ======================================================================================
#
# 1. G4-7: a requested value that no property can PASS was accepted
#    (DOCUMENT_TYPE EQ UNKNOWN, EQ UNSPECIFIED_DOCUMENT, RIGHT_TYPE EQ UNKNOWN).
# 2. G4-7: a deferred BUDGET_TARGET row skipped validation (IN, an object
#    value, unit HOURS, blocking_if_unknown = true were all deferred as is).
# 3. A reason code whose seeded label names another importance:
#    AREA_BELOW_PREFERENCE on a REQUIRED area; LOCATION_MISMATCH and
#    DOCUMENT_MISMATCH ("Required ...") on a soft criterion.
# Measured against the f789a59 code: evidence/SLICE4-STEP4-REVIEW-BEFORE-FIX.txt.

@pytest.mark.parametrize("code, operator, value", [
    ("DOCUMENT_TYPE", "EQ", "UNKNOWN"),
    ("DOCUMENT_TYPE", "EQ", "UNSPECIFIED_DOCUMENT"),
    ("RIGHT_TYPE", "EQ", "UNKNOWN"),
    ("DOCUMENT_TYPE", "IN", ["UNKNOWN", "UNSPECIFIED_DOCUMENT"]),
    ("PROPERTY_TYPE", "NOT_IN", ["HOUSE_VILLA", "APARTMENT", "LAND", "SHOP_COMMERCIAL",
                                 "AGRICULTURAL_PROPERTY", "BUILDING", "OTHER"]),
    ("TRANSACTION_INTENT", "NOT_IN", ["BUY", "RENT"]),
])
@pytest.mark.parametrize("importance", ["REQUIRED", "PREFERRED"])
def test_a_requested_value_no_property_can_pass_is_refused(session, ids, code, operator,
                                                           value, importance):
    """No property value can PASS these: an unknown value is UNKNOWN, a known
    one FAILs (or, for the NOT_IN cases, every value is excluded)."""
    req = _request(session, ids, bmax=10_000_000)
    rid = _row(session, req, code, operator, value, importance=importance)
    refused = _refusal(session, req)
    assert (refused.decision, refused.criterion_code, refused.request_criterion_id) == (
        "G4-7", code, str(rid))
    assert refused.problem == "no property value can satisfy it"


def test_not_in_every_active_document_type_is_accepted_because_the_domain_is_open(session,
                                                                                ids):
    """Review of ba5f25e. Excluding every ACTIVE known option does not make
    the criterion unsatisfiable: a property can hold a retired option's
    value, and the rule compares it. The ba5f25e round refused this case; its
    refusal was the contradiction the review found."""
    known = sorted(set(session.execute(text("""
        SELECT o.option_code FROM turab.attribute_options o
          JOIN turab.attribute_definitions d USING (attribute_definition_id)
         WHERE d.code = 'DOCUMENT_TYPE' AND o.active""")).scalars())
                   - {"UNKNOWN", "UNSPECIFIED_DOCUMENT"})
    req = _request(session, ids, bmax=10_000_000)
    _row(session, req, "DOCUMENT_TYPE", "NOT_IN", known)
    _, plan = _plan(session, req)
    assert [c["code"] for c in plan.criteria].count("DOCUMENT_TYPE") == 1


@pytest.mark.parametrize("operator, value", [
    ("IN", ["UNKNOWN", "LAND_BOOK"]),     # one known, passable option: accepted
    ("NEQ", "UNKNOWN"),
    ("NOT_IN", ["UNKNOWN", "UNSPECIFIED_DOCUMENT"]),
])
def test_a_set_with_a_passable_known_option_is_accepted(session, ids, operator, value):
    req = _request(session, ids, bmax=10_000_000)
    _row(session, req, "DOCUMENT_TYPE", operator, value)
    prop = _property(session, ptype="LAND")
    _attribute(session, prop, "DOCUMENT_TYPE", "LAND_BOOK")
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), "DOCUMENT_TYPE")
    assert r.compatibility == "PASS"


@pytest.mark.parametrize("operator, value, unit, blocking, problem", [
    ("IN", [24_000_000], None, False, "does not suit"),
    ("EQ", {"amount": 24_000_000}, None, False, "a value its rule cannot read"),
    ("EQ", 24_000_000, "HOURS", False, "a unit its rule cannot read"),
    ("EQ", -5, None, False, "a value its rule cannot read"),
    ("EQ", 24_000_000, None, True, "blocking_if_unknown"),
    ("TEXT_SEMANTIC", "around 24M", None, False, "does not suit"),
])
def test_a_deferred_budget_target_is_validated_before_it_is_deferred(
        session, ids, operator, value, unit, blocking, problem):
    req = _request(session, ids, bmax=30_000_000)
    rid = _row(session, req, "BUDGET_TARGET", operator, value, importance="PREFERRED",
               unit=unit, blocking=blocking)
    refused = _refusal(session, req)
    assert (refused.decision, refused.criterion_code, refused.request_criterion_id) == (
        "G4-7", "BUDGET_TARGET", str(rid))
    assert problem in refused.problem


def test_a_valid_budget_target_row_is_deferred_with_its_value_read(session, ids):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "BUDGET_TARGET", "EQ", 24_000_000, importance="FLEXIBLE", unit="DZD")
    _, plan = _plan(session, req)
    [deferred] = plan.deferred
    assert (deferred["value"], deferred["unit"], deferred["deferred_to"]) == (
        Decimal(24_000_000), "DZD", "step 6 (G4-12)")


@pytest.mark.parametrize("importance, reason", [("REQUIRED", None),
                                                ("PREFERRED", "AREA_BELOW_PREFERENCE"),
                                                ("FLEXIBLE", "AREA_BELOW_PREFERENCE")])
def test_an_area_fail_carries_the_preference_code_only_when_soft(session, ids, importance,
                                                                 reason):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "LAND_AREA_MIN", "GTE", 500, importance=importance)
    prop = _property(session, land=400)
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), "LAND_AREA_MIN")
    assert (r.compatibility, r.reason_code, r.explanation["basis"]) == (
        "FAIL", reason, "AREA_MINIMUM")


@pytest.mark.parametrize("importance, reason", [("REQUIRED", "LOCATION_MISMATCH"),
                                                ("PREFERRED", None), ("FLEXIBLE", None)])
def test_a_location_fail_carries_the_required_code_only_when_required(session, ids,
                                                                      importance, reason):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "LOCATION", "EQ", str(_loc(session, "C-TAMEST")), importance=importance)
    prop = _property(session, loc=_loc(session, "ADR-CENTER"))
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), "LOCATION")
    assert (r.compatibility, r.reason_code, r.explanation["basis"]) == (
        "FAIL", reason, "LOCATION_SUBTREE")


@pytest.mark.parametrize("importance, reason", [("REQUIRED", "DOCUMENT_MISMATCH"),
                                                ("PREFERRED", None), ("FLEXIBLE", None)])
def test_a_document_fail_carries_the_required_code_only_when_required(session, ids,
                                                                      importance, reason):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", importance=importance)
    prop = _property(session, ptype="LAND")
    _attribute(session, prop, "DOCUMENT_TYPE", "POSSESSION_CERTIFICATE")
    r = _result(_gate(session, req, prop, _offer(session, ids, prop, ask=1)), "DOCUMENT_TYPE")
    assert (r.compatibility, r.reason_code, r.explanation["basis"]) == (
        "FAIL", reason, "ATTRIBUTE_OPTION")


# --- G4-18 (b), decided in the review of f789a59 --------------------------------------------

@pytest.mark.parametrize("code, attribute", [("ROOMS_MIN", "ROOMS"),
                                             ("BEDROOMS_MIN", "BEDROOMS")])
def test_a_count_on_a_type_the_attribute_cannot_apply_to_fails(session, ids, code, attribute):
    """G4-18 (b): ROOMS and BEDROOMS apply to HOUSE_VILLA and APARTMENT only
    (seed lines 80–81). On LAND the fact cannot exist, so a REQUIRED minimum
    is a confirmed FAIL, not a blocking unknown that can never be resolved."""
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, code, "GTE", 2)
    land = _property(session, ptype="LAND")
    gate = _gate(session, req, land, _offer(session, ids, land, ask=1))
    r = _result(gate, code)
    assert (r.compatibility, r.reason_code, r.explanation) == (
        "FAIL", None, {"basis": "ATTRIBUTE_NOT_APPLICABLE", "attribute": attribute})
    assert (r.rule_id, r.rule_version) == ("criterion.count_min", "2")
    assert gate.hard_gate_status == "FAIL" and gate.blocking_unknowns == ()


def test_an_applicable_count_that_is_not_recorded_stays_unknown(session, ids):
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "ROOMS_MIN", "GTE", 2)
    flat = _property(session, ptype="APARTMENT")
    r = _result(_gate(session, req, flat, _offer(session, ids, flat, ask=1)), "ROOMS_MIN")
    assert (r.compatibility, r.blocking, r.explanation["basis"]) == (
        "UNKNOWN", True, "ATTRIBUTE_NOT_RECORDED")


def test_applicability_replays_from_the_snapshot_after_the_definition_changed(session, ids):
    """`applies_to` is read from the snapshot (format 3), never the live
    definition. After ROOMS is extended to LAND, the stored snapshot still
    gives FAIL, and a fresh one gives UNKNOWN (applicable, not recorded)."""
    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "ROOMS_MIN", "GTE", 2)
    land = _property(session, ptype="LAND")
    offer = _offer(session, ids, land, ask=1)
    rs, plan = _plan(session, req)
    stored_prop = snapshots.stored_form(snapshots.property_snapshot(session, land))
    stored_offer = snapshots.stored_form(snapshots.commercial_context_snapshot(session, offer))
    assert stored_prop["attribute_applies_to"]["ROOMS"] == ["HOUSE_VILLA", "APARTMENT"]
    before = hard_gate.evaluate(plan, rs, stored_prop, stored_offer)

    session.execute(text("""UPDATE turab.attribute_definitions
                               SET applies_to = ARRAY['HOUSE_VILLA','APARTMENT','LAND']
                                                ::turab.property_type[]
                             WHERE code = 'ROOMS'"""))
    assert hard_gate.evaluate(plan, rs, stored_prop, stored_offer) == before
    assert _result(before, "ROOMS_MIN").compatibility == "FAIL"
    assert _result(_gate(session, req, land, offer), "ROOMS_MIN").compatibility == "UNKNOWN"



def test_count_min_2_refuses_a_snapshot_without_applicability():
    rule = registry.REGISTRY.resolve("criterion.count_min", "2")
    with pytest.raises(RuntimeError, match="G4-18"):
        rule.evaluate({"code": "ROOMS_MIN", "value": Decimal(1), "importance": "REQUIRED"},
                      {}, {"property_type": "LAND", "attributes": []}, None)


# --- the mechanisms behind the three fixes ------------------------------------------------

def test_not_known_options_are_exactly_those_the_rule_calls_unknown(session):
    """`criteria.NOT_KNOWN_OPTIONS` (which values can never PASS) and the
    rule's own UNKNOWN set must agree: every active option is run through
    `attribute_option@2` as the property's value."""
    rule = registry.REGISTRY.resolve("criterion.attribute_option", "2")
    rows = session.execute(text("""
        SELECT d.code, o.option_code FROM turab.attribute_options o
          JOIN turab.attribute_definitions d USING (attribute_definition_id)
         WHERE o.active AND d.code IN ('DOCUMENT_TYPE', 'RIGHT_TYPE')""")).all()
    called_unknown = set()
    for code, option in rows:
        crit = {"code": code, "operator": "EQ", "value": option, "importance": "REQUIRED"}
        out = rule.evaluate(crit, {}, {"attributes": [{"code": code, "value": option}]}, None)
        if out["compatibility"] == "UNKNOWN":
            called_unknown.add(option)
        else:
            assert out["compatibility"] == "PASS", (code, option)
    assert called_unknown == set(criteria.NOT_KNOWN_OPTIONS)


def test_the_importance_of_each_reason_code_is_its_seeded_label(session):
    """`hard_gate.REASON_IMPORTANCE` is read off the seed: a label saying
    "Required" binds its code to REQUIRED, one saying "preference" to the soft
    importances, and every other MATCH code names no importance."""
    labels = dict(session.execute(text(
        "SELECT code, label_en FROM turab.reason_codes WHERE category = 'MATCH'")).all())
    derived = {}
    for code, label in labels.items():
        if label.startswith("Required "):
            derived[code] = frozenset({"REQUIRED"})
        elif "preference" in label.lower():
            derived[code] = frozenset({"PREFERRED", "FLEXIBLE"})
    assert derived == hard_gate.REASON_IMPORTANCE


def test_a_rule_output_naming_another_importance_is_refused():
    reg = registry.RuleRegistry()

    @reg.register("criterion.says_required", "1")
    def says_required(criterion, request, prop, offer):
        return {"compatibility": "FAIL", "property_value": None, "delta": None,
                "evidence_level": None, "evidence_claim_id": None,
                "reason_code": "LOCATION_MISMATCH", "explanation": {}}

    crit = {"code": "LOCATION", "ordinal": 1, "operator": "EQ", "value": "x", "unit": None,
            "blocking_if_unknown": False, "request_criterion_id": None, "source": "ROW",
            "rule_id": "criterion.says_required", "rule_version": "1"}
    hard_gate.evaluate(criteria.CriteriaPlan(({**crit, "importance": "REQUIRED"},), ()),
                       {}, {}, None, registry=reg)
    with pytest.raises(hard_gate.RuleOutputInvalid, match="another importance"):
        hard_gate.evaluate(criteria.CriteriaPlan(({**crit, "importance": "PREFERRED"},), ()),
                           {}, {}, None, registry=reg)


def test_version_2_is_used_and_version_1_stays_registered_beside_it():
    """G4-2: a changed rule is a new version, registered beside the old one."""
    for rule_id in ("criterion.location", "criterion.area_min", "criterion.count_min",
                    "criterion.attribute_option"):
        assert registry.REGISTRY.versions(rule_id) == ("1", "2")
    used = {(rule_id, version) for rule_id, version, _ in criteria.RULES.values()}
    assert used == {("criterion.transaction_intent", "1"), ("criterion.property_type", "1"),
                    ("criterion.location", "2"), ("criterion.budget_max_sale", "1"),
                    ("criterion.area_min", "2"), ("criterion.count_min", "2"),
                    ("criterion.attribute_option", "2")}


# ======================================================================================
# Review of ba5f25e: the pre-check and the rule must judge the same domain
# ======================================================================================
#
# `_can_pass` took the option domain from the options ACTIVE now; the rule
# compares whatever value the property holds. `attribute_options.active` gates
# only new writes (`truth.validate_attribute`), `property_attributes.value` is
# jsonb with no reference to `attribute_options`, and no table references an
# option row. So an option can be deactivated, or deleted, while a property
# still holds its value. Measured against the ba5f25e code:
# evidence/SLICE4-STEP4-REVIEW2-BEFORE-FIX.txt.

def _document_type_property_holding(session, ids, value):
    """A LAND property whose DOCUMENT_TYPE is written through the Slice 3
    validator, which accepts only an ACTIVE option: the option is active now."""
    from turab.services import truth
    prop = _property(session, ptype="LAND")
    truth.upsert_property_attribute(session, property_id=prop, property_type="LAND",
                                    attribute_code="DOCUMENT_TYPE", value=value)
    return prop


def _only_active(session, keep):
    session.execute(text("""
        UPDATE turab.attribute_options o SET active = (o.option_code = ANY(:keep))
          FROM turab.attribute_definitions d
         WHERE d.attribute_definition_id = o.attribute_definition_id
           AND d.code = 'DOCUMENT_TYPE'"""), {"keep": list(keep)})


@pytest.mark.parametrize("retired", ["deactivated", "deleted"])
def test_a_retired_option_held_by_a_property_gets_the_same_verdict_from_both(
        session, ids, retired):
    """The review's case on PostgreSQL. OTHER is written while active; then
    every document type but LAND_BOOK (and the two not-known values) is
    deactivated, and OTHER is deactivated or deleted. `DOCUMENT_TYPE NOT_IN
    [LAND_BOOK, UNKNOWN]` is then judged twice, on the same property:
    - by the pre-check (`criteria_of`): can any property value pass it?
    - by the rule (`attribute_option@2`): does THIS property pass it?
    A refusal while the rule gives PASS is the contradiction."""
    prop = _document_type_property_holding(session, ids, "OTHER")
    _only_active(session, {"LAND_BOOK", "UNKNOWN", "UNSPECIFIED_DOCUMENT"})
    if retired == "deleted":
        session.execute(text("""
            DELETE FROM turab.attribute_options o USING turab.attribute_definitions d
             WHERE d.attribute_definition_id = o.attribute_definition_id
               AND d.code = 'DOCUMENT_TYPE' AND o.option_code = 'OTHER'"""))
    stored = snapshots.stored_form(snapshots.property_snapshot(session, prop))
    assert [a["value"] for a in stored["attributes"]] == ["OTHER"]

    req = _request(session, ids, bmax=30_000_000)
    _row(session, req, "DOCUMENT_TYPE", "NOT_IN", ["LAND_BOOK", "UNKNOWN"])
    rule = registry.REGISTRY.resolve(*criteria.RULES["DOCUMENT_TYPE"][:2])
    verdict = rule.evaluate({"code": "DOCUMENT_TYPE", "operator": "NOT_IN",
                             "value": ["LAND_BOOK", "UNKNOWN"], "importance": "REQUIRED"},
                            {}, stored, None)["compatibility"]
    try:
        _plan(session, req)
        refused = False
    except CriterionRefused:
        refused = True
    assert verdict == "PASS"
    assert not refused, "the pre-check says no property can pass; this property passes"
    gate = _gate(session, req, prop, _offer(session, ids, prop, ask=1))
    assert _result(gate, "DOCUMENT_TYPE").compatibility == "PASS"


OPTION_POOL = ("LAND_BOOK", "POSSESSION_CERTIFICATE", "OTHER", "UNKNOWN",
               "UNSPECIFIED_DOCUMENT", "A_VALUE_NO_OPTION_NAMES")


def _sets():
    import itertools
    for size in (1, 2, len(OPTION_POOL) - 1, len(OPTION_POOL)):
        yield from (list(c) for c in itertools.combinations(OPTION_POOL, size))


def test_the_pre_check_refuses_exactly_what_the_rule_can_never_pass():
    """Exhaustive over EQ, NEQ, IN and NOT_IN on a pool that holds known,
    not-known and unregistered values, plus a value in no set at all: the
    pre-check accepts a criterion exactly when some property value gets PASS
    from `attribute_option@2`. No vocabulary is involved, so no state of
    `attribute_options` can make the two disagree."""
    rule = registry.REGISTRY.resolve(*criteria.RULES["DOCUMENT_TYPE"][:2])
    candidates = OPTION_POOL + ("A_FRESH_VALUE_IN_NO_SET",)
    checked = 0
    for operator in ("EQ", "NEQ", "IN", "NOT_IN"):
        for values in _sets():
            if operator in ("EQ", "NEQ") and len(values) != 1:
                continue
            value = values if operator in ("IN", "NOT_IN") else values[0]
            crit = {"code": "DOCUMENT_TYPE", "operator": operator, "value": value,
                    "importance": "REQUIRED"}
            some_pass = any(rule.evaluate(crit, {}, {"attributes": [
                {"code": "DOCUMENT_TYPE", "value": v}]}, None)["compatibility"] == "PASS"
                for v in candidates)
            assert criteria.can_pass("DOCUMENT_TYPE", operator, value) is some_pass, (
                operator, value)
            checked += 1
    assert checked == 2 * 6 + 2 * (6 + 15 + 6 + 1)
