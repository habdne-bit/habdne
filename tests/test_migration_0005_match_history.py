"""0005 — match history and immutable policies cannot be rewritten (G4-14).

Ref: `db/migrations/versions/0005_match_history_immutability.py`;
`docs/gate/evidence/SLICE4-PLAN-MEASUREMENTS.txt` §B and §C, the
measurement taken BEFORE this revision, where each refused write below
succeeded.

The guards are in the DATABASE, so these tests write directly. That is the
point: they must hold for every writer, not only for the engine that Slice 4
has not built yet. The match rows here are fixtures. No matching code
exists.

Each refused write gets its own test, next to the writes that must still
succeed. A guard that refused everything would otherwise pass.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

HISTORY = "Historical TURAB record is immutable"
POLICY = "is immutable: its version, name, rules and immutability cannot change"


def _one(session, sql, **p):
    return session.execute(text(sql), p).scalar_one()


def _refused(session, sql, message, **p):
    """Run `sql` under a savepoint and return the database's refusal."""
    savepoint = session.begin_nested()
    with pytest.raises(DBAPIError) as caught:
        session.execute(text(sql), p)
    savepoint.rollback()
    assert message in str(caught.value), caught.value
    return caught.value


@pytest.fixture
def match(session, ids):
    """A match row, one criterion result and one diagnostic run, as fixture."""
    req = _one(session, """INSERT INTO turab.requests (party_id, transaction_intent,
                                  management_mode, claim_status)
                           VALUES (:p, 'BUY', 'ASSISTED', 'UNCLAIMED') RETURNING request_id""",
               p=ids.BRAHIM)
    criterion = _one(session, """INSERT INTO turab.request_criteria
                                        (request_id, criterion_code, importance, operator, value)
                                 VALUES (:r, 'PROPERTY_TYPE', 'REQUIRED', 'EQ', '"APARTMENT"')
                                 RETURNING request_criterion_id""", r=req)
    prop = _one(session, """INSERT INTO turab.properties (property_type, supply_mode,
                                   management_mode, claim_status)
                            VALUES ('APARTMENT', 'PUBLIC', 'ASSISTED', 'UNCLAIMED')
                            RETURNING property_id""")
    offer = _one(session, """INSERT INTO turab.property_offers (property_id, party_id,
                                    transaction_type, status)
                             VALUES (:p, :party, 'SALE', 'ACTIVE') RETURNING offer_id""",
                 p=prop, party=ids.BRAHIM)
    policy_id, version = session.execute(text(
        "SELECT matching_policy_id, version FROM turab.matching_policies WHERE active")).one()
    match_id = _one(session, """
        INSERT INTO turab.match_candidates
          (request_id, property_id, evaluated_offer_id, matching_policy_id,
           matching_policy_version, request_version, property_version, offer_version,
           eligibility, hard_gate_status, information_gate_status, request_freshness,
           property_freshness, freshness_gate_status, permission_gate_status,
           request_snapshot, property_snapshot, input_hash)
        VALUES (:r, :p, :o, :pol, :v, 1, 1, 1, 'REJECTED', 'FAIL', 'PASS', 'FRESH', 'FRESH',
                'PASS', 'PASS', '{}', '{}', 'fixture')
        RETURNING match_id""", r=req, p=prop, o=offer, pol=policy_id, v=version)
    result = _one(session, """
        INSERT INTO turab.match_criterion_results
          (match_id, request_criterion_id, criterion_code, importance, compatibility,
           blocking, rule_id, rule_version)
        VALUES (:m, :c, 'PROPERTY_TYPE', 'REQUIRED', 'FAIL', true, 'fixture', '1')
        RETURNING match_criterion_result_id""", m=match_id, c=criterion)
    run = _one(session, """
        INSERT INTO turab.match_diagnostic_runs
          (request_id, request_version, matching_policy_id, matching_policy_version,
           request_snapshot, input_hash)
        VALUES (:r, 1, :pol, :v, '{}', 'fixture') RETURNING diagnostic_run_id""",
               r=req, pol=policy_id, v=version)
    return {"match": match_id, "result": result, "run": run, "criterion": criterion,
            "policy": policy_id, "version": version}


# --- criterion results -------------------------------------------------------------

