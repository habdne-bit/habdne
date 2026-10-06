"""Slice 5 step 4: the internal read, the customer read, and the match queue.

Ref: `docs/gate/SLICE_5_PLAN.md`: §3.4, §3.6; G5-5 (a) with [R4-2]; G5-6 (a)
(SUMMARY_ONLY: four fields); G5-7 (a); G5-11; §6.1 mandatory test 5; RFC-001
R8.2, R8.2a, R9.2, R9.5, R6.3 and Appendix B. Scope authorized in the review
of 921ed01: "internal read + customer read + match queue", with "proof of
the withholding and of no leak of any private expectation or claim" as a
condition of acceptance.

**What is a fixture here.** Share is step 5's. A customer sees an
opportunity only once shared (G5-7 (a)), so the tests mark an opportunity
SHARED by SQL (`_share`), labelled so: NEW -> SHARED with `shared_at`, the
edge migration 0006 admits. A changed field after the evaluation ([R4-2]) is
also written by SQL, as an operator's correction would land.

**No new module is imported at module level,** so the whole file collects at
the step's base commit and the before-fix record measures each test. The
pure tests of the withholding import it inside their body.
"""
from __future__ import annotations

import json
import re
import uuid
from decimal import Decimal

import pytest
import yaml
from fastapi.testclient import TestClient

from tests.test_slice4_step7 import (_all, _criterion, _exec, _offer, _one, _request,
                                     _run)
from turab.auth.audit import AccessAuditor, RecordingAuditSink

CONTRACT = yaml.safe_load(open("docs/handoff/05_API/openapi_v0.2.3.yaml"))
SCHEMAS = CONTRACT["components"]["schemas"]
SCOPES = ("SUMMARY_ONLY", "PROPERTY_DETAILS_ALLOWED", "CONTACT_AFTER_CONFIRMATION")
SUMMARY_FIELDS = {"property_id", "property_type", "supply_mode", "canonical_location_id"}


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _get(client, path, account):
    return client.get(path, headers={"Authorization": f"Bearer {account}"})


# --- a minimal validator for the frozen schemas this file asserts ------------------------

def _validate(value, schema, where="$"):
    """The subset of JSON Schema the frozen types use: `$ref`, `type` (one or
    a list), `enum`, `required`, `properties`, `additionalProperties: false`,
    `anyOf`, `items`, and the `uuid` and `date-time` formats."""
    if "$ref" in schema:
        return _validate(value, SCHEMAS[schema["$ref"].rsplit("/", 1)[1]], where)
    if "anyOf" in schema:
        errors = []
        for option in schema["anyOf"]:
            try:
                _validate(value, option, where)
                return
            except AssertionError as exc:
                errors.append(str(exc))
        raise AssertionError(f"{where}: matches no anyOf option: {errors}")
    kinds = schema.get("type")
    if kinds is not None:
        kinds = kinds if isinstance(kinds, list) else [kinds]
        checks = {"object": lambda v: isinstance(v, dict),
                  "array": lambda v: isinstance(v, list),
                  "string": lambda v: isinstance(v, str),
                  "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
                  "number": lambda v: isinstance(v, (int, float, Decimal))
                  and not isinstance(v, bool),
                  "boolean": lambda v: isinstance(v, bool),
                  "null": lambda v: v is None}
        assert any(checks[k](value) for k in kinds), f"{where}: {value!r} is not {kinds}"
    if value is None:
        return
    if "enum" in schema:
        assert value in schema["enum"], f"{where}: {value!r} not in {schema['enum']}"
    if schema.get("format") == "uuid" and isinstance(value, str):
        uuid.UUID(value)
    if schema.get("format") == "date-time" and isinstance(value, str):
        assert re.match(r"\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d", value), f"{where}: {value}"
    if isinstance(value, dict):
        for key in schema.get("required", []):
            assert key in value, f"{where}: missing required {key}"
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            extra = set(value) - set(properties)
            assert not extra, f"{where}: keys the frozen type does not allow: {sorted(extra)}"
        for key, item in value.items():
            if key in properties:
                _validate(item, properties[key], f"{where}.{key}")
    if isinstance(value, list) and "items" in schema:
        for i, item in enumerate(value):
            _validate(item, schema["items"], f"{where}[{i}]")


