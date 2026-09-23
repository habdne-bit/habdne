"""F-3: numeric input means what the contract's JSON Schema means.

Ref: decision F-3; the effective contract's `RequestCreate`, `RequestPatch`,
`RequestCriterion` (`integer`) and `PropertyCreate`, `PropertyPatch`
(`number`); JSON Schema 2020-12 Core §4.2.1.

Pydantic's lax `int` accepted `true` (as 1) and `"123"` (as 123), and its lax
`float` accepted `true` and `"1.5"`. None of them is a JSON number. Each is now
a 422 field error, and each test below asserts two further things about the
refused command:

  * nothing was written;
  * where the command takes an `Idempotency-Key`, the key was not consumed —
    the SAME key then succeeds with a valid body, rather than being refused as
    a key reused with a different body.

What is deliberately kept: an integer is a JSON `number`, so `5` is a valid
area; `5.0` is a JSON `integer`; and `null` still clears the fields whose
contract type admits it.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink

NOT_JSON_NUMBERS = [True, "123", "1.5"]


@pytest.fixture
def client(engine):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink()))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def clean(engine):
    yield
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.idempotency_records"))
        s.commit()


def cust(ids):
    return {"Authorization": f"Bearer {ids.ACC_AMINA}"}


def key():
    return {"Idempotency-Key": f"f3-{uuid.uuid4()}"}


def _count(engine, sql, **params) -> int:
    with Session(bind=engine, future=True) as s:
        return s.execute(text(sql), params).scalar_one()


def _request_body(ids, **over):
    return {"party_id": str(ids.AMINA), "transaction_intent": "BUY",
            "intent": "ACTIVE_SEARCH", "management_mode": "SELF_MANAGED",
            "claim_status": "CLAIMED", **over}


def _property_body(**over):
    return {"property_type": "LAND", "supply_mode": "PUBLIC",
            "management_mode": "SELF_MANAGED", "claim_status": "CLAIMED", **over}


def _is_field_error(r, field):
    assert r.status_code == 422, r.text
    assert field in r.text, f"the error should name {field}: {r.text}"


# --- REQUEST (integer) -----------------------------------------------------

@pytest.mark.parametrize("field", ["budget_target_dzd", "budget_max_dzd"])
@pytest.mark.parametrize("value", NOT_JSON_NUMBERS, ids=repr)
def test_request_create_refuses_a_non_number_budget(client, ids, engine, field, value):
    count = "SELECT count(*) FROM turab.requests WHERE party_id = :p"
    before = _count(engine, count, p=ids.AMINA)
    k = key()
    r = client.post("/requests", json=_request_body(ids, **{field: value}),
                    headers={**cust(ids), **k})
    _is_field_error(r, field)
    assert _count(engine, count, p=ids.AMINA) == before, "nothing may be written"

    ok = client.post("/requests", json=_request_body(ids, **{field: 5}),
                     headers={**cust(ids), **k})
    assert ok.status_code == 201, f"the refused call consumed its key: {ok.text}"


def _new_request(client, ids):
    r = client.post("/requests", json=_request_body(ids), headers={**cust(ids), **key()})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.mark.parametrize("value", NOT_JSON_NUMBERS, ids=repr)
def test_request_patch_refuses_a_non_number_budget(client, ids, engine, value):
    req = _new_request(client, ids)
    r = client.patch(f"/requests/{req['request_id']}", json={"budget_max_dzd": value},
                     headers={**cust(ids), "If-Match-Version": str(req["version"])})
    _is_field_error(r, "budget_max_dzd")
    version = _count(engine, "SELECT version FROM turab.requests WHERE request_id = :r",
                     r=req["request_id"])
    assert version == req["version"], "nothing may be written"


def test_request_patch_null_still_clears_a_budget(client, ids):
    req = _new_request(client, ids)
    r = client.patch(f"/requests/{req['request_id']}",
                     json={"budget_target_dzd": 5},
                     headers={**cust(ids), "If-Match-Version": str(req["version"])})
    assert r.status_code == 200, r.text
    r = client.patch(f"/requests/{req['request_id']}",
                     json={"budget_target_dzd": None},
                     headers={**cust(ids), "If-Match-Version": str(r.json()["version"])})
    assert r.status_code == 200, r.text
    assert r.json()["budget_target_dzd"] is None


def test_an_integral_budget_written_as_a_decimal_is_an_integer(client, ids):
    r = client.post("/requests", json=_request_body(ids, budget_max_dzd=5.0),
                    headers={**cust(ids), **key()})
    assert r.status_code == 201, r.text
    assert r.json()["budget_max_dzd"] == 5


@pytest.mark.parametrize("value", NOT_JSON_NUMBERS, ids=repr)
def test_a_criterion_refuses_a_non_number_sort_order(client, ids, engine, value):
    rid = _new_request(client, ids)["request_id"]
    count = "SELECT count(*) FROM turab.request_criteria WHERE request_id = :r"
    before = _count(engine, count, r=rid)
    k = key()
    body = {"criterion_code": "ROOMS_MIN", "importance": "REQUIRED",
            "operator": "GTE", "value": 3}
    r = client.post(f"/requests/{rid}/criteria", json={**body, "sort_order": value},
                    headers={**cust(ids), **k})
    _is_field_error(r, "sort_order")
    assert _count(engine, count, r=rid) == before, "nothing may be written"

    ok = client.post(f"/requests/{rid}/criteria", json={**body, "sort_order": 7},
                     headers={**cust(ids), **k})
    assert ok.status_code == 201, f"the refused call consumed its key: {ok.text}"


# --- PROPERTY (number) -----------------------------------------------------

@pytest.mark.parametrize("field", ["land_area_m2", "built_area_m2"])
@pytest.mark.parametrize("value", NOT_JSON_NUMBERS, ids=repr)
def test_property_create_refuses_a_non_number_area(client, ids, engine, field, value):
    count = ("SELECT count(*) FROM turab.properties "
             "WHERE created_by_account_id = :a")
    before = _count(engine, count, a=ids.ACC_AMINA)
    k = key()
    r = client.post("/properties", json=_property_body(**{field: value}),
                    headers={**cust(ids), **k})
    _is_field_error(r, field)
    assert _count(engine, count, a=ids.ACC_AMINA) == before, "nothing may be written"

    ok = client.post("/properties", json=_property_body(**{field: 5}),
                     headers={**cust(ids), **k})
    assert ok.status_code == 201, f"the refused call consumed its key: {ok.text}"


def test_an_integer_is_a_valid_area(client, ids):
    """`number` includes the integers; refusing `5` would narrow the contract."""
    r = client.post("/properties", json=_property_body(land_area_m2=5),
                    headers={**cust(ids), **key()})
    assert r.status_code == 201, r.text
    assert r.json()["land_area_m2"] == 5


@pytest.mark.parametrize("value", NOT_JSON_NUMBERS, ids=repr)
def test_property_patch_refuses_a_non_number_area(client, ids, engine, value):
    r = client.post("/properties", json=_property_body(land_area_m2=10),
                    headers={**cust(ids), **key()})
    prop = r.json()
    r = client.patch(f"/properties/{prop['property_id']}",
                     json={"land_area_m2": value},
                     headers={**cust(ids), "If-Match-Version": str(prop["version"])})
    _is_field_error(r, "land_area_m2")
    version = _count(engine, "SELECT version FROM turab.properties "
                             "WHERE property_id = :p", p=prop["property_id"])
    assert version == prop["version"], "nothing may be written"


def test_property_patch_null_still_clears_an_area(client, ids):
    r = client.post("/properties", json=_property_body(land_area_m2=10),
                    headers={**cust(ids), **key()})
    prop = r.json()
    r = client.patch(f"/properties/{prop['property_id']}", json={"land_area_m2": None},
                     headers={**cust(ids), "If-Match-Version": str(prop["version"])})
    assert r.status_code == 200, r.text
    assert "land_area_m2" not in r.json()
