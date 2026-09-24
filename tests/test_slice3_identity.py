"""Identity Lite — Slice 3, step 7, over HTTP on PostgreSQL.

Ref: `services/identity.py`; ADR-03; Developer Spec §8; red-team E01–E04;
`docs/gate/SLICE_3_PLAN.md` §3.10, §6.1 (mandatory tests 6 and 7), §6.2
(Identity), §6.3 (the pair race); `docs/gate/SLICE_3_STEP7_DELIVERY.md`.

**Isolation.** HTTP tests commit to a shared database. Each test builds its
properties under a location created for it, and generation is always focused
(`property_id`), so it only sees that test's pairs.

**Seeded matches and opportunities** (plan §6.4). No slice creates them yet,
so the corrective-effect tests insert them with SQL. Each passes the schema's
own gates (`enforce_match_commercial_context`, `enforce_approved_review_gate`,
`enforce_opportunity_gate`), so each is a row the schema accepts.
"""
from __future__ import annotations

import json
import threading
import time
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink

GEN = "/identity/candidates/generate"


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _h(account):
    return {"Authorization": f"Bearer {account}", "Idempotency-Key": str(uuid.uuid4())}


def _one(engine, sql, **p):
    with engine.begin() as conn:
        return conn.execute(text(sql), p).scalar_one()


def _all(engine, sql, **p):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), p).mappings()]


def _run(engine, sql, **p):
    with engine.begin() as conn:
        conn.execute(text(sql), p)


def _location(engine):
    return _one(engine, """INSERT INTO turab.locations (code, canonical_ar, location_type)
                           VALUES (:c, 'موقع اختبار', 'AREA') RETURNING location_id""",
                c=f"TEST-IDN-{uuid.uuid4().hex[:16]}")


def _property(client, ids, loc, *, ptype="LAND", land=270, built=None,
              detail="قرب البئر القديمة"):
    body = {"property_type": ptype, "supply_mode": "PUBLIC",
            "management_mode": "ASSISTED", "claim_status": "UNCLAIMED",
            "canonical_location_id": str(loc), "local_location_detail": detail}
    if land is not None:
        body["land_area_m2"] = land
    if built is not None:
        body["built_area_m2"] = built
    r = client.post("/properties", headers=_h(ids.ACC_OPERATOR), json=body)
    assert r.status_code == 201, r.text
    return r.json()["property_id"]


def _pair(client, ids, **kw):
    loc = _location(kw.pop("engine"))
    return loc, _property(client, ids, loc, **kw), _property(client, ids, loc, **kw)


def _generate(client, ids, pid, **extra):
    r = client.post(GEN, headers=_h(ids.ACC_OPERATOR), json={"property_id": pid, **extra})
    assert r.status_code == 201, r.text
    return r.json()


def _review(client, ids, cid, account=None, **body):
    return client.post(f"/identity/candidates/{cid}/review",
                       headers=_h(account or ids.ACC_REVIEWER), json=body)


def _same(client, ids, engine, **kw):
    """A pair, its candidate, and the candidate confirmed SAME with the first
    property canonical. Returns (canonical, alias, candidate_id)."""
    _, a, b = _pair(client, ids, engine=engine, **kw)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    r = _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=a)
    assert r.status_code == 200, r.text
    return a, b, cid


# --- generation ---------------------------------------------------------------

def test_an_omitted_algorithm_version_is_stored_as_the_contract_default(client, ids,
                                                                        engine):
    """Plan §3.10: the contract defaults to rules-0.1.0, the column to
    rules-0.2.0. The service writes the value, so the column never decides."""
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    assert _one(engine, "SELECT algorithm_version FROM turab.property_identity_candidates "
                        "WHERE identity_candidate_id = :c", c=cid) == "rules-0.1.0"
    assert _one(engine, """SELECT column_default FROM information_schema.columns
                            WHERE table_schema = 'turab'
                              AND table_name = 'property_identity_candidates'
                              AND column_name = 'algorithm_version'""") \
        == "'rules-0.2.0'::text", "the premise: the column's default differs"


def test_an_algorithm_version_that_names_no_implemented_algorithm_is_refused(client,
                                                                            ids, engine):
    _, a, _ = _pair(client, ids, engine=engine)
    h = _h(ids.ACC_OPERATOR)
    r = client.post(GEN, headers=h, json={"property_id": a, "algorithm_version": "rules-9.9.9"})
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_FAILED", r.text
    assert "rules-9.9.9" not in r.text, "the caller's text is not echoed"
    assert _one(engine, """SELECT count(*) FROM turab.property_identity_candidates
                            WHERE :a IN (property_a_id, property_b_id)""", a=a) == 0
    ok = client.post(GEN, headers=h, json={"property_id": a,
                                           "algorithm_version": "rules-0.1.0"})
    assert ok.status_code == 201, "the refused call did not consume the key"


def test_generation_only_ever_writes_pending_review(client, ids, engine):
    _, a, b = _pair(client, ids, engine=engine)
    out = _generate(client, ids, a)
    assert [c["review_status"] for c in out] == ["PENDING_REVIEW"]
    assert {out[0]["property_a_id"], out[0]["property_b_id"]} == {a, b}
    assert _all(engine, """SELECT review_status::text AS s, reviewer_account_id
                             FROM turab.property_identity_candidates
                            WHERE :a IN (property_a_id, property_b_id)""", a=a) \
        == [{"s": "PENDING_REVIEW", "reviewer_account_id": None}]


