"""Slice 3, step 3 — SOURCE: external leads, on real PostgreSQL.

Ref: plan §1.5; the effective contract's `ExternalLeadCreate` and the three
operations; API_CONTRACTS_v0.2 §4.3; `docs/gate/G3-10_external_lead_conversion.md`.

Step 2 had to insert `sources` rows directly to test offer-source links,
because no source could yet be created through the API. The first test below
closes that gap end-to-end.
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
def clean(engine):
    yield
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.idempotency_records"))
        s.commit()


def as_(account):
    return {"Authorization": f"Bearer {account}"}


def key():
    return {"Idempotency-Key": f"s3s-{uuid.uuid4()}"}


def _db(engine, sql, **params):
    with Session(bind=engine, future=True) as s:
        return s.execute(text(sql), params).mappings().all()


def _lead_body(**source_over):
    return {"lead_kind": "PROPERTY",
            "source": {"kind": "FACEBOOK_POST",
                       "external_url": "https://example.invalid/post/1",
                       "raw_text": "villa for sale", "title": "post",
                       "captured_at": "2026-09-01T10:00:00Z",
                       "metadata": {"group": "adrar"}, **source_over},
            "raw_payload": {"price": "2 million"}}


def _capture(client, ids, **source_over):
    r = client.post("/external-leads", headers={**as_(ids.ACC_OPERATOR), **key()},
                    json=_lead_body(**source_over))
    assert r.status_code == 201, r.text
    return r.json()


# --- capture ---------------------------------------------------------------

def test_a_captured_source_can_be_linked_to_an_offer_end_to_end(client, ids, engine):
    """The gap step 2 recorded: a source created through the API, then linked
    as an offer's primary source through the API."""
    lead = _capture(client, ids)
    prop = client.post("/properties", headers={**as_(ids.ACC_OPERATOR), **key()}, json={
        "property_type": "LAND", "supply_mode": "PUBLIC",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"}).json()
    offer = client.post(f"/properties/{prop['property_id']}/offers",
                        headers={**as_(ids.ACC_OPERATOR), **key()},
                        json={"party_id": str(ids.BRAHIM),
                              "transaction_type": "SALE"}).json()
    r = client.post(f"/offers/{offer['offer_id']}/sources",
                    headers={**as_(ids.ACC_OPERATOR), **key()},
                    json={"source_id": lead["source_id"], "is_primary": True})
    assert r.status_code == 204, r.text
    rows = _db(engine, "SELECT is_primary FROM turab.property_offer_sources "
                       "WHERE offer_id = :o AND source_id = :s",
               o=offer["offer_id"], s=lead["source_id"])
    assert [r["is_primary"] for r in rows] == [True]


def test_capture_writes_a_discovery_record_and_nothing_else(client, ids, engine):
    """§4.3: "not an active REQUEST or PROPERTY". No party, no resource."""
    counts = ("SELECT (SELECT count(*) FROM turab.requests) AS r, "
              "(SELECT count(*) FROM turab.properties) AS p, "
              "(SELECT count(*) FROM turab.party_property_relations) AS rel")
    before = _db(engine, counts)[0]
    lead = _capture(client, ids)
    assert lead["status"] == "DISCOVERED"
    assert _db(engine, counts)[0] == before
    row = _db(engine, """SELECT l.lead_kind::text AS kind, l.party_id,
                                l.raw_payload, l.created_by_account_id,
                                s.kind::text AS source_kind, s.external_url,
                                s.raw_text, s.metadata
                           FROM turab.external_leads l
                           JOIN turab.sources s USING (source_id)
                          WHERE l.external_lead_id = :l""",
              l=lead["external_lead_id"])[0]
    assert row["kind"] == "PROPERTY" and row["party_id"] is None
    assert row["created_by_account_id"] == ids.ACC_OPERATOR
    assert row["source_kind"] == "FACEBOOK_POST"
    assert row["external_url"] == "https://example.invalid/post/1"
    assert row["raw_payload"] == {"price": "2 million"}
    assert row["metadata"] == {"group": "adrar"}


def test_the_url_is_stored_verbatim(client, ids, engine):
    """No normalising URL type: the record is what the source showed."""
    lead = _capture(client, ids, external_url="HTTPS://Example.invalid")
    got = _db(engine, "SELECT external_url FROM turab.sources WHERE source_id = :s",
              s=lead["source_id"])
    assert got[0]["external_url"] == "HTTPS://Example.invalid"


def test_the_response_is_the_declared_three_fields(client, ids):
    assert set(_capture(client, ids)) == {"external_lead_id", "status", "source_id"}


@pytest.mark.parametrize("override,label", [
    ({"external_url": "not a uri"}, "relative url"),
    ({"captured_at": "2026-09-01T10:00:00"}, "no offset"),
    ({"kind": "TELEGRAM"}, "unknown kind"),
    ({"surprise": 1}, "unknown key"),
    ({"title": None}, "null for a non-nullable field"),
])
def test_a_malformed_source_is_refused_writes_nothing_and_keeps_the_key(
    client, ids, engine, override, label
):
    before = _db(engine, "SELECT count(*) AS n FROM turab.sources")[0]["n"]
    k = {**as_(ids.ACC_OPERATOR), **key()}
    r = client.post("/external-leads", headers=k, json=_lead_body(**override))
    assert r.status_code == 422, f"{label}: {r.text}"
    assert _db(engine, "SELECT count(*) AS n FROM turab.sources")[0]["n"] == before
    ok = client.post("/external-leads", headers=k, json=_lead_body())
    assert ok.status_code == 201, f"{label}: the refused call consumed its key"


def test_capture_is_audited_by_the_command_layer(client, ids, engine):
    """Neither table has an audit trigger in the frozen schema."""
    lead = _capture(client, ids)
    rows = _db(engine, """SELECT entity_table, action, actor_account_id, context
                            FROM turab.audit_log
                           WHERE entity_id IN (:l, :s) ORDER BY audit_id""",
               l=lead["external_lead_id"], s=lead["source_id"])
    assert [(r["entity_table"], r["action"]) for r in rows] == [
        ("sources", "INSERT"), ("external_leads", "INSERT")]
    assert {r["actor_account_id"] for r in rows} == {ids.ACC_OPERATOR}
    assert {r["context"]["operation"] for r in rows} == {"postExternalLeads"}


def test_a_replayed_capture_returns_the_first_lead(client, ids, engine):
    k = {**as_(ids.ACC_OPERATOR), **key()}
    first = client.post("/external-leads", headers=k, json=_lead_body())
    again = client.post("/external-leads", headers=k, json=_lead_body())
    assert first.json() == again.json()
    assert len(_db(engine, "SELECT 1 FROM turab.external_leads "
                           "WHERE external_lead_id = :l",
                   l=first.json()["external_lead_id"])) == 1


def test_a_customer_cannot_capture(client, ids):
    r = client.post("/external-leads", headers={**as_(ids.ACC_AMINA), **key()},
                    json=_lead_body())
    assert r.status_code == 403, r.text


# --- convert: refused, typed, naming what is undecided -------------------------

def _convert(client, ids, lead_id, who=None, headers=None):
    return client.post(
        f"/external-leads/{lead_id}/convert",
        headers=headers or {**as_(who or ids.ACC_OPERATOR), **key()},
        json={"party_id": str(ids.AMINA),
              "consent_id": "f8000000-0000-4000-8000-000000000001",
              "target": "PROPERTY", "payload": {"property_type": "LAND"}})


def test_conversion_is_refused_with_a_typed_409_and_changes_nothing(client, ids, engine):
    lead = _capture(client, ids)
    counts = ("SELECT (SELECT count(*) FROM turab.requests) AS r, "
              "(SELECT count(*) FROM turab.properties) AS p")
    before = _db(engine, counts)[0]
    k = {**as_(ids.ACC_OPERATOR), **key()}
    r = _convert(client, ids, lead["external_lead_id"], headers=k)
    assert r.status_code == 409, r.text
    assert r.json()["code"] == "EXTERNAL_LEAD_CONVERSION_UNDECIDED"
    assert "G3-10" in r.json()["detail"]
    assert _db(engine, counts)[0] == before
    status = _db(engine, "SELECT status::text AS s FROM turab.external_leads "
                         "WHERE external_lead_id = :l", l=lead["external_lead_id"])
    assert status[0]["s"] == "DISCOVERED"
    assert not _db(engine, "SELECT 1 FROM turab.idempotency_records "
                           "WHERE idempotency_key = :k", k=k["Idempotency-Key"])


def test_converting_an_unknown_lead_is_404(client, ids):
    assert _convert(client, ids, uuid.uuid4()).status_code == 404


def test_a_customer_cannot_convert(client, ids):
    lead = _capture(client, ids)
    assert _convert(client, ids, lead["external_lead_id"],
                    who=ids.ACC_AMINA).status_code == 403


# --- the queue -------------------------------------------------------------

def test_the_queue_lists_open_leads_oldest_first_and_omits_closed_ones(client, ids,
                                                                      engine):
    first, second, closed = _capture(client, ids), _capture(client, ids), \
        _capture(client, ids)
    with Session(bind=engine, future=True) as s:
        s.execute(text("""UPDATE turab.external_leads SET status = 'DECLINED'
                           WHERE external_lead_id = :l"""),
                  {"l": closed["external_lead_id"]})
        s.commit()
    r = client.get("/backoffice/queues/external-leads", headers=as_(ids.ACC_OPERATOR))
    assert r.status_code == 200, r.text
    listed = [i["id"] for i in r.json()["items"]]
    assert closed["external_lead_id"] not in listed
    assert listed.index(first["external_lead_id"]) < listed.index(
        second["external_lead_id"])
    item = next(i for i in r.json()["items"] if i["id"] == first["external_lead_id"])
    assert item == {"id": first["external_lead_id"], "kind": "EXTERNAL_LEAD_PROPERTY",
                    "priority": "NORMAL", "created_at": item["created_at"],
                    "reason": "DISCOVERED"}
    assert r.json()["next_cursor"] is None


def test_the_queue_order_is_deterministic(client, ids):
    _capture(client, ids)
    a = client.get("/backoffice/queues/external-leads", headers=as_(ids.ACC_OPERATOR))
    b = client.get("/backoffice/queues/external-leads", headers=as_(ids.ACC_OPERATOR))
    assert a.json() == b.json()


def test_the_queue_carries_no_floor_field(client, ids):
    """Staff audience, but the queue item is a summary: no raw text, URL,
    metadata or source id is needed to decide what to do next."""
    _capture(client, ids)
    r = client.get("/backoffice/queues/external-leads", headers=as_(ids.ACC_OPERATOR))
    for item in r.json()["items"]:
        assert set(item) == {"id", "kind", "priority", "created_at", "reason"}


def test_the_queue_is_audited_once_and_refused_to_customers(client, ids, sink):
    sink.clear()
    assert client.get("/backoffice/queues/external-leads",
                      headers=as_(ids.ACC_REVIEWER)).status_code == 200
    assert len(sink.of(AccessEvent.LIST)) == 1
    assert client.get("/backoffice/queues/external-leads",
                      headers=as_(ids.ACC_AMINA)).status_code == 403
