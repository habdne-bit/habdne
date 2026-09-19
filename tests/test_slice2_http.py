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
#
# The frozen contract's own x-authorization on postRecordsClaim:
#
#   "For customer, verified contact point and resource party relationship are
#    mandatory."
#
# That is a DECLARED CONDITION. Slice 2 first shipped INV-1 (which governs
# conflicts between claimants) with this half unenforced. The tests below are
# the adopted rule, case by case.

def _claim(client, ids, *, account, resource, contact_point, key_suffix):
    return client.post(
        "/records/claim",
        json={"resource_type": "REQUEST", "resource_id": str(resource),
              "verification_contact_point_id": str(contact_point)},
        headers={"Authorization": f"Bearer {account}",
                 "Idempotency-Key": f"s2-claim-{key_suffix}"},
    )


def test_the_rightful_claimant_converts_the_record_in_place(client, ids, engine):
    """No second request, no copy: the same row changes management mode."""
    before_total = _count(engine)
    before = _request(engine, ids.REQ_KHADIJA_ASSISTED)

    r = _claim(client, ids, account=ids.ACC_KHADIJA,
               resource=ids.REQ_KHADIJA_ASSISTED, contact_point=ids.CP_KHADIJA,
               key_suffix="ok")
    assert r.status_code == 200, r.text
    assert r.json()["outcome"] == "CLAIMED"

    after = _request(engine, ids.REQ_KHADIJA_ASSISTED)
    assert _count(engine) == before_total, "claiming must not create a request"
    assert after["management_mode"] == "SHARED_MANAGEMENT"
    assert after["claim_status"] == "CLAIMED"
    assert after["party_id"] == before["party_id"]
    assert after["budget_target_dzd"] == before["budget_target_dzd"]
    _unclaim(engine, ids.REQ_KHADIJA_ASSISTED)


# --- acceptance case 1: a different party ---------------------------------

def test_an_account_of_a_different_party_cannot_claim(client, ids, engine):
    before = _request(engine, ids.REQ_KHADIJA_ASSISTED)
    r = _claim(client, ids, account=ids.ACC_AMINA,
               resource=ids.REQ_KHADIJA_ASSISTED, contact_point=ids.CP_AMINA,
               key_suffix="wrongparty")
    assert r.status_code == 403
    assert r.json()["code"] == "CLAIM_NOT_ELIGIBLE"
    _assert_no_trace(engine, ids.REQ_KHADIJA_ASSISTED, before)


# --- acceptance case 2: a phone shared by two parties ---------------------

def test_a_shared_phone_does_not_make_one_party_the_other(client, ids, engine):
    """DL-02, at the surface that most invites the inference.

    Brahim's account holds the line that ALSO reaches the agency. Holding a
    number the agency is reachable on does not make him the agency, so he
    cannot claim the agency's record.
    """
    before = _request(engine, ids.REQ_AGENCY_ASSISTED)
    r = _claim(client, ids, account=ids.ACC_BRAHIM,
               resource=ids.REQ_AGENCY_ASSISTED, contact_point=ids.CP_SHARED,
               key_suffix="shared")
    assert r.status_code == 403
    assert r.json()["code"] == "CLAIM_NOT_ELIGIBLE"
    _assert_no_trace(engine, ids.REQ_AGENCY_ASSISTED, before)


# --- acceptance case 3: a contact point belonging to another account ------

def test_a_contact_point_of_another_account_does_not_prove_control(
    client, ids, engine
):
    """Passing a VERIFIED_CONTROL id proves somebody controls it, not that
    this account does. The trusted link is the account's own login contact
    point, which the OTP flow is what sets."""
    before = _request(engine, ids.REQ_KHADIJA_ASSISTED)
    r = _claim(client, ids, account=ids.ACC_KHADIJA,
               resource=ids.REQ_KHADIJA_ASSISTED, contact_point=ids.CP_AMINA,
               key_suffix="notmine")
    assert r.status_code == 403
    assert r.json()["code"] == "CLAIM_NOT_ELIGIBLE"
    _assert_no_trace(engine, ids.REQ_KHADIJA_ASSISTED, before)


# --- acceptance case 4: two concurrent attempts ---------------------------

