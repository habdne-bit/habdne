"""Slice 4 step 2: the canonical form, the input hash, the rule registry, the
policy loader and the snapshots.

Ref: `docs/gate/SLICE_4_PLAN.md` revision 3, G4-2 and G4-13 (decided in the
review of aad9f34) and §3.1; `docs/gate/SLICE_4_STEP2_DELIVERY.md`.

No match is produced here. The schema-level tests at the end insert FIXTURE
match rows. They prove what the hash does against the real uniqueness
constraint, which is the condition the review attached to G4-13. The
engine's own run is step 7.
"""
from __future__ import annotations

import ast
import datetime as dt
import importlib.util
import pathlib
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.matching import canonical, policy, registry, snapshots
from turab.services import freshness

ROOT = pathlib.Path(__file__).resolve().parents[1]
MATCHING = ROOT / "src" / "turab" / "matching"


# ======================================================================================
# The canonical form (G4-13)
# ======================================================================================

def test_key_order_does_not_change_the_bytes():
    assert canonical.canonical_bytes({"b": 1, "a": {"y": 2, "x": 3}}) == \
        canonical.canonical_bytes({"a": {"x": 3, "y": 2}, "b": 1})


@pytest.mark.parametrize("value", [0.5, {"a": 0.1}, [1, 2.0], {"deep": [{"x": 3.25}]}])
def test_a_float_is_refused_wherever_it_is(value):
    with pytest.raises(canonical.CanonicalError, match="float"):
        canonical.canonical_bytes(value)


def test_numbers_are_json_numbers_written_by_value():
    forms = [Decimal("268.50"), Decimal("268.5"), Decimal("2.685E+2"), Decimal("268.500000")]
    assert {canonical.canonical_bytes(d) for d in forms} == {b"268.5"}
    assert canonical.canonical_bytes(Decimal("-0")) == canonical.canonical_bytes(Decimal("0E-2")) \
        == b"0"
    assert canonical.canonical_bytes(Decimal("1E+2")) == canonical.canonical_bytes(100) == b"100"
    assert canonical.canonical_bytes(Decimal("0.00012")) == b"0.00012", "plain, never 1.2E-4"
    assert canonical.canonical_bytes(Decimal("-12.340")) == b"-12.34"


# --- review of 4538a2d: two collisions BEFORE sha256 -----------------------------------
#
# Revision 1 wrote every Decimal as a JSON string through Decimal.normalize().
# Reproduced on 4538a2d: evidence/SLICE4-STEP2-CANONICAL-BEFORE-FIX.txt.

def test_a_json_number_and_a_json_string_never_share_bytes():
    """The jsonb reader turns the JSON number 1 into Decimal('1'). The JSON
    string "1" stays a string. In revision 1 both were written "1"."""
    number = {"value": snapshots.exact_json("1")}
    string = {"value": snapshots.exact_json('"1"')}
    assert canonical.canonical_bytes(number) == b'{"value":1}'
    assert canonical.canonical_bytes(string) == b'{"value":"1"}'
    assert canonical.input_hash(**_inputs(request_snapshot=number)) != \
        canonical.input_hash(**_inputs(request_snapshot=string))


TWENTY_NINE_ONE = Decimal("1.00000000000000000000000000001")
TWENTY_NINE_TWO = Decimal("1.00000000000000000000000000002")


@pytest.mark.parametrize("precision", [3, 28, 40, 200])
def test_every_digit_is_kept_whatever_the_decimal_context(precision):
    """Revision 1 used normalize(), which ROUNDS to the context precision
    (28 by default): these two values were both written "1". The form is
    now built from as_tuple(), so it is exact and context-free."""
    import decimal

    with decimal.localcontext() as ctx:
        ctx.prec = precision
        one = canonical.canonical_bytes({"value": TWENTY_NINE_ONE})
        two = canonical.canonical_bytes({"value": TWENTY_NINE_TWO})
        h1 = canonical.input_hash(**_inputs(request_snapshot={"value": TWENTY_NINE_ONE}))
        h2 = canonical.input_hash(**_inputs(request_snapshot={"value": TWENTY_NINE_TWO}))
    assert one == b'{"value":1.00000000000000000000000000001}'
    assert two == b'{"value":1.00000000000000000000000000002}'
    assert h1 != h2


def test_the_hash_of_one_value_does_not_depend_on_the_decimal_context():
    import decimal

    hashes = set()
    for precision in (3, 28, 200):
        with decimal.localcontext() as ctx:
            ctx.prec = precision
            hashes.add(canonical.input_hash(**_inputs(
                request_snapshot={"value": TWENTY_NINE_ONE, "area": Decimal("268.50")})))
    assert len(hashes) == 1


