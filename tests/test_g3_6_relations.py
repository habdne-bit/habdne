"""G3-6 — party–property relations over HTTP, on real PostgreSQL.

Ref: Contract Delta revision 3a (re-confirmed) and its addendum
`docs/contract/addenda/ADD-G3-6_party_property_relations.yaml`; RFC-001 R4.5,
R4.6, R4.12; migrations 0003 and 0004.

Each test names the Delta section it proves. The two authorization scenarios,
S12 and S16h, are re-expressed END-TO-END here (Delta §8): the relation is
created through the API — not inserted by a fixture — and then shown to open
nothing.
"""
from __future__ import annotations

import hashlib
import shutil
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, AccessEvent, RecordingAuditSink

ADDENDUM = "docs/contract/addenda/ADD-G3-6_party_property_relations.yaml"


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
        s.commit()


def as_(account):
    return {"Authorization": f"Bearer {account}"}


def key():
    return {"Idempotency-Key": f"g36-{uuid.uuid4()}"}


def _db(engine, sql, **params):
    with Session(bind=engine, future=True) as s:
        return s.execute(text(sql), params).mappings().all()


def _property(client, ids) -> str:
    r = client.post("/properties", headers={**as_(ids.ACC_OPERATOR), **key()}, json={
        "property_type": "LAND", "supply_mode": "PUBLIC",
        "management_mode": "SELF_MANAGED", "claim_status": "CLAIMED"})
    assert r.status_code == 201, r.text
    return r.json()["property_id"]


def _relate(client, ids, pid, party=None, code="OWNER_DECLARED", **over):
    return client.post(f"/properties/{pid}/relations",
                       headers={**as_(ids.ACC_OPERATOR), **key()},
                       json={"party_id": str(party or ids.AMINA),
                             "relation_code": code, **over})


def _list(client, ids, pid, **params):
    r = client.get(f"/properties/{pid}/relations", headers=as_(ids.ACC_OPERATOR),
                   params=params)
    assert r.status_code == 200, r.text
    return r.json()


def _end(client, ids, pid, rid, headers=None, **body):
    return client.post(f"/properties/{pid}/relations/{rid}/end",
                       headers=headers or {**as_(ids.ACC_OPERATOR), **key()},
                       json=body)


def _declared_keys() -> set[str]:
    with open(ADDENDUM, encoding="utf-8") as fh:
        doc = yaml.safe_load(fh)
    return set(doc["components"]["schemas"]["PartyPropertyRelation"]["properties"])


# --- §3.1 create -----------------------------------------------------------

def test_an_omitted_start_is_the_server_clock_and_current_at_once(client, ids):
    """§5.1: omitted -> now(), so the relation is current immediately."""
    pid = _property(client, ids)
    r = _relate(client, ids, pid)
    assert r.status_code == 201, r.text
    got = r.json()
    assert got["valid_from"] is not None and got["valid_to"] is None
    assert [i["party_property_relation_id"] for i in _list(client, ids, pid)["items"]] \
        == [got["party_property_relation_id"]]


def test_a_relation_is_always_declared(client, ids):
    """§5: no client-asserted level; the input has no such field."""
    pid = _property(client, ids)
    assert _relate(client, ids, pid).json()["verification_level"] == "DECLARED"
    r = _relate(client, ids, pid, party=ids.BRAHIM,
                verification_level="PROFESSIONAL_CHECK")
    assert r.status_code == 422, r.text


def test_valid_to_is_not_accepted_on_create(client, ids):
    r = _relate(client, ids, _property(client, ids),
                valid_to="2030-01-01T00:00:00Z")
    assert r.status_code == 422, r.text


def test_an_explicit_null_start_is_refused(client, ids):
    """§5.1: omissible, never null."""
    r = _relate(client, ids, _property(client, ids), valid_from=None)
    assert r.status_code == 422, r.text


def test_a_start_without_an_offset_is_refused(client, ids):
    r = _relate(client, ids, _property(client, ids), valid_from="2026-01-01T00:00:00")
    assert r.status_code == 422, r.text


def test_a_future_start_is_allowed_and_not_current_until_it_starts(client, ids):
    """Revision 3a's correction to §10: a future `valid_from` creates a
    relation that is NOT current — absent from the default list, present with
    include_ended."""
    pid = _property(client, ids)
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    r = _relate(client, ids, pid, valid_from=future)
    assert r.status_code == 201, r.text
    rid = r.json()["party_property_relation_id"]
    assert _list(client, ids, pid)["items"] == []
    assert [i["party_property_relation_id"]
            for i in _list(client, ids, pid, include_ended="true")["items"]] == [rid]


def test_the_response_carries_no_undeclared_key(client, ids):
    got = _relate(client, ids, _property(client, ids)).json()
    assert set(got) == _declared_keys()


