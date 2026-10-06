"""Slice 4 step 7: the matching run, over HTTP and against PostgreSQL.

Ref: `docs/gate/SLICE_4_PLAN.md` §3.3, §3.6, G4-13, G4-15 (decided in the
review of b3246b0: D1–D6 with their constraints) and the seven conditions
recorded under G4-15; CORRECTION-004; `services/matching_run.py`,
`matching/explain.py`, `gates.next_action_v1`.

**Isolation.** HTTP tests commit to the shared test database. Each test
builds its own request, properties and offers, and every run is narrowed to
that test's properties (`property_ids`), so no test sees another's rows.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.matching import canonical, criteria, explain, gates, snapshots
from turab.matching.candidates import Excluded, Exclusion
from turab.matching.eligibility import Eligibility
from turab.matching.hard_gate import CriterionResult, classify
from turab.services import matching_run

VERSION = "0.2.0"
NEXT = gates.next_action_v1


@pytest.fixture
def client(engine):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink()))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _one(engine, sql, **p):
    with engine.begin() as conn:
        return conn.execute(text(sql), p).scalar_one()


def _all(engine, sql, **p):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), p).mappings()]


def _exec(engine, sql, **p):
    with engine.begin() as conn:
        conn.execute(text(sql), p)


def _request(engine, ids, *, intent="BUY", status="ACTIVE", budget_max=30_000_000,
             budget_importance="REQUIRED", confirmed=True, desired_type=None):
    return _one(engine, """
        INSERT INTO turab.requests (party_id, transaction_intent, status, management_mode,
                                    claim_status, budget_max_dzd, budget_importance,
                                    desired_property_type, property_type_importance,
                                    last_confirmed_at)
        VALUES (:p, CAST(:intent AS turab.request_transaction_intent),
                CAST(:status AS turab.request_status), 'ASSISTED', 'UNCLAIMED', :max,
                CAST(:bi AS turab.criterion_importance),
                CAST(:dt AS turab.property_type), 'REQUIRED',
                CASE WHEN :confirmed THEN now() - interval '1 day' END)
        RETURNING request_id""", p=ids.BRAHIM, intent=intent, status=status, max=budget_max,
        bi=budget_importance, dt=desired_type, confirmed=confirmed)


def _criterion(engine, request_id, code, operator, value, importance, sort_order=0,
               blocking_if_unknown=False):
    return _one(engine, """
        INSERT INTO turab.request_criteria (request_id, criterion_code, importance, operator,
                                            value, blocking_if_unknown, sort_order)
        VALUES (:r, :c, CAST(:i AS turab.criterion_importance),
                CAST(:o AS turab.criterion_operator), CAST(:v AS jsonb), :b, :s)
        RETURNING request_criterion_id""", r=request_id, c=code, i=importance, o=operator,
        v=json.dumps(value), b=blocking_if_unknown, s=sort_order)


def _property(engine, *, document="LAND_BOOK", land=400, availability="AVAILABLE",
              confirmed=True):
    prop = _one(engine, """
        INSERT INTO turab.properties (property_type, supply_mode, management_mode, claim_status,
                                      land_area_m2, availability_last_confirmed_at,
                                      current_availability)
        VALUES ('LAND', 'PUBLIC', 'ASSISTED', 'UNCLAIMED', :land,
                CASE WHEN :confirmed THEN now() - interval '1 day' END,
                CAST(:a AS turab.availability_status))
        RETURNING property_id""", land=land, a=availability, confirmed=confirmed)
    if document is not None:
        _exec(engine, """
            INSERT INTO turab.property_attributes (property_id, attribute_definition_id, value)
            SELECT :p, attribute_definition_id, CAST(:v AS jsonb)
              FROM turab.attribute_definitions WHERE code = 'DOCUMENT_TYPE'""",
              p=prop, v=json.dumps(document))
    return prop


def _offer(engine, ids, prop, *, price=20_000_000, negotiable="NO", expectation=None,
           consent=True, transaction="SALE"):
    offer = _one(engine, """
        INSERT INTO turab.property_offers (property_id, party_id, transaction_type, status,
                                           asking_price_dzd, price_negotiable,
                                           seller_expectation_dzd,
                                           commercial_terms_last_confirmed_at)
        VALUES (:p, :party, CAST(:t AS turab.transaction_type), 'ACTIVE', :price,
                CAST(:n AS turab.price_negotiability), :e, now() - interval '1 day')
        RETURNING offer_id""", p=prop, party=ids.BRAHIM, t=transaction, price=price,
        n=negotiable, e=expectation)
    if consent:
        grant = _one(engine, """
            INSERT INTO turab.consent_grants (party_id, scope, channel, consent_version,
                                              granted_at)
            VALUES (:party, 'PRIVATE_MATCHING_ONLY', 'PHONE_CONFIRMED', 'v1',
                    now() - interval '2 days')
            RETURNING consent_id""", party=ids.BRAHIM)
        _exec(engine, """
            INSERT INTO turab.resource_consent_bindings (consent_id, purpose, offer_id, bound_at)
            VALUES (:c, 'PRIVATE_MATCHING_ONLY', :o, now() - interval '1 day')""",
              c=grant, o=offer)
    return offer


def _world(engine, ids, *, document="LAND_BOOK", **offer_kw):
    """An ELIGIBLE candidate by default: BUY, max 30M REQUIRED; REQUIRED
    DOCUMENT_TYPE EQ LAND_BOOK; a fresh LAND property holding LAND_BOOK; one
    fresh ACTIVE SALE offer at 20M, not negotiable, with a current binding."""
    req = _request(engine, ids)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    prop = _property(engine, document=document)
    offer = _offer(engine, ids, prop, **offer_kw)
    return req, prop, offer


def _headers(account, key=None):
    return {"Authorization": f"Bearer {account}", "Idempotency-Key": key or str(uuid.uuid4())}


def _run(client, ids, req, props, *, account=None, key=None, body=None):
    if body is None:
        body = {"matching_policy_version": VERSION, "property_ids": [str(p) for p in props]}
    return client.post(f"/requests/{req}/matching/run",
                       headers=_headers(account or ids.ACC_OPERATOR, key), json=body)


def _ok(response):
    assert response.status_code == 201, response.text
    return response.json()


def _matches(engine, req):
    return _all(engine, """SELECT match_id, property_id, evaluated_offer_id, input_hash,
                                  eligibility::text AS eligibility, generated_by, ai_trace_ref
                             FROM turab.match_candidates WHERE request_id = :r
                            ORDER BY created_at, match_id""", r=req)


def _footprint(engine, req, key=None):
    """Everything a run could write for `req`, and the audit log's high-water
    mark. Equal before and after a refused run (D6)."""
    return {
        "matches": _one(engine, "SELECT count(*) FROM turab.match_candidates "
                                "WHERE request_id = :r", r=req),
        "criteria": _one(engine, """SELECT count(*) FROM turab.match_criterion_results c
                                     JOIN turab.match_candidates m USING (match_id)
                                    WHERE m.request_id = :r""", r=req),
        "diagnostics": _one(engine, "SELECT count(*) FROM turab.match_diagnostic_runs "
                                    "WHERE request_id = :r", r=req),
        "audit": _one(engine, "SELECT coalesce(max(audit_id), 0) FROM turab.audit_log"),
        "idempotency": None if key is None else _one(
            engine, "SELECT count(*) FROM turab.idempotency_records "
                    "WHERE idempotency_key = :k", k=key),
    }


# ======================================================================================
# A run, and what it stores
# ======================================================================================

def test_a_run_stores_each_match_with_its_criteria_audit_and_one_diagnostic(client, ids,
                                                                             engine):
    req, prop, offer = _world(engine, ids)
    audit_before = _one(engine, "SELECT coalesce(max(audit_id), 0) FROM turab.audit_log")
    body = _ok(_run(client, ids, req, [prop]))
    [match] = body["matches"]
    assert (match["eligibility"], match["property_id"], match["evaluated_offer_id"]) == (
        "ELIGIBLE", str(prop), str(offer))
    for key in ("commercial_context_snapshot", "criteria", "eligibility", "freshness_snapshot",
                "input_hash", "match_id", "matching_policy_id", "matching_policy_version",
                "permission_snapshot", "property_id", "property_snapshot", "request_id",
                "request_snapshot"):
        assert key in match, key
    stored = _matches(engine, req)
    assert [(str(m["match_id"]), m["generated_by"], m["ai_trace_ref"]) for m in stored] == [
        (match["match_id"], "RULE_ENGINE", None)]
    rows = _all(engine, """SELECT criterion_code, ordinal, rule_id, rule_version
                             FROM turab.match_criterion_results WHERE match_id = :m
                            ORDER BY criterion_code, ordinal""", m=match["match_id"])
    assert [(r["criterion_code"], r["ordinal"]) for r in rows] == [
        ("BUDGET_MAX", 1), ("DOCUMENT_TYPE", 1), ("TRANSACTION_INTENT", 1)]
    assert set(match["explanation"]["criteria"]) == {"BUDGET_MAX#1", "DOCUMENT_TYPE#1",
                                                     "TRANSACTION_INTENT#1"}
    audited = _all(engine, """SELECT entity_table, entity_id, action, actor_account_id,
                                     context->>'operation' AS operation
                                FROM turab.audit_log WHERE audit_id > :a
                                 AND entity_table LIKE 'match%'""", a=audit_before)
    tables = sorted(a["entity_table"] for a in audited)
    assert tables == ["match_candidates", "match_criterion_results", "match_criterion_results",
                      "match_criterion_results", "match_diagnostic_runs"]
    assert {(a["action"], a["actor_account_id"], a["operation"]) for a in audited} == {
        ("INSERT", ids.ACC_OPERATOR, "postRequestsRequestIdMatchingRun")}
    diagnostic = body["diagnostic"]
    [row] = _all(engine, """SELECT diagnostic_run_id, run_at, input_hash,
                                   suggested_actions, relaxation_scenarios
                              FROM turab.match_diagnostic_runs WHERE request_id = :r""", r=req)
    assert diagnostic["diagnostic_run_id"] == str(row["diagnostic_run_id"])
    assert (row["suggested_actions"], row["relaxation_scenarios"]) == ([], [])
    assert (diagnostic["ready_opportunity_count"], diagnostic["actionable_unknown_count"],
            diagnostic["near_match_count"]) == (1, 0, 0)
    assert _one(engine, "SELECT evaluated_at FROM turab.match_candidates WHERE match_id = :m",
                m=match["match_id"]) == row["run_at"]


def _exact(text_):
    """JSON read with every non-integer number as Decimal (never a float)."""
    return json.loads(text_, parse_float=Decimal)


def _stored_match(engine, match_id):
    """The stored match and its criterion rows, from their jsonb TEXT, read
    independently of `match_view` (review of bf052f4, R-S4-7-03)."""
    row = _one(engine, """SELECT (to_jsonb(m) - 'generated_by' - 'ai_trace_ref'
                                  - 'created_at')::text
                             FROM turab.match_candidates m WHERE match_id = :m""",
               m=match_id)
    criteria_rows = _all(engine, """
        SELECT (to_jsonb(c) - 'match_id' - 'match_criterion_result_id' - 'created_at')::text
               AS t
          FROM turab.match_criterion_results c WHERE match_id = :m""", m=match_id)
    stored = _exact(row)
    stored["criteria"] = sorted((_exact(r["t"]) for r in criteria_rows),
                                key=lambda c: (c["criterion_code"], c["ordinal"]))
    return stored


def test_the_response_is_the_stored_rows(client, ids, engine):
    """The raw response body, read with Decimal, equals the stored rows'
    jsonb text, read with Decimal. `match_view` is not used on either side."""
    req, prop, _ = _world(engine, ids)
    raw = _run(client, ids, req, [prop])
    assert raw.status_code == 201, raw.text
    [match] = _exact(raw.text)["matches"]
    match["criteria"] = sorted(match["criteria"],
                               key=lambda c: (c["criterion_code"], c["ordinal"]))
    assert match == _stored_match(engine, match["match_id"])


def test_the_run_reads_one_repeatable_read_snapshot(client, ids, engine, monkeypatch):
    """Condition 1. Every statement of the run sees one snapshot: the
    transaction is REPEATABLE READ when the candidates are evaluated."""
    req, prop, _ = _world(engine, ids)
    seen = []
    original = matching_run.evaluate

    def spy(session, prepared, candidate):
        seen.append(session.execute(text("SHOW transaction_isolation")).scalar_one())
        return original(session, prepared, candidate)

    monkeypatch.setattr(matching_run, "evaluate", spy)
    _ok(_run(client, ids, req, [prop]))
    assert seen == ["repeatable read"]


def test_the_run_refuses_a_transaction_that_is_not_repeatable_read(session, ids):
    """The guard behind condition 1: `prepare` refuses Read Committed, the
    server default, which the test fixture's transaction uses."""
    with pytest.raises(matching_run.NotRepeatableRead):
        matching_run.prepare(session, ids.REQ_AMINA, matching_policy_version=VERSION,
                             property_ids=[])