def test_a_number_beyond_the_size_bound_is_refused_not_truncated():
    with pytest.raises(canonical.CanonicalError, match="1000 digits"):
        canonical.canonical_bytes(Decimal("1E+1000"))
    with pytest.raises(canonical.CanonicalError, match="1000 digits"):
        canonical.canonical_bytes(10 ** 1000)
    assert canonical.canonical_bytes(Decimal("1E+998")) == b"1" + b"0" * 998


@pytest.mark.parametrize("value", [Decimal("NaN"), Decimal("Infinity"), Decimal("-Infinity")])
def test_a_non_finite_decimal_is_refused(value):
    with pytest.raises(canonical.CanonicalError, match="non-finite"):
        canonical.canonical_bytes(value)


def test_one_instant_gives_one_string_whatever_its_zone():
    utc = dt.datetime(2026, 9, 26, 12, 0, tzinfo=dt.timezone.utc)
    algiers = utc.astimezone(dt.timezone(dt.timedelta(hours=1)))
    assert canonical.canonical_bytes(utc) == canonical.canonical_bytes(algiers) == \
        b'"2026-09-26T12:00:00.000000Z"'


def test_a_naive_datetime_is_refused():
    with pytest.raises(canonical.CanonicalError, match="naive"):
        canonical.canonical_bytes(dt.datetime(2026, 9, 26, 12, 0))


@pytest.mark.parametrize("value", [{1: "a"}, {"a": {2: "b"}}])
def test_a_non_string_key_is_refused(value):
    with pytest.raises(canonical.CanonicalError, match="not a string"):
        canonical.canonical_bytes(value)


@pytest.mark.parametrize("value", [{1, 2}, b"bytes", object()])
def test_an_unknown_type_is_refused_not_stringified(value):
    with pytest.raises(canonical.CanonicalError, match="no canonical form"):
        canonical.canonical_bytes(value)


def test_arabic_is_hashed_as_written_and_a_bool_is_not_an_integer():
    assert canonical.canonical_bytes({"ar": "الموقع"}) == '{"ar":"الموقع"}'.encode("utf-8")
    assert canonical.canonical_bytes(True) != canonical.canonical_bytes(1)


def test_the_canonical_form_is_pinned():
    """A golden vector. Changing the canonical form changes every stored
    hash's meaning, so it must be a deliberate change that fails here."""
    doc = {"z": [Decimal("1.50"), 3, None, True], "a": "ب",
           "t": dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc),
           "d": dt.date(2026, 1, 2), "u": uuid.UUID("F4000000-0000-4000-8000-000000000001")}
    assert canonical.canonical_bytes(doc) == (
        '{"a":"ب","d":"2026-01-02","t":"2026-01-01T00:00:00.000000Z",'
        '"u":"f4000000-0000-4000-8000-000000000001","z":[1.5,3,null,true]}').encode("utf-8")


# ======================================================================================
# The input hash (G4-13)
# ======================================================================================

POLICY_ID = uuid.UUID("00000000-0000-4000-8000-00000000aaaa")
OFFER_A = uuid.UUID("00000000-0000-4000-8000-0000000000a1")
OFFER_B = uuid.UUID("00000000-0000-4000-8000-0000000000b2")


def _inputs(**over):
    base = {"matching_policy_id": POLICY_ID, "matching_policy_version": "0.2.0",
            "rule_registry_digest": "d" * 64, "evaluated_offer_id": OFFER_A,
            "request_snapshot": {"budget_max_dzd": 25000000},
            "property_snapshot": {"land_area_m2": Decimal("300.00")},
            "commercial_context_snapshot": {"asking_price_dzd": 24000000},
            "permission_snapshot": {}, "freshness_snapshot": {}}
    return {**base, **over}


def test_the_same_inputs_give_the_same_hash():
    assert canonical.input_hash(**_inputs()) == canonical.input_hash(**_inputs())
    assert len(canonical.input_hash(**_inputs())) == 64


