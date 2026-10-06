"""The human match review (Slice 5, steps 2 and 3).

Ref: the contract's `postMatchesMatchIdReview` (ADMIN, REVIEWER;
separation-sensitive, INV-2) and `MatchReviewInput`;
`docs/gate/SLICE_5_PLAN.md`: §3.1 (one decision, one row, the review stamp,
[R3-1]), §3.2, §3.3, §3.4, §3.7; G5-2 (a); G5-3 (decided (a) in the review of
29a0f30); G5-4 (a) with [R6-1]; G5-5 (decided (a) in the review of 60b0152);
ADR-01, ADR-08; Developer Spec §15.3, §19.1; API_CONTRACTS §4.8, §4.11.

**What is executed.** REJECTED and NEED_MORE_INFORMATION, with the one
focused task each NEED_MORE_INFORMATION review raises (step 2). APPROVED,
with the one opportunity it creates (step 3). There is no other way to
create an opportunity (H03).

**The order of the checks.** Every refusal comes before any write. The
command runs `prepare` before the idempotency claim (G4-15 D6), so a refused
review writes no review, no task, no opportunity and no audit row, and
consumes no key:
1. the shape of the input, needing no database: 422;
2. the match row, locked `FOR UPDATE` as the first statement on it (§3.1);
3. a match already decided (latest review REJECTED or APPROVED, or an
   opportunity created from it): 409 `MATCH_REVIEW_DECIDED` (G5-3 (a));
4. the reason code against the vocabulary and, for ACTIONABLE_UNKNOWN,
   against the match's stored `next_action` ([R6-1]): 422;
5. APPROVED only, in this order:
   a. the stored gates: eligibility ELIGIBLE and the four gates PASS, else
      409 `MATCH_GATES_NOT_PASS`. The frozen `trg_match_review_gate` refuses
      the same, as an untyped database error; this check names it first;
   b. supersession, per offer (G5-2): a later match of the same request,
      property, policy AND evaluated offer, else 409 `MATCH_SUPERSEDED`;
   c. the currency check (`currency.check`, §3.7), on the facts now, under
      locks: VALID, else 409 `MATCH_CONTEXT_NOT_VALID`, every reason listed;
   d. no open opportunity for the same request and the same canonical
      property, its aliases counted (§3.3): else 409
      `OPPORTUNITY_ALREADY_OPEN`. The currency check's request lock
      serializes approvals on one request, so this read sees every
      opportunity committed before it.

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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .. import exact_json
from ..matching import canonical
from . import audit_rows, currency

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


#: G5-5 (a), the render-derivability rule: the criterion codes whose results
#: may be shown to the customer, by scope. Each reads only fields the
#: customer view renders at that scope. At SUMMARY_ONLY the property is
#: rendered by four fields (id, type, supply mode, location id), so only
#: PROPERTY_TYPE qualifies; LOCATION never does ([R3-5]).
SHOWN_BY_SCOPE: Mapping[str, tuple[str, ...]] = {
    "SUMMARY_ONLY": ("PROPERTY_TYPE",),
    "PROPERTY_DETAILS_ALLOWED": ("PROPERTY_TYPE", "LAND_AREA_MIN", "BUILT_AREA_MIN"),
    "CONTACT_AFTER_CONFIRMATION": ("PROPERTY_TYPE", "LAND_AREA_MIN", "BUILT_AREA_MIN"),
}
#: The pinned rule each shown code must have been evaluated by. A result of
#: another rule or version is not shown: its keys were never checked.
SHOWN_RULES: Mapping[str, tuple[str, str]] = {
    "PROPERTY_TYPE": ("criterion.property_type", "1"),
    "LAND_AREA_MIN": ("criterion.area_min", "2"),
    "BUILT_AREA_MIN": ("criterion.area_min", "2"),
}
WHY_REAL_FORMAT = "turab.why-real/1"
_GATES = ("hard_gate_status", "information_gate_status", "freshness_gate_status",
          "permission_gate_status")


class ReviewRefused(Exception):
    """A typed refusal. `code` is a `ProblemCode` name; the route maps it.
    `field_errors`, when given, are the contract's `Problem.field_errors`
    entries (`field`, `code`, `message`): for a 409 of step 3, the facts that
    failed."""

    code = "VALIDATION_FAILED"

    def __init__(self, code: str, detail: str,
                 field_errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.field_errors = field_errors


@dataclass(frozen=True, slots=True)
class Prepared:
    """What `prepare` decided, under the match lock, for the handler to write."""

    match: Mapping[str, Any]
    decision: str
    reason_code: str | None
    reason_text: str | None
    task_type: str | None
    #: APPROVED only: what the currency check found, under its locks.
    checked: currency.Checked | None = None


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
    row = session.execute(text("""
        SELECT match_id, request_id, property_id, evaluated_offer_id, matching_policy_id,
               evaluated_at, created_at, eligibility::text AS eligibility,
               hard_gate_status::text AS hard_gate_status,
               information_gate_status::text AS information_gate_status,
               freshness_gate_status::text AS freshness_gate_status,
               permission_gate_status::text AS permission_gate_status,
               next_action, (explanation -> 'engine')::text AS engine,
               (freshness_snapshot -> 'threshold_days')::text AS threshold_days
          FROM turab.match_candidates WHERE match_id = :m FOR UPDATE"""),
        {"m": match_id}).mappings().first()
    if row is None:
        return None
    out = dict(row)
    out["engine"] = exact_json.loads(row["engine"]) if row["engine"] else {}
    out["threshold_days"] = ({k: int(v) for k, v in exact_json.loads(
        row["threshold_days"]).items()} if row["threshold_days"] else {})
    return out


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


def _gates_not_pass(match: Mapping[str, Any]) -> list[dict[str, str]]:
    """5a: the stored eligibility and gates, as the frozen
    `enforce_approved_review_gate` reads them."""
    failing = [] if match["eligibility"] == "ELIGIBLE" else [
        {"field": "ELIGIBILITY", "code": match["eligibility"],
         "message": f"eligibility is {match['eligibility']}, not ELIGIBLE"}]
    for gate in _GATES:
        if match[gate] != "PASS":
            name = gate.removesuffix("_status").upper()
            failing.append({"field": name, "code": match[gate],
                            "message": f"{name} is {match[gate]}, not PASS"})
    return failing


def _superseded_by(session: Session, match: Mapping[str, Any]) -> uuid.UUID | None:
    """5b, G5-2: a match of the same request, property, policy AND evaluated
    offer, strictly later on (`evaluated_at`, `created_at`). A tie on both is
    not supersession, and `match_id` is never a tie-break."""
    return session.execute(text("""
        SELECT match_id FROM turab.match_candidates
         WHERE request_id = :r AND property_id = :p AND matching_policy_id = :pol
           AND evaluated_offer_id IS NOT DISTINCT FROM :o
           AND (evaluated_at, created_at) > (:ea, :ca)
         ORDER BY evaluated_at DESC, created_at DESC, match_id
         LIMIT 1"""),
        {"r": match["request_id"], "p": match["property_id"],
         "pol": match["matching_policy_id"], "o": match["evaluated_offer_id"],
         "ea": match["evaluated_at"], "ca": match["created_at"]}).scalar_one_or_none()


def _open_opportunity(session: Session, match: Mapping[str, Any]) -> uuid.UUID | None:
    """5d, §3.3: an open opportunity of the request on the property or on any
    alias of it. The property is canonical here: 5c refused an alias."""
    return session.execute(text("""
        SELECT opportunity_id FROM turab.opportunities
         WHERE request_id = :r AND status <> 'CLOSED'
           AND (property_id = :p
                OR property_id IN (SELECT alias_property_id
                                     FROM turab.property_identity_aliases
                                    WHERE canonical_property_id = :p))
         ORDER BY created_at, opportunity_id LIMIT 1"""),
        {"r": match["request_id"], "p": match["property_id"]}).scalar_one_or_none()


def _approval(session: Session, match: Mapping[str, Any], clock: Any) -> currency.Checked:
    """5a–5d, in order, under the match lock. Returns the currency check's
    result for `record` to write from."""
    failing = _gates_not_pass(match)
    if failing:
        raise ReviewRefused("MATCH_GATES_NOT_PASS",
                            "this match was not evaluated ELIGIBLE with all four gates PASS; "
                            "it cannot be approved", failing)
    newer = _superseded_by(session, match)
    if newer is not None:
        raise ReviewRefused("MATCH_SUPERSEDED",
                            f"a later evaluation of the same offer exists: match {newer}; "
                            "review that match")
    checked = currency.check(session, match=match, offer_id=match["evaluated_offer_id"],
                             clock=clock)
    if checked.currency.validity != currency.VALID:
        raise ReviewRefused(
            "MATCH_CONTEXT_NOT_VALID",
            f"the facts now are {checked.currency.validity}, not VALID; reconfirm them or run "
            "the matching again",
            [{"field": r["fact"], "code": r["reason_code"] or r["value"],
              "message": f"{r['fact']} is {r['value']}: {r['class']}"}
             for r in checked.currency.reasons])
    already = _open_opportunity(session, match)
    if already is not None:
        raise ReviewRefused("OPPORTUNITY_ALREADY_OPEN",
                            f"opportunity {already} is open for this request and this "
                            "property; one open opportunity per request and property")
    return checked


def prepare(session: Session, *, match_id: uuid.UUID, decision: str,
            reason_code: str | None, reason_text: str | None,
            clock: Any = None) -> Prepared:
    """Steps 1–5, read-only, before the idempotency claim. `clock` is the
    approval's instant: NULL in production (`clock_timestamp()`)."""
    check_shape(decision, reason_code)
    match = _lock_match(session, match_id)
    if match is None:
        # The route checked existence first, and a match is never deleted;
        # this is the same answer, kept in case it is reached.
        raise ReviewRefused("OBJECT_NOT_AUTHORIZED", "not an available match")
    if _decided(session, match_id):
        raise ReviewRefused("MATCH_REVIEW_DECIDED",
                            "this match has a final review; a later review is refused")
    task_type = checked = None
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
        checked = _approval(session, match, clock)
    return Prepared(match=match, decision=decision, reason_code=reason_code,
                    reason_text=reason_text, task_type=task_type, checked=checked)


