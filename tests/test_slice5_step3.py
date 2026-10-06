"""Slice 5 step 3: APPROVED, the currency check, and the one opportunity.

Ref: `docs/gate/SLICE_5_PLAN.md`: §2, §3.2, §3.3, §3.4, §3.7; G5-2 (a);
G5-3 (decided (a), review of 29a0f30); G5-5 (decided (a), review of 60b0152);
§6.1 mandatory tests 1, 2, 3, 4 and 6; `services/match_review.py`,
`services/currency.py`.

**Step 3's boundary (review of 60b0152).** APPROVED, the check of the facts
now, and the creation of ONE opportunity with its uniqueness and concurrency
guards. Not here: share, close, revalidate and the customer view (steps 4
and 5). Where a test needs a closed opportunity, the close is a SQL fixture,
labelled so; the customer-body tests of G5-5 and mandatory test 5 are step
4's. What is tested here is the STORED content those views will read.

**Isolation.** HTTP tests commit to the shared test database. Each builds its
own request, properties, offers and consents; every match is a real output of
the Slice 4 run.
"""
from __future__ import annotations

import itertools
import json
import threading
import time
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.test_slice4_step7 import (_all, _criterion, _exec, _offer, _one, _property,
                                     _request, _run)
from tests.test_slice5_step2 import _footprint, _review, _reviews
from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.matching import criteria, rules
from turab.matching.registry import REGISTRY
from turab.services import currency, match_review

CONTRACT = yaml.safe_load(open("docs/handoff/05_API/openapi_v0.2.3.yaml"))
SCHEMAS = CONTRACT["components"]["schemas"]
APPROVE = {"decision": "APPROVED"}


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# --- the world ------------------------------------------------------------------------

def _world(client, engine, ids, *, offers=1, request_status="ACTIVE", desired_type=None,
           area_criteria=(), consent=True, **offer_kw):
    """One request (REQUIRED DOCUMENT_TYPE LAND_BOOK, max 30M), one fresh LAND
    property of 400 m² holding LAND_BOOK, `offers` fresh ACTIVE SALE offers
    with a current binding, and ONE run. Returns (request, property, offers,
    matches by offer)."""
    req = _request(engine, ids, status=request_status, desired_type=desired_type)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    for order, (code, importance, minimum) in enumerate(area_criteria, start=1):
        _criterion(engine, req, code, "GTE", minimum, importance, sort_order=order)
    prop = _property(engine)
    made = [_offer(engine, ids, prop, consent=consent, **offer_kw) for _ in range(offers)]
    r = _run(client, ids, req, [prop])
    assert r.status_code == 201, r.text
    by_offer = {m["evaluated_offer_id"]: m for m in r.json()["matches"]}
    return req, prop, made, [by_offer[str(o)] for o in made]


def _approve(client, match_id, account, key=None):
    return _review(client, match_id, APPROVE, account, key)


def _refused(client, engine, match_id, account, status, code):
    """The refusal, and nothing written: no review, no task, no opportunity,
    no audit row, no key consumed."""
    key = str(uuid.uuid4())
    before = _footprint(engine, match_id, key)
    before["all_opportunities"] = _one(engine, "SELECT count(*) FROM turab.opportunities")
    r = _approve(client, match_id, account, key)
    assert (r.status_code, r.json().get("code")) == (status, code), r.text
    after = _footprint(engine, match_id, key)
    after["all_opportunities"] = _one(engine, "SELECT count(*) FROM turab.opportunities")
    assert after == before, "a refusal writes nothing and consumes no key"
    return r.json()


def _opportunity(engine, match_id):
    rows = _all(engine, """
        SELECT o.*, o.status::text AS status_text, o.sharing_scope::text AS scope,
               o.why_real::text AS why_real_text, o.known_differences::text AS kd_text,
               o.permission_snapshot::text AS permission_text,
               o.commercial_context_snapshot = m.commercial_context_snapshot AS same_context,
               m.evaluated_offer_id
          FROM turab.opportunities o
          JOIN turab.match_candidates m ON m.match_id = o.approved_match_id
         WHERE o.approved_match_id = :m""", m=match_id)
    assert len(rows) <= 1
    return rows[0] if rows else None


def _make_alias(engine, ids, alias, canonical):
    """`alias` becomes an identity alias of `canonical` (SQL fixture: the
    identity review is Slice 3's, and its own tests cover it)."""
    cid = _one(engine, """INSERT INTO turab.property_identity_candidates
                                 (property_a_id, property_b_id)
                          VALUES (:a, :b) RETURNING identity_candidate_id""",
               a=min(alias, canonical), b=max(alias, canonical))
    _exec(engine, """INSERT INTO turab.property_identity_aliases
                            (alias_property_id, canonical_property_id,
                             source_identity_candidate_id, resolved_by_account_id)
                     VALUES (:a, :c, :cid, :acct)""",
          a=alias, c=canonical, cid=cid, acct=ids.ACC_REVIEWER)


def _close(engine, opportunity_id):
    """SQL fixture: the close operation is step 5. NEW -> CLOSED, with its
    reason and time, as migration 0006 admits."""
    _exec(engine, """UPDATE turab.opportunities
                        SET status = 'CLOSED', closed_at = now(),
                            close_reason_code = 'BUYER_REJECTED'
                      WHERE opportunity_id = :o""", o=opportunity_id)


# ======================================================================================
# §3.7: the table, exhaustively, without PostgreSQL
# ======================================================================================

V, N, I = "VALID", "NEEDS_CONFIRMATION", "INVALID"
#: §3.7's table, written out here and not read from the module under test.
PLAN_TABLE = {
    "REQUEST_STATUS": {"ACTIVE": V, "NEEDS_CONFIRMATION": N, "PAUSED": N, "CLOSED": I,
                       "RAW": I, "CONTACTED": I, "QUALIFIED": I},
    "OFFER_STATUS": {"ACTIVE": V, "PENDING_INFO": N, "PAUSED": N, "WITHDRAWN": I,
                     "CLOSED": I, "DRAFT": I},
    "AVAILABILITY": {"AVAILABLE": V, "POTENTIALLY_AVAILABLE": V, "UNDER_DISCUSSION": N,
                     "TEMPORARILY_UNAVAILABLE": N, "NEEDS_CONFIRMATION": N, "UNKNOWN": N,
                     "UNAVAILABLE": I},
    "IDENTITY": {"CANONICAL": V, "ALIAS": I},
    "REQUEST_FRESHNESS": {"FRESH": V, "STALE": N, "UNKNOWN": N},
    "PROPERTY_FRESHNESS": {"FRESH": V, "STALE": N, "UNKNOWN": N},
    "OFFER_FRESHNESS": {"FRESH": V, "STALE": N, "UNKNOWN": N},
    "PERMISSION": {"PASS": V, "UNKNOWN": N, "FAIL": I},
}
FACTS = list(PLAN_TABLE)