@pytest.mark.parametrize("key, value", [
    ("matching_policy_id", uuid.UUID("00000000-0000-4000-8000-00000000bbbb")),
    ("matching_policy_version", "0.3.0"),
    ("rule_registry_digest", "e" * 64),
    ("evaluated_offer_id", OFFER_B),
    ("evaluated_offer_id", None),
    ("request_snapshot", {"budget_max_dzd": 25000001}),
    ("property_snapshot", {"land_area_m2": Decimal("300.01")}),
    ("commercial_context_snapshot", {"asking_price_dzd": 24000001}),
    ("permission_snapshot", {"binding": "x"}),
    ("freshness_snapshot", {"request": "x"}),
])
def test_every_input_changes_the_hash(key, value):
    assert canonical.input_hash(**_inputs(**{key: value})) != canonical.input_hash(**_inputs())


def test_two_offers_on_identical_terms_hash_differently():
    """The condition of the review of aad9f34. The two commercial snapshots
    are made IDENTICAL on purpose, so the difference can come only from
    `evaluated_offer_id` being a top-level input."""
    same_terms = {"asking_price_dzd": 24000000, "transaction_type": "SALE"}
    a = canonical.input_hash(**_inputs(evaluated_offer_id=OFFER_A,
                                       commercial_context_snapshot=same_terms))
    b = canonical.input_hash(**_inputs(evaluated_offer_id=OFFER_B,
                                       commercial_context_snapshot=same_terms))
    assert a != b


@pytest.mark.parametrize("snapshot", [
    {"evaluated_at": "2026-09-26T00:00:00Z"},
    {"input_hash": "x"},
])
def test_the_engines_own_stamp_is_refused_at_a_snapshots_top_level(snapshot):
    with pytest.raises(canonical.CanonicalError, match="not a matching input"):
        canonical.input_hash(**_inputs(request_snapshot=snapshot))


def test_the_same_names_inside_user_data_are_hashed_like_any_value():
    """Review of 4538a2d. Revision 1 searched every depth, and refused a
    criterion whose jsonb value was {"evaluated_at": "2012-03-04"}. That is
    the customer's data: it is hashed, and a change to it changes the hash."""
    def snap(day):
        return {"criteria": [{"criterion_code": "CUSTOM_ATTRIBUTE",
                              "value": {"evaluated_at": day, "input_hash": "their text"}}]}
    first = canonical.input_hash(**_inputs(request_snapshot=snap("2012-03-04")))
    again = canonical.input_hash(**_inputs(request_snapshot=snap("2012-03-04")))
    other = canonical.input_hash(**_inputs(request_snapshot=snap("2012-03-05")))
    assert first == again != other


def test_no_input_can_be_left_out():
    inputs = _inputs()
    inputs.pop("freshness_snapshot")
    with pytest.raises(TypeError):
        canonical.input_hash(**inputs)


def test_the_input_hash_is_the_sha256_of_this_exact_document():
    """Derived independently: the canonical document is written out BY HAND
    here, so the test pins the format and the set of inputs, not merely a
    value the implementation happened to produce."""
    import hashlib

    written_out = (
        '{"commercial_context_snapshot":{"asking_price_dzd":24000000},'
        '"evaluated_offer_id":"00000000-0000-4000-8000-0000000000a1",'
        '"format":"turab.match-input/2",'
        '"freshness_snapshot":{},'
        '"matching_policy_id":"00000000-0000-4000-8000-00000000aaaa",'
        '"matching_policy_version":"0.2.0",'
        '"permission_snapshot":{},'
        '"property_snapshot":{"land_area_m2":300},'
        '"request_snapshot":{"budget_max_dzd":25000000},'
        f'"rule_registry_digest":"{"d" * 64}"}}').encode("utf-8")
    assert canonical.input_hash(**_inputs()) == hashlib.sha256(written_out).hexdigest()


# ======================================================================================
# The rule registry (G4-2)
# ======================================================================================

def _rules_module(tmp_path, name, source):
    """A module written to disk, so `inspect.getsource` reads real source."""
    path = tmp_path / f"{name}.py"
    path.write_text(source, encoding="utf-8")
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


V1 = "def price_v1(ask, cap):\n    return ask <= cap\n"
V2 = "def price_v2(ask, cap):\n    return ask < cap\n"


def test_a_new_version_is_registered_beside_the_old_and_both_resolve(tmp_path):
    m = _rules_module(tmp_path, "rules_a", V1 + V2)
    reg = registry.RuleRegistry()
    reg.register("BUDGET_MAX.offer_price", "1")(m.price_v1)
    reg.register("BUDGET_MAX.offer_price", "2")(m.price_v2)
    assert reg.versions("BUDGET_MAX.offer_price") == ("1", "2")
    assert reg.resolve("BUDGET_MAX.offer_price", "1").evaluate(5, 5) is True
    assert reg.resolve("BUDGET_MAX.offer_price", "2").evaluate(5, 5) is False