# --- the world ------------------------------------------------------------------------

def _location(engine, parent=None):
    return _one(engine, """INSERT INTO turab.locations (code, canonical_ar, location_type,
                                                        parent_id)
                           VALUES (:c, 'موقع اختبار', 'AREA', :parent)
                           RETURNING location_id""",
                c=f"TEST-S5-4-{uuid.uuid4().hex[:16]}", parent=parent)


def _claim(engine, prop, attribute, value):
    return _one(engine, """
        INSERT INTO turab.claims (property_id, attribute_code, claimed_value,
                                  effective_verification_level)
        VALUES (:p, :a, CAST(:v AS jsonb), 'DOCUMENT_SEEN') RETURNING claim_id""",
        p=prop, a=attribute, v=json.dumps(value))


def _attribute(engine, prop, code, value, claim=None):
    _exec(engine, """
        INSERT INTO turab.property_attributes (property_id, attribute_definition_id, value,
                                               resolved_claim_id)
        SELECT :p, attribute_definition_id, CAST(:v AS jsonb), :c
          FROM turab.attribute_definitions WHERE code = :code""",
          p=prop, v=json.dumps(value), c=claim, code=code)


def _opportunity(client, engine, ids, *, scope="SUMMARY_ONLY", ptype="LAND", land=400,
                 built=None, desired_type=None, criteria=(), document="LAND_BOOK",
                 document_claim=False, rooms=None, rooms_claim=False, ask=20_000_000,
                 negotiable="NO", expectation=None, location=None, request_location=None,
                 share=True):
    """One APPROVED opportunity, through the real run and the real review, its
    offer's scope set before approval. Returns a dict of the ids."""
    req = _request(engine, ids, desired_type=desired_type)
    if request_location is not None:
        _exec(engine, """UPDATE turab.requests SET primary_location_id = :l,
                                location_importance = 'REQUIRED' WHERE request_id = :r""",
              l=request_location, r=req)
    for order, (code, operator, value, importance) in enumerate(criteria):
        _criterion(engine, req, code, operator, value, importance, sort_order=order)
    prop = _one(engine, """
        INSERT INTO turab.properties (property_type, supply_mode, management_mode, claim_status,
                                      land_area_m2, built_area_m2, canonical_location_id,
                                      availability_last_confirmed_at, current_availability)
        VALUES (CAST(:t AS turab.property_type), 'PUBLIC', 'ASSISTED', 'UNCLAIMED', :land,
                :built, :loc, now() - interval '1 day', 'AVAILABLE')
        RETURNING property_id""", t=ptype, land=land, built=built, loc=location)
    claims = {}
    if document is not None:
        claims["DOCUMENT_TYPE"] = (_claim(engine, prop, "DOCUMENT_TYPE", document)
                                   if document_claim else None)
        _attribute(engine, prop, "DOCUMENT_TYPE", document, claims["DOCUMENT_TYPE"])
    if rooms is not None:
        claims["ROOMS"] = _claim(engine, prop, "ROOMS", rooms) if rooms_claim else None
        _attribute(engine, prop, "ROOMS", rooms, claims["ROOMS"])
    offer = _offer(engine, ids, prop, price=ask, negotiable=negotiable, expectation=expectation)
    _exec(engine, """UPDATE turab.property_offers
                        SET permission_scope = CAST(:s AS turab.sharing_scope)
                      WHERE offer_id = :o""", s=scope, o=offer)
    r = _run(client, ids, req, [prop])
    assert r.status_code == 201, r.text
    [m] = r.json()["matches"]
    assert m["eligibility"] == "ELIGIBLE", m["explanation"]["reasons"]
    approved = client.post(f"/matches/{m['match_id']}/review", json={"decision": "APPROVED"},
                           headers={"Authorization": f"Bearer {ids.ACC_REVIEWER}",
                                    "Idempotency-Key": str(uuid.uuid4())})
    assert approved.status_code == 200, approved.text
    opp = approved.json()["opportunity"]
    if share:
        _share(engine, opp["opportunity_id"])
    return {"request": req, "property": prop, "offer": offer, "match": m,
            "opportunity": uuid.UUID(opp["opportunity_id"]), "approved": opp,
            "claims": claims}