def test_a_criterion_result_cannot_be_turned_from_fail_to_pass(session, match):
    _refused(session, """UPDATE turab.match_criterion_results
                            SET compatibility = 'PASS', blocking = false
                          WHERE match_criterion_result_id = :i""", HISTORY, i=match["result"])
    assert _one(session, """SELECT compatibility::text FROM turab.match_criterion_results
                             WHERE match_criterion_result_id = :i""",
                i=match["result"]) == "FAIL"


def test_a_criterion_result_cannot_be_deleted(session, match):
    _refused(session, "DELETE FROM turab.match_criterion_results "
                      "WHERE match_criterion_result_id = :i", HISTORY, i=match["result"])


def test_a_criterion_result_can_still_be_appended(session, match):
    """Append-only, not frozen: a new result row is how history grows."""
    session.execute(text("""
        INSERT INTO turab.match_criterion_results
          (match_id, criterion_code, ordinal, importance, compatibility, rule_id, rule_version)
        VALUES (:m, 'LOCATION', 1, 'REQUIRED', 'PASS', 'fixture', '1')"""), {"m": match["match"]})
    assert _one(session, "SELECT count(*) FROM turab.match_criterion_results "
                         "WHERE match_id = :m", m=match["match"]) == 2


def test_deleting_a_request_criterion_a_result_cites_is_refused(session, match):
    """The interaction declared before approval (plan G4-14):
    `request_criterion_id` is ON DELETE SET NULL, and a SET NULL is an UPDATE
    of a guarded row. No code path deletes criteria; this pins the
    consequence so a future deletion path meets it in a test, not in
    production."""
    _refused(session, "DELETE FROM turab.request_criteria WHERE request_criterion_id = :c",
             HISTORY, c=match["criterion"])


# --- diagnostic runs ---------------------------------------------------------------------

def test_a_diagnostic_run_cannot_be_updated(session, match):
    _refused(session, """UPDATE turab.match_diagnostic_runs SET ready_opportunity_count = 5
                          WHERE diagnostic_run_id = :i""", HISTORY, i=match["run"])


def test_a_diagnostic_run_cannot_be_deleted(session, match):
    _refused(session, "DELETE FROM turab.match_diagnostic_runs WHERE diagnostic_run_id = :i",
             HISTORY, i=match["run"])


def test_the_match_row_itself_still_refuses_as_the_frozen_schema_made_it(session, match):
    _refused(session, "UPDATE turab.match_candidates SET eligibility = 'ELIGIBLE' "
                      "WHERE match_id = :m", HISTORY, m=match["match"])


# --- matching policies ------------------------------------------------------------------

@pytest.mark.parametrize("assignment", [
    "rules = rules || '{\"probe\": true}'",
    "version = '9.9.9'",
    "name = 'renamed'",
    "immutable = false",
])
def test_an_immutable_policy_cannot_change(session, assignment):
    _refused(session, f"UPDATE turab.matching_policies SET {assignment} WHERE version = '0.2.0'",
             POLICY)


def test_an_immutable_policy_can_still_be_activated_and_deactivated(session):
    session.execute(text("UPDATE turab.matching_policies SET active = false, "
                         "activated_at = NULL WHERE version = '0.2.0'"))
    session.execute(text("UPDATE turab.matching_policies SET active = true, "
                         "activated_at = now() WHERE version = '0.2.0'"))
    assert _one(session, "SELECT active FROM turab.matching_policies "
                         "WHERE version = '0.2.0'") is True


def test_a_mutable_policy_is_editable_until_it_is_made_immutable(session):
    session.execute(text("""INSERT INTO turab.matching_policies (version, name, rules, immutable)
                            VALUES ('draft-1', 'draft', '{}', false)"""))
    session.execute(text("UPDATE turab.matching_policies SET rules = '{\"a\": 1}' "
                         "WHERE version = 'draft-1'"))
    session.execute(text("UPDATE turab.matching_policies SET immutable = true "
                         "WHERE version = 'draft-1'"))
    _refused(session, "UPDATE turab.matching_policies SET rules = '{\"a\": 2}' "
                      "WHERE version = 'draft-1'", POLICY)
    assert _one(session, "SELECT rules FROM turab.matching_policies "
                         "WHERE version = 'draft-1'") == {"a": 1}
