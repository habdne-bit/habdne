"""Slice 3, step 2 — the commercial OFFER over HTTP, on real PostgreSQL.

Ref: `docs/gate/SLICE_3_PLAN.md` §3.5 (G3-1, ratified), §3.6, §5.1, §6.1,
§6.3; RFC-001 §4.6 (R4.12, R4.13); the effective contract's `OfferCreate`,
`OfferPatch`, `OfferStateCommand`, `PropertyOffer`.

The scenarios named `test_s16*` carry RFC-001's own verdicts (its lines
600-604), not ours.
"""
from __future__ import annotations

import threading
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, AccessEvent, RecordingAuditSink
from turab.db.session import audited_transaction
from turab.services import offers as offer_service
from turab.services.provenance import UpdateChannel

CONTRACT = "docs/handoff/05_API/openapi_v0.2.3.yaml"


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
    """Only idempotency keys are cleared: `prevent_core_delete()` forbids
    hard-deleting offers and properties, so every assertion reads by id."""
    yield
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.idempotency_records"))
        s.commit()


def amina(ids):
    return {"Authorization": f"Bearer {ids.ACC_AMINA}"}


def brahim(ids):
    return {"Authorization": f"Bearer {ids.ACC_BRAHIM}"}


def staff(ids):
    return {"Authorization": f"Bearer {ids.ACC_OPERATOR}"}


def key():
    return {"Idempotency-Key": f"s3o-{uuid.uuid4()}"}


def _property(client, who) -> str:
    r = client.post("/properties", headers={**who, **key()}, json={
        "property_type": "APARTMENT", "supply_mode": "PUBLIC",
        "management_mode": "SELF_MANAGED", "claim_status": "CLAIMED",
    })
    assert r.status_code == 201, r.text
    return r.json()["property_id"]


