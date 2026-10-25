"""Communication record: the staff thread and the staff message (Slice 7, step 2).

Ref: the contract's `postCommunicationThreads` (narrowed by CORRECTION-006)
and `postCommunicationThreadsThreadIdMessages`, both ADMIN and OPERATOR with
an Idempotency-Key; `docs/gate/SLICE_7_PLAN.md` revision 8 (G7-3, G7-4, G7-6,
G7-7, G7-9, G7-16); `services/communication.py`.

Like every route module: no session, no repository, no SQLAlchemy. Each
command calls `command.authorize` and `command.authorize_staff_only` itself,
where the architecture guard can see it; the message also checks that its
thread exists (RFC-001 R5.3b: 403 OBJECT_NOT_AUTHORIZED, recorded).
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, field_validator

from ...services import communication as communication_service
from ..deps import Command
from ..json_types import FiniteJsonObject
from ..problems import for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["Communication"])

THREAD = "postCommunicationThreads"
MESSAGE = "postCommunicationThreadsThreadIdMessages"


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CommunicationThreadCreate(_Body):
    """The effective `CommunicationThreadCreate` (CORRECTION-006), field for
    field, closed as the frozen component is:
    - `party_id`: required and not null (the correction);
    - `request_id`, `property_id`, `opportunity_id`: a uuid or null, as frozen;
    - `external_thread_ref`: a string; omissible, and not nullable, as frozen.
    `tests/test_correction_006.py` holds this model to the effective schema."""

    channel: Literal["WHATSAPP", "PHONE", "SMS", "EMAIL", "WEB", "IN_PERSON", "OTHER"]
    party_id: uuid.UUID
    request_id: uuid.UUID | None = None
    property_id: uuid.UUID | None = None
    opportunity_id: uuid.UUID | None = None
    external_thread_ref: str = None  # type: ignore[assignment]


class MessageCreate(_Body):
    """The frozen `MessageCreate`, field for field. Every optional field is
    omissible and none is nullable in the contract. The rules the contract
    does not state are the service's (G7-16)."""

    direction: Literal["INBOUND", "OUTBOUND", "INTERNAL"]
    occurred_at: datetime
    external_message_ref: str = None  # type: ignore[assignment]
    message_type: str = "TEXT"
    body_text: str = None  # type: ignore[assignment]
    media_ref: str = None  # type: ignore[assignment]
    delivery_status: Literal["QUEUED", "SENT", "DELIVERED", "READ", "FAILED",
                             "UNKNOWN"] = None  # type: ignore[assignment]
    metadata: FiniteJsonObject = None  # type: ignore[assignment]

    @field_validator("occurred_at")
    @classmethod
    def _an_instant(cls, value: datetime):
        """`format: date-time` is RFC 3339, which requires an offset."""
        if value.tzinfo is None:
            raise ValueError(
                "must carry a timezone offset (for example 2026-01-01T12:00:00Z)")
        return value


def _refusals(request: Request, decisions):
    for decision in decisions:
        if not decision.allowed:
            return for_denial(decision.reason, trace_id_of(request),
                              customer_scoped=False, detail=decision.detail)
    return None


@router.post("/communication/threads", operation_id=THREAD)
def create_thread(request: Request, body: CommunicationThreadCreate, command: Command):
    """G7-6, G7-3: a thread whose links agree, SALE checked, written once.
    Every refusal writes nothing and consumes no key."""
    refused = _refusals(request, (
        command.authorize(THREAD),
        command.authorize_staff_only(THREAD, "creating a thread is a staff action")))
    if refused is not None:
        return refused

    def prepare(session):
        return communication_service.prepare_thread(
            session, channel=body.channel, party_id=body.party_id,
            request_id=body.request_id, property_id=body.property_id,
            opportunity_id=body.opportunity_id,
            external_thread_ref=body.external_thread_ref)

    def handler(session, prepared):
        return 201, communication_service.record_thread(
            session, prepared, created_by_account_id=command.subject.account_id)

    return _run(request, command, THREAD, "POST /communication/threads",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=communication_service.CommunicationRefused, prepare=prepare)


@router.post("/communication/threads/{thread_id}/messages", operation_id=MESSAGE)
def create_message(request: Request, thread_id: uuid.UUID, body: MessageCreate,
                   command: Command):
    """G7-4, G7-9, G7-16: an OUTBOUND or INTERNAL message, the thread locked
    first. Every refusal writes nothing and consumes no key."""
    refused = _refusals(request, (
        command.authorize(MESSAGE),
        command.authorize_staff_only(MESSAGE, "recording a message is a staff action"),
        command.authorize_thread_exists(thread_id, MESSAGE)))
    if refused is not None:
        return refused

    def prepare(session):
        return communication_service.prepare_message(
            session, thread_id=thread_id, direction=body.direction,
            delivery_status=body.delivery_status, metadata=body.metadata,
            message_type=body.message_type, external_message_ref=body.external_message_ref,
            body_text=body.body_text, media_ref=body.media_ref,
            occurred_at=body.occurred_at)

    def handler(session, prepared):
        return 201, communication_service.record_message(
            session, prepared, sent_by_account_id=command.subject.account_id)

    return _run(request, command, MESSAGE, f"POST /communication/threads/{thread_id}/messages",
                body.model_dump(mode="json", exclude_unset=True), handler, 201,
                extra_errors=communication_service.CommunicationRefused, prepare=prepare)
