"""Optimistic concurrency for mutable projections.

Ref: API_CONTRACTS v0.2 §2.4 ("Mutable projection PATCH requests require
`If-Match-Version`. On stale version, return 409 and do not partially apply
changes."); frozen contract component `IfMatchVersion`.

A note on the header name. API_CONTRACTS §2.4 calls it `If-Match-Version`,
while the frozen `openapi_v0.2.yaml` declares the component `IfMatchVersion`
with `name: If-Match`. Per the authority order in API_CONTRACTS §1, OpenAPI
governs HTTP shape, so the wire header is **If-Match**. `If-Match-Version` is
accepted as an alias so a client following the prose is not silently rejected,
and the discrepancy is recorded for the contract owner rather than resolved
unilaterally.

`requests`, `properties` and `property_offers` carry an integer `version`
bumped by `bump_version_and_timestamp()` in the frozen schema. `parties` does
not, which the contract's fourth If-Match operation implies it should; see
`VERSIONED_TABLES`.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

HEADER = "If-Match"
HEADER_ALIAS = "If-Match-Version"

#: table -> primary key column, for resources carrying an integer `version`.
#: `parties` is deliberately absent: it has no version column in the frozen
#: schema, so PATCH /parties/{id} cannot be version-checked without a schema
#: change. Recorded as an accepted deviation rather than faked.
VERSIONED_TABLES: dict[str, str] = {
    "requests": "request_id",
    "properties": "property_id",
    "property_offers": "offer_id",
}


class IfMatchRequired(Exception):
    """§2.4. The header is required on mutable projection PATCH."""


class MalformedIfMatch(Exception):
    """The header is present but is not a version integer."""


class StaleVersion(Exception):
    """The caller's version is not the current one. Nothing was applied."""

    def __init__(self, table: str, resource_id: uuid.UUID, expected: int | None,
                 provided: int) -> None:
        self.table = table
        self.resource_id = resource_id
        self.expected = expected
        self.provided = provided
        super().__init__(
            f"{table} {resource_id} is at a different version than the caller's"
        )


@dataclass(frozen=True, slots=True)
class VersionGuard:
    table: str
    id_column: str
    resource_id: uuid.UUID
    version: int


def parse_if_match(value: str | None, alias: str | None = None) -> int:
    """Read the version from the header, accepting a weak/quoted ETag form."""
    raw = value or alias
    if raw is None or not raw.strip():
        raise IfMatchRequired(f"{HEADER} header is required")
    cleaned = raw.strip()
    if cleaned.startswith("W/"):
        cleaned = cleaned[2:]
    cleaned = cleaned.strip('"').strip()
    try:
        version = int(cleaned)
    except ValueError as exc:
        raise MalformedIfMatch(f"{HEADER} must be a version integer") from exc
    if version < 1:
        raise MalformedIfMatch(f"{HEADER} must be a positive version")
    return version


def check(
    session: Session, table: str, resource_id: uuid.UUID, provided: int
) -> VersionGuard:
    """Verify the caller's version matches, BEFORE any change is applied.

    §2.4 requires that a stale version apply nothing, so this is called first
    and the caller runs inside one transaction — a partial apply is not a
    thing that can happen rather than a thing that is cleaned up.
    """
    if table not in VERSIONED_TABLES:
        raise ValueError(f"{table} carries no version column in the frozen schema")
    id_column = VERSIONED_TABLES[table]
    current = session.execute(
        text(f"SELECT version FROM turab.{table} WHERE {id_column} = :id"),
        {"id": resource_id},
    ).scalar_one_or_none()
    if current is None or current != provided:
        raise StaleVersion(table, resource_id, current, provided)
    return VersionGuard(table, id_column, resource_id, provided)


def current_version(session: Session, table: str, resource_id: uuid.UUID) -> int | None:
    id_column = VERSIONED_TABLES[table]
    return session.execute(
        text(f"SELECT version FROM turab.{table} WHERE {id_column} = :id"),
        {"id": resource_id},
    ).scalar_one_or_none()
