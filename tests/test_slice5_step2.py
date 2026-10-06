"""Slice 5 step 2: the human match review, REJECTED and NEED_MORE_INFORMATION.

Ref: `docs/gate/SLICE_5_PLAN.md` revision 6: §3.1 (one decision, one row; the
review stamp, [R3-1]), §3.2, G5-3 (decided (a) in the review of 29a0f30),
G5-4 (a) with [R6-1], §7 condition 4; `services/match_review.py`.

**Step 2's boundary (review of 29a0f30).** REJECTED and NEED_MORE_INFORMATION
are executed, with the NMI task and the ordering rule. APPROVED is a valid
decision of the contract that is NOT executed in this step: it is refused with
`REVIEW_DECISION_NOT_YET_AVAILABLE` and writes nothing. The tests below show
it is not classed as a gate failure. The approval codes of G5-3 (gates,
supersession, currency, an open opportunity) belong to step 3, and no test
here is attributed to them.

**Isolation.** HTTP tests commit to the shared test database. Each builds its
own request, properties and offers; matches come from the delivered Slice 4
run, so every match is a real engine output. The §3.1 tests that need the
clock seam call the service directly.
"""
from __future__ import annotations

import ast
import datetime
import json
import pathlib
import re
import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from tests.test_slice4_step7 import (_all, _criterion, _exec, _offer, _one, _request,
                                     _run)
from turab.api.problems import ProblemCode
from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.services import match_review

ROOT = pathlib.Path(__file__).resolve().parents[1]


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

def _prop(engine, *, ptype="LAND", document="LAND_BOOK"):
    prop = _one(engine, """
        INSERT INTO turab.properties (property_type, supply_mode, management_mode, claim_status,
                                      land_area_m2, availability_last_confirmed_at,
                                      current_availability)
        VALUES (CAST(:t AS turab.property_type), 'PUBLIC', 'ASSISTED', 'UNCLAIMED', 400,
                now() - interval '1 day', 'AVAILABLE')
        RETURNING property_id""", t=ptype)
    if document is not None:
        _exec(engine, """
            INSERT INTO turab.property_attributes (property_id, attribute_definition_id, value)
            SELECT :p, attribute_definition_id, CAST(:v AS jsonb)
              FROM turab.attribute_definitions WHERE code = 'DOCUMENT_TYPE'""",
              p=prop, v=json.dumps(document))
    return prop


def _match(client, engine, ids, kind="ELIGIBLE"):
    """One real match from the Slice 4 run:
    - ELIGIBLE: every gate PASS; `next_action` null;
    - DOCUMENT_UNKNOWN: REQUIRED DOCUMENT_TYPE unknown, so NEED_MORE_INFORMATION
      with `next_action.type` VERIFY_DOCUMENT;
    - ROOMS_UNKNOWN: an APARTMENT with no ROOMS recorded and REQUIRED ROOMS_MIN,
      so NEED_MORE_INFORMATION with `next_action.type` OTHER ([R6-1])."""
    req = _request(engine, ids)
    if kind == "ROOMS_UNKNOWN":
        _criterion(engine, req, "ROOMS_MIN", "GTE", 3, "REQUIRED")
        prop = _prop(engine, ptype="APARTMENT", document=None)
    else:
        _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
        prop = _prop(engine, document=None if kind == "DOCUMENT_UNKNOWN" else "LAND_BOOK")
    _offer(engine, ids, prop)
    r = _run(client, ids, req, [prop])
    assert r.status_code == 201, r.text
    [m] = r.json()["matches"]
    return m


def _review(client, match_id, body, account, key=None):
    return client.post(f"/matches/{match_id}/review", json=body,
                       headers={"Authorization": f"Bearer {account}",
                                "Idempotency-Key": key or str(uuid.uuid4())})


def _footprint(engine, match_id, key=None):
    """Everything a review could write, and the audit high-water mark."""
    return {
        "reviews": _one(engine, "SELECT count(*) FROM turab.match_reviews "
                                "WHERE match_id = :m", m=match_id),
        "tasks": _one(engine, "SELECT count(*) FROM turab.tasks WHERE match_id = :m",
                      m=match_id),
        "opportunities": _one(engine, "SELECT count(*) FROM turab.opportunities "
                                      "WHERE approved_match_id = :m", m=match_id),
        "audit": _one(engine, "SELECT coalesce(max(audit_id), 0) FROM turab.audit_log"),
        "idempotency": None if key is None else _one(
            engine, "SELECT count(*) FROM turab.idempotency_records "
                    "WHERE idempotency_key = :k", k=key),
    }