def test_an_unknown_party_is_422_and_consumes_no_key(client, ids, engine):
    pid = _property(client, ids)
    k = key()
    r = client.post(f"/properties/{pid}/relations", headers={**as_(ids.ACC_OPERATOR), **k},
                    json={"party_id": str(uuid.uuid4()), "relation_code": "BROKER"})
    assert r.status_code == 422, r.text
    ok = client.post(f"/properties/{pid}/relations", headers={**as_(ids.ACC_OPERATOR), **k},
                     json={"party_id": str(ids.BRAHIM), "relation_code": "BROKER"})
    assert ok.status_code == 201, f"the refused call consumed its key: {ok.text}"


def test_an_unknown_property_is_404(client, ids):
    assert _relate(client, ids, uuid.uuid4()).status_code == 404


def test_a_relation_is_not_recorded_on_an_identity_alias(client, ids, engine):
    """Decision F-2 applies to this write too."""
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
    r = _relate(client, ids, alias)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDENTITY_ALIAS_NOT_CANONICAL"
    assert not _db(engine, "SELECT 1 FROM turab.party_property_relations "
                           "WHERE property_id = :p", p=alias)


# --- §6 rule 6a ------------------------------------------------------------

def test_a_second_overlapping_relation_is_a_typed_409_naming_the_first(client, ids):
    pid = _property(client, ids)
    first = _relate(client, ids, pid, code="BROKER").json()
    r = _relate(client, ids, pid, code="BROKER")
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "RELATION_OVERLAP"
    assert first["party_property_relation_id"] in r.json()["detail"]


def test_different_codes_and_different_parties_never_conflict(client, ids):
    pid = _property(client, ids)
    assert _relate(client, ids, pid, code="OWNER_DECLARED").status_code == 201
    assert _relate(client, ids, pid, code="CONTACT_PERSON").status_code == 201
    assert _relate(client, ids, pid, party=ids.BRAHIM, code="BROKER").status_code == 201
    assert _relate(client, ids, pid, party=ids.AGENCY, code="BROKER").status_code == 201


def test_after_an_end_the_same_relation_may_be_recorded_again(client, ids):
    pid = _property(client, ids)
    first = _relate(client, ids, pid, code="OCCUPANT").json()
    assert _end(client, ids, pid, first["party_property_relation_id"]).status_code == 200
    assert _relate(client, ids, pid, code="OCCUPANT").status_code == 201


# --- §3.3 end --------------------------------------------------------------

def test_ending_keeps_the_row_and_removes_it_from_the_current_list(client, ids, engine):
    pid = _property(client, ids)
    rid = _relate(client, ids, pid).json()["party_property_relation_id"]
    r = _end(client, ids, pid, rid)
    assert r.status_code == 200, r.text
    assert r.json()["valid_to"] is not None
    assert _list(client, ids, pid)["items"] == []
    assert _list(client, ids, pid, include_ended="true")["total"] == 1
    assert _db(engine, "SELECT 1 FROM turab.party_property_relations "
                       "WHERE party_property_relation_id = :r", r=rid)


def test_ending_twice_is_a_409_not_a_silent_success(client, ids):
    pid = _property(client, ids)
    rid = _relate(client, ids, pid).json()["party_property_relation_id"]
    assert _end(client, ids, pid, rid).status_code == 200
    again = _end(client, ids, pid, rid)
    assert again.status_code == 409, again.text
    assert again.json()["code"] == "RELATION_ALREADY_ENDED"


def test_an_end_before_the_start_is_a_typed_422(client, ids):
    pid = _property(client, ids)
    rid = _relate(client, ids, pid).json()["party_property_relation_id"]
    r = _end(client, ids, pid, rid, valid_to="2000-01-01T00:00:00Z")
    assert r.status_code == 422, r.text


def test_an_end_without_an_offset_is_refused(client, ids):
    pid = _property(client, ids)
    rid = _relate(client, ids, pid).json()["party_property_relation_id"]
    assert _end(client, ids, pid, rid, valid_to="2030-01-01T00:00:00").status_code == 422


def test_an_unknown_reason_code_is_refused_and_a_known_one_accepted(client, ids, engine):
    pid = _property(client, ids)
    rid = _relate(client, ids, pid).json()["party_property_relation_id"]
    assert _end(client, ids, pid, rid, reason_code="NO_SUCH").status_code == 422
    assert _end(client, ids, pid, rid, reason_code="OTHER").status_code == 200
    trail = _db(engine, """SELECT claimed_value FROM turab.claims
                            WHERE property_id = :p
                              AND attribute_code = 'party_property_relation'
                            ORDER BY recorded_at""", p=pid)
    assert trail[-1]["claimed_value"]["event"] == "ENDED"
    assert trail[-1]["claimed_value"]["reason_code"] == "OTHER"


