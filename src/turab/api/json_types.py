"""Request-body types that mean what the contract's JSON Schema means.

Pydantic's default `int` is LAX: it accepts `true` (as 1) and `"123"` (as 123).
Neither is an `integer` in the contract's JSON Schema, so a money field typed
`int` accepts bodies the contract refuses. `StrictInt` over-corrects: it
refuses `1.0`, which JSON Schema 2020-12 does count as an integer ("any number
with a zero fractional part", Core §4.2.1).

`JsonInteger` accepts exactly the JSON Schema set: a JSON number with a zero
fractional part, and never a boolean or a string.
"""
from __future__ import annotations

from typing import Annotated, Any

from pydantic import BeforeValidator


def _json_integer(value: Any) -> Any:
    # `bool` first: in Python it IS an `int`, which is the whole problem.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a JSON integer")
    if isinstance(value, float):
        if not value.is_integer():
            raise ValueError("must be a JSON integer")
        return int(value)
    return value


JsonInteger = Annotated[int, BeforeValidator(_json_integer)]
