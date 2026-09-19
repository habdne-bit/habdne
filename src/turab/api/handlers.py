"""Exception handlers — every error leaves as problem+json.

Ref: API_CONTRACTS v0.2 §2.5, §8.

Without these, FastAPI's defaults emit `{"detail": ...}` with no `code` or
`trace_id`, and an unhandled exception returns a framework 500 whose body can
carry implementation text. Both would breach the error contract on paths nobody
tested.
"""
from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .problems import _CATALOGUE, ProblemCode, coded, problem, trace_id_of

logger = logging.getLogger("turab.api")

_STATUS_CODES: dict[int, ProblemCode] = {
    400: ProblemCode.VALIDATION_FAILED,
    401: ProblemCode.UNAUTHENTICATED,
    403: ProblemCode.ROLE_NOT_PERMITTED,
    404: ProblemCode.NOT_FOUND,
    405: ProblemCode.METHOD_NOT_ALLOWED,
    409: ProblemCode.STALE_VERSION,
    422: ProblemCode.VALIDATION_FAILED,
    501: ProblemCode.NOT_IMPLEMENTED,
}


def install(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def http_exception(request: Request, exc: StarletteHTTPException):
        code = _STATUS_CODES.get(exc.status_code, ProblemCode.INTERNAL_ERROR)
        # `exc.detail` is framework- or caller-supplied and may be anything;
        # it is used only when it is already one of our stable codes.
        if isinstance(exc.detail, str) and exc.detail in ProblemCode.__members__:
            code = ProblemCode[exc.detail]
        # The transport status wins over the catalogue's. Deriving it from the
        # code would let a mapping mistake silently turn, say, a 405 into a
        # 403, reporting a method error as an authorization failure.
        status, title = _CATALOGUE[code]
        return problem(exc.status_code or status, code.value, title,
                       trace_id_of(request))

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        """K04. Undeclared or malformed fields are rejected with field detail.

        Only the field location and our own code are echoed — never the input
        value, which may be exactly the sensitive payload §8 protects.
        """
        field_errors = [
            {
                "field": ".".join(str(p) for p in err.get("loc", ()) if p != "body"),
                "code": ProblemCode.UNKNOWN_FIELD.value
                if err.get("type") == "extra_forbidden"
                else ProblemCode.VALIDATION_FAILED.value,
                "message": err.get("msg", "invalid"),
            }
            for err in exc.errors()
        ]
        return coded(
            ProblemCode.VALIDATION_FAILED,
            trace_id_of(request),
            "The request body failed validation.",
            field_errors=field_errors,
        )

    @app.exception_handler(Exception)
    async def unhandled(request: Request, exc: Exception):
        """The trace id is the only bridge between the client and the log.

        The exception text stays in the log; the client gets a code and the id.
        """
        trace_id = trace_id_of(request)
        logger.exception("unhandled error", extra={"trace_id": trace_id})
        return problem(
            500, ProblemCode.INTERNAL_ERROR.value, "Internal error", trace_id,
        )
