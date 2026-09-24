"""Slice 3, step 5 — the truth layer, on real PostgreSQL.

Ref: `docs/gate/SLICE_3_PLAN.md` §3.1, §3.2, §3.7 (G3-4), §3.8, §3.9, §6.1,
§6.2, §6.3; the mandatory tests of IMPLEMENTATION_SLICES_v0.2.md Slice 3.
Test names follow the plan where it names them.
"""
from __future__ import annotations

import threading
import time
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.db.session import audited_transaction
from turab.services import truth


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


def as_(account):
    return {"Authorization": f"Bearer {account}"}


def key():
    return {"Idempotency-Key": f"s3t-{uuid.uuid4()}"}


def op(ids):
    return {**as_(ids.ACC_OPERATOR), **key()}


def _db(engine, sql, **params):
    with Session(bind=engine, future=True) as s:
        return s.execute(text(sql), params).mappings().all()


def _property(client, ids, ptype="APARTMENT") -> str:
    r = client.post("/properties", headers=op(ids), json={
        "property_type": ptype, "supply_mode": "PUBLIC",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"})
    assert r.status_code == 201, r.text
    return r.json()["property_id"]


def _claim(client, ids, pid, code="ROOMS", value=4, headers=None, **over):
    body = {"subject": {"type": "PROPERTY", "id": pid}, "attribute_code": code,
            "claimed_value": value, "asserted_by_party_id": str(ids.BRAHIM), **over}
    return client.post("/claims", headers=headers or op(ids), json=body)


def _verify(client, ids, claim_id, level, outcome, who=None):
    return client.post(f"/claims/{claim_id}/verification-events",
                       headers={**as_(who or ids.ACC_REVIEWER), **key()},
                       json={"level": level, "outcome": outcome})


def _resolve(client, ids, pid, code="ROOMS", value=4, headers=None, **over):
    body = {"subject": {"type": "PROPERTY", "id": pid}, "attribute_code": code,
            "resolved_value": value, **over}
    return client.post("/resolutions", headers=headers or op(ids), json=body)


def _claim_row(engine, claim_id):
    return _db(engine, """SELECT effective_verification_level::text AS level,
                                 status::text AS status
                            FROM turab.claims WHERE claim_id = :c""", c=claim_id)[0]


def _source(engine) -> str:
    """Sources are created only through an external lead (step 3); inserted
    directly here to exercise the origin rules, not as a creation path."""
    with Session(bind=engine, future=True) as s:
        sid = s.execute(text("INSERT INTO turab.sources (kind) VALUES ('OTHER') "
                             "RETURNING source_id")).scalar_one()
        s.commit()
    return str(sid)


# --- observations -----------------------------------------------------------

def test_an_observation_is_recorded_with_its_origin(client, ids, engine):
    sid = _source(engine)
    r = client.post("/observations", headers=op(ids), json={
        "kind": "CALL_NOTE", "source_id": sid, "party_id": str(ids.BRAHIM),
        "observed_at": "2026-09-01T10:00:00Z", "raw_text": "owner called"})
    assert r.status_code == 201, r.text
    assert set(r.json()) == {"observation_id", "recorded_at"}
    row = _db(engine, """SELECT source_id::text AS s, party_id, raw_text,
                                recorded_by_account_id FROM turab.observations
                          WHERE observation_id = :o""", o=r.json()["observation_id"])[0]
    assert row["s"] == sid and row["party_id"] == ids.BRAHIM
    assert row["recorded_by_account_id"] == ids.ACC_OPERATOR


@pytest.mark.parametrize("override,label", [
    ({"source_id": str(uuid.uuid4())}, "unknown source"),
    ({"party_id": str(uuid.uuid4())}, "unknown party"),
    ({"observed_at": "2026-01-01T00:00:00"}, "no offset"),
    ({"observed_at": (datetime.now(UTC) + timedelta(days=1)).isoformat()}, "future"),
    ({"raw_text": None}, "null raw_text"),
])
def test_a_malformed_observation_is_refused_and_keeps_the_key(client, ids, engine,
                                                              override, label):
    before = _db(engine, "SELECT count(*) AS n FROM turab.observations")[0]["n"]
    k = op(ids)
    r = client.post("/observations", headers=k, json={"kind": "TEXT", **override})
    assert r.status_code == 422, f"{label}: {r.text}"
    assert _db(engine, "SELECT count(*) AS n FROM turab.observations")[0]["n"] == before
    assert client.post("/observations", headers=k,
                       json={"kind": "TEXT"}).status_code == 201, label


def test_an_observation_is_audited_by_the_command_layer(client, ids, engine):
    oid = client.post("/observations", headers=op(ids),
                      json={"kind": "TEXT"}).json()["observation_id"]
    rows = _db(engine, """SELECT action, context FROM turab.audit_log
                           WHERE entity_table = 'observations' AND entity_id = :o""",
               o=oid)
    assert [r["action"] for r in rows] == ["INSERT"]
    assert rows[0]["context"]["operation"] == "postObservations"


# --- §3.1: a claim is born DECLARED; only the database raises it ---------------

def test_a_claim_cannot_be_created_already_verified(client, ids):
    """A CONTRACT-BOUNDARY test, labelled as one (§3.1): `ClaimInput` is
    closed and has no level field, so the field is refused before any
    service code runs."""
    pid = _property(client, ids)
    for field in ("effective_verification_level", "verification_level"):
        r = _claim(client, ids, pid, **{field: "DOCUMENT_SEEN"})
        assert r.status_code == 422, r.text


def test_a_claim_is_born_declared(client, ids, engine):
    pid = _property(client, ids)
    r = _claim(client, ids, pid)
    assert r.status_code == 201, r.text
    assert r.json()["verification_level"] == "DECLARED"
    assert r.json()["status"] == "ACTIVE"
    assert _claim_row(engine, r.json()["claim_id"])["level"] == "DECLARED"


def test_only_a_confirmed_verification_event_raises_the_level(client, ids, engine):
    pid = _property(client, ids)
    cid = _claim(client, ids, pid).json()["claim_id"]
    r = _verify(client, ids, cid, "DOCUMENT_SEEN", "CONFIRMED")
    assert r.status_code == 201, r.text
    assert r.json() == {"verification_event_id": r.json()["verification_event_id"],
                        "level": "DOCUMENT_SEEN", "outcome": "CONFIRMED"}
    assert _claim_row(engine, cid)["level"] == "DOCUMENT_SEEN"


@pytest.mark.parametrize("outcome", ["NOT_CONFIRMED", "INCONCLUSIVE"])
def test_a_non_confirmed_outcome_records_the_event_and_changes_nothing(
    client, ids, engine, outcome
):
    pid = _property(client, ids)
    cid = _claim(client, ids, pid).json()["claim_id"]
    assert _verify(client, ids, cid, "PROFESSIONAL_CHECK", outcome).status_code == 201
    assert _claim_row(engine, cid) == {"level": "DECLARED", "status": "ACTIVE"}
    events = _db(engine, "SELECT outcome FROM turab.verification_events "
                         "WHERE claim_id = :c", c=cid)
    assert [e["outcome"] for e in events] == [outcome]


def test_a_conflict_found_marks_the_claim_conflicting(client, ids, engine):
    pid = _property(client, ids)
    cid = _claim(client, ids, pid).json()["claim_id"]
    assert _verify(client, ids, cid, "DETAILS_MATCHED", "CONFLICT_FOUND").status_code == 201
    assert _claim_row(engine, cid) == {"level": "DECLARED", "status": "CONFLICTING"}


def test_a_lower_confirmation_never_lowers_the_level(client, ids, engine):
    pid = _property(client, ids)
    cid = _claim(client, ids, pid).json()["claim_id"]
    assert _verify(client, ids, cid, "DETAILS_MATCHED", "CONFIRMED").status_code == 201
    assert _verify(client, ids, cid, "DOCUMENT_SEEN", "CONFIRMED").status_code == 201
    assert _claim_row(engine, cid)["level"] == "DETAILS_MATCHED"


def test_verifying_an_unknown_claim_is_404(client, ids):
    assert _verify(client, ids, uuid.uuid4(), "DECLARED", "CONFIRMED").status_code == 404


def test_the_verifier_is_recorded_and_the_event_audited(client, ids, engine):
    pid = _property(client, ids)
    cid = _claim(client, ids, pid).json()["claim_id"]
    vid = _verify(client, ids, cid, "DOCUMENT_SEEN", "CONFIRMED").json()[
        "verification_event_id"]
    row = _db(engine, "SELECT verified_by_account_id FROM turab.verification_events "
                      "WHERE verification_event_id = :v", v=vid)[0]
    assert row["verified_by_account_id"] == ids.ACC_REVIEWER
    assert _db(engine, """SELECT 1 FROM turab.audit_log
                           WHERE entity_table = 'verification_events'
                             AND entity_id = :v""", v=vid)


# --- §3.8: claim provenance ---------------------------------------------------

def test_a_claim_must_carry_at_least_one_origin(client, ids, engine):
    pid = _property(client, ids)
    r = _claim(client, ids, pid, asserted_by_party_id=None)
    assert r.status_code == 422, r.text
    assert "origin" in r.json()["detail"]
    assert not _db(engine, "SELECT 1 FROM turab.claims WHERE property_id = :p "
                           "AND attribute_code = 'ROOMS'", p=pid)


def test_a_party_assertion_alone_is_a_valid_origin(client, ids):
    pid = _property(client, ids)
    assert _claim(client, ids, pid).status_code == 201


@pytest.mark.parametrize("origin", ["source_id", "observation_id"])
def test_a_source_or_an_observation_alone_is_a_valid_origin(client, ids, engine,
                                                            origin):
    pid = _property(client, ids)
    value = (_source(engine) if origin == "source_id" else
             client.post("/observations", headers=op(ids),
                         json={"kind": "TEXT"}).json()["observation_id"])
    assert _claim(client, ids, pid, asserted_by_party_id=None,
                  **{origin: value}).status_code == 201


def test_recorded_by_account_is_not_an_origin(client, ids, engine):
    """The operator who ENTERED it is recorded — and that is not where it
    came from. With no other origin the claim is refused."""
    pid = _property(client, ids)
    r = _claim(client, ids, pid, asserted_by_party_id=None)
    assert r.status_code == 422
    assert "recorded_by_account_id" in r.json()["detail"]


def test_a_source_inconsistent_with_its_observation_is_refused(client, ids, engine):
    pid = _property(client, ids)
    one, other = _source(engine), _source(engine)
    oid = client.post("/observations", headers=op(ids),
                      json={"kind": "TEXT", "source_id": one}).json()["observation_id"]
    r = _claim(client, ids, pid, source_id=other, observation_id=oid)
    assert r.status_code == 422, r.text
    assert _claim(client, ids, pid, source_id=one, observation_id=oid).status_code == 201


@pytest.mark.parametrize("field", ["asserted_by_party_id", "source_id", "observation_id"])
def test_an_unknown_origin_is_a_typed_422(client, ids, field):
    pid = _property(client, ids)
    r = _claim(client, ids, pid, **{field: str(uuid.uuid4())})
    assert r.status_code == 422, r.text


def test_a_claim_about_an_unknown_property_is_404(client, ids):
    assert _claim(client, ids, str(uuid.uuid4())).status_code == 404


@pytest.mark.parametrize("subject_type", ["PARTY", "REQUEST", "OFFER"])
def test_claims_and_resolutions_about_other_subjects_are_refused_naming_g3_11(
    client, ids, engine, subject_type
):
    """No vocabulary is registered for these subjects (G3-11): refused,
    typed, and nothing written — not accepted by accident."""
    subject_id = {"PARTY": ids.AMINA, "REQUEST": ids.REQ_AMINA,
                  "OFFER": ids.OFFER_OWNER_SALE}[subject_type]
    before = _db(engine, "SELECT count(*) AS n FROM turab.claims")[0]["n"]
    body = {"subject": {"type": subject_type, "id": str(subject_id)},
            "attribute_code": "ROOMS", "claimed_value": 3,
            "asserted_by_party_id": str(ids.BRAHIM)}
    r = client.post("/claims", headers=op(ids), json=body)
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "ATTRIBUTE_VOCABULARY_UNDECIDED"
    assert "G3-11" in r.json()["detail"]
    assert _db(engine, "SELECT count(*) AS n FROM turab.claims")[0]["n"] == before
    r = client.post("/resolutions", headers=op(ids), json={
        "subject": body["subject"], "attribute_code": "ROOMS", "resolved_value": 3})
    assert r.status_code == 422 and r.json()["code"] == "ATTRIBUTE_VOCABULARY_UNDECIDED"


def test_a_claim_about_an_alias_is_refused(client, ids, engine):
    canonical, alias = _property(client, ids), _property(client, ids)
    with Session(bind=engine, future=True) as s:
        cand = s.execute(text(
            """INSERT INTO turab.property_identity_candidates
                      (property_a_id, property_b_id, review_status)
               VALUES (:a, :b, 'PENDING_REVIEW') RETURNING identity_candidate_id"""),
            {"a": alias, "b": canonical}).scalar_one()
        s.execute(text(
            """INSERT INTO turab.property_identity_aliases
                      (alias_property_id, canonical_property_id,
                       source_identity_candidate_id, resolved_by_account_id)
               VALUES (:a, :c, :cand, :acct)"""),
            {"a": alias, "c": canonical, "cand": cand, "acct": ids.ACC_OPERATOR})
        s.commit()
    r = _claim(client, ids, alias)
    assert r.status_code == 409 and r.json()["code"] == "IDENTITY_ALIAS_NOT_CANONICAL"


# --- §3.9: controlled options, one validator, three call sites -----------------

def _inactive_definition(engine) -> str:
    code = f"S3T_RETIRED_{uuid.uuid4().hex[:8].upper()}"
    with Session(bind=engine, future=True) as s:
        s.execute(text("""INSERT INTO turab.attribute_definitions
                                 (code, label_ar, value_type, active)
                          VALUES (:c, 'x', 'NUMBER', false)"""), {"c": code})
        s.commit()
    return code


def _call(site, client, ids, engine, pid, code, value, ptype):
    """Invoke one of the three call sites; return True if it was ACCEPTED."""
    if site == "claim":
        return _claim(client, ids, pid, code=code, value=value).status_code == 201
    if site == "resolution":
        return _resolve(client, ids, pid, code=code, value=value).status_code == 201
    with Session(bind=engine, future=True) as s:
        try:
            with s.begin():
                truth.upsert_property_attribute(
                    s, property_id=uuid.UUID(pid), property_type=ptype,
                    attribute_code=code, value=value)
            return True
        except truth.Invalid:
            return False


SITES = ["claim", "resolution", "property_attribute"]


@pytest.mark.parametrize("site", SITES)
def test_an_inactive_attribute_code_is_refused(client, ids, engine, site):
    pid = _property(client, ids)
    assert not _call(site, client, ids, engine, pid, _inactive_definition(engine), 1,
                     "APARTMENT")


@pytest.mark.parametrize("site", SITES)
def test_an_unregistered_enum_option_is_refused(client, ids, engine, site):
    pid = _property(client, ids)
    assert not _call(site, client, ids, engine, pid, "RIGHT_TYPE", "LEASEHOLD",
                     "APARTMENT")
    assert _call(site, client, ids, engine, pid, "RIGHT_TYPE", "PRIVATE_OWNERSHIP",
                 "APARTMENT"), "the registered option must still be accepted"


@pytest.mark.parametrize("site", SITES)
def test_an_attribute_not_applicable_to_this_property_type_is_refused(
    client, ids, engine, site
):
    """BEDROOMS applies to HOUSE_VILLA and APARTMENT, not LAND."""
    land = _property(client, ids, ptype="LAND")
    assert not _call(site, client, ids, engine, land, "BEDROOMS", 2, "LAND")


@pytest.mark.parametrize("site", SITES)
def test_an_unknown_attribute_code_is_refused(client, ids, engine, site):
    pid = _property(client, ids)
    assert not _call(site, client, ids, engine, pid, "NO_SUCH_ATTRIBUTE", 1, "APARTMENT")


@pytest.mark.parametrize("value", [True, "4", None])
def test_a_number_attribute_takes_a_json_number(client, ids, value):
    pid = _property(client, ids)
    assert _claim(client, ids, pid, code="ROOMS", value=value).status_code == 422


# --- §3.2 and §3.7: resolutions ---------------------------------------------------

def test_a_resolution_cannot_cite_a_claim_about_another_subject(client, ids, engine):
    """Service pre-check under a row lock: typed 422, not the lineage
    trigger's exception surfacing as a 500 (§3.2)."""
    pid, other = _property(client, ids), _property(client, ids)
    cid = _claim(client, ids, other).json()["claim_id"]
    r = _resolve(client, ids, pid, source_claim_id=cid)
    assert r.status_code == 422, r.text
    assert "another subject" in r.json()["detail"]
    assert not _db(engine, "SELECT 1 FROM turab.resolved_values WHERE property_id = :p",
                   p=pid)


def test_a_resolution_cannot_cite_a_claim_about_another_attribute(client, ids, engine):
    pid = _property(client, ids)
    cid = _claim(client, ids, pid, code="BEDROOMS", value=2).json()["claim_id"]
    r = _resolve(client, ids, pid, code="ROOMS", source_claim_id=cid)
    assert r.status_code == 422, r.text
    assert "BEDROOMS" in r.json()["detail"]


def test_the_lineage_trigger_still_stands_behind_the_pre_check(session, ids):
    """Belt and braces, asserted on the database itself: the schema refuses
    the same row a caller bypassing the service would write."""
    props = session.execute(text(
        """INSERT INTO turab.properties (property_type, supply_mode, management_mode,
                  claim_status) VALUES ('APARTMENT','PUBLIC','ASSISTED','UNCLAIMED'),
                                       ('APARTMENT','PUBLIC','ASSISTED','UNCLAIMED')
           RETURNING property_id""")).scalars().all()
    cid = session.execute(text(
        """INSERT INTO turab.claims (property_id, attribute_code, claimed_value)
           VALUES (:p, 'ROOMS', '4') RETURNING claim_id"""), {"p": props[1]}).scalar_one()
    with pytest.raises(Exception, match="subject must match"):
        session.execute(text(
            """INSERT INTO turab.resolved_values (property_id, attribute_code,
                      resolved_value, source_claim_id)
               VALUES (:p, 'ROOMS', '4', :c)"""), {"p": props[0], "c": cid})


def test_resolved_by_account_is_recorded(client, ids, engine):
    """§3.7 condition 1."""
    pid = _property(client, ids)
    rid = _resolve(client, ids, pid).json()["resolved_value_id"]
    row = _db(engine, "SELECT resolved_by_account_id FROM turab.resolved_values "
                      "WHERE resolved_value_id = :r", r=rid)[0]
    assert row["resolved_by_account_id"] == ids.ACC_OPERATOR


def test_only_one_resolved_value_is_current_per_attribute(client, ids, engine):
    pid = _property(client, ids)
    for value in (3, 4, 5):
        assert _resolve(client, ids, pid, value=value).status_code == 201
    rows = _db(engine, """SELECT resolved_value, resolution_status::text AS s, valid_to
                            FROM turab.resolved_values
                           WHERE property_id = :p AND attribute_code = 'ROOMS'
                           ORDER BY valid_from""", p=pid)
    assert [r["s"] for r in rows] == ["SUPERSEDED", "SUPERSEDED", "CURRENT"]
    assert [r["resolved_value"] for r in rows] == [3, 4, 5]


def test_superseding_closes_the_previous_row_in_the_same_transaction(client, ids,
                                                                    engine):
    """§3.7 condition 2: history preserved, never overwritten. The previous
    row's `valid_to` equals the new row's `valid_from` — both written in one
    transaction, visible in one audit context."""
    pid = _property(client, ids)
    first = _resolve(client, ids, pid, value=3).json()["resolved_value_id"]
    second = _resolve(client, ids, pid, value=4).json()["resolved_value_id"]
    rows = {r["id"]: r for r in _db(engine, """
        SELECT resolved_value_id::text AS id, valid_from, valid_to,
               resolution_status::text AS s, resolved_value
          FROM turab.resolved_values WHERE property_id = :p""", p=pid)}
    assert rows[first]["s"] == "SUPERSEDED" and rows[first]["resolved_value"] == 3
    assert rows[first]["valid_to"] == rows[second]["valid_from"]
    assert rows[second]["valid_to"] is None
    audits = _db(engine, """SELECT context->>'trace_id' AS t, action FROM turab.audit_log
                             WHERE entity_table = 'resolved_values'
                               AND entity_id IN (:a, :b) ORDER BY audit_id""",
                 a=first, b=second)
    assert [a["action"] for a in audits] == ["INSERT", "UPDATE", "INSERT"]
    assert audits[1]["t"] == audits[2]["t"], "close and insert: one command"


def test_the_source_claim_is_stored(client, ids, engine):
    """§3.7 condition 3, and the projection carries it (§3.9)."""
    pid = _property(client, ids)
    cid = _claim(client, ids, pid).json()["claim_id"]
    rid = _resolve(client, ids, pid, source_claim_id=cid).json()["resolved_value_id"]
    assert _db(engine, "SELECT source_claim_id::text AS c FROM turab.resolved_values "
                       "WHERE resolved_value_id = :r", r=rid)[0]["c"] == cid
    pa = _db(engine, """SELECT pa.value, pa.resolved_claim_id::text AS c
                          FROM turab.property_attributes pa
                          JOIN turab.attribute_definitions d USING (attribute_definition_id)
                         WHERE pa.property_id = :p AND d.code = 'ROOMS'""", p=pid)
    assert pa == [{"value": 4, "c": cid}]


def test_a_background_job_cannot_issue_a_resolution(session, ids):
    """§3.7 condition 4. A background job runs actor-less; the service
    refuses it. (A machine holding a user's token cannot be told apart —
    the schema has no such distinction; stated in the delivery note.)"""
    pid = session.execute(text(
        """INSERT INTO turab.properties (property_type, supply_mode, management_mode,
                  claim_status) VALUES ('APARTMENT','PUBLIC','ASSISTED','UNCLAIMED')
           RETURNING property_id""")).scalar_one()
    with pytest.raises(truth.ActorRequired):
        truth.resolve(session, subject_type="PROPERTY", subject_id=pid,
                      attribute_code="ROOMS", resolved_value=3,
                      resolved_by_account_id=None)
    assert not session.execute(text(
        "SELECT 1 FROM turab.resolved_values WHERE property_id = :p"), {"p": pid}).first()


def test_every_resolution_write_is_audited(client, ids, engine):
    """§3.7 condition 5: `audit_resolved_values` fires on insert and update."""
    pid = _property(client, ids)
    _resolve(client, ids, pid, value=3)
    _resolve(client, ids, pid, value=4)
    actions = _db(engine, """SELECT a.action FROM turab.audit_log a
                              JOIN turab.resolved_values r
                                ON r.resolved_value_id = a.entity_id
                             WHERE a.entity_table = 'resolved_values'
                               AND r.property_id = :p ORDER BY a.audit_id""", p=pid)
    assert sorted(a["action"] for a in actions) == ["INSERT", "INSERT", "UPDATE"]


@pytest.mark.parametrize("override,label", [
    ({"resolution_reason_code": "NO_SUCH"}, "unknown reason"),
    ({"valid_from": "2026-01-01T00:00:00"}, "no offset"),
    ({"valid_from": (datetime.now(UTC) + timedelta(days=1)).isoformat()}, "future"),
    ({"source_claim_id": str(uuid.uuid4())}, "unknown claim"),
])
def test_a_malformed_resolution_is_refused_and_keeps_the_key(client, ids, engine,
                                                             override, label):
    pid = _property(client, ids)
    k = op(ids)
    r = _resolve(client, ids, pid, headers=k, **override)
    assert r.status_code == 422, f"{label}: {r.text}"
    assert not _db(engine, "SELECT 1 FROM turab.resolved_values WHERE property_id = :p",
                   p=pid)
    assert _resolve(client, ids, pid, headers=k).status_code == 201, label


def test_a_backdated_resolution_must_follow_the_current_one(client, ids):
    pid = _property(client, ids)
    assert _resolve(client, ids, pid, value=3).status_code == 201
    r = _resolve(client, ids, pid, value=4, valid_from="2020-01-01T00:00:00Z")
    assert r.status_code == 422, r.text


# --- roles ------------------------------------------------------------------

def test_a_customer_can_reach_none_of_the_four(client, ids):
    pid = _property(client, ids)
    c = as_(ids.ACC_AMINA)
    assert client.post("/observations", headers={**c, **key()},
                       json={"kind": "TEXT"}).status_code == 403
    assert _claim(client, ids, pid, headers={**c, **key()}).status_code == 403
    assert client.post(f"/claims/{uuid.uuid4()}/verification-events",
                       headers={**c, **key()},
                       json={"level": "DECLARED", "outcome": "CONFIRMED"}).status_code == 403
    assert _resolve(client, ids, pid, headers={**c, **key()}).status_code == 403


def test_a_reviewer_verifies_and_resolves_but_does_not_record(client, ids):
    pid = _property(client, ids)
    rev = as_(ids.ACC_REVIEWER)
    assert _claim(client, ids, pid, headers={**rev, **key()}).status_code == 403
    assert client.post("/observations", headers={**rev, **key()},
                       json={"kind": "TEXT"}).status_code == 403
    assert _resolve(client, ids, pid, headers={**rev, **key()}).status_code == 201


# --- §6.3: two concurrent resolutions of one attribute ----------------------------

@pytest.fixture
def two_engines(database_url):
    a = create_engine(database_url, future=True)
    b = create_engine(database_url, future=True)
    yield a, b
    a.dispose()
    b.dispose()


def test_two_concurrent_resolutions_of_one_attribute_yield_one_current_value(
    client, ids, engine, two_engines
):
    """Serialised on the SUBJECT row: both succeed; the second closes the
    first's row; exactly one CURRENT; full history kept (plan §6.3).

    The step-4 lesson applied: the holder's commit does NOT wait for the
    contender to finish. A witness releases the holder when PostgreSQL reports
    the contender blocked BY the holder (`pg_blocking_pids`), or when the
    contender has finished — and the facts say which happened."""
    pid = _property(client, ids)
    engine_a, engine_b = two_engines
    out: dict[str, object] = {}
    pids: dict[str, int] = {}
    locked, finished, release = threading.Event(), threading.Event(), threading.Event()

    def resolve_in(eng, value, account, tag, before_commit=None):
        with Session(bind=eng, future=True) as s:
            with audited_transaction(s, account):
                pids[tag] = s.execute(text("SELECT pg_backend_pid()")).scalar_one()
                row = truth.resolve(s, subject_type="PROPERTY",
                                    subject_id=uuid.UUID(pid), attribute_code="ROOMS",
                                    resolved_value=value, resolved_by_account_id=account)
                if before_commit:
                    before_commit()
        return str(row["resolved_value_id"])

    def holder():
        try:
            out["holder"] = resolve_in(engine_a, 3, ids.ACC_OPERATOR, "holder",
                                       lambda: (locked.set(), release.wait(30)))
        except Exception as exc:
            out["holder"] = f"raised {type(exc).__name__}: {exc}"
        finally:
            locked.set()

    def contender():
        assert locked.wait(30)
        try:
            out["contender"] = resolve_in(engine_b, 4, ids.ACC_REVIEWER, "contender")
        except Exception as exc:
            out["contender"] = f"raised {type(exc).__name__}: {exc}"
        finally:
            finished.set()

    def witness():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and not finished.is_set():
            if "contender" in pids and "holder" in pids:
                with Session(bind=engine, future=True) as s:
                    blockers = s.execute(text("SELECT pg_blocking_pids(:p)"),
                                         {"p": pids["contender"]}).scalar_one()
                if pids["holder"] in blockers:
                    out["waited"] = True
                    break
            time.sleep(0.005)
        out.setdefault("waited", False)
        release.set()

    threads = [threading.Thread(target=f) for f in (holder, contender, witness)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(60)
    assert not any(t.is_alive() for t in threads)

    facts = f"waited={out['waited']} holder={out['holder']} contender={out['contender']}"
    assert out["waited"] is True, f"the subject lock did not serialise them: {facts}"
    assert not str(out["holder"]).startswith("raised"), facts
    assert not str(out["contender"]).startswith("raised"), facts
    rows = _db(engine, """SELECT resolved_value_id::text AS id, resolved_value,
                                 resolution_status::text AS s
                            FROM turab.resolved_values
                           WHERE property_id = :p AND attribute_code = 'ROOMS'""", p=pid)
    by_id = {r["id"]: r for r in rows}
    assert len(rows) == 2, "both are kept: history is never overwritten"
    assert by_id[out["holder"]]["s"] == "SUPERSEDED"
    assert by_id[out["contender"]]["s"] == "CURRENT", "the last committer is current"


def test_the_current_value_uniqueness_is_a_database_index(session):
    """'Exactly one CURRENT at every committed moment' does not rest on the
    lock: the partial unique index holds it for every writer."""
    names = set(session.execute(text(
        """SELECT indexname FROM pg_indexes WHERE schemaname = 'turab'
             AND indexname LIKE 'ux_resolved_current_%'""")).scalars())
    assert names == {"ux_resolved_current_party", "ux_resolved_current_request",
                     "ux_resolved_current_property", "ux_resolved_current_offer"}