def _share(engine, opportunity_id):
    """FIXTURE: the share operation is step 5's. NEW -> SHARED, with its time."""
    _exec(engine, """UPDATE turab.opportunities SET status = 'SHARED', shared_at = now()
                      WHERE opportunity_id = :o""", o=opportunity_id)


def _customer(client, ids, world, account=None):
    return _get(client, f"/me/opportunities/{world['opportunity']}", account or ids.ACC_BRAHIM)


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _codes(body):
    return ([e["code"] for e in body["why_real"].get("criteria", [])],
            [e["code"] for e in body["known_differences"]])


def _without_ids_and_times(body):
    """Two customer bodies compared as the customer sees them, ids and times
    aside."""
    out = json.loads(json.dumps(body))
    for key in ("opportunity_id", "created_at", "shared_at"):
        out.pop(key, None)
    for key in ("property_id", "canonical_location_id", "availability_last_confirmed_at"):
        out.get("property", {}).pop(key, None)
    return out


# ======================================================================================
# G5-7 (a): who may see an opportunity, and when
# ======================================================================================

def _not_found_shape(response):
    body = response.json()
    body.pop("trace_id", None)
    return response.status_code, body


def test_an_unshared_opportunity_is_answered_as_an_unknown_id(client, engine, ids, sink):
    """G5-7 (a): before `shared_at`, the customer-scoped answer an unknown id
    gets; the attempt is recorded as a denial."""
    world = _opportunity(client, engine, ids, share=False)
    unshared = _customer(client, ids, world)
    unknown = _get(client, f"/me/opportunities/{uuid.uuid4()}", ids.ACC_BRAHIM)
    assert unshared.status_code == 404
    assert _not_found_shape(unshared) == _not_found_shape(unknown)
    assert [r.event.value for r in sink.records
            if r.resource_id == world["opportunity"]] == ["DENIED"]
    _share(engine, world["opportunity"])
    assert _customer(client, ids, world).status_code == 200


def test_another_partys_opportunity_is_answered_as_an_unknown_id(client, engine, ids):
    world = _opportunity(client, engine, ids)
    other = _customer(client, ids, world, account=ids.ACC_AMINA)
    unknown = _get(client, f"/me/opportunities/{uuid.uuid4()}", ids.ACC_AMINA)
    assert _not_found_shape(other) == _not_found_shape(unknown)
    assert other.status_code == 404


def test_a_relation_to_the_property_grants_nothing(client, engine, ids):
    """§7 condition 8 and RFC-001 decision 1: the request's party only; a
    current relation of another party to the property opens nothing."""
    world = _opportunity(client, engine, ids)
    _exec(engine, """INSERT INTO turab.party_property_relations (party_id, property_id,
                                                                 relation_code, valid_from)
                     VALUES (:party, :p, 'OWNER_DECLARED', now() - interval '1 day')""",
          party=ids.AMINA, p=world["property"])
    assert _customer(client, ids, world, account=ids.ACC_AMINA).status_code == 404


# ======================================================================================
# G5-6 (a), RFC-001 Appendix B: the frozen type, key for key (R9.5; F5-1, F5-2, F5-3)
# ======================================================================================

