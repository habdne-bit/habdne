"""Slice 5 step 6: L-S5-3a and L-S5-3b, and the carried red-team cases.

Ref: `docs/gate/SLICE_5_PLAN.md` §6 (the mandatory and red-team tests,
STOP GATE E), §8 ("Carried to step 6": L-S5-3a, L-S5-3b); the review of
3a60b3b (step 6 authorized; L-S5-3a and L-S5-3b must each be settled
explicitly, by proof or by an accepted, documented limit).

**L-S5-3a.** Supersession is per request, property, POLICY and evaluated
offer (G5-2). Step 3 proved it within one policy only. Here a later match
of the same request, property and offer under ANOTHER policy does not
supersede the earlier one, for the approval and for the match queue.
- The second policy is a new row, since `0005` makes `0.2.0` immutable, and
  is active only inside a transaction that is rolled back.
- A committed second policy could never be removed (a match cites it, and
  matches are immutable), and the suite pins the seed's single policy
  (`test_correction_004`).
- The run and the approval are the real services, called in that
  transaction.

**L-S5-3b.** A matching run committing between the approval's supersession
check and its commit. Measured over HTTP, in both orders, with a
`pg_blocking_pids` witness.

**No new module is imported at module level,** so the file collects at
the step's base commit and the before-fix record measures each test.
"""
from __future__ import annotations

import threading
import time
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.test_slice4_step7 import _all, _exec, _one, _run
from tests.test_slice5_step3 import _approve, _world
from tests.test_slice5_step3 import _opportunity as _by_match
from turab.auth.audit import AccessAuditor, RecordingAuditSink


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# --- the witness helpers (as step 5's) ---------------------------------------------------

def _blocked_by(engine, pid):
    return [r["pid"] for r in _all(engine, """
        SELECT pid FROM pg_stat_activity
         WHERE pid <> :w AND wait_event_type = 'Lock'
           AND :w = ANY(pg_blocking_pids(pid))""", w=pid)]


