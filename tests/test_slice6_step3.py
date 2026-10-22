"""Slice 6 step 3: the diagnostic's pure functions, their registry entries, and
replay.

Ref: `docs/gate/SLICE_6_PLAN.md` revision 8: G6-2 (a), G6-3, G6-5, G6-6, G6-7,
G6-11; §3.3-§3.5; F6-1, F6-10, F6-11, F6-13; `matching/diagnostic_rules.py`,
`matching/diagnostic.py`, `services/diagnostic_replay.py`.

**Step 3 writes nothing.** The run still stores format 1 and empty
suggestions (asserted below). These tests build the format-2 parts with
`compute` from REAL stored matches (the delivered run), and replay those
documents; no format-2 row exists before step 4.

Two layers:
- the decision rules, on synthetic records shaped as `candidate_record`
  builds them;
- the same rules on records built from real runs: the inputs of mandatory
  tests 1-3, the location cases L1-L4 of step 0, the seller expectation,
  and the replay test of G6-11.
"""
from __future__ import annotations

import copy
import json
import uuid
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.test_slice4_step7 import _criterion, _exec, _offer, _one, _request, _run
from tests.test_slice5_step2 import _prop
from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.matching import diagnostic, registry, registry_history
from turab.matching.registry import REGISTRY
from turab.services import diagnostic_replay

VALUE = REGISTRY.resolve("diagnostic.value", "1").evaluate
ACTIONS = REGISTRY.resolve("diagnostic.actions", "1").evaluate
RELAXATION = REGISTRY.resolve("diagnostic.relaxation", "1").evaluate


@pytest.fixture
def client(engine):
    from turab.app import create_app

    with TestClient(create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink())),
                    raise_server_exceptions=True) as c:
        yield c


# ======================================================================================
# Synthetic records
# ======================================================================================

def _c(code, compatibility, *, importance="REQUIRED", blocking=None, basis="B", ordinal=1,
       reason=None, request_value=None, property_value=None):
    if blocking is None:
        blocking = importance == "REQUIRED" and compatibility != "PASS"
    return {"criterion": code, "ordinal": Decimal(ordinal), "request_criterion_id": None,
            "importance": importance, "compatibility": compatibility, "blocking": blocking,
            "reason_code": reason, "basis": basis, "request_value": request_value,
            "property_value": property_value}


def _record(eligibility, criteria, *, hard=None, fresh="PASS", perm="PASS", reasons=(),
            prop=None, offer=None):
    if hard is None:
        required = [c["compatibility"] for c in criteria if c["importance"] == "REQUIRED"]
        hard = "FAIL" if "FAIL" in required else "UNKNOWN" if "UNKNOWN" in required else "PASS"
    return {"match_id": str(uuid.uuid4()), "property_id": prop or str(uuid.uuid4()),
            "offer_id": offer or str(uuid.uuid4()), "eligibility": eligibility,
            "hard_gate_status": hard, "freshness_gate_status": fresh,
            "permission_gate_status": perm, "criteria": criteria, "reasons": list(reasons),
            "location_ancestry": [], "precedence": "eligibility.precedence@1"}


REQ = str(uuid.uuid4())
DOC_UNKNOWN = _c("DOCUMENT_TYPE", "UNKNOWN", basis="ATTRIBUTE_NOT_RECORDED",
                 reason="DOCUMENT_NOT_KNOWN")
ROOMS_UNKNOWN = _c("ROOMS_MIN", "UNKNOWN", basis="ATTRIBUTE_NOT_RECORDED")
PASSING = _c("PROPERTY_TYPE", "PASS")
STALE_OFFER = {"gate": "FRESHNESS", "subject": "OFFER", "reason_code": "OFFER_STALE",
               "basis": "STALE"}
NO_BINDING = {"gate": "PERMISSION", "reason_code": "PERMISSION_MISSING",
              "basis": "NO_CURRENT_BINDING"}


# --- diagnostic.value@1 (G6-2 (a)) ---------------------------------------------------

def test_one_actionable_unknown_with_fresh_and_permitted_gates_is_high_value():
    assert VALUE(_record("NEED_MORE_INFORMATION", [DOC_UNKNOWN, PASSING])) == [
        {"criterion": "DOCUMENT_TYPE", "ordinal": Decimal(1)}]


