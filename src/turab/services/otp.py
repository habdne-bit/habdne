"""Phone control verification and account activation — Slice 1.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 1; API_CONTRACTS v0.2 §4.1; ADR-07;
red-team A02, A03; Foundation §8 (the official provider integration boundary).

The invariant, from Master §4 (11) and ADR-07:

    a verified phone proves control of a CONTACT_POINT.
    It does not create a PARTY, and it does not create a USER_ACCOUNT.

## Where challenge state lives — decided

The frozen schema has no table for OTP challenges, and the approved resolution
is **delegation**: the SMS/WhatsApp provider issues the code, holds the
challenge, counts attempts and expires it. `challenge_id` in the contract *is*
the provider's verification id, and TURAB stores nothing about the challenge.

That leaves this module with only the domain half, which is the half that
belongs here: recording verified control of a contact point, and activating an
account that already exists. Attempt limits, code generation, expiry and
throttling are the provider's, and deliberately not reimplemented.

One consequence worth stating: `purpose` is TURAB's concept, not the
provider's. It is sent when the verification starts and read back when it is
checked, so a provider must be able to carry it — real verification APIs do,
as metadata or as separate templates. Where a provider cannot, `check()`
returns `purpose=None` and this module **fails closed to
VERIFY_PHONE_CONTROL**: no session is ever created from a verification whose
purpose could not be established.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Mapping, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from .parties import normalize_phone


class OtpPurpose(StrEnum):
    LOGIN = "LOGIN"
    VERIFY_PHONE_CONTROL = "VERIFY_PHONE_CONTROL"


class VerificationResult(StrEnum):
    PHONE_CONTROL_VERIFIED = "PHONE_CONTROL_VERIFIED"
    SESSION_CREATED = "SESSION_CREATED"


class OtpError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


class VerificationRejected(OtpError):
    """Unknown, expired, exhausted or wrong code.

    Deliberately one error for all of them: distinguishing "no such
    verification" from "wrong code" tells a caller which ids exist.
    """

    def __init__(self) -> None:
        super().__init__(
            "OTP_INVALID", "the verification is unknown, expired or the code is wrong"
        )


class ProviderUnavailable(OtpError):
    """The verification provider could not be reached.

    Distinct from a rejection on purpose: a caller who was refused should not
    retry, and a caller whose provider is down should.
    """

    def __init__(self, detail: str = "the verification provider is unavailable") -> None:
        super().__init__("PROVIDER_UNAVAILABLE", detail)


# ---------------------------------------------------------------------------
# The provider boundary
# ---------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class StartedVerification:
    """What the provider returns when a verification begins."""

    verification_id: uuid.UUID
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class CheckedVerification:
    """What the provider returns when a code is checked.

    `purpose` is None when the provider cannot carry TURAB's purpose; the
    caller then fails closed (see the module docstring).
    """

    approved: bool
    phone_e164: str | None = None
    purpose: OtpPurpose | None = None


class VerificationProvider(Protocol):
    """The official SMS/WhatsApp verification boundary.

    TURAB never sees the code. It asks for a verification, and later asks
    whether a code was accepted.
    """

    def start(self, *, phone_e164: str, purpose: OtpPurpose) -> StartedVerification: ...

    def check(self, *, verification_id: uuid.UUID, code: str) -> CheckedVerification: ...


class FakeVerificationProvider:
    """A stand-in for the provider, for development and tests.

    This holds challenge state in memory, and that is now legitimate: it is
    standing in for the external system that owns that state, not for a TURAB
    table. Nothing in the service depends on it.
    """

    TTL = timedelta(minutes=10)
    MAX_ATTEMPTS = 5

    def __init__(self) -> None:
        self._verifications: dict[uuid.UUID, dict] = {}
        self.unavailable = False

    def start(self, *, phone_e164: str, purpose: OtpPurpose) -> StartedVerification:
        if self.unavailable:
            raise ProviderUnavailable()
        verification_id = uuid.uuid4()
        self._verifications[verification_id] = {
            "phone_e164": phone_e164,
            "purpose": purpose,
            "code": "424242",  # fixed in the fake; a real provider generates it
            "expires_at": datetime.now(UTC) + self.TTL,
            "attempts": 0,
        }
        return StartedVerification(
            verification_id, self._verifications[verification_id]["expires_at"]
        )

    def check(self, *, verification_id: uuid.UUID, code: str) -> CheckedVerification:
        if self.unavailable:
            raise ProviderUnavailable()
        record = self._verifications.get(verification_id)
        if record is None or record["expires_at"] <= datetime.now(UTC):
            return CheckedVerification(approved=False)
        record["attempts"] += 1
        if record["attempts"] > self.MAX_ATTEMPTS:
            self._verifications.pop(verification_id, None)
            return CheckedVerification(approved=False)
        if code.strip() != record["code"]:
            return CheckedVerification(approved=False)
        self._verifications.pop(verification_id, None)
        return CheckedVerification(
            approved=True, phone_e164=record["phone_e164"], purpose=record["purpose"]
        )

    # test affordance, not part of the protocol
    def code_for(self, verification_id: uuid.UUID) -> str:
        return self._verifications[verification_id]["code"]


# ---------------------------------------------------------------------------
# Domain
# ---------------------------------------------------------------------------

def start_verification(
    provider: VerificationProvider, *, phone_e164: str, purpose: str
) -> StartedVerification:
    """Ask the provider to begin. Creates nothing in TURAB."""
    normalized = normalize_phone(phone_e164)
    try:
        parsed = OtpPurpose(purpose)
    except ValueError as exc:
        raise OtpError(
            "VALIDATION_FAILED", f"purpose must be one of {[p.value for p in OtpPurpose]}"
        ) from exc
    return provider.start(phone_e164=normalized, purpose=parsed)


def apply_verification(
    session: Session,
    provider: VerificationProvider,
    *,
    verification_id: uuid.UUID,
    code: str,
) -> Mapping[str, object]:
    """Check with the provider, then apply what the purpose permits.

    A02: `VERIFY_PHONE_CONTROL` marks the contact point verified and stops.
    `LOGIN` may open a session only where an account already exists; where none
    does, the result is still `PHONE_CONTROL_VERIFIED`, which is the contract's
    `account_id` being nullable "by design" (§4.1).
    """
    checked = provider.check(verification_id=verification_id, code=code)
    if not checked.approved or not checked.phone_e164:
        raise VerificationRejected()

    # Fail closed: an unestablished purpose never yields a session.
    purpose = checked.purpose or OtpPurpose.VERIFY_PHONE_CONTROL

    contact_point_id = _mark_control_verified(session, checked.phone_e164)
    result: dict[str, object] = {
        "verification_result": VerificationResult.PHONE_CONTROL_VERIFIED.value,
        "contact_point_id": contact_point_id,
        "account_id": None,
        "access_token": None,
    }

    if purpose is OtpPurpose.LOGIN:
        account_id = _activate_existing_account(session, contact_point_id)
        if account_id is not None:
            result["verification_result"] = VerificationResult.SESSION_CREATED.value
            result["account_id"] = account_id
            # Token issuance belongs to the authentication workstream (D4).
            result["access_token"] = str(account_id)

    return result


def _mark_control_verified(session: Session, phone_e164: str) -> uuid.UUID:
    """Record verified control, creating the contact point if needed.

    Creating a CONTACT_POINT is not creating a party or an account: it is the
    record of the thing whose control was just proved.
    """
    return session.execute(
        text(
            """
            INSERT INTO turab.contact_points
                   (kind, normalized_value, display_value, control_status,
                    control_verified_at, verification_method)
            VALUES ('PHONE', :value, :value, 'VERIFIED_CONTROL', now(), 'OTP_PROVIDER')
            ON CONFLICT (kind, normalized_value) DO UPDATE
               SET control_status = 'VERIFIED_CONTROL',
                   control_verified_at = now(),
                   verification_method = 'OTP_PROVIDER'
            RETURNING contact_point_id
            """
        ),
        {"value": phone_e164},
    ).scalar_one()


def _activate_existing_account(
    session: Session, contact_point_id: uuid.UUID
) -> uuid.UUID | None:
    """Activate an account bound to this login contact point, if one exists.

    A02/A03: no account is created here under any circumstance. `INVITED`
    becomes `ACTIVATED`; `SUSPENDED` and `DISABLED` are left alone, because
    proving control of a phone must not undo an administrative decision.
    """
    account = session.execute(
        text(
            """SELECT account_id, status::text AS status
                 FROM turab.user_accounts WHERE login_contact_point_id = :cp"""
        ),
        {"cp": contact_point_id},
    ).mappings().first()
    if account is None:
        return None

    if account["status"] == "INVITED":
        session.execute(
            text(
                """UPDATE turab.user_accounts
                      SET status='ACTIVATED', activated_at=now(), last_login_at=now()
                    WHERE account_id=:a"""
            ),
            {"a": account["account_id"]},
        )
        return account["account_id"]

    if account["status"] == "ACTIVATED":
        session.execute(
            text("UPDATE turab.user_accounts SET last_login_at=now() WHERE account_id=:a"),
            {"a": account["account_id"]},
        )
        return account["account_id"]

    return None


class OtpService:
    """The application service the OTP routes talk to.

    It exists so the routes hold no session. The verify path writes, so it
    opens the audited transaction here — with a null actor, which is the
    honest record of an anonymous verification and the one place
    `require_actor=False` is legitimate.
    """

    def __init__(
        self, session: Session, provider: VerificationProvider, trace_id: str
    ) -> None:
        self._session = session
        self._provider = provider
        self._trace_id = trace_id

    def start(self, *, phone_e164: str, purpose: str) -> StartedVerification:
        return start_verification(
            self._provider, phone_e164=phone_e164, purpose=purpose
        )

    def verify(self, *, verification_id: uuid.UUID, code: str) -> Mapping[str, object]:
        from ..db.session import audited_transaction

        with audited_transaction(
            self._session, None,
            {"operation": "postAuthOtpVerify", "trace_id": self._trace_id},
            require_actor=False,
        ) as session:
            return apply_verification(
                session, self._provider, verification_id=verification_id, code=code
            )
