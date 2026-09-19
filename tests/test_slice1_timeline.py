"""GET /parties/{party_id}/timeline — the last Slice 1 contract operation.

Two things make this endpoint worth its own file.

First, the frozen contract types a timeline item as `additionalProperties:
true`. An open schema delegates the field set to the implementation; it does
not authorize returning the row. The tests below pin the allow-list and prove
`interactions.metadata` never leaves the process.

Second, it is a LIST about one OBJECT. A list endpoint audited once (R6.3c)
still owes that object's gate, or the endpoint becomes an existence oracle:
"no interactions" for an id that is not a party, and "no interactions" for a
party with none, are the same answer only if the gate ran first.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, AccessEvent, RecordingAuditSink
from turab.services import timeline


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


BASE = datetime(2026, 3, 1, 9, 0, tzinfo=timezone.utc)


@pytest.fixture
def interactions(engine, ids):
    """Three interactions for Amina, one for Brahim, one orphaned.

    The orphan (`party_id IS NULL`) is the interesting one: the column is
    ON DELETE SET NULL, so an equality predicate must exclude it. A row that
    belongs to nobody must not belong to everybody.
    """
    made: list[uuid.UUID] = []
    rows = [
        (ids.AMINA, "CALL", "PHONE", BASE, "first call"),
        (ids.AMINA, "WHATSAPP", "WHATSAPP", BASE + timedelta(days=1), "followed up"),
        (ids.AMINA, "NOTE", None, BASE + timedelta(days=2), "note"),
        (ids.BRAHIM, "CALL", "PHONE", BASE + timedelta(days=3), "brahim only"),
        (None, "OTHER", None, BASE + timedelta(days=4), "orphaned"),
    ]
    with Session(bind=engine, future=True) as s:
        for party_id, kind, channel, when, summary in rows:
            new_id = uuid.uuid4()
            made.append(new_id)
            s.execute(
                text(
                    """
                    INSERT INTO turab.interactions
                      (interaction_id, interaction_type, channel, party_id,
                       summary, occurred_at, metadata)
                    VALUES (:i, CAST(:t AS turab.interaction_type),
                            CAST(:c AS turab.communication_channel), :p,
                            :s, :o, :m)
                    """
                ),
                {"i": new_id, "t": kind, "c": channel, "p": party_id,
                 "s": summary, "o": when,
                 "m": '{"secret_code": "482913", "raw_body": "private"}'},
            )
        s.commit()
    yield made
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.interactions WHERE interaction_id = ANY(:i)"),
                  {"i": made})
        s.commit()


def staff(ids):
    return {"Authorization": f"Bearer {ids.ACC_OPERATOR}"}


# --- scoping --------------------------------------------------------------

def test_the_timeline_holds_only_that_partys_interactions(client, ids, interactions):
    body = client.get(f"/parties/{ids.AMINA}/timeline", headers=staff(ids)).json()
    summaries = [i["summary"] for i in body["items"]]
    assert summaries == ["note", "followed up", "first call"]  # newest first
    assert "brahim only" not in summaries
    assert "orphaned" not in summaries


def test_an_orphaned_interaction_belongs_to_nobody(client, ids, engine, interactions):
    """party_id is ON DELETE SET NULL; a NULL must match no party's timeline."""
    for party in (ids.AMINA, ids.BRAHIM):
        body = client.get(f"/parties/{party}/timeline", headers=staff(ids)).json()
        assert "orphaned" not in [i["summary"] for i in body["items"]]


def test_a_party_with_no_interactions_gets_an_empty_page(client, ids):
    r = client.get(f"/parties/{ids.BRAHIM}/timeline", headers=staff(ids))
    assert r.status_code == 200
    assert r.json()["items"] == []
    assert r.json()["meta"]["total"] == 0


# --- the object gate ------------------------------------------------------

def test_an_unknown_party_is_refused_not_answered_empty(client, ids, sink):
    """Otherwise the endpoint is an existence oracle for party ids."""
    r = client.get(f"/parties/{uuid.uuid4()}/timeline", headers=staff(ids))
    assert r.status_code == 403
    assert r.json()["code"] == "OBJECT_NOT_AUTHORIZED"
    assert any(r.decision == "DENY"
               and r.operation_id == "getPartiesPartyIdTimeline"
               for r in sink.records)


def test_a_customer_cannot_read_any_timeline(client, ids):
    """x-roles is ADMIN/OPERATOR/REVIEWER. A customer is refused on their OWN
    party too: this is the internal operating record, not a customer history."""
    own = client.get(f"/parties/{ids.AMINA}/timeline",
                     headers={"Authorization": f"Bearer {ids.ACC_AMINA}"})
    assert own.status_code == 403


def test_a_reviewer_may_read_it(client, ids, interactions):
    r = client.get(f"/parties/{ids.AMINA}/timeline",
                   headers={"Authorization": f"Bearer {ids.ACC_REVIEWER}"})
    assert r.status_code == 200


def test_the_timeline_is_not_reachable_unauthenticated(client, ids):
    assert client.get(f"/parties/{ids.AMINA}/timeline").status_code == 401


# --- what may be serialized ----------------------------------------------

