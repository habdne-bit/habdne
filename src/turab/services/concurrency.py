"""Optimistic concurrency for mutable projections.

Ref: API_CONTRACTS v0.2 §2.4 ("Mutable projection PATCH requests require
`If-Match-Version`. On stale version, return 409 and do not partially apply
changes."); frozen contract component `IfMatchVersion`.

Technical Patch v0.2.2 settled the header name: the canonical header is
**If-Match-Version**, and the frozen contract types it `integer, minimum: 1`.
The undocumented `If-Match` alias carried during v0.2.1 is gone — there was no
production client depending on it.

Because the contract now types the value as an integer, a weak/quoted ETag form
is no longer accepted either. `If-Match` conventionally carries an ETag, which
is why v0.2.1 tolerated `W/"3"`; `If-Match-Version` carries a version integer
and nothing else, so accepting ETag syntax would be a liberality the contract
does not describe.

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

HEADER = "If-Match-Version"

#: table -> primary key column, for resources carrying an integer `version`.
#: `parties` joined this set in v0.2.2 (decision D2): it gained
#: `version integer NOT NULL DEFAULT 1 CHECK (version > 0)` and the
#: `bump_version_and_timestamp()` trigger, so PATCH /parties/{party_id} can now
#: be version-checked as the contract has always required.
VERSIONED_TABLES: dict[str, str] = {
    "parties": "party_id",
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


def parse_if_match(value: str | None) -> int:
    """Read the version from the header.

    The contract types it `integer, minimum: 1`, so that is exactly what is
    accepted: no ETag quoting, no weak-validator prefix, no alias.
    """
    if value is None or not value.strip():
        raise IfMatchRequired(f"{HEADER} header is required")
    try:
        version = int(value.strip())
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
