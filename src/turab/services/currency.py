"""The currency check (Slice 5, §3.7 [R3-2]): one table, three users.

Ref: `docs/gate/SLICE_5_PLAN.md` §3.7 (adopted in the review of `3a797d8`),
G5-2 (a), G5-5 (a) (decided in the review of `60b0152`); Spec §15.3; M-05,
M-06.

**One function, three users.** The APPROVED review requires VALID (step 3).
`revalidate` writes the result and `share` requires it (step 5). Each calls
`check`, and nothing else decides validity.

**The table.** Each fact is classed on its own. The validity is the worst
class found (INVALID > NEEDS_CONFIRMATION > VALID). Every class other than
VALID adds a reason, so the reasons name every failing fact, not only the
worst. A value the table does not name is INVALID: an unreachable or new
state fails closed.

**The rules are the match's.** The freshness state and the permission gate
are computed by the pinned functions whose versions the match recorded
(`explanation.engine`), with the thresholds the match recorded
(`freshness_snapshot.threshold_days`), on facts read NOW. A fact Slice 4
called FRESH or PASS is called the same here.

**Locks.** `check` reads the facts after locking their rows, in this order,
after the caller's lock on the match:
- the request, `FOR NO KEY UPDATE`. Two approvals on one request
  serialize here, so the open-opportunity check that follows is made
  against every opportunity committed before it, aliases included
  (the index cannot see them, §3.3);
- the property and the offer, `FOR SHARE`;
- the offer's and the property's consent bindings and their grants,
  `FOR SHARE`.

A writer of any of these facts waits until the approval commits. So the
facts the check classed are the facts at commit.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.matching import snapshots
from turab.matching.registry import REGISTRY

VALID, NEEDS_CONFIRMATION, INVALID = "VALID", "NEEDS_CONFIRMATION", "INVALID"
#: The order of the classes, worst last.
RANK = {VALID: 0, NEEDS_CONFIRMATION: 1, INVALID: 2}

_FRESHNESS = {"FRESH": VALID, "STALE": NEEDS_CONFIRMATION, "UNKNOWN": NEEDS_CONFIRMATION}

#: §3.7's table, fact by fact, in the order the reasons are listed.
TABLE: Mapping[str, Mapping[str, str]] = {
    "REQUEST_STATUS": {
        "ACTIVE": VALID, "NEEDS_CONFIRMATION": NEEDS_CONFIRMATION,
        "PAUSED": NEEDS_CONFIRMATION, "CLOSED": INVALID, "RAW": INVALID,
        "CONTACTED": INVALID, "QUALIFIED": INVALID},
    "OFFER_STATUS": {
        "ACTIVE": VALID, "PENDING_INFO": NEEDS_CONFIRMATION, "PAUSED": NEEDS_CONFIRMATION,
        "WITHDRAWN": INVALID, "CLOSED": INVALID, "DRAFT": INVALID},
    "AVAILABILITY": {
        "AVAILABLE": VALID, "POTENTIALLY_AVAILABLE": VALID,
        "UNDER_DISCUSSION": NEEDS_CONFIRMATION, "TEMPORARILY_UNAVAILABLE": NEEDS_CONFIRMATION,
        "NEEDS_CONFIRMATION": NEEDS_CONFIRMATION, "UNKNOWN": NEEDS_CONFIRMATION,
        "UNAVAILABLE": INVALID},
    "IDENTITY": {"CANONICAL": VALID, "ALIAS": INVALID},
    "REQUEST_FRESHNESS": _FRESHNESS,
    "PROPERTY_FRESHNESS": _FRESHNESS,
    "OFFER_FRESHNESS": _FRESHNESS,
    "PERMISSION": {"PASS": VALID, "UNKNOWN": NEEDS_CONFIRMATION, "FAIL": INVALID},
}

#: A seeded reason code, only where its name and label state the fact (the
#: rule `eligibility.py` follows). Every other reason carries no code; its
#: fact and value say what it is.
REASON_CODES: Mapping[tuple[str, str], str] = {
    ("REQUEST_FRESHNESS", "STALE"): "REQUEST_STALE",
    ("PROPERTY_FRESHNESS", "STALE"): "PROPERTY_STALE",
    ("OFFER_FRESHNESS", "STALE"): "OFFER_STALE",
    ("AVAILABILITY", "UNAVAILABLE"): "PROPERTY_UNAVAILABLE",
    ("PERMISSION", "FAIL"): "CONSENT_REVOKED",
    ("PERMISSION", "UNKNOWN"): "PERMISSION_MISSING",
}


@dataclass(frozen=True, slots=True)
class Currency:
    validity: str
    reasons: tuple[Mapping[str, Any], ...]


def classify(facts: Mapping[str, str]) -> Currency:
    """§3.7, pure: the worst class over the facts, and one reason per fact
    that is not VALID, in the table's order."""
    if set(facts) != set(TABLE):
        raise ValueError(f"the facts must be exactly {sorted(TABLE)}")
    worst, reasons = VALID, []
    for fact, classes in TABLE.items():
        value = facts[fact]
        cls = classes.get(value, INVALID)
        if RANK[cls] > RANK[worst]:
            worst = cls
        if cls != VALID:
            reasons.append({"fact": fact, "value": value, "class": cls,
                            "reason_code": REASON_CODES.get((fact, value))})
    return Currency(worst, tuple(reasons))


