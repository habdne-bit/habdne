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

**Finite numbers only** (review of 1c2f6c5, defect 2). Python's `json.loads`,
which parses every request body, accepts `1e400` (as `inf`), `NaN`,
`Infinity` and `-Infinity`. None is a JSON number: RFC 8259 §6 says "Numeric
values that cannot be represented in the grammar below (such as Infinity and
NaN) are not permitted", and PostgreSQL's `jsonb` refuses the `Infinity`
token `json.dumps` writes for them. So:

- `JsonNumber` and `JsonInteger` refuse a non-finite value (`JsonNumber` by
  its own check; `JsonInteger` because a non-finite float is not integral);
- `FiniteJson` / `FiniteJsonObject` type the free JSON fields (a claimed or
  resolved value, an observation or lead payload, source metadata, a
  criterion value) and refuse a non-finite number AT ANY DEPTH.

**Storage bounds.** The contract's integers and numbers carry no maximum; the
frozen columns do (`bigint`, `smallint`, `numeric(12,2)`). A value outside the
column is not storable, and reached the database as an error. The bounds
below are the columns' own, so nothing storable is refused.
"""
from __future__ import annotations

import math
from decimal import Decimal
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator

#: PostgreSQL `bigint` and `smallint` (PostgreSQL 16 documentation, §8.1.1,
#: Table 8.2) and the largest `numeric(12,2)` (§8.1.2: precision 12, scale 2).
BIGINT_MAX = 2**63 - 1
SMALLINT_MIN, SMALLINT_MAX = -(2**15), 2**15 - 1
NUMERIC_12_2_MAX = float(Decimal("9999999999.99"))


def _json_integer(value: Any) -> Any:
    # `bool` first: in Python it IS an `int`, which is the whole problem.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a JSON integer")
    if isinstance(value, float):
        # `is_integer()` is False for inf and NaN ("finite with integral
        # value", Python documentation, float.is_integer), so a non-finite
        # float is refused here with no separate check.
        if not value.is_integer():
            raise ValueError("must be a JSON integer")
        return int(value)
    return value


def _json_number(value: Any) -> Any:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("must be a JSON number")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("must be a finite JSON number")
    return value


def _finite_tree(value: Any) -> Any:
    """Refuse a non-finite float anywhere inside a parsed JSON value.

    Iterative, so a deeply nested body cannot exhaust the stack. The message
    names no path and no value: both are the caller's text.
    """
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, float):
            if not math.isfinite(item):
                raise ValueError("must contain only finite JSON numbers")
        elif isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return value


JsonInteger = Annotated[int, BeforeValidator(_json_integer)]
JsonNumber = Annotated[float, BeforeValidator(_json_number)]
FiniteJson = Annotated[Any, AfterValidator(_finite_tree)]
FiniteJsonObject = Annotated[dict[str, Any], AfterValidator(_finite_tree)]
