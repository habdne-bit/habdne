"""Concurrency on real PostgreSQL: two connections, two transactions.

Ref: independent review R-S2-01 and R-S2-02; PostgreSQL 16 "Transaction
Isolation" — under the default Read Committed level each statement takes its
own snapshot and a plain `SELECT` acquires no lasting lock, so "both inside a
transaction" is not by itself an atomic read-then-write.

Every test here opens TWO engines and drives them from TWO threads with an
explicit event order. A sequential test in one session cannot reach these
windows: it can only show what happens when the interleaving does NOT occur.

The shape used throughout:

    A: BEGIN, take its decision (which locks the row)
    B: BEGIN, attempt the same thing  -> blocks on A's lock
    A: COMMIT
    B: proceeds, and must now SEE what A did

**Interleaving is proved, not assumed.** A barrier and a sleep order the
START; they say nothing about whether the second transaction ever reached the
contended point. So A holds its lock until `wait_for_blocked_backend` observes,
in `pg_stat_activity`, a backend on this database actually waiting on a lock
— and fails the test if that never happens within the deadline. The database
is the witness.

**Every worker's outcome is asserted.** `_run_pair` captures exceptions and
returns them as values, so a test that ignores a return value can pass while
an operation failed for an unrelated reason. Each test below therefore states,
for BOTH workers, either that they succeeded or exactly which domain refusal
they raised, and `assert_outcome` fails on any other exception — including one
injected to check that the assertions bite.
"""
from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from turab.db.session import audited_transaction
from turab.services import freshness, requests as request_service
from turab.services.concurrency import StaleVersion, check as version_check
from turab.services.requests import UpdateChannel

#: How long a worker holds its lock while waiting for the other to block, and
#: how long `wait_for_blocked_backend` waits for that to be observable.
LOCK_WAIT_DEADLINE = 10.0


class UnexpectedWorkerError(AssertionError):
    """A worker raised something no test expected. Never swallowed."""


def wait_for_blocked_backend(engine, deadline=LOCK_WAIT_DEADLINE) -> bool:
    """Wait until PostgreSQL reports a backend waiting on a lock.

    This is the interleaving evidence. `pg_stat_activity.wait_event_type =
    'Lock'` means a backend is blocked acquiring one — i.e. the second
    transaction has genuinely reached the contended point, rather than merely
    having been started.

    Uses its own short-lived connection so it never holds a lock itself.
    Returns False on timeout, and every caller treats that as a failure.
    """
    import time

    deadline_at = time.monotonic() + deadline
    while time.monotonic() < deadline_at:
        with Session(bind=engine, future=True) as s:
            blocked = s.execute(
                text(
                    """SELECT count(*) FROM pg_stat_activity
                        WHERE datname = current_database()
                          AND pid <> pg_backend_pid()
                          AND wait_event_type = 'Lock'"""
                )
            ).scalar_one()
        if blocked:
            return True
        time.sleep(0.02)
    return False


def assert_outcome(outcome, *, expect=None, raises=None, label=""):
    """State what a worker must have done, and fail on anything else.

    `expect` — it must have succeeded, returning this value (or any, if None).
    `raises` — it must have raised this exception type, by name.
    """
    kind, payload = outcome
    if raises is not None:
        assert kind == "raised", f"{label}: expected {raises}, got success {payload!r}"
        assert payload.startswith(raises), f"{label}: expected {raises}, got {payload}"
        return payload
    if kind == "raised":
        raise UnexpectedWorkerError(f"{label}: unexpected exception {payload}")
    if expect is not None:
        assert payload == expect, f"{label}: expected {expect!r}, got {payload!r}"
    return payload


@pytest.fixture
def two_engines(database_url):
    """Two independent engines — two real backend connections."""
    a = create_engine(database_url, future=True, poolclass=None)
    b = create_engine(database_url, future=True, poolclass=None)
    yield a, b
    a.dispose()
    b.dispose()


@pytest.fixture
def committed_request(engine, ids):
    """A committed ACTIVE request the concurrent tests can contend over.

    Committed, not the rolled-back `session` fixture: another connection
    cannot see an uncommitted row. Left behind afterwards —
    `prevent_core_delete()` forbids hard-deleting a core record.
    """
    with Session(bind=engine, future=True) as s:
        row = request_service.create_request(
            s, party_id=ids.AMINA, transaction_intent="BUY",
            intent="ACTIVE_SEARCH", management_mode="SELF_MANAGED",
            claim_status="CLAIMED", created_by_account_id=ids.ACC_AMINA,
            budget_target_dzd=10_000_000, budget_max_dzd=20_000_000,
        )
        rid = row["request_id"]
        for target in ("CONTACTED", "QUALIFIED", "ACTIVE"):
            request_service.transition(
                s, request_id=rid, target_status=target,
                recorded_by_account_id=ids.ACC_OPERATOR,
            )
        request_service.reconfirm(s, request_id=rid,
                                  recorded_by_account_id=ids.ACC_OPERATOR)
        s.commit()
        version = request_service.read_request(s, rid)["version"]
    return rid, version


