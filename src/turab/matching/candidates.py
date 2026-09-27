"""The candidate set: which (property, offer) pairs a run evaluates, and why
the others are not evaluated (Slice 4 step 3).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-8 and G4-9, decided in the review of
4538a2d; ADR-01 (one commercial context per evaluation), ADR-03 (canonical
only); `API_CONTRACTS_v0.2` §4.8; red-team C01, D05, E02; the frozen trigger
`trg_match_commercial_context` (`schema_v0.2.3.sql:1170–1207`).

## The rules (G4-8, as decided)

- **The request** must be `ACTIVE` or `NEEDS_CONFIRMATION`. Any other status
  is refused (`RequestNotMatchable`); the route answers a typed 409 in step
  7. A stale request is still evaluated; its freshness gate carries the
  staleness (M-06, step 5).
- **Transaction compatibility** (C01, mandatory test 1): a BUY request
  evaluates only SALE offers, and a RENT request only RENT offers. The
  frozen trigger enforces the same mapping as a backstop.
- **Offers:** only `ACTIVE` offers of that transaction type qualify.
- **One candidate per qualifying offer.** Two ACTIVE SALE offers on one
  property are two candidates, each with its own commercial context
  (ADR-01).
- **Canonical properties only** (E02, mandatory test 9). An alias is never a
  candidate.
- **`UNAVAILABLE` excludes the property.** Every other availability value is
  evaluated; its effect is the freshness gate's (step 5).
- **`property_ids`** narrows the set. The ids are de-duplicated and ordered.

## G4-9 (a), as decided

A POTENTIAL property with **no offer at all** is **not evaluated**. The
frozen schema holds no structured willingness context, so there is nothing
to evaluate it against. Its exclusion is reported with that reason.
Mandatory test 6 is proven in this refusing half only.

A POTENTIAL property that HAS offers, none of which qualifies for this
request (another transaction type, or not ACTIVE), is not "without offer".
It is `NO_QUALIFYING_OFFER`, with the count of its offers (review of
cc3a7fe).

## Every exclusion is reported, never silent

Each non-candidate that the caller named, or that a full scan would
otherwise have reached, is returned with a reason:

| Reason | When |
|---|---|
| `PROPERTY_NOT_FOUND` | a listed id that names no property |
| `IDENTITY_ALIAS` | a listed id that is an alias; the canonical id is given |
| `OFFER_ON_ALIAS` | a qualifying offer sits on an alias property (see below) |
| `PROPERTY_UNAVAILABLE` | `current_availability = UNAVAILABLE` |
| `POTENTIAL_WITHOUT_OFFER` | G4-9 (a): a POTENTIAL property with no offer at all |
| `NO_QUALIFYING_OFFER` | a listed property that has offers, or none, but no ACTIVE offer of the right type |

**Precedence, one reason each:** alias (`OFFER_ON_ALIAS` if it carries a
qualifying offer, else `IDENTITY_ALIAS`) > `PROPERTY_UNAVAILABLE` >
candidate > `POTENTIAL_WITHOUT_OFFER` > `NO_QUALIFYING_OFFER`. Even with
willingness data, an unavailable property would not be evaluated, so
`PROPERTY_UNAVAILABLE` comes before `POTENTIAL_WITHOUT_OFFER`.

**Scope of a full scan.** A full scan (no `property_ids`) takes into scope:
- every property with a qualifying offer;
- every POTENTIAL property with no offer at all.

**Every property in scope ends as a candidate or with exactly one reason.**
Before the review of cc3a7fe, a POTENTIAL property that was UNAVAILABLE, or
an alias, could enter the scope and leave it unreported.

A property outside the scope is not listed, or a BUY run would enumerate
every rental in the market.

**`OFFER_ON_ALIAS`, a finding stated here.** G3-13 decided that an alias's
offers are not moved. The frozen trigger requires the evaluated offer to
belong to the matched property, and forbids a match on an alias. So an
ACTIVE offer attached to an alias can be evaluated neither under the alias
nor under its canonical record. This module reports it; it decides nothing
more.

These labels are the diagnostic's exclusion reasons. They are not rows of
`reason_codes`. Where they are stored is the diagnostic row's
`blocker_summary`, in step 7.

**Read-only.** Plain SELECTs; nothing is written. The run gives this
function its one Repeatable Read transaction (plan §3.3).
"""
from __future__ import annotations

import enum
import uuid
from dataclasses import dataclass, field
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.orm import Session

#: The statuses a run accepts (G4-8).
MATCHABLE_REQUEST_STATUSES = ("ACTIVE", "NEEDS_CONFIRMATION")

#: Request intent -> the offer transaction type it may evaluate (C01). The
#: frozen trigger enforces the same mapping.
OFFER_TYPE_FOR_INTENT = {"BUY": "SALE", "RENT": "RENT"}


class Exclusion(enum.StrEnum):
    PROPERTY_NOT_FOUND = "PROPERTY_NOT_FOUND"
    IDENTITY_ALIAS = "IDENTITY_ALIAS"
    OFFER_ON_ALIAS = "OFFER_ON_ALIAS"
    PROPERTY_UNAVAILABLE = "PROPERTY_UNAVAILABLE"
    POTENTIAL_WITHOUT_OFFER = "POTENTIAL_WITHOUT_OFFER"
    NO_QUALIFYING_OFFER = "NO_QUALIFYING_OFFER"


