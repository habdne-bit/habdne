"""Assisted-record claiming — Slice 1 surface over the Slice 0 command.

Ref: API_CONTRACTS v0.2 §4.3; RFC-001 §4.1, INV-1.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from ...auth.loaders import ResourceKind
from ...services import claims as claim_service
from ..deps import Command
from ..problems import ProblemCode, coded, for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["External Leads"])


class ClaimRecordInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resource_type: str
    resource_id: uuid.UUID
    verification_contact_point_id: uuid.UUID


@router.post("/records/claim", operation_id="postRecordsClaim")
def claim_record(request: Request, body: ClaimRecordInput, command: Command):
    decision = command.authorize("postRecordsClaim")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    # No party-scope guard here on purpose: claiming is how a customer ACQUIRES
    # authority over a record they do not yet hold, so an ownership check would
    # make the command unusable. Its object rule is INV-1 inside
    # services/claims.py: a resource already claimed by another account is
    # rejected, and an ambiguous one grants authority to nobody.
    if body.resource_type not in ("REQUEST", "PROPERTY"):
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request),
                     "resource_type must be REQUEST or PROPERTY.")

    kind = (ResourceKind.REQUEST if body.resource_type == "REQUEST"
            else ResourceKind.PROPERTY)

    def handler(session):
        result = claim_service.claim_record(
            session, kind=kind, resource_id=body.resource_id,
            account_id=command.subject.account_id,
            verification_contact_point_id=body.verification_contact_point_id,
        )
        return 200, {
            "outcome": result.outcome.value,
            "claim_event_id": str(result.claim_event_id),
            "resource_type": body.resource_type,
            "resource_id": str(body.resource_id),
        }

    try:
        return _run(request, command, "postRecordsClaim", "POST /records/claim",
                    body.model_dump(mode="json"), handler, 200)
    except claim_service.ClaimRejected as exc:
        code = (ProblemCode[exc.code] if exc.code in ProblemCode.__members__
                else ProblemCode.VALIDATION_FAILED)
        return coded(code, trace_id_of(request), str(exc))