def test_two_concurrent_claims_produce_one_claim_and_no_ambiguity(ids, engine):
    """The check must hold at the moment the row changes, not before it.

    Two real sessions race on the same record. The row lock serialises them,
    so exactly one claim event exists afterwards and INV-1's ambiguous state
    is never created.
    """
    import threading

    from turab.db.session import audited_transaction
    from turab.services.claims import ClaimRejected, claim_record
    from turab.auth.loaders import ResourceKind

    outcomes: list[str] = []
    barrier = threading.Barrier(2)

    def attempt(account_id, contact_point_id):
        with Session(bind=engine, future=True) as s:
            barrier.wait(timeout=10)
            try:
                with audited_transaction(s, account_id):
                    claim_record(
                        s, kind=ResourceKind.REQUEST,
                        resource_id=ids.REQ_AMINA_ASSISTED,
                        account_id=account_id,
                        verification_contact_point_id=contact_point_id,
                    )
                outcomes.append("CLAIMED")
            except ClaimRejected as exc:
                outcomes.append(exc.code)
            except Exception as exc:  # pragma: no cover - diagnostic
                outcomes.append(f"{type(exc).__name__}: {exc}")

    threads = [
        threading.Thread(target=attempt, args=(ids.ACC_AMINA, ids.CP_AMINA)),
        threading.Thread(target=attempt,
                         args=(ids.ACC_AMINA_SECOND, ids.CP_AMINA_SECOND)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=20)

    assert outcomes.count("CLAIMED") == 1, outcomes
    assert "RESOURCE_ALREADY_CLAIMED" in outcomes, outcomes
    with Session(bind=engine, future=True) as s:
        distinct = s.execute(
            text("""SELECT count(DISTINCT claimed_by_account_id)
                      FROM turab.record_claim_events WHERE request_id = :r"""),
            {"r": ids.REQ_AMINA_ASSISTED},
        ).scalar_one()
    assert distinct == 1, "a race must not create ambiguous claim authority"
    _unclaim(engine, ids.REQ_AMINA_ASSISTED)


# --- a refused attempt must not block the rightful claimant ---------------

def test_a_refused_attempt_does_not_block_the_rightful_claimant(
    client, ids, engine
):
    """The exposure the old implementation carried: a wrongful claim recorded
    an ownership event, and INV-1 then refused the rightful person."""
    refused = _claim(client, ids, account=ids.ACC_AMINA,
                     resource=ids.REQ_KHADIJA_ASSISTED, contact_point=ids.CP_AMINA,
                     key_suffix="blocker")
    assert refused.status_code == 403

    allowed = _claim(client, ids, account=ids.ACC_KHADIJA,
                     resource=ids.REQ_KHADIJA_ASSISTED,
                     contact_point=ids.CP_KHADIJA, key_suffix="rightful")
    assert allowed.status_code == 200, allowed.text
    assert allowed.json()["outcome"] == "CLAIMED"
    _unclaim(engine, ids.REQ_KHADIJA_ASSISTED)


# --- staff may not claim under their own account --------------------------

def test_staff_roles_alone_do_not_confer_the_right_to_claim(client, ids, engine):
    """An operator is not the holder of a record. Acting for someone else is
    delegation, undefined in this version (RFC-001 decision 4)."""
    before = _request(engine, ids.REQ_KHADIJA_ASSISTED)
    r = _claim(client, ids, account=ids.ACC_OPERATOR,
               resource=ids.REQ_KHADIJA_ASSISTED, contact_point=ids.CP_KHADIJA,
               key_suffix="staff")
    assert r.status_code == 403
    assert r.json()["code"] == "CLAIM_NOT_ELIGIBLE"
    _assert_no_trace(engine, ids.REQ_KHADIJA_ASSISTED, before)


# --- INV-1 still holds on top of eligibility ------------------------------

def test_a_second_eligible_claim_is_still_rejected(client, ids, engine):
    first = _claim(client, ids, account=ids.ACC_AMINA,
                   resource=ids.REQ_AMINA_ASSISTED, contact_point=ids.CP_AMINA,
                   key_suffix="inv1a")
    assert first.status_code == 200, first.text
    second = _claim(client, ids, account=ids.ACC_AMINA_SECOND,
                    resource=ids.REQ_AMINA_ASSISTED,
                    contact_point=ids.CP_AMINA_SECOND, key_suffix="inv1b")
    assert second.status_code == 409
    _unclaim(engine, ids.REQ_AMINA_ASSISTED)


def test_a_self_managed_record_is_not_claimable(client, ids):
    """Refused for its STATE, by a claimant who passes eligibility."""
    r = _claim(client, ids, account=ids.ACC_AMINA, resource=ids.REQ_AMINA,
               contact_point=ids.CP_AMINA, key_suffix="selfmanaged")
    assert r.status_code != 200
    assert "ASSISTED" in r.json()["detail"]


def test_property_claiming_fails_closed(client, ids):
    """The adopted rule is for REQUEST. A property has no `party_id`, and its
    party relationship is `party_property_relations`, which RFC-001 decision 1
    forbids as an authorization source. Rather than pick one reading, the path
    refuses."""
    r = client.post(
        "/records/claim",
        json={"resource_type": "PROPERTY",
              "resource_id": str(ids.ASSISTED_APARTMENT),
              "verification_contact_point_id": str(ids.CP_AMINA)},
        headers={**cust(ids), **key("s2-prop")},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "CLAIM_NOT_ELIGIBLE"
    assert "not been decided" in r.json()["detail"]


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


def _assert_no_trace(engine, request_id, before) -> None:
    """A refused attempt leaves NOTHING: no claim event, no state change."""
    with Session(bind=engine, future=True) as s:
        events = s.execute(
            text("SELECT count(*) FROM turab.record_claim_events "
                 "WHERE request_id = :r"),
            {"r": request_id},
        ).scalar_one()
    assert events == 0, "a refused claim must not record an ownership event"
    assert _request(engine, request_id) == before


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


# --- R-S2-03: the criteria endpoint adds AND changes -----------------------
#
# API_CONTRACTS v0.2: "Adds/changes structured criteria." The change half is
# selected by `request_criterion_id`, which the contract's `RequestCriterion`
# already declares — so nothing new is invented to carry it.

def _new_request(client, ids, tag):
    r = client.post("/requests", json=body(ids, local_location_detail=f"s2-{tag}"),
                    headers={**cust(ids), **key(f"s2-{tag}")})
    assert r.status_code == 201, r.text
    return r.json()["request_id"]


def _criterion(client, ids, rid, tag, **over):
    payload = {"criterion_code": "ROOMS_MIN", "importance": "REQUIRED",
               "operator": "GTE", "value": 3}
    payload.update(over)
    return client.post(f"/requests/{rid}/criteria", json=payload,
                       headers={**cust(ids), **key(f"s2-crit-{tag}")})


def test_the_contracts_criterion_id_is_accepted(client, ids):
    """It was declared by the contract and rejected by the model."""
    rid = _new_request(client, ids, "c-accept")
    created = _criterion(client, ids, rid, "c1")
    assert created.status_code == 201, created.text
    cid = created.json()["request_criterion_id"]

    changed = _criterion(client, ids, rid, "c2",
                         request_criterion_id=cid, value=5)
    assert changed.status_code == 201, changed.text
    assert changed.json()["request_criterion_id"] == cid


def test_changing_a_criterion_does_not_duplicate_it(client, ids):
    rid = _new_request(client, ids, "c-nodup")
    cid = _criterion(client, ids, rid, "d1").json()["request_criterion_id"]
    _criterion(client, ids, rid, "d2", request_criterion_id=cid,
               value=6, importance="PREFERRED")

    view = client.get(f"/requests/{rid}", headers=staff(ids)).json()
    rooms = [c for c in view["criteria"] if c["criterion_code"] == "ROOMS_MIN"]
    assert len(rooms) == 1, "changing a criterion must not leave the old one"
    assert rooms[0]["value"] == 6
    assert rooms[0]["importance"] == "PREFERRED"


def test_changing_a_criterion_bumps_the_request_version(client, ids):
    rid = _new_request(client, ids, "c-version")
    cid = _criterion(client, ids, rid, "v1").json()["request_criterion_id"]
    before = client.get(f"/requests/{rid}", headers=staff(ids)).json()["version"]
    _criterion(client, ids, rid, "v2", request_criterion_id=cid, value=4)
    after = client.get(f"/requests/{rid}", headers=staff(ids)).json()["version"]
    assert after > before


def test_a_criterion_id_from_another_request_is_refused(client, ids, engine):
    """Ownership is part of the predicate, not a separate check."""
    mine = _new_request(client, ids, "c-mine")
    theirs = _new_request(client, ids, "c-theirs")
    foreign = _criterion(client, ids, theirs, "f1").json()["request_criterion_id"]

    r = _criterion(client, ids, mine, "f2",
                   request_criterion_id=foreign, value=9)
    assert r.status_code == 404
    # and the other request's criterion is untouched
    other = client.get(f"/requests/{theirs}", headers=staff(ids)).json()
    assert other["criteria"][0]["value"] == 3


def test_an_unknown_criterion_id_is_refused(client, ids):
    rid = _new_request(client, ids, "c-unknown")
    r = _criterion(client, ids, rid, "u1",
                   request_criterion_id=str(uuid.uuid4()))
    assert r.status_code == 404


def test_re_adding_the_same_slot_points_at_the_change_path(client, ids):
    """`UNIQUE(request_id, criterion_code, sort_order)` surfaces as a typed
    conflict naming the change path, not as a database error."""
    rid = _new_request(client, ids, "c-slot")
    _criterion(client, ids, rid, "s1")
    again = _criterion(client, ids, rid, "s2", value=7)
    assert again.status_code == 409, again.text
    assert again.json()["code"] == "DUPLICATE_CRITERION_SLOT"
    assert "request_criterion_id" in again.json()["detail"]


def test_the_change_is_recorded_with_its_previous_value(client, ids, engine):
    rid = _new_request(client, ids, "c-prov")
    cid = _criterion(client, ids, rid, "p1").json()["request_criterion_id"]
    _criterion(client, ids, rid, "p2", request_criterion_id=cid, value=8)

    entries = [
        p for p in client.get(f"/requests/{rid}", headers=staff(ids)).json()["provenance"]
        if p["attribute_code"] == "criterion.ROOMS_MIN"
    ]
    assert len(entries) == 2, "the add and the change are both recorded"
    assert entries[-1]["previous"] is not None
    assert entries[-1]["previous"]["value"] == 3


# --- R-S2-05: input contracts --------------------------------------------

def test_a_null_non_nullable_field_is_a_422_not_a_500(client, ids, engine):
    """`intent` is NOT NULL in the schema and non-nullable in the contract."""
    rid = _new_request(client, ids, "n-null")
    version = client.get(f"/requests/{rid}", headers=staff(ids)).json()["version"]
    r = client.patch(f"/requests/{rid}", json={"intent": None},
                     headers={**cust(ids), "If-Match-Version": str(version)})
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "VALIDATION_FAILED"
    # The field is named in field_errors, never the value (K04).
    fields = [e["field"] for e in r.json()["field_errors"]]
    assert "intent" in fields, r.json()


def test_an_unknown_enum_value_is_a_422_not_a_500(client, ids):
    rid = _new_request(client, ids, "n-enum")
    version = client.get(f"/requests/{rid}", headers=staff(ids)).json()["version"]
    r = client.patch(f"/requests/{rid}",
                     json={"desired_property_type": "NOT_A_PROPERTY_TYPE"},
                     headers={**cust(ids), "If-Match-Version": str(version)})
    assert r.status_code == 422, r.text


def test_an_incoherent_budget_pair_is_refused_on_create(client, ids, engine):
    before = _count(engine)
    r = client.post("/requests",
                    json=body(ids, budget_target_dzd=200, budget_max_dzd=100),
                    headers={**cust(ids), **key("s2-budget-create")})
    assert r.status_code == 422, r.text
    # Both values are in the body, so the MODEL decides it and the caller
    # gets a field-level error rather than a generic message.
    blob = r.text
    assert "budget_target_dzd" in blob, blob
    assert _count(engine) == before, "a refused create must write nothing"


def test_the_budget_pair_is_checked_on_the_merged_values(client, ids):
    """A patch that sets only the target can still break the pair, so the
    check runs against the patch applied over the current row."""
    rid = _new_request(client, ids, "n-merge")
    version = client.get(f"/requests/{rid}", headers=staff(ids)).json()["version"]
    # current max is unset in the base body; give it one first
    set_max = client.patch(f"/requests/{rid}", json={"budget_max_dzd": 1_000},
                           headers={**cust(ids), "If-Match-Version": str(version)})
    assert set_max.status_code == 200, set_max.text
    version = set_max.json()["version"]

    r = client.patch(f"/requests/{rid}", json={"budget_target_dzd": 9_999},
                     headers={**cust(ids), "If-Match-Version": str(version)})
    assert r.status_code == 422, r.text
    assert "budget_target_dzd" in r.json()["detail"]


def test_a_refused_input_consumes_no_idempotency_key(client, ids, engine):
    """A rejected command must leave its key free for a corrected retry."""
    k = "s2-budget-retry"
    bad = client.post("/requests",
                      json=body(ids, budget_target_dzd=500, budget_max_dzd=100,
                                local_location_detail="s2-retry"),
                      headers={**cust(ids), "Idempotency-Key": k})
    assert bad.status_code == 422
    with Session(bind=engine, future=True) as s:
        assert s.execute(
            text("SELECT count(*) FROM turab.idempotency_records "
                 "WHERE idempotency_key = :k"), {"k": k},
        ).scalar_one() == 0

    good = client.post("/requests",
                       json=body(ids, budget_target_dzd=100, budget_max_dzd=500,
                                 local_location_detail="s2-retry"),
                       headers={**cust(ids), "Idempotency-Key": k})
    assert good.status_code == 201, good.text


def test_a_refused_input_leaks_no_database_text(client, ids):
    rid = _new_request(client, ids, "n-leak")
    version = client.get(f"/requests/{rid}", headers=staff(ids)).json()["version"]
    r = client.patch(f"/requests/{rid}",
                     json={"desired_property_type": "NOPE"},
                     headers={**cust(ids), "If-Match-Version": str(version)})
    blob = r.text.lower()
    for forbidden in ("psycopg", "sqlalchemy", "turab.requests", "constraint",
                      "traceback"):
        assert forbidden not in blob, forbidden