@pytest.mark.parametrize("label, record", [
    ("two actionable unknowns",
     _record("NEED_MORE_INFORMATION", [DOC_UNKNOWN, ROOMS_UNKNOWN])),
    ("freshness not PASS",
     _record("NEED_MORE_INFORMATION", [DOC_UNKNOWN], fresh="FAIL", reasons=[STALE_OFFER])),
    ("permission not PASS",
     _record("NEED_MORE_INFORMATION", [DOC_UNKNOWN], perm="UNKNOWN", reasons=[NO_BINDING])),
    ("REJECTED", _record("REJECTED", [DOC_UNKNOWN, _c("LOCATION", "FAIL")])),
    ("ELIGIBLE", _record("ELIGIBLE", [PASSING])),
    ("a non-blocking unknown is not actionable",
     _record("ELIGIBLE", [_c("DOCUMENT_TYPE", "UNKNOWN", importance="PREFERRED")])),
])
def test_nothing_else_is_high_value(label, record):
    assert VALUE(record) == [], label


# --- diagnostic.actions@1 (G6-3) ---------------------------------------------------------

def _actions(records):
    return ACTIONS(REQ, records, [VALUE(r) for r in records])


def test_mandatory_2_a_candidate_failing_three_hard_criteria_gets_no_action():
    """§3.3: REJECTED, an unrelated document UNKNOWN, and stale terms: no entry,
    of any priority."""
    rejected = _record("REJECTED", [_c("LOCATION", "FAIL"), _c("BUDGET_MAX", "FAIL"),
                                    _c("PROPERTY_TYPE", "FAIL"), DOC_UNKNOWN],
                       fresh="FAIL", reasons=[STALE_OFFER])
    assert _actions([rejected]) == []


def test_eligible_gets_no_action():
    assert _actions([_record("ELIGIBLE", [PASSING])]) == []


def test_only_the_high_value_unknown_is_high():
    """G6-2 (a): the candidate one fact away is HIGH; the one two facts away
    is NORMAL, for the same kind of work."""
    one = _record("NEED_MORE_INFORMATION", [DOC_UNKNOWN, PASSING])
    two = _record("NEED_MORE_INFORMATION", [DOC_UNKNOWN, ROOMS_UNKNOWN])
    by_property = {a["subject"]["id"]: a["priority"] for a in _actions([one, two])
                   if a["type"] == "VERIFY_DOCUMENT"}
    assert by_property == {one["property_id"]: "HIGH", two["property_id"]: "NORMAL"}


def test_every_reason_of_a_candidate_is_an_entry_not_only_the_first():
    record = _record("NEED_MORE_INFORMATION", [DOC_UNKNOWN, ROOMS_UNKNOWN], fresh="FAIL",
                     perm="UNKNOWN", reasons=[STALE_OFFER, NO_BINDING])
    assert sorted(a["type"] for a in _actions([record])) == [
        "CONFIRM_PERMISSION", "CONFIRM_PRICE", "OTHER", "VERIFY_DOCUMENT"]


def test_needs_confirmation_gets_its_reconfirmation_and_permission_work():
    record = _record("NEEDS_CONFIRMATION", [PASSING], fresh="FAIL", perm="UNKNOWN",
                     reasons=[STALE_OFFER, NO_BINDING])
    actions = _actions([record])
    assert [(a["type"], a["class"], a["priority"]) for a in actions] == [
        ("CONFIRM_PRICE", "RECONFIRMATION", "NORMAL"),
        ("CONFIRM_PERMISSION", "PERMISSION", "NORMAL")]
    assert {a["subject"]["entity"] for a in actions} == {"PROPERTY_OFFER"}


def test_f6_13_two_offers_and_two_gates_are_four_subjects():
    """One property, offers A and B, each with its price above the maximum
    and negotiable (an INFORMATION unknown on the OFFER); B's terms are also
    stale. Four subjects: two offers, and for B two gates of the same type."""
    prop = str(uuid.uuid4())
    price = _c("BUDGET_MAX", "UNKNOWN", basis="PRICE_ABOVE_MAX_NEGOTIATION_UNCONFIRMED",
               reason="PRICE_NEGOTIATION_UNCONFIRMED")
    a = _record("NEED_MORE_INFORMATION", [price], prop=prop)
    b = _record("NEED_MORE_INFORMATION", [price], prop=prop, fresh="FAIL",
                reasons=[STALE_OFFER])
    actions = _actions([a, b])
    assert sorted((x["subject"]["id"], x["subject"]["gate"]) for x in actions) == sorted([
        (a["offer_id"], "INFORMATION"), (b["offer_id"], "INFORMATION"),
        (b["offer_id"], "FRESHNESS")])
    assert {x["type"] for x in actions} == {"CONFIRM_PRICE"}


