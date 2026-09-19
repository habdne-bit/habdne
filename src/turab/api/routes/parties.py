"""PARTY, contact point and consent-grant endpoints — Slice 1.

Ref: API_CONTRACTS v0.2 §4.1, §4.2; RFC-001 §4, §12.

Like every route module here: no session, no repository, no SQLAlchemy. The
handlers passed to CommandService close over request data only; the session
they receive is supplied by the command boundary inside its transaction.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Header, Request
from pydantic import BaseModel, ConfigDict, Field

from ...auth.loaders import ResourceKind
from ...dto import Audience, CustomerPartyView, assert_no_forbidden_fields
from ...services import consent as consent_service
from ...services import parties as party_service
from ...services.concurrency import (
    HEADER,
    IfMatchRequired,
    MalformedIfMatch,
    StaleVersion,
    parse_if_match,
)
from ..deps import Access, Command
from ..problems import ProblemCode, coded, for_denial, trace_id_of

router = APIRouter(tags=["Parties"])

PHONE = r"^\+[1-9][0-9]{7,14}$"


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PartyCreate(_Body):
    kind: str = Field(pattern="^(PERSON|BUSINESS)$")
    display_name: str | None = None
    legal_name: str | None = None
    notes: str | None = None


class PartyPatch(_Body):
    display_name: str | None = None
    legal_name: str | None = None
    notes: str | None = None


class PhoneInput(_Body):
    phone_e164: str = Field(pattern=PHONE)
    is_primary: bool = False
    relationship_note: str | None = None


class ConsentGrantInput(_Body):
    scope: str
    channel: str
    consent_version: str
    granted_at: datetime
    evidence_observation_id: uuid.UUID | None = None
    notes: str | None = None


def _internal_party(row) -> dict[str, Any]:
    """The contract's `Party` schema: a staff view, so version is included."""
    return {
        "party_id": str(row["party_id"]),
        "kind": row["kind"],
        "status": row["status"],
        "display_name": row["display_name"],
        "legal_name": row["legal_name"],
        "version": row["version"],
        "created_at": row["created_at"].isoformat(),
        "updated_at": row["updated_at"].isoformat(),
    }


@router.post("/parties", operation_id="postParties", status_code=201)
def create_party(request: Request, body: PartyCreate, command: Command):
    decision = command.authorize("postParties")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)

    def handler(session):
        row = party_service.create_party(
            session, kind=body.kind, display_name=body.display_name,
            legal_name=body.legal_name, notes=body.notes,
        )
        return 201, _internal_party(row)

    return _run(request, command, "postParties", "POST /parties",
                body.model_dump(mode="json"), handler, 201)


@router.get("/parties/{party_id}", operation_id="getPartiesPartyId")
def read_party(request: Request, party_id: uuid.UUID, access: Access):
    """Internal read. x-roles excludes CUSTOMER (K01); customers use /me/party."""
    decision = access.authorize_operation("getPartiesPartyId")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    result = access.read_staff_resource(
        ResourceKind.PARTY, party_id, "getPartiesPartyId"
    )
    if not result.authorized:
        return for_denial(result.reason, trace_id_of(request), customer_scoped=False)
    return _internal_party(result.row)


@router.patch("/parties/{party_id}", operation_id="patchPartiesPartyId")
def update_party(
    request: Request,
    party_id: uuid.UUID,
    body: PartyPatch,
    command: Command,
    if_match_version: Annotated[str | None, Header(alias=HEADER)] = None,
):
    """Typed projection update under optimistic concurrency (§2.4).

    The version is checked inside the command's transaction and before the
    update, so a stale version applies nothing.
    """
    decision = command.authorize("patchPartiesPartyId")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    try:
        expected = parse_if_match(if_match_version)
    except IfMatchRequired:
        return coded(ProblemCode.IF_MATCH_REQUIRED, trace_id_of(request),
                     f"{HEADER} is required on this command.")
    except MalformedIfMatch:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request),
                     f"{HEADER} must be a positive version integer.")

    changes = body.model_dump(exclude_unset=True)
    if not changes:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request),
                     "at least one field must be supplied.")

    def handler(session):
        row = party_service.update_party(session, party_id, changes)
        return 200, _internal_party(row)

    return _run(
        request, command, "patchPartiesPartyId", f"PATCH /parties/{party_id}",
        changes, handler, 200, version_guard=("parties", party_id, expected),
    )