def _run_ordered(holder, contender, *, holder_waits_for_contender=False):
    """Run two workers with a DETERMINISTIC order, and return both outcomes.

    A plain barrier only starts them together; which one acquires the
    contended lock first is then a race, and the first version of these tests
    assumed an answer it had not established. (The strict assertions added
    here are what exposed that — the harness was wrong, not the locks.)

    The handshake instead:

      1. `holder(locked)` takes its lock and calls `locked()`;
      2. the contender does not begin until that signal arrives;
      3. the holder waits for `wait_for_blocked_backend` to observe the
         contender actually blocked, then finishes and commits.

    `holder_waits_for_contender` is for the staleness pass, which uses
    `FOR UPDATE SKIP LOCKED` and therefore never blocks — skipping is the
    behaviour under test. Lock-waiting is the wrong evidence there, so the
    holder instead waits until the contender has FINISHED before committing:
    that proves the pass ran entirely inside the holder's open transaction,
    which is the interleaving the test needs.

    Outcomes are ("ok", value) or ("raised", "TypeName: message"); nothing is
    swallowed — `assert_outcome` is how a test states what it expected.
    """
    out: dict[str, object] = {}
    holds_lock = threading.Event()
    contender_done = threading.Event()

    def signal_and_maybe_wait():
        holds_lock.set()
        if holder_waits_for_contender:
            assert contender_done.wait(timeout=60), (
                "the contender never finished inside the holder's transaction"
            )

    def run_holder():
        try:
            out["holder"] = ("ok", holder(signal_and_maybe_wait))
        except Exception as exc:
            out["holder"] = ("raised", f"{type(exc).__name__}: {exc}")
        finally:
            holds_lock.set()  # never leave the contender waiting on a failure

    def run_contender():
        assert holds_lock.wait(timeout=30), "the holder never took its lock"
        try:
            out["contender"] = ("ok", contender())
        except Exception as exc:
            out["contender"] = ("raised", f"{type(exc).__name__}: {exc}")
        finally:
            contender_done.set()

    threads = [threading.Thread(target=run_holder),
               threading.Thread(target=run_contender)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=90)
    assert set(out) == {"holder", "contender"}, f"a thread did not finish: {out}"
    return out["holder"], out["contender"]


def _state(engine, rid) -> dict:
    with Session(bind=engine, future=True) as s:
        return dict(s.execute(
            text("""SELECT status::text AS status, version, budget_max_dzd,
                           budget_target_dzd, last_confirmed_at
                      FROM turab.requests WHERE request_id = :r"""),
            {"r": rid},
        ).mappings().one())


def _provenance_count(engine, rid, attribute) -> int:
    with Session(bind=engine, future=True) as s:
        return s.execute(
            text("""SELECT count(*) FROM turab.claims
                     WHERE request_id = :r AND attribute_code = :a"""),
            {"r": rid, "a": attribute},
        ).scalar_one()


# --- R-S2-01: the version guard ------------------------------------------

def test_two_patches_holding_the_same_version_yield_one_success_and_one_409(
    two_engines, engine, ids, committed_request
):
    """The race the original implementation lost.

    Both transactions hold version N. Without a lock both read N, both pass
    the check, and both write — the second silently overwriting a change its
    caller never saw. With `FOR UPDATE` the second blocks, then sees N+1 and
    is refused.
    """
    rid, version = committed_request
    engine_a, engine_b = two_engines

    def holder(locked):
        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                version_check(s, "requests", rid, version)
                locked()  # the contender may now start
                # Hold until the OTHER transaction is observably blocked.
                assert wait_for_blocked_backend(engine), (
                    "no backend ever blocked: the two transactions did not "
                    "contend, so this test proves nothing"
                )
                request_service.patch_request(
                    s, request_id=rid, changes={"budget_max_dzd": 31_000_000},
                    recorded_by_account_id=ids.ACC_OPERATOR,
                    channel=UpdateChannel.STAFF_RECORDED,
                )
        return 31_000_000

    def contender():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, ids.ACC_ADMIN):
                version_check(s, "requests", rid, version)
                request_service.patch_request(
                    s, request_id=rid, changes={"budget_max_dzd": 32_000_000},
                    recorded_by_account_id=ids.ACC_ADMIN,
                    channel=UpdateChannel.STAFF_RECORDED,
                )
        return 32_000_000

    first, second = _run_ordered(holder, contender)
    assert_outcome(first, expect=31_000_000, label="holder")
    assert_outcome(second, raises="StaleVersion", label="contender")

    after = _state(engine, rid)
    assert after["budget_max_dzd"] == 31_000_000
    assert after["version"] == version + 1, "exactly one write landed"
    assert _provenance_count(engine, rid, "budget_max_dzd") == 1, (
        "the refused attempt must record no provenance"
    )