def _watch(engine, pid, thread, seconds=8.0):
    """Until a backend waits on `pid`, or `thread` ends: True if one waited."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if _blocked_by(engine, pid):
            return True
        if not thread.is_alive():
            return False
        time.sleep(0.02)
    return False


def _in_thread(engine, out, name, call):
    from turab.app import create_app

    def run():
        with TestClient(create_app(engine=engine)) as c:
            out[name] = call(c)
            out[f"{name}_done"] = time.monotonic()
    t = threading.Thread(target=run)
    t.start()
    return t


# ======================================================================================
# L-S5-3a: supersession across two policies
# ======================================================================================

def _second_policy(session):
    """A new, active policy with 0.2.0's rules, in the caller's transaction."""
    version = f"l-s5-3a-{uuid.uuid4().hex[:12]}"
    session.execute(text("UPDATE turab.matching_policies SET active = false WHERE active"))
    session.execute(text("""
        INSERT INTO turab.matching_policies (version, name, rules, active, activated_at)
        SELECT :v, name, rules, true, clock_timestamp()
          FROM turab.matching_policies WHERE version = '0.2.0'"""), {"v": version})
    return version


def test_l_s5_3a_a_later_match_under_another_policy_supersedes_nothing(client, engine, ids):
    """G5-2: a match is superseded only by a later match of the same request,
    property, POLICY and evaluated offer.
    - Match A is a committed run under 0.2.0.
    - In a later transaction, a second policy becomes active, and the real
      run evaluates the same request, property and offer under it: match B,
      evaluated strictly later than A.
    - B does not supersede A: A stays in the match queue beside B, and A's
      APPROVED review creates the opportunity (no MATCH_SUPERSEDED).
    The transaction is rolled back: the policy, B, the review and the
    opportunity leave nothing behind."""
    from sqlalchemy.orm import Session

    from turab.services import match_review, matching_run, opportunity_views

    req, prop, [offer], [a] = _world(client, engine, ids)
    s = Session(bind=engine)
    try:
        s.execute(text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ"))
        s.execute(text("SELECT set_config('app.account_id', :a, true)"),
                  {"a": str(ids.ACC_OPERATOR)})
        version = _second_policy(s)
        prepared = matching_run.prepare(s, req, matching_policy_version=version,
                                        property_ids=[prop])
        status, body = matching_run.execute(s, prepared)
        [b] = body["matches"]
        assert status == 201 and b["match_id"] != a["match_id"]
        assert (b["request_id"], b["property_id"], b["evaluated_offer_id"]) == (
            a["request_id"], a["property_id"], a["evaluated_offer_id"])
        assert b["matching_policy_version"] == version != a["matching_policy_version"]
        assert b["evaluated_at"] > a["evaluated_at"], "B is strictly later than A"

        queued = {i["id"] for i in opportunity_views.match_queue(s)}
        assert {a["match_id"], b["match_id"]} <= queued, "per policy: both are current"

        assert match_review._superseded_by(s, match_review._lock_match(
            s, uuid.UUID(a["match_id"]))) is None
        s.execute(text("SELECT set_config('app.account_id', :a, true)"),
                  {"a": str(ids.ACC_REVIEWER)})
        approved = match_review.prepare(s, match_id=uuid.UUID(a["match_id"]),
                                        decision="APPROVED", reason_code=None,
                                        reason_text=None)
        made = match_review.record(s, approved, reviewer_account_id=ids.ACC_REVIEWER)
        assert made["opportunity"]["approved_match_id"] == a["match_id"]
    finally:
        s.rollback()
        s.close()
    assert _one(engine, "SELECT version FROM turab.matching_policies WHERE active") == "0.2.0"
    assert _by_match(engine, a["match_id"]) is None, "rolled back"


def test_l_s5_3a_a_later_match_under_the_same_policy_still_supersedes(client, engine, ids):
    """The control: the same request, property, offer AND policy, evaluated
    later (a committed second run on changed facts), supersedes the first.
    The step-3 proof, repeated here beside the two-policy case."""
    req, prop, [offer], [a] = _world(client, engine, ids)
    _exec(engine, "UPDATE turab.property_offers SET commercial_terms_last_confirmed_at = "
                  "now() - interval '2 hours' WHERE offer_id = :o", o=offer)
    r = _run(client, ids, req, [prop])
    [b] = r.json()["matches"]
    assert b["match_id"] != a["match_id"]
    refused = _approve(client, a["match_id"], ids.ACC_REVIEWER)
    assert (refused.status_code, refused.json()["code"]) == (409, "MATCH_SUPERSEDED")


# ======================================================================================
# L-S5-3b: a run committing between the approval's supersession check and its commit
# ======================================================================================

def _a_newer_input(engine, offer):
    """A changed fact, committed, so the next run stores a NEW match of the
    same request, property, policy and offer (G4-13: identical facts would
    return the same match). It keeps the facts VALID for the approval."""
    _exec(engine, "UPDATE turab.property_offers SET commercial_terms_last_confirmed_at = "
                  "now() - interval '2 hours' WHERE offer_id = :o", o=offer)


def _newer_matches(engine, match_id):
    return _one(engine, """
        SELECT count(*) FROM turab.match_candidates n, turab.match_candidates m
         WHERE m.match_id = :m AND n.request_id = m.request_id
           AND n.property_id = m.property_id
           AND n.matching_policy_id = m.matching_policy_id
           AND n.evaluated_offer_id IS NOT DISTINCT FROM m.evaluated_offer_id
           AND (n.evaluated_at, n.created_at) > (m.evaluated_at, m.created_at)""", m=match_id)


def test_l_s5_3b_a_run_while_an_approval_is_held_waits_for_it(client, engine, ids,
                                                             monkeypatch):
    """Order A, the window of L-S5-3b. The approval is held after its
    supersession check, before its commit. A run that would store a newer
    match of the same offer must wait on the approval (witness), and commit
    after it: the opportunity's match was current when the approval
    committed. Without the serialization the run commits while the approval
    is held, and the approval then commits an opportunity from a match that
    a committed run had already superseded."""
    from turab.services import match_review

    req, prop, [offer], [m] = _world(client, engine, ids)
    _a_newer_input(engine, offer)
    out, checked, release = {}, threading.Event(), threading.Event()
    real = match_review._superseded_by

    def held(session, match):
        found = real(session, match)
        out["approval_pid"] = session.execute(text("SELECT pg_backend_pid()")).scalar_one()
        checked.set()
        assert release.wait(30), "the approval was never released"
        return found
    monkeypatch.setattr(match_review, "_superseded_by", held)
    approval = _in_thread(engine, out, "approve",
                          lambda c: _approve(c, m["match_id"], ids.ACC_REVIEWER))
    run = None
    try:
        assert checked.wait(30), "the approval never reached its supersession check"
        run = _in_thread(engine, out, "run", lambda c: _run(c, ids, req, [prop]))
        waited = _watch(engine, out["approval_pid"], run)
        ran_while_held = not run.is_alive()
    finally:
        release.set()
        approval.join(30)
        if run is not None:
            run.join(60)
    observed = {
        "run_waited_on_the_approval": waited,
        "run_committed_while_the_approval_was_held": ran_while_held,
        "approve": out["approve"].status_code,
        "run": out["run"].status_code,
        "approval_committed_first": out["approve_done"] < out["run_done"],
        "newer_matches": _newer_matches(engine, m["match_id"]),
        "opportunity_from_the_held_match": _by_match(engine, m["match_id"]) is not None,
    }
    assert observed == {
        "run_waited_on_the_approval": True,
        "run_committed_while_the_approval_was_held": False,
        "approve": 200, "run": 201, "approval_committed_first": True,
        "newer_matches": 1, "opportunity_from_the_held_match": True,
    }, observed


def test_l_s5_3b_an_approval_waits_for_a_run_in_flight_and_is_refused_superseded(
        client, engine, ids, monkeypatch):
    """Order B. The run has stored its newer match and is held before its
    commit. The approval must wait on it (witness), read again after the
    wait, and be refused 409 MATCH_SUPERSEDED: no review, no opportunity, no
    audit row, no key consumed."""
    from turab.services import matching_run

    req, prop, [offer], [m] = _world(client, engine, ids)
    _a_newer_input(engine, offer)
    out, stored, release = {}, threading.Event(), threading.Event()
    real = matching_run.match_view

    def held(conn, match_id):
        if not stored.is_set():
            out["run_pid"] = conn.execute(text("SELECT pg_backend_pid()")).scalar_one()
            stored.set()
            assert release.wait(30), "the run was never released"
        return real(conn, match_id)
    monkeypatch.setattr(matching_run, "match_view", held)
    key = str(uuid.uuid4())
    run = _in_thread(engine, out, "run", lambda c: _run(c, ids, req, [prop]))
    approval = None
    try:
        assert stored.wait(30), "the run never stored its match"
        approval = _in_thread(engine, out, "approve",
                              lambda c: _approve(c, m["match_id"], ids.ACC_REVIEWER, key))
        waited = _watch(engine, out["run_pid"], approval)
        answered_while_held = not approval.is_alive()
    finally:
        release.set()
        run.join(60)
        if approval is not None:
            approval.join(30)
    observed = {
        "approval_waited_on_the_run": waited,
        "approval_answered_while_the_run_was_held": answered_while_held,
        "run": out["run"].status_code,
        "approve": (out["approve"].status_code, out["approve"].json().get("code")
                    or out["approve"].json().get("decision")),
        "newer_matches": _newer_matches(engine, m["match_id"]),
        "reviews": _one(engine, "SELECT count(*) FROM turab.match_reviews WHERE match_id = :m",
                        m=m["match_id"]),
        "opportunity": _by_match(engine, m["match_id"]) is not None,
        "key_records": _one(engine, "SELECT count(*) FROM turab.idempotency_records "
                                    "WHERE idempotency_key = :k", k=key),
    }
    assert observed == {
        "approval_waited_on_the_run": True,
        "approval_answered_while_the_run_was_held": False,
        "run": 201, "approve": (409, "MATCH_SUPERSEDED"), "newer_matches": 1,
        "reviews": 0, "opportunity": False, "key_records": 0,
    }, observed


# ======================================================================================
# STOP GATE E: one SALE, over HTTP only, from a new party to the customer's view
# ======================================================================================

def _call(client, method, path, account, body=None):
    headers = {"Authorization": f"Bearer {account}"}
    if method == "post":
        headers["Idempotency-Key"] = str(uuid.uuid4())
        return client.post(path, json=body or {}, headers=headers)
    return client.get(path, headers=headers)


def _created(response, *statuses):
    assert response.status_code in (statuses or (200, 201)), response.text
    return response.json()


def test_stop_gate_e_a_sale_from_a_new_party_to_the_customer_view_over_http(
        client, engine, ids, record_property):
    """Plan §6.3, the proof of STOP GATE E: one test, over HTTP only. Every
    business row is created by the API: the seed's reference data (the
    location, the policy, the reason codes) and the test accounts are the
    only rows not made here.
    1. a seller party and its consent grant; the buyer's request (for the
       existing customer party of ACC_AMINA, who will read it) and its
       criterion, brought to ACTIVE and confirmed (Slices 1–2);
    2. a property, confirmed AVAILABLE; its SALE offer, made ACTIVE and its
       terms confirmed; the consent bound to the offer (Slice 3);
    3. the run (Slice 4): one ELIGIBLE match;
    4. the review APPROVED: one opportunity (Slice 5); the share;
    5. the internal read and the customer's read of the opportunity;
    and the reconstruction and replay of STOP GATE D on the very match
    approved. Its stated limit: SALE only (G4-5R open)."""
    from decimal import Decimal

    from tests.test_slice4_step8 import _rows
    from tests.test_slice5_step4 import SCHEMAS, _validate
    from turab.matching import reconstruct

    staff, reviewer, admin = ids.ACC_OPERATOR, ids.ACC_REVIEWER, ids.ACC_ADMIN
    calls = 0

    def post(path, account, body=None, *statuses):
        nonlocal calls
        calls += 1
        return _created(_call(client, "post", path, account, body), *statuses)

    seller = post("/parties", staff, {"kind": "PERSON",
                                      "display_name": f"بائع {uuid.uuid4().hex[:6]}"})["party_id"]
    grant = post(f"/parties/{seller}/consents", staff, {
        "scope": "PRIVATE_MATCHING_ONLY", "channel": "PHONE_CONFIRMED",
        "consent_version": "v1", "granted_at": "2026-01-01T00:00:00Z"})["consent_id"]
    request = post("/requests", staff, {
        "party_id": str(ids.AMINA), "transaction_intent": "BUY", "intent": "ACTIVE_SEARCH",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED",
        "desired_property_type": "LAND", "property_type_importance": "REQUIRED",
        "budget_max_dzd": 30_000_000, "budget_importance": "REQUIRED"})["request_id"]
    post(f"/requests/{request}/criteria", staff, {
        "criterion_code": "LAND_AREA_MIN", "importance": "REQUIRED", "operator": "GTE",
        "value": 300})
    for target in ("CONTACTED", "QUALIFIED", "ACTIVE"):
        post(f"/requests/{request}/state", staff, {"target_status": target})
    post(f"/requests/{request}/reconfirm", staff, {})

    location = _one(engine, "SELECT location_id FROM turab.locations "
                            "WHERE code = 'ADR-CENTER'")
    prop = post("/properties", staff, {
        "property_type": "LAND", "supply_mode": "PUBLIC", "management_mode": "ASSISTED",
        "claim_status": "UNCLAIMED", "canonical_location_id": str(location),
        "land_area_m2": 400})["property_id"]
    post(f"/properties/{prop}/reconfirm", staff, {"availability": "AVAILABLE"})
    offer = post(f"/properties/{prop}/offers", staff, {
        "party_id": seller, "transaction_type": "SALE", "asking_price_dzd": 20_000_000,
        "price_negotiable": "NO"})["offer_id"]
    post(f"/offers/{offer}/state", staff, {"status": "ACTIVE"})
    post(f"/offers/{offer}/reconfirm", staff, {})
    post("/consents/bindings", staff, {
        "consent_id": grant, "purpose": "PRIVATE_MATCHING_ONLY",
        "resource_type": "PROPERTY_OFFER", "resource_id": offer})

    run = post(f"/requests/{request}/matching/run", staff,
               {"matching_policy_version": "0.2.0", "property_ids": [prop]})
    [match] = run["matches"]
    assert (match["eligibility"], match["evaluated_offer_id"]) == ("ELIGIBLE", offer), match
    review = post(f"/matches/{match['match_id']}/review", reviewer, {"decision": "APPROVED"})
    opportunity = review["opportunity"]["opportunity_id"]
    post(f"/opportunities/{opportunity}/share", staff, {"channel": "WEB"})

    internal = _created(_call(client, "get", f"/opportunities/{opportunity}", admin))
    assert (internal["approved_match_id"], internal["current_offer_id"],
            internal["status"], internal["validity_status"]) == (
        match["match_id"], offer, "SHARED", "VALID")
    customer = _created(_call(client, "get", f"/me/opportunities/{opportunity}",
                              ids.ACC_AMINA))
    _validate(customer, SCHEMAS["CustomerOpportunityView"])
    assert customer["opportunity_id"] == opportunity
    assert customer["property"]["property_id"] == prop

    stored, rows = _rows(engine, match["match_id"])
    assert reconstruct.reconstruct(stored, rows) == []
    assert reconstruct.replay(stored, rows) == []
    assert Decimal(str(stored["property_snapshot"]["land_area_m2"])) == Decimal("400")

    record_property("http_commands", calls)
    record_property("approved_match_id", match["match_id"])
    record_property("transaction_type", "SALE")


# ======================================================================================
# E04 on real opportunities (red-team E04; plan §6.2)
# ======================================================================================

def _ready_offer(client, ids, prop):
    """An ACTIVE SALE offer of BRAHIM on `prop`, terms confirmed, with its own
    PRIVATE_MATCHING_ONLY grant bound to it; the property confirmed AVAILABLE.
    Over HTTP."""
    staff = ids.ACC_OPERATOR
    _created(_call(client, "post", f"/properties/{prop}/reconfirm", staff,
                   {"availability": "AVAILABLE"}))
    offer = _created(_call(client, "post", f"/properties/{prop}/offers", staff, {
        "party_id": str(ids.BRAHIM), "transaction_type": "SALE",
        "asking_price_dzd": 20_000_000, "price_negotiable": "NO"}))["offer_id"]
    _created(_call(client, "post", f"/offers/{offer}/state", staff, {"status": "ACTIVE"}))
    _created(_call(client, "post", f"/offers/{offer}/reconfirm", staff, {}))
    grant = _created(_call(client, "post", f"/parties/{ids.BRAHIM}/consents", staff, {
        "scope": "PRIVATE_MATCHING_ONLY", "channel": "PHONE_CONFIRMED",
        "consent_version": "v1", "granted_at": "2026-01-01T00:00:00Z"}))["consent_id"]
    _created(_call(client, "post", "/consents/bindings", staff, {
        "consent_id": grant, "purpose": "PRIVATE_MATCHING_ONLY",
        "resource_type": "PROPERTY_OFFER", "resource_id": offer}))
    return offer


def _active_request(client, ids):
    staff = ids.ACC_OPERATOR
    request = _created(_call(client, "post", "/requests", staff, {
        "party_id": str(ids.AMINA), "transaction_intent": "BUY", "intent": "ACTIVE_SEARCH",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED",
        "desired_property_type": "LAND", "property_type_importance": "REQUIRED",
        "budget_max_dzd": 30_000_000, "budget_importance": "REQUIRED"}))["request_id"]
    _created(_call(client, "post", f"/requests/{request}/criteria", staff, {
        "criterion_code": "LAND_AREA_MIN", "importance": "REQUIRED", "operator": "GTE",
        "value": 300}))
    for target in ("CONTACTED", "QUALIFIED", "ACTIVE"):
        _created(_call(client, "post", f"/requests/{request}/state", staff,
                       {"target_status": target}))
    _created(_call(client, "post", f"/requests/{request}/reconfirm", staff, {}))
    return request


def test_e04_consolidation_with_two_real_open_opportunities_surfaces_work_and_closes_none(
        client, engine, ids):
    """Red-team E04, on opportunities made by the run and the APPROVED review
    (Slice 3's E04 test made them by SQL, before Slice 5 existed).
    - One request, two properties that are the same place; each has its own
      ACTIVE offer and is matched; both matches are approved: two open
      opportunities, one per property, which is allowed while they are two
      properties.
    - The identity review then confirms them SAME, with C canonical and A
      the alias.
    - One RESOLVE_IDENTITY task names A's opportunity and lists C's as the
      duplicate. Neither opportunity is closed or changed."""
    from tests.test_slice3_identity import _generate, _pair, _review

    _, canonical, alias = _pair(client, ids, engine=engine, land=400)
    request = _active_request(client, ids)
    _ready_offer(client, ids, canonical)
    _ready_offer(client, ids, alias)
    run = _created(_call(client, "post", f"/requests/{request}/matching/run", ids.ACC_OPERATOR,
                         {"matching_policy_version": "0.2.0",
                          "property_ids": [canonical, alias]}))
    by_property = {m["property_id"]: m for m in run["matches"]}
    assert {m["eligibility"] for m in by_property.values()} == {"ELIGIBLE"}
    opportunities = {}
    for prop in (canonical, alias):
        approved = _created(_approve(client, by_property[prop]["match_id"], ids.ACC_REVIEWER))
        opportunities[prop] = approved["opportunity"]["opportunity_id"]
    before = _all(engine, "SELECT to_jsonb(o)::text AS row FROM turab.opportunities o "
                          "WHERE opportunity_id IN (:a, :c) ORDER BY opportunity_id",
                  a=opportunities[alias], c=opportunities[canonical])

    cid = _generate(client, ids, canonical)[0]["identity_candidate_id"]
    r = _review(client, ids, cid, decision="CONFIRMED_SAME", canonical_property_id=canonical)
    assert r.status_code == 200, r.text

    tasks = _all(engine, """SELECT task_type::text AS type, payload FROM turab.tasks
                             WHERE property_id = :a AND task_type = 'RESOLVE_IDENTITY'""",
                 a=alias)
    assert len(tasks) == 1, tasks
    payload = tasks[0]["payload"]
    assert (payload["affected"], payload["opportunity_id"],
            payload["duplicate_open_opportunity_ids"]) == (
        "OPPORTUNITY", opportunities[alias], [opportunities[canonical]])
    after = _all(engine, "SELECT to_jsonb(o)::text AS row FROM turab.opportunities o "
                         "WHERE opportunity_id IN (:a, :c) ORDER BY opportunity_id",
                 a=opportunities[alias], c=opportunities[canonical])
    assert after == before, "nothing is closed or changed"


# ======================================================================================
# K05: the replay of each Slice 5 POST
# ======================================================================================

def _k05_world(client, engine, ids, command):
    """The object each command acts on, and its body; and the alternative body
    for the same key."""
    from tests.test_slice5_step4 import _opportunity

    if command.startswith("review"):
        *_, [m] = _world(client, engine, ids)
        body = {"review-REJECTED": {"decision": "REJECTED", "reason_code": "OTHER"},
                "review-NMI": {"decision": "NEED_MORE_INFORMATION",
                               "reason_code": "DOCUMENT_NOT_KNOWN"},
                "review-APPROVED": {"decision": "APPROVED"}}[command]
        other = {"decision": "REJECTED", "reason_code": "OTHER", "reason_text": "other"}
        return f"/matches/{m['match_id']}/review", body, other, ids.ACC_REVIEWER
    world = _opportunity(client, engine, ids, share=False)
    path = f"/opportunities/{world['opportunity']}/{command}"
    body, other = {"revalidate": ({"note": "k05"}, {"note": "other"}),
                   "share": ({"channel": "WEB", "note": "k05"}, {"channel": "SMS"}),
                   "close": ({"reason_code": "OTHER", "note": "k05"},
                             {"reason_code": "UNREACHABLE"})}[command]
    return path, body, other, ids.ACC_OPERATOR


def _counts(engine):
    return {table: _one(engine, f"SELECT count(*) FROM turab.{table}")
            for table in ("match_reviews", "opportunities", "tasks", "interactions")} | {
        "audit": _one(engine, "SELECT coalesce(max(audit_id), 0) FROM turab.audit_log")}


@pytest.mark.parametrize("command", ["review-REJECTED", "review-NMI", "review-APPROVED",
                                     "revalidate", "share", "close"])
def test_k05_each_slice_5_post_replays_and_a_changed_body_is_409(client, engine, ids,
                                                                 command):
    """Red-team K05: the same key and body return the first response and
    write nothing more; the same key with another body is 409
    IDEMPOTENCY_KEY_CONFLICT and writes nothing."""
    path, body, other, account = _k05_world(client, engine, ids, command)
    key = str(uuid.uuid4())
    headers = {"Authorization": f"Bearer {account}", "Idempotency-Key": key}
    first = client.post(path, json=body, headers=headers)
    assert first.status_code == 200, first.text
    after_first = _counts(engine)
    again = client.post(path, json=body, headers=headers)
    assert (again.status_code, again.json()) == (first.status_code, first.json())
    assert _counts(engine) == after_first, "a replay writes nothing"
    changed = client.post(path, json=other, headers=headers)
    assert (changed.status_code, changed.json()["code"]) == (409, "IDEMPOTENCY_KEY_CONFLICT")
    assert _counts(engine) == after_first


# ======================================================================================
# The currency check's request lock, for revalidate (L-S5-3b's neighbour)
# ======================================================================================

def test_a_revalidate_waits_for_a_request_writer_and_reads_its_commit(client, engine, ids):
    """Since L-S5-3b the approval takes the request `FOR UPDATE` itself. The
    currency check's own `FOR NO KEY UPDATE` on the request still serializes
    revalidate and share with a writer of the request. A writer holds an
    uncommitted status change; a revalidate waits on it (witness), then
    records what the writer committed."""
    from tests.test_slice5_step4 import _opportunity

    world = _opportunity(client, engine, ids, share=False)
    writer = engine.connect()
    out = {}
    try:
        tx = writer.begin()
        writer.execute(text("SELECT set_config('app.account_id', :a, true)"),
                       {"a": str(ids.ACC_ADMIN)})
        wpid = writer.execute(text("SELECT pg_backend_pid()")).scalar_one()
        writer.execute(text("UPDATE turab.requests SET status = 'PAUSED' "
                            "WHERE request_id = :r"), {"r": world["request"]})
        revalidate = _in_thread(engine, out, "revalidate", lambda c: _call(
            c, "post", f"/opportunities/{world['opportunity']}/revalidate", ids.ACC_OPERATOR,
            {}))
        waited = _watch(engine, wpid, revalidate)
        tx.commit()
    finally:
        writer.close()
    revalidate.join(30)
    assert waited, "the revalidate never waited on the request writer"
    body = out["revalidate"].json()
    assert (out["revalidate"].status_code, body["validity_status"]) == (
        200, "NEEDS_CONFIRMATION"), body
    assert [(r["fact"], r["value"]) for r in body["validity_reasons"]] == [
        ("REQUEST_STATUS", "PAUSED")]


# ======================================================================================
# K06 stays UNPROVEN: the trigger-level refusals, labelled as such (plan §6.2, G5-13)
# ======================================================================================

@pytest.mark.parametrize("statement", [
    "UPDATE turab.match_reviews SET reason_text = 'edited' WHERE match_review_id = :r",
    "DELETE FROM turab.match_reviews WHERE match_review_id = :r",
])
def test_trigger_level_a_review_row_cannot_be_changed_or_deleted(client, engine, ids,
                                                                 statement):
    """TRIGGER-LEVEL, NOT K06. The frozen `prevent_immutable_history_change`
    refuses a change or a delete of a review row, even from the application
    role. K06 (the application role cannot hard-delete protected history)
    needs a role that is neither superuser nor owner, which no test of this
    slice runs under (EN-02, G5-13 (b)(ii)): K06 stays UNPROVEN."""
    from sqlalchemy.exc import DBAPIError

    *_, [m] = _world(client, engine, ids)
    _approve(client, m["match_id"], ids.ACC_REVIEWER)
    review = _one(engine, "SELECT match_review_id FROM turab.match_reviews WHERE match_id = :m",
                  m=m["match_id"])
    with engine.connect() as conn:
        tx = conn.begin()
        try:
            with pytest.raises(DBAPIError):
                conn.execute(text(statement), {"r": review})
        finally:
            tx.rollback()
    assert _one(engine, "SELECT count(*) FROM turab.match_reviews WHERE match_review_id = :r",
                r=review) == 1
