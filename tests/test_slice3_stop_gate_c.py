"""STOP GATE C tests that plan §6 names and no earlier step wrote — Slice 3,
step 8, over HTTP on PostgreSQL.

Ref: `docs/gate/SLICE_3_PLAN.md` §6 (the six questions and their named
tests); `docs/gate/SLICE_3_STOP_GATE_C.md` (the evidence, generated).

Two named tests are NOT here, and the evidence document says why:
- `test_listing_a_property_returns_all_of_its_offers`: the frozen contract
  declares no operation that lists a property's offers
  (`/properties/{property_id}/offers` has only POST). Finding G3-16.
- `test_converting_a_lead_records_its_party_and_consent`: conversion is
  refused by decision G3-10. The refusal is what is proven
  (`test_conversion_is_refused_with_a_typed_409_and_changes_nothing`).
"""
from __future__ import annotations

import pathlib
import re
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from turab.auth.audit import AccessAuditor, RecordingAuditSink

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture
def client(engine):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink()))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _h(account):
    return {"Authorization": f"Bearer {account}", "Idempotency-Key": str(uuid.uuid4())}


def _one(engine, sql, **p):
    with engine.begin() as conn:
        return conn.execute(text(sql), p).scalar_one()


def _rows(engine, sql, **p):
    with engine.connect() as conn:
        return [dict(r) for r in conn.execute(text(sql), p).mappings()]


def _location(engine):
    return _one(engine, """INSERT INTO turab.locations (code, canonical_ar, location_type)
                           VALUES (:c, 'موقع اختبار', 'AREA') RETURNING location_id""",
                c=f"TEST-SGC-{uuid.uuid4().hex[:16]}")


# --- "what is the physical property?" ---------------------------------------------

@pytest.mark.parametrize("ptype,supply", [("LAND", "POTENTIAL"), ("APARTMENT", "PUBLIC"),
                                          ("SHOP_COMMERCIAL", "PRIVATE")])
def test_a_property_is_created_with_its_type_location_and_supply_mode(client, ids, engine,
                                                                     ptype, supply):
    """Created through the API; the three facts are stored and read back
    through the staff read, as sent."""
    loc = _location(engine)
    r = client.post("/properties", headers=_h(ids.ACC_OPERATOR), json={
        "property_type": ptype, "supply_mode": supply, "canonical_location_id": str(loc),
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"})
    assert r.status_code == 201, r.text
    pid = r.json()["property_id"]
    assert _rows(engine, """SELECT property_type::text AS t, supply_mode::text AS s,
                                   canonical_location_id AS l
                              FROM turab.properties WHERE property_id = :p""", p=pid) \
        == [{"t": ptype, "s": supply, "l": loc}]
    read = client.get(f"/properties/{pid}", headers={"Authorization": f"Bearer {ids.ACC_OPERATOR}"})
    assert read.status_code == 200, read.text
    body = read.json()
    assert (body["property_type"], body["supply_mode"], body["canonical_location_id"]) \
        == (ptype, supply, str(loc))


def test_property_attributes_are_unique_per_definition(client, ids, engine):
    """One row per (property, attribute definition). Two successive
    resolutions of ROOMS leave ONE projection row, holding the current
    value, while both resolutions stay in history. The UNIQUE constraint
    behind it is a SCHEMA guarantee, shown directly and labelled so."""
    r = client.post("/properties", headers=_h(ids.ACC_OPERATOR), json={
        "property_type": "APARTMENT", "supply_mode": "PUBLIC",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"})
    pid = r.json()["property_id"]
    for rooms in (3, 4):
        res = client.post("/resolutions", headers=_h(ids.ACC_OPERATOR), json={
            "subject": {"type": "PROPERTY", "id": pid}, "attribute_code": "ROOMS",
            "resolved_value": rooms})
        assert res.status_code == 201, res.text
    rows = _rows(engine, """SELECT pa.value FROM turab.property_attributes pa
                              JOIN turab.attribute_definitions d
                                ON d.attribute_definition_id = pa.attribute_definition_id
                             WHERE pa.property_id = :p AND d.code = 'ROOMS'""", p=pid)
    assert rows == [{"value": 4}]
    assert _one(engine, "SELECT count(*) FROM turab.resolved_values "
                        "WHERE property_id = :p AND attribute_code = 'ROOMS'", p=pid) == 2
    with pytest.raises(Exception, match="duplicate key|unique"):
        with engine.begin() as conn:
            conn.execute(text("""
                INSERT INTO turab.property_attributes (property_id, attribute_definition_id, value)
                SELECT :p, attribute_definition_id, '5'::jsonb
                  FROM turab.attribute_definitions WHERE code = 'ROOMS'"""), {"p": pid})


# --- "who supplied each fact?" ------------------------------------------------------

def test_a_source_is_created_only_through_an_external_lead(client, ids, engine):
    """Three facts, together:
    1. in the code, exactly one statement inserts into `turab.sources`, in the
       external-lead service (structural);
    2. capturing a lead through the API creates exactly one source;
    3. linking a source to an offer never creates one: an unknown source id
       is refused and no source row appears."""
    writers = [str(p.relative_to(ROOT)) for p in (ROOT / "src").rglob("*.py")
               if re.search(r"INSERT\s+INTO\s+turab\.sources\b", p.read_text())]
    assert writers == ["src/turab/services/external_leads.py"], writers

    before = _one(engine, "SELECT count(*) FROM turab.sources")
    lead = client.post("/external-leads", headers=_h(ids.ACC_OPERATOR),
                       json={"lead_kind": "PROPERTY", "source": {"kind": "OTHER"}})
    assert lead.status_code == 201, lead.text
    assert _one(engine, "SELECT count(*) FROM turab.sources") == before + 1

    prop = client.post("/properties", headers=_h(ids.ACC_OPERATOR), json={
        "property_type": "LAND", "supply_mode": "PUBLIC",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"}).json()
    offer = client.post(f"/properties/{prop['property_id']}/offers",
                        headers=_h(ids.ACC_OPERATOR),
                        json={"party_id": str(ids.BRAHIM), "transaction_type": "SALE"}).json()
    r = client.post(f"/offers/{offer['offer_id']}/sources", headers=_h(ids.ACC_OPERATOR),
                    json={"source_id": str(uuid.uuid4()), "is_primary": True})
    assert 400 <= r.status_code < 500, r.text
    assert _one(engine, "SELECT count(*) FROM turab.sources") == before + 1