def _offer(client, who, property_id, party_id, **over) -> dict:
    body = {"party_id": str(party_id), "transaction_type": "SALE", **over}
    r = client.post(f"/properties/{property_id}/offers",
                    headers={**who, **key()}, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _state(client, who, offer_id, status, **extra):
    return client.post(f"/offers/{offer_id}/state", headers={**who, **key()},
                       json={"status": status, **extra})


def _patch(client, who, offer, body, version=None):
    return client.patch(
        f"/offers/{offer['offer_id']}", json=body,
        headers={**who, "If-Match-Version": str(version or offer["version"])},
    )


def _db(engine, sql, **params):
    with Session(bind=engine, future=True) as s:
        return s.execute(text(sql), params).mappings().all()


def _declared_offer_keys() -> set[str]:
    with open(CONTRACT, encoding="utf-8") as fh:
        spec = yaml.safe_load(fh)
    schemas = spec["components"]["schemas"]
    keys = set(schemas["OfferCreate"]["properties"])
    for part in schemas["PropertyOffer"]["allOf"]:
        keys |= set(part.get("properties", {}))
    return keys


# --- creation --------------------------------------------------------------

def test_a_customer_creates_an_offer_on_their_own_property(client, ids):
    pid = _property(client, amina(ids))
    got = _offer(client, amina(ids), pid, ids.AMINA, asking_price_dzd=9_000_000)
    assert got["status"] == "DRAFT"
    assert got["property_id"] == pid
    assert got["party_id"] == str(ids.AMINA)
    assert got["asking_price_dzd"] == 9_000_000
    assert got["version"] == 1


def test_a_new_offer_is_never_confirmed(client, ids):
    """Neither confirmation column is set by creation (plan §3.4): a newly
    entered offer has not been reconfirmed, the same as a new request."""
    got = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    assert got["last_confirmed_at"] is None
    assert got["commercial_terms_last_confirmed_at"] is None


def test_a_customer_cannot_create_an_offer_on_a_property_that_is_not_theirs(
    client, ids
):
    """404, and the same body as for a property that does not exist."""
    staff_pid = _property(client, staff(ids))
    theirs = client.post(f"/properties/{staff_pid}/offers",
                         headers={**amina(ids), **key()},
                         json={"party_id": str(ids.AMINA), "transaction_type": "SALE"})
    missing = client.post(f"/properties/{uuid.uuid4()}/offers",
                          headers={**amina(ids), **key()},
                          json={"party_id": str(ids.AMINA), "transaction_type": "SALE"})
    assert theirs.status_code == missing.status_code == 404
    strip = lambda r: {k: v for k, v in r.json().items() if k != "trace_id"}
    assert strip(theirs) == strip(missing)


def test_a_customer_cannot_create_an_offer_in_another_partys_name(client, ids,
                                                                 engine):
    """Otherwise §4.6 condition 1 would give them creator authority over an
    offer attributed to someone else."""
    pid = _property(client, amina(ids))
    r = client.post(f"/properties/{pid}/offers", headers={**amina(ids), **key()},
                    json={"party_id": str(ids.KHADIJA), "transaction_type": "SALE"})
    assert r.status_code == 403, r.text
    assert not _db(engine, "SELECT 1 FROM turab.property_offers WHERE property_id = :p",
                   p=pid)


def test_a_customer_with_a_claim_creates_an_offer_on_the_claimed_property(client, ids):
    """R4.1: a recorded claim is authority, exactly as creation is."""
    got = _offer(client, amina(ids), ids.CLAIMED_HOUSE, ids.AMINA)
    assert got["property_id"] == str(ids.CLAIMED_HOUSE)


def test_staff_create_an_offer_for_any_party(client, ids):
    pid = _property(client, staff(ids))
    got = _offer(client, staff(ids), pid, ids.KHADIJA, seller_expectation_dzd=5)
    assert got["party_id"] == str(ids.KHADIJA)
    assert got["seller_expectation_dzd"] == 5


def test_owner_sale_broker_sale_and_rent_coexist_on_one_property(client, ids, engine):
    """Mandatory test 1 (plan §6.1). Several offers, by different parties, for
    one physical property at once: PROPERTY is not PROPERTY_OFFER."""
    pid = _property(client, staff(ids))
    owner = _offer(client, staff(ids), pid, ids.BRAHIM, asking_price_dzd=20_000_000)
    broker = _offer(client, staff(ids), pid, ids.AGENCY, asking_price_dzd=22_000_000)
    rent = _offer(client, staff(ids), pid, ids.BRAHIM, transaction_type="RENT",
                  asking_price_dzd=60_000)
    rows = _db(engine, """SELECT offer_id::text AS id, party_id::text AS party,
                                 transaction_type::text AS t
                            FROM turab.property_offers WHERE property_id = :p""", p=pid)
    assert {(r["id"], r["party"], r["t"]) for r in rows} == {
        (owner["offer_id"], str(ids.BRAHIM), "SALE"),
        (broker["offer_id"], str(ids.AGENCY), "SALE"),
        (rent["offer_id"], str(ids.BRAHIM), "RENT"),
    }


def test_a_rent_offer_cannot_carry_a_seller_expectation(client, ids, engine):
    """The schema's unnamed CHECK, named for the caller: typed 422, not 500,
    and nothing written."""
    pid = _property(client, staff(ids))
    r = client.post(f"/properties/{pid}/offers", headers={**staff(ids), **key()},
                    json={"party_id": str(ids.BRAHIM), "transaction_type": "RENT",
                          "seller_expectation_dzd": 1})
    assert r.status_code == 422, r.text
    assert "SALE" in r.json()["detail"]
    assert not _db(engine, "SELECT 1 FROM turab.property_offers WHERE property_id = :p",
                   p=pid)


def test_an_unknown_party_is_a_typed_4xx(client, ids):
    pid = _property(client, staff(ids))
    r = client.post(f"/properties/{pid}/offers", headers={**staff(ids), **key()},
                    json={"party_id": str(uuid.uuid4()), "transaction_type": "SALE"})
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "VALIDATION_FAILED"


def test_an_unknown_property_is_404_for_staff(client, ids):
    r = client.post(f"/properties/{uuid.uuid4()}/offers",
                    headers={**staff(ids), **key()},
                    json={"party_id": str(ids.BRAHIM), "transaction_type": "SALE"})
    assert r.status_code == 404, r.text


@pytest.mark.parametrize("field", [
    "asking_price_dzd", "raw_price_text", "price_negotiable",
    "seller_expectation_dzd", "price_visibility", "permission_scope",
])
def test_create_refuses_an_explicit_null(client, ids, field):
    """Every optional field of `OfferCreate` is omissible and none is nullable."""
    pid = _property(client, staff(ids))
    r = client.post(f"/properties/{pid}/offers", headers={**staff(ids), **key()},
                    json={"party_id": str(ids.BRAHIM), "transaction_type": "SALE",
                          field: None})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("value", [True, "123", 1.5, -1])
def test_a_price_must_be_a_json_integer(client, ids, value):
    """Pydantic's lax `int` accepts `true` and `"123"`; the contract's
    `integer` does not."""
    pid = _property(client, staff(ids))
    r = client.post(f"/properties/{pid}/offers", headers={**staff(ids), **key()},
                    json={"party_id": str(ids.BRAHIM), "transaction_type": "SALE",
                          "asking_price_dzd": value})
    assert r.status_code == 422, r.text


def test_an_integral_number_is_a_json_integer(client, ids):
    """JSON Schema 2020-12 counts 5.0 as an integer; refusing it would narrow
    the contract."""
    got = _offer(client, staff(ids), _property(client, staff(ids)), ids.BRAHIM,
                 asking_price_dzd=5.0)
    assert got["asking_price_dzd"] == 5


def test_zero_and_empty_are_values_not_absence(client, ids):
    got = _offer(client, staff(ids), _property(client, staff(ids)), ids.BRAHIM,
                 asking_price_dzd=0, raw_price_text="")
    assert got["asking_price_dzd"] == 0
    assert got["raw_price_text"] == ""


def test_an_omitted_optional_field_is_absent_from_the_response(client, ids):
    got = _offer(client, staff(ids), _property(client, staff(ids)), ids.BRAHIM)
    for absent in ("asking_price_dzd", "raw_price_text", "seller_expectation_dzd"):
        assert absent not in got
    # NOT NULL with a schema default: always present.
    assert got["price_negotiable"] == "UNKNOWN"
    assert got["price_visibility"] == "PUBLIC"
    assert got["permission_scope"] == "SUMMARY_ONLY"


def test_the_response_carries_no_undeclared_key(client, ids):
    got = _offer(client, staff(ids), _property(client, staff(ids)), ids.BRAHIM,
                 asking_price_dzd=1, raw_price_text="x", seller_expectation_dzd=1)
    extra = set(got) - _declared_offer_keys()
    assert not extra, f"undeclared keys in PropertyOffer: {extra}"


def test_creation_writes_no_party_property_relation(client, ids, engine):
    """G3-6: naming a party on an offer is not a statement about who is
    related to the property."""
    before = _db(engine, "SELECT count(*) AS n FROM turab.party_property_relations")
    _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    after = _db(engine, "SELECT count(*) AS n FROM turab.party_property_relations")
    assert after[0]["n"] == before[0]["n"]


def test_creation_records_its_provenance(client, ids, engine):
    got = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA,
                 asking_price_dzd=7)
    rows = _db(engine, """SELECT attribute_code, asserted_by_party_id, extracted_by
                            FROM turab.claims WHERE offer_id = :o""",
               o=got["offer_id"])
    codes = {r["attribute_code"] for r in rows}
    assert {"party_id", "transaction_type", "asking_price_dzd"} <= codes
    assert "created_by_account_id" not in codes
    # Self-service: attributed to the party who submitted it.
    assert {r["asserted_by_party_id"] for r in rows} == {ids.AMINA}
    assert {r["extracted_by"] for r in rows} == {"SELF_SERVICE"}


# --- the DTO floor (mandatory test 2) --------------------------------------

