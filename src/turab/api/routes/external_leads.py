"""SOURCE endpoints — external leads (Slice 3, step 3; plan §1.5).

Ref: `ExternalLeadCreate`, `postExternalLeads`, `postExternalLeadsLeadIdConvert`,
`getBackofficeQueuesExternalLeads`; API_CONTRACTS_v0.2 §4.3;
`docs/gate/G3-10_external_lead_conversion.md`.

Like every route module: no session, no repository, no SQLAlchemy. All three
are staff-only by `x-roles`, and each command checks it again as the second
lock. The payloads carry `raw_text`, `external_url` and `metadata`, which are
on the R9.2 floor; nothing here renders to a customer.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ...services import external_leads as lead_service
from ..deps import Access, Command
from ..problems import for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["ExternalLeads"])

#: RFC 3986 §3.1: a URI begins with a scheme. `format: uri` is an absolute URI
#: (JSON Schema 2020-12 Validation §7.3.5), so a relative reference is refused.
#: The value is stored VERBATIM: a URL type that normalises it would record a
#: different string from the one the source actually showed.
_URI_SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:\S+$")


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SourceInput(_Body):
    """The inline `source` object of `ExternalLeadCreate`.

    Open in the contract (no `additionalProperties: false`); unknown keys are
    refused all the same, the choice already made for `RequestCriterion` and
    the offer-source link. Every optional field is omissible and none is
    nullable in the contract.
    """

    kind: str = Field(pattern="^(" + "|".join(lead_service.SOURCE_KINDS) + ")$")
    external_url: str = None  # type: ignore[assignment]
    external_ref: str = None  # type: ignore[assignment]
    title: str = None  # type: ignore[assignment]
    raw_text: str = None  # type: ignore[assignment]
    captured_at: datetime = None  # type: ignore[assignment]
    metadata: dict[str, Any] = None  # type: ignore[assignment]

    @field_validator("external_url")
    @classmethod
    def _absolute_uri(cls, value: str):
        if not _URI_SCHEME.match(value):
            raise ValueError("must be an absolute URI with a scheme (RFC 3986 §3)")
        return value

    @field_validator("captured_at")
    @classmethod
    def _an_instant(cls, value: datetime):
        if value.tzinfo is None:
            raise ValueError(
                "must carry a timezone offset (for example 2026-01-01T12:00:00Z)")
        return value


class ExternalLeadCreate(_Body):
    lead_kind: str = Field(pattern="^(PROPERTY|REQUEST)$")
    source: SourceInput
    raw_payload: dict[str, Any] = None  # type: ignore[assignment]


class ExternalLeadConvert(_Body):
    """The inline convert body, field for field — validated, then refused."""

    party_id: uuid.UUID
    consent_id: uuid.UUID
    target: str = Field(default=None, pattern="^(REQUEST|PROPERTY)$")  # type: ignore[assignment]
    payload: dict[str, Any] = None  # type: ignore[assignment]


@router.post("/external-leads", operation_id="postExternalLeads", status_code=201)
def capture_lead(request: Request, body: ExternalLeadCreate, command: Command):
    """A discovery record only — never an active REQUEST or PROPERTY (§4.3)."""
    decision = command.authorize("postExternalLeads")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    staff = command.authorize_staff_only("postExternalLeads",
                                         "capturing a lead is a staff action")
    if not staff.allowed:
        return for_denial(staff.reason, trace_id_of(request),
                          customer_scoped=False, detail=staff.detail)

    source = body.source.model_dump(exclude_unset=True)

    def handler(session):
        row = lead_service.capture(
            session, lead_kind=body.lead_kind, source=source,
            raw_payload=body.raw_payload,
            created_by_account_id=command.subject.account_id,
        )
        return 201, {"external_lead_id": str(row["external_lead_id"]),
                     "status": row["status"], "source_id": str(row["source_id"])}

    return _run(request, command, "postExternalLeads", "POST /external-leads",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=lead_service.LeadError)


@router.post("/external-leads/{lead_id}/convert",
             operation_id="postExternalLeadsLeadIdConvert", status_code=201)
def convert_lead(request: Request, lead_id: uuid.UUID, body: ExternalLeadConvert,
                 command: Command):
    """Refused with `409 EXTERNAL_LEAD_CONVERSION_UNDECIDED` (G3-10).

    Raised inside the command's transaction, so the refusal writes nothing and
    consumes no idempotency key; an unknown lead is still a 404.
    """
    decision = command.authorize("postExternalLeadsLeadIdConvert")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    staff = command.authorize_staff_only("postExternalLeadsLeadIdConvert",
                                         "converting a lead is a staff action")
    if not staff.allowed:
        return for_denial(staff.reason, trace_id_of(request),
                          customer_scoped=False, detail=staff.detail)

    def handler(session):
        lead_service.refuse_conversion(session, lead_id)
        return 201, None  # unreachable: refuse_conversion always raises

    return _run(request, command, "postExternalLeadsLeadIdConvert",
                f"POST /external-leads/{lead_id}/convert",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=lead_service.LeadError)


@router.get("/backoffice/queues/external-leads",
            operation_id="getBackofficeQueuesExternalLeads")
def lead_queue(request: Request, access: Access):
    decision = access.authorize_operation("getBackofficeQueuesExternalLeads")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    rows = access.external_lead_queue(operation_id="getBackofficeQueuesExternalLeads")
    return {"items": [lead_service.queue_item(r) for r in rows], "next_cursor": None}
