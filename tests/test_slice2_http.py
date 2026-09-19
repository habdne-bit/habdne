"""Slice 2 over HTTP: authorization, the claim flow, and the three commands.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 2; Design Ledger DL-02 (identity is
never inferred from a shared phone); RFC-001 §4.8.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def clean(engine):
    """Only the idempotency keys are cleared.

    Requests created here are deliberately LEFT: `prevent_core_delete()`
    forbids hard-deleting a core TURAB record, and a test that worked around
    that trigger would be testing a database the application can never
    produce. Every assertion below is therefore relative — counted before and
    after, or read back by id — rather than assuming an empty table.
    """
    yield
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.idempotency_records"))
        s.commit()


def cust(ids):
    return {"Authorization": f"Bearer {ids.ACC_AMINA}"}


def staff(ids):
    return {"Authorization": f"Bearer {ids.ACC_OPERATOR}"}


def key(k):
    return {"Idempotency-Key": k}


def body(ids, **over):
    base = {
        "party_id": str(ids.AMINA),
        "transaction_intent": "BUY",
        "intent": "ACTIVE_SEARCH",
        "management_mode": "SELF_MANAGED",
        "claim_status": "CLAIMED",
        "local_location_detail": "s2-http",
    }
    base.update(over)
    return base


# --- self-managed creation by the customer --------------------------------

def test_a_customer_creates_their_own_request(client, ids):
    r = client.post("/requests", json=body(ids), headers={**cust(ids), **key("s2-1")})
    assert r.status_code == 201, r.text
    assert r.json()["party_id"] == str(ids.AMINA)
    assert r.json()["management_mode"] == "SELF_MANAGED"
    assert r.json()["status"] == "RAW"


def test_a_customer_cannot_create_a_request_for_another_party(client, ids, engine):
    """DL-02. The party comes from the account's binding, never inferred."""
    before = _count(engine)
    r = client.post("/requests", json=body(ids, party_id=str(ids.BRAHIM)),
                    headers={**cust(ids), **key("s2-2")})
    assert r.status_code == 403
    assert r.json()["code"] == "OBJECT_NOT_AUTHORIZED"
    assert _count(engine) == before


def test_a_customer_cannot_create_an_assisted_record(client, ids):
    """ASSISTED means staff are operating a record on someone's behalf. A
    customer creating one would assert an operating relationship that does
    not exist."""
    r = client.post(
        "/requests",
        json=body(ids, management_mode="ASSISTED", claim_status="UNCLAIMED"),
        headers={**cust(ids), **key("s2-3")},
    )
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_FAILED"


def test_staff_create_an_assisted_unclaimed_record(client, ids):
    r = client.post(
        "/requests",
        json=body(ids, party_id=str(ids.BRAHIM), management_mode="ASSISTED",
                  claim_status="UNCLAIMED"),
        headers={**staff(ids), **key("s2-4")},
    )
    assert r.status_code == 201, r.text
    assert (r.json()["management_mode"], r.json()["claim_status"]) == (
        "ASSISTED", "UNCLAIMED"
    )


def test_an_assisted_record_cannot_be_created_claimed(client, ids):
    r = client.post(
        "/requests",
        json=body(ids, party_id=str(ids.BRAHIM), management_mode="ASSISTED",
                  claim_status="CLAIMED"),
        headers={**staff(ids), **key("s2-5")},
    )
    assert r.status_code == 422
    assert "UNCLAIMED" in r.json()["detail"]


# --- the claim flow --------------------------------------------------------

def test_claiming_converts_the_record_in_place(client, ids, engine):
    """No second request, no copy: the same row changes management mode.

    Slice 2 says 'converting assisted record to shared/claimed management
    without duplication', and duplication is the failure this guards: a
    claimed copy would split one person's search across two records that
    then drift.
    """
    before_total = _count(engine)
    before = _request(engine, ids.REQ_AGENCY_ASSISTED)

    r = client.post(
        "/records/claim",
        json={"resource_type": "REQUEST", "resource_id": str(ids.REQ_AGENCY_ASSISTED),
              "verification_contact_point_id": str(ids.CP_AMINA)},
        headers={**{"Authorization": f"Bearer {ids.ACC_KHADIJA}"}, **key("s2-claim")},
    )
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "CLAIMED"

    after = _request(engine, ids.REQ_AGENCY_ASSISTED)
    assert _count(engine) == before_total, "claiming must not create a request"
    assert after["management_mode"] == "SHARED_MANAGEMENT"
    assert after["claim_status"] == "CLAIMED"
    # Everything that describes the search survives untouched.
    assert after["party_id"] == before["party_id"]
    assert after["budget_target_dzd"] == before["budget_target_dzd"]
    assert after["status"] == before["status"]
    _unclaim(engine, ids.REQ_AGENCY_ASSISTED)


