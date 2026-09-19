"""CORRECTION-001 / decision D7 — POST /parties is ADMIN and OPERATOR only.

The acceptance criteria are the approver's, stated in the decision, and each
one is a test below:

  1. creation succeeds for ADMIN and for OPERATOR;
  2. CUSTOMER is refused 403, unauthenticated 401;
  3. a refusal creates no PARTY, no account, and assigns no role;
  4. idempotency and audit guarantees still hold;
  5. POST /requests remains available to CUSTOMER within their own resources.

The last one matters most: narrowing PARTY creation must not quietly narrow
the customer's own path. It is asserted at the policy layer because the
endpoint itself is Slice 2 work.

Also tested here is the correction MECHANISM, because an overlay that can
change what the contract says is only safe while it can only ever say less.
"""
from __future__ import annotations

import pathlib
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.auth.contract import (
    CORRECTIONS_PATH,
    ContractError,
    build_policy_table,
    load_corrections,
    verify_policy_matches_contract,
)
from turab.auth.roles import Role


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
    yield
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.idempotency_records"))
        s.execute(text("DELETE FROM turab.parties WHERE display_name LIKE 'c001-%'"))
        s.commit()


def _counts(engine) -> tuple[int, int, int]:
    with Session(bind=engine, future=True) as s:
        return (
            s.execute(text("SELECT count(*) FROM turab.parties")).scalar_one(),
            s.execute(text("SELECT count(*) FROM turab.user_accounts")).scalar_one(),
            s.execute(text("SELECT count(*) FROM turab.user_account_roles")).scalar_one(),
        )


def body(name: str) -> dict:
    return {"kind": "PERSON", "display_name": name}


# --- 1. the authorized roles succeed --------------------------------------

@pytest.mark.parametrize("who", ["ACC_ADMIN", "ACC_OPERATOR"])
def test_an_authorized_staff_role_creates_a_party(client, ids, engine, who):
    r = client.post(
        "/parties", json=body(f"c001-{who}"),
        headers={"Authorization": f"Bearer {getattr(ids, who)}",
                 "Idempotency-Key": f"c001-ok-{who}"},
    )
    assert r.status_code == 201, r.text
    assert r.json()["display_name"] == f"c001-{who}"
    with Session(bind=engine, future=True) as s:
        assert s.execute(
            text("SELECT count(*) FROM turab.parties WHERE party_id = :p"),
            {"p": uuid.UUID(r.json()["party_id"])},
        ).scalar_one() == 1


# --- 2. the refusals ------------------------------------------------------

def test_a_customer_is_refused_403(client, ids):
    r = client.post("/parties", json=body("c001-cust"),
                    headers={"Authorization": f"Bearer {ids.ACC_AMINA}",
                             "Idempotency-Key": "c001-cust"})
    assert r.status_code == 403
    assert r.json()["code"] == "ROLE_NOT_PERMITTED"


def test_an_unauthenticated_caller_is_refused_401(client):
    r = client.post("/parties", json=body("c001-anon"),
                    headers={"Idempotency-Key": "c001-anon"})
    assert r.status_code == 401


def test_a_reviewer_is_also_refused(client, ids):
    """REVIEWER is not in the corrected set either, and was never in the
    frozen one. The correction removed CUSTOMER; it added nobody."""
    r = client.post("/parties", json=body("c001-rev"),
                    headers={"Authorization": f"Bearer {ids.ACC_REVIEWER}",
                             "Idempotency-Key": "c001-rev"})
    assert r.status_code == 403


# --- 3. a refusal writes nothing -----------------------------------------

@pytest.mark.parametrize("headers", [
    {"Authorization": "CUSTOMER"},   # resolved below
    {},                              # unauthenticated
])
def test_a_refusal_creates_no_party_no_account_and_no_role(
    client, ids, engine, headers
):
    if headers.get("Authorization") == "CUSTOMER":
        headers = {"Authorization": f"Bearer {ids.ACC_AMINA}"}
    before = _counts(engine)
    r = client.post("/parties", json=body("c001-nothing"),
                    headers={**headers, "Idempotency-Key": "c001-nothing"})
    assert r.status_code in (401, 403)
    assert _counts(engine) == before


def test_a_refusal_leaves_no_idempotency_record_to_replay(client, ids, engine):
    """A denied command must not consume its key: the caller has to be able to
    retry with authority, and a claimed-but-never-executed key would answer a
    later legitimate request with a stale conflict."""
    key = "c001-denied-key"
    client.post("/parties", json=body("c001-denied"),
                headers={"Authorization": f"Bearer {ids.ACC_AMINA}",
                         "Idempotency-Key": key})
    with Session(bind=engine, future=True) as s:
        assert s.execute(
            text("SELECT count(*) FROM turab.idempotency_records WHERE idempotency_key = :k"),
            {"k": key},
        ).scalar_one() == 0

    ok = client.post("/parties", json=body("c001-denied"),
                     headers={"Authorization": f"Bearer {ids.ACC_OPERATOR}",
                              "Idempotency-Key": key})
    assert ok.status_code == 201, ok.text


def test_the_refusal_is_audited(client, ids, sink):
    client.post("/parties", json=body("c001-audit"),
                headers={"Authorization": f"Bearer {ids.ACC_AMINA}",
                         "Idempotency-Key": "c001-audit"})
    denials = [r for r in sink.records
               if r.operation_id == "postParties" and r.decision == "DENY"]
    assert denials, "a denied command must leave an audit record (R6.3a)"


