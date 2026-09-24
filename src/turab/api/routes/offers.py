"""OFFER endpoints — Slice 3, step 2.

Ref: the effective contract's `OfferCreate`, `OfferPatch`,
`OfferStateCommand`, `PropertyOffer` and the `postOffersOfferIdSources` body;
RFC-001 §4.6 (R4.12, R4.13); R9.2 / ADR-06 (the DTO floor);
`docs/gate/SLICE_3_PLAN.md` §3.5, §3.6.

Like every route module: no session, no repository, no SQLAlchemy.

**`seller_expectation_dzd` never reaches a customer.** `PropertyOffer`
declares it as an OPTIONAL property, so omitting it conforms to the contract,
and the contract's own description of the field says "Never expose in
customer/public DTOs". A customer may still SEND it — `OfferCreate` and
`OfferPatch` declare it for every role the operation admits — and it is stored;
it is simply never rendered back to a CUSTOMER audience, including the
customer who sent it.

`postOffersOfferIdReconfirm` (step 4) writes both confirmation columns
together; the `offer_terms` freshness policy reads only the commercial-terms
one (plan §3.4).
"""
from __future__ import annotations

import uuid
from typing import Annotated, Any

from datetime import datetime

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...dto.boundaries import Audience, assert_no_forbidden_fields
from ...services import offers as offer_service
from ...services.concurrency import HEADER, IfMatchRequired, parse_if_match
from ...services.provenance import UpdateChannel
from ..deps import Command
from ..json_types import JsonInteger
from ..problems import ProblemCode, coded, for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["Properties"])

TRANSACTION_TYPE_PATTERN = "^(SALE|RENT)$"
NEGOTIABLE_PATTERN = "^(YES|NO|UNKNOWN)$"
VISIBILITY_PATTERN = "^(PUBLIC|ON_REQUEST|PRIVATE)$"
SCOPE_PATTERN = "^(SUMMARY_ONLY|PROPERTY_DETAILS_ALLOWED|CONTACT_AFTER_CONFIRMATION)$"
STATUS_PATTERN = "^(DRAFT|PENDING_INFO|ACTIVE|PAUSED|WITHDRAWN|CLOSED)$"


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OfferCreate(_Body):
    """`OfferCreate`, field for field.

    Every optional field is omissible and NONE is nullable in the contract,
    so each uses a sentinel default and the route reads `model_fields_set` to
    learn what was actually sent (the step-1 lesson: omitted is not the same
    as empty, and `0` is a price).
    """

    party_id: uuid.UUID
    transaction_type: str = Field(pattern=TRANSACTION_TYPE_PATTERN)
    asking_price_dzd: JsonInteger = Field(default=0, ge=0)
    raw_price_text: str = ""
    price_negotiable: str = Field(default="UNKNOWN", pattern=NEGOTIABLE_PATTERN)
    seller_expectation_dzd: JsonInteger = Field(default=0, ge=0)
    price_visibility: str = Field(default="PUBLIC", pattern=VISIBILITY_PATTERN)
    permission_scope: str = Field(default="SUMMARY_ONLY", pattern=SCOPE_PATTERN)


class OfferPatch(_Body):
    """`OfferPatch`, field for field.

    Nullable in the contract: `asking_price_dzd`, `raw_price_text`,
    `seller_expectation_dzd` — `null` clears them. NOT nullable:
    `price_negotiable`, `price_visibility` — typed as plain strings, so `null`
    is a field error rather than a NOT NULL violation surfacing as a 500.
    """

    asking_price_dzd: JsonInteger | None = Field(default=None, ge=0)
    raw_price_text: str | None = None
    price_negotiable: str = Field(default="", pattern=NEGOTIABLE_PATTERN)
    seller_expectation_dzd: JsonInteger | None = Field(default=None, ge=0)
    price_visibility: str = Field(default="", pattern=VISIBILITY_PATTERN)


class OfferStateCommand(_Body):
    status: str = Field(pattern=STATUS_PATTERN)
    reason_code: str | None = None