def test_a_second_implementation_of_one_version_is_refused(tmp_path):
    m = _rules_module(tmp_path, "rules_b", V1 + V2)
    reg = registry.RuleRegistry()
    reg.register("R", "1")(m.price_v1)
    with pytest.raises(registry.RegistryError, match="NEW version"):
        reg.register("R", "1")(m.price_v2)


@pytest.mark.parametrize("rule_id, version", [("", "1"), ("R", ""), ("R@x", "1"), (" R", "1")])
def test_an_ill_formed_id_or_version_is_refused(rule_id, version):
    with pytest.raises(registry.RegistryError, match="invalid"):
        registry.RuleRegistry().register(rule_id, version)


def test_an_unimplemented_version_does_not_resolve():
    with pytest.raises(registry.UnknownRuleVersion):
        registry.RuleRegistry().resolve("R", "1")


def test_the_digest_covers_every_version_and_ignores_registration_order(tmp_path):
    m = _rules_module(tmp_path, "rules_c", V1 + V2)
    one, two, both = registry.RuleRegistry(), registry.RuleRegistry(), registry.RuleRegistry()
    one.register("R", "1")(m.price_v1)
    two.register("R", "2")(m.price_v2)
    two.register("R", "1")(m.price_v1)
    both.register("R", "1")(m.price_v1)
    both.register("R", "2")(m.price_v2)
    assert two.digest() == both.digest() != one.digest()


def test_the_digest_changes_when_a_rule_source_changes_under_the_same_version(tmp_path):
    """The digest is an input of the match hash (G4-13). A rule whose code
    changed must therefore change it, even before the pin check refuses the
    change. Found by mutation S13, which survived without this test."""
    old = _rules_module(tmp_path, "rules_g1", V1)
    new = _rules_module(tmp_path, "rules_g2", V1.replace("<=", "<"))
    a, b = registry.RuleRegistry(), registry.RuleRegistry()
    a.register("R", "1")(old.price_v1)
    b.register("R", "1")(new.price_v1)
    assert a.digest() != b.digest()


def test_a_rule_changed_without_a_version_bump_is_reported(tmp_path):
    old = _rules_module(tmp_path, "rules_old", V1)
    pinned = registry.RuleRegistry()
    pinned.register("R", "1")(old.price_v1)
    pins = {r.key: r.source_sha256() for r in pinned.rules()}
    new = _rules_module(tmp_path, "rules_new", V1.replace("<=", "<"))
    edited = registry.RuleRegistry()
    edited.register("R", "1")(new.price_v1)
    assert pinned.verify_pins(pins) == []
    assert any("changed without a version bump" in p for p in edited.verify_pins(pins))


def test_a_pinned_version_that_is_no_longer_implemented_is_reported(tmp_path):
    m = _rules_module(tmp_path, "rules_d", V1 + V2)
    reg = registry.RuleRegistry()
    reg.register("R", "2")(m.price_v2)
    pins = {"R@1": "0" * 64, "R@2": reg.resolve("R", "2").source_sha256()}
    assert reg.verify_pins(pins) == [
        "R@1 is pinned but no longer implemented: every match citing it can no longer be "
        "replayed"]


def test_an_unpinned_version_is_reported(tmp_path):
    m = _rules_module(tmp_path, "rules_e", V1)
    reg = registry.RuleRegistry()
    reg.register("R", "1")(m.price_v1)
    assert any("not pinned" in p for p in reg.verify_pins({}))


def test_the_production_registry_agrees_with_the_committed_pins():
    """The standing guard. Empty in step 2; from step 4 every rule is pinned."""
    assert registry.REGISTRY.verify_pins(registry.load_pins()) == []


def test_the_pin_file_is_data_and_is_refused_when_malformed(tmp_path):
    bad = tmp_path / "pins.py"
    bad.write_text("FORMAT = 2\nPINS = {}\n")
    with pytest.raises(registry.RegistryError, match="not a rule pin file"):
        registry.load_pins(bad)
    evil = tmp_path / "evil.py"
    evil.write_text("FORMAT = 1\nPINS = dict(a=__import__('os').getcwd())\n")
    with pytest.raises(ValueError):
        registry.load_pins(evil)