def test_a_pair_is_stored_least_first_whichever_side_generated_it(client, ids, engine):
    _, a, b = _pair(client, ids, engine=engine)
    c = _generate(client, ids, b)[0]
    assert (c["property_a_id"], c["property_b_id"]) == tuple(sorted([a, b]))


def test_generating_twice_is_idempotent_for_a_pending_pair(client, ids, engine):
    _, a, _ = _pair(client, ids, engine=engine)
    first = _generate(client, ids, a)
    second = _generate(client, ids, a)
    assert first == second
    assert _one(engine, """SELECT count(*) FROM turab.property_identity_candidates
                            WHERE :a IN (property_a_id, property_b_id)""", a=a) == 1


def test_generating_twice_produces_identical_signals(client, ids, engine):
    """Reproducibility (plan §3.10): two pairs with equal facts, in two
    locations, generated separately, carry equal `signals` and
    `explanation`. Neither object carries an id or a time."""
    _, a1, _ = _pair(client, ids, engine=engine, land=270, built=180)
    _, a2, _ = _pair(client, ids, engine=engine, land=270, built=180)
    c1, c2 = _generate(client, ids, a1)[0], _generate(client, ids, a2)[0]
    assert c1["signals"] == c2["signals"]
    assert c1["explanation"] == c2["explanation"]
    assert c1["identity_candidate_id"] != c2["identity_candidate_id"]


@pytest.mark.parametrize("change", ["type", "location", "no_location"])
def test_blocking_proposes_no_pair_across_type_or_location(client, ids, engine, change):
    loc = _location(engine)
    a = _property(client, ids, loc)
    if change == "type":
        _property(client, ids, loc, ptype="APARTMENT", land=None, built=90)
    elif change == "location":
        _property(client, ids, _location(engine))
    else:
        r = client.post("/properties", headers=_h(ids.ACC_OPERATOR), json={
            "property_type": "LAND", "supply_mode": "PUBLIC",
            "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"})
        assert r.status_code == 201
        a = r.json()["property_id"]
    assert _generate(client, ids, a) == []


def test_a_decided_pair_is_not_reopened_by_generation(client, ids, engine):
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    assert _review(client, ids, cid, decision="CONFIRMED_DISTINCT").status_code == 200
    assert _generate(client, ids, a) == []
    assert _one(engine, """SELECT count(*) FROM turab.property_identity_candidates
                            WHERE :a IN (property_a_id, property_b_id)""", a=a) == 1


def test_generation_for_an_unknown_property_is_404(client, ids):
    r = client.post(GEN, headers=_h(ids.ACC_OPERATOR), json={"property_id": str(uuid.uuid4())})
    assert r.status_code == 404, r.text


def test_generation_for_an_alias_is_refused_and_aliases_are_never_paired(client, ids,
                                                                        engine):
    canonical, alias, _ = _same(client, ids, engine)
    r = client.post(GEN, headers=_h(ids.ACC_OPERATOR), json={"property_id": alias})
    assert r.status_code == 409 and r.json()["code"] == "IDENTITY_ALIAS_NOT_CANONICAL"
    loc = _one(engine, "SELECT canonical_location_id FROM turab.properties "
                       "WHERE property_id = :p", p=canonical)
    third = _property(client, ids, loc)
    out = _generate(client, ids, third)
    assert [sorted([c["property_a_id"], c["property_b_id"]]) for c in out] \
        == [sorted([canonical, third])], "the alias is not a generation input"


def test_an_operator_generates_and_a_reviewer_cannot(client, ids, engine):
    """x-roles: ADMIN, OPERATOR."""
    _, a, _ = _pair(client, ids, engine=engine)
    r = client.post(GEN, headers=_h(ids.ACC_REVIEWER), json={"property_id": a})
    assert r.status_code == 403, r.text


# --- rules-0.1.0 signals ---------------------------------------------------------

def _facts(land=None, built=None, detail=None):
    return {"land_area_m2": None if land is None else Decimal(str(land)),
            "built_area_m2": None if built is None else Decimal(str(built)),
            "local_location_detail": detail}


@pytest.mark.parametrize("a,b,expected", [
    (270, 268.5, "CLOSE"), (100, 110, "CLOSE"), (100, 110.01, "APART"),
    (100, 149.99, "APART"), (100, 150, "CONTRADICTION"), (270, 600, "CONTRADICTION"),
    (None, 100, "ONE_UNKNOWN"), (None, None, "BOTH_UNKNOWN"),
])
def test_area_signal_boundaries_of_rules_0_1_0(a, b, expected):
    """Developer Spec §8.2 names "مساحة متقاربة" (medium) and "270 مقابل 600"
    (a contradiction). The ratios 1.10 and 1.50 are this version's."""
    from turab.services.identity import signals_for

    signals, explanation = signals_for(_facts(land=a), _facts(land=b), shared_party=False)
    assert signals["land_area"] == expected
    assert ("land_area_contradiction" in explanation["contradictions"]) \
        == (expected == "CONTRADICTION")


def test_the_local_detail_is_compared_normalized():
    from turab.services.identity import signals_for

    s, e = signals_for(_facts(detail="  قرب   البئر "), _facts(detail="قرب البئر"),
                       shared_party=False)
    assert s["local_location_detail"] == "EQUAL"
    assert "local_location_detail_equal" in e["medium"]