def stamp(session: Session, match_id: uuid.UUID, clock: Any = None):
    """§3.1: strictly above every earlier stamp of the match."""
    return session.execute(text(STAMP_SQL), {"clock": clock, "m": match_id}).scalar_one()


def record(session: Session, prepared: Prepared, *, reviewer_account_id: uuid.UUID,
           clock: Any = None) -> dict[str, Any]:
    """The writes, after the claim: ONE review row; for NMI ONE task; for
    APPROVED ONE opportunity, written after the review it requires."""
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
    task = opportunity = None
    if prepared.decision == "NEED_MORE_INFORMATION":
        task = _raise_task(session, prepared, review_id)
    elif prepared.decision == "APPROVED":
        opportunity = _create_opportunity(session, prepared, reviewer_account_id)
    return {"match_id": str(match["match_id"]), "decision": prepared.decision,
            "opportunity": opportunity, "task": task}


# --- APPROVED: the opportunity (G5-5 (a)) -----------------------------------------

def shown_content(results: list[Mapping[str, Any]], scope: str) -> tuple[dict, list]:
    """`why_real` and `known_differences` (G5-5 (a)), from the match's criterion
    results. Pure. Only shown codes, evaluated by their pinned rule:
    - `why_real.criteria`: REQUIRED or PREFERRED, PASS; code, Arabic label,
      importance;
    - `known_differences`: PREFERRED or FLEXIBLE, FAIL or a non-blocking
      UNKNOWN; code and compatibility.

    No value, delta, evidence, claim, rule or score is written: both fields
    are rendered to the customer (§3.4). What is shown depends only on the
    criteria, the scope and the shown results, never on whether a claim
    exists."""
    shown = set(SHOWN_BY_SCOPE[scope])
    eligible = [r for r in results if r["criterion_code"] in shown
                and (r["rule_id"], r["rule_version"]) == SHOWN_RULES[r["criterion_code"]]]
    why = [{"code": r["criterion_code"], "label_ar": r["label_ar"],
            "importance": r["importance"]}
           for r in eligible
           if r["importance"] in ("REQUIRED", "PREFERRED") and r["compatibility"] == "PASS"]
    differences = [{"code": r["criterion_code"], "compatibility": r["compatibility"]}
                   for r in eligible
                   if r["importance"] in ("PREFERRED", "FLEXIBLE")
                   and (r["compatibility"] == "FAIL"
                        or (r["compatibility"] == "UNKNOWN" and not r["blocking"]))]
    return {"format": WHY_REAL_FORMAT, "criteria": why}, differences