def test_the_refused_patch_leaves_the_value_it_tried_to_write_absent(
    two_engines, engine, ids, committed_request
):
    """The loser's value must be nowhere: not in the row, not in the trail."""
    rid, version = committed_request
    engine_a, engine_b = two_engines
    WINNER, LOSER = 41_000_000, 99_000_001

    def holder(locked):
        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                version_check(s, "requests", rid, version)
                locked()
                assert wait_for_blocked_backend(engine), "no contention observed"
                request_service.patch_request(
                    s, request_id=rid, changes={"budget_max_dzd": WINNER},
                    recorded_by_account_id=ids.ACC_OPERATOR,
                    channel=UpdateChannel.STAFF_RECORDED,
                )
        return WINNER

    def contender():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, ids.ACC_ADMIN):
                version_check(s, "requests", rid, version)
                request_service.patch_request(
                    s, request_id=rid, changes={"budget_max_dzd": LOSER},
                    recorded_by_account_id=ids.ACC_ADMIN,
                    channel=UpdateChannel.STAFF_RECORDED,
                )
        return LOSER

    first, second = _run_ordered(holder, contender)
    assert_outcome(first, expect=WINNER, label="holder")
    assert_outcome(second, raises="StaleVersion", label="contender")

    assert _state(engine, rid)["budget_max_dzd"] == WINNER
    with Session(bind=engine, future=True) as s:
        values = s.execute(
            text("""SELECT claimed_value FROM turab.claims
                     WHERE request_id = :r AND attribute_code = 'budget_max_dzd'"""),
            {"r": rid},
        ).scalars().all()
    assert LOSER not in values


def test_an_unexpected_worker_error_fails_the_assertions(engine, ids,
                                                          committed_request):
    """The harness must bite.

    An injected error in a worker has to fail the test rather than be
    returned as a value nobody inspects — which is exactly the weakness the
    follow-up review identified in the first version of these tests.

    `explode` MUST take the `locked` callback and call it. An earlier version
    declared it as `explode()`, so `_run_ordered` raised `TypeError` when it
    passed the callback, and the worker never reached the `RuntimeError` the
    test names: the assertions still bit, but on the wrong exception, and the
    contender was released only by the `finally` in `run_holder` rather than
    by the handshake (acceptance review E-02). The recorded outcome is
    therefore checked to carry the INTENDED error before it is checked to be
    refused, so the test cannot silently drift back to measuring itself.
    """
    def explode(locked):
        locked()
        raise RuntimeError("injected")

    def fine():
        return "ok"

    first, second = _run_ordered(explode, fine)
    assert first == ("raised", "RuntimeError: injected"), first
    with pytest.raises(UnexpectedWorkerError):
        assert_outcome(first, expect="anything", label="injected")
    assert_outcome(second, expect="ok", label="control")

    # and a WRONG expected exception type is caught too
    with pytest.raises(AssertionError):
        assert_outcome(first, raises="StaleVersion", label="injected")


# --- R-S2-02: state decisions --------------------------------------------

def test_reconfirm_racing_a_close_does_not_reopen_the_closed_request(
    two_engines, engine, ids, committed_request
):
    """`reconfirm` reads NEEDS_CONFIRMATION, another transaction closes the
    request, and the first must NOT write ACTIVE anyway."""
    rid, _ = committed_request
    engine_a, engine_b = two_engines
    with Session(bind=engine, future=True) as s:
        request_service.transition(
            s, request_id=rid, target_status="NEEDS_CONFIRMATION",
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
        s.commit()

    def closer(locked):
        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                request_service.transition(
                    s, request_id=rid, target_status="CLOSED",
                    reason_code="REQUEST_WITHDRAWN",
                    recorded_by_account_id=ids.ACC_OPERATOR,
                )
                locked()
                assert wait_for_blocked_backend(engine), "no contention observed"
        return "CLOSED"

    def reconfirmer():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, ids.ACC_ADMIN):
                request_service.reconfirm(
                    s, request_id=rid, recorded_by_account_id=ids.ACC_ADMIN,
                )
        return "RECONFIRMED"

    first, second = _run_ordered(closer, reconfirmer)
    # BOTH must succeed: closing wins the row, and reconfirming is a
    # legitimate act that records a confirmation — it simply must not change
    # the status it no longer owns.
    assert_outcome(first, expect="CLOSED", label="closer")
    assert_outcome(second, expect="RECONFIRMED", label="reconfirmer")

    after = _state(engine, rid)
    assert after["status"] == "CLOSED", (
        "a CLOSED request must not be reopened by a concurrent reconfirmation"
    )
    assert after["last_confirmed_at"] is not None