def test_an_isolation_outside_the_closed_set_is_refused(engine, ids):
    from turab.db.session import audited_transaction

    with Session(bind=engine, future=True) as s:
        with pytest.raises(ValueError):
            with audited_transaction(s, ids.ACC_OPERATOR, isolation="SERIALIZABLE; --"):
                pass


def test_the_stored_hash_is_recomputed_from_the_stored_snapshots(client, ids, engine):
    """G4-13, condition 2: the hash covers the five stored snapshots, the
    policy, the registry digest and the evaluated offer."""
    from turab.matching.registry import REGISTRY

    req, prop, offer = _world(engine, ids)
    [match] = _ok(_run(client, ids, req, [prop]))["matches"]
    [row] = _all(engine, """
        SELECT matching_policy_id, matching_policy_version, evaluated_offer_id, input_hash,
               request_snapshot::text AS rs, property_snapshot::text AS ps,
               commercial_context_snapshot::text AS cs, permission_snapshot::text AS perm,
               freshness_snapshot::text AS fs
          FROM turab.match_candidates WHERE match_id = :m""", m=match["match_id"])
    assert row["input_hash"] == canonical.input_hash(
        matching_policy_id=row["matching_policy_id"],
        matching_policy_version=row["matching_policy_version"],
        rule_registry_digest=REGISTRY.digest(), evaluated_offer_id=row["evaluated_offer_id"],
        request_snapshot=snapshots.exact_json(row["rs"]),
        property_snapshot=snapshots.exact_json(row["ps"]),
        commercial_context_snapshot=snapshots.exact_json(row["cs"]),
        permission_snapshot=snapshots.exact_json(row["perm"]),
        freshness_snapshot=snapshots.exact_json(row["fs"]))
    assert row["evaluated_offer_id"] == offer


def test_an_identical_rerun_returns_the_existing_match_and_writes_no_second(client, ids,
                                                                            engine):
    """G4-13, condition 2: the same input is the same match. The second run
    writes its own diagnostic row (D1: one per run) and nothing else."""
    req, prop, _ = _world(engine, ids)
    first = _ok(_run(client, ids, req, [prop]))
    audit = _one(engine, "SELECT coalesce(max(audit_id), 0) FROM turab.audit_log")
    second = _ok(_run(client, ids, req, [prop]))
    assert second["matches"] == first["matches"]
    assert len(_matches(engine, req)) == 1
    assert _one(engine, "SELECT count(*) FROM turab.match_diagnostic_runs WHERE request_id = :r",
                r=req) == 2
    assert [r["entity_table"] for r in _all(
        engine, "SELECT entity_table FROM turab.audit_log WHERE audit_id > :a "
                "AND entity_table LIKE 'match%'", a=audit)] == ["match_diagnostic_runs"]


def test_a_changed_input_is_a_new_match(client, ids, engine):
    """The offer's price changes: a new input, so a new match beside the old
    one, which is immutable and unchanged."""
    req, prop, offer = _world(engine, ids)
    [old] = _ok(_run(client, ids, req, [prop]))["matches"]
    _exec(engine, "UPDATE turab.property_offers SET asking_price_dzd = 21000000 "
                  "WHERE offer_id = :o", o=offer)
    [new] = _ok(_run(client, ids, req, [prop]))["matches"]
    assert new["match_id"] != old["match_id"] and new["input_hash"] != old["input_hash"]
    assert new["offer_version"] == old["offer_version"] + 1
    assert new["commercial_context_snapshot"]["asking_price_dzd"] == 21_000_000
    with engine.connect() as conn:
        assert matching_run.match_view(conn, uuid.UUID(old["match_id"])) == old


def test_two_offers_on_identical_terms_are_two_matches(client, ids, engine):
    """Condition 2 (ADR-01): the evaluated offer is an input of the hash, so
    two offers on identical terms are two candidates and two matches."""
    req, prop, first = _world(engine, ids)
    second = _offer(engine, ids, prop)
    body = _ok(_run(client, ids, req, [prop]))
    assert sorted(m["evaluated_offer_id"] for m in body["matches"]) == sorted(
        [str(first), str(second)])
    assert len({m["input_hash"] for m in body["matches"]}) == 2
    assert len(_matches(engine, req)) == 2


def test_every_version_used_is_stored_and_no_version_1_rule_is_cited(client, ids, engine):
    """Conditions 3 and 5. Each criterion row names the rule version that
    produced it, which is the one `criteria.RULES` selects; the explanation
    names every pinned function the run executed. No stored row cites a
    version 1 of location, area_min, attribute_option or count_min (G4-2's
    limit: those are not replay evidence)."""
    req, prop, _ = _world(engine, ids)
    _criterion(engine, req, "LAND_AREA_MIN", "GTE", 300, "PREFERRED", sort_order=1)
    [match] = _ok(_run(client, ids, req, [prop]))["matches"]
    from turab.matching.registry import REGISTRY
    registry_digest = REGISTRY.digest
    expected = {code: f"{rid}@{ver}" for code, (rid, ver, _) in criteria.RULES.items()}
    for c in match["criteria"]:
        assert f"{c['rule_id']}@{c['rule_version']}" == expected[c["criterion_code"]]
    assert match["explanation"]["engine"] == {
        "freshness_state": "freshness.state@1", "permission_binding_state":
        "permission.binding_state@1", "freshness_gate": "freshness.gate@1",
        "permission_gate": "permission.gate@1", "precedence": "eligibility.precedence@1",
        "soft_score": "score.soft@2", "next_action": "action.next@1",
        "registry_digest": registry_digest()}
    assert _one(engine, """SELECT count(*) FROM turab.match_criterion_results
                            WHERE rule_version = '1' AND rule_id IN (
                                'criterion.location', 'criterion.area_min',
                                'criterion.attribute_option', 'criterion.count_min')""") == 0


