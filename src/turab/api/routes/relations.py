"""PARTY–PROPERTY RELATIONS endpoints — G3-6, Contract Delta revision 3a.

Ref: `docs/contract/addenda/ADD-G3-6_party_property_relations.yaml` (the
approved ADDITION these three operations are declared in — not the frozen
contract, not the correction overlay); the Delta document it is bound to by
sha256.

Like every route module: no session, no repository, no SQLAlchemy.

All three are staff-only (Delta §4). A relation GRANTS NOTHING (§8): no loader
reads `party_property_relations`, and nothing here touches an authority input.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...services import relations as relation_service
from ...services import timeline as timeline_service
from ..deps import Access, Command
from ..problems import ProblemCode, coded, for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["Properties"])

RELATION_CODE_PATTERN = "^(" + "|".join(relation_service.RELATION_CODES) + ")$"

_OFFSET_REQUIRED = (
    "must carry a timezone offset (for example 2026-01-01T12:00:00Z); a local "
    "time with no offset does not identify a moment"
)


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PartyPropertyRelationInput(_Body):
    """`PartyPropertyRelationInput`, field for field.

    `valid_from` is omissible and NEVER null (Delta §5.1). The default is
    `None` but the declared type is `datetime`, and Pydantic does not validate
    defaults: an omitted field arrives as `None` (-> server clock), while an
    explicit `null` is validated against `datetime` and refused as a field
    error. `verification_level` and `valid_to` are absent on purpose (§3.1, §5).
    """

    party_id: uuid.UUID
    relation_code: str = Field(pattern=RELATION_CODE_PATTERN)
    valid_from: datetime = None  # type: ignore[assignment]
    note: str | None = None

    @field_validator("valid_from")
    @classmethod
    def _an_instant(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError(_OFFSET_REQUIRED)
        return value


class PartyPropertyRelationEnd(_Body):
    valid_to: datetime = None  # type: ignore[assignment]
    reason_code: str = None  # type: ignore[assignment]

    @field_validator("valid_to")
    @classmethod
    def _an_instant(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError(_OFFSET_REQUIRED)
        return value


@router.post("/properties/{property_id}/relations",
             operation_id="postPropertiesPropertyIdRelations", status_code=201)
def create_relation(request: Request, property_id: uuid.UUID,
                    body: PartyPropertyRelationInput, command: Command):
    decision = command.authorize("postPropertiesPropertyIdRelations")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    staff = command.authorize_staff_only(
        "postPropertiesPropertyIdRelations", "recording a relation is a staff action")
    if not staff.allowed:
        return for_denial(staff.reason, trace_id_of(request),
                          customer_scoped=False, detail=staff.detail)

    def handler(session):
        row = relation_service.create_relation(
            session, property_id=property_id, party_id=body.party_id,
            relation_code=body.relation_code, valid_from=body.valid_from,
            note=body.note, recorded_by_account_id=command.subject.account_id,
        )
        return 201, relation_service.view(row)

    return _run(request, command, "postPropertiesPropertyIdRelations",
                f"POST /properties/{property_id}/relations",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=relation_service.RelationError)


@router.get("/properties/{property_id}/relations",
            operation_id="getPropertiesPropertyIdRelations")
def list_relations(
    request: Request,
    property_id: uuid.UUID,
    access: Access,
    include_ended: Annotated[bool, Query()] = False,
    page: Annotated[int, Query()] = 1,
    page_size: Annotated[int, Query()] = timeline_service.DEFAULT_PAGE_SIZE,
):
    decision = access.authorize_operation("getPropertiesPropertyIdRelations")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    try:
        page, page_size = timeline_service.validate_pagination(page, page_size)
    except timeline_service.InvalidPagination as exc:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request), str(exc))
    try:
        items, total = access.list_property_relations(
            property_id, include_ended=include_ended, page=page,
            page_size=page_size, operation_id="getPropertiesPropertyIdRelations",
        )
    except relation_service.PropertyNotFound:
        return coded(ProblemCode.NOT_FOUND, trace_id_of(request))
    return {"items": [relation_service.view(r) for r in items],
            "page": page, "page_size": page_size, "total": total}


@router.post("/properties/{property_id}/relations/{relation_id}/end",
             operation_id="postPropertyRelationEnd")
def end_relation(request: Request, property_id: uuid.UUID, relation_id: uuid.UUID,
                 body: PartyPropertyRelationEnd, command: Command):
    decision = command.authorize("postPropertyRelationEnd")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    staff = command.authorize_staff_only(
        "postPropertyRelationEnd", "ending a relation is a staff action")
    if not staff.allowed:
        return for_denial(staff.reason, trace_id_of(request),
                          customer_scoped=False, detail=staff.detail)

    def handler(session):
        row = relation_service.end_relation(
            session, property_id=property_id, relation_id=relation_id,
            valid_to=body.valid_to, reason_code=body.reason_code,
            recorded_by_account_id=command.subject.account_id,
        )
        return 200, relation_service.view(row)

    return _run(request, command, "postPropertyRelationEnd",
                f"POST /properties/{property_id}/relations/{relation_id}/end",
                body.model_dump(mode="json", exclude_unset=True), handler, 200,
                extra_errors=relation_service.RelationError)