def test_a_subject_shared_by_candidates_is_one_entry_with_their_count():
    """A criterion no rule reads is the REQUEST's work, whichever property."""
    no_rule = _c("CUSTOM", "UNKNOWN", importance="PREFERRED", blocking=True,
                 basis="NO_DETERMINISTIC_RULE")
    records = [_record("NEED_MORE_INFORMATION", [no_rule]) for _ in range(3)]
    [entry] = _actions(records)
    assert (entry["subject"]["entity"], entry["subject"]["id"]) == ("REQUEST", REQ)
    assert entry["candidate_count"] == 3 and len(entry["candidates"]) == 3


def test_the_order_is_priority_class_count_then_ids():
    """G6-3's order, fixed: HIGH first; then information, reconfirmation
    (request, property, offer), permission; then count, descending; then the
    entity id."""
    high = _record("NEED_MORE_INFORMATION", [DOC_UNKNOWN])
    stale = [{"gate": "FRESHNESS", "subject": s, "reason_code": None,
              "basis": "NEVER_CONFIRMED"} for s in ("OFFER", "PROPERTY", "REQUEST")]
    confirm = _record("NEEDS_CONFIRMATION", [PASSING], fresh="UNKNOWN", perm="UNKNOWN",
                      reasons=[*stale, NO_BINDING])
    two = [_record("NEED_MORE_INFORMATION", [DOC_UNKNOWN, ROOMS_UNKNOWN])
           for _ in range(2)]
    actions = _actions([confirm, *two, high])
    order = [(a["priority"], a["type"], a["candidate_count"]) for a in actions]
    assert order[0] == ("HIGH", "VERIFY_DOCUMENT", 1)
    assert [t for _, t, _ in order[1:]][-4:] == [
        "RECONFIRM_REQUEST", "RECONFIRM_PROPERTY", "CONFIRM_PRICE", "CONFIRM_PERMISSION"]
    information = [a for a in actions[1:] if a["class"] == "INFORMATION"]
    ids = [a["subject"]["id"] for a in information if a["type"] == "VERIFY_DOCUMENT"]
    assert ids == sorted(ids)


def test_an_entry_carries_no_value():
    """§3.4: ids, codes, the basis and counts only."""
    price = _c("BUDGET_MAX", "UNKNOWN", basis="PRICE_ABOVE_MAX_NEGOTIATION_UNCONFIRMED",
               request_value={"operator": "LTE", "value": Decimal(24_000_000)},
               property_value={"asking_price_dzd": Decimal(26_000_000),
                               "price_negotiable": "YES"})
    rendered = json.dumps(_actions([_record("NEED_MORE_INFORMATION", [price])]), default=str)
    assert "26000000" not in rendered and "24000000" not in rendered
    assert "asking_price" not in rendered and "property_value" not in rendered


# --- diagnostic.relaxation@1 on synthetic records (G6-5) -------------------------------

def _near(code, failing, *, others=(PASSING,), basis="B"):
    return _record("REJECTED", [failing, *others])


def _relax(records, chains=None, high=()):
    reach = [diagnostic.would_reach(r) if diagnostic._near_match(r) else None
             for r in records]
    return RELAXATION(records, reach, chains or {}, list(high))


def _budget(ask, maximum):
    return _c("BUDGET_MAX", "FAIL", basis="PRICE_ABOVE_MAX_NOT_NEGOTIABLE",
              reason="BUDGET_EXCEEDED",
              request_value={"operator": "LTE", "value": Decimal(maximum)},
              property_value={"asking_price_dzd": Decimal(ask), "price_negotiable": "NO"})


def test_budget_scenarios_are_cumulative_and_smallest_first():
    a = _near("BUDGET_MAX", _budget(25_500_000, 24_000_000))
    b = _near("BUDGET_MAX", _budget(27_000_000, 24_000_000))
    out = _relax([b, a])
    assert [(s["magnitude"]["budget_delta_dzd"], s["near_match_count"]) for s in out] == [
        (Decimal(1_500_000), 1), (Decimal(3_000_000), 2)]
    assert {s["magnitude"]["stated_at"] for s in out} == {"ASKING_PRICE"}
    assert [n["property_id"] for n in out[0]["near_matches"]] == [a["property_id"]]


def test_two_required_failures_are_not_a_near_match():
    """G6-5 (ii) (a): D2's definition only."""
    record = _record("REJECTED", [_budget(25_500_000, 24_000_000), _c("LOCATION", "FAIL")])
    assert _relax([record]) == []


