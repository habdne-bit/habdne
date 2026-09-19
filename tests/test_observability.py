"""Structured logging, health and readiness.

Ref: API_CONTRACTS §8; RFC-001 R6.3b.
"""
from __future__ import annotations

import json
import logging
import uuid

import pytest
from fastapi.testclient import TestClient

from turab.observability import REDACTED, JsonFormatter, redact


def _format(**extra):
    record = logging.LogRecord("turab.test", logging.INFO, __file__, 1, "msg", (), None)
    for k, v in extra.items():
        setattr(record, k, v)
    return json.loads(JsonFormatter().format(record))


def test_records_are_json_with_the_expected_envelope():
    out = _format(trace_id="abc")
    assert out["level"] == "INFO" and out["message"] == "msg"
    assert out["logger"] == "turab.test" and out["trace_id"] == "abc"
    assert "ts" in out


@pytest.mark.parametrize(
    "key", ["otp", "otp_code", "password", "token", "seller_expectation_dzd",
            "raw_text", "authorization", "notes"]
)
def test_sensitive_keys_are_redacted(key):
    """§8. Logs must not contain OTP codes or sensitive payloads."""
    assert _format(**{key: "secret-value"})[key] == REDACTED


def test_redaction_reaches_nested_structures():
    out = _format(access_record={"actor": "a", "extra": {"otp": "123456"}})
    assert out["access_record"]["extra"]["otp"] == REDACTED
    assert out["access_record"]["actor"] == "a"


def test_redaction_reaches_inside_lists():
    assert redact([{"otp": "1"}, {"safe": "2"}]) == [{"otp": REDACTED}, {"safe": "2"}]


def test_exceptions_log_type_and_message_not_a_traceback():
    """A traceback can carry query text and bound parameters."""
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord(
            "turab.test", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )
        out = json.loads(JsonFormatter().format(record))
    assert out["error"] == {"type": "ValueError", "message": "boom"}
    assert "Traceback" not in json.dumps(out)


def test_an_access_record_survives_redaction_intact(engine, ids):
    """The audit record carries references only, so nothing should be redacted."""
    from turab.auth.audit import AccessAuditor, RecordingAuditSink
    from turab.auth.subject import Subject
    from turab.auth.roles import Role

    sink = RecordingAuditSink()
    auditor = AccessAuditor(sink)
    subject = Subject(ids.ACC_OPERATOR, None, frozenset({Role.OPERATOR}), "ACTIVATED")
    auditor.read(subject=subject, operation_id="getRequestsRequestId", trace_id="t",
                 resource_kind="REQUEST", resource_id=ids.REQ_AMINA)
    out = _format(access_record=sink.records[0].as_dict())
    assert REDACTED not in json.dumps(out)


# --- health / readiness ----------------------------------------------------

@pytest.fixture
def client(engine):
    from turab.app import create_app

    with TestClient(create_app(engine=engine)) as c:
        yield c


def test_health_is_liveness_only(client):
    r = client.get("/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}


def test_readiness_checks_the_database(client):
    r = client.get("/ready")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ready"
    assert body["database"] == "ok"
    assert body["policy_operations"] == 64


def test_readiness_reports_503_when_the_database_is_unreachable(ids):
    """A readiness probe that only says 'process alive' keeps a broken
    instance in the load balancer."""
    from sqlalchemy import create_engine

    from turab.app import create_app

    broken = create_engine("postgresql+psycopg://turab:turab@127.0.0.1:1/nope")
    with TestClient(create_app(engine=broken), raise_server_exceptions=False) as c:
        r = c.get("/ready")
    assert r.status_code == 503
    assert r.json()["status"] == "not_ready"
    assert r.json()["database"] == "unavailable"


def test_probes_are_outside_the_api_contract(client):
    spec = client.get("/openapi.json").json()
    assert "/health" not in spec["paths"] and "/ready" not in spec["paths"]
