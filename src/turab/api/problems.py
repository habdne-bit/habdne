"""RFC 7807 problem responses — the complete error contract.

Ref: RFC-001 §12; API_CONTRACTS v0.2 §2.5, §8; the frozen `Problem` schema
(`title`, `status`, `code`, `trace_id` required, plus optional `type`,
`detail`, `field_errors`).

Two rules govern everything here:
  * decision 2 — 404 conceals, 403 says the action is barred on an object the
    caller may already see;
  * §2.5 / §8 — `detail` never carries database exception text, OTP codes or
    document payloads.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Iterable

from fastapi import Request
from fastapi.responses import JSONResponse

from ..auth.policy import DenyReason

MEDIA_TYPE = "application/problem+json"


class ProblemCode(StrEnum):
    """Stable codes. API_CONTRACTS §2.5 requires these rather than DB text."""

    UNAUTHENTICATED = "UNAUTHENTICATED"
    ROLE_NOT_PERMITTED = "ROLE_NOT_PERMITTED"
    ROLE_CONFIGURATION_ANOMALY = "ROLE_CONFIGURATION_ANOMALY"
    OBJECT_NOT_AUTHORIZED = "OBJECT_NOT_AUTHORIZED"
    ACTION_NOT_PERMITTED = "ACTION_NOT_PERMITTED"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    IDEMPOTENCY_KEY_REQUIRED = "IDEMPOTENCY_KEY_REQUIRED"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    IF_MATCH_REQUIRED = "IF_MATCH_REQUIRED"
    STALE_VERSION = "STALE_VERSION"
    CLAIM_AUTHORITY_CONFLICT = "CLAIM_AUTHORITY_CONFLICT"
    CONSENT_REVOKED = "CONSENT_REVOKED"
    HARD_GATE_FAILED = "HARD_GATE_FAILED"
    IDENTITY_ALIAS_NOT_CANONICAL = "IDENTITY_ALIAS_NOT_CANONICAL"
    RESOURCE_ALREADY_CLAIMED = "RESOURCE_ALREADY_CLAIMED"
    RESOURCE_NOT_CLAIMABLE = "RESOURCE_NOT_CLAIMABLE"
    #: A criterion already occupies (request, code, sort_order). 409, not
    #: 422: the body is well formed and the request is refused because of
    #: the resource's current state, which is what a conflict is.
    DUPLICATE_CRITERION_SLOT = "DUPLICATE_CRITERION_SLOT"
    #: An offer transition lost its compare-and-set: the offer left the state
    #: the transition was decided from before it could apply (Slice 3 plan
    #: §6.3). 409 for the same reason as above — the body is well formed and
    #: the refusal is about the resource's current state.
    OFFER_STATE_CHANGED = "OFFER_STATE_CHANGED"
    #: `ux_offer_primary_source` reached despite the parent-offer lock. Not the
    #: normal outcome of two lock-serialised links (plan §3.6), which both
    #: succeed; mapped so that a path bypassing the lock is a 409, not a 500.
    PRIMARY_SOURCE_CONFLICT = "PRIMARY_SOURCE_CONFLICT"
    #: G3-6 rule 6a (enforced by migration 0004): the party already holds this
    #: relation_code on this property for an overlapping period.
    RELATION_OVERLAP = "RELATION_OVERLAP"
    #: G3-6 §3.3: ending a relation that already has an end is a conflict,
    #: never a silent success.
    RELATION_ALREADY_ENDED = "RELATION_ALREADY_ENDED"
    #: G3-10 (decided): lead conversion is refused until a recorded contact
    #: path (Slice 8) and a declared conversion schema exist. 409, a status the
    #: operation declares: the body is valid; the preconditions are not.
    EXTERNAL_LEAD_CONVERSION_NOT_AVAILABLE = "EXTERNAL_LEAD_CONVERSION_NOT_AVAILABLE"
    #: G3-11, decided (c): the truth layer is PROPERTY-only in this version.
    #: Claims and resolutions about a PARTY, REQUEST or OFFER are refused: the
    #: controlled vocabulary registers property attributes only. 422: the
    #: subject is well formed; no rule exists yet for what may be said of it.
    ATTRIBUTE_VOCABULARY_UNDECIDED = "ATTRIBUTE_VOCABULARY_UNDECIDED"
    #: Step 7: a CONFIRMED_SAME or CONFIRMED_DISTINCT decision is final. 409:
    #: the body is valid; the candidate's state does not admit it.
    IDENTITY_CANDIDATE_DECIDED = "IDENTITY_CANDIDATE_DECIDED"
    #: The contract's declared condition on `postRecordsClaim` is not met.
    #: 403, not 404: the caller already named a record they may not claim,
    #: and concealing it would leave them unable to tell a wrong id from a
    #: wrong account. One message covers every failing reason, so the code
    #: cannot be used to map which records belong to which party.
    CLAIM_NOT_ELIGIBLE = "CLAIM_NOT_ELIGIBLE"
    #: Slice 4 step 7, G4-15 D6. CORRECTION-004: the requested version is not
    #: the ACTIVE policy's (omitted, unknown, or inactive). 422; the value is
    #: never echoed.
    MATCHING_POLICY_VERSION_REFUSED = "MATCHING_POLICY_VERSION_REFUSED"
    #: G4-8: the request's status is not one a run accepts. 409: the body is
    #: valid; the request's current state refuses it.
    REQUEST_NOT_MATCHABLE = "REQUEST_NOT_MATCHABLE"
    #: G4-3 (b), G4-5R, G4-7: the request's criteria cannot be matched as
    #: they stand. 422, naming the rule and the criterion, never the value.
    MATCHING_INPUT_REFUSED = "MATCHING_INPUT_REFUSED"
    #: Plan §3.1, a configuration fault, not the caller's input: a TYPED 500
    #: (review of bf052f4), one code per fault (review of 48588a0). The
    #: detail is fixed; the cause is logged under the trace id. Nothing is
    #: written. No matching policy is active:
    MATCHING_POLICY_NOT_ACTIVE = "MATCHING_POLICY_NOT_ACTIVE"
    #: The active matching policy is not one this engine implements:
    MATCHING_POLICY_NOT_SUPPORTED = "MATCHING_POLICY_NOT_SUPPORTED"
    #: Slice 5 step 2 (G5-3, decided (a) in the review of 29a0f30). The
    #: review's reason is required (REJECTED, NEED_MORE_INFORMATION), or
    #: forbidden (APPROVED), or outside what the decision admits: 422, input.
    REVIEW_REASON_REQUIRED = "REVIEW_REASON_REQUIRED"
    REVIEW_REASON_NOT_ALLOWED = "REVIEW_REASON_NOT_ALLOWED"
    #: The match's latest review is REJECTED or APPROVED, or an opportunity
    #: was created from it: a later review is refused. 409, state.
    MATCH_REVIEW_DECIDED = "MATCH_REVIEW_DECIDED"
    #: Slice 5 step 3, APPROVED (G5-2 (a), G5-3, §3.3, §3.7). 409, state:
    #: - the match was not evaluated ELIGIBLE with all four gates PASS (named
    #:   before the frozen `trg_match_review_gate` fires);
    #: - a later evaluation of the same offer exists;
    #: - the currency check of the facts now is not VALID (`field_errors`
    #:   lists every failing fact);
    #: - an opportunity is open for the request and the canonical property.
    #: The step-2 code REVIEW_DECISION_NOT_YET_AVAILABLE is removed: APPROVED
    #: is executed (review of 29a0f30; review of 60b0152).
    MATCH_GATES_NOT_PASS = "MATCH_GATES_NOT_PASS"
    MATCH_SUPERSEDED = "MATCH_SUPERSEDED"
    MATCH_CONTEXT_NOT_VALID = "MATCH_CONTEXT_NOT_VALID"
    OPPORTUNITY_ALREADY_OPEN = "OPPORTUNITY_ALREADY_OPEN"
    #: Slice 5 step 5, the opportunity commands (G5-8, G5-9, G5-10). 409,
    #: state, except the close reason (422, input):
    #: - any command on a CLOSED opportunity (CLOSED is final);
    #: - a share whose recorded validity, or the check now, is not VALID
    #:   (permission FAIL answers CONSENT_REVOKED instead);
    #: - a share whose offer's permission scope is now narrower than the
    #:   opportunity's sharing scope;
    #: - G5-8 (iii) (a), decided in the review of 6c6e614: a share while a
    #:   CONTACT_BEFORE_SHARING binding is CURRENT;
    #: - a close reason outside the category OPPORTUNITY and OTHER.
    OPPORTUNITY_CLOSED = "OPPORTUNITY_CLOSED"
    OPPORTUNITY_NOT_VALID = "OPPORTUNITY_NOT_VALID"
    SHARING_SCOPE_NARROWED = "SHARING_SCOPE_NARROWED"
    CONTACT_BEFORE_SHARING_REQUIRED = "CONTACT_BEFORE_SHARING_REQUIRED"
    CLOSE_REASON_NOT_ALLOWED = "CLOSE_REASON_NOT_ALLOWED"
    #: Slice 6 step 2, the task completion (G6-8). A task that is DONE or
    #: CANCELLED is not completed again: 409, state (G6-8 (i)). The evidence
    #: observation named does not exist, or was deleted while the completion
    #: waited for it: 422, input (G6-8 (iv), R2d). Neither echoes an id.
    TASK_NOT_OPEN = "TASK_NOT_OPEN"
    EVIDENCE_OBSERVATION_NOT_FOUND = "EVIDENCE_OBSERVATION_NOT_FOUND"
    #: Slice 7 step 2, the communication record (SLICE_7_PLAN.md G7-3, G7-4,
    #: G7-6, G7-9, G7-16 (vi), decided in the review of 0f423d2). None echoes
    #: an id, a reference or database text; `field_errors` name fields only.
    #: The thread command:
    THREAD_REF_NOT_SCOPED = "THREAD_REF_NOT_SCOPED"
    THREAD_REF_TAKEN = "THREAD_REF_TAKEN"
    OPPORTUNITY_NOT_SALE = "OPPORTUNITY_NOT_SALE"
    THREAD_LINKS_INCONSISTENT = "THREAD_LINKS_INCONSISTENT"
    LINKED_RECORD_NOT_FOUND = "LINKED_RECORD_NOT_FOUND"
    #: The message command:
    DIRECTION_NOT_ACCEPTED = "DIRECTION_NOT_ACCEPTED"
    DELIVERY_STATUS_NOT_ACCEPTED = "DELIVERY_STATUS_NOT_ACCEPTED"
    MESSAGE_METADATA_NOT_ACCEPTED = "MESSAGE_METADATA_NOT_ACCEPTED"
    EXTERNAL_REF_WITHOUT_PROVIDER = "EXTERNAL_REF_WITHOUT_PROVIDER"
    #: G7-4: "an INTERNAL message never carries a reference (422)"; the plan
    #: names no code, so this name is ours, submitted with step 2's delivery.
    INTERNAL_MESSAGE_REF_NOT_ACCEPTED = "INTERNAL_MESSAGE_REF_NOT_ACCEPTED"
    MESSAGE_REF_TAKEN = "MESSAGE_REF_TAKEN"
    #: Slice 7 step 4, G7-10 and G7-18 (vii), decided in the review of e18271a.
    #: 422; `field_errors` name a field, never a value or an id. A type of
    #: G7-10 outside an INTERNAL message of a PHONE thread, or a link's
    #: metadata not exactly its two uuids:
    PHONE_DECISION_NOT_ACCEPTED = "PHONE_DECISION_NOT_ACCEPTED"
    CONFIRMATION_LINK_NOT_ACCEPTED = "CONFIRMATION_LINK_NOT_ACCEPTED"
    #: The decision is missing, of another type or direction, or of another
    #: thread; the observation is missing, of another kind or party, has no
    #: time, or is before the decision:
    DECISION_NOT_LINKABLE = "DECISION_NOT_LINKABLE"
    OBSERVATION_NOT_LINKABLE = "OBSERVATION_NOT_LINKABLE"
    CONTENT_NOT_ARCHIVABLE = "CONTENT_NOT_ARCHIVABLE"
    #: Slice 7 step 3, the webhook (G7-15, G7-17). None echoes the body, a
    #: reference or the signature. The body is larger than 64 KiB (G7-15), or
    #: its envelope or a known type's keys are not valid (G7-17 (iii)): 400,
    #: the status the frozen operation declares. Both names are ours,
    #: submitted with step 3's delivery (the plan names no code).
    WEBHOOK_BODY_TOO_LARGE = "WEBHOOK_BODY_TOO_LARGE"
    WEBHOOK_ENVELOPE_NOT_VALID = "WEBHOOK_ENVELOPE_NOT_VALID"
    #: CORRECTION-007 and CORRECTION-008: the event stored and not processed
    #: (500); the signing secret not configured, nothing stored (503).
    WEBHOOK_PROCESSING_FAILED = "WEBHOOK_PROCESSING_FAILED"
    WEBHOOK_NOT_READY = "WEBHOOK_NOT_READY"
    INVALID_ROLE_COMBINATION = "INVALID_ROLE_COMBINATION"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: code -> (status, title). One place, so a code cannot acquire two statuses.
_CATALOGUE: dict[ProblemCode, tuple[int, str]] = {
    ProblemCode.UNAUTHENTICATED: (401, "Not authenticated"),
    ProblemCode.ROLE_NOT_PERMITTED: (403, "Not permitted"),
    ProblemCode.ROLE_CONFIGURATION_ANOMALY: (403, "Not permitted"),
    ProblemCode.OBJECT_NOT_AUTHORIZED: (403, "Not permitted"),
    ProblemCode.ACTION_NOT_PERMITTED: (403, "Action not permitted"),
    ProblemCode.NOT_FOUND: (404, "Not found"),
    ProblemCode.METHOD_NOT_ALLOWED: (405, "Method not allowed"),
    ProblemCode.VALIDATION_FAILED: (422, "Validation failed"),
    ProblemCode.UNKNOWN_FIELD: (422, "Unknown field"),
    ProblemCode.IDEMPOTENCY_KEY_REQUIRED: (400, "Idempotency-Key required"),
    ProblemCode.IDEMPOTENCY_KEY_CONFLICT: (409, "Idempotency key conflict"),
    ProblemCode.IF_MATCH_REQUIRED: (428, "If-Match required"),
    ProblemCode.STALE_VERSION: (409, "Stale version"),
    ProblemCode.CLAIM_AUTHORITY_CONFLICT: (409, "Conflicting claim authority"),
    ProblemCode.CONSENT_REVOKED: (409, "Consent revoked"),
    ProblemCode.HARD_GATE_FAILED: (409, "Hard gate failed"),
    ProblemCode.IDENTITY_ALIAS_NOT_CANONICAL: (409, "Alias is not canonical"),
    ProblemCode.RESOURCE_ALREADY_CLAIMED: (409, "Already claimed"),
    ProblemCode.RESOURCE_NOT_CLAIMABLE: (409, "Not claimable"),
    ProblemCode.DUPLICATE_CRITERION_SLOT: (409, "Duplicate criterion"),
    ProblemCode.OFFER_STATE_CHANGED: (409, "Offer state changed"),
    ProblemCode.PRIMARY_SOURCE_CONFLICT: (409, "Primary source conflict"),
    ProblemCode.RELATION_OVERLAP: (409, "Overlapping relation"),
    ProblemCode.RELATION_ALREADY_ENDED: (409, "Relation already ended"),
    ProblemCode.EXTERNAL_LEAD_CONVERSION_NOT_AVAILABLE: (409, "Conversion not available"),
    ProblemCode.ATTRIBUTE_VOCABULARY_UNDECIDED: (422, "Attribute vocabulary undecided"),
    ProblemCode.IDENTITY_CANDIDATE_DECIDED: (409, "Identity decision is final"),
    ProblemCode.CLAIM_NOT_ELIGIBLE: (403, "Not eligible to claim"),
    ProblemCode.MATCHING_POLICY_VERSION_REFUSED: (422, "Matching policy version refused"),
    ProblemCode.REQUEST_NOT_MATCHABLE: (409, "Request not matchable"),
    ProblemCode.MATCHING_INPUT_REFUSED: (422, "Matching input refused"),
    ProblemCode.REVIEW_REASON_REQUIRED: (422, "Review reason required"),
    ProblemCode.REVIEW_REASON_NOT_ALLOWED: (422, "Review reason not allowed"),
    ProblemCode.MATCH_REVIEW_DECIDED: (409, "Match review is final"),
    ProblemCode.MATCH_GATES_NOT_PASS: (409, "Match gates not passed"),
    ProblemCode.MATCH_SUPERSEDED: (409, "Match superseded"),
    ProblemCode.MATCH_CONTEXT_NOT_VALID: (409, "Match context not valid"),
    ProblemCode.OPPORTUNITY_ALREADY_OPEN: (409, "Opportunity already open"),
    ProblemCode.OPPORTUNITY_CLOSED: (409, "Opportunity closed"),
    ProblemCode.OPPORTUNITY_NOT_VALID: (409, "Opportunity not valid"),
    ProblemCode.SHARING_SCOPE_NARROWED: (409, "Sharing scope narrowed"),
    ProblemCode.CONTACT_BEFORE_SHARING_REQUIRED: (409, "Contact before sharing required"),
    ProblemCode.CLOSE_REASON_NOT_ALLOWED: (422, "Close reason not allowed"),
    ProblemCode.TASK_NOT_OPEN: (409, "Task not open"),
    ProblemCode.EVIDENCE_OBSERVATION_NOT_FOUND: (422, "Evidence observation not found"),
    ProblemCode.THREAD_REF_NOT_SCOPED: (422, "Thread reference not scoped"),
    ProblemCode.THREAD_REF_TAKEN: (409, "Thread reference taken"),
    ProblemCode.OPPORTUNITY_NOT_SALE: (422, "Opportunity not of a sale"),
    ProblemCode.THREAD_LINKS_INCONSISTENT: (422, "Thread links inconsistent"),
    ProblemCode.LINKED_RECORD_NOT_FOUND: (422, "Linked record not found"),
    ProblemCode.DIRECTION_NOT_ACCEPTED: (422, "Direction not accepted"),
    ProblemCode.DELIVERY_STATUS_NOT_ACCEPTED: (422, "Delivery status not accepted"),
    ProblemCode.MESSAGE_METADATA_NOT_ACCEPTED: (422, "Message metadata not accepted"),
    ProblemCode.EXTERNAL_REF_WITHOUT_PROVIDER: (422, "External reference without provider"),
    ProblemCode.INTERNAL_MESSAGE_REF_NOT_ACCEPTED: (422,
                                                    "Internal message reference not accepted"),
    ProblemCode.MESSAGE_REF_TAKEN: (409, "Message reference taken"),
    ProblemCode.PHONE_DECISION_NOT_ACCEPTED: (422, "Phone decision not accepted"),
    ProblemCode.CONFIRMATION_LINK_NOT_ACCEPTED: (422, "Confirmation link not accepted"),
    ProblemCode.DECISION_NOT_LINKABLE: (422, "Decision not linkable"),
    ProblemCode.OBSERVATION_NOT_LINKABLE: (422, "Observation not linkable"),
    ProblemCode.CONTENT_NOT_ARCHIVABLE: (422, "Content not archivable"),
    ProblemCode.MATCHING_POLICY_NOT_ACTIVE: (500, "No active matching policy"),
    ProblemCode.MATCHING_POLICY_NOT_SUPPORTED: (500, "Matching policy not supported"),
    ProblemCode.WEBHOOK_BODY_TOO_LARGE: (400, "Request rejected"),
    ProblemCode.WEBHOOK_ENVELOPE_NOT_VALID: (400, "Request rejected"),
    ProblemCode.WEBHOOK_PROCESSING_FAILED: (500, "Webhook event not processed"),
    ProblemCode.WEBHOOK_NOT_READY: (503, "Webhook not ready"),
    ProblemCode.INVALID_ROLE_COMBINATION: (422, "Invalid role combination"),
    ProblemCode.PROVIDER_UNAVAILABLE: (503, "Verification provider unavailable"),
    ProblemCode.NOT_IMPLEMENTED: (501, "Not implemented"),
    ProblemCode.INTERNAL_ERROR: (500, "Internal error"),
}

#: Substrings that must never reach a client in `detail` (§2.5, §8).
_LEAK_MARKERS: tuple[str, ...] = (
    "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "psycopg", "sqlalchemy",
    "Traceback", "turab.", "DETAIL:", "HINT:", "otp",
)


class DetailLeak(RuntimeError):
    """A problem `detail` tried to carry implementation text."""


def _check_detail(detail: str | None) -> None:
    if not detail:
        return
    lowered = detail.lower()
    for marker in _LEAK_MARKERS:
        if marker.lower() in lowered:
            raise DetailLeak(
                f"problem detail may not contain {marker!r}: domain failures "
                "expose stable codes, not database or implementation text "
                "(API_CONTRACTS §2.5)"
            )


def problem(
    status: int,
    code: str,
    title: str,
    trace_id: str,
    detail: str | None = None,
    *,
    field_errors: Iterable[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    _check_detail(detail)
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": code,
        "trace_id": trace_id,
    }
    if detail:
        body["detail"] = detail
    if field_errors:
        body["field_errors"] = list(field_errors)
    body.update(extra)
    return JSONResponse(
        status_code=status, content=body, media_type=MEDIA_TYPE, headers=headers,
    )


def coded(
    code: ProblemCode, trace_id: str, detail: str | None = None, **kwargs: Any
) -> JSONResponse:
    """Build a problem from the catalogue, so status and code cannot diverge."""
    status, title = _CATALOGUE[code]
    return problem(status, code.value, title, trace_id, detail, **kwargs)


#: Denial reasons that are concealed on /me/* (decision 2).
_CONCEALED = (DenyReason.OBJECT_NOT_AUTHORIZED, DenyReason.NO_PARTY)

_DENIAL_CODES: dict[DenyReason, ProblemCode] = {
    DenyReason.NO_POLICY: ProblemCode.ROLE_NOT_PERMITTED,
    DenyReason.ACCOUNT_NOT_USABLE: ProblemCode.UNAUTHENTICATED,
    DenyReason.ROLE_NOT_PERMITTED: ProblemCode.ROLE_NOT_PERMITTED,
    DenyReason.ROLE_CONFIGURATION_ANOMALY: ProblemCode.ROLE_CONFIGURATION_ANOMALY,
    DenyReason.NO_PARTY: ProblemCode.OBJECT_NOT_AUTHORIZED,
    DenyReason.OBJECT_NOT_AUTHORIZED: ProblemCode.OBJECT_NOT_AUTHORIZED,
    DenyReason.CLAIM_AUTHORITY_CONFLICT: ProblemCode.CLAIM_AUTHORITY_CONFLICT,
}

#: The one fixed body for a disclosed claim conflict. Says only THAT the claim
#: is contested: no claimant identity, no count, nothing a caller could use to
#: identify the other party.
CONFLICT_DETAIL = (
    "This record's claim authority is contested and requires operational "
    "resolution."
)


def for_denial(
    reason: DenyReason, trace_id: str, *, customer_scoped: bool,
    detail: str | None = None,
) -> JSONResponse:
    """Map a denial to a response, applying decision 2.

    On /me/*, a failed object check returns 404: a 403 there would confirm an
    id exists and turn the endpoint into an existence oracle (K01/K02).
    """
    if reason is DenyReason.CLAIM_AUTHORITY_CONFLICT:
        # `detail` is ignored on purpose: no call site can widen this body.
        return coded(ProblemCode.CLAIM_AUTHORITY_CONFLICT, trace_id, CONFLICT_DETAIL)

    if customer_scoped and reason in _CONCEALED:
        return coded(ProblemCode.NOT_FOUND, trace_id)

    return coded(_DENIAL_CODES[reason], trace_id, detail)


def trace_id_of(request: Request) -> str:
    return getattr(request.state, "trace_id", "-")
