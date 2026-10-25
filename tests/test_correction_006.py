"""CORRECTION-006: a staff-created thread names its party.

Ref: `docs/contract/CORRECTION-006-thread-party-required.md`; decision G7-7 (a)
(Slice 7 plan; direction approved in the review of 4aed49b, the method in the
review of 0f423d2); `API_CONTRACTS_v0.2.md` §4.12; M5
(`SLICE7-PLAN-MEASUREMENTS.txt`).

What this file proves, as the review of 0f423d2 asked ("the text, the
effective contract, and the test that the two agree"):
- the effective contract narrows the operation's body exactly as the entry
  says, through an operation-local copy, and leaves the frozen component as
  published;
- the route refuses exactly what the effective schema refuses, body for body;
- the loader's extension to an `anyOf` with a null branch refuses every
  shape that would not be a narrowing.
"""
from __future__ import annotations

import copy
import pathlib
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.test_slice4_step7 import _one
from turab.auth.contract import (
    CORRECTIONS_PATH,
    ContractError,
    effective_request_body,
    load_contract,
    load_request_body_narrowings,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
EFFECTIVE = ROOT / "docs" / "api" / "openapi_effective_v0.2.3.yaml"
THREADS = ("/communication/threads", "post")
COMPONENT = "CommunicationThreadCreate"
REF = f"#/components/schemas/{COMPONENT}"


def _body_of(doc):
    return doc["paths"][THREADS[0]][THREADS[1]]["requestBody"]["content"][
        "application/json"]["schema"]


def _effective():
    return yaml.safe_load(EFFECTIVE.read_text(encoding="utf-8"))


# --- the text and the effective contract agree --------------------------------------

def test_the_entry_is_exactly_the_narrowing_of_party_id():
    doc = yaml.safe_load(CORRECTIONS_PATH.read_text(encoding="utf-8"))
    [entry] = [e for e in doc["request_body_narrowings"] if e["id"] == "CORRECTION-006"]
    assert (entry["operation_id"], entry["require"], entry["non_null"],
            entry["frozen_defaults"]) == ("postCommunicationThreads", ["party_id"],
                                          ["party_id"], {})
    assert "enum" not in entry
    # Approved in the review of f7e5297; submitted until then without a date.
    assert entry["approved"] == "2026-10-25" and "review of f7e5297" in entry["decision"]


def test_the_effective_body_is_the_frozen_component_with_party_id_required_and_not_null():
    """The expectation is built here from the FROZEN component, independently
    of `narrowed_body_schema`: `party_id` added to `required`, and its
    `{type: 'null'}` branch removed, leaving the uuid string. Nothing else."""
    frozen = load_contract()
    expected = copy.deepcopy(frozen["components"]["schemas"][COMPONENT])
    expected["required"] = ["channel", "party_id"]
    assert expected["properties"]["party_id"] == {
        "anyOf": [{"type": "string", "format": "uuid"}, {"type": "null"}]}
    expected["properties"]["party_id"] = {"type": "string", "format": "uuid"}
    assert _body_of(_effective()) == expected
    assert effective_request_body("postCommunicationThreads") == expected


def test_the_frozen_component_is_unchanged_and_used_by_this_operation_alone():
    frozen, effective = load_contract(), _effective()
    assert effective["components"]["schemas"][COMPONENT] == \
        frozen["components"]["schemas"][COMPONENT]
    assert _body_of(frozen) == {"$ref": REF}
    text = (ROOT / "docs" / "handoff" / "05_API" / "openapi_v0.2.3.yaml").read_text(
        encoding="utf-8")
    assert text.count(REF) == 1


def test_the_roles_are_untouched():
    frozen, effective = load_contract(), _effective()
    assert effective["paths"][THREADS[0]][THREADS[1]]["x-roles"] == \
        frozen["paths"][THREADS[0]][THREADS[1]]["x-roles"] == ["ADMIN", "OPERATOR"]


def test_the_annotation_names_the_correction_and_its_approval():
    note = _effective()["paths"][THREADS[0]][THREADS[1]]["x-turab-correction"]
    assert (note["id"], note["kind"], note["non-null"], note["frozen-body-ref"]) == (
        "CORRECTION-006", "REQUEST_BODY_NARROWING", ["party_id"], REF)
    assert "review of f7e5297" in note["decision"] and note["approved"] == "2026-10-25"


# --- the route refuses exactly what the effective schema refuses --------------------

_KEYWORDS = {"type", "required", "properties", "additionalProperties", "enum", "format",
             "anyOf"}


def _keywords(schema):
    found = set()
    if isinstance(schema, dict):
        found |= set(schema)
        for key, value in schema.items():
            if key == "properties":
                for sub in value.values():
                    found |= _keywords(sub)
            elif key == "anyOf":
                for sub in value:
                    found |= _keywords(sub)
    return found


def test_the_effective_body_uses_only_the_keywords_the_judge_below_reads():
    schema = effective_request_body("postCommunicationThreads")
    assert schema is not None, "the operation is narrowed"
    assert _keywords(schema) <= _KEYWORDS


def _accepts(schema, value) -> bool:
    """The effective schema's verdict, for exactly the keywords it uses."""
    if "anyOf" in schema:
        return any(_accepts(s, value) for s in schema["anyOf"])
    kinds = {"string": isinstance(value, str), "null": value is None,
             "object": isinstance(value, dict)}
    declared = schema["type"]
    if not any(kinds[t] for t in (declared if isinstance(declared, list) else [declared])):
        return False
    if "enum" in schema and value not in schema["enum"]:
        return False
    if schema.get("format") == "uuid" and isinstance(value, str):
        try:
            uuid.UUID(value)
        except ValueError:
            return False
    if isinstance(value, dict):
        if not set(schema.get("required", ())) <= set(value):
            return False
        if schema.get("additionalProperties") is False and \
                set(value) - set(schema["properties"]):
            return False
        return all(_accepts(schema["properties"][k], v) for k, v in value.items())
    return True


def _party(engine):
    return str(_one(engine, "INSERT INTO turab.parties (kind) VALUES ('PERSON') "
                            "RETURNING party_id"))


BODIES = [
    ("party absent", {"channel": "PHONE"}),
    ("party null", {"channel": "PHONE", "party_id": None}),
    ("party not a uuid", {"channel": "PHONE", "party_id": "not-a-uuid"}),
    ("party a number", {"channel": "PHONE", "party_id": 5}),
    ("party given", {"channel": "PHONE", "party_id": "PARTY"}),
    ("channel unknown", {"channel": "TELEGRAM", "party_id": "PARTY"}),
    ("channel absent", {"party_id": "PARTY"}),
    ("an extra key", {"channel": "PHONE", "party_id": "PARTY", "x": 1}),
    ("reference null", {"channel": "PHONE", "party_id": "PARTY",
                        "external_thread_ref": None}),
    ("reference given", {"channel": "PHONE", "party_id": "PARTY",
                         "external_thread_ref": "free text"}),
    ("request null", {"channel": "PHONE", "party_id": "PARTY", "request_id": None}),
    ("opportunity not a uuid", {"channel": "PHONE", "party_id": "PARTY",
                                "opportunity_id": "x"}),
]


@pytest.mark.parametrize("label, body", BODIES, ids=[b[0] for b in BODIES])
def test_the_route_refuses_exactly_what_the_effective_schema_refuses(engine, ids, label,
                                                                    body):
    from turab.app import create_app

    party = _party(engine)
    body = {k: (party if v == "PARTY" else v) for k, v in body.items()}
    expected = _accepts(effective_request_body("postCommunicationThreads"), body)
    before = _one(engine, "SELECT count(*) FROM turab.communication_threads")
    with TestClient(create_app(engine=engine)) as c:
        r = c.post("/communication/threads", json=body,
                   headers={"Authorization": f"Bearer {ids.ACC_OPERATOR}",
                            "Idempotency-Key": str(uuid.uuid4())})
    assert (r.status_code == 201) is expected, (label, r.status_code, r.text)
    if not expected:
        assert (r.status_code, r.json()["code"]) == (422, "VALIDATION_FAILED")
        assert _one(engine, "SELECT count(*) FROM turab.communication_threads") == before


# --- the loader's extension: anyOf with a null branch --------------------------------

def _party_id_as(value):
    contract = copy.deepcopy(load_contract())
    contract["components"]["schemas"][COMPONENT]["properties"]["party_id"] = value
    return contract


@pytest.mark.parametrize("label, field, message", [
    ("two null branches",
     {"anyOf": [{"type": "string"}, {"type": "null"}, {"type": "null"}]},
     "2 null branches"),
    ("no null branch", {"anyOf": [{"type": "string"}, {"type": "integer"}]},
     "0 null branches"),
    ("null only", {"anyOf": [{"type": "null"}]}, "admits null only"),
    ("another branch whose type list admits null",
     {"anyOf": [{"type": ["string", "null"]}, {"type": "null"}]}, "may admit null"),
    ("another branch with no type", {"anyOf": [{"format": "uuid"}, {"type": "null"}]},
     "may admit null"),
    ("another branch by reference",
     {"anyOf": [{"$ref": "#/components/schemas/Problem"}, {"type": "null"}]},
     "may admit null"),
    ("another branch with its own combinator",
     {"anyOf": [{"anyOf": [{"type": "string"}, {"type": "null"}]}, {"type": "null"}]},
     "may admit null"),
    # The first trial mutation run showed the two cases above caught by the
    # no-type fallback, not by the reference or combinator check (K6
    # survived). Each branch below carries a type, so only that check can
    # refuse it.
    ("another branch by reference, with a type",
     {"anyOf": [{"$ref": "#/components/schemas/Problem", "type": "string"},
                {"type": "null"}]}, "may admit null"),
    ("another branch with its own combinator, with a type",
     {"anyOf": [{"type": "string", "anyOf": [{"type": "string"}, {"type": "null"}]},
                {"type": "null"}]}, "may admit null"),
    ("a type beside the anyOf",
     {"type": ["string", "null"], "anyOf": [{"type": "string"}, {"type": "null"}]},
     "declares a type beside"),
])
def test_the_anyof_extension_refuses_what_would_not_narrow(label, field, message):
    with pytest.raises(ContractError, match=message):
        load_request_body_narrowings(contract=_party_id_as(field))


def test_the_anyof_extension_keeps_the_fields_other_keywords_and_several_branches():
    """Two non-null branches stay an `anyOf`; the field's own keywords are
    kept. Built on a copy, the committed contract untouched."""
    from turab.auth.contract import narrowed_body_schema

    contract = _party_id_as({"description": "d", "anyOf": [
        {"type": "string", "format": "uuid"}, {"type": "integer"}, {"type": "null"}]})
    [entry] = [e for e in load_request_body_narrowings(contract=contract)
               if e["id"] == "CORRECTION-006"]
    assert narrowed_body_schema(entry, contract)["properties"]["party_id"] == {
        "description": "d", "anyOf": [{"type": "string", "format": "uuid"},
                                      {"type": "integer"}]}
