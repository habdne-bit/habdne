"""The canonical JSON form, and the match input hash (decision G4-13).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-13, decided in the review of aad9f34;
ADR-02 ("canonical input hash"); `API_CONTRACTS_v0.2` §6.

## Revision 2 of the form (review of 4538a2d)

Revision 1 wrote every Decimal as a JSON STRING, via `Decimal.normalize()`.
The review found two collisions BEFORE sha256, and both were reproduced on
4538a2d (`docs/gate/evidence/SLICE4-STEP2-CANONICAL-BEFORE-FIX.txt`):

1. **A number and a string became the same bytes.** The JSON number `1`
   (read by the jsonb reader as `Decimal('1')`) and the JSON string `"1"`
   were both written `"1"`. `request_criteria.value` is jsonb, and holds
   either one.
2. **The form depended on the decimal context, and lost digits.**
   `normalize()` ROUNDS to the context precision, 28 by default. Two values
   differing in the 30th significant digit were both written `"1"`. At
   precision 40 they differed. So the hash depended on
   `decimal.getcontext()`.

Revision 2 is its own serializer, written without `json.dumps` for numbers.
The format tag becomes `turab.match-input/2`.

## The form

- **Numbers are JSON numbers; strings are JSON strings.** The two can never
  meet: `1` and `"1"` are different bytes.
- **A number is written by value, exactly, without any decimal context.**
  Its text is built from `Decimal.as_tuple()`, which is the exact
  coefficient and exponent, with pure integer and string operations:
  - leading and trailing zeros removed;
  - plain notation with no exponent;
  - `0` for any zero, `-0` included.

  So `268.50`, `268.5` and `2.685E+2` are all `268.5`; `100`, `1E+2` and
  `100.00` are all `100`; and `1.00000000000000000000000000001` keeps all
  its digits under ANY context precision.
- **An int and a Decimal of equal value give the same number.** A JSON
  number has no integer/decimal distinction, and neither does value
  equality.
- **Size bound.** A number whose plain form would exceed 1000 digits is
  refused, rather than written or truncated. No real price, area or count
  comes near.
- **No binary floating point.** A float is refused (the F-3 precedent).
- **Strings** are written with `json.dumps` on the one string: UTF-8, no
  ASCII escaping, JSON's own escapes for quotes, backslash and control
  characters.
- **Objects:** keys must be strings, sorted by code point, with no
  whitespace. **Arrays** keep their order.
- **Other types, written as strings:**
  - a UUID, as its lowercase string;
  - a timezone-aware `datetime`, in UTC with microseconds and `Z` (a naive
    one is refused);
  - a `date`, ISO 8601;
  - an Enum, as its value.

  Each of these reaches the hash only from a typed COLUMN, whose position
  in a snapshot always holds that one type. The jsonb reader never
  produces them. So they cannot meet a user string in the same position,
  and collide with it, as number and string could.
- Anything else is refused, never stringified.

## The input hash

`input_hash` is sha256 over the canonical bytes of ONE document:

    {"format": "turab.match-input/2",
     "matching_policy_id", "matching_policy_version", "rule_registry_digest",
     "evaluated_offer_id": <uuid or null>,
     "request_snapshot", "property_snapshot", "commercial_context_snapshot",
     "permission_snapshot", "freshness_snapshot"}

- **`evaluated_offer_id` is a top-level element** (condition of the review
  of aad9f34). The uniqueness `(request_id, property_id,
  matching_policy_id, input_hash)` does not contain the offer.
- **The engine's own evaluation stamp is not an input, by construction.**
  The document has no place for it: the arguments are fixed and
  keyword-only.
- As a guard, `evaluated_at` and `input_hash` are refused as TOP-LEVEL keys
  of a snapshot, the fields the engine itself writes.
- **Keys inside user data are left as they are** (review of 4538a2d).
  Revision 1 searched every depth, and refused a criterion whose jsonb
  value was `{"evaluated_at": "2012-03-04"}`. That is the customer's data,
  and it is hashed like any other value.
"""
from __future__ import annotations

import datetime as dt
import enum
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any, Mapping

INPUT_FORMAT = "turab.match-input/2"

#: Fields the ENGINE writes, which must never be hashed as input. Checked on
#: each snapshot's TOP level only: below it lies user data.
FORBIDDEN_INPUT_KEYS = frozenset({"evaluated_at", "input_hash"})