def _criterion_results(session: Session, match_id: uuid.UUID) -> list[dict]:
    return [dict(r) for r in session.execute(text("""
        SELECT r.criterion_code, r.ordinal, r.importance::text AS importance,
               r.compatibility::text AS compatibility, r.blocking, r.rule_id, r.rule_version,
               d.label_ar
          FROM turab.match_criterion_results r
          LEFT JOIN turab.criterion_definitions d ON d.code = r.criterion_code
         WHERE r.match_id = :m
         ORDER BY r.criterion_code, r.ordinal"""), {"m": match_id}).mappings()]


_OPPORTUNITY_COLUMNS = """
    opportunity_id, request_id, property_id, approved_match_id,
    status::text AS status, validity_status::text AS validity_status,
    sharing_scope::text AS sharing_scope, why_real::text AS why_real,
    known_differences::text AS known_differences, created_at, shared_at, engaged_at,
    last_confirmed_at, last_activity_at, closed_at, close_reason_code, current_offer_id,
    current_permission_binding_id,
    commercial_context_snapshot::text AS commercial_context_snapshot,
    permission_snapshot::text AS permission_snapshot"""


def _create_opportunity(session: Session, prepared: Prepared,
                        reviewer_account_id: uuid.UUID) -> dict[str, Any]:
    """The one opportunity of an APPROVED review, after the review row (the
    frozen gate reads the latest review). G5-5 (a):
    - `sharing_scope`: the evaluated offer's `permission_scope` now, recorded
      in the permission snapshot of the approval;
    - `commercial_context_snapshot`: the match's, copied in SQL, so it is the
      stored bytes (mandatory test 4); `current_offer_id`: the evaluated offer;
    - `current_permission_binding_id`: the first CURRENT binding, offer-bound
      before property-bound, then `bound_at`, then id;
    - NEW and VALID (the birth rule), `last_confirmed_at` the approval's
      instant, `created_by_account_id` the reviewer.

    The audit row is the frozen `audit_opportunities` trigger's. A unique
    violation can only come from a writer outside this service; it maps to the
    same typed refusals."""
    checked = prepared.checked
    why_real, differences = shown_content(
        _criterion_results(session, prepared.match["match_id"]), checked.sharing_scope)
    try:
        row = session.execute(text(f"""
            INSERT INTO turab.opportunities
                   (request_id, property_id, approved_match_id, current_offer_id,
                    current_permission_binding_id, commercial_context_snapshot,
                    permission_snapshot, sharing_scope, why_real, known_differences,
                    created_by_account_id, last_confirmed_at)
            SELECT m.request_id, m.property_id, m.match_id, m.evaluated_offer_id, :binding,
                   m.commercial_context_snapshot, CAST(:permission AS jsonb),
                   CAST(:scope AS turab.sharing_scope), CAST(:why AS jsonb),
                   CAST(:differences AS jsonb), :acct, :as_of
              FROM turab.match_candidates m WHERE m.match_id = :m
            RETURNING {_OPPORTUNITY_COLUMNS}"""),
            {"m": prepared.match["match_id"],
             "binding": checked.current_permission_binding_id,
             "permission": canonical.canonical_bytes(checked.permission_snapshot).decode(),
             "scope": checked.sharing_scope,
             "why": canonical.canonical_bytes(why_real).decode(),
             "differences": canonical.canonical_bytes(differences).decode(),
             "acct": reviewer_account_id, "as_of": checked.as_of}).mappings().one()
    except IntegrityError as exc:
        name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if name == "ux_one_open_opportunity_per_pair":
            raise ReviewRefused("OPPORTUNITY_ALREADY_OPEN",
                                "an opportunity is open for this request and this "
                                "property") from exc
        if name == "opportunities_approved_match_id_key":
            raise ReviewRefused("MATCH_REVIEW_DECIDED",
                                "an opportunity was already created from this match") from exc
        raise
    return opportunity_view(row)


