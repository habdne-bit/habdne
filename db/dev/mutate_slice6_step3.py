"""Slice 6 step 3, the diagnostic's pure functions and replay: which test
refuses which weakening.

    .venv/bin/python db/dev/mutate_slice6_step3.py [V1 A1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule (plan revision 8; G6-2, G6-3, G6-5, G6-6,
G6-7, G6-11), in `matching/diagnostic_rules.py`, `matching/diagnostic.py`
or `services/diagnostic_replay.py`:
- V: the high-value reading (G6-2 (a));
- A: `suggested_actions` (G6-3), and what an entry may carry (§3.4);
- L: the relaxation scenarios (G6-5) and the location choice (G6-6);
- W: the eligibility a near match would reach (G6-5 (v));
- U: the format-2 summary's unknowns (G6-7);
- R: the replay's two checks (G6-11).

The test file is `tests/test_slice6_step3.py` only. The pins, which fail on
ANY edit of a pinned function, are in `test_slice6_step3_registry.py` and
Slice 4's files, so they cannot hide whether a behavioural test catches a
mutation (Slice 4 step 4's convention). See `mutation_runner.py`.

**Removed after the first run, as EQUIVALENT** (no test can tell them from
the code; `SLICE6-STEP3-MUTATIONS-FIRST-RUN.txt` keeps their run):
- V4, dropping the NEED_MORE_INFORMATION condition of `diagnostic.value@1`:
  with the hard gate not FAIL, freshness and permission PASS and one
  blocking unknown, `eligibility.precedence@1` gives NEED_MORE_INFORMATION;
- A10, dropping the gate from the key: INFORMATION alone carries a
  criterion, and FRESHNESS and PERMISSION differ by type;
- L4, reversing the inner sort of magnitudes: the final sort orders by
  `abs(magnitude)`;
- L10, `property_value is not None` for the COUNT_MINIMUM basis: in
  `count_min@2`'s FAIL results they are the same condition.
Three others survived because a test was missing (A9, L6, R2); the tests
were added.
"""
import sys

from mutation_runner import run

RULES = "src/turab/matching/diagnostic_rules.py"
WIRING = "src/turab/matching/diagnostic.py"
REPLAY = "src/turab/services/diagnostic_replay.py"
TESTS = "tests/test_slice6_step3.py"