def test_interaction_metadata_never_reaches_the_response(client, ids, interactions):
    """Free-form operator JSON: its contents cannot be stated in advance, so
    it cannot be released in advance."""
    raw = client.get(f"/parties/{ids.AMINA}/timeline", headers=staff(ids)).text
    assert "secret_code" not in raw
    assert "482913" not in raw
    assert "raw_body" not in raw
    assert "metadata" not in raw


def test_the_item_field_set_is_exactly_the_allow_list(client, ids, interactions):
    body = client.get(f"/parties/{ids.AMINA}/timeline", headers=staff(ids)).json()
    for item in body["items"]:
        assert set(item) == set(timeline._ENTRY_FIELDS)


def test_a_new_column_does_not_silently_reach_the_response(engine, ids, interactions):
    """The allow-list is built by naming columns, not by copying a row."""
    with Session(bind=engine, future=True) as s:
        page = timeline.read_party_timeline(s, ids.AMINA)
        row = dict(page.items[0])
    row["a_column_added_later"] = "leaked"
    assert "a_column_added_later" not in timeline.entry(row)


# --- pagination -----------------------------------------------------------

def test_pages_partition_the_timeline_without_overlap(client, ids, interactions):
    first = client.get(f"/parties/{ids.AMINA}/timeline?page=1&page_size=2",
                       headers=staff(ids)).json()
    second = client.get(f"/parties/{ids.AMINA}/timeline?page=2&page_size=2",
                        headers=staff(ids)).json()
    assert [i["summary"] for i in first["items"]] == ["note", "followed up"]
    assert [i["summary"] for i in second["items"]] == ["first call"]
    assert first["meta"] == {"page": 1, "page_size": 2, "total": 3, "has_next": True}
    assert second["meta"]["has_next"] is False
    ids_seen = [i["interaction_id"] for i in first["items"] + second["items"]]
    assert len(set(ids_seen)) == 3


def test_the_ordering_is_total_so_pages_cannot_repeat_a_row(engine, ids, interactions):
    """occurred_at alone is not a stable sort key; ties would let a row appear
    on two pages or on none. interaction_id breaks them."""
    same = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    extra = []
    with Session(bind=engine, future=True) as s:
        for n in range(4):
            new_id = uuid.uuid4()
            extra.append(new_id)
            s.execute(
                text(
                    """
                    INSERT INTO turab.interactions
                      (interaction_id, interaction_type, party_id, summary, occurred_at)
                    VALUES (:i, 'NOTE', :p, :s, :o)
                    """
                ),
                {"i": new_id, "p": ids.AMINA, "s": f"tie-{n}", "o": same},
            )
        s.commit()
    try:
        with Session(bind=engine, future=True) as s:
            seen = []
            for page in (1, 2, 3, 4):
                seen += [r["interaction_id"] for r in
                         timeline.read_party_timeline(s, ids.AMINA, page=page,
                                                      page_size=2).items]
        assert len(seen) == len(set(seen)) == 7
    finally:
        with Session(bind=engine, future=True) as s:
            s.execute(text("DELETE FROM turab.interactions WHERE interaction_id = ANY(:i)"),
                      {"i": extra})
            s.commit()


@pytest.mark.parametrize("query", ["page=0", "page=-1", "page_size=0", "page_size=101"])
def test_pagination_outside_the_contracts_bounds_is_rejected(client, ids, query):
    r = client.get(f"/parties/{ids.AMINA}/timeline?{query}", headers=staff(ids))
    assert r.status_code == 422
    assert r.json()["code"] == "VALIDATION_FAILED"


def test_the_page_size_cap_is_the_contracts_maximum(client, ids, interactions):
    """An uncapped page size turns a paginated read into a bulk export of one
    party's entire operational history in a single audited request."""
    assert timeline.MAX_PAGE_SIZE == 100
    r = client.get(f"/parties/{ids.AMINA}/timeline?page_size=100", headers=staff(ids))
    assert r.status_code == 200


# --- audit ----------------------------------------------------------------

def test_the_page_is_audited_once_not_per_row(client, ids, sink, interactions):
    """R6.3c. Three interactions, one audit record."""
    client.get(f"/parties/{ids.AMINA}/timeline", headers=staff(ids))
    accesses = [r for r in sink.records
                if r.operation_id == "getPartiesPartyIdTimeline"]
    assert len(accesses) == 1
    assert accesses[0].event is AccessEvent.LIST
    assert accesses[0].result_count == 3


def test_the_audit_records_the_query_shape_not_the_rows(client, ids, sink, interactions):
    """R6.3b. References, never payloads."""
    client.get(f"/parties/{ids.AMINA}/timeline?page=1&page_size=2", headers=staff(ids))
    record = [r for r in sink.records
              if r.operation_id == "getPartiesPartyIdTimeline"][0]
    rendered = repr(record.as_dict())
    assert "first call" not in rendered
    assert "secret_code" not in rendered
    # The auditor keeps the shape's KEYS, not its values: recording which
    # dimensions were queried is a reference, recording the values is a
    # payload, and R6.3b permits only the first.
    assert record.extra["query_shape"] == ["page", "page_size", "party_id"]
