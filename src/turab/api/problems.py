"""RFC 7807 problem responses — the complete error contract.

Ref: RFC-001 §12; API_CONTRACTS v0.2 §2.5, §8; the frozen `Problem` schema
(`title`, `status`, `code`, `trace_id` required, plus optional `type`,
`detail`, `field_errors`).

Two rules govern everything here:
  * decision 2 — 404 conceals, 403 says the action is barred on an object the
    caller may already see;
  * §2.5 / §8 — `detail` never carries database exception text, OTP codes or
    document payloads.
"""
from __future__ import annotations

from enum import StrEnum
from typing import Any, Iterable

from fastapi import Request
from fastapi.responses import JSONResponse

from ..auth.policy import DenyReason

MEDIA_TYPE = "application/problem+json"


class ProblemCode(StrEnum):
    """Stable codes. API_CONTRACTS §2.5 requires these rather than DB text."""

    UNAUTHENTICATED = "UNAUTHENTICATED"
    ROLE_NOT_PERMITTED = "ROLE_NOT_PERMITTED"
    ROLE_CONFIGURATION_ANOMALY = "ROLE_CONFIGURATION_ANOMALY"
    OBJECT_NOT_AUTHORIZED = "OBJECT_NOT_AUTHORIZED"
    ACTION_NOT_PERMITTED = "ACTION_NOT_PERMITTED"
    NOT_FOUND = "NOT_FOUND"
    METHOD_NOT_ALLOWED = "METHOD_NOT_ALLOWED"
    VALIDATION_FAILED = "VALIDATION_FAILED"
    UNKNOWN_FIELD = "UNKNOWN_FIELD"
    IDEMPOTENCY_KEY_REQUIRED = "IDEMPOTENCY_KEY_REQUIRED"
    IDEMPOTENCY_KEY_CONFLICT = "IDEMPOTENCY_KEY_CONFLICT"
    IF_MATCH_REQUIRED = "IF_MATCH_REQUIRED"
    STALE_VERSION = "STALE_VERSION"
    CLAIM_AUTHORITY_CONFLICT = "CLAIM_AUTHORITY_CONFLICT"
    CONSENT_REVOKED = "CONSENT_REVOKED"
    HARD_GATE_FAILED = "HARD_GATE_FAILED"
    IDENTITY_ALIAS_NOT_CANONICAL = "IDENTITY_ALIAS_NOT_CANONICAL"
    RESOURCE_ALREADY_CLAIMED = "RESOURCE_ALREADY_CLAIMED"
    RESOURCE_NOT_CLAIMABLE = "RESOURCE_NOT_CLAIMABLE"
    INVALID_ROLE_COMBINATION = "INVALID_ROLE_COMBINATION"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    INTERNAL_ERROR = "INTERNAL_ERROR"


#: code -> (status, title). One place, so a code cannot acquire two statuses.
_CATALOGUE: dict[ProblemCode, tuple[int, str]] = {
    ProblemCode.UNAUTHENTICATED: (401, "Not authenticated"),
    ProblemCode.ROLE_NOT_PERMITTED: (403, "Not permitted"),
    ProblemCode.ROLE_CONFIGURATION_ANOMALY: (403, "Not permitted"),
    ProblemCode.OBJECT_NOT_AUTHORIZED: (403, "Not permitted"),
    ProblemCode.ACTION_NOT_PERMITTED: (403, "Action not permitted"),
    ProblemCode.NOT_FOUND: (404, "Not found"),
    ProblemCode.METHOD_NOT_ALLOWED: (405, "Method not allowed"),
    ProblemCode.VALIDATION_FAILED: (422, "Validation failed"),
    ProblemCode.UNKNOWN_FIELD: (422, "Unknown field"),
    ProblemCode.IDEMPOTENCY_KEY_REQUIRED: (400, "Idempotency-Key required"),
    ProblemCode.IDEMPOTENCY_KEY_CONFLICT: (409, "Idempotency key conflict"),
    ProblemCode.IF_MATCH_REQUIRED: (428, "If-Match required"),
    ProblemCode.STALE_VERSION: (409, "Stale version"),
    ProblemCode.CLAIM_AUTHORITY_CONFLICT: (409, "Conflicting claim authority"),
    ProblemCode.CONSENT_REVOKED: (409, "Consent revoked"),
    ProblemCode.HARD_GATE_FAILED: (409, "Hard gate failed"),
    ProblemCode.IDENTITY_ALIAS_NOT_CANONICAL: (409, "Alias is not canonical"),
    ProblemCode.RESOURCE_ALREADY_CLAIMED: (409, "Already claimed"),
    ProblemCode.RESOURCE_NOT_CLAIMABLE: (409, "Not claimable"),
    ProblemCode.INVALID_ROLE_COMBINATION: (422, "Invalid role combination"),
    ProblemCode.PROVIDER_UNAVAILABLE: (503, "Verification provider unavailable"),
    ProblemCode.NOT_IMPLEMENTED: (501, "Not implemented"),
    ProblemCode.INTERNAL_ERROR: (500, "Internal error"),
}

