"""JSON that keeps every number exactly as stored (review of bf052f4, R-S4-7-03).

Python's `json` reads a non-integer number as a binary float, and writes no
Decimal at all. A value stored exactly in PostgreSQL (`numeric`, or a number
inside `jsonb`) therefore changed on its way to a response:
`400.12654321098765432` became `400.1265432109877`. The same happened to a
stored response replayed by idempotency (API_CONTRACTS §2.3).

- `loads` reads every non-integer number as `Decimal`; integers stay `int`.
- `dumps` writes a `Decimal` as its own digits, which is a JSON number, and
  everything else as `json.dumps` would: a float by its shortest repr,
  strings without ASCII escaping, keys in their given order. A non-finite
  number is refused, as `JSONResponse` refuses one.

Numbers stay JSON numbers. Nothing here is a canonical form: that is
`matching.canonical`, which is for hashing, sorts keys and refuses floats.
"""
from __future__ import annotations

import json
import math
from decimal import Decimal
from typing import Any, Mapping


def loads(text: str) -> Any:
    return json.loads(text, parse_float=Decimal)


def _write(value: Any, out: list[str]) -> None:
    if value is None:
        out.append("null")
    elif value is True:
        out.append("true")
    elif value is False:
        out.append("false")
    elif isinstance(value, str):
        out.append(json.dumps(value, ensure_ascii=False))
    elif isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("a non-finite number has no JSON form")
        out.append(str(value))
    elif isinstance(value, int):
        out.append(str(int(value)))
    elif isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("a non-finite number has no JSON form")
        out.append(json.dumps(value))
    elif isinstance(value, Mapping):
        out.append("{")
        for i, (key, item) in enumerate(value.items()):
            if not isinstance(key, str):
                raise TypeError(f"JSON object keys are strings, not {type(key).__name__}")
            if i:
                out.append(",")
            out.append(json.dumps(key, ensure_ascii=False))
            out.append(":")
            _write(item, out)
        out.append("}")
    elif isinstance(value, (list, tuple)):
        out.append("[")
        for i, item in enumerate(value):
            if i:
                out.append(",")
            _write(item, out)
        out.append("]")
    else:
        raise TypeError(f"{type(value).__name__} is not JSON")


def dumps(value: Any) -> str:
    out: list[str] = []
    _write(value, out)
    return "".join(out)