def test_the_pin_tool_only_adds_and_refuses_to_move_a_pin(tmp_path, monkeypatch):
    spec = importlib.util.spec_from_file_location("pin_rules", ROOT / "db/dev/pin_rules.py")
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    pins_file = tmp_path / "rule_pins.py"
    pins_file.write_text(registry.render_pins({}))
    monkeypatch.setattr(registry, "PINS_PATH", pins_file)
    m1 = _rules_module(tmp_path, "rules_f1", V1)
    reg = registry.RuleRegistry()
    reg.register("R", "1")(m1.price_v1)
    monkeypatch.setattr(registry, "REGISTRY", reg)
    assert tool.main([]) == 0
    first = registry.load_pins(pins_file)
    assert list(first) == ["R@1"]

    m2 = _rules_module(tmp_path, "rules_f2", V1.replace("<=", "<"))
    edited = registry.RuleRegistry()
    edited.register("R", "1")(m2.price_v1)
    monkeypatch.setattr(registry, "REGISTRY", edited)
    before = pins_file.read_bytes()
    assert tool.main([]) == 1
    assert pins_file.read_bytes() == before, "a refused run writes nothing"

    monkeypatch.setattr(registry, "REGISTRY", registry.RuleRegistry())
    assert tool.main([]) == 1, "a pinned version that vanished is refused too"


# ======================================================================================
# The policy loader (§3.1) and CORRECTION-004's version rule
# ======================================================================================

def test_the_seeded_policy_loads(session):
    active = policy.load_active_policy(session)
    assert active.version == "0.2.0"
    assert dict(active.freshness_threshold_days) == {"request": 30, "property": 30,
                                                     "offer_terms": 14}


def _activate_variant(session, patch_sql):
    """Deactivate 0.2.0 and activate a NEW policy derived from it. 0005
    forbids editing an immutable policy, so a variant is a new row."""
    session.execute(text("UPDATE turab.matching_policies SET active = false WHERE active"))
    session.execute(text(f"""INSERT INTO turab.matching_policies (version, name, rules, active)
                             SELECT 'test-variant', name, {patch_sql}, true
                               FROM turab.matching_policies WHERE version = '0.2.0'"""))


@pytest.mark.parametrize("patch_sql, message", [
    ("jsonb_set(rules, '{automatic_request_relaxation}', 'true')", "automatic_request_relaxation"),
    ("rules - 'automatic_request_relaxation'", "automatic_request_relaxation"),
    ("jsonb_set(rules, '{human_review_required_for_opportunity}', 'false')",
     "human_review_required"),
    ("jsonb_set(rules, '{hard_gate,unknown_required}', '\"REJECTED\"')", "hard_gate"),
])
def test_a_policy_this_engine_does_not_implement_is_refused(session, patch_sql, message):
    _activate_variant(session, patch_sql)
    with pytest.raises(policy.PolicyNotImplemented, match=message):
        policy.load_active_policy(session)


def test_no_active_policy_is_refused_not_defaulted(session):
    session.execute(text("UPDATE turab.matching_policies SET active = false WHERE active"))
    with pytest.raises(freshness.NoActiveFreshnessPolicy):
        policy.load_active_policy(session)


def test_the_active_version_is_accepted(session):
    policy.require_active_version(policy.load_active_policy(session), "0.2.0")


@pytest.mark.parametrize("requested", [None, "0.1.0", "inactive-9", 2, "0.2.0 "])
def test_any_other_version_is_refused_without_echoing_it(session, requested):
    session.execute(text("""INSERT INTO turab.matching_policies (version, name, rules)
                            VALUES ('inactive-9', 'inactive', '{}')"""))
    active = policy.load_active_policy(session)
    with pytest.raises(policy.PolicyVersionRefused) as refused:
        policy.require_active_version(active, requested)
    if isinstance(requested, str):
        assert requested.strip() not in str(refused.value)


# ======================================================================================
# The snapshots (§6)
# ======================================================================================

def _floats(value, path="$"):
    if isinstance(value, float):
        return [path]
    if isinstance(value, dict):
        return [p for k, v in value.items() for p in _floats(v, f"{path}.{k}")]
    if isinstance(value, list):
        return [p for i, v in enumerate(value) for p in _floats(v, f"{path}[{i}]")]
    return []


