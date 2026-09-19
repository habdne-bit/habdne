"""Phone control verification and account activation — Slice 1.

Ref: IMPLEMENTATION_SLICES_v0.2.md Slice 1; API_CONTRACTS v0.2 §4.1;
ADR-07; red-team A02, A03.

The invariant this module protects, from Master §4 (11) and ADR-07:

    a verified phone proves control of a CONTACT_POINT.
    It does not create a PARTY, and it does not create a USER_ACCOUNT.

`VERIFY_PHONE_CONTROL` therefore changes exactly one thing — the contact
point's control status — and `LOGIN` creates a session only where an account
already exists for that contact point. Neither purpose ever manufactures one.

## Where challenge state lives — an open gap, raised not invented

The frozen schema has **no table for OTP challenges**, yet the contract's
`POST /auth/otp/start` returns a `challenge_id` and `expires_at`, and
`/verify` takes that id back. Nothing in `schema_v0.2.3.sql` can hold it.

That is a real gap of the same kind as delegated authority (RFC-001 Q7), so it
is not resolved here by inventing a table. Instead the carrier is a protocol
with a development implementation, and the production choice is a decision:

  (a) delegate to the SMS/WhatsApp provider's verification API, which issues
      and checks the code and needs no table — `challenge_id` becomes the
      provider's verification id, and it fits the integration boundary the
      Foundation already describes; or
  (b) add a table, which is a schema change with its own approval and package.

`InMemoryChallengeStore` is (a)-shaped but local: it is correct for a single
process and **wrong for more than one**, so it is not production-viable and is
named so that nobody mistakes it for a finished choice. What is finished, and
fully tested, is the domain outcome: the contact point's verified control, and
activation strictly from an existing account.
"""
from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Mapping, Protocol

from sqlalchemy import text
from sqlalchemy.orm import Session

from .parties import normalize_phone

CHALLENGE_TTL = timedelta(minutes=10)
CODE_LENGTH = 6
MAX_ATTEMPTS = 5


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


class ChallengeNotFound(OtpError):
    def __init__(self) -> None:
        # Deliberately indistinguishable from a wrong code: telling a caller
        # that a challenge id exists is itself information.
        super().__init__("OTP_INVALID", "the challenge is unknown, expired or used")


class ChallengeExpired(ChallengeNotFound):
    pass


class WrongCode(OtpError):
    def __init__(self) -> None:
        super().__init__("OTP_INVALID", "the challenge is unknown, expired or used")


@dataclass(slots=True)
class Challenge:
    challenge_id: uuid.UUID
    phone_e164: str
    purpose: OtpPurpose
    code: str
    expires_at: datetime
    attempts: int = 0


class ChallengeStore(Protocol):
    def put(self, challenge: Challenge) -> None: ...
    def take(self, challenge_id: uuid.UUID) -> Challenge | None: ...
    def discard(self, challenge_id: uuid.UUID) -> None: ...


class InMemoryChallengeStore:
    """Development carrier. NOT production-viable: see the module docstring.

    Single-process only. With more than one worker a challenge issued by one
    would be unknown to another, so verification would fail at random.
    """

    def __init__(self) -> None:
        self._challenges: dict[uuid.UUID, Challenge] = {}

    def put(self, challenge: Challenge) -> None:
        self._challenges[challenge.challenge_id] = challenge

    def take(self, challenge_id: uuid.UUID) -> Challenge | None:
        return self._challenges.get(challenge_id)

    def discard(self, challenge_id: uuid.UUID) -> None:
        self._challenges.pop(challenge_id, None)


def start_challenge(
    store: ChallengeStore, *, phone_e164: str, purpose: str,
    now: datetime | None = None,
) -> Challenge:
    """Issue a challenge. Creates no party, no contact point and no account."""
    normalized = normalize_phone(phone_e164)
    try:
        parsed = OtpPurpose(purpose)
    except ValueError as exc:
        raise OtpError(
            "VALIDATION_FAILED", f"purpose must be one of {list(OtpPurpose)}"
        ) from exc

    now = now or datetime.now(UTC)
    challenge = Challenge(
        challenge_id=uuid.uuid4(),
        phone_e164=normalized,
        purpose=parsed,
        code=f"{secrets.randbelow(10 ** CODE_LENGTH):0{CODE_LENGTH}d}",
        expires_at=now + CHALLENGE_TTL,
    )
    store.put(challenge)
    return challenge


