"""Slice 4 step 2: which check of the canonical form, input hash, registry,
policy loader and snapshots fails which test.

    .venv/bin/python db/dev/mutate_slice4_step2.py [S1 S2 ...] > /outside/the/tree.txt

See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

C = "src/turab/matching/canonical.py"
R = "src/turab/matching/registry.py"
P = "src/turab/matching/policy.py"
S = "src/turab/matching/snapshots.py"

MUTATIONS = [
 ("S1 floats accepted", C,
  '        raise CanonicalError(f"{path}: a float has no canonical form; use Decimal")',
  "        return value"),
 ("S2 decimals written as their text, not by value", C,
  "    return format(value.normalize(), \"f\")", "    return str(value)"),
 ("S3 datetimes not normalised to UTC", C,
  'return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")',
  "return value.isoformat()"),
 ("S4 naive datetimes accepted", C,
  "        if value.tzinfo is None or value.utcoffset() is None:", "        if False:"),
 ("S5 non-string keys stringified", C,
  "            if not isinstance(key, str):", "            if False:"),
 ("S6 evaluated_offer_id left out of the document", C,
  '        "evaluated_offer_id": evaluated_offer_id,\n', ""),
 ("S7 evaluated_at accepted as an input", C,
  'FORBIDDEN_INPUT_KEYS = frozenset({"evaluated_at", "input_hash"})',
  "FORBIDDEN_INPUT_KEYS = frozenset()"),
 ("S8 ASCII escaping", C, "ensure_ascii=False, allow_nan=False", "ensure_ascii=True, allow_nan=False"),
 ("S9 keys not sorted", C, "json.dumps(normalize(value), sort_keys=True,",
  "json.dumps(normalize(value), sort_keys=False,"),
 ("S10 a version may be re-implemented", R, "            if key in self._rules:", "            if False:"),
 ("S11 a changed source goes unreported", R,
  "            elif pins[key] != rule.source_sha256():", "            elif False:"),
 ("S12 a vanished version goes unreported", R,
  "        for key in sorted(set(pins) - set(registered)):", "        for key in []:"),
 ("S13 the digest ignores the source", R,
  'lines = "".join(f"{r.rule_id}\\t{r.rule_version}\\t{r.source_sha256()}\\n"',
  'lines = "".join(f"{r.rule_id}\\t{r.rule_version}\\n"'),
 ("S14 automatic relaxation tolerated", P,
  '    if rules.get("automatic_request_relaxation") is not False:', "    if False:"),
 ("S15 human review not required", P,
  '    if rules.get("human_review_required_for_opportunity") is not True:', "    if False:"),
 ("S16 any hard-gate mapping tolerated", P,
  '    if rules.get("hard_gate") != IMPLEMENTED_HARD_GATE:', "    if False:"),
 ("S17 any version string accepted", P,
  "    if not isinstance(requested, str) or requested != policy.version:",
  "    if not isinstance(requested, str):"),
 ("S18 criteria in no declared order", S,
  "             ORDER BY sort_order, criterion_code, request_criterion_id", ""),
 ("S19 jsonb numbers parsed as floats", S,
  "    return json.loads(value, parse_float=Decimal, parse_int=Decimal)",
  "    return json.loads(value)"),
 ("S20 alias status not recorded", S,
  'snapshot["identity"] = {"is_alias": alias_of is not None,',
  'snapshot["identity"] = {"is_alias": False,'),
 ("S21 non-finite decimals accepted", C,
  "    if not value.is_finite():", "    if False:"),
 ("S22 the pin path bound at definition time", R,
  "    path = path or PINS_PATH\n", "    path = path or pathlib.Path(__file__).with_name('rule_pins.py')\n"),
]

if __name__ == "__main__":
    run("TURAB — Slice 4 step 2: which check fails which test",
        "tests/test_slice4_step2.py", MUTATIONS, sys.argv[1:])
