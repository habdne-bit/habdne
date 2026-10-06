"""/me/* — the customer-scoped reads.

Ref: RFC-001 §5, decision 2.

Note what this module imports: the access service and the problem helpers. No
session, no repository, no SQLAlchemy. A route here cannot issue a query even
if someone tries (R10.3), which is enforced by an architecture test.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response

from ...auth.loaders import ResourceKind
from ...dto import (
    Audience,
    CustomerPartyView,
    CustomerPropertyView,
    CustomerRequestView,
    assert_no_forbidden_fields,
)
from ..deps import Access
from ..problems import for_denial, trace_id_of
from ..responses import ExactJSONResponse

router = APIRouter(prefix="/me", tags=["Me"])


#: A row is never returned as-is. Each kind is rendered through its customer
#: type, so an internal column added to a table cannot reach a customer (R9.1).
_RENDERERS = {
    ResourceKind.PARTY: CustomerPartyView.render,
    ResourceKind.REQUEST: CustomerRequestView.render,
    ResourceKind.PROPERTY: CustomerPropertyView.render,
}


def _render(kind: ResourceKind, row) -> dict:
    payload = _RENDERERS[kind](row).model_dump(mode="json")
    # Belt and braces: the type already constrains this, and this makes a
    # regression loud rather than silent.
    assert_no_forbidden_fields(payload, Audience.CUSTOMER)
    return payload


def _respond(access: Access, request: Request, kind: ResourceKind,
             resource_id: uuid.UUID, operation_id: str) -> Response | dict:
    decision = access.authorize_operation(operation_id)
    if not decision.allowed:
        return for_denial(
            decision.reason, trace_id_of(request), customer_scoped=True,
            detail=decision.detail,
        )
    result = access.read_resource(kind, resource_id, operation_id)
    if not result.authorized:
        return for_denial(
            result.reason, trace_id_of(request), customer_scoped=True,
        )
    return _render(kind, result.row)


@router.get("/party", operation_id="getMeParty")
def get_me_party(request: Request, access: Access):
    """R5.1. No arbitrary party id is accepted; the subject is the only input."""
    decision = access.authorize_operation("getMeParty")
    if not decision.allowed:
        return for_denial(
            decision.reason, trace_id_of(request), customer_scoped=True,
            detail=decision.detail,
        )
    result = access.read_resource(
        ResourceKind.PARTY, access.subject.party_id, "getMeParty"
    )
    if not result.authorized:
        return for_denial(result.reason, trace_id_of(request), customer_scoped=True)
    return _render(ResourceKind.PARTY, result.row)


@router.get("/requests/{request_id}", operation_id="getMeRequestsRequestId")
def get_me_request(request: Request, request_id: uuid.UUID, access: Access):
    return _respond(access, request, ResourceKind.REQUEST, request_id,
                    "getMeRequestsRequestId")


@router.get("/properties/{property_id}", operation_id="getMePropertiesPropertyId")
def get_me_property(request: Request, property_id: uuid.UUID, access: Access):
    return _respond(access, request, ResourceKind.PROPERTY, property_id,
                    "getMePropertiesPropertyId")


@router.get("/opportunities/{opportunity_id}", operation_id="getMeOpportunitiesOpportunityId")
def get_me_opportunity(request: Request, opportunity_id: uuid.UUID, access: Access):
    """The frozen `CustomerOpportunityView` (Slice 5 step 4; G5-6 (a), G5-7 (a),
    [R4-2]; RFC-001 Appendix B).

    The loader authorizes through `opportunities.request_id ->
    requests.party_id` and admits a SHARED opportunity only: an unshared or
    another party's opportunity gets the answer an unknown id gets. The body
    is rendered through the scope ladder, with the withholding of entries
    whose field changed since the evaluation, and numbers written exactly.
    """
    decision = access.authorize_operation("getMeOpportunitiesOpportunityId")
    if not decision.allowed:
        return for_denial(
            decision.reason, trace_id_of(request), customer_scoped=True,
            detail=decision.detail,
        )
    result = access.read_resource(
        ResourceKind.OPPORTUNITY, opportunity_id, "getMeOpportunitiesOpportunityId"
    )
    if not result.authorized:
        return for_denial(result.reason, trace_id_of(request), customer_scoped=True)
    payload = access.customer_opportunity(opportunity_id)
    assert_no_forbidden_fields(payload, Audience.CUSTOMER)
    return ExactJSONResponse(content=payload)
