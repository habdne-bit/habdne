"""Slice 4 step 6: which soft-score decision, refusal or pin fails which test.

    .venv/bin/python db/dev/mutate_slice4_step6.py [G1 S1 K1 ...] > /outside/the/tree.txt

Each mutation reintroduces one defect:
- G: the soft score of G4-12, as decided in the review of a5ea6f5 (weights,
  contributions, edge cases, rounding, the expectation, RENT);
- S: what `soft.py` gives the formula, or the refusal of the undecided
  column target;
- K: the pinning of the gates (versions run, versions recorded, the
  registry).

The test file is step 6's only.
"""
import sys

from mutation_runner import run

G = "src/turab/matching/gates.py"
S = "src/turab/matching/soft.py"
E = "src/turab/matching/eligibility.py"
N = "src/turab/matching/snapshots.py"
R = "src/turab/matching/registry.py"

MUTATIONS = [
 ("G1 PREFERRED weighs like FLEXIBLE", G,
  'weight_of = {"PREFERRED": 2, "FLEXIBLE": 1}', 'weight_of = {"PREFERRED": 1, "FLEXIBLE": 1}'),
 ("G2 UNKNOWN contributes like PASS", G,
  '"contribution": Fraction(1 if c["compatibility"] == "PASS" else 0)})',
  '"contribution": Fraction(0 if c["compatibility"] == "FAIL" else 1)})'),
 ("G3 a soft criterion without a rule carries weight (G4-7)", G,
  'if c["importance"] in weight_of and c["rule_id"] != "criterion.no_deterministic_rule":',
  'if c["importance"] in weight_of:'),
 ("G4 REQUIRED criteria counted as terms", G,
  'weight_of = {"PREFERRED": 2, "FLEXIBLE": 1}',
  'weight_of = {"PREFERRED": 2, "FLEXIBLE": 1, "REQUIRED": 3}'),
 ("G5 a score despite a hard gate that is not PASS", G,
  '    if hard_gate_status != "PASS":', "    if False:"),
 ("G6 the distance not capped by min(1, ...)", G,
  "Fraction(target - min(target, distance), target)", "Fraction(target - distance, target)"),
 ("G7 a zero target always contributes 1", G,
  "Fraction(1 if int(ask) == 0 else 0)", "Fraction(1)"),
 ("G8 a missing ask contributes 1", G,
  'proximity, basis = Fraction(0), "PRICE_NOT_KNOWN"',
  'proximity, basis = Fraction(1), "PRICE_NOT_KNOWN"'),
 ("G9 the seller expectation read as the price", G,
  '        ask = offer.get("asking_price_dzd")',
  '        ask = offer.get("seller_expectation_dzd") or offer.get("asking_price_dzd")'),
 ("G10 rounding by truncation", G,
  "millionths = (2 * share.numerator * 1_000_000 + share.denominator) // (2 * share.denominator)",
  "millionths = (share.numerator * 1_000_000) // share.denominator"),
 ("G11 no soft term scored 0, not null", G,
  '        return {"soft_score": None, "basis": "NO_SOFT_CRITERION", "terms": []}',
  '        return {"soft_score": Decimal(0), "basis": "NO_SOFT_CRITERION", "terms": []}'),
 ("G12 a RENT target compared (G4-5R)", G,
  '        if offer is None or offer.get("transaction_type") != "SALE":', "        if False:"),
 ("G13 a target's importance ignored", G,
  '"weight": weight_of[t["importance"]], "contribution": proximity,',
  '"weight": 1, "contribution": proximity,'),
 ("S1 the undecided column target scored", S,
  '    if any(t["source"] == "COLUMN" for t in targets):', "    if False:"),
 ("S2 deferred targets not given to the formula", S,
  '    targets = [d for d in plan.deferred if d["code"] == "BUDGET_TARGET"]',
  "    targets = []"),
 ("K1 the freshness snapshot does not name its version", N,
  '        "derived_by": "@".join(FRESHNESS_STATE),\n', ""),
 ("K2 the permission snapshot does not name its version", N,
  '    return {"format": PERMISSION_FORMAT, "derived_by": "@".join(BINDING_STATE),',
  '    return {"format": PERMISSION_FORMAT,'),
 ("K3 eligibility does not record its versions", E,
  '        engine={name: "@".join(key) for name, key in ENGINE.items()})', "        engine={})"),
 ("K4 the gates not registered", R,
  "from turab.matching import gates as _gates  # noqa: E402,F401\n", ""),
]

if __name__ == "__main__":
    run("TURAB — Slice 4 step 6: which soft-score decision, refusal or pin fails which test",
        "tests/test_slice4_step6.py", MUTATIONS, sys.argv[1:])
