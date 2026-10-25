"""CORRECTION-007 and CORRECTION-008: the webhook's two added error responses.

Ref: `docs/contract/CORRECTION-007-webhook-processing-failed.md`,
`docs/contract/CORRECTION-008-webhook-not-ready.md`; Slice 7 plan §5.2 and
G7-17 (ii) and (vi), decided in the review of bf1fe3d (`response_additions`,
unique per (operation, HTTP status)); `API_CONTRACTS_v0.2.md` §4.12.

What this file proves, as G7-17 (vi) asks ("the two corrections' texts, and
the resulting contract, are delivered with step 3"):
- each entry is exactly the addition its note describes, and still carries
  no approval date;
- the effective contract gains exactly the two responses, annotated, and
  the frozen package is unchanged;
- each added response's code is a `ProblemCode` whose catalogue status is the
  entry's, so the runtime answers what the contract declares;
- the loader refuses every shape that would not be one error response added
  to one (operation, status).
The runtime's own answers (the 500 and the 503 through the route) are
`tests/test_slice7_step3.py`'s.
"""
from __future__ import annotations

import copy
import pathlib

import pytest
import yaml

from turab.auth.contract import CORRECTIONS_PATH, ContractError, load_contract

ROOT = pathlib.Path(__file__).resolve().parents[1]
EFFECTIVE = ROOT / "docs" / "api" / "openapi_effective_v0.2.3.yaml"
PATH, METHOD = "/webhooks/whatsapp", "post"
PROBLEM = {"application/problem+json": {"schema": {"$ref": "#/components/schemas/Problem"}}}


def load_response_additions(*a, **kw):
    """Imported where used, so that this file is collected on a tree without
    the loader and each test there fails on its own (the before record)."""
    from turab.auth.contract import load_response_additions as loader

    return loader(*a, **kw)


def added_response(entry):
    from turab.auth.contract import added_response as build

    return build(entry)


def _entries():
    doc = yaml.safe_load(CORRECTIONS_PATH.read_text(encoding="utf-8"))
    return {e["id"]: e for e in doc["response_additions"]}


def _operation(doc):
    return doc["paths"][PATH][METHOD]


# --- the entries ---------------------------------------------------------------------------

@pytest.mark.parametrize("cid, status, code", [
    ("CORRECTION-007", "500", "WEBHOOK_PROCESSING_FAILED"),
    ("CORRECTION-008", "503", "WEBHOOK_NOT_READY"),
])
def test_each_entry_is_one_error_response_of_the_webhook(cid, status, code):
    entry = _entries()[cid]
    assert (entry["operation_id"], entry["status"], entry["code"],
            entry["frozen_statuses"]) == ("postWebhooksWhatsapp", status, code,
                                          ["200", "400", "401"])
    assert entry["reference"] == next(
        str(p.relative_to(ROOT)) for p in (ROOT / "docs" / "contract").glob(f"{cid}-*.md"))
    # Submitted with step 3's delivery: no approval date until the review.
    assert "approved" not in entry and "not yet approved" in entry["decision"]


def test_the_two_meanings_differ_as_decided():
    """G7-17 (vi): the 500 says the event is recorded; the 503 asks for a
    redelivery WITHOUT claiming it is."""
    entries = _entries()
    stored = entries["CORRECTION-007"]["description"]
    not_ready = entries["CORRECTION-008"]["description"]
    assert "is stored" in stored and "provider_event_id is recorded" in stored
    assert "Nothing is recorded" in not_ready and "stored" not in not_ready
    for text in (stored, not_ready):
        assert "Deliver the same provider_event_id again" in text


def test_the_loader_returns_both_and_only_them():
    assert [e["id"] for e in load_response_additions()] == ["CORRECTION-007",
                                                            "CORRECTION-008"]


# --- the effective contract ---------------------------------------------------------------

def test_the_effective_operation_is_the_frozen_one_with_the_two_responses():
    """The expectation is written here, independently of `added_response`."""
    frozen, effective = load_contract(), yaml.safe_load(EFFECTIVE.read_text(encoding="utf-8"))
    expected = copy.deepcopy(_operation(frozen))
    entries = _entries()
    for cid, status in (("CORRECTION-007", "500"), ("CORRECTION-008", "503")):
        entry = entries[cid]
        expected["responses"][status] = {
            "description": " ".join(entry["description"].split()),
            "content": PROBLEM,
            "x-turab-correction": {
                "id": cid, "kind": "RESPONSE_ADDITION",
                "decision": " ".join(entry["decision"].split()), "approved": "",
                "code": entry["code"], "frozen-statuses": ["200", "400", "401"],
                "reference": entry["reference"]}}
    assert _operation(effective) == expected
    assert sorted(_operation(effective)["responses"]) == ["200", "400", "401", "500", "503"]
    assert added_response(entries["CORRECTION-008"]) == expected["responses"]["503"]


def test_the_frozen_operation_is_unchanged():
    frozen = _operation(load_contract())
    assert sorted(frozen["responses"]) == ["200", "400", "401"]
    assert frozen["security"] == []


