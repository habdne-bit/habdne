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
from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...auth.loaders import ResourceKind
from ...services import freshness as freshness_service
from ...services import requests as request_service
from ...services.requests import UpdateChannel
from ...services.concurrency import HEADER, IfMatchRequired, parse_if_match
from ..deps import Access, Command
from ..problems import ProblemCode, coded, for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["Requests"])

IMPORTANCE = "^(REQUIRED|PREFERRED|FLEXIBLE)$"

#: The contract's `property_type` enumeration, and the columns that are NOT
#: nullable in the frozen schema. Declared once so the create and patch models
#: cannot drift apart from each other or from the contract.
PROPERTY_TYPES = (
    "HOUSE_VILLA", "APARTMENT", "LAND", "SHOP_COMMERCIAL",
    "AGRICULTURAL_PROPERTY", "BUILDING", "OTHER",
)
PROPERTY_TYPE_PATTERN = "^(" + "|".join(PROPERTY_TYPES) + ")$"


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RequestCriterionInput(_Body):
    #: Declared by the contract's `RequestCriterion`. Present -> CHANGE that
    #: criterion; absent -> ADD one. The endpoint "adds/changes structured
    #: criteria" (API_CONTRACTS v0.2), and this is the field that selects
    #: which, so no new field is invented to carry it (R-S2-03).
    request_criterion_id: uuid.UUID | None = None
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
    desired_property_type: str | None = Field(default=None, pattern=PROPERTY_TYPE_PATTERN)
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

    @model_validator(mode="after")
    def _budgets_are_coherent(self):
        """`CHECK (budget_target_dzd <= budget_max_dzd)`, enforced where both
        values are present in the body.

        On a create the pair is fully supplied, so the model can decide it and
        the caller gets a field-level error. A PATCH may supply only one, and
        the coherence of the RESULT depends on the current row — that check
        lives in the route, against the merged values.
        """
        conflict = _budget_conflict(self.budget_target_dzd, self.budget_max_dzd)
        if conflict:
            raise ValueError(conflict)
        return self


class RequestPatch(_Body):
    """Every field here is OPTIONAL, and `None` means "not supplied" only for
    the columns the schema actually allows to be null.

    `intent`, `payment` and `budget_flexibility` are `NOT NULL` in the frozen
    schema and non-nullable in the contract, so they are typed as plain
    strings with a default sentinel rather than `str | None` — an earlier
    version accepted `{"intent": null}`, which passed validation and then
    reached PostgreSQL as a NOT NULL violation, surfacing as a 500 (R-S2-05).

    `desired_property_type`, `primary_location_id` and the budgets ARE
    nullable in the schema and in the contract, so `null` is a real value for
    them: it clears the field.
    """

    # Non-nullable: absent or a valid value, never null.
    intent: str = Field(default="", pattern="^(EXPLORING|ACTIVE_SEARCH|READY_TO_ACT)$")
    payment: str = Field(default="", pattern="^(CASH|BANK_FINANCING|MIXED|UNDECIDED)$")
    budget_flexibility: str = Field(
        default="", pattern="^(STRICT|LOW|MODERATE|HIGH|UNSPECIFIED)$"
    )
    # Nullable in the schema: null clears the value.
    desired_property_type: str | None = Field(default=None, pattern=PROPERTY_TYPE_PATTERN)
    primary_location_id: uuid.UUID | None = None
    local_location_detail: str | None = None
    budget_target_dzd: int | None = Field(default=None, ge=0)
    budget_max_dzd: int | None = Field(default=None, ge=0)


class RequestStateCommand(_Body):
    target_status: str = Field(
        pattern="^(CONTACTED|QUALIFIED|ACTIVE|NEEDS_CONFIRMATION|PAUSED|CLOSED)$"
    )
    reason_code: str | None = None
    note: str | None = None
    # No `reactivate` field. An earlier draft added one; it was not in the
    # contract, and `extra="forbid"` above means every field here is part of
    # the declared shape. Sending `target_status=ACTIVE` from PAUSED or CLOSED
    # IS the explicit reactivation §5.2 asks for — a second flag would be a
    # second way of saying the same thing.


class StateReconfirm(_Body):
    confirmed_at: datetime | None = None
    notes: str | None = None