def test_the_check_is_section_3_7s_table():
    assert {f: dict(c) for f, c in currency.TABLE.items()} == PLAN_TABLE
    assert list(currency.TABLE) == FACTS, "the reasons are listed in the table's order"


def test_every_combination_is_the_worst_fact_and_names_every_failing_fact():
    """7 × 6 × 7 × 2 × 3 × 3 × 3 × 3 = 47 628 combinations."""
    rank = {V: 0, N: 1, I: 2}
    count = 0
    for values in itertools.product(*(PLAN_TABLE[f] for f in FACTS)):
        facts = dict(zip(FACTS, values))
        classes = [PLAN_TABLE[f][facts[f]] for f in FACTS]
        got = currency.classify(facts)
        assert got.validity == max(classes, key=rank.__getitem__), facts
        assert [(r["fact"], r["value"], r["class"]) for r in got.reasons] == [
            (f, facts[f], c) for f, c in zip(FACTS, classes) if c != V], facts
        count += 1
    assert count == 47_628


def test_the_table_names_every_value_of_the_schemas_enums(engine):
    for fact, enum in (("REQUEST_STATUS", "request_status"), ("OFFER_STATUS", "offer_status"),
                       ("AVAILABILITY", "availability_status")):
        values = set(_one(engine, f"SELECT enum_range(NULL::turab.{enum})::text[]"))
        assert set(currency.TABLE[fact]) == values, fact


def test_a_value_outside_the_table_fails_closed():
    facts = {f: next(iter(PLAN_TABLE[f])) for f in FACTS}
    facts["REQUEST_STATUS"] = "A_FUTURE_STATE"
    got = currency.classify(facts)
    assert got.validity == I and got.reasons[0]["class"] == I
    with pytest.raises(ValueError):
        currency.classify({f: v for f, v in facts.items() if f != "PERMISSION"})


def test_each_reason_code_is_seeded_and_names_its_fact(engine):
    seeded = {r["code"]: r["category"] for r in _all(
        engine, "SELECT code, category FROM turab.reason_codes WHERE active")}
    assert dict(currency.REASON_CODES) == {
        ("REQUEST_FRESHNESS", "STALE"): "REQUEST_STALE",
        ("PROPERTY_FRESHNESS", "STALE"): "PROPERTY_STALE",
        ("OFFER_FRESHNESS", "STALE"): "OFFER_STALE",
        ("AVAILABILITY", "UNAVAILABLE"): "PROPERTY_UNAVAILABLE",
        ("PERMISSION", "FAIL"): "CONSENT_REVOKED",
        ("PERMISSION", "UNKNOWN"): "PERMISSION_MISSING"}
    assert all(code in seeded for code in currency.REASON_CODES.values())


# ======================================================================================
# APPROVED creates the one opportunity (G5-5 (a); mandatory test 4)
# ======================================================================================