def test_area_and_count_are_lowered_by_a_negative_delta():
    area = _c("LAND_AREA_MIN", "FAIL", basis="AREA_MINIMUM",
              request_value={"operator": "GTE", "value": Decimal(500)},
              property_value=Decimal(400))
    rooms = _c("ROOMS_MIN", "FAIL", basis="COUNT_MINIMUM",
               request_value={"operator": "GTE", "value": Decimal(4)},
               property_value=Decimal(3))
    out = _relax([_near("LAND_AREA_MIN", area), _near("ROOMS_MIN", rooms)])
    assert [(s["criterion"], s["scenario"], s["magnitude"]) for s in out] == [
        ("LAND_AREA_MIN", "LOWER_MINIMUM", {"area_delta_m2": Decimal(-100)}),
        ("ROOMS_MIN", "LOWER_MINIMUM", {"count_delta": Decimal(-1)})]


def test_a_count_that_cannot_apply_is_not_proposed():
    """count_min@2 FAILs an attribute that cannot apply to the type: no
    lowering passes it."""
    rooms = _c("ROOMS_MIN", "FAIL", basis="ATTRIBUTE_NOT_APPLICABLE",
               request_value={"operator": "GTE", "value": Decimal(4)})
    [s] = _relax([_near("ROOMS_MIN", rooms)])
    assert (s["scenario"], s["basis"], s["near_match_count"]) == (
        "NOT_PROPOSED", "ATTRIBUTE_NOT_APPLICABLE", 1)


def test_a_type_and_a_document_are_named_and_the_document_only_if_chosen():
    ptype = _c("PROPERTY_TYPE", "FAIL", property_value="VILLA")
    document = _c("DOCUMENT_TYPE", "FAIL", basis="ATTRIBUTE_OPTION",
                  property_value="CUSTOMARY_DEED")
    out = _relax([_near("PROPERTY_TYPE", ptype, others=()),
                  _near("DOCUMENT_TYPE", document)])
    by_code = {s["criterion"]: s for s in out}
    assert (by_code["PROPERTY_TYPE"]["scenario"], by_code["PROPERTY_TYPE"]["named"]) == (
        "ACCEPT_PROPERTY_TYPE", "VILLA")
    assert "only_if_user_chooses" not in by_code["PROPERTY_TYPE"]
    assert (by_code["DOCUMENT_TYPE"]["scenario"], by_code["DOCUMENT_TYPE"]["named"],
            by_code["DOCUMENT_TYPE"]["only_if_user_chooses"]) == (
        "ACCEPT_DOCUMENT", "CUSTOMARY_DEED", True)


def test_would_reach_is_the_precedence_without_the_failure():
    """G6-5 (v): ELIGIBLE, NEEDS_CONFIRMATION with its reasons, or
    NEED_MORE_INFORMATION when a blocking soft unknown stays."""
    plain = _near("BUDGET_MAX", _budget(25_500_000, 24_000_000))
    stale = _record("REJECTED", [_budget(25_500_000, 24_000_000), PASSING], fresh="FAIL",
                    reasons=[STALE_OFFER])
    soft = _record("REJECTED", [_budget(25_500_000, 24_000_000),
                                _c("ROOMS_MIN", "UNKNOWN", importance="PREFERRED",
                                   blocking=True)])
    reach = {r["property_id"]: diagnostic.would_reach(r) for r in (plain, stale, soft)}
    assert reach[plain["property_id"]] == {"eligibility": "ELIGIBLE", "reasons": []}
    assert reach[stale["property_id"]] == {"eligibility": "NEEDS_CONFIRMATION",
                                           "reasons": [STALE_OFFER]}
    assert reach[soft["property_id"]]["eligibility"] == "NEED_MORE_INFORMATION"


def test_every_scenario_is_subordinate_to_the_high_actions():
    out = _relax([_near("BUDGET_MAX", _budget(25_500_000, 24_000_000))],
                 high=["VERIFY_DOCUMENT|PROPERTY|x|INFORMATION|DOCUMENT_TYPE#1|B"])
    assert out[0]["subordinate_to"] == [
        "VERIFY_DOCUMENT|PROPERTY|x|INFORMATION|DOCUMENT_TYPE#1|B"]


# ======================================================================================
# The registry (G6-11)
# ======================================================================================