def test_two_transitions_from_the_same_state_do_not_both_apply(
    two_engines, engine, ids, committed_request
):
    """Both read ACTIVE and pick a different target. One wins outright, and
    the loser is refused by the STATE MACHINE — named exactly, not "some
    exception"."""
    rid, _ = committed_request
    engine_a, engine_b = two_engines

    def pauser(locked):
        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                request_service.transition(
                    s, request_id=rid, target_status="PAUSED",
                    recorded_by_account_id=ids.ACC_OPERATOR,
                )
                locked()
                assert wait_for_blocked_backend(engine), "no contention observed"
        return "PAUSED"

    def closer():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, ids.ACC_ADMIN):
                request_service.transition(
                    s, request_id=rid, target_status="CLOSED",
                    reason_code="REQUEST_WITHDRAWN",
                    recorded_by_account_id=ids.ACC_ADMIN,
                )
        return "CLOSED"

    first, second = _run_ordered(pauser, closer)
    assert_outcome(first, expect="PAUSED", label="pauser")
    # From PAUSED, CLOSED is not a defined edge. The second transaction, which
    # now sees PAUSED rather than the ACTIVE it started from, must be refused
    # with that specific domain error.
    assert_outcome(second, raises="UndefinedTransition", label="closer")
    assert _state(engine, rid)["status"] == "PAUSED"


# --- R-S2-02: the staleness pass -----------------------------------------

def test_the_staleness_pass_does_not_mark_a_concurrently_reconfirmed_request(
    two_engines, engine, ids, committed_request
):
    """A row another transaction is holding is not marked by the pass.

    What this proves, exactly: `FOR UPDATE SKIP LOCKED` causes the pass to
    SKIP a row that is concurrently held, so a request reconfirmed inside an
    open transaction is left alone.

    What it does NOT prove: the repeated predicates in the outer `UPDATE`.
    Those guard a window inside a single statement, which cannot be opened
    from another connection, so they are defence in depth — the statement
    stays correct on its own terms — rather than something these tests
    exercise. Reverting them alone does not fail this test, and saying
    otherwise would be claiming evidence that does not exist.
    """
    rid, _ = committed_request
    engine_a, engine_b = two_engines
    _age(engine, rid, extra_days=5)

    def reconfirmer(locked):
        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                request_service.reconfirm(
                    s, request_id=rid, recorded_by_account_id=ids.ACC_OPERATOR,
                )
                # The pass SKIPS a locked row rather than blocking, so the
                # evidence is ordering, not lock-waiting: this returns only
                # once the pass has finished, inside this transaction.
                locked()
        return "RECONFIRMED"

    def pass_runner():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, None, require_actor=False):
                return [str(x) for x in
                        request_service.mark_stale_as_needing_confirmation(s)]

    first, second = _run_ordered(reconfirmer, pass_runner,
                                 holder_waits_for_contender=True)
    assert_outcome(first, expect="RECONFIRMED", label="reconfirmer")
    moved = assert_outcome(second, label="staleness pass")
    assert str(rid) not in moved, (
        "the pass must not mark a request reconfirmed under it"
    )
    assert _state(engine, rid)["status"] == "ACTIVE"


def test_the_staleness_pass_does_not_reopen_a_concurrently_closed_request(
    two_engines, engine, ids, committed_request
):
    """As above: the SKIP LOCKED behaviour, on a row closed under the pass."""
    rid, _ = committed_request
    engine_a, engine_b = two_engines
    _age(engine, rid, extra_days=5)

    def closer(locked):
        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                request_service.transition(
                    s, request_id=rid, target_status="CLOSED",
                    reason_code="REQUEST_FULFILLED",
                    recorded_by_account_id=ids.ACC_OPERATOR,
                )
                locked()
        return "CLOSED"

    def pass_runner():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, None, require_actor=False):
                return [str(x) for x in
                        request_service.mark_stale_as_needing_confirmation(s)]

    first, second = _run_ordered(closer, pass_runner,
                                 holder_waits_for_contender=True)
    assert_outcome(first, expect="CLOSED", label="closer")
    moved = assert_outcome(second, label="staleness pass")
    assert str(rid) not in moved
    assert _state(engine, rid)["status"] == "CLOSED", (
        "the pass must not move a request closed under it"
    )


