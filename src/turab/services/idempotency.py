"""Idempotency for mutating commands, backed by `idempotency_records`.

Ref: API_CONTRACTS v0.2 §2.3; ADR-09; Slice 0 mandatory tests
("duplicate key with same payload replays result", "duplicate key with
different payload returns 409").

The frozen table is the whole mechanism:
    UNIQUE(actor_account_id, route_key, idempotency_key)
plus `request_hash`, `response_status`, `response_body`, `expires_at`.

Note the uniqueness is per ACTOR. Two accounts may use the same key without
colliding, which is what makes a client-chosen key safe.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

DEFAULT_TTL = timedelta(hours=24)
MAX_KEY_LENGTH = 128  # the frozen contract's maxLength for Idempotency-Key


class IdempotencyOutcome(StrEnum):
    NEW = "NEW"
    REPLAYED = "REPLAYED"


@dataclass(frozen=True, slots=True)
class Replay:
    status: int
    body: dict[str, Any] | None
    resource_ref: str | None


class IdempotencyKeyRequired(Exception):
    """§2.3. Every mutating authenticated POST must carry the header."""


class IdempotencyKeyConflict(Exception):
    """Same key, different payload. The client reused a key for new content."""

    def __init__(self, route_key: str, key: str) -> None:
        self.route_key = route_key
        self.key = key
        super().__init__(
            f"idempotency key already used on {route_key} with a different "
            "request body"
        )


def canonical_request_hash(payload: Any) -> str:
    """A stable hash of the request body.

    Canonicalised so that key order and insignificant whitespace do not make
    an identical request look like a different one — a replay that failed for
    that reason would push a client into retrying a command it already ran.
    """
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _validate_key(key: str | None) -> str:
    if not key or not key.strip():
        raise IdempotencyKeyRequired("Idempotency-Key header is required")
    key = key.strip()
    if len(key) > MAX_KEY_LENGTH:
        raise IdempotencyKeyRequired(
            f"Idempotency-Key exceeds {MAX_KEY_LENGTH} characters"
        )
    return key


def lookup(
    session: Session,
    *,
    actor_account_id: uuid.UUID,
    route_key: str,
    idempotency_key: str | None,
    payload: Any,
) -> tuple[Replay | None, uuid.UUID | None]:
    """The read half of `begin`: (the stored result of an identical earlier
    call, or None; the id of an EXPIRED record to replace, or None).

    It writes nothing, so a command can decide a refusal between this and
    `claim` and write nothing at all (Slice 4, G4-15 D6). Raises on a key
    reused with a different body, or claimed and never completed.
    """
    key = _validate_key(idempotency_key)
    request_hash = canonical_request_hash(payload)
    existing = session.execute(
        text(
            """
            SELECT idempotency_record_id, request_hash, response_status,
                   response_body, response_resource_ref, expires_at
              FROM turab.idempotency_records
             WHERE actor_account_id = :actor
               AND route_key = :route_key
               AND idempotency_key = :key
            """
        ),
        {"actor": actor_account_id, "route_key": route_key, "key": key},
    ).mappings().first()
    if existing is None:
        return None, None
    if existing["expires_at"] <= datetime.now(UTC):
        return None, existing["idempotency_record_id"]
    if existing["request_hash"] != request_hash:
        raise IdempotencyKeyConflict(route_key, key)
    if existing["response_status"] is None:
        # Claimed but never completed: an earlier attempt died mid-flight.
        # Replaying an absent result would be a lie, and re-running could
        # duplicate a side effect, so the client is told to retry with a
        # new key rather than silently getting either.
        raise IdempotencyKeyConflict(route_key, key)
    return Replay(
        status=existing["response_status"],
        body=existing["response_body"],
        resource_ref=existing["response_resource_ref"],
    ), None


def claim(
    session: Session,
    *,
    actor_account_id: uuid.UUID,
    route_key: str,
    idempotency_key: str | None,
    payload: Any,
    expired_record_id: uuid.UUID | None = None,
    ttl: timedelta = DEFAULT_TTL,
) -> None:
    """The write half of `begin`: replace an expired record, then claim."""
    key = _validate_key(idempotency_key)
    if expired_record_id is not None:
        session.execute(
            text(
                """DELETE FROM turab.idempotency_records
                    WHERE idempotency_record_id = :id"""
            ),
            {"id": expired_record_id},
        )
    session.execute(
        text(
            """
            INSERT INTO turab.idempotency_records
                   (actor_account_id, route_key, idempotency_key, request_hash,
                    expires_at)
            VALUES (:actor, :route_key, :key, :hash, :expires_at)
            """
        ),
        {
            "actor": actor_account_id,
            "route_key": route_key,
            "key": key,
            "hash": canonical_request_hash(payload),
            "expires_at": datetime.now(UTC) + ttl,
        },
    )


def begin(
    session: Session,
    *,
    actor_account_id: uuid.UUID,
    route_key: str,
    idempotency_key: str | None,
    payload: Any,
    ttl: timedelta = DEFAULT_TTL,
) -> tuple[IdempotencyOutcome, Replay | None]:
    """Claim the key, or return the stored result of an identical earlier call.

    Returns (NEW, None) when the caller should execute the command, or
    (REPLAYED, Replay) when it must not. Raises on a key reused with a
    different body.

    Expired records are replaced rather than replayed: `expires_at` marks the
    point past which a replay is no longer promised. `lookup` then `claim`,
    in one call.
    """
    replay, expired = lookup(session, actor_account_id=actor_account_id,
                             route_key=route_key, idempotency_key=idempotency_key,
                             payload=payload)
    if replay is not None:
        return IdempotencyOutcome.REPLAYED, replay
    claim(session, actor_account_id=actor_account_id, route_key=route_key,
          idempotency_key=idempotency_key, payload=payload,
          expired_record_id=expired, ttl=ttl)
    return IdempotencyOutcome.NEW, None


def complete(
    session: Session,
    *,
    actor_account_id: uuid.UUID,
    route_key: str,
    idempotency_key: str,
    status: int,
    body: dict[str, Any] | None = None,
    resource_ref: str | None = None,
) -> None:
    """Store the result so an identical retry replays it."""
    session.execute(
        text(
            """
            UPDATE turab.idempotency_records
               SET response_status = :status,
                   response_body = CAST(:body AS jsonb),
                   response_resource_ref = :ref
             WHERE actor_account_id = :actor
               AND route_key = :route_key
               AND idempotency_key = :key
            """
        ),
        {
            "status": status,
            "body": json.dumps(body, ensure_ascii=False) if body is not None else None,
            "ref": resource_ref,
            "actor": actor_account_id,
            "route_key": route_key,
            "key": idempotency_key.strip(),
        },
    )
