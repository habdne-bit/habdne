"""0006 — an opportunity's history cannot be rewritten (G5-12).

Ref: `db/migrations/versions/0006_opportunity_history.py`;
`docs/gate/SLICE_5_PLAN.md` revision 4, G5-12 (approved in the review of
6ba73ce): the five edges, rules 1–6, the birth rule, the B-case table and the
fifteen event-stamp cases; `docs/gate/evidence/SLICE5-PLAN-MEASUREMENTS.txt`
§B, the measurement taken BEFORE this revision, where B4–B17 were accepted.

The guards are in the DATABASE, so these tests write directly. That is the
point: they must hold for every writer, not only for the review and
opportunity commands that Slice 5 has not built yet. The match, review and
opportunity rows here are fixtures; no Slice 5 code exists.

Each refused write is tested next to the writes that must still succeed. A
guard that refused everything would otherwise pass.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

R1 = "a CLOSED opportunity is final"
R2 = "are written once"
R3 = "is not a permitted edge"
R4 = "closed_at and close_reason_code are set exactly when the status is CLOSED"
R5 = "shared_at is set only on NEW -> SHARED"
R6 = "engaged_at is set only on SHARED -> ENGAGED"
BIRTH = "a new opportunity is NEW and VALID"
GATE = "Opportunity request/property must match approved candidate"
GATE_REVIEW = "Opportunity requires the latest human review to be APPROVED"

CLOSE = "status = 'CLOSED', closed_at = now(), close_reason_code = 'BUYER_REJECTED'"


def _one(session, sql, **p):
    return session.execute(text(sql), p).scalar_one()


def _refused(session, sql, *messages, **p):
    """Run `sql` under a savepoint; it must be refused with one of `messages`."""
    savepoint = session.begin_nested()
    with pytest.raises(DBAPIError) as caught:
        session.execute(text(sql), p)
    savepoint.rollback()
    assert any(m in str(caught.value) for m in messages), caught.value
    return caught.value


def _accepted(session, sql, **p):
    """Run `sql` under a savepoint that is kept; return nothing."""
    savepoint = session.begin_nested()
    session.execute(text(sql), p)
    savepoint.commit()


def _match(session, ids, req, prop, offer, policy_id, version, *, approved):
    match_id = _one(session, """
        INSERT INTO turab.match_candidates
          (request_id, property_id, evaluated_offer_id, matching_policy_id,
           matching_policy_version, request_version, property_version, offer_version,
           eligibility, hard_gate_status, information_gate_status, request_freshness,
           property_freshness, offer_freshness, freshness_gate_status,
           permission_gate_status, request_snapshot, property_snapshot, input_hash)
        VALUES (:r, :p, :o, :pol, :v, 1, 1, 1, 'ELIGIBLE', 'PASS', 'PASS', 'FRESH', 'FRESH',
                'FRESH', 'PASS', 'PASS', '{}', '{}', :h)
        RETURNING match_id""", r=req, p=prop, o=offer, pol=policy_id, v=version,
        h=f"fixture-{offer}")
    if approved:
        session.execute(text("""
            INSERT INTO turab.match_reviews (match_id, decision, reviewer_account_id)
            VALUES (:m, 'APPROVED', :a)"""), {"m": match_id, "a": ids.ACC_REVIEWER})
    return match_id


INSERT = """
    INSERT INTO turab.opportunities (request_id, property_id, approved_match_id,
                                     current_offer_id, sharing_scope, why_real,
                                     created_by_account_id{extra_cols})
    SELECT request_id, property_id, match_id, evaluated_offer_id, 'SUMMARY_ONLY',
           '{{"format": "fixture"}}'::jsonb, :acct{extra_vals}
      FROM turab.match_candidates WHERE match_id = :m"""


def _insert(extra=None):
    extra = extra or {}
    cols = "".join(f", {c}" for c in extra)
    vals = "".join(f", {v}" for v in extra.values())
    return INSERT.format(extra_cols=cols, extra_vals=vals)


@pytest.fixture
def world(session, ids):
    """One request and property; three ACTIVE SALE offers, each with an
    ELIGIBLE match: the first APPROVED and holding an open NEW opportunity,
    the second APPROVED without one (`spare`), the third not reviewed."""
    req = _one(session, """INSERT INTO turab.requests (party_id, transaction_intent,
                                  management_mode, claim_status)
                           VALUES (:p, 'BUY', 'ASSISTED', 'UNCLAIMED') RETURNING request_id""",
               p=ids.BRAHIM)
    prop = _one(session, """INSERT INTO turab.properties (property_type, supply_mode,
                                   management_mode, claim_status)
                            VALUES ('APARTMENT', 'PUBLIC', 'ASSISTED', 'UNCLAIMED')
                            RETURNING property_id""")
    offers = [_one(session, """INSERT INTO turab.property_offers (property_id, party_id,
                                      transaction_type, status)
                               VALUES (:p, :party, 'SALE', 'ACTIVE') RETURNING offer_id""",
                   p=prop, party=ids.BRAHIM) for _ in range(3)]
    policy_id, version = session.execute(text(
        "SELECT matching_policy_id, version FROM turab.matching_policies WHERE active")).one()
    m1, spare, unreviewed = (
        _match(session, ids, req, prop, o, policy_id, version, approved=a)
        for o, a in zip(offers, (True, True, False)))
    session.execute(text(_insert()), {"m": m1, "acct": ids.ACC_REVIEWER})
    opp = _one(session, "SELECT opportunity_id FROM turab.opportunities "
                        "WHERE approved_match_id = :m", m=m1)
    other_req = _one(session, """INSERT INTO turab.requests (party_id, transaction_intent,
                                        management_mode, claim_status)
                                 VALUES (:p, 'BUY', 'ASSISTED', 'UNCLAIMED')
                                 RETURNING request_id""", p=ids.BRAHIM)
    other_prop = _one(session, """INSERT INTO turab.properties (property_type, supply_mode,
                                         management_mode, claim_status)
                                  VALUES ('APARTMENT', 'PUBLIC', 'ASSISTED', 'UNCLAIMED')
                                  RETURNING property_id""")
    return {"opp": opp, "offers": offers, "spare": spare, "unreviewed": unreviewed,
            "other_req": other_req, "other_prop": other_prop}


def _update(assignment):
    return f"UPDATE turab.opportunities SET {assignment} WHERE opportunity_id = :o"


def _row(session, opp):
    return session.execute(text("""
        SELECT status::text AS status, shared_at, engaged_at, closed_at, close_reason_code
          FROM turab.opportunities WHERE opportunity_id = :o"""), {"o": opp}).mappings().one()


def _to(session, opp, state):
    """Bring the NEW fixture opportunity to `state` along permitted edges."""
    if state in ("SHARED", "ENGAGED"):
        _accepted(session, _update("status = 'SHARED', shared_at = now()"), o=opp)
    if state == "ENGAGED":
        _accepted(session, _update("status = 'ENGAGED', engaged_at = now()"), o=opp)
    if state == "CLOSED":
        _accepted(session, _update(CLOSE), o=opp)
    assert _row(session, opp)["status"] == state


# ======================================================================================
# The birth rule (enforce_opportunity_birth)
# ======================================================================================

def test_an_opportunity_is_born_new_and_valid_with_no_event_time(session, world):
    row = session.execute(text("""
        SELECT status::text, validity_status::text, shared_at, engaged_at, closed_at,
               close_reason_code
          FROM turab.opportunities WHERE opportunity_id = :o"""), {"o": world["opp"]}).one()
    assert tuple(row) == ("NEW", "VALID", None, None, None, None)


@pytest.mark.parametrize("extra", [
    {"status": "'SHARED'"},
    {"status": "'ENGAGED'"},
    {"status": "'CLOSED'", "closed_at": "now()", "close_reason_code": "'BUYER_REJECTED'"},
    {"validity_status": "'NEEDS_CONFIRMATION'"},
    {"validity_status": "'INVALID'"},
    {"shared_at": "now()"},
    {"engaged_at": "now()"},
    {"closed_at": "now()"},
    {"close_reason_code": "'BUYER_REJECTED'"},
], ids=lambda e: "+".join(e))
def test_any_other_birth_is_refused(session, ids, world, extra):
    """A row cannot be born with a history it did not live: shared, engaged,
    closed, or other than VALID. The test identity (test_slice3_identity) that
    inserted a born-CLOSED opportunity was the first writer this caught."""
    _refused(session, _insert(extra), BIRTH, m=world["spare"], acct=ids.ACC_REVIEWER)


# ======================================================================================
# Rule 2: written once (B1–B9, and known_differences)
# ======================================================================================

@pytest.mark.parametrize("case,assignment", [
    ("B1 request_id", "request_id = :x_req"),
    ("B2 property_id", "property_id = :x_prop"),
    ("B3 approved_match_id", "approved_match_id = :x_match"),
])
def test_the_pair_and_the_match_cannot_change(session, world, case, assignment):
    """Refused today by trg_opportunity_gate's re-check, which fires first
    (triggers fire in name order); rule 2 refuses them too."""
    _refused(session, _update(assignment), GATE, GATE_REVIEW, R2, o=world["opp"],
             x_req=world["other_req"], x_prop=world["other_prop"],
             x_match=world["unreviewed"])


@pytest.mark.parametrize("case,assignment", [
    ("B4 commercial_context_snapshot",
     "commercial_context_snapshot = '{\"rewritten\": true}'::jsonb"),
    ("B5 permission_snapshot", "permission_snapshot = '{\"rewritten\": true}'::jsonb"),
    ("B6 why_real", "why_real = '{\"rewritten\": true}'::jsonb"),
    ("known_differences", "known_differences = '[\"rewritten\"]'::jsonb"),
    ("B7 sharing_scope", "sharing_scope = 'CONTACT_AFTER_CONFIRMATION'"),
    ("B8 created_by_account_id", "created_by_account_id = :x_acct"),
    ("B9 created_at", "created_at = created_at - interval '1 year'"),
], ids=lambda v: v.split()[0] if " " in v else v)
def test_a_field_written_at_creation_cannot_be_rewritten(session, ids, world, case,
                                                        assignment):
    _refused(session, _update(assignment), R2, o=world["opp"], x_acct=ids.ACC_OPERATOR)


def test_rule_2_holds_on_a_permitted_edge_too(session, world):
    """Taking an edge does not open the history columns."""
    _refused(session, _update(f"{CLOSE}, why_real = '{{}}'::jsonb"), R2, o=world["opp"])


def test_rule_2_refuses_a_match_change_the_frozen_gate_accepts(session, world):
    """B3, in the form the frozen gate ACCEPTS: the spare match is APPROVED,
    ELIGIBLE and of the same pair, so `trg_opportunity_gate`'s re-check
    passes. Only rule 2 refuses it.

    The first mutation run (H2c) showed that the B3 test above could not
    tell rule 2 from the gate, because the gate refused first."""
    _refused(session, _update("approved_match_id = :x"), R2, o=world["opp"],
             x=world["spare"])


@pytest.mark.parametrize("case,assignment", [
    ("B1 request_id", "request_id = :x_req"),
    ("B2 property_id", "property_id = :x_prop"),
    ("B3 approved_match_id", "approved_match_id = :x_match"),
])
def test_rule_2_alone_refuses_the_pair_and_the_match(session, world, case, assignment):
    """Rule 2 in isolation. Inside this test's transaction, which is rolled
    back, the frozen `trg_opportunity_gate` is disabled, so the refusal can
    only come from rule 2.

    Without this, removing request_id or property_id from rule 2 (H2a,
    H2b) survives: with the gate present, no UPDATE that changes either
    column alone is accepted by the gate. That makes the gate the operative
    guard and rule 2 a second one behind it, as the plan states. This test
    pins the second guard on its own.

    It uses the superuser's ability to disable a trigger (EN-02) to TEST a
    guard. It is not a claim about K06."""
    session.execute(text("ALTER TABLE turab.opportunities DISABLE TRIGGER trg_opportunity_gate"))
    _refused(session, _update(assignment), R2, o=world["opp"],
             x_req=world["other_req"], x_prop=world["other_prop"],
             x_match=world["unreviewed"])


def test_b10_current_offer_id_stays_accepted_by_the_schema(session, world):
    """B10 is NOT refused by 0006: the contract lets revalidate update the
    current offer context (API_CONTRACTS §4.11). The guard for Slice 5 is the
    service's (G5-12, three proofs), and this test pins that the schema
    still accepts it, so the attribution cannot drift silently."""
    _accepted(session, _update("current_offer_id = :x"), o=world["opp"],
              x=world["offers"][1])


# ======================================================================================
# The columns left writable
# ======================================================================================

@pytest.mark.parametrize("assignment", [
    "validity_status = 'NEEDS_CONFIRMATION'",
    "validity_status = 'INVALID'",
    "last_confirmed_at = now()",
    "last_activity_at = now()",
    "current_permission_binding_id = (SELECT consent_binding_id "
    "FROM turab.resource_consent_bindings ORDER BY consent_binding_id LIMIT 1)",
    "current_permission_binding_id = NULL",
])
def test_the_writable_columns_stay_writable(session, world, assignment):
    _accepted(session, _update(assignment), o=world["opp"])


def test_validity_is_not_monotonic(session, world):
    for v in ("INVALID", "NEEDS_CONFIRMATION", "VALID"):
        _accepted(session, _update(f"validity_status = '{v}'"), o=world["opp"])


# ======================================================================================
# Rule 3: only the five edges (B11, B16)
# ======================================================================================

@pytest.mark.parametrize("start,target,stamps", [
    ("NEW", "ENGAGED", ""),                                   # B11
    ("NEW", "ENGAGED", ", engaged_at = now()"),
    ("SHARED", "NEW", ""),                                    # B16
    ("ENGAGED", "SHARED", ""),
    ("ENGAGED", "NEW", ""),
])
def test_a_status_change_off_the_graph_is_refused(session, world, start, target, stamps):
    _to(session, world["opp"], start)
    _refused(session, _update(f"status = '{target}'{stamps}"), R3, o=world["opp"])


# ======================================================================================
# Rule 4: the closing fields (B12, B13)
# ======================================================================================

@pytest.mark.parametrize("assignment", [
    "status = 'CLOSED'",                                                    # B12
    "status = 'CLOSED', closed_at = now()",
    "status = 'CLOSED', close_reason_code = 'BUYER_REJECTED'",
    "closed_at = now()",                                                    # B13
    "close_reason_code = 'BUYER_REJECTED'",
])
def test_the_closing_fields_go_with_the_closed_status(session, world, assignment):
    _refused(session, _update(assignment), R4, o=world["opp"])


# ======================================================================================
# Rule 1: a CLOSED row is final (B14, B15)
# ======================================================================================

@pytest.mark.parametrize("assignment", [
    "status = 'NEW', closed_at = NULL, close_reason_code = NULL",            # B14
    "status = 'SHARED', closed_at = NULL, close_reason_code = NULL, shared_at = now()",  # B15
    "validity_status = 'INVALID'",
    "last_activity_at = now()",
    "status = status",
])
def test_a_closed_opportunity_is_final(session, world, assignment):
    _to(session, world["opp"], "CLOSED")
    _refused(session, _update(assignment), R1, o=world["opp"])


# ======================================================================================
# Rules 5 and 6 [R4-1]: the event stamps, case by case (plan G5-12, 15 cases)
# ======================================================================================

STAMP_CASES = [
    # (id, start, change, expected: None = accepted, else the rule's message)
    ("NEW-close-stamps-null", "NEW", CLOSE, None),
    ("NEW-close-shared-supplied", "NEW", f"{CLOSE}, shared_at = now()", R5),
    ("NEW-close-engaged-supplied", "NEW", f"{CLOSE}, engaged_at = now()", R6),
    ("SHARED-close-engaged-null", "SHARED", CLOSE, None),
    ("SHARED-close-engaged-supplied", "SHARED", f"{CLOSE}, engaged_at = now()", R6),
    ("ENGAGED-close", "ENGAGED", CLOSE, None),
    ("NEW-share-without-shared_at", "NEW", "status = 'SHARED'", R5),
    ("NEW-share-with-shared_at", "NEW", "status = 'SHARED', shared_at = now()", None),
    ("NEW-share-engaged-supplied", "NEW",
     "status = 'SHARED', shared_at = now(), engaged_at = now()", R6),
    ("SHARED-engage-without-engaged_at", "SHARED", "status = 'ENGAGED'", R6),
    ("SHARED-engage-with-engaged_at", "SHARED", "status = 'ENGAGED', engaged_at = now()",
     None),
    ("NEW-unchanged-shared-supplied", "NEW", "shared_at = now()", R5),
    ("SHARED-unchanged-engaged-supplied", "SHARED", "engaged_at = now()", R6),
    ("SHARED-shared_at-moved", "SHARED", "shared_at = shared_at + interval '1 second'", R5),
    ("SHARED-shared_at-cleared", "SHARED", "shared_at = NULL", R5),           # B17
    ("ENGAGED-engaged_at-moved", "ENGAGED",
     "engaged_at = engaged_at + interval '1 second'", R6),
    ("ENGAGED-engaged_at-cleared", "ENGAGED", "engaged_at = NULL", R6),
]


@pytest.mark.parametrize("case,start,change,expected", STAMP_CASES,
                         ids=[c[0] for c in STAMP_CASES])
def test_event_stamps(session, world, case, start, change, expected):
    _to(session, world["opp"], start)
    before = _row(session, world["opp"])
    if expected is not None:
        _refused(session, _update(change), expected, o=world["opp"])
        assert _row(session, world["opp"]) == before, "a refusal changes nothing"
        return
    _accepted(session, _update(change), o=world["opp"])
    after = _row(session, world["opp"])
    if after["status"] == "CLOSED":
        # Closing keeps the stamps of events that happened, and invents none.
        assert after["shared_at"] == before["shared_at"]
        assert after["engaged_at"] == before["engaged_at"]
        if start == "NEW":
            assert after["shared_at"] is None and after["engaged_at"] is None
        if start == "SHARED":
            assert after["shared_at"] is not None and after["engaged_at"] is None


def test_a_never_shared_opportunity_closes_with_no_stamp_and_frees_the_pair(session, ids,
                                                                          world):
    """The precondition of the plan's 'closing frees the pair' test (§6.1
    test 6; measured F2): a NEW opportunity closes with both stamps null, and
    the pair's other approved match may then become an opportunity."""
    _accepted(session, _update(CLOSE), o=world["opp"])
    row = _row(session, world["opp"])
    assert (row["status"], row["shared_at"], row["engaged_at"]) == ("CLOSED", None, None)
    _accepted(session, _insert(), m=world["spare"], acct=ids.ACC_REVIEWER)


