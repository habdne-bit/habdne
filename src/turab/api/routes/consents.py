"""Consent binding and revocation — Slice 1.

Ref: ADR-04; API_CONTRACTS v0.2 §4.2; RFC-001 R7.5.

Note the role asymmetry, which is deliberate: binding is staff-only, while a
customer may revoke their own grant. Revocation is meant to be easier than
granting, so the service must not "helpfully" let a customer create bindings.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict

from ...auth.loaders import ResourceKind
from ...services import consent as consent_service
from ..deps import Access, Command
from ..problems import ProblemCode, coded, for_denial, trace_id_of
from .parties import _run

router = APIRouter(tags=["Consent"])


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ConsentBindingInput(_Body):
    consent_id: uuid.UUID
    purpose: str
    resource_type: str
    resource_id: uuid.UUID
    notes: str | None = None


class ConsentRevokeInput(_Body):
    reason: str | None = None
    evidence_observation_id: uuid.UUID | None = None


@router.post("/consents/bindings", operation_id="postConsentsBindings")
def bind_consent(request: Request, body: ConsentBindingInput, command: Command):
    decision = command.authorize("postConsentsBindings")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    # x-roles already excludes CUSTOMER (R7.5: revocation is easier than
    # granting). Stated again as an object check so the guarantee does not
    # depend on the contract staying that way.
    scope = command.authorize_staff_only(
        "postConsentsBindings", "binding a consent is a staff operation"
    )
    if not scope.allowed:
        return for_denial(scope.reason, trace_id_of(request),
                          customer_scoped=False, detail=scope.detail)

    def handler(session):
        row = consent_service.bind_consent(
            session, consent_id=body.consent_id, purpose=body.purpose,
            resource_type=body.resource_type, resource_id=body.resource_id,
            notes=body.notes, bound_by_account_id=command.subject.account_id,
        )
        return 200, {
            "consent_binding_id": str(row["consent_binding_id"]),
            "consent_id": str(row["consent_id"]),
            "purpose": row["purpose"],
            "resource_type": body.resource_type,
            "resource_id": str(body.resource_id),
            "bound_at": row["bound_at"].isoformat(),
            "revoked_at": None,
        }

    return _run(request, command, "postConsentsBindings", "POST /consents/bindings",
                body.model_dump(mode="json"), handler, 200)


@router.post("/consents/{consent_id}/revoke",
             operation_id="postConsentsConsentIdRevoke")
def revoke_consent(request: Request, consent_id: uuid.UUID,
                   body: ConsentRevokeInput, command: Command, access: Access):
    """A CUSTOMER may revoke only their own grant; staff act operationally."""
    decision = command.authorize("postConsentsConsentIdRevoke")
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)

    from ...auth.roles import Role

    if command.subject.roles == frozenset({Role.CUSTOMER}):
        owned = access.read_resource(
            ResourceKind.CONSENT_GRANT, consent_id, "postConsentsConsentIdRevoke"
        )
        if not owned.authorized:
            # Their own grant or nothing: concealed, since a customer probing
            # consent ids learns nothing from a 403 they could not guess.
            return coded(ProblemCode.NOT_FOUND, trace_id_of(request))

    def handler(session):
        row = consent_service.revoke_consent(
            session, consent_id=consent_id, reason=body.reason,
            evidence_observation_id=body.evidence_observation_id,
        )
        return 200, {
            "consent_id": str(row["consent_id"]),
            "status": row["status"],
            "revoked_at": row["revoked_at"].isoformat() if row["revoked_at"] else None,
        }

    return _run(request, command, "postConsentsConsentIdRevoke",
                f"POST /consents/{consent_id}/revoke",
                body.model_dump(mode="json"), handler, 200)
