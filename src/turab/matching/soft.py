"""The soft score of one candidate (Slice 4 step 6, G4-12).

Ref: `docs/gate/SLICE_4_PLAN.md` G4-12, decided in the review of a5ea6f5;
G4-7 (a soft criterion without a deterministic rule carries no weight);
G4-3's table (BUDGET_TARGET is soft only); Developer Spec §12.1 ("no soft
score or semantic similarity overrides a hard FAIL"), §12.2; plan §3.2.

The formula is the pinned `score.soft@2` (`gates.py`). Its docstring states
the decisions in full. This module gathers the formula's inputs and records
the version it ran.

**The request's `budget_target_dzd` column** was refused in the first round
(0cf6a7a), its weight being undecided. The review of 0cf6a7a decided (a):
it weighs 2, as PREFERRED, as its own term (source COLUMN). That decision is
`score.soft@2`. Version 1 stays registered and pinned (G4-2): it never
received a column. A BUDGET_TARGET ROW carries its own importance, and is a
separate term.

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

SOFT_SCORE = ("score.soft", "2")


@dataclass(frozen=True, slots=True)
class SoftScore:
    soft_score: Decimal | None
    basis: str
    #: Each term, for `explanation` (G4-12): kind, criterion or source,
    #: weight (and, for a target, its basis), contribution as an exact
    #: fraction "n/d". The column target and a target row are separate.
    terms: tuple[Mapping[str, Any], ...]
    engine: str


def soft_score(plan: CriteriaPlan, hard: HardGate,
               offer: Mapping[str, Any] | None) -> SoftScore:
    """G4-12 for one candidate. `plan` is the request's `criteria_of`, `hard`
    the candidate's `hard_gate.evaluate`, `offer` its commercial snapshot."""
    targets = [d for d in plan.deferred if d["code"] == "BUDGET_TARGET"]
    criteria = [{"criterion_code": r.criterion_code, "ordinal": r.ordinal,
                 "importance": r.importance, "compatibility": r.compatibility,
                 "rule_id": r.rule_id} for r in hard.results]
    terms = [{"source": t["source"], "request_criterion_id": t["request_criterion_id"],
              "importance": t["importance"], "value": t["value"]} for t in targets]
    out = REGISTRY.resolve(*SOFT_SCORE).evaluate(
        hard.hard_gate_status, criteria, terms, snapshots.stored_form(offer))
    return SoftScore(out["soft_score"], out["basis"], tuple(out["terms"]),
                     "@".join(SOFT_SCORE))