@pytest.fixture
def request_id(session, ids):
    rid = session.execute(text("""
        INSERT INTO turab.requests (party_id, transaction_intent, management_mode, claim_status,
                                    desired_property_type, budget_max_dzd)
        VALUES (:p, 'BUY', 'ASSISTED', 'UNCLAIMED', 'APARTMENT', 25000000)
        RETURNING request_id"""), {"p": ids.BRAHIM}).scalar_one()
    for code, op, value, order in (("ROOMS_MIN", "GTE", "3.50", 20),
                                   ("DOCUMENT_TYPE", "IN", '["LIVRET_FONCIER"]', 10),
                                   ("BEDROOMS_MIN", "GTE", "2", 20)):
        session.execute(text("""INSERT INTO turab.request_criteria
                                  (request_id, criterion_code, importance, operator, value, sort_order)
                                VALUES (:r, :c, 'REQUIRED', CAST(:o AS turab.criterion_operator),
                                        CAST(:v AS jsonb), :s)"""),
                        {"r": rid, "c": code, "o": op, "v": value, "s": order})
    return rid


def test_the_request_snapshot_is_complete_exact_and_ordered(session, request_id):
    snap = snapshots.request_snapshot(session, request_id)
    assert snap["format"] == "turab.request-snapshot/1"
    assert (snap["transaction_intent"], snap["desired_property_type"], snap["budget_max_dzd"]) \
        == ("BUY", "APARTMENT", 25000000)
    assert [c["criterion_code"] for c in snap["criteria"]] == \
        ["DOCUMENT_TYPE", "BEDROOMS_MIN", "ROOMS_MIN"], "sort_order, then code"
    rooms = next(c for c in snap["criteria"] if c["criterion_code"] == "ROOMS_MIN")
    assert rooms["value"] == Decimal("3.50") and isinstance(rooms["value"], Decimal)
    assert _floats(snap) == []
    assert "evaluated_at" not in snap and "fresh" not in str(sorted(snap)).lower()


def test_the_same_state_gives_the_same_bytes_and_a_changed_criterion_does_not(session,
                                                                            request_id):
    """C04's basis: a criterion change is a different input."""
    first = canonical.canonical_bytes(snapshots.request_snapshot(session, request_id))
    assert canonical.canonical_bytes(snapshots.request_snapshot(session, request_id)) == first
    session.execute(text("""UPDATE turab.request_criteria SET value = '4'
                             WHERE request_id = :r AND criterion_code = 'ROOMS_MIN'"""),
                    {"r": request_id})
    changed = snapshots.request_snapshot(session, request_id)
    assert canonical.canonical_bytes(changed) != first


@pytest.fixture
def client(engine):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink()))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


def _h(account):
    return {"Authorization": f"Bearer {account}", "Idempotency-Key": str(uuid.uuid4())}


def test_the_property_snapshot_records_areas_attributes_evidence_and_identity(client, ids,
                                                                             engine):
    from sqlalchemy.orm import Session

    loc = None
    with engine.begin() as conn:
        loc = conn.execute(text("""INSERT INTO turab.locations (code, canonical_ar, location_type)
                                   VALUES (:c, 'موقع', 'AREA') RETURNING location_id"""),
                           {"c": f"TEST-S4-{uuid.uuid4().hex[:12]}"}).scalar_one()
    body = {"property_type": "APARTMENT", "supply_mode": "PUBLIC", "management_mode": "ASSISTED",
            "claim_status": "UNCLAIMED", "canonical_location_id": str(loc),
            "built_area_m2": 120.5}
    a = client.post("/properties", headers=_h(ids.ACC_OPERATOR), json=body).json()["property_id"]
    b = client.post("/properties", headers=_h(ids.ACC_OPERATOR), json=body).json()["property_id"]
    claim = client.post("/claims", headers=_h(ids.ACC_OPERATOR), json={
        "subject": {"type": "PROPERTY", "id": a}, "attribute_code": "ROOMS",
        "claimed_value": 4, "asserted_by_party_id": str(ids.BRAHIM)}).json()["claim_id"]
    assert client.post(f"/claims/{claim}/verification-events", headers=_h(ids.ACC_REVIEWER),
                       json={"level": "DOCUMENT_SEEN", "outcome": "CONFIRMED"}).status_code == 201
    assert client.post("/resolutions", headers=_h(ids.ACC_OPERATOR), json={
        "subject": {"type": "PROPERTY", "id": a}, "attribute_code": "ROOMS",
        "resolved_value": 4, "source_claim_id": claim}).status_code == 201
    cid = client.post("/identity/candidates/generate", headers=_h(ids.ACC_OPERATOR),
                      json={"property_id": a}).json()[0]["identity_candidate_id"]
    assert client.post(f"/identity/candidates/{cid}/review", headers=_h(ids.ACC_REVIEWER),
                       json={"decision": "CONFIRMED_SAME", "canonical_property_id": a}
                       ).status_code == 200

    with Session(bind=engine, future=True) as s:
        canon = snapshots.property_snapshot(s, uuid.UUID(a))
        alias = snapshots.property_snapshot(s, uuid.UUID(b))
    assert canon["built_area_m2"] == Decimal("120.50") and _floats(canon) == []
    assert canon["attributes"] == [{"code": "ROOMS", "value": Decimal("4"),
                                    "resolved_claim_id": uuid.UUID(claim),
                                    "evidence_level": "DOCUMENT_SEEN"}]
    assert canon["identity"] == {"is_alias": False, "canonical_property_id": uuid.UUID(a)}
    assert alias["identity"] == {"is_alias": True, "canonical_property_id": uuid.UUID(a)}
    canonical.canonical_bytes(canon)


