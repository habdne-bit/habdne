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
from sqlalchemy import create_engine, text

NOW = datetime.now(UTC)


@pytest.fixture
def two_engines(database_url):
    """Two independent engines — two real backend connections."""
    a = create_engine(database_url, future=True, poolclass=None)
    b = create_engine(database_url, future=True, poolclass=None)
    yield a, b
    a.dispose()
    b.dispose()


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


# --- the constraint under real contention ----------------------------------
#
# Every test above is sequential in ONE session, which shows what the
# constraint does when nothing is racing it. That is not the case it exists
# for. `EXCLUDE` is enforced by an index that makes the second inserter WAIT
# on the first, and the outcome depends on what the first transaction does —
# which a single session cannot exhibit at all.

def test_two_concurrent_overlapping_inserts_leave_exactly_one_row(
    two_engines, engine, ids
):
    """Two connections, two transactions, a deterministic handshake.

    Unlike the primary-source case, this DOES have a winner and a loser, and
    the reason is the difference the last review drew: there is no lock here
    that serialises two paths into both succeeding. The exclusion index makes
    the contender WAIT, and when the holder COMMITS the contender's row is
    then genuinely excluded — so it fails, with SQLSTATE `23P01`
    (`exclusion_violation`). The refusal is the constraint's, not a version
    guard's, which is why it is legitimate to expect one here.

    Both workers' outcomes are asserted, not just the surviving row: a test
    that checked only the row count would pass if BOTH had failed.
    """
    import threading

    from sqlalchemy.orm import Session as _Session

    engine_a, engine_b = two_engines
    with _Session(bind=engine, future=True) as s:
        prop = _property(s, ids)
        s.commit()

    out: dict[str, tuple[str, object]] = {}
    holds = threading.Event()
    contender_blocked = threading.Event()

    def holder():
        try:
            with _Session(bind=engine_a, future=True) as s:
                _relate(s, party=ids.AMINA, prop=prop,
                        valid_from=NOW - timedelta(days=5))
                holds.set()
                # Wait until the database itself reports the contender waiting
                # on a lock. Ordering by sleep would prove only that time
                # passed, not that the second transaction ever reached the
                # contended point.
                assert contender_blocked.wait(timeout=20), (
                    "the contender never reached the exclusion index"
                )
                s.commit()
            out["holder"] = ("ok", None)
        except Exception as exc:                       # pragma: no cover
            out["holder"] = ("raised", f"{type(exc).__name__}: {exc}")

    def contender():
        assert holds.wait(timeout=20), "the holder never inserted"
        try:
            with _Session(bind=engine_b, future=True) as s:
                _relate(s, party=ids.AMINA, prop=prop,
                        valid_from=NOW - timedelta(days=1))
                s.commit()
            out["contender"] = ("ok", None)
        except Exception as exc:
            out["contender"] = ("raised", getattr(
                getattr(exc, "orig", None), "sqlstate", None) or f"{type(exc).__name__}")

    def watch():
        """Witness the contention, then release the holder."""
        import time

        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            with _Session(bind=engine, future=True) as s:
                blocked = s.execute(
                    text("""SELECT count(*) FROM pg_stat_activity
                             WHERE datname = current_database()
                               AND pid <> pg_backend_pid()
                               AND wait_event_type = 'Lock'""")
                ).scalar_one()
            if blocked:
                contender_blocked.set()
                return
            time.sleep(0.02)
        contender_blocked.set()   # release the holder so the test fails cleanly

    threads = [threading.Thread(target=holder), threading.Thread(target=contender),
               threading.Thread(target=watch)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=40)

    assert out.get("holder") == ("ok", None), out
    kind, payload = out.get("contender", (None, None))
    assert kind == "raised", f"both inserts succeeded: {out}"
    assert payload == "23P01", (
        f"expected SQLSTATE 23P01 (exclusion_violation), got {payload!r}"
    )

    with _Session(bind=engine, future=True) as s:
        rows = s.execute(
            text("""SELECT count(*) FROM turab.party_property_relations
                     WHERE property_id = :p AND party_id = :a"""),
            {"p": prop, "a": ids.AMINA},
        ).scalar_one()
    assert rows == 1, f"exactly one row must survive, found {rows}"
