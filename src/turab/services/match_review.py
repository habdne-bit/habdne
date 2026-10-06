"""The human match review (Slice 5, step 2).

Ref: the contract's `postMatchesMatchIdReview` (ADMIN, REVIEWER;
separation-sensitive, INV-2) and `MatchReviewInput`;
`docs/gate/SLICE_5_PLAN.md` revision 6: §3.1 (one decision, one row, the
review stamp, [R3-1]), §3.2, G5-3 (decided (a) in the review of 29a0f30),
G5-4 (a) with [R6-1]; ADR-08; Developer Spec §19.1; API_CONTRACTS §4.8.

**What step 2 executes.** REJECTED and NEED_MORE_INFORMATION, and the one
focused task each NEED_MORE_INFORMATION review raises. APPROVED is a valid
decision in the contract, but its execution (the currency check, the
opportunity) is step 3. Until then it is refused with its own typed code,
`REVIEW_DECISION_NOT_YET_AVAILABLE`, and writes nothing. It is never reported
as a gate failure (review of 29a0f30).

**The order of the checks.** Every refusal comes before any write. The
command runs `prepare` before the idempotency claim (G4-15 D6), so a refused
review writes no review, no task and no audit row, and consumes no key:
1. the shape of the input, needing no database: 422;
2. the match row, locked `FOR UPDATE` as the first statement on it (§3.1);
3. a match already decided (latest review REJECTED or APPROVED, or an
   opportunity created from it): 409 `MATCH_REVIEW_DECIDED` (G5-3 (a));
4. the reason code against the vocabulary and, for ACTIONABLE_UNKNOWN,
   against the match's stored `next_action` ([R6-1]): 422;
5. APPROVED: 409 `REVIEW_DECISION_NOT_YET_AVAILABLE` (step 2 only).

**The review stamp (§3.1, [R3-1]).** Under the lock, one statement computes
`GREATEST(clock, max(reviewed_at) + 1 µs)` over the match's reviews. The
stamps of one match therefore increase strictly in the order the decisions
were taken, and the schema's "latest review" ordering never reaches the
random `match_review_id`. `clock` is a bound parameter: production binds
NULL and the statement reads `clock_timestamp()`; a test binds a fixed value
to reach the equal-reading case.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import exact_json
from . import audit_rows

DECISIONS = ("APPROVED", "REJECTED", "NEED_MORE_INFORMATION")
#: Final for the match: a later review is refused (G5-3 (a)). The same rule
#: Slice 3's `_OPEN_MATCHES` applies to call a match open or closed.
FINAL = frozenset({"REJECTED", "APPROVED"})
#: REJECTED takes a reason of these categories, or `OTHER` (G5-3).
REJECT_CATEGORIES = ("MATCH", "FRESHNESS", "PERMISSION")
REJECT_OTHER = "OTHER"

#: G5-4: the task a NEED_MORE_INFORMATION reason raises. Any other reason is
#: refused for NMI, `OTHER` included (Spec §19.1: no unspecific task).
NMI_TASK_TYPES: Mapping[str, str] = {
    "DOCUMENT_NOT_KNOWN": "VERIFY_DOCUMENT",
    "DOCUMENT_MISMATCH": "VERIFY_DOCUMENT",
    "PRICE_NOT_KNOWN": "CONFIRM_PRICE",
    "PRICE_NEGOTIATION_UNCONFIRMED": "CONFIRM_PRICE",
    "OFFER_STALE": "CONFIRM_PRICE",
    "REQUEST_STALE": "RECONFIRM_REQUEST",
    "PROPERTY_STALE": "RECONFIRM_PROPERTY",
    "PERMISSION_MISSING": "CONFIRM_PERMISSION",
    "CONSENT_REVOKED": "CONFIRM_PERMISSION",
}
#: [R6-1]: the reason whose task type is the match's stored `next_action`.
ACTIONABLE_UNKNOWN = "ACTIONABLE_UNKNOWN"
#: The types of `action.next@1` that name specific work. Its sixth type,
#: `OTHER`, does not, and a null `next_action` names nothing ([R6-1]).
SPECIFIC_NEXT_ACTION_TYPES = frozenset({
    "VERIFY_DOCUMENT", "CONFIRM_PRICE", "RECONFIRM_REQUEST", "RECONFIRM_PROPERTY",
    "CONFIRM_PERMISSION"})

#: A fixed title per task type, never the reviewer's free text (G5-4).
TASK_TITLES: Mapping[str, str] = {
    "VERIFY_DOCUMENT": "Verify the property's document",
    "CONFIRM_PRICE": "Confirm the offer's price terms",
    "RECONFIRM_REQUEST": "Reconfirm the request",
    "RECONFIRM_PROPERTY": "Reconfirm the property",
    "CONFIRM_PERMISSION": "Confirm the permission to share",
}

#: The stamp statement of §3.1, verbatim. `:clock` is NULL in production.
STAMP_SQL = """
    SELECT GREATEST(COALESCE(CAST(:clock AS timestamptz), clock_timestamp()),
                    max(reviewed_at) + interval '1 microsecond')
      FROM turab.match_reviews WHERE match_id = :m"""


class ReviewRefused(Exception):
    """A typed refusal. `code` is a `ProblemCode` name; the route maps it."""

    code = "VALIDATION_FAILED"

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


@dataclass(frozen=True, slots=True)
class Prepared:
    """What `prepare` decided, under the match lock, for the handler to write."""

    match: Mapping[str, Any]
    decision: str
    reason_code: str | None
    reason_text: str | None
    task_type: str | None


def check_shape(decision: str, reason_code: str | None) -> None:
    """Step 1: the rules that need no database (G5-3, Spec §19.1)."""
    if decision not in DECISIONS:
        raise ReviewRefused("VALIDATION_FAILED", f"decision must be one of {list(DECISIONS)}")
    if decision == "APPROVED":
        if reason_code is not None:
            raise ReviewRefused("REVIEW_REASON_NOT_ALLOWED",
                                "APPROVED takes no reason_code")
    elif reason_code is None:
        raise ReviewRefused("REVIEW_REASON_REQUIRED",
                            f"{decision} requires a reason_code")


def _lock_match(session: Session, match_id: uuid.UUID) -> Mapping[str, Any] | None:
    """Step 2. The FIRST statement on the match (§3.1). A second review of the
    same match waits here until the first commits; under Read Committed its
    later statements then see the first's review."""
    return session.execute(text("""
        SELECT match_id, request_id, property_id, eligibility::text AS eligibility,
               next_action
          FROM turab.match_candidates WHERE match_id = :m FOR UPDATE"""),
        {"m": match_id}).mappings().first()


