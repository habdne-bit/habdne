"""`add_all_of`: a request-body narrowing that appends `allOf` branches.

Ref: Slice 8 plan (`docs/gate/SLICE_8_PLAN.md`) Q-B3 (a), decided in the
review of `0a78e91`: "a separate, limited preparatory step: `add_all_of` in
the corrections loader, the contract generator and their tests". **It
activates nothing:** no entry of `docs/contract/CONTRACT_CORRECTIONS.yaml`
uses the key, and CORRECTION-009 stays a draft.

What the review asked this file to prove:
- the addition applies to an **operation-local copy** of the body; the frozen
  contract is unchanged;
- **the effective contract and the runtime validation refuse the same
  payload**: the body the GENERATOR writes, judged by an independent judge
  below, against `contract.body_violations` on the loader's body, body for
  body, with the expected verdict stated too;
- invalid correction input is refused;
- **no other operation changes** in the effective contract.

The narrowing used here is a TEST entry, `TEST-ADD-ALL-OF`, in a temporary
copy of the corrections file. It is not CORRECTION-009.
"""
from __future__ import annotations

import copy
import datetime
import pathlib
import uuid

import pytest
import yaml

from turab.auth import contract as C

ROOT = pathlib.Path(__file__).resolve().parents[1]
OPERATION = "postExternalLeadsLeadIdConvert"
ROUTE = ("/external-leads/{lead_id}/convert", "post")

PAYLOAD = {
    "type": "object",
    "additionalProperties": False,
    "required": ["intent", "transaction_intent"],
    "properties": {
        "intent": {"type": "string", "enum": ["EXPLORING", "ACTIVE_SEARCH", "READY_TO_ACT"]},
        "transaction_intent": {"type": "string", "enum": ["BUY", "RENT"]},
        "primary_location_id": {"anyOf": [{"type": "string", "format": "uuid"},
                                          {"type": "null"}]},
        "budget_max_dzd": {"type": "integer", "minimum": 0},
        "criteria": {"type": "array", "items": {"$ref": "#/components/schemas/RequestCriterion"}},
    },
}
ALL_OF = [{"if": {"properties": {"target": {"const": "REQUEST"}}, "required": ["target"]},
           "then": {"properties": {"payload": PAYLOAD}}}]


def _entry(**changes):
    entry = {"id": "TEST-ADD-ALL-OF", "decision": "a test entry, not an approved correction",
             "approved": "2026-10-31", "operation_id": OPERATION,
             "require": ["target", "payload"], "add_all_of": copy.deepcopy(ALL_OF),
             "frozen_defaults": {}, "rationale": "test", "runtime_rule": "test",
             "reference": "tests/test_contract_add_all_of.py"}
    entry.update(changes)
    return {k: v for k, v in entry.items() if v is not None}


def _corrections_with(tmp_path, entry) -> pathlib.Path:
    doc = yaml.safe_load(C.CORRECTIONS_PATH.read_text(encoding="utf-8"))
    doc["request_body_narrowings"] = list(doc.get("request_body_narrowings") or []) + [entry]
    path = tmp_path / "CONTRACT_CORRECTIONS.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return path


def _loaded(tmp_path, **changes):
    path = _corrections_with(tmp_path, _entry(**changes))
    entries = C.load_request_body_narrowings(path, C.load_contract())
    [entry] = [e for e in entries if e["id"] == "TEST-ADD-ALL-OF"]
    return entry


def _generate(monkeypatch, corrections: pathlib.Path) -> dict:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "generate_effective_contract", ROOT / "db" / "gate" / "generate_effective_contract.py")
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    monkeypatch.setattr(gen, "CORRECTIONS", corrections)
    text, _ = gen.build()
    return yaml.safe_load(text)


def _body(doc) -> dict:
    return doc["paths"][ROUTE[0]][ROUTE[1]]["requestBody"]["content"]["application/json"][
        "schema"]


# --- the operation-local copy ---------------------------------------------------------------

def test_the_effective_body_is_the_frozen_body_required_and_with_the_branches_appended(
        tmp_path):
    frozen = C.load_contract()
    before = copy.deepcopy(frozen)
    entry = _loaded(tmp_path)
    body = C.narrowed_body_schema(entry, frozen)
    assert body["allOf"][0] is not entry["add_all_of"][0], "a copy, not the entry's object"
    expected = copy.deepcopy(_body(before))
    expected["required"] = expected["required"] + ["target", "payload"]
    expected["allOf"] = ALL_OF
    assert body == expected
    assert frozen == before, "the frozen contract is unchanged"
    assert body is not _body(frozen) and body["allOf"] is not ALL_OF


