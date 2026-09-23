"""Request-body types that mean what the contract's JSON Schema means.

Pydantic's default `int` is LAX: it accepts `true` (as 1) and `"123"` (as 123).
Neither is an `integer` in the contract's JSON Schema, so a money field typed
`int` accepts bodies the contract refuses. `StrictInt` over-corrects: it
refuses `1.0`, which JSON Schema 2020-12 does count as an integer ("any number
with a zero fractional part", Core §4.2.1).

`JsonInteger` accepts exactly the JSON Schema set: a JSON number with a zero
fractional part, and never a boolean or a string.

`JsonNumber` is the same rule for `number`: any JSON number, integers
included (an integer IS a JSON Schema `number`), and never a boolean or a
string. Pydantic's lax `float` accepts `true` and `"1.5"`.

Neither type touches UUIDs, dates or any other field: the decision (F-3) is
about numbers only, and global strict mode would also refuse the ISO-8601
strings a JSON body can only carry dates as.
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


def _json_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a JSON number")
    return value


JsonInteger = Annotated[int, BeforeValidator(_json_integer)]
JsonNumber = Annotated[float, BeforeValidator(_json_number)]