def test_the_run_changes_no_request_property_offer_consent_or_criterion(client, ids, engine):
    """Acceptance condition 7: row digests before and after."""
    req, prop, offer = _world(engine, ids)

    def digest():
        return _one(engine, """
            SELECT md5(string_agg(t, '|' ORDER BY t)) FROM (
              SELECT to_jsonb(r)::text AS t FROM turab.requests r WHERE request_id = :r
              UNION ALL SELECT to_jsonb(c)::text FROM turab.request_criteria c
                         WHERE request_id = :r
              UNION ALL SELECT to_jsonb(p)::text FROM turab.properties p WHERE property_id = :p
              UNION ALL SELECT to_jsonb(a)::text FROM turab.property_attributes a
                         WHERE property_id = :p
              UNION ALL SELECT to_jsonb(o)::text FROM turab.property_offers o WHERE offer_id = :o
              UNION ALL SELECT to_jsonb(b)::text FROM turab.resource_consent_bindings b
                         WHERE offer_id = :o
              UNION ALL SELECT to_jsonb(g)::text FROM turab.consent_grants g
                         JOIN turab.resource_consent_bindings b USING (consent_id)
                         WHERE b.offer_id = :o) x""", r=req, p=prop, o=offer)

    before = digest()
    _ok(_run(client, ids, req, [prop]))
    assert digest() == before


def test_no_review_opportunity_or_task_is_written(client, ids, engine):
    """D1: the run writes only the three match tables and their audit rows."""
    req, prop, _ = _world(engine, ids, consent=False)

    def counts():
        return [_one(engine, f"SELECT count(*) FROM turab.{t}")
                for t in ("match_reviews", "opportunities", "tasks")]

    before = counts()
    body = _ok(_run(client, ids, req, [prop]))
    assert body["matches"][0]["next_action"] is not None  # a recommendation only
    assert counts() == before
    assert (body["diagnostic"]["suggested_actions"],
            body["diagnostic"]["relaxation_scenarios"]) == ([], [])


def test_no_candidate_is_a_valid_run(client, ids, engine):
    """G06 (mandatory test 10, its run half): an empty candidate set is a 201
    with no match and a diagnostic row."""
    req = _request(engine, ids)
    body = _ok(_run(client, ids, req, []))
    assert body["matches"] == []
    assert (body["diagnostic"]["ready_opportunity_count"],
            body["diagnostic"]["actionable_unknown_count"],
            body["diagnostic"]["near_match_count"]) == (0, 0, 0)
    assert body["diagnostic"]["blocker_summary"]["candidates_evaluated"] == 0
    assert _one(engine, "SELECT count(*) FROM turab.match_diagnostic_runs WHERE request_id = :r",
                r=req) == 1


# ======================================================================================
# D2, D3, D3b: the diagnostic
# ======================================================================================

def test_the_counts_take_each_candidate_once_in_each(client, ids, engine):
    """D3 over one run. Five properties:
    - ELIGIBLE                                     → ready;
    - document not recorded (REQUIRED UNKNOWN)     → actionable unknown;
    - wrong document, all else PASS                → near match (D2);
    - wrong document AND budget exceeded           → REJECTED, two FAILs: none;
    - wrong document AND area not recorded on a REQUIRED minimum → REJECTED,
      one FAIL and one REQUIRED UNKNOWN: not a near match (D2's constraint)."""
    req = _request(engine, ids)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    _criterion(engine, req, "LAND_AREA_MIN", "GTE", 300, "REQUIRED", sort_order=1)
    eligible = _property(engine)
    unknown = _property(engine, document=None)
    near = _property(engine, document="POSSESSION_CERTIFICATE")
    two = _property(engine, document="POSSESSION_CERTIFICATE")
    fail_and_unknown = _property(engine, document="POSSESSION_CERTIFICATE", land=None)
    for p in (eligible, unknown, near, fail_and_unknown):
        _offer(engine, ids, p)
    _offer(engine, ids, two, price=40_000_000)
    body = _ok(_run(client, ids, req, [eligible, unknown, near, two, fail_and_unknown]))
    by_property = {m["property_id"]: m["eligibility"] for m in body["matches"]}
    assert by_property == {str(eligible): "ELIGIBLE", str(unknown): "NEED_MORE_INFORMATION",
                           str(near): "REJECTED", str(two): "REJECTED",
                           str(fail_and_unknown): "REJECTED"}
    d = body["diagnostic"]
    assert (d["ready_opportunity_count"], d["actionable_unknown_count"],
            d["near_match_count"]) == (1, 1, 1)
    stored = _all(engine, """SELECT ready_opportunity_count, actionable_unknown_count,
                                    near_match_count
                               FROM turab.match_diagnostic_runs WHERE request_id = :r""",
                  r=req)
    assert stored == [{"ready_opportunity_count": 1, "actionable_unknown_count": 1,
                       "near_match_count": 1}]
    summary = d["blocker_summary"]
    assert summary["candidates_evaluated"] == 5
    assert summary["by_reason"]["DOCUMENT_MISMATCH"]["candidates"] == 3
    assert summary["by_reason"]["BUDGET_EXCEEDED"]["candidates"] == 1


def _result(code, importance, compatibility, ordinal=1, reason=None, basis="X"):
    return CriterionResult(
        request_criterion_id=None, criterion_code=code, ordinal=ordinal,
        importance=importance, request_value={"source": "ROW"}, property_value=None,
        compatibility=compatibility,
        blocking=importance == "REQUIRED" and compatibility != "PASS", delta=None,
        evidence_level=None, evidence_claim_id=None, reason_code=reason,
        rule_id="criterion.x", rule_version="1", explanation={"basis": basis})


def _verdict(eligibility, reasons=()):
    return Eligibility(eligibility, "PASS", "PASS", "PASS", "PASS", "FRESH", "FRESH", "FRESH",
                       tuple(reasons), {})


@pytest.mark.parametrize("required, eligibility, near", [
    (("FAIL", "PASS", "PASS"), "REJECTED", True),
    (("FAIL",), "REJECTED", True),
    (("FAIL", "UNKNOWN"), "REJECTED", False),      # D2: every other REQUIRED must PASS
    (("FAIL", "FAIL"), "REJECTED", False),
    (("PASS", "PASS"), "ELIGIBLE", False),
    (("UNKNOWN", "PASS"), "NEED_MORE_INFORMATION", False),
])
def test_a_near_match_is_one_required_fail_and_every_other_required_pass(required,
                                                                        eligibility, near):
    results = tuple(_result(f"C{i}", "REQUIRED", c) for i, c in enumerate(required))
    results += (_result("SOFT", "PREFERRED", "FAIL"), _result("SOFT2", "FLEXIBLE", "UNKNOWN"))
    assert explain.is_near_match(classify(results), _verdict(eligibility)) is near


def test_the_blocker_summary_counts_a_candidate_once_per_key():
    """D3b. One candidate with two REQUIRED FAILs whose code is null counts
    once under `HARD:REQUIRED_FAIL`, and once for each criterion. The
    exclusions are listed separately, with their reasons and ids."""
    both = _verdict("REJECTED", [
        {"gate": "HARD", "criterion": "ROOMS_MIN", "ordinal": 1, "reason_code": None,
         "basis": "REQUIRED_FAIL"},
        {"gate": "HARD", "criterion": "ROOMS_MIN", "ordinal": 2, "reason_code": None,
         "basis": "REQUIRED_FAIL"},
        {"gate": "FRESHNESS", "subject": "REQUEST", "reason_code": None,
         "basis": "NEVER_CONFIRMED"},
        {"gate": "PERMISSION", "subject": "OFFER", "reason_code": "PERMISSION_MISSING",
         "basis": "NO_CURRENT_BINDING", "next_action": "CONFIRM_PERMISSION"}])
    one = _verdict("REJECTED", [
        {"gate": "HARD", "criterion": "ROOMS_MIN", "ordinal": 1, "reason_code": None,
         "basis": "REQUIRED_FAIL"}])
    gone = uuid.uuid4()
    alias, canonical_id = uuid.uuid4(), uuid.uuid4()
    summary = explain.blocker_summary([both, one], [
        Excluded(gone, Exclusion.PROPERTY_NOT_FOUND),
        Excluded(alias, Exclusion.IDENTITY_ALIAS, {"canonical_property_id": canonical_id})])
    assert summary["candidates_evaluated"] == 2
    hard = summary["by_reason"]["HARD:REQUIRED_FAIL"]
    assert hard["candidates"] == 2
    assert hard["criteria"] == {"ROOMS_MIN#1": 2, "ROOMS_MIN#2": 1}
    assert summary["by_reason"]["FRESHNESS:NEVER_CONFIRMED"]["candidates"] == 1
    permission = summary["by_reason"]["PERMISSION_MISSING"]
    assert permission["bases"] == {"NO_CURRENT_BINDING": 1}
    assert permission["wording"] == {
        "NO_CURRENT_BINDING": explain.PERMISSION_WORDING["NO_CURRENT_BINDING"]}
    assert summary["excluded"] == [
        {"property_id": str(gone), "reason": "PROPERTY_NOT_FOUND", "detail": {}},
        {"property_id": str(alias), "reason": "IDENTITY_ALIAS",
         "detail": {"canonical_property_id": str(canonical_id)}}]
    assert summary["excluded_counts"] == {"PROPERTY_NOT_FOUND": 1, "IDENTITY_ALIAS": 1}


