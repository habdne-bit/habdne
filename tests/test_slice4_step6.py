"""Slice 4 step 6: the soft score (G4-12), and the pinned gates.

Ref: `docs/gate/SLICE_4_PLAN.md` G4-12, and the pinning of the gates, both
decided in the review of a5ea6f5; G4-2; G4-7; G4-13; mandatory test 2;
Developer Spec §12.1, §12.2; `src/turab/matching/gates.py`, `soft.py`.
"""
from __future__ import annotations

import builtins
import dis
import inspect
import types
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction

import pytest
from sqlalchemy import text

from turab.matching import (criteria, eligibility, gates, hard_gate, policy, registry,
                            snapshots, soft)

AS_OF = datetime(2026, 10, 2, 12, 0, 0, tzinfo=timezone.utc)
DAY = timedelta(days=1)
SCORE = registry.REGISTRY.resolve(*soft.SOFT_SCORE).evaluate
PINNED = ("freshness.state@1", "freshness.gate@1", "permission.binding_state@1",
          "permission.gate@1", "eligibility.precedence@1", "score.soft@1")


# ======================================================================================
# The gates and the score are pinned (review of a5ea6f5)
# ======================================================================================

def _globals_read(code: types.CodeType) -> set[str]:
    names = {i.argval for i in dis.get_instructions(code) if i.opname == "LOAD_GLOBAL"}
    for const in code.co_consts:
        if isinstance(const, types.CodeType):
            names |= _globals_read(const)
    return names


def test_every_registered_function_is_self_contained():
    """A pin covers a function's own source (G4-2). Beyond the builtins, a
    registered function may read only these stable names: the criterion
    rules `Decimal`; the gates and the score also `datetime`, `timedelta`,
    `timezone` and `Fraction`."""
    allowed = {"Decimal", "Fraction", "datetime", "timedelta", "timezone"}
    offenders = {r.key: sorted(extra) for r in registry.REGISTRY.rules()
                 if (extra := {n for n in _globals_read(r.evaluate.__code__)
                               if n not in allowed and not hasattr(builtins, n)})}
    assert offenders == {}


def test_the_gates_and_the_score_are_registered_and_pinned():
    keys = {r.key for r in registry.REGISTRY.rules()}
    assert set(PINNED) <= keys
    assert registry.REGISTRY.verify_pins(registry.load_pins()) == []
    for key in PINNED:
        assert inspect.getmodule(registry.REGISTRY.resolve(*key.split("@")).evaluate) is gates


def test_the_engine_registers_every_pinned_function_on_its_own():
    """In a fresh interpreter that imports only what the engine imports (not
    `gates` or `rules`), the registry already holds every pinned function and
    agrees with the pins. Inside this test module the check would prove
    nothing: it imports `gates` itself (found by mutation K4)."""
    import json
    import subprocess
    import sys
    code = ("import json; from turab.matching import eligibility, soft, criteria, registry; "
            "print(json.dumps({'keys': sorted(r.key for r in registry.REGISTRY.rules()), "
            "'pins': registry.REGISTRY.verify_pins(registry.load_pins())}))")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                         check=True)
    found = json.loads(out.stdout)
    assert set(PINNED) <= set(found["keys"])
    assert found["pins"] == []
    assert len(found["keys"]) == len(registry.load_pins())


def test_a_change_to_a_gate_changes_the_registry_digest_and_so_the_hash():
    """The digest is an input of the match hash (G4-13). Two registries that
    differ only in the source of `eligibility.precedence@1` have different
    digests."""
    def build(precedence):
        reg = registry.RuleRegistry()
        for r in registry.REGISTRY.rules():
            fn = precedence if r.key == "eligibility.precedence@1" else r.evaluate
            reg.register(r.rule_id, r.rule_version)(fn)
        return reg

    def altered(hard, freshness_gate, permission_gate):
        return {"eligibility": "ELIGIBLE", "reasons": []}

    same = build(registry.REGISTRY.resolve("eligibility.precedence", "1").evaluate)
    assert same.digest() == registry.REGISTRY.digest()
    assert build(altered).digest() != registry.REGISTRY.digest()


