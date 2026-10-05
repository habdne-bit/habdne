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
- **the three freshness states**, re-derived from their raw fields: the
  confirmation time each stored snapshot holds, the threshold the freshness
  snapshot holds, and the match's `evaluated_at`, by the version
  `freshness_snapshot.derived_by` names. State, basis and confirmation time
  are compared (review of c657bd9, R-S4-8-01);
- **each binding's state**, re-derived from the grant and binding fields,
  the offer's party and `evaluated_at`, by the version
  `permission_snapshot.derived_by` names, and compared;
- the freshness gate, the permission gate and the eligibility precedence,
  each by the VERSION `explanation.engine` names, run on the RE-DERIVED
  states, never on the stored ones;
- every reason the precedence keeps;
- the soft score, by its stored version, from the criterion rows, the
  stored request snapshot's targets and the stored commercial snapshot;
- the next action, by its stored version.

Every one of those is compared with what was stored. Any disagreement is
returned.

**Replay** (`replay`) re-runs each criterion's rule, by the `rule_id` and
`rule_version` its row names, on the three stored snapshots, and compares
the result with the row. It then recomputes the input hash from the five
stored snapshots and **the registry digest the match was evaluated under**
(G4-19, decided (a) in the review of c657bd9):
- format 2: the digest the match records (`explanation.engine.registry_digest`),
  which must also be one the recorded history knows (`registry_history`);
- format 1: the one digest `registry_history.FORMAT_DIGESTS` attributes to
  every format-1 row, with its evidence;
- otherwise: **UNPROVEN**, reported as such. The current digest is never
  substituted.

Replay alone cannot see a state derived wrongly and then hashed with its
wrong inputs: the hash covers what was written. Reconstruction re-derives
those states, and so the two proofs together cover them.

**Pure.** Nothing here reads the database or writes. The caller passes the
rows.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any, Mapping, Sequence

from turab.matching import canonical, eligibility, explain, registry_history, snapshots
from turab.matching.hard_gate import CriterionResult, blocking, classify
from turab.matching.registry import REGISTRY

#: The explanation formats this module reads: 1 (step 7, D4), and 2, which
#: records the registry digest (G4-19).
EXPLANATION_FORMATS = ("turab.match-explanation/1", "turab.match-explanation/2")
EXPLANATION_FORMAT = EXPLANATION_FORMATS[-1]

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


def _instant(value: Any) -> datetime:
    """A stored instant (`evaluated_at`, as jsonb gives it) as an aware
    datetime."""
    instant = value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if instant.tzinfo is None:
        raise ValueError("a stored instant without a time zone names no instant")
    return instant


#: subject -> (where its confirmation time is stored, its threshold key).
_FRESHNESS_SOURCES = (("request", "request_snapshot", "last_confirmed_at", "request"),
                      ("property", "property_snapshot", "availability_last_confirmed_at",
                       "property"),
                      ("offer", "commercial_context_snapshot",
                       "commercial_terms_last_confirmed_at", "offer_terms"))


def _rederived_freshness(match: Mapping[str, Any], as_of: datetime):
    """Each subject's freshness state, re-derived from its raw fields by the
    version the stored snapshot names; and the disagreements (R-S4-8-01)."""
    stored = match["freshness_snapshot"]
    state = REGISTRY.resolve(*stored["derived_by"].split("@")).evaluate
    derived = dict(stored)
    problems = []
    for subject, source, field, key in _FRESHNESS_SOURCES:
        if subject == "offer" and match["evaluated_offer_id"] is None:
            again = {"state": "NOT_APPLICABLE", "basis": "NO_EVALUATED_OFFER",
                     "confirmed_at": None}
        else:
            again = snapshots.stored_form(state(match[source][field],
                                                int(stored["threshold_days"][key]), as_of))
        for part in ("state", "basis", "confirmed_at"):
            if again[part] != stored[subject][part]:
                problems.append(f"freshness.{subject}.{part}: stored "
                                f"{stored[subject][part]!r}, derived {again[part]!r}")
        derived[subject] = again
    return derived, problems


