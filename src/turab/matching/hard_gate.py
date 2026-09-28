"""The hard gate and the information gate of one candidate (Slice 4 step 4).

Ref: `docs/gate/SLICE_4_PLAN.md` §2 (evaluation order, steps 1–3), §3.2,
G4-4 (decided in the review of cc3a7fe); G4-11's text for the information
gate; Developer Spec §12.1 (hard gate: REQUIRED criteria only), §13 and
§13.1 (blocking and actionable unknowns); red-team C03, G01; policy 0.2.0
`hard_gate` (`seed_master_data_v0.2.3.sql:169–172`).

## Blocking (G4-4, as decided)

`blocking` is true when the result, by itself, keeps the candidate from
ELIGIBLE:
- a REQUIRED criterion that is FAIL (§12.1: it rejects the candidate);
- a REQUIRED criterion that is UNKNOWN, always (C03, mandatory test 3);
- a PREFERRED or FLEXIBLE criterion that is UNKNOWN with
  `blocking_if_unknown = true`: the column ADDS blocking, never removes it.

A PREFERRED or FLEXIBLE FAIL never blocks: it is for the soft score.

## The two gates

- **Hard gate** (§12.1, REQUIRED criteria only):
  - FAIL if any REQUIRED criterion is FAIL;
  - otherwise UNKNOWN if any REQUIRED criterion is UNKNOWN;
  - otherwise PASS.
  A soft score is never computed unless it is PASS (§3.2, step 6).
- **Information gate** (G4-11's text):
  - UNKNOWN if any blocking UNKNOWN exists;
  - otherwise PASS;
  - never FAIL: a confirmed failure is the hard gate's.

**Actionable unknowns** (§13.1: information acquisition first, "when the
missing information alone can produce an exact match"): the blocking
unknowns of a candidate whose hard gate is NOT FAIL. On a rejected
candidate, resolving an unknown cannot make it eligible.

**Not here:** eligibility and its precedence (G4-11, step 5), freshness and
permission (step 5), the soft score (step 6). Nothing is written.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from turab.matching import snapshots
from turab.matching.criteria import CriteriaPlan
from turab.matching.registry import REGISTRY, RuleRegistry

#: The frozen seed's reason codes of category MATCH (lines 135–142, 157): the
#: only codes a criterion result may carry (acceptance condition 4).
MATCH_REASON_CODES = frozenset({
    "LOCATION_MISMATCH", "PROPERTY_TYPE_MISMATCH", "BUDGET_EXCEEDED", "PRICE_NOT_KNOWN",
    "PRICE_NEGOTIATION_UNCONFIRMED", "DOCUMENT_NOT_KNOWN", "DOCUMENT_MISMATCH",
    "AREA_BELOW_PREFERENCE", "ACTIONABLE_UNKNOWN"})
COMPATIBILITY = ("PASS", "FAIL", "UNKNOWN")
RESULT_KEYS = frozenset({"compatibility", "property_value", "delta", "evidence_level",
                         "evidence_claim_id", "reason_code", "explanation"})


class RuleOutputInvalid(RuntimeError):
    """A rule returned something `match_criterion_results` cannot hold."""


@dataclass(frozen=True, slots=True)
class CriterionResult:
    """One row of `match_criterion_results`, before it has a `match_id`."""
    request_criterion_id: str | None
    criterion_code: str
    ordinal: int
    importance: str
    request_value: Mapping[str, Any]
    property_value: Any
    compatibility: str
    blocking: bool
    delta: Any
    evidence_level: str | None
    evidence_claim_id: str | None
    reason_code: str | None
    rule_id: str
    rule_version: str
    explanation: Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class HardGate:
    results: tuple[CriterionResult, ...]
    deferred: tuple[Mapping[str, Any], ...]
    hard_gate_status: str
    information_gate_status: str
    required_failures: tuple[tuple[str, int], ...]
    blocking_unknowns: tuple[tuple[str, int], ...]
    actionable_unknowns: tuple[tuple[str, int], ...]


def blocking(importance: str, compatibility: str, blocking_if_unknown: bool) -> bool:
    """G4-4, as decided."""
    if importance == "REQUIRED":
        return compatibility in ("FAIL", "UNKNOWN")
    return compatibility == "UNKNOWN" and blocking_if_unknown


def _checked(rule_key: str, output: Any) -> Mapping[str, Any]:
    if not isinstance(output, Mapping) or set(output) != RESULT_KEYS:
        raise RuleOutputInvalid(f"{rule_key} returned keys other than {sorted(RESULT_KEYS)}")
    if output["compatibility"] not in COMPATIBILITY:
        raise RuleOutputInvalid(f"{rule_key}: compatibility must be PASS, FAIL or UNKNOWN")
    if output["reason_code"] is not None and output["reason_code"] not in MATCH_REASON_CODES:
        raise RuleOutputInvalid(f"{rule_key}: reason code not in the frozen seed")
    if not isinstance(output["explanation"], Mapping):
        raise RuleOutputInvalid(f"{rule_key}: the explanation must be an object")
    return output


def evaluate(plan: CriteriaPlan, request: Mapping[str, Any], prop: Mapping[str, Any],
             offer: Mapping[str, Any] | None,
             registry: RuleRegistry = REGISTRY) -> HardGate:
    """Every criterion of `plan` against one candidate, then both gates.

    `request`, `prop` and `offer` are the snapshots; they are converted to
    the stored form here (`snapshots.stored_form`). `plan` is
    `criteria.criteria_of`'s output for the same request."""
    request, prop, offer = (snapshots.stored_form(x) for x in (request, prop, offer))
    results = []
    for criterion in plan.criteria:
        rule = registry.resolve(criterion["rule_id"], criterion["rule_version"])
        out = _checked(rule.key, rule.evaluate(criterion, request, prop, offer))
        results.append(CriterionResult(
            request_criterion_id=criterion["request_criterion_id"],
            criterion_code=criterion["code"], ordinal=criterion["ordinal"],
            importance=criterion["importance"],
            request_value={"operator": criterion["operator"], "value": criterion["value"],
                           "unit": criterion["unit"], "source": criterion["source"]},
            property_value=out["property_value"], compatibility=out["compatibility"],
            blocking=blocking(criterion["importance"], out["compatibility"],
                              criterion["blocking_if_unknown"]),
            delta=out["delta"], evidence_level=out["evidence_level"],
            evidence_claim_id=out["evidence_claim_id"], reason_code=out["reason_code"],
            rule_id=rule.rule_id, rule_version=rule.rule_version,
            explanation=out["explanation"]))
    return classify(tuple(results), plan.deferred)


def classify(results: tuple[CriterionResult, ...],
             deferred: tuple[Mapping[str, Any], ...] = ()) -> HardGate:
    """The gates, from the results alone. STOP GATE D's reconstruction (step
    8) re-derives them from stored rows with this same reading."""
    required = [r for r in results if r.importance == "REQUIRED"]
    failures = tuple((r.criterion_code, r.ordinal) for r in required
                     if r.compatibility == "FAIL")
    if failures:
        hard = "FAIL"
    elif any(r.compatibility == "UNKNOWN" for r in required):
        hard = "UNKNOWN"
    else:
        hard = "PASS"
    unknowns = tuple((r.criterion_code, r.ordinal) for r in results
                     if r.blocking and r.compatibility == "UNKNOWN")
    return HardGate(results=results, deferred=deferred, hard_gate_status=hard,
                    information_gate_status="UNKNOWN" if unknowns else "PASS",
                    required_failures=failures, blocking_unknowns=unknowns,
                    actionable_unknowns=() if hard == "FAIL" else unknowns)