def test_the_frozen_delete_guard_is_unchanged(session, world):
    """B18: still refused by prevent_delete_opportunities (frozen)."""
    _refused(session, "DELETE FROM turab.opportunities WHERE opportunity_id = :o",
             "Hard delete prohibited", o=world["opp"])


def test_no_refusal_text_names_an_id(session, ids, world):
    """G5-12, the error texts: fixed per rule, naming no id."""
    errors = [
        _refused(session, _update("why_real = '{}'::jsonb"), R2, o=world["opp"]),
        _refused(session, _update("status = 'ENGAGED'"), R3, o=world["opp"]),
        _refused(session, _update("closed_at = now()"), R4, o=world["opp"]),
        _refused(session, _update("shared_at = now()"), R5, o=world["opp"]),
        _refused(session, _update("engaged_at = now()"), R6, o=world["opp"]),
        _refused(session, _insert({"status": "'SHARED'"}), BIRTH, m=world["spare"],
                 acct=ids.ACC_REVIEWER),
    ]
    _to(session, world["opp"], "CLOSED")
    errors.append(_refused(session, _update("last_activity_at = now()"), R1, o=world["opp"]))
    for e in errors:
        primary = e.orig.diag.message_primary
        assert str(world["opp"]) not in primary and str(world["spare"]) not in primary
