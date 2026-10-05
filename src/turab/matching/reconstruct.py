"""STOP GATE D: a stored match, reconstructed and replayed from its rows alone
(Slice 4 step 8).

Ref: `docs/gate/SLICE_4_PLAN.md` §6.2 ("a human reviewer must be able to
read a candidate and reconstruct every eligibility decision without an
LLM"), G4-2 (every version a stored match cites stays implemented), G4-13,
G4-15 D4; red-team G04 (immutable replay), G05 (rule and policy lineage).

## Two proofs, both from stored rows only

**Reconstruction** (`reconstruct`) reads the match row and its criterion
rows, nothing else, and re-derives every decision the run recorded:
- each criterion's `blocking` (G4-4), from its importance, its
  compatibility and the `blocking_if_unknown` the stored request snapshot
  holds;
- the hard gate and the information gate (`hard_gate.classify`);
- the freshness gate, the permission gate and the eligibility precedence,
  each by the VERSION the match's `explanation.engine` names;
- every reason the precedence keeps;
- the soft score, by its stored version, from the criterion rows, the
  stored request snapshot's targets and the stored commercial snapshot;
- the next action, by its stored version;
- the three freshness states, from the stored freshness snapshot.

Every one of those is compared with what was stored. Any disagreement is
returned.

**Replay** (`replay`) re-runs each criterion's rule, by the `rule_id` and
`rule_version` its row names, on the three stored snapshots, and compares
the result with the row. It then recomputes the input hash from the five
stored snapshots.

**A limit, stated (raised for the reviewer in the step-8 note).** The input
hash covers `REGISTRY.digest()` (G4-13), and the digest at evaluation time
is not stored. `replay` recomputes it with the CURRENT registry. So the hash
replays while the registry is the one the match was evaluated under; once a
new version is registered, an older match's hash can no longer be
recomputed from the database alone. The criterion results still replay:
each row names its own version.

**Pure.** Nothing here reads the database or writes. The caller passes the
rows.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping, Sequence

from turab.matching import canonical, eligibility, explain, snapshots
from turab.matching.hard_gate import CriterionResult, blocking, classify
from turab.matching.registry import REGISTRY

#: The explanation format this module reads (step 7, D4).
EXPLANATION_FORMAT = "turab.match-explanation/1"

#: The stored fields reconstruction re-derives and compares.
GATE_FIELDS = ("eligibility", "hard_gate_status", "information_gate_status",
               "freshness_gate_status", "permission_gate_status", "request_freshness",
               "property_freshness", "offer_freshness")


def _key(code: str, ordinal: int) -> str:
    return f"{code}#{ordinal}"


def _pinned(name: str, engine: Mapping[str, str]):
    rule_id, version = engine[name].split("@")
    return REGISTRY.resolve(rule_id, version).evaluate


def _results(match: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]):
    """The criterion rows as `CriterionResult`s, each with its rule's own
    explanation from the stored explanation, and `blocking` RE-DERIVED."""
    request = match["request_snapshot"]
    flagged = {str(c["request_criterion_id"]): bool(c["blocking_if_unknown"])
               for c in request.get("criteria") or []}
    stored = match["explanation"]["criteria"]
    order = list(stored)  # the evaluation order, as the run recorded it
    rows = sorted(rows, key=lambda r: order.index(_key(r["criterion_code"], r["ordinal"])))
    out = []
    for r in rows:
        rcid = r["request_criterion_id"]
        out.append(CriterionResult(
            request_criterion_id=rcid, criterion_code=r["criterion_code"],
            ordinal=r["ordinal"], importance=r["importance"],
            request_value=r["request_value"], property_value=r["property_value"],
            compatibility=r["compatibility"],
            blocking=blocking(r["importance"], r["compatibility"],
                              flagged.get(str(rcid), False) if rcid is not None else False),
            delta=r["delta"], evidence_level=r["evidence_level"],
            evidence_claim_id=r["evidence_claim_id"], reason_code=r["reason_code"],
            rule_id=r["rule_id"], rule_version=r["rule_version"],
            explanation=stored[_key(r["criterion_code"], r["ordinal"])]["rule_explanation"]))
    return tuple(out)


def _targets(request: Mapping[str, Any]) -> list[dict]:
    """The soft score's targets, as the run's plan deferred them: the
    request's `budget_target_dzd` column first (source COLUMN, no
    importance), then each BUDGET_TARGET row in the snapshot's order."""
    targets = []
    if request.get("budget_target_dzd") is not None:
        targets.append({"source": "COLUMN", "request_criterion_id": None, "importance": None,
                        "value": request["budget_target_dzd"]})
    for c in request.get("criteria") or []:
        if c["criterion_code"] == "BUDGET_TARGET":
            targets.append({"source": "ROW", "request_criterion_id": c["request_criterion_id"],
                            "importance": c["importance"], "value": c["value"]})
    return targets


def _without_wording(reasons: Sequence[Mapping[str, Any]]) -> list[dict]:
    return [{k: v for k, v in r.items() if k != "wording"} for r in reasons]


