"""The soft score of one candidate (Slice 4 step 6, G4-12).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-12, decided in the review of a5ea6f5;
G4-7 (a soft criterion without a deterministic rule carries no weight);
G4-3's table (BUDGET_TARGET is soft only); Developer Spec §12.1 ("no soft
score or semantic similarity overrides a hard FAIL"), §12.2; plan §3.2.

The formula is the pinned `score.soft@1` (`gates.py`). Its docstring states
the decision in full. This module gathers the formula's inputs and records
the version it ran.

**One case is not decided, and is refused.** The request's own
`budget_target_dzd` COLUMN has no importance of its own: `budget_importance`
is the maximum's. G4-12 gives weights by importance (PREFERRED = 2,
FLEXIBLE = 1), so the column's weight is undecided. Acceptance condition 1
applies: anything undecided refuses with a typed error naming the rule
(`SoftScoreUndecided`, "G4-12").
- The refusal holds whatever the hard gate says, so it is per request, not
  per candidate.
- A BUDGET_TARGET ROW carries its own importance (PREFERRED or FLEXIBLE; a
  REQUIRED one is refused by `criteria`, G4-7), and is scored.

**Pure.** Nothing here reads the database or writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Mapping

from turab.matching import snapshots
from turab.matching.criteria import CriteriaPlan
from turab.matching.hard_gate import HardGate
from turab.matching.registry import REGISTRY

SOFT_SCORE = ("score.soft", "1")


class SoftScoreUndecided(ValueError):
    """G4-12 does not decide the weight of the request's `budget_target_dzd`
    column."""

    def __init__(self) -> None:
        super().__init__("G4-12: the weight of the request's budget_target_dzd column is not "
                         "decided (it has no importance of its own)")
        self.decision = "G4-12"


@dataclass(frozen=True, slots=True)
class SoftScore:
    soft_score: Decimal | None
    basis: str
    #: Each term, for `explanation` (G4-12): kind, criterion or source,
    #: weight, contribution as an exact fraction "n/d".
    terms: tuple[Mapping[str, Any], ...]
    engine: str


def soft_score(plan: CriteriaPlan, hard: HardGate,
               offer: Mapping[str, Any] | None) -> SoftScore:
    """G4-12 for one candidate. `plan` is the request's `criteria_of`, `hard`
    the candidate's `hard_gate.evaluate`, `offer` its commercial snapshot."""
    targets = [d for d in plan.deferred if d["code"] == "BUDGET_TARGET"]
    if any(t["source"] == "COLUMN" for t in targets):
        raise SoftScoreUndecided()
    criteria = [{"criterion_code": r.criterion_code, "ordinal": r.ordinal,
                 "importance": r.importance, "compatibility": r.compatibility,
                 "rule_id": r.rule_id} for r in hard.results]
    terms = [{"source": t["source"], "request_criterion_id": t["request_criterion_id"],
              "importance": t["importance"], "value": t["value"]} for t in targets]
    out = REGISTRY.resolve(*SOFT_SCORE).evaluate(
        hard.hard_gate_status, criteria, terms, snapshots.stored_form(offer))
    return SoftScore(out["soft_score"], out["basis"], tuple(out["terms"]),
                     "@".join(SOFT_SCORE))