@pytest.mark.parametrize("scope", SCOPES)
def test_the_customer_body_is_the_frozen_type_at_each_scope(client, engine, ids, scope):
    world = _opportunity(client, engine, ids, scope=scope, land=Decimal("137.50"))
    body = _ok(_customer(client, ids, world))
    _validate(body, SCHEMAS["CustomerOpportunityView"])
    assert set(body) == set(SCHEMAS["CustomerOpportunityView"]["properties"])
    assert "contact" not in body, "F5-1: no contact field at any scope"
    if scope == "SUMMARY_ONLY":
        assert set(body["property"]) == SUMMARY_FIELDS, "four fields, no area (F5-2, F5-3)"
    else:
        assert set(body["property"]) == set(SCHEMAS["CustomerPropertyView"]["properties"])
    assert (body["status"], body["sharing_scope"]) == ("SHARED", scope)


def test_an_area_is_an_exact_json_number(client, engine, ids):
    """At PROPERTY_DETAILS_ALLOWED, the area is a JSON number with the stored
    digits (`exact_json`), not a string and not a float's rounding."""
    world = _opportunity(client, engine, ids, scope="PROPERTY_DETAILS_ALLOWED",
                         land=Decimal("1234567.89"))
    r = _customer(client, ids, world)
    assert '"land_area_m2":1234567.89' in r.text.replace(" ", "")
    assert json.loads(r.text, parse_float=Decimal)["property"]["land_area_m2"] == Decimal(
        "1234567.89")


# ======================================================================================
# Mandatory test 5 and §3.4: no private expectation and no claim, at any scope
# ======================================================================================

SENTINEL = 27_777_777
#: A REQUIRED DOCUMENT_TYPE, so the document (and its claim, when there is one)
#: is evaluated: without it the claim would never be read.
DOCUMENT = ("DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")


@pytest.mark.parametrize("scope", SCOPES)
def test_no_private_value_reaches_the_customer_at_any_scope(client, engine, ids, scope):
    """A seller expectation that DECIDES the budget (asking 35M > max 30M,
    expectation 27 777 777 <= 30M: PASS internally, R9.3), and a document
    known from a claim. Neither, nor anything staff-only, is in the body."""
    world = _opportunity(client, engine, ids, scope=scope, ask=35_000_000, negotiable="YES",
                         expectation=SENTINEL, document_claim=True,
                         criteria=[DOCUMENT, ("LAND_AREA_MIN", "GTE", 100, "PREFERRED")])
    budget = [c for c in world["match"]["criteria"] if c["criterion_code"] == "BUDGET_MAX"]
    assert [c["compatibility"] for c in budget] == ["PASS"], "the expectation decided it"
    [document] = [c for c in world["match"]["criteria"] if c["criterion_code"] == "DOCUMENT_TYPE"]
    assert document["evidence_claim_id"] == str(world["claims"]["DOCUMENT_TYPE"]), \
        "the claim stands behind a result the engine used"
    r = _customer(client, ids, world)
    text_ = r.text
    for secret in (str(SENTINEL), "27777777", str(world["claims"]["DOCUMENT_TYPE"]),
                   "LAND_BOOK", "DOCUMENT_TYPE", "BUDGET_MAX", "seller_expectation",
                   "claim", "evidence", "permission_snapshot", "commercial_context",
                   "approved_match_id", "current_offer_id", "binding", "35000000", "delta",
                   "rule", "score", "contact", "phone"):
        assert secret not in text_, (scope, secret)


@pytest.mark.parametrize("scope", SCOPES)
def test_a_claim_behind_the_document_changes_nothing_the_customer_sees(client, engine, ids,
                                                                       scope):
    """G5-5 (a): the fixed list never depends on a claim. A DOCUMENT_TYPE PASS
    backed by a claim, and one backed by none: the two bodies are identical
    apart from ids and times, and neither names DOCUMENT_TYPE."""
    criteria = [DOCUMENT, ("LAND_AREA_MIN", "GTE", 100, "PREFERRED")]
    plain = _opportunity(client, engine, ids, scope=scope, criteria=criteria)
    claimed = _opportunity(client, engine, ids, scope=scope, criteria=criteria,
                           document_claim=True)
    [document] = [c for c in claimed["match"]["criteria"]
                  if c["criterion_code"] == "DOCUMENT_TYPE"]
    assert document["evidence_claim_id"] == str(claimed["claims"]["DOCUMENT_TYPE"])
    a, b = _ok(_customer(client, ids, plain)), _ok(_customer(client, ids, claimed))
    assert _without_ids_and_times(a) == _without_ids_and_times(b)
    assert "DOCUMENT_TYPE" not in json.dumps(a) + json.dumps(b)


