"""Object authorization on Slice 1's command surface.

These exist because Slice 1 first shipped the role gate WITHOUT the object
gate. A customer could PATCH any party, attach a phone to any party, and grant
consent on any party — a live BOLA of exactly the kind K01/K02 and RFC-001 §4
forbid, on write paths rather than reads.

Each test below is the exploit, asserted closed.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, AccessEvent, RecordingAuditSink


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
def clean_keys(engine):
    yield
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.idempotency_records"))
        s.commit()


def cust(ids):
    """Amina: CUSTOMER, whose party is ids.AMINA."""
    return {"Authorization": f"Bearer {ids.ACC_AMINA}"}


def staff(ids):
    return {"Authorization": f"Bearer {ids.ACC_OPERATOR}"}


def key(k):
    return {"Idempotency-Key": k}


# --- the exploit, closed --------------------------------------------------

def test_customer_cannot_patch_another_partys_record(client, ids, engine):
    """The original defect: this returned 200 and renamed the party."""
    before = _display_name(engine, ids.BRAHIM)
    r = client.patch(
        f"/parties/{ids.BRAHIM}", json={"display_name": "PWNED"},
        headers={**cust(ids), "If-Match-Version": "1"},
    )
    assert r.status_code == 403
    assert r.json()["code"] == "OBJECT_NOT_AUTHORIZED"
    assert _display_name(engine, ids.BRAHIM) == before


def test_customer_cannot_attach_a_phone_to_another_party(client, ids, engine):
    r = client.post(
        f"/parties/{ids.BRAHIM}/contact-points/phone",
        json={"phone_e164": "+213700000901"},
        headers={**cust(ids), **key("bola-phone")},
    )
    assert r.status_code == 403
    with Session(bind=engine, future=True) as s:
        assert s.execute(
            text("SELECT count(*) FROM turab.contact_points WHERE normalized_value=:v"),
            {"v": "+213700000901"},
        ).scalar_one() == 0


def test_customer_cannot_grant_consent_on_another_party(client, ids, engine):
    """Consent granted on someone else's behalf is the worst of the three."""
    r = client.post(
        f"/parties/{ids.BRAHIM}/consents",
        json={"scope": "PUBLIC_LISTING_ALLOWED", "channel": "WEB",
              "consent_version": "v1", "granted_at": "2026-09-19T10:00:00Z"},
        headers={**cust(ids), **key("bola-consent")},
    )
    assert r.status_code == 403
    with Session(bind=engine, future=True) as s:
        assert s.execute(
            text("""SELECT count(*) FROM turab.consent_grants
                     WHERE party_id=:p AND consent_version='v1'
                       AND scope='PUBLIC_LISTING_ALLOWED'"""),
            {"p": ids.BRAHIM},
        ).scalar_one() == 0


def test_customer_cannot_create_an_arbitrary_party(client, ids, engine):
    """Creating a party is a staff operation.

    Allowing it here would produce a record with no owner that its creator
    could never read back, and hand customers an unbounded write primitive.

    The refusal is now `ROLE_NOT_PERMITTED`, not `OBJECT_NOT_AUTHORIZED`:
    decision D7 / CORRECTION-001 narrowed this operation to ADMIN and
    OPERATOR, so the ROLE gate denies before the object gate is reached. That
    is a stronger position, not a weaker one — the object gate below is still
    in place as the second lock, and
    `test_the_object_gate_on_party_creation_is_still_present` proves it.
    """
    r = client.post("/parties", json={"kind": "PERSON", "display_name": "orphan"},
                    headers={**cust(ids), **key("bola-create")})
    assert r.status_code == 403
    assert r.json()["code"] == "ROLE_NOT_PERMITTED"
    with Session(bind=engine, future=True) as s:
        assert s.execute(
            text("SELECT count(*) FROM turab.parties WHERE display_name='orphan'")
        ).scalar_one() == 0


def test_every_refusal_is_audited(client, ids, sink):
    """A customer probing party ids is precisely the signal worth keeping."""
    sink.clear()
    client.patch(f"/parties/{ids.BRAHIM}", json={"display_name": "x"},
                 headers={**cust(ids), "If-Match-Version": "1"})
    denials = sink.of(AccessEvent.DENIED)
    assert denials and denials[-1].reason_code == "OBJECT_NOT_AUTHORIZED"


