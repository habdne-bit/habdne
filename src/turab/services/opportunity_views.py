"""The opportunity reads and the match queue (Slice 5, step 4).

Ref: `docs/gate/SLICE_5_PLAN.md`: §3.4, §3.6; G5-5 (a) with [R4-2] (decided
in the review of 60b0152); G5-6 (a) (the frozen contract first; SUMMARY_ONLY
renders four property fields, decided in the review of 60b0152); G5-7 (a);
G5-11; RFC-001 R8.2, R8.2a, R9.2, R6.3 and Appendix B; API_CONTRACTS §5.

**Three reads, three audiences.**
- `internal_view`: the staff `InternalOpportunityView`, the stored row as it
  is (snapshots, `approved_match_id`, the stored `why_real`).
- `customer_view`: the frozen `CustomerOpportunityView`, key for key. It
  carries no `contact`, and no offer term, because the frozen type has no
  field for either (F5-1, F5-2; Appendix B). Its `property` is the frozen
  `CustomerPropertyView`: four fields at SUMMARY_ONLY, every field above it.
- `match_queue`: the staff `QueuePage` of matches awaiting a decision.

**[R4-2] The withholding, at render time.** A `why_real` or
`known_differences` entry states a result computed from the match's
`property_snapshot`. The customer response renders the property's CURRENT
row. When the field an entry's rule read now differs from the snapshot's
value, the entry is dropped from that response. The comparison is on the
value, exactly, not on the outcome. The stored row is never touched.

**Exact numbers.** Areas are `numeric` and are rendered by their own digits
(`exact_json`), never through a float.
"""
from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import exact_json
from ..dto.boundaries import render_opportunity_for_scope
from . import match_review

#: The property field each shown code's pinned rule reads ([R4-2]; the keys
#: test of step 3 proves each rule reads exactly this one field).
FIELD_OF: Mapping[str, str] = {
    "PROPERTY_TYPE": "property_type",
    "LAND_AREA_MIN": "land_area_m2",
    "BUILT_AREA_MIN": "built_area_m2",
}


def _text(value: Any) -> Any:
    """A JSON value for `exact_json`: ids and times as strings, numbers
    exact."""
    if value is None or isinstance(value, (str, bool, int, Decimal)):
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    if hasattr(value, "isoformat"):
        return value.isoformat()
    raise TypeError(f"{type(value).__name__} is not rendered")


def _value(field: str, value: Any) -> Any:
    """One comparable value: the type as text, an area as an exact `Decimal`
    (so 137.5 and 137.50 are one value, and 137.5 and 150 are two)."""
    if value is None:
        return None
    return str(value) if field == "property_type" else Decimal(str(value))