def _refused(client, engine, match_id, body, account, status, code):
    key = str(uuid.uuid4())
    before = _footprint(engine, match_id, key)
    r = _review(client, match_id, body, account, key)
    assert (r.status_code, r.json()["code"]) == (status, code), r.text
    assert _footprint(engine, match_id, key) == before, "a refusal writes nothing"
    return r


def _reviews(engine, match_id):
    return _all(engine, """
        SELECT match_review_id, decision::text AS decision, reason_code, reason_text,
               reviewer_account_id, reviewed_at
          FROM turab.match_reviews WHERE match_id = :m
         ORDER BY reviewed_at DESC, match_review_id DESC""", m=match_id)


def _tasks(engine, match_id):
    return _all(engine, """
        SELECT task_id, task_type::text AS task_type, priority::text AS priority,
               status::text AS status, title, reason_code, request_id, property_id,
               match_id, party_id, assigned_account_id, due_at, payload
          FROM turab.tasks WHERE match_id = :m ORDER BY created_at, task_id""", m=match_id)


# ======================================================================================
# The shape of the input: 422 before anything (G5-3, Spec §19.1)
# ======================================================================================

@pytest.mark.parametrize("body,code", [
    ({"decision": "REJECTED"}, "REVIEW_REASON_REQUIRED"),
    ({"decision": "NEED_MORE_INFORMATION"}, "REVIEW_REASON_REQUIRED"),
    ({"decision": "APPROVED", "reason_code": "OTHER"}, "REVIEW_REASON_NOT_ALLOWED"),
    ({"decision": "MAYBE", "reason_code": "OTHER"}, "VALIDATION_FAILED"),
    ({"decision": "REJECTED", "reason_code": None}, "VALIDATION_FAILED"),
    ({"decision": "REJECTED", "reason_code": "OTHER", "reason_text": None},
     "VALIDATION_FAILED"),
    ({"decision": "REJECTED", "reason_code": "OTHER", "opportunity": {}},
     "VALIDATION_FAILED"),
], ids=["reject-no-reason", "nmi-no-reason", "approve-with-reason", "unknown-decision",
        "null-reason", "null-text", "unknown-field"])
def test_a_malformed_review_is_refused_before_any_write(client, engine, ids, body, code):
    m = _match(client, engine, ids)
    _refused(client, engine, m["match_id"], body, ids.ACC_REVIEWER, 422, code)


# ======================================================================================
# Authorization (x-roles ADMIN, REVIEWER; INV-2; the staff-read convention)
# ======================================================================================

@pytest.mark.parametrize("account,status,code", [
    ("ACC_OPERATOR", 403, "ROLE_NOT_PERMITTED"),
    ("ACC_AMINA", 403, "ROLE_NOT_PERMITTED"),
])
def test_only_admin_and_reviewer_may_review(client, engine, ids, account, status, code):
    """Maker–checker (RFC-001 §2.1): the OPERATOR who records market truth
    does not decide on the match."""
    m = _match(client, engine, ids)
    _refused(client, engine, m["match_id"],
             {"decision": "REJECTED", "reason_code": "OTHER"}, getattr(ids, account),
             status, code)


@pytest.mark.parametrize("account", ["ACC_REVIEWER", "ACC_ADMIN"])
def test_admin_and_reviewer_may_review(client, engine, ids, account):
    m = _match(client, engine, ids)
    r = _review(client, m["match_id"], {"decision": "REJECTED", "reason_code": "OTHER"},
                getattr(ids, account))
    assert r.status_code == 200, r.text
    [row] = _reviews(engine, m["match_id"])
    assert row["reviewer_account_id"] == getattr(ids, account), "the subject, never the body"


def test_an_unknown_match_is_403_and_recorded(client, ids, sink):
    """G5-3: the staff convention of Slice 4 (`read_match`): 403 for an id
    that is not there, and the denial is recorded (R6.3a)."""
    unknown = uuid.uuid4()
    r = _review(client, unknown, {"decision": "REJECTED", "reason_code": "OTHER"},
                ids.ACC_REVIEWER)
    assert (r.status_code, r.json()["code"]) == (403, "OBJECT_NOT_AUTHORIZED")
    denied = [rec for rec in sink.records if rec.resource_id == unknown]
    assert [(d.event.value, d.resource_kind) for d in denied] == [("DENIED", "MATCH_CANDIDATE")]