def _rederived_permission(match: Mapping[str, Any], as_of: datetime):
    """Each binding's state, re-derived from the grant and binding fields by
    the version the stored snapshot names; and the disagreements."""
    stored = match["permission_snapshot"]
    state = REGISTRY.resolve(*stored["derived_by"].split("@")).evaluate
    bindings, problems = [], []
    for b in stored["bindings"]:
        again = state(b, stored["offer_party_id"], as_of)
        if again != b["state"]:
            problems.append(f"permission.binding {b['consent_binding_id']}: stored "
                            f"{b['state']}, derived {again}")
        bindings.append({**b, "state": again})
    return {**stored, "bindings": bindings}, problems


def reconstruct(match: Mapping[str, Any],
                rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Every decision of one stored match, re-derived from its rows. Returns
    the disagreements; an empty list means every decision was reconstructed.

    `match` is the `match_candidates` row and `rows` its
    `match_criterion_results`, both in stored form (jsonb read exactly)."""
    match, rows = snapshots.stored_form(match), snapshots.stored_form(list(rows))
    problems: list[str] = []
    explanation = match["explanation"]
    if explanation.get("format") not in EXPLANATION_FORMATS:
        return [f"explanation format {explanation.get('format')!r} is not one of "
                f"{EXPLANATION_FORMATS}"]
    engine = explanation["engine"]
    as_of = _instant(match["evaluated_at"])
    freshness, fresh_problems = _rederived_freshness(match, as_of)
    permission, binding_problems = _rederived_permission(match, as_of)
    problems += fresh_problems + binding_problems
    results = _results(match, rows)
    for r, row in zip(results, sorted(rows, key=lambda x: list(explanation["criteria"]).index(
            _key(x["criterion_code"], x["ordinal"])))):
        if r.blocking != row["blocking"]:
            problems.append(f"{_key(r.criterion_code, r.ordinal)}: blocking stored "
                            f"{row['blocking']}, derived {r.blocking}")
    hard = classify(results)
    fresh = _pinned("freshness_gate", engine)(freshness)
    perm = _pinned("permission_gate", engine)(permission)
    verdict = _pinned("precedence", engine)(eligibility.hard_summary(hard), fresh, perm)
    derived = {
        "eligibility": verdict["eligibility"],
        "hard_gate_status": hard.hard_gate_status,
        "information_gate_status": hard.information_gate_status,
        "freshness_gate_status": fresh["status"],
        "permission_gate_status": perm["status"],
        "request_freshness": freshness["request"]["state"],
        "property_freshness": freshness["property"]["state"],
        "offer_freshness": freshness["offer"]["state"],
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


def evaluated_digest(explanation: Mapping[str, Any]) -> tuple[str | None, str | None]:
    """(the registry digest the match was evaluated under, or None; why it
    cannot be attributed, or None). Never the current digest by default
    (G4-19, the review's condition)."""
    fmt = explanation.get("format")
    if fmt == "turab.match-explanation/2":
        digest = (explanation.get("engine") or {}).get("registry_digest")
        if digest is None:
            return None, "a format-2 match records no registry digest"
        if not registry_history.known(digest):
            return None, f"the recorded digest {digest} is in no recorded registry"
        return digest, None
    if fmt in registry_history.FORMAT_DIGESTS:
        return registry_history.FORMAT_DIGESTS[fmt], None
    return None, f"no registry digest is attributed to explanation format {fmt!r}"


def replay(match: Mapping[str, Any], rows: Sequence[Mapping[str, Any]]) -> list[str]:
    """Each criterion re-evaluated by the rule version its row names, on the
    stored snapshots; then the input hash, from the stored snapshots and the
    digest the match was evaluated under (`evaluated_digest`). Returns the
    disagreements; an unattributable digest is reported UNPROVEN."""
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
    digest, unproven = evaluated_digest(match["explanation"])
    if unproven:
        problems.append(f"input_hash: UNPROVEN, {unproven}")
        return problems
    recomputed = canonical.input_hash(
        matching_policy_id=match["matching_policy_id"],
        matching_policy_version=match["matching_policy_version"],
        rule_registry_digest=digest,
        evaluated_offer_id=match["evaluated_offer_id"],
        request_snapshot=request, property_snapshot=prop, commercial_context_snapshot=offer,
        permission_snapshot=match["permission_snapshot"],
        freshness_snapshot=match["freshness_snapshot"])
    if recomputed != match["input_hash"]:
        problems.append("input_hash: not recomputed from the stored snapshots")
    return problems
