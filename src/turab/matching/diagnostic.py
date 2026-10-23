"""The diagnostic's computed parts, and their replay (Slice 6 step 3).

Ref: `docs/gate/SLICE_6_PLAN.md` G6-2, G6-3, G6-5, G6-6, G6-7, G6-11,
decided in the review of bd54216; §3.5 (replayable); F6-2, F6-10, F6-11.

**Step 3 writes nothing.** The run (`services/matching_run.py`) still
writes `blocker_summary` format 1 and empty suggestions; step 4 makes it
write what `compute` returns. Until then nothing calls `compute` but the
tests.

**One input, for the run and for the replay.** `candidate_record` builds a
candidate's record from its STORED match (`matching_run.match_view`): the
gates, the criterion rows, the reasons the explanation records, and the
property's location chain. The pinned functions read only these records and
the stored location chains. A live run that reads back what it stored, and
a replay, therefore give them the same input. A record carries no commercial
snapshot: `seller_expectation_dzd` is not in it (§3.4).

**The pinned functions** (`diagnostic_rules.py`) do not call one another.
This module wires them, and records their versions in format 2 (G6-7).

**Replay** (G6-11) is `services/diagnostic_replay.py`: it reads the stored
matches and calls `compute` again.
"""
from __future__ import annotations

import uuid
from typing import Any, Iterable, Mapping

from sqlalchemy import text

from turab.matching import explain, snapshots
from turab.matching.registry import REGISTRY

SUMMARY_FORMAT = "turab.blocker-summary/2"
VALUE = ("diagnostic.value", "1")
ACTIONS = ("diagnostic.actions", "1")
RELAXATION = ("diagnostic.relaxation", "1")
#: The parts of a format-2 summary that `compute` derives. The others are
#: what the run recorded (`evaluated`, `requested_location_chains`,
#: `excluded`, `excluded_counts`), verified by (R) or taken as input.
COMPUTED_SUMMARY_KEYS = ("format", "candidates_evaluated", "by_reason", "excluded_counts",
                         "unknowns", "versions")

_CHAINS = """
    WITH RECURSIVE up(location_id, location_type, parent_id, depth, path) AS (
        SELECT location_id, location_type::text, parent_id, 0, ARRAY[location_id]
          FROM turab.locations WHERE location_id = :loc
        UNION ALL
        SELECT l.location_id, l.location_type::text, l.parent_id, u.depth + 1,
               u.path || l.location_id
          FROM turab.locations l JOIN up u ON l.location_id = u.parent_id
         WHERE NOT l.location_id = ANY(u.path))
    SELECT location_id, location_type FROM up ORDER BY depth"""


def _key(code: str, ordinal: Any) -> str:
    return explain.criterion_key(code, ordinal)


def candidate_record(match: Mapping[str, Any]) -> dict:
    """The record the pinned functions read, from a stored match as
    `matching_run.match_view` returns it. Stored form throughout."""
    explanation = match["explanation"]
    criteria = []
    for c in match["criteria"]:
        stated = explanation["criteria"][_key(c["criterion_code"], c["ordinal"])]
        criteria.append({
            "criterion": c["criterion_code"], "ordinal": c["ordinal"],
            "request_criterion_id": c["request_criterion_id"],
            "importance": c["importance"], "compatibility": c["compatibility"],
            "blocking": c["blocking"], "reason_code": c["reason_code"],
            "basis": stated["rule_explanation"].get("basis"),
            "request_value": c["request_value"], "property_value": c["property_value"]})
    return snapshots.stored_form({
        "match_id": match["match_id"], "property_id": match["property_id"],
        "offer_id": match["evaluated_offer_id"], "eligibility": match["eligibility"],
        "hard_gate_status": match["hard_gate_status"],
        "freshness_gate_status": match["freshness_gate_status"],
        "permission_gate_status": match["permission_gate_status"],
        "criteria": criteria,
        "reasons": [{k: v for k, v in r.items() if k != "wording"}
                    for r in explanation["reasons"]],
        "location_ancestry": match["property_snapshot"].get("location_ancestry") or [],
        "precedence": explanation["engine"]["precedence"]})


def requested_location_ids(records: Iterable[Mapping[str, Any]]) -> list[str]:
    """Every location a LOCATION criterion requests, in first-seen order."""
    out: list[str] = []
    for record in records:
        for c in record["criteria"]:
            if c["criterion"] != "LOCATION":
                continue
            value = c["request_value"]["value"]
            for w in (value if c["request_value"]["operator"] == "IN" else [value]):
                if w not in out:
                    out.append(w)
    return out


def read_location_chains(conn: Any, location_ids: Iterable[Any]) -> dict:
    """G6-6, F6-2: each requested location's chain, nearest first, with its
    type, as read NOW (in the run's snapshot, from step 4). Stored with the
    diagnostic so that a replay never reads `locations` again (F6-10)."""
    chains = {}
    for w in location_ids:
        rows = conn.execute(text(_CHAINS), {"loc": uuid.UUID(str(w))}).mappings().all()
        chains[str(w)] = [{"location_id": str(r["location_id"]),
                           "location_type": r["location_type"]} for r in rows]
    return snapshots.stored_form(chains)


