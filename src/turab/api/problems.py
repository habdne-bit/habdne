"""RFC 7807 problem responses.

Ref: RFC-001 §12, API_CONTRACTS v0.2 §2.5, §8.

The status/code mapping is the whole of decision 2: 404 conceals, 403 says the
action is prohibited on an object the caller may already see.
"""
from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from ..auth.policy import DenyReason

MEDIA_TYPE = "application/problem+json"

#: DenyReason -> (status, code, title).
#: `NO_PARTY` and `OBJECT_NOT_AUTHORIZED` become 404 on /me/*: see `for_denial`.
_MAPPING: dict[DenyReason, tuple[int, str, str]] = {
    DenyReason.NO_POLICY: (403, "ROLE_NOT_PERMITTED", "Not permitted"),
    DenyReason.ACCOUNT_NOT_USABLE: (401, "UNAUTHENTICATED", "Not authenticated"),
    DenyReason.ROLE_NOT_PERMITTED: (403, "ROLE_NOT_PERMITTED", "Not permitted"),
    DenyReason.ROLE_CONFIGURATION_ANOMALY: (
        403, "ROLE_CONFIGURATION_ANOMALY", "Not permitted",
    ),
    DenyReason.NO_PARTY: (403, "OBJECT_NOT_AUTHORIZED", "Not permitted"),
    DenyReason.OBJECT_NOT_AUTHORIZED: (
        403, "OBJECT_NOT_AUTHORIZED", "Not permitted",
    ),
    DenyReason.CLAIM_AUTHORITY_CONFLICT: (
        409, "CLAIM_AUTHORITY_CONFLICT", "Conflicting claim authority",
    ),
}


def problem(
    status: int, code: str, title: str, trace_id: str, detail: str | None = None,
    **extra: Any,
) -> JSONResponse:
    """Build a problem response.

    `detail` is caller-supplied and must never carry database exception text,
    OTP codes or document payloads (API_CONTRACTS §2.5, §8).
    """
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title,
        "status": status,
        "code": code,
        "trace_id": trace_id,
    }
    if detail:
        body["detail"] = detail
    body.update(extra)
    return JSONResponse(status_code=status, content=body, media_type=MEDIA_TYPE)


def for_denial(
    reason: DenyReason, trace_id: str, *, customer_scoped: bool,
    detail: str | None = None,
) -> JSONResponse:
    """Map a denial to a response, applying decision 2.

    On /me/*, a failed object check returns 404: a 403 there would confirm that
    an id exists and turn the endpoint into an existence oracle for UUIDs, which
    is what K01/K02 forbid. A conflict (INV-1) is NOT concealed — it is an
    operational condition on a resource the caller may well be entitled to, and
    silently returning 404 would leave it undiagnosable.
    """
    status, code, title = _MAPPING[reason]
    if customer_scoped and reason in (
        DenyReason.OBJECT_NOT_AUTHORIZED,
        DenyReason.NO_PARTY,
    ):
        return problem(404, "NOT_FOUND", "Not found", trace_id)
    return problem(status, code, title, trace_id, detail)


def trace_id_of(request: Request) -> str:
    return getattr(request.state, "trace_id", "-")
