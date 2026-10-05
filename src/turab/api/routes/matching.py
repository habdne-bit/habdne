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
from pydantic import BaseModel, ConfigDict, field_validator

from ...services import matching_run
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