MUTATIONS = [
    # --- V: high value (G6-2 (a)) ----------------------------------------------------
    ("V1 freshness ignored", RULES,
     '            or candidate["freshness_gate_status"] != "PASS"\n', ""),
    ("V2 permission ignored", RULES,
     '            or candidate["permission_gate_status"] != "PASS"):',
     "            ):"),
    ("V3 several actionable unknowns are high value", RULES,
     "    if len(actionable) != 1:\n        return []",
     "    if not actionable:\n        return []"),
    # --- A: suggested_actions (G6-3, §3.4) ---------------------------------------------
    ("A1 a REJECTED candidate gets work", RULES,
     'if candidate["eligibility"] not in ("NEED_MORE_INFORMATION", "NEEDS_CONFIRMATION"):',
     'if candidate["eligibility"] not in ("NEED_MORE_INFORMATION", "NEEDS_CONFIRMATION",\n'
     '                                         "REJECTED"):'),
    ("A2 only the first unknown", RULES,
     "                    \"reason_code\": c[\"reason_code\"], \"basis\": basis}))\n",
     "                    \"reason_code\": c[\"reason_code\"], \"basis\": basis}))\n"
     "                break\n"),
    ("A3 every information entry HIGH", RULES,
     'items.append((0, kind, "HIGH" if high else "NORMAL", {',
     'items.append((0, kind, "HIGH", {'),
    ("A4 the price entity is the property", RULES,
     'elif basis in ("PRICE_NOT_KNOWN", "PRICE_ABOVE_MAX_NEGOTIATION_UNCONFIRMED",',
     'elif basis in ("PRICE_NOT_KNOWN_X",'),
    ("A5 a document is OTHER work", RULES,
     '{"DOCUMENT_TYPE": "VERIFY_DOCUMENT", "RIGHT_TYPE": "VERIFY_DOCUMENT",',
     '{"RIGHT_TYPE": "VERIFY_DOCUMENT",'),
    ("A6 freshness reasons ignored", RULES,
     '            if r["gate"] == "FRESHNESS":', '            if False:'),
    ("A7 permission reasons ignored", RULES,
     '            elif r["gate"] == "PERMISSION":', '            elif False:'),
    ("A8 the class order ignored", RULES,
     '        return (0 if entry["priority"] == "HIGH" else 1, entry["rank"],',
     '        return (0 if entry["priority"] == "HIGH" else 1, 0,'),
    ("A9 the count ascending", RULES,
     '                -len(entry["candidates"]), str(s["id"]),',
     '                len(entry["candidates"]), str(s["id"]),'),
    ("A11 a shared subject is not merged", RULES,
     'key = (kind, subject["entity"], subject["id"], subject["gate"],',
     'key = (kind, candidate["property_id"], subject["entity"], subject["id"], subject["gate"],'),
    ("A12 an entry carries the property's value", RULES,
     '"request_criterion_id": c["request_criterion_id"],\n                    "reason_code": c["reason_code"], "basis": basis}))',
     '"request_criterion_id": c["request_criterion_id"], "value": c["property_value"],\n'
     '                    "reason_code": c["reason_code"], "basis": basis}))'),
    # --- L: relaxation (G6-5, G6-6) -------------------------------------------------------
    ("L1 two failures make a near match", RULES,
     'if not (candidate["eligibility"] == "REJECTED" and len(failing) == 1',
     'if not (candidate["eligibility"] == "REJECTED" and len(failing) >= 1'),
    ("L2 the budget delta reversed", RULES,
     'value = c["property_value"]["asking_price_dzd"] - c["request_value"]["value"]',
     'value = c["request_value"]["value"] - c["property_value"]["asking_price_dzd"]'),
    ("L3 not cumulative", RULES,
     "turned = [n for v, n in members if abs(v) <= abs(magnitude)]",
     "turned = [n for v, n in members if abs(v) == abs(magnitude)]"),
    ("L5 not stated at the asking price", RULES,
     '                    body["stated_at"] = "ASKING_PRICE"\n', "                    pass\n"),
    ("L6 G6-6: the widening before the property's ancestor", RULES,
     'e["common"] is None, e["property_below"] or 0, e["widened"] or 0,',
     'e["common"] is None, e["widened"] or 0, e["property_below"] or 0,'),
    ("L7 G6-6: the last requested location wins a tie", RULES,
     '                e["position"]))[0]', '                -e["position"]))[0]'),
    ("L8 a widening turns only its own choosers", RULES,
     "n for n in same_criterion if target in n[\"location_ancestry\"]]",
     "n for _, n in members]"),
    ("L9 a document scenario without the user's choice", RULES,
     '                entry["only_if_user_chooses"] = True\n', "                pass\n"),
    ("L11 not subordinate to the high actions", RULES,
     '        scenario["subordinate_to"] = list(subordinate_to)',
     '        scenario["subordinate_to"] = []'),
    ("L12 widenings ordered by id only", RULES,
     "            widened = 0 if target is None else min(\n"
     "                n[\"choice\"][\"levels_widened\"] for _, n in members)",
     "            widened = 0"),
    # --- W: would reach (G6-5 (v)) ---------------------------------------------------------
    ("W1 a blocking soft unknown is dropped", WIRING,
     '            "information_gate_status": "UNKNOWN" if unknowns else "PASS",',
     '            "information_gate_status": "PASS",'),
    ("W2 the freshness reasons are dropped", WIRING,
     '                "reasons": [r for r in record["reasons"] if r["gate"] == name]}',
     '                "reasons": []}'),
    # --- U: unknowns (G6-7) ---------------------------------------------------------------
    ("U1 a non-blocking unknown counted as blocking", WIRING,
     "            if not c[\"blocking\"]:\n                entry[\"non_blocking\"] += 1\n"
     "                continue\n", ""),
    ("U2 a rejected candidate's unknown is actionable", WIRING,
     '            if record["hard_gate_status"] != "FAIL":\n                entry["actionable"] += 1',
     '            if True:\n                entry["actionable"] += 1'),
    ("U3 high value never counted", WIRING,
     '            if key in valued_keys:\n                entry["high_value"] += 1',
     '            if False:\n                entry["high_value"] += 1'),
    # --- R: replay (G6-11) ---------------------------------------------------------------
    ("R1 (R) no hash check", REPLAY,
     '        if row["input_hash"] != entry["input_hash"]:', "        if False:"),
    ("R2 (R) no instant check", REPLAY,
     '        if entry["stored"] == "NEW" and not row["at_run"]:', "        if False:"),
    ("R3 (D) the suggestions not compared", REPLAY,
     '    for part in ("suggested_actions", "relaxation_scenarios"):',
     '    for part in ("relaxation_scenarios",):'),
    ("R4 (D) the scenarios not compared", REPLAY,
     '    for part in ("suggested_actions", "relaxation_scenarios"):',
     '    for part in ("suggested_actions",):'),
    ("R5 (D) reads the chains again instead of the stored ones", REPLAY,
     '                    location_chains=summary["requested_location_chains"],',
     '                    location_chains=__import__("turab.matching.diagnostic", '
     'fromlist=["x"]).read_location_chains(conn, list(summary["requested_location_chains"])),'),
]

if __name__ == "__main__":
    sys.exit(1 if run("TURAB — Slice 6 step 3: the diagnostic's functions and replay",
                      TESTS, MUTATIONS, tuple(sys.argv[1:])) else 0)