def test_a_second_claim_by_another_account_is_rejected(client, ids, engine):
    """INV-1, at the Slice 2 surface."""
    first = client.post(
        "/records/claim",
        json={"resource_type": "REQUEST", "resource_id": str(ids.REQ_AGENCY_ASSISTED),
              "verification_contact_point_id": str(ids.CP_AMINA)},
        headers={"Authorization": f"Bearer {ids.ACC_KHADIJA}", **key("s2-c1")},
    )
    assert first.status_code == 200
    second = client.post(
        "/records/claim",
        json={"resource_type": "REQUEST", "resource_id": str(ids.REQ_AGENCY_ASSISTED),
              "verification_contact_point_id": str(ids.CP_AMINA)},
        headers={**cust(ids), **key("s2-c2")},
    )
    assert second.status_code == 409
    _unclaim(engine, ids.REQ_AGENCY_ASSISTED)


def test_a_self_managed_record_is_not_claimable(client, ids):
    r = client.post(
        "/records/claim",
        json={"resource_type": "REQUEST", "resource_id": str(ids.REQ_AMINA),
              "verification_contact_point_id": str(ids.CP_AMINA)},
        headers={"Authorization": f"Bearer {ids.ACC_KHADIJA}", **key("s2-c3")},
    )
    assert r.status_code != 200
    assert "ASSISTED" in r.json()["detail"]


def test_claiming_does_not_infer_ownership_from_the_phone(client, ids, engine):
    """DL-02, checked at the surface that most invites the inference.

    The claim carries a `verification_contact_point_id`, and the temptation is
    to treat "this phone reaches that party" as "this account owns that
    party's records". It does not: after claiming, read access is still
    decided by the account's own party binding, so an account whose party
    differs from the record's gains an ownership event and no readable record.

    That asymmetry is a REAL GAP, pinned here rather than papered over — see
    the Slice 2 report. The test asserts the safe half (no read access leaks)
    and names the unsafe half.
    """
    claimed = client.post(
        "/records/claim",
        json={"resource_type": "REQUEST", "resource_id": str(ids.REQ_AGENCY_ASSISTED),
              "verification_contact_point_id": str(ids.CP_AMINA)},
        headers={**cust(ids), **key("s2-c4")},
    )
    assert claimed.status_code == 200

    # Amina's party is AMINA; the record's party is AGENCY. Claiming did not
    # make the record hers to read.
    seen = client.get(f"/me/requests/{ids.REQ_AGENCY_ASSISTED}", headers=cust(ids))
    assert seen.status_code == 404, (
        "a claim must not hand over a record whose party the claimant is not"
    )
    _unclaim(engine, ids.REQ_AGENCY_ASSISTED)


# --- the three commands, over HTTP ----------------------------------------

