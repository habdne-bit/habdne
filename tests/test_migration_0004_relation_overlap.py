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
    """Two connections, two transactions, with the wait BOUND TO THIS RACE.

    Unlike the primary-source case, this DOES have a winner and a loser, and
    the reason is the difference an earlier review drew: there is no lock here
    that serialises two paths into both succeeding. The exclusion index makes
    the contender WAIT, and when the holder COMMITS the contender's row is
    genuinely excluded — so it fails with SQLSTATE `23P01`
    (`exclusion_violation`). The refusal is the constraint's, not a version
    guard's, which is why expecting a loser is legitimate here.

    **The witness is specific, not ambient.** A first version counted ANY
    backend on the database with `wait_event_type = 'Lock'`. On a busy server —
    or simply alongside another test — that counts someone else's wait and the
    test would claim an interleaving it never observed. Both workers therefore
    report their own `pg_backend_pid()`, and the watcher requires
    `pg_blocking_pids(contender_pid)` to contain the HOLDER's pid: the database
    stating that this contender is blocked by this holder.

    Both workers' outcomes are asserted, and every thread is joined before any
    of them is read — a test that inspects results while a worker is still
    running is reading a race of its own.
    """
    import threading
    import time

    from sqlalchemy.orm import Session as _Session

    engine_a, engine_b = two_engines
    with _Session(bind=engine, future=True) as s:
        prop = _property(s, ids)
        s.commit()

    out: dict[str, object] = {}
    pids: dict[str, int] = {}
    holds = threading.Event()
    contender_started = threading.Event()
    witnessed = threading.Event()

    def holder():
        try:
            with _Session(bind=engine_a, future=True) as s:
                pids["holder"] = s.execute(text("SELECT pg_backend_pid()")).scalar_one()
                _relate(s, party=ids.AMINA, prop=prop,
                        valid_from=NOW - timedelta(days=5))
                holds.set()
                assert witnessed.wait(timeout=30), (
                    "the database never reported the contender blocked BY THIS "
                    "holder; the interleaving was not observed"
                )
                s.commit()
            out["holder"] = "ok"
        except Exception as exc:                       # pragma: no cover
            out["holder"] = f"raised {type(exc).__name__}: {exc}"

    def contender():
        assert holds.wait(timeout=30), "the holder never inserted"
        try:
            with _Session(bind=engine_b, future=True) as s:
                pids["contender"] = s.execute(
                    text("SELECT pg_backend_pid()")).scalar_one()
                contender_started.set()
                _relate(s, party=ids.AMINA, prop=prop,
                        valid_from=NOW - timedelta(days=1))
                s.commit()
            out["contender"] = "ok"
        except Exception as exc:
            out["contender"] = getattr(
                getattr(exc, "orig", None), "sqlstate", None
            ) or f"raised {type(exc).__name__}"

    def watch():
        """Wait for PostgreSQL to say: this contender is blocked by this holder."""
        assert contender_started.wait(timeout=30), "the contender never connected"
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            with _Session(bind=engine, future=True) as s:
                blockers = s.execute(
                    text("SELECT pg_blocking_pids(:pid)"),
                    {"pid": pids["contender"]},
                ).scalar_one()
            if pids.get("holder") in (blockers or []):
                out["blocked_by_holder"] = True
                witnessed.set()
                return
            time.sleep(0.02)
        out["blocked_by_holder"] = False
        witnessed.set()          # release the holder so the test fails cleanly

    threads = [threading.Thread(target=holder), threading.Thread(target=contender),
               threading.Thread(target=watch)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    assert not any(t.is_alive() for t in threads), "a worker never finished"

    assert out.get("blocked_by_holder") is True, (
        f"no interleaving witnessed for this race: {out}, pids={pids}")
    assert out.get("holder") == "ok", out
    assert out.get("contender") == "23P01", (
        f"expected the contender to fail with SQLSTATE 23P01, got {out.get('contender')!r}")

    with _Session(bind=engine, future=True) as s:
        rows = s.execute(
            text("""SELECT count(*) FROM turab.party_property_relations
                     WHERE property_id = :p AND party_id = :a"""),
            {"p": prop, "a": ids.AMINA},
        ).scalar_one()
    assert rows == 1, f"exactly one row must survive, found {rows}"
