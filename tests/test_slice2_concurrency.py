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

`barrier` orders the start; a short settle lets B reach the lock before A
commits, so the block is real rather than accidental. Each test also asserts
the LOSER changed nothing, which is the half that distinguishes "serialised"
from "both ran".
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

SETTLE = 0.35  # seconds for the second transaction to reach the lock


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


def _run_pair(first, second):
    """Start both, ordering them so `second` reaches its lock while `first`
    still holds one. Returns (outcome_first, outcome_second)."""
    import time

    out: dict[str, object] = {}
    barrier = threading.Barrier(2)

    def wrap(name, fn, delay):
        def run():
            barrier.wait(timeout=15)
            if delay:
                time.sleep(delay)
            try:
                out[name] = ("ok", fn())
            except Exception as exc:  # recorded, then asserted on
                out[name] = ("raised", f"{type(exc).__name__}: {exc}")
        return run

    threads = [
        threading.Thread(target=wrap("first", first, 0.0)),
        threading.Thread(target=wrap("second", second, SETTLE / 3)),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=40)
    assert set(out) == {"first", "second"}, f"a thread did not finish: {out}"
    return out["first"], out["second"]


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
    """The race the previous implementation lost.

    Both transactions hold version N. Without a lock both read N, both pass
    the check, and both write — the second silently overwriting a change its
    caller never saw. With `FOR UPDATE` in the guard the second blocks, then
    sees N+1 and is refused.
    """
    rid, version = committed_request
    engine_a, engine_b = two_engines

    def patch(eng, account, value):
        def run():
            import time

            with Session(bind=eng, future=True) as s:
                with audited_transaction(s, account):
                    version_check(s, "requests", rid, version)
                    time.sleep(SETTLE)  # hold the lock while the other arrives
                    request_service.patch_request(
                        s, request_id=rid, changes={"budget_max_dzd": value},
                        recorded_by_account_id=account,
                        channel=UpdateChannel.STAFF_RECORDED,
                    )
            return value
        return run

    first, second = _run_pair(
        patch(engine_a, ids.ACC_OPERATOR, 31_000_000),
        patch(engine_b, ids.ACC_ADMIN, 32_000_000),
    )
    outcomes = [first, second]
    succeeded = [o for o in outcomes if o[0] == "ok"]
    refused = [o for o in outcomes if o[0] == "raised"]

    assert len(succeeded) == 1, outcomes
    assert len(refused) == 1, outcomes
    assert "StaleVersion" in refused[0][1], refused[0][1]

    after = _state(engine, rid)
    assert after["budget_max_dzd"] == succeeded[0][1]
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
    LOSER_VALUE = 99_000_001

    def patch(eng, account, value, hold):
        def run():
            import time

            with Session(bind=eng, future=True) as s:
                with audited_transaction(s, account):
                    version_check(s, "requests", rid, version)
                    if hold:
                        time.sleep(SETTLE)
                    request_service.patch_request(
                        s, request_id=rid, changes={"budget_max_dzd": value},
                        recorded_by_account_id=account,
                        channel=UpdateChannel.STAFF_RECORDED,
                    )
            return value
        return run

    _run_pair(
        patch(engine_a, ids.ACC_OPERATOR, 41_000_000, True),
        patch(engine_b, ids.ACC_ADMIN, LOSER_VALUE, False),
    )
    assert _state(engine, rid)["budget_max_dzd"] != LOSER_VALUE
    with Session(bind=engine, future=True) as s:
        values = s.execute(
            text("""SELECT claimed_value FROM turab.claims
                     WHERE request_id = :r AND attribute_code = 'budget_max_dzd'"""),
            {"r": rid},
        ).scalars().all()
    assert LOSER_VALUE not in values


# --- R-S2-02: state decisions --------------------------------------------

def test_reconfirm_racing_a_close_does_not_reopen_the_closed_request(
    two_engines, engine, ids, committed_request
):
    """The window the review identified: `reconfirm` reads
    NEEDS_CONFIRMATION, another transaction closes the request, and the first
    writes ACTIVE anyway — reopening a CLOSED request under concurrency,
    which the sequential tests could not see."""
    rid, _ = committed_request
    engine_a, engine_b = two_engines
    with Session(bind=engine, future=True) as s:
        request_service.transition(
            s, request_id=rid, target_status="NEEDS_CONFIRMATION",
            recorded_by_account_id=ids.ACC_OPERATOR,
        )
        s.commit()

    def closer():
        import time

        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                request_service.transition(
                    s, request_id=rid, target_status="CLOSED",
                    reason_code="REQUEST_WITHDRAWN",
                    recorded_by_account_id=ids.ACC_OPERATOR,
                )
                time.sleep(SETTLE)
        return "CLOSED"

    def reconfirmer():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, ids.ACC_ADMIN):
                request_service.reconfirm(
                    s, request_id=rid, recorded_by_account_id=ids.ACC_ADMIN,
                )
        return "RECONFIRMED"

    _run_pair(closer, reconfirmer)

    assert _state(engine, rid)["status"] == "CLOSED", (
        "a CLOSED request must not be reopened by a concurrent reconfirmation"
    )