def test_a_review_needs_an_idempotency_key(client, engine, ids):
    m = _match(client, engine, ids)
    before = _footprint(engine, m["match_id"])
    r = client.post(f"/matches/{m['match_id']}/review",
                    json={"decision": "REJECTED", "reason_code": "OTHER"},
                    headers={"Authorization": f"Bearer {ids.ACC_REVIEWER}"})
    assert (r.status_code, r.json()["code"]) == (400, "IDEMPOTENCY_KEY_REQUIRED")
    assert _footprint(engine, m["match_id"]) == before


# ======================================================================================
# REJECTED (G5-3 (a)): a reason of MATCH, FRESHNESS or PERMISSION, or OTHER; final
# ======================================================================================

@pytest.mark.parametrize("reason", ["LOCATION_MISMATCH", "REQUEST_STALE",
                                    "PERMISSION_MISSING", "OTHER"])
def test_rejected_records_one_review_and_no_task(client, engine, ids, reason):
    m = _match(client, engine, ids)
    r = _review(client, m["match_id"],
                {"decision": "REJECTED", "reason_code": reason, "reason_text": "why"},
                ids.ACC_REVIEWER)
    assert r.status_code == 200, r.text
    assert r.json() == {"match_id": m["match_id"], "decision": "REJECTED",
                        "opportunity": None, "task": None}
    [row] = _reviews(engine, m["match_id"])
    assert (row["decision"], row["reason_code"], row["reason_text"]) == (
        "REJECTED", reason, "why")
    assert _tasks(engine, m["match_id"]) == []
    audited = _all(engine, """SELECT action, actor_account_id FROM turab.audit_log
                               WHERE entity_table = 'match_reviews' AND entity_id = :r""",
                   r=row["match_review_id"])
    assert audited == [{"action": "INSERT", "actor_account_id": ids.ACC_REVIEWER}]


@pytest.mark.parametrize("reason", ["BUYER_REJECTED", "SAME_PROPERTY_CONFIRMED",
                                    "NO_SUCH_REASON"])
def test_rejected_refuses_a_reason_outside_its_categories(client, engine, ids, reason):
    """OPPORTUNITY and IDENTITY reasons do not explain a rejected match, and an
    unknown code is no reason (G5-3)."""
    m = _match(client, engine, ids)
    _refused(client, engine, m["match_id"],
             {"decision": "REJECTED", "reason_code": reason}, ids.ACC_REVIEWER,
             422, "REVIEW_REASON_NOT_ALLOWED")


@pytest.mark.parametrize("then", [
    {"decision": "REJECTED", "reason_code": "OTHER"},
    {"decision": "NEED_MORE_INFORMATION", "reason_code": "DOCUMENT_NOT_KNOWN"},
    {"decision": "APPROVED"},
])
def test_rejected_is_final(client, engine, ids, then):
    """G5-3 (a): after REJECTED, any later review is 409 MATCH_REVIEW_DECIDED,
    APPROVED included (the decided check precedes step 2's APPROVED refusal),
    and nothing is written."""
    m = _match(client, engine, ids)
    assert _review(client, m["match_id"], {"decision": "REJECTED", "reason_code": "OTHER"},
                   ids.ACC_REVIEWER).status_code == 200
    _refused(client, engine, m["match_id"], then, ids.ACC_REVIEWER, 409,
             "MATCH_REVIEW_DECIDED")


def test_a_match_with_an_opportunity_is_decided(client, engine, ids):
    """G5-3 (a): an opportunity created from the match closes it to review.
    No step-2 path creates one; the row here is a fixture written by SQL,
    after an APPROVED review written by SQL."""
    m = _match(client, engine, ids)
    _exec(engine, """INSERT INTO turab.match_reviews (match_id, decision, reviewer_account_id)
                     VALUES (:m, 'APPROVED', :a)""", m=m["match_id"], a=ids.ACC_REVIEWER)
    _exec(engine, """
        INSERT INTO turab.opportunities (request_id, property_id, approved_match_id,
                                         current_offer_id, sharing_scope, why_real,
                                         created_by_account_id)
        SELECT request_id, property_id, match_id, evaluated_offer_id, 'SUMMARY_ONLY',
               '{}'::jsonb, :a FROM turab.match_candidates WHERE match_id = :m""",
          m=m["match_id"], a=ids.ACC_REVIEWER)
    _refused(client, engine, m["match_id"],
             {"decision": "NEED_MORE_INFORMATION", "reason_code": "DOCUMENT_NOT_KNOWN"},
             ids.ACC_REVIEWER, 409, "MATCH_REVIEW_DECIDED")


