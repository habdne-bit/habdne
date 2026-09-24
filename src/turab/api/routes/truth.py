"""Truth-layer endpoints — Slice 3, step 5.

Ref: the contract's `postObservations`, `postClaims`,
`postClaimsClaimIdVerificationEvents`, `postResolutions`;
`docs/gate/SLICE_3_PLAN.md` §3.1, §3.2, §3.7, §3.8, §3.9.

Like every route module: no session, no repository, no SQLAlchemy. All four
are staff-only by `x-roles`, and each command checks it again as the second
lock. `postObservations` and `postClaims` are separation-sensitive (an
account holding both OPERATOR and REVIEWER is refused; INV-2).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...services import truth
from ..deps import Command
from ..json_types import JsonNumber
from ..problems import for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["Truth"])

_OFFSET = ("must carry a timezone offset (for example 2026-01-01T12:00:00Z); "
           "a local time with no offset does not identify a moment")


def _instant(value):
    if value is not None and value.tzinfo is None:
        raise ValueError(_OFFSET)
    return value


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SubjectRef(_Body):
    type: str = Field(pattern="^(PARTY|REQUEST|PROPERTY|OFFER)$")
    id: uuid.UUID


class ObservationInput(_Body):
    kind: str = Field(pattern="^(TEXT|CALL_NOTE|MESSAGE|DOCUMENT|IMAGE|"
                              "FORM_SUBMISSION|SYSTEM_IMPORT|OTHER)$")
    source_id: uuid.UUID | None = None
    party_id: uuid.UUID | None = None
    observed_at: datetime | None = None
    #: Omissible, never null.
    raw_text: str = None  # type: ignore[assignment]
    payload: dict[str, Any] = None  # type: ignore[assignment]

    _observed = field_validator("observed_at")(classmethod(lambda cls, v: _instant(v)))


class ClaimInput(_Body):
    """`ClaimInput`, field for field — and NO level field. A body carrying
    one is refused by `extra="forbid"`: the contract boundary is what makes a
    claim impossible to create already verified (§3.1)."""

    subject: SubjectRef
    attribute_code: str
    claimed_value: Any
    asserted_by_party_id: uuid.UUID | None = None
    source_id: uuid.UUID | None = None
    observation_id: uuid.UUID | None = None
    extracted_by: str = None  # type: ignore[assignment]
    extraction_model_version: str = None  # type: ignore[assignment]
    extraction_confidence: JsonNumber = Field(default=None, ge=0, le=1)  # type: ignore[assignment]
    observed_at: datetime | None = None
    valid_from: datetime | None = None
    valid_to: datetime | None = None

    _instants = field_validator("observed_at", "valid_from", "valid_to")(
        classmethod(lambda cls, v: _instant(v)))


class VerificationEventInput(_Body):
    level: str = Field(pattern="^(DECLARED|DOCUMENT_SEEN|DETAILS_MATCHED|"
                               "PROFESSIONAL_CHECK)$")
    outcome: str = Field(pattern="^(CONFIRMED|NOT_CONFIRMED|CONFLICT_FOUND|"
                                 "INCONCLUSIVE)$")
    procedure_code: str = None  # type: ignore[assignment]
    notes: str = None  # type: ignore[assignment]


class ResolutionInput(_Body):
    subject: SubjectRef
    attribute_code: str
    resolved_value: Any
    source_claim_id: uuid.UUID | None = None
    resolution_reason_code: str = None  # type: ignore[assignment]
    valid_from: datetime | None = None

    _start = field_validator("valid_from")(classmethod(lambda cls, v: _instant(v)))


def _refused(request, decision):
    """The denial response for a refused decision, or None."""
    if decision.allowed:
        return None
    return for_denial(decision.reason, trace_id_of(request),
                      customer_scoped=False, detail=decision.detail)


# Each route calls `command.authorize` and `command.authorize_staff_only`
# ITSELF: the architecture guard (tests/test_architecture.py) requires the
# object check to be visible in the route, and a helper that hid it was
# rightly refused.


@router.post("/observations", operation_id="postObservations", status_code=201)
def post_observation(request: Request, body: ObservationInput, command: Command):
    refused = (_refused(request, command.authorize("postObservations"))
               or _refused(request, command.authorize_staff_only(
                   "postObservations", "recording an observation is a staff action")))
    if refused is not None:
        return refused

    def handler(session):
        row = truth.record_observation(
            session, kind=body.kind, source_id=body.source_id,
            party_id=body.party_id, observed_at=body.observed_at,
            raw_text=body.raw_text, payload=body.payload,
            recorded_by_account_id=command.subject.account_id)
        return 201, {"observation_id": str(row["observation_id"]),
                     "recorded_at": row["recorded_at"].isoformat()}

    return _run(request, command, "postObservations", "POST /observations",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=truth.TruthError)


@router.post("/claims", operation_id="postClaims", status_code=201)
def post_claim(request: Request, body: ClaimInput, command: Command):
    refused = (_refused(request, command.authorize("postClaims"))
               or _refused(request, command.authorize_staff_only(
                   "postClaims", "recording a claim is a staff action")))
    if refused is not None:
        return refused

    def handler(session):
        row = truth.record_claim(
            session, subject_type=body.subject.type, subject_id=body.subject.id,
            attribute_code=body.attribute_code, claimed_value=body.claimed_value,
            asserted_by_party_id=body.asserted_by_party_id,
            source_id=body.source_id, observation_id=body.observation_id,
            extracted_by=body.extracted_by,
            extraction_model_version=body.extraction_model_version,
            extraction_confidence=body.extraction_confidence,
            observed_at=body.observed_at, valid_from=body.valid_from,
            valid_to=body.valid_to,
            recorded_by_account_id=command.subject.account_id)
        return 201, {"claim_id": str(row["claim_id"]),
                     "verification_level": row["verification_level"],
                     "status": row["status"]}

    return _run(request, command, "postClaims", "POST /claims",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=truth.TruthError)


@router.post("/claims/{claim_id}/verification-events",
             operation_id="postClaimsClaimIdVerificationEvents", status_code=201)
def post_verification(request: Request, claim_id: uuid.UUID,
                      body: VerificationEventInput, command: Command):
    refused = (_refused(request, command.authorize("postClaimsClaimIdVerificationEvents"))
               or _refused(request, command.authorize_staff_only(
                   "postClaimsClaimIdVerificationEvents", "verifying a claim is a staff action")))
    if refused is not None:
        return refused

    def handler(session):
        row = truth.record_verification(
            session, claim_id=claim_id, level=body.level, outcome=body.outcome,
            procedure_code=body.procedure_code, notes=body.notes,
            verified_by_account_id=command.subject.account_id)
        return 201, {"verification_event_id": str(row["verification_event_id"]),
                     "level": row["level"], "outcome": row["outcome"]}

    return _run(request, command, "postClaimsClaimIdVerificationEvents",
                f"POST /claims/{claim_id}/verification-events",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=truth.TruthError)


@router.post("/resolutions", operation_id="postResolutions", status_code=201)
def post_resolution(request: Request, body: ResolutionInput, command: Command):
    refused = (_refused(request, command.authorize("postResolutions"))
               or _refused(request, command.authorize_staff_only(
                   "postResolutions", "issuing a resolution is a staff action")))
    if refused is not None:
        return refused

    def handler(session):
        row = truth.resolve(
            session, subject_type=body.subject.type, subject_id=body.subject.id,
            attribute_code=body.attribute_code, resolved_value=body.resolved_value,
            source_claim_id=body.source_claim_id,
            resolution_reason_code=body.resolution_reason_code,
            valid_from=body.valid_from,
            resolved_by_account_id=command.subject.account_id)
        return 201, {"resolved_value_id": str(row["resolved_value_id"]),
                     "resolution_status": row["resolution_status"]}

    return _run(request, command, "postResolutions", "POST /resolutions",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=truth.TruthError)