def test_the_three_functions_are_registered_pinned_and_recorded():
    keys = {r.key for r in REGISTRY.rules()}
    assert {"diagnostic.value@1", "diagnostic.actions@1", "diagnostic.relaxation@1"} <= keys
    assert REGISTRY.verify_pins(registry.load_pins()) == []
    [entry] = [e for e in registry_history.HISTORY if e["digest"] == REGISTRY.digest()]
    assert len(entry["pairs"]) == 23
    first = {p for p in registry_history.HISTORY[0]["pairs"]}
    assert first < set(entry["pairs"]), "the twenty earlier pairs are unchanged"


# ======================================================================================
# Real runs
# ======================================================================================

LOC = {}


def _loc(engine, code):
    if code not in LOC:
        LOC[code] = str(_one(engine, "SELECT location_id FROM turab.locations WHERE code = :c",
                             c=code))
    return LOC[code]


def _at(engine, prop, code):
    _exec(engine, "UPDATE turab.properties SET canonical_location_id = :l "
                  "WHERE property_id = :p", l=_loc(engine, code), p=prop)
    return prop


def _ran(client, ids, req, props):
    r = _run(client, ids, req, props)
    assert r.status_code == 201, r.text
    return r.json()


def _evaluated(body):
    run_at = body["diagnostic"]["run_at"]
    return [{"property_id": m["property_id"], "offer_id": m["evaluated_offer_id"],
             "match_id": m["match_id"], "input_hash": m["input_hash"],
             "stored": "NEW" if m["evaluated_at"] == run_at else "EXISTING"}
            for m in body["matches"]]


def _computed(engine, body):
    records = [diagnostic.candidate_record(m) for m in body["matches"]]
    with engine.connect() as conn:
        chains = diagnostic.read_location_chains(conn,
                                                 diagnostic.requested_location_ids(records))
    return diagnostic.compute(body["diagnostic"]["request_id"], records,
                              location_chains=chains, evaluated=_evaluated(body),
                              excluded=body["diagnostic"]["blocker_summary"]["excluded"])


def _row(body, computed):
    """The format-2 diagnostic row step 4 would write, as a document."""
    return {"request_id": body["diagnostic"]["request_id"],
            "run_at": body["diagnostic"]["run_at"], **computed}


def test_the_run_still_writes_format_1_and_no_suggestion(client, engine, ids):
    """Step 3's boundary: nothing in the run changed."""
    req = _request(engine, ids)
    prop = _prop(engine, document=None)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    _offer(engine, ids, prop)
    body = _ran(client, ids, req, [prop])
    d = body["diagnostic"]
    assert d["blocker_summary"]["format"] == "turab.blocker-summary/1"
    assert (d["suggested_actions"], d["relaxation_scenarios"]) == ([], [])


def test_mandatory_1_the_document_unknown_ranks_above_the_location_scenario(
        client, engine, ids):
    """R-001 with P08 (document UNKNOWN, all else PASS) and P03 (LOCATION FAIL
    only). The first suggested action is P08's VERIFY_DOCUMENT, HIGH; the
    location scenario of P03 is subordinate to it (G6-5 (i) (a); M-12, I01)."""
    req = _request(engine, ids)
    _criterion(engine, req, "LOCATION", "IN", [_loc(engine, "ADR-NEW-TIL")], "REQUIRED")
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED", sort_order=1)
    p08 = _at(engine, _prop(engine, document=None), "ADR-NEW-TIL")
    p03 = _at(engine, _prop(engine), "ADR-AIRPORT")
    for p in (p08, p03):
        _offer(engine, ids, p)
    out = _computed(engine, _ran(client, ids, req, [p08, p03]))
    first = out["suggested_actions"][0]
    assert (first["type"], first["priority"], first["subject"]["id"]) == (
        "VERIFY_DOCUMENT", "HIGH", str(p08))
    [location] = [s for s in out["relaxation_scenarios"] if s["criterion"] == "LOCATION"]
    assert location["subordinate_to"] == [first["key"]]
    assert [n["property_id"] for n in location["near_matches"]] == [str(p03)]


def test_mandatory_2_over_a_real_run(client, engine, ids):
    """A property failing LOCATION, BUDGET_MAX and PROPERTY_TYPE with an
    UNKNOWN document: no action and no scenario for it (not a near match)."""
    req = _request(engine, ids, budget_max=24_000_000, desired_type="LAND")
    _criterion(engine, req, "LOCATION", "IN", [_loc(engine, "ADR-NEW-TIL")], "REQUIRED")
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED", sort_order=1)
    bad = _at(engine, _prop(engine, ptype="APARTMENT", document=None), "ADR-AIRPORT")
    _offer(engine, ids, bad, price=30_000_000, negotiable="NO")
    body = _ran(client, ids, req, [bad])
    assert body["matches"][0]["eligibility"] == "REJECTED"
    out = _computed(engine, body)
    assert (out["suggested_actions"], out["relaxation_scenarios"]) == ([], [])
    assert out["blocker_summary"]["unknowns"]["DOCUMENT_TYPE#1"] == {
        "blocking": 1, "non_blocking": 0, "actionable": 0, "high_value": 0}


