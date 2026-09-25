"""The RFC-001 §5.1 scenarios that had no test named for them — Slice 3,
step 8, over HTTP on PostgreSQL.

Ref: `docs/gate/SLICE_3_PLAN.md` §5.1 ("Each is a test, named for its
scenario"); RFC-001 §4 (R4.1–R4.11a) and its scenario matrix (lines 590–606).

The other §5.1 scenarios already have scenario-named tests:
- S10, S12, S13, S14: `test_slice3_properties.py`
- S12, S16h end to end: `test_g3_6_relations.py`
- S16d–S16h: `test_slice3_offers.py`
Each rule is also proven at loader level in `test_authorization_integration.py`.

**Fixture honesty.** PROPERTY claim eligibility is undecided (G3-2), so no
API path creates a property claim. The claim rows here are
`record_claim_events` inserted as fixture: legitimate for proving what a
claim GRANTS, not evidence that a claim flow exists.

**S16i / S16j: G3-15, decided in the review of d0d58c3.** The expected
answer is **401**. The implementation refuses a non-ACTIVATED account at
AUTHENTICATION, as it has since Slice 1: `resolve_subject` admits only
ACTIVATED accounts (R4.11a), and RFC-001's pipeline, stage 1, answers 401 for
an invalid token. RFC-001's scenario table said 404; it is corrected with the
decision. These tests also assert that the 401 does not depend on the
resource, so it reveals nothing about existence.
"""
from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from turab.auth.audit import AccessAuditor, RecordingAuditSink


@pytest.fixture
def client(engine):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink()))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _get(client, account, pid):
    return client.get(f"/me/properties/{pid}", headers={"Authorization": f"Bearer {account}"})


def _one(engine, sql, **p):
    with engine.begin() as conn:
        return conn.execute(text(sql), p).scalar_one()


def _run(engine, sql, **p):
    with engine.begin() as conn:
        conn.execute(text(sql), p)


def _claimed_by_new_account(engine, ids, status="ACTIVATED"):
    """A fresh CUSTOMER account of Amina's party, holding a claim on a fresh
    CLAIMED property that it did not create (the creator is the operator)."""
    account = uuid.uuid4()
    _run(engine, """INSERT INTO turab.user_accounts (account_id, party_id, status)
                    VALUES (:a, :p, CAST(:s AS turab.account_status))""",
         a=account, p=ids.AMINA, s=status)
    _run(engine, "INSERT INTO turab.user_account_roles (account_id, role) "
                 "VALUES (:a, 'CUSTOMER')", a=account)
    pid = _one(engine, """
        INSERT INTO turab.properties (property_type, supply_mode, management_mode,
                                      claim_status, created_by_account_id)
        VALUES ('LAND', 'PRIVATE', 'SELF_MANAGED', 'CLAIMED', :op)
        RETURNING property_id""", op=ids.ACC_OPERATOR)
    _run(engine, """INSERT INTO turab.record_claim_events (property_id, claimed_by_account_id)
                    VALUES (:p, :a)""", p=pid, a=account)
    return account, pid


# --- the scenarios --------------------------------------------------------------

def test_s11_a_property_whose_creator_is_null_is_denied_to_every_customer(client, ids,
                                                                        engine):
    """S11 / R4.3: NULL matches nobody, not everybody."""
    assert _one(engine, "SELECT created_by_account_id IS NULL FROM turab.properties "
                        "WHERE property_id = :p", p=ids.ORPHAN_LAND) is True
    for account in (ids.ACC_AMINA, ids.ACC_KHADIJA, ids.ACC_AMINA_SECOND):
        r = _get(client, account, ids.ORPHAN_LAND)
        assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND", (account, r.text)


def test_s15_the_same_record_after_a_successful_claim_is_allowed(client, ids, engine):
    """S15 / R4.1: the claimant, who is not the creator, reads the property."""
    account, pid = _claimed_by_new_account(engine, ids)
    assert _one(engine, "SELECT created_by_account_id FROM turab.properties "
                        "WHERE property_id = :p", p=pid) != account
    r = _get(client, account, pid)
    assert r.status_code == 200 and r.json()["property_id"] == str(pid), r.text


def test_s16_a_declared_unverified_relation_does_not_block_a_claimant(client, ids, engine):
    """S16 / R4.7: the claimed house carries an OWNER_DECLARED relation that is
    only DECLARED, never verified; the claim grants regardless."""
    assert _one(engine, """SELECT count(*) FROM turab.party_property_relations
                            WHERE property_id = :p AND verification_level = 'DECLARED'
                              AND valid_to IS NULL""", p=ids.CLAIMED_HOUSE) >= 1
    r = _get(client, ids.ACC_AMINA, ids.CLAIMED_HOUSE)
    assert r.status_code == 200, r.text


def test_s16a_an_expired_relation_does_not_revoke_a_claimed_owner(client, ids, engine):
    """S16a / R4.6."""
    assert _one(engine, """SELECT count(*) FROM turab.party_property_relations
                            WHERE property_id = :p AND valid_to < now()""",
                p=ids.CLAIMED_HOUSE) >= 1
    r = _get(client, ids.ACC_AMINA, ids.CLAIMED_HOUSE)
    assert r.status_code == 200, r.text


def test_s16b_a_second_account_of_the_same_party_is_denied(client, ids, engine):
    """S16b / R4.2: authority is account-scoped, not party-scoped."""
    assert _one(engine, "SELECT party_id FROM turab.user_accounts WHERE account_id = :a",
                a=ids.ACC_AMINA_SECOND) == ids.AMINA
    assert _get(client, ids.ACC_AMINA, ids.CLAIMED_HOUSE).status_code == 200
    r = _get(client, ids.ACC_AMINA_SECOND, ids.CLAIMED_HOUSE)
    assert r.status_code == 404 and r.json()["code"] == "NOT_FOUND", r.text


def test_s16i_an_owner_whose_account_is_later_disabled_is_denied(client, ids, engine):
    """S16i / R4.11a: claim authority ends with the account. Denied with 401
    at authentication (G3-15)."""
    account, pid = _claimed_by_new_account(engine, ids)
    assert _get(client, account, pid).status_code == 200
    _run(engine, "UPDATE turab.user_accounts SET status = 'DISABLED' "
                 "WHERE account_id = :a", a=account)
    r = _get(client, account, pid)
    assert r.status_code == 401, r.text
    assert "property_id" not in r.text


@pytest.mark.parametrize("status", ["INVITED", "SUSPENDED"])
def test_s16j_an_invited_or_suspended_account_is_denied(client, ids, engine, status):
    """S16j / R4.11a: a claim held by a non-ACTIVATED account grants nothing.
    The 401 is the same for the claimed property and for a property id that
    does not exist, so it is not an existence oracle."""
    account, pid = _claimed_by_new_account(engine, ids, status=status)
    claimed, missing = _get(client, account, pid), _get(client, account, uuid.uuid4())
    assert claimed.status_code == missing.status_code == 401, (claimed.text, missing.text)
    strip = lambda body: {k: v for k, v in body.items() if k != "trace_id"}  # noqa: E731
    assert strip(claimed.json()) == strip(missing.json())
