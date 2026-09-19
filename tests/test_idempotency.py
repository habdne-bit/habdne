"""Idempotency — API_CONTRACTS §2.3, ADR-09, Slice 0 mandatory tests."""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

from turab.services.idempotency import (
    IdempotencyKeyConflict,
    IdempotencyKeyRequired,
    IdempotencyOutcome,
    begin,
    canonical_request_hash,
    complete,
)

ROUTE = "POST /requests"


def _begin(session, ids, key="key-1", payload=None, actor=None):
    return begin(
        session,
        actor_account_id=actor or ids.ACC_AMINA,
        route_key=ROUTE,
        idempotency_key=key,
        payload=payload if payload is not None else {"a": 1},
    )


def test_first_call_is_new(session, ids):
    outcome, replay = _begin(session, ids)
    assert outcome is IdempotencyOutcome.NEW and replay is None


def test_same_key_same_payload_replays_the_result(session, ids):
    """Slice 0 mandatory test 1."""
    _begin(session, ids)
    complete(session, actor_account_id=ids.ACC_AMINA, route_key=ROUTE,
             idempotency_key="key-1", status=201, body={"request_id": "abc"},
             resource_ref="/requests/abc")
    outcome, replay = _begin(session, ids)
    assert outcome is IdempotencyOutcome.REPLAYED
    assert replay.status == 201
    assert replay.body == {"request_id": "abc"}
    assert replay.resource_ref == "/requests/abc"


def test_same_key_different_payload_is_a_conflict(session, ids):
    """Slice 0 mandatory test 2."""
    _begin(session, ids, payload={"a": 1})
    complete(session, actor_account_id=ids.ACC_AMINA, route_key=ROUTE,
             idempotency_key="key-1", status=201, body={})
    with pytest.raises(IdempotencyKeyConflict):
        _begin(session, ids, payload={"a": 2})


def test_key_order_does_not_change_the_hash(session, ids):
    """An identical request must not look different because of key order."""
    assert canonical_request_hash({"a": 1, "b": 2}) == canonical_request_hash({"b": 2, "a": 1})
    _begin(session, ids, payload={"a": 1, "b": 2})
    complete(session, actor_account_id=ids.ACC_AMINA, route_key=ROUTE,
             idempotency_key="key-1", status=201, body={})
    outcome, _ = _begin(session, ids, payload={"b": 2, "a": 1})
    assert outcome is IdempotencyOutcome.REPLAYED


def test_the_same_key_is_independent_per_actor(session, ids):
    """UNIQUE(actor, route, key): a client-chosen key cannot collide across
    accounts, which is what makes client-chosen keys safe."""
    _begin(session, ids, actor=ids.ACC_AMINA)
    outcome, _ = _begin(session, ids, actor=ids.ACC_KHADIJA)
    assert outcome is IdempotencyOutcome.NEW


def test_the_same_key_is_independent_per_route(session, ids):
    _begin(session, ids)
    outcome, _ = begin(session, actor_account_id=ids.ACC_AMINA,
                       route_key="POST /properties", idempotency_key="key-1",
                       payload={"a": 1})
    assert outcome is IdempotencyOutcome.NEW


def test_a_claimed_but_incomplete_key_is_a_conflict(session, ids):
    """An earlier attempt died before storing a result.

    Replaying would return a result that never existed; re-running could
    duplicate a side effect. Neither is acceptable silently, so the client is
    told to use a new key.
    """
    _begin(session, ids)
    with pytest.raises(IdempotencyKeyConflict):
        _begin(session, ids)


def test_an_expired_record_is_replaced_not_replayed(session, ids):
    _begin(session, ids)
    complete(session, actor_account_id=ids.ACC_AMINA, route_key=ROUTE,
             idempotency_key="key-1", status=201, body={"old": True})
    session.execute(
        text("UPDATE turab.idempotency_records SET expires_at = :t WHERE idempotency_key = 'key-1'"),
        {"t": datetime.now(UTC) - timedelta(seconds=1)},
    )
    outcome, replay = _begin(session, ids)
    assert outcome is IdempotencyOutcome.NEW and replay is None


@pytest.mark.parametrize("key", [None, "", "   "])
def test_a_missing_key_is_rejected(session, ids, key):
    with pytest.raises(IdempotencyKeyRequired):
        _begin(session, ids, key=key)


def test_an_overlong_key_is_rejected(session, ids):
    """The frozen contract caps Idempotency-Key at 128 characters."""
    with pytest.raises(IdempotencyKeyRequired):
        _begin(session, ids, key="x" * 129)


def test_the_record_lands_in_the_frozen_table(session, ids):
    _begin(session, ids)
    row = session.execute(
        text(
            """SELECT actor_account_id, route_key, idempotency_key, request_hash,
                      response_status, expires_at
                 FROM turab.idempotency_records WHERE idempotency_key='key-1'"""
        )
    ).mappings().one()
    assert row["actor_account_id"] == ids.ACC_AMINA
    assert row["route_key"] == ROUTE
    assert row["response_status"] is None
    assert row["expires_at"] > datetime.now(UTC)