def test_two_transitions_from_the_same_state_do_not_both_apply(
    two_engines, engine, ids, committed_request
):
    """Both read ACTIVE and pick a different target. One must win outright."""
    rid, _ = committed_request
    engine_a, engine_b = two_engines

    def move(eng, account, target, reason, hold):
        def run():
            import time

            with Session(bind=eng, future=True) as s:
                with audited_transaction(s, account):
                    request_service.transition(
                        s, request_id=rid, target_status=target,
                        reason_code=reason, recorded_by_account_id=account,
                    )
                    if hold:
                        time.sleep(SETTLE)
            return target
        return run

    first, second = _run_pair(
        move(engine_a, ids.ACC_OPERATOR, "PAUSED", None, True),
        move(engine_b, ids.ACC_ADMIN, "CLOSED", "REQUEST_WITHDRAWN", False),
    )
    final = _state(engine, rid)["status"]
    assert final in ("PAUSED", "CLOSED")

    # The loser must have been refused, not silently ignored: from PAUSED,
    # CLOSED is not a defined edge, so the second transaction — which now
    # sees PAUSED rather than the ACTIVE it started from — is rejected.
    outcomes = [first, second]
    assert any(o[0] == "raised" for o in outcomes), outcomes


# --- R-S2-02: the staleness pass -----------------------------------------

def test_the_staleness_pass_does_not_mark_a_concurrently_reconfirmed_request(
    two_engines, engine, ids, committed_request
):
    """The pass selects candidates, then writes. Between the two, another
    transaction reconfirms — and the row it is about to mark stale is no
    longer stale."""
    rid, _ = committed_request
    engine_a, engine_b = two_engines
    days, _policy = freshness.request_threshold_days(
        Session(bind=engine, future=True)
    )
    with Session(bind=engine, future=True) as s:
        s.execute(
            text("UPDATE turab.requests SET last_confirmed_at = :t "
                 "WHERE request_id = :r"),
            {"t": datetime.now(UTC) - timedelta(days=days + 5), "r": rid},
        )
        s.commit()

    def reconfirmer():
        import time

        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                request_service.reconfirm(
                    s, request_id=rid, recorded_by_account_id=ids.ACC_OPERATOR,
                )
                time.sleep(SETTLE)
        return "RECONFIRMED"

    def pass_runner():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, None, require_actor=False):
                return [str(x) for x in
                        request_service.mark_stale_as_needing_confirmation(s)]

    _first, second = _run_pair(reconfirmer, pass_runner)

    after = _state(engine, rid)
    if second[0] == "ok":
        assert str(rid) not in second[1], (
            "the pass must not mark a request reconfirmed under it"
        )
    assert after["status"] == "ACTIVE", (
        "a request reconfirmed concurrently must not end up NEEDS_CONFIRMATION"
    )


def test_the_staleness_pass_does_not_reopen_a_concurrently_closed_request(
    two_engines, engine, ids, committed_request
):
    rid, _ = committed_request
    engine_a, engine_b = two_engines
    with Session(bind=engine, future=True) as s:
        days, _ = freshness.request_threshold_days(s)
        s.execute(
            text("UPDATE turab.requests SET last_confirmed_at = :t "
                 "WHERE request_id = :r"),
            {"t": datetime.now(UTC) - timedelta(days=days + 5), "r": rid},
        )
        s.commit()

    def closer():
        import time

        with Session(bind=engine_a, future=True) as s:
            with audited_transaction(s, ids.ACC_OPERATOR):
                request_service.transition(
                    s, request_id=rid, target_status="CLOSED",
                    reason_code="REQUEST_FULFILLED",
                    recorded_by_account_id=ids.ACC_OPERATOR,
                )
                time.sleep(SETTLE)
        return "CLOSED"

    def pass_runner():
        with Session(bind=engine_b, future=True) as s:
            with audited_transaction(s, None, require_actor=False):
                return [str(x) for x in
                        request_service.mark_stale_as_needing_confirmation(s)]

    _run_pair(closer, pass_runner)
    assert _state(engine, rid)["status"] == "CLOSED", (
        "the pass must not move a request closed under it"
    )