@pytest.mark.parametrize("scope", SCOPES)
def test_a_claim_behind_the_rooms_changes_nothing_the_customer_sees(client, engine, ids,
                                                                    scope):
    """The same pair for ROOMS_MIN: an APARTMENT whose ROOMS is known from a
    claim, and one whose ROOMS is plain."""
    kw = dict(scope=scope, ptype="APARTMENT", land=None, built=Decimal("90"), document=None,
              criteria=[("ROOMS_MIN", "GTE", 3, "REQUIRED")], rooms=4)
    plain = _opportunity(client, engine, ids, **kw)
    claimed = _opportunity(client, engine, ids, rooms_claim=True, **kw)
    a, b = _ok(_customer(client, ids, plain)), _ok(_customer(client, ids, claimed))
    assert _without_ids_and_times(a) == _without_ids_and_times(b)
    assert "ROOMS" not in json.dumps(a) + json.dumps(b)
    assert str(claimed["claims"]["ROOMS"]) not in json.dumps(b)


@pytest.mark.parametrize("scope", SCOPES)
def test_a_budget_decided_by_the_expectation_leaves_no_trace(client, engine, ids, scope):
    """S36 / R9.3: BUDGET_MAX PASS by the asking price, and PASS by the seller
    expectation. The bodies are identical apart from ids and times."""
    by_price = _opportunity(client, engine, ids, scope=scope, ask=20_000_000)
    by_expectation = _opportunity(client, engine, ids, scope=scope, ask=35_000_000,
                                  negotiable="YES", expectation=SENTINEL)
    a, b = _ok(_customer(client, ids, by_price)), _ok(_customer(client, ids, by_expectation))
    assert _without_ids_and_times(a) == _without_ids_and_times(b)
    assert str(SENTINEL) not in json.dumps(b)


@pytest.mark.parametrize("scope", SCOPES)
def test_location_is_never_named(client, engine, ids, scope):
    """[R3-5]: a REQUIRED LOCATION PASS by an ANCESTOR, and one PASS by the
    property's own location. Neither body names LOCATION, at any scope."""
    parent = _location(engine)
    child = _location(engine, parent)
    by_ancestor = _opportunity(client, engine, ids, scope=scope, location=child,
                               request_location=parent)
    by_own = _opportunity(client, engine, ids, scope=scope, location=parent,
                          request_location=parent)
    for world in (by_ancestor, by_own):
        [loc] = [c for c in world["match"]["criteria"] if c["criterion_code"] == "LOCATION"]
        assert loc["compatibility"] == "PASS"
    a, b = _ok(_customer(client, ids, by_ancestor)), _ok(_customer(client, ids, by_own))
    assert "LOCATION" not in json.dumps(a) + json.dumps(b)
    assert _without_ids_and_times(a) == _without_ids_and_times(b)


# ======================================================================================
# [R4-2]: an entry is withheld when its field changed since the evaluation
# ======================================================================================

AREA = [("LAND_AREA_MIN", "GTE", 120, "PREFERRED")]


def _land(engine, world, value):
    """FIXTURE: an operator's correction of the area, after the evaluation."""
    _exec(engine, "UPDATE turab.properties SET land_area_m2 = :v WHERE property_id = :p",
          v=value, p=world["property"])