def test_each_result_names_the_versions_that_decided_it(session, ids):
    req, prop, offer = _world(session, ids)
    run = _evaluate(session, req, prop, offer)
    assert run["freshness"]["derived_by"] == "freshness.state@1"
    assert run["permission"]["derived_by"] == "permission.binding_state@1"
    assert dict(run["eligibility"].engine) == {
        "freshness_gate": "freshness.gate@1", "permission_gate": "permission.gate@1",
        "precedence": "eligibility.precedence@1"}
    assert run["soft"].engine == "score.soft@1"
    for key in ("freshness.state@1", "permission.binding_state@1",
                *run["eligibility"].engine.values(), run["soft"].engine):
        registry.REGISTRY.resolve(*key.split("@"))


# ======================================================================================
# G4-12, as decided
# ======================================================================================

def _c(importance, compatibility, code="X", rule_id="criterion.x", ordinal=1):
    return {"criterion_code": code, "ordinal": ordinal, "importance": importance,
            "compatibility": compatibility, "rule_id": rule_id}


def _t(importance, value, source="ROW"):
    return {"source": source, "request_criterion_id": None, "importance": importance,
            "value": Decimal(value)}


SALE = {"transaction_type": "SALE", "asking_price_dzd": Decimal(20_000_000)}


@pytest.mark.parametrize("criteria_in, expected", [
    ([_c("PREFERRED", "PASS")], "1.000000"),
    ([_c("PREFERRED", "PASS"), _c("FLEXIBLE", "FAIL", "Y")], "0.666667"),     # 2/3
    ([_c("PREFERRED", "UNKNOWN"), _c("FLEXIBLE", "PASS", "Y")], "0.333333"),  # 1/3
    ([_c("PREFERRED", "FAIL"), _c("FLEXIBLE", "UNKNOWN", "Y")], "0.000000"),
    # REQUIRED criteria are the hard gate's, never a term:
    ([_c("REQUIRED", "PASS"), _c("FLEXIBLE", "FAIL", "Y")], "0.000000"),
    # G4-7: a soft criterion without a deterministic rule carries no weight:
    ([_c("PREFERRED", "PASS"), _c("PREFERRED", "UNKNOWN", "Z",
                                  rule_id="criterion.no_deterministic_rule")], "1.000000"),
])
def test_weights_and_contributions(criteria_in, expected):
    out = SCORE("PASS", criteria_in, [], SALE)
    assert out["soft_score"] == Decimal(expected) and out["basis"] == "WEIGHTED_SHARE"
    assert str(out["soft_score"]) == expected


@pytest.mark.parametrize("target, ask, proximity", [
    (20_000_000, 20_000_000, Fraction(1)),
    (20_000_000, 10_000_000, Fraction(1, 2)),
    (20_000_000, 22_000_000, Fraction(9, 10)),     # above the target, symmetric
    (20_000_000, 50_000_000, Fraction(0)),          # min(1, ...) caps the distance
    (0, 0, Fraction(1)),                            # zero target, zero ask
    (0, 1, Fraction(0)),                            # zero target, positive ask
    (20_000_000, None, Fraction(0)),                # no asking price
])
def test_a_budget_target_contributes_its_proximity(target, ask, proximity):
    offer = {"transaction_type": "SALE",
             "asking_price_dzd": None if ask is None else Decimal(ask)}
    out = SCORE("PASS", [], [_t("FLEXIBLE", target)], offer)
    [term] = out["terms"]
    assert term["contribution"] == f"{proximity.numerator}/{proximity.denominator}"
    assert out["soft_score"] == Decimal(round(proximity * 1_000_000)).scaleb(-6)


def test_a_target_is_weighted_by_its_importance():
    """A PREFERRED target at 1/2 beside a FLEXIBLE FAIL: (2 x 1/2 + 1 x 0) / 3."""
    out = SCORE("PASS", [_c("FLEXIBLE", "FAIL")], [_t("PREFERRED", 40_000_000)], SALE)
    assert out["soft_score"] == Decimal("0.333333")