class StateReconfirm(_Body):
    """`StateReconfirm` — the body the request reconfirm also takes. The
    R-S2-05b refusal of an offset-less `confirmed_at` is applied HERE and
    tested on this endpoint, not assumed to carry over (plan §3.4)."""

    confirmed_at: datetime = None  # type: ignore[assignment]
    notes: str = None  # type: ignore[assignment]

    @field_validator("confirmed_at")
    @classmethod
    def _an_instant(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError(
                "must carry a timezone offset (for example 2026-01-01T12:00:00Z); "
                "a local time with no offset does not identify a moment")
        return value


class OfferSourceLink(_Body):
    """The inline body of `postOffersOfferIdSources`.

    The contract leaves this body OPEN (no `additionalProperties: false`).
    Unknown keys are refused here all the same — the same choice Slice 2 made
    for the equally open `RequestCriterion` body — because silently dropping
    a key the caller believed meaningful is worse than telling them.
    """

    source_id: uuid.UUID
    is_primary: bool = False


def _channel(command) -> UpdateChannel:
    return (UpdateChannel.STAFF_RECORDED if command.is_staff
            else UpdateChannel.SELF_SERVICE)


def _audience(command) -> Audience:
    return Audience.INTERNAL if command.is_staff else Audience.CUSTOMER


def _view(row, audience: Audience) -> dict[str, Any]:
    """`PropertyOffer`, and nothing beyond it.

    `allOf [OfferCreate, {...}]` with `OfferCreate` closed, so: no key the
    schema does not declare; an optional NON-nullable field is OMITTED when it
    has no value; the two confirmation timestamps are declared nullable and
    are sent as `null`.

    For a CUSTOMER audience `seller_expectation_dzd` is never included, and
    the payload is then checked against the R9.2 floor, so a leak would be a
    500 in a test rather than a field in a response.
    """
    view: dict[str, Any] = {
        "offer_id": str(row["offer_id"]),
        "property_id": str(row["property_id"]),
        "party_id": str(row["party_id"]),
        "transaction_type": row["transaction_type"],
        "status": row["status"],
        "price_negotiable": row["price_negotiable"],
        "price_visibility": row["price_visibility"],
        "permission_scope": row["permission_scope"],
        "version": row["version"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
        "last_confirmed_at": (row["last_confirmed_at"].isoformat()
                              if row["last_confirmed_at"] else None),
        "commercial_terms_last_confirmed_at": (
            row["commercial_terms_last_confirmed_at"].isoformat()
            if row["commercial_terms_last_confirmed_at"] else None),
    }
    if row["asking_price_dzd"] is not None:
        view["asking_price_dzd"] = int(row["asking_price_dzd"])
    if row["raw_price_text"] is not None:
        view["raw_price_text"] = row["raw_price_text"]
    if audience is Audience.INTERNAL and row["seller_expectation_dzd"] is not None:
        view["seller_expectation_dzd"] = int(row["seller_expectation_dzd"])
    assert_no_forbidden_fields(view, audience)
    return view


@router.post("/properties/{property_id}/offers",
             operation_id="postPropertiesPropertyIdOffers", status_code=201)
def create_offer(request: Request, property_id: uuid.UUID, body: OfferCreate,
                 command: Command):
    """Create an offer on a physical property, in `DRAFT`.

    For a CUSTOMER, two object checks, both from the contract's
    `x-authorization` ("may act only on resources owned/managed by
    authenticated party"):

      1. the parent PROPERTY is theirs under R4.1 — reusing `load_property`,
         so a property they may not see is a 404, indistinguishable from one
         that does not exist;
      2. `party_id` is THEIR party. Otherwise condition 1 of §4.6 would hand
         them creator authority over an offer made in another party's name.
    """
    decision = command.authorize("postPropertiesPropertyIdOffers")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    scope = command.authorize_property_scope(property_id)
    if not scope.allowed:
        return for_denial(scope.reason, trace_id_of(request),
                          customer_scoped=not command.is_staff,
                          detail=scope.detail)
    party = command.authorize_party_scope(body.party_id)
    if not party.allowed:
        return for_denial(party.reason, trace_id_of(request),
                          customer_scoped=False, detail=party.detail)

    supplied = body.model_fields_set
    optional = {name: getattr(body, name)
                for name in offer_service.CREATE_OPTIONAL if name in supplied}

    def handler(session):
        row = offer_service.create_offer(
            session,
            property_id=property_id,
            party_id=body.party_id,
            transaction_type=body.transaction_type,
            created_by_account_id=command.subject.account_id,
            recorded_by_account_id=command.subject.account_id,
            channel=_channel(command),
            **optional,
        )
        return 201, _view(row, _audience(command))

    return _run(request, command, "postPropertiesPropertyIdOffers",
                f"POST /properties/{property_id}/offers",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=offer_service.OfferError)


@router.patch("/offers/{offer_id}", operation_id="patchOffersOfferId")
def patch_offer(
    request: Request,
    offer_id: uuid.UUID,
    body: OfferPatch,
    command: Command,
    if_match_version: Annotated[str | None, Header(alias=HEADER)] = None,
):
    """Change the terms of an offer. Never its state, party, transaction type
    or sharing scope — the contract's patch body does not declare them."""
    decision = command.authorize("patchOffersOfferId")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    scope = command.authorize_offer_scope(offer_id)
    if not scope.allowed:
        return for_denial(scope.reason, trace_id_of(request),
                          customer_scoped=not command.is_staff,
                          detail=scope.detail)
    try:
        expected = parse_if_match(if_match_version)
    except IfMatchRequired:
        return coded(ProblemCode.IF_MATCH_REQUIRED, trace_id_of(request),
                     f"{HEADER} must be the integer version last read.")

    changes = body.model_dump(exclude_unset=True)
    # The two non-nullable fields carry "" as "not supplied". Their patterns
    # reject "" before this point; kept as a narrow assertion, not a filter.
    for name in ("price_negotiable", "price_visibility"):
        if changes.get(name) == "":
            return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request),
                         f"{name} cannot be empty; omit it to leave it unchanged.")
    if not changes:
        # `OfferPatch` declares `minProperties: 1`.
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request),
                     "at least one field must be supplied.")

    def handler(session):
        row = offer_service.patch_offer(
            session, offer_id=offer_id, changes=changes,
            recorded_by_account_id=command.subject.account_id,
            channel=_channel(command),
        )
        return 200, _view(row, _audience(command))

    return _run(request, command, "patchOffersOfferId", f"PATCH /offers/{offer_id}",
                body.model_dump(mode="json", exclude_unset=True), handler, 200,
                version_guard=("property_offers", offer_id, expected),
                extra_errors=offer_service.OfferError)


