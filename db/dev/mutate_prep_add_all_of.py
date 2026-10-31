"""The preparatory step `add_all_of` (Slice 8 plan Q-B3 (a)): which test refuses which weakening.

    .venv/bin/python db/dev/mutate_prep_add_all_of.py [K1 N1 ...] > /outside/the/tree.txt

Authorized in the review of `0a78e91`: "a separate, limited preparatory
step: `add_all_of` in the corrections loader, the contract generator and their
tests". Each mutation weakens ONE rule:
- K: the loader's checks of an `add_all_of` entry;
- N: the effective body is an operation-local copy, the branches appended;
- G: the generator's annotation;
- V: `body_violations`, the runtime's judge, keyword by keyword, and its
  refusal to judge an unread keyword.

Not mutated, each with its reason:
- `default` (an annotation, read by nothing);
- the date-time branch of `_format_holds`: no frozen schema the step's tests
  narrow carries a date-time; it is asserted, and stays to be exercised by
  the first correction that narrows one;
- the `seen` guard of `_schema_problems`: no frozen component refers to
  itself; it prevents a loop that the frozen contract cannot produce today.

Only `tests/test_contract_add_all_of.py` is run. See `mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

CONTRACT = "src/turab/auth/contract.py"
GENERATOR = "db/gate/generate_effective_contract.py"
TESTS = "tests/test_contract_add_all_of.py"

MUTATIONS = [
 # --- K: the loader -------------------------------------------------------------------------
 ("K1 the key not admitted", CONTRACT,
  '"add_all_of", "frozen_defaults"', '"frozen_defaults"'),
 ("K2 the loader's check never called", CONTRACT,
  '        if "add_all_of" in entry:\n            _check_add_all_of(',
  '        if False:\n            _check_add_all_of('),
 ("K3 an unread keyword admitted", CONTRACT,
  '    problems = [f"keyword {k!r} is not one the validator reads"\n'
  '                for k in sorted(set(node) - _ALL_OF_KEYWORDS)]',
  '    problems = []'),
 ("K4 a referenced component not inspected", CONTRACT,
  '        elif name not in seen:\n', '        elif False:\n'),
 ("K5 a $ref to no component admitted", CONTRACT,
  '            problems.append(f"$ref {ref!r}: no component {name}")', '            pass'),
 ("K6 any format admitted", CONTRACT,
  '    if "format" in node and node["format"] not in _ALL_OF_FORMATS:', '    if False:'),
 ("K7 additionalProperties other than false admitted", CONTRACT,
  '    if extra is not False and (branch or extra is not True):', '    if False:'),
 ("K8 then without if admitted", CONTRACT,
  '    if "then" in node and "if" not in node:', '    if False:'),
 ("K9 if without then admitted", CONTRACT,
  '    if "if" in node and "then" not in node:', '    if False:'),
 ("K10 any type admitted", CONTRACT,
  '            problems.append(f"type {kind!r} is not a JSON type")', '            pass'),
 # --- N: the operation-local copy -----------------------------------------------------------
 ("N1 the branches not appended", CONTRACT,
  '    if entry.get("add_all_of"):\n        # Slice 8 Q-B3 (a)',
  '    if False:\n        # Slice 8 Q-B3 (a)'),
 ("N2 the frozen body changed", CONTRACT,
  '        schema["allOf"] = (list(frozen.get("allOf") or [])',
  '        schema["allOf"] = (frozen.setdefault("allOf", [])'),
 ("N3 the entry's own objects in the body", CONTRACT,
  '                           + json.loads(json.dumps(entry["add_all_of"])))',
  '                           + entry["add_all_of"])'),
 # --- G: the generator ----------------------------------------------------------------------
 ("G1 the annotation omits the branches", GENERATOR,
  '                marker["add-all-of"] = json.loads(json.dumps(entry["add_all_of"]))',
  '                pass'),
 # --- V: the runtime's judge ----------------------------------------------------------------
 ("V1 if/then ignored", CONTRACT,
  '    if "if" in schema and not body_violations(schema["if"], value, contract, where):',
  '    if False:'),
 ("V2 required ignored", CONTRACT,
  '        out += [f"{where}.{f}: required" for f in schema.get("required") or ()\n'
  '                if f not in value]',
  '        out += []'),
 ("V3 additionalProperties false ignored", CONTRACT,
  '        if schema.get("additionalProperties") is False:', '        if False:'),
 ("V4 enum ignored", CONTRACT,
  '    if "enum" in schema and not any(_json_same(value, e) for e in schema["enum"]):',
  '    if False:'),
 ("V5 const ignored", CONTRACT,
  '    if "const" in schema and not _json_same(value, schema["const"]):', '    if False:'),
 ("V6 items ignored", CONTRACT,
  '    if isinstance(value, list) and "items" in schema:', '    if False:'),
 ("V7 anyOf read as allOf", CONTRACT,
  '    if "anyOf" in schema and all(body_violations(b, value, contract, where)',
  '    if "anyOf" in schema and any(body_violations(b, value, contract, where)'),
 ("V8 minimum ignored", CONTRACT,
  '    if "minimum" in schema and _type_holds("number", value) and value < schema["minimum"]:',
  '    if False:'),
 ("V9 a boolean taken for an integer", CONTRACT,
  '        "integer": isinstance(value, int) and not isinstance(value, bool),',
  '        "integer": isinstance(value, int),'),
 ("V10 an unread keyword judged as absent", CONTRACT,
  '    if unread:\n        raise ContractError(f"{where}: keyword(s) {unread} not read by body_violations")',
  '    if False:\n        raise ContractError(f"{where}: keyword(s) {unread} not read by body_violations")'),
 ("V11 format not asserted", CONTRACT,
  '    if "format" in schema and isinstance(value, str) and \\\n',
  '    if False and \\\n'),
 ("V12 a $ref not followed", CONTRACT,
  '        out += body_violations(contract["components"]["schemas"][name], value, contract,\n'
  '                               where)',
  '        pass'),
 ("V13 the allOf branches not applied", CONTRACT,
  '    for branch in schema.get("allOf") or ():\n        out += body_violations(branch, value, contract, where)',
  '    for branch in ():\n        out += body_violations(branch, value, contract, where)'),
 ("V14 a violation names the value", CONTRACT,
  '        out.append(f"{where}: not one of the allowed values")',
  '        out.append(f"{where}: {value!r} not one of the allowed values")'),
]


def _check_anchors() -> None:
    """Each anchor names ONE site: the runner replaces every occurrence. Run
    before a run, never on import."""
    for name, rel, old, _new in MUTATIONS:
        count = (ROOT / rel).read_text().count(old)
        assert count == 1, (name, count)
    labels = [m[0].split()[0] for m in MUTATIONS]
    assert len(set(labels)) == len(labels)


if __name__ == "__main__":
    _check_anchors()
    survivors = run("TURAB — preparatory step: add_all_of (Slice 8 plan Q-B3 (a))", TESTS,
                    MUTATIONS, tuple(sys.argv[1:]))
    sys.exit(1 if survivors else 0)
