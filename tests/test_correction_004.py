"""CORRECTION-004: `matching_policy_version` is required on the matching run.

Ref: `docs/contract/CORRECTION-004-matching-policy-version.md`; decision
G4-1 (Slice 4 plan revision 2, approved for step 1);
`docs/gate/evidence/SLICE4-PLAN-MEASUREMENTS.txt` §A.

What this file proves in step 1:
- the effective contract requires the field and no longer carries the
  default that names no policy;
- the frozen package is what the correction says it was;
- the validator refuses every way a "narrowing" could be stale or become
  something else, and the application refuses to start on one.

What it does NOT prove: the runtime rule (the value must be the ACTIVE
policy's version). The route that enforces it is Slice 4 step 7, and its
tests come with it.
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
    load_contract,
    load_request_body_narrowings,
)

ROOT = pathlib.Path(__file__).resolve().parents[1]
EFFECTIVE = ROOT / "docs" / "api" / "openapi_effective_v0.2.3.yaml"
RUN = ("/requests/{request_id}/matching/run", "post")


def _body_schema(doc):
    return doc["paths"][RUN[0]][RUN[1]]["requestBody"]["content"]["application/json"]["schema"]


def _with(tmp_path, mutate) -> pathlib.Path:
    """A copy of the real corrections file with its narrowing entry mutated."""
    doc = yaml.safe_load(CORRECTIONS_PATH.read_text(encoding="utf-8"))
    mutate(doc, doc["request_body_narrowings"][0])
    path = tmp_path / "CONTRACT_CORRECTIONS.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return path


# --- what the correction does ----------------------------------------------------

def test_the_effective_contract_requires_the_policy_version_without_a_default():
    effective = yaml.safe_load(EFFECTIVE.read_text(encoding="utf-8"))
    schema = _body_schema(effective)
    assert schema["required"] == ["matching_policy_version"]
    assert "default" not in schema["properties"]["matching_policy_version"]
    assert schema["properties"]["property_ids"] == _body_schema(load_contract())["properties"][
        "property_ids"], "the other field is untouched"
    marker = effective["paths"][RUN[0]][RUN[1]]["x-turab-correction"]
    assert (marker["id"], marker["kind"]) == ("CORRECTION-004", "REQUEST_BODY_NARROWING")
    assert marker["frozen-defaults"] == {"matching_policy_version": "0.1.0"}
    assert marker["frozen-required"] == []
    assert "ACTIVE matching policy" in marker["runtime-rule"]
    assert (ROOT / marker["reference"]).exists()


def test_the_frozen_package_is_what_the_correction_records():
    schema = _body_schema(load_contract())
    assert "required" not in schema
    assert schema["properties"]["matching_policy_version"]["default"] == "0.1.0"


def test_the_frozen_default_names_no_policy_the_seed_creates(engine):
    """The reason for the correction, read from the database the suite builds
    from the frozen schema and seed."""
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT version, active FROM turab.matching_policies "
                                 "ORDER BY version")).all()
    assert [tuple(r) for r in rows] == [("0.2.0", True)]


def test_the_roles_are_untouched():
    table = build_policy_table()
    policy = table.get("postRequestsRequestIdMatchingRun")
    assert {r.value for r in policy.roles} == {"ADMIN", "OPERATOR", "REVIEWER"}


# --- the validator refuses every other shape ---------------------------------------

@pytest.mark.parametrize("label, mutate, message", [
    ("a stale frozen default",
     lambda d, e: e.update(frozen_defaults={"matching_policy_version": "0.2.0"}), "stale"),
    ("a default left unrecorded",
     lambda d, e: e.update(frozen_defaults={}), "stale"),
    ("a field the body does not declare",
     lambda d, e: e.update(require=["no_such_field"]), "not a property"),
    ("requiring nothing",
     lambda d, e: e.update(require=[]), "requires nothing"),
    ("a key that is not a narrowing",
     lambda d, e: e.update(unrequire=["property_ids"]), "unknown key"),
    ("no decision",
     lambda d, e: e.pop("decision"), "names no decision"),
    ("an id another correction uses",
     lambda d, e: e.update(id="CORRECTION-001"), "duplicated id"),
    ("an operation that is also role-corrected",
     lambda d, e: e.update(operation_id="postParties"), "already role-corrected"),
    ("an operation the frozen contract does not have",
     lambda d, e: e.update(operation_id="postNothing"), "not in the frozen contract"),
])
def test_the_validator_refuses(tmp_path, label, mutate, message):
    with pytest.raises(ContractError, match=message):
        load_request_body_narrowings(_with(tmp_path, mutate))


def test_a_field_the_package_already_requires_is_refused(tmp_path):
    """Nothing to narrow is not a narrowing. Shown on a copy of the package in
    which the field is already required."""
    contract = copy.deepcopy(load_contract())
    _body_schema(contract)["required"] = ["matching_policy_version"]
    with pytest.raises(ContractError, match="already required"):
        load_request_body_narrowings(contract=contract)


def test_the_application_refuses_to_start_on_a_stale_narrowing(tmp_path, monkeypatch):
    path = _with(tmp_path, lambda d, e: e.update(frozen_defaults={}))
    monkeypatch.setattr(contract_module, "CORRECTIONS_PATH", path)
    with pytest.raises(ContractError, match="stale"):
        build_policy_table()


# --- review of aad9f34: two narrowings of ONE operation -----------------------------
#
# The reviewer added a second narrowing with another id that required
# `property_ids` on the same operation. On aad9f34 the loader accepted both,
# the application started, and the generated contract required ONLY
# `property_ids`: `matching_policy_version` was optional again, with its
# default `0.1.0` back, and the marker named the second correction alone.
# Reproduced before the fix: docs/gate/evidence/SLICE4-STEP1-DUPLICATE-NARROWING-BEFORE-FIX.txt.

def _second_narrowing(doc, entry):
    doc["request_body_narrowings"].append({
        "id": "CORRECTION-099", "decision": "review experiment",
        "approved": "2026-09-26", "operation_id": entry["operation_id"],
        "require": ["property_ids"], "frozen_defaults": {},
        "rationale": "experiment", "runtime_rule": "experiment"})


def test_a_second_narrowing_of_the_same_operation_is_refused_by_the_loader(tmp_path):
    with pytest.raises(ContractError, match="already narrowed by CORRECTION-004"):
        load_request_body_narrowings(_with(tmp_path, _second_narrowing))


def test_the_application_refuses_to_start_on_a_second_narrowing(tmp_path, monkeypatch):
    monkeypatch.setattr(contract_module, "CORRECTIONS_PATH", _with(tmp_path, _second_narrowing))
    with pytest.raises(ContractError, match="one narrowing per operation"):
        build_policy_table()


def test_the_effective_contract_is_not_generated_from_a_second_narrowing(tmp_path, monkeypatch):
    """The generator is run on the bad file. It must stop, and nothing may be
    written in place of the effective contract."""
    import importlib
    import sys

    sys.path.insert(0, str(ROOT / "db" / "gate"))
    generator = importlib.import_module("generate_effective_contract")
    monkeypatch.setattr(generator, "CORRECTIONS", _with(tmp_path, _second_narrowing))
    before = EFFECTIVE.read_bytes()
    with pytest.raises(ContractError, match="one narrowing per operation"):
        generator.build()
    assert EFFECTIVE.read_bytes() == before


def test_the_generator_refuses_an_overwrite_even_if_the_loader_let_it_through(tmp_path,
                                                                            monkeypatch):
    """Defence in depth: the loader is replaced by one that returns the two
    entries unchecked. The generator's own guard must still stop."""
    import importlib
    import sys

    sys.path.insert(0, str(ROOT / "db" / "gate"))
    generator = importlib.import_module("generate_effective_contract")
    doc = yaml.safe_load(_with(tmp_path, _second_narrowing).read_text(encoding="utf-8"))
    monkeypatch.setattr(contract_module, "load_request_body_narrowings",
                        lambda *a, **k: tuple(doc["request_body_narrowings"]))
    with pytest.raises(SystemExit, match="silently replace"):
        generator.build()


def test_a_field_listed_twice_in_require_is_refused(tmp_path):
    """Otherwise the effective contract carries `required` with a repeated
    field (measured on aad9f34)."""
    path = _with(tmp_path, lambda d, e: e.update(
        require=["matching_policy_version", "matching_policy_version"]))
    with pytest.raises(ContractError, match="listed more than once"):
        load_request_body_narrowings(path)
