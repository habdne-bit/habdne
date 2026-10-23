"""Slice 6 step 5: the mandatory and red-team tests, end to end.

Ref: `docs/gate/SLICE_6_PLAN.md` revision 13: §6.1 (the three mandatory
tests), §6.2 (red-team I01, I03, D02 / R9.3, G04 / G06), §8 step 5; the
review of `0fae42c` (a HIGH task shared by two candidates, `match_id` null,
understandable in `GET /tasks`; the replay's stated limit on the
diagnostic's own `input_hash`).

**End to end.** Every business row is made by the API:
- the request, its criteria, its state and its confirmation;
- the parties and their consents;
- the properties, their confirmation and their documents (`/resolutions`);
- the offers, their state, their confirmation and their consent bindings.

The seed's reference data (locations, the policy, the reason codes) and the
test accounts are the only rows not made here. The run, the diagnostic, the
task list and the completion are read and driven over HTTP. The database is
read only to replay a stored row and to check what was NOT written.

**Isolation.** HTTP tests commit to the shared test database; each builds its
own request, parties, properties and offers. `GET /tasks` lists every task,
so a test keeps only the tasks of its own request.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.test_slice4_step7 import VERSION, _all, _one
from tests.test_slice6_step2 import _all_pages
from tests.test_slice6_step4 import _replay, _stored_row
from turab.auth.audit import AccessAuditor, RecordingAuditSink


@pytest.fixture
def client(engine):
    from turab.app import create_app

    with TestClient(create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink())),
                    raise_server_exceptions=True) as c:
        yield c


# ======================================================================================
# The world, over HTTP
# ======================================================================================

def _post(client, path, account, body=None, *ok):
    r = client.post(path, json=body or {}, headers={"Authorization": f"Bearer {account}",
                                                    "Idempotency-Key": str(uuid.uuid4())})
    assert r.status_code in (ok or (200, 201)), (path, r.text)
    return r.json()


def _get(client, path, account, **params):
    r = client.get(path, params=params, headers={"Authorization": f"Bearer {account}"})
    assert r.status_code == 200, (path, r.text)
    return r.json()


def _loc(engine, code):
    return str(_one(engine, "SELECT location_id FROM turab.locations WHERE code = :c", c=code))


def _request(client, ids, *, budget_max=24_000_000, criteria=()):
    """A BUY request for LAND of the customer AMINA, ACTIVE and confirmed.
    `budget_max=None` leaves the maximum unstated while it stays REQUIRED."""
    staff = ids.ACC_OPERATOR
    request = _post(client, "/requests", staff, {
        "party_id": str(ids.AMINA), "transaction_intent": "BUY", "intent": "ACTIVE_SEARCH",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED",
        "desired_property_type": "LAND", "property_type_importance": "REQUIRED",
        "budget_max_dzd": budget_max, "budget_importance": "REQUIRED"})["request_id"]
    for criterion in criteria:
        _post(client, f"/requests/{request}/criteria", staff, criterion)
    for target in ("CONTACTED", "QUALIFIED", "ACTIVE"):
        _post(client, f"/requests/{request}/state", staff, {"target_status": target})
    _post(client, f"/requests/{request}/reconfirm", staff, {})
    return request


def _location(engine, *codes):
    return {"criterion_code": "LOCATION", "importance": "REQUIRED", "operator": "IN",
            "value": [_loc(engine, c) for c in codes]}


LAND_BOOK = {"criterion_code": "DOCUMENT_TYPE", "importance": "REQUIRED", "operator": "EQ",
             "value": "LAND_BOOK"}


def _property(client, engine, ids, code, *, ptype="LAND", document=None):
    """A property at the location `code`, confirmed AVAILABLE; its document
    resolved over HTTP when given, else UNKNOWN."""
    staff = ids.ACC_OPERATOR
    prop = _post(client, "/properties", staff, {
        "property_type": ptype, "supply_mode": "PUBLIC", "management_mode": "ASSISTED",
        "claim_status": "UNCLAIMED", "canonical_location_id": _loc(engine, code)})["property_id"]
    _post(client, f"/properties/{prop}/reconfirm", staff, {"availability": "AVAILABLE"})
    if document is not None:
        _document(client, ids, prop, document)
    return prop


def _document(client, ids, prop, value):
    _post(client, "/resolutions", ids.ACC_OPERATOR, {
        "subject": {"type": "PROPERTY", "id": prop}, "attribute_code": "DOCUMENT_TYPE",
        "resolved_value": value})


def _offer(client, ids, prop, *, price=20_000_000, negotiable="NO", expectation=None,
           consent=True):
    """An ACTIVE SALE offer of a new seller party, its terms confirmed, its own
    PRIVATE_MATCHING_ONLY grant bound to it (unless `consent` is false: then
    no grant, and the permission gate has a reason)."""
    staff = ids.ACC_OPERATOR
    seller = _post(client, "/parties", staff, {
        "kind": "PERSON", "display_name": f"بائع {uuid.uuid4().hex[:6]}"})["party_id"]
    body = {"party_id": seller, "transaction_type": "SALE", "asking_price_dzd": price,
            "price_negotiable": negotiable}
    if expectation is not None:
        body["seller_expectation_dzd"] = expectation
    offer = _post(client, f"/properties/{prop}/offers", staff, body)["offer_id"]
    _post(client, f"/offers/{offer}/state", staff, {"status": "ACTIVE"})
    _post(client, f"/offers/{offer}/reconfirm", staff, {})
    if not consent:
        return offer
    grant = _post(client, f"/parties/{seller}/consents", staff, {
        "scope": "PRIVATE_MATCHING_ONLY", "channel": "PHONE_CONFIRMED",
        "consent_version": "v1", "granted_at": "2026-01-01T00:00:00Z"})["consent_id"]
    _post(client, "/consents/bindings", staff, {
        "consent_id": grant, "purpose": "PRIVATE_MATCHING_ONLY",
        "resource_type": "PROPERTY_OFFER", "resource_id": offer})
    return offer


def _run(client, ids, request, props):
    return _post(client, f"/requests/{request}/matching/run", ids.ACC_OPERATOR,
                 {"matching_policy_version": VERSION, "property_ids": list(props)}, 201)


def _diagnostic(client, ids, request):
    return _get(client, f"/requests/{request}/diagnostic", ids.ACC_OPERATOR)


def _tasks(client, ids, request):
    """The tasks of `request` as `GET /tasks` lists them, every page read."""
    items, _ = _all_pages(client, ids.ACC_OPERATOR)
    return [t for t in items if t["request_id"] == request]


def _by_property(body):
    return {m["property_id"]: m for m in body["matches"]}


def _numbers(document):
    """Every number a JSON document holds, at any depth."""
    if isinstance(document, dict):
        return [n for v in document.values() for n in _numbers(v)]
    if isinstance(document, list):
        return [n for v in document for n in _numbers(v)]
    return [document] if isinstance(document, (int, float)) and not isinstance(
        document, bool) else []


def _keys(document):
    if isinstance(document, dict):
        return set(document) | {k for v in document.values() for k in _keys(v)}
    if isinstance(document, list):
        return {k for v in document for k in _keys(v)}
    return set()


# ======================================================================================
# §6.1: the three mandatory tests, end to end
# ======================================================================================

def test_mandatory_1_over_http_the_document_task_outranks_the_new_location(
        client, engine, ids):
    """"document UNKNOWN on otherwise exact candidate becomes higher-priority
    task than suggesting a new location" (§6.1, I01, M-12). R-001 with P08
    (document UNKNOWN, all else PASS) and P03 (LOCATION FAIL only), one run:
    - the diagnostic's first suggested action is P08's VERIFY_DOCUMENT, HIGH;
    - the location is a scenario only, subordinate to that action;
    - `GET /tasks` lists one task for the request: HIGH, P08's match, the
      document; no task names P03;
    - the stored row replays."""
    req = _request(client, ids, criteria=[_location(engine, "ADR-NEW-TIL"), LAND_BOOK])
    p08 = _property(client, engine, ids, "ADR-NEW-TIL")
    p03 = _property(client, engine, ids, "ADR-AIRPORT", document="LAND_BOOK")
    for p in (p08, p03):
        _offer(client, ids, p)
    run = _by_property(_run(client, ids, req, [p08, p03]))
    assert (run[p08]["eligibility"], run[p03]["eligibility"]) == (
        "NEED_MORE_INFORMATION", "REJECTED")

    d = _diagnostic(client, ids, req)
    first = d["suggested_actions"][0]
    assert (first["type"], first["priority"], first["subject"]["entity"],
            first["subject"]["id"]) == ("VERIFY_DOCUMENT", "HIGH", "PROPERTY", p08)
    assert not [a for a in d["suggested_actions"] if a["subject"]["id"] == p03]
    [location] = d["relaxation_scenarios"]
    assert (location["criterion"], location["scenario"], location["subordinate_to"]) == (
        "LOCATION", "WIDEN_AREA", [first["key"]])
    assert [n["property_id"] for n in location["near_matches"]] == [p03]

    [task] = _tasks(client, ids, req)
    assert (task["task_type"], task["priority"], task["status"], task["property_id"],
            task["match_id"], task["payload"]["diagnostic_run_id"]) == (
        "VERIFY_DOCUMENT", "HIGH", "OPEN", p08, run[p08]["match_id"], d["diagnostic_run_id"])
    assert _replay(engine, d["diagnostic_run_id"]) == {"R": [], "D": []}


def test_mandatory_2_over_http_three_hard_failures_raise_no_task(client, engine, ids):
    """"candidate failing three hard criteria does not receive high-priority
    task for an unrelated unknown" (§6.1, §3.3). Two APARTMENTs, each outside
    the location, above the maximum and not negotiable:
    - one with its document UNKNOWN and no consent bound to its offer (a
      permission reason as well);
    - one with its document known (LAND_BOOK), so nothing but the three
      failures keeps it from being a near match.
    No action (no information work, no permission work), no scenario (neither
    is a near match), no task; the unknown is counted blocking and not
    actionable. The two shapes were added after the first mutation run (M2,
    M3 survived it: `SLICE6-STEP5-MUTATIONS-FIRST-RUN.txt`)."""
    req = _request(client, ids, criteria=[_location(engine, "ADR-NEW-TIL"), LAND_BOOK])
    bad = _property(client, engine, ids, "ADR-AIRPORT", ptype="APARTMENT")
    known = _property(client, engine, ids, "ADR-AIRPORT", ptype="APARTMENT",
                      document="LAND_BOOK")
    _offer(client, ids, bad, price=30_000_000, consent=False)
    _offer(client, ids, known, price=30_000_000)
    run = _by_property(_run(client, ids, req, [bad, known]))
    for m in run.values():
        assert m["eligibility"] == "REJECTED"
        failed = {key.split("#")[0] for key, c in m["explanation"]["criteria"].items()
                  if c["compatibility"] == "FAIL"}
        assert {"LOCATION", "BUDGET_MAX", "PROPERTY_TYPE"} <= failed, failed
    assert [r for r in run[bad]["explanation"]["reasons"] if r["gate"] == "PERMISSION"]
    d = _diagnostic(client, ids, req)
    assert (d["suggested_actions"], d["relaxation_scenarios"]) == ([], [])
    assert d["blocker_summary"]["unknowns"]["DOCUMENT_TYPE#1"] == {
        "blocking": 1, "non_blocking": 0, "actionable": 0, "high_value": 0}
    assert _tasks(client, ids, req) == []
    assert _replay(engine, d["diagnostic_run_id"]) == {"R": [], "D": []}


def test_mandatory_3_over_http_the_magnitudes_after_the_document_fails(client, engine, ids):
    """"relaxation scenario reports magnitude (e.g. +150M centimes / adjacent
    area), not only 'remove criterion.'" (§6.1, M-13). The world of test 1,
    P08's document then resolved to another document (a FAIL), and a third
    property at max + 1,500,000 DZD, not negotiable. Three near matches, three
    magnitudes:
    - BUDGET_MAX: `budget_delta_dzd` 1,500,000, at the asking price (F6-1);
    - LOCATION: the widening's level and target (G6-6); no `adjacent_zone`
      (F6-3);
    - DOCUMENT_TYPE: the document named, only if the user chooses it."""
    req = _request(client, ids, criteria=[_location(engine, "ADR-NEW-TIL"), LAND_BOOK])
    p08 = _property(client, engine, ids, "ADR-NEW-TIL")
    p03 = _property(client, engine, ids, "ADR-AIRPORT", document="LAND_BOOK")
    pb = _property(client, engine, ids, "ADR-NEW-TIL", document="LAND_BOOK")
    _offer(client, ids, p08)
    _offer(client, ids, p03)
    _offer(client, ids, pb, price=25_500_000)
    _document(client, ids, p08, "ADMINISTRATIVE_DEED")
    run = _by_property(_run(client, ids, req, [p08, p03, pb]))
    assert {m["eligibility"] for m in run.values()} == {"REJECTED"}

    d = _diagnostic(client, ids, req)
    scenarios = {s["criterion"]: s for s in d["relaxation_scenarios"]}
    assert set(scenarios) == {"BUDGET_MAX", "LOCATION", "DOCUMENT_TYPE"}
    budget = scenarios["BUDGET_MAX"]
    assert (budget["scenario"], budget["magnitude"]) == (
        "RAISE_MAXIMUM", {"budget_delta_dzd": 1_500_000, "stated_at": "ASKING_PRICE"})
    assert [n["property_id"] for n in budget["near_matches"]] == [pb]
    location = scenarios["LOCATION"]
    assert (location["scenario"], location["level"]) == ("WIDEN_AREA", "COMMUNE")
    assert location["widen_to"] == _one(
        engine, "SELECT parent_id::text FROM turab.locations WHERE code = 'ADR-NEW-TIL'")
    assert [n["property_id"] for n in location["near_matches"]] == [p03]
    document = scenarios["DOCUMENT_TYPE"]
    assert (document["scenario"], document["named"], document["only_if_user_chooses"]) == (
        "ACCEPT_DOCUMENT", "ADMINISTRATIVE_DEED", True)
    assert "adjacent_zone" not in _keys(d)
    for s in scenarios.values():
        [near] = s["near_matches"]
        assert near["would_reach"]["eligibility"] == "ELIGIBLE"
    assert _replay(engine, d["diagnostic_run_id"]) == {"R": [], "D": []}


# ======================================================================================
# The review of 0fae42c: a HIGH task shared by two candidates, `match_id` null
# ======================================================================================

def test_a_high_task_shared_by_two_offers_names_no_match_and_is_understood(
        client, engine, ids):
    """One property, its document UNKNOWN, two ACTIVE SALE offers: two
    candidates, one HIGH work (the PROPERTY's document).
    - **One task,** `match_id` null (no match is chosen), `property_id` the
      property (the subject is a property), its request.
    - **Understood from `GET /tasks` alone:** its type, priority, title,
      reason and subject state the work; the subject is the diagnostic's
      entry's, whose two candidates are the run's two matches; the property
      and both matches are readable.
    - **Done over HTTP:** completed with an observation, then the document
      resolved; the next run suggests nothing and raises nothing; the DONE
      task stays DONE.
    Both rows replay."""
    staff = ids.ACC_OPERATOR
    req = _request(client, ids, criteria=[LAND_BOOK])
    prop = _property(client, engine, ids, "ADR-NEW-TIL")
    offers = {_offer(client, ids, prop), _offer(client, ids, prop)}
    matches = _run(client, ids, req, [prop])["matches"]
    assert {m["evaluated_offer_id"] for m in matches} == offers
    assert {m["eligibility"] for m in matches} == {"NEED_MORE_INFORMATION"}

    d = _diagnostic(client, ids, req)
    [entry] = d["suggested_actions"]
    assert (entry["type"], entry["priority"], entry["candidate_count"]) == (
        "VERIFY_DOCUMENT", "HIGH", 2)
    assert {c["offer_id"] for c in entry["candidates"]} == offers

    [task] = _tasks(client, ids, req)
    assert (task["match_id"], task["property_id"], task["request_id"]) == (None, prop, req)
    assert (task["task_type"], task["priority"], task["status"], task["title"],
            task["reason_code"]) == ("VERIFY_DOCUMENT", "HIGH", "OPEN",
                                     "Verify the property's document", "DOCUMENT_NOT_KNOWN")
    subject = task["payload"]["subject"]
    assert subject == {k: entry["subject"][k] for k in subject}
    assert (subject["entity"], subject["id"], subject["criterion"]) == (
        "PROPERTY", prop, "DOCUMENT_TYPE")
    assert task["payload"]["diagnostic_run_id"] == d["diagnostic_run_id"]
    assert _get(client, f"/properties/{prop}", staff)["property_id"] == prop
    for m in matches:
        assert _get(client, f"/matches/{m['match_id']}", staff)["property_id"] == prop

    observation = _post(client, "/observations", staff, {
        "kind": "CALL_NOTE", "party_id": str(ids.BRAHIM),
        "observed_at": "2026-09-01T10:00:00Z",
        "raw_text": "the owner read the land book number"}, 201)["observation_id"]
    done = _post(client, f"/tasks/{task['task_id']}/complete", staff, {
        "outcome_code": "TASK_INFORMATION_OBTAINED", "evidence_observation_id": observation})
    assert done["status"] == "DONE"
    _document(client, ids, prop, "LAND_BOOK")
    again = _run(client, ids, req, [prop])
    assert {m["eligibility"] for m in again["matches"]} == {"ELIGIBLE"}
    assert again["diagnostic"]["suggested_actions"] == []
    assert [(t["task_id"], t["status"]) for t in _tasks(client, ids, req)] == [
        (task["task_id"], "DONE")]
    for row in (d["diagnostic_run_id"], again["diagnostic"]["diagnostic_run_id"]):
        assert _replay(engine, row) == {"R": [], "D": []}


def test_a_high_task_shared_by_two_properties_names_only_the_request(client, engine, ids):
    """The request's maximum is REQUIRED and not stated: every candidate's one
    unknown is the REQUEST's own work. Two properties, one HIGH entry of two
    candidates, one task with `property_id` AND `match_id` null. What states the
    work in `GET /tasks` is the request and the subject: entity REQUEST, the
    BUDGET_MAX criterion, the basis BUDGET_MAX_NOT_STATED (its `reason_code` is
    null: the basis has none), and its title names the request (F6-22, review
    of 3657973)."""
    req = _request(client, ids, budget_max=None)
    props = [_property(client, engine, ids, "ADR-NEW-TIL") for _ in range(2)]
    for p in props:
        _offer(client, ids, p)
    matches = _run(client, ids, req, props)["matches"]
    assert {m["eligibility"] for m in matches} == {"NEED_MORE_INFORMATION"}
    d = _diagnostic(client, ids, req)
    [entry] = d["suggested_actions"]
    assert (entry["priority"], entry["candidate_count"]) == ("HIGH", 2)
    assert {c["property_id"] for c in entry["candidates"]} == set(props)

    [task] = _tasks(client, ids, req)
    assert (task["request_id"], task["property_id"], task["match_id"], task["reason_code"]) == (
        req, None, None, None)
    assert (task["task_type"], task["priority"], task["title"]) == (
        "CONFIRM_PRICE", "HIGH", "Confirm the request's maximum budget")
    assert task["payload"]["subject"] == {
        "entity": "REQUEST", "id": req, "gate": "INFORMATION", "criterion": "BUDGET_MAX",
        "ordinal": 1, "basis": "BUDGET_MAX_NOT_STATED"}
    assert _get(client, f"/requests/{req}", ids.ACC_OPERATOR)["budget_max_dzd"] is None
    assert _replay(engine, d["diagnostic_run_id"]) == {"R": [], "D": []}


def test_f6_22_the_request_tasks_title_names_the_request(client, engine, ids):
    """F6-22, DECIDED in the review of 3657973 (inverted from the measurement
    delivered at 3657973, which accepted the offer's title). The title is
    fixed by the task's type AND its subject's entity: a CONFIRM_PRICE task
    whose subject is the REQUEST (its maximum not stated) is "Confirm the
    request's maximum budget"; it names no offer."""
    req = _request(client, ids, budget_max=None)
    prop = _property(client, engine, ids, "ADR-NEW-TIL")
    _offer(client, ids, prop)
    _run(client, ids, req, [prop])
    [task] = _tasks(client, ids, req)
    assert (task["task_type"], task["payload"]["subject"]["entity"],
            task["payload"]["subject"]["basis"]) == (
        "CONFIRM_PRICE", "REQUEST", "BUDGET_MAX_NOT_STATED")
    assert task["title"] == "Confirm the request's maximum budget"
    assert "offer" not in task["title"]


def test_f6_22_an_offer_subject_keeps_the_offers_title(client, engine, ids):
    """F6-22, the other half of the decision: a CONFIRM_PRICE task whose
    subject is the OFFER (its price above the maximum, negotiation not
    confirmed) keeps "Confirm the offer's price terms", and names its
    match."""
    req = _request(client, ids)
    prop = _property(client, engine, ids, "ADR-NEW-TIL")
    offer = _offer(client, ids, prop, price=26_000_000, negotiable="YES")
    [m] = _run(client, ids, req, [prop])["matches"]
    [task] = _tasks(client, ids, req)
    assert (task["task_type"], task["priority"], task["payload"]["subject"]["entity"],
            task["payload"]["subject"]["id"], task["match_id"]) == (
        "CONFIRM_PRICE", "HIGH", "PROPERTY_OFFER", offer, m["match_id"])
    assert task["title"] == "Confirm the offer's price terms"


def test_f6_22_an_old_title_stays_after_done_and_new_work_gets_the_corrected_title(client, engine, ids):
    """The fate of a row stored before the fix (review of 3657973: a code
    change is not assumed to correct an existing row). The row is the run's
    own task, its title then set by SQL to the old one: the only way to hold,
    in this database, a row as the code before the fix wrote it (labelled so).
    - A later run changes nothing of it and raises nothing: the work is open,
      and no path updates a title.
    - Completed over HTTP, it is DONE and KEEPS its old title: completing a
      task does not change its title, and no path ever does.
    - The next run raises the work again as a NEW task, which carries the
      corrected title; the old row stays as it was.
    Named `test_f6_22_a_task_stored_with_the_old_title_keeps_it_until_done`
    at ce8cfa0; renamed in the review of 1c27241, whose reading the old name
    invited ("until DONE" suggested the title changes on completion). The
    assertions are unchanged.
    The count of such rows actually stored is in
    `evidence/SLICE6-STEP5-F6-22-STORED-TITLES.txt`."""
    old = "Confirm the offer's price terms"
    req = _request(client, ids, budget_max=None)
    prop = _property(client, engine, ids, "ADR-NEW-TIL")
    _offer(client, ids, prop)
    _run(client, ids, req, [prop])
    [task] = _tasks(client, ids, req)
    with engine.begin() as conn:
        conn.execute(text("UPDATE turab.tasks SET title = :t WHERE task_id = :i"),
                     {"t": old, "i": task["task_id"]})
    stored = _tasks(client, ids, req)
    _run(client, ids, req, [prop])
    assert _tasks(client, ids, req) == stored
    assert stored[0]["title"] == old
    done = _post(client, f"/tasks/{task['task_id']}/complete", ids.ACC_OPERATOR,
                 {"outcome_code": "TASK_INFORMATION_UNAVAILABLE"})
    assert done["status"] == "DONE"
    _run(client, ids, req, [prop])
    first, second = _tasks(client, ids, req)
    assert (first["task_id"], first["status"], first["title"]) == (task["task_id"], "DONE", old)
    assert (second["status"], second["title"]) == ("OPEN", "Confirm the request's maximum budget")


# ======================================================================================
# §6.2: red-team cases, end to end
# ======================================================================================

def test_i03_a_scenario_changes_no_request_and_an_explicit_criterion_does(client, engine, ids):
    """I03 (§3.1): a run producing +1,500,000 DZD leaves the request, its
    `version` and its criteria as they were. Then an explicit
    `postRequestsRequestIdCriteria` changes it, and the next run sees it: its
    diagnostic records the new version, and its match evaluates the new
    criterion."""
    staff = ids.ACC_OPERATOR
    req = _request(client, ids)
    prop = _property(client, engine, ids, "ADR-NEW-TIL", document="LAND_BOOK")
    _offer(client, ids, prop, price=25_500_000)
    before = _get(client, f"/requests/{req}", staff)
    first = _run(client, ids, req, [prop])["diagnostic"]
    [s] = first["relaxation_scenarios"]
    assert s["magnitude"]["budget_delta_dzd"] == 1_500_000
    assert _get(client, f"/requests/{req}", staff) == before

    _post(client, f"/requests/{req}/criteria", staff, {
        **LAND_BOOK, "importance": "PREFERRED"})
    after = _get(client, f"/requests/{req}", staff)
    assert after["version"] > before["version"]
    [m] = _run(client, ids, req, [prop])["matches"]
    assert "DOCUMENT_TYPE#1" in m["explanation"]["criteria"]
    versions = [r["request_version"] for r in _all(engine, """
        SELECT request_version FROM turab.match_diagnostic_runs WHERE request_id = :r
         ORDER BY run_at""", r=req)]
    assert versions == [before["version"], after["version"]]


def test_d02_the_expectation_reaches_no_diagnostic_task_or_slice_6_audit(client, engine, ids):
    """D02 / R9.3 (§3.4), on what Slice 6 renders and writes. An expectation
    (25,000,000) between the maximum (24,000,000) and the asking price
    (26,000,000):
    - the scenario's magnitude is ask − max = 2,000,000, never exp − max;
    - neither the expectation nor exp − max is a number, nor
      `seller_expectation_dzd` a key, of: the diagnostic (`GET`), the run's
      `diagnostic`, the request's tasks (`GET /tasks`), and the audit rows of
      the diagnostic and of the tasks.
    A second property, its document UNKNOWN, raises a task, so the task list
    is not empty. What the staff match carries is Slice 4's, witnessed by
    `test_f6_21_the_staff_match_keeps_the_expectation_the_boundary_witness`."""
    expectation = 25_000_000
    req = _request(client, ids, criteria=[LAND_BOOK])
    near = _property(client, engine, ids, "ADR-NEW-TIL", document="LAND_BOOK")
    unknown = _property(client, engine, ids, "ADR-NEW-TIL")
    _offer(client, ids, near, price=26_000_000, expectation=expectation)
    _offer(client, ids, unknown)
    run = _run(client, ids, req, [near, unknown])
    d = _diagnostic(client, ids, req)
    [s] = d["relaxation_scenarios"]
    assert s["magnitude"]["budget_delta_dzd"] == 2_000_000
    tasks = _tasks(client, ids, req)
    assert len(tasks) == 1
    audit = [r["row"] for r in _all(engine, """
        SELECT new_row AS row FROM turab.audit_log
         WHERE (entity_table = 'match_diagnostic_runs' AND entity_id = :d)
            OR (entity_table = 'tasks' AND entity_id = :t)""",
        d=d["diagnostic_run_id"], t=tasks[0]["task_id"])]
    assert len(audit) == 2
    for name, document in (("GET diagnostic", d), ("the run's diagnostic", run["diagnostic"]),
                           ("GET /tasks", tasks), ("Slice 6 audit", audit)):
        assert not {expectation, expectation - 24_000_000} & set(_numbers(document)), name
        assert "seller_expectation_dzd" not in _keys(document), name


def test_f6_21_the_staff_match_keeps_the_expectation_the_boundary_witness(
        client, engine, ids):
    """The witness of a boundary (F6-21, DECIDED in the review of 3657973):
    the rule of §3.4 and §6.2's D02 binds what Slice 6 generates (the D02
    test above), not every output of the run. Slice 4 §3.5 (decided) keeps
    `seller_expectation_dzd` in the staff `MatchCandidate`'s commercial
    snapshot, so in the run's `matches` and in the match row's audit;
    `API_CONTRACTS_v0.2.md` §8 forbids its serialization to public and
    customer DTOs, and no customer or public operation returns a match
    (Slice 4, R9.2). The diagnostic of the same run does not carry it."""
    expectation = 25_000_000
    req = _request(client, ids)
    prop = _property(client, engine, ids, "ADR-NEW-TIL")
    _offer(client, ids, prop, price=26_000_000, expectation=expectation)
    [m] = _run(client, ids, req, [prop])["matches"]
    assert m["commercial_context_snapshot"]["seller_expectation_dzd"] == expectation
    assert _one(engine, """
        SELECT (new_row -> 'commercial_context_snapshot' ->> 'seller_expectation_dzd')::bigint
          FROM turab.audit_log
         WHERE entity_table = 'match_candidates' AND entity_id = :m""",
        m=m["match_id"]) == expectation
    assert expectation not in _numbers(_diagnostic(client, ids, req))


def test_g06_a_run_with_no_candidate_writes_an_empty_valid_format_2_that_replays(
        client, engine, ids):
    """G04 / G06: a property with no offer is excluded; the run evaluates
    nothing and writes a format-2 diagnostic: no suggestion, no scenario, no
    task, the exclusion counted; it replays."""
    req = _request(client, ids)
    lonely = _property(client, engine, ids, "ADR-NEW-TIL")
    body = _run(client, ids, req, [lonely])
    assert body["matches"] == []
    d = _diagnostic(client, ids, req)
    summary = d["blocker_summary"]
    assert (summary["format"], summary["evaluated"], summary["candidates_evaluated"],
            summary["excluded_counts"]) == (
        "turab.blocker-summary/2", [], 0, {"NO_QUALIFYING_OFFER": 1})
    assert (d["suggested_actions"], d["relaxation_scenarios"]) == ([], [])
    assert _tasks(client, ids, req) == []
    assert _replay(engine, d["diagnostic_run_id"]) == {"R": [], "D": []}


# ======================================================================================
# The review of 0fae42c: a stated limit of the replay, measured
# ======================================================================================

def test_limit_the_replay_does_not_read_the_diagnostics_own_input_hash(client, engine, ids):
    """A LIMIT, not a guarantee (review of 0fae42c; plan §5.4). The replay
    verifies the matches (R) and recomputes the decisions (D). It does not
    recompute the diagnostic row's `input_hash` (`turab.diagnostic-input/2`),
    nor compare it with the stored one: a document carrying any other value
    replays with no problem, and the replay reads no row of
    `match_diagnostic_runs`. So `{"R": [], "D": []}` is not a proof that every
    input of that hash is sound."""
    import inspect

    from turab.services import diagnostic_replay

    req = _request(client, ids, criteria=[LAND_BOOK])
    prop = _property(client, engine, ids, "ADR-NEW-TIL")
    _offer(client, ids, prop)
    d = _run(client, ids, req, [prop])["diagnostic"]
    row = _stored_row(engine, d["diagnostic_run_id"])
    stored_hash = _one(engine, "SELECT input_hash FROM turab.match_diagnostic_runs "
                               "WHERE diagnostic_run_id = :d", d=d["diagnostic_run_id"])
    with engine.connect() as conn:
        for value in (stored_hash, "0" * 64, None):
            assert diagnostic_replay.replay(conn, {**row, "input_hash": value}) == {
                "R": [], "D": []}, value
    assert "match_diagnostic_runs" not in inspect.getsource(diagnostic_replay)
