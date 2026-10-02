"""The freshness gate, the permission gate, and eligibility (Slice 4 step 5).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-10 and G4-11, decided in the review of
f789a59, with its two conditions:
- a valid PUBLIC_LISTING_ALLOWED binding counts for internal matching of the
  same bound resource, and grants no new sharing;
- the reason for a missing or revoked permission stays visible in the
  diagnostic, even when eligibility is NEEDS_CONFIRMATION.

Also: plan §2 (evaluation order, steps 4 to 7); ADR-04; red-team B04; spec
M-05, M-06; mandatory test 3; `schema_v0.2.3.sql` `enforce_approved_review_gate`
(a review can be APPROVED only when all four gates are PASS and eligibility
is ELIGIBLE).

## The gates, as decided

**Freshness (G4-11).** PASS when request, property and offer are each FRESH
or NOT_APPLICABLE; FAIL when any is STALE; UNKNOWN otherwise (a
NEVER_CONFIRMED state, mapped to UNKNOWN).

**Permission (G4-10).** Over the bindings that count (the offer's own
party's, with a matching scope; `snapshots.binding_state`):
- PASS when one is CURRENT;
- FAIL (CONSENT_REVOKED) when there are some, and every one is REVOKED;
- UNKNOWN (PERMISSION_MISSING, next action CONFIRM_PERMISSION) otherwise:
  none, or only one that has not started yet.

## Eligibility, in this precedence (G4-11)

1. REJECTED if the hard gate is FAIL;
2. otherwise NEED_MORE_INFORMATION if a blocking unknown exists;
3. otherwise NEEDS_CONFIRMATION if the freshness or the permission gate is
   not PASS;
4. otherwise ELIGIBLE.

## Every reason is kept, whatever the eligibility

`reasons` lists every gate that is not PASS, with its reason. It is not only
the gate that decided. A REJECTED candidate with a revoked consent says
both. A NEEDS_CONFIRMATION candidate always shows its permission reason
(the review's condition).

Reason codes are the frozen seed's, used only where their name and label
state the fact:
- REQUEST_STALE, PROPERTY_STALE and OFFER_STALE ("needs reconfirmation")
  for STALE;
- CONSENT_REVOKED for a revoked consent;
- PERMISSION_MISSING when no current binding exists.

A never-confirmed state has no seeded code. Its reason is null, and its
basis is NEVER_CONFIRMED.

**Pinned (review of a5ea6f5).** The gates and the precedence are the pinned
functions of `gates.py` (`freshness.gate@1`, `permission.gate@1`,
`eligibility.precedence@1`). This module only wires them, and records
their versions in `Eligibility.engine`.

**Pure.** Nothing here reads the database or writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from turab.matching.hard_gate import HardGate
from turab.matching.registry import REGISTRY

#: The pinned functions this module runs (review of a5ea6f5), `id@version`.
#: The logic lives in `gates.py`; this module wires their inputs together.
ENGINE = {"freshness_gate": ("freshness.gate", "1"),
          "permission_gate": ("permission.gate", "1"),
          "precedence": ("eligibility.precedence", "1")}

#: The FRESHNESS codes `freshness.gate@1` emits, per subject; read by tests
#: that check them against the seed (`gates.freshness_gate_v1` holds its own
#: copy, being self-contained).
FRESHNESS_SUBJECTS = (("request", "REQUEST_STALE"), ("property", "PROPERTY_STALE"),
                      ("offer", "OFFER_STALE"))


@dataclass(frozen=True, slots=True)
class Eligibility:
    eligibility: str
    hard_gate_status: str
    information_gate_status: str
    freshness_gate_status: str
    permission_gate_status: str
    request_freshness: str
    property_freshness: str
    offer_freshness: str
    reasons: tuple[Mapping[str, Any], ...]
    #: The pinned functions that decided, `name -> "id@version"`. Step 7
    #: stores them with the match, so that a replay runs the same versions.
    engine: Mapping[str, str]


def _run(name: str, *args: Any) -> Any:
    return REGISTRY.resolve(*ENGINE[name]).evaluate(*args)


def freshness_gate(freshness: Mapping[str, Any]) -> tuple[str, list[dict]]:
    out = _run("freshness_gate", freshness)
    return out["status"], out["reasons"]


def permission_gate(permission: Mapping[str, Any]) -> tuple[str, list[dict]]:
    out = _run("permission_gate", permission)
    return out["status"], out["reasons"]


def hard_summary(hard: HardGate) -> dict:
    """What the precedence reads from the hard gate."""
    by_key = {(r.criterion_code, r.ordinal): r for r in hard.results}

    def entries(keys):
        return [{"criterion": code, "ordinal": ordinal,
                 "reason_code": by_key[(code, ordinal)].reason_code} for code, ordinal in keys]
    return {"hard_gate_status": hard.hard_gate_status,
            "information_gate_status": hard.information_gate_status,
            "required_failures": entries(hard.required_failures),
            "blocking_unknowns": entries(hard.blocking_unknowns)}


def eligibility_of(hard: HardGate, freshness: Mapping[str, Any],
                   permission: Mapping[str, Any]) -> Eligibility:
    """G4-11's precedence over the four gates, with every reason kept, each
    decision taken by a pinned function."""
    fresh = _run("freshness_gate", freshness)
    perm = _run("permission_gate", permission)
    verdict = _run("precedence", hard_summary(hard), fresh, perm)
    return Eligibility(
        eligibility=verdict["eligibility"], hard_gate_status=hard.hard_gate_status,
        information_gate_status=hard.information_gate_status,
        freshness_gate_status=fresh["status"], permission_gate_status=perm["status"],
        request_freshness=freshness["request"]["state"],
        property_freshness=freshness["property"]["state"],
        offer_freshness=freshness["offer"]["state"], reasons=tuple(verdict["reasons"]),
        engine={name: "@".join(key) for name, key in ENGINE.items()})
