"""Internal staff reads and a back-office queue.

Ref: RFC-001 §6, R5.3b, R6.3c.

Staff failures return 403 with OBJECT_NOT_AUTHORIZED rather than 404: a staff
caller is already trusted to know that objects exist, so concealment buys
nothing and a precise error is more useful.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request

from ...auth.loaders import ResourceKind
from ..deps import Access
from ..problems import for_denial, problem, trace_id_of

router = APIRouter(tags=["BackOffice"])


@router.get("/reason-codes", operation_id="getReasonCodes")
def get_reason_codes(request: Request, access: Access):
    """Decision 5: ADMIN, OPERATOR, REVIEWER. Not CUSTOMER."""
    decision = access.authorize_operation("getReasonCodes")
    if not decision.allowed:
        return for_denial(
            decision.reason, trace_id_of(request), customer_scoped=False,
            detail=decision.detail,
        )
    # Master data: no per-resource read audit (R6.3).
    return {"items": []}


@router.get("/backoffice/queues/requests", operation_id="getBackofficeQueuesRequests")
def get_requests_queue(request: Request, access: Access):
    """A bulk list: audited ONCE for the access, never per row (R6.3c)."""
    decision = access.authorize_operation("getBackofficeQueuesRequests")
    if not decision.allowed:
        return for_denial(
            decision.reason, trace_id_of(request), customer_scoped=False,
            detail=decision.detail,
        )
    items: list[dict] = []
    access.record_list_access(
        operation_id="getBackofficeQueuesRequests",
        resource_kind=ResourceKind.REQUEST.value,
        result_count=len(items),
        query_shape={"status": "ACTIVE"},
    )
    return {"items": items}


@router.get("/requests/{request_id}", operation_id="getRequestsRequestId")
def get_request_internal(request: Request, request_id: uuid.UUID, access: Access):
    """Internal arbitrary-id read. x-roles excludes CUSTOMER (K01)."""
    decision = access.authorize_operation("getRequestsRequestId")
    if not decision.allowed:
        return for_denial(
            decision.reason, trace_id_of(request), customer_scoped=False,
            detail=decision.detail,
        )
    return problem(
        501, "NOT_IMPLEMENTED", "Not implemented", trace_id_of(request),
        "staff request projection belongs to Slice 2",
    )