def test_the_withholding_follows_the_current_area(client, engine, ids):
    """Over HTTP at PROPERTY_DETAILS_ALLOWED, the plan's four cases in order:
    - unchanged (137.5): LAND_AREA_MIN present;
    - corrected to 110, the outcome flipped: absent from the customer body,
      present in the internal view's stored `why_real`;
    - 150, the outcome unchanged: still absent, the comparison is on the value;
    - back to 137.5: present again, the comparison is made at each render."""
    world = _opportunity(client, engine, ids, scope="PROPERTY_DETAILS_ALLOWED",
                         land=Decimal("137.5"), criteria=AREA)
    assert "LAND_AREA_MIN" in _codes(_ok(_customer(client, ids, world)))[0]
    for value, shown in ((Decimal("110"), False), (Decimal("150"), False),
                         (Decimal("137.50"), True)):
        _land(engine, world, value)
        body = _ok(_customer(client, ids, world))
        assert ("LAND_AREA_MIN" in _codes(body)[0]) is shown, value
        assert body["property"]["land_area_m2"] == float(value)
        internal = _ok(_get(client, f"/opportunities/{world['opportunity']}",
                            ids.ACC_REVIEWER))
        assert "LAND_AREA_MIN" in [e["code"] for e in internal["why_real"]["criteria"]]
    assert json.loads(_one(engine, "SELECT why_real::text FROM turab.opportunities "
                                   "WHERE opportunity_id = :o", o=world["opportunity"])
                      ) == world["approved"]["why_real"], "the stored row is never touched"


@pytest.mark.parametrize("scope", SCOPES)
def test_a_changed_property_type_withholds_property_type_at_every_scope(client, engine,
                                                                        ids, scope):
    world = _opportunity(client, engine, ids, scope=scope, desired_type="LAND")
    assert "PROPERTY_TYPE" in _codes(_ok(_customer(client, ids, world)))[0]
    _exec(engine, "UPDATE turab.properties SET property_type = 'OTHER' WHERE property_id = :p",
          p=world["property"])
    body = _ok(_customer(client, ids, world))
    assert "PROPERTY_TYPE" not in _codes(body)[0] + _codes(body)[1]
    assert body["property"]["property_type"] == "OTHER"


def test_at_summary_only_an_area_change_cannot_show(client, engine, ids):
    world = _opportunity(client, engine, ids, scope="SUMMARY_ONLY", land=Decimal("137.5"),
                         criteria=AREA)
    for value in (None, Decimal("110")):
        if value is not None:
            _land(engine, world, value)
        body = _ok(_customer(client, ids, world))
        assert "LAND_AREA_MIN" not in _codes(body)[0] + _codes(body)[1]
        assert "land_area_m2" not in body["property"]


def test_an_unknown_difference_stays_while_the_area_is_still_unknown(client, engine, ids):
    """`known_differences`: BUILT_AREA_MIN is UNKNOWN because no built area was
    recorded. Still none: the same value, the entry stays. Recorded since:
    withheld."""
    world = _opportunity(client, engine, ids, scope="PROPERTY_DETAILS_ALLOWED",
                         criteria=[("BUILT_AREA_MIN", "GTE", 80, "FLEXIBLE")])
    assert _codes(_ok(_customer(client, ids, world)))[1] == ["BUILT_AREA_MIN"]
    _exec(engine, "UPDATE turab.properties SET built_area_m2 = 95 WHERE property_id = :p",
          p=world["property"])
    assert _codes(_ok(_customer(client, ids, world)))[1] == []