def test_seller_expectation_never_appears_in_a_public_or_customer_payload(client, ids,
                                                                         engine):
    """Mandatory test 2 (plan §6.1).

    A customer may SEND it — the contract declares it for every role the
    operation admits — and it is stored. It is never rendered back to a
    CUSTOMER, on any of the three commands that return an offer; staff see it.
    """
    pid = _property(client, amina(ids))
    created = _offer(client, amina(ids), pid, ids.AMINA, seller_expectation_dzd=111)
    assert "seller_expectation_dzd" not in created

    patched = _patch(client, amina(ids), created, {"seller_expectation_dzd": 222})
    assert patched.status_code == 200, patched.text
    assert "seller_expectation_dzd" not in patched.json()

    moved = _state(client, amina(ids), created["offer_id"], "ACTIVE")
    assert moved.status_code == 200, moved.text
    assert "seller_expectation_dzd" not in moved.json()

    stored = _db(engine, """SELECT seller_expectation_dzd AS v
                              FROM turab.property_offers WHERE offer_id = :o""",
                 o=created["offer_id"])
    assert stored[0]["v"] == 222, "the value is stored, only never rendered"

    public = client.get("/public/properties")
    assert "seller_expectation_dzd" not in public.text


def test_staff_do_see_the_seller_expectation(client, ids):
    got = _offer(client, staff(ids), _property(client, staff(ids)), ids.BRAHIM,
                 seller_expectation_dzd=333)
    assert got["seller_expectation_dzd"] == 333


# --- patch -----------------------------------------------------------------

def test_a_customer_patches_the_terms_of_their_own_offer(client, ids):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    r = _patch(client, amina(ids), offer,
               {"asking_price_dzd": 10, "price_visibility": "ON_REQUEST"})
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["asking_price_dzd"] == 10
    assert got["price_visibility"] == "ON_REQUEST"
    assert got["version"] == offer["version"] + 1


def test_a_patch_without_a_version_is_refused(client, ids):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    r = client.patch(f"/offers/{offer['offer_id']}", headers=amina(ids),
                     json={"asking_price_dzd": 1})
    assert r.status_code == 428, r.text


def test_a_stale_version_is_refused_and_applies_nothing(client, ids, engine):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA,
                   asking_price_dzd=1)
    assert _patch(client, amina(ids), offer, {"asking_price_dzd": 2}).status_code == 200
    stale = _patch(client, amina(ids), offer, {"asking_price_dzd": 3})
    assert stale.status_code == 409, stale.text
    assert stale.json()["code"] == "STALE_VERSION"
    row = _db(engine, "SELECT asking_price_dzd AS p FROM turab.property_offers "
                      "WHERE offer_id = :o", o=offer["offer_id"])
    assert row[0]["p"] == 2


@pytest.mark.parametrize("field,value", [
    ("status", "ACTIVE"), ("transaction_type", "RENT"),
    ("party_id", "f1000000-0000-4000-8000-000000000004"),
    ("permission_scope", "CONTACT_AFTER_CONFIRMATION"),
])
def test_patch_cannot_change_what_the_contract_does_not_declare(client, ids,
                                                               field, value):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    r = _patch(client, amina(ids), offer, {field: value})
    assert r.status_code == 422, r.text


@pytest.mark.parametrize("field", ["price_negotiable", "price_visibility"])
def test_patch_refuses_null_for_a_non_nullable_field(client, ids, field):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    r = _patch(client, amina(ids), offer, {field: None})
    assert r.status_code == 422, r.text


def test_patch_null_clears_a_nullable_field(client, ids):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA,
                   asking_price_dzd=5)
    r = _patch(client, amina(ids), offer, {"asking_price_dzd": None})
    assert r.status_code == 200, r.text
    assert "asking_price_dzd" not in r.json()


def test_an_empty_patch_is_refused(client, ids):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    assert _patch(client, amina(ids), offer, {}).status_code == 422


def test_a_rent_offer_cannot_be_patched_to_carry_a_seller_expectation(client, ids):
    offer = _offer(client, staff(ids), _property(client, staff(ids)), ids.BRAHIM,
                   transaction_type="RENT")
    r = _patch(client, staff(ids), offer, {"seller_expectation_dzd": 1})
    assert r.status_code == 422, r.text
    assert "SALE" in r.json()["detail"]


def test_a_patch_records_provenance_with_the_previous_value(client, ids, engine):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA,
                   asking_price_dzd=1)
    assert _patch(client, amina(ids), offer, {"asking_price_dzd": 2}).status_code == 200
    rows = _db(engine, """SELECT o.payload FROM turab.claims c
                            JOIN turab.observations o USING (observation_id)
                           WHERE c.offer_id = :o AND c.attribute_code = 'asking_price_dzd'
                           ORDER BY c.recorded_at""", o=offer["offer_id"])
    assert rows[-1]["payload"]["before"] == {"asking_price_dzd": 1}
    assert rows[-1]["payload"]["after"] == {"asking_price_dzd": 2}


# --- RFC-001 §4.6 through the command paths --------------------------------

def test_s16d_an_owner_who_claimed_the_property_commands_their_own_offer(client, ids):
    """Condition 2: parent claim AND party match AND parent CLAIMED. The offer
    is created by STAFF, so the creator branch cannot be what admits her."""
    offer = _offer(client, staff(ids), ids.CLAIMED_HOUSE, ids.AMINA)
    r = _patch(client, amina(ids), offer, {"asking_price_dzd": 1})
    assert r.status_code == 200, r.text


def test_s16e_the_same_owner_cannot_command_anothers_offer_on_that_property(client,
                                                                           ids):
    """R4.13: claiming the property does not open another party's offer on it."""
    offer = _offer(client, staff(ids), ids.CLAIMED_HOUSE, ids.KHADIJA)
    assert _patch(client, amina(ids), offer, {"asking_price_dzd": 1}).status_code == 404
    assert _state(client, amina(ids), offer["offer_id"], "ACTIVE").status_code == 404