# --- the positive half, without which the above proves only refusal -------

def test_customer_may_patch_their_own_party(client, ids, engine):
    version = _version(engine, ids.AMINA)
    r = client.patch(
        f"/parties/{ids.AMINA}", json={"display_name": "أمينة (محدَّث)"},
        headers={**cust(ids), "If-Match-Version": str(version)},
    )
    assert r.status_code == 200
    assert r.json()["display_name"] == "أمينة (محدَّث)"
    _restore(engine, ids.AMINA, "أمينة (مشترية)")


def test_customer_may_grant_consent_on_their_own_party(client, ids, engine):
    r = client.post(
        f"/parties/{ids.AMINA}/consents",
        json={"scope": "CONTACT_BEFORE_SHARING", "channel": "WEB",
              "consent_version": "own-v1", "granted_at": "2026-09-19T10:00:00Z"},
        headers={**cust(ids), **key("own-consent")},
    )
    assert r.status_code == 201
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.consent_grants WHERE consent_version='own-v1'"))
        s.commit()


def test_staff_may_act_on_any_party(client, ids, engine):
    """Staff authority is by role plus a recorded purpose, not ownership."""
    version = _version(engine, ids.BRAHIM)
    r = client.patch(
        f"/parties/{ids.BRAHIM}", json={"display_name": "تعديل موظف"},
        headers={**staff(ids), "If-Match-Version": str(version)},
    )
    assert r.status_code == 200
    _restore(engine, ids.BRAHIM, "ابراهيم (مالك)")


def test_staff_may_still_create_parties(client, ids, engine):
    r = client.post("/parties", json={"kind": "BUSINESS", "display_name": "شركة"},
                    headers={**staff(ids), **key("staff-create")})
    assert r.status_code == 201
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.parties WHERE party_id=:p"),
                  {"p": r.json()["party_id"]})
        s.commit()


# --- an account with no party --------------------------------------------

def test_a_customer_with_no_party_can_act_on_nothing(client, ids, engine):
    """R3.1 on the write surface: a null owner matches nobody."""
    with Session(bind=engine, future=True) as s:
        s.execute(text("UPDATE turab.user_accounts SET party_id=NULL WHERE account_id=:a"),
                  {"a": ids.ACC_AMINA_SECOND})
        s.commit()
    try:
        r = client.patch(f"/parties/{ids.AMINA}", json={"display_name": "x"},
                         headers={"Authorization": f"Bearer {ids.ACC_AMINA_SECOND}",
                                  "If-Match-Version": "1"})
        assert r.status_code == 403
    finally:
        with Session(bind=engine, future=True) as s:
            s.execute(text("UPDATE turab.user_accounts SET party_id=:p WHERE account_id=:a"),
                      {"p": ids.AMINA, "a": ids.ACC_AMINA_SECOND})
            s.commit()


# --- helpers --------------------------------------------------------------

def _display_name(engine, party_id):
    with Session(bind=engine, future=True) as s:
        return s.execute(
            text("SELECT display_name FROM turab.parties WHERE party_id=:p"),
            {"p": party_id},
        ).scalar_one()


def _version(engine, party_id):
    with Session(bind=engine, future=True) as s:
        return s.execute(
            text("SELECT version FROM turab.parties WHERE party_id=:p"),
            {"p": party_id},
        ).scalar_one()


def _restore(engine, party_id, name):
    with Session(bind=engine, future=True) as s:
        s.execute(text("UPDATE turab.parties SET display_name=:n WHERE party_id=:p"),
                  {"n": name, "p": party_id})
        s.commit()


def test_the_object_gate_on_party_creation_is_still_present():
    """CORRECTION-001 moved the refusal to the role gate. The object gate must
    not be deleted as redundant: a create has no object to own, so if the
    contract's roles ever widened again, the contract would be the only thing
    between a customer and an unbounded write primitive.
    """
    import ast
    import pathlib

    source = pathlib.Path("src/turab/api/routes/parties.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    create = next(
        n for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "create_party"
    )
    called = {
        node.func.attr for node in ast.walk(create)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
    }
    assert "authorize_staff_only" in called