# ======================================================================================
# NEED_MORE_INFORMATION (G5-4 (a)): one NEW task per review, typed from the reason
# ======================================================================================

@pytest.mark.parametrize("reason,task_type", sorted(match_review.NMI_TASK_TYPES.items()))
def test_nmi_raises_one_task_of_the_reasons_type(client, engine, ids, reason, task_type):
    m = _match(client, engine, ids)
    r = _review(client, m["match_id"],
                {"decision": "NEED_MORE_INFORMATION", "reason_code": reason},
                ids.ACC_REVIEWER)
    assert r.status_code == 200, r.text
    [review] = _reviews(engine, m["match_id"])
    [task] = _tasks(engine, m["match_id"])
    body = r.json()
    assert body["decision"] == "NEED_MORE_INFORMATION" and body["opportunity"] is None
    assert body["task"]["task_id"] == str(task["task_id"])
    assert (task["task_type"], task["status"], task["reason_code"], task["title"]) == (
        task_type, "OPEN", reason, match_review.TASK_TITLES[task_type])
    assert (str(task["request_id"]), str(task["property_id"]), str(task["match_id"])) == (
        m["request_id"], m["property_id"], m["match_id"])
    assert (task["party_id"], task["assigned_account_id"], task["due_at"]) == (None, None, None)
    assert task["payload"] == {"match_review_id": str(review["match_review_id"]),
                               "next_action": m["next_action"]}
    audited = _all(engine, """SELECT action FROM turab.audit_log
                               WHERE entity_table = 'tasks' AND entity_id = :t""",
                   t=task["task_id"])
    assert audited == [{"action": "INSERT"}]


def test_the_response_and_the_task_are_the_contracts_shapes(client, engine, ids):
    import yaml

    schemas = yaml.safe_load((ROOT / "docs/handoff/05_API/openapi_v0.2.3.yaml").read_text())[
        "components"]["schemas"]
    m = _match(client, engine, ids)
    body = _review(client, m["match_id"],
                   {"decision": "NEED_MORE_INFORMATION", "reason_code": "PROPERTY_STALE"},
                   ids.ACC_REVIEWER).json()
    assert set(body) == {"match_id", "decision", "opportunity", "task"}
    assert set(body["task"]) == set(schemas["Task"]["properties"])


@pytest.mark.parametrize("kind,priority", [("DOCUMENT_UNKNOWN", "HIGH"), ("ELIGIBLE", "NORMAL")])
def test_the_task_is_high_priority_when_the_match_has_a_blocking_unknown(
        client, engine, ids, kind, priority):
    """G5-4: Spec §13, as `action.next@1` applies it."""
    m = _match(client, engine, ids, kind)
    _review(client, m["match_id"],
            {"decision": "NEED_MORE_INFORMATION", "reason_code": "DOCUMENT_NOT_KNOWN"},
            ids.ACC_REVIEWER)
    [task] = _tasks(engine, m["match_id"])
    assert task["priority"] == priority


def test_two_nmi_reviews_give_two_tasks_each_linked_to_its_own_review(client, engine, ids):
    """G5-4 (a): never reused; the link is 1:1 and written once."""
    m = _match(client, engine, ids)
    for reason in ("DOCUMENT_NOT_KNOWN", "DOCUMENT_NOT_KNOWN"):
        assert _review(client, m["match_id"],
                       {"decision": "NEED_MORE_INFORMATION", "reason_code": reason},
                       ids.ACC_REVIEWER).status_code == 200
    reviews = {str(r["match_review_id"]) for r in _reviews(engine, m["match_id"])}
    tasks = _tasks(engine, m["match_id"])
    assert len(reviews) == 2 and len(tasks) == 2
    assert {t["payload"]["match_review_id"] for t in tasks} == reviews


def test_nmi_is_not_final(client, engine, ids):
    """G5-3 (a): NMI, then REJECTED, are both kept; then the match is final."""
    m = _match(client, engine, ids)
    assert _review(client, m["match_id"],
                   {"decision": "NEED_MORE_INFORMATION", "reason_code": "REQUEST_STALE"},
                   ids.ACC_REVIEWER).status_code == 200
    assert _review(client, m["match_id"], {"decision": "REJECTED", "reason_code": "OTHER"},
                   ids.ACC_REVIEWER).status_code == 200
    assert [r["decision"] for r in _reviews(engine, m["match_id"])] == [
        "REJECTED", "NEED_MORE_INFORMATION"]


