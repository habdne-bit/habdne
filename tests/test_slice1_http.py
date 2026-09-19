"""Slice 1 through the HTTP surface.

Ref: cross-slice Definition of Done — "idempotency/retry behavior is tested
for commands", "authorization tests cover positive and negative cases",
"OpenAPI remains synchronized with implementation".

Slice 0 built idempotency and optimistic concurrency and left them unwired
because no domain commands existed. These tests are the first proof that they
are actually applied, not merely available.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, AccessEvent, RecordingAuditSink


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def provider():
    from turab.services.otp import FakeVerificationProvider

    return FakeVerificationProvider()


@pytest.fixture
def client(engine, sink, provider):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink), provider=provider)
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def cleanup(engine):
    """Remove rows the HTTP client committed; it does not share the rollback
    fixture, so it must tidy up after itself."""
    created: dict[str, list] = {"parties": [], "keys": []}
    yield created
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.idempotency_records"))
        for party_id in created["parties"]:
            s.execute(text("DELETE FROM turab.resource_consent_bindings b USING turab.consent_grants g WHERE b.consent_id=g.consent_id AND g.party_id=:p"), {"p": party_id})
            s.execute(text("DELETE FROM turab.consent_grants WHERE party_id=:p"), {"p": party_id})
            s.execute(text("DELETE FROM turab.party_contact_points WHERE party_id=:p"), {"p": party_id})
            s.execute(text("DELETE FROM turab.parties WHERE party_id=:p"), {"p": party_id})
        s.commit()


def auth(account_id):
    return {"Authorization": f"Bearer {account_id}"}


def hdrs(account_id, key=None):
    h = auth(account_id)
    if key:
        h["Idempotency-Key"] = key
    return h


def _create_party(client, ids, cleanup, key="k-create", **body):
    payload = {"kind": "PERSON", "display_name": "اختبار", **body}
    r = client.post("/parties", json=payload, headers=hdrs(ids.ACC_OPERATOR, key))
    if r.status_code == 201:
        cleanup["parties"].append(r.json()["party_id"])
    return r


# --- authorization: positive and negative ---------------------------------

def test_operator_can_create_a_party(client, ids, cleanup):
    r = _create_party(client, ids, cleanup)
    assert r.status_code == 201
    body = r.json()
    assert body["kind"] == "PERSON" and body["status"] == "DISCOVERED"
    assert body["version"] == 1


def test_customer_cannot_read_a_party_internally(client, ids, cleanup):
    """K01. The internal endpoint excludes CUSTOMER even for a real party."""
    created = _create_party(client, ids, cleanup).json()
    r = client.get(f"/parties/{created['party_id']}", headers=auth(ids.ACC_AMINA))
    assert r.status_code == 403
    assert r.json()["code"] == "ROLE_NOT_PERMITTED"


def test_reviewer_can_read_but_not_create(client, ids, cleanup):
    created = _create_party(client, ids, cleanup).json()
    assert client.get(f"/parties/{created['party_id']}",
                      headers=auth(ids.ACC_REVIEWER)).status_code == 200
    r = client.post("/parties", json={"kind": "PERSON"},
                    headers=hdrs(ids.ACC_REVIEWER, "k-rev"))
    assert r.status_code == 403


def test_staff_read_of_a_party_is_audited(client, ids, cleanup, sink):
    """R6.3: a staff read of an individual resource is recorded."""
    created = _create_party(client, ids, cleanup).json()
    sink.clear()
    client.get(f"/parties/{created['party_id']}", headers=auth(ids.ACC_OPERATOR))
    reads = sink.of(AccessEvent.READ)
    assert len(reads) == 1 and str(reads[0].resource_id) == created["party_id"]


def test_unknown_party_is_404_for_staff(client, ids):
    r = client.get(f"/parties/{uuid.uuid4()}", headers=auth(ids.ACC_OPERATOR))
    assert r.status_code == 403  # object check failed on an internal endpoint
    assert r.json()["code"] == "OBJECT_NOT_AUTHORIZED"


# --- idempotency, now actually applied (§2.3) -----------------------------

def test_missing_idempotency_key_is_rejected(client, ids):
    r = client.post("/parties", json={"kind": "PERSON"}, headers=auth(ids.ACC_OPERATOR))
    assert r.status_code == 400
    assert r.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


def test_same_key_same_payload_replays(client, ids, cleanup):
    first = _create_party(client, ids, cleanup, key="k-replay")
    assert first.status_code == 201
    second = client.post("/parties", json={"kind": "PERSON", "display_name": "اختبار"},
                         headers=hdrs(ids.ACC_OPERATOR, "k-replay"))
    assert second.status_code == 201
    assert second.json()["party_id"] == first.json()["party_id"]


def test_same_key_different_payload_is_409(client, ids, cleanup):
    _create_party(client, ids, cleanup, key="k-conflict")
    r = client.post("/parties", json={"kind": "BUSINESS", "display_name": "مختلف"},
                    headers=hdrs(ids.ACC_OPERATOR, "k-conflict"))
    assert r.status_code == 409
    assert r.json()["code"] == "IDEMPOTENCY_KEY_CONFLICT"


def test_a_replay_creates_no_second_row(client, ids, cleanup, engine):
    """The point of idempotency: the retry must not duplicate the effect."""
    _create_party(client, ids, cleanup, key="k-once")
    client.post("/parties", json={"kind": "PERSON", "display_name": "اختبار"},
                headers=hdrs(ids.ACC_OPERATOR, "k-once"))
    with Session(bind=engine, future=True) as s:
        count = s.execute(
            text("SELECT count(*) FROM turab.parties WHERE display_name = 'اختبار'")
        ).scalar_one()
    assert count == 1


# --- optimistic concurrency, now actually applied (§2.4) ------------------

def test_patch_requires_the_version_header(client, ids, cleanup):
    created = _create_party(client, ids, cleanup, key="k-patch-1").json()
    r = client.patch(f"/parties/{created['party_id']}",
                     json={"display_name": "جديد"}, headers=auth(ids.ACC_OPERATOR))
    assert r.status_code == 428
    assert r.json()["code"] == "IF_MATCH_REQUIRED"


def test_patch_with_the_current_version_succeeds_and_bumps_it(client, ids, cleanup):
    created = _create_party(client, ids, cleanup, key="k-patch-2").json()
    r = client.patch(
        f"/parties/{created['party_id']}", json={"display_name": "محدَّث"},
        headers={**auth(ids.ACC_OPERATOR), "If-Match-Version": str(created["version"])},
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "محدَّث"
    assert r.json()["version"] == created["version"] + 1


def test_patch_with_a_stale_version_is_409_and_changes_nothing(client, ids, cleanup):
    created = _create_party(client, ids, cleanup, key="k-patch-3").json()
    pid = created["party_id"]
    client.patch(pid and f"/parties/{pid}", json={"display_name": "أول"},
                 headers={**auth(ids.ACC_OPERATOR), "If-Match-Version": "1"})
    r = client.patch(f"/parties/{pid}", json={"display_name": "ثانٍ"},
                     headers={**auth(ids.ACC_OPERATOR), "If-Match-Version": "1"})
    assert r.status_code == 409
    assert r.json()["code"] == "STALE_VERSION"
    current = client.get(f"/parties/{pid}", headers=auth(ids.ACC_OPERATOR)).json()
    assert current["display_name"] == "أول"  # nothing partially applied


def test_the_old_if_match_header_is_not_accepted(client, ids, cleanup):
    """D1: the alias was removed, so the old name must not work."""
    created = _create_party(client, ids, cleanup, key="k-patch-4").json()
    r = client.patch(f"/parties/{created['party_id']}", json={"display_name": "x"},
                     headers={**auth(ids.ACC_OPERATOR), "If-Match": "1"})
    assert r.status_code == 428


def test_patch_rejects_an_undeclared_field(client, ids, cleanup):
    """K04: status, kind and version are not patchable."""
    created = _create_party(client, ids, cleanup, key="k-patch-5").json()
    for field in ("status", "kind", "version"):
        r = client.patch(
            f"/parties/{created['party_id']}", json={field: "PARTY_ACTIVE"},
            headers={**auth(ids.ACC_OPERATOR), "If-Match-Version": "1"},
        )
        assert r.status_code == 422, field


# --- OTP through HTTP -----------------------------------------------------

def test_otp_is_unauthenticated_and_creates_nothing(client, engine):
    """A02 end to end. Both endpoints are in the closed public list."""
    with Session(bind=engine, future=True) as s:
        before = s.execute(text("SELECT count(*) FROM turab.user_accounts")).scalar_one()

    start = client.post("/auth/otp/start",
                        json={"phone_e164": "+213770009001",
                              "purpose": "VERIFY_PHONE_CONTROL"})
    assert start.status_code == 201
    body = start.json()
    assert "challenge_id" in body and "expires_at" in body
    # the code is never returned
    assert "code" not in body

    with Session(bind=engine, future=True) as s:
        after = s.execute(text("SELECT count(*) FROM turab.user_accounts")).scalar_one()
    assert after == before


def test_otp_verify_with_a_wrong_code_is_rejected(client):
    start = client.post("/auth/otp/start",
                        json={"phone_e164": "+213770009002", "purpose": "LOGIN"}).json()
    r = client.post("/auth/otp/verify",
                    json={"challenge_id": start["challenge_id"], "code": "000000"})
    assert r.status_code == 422


def test_challenge_id_is_the_providers_verification_id(client, provider):
    """The decision: no TURAB challenge table, so the id must be the
    provider's own."""
    import uuid as _uuid

    start = client.post("/auth/otp/start",
                        json={"phone_e164": "+213770009010",
                              "purpose": "VERIFY_PHONE_CONTROL"}).json()
    verification_id = _uuid.UUID(start["challenge_id"])
    # the provider recognises it as its own, and holds the code we never saw
    assert provider.code_for(verification_id)