def test_a_party_offering_on_both_properties_is_a_strong_signal(client, ids, engine):
    _, a, b = _pair(client, ids, engine=engine)
    for pid in (a, b):
        r = client.post(f"/properties/{pid}/offers", headers=_h(ids.ACC_OPERATOR),
                        json={"party_id": str(ids.BRAHIM), "transaction_type": "SALE"})
        assert r.status_code == 201, r.text
    c = _generate(client, ids, a)[0]
    assert c["signals"]["shared_offer_party"] is True
    assert c["explanation"]["strong"] == ["shared_offer_party"]


# --- review: the decision --------------------------------------------------------

def test_an_operator_cannot_review(client, ids, engine):
    """x-roles: ADMIN, REVIEWER; OPERATOR excluded (maker-checker)."""
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    r = _review(client, ids, cid, account=ids.ACC_OPERATOR, decision="UNSURE")
    assert r.status_code == 403, r.text


def test_confirmed_same_without_a_canonical_id_is_refused(client, ids, engine):
    """Mandatory test 6 (plan §6.1)."""
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    r = _review(client, ids, cid, decision="CONFIRMED_SAME")
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_FAILED", r.text
    # The caller is told WHAT is missing, not only that the pair is wrong.
    assert "required for CONFIRMED_SAME" in r.json()["detail"], r.text
    assert _one(engine, "SELECT count(*) FROM turab.property_identity_aliases "
                        "WHERE source_identity_candidate_id = :c", c=cid) == 0


def test_the_canonical_must_be_one_of_the_candidate_pair(client, ids, engine):
    """Mandatory test 6 (plan §6.1), the other half."""
    loc, a, _ = _pair(client, ids, engine=engine)
    outsider = _property(client, ids, _location(engine))
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    r = _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=outsider)
    assert r.status_code == 422, r.text
    assert _one(engine, "SELECT review_status::text FROM turab.property_identity_candidates "
                        "WHERE identity_candidate_id = :c", c=cid) == "PENDING_REVIEW"


@pytest.mark.parametrize("decision", ["CONFIRMED_DISTINCT", "UNSURE"])
def test_a_canonical_id_with_another_decision_is_refused(client, ids, engine, decision):
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    r = _review(client, ids, cid, decision=decision, canonical_property_id=a)
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("code", ["OWNER_REJECTED", "NO_SUCH_CODE", "otp"])
def test_a_reason_code_outside_the_identity_category_is_refused(client, ids, engine, code):
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    r = _review(client, ids, cid, decision="UNSURE", reason_code=code)
    assert r.status_code == 422 and r.json()["code"] == "VALIDATION_FAILED", r.text
    assert code not in r.json().get("detail", "")


def test_confirmed_same_writes_the_alias_before_the_status(client, ids, engine):
    """ADR-03's order. The service writes the alias, then the status; the
    trigger refuses the status alone, which is shown directly below (a
    schema guarantee, labelled as such)."""
    canonical, alias, cid = _same(client, ids, engine,)
    row = _all(engine, """SELECT canonical_property_id::text AS canon,
                                 source_identity_candidate_id::text AS c,
                                 resolved_by_account_id::text AS acct
                            FROM turab.property_identity_aliases
                           WHERE alias_property_id = :a""", a=alias)
    assert row == [{"canon": canonical, "c": cid, "acct": str(ids.ACC_REVIEWER)}]
    status = _all(engine, """SELECT review_status::text AS s,
                                    reviewer_account_id::text AS r, reviewed_at IS NOT NULL AS at
                               FROM turab.property_identity_candidates
                              WHERE identity_candidate_id = :c""", c=cid)
    assert status == [{"s": "CONFIRMED_SAME", "r": str(ids.ACC_REVIEWER), "at": True}]


def test_the_trigger_refuses_a_same_status_without_its_alias(client, ids, engine):
    """SCHEMA guarantee (trg_identity_same_requires_alias): the backstop behind
    the service's order, not evidence of the service."""
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    with pytest.raises(Exception, match="requires a canonical alias mapping"):
        _run(engine, "UPDATE turab.property_identity_candidates "
                     "SET review_status = 'CONFIRMED_SAME' WHERE identity_candidate_id = :c",
             c=cid)


def test_e01_confirming_same_deletes_and_rewrites_nothing(client, ids, engine):
    """Red-team E01: offers, claims and observations of both records stay."""
    _, a, b = _pair(client, ids, engine=engine)
    for pid in (a, b):
        client.post(f"/properties/{pid}/offers", headers=_h(ids.ACC_OPERATOR),
                    json={"party_id": str(ids.BRAHIM), "transaction_type": "SALE"})
    counts = """SELECT (SELECT count(*) FROM turab.property_offers WHERE property_id = :p),
                       (SELECT count(*) FROM turab.claims WHERE property_id = :p)"""

    def snapshot():
        with engine.connect() as conn:
            return [tuple(conn.execute(text(counts), {"p": p}).one()) for p in (a, b)]

    before = snapshot()
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    assert _review(client, ids, cid, decision="CONFIRMED_SAME",
                   canonical_property_id=a).status_code == 200
    assert snapshot() == before
    assert _one(engine, "SELECT count(*) FROM turab.properties "
                        "WHERE property_id IN (:a, :b)", a=a, b=b) == 2