def test_a_relation_of_another_property_is_404(client, ids):
    pid, other = _property(client, ids), _property(client, ids)
    rid = _relate(client, ids, pid).json()["party_property_relation_id"]
    assert _end(client, ids, other, rid).status_code == 404


def test_a_refused_end_consumes_no_key(client, ids):
    pid = _property(client, ids)
    rid = _relate(client, ids, pid).json()["party_property_relation_id"]
    k = {**as_(ids.ACC_OPERATOR), **key()}
    assert _end(client, ids, pid, rid, headers=k, reason_code="NO_SUCH").status_code == 422
    assert _end(client, ids, pid, rid, headers=k).status_code == 200


def test_a_replayed_create_returns_the_first_result(client, ids):
    pid = _property(client, ids)
    k = {**as_(ids.ACC_OPERATOR), **key()}
    body = {"party_id": str(ids.AMINA), "relation_code": "DEVELOPER"}
    first = client.post(f"/properties/{pid}/relations", headers=k, json=body)
    again = client.post(f"/properties/{pid}/relations", headers=k, json=body)
    assert first.status_code == again.status_code == 201
    assert first.json() == again.json()


# --- §7 audit and provenance -----------------------------------------------

def test_create_and_end_are_audited_by_the_command_layer(client, ids, engine):
    """The table has no audit trigger (Delta §7); the command layer writes the
    row, with the actor and the command's context."""
    pid = _property(client, ids)
    rid = _relate(client, ids, pid).json()["party_property_relation_id"]
    assert _end(client, ids, pid, rid).status_code == 200
    rows = _db(engine, """SELECT action, actor_account_id, context, old_row, new_row
                            FROM turab.audit_log
                           WHERE entity_table = 'party_property_relations'
                             AND entity_id = :r ORDER BY audit_id""", r=rid)
    assert [r["action"] for r in rows] == ["INSERT", "UPDATE"]
    assert {r["actor_account_id"] for r in rows} == {ids.ACC_OPERATOR}
    assert rows[0]["context"]["operation"] == "postPropertiesPropertyIdRelations"
    assert rows[1]["context"]["operation"] == "postPropertyRelationEnd"
    assert rows[1]["old_row"]["valid_to"] is None
    assert rows[1]["new_row"]["valid_to"] is not None


def test_create_records_provenance_as_staff_asserting_nothing_for_the_party(client, ids,
                                                                           engine):
    pid = _property(client, ids)
    _relate(client, ids, pid, note="owner phoned")
    rows = _db(engine, """SELECT c.claimed_value, c.asserted_by_party_id,
                                 c.extracted_by, o.raw_text
                            FROM turab.claims c JOIN turab.observations o
                                 USING (observation_id)
                           WHERE c.property_id = :p
                             AND c.attribute_code = 'party_property_relation'""", p=pid)
    assert len(rows) == 1
    assert rows[0]["claimed_value"]["event"] == "CREATED"
    assert rows[0]["asserted_by_party_id"] is None
    assert rows[0]["extracted_by"] == "STAFF_RECORDED"
    assert rows[0]["raw_text"] == "owner phoned"


def test_the_list_is_audited_once(client, ids, sink):
    pid = _property(client, ids)
    _relate(client, ids, pid)
    sink.clear()
    _list(client, ids, pid)
    assert len(sink.of(AccessEvent.LIST)) == 1


# --- §4 roles --------------------------------------------------------------

def test_a_customer_can_reach_none_of_the_three(client, ids):
    pid = _property(client, ids)
    rid = _relate(client, ids, pid).json()["party_property_relation_id"]
    cust = as_(ids.ACC_AMINA)
    assert client.post(f"/properties/{pid}/relations", headers={**cust, **key()},
                       json={"party_id": str(ids.AMINA),
                             "relation_code": "OTHER"}).status_code == 403
    assert client.get(f"/properties/{pid}/relations", headers=cust).status_code == 403
    assert _end(client, ids, pid, rid, headers={**cust, **key()}).status_code == 403


def test_a_reviewer_may_read_but_not_write(client, ids):
    pid = _property(client, ids)
    rev = as_(ids.ACC_REVIEWER)
    assert client.get(f"/properties/{pid}/relations", headers=rev).status_code == 200
    assert client.post(f"/properties/{pid}/relations", headers={**rev, **key()},
                       json={"party_id": str(ids.AMINA),
                             "relation_code": "OTHER"}).status_code == 403


# --- §8: a relation grants nothing — S12 and S16h end-to-end -----------------

