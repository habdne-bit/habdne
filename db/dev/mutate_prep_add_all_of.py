"""The preparatory step `add_all_of` (Slice 8 plan Q-B3 (a)): which test refuses which weakening.

    .venv/bin/python db/dev/mutate_prep_add_all_of.py [K1 N1 ...] > /outside/the/tree.txt

Authorized in the review of `0a78e91`: "a separate, limited preparatory
step: `add_all_of` in the corrections loader, the contract generator and their
tests". Each mutation weakens ONE rule:
- K: the loader's checks of an `add_all_of` entry;
- N: the effective body is an operation-local copy, the branches appended;
- G: the generator's annotation;
- V: `body_violations`, the runtime's judge, keyword by keyword, and its
  refusal to judge an unread keyword;
- S (addendum, review of a7a4fe9): the structure of each keyword's value,
  checked by `_value_problems` for the loader and the judge alike, and
  `date-time` no longer admitted.

Not mutated, each with its reason:
- `default` as a keyword of judgement (an annotation, read by nothing); its
  value's structure is (S5);
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
  '    if "format" in node and not (isinstance(node["format"], str)',
  '    if False and not (isinstance(node["format"], str)'),
 ("K7 additionalProperties other than false admitted", CONTRACT,
  '    if branch and node.get("additionalProperties", False) is not False:', '    if False:'),
 ("K8 then without if admitted", CONTRACT,
  '    if "then" in node and "if" not in node:', '    if False:'),
 ("K9 if without then admitted", CONTRACT,
  '    if "if" in node and "then" not in node:', '    if False:'),
 ("K10 any type admitted", CONTRACT,
  '            problems += [f"type {k!r} is not a JSON type" for k in kinds\n'
  '                         if k not in _ALL_OF_TYPES]',
  '            pass'),
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
  '        out += body_violations(target, value, contract, where)',
  '        pass'),
 ("V13 the allOf branches not applied", CONTRACT,
  '    for branch in schema.get("allOf") or ():\n        out += body_violations(branch, value, contract, where)',
  '    for branch in ():\n        out += body_violations(branch, value, contract, where)'),
 ("V14 a violation names the value", CONTRACT,
  '        out.append(f"{where}: not one of the allowed values")',
  '        out.append(f"{where}: {value!r} not one of the allowed values")'),
 # --- S: the structure of each keyword's value (review of a7a4fe9) -------------------------
 ("S1 required's structure unchecked", CONTRACT,
  '    if "required" in node:\n        names = node["required"]',
  '    if False:\n        names = node["required"]'),
 ("S2 minimum's structure unchecked", CONTRACT,
  '    if "minimum" in node and not (_type_holds("number", node["minimum"])',
  '    if False and not (_type_holds("number", node["minimum"])'),
 ("S3 properties' structure unchecked", CONTRACT,
  '    if "properties" in node and not (isinstance(node["properties"], dict)',
  '    if False and not (isinstance(node["properties"], dict)'),
 ("S4 enum's structure unchecked", CONTRACT,
  '    if "enum" in node:\n        values = node["enum"]',
  '    if False:\n        values = node["enum"]'),
 ("S5 const and default not checked as JSON values", CONTRACT,
  '        if key in node and not _is_json(node[key]):', '        if False:'),
 ("S6 type's structure unchecked", CONTRACT,
  '        if not kinds or not all(isinstance(k, str) for k in kinds) \\\n',
  '        if False and not all(isinstance(k, str) for k in kinds) \\\n'),
 ("S7 anyOf's structure unchecked", CONTRACT,
  '    if "anyOf" in node and not (isinstance(node["anyOf"], list) and node["anyOf"]):',
  '    if False:'),
 ("S8 additionalProperties as a schema admitted", CONTRACT,
  '    if "additionalProperties" in node and not isinstance(node["additionalProperties"], bool):',
  '    if False:'),
 ("S9 an enum value twice admitted", CONTRACT,
  '                or any(_json_same(a, b) for i, a in enumerate(values) for b in values[i + 1:]):',
  '                or False:'),
 ("S10 an enum value not checked as JSON", CONTRACT,
  'if not isinstance(values, list) or not values or not all(map(_is_json, values)) \\\n',
  'if not isinstance(values, list) or not values \\\n'),
 ("S11 the judge does not check structure", CONTRACT,
  '    if malformed:\n        raise ContractError(f"{where}: " + "; ".join(malformed))',
  '    if False:\n        raise ContractError(f"{where}: " + "; ".join(malformed))'),
 ("S12 the judge follows a $ref to no component", CONTRACT,
  '        if target is None:\n            raise ContractError(f"{where}: $ref',
  '        if False:\n            raise ContractError(f"{where}: $ref'),
 ("S13 any value taken for JSON", CONTRACT,
  '    return False\n\n\ndef _value_problems', '    return True\n\n\ndef _value_problems'),
 ("S14 a required name twice admitted", CONTRACT,
  '                or len(set(names)) != len(names):', '                or False:'),
 ("S15 date-time admitted again", CONTRACT,
  '_ALL_OF_FORMATS = frozenset({"uuid"})', '_ALL_OF_FORMATS = frozenset({"uuid", "date-time"})'),
 ("S16 the judge's allOf not checked", CONTRACT,
  '    if "allOf" in schema and not (isinstance(schema["allOf"], list) and schema["allOf"]):',
  '    if False:'),
 ("S17 the judge reads a non-object as a schema", CONTRACT,
  '    if not isinstance(schema, dict):\n        raise ContractError(f"{where}: {schema!r} is not',
  '    if False:\n        raise ContractError(f"{where}: {schema!r} is not'),
 ("S18 minimum not required finite", CONTRACT,
  '                                  and math.isfinite(node["minimum"])):',
  '                                  and True):'),
 ("S19 a non-finite number taken for JSON", CONTRACT,
  '        return math.isfinite(value)', '        return True'),
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
