"""Request, property and commercial-context snapshots: the inputs a match
records (ADR-02; `API_CONTRACTS_v0.2` §6 "canonical minimum").

Ref: `docs/gate/SLICE_4_PLAN.md` §2, §3.3, §3.4, G4-13.

## What is here, and what is not

Delivered in step 2, because §6 defines their content and no decision is
open on it:
- `request_snapshot`;
- `property_snapshot`;
- `commercial_context_snapshot`, for an offer.

Delivered in step 5, after G4-10 and G4-11 were decided (review of
f789a59):
- `freshness_snapshot`: the three derived states. It is pure;
- `permission_snapshot`: the matching bindings of the offer and its
  property, each with its state at the run's instant.

**Not here:** the commercial context of a POTENTIAL property WITHOUT an
offer, because no willingness data exists in the schema (G4-9).

**The run's instant (`as_of`).** Freshness and consent currency are judged
at ONE instant, which the caller gives: the run takes it once (step 7), and
stores it as the match's `evaluated_at`. It is not written into any
snapshot. G4-13 decided that the hash excludes `evaluated_at` and includes
the DERIVED states. So two runs that see the same states are the same input.
A state change is a new input.

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
- **No derived state** in the request, property and commercial snapshots. A
  timestamp is recorded there, and whether it is fresh is not. The
  freshness and permission snapshots hold the derived states (G4-13).
"""
from __future__ import annotations

import json
import uuid
from decimal import Decimal
from datetime import datetime
from typing import Any, Mapping

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
#: Format 2 (review of a5ea6f5): the states are derived by pinned functions
#: (`gates.py`), and each snapshot names the one it used in `derived_by`.
FRESHNESS_FORMAT = "turab.freshness-snapshot/2"
PERMISSION_FORMAT = "turab.permission-snapshot/2"
#: The pinned functions that derive the states (`id`, `version`).
FRESHNESS_STATE = ("freshness.state", "1")
BINDING_STATE = ("permission.binding_state", "1")


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


# --- step 5: freshness (G4-11) and permission (G4-10) -----------------------------------

#: The consent purposes that count for matching (G4-10, decided in the review
#: of f789a59): PRIVATE_MATCHING_ONLY, and a valid PUBLIC_LISTING_ALLOWED for
#: internal matching of the same bound resource. The second grants no new
#: sharing; sharing is Slice 5's check.
MATCHING_PURPOSES = ("PRIVATE_MATCHING_ONLY", "PUBLIC_LISTING_ALLOWED")


def _aware(as_of: datetime) -> datetime:
    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:
        raise ValueError("as_of must be a timezone-aware instant")
    return as_of


def _pinned(key: tuple[str, str]):
    from turab.matching.registry import REGISTRY
    return REGISTRY.resolve(*key)


def _state(confirmed_at: Any, days: int, as_of: datetime) -> dict:
    """One subject's freshness, by the pinned `freshness.state` (G4-11)."""
    return _pinned(FRESHNESS_STATE).evaluate(stored_form(confirmed_at), days, as_of)


def freshness_snapshot(request: Mapping[str, Any], prop: Mapping[str, Any],
                       offer: Mapping[str, Any] | None, *, policy_version: str,
                       threshold_days: Mapping[str, int], as_of: datetime) -> dict:
    """The freshness snapshot (G4-11), from the three snapshots alone. Pure.

    - request: `last_confirmed_at` against `threshold_days["request"]`;
    - property: `availability_last_confirmed_at` against `["property"]`;
    - offer: `commercial_terms_last_confirmed_at` against `["offer_terms"]`
      (plan §3.4 of Slice 3, `evaluate_offer`). It is NOT_APPLICABLE only
      when no offer is evaluated.

    `as_of` is not recorded (see the module docstring). `derived_by` names the
    pinned function that derived the states."""
    as_of = _aware(as_of)
    request, prop, offer = stored_form(request), stored_form(prop), stored_form(offer)
    days = {key: threshold_days[key] for key in ("request", "property", "offer_terms")}
    return {
        "format": FRESHNESS_FORMAT,
        "derived_by": "@".join(FRESHNESS_STATE),
        "policy_version": policy_version,
        "threshold_days": days,
        "request": _state(request["last_confirmed_at"], days["request"], as_of),
        "property": _state(prop["availability_last_confirmed_at"], days["property"], as_of),
        "offer": ({"state": "NOT_APPLICABLE", "basis": "NO_EVALUATED_OFFER",
                   "confirmed_at": None} if offer is None else
                  _state(offer["commercial_terms_last_confirmed_at"], days["offer_terms"],
                         as_of)),
    }


def binding_state(binding: Mapping[str, Any], offer_party_id: Any, as_of: datetime) -> str:
    """One binding's state at `as_of`, by the pinned `permission.binding_state`
    (G4-10; its docstring states the precedence)."""
    return _pinned(BINDING_STATE).evaluate(stored_form(binding), offer_party_id,
                                           _aware(as_of))


def permission_snapshot(session: Session, offer_id: uuid.UUID, *, as_of: datetime) -> dict:
    """The permission snapshot (G4-10): the offer's party and sharing scope,
    and every binding for a matching purpose on the offer OR on its property,
    each with its grant and its state at `as_of`.

    `party_property_relations` is not read (acceptance condition 10). A
    property binding counts only when its grant's party is the offer's
    party, which the grant itself says."""
    as_of = _aware(as_of)
    offer = session.execute(text("""
        SELECT offer_id, property_id, party_id, permission_scope::text AS permission_scope
          FROM turab.property_offers WHERE offer_id = :o"""), {"o": offer_id}).mappings().first()
    if offer is None:
        raise SnapshotSubjectMissing("offer")
    bindings = []
    for row in session.execute(text("""
            SELECT b.consent_binding_id,
                   CASE WHEN b.offer_id IS NOT NULL THEN 'OFFER' ELSE 'PROPERTY' END AS bound_to,
                   b.purpose::text AS purpose, b.bound_at, b.revoked_at AS binding_revoked_at,
                   g.consent_id, g.party_id AS grant_party_id, g.scope::text AS grant_scope,
                   g.status::text AS grant_status, g.granted_at,
                   g.revoked_at AS grant_revoked_at
              FROM turab.resource_consent_bindings b
              JOIN turab.consent_grants g ON g.consent_id = b.consent_id
             WHERE (b.offer_id = :o OR b.property_id = :p)
               AND b.purpose::text = ANY(:purposes)
             ORDER BY b.consent_binding_id"""),
            {"o": offer_id, "p": offer["property_id"],
             "purposes": list(MATCHING_PURPOSES)}).mappings():
        binding = dict(row)
        binding["state"] = binding_state(binding, offer["party_id"], as_of)
        bindings.append(binding)
    return {"format": PERMISSION_FORMAT, "derived_by": "@".join(BINDING_STATE),
            "offer_id": offer["offer_id"],
            "offer_party_id": offer["party_id"],
            "permission_scope": offer["permission_scope"], "bindings": bindings}