def test_mandatory_3_the_budget_magnitude_is_1_500_000_dzd(client, engine, ids):
    """F6-1: the spec's +150M centimes is +1,500,000 DZD (prices are stored in
    DZD). A property at max + 1,500,000, not negotiable."""
    req = _request(engine, ids, budget_max=24_000_000)
    prop = _prop(engine)
    _offer(engine, ids, prop, price=25_500_000, negotiable="NO")
    out = _computed(engine, _ran(client, ids, req, [prop]))
    [s] = out["relaxation_scenarios"]
    assert (s["criterion"], s["scenario"], s["magnitude"]) == (
        "BUDGET_MAX", "RAISE_MAXIMUM",
        {"budget_delta_dzd": Decimal(1_500_000), "stated_at": "ASKING_PRICE"})
    assert s["near_matches"][0]["would_reach"]["eligibility"] == "ELIGIBLE"


def test_the_seller_expectation_is_never_stated_nor_used(client, engine, ids):
    """§3.4, R9.3, D02. An expectation between the maximum and the asking
    price: the magnitude is ask − max (2,000,000), never exp − max
    (1,000,000), and nothing of the output changes with the expectation."""
    outputs = []
    for expectation in (25_000_000, 25_900_000):
        req = _request(engine, ids, budget_max=24_000_000)
        prop = _prop(engine)
        _offer(engine, ids, prop, price=26_000_000, negotiable="NO", expectation=expectation)
        out = _computed(engine, _ran(client, ids, req, [prop]))
        rendered = json.dumps(out, default=str)
        for leaked in (str(expectation), str(expectation - 24_000_000)):
            assert leaked not in rendered, leaked
        [s] = out["relaxation_scenarios"]
        assert s["magnitude"]["budget_delta_dzd"] == Decimal(2_000_000)
        outputs.append([{k: v for k, v in s.items() if k != "near_matches"}])
    assert outputs[0] == outputs[1]


@pytest.mark.parametrize("label, requested, at, widen_to, level, chosen, levels", [
    ("L1 two different ancestors", ["ADR-NEW-TIL", "C-TIMEKTEN"], "ADR-AIRPORT",
     "C-ADRAR", "COMMUNE", "ADR-NEW-TIL", 1),
    ("L2 a full tie on one ancestor", ["ADR-NEW-TIL", "ADR-CENTER"], "ADR-AIRPORT",
     "C-ADRAR", "COMMUNE", "ADR-NEW-TIL", 1),
    ("L3 one ancestor by different widenings", ["ADR-KSAR-TILILANE", "ADR-NEW-TIL"],
     "ADR-AIRPORT", "C-ADRAR", "COMMUNE", "ADR-NEW-TIL", 1),
    ("L4 two ancestors at two depths", ["ADR-KSAR-TILILANE", "ADR-NEW-TIL"],
     "ADR-KSAR-MERAGUEN", "ADR-KSOUR", "AREA", "ADR-KSAR-TILILANE", 1),
    ("EQ is IN of one", ["C-TIMEKTEN"], "ADR-AIRPORT", "W-ADRAR", "WILAYA", "C-TIMEKTEN", 1),
])
def test_g6_6_the_location_measured_in_step_0(client, engine, ids, label, requested, at,
                                               widen_to, level, chosen, levels):
    req = _request(engine, ids)
    operator, value = (("IN", [_loc(engine, c) for c in requested]) if len(requested) > 1
                       else ("EQ", _loc(engine, requested[0])))
    _criterion(engine, req, "LOCATION", operator, value, "REQUIRED")
    prop = _at(engine, _prop(engine), at)
    _offer(engine, ids, prop)
    out = _computed(engine, _ran(client, ids, req, [prop]))
    [s] = out["relaxation_scenarios"]
    [choice] = s["choices"]
    assert (s["widen_to"], s["level"], choice["from"], choice["levels_widened"]) == (
        _loc(engine, widen_to), level, _loc(engine, chosen), levels), label
    assert [e["location_id"] for e in choice["evaluated"]] == [
        _loc(engine, c) for c in requested], "every requested location is listed"
    assert set(out["blocker_summary"]["requested_location_chains"]) == {
        _loc(engine, c) for c in requested}


