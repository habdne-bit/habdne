"""Slice 4 step 8: the two staff reads, the ten mandatory tests, the
reference scenarios, and STOP GATE D's two proofs. Over HTTP and against
PostgreSQL.

Ref: `docs/gate/SLICE_4_PLAN.md` §1 (the three operations), §3.5 (staff
DTO only), §6.1 (the ten mandatory tests, their planned names), §6.2
(STOP GATE D: reconstruction and replay), §7 (acceptance); Developer Spec
§24 M-01 … M-06; red-team B04, C01, C03, C04, D02, E02, G01 … G06;
`matching/reconstruct.py`.

**Isolation.** As in step 7: every test builds its own rows and narrows
every run to its own properties.

**Mandatory tests 2 and 6 are narrowed**, as the plan states: the API
review is Slice 5, so test 2 proves the engine and the schema; G4-9 (a)
leaves test 6 its refusing half.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.conftest import REPO_ROOT
from tests.test_slice4_step7 import (VERSION, _all, _exact, _exec, _headers, _matches,
                                     _offer, _one, _property, _request, _stored_match)
from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.matching import reconstruct
from turab.services import matching_run


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _criterion(engine, req, code, op, value, importance, sort_order=0,
               blocking_if_unknown=False):
    return _one(engine, """
        INSERT INTO turab.request_criteria (request_id, criterion_code, importance, operator,
                                            value, blocking_if_unknown, sort_order)
        VALUES (:r, :c, CAST(:i AS turab.criterion_importance),
                CAST(:o AS turab.criterion_operator), CAST(:v AS jsonb), :b, :s)
        RETURNING request_criterion_id""", r=req, c=code, i=importance, o=op,
                v=json.dumps(value), b=blocking_if_unknown, s=sort_order)


def _location(engine, parent=None):
    return _one(engine, """INSERT INTO turab.locations (code, canonical_ar, location_type,
                                                      parent_id)
                           VALUES (:c, 'موقع اختبار', 'AREA', :p) RETURNING location_id""",
                c=f"TEST-S4S8-{uuid.uuid4().hex[:16]}", p=parent)


def _run(client, ids, req, props, account=None, key=None):
    return client.post(f"/requests/{req}/matching/run",
                       headers=_headers(account or ids.ACC_OPERATOR, key),
                       json={"matching_policy_version": VERSION,
                             "property_ids": [str(p) for p in props]})


def _matched(client, ids, req, props):
    r = _run(client, ids, req, props)
    assert r.status_code == 201, r.text
    return _exact(r.text)


def _get(client, path, account):
    return client.get(path, headers={"Authorization": f"Bearer {account}"})


def _world(engine, ids, *, document="LAND_BOOK", **offer_kw):
    """ELIGIBLE by default: BUY, max 30M REQUIRED; REQUIRED DOCUMENT_TYPE EQ
    LAND_BOOK; a fresh LAND property holding it; one fresh ACTIVE SALE offer
    at 20M, not negotiable, with a current PRIVATE_MATCHING_ONLY binding."""
    req = _request(engine, ids)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    prop = _property(engine, document=document)
    offer = _offer(engine, ids, prop, **offer_kw)
    return req, prop, offer


def _criterion_of(match, code):
    [c] = [c for c in match["criteria"] if c["criterion_code"] == code]
    return c


def _rows(engine, match_id):
    """The stored match and its criterion rows, from their jsonb TEXT, read
    exactly: what `reconstruct` and `replay` are given."""
    match = _exact(_one(engine, "SELECT to_jsonb(m)::text FROM turab.match_candidates m "
                                "WHERE match_id = :m", m=match_id))
    rows = [_exact(r["t"]) for r in _all(engine, """
        SELECT to_jsonb(c)::text AS t FROM turab.match_criterion_results c
         WHERE match_id = :m""", m=match_id)]
    return match, rows


# ======================================================================================
# GET /matches/{match_id}
# ======================================================================================

def test_a_match_is_read_exactly_as_stored(client, ids, engine):
    """The body, read with Decimal, is the stored rows, read with Decimal;
    and it is the run's own response for that match. The review's numeric
    case of step 7 keeps every digit."""
    req = _request(engine, ids)
    _exec(engine, """
        INSERT INTO turab.request_criteria (request_id, criterion_code, importance, operator,
                                            value, sort_order)
        VALUES (:r, 'LAND_AREA_MIN', 'REQUIRED', 'GTE', '0.12345678901234568'::jsonb, 0)""",
          r=req)
    prop = _property(engine, land=Decimal("400.25"))
    _offer(engine, ids, prop)
    [ran] = _matched(client, ids, req, [prop])["matches"]
    r = _get(client, f"/matches/{ran['match_id']}", ids.ACC_REVIEWER)
    assert r.status_code == 200, r.text
    read = _exact(r.text)
    assert read == ran
    read["criteria"] = sorted(read["criteria"], key=lambda c: (c["criterion_code"],
                                                               c["ordinal"]))
    assert read == _stored_match(engine, ran["match_id"])
    assert _criterion_of(read, "LAND_AREA_MIN")["delta"] == {
        "m2": Decimal("400.12654321098765432")}


@pytest.mark.parametrize("account", ["ACC_OPERATOR", "ACC_REVIEWER", "ACC_ADMIN"])
def test_each_staff_role_of_the_contract_reads_a_match(client, ids, engine, account):
    req, prop, _ = _world(engine, ids)
    [m] = _matched(client, ids, req, [prop])["matches"]
    assert _get(client, f"/matches/{m['match_id']}", getattr(ids, account)).status_code == 200


def test_a_customer_cannot_read_a_match(client, ids, engine):
    """R9.2: there is no customer path to a match; the role gate refuses."""
    req, prop, _ = _world(engine, ids)
    [m] = _matched(client, ids, req, [prop])["matches"]
    r = _get(client, f"/matches/{m['match_id']}", ids.ACC_AMINA)
    assert (r.status_code, r.json()["code"]) == (403, "ROLE_NOT_PERMITTED")


def test_an_unknown_match_is_refused_as_every_staff_read(client, ids, sink):
    """The staff-read convention (Slice 3): one answer, 403, for an id that is
    not there; and the denial is recorded."""
    unknown = uuid.uuid4()
    r = _get(client, f"/matches/{unknown}", ids.ACC_OPERATOR)
    assert (r.status_code, r.json()["code"]) == (403, "OBJECT_NOT_AUTHORIZED")
    denied = [rec for rec in sink.records if rec.resource_id == unknown]
    assert [(d.event.value, d.resource_kind) for d in denied] == [("DENIED", "MATCH_CANDIDATE")]


def test_a_match_read_is_recorded(client, ids, engine, sink):
    """R6.3: a staff read of a match is an access record, with the operation,
    the actor and the match."""
    req, prop, _ = _world(engine, ids)
    [m] = _matched(client, ids, req, [prop])["matches"]
    _get(client, f"/matches/{m['match_id']}", ids.ACC_REVIEWER)
    reads = [rec for rec in sink.records if str(rec.resource_id) == m["match_id"]]
    assert [(r.event.value, r.operation_id, r.resource_kind, r.actor_account_id)
            for r in reads] == [("READ", "getMatchesMatchId", "MATCH_CANDIDATE",
                                 ids.ACC_REVIEWER)]


# ======================================================================================
# GET /requests/{request_id}/diagnostic
# ======================================================================================

def test_the_latest_diagnostic_is_read_as_stored(client, ids, engine):
    """Two runs, two rows; the read returns the later one, as stored."""
    req, prop, _ = _world(engine, ids)
    _matched(client, ids, req, [prop])
    second = _matched(client, ids, req, [prop])["diagnostic"]
    r = _get(client, f"/requests/{req}/diagnostic", ids.ACC_OPERATOR)
    assert r.status_code == 200, r.text
    read = _exact(r.text)
    assert read == second
    assert read["diagnostic_run_id"] == str(_one(engine, """
        SELECT diagnostic_run_id FROM turab.match_diagnostic_runs WHERE request_id = :r
         ORDER BY run_at DESC LIMIT 1""", r=req))
    for key in ("request_id", "ready_opportunity_count", "actionable_unknown_count",
                "near_match_count"):
        assert key in read
    assert (read["suggested_actions"], read["relaxation_scenarios"]) == ([], [])


def test_a_request_never_run_has_no_diagnostic(client, ids, engine):
    req = _request(engine, ids)
    r = _get(client, f"/requests/{req}/diagnostic", ids.ACC_OPERATOR)
    assert (r.status_code, r.json()["code"]) == (404, "NOT_FOUND")


def test_the_diagnostic_of_an_unknown_request_is_refused_as_every_staff_read(client, ids):
    r = _get(client, f"/requests/{uuid.uuid4()}/diagnostic", ids.ACC_OPERATOR)
    assert (r.status_code, r.json()["code"]) == (403, "OBJECT_NOT_AUTHORIZED")


def test_a_customer_cannot_read_a_diagnostic(client, ids, engine):
    req, prop, _ = _world(engine, ids)
    _matched(client, ids, req, [prop])
    r = _get(client, f"/requests/{req}/diagnostic", ids.ACC_AMINA)
    assert (r.status_code, r.json()["code"]) == (403, "ROLE_NOT_PERMITTED")


def test_a_diagnostic_read_is_recorded(client, ids, engine, sink):
    req, prop, _ = _world(engine, ids)
    diagnostic = _matched(client, ids, req, [prop])["diagnostic"]
    _get(client, f"/requests/{req}/diagnostic", ids.ACC_REVIEWER)
    kinds = {(str(r.resource_id), r.resource_kind) for r in sink.records
             if r.operation_id == "getRequestsRequestIdDiagnostic" and r.event.value == "READ"}
    assert (diagnostic["diagnostic_run_id"], "MATCH_DIAGNOSTIC_RUN") in kinds
    assert (str(req), "REQUEST") in kinds


def test_no_customer_or_public_operation_returns_a_match_or_a_diagnostic():
    """R9.2, acceptance condition 9, from the effective contract: no operation
    a CUSTOMER may call, and none without security, has a response schema
    that is, or contains, `MatchCandidate`, `CriterionResult` or
    `Diagnostic`; and the three Slice 4 operations are staff-only."""
    doc = yaml.safe_load((REPO_ROOT / "docs" / "api" / "openapi_effective_v0.2.3.yaml")
                         .read_text(encoding="utf-8"))
    schemas = doc["components"]["schemas"]
    match_names = {"MatchCandidate", "CriterionResult", "Diagnostic"}

    def refs(node, seen):
        if isinstance(node, dict):
            ref = node.get("$ref")
            if isinstance(ref, str) and ref.startswith("#/components/schemas/"):
                name = ref.rsplit("/", 1)[1]
                if name not in seen:
                    seen.add(name)
                    refs(schemas.get(name, {}), seen)
            for value in node.values():
                refs(value, seen)
        elif isinstance(node, list):
            for value in node:
                refs(value, seen)
        return seen

    offenders, staff_only = [], {}
    for path, item in doc["paths"].items():
        for method, op in item.items():
            if not isinstance(op, dict) or "responses" not in op:
                continue
            roles = set(op.get("x-roles") or [])
            open_to_customers = "CUSTOMER" in roles or not op.get("security", True)
            reached = refs(op["responses"], set())
            if open_to_customers and reached & match_names:
                offenders.append((method, path, sorted(reached & match_names)))
            if op.get("operationId") in ("getMatchesMatchId", "getRequestsRequestIdDiagnostic",
                                          "postRequestsRequestIdMatchingRun"):
                staff_only[op["operationId"]] = roles
    assert offenders == []
    assert staff_only == {name: {"ADMIN", "OPERATOR", "REVIEWER"} for name in staff_only}
    assert len(staff_only) == 3


# ======================================================================================
# The ten mandatory tests (plan §6.1), under their planned names
# ======================================================================================

def test_a_buy_request_never_evaluates_a_rent_offer(client, ids, engine):
    """1 (C01). One property carries a SALE offer and a RENT offer; a BUY run
    evaluates the SALE offer only. The schema half is step 3's
    `test_the_schema_refuses_a_buy_match_on_a_rent_offer`."""
    req, prop, sale = _world(engine, ids)
    _offer(engine, ids, prop, transaction="RENT", price=70_000, consent=False)
    body = _matched(client, ids, req, [prop])
    assert [m["evaluated_offer_id"] for m in body["matches"]] == [str(sale)]
    assert {m["commercial_context_snapshot"]["transaction_type"]
            for m in body["matches"]} == {"SALE"}


def test_a_hard_fail_is_rejected_whatever_the_soft_score(client, ids, engine):
    """2 (G01), over HTTP. Every soft criterion passes and the target is met
    exactly; a REQUIRED document mismatch still rejects, with no score. The
    same world with the right document is ELIGIBLE with the full score.
    NARROWED: the API review is Slice 5; the schema half is
    `test_the_schema_refuses_to_approve_a_rejected_match`."""
    def world(document):
        req, prop, _ = _world(engine, ids, document=document)
        _criterion(engine, req, "PROPERTY_TYPE", "EQ", "LAND", "PREFERRED", sort_order=1)
        _criterion(engine, req, "LAND_AREA_MIN", "GTE", 300, "FLEXIBLE", sort_order=2)
        _criterion(engine, req, "BUDGET_TARGET", "EQ", 20_000_000, "PREFERRED", sort_order=3)
        [m] = _matched(client, ids, req, [prop])["matches"]
        return m
    rejected = world("POSSESSION_CERTIFICATE")
    assert (rejected["eligibility"], rejected["soft_score"]) == ("REJECTED", None)
    assert _criterion_of(rejected, "DOCUMENT_TYPE")["compatibility"] == "FAIL"
    eligible = world("LAND_BOOK")
    assert (eligible["eligibility"], eligible["soft_score"]) == ("ELIGIBLE", Decimal("1"))


def test_the_schema_refuses_to_approve_a_rejected_match(client, ids, engine):
    """2, its schema half, on a match the RUN wrote: `enforce_approved_review_gate`
    refuses an APPROVED review of a REJECTED match. Inside a transaction that
    is rolled back: no review row is ever kept (acceptance condition 6)."""
    req, prop, _ = _world(engine, ids, document="POSSESSION_CERTIFICATE")
    [m] = _matched(client, ids, req, [prop])["matches"]
    assert m["eligibility"] == "REJECTED"
    with engine.connect() as conn, conn.begin() as tx:
        with pytest.raises(Exception, match="Cannot approve match"):
            conn.execute(text("""INSERT INTO turab.match_reviews (match_id, decision,
                                                                  reviewer_account_id)
                                 VALUES (:m, 'APPROVED', :a)"""),
                         {"m": m["match_id"], "a": ids.ACC_REVIEWER})
        tx.rollback()
    assert _one(engine, "SELECT count(*) FROM turab.match_reviews WHERE match_id = :m",
                m=m["match_id"]) == 0


def test_a_required_unknown_is_need_more_information_never_pass_or_fail(client, ids, engine):
    """3 (C03, M-02): a REQUIRED document not recorded is UNKNOWN, blocking,
    and the candidate NEED_MORE_INFORMATION; neither PASS nor FAIL."""
    req, prop, _ = _world(engine, ids, document=None)
    [m] = _matched(client, ids, req, [prop])["matches"]
    document = _criterion_of(m, "DOCUMENT_TYPE")
    assert (document["compatibility"], document["blocking"]) == ("UNKNOWN", True)
    assert (m["eligibility"], m["hard_gate_status"], m["information_gate_status"]) == (
        "NEED_MORE_INFORMATION", "UNKNOWN", "UNKNOWN")


def test_negotiable_above_max_is_unknown_not_pass(client, ids, engine):
    """4 (G02, M-04): asking 35M above a 30M maximum, negotiable YES, no
    expectation: UNKNOWN (PRICE_NEGOTIATION_UNCONFIRMED), never PASS."""
    req, prop, _ = _world(engine, ids, price=35_000_000, negotiable="YES")
    [m] = _matched(client, ids, req, [prop])["matches"]
    budget = _criterion_of(m, "BUDGET_MAX")
    assert (budget["compatibility"], budget["reason_code"]) == (
        "UNKNOWN", "PRICE_NEGOTIATION_UNCONFIRMED")
    assert m["eligibility"] == "NEED_MORE_INFORMATION"


def test_seller_expectation_can_pass_price_and_is_never_exposed(client, ids, engine):
    """5 (D02, M-03): asking 35M above the 30M maximum, expectation 27,777,777
    within it: the price PASSES on the expectation. It is never exposed: no
    customer or public operation returns a match
    (`test_no_customer_or_public_operation_returns_a_match_or_a_diagnostic`),
    a customer is refused the match, and neither the explanation, the next
    action nor the diagnostic carries the field or its value."""
    req, prop, _ = _world(engine, ids, price=35_000_000, expectation=27_777_777)
    body = _matched(client, ids, req, [prop])
    [m] = body["matches"]
    assert (_criterion_of(m, "BUDGET_MAX")["compatibility"], m["eligibility"]) == (
        "PASS", "ELIGIBLE")
    assert _get(client, f"/matches/{m['match_id']}", ids.ACC_AMINA).status_code == 403
    shown = json.dumps([m["explanation"], m["next_action"], body["diagnostic"]], default=str)
    assert "seller_expectation" not in shown and "27777777" not in shown


def test_a_potential_property_without_willingness_context_is_not_evaluated(client, ids,
                                                                          engine):
    """6, NARROWED to its refusing half (G4-9 (a)): a POTENTIAL property with no
    offer is not evaluated, and the diagnostic says why."""
    req = _request(engine, ids)
    prop = _one(engine, """
        INSERT INTO turab.properties (property_type, supply_mode, management_mode,
                                      claim_status, current_availability)
        VALUES ('LAND', 'POTENTIAL', 'ASSISTED', 'UNCLAIMED', 'AVAILABLE')
        RETURNING property_id""")
    body = _matched(client, ids, req, [prop])
    assert body["matches"] == []
    assert [(e["property_id"], e["reason"])
            for e in body["diagnostic"]["blocker_summary"]["excluded"]] == [
        (str(prop), "POTENTIAL_WITHOUT_OFFER")]


def test_an_old_match_replays_from_its_snapshots_after_everything_changed(client, ids,
                                                                        engine):
    """7 (G04, C04). After the request's criteria, the property's document,
    the offer's price and the consent have ALL changed:
    - GET the old match returns exactly what it returned before;
    - its decisions are reconstructed, and its criterion results and input
      hash replayed, from its stored rows alone;
    - a new run is a new match, beside the old one (a new input)."""
    req, prop, offer = _world(engine, ids)
    [old] = _matched(client, ids, req, [prop])["matches"]
    before = _get(client, f"/matches/{old['match_id']}", ids.ACC_OPERATOR).text
    version = _one(engine, "SELECT version FROM turab.requests WHERE request_id = :r", r=req)

    _criterion(engine, req, "LAND_AREA_MIN", "GTE", 500, "REQUIRED", sort_order=5)
    _exec(engine, "UPDATE turab.requests SET budget_max_dzd = 31000000 WHERE request_id = :r",
          r=req)
    _exec(engine, """UPDATE turab.property_attributes SET value = '"POSSESSION_CERTIFICATE"'
                      WHERE property_id = :p""", p=prop)
    _exec(engine, "UPDATE turab.property_offers SET asking_price_dzd = 29000000 "
                  "WHERE offer_id = :o", o=offer)
    _exec(engine, """UPDATE turab.consent_grants SET status = 'REVOKED', revoked_at = now()
                      WHERE consent_id IN (SELECT consent_id
                                             FROM turab.resource_consent_bindings
                                            WHERE offer_id = :o)""", o=offer)

    assert _get(client, f"/matches/{old['match_id']}", ids.ACC_OPERATOR).text == before
    match, rows = _rows(engine, old["match_id"])
    assert reconstruct.reconstruct(match, rows) == []
    assert reconstruct.replay(match, rows) == []
    [new] = _matched(client, ids, req, [prop])["matches"]
    assert new["match_id"] != old["match_id"] and new["input_hash"] != old["input_hash"]
    assert new["request_version"] > version
    assert (new["eligibility"], new["permission_gate_status"]) == ("REJECTED", "FAIL")


def test_match_rows_and_their_criterion_results_cannot_change(client, ids, engine):
    """8, on rows the RUN wrote: the match, its criterion results and its
    diagnostic refuse UPDATE and DELETE (the frozen trigger; migration
    0005)."""
    req, prop, _ = _world(engine, ids)
    body = _matched(client, ids, req, [prop])
    [m] = body["matches"]
    statements = [
        ("UPDATE turab.match_candidates SET eligibility = 'REJECTED' WHERE match_id = :m", m),
        ("DELETE FROM turab.match_candidates WHERE match_id = :m", m),
        ("UPDATE turab.match_criterion_results SET compatibility = 'FAIL' WHERE match_id = :m",
         m),
        ("DELETE FROM turab.match_criterion_results WHERE match_id = :m", m),
        ("UPDATE turab.match_diagnostic_runs SET near_match_count = 9 "
         "WHERE diagnostic_run_id = :d", m),
        ("DELETE FROM turab.match_diagnostic_runs WHERE diagnostic_run_id = :d", m),
    ]
    stored = _stored_match(engine, m["match_id"])
    for sql, _ in statements:
        with engine.connect() as conn, conn.begin() as tx:
            with pytest.raises(Exception):
                conn.execute(text(sql), {"m": m["match_id"],
                                         "d": body["diagnostic"]["diagnostic_run_id"]})
            tx.rollback()
    assert _stored_match(engine, m["match_id"]) == stored


def _alias_of(engine, ids, canonical):
    alias = _property(engine)
    _offer(engine, ids, alias)
    cid = _one(engine, """INSERT INTO turab.property_identity_candidates
                                 (property_a_id, property_b_id)
                          VALUES (:a, :b) RETURNING identity_candidate_id""",
               a=min(alias, canonical), b=max(alias, canonical))
    _exec(engine, """INSERT INTO turab.property_identity_aliases
                            (alias_property_id, canonical_property_id,
                             source_identity_candidate_id, resolved_by_account_id)
                     VALUES (:a, :c, :cid, :acct)""",
          a=alias, c=canonical, cid=cid, acct=ids.ACC_REVIEWER)
    _exec(engine, """UPDATE turab.property_identity_candidates
                        SET review_status = 'CONFIRMED_SAME'
                      WHERE identity_candidate_id = :c""", c=cid)
    return alias


def test_an_alias_is_never_a_candidate(client, ids, engine):
    """9 (E02), over HTTP: an alias carrying a qualifying offer is listed and
    is not a candidate; the diagnostic names its canonical record."""
    req, canonical, _ = _world(engine, ids)
    alias = _alias_of(engine, ids, canonical)
    body = _matched(client, ids, req, [canonical, alias])
    assert [m["property_id"] for m in body["matches"]] == [str(canonical)]
    [excluded] = body["diagnostic"]["blocker_summary"]["excluded"]
    assert (excluded["property_id"], excluded["reason"],
            excluded["detail"]["canonical_property_id"]) == (
        str(alias), "OFFER_ON_ALIAS", str(canonical))


def test_the_schema_refuses_a_match_on_an_alias(client, ids, engine):
    """9, its schema half: the run's own row, re-inserted against an alias,
    is refused by `trg_match_commercial_context`. Rolled back."""
    req, canonical, _ = _world(engine, ids)
    [m] = _matched(client, ids, req, [canonical])["matches"]
    alias = _alias_of(engine, ids, canonical)
    with engine.connect() as conn, conn.begin() as tx:
        with pytest.raises(Exception, match="canonical properties"):
            conn.execute(text("""
                INSERT INTO turab.match_candidates (
                    request_id, property_id, matching_policy_id, matching_policy_version,
                    request_version, property_version, eligibility, hard_gate_status,
                    information_gate_status, request_freshness, property_freshness,
                    freshness_gate_status, permission_gate_status, request_snapshot,
                    property_snapshot, input_hash)
                SELECT request_id, :alias, matching_policy_id, matching_policy_version,
                       request_version, property_version, eligibility, hard_gate_status,
                       information_gate_status, request_freshness, property_freshness,
                       freshness_gate_status, permission_gate_status, request_snapshot,
                       property_snapshot, input_hash || '-alias'
                  FROM turab.match_candidates WHERE match_id = :m"""),
                         {"alias": alias, "m": m["match_id"]})
        tx.rollback()


# Mandatory test 10 (G06) is step 7's `test_no_candidate_is_a_valid_run`, over HTTP.


# ======================================================================================
# The reference scenarios (Spec §24; red-team), each over HTTP
# ======================================================================================

def test_m01_a_required_location_fail_rejects_whatever_else(client, ids, engine):
    """M-01: a REQUIRED location FAILS while every other criterion is
    excellent: REJECTED, a near match (exactly one REQUIRED FAIL), no
    opportunity, no next action."""
    wanted, elsewhere = _location(engine), _location(engine)
    req, prop, _ = _world(engine, ids)
    _exec(engine, """UPDATE turab.requests SET primary_location_id = :l,
                            location_importance = 'REQUIRED' WHERE request_id = :r""",
          l=wanted, r=req)
    _exec(engine, "UPDATE turab.properties SET canonical_location_id = :l "
                  "WHERE property_id = :p", l=elsewhere, p=prop)
    body = _matched(client, ids, req, [prop])
    [m] = body["matches"]
    location = _criterion_of(m, "LOCATION")
    assert (location["compatibility"], location["reason_code"]) == ("FAIL",
                                                                  "LOCATION_MISMATCH")
    assert (m["eligibility"], m["next_action"]) == ("REJECTED", None)
    assert body["diagnostic"]["near_match_count"] == 1
    assert _one(engine, "SELECT count(*) FROM turab.opportunities WHERE request_id = :r",
                r=req) == 0


def test_m02_a_required_document_unknown_asks_for_the_document(client, ids, engine):
    """M-02: NEED_MORE_INFORMATION, and the next action is a HIGH
    VERIFY_DOCUMENT on the property (a recommendation; no task, D1)."""
    req, prop, _ = _world(engine, ids, document=None)
    [m] = _matched(client, ids, req, [prop])["matches"]
    assert m["eligibility"] == "NEED_MORE_INFORMATION"
    assert (m["next_action"]["type"], m["next_action"]["priority"],
            m["next_action"]["subject"]["entity"]) == ("VERIFY_DOCUMENT", "HIGH", "PROPERTY")


def test_m05_a_stale_property_with_every_criterion_passing_needs_confirmation(client, ids,
                                                                              engine):
    req, prop, _ = _world(engine, ids)
    _exec(engine, """UPDATE turab.properties
                        SET availability_last_confirmed_at = now() - interval '45 days'
                      WHERE property_id = :p""", p=prop)
    [m] = _matched(client, ids, req, [prop])["matches"]
    assert (m["hard_gate_status"], m["property_freshness"], m["freshness_gate_status"],
            m["eligibility"]) == ("PASS", "STALE", "FAIL", "NEEDS_CONFIRMATION")
    assert m["next_action"]["type"] == "RECONFIRM_PROPERTY"


def test_m06_a_stale_request_needs_confirmation(client, ids, engine):
    req, prop, _ = _world(engine, ids)
    _exec(engine, """UPDATE turab.requests SET last_confirmed_at = now() - interval '45 days'
                      WHERE request_id = :r""", r=req)
    [m] = _matched(client, ids, req, [prop])["matches"]
    assert (m["request_freshness"], m["eligibility"]) == ("STALE", "NEEDS_CONFIRMATION")
    assert m["next_action"]["type"] == "RECONFIRM_REQUEST"


def test_g03_each_match_names_its_evaluated_offer_and_version(client, ids, engine):
    """G03: two offers on one property, each match explained against its own
    offer: the evaluated offer, its version and its commercial snapshot
    agree."""
    req, prop, first = _world(engine, ids)
    second = _offer(engine, ids, prop, price=25_000_000)
    body = _matched(client, ids, req, [prop])
    assert {m["evaluated_offer_id"] for m in body["matches"]} == {str(first), str(second)}
    for m in body["matches"]:
        snapshot = m["commercial_context_snapshot"]
        assert (snapshot["offer_id"], snapshot["version"]) == (m["evaluated_offer_id"],
                                                               m["offer_version"])
        assert _criterion_of(m, "BUDGET_MAX")["property_value"]["asking_price_dzd"] == \
            snapshot["asking_price_dzd"]


def test_g05_a_match_names_an_existing_policy_and_its_version(client, ids, engine):
    req, prop, _ = _world(engine, ids)
    [m] = _matched(client, ids, req, [prop])["matches"]
    assert _one(engine, "SELECT version FROM turab.matching_policies "
                        "WHERE matching_policy_id = :p", p=m["matching_policy_id"]) == \
        m["matching_policy_version"] == VERSION


def test_c04_changing_criteria_makes_a_new_match_and_keeps_the_old(client, ids, engine):
    req, prop, _ = _world(engine, ids)
    [old] = _matched(client, ids, req, [prop])["matches"]
    stored = _stored_match(engine, old["match_id"])
    _criterion(engine, req, "LAND_AREA_MIN", "GTE", 100, "PREFERRED", sort_order=7)
    [new] = _matched(client, ids, req, [prop])["matches"]
    assert new["match_id"] != old["match_id"]
    assert _stored_match(engine, old["match_id"]) == stored
    assert len(_matches(engine, req)) == 2


def test_b04_a_private_matching_only_binding_admits_internal_matching(client, ids, engine):
    """B04, its matching half: the offer's only binding is
    PRIVATE_MATCHING_ONLY, and it counts for internal matching (G4-10). Its
    public half, absence from public browse, is Slice 3's
    `test_only_active_consented_offers_are_projected`."""
    req, prop, offer = _world(engine, ids)
    assert _all(engine, "SELECT purpose::text AS p FROM turab.resource_consent_bindings "
                        "WHERE offer_id = :o", o=offer) == [{"p": "PRIVATE_MATCHING_ONLY"}]
    [m] = _matched(client, ids, req, [prop])["matches"]
    assert (m["permission_gate_status"], m["eligibility"]) == ("PASS", "ELIGIBLE")


# ======================================================================================
# STOP GATE D (plan §6.2): reconstruction and replay, from stored rows alone
# ======================================================================================

def _scenario_suite(client, ids, engine):
    """One run per kind of decision the engine records, so the two proofs
    below meet each one. Returns the match ids written here."""
    made = []

    def run(req, props):
        made.extend(m["match_id"] for m in _matched(client, ids, req, props)["matches"])

    req, prop, _ = _world(engine, ids)                                   # ELIGIBLE
    _criterion(engine, req, "BUDGET_TARGET", "EQ", 21_000_000, "FLEXIBLE", sort_order=4)
    _criterion(engine, req, "LAND_AREA_MIN", "GTE", 300, "PREFERRED", sort_order=5)
    _exec(engine, "UPDATE turab.requests SET budget_target_dzd = 19000000 "
                  "WHERE request_id = :r", r=req)
    run(req, [prop])
    req, prop, _ = _world(engine, ids, document="POSSESSION_CERTIFICATE")   # REJECTED
    run(req, [prop])
    req, prop, _ = _world(engine, ids, document=None)                     # NEED_MORE_INFO
    run(req, [prop])
    req, prop, _ = _world(engine, ids, consent=False)                     # NEEDS_CONFIRMATION
    run(req, [prop])
    req, prop, _ = _world(engine, ids, price=35_000_000, negotiable="YES")  # price UNKNOWN
    run(req, [prop])
    req, prop, _ = _world(engine, ids, price=35_000_000, expectation=27_000_000)
    run(req, [prop])
    req, prop, _ = _world(engine, ids)                                    # stale property
    _exec(engine, """UPDATE turab.properties
                        SET availability_last_confirmed_at = now() - interval '45 days'
                      WHERE property_id = :p""", p=prop)
    run(req, [prop])
    req, prop, _ = _world(engine, ids)                                    # blocking soft
    _criterion(engine, req, "LAND_AREA_MIN", "GTE", 300, "PREFERRED", sort_order=1,
               blocking_if_unknown=True)
    _exec(engine, "UPDATE turab.properties SET land_area_m2 = NULL WHERE property_id = :p",
          p=prop)
    run(req, [prop])
    return made


def _engine_matches(engine):
    """Every match the RUN wrote: its explanation carries the run's format.
    Rows inserted by hand as fixtures by earlier slices' tests (Slice 3's
    identity tests seed matches by SQL) are not engine output."""
    return [r["match_id"] for r in _all(engine, """
        SELECT match_id FROM turab.match_candidates
         WHERE explanation->>'format' = :f ORDER BY created_at, match_id""",
                                       f=reconstruct.EXPLANATION_FORMAT)]


def _record_counts(record_property, engine, made, every):
    """Recorded in the JUnit report (xunit1 properties), so STOP GATE D states
    the counts the run itself measured."""
    total = _one(engine, "SELECT count(*) FROM turab.match_candidates")
    record_property("matches_written_by_this_test", len(made))
    record_property("engine_matches_checked", len(every))
    record_property("fixture_rows_not_engine_output", total - len(every))


def test_every_stored_match_is_reconstructed_from_its_rows_alone(client, ids, engine,
                                                                 record_property):
    """STOP GATE D, proof 1. For EVERY match the run has written in this test
    database (this test's suite and every earlier test's runs), a pure
    function reading only the stored rows re-derives every gate, the
    eligibility, every reason, the soft score and the next action, by the
    versions the match names, and agrees with what was stored."""
    made = _scenario_suite(client, ids, engine)
    every = _engine_matches(engine)
    assert set(map(uuid.UUID, made)) <= set(every)
    _record_counts(record_property, engine, made, every)
    disagreements = {str(m): problems for m in every
                     if (problems := reconstruct.reconstruct(*_rows(engine, m)))}
    assert disagreements == {}, list(disagreements.items())[:3]
    eligibilities = {_one(engine, "SELECT eligibility::text FROM turab.match_candidates "
                                  "WHERE match_id = :m", m=m) for m in made}
    assert eligibilities == {"ELIGIBLE", "REJECTED", "NEED_MORE_INFORMATION",
                             "NEEDS_CONFIRMATION"}


def test_every_stored_match_replays_its_criterion_results_and_input_hash(
        client, ids, engine, record_property):
    """STOP GATE D, proof 2. For EVERY match the run has written, each
    criterion re-run by the rule version its row names, on the stored
    snapshots, gives the stored result; and the input hash is recomputed
    from the stored snapshots. The hash uses the CURRENT registry digest, the
    one these matches were evaluated under (see `reconstruct`'s limit)."""
    made = _scenario_suite(client, ids, engine)
    every = _engine_matches(engine)
    assert set(map(uuid.UUID, made)) <= set(every)
    _record_counts(record_property, engine, made, every)
    disagreements = {str(m): problems for m in every
                     if (problems := reconstruct.replay(*_rows(engine, m)))}
    assert disagreements == {}, list(disagreements.items())[:3]


@pytest.mark.parametrize("field, value", [
    ("eligibility", "ELIGIBLE"),
    ("hard_gate_status", "PASS"),
    ("information_gate_status", "PASS"),
    ("freshness_gate_status", "FAIL"),
    ("permission_gate_status", "FAIL"),
    ("soft_score", "0.5"),
    ("next_action", {"type": "OTHER", "priority": "HIGH", "subject": {}}),
    ("reasons", []),
])
def test_reconstruction_detects_a_stored_decision_that_was_not_derived(client, ids, engine,
                                                                       field, value):
    """The first proof is not vacuous: one stored decision altered in a copy
    of the rows (the stored rows themselves cannot change) is reported."""
    req, prop, _ = _world(engine, ids, document=None)
    [m] = _matched(client, ids, req, [prop])["matches"]
    match, rows = _rows(engine, m["match_id"])
    assert reconstruct.reconstruct(match, rows) == []
    if field == "reasons":
        match["explanation"]["reasons"] = value
    else:
        match[field] = Decimal(value) if field == "soft_score" else value
    assert any(p.startswith(field) for p in reconstruct.reconstruct(match, rows))


def test_reconstruction_detects_a_blocking_flag_that_was_not_derived(client, ids, engine):
    req, prop, _ = _world(engine, ids, document=None)
    [m] = _matched(client, ids, req, [prop])["matches"]
    match, rows = _rows(engine, m["match_id"])
    [document] = [r for r in rows if r["criterion_code"] == "DOCUMENT_TYPE"]
    document["blocking"] = False
    assert any("blocking" in p for p in reconstruct.reconstruct(match, rows))


@pytest.mark.parametrize("where", ["property_snapshot", "commercial_context_snapshot",
                                   "result", "permission_snapshot", "rule_explanation"])
def test_replay_detects_a_result_its_snapshots_do_not_give(client, ids, engine, where):
    """The second proof is not vacuous: a copy with a changed snapshot, or a
    changed criterion result, is reported."""
    req, prop, _ = _world(engine, ids)
    [m] = _matched(client, ids, req, [prop])["matches"]
    match, rows = _rows(engine, m["match_id"])
    assert reconstruct.replay(match, rows) == []
    if where == "property_snapshot":
        match["property_snapshot"]["attributes"][0]["value"] = "POSSESSION_CERTIFICATE"
    elif where == "commercial_context_snapshot":
        match["commercial_context_snapshot"]["asking_price_dzd"] = Decimal(35_000_000)
    elif where == "result":
        [budget] = [r for r in rows if r["criterion_code"] == "BUDGET_MAX"]
        budget["compatibility"] = "UNKNOWN"
    elif where == "permission_snapshot":
        # read by no criterion rule: only the input hash can tell
        match["permission_snapshot"]["permission_scope"] = "CHANGED"
    else:
        match["explanation"]["criteria"]["DOCUMENT_TYPE#1"]["rule_explanation"]["basis"] = "X"
    problems = reconstruct.replay(match, rows)
    assert problems != []
    if where == "permission_snapshot":
        assert problems == ["input_hash: not recomputed from the stored snapshots"]
    if where == "rule_explanation":
        assert problems == ["DOCUMENT_TYPE#1.explanation: stored differs from replayed"]