@router.post("/offers/{offer_id}/state", operation_id="postOffersOfferIdState")
def change_offer_state(request: Request, offer_id: uuid.UUID,
                       body: OfferStateCommand, command: Command):
    """The ratified machine (plan §3.5), with the CUSTOMER narrowing applied
    as a second gate after the edge check."""
    decision = command.authorize("postOffersOfferIdState")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    scope = command.authorize_offer_scope(offer_id)
    if not scope.allowed:
        return for_denial(scope.reason, trace_id_of(request),
                          customer_scoped=not command.is_staff,
                          detail=scope.detail)

    def handler(session):
        row = offer_service.transition(
            session, offer_id=offer_id, target_status=body.status,
            reason_code=body.reason_code, customer=not command.is_staff,
            recorded_by_account_id=command.subject.account_id,
            channel=_channel(command),
        )
        return 200, _view(row, _audience(command))

    return _run(request, command, "postOffersOfferIdState",
                f"POST /offers/{offer_id}/state",
                body.model_dump(mode="json", exclude_unset=True), handler, 200,
                extra_errors=offer_service.OfferError)


@router.post("/offers/{offer_id}/reconfirm", operation_id="postOffersOfferIdReconfirm")
def reconfirm_offer(request: Request, offer_id: uuid.UUID, body: StateReconfirm,
                    command: Command):
    decision = command.authorize("postOffersOfferIdReconfirm")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    scope = command.authorize_offer_scope(offer_id)
    if not scope.allowed:
        return for_denial(scope.reason, trace_id_of(request),
                          customer_scoped=not command.is_staff,
                          detail=scope.detail)

    def handler(session):
        row = offer_service.reconfirm(
            session, offer_id=offer_id, confirmed_at=body.confirmed_at,
            notes=body.notes, recorded_by_account_id=command.subject.account_id,
            channel=_channel(command),
        )
        return 200, _view(row, _audience(command))

    return _run(request, command, "postOffersOfferIdReconfirm",
                f"POST /offers/{offer_id}/reconfirm",
                body.model_dump(mode="json", exclude_unset=True), handler, 200,
                extra_errors=offer_service.OfferError)


@router.post("/offers/{offer_id}/sources", operation_id="postOffersOfferIdSources",
             status_code=204)
def link_offer_source(request: Request, offer_id: uuid.UUID,
                      body: OfferSourceLink, command: Command):
    """Staff only by `x-roles`; checked again here as the second lock."""
    decision = command.authorize("postOffersOfferIdSources")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    staff = command.authorize_staff_only(
        "postOffersOfferIdSources", "linking a source is a staff action")
    if not staff.allowed:
        return for_denial(staff.reason, trace_id_of(request),
                          customer_scoped=False, detail=staff.detail)

    def handler(session):
        offer_service.link_source(session, offer_id=offer_id,
                                  source_id=body.source_id,
                                  is_primary=body.is_primary)
        return 204, None

    response = _run(request, command, "postOffersOfferIdSources",
                    f"POST /offers/{offer_id}/sources",
                    body.model_dump(mode="json", exclude_unset=True), handler, 204,
                    extra_errors=offer_service.OfferError)
    if response.status_code == 204:
        from fastapi.responses import Response

        # A 204 carries no body; `JSONResponse(None)` would send "null".
        return Response(status_code=204)
    return response
