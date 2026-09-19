"""OTP endpoints — Slice 1.

Ref: API_CONTRACTS v0.2 §4.1; ADR-07; red-team A02.

Both operations are in the closed unauthenticated list (RFC-001 R10.4). The
invariant they protect: proving control of a phone creates neither a PARTY nor
a USER_ACCOUNT.
"""
from __future__ import annotations

import uuid

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

from ...services import otp as otp_service
from ..deps import Otp
from ..problems import ProblemCode, coded, trace_id_of

router = APIRouter(prefix="/auth/otp", tags=["Auth"])


class _Body(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OtpStart(_Body):
    phone_e164: str = Field(pattern=r"^\+[1-9][0-9]{7,14}$")
    purpose: str = Field(pattern="^(LOGIN|VERIFY_PHONE_CONTROL)$")


class OtpVerify(_Body):
    challenge_id: uuid.UUID
    code: str = Field(min_length=4, max_length=8)


@router.post("/start", operation_id="postAuthOtpStart", status_code=201)
def otp_start(request: Request, body: OtpStart, otp: Otp):
    """Issue a challenge. Creates nothing in the domain."""
    try:
        challenge = otp.start(phone_e164=body.phone_e164, purpose=body.purpose)
    except otp_service.OtpError as exc:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request), str(exc))
    except ValueError as exc:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request), str(exc))

    # The code itself is never returned and never logged (§8).
    return {
        "challenge_id": str(challenge.challenge_id),
        "expires_at": challenge.expires_at.isoformat(),
    }


@router.post("/verify", operation_id="postAuthOtpVerify")
def otp_verify(request: Request, body: OtpVerify, otp: Otp):
    """Verify, and apply only what the purpose permits.

    This is the one write path not routed through CommandService: it is
    unauthenticated, so there is no actor to carry, and the contract gives it
    no Idempotency-Key. OtpService still opens an audited transaction, with a
    null actor, which is the honest record of an anonymous verification.
    """
    trace = trace_id_of(request)
    try:
        result = otp.verify(challenge_id=body.challenge_id, code=body.code)
    except otp_service.OtpError as exc:
        # One code for unknown, expired and wrong: distinguishing them would
        # tell a caller which challenge ids exist.
        return coded(ProblemCode.VALIDATION_FAILED, trace, str(exc))

    return {
        "verification_result": result["verification_result"],
        "contact_point_id": str(result["contact_point_id"]),
        "account_id": str(result["account_id"]) if result["account_id"] else None,
        "access_token": result["access_token"],
    }