@pytest.mark.parametrize("reason", ["OTHER", "LOCATION_MISMATCH", "BUYER_REJECTED",
                                    "NO_SUCH_REASON"])
def test_nmi_refuses_a_reason_that_names_no_specific_task(client, engine, ids, reason):
    """Spec §19.1: a specific task, never "contact the client" only."""
    m = _match(client, engine, ids)
    _refused(client, engine, m["match_id"],
             {"decision": "NEED_MORE_INFORMATION", "reason_code": reason},
             ids.ACC_REVIEWER, 422, "REVIEW_REASON_NOT_ALLOWED")


# ======================================================================================
# [R6-1] ACTIONABLE_UNKNOWN
# ======================================================================================

@pytest.mark.parametrize("kind,stored_type", [("ROOMS_UNKNOWN", "OTHER"), ("ELIGIBLE", None)])
def test_actionable_unknown_is_refused_without_a_specific_next_action(
        client, engine, ids, kind, stored_type):
    """The OTHER case and the absent case: 422 before any write."""
    m = _match(client, engine, ids, kind)
    assert (m["next_action"] or {}).get("type") == stored_type
    r = _refused(client, engine, m["match_id"],
                 {"decision": "NEED_MORE_INFORMATION", "reason_code": "ACTIONABLE_UNKNOWN"},
                 ids.ACC_REVIEWER, 422, "REVIEW_REASON_NOT_ALLOWED")
    assert "ACTIONABLE_UNKNOWN" in r.json()["detail"]


def test_actionable_unknown_takes_a_specific_next_action(client, engine, ids):
    m = _match(client, engine, ids, "DOCUMENT_UNKNOWN")
    assert m["next_action"]["type"] == "VERIFY_DOCUMENT"
    r = _review(client, m["match_id"],
                {"decision": "NEED_MORE_INFORMATION", "reason_code": "ACTIONABLE_UNKNOWN"},
                ids.ACC_REVIEWER)
    assert r.status_code == 200, r.text
    [review] = _reviews(engine, m["match_id"])
    [task] = _tasks(engine, m["match_id"])
    assert (task["task_type"], task["priority"], task["reason_code"]) == (
        "VERIFY_DOCUMENT", "HIGH", "ACTIONABLE_UNKNOWN")
    assert task["payload"]["match_review_id"] == str(review["match_review_id"])


def _next_action_types() -> set[str]:
    """The `type` values the pinned `action.next@1` can return, read from its
    code: the dictionary of criterion types plus its `.get` default, and every
    literal `"type"` it returns."""
    tree = ast.parse((ROOT / "src/turab/matching/gates.py").read_text())
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "next_action_v1")
    found: set[str] = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "kind" for t in node.targets):
            call = node.value
            if isinstance(call, ast.Call):
                found |= {v.value for v in call.func.value.values}
                found |= {a.value for a in call.args[1:] if isinstance(a, ast.Constant)}
        if isinstance(node, ast.For) and isinstance(node.iter, ast.Tuple):
            for elt in node.iter.elts:
                if isinstance(elt, ast.Tuple):
                    found.add(elt.elts[-1].value)
        if isinstance(node, ast.Dict):
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and k.value == "type" and isinstance(
                        v, ast.Constant):
                    found.add(v.value)
    return found


def test_the_next_action_vocabulary_is_the_six_types_and_five_are_specific():
    """[R6-1], a guard without PostgreSQL. A later rule version that adds a
    type fails here, and so forces the mapping to be decided again."""
    six = {"VERIFY_DOCUMENT", "CONFIRM_PRICE", "OTHER", "RECONFIRM_REQUEST",
           "RECONFIRM_PROPERTY", "CONFIRM_PERMISSION"}
    assert _next_action_types() == six
    assert match_review.SPECIFIC_NEXT_ACTION_TYPES == six - {"OTHER"}
    assert set(match_review.NMI_TASK_TYPES.values()) <= match_review.SPECIFIC_NEXT_ACTION_TYPES
    assert set(match_review.TASK_TITLES) == match_review.SPECIFIC_NEXT_ACTION_TYPES


