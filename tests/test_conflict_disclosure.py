"""INV-1 disclosure: explicit internally, concealment-safe externally.

An unrelated actor receives 404. A known conflicting claimant, or authorized
staff, receives a typed 409 that reveals neither the other claimant's identity
nor any detail of the conflict. Operations always get the full picture from the
audit record, whatever the caller was told.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from turab.auth.audit import AccessAuditor, AccessEvent, RecordingAuditSink
from turab.auth.loaders import ResourceKind
from turab.auth.policy import DenyReason

UNKNOWN = uuid.UUID("00000000-0000-4000-8000-0000000000ff")


def _contest(session, property_id, *accounts):
    """Make `property_id` claimed by several distinct accounts."""
    for account in accounts:
        session.execute(
            text(
                """INSERT INTO turab.record_claim_events
                     (property_id, claimed_by_account_id) VALUES (:p, :a)"""
            ),
            {"p": property_id, "a": account},
        )


# --- service level ---------------------------------------------------------

def test_conflicting_claimant_is_told(session, subject_of, ids, access_for):
    """Amina is one of the claimants: she may learn the claim is contested."""
    _contest(session, ids.CLAIMED_HOUSE, ids.ACC_KHADIJA)
    access = access_for(subject_of(ids.ACC_AMINA))
    result = access.read_resource(
        ResourceKind.PROPERTY, ids.CLAIMED_HOUSE, "getMePropertiesPropertyId"
    )
    assert result.reason is DenyReason.CLAIM_AUTHORITY_CONFLICT


def test_the_other_claimant_is_also_told(session, subject_of, ids, access_for):
    """Symmetric: both sides of the conflict are entitled."""
    _contest(session, ids.CLAIMED_HOUSE, ids.ACC_KHADIJA)
    access = access_for(subject_of(ids.ACC_KHADIJA))
    result = access.read_resource(
        ResourceKind.PROPERTY, ids.CLAIMED_HOUSE, "getMePropertiesPropertyId"
    )
    assert result.reason is DenyReason.CLAIM_AUTHORITY_CONFLICT


@pytest.mark.parametrize("staff", ["ACC_OPERATOR", "ACC_REVIEWER", "ACC_ADMIN"])
def test_authorized_staff_are_told(session, subject_of, ids, access_for, staff):
    _contest(session, ids.CLAIMED_HOUSE, ids.ACC_KHADIJA)
    access = access_for(subject_of(getattr(ids, staff)))
    result = access.read_resource(
        ResourceKind.PROPERTY, ids.CLAIMED_HOUSE, "getPropertiesPropertyId"
    )
    assert result.reason is DenyReason.CLAIM_AUTHORITY_CONFLICT


def test_an_unrelated_customer_is_not_told(session, subject_of, ids, access_for):
    """The actor who claimed nothing sees the ordinary concealment."""
    # Amina and the second account contest it; a third, unrelated customer asks.
    _contest(session, ids.CLAIMED_HOUSE, ids.ACC_AMINA_SECOND)
    access = access_for(subject_of(ids.ACC_KHADIJA))
    result = access.read_resource(
        ResourceKind.PROPERTY, ids.CLAIMED_HOUSE, "getMePropertiesPropertyId"
    )
    assert result.reason is DenyReason.OBJECT_NOT_AUTHORIZED
    assert result.reason is not DenyReason.CLAIM_AUTHORITY_CONFLICT


# --- audit is explicit internally regardless -------------------------------

def test_audit_is_full_even_when_the_caller_is_told_nothing(session, subject_of, ids,
                                                            access_for, auditor):
    """The split lives between the audit record and the response."""
    _contest(session, ids.CLAIMED_HOUSE, ids.ACC_AMINA_SECOND)
    access = access_for(subject_of(ids.ACC_KHADIJA))
    access.read_resource(
        ResourceKind.PROPERTY, ids.CLAIMED_HOUSE, "getMePropertiesPropertyId"
    )
    records = auditor.sink.of(AccessEvent.CLAIM_AUTHORITY_CONFLICT)
    assert len(records) == 1
    assert records[0].extra["claim_account_count"] == 2
    assert len(records[0].extra["claim_account_ids"]) == 2
    assert records[0].extra["disclosed_to_caller"] is False


def test_audit_marks_when_the_caller_was_told(session, subject_of, ids,
                                              access_for, auditor):
    _contest(session, ids.CLAIMED_HOUSE, ids.ACC_KHADIJA)
    access = access_for(subject_of(ids.ACC_AMINA))
    access.read_resource(
        ResourceKind.PROPERTY, ids.CLAIMED_HOUSE, "getMePropertiesPropertyId"
    )
    record = auditor.sink.of(AccessEvent.CLAIM_AUTHORITY_CONFLICT)[0]
    assert record.extra["disclosed_to_caller"] is True


# --- HTTP level ------------------------------------------------------------

@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app) as c:
        yield c


@pytest.fixture
def contested(engine, ids):
    """Contest the property for the duration of one HTTP test, then undo it.

    The HTTP client uses its own sessions, so the surrounding rollback fixture
    cannot cover it; this cleans up explicitly.
    """
    from sqlalchemy.orm import Session

    marker = uuid.uuid4()
    with Session(bind=engine, future=True) as s:
        s.execute(
            text(
                """INSERT INTO turab.record_claim_events
                     (claim_event_id, property_id, claimed_by_account_id)
                   VALUES (:e, :p, :a)"""
            ),
            {"e": marker, "p": ids.CLAIMED_HOUSE, "a": ids.ACC_KHADIJA},
        )
        s.commit()
    yield
    with Session(bind=engine, future=True) as s:
        s.execute(
            text("DELETE FROM turab.record_claim_events WHERE claim_event_id = :e"),
            {"e": marker},
        )
        s.commit()


def _auth(account_id):
    return {"Authorization": f"Bearer {account_id}"}


def test_http_claimant_gets_409(client, ids, contested):
    r = client.get(f"/me/properties/{ids.CLAIMED_HOUSE}", headers=_auth(ids.ACC_AMINA))
    assert r.status_code == 409
    assert r.json()["code"] == "CLAIM_AUTHORITY_CONFLICT"


def test_http_staff_gets_409(client, ids, contested):
    r = client.get(f"/me/properties/{ids.CLAIMED_HOUSE}", headers=_auth(ids.ACC_OPERATOR))
    # staff are refused /me/* by role before the object is reached
    assert r.status_code == 403


def test_http_unrelated_customer_gets_404(client, ids, contested):
    """The unrelated actor must be unable to distinguish this from absence."""
    r = client.get(
        f"/me/properties/{ids.CLAIMED_HOUSE}", headers=_auth(ids.ACC_AMINA_SECOND)
    )
    assert r.status_code == 404
    absent = client.get(f"/me/properties/{UNKNOWN}", headers=_auth(ids.ACC_AMINA_SECOND))
    assert absent.status_code == 404
    assert r.json() == {**absent.json(), "trace_id": r.json()["trace_id"]}


def test_the_409_body_discloses_no_claimant_and_no_details(client, ids, contested):
    """Typed, but says only THAT the claim is contested."""
    r = client.get(f"/me/properties/{ids.CLAIMED_HOUSE}", headers=_auth(ids.ACC_AMINA))
    body = r.json()
    assert set(body) == {"type", "title", "status", "code", "trace_id", "detail"}
    serialized = str(body)
    for leak in (
        str(ids.ACC_KHADIJA), str(ids.ACC_AMINA), str(ids.KHADIJA),
        "claim_account_ids", "claim_account_count", "claimed_by", "claimed_at",
    ):
        assert leak not in serialized, f"the 409 body leaks {leak!r}"
    # no count of claimants, however phrased
    assert "2" not in body["detail"]


def test_conflict_is_audited_at_http_level(client, ids, contested, sink):
    client.get(f"/me/properties/{ids.CLAIMED_HOUSE}", headers=_auth(ids.ACC_AMINA))
    records = sink.of(AccessEvent.CLAIM_AUTHORITY_CONFLICT)
    assert len(records) == 1
    assert records[0].extra["disclosed_to_caller"] is True
    assert records[0].extra["claim_account_count"] == 2