@router.post("/parties/{party_id}/contact-points/phone",
             operation_id="attachPartyPhoneContactPoint", status_code=201)
def attach_phone(request: Request, party_id: uuid.UUID, body: PhoneInput,
                 command: Command):
    """A01/ADR-07: reuses an existing contact point and never merges parties."""
    decision = command.authorize("attachPartyPhoneContactPoint")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)

    def handler(session):
        row = party_service.attach_phone(
            session, party_id=party_id, phone_e164=body.phone_e164,
            is_primary=body.is_primary, relationship_note=body.relationship_note,
        )
        return 201, {
            "contact_point_id": str(row["contact_point_id"]),
            "kind": row["kind"],
            "normalized_value": row["normalized_value"],
            "display_value": row["display_value"],
            "control_status": row["control_status"],
        }

    return _run(request, command, "attachPartyPhoneContactPoint",
                f"POST /parties/{party_id}/contact-points/phone",
                body.model_dump(mode="json"), handler, 201)


@router.post("/parties/{party_id}/consents",
             operation_id="postPartiesPartyIdConsents", status_code=201)
def grant_consent(request: Request, party_id: uuid.UUID, body: ConsentGrantInput,
                  command: Command):
    """A grant is not yet proof for a resource; binding is a separate command."""
    decision = command.authorize("postPartiesPartyIdConsents")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)

    def handler(session):
        row = consent_service.grant_consent(
            session, party_id=party_id, scope=body.scope, channel=body.channel,
            consent_version=body.consent_version, granted_at=body.granted_at,
            evidence_observation_id=body.evidence_observation_id,
            notes=body.notes, created_by_account_id=command.subject.account_id,
        )
        return 201, {"consent_id": str(row["consent_id"]), "status": row["status"]}

    return _run(request, command, "postPartiesPartyIdConsents",
                f"POST /parties/{party_id}/consents",
                body.model_dump(mode="json"), handler, 201)


def _run(request, command, operation_id, route_key, payload, handler,
         success_status, version_guard=None):
    """Shared command plumbing: idempotency, concurrency and stable errors."""
    from ...services.idempotency import IdempotencyKeyConflict, IdempotencyKeyRequired

    trace = trace_id_of(request)
    try:
        result = command.run(
            operation_id=operation_id, route_key=route_key, payload=payload,
            handler=handler, success_status=success_status,
            version_guard=version_guard,
        )
    except IdempotencyKeyRequired:
        return coded(ProblemCode.IDEMPOTENCY_KEY_REQUIRED, trace,
                     "Idempotency-Key is required on this command.")
    except IdempotencyKeyConflict:
        return coded(ProblemCode.IDEMPOTENCY_KEY_CONFLICT, trace,
                     "This idempotency key was already used with a different body.")
    except StaleVersion:
        return coded(ProblemCode.STALE_VERSION, trace,
                     "The resource has changed; re-read it and retry.")
    except party_service.PartyNotFound:
        return coded(ProblemCode.NOT_FOUND, trace)
    except party_service.InvalidPhone as exc:
        return coded(ProblemCode.VALIDATION_FAILED, trace, str(exc))
    except consent_service.ConsentError as exc:
        code = (ProblemCode[exc.code] if exc.code in ProblemCode.__members__
                else ProblemCode.VALIDATION_FAILED)
        return coded(code, trace, str(exc))
    except ValueError as exc:
        return coded(ProblemCode.VALIDATION_FAILED, trace, str(exc))

    from fastapi.responses import JSONResponse

    return JSONResponse(status_code=result.status, content=result.body)
