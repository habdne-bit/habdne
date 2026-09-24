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

- For the integer columns the bound is exact: an integer is stored as sent.
- For `numeric(12,2)` it is NOT a comparison on the value sent.
  - PostgreSQL ROUNDS to the column's scale before it checks capacity or the
    `CHECK (… > 0)` (documentation §8.1.2).
  - A Python float is bound as `double precision`. Its conversion to
    `numeric` goes through 15 significant digits (`DBL_DIG`, `float8_numeric`
    in `src/backend/utils/adt/numeric.c`).
  - So `9999999999.991` is stored as `9999999999.99`, `9999999999.995`
    overflows, `0.005` is stored as `0.01`, and `0.004` becomes `0.00` and
    breaks the CHECK.
  - `PositiveArea` applies exactly that rule (review of 3010cb9). An earlier
    `le=9999999999.99` refused storable values and let `0.004` reach the
    CHECK as a 500. A differential test compares this rule with the live
    column value by value.
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

#: A positive `numeric(12,2)` value, as PostgreSQL rounds it (half away from
#: zero, to two places): every decimal in [0.005, 9999999999.995) is stored
#: as a value in [0.01, 9999999999.99]; nothing outside that interval is.
_AREA_LOWEST = Decimal("0.005")
_AREA_BEYOND = Decimal("9999999999.995")


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


def as_bound_to_numeric(value: float | int) -> Decimal:
    """The decimal PostgreSQL converts this parameter to, before the typmod.

    A float travels as `double precision` and is converted with 15
    significant digits (`DBL_DIG`); an int is exact.
    """
    return Decimal(str(value) if isinstance(value, int) else format(value, ".15g"))


def numeric_12_2_stores_as_positive(value: float | int) -> bool:
    """True exactly when a `numeric(12,2) CHECK (> 0)` column accepts it."""
    if isinstance(value, float) and not math.isfinite(value):
        return False
    return _AREA_LOWEST <= as_bound_to_numeric(value) < _AREA_BEYOND


def _positive_area(value: Any) -> Any:
    if not numeric_12_2_stores_as_positive(value):
        # No value is echoed: it is the caller's.
        raise ValueError(
            "must be an area the column stores as a positive numeric(12,2): "
            "PostgreSQL rounds to two decimals first, so it must be at least "
            "0.005 (stored as 0.01) and below 9999999999.995 (stored as "
            "9999999999.99)")
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
#: `land_area_m2` / `built_area_m2`. The contract's `exclusiveMinimum: 0` is
#: implied: every accepted value is at least 0.005.
PositiveArea = Annotated[float, BeforeValidator(_json_number),
                         AfterValidator(_positive_area)]
FiniteJson = Annotated[Any, AfterValidator(_finite_tree)]
FiniteJsonObject = Annotated[dict[str, Any], AfterValidator(_finite_tree)]