def test_the_withholding_compares_exact_values_and_fails_closed():
    """Pure. 137.5 and 137.50 are one value; an unlisted code, or a code not
    shown at the scope, is dropped."""
    from turab.services.opportunity_views import withheld

    entries = [{"code": "LAND_AREA_MIN", "label_ar": "x", "importance": "PREFERRED"},
               {"code": "PROPERTY_TYPE", "label_ar": "y", "importance": "REQUIRED"},
               {"code": "DOCUMENT_TYPE", "label_ar": "z", "importance": "REQUIRED"}]
    snapshot = {"land_area_m2": Decimal("137.5"), "property_type": "LAND"}
    same = {"land_area_m2": Decimal("137.50"), "property_type": "LAND"}
    assert [e["code"] for e in withheld(entries, "PROPERTY_DETAILS_ALLOWED",
                                        snapshot=snapshot, current=same)] == [
        "LAND_AREA_MIN", "PROPERTY_TYPE"]
    assert [e["code"] for e in withheld(entries, "SUMMARY_ONLY", snapshot=snapshot,
                                        current=same)] == ["PROPERTY_TYPE"]
    changed = {"land_area_m2": Decimal("137.51"), "property_type": "LAND"}
    assert [e["code"] for e in withheld(entries, "PROPERTY_DETAILS_ALLOWED",
                                        snapshot=snapshot, current=changed)] == [
        "PROPERTY_TYPE"]


# ======================================================================================
# The internal read (staff, recorded, unfiltered)
# ======================================================================================

@pytest.mark.parametrize("account", ["ACC_ADMIN", "ACC_OPERATOR", "ACC_REVIEWER"])
def test_staff_read_the_stored_opportunity_and_the_read_is_recorded(client, engine, ids, sink,
                                                                    account):
    world = _opportunity(client, engine, ids, share=False)
    body = _ok(_get(client, f"/opportunities/{world['opportunity']}", getattr(ids, account)))
    assert set(body) == set(SCHEMAS["InternalOpportunityView"]["properties"])
    _validate(body, SCHEMAS["InternalOpportunityView"])
    assert body == world["approved"], "the stored row, as the approval returned it"
    assert [(r.event.value, r.resource_kind) for r in sink.records
            if r.resource_id == world["opportunity"]] == [("READ", "OPPORTUNITY")]


def test_an_unknown_opportunity_is_403_for_staff_and_recorded(client, ids, sink):
    unknown = uuid.uuid4()
    r = _get(client, f"/opportunities/{unknown}", ids.ACC_REVIEWER)
    assert (r.status_code, r.json()["code"]) == (403, "OBJECT_NOT_AUTHORIZED")
    assert [(r_.event.value, r_.resource_kind) for r_ in sink.records
            if r_.resource_id == unknown] == [("DENIED", "OPPORTUNITY")]


def test_a_customer_cannot_use_the_internal_read(client, engine, ids):
    world = _opportunity(client, engine, ids)
    r = _get(client, f"/opportunities/{world['opportunity']}", ids.ACC_BRAHIM)
    assert (r.status_code, r.json()["code"]) == (403, "ROLE_NOT_PERMITTED")


# ======================================================================================
# G5-11: the match queue
# ======================================================================================

def _queue(client, account):
    r = _get(client, "/backoffice/queues/matches", account)
    assert r.status_code == 200, r.text
    _validate(r.json(), SCHEMAS["QueuePage"])
    return r.json()


def _one_match(client, engine, ids, *, kind="ELIGIBLE", offers=1):
    from tests.test_slice5_step3 import _non_eligible, _world

    if kind == "ELIGIBLE":
        return _world(client, engine, ids, offers=offers)[3]
    return [_non_eligible(client, engine, ids, kind)]


