"""Identity Lite endpoints — Slice 3, step 7.

Ref: the contract's `postIdentityCandidatesGenerate` (ADMIN, OPERATOR),
`getIdentityCandidates` (ADMIN, OPERATOR, REVIEWER) and
`postIdentityCandidatesCandidateIdReview` (ADMIN, REVIEWER;
separation-sensitive, INV-2); ADR-03; `services/identity.py`.

Like every route module: no session, no repository, no SQLAlchemy. Each
command calls `command.authorize` and `command.authorize_staff_only` itself,
where the architecture guard can see it.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from ...services import identity as identity_service
from ...services import timeline as timeline_service
from ..deps import Access, Command
from ..problems import ProblemCode, coded, for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["Identity"])


class GenerateInput(BaseModel):
    """The inline body: `property_id` and `algorithm_version`, neither
    required. The contract does not close this body, but every sibling body
    in this code base is closed, and an unknown field here would be ignored
    in silence, so it is closed too (stated in the step-7 note)."""

    model_config = ConfigDict(extra="forbid")

    property_id: uuid.UUID | None = None
    #: Omissible; the service writes the contract's default explicitly.
    algorithm_version: str = None  # type: ignore[assignment]


class IdentityReviewInput(BaseModel):
    """`IdentityReviewInput`, field for field (closed in the contract)."""

    model_config = ConfigDict(extra="forbid")

    decision: str = Field(pattern="^(CONFIRMED_SAME|CONFIRMED_DISTINCT|UNSURE)$")
    canonical_property_id: uuid.UUID | None = None
    reason_code: str | None = None
    reason_text: str | None = None


def _refused(request, decision):
    if decision.allowed:
        return None
    return for_denial(decision.reason, trace_id_of(request),
                      customer_scoped=False, detail=decision.detail)


@router.post("/identity/candidates/generate",
             operation_id="postIdentityCandidatesGenerate", status_code=201)
def generate(request: Request, body: GenerateInput, command: Command):
    refused = (_refused(request, command.authorize("postIdentityCandidatesGenerate"))
               or _refused(request, command.authorize_staff_only(
                   "postIdentityCandidatesGenerate",
                   "generating identity candidates is a staff action")))
    if refused is not None:
        return refused

    def handler(session):
        rows = identity_service.generate(
            session, property_id=body.property_id,
            algorithm_version=body.algorithm_version)
        return 201, [identity_service.view(r) for r in rows]

    return _run(request, command, "postIdentityCandidatesGenerate",
                "POST /identity/candidates/generate",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=identity_service.IdentityError)


@router.get("/identity/candidates", operation_id="getIdentityCandidates")
def list_candidates(
    request: Request,
    access: Access,
    status: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query()] = 1,
    page_size: Annotated[int, Query()] = timeline_service.DEFAULT_PAGE_SIZE,
):
    decision = access.authorize_operation("getIdentityCandidates")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    try:
        page, page_size = timeline_service.validate_pagination(page, page_size)
    except timeline_service.InvalidPagination as exc:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request), str(exc))
    items, total = access.list_identity_candidates(
        status=status, page=page, page_size=page_size,
        operation_id="getIdentityCandidates")
    page_view = timeline_service.Page(items=tuple(items), page=page,
                                      page_size=page_size, total=total)
    return {"items": [identity_service.view(r) for r in items],
            "meta": page_view.meta()}


@router.post("/identity/candidates/{candidate_id}/review",
             operation_id="postIdentityCandidatesCandidateIdReview")
def review(request: Request, candidate_id: uuid.UUID, body: IdentityReviewInput,
           command: Command):
    refused = (_refused(request, command.authorize("postIdentityCandidatesCandidateIdReview"))
               or _refused(request, command.authorize_staff_only(
                   "postIdentityCandidatesCandidateIdReview",
                   "an identity decision is a staff action")))
    if refused is not None:
        return refused

    def handler(session):
        row = identity_service.review(
            session, candidate_id=candidate_id, decision=body.decision,
            canonical_property_id=body.canonical_property_id,
            reason_code=body.reason_code, reason_text=body.reason_text,
            reviewer_account_id=command.subject.account_id)
        return 200, identity_service.view(row)

    return _run(request, command, "postIdentityCandidatesCandidateIdReview",
                f"POST /identity/candidates/{candidate_id}/review",
                body.model_dump(mode="json", exclude_unset=True), handler, 200,
                extra_errors=identity_service.IdentityError)