#: The longest plain-notation number written; anything longer is refused.
MAX_NUMBER_DIGITS = 1000


class CanonicalError(TypeError):
    """A value has no canonical form here, so it cannot be hashed."""


def _number(value: Decimal | int, path: str) -> str:
    """The exact plain-notation text of a finite number, built from its
    digits with no decimal-context arithmetic."""
    if isinstance(value, int):
        value = Decimal(value)  # exact: int -> Decimal never rounds
    if not value.is_finite():
        raise CanonicalError(f"{path}: a non-finite number ({value}) has no canonical form")
    sign, digits, exponent = value.as_tuple()
    digits = list(digits)
    while digits and digits[0] == 0:
        digits.pop(0)
    if not digits:
        return "0"  # every zero, -0 included
    while digits[-1] == 0:
        digits.pop()
        exponent += 1
    coefficient = "".join(map(str, digits))
    if len(coefficient) + abs(exponent) > MAX_NUMBER_DIGITS:
        raise CanonicalError(f"{path}: a number beyond {MAX_NUMBER_DIGITS} digits is refused")
    if exponent >= 0:
        text = coefficient + "0" * exponent
    else:
        point = len(coefficient) + exponent
        text = (coefficient[:point] + "." + coefficient[point:] if point > 0
                else "0." + "0" * (-point) + coefficient)
    return ("-" if sign else "") + text


def _string(value: str) -> str:
    return json.dumps(value, ensure_ascii=False)


def _write(value: Any, path: str) -> str:
    if value is None:
        return "null"
    if value is True:
        return "true"
    if value is False:
        return "false"
    if isinstance(value, str):
        return _string(value)
    if isinstance(value, enum.Enum):
        return _write(value.value, path)
    if isinstance(value, float):
        raise CanonicalError(f"{path}: a float has no canonical form; use Decimal")
    if isinstance(value, (int, Decimal)):
        return _number(value, path)
    if isinstance(value, uuid.UUID):
        return _string(str(value))
    if isinstance(value, dt.datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalError(f"{path}: a naive datetime names no instant")
        return _string(value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
    if isinstance(value, dt.date):
        return _string(value.isoformat())
    if isinstance(value, Mapping):
        for key in value:
            if not isinstance(key, str):
                raise CanonicalError(f"{path}: object key {key!r} is not a string")
        return "{" + ",".join(f"{_string(k)}:{_write(value[k], f'{path}.{k}')}"
                              for k in sorted(value)) + "}"
    if isinstance(value, (list, tuple)):
        return "[" + ",".join(_write(item, f"{path}[{i}]")
                              for i, item in enumerate(value)) + "]"
    raise CanonicalError(f"{path}: {type(value).__name__} has no canonical form")


def canonical_bytes(value: Any) -> bytes:
    return _write(value, "$").encode("utf-8")


def input_document(*, matching_policy_id: uuid.UUID, matching_policy_version: str,
                   rule_registry_digest: str, evaluated_offer_id: uuid.UUID | None,
                   request_snapshot: Mapping, property_snapshot: Mapping,
                   commercial_context_snapshot: Mapping, permission_snapshot: Mapping,
                   freshness_snapshot: Mapping) -> dict:
    """The one document the hash is taken over. Every argument is keyword-only
    and required, so no input can be left out by accident."""
    snapshots = {
        "request_snapshot": request_snapshot,
        "property_snapshot": property_snapshot,
        "commercial_context_snapshot": commercial_context_snapshot,
        "permission_snapshot": permission_snapshot,
        "freshness_snapshot": freshness_snapshot,
    }
    for name, snapshot in snapshots.items():
        if not isinstance(snapshot, Mapping):
            raise CanonicalError(f"{name} must be an object")
        stamped = sorted(FORBIDDEN_INPUT_KEYS & set(snapshot))
        if stamped:
            raise CanonicalError(f"{name}.{stamped[0]}: {stamped[0]} is not a matching "
                                 "input; the engine's own stamp is never hashed")
    return {
        "format": INPUT_FORMAT,
        "matching_policy_id": matching_policy_id,
        "matching_policy_version": matching_policy_version,
        "rule_registry_digest": rule_registry_digest,
        "evaluated_offer_id": evaluated_offer_id,
        **snapshots,
    }


def input_hash(**inputs: Any) -> str:
    """sha256, hex, of the canonical bytes of `input_document(**inputs)`."""
    return hashlib.sha256(canonical_bytes(input_document(**inputs))).hexdigest()
