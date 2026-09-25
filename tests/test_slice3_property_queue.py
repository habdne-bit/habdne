"""The properties review queue — `getBackofficeQueuesProperties`, Slice 3.

Listed in plan §1.1 and omitted from step 1. The STOP GATE C generator
(`db/gate/stop_gate_c_evidence.py`, step 8) found that no route served it.

Ref: Developer Spec §19 ("Properties needing review | تعارض/نقص/إتاحة قديمة
أو Identity candidate"); `services/properties.review_queue`.

Each criterion is shown to ENTER a property that was not queued before, so an
absence on an empty queue proves nothing by accident.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from turab.auth.audit import AccessAuditor, RecordingAuditSink

Q = "/backoffice/queues/properties"


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _h(account, key=True):
    h = {"Authorization": f"Bearer {account}"}
    if key:
        h["Idempotency-Key"] = str(uuid.uuid4())
    return h


def _run(engine, sql, **p):
    with engine.begin() as conn:
        conn.execute(text(sql), p)


def _one(engine, sql, **p):
    with engine.begin() as conn:
        return conn.execute(text(sql), p).scalar_one()


def _property(client, ids, loc=None):
    body = {"property_type": "APARTMENT", "supply_mode": "PUBLIC",
            "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"}
    if loc:
        body["canonical_location_id"] = str(loc)
    r = client.post("/properties", headers=_h(ids.ACC_OPERATOR), json=body)
    assert r.status_code == 201, r.text
    return r.json()["property_id"]


def _queue(client, ids, account=None):
    r = client.get(Q, headers=_h(account or ids.ACC_OPERATOR, key=False))
    assert r.status_code == 200, r.text
    return {item["id"]: item for item in r.json()["items"]}


def _location(engine):
    return _one(engine, """INSERT INTO turab.locations (code, canonical_ar, location_type)
                           VALUES (:c, 'موقع', 'AREA') RETURNING location_id""",
                c=f"TEST-Q-{uuid.uuid4().hex[:16]}")


def test_stale_availability_enters_the_queue(client, ids, engine):
    pid = _property(client, ids)
    assert pid not in _queue(client, ids)
    _run(engine, "UPDATE turab.properties SET current_availability = 'NEEDS_CONFIRMATION' "
                 "WHERE property_id = :p", p=pid)
    item = _queue(client, ids)[pid]
    assert item["reasons"] == ["AVAILABILITY_NEEDS_CONFIRMATION"]
    assert (item["kind"], item["priority"], item["reason"]) \
        == ("PROPERTY", "NORMAL", "AVAILABILITY_NEEDS_CONFIRMATION")


@pytest.mark.parametrize("decision,queued", [(None, True), ("UNSURE", True),
                                             ("CONFIRMED_DISTINCT", False)])
def test_a_pending_or_unsure_identity_candidate_enters_the_queue(client, ids, engine,
                                                                decision, queued):
    loc = _location(engine)
    a, b = _property(client, ids, loc), _property(client, ids, loc)
    assert a not in _queue(client, ids)
    r = client.post("/identity/candidates/generate", headers=_h(ids.ACC_OPERATOR),
                    json={"property_id": a})
    cid = r.json()[0]["identity_candidate_id"]
    if decision:
        assert client.post(f"/identity/candidates/{cid}/review", headers=_h(ids.ACC_REVIEWER),
                           json={"decision": decision}).status_code == 200
    queue = _queue(client, ids)
    assert (a in queue and b in queue) is queued
    if queued:
        assert queue[a]["reasons"] == ["IDENTITY_CANDIDATE_PENDING"]


def test_a_claim_verified_with_a_conflict_enters_the_queue(client, ids, engine):
    pid = _property(client, ids)
    claim = client.post("/claims", headers=_h(ids.ACC_OPERATOR), json={
        "subject": {"type": "PROPERTY", "id": pid}, "attribute_code": "ROOMS",
        "claimed_value": 3, "asserted_by_party_id": str(ids.BRAHIM)})
    assert claim.status_code == 201, claim.text
    assert pid not in _queue(client, ids)
    v = client.post(f"/claims/{claim.json()['claim_id']}/verification-events",
                    headers=_h(ids.ACC_REVIEWER),
                    json={"level": "DOCUMENT_SEEN", "outcome": "CONFLICT_FOUND"})
    assert v.status_code == 201, v.text
    assert _queue(client, ids)[pid]["reasons"] == ["CLAIM_CONFLICT_FOUND"]


def test_several_reasons_are_listed_in_the_declared_order(client, ids, engine):
    loc = _location(engine)
    a, _ = _property(client, ids, loc), _property(client, ids, loc)
    client.post("/identity/candidates/generate", headers=_h(ids.ACC_OPERATOR),
                json={"property_id": a})
    _run(engine, "UPDATE turab.properties SET current_availability = 'NEEDS_CONFIRMATION' "
                 "WHERE property_id = :p", p=a)
    item = _queue(client, ids)[a]
    assert item["reasons"] == ["IDENTITY_CANDIDATE_PENDING", "AVAILABILITY_NEEDS_CONFIRMATION"]
    assert item["reason"] == "IDENTITY_CANDIDATE_PENDING"


def test_an_alias_is_not_queued(client, ids, engine):
    loc = _location(engine)
    a, b = _property(client, ids, loc), _property(client, ids, loc)
    cid = client.post("/identity/candidates/generate", headers=_h(ids.ACC_OPERATOR),
                      json={"property_id": a}).json()[0]["identity_candidate_id"]
    _run(engine, "UPDATE turab.properties SET current_availability = 'NEEDS_CONFIRMATION' "
                 "WHERE property_id IN (:a, :b)", a=a, b=b)
    assert client.post(f"/identity/candidates/{cid}/review", headers=_h(ids.ACC_REVIEWER),
                       json={"decision": "CONFIRMED_SAME",
                             "canonical_property_id": a}).status_code == 200
    queue = _queue(client, ids)
    assert a in queue and b not in queue


def test_a_candidate_that_can_no_longer_be_reviewed_does_not_queue_its_other_member(
        client, ids, engine):
    """A chain A–B, B–C. Once A–B is confirmed SAME and B is an alias, review
    refuses every decision on B–C. B–C is then no reason to queue C: C leaves
    the queue, while the B–C row stays as history. A reviewable candidate
    (A–C) brings C back, so the rule excludes only the unreviewable one."""
    loc = _location(engine)
    a, b, c = (_property(client, ids, loc) for _ in range(3))
    made = client.post("/identity/candidates/generate", headers=_h(ids.ACC_OPERATOR),
                       json={"property_id": b})
    assert made.status_code == 201, made.text
    by_pair = {frozenset((x["property_a_id"], x["property_b_id"])): x["identity_candidate_id"]
               for x in made.json()}
    ab, bc = by_pair[frozenset((a, b))], by_pair[frozenset((b, c))]
    assert frozenset((a, c)) not in by_pair
    assert c in _queue(client, ids)

    assert client.post(f"/identity/candidates/{ab}/review", headers=_h(ids.ACC_REVIEWER),
                       json={"decision": "CONFIRMED_SAME",
                             "canonical_property_id": a}).status_code == 200
    for decision in ("CONFIRMED_DISTINCT", "UNSURE"):
        r = client.post(f"/identity/candidates/{bc}/review", headers=_h(ids.ACC_REVIEWER),
                        json={"decision": decision})
        assert r.status_code == 409 and r.json()["code"] == "IDENTITY_ALIAS_NOT_CANONICAL", r.text
    queue = _queue(client, ids)
    assert b not in queue, "B is an alias"
    assert a not in queue, "A's only candidate is decided"
    assert c not in queue, f"C is queued by the unreviewable B–C candidate: {queue.get(c)}"
    with engine.connect() as conn:
        assert conn.execute(text("""SELECT review_status::text FROM turab.property_identity_candidates
                                     WHERE identity_candidate_id = :i"""),
                            {"i": bc}).scalar_one() == "PENDING_REVIEW"

    again = client.post("/identity/candidates/generate", headers=_h(ids.ACC_OPERATOR),
                        json={"property_id": c})
    assert again.status_code == 201, again.text
    assert [{x["property_a_id"], x["property_b_id"]} for x in again.json()] == [{a, c}]
    queue = _queue(client, ids)
    assert queue[a]["reasons"] == queue[c]["reasons"] == ["IDENTITY_CANDIDATE_PENDING"]
    assert b not in queue


def test_the_queue_is_oldest_first_and_conforms_to_the_contract(client, ids, engine):
    from turab.auth.contract import load_contract

    first, second = _property(client, ids), _property(client, ids)
    _run(engine, "UPDATE turab.properties SET current_availability = 'NEEDS_CONFIRMATION' "
                 "WHERE property_id IN (:a, :b)", a=first, b=second)
    r = client.get(Q, headers=_h(ids.ACC_REVIEWER, key=False))
    body = r.json()
    assert set(body) == {"items", "next_cursor"} and body["next_cursor"] is None
    order = [i["id"] for i in body["items"]]
    assert order.index(first) < order.index(second)
    required = set(load_contract()["components"]["schemas"]["QueueItem"]["required"])
    assert all(required <= set(item) for item in body["items"])


def test_the_queue_is_audited_once_and_refused_to_customers(client, ids, sink):
    sink.clear()
    _queue(client, ids)
    assert len(sink.records) == 1, "a list is audited once (R6.3c)"
    r = client.get(Q, headers=_h(ids.ACC_AMINA, key=False))
    assert r.status_code == 403, r.text