def test_e03_similar_units_confirmed_distinct_create_no_alias(client, ids, engine):
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    r = _review(client, ids, cid, decision="CONFIRMED_DISTINCT",
                reason_code="SIMILAR_UNITS_SAME_DEVELOPMENT_NOT_SAME_PROPERTY")
    assert r.status_code == 200, r.text
    assert r.json()["review_reason_code"] == "SIMILAR_UNITS_SAME_DEVELOPMENT_NOT_SAME_PROPERTY"
    assert _one(engine, "SELECT count(*) FROM turab.property_identity_aliases "
                        "WHERE source_identity_candidate_id = :c", c=cid) == 0


def test_unsure_may_be_reviewed_again(client, ids, engine):
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    assert _review(client, ids, cid, decision="UNSURE").status_code == 200
    r = _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=a)
    assert r.status_code == 200 and r.json()["review_status"] == "CONFIRMED_SAME"


@pytest.mark.parametrize("first,then", [("CONFIRMED_DISTINCT", "CONFIRMED_SAME"),
                                        ("CONFIRMED_SAME", "UNSURE"),
                                        ("CONFIRMED_SAME", "CONFIRMED_DISTINCT")])
def test_a_final_decision_is_not_reviewed_again(client, ids, engine, first, then):
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    body = {"canonical_property_id": a} if first == "CONFIRMED_SAME" else {}
    assert _review(client, ids, cid, decision=first, **body).status_code == 200
    again = {"canonical_property_id": a} if then == "CONFIRMED_SAME" else {}
    r = _review(client, ids, cid, decision=then, **again)
    assert r.status_code == 409 and r.json()["code"] == "IDENTITY_CANDIDATE_DECIDED", r.text
    assert _one(engine, "SELECT review_status::text FROM turab.property_identity_candidates "
                        "WHERE identity_candidate_id = :c", c=cid) == first


def test_an_unknown_candidate_is_404(client, ids):
    r = _review(client, ids, uuid.uuid4(), decision="UNSURE")
    assert r.status_code == 404, r.text


# --- review: no alias chains (ADR-03), as typed 409s ------------------------------

def _pending(engine, a, b):
    """A PENDING candidate for a pair generation would not propose (an alias is
    never a generation input), written as fixture to reach the pre-checks."""
    lo, hi = sorted([a, b])
    return str(_one(engine, """INSERT INTO turab.property_identity_candidates
                                      (property_a_id, property_b_id, algorithm_version)
                               VALUES (:a, :b, 'rules-0.1.0')
                               RETURNING identity_candidate_id""", a=lo, b=hi))


def test_the_chosen_canonical_may_not_itself_be_an_alias(client, ids, engine):
    canonical, alias, _ = _same(client, ids, engine)
    loc = _one(engine, "SELECT canonical_location_id FROM turab.properties "
                       "WHERE property_id = :p", p=canonical)
    third = _property(client, ids, loc)
    cid = _pending(engine, alias, third)
    r = _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=alias)
    assert r.status_code == 409 and r.json()["code"] == "IDENTITY_ALIAS_NOT_CANONICAL", r.text


def test_an_alias_may_not_become_an_alias_again(client, ids, engine):
    canonical, alias, _ = _same(client, ids, engine)
    loc = _one(engine, "SELECT canonical_location_id FROM turab.properties "
                       "WHERE property_id = :p", p=canonical)
    third = _property(client, ids, loc)
    cid = _pending(engine, alias, third)
    r = _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=third)
    assert r.status_code == 409 and r.json()["code"] == "IDENTITY_ALIAS_NOT_CANONICAL", r.text


def test_a_canonical_record_may_not_become_an_alias(client, ids, engine):
    canonical, alias, _ = _same(client, ids, engine)
    loc = _one(engine, "SELECT canonical_location_id FROM turab.properties "
                       "WHERE property_id = :p", p=canonical)
    third = _property(client, ids, loc)
    cid = _generate(client, ids, third)[0]["identity_candidate_id"]
    r = _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=third)
    assert r.status_code == 409 and r.json()["code"] == "IDENTITY_ALIAS_NOT_CANONICAL", r.text
    assert _one(engine, "SELECT review_status::text FROM turab.property_identity_candidates "
                        "WHERE identity_candidate_id = :c", c=cid) == "PENDING_REVIEW"


# --- the corrective effect (ADR-03, E04) -------------------------------------------

def _request(client, ids):
    r = client.post("/requests", headers=_h(ids.ACC_OPERATOR), json={
        "party_id": str(ids.AMINA), "transaction_intent": "BUY",
        "intent": "ACTIVE_SEARCH", "management_mode": "ASSISTED",
        "claim_status": "UNCLAIMED"})
    assert r.status_code == 201, r.text
    return r.json()["request_id"]


def _offer(client, ids, pid):
    r = client.post(f"/properties/{pid}/offers", headers=_h(ids.ACC_OPERATOR),
                    json={"party_id": str(ids.BRAHIM), "transaction_type": "SALE"})
    assert r.status_code == 201, r.text
    return r.json()["offer_id"]


