"""PROPERTY endpoints — Slice 3, step 1.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 3; the effective contract's
`PropertyCreate` and `PropertyPatch`; RFC-001 §4.4 (R4.1-R4.3), §4.2 (R4.5),
R4.9; `docs/gate/SLICE_3_PLAN.md` §1.1, §3.3, §5.

Like every route module: no session, no repository, no SQLAlchemy.

**What is not here, and why.** There is no way to change availability through
`PATCH`. That is not a gap: the contract's `PropertyPatch` declares five fields
and `additionalProperties: false`, and availability is not among them. It
changes through `POST /properties/{id}/reconfirm`, whose body REQUIRES an
explicit availability value — so a change of availability always carries the
statement of what was confirmed and when (plan §3.3, ratified as G3-3).

**A property has no `party_id`.** Authority over it is the creator account or a
recorded claim, and nothing else (R4.1). Nothing here asks whose property it
is, because there is no column to answer from and answering it from
`party_property_relations` would contradict a FINAL decision (R4.5).
"""
from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from ...auth.loaders import ResourceKind
from ...services import properties as property_service
from ...services.concurrency import HEADER, IfMatchRequired, parse_if_match
from ...services.provenance import UpdateChannel
from ..deps import Access, Command
from ..problems import ProblemCode, coded, for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["Properties"])

PROPERTY_TYPE_PATTERN = "^(" + "|".join(property_service.PROPERTY_TYPES) + ")$"
AVAILABILITY_PATTERN = (
    "^(AVAILABLE|POTENTIALLY_AVAILABLE|UNDER_DISCUSSION|"
    "TEMPORARILY_UNAVAILABLE|UNAVAILABLE|NEEDS_CONFIRMATION|UNKNOWN)$"
)
SUPPLY_MODE_PATTERN = "^(PUBLIC|PRIVATE|POTENTIAL)$"
MANAGEMENT_MODE_PATTERN = "^(SELF_MANAGED|ASSISTED|SHARED_MANAGEMENT)$"
CLAIM_STATUS_PATTERN = "^(CLAIMED|UNCLAIMED)$"


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PropertyCreate(_Body):
    """`PropertyCreate`, field for field.

    `current_availability` IS accepted here and refused by `PropertyPatch`,
    which is not an inconsistency: the contract declares it on the create body
    and omits it from the patch body. The initial value is stated once, and
    every later change goes through reconfirmation.
    """

    property_type: str = Field(pattern=PROPERTY_TYPE_PATTERN)
    supply_mode: str = Field(pattern=SUPPLY_MODE_PATTERN)
    management_mode: str = Field(pattern=MANAGEMENT_MODE_PATTERN)
    claim_status: str = Field(pattern=CLAIM_STATUS_PATTERN)
    canonical_location_id: uuid.UUID | None = None
    local_location_detail: str | None = None
    land_area_m2: float | None = Field(default=None, gt=0)
    built_area_m2: float | None = Field(default=None, gt=0)
    current_availability: str | None = Field(default=None,
                                             pattern=AVAILABILITY_PATTERN)


class PropertyPatch(_Body):
    """`PropertyPatch`, field for field: five fields, and no availability.

    `null` is a real value for every one of them except `property_type`, which
    is `NOT NULL` in the frozen schema — so it is typed as a plain string with
    a sentinel default, the R-S2-05 shape, and an explicit `null` is refused as
    a field error rather than reaching PostgreSQL.
    """

    property_type: str = Field(default="", pattern=PROPERTY_TYPE_PATTERN)
    canonical_location_id: uuid.UUID | None = None
    local_location_detail: str | None = None
    land_area_m2: float | None = Field(default=None, gt=0)
    built_area_m2: float | None = Field(default=None, gt=0)


def _channel(command) -> UpdateChannel:
    return (UpdateChannel.STAFF_RECORDED if command.is_staff
            else UpdateChannel.SELF_SERVICE)