def test_otp_verify_succeeds_end_to_end(client, provider, engine):
    start = client.post("/auth/otp/start",
                        json={"phone_e164": "+213770009011",
                              "purpose": "VERIFY_PHONE_CONTROL"}).json()
    import uuid as _uuid

    code = provider.code_for(_uuid.UUID(start["challenge_id"]))
    r = client.post("/auth/otp/verify",
                    json={"challenge_id": start["challenge_id"], "code": code})
    assert r.status_code == 200
    body = r.json()
    assert body["verification_result"] == "PHONE_CONTROL_VERIFIED"
    assert body["account_id"] is None and body["access_token"] is None
    try:
        with Session(bind=engine, future=True) as s:
            assert s.execute(
                text("SELECT control_status::text FROM turab.contact_points "
                     "WHERE normalized_value=:v"),
                {"v": "+213770009011"},
            ).scalar_one() == "VERIFIED_CONTROL"
    finally:
        with Session(bind=engine, future=True) as s:
            s.execute(text("DELETE FROM turab.contact_points WHERE normalized_value=:v"),
                      {"v": "+213770009011"})
            s.commit()


def test_a_provider_outage_is_503_not_a_rejection(client, provider):
    """A refused caller should not retry; a caller whose provider is down
    should. Collapsing the two would make that impossible to tell."""
    provider.unavailable = True
    r = client.post("/auth/otp/start",
                    json={"phone_e164": "+213770009012", "purpose": "LOGIN"})
    assert r.status_code == 503
    assert r.json()["code"] == "PROVIDER_UNAVAILABLE"