def test_the_commercial_snapshot_carries_the_internal_expectation(session, ids):
    snap = snapshots.commercial_context_snapshot(session, ids.OFFER_OWNER_SALE)
    assert snap["kind"] == "OFFER" and snap["offer_id"] == ids.OFFER_OWNER_SALE
    assert "seller_expectation_dzd" in snap and "price_negotiable" in snap
    assert "commercial_terms_last_confirmed_at" in snap
    canonical.canonical_bytes(snap)


@pytest.mark.parametrize("builder", [snapshots.request_snapshot, snapshots.property_snapshot,
                                     snapshots.commercial_context_snapshot])
def test_a_missing_subject_is_refused(session, builder):
    with pytest.raises(snapshots.SnapshotSubjectMissing):
        builder(session, uuid.uuid4())


# ======================================================================================
# The hash against the real uniqueness constraint (the condition on G4-13)
# ======================================================================================

@pytest.fixture
def two_offers_identical_terms(session, ids):
    prop = session.execute(text("""
        INSERT INTO turab.properties (property_type, supply_mode, management_mode, claim_status)
        VALUES ('APARTMENT', 'PUBLIC', 'ASSISTED', 'UNCLAIMED') RETURNING property_id""")
    ).scalar_one()
    offers = [session.execute(text("""
        INSERT INTO turab.property_offers (property_id, party_id, transaction_type, status,
                                           asking_price_dzd, price_negotiable)
        VALUES (:p, :party, 'SALE', 'ACTIVE', 24000000, 'NO') RETURNING offer_id"""),
        {"p": prop, "party": ids.BRAHIM}).scalar_one() for _ in range(2)]
    req = session.execute(text("""
        INSERT INTO turab.requests (party_id, transaction_intent, management_mode, claim_status)
        VALUES (:p, 'BUY', 'ASSISTED', 'UNCLAIMED') RETURNING request_id"""),
        {"p": ids.BRAHIM}).scalar_one()
    return req, prop, offers


def _hash_for(session, req, prop, offer):
    active = policy.load_active_policy(session)
    commercial = snapshots.commercial_context_snapshot(session, offer)
    return active, canonical.input_hash(
        matching_policy_id=active.matching_policy_id, matching_policy_version=active.version,
        rule_registry_digest=registry.REGISTRY.digest(), evaluated_offer_id=offer,
        request_snapshot=snapshots.request_snapshot(session, req),
        property_snapshot=snapshots.property_snapshot(session, prop),
        commercial_context_snapshot=commercial, permission_snapshot={}, freshness_snapshot={})


def _insert_match(session, req, prop, offer, active, digest):
    session.execute(text("""
        INSERT INTO turab.match_candidates
          (request_id, property_id, evaluated_offer_id, matching_policy_id,
           matching_policy_version, request_version, property_version, offer_version,
           eligibility, hard_gate_status, information_gate_status, request_freshness,
           property_freshness, freshness_gate_status, permission_gate_status,
           request_snapshot, property_snapshot, input_hash)
        VALUES (:r, :p, :o, :pol, :v, 1, 1, 1, 'REJECTED', 'FAIL', 'PASS', 'FRESH', 'FRESH',
                'PASS', 'PASS', '{}', '{}', :h)"""),
        {"r": req, "p": prop, "o": offer, "pol": active.matching_policy_id,
         "v": active.version, "h": digest})


def test_two_offers_on_identical_terms_give_two_independent_match_rows(
        session, two_offers_identical_terms):
    """Fixture rows, hashed by the real functions from the real snapshots.
    Both inserts must succeed under UNIQUE(request, property, policy, hash)."""
    req, prop, (o1, o2) = two_offers_identical_terms
    active, h1 = _hash_for(session, req, prop, o1)
    _, h2 = _hash_for(session, req, prop, o2)
    assert h1 != h2
    _insert_match(session, req, prop, o1, active, h1)
    _insert_match(session, req, prop, o2, active, h2)
    assert session.execute(text("SELECT count(*) FROM turab.match_candidates "
                                "WHERE request_id = :r"), {"r": req}).scalar_one() == 2