def test_the_queue_holds_the_matches_awaiting_a_decision(client, engine, ids):
    """G5-11 membership, priority and reason, on real matches."""
    [eligible] = _one_match(client, engine, ids)
    [awaiting] = _one_match(client, engine, ids)
    client.post(f"/matches/{awaiting['match_id']}/review",
                json={"decision": "NEED_MORE_INFORMATION", "reason_code": "REQUEST_STALE"},
                headers={"Authorization": f"Bearer {ids.ACC_REVIEWER}",
                         "Idempotency-Key": str(uuid.uuid4())})
    [permission] = _one_match(client, engine, ids, kind="PERMISSION")
    [freshness] = _one_match(client, engine, ids, kind="FRESHNESS")
    [information] = _one_match(client, engine, ids, kind="INFORMATION")
    [rejected_run] = _one_match(client, engine, ids, kind="HARD")
    [rejected_review] = _one_match(client, engine, ids)
    client.post(f"/matches/{rejected_review['match_id']}/review",
                json={"decision": "REJECTED", "reason_code": "OTHER"},
                headers={"Authorization": f"Bearer {ids.ACC_REVIEWER}",
                         "Idempotency-Key": str(uuid.uuid4())})
    [approved] = _one_match(client, engine, ids)
    client.post(f"/matches/{approved['match_id']}/review", json={"decision": "APPROVED"},
                headers={"Authorization": f"Bearer {ids.ACC_REVIEWER}",
                         "Idempotency-Key": str(uuid.uuid4())})
    items = {i["id"]: i for i in _queue(client, ids.ACC_OPERATOR)["items"]}
    expected = {
        eligible["match_id"]: ("HIGH", "READY_FOR_REVIEW"),
        awaiting["match_id"]: ("HIGH", "AWAITING_INFORMATION"),
        permission["match_id"]: ("NORMAL", "PERMISSION_MISSING"),
        freshness["match_id"]: ("NORMAL", "NEVER_CONFIRMED"),
        information["match_id"]: ("NORMAL", "DOCUMENT_NOT_KNOWN"),
    }
    for match_id, (priority, reason) in expected.items():
        assert (items[match_id]["kind"], items[match_id]["priority"],
                items[match_id]["reason"]) == ("MATCH", priority, reason), match_id
    for absent in (rejected_run, rejected_review, approved):
        assert absent["match_id"] not in items


def test_the_queue_keeps_each_offers_current_match_only(client, engine, ids):
    """Two offers, two items; a new evaluation of one offer replaces that
    offer's item only (G5-2, per offer)."""
    from tests.test_slice5_step3 import _world

    req, prop, [o1, o2], [m1, m2] = _world(client, engine, ids, offers=2)
    items = {i["id"] for i in _queue(client, ids.ACC_REVIEWER)["items"]}
    assert {m1["match_id"], m2["match_id"]} <= items
    _exec(engine, """UPDATE turab.property_offers SET asking_price_dzd = 21000000,
                            version = version + 1 WHERE offer_id = :o""", o=o1)
    after = {m["evaluated_offer_id"]: m["match_id"]
             for m in _run(client, ids, req, [prop]).json()["matches"]}
    items = {i["id"] for i in _queue(client, ids.ACC_REVIEWER)["items"]}
    assert after[str(o1)] in items and m2["match_id"] in items
    assert m1["match_id"] not in items, "superseded"


def test_an_aliased_propertys_match_leaves_the_queue(client, engine, ids):
    from tests.test_slice5_step3 import _make_alias, _world

    req, prop, _, [m] = _world(client, engine, ids)
    assert m["match_id"] in {i["id"] for i in _queue(client, ids.ACC_REVIEWER)["items"]}
    from tests.test_slice4_step7 import _property

    _make_alias(engine, ids, prop, _property(engine))
    assert m["match_id"] not in {i["id"] for i in _queue(client, ids.ACC_REVIEWER)["items"]}


def test_the_queue_is_ordered_high_first_and_audited_once_with_its_count(client, engine, ids,
                                                                         sink):
    _one_match(client, engine, ids)
    _one_match(client, engine, ids, kind="PERMISSION")
    page = _queue(client, ids.ACC_ADMIN)
    ranks = [{"HIGH": 0, "NORMAL": 1}[i["priority"]] for i in page["items"]]
    assert ranks == sorted(ranks)
    assert page["next_cursor"] is None
    [listed] = [r for r in sink.records if r.event.value == "LIST"
                and r.operation_id == "getBackofficeQueuesMatches"]
    assert listed.result_count == len(page["items"]) and listed.resource_id is None


def test_a_customer_cannot_read_the_match_queue(client, ids):
    r = _get(client, "/backoffice/queues/matches", ids.ACC_AMINA)
    assert (r.status_code, r.json()["code"]) == (403, "ROLE_NOT_PERMITTED")
