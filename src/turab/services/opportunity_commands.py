"""The opportunity commands (Slice 5, step 5): revalidate, share, close.

Ref: the contract's `postOpportunitiesOpportunityIdRevalidate` (ADMIN,
OPERATOR, REVIEWER), `postOpportunitiesOpportunityIdShare` (ADMIN, OPERATOR;
separation-sensitive, INV-2) and `postOpportunitiesOpportunityIdClose`
(ADMIN, OPERATOR, REVIEWER; `CloseCommand`); `docs/gate/SLICE_5_PLAN.md`:
§3.7 [R3-2], G5-8 (direction accepted in the review of `288bfdb`), G5-9,
G5-10 (decided in the review of `d0e0bc9`), G5-12 (B10); API_CONTRACTS §4.11;
RFC-001 R8.4.

**One currency check, three users (§3.7).** `currency.check` decides
validity, and nothing else does:
- `revalidate` is the ONLY command that persists its result
  (`validity_status`, `last_activity_at`, `last_confirmed_at` when VALID,
  `current_permission_binding_id`);
- `share` requires it, and never persists it.

**The order of the checks.** Each command locks the opportunity row
`FOR UPDATE` as its first statement on it, so two commands on one
opportunity serialize. Every refusal is decided in `prepare`, before the
idempotency claim (G4-15 D6): a refused command writes nothing, leaves no
audit row (the frozen `audit_opportunities` trigger fires only on a write),
and consumes no key.

**B10, the service guard (G5-12).** No statement here names
`current_offer_id` in a write. The opportunity stays on the offer it was
approved on: another offer is a new run and a new review (G5-9). The schema
leaves the column writable for a later slice; a test of the source pins
that no Slice 5 UPDATE writes it.

**What the request body carries and where it goes.**
- The share's `channel` and `note`: G5-8 (i), decided (a) in the review of
  `6c6e614`. Each successful share writes ONE `interactions` row
  (STATUS_CHANGE), in its own transaction: the channel, the note as
  `summary`, the operator, the opportunity and the request's party. It
  records the share. It is no proof that a message was sent or a contact
  made, and no check reads it as one. Its audit row leaves out `summary`
  (`audit_rows.WITHHELD`): the free-text note reaches neither the audit log
  nor any response. A replay returns the stored response and writes
  nothing; a refusal writes nothing.
- The `note` of revalidate and close: stored nowhere. The decision named the
  share; G5-10's "the note follows G5-8 (i)" is put to the reviewer
  (`SLICE_5_STEP5_DELIVERY.md` §13).

**R-S5-5-01 (review of `6c6e614`).** The share's check takes the property
and the offer `FOR UPDATE` (`currency.check(..., exclusive=True)`), so a
consent binding inserted on either is serialized with the share
(`currency.py`, the measured record in
`evidence/SLICE5-STEP5-R-S5-5-01-BEFORE-FIX.txt`).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from .. import exact_json
from . import audit_rows, currency, match_review

#: G5-10 (decided in the review of `d0e0bc9`): the reason category
#: OPPORTUNITY, plus `OTHER`. A test pins this tuple to the seed.
CLOSE_REASONS = ("OWNER_REJECTED", "BUYER_REJECTED", "PROPERTY_UNAVAILABLE",
                 "REQUEST_CHANGED", "UNREACHABLE", "DEAL_CONFIRMED",
                 "DUPLICATE_OPPORTUNITY_CONSOLIDATED", "OTHER")
#: The sharing scopes, narrowest first (RFC-001 R8.2).
SCOPE_RANK: Mapping[str, int] = {"SUMMARY_ONLY": 0, "PROPERTY_DETAILS_ALLOWED": 1,
                                 "CONTACT_AFTER_CONFIRMATION": 2}
#: G5-8 (iii), decided (a) in the review of `6c6e614`: a CURRENT binding with
#: this purpose refuses the share, until a path that records the contact
#: exists. The share's own interaction is not such a record.
CONTACT_FIRST = "CONTACT_BEFORE_SHARING"


class OpportunityRefused(Exception):
    """A typed refusal. `code` is a `ProblemCode` name; the route maps it.
    `field_errors`, when given, name the failing checks (`field`, `code`,
    `message`), as the contract's `Problem.field_errors`."""

    code = "VALIDATION_FAILED"

    def __init__(self, code: str, detail: str,
                 field_errors: list[dict[str, str]] | None = None) -> None:
        super().__init__(detail)
        self.code = code
        self.field_errors = field_errors