# --- 4. idempotency still holds for the callers who ARE authorized --------

def test_idempotency_is_unchanged_for_an_authorized_caller(client, ids, engine):
    headers = {"Authorization": f"Bearer {ids.ACC_OPERATOR}",
               "Idempotency-Key": "c001-replay"}
    first = client.post("/parties", json=body("c001-replay"), headers=headers)
    second = client.post("/parties", json=body("c001-replay"), headers=headers)
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["party_id"] == second.json()["party_id"]
    with Session(bind=engine, future=True) as s:
        assert s.execute(
            text("SELECT count(*) FROM turab.parties WHERE display_name = :d"),
            {"d": "c001-replay"},
        ).scalar_one() == 1


def test_the_key_is_still_required(client, ids):
    r = client.post("/parties", json=body("c001-nokey"),
                    headers={"Authorization": f"Bearer {ids.ACC_OPERATOR}"})
    assert r.status_code != 201
    assert r.json()["code"] == "IDEMPOTENCY_KEY_REQUIRED"


# --- 5. the customer's own path is untouched ------------------------------

def test_the_customer_may_still_create_their_own_request(ids):
    """The decision says so explicitly: restricting PARTY creation to staff
    does not remove the customer's REQUEST path. Asserted at the policy layer
    because the endpoint itself is Slice 2."""
    policy = build_policy_table().get("postRequests")
    assert policy is not None
    assert Role.CUSTOMER in policy.roles


def test_the_correction_touched_exactly_one_operation():
    corrections = load_corrections()
    assert set(corrections) == {"postParties"}


def test_no_other_operation_lost_a_role(ids):
    """A correction file is a blunt instrument; prove it cut once."""
    doc = yaml.safe_load(
        pathlib.Path("docs/handoff/05_API/openapi_v0.2.3.yaml").read_text(encoding="utf-8")
    )
    table = build_policy_table()
    for path, item in doc["paths"].items():
        for method, op in item.items():
            if not isinstance(op, dict) or "operationId" not in op:
                continue
            declared = op.get("x-roles")
            if not declared:
                continue
            policy = table.get(op["operationId"])
            expected = frozenset(Role(r) for r in declared)
            if op["operationId"] == "postParties":
                assert policy.roles == frozenset({Role.ADMIN, Role.OPERATOR})
            else:
                assert policy.roles == expected, op["operationId"]


# --- the mechanism itself -------------------------------------------------

def test_the_policy_table_still_matches_the_contract_as_corrected():
    verify_policy_matches_contract(build_policy_table())


def test_the_frozen_contract_is_not_edited():
    """The whole point: the published package stays byte-for-byte."""
    import hashlib

    frozen = pathlib.Path("docs/handoff/05_API/openapi_v0.2.3.yaml")
    assert hashlib.sha256(frozen.read_bytes()).hexdigest() == (
        "b3b1eb864836d14e275d58e312f960e0e45c7e5b80d2170b54c0e8b39c1f7b72"
    )


def test_a_correction_may_only_narrow(tmp_path):
    """The invariant that keeps this file from being a back door.

    A correction that ADDS a role is a grant of access, and a grant of access
    is a contract change requiring a new official package — never a local
    overlay.
    """
    widening = tmp_path / "widen.yaml"
    widening.write_text(yaml.safe_dump({
        "baseline": "0.2.3",
        "corrections": [{
            "id": "TEST-WIDEN", "decision": "none", "operation_id": "getMeParty",
            "field": "x-roles", "frozen": ["CUSTOMER"],
            "corrected": ["CUSTOMER", "ADMIN"],
        }],
    }))
    with pytest.raises(ContractError) as exc:
        load_corrections(widening)
    assert "only NARROW" in str(exc.value)


def test_a_correction_must_name_a_decision(tmp_path):
    f = tmp_path / "nodecision.yaml"
    f.write_text(yaml.safe_dump({
        "baseline": "0.2.3",
        "corrections": [{
            "id": "TEST-NODEC", "operation_id": "postParties", "field": "x-roles",
            "frozen": ["ADMIN", "OPERATOR", "CUSTOMER"], "corrected": ["ADMIN"],
        }],
    }))
    with pytest.raises(ContractError) as exc:
        load_corrections(f)
    assert "names no decision" in str(exc.value)


def test_a_correction_cannot_empty_an_operation(tmp_path):
    f = tmp_path / "empty.yaml"
    f.write_text(yaml.safe_dump({
        "baseline": "0.2.3",
        "corrections": [{
            "id": "TEST-EMPTY", "decision": "x", "operation_id": "postParties",
            "field": "x-roles", "frozen": ["ADMIN"], "corrected": [],
        }],
    }))
    with pytest.raises(ContractError):
        load_corrections(f)


def test_the_committed_correction_describes_the_contract_as_it_stands():
    """Invariant 2: if the published package changes, a correction written
    against the old text must fail loudly rather than apply to the new."""
    doc = yaml.safe_load(CORRECTIONS_PATH.read_text(encoding="utf-8"))
    contract = yaml.safe_load(
        pathlib.Path("docs/handoff/05_API/openapi_v0.2.3.yaml").read_text(encoding="utf-8")
    )
    by_id = {
        op["operationId"]: op
        for item in contract["paths"].values()
        for op in item.values()
        if isinstance(op, dict) and "operationId" in op
    }
    for entry in doc["corrections"]:
        assert sorted(entry["frozen"]) == sorted(by_id[entry["operation_id"]]["x-roles"])