@pytest.mark.parametrize("hard_status", ["FAIL", "UNKNOWN"])
def test_no_score_unless_the_hard_gate_passes(hard_status):
    out = SCORE(hard_status, [_c("PREFERRED", "PASS")], [_t("PREFERRED", 20_000_000)], SALE)
    assert (out["soft_score"], out["basis"]) == (None, "HARD_GATE_NOT_PASS")


def test_no_score_without_a_soft_term():
    out = SCORE("PASS", [_c("REQUIRED", "PASS"),
                         _c("FLEXIBLE", "UNKNOWN", rule_id="criterion.no_deterministic_rule")],
                [], SALE)
    assert (out["soft_score"], out["basis"]) == (None, "NO_SOFT_CRITERION")


def test_rounding_is_half_up_like_postgresql_numeric(session):
    """An exact half at the seventh place: a FLEXIBLE target of 2,000,000 and
    an ask of 3,999,999 give 1/2,000,000 = 0.0000005. Half up gives 0.000001;
    half even would give 0.000000. PostgreSQL rounds the same value into
    numeric(7,6) the same way, and so for the other cases."""
    cases = [
        ([], [_t("FLEXIBLE", 2_000_000)], {"transaction_type": "SALE",
                                          "asking_price_dzd": Decimal(3_999_999)}),
        ([_c("PREFERRED", "PASS"), _c("FLEXIBLE", "FAIL", "Y")], [], SALE),
        ([_c("PREFERRED", "UNKNOWN"), _c("FLEXIBLE", "PASS", "Y")], [], SALE),
        ([_c("FLEXIBLE", "PASS")], [_t("PREFERRED", 3)], {"transaction_type": "SALE",
                                                         "asking_price_dzd": Decimal(1)}),
    ]
    for criteria_in, targets, offer in cases:
        out = SCORE("PASS", criteria_in, targets, offer)
        weights = {"PREFERRED": 2, "FLEXIBLE": 1}
        exact = sum((t["weight"] * Fraction(*map(int, t["contribution"].split("/")))
                     for t in out["terms"]), Fraction(0)) / sum(
            weights[c["importance"]] for c in criteria_in + targets)
        pg = session.execute(text("SELECT CAST(round(CAST(:n AS numeric) / :d, 6) "
                                  "AS numeric(7,6))"),
                             {"n": exact.numerator, "d": exact.denominator}).scalar_one()
        assert out["soft_score"] == pg, (out["terms"], pg)
    assert SCORE("PASS", *cases[0])["soft_score"] == Decimal("0.000001")


def test_the_seller_expectation_is_never_read():
    """G4-12 as decided: `seller_expectation_dzd` stays out of the
    calculation. The score is the same with or without it, and the formula's
    source never names it."""
    with_exp = dict(SALE, seller_expectation_dzd=Decimal(24_000_000))
    a = SCORE("PASS", [], [_t("PREFERRED", 24_000_000)], with_exp)
    b = SCORE("PASS", [], [_t("PREFERRED", 24_000_000)], SALE)
    assert a == b and a["soft_score"] == Decimal("0.833333")
    assert "seller_expectation" not in inspect.getsource(gates.soft_score_v1).split(
        '"""')[2]


def test_a_target_on_a_rent_offer_is_refused():
    """G4-5R: no numeric comparison of a rent price."""
    with pytest.raises(RuntimeError, match="G4-5R"):
        SCORE("PASS", [], [_t("PREFERRED", 70_000)],
              {"transaction_type": "RENT", "asking_price_dzd": Decimal(70_000)})


# ======================================================================================
# On PostgreSQL: the whole of steps 4 to 6
# ======================================================================================

def _one(session, sql, **p):
    return session.execute(text(sql), p).scalar_one()


