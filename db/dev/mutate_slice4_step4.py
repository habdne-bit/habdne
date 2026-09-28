"""Slice 4 step 4: which rule, validation or gate decision fails which test.

    .venv/bin/python db/dev/mutate_slice4_step4.py [R1 C1 ...] > /outside/the/tree.txt

Each mutation reintroduces one defect: a rule decided differently, a
refusal skipped (G4-3 (b), G4-5R, G4-7), a gate or blocking decision
changed (G4-4), or the stored form bypassed. The test file is step 4's
only. The rule pins, which would catch any rule edit, are step 2's, so they
cannot hide whether a behavioural test catches it.

**Left out, and why:** removing the cycle guard of the location ancestry
query. Its failure mode is non-termination on a cyclic tree, which this
runner has no timeout to observe. The guard is tested directly
(`test_location_ancestry_is_nearest_first_and_survives_a_cycle`), and it
ends in bounded time only because the guard is there.
"""
import sys

from mutation_runner import run

R = "src/turab/matching/rules.py"
C = "src/turab/matching/criteria.py"
H = "src/turab/matching/hard_gate.py"
S = "src/turab/matching/snapshots.py"

MUTATIONS = [
 # --- rules ------------------------------------------------------------------------------
 ("R1 transaction mapping swapped", R,
  'served = {"SALE": "BUY", "RENT": "RENT"}.get(offer_type)',
  'served = {"SALE": "RENT", "RENT": "BUY"}.get(offer_type)'),
 ("R2 PROPERTY_TYPE ignores NEQ / NOT_IN", R,
  '    inside = actual in wanted\n    if operator in ("NEQ", "NOT_IN"):\n'
  '        inside = not inside\n',
  '    inside = actual in wanted\n'),
 ("R3 PROPERTY_TYPE mismatch without its reason code", R,
  '"reason_code": None if inside else "PROPERTY_TYPE_MISMATCH",', '"reason_code": None,'),
 ("R4 LOCATION exact, not the subtree (G4-6)", R,
  "    inside = any(w in ancestry for w in wanted)", "    inside = here in wanted"),
 ("R5 LOCATION unknown taken as PASS", R,
  '        return {**base, "compatibility": "UNKNOWN", "reason_code": None,\n'
  '                "explanation": {"basis": "LOCATION_NOT_RECORDED"',
  '        return {**base, "compatibility": "PASS", "reason_code": None,\n'
  '                "explanation": {"basis": "LOCATION_NOT_RECORDED"'),
 ("R6 LOCATION reads a snapshot without ancestry", R,
  "    if not isinstance(ancestry, list) or not ancestry or ancestry[0] != here:",
  "    if False:"),
 ("R7 the seller expectation ignored (M-03, mandatory test 5)", R,
  "    if ask <= maximum or (expectation is not None and expectation <= maximum):",
  "    if ask <= maximum:"),
 ("R8 negotiable above max is PASS (G02, mandatory test 4)", R,
  '    return {**base, "compatibility": "UNKNOWN", "reason_code": "PRICE_NEGOTIATION_UNCONFIRMED",',
  '    return {**base, "compatibility": "PASS", "reason_code": "PRICE_NEGOTIATION_UNCONFIRMED",'),
 ("R9 negotiability UNKNOWN taken as NO", R,
  '    if negotiable == "NO":', '    if negotiable != "YES":'),
 ("R10 a null maximum is FAIL", R,
  '"compatibility": "UNKNOWN", "reason_code": None,\n'
  '                "explanation": {"basis": "BUDGET_MAX_NOT_STATED"',
  '"compatibility": "FAIL", "reason_code": None,\n'
  '                "explanation": {"basis": "BUDGET_MAX_NOT_STATED"'),
 ("R11 an unknown asking price is PASS", R,
  '"compatibility": "UNKNOWN", "reason_code": "PRICE_NOT_KNOWN"',
  '"compatibility": "PASS", "reason_code": "PRICE_NOT_KNOWN"'),
 ("R12 the expectation leaks into the explanation (R9.3)", R,
  '"explanation": {"basis": "PRICE_COMPATIBLE", "evidence": "NO_CLAIM_LINK"}}',
  '"explanation": {"basis": "PRICE_COMPATIBLE", "evidence": "NO_CLAIM_LINK",'
  ' "within": expectation}}'),
 ("R13 the SALE price rule compares a RENT price (G4-5R)", R,
  '    if offer is None or offer.get("transaction_type") != "SALE":', "    if False:"),
 ("R14 an area equal to the minimum fails", R,
  "    inside = area >= minimum", "    inside = area > minimum"),
 ("R15 an unknown area is FAIL", R,
  '        return {**base, "compatibility": "UNKNOWN", "reason_code": None,\n'
  '                "explanation": {"basis": "AREA_NOT_RECORDED"',
  '        return {**base, "compatibility": "FAIL", "reason_code": None,\n'
  '                "explanation": {"basis": "AREA_NOT_RECORDED"'),
 ("R16 land and built areas swapped", R,
  '{"LAND_AREA_MIN": "land_area_m2", "BUILT_AREA_MIN": "built_area_m2"}',
  '{"LAND_AREA_MIN": "built_area_m2", "BUILT_AREA_MIN": "land_area_m2"}'),
 ("R17 a count equal to the minimum fails", R,
  "    inside = value >= minimum", "    inside = value > minimum"),
 ("R18 the evidence claim is dropped (§3.4)", R,
  '"evidence_claim_id": attribute.get("resolved_claim_id")}', '"evidence_claim_id": None}'),
 ("R19 a missing count attribute is PASS", R,
  '        return {**base, "compatibility": "UNKNOWN", "reason_code": None,\n'
  '                "explanation": {"basis": "ATTRIBUTE_NOT_RECORDED"',
  '        return {**base, "compatibility": "PASS", "reason_code": None,\n'
  '                "explanation": {"basis": "ATTRIBUTE_NOT_RECORDED"'),
 ("R20 an UNKNOWN option compared as a value (C03, M-02)", R,
  '    if value in ("UNKNOWN", "UNSPECIFIED_DOCUMENT"):', "    if value in ():"),
 ("R21 UNSPECIFIED_DOCUMENT compared as a value", R,
  '    if value in ("UNKNOWN", "UNSPECIFIED_DOCUMENT"):', '    if value in ("UNKNOWN",):'),
 ("R22 an option criterion ignores NEQ / NOT_IN", R,
  '    inside = value in wanted\n    if operator in ("NEQ", "NOT_IN"):\n'
  '        inside = not inside\n    mismatch',
  '    inside = value in wanted\n    mismatch'),
 ("R23 DOCUMENT_MISMATCH not emitted", R,
  'mismatch = "DOCUMENT_MISMATCH" if code == "DOCUMENT_TYPE" else None', "mismatch = None"),
 ("R24 DOCUMENT_NOT_KNOWN not emitted", R,
  'unknown_reason = "DOCUMENT_NOT_KNOWN" if code == "DOCUMENT_TYPE" else None',
  "unknown_reason = None"),
 ("R25 a criterion without a rule passes silently (§3.2)", R,
  '"evidence_claim_id": None, "compatibility": "UNKNOWN", "reason_code": None,\n'
  '            "explanation": {"basis": "NO_DETERMINISTIC_RULE"}}',
  '"evidence_claim_id": None, "compatibility": "PASS", "reason_code": None,\n'
  '            "explanation": {"basis": "NO_DETERMINISTIC_RULE"}}'),
 # --- criteria: refusals (G4-3 (b), G4-5R, G4-7) ------------------------------------------
 ("C1 an unsuited operator is not refused", C,
  "    if operator not in operators:", "    if False:"),
 ("C2 an unreadable value is not refused", C,
  "    if value is None:\n        raise CriterionRefused",
  "    if False:\n        raise CriterionRefused"),
 ("C3 an unreadable unit is not refused", C,
  '    if crit["unit"] not in UNITS.get(code, (None,)):', "    if False:"),
 ("C4 a REQUIRED criterion without a rule is accepted", C,
  '        if importance == "REQUIRED":\n            raise CriterionRefused("G4-7", "REQUIRED, and',
  '        if False:\n            raise CriterionRefused("G4-7", "REQUIRED, and'),
 ("C5 a blocking criterion without a rule is accepted", C,
  "        if blocking:\n            raise CriterionRefused",
  "        if False:\n            raise CriterionRefused"),
 ("C6 TEXT_SEMANTIC handed to the code's rule", C,
  '    if code not in RULES or operator == "TEXT_SEMANTIC":', "    if code not in RULES:"),
 ("C7 a REQUIRED BUDGET_TARGET is accepted", C,
  '        if importance == "REQUIRED":\n            raise CriterionRefused("G4-7", "a soft-only',
  '        if False:\n            raise CriterionRefused("G4-7", "a soft-only'),
 ("C8 a location that does not exist is accepted", C,
  "        if any(p is None or p not in vocab.location_ancestry for p in parsed):",
  "        if any(p is None for p in parsed):"),
 ("C9 no contradiction check (G4-3 (b))", C,
  '                and _disjoint(row["code"], column["value"], _set_of(row), vocab)):',
  "                and False):"),
 ("C10 nested locations judged disjoint", C,
  "        return all(column_value not in above[v] and v not in above[column_value]",
  "        return all(column_value != v"),
 ("C11 a soft column counted in the contradiction check", C,
  '                        if c["importance"] == "REQUIRED" and c["value"] is not None}',
  '                        if c["value"] is not None}'),
 ("C12 a RENT request is evaluated (G4-5R)", C,
  '    if request["transaction_intent"] == "RENT":', "    if False:"),
 ("C13 a null budget column is added beside a budget row", C,
  '    if request.get("budget_max_dzd") is not None or not has_budget_row:', "    if True:"),
 ("C14 ordinals counted across codes", C,
  '        ordinals[criterion["code"]] = ordinals.get(criterion["code"], 0) + 1\n'
  '        criterion["ordinal"] = ordinals[criterion["code"]]',
  '        ordinals["*"] = ordinals.get("*", 0) + 1\n'
  '        criterion["ordinal"] = ordinals["*"]'),
 ("C15 deferred criteria dropped", C,
  '    deferred = [r for r in rows if "deferred_to" in r]', "    deferred = []"),
 # --- hard_gate: G4-4 and the gates -------------------------------------------------------
 ("H1 a REQUIRED FAIL is not blocking", H,
  '        return compatibility in ("FAIL", "UNKNOWN")', '        return compatibility == "UNKNOWN"'),
 ("H2 blocking_if_unknown ignored", H,
  '    return compatibility == "UNKNOWN" and blocking_if_unknown', "    return False"),
 ("H3 blocking_if_unknown blocks a soft FAIL", H,
  '    return compatibility == "UNKNOWN" and blocking_if_unknown',
  '    return compatibility != "PASS" and blocking_if_unknown'),
 ("H4 soft criteria decide the hard gate", H,
  '    required = [r for r in results if r.importance == "REQUIRED"]',
  "    required = list(results)"),
 ("H5 a REQUIRED unknown leaves the hard gate PASS", H,
  '    elif any(r.compatibility == "UNKNOWN" for r in required):', "    elif False:"),
 ("H6 unknowns on a rejected candidate called actionable", H,
  'actionable_unknowns=() if hard == "FAIL" else unknowns', "actionable_unknowns=unknowns"),
 ("H7 the information gate ignores blocking unknowns", H,
  'information_gate_status="UNKNOWN" if unknowns else "PASS"',
  'information_gate_status="PASS"'),
 ("H8 a reason code outside the seed is accepted", H,
  '    if output["reason_code"] is not None and output["reason_code"] not in MATCH_REASON_CODES:',
  "    if False:"),
 ("H9 a compatibility outside PASS/FAIL/UNKNOWN is accepted", H,
  '    if output["compatibility"] not in COMPATIBILITY:', "    if False:"),
 ("H10 rules read the live form, not the stored form", H,
  "    request, prop, offer = (snapshots.stored_form(x) for x in (request, prop, offer))",
  "    pass"),
 # --- snapshots: the ancestry the location rule reads -------------------------------------
 ("S1 no ancestry recorded, only the location itself", S,
  '    snapshot["location_ancestry"] = location_ancestry(session,\n'
  '                                                      snapshot["canonical_location_id"])',
  '    snapshot["location_ancestry"] = [snapshot["canonical_location_id"]]'),
 ("S2 ancestry root first", S,
  "    SELECT location_id FROM up ORDER BY depth\"\"\"",
  "    SELECT location_id FROM up ORDER BY depth DESC\"\"\""),
]

if __name__ == "__main__":
    run("TURAB — Slice 4 step 4: which rule, refusal or gate decision fails which test",
        "tests/test_slice4_step4.py", MUTATIONS, sys.argv[1:])