def test_the_generator_writes_that_body_and_changes_no_other_operation(tmp_path, monkeypatch):
    baseline = _generate(monkeypatch, C.CORRECTIONS_PATH)
    narrowed = _generate(monkeypatch, _corrections_with(tmp_path, _entry()))
    assert _body(narrowed) == C.narrowed_body_schema(_loaded(tmp_path), C.load_contract())
    assert narrowed["paths"][ROUTE[0]][ROUTE[1]]["x-turab-correction"]["add-all-of"] == ALL_OF
    for route, item in baseline["paths"].items():
        for method, op in item.items():
            if (route, method) != ROUTE:
                assert narrowed["paths"][route][method] == op, (route, method)
    assert narrowed["components"] == baseline["components"]
    assert set(narrowed["paths"]) == set(baseline["paths"])


def test_no_approved_correction_uses_add_all_of():
    """CORRECTION-009 is not activated by this step (review of 0a78e91)."""
    doc = yaml.safe_load(C.CORRECTIONS_PATH.read_text(encoding="utf-8"))
    assert not [e["id"] for e in doc.get("request_body_narrowings") or ()
                if "add_all_of" in e]
    assert C.effective_request_body(OPERATION) is None


# --- the effective contract and the runtime refuse the same payload -------------------------

def _judge(schema, value, components) -> bool:
    """An independent verdict, written here for the subset the loader admits."""
    if "$ref" in schema:
        if not _judge(components[schema["$ref"].rsplit("/", 1)[1]], value, components):
            return False
    if "anyOf" in schema and not any(_judge(s, value, components) for s in schema["anyOf"]):
        return False
    for branch in schema.get("allOf", ()):
        if not _judge(branch, value, components):
            return False
    if "if" in schema and _judge(schema["if"], value, components):
        if not _judge(schema["then"], value, components):
            return False
    if "type" in schema:
        kinds = {"object": isinstance(value, dict), "array": isinstance(value, list),
                 "string": isinstance(value, str), "null": value is None,
                 "boolean": isinstance(value, bool),
                 "integer": isinstance(value, int) and not isinstance(value, bool),
                 "number": isinstance(value, (int, float)) and not isinstance(value, bool)}
        declared = schema["type"]
        if not any(kinds[t] for t in (declared if isinstance(declared, list) else [declared])):
            return False
    same = (lambda a, b: a == b and type(a) is type(b))
    if "enum" in schema and not any(same(value, e) for e in schema["enum"]):
        return False
    if "const" in schema and not same(value, schema["const"]):
        return False
    if "minimum" in schema and isinstance(value, (int, float)) and not isinstance(value, bool) \
            and value < schema["minimum"]:
        return False
    if schema.get("format") == "uuid" and isinstance(value, str):
        try:
            uuid.UUID(value)
        except ValueError:
            return False
    if schema.get("format") == "date-time" and isinstance(value, str):
        try:
            datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return False
    if isinstance(value, dict):
        if not set(schema.get("required", ())) <= set(value):
            return False
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False and set(value) - set(properties):
            return False
        if not all(_judge(properties[k], v, components) for k, v in value.items()
                   if k in properties):
            return False
    if isinstance(value, list) and "items" in schema:
        if not all(_judge(schema["items"], v, components) for v in value):
            return False
    return True


P, C1 = str(uuid.uuid4()), str(uuid.uuid4())
GOOD = {"intent": "EXPLORING", "transaction_intent": "BUY"}
CRITERION = {"criterion_code": "ROOMS", "importance": "REQUIRED", "operator": "GTE", "value": 3}
BODIES = [
    ("REQUEST, a minimal payload", True,
     {"party_id": P, "consent_id": C1, "target": "REQUEST", "payload": GOOD}),
    ("REQUEST, RENT", True,
     {"party_id": P, "consent_id": C1, "target": "REQUEST",
      "payload": {**GOOD, "transaction_intent": "RENT"}}),
    ("REQUEST, every field", True,
     {"party_id": P, "consent_id": C1, "target": "REQUEST",
      "payload": {**GOOD, "primary_location_id": None, "budget_max_dzd": 0,
                  "criteria": [CRITERION]}}),
    ("target absent", False, {"party_id": P, "consent_id": C1, "payload": GOOD}),
    ("payload absent", False, {"party_id": P, "consent_id": C1, "target": "REQUEST"}),
    ("payload without intent", False,
     {"party_id": P, "consent_id": C1, "target": "REQUEST",
      "payload": {"transaction_intent": "BUY"}}),
    ("payload carries party_id", False,
     {"party_id": P, "consent_id": C1, "target": "REQUEST", "payload": {**GOOD, "party_id": P}}),
    ("payload carries management_mode", False,
     {"party_id": P, "consent_id": C1, "target": "REQUEST",
      "payload": {**GOOD, "management_mode": "ASSISTED"}}),
    ("payload, an unknown intent", False,
     {"party_id": P, "consent_id": C1, "target": "REQUEST",
      "payload": {**GOOD, "intent": "LATER"}}),
    ("payload, a negative budget", False,
     {"party_id": P, "consent_id": C1, "target": "REQUEST",
      "payload": {**GOOD, "budget_max_dzd": -1}}),
    ("payload, a budget given as true", False,
     {"party_id": P, "consent_id": C1, "target": "REQUEST",
      "payload": {**GOOD, "budget_max_dzd": True}}),
    ("payload, a location not a uuid", False,
     {"party_id": P, "consent_id": C1, "target": "REQUEST",
      "payload": {**GOOD, "primary_location_id": "nowhere"}}),
    ("payload, a criterion without its code", False,
     {"party_id": P, "consent_id": C1, "target": "REQUEST",
      "payload": {**GOOD, "criteria": [{k: v for k, v in CRITERION.items()
                                        if k != "criterion_code"}]}}),
    ("payload, criteria not a list", False,
     {"party_id": P, "consent_id": C1, "target": "REQUEST",
      "payload": {**GOOD, "criteria": CRITERION}}),
    ("PROPERTY, any payload: not narrowed here", True,
     {"party_id": P, "consent_id": C1, "target": "PROPERTY", "payload": {"anything": 1}}),
    ("target unknown", False,
     {"party_id": P, "consent_id": C1, "target": "OFFER", "payload": GOOD}),
    ("party_id not a uuid", False,
     {"party_id": "x", "consent_id": C1, "target": "REQUEST", "payload": GOOD}),
    # The frozen body declares no `additionalProperties: false`: the contract
    # admits an unknown top-level key, and a narrowing of the payload does not
    # change that.
    ("an unknown top-level key: the frozen body admits it", True,
     {"party_id": P, "consent_id": C1, "target": "REQUEST", "payload": GOOD, "x": 1}),
]