def _match(engine, request_id, property_id, offer_id, *, eligible=True):
    gate = "PASS" if eligible else "FAIL"
    return str(_one(engine, """
        INSERT INTO turab.match_candidates (request_id, property_id, evaluated_offer_id,
               matching_policy_id, matching_policy_version, request_version,
               property_version, offer_version, eligibility, hard_gate_status,
               information_gate_status, request_freshness, property_freshness,
               freshness_gate_status, permission_gate_status, request_snapshot,
               property_snapshot, input_hash)
        SELECT :r, :p, :o, mp.matching_policy_id, mp.version,
               (SELECT version FROM turab.requests WHERE request_id = :r),
               (SELECT version FROM turab.properties WHERE property_id = :p),
               (SELECT version FROM turab.property_offers WHERE offer_id = :o),
               CAST(:el AS turab.match_eligibility), CAST(:g AS turab.gate_status),
               'PASS', 'FRESH', 'FRESH', 'PASS', 'PASS', '{}'::jsonb, '{}'::jsonb,
               :h
          FROM turab.matching_policies mp ORDER BY mp.activated_at DESC NULLS LAST LIMIT 1
        RETURNING match_id""",
        r=request_id, p=property_id, o=offer_id, h=f"seeded-{uuid.uuid4().hex}",
        el="ELIGIBLE" if eligible else "REJECTED", g=gate))


def _match_review(engine, match_id, decision, ids):
    _run(engine, """INSERT INTO turab.match_reviews (match_id, decision, reviewer_account_id)
                    VALUES (:m, CAST(:d AS turab.match_review_decision), :acct)""",
         m=match_id, d=decision, acct=ids.ACC_REVIEWER)


def _opportunity(engine, ids, match_id, *, status="NEW"):
    _match_review(engine, match_id, "APPROVED", ids)
    return str(_one(engine, """
        INSERT INTO turab.opportunities (request_id, property_id, approved_match_id,
               current_offer_id, sharing_scope, why_real, created_by_account_id, status)
        SELECT m.request_id, m.property_id, m.match_id, m.evaluated_offer_id,
               'SUMMARY_ONLY', '{}'::jsonb, :acct, CAST(:s AS turab.opportunity_status)
          FROM turab.match_candidates m WHERE m.match_id = :m
        RETURNING opportunity_id""", m=match_id, acct=ids.ACC_OPERATOR, s=status))


def _tasks(engine, alias):
    return _all(engine, """SELECT task_type::text AS type, reason_code, match_id::text AS m,
                                  request_id::text AS r, payload
                             FROM turab.tasks WHERE property_id = :a
                            ORDER BY payload->>'affected', match_id""", a=alias)


def test_confirming_same_raises_review_work_for_affected_open_records(client, ids,
                                                                     engine):
    """Plan §6.2 (Identity). One RESOLVE_IDENTITY task per OPEN match or
    opportunity on the new alias. A rejected match, a closed opportunity, and
    anything on the canonical record raise none. Nothing is changed."""
    loc, canonical, alias = _pair(client, ids, engine=engine)
    req = _request(client, ids)
    open_match = _match(engine, req, alias, _offer(client, ids, alias))
    rejected = _match(engine, req, alias, _offer(client, ids, alias))
    _match_review(engine, rejected, "REJECTED", ids)
    open_opp = _opportunity(engine, ids, _match(engine, req, alias, _offer(client, ids, alias)))
    _opportunity(engine, ids, _match(engine, req, alias, _offer(client, ids, alias)),
                 status="CLOSED")
    _match(engine, req, canonical, _offer(client, ids, canonical))  # on the canonical
    cid = _generate(client, ids, canonical)[0]["identity_candidate_id"]
    assert _review(client, ids, cid, decision="CONFIRMED_SAME",
                   canonical_property_id=canonical).status_code == 200

    tasks = _tasks(engine, alias)
    assert [(t["payload"]["affected"], t["type"], t["reason_code"]) for t in tasks] == [
        ("MATCH", "RESOLVE_IDENTITY", "IDENTITY_CONSOLIDATED"),
        ("OPPORTUNITY", "RESOLVE_IDENTITY", "IDENTITY_CONSOLIDATED")]
    assert tasks[0]["payload"]["match_id"] == open_match
    assert tasks[1]["payload"]["opportunity_id"] == open_opp
    assert {t["payload"]["canonical_property_id"] for t in tasks} == {canonical}
    assert {t["payload"]["identity_candidate_id"] for t in tasks} == {cid}
    assert _all(engine, "SELECT count(*) AS n FROM turab.tasks WHERE property_id = :c",
                c=canonical) == [{"n": 0}]
    assert _one(engine, "SELECT status::text FROM turab.opportunities "
                        "WHERE opportunity_id = :o", o=open_opp) == "NEW", "changed nothing"


def test_a_match_whose_latest_review_is_not_rejected_is_still_open(client, ids, engine):
    """The latest review decides, in the order `enforce_opportunity_gate()`
    itself uses."""
    loc, canonical, alias = _pair(client, ids, engine=engine)
    req = _request(client, ids)
    m = _match(engine, req, alias, _offer(client, ids, alias))
    _match_review(engine, m, "REJECTED", ids)
    time.sleep(0.01)
    _match_review(engine, m, "NEED_MORE_INFORMATION", ids)
    cid = _generate(client, ids, canonical)[0]["identity_candidate_id"]
    _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=canonical)
    assert [t["m"] for t in _tasks(engine, alias)] == [m]