@pytest.mark.parametrize("next_action", [None, {}, {"type": "OTHER"}, {"type": "UNHEARD_OF"}])
def test_actionable_unknown_refuses_every_unspecific_next_action(next_action):
    with pytest.raises(match_review.ReviewRefused) as caught:
        match_review.task_type_for("ACTIONABLE_UNKNOWN", next_action)
    assert caught.value.code == "REVIEW_REASON_NOT_ALLOWED"


@pytest.mark.parametrize("kind", sorted(match_review.SPECIFIC_NEXT_ACTION_TYPES))
def test_actionable_unknown_takes_each_specific_type(kind):
    assert match_review.task_type_for("ACTIONABLE_UNKNOWN", {"type": kind}) == kind


def test_every_reason_the_review_names_is_seeded_and_active(engine):
    rows = {r["code"]: r for r in _all(engine, """
        SELECT code, category, active FROM turab.reason_codes""")}
    named = set(match_review.NMI_TASK_TYPES) | {"ACTIONABLE_UNKNOWN", "OTHER"}
    assert named <= set(rows), named - set(rows)
    assert all(rows[c]["active"] for c in named)
    assert set(match_review.REJECT_CATEGORIES) <= {r["category"] for r in rows.values()}


# ======================================================================================
# APPROVED in step 2: a valid decision, not executed yet — never a gate failure
# ======================================================================================

@pytest.mark.parametrize("kind", ["ELIGIBLE", "DOCUMENT_UNKNOWN"])
def test_approved_is_refused_in_step_2_as_not_yet_available(client, engine, ids, kind):
    """The review of 29a0f30: APPROVED is refused with a typed, zero-footprint
    refusal that says the decision is valid but not executed in this step.
    On an ELIGIBLE match with every gate PASS the answer is the same as on a
    NEED_MORE_INFORMATION match, so it is not a gate verdict."""
    m = _match(client, engine, ids, kind)
    r = _refused(client, engine, m["match_id"], {"decision": "APPROVED"}, ids.ACC_REVIEWER,
                 409, "REVIEW_DECISION_NOT_YET_AVAILABLE")
    assert "valid decision" in r.json()["detail"] and "step 3" in r.json()["detail"]
    assert r.json()["code"] not in {"HARD_GATE_FAILED", "MATCH_GATES_NOT_PASS"}


def test_the_step_3_codes_are_not_introduced_by_step_2():
    """G5-3's approval codes are step 3's; step 2 adds only its own four."""
    for code in ("MATCH_GATES_NOT_PASS", "MATCH_SUPERSEDED", "MATCH_CONTEXT_NOT_VALID",
                 "OPPORTUNITY_ALREADY_OPEN"):
        assert code not in ProblemCode.__members__, code


# ======================================================================================
# Idempotency (API_CONTRACTS §2.3, K05)
# ======================================================================================

def test_a_replay_returns_the_original_and_writes_nothing_more(client, engine, ids):
    m = _match(client, engine, ids)
    key = str(uuid.uuid4())
    body = {"decision": "NEED_MORE_INFORMATION", "reason_code": "DOCUMENT_NOT_KNOWN"}
    first = _review(client, m["match_id"], body, ids.ACC_REVIEWER, key)
    again = _review(client, m["match_id"], body, ids.ACC_REVIEWER, key)
    assert (first.status_code, again.status_code) == (200, 200)
    assert again.json() == first.json()
    assert (len(_reviews(engine, m["match_id"])), len(_tasks(engine, m["match_id"]))) == (1, 1)
    other = _review(client, m["match_id"], {"decision": "REJECTED", "reason_code": "OTHER"},
                    ids.ACC_REVIEWER, key)
    assert (other.status_code, other.json()["code"]) == (409, "IDEMPOTENCY_KEY_CONFLICT")


def test_a_refused_review_does_not_consume_its_key(client, engine, ids):
    """The refusal is decided before the claim: the same key then serves a
    valid review."""
    m = _match(client, engine, ids)
    key = str(uuid.uuid4())
    bad = _review(client, m["match_id"],
                  {"decision": "NEED_MORE_INFORMATION", "reason_code": "OTHER"},
                  ids.ACC_REVIEWER, key)
    assert bad.status_code == 422
    good = _review(client, m["match_id"],
                   {"decision": "NEED_MORE_INFORMATION", "reason_code": "OTHER"},
                   ids.ACC_REVIEWER, key)
    assert good.status_code == 422, "the same body is evaluated afresh, not replayed"
    fixed = _review(client, m["match_id"], {"decision": "REJECTED", "reason_code": "OTHER"},
                    ids.ACC_REVIEWER, key)
    assert fixed.status_code == 200, fixed.text