def reconstruct(match: Mapping[str, Any],
                rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Every decision of one stored match, re-derived from its rows. Returns
    the disagreements; an empty list means every decision was reconstructed.

    `match` is the `match_candidates` row and `rows` its
    `match_criterion_results`, both in stored form (jsonb read exactly)."""
    match, rows = snapshots.stored_form(match), snapshots.stored_form(list(rows))
    problems: list[str] = []
    explanation = match["explanation"]
    if explanation.get("format") != EXPLANATION_FORMAT:
        return [f"explanation format {explanation.get('format')!r} is not "
                f"{EXPLANATION_FORMAT}"]
    engine = explanation["engine"]
    results = _results(match, rows)
    for r, row in zip(results, sorted(rows, key=lambda x: list(explanation["criteria"]).index(
            _key(x["criterion_code"], x["ordinal"])))):
        if r.blocking != row["blocking"]:
            problems.append(f"{_key(r.criterion_code, r.ordinal)}: blocking stored "
                            f"{row['blocking']}, derived {r.blocking}")
    hard = classify(results)
    fresh = _pinned("freshness_gate", engine)(match["freshness_snapshot"])
    perm = _pinned("permission_gate", engine)(match["permission_snapshot"])
    verdict = _pinned("precedence", engine)(eligibility.hard_summary(hard), fresh, perm)
    derived = {
        "eligibility": verdict["eligibility"],
        "hard_gate_status": hard.hard_gate_status,
        "information_gate_status": hard.information_gate_status,
        "freshness_gate_status": fresh["status"],
        "permission_gate_status": perm["status"],
        "request_freshness": match["freshness_snapshot"]["request"]["state"],
        "property_freshness": match["freshness_snapshot"]["property"]["state"],
        "offer_freshness": match["freshness_snapshot"]["offer"]["state"],
    }
    for field in GATE_FIELDS:
        if derived[field] != match[field]:
            problems.append(f"{field}: stored {match[field]}, derived {derived[field]}")
    if _without_wording(explanation["reasons"]) != snapshots.stored_form(verdict["reasons"]):
        problems.append("reasons: the stored reasons are not the precedence's")

    score = _pinned("soft_score", engine)(
        hard.hard_gate_status,
        [{"criterion_code": r.criterion_code, "ordinal": r.ordinal, "importance": r.importance,
          "compatibility": r.compatibility, "rule_id": r.rule_id} for r in results],
        _targets(match["request_snapshot"]), match["commercial_context_snapshot"])
    stored_score = match["soft_score"]
    if (score["soft_score"] is None) != (stored_score is None) or (
            stored_score is not None and Decimal(stored_score) != score["soft_score"]):
        problems.append(f"soft_score: stored {stored_score}, derived {score['soft_score']}")

    verdict_view = eligibility.Eligibility(
        derived["eligibility"], derived["hard_gate_status"], derived["information_gate_status"],
        derived["freshness_gate_status"], derived["permission_gate_status"],
        derived["request_freshness"], derived["property_freshness"],
        derived["offer_freshness"], tuple(verdict["reasons"]), dict(engine))
    action_id, action_version = engine["next_action"].split("@")
    if (action_id, action_version) != explain.NEXT_ACTION:
        problems.append(f"next_action: version {engine['next_action']} is not the one "
                        "`explain.next_action` runs")
    action = explain.next_action(hard, verdict_view, {
        "REQUEST": match["request_id"], "PROPERTY": match["property_id"],
        "PROPERTY_OFFER": match["evaluated_offer_id"]})
    if snapshots.stored_form(action) != match["next_action"]:
        problems.append("next_action: stored differs from derived")
    return problems


def replay(match: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Each criterion re-evaluated by the rule version its row names, on the
    stored snapshots; then the input hash, from the stored snapshots and the
    CURRENT registry digest (see the module docstring). Returns the
    disagreements."""
    match, rows = snapshots.stored_form(match), snapshots.stored_form(list(rows))
    problems: list[str] = []
    stored = match["explanation"]["criteria"]
    request, prop = match["request_snapshot"], match["property_snapshot"]
    offer = match["commercial_context_snapshot"]
    for row in rows:
        key = _key(row["criterion_code"], row["ordinal"])
        criterion = {"code": row["criterion_code"], "importance": row["importance"],
                     "operator": row["request_value"]["operator"],
                     "value": row["request_value"]["value"],
                     "unit": row["request_value"]["unit"],
                     "source": row["request_value"]["source"],
                     "request_criterion_id": row["request_criterion_id"]}
        out = snapshots.stored_form(REGISTRY.resolve(row["rule_id"], row["rule_version"])
                                    .evaluate(criterion, request, prop, offer))
        for field in ("compatibility", "property_value", "delta", "evidence_level",
                      "evidence_claim_id", "reason_code"):
            if out[field] != row[field]:
                problems.append(f"{key}.{field}: stored {row[field]!r}, replayed {out[field]!r}")
        if out["explanation"] != stored[key]["rule_explanation"]:
            problems.append(f"{key}.explanation: stored differs from replayed")
    recomputed = canonical.input_hash(
        matching_policy_id=match["matching_policy_id"],
        matching_policy_version=match["matching_policy_version"],
        rule_registry_digest=REGISTRY.digest(),
        evaluated_offer_id=match["evaluated_offer_id"],
        request_snapshot=request, property_snapshot=prop, commercial_context_snapshot=offer,
        permission_snapshot=match["permission_snapshot"],
        freshness_snapshot=match["freshness_snapshot"])
    if recomputed != match["input_hash"]:
        problems.append("input_hash: not recomputed from the stored snapshots")
    return problems