def test_s16f_a_creator_commands_their_offer_without_any_claim(client, ids, engine):
    """Condition 1. Brahim holds no claim on this property; he created it and
    then the offer, and creator authority is what admits him."""
    pid = _property(client, brahim(ids))
    assert not _db(engine, "SELECT 1 FROM turab.record_claim_events "
                           "WHERE property_id = :p", p=pid)
    offer = _offer(client, brahim(ids), pid, ids.BRAHIM)
    assert _patch(client, brahim(ids), offer, {"asking_price_dzd": 1}).status_code == 200


def test_s16g_a_party_match_alone_grants_nothing(client, ids):
    """R4.12. Offer in Amina's party's name, on a property she has no claim on,
    created by staff: the party match is one conjunct, never sufficient."""
    offer = _offer(client, staff(ids), _property(client, staff(ids)), ids.AMINA)
    assert _patch(client, amina(ids), offer, {"asking_price_dzd": 1}).status_code == 404
    assert _state(client, amina(ids), offer["offer_id"], "WITHDRAWN").status_code == 404


def test_s16h_a_relation_row_grants_nothing(client, ids):
    """R4.12. Brahim's party holds an `OWNER_DECLARED` relation on the villa
    (a dev-fixture row, inserted directly: no path creates relations, G3-6)
    and the fixture offer is in his party's name. No claim, not the creator:
    refused."""
    r = client.post(f"/offers/{ids.OFFER_OWNER_SALE}/state",
                    headers={**brahim(ids), **key()}, json={"status": "PAUSED"})
    assert r.status_code == 404, r.text


def test_the_customer_path_cannot_be_used_to_enumerate_offers(client, ids):
    """An offer that is not theirs and an offer that does not exist are
    answered identically."""
    theirs = _state(client, amina(ids), ids.OFFER_BROKER_SALE, "PAUSED")
    missing = _state(client, amina(ids), uuid.uuid4(), "PAUSED")
    assert theirs.status_code == missing.status_code == 404
    strip = lambda r: {k: v for k, v in r.json().items() if k != "trace_id"}
    assert strip(theirs) == strip(missing)


def test_a_customer_cannot_link_a_source(client, ids):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    r = client.post(f"/offers/{offer['offer_id']}/sources",
                    headers={**amina(ids), **key()},
                    json={"source_id": str(uuid.uuid4())})
    assert r.status_code == 403, r.text


def test_an_offer_on_a_contested_property_is_a_typed_409_to_a_claimant(client, ids,
                                                                       engine):
    """INV-1 through `postPropertiesPropertyIdOffers`, which shares
    `authorize_property_scope` with PATCH /properties."""
    pid = _property(client, amina(ids))
    with Session(bind=engine, future=True) as s:
        for account in (ids.ACC_AMINA, ids.ACC_KHADIJA):
            s.execute(text("""INSERT INTO turab.record_claim_events
                                     (property_id, claimed_by_account_id)
                              VALUES (:p, :a)"""), {"p": pid, "a": account})
        s.commit()
    r = client.post(f"/properties/{pid}/offers", headers={**amina(ids), **key()},
                    json={"party_id": str(ids.AMINA), "transaction_type": "SALE"})
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "CLAIM_AUTHORITY_CONFLICT"


# --- F-4: the claim branch of §4.6 on a contested or aliased parent ---------
#
# Condition 1 (creator) and condition 2 (parent claim + party match + CLAIMED)
# are independent grants. These tests prove each branch SEPARATELY, so a guard
# that fixed condition 2 by also dropping condition 1 would fail here.
# Claim events and alias rows are inserted directly: no API path creates them
# yet (G3-2; identity review is step 7).

def _claim(engine, property_id, *accounts):
    with Session(bind=engine, future=True) as s:
        for account in accounts:
            s.execute(text("""INSERT INTO turab.record_claim_events
                                     (property_id, claimed_by_account_id)
                              VALUES (:p, :a)"""), {"p": property_id, "a": account})
        s.commit()


def _offer_by(engine, ids, property_id, party_id, created_by) -> dict:
    """An offer whose creator account is chosen by the test."""
    with Session(bind=engine, future=True) as s:
        with audited_transaction(s, ids.ACC_OPERATOR):
            row = offer_service.create_offer(
                s, property_id=uuid.UUID(str(property_id)), party_id=party_id,
                transaction_type="SALE", created_by_account_id=created_by)
    return {"offer_id": str(row["offer_id"]), "version": row["version"]}


def _alias(engine, ids, alias, canonical):
    with Session(bind=engine, future=True) as s:
        candidate = s.execute(
            text("""INSERT INTO turab.property_identity_candidates
                           (property_a_id, property_b_id, review_status)
                    VALUES (:a, :b, 'PENDING_REVIEW')
                 RETURNING identity_candidate_id"""),
            {"a": uuid.UUID(str(alias)), "b": uuid.UUID(str(canonical))},
        ).scalar_one()
        s.execute(
            text("""INSERT INTO turab.property_identity_aliases
                           (alias_property_id, canonical_property_id,
                            source_identity_candidate_id, resolved_by_account_id)
                    VALUES (:alias, :canon, :cand, :acct)"""),
            {"alias": uuid.UUID(str(alias)), "canon": uuid.UUID(str(canonical)),
             "cand": candidate, "acct": ids.ACC_OPERATOR},
        )
        s.commit()


def test_f4_a_claimant_is_admitted_on_an_uncontested_parent(client, ids, engine):
    """The control for the next test: same shape, ONE claimant, so a refusal
    there can only come from the conflict."""
    pid = _property(client, staff(ids))
    _claim(engine, pid, ids.ACC_AMINA)
    offer = _offer_by(engine, ids, pid, ids.AMINA, ids.ACC_OPERATOR)
    assert _patch(client, amina(ids), offer, {"asking_price_dzd": 1}).status_code == 200