@pytest.mark.parametrize("cid", ["CORRECTION-007", "CORRECTION-008"])
def test_each_code_is_a_problem_code_of_the_entrys_status(cid):
    from turab.api.problems import _CATALOGUE, ProblemCode

    entry = _entries()[cid]
    code = ProblemCode(entry["code"])
    assert _CATALOGUE[code][0] == int(entry["status"])


def test_the_runtimes_other_webhook_answers_are_declared_statuses():
    """The 400s and the 401 the route answers are statuses the frozen
    operation declares; the generic 500 of a T1 that did not commit is the
    500 CORRECTION-007 adds (with another code: nothing is stored)."""
    from turab.api.problems import _CATALOGUE, ProblemCode

    for code in (ProblemCode.WEBHOOK_BODY_TOO_LARGE, ProblemCode.WEBHOOK_ENVELOPE_NOT_VALID):
        assert _CATALOGUE[code][0] == 400
    assert _CATALOGUE[ProblemCode.UNAUTHENTICATED][0] == 401
    assert _CATALOGUE[ProblemCode.INTERNAL_ERROR][0] == 500


# --- the loader's refusals ----------------------------------------------------------------

def _refusal(tmp_path, change, contract=None):
    doc = yaml.safe_load(CORRECTIONS_PATH.read_text(encoding="utf-8"))
    change(doc["response_additions"], doc)
    path = tmp_path / "corrections.yaml"
    path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return lambda: load_response_additions(path, contract=contract)


def _set(i, key, value):
    def change(entries, doc):
        entries[i][key] = value
    return change


def _drop(i, key):
    def change(entries, doc):
        entries[i].pop(key)
    return change


@pytest.mark.parametrize("label, change, message", [
    ("an unknown key", _set(0, "schema", {"type": "object"}), "unknown key"),
    ("a role", _set(0, "x_roles", ["ADMIN"]), "unknown key"),
    ("no id", _drop(0, "id"), "missing or duplicated id"),
    ("a reused id", _set(1, "id", "CORRECTION-007"), "missing or duplicated id"),
    ("an id of another section", _set(0, "id", "CORRECTION-006"),
     "missing or duplicated id"),
    ("no decision", _set(0, "decision", ""), "names no decision"),
    ("an unknown operation", _set(0, "operation_id", "postNothing"),
     "not in the frozen contract"),
    ("a 2xx", _set(0, "status", "202"), "not a 5xx"),
    ("a 4xx", _set(0, "status", "409"), "not a 5xx"),
    ("a status as a number", _set(0, "status", 500), "not a 5xx"),
    ("a status of four digits", _set(0, "status", "5000"), "not a 5xx"),
    ("the same pair twice", _set(1, "status", "500"), "is already added; one addition per"),
    ("stale frozen statuses", _set(0, "frozen_statuses", ["200", "400"]), "stale"),
    ("no frozen statuses", _drop(0, "frozen_statuses"), "stale"),
    ("a lower-case code", _set(0, "code", "webhook_processing_failed"),
     "not an upper-case identifier"),
    ("no code", _drop(0, "code"), "not an upper-case identifier"),
    ("an empty description", _set(0, "description", "  "), "no description"),
])
def test_the_loader_refuses_what_is_not_one_added_error_response(tmp_path, label, change,
                                                                 message):
    with pytest.raises(ContractError, match=message):
        _refusal(tmp_path, change)()


def test_the_loader_refuses_a_status_the_operation_already_declares(tmp_path):
    """A frozen package that already declares 500 leaves nothing to add."""
    contract = copy.deepcopy(load_contract())
    _operation(contract)["responses"]["500"] = {"description": "x"}

    def change(entries, doc):
        for e in entries:
            e["frozen_statuses"] = ["200", "400", "401", "500"]

    with pytest.raises(ContractError, match="already declares 500"):
        _refusal(tmp_path, change, contract)()


def test_the_loader_refuses_a_package_whose_statuses_changed(tmp_path):
    contract = copy.deepcopy(load_contract())
    _operation(contract)["responses"]["422"] = {"description": "x"}
    with pytest.raises(ContractError, match="stale"):
        _refusal(tmp_path, lambda entries, doc: None, contract)()


def test_the_same_status_on_two_operations_is_two_pairs(tmp_path):
    """Uniqueness is per (operation, status), not per operation or status."""
    def change(entries, doc):
        other = copy.deepcopy(entries[0])
        other.update(id="CORRECTION-900", operation_id="postAuthOtpVerify",
                     frozen_statuses=sorted(_operation_of("postAuthOtpVerify")["responses"]))
        entries.append(other)

    assert [e["id"] for e in _refusal(tmp_path, change)()][-1] == "CORRECTION-900"


def _operation_of(operation_id):
    for item in load_contract()["paths"].values():
        for op in item.values():
            if isinstance(op, dict) and op.get("operationId") == operation_id:
                return op
    raise KeyError(operation_id)
