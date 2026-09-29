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

**Pure.** Nothing here reads the database or writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from turab.matching.hard_gate import HardGate

FRESHNESS_SUBJECTS = (("request", "REQUEST_STALE"), ("property", "PROPERTY_STALE"),
                      ("offer", "OFFER_STALE"))
#: Binding states that are not this party's valid consent: they do not count.
NOT_COUNTED = ("OTHER_PARTY", "SCOPE_MISMATCH")


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


def freshness_gate(freshness: Mapping[str, Any]) -> tuple[str, list[dict]]:
    states = {subject: freshness[subject]["state"] for subject, _ in FRESHNESS_SUBJECTS}
    if any(state == "STALE" for state in states.values()):
        status = "FAIL"
    elif all(state in ("FRESH", "NOT_APPLICABLE") for state in states.values()):
        status = "PASS"
    else:
        status = "UNKNOWN"
    reasons = []
    for subject, stale_code in FRESHNESS_SUBJECTS:
        entry = freshness[subject]
        if entry["state"] == "STALE":
            reasons.append({"gate": "FRESHNESS", "subject": subject.upper(),
                            "reason_code": stale_code, "basis": "STALE"})
        elif entry["state"] == "UNKNOWN":
            reasons.append({"gate": "FRESHNESS", "subject": subject.upper(),
                            "reason_code": None, "basis": entry["basis"]})
    return status, reasons


def permission_gate(permission: Mapping[str, Any]) -> tuple[str, list[dict]]:
    counted = [b for b in permission["bindings"] if b["state"] not in NOT_COUNTED]
    current = [b for b in counted if b["state"] == "CURRENT"]
    if current:
        return "PASS", []
    if counted and all(b["state"] == "REVOKED" for b in counted):
        return "FAIL", [{"gate": "PERMISSION", "subject": "OFFER",
                         "reason_code": "CONSENT_REVOKED", "basis": "ONLY_REVOKED_BINDINGS"}]
    return "UNKNOWN", [{"gate": "PERMISSION", "subject": "OFFER",
                        "reason_code": "PERMISSION_MISSING",
                        "basis": "NO_CURRENT_BINDING" if not counted else "NOT_STARTED",
                        "next_action": "CONFIRM_PERMISSION"}]


def eligibility_of(hard: HardGate, freshness: Mapping[str, Any],
                   permission: Mapping[str, Any]) -> Eligibility:
    """G4-11's precedence over the four gates, with every reason kept."""
    fresh_status, fresh_reasons = freshness_gate(freshness)
    perm_status, perm_reasons = permission_gate(permission)
    by_key = {(r.criterion_code, r.ordinal): r for r in hard.results}
    reasons = [{"gate": "HARD", "criterion": code, "ordinal": ordinal,
                "reason_code": by_key[(code, ordinal)].reason_code, "basis": "REQUIRED_FAIL"}
               for code, ordinal in hard.required_failures]
    reasons += [{"gate": "INFORMATION", "criterion": code, "ordinal": ordinal,
                 "reason_code": by_key[(code, ordinal)].reason_code,
                 "basis": "BLOCKING_UNKNOWN"}
                for code, ordinal in hard.blocking_unknowns]
    reasons += fresh_reasons + perm_reasons
    if hard.hard_gate_status == "FAIL":
        verdict = "REJECTED"
    elif hard.information_gate_status != "PASS":
        verdict = "NEED_MORE_INFORMATION"
    elif fresh_status != "PASS" or perm_status != "PASS":
        verdict = "NEEDS_CONFIRMATION"
    else:
        verdict = "ELIGIBLE"
    return Eligibility(
        eligibility=verdict, hard_gate_status=hard.hard_gate_status,
        information_gate_status=hard.information_gate_status,
        freshness_gate_status=fresh_status, permission_gate_status=perm_status,
        request_freshness=freshness["request"]["state"],
        property_freshness=freshness["property"]["state"],
        offer_freshness=freshness["offer"]["state"], reasons=tuple(reasons))