# --- follow-up R-S2-03: concurrent criteria on the same slot -------------

def test_two_concurrent_adds_of_the_same_slot_yield_one_success_and_one_409(
    two_engines, engine, ids, committed_request
):
    """The unprotected pre-check: both could read "the slot is free".

    The parent request is now locked before the slot is inspected, so the
    second command blocks, then sees the slot taken and is refused with the
    typed conflict — not a constraint violation surfacing as a 500.
    """
    rid, _ = committed_request
    engine_a, engine_b = two_engines

    def holder(locked):
        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                row = request_service.add_criterion(
                    s, request_id=rid, criterion_code="ROOMS_MIN",
                    importance="REQUIRED", operator="GTE", value=3,
                    sort_order=100, recorded_by_account_id=ids.ACC_OPERATOR,
                )
                locked()
                assert wait_for_blocked_backend(engine), "no contention observed"
        return row["value"]

    def contender():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, ids.ACC_ADMIN):
                row = request_service.add_criterion(
                    s, request_id=rid, criterion_code="ROOMS_MIN",
                    importance="REQUIRED", operator="GTE", value=4,
                    sort_order=100, recorded_by_account_id=ids.ACC_ADMIN,
                )
        return row["value"]

    first, second = _run_ordered(holder, contender)
    assert_outcome(first, expect=3, label="first add")
    assert_outcome(second, raises="DuplicateCriterionSlot", label="second add")

    with Session(bind=engine, future=True) as s:
        rows = s.execute(
            text("""SELECT value, sort_order FROM turab.request_criteria
                     WHERE request_id = :r AND criterion_code = 'ROOMS_MIN'"""),
            {"r": rid},
        ).mappings().all()
    assert len(rows) == 1, f"exactly one criterion may exist in the slot: {rows}"
    assert rows[0]["value"] == 3
    assert _provenance_count(engine, rid, "criterion.ROOMS_MIN") == 1, (
        "the refused add must record no provenance"
    )


def test_a_concurrent_move_onto_a_slot_being_taken_is_refused(
    two_engines, engine, ids, committed_request
):
    """The CHANGE branch under contention: a move onto a slot another
    transaction is filling must be refused, not reach the constraint."""
    rid, _ = committed_request
    engine_a, engine_b = two_engines
    with Session(bind=engine, future=True) as s:
        mover = request_service.add_criterion(
            s, request_id=rid, criterion_code="ROOMS_MIN", importance="REQUIRED",
            operator="GTE", value=9, sort_order=200,
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
        s.commit()
        mover_id = mover["request_criterion_id"]

    def filler(locked):
        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                request_service.add_criterion(
                    s, request_id=rid, criterion_code="ROOMS_MIN",
                    importance="REQUIRED", operator="GTE", value=3,
                    sort_order=100, recorded_by_account_id=ids.ACC_OPERATOR,
                )
                locked()
                assert wait_for_blocked_backend(engine), "no contention observed"
        return "FILLED"

    def move():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, ids.ACC_ADMIN):
                request_service.add_criterion(
                    s, request_id=rid, criterion_code="ROOMS_MIN",
                    importance="REQUIRED", operator="GTE", value=9,
                    sort_order=100, request_criterion_id=mover_id,
                    recorded_by_account_id=ids.ACC_ADMIN,
                )
        return "MOVED"

    first, second = _run_ordered(filler, move)
    assert_outcome(first, expect="FILLED", label="filler")
    assert_outcome(second, raises="DuplicateCriterionSlot", label="mover")

    with Session(bind=engine, future=True) as s:
        slots = sorted(s.execute(
            text("""SELECT sort_order FROM turab.request_criteria
                     WHERE request_id = :r AND criterion_code = 'ROOMS_MIN'"""),
            {"r": rid},
        ).scalars().all())
    assert slots == [100, 200], (
        "the refused move must leave the criterion where it was"
    )


def _age(engine, rid, *, extra_days: int) -> None:
    with Session(bind=engine, future=True) as s:
        days, _ = freshness.request_threshold_days(s)
        s.execute(
            text("UPDATE turab.requests SET last_confirmed_at = :t "
                 "WHERE request_id = :r"),
            {"t": datetime.now(UTC) - timedelta(days=days + extra_days), "r": rid},
        )
        s.commit()
