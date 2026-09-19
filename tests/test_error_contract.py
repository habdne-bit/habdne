"""The problem+json error contract.

Ref: API_CONTRACTS §2.5, §8; RFC-001 §12; the frozen `Problem` schema.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from turab.api.problems import (
    _CATALOGUE,
    CONFLICT_DETAIL,
    DetailLeak,
    ProblemCode,
    coded,
    problem,
)

REQUIRED_FIELDS = {"title", "status", "code", "trace_id"}


@pytest.fixture
def client(engine):
    from turab.app import create_app

    with TestClient(create_app(engine=engine), raise_server_exceptions=False) as c:
        yield c


def _auth(account_id):
    return {"Authorization": f"Bearer {account_id}"}


def test_every_catalogued_code_has_one_status():
    """A code that means two statuses is a contract the client cannot rely on."""
    assert set(_CATALOGUE) == set(ProblemCode)
    for code, (status, title) in _CATALOGUE.items():
        assert 400 <= status <= 599 and title


def test_required_fields_match_the_frozen_problem_schema():
    from turab.auth.contract import load_contract

    frozen = load_contract()["components"]["schemas"]["Problem"]
    assert set(frozen["required"]) == REQUIRED_FIELDS
    body = coded(ProblemCode.NOT_FOUND, "t").body.decode()
    import json

    assert REQUIRED_FIELDS <= set(json.loads(body))


@pytest.mark.parametrize(
    "detail",
    [
        "SELECT * FROM turab.requests",
        "psycopg.errors.UniqueViolation",
        "Traceback (most recent call last)",
        "relation turab.parties does not exist",
        "DETAIL: Key (id)=(1) already exists",
        "the OTP is 123456",
    ],
)
def test_detail_refuses_implementation_and_sensitive_text(detail):
    """§2.5 / §8. Enforced, so a future call site cannot quietly leak."""
    with pytest.raises(DetailLeak):
        problem(400, "X", "X", "t", detail)


def test_ordinary_detail_is_allowed():
    r = problem(400, "X", "X", "t", "The request body failed validation.")
    assert r.status_code == 400


def test_validation_errors_carry_field_errors_not_values(client, ids):
    """K04. The field location is echoed; the input value never is."""
    r = client.get("/me/requests/not-a-uuid", headers=_auth(ids.ACC_AMINA))
    assert r.status_code == 422
    body = r.json()
    assert body["code"] == "VALIDATION_FAILED"
    assert body["field_errors"]
    assert "not-a-uuid" not in str(body)


def test_unknown_route_is_problem_json(client, ids):
    r = client.get("/no/such/route", headers=_auth(ids.ACC_AMINA))
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    assert REQUIRED_FIELDS <= set(r.json())


def test_method_not_allowed_is_problem_json(client, ids):
    r = client.post("/me/party", headers=_auth(ids.ACC_AMINA))
    assert r.status_code == 405
    assert REQUIRED_FIELDS <= set(r.json())


def test_unauthenticated_is_a_coded_problem(client):
    r = client.get("/me/party")
    assert r.status_code == 401
    assert r.json()["code"] == "UNAUTHENTICATED"
    assert r.headers["content-type"].startswith("application/problem+json")


def test_an_unhandled_error_returns_a_code_and_a_trace_id(engine, ids):
    """The trace id is the only bridge between client and log; the exception
    text stays in the log."""
    from fastapi import APIRouter

    from turab.app import create_app

    app = create_app(engine=engine)
    router = APIRouter()

    @router.get("/boom", include_in_schema=False)
    def boom():
        raise RuntimeError("database password is hunter2")

    app.include_router(router)
    with TestClient(app, raise_server_exceptions=False) as c:
        r = c.get("/boom")
    assert r.status_code == 500
    body = r.json()
    assert body["code"] == "INTERNAL_ERROR"
    assert body["trace_id"]
    assert "hunter2" not in str(body)


def test_conflict_detail_is_a_fixed_string():
    """No call site can widen the claim-conflict body."""
    from turab.api.problems import for_denial
    from turab.auth.policy import DenyReason
    import json

    widened = for_denial(
        DenyReason.CLAIM_AUTHORITY_CONFLICT, "t", customer_scoped=True,
        detail="claimed by account 123 and account 456",
    )
    body = json.loads(widened.body.decode())
    assert body["detail"] == CONFLICT_DETAIL
    assert "123" not in str(body)


@pytest.mark.parametrize("path,method,expected", [
    ("/me/party", "post", 405),
    ("/no/such/route", "get", 404),
])
def test_transport_status_is_preserved_not_rewritten(client, ids, path, method, expected):
    """A mapping mistake must not turn a 405 into a 403: the transport status
    wins, and the code is chosen to agree with it."""
    r = getattr(client, method)(path, headers=_auth(ids.ACC_AMINA))
    assert r.status_code == expected
    assert r.json()["status"] == expected
