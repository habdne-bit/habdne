"""A request body parsed so that its numbers keep their value.

Ref: Slice 8 plan (`docs/gate/SLICE_8_PLAN.md`) Q-C1 (a), decided in the
review of `5054bd0`; M15 (`docs/gate/evidence/SLICE8-NUMBER-PARSING-MEASUREMENTS.txt`).

FastAPI parses a body with `json.loads`, which turns every non-integer number
into a float: `1e400` becomes infinity, and `1e-400`, `1.0000000000000001`
and `0.99999999999999999` become integers. The contract's JSON Schema judges
the number the text denotes (Validation 6.1.1, 6.2.4), so a judge reading
those floats disagrees with it, in both directions (M15).

`parse_exact` reads the body's bytes instead:
- a non-integer number becomes a `decimal.Decimal`, exact for every decimal
  literal;
- an integer stays an `int`, and one beyond Python's default limit of 4300
  digits (`sys.int_max_str_digits`) becomes an exact `Decimal` rather than a
  refusal: the schema accepts it, so the parser does too;
- `NaN`, `Infinity` and `-Infinity`, which Python accepts and JSON does not
  (RFC 8259 6), are refused.

**Every refusal is classified** (`BodyNotParsed`), never a general exception,
with the status FastAPI's own parsing gives the same body (measured on the
conversion route, M16): `400 VALIDATION_FAILED` for a body that is not UTF-8
(RFC 8259 8.1) or nests beyond the parser's recursion, `422
VALIDATION_FAILED` for one that is not JSON or carries a non-JSON constant.
`ExactJsonBody` raises them before the route's handler runs, so before any
command claims an idempotency key.

**It activates nothing:** no route uses it yet. The conversion (Slice 8 step
3) is where an accepted value is carried to storage, and tested there.
"""
from __future__ import annotations

import decimal
import json
from typing import Annotated, Any

from fastapi import Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError


class BodyNotParsed(Exception):
    """A body refused at parsing: `status` 400 or 422, a fixed message that
    names no part of the body."""

    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _integer(literal: str) -> int | decimal.Decimal:
    try:
        return int(literal)
    except ValueError:
        # Beyond sys.int_max_str_digits: kept exactly, not refused.
        return decimal.Decimal(literal)


def _constant(name: str) -> Any:
    raise BodyNotParsed(422, "a non-finite number is not JSON")


def parse_exact(raw: bytes) -> Any:
    """The JSON value `raw` denotes, its numbers exact; or `BodyNotParsed`."""
    try:
        text_ = raw.decode("utf-8")
    except UnicodeDecodeError:
        raise BodyNotParsed(400, "the body is not UTF-8") from None
    try:
        return json.loads(text_, parse_float=decimal.Decimal, parse_int=_integer,
                          parse_constant=_constant)
    except BodyNotParsed:
        raise
    except RecursionError:
        raise BodyNotParsed(400, "the body nests too deeply to be parsed") from None
    except ValueError:  # json.JSONDecodeError is a ValueError
        raise BodyNotParsed(422, "the body is not JSON") from None


async def exact_json_body(request: Request) -> Any:
    """The request's body by `parse_exact`; a refusal is answered as FastAPI
    answers the same body: 400 as an `HTTPException`, 422 as a
    `RequestValidationError`, each a `VALIDATION_FAILED` problem."""
    try:
        return parse_exact(await request.body())
    except BodyNotParsed as refused:
        if refused.status == 400:
            raise HTTPException(status_code=400, detail="VALIDATION_FAILED") from None
        raise RequestValidationError([{"type": "json_invalid", "loc": ("body",),
                                       "msg": refused.message}]) from None


ExactJsonBody = Annotated[Any, Depends(exact_json_body)]