def would_reach(record: Mapping[str, Any]) -> dict:
    """G6-5 (v): the eligibility a near match would reach on its stored facts
    with its one REQUIRED failure removed, by the precedence the match itself
    recorded. NEED_MORE_INFORMATION is possible: a blocking PREFERRED or
    FLEXIBLE unknown stays."""
    unknowns = [{"criterion": c["criterion"], "ordinal": c["ordinal"],
                 "reason_code": c["reason_code"]} for c in record["criteria"]
                if c["blocking"] and c["compatibility"] == "UNKNOWN"]
    hard = {"hard_gate_status": "PASS",
            "information_gate_status": "UNKNOWN" if unknowns else "PASS",
            "required_failures": [], "blocking_unknowns": unknowns}

    def gate(name, status):
        return {"status": status,
                "reasons": [r for r in record["reasons"] if r["gate"] == name]}
    rule_id, version = record["precedence"].split("@")
    out = REGISTRY.resolve(rule_id, version).evaluate(
        hard, gate("FRESHNESS", record["freshness_gate_status"]),
        gate("PERMISSION", record["permission_gate_status"]))
    return snapshots.stored_form(out)


def _near_match(record: Mapping[str, Any]) -> bool:
    required = [c["compatibility"] for c in record["criteria"] if c["importance"] == "REQUIRED"]
    return (record["eligibility"] == "REJECTED" and required.count("FAIL") == 1
            and required.count("UNKNOWN") == 0)


def unknowns(records: list[Mapping[str, Any]], high_value: list[list]) -> dict:
    """G6-7: per criterion key, the candidates with it UNKNOWN, split into
    blocking and non-blocking (G4-4), and within blocking, actionable and
    high-value (§3.2). Each candidate counted once per key."""
    out: dict[str, dict] = {}
    for record, valued in zip(records, high_value, strict=True):
        valued_keys = {_key(v["criterion"], v["ordinal"]) for v in valued}
        for c in record["criteria"]:
            if c["compatibility"] != "UNKNOWN":
                continue
            key = _key(c["criterion"], c["ordinal"])
            entry = out.setdefault(key, {"blocking": 0, "non_blocking": 0,
                                         "actionable": 0, "high_value": 0})
            if not c["blocking"]:
                entry["non_blocking"] += 1
                continue
            entry["blocking"] += 1
            if record["hard_gate_status"] != "FAIL":
                entry["actionable"] += 1
            if key in valued_keys:
                entry["high_value"] += 1
    return {key: out[key] for key in sorted(out)}


class _Verdict:
    """What `explain.blocker_summary` reads of a verdict: its reasons."""

    def __init__(self, reasons):
        self.reasons = reasons


def current_versions() -> dict[str, str]:
    """The versions a NEW computation runs, `name -> "id@version"`."""
    return {"value": "@".join(VALUE), "actions": "@".join(ACTIONS),
            "relaxation": "@".join(RELAXATION)}


def compute(request_id: Any, records: list[Mapping[str, Any]], *,
            location_chains: Mapping[str, Any], evaluated: list[Mapping[str, Any]],
            excluded: list[Mapping[str, Any]],
            versions: Mapping[str, str] | None = None) -> dict:
    """`suggested_actions`, `relaxation_scenarios` and the format-2
    `blocker_summary`, from the records in the run's evaluation order.

    `versions` names the pinned functions to run (`current_versions()` when
    omitted). A replay passes the versions the row RECORDS, so an old row is
    recomputed by its own versions after a new one is registered (G6-11;
    review of 220573a). The summary records the versions run. An unknown
    version raises `UnknownRuleVersion`.

    `evaluated` and `excluded` are what the run records (G6-11); they enter
    the summary unchanged. Pure: `location_chains` is given, never read."""
    versions = dict(versions if versions is not None else current_versions())
    request_id = snapshots.stored_form(request_id)
    value = REGISTRY.resolve(*versions["value"].split("@"))
    high_value = [value.evaluate(r) for r in records]
    actions = REGISTRY.resolve(*versions["actions"].split("@")).evaluate(
        request_id, records, high_value)
    reach = [would_reach(r) if _near_match(r) else None for r in records]
    scenarios = REGISTRY.resolve(*versions["relaxation"].split("@")).evaluate(
        records, reach, location_chains,
        [a["key"] for a in actions if a["priority"] == "HIGH"])
    summary = dict(explain.blocker_summary([_Verdict(r["reasons"]) for r in records], ()))
    summary.update({
        "format": SUMMARY_FORMAT,
        "excluded": list(excluded),
        "excluded_counts": _excluded_counts(excluded),
        "unknowns": unknowns(records, high_value),
        "versions": {name: versions[name] for name in ("value", "actions", "relaxation")},
        "evaluated": list(evaluated),
        "requested_location_chains": dict(location_chains)})
    return snapshots.stored_form({"suggested_actions": actions,
                                  "relaxation_scenarios": scenarios,
                                  "blocker_summary": summary})


def _excluded_counts(excluded: list[Mapping[str, Any]]) -> dict:
    counts: dict[str, int] = {}
    for e in excluded:
        counts[e["reason"]] = counts.get(e["reason"], 0) + 1
    return counts