def test_widening_turns_every_near_match_under_the_location(client, engine, ids):
    """Two near matches choose different ancestors; the wider scenario turns
    both, the narrower only its own (G6-5 (v), cumulative)."""
    req = _request(engine, ids)
    _criterion(engine, req, "LOCATION", "IN", [_loc(engine, "ADR-KSAR-TILILANE")], "REQUIRED")
    near = _at(engine, _prop(engine), "ADR-KSAR-MERAGUEN")
    far = _at(engine, _prop(engine), "ADR-AIRPORT")
    for p in (near, far):
        _offer(engine, ids, p)
    out = _computed(engine, _ran(client, ids, req, [near, far]))
    turned = {s["widen_to"]: {n["property_id"] for n in s["near_matches"]}
              for s in out["relaxation_scenarios"]}
    assert turned == {_loc(engine, "ADR-KSOUR"): {str(near)},
                      _loc(engine, "C-ADRAR"): {str(near), str(far)}}
    assert [s["widen_to"] for s in out["relaxation_scenarios"]] == [
        _loc(engine, "ADR-KSOUR"), _loc(engine, "C-ADRAR")]


# --- replay (G6-11) ---------------------------------------------------------------------

def _footprint(engine):
    return {t: _one(engine, f"SELECT count(*) FROM turab.{t}")
            for t in ("match_candidates", "match_criterion_results", "match_diagnostic_runs",
                      "tasks", "locations", "audit_log")}


def test_g6_11_two_runs_one_reused_match_both_replay(client, engine, ids):
    """Run 2, after P2's offer price changed, REUSES P1's match (EXISTING, run
    1's id) and stores a NEW one for P2. Both documents pass (R) and (D).
    Then: an altered `stored` or hash fails (R), not (D); an altered
    suggestion fails (D); after a requested location is re-parented, the
    replay still gives the stored scenario."""
    req = _request(engine, ids, budget_max=24_000_000)
    _criterion(engine, req, "LOCATION", "IN", [_loc(engine, "ADR-NEW-TIL")], "REQUIRED")
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED", sort_order=1)
    p1 = _at(engine, _prop(engine, document=None), "ADR-NEW-TIL")
    p2 = _at(engine, _prop(engine), "ADR-AIRPORT")
    _offer(engine, ids, p1)
    o2 = _offer(engine, ids, p2)
    first = _ran(client, ids, req, [p1, p2])
    _exec(engine, "UPDATE turab.property_offers SET asking_price_dzd = 21000000 "
                  "WHERE offer_id = :o", o=o2)
    second = _ran(client, ids, req, [p1, p2])
    rows = [_row(b, _computed(engine, b)) for b in (first, second)]
    stored = {e["property_id"]: e for e in rows[1]["blocker_summary"]["evaluated"]}
    assert stored[str(p1)]["stored"] == "EXISTING"
    [p1_first] = [m for m in first["matches"] if m["property_id"] == str(p1)]
    assert stored[str(p1)]["match_id"] == p1_first["match_id"]
    assert stored[str(p2)]["stored"] == "NEW"
    before = _footprint(engine)
    with engine.connect() as conn:
        assert [diagnostic_replay.replay(conn, r) for r in rows] == [{"R": [], "D": []}] * 2

        bad = copy.deepcopy(rows[1])
        bad["blocker_summary"]["evaluated"][0]["stored"] = (
            "NEW" if bad["blocker_summary"]["evaluated"][0]["stored"] == "EXISTING"
            else "EXISTING")
        bad["blocker_summary"]["evaluated"][1]["input_hash"] = "0" * 64
        result = diagnostic_replay.replay(conn, bad)
        assert result["R"] and result["D"] == [], result

        assert rows[1]["suggested_actions"] and rows[1]["relaxation_scenarios"], \
            "both parts exist, so altering each is a test"
        for part, alter in (("suggested_actions", lambda d: d[0].update(priority="NORMAL")),
                            ("relaxation_scenarios", lambda d: d[0].update(near_matches=[]))):
            bad = copy.deepcopy(rows[1])
            alter(bad[part])
            result = diagnostic_replay.replay(conn, bad)
            assert result["R"] == [] and result["D"] == [
                f"{part} differs from what the stored inputs give"], result
    new_til, center = _loc(engine, "ADR-NEW-TIL"), _loc(engine, "ADR-CENTER")
    with engine.begin() as conn:
        parent = conn.execute(text("SELECT parent_id FROM turab.locations "
                                   "WHERE location_id = :l"), {"l": new_til}).scalar_one()
        try:
            conn.execute(text("UPDATE turab.locations SET parent_id = :p WHERE location_id = :l"),
                         {"p": center, "l": new_til})
            assert diagnostic_replay.replay(conn, rows[0]) == {"R": [], "D": []}
            again = diagnostic.read_location_chains(conn, [new_til])
            assert again != rows[0]["blocker_summary"]["requested_location_chains"], \
                "the chain did change; the replay used the stored one"
        finally:
            conn.execute(text("UPDATE turab.locations SET parent_id = :p WHERE location_id = :l"),
                         {"p": parent, "l": new_til})
    assert _footprint(engine) == before, "compute and replay write nothing"