def test_e04_a_duplicate_open_opportunity_is_surfaced_not_closed(client, ids, engine):
    """Red-team E04: alias and canonical both carry an open opportunity for
    the same request. The task names the canonical's; neither is closed."""
    loc, canonical, alias = _pair(client, ids, engine=engine)
    req = _request(client, ids)
    on_alias = _opportunity(engine, ids, _match(engine, req, alias, _offer(client, ids, alias)))
    on_canon = _opportunity(engine, ids,
                            _match(engine, req, canonical, _offer(client, ids, canonical)))
    cid = _generate(client, ids, canonical)[0]["identity_candidate_id"]
    _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=canonical)
    [task] = _tasks(engine, alias)
    assert task["payload"]["opportunity_id"] == on_alias
    assert task["payload"]["duplicate_open_opportunity_ids"] == [on_canon]
    assert _all(engine, """SELECT status::text AS s FROM turab.opportunities
                            WHERE opportunity_id IN (:a, :b)""", a=on_alias, b=on_canon) \
        == [{"s": "NEW"}, {"s": "NEW"}]


def test_e02_a_new_match_on_the_alias_is_refused_by_the_schema(client, ids, engine):
    """SCHEMA guarantee (enforce_match_commercial_context), labelled as such:
    once aliased, a property is not a match target. No matching code exists
    in this slice to exercise it further (plan §6.4)."""
    loc, canonical, alias = _pair(client, ids, engine=engine)
    offer = _offer(client, ids, alias)
    cid = _generate(client, ids, canonical)[0]["identity_candidate_id"]
    _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=canonical)
    with pytest.raises(Exception, match="Matches must target canonical properties"):
        _match(engine, _request(client, ids), alias, offer)


def test_the_canonical_resolver_returns_the_canonical_for_an_alias(client, ids, engine):
    """Mandatory test 7, NARROWED (plan §6.4): proven as a query on an alias
    created through the API. No matching input exists to consume it yet."""
    from turab.auth.loaders import resolve_canonical_property

    canonical, alias, _ = _same(client, ids, engine)
    with Session(bind=engine, future=True) as s:
        assert str(resolve_canonical_property(s, uuid.UUID(alias))) == canonical
        assert str(resolve_canonical_property(s, uuid.UUID(canonical))) == canonical


# --- audit, idempotency, list ----------------------------------------------------

def test_every_identity_write_is_audited(client, ids, engine):
    """None of the three tables has an audit trigger; the command layer
    writes the rows (audit_rows)."""
    loc, canonical, alias = _pair(client, ids, engine=engine)
    req = _request(client, ids)
    _match(engine, req, alias, _offer(client, ids, alias))
    cid = _generate(client, ids, canonical)[0]["identity_candidate_id"]
    _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=canonical)
    task = _tasks(engine, alias)
    rows = _all(engine, """SELECT entity_table, action, actor_account_id::text AS actor
                             FROM turab.audit_log
                            WHERE entity_id IN (:c, :a)
                               OR entity_id IN (SELECT task_id FROM turab.tasks
                                                 WHERE property_id = :a)
                            ORDER BY audit_id""", c=cid, a=alias)
    seen = [(r["entity_table"], r["action"]) for r in rows
            if r["entity_table"] in ("property_identity_candidates",
                                     "property_identity_aliases", "tasks")]
    assert seen == [("property_identity_candidates", "INSERT"),
                    ("property_identity_aliases", "INSERT"),
                    ("property_identity_candidates", "UPDATE"),
                    ("tasks", "INSERT")]
    assert len(task) == 1


def test_a_replayed_review_returns_the_same_answer_and_writes_once(client, ids, engine):
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    h = _h(ids.ACC_REVIEWER)
    body = {"decision": "CONFIRMED_SAME", "canonical_property_id": a}
    first = client.post(f"/identity/candidates/{cid}/review", headers=h, json=body)
    again = client.post(f"/identity/candidates/{cid}/review", headers=h, json=body)
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()
    assert _one(engine, "SELECT count(*) FROM turab.property_identity_aliases "
                        "WHERE source_identity_candidate_id = :c", c=cid) == 1


def test_the_list_filters_by_status_and_pages(client, ids, engine, sink):
    _, a, _ = _pair(client, ids, engine=engine)
    cid = _generate(client, ids, a)[0]["identity_candidate_id"]
    _review(client, ids, cid, decision="UNSURE")
    sink.clear()
    r = client.get("/identity/candidates", headers=_h(ids.ACC_REVIEWER),
                   params={"status": "UNSURE", "page_size": 100})
    assert r.status_code == 200, r.text
    body = r.json()
    assert cid in [c["identity_candidate_id"] for c in body["items"]]
    assert {c["review_status"] for c in body["items"]} == {"UNSURE"}
    assert set(body["meta"]) == {"page", "page_size", "total", "has_next"}
    assert len(sink.records) == 1, "a bulk list is audited once (R6.3c)"
    none = client.get("/identity/candidates", headers=_h(ids.ACC_REVIEWER),
                      params={"status": "NOT_A_STATUS"})
    assert none.status_code == 200 and none.json()["items"] == []


def test_a_customer_cannot_list_candidates(client, ids):
    r = client.get("/identity/candidates", headers=_h(ids.ACC_AMINA))
    assert r.status_code == 403, r.text


# --- integration with steps 1 and 6 ------------------------------------------------