@dataclass(frozen=True, slots=True)
class Checked:
    """What `check` found: the classification, the facts, and what an
    approval records from them."""

    currency: Currency
    facts: Mapping[str, str]
    sharing_scope: str
    permission_snapshot: dict
    current_permission_binding_id: uuid.UUID | None
    as_of: datetime = field(compare=False)


def _engine_rule(match: Mapping[str, Any], name: str):
    """The pinned function the match recorded under `name` ("id@version")."""
    rule_id, version = match["engine"][name].split("@")
    return REGISTRY.resolve(rule_id, version)


def _lock(session: Session, *, request_id, property_id, offer_id) -> dict:
    request = session.execute(text("""
        SELECT status::text AS status, last_confirmed_at
          FROM turab.requests WHERE request_id = :r FOR NO KEY UPDATE"""),
        {"r": request_id}).mappings().one()
    prop = session.execute(text("""
        SELECT current_availability::text AS availability, availability_last_confirmed_at
          FROM turab.properties WHERE property_id = :p FOR SHARE"""),
        {"p": property_id}).mappings().one()
    offer = session.execute(text("""
        SELECT status::text AS status, commercial_terms_last_confirmed_at
          FROM turab.property_offers WHERE offer_id = :o FOR SHARE"""),
        {"o": offer_id}).mappings().one()
    session.execute(text("""
        SELECT 1 FROM turab.resource_consent_bindings b
          JOIN turab.consent_grants g ON g.consent_id = b.consent_id
         WHERE b.offer_id = :o OR b.property_id = :p
         ORDER BY b.consent_binding_id
           FOR SHARE OF b, g"""), {"o": offer_id, "p": property_id}).all()
    alias = session.execute(text("""
        SELECT 1 FROM turab.property_identity_aliases WHERE alias_property_id = :p"""),
        {"p": property_id}).first()
    return {"request": request, "property": prop, "offer": offer, "alias": alias is not None}


def _binding_order(binding: Mapping[str, Any]):
    """G5-5: offer-bound before property-bound, then `bound_at`, then id."""
    return (binding["bound_to"] != "OFFER", binding["bound_at"],
            str(binding["consent_binding_id"]))


def check(session: Session, *, match: Mapping[str, Any], offer_id: uuid.UUID,
          clock: Any = None) -> Checked:
    """Lock the facts, read them now, and classify them (§3.7).

    `match` carries `request_id`, `property_id`, `engine` (the match's
    `explanation.engine`) and `threshold_days` (its freshness snapshot's).
    `offer_id` is the offer the opportunity stands on: at approval, the
    evaluated offer.

    The check's instant is read AFTER the locks, so a check that waited on a
    writer judges freshness at the instant it reads the facts. `clock` pins
    it for a test; production passes None (`clock_timestamp()`)."""
    rows = _lock(session, request_id=match["request_id"], property_id=match["property_id"],
                 offer_id=offer_id)
    as_of = session.execute(text(
        "SELECT COALESCE(CAST(:clock AS timestamptz), clock_timestamp())"),
        {"clock": clock}).scalar_one()
    days = match["threshold_days"]
    state = _engine_rule(match, "freshness_state")

    def fresh(confirmed_at, threshold):
        return state.evaluate(confirmed_at, threshold, as_of)["state"]

    # The permission snapshot of this instant, each binding's state derived by
    # the version the match recorded, and that version named.
    permission = snapshots.permission_snapshot(session, offer_id, as_of=as_of)
    binding_rule = _engine_rule(match, "permission_binding_state")
    permission["derived_by"] = match["engine"]["permission_binding_state"]
    for binding in permission["bindings"]:
        binding["state"] = binding_rule.evaluate(snapshots.stored_form(binding),
                                                 permission["offer_party_id"], as_of)
    gate = _engine_rule(match, "permission_gate").evaluate(permission)["status"]
    current = sorted((b for b in permission["bindings"] if b["state"] == "CURRENT"),
                     key=_binding_order)

    facts = {
        "REQUEST_STATUS": rows["request"]["status"],
        "OFFER_STATUS": rows["offer"]["status"],
        "AVAILABILITY": rows["property"]["availability"],
        "IDENTITY": "ALIAS" if rows["alias"] else "CANONICAL",
        "REQUEST_FRESHNESS": fresh(rows["request"]["last_confirmed_at"], days["request"]),
        "PROPERTY_FRESHNESS": fresh(rows["property"]["availability_last_confirmed_at"],
                                    days["property"]),
        "OFFER_FRESHNESS": fresh(rows["offer"]["commercial_terms_last_confirmed_at"],
                                 days["offer_terms"]),
        "PERMISSION": gate,
    }
    return Checked(currency=classify(facts), facts=facts,
                   sharing_scope=permission["permission_scope"],
                   permission_snapshot=permission,
                   current_permission_binding_id=(current[0]["consent_binding_id"]
                                                  if current else None),
                   as_of=as_of)