@dataclass(frozen=True, slots=True)
class Prepared:
    """What `prepare_*` decided, under the opportunity lock."""

    opportunity: Mapping[str, Any]
    checked: currency.Checked | None = None
    reason_code: str | None = None


def _lock(session: Session, opportunity_id: uuid.UUID) -> Mapping[str, Any]:
    """The FIRST statement on the opportunity. A second command on it waits
    here until the first commits, then reads what the first wrote."""
    row = session.execute(text("""
        SELECT opportunity_id, approved_match_id, request_id, property_id, current_offer_id,
               status::text AS status, validity_status::text AS validity_status,
               sharing_scope::text AS sharing_scope
          FROM turab.opportunities WHERE opportunity_id = :o FOR UPDATE"""),
        {"o": opportunity_id}).mappings().first()
    if row is None:
        # The route checked existence first, and an opportunity is never
        # deleted (`prevent_delete_opportunities`); the same answer, kept.
        raise OpportunityRefused("OBJECT_NOT_AUTHORIZED", "not an available opportunity")
    if row["status"] == "CLOSED":
        raise OpportunityRefused("OPPORTUNITY_CLOSED",
                                 "this opportunity is closed; a closed opportunity is final")
    return row


def _match_context(session: Session, match_id: uuid.UUID) -> dict[str, Any]:
    """What `currency.check` needs from the approved match: its request and
    property, the pinned rule versions it recorded (`explanation.engine`) and
    its freshness thresholds. A match is never changed after its run, so it
    is read without a lock."""
    row = session.execute(text("""
        SELECT request_id, property_id, (explanation -> 'engine')::text AS engine,
               (freshness_snapshot -> 'threshold_days')::text AS threshold_days
          FROM turab.match_candidates WHERE match_id = :m"""),
        {"m": match_id}).mappings().one()
    return {"request_id": row["request_id"], "property_id": row["property_id"],
            "engine": exact_json.loads(row["engine"]),
            "threshold_days": {k: int(v) for k, v in
                               exact_json.loads(row["threshold_days"]).items()}}


def _check(session: Session, opportunity: Mapping[str, Any], clock: Any) -> currency.Checked:
    """§3.7 on the facts now, for the offer the opportunity stands on."""
    return currency.check(session, match=_match_context(session, opportunity["approved_match_id"]),
                          offer_id=opportunity["current_offer_id"], clock=clock)


def reasons_of(checked: currency.Checked) -> list[dict[str, Any]]:
    """The check's reasons, every failing fact, in the table's order."""
    return [dict(r) for r in checked.currency.reasons]


def _field_errors(checked: currency.Checked) -> list[dict[str, str]]:
    return [{"field": r["fact"], "code": r["reason_code"] or r["value"],
             "message": f"{r['fact']} is {r['value']}: {r['class']}"}
            for r in checked.currency.reasons]


def _returning(session: Session, sql: str, params: Mapping[str, Any]) -> dict[str, Any]:
    row = session.execute(text(f"{sql} RETURNING {match_review._OPPORTUNITY_COLUMNS}"),
                          params).mappings().one()
    return match_review.opportunity_view(row)


# --- revalidate (G5-9) ----------------------------------------------------------------

def prepare_revalidate(session: Session, *, opportunity_id: uuid.UUID,
                       clock: Any = None) -> Prepared:
    """Read-only: the lock, the closed check, and the currency check."""
    opportunity = _lock(session, opportunity_id)
    return Prepared(opportunity=opportunity, checked=_check(session, opportunity, clock))


def revalidate(session: Session, prepared: Prepared) -> dict[str, Any]:
    """The one writer of `validity_status` (§3.7). Writes what the check
    found: the validity (not monotonic: INVALID returns to VALID when the
    facts do), `last_activity_at`, `last_confirmed_at` only when VALID, and
    the current binding by G5-5's order (null when none is CURRENT). No
    snapshot, and never `current_offer_id` (B10). The response is the
    `InternalOpportunityView` (an open schema) plus `validity_reasons`: the
    plan's "the reasons name the failing checks, in the response"; no
    column holds them."""
    checked = prepared.checked
    view = _returning(session, """
        UPDATE turab.opportunities
           SET validity_status = CAST(:v AS turab.opportunity_validity),
               last_activity_at = :at,
               last_confirmed_at = CASE WHEN CAST(:v AS text) = 'VALID' THEN :at
                                        ELSE last_confirmed_at END,
               current_permission_binding_id = :binding
         WHERE opportunity_id = :o""",
        {"v": checked.currency.validity, "at": checked.as_of,
         "binding": checked.current_permission_binding_id,
         "o": prepared.opportunity["opportunity_id"]})
    return {**view, "validity_reasons": reasons_of(checked)}