def withheld(entries: list[Mapping[str, Any]], scope: str, *, snapshot: Mapping[str, Any],
             current: Mapping[str, Any]) -> list[dict]:
    """[R4-2], pure. Keep an entry only when its code is shown at `scope`
    (G5-5 (a); any other code fails closed) AND its field's current value
    equals the snapshot's, null included: an area unknown at evaluation and
    still unknown now is the same value, so its UNKNOWN difference stays; a
    null on one side only is a change, and withholds the entry."""
    shown = set(match_review.SHOWN_BY_SCOPE[scope])
    kept = []
    for entry in entries:
        code = entry.get("code")
        field = FIELD_OF.get(code)
        if code not in shown or field is None:
            continue
        then, now = _value(field, snapshot.get(field)), _value(field, current.get(field))
        if then != now:
            continue
        kept.append(dict(entry))
    return kept


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {k: _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    return _text(value)


def customer_view(session: Session, opportunity_id: uuid.UUID) -> dict[str, Any]:
    """The frozen `CustomerOpportunityView` of a shared opportunity the caller
    is authorized for (the loader decided both). Read on the READ session."""
    row = session.execute(text("""
        SELECT o.opportunity_id, o.status::text AS status,
               o.validity_status::text AS validity_status,
               o.sharing_scope::text AS sharing_scope, o.why_real::text AS why_real,
               o.known_differences::text AS known_differences, o.created_at, o.shared_at,
               o.property_id, (m.property_snapshot)::text AS snapshot
          FROM turab.opportunities o
          JOIN turab.match_candidates m ON m.match_id = o.approved_match_id
         WHERE o.opportunity_id = :o"""), {"o": opportunity_id}).mappings().one()
    prop = session.execute(text("""
        SELECT property_id, property_type::text AS property_type, canonical_location_id,
               local_location_detail, land_area_m2, built_area_m2,
               current_availability::text AS current_availability,
               availability_last_confirmed_at, supply_mode::text AS supply_mode, version
          FROM turab.properties WHERE property_id = :p"""),
        {"p": row["property_id"]}).mappings().one()
    scope = row["sharing_scope"]
    snapshot = exact_json.loads(row["snapshot"])
    why_real = exact_json.loads(row["why_real"])
    criteria = why_real.get("criteria", []) if isinstance(why_real, dict) else []
    rendered_why = {**{k: v for k, v in why_real.items() if k != "criteria"},
                    "criteria": withheld(criteria, scope, snapshot=snapshot, current=prop)}
    differences = withheld(exact_json.loads(row["known_differences"]), scope,
                           snapshot=snapshot, current=prop)
    view = render_opportunity_for_scope(
        {**row, "why_real": rendered_why, "known_differences": differences},
        property_row=prop)
    return _jsonable(view.model_dump())


def internal_view(session: Session, opportunity_id: uuid.UUID) -> dict[str, Any] | None:
    """The staff `InternalOpportunityView`: the stored row, unfiltered."""
    row = session.execute(text(
        f"SELECT {match_review._OPPORTUNITY_COLUMNS} FROM turab.opportunities "
        "WHERE opportunity_id = :o"), {"o": opportunity_id}).mappings().first()
    return None if row is None else match_review.opportunity_view(row)


# --- the match queue (G5-11) ------------------------------------------------------------

#: The membership of G5-11, every condition on a stored column:
#: - not superseded, per offer (G5-2): no later match of the same request,
#:   property, policy and evaluated offer; a strict tie keeps both;
#: - the property canonical now (an alias's matches are Slice 3's
#:   RESOLVE_IDENTITY work);
#: - eligibility other than REJECTED;
#: - no opportunity created from it;
#: - its latest review absent or NEED_MORE_INFORMATION.
MATCH_QUEUE = """
    SELECT m.match_id, m.created_at, m.evaluated_at, m.request_id, m.property_id,
           m.evaluated_offer_id, m.eligibility::text AS eligibility,
           (m.explanation -> 'reasons' -> 0)::text AS first_reason,
           latest.decision AS latest_review
      FROM turab.match_candidates m
      LEFT JOIN LATERAL (
            SELECT r.decision::text AS decision FROM turab.match_reviews r
             WHERE r.match_id = m.match_id
             ORDER BY r.reviewed_at DESC, r.match_review_id DESC LIMIT 1) latest ON true
     WHERE m.eligibility <> 'REJECTED'
       AND (latest.decision IS NULL OR latest.decision = 'NEED_MORE_INFORMATION')
       AND NOT EXISTS (SELECT 1 FROM turab.opportunities o
                        WHERE o.approved_match_id = m.match_id)
       AND NOT EXISTS (SELECT 1 FROM turab.property_identity_aliases a
                        WHERE a.alias_property_id = m.property_id)
       AND NOT EXISTS (SELECT 1 FROM turab.match_candidates n
                        WHERE n.request_id = m.request_id AND n.property_id = m.property_id
                          AND n.matching_policy_id = m.matching_policy_id
                          AND n.evaluated_offer_id IS NOT DISTINCT FROM m.evaluated_offer_id
                          AND (n.evaluated_at, n.created_at) > (m.evaluated_at, m.created_at))
"""
PRIORITY_ORDER = {"HIGH": 0, "NORMAL": 1}


def match_queue(session: Session) -> list[dict[str, Any]]:
    """The queue's items, ordered by priority, then `evaluated_at`, then
    `match_id`."""
    items = [(queue_item(row), row) for row in session.execute(text(MATCH_QUEUE)).mappings()]
    items.sort(key=lambda pair: (PRIORITY_ORDER[pair[0]["priority"]],
                                 pair[1]["evaluated_at"], str(pair[1]["match_id"])))
    return [item for item, _ in items]


def queue_item(row: Mapping[str, Any]) -> dict[str, Any]:
    """`QueueItem` (open), G5-11:
    - ELIGIBLE: HIGH, `READY_FOR_REVIEW`; `AWAITING_INFORMATION` when its
      latest review is NEED_MORE_INFORMATION;
    - NEEDS_CONFIRMATION, NEED_MORE_INFORMATION: NORMAL, the match's first
      reason, by its seeded code, or by its basis where it has no code
      (a freshness never confirmed).
    `created_at` is the match's own creation time."""
    if row["eligibility"] == "ELIGIBLE":
        priority = "HIGH"
        reason = ("AWAITING_INFORMATION" if row["latest_review"] == "NEED_MORE_INFORMATION"
                  else "READY_FOR_REVIEW")
    else:
        priority = "NORMAL"
        first = exact_json.loads(row["first_reason"]) if row["first_reason"] else {}
        reason = first.get("reason_code") or first.get("basis")
    return {"id": str(row["match_id"]), "kind": "MATCH", "priority": priority,
            "created_at": row["created_at"].isoformat(), "reason": reason,
            "request_id": str(row["request_id"]), "property_id": str(row["property_id"]),
            "eligibility": row["eligibility"]}


# --- the opportunity queue (G5-11 (a)) ----------------------------------------------------

#: G5-11 (a), direction accepted in the review of `288bfdb`: no time-based
#: membership. Open opportunities that are INVALID, NEEDS_CONFIRMATION, or
#: VALID and not yet shared (NEW: `0006` rule 5 keeps `shared_at` null
#: exactly while NEW). Every condition reads a stored column; no engine call
#: per row.
OPPORTUNITY_QUEUE = """
    SELECT opportunity_id, created_at, request_id, property_id, status::text AS status,
           validity_status::text AS validity_status
      FROM turab.opportunities
     WHERE status <> 'CLOSED'
       AND (validity_status <> 'VALID' OR status = 'NEW')
"""
#: G5-11 (a)'s table, as proposed: (priority, reason) by case.
OPPORTUNITY_CASES: Mapping[str, tuple[str, str]] = {
    "INVALID": ("HIGH", "VALIDITY_INVALID"),
    "NEEDS_CONFIRMATION": ("NORMAL", "VALIDITY_NEEDS_CONFIRMATION"),
    "NOT_YET_SHARED": ("NORMAL", "NOT_YET_SHARED"),
}


def opportunity_queue(session: Session) -> list[dict[str, Any]]:
    """The queue's items, ordered by priority, then `created_at`, then
    `opportunity_id` (the match queue's order, on the opportunity's own
    creation time)."""
    items = [(opportunity_queue_item(row), row)
             for row in session.execute(text(OPPORTUNITY_QUEUE)).mappings()]
    items.sort(key=lambda pair: (PRIORITY_ORDER[pair[0]["priority"]],
                                 pair[1]["created_at"], str(pair[1]["opportunity_id"])))
    return [item for item, _ in items]


def opportunity_queue_item(row: Mapping[str, Any]) -> dict[str, Any]:
    """`QueueItem` (open), G5-11 (a): the validity decides first, so an
    unshared INVALID opportunity is HIGH, `VALIDITY_INVALID`."""
    case = (row["validity_status"] if row["validity_status"] != "VALID"
            else "NOT_YET_SHARED")
    priority, reason = OPPORTUNITY_CASES[case]
    return {"id": str(row["opportunity_id"]), "kind": "OPPORTUNITY", "priority": priority,
            "created_at": row["created_at"].isoformat(), "reason": reason,
            "request_id": str(row["request_id"]), "property_id": str(row["property_id"]),
            "status": row["status"], "validity_status": row["validity_status"]}