def _decided(session: Session, match_id: uuid.UUID) -> bool:
    """Step 3. The latest review, in the order the schema itself uses
    (`latest_match_reviews`, `enforce_opportunity_gate`), or an opportunity."""
    latest = session.execute(text("""
        SELECT decision::text FROM turab.match_reviews WHERE match_id = :m
         ORDER BY reviewed_at DESC, match_review_id DESC LIMIT 1"""),
        {"m": match_id}).scalar_one_or_none()
    if latest in FINAL:
        return True
    return session.execute(text(
        "SELECT EXISTS (SELECT 1 FROM turab.opportunities WHERE approved_match_id = :m)"),
        {"m": match_id}).scalar_one()


def _reason(session: Session, code: str) -> Mapping[str, Any] | None:
    return session.execute(text("""
        SELECT code, category FROM turab.reason_codes WHERE code = :c AND active"""),
        {"c": code}).mappings().first()


def task_type_for(reason_code: str, next_action: Mapping[str, Any] | None) -> str:
    """G5-4 with [R6-1]: the specific task an NMI reason raises, or a refusal.
    Pure, so the mapping is tested without PostgreSQL."""
    if reason_code == ACTIONABLE_UNKNOWN:
        kind = (next_action or {}).get("type")
        if kind not in SPECIFIC_NEXT_ACTION_TYPES:
            raise ReviewRefused(
                "REVIEW_REASON_NOT_ALLOWED",
                "ACTIONABLE_UNKNOWN names no specific task for this match: its "
                "recorded next action is absent or unspecific; give the reason "
                "that names the missing information")
        return kind
    if reason_code not in NMI_TASK_TYPES:
        raise ReviewRefused(
            "REVIEW_REASON_NOT_ALLOWED",
            "NEED_MORE_INFORMATION takes a reason that names a specific task")
    return NMI_TASK_TYPES[reason_code]


def prepare(session: Session, *, match_id: uuid.UUID, decision: str,
            reason_code: str | None, reason_text: str | None) -> Prepared:
    """Steps 1–5, read-only, before the idempotency claim."""
    check_shape(decision, reason_code)
    match = _lock_match(session, match_id)
    if match is None:
        # The route checked existence first, and a match is never deleted;
        # this is the same answer, kept in case it is reached.
        raise ReviewRefused("OBJECT_NOT_AUTHORIZED", "not an available match")
    if _decided(session, match_id):
        raise ReviewRefused("MATCH_REVIEW_DECIDED",
                            "this match has a final review; a later review is refused")
    task_type = None
    if decision != "APPROVED":
        reason = _reason(session, reason_code)
        if decision == "REJECTED":
            if reason is None or not (reason["category"] in REJECT_CATEGORIES
                                      or reason["code"] == REJECT_OTHER):
                raise ReviewRefused(
                    "REVIEW_REASON_NOT_ALLOWED",
                    "REJECTED takes an active reason of category MATCH, FRESHNESS "
                    "or PERMISSION, or OTHER")
        else:
            if reason is None:
                raise ReviewRefused("REVIEW_REASON_NOT_ALLOWED",
                                    "the reason_code is not an active reason")
            task_type = task_type_for(reason_code, match["next_action"])
    else:
        raise ReviewRefused(
            "REVIEW_DECISION_NOT_YET_AVAILABLE",
            "APPROVED is a valid decision; its execution (the currency check and "
            "the opportunity) is delivered in Slice 5 step 3. Nothing was recorded")
    return Prepared(match=match, decision=decision, reason_code=reason_code,
                    reason_text=reason_text, task_type=task_type)