def test_an_alias_made_through_the_api_leaves_the_public_list(client, ids, engine):
    """Step 6 closure item (review of 3a53b0a): with the alias created by
    THIS step's API, not by fixture SQL, the public list drops the alias and
    keeps the canonical with only its own consented offers (G3-13)."""
    loc, canonical, alias = _pair(client, ids, engine=engine)
    listed = {}
    for pid in (canonical, alias):
        offer = _offer(client, ids, pid)
        for target in ("ACTIVE",):
            r = client.post(f"/offers/{offer}/state", headers=_h(ids.ACC_OPERATOR),
                            json={"status": target})
            assert r.status_code == 200, r.text
        consent = _one(engine, """INSERT INTO turab.consent_grants
                                        (party_id, scope, channel, consent_version, granted_at)
                                  VALUES (:p, 'PUBLIC_LISTING_ALLOWED', 'PHONE_CONFIRMED',
                                          'consent-v1', now() - interval '1 day')
                                  RETURNING consent_id""", p=ids.BRAHIM)
        _run(engine, """INSERT INTO turab.resource_consent_bindings (consent_id, purpose,
                               offer_id, bound_at)
                        VALUES (:c, 'PUBLIC_LISTING_ALLOWED', :o, now() - interval '1 hour')""",
             c=consent, o=offer)
        listed[pid] = offer

    def public():
        r = client.get("/public/properties", params={"location_id": str(loc)})
        assert r.status_code == 200, r.text
        return {i["property_id"]: [o["offer_id"] for o in i["offers"]] for i in r.json()}

    assert public() == {canonical: [listed[canonical]], alias: [listed[alias]]}
    cid = _generate(client, ids, canonical)[0]["identity_candidate_id"]
    assert _review(client, ids, cid, decision="CONFIRMED_SAME",
                   canonical_property_id=canonical).status_code == 200
    assert public() == {canonical: [listed[canonical]]}


def test_an_alias_made_through_the_api_refuses_writes(client, ids, engine):
    """F-2 (step 1), now reachable through the API: a write to an alias is a
    409 naming its canonical record."""
    canonical, alias, _ = _same(client, ids, engine)
    r = client.patch(f"/properties/{alias}",
                     headers={**_h(ids.ACC_OPERATOR), "If-Match-Version": "1"},
                     json={"local_location_detail": "x"})
    assert r.status_code == 409 and r.json()["code"] == "IDENTITY_ALIAS_NOT_CANONICAL", r.text


# --- the pair race (plan §6.3, third row) ----------------------------------------

@pytest.fixture
def two_engines(database_url):
    a = create_engine(database_url, future=True)
    b = create_engine(database_url, future=True)
    yield a, b
    a.dispose()
    b.dispose()


