"""Exact numbers: a request body parsed so that its numbers keep their value.

Ref: Slice 8 plan (`docs/gate/SLICE_8_PLAN.md`) Q-C1 (a), decided in the
review of `5054bd0`: "a limited preparatory step for numbers before
CORRECTION-009 is approved: parse the body from its bytes before its numbers
become `float`, update the judge and its comparison for exact values, with
agreement tests for the four examples and `1.0`, and a test for an integer
beyond Python's default limit of 4300 digits. Any refusal at the parsing
limit must be a classified answer, not a general exception or a consumed
idempotency key."

M15 (`docs/gate/evidence/SLICE8-NUMBER-PARSING-MEASUREMENTS.txt`) measured
four differences between the schema and the judge when `json.loads` makes
floats: `1e400` refused, and `1e-400`, `1.0000000000000001`,
`0.99999999999999999` ACCEPTED where the schema refuses them.

What this file does NOT show: that every accepted body is stored as sent.
The conversion is not wired (step 3); its storage (`bigint` budgets, a
`jsonb` payload) is tested there.
"""
# No `from __future__ import annotations`: the test route's annotations must
# be objects when FastAPI reads them (they name a module imported per test).

import decimal
import json
import math
import uuid

import pytest
from fastapi import Request
from fastapi.testclient import TestClient
from sqlalchemy import text

from turab.auth import contract as C

D = decimal.Decimal
OP = "postExternalLeadsLeadIdConvert"
INTEGER = {"type": "integer", "minimum": 0}
LONG = "7" * 5000  # beyond Python's default int_max_str_digits (4300)


def _exact():
    """Imported per test, so that each test reports for itself."""
    from turab.api import exact_json
    return exact_json


def _spec(text_: str) -> bool:
    """The specification's verdict on {"type": "integer", "minimum": 0},
    computed from the TEXT: a JSON number literal is exact in Decimal
    (Validation 6.1.1: an integer is a number with a zero fractional part)."""
    d = D(text_)
    return d == math.floor(d) and d >= 0


def _no_float(value) -> bool:
    pending = [value]
    while pending:
        item = pending.pop()
        if isinstance(item, float):
            return False
        if isinstance(item, dict):
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    return True


# --- parsing keeps the value ----------------------------------------------------------------

@pytest.mark.parametrize("literal", ["1.0", "1e400", "1e-400", "1.0000000000000001",
                                     "0.99999999999999999", "9007199254740993.0", "-0.0"])
def test_a_non_integer_literal_keeps_its_exact_value(literal):
    parsed = _exact().parse_exact(literal.encode())
    assert isinstance(parsed, D) and parsed == D(literal) and str(parsed) == str(D(literal))


def test_an_integer_literal_stays_an_int():
    assert _exact().parse_exact(b"12") == 12 and type(_exact().parse_exact(b"12")) is int


def test_an_integer_beyond_4300_digits_is_kept_exactly():
    """Python's int() refuses more than 4300 digits (sys.int_max_str_digits);
    the parser keeps the value instead, as the schema accepts it."""
    parsed = _exact().parse_exact(LONG.encode())
    assert parsed == D(LONG) and C.body_violations(INTEGER, parsed, C.load_contract()) == []


def test_a_parsed_body_holds_no_float_anywhere():
    raw = b'{"a": [1.5, {"b": 2e-3}], "c": 3, "d": [[0.1]]}'
    assert _no_float(_exact().parse_exact(raw))


# --- the schema and the judge agree (the review's four, and 1.0) -----------------------------

AGREEMENT = ["1.0", "1e400", "1e-400", "1.0000000000000001", "0.99999999999999999",
             "1", "0", "1.5", "-1", "-0.0", "1E+2", LONG]


@pytest.mark.parametrize("literal", AGREEMENT, ids=[a[:24] for a in AGREEMENT])
def test_the_judge_agrees_with_the_schema_on_the_exact_value(literal):
    parsed = _exact().parse_exact(literal.encode())
    runtime = C.body_violations(INTEGER, parsed, C.load_contract())
    assert (runtime == []) is _spec(literal), (literal[:30], runtime)


@pytest.mark.parametrize("literal", ["1.0", "1e400", "1e-400", "1.0000000000000001",
                                     "0.99999999999999999"])
def test_in_a_conversion_body_the_budget_is_judged_as_the_schema_judges_it(literal):
    """The same literals as a REQUEST payload's budget, through an effective
    body narrowed by an add_all_of entry shaped as CORRECTION-009's."""
    payload = {"type": "object", "additionalProperties": False,
               "required": ["intent"],
               "properties": {"intent": {"type": "string"},
                              "budget_max_dzd": {"type": "integer", "minimum": 0}}}
    entry = {"id": "TEST-EXACT", "operation_id": OP, "require": ["target", "payload"],
             "add_all_of": [{"if": {"properties": {"target": {"const": "REQUEST"}},
                                    "required": ["target"]},
                             "then": {"properties": {"payload": payload}}}],
             "frozen_defaults": {}}
    schema = C.narrowed_body_schema(entry, C.load_contract())
    raw = ('{"party_id": "%s", "consent_id": "%s", "target": "REQUEST", '
           '"payload": {"intent": "EXPLORING", "budget_max_dzd": %s}}'
           % (uuid.uuid4(), uuid.uuid4(), literal)).encode()
    runtime = C.body_violations(schema, _exact().parse_exact(raw), C.load_contract())
    assert (runtime == []) is _spec(literal), (literal, runtime)