def test_f4_a_claimant_who_did_not_create_the_offer_is_refused_on_a_contested_parent(
    client, ids, engine, sink
):
    """INV-1 before condition 2: the parent is claimed by two accounts, so a
    claim on it grants nothing. She IS a claimant, so she is told why (409),
    and the conflict is audited with `disclosed_to_caller` true."""
    pid = _property(client, staff(ids))
    _claim(engine, pid, ids.ACC_AMINA, ids.ACC_KHADIJA)
    offer = _offer_by(engine, ids, pid, ids.AMINA, ids.ACC_OPERATOR)
    r = _patch(client, amina(ids), offer, {"asking_price_dzd": 1})
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "CLAIM_AUTHORITY_CONFLICT"
    assert str(ids.ACC_KHADIJA) not in r.text, "the other claimant stays internal"
    records = [x for x in sink.of(AccessEvent.CLAIM_AUTHORITY_CONFLICT)
               if str(x.resource_id) == str(pid)]
    assert records and records[-1].extra["disclosed_to_caller"] is True


def test_f4_a_party_member_who_is_not_a_claimant_learns_nothing(client, ids, engine,
                                                              sink):
    """Same party as the offer, not a claimant, not the creator: 404, identical
    to an offer that does not exist. The conflict is still audited."""
    pid = _property(client, staff(ids))
    _claim(engine, pid, ids.ACC_AMINA, ids.ACC_KHADIJA)
    offer = _offer_by(engine, ids, pid, ids.AMINA, ids.ACC_OPERATOR)
    second = {"Authorization": f"Bearer {ids.ACC_AMINA_SECOND}"}
    r = _patch(client, second, offer, {"asking_price_dzd": 1})
    assert r.status_code == 404, r.text
    records = [x for x in sink.of(AccessEvent.CLAIM_AUTHORITY_CONFLICT)
               if str(x.resource_id) == str(pid)]
    assert records and records[-1].extra["disclosed_to_caller"] is False


def test_f4_the_creator_keeps_authority_on_a_contested_parent(client, ids, engine):
    """§4.6 condition 1 is independent of any claim. Brahim created the offer
    and holds no claim; the parent's conflict is between two OTHER accounts
    and neither grants nor removes his authority."""
    pid = _property(client, staff(ids))
    _claim(engine, pid, ids.ACC_AMINA, ids.ACC_KHADIJA)
    offer = _offer_by(engine, ids, pid, ids.BRAHIM, ids.ACC_BRAHIM)
    r = _patch(client, brahim(ids), offer, {"asking_price_dzd": 1})
    assert r.status_code == 200, r.text