def _race(engine, two_engines, holder_work, contender_work):
    """Run `holder_work(session)` and `contender_work(session)` in two
    transactions. The holder stops before its commit. The witness releases it
    once PostgreSQL reports the contender blocked BY the holder
    (`pg_blocking_pids`), or once the contender has finished. The holder's
    commit never waits for the contender to finish (the step-4 lesson). Each
    outcome is recorded: the value returned, or the exception raised."""
    from turab.db.session import audited_transaction

    engine_a, engine_b = two_engines
    out: dict[str, object] = {}
    pids: dict[str, int] = {}
    ready, finished, release = threading.Event(), threading.Event(), threading.Event()

    def run_in(eng, tag, work, account, before_commit=None):
        with Session(bind=eng, future=True) as s:
            with audited_transaction(s, account):
                pids[tag] = s.execute(text("SELECT pg_backend_pid()")).scalar_one()
                result = work(s)
                if before_commit:
                    before_commit()
        return result

    def holder():
        try:
            out["holder"] = run_in(engine_a, "holder", holder_work[0], holder_work[1],
                                   lambda: (ready.set(), release.wait(30)))
        except Exception as exc:
            out["holder"] = exc
        finally:
            ready.set()

    def contender():
        assert ready.wait(30)
        try:
            out["contender"] = run_in(engine_b, "contender", contender_work[0],
                                      contender_work[1])
        except Exception as exc:
            out["contender"] = exc
        finally:
            finished.set()

    def witness():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not finished.is_set():
            if "contender" in pids and "holder" in pids:
                with Session(bind=engine, future=True) as s:
                    blockers = s.execute(text("SELECT pg_blocking_pids(:p)"),
                                         {"p": pids["contender"]}).scalar_one()
                if pids["holder"] in blockers:
                    out["waited"] = True
                    break
            time.sleep(0.005)
        out.setdefault("waited", False)
        release.set()

    threads = [threading.Thread(target=f) for f in (holder, contender, witness)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not any(t.is_alive() for t in threads)
    return out


def _said(out):
    return "; ".join(f"{k}={v!r}" for k, v in out.items())


def test_two_concurrent_reviews_of_one_candidate_leave_one_final_decision(
        client, ids, engine, two_engines):
    """Serialised on the CANDIDATE row (`FOR UPDATE`). The second reviewer
    waits, then reads the committed final decision and is refused by the
    declared rule "a final decision is not reviewed again": a genuine winner
    and loser, backed by that rule (plan §6.3)."""
    from turab.services import identity

    _, a, _ = _pair(client, ids, engine=engine)
    cid = uuid.UUID(_generate(client, ids, a)[0]["identity_candidate_id"])
    same = (lambda s: identity.review(
        s, candidate_id=cid, decision="CONFIRMED_SAME", canonical_property_id=uuid.UUID(a),
        reason_code=None, reason_text=None, reviewer_account_id=ids.ACC_REVIEWER),
        ids.ACC_REVIEWER)
    distinct = (lambda s: identity.review(
        s, candidate_id=cid, decision="CONFIRMED_DISTINCT", canonical_property_id=None,
        reason_code=None, reason_text=None, reviewer_account_id=ids.ACC_ADMIN),
        ids.ACC_ADMIN)
    out = _race(engine, two_engines, same, distinct)
    assert out["waited"] is True, f"the candidate lock did not serialise them: {_said(out)}"
    assert not isinstance(out["holder"], Exception), _said(out)
    assert isinstance(out["contender"], identity.AlreadyDecided), _said(out)
    assert _one(engine, "SELECT review_status::text FROM turab.property_identity_candidates "
                        "WHERE identity_candidate_id = :c", c=cid) == "CONFIRMED_SAME"


def test_two_concurrent_reviews_cannot_build_an_alias_chain(client, ids, engine,
                                                           two_engines):
    """Candidates A–B and B–C, reviewed concurrently: B canonical for A, and B
    an alias of C. Each is valid alone; together they are a chain, which
    ADR-03 forbids. Without the property row locks, each review's checks (and
    the trigger's) run against the other's UNCOMMITTED alias and both pass.
    With them, the second waits on B, then sees B already canonical, and is
    refused with a typed 409."""
    from turab.services import identity

    loc = _location(engine)
    a, b, c = (_property(client, ids, loc) for _ in range(3))
    ab = uuid.UUID(_pending(engine, a, b))
    bc = uuid.UUID(_pending(engine, b, c))
    first = (lambda s: identity.review(
        s, candidate_id=ab, decision="CONFIRMED_SAME", canonical_property_id=uuid.UUID(b),
        reason_code=None, reason_text=None, reviewer_account_id=ids.ACC_REVIEWER),
        ids.ACC_REVIEWER)
    second = (lambda s: identity.review(
        s, candidate_id=bc, decision="CONFIRMED_SAME", canonical_property_id=uuid.UUID(c),
        reason_code=None, reason_text=None, reviewer_account_id=ids.ACC_ADMIN),
        ids.ACC_ADMIN)
    out = _race(engine, two_engines, first, second)
    assert out["waited"] is True, f"no property lock serialised them: {_said(out)}"
    assert not isinstance(out["holder"], Exception), _said(out)
    assert isinstance(out["contender"], identity.NotCanonical), _said(out)
    chains = _all(engine, """SELECT count(*) AS n FROM turab.property_identity_aliases x
                               JOIN turab.property_identity_aliases y
                                 ON y.canonical_property_id = x.alias_property_id""")
    assert chains == [{"n": 0}]


def test_generating_the_same_pair_twice_concurrently_yields_one_candidate(
        client, ids, engine, two_engines):
    """Nothing serialises generation (no parent row). `ux_identity_pair`
    admits one row; the other INSERT waits on it, fails inside its
    SAVEPOINT, and reads the winner's row. Both calls succeed, with the same
    candidate.

    The witness (the step-4 lesson): the holder commits once PostgreSQL
    reports the contender blocked BY it, or once the contender has finished.
    It never waits for the contender to finish."""
    from turab.db.session import audited_transaction
    from turab.services import identity

    _, a, _ = _pair(client, ids, engine=engine)
    engine_a, engine_b = two_engines
    out: dict[str, object] = {}
    pids: dict[str, int] = {}
    ready, finished, release = threading.Event(), threading.Event(), threading.Event()

    def generate_in(eng, tag, before_commit=None):
        with Session(bind=eng, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                pids[tag] = s.execute(text("SELECT pg_backend_pid()")).scalar_one()
                rows = identity.generate(s, property_id=uuid.UUID(a), algorithm_version=None)
                if before_commit:
                    before_commit()
        return [str(r["identity_candidate_id"]) for r in rows]

    def holder():
        try:
            out["holder"] = generate_in(engine_a, "holder",
                                        lambda: (ready.set(), release.wait(30)))
        except Exception as exc:
            out["holder"] = f"raised {type(exc).__name__}: {exc}"
        finally:
            ready.set()

    def contender():
        assert ready.wait(30)
        try:
            out["contender"] = generate_in(engine_b, "contender")
        except Exception as exc:
            out["contender"] = f"raised {type(exc).__name__}: {exc}"
        finally:
            finished.set()

    def witness():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not finished.is_set():
            if "contender" in pids and "holder" in pids:
                with Session(bind=engine, future=True) as s:
                    blockers = s.execute(text("SELECT pg_blocking_pids(:p)"),
                                         {"p": pids["contender"]}).scalar_one()
                if pids["holder"] in blockers:
                    out["waited"] = True
                    break
            time.sleep(0.005)
        out.setdefault("waited", False)
        release.set()

    threads = [threading.Thread(target=f) for f in (holder, contender, witness)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not any(t.is_alive() for t in threads)
    facts = f"waited={out['waited']} holder={out['holder']} contender={out['contender']}"
    assert out["waited"] is True, f"the contender never waited on the pair: {facts}"
    assert not str(out["holder"]).startswith("raised"), facts
    assert not str(out["contender"]).startswith("raised"), facts
    assert out["holder"] == out["contender"] and len(out["holder"]) == 1, facts
    assert _one(engine, """SELECT count(*) FROM turab.property_identity_candidates
                            WHERE :a IN (property_a_id, property_b_id)""", a=a) == 1