def _view(row) -> dict:
    return {
        "property_id": str(row["property_id"]),
        "property_type": row["property_type"],
        "canonical_location_id": (str(row["canonical_location_id"])
                                  if row["canonical_location_id"] else None),
        "local_location_detail": row["local_location_detail"],
        "land_area_m2": float(row["land_area_m2"]) if row["land_area_m2"] is not None else None,
        "built_area_m2": float(row["built_area_m2"]) if row["built_area_m2"] is not None else None,
        "current_availability": row["current_availability"],
        "availability_last_confirmed_at": (
            row["availability_last_confirmed_at"].isoformat()
            if row["availability_last_confirmed_at"] else None),
        "supply_mode": row["supply_mode"],
        "management_mode": row["management_mode"],
        "claim_status": row["claim_status"],
        "version": row["version"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


@router.post("/properties", operation_id="postProperties", status_code=201)
def create_property(request: Request, body: PropertyCreate, command: Command):
    """Create the physical record.

    Note what this route does NOT do, and could not: bind the property to a
    party. `PropertyCreate` carries no `party_id` and `properties` has no such
    column, so the record's only link to anyone is `created_by_account_id` —
    which is exactly the authority R4.1 defines. Writing a
    `party_property_relations` row here would be inferring a relation from an
    act of creation, which G3-6 forbids until the relations contract exists.
    """
    decision = command.authorize("postProperties")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)

    # Same rule as a REQUEST: a customer creates their own record, so it is
    # theirs from the first moment. ASSISTED means staff are operating a record
    # on someone's behalf, and that record is UNCLAIMED until claimed — a
    # different flow, not a different flag.
    if not command.is_staff and body.management_mode != "SELF_MANAGED":
        return coded(
            ProblemCode.VALIDATION_FAILED, trace_id_of(request),
            "a customer creates a SELF_MANAGED property; assisted records are "
            "created by staff and claimed afterwards",
        )

    def handler(session):
        row = property_service.create_property(
            session,
            property_type=body.property_type,
            management_mode=body.management_mode,
            claim_status=body.claim_status,
            supply_mode=body.supply_mode,
            created_by_account_id=command.subject.account_id,
            recorded_by_account_id=command.subject.account_id,
            channel=_channel(command),
            canonical_location_id=body.canonical_location_id,
            local_location_detail=body.local_location_detail,
            land_area_m2=body.land_area_m2,
            built_area_m2=body.built_area_m2,
            current_availability=body.current_availability,
        )
        return 201, _view(row)

    return _run(request, command, "postProperties", "POST /properties",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=property_service.PropertyError)


@router.patch("/properties/{property_id}", operation_id="patchPropertiesPropertyId")
def patch_property(
    request: Request,
    property_id: uuid.UUID,
    body: PropertyPatch,
    command: Command,
    if_match_version: Annotated[str | None, Header(alias=HEADER)] = None,
):
    """Change the physical description of a property.

    Availability is unreachable from here by construction: `PropertyPatch` has
    `extra="forbid"` and no such field, so sending it is a field error before
    any of this runs, and `properties.PATCHABLE` refuses it again in the
    service for a caller that bypasses the model.
    """
    decision = command.authorize("patchPropertiesPropertyId")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    scope = command.authorize_property_scope(property_id)
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
    # `property_type` is NOT NULL and carries "" as its "not supplied" default.
    # The check is scoped to it alone: an empty `local_location_detail` is a
    # value the contract allows, and equating empty text with null was the
    # R-S2-05a defect. It must never fire — the pattern rejects "" first — and
    # is kept as a narrow assertion, not a filter.
    if changes.get("property_type") == "":
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request),
                     "property_type cannot be empty; omit it to leave it unchanged.")
    if not changes:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request),
                     "at least one field must be supplied.")

    def handler(session):
        row = property_service.patch_property(
            session, property_id=property_id, changes=changes,
            recorded_by_account_id=command.subject.account_id,
            channel=_channel(command),
        )
        return 200, _view(row)

    return _run(request, command, "patchPropertiesPropertyId",
                f"PATCH /properties/{property_id}",
                body.model_dump(mode="json", exclude_unset=True), handler, 200,
                version_guard=("properties", property_id, expected),
                extra_errors=property_service.PropertyError)


@router.get("/properties/{property_id}", operation_id="getPropertiesPropertyId")
def read_property(request: Request, property_id: uuid.UUID, access: Access):
    """Internal read. `x-roles` excludes CUSTOMER; customers use /me/properties."""
    decision = access.authorize_operation("getPropertiesPropertyId")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    result = access.read_staff_resource(
        ResourceKind.PROPERTY, property_id, "getPropertiesPropertyId"
    )
    if not result.authorized:
        return for_denial(result.reason, trace_id_of(request), customer_scoped=False)
    body = _view(result.row)
    # Additive, and the point of it: a reader must be able to tell a change the
    # party made themselves from one a staff member typed, and whether any call
    # or message was recorded behind it.
    body["provenance"] = [
        {
            "attribute_code": c["attribute_code"],
            "value": c["claimed_value"],
            "channel": c["channel"],
            "recorded_at": c["recorded_at"].isoformat(),
            "recorded_by_account_id": (str(c["recorded_by_account_id"])
                                       if c["recorded_by_account_id"] else None),
            "source_recorded": c["source_recorded"],
            "verification_level": c["verification_level"],
        }
        for c in access.property_provenance(property_id)
    ]
    return body