def verify_challenge(
    session: Session,
    store: ChallengeStore,
    *,
    challenge_id: uuid.UUID,
    code: str,
    now: datetime | None = None,
) -> Mapping[str, object]:
    """Check the code and apply the outcome the purpose allows.

    A02: `VERIFY_PHONE_CONTROL` marks the contact point verified and stops
    there. `LOGIN` may open a session only when an account already exists;
    where none does, the result is still `PHONE_CONTROL_VERIFIED` and the
    caller learns that control was proved but no session was created. That is
    the contract's `account_id` being nullable "by design" (§4.1).
    """
    now = now or datetime.now(UTC)
    challenge = store.take(challenge_id)
    if challenge is None:
        raise ChallengeNotFound()
    if challenge.expires_at <= now:
        store.discard(challenge_id)
        raise ChallengeExpired()

    if not secrets.compare_digest(challenge.code, (code or "").strip()):
        challenge.attempts += 1
        if challenge.attempts >= MAX_ATTEMPTS:
            # Burn the challenge rather than let it be brute-forced.
            store.discard(challenge_id)
        raise WrongCode()

    store.discard(challenge_id)

    contact_point_id = _mark_control_verified(session, challenge.phone_e164)
    result: dict[str, object] = {
        "verification_result": VerificationResult.PHONE_CONTROL_VERIFIED.value,
        "contact_point_id": contact_point_id,
        "account_id": None,
        "access_token": None,
    }

    if challenge.purpose is OtpPurpose.LOGIN:
        account_id = _activate_existing_account(session, contact_point_id)
        if account_id is not None:
            result["verification_result"] = VerificationResult.SESSION_CREATED.value
            result["account_id"] = account_id
            # Token issuance belongs to the authentication workstream (D4).
            # The bearer is currently the account id; see api/deps.py.
            result["access_token"] = str(account_id)

    return result


def _mark_control_verified(session: Session, phone_e164: str) -> uuid.UUID:
    """Record verified control of the contact point, creating it if needed.

    Creating the CONTACT_POINT is not creating a party or an account: it is
    the record of the thing whose control was just proved.
    """
    row = session.execute(
        text(
            """
            INSERT INTO turab.contact_points
                   (kind, normalized_value, display_value, control_status,
                    control_verified_at, verification_method)
            VALUES ('PHONE', :value, :value, 'VERIFIED_CONTROL', now(), 'OTP')
            ON CONFLICT (kind, normalized_value) DO UPDATE
               SET control_status = 'VERIFIED_CONTROL',
                   control_verified_at = now(),
                   verification_method = 'OTP'
            RETURNING contact_point_id
            """
        ),
        {"value": phone_e164},
    ).scalar_one()
    return row


def _activate_existing_account(
    session: Session, contact_point_id: uuid.UUID
) -> uuid.UUID | None:
    """Activate an account bound to this login contact point, if one exists.

    A02/A03: no account is created here under any circumstance. `INVITED`
    becomes `ACTIVATED`; `SUSPENDED` and `DISABLED` are left alone, because
    proving control of a phone must not resurrect an account someone disabled.
    """
    account = session.execute(
        text(
            """
            SELECT account_id, status::text AS status
              FROM turab.user_accounts
             WHERE login_contact_point_id = :cp
            """
        ),
        {"cp": contact_point_id},
    ).mappings().first()
    if account is None:
        return None

    if account["status"] == "INVITED":
        session.execute(
            text(
                """UPDATE turab.user_accounts
                      SET status = 'ACTIVATED', activated_at = now(),
                          last_login_at = now()
                    WHERE account_id = :a"""
            ),
            {"a": account["account_id"]},
        )
        return account["account_id"]

    if account["status"] == "ACTIVATED":
        session.execute(
            text("UPDATE turab.user_accounts SET last_login_at = now() WHERE account_id = :a"),
            {"a": account["account_id"]},
        )
        return account["account_id"]

    return None


class OtpService:
    """The application service the OTP routes talk to.

    It exists so the routes hold no session. The verify path writes, so it
    opens the audited transaction here rather than in the route — with a null
    actor, which is the honest record of an anonymous verification, and the one
    place `require_actor=False` is legitimately used.
    """

    def __init__(
        self, session: Session, store: ChallengeStore, trace_id: str
    ) -> None:
        self._session = session
        self._store = store
        self._trace_id = trace_id

    def start(self, *, phone_e164: str, purpose: str) -> Challenge:
        return start_challenge(self._store, phone_e164=phone_e164, purpose=purpose)

    def verify(self, *, challenge_id: uuid.UUID, code: str) -> Mapping[str, object]:
        from ..db.session import audited_transaction

        with audited_transaction(
            self._session, None,
            {"operation": "postAuthOtpVerify", "trace_id": self._trace_id},
            require_actor=False,
        ) as session:
            return verify_challenge(
                session, self._store, challenge_id=challenge_id, code=code
            )