def opportunity_view(row: Mapping[str, Any]) -> dict[str, Any]:
    """The contract's `InternalOpportunityView`, key for key (staff only;
    R9.2: the snapshots and `approved_match_id` are never a customer's)."""
    def _id(value):
        return None if value is None else str(value)

    def _at(value):
        return None if value is None else value.isoformat()
    return {"opportunity_id": str(row["opportunity_id"]),
            "request_id": str(row["request_id"]), "property_id": str(row["property_id"]),
            "approved_match_id": str(row["approved_match_id"]), "status": row["status"],
            "validity_status": row["validity_status"], "sharing_scope": row["sharing_scope"],
            "why_real": exact_json.loads(row["why_real"]),
            "known_differences": exact_json.loads(row["known_differences"]),
            "created_at": _at(row["created_at"]), "shared_at": _at(row["shared_at"]),
            "engaged_at": _at(row["engaged_at"]),
            "last_confirmed_at": _at(row["last_confirmed_at"]),
            "last_activity_at": _at(row["last_activity_at"]),
            "closed_at": _at(row["closed_at"]), "close_reason_code": row["close_reason_code"],
            "current_offer_id": _id(row["current_offer_id"]),
            "current_permission_binding_id": _id(row["current_permission_binding_id"]),
            "commercial_context_snapshot": exact_json.loads(row["commercial_context_snapshot"]),
            "permission_snapshot": exact_json.loads(row["permission_snapshot"])}


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
