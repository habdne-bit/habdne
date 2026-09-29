"""Request, property and commercial-context snapshots: the inputs a match
records (ADR-02; `API_CONTRACTS_v0.2` §6 "canonical minimum").

Ref: `docs/gate/SLICE_4_PLAN.md` §2, §3.3, §3.4, G4-13.

## What is here, and what is not

Delivered in step 2, because §6 defines their content and no decision is
open on it:
- `request_snapshot`;
- `property_snapshot`;
- `commercial_context_snapshot`, for an offer.

**Not here, each waiting on its decision:**
- the permission snapshot, because WHICH bindings count is G4-10;
- the freshness snapshot, because the state mapping and the gate are G4-11;
- the commercial context of a POTENTIAL property WITHOUT an offer, because
  no willingness data exists in the schema (G4-9).

## Rules every snapshot follows

- **Read-only.** Plain SELECTs; nothing is written.
- **One consistent read.** These functions read with the session they are
  given. The run (step 7) gives them ONE Repeatable Read transaction, so
  the request, the property and the offer are read from one snapshot of the
  database (plan §3.3, measured D7).
- **Exact numbers.** Numeric columns arrive as `Decimal`. A `jsonb` value is
  read as TEXT and parsed with every JSON number as `Decimal`, because
  psycopg's default JSON loader would produce binary floats, which the
  canonical form refuses (G4-13).
- **Deterministic order.** Every list has a total order: criteria by
  (sort_order, criterion_code, request_criterion_id); attributes by code.
  The same state therefore gives the same bytes.
- **Internal.** These are staff-internal records. The commercial snapshot
  carries `seller_expectation_dzd`, which the engine may read (R9.3). No
  customer or public DTO may carry any of them (R9.2).
- **No derived state.** A timestamp is recorded, and whether it is fresh is
  not. That belongs to the freshness snapshot, under G4-11.
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.matching import canonical

REQUEST_FORMAT = "turab.request-snapshot/1"
#: Revision 2 (step 4): adds `location_ancestry`, the chain that G4-6's
#: subtree rule reads, so that the rule replays from the snapshot alone.
#: Revision 3 (review of f789a59): adds `attribute_applies_to`, which
#: `count_min@2` reads (G4-18 (b)).
PROPERTY_FORMAT = "turab.property-snapshot/3"
COMMERCIAL_FORMAT = "turab.commercial-context-snapshot/1"


class SnapshotSubjectMissing(LookupError):
    """The record to snapshot does not exist."""


def exact_json(value: str | None) -> Any:
    """Parse jsonb TEXT with every number as Decimal (never a float)."""
    if value is None:
        return None
    return json.loads(value, parse_float=Decimal, parse_int=Decimal)


def stored_form(snapshot: Any) -> Any:
    """`snapshot` exactly as a stored row gives it back: its canonical JSON
    (G4-13), parsed with every number as Decimal. UUIDs and timestamps become
    their canonical strings. The rules read only this form (step 4), so a live
    run and a replay from stored rows give them identical input. Applying it
    twice changes nothing."""
    if snapshot is None:
        return None
    return exact_json(canonical.canonical_bytes(snapshot).decode("utf-8"))


def request_snapshot(session: Session, request_id: uuid.UUID) -> dict:
    """§6 "Request snapshot": id and version, transaction intent, intent
    stage, budgets and their flexibility, requested type and location with
    their importance, the complete criteria, and the confirmation time."""
    row = session.execute(text("""
        SELECT request_id, version, party_id, status::text AS status,
               transaction_intent::text AS transaction_intent, intent::text AS intent,
               payment::text AS payment,
               desired_property_type::text AS desired_property_type,
               property_type_importance::text AS property_type_importance,
               primary_location_id, location_importance::text AS location_importance,
               budget_target_dzd, budget_max_dzd,
               budget_importance::text AS budget_importance,
               budget_flexibility::text AS budget_flexibility, last_confirmed_at
          FROM turab.requests WHERE request_id = :r"""), {"r": request_id}).mappings().first()
    if row is None:
        raise SnapshotSubjectMissing("request")
    criteria = [
        {**dict(c), "value": exact_json(c["value"])}
        for c in session.execute(text("""
            SELECT request_criterion_id, criterion_code, importance::text AS importance,
                   operator::text AS operator, value::text AS value, unit,
                   blocking_if_unknown, sort_order
              FROM turab.request_criteria WHERE request_id = :r
             ORDER BY sort_order, criterion_code, request_criterion_id"""),
            {"r": request_id}).mappings()
    ]
    return {"format": REQUEST_FORMAT, **dict(row), "criteria": criteria}


#: A location and its ancestors, nearest first. The `path` guard ends the
#: recursion even if `parent_id` ever formed a cycle, which the schema does not
#: forbid (the same concern as G3-14's UNION; PostgreSQL 16 documentation,
#: §7.8.2.2).
_ANCESTRY = """
    WITH RECURSIVE up(location_id, parent_id, depth, path) AS (
        SELECT l.location_id, l.parent_id, 0, ARRAY[l.location_id]
          FROM turab.locations l WHERE l.location_id = :loc
        UNION ALL
        SELECT l.location_id, l.parent_id, u.depth + 1, u.path || l.location_id
          FROM turab.locations l JOIN up u ON l.location_id = u.parent_id
         WHERE NOT l.location_id = ANY(u.path))
    SELECT location_id FROM up ORDER BY depth"""


def location_ancestry(session: Session, location_id: uuid.UUID | None) -> list[uuid.UUID]:
    """`location_id` first, then each parent up to the root. Empty for None or
    for an id that names no location."""
    if location_id is None:
        return []
    return list(session.execute(text(_ANCESTRY), {"loc": location_id}).scalars())


def property_snapshot(session: Session, property_id: uuid.UUID) -> dict:
    """§6 "Property snapshot": id and version, type, location and areas,
    availability and its confirmation time, identity status, and the current
    resolved attributes.

    `attribute_applies_to` (format 3) maps every attribute code to the
    property types it can apply to (null: all), as `attribute_definitions`
    says at the snapshot (G4-18 (b)).

    `location_ancestry` (format 2) is the property's location and every
    location above it. G4-6 passes a LOCATION criterion when the requested
    location is in this chain, which is the same set as G3-14's subtree seen
    from below. Recording it lets the rule replay from the snapshot alone,
    after the location tree has changed.

    **All** current attributes are recorded, with the claim and verification
    level behind each (plan §3.4). Which of them a rule reads is step 4's
    decision (G4-3). A superset records no decision, and still lets a
    reviewer see everything the engine could see.
    """
    row = session.execute(text("""
        SELECT p.property_id, p.version, p.property_type::text AS property_type,
               p.canonical_location_id, p.land_area_m2, p.built_area_m2,
               p.current_availability::text AS current_availability,
               p.availability_last_confirmed_at, p.supply_mode::text AS supply_mode,
               a.canonical_property_id AS alias_of
          FROM turab.properties p
          LEFT JOIN turab.property_identity_aliases a ON a.alias_property_id = p.property_id
         WHERE p.property_id = :p"""), {"p": property_id}).mappings().first()
    if row is None:
        raise SnapshotSubjectMissing("property")
    attributes = [
        {**dict(a), "value": exact_json(a["value"])}
        for a in session.execute(text("""
            SELECT d.code, pa.value::text AS value, pa.resolved_claim_id,
                   c.effective_verification_level::text AS evidence_level
              FROM turab.property_attributes pa
              JOIN turab.attribute_definitions d
                ON d.attribute_definition_id = pa.attribute_definition_id
              LEFT JOIN turab.claims c ON c.claim_id = pa.resolved_claim_id
             WHERE pa.property_id = :p
             ORDER BY d.code"""), {"p": property_id}).mappings()
    ]
    snapshot = dict(row)
    alias_of = snapshot.pop("alias_of")
    snapshot["identity"] = {"is_alias": alias_of is not None, "canonical_property_id":
                            alias_of if alias_of is not None else snapshot["property_id"]}
    snapshot["location_ancestry"] = location_ancestry(session,
                                                      snapshot["canonical_location_id"])
    # G4-18 (b): which property types each attribute can apply to, as the
    # definitions say NOW (null: every type). Recorded for replay.
    snapshot["attribute_applies_to"] = {
        code: None if types is None else list(types)
        for code, types in session.execute(text("""
            SELECT code, applies_to::text[] FROM turab.attribute_definitions ORDER BY code"""))}
    return {"format": PROPERTY_FORMAT, **snapshot, "attributes": attributes}


def commercial_context_snapshot(session: Session, offer_id: uuid.UUID) -> dict:
    """§6 "Commercial context snapshot", for an evaluated offer: id and
    version, transaction type, asking price, the internal seller expectation,
    negotiability, price visibility, and both confirmation times."""
    row = session.execute(text("""
        SELECT offer_id, version, property_id, party_id,
               transaction_type::text AS transaction_type, status::text AS status,
               asking_price_dzd, raw_price_text,
               price_negotiable::text AS price_negotiable, seller_expectation_dzd,
               price_visibility::text AS price_visibility,
               permission_scope::text AS permission_scope,
               last_confirmed_at, commercial_terms_last_confirmed_at
          FROM turab.property_offers WHERE offer_id = :o"""), {"o": offer_id}).mappings().first()
    if row is None:
        raise SnapshotSubjectMissing("offer")
    return {"format": COMMERCIAL_FORMAT, "kind": "OFFER", **dict(row)}
