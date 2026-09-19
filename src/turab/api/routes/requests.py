"""REQUEST endpoints — Slice 2.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 2; Developer Reference Spec §5.2,
§15.1; RFC-001 §4.8, R10.3/Q6.

Like every route module: no session, no repository, no SQLAlchemy.

The three commands that could plausibly have been one are deliberately three,
matching the contract's three bodies:

    PATCH  /requests/{id}            what the buyer wants
    POST   /requests/{id}/state      where the request is in its workflow
    POST   /requests/{id}/reconfirm  when the information was last confirmed

A single "update" that did all three would make it impossible to tell, from
the record, whether a buyer changed their mind or an operator merely rang to
check — which is exactly the distinction STOP GATE B asks a staff member to
be able to make.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from ...auth.loaders import ResourceKind
from ...services import freshness as freshness_service
from ...services import requests as request_service
from ...services.concurrency import HEADER, IfMatchRequired, parse_if_match
from ..deps import Access, Command
from ..problems import ProblemCode, coded, for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["Requests"])

IMPORTANCE = "^(REQUIRED|PREFERRED|FLEXIBLE)$"


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestCriterionInput(_Body):
    criterion_code: str
    importance: str = Field(pattern=IMPORTANCE)
    operator: str = Field(
        pattern="^(EQ|NEQ|IN|NOT_IN|GTE|LTE|BETWEEN|EXISTS|BOOL|TEXT_SEMANTIC)$"
    )
    value: Any
    unit: str | None = None
    blocking_if_unknown: bool = False
    sort_order: int = 100


class RequestCreate(_Body):
    party_id: uuid.UUID
    transaction_intent: str = Field(pattern="^(BUY|RENT)$")
    intent: str = Field(pattern="^(EXPLORING|ACTIVE_SEARCH|READY_TO_ACT)$")
    management_mode: str = Field(pattern="^(SELF_MANAGED|ASSISTED|SHARED_MANAGEMENT)$")
    claim_status: str = Field(pattern="^(UNCLAIMED|CLAIMED)$")
    payment: str | None = Field(default=None, pattern="^(CASH|BANK_FINANCING|MIXED|UNDECIDED)$")
    desired_property_type: str | None = None
    property_type_importance: str | None = Field(default=None, pattern=IMPORTANCE)
    primary_location_id: uuid.UUID | None = None
    location_importance: str | None = Field(default=None, pattern=IMPORTANCE)
    local_location_detail: str | None = None
    budget_target_dzd: int | None = Field(default=None, ge=0)
    budget_max_dzd: int | None = Field(default=None, ge=0)
    budget_importance: str | None = Field(default=None, pattern=IMPORTANCE)
    budget_flexibility: str | None = Field(
        default=None, pattern="^(STRICT|LOW|MODERATE|HIGH|UNSPECIFIED)$"
    )
    criteria: list[RequestCriterionInput] | None = None


class RequestPatch(_Body):
    intent: str | None = Field(default=None, pattern="^(EXPLORING|ACTIVE_SEARCH|READY_TO_ACT)$")
    payment: str | None = Field(default=None, pattern="^(CASH|BANK_FINANCING|MIXED|UNDECIDED)$")
    desired_property_type: str | None = None
    primary_location_id: uuid.UUID | None = None
    local_location_detail: str | None = None
    budget_target_dzd: int | None = Field(default=None, ge=0)
    budget_max_dzd: int | None = Field(default=None, ge=0)
    budget_flexibility: str | None = Field(
        default=None, pattern="^(STRICT|LOW|MODERATE|HIGH|UNSPECIFIED)$"
    )


class RequestStateCommand(_Body):
    target_status: str = Field(
        pattern="^(CONTACTED|QUALIFIED|ACTIVE|NEEDS_CONFIRMATION|PAUSED|CLOSED)$"
    )
    reason_code: str | None = None
    note: str | None = None
    #: Not in the frozen schema: §5.2 requires leaving PAUSED/CLOSED to be
    #: EXPLICIT, and the contract gives no way to say so. Accepted as an
    #: optional extra rather than inferred, and reported as a contract gap.
    reactivate: bool = False


class StateReconfirm(_Body):
    confirmed_at: datetime | None = None
    notes: str | None = None


def _internal_request(row, fresh=None, criteria=None) -> dict[str, Any]:
    """The contract's `Request` schema — a staff view.

    `freshness` is additive and computed, never stored: the contract has no
    field for it, and duplicating a derived value into the row would create a
    second truth that can disagree with `last_confirmed_at`.
    """
    body = {
        "request_id": str(row["request_id"]),
        "party_id": str(row["party_id"]),
        "status": row["status"],
        "transaction_intent": row["transaction_intent"],
        "intent": row["intent"],
        "payment": row["payment"],
        "desired_property_type": row["desired_property_type"],
        "property_type_importance": row["property_type_importance"],
        "primary_location_id": (str(row["primary_location_id"])
                                if row["primary_location_id"] else None),
        "location_importance": row["location_importance"],
        "local_location_detail": row["local_location_detail"],
        "budget_target_dzd": row["budget_target_dzd"],
        "budget_max_dzd": row["budget_max_dzd"],
        "budget_importance": row["budget_importance"],
        "budget_flexibility": row["budget_flexibility"],
        "last_confirmed_at": (row["last_confirmed_at"].isoformat()
                              if row["last_confirmed_at"] else None),
        "management_mode": row["management_mode"],
        "claim_status": row["claim_status"],
        "version": row["version"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }
    if criteria is not None:
        # The contract's `Request` is allOf[RequestCreate, ...] and
        # `RequestCreate` carries `criteria`, so they belong in this payload.
        # Without them a staff reader can see the budget but not whether the
        # buyer called it hard or merely hoped-for, which is half of what
        # STOP GATE B asks them to know.
        body["criteria"] = [
            {
                "request_criterion_id": str(c["request_criterion_id"]),
                "criterion_code": c["criterion_code"],
                "importance": c["importance"],
                "operator": c["operator"],
                "value": c["value"],
                "unit": c["unit"],
                "blocking_if_unknown": c["blocking_if_unknown"],
                "sort_order": c["sort_order"],
            }
            for c in criteria
        ]
    if fresh is not None:
        body["freshness"] = {
            "state": fresh.state.value,
            "threshold_days": fresh.threshold_days,
            "policy_version": fresh.policy_version,
        }
    return body


def _request_error(exc: request_service.RequestError, trace: str):
    code = (ProblemCode[exc.code] if exc.code in ProblemCode.__members__
            else ProblemCode.VALIDATION_FAILED)
    return coded(code, trace, str(exc))


# --- creation --------------------------------------------------------------

@router.post("/requests", operation_id="postRequests", status_code=201)
def create_request(request: Request, body: RequestCreate, command: Command):
    """Self-managed creation by the customer, or assisted creation by staff.

    The object rule here is the one the Design Ledger insists on (DL-02): a
    customer may create a request only for THEIR OWN party, established from
    the account's binding — never inferred from a phone number or any other
    shared attribute.
    """
    decision = command.authorize("postRequests")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    scope = command.authorize_party_scope(body.party_id)
    if not scope.allowed:
        return for_denial(scope.reason, trace_id_of(request),
                          customer_scoped=False, detail=scope.detail)

    # A customer creates their own record, so it is theirs from the first
    # moment: SELF_MANAGED/CLAIMED. ASSISTED means staff are operating a
    # record on someone's behalf, and that record is UNCLAIMED until the
    # person claims it — which is a different flow, not a different flag.
    if not command.is_staff and body.management_mode != "SELF_MANAGED":
        return coded(
            ProblemCode.VALIDATION_FAILED, trace_id_of(request),
            "a customer creates a SELF_MANAGED request; assisted records are "
            "created by staff and claimed afterwards",
        )

    def handler(session):
        row = request_service.create_request(
            session,
            party_id=body.party_id,
            transaction_intent=body.transaction_intent,
            intent=body.intent,
            management_mode=body.management_mode,
            claim_status=body.claim_status,
            created_by_account_id=command.subject.account_id,
            payment=body.payment,
            desired_property_type=body.desired_property_type,
            property_type_importance=body.property_type_importance,
            primary_location_id=body.primary_location_id,
            location_importance=body.location_importance,
            local_location_detail=body.local_location_detail,
            budget_target_dzd=body.budget_target_dzd,
            budget_max_dzd=body.budget_max_dzd,
            budget_importance=body.budget_importance,
            budget_flexibility=body.budget_flexibility,
        )
        for criterion in body.criteria or []:
            request_service.add_criterion(
                session, request_id=row["request_id"],
                criterion_code=criterion.criterion_code,
                importance=criterion.importance, operator=criterion.operator,
                value=criterion.value, unit=criterion.unit,
                blocking_if_unknown=criterion.blocking_if_unknown,
                sort_order=criterion.sort_order,
                recorded_by_account_id=command.subject.account_id,
            )
        return 201, _internal_request(
            request_service.read_request(session, row["request_id"])
        )

    return _run(request, command, "postRequests", "POST /requests",
                body.model_dump(mode="json"), handler, 201,
                extra_errors=request_service.RequestError)


# --- staff read ------------------------------------------------------------

@router.get("/requests/{request_id}", operation_id="getRequestsRequestId")
def read_request(request: Request, request_id: uuid.UUID, access: Access):
    """Internal read. x-roles excludes CUSTOMER; customers use /me/requests."""
    decision = access.authorize_operation("getRequestsRequestId")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    result = access.read_staff_resource(
        ResourceKind.REQUEST, request_id, "getRequestsRequestId"
    )
    if not result.authorized:
        return for_denial(result.reason, trace_id_of(request), customer_scoped=False)
    fresh = access.evaluate_request_freshness(result.row["last_confirmed_at"])
    return _internal_request(
        result.row, fresh, access.request_criteria(request_id)
    )


# --- typed update ----------------------------------------------------------

@router.patch("/requests/{request_id}", operation_id="patchRequestsRequestId")
def update_request(
    request: Request,
    request_id: uuid.UUID,
    body: RequestPatch,
    command: Command,
    if_match_version: Annotated[str | None, Header(alias=HEADER)] = None,
):
    """Change what the buyer wants — not the status, not the confirmation."""
    decision = command.authorize("patchRequestsRequestId")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    scope = command.authorize_request_scope(request_id)
    if not scope.allowed:
        return for_denial(scope.reason, trace_id_of(request),
                          customer_scoped=False, detail=scope.detail)
    try:
        expected = parse_if_match(if_match_version)
    except IfMatchRequired:
        return coded(ProblemCode.IF_MATCH_REQUIRED, trace_id_of(request))
    except Exception:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request),
                     f"{HEADER} must be the integer version last read.")

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request),
                     "at least one field must be supplied.")

    def handler(session):
        row = request_service.patch_request(
            session, request_id=request_id, changes=changes,
            recorded_by_account_id=command.subject.account_id,
        )
        return 200, _internal_request(row)

    return _run(request, command, "patchRequestsRequestId",
                f"PATCH /requests/{request_id}",
                body.model_dump(mode="json", exclude_unset=True), handler, 200,
                version_guard=("requests", request_id, expected),
                extra_errors=request_service.RequestError)


# --- criteria --------------------------------------------------------------

@router.post("/requests/{request_id}/criteria",
             operation_id="postRequestsRequestIdCriteria", status_code=201)
def add_criterion(request: Request, request_id: uuid.UUID,
                  body: RequestCriterionInput, command: Command):
    """Add a structured criterion. Bumps the request's version (Slice 2)."""
    decision = command.authorize("postRequestsRequestIdCriteria")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    scope = command.authorize_request_scope(request_id)
    if not scope.allowed:
        return for_denial(scope.reason, trace_id_of(request),
                          customer_scoped=False, detail=scope.detail)

    def handler(session):
        row = request_service.add_criterion(
            session, request_id=request_id,
            criterion_code=body.criterion_code, importance=body.importance,
            operator=body.operator, value=body.value, unit=body.unit,
            blocking_if_unknown=body.blocking_if_unknown,
            sort_order=body.sort_order,
            recorded_by_account_id=command.subject.account_id,
        )
        return 201, {
            "request_criterion_id": str(row["request_criterion_id"]),
            "criterion_code": row["criterion_code"],
            "importance": row["importance"],
            "operator": row["operator"],
            "value": row["value"],
            "unit": row["unit"],
            "blocking_if_unknown": row["blocking_if_unknown"],
            "sort_order": row["sort_order"],
        }

    return _run(request, command, "postRequestsRequestIdCriteria",
                f"POST /requests/{request_id}/criteria",
                body.model_dump(mode="json"), handler, 201,
                extra_errors=request_service.RequestError)


