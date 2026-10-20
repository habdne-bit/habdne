"""CORRECTION-005: a task completion names one of the four task outcome codes.

Ref: `docs/contract/CORRECTION-005-task-outcome-code.md`; decision G6-8 (ii)
(a) (Slice 6 plan, approved in the review of bd54216); plan §5.2 and F6-19
(the loader's extension); migration `0007` part B.

What this file proves:
- the effective contract narrows the operation's body as §5.2 writes it,
  through an operation-local copy, and leaves the frozen component as
  published;
- the enum is the ACTIVE codes of category TASK_OUTCOME in the database, and
  the route reads the same list;
- the extended loader refuses every shape that would not be a narrowing, and
  the application and the generator refuse to run on one.

The bodies sent through the effective schema and the route together are in
`tests/test_slice6_step2.py`.
"""
from __future__ import annotations

import copy
import pathlib

import pytest
import yaml
from sqlalchemy import text

from turab.auth import contract as contract_module
from turab.auth.contract import (
    CORRECTIONS_PATH,
    ContractError,
    build_policy_table,
    effective_request_body,
    load_contract,
    load_request_body_narrowings,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
EFFECTIVE = ROOT / "docs" / "api" / "openapi_effective_v0.2.3.yaml"
COMPLETE = ("/tasks/{task_id}/complete", "post")
REF = "#/components/schemas/TaskCompletionInput"
CODES = ["TASK_INFORMATION_OBTAINED", "TASK_INFORMATION_UNAVAILABLE",
         "TASK_PARTY_UNREACHABLE", "TASK_NO_LONGER_NEEDED"]


def _op(doc):
    return doc["paths"][COMPLETE[0]][COMPLETE[1]]


def _body(doc):
    return _op(doc)["requestBody"]["content"]["application/json"]["schema"]


def _entry(doc):
    [entry] = [e for e in doc["request_body_narrowings"] if e["id"] == "CORRECTION-005"]
    return entry


def _with(tmp_path, mutate) -> pathlib.Path:
    """A copy of the real corrections file with CORRECTION-005 mutated."""
    doc = yaml.safe_load(CORRECTIONS_PATH.read_text(encoding="utf-8"))
    mutate(doc, _entry(doc))
    path = tmp_path / "CONTRACT_CORRECTIONS.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


# --- what the correction does ----------------------------------------------------

def test_the_effective_body_is_the_narrowed_copy_of_the_component():
    effective = yaml.safe_load(EFFECTIVE.read_text(encoding="utf-8"))
    assert _body(effective) == {
        "type": "object", "additionalProperties": False,
        "properties": {
            "outcome_code": {"type": "string", "enum": CODES},
            "note": {"type": ["string", "null"]},
            "evidence_observation_id": {"type": ["string", "null"], "format": "uuid"},
        },
        "required": ["outcome_code"],
    }
    marker = _op(effective)["x-turab-correction"]
    assert (marker["id"], marker["kind"]) == ("CORRECTION-005", "REQUEST_BODY_NARROWING")
    assert marker["frozen-body-ref"] == REF
    assert (marker["frozen-required"], marker["frozen-defaults"]) == ([], {})
    assert marker["non-null"] == ["outcome_code"]
    assert marker["enum"] == {"outcome_code": CODES}
    assert (ROOT / marker["reference"]).exists()


def test_the_frozen_component_is_unchanged_in_the_effective_contract():
    effective = yaml.safe_load(EFFECTIVE.read_text(encoding="utf-8"))
    frozen = load_contract()
    assert (effective["components"]["schemas"]["TaskCompletionInput"]
            == frozen["components"]["schemas"]["TaskCompletionInput"])
    component = frozen["components"]["schemas"]["TaskCompletionInput"]
    assert "required" not in component
    assert component["properties"]["outcome_code"] == {"type": ["string", "null"]}


def test_the_frozen_body_is_a_reference_this_operation_alone_uses():
    """The condition under which the loader accepts it (F6-19), measured on
    the frozen text: one `$ref` to the component, this operation's body."""
    frozen = load_contract()
    assert _body(frozen) == {"$ref": REF}
    raw = (ROOT / "docs/handoff/05_API/openapi_v0.2.3.yaml").read_text(encoding="utf-8")
    assert raw.count(f"$ref: '{REF}'") == 1


def test_the_roles_are_untouched():
    policy = build_policy_table().get("postTasksTaskIdComplete")
    assert {r.value for r in policy.roles} == {"ADMIN", "OPERATOR", "REVIEWER"}
    assert policy.requires_idempotency


def test_the_enum_is_the_active_task_outcome_codes_of_the_database(engine):
    with engine.connect() as conn:
        active = [r[0] for r in conn.execute(text(
            "SELECT code FROM turab.reason_codes WHERE category = 'TASK_OUTCOME' AND active "
            "ORDER BY code"))]
    enum = effective_request_body("postTasksTaskIdComplete")["properties"]["outcome_code"][
        "enum"]
    assert sorted(enum) == active == sorted(CODES)


def test_the_route_reads_the_effective_enum():
    from turab.api.routes import tasks as task_routes

    assert task_routes.OUTCOME_CODES == tuple(CODES)


# --- the extended loader refuses every other shape (F6-19) --------------------------

def _set_type(field, value):
    def mutate(contract):
        contract["components"]["schemas"]["TaskCompletionInput"]["properties"][field][
            "type"] = value
    return mutate


@pytest.mark.parametrize("label, mutate, message", [
    ("non_null empty", lambda d, e: e.update(non_null=[]), "non-empty list"),
    ("non_null not a list", lambda d, e: e.update(non_null="outcome_code"),
     "non-empty list"),
    ("non_null repeated", lambda d, e: e.update(non_null=["outcome_code", "outcome_code"]),
     "more than once in non_null"),
    ("non_null of a field the body does not declare",
     lambda d, e: e.update(non_null=["no_such_field"]), "not a property"),
    ("an enum of a field the body does not declare",
     lambda d, e: e.update(enum={"no_such_field": ["A"]}), "not a property"),
    ("an empty enum", lambda d, e: e.update(enum={"outcome_code": []}), "is empty"),
    ("an enum that is not a mapping", lambda d, e: e.update(enum=["A"]),
     "map fields to their values"),
    ("an enum repeating a value",
     lambda d, e: e.update(enum={"outcome_code": ["TASK_NO_LONGER_NEEDED"] * 2}),
     "repeats a value"),
    ("an enum value of another type", lambda d, e: e.update(enum={"outcome_code": [5]}),
     "not of its type"),
    ("an enum value that is a boolean",
     lambda d, e: e.update(enum={"outcome_code": [True]}), "not of its type"),
    ("an unknown key", lambda d, e: e.update(pattern={"outcome_code": "^T"}), "unknown key"),
    ("requiring nothing", lambda d, e: e.update(require=[]), "requires nothing"),
    ("a stale frozen default",
     lambda d, e: e.update(frozen_defaults={"outcome_code": "TASK_NO_LONGER_NEEDED"}),
     "stale"),
])
def test_the_extended_loader_refuses(tmp_path, label, mutate, message):
    with pytest.raises(ContractError, match=message):
        load_request_body_narrowings(_with(tmp_path, mutate))


@pytest.mark.parametrize("label, mutate, message", [
    ("non_null of a field whose type admits no null", _set_type("outcome_code", "string"),
     "no type list admitting null"),
    ("non_null of a field that admits null only", _set_type("outcome_code", ["null"]),
     "admits null only"),
])
def test_non_null_is_refused_where_there_is_nothing_to_narrow(label, mutate, message):
    contract = copy.deepcopy(load_contract())
    mutate(contract)
    with pytest.raises(ContractError, match=message):
        load_request_body_narrowings(contract=contract)


def test_an_enum_wider_than_a_frozen_enum_is_refused():
    contract = copy.deepcopy(load_contract())
    contract["components"]["schemas"]["TaskCompletionInput"]["properties"]["outcome_code"][
        "enum"] = ["TASK_INFORMATION_OBTAINED"]
    with pytest.raises(ContractError, match="only remove values"):
        load_request_body_narrowings(contract=contract)


def test_a_component_another_operation_also_uses_is_refused():
    """Narrowing a shared component would narrow the other operation too."""
    contract = copy.deepcopy(load_contract())
    other = contract["paths"]["/matches/{match_id}/review"]["post"]
    other["requestBody"]["content"]["application/json"]["schema"] = {"$ref": REF}
    with pytest.raises(ContractError, match="referenced 2 times"):
        load_request_body_narrowings(contract=contract)


def test_a_reference_with_siblings_is_refused():
    contract = copy.deepcopy(load_contract())
    _body(contract)["description"] = "a sibling of the $ref"
    with pytest.raises(ContractError, match="not a plain reference"):
        load_request_body_narrowings(contract=contract)


def test_the_application_refuses_to_start_on_a_bad_narrowing(tmp_path, monkeypatch):
    path = _with(tmp_path, lambda d, e: e.update(enum={"outcome_code": [5]}))
    monkeypatch.setattr(contract_module, "CORRECTIONS_PATH", path)
    with pytest.raises(ContractError, match="not of its type"):
        build_policy_table()


def test_the_effective_contract_is_not_generated_from_a_bad_narrowing(tmp_path,
                                                                      monkeypatch):
    import importlib
    import sys

    sys.path.insert(0, str(ROOT / "db" / "gate"))
    generator = importlib.import_module("generate_effective_contract")
    monkeypatch.setattr(generator, "CORRECTIONS",
                        _with(tmp_path, lambda d, e: e.update(non_null=["no_such_field"])))
    before = EFFECTIVE.read_bytes()
    with pytest.raises(ContractError, match="not a property"):
        generator.build()
    assert EFFECTIVE.read_bytes() == before


def test_the_generator_and_the_runtime_share_one_transformation():
    """The generator writes `narrowed_body_schema`'s output; it has no
    transformation of its own to drift (plan §5.2: one validation)."""
    source = (ROOT / "db" / "gate" / "generate_effective_contract.py").read_text(
        encoding="utf-8")
    assert "narrowed_body_schema(entry, doc)" in source
    assert 'schema["required"] = frozen_required' not in source


def test_the_runtime_body_is_the_committed_effective_body():
    """The route reads `effective_request_body`; readers read the committed
    effective contract. The two must be one schema."""
    effective = yaml.safe_load(EFFECTIVE.read_text(encoding="utf-8"))
    assert effective_request_body("postTasksTaskIdComplete") == _body(effective)