# --- share (G5-8) ---------------------------------------------------------------------

def _contact_first(session: Session, opportunity: Mapping[str, Any], match: Mapping[str, Any],
                   checked: currency.Checked) -> list[str]:
    """G5-8 (iii): the CURRENT bindings with purpose CONTACT_BEFORE_SHARING on
    the offer or its property, by the binding-state rule the match recorded,
    at the check's instant. The existing rows were locked by the check (every
    purpose). A binding being inserted on the offer or the property was
    waited for by the check's `FOR UPDATE` and is read here, by a new
    statement, once committed (R-S5-5-01)."""
    from ..matching import snapshots

    rule = currency._engine_rule(match, "permission_binding_state")
    party = checked.permission_snapshot["offer_party_id"]
    found = []
    for row in session.execute(text("""
            SELECT b.consent_binding_id,
                   CASE WHEN b.offer_id IS NOT NULL THEN 'OFFER' ELSE 'PROPERTY' END AS bound_to,
                   b.purpose::text AS purpose, b.bound_at, b.revoked_at AS binding_revoked_at,
                   g.consent_id, g.party_id AS grant_party_id, g.scope::text AS grant_scope,
                   g.status::text AS grant_status, g.granted_at,
                   g.revoked_at AS grant_revoked_at
              FROM turab.resource_consent_bindings b
              JOIN turab.consent_grants g ON g.consent_id = b.consent_id
             WHERE (b.offer_id = :o OR b.property_id = :p) AND b.purpose::text = :purpose
             ORDER BY b.consent_binding_id"""),
            {"o": opportunity["current_offer_id"], "p": match["property_id"],
             "purpose": CONTACT_FIRST}).mappings():
        if rule.evaluate(snapshots.stored_form(dict(row)), party, checked.as_of) == "CURRENT":
            found.append(str(row["consent_binding_id"]))
    return found


def prepare_share(session: Session, *, opportunity_id: uuid.UUID,
                  clock: Any = None) -> Prepared:
    """G5-8, read-only, in this order:
    1. the opportunity is open, else 409 `OPPORTUNITY_CLOSED`;
    2. its STORED validity is VALID, else 409 `OPPORTUNITY_NOT_VALID`: a
       NEEDS_CONFIRMATION or INVALID opportunity is first revalidated, by
       the command that records it;
    3. the check now is VALID, else 409 `CONSENT_REVOKED` when the
       permission is FAIL, `OPPORTUNITY_NOT_VALID` otherwise; every failing
       fact is named;
    4. the offer's `permission_scope` now is not narrower than the
       opportunity's `sharing_scope`, else 409 `SHARING_SCOPE_NARROWED`;
    5. G5-8 (iii) (a): no CURRENT CONTACT_BEFORE_SHARING binding, else 409
       `CONTACT_BEFORE_SHARING_REQUIRED`.
    What the check found is NOT stored by a refusal: `revalidate` stores it."""
    opportunity = _lock(session, opportunity_id)
    if opportunity["validity_status"] != currency.VALID:
        raise OpportunityRefused(
            "OPPORTUNITY_NOT_VALID",
            f"the recorded validity is {opportunity['validity_status']}, not VALID; "
            "revalidate the opportunity first",
            [{"field": "VALIDITY_STATUS", "code": opportunity["validity_status"],
              "message": "the recorded validity is not VALID"}])
    match = _match_context(session, opportunity["approved_match_id"])
    checked = currency.check(session, match=match, offer_id=opportunity["current_offer_id"],
                             clock=clock, exclusive=True)
    if checked.currency.validity != currency.VALID:
        revoked = checked.facts["PERMISSION"] == "FAIL"
        raise OpportunityRefused(
            "CONSENT_REVOKED" if revoked else "OPPORTUNITY_NOT_VALID",
            f"the facts now are {checked.currency.validity}, not VALID; revalidate the "
            "opportunity to record them", _field_errors(checked))
    if SCOPE_RANK[checked.sharing_scope] < SCOPE_RANK[opportunity["sharing_scope"]]:
        raise OpportunityRefused(
            "SHARING_SCOPE_NARROWED",
            f"the offer's permission scope is now {checked.sharing_scope}, narrower than "
            f"the opportunity's {opportunity['sharing_scope']}",
            [{"field": "SHARING_SCOPE", "code": checked.sharing_scope,
              "message": f"narrower than {opportunity['sharing_scope']}"}])
    contact = _contact_first(session, opportunity, match, checked)
    if contact:
        raise OpportunityRefused(
            "CONTACT_BEFORE_SHARING_REQUIRED",
            "a current consent asks for contact before sharing; no contact is recorded",
            [{"field": "PERMISSION", "code": CONTACT_FIRST,
              "message": f"binding {b} is CURRENT"} for b in contact])
    return Prepared(opportunity=opportunity, checked=checked)