def _row(session, req, code, operator, value, importance):
    import json
    session.execute(text("""
        INSERT INTO turab.request_criteria (request_id, criterion_code, importance, operator,
                                            value, sort_order)
        VALUES (:r, :c, CAST(:i AS turab.criterion_importance),
                CAST(:o AS turab.criterion_operator), CAST(:v AS jsonb),
                (SELECT count(*) + 1 FROM turab.request_criteria WHERE request_id = :r))"""),
        {"r": req, "c": code, "i": importance, "o": operator, "v": json.dumps(value)})


def _world(session, ids, document="LAND_BOOK", target_column=None):
    req = _one(session, """
        INSERT INTO turab.requests (party_id, transaction_intent, status, management_mode,
                                    claim_status, budget_max_dzd, budget_target_dzd,
                                    last_confirmed_at)
        VALUES (:p, 'BUY', 'ACTIVE', 'ASSISTED', 'UNCLAIMED', 30000000, :t, :c)
        RETURNING request_id""", p=ids.BRAHIM, t=target_column, c=AS_OF - DAY)
    _row(session, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    _row(session, req, "PROPERTY_TYPE", "EQ", "LAND", "PREFERRED")
    _row(session, req, "LAND_AREA_MIN", "GTE", 300, "FLEXIBLE")
    _row(session, req, "BUDGET_TARGET", "EQ", 20_000_000, "PREFERRED")
    prop = _one(session, """
        INSERT INTO turab.properties (property_type, supply_mode, management_mode, claim_status,
                                      land_area_m2, availability_last_confirmed_at,
                                      current_availability)
        VALUES ('LAND', 'PUBLIC', 'ASSISTED', 'UNCLAIMED', 400, :c, 'AVAILABLE')
        RETURNING property_id""", c=AS_OF - DAY)
    session.execute(text("""
        INSERT INTO turab.property_attributes (property_id, attribute_definition_id, value)
        SELECT :p, attribute_definition_id, CAST(:v AS jsonb)
          FROM turab.attribute_definitions WHERE code = 'DOCUMENT_TYPE'"""),
        {"p": prop, "v": f'"{document}"'})
    offer = _one(session, """
        INSERT INTO turab.property_offers (property_id, party_id, transaction_type, status,
                                           asking_price_dzd, price_negotiable,
                                           commercial_terms_last_confirmed_at)
        VALUES (:p, :party, 'SALE', 'ACTIVE', 20000000, 'NO', :c) RETURNING offer_id""",
        p=prop, party=ids.BRAHIM, c=AS_OF - DAY)
    consent = _one(session, """
        INSERT INTO turab.consent_grants (party_id, scope, channel, consent_version, granted_at)
        VALUES (:party, 'PRIVATE_MATCHING_ONLY', 'PHONE_CONFIRMED', 'v1', :at)
        RETURNING consent_id""", party=ids.BRAHIM, at=AS_OF - 2 * DAY)
    session.execute(text("""
        INSERT INTO turab.resource_consent_bindings (consent_id, purpose, offer_id, bound_at)
        VALUES (:c, 'PRIVATE_MATCHING_ONLY', :o, :at)"""),
        {"c": consent, "o": offer, "at": AS_OF - DAY})
    return req, prop, offer


def _evaluate(session, req, prop, offer):
    rs = snapshots.request_snapshot(session, req)
    plan = criteria.criteria_of(rs, criteria.read_vocabulary(session, rs))
    ps = snapshots.property_snapshot(session, prop)
    cs = snapshots.commercial_context_snapshot(session, offer)
    hard = hard_gate.evaluate(plan, rs, ps, cs)
    active = policy.load_active_policy(session)
    fs = snapshots.freshness_snapshot(rs, ps, cs, policy_version=active.version,
                                      threshold_days=active.freshness_threshold_days,
                                      as_of=AS_OF)
    perm = snapshots.permission_snapshot(session, offer, as_of=AS_OF)
    return {"eligibility": eligibility.eligibility_of(hard, fs, perm),
            "soft": soft.soft_score(plan, hard, cs), "freshness": fs, "permission": perm}


def test_a_hard_fail_is_rejected_whatever_the_soft_score(session, ids):
    """Mandatory test 2, its engine half, under its planned name (G01, §12.1).
    Every soft criterion of this candidate passes, and its target is met
    exactly. A REQUIRED document mismatch still rejects it, and no score is
    computed. The same candidate with the right document is ELIGIBLE with
    the full score."""
    req, prop, offer = _world(session, ids, document="POSSESSION_CERTIFICATE")
    run = _evaluate(session, req, prop, offer)
    assert run["eligibility"].eligibility == "REJECTED"
    assert (run["soft"].soft_score, run["soft"].basis) == (None, "HARD_GATE_NOT_PASS")

    req, prop, offer = _world(session, ids, document="LAND_BOOK")
    run = _evaluate(session, req, prop, offer)
    assert run["eligibility"].eligibility == "ELIGIBLE"
    assert run["soft"].soft_score == Decimal("1.000000")
    assert [(t["kind"], t["weight"], t["contribution"]) for t in run["soft"].terms] == [
        ("CRITERION", 2, "1/1"), ("CRITERION", 1, "1/1"), ("BUDGET_TARGET", 2, "1/1")]


def test_the_schema_refuses_to_approve_a_rejected_match(session, ids):
    """Mandatory test 2, its schema half: `enforce_approved_review_gate`
    refuses an APPROVED review of a match that is not ELIGIBLE with all four
    gates PASS. The rows are fixtures inside the rolled-back session; the
    engine writes nothing in this step."""
    from sqlalchemy.exc import DBAPIError
    req, prop, offer = _world(session, ids, document="POSSESSION_CERTIFICATE")
    pol, version = session.execute(text(
        "SELECT matching_policy_id, version FROM turab.matching_policies WHERE active")).one()
    match = _one(session, """
        INSERT INTO turab.match_candidates
          (request_id, property_id, evaluated_offer_id, matching_policy_id,
           matching_policy_version, request_version, property_version, offer_version,
           eligibility, hard_gate_status, information_gate_status, request_freshness,
           property_freshness, freshness_gate_status, permission_gate_status,
           request_snapshot, property_snapshot, input_hash)
        VALUES (:r, :p, :o, :pol, :v, 1, 1, 1, 'REJECTED', 'FAIL', 'PASS', 'FRESH', 'FRESH',
                'PASS', 'PASS', '{}', '{}', 'fixture') RETURNING match_id""",
        r=req, p=prop, o=offer, pol=pol, v=version)
    savepoint = session.begin_nested()
    with pytest.raises(DBAPIError, match="before all opportunity gates pass"):
        session.execute(text("""INSERT INTO turab.match_reviews (match_id, decision,
                                                                  reviewer_account_id)
                                VALUES (:m, 'APPROVED', :a)"""),
                        {"m": match, "a": ids.ACC_REVIEWER})
    savepoint.rollback()


def test_the_score_fits_the_column(session, ids):
    req, prop, offer = _world(session, ids)
    score = _evaluate(session, req, prop, offer)["soft"].soft_score
    assert session.execute(text("SELECT CAST(:s AS numeric(7,6))"), {"s": score}
                           ).scalar_one() == score


def test_the_request_target_column_is_refused_until_its_weight_is_decided(session, ids):
    """G4-12 gives weights by importance; `budget_target_dzd` has none of its
    own. Acceptance condition 1: refused, naming G4-12, whatever the hard
    gate says."""
    for document in ("LAND_BOOK", "POSSESSION_CERTIFICATE"):
        req, prop, offer = _world(session, ids, document=document,
                                  target_column=20_000_000)
        with pytest.raises(soft.SoftScoreUndecided) as refused:
            _evaluate(session, req, prop, offer)
        assert refused.value.decision == "G4-12"


def test_scoring_writes_nothing(session, ids):
    req, prop, offer = _world(session, ids)
    tables = ("requests", "request_criteria", "properties", "property_offers",
              "match_candidates", "match_criterion_results", "match_diagnostic_runs",
              "audit_log")

    def counts():
        return {t: _one(session, f"SELECT count(*) FROM turab.{t}") for t in tables}

    before = counts()
    _evaluate(session, req, prop, offer)
    assert counts() == before
