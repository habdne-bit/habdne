"""0004 — no two overlapping relations for one (party, property, code).

Ref: the G3-6 Contract Delta §6 (rule 6a, ratified);
`db/migrations/versions/0004_relation_overlap_guard.py`.

The rule is enforced in the DATABASE, so these tests write directly rather than
through an API — which is the point: it must hold for every writer, including
an importer, a fixture, and a hand-run INSERT, not only for the command path.

Each distinguishing case is separate. "Overlaps are refused" as one test would
pass against a constraint that also refused the three things it must allow.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import text

NOW = datetime.now(UTC)


def _property(session, ids):
    return session.execute(
        text("""INSERT INTO turab.properties
                       (property_type, supply_mode, management_mode, claim_status,
                        created_by_account_id)
                VALUES ('LAND', 'PUBLIC', 'ASSISTED', 'UNCLAIMED', :acct)
             RETURNING property_id"""),
        {"acct": ids.ACC_OPERATOR},
    ).scalar_one()


def _relate(session, *, party, prop, code="BROKER", valid_from, valid_to=None):
    session.execute(
        text("""INSERT INTO turab.party_property_relations
                       (party_id, property_id, relation_code, valid_from, valid_to)
                VALUES (:party, :prop, :code, :vf, :vt)"""),
        {"party": party, "prop": prop, "code": code, "vf": valid_from, "vt": valid_to},
    )


def test_two_overlapping_relations_for_one_triple_are_refused(session, ids):
    prop = _property(session, ids)
    _relate(session, party=ids.AMINA, prop=prop, valid_from=NOW - timedelta(days=5))
    with pytest.raises(Exception, match="no_overlap"):
        _relate(session, party=ids.AMINA, prop=prop,
                valid_from=NOW - timedelta(days=1))


def test_a_relation_resumed_after_the_previous_one_ended_is_allowed(session, ids):
    """Successive periods are the whole reason the rule is about intervals
    rather than about a flag: a broker who stops and later resumes must be
    expressible, and the history of both periods must survive."""
    prop = _property(session, ids)
    _relate(session, party=ids.AMINA, prop=prop,
            valid_from=NOW - timedelta(days=30), valid_to=NOW - timedelta(days=10))
    _relate(session, party=ids.AMINA, prop=prop,
            valid_from=NOW - timedelta(days=5))       # must not raise
    rows = session.execute(
        text("""SELECT count(*) FROM turab.party_property_relations
                 WHERE property_id = :p AND party_id = :a"""),
        {"p": prop, "a": ids.AMINA},
    ).scalar_one()
    assert rows == 2, "both periods must remain; nothing is overwritten"


def test_a_different_relation_code_never_conflicts(session, ids):
    """A party may be both the declared owner and the contact person."""
    prop = _property(session, ids)
    _relate(session, party=ids.AMINA, prop=prop, code="OWNER_DECLARED",
            valid_from=NOW - timedelta(days=1))
    _relate(session, party=ids.AMINA, prop=prop, code="CONTACT_PERSON",
            valid_from=NOW - timedelta(days=1))       # must not raise


def test_a_different_party_never_conflicts(session, ids):
    """Two brokers on one property is a real situation, not a conflict."""
    prop = _property(session, ids)
    other = session.execute(
        text("SELECT party_id FROM turab.parties WHERE party_id <> :a LIMIT 1"),
        {"a": ids.AMINA},
    ).scalar_one()
    _relate(session, party=ids.AMINA, prop=prop, valid_from=NOW - timedelta(days=1))
    _relate(session, party=other, prop=prop, valid_from=NOW - timedelta(days=1))


def test_a_relation_with_no_start_still_participates_in_the_guard(session, ids):
    """`valid_from IS NULL` is treated as `-infinity` HERE, while the 0003
    consent gate refuses it.

    Not a contradiction, and worth stating because it looks like one: 0003 asks
    "can this relation be shown to be in force?", where an unrecorded start
    means no. This constraint asks "could these two rows describe the same
    period?", where a row with no start must be INCLUDED — otherwise a row that
    cannot back a consent could still sit invisibly under the overlap guard and
    hide a genuine conflict.
    """
    prop = _property(session, ids)
    _relate(session, party=ids.AMINA, prop=prop, valid_from=None)
    with pytest.raises(Exception, match="no_overlap"):
        _relate(session, party=ids.AMINA, prop=prop,
                valid_from=NOW - timedelta(days=1))


def test_the_guard_is_a_database_constraint_not_a_service_check(session):
    """Asserted on the catalog: the rule must hold for every writer.

    If this ever becomes a service-only check again, the G3-6 Delta's stated
    weakness — the one uniqueness rule in the slice with no database backstop —
    comes back, and this test is what would say so.
    """
    kind = session.execute(
        text("""SELECT contype FROM pg_constraint
                 WHERE conname = 'party_property_relations_no_overlap'""")
    ).scalar_one_or_none()
    assert kind == "x", f"expected an EXCLUDE constraint, got {kind!r}"