def test_the_run_reports_its_exclusions_with_ids(client, ids, engine):
    """G4-8 through D3b: an unavailable property and an unknown id are not
    candidates, and the diagnostic names each, with its reason."""
    req, prop, _ = _world(engine, ids)
    unavailable = _property(engine, availability="UNAVAILABLE")
    _offer(engine, ids, unavailable)
    unknown = uuid.uuid4()
    body = _ok(_run(client, ids, req, [prop, unavailable, unknown]))
    assert [m["property_id"] for m in body["matches"]] == [str(prop)]
    excluded = {e["property_id"]: e["reason"]
                for e in body["diagnostic"]["blocker_summary"]["excluded"]}
    assert excluded == {str(unavailable): "PROPERTY_UNAVAILABLE",
                        str(unknown): "PROPERTY_NOT_FOUND"}


def test_permission_missing_is_worded_from_its_basis(client, ids, engine):
    """Condition 4 (review of a5ea6f5): the seeded label of PERMISSION_MISSING
    is never the displayed explanation; the basis is, in the match and in the
    diagnostic. The reason stays visible under NEEDS_CONFIRMATION (G4-11)."""
    req, prop, offer = _world(engine, ids, consent=False)
    body = _ok(_run(client, ids, req, [prop]))
    [match] = body["matches"]
    assert match["eligibility"] == "NEEDS_CONFIRMATION"
    [reason] = [r for r in match["explanation"]["reasons"] if r["gate"] == "PERMISSION"]
    assert (reason["reason_code"], reason["basis"]) == ("PERMISSION_MISSING",
                                                        "NO_CURRENT_BINDING")
    assert reason["wording"] == explain.PERMISSION_WORDING["NO_CURRENT_BINDING"]
    label = _one(engine, "SELECT label_en FROM turab.reason_codes WHERE code = "
                         "'PERMISSION_MISSING'")
    text_of = canonical.canonical_bytes([match["explanation"], match["next_action"],
                                         body["diagnostic"]]).decode()
    assert label not in text_of
    entry = body["diagnostic"]["blocker_summary"]["by_reason"]["PERMISSION_MISSING"]
    assert entry["wording"] == {"NO_CURRENT_BINDING":
                                explain.PERMISSION_WORDING["NO_CURRENT_BINDING"]}
    assert match["next_action"] == {
        "type": "CONFIRM_PERMISSION", "priority": "NORMAL",
        "subject": {"entity": "PROPERTY_OFFER", "id": str(offer), "gate": "PERMISSION",
                    "reason_code": "PERMISSION_MISSING", "basis": "NO_CURRENT_BINDING"}}


def test_every_permission_basis_has_a_wording():
    """A basis `permission.gate@1` can emit, read from its source."""
    import inspect
    source = inspect.getsource(gates.permission_gate_v1)
    for basis in ("NO_CURRENT_BINDING", "NOT_STARTED", "ONLY_REVOKED_BINDINGS"):
        assert f'"{basis}"' in source
        assert basis in explain.PERMISSION_WORDING


# ======================================================================================
# D4: the explanation
# ======================================================================================

def test_the_explanation_never_states_the_seller_expectation(client, ids, engine):
    """D4, R9.3, mandatory deliverable 5's other half. The asking price is
    above the maximum and the expectation below it, so the price criterion
    PASSES on the expectation alone. Neither the field nor its value appears
    in the explanation, the next action or the diagnostic."""
    req, prop, _ = _world(engine, ids, price=35_000_000, expectation=27_777_777)
    body = _ok(_run(client, ids, req, [prop]))
    [match] = body["matches"]
    assert match["eligibility"] == "ELIGIBLE"
    budget = [c for c in match["criteria"] if c["criterion_code"] == "BUDGET_MAX"]
    assert budget[0]["compatibility"] == "PASS"
    written = canonical.canonical_bytes([match["explanation"], match["next_action"],
                                         body["diagnostic"]]).decode()
    assert "seller_expectation" not in written and "27777777" not in written


def test_the_explanation_carries_nothing_taken_from_a_claim(client, ids, engine):
    """D4: the claim behind a criterion is cited by its row
    (`evidence_claim_id`, `evidence_level`), never by the explanation."""
    req = _request(engine, ids)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    prop = _property(engine, document=None)
    claim = _one(engine, """
        INSERT INTO turab.claims (property_id, attribute_code, claimed_value,
                                  effective_verification_level)
        VALUES (:p, 'DOCUMENT_TYPE', '"LAND_BOOK"', 'DOCUMENT_SEEN') RETURNING claim_id""",
        p=prop)
    _exec(engine, """
        INSERT INTO turab.property_attributes (property_id, attribute_definition_id, value,
                                               resolved_claim_id)
        SELECT :p, attribute_definition_id, '"LAND_BOOK"', :c
          FROM turab.attribute_definitions WHERE code = 'DOCUMENT_TYPE'""", p=prop, c=claim)
    _offer(engine, ids, prop)
    [match] = _ok(_run(client, ids, req, [prop]))["matches"]
    [document] = [c for c in match["criteria"] if c["criterion_code"] == "DOCUMENT_TYPE"]
    assert (document["evidence_claim_id"], document["evidence_level"]) == (
        str(claim), "DOCUMENT_SEEN")
    written = canonical.canonical_bytes([match["explanation"], match["next_action"]]).decode()
    assert str(claim) not in written and "claimed_value" not in written


# ======================================================================================
# D5: next_action
# ======================================================================================

SUBJECTS = {"REQUEST": "r", "PROPERTY": "p", "PROPERTY_OFFER": "o"}


def _u(code, importance="REQUIRED", basis="ATTRIBUTE_NOT_RECORDED", ordinal=1, reason=None):
    return {"criterion": code, "ordinal": ordinal, "request_criterion_id": None,
            "importance": importance, "reason_code": reason, "basis": basis}


FRESH_REQUEST = {"gate": "FRESHNESS", "subject": "REQUEST", "reason_code": "REQUEST_STALE",
                 "basis": "STALE"}
FRESH_PROPERTY = {"gate": "FRESHNESS", "subject": "PROPERTY", "reason_code": None,
                  "basis": "NEVER_CONFIRMED"}
FRESH_OFFER = {"gate": "FRESHNESS", "subject": "OFFER", "reason_code": "OFFER_STALE",
               "basis": "STALE"}
PERMISSION = {"gate": "PERMISSION", "subject": "OFFER", "reason_code": "PERMISSION_MISSING",
              "basis": "NO_CURRENT_BINDING", "next_action": "CONFIRM_PERMISSION"}


@pytest.mark.parametrize("eligibility", ["ELIGIBLE", "REJECTED"])
def test_there_is_no_next_action_for_eligible_or_rejected(eligibility):
    assert NEXT(eligibility, [_u("DOCUMENT_TYPE")], [FRESH_REQUEST], [PERMISSION],
                SUBJECTS) is None


@pytest.mark.parametrize("unknown, kind, entity", [
    (_u("DOCUMENT_TYPE", reason="DOCUMENT_NOT_KNOWN"), "VERIFY_DOCUMENT", "PROPERTY"),
    (_u("RIGHT_TYPE"), "VERIFY_DOCUMENT", "PROPERTY"),
    (_u("BUDGET_MAX", basis="BUDGET_MAX_NOT_STATED"), "CONFIRM_PRICE", "REQUEST"),
    (_u("BUDGET_MAX", basis="PRICE_NOT_KNOWN", reason="PRICE_NOT_KNOWN"), "CONFIRM_PRICE",
     "PROPERTY_OFFER"),
    (_u("BUDGET_MAX", basis="PRICE_ABOVE_MAX_NEGOTIATION_UNCONFIRMED",
        reason="PRICE_NEGOTIATION_UNCONFIRMED"), "CONFIRM_PRICE", "PROPERTY_OFFER"),
    (_u("LAND_AREA_MIN", basis="AREA_NOT_RECORDED"), "OTHER", "PROPERTY"),
    (_u("CUSTOM_ATTRIBUTE", importance="PREFERRED", basis="NO_DETERMINISTIC_RULE"), "OTHER",
     "REQUEST"),
])
def test_an_actionable_unknown_gives_a_high_priority_information_action(unknown, kind,
                                                                        entity):
    action = NEXT("NEED_MORE_INFORMATION", [unknown], [FRESH_REQUEST], [PERMISSION], SUBJECTS)
    assert action == {"type": kind, "priority": "HIGH", "subject": {
        "entity": entity, "id": SUBJECTS[entity], "gate": "INFORMATION",
        "criterion": unknown["criterion"], "ordinal": 1, "request_criterion_id": None,
        "reason_code": unknown["reason_code"], "basis": unknown["basis"]}}