def test_the_replay_never_reads_tasks(client, engine, ids):
    """G6-4 (iii): every statement the replay executes is captured; none
    names `tasks`. The world has an open task on the match, so a read of
    `tasks` would have something to find."""
    from sqlalchemy import event

    req = _request(engine, ids)
    _criterion(engine, req, "DOCUMENT_TYPE", "EQ", "LAND_BOOK", "REQUIRED")
    prop = _prop(engine, document=None)
    _offer(engine, ids, prop)
    body = _ran(client, ids, req, [prop])
    _exec(engine, "INSERT INTO turab.tasks (task_type, title, match_id) "
                  "VALUES ('VERIFY_DOCUMENT', 'probe', :m)", m=body["matches"][0]["match_id"])
    row = _row(body, _computed(engine, body))
    seen = []
    with engine.connect() as conn:
        event.listen(conn, "before_cursor_execute",
                     lambda *a: seen.append(a[2]))
        assert diagnostic_replay.replay(conn, row) == {"R": [], "D": []}
    assert seen and not [s for s in seen if "turab.tasks" in s]


def test_a_format_1_row_is_reported_not_replayed():
    result = diagnostic_replay.replay(None, {"request_id": REQ, "run_at": "x",
                                             "blocker_summary": {"format": "turab.blocker-summary/1"},
                                             "suggested_actions": [],
                                             "relaxation_scenarios": []})
    assert result["D"] == [] and "only format 2 is replayed" in result["R"][0]


# --- the format-2 summary (G6-7) ---------------------------------------------------------

def test_g6_7_unknowns_are_split_and_the_versions_named():
    """Per criterion key: the candidates with it UNKNOWN, blocking or not;
    within blocking, actionable (hard gate not FAIL) and high-value. D3's
    three counts keep their meaning; the versions used are named."""
    soft = _c("ROOMS_MIN", "UNKNOWN", importance="PREFERRED", blocking=False)
    records = [
        _record("NEED_MORE_INFORMATION", [DOC_UNKNOWN, PASSING]),              # high-value
        _record("NEED_MORE_INFORMATION", [DOC_UNKNOWN, ROOMS_UNKNOWN]),        # actionable
        _record("REJECTED", [DOC_UNKNOWN, _c("LOCATION", "FAIL")]),            # blocking only
        _record("ELIGIBLE", [PASSING, soft]),                                  # non-blocking
    ]
    out = diagnostic.compute(REQ, records, location_chains={}, evaluated=[], excluded=[])
    summary = out["blocker_summary"]
    assert summary["unknowns"] == {
        "DOCUMENT_TYPE#1": {"blocking": 3, "non_blocking": 0, "actionable": 2,
                            "high_value": 1},
        "ROOMS_MIN#1": {"blocking": 1, "non_blocking": 1, "actionable": 1, "high_value": 0}}
    assert summary["format"] == "turab.blocker-summary/2"
    assert summary["versions"] == {"value": "diagnostic.value@1",
                                   "actions": "diagnostic.actions@1",
                                   "relaxation": "diagnostic.relaxation@1"}
    assert summary["candidates_evaluated"] == 4


def test_an_empty_run_gives_an_empty_valid_format_2():
    """G06: no candidate, a valid document whose empty lists mean "none"."""
    out = diagnostic.compute(REQ, [], location_chains={}, evaluated=[], excluded=[])
    assert (out["suggested_actions"], out["relaxation_scenarios"]) == ([], [])
    assert out["blocker_summary"]["format"] == "turab.blocker-summary/2"
    assert out["blocker_summary"]["unknowns"] == {}