# --- state transition ------------------------------------------------------

@router.post("/requests/{request_id}/state",
             operation_id="postRequestsRequestIdState")
def change_state(request: Request, request_id: uuid.UUID,
                 body: RequestStateCommand, command: Command):
    """Move through the state machine documented in Reference Spec §5.2.

    Targets the contract permits but the state machine does not define are
    refused, naming the defined targets. Inventing an edge would add a
    workflow rule to TURAB by implementation accident.
    """
    decision = command.authorize("postRequestsRequestIdState")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    scope = command.authorize_request_scope(request_id)
    if not scope.allowed:
        return for_denial(scope.reason, trace_id_of(request),
                          customer_scoped=False, detail=scope.detail)

    def handler(session):
        row = request_service.transition(
            session, request_id=request_id, target_status=body.target_status,
            reason_code=body.reason_code, note=body.note,
            reactivate=body.reactivate,
            recorded_by_account_id=command.subject.account_id,
        )
        return 200, _internal_request(row)

    return _run(request, command, "postRequestsRequestIdState",
                f"POST /requests/{request_id}/state",
                body.model_dump(mode="json"), handler, 200,
                extra_errors=request_service.RequestError)


# --- reconfirmation --------------------------------------------------------

@router.post("/requests/{request_id}/reconfirm",
             operation_id="postRequestsRequestIdReconfirm")
def reconfirm_request(request: Request, request_id: uuid.UUID,
                      body: StateReconfirm, command: Command):
    """Record that the information is still current — and nothing else."""
    decision = command.authorize("postRequestsRequestIdReconfirm")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    scope = command.authorize_request_scope(request_id)
    if not scope.allowed:
        return for_denial(scope.reason, trace_id_of(request),
                          customer_scoped=False, detail=scope.detail)

    def handler(session):
        row = request_service.reconfirm(
            session, request_id=request_id, confirmed_at=body.confirmed_at,
            notes=body.notes,
            recorded_by_account_id=command.subject.account_id,
        )
        return 200, _internal_request(row)

    return _run(request, command, "postRequestsRequestIdReconfirm",
                f"POST /requests/{request_id}/reconfirm",
                body.model_dump(mode="json"), handler, 200,
                extra_errors=request_service.RequestError)
