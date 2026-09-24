"""The public property list — Slice 3, step 6.

Ref: the contract's `getPublicProperties` (`security: []`); RFC-001 R10.4 (the
closed list of unauthenticated operations) and R6.3 (no per-request read
audit); API_CONTRACTS v0.2 §3 "Public"; `docs/gate/SLICE_3_STEP6_DELIVERY.md`.

Like every route module: no session, no repository, no SQLAlchemy. The three
listing conditions live in `services/public_listing.py`. The projection lives
in `dto.PublicPropertySummary`. This route checks the policy, validates the
page, renders, and checks the R9.2 floor.
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Query, Request

from ...dto.boundaries import Audience, PublicPropertySummary, assert_no_forbidden_fields
from ...services import timeline as timeline_service
from ..deps import Public
from ..problems import ProblemCode, coded, for_denial, trace_id_of

router = APIRouter(tags=["Public"])


@router.get("/public/properties", operation_id="getPublicProperties")
def list_public_properties(
    request: Request,
    public: Public,
    location_id: Annotated[uuid.UUID | None, Query()] = None,
    property_type: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query()] = 1,
    page_size: Annotated[int, Query()] = timeline_service.DEFAULT_PAGE_SIZE,
):
    """A JSON array of `PublicPropertySummary`, as the contract declares.

    Not audited per request: `getPublicProperties` is in
    `NON_AUDITED_READ_OPERATIONS` (R6.3).
    """
    decision = public.authorize("getPublicProperties")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    try:
        # The contract's `Page` (minimum 1) and `PageSize` (1..100).
        page, page_size = timeline_service.validate_pagination(page, page_size)
    except timeline_service.InvalidPagination as exc:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request), str(exc))

    listed = public.list_properties(location_id=location_id, property_type=property_type,
                                    page=page, page_size=page_size)
    body = [PublicPropertySummary.render(item.row, offers=item.offers).to_json()
            for item in listed]
    assert_no_forbidden_fields(body, Audience.PUBLIC, operation_id="getPublicProperties")
    return body