def test_the_information_tie_break_is_required_first_then_evaluation_order():
    soft = _u("BEDROOMS_MIN", importance="PREFERRED")
    first, second = _u("RIGHT_TYPE"), _u("DOCUMENT_TYPE")
    assert NEXT("NEED_MORE_INFORMATION", [soft, first, second], [], [],
                SUBJECTS)["subject"]["criterion"] == "RIGHT_TYPE"
    assert NEXT("NEED_MORE_INFORMATION", [soft, second, first], [], [],
                SUBJECTS)["subject"]["criterion"] == "DOCUMENT_TYPE"
    assert NEXT("NEED_MORE_INFORMATION", [soft], [], [],
                SUBJECTS)["subject"]["criterion"] == "BEDROOMS_MIN"


@pytest.mark.parametrize("freshness, kind, entity", [
    ([FRESH_OFFER, FRESH_PROPERTY, FRESH_REQUEST], "RECONFIRM_REQUEST", "REQUEST"),
    ([FRESH_OFFER, FRESH_PROPERTY], "RECONFIRM_PROPERTY", "PROPERTY"),
    ([FRESH_OFFER], "CONFIRM_PRICE", "PROPERTY_OFFER"),
])
def test_reconfirmation_comes_before_permission_in_a_fixed_order(freshness, kind, entity):
    action = NEXT("NEEDS_CONFIRMATION", [], freshness, [PERMISSION], SUBJECTS)
    assert (action["type"], action["priority"], action["subject"]["entity"],
            action["subject"]["id"]) == (kind, "NORMAL", entity, SUBJECTS[entity])


def test_permission_is_last():
    action = NEXT("NEEDS_CONFIRMATION", [], [], [PERMISSION], SUBJECTS)
    assert (action["type"], action["priority"], action["subject"]["gate"]) == (
        "CONFIRM_PERMISSION", "NORMAL", "PERMISSION")
    assert NEXT("NEEDS_CONFIRMATION", [], [], [], SUBJECTS) is None


def test_every_type_is_a_task_type_of_the_contract():
    import yaml
    from tests.conftest import REPO_ROOT

    doc = yaml.safe_load((REPO_ROOT / "docs" / "api" / "openapi_effective_v0.2.3.yaml")
                         .read_text(encoding="utf-8"))
    task_types = set(doc["components"]["schemas"]["Task"]["properties"]["task_type"]["enum"])
    import inspect
    source = inspect.getsource(gates.next_action_v1)
    emitted = {t for t in task_types | {"VERIFY_DOCUMENT", "CONFIRM_PRICE", "OTHER",
                                        "RECONFIRM_REQUEST", "RECONFIRM_PROPERTY",
                                        "CONFIRM_PERMISSION"} if f'"{t}"' in source}
    assert emitted == {"VERIFY_DOCUMENT", "CONFIRM_PRICE", "OTHER", "RECONFIRM_REQUEST",
                       "RECONFIRM_PROPERTY", "CONFIRM_PERMISSION"}
    assert emitted <= task_types


def test_a_missing_document_gives_verify_document_on_the_property(client, ids, engine):
    req, prop, _ = _world(engine, ids, document=None)
    [match] = _ok(_run(client, ids, req, [prop]))["matches"]
    assert match["eligibility"] == "NEED_MORE_INFORMATION"
    request_criterion_id = _one(engine, "SELECT request_criterion_id FROM "
                                        "turab.request_criteria WHERE request_id = :r", r=req)
    assert match["next_action"] == {"type": "VERIFY_DOCUMENT", "priority": "HIGH", "subject": {
        "entity": "PROPERTY", "id": str(prop), "gate": "INFORMATION",
        "criterion": "DOCUMENT_TYPE", "ordinal": 1,
        "request_criterion_id": str(request_criterion_id),
        "reason_code": "DOCUMENT_NOT_KNOWN", "basis": "ATTRIBUTE_NOT_RECORDED"}}


def test_an_eligible_candidate_has_no_next_action(client, ids, engine):
    req, prop, _ = _world(engine, ids)
    [match] = _ok(_run(client, ids, req, [prop]))["matches"]
    assert (match["eligibility"], match["next_action"]) == ("ELIGIBLE", None)


# ======================================================================================
# D6: a refused run writes nothing; CORRECTION-004 at run time
# ======================================================================================

def _refused(client, ids, engine, req, body, status, code, props=()):
    key = str(uuid.uuid4())
    before = _footprint(engine, req, key)
    r = _run(client, ids, req, props, key=key, body=body)
    assert (r.status_code, r.json()["code"]) == (status, code), r.text
    assert _footprint(engine, req, key) == before
    assert before["idempotency"] == 0
    return r, key


@pytest.mark.parametrize("label, body", [
    ("omitted", {}),
    ("null", {"matching_policy_version": None}),
    ("unknown", {"matching_policy_version": "9.9.9-unknown"}),
    ("the frozen default", {"matching_policy_version": "0.1.0"}),
    ("not a string", {"matching_policy_version": 2}),
])
def test_correction_004_refuses_any_version_but_the_active_one(client, ids, engine, label,
                                                              body):
    """CORRECTION-004's runtime rule: 422, the value not echoed, nothing
    written, the key not consumed (the same key then serves a valid run)."""
    req, prop, _ = _world(engine, ids)
    r, key = _refused(client, ids, engine, req, body, 422, "MATCHING_POLICY_VERSION_REFUSED")
    if isinstance(body.get("matching_policy_version"), str):
        assert body["matching_policy_version"] not in r.text
    _ok(_run(client, ids, req, [prop], key=key))


def test_correction_004_refuses_an_inactive_policys_version(client, ids, engine):
    req, prop, _ = _world(engine, ids)
    version = f"0.0.{uuid.uuid4().int % 10**9}-inactive"
    policy = _one(engine, """INSERT INTO turab.matching_policies (version, name, rules, active)
                             VALUES (:v, 'inactive test policy', '{}'::jsonb, false)
                             RETURNING matching_policy_id""", v=version)
    try:
        r, _ = _refused(client, ids, engine, req, {"matching_policy_version": version}, 422,
                        "MATCHING_POLICY_VERSION_REFUSED")
        assert version not in r.text
    finally:
        _exec(engine, "DELETE FROM turab.matching_policies WHERE matching_policy_id = :p",
              p=policy)


@pytest.mark.parametrize("status", ["PAUSED", "CLOSED", "RAW", "QUALIFIED"])
def test_a_request_status_a_run_does_not_accept_is_409(client, ids, engine, status):
    """G4-8, D6: 409, nothing written."""
    req = _request(engine, ids, status="ACTIVE")
    try:
        _exec(engine, "UPDATE turab.requests SET status = CAST(:s AS turab.request_status) "
                      "WHERE request_id = :r", s=status, r=req)
    except Exception as exc:  # a status the schema guards needs its own fields
        pytest.skip(f"{status} cannot be set directly here: {type(exc).__name__}")
    _refused(client, ids, engine, req, {"matching_policy_version": VERSION}, 409,
             "REQUEST_NOT_MATCHABLE")


def test_a_rent_request_is_refused(client, ids, engine):
    """Condition 7, G4-5R: a RENT run is refused, with or without a budget."""
    for budget in (30_000_000, None):
        req = _request(engine, ids, intent="RENT", budget_max=budget)
        r, _ = _refused(client, ids, engine, req, {"matching_policy_version": VERSION}, 422,
                        "MATCHING_INPUT_REFUSED")
        assert r.json()["detail"].startswith("G4-5R")


@pytest.mark.parametrize("label, rows, rule", [
    ("G4-7: no property value can pass",
     [("DOCUMENT_TYPE", "EQ", "UNKNOWN", "REQUIRED")], "G4-7"),
    ("G4-7: an operator the code does not take",
     [("LAND_AREA_MIN", "EQ", 300, "REQUIRED")], "G4-7"),
    ("G4-3 (b): disjoint from the REQUIRED column",
     [("PROPERTY_TYPE", "EQ", "APARTMENT", "REQUIRED")], "G4-3"),
])
def test_a_criterion_the_run_cannot_take_is_422(client, ids, engine, label, rows, rule):
    req = _request(engine, ids, desired_type="HOUSE_VILLA")
    for i, (code, op, value, importance) in enumerate(rows):
        _criterion(engine, req, code, op, value, importance, sort_order=i)
    r, _ = _refused(client, ids, engine, req, {"matching_policy_version": VERSION}, 422,
                    "MATCHING_INPUT_REFUSED")
    assert r.json()["detail"].startswith(rule)


def test_an_unknown_request_is_404_and_writes_nothing(client, ids, engine):
    _refused(client, ids, engine, uuid.uuid4(), {"matching_policy_version": VERSION}, 404,
             "NOT_FOUND")


def test_the_version_is_checked_before_the_request(client, ids, engine):
    """The refusals are decided in a fixed order: the version first, so a
    wrong version is 422 whatever the request."""
    req = _request(engine, ids, status="PAUSED")
    _refused(client, ids, engine, req, {"matching_policy_version": "x"}, 422,
             "MATCHING_POLICY_VERSION_REFUSED")