def stamp(session: Session, match_id: uuid.UUID, clock: Any = None):
    """§3.1: strictly above every earlier stamp of the match."""
    return session.execute(text(STAMP_SQL), {"clock": clock, "m": match_id}).scalar_one()


def record(session: Session, prepared: Prepared, *, reviewer_account_id: uuid.UUID,
           clock: Any = None) -> dict[str, Any]:
    """The writes, after the claim: ONE review row, and for NMI ONE task."""
    match = prepared.match
    reviewed_at = stamp(session, match["match_id"], clock)
    review_id = session.execute(text("""
        INSERT INTO turab.match_reviews (match_id, decision, reason_code, reason_text,
                                         reviewer_account_id, reviewed_at)
        VALUES (:m, CAST(:d AS turab.match_review_decision), :r, :t, :acct, :at)
        RETURNING match_review_id"""),
        {"m": match["match_id"], "d": prepared.decision, "r": prepared.reason_code,
         "t": prepared.reason_text, "acct": reviewer_account_id,
         "at": reviewed_at}).scalar_one()
    task = None
    if prepared.decision == "NEED_MORE_INFORMATION":
        task = _raise_task(session, prepared, review_id)
    return {"match_id": str(match["match_id"]), "decision": prepared.decision,
            "opportunity": None, "task": task}


def _blocking_unknown(session: Session, match_id: uuid.UUID) -> bool:
    return session.execute(text("""
        SELECT EXISTS (SELECT 1 FROM turab.match_criterion_results
                        WHERE match_id = :m AND blocking AND compatibility = 'UNKNOWN')"""),
        {"m": match_id}).scalar_one()


def _raise_task(session: Session, prepared: Prepared,
                review_id: uuid.UUID) -> dict[str, Any]:
    """G5-4 (a): one NEW task per NMI review, never reused. The link is
    `payload.match_review_id`, written once here (measurement J: no column
    names a review). Priority HIGH when the match has a blocking unknown
    (Spec §13, as `action.next@1` applies it), NORMAL otherwise."""
    match = prepared.match
    priority = "HIGH" if _blocking_unknown(session, match["match_id"]) else "NORMAL"
    payload = {"match_review_id": str(review_id), "next_action": match["next_action"]}
    row = session.execute(text("""
        INSERT INTO turab.tasks (task_type, priority, title, reason_code, request_id,
                                 property_id, match_id, payload)
        VALUES (CAST(:type AS turab.task_type), CAST(:prio AS turab.task_priority),
                :title, :r, :req, :prop, :m, CAST(:p AS jsonb))
        RETURNING task_id, task_type::text AS task_type, priority::text AS priority,
                  status::text AS status, title, reason_code, party_id, request_id,
                  property_id, match_id, due_at, payload::text AS payload"""),
        {"type": prepared.task_type, "prio": priority,
         "title": TASK_TITLES[prepared.task_type], "r": prepared.reason_code,
         "req": match["request_id"], "prop": match["property_id"], "m": match["match_id"],
         "p": exact_json.dumps(payload)}).mappings().one()
    audit_rows.write(session, "tasks", row["task_id"], "INSERT", None,
                     audit_rows.row_json(session, "tasks", row["task_id"]))
    return task_view(row)


def task_view(row: Mapping[str, Any]) -> dict[str, Any]:
    """The contract's `Task`, key for key."""
    def _id(value):
        return None if value is None else str(value)
    return {"task_id": str(row["task_id"]), "task_type": row["task_type"],
            "priority": row["priority"], "status": row["status"], "title": row["title"],
            "reason_code": row["reason_code"], "party_id": _id(row["party_id"]),
            "request_id": _id(row["request_id"]), "property_id": _id(row["property_id"]),
            "match_id": _id(row["match_id"]),
            "due_at": None if row["due_at"] is None else row["due_at"].isoformat(),
            "payload": exact_json.loads(row["payload"])}
