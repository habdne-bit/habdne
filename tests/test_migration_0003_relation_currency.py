"""0003 — relation currency in the property-scoped consent gate (G3-7).

Ref: RFC-001 R4.6 (`valid_from <= now() < valid_to`, governing use 2, which is
`enforce_consent_binding()` by name); `docs/gate/G3-7_consent_binding_relation_currency.md`.

These are BEHAVIOURAL tests, run against the suite's database, which is built
from the frozen schema and then migrated to head. A fingerprint proves the
function text changed; only these prove it now does the right thing.

Each case is asserted SEPARATELY. A single "the wrong relations are refused"
test would pass against a predicate that caught only one of them.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session


def _consent(session):
    """A GRANTED consent, with its party and scope."""
    row = session.execute(
        text("""SELECT consent_id, party_id, scope::text AS scope
                  FROM turab.consent_grants WHERE status = 'GRANTED' LIMIT 1""")
    ).mappings().first()
    assert row is not None, "the fixtures must seed at least one GRANTED consent"
    return row


def _fresh_property(session, ids):
    return session.execute(
        text("""INSERT INTO turab.properties
                       (property_type, supply_mode, management_mode, claim_status,
                        created_by_account_id)
                VALUES ('APARTMENT', 'PUBLIC', 'ASSISTED', 'UNCLAIMED', :acct)
             RETURNING property_id"""),
        {"acct": ids.ACC_OPERATOR},
    ).scalar_one()


def _relate(session, *, party_id, property_id, valid_from, valid_to=None):
    session.execute(
        text("""INSERT INTO turab.party_property_relations
                       (party_id, property_id, relation_code, valid_from, valid_to)
                VALUES (:party, :prop, 'BROKER', :vf, :vt)"""),
        {"party": party_id, "prop": property_id, "vf": valid_from, "vt": valid_to},
    )


def _bind(session, consent, property_id):
    """Attempt the property-scoped consent binding the gate guards."""
    session.execute(
        text("""INSERT INTO turab.resource_consent_bindings
                       (consent_id, purpose, property_id)
                VALUES (:cid, CAST(:scope AS turab.consent_scope), :prop)"""),
        {"cid": consent["consent_id"], "scope": consent["scope"],
         "prop": property_id},
    )


NOW = datetime.now(UTC)


def test_a_current_relation_permits_a_property_consent_binding(session, ids):
    """The positive case. Without it the others would pass against a gate that
    refuses everything, which is not the rule — it is a broken rule."""
    consent = _consent(session)
    prop = _fresh_property(session, ids)
    _relate(session, party_id=consent["party_id"], property_id=prop,
            valid_from=NOW - timedelta(days=1))
    _bind(session, consent, prop)          # must not raise
    bound = session.execute(
        text("""SELECT count(*) FROM turab.resource_consent_bindings
                 WHERE property_id = :p"""), {"p": prop},
    ).scalar_one()
    assert bound == 1


def test_a_future_relation_is_refused(session, ids):
    """`valid_from` in the future: not yet in force, so it backs nothing.

    This is the case the frozen function accepted.
    """
    consent = _consent(session)
    prop = _fresh_property(session, ids)
    _relate(session, party_id=consent["party_id"], property_id=prop,
            valid_from=NOW + timedelta(days=365 * 70))
    with pytest.raises(Exception, match="no active property relation"):
        _bind(session, consent, prop)


def test_a_relation_with_no_start_is_refused(session, ids):
    """`valid_from IS NULL`: ratified as a REFUSAL, not as "unbounded".

    A NULL cannot satisfy `valid_from <= now()`, and this is a consent gate — a
    relation whose start nobody recorded is not one anyone can show was in
    force. Deliberately asymmetric with `valid_to IS NULL`, which does mean
    "still open"; the next test pins that other half so the asymmetry is
    proven rather than assumed.
    """
    consent = _consent(session)
    prop = _fresh_property(session, ids)
    _relate(session, party_id=consent["party_id"], property_id=prop,
            valid_from=None)
    with pytest.raises(Exception, match="no active property relation"):
        _bind(session, consent, prop)


def test_an_open_ended_relation_is_still_current(session, ids):
    """`valid_to IS NULL` means still open, and must keep working."""
    consent = _consent(session)
    prop = _fresh_property(session, ids)
    _relate(session, party_id=consent["party_id"], property_id=prop,
            valid_from=NOW - timedelta(days=10), valid_to=None)
    _bind(session, consent, prop)          # must not raise


def test_an_expired_relation_is_refused(session, ids):
    consent = _consent(session)
    prop = _fresh_property(session, ids)
    _relate(session, party_id=consent["party_id"], property_id=prop,
            valid_from=NOW - timedelta(days=10), valid_to=NOW - timedelta(days=1))
    with pytest.raises(Exception, match="no active property relation"):
        _bind(session, consent, prop)


def test_no_relation_at_all_is_refused(session, ids):
    """The control. It passed before the migration too, and is kept so a
    regression that disables the whole branch is caught."""
    consent = _consent(session)
    prop = _fresh_property(session, ids)
    with pytest.raises(Exception, match="no active property relation"):
        _bind(session, consent, prop)


def test_another_partys_relation_is_refused(session, ids):
    """A current relation held by SOMEONE ELSE backs nothing for this consent.

    The relation must be the CONSENTING party's; the gate joins on `party_id`,
    and this is the test that would fail if that join were ever dropped while
    the temporal predicate stayed.
    """
    consent = _consent(session)
    other = session.execute(
        text("SELECT party_id FROM turab.parties WHERE party_id <> :p LIMIT 1"),
        {"p": consent["party_id"]},
    ).scalar_one()
    prop = _fresh_property(session, ids)
    _relate(session, party_id=other, property_id=prop,
            valid_from=NOW - timedelta(days=1))
    with pytest.raises(Exception, match="no active property relation"):
        _bind(session, consent, prop)


def test_the_migrated_function_reads_valid_from(session):
    """The text-level companion to the behavioural cases above.

    It states, in one place, that the deployed definition carries the R4.6
    predicate — so a database that was never migrated fails HERE with a clear
    reason rather than through six confusing behavioural failures.
    """
    body = session.execute(
        text("""SELECT pg_get_functiondef(p.oid)
                  FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                 WHERE n.nspname = 'turab'
                   AND p.proname = 'enforce_consent_binding'""")
    ).scalar_one()
    assert "valid_from IS NOT NULL" in body
    assert "valid_from <= now()" in body
    assert "now() < valid_to" in body