def test_an_identical_call_replays_and_writes_nothing_more(client, ids, engine):
    req, prop, _ = _world(engine, ids)
    key = str(uuid.uuid4())
    first = _ok(_run(client, ids, req, [prop], key=key))
    before = _footprint(engine, req, key)
    again = _ok(_run(client, ids, req, [prop], key=key))
    assert again == first
    assert _footprint(engine, req, key) == before


def test_a_replay_is_returned_even_after_the_request_stopped_being_matchable(client, ids,
                                                                           engine):
    """The refusals are decided AFTER the replay lookup: an identical call
    with the same key returns its stored result, as §2.3 promises."""
    req, prop, _ = _world(engine, ids)
    key = str(uuid.uuid4())
    first = _ok(_run(client, ids, req, [prop], key=key))
    _exec(engine, "UPDATE turab.requests SET status = 'PAUSED' WHERE request_id = :r", r=req)
    assert _ok(_run(client, ids, req, [prop], key=key)) == first


def test_a_customer_cannot_run_matching(client, ids, engine):
    req, prop, _ = _world(engine, ids)
    r = _run(client, ids, req, [prop], account=ids.ACC_AMINA)
    assert r.status_code == 403
    assert _matches(engine, req) == []


@pytest.mark.parametrize("account", ["ACC_OPERATOR", "ACC_REVIEWER", "ACC_ADMIN"])
def test_each_staff_role_of_the_contract_may_run(client, ids, engine, account):
    req, prop, _ = _world(engine, ids)
    _ok(_run(client, ids, req, [prop], account=getattr(ids, account)))


def test_an_undeclared_body_field_is_accepted_and_changes_nothing(client, ids, engine):
    """R-S4-7-01 (review of bf052f4). The contract does not close this body
    (no `additionalProperties: false`), and CORRECTION-004 narrows only
    `matching_policy_version`. An undeclared field is accepted, and it
    changes nothing the run computes: the same input, the same match."""
    req, prop, _ = _world(engine, ids)
    plain = _ok(_run(client, ids, req, [prop]))
    hinted = _ok(_run(client, ids, req, [prop], body={
        "matching_policy_version": VERSION, "property_ids": [str(prop)],
        "future_hint": {"x": 1}}))
    assert hinted["matches"] == plain["matches"]
    assert len(_matches(engine, req)) == 1


def test_an_undeclared_field_is_part_of_the_body_for_idempotency(client, ids, engine):
    """API_CONTRACTS §2.3: the same key with a different body is 409. A body
    that differs only by an undeclared field is a different body."""
    req, prop, _ = _world(engine, ids)
    key = str(uuid.uuid4())
    _ok(_run(client, ids, req, [prop], key=key))
    r = _run(client, ids, req, [prop], key=key, body={
        "matching_policy_version": VERSION, "property_ids": [str(prop)], "future_hint": 1})
    assert (r.status_code, r.json()["code"]) == (409, "IDEMPOTENCY_KEY_CONFLICT")


def test_property_ids_null_is_refused_and_absent_or_empty_keep_their_meaning(
        client, ids, engine, monkeypatch):
    """R-S4-7-01. The contract types `property_ids` as an array, which null is
    not: 422, nothing written. Absent means a full scan (None reaches the
    run); [] means no candidate."""
    req, prop, _ = _world(engine, ids)
    seen = []
    original = matching_run.prepare

    def spy(session, request_id, *, matching_policy_version, property_ids):
        seen.append(property_ids)
        return original(session, request_id, matching_policy_version=matching_policy_version,
                        property_ids=property_ids)

    monkeypatch.setattr(matching_run, "prepare", spy)
    key = str(uuid.uuid4())
    before = _footprint(engine, req, key)
    r = _run(client, ids, req, [], key=key,
             body={"matching_policy_version": VERSION, "property_ids": None})
    assert (r.status_code, r.json()["code"]) == (422, "VALIDATION_FAILED"), r.text
    assert _footprint(engine, req, key) == before and seen == []

    monkeypatch.setattr(matching_run, "execute", lambda session, prepared: (201, {}))
    _ok(_run(client, ids, req, [], body={"matching_policy_version": VERSION}))
    _ok(_run(client, ids, req, [], body={"matching_policy_version": VERSION,
                                         "property_ids": []}))
    assert seen == [None, []]


def test_an_empty_property_list_evaluates_nothing(client, ids, engine):
    req, prop, _ = _world(engine, ids)
    body = _ok(_run(client, ids, req, [], body={"matching_policy_version": VERSION,
                                                 "property_ids": []}))
    assert body["matches"] == [] and _matches(engine, req) == []


# ======================================================================================
# §6.3: concurrency
# ======================================================================================

def _service_run(engine, ids, req, props):
    from turab.db.session import audited_transaction

    with Session(bind=engine, future=True) as s:
        with audited_transaction(s, ids.ACC_OPERATOR, {"operation": "test"},
                                 isolation="REPEATABLE READ"):
            prepared = matching_run.prepare(s, req, matching_policy_version=VERSION,
                                            property_ids=props)
            return matching_run.execute(s, prepared)[1]


def _blocked_by(engine, pids, statement, message):
    """The witness of a race (review of 48588a0): `pids` holds the backend of
    A, then of B, recorded by the test's wrappers. It waits until B's backend
    is waiting on a lock, in `statement`, AND `pg_blocking_pids(B)` names A's
    backend: B waits on A, not merely on something."""
    deadline = time.monotonic() + 30
    while True:
        if len(pids) == 2:
            row = _all(engine, """
                SELECT a.wait_event_type, a.query, :a = ANY(pg_blocking_pids(:b)) AS by_a
                  FROM pg_stat_activity a WHERE a.pid = :b""", a=pids[0], b=pids[1])
            if (row and row[0]["by_a"] and row[0]["wait_event_type"] == "Lock"
                    and statement in row[0]["query"]):
                return
        assert time.monotonic() < deadline, message
        time.sleep(0.05)


def test_two_identical_runs_race_and_store_one_match(engine, ids, monkeypatch):
    """§6.3, first race, with a witness. Run A has inserted its match and not
    committed. Run B, with the identical input, is shown WAITING on A's row
    (pg_stat_activity). A commits; B's insert fails 23505 inside its
    savepoint; the row is invisible in B's snapshot (measured D5), so B reads
    it on a new connection. Both runs succeed, and both return the one
    match."""
    req, prop, _ = _world(engine, ids)
    inserted, release = threading.Event(), threading.Event()
    original = matching_run._insert
    calls, pids = [], []

    def paused(session, prepared, ev):
        # Each run's backend, recorded BEFORE its insert (B's insert blocks).
        pids.append(session.execute(text("SELECT pg_backend_pid()")).scalar_one())
        match_id = original(session, prepared, ev)
        calls.append(match_id)
        if len(calls) == 1:
            inserted.set()
            assert release.wait(30)
        return match_id

    monkeypatch.setattr(matching_run, "_insert", paused)
    stored = []
    original_store = matching_run._store

    def recorded(session, prepared, ev):
        result = original_store(session, prepared, ev)
        stored.append(result)
        return result

    monkeypatch.setattr(matching_run, "_store", recorded)
    out = {}

    def run(name):
        try:
            out[name] = _service_run(engine, ids, req, [prop])
        except Exception as exc:  # reported by the assertions below
            out[name] = exc

    a = threading.Thread(target=run, args=("a",))
    a.start()
    assert inserted.wait(30)
    b = threading.Thread(target=run, args=("b",))
    b.start()
    _blocked_by(engine, pids, "INSERT INTO turab.match_candidates",
                "run B never waited on run A's row")
    release.set()
    a.join(60)
    b.join(60)
    assert not isinstance(out["a"], Exception), out["a"]
    assert not isinstance(out["b"], Exception), out["b"]
    assert out["a"]["matches"] == out["b"]["matches"]
    assert len(calls) == 1
    # A's own insert, visible to A; then B's, found only on a new connection.
    match_id = calls[0]
    assert stored == [(match_id, True), (match_id, False)]
    assert len(_matches(engine, req)) == 1
    assert _one(engine, "SELECT count(*) FROM turab.match_diagnostic_runs WHERE request_id = :r",
                r=req) == 2