# ======================================================================================
# §3.1 [R3-1]: the latest review is the last decision taken
# ======================================================================================

def _session(engine, account) -> Session:
    s = Session(bind=engine, expire_on_commit=False, future=True)
    s.begin()
    s.execute(text("SELECT set_config('app.account_id', :a, true)"), {"a": str(account)})
    return s


def _service_review(engine, account, match_id, decision, reason, clock=None):
    s = _session(engine, account)
    try:
        prepared = match_review.prepare(s, match_id=uuid.UUID(match_id), decision=decision,
                                        reason_code=reason, reason_text=None)
        match_review.record(s, prepared, reviewer_account_id=account, clock=clock)
        s.commit()
    finally:
        s.close()


def _latest(engine, match_id):
    return _reviews(engine, match_id)[0]


def test_an_equal_clock_reading_still_stamps_strictly_after(client, engine, ids):
    """Case 1: the new reading equals the previous stamp. Without `+ 1 µs`
    the stamps tie and the random id decides (step 0, A3)."""
    m = _match(client, engine, ids)
    t = datetime.datetime(2030, 1, 1, tzinfo=datetime.timezone.utc)
    _service_review(engine, ids.ACC_REVIEWER, m["match_id"], "NEED_MORE_INFORMATION",
                    "DOCUMENT_NOT_KNOWN", clock=t)
    _service_review(engine, ids.ACC_REVIEWER, m["match_id"], "REJECTED", "OTHER", clock=t)
    latest, first = _reviews(engine, m["match_id"])
    assert (latest["decision"], first["decision"]) == ("REJECTED", "NEED_MORE_INFORMATION")
    assert first["reviewed_at"] == t
    assert latest["reviewed_at"] == t + datetime.timedelta(microseconds=1)


def test_a_previous_stamp_in_the_future_is_still_exceeded(client, engine, ids):
    """Case 2: a previous `reviewed_at` later than the clock (a clock step
    back). The new review takes that stamp + 1 µs and is the latest."""
    m = _match(client, engine, ids)
    _exec(engine, """INSERT INTO turab.match_reviews (match_id, decision, reason_code,
                                                      reviewer_account_id, reviewed_at)
                     VALUES (:m, 'NEED_MORE_INFORMATION', 'DOCUMENT_NOT_KNOWN', :a,
                             now() + interval '1 day')""",
          m=m["match_id"], a=ids.ACC_REVIEWER)
    future = _latest(engine, m["match_id"])["reviewed_at"]
    _service_review(engine, ids.ACC_REVIEWER, m["match_id"], "REJECTED", "OTHER")
    latest = _latest(engine, m["match_id"])
    assert latest["decision"] == "REJECTED"
    assert latest["reviewed_at"] == future + datetime.timedelta(microseconds=1)


def test_the_first_review_takes_the_clock(client, engine, ids):
    m = _match(client, engine, ids)
    t = datetime.datetime(2031, 6, 1, 12, tzinfo=datetime.timezone.utc)
    _service_review(engine, ids.ACC_REVIEWER, m["match_id"], "REJECTED", "OTHER", clock=t)
    assert _latest(engine, m["match_id"])["reviewed_at"] == t


def _race(engine, ids, match_id, first, second):
    """A holds the match lock; B's prepare waits on it (pg_blocking_pids is the
    witness); A records and commits; B then proceeds, or is refused."""
    a = _session(engine, ids.ACC_REVIEWER)
    b = _session(engine, ids.ACC_ADMIN)
    pid_a = a.execute(text("SELECT pg_backend_pid()")).scalar_one()
    pid_b = b.execute(text("SELECT pg_backend_pid()")).scalar_one()
    prepared_a = match_review.prepare(a, match_id=uuid.UUID(match_id), decision=first[0],
                                      reason_code=first[1], reason_text=None)
    outcome: dict = {}

    def run_b():
        try:
            prepared = match_review.prepare(b, match_id=uuid.UUID(match_id),
                                            decision=second[0], reason_code=second[1],
                                            reason_text=None)
            match_review.record(b, prepared, reviewer_account_id=ids.ACC_ADMIN)
            b.commit()
            outcome["b"] = "recorded"
        except match_review.ReviewRefused as exc:
            b.rollback()
            outcome["b"] = exc.code

    thread = threading.Thread(target=run_b)
    thread.start()
    waited = False
    with engine.connect() as probe:
        for _ in range(200):
            time.sleep(0.02)
            if pid_a in probe.execute(text("SELECT pg_blocking_pids(:p)"),
                                      {"p": pid_b}).scalar_one():
                waited = True
                break
    match_review.record(a, prepared_a, reviewer_account_id=ids.ACC_REVIEWER)
    a.commit()
    thread.join(20)
    a.close()
    b.close()
    return waited, outcome.get("b")


