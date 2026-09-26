"""The canonical JSON form, and the match input hash (decision G4-13).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-13, decided in the review of aad9f34;
ADR-02 ("canonical input hash"); `API_CONTRACTS_v0.2` §6.

## The canonical form

One byte string per value, whatever order or type the value was built in:

- UTF-8, with no ASCII escaping, so Arabic text is hashed as written;
- object keys sorted, and every key a string;
- separators `,` and `:`, with no whitespace;
- **no binary floating point**. A float is refused (the F-3 precedent):
  `0.1 + 0.2` is not a price. Exact numbers travel as `Decimal`. A Decimal is
  written as a string, **by value**: `268.50`, `268.5` and `2.685E+2` are
  the same number and give the same bytes. NaN and infinities are refused;
- integers stay JSON integers (versions, counts, DZD amounts in `bigint`);
- a UUID becomes its lowercase string;
- a `datetime` must carry a time zone. It is written in UTC, with
  microseconds, and a `Z` suffix, so one instant gives one string whatever
  zone it was read in. A naive datetime is refused, because it names no
  instant;
- a `date` is written ISO 8601;
- an Enum is written as its value;
- anything else is refused rather than stringified. A value this module
  does not know is a value the hash would not describe.

## The input hash

`input_hash` is sha256 over the canonical bytes of ONE document:

    {"format": "turab.match-input/1",
     "matching_policy_id": ..., "matching_policy_version": ...,
     "rule_registry_digest": ...,
     "evaluated_offer_id": <uuid or null>,
     "request_snapshot": ..., "property_snapshot": ...,
     "commercial_context_snapshot": ..., "permission_snapshot": ...,
     "freshness_snapshot": ...}

- **`evaluated_offer_id` is a top-level element** (condition of the review
  of aad9f34). The schema's uniqueness is `(request_id, property_id,
  matching_policy_id, input_hash)`, and it does not contain the offer. Two
  offers of one property on identical terms must therefore differ in the
  hash itself, or the second would be taken for an identical re-run of the
  first.
- **`evaluated_at` is not an input.** It is refused anywhere inside a
  snapshot, together with `input_hash`, so an identical run gives an
  identical hash and returns the existing match (G4-13).
"""
from __future__ import annotations

import datetime as dt
import enum
import hashlib
import json
import uuid
from decimal import Decimal
from typing import Any, Mapping

INPUT_FORMAT = "turab.match-input/1"

#: Keys that must never be hashed as input. `evaluated_at` would make every
#: run unique, and a hash cannot contain itself.
FORBIDDEN_INPUT_KEYS = frozenset({"evaluated_at", "input_hash"})

SNAPSHOT_KEYS = ("request_snapshot", "property_snapshot", "commercial_context_snapshot",
                 "permission_snapshot", "freshness_snapshot")


class CanonicalError(TypeError):
    """A value has no canonical form here, so it cannot be hashed."""


def _decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise CanonicalError(f"a non-finite number ({value}) has no canonical form")
    if value == 0:
        return "0"  # -0 and 0E-2 are zero
    return format(value.normalize(), "f")


def normalize(value: Any, *, path: str = "$") -> Any:
    """Return `value` as plain JSON types, in canonical form. Refuses
    anything without one."""
    if value is None or isinstance(value, (bool, str)):
        return value
    if isinstance(value, enum.Enum):
        return normalize(value.value, path=path)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        raise CanonicalError(f"{path}: a float has no canonical form; use Decimal")
    if isinstance(value, Decimal):
        return _decimal(value)
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dt.datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise CanonicalError(f"{path}: a naive datetime names no instant")
        return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    if isinstance(value, dt.date):
        return value.isoformat()
    if isinstance(value, Mapping):
        out = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise CanonicalError(f"{path}: object key {key!r} is not a string")
            out[key] = normalize(item, path=f"{path}.{key}")
        return out
    if isinstance(value, (list, tuple)):
        return [normalize(item, path=f"{path}[{i}]") for i, item in enumerate(value)]
    raise CanonicalError(f"{path}: {type(value).__name__} has no canonical form")


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(normalize(value), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False, allow_nan=False).encode("utf-8")


def _refuse_forbidden_keys(value: Any, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if key in FORBIDDEN_INPUT_KEYS:
                raise CanonicalError(f"{path}.{key}: {key} is not a matching input")
            _refuse_forbidden_keys(item, f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for i, item in enumerate(value):
            _refuse_forbidden_keys(item, f"{path}[{i}]")


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
        _refuse_forbidden_keys(snapshot, name)
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