def test_the_same_offer_on_the_same_state_hashes_identically_and_cannot_be_stored_twice(
        session, two_offers_identical_terms):
    req, prop, (o1, _) = two_offers_identical_terms
    active, first = _hash_for(session, req, prop, o1)
    _, again = _hash_for(session, req, prop, o1)
    assert first == again
    _insert_match(session, req, prop, o1, active, first)
    savepoint = session.begin_nested()
    with pytest.raises(IntegrityError, match="duplicate key"):
        _insert_match(session, req, prop, o1, active, again)
    savepoint.rollback()


# ======================================================================================
# Architecture: step 2 writes nothing, and reads no relation
# ======================================================================================

def _sql_in(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
            and any(k in n.value.upper() for k in ("SELECT", "INSERT", "UPDATE ", "DELETE"))]


def test_the_matching_package_reads_and_never_writes():
    found = {p.name: _sql_in(p) for p in MATCHING.glob("*.py")}
    assert found["snapshots.py"], "the detector must see the snapshot SQL"
    writes = [(n, s.strip()[:50]) for n, sqls in found.items() for s in sqls
              if any(w in s.upper() for w in ("INSERT INTO", "UPDATE TURAB", "DELETE FROM"))]
    assert writes == []


def test_the_matching_package_never_reads_party_property_relations():
    offenders = [p.name for p in MATCHING.glob("*.py")
                 if "party_property_relations" in "".join(_sql_in(p))]
    assert offenders == []


# ======================================================================================
# Review of 4538a2d, over HTTP: a user's key named like an engine field
# ======================================================================================

def test_a_criterion_value_naming_evaluated_at_is_accepted_and_hashed(client, ids, engine):
    """`request_criteria.value` is jsonb, and `RequestCriterionInput.value` is
    FiniteJson: nothing forbids a customer's object from carrying a key named
    `evaluated_at` or `input_hash`. The criterion is added through the Slice 2
    route, read back by the snapshot builder, and hashed. Then the SAME
    criterion's value is changed (the route's change half, selected by
    `request_criterion_id`), and the hash changes.

    A changed criterion also bumps the request's version
    (`touch_request_from_criterion`), which would change the hash by
    itself. So the second comparison holds the version at its first value:
    the hash still differs, and that difference comes from the value alone."""
    from sqlalchemy.orm import Session

    with engine.begin() as conn:
        rid = conn.execute(text("""
            INSERT INTO turab.requests (party_id, transaction_intent, management_mode,
                                        claim_status)
            VALUES (:p, 'BUY', 'ASSISTED', 'UNCLAIMED') RETURNING request_id"""),
            {"p": ids.BRAHIM}).scalar_one()

    def put(day, criterion_id=None):
        body = {"criterion_code": "CUSTOM_ATTRIBUTE", "importance": "PREFERRED",
                "operator": "EQ", "sort_order": 1,
                "value": {"evaluated_at": day, "input_hash": "the customer's own text"}}
        if criterion_id:
            body["request_criterion_id"] = criterion_id
        r = client.post(f"/requests/{rid}/criteria", headers=_h(ids.ACC_OPERATOR), json=body)
        assert r.status_code == 201, r.text
        return r.json()["request_criterion_id"]

    def hashed():
        with Session(bind=engine, future=True) as s:
            snap = snapshots.request_snapshot(s, rid)
        return snap, canonical.input_hash(**_inputs(request_snapshot=snap))

    criterion = put("2012-03-04")
    first_snap, first = hashed()
    value = first_snap["criteria"][0]["value"]
    assert value == {"evaluated_at": "2012-03-04", "input_hash": "the customer's own text"}
    assert hashed()[1] == first

    assert put("2012-03-05", criterion) == criterion
    changed_snap, changed = hashed()
    assert len(changed_snap["criteria"]) == 1, "the same criterion, changed"
    assert changed_snap["criteria"][0]["value"]["evaluated_at"] == "2012-03-05"
    assert changed != first
    assert changed_snap["version"] != first_snap["version"], "the trigger bumped it"
    same_version = {**changed_snap, "version": first_snap["version"]}
    assert canonical.input_hash(**_inputs(request_snapshot=same_version)) != first
