"""End-to-end HTTP behaviour.

Ref: RFC-001 decision 2 (404 conceals / 403 prohibits), §12, R10.4, R14.2.
This is the behavioural proof that the layering holds through a real request,
which an architecture test alone cannot give.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from turab.auth.audit import AccessAuditor, AccessEvent, RecordingAuditSink

UNKNOWN = uuid.UUID("00000000-0000-4000-8000-0000000000ff")


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app) as c:
        yield c


def auth(account_id) -> dict[str, str]:
    return {"Authorization": f"Bearer {account_id}"}


# --- authentication --------------------------------------------------------

def test_no_token_is_401(client):
    assert client.get("/me/party").status_code == 401


def test_garbage_token_is_401(client):
    assert client.get("/me/party", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_unknown_account_is_401(client):
    assert client.get("/me/party", headers=auth(UNKNOWN)).status_code == 401


# --- decision 2: 404 conceals, 403 prohibits -------------------------------

def test_customer_reads_own_request(client, ids):
    r = client.get(f"/me/requests/{ids.REQ_AMINA}", headers=auth(ids.ACC_AMINA))
    assert r.status_code == 200
    assert r.json()["request_id"] == str(ids.REQ_AMINA)


def test_another_customers_request_is_404_not_403(client, ids):
    """S02. A 403 here would confirm the id exists — an existence oracle."""
    r = client.get(f"/me/requests/{ids.REQ_AMINA}", headers=auth(ids.ACC_KHADIJA))
    assert r.status_code == 404
    assert r.json()["code"] == "NOT_FOUND"


def test_a_nonexistent_id_is_indistinguishable_from_an_unowned_one(client, ids):
    """The concealment is only real if the two cases look identical."""
    unowned = client.get(f"/me/requests/{ids.REQ_AMINA}", headers=auth(ids.ACC_KHADIJA))
    absent = client.get(f"/me/requests/{UNKNOWN}", headers=auth(ids.ACC_KHADIJA))
    assert unowned.status_code == absent.status_code == 404
    assert unowned.json()["code"] == absent.json()["code"]
    assert unowned.json().keys() == absent.json().keys()


def test_customer_on_an_internal_endpoint_is_403(client, ids):
    """S03 / K01 / R5.3b. Role refusal, on an endpoint that conceals nothing."""
    r = client.get(f"/requests/{ids.REQ_AMINA}", headers=auth(ids.ACC_AMINA))
    assert r.status_code == 403
    assert r.json()["code"] == "ROLE_NOT_PERMITTED"


def test_staff_on_a_me_endpoint_is_403(client, ids):
    """R5.4. A staff role never widens /me/*."""
    r = client.get("/me/party", headers=auth(ids.ACC_OPERATOR))
    assert r.status_code == 403


def test_customer_reason_codes_is_403_staff_is_200(client, ids):
    """S21b / S21c, decision 5."""
    assert client.get("/reason-codes", headers=auth(ids.ACC_AMINA)).status_code == 403
    for account in (ids.ACC_OPERATOR, ids.ACC_REVIEWER, ids.ACC_ADMIN):
        assert client.get("/reason-codes", headers=auth(account)).status_code == 200


# --- problem contract ------------------------------------------------------

def test_problem_responses_carry_the_required_fields(client, ids):
    r = client.get(f"/me/requests/{UNKNOWN}", headers=auth(ids.ACC_KHADIJA))
    body = r.json()
    assert {"title", "status", "code", "trace_id"} <= set(body)
    assert r.headers["content-type"].startswith("application/problem+json")


def test_trace_id_is_echoed(client, ids):
    r = client.get("/me/party", headers={**auth(ids.ACC_AMINA), "x-trace-id": "abc123"})
    assert r.headers["x-trace-id"] == "abc123"


def test_problem_detail_never_leaks_database_text(client, ids):
    """API_CONTRACTS §2.5."""
    r = client.get(f"/me/requests/{UNKNOWN}", headers=auth(ids.ACC_KHADIJA))
    detail = r.json().get("detail", "")
    for leak in ("SELECT", "psycopg", "Traceback", "turab.requests"):
        assert leak not in detail


# --- audit through the stack ----------------------------------------------

def test_denied_request_is_audited(client, ids, sink):
    client.get(f"/me/requests/{ids.REQ_AMINA}", headers=auth(ids.ACC_KHADIJA))
    assert len(sink.of(AccessEvent.DENIED)) == 1


def test_list_endpoint_audits_once(client, ids, sink):
    r = client.get("/backoffice/queues/requests", headers=auth(ids.ACC_OPERATOR))
    assert r.status_code == 200
    assert len(sink.of(AccessEvent.LIST)) == 1
    assert sink.of(AccessEvent.READ) == []


# --- contract conformance (R14.2) -----------------------------------------

def test_generated_paths_exist_in_the_frozen_contract(client):
    """R14.1-R14.2. The generated document is checked against the contract,
    never the other way round.

    "The contract" is the frozen file PLUS the approved addenda under
    docs/contract/addenda — additions the correction overlay cannot carry
    (G3-6). An addendum route must be ABSENT from the frozen file: it may only
    add, never shadow.
    """
    from turab.auth.contract import load_addenda, load_contract

    frozen = load_contract()
    added: dict[str, dict] = {}
    for addendum in load_addenda():
        for path, item in addendum["paths"].items():
            assert path not in frozen["paths"] or not (
                set(item) & set(frozen["paths"][path])), (
                f"{path}: an addendum may not redeclare a frozen operation")
            added.setdefault(path, {}).update(item)
    generated = client.get("/openapi.json").json()
    for path, item in generated["paths"].items():
        source = frozen["paths"] if path in frozen["paths"] else added
        assert path in source, f"{path} is in neither the contract nor an addendum"
        for method, op in item.items():
            declared = source[path].get(method)
            assert declared is not None, f"{method.upper()} {path} not in contract"
            assert op["operationId"] == declared["operationId"]


def test_health_and_ready_are_outside_the_contract(client):
    """Operational endpoints are excluded from the schema, so they cannot be
    mistaken for contract drift."""
    generated = client.get("/openapi.json").json()
    assert "/health" not in generated["paths"]
    assert client.get("/health").status_code == 200
    # 64 frozen operations + 3 from the approved G3-6 addendum.
    assert client.get("/ready").json()["policy_operations"] == 67