#: Substrings that must never reach a client in `detail` (§2.5, §8).
_LEAK_MARKERS: tuple[str, ...] = (
    "SELECT ", "INSERT ", "UPDATE ", "DELETE ", "psycopg", "sqlalchemy",
    "Traceback", "turab.", "DETAIL:", "HINT:", "otp",
)


class DetailLeak(RuntimeError):
    """A problem `detail` tried to carry implementation text."""


def _check_detail(detail: str | None) -> None:
    if not detail:
        return
    lowered = detail.lower()
    for marker in _LEAK_MARKERS:
        if marker.lower() in lowered:
            raise DetailLeak(
                f"problem detail may not contain {marker!r}: domain failures "
                "expose stable codes, not database or implementation text "
                "(API_CONTRACTS §2.5)"
            )


def problem(
    status: int,
    code: str,
    title: str,
    trace_id: str,
    detail: str | None = None,
    *,
    field_errors: Iterable[dict[str, str]] | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    _check_detail(detail)
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": code,
        "trace_id": trace_id,
    }
    if detail:
        body["detail"] = detail
    if field_errors:
        body["field_errors"] = list(field_errors)
    body.update(extra)
    return JSONResponse(
        status_code=status, content=body, media_type=MEDIA_TYPE, headers=headers,
    )


def coded(
    code: ProblemCode, trace_id: str, detail: str | None = None, **kwargs: Any
) -> JSONResponse:
    """Build a problem from the catalogue, so status and code cannot diverge."""
    status, title = _CATALOGUE[code]
    return problem(status, code.value, title, trace_id, detail, **kwargs)


#: Denial reasons that are concealed on /me/* (decision 2).
_CONCEALED = (DenyReason.OBJECT_NOT_AUTHORIZED, DenyReason.NO_PARTY)

_DENIAL_CODES: dict[DenyReason, ProblemCode] = {
    DenyReason.NO_POLICY: ProblemCode.ROLE_NOT_PERMITTED,
    DenyReason.ACCOUNT_NOT_USABLE: ProblemCode.UNAUTHENTICATED,
    DenyReason.ROLE_NOT_PERMITTED: ProblemCode.ROLE_NOT_PERMITTED,
    DenyReason.ROLE_CONFIGURATION_ANOMALY: ProblemCode.ROLE_CONFIGURATION_ANOMALY,
    DenyReason.NO_PARTY: ProblemCode.OBJECT_NOT_AUTHORIZED,
    DenyReason.OBJECT_NOT_AUTHORIZED: ProblemCode.OBJECT_NOT_AUTHORIZED,
    DenyReason.CLAIM_AUTHORITY_CONFLICT: ProblemCode.CLAIM_AUTHORITY_CONFLICT,
}

#: The one fixed body for a disclosed claim conflict. Says only THAT the claim
#: is contested: no claimant identity, no count, nothing a caller could use to
#: identify the other party.
CONFLICT_DETAIL = (
    "This record's claim authority is contested and requires operational "
    "resolution."
)


def for_denial(
    reason: DenyReason, trace_id: str, *, customer_scoped: bool,
    detail: str | None = None,
) -> JSONResponse:
    """Map a denial to a response, applying decision 2.

    On /me/*, a failed object check returns 404: a 403 there would confirm an
    id exists and turn the endpoint into an existence oracle (K01/K02).
    """
    if reason is DenyReason.CLAIM_AUTHORITY_CONFLICT:
        # `detail` is ignored on purpose: no call site can widen this body.
        return coded(ProblemCode.CLAIM_AUTHORITY_CONFLICT, trace_id, CONFLICT_DETAIL)

    if customer_scoped and reason in _CONCEALED:
        return coded(ProblemCode.NOT_FOUND, trace_id)

    return coded(_DENIAL_CODES[reason], trace_id, detail)


def trace_id_of(request: Request) -> str:
    return getattr(request.state, "trace_id", "-")