def test_a_run_racing_a_price_change_stores_the_state_it_read(engine, ids, monkeypatch):
    """§6.3, second race (measured D7). The run has read its snapshot; the
    offer's price then changes and COMMITS; the run inserts. The insert
    succeeds against the snapshot, and the match records exactly the state
    it read: the old price, the old offer version, and their hash."""
    req, prop, offer = _world(engine, ids)
    old_version = _one(engine, "SELECT version FROM turab.property_offers WHERE offer_id = :o",
                       o=offer)
    reached, release = threading.Event(), threading.Event()
    original = matching_run._store

    def paused(session, prepared, ev):
        reached.set()
        assert release.wait(30)
        return original(session, prepared, ev)

    monkeypatch.setattr(matching_run, "_store", paused)
    out = {}

    def run():
        try:
            out["run"] = _service_run(engine, ids, req, [prop])
        except Exception as exc:
            out["run"] = exc

    t = threading.Thread(target=run)
    t.start()
    assert reached.wait(30)
    _exec(engine, "UPDATE turab.property_offers SET asking_price_dzd = 25000000 "
                  "WHERE offer_id = :o", o=offer)
    release.set()
    t.join(60)
    assert not isinstance(out["run"], Exception), out["run"]
    [match] = out["run"]["matches"]
    assert match["commercial_context_snapshot"]["asking_price_dzd"] == 20_000_000
    assert match["offer_version"] == old_version
    assert _one(engine, "SELECT version FROM turab.property_offers WHERE offer_id = :o",
                o=offer) == old_version + 1
    monkeypatch.setattr(matching_run, "_store", original)
    [after] = _service_run(engine, ids, req, [prop])["matches"]
    assert after["commercial_context_snapshot"]["asking_price_dzd"] == 25_000_000
    assert after["input_hash"] != match["input_hash"]


def test_a_unique_violation_on_another_constraint_is_not_taken_for_an_identical_input():
    """Only the frozen UNIQUE of the match is an identical input; any other
    integrity error propagates."""
    from sqlalchemy.exc import IntegrityError

    class Diag:
        def __init__(self, name):
            self.constraint_name = name

    class Orig(Exception):
        def __init__(self, state, name):
            self.sqlstate, self.diag = state, Diag(name)

    def error(state, name):
        return IntegrityError("stmt", {}, Orig(state, name))

    assert matching_run._identical_input(error("23505", matching_run.IDENTICAL_INPUT))
    assert not matching_run._identical_input(error("23505", "some_other_key"))
    assert not matching_run._identical_input(error("23503", matching_run.IDENTICAL_INPUT))


def test_the_identical_input_constraint_is_named_as_postgresql_names_it(engine):
    names = [r["conname"] for r in _all(engine, """
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'turab.match_candidates'::regclass AND contype = 'u'""")]
    assert names == [matching_run.IDENTICAL_INPUT]


def test_decimal_values_are_stored_exactly(client, ids, engine):
    """The snapshots are written in canonical form: an area with a fraction is
    stored as written, and reads back as the same Decimal."""
    req = _request(engine, ids)
    _criterion(engine, req, "LAND_AREA_MIN", "GTE", 300, "REQUIRED")
    prop = _property(engine, land=Decimal("400.25"))
    _offer(engine, ids, prop)
    [match] = _ok(_run(client, ids, req, [prop]))["matches"]
    stored = _one(engine, "SELECT property_snapshot->>'land_area_m2' FROM "
                          "turab.match_candidates WHERE match_id = :m", m=match["match_id"])
    assert Decimal(stored) == Decimal("400.25")


def _writers(table):
    import re

    from tests.conftest import REPO_ROOT
    pattern = re.compile(rf"INSERT\s+INTO\s+turab\.{table}\b")
    return sorted(str(p.relative_to(REPO_ROOT)) for p in (REPO_ROOT / "src").rglob("*.py")
                  if pattern.search(p.read_text(encoding="utf-8")))


def test_no_path_writes_a_review_or_an_opportunity_and_matching_writes_no_task():
    """Acceptance condition 6 and D1, computed from the tree: neither the run
    nor the matching package inserts into `match_reviews`, `opportunities`
    or `tasks`; the three match tables are written by the run alone.

    Slice 5 step 2 (review of 29a0f30) opened `match_reviews` to the review
    command, and step 3 (review of 60b0152) opened `opportunities` to the
    APPROVED review, as the Slice 5 plan asked. Until then this test required
    NO writer at all; the matching-side claim is unchanged, and the current
    writers are pinned below so that any further one fails here too."""
    run = "src/turab/services/matching_run.py"
    for table in ("match_reviews", "opportunities", "tasks"):
        assert not [w for w in _writers(table)
                    if w == run or w.startswith("src/turab/matching/")], table
    assert _writers("match_reviews") == ["src/turab/services/match_review.py"]
    assert _writers("opportunities") == ["src/turab/services/match_review.py"]
    for table in ("match_candidates", "match_criterion_results", "match_diagnostic_runs"):
        assert _writers(table) == [run], table


@pytest.mark.parametrize("label, setup, body, status", [
    ("unknown version", "world", {"matching_policy_version": "9.9.9"}, 422),
    ("not matchable", "paused", {"matching_policy_version": VERSION}, 409),
    ("RENT", "rent", {"matching_policy_version": VERSION}, 422),
])
def test_a_refusal_is_decided_before_any_write(client, ids, engine, label, setup, body,
                                               status):
    """D6, "before any write", observed and not inferred from a rollback:
    every statement the database receives during a refused call is
    recorded, and none is an INSERT, UPDATE or DELETE. The idempotency claim
    included. A valid call, recorded the same way, does write."""
    from sqlalchemy import event

    if setup == "world":
        req, _, _ = _world(engine, ids)
    elif setup == "paused":
        req = _request(engine, ids, status="PAUSED")
    else:
        req = _request(engine, ids, intent="RENT")
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement.lstrip().split(None, 1)[0].upper())

    event.listen(engine, "before_cursor_execute", record)
    try:
        r = _run(client, ids, req, [], body=body)
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert r.status_code == status, r.text
    assert statements and not {"INSERT", "UPDATE", "DELETE"} & set(statements), statements

    valid, _, _ = _world(engine, ids)
    statements.clear()
    event.listen(engine, "before_cursor_execute", record)
    try:
        _ok(_run(client, ids, valid, []))
    finally:
        event.remove(engine, "before_cursor_execute", record)
    assert "INSERT" in statements


def test_a_soft_unknown_that_does_not_block_gives_no_information_action(client, ids,
                                                                         engine):
    """D5: an information action only for an ACTIONABLE blocking unknown. A
    PREFERRED area minimum on a property with no recorded area is UNKNOWN and
    does not block (G4-4), so the next action is the permission's."""
    req = _request(engine, ids)
    _criterion(engine, req, "LAND_AREA_MIN", "GTE", 300, "PREFERRED")
    prop = _property(engine, land=None)
    _offer(engine, ids, prop, consent=False)
    [match] = _ok(_run(client, ids, req, [prop]))["matches"]
    [area] = [c for c in match["criteria"] if c["criterion_code"] == "LAND_AREA_MIN"]
    assert (area["compatibility"], area["blocking"]) == ("UNKNOWN", False)
    assert match["eligibility"] == "NEEDS_CONFIRMATION"
    assert match["next_action"]["type"] == "CONFIRM_PERMISSION"


# ======================================================================================
# Review of bf052f4: R-S4-7-02, one Idempotency-Key in two concurrent calls (HTTP)
# ======================================================================================

def _same_key_race(client, ids, engine, monkeypatch, req, first_body, second_body):
    """Call A claims the key and is held before it commits; call B, with the
    SAME key, is shown WAITING on A's idempotency row (pg_stat_activity);
    then A is released. Both go through the route, CommandService and
    idempotency: nothing is called directly."""
    from turab.services import idempotency

    claimed, release = threading.Event(), threading.Event()
    original = idempotency.claim
    calls, pids = [], []

    def held(session, **kw):
        # Each call's backend, recorded BEFORE its claim (B's claim blocks).
        pids.append(session.execute(text("SELECT pg_backend_pid()")).scalar_one())
        original(session, **kw)
        calls.append(kw["idempotency_key"])
        if len(calls) == 1:
            claimed.set()
            assert release.wait(30)

    monkeypatch.setattr(idempotency, "claim", held)
    key, out = str(uuid.uuid4()), {}

    def call(name, body):
        try:
            out[name] = client.post(f"/requests/{req}/matching/run",
                                    headers=_headers(ids.ACC_OPERATOR, key), json=body)
        except Exception as exc:  # reported by the assertions
            out[name] = exc

    a = threading.Thread(target=call, args=("a", first_body))
    a.start()
    assert claimed.wait(30)
    b = threading.Thread(target=call, args=("b", second_body))
    b.start()
    _blocked_by(engine, pids, "INSERT INTO turab.idempotency_records",
                "call B never waited on call A's key")
    release.set()
    a.join(60)
    b.join(60)
    return key, out


def test_one_key_and_one_body_in_two_concurrent_calls_return_the_original_result(
        client, ids, engine, monkeypatch):
    """API_CONTRACTS §2.3 under a race: B's claim meets A's committed key,
    which B's Repeatable Read snapshot cannot see. B returns A's stored result
    and runs nothing: one diagnostic row, one idempotency record."""
    req, prop, _ = _world(engine, ids)
    body = {"matching_policy_version": VERSION, "property_ids": [str(prop)]}
    key, out = _same_key_race(client, ids, engine, monkeypatch, req, body, body)
    assert not isinstance(out["a"], Exception), out["a"]
    assert not isinstance(out["b"], Exception), out["b"]
    assert (out["a"].status_code, out["b"].status_code) == (201, 201), out["b"].text
    assert _exact(out["b"].text) == _exact(out["a"].text)
    assert _one(engine, "SELECT count(*) FROM turab.match_diagnostic_runs WHERE request_id = :r",
                r=req) == 1
    assert len(_matches(engine, req)) == 1
    assert _one(engine, "SELECT count(*) FROM turab.idempotency_records "
                        "WHERE idempotency_key = :k", k=key) == 1


