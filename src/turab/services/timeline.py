"""Operational interaction timeline for a PARTY — Slice 1.

Ref: API_CONTRACTS v0.2 (`getPartiesPartyIdTimeline`); schema v0.2.3
`interactions`; RFC-001 R6.3c (a list is audited once), R9.1 (separate types).

The frozen contract types a timeline item as `additionalProperties: true` —
an open object. An open schema is not permission to return the row: it means
the contract delegates the field set to the implementation, and the
implementation owes an explicit allow-list. `_ENTRY_FIELDS` is that
allow-list, and `interactions.metadata` is deliberately outside it (see
`entry`).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

#: Contract bounds for `#/components/parameters/Page` and `PageSize`.
DEFAULT_PAGE_SIZE = 25
MAX_PAGE_SIZE = 100

#: R9.1. The columns a staff caller may see, named one by one. A column added
#: to `interactions` later is simply absent here and is not serialized.
_ENTRY_FIELDS = (
    "interaction_id", "party_id", "interaction_type", "channel",
    "request_id", "property_id", "opportunity_id", "thread_id",
    "summary", "outcome_code", "occurred_at", "operator_account_id",
    "created_at",
)


class InvalidPagination(ValueError):
    """The page or page size is outside the contract's stated bounds."""


@dataclass(frozen=True, slots=True)
class Page:
    items: tuple[Mapping[str, Any], ...]
    page: int
    page_size: int
    total: int

    @property
    def has_next(self) -> bool:
        return self.page * self.page_size < self.total

    def meta(self) -> dict[str, Any]:
        """The contract's `PageMeta`."""
        return {
            "page": self.page,
            "page_size": self.page_size,
            "total": self.total,
            "has_next": self.has_next,
        }


def validate_pagination(page: int, page_size: int) -> tuple[int, int]:
    """Enforce the contract's bounds here rather than at the edge.

    `page_size` is capped because an uncapped page size turns a paginated
    staff read into a bulk export of one party's entire operational history
    in a single audited request.
    """
    if page < 1:
        raise InvalidPagination("page must be 1 or greater")
    if page_size < 1 or page_size > MAX_PAGE_SIZE:
        raise InvalidPagination(f"page_size must be between 1 and {MAX_PAGE_SIZE}")
    return page, page_size


def entry(row: Mapping[str, Any]) -> dict[str, Any]:
    """Render one interaction for a staff audience.

    `interactions.metadata` is withheld at every audience, including this one.
    It is free-form operator JSON that no allow-list can vet: whatever an
    integration decides to put there — a raw message body, a verification
    code, a copied identity document reference — would be serialized the day
    it starts being written. A field whose contents cannot be stated in
    advance cannot be released in advance.
    """
    out: dict[str, Any] = {}
    for field in _ENTRY_FIELDS:
        value = row[field]
        if isinstance(value, uuid.UUID):
            out[field] = str(value)
        elif hasattr(value, "isoformat"):
            out[field] = value.isoformat()
        else:
            out[field] = value
    return out


def read_party_timeline(
    session: Session,
    party_id: uuid.UUID,
    *,
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
) -> Page:
    """One party's interactions, newest first.

    The party filter is a bound parameter and is never optional: there is no
    code path through this function that returns another party's rows, or
    every party's rows. `idx_interactions_party_time` serves exactly this
    ordering.

    Rows whose `party_id` is NULL are excluded by the equality predicate.
    That matters: `interactions.party_id` is `ON DELETE SET NULL`, so an
    orphaned interaction must belong to nobody rather than to everybody.
    """
    page, page_size = validate_pagination(page, page_size)

    total = session.execute(
        text("SELECT count(*) FROM turab.interactions WHERE party_id = :party_id"),
        {"party_id": party_id},
    ).scalar_one()

    rows = session.execute(
        text(
            """
            SELECT interaction_id, party_id,
                   interaction_type::text AS interaction_type,
                   channel::text AS channel,
                   request_id, property_id, opportunity_id, thread_id,
                   summary, outcome_code, occurred_at, operator_account_id,
                   created_at
              FROM turab.interactions
             WHERE party_id = :party_id
             ORDER BY occurred_at DESC, interaction_id
             LIMIT :limit OFFSET :offset
            """
        ),
        {
            "party_id": party_id,
            "limit": page_size,
            "offset": (page - 1) * page_size,
        },
    ).mappings().all()

    return Page(tuple(rows), page, page_size, int(total))