# --- the judge reads an exact number --------------------------------------------------------

def test_the_judge_reads_a_decimal_as_a_json_number():
    frozen = C.load_contract()
    assert C.body_violations({"type": "integer"}, D("1.0"), frozen) == []
    assert C.body_violations({"type": "integer"}, D("1.5"), frozen) == [
        "body: not of type integer"]
    assert C.body_violations({"type": "number"}, D("0.1"), frozen) == []
    assert C.body_violations({"minimum": 0}, D("-1e-400"), frozen) == ["body: below 0"]
    assert C.body_violations({"const": 1}, D("1.000"), frozen) == []
    assert C.body_violations({"const": [1]}, [D("1E+0")], frozen) == []
    for v in (D("NaN"), D("Infinity"), D("-Infinity")):
        assert C.body_violations({"type": "number"}, v, frozen) == [
            "body: not of type number"], v


# --- the schema's own numbers must be exact too ---------------------------------------------

@pytest.mark.parametrize("node", [
    {"properties": {"n": {"minimum": 0.5}}},
    {"properties": {"n": {"const": 0.1}}},
    {"properties": {"n": {"enum": [1, 2.5]}}},
    {"properties": {"n": {"const": {"a": [0.25]}}}},
    {"properties": {"n": {"default": 1.5}}},
], ids=["minimum", "const", "enum", "nested const", "default"])
def test_a_non_integral_number_in_the_schema_is_refused_at_load(tmp_path, node):
    """YAML reads 0.1 as the binary float nearest to it, so an exact instance
    0.1 would not equal it. None is in the frozen components (M16)."""
    from test_contract_add_all_of import _loaded
    with pytest.raises(C.ContractError, match="non-integral"):
        _loaded(tmp_path, add_all_of=[node])


def test_an_integral_float_in_the_schema_is_exact_and_admitted(tmp_path):
    from test_contract_add_all_of import _loaded
    _loaded(tmp_path, add_all_of=[{"properties": {"payload": {"properties": {
        "n": {"type": "integer", "minimum": 0.0}}}}}])


# --- a refusal at the parsing limit is classified, and consumes no key ----------------------

@pytest.fixture
def client(engine):
    """The application, with one route for this test only: the exact body,
    then the real command plumbing (`_run`), which claims the key."""
    from turab.app import create_app
    from turab.api.deps import Command
    from turab.api.routes.parties import _run

    exact = _exact()
    app = create_app(engine=engine)

    def route(request: Request, lead_id: uuid.UUID, body: exact.ExactJsonBody,
              command: Command):
        return _run(request, command, OP, f"POST /__test/exact-body/{lead_id}",
                    {"accepted": True}, lambda session: (201, {"accepted": True}), 201)

    app.add_api_route("/__test/exact-body/{lead_id}", route, methods=["POST"])
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _post(client, ids, raw: bytes, key: str):
    return client.post(f"/__test/exact-body/{uuid.uuid4()}", content=raw,
                       headers={"Authorization": f"Bearer {ids.ACC_OPERATOR}",
                                "Idempotency-Key": key, "Content-Type": "application/json"})


def _key_used(engine, key: str) -> bool:
    with engine.connect() as c:
        return c.execute(text("SELECT 1 FROM turab.idempotency_records "
                              "WHERE idempotency_key = :k"), {"k": key}).first() is not None


REFUSED = [
    ("not UTF-8", b'{"a": "\xff"}', 400),
    ("nested 100000 deep", b"[" * 100000 + b"]" * 100000, 400),
    ("not JSON", b"{", 422),
    ("empty", b"", 422),
    ("NaN", b'{"n": NaN}', 422),
    ("Infinity", b'{"n": Infinity}', 422),
    ("-Infinity", b'{"n": -Infinity}', 422),
]


@pytest.mark.parametrize("label, raw, status", REFUSED, ids=[r[0] for r in REFUSED])
def test_a_body_refused_at_parsing_is_classified_and_consumes_no_key(client, engine, ids,
                                                                    label, raw, status):
    key = str(uuid.uuid4())
    r = _post(client, ids, raw, key)
    assert r.status_code == status, (label, r.status_code, r.text)
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["code"] == "VALIDATION_FAILED"
    assert not _key_used(engine, key), label


@pytest.mark.parametrize("raw", [b'{"n": 1e-400}', b'{"n": 1e400}', ('{"n": %s}' % LONG).encode()],
                         ids=["1e-400", "1e400", "5000 digits"])
def test_a_body_that_parses_reaches_the_command_and_its_key(client, engine, ids, raw):
    """The control: the same route claims the key when the body parses, so
    the refusals above consumed none because they never reached it."""
    key = str(uuid.uuid4())
    r = _post(client, ids, raw, key)
    assert r.status_code == 201, r.text
    assert _key_used(engine, key)