def test_one_key_with_another_body_in_a_concurrent_call_is_409(client, ids, engine,
                                                               monkeypatch):
    req, prop, _ = _world(engine, ids)
    key, out = _same_key_race(
        client, ids, engine, monkeypatch, req,
        {"matching_policy_version": VERSION, "property_ids": [str(prop)]},
        {"matching_policy_version": VERSION, "property_ids": []})
    assert not isinstance(out["b"], Exception), out["b"]
    assert out["a"].status_code == 201
    assert (out["b"].status_code, out["b"].json()["code"]) == (409, "IDEMPOTENCY_KEY_CONFLICT")
    assert _one(engine, "SELECT count(*) FROM turab.match_diagnostic_runs WHERE request_id = :r",
                r=req) == 1
    assert _one(engine, "SELECT count(*) FROM turab.idempotency_records "
                        "WHERE idempotency_key = :k", k=key) == 1


# ======================================================================================
# Review of bf052f4: R-S4-7-03, the response and the replay carry the stored numbers
# ======================================================================================

def test_the_response_and_its_replay_carry_the_stored_numbers_exactly(client, ids, engine):
    """The reviewer's case: area 400.25, minimum 0.12345678901234568. The
    stored delta is 400.12654321098765432; a float gives 400.1265432109877.
    The raw body and the replayed raw body, read with Decimal, equal the
    stored jsonb text, read with Decimal; and the numbers stay JSON numbers."""
    req = _request(engine, ids)
    _exec(engine, """
        INSERT INTO turab.request_criteria (request_id, criterion_code, importance, operator,
                                            value, sort_order)
        VALUES (:r, 'LAND_AREA_MIN', 'REQUIRED', 'GTE', '0.12345678901234568'::jsonb, 0)""",
          r=req)
    prop = _property(engine, land=Decimal("400.25"))
    _offer(engine, ids, prop)
    key = str(uuid.uuid4())
    first = _run(client, ids, req, [prop], key=key)
    assert first.status_code == 201, first.text
    [match] = _exact(first.text)["matches"]
    stored_delta = _one(engine, """SELECT delta::text FROM turab.match_criterion_results
                                    WHERE match_id = :m AND criterion_code = 'LAND_AREA_MIN'""",
                        m=match["match_id"])
    assert _exact(stored_delta) == {"m2": Decimal("400.12654321098765432")}
    [area] = [c for c in match["criteria"] if c["criterion_code"] == "LAND_AREA_MIN"]
    assert area["delta"] == {"m2": Decimal("400.12654321098765432")}
    assert '"m2":400.12654321098765432' in first.text.replace(" ", "")
    match["criteria"] = sorted(match["criteria"],
                               key=lambda c: (c["criterion_code"], c["ordinal"]))
    assert match == _stored_match(engine, match["match_id"])
    replay = _run(client, ids, req, [prop], key=key)
    assert replay.status_code == 201
    assert _exact(replay.text) == _exact(first.text)
    assert "400.12654321098765432" in replay.text


# ======================================================================================
# The policy faults of plan §3.1: two typed 500s, a fixed detail, the cause logged
# (review of bf052f4: the typed 500; review of 48588a0: R-S4-7-04)
# ======================================================================================

#: Carried by a test policy's VERSION, which the schema leaves free text:
#: `otp` is a marker the problem-detail guard refuses (`problems._LEAK_MARKERS`),
#: and `secretmarker` stands for any policy data.
LEAKY = "otp-secretmarker"


def _policy_fault(client, ids, engine, req, caplog, code, *, internal_has=(),
                  never_shown=()):
    """The call is refused with `code` (500) and the FIXED detail; nothing is
    written and the key is not consumed; the cause, and only there, is in the
    server log, under the response's trace id."""
    key = str(uuid.uuid4())
    before = _footprint(engine, req, key)
    caplog.clear()
    with caplog.at_level(logging.ERROR, logger="turab.api"):
        r = _run(client, ids, req, [], key=key, body={"matching_policy_version": VERSION})
    assert r.status_code == 500, r.text
    problem = r.json()
    assert problem["code"] == code
    assert problem["detail"] == f"plan §3.1: {matching_run.POLICY_FAULTS[code]}"
    for marker in never_shown:
        assert marker not in r.text
    assert _footprint(engine, req, key) == before and before["idempotency"] == 0
    logged = [rec for rec in caplog.records
              if getattr(rec, "trace_id", None) == problem["trace_id"]]
    assert len(logged) == 1, [rec.getMessage() for rec in caplog.records]
    assert (logged[0].levelname, logged[0].problem_code) == ("ERROR", code)
    for fragment in internal_has:
        assert fragment in logged[0].internal_detail


def test_no_active_policy_is_its_own_typed_500(client, ids, engine, caplog):
    req = _request(engine, ids)
    _exec(engine, "UPDATE turab.matching_policies SET active = false WHERE version = :v",
          v=VERSION)
    try:
        _policy_fault(client, ids, engine, req, caplog, "MATCHING_POLICY_NOT_ACTIVE",
                      internal_has=("no active matching policy",))
    finally:
        _exec(engine, "UPDATE turab.matching_policies SET active = true WHERE version = :v",
              v=VERSION)


@pytest.mark.parametrize("label, change, internal", [
    ("relaxes requests", {"automatic_request_relaxation": True},
     "automatic_request_relaxation"),
    ("no human review", {"human_review_required_for_opportunity": False},
     "human_review_required_for_opportunity"),
    ("another hard-gate mapping", {"hard_gate": {"unknown_required": "REJECTED"}},
     "hard_gate"),
    ("no request freshness threshold", {"freshness_threshold_days": {"property": 30,
                                                                     "offer_terms": 14}},
     "freshness_threshold_days.request"),
])
def test_a_policy_this_engine_does_not_implement_is_its_own_typed_500(
        client, ids, engine, caplog, label, change, internal):
    """The active policy carries a version with leak markers. Before the
    review of 48588a0 that version reached the problem detail, and `otp`
    turned the typed refusal into an untyped 500 (DetailLeak)."""
    req = _request(engine, ids)
    seeded = _one(engine, "SELECT rules::text FROM turab.matching_policies WHERE version = :v",
                  v=VERSION)
    version = f"0.0.{uuid.uuid4().int % 10**9}-{LEAKY}"
    _exec(engine, "UPDATE turab.matching_policies SET active = false WHERE version = :v",
          v=VERSION)
    policy = None
    try:
        policy = _one(engine, """
            INSERT INTO turab.matching_policies (version, name, rules, active)
            VALUES (:v, 'unimplemented test policy', CAST(:r AS jsonb), true)
            RETURNING matching_policy_id""", v=version,
                      r=json.dumps({**json.loads(seeded), **change}))
        _policy_fault(client, ids, engine, req, caplog, "MATCHING_POLICY_NOT_SUPPORTED",
                      internal_has=(version, internal),
                      never_shown=(version, "secretmarker", internal))
    finally:
        if policy is not None:
            _exec(engine, "DELETE FROM turab.matching_policies WHERE matching_policy_id = :p",
                  p=policy)
        _exec(engine, "UPDATE turab.matching_policies SET active = true WHERE version = :v",
              v=VERSION)


def test_the_exact_writer_keeps_decimals_and_renders_everything_else_as_json_does():
    from turab import exact_json

    body = {"z": 1, "a": [True, None, "é", 2.5, 1e-07], "n": -3}
    assert exact_json.dumps(body) == json.dumps(body, ensure_ascii=False,
                                                separators=(",", ":"))
    exact = {"m2": Decimal("400.12654321098765432"), "s": Decimal("1.000000")}
    text_ = exact_json.dumps(exact)
    assert text_ == '{"m2":400.12654321098765432,"s":1.000000}'
    assert exact_json.loads(text_) == exact
    assert json.loads(text_)["m2"] == 400.1265432109877  # still a JSON number
    for bad in (Decimal("NaN"), float("inf")):
        with pytest.raises(ValueError):
            exact_json.dumps({"x": bad})


def test_only_the_frozen_key_constraint_is_a_taken_key():
    from sqlalchemy.exc import IntegrityError

    from turab.services import idempotency

    class Diag:
        def __init__(self, name):
            self.constraint_name = name

    class Orig(Exception):
        def __init__(self, state, name):
            self.sqlstate, self.diag = state, Diag(name)

    assert idempotency.key_taken(IntegrityError("s", {}, Orig("23505",
                                                              idempotency.KEY_CONSTRAINT)))
    assert not idempotency.key_taken(IntegrityError("s", {}, Orig("23505", "other_key")))
    assert not idempotency.key_taken(IntegrityError("s", {}, Orig("23503",
                                                                  idempotency.KEY_CONSTRAINT)))


def test_the_key_constraint_is_named_as_postgresql_names_it(engine):
    from turab.services import idempotency

    names = [r["conname"] for r in _all(engine, """
        SELECT conname FROM pg_constraint
         WHERE conrelid = 'turab.idempotency_records'::regclass AND contype = 'u'""")]
    assert names == [idempotency.KEY_CONSTRAINT]