#: The operation recorded in the interaction's `metadata`, so a reader tells
#: a share's record from a contact.
SHARE_OPERATION = "postOpportunitiesOpportunityIdShare"


def share(session: Session, prepared: Prepared, *, channel: str | None, note: str | None,
          operator_account_id: uuid.UUID) -> dict[str, Any]:
    """NEW → SHARED with `shared_at` the first time (migration `0006`, rule
    5); a later share keeps the status and moves `last_activity_at` only.
    No validity, binding or offer is written, and no message is sent
    (Slice 7). Then the share's one interaction (G5-8 (i) (a))."""
    view = _returning(session, """
        UPDATE turab.opportunities
           SET status = CASE WHEN status = 'NEW' THEN 'SHARED'::turab.opportunity_status
                             ELSE status END,
               shared_at = CASE WHEN status = 'NEW' THEN :at ELSE shared_at END,
               last_activity_at = :at
         WHERE opportunity_id = :o""",
        {"at": prepared.checked.as_of, "o": prepared.opportunity["opportunity_id"]})
    _record_share(session, prepared, view, channel=channel, note=note,
                  operator_account_id=operator_account_id)
    return view


def _record_share(session: Session, prepared: Prepared, view: Mapping[str, Any], *,
                  channel: str | None, note: str | None,
                  operator_account_id: uuid.UUID) -> None:
    """One `interactions` row, STATUS_CHANGE, at the share's instant: the
    channel (the contract's four values are values of
    `communication_channel`), the note as `summary`, the request's party, the
    opportunity, the operator. No thread, no outcome. `metadata` names the
    operation and the status before and after."""
    interaction_id = session.execute(text("""
        INSERT INTO turab.interactions (interaction_type, channel, party_id, opportunity_id,
                                        summary, occurred_at, operator_account_id, metadata)
        SELECT 'STATUS_CHANGE', CAST(:channel AS turab.communication_channel), r.party_id,
               :o, :note, :at, :operator, CAST(:metadata AS jsonb)
          FROM turab.requests r WHERE r.request_id = :r
        RETURNING interaction_id"""),
        {"channel": channel, "o": prepared.opportunity["opportunity_id"], "note": note,
         "at": prepared.checked.as_of, "operator": operator_account_id,
         "r": prepared.opportunity["request_id"],
         "metadata": exact_json.dumps({"source_operation": SHARE_OPERATION,
                                       "status_before": prepared.opportunity["status"],
                                       "status_after": view["status"]})}).scalar_one()
    audit_rows.write(session, "interactions", interaction_id, "INSERT", None,
                     audit_rows.row_json(session, "interactions", interaction_id))


# --- close (G5-10) --------------------------------------------------------------------

def prepare_close(session: Session, *, opportunity_id: uuid.UUID,
                  reason_code: str) -> Prepared:
    """G5-10: the reason first (input, 422), then the lock and the closed
    check (state, 409). Close is permitted from NEW, SHARED and ENGAGED."""
    if reason_code not in CLOSE_REASONS:
        raise OpportunityRefused(
            "CLOSE_REASON_NOT_ALLOWED",
            "reason_code must be a reason of the category OPPORTUNITY, or OTHER",
            [{"field": "reason_code", "code": "CLOSE_REASON_NOT_ALLOWED",
              "message": f"one of {list(CLOSE_REASONS)}"}])
    return Prepared(opportunity=_lock(session, opportunity_id), reason_code=reason_code)


def close(session: Session, prepared: Prepared, clock: Any = None) -> dict[str, Any]:
    """CLOSED, `closed_at`, `close_reason_code` and `last_activity_at`, in
    one UPDATE (rule 4 of `0006`). CLOSED is final (rule 1)."""
    return _returning(session, """
        UPDATE turab.opportunities
           SET status = 'CLOSED', closed_at = c.at, close_reason_code = :r,
               last_activity_at = c.at
          FROM (SELECT COALESCE(CAST(:clock AS timestamptz), clock_timestamp()) AS at) c
         WHERE opportunity_id = :o""",
        {"r": prepared.reason_code, "clock": clock,
         "o": prepared.opportunity["opportunity_id"]})
