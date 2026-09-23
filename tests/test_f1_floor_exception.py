"""F-1: numbered exception R9.2-EX-01 to the DTO floor, and its edges.

Ref: decision F-1; RFC-001 R9.2; ADR-06 ("unless explicitly approved by the
relevant sharing contract"); the effective contract's `Property`, `Request`.

The exception is proved from both sides: that it covers exactly the
operations the contract obliges it to, and that it covers NOTHING else — not a
nested object, not a `/me` read, not the public list, not another floor field.
"""
from __future__ import annotations

import uuid

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.dto.boundaries import (
    FLOOR_EXCEPTIONS, NEVER_SERIALIZED, Audience, FieldLeak,
    assert_no_forbidden_fields,
)

CONTRACT = "docs/handoff/05_API/openapi_v0.2.3.yaml"
FIELDS = {"management_mode", "claim_status"}


def _operations_the_contract_obliges() -> set[str]:
    """CUSTOMER-callable operations whose 2xx body is `Property` or `Request`."""
    with open(CONTRACT, encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    found = set()
    for ops in spec["paths"].values():
        for method, op in ops.items():
            if method not in ("get", "post", "patch", "put", "delete"):
                continue
            if "CUSTOMER" not in (op.get("x-roles") or []):
                continue
            for status, response in op.get("responses", {}).items():
                if not status.startswith("2"):
                    continue
                schema = (response.get("content", {}).get("application/json", {})
                          .get("schema", {}))
                if schema.get("$ref", "").rsplit("/", 1)[-1] in ("Property", "Request"):
                    found.add(op["operationId"])
    return found


def test_there_is_exactly_one_numbered_exception():
    assert [e.number for e in FLOOR_EXCEPTIONS] == ["R9.2-EX-01"]
    assert FLOOR_EXCEPTIONS[0].fields == FIELDS


def test_the_exception_covers_exactly_the_operations_the_contract_obliges():
    """Seven, derived from the contract rather than copied from it."""
    obliged = _operations_the_contract_obliges()
    assert len(obliged) == 7, obliged
    assert FLOOR_EXCEPTIONS[0].operations == obliged


def test_the_fields_stay_in_the_floor():
    """Not deleted from `NEVER_SERIALIZED`: the exception is a bounded hole,
    not a lowered floor."""
    assert FIELDS <= NEVER_SERIALIZED


def test_the_basis_is_the_schema_not_that_the_customer_sent_the_values():
    basis = FLOOR_EXCEPTIONS[0].basis
    assert "schema" in basis and "NOT that the customer supplied" in basis


@pytest.mark.parametrize("operation", sorted(FLOOR_EXCEPTIONS[0].operations))
def test_the_exception_admits_the_fields_at_the_top_level(operation):
    assert_no_forbidden_fields({"management_mode": "SELF_MANAGED",
                                "claim_status": "CLAIMED"},
                               Audience.CUSTOMER, operation_id=operation)


@pytest.mark.parametrize("operation", sorted(FLOOR_EXCEPTIONS[0].operations))
def test_the_exception_does_not_reach_a_nested_object(operation):
    with pytest.raises(FieldLeak):
        assert_no_forbidden_fields({"nested": {"claim_status": "CLAIMED"}},
                                   Audience.CUSTOMER, operation_id=operation)


@pytest.mark.parametrize("operation", sorted(FLOOR_EXCEPTIONS[0].operations))
def test_the_exception_does_not_admit_any_other_floor_field(operation):
    with pytest.raises(FieldLeak):
        assert_no_forbidden_fields({"seller_expectation_dzd": 1},
                                   Audience.CUSTOMER, operation_id=operation)


@pytest.mark.parametrize("operation", [
    None, "getMePropertiesPropertyId", "getMeRequestsRequestId",
    "getPublicProperties", "postPropertiesPropertyIdOffers",
])
@pytest.mark.parametrize("audience", [Audience.CUSTOMER, Audience.PUBLIC])
def test_everywhere_else_the_fields_are_refused(operation, audience):
    with pytest.raises(FieldLeak):
        assert_no_forbidden_fields({"claim_status": "CLAIMED"}, audience,
                                   operation_id=operation)


# --- over HTTP ---------------------------------------------------------------

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
    return {"Idempotency-Key": f"f1-{uuid.uuid4()}"}


def test_customer_command_responses_carry_the_required_fields(client, ids):
    """The contract requires them; the floor check runs on these responses
    and admits them only through R9.2-EX-01 (without it, a 500)."""
    prop = client.post("/properties", headers={**cust(ids), **key()}, json={
        "property_type": "LAND", "supply_mode": "PUBLIC",
        "management_mode": "SELF_MANAGED", "claim_status": "CLAIMED"})
    assert prop.status_code == 201, prop.text
    assert FIELDS <= set(prop.json())

    req = client.post("/requests", headers={**cust(ids), **key()}, json={
        "party_id": str(ids.AMINA), "transaction_intent": "BUY",
        "intent": "ACTIVE_SEARCH", "management_mode": "SELF_MANAGED",
        "claim_status": "CLAIMED"})
    assert req.status_code == 201, req.text
    assert FIELDS <= set(req.json())


def test_the_me_reads_never_carry_them(client, ids):
    prop = client.post("/properties", headers={**cust(ids), **key()}, json={
        "property_type": "LAND", "supply_mode": "PUBLIC",
        "management_mode": "SELF_MANAGED", "claim_status": "CLAIMED"}).json()
    got = client.get(f"/me/properties/{prop['property_id']}", headers=cust(ids))
    assert got.status_code == 200, got.text
    assert not FIELDS & set(got.json())

    req = client.post("/requests", headers={**cust(ids), **key()}, json={
        "party_id": str(ids.AMINA), "transaction_intent": "BUY",
        "intent": "ACTIVE_SEARCH", "management_mode": "SELF_MANAGED",
        "claim_status": "CLAIMED"}).json()
    got = client.get(f"/me/requests/{req['request_id']}", headers=cust(ids))
    assert got.status_code == 200, got.text
    assert not FIELDS & set(got.json())


def test_the_public_types_cannot_carry_them():
    """The public list itself is step 6 and is not served yet — an HTTP check
    against it would pass on a 404 body and prove nothing. What exists now is
    the public DTO TYPES, and they have no such field to render."""
    from turab.dto.boundaries import PublicOfferSummary, PublicPropertySummary

    for model in (PublicPropertySummary, PublicOfferSummary):
        assert not FIELDS & set(model.model_fields), model.__name__