@pytest.fixture(scope="module")
def both(tmp_path_factory):
    """The body the GENERATOR writes, and the body the LOADER gives the
    runtime, from the same test entry: generated once for the module."""
    tmp = tmp_path_factory.mktemp("add-all-of")
    with pytest.MonkeyPatch.context() as mp:
        generated = _generate(mp, _corrections_with(tmp, _entry()))
    return generated, C.narrowed_body_schema(_loaded(tmp), C.load_contract())


@pytest.mark.parametrize("label, expected, body", BODIES, ids=[b[0] for b in BODIES])
def test_the_effective_contract_and_the_runtime_refuse_the_same_payload(both, label,
                                                                       expected, body):
    generated, loaded = both
    by_contract = _judge(_body(generated), body, generated["components"]["schemas"])
    runtime = C.body_violations(loaded, body, C.load_contract())
    assert by_contract is expected, label
    assert (runtime == []) is expected, (label, runtime)


def test_a_violation_names_where_it_is_and_never_the_value():
    schema = C.narrowed_body_schema(_entry(), C.load_contract())
    body = {"party_id": P, "consent_id": C1, "target": "REQUEST",
            "payload": {**GOOD, "intent": "SECRET-VALUE-q3"}}
    violations = C.body_violations(schema, body, C.load_contract())
    assert violations and all("payload.intent" in v for v in violations)
    assert not any("SECRET-VALUE-q3" in v for v in violations)


def test_the_runtime_refuses_to_judge_a_keyword_it_does_not_read():
    """Fail closed: a schema carrying a keyword the validator does not read is
    not validated as if the keyword were absent."""
    with pytest.raises(C.ContractError, match="pattern"):
        C.body_violations({"type": "string", "pattern": "^a"}, "b", C.load_contract())


# --- invalid correction input is refused ----------------------------------------------------

INVALID = [
    ("not a list", {"type": "object"}, "a non-empty list"),
    ("an empty list", [], "a non-empty list"),
    ("a branch that is not an object", ["x"], "a non-empty list"),
    ("an unread keyword", [{"properties": {"payload": {"pattern": "^a"}}}], "pattern"),
    ("$defs", [{"$defs": {"x": {"type": "object"}}}], r"\$defs"),
    ("a $ref outside the components", [{"$ref": "#/paths/x"}], "components"),
    ("a $ref to no component", [{"$ref": "#/components/schemas/NoSuchThing"}], "NoSuchThing"),
    ("a $ref to a component with an unread keyword",
     [{"properties": {"payload": {"$ref": "#/components/schemas/PhoneInput"}}}], "pattern"),
    ("a format the validator does not assert", [{"properties": {"payload": {"format": "uri"}}}],
     "uri"),
    ("additionalProperties true", [{"additionalProperties": True}], "additionalProperties"),
    ("additionalProperties as a schema", [{"additionalProperties": {"type": "string"}}],
     "additionalProperties"),
    ("then without if", [{"then": {"required": ["target"]}}], "then"),
    ("if without then", [{"if": {"required": ["target"]}}], "if"),
    ("an unknown type", [{"type": "date"}], "date"),
]


@pytest.mark.parametrize("label, value, message", INVALID, ids=[i[0] for i in INVALID])
def test_invalid_add_all_of_is_refused(tmp_path, label, value, message):
    with pytest.raises(C.ContractError, match=message):
        _loaded(tmp_path, add_all_of=value)