def test_f4_a_claim_on_the_canonical_admits_an_offer_on_its_alias(client, ids, engine):
    """R4.9 on condition 2: the parent resolves to its canonical, and the
    claim and CLAIMED status are read THERE. The alias itself is ASSISTED /
    UNCLAIMED and carries no claim, so the old per-row EXISTS refused this."""
    canonical = _property(client, staff(ids))
    _claim(engine, canonical, ids.ACC_AMINA)
    r = client.post("/properties", headers={**staff(ids), **key()}, json={
        "property_type": "APARTMENT", "supply_mode": "PUBLIC",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"})
    alias = r.json()["property_id"]
    offer = _offer_by(engine, ids, alias, ids.AMINA, ids.ACC_OPERATOR)
    _alias(engine, ids, alias, canonical)
    assert _patch(client, amina(ids), offer, {"asking_price_dzd": 1}).status_code == 200


def test_f4_a_contested_canonical_blocks_the_claim_branch_through_an_alias(
    client, ids, engine
):
    """INV-1 is evaluated on the CANONICAL parent, not on the alias row."""
    canonical = _property(client, staff(ids))
    _claim(engine, canonical, ids.ACC_AMINA, ids.ACC_KHADIJA)
    r = client.post("/properties", headers={**staff(ids), **key()}, json={
        "property_type": "APARTMENT", "supply_mode": "PUBLIC",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"})
    alias = r.json()["property_id"]
    offer = _offer_by(engine, ids, alias, ids.AMINA, ids.ACC_OPERATOR)
    _alias(engine, ids, alias, canonical)
    r = _patch(client, amina(ids), offer, {"asking_price_dzd": 1})
    assert r.status_code == 409, r.text


# --- F-2: no new offer on an identity alias ---------------------------------

def test_f2_an_offer_is_not_created_on_an_alias(client, ids, engine):
    """409 after authorization, nothing written, and the key not consumed."""
    canonical = _property(client, amina(ids))
    r = client.post("/properties", headers={**staff(ids), **key()}, json={
        "property_type": "APARTMENT", "supply_mode": "PUBLIC",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"})
    alias = r.json()["property_id"]
    _alias(engine, ids, alias, canonical)

    k = {"Idempotency-Key": f"s3o-f2-{uuid.uuid4()}"}
    body = {"party_id": str(ids.AMINA), "transaction_type": "SALE"}
    r = client.post(f"/properties/{alias}/offers", headers={**amina(ids), **k},
                    json=body)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "IDENTITY_ALIAS_NOT_CANONICAL"
    assert not _db(engine, "SELECT 1 FROM turab.property_offers WHERE property_id = :p",
                   p=alias)
    assert not _db(engine, "SELECT 1 FROM turab.idempotency_records "
                           "WHERE idempotency_key = :k", k=k["Idempotency-Key"])


def test_f2_an_unauthorized_caller_is_told_nothing_about_the_alias(client, ids, engine):
    canonical = _property(client, amina(ids))
    alias = _property(client, staff(ids))
    _alias(engine, ids, alias, canonical)
    r = client.post(f"/properties/{alias}/offers", headers={**brahim(ids), **key()},
                    json={"party_id": str(ids.BRAHIM), "transaction_type": "SALE"})
    assert r.status_code == 404, r.text


def test_f2_existing_offers_on_an_alias_are_left_where_they_are(client, ids, engine):
    """ADR-03: identity resolution is non-destructive. The refusal applies to
    NEW writes; an offer made before the alias existed is not moved."""
    canonical = _property(client, staff(ids))
    alias = _property(client, staff(ids))
    offer = _offer(client, staff(ids), alias, ids.BRAHIM)
    _alias(engine, ids, alias, canonical)
    r = client.post(f"/properties/{alias}/offers", headers={**staff(ids), **key()},
                    json={"party_id": str(ids.BRAHIM), "transaction_type": "SALE"})
    assert r.status_code == 409
    rows = _db(engine, "SELECT property_id::text AS p FROM turab.property_offers "
                       "WHERE offer_id = :o", o=offer["offer_id"])
    assert rows[0]["p"] == alias


# --- the state machine (plan §3.5, G3-1) -----------------------------------

#: How to reach each state from DRAFT with staff transitions.
_PATH = {
    "DRAFT": [], "PENDING_INFO": ["PENDING_INFO"], "ACTIVE": ["ACTIVE"],
    "PAUSED": ["ACTIVE", "PAUSED"], "WITHDRAWN": ["WITHDRAWN"], "CLOSED": ["CLOSED"],
}
_ALL = list(_PATH)
_EDGES = [(a, b) for a in _ALL for b in sorted(offer_service.TRANSITIONS[a])]
_NON_EDGES = [(a, b) for a in _ALL for b in _ALL
              if b != a and b not in offer_service.TRANSITIONS[a]]
_CUSTOMER_EDGES = [(a, b) for a, bs in offer_service.CUSTOMER_TARGETS.items()
                   for b in sorted(bs)]
_STAFF_ONLY_EDGES = [(a, b) for (a, b) in _EDGES
                     if b not in offer_service.CUSTOMER_TARGETS.get(a, set())]


def _offer_in(client, ids, state, *, owner="staff"):
    if owner == "staff":
        offer = _offer(client, staff(ids), _property(client, staff(ids)), ids.BRAHIM)
    else:
        offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    for step in _PATH[state]:
        r = _state(client, staff(ids), offer["offer_id"], step)
        assert r.status_code == 200, r.text
    return offer["offer_id"]


def test_the_machine_is_the_ratified_table():
    """Transcribed, not inferred: every edge of plan §3.5 and no other."""
    assert offer_service.TRANSITIONS == {
        "DRAFT": {"PENDING_INFO", "ACTIVE", "WITHDRAWN", "CLOSED"},
        "PENDING_INFO": {"ACTIVE", "WITHDRAWN", "CLOSED"},
        "ACTIVE": {"PENDING_INFO", "PAUSED", "WITHDRAWN", "CLOSED"},
        "PAUSED": {"PENDING_INFO", "ACTIVE", "WITHDRAWN", "CLOSED"},
        "WITHDRAWN": set(), "CLOSED": set(),
    }
    assert offer_service.CUSTOMER_TARGETS == {
        "DRAFT": {"ACTIVE", "WITHDRAWN"}, "PENDING_INFO": {"ACTIVE", "WITHDRAWN"},
        "ACTIVE": {"PAUSED", "WITHDRAWN"}, "PAUSED": {"ACTIVE", "WITHDRAWN"},
    }


@pytest.mark.parametrize("current,target", _EDGES, ids=lambda v: v)
def test_every_ratified_edge_is_allowed_to_staff(client, ids, current, target):
    oid = _offer_in(client, ids, current)
    r = _state(client, staff(ids), oid, target)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == target


@pytest.mark.parametrize("current,target", _NON_EDGES, ids=lambda v: v)
def test_every_other_edge_is_refused_and_changes_nothing(client, ids, engine,
                                                        current, target):
    oid = _offer_in(client, ids, current)
    r = _state(client, staff(ids), oid, target)
    assert r.status_code == 422, r.text
    assert _db(engine, "SELECT status::text AS s FROM turab.property_offers "
                       "WHERE offer_id = :o", o=oid)[0]["s"] == current


def test_the_same_state_is_refused(client, ids):
    oid = _offer_in(client, ids, "ACTIVE")
    r = _state(client, staff(ids), oid, "ACTIVE")
    assert r.status_code == 422
    assert "already ACTIVE" in r.json()["detail"]


@pytest.mark.parametrize("current,target", _CUSTOMER_EDGES, ids=lambda v: v)
def test_every_customer_edge_is_allowed_to_the_holder(client, ids, current, target):
    oid = _offer_in(client, ids, current, owner="amina")
    r = _state(client, amina(ids), oid, target)
    assert r.status_code == 200, r.text


@pytest.mark.parametrize("current,target", _STAFF_ONLY_EDGES, ids=lambda v: v)
def test_every_staff_only_edge_is_refused_to_a_customer(client, ids, engine,
                                                       current, target):
    oid = _offer_in(client, ids, current, owner="amina")
    r = _state(client, amina(ids), oid, target)
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "ACTION_NOT_PERMITTED"
    assert _db(engine, "SELECT status::text AS s FROM turab.property_offers "
                       "WHERE offer_id = :o", o=oid)[0]["s"] == current


def test_a_customer_cannot_close_an_offer(client, ids):
    """And is told what CLOSED means and which state they want instead."""
    oid = _offer_in(client, ids, "ACTIVE", owner="amina")
    r = _state(client, amina(ids), oid, "CLOSED")
    assert r.status_code == 403
    detail = r.json()["detail"]
    assert "operational closure" in detail and "WITHDRAWN" in detail


def test_an_offer_activates_without_a_price(client, ids):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    assert "asking_price_dzd" not in offer
    assert _state(client, amina(ids), offer["offer_id"], "ACTIVE").status_code == 200


def test_a_self_entered_offer_activates_without_a_source(client, ids, engine):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    assert not _db(engine, "SELECT 1 FROM turab.property_offer_sources "
                           "WHERE offer_id = :o", o=offer["offer_id"])
    assert _state(client, amina(ids), offer["offer_id"], "ACTIVE").status_code == 200


def test_a_transition_bumps_the_version(client, ids):
    offer = _offer(client, amina(ids), _property(client, amina(ids)), ids.AMINA)
    r = _state(client, amina(ids), offer["offer_id"], "ACTIVE")
    assert r.json()["version"] == offer["version"] + 1


def test_a_supplied_reason_code_is_readable_back(client, ids, engine):
    """Plan §3.5: "persisted" means retrievable — from the provenance trail AND
    from the audit row of the UPDATE that applied the transition."""
    oid = _offer_in(client, ids, "ACTIVE")
    r = _state(client, staff(ids), oid, "PAUSED", reason_code="OFFER_STALE")
    assert r.status_code == 200, r.text

    with Session(bind=engine, future=True) as s:
        history = offer_service.state_history(s, uuid.UUID(oid))
    assert history[-1] == {"from": "ACTIVE", "to": "PAUSED",
                           "reason_code": "OFFER_STALE"}

    audit = _db(engine, """SELECT context, new_row->>'status' AS status
                             FROM turab.audit_log
                            WHERE entity_table = 'property_offers'
                              AND entity_id = :o AND action = 'UPDATE'
                            ORDER BY audit_id DESC LIMIT 1""", o=oid)
    assert audit[0]["status"] == "PAUSED"
    assert audit[0]["context"]["reason_code"] == "OFFER_STALE"
    # Merged into, not replacing, what the command set.
    assert audit[0]["context"]["operation"] == "postOffersOfferIdState"


def test_an_unknown_reason_code_is_refused_and_changes_nothing(client, ids, engine):
    oid = _offer_in(client, ids, "ACTIVE")
    r = _state(client, staff(ids), oid, "PAUSED", reason_code="NO_SUCH_CODE")
    assert r.status_code == 422, r.text
    assert _db(engine, "SELECT status::text AS s FROM turab.property_offers "
                       "WHERE offer_id = :o", o=oid)[0]["s"] == "ACTIVE"


def test_an_inactive_reason_code_is_refused(client, ids, engine):
    with Session(bind=engine, future=True) as s:
        s.execute(text("""INSERT INTO turab.reason_codes
                                 (code, category, label_ar, active)
                          VALUES ('S3O_RETIRED', 'GENERAL', 'x', false)
                          ON CONFLICT (code) DO NOTHING"""))
        s.commit()
    oid = _offer_in(client, ids, "ACTIVE")
    r = _state(client, staff(ids), oid, "PAUSED", reason_code="S3O_RETIRED")
    assert r.status_code == 422, r.text


def test_a_transition_without_a_reason_records_null(client, ids, engine):
    oid = _offer_in(client, ids, "ACTIVE")
    assert _state(client, staff(ids), oid, "PAUSED").status_code == 200
    with Session(bind=engine, future=True) as s:
        history = offer_service.state_history(s, uuid.UUID(oid))
    assert history[-1]["reason_code"] is None


def test_a_replayed_transition_returns_the_first_result(client, ids):
    oid = _offer_in(client, ids, "ACTIVE")
    k = {"Idempotency-Key": f"s3o-replay-{oid}"}
    first = client.post(f"/offers/{oid}/state", headers={**staff(ids), **k},
                        json={"status": "PAUSED"})
    again = client.post(f"/offers/{oid}/state", headers={**staff(ids), **k},
                        json={"status": "PAUSED"})
    assert first.status_code == again.status_code == 200
    assert first.json() == again.json()


# --- sources (plan §3.6) ---------------------------------------------------
#
# A `sources` row can be created only through an external lead (plan §1.5),
# which is step 3. Until then these tests insert sources directly; that proves
# the LINK behaviour, and is not evidence that a source-creation flow exists.

def _source(engine) -> uuid.UUID:
    with Session(bind=engine, future=True) as s:
        sid = s.execute(text("""INSERT INTO turab.sources (kind)
                                VALUES ('OTHER') RETURNING source_id""")).scalar_one()
        s.commit()
    return sid


def _link(client, ids, oid, sid, primary):
    return client.post(f"/offers/{oid}/sources", headers={**staff(ids), **key()},
                       json={"source_id": str(sid), "is_primary": primary})


def _links(engine, oid):
    return {r["source_id"]: r["is_primary"] for r in _db(
        engine, "SELECT source_id, is_primary FROM turab.property_offer_sources "
                "WHERE offer_id = :o", o=oid)}


def test_linking_a_primary_source_transfers_the_flag(client, ids, engine):
    oid = _offer_in(client, ids, "DRAFT")
    first, second, plain = _source(engine), _source(engine), _source(engine)
    assert _link(client, ids, oid, first, True).status_code == 204
    assert _link(client, ids, oid, plain, False).status_code == 204
    r = _link(client, ids, oid, second, True)
    assert r.status_code == 204, r.text
    assert r.content == b""
    assert _links(engine, oid) == {first: False, plain: False, second: True}, (
        "the flag moves; no link is deleted"
    )


def test_relinking_the_primary_keeps_exactly_one(client, ids, engine):
    oid = _offer_in(client, ids, "DRAFT")
    sid = _source(engine)
    assert _link(client, ids, oid, sid, True).status_code == 204
    assert _link(client, ids, oid, sid, True).status_code == 204
    assert _links(engine, oid) == {sid: True}


def test_linking_an_unknown_source_is_a_typed_4xx(client, ids):
    oid = _offer_in(client, ids, "DRAFT")
    r = _link(client, ids, oid, uuid.uuid4(), True)
    assert r.status_code == 422, r.text


def test_linking_to_an_unknown_offer_is_404(client, ids, engine):
    r = _link(client, ids, uuid.uuid4(), _source(engine), False)
    assert r.status_code == 404, r.text


# --- concurrency (plan §6.3) -----------------------------------------------

@pytest.fixture
def two_engines(database_url):
    a = create_engine(database_url, future=True)
    b = create_engine(database_url, future=True)
    yield a, b
    a.dispose()
    b.dispose()


def _race(engine, holder, contender):
    """Run `holder` then `contender` with the wait BOUND to this race.

    The holder does its write (taking the row lock) and waits; the contender
    starts only then. The holder commits only after the database reports
    `pg_blocking_pids(contender_pid)` containing the holder's pid — the
    database's own statement that THIS contender is blocked by THIS holder,
    not that some backend somewhere is waiting. Every thread is joined before
    any outcome is read, and both outcomes are returned as values.
    """
    import time

    out: dict[str, tuple[str, object]] = {}
    pids: dict[str, int] = {}
    holding = threading.Event()
    witnessed = threading.Event()

    def watch():
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            if "holder" in pids and "contender" in pids:
                with Session(bind=engine, future=True) as s:
                    blockers = s.execute(text("SELECT pg_blocking_pids(:p)"),
                                         {"p": pids["contender"]}).scalar_one()
                if pids["holder"] in blockers:
                    witnessed.set()
                    return
            time.sleep(0.02)

    def run_holder():
        try:
            out["holder"] = ("ok", holder(pids, holding, witnessed))
        except Exception as exc:
            out["holder"] = ("raised", f"{type(exc).__name__}: {exc}")
        finally:
            holding.set()

    def run_contender():
        assert holding.wait(timeout=30)
        try:
            out["contender"] = ("ok", contender(pids))
        except Exception as exc:
            out["contender"] = ("raised", f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=f) for f in (run_holder, run_contender, watch)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    assert not any(t.is_alive() for t in threads), "a worker did not finish"
    assert witnessed.is_set(), "the contention was never observed"
    return out["holder"], out["contender"]


def _committed_active_offer(engine, ids) -> uuid.UUID:
    with Session(bind=engine, future=True) as s:
        with audited_transaction(s, ids.ACC_OPERATOR):
            pid = s.execute(text(
                """INSERT INTO turab.properties (property_type, supply_mode,
                          management_mode, claim_status, created_by_account_id)
                   VALUES ('LAND', 'PUBLIC', 'SELF_MANAGED', 'CLAIMED', :a)
                   RETURNING property_id"""), {"a": ids.ACC_OPERATOR}).scalar_one()
            row = offer_service.create_offer(
                s, property_id=pid, party_id=ids.BRAHIM, transaction_type="SALE",
                created_by_account_id=ids.ACC_OPERATOR)
            offer_service.transition(
                s, offer_id=row["offer_id"], target_status="ACTIVE", customer=False,
                recorded_by_account_id=ids.ACC_OPERATOR,
                channel=UpdateChannel.STAFF_RECORDED)
    return row["offer_id"]


def test_two_concurrent_offer_transitions_from_one_state_do_not_both_apply(
    two_engines, engine, ids
):
    """Plan §6.3: a genuine winner and loser, because the `UPDATE` carries a
    declared compare-and-set (`AND status = :expected`).

    Both start from ACTIVE and choose DIFFERENT targets whose edges exist from
    each other's result (ACTIVE -> PAUSED, and PAUSED -> WITHDRAWN is also an
    edge). That is the case a lock-then-re-read design gets wrong: the
    contender would re-read PAUSED, find WITHDRAWN allowed, and apply a
    transition decided from a state its caller never saw. Here the contender
    decided from ACTIVE, so it must be refused with `OfferStateChanged`.
    """
    oid = _committed_active_offer(engine, ids)
    engine_a, engine_b = two_engines
    with Session(bind=engine, future=True) as s:
        before = len(offer_service.state_history(s, oid))

    def holder(pids, holding, witnessed):
        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                pids["holder"] = s.execute(text("SELECT pg_backend_pid()")).scalar_one()
                offer_service.transition(
                    s, offer_id=oid, target_status="PAUSED", customer=False,
                    recorded_by_account_id=ids.ACC_OPERATOR,
                    channel=UpdateChannel.STAFF_RECORDED)
                holding.set()
                assert witnessed.wait(timeout=30), "contention never observed"
        return "PAUSED"

    def contender(pids):
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, ids.ACC_ADMIN):
                pids["contender"] = s.execute(
                    text("SELECT pg_backend_pid()")).scalar_one()
                offer_service.transition(
                    s, offer_id=oid, target_status="WITHDRAWN", customer=False,
                    recorded_by_account_id=ids.ACC_ADMIN,
                    channel=UpdateChannel.STAFF_RECORDED)
        return "WITHDRAWN"

    first, second = _race(engine, holder, contender)
    assert first == ("ok", "PAUSED"), first
    assert second[0] == "raised" and second[1].startswith("OfferStateChanged"), second

    with Session(bind=engine, future=True) as s:
        status = s.execute(text("SELECT status::text FROM turab.property_offers "
                                "WHERE offer_id = :o"), {"o": oid}).scalar_one()
        history = offer_service.state_history(s, oid)
    assert status == "PAUSED"
    assert len(history) == before + 1, "the loser must leave no trail behind"
    assert history[-1] == {"from": "ACTIVE", "to": "PAUSED", "reason_code": None}


def test_two_concurrent_primary_source_links_leave_exactly_one_primary(
    two_engines, engine, ids
):
    """Plan §3.6: the parent-offer lock SERIALISES the two, so BOTH succeed and
    the last committer's source is primary. No loser is required, because no
    compare-and-set is declared for this operation."""
    oid = _committed_active_offer(engine, ids)
    first, second = _source(engine), _source(engine)
    engine_a, engine_b = two_engines

    def holder(pids, holding, witnessed):
        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                pids["holder"] = s.execute(text("SELECT pg_backend_pid()")).scalar_one()
                offer_service.link_source(s, offer_id=oid, source_id=first,
                                          is_primary=True)
                holding.set()
                assert witnessed.wait(timeout=30), "contention never observed"
        return "first"

    def contender(pids):
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, ids.ACC_ADMIN):
                pids["contender"] = s.execute(
                    text("SELECT pg_backend_pid()")).scalar_one()
                offer_service.link_source(s, offer_id=oid, source_id=second,
                                          is_primary=True)
        return "second"

    a, b = _race(engine, holder, contender)
    assert a == ("ok", "first"), a
    assert b == ("ok", "second"), b
    assert _links(engine, oid) == {first: False, second: True}