def test_the_three_commands_are_three_endpoints(client, ids):
    created = client.post("/requests", json=body(ids),
                          headers={**cust(ids), **key("s2-6")})
    rid = created.json()["request_id"]
    version = created.json()["version"]

    patched = client.patch(
        f"/requests/{rid}", json={"budget_max_dzd": 30_000_000},
        headers={**cust(ids), "If-Match-Version": str(version)},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["budget_max_dzd"] == 30_000_000
    assert patched.json()["status"] == "RAW"
    assert patched.json()["last_confirmed_at"] is None

    state = client.post(f"/requests/{rid}/state", json={"target_status": "CONTACTED"},
                        headers={**staff(ids), **key("s2-7")})
    assert state.status_code == 200, state.text
    assert state.json()["status"] == "CONTACTED"
    assert state.json()["budget_max_dzd"] == 30_000_000

    confirmed = client.post(f"/requests/{rid}/reconfirm", json={},
                            headers={**staff(ids), **key("s2-8")})
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["last_confirmed_at"] is not None
    assert confirmed.json()["status"] == "CONTACTED"


def test_an_undefined_transition_is_refused_over_http(client, ids):
    created = client.post("/requests", json=body(ids),
                          headers={**cust(ids), **key("s2-9")})
    rid = created.json()["request_id"]
    r = client.post(f"/requests/{rid}/state", json={"target_status": "CLOSED"},
                    headers={**staff(ids), **key("s2-10")})
    assert r.status_code == 422
    assert "not a transition defined" in r.json()["detail"]


def test_a_stale_version_applies_nothing(client, ids, engine):
    created = client.post("/requests", json=body(ids),
                          headers={**cust(ids), **key("s2-11")})
    rid = created.json()["request_id"]
    stale = created.json()["version"]
    client.post(f"/requests/{rid}/criteria",
                json={"criterion_code": "ROOMS_MIN", "importance": "REQUIRED",
                      "operator": "GTE", "value": 3},
                headers={**cust(ids), **key("s2-12")})

    r = client.patch(f"/requests/{rid}", json={"budget_max_dzd": 99_000_000},
                     headers={**cust(ids), "If-Match-Version": str(stale)})
    assert r.status_code == 409
    row = _request(engine, uuid.UUID(rid))
    assert row["budget_max_dzd"] != 99_000_000


# --- authorization on the new surface -------------------------------------

def test_a_customer_cannot_command_another_partys_request(client, ids, engine):
    before = _request(engine, ids.REQ_AGENCY_ASSISTED)
    for path, payload, extra in [
        (f"/requests/{ids.REQ_AGENCY_ASSISTED}/state",
         {"target_status": "ACTIVE"}, key("s2-13")),
        (f"/requests/{ids.REQ_AGENCY_ASSISTED}/reconfirm", {}, key("s2-14")),
        (f"/requests/{ids.REQ_AGENCY_ASSISTED}/criteria",
         {"criterion_code": "ROOMS_MIN", "importance": "REQUIRED",
          "operator": "GTE", "value": 2}, key("s2-15")),
    ]:
        r = client.post(path, json=payload, headers={**cust(ids), **extra})
        assert r.status_code == 403, (path, r.text)
        assert r.json()["code"] == "OBJECT_NOT_AUTHORIZED"
    assert _request(engine, ids.REQ_AGENCY_ASSISTED) == before


def test_a_customer_cannot_read_a_request_internally(client, ids):
    r = client.get(f"/requests/{ids.REQ_AMINA}", headers=cust(ids))
    assert r.status_code == 403
    assert r.json()["code"] == "ROLE_NOT_PERMITTED"


def test_staff_read_carries_derived_freshness(client, ids):
    r = client.get(f"/requests/{ids.REQ_AGENCY_ASSISTED}", headers=staff(ids))
    assert r.status_code == 200, r.text
    fresh = r.json()["freshness"]
    # The fixture confirms this request 120 days ago; the active policy's
    # window is 30, so it is stale — and the policy version is reported so a
    # reader knows WHICH policy judged it.
    assert fresh["state"] == "STALE"
    assert fresh["threshold_days"] == 30
    assert fresh["policy_version"] == "0.2.0"


def test_the_staff_read_is_audited(client, ids, sink):
    client.get(f"/requests/{ids.REQ_AMINA}", headers=staff(ids))
    assert [r for r in sink.records
            if r.operation_id == "getRequestsRequestId" and r.decision == "ALLOW"]


def test_an_unknown_criterion_code_is_a_typed_error(client, ids):
    created = client.post("/requests", json=body(ids),
                          headers={**cust(ids), **key("s2-16")})
    rid = created.json()["request_id"]
    r = client.post(f"/requests/{rid}/criteria",
                    json={"criterion_code": "VIBES", "importance": "REQUIRED",
                          "operator": "EQ", "value": "good"},
                    headers={**cust(ids), **key("s2-17")})
    assert r.status_code == 422
    assert "master registry" in r.json()["detail"]


# --- helpers ---------------------------------------------------------------

def _count(engine) -> int:
    with Session(bind=engine, future=True) as s:
        return s.execute(text("SELECT count(*) FROM turab.requests")).scalar_one()


def _request(engine, request_id):
    with Session(bind=engine, future=True) as s:
        return dict(s.execute(
            text("""SELECT party_id, status::text AS status,
                           management_mode::text AS management_mode,
                           claim_status::text AS claim_status,
                           budget_target_dzd, budget_max_dzd
                      FROM turab.requests WHERE request_id = :r"""),
            {"r": request_id},
        ).mappings().one())


def _unclaim(engine, request_id) -> None:
    """Put the shared fixture back as it was."""
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.record_claim_events WHERE request_id = :r"),
                  {"r": request_id})
        s.execute(
            text("""UPDATE turab.requests
                       SET management_mode = 'ASSISTED', claim_status = 'UNCLAIMED'
                     WHERE request_id = :r"""),
            {"r": request_id},
        )
        s.commit()