def test_s12_end_to_end_a_relation_created_through_the_api_grants_nothing(client, ids):
    """RFC-001 S12 / R4.5, no longer on a fixture row: the strongest code,
    OWNER_DECLARED, recorded through the API for Amina's party, on a property
    she neither created nor claimed."""
    pid = _property(client, ids)
    assert _relate(client, ids, pid, code="OWNER_DECLARED").status_code == 201
    cust = as_(ids.ACC_AMINA)
    assert client.get(f"/me/properties/{pid}", headers=cust).status_code == 404
    assert client.patch(f"/properties/{pid}", json={"local_location_detail": "x"},
                        headers={**cust, "If-Match-Version": "1"}).status_code == 404


def test_s16h_end_to_end_a_relation_opens_no_offer(client, ids):
    """RFC-001 S16h / R4.12: the offer is in her party's name, the relation
    is recorded through the API, and neither is authority."""
    pid = _property(client, ids)
    offer = client.post(f"/properties/{pid}/offers",
                        headers={**as_(ids.ACC_OPERATOR), **key()},
                        json={"party_id": str(ids.AMINA), "transaction_type": "SALE"})
    assert offer.status_code == 201, offer.text
    assert _relate(client, ids, pid, code="OWNER_DECLARED").status_code == 201
    r = client.post(f"/offers/{offer.json()['offer_id']}/state",
                    headers={**as_(ids.ACC_AMINA), **key()}, json={"status": "ACTIVE"})
    assert r.status_code == 404, r.text


# --- §1.1: the consent gate's property branch becomes reachable ---------------

def _bind(engine, ids, pid):
    """A property-scoped binding of Amina's PRIVATE_MATCHING_ONLY grant,
    attempted in a transaction that is always rolled back."""
    with Session(bind=engine, future=True) as s:
        try:
            s.execute(text(
                """INSERT INTO turab.resource_consent_bindings
                          (consent_id, purpose, property_id, bound_by_account_id)
                   VALUES ('f8000000-0000-4000-8000-000000000001',
                           'PRIVATE_MATCHING_ONLY', :p, :a)"""),
                {"p": pid, "a": ids.ACC_OPERATOR})
            return "bound"
        except Exception as exc:          # the trigger's refusal, as a value
            return str(exc.orig) if hasattr(exc, "orig") else str(exc)
        finally:
            s.rollback()


def test_an_api_created_relation_satisfies_the_consent_gate(client, ids, engine):
    """Delta §1.1: the branch was unreachable through the operational surface.
    It is reachable now, through a relation the API created."""
    pid = _property(client, ids)
    assert "no active property relation" in _bind(engine, ids, pid)
    assert _relate(client, ids, pid).status_code == 201
    assert _bind(engine, ids, pid) == "bound"


def test_a_future_relation_does_not_satisfy_the_consent_gate(client, ids, engine):
    """The list and the gate agree about the same row (§3.2, 0003)."""
    pid = _property(client, ids)
    future = (datetime.now(UTC) + timedelta(days=30)).isoformat()
    assert _relate(client, ids, pid, valid_from=future).status_code == 201
    assert "no active property relation" in _bind(engine, ids, pid)


# --- the addendum is bound to the approved text -----------------------------

def _addendum_copy(tmp_path, mutate):
    target = tmp_path / "addenda"
    target.mkdir()
    doc = yaml.safe_load(open(ADDENDUM, encoding="utf-8"))
    mutate(doc)
    (target / "a.yaml").write_text(yaml.safe_dump(doc), encoding="utf-8")
    return target


def test_the_addendum_is_bound_to_the_current_delta_text():
    doc = yaml.safe_load(open(ADDENDUM, encoding="utf-8"))
    meta = doc["addendum"]
    with open(meta["delta_document"], "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == meta["delta_sha256"]


def test_an_addendum_whose_delta_changed_refuses_to_load(tmp_path):
    from turab.auth.contract import ContractError, load_addenda

    directory = _addendum_copy(
        tmp_path, lambda d: d["addendum"].__setitem__("delta_sha256", "0" * 64))
    with pytest.raises(ContractError, match="re-bound"):
        load_addenda(directory)


def test_an_addendum_cannot_redeclare_a_frozen_operation(tmp_path):
    from turab.auth.contract import ContractError, load_addenda

    def collide(d):
        d["paths"]["/properties/{property_id}/relations"]["post"]["operationId"] = \
            "postProperties"
    with pytest.raises(ContractError, match="may only add"):
        load_addenda(_addendum_copy(tmp_path, collide))


def test_an_addendum_operation_must_carry_roles(tmp_path):
    from turab.auth.contract import ContractError, load_addenda

    def strip(d):
        del d["paths"]["/properties/{property_id}/relations"]["get"]["x-roles"]
    with pytest.raises(ContractError, match="x-roles"):
        load_addenda(_addendum_copy(tmp_path, strip))