def test_a5_the_waiting_review_committed_last_is_the_latest(client, engine, ids):
    """A5 against the command: B started first and waited at the lock; its
    review, committed last, is the latest (step 0 measured the opposite
    without the rule)."""
    m = _match(client, engine, ids)
    waited, b = _race(engine, ids, m["match_id"],
                      ("NEED_MORE_INFORMATION", "DOCUMENT_NOT_KNOWN"), ("REJECTED", "OTHER"))
    assert waited and b == "recorded"
    latest, earlier = _reviews(engine, m["match_id"])
    assert (latest["decision"], earlier["decision"]) == ("REJECTED", "NEED_MORE_INFORMATION")
    assert latest["reviewed_at"] > earlier["reviewed_at"]


def test_a_review_waiting_behind_a_rejection_is_refused_as_decided(client, engine, ids):
    """The lock serializes; the decided check is made after it, so the
    second reviewer sees the first's REJECTED and is refused."""
    m = _match(client, engine, ids)
    waited, b = _race(engine, ids, m["match_id"], ("REJECTED", "OTHER"),
                      ("NEED_MORE_INFORMATION", "DOCUMENT_NOT_KNOWN"))
    assert waited and b == "MATCH_REVIEW_DECIDED"
    assert [r["decision"] for r in _reviews(engine, m["match_id"])] == ["REJECTED"]


def test_a3_twenty_sequences_end_with_the_last_decision(client, engine, ids):
    """A3 against the command. One command writes one review, so two reviews
    of one transaction cannot arise. Twenty pairs of committed reviews, each
    pair NMI (DOCUMENT_NOT_KNOWN) then NMI (REQUEST_STALE), each end with the
    second as the latest: 20/20, not about half. (The plan's APPROVED → NMI
    form needs APPROVED, which is step 3's.)"""
    ends = []
    for _ in range(20):
        m = _match(client, engine, ids)
        for reason in ("DOCUMENT_NOT_KNOWN", "REQUEST_STALE"):
            assert _review(client, m["match_id"],
                           {"decision": "NEED_MORE_INFORMATION", "reason_code": reason},
                           ids.ACC_REVIEWER).status_code == 200
        ends.append(_latest(engine, m["match_id"])["reason_code"])
    assert ends == ["REQUEST_STALE"] * 20


def test_the_stamp_statement_is_the_plans(engine):
    """§3.1 states the statement; the service runs that statement."""
    expected = ("SELECT GREATEST(COALESCE(CAST(:clock AS timestamptz), clock_timestamp()), "
                "max(reviewed_at) + interval '1 microsecond') "
                "FROM turab.match_reviews WHERE match_id = :m")
    assert " ".join(match_review.STAMP_SQL.split()) == expected


# ======================================================================================
# Writers (§7 conditions 3 and 4)
# ======================================================================================

def _writers(table: str) -> list[str]:
    pattern = re.compile(rf"INSERT\s+INTO\s+turab\.{table}\b")
    return sorted(str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")
                  if pattern.search(p.read_text()))


def test_only_the_review_command_writes_match_reviews_and_nothing_writes_opportunities():
    assert _writers("match_reviews") == ["src/turab/services/match_review.py"]
    assert _writers("opportunities") == []
    assert _writers("tasks") == ["src/turab/services/identity.py",
                                 "src/turab/services/match_review.py"]


def test_step_2_never_writes_an_opportunity(client, engine, ids):
    m = _match(client, engine, ids)
    for body in ({"decision": "NEED_MORE_INFORMATION", "reason_code": "DOCUMENT_NOT_KNOWN"},
                 {"decision": "APPROVED"}, {"decision": "REJECTED", "reason_code": "OTHER"}):
        _review(client, m["match_id"], body, ids.ACC_REVIEWER)
    assert _one(engine, "SELECT count(*) FROM turab.opportunities WHERE request_id = :r",
                r=m["request_id"]) == 0