def test_approved_creates_one_opportunity_with_the_decided_content(client, engine, ids):
    req, prop, [offer], [m] = _world(client, engine, ids)
    assert m["eligibility"] == "ELIGIBLE"
    r = _approve(client, m["match_id"], ids.ACC_REVIEWER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert (body["match_id"], body["decision"], body["task"]) == (m["match_id"], "APPROVED",
                                                                   None)
    view = body["opportunity"]
    assert set(view) == set(SCHEMAS["InternalOpportunityView"]["properties"])
    assert set(SCHEMAS["InternalOpportunityView"]["required"]) <= set(view)

    o = _opportunity(engine, m["match_id"])
    assert view["opportunity_id"] == str(o["opportunity_id"])
    assert (o["status_text"], o["validity_status"], o["scope"]) == ("NEW", "VALID",
                                                                     "SUMMARY_ONLY")
    assert (o["request_id"], o["property_id"]) == (req, prop)
    # Mandatory test 4: the initial context is the evaluated one.
    assert o["current_offer_id"] == o["evaluated_offer_id"] == offer
    assert o["same_context"] is True
    assert view["commercial_context_snapshot"] == m["commercial_context_snapshot"]
    # The permission snapshot of the approval records the scope; the binding is
    # the offer's current one.
    permission = json.loads(o["permission_text"])
    assert permission["permission_scope"] == "SUMMARY_ONLY"
    assert permission["derived_by"] == "permission.binding_state@1"
    [binding] = permission["bindings"]
    assert binding["state"] == "CURRENT"
    assert str(o["current_permission_binding_id"]) == binding["consent_binding_id"]
    assert o["created_by_account_id"] == ids.ACC_REVIEWER
    assert o["last_confirmed_at"] is not None and o["shared_at"] is None
    [review] = _reviews(engine, m["match_id"])
    assert review["decision"] == "APPROVED"
    assert o["last_confirmed_at"] <= review["reviewed_at"]


def test_the_creation_is_audited_with_the_reviewer_as_actor(client, engine, ids):
    *_, [m] = _world(client, engine, ids)
    assert _approve(client, m["match_id"], ids.ACC_ADMIN).status_code == 200
    o = _opportunity(engine, m["match_id"])
    [review] = _reviews(engine, m["match_id"])
    audited = _all(engine, """
        SELECT entity_table, action, actor_account_id FROM turab.audit_log
         WHERE (entity_table = 'opportunities' AND entity_id = :o)
            OR (entity_table = 'match_reviews' AND entity_id = :r)
         ORDER BY entity_table""", o=o["opportunity_id"], r=review["match_review_id"])
    assert [(a["entity_table"], a["action"], a["actor_account_id"]) for a in audited] == [
        ("match_reviews", "INSERT", ids.ACC_ADMIN), ("opportunities", "INSERT", ids.ACC_ADMIN)]


def test_the_scope_is_the_offers_permission_scope_at_approval(client, engine, ids):
    """G5-5 (a): read at approval, not at the run, and recorded with the
    permission snapshot."""
    *_, [offer], [m] = _world(client, engine, ids)
    _exec(engine, """UPDATE turab.property_offers
                        SET permission_scope = 'PROPERTY_DETAILS_ALLOWED' WHERE offer_id = :o""",
          o=offer)
    assert _approve(client, m["match_id"], ids.ACC_REVIEWER).status_code == 200
    o = _opportunity(engine, m["match_id"])
    assert o["scope"] == "PROPERTY_DETAILS_ALLOWED"
    assert json.loads(o["permission_text"])["permission_scope"] == "PROPERTY_DETAILS_ALLOWED"
    assert m["commercial_context_snapshot"]["permission_scope"] == "SUMMARY_ONLY"


def test_a_replay_returns_the_same_opportunity_and_creates_no_second(client, engine, ids):
    *_, [m] = _world(client, engine, ids)
    key = str(uuid.uuid4())
    first = _approve(client, m["match_id"], ids.ACC_REVIEWER, key)
    again = _approve(client, m["match_id"], ids.ACC_REVIEWER, key)
    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json() == first.json()
    assert _one(engine, "SELECT count(*) FROM turab.opportunities WHERE approved_match_id = :m",
                m=m["match_id"]) == 1


def test_an_approved_match_is_final(client, engine, ids):
    *_, [m] = _world(client, engine, ids)
    assert _approve(client, m["match_id"], ids.ACC_REVIEWER).status_code == 200
    _refused(client, engine, m["match_id"], ids.ACC_ADMIN, 409, "MATCH_REVIEW_DECIDED")


def test_mandatory_1_nmi_then_approved_keeps_both_decisions(client, engine, ids):
    """H01 on one ELIGIBLE match (§3.2): two rows, in order, one opportunity."""
    *_, [m] = _world(client, engine, ids)
    assert _review(client, m["match_id"], {"decision": "NEED_MORE_INFORMATION",
                                           "reason_code": "REQUEST_STALE"},
                   ids.ACC_REVIEWER).status_code == 200
    assert _approve(client, m["match_id"], ids.ACC_ADMIN).status_code == 200
    assert [r["decision"] for r in _reviews(engine, m["match_id"])] == [
        "APPROVED", "NEED_MORE_INFORMATION"]
    assert _opportunity(engine, m["match_id"]) is not None


def test_mandatory_1_across_matches_of_one_pair(client, engine, ids):
    """§3.2, the cross-match case: NMI on M1, APPROVED on M2 of the same pair
    (two offers), both reviews kept, one opportunity, on M2."""
    req, prop, _, [m1, m2] = _world(client, engine, ids, offers=2)
    assert _review(client, m1["match_id"], {"decision": "NEED_MORE_INFORMATION",
                                            "reason_code": "OFFER_STALE"},
                   ids.ACC_REVIEWER).status_code == 200
    assert _approve(client, m2["match_id"], ids.ACC_REVIEWER).status_code == 200
    assert [r["decision"] for r in _reviews(engine, m1["match_id"])] == [
        "NEED_MORE_INFORMATION"]
    assert [r["decision"] for r in _reviews(engine, m2["match_id"])] == ["APPROVED"]
    assert [o["approved_match_id"] for o in _all(
        engine, "SELECT approved_match_id FROM turab.opportunities WHERE request_id = :r",
        r=req)] == [uuid.UUID(m2["match_id"])]


def test_mandatory_4_the_schema_refuses_another_initial_offer(client, engine, ids):
    """Labelled SCHEMA: with the service bypassed, the frozen
    `trg_opportunity_gate` refuses an initial offer other than the evaluated
    one. The service never writes one (the test above)."""
    req, prop, [o1, o2], [m1, _] = _world(client, engine, ids, offers=2)
    _exec(engine, """INSERT INTO turab.match_reviews (match_id, decision, reviewer_account_id)
                     VALUES (:m, 'APPROVED', :a)""", m=m1["match_id"], a=ids.ACC_REVIEWER)
    with pytest.raises(Exception, match="current_offer_id must initially match"):
        _exec(engine, """
            INSERT INTO turab.opportunities (request_id, property_id, approved_match_id,
                                             current_offer_id, sharing_scope, why_real,
                                             created_by_account_id)
            VALUES (:r, :p, :m, :o, 'SUMMARY_ONLY', '{}'::jsonb, :a)""",
              r=req, p=prop, m=m1["match_id"], o=o2, a=ids.ACC_REVIEWER)


# ======================================================================================
# Mandatory test 2: approval fails when a gate is not PASS
# ======================================================================================

def _non_eligible(client, engine, ids, kind):
    req = _request(engine, ids, confirmed=kind != "FRESHNESS")
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    prop = _property(engine, document={"HARD": "ADMINISTRATIVE_DEED",
                                       "INFORMATION": None}.get(kind, "LAND_BOOK"))
    _offer(engine, ids, prop, consent=kind != "PERMISSION")
    r = _run(client, ids, req, [prop])
    assert r.status_code == 201, r.text
    [m] = r.json()["matches"]
    return m


@pytest.mark.parametrize("kind,eligibility,gate", [
    ("HARD", "REJECTED", "HARD_GATE"),
    ("INFORMATION", "NEED_MORE_INFORMATION", "INFORMATION_GATE"),
    ("FRESHNESS", "NEEDS_CONFIRMATION", "FRESHNESS_GATE"),
    ("PERMISSION", "NEEDS_CONFIRMATION", "PERMISSION_GATE"),
])
def test_mandatory_2_a_gate_not_pass_is_refused_before_any_write(client, engine, ids, kind,
                                                                  eligibility, gate):
    """Over HTTP, one case per gate and per non-ELIGIBLE eligibility: 409
    MATCH_GATES_NOT_PASS, named before the frozen trigger fires, with the
    failing gates; no review, no opportunity, no key consumed."""
    m = _non_eligible(client, engine, ids, kind)
    assert m["eligibility"] == eligibility
    body = _refused(client, engine, m["match_id"], ids.ACC_REVIEWER, 409,
                    "MATCH_GATES_NOT_PASS")
    named = {e["field"] for e in body["field_errors"]}
    assert {"ELIGIBILITY", gate} <= named


def test_mandatory_2_the_schema_refuses_the_same_when_the_service_check_is_bypassed(
        client, engine, ids):
    """Labelled SCHEMA: an APPROVED review written by SQL on a non-ELIGIBLE
    match is refused by the frozen `trg_match_review_gate`."""
    m = _non_eligible(client, engine, ids, "INFORMATION")
    with pytest.raises(Exception, match="before all opportunity gates pass"):
        _exec(engine, """INSERT INTO turab.match_reviews (match_id, decision,
                                                          reviewer_account_id)
                         VALUES (:m, 'APPROVED', :a)""", m=m["match_id"], a=ids.ACC_REVIEWER)


# ======================================================================================
# Mandatory test 3: no generic creation
# ======================================================================================

def test_mandatory_3_there_is_no_generic_opportunity_creation(client, ids):
    r = client.post("/opportunities", json={}, headers={
        "Authorization": f"Bearer {ids.ACC_ADMIN}", "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code in (404, 405), r.text
    assert "/opportunities" not in CONTRACT["paths"] or "post" not in CONTRACT["paths"][
        "/opportunities"]


# ======================================================================================
# G5-2 (a): supersession per offer
# ======================================================================================

def test_a_new_evaluation_supersedes_its_own_offers_match_only(client, engine, ids):
    req, prop, [o1, o2], [m1, m2] = _world(client, engine, ids, offers=2)
    _exec(engine, """UPDATE turab.property_offers SET asking_price_dzd = 21000000,
                            version = version + 1 WHERE offer_id = :o""", o=o1)
    r = _run(client, ids, req, [prop])
    assert r.status_code == 201, r.text
    after = {m["evaluated_offer_id"]: m["match_id"] for m in r.json()["matches"]}
    assert after[str(o1)] != m1["match_id"], "a changed input is a new match (G4-13)"
    assert after[str(o2)] == m2["match_id"], "an unchanged input is the same match"
    # The other offer's match is still current, though it is older than the
    # new evaluation of offer 1: supersession is per offer.
    assert _approve(client, m2["match_id"], ids.ACC_REVIEWER).status_code == 200
    # Offer 1's old match is superseded, checked before the open opportunity.
    body = _refused(client, engine, m1["match_id"], ids.ACC_REVIEWER, 409, "MATCH_SUPERSEDED")
    assert after[str(o1)] in body["detail"]
    _refused(client, engine, after[str(o1)], ids.ACC_REVIEWER, 409, "OPPORTUNITY_ALREADY_OPEN")


def test_two_offers_of_one_run_are_both_current(client, engine, ids):
    """Measurement H: one run, two offers, equal times. Neither supersedes the
    other; the first approval creates the opportunity."""
    *_, [m1, m2] = _world(client, engine, ids, offers=2)
    assert m1["evaluated_at"] == m2["evaluated_at"]
    assert _approve(client, m2["match_id"], ids.ACC_REVIEWER).status_code == 200


# ======================================================================================
# §3.7 over HTTP: the facts now
# ======================================================================================

def _stale(engine, table, column, key, value):
    _exec(engine, f"UPDATE turab.{table} SET {column} = now() - interval '400 days' "
                  f"WHERE {key} = :v", v=value)


@pytest.mark.parametrize("change,fact,code,validity", [
    ("request_paused", "REQUEST_STATUS", "PAUSED", "NEEDS_CONFIRMATION"),
    ("request_closed", "REQUEST_STATUS", "CLOSED", "INVALID"),
    ("offer_paused", "OFFER_STATUS", "PAUSED", "NEEDS_CONFIRMATION"),
    ("offer_withdrawn", "OFFER_STATUS", "WITHDRAWN", "INVALID"),
    ("unavailable", "AVAILABILITY", "PROPERTY_UNAVAILABLE", "INVALID"),
    ("under_discussion", "AVAILABILITY", "UNDER_DISCUSSION", "NEEDS_CONFIRMATION"),
    ("request_stale", "REQUEST_FRESHNESS", "REQUEST_STALE", "NEEDS_CONFIRMATION"),
    ("property_stale", "PROPERTY_FRESHNESS", "PROPERTY_STALE", "NEEDS_CONFIRMATION"),
    ("offer_stale", "OFFER_FRESHNESS", "OFFER_STALE", "NEEDS_CONFIRMATION"),
    ("consent_revoked", "PERMISSION", "CONSENT_REVOKED", "INVALID"),
])
def test_a_fact_that_changed_after_the_run_refuses_the_approval(client, engine, ids, change,
                                                                fact, code, validity):
    """G5-2 (a), [R3-2]: a match ELIGIBLE at its run, a fact changed since: 409
    MATCH_CONTEXT_NOT_VALID, naming the fact; nothing written."""
    req, prop, [offer], [m] = _world(client, engine, ids)
    assert m["eligibility"] == "ELIGIBLE"
    sql = {
        "request_paused": ("UPDATE turab.requests SET status = 'PAUSED' WHERE request_id = :v",
                           req),
        "request_closed": ("UPDATE turab.requests SET status = 'CLOSED' WHERE request_id = :v",
                           req),
        "offer_paused": ("UPDATE turab.property_offers SET status = 'PAUSED' "
                         "WHERE offer_id = :v", offer),
        "offer_withdrawn": ("UPDATE turab.property_offers SET status = 'WITHDRAWN' "
                            "WHERE offer_id = :v", offer),
        "unavailable": ("UPDATE turab.properties SET current_availability = 'UNAVAILABLE' "
                        "WHERE property_id = :v", prop),
        "under_discussion": ("UPDATE turab.properties SET current_availability = "
                             "'UNDER_DISCUSSION' WHERE property_id = :v", prop),
        "consent_revoked": ("UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                            "WHERE offer_id = :v", offer),
    }.get(change)
    if sql is not None:
        _exec(engine, sql[0], v=sql[1])
    else:
        table, column, key, value = {
            "request_stale": ("requests", "last_confirmed_at", "request_id", req),
            "property_stale": ("properties", "availability_last_confirmed_at", "property_id",
                               prop),
            "offer_stale": ("property_offers", "commercial_terms_last_confirmed_at",
                            "offer_id", offer)}[change]
        _stale(engine, table, column, key, value)
    body = _refused(client, engine, m["match_id"], ids.ACC_REVIEWER, 409,
                    "MATCH_CONTEXT_NOT_VALID")
    assert validity in body["detail"]
    assert [(e["field"], e["code"]) for e in body["field_errors"]] == [(fact, code)]
    for entry in body["field_errors"]:
        assert set(entry) == {"field", "code", "message"}
        assert all(isinstance(v, str) for v in entry.values())


def test_every_failing_fact_is_named_and_the_worst_decides(client, engine, ids):
    req, prop, [offer], [m] = _world(client, engine, ids)
    _exec(engine, "UPDATE turab.requests SET status = 'PAUSED' WHERE request_id = :r", r=req)
    _exec(engine, "UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                  "WHERE offer_id = :o", o=offer)
    _stale(engine, "property_offers", "commercial_terms_last_confirmed_at", "offer_id", offer)
    body = _refused(client, engine, m["match_id"], ids.ACC_REVIEWER, 409,
                    "MATCH_CONTEXT_NOT_VALID")
    assert "INVALID" in body["detail"]
    assert [e["field"] for e in body["field_errors"]] == [
        "REQUEST_STATUS", "OFFER_FRESHNESS", "PERMISSION"]


def test_a_needs_confirmation_request_is_matched_eligible_but_not_approved(client, engine,
                                                                           ids):
    """§3.7: approval is stricter than a run. A NEEDS_CONFIRMATION request is
    evaluated (G4-8) and its match may be ELIGIBLE; approving it is 409."""
    *_, [m] = _world(client, engine, ids, request_status="NEEDS_CONFIRMATION")
    assert m["eligibility"] == "ELIGIBLE"
    body = _refused(client, engine, m["match_id"], ids.ACC_REVIEWER, 409,
                    "MATCH_CONTEXT_NOT_VALID")
    assert [(e["field"], e["code"]) for e in body["field_errors"]] == [
        ("REQUEST_STATUS", "NEEDS_CONFIRMATION")]


def test_the_approval_is_accepted_exactly_when_the_check_is_valid(client, engine, ids,
                                                                  monkeypatch):
    """The approval's one source of currency is `currency.check`: with every
    fact unchanged, forcing the check's answer decides the approval alone."""
    *_, [m] = _world(client, engine, ids)
    real = currency.check

    def forced(validity):
        def check(session, **kw):
            got = real(session, **kw)
            reasons = () if validity == "VALID" else (
                {"fact": "IDENTITY", "value": "ALIAS", "class": validity, "reason_code": None},)
            return currency.Checked(currency.Currency(validity, reasons), got.facts,
                                    got.sharing_scope, got.permission_snapshot,
                                    got.current_permission_binding_id, got.as_of)
        return check
    for validity in ("INVALID", "NEEDS_CONFIRMATION"):
        monkeypatch.setattr(currency, "check", forced(validity))
        _refused(client, engine, m["match_id"], ids.ACC_REVIEWER, 409,
                 "MATCH_CONTEXT_NOT_VALID")
    monkeypatch.setattr(currency, "check", forced("VALID"))
    assert _approve(client, m["match_id"], ids.ACC_REVIEWER).status_code == 200


@pytest.mark.parametrize("fact,sql,field,code", [
    ("request", "UPDATE turab.requests SET status = 'PAUSED' WHERE request_id = :v",
     "REQUEST_STATUS", "PAUSED"),
    ("property", "UPDATE turab.properties SET current_availability = 'UNAVAILABLE' "
                 "WHERE property_id = :v", "AVAILABILITY", "PROPERTY_UNAVAILABLE"),
    ("offer", "UPDATE turab.property_offers SET status = 'PAUSED' WHERE offer_id = :v",
     "OFFER_STATUS", "PAUSED"),
    ("binding", "UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                "WHERE offer_id = :v", "PERMISSION", "CONSENT_REVOKED"),
])
def test_a_fact_being_changed_is_waited_for_and_read_after_its_commit(
        client, engine, ids, fact, sql, field, code):
    """The facts the check classes are the facts at commit. A writer holds an
    uncommitted change of one fact; the approval, over HTTP, waits on that
    writer's row (witness: `pg_blocking_pids`), then reads the committed
    change and is refused. Without the lock it would read the old value and
    approve."""
    from turab.app import create_app

    req, prop, [offer], [m] = _world(client, engine, ids)
    value = {"request": req, "property": prop, "offer": offer, "binding": offer}[fact]
    writer = engine.connect()
    try:
        tx = writer.begin()
        writer.execute(text(sql), {"v": value})
        wpid = writer.execute(text("SELECT pg_backend_pid()")).scalar_one()
        out = {}

        def send():
            with TestClient(create_app(engine=engine)) as c:
                out["r"] = _approve(c, m["match_id"], ids.ACC_REVIEWER)

        t = threading.Thread(target=send)
        t.start()
        deadline, waiting = time.monotonic() + 30, []
        while not waiting:
            waiting = _all(engine, """
                SELECT pid FROM pg_stat_activity
                 WHERE pid <> :w AND wait_event_type = 'Lock'
                   AND :w = ANY(pg_blocking_pids(pid))""", w=wpid)
            assert waiting or time.monotonic() < deadline, "the approval never waited"
            time.sleep(0.02)
        tx.commit()
    finally:
        writer.close()
    t.join(30)
    r = out["r"]
    assert (r.status_code, r.json()["code"]) == (409, "MATCH_CONTEXT_NOT_VALID"), r.text
    assert [(e["field"], e["code"]) for e in r.json()["field_errors"]] == [(field, code)]
    assert _opportunity(engine, m["match_id"]) is None


def test_the_binding_recorded_is_offer_bound_before_property_bound(client, engine, ids):
    """G5-5 (a): the current binding, by a fixed order: offer-bound before
    property-bound, then `bound_at`, then the id. The property-bound binding
    here is the OLDER one, so `bound_at` alone would pick it. The frozen
    `enforce_consent_binding` requires an active party-property relation for a
    property-bound binding; the fixture writes one for the schema. No code of
    this slice reads it (acceptance condition 7)."""
    req, prop, [offer], [m] = _world(client, engine, ids)
    _exec(engine, """INSERT INTO turab.party_property_relations (party_id, property_id,
                                                                 relation_code, valid_from)
                     VALUES (:party, :p, 'OWNER_DECLARED', now() - interval '10 days')""",
          party=ids.BRAHIM, p=prop)
    grant = _one(engine, """
        INSERT INTO turab.consent_grants (party_id, scope, channel, consent_version, granted_at)
        VALUES (:party, 'PRIVATE_MATCHING_ONLY', 'PHONE_CONFIRMED', 'v1',
                now() - interval '9 days')
        RETURNING consent_id""", party=ids.BRAHIM)
    on_property = _one(engine, """
        INSERT INTO turab.resource_consent_bindings (consent_id, purpose, property_id, bound_at)
        VALUES (:c, 'PRIVATE_MATCHING_ONLY', :p, now() - interval '8 days')
        RETURNING consent_binding_id""", c=grant, p=prop)
    on_offer = _one(engine, """SELECT consent_binding_id FROM turab.resource_consent_bindings
                                WHERE offer_id = :o""", o=offer)
    assert _approve(client, m["match_id"], ids.ACC_REVIEWER).status_code == 200
    o = _opportunity(engine, m["match_id"])
    states = {b["consent_binding_id"]: b["state"]
              for b in json.loads(o["permission_text"])["bindings"]}
    assert states == {str(on_offer): "CURRENT", str(on_property): "CURRENT"}
    assert o["current_permission_binding_id"] == on_offer


def test_the_check_uses_the_thresholds_and_versions_the_match_recorded(client, engine, ids):
    """The rules are the match's: its recorded freshness thresholds, and the
    pinned versions in its `explanation.engine`."""
    from sqlalchemy.orm import Session

    *_, [m] = _world(client, engine, ids)
    s = Session(bind=engine)
    try:
        match = match_review._lock_match(s, uuid.UUID(m["match_id"]))
        assert match["threshold_days"] == {
            k: int(v) for k, v in m["freshness_snapshot"]["threshold_days"].items()}
        assert match["engine"]["freshness_state"] == "freshness.state@1"
        assert match["engine"]["permission_gate"] == "permission.gate@1"
        # A threshold of 0 days, under the request's age (1 day), makes it STALE.
        short = {**match, "threshold_days": {**match["threshold_days"], "request": 0}}
        got = currency.check(s, match=short, offer_id=uuid.UUID(m["evaluated_offer_id"]))
        assert got.facts["REQUEST_FRESHNESS"] == "STALE"
        # The clock seam: the same facts, judged 400 days on, are STALE too.
        later = s.execute(text("SELECT now() + interval '400 days'")).scalar_one()
        got = currency.check(s, match=match, offer_id=uuid.UUID(m["evaluated_offer_id"]),
                             clock=later)
        assert got.as_of == later
        assert {f: got.facts[f] for f in ("REQUEST_FRESHNESS", "PROPERTY_FRESHNESS",
                                          "OFFER_FRESHNESS")} == {
            "REQUEST_FRESHNESS": "STALE", "PROPERTY_FRESHNESS": "STALE",
            "OFFER_FRESHNESS": "STALE"}
    finally:
        s.rollback()
        s.close()


# ======================================================================================
# Mandatory test 6 and §3.3: one open opportunity per request × canonical property
# ======================================================================================

def test_mandatory_6_a_second_offers_match_is_refused_while_one_is_open(client, engine,
                                                                        ids):
    req, prop, _, [m1, m2] = _world(client, engine, ids, offers=2)
    assert _approve(client, m1["match_id"], ids.ACC_REVIEWER).status_code == 200
    body = _refused(client, engine, m2["match_id"], ids.ACC_REVIEWER, 409,
                    "OPPORTUNITY_ALREADY_OPEN")
    first = _opportunity(engine, m1["match_id"])
    assert str(first["opportunity_id"]) in body["detail"]


def test_mandatory_6_after_close_the_other_match_is_approvable(client, engine, ids):
    req, prop, _, [m1, m2] = _world(client, engine, ids, offers=2)
    assert _approve(client, m1["match_id"], ids.ACC_REVIEWER).status_code == 200
    _close(engine, _opportunity(engine, m1["match_id"])["opportunity_id"])
    assert _approve(client, m2["match_id"], ids.ACC_REVIEWER).status_code == 200
    assert _one(engine, """SELECT count(*) FROM turab.opportunities
                            WHERE request_id = :r AND status <> 'CLOSED'""", r=req) == 1


def test_mandatory_6_an_open_opportunity_on_an_alias_blocks_its_canonical(client, engine,
                                                                          ids):
    """§3.3, layer 2: the index keys on `property_id` and cannot see this
    (E04). An opportunity opened on A while A was canonical; A then becomes an
    alias of C; approving the request's match on C is refused."""
    req = _request(engine, ids)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    a, c = _property(engine), _property(engine)
    _offer(engine, ids, a)
    _offer(engine, ids, c)
    r = _run(client, ids, req, [a, c])
    assert r.status_code == 201, r.text
    by_prop = {m["property_id"]: m for m in r.json()["matches"]}
    assert _approve(client, by_prop[str(a)]["match_id"], ids.ACC_REVIEWER).status_code == 200
    _make_alias(engine, ids, a, c)
    _refused(client, engine, by_prop[str(c)]["match_id"], ids.ACC_REVIEWER, 409,
             "OPPORTUNITY_ALREADY_OPEN")


def test_mandatory_6_a_match_on_a_property_that_is_now_an_alias_is_refused(client, engine,
                                                                           ids):
    """§3.3, layer 1: no opportunity on an alias; the identity fact names it."""
    req, prop, _, [m] = _world(client, engine, ids)
    _make_alias(engine, ids, prop, _property(engine))
    body = _refused(client, engine, m["match_id"], ids.ACC_REVIEWER, 409,
                    "MATCH_CONTEXT_NOT_VALID")
    assert [(e["field"], e["code"]) for e in body["field_errors"]] == [("IDENTITY", "ALIAS")]


def test_mandatory_6_the_index_backstop_maps_to_the_same_refusal(client, engine, ids,
                                                                 monkeypatch):
    """Labelled SCHEMA BACKSTOP: with the service's open-opportunity check
    disabled, `ux_one_open_opportunity_per_pair` refuses the second
    opportunity, and its 23505 maps to the same typed 409, with nothing
    written."""
    *_, [m1, m2] = _world(client, engine, ids, offers=2)
    assert _approve(client, m1["match_id"], ids.ACC_REVIEWER).status_code == 200
    monkeypatch.setattr(match_review, "_open_opportunity", lambda session, match: None)
    _refused(client, engine, m2["match_id"], ids.ACC_REVIEWER, 409, "OPPORTUNITY_ALREADY_OPEN")


def test_mandatory_6_two_concurrent_approvals_of_one_pair_make_one_opportunity(
        client, engine, ids, monkeypatch):
    """Two reviewers approve the two offers' matches of one pair at once, over
    HTTP. A is paused after writing its opportunity, uncommitted. B, on the
    OTHER match, holds its own match lock and waits on the request lock A
    holds (witness: `pg_blocking_pids`, in the request's `FOR NO KEY UPDATE`).
    A commits; B then sees A's opportunity and is refused, typed. One
    opportunity; B wrote nothing."""
    from turab.app import create_app

    req, prop, _, [m1, m2] = _world(client, engine, ids, offers=2)
    written, release = threading.Event(), threading.Event()
    pids = []
    original = match_review._create_opportunity

    def paused(session, prepared, reviewer):
        result = original(session, prepared, reviewer)
        if not pids:
            pids.append(session.execute(text("SELECT pg_backend_pid()")).scalar_one())
            written.set()
            assert release.wait(30)
        return result

    monkeypatch.setattr(match_review, "_create_opportunity", paused)
    out = {}

    def send(name, match_id, account):
        with TestClient(create_app(engine=engine)) as c:
            out[name] = _approve(c, match_id, account)

    a = threading.Thread(target=send, args=("a", m1["match_id"], ids.ACC_REVIEWER))
    a.start()
    assert written.wait(30)
    b = threading.Thread(target=send, args=("b", m2["match_id"], ids.ACC_ADMIN))
    b.start()
    deadline, waiting = time.monotonic() + 30, []
    while not waiting:
        waiting = _all(engine, """
            SELECT pid FROM pg_stat_activity
             WHERE pid <> :a AND wait_event_type = 'Lock'
               AND :a = ANY(pg_blocking_pids(pid))
               AND query LIKE '%FROM turab.requests WHERE request_id = %FOR NO KEY UPDATE%'""",
                       a=pids[0])
        assert waiting or time.monotonic() < deadline, "B never waited on A's request lock"
        time.sleep(0.02)
    assert _one(engine, "SELECT count(*) FROM turab.opportunities WHERE request_id = :r",
                r=req) == 0, "A has committed nothing while B waits"
    release.set()
    a.join(30)
    b.join(30)
    assert out["a"].status_code == 200, out["a"].text
    assert (out["b"].status_code, out["b"].json()["code"]) == (409, "OPPORTUNITY_ALREADY_OPEN")
    assert _one(engine, "SELECT count(*) FROM turab.opportunities WHERE request_id = :r",
                r=req) == 1
    assert _reviews(engine, m2["match_id"]) == []


# ======================================================================================
# G5-5 (a): what the stored why_real and known_differences may contain (§3.4)
# ======================================================================================

def _result(code, importance="REQUIRED", compatibility="PASS", blocking=False, rule=None):
    rule_id, version = rule or criteria.RULES.get(code, criteria.NO_RULE)[:2]
    return {"criterion_code": code, "ordinal": 1, "importance": importance,
            "compatibility": compatibility, "blocking": blocking, "rule_id": rule_id,
            "rule_version": version, "label_ar": f"label {code}"}


ALL_CODES = sorted(set(criteria.RULES) | {"BUDGET_TARGET", "LOCATION"})


@pytest.mark.parametrize("scope", ["SUMMARY_ONLY", "PROPERTY_DETAILS_ALLOWED",
                                   "CONTACT_AFTER_CONFIRMATION"])
def test_only_the_decided_codes_are_ever_shown(scope):
    """The fixed list by code and scope (G5-5 (a)): every code, at every
    importance and compatibility, is shown only if the list names it."""
    allowed = {"SUMMARY_ONLY": {"PROPERTY_TYPE"}}.get(
        scope, {"PROPERTY_TYPE", "LAND_AREA_MIN", "BUILT_AREA_MIN"})
    results = [_result(code, importance, compatibility)
               for code in ALL_CODES
               for importance in ("REQUIRED", "PREFERRED", "FLEXIBLE")
               for compatibility in ("PASS", "FAIL", "UNKNOWN")]
    why, differences = match_review.shown_content(results, scope)
    shown = {e["code"] for e in why["criteria"]} | {e["code"] for e in differences}
    assert shown == allowed
    for never in ("LOCATION", "DOCUMENT_TYPE", "RIGHT_TYPE", "ROOMS_MIN", "BEDROOMS_MIN",
                  "BUDGET_MAX", "BUDGET_TARGET", "TRANSACTION_INTENT"):
        assert never not in shown


def test_the_shapes_carry_no_value_delta_evidence_or_rule():
    why, differences = match_review.shown_content([
        _result("PROPERTY_TYPE", "REQUIRED", "PASS"),
        _result("LAND_AREA_MIN", "PREFERRED", "PASS"),
        _result("BUILT_AREA_MIN", "FLEXIBLE", "UNKNOWN"),
        _result("LAND_AREA_MIN", "FLEXIBLE", "FAIL"),
        _result("BUILT_AREA_MIN", "PREFERRED", "UNKNOWN", blocking=True),
        _result("PROPERTY_TYPE", "FLEXIBLE", "PASS"),
    ], "PROPERTY_DETAILS_ALLOWED")
    assert why == {"format": "turab.why-real/1", "criteria": [
        {"code": "PROPERTY_TYPE", "label_ar": "label PROPERTY_TYPE", "importance": "REQUIRED"},
        {"code": "LAND_AREA_MIN", "label_ar": "label LAND_AREA_MIN",
         "importance": "PREFERRED"}]}
    assert differences == [{"code": "BUILT_AREA_MIN", "compatibility": "UNKNOWN"},
                           {"code": "LAND_AREA_MIN", "compatibility": "FAIL"}]


def test_a_result_of_another_rule_version_is_not_shown():
    why, differences = match_review.shown_content(
        [_result("LAND_AREA_MIN", "REQUIRED", "PASS", rule=("criterion.area_min", "1")),
         _result("PROPERTY_TYPE", "PREFERRED", "FAIL", rule=("criterion.other", "1"))],
        "PROPERTY_DETAILS_ALLOWED")
    assert (why["criteria"], differences) == ([], [])


def test_whether_a_claim_stands_behind_a_result_changes_nothing_shown():
    """The content depends on the codes, the scope and the shown results only:
    a claim link, a value or a delta on ANY result changes nothing."""
    plain = [_result(c) for c in ALL_CODES]
    linked = [{**r, "evidence_claim_id": uuid.uuid4(), "property_value": "SECRET",
               "delta": {"dzd": 1}} for r in plain]
    for scope in match_review.SHOWN_BY_SCOPE:
        assert match_review.shown_content(plain, scope) == match_review.shown_content(
            linked, scope)


class _Reads(dict):
    """A snapshot that records which keys a rule reads."""

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.read = set()

    def __getitem__(self, key):
        self.read.add(key)
        return super().__getitem__(key)

    def get(self, key, default=None):
        self.read.add(key)
        return super().get(key, default)


@pytest.mark.parametrize("code,keys", [("PROPERTY_TYPE", {"property_type"}),
                                       ("LAND_AREA_MIN", {"land_area_m2"}),
                                       ("BUILT_AREA_MIN", {"built_area_m2"})])
def test_each_shown_rule_reads_only_its_rendered_field_and_links_no_claim(code, keys):
    """G5-5: a pinned-rule test. A later version that reads another key, or
    links a claim, fails here and forces a decision."""
    rule_id, version = match_review.SHOWN_RULES[code]
    rule = REGISTRY.resolve(rule_id, version)
    prop = _Reads({"property_type": "LAND", "land_area_m2": 400, "built_area_m2": 120,
                   "attributes": [], "canonical_location_id": None})
    request, offer = _Reads(), _Reads()
    value = "LAND" if code == "PROPERTY_TYPE" else 100
    out = rule.evaluate({"code": code, "operator": "EQ" if code == "PROPERTY_TYPE" else "GTE",
                         "value": value, "importance": "REQUIRED"}, request, prop, offer)
    assert prop.read == keys and request.read == set() and offer.read == set()
    assert out["evidence_claim_id"] is None
    assert rules  # the module that registers the pinned rules is loaded


def test_the_stored_content_follows_the_scope_and_carries_no_private_value(client, engine,
                                                                           ids):
    """Over HTTP, the STORED fields (the customer render is step 4's):
    - at PROPERTY_DETAILS_ALLOWED: PROPERTY_TYPE and LAND_AREA_MIN shown, the
      unknown BUILT_AREA_MIN listed as a difference;
    - at SUMMARY_ONLY: PROPERTY_TYPE only;
    - DOCUMENT_TYPE and BUDGET_MAX, both PASS, never; a sentinel seller
      expectation and the property's document never appear."""
    stored = {}
    for scope in ("PROPERTY_DETAILS_ALLOWED", "SUMMARY_ONLY"):
        req, prop, [offer], [m] = _world(
            client, engine, ids, desired_type="LAND", expectation=27_777_777,
            area_criteria=[("LAND_AREA_MIN", "PREFERRED", 300),
                           ("BUILT_AREA_MIN", "FLEXIBLE", 80)])
        assert m["eligibility"] == "ELIGIBLE"
        _exec(engine, """UPDATE turab.property_offers
                            SET permission_scope = CAST(:s AS turab.sharing_scope)
                          WHERE offer_id = :o""", s=scope, o=offer)
        assert _approve(client, m["match_id"], ids.ACC_REVIEWER).status_code == 200
        o = _opportunity(engine, m["match_id"])
        stored[scope] = (json.loads(o["why_real_text"]), json.loads(o["kd_text"]))
        for text_ in (o["why_real_text"], o["kd_text"]):
            for secret in ("27777777", "LAND_BOOK", "DOCUMENT_TYPE", "BUDGET_MAX",
                           "claim", "delta", "rule"):
                assert secret not in text_, (scope, secret)
    labels = {r["code"]: r["label_ar"] for r in _all(
        engine, "SELECT code, label_ar FROM turab.criterion_definitions")}
    details_why, details_kd = stored["PROPERTY_DETAILS_ALLOWED"]
    assert details_why == {"format": "turab.why-real/1", "criteria": [
        {"code": "LAND_AREA_MIN", "label_ar": labels["LAND_AREA_MIN"],
         "importance": "PREFERRED"},
        {"code": "PROPERTY_TYPE", "label_ar": labels["PROPERTY_TYPE"],
         "importance": "REQUIRED"}]}
    assert details_kd == [{"code": "BUILT_AREA_MIN", "compatibility": "UNKNOWN"}]
    summary_why, summary_kd = stored["SUMMARY_ONLY"]
    assert summary_why == {"format": "turab.why-real/1", "criteria": [
        {"code": "PROPERTY_TYPE", "label_ar": labels["PROPERTY_TYPE"],
         "importance": "REQUIRED"}]}
    assert summary_kd == []


# ======================================================================================
# Writers (§7 condition 3)
# ======================================================================================

def test_the_approved_review_is_the_one_writer_of_opportunities():
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[1]
    pattern = re.compile(r"INSERT\s+INTO\s+turab\.opportunities\b")
    writers = sorted(str(p.relative_to(root)) for p in (root / "src").rglob("*.py")
                     if pattern.search(p.read_text()))
    assert writers == ["src/turab/services/match_review.py"]
