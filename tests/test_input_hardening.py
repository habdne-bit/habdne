"""Hostile-but-well-formed input must be a typed 4xx, never a 500.

Review of 1c2f6c5 found two routes to a 500 in the truth layer; each is a
FAMILY, and every member found is tested here, over HTTP, on real PostgreSQL
(one exception: the `postExternalLeadsLeadIdConvert` payload is typed the same
way but not tested here — conversion is refused by G3-10 and writes nothing):

1. **A caller value echoed into `detail`.** The problem builder refuses a
   `detail` containing implementation markers (`otp`, `turab.`, `SELECT `…,
   `problems._LEAK_MARKERS`) and raises `DetailLeak` — a 500. A typed domain
   error that quoted the caller's own text (an unknown attribute code, an
   ENUM value, a reason code, a criterion code) therefore turned a 422 into a
   500 whenever that text happened to contain a marker. The validation
   handler already followed the right rule — it never echoes input values
   (§8); the domain errors now follow it too.

2. **A number the database cannot store.** Python's `json.loads` accepts
   `1e400` (as `inf`) and the literals `NaN` / `Infinity`. They reached
   `json.dumps` → `Infinity` → `CAST(... AS jsonb)`, which PostgreSQL refuses;
   and through a `number` field they reached `numeric(12,2)`. An integer
   beyond the column's range (bigint, smallint) overflowed it. JSON itself
   (RFC 8259 §6) has no representation for infinity or NaN.

Each case asserts: a typed 4xx with a stable code (never 500); NOTHING
written; and, where the command takes an Idempotency-Key, that the SAME key
then succeeds with a valid body — the refused call did not consume it.
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink

BAD = "__BAD__"


@pytest.fixture
def client(engine):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink()))
    # raise_server_exceptions=True: a regression to a 500 fails the test WITH
    # its cause (DetailLeak, a psycopg DataError...), not merely a status code.
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


@pytest.fixture(autouse=True)
def clean(engine):
    yield
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.idempotency_records"))
        s.commit()


def _h(account, with_key=True):
    h = {"Authorization": f"Bearer {account}", "Content-Type": "application/json"}
    if with_key:
        h["Idempotency-Key"] = f"hard-{uuid.uuid4()}"
    return h


def _count(engine, sql, **p) -> int:
    with Session(bind=engine, future=True) as s:
        return s.execute(text(sql), p).scalar_one()


def _raw(body: dict, bad: str) -> str:
    """The body as JSON text with the BAD placeholder replaced verbatim, so
    `1e400` / `NaN` / huge integers reach the server as a client sends them."""
    return json.dumps(body).replace(f'"{BAD}"', bad)


# --- fixtures built through the API -----------------------------------------

def _property(client, ids, ptype="APARTMENT"):
    r = client.post("/properties", headers=_h(ids.ACC_OPERATOR), json={
        "property_type": ptype, "supply_mode": "PUBLIC",
        "management_mode": "ASSISTED", "claim_status": "UNCLAIMED"})
    assert r.status_code == 201, r.text
    return r.json()["property_id"]


def _offer(client, ids):
    pid = _property(client, ids)
    r = client.post(f"/properties/{pid}/offers", headers=_h(ids.ACC_OPERATOR),
                    json={"party_id": str(ids.BRAHIM), "transaction_type": "SALE"})
    assert r.status_code == 201, r.text
    return r.json()


def _active_request(client, ids):
    r = client.post("/requests", headers=_h(ids.ACC_OPERATOR), json={
        "party_id": str(ids.AMINA), "transaction_intent": "BUY",
        "intent": "ACTIVE_SEARCH", "management_mode": "ASSISTED",
        "claim_status": "UNCLAIMED"})
    assert r.status_code == 201, r.text
    rid = r.json()["request_id"]
    for target in ("CONTACTED", "QUALIFIED", "ACTIVE"):
        s = client.post(f"/requests/{rid}/state", headers=_h(ids.ACC_OPERATOR),
                        json={"target_status": target})
        assert s.status_code == 200, s.text
    return rid


def _relation(client, ids):
    pid = _property(client, ids)
    r = client.post(f"/properties/{pid}/relations", headers=_h(ids.ACC_OPERATOR),
                    json={"party_id": str(ids.BRAHIM), "relation_code": "BROKER"})
    assert r.status_code == 201, r.text
    return pid, r.json()["party_property_relation_id"]


def _send(client, method, path, headers, raw):
    return client.request(method, path, headers=headers, content=raw)


def _assert_refused_cleanly(r, label):
    assert r.status_code != 500, f"{label}: 500 — {r.text}"
    assert 400 <= r.status_code < 500, f"{label}: {r.status_code} {r.text}"
    assert r.json().get("code") in ("VALIDATION_FAILED", "UNKNOWN_FIELD"), (
        f"{label}: not a typed input refusal: {r.text}")


# --- family 1: caller text echoed into `detail` ------------------------------

MARKED = ["otp", "turab.x", "SELECT 1"]


@pytest.mark.parametrize("value", MARKED)
def test_claim_with_a_marked_enum_value_is_a_typed_422(client, ids, engine, value):
    pid = _property(client, ids)
    # Creating a property records its provenance claims (services/provenance.py);
    # the refusal must add none.
    claims_before = _count(engine, "SELECT count(*) FROM turab.claims "
                                   "WHERE property_id=:p", p=pid)
    body = {"subject": {"type": "PROPERTY", "id": pid}, "attribute_code": "RIGHT_TYPE",
            "claimed_value": value, "asserted_by_party_id": str(ids.BRAHIM)}
    h = _h(ids.ACC_OPERATOR)
    _assert_refused_cleanly(_send(client, "POST", "/claims", h, json.dumps(body)), value)
    assert _count(engine, "SELECT count(*) FROM turab.claims WHERE property_id=:p",
                  p=pid) == claims_before
    body["claimed_value"] = "PRIVATE_OWNERSHIP"
    assert _send(client, "POST", "/claims", h, json.dumps(body)).status_code == 201


@pytest.mark.parametrize("code", MARKED)
def test_claim_with_a_marked_unknown_attribute_code_is_a_typed_422(client, ids, engine,
                                                                   code):
    pid = _property(client, ids)
    # Creating a property records its provenance claims (services/provenance.py);
    # the refusal must add none.
    claims_before = _count(engine, "SELECT count(*) FROM turab.claims "
                                   "WHERE property_id=:p", p=pid)
    body = {"subject": {"type": "PROPERTY", "id": pid}, "attribute_code": code,
            "claimed_value": 4, "asserted_by_party_id": str(ids.BRAHIM)}
    h = _h(ids.ACC_OPERATOR)
    _assert_refused_cleanly(_send(client, "POST", "/claims", h, json.dumps(body)), code)
    assert _count(engine, "SELECT count(*) FROM turab.claims WHERE property_id=:p",
                  p=pid) == claims_before
    body["attribute_code"] = "ROOMS"
    assert _send(client, "POST", "/claims", h, json.dumps(body)).status_code == 201


@pytest.mark.parametrize("code", MARKED)
def test_resolution_with_a_marked_reason_code_is_a_typed_422(client, ids, engine, code):
    pid = _property(client, ids)
    body = {"subject": {"type": "PROPERTY", "id": pid}, "attribute_code": "ROOMS",
            "resolved_value": 4, "resolution_reason_code": code}
    h = _h(ids.ACC_OPERATOR)
    _assert_refused_cleanly(_send(client, "POST", "/resolutions", h, json.dumps(body)),
                            code)
    assert _count(engine, "SELECT count(*) FROM turab.resolved_values "
                          "WHERE property_id=:p", p=pid) == 0
    del body["resolution_reason_code"]
    assert _send(client, "POST", "/resolutions", h, json.dumps(body)).status_code == 201


@pytest.mark.parametrize("code", MARKED)
def test_offer_transition_with_a_marked_reason_code_is_a_typed_422(client, ids, engine,
                                                                   code):
    offer = _offer(client, ids)
    h = _h(ids.ACC_OPERATOR)
    path = f"/offers/{offer['offer_id']}/state"
    _assert_refused_cleanly(_send(client, "POST", path, h, json.dumps(
        {"status": "ACTIVE", "reason_code": code})), code)
    assert _count(engine, "SELECT count(*) FROM turab.property_offers "
                          "WHERE offer_id=:o AND status='DRAFT'", o=offer["offer_id"]) == 1
    assert _send(client, "POST", path, h, json.dumps({"status": "ACTIVE"})).status_code == 200


@pytest.mark.parametrize("code", MARKED)
def test_relation_end_with_a_marked_reason_code_is_a_typed_422(client, ids, engine, code):
    pid, rid = _relation(client, ids)
    h = _h(ids.ACC_OPERATOR)
    path = f"/properties/{pid}/relations/{rid}/end"
    _assert_refused_cleanly(_send(client, "POST", path, h, json.dumps(
        {"reason_code": code})), code)
    assert _count(engine, "SELECT count(*) FROM turab.party_property_relations "
                          "WHERE party_property_relation_id=:r AND valid_to IS NULL",
                  r=rid) == 1
    assert _send(client, "POST", path, h, "{}").status_code == 200


@pytest.mark.parametrize("code", MARKED)
def test_request_closure_with_a_marked_reason_code_is_a_typed_422(client, ids, engine,
                                                                  code):
    """Slice 2 code, same defect: the closure reason was echoed."""
    rid = _active_request(client, ids)
    h = _h(ids.ACC_OPERATOR)
    path = f"/requests/{rid}/state"
    _assert_refused_cleanly(_send(client, "POST", path, h, json.dumps(
        {"target_status": "CLOSED", "reason_code": code})), code)
    assert _count(engine, "SELECT count(*) FROM turab.requests "
                          "WHERE request_id=:r AND status='ACTIVE'", r=rid) == 1
    assert _send(client, "POST", path, h, json.dumps(
        {"target_status": "CLOSED", "reason_code": "REQUEST_WITHDRAWN"})).status_code == 200


@pytest.mark.parametrize("code", MARKED)
def test_request_criterion_with_a_marked_code_is_a_typed_422(client, ids, engine, code):
    """Slice 2 code, same defect: the unknown criterion code was echoed."""
    rid = _active_request(client, ids)
    h = _h(ids.ACC_OPERATOR)
    path = f"/requests/{rid}/criteria"
    body = {"criterion_code": code, "importance": "REQUIRED", "operator": "GTE",
            "value": 3}
    _assert_refused_cleanly(_send(client, "POST", path, h, json.dumps(body)), code)
    assert _count(engine, "SELECT count(*) FROM turab.request_criteria "
                          "WHERE request_id=:r", r=rid) == 0
    body["criterion_code"] = "ROOMS_MIN"
    assert _send(client, "POST", path, h, json.dumps(body)).status_code == 201


# --- family 2: numbers the database cannot store ------------------------------

NON_FINITE = ["1e400", "-1e400", "NaN", "Infinity", "-Infinity"]


@pytest.mark.parametrize("bad", NON_FINITE)
@pytest.mark.parametrize("field", ["claimed_value", "extraction_confidence"])
def test_claim_with_a_non_finite_number_is_a_typed_422(client, ids, engine, bad, field):
    pid = _property(client, ids)
    # Creating a property records its provenance claims (services/provenance.py);
    # the refusal must add none.
    claims_before = _count(engine, "SELECT count(*) FROM turab.claims "
                                   "WHERE property_id=:p", p=pid)
    body = {"subject": {"type": "PROPERTY", "id": pid}, "attribute_code": "ROOMS",
            "claimed_value": 4, "asserted_by_party_id": str(ids.BRAHIM), field: BAD}
    h = _h(ids.ACC_OPERATOR)
    _assert_refused_cleanly(_send(client, "POST", "/claims", h, _raw(body, bad)),
                            f"{field}={bad}")
    assert _count(engine, "SELECT count(*) FROM turab.claims WHERE property_id=:p",
                  p=pid) == claims_before
    body[field] = 4 if field == "claimed_value" else 0.5
    assert _send(client, "POST", "/claims", h, json.dumps(body)).status_code == 201


@pytest.mark.parametrize("bad", NON_FINITE)
def test_resolution_with_a_non_finite_value_is_a_typed_422(client, ids, engine, bad):
    pid = _property(client, ids)
    body = {"subject": {"type": "PROPERTY", "id": pid}, "attribute_code": "ROOMS",
            "resolved_value": BAD}
    h = _h(ids.ACC_OPERATOR)
    _assert_refused_cleanly(_send(client, "POST", "/resolutions", h, _raw(body, bad)), bad)
    assert _count(engine, "SELECT count(*) FROM turab.resolved_values "
                          "WHERE property_id=:p", p=pid) == 0
    body["resolved_value"] = 4
    assert _send(client, "POST", "/resolutions", h, json.dumps(body)).status_code == 201


@pytest.mark.parametrize("bad", NON_FINITE)
def test_observation_payload_with_a_non_finite_nested_number_is_a_typed_422(
    client, ids, engine, bad
):
    body = {"kind": "TEXT", "payload": {"outer": {"inner": [1, BAD]}}}
    h = _h(ids.ACC_OPERATOR)
    before = _count(engine, "SELECT count(*) FROM turab.observations")
    _assert_refused_cleanly(_send(client, "POST", "/observations", h, _raw(body, bad)), bad)
    assert _count(engine, "SELECT count(*) FROM turab.observations") == before
    body["payload"] = {"outer": {"inner": [1, 2]}}
    assert _send(client, "POST", "/observations", h, json.dumps(body)).status_code == 201


@pytest.mark.parametrize("bad", NON_FINITE)
@pytest.mark.parametrize("where", ["metadata", "raw_payload"])
def test_lead_with_a_non_finite_nested_number_is_a_typed_422(client, ids, engine, bad,
                                                             where):
    body = {"lead_kind": "PROPERTY", "source": {"kind": "OTHER"}}
    if where == "metadata":
        body["source"]["metadata"] = {"x": BAD}
    else:
        body["raw_payload"] = {"x": [BAD]}
    h = _h(ids.ACC_OPERATOR)
    before = _count(engine, "SELECT count(*) FROM turab.sources")
    _assert_refused_cleanly(_send(client, "POST", "/external-leads", h, _raw(body, bad)),
                            f"{where}={bad}")
    assert _count(engine, "SELECT count(*) FROM turab.sources") == before
    good = {"lead_kind": "PROPERTY", "source": {"kind": "OTHER"}}
    assert _send(client, "POST", "/external-leads", h, json.dumps(good)).status_code == 201


@pytest.mark.parametrize("bad", NON_FINITE)
def test_request_criterion_with_a_non_finite_value_is_a_typed_422(client, ids, engine,
                                                                  bad):
    rid = _active_request(client, ids)
    h = _h(ids.ACC_OPERATOR)
    path = f"/requests/{rid}/criteria"
    body = {"criterion_code": "ROOMS_MIN", "importance": "REQUIRED", "operator": "GTE",
            "value": BAD}
    _assert_refused_cleanly(_send(client, "POST", path, h, _raw(body, bad)), bad)
    assert _count(engine, "SELECT count(*) FROM turab.request_criteria "
                          "WHERE request_id=:r", r=rid) == 0
    body["value"] = 3
    assert _send(client, "POST", path, h, json.dumps(body)).status_code == 201


@pytest.mark.parametrize("bad", ["1e400", "NaN", "Infinity", "10000000000"])
@pytest.mark.parametrize("field", ["land_area_m2", "built_area_m2"])
def test_property_area_that_the_column_cannot_store_is_a_typed_422(client, ids, engine,
                                                                   bad, field):
    """numeric(12,2): at most 9 999 999 999.99. 1e10 overflows it."""
    body = {"property_type": "LAND", "supply_mode": "PUBLIC",
            "management_mode": "ASSISTED", "claim_status": "UNCLAIMED", field: BAD}
    h = _h(ids.ACC_OPERATOR)
    before = _count(engine, "SELECT count(*) FROM turab.properties")
    _assert_refused_cleanly(_send(client, "POST", "/properties", h, _raw(body, bad)),
                            f"{field}={bad}")
    assert _count(engine, "SELECT count(*) FROM turab.properties") == before
    body[field] = 9999999999.99
    assert _send(client, "POST", "/properties", h, json.dumps(body)).status_code == 201


@pytest.mark.parametrize("bad", ["1e400", "NaN", "10000000000"])
def test_property_area_patch_that_the_column_cannot_store_is_a_typed_422(client, ids,
                                                                         engine, bad):
    pid = _property(client, ids)
    h = {**_h(ids.ACC_OPERATOR, with_key=False), "If-Match-Version": "1"}
    _assert_refused_cleanly(_send(client, "PATCH", f"/properties/{pid}", h,
                                  _raw({"land_area_m2": BAD}, bad)), bad)
    assert _count(engine, "SELECT version FROM turab.properties WHERE property_id=:p",
                  p=pid) == 1
    # The refusal consumed nothing: the SAME If-Match-Version still applies.
    assert _send(client, "PATCH", f"/properties/{pid}", h,
                 json.dumps({"land_area_m2": 9999999999.99})).status_code == 200


BIGINT_OVER = str(2 ** 63)


@pytest.mark.parametrize("field", ["asking_price_dzd", "seller_expectation_dzd"])
def test_offer_amount_beyond_bigint_is_a_typed_422(client, ids, engine, field):
    pid = _property(client, ids)
    body = {"party_id": str(ids.BRAHIM), "transaction_type": "SALE", field: BAD}
    h = _h(ids.ACC_OPERATOR)
    _assert_refused_cleanly(_send(client, "POST", f"/properties/{pid}/offers", h,
                                  _raw(body, BIGINT_OVER)), field)
    assert _count(engine, "SELECT count(*) FROM turab.property_offers "
                          "WHERE property_id=:p", p=pid) == 0
    body[field] = 2 ** 63 - 1
    assert _send(client, "POST", f"/properties/{pid}/offers", h,
                 json.dumps(body)).status_code == 201


def test_offer_patch_beyond_bigint_is_a_typed_422(client, ids, engine):
    offer = _offer(client, ids)
    h = {**_h(ids.ACC_OPERATOR, with_key=False), "If-Match-Version": "1"}
    _assert_refused_cleanly(_send(client, "PATCH", f"/offers/{offer['offer_id']}", h,
                                  _raw({"asking_price_dzd": BAD}, BIGINT_OVER)), "patch")
    assert _count(engine, "SELECT version FROM turab.property_offers WHERE offer_id=:o",
                  o=offer["offer_id"]) == 1
    # The refusal consumed nothing: the SAME If-Match-Version still applies.
    assert _send(client, "PATCH", f"/offers/{offer['offer_id']}", h,
                 json.dumps({"asking_price_dzd": 2 ** 63 - 1})).status_code == 200


@pytest.mark.parametrize("field", ["budget_target_dzd", "budget_max_dzd"])
def test_request_budget_beyond_bigint_is_a_typed_422(client, ids, engine, field):
    body = {"party_id": str(ids.AMINA), "transaction_intent": "BUY",
            "intent": "ACTIVE_SEARCH", "management_mode": "ASSISTED",
            "claim_status": "UNCLAIMED", field: BAD}
    h = _h(ids.ACC_OPERATOR)
    before = _count(engine, "SELECT count(*) FROM turab.requests")
    _assert_refused_cleanly(_send(client, "POST", "/requests", h,
                                  _raw(body, BIGINT_OVER)), field)
    assert _count(engine, "SELECT count(*) FROM turab.requests") == before
    body[field] = 2 ** 63 - 1
    if field == "budget_target_dzd":
        body["budget_max_dzd"] = 2 ** 63 - 1
    assert _send(client, "POST", "/requests", h, json.dumps(body)).status_code == 201


@pytest.mark.parametrize("bad", ["32768", "-32769"])
def test_criterion_sort_order_beyond_smallint_is_a_typed_422(client, ids, engine, bad):
    rid = _active_request(client, ids)
    h = _h(ids.ACC_OPERATOR)
    path = f"/requests/{rid}/criteria"
    body = {"criterion_code": "ROOMS_MIN", "importance": "REQUIRED", "operator": "GTE",
            "value": 3, "sort_order": BAD}
    _assert_refused_cleanly(_send(client, "POST", path, h, _raw(body, bad)), bad)
    assert _count(engine, "SELECT count(*) FROM turab.request_criteria "
                          "WHERE request_id=:r", r=rid) == 0
    body["sort_order"] = 32767
    assert _send(client, "POST", path, h, json.dumps(body)).status_code == 201


# --- the types themselves, with no field bounds in front of them -------------
#
# Every `JsonNumber` field in the API today also carries `ge`/`gt`/`le`
# bounds, and those bounds refuse inf and NaN on their own (NaN fails every
# comparison). Removing `JsonNumber`'s finite check therefore fails no HTTP
# test above (mutation M8). It exists for a field with no bounds; it is
# proven here, on the type, where nothing else stands in front of it.

def _unbounded(tp):
    from pydantic import BaseModel

    class Probe(BaseModel):
        v: tp

    return Probe


@pytest.mark.parametrize("bad", NON_FINITE)
def test_json_number_refuses_a_non_finite_value_with_no_bounds(bad):
    from pydantic import ValidationError

    from turab.api.json_types import JsonNumber

    with pytest.raises(ValidationError, match="finite JSON number"):
        _unbounded(JsonNumber).model_validate(json.loads('{"v": %s}' % bad))


@pytest.mark.parametrize("bad", NON_FINITE)
def test_json_integer_refuses_a_non_finite_value_with_no_bounds(bad):
    from pydantic import ValidationError

    from turab.api.json_types import JsonInteger

    with pytest.raises(ValidationError, match="JSON integer"):
        _unbounded(JsonInteger).model_validate(json.loads('{"v": %s}' % bad))


def test_finite_json_refuses_a_non_finite_value_at_depth():
    from pydantic import ValidationError

    from turab.api.json_types import FiniteJson

    deep = json.loads('{"a": [1, {"b": [2, 1e400]}]}')
    with pytest.raises(ValidationError, match="only finite JSON numbers"):
        _unbounded(FiniteJson).model_validate({"v": deep})
    assert _unbounded(FiniteJson).model_validate(
        {"v": json.loads('{"a": [1, {"b": [2, 1e300]}]}')}).v["a"][1]["b"][1] == 1e300


# --- what IS still echoed: registered codes only ------------------------------
#
# After the fix, a typed error echoes a code only once it has MATCHED a
# registry row ("'ROOMS' takes a JSON number"): that text is the registry's,
# not the caller's. It is safe only while no registered code contains a leak
# marker, which this pins against the seeded database.

def test_no_registered_code_contains_a_leak_marker(engine):
    from turab.api.problems import _LEAK_MARKERS

    with Session(bind=engine, future=True) as s:
        codes = s.execute(text(
            "SELECT code FROM turab.attribute_definitions "
            "UNION ALL SELECT option_code FROM turab.attribute_options "
            "UNION ALL SELECT code FROM turab.criterion_definitions "
            "UNION ALL SELECT code FROM turab.reason_codes")).scalars().all()
    assert codes, "the registries are empty; the check would be vacuous"
    marked = [c for c in codes for m in _LEAK_MARKERS if m.lower() in c.lower()]
    assert marked == []
