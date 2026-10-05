"""What a run records beside the gates: the explanation, the next action, the
diagnostic's counts and its blocker summary (Slice 4 step 7, G4-15).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-15, decided in the review of b3246b0
(D1–D6, with the reviewer's constraints); §3.4 (the explanation is stored on
the match, keyed by criterion); §3.5 and R9.3 (the seller expectation is
never stated or inferable); G4-8 (exclusions reported); G4-10's display rule
(PERMISSION_MISSING is worded from its basis, review of a5ea6f5); Developer
Spec §13, §13.1.

## As decided

- **D2, near match.** A REJECTED candidate with exactly ONE REQUIRED FAIL,
  and every other REQUIRED criterion PASS (no REQUIRED UNKNOWN). Counted
  only.
- **D3, the counts.** Each candidate counts at most once in each: ELIGIBLE
  → `ready_opportunity_count`; NEED_MORE_INFORMATION →
  `actionable_unknown_count`; D2 → `near_match_count`.
- **D3b, `blocker_summary`.** Keyed by the reason code, or `GATE:basis` when
  the code is null. A candidate counts ONCE per distinct key, however many
  of its reasons share it. The candidate set's exclusions are listed
  separately, each with its reason and ids. PERMISSION_MISSING carries the
  wording of its basis, never its seeded label.
- **D4, the explanation.** Each criterion's explanation keyed
  `CODE#ordinal`, the deferred criteria, the soft-score terms, every
  reason, and the version of every pinned function used. It carries neither
  `seller_expectation_dzd` nor anything taken from a claim: no claim id, no
  claimed value. The evidence of a criterion stays in its row
  (`evidence_level`, `evidence_claim_id`), as the contract's
  `CriterionResult` defines it.
- **D5, `next_action`.** The pinned `action.next@1` (`gates.py`), whose
  docstring states the order and the tie-break.

**Pure.** Nothing here reads the database or writes.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

from turab.matching import snapshots
from turab.matching.candidates import Excluded
from turab.matching.criteria import CriteriaPlan
from turab.matching.eligibility import Eligibility
from turab.matching.hard_gate import HardGate
from turab.matching.registry import REGISTRY
from turab.matching.soft import SoftScore

NEXT_ACTION = ("action.next", "1")
#: Format 2 (G4-19, decided (a) in the review of c657bd9) adds
#: `engine.registry_digest`, the digest that entered the match's input hash.
EXPLANATION_FORMAT = "turab.match-explanation/2"
SUMMARY_FORMAT = "turab.blocker-summary/1"

#: How a permission reason is worded, from its BASIS (review of a5ea6f5: the
#: seeded label of PERMISSION_MISSING, "Permission scope insufficient", is
#: not an exact reading of these facts). One entry per basis that
#: `permission.gate@1` emits; a basis without one fails the run.
PERMISSION_WORDING = {
    "NO_CURRENT_BINDING": "The offer's party has no consent binding for a matching purpose "
                          "on this offer or its property",
    "NOT_STARTED": "No consent binding of the offer's party for a matching purpose is in "
                   "force yet: none is current, and at least one has not started",
    "ONLY_REVOKED_BINDINGS": "Every consent binding of the offer's party for a matching "
                             "purpose is revoked",
}


def criterion_key(code: str, ordinal: int) -> str:
    return f"{code}#{ordinal}"


def _worded(reason: Mapping[str, Any]) -> dict:
    out = dict(reason)
    if reason["gate"] == "PERMISSION":
        out["wording"] = PERMISSION_WORDING[reason["basis"]]
    return out


def next_action(hard: HardGate, verdict: Eligibility,
                subjects: Mapping[str, Any]) -> dict | None:
    """D5, by the pinned `action.next@1`. `subjects` maps REQUEST, PROPERTY
    and PROPERTY_OFFER to their ids."""
    actionable = set(hard.actionable_unknowns)
    information = [{"criterion": r.criterion_code, "ordinal": r.ordinal,
                    "request_criterion_id": r.request_criterion_id,
                    "importance": r.importance, "reason_code": r.reason_code,
                    "basis": r.explanation.get("basis")}
                   for r in hard.results if (r.criterion_code, r.ordinal) in actionable]
    reasons = list(verdict.reasons)
    return REGISTRY.resolve(*NEXT_ACTION).evaluate(
        verdict.eligibility, snapshots.stored_form(information),
        [r for r in reasons if r["gate"] == "FRESHNESS"],
        [r for r in reasons if r["gate"] == "PERMISSION"],
        snapshots.stored_form(dict(subjects)))


def explanation(plan: CriteriaPlan, hard: HardGate, verdict: Eligibility, score: SoftScore,
                freshness: Mapping[str, Any], permission: Mapping[str, Any],
                registry_digest: str) -> dict:
    """D4. Every version named here is one this run executed, and
    `registry_digest` is the digest that entered the input hash: the run
    computes it ONCE and passes the same value to both (G4-19)."""
    criteria = {}
    for r in hard.results:
        criteria[criterion_key(r.criterion_code, r.ordinal)] = {
            "importance": r.importance, "compatibility": r.compatibility,
            "blocking": r.blocking, "reason_code": r.reason_code,
            "source": r.request_value["source"],
            "request_criterion_id": r.request_criterion_id,
            "rule": f"{r.rule_id}@{r.rule_version}",
            "rule_explanation": dict(r.explanation)}
    return snapshots.stored_form({
        "format": EXPLANATION_FORMAT,
        "eligibility": verdict.eligibility,
        "criteria": criteria,
        "deferred": [{"criterion": d["code"], "source": d["source"],
                      "request_criterion_id": d["request_criterion_id"],
                      "deferred_to": d["deferred_to"]} for d in plan.deferred],
        "soft_score": {"basis": score.basis, "terms": list(score.terms)},
        "reasons": [_worded(r) for r in verdict.reasons],
        "engine": {"freshness_state": freshness["derived_by"],
                   "permission_binding_state": permission["derived_by"],
                   **dict(verdict.engine),
                   "soft_score": score.engine,
                   "registry_digest": registry_digest,
                   "next_action": "@".join(NEXT_ACTION)},
    })


def is_near_match(hard: HardGate, verdict: Eligibility) -> bool:
    """D2: REJECTED, exactly one REQUIRED FAIL, every other REQUIRED PASS."""
    required = [r.compatibility for r in hard.results if r.importance == "REQUIRED"]
    return (verdict.eligibility == "REJECTED" and required.count("FAIL") == 1
            and required.count("UNKNOWN") == 0)


def counts(evaluated: Iterable[tuple[HardGate, Eligibility]]) -> dict[str, int]:
    """D3: each candidate counted at most once in each count."""
    out = {"ready_opportunity_count": 0, "actionable_unknown_count": 0,
           "near_match_count": 0}
    for hard, verdict in evaluated:
        if verdict.eligibility == "ELIGIBLE":
            out["ready_opportunity_count"] += 1
        if verdict.eligibility == "NEED_MORE_INFORMATION":
            out["actionable_unknown_count"] += 1
        if is_near_match(hard, verdict):
            out["near_match_count"] += 1
    return out


def reason_key(reason: Mapping[str, Any]) -> str:
    """D3b: the reason code, or `GATE:basis` when the code is null."""
    code = reason["reason_code"]
    return code if code is not None else f"{reason['gate']}:{reason['basis']}"


def blocker_summary(verdicts: Iterable[Eligibility],
                    excluded: Iterable[Excluded]) -> dict:
    """D3b. `by_reason[key]` counts the candidates with at least one reason
    under `key`, each ONCE; inside it, `bases` and `criteria` count the
    candidates per basis and per criterion, each once too."""
    by_reason: dict[str, dict] = {}
    evaluated = 0
    for verdict in verdicts:
        evaluated += 1
        seen: set[tuple] = set()
        for reason in verdict.reasons:
            key = reason_key(reason)
            entry = by_reason.setdefault(key, {"candidates": 0, "gates": [], "bases": {},
                                               "criteria": {}})
            if (key,) not in seen:
                seen.add((key,))
                entry["candidates"] += 1
            if reason["gate"] not in entry["gates"]:
                entry["gates"].append(reason["gate"])
            if (key, "basis", reason["basis"]) not in seen:
                seen.add((key, "basis", reason["basis"]))
                entry["bases"][reason["basis"]] = entry["bases"].get(reason["basis"], 0) + 1
            if "criterion" in reason:
                criterion = criterion_key(reason["criterion"], reason["ordinal"])
                if (key, "criterion", criterion) not in seen:
                    seen.add((key, "criterion", criterion))
                    entry["criteria"][criterion] = entry["criteria"].get(criterion, 0) + 1
            if reason["gate"] == "PERMISSION":
                entry.setdefault("wording", {})[reason["basis"]] = (
                    PERMISSION_WORDING[reason["basis"]])
    exclusions = [{"property_id": e.property_id, "reason": e.reason.value,
                   "detail": dict(e.detail)} for e in excluded]
    excluded_counts: dict[str, int] = {}
    for e in exclusions:
        excluded_counts[e["reason"]] = excluded_counts.get(e["reason"], 0) + 1
    return snapshots.stored_form({
        "format": SUMMARY_FORMAT,
        "candidates_evaluated": evaluated,
        "by_reason": {key: by_reason[key] for key in sorted(by_reason)},
        "excluded": exclusions,
        "excluded_counts": excluded_counts,
    })