def access_free_budget_check(command, request_id, changes) -> str | None:
    """Merge the patch over the current row and check the budget pair.

    Read on the command's READ session, the same one its object checks use:
    the write session must own the transaction the command commits.
    """
    current = command.read_current(
        "requests", request_id, ("budget_target_dzd", "budget_max_dzd")
    )
    if current is None:
        return None
    target = changes.get("budget_target_dzd", current["budget_target_dzd"])
    maximum = changes.get("budget_max_dzd", current["budget_max_dzd"])
    return _budget_conflict(target, maximum)


def _budget_conflict(target, maximum) -> str | None:
    """The schema's `CHECK (budget_target_dzd <= budget_max_dzd)`, checked
    before SQL so it is a typed 422 rather than a constraint violation.

    For a PATCH this must be evaluated on the MERGED values — the supplied
    fields applied over the current row — because a patch that sets only the
    target can still break the pair (R-S2-05).
    """
    if target is not None and maximum is not None and target > maximum:
        return (
            f"budget_target_dzd ({target}) cannot exceed budget_max_dzd ({maximum})"
        )
    return None


def _channel(command) -> UpdateChannel:
    """Who is recording this, as a fact about the actor's role — not a claim
    about who asked for the change."""
    return (UpdateChannel.STAFF_RECORDED if command.is_staff
            else UpdateChannel.SELF_SERVICE)


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
    conflict = _budget_conflict(body.budget_target_dzd, body.budget_max_dzd)
    if conflict:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request), conflict)

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
                request_criterion_id=criterion.request_criterion_id,
                recorded_by_account_id=command.subject.account_id,
                channel=_channel(command),
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
    body = _internal_request(
        result.row, fresh, access.request_criteria(request_id)
    )
    # Additive, and the point of it: a reader must be able to tell a change
    # the party made themselves from one a staff member typed, and whether
    # any call or message was recorded behind it. Without that distinction a
    # staff-entered value reads as the customer's own words.
    body["provenance"] = [
        {
            "attribute_code": c["attribute_code"],
            "value": c["claimed_value"],
            "channel": c["channel"],
            "recorded_at": c["recorded_at"].isoformat(),
            "recorded_by_account_id": (str(c["recorded_by_account_id"])
                                       if c["recorded_by_account_id"] else None),
            "asserted_by_party_id": (str(c["asserted_by_party_id"])
                                     if c["asserted_by_party_id"] else None),
            "source_recorded": c["source_recorded"],
            "verification_level": c["verification_level"],
            "previous": (c["observation_payload"] or {}).get("before", {}).get(
                c["attribute_code"]
            ),
        }
        for c in access.request_provenance(request_id)
    ]
    return body


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
    # The non-nullable fields use "" as their "not supplied" sentinel, so an
    # explicit `null` for one of them arrives here as "" and is refused by
    # name rather than reaching a NOT NULL column (R-S2-05).
    nulled = [k for k, v in changes.items() if v == ""]
    if nulled:
        return coded(
            ProblemCode.VALIDATION_FAILED, trace_id_of(request),
            f"{sorted(nulled)} cannot be null; omit the field to leave it unchanged.",
        )
    if not changes:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request),
                     "at least one field must be supplied.")

    # The budget pair must be coherent AFTER the patch is applied, so it is
    # checked against the merged values, not against the submitted ones.
    merged = access_free_budget_check(command, request_id, changes)
    if merged:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request), merged)

    def handler(session):
        row = request_service.patch_request(
            session, request_id=request_id, changes=changes,
            recorded_by_account_id=command.subject.account_id,
            channel=_channel(command),
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
            request_criterion_id=body.request_criterion_id,
            recorded_by_account_id=command.subject.account_id,
            channel=_channel(command),
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

    Reactivation from PAUSED or CLOSED is this command with
    `target_status=ACTIVE`. It does not refresh `last_confirmed_at`.
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
            recorded_by_account_id=command.subject.account_id,
            channel=_channel(command),
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
            channel=_channel(command),
        )
        return 200, _internal_request(row)

    return _run(request, command, "postRequestsRequestIdReconfirm",
                f"POST /requests/{request_id}/reconfirm",
                body.model_dump(mode="json"), handler, 200,
                extra_errors=request_service.RequestError)
