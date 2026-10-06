"""The matching run (Slice 4, step 7), and the two staff reads of step 8.

Ref: the contract's `postRequestsRequestIdMatchingRun` (ADMIN, OPERATOR,
REVIEWER; Idempotency-Key), narrowed by CORRECTION-004;
`docs/gate/SLICE_4_PLAN.md` G4-15 (decided in the review of b3246b0);
`services/matching_run.py`.

Like every route module: no session, no repository, no SQLAlchemy. The
route calls `command.authorize` and `command.authorize_staff_only` itself,
where the architecture guard can see it. Matching is staff-only by its
`x-roles`; the second lock refuses a customer even if the role table ever
said otherwise.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...services import match_review, matching_run
from ...services.access import AccessDenied
from ..deps import Access, Command
from ..problems import ProblemCode, coded, for_denial, trace_id_of
from ..responses import ExactJSONResponse
from .parties import _run

router = APIRouter(tags=["Matching"])

RUN = "postRequestsRequestIdMatchingRun"


class MatchingRunInput(BaseModel):
    """The inline body, as the effective contract declares it.

    - `matching_policy_version` is REQUIRED by CORRECTION-004 and must equal
      the ACTIVE policy's version. It is typed `Any` here on purpose: an
      omitted, mistyped, unknown or inactive version all reach the one typed
      refusal (422 `MATCHING_POLICY_VERSION_REFUSED`), which never echoes the
      value, instead of a generic validation error that could.
    - `property_ids` is an array of ids. Absent means a full scan; `[]`
      means no candidate; **null is refused**, since the contract's type is
      an array and null is not one (review of bf052f4, R-S4-7-01).
    - **The body is open**, as the contract leaves it (no
      `additionalProperties: false`; CORRECTION-004 narrows only the
      version). An undeclared field is accepted and changes nothing the run
      computes. It is part of the body, so it counts for idempotency
      (API_CONTRACTS §2.3). Closing the body would be a contract narrowing of
      its own, which no correction approves (review of bf052f4).
    """

    model_config = ConfigDict(extra="allow")

    matching_policy_version: Any = None
    property_ids: list[uuid.UUID] | None = None

    @field_validator("property_ids", mode="before")
    @classmethod
    def _an_array_not_null(cls, value: Any) -> Any:
        # Runs only for a value that was SENT: an absent field keeps its
        # default and is a full scan.
        if value is None:
            raise ValueError("property_ids is an array; omit it for a full scan")
        return value


@router.post("/requests/{request_id}/matching/run", operation_id=RUN, status_code=201)
def run_matching(request: Request, request_id: uuid.UUID, body: MatchingRunInput,
                 command: Command):
    for decision in (command.authorize(RUN),
                     command.authorize_staff_only(RUN, "matching is a staff action")):
        if not decision.allowed:
            return for_denial(decision.reason, trace_id_of(request),
                              customer_scoped=False, detail=decision.detail)

    def prepare(session):
        return matching_run.prepare(
            session, request_id, matching_policy_version=body.matching_policy_version,
            property_ids=body.property_ids)

    return _run(request, command, RUN, f"POST /requests/{request_id}/matching/run",
                body.model_dump(mode="json"), matching_run.execute, 201,
                extra_errors=(matching_run.RunRefused, matching_run.RequestMissing),
                prepare=prepare, isolation="REPEATABLE READ")


# --- step 8: the two staff reads ---------------------------------------------

MATCH = "getMatchesMatchId"
DIAGNOSTIC = "getRequestsRequestIdDiagnostic"


@router.get("/matches/{match_id}", operation_id=MATCH)
def read_match(request: Request, match_id: uuid.UUID, access: Access):
    """One stored match as the contract's `MatchCandidate`: staff only by its
    `x-roles`, read from its rows and recorded (R6.3). There is no customer
    path to a match (R9.2). Numbers are returned as stored (`ExactJSONResponse`)."""
    decision = access.authorize_operation(MATCH)
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    result = access.read_match(match_id, MATCH)
    if isinstance(result, AccessDenied):
        return for_denial(result.reason, trace_id_of(request), customer_scoped=False)
    return ExactJSONResponse(content=result)


@router.get("/requests/{request_id}/diagnostic", operation_id=DIAGNOSTIC)
def read_latest_diagnostic(request: Request, request_id: uuid.UUID, access: Access):
    """The request's latest diagnostic run (G4-15: counts and blocker summary;
    `suggested_actions` and `relaxation_scenarios` are empty until Slice 6).
    Staff only and recorded. 404 when the request has never been run."""
    decision = access.authorize_operation(DIAGNOSTIC)
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    result = access.read_latest_diagnostic(request_id, DIAGNOSTIC)
    if result is None:
        return coded(ProblemCode.NOT_FOUND, trace_id_of(request),
                     "no matching run has been recorded for this request")
    if not isinstance(result, dict):
        return for_denial(result.reason, trace_id_of(request), customer_scoped=False)
    return ExactJSONResponse(content=result)


# --- Slice 5 step 2: the human review ----------------------------------------

REVIEW = "postMatchesMatchIdReview"


class MatchReviewInput(BaseModel):
    """`MatchReviewInput`, field for field (closed in the contract). The
    rules that depend on the decision (G5-3) are the service's, so that they
    answer with their own codes. `reason_code` and `reason_text` are strings
    in the contract: absent is allowed, an explicit null is not."""

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(APPROVED|REJECTED|NEED_MORE_INFORMATION)$")
    reason_code: str | None = None
    reason_text: str | None = None

    @field_validator("reason_code", "reason_text", mode="before")
    @classmethod
    def _a_string_not_null(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("a string; omit the field rather than send null")
        return value


@router.post("/matches/{match_id}/review", operation_id=REVIEW)
def review_match(request: Request, match_id: uuid.UUID, body: MatchReviewInput,
                 command: Command):
    """The human decision on one match (Slice 5, steps 2 and 3). REJECTED and
    NEED_MORE_INFORMATION record a review (and NMI a task); APPROVED records a
    review and creates the one opportunity, after the checks of
    `match_review`. A refusal writes nothing."""
    for decision in (command.authorize(REVIEW),
                     command.authorize_staff_only(REVIEW, "a match review is a staff action"),
                     command.authorize_match_exists(match_id, REVIEW)):
        if not decision.allowed:
            return for_denial(decision.reason, trace_id_of(request),
                              customer_scoped=False, detail=decision.detail)

    def prepare(session):
        return match_review.prepare(
            session, match_id=match_id, decision=body.decision,
            reason_code=body.reason_code, reason_text=body.reason_text)

    def handler(session, prepared):
        return 200, match_review.record(
            session, prepared, reviewer_account_id=command.subject.account_id)

    return _run(request, command, REVIEW, f"POST /matches/{match_id}/review",
                body.model_dump(mode="json", exclude_unset=True), handler, 200,
                extra_errors=match_review.ReviewRefused, prepare=prepare)


# --- Slice 5 step 4: the internal opportunity read and the match queue -----------

OPPORTUNITY = "getOpportunitiesOpportunityId"
MATCH_QUEUE = "getBackofficeQueuesMatches"


@router.get("/opportunities/{opportunity_id}", operation_id=OPPORTUNITY)
def read_opportunity(request: Request, opportunity_id: uuid.UUID, access: Access):
    """The contract's `InternalOpportunityView`: staff only by its `x-roles`,
    the stored row unfiltered, recorded (R6.3; plan §3.6). An unknown id is
    403 and recorded, the staff-read convention. Numbers as stored."""
    decision = access.authorize_operation(OPPORTUNITY)
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    result = access.read_opportunity(opportunity_id, OPPORTUNITY)
    if isinstance(result, AccessDenied):
        return for_denial(result.reason, trace_id_of(request), customer_scoped=False)
    return ExactJSONResponse(content=result)


@router.get("/backoffice/queues/matches", operation_id=MATCH_QUEUE, tags=["BackOffice"])
def match_queue(request: Request, access: Access):
    """`QueuePage` of matches awaiting a decision (G5-11), staff only, audited
    once with its count (R6.3c). Paging as the Slice 3 queues: the whole
    queue, `next_cursor` null."""
    decision = access.authorize_operation(MATCH_QUEUE)
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    return {"items": access.match_queue(operation_id=MATCH_QUEUE), "next_cursor": None}