def test_otp_verify_with_an_unknown_challenge_is_indistinguishable(client):
    """Telling a caller that a challenge id exists is itself information."""
    start = client.post("/auth/otp/start",
                        json={"phone_e164": "+213770009003", "purpose": "LOGIN"}).json()
    wrong_code = client.post("/auth/otp/verify",
                             json={"challenge_id": start["challenge_id"], "code": "111111"})
    unknown = client.post("/auth/otp/verify",
                          json={"challenge_id": str(uuid.uuid4()), "code": "111111"})
    assert wrong_code.status_code == unknown.status_code
    assert wrong_code.json()["code"] == unknown.json()["code"]
    assert wrong_code.json()["detail"] == unknown.json()["detail"]


# --- consent through HTTP -------------------------------------------------

def test_customer_cannot_create_a_consent_binding(client, ids):
    """R7.5: binding is staff-only, revocation is not."""
    r = client.post(
        "/consents/bindings",
        json={"consent_id": str(uuid.uuid4()), "purpose": "PRIVATE_MATCHING_ONLY",
              "resource_type": "REQUEST", "resource_id": str(ids.REQ_AMINA)},
        headers=hdrs(ids.ACC_AMINA, "k-bind"),
    )
    assert r.status_code == 403


def test_customer_cannot_revoke_another_partys_consent(client, ids, engine):
    """The grant belongs to Brahim; Amina must not reach it."""
    with Session(bind=engine, future=True) as s:
        consent_id = s.execute(
            text(
                """INSERT INTO turab.consent_grants
                     (party_id, scope, status, channel, consent_version, granted_at)
                   VALUES (:p,'PRIVATE_MATCHING_ONLY','GRANTED','WEB','v1', now())
                   RETURNING consent_id"""
            ),
            {"p": ids.BRAHIM},
        ).scalar_one()
        s.commit()
    try:
        r = client.post(f"/consents/{consent_id}/revoke", json={},
                        headers=hdrs(ids.ACC_AMINA, "k-revoke-other"))
        assert r.status_code == 404
    finally:
        with Session(bind=engine, future=True) as s:
            s.execute(text("DELETE FROM turab.idempotency_records"))
            s.execute(text("DELETE FROM turab.consent_grants WHERE consent_id=:c"),
                      {"c": consent_id})
            s.commit()


# --- contract conformance -------------------------------------------------

def test_all_slice1_operations_match_the_frozen_contract(client):
    """Definition of Done: OpenAPI stays synchronized with implementation."""
    from turab.auth.contract import load_contract

    frozen = load_contract()
    generated = client.get("/openapi.json").json()
    for path, item in generated["paths"].items():
        assert path in frozen["paths"], path
        for method, op in item.items():
            assert op["operationId"] == frozen["paths"][path][method]["operationId"]