class RequestNotFound(LookupError):
    """The request does not exist."""


class RequestNotMatchable(ValueError):
    """The request's status is not one a run accepts (G4-8)."""

    def __init__(self, status: str) -> None:
        super().__init__(f"a request in status {status} is not matched; only "
                         f"{' or '.join(MATCHABLE_REQUEST_STATUSES)} are")
        self.status = status


@dataclass(frozen=True, slots=True)
class Candidate:
    property_id: uuid.UUID
    property_version: int
    offer_id: uuid.UUID
    offer_version: int


@dataclass(frozen=True, slots=True)
class Excluded:
    property_id: uuid.UUID
    reason: Exclusion
    detail: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class CandidateSet:
    request_id: uuid.UUID
    request_status: str
    transaction_intent: str
    offer_transaction_type: str
    candidates: tuple[Candidate, ...]
    excluded: tuple[Excluded, ...]


_ROWS = """
    WITH qualifying AS (
        SELECT o.offer_id, o.property_id, o.version AS offer_version
          FROM turab.property_offers o
         WHERE o.status = 'ACTIVE'
           AND o.transaction_type = CAST(:offer_type AS turab.transaction_type)
    )
    SELECT p.property_id, p.version AS property_version,
           p.supply_mode::text AS supply_mode,
           p.current_availability::text AS availability,
           a.canonical_property_id AS alias_of,
           (SELECT count(*) FROM turab.property_offers ao
             WHERE ao.property_id = p.property_id) AS offers_on_property,
           q.offer_id, q.offer_version
      FROM turab.properties p
      LEFT JOIN turab.property_identity_aliases a ON a.alias_property_id = p.property_id
      LEFT JOIN qualifying q ON q.property_id = p.property_id
     WHERE {scope}
     ORDER BY p.property_id, q.offer_id
"""

#: A full scan's SCOPE: a property with a qualifying offer, or a POTENTIAL
#: property with no offer at all (G4-9 reports it). Every property in scope
#: ends as a candidate or with exactly one reason (review of cc3a7fe).
_FULL_SCAN = ("(q.offer_id IS NOT NULL OR (p.supply_mode = 'POTENTIAL' AND NOT EXISTS "
              "(SELECT 1 FROM turab.property_offers ao WHERE ao.property_id = p.property_id)))")
_LISTED = "p.property_id = ANY(:ids)"


def candidate_set(session: Session, request_id: uuid.UUID,
                  property_ids: Iterable[uuid.UUID] | None = None) -> CandidateSet:
    request = session.execute(text("""
        SELECT status::text AS status, transaction_intent::text AS intent
          FROM turab.requests WHERE request_id = :r"""), {"r": request_id}).mappings().first()
    if request is None:
        raise RequestNotFound("request")
    if request["status"] not in MATCHABLE_REQUEST_STATUSES:
        raise RequestNotMatchable(request["status"])
    offer_type = OFFER_TYPE_FOR_INTENT[request["intent"]]

    listed = None if property_ids is None else sorted(set(property_ids))
    params = {"offer_type": offer_type}
    if listed is not None:
        params["ids"] = listed
    rows = session.execute(text(_ROWS.format(scope=_LISTED if listed is not None
                                             else _FULL_SCAN)), params).mappings().all()

    by_property: dict[uuid.UUID, list] = {}
    for row in rows:
        by_property.setdefault(row["property_id"], []).append(row)

    candidates: list[Candidate] = []
    excluded: list[Excluded] = []
    for property_id in (listed if listed is not None else sorted(by_property)):
        group = by_property.get(property_id)
        if group is None:
            excluded.append(Excluded(property_id, Exclusion.PROPERTY_NOT_FOUND))
            continue
        # Every property reaching this point is IN SCOPE (listed, or inside
        # the full scan's scope), so it ends as candidates or with exactly
        # one reason. Precedence: alias > unavailable > candidate >
        # POTENTIAL without any offer > no qualifying offer.
        head = group[0]
        offers = [r for r in group if r["offer_id"] is not None]
        if head["alias_of"] is not None:
            detail = {"canonical_property_id": head["alias_of"]}
            if offers:
                excluded.append(Excluded(property_id, Exclusion.OFFER_ON_ALIAS, {
                    **detail, "offer_ids": [r["offer_id"] for r in offers]}))
            else:
                excluded.append(Excluded(property_id, Exclusion.IDENTITY_ALIAS, detail))
            continue
        if head["availability"] == "UNAVAILABLE":
            excluded.append(Excluded(property_id, Exclusion.PROPERTY_UNAVAILABLE))
            continue
        if offers:
            candidates.extend(Candidate(property_id, r["property_version"], r["offer_id"],
                                        r["offer_version"]) for r in offers)
        elif head["supply_mode"] == "POTENTIAL" and head["offers_on_property"] == 0:
            excluded.append(Excluded(property_id, Exclusion.POTENTIAL_WITHOUT_OFFER, {
                "because": "no structured willingness context exists (G4-9 (a))"}))
        else:
            # Offers exist, but none qualifies for THIS request (another
            # transaction type, or not ACTIVE). That is not "without offer".
            excluded.append(Excluded(property_id, Exclusion.NO_QUALIFYING_OFFER,
                                     {"offers_on_property": head["offers_on_property"]}))
    return CandidateSet(request_id, request["status"], request["intent"], offer_type,
                        tuple(candidates), tuple(excluded))
