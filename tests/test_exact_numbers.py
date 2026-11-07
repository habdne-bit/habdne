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

Storage (the review's second note on `5054bd0`): through a route built of the
real parts (the application, the command plumbing that claims the key, the
request model with its storage bounds, the request service writing the row):
- an accepted integer reaches the `bigint` column with its exact value;
- a refusal at parsing, or at the column's bound (decision F-3), is a
  classified answer, given before any key is claimed, writing no row.
The schema's verdict and the column's stay distinct: a budget above
`BIGINT_MAX` is an `integer` the contract accepts and the column cannot hold.

**On a tree without the parser** (the before record), the tests measure
today's parsing instead, FastAPI's `json.loads` and the route's body model as
`POST /requests` declares it, so each test reports an assertion, not an
import error.

What this file does NOT show: the conversion route itself (step 3), nor a
`jsonb` payload or a `number` field holding an exact non-integer.
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
    """The tree's parser, or None on a tree without it (the before record)."""
    try:
        from turab.api import exact_json
    except ImportError:
        return None
    return exact_json


def _parse(raw: bytes):
    """The tree's parser; without it, today's parsing: `json.loads`, as
    FastAPI parses a body."""
    exact = _exact()
    return exact.parse_exact(raw) if exact else json.loads(raw)


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
    parsed = _parse(literal.encode())
    assert isinstance(parsed, D) and parsed == D(literal) and str(parsed) == str(D(literal))


def test_an_integer_literal_stays_an_int():
    assert _parse(b"12") == 12 and type(_parse(b"12")) is int


def test_an_integer_beyond_4300_digits_is_kept_exactly():
    """Python's int() refuses more than 4300 digits (sys.int_max_str_digits);
    the parser keeps the value instead, as the schema accepts it."""
    parsed = _parse(LONG.encode())
    assert parsed == D(LONG) and C.body_violations(INTEGER, parsed, C.load_contract()) == []


def test_a_parsed_body_holds_no_float_anywhere():
    raw = b'{"a": [1.5, {"b": 2e-3}], "c": 3, "d": [[0.1]]}'
    assert _no_float(_parse(raw))


# --- the schema and the judge agree (the review's four, and 1.0) -----------------------------

AGREEMENT = ["1.0", "1e400", "1e-400", "1.0000000000000001", "0.99999999999999999",
             "1", "0", "1.5", "-1", "-0.0", "1E+2", LONG]


@pytest.mark.parametrize("literal", AGREEMENT, ids=[a[:24] for a in AGREEMENT])
def test_the_judge_agrees_with_the_schema_on_the_exact_value(literal):
    parsed = _parse(literal.encode())
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
    runtime = C.body_violations(schema, _parse(raw), C.load_contract())
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

def _store(request, command, body, run, request_service):
    """The request service writes the row inside the command, as POST
    /requests does; `run` claims the key first."""
    def handler(session):
        row = request_service.create_request(
            session, party_id=body.party_id, transaction_intent=body.transaction_intent,
            intent=body.intent, management_mode=body.management_mode,
            claim_status=body.claim_status, created_by_account_id=command.subject.account_id,
            budget_target_dzd=body.budget_target_dzd, budget_max_dzd=body.budget_max_dzd)
        return 201, {"request_id": str(row["request_id"])}
    return run(request, command, "postRequests", "POST /__test/exact-request",
               body.model_dump(mode="json"), handler, 201,
               extra_errors=request_service.RequestError)


@pytest.fixture
def client(engine):
    """The application, with two routes for these tests only, built of the
    real parts. With the parser: the exact body, then (for the request) the
    route's own body model and its storage bounds, by `exact_json.validated`.
    Without it: FastAPI's own parsing, the body model as POST /requests
    declares it."""
    from typing import Annotated, Any

    from fastapi import Body

    from turab.api.deps import Command
    from turab.api.routes.parties import _run
    from turab.api.routes.requests import RequestCreate
    from turab.app import create_app
    from turab.services import requests as request_service

    exact = _exact()
    app = create_app(engine=engine)

    def accept(request, command, lead_id):
        return _run(request, command, OP, f"POST /__test/exact-body/{lead_id}",
                    {"accepted": True}, lambda session: (201, {"accepted": True}), 201)

    if exact is not None:
        def route(request: Request, lead_id: uuid.UUID, body: exact.ExactJsonBody,
                  command: Command):
            return accept(request, command, lead_id)

        def store(request: Request, raw: exact.ExactJsonBody, command: Command):
            body = exact.validated(RequestCreate, raw)
            return _store(request, command, body, _run, request_service)
    else:
        def route(request: Request, lead_id: uuid.UUID, body: Annotated[Any, Body()],
                  command: Command):
            return accept(request, command, lead_id)

        def store(request: Request, body: RequestCreate, command: Command):
            return _store(request, command, body, _run, request_service)

    app.add_api_route("/__test/exact-body/{lead_id}", route, methods=["POST"])
    app.add_api_route("/__test/exact-request", store, methods=["POST"])
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


# --- storage: the exact value reaches the column; a value it cannot hold is refused first ---

BIGINT_MAX = 2**63 - 1


def _request_body(ids, budget_literal: str) -> bytes:
    return ('{"party_id": "%s", "transaction_intent": "BUY", "intent": "EXPLORING", '
            '"management_mode": "ASSISTED", "claim_status": "UNCLAIMED", '
            '"budget_max_dzd": %s}' % (ids.AMINA, budget_literal)).encode()


def _store_post(client, ids, raw: bytes, key: str):
    return client.post("/__test/exact-request", content=raw,
                       headers={"Authorization": f"Bearer {ids.ACC_OPERATOR}",
                                "Idempotency-Key": key, "Content-Type": "application/json"})


def _requests(engine) -> int:
    with engine.connect() as c:
        return c.execute(text("SELECT count(*) FROM turab.requests")).scalar_one()


STORED = [("9007199254740993.0", 9007199254740993), ("9223372036854775807", BIGINT_MAX),
          ("9223372036854775807.0", BIGINT_MAX), ("1E+3", 1000), ("1.0", 1)]


@pytest.mark.parametrize("literal, stored", STORED, ids=[s_[0] for s_ in STORED])
def test_an_accepted_budget_reaches_the_column_with_its_exact_value(client, engine, ids,
                                                                    literal, stored):
    """`9007199254740993.0` as a float is 9007199254740992.0: the column would
    hold another number. `9223372036854775807.0` as a float exceeds bigint."""
    key = str(uuid.uuid4())
    r = _store_post(client, ids, _request_body(ids, literal), key)
    assert r.status_code == 201, (literal, r.text)
    with engine.connect() as c:
        held = c.execute(text("SELECT budget_max_dzd FROM turab.requests WHERE request_id = :r"),
                         {"r": r.json()["request_id"]}).scalar_one()
    assert held == stored, (literal, held)
    assert _key_used(engine, key)


NOT_STORED = [("9223372036854775808", "beyond bigint"), ("9223372036854775808.0", "beyond bigint"),
              (LONG, "5000 digits"), ("1e400", "1e400"), ("1e-400", "not an integer"),
              ("1.5", "not an integer"), ("-1", "below 0")]


@pytest.mark.parametrize("literal, label", NOT_STORED, ids=[n[1] + " " + n[0][:12] for n in NOT_STORED])
def test_a_budget_refused_is_classified_before_the_key_and_writes_nothing(client, engine, ids,
                                                                          literal, label):
    """The column's bound (F-3) and the schema's own rules: a 422 naming the
    field, the key free, no row. `1e400` and the 5000-digit integer are
    integers the schema accepts and no column can hold."""
    key, before = str(uuid.uuid4()), _requests(engine)
    r = _store_post(client, ids, _request_body(ids, literal), key)
    assert r.status_code == 422, (label, r.status_code, r.text)
    assert r.json()["code"] == "VALIDATION_FAILED"
    assert [f["field"] for f in r.json()["field_errors"]] == ["budget_max_dzd"], label
    assert literal[:40] not in r.text, "no value echoed (the bound may be named, not the value)"
    assert not _key_used(engine, key) and _requests(engine) == before, label


def test_json_integer_reads_an_exact_decimal():
    """`json_types.JsonInteger` on `api.exact_json`'s exact numbers: an
    integral Decimal is the exact int; any other is refused; the digit count
    is bounded BEFORE `int()`, so an exponent such as `1E+100000000` builds no
    huge int. Tested at `1E+5000`: beyond the bound, yet small enough that a
    mutant without it still ends (and is caught by the message)."""
    from turab.api.json_types import _json_integer
    assert _json_integer(D("1.0")) == 1 and type(_json_integer(D("1.0"))) is int
    assert _json_integer(D("9007199254740993.0")) == 9007199254740993
    assert _json_integer(D("-0.0")) == 0 and _json_integer(D("1E+2")) == 100
    for refused, why in [(D("1.5"), "a JSON integer"), (D("1e-400"), "a JSON integer"),
                         (D("NaN"), "a JSON integer"), (D("Infinity"), "a JSON integer"),
                         (D("1E+5000"), "a column can store")]:
        with pytest.raises(ValueError, match=why):
            _json_integer(refused)


def test_a_budget_with_a_huge_exponent_is_refused_by_the_bound_not_built(client, engine, ids):
    """Refused by the digit bound, before `int()`, not by the column's `le`."""
    key, before = str(uuid.uuid4()), _requests(engine)
    r = _store_post(client, ids, _request_body(ids, "1e5000"), key)
    assert r.status_code == 422, r.text
    [error] = r.json()["field_errors"]
    assert error["field"] == "budget_max_dzd" and "a column can store" in error["message"]
    assert not _key_used(engine, key) and _requests(engine) == before

