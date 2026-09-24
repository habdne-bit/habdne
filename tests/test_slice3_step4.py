"""Slice 3, step 4 — availability reconfirmation, the restricted staleness
pass, and offer reconfirmation with `offer_terms` freshness.

Ref: `docs/gate/SLICE_3_PLAN.md` §3.3 (G3-3, ratified), §3.4 (ratified),
§6.2 (the test names used here); the effective contract's
`postPropertiesPropertyIdReconfirm` and `postOffersOfferIdReconfirm`.
"""
from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.db.session import audited_transaction
from turab.services import freshness
from turab.services import properties as property_service
from turab.services.provenance import UpdateChannel

ALL_VALUES = property_service.AVAILABILITY_VALUES
CONVERTIBLE = property_service.STALE_CONVERTIBLE


@pytest.fixture
def client(engine):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(RecordingAuditSink()))
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture(autouse=True)
def clean(engine):
    yield
    with Session(bind=engine, future=True) as s:
        s.execute(text("DELETE FROM turab.idempotency_records"))
        s.commit()


def as_(account):
    return {"Authorization": f"Bearer {account}"}


def key():
    return {"Idempotency-Key": f"s3r-{uuid.uuid4()}"}


def _db(engine, sql, **params):
    with Session(bind=engine, future=True) as s:
        return s.execute(text(sql), params).mappings().all()


def _property(client, ids, who=None) -> str:
    r = client.post("/properties", headers={**as_(who or ids.ACC_AMINA), **key()},
                    json={"property_type": "LAND", "supply_mode": "PUBLIC",
                          "management_mode": "SELF_MANAGED",
                          "claim_status": "CLAIMED"})
    assert r.status_code == 201, r.text
    return r.json()["property_id"]


def _reconfirm(client, ids, pid, who=None, headers=None, **body):
    return client.post(f"/properties/{pid}/reconfirm",
                       headers=headers or {**as_(who or ids.ACC_AMINA), **key()},
                       json=body)


def _availability(engine, pid):
    return _db(engine, """SELECT current_availability::text AS a,
                                 availability_last_confirmed_at AS at, version
                            FROM turab.properties WHERE property_id = :p""", p=pid)[0]


def _ago(days: float) -> str:
    return (datetime.now(UTC) - timedelta(days=days)).isoformat()


# --- §3.3 availability reconfirmation ----------------------------------------

@pytest.mark.parametrize("start,target",
                         [(a, b) for a in ALL_VALUES for b in ALL_VALUES if a != b])
def test_reconfirm_moves_between_any_two_availability_values(client, ids, engine,
                                                             start, target):
    """Rule 1: a fact, not an edge. All 42 ordered pairs, no table."""
    pid = _property(client, ids)
    assert _reconfirm(client, ids, pid, availability=start).status_code == 200
    r = _reconfirm(client, ids, pid, availability=target)
    assert r.status_code == 200, r.text
    assert r.json()["current_availability"] == target
    assert _availability(engine, pid)["a"] == target


@pytest.mark.parametrize("body", [{}, {"availability": None},
                                  {"confirmed_at": "2026-01-01T00:00:00Z"}])
def test_reconfirm_requires_an_explicit_availability(client, ids, engine, body):
    """Rule 2: the value is stated, never restored from memory."""
    pid = _property(client, ids)
    before = _availability(engine, pid)
    r = _reconfirm(client, ids, pid, **body)
    assert r.status_code == 422, r.text
    assert _availability(engine, pid) == before


def test_patch_cannot_change_availability_and_reconfirm_is_the_path(client, ids, engine):
    pid = _property(client, ids)
    r = client.patch(f"/properties/{pid}", json={"current_availability": "AVAILABLE"},
                     headers={**as_(ids.ACC_AMINA), "If-Match-Version": "1"})
    assert r.status_code == 422, r.text
    assert _availability(engine, pid)["a"] == "UNKNOWN"


def test_reconfirmation_stamps_time_actor_channel_and_provenance(client, ids, engine):
    """Rule 3."""
    pid = _property(client, ids)
    r = _reconfirm(client, ids, pid, availability="AVAILABLE", notes="owner called")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["availability_last_confirmed_at"] is not None
    rows = _db(engine, """SELECT c.attribute_code, c.claimed_value,
                                 c.recorded_by_account_id, c.extracted_by,
                                 o.payload, o.raw_text
                            FROM turab.claims c JOIN turab.observations o
                                 USING (observation_id)
                           WHERE c.property_id = :p
                             AND c.attribute_code = 'current_availability'""", p=pid)
    assert len(rows) >= 1
    last = rows[-1]
    assert last["claimed_value"] == "AVAILABLE"
    assert last["recorded_by_account_id"] == ids.ACC_AMINA
    assert last["extracted_by"] == "SELF_SERVICE"
    assert last["payload"]["before"]["current_availability"] == "UNKNOWN"
    assert last["raw_text"] == "owner called"


def test_staff_reconfirmation_is_recorded_as_staff(client, ids, engine):
    pid = _property(client, ids)
    assert _reconfirm(client, ids, pid, who=ids.ACC_OPERATOR,
                      availability="UNAVAILABLE").status_code == 200
    rows = _db(engine, """SELECT extracted_by, asserted_by_party_id FROM turab.claims
                           WHERE property_id = :p
                             AND attribute_code = 'current_availability'""", p=pid)
    assert rows[-1]["extracted_by"] == "STAFF_RECORDED"
    assert rows[-1]["asserted_by_party_id"] is None


def test_a_historical_confirmation_is_stored_as_stated(client, ids, engine):
    pid = _property(client, ids)
    when = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
    r = _reconfirm(client, ids, pid, availability="AVAILABLE",
                   confirmed_at=when.isoformat())
    assert r.status_code == 200, r.text
    assert _availability(engine, pid)["at"] == when


@pytest.mark.parametrize("confirmed_at,label", [
    ("2026-01-01T00:00:00", "no offset"),
    ((datetime.now(UTC) + timedelta(days=2)).isoformat(), "in the future"),
])
def test_a_bad_confirmation_time_is_refused_and_writes_nothing(client, ids, engine,
                                                               confirmed_at, label):
    pid = _property(client, ids)
    before = _availability(engine, pid)
    k = {**as_(ids.ACC_AMINA), **key()}
    r = _reconfirm(client, ids, pid, headers=k, availability="AVAILABLE",
                   confirmed_at=confirmed_at)
    assert r.status_code == 422, f"{label}: {r.text}"
    assert _availability(engine, pid) == before
    ok = _reconfirm(client, ids, pid, headers=k, availability="AVAILABLE")
    assert ok.status_code == 200, f"{label}: the refused call consumed its key"


def test_a_customer_cannot_reconfirm_a_property_that_is_not_theirs(client, ids):
    pid = _property(client, ids, who=ids.ACC_OPERATOR)
    r = _reconfirm(client, ids, pid, availability="AVAILABLE")
    assert r.status_code == 404, r.text


def test_reconfirming_an_alias_is_refused(client, ids, engine):
    """Decision F-2 applies to this write too."""
    canonical = _property(client, ids)
    alias = _property(client, ids, who=ids.ACC_OPERATOR)
    with Session(bind=engine, future=True) as s:
        cand = s.execute(text(
            """INSERT INTO turab.property_identity_candidates
                      (property_a_id, property_b_id, review_status)
               VALUES (:a, :b, 'PENDING_REVIEW') RETURNING identity_candidate_id"""),
            {"a": alias, "b": canonical}).scalar_one()
        s.execute(text(
            """INSERT INTO turab.property_identity_aliases
                      (alias_property_id, canonical_property_id,
                       source_identity_candidate_id, resolved_by_account_id)
               VALUES (:a, :c, :cand, :acct)"""),
            {"a": alias, "c": canonical, "cand": cand, "acct": ids.ACC_OPERATOR})
        s.commit()
    before = _availability(engine, alias)
    r = _reconfirm(client, ids, alias, availability="AVAILABLE")
    assert r.status_code == 409, r.text
    assert _availability(engine, alias) == before


# --- §3.3 rule 4: the staleness pass ------------------------------------------

def _run_pass(engine):
    with Session(bind=engine, future=True) as s:
        with audited_transaction(s, None, {"operation": "freshness-pass:property"},
                                 require_actor=False):
            return property_service.mark_stale_availability(s)


def _stale_property(client, ids, value, days_ago=40) -> str:
    """A property whose `value` was confirmed `days_ago` days ago, through the
    API's own historical confirmation."""
    pid = _property(client, ids)
    r = _reconfirm(client, ids, pid, availability=value, confirmed_at=_ago(days_ago))
    assert r.status_code == 200, r.text
    return pid


@pytest.mark.parametrize("value", CONVERTIBLE)
def test_the_sweep_converts_each_of_the_four_named_values(client, ids, engine, value):
    pid = _stale_property(client, ids, value)
    before = _availability(engine, pid)
    assert uuid.UUID(pid) in _run_pass(engine)
    after = _availability(engine, pid)
    assert after["a"] == "NEEDS_CONFIRMATION"
    assert after["at"] == before["at"], "the pass is not a confirmation"


def test_the_sweep_leaves_unknown_untouched(client, ids, engine):
    pid = _stale_property(client, ids, "UNKNOWN")
    assert uuid.UUID(pid) not in _run_pass(engine)
    assert _availability(engine, pid)["a"] == "UNKNOWN"


def test_the_sweep_leaves_needs_confirmation_untouched(client, ids, engine):
    pid = _stale_property(client, ids, "NEEDS_CONFIRMATION")
    version = _availability(engine, pid)["version"]
    assert uuid.UUID(pid) not in _run_pass(engine)
    after = _availability(engine, pid)
    assert after["a"] == "NEEDS_CONFIRMATION"
    assert after["version"] == version, "an untouched row is not rewritten"


def test_the_sweep_leaves_unavailable_untouched(client, ids, engine):
    pid = _stale_property(client, ids, "UNAVAILABLE")
    assert uuid.UUID(pid) not in _run_pass(engine)
    assert _availability(engine, pid)["a"] == "UNAVAILABLE"


def test_the_sweep_reads_the_threshold_from_the_active_policy(client, ids, engine):
    """30 days in the seeded policy: 29 is fresh, 31 is stale."""
    with Session(bind=engine, future=True) as s:
        days, _ = freshness.property_threshold_days(s)
    fresh = _stale_property(client, ids, "AVAILABLE", days_ago=days - 1)
    stale = _stale_property(client, ids, "AVAILABLE", days_ago=days + 1)
    moved = _run_pass(engine)
    assert uuid.UUID(stale) in moved and uuid.UUID(fresh) not in moved


def test_a_never_confirmed_availability_is_not_stale(client, ids, engine):
    """NULL confirmation: not out of date — never put in date. Same rule as
    the REQUEST pass."""
    pid = _property(client, ids)
    with Session(bind=engine, future=True) as s:
        s.execute(text("""UPDATE turab.properties SET current_availability = 'AVAILABLE'
                           WHERE property_id = :p"""), {"p": pid})
        s.commit()
    assert _availability(engine, pid)["at"] is None
    assert uuid.UUID(pid) not in _run_pass(engine)
    assert _availability(engine, pid)["a"] == "AVAILABLE"


def test_the_sweep_is_audited_with_its_operation(client, ids, engine):
    pid = _stale_property(client, ids, "AVAILABLE")
    _run_pass(engine)
    rows = _db(engine, """SELECT context, new_row->>'current_availability' AS a
                            FROM turab.audit_log
                           WHERE entity_table = 'properties' AND entity_id = :p
                           ORDER BY audit_id DESC LIMIT 1""", p=pid)
    assert rows[0]["a"] == "NEEDS_CONFIRMATION"
    assert rows[0]["context"]["operation"] == "freshness-pass:property"


# --- the re-assertion at write time, under real contention -------------------

@pytest.fixture
def two_engines(database_url):
    a = create_engine(database_url, future=True)
    b = create_engine(database_url, future=True)
    yield a, b
    a.dispose()
    b.dispose()


def _pass_inside_a_locked_change(engine_a, engine_b, ids, pid, value):
    """Holder: reconfirm `pid` to `value` (row locked, uncommitted). The pass
    runs ENTIRELY inside the holder's open transaction — the holder commits
    only after the pass has finished — which is the interleaving under test.
    `FOR UPDATE SKIP LOCKED` never blocks, so blocked-backend evidence is the
    wrong witness here; completion inside the window is the right one."""
    out: dict[str, object] = {}
    locked, passed = threading.Event(), threading.Event()

    def holder():
        try:
            with Session(bind=engine_a, future=True) as s:
                with audited_transaction(s, ids.ACC_OPERATOR):
                    property_service.reconfirm_availability(
                        s, property_id=uuid.UUID(pid), availability=value,
                        recorded_by_account_id=ids.ACC_OPERATOR,
                        channel=UpdateChannel.STAFF_RECORDED)
                    locked.set()
                    assert passed.wait(30), "the pass never ran inside the window"
            out["holder"] = "ok"
        except Exception as exc:
            out["holder"] = f"raised {type(exc).__name__}: {exc}"
        finally:
            locked.set()

    def sweeper():
        assert locked.wait(30)
        try:
            out["moved"] = _run_pass(engine_b)
        except Exception as exc:
            out["moved"] = f"raised {type(exc).__name__}: {exc}"
        finally:
            passed.set()

    threads = [threading.Thread(target=holder), threading.Thread(target=sweeper)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(90)
    assert not any(t.is_alive() for t in threads)
    return out


@pytest.mark.parametrize("value", ["AVAILABLE", "UNAVAILABLE"])
def test_the_sweep_does_not_overwrite_a_concurrent_reconfirmation(
    client, ids, engine, two_engines, value
):
    """The property is stale when sampled; a reconfirmation is in flight.
    Whatever the reconfirmation says — a fresh AVAILABLE, or an excluded
    UNAVAILABLE — it must stand after both commit."""
    pid = _stale_property(client, ids, "AVAILABLE")
    out = _pass_inside_a_locked_change(*two_engines, ids, pid, value)
    assert out["holder"] == "ok", out
    assert isinstance(out["moved"], list), out
    assert uuid.UUID(pid) not in out["moved"]
    assert _availability(engine, pid)["a"] == value


# --- §3.4 offer reconfirmation and offer_terms freshness ----------------------

def _offer(client, ids) -> dict:
    pid = _property(client, ids)
    r = client.post(f"/properties/{pid}/offers", headers={**as_(ids.ACC_AMINA), **key()},
                    json={"party_id": str(ids.AMINA), "transaction_type": "SALE",
                          "asking_price_dzd": 1})
    assert r.status_code == 201, r.text
    return r.json()


def _offer_reconfirm(client, ids, oid, headers=None, who=None, **body):
    return client.post(f"/offers/{oid}/reconfirm",
                       headers=headers or {**as_(who or ids.ACC_AMINA), **key()},
                       json=body)


def _offer_row(engine, oid):
    return _db(engine, """SELECT last_confirmed_at, commercial_terms_last_confirmed_at,
                                 status::text AS status, asking_price_dzd, version
                            FROM turab.property_offers WHERE offer_id = :o""", o=oid)[0]


def test_reconfirming_an_offer_updates_both_confirmation_columns(client, ids, engine):
    offer = _offer(client, ids)
    r = _offer_reconfirm(client, ids, offer["offer_id"])
    assert r.status_code == 200, r.text
    row = _offer_row(engine, offer["offer_id"])
    assert row["last_confirmed_at"] is not None
    assert row["last_confirmed_at"] == row["commercial_terms_last_confirmed_at"]
    got = r.json()
    assert got["last_confirmed_at"] == got["commercial_terms_last_confirmed_at"]


def test_a_stated_confirmation_time_is_written_to_both_columns(client, ids, engine):
    offer = _offer(client, ids)
    when = datetime(2026, 2, 3, 4, 5, 6, tzinfo=UTC)
    assert _offer_reconfirm(client, ids, offer["offer_id"],
                            confirmed_at=when.isoformat()).status_code == 200
    row = _offer_row(engine, offer["offer_id"])
    assert row["last_confirmed_at"] == row["commercial_terms_last_confirmed_at"] == when


def test_a_confirmation_without_a_timezone_is_refused_on_the_offer_endpoint(
    client, ids, engine
):
    """R-S2-05b, tested HERE rather than assumed to carry over (§3.4)."""
    offer = _offer(client, ids)
    before = _offer_row(engine, offer["offer_id"])
    k = {**as_(ids.ACC_AMINA), **key()}
    r = _offer_reconfirm(client, ids, offer["offer_id"], headers=k,
                         confirmed_at="2026-01-01T00:00:00")
    assert r.status_code == 422, r.text
    assert _offer_row(engine, offer["offer_id"]) == before
    assert _offer_reconfirm(client, ids, offer["offer_id"],
                            headers=k).status_code == 200, "key was consumed"


def test_a_future_offer_confirmation_is_refused(client, ids, engine):
    offer = _offer(client, ids)
    r = _offer_reconfirm(client, ids, offer["offer_id"],
                         confirmed_at=(datetime.now(UTC) + timedelta(days=1)).isoformat())
    assert r.status_code == 422, r.text


def test_reconfirming_changes_neither_terms_nor_state(client, ids, engine):
    offer = _offer(client, ids)
    before = _offer_row(engine, offer["offer_id"])
    assert _offer_reconfirm(client, ids, offer["offer_id"]).status_code == 200
    after = _offer_row(engine, offer["offer_id"])
    assert after["status"] == before["status"] == "DRAFT"
    assert after["asking_price_dzd"] == before["asking_price_dzd"]


def test_offer_reconfirmation_records_provenance(client, ids, engine):
    offer = _offer(client, ids)
    assert _offer_reconfirm(client, ids, offer["offer_id"],
                            notes="terms unchanged").status_code == 200
    codes = {r["attribute_code"] for r in _db(
        engine, "SELECT attribute_code FROM turab.claims WHERE offer_id = :o",
        o=offer["offer_id"])}
    assert {"last_confirmed_at", "commercial_terms_last_confirmed_at"} <= codes


def test_a_customer_cannot_reconfirm_an_offer_that_is_not_theirs(client, ids):
    r = _offer_reconfirm(client, ids, ids.OFFER_BROKER_SALE)
    assert r.status_code == 404, r.text


def _set_offer_clocks(engine, oid, *, last, commercial):
    """Diverge the two columns directly. The API writes them together (§3.4),
    so only another writer — an import — could produce this row; it is the
    row that shows WHICH clock the policy reads."""
    with Session(bind=engine, future=True) as s:
        s.execute(text("""UPDATE turab.property_offers
                             SET last_confirmed_at = :l,
                                 commercial_terms_last_confirmed_at = :c
                           WHERE offer_id = :o"""),
                  {"l": last, "c": commercial, "o": oid})
        s.commit()


def test_offer_staleness_is_measured_on_commercial_terms_last_confirmed_at(
    client, ids, engine
):
    offer = _offer(client, ids)
    now = datetime.now(UTC)
    with Session(bind=engine, future=True) as s:
        days, _ = freshness.offer_terms_threshold_days(s)
    _set_offer_clocks(engine, offer["offer_id"], last=now,
                      commercial=now - timedelta(days=days + 1))
    with Session(bind=engine, future=True) as s:
        assert freshness.evaluate_offer(s, offer["offer_id"]).state is \
            freshness.FreshnessState.STALE
    _set_offer_clocks(engine, offer["offer_id"], last=now - timedelta(days=days + 1),
                      commercial=now)
    with Session(bind=engine, future=True) as s:
        assert freshness.evaluate_offer(s, offer["offer_id"]).state is \
            freshness.FreshnessState.FRESH


def test_a_stale_offer_is_reported_stale_on_its_commercial_terms_clock(client, ids,
                                                                      engine):
    """STOP GATE C row "current vs historical": the `offer_terms` threshold
    (14 days in the seeded policy) decides, not the request/property one."""
    offer = _offer(client, ids)
    with Session(bind=engine, future=True) as s:
        days, _ = freshness.offer_terms_threshold_days(s)
        assert days != freshness.property_threshold_days(s)[0]
    assert _offer_reconfirm(client, ids, offer["offer_id"],
                            confirmed_at=_ago(days - 1)).status_code == 200
    with Session(bind=engine, future=True) as s:
        assert freshness.evaluate_offer(s, offer["offer_id"]).state is \
            freshness.FreshnessState.FRESH
    # One day past `offer_terms`, still well inside the 30-day property and
    # request windows: STALE here can only come from the offer policy.
    assert _offer_reconfirm(client, ids, offer["offer_id"],
                            confirmed_at=_ago(days + 1)).status_code == 200
    with Session(bind=engine, future=True) as s:
        got = freshness.evaluate_offer(s, offer["offer_id"])
    assert got.state is freshness.FreshnessState.STALE
    assert got.threshold_days == days


def test_a_new_offer_is_never_confirmed_not_stale(client, ids, engine):
    offer = _offer(client, ids)
    with Session(bind=engine, future=True) as s:
        assert freshness.evaluate_offer(s, offer["offer_id"]).state is \
            freshness.FreshnessState.NEVER_CONFIRMED


def test_a_policy_without_an_offer_terms_threshold_is_refused_not_defaulted(session):
    session.execute(text("""UPDATE turab.matching_policies
                               SET rules = rules #- '{freshness_threshold_days,offer_terms}'
                             WHERE active"""))
    with pytest.raises(freshness.NoActiveFreshnessPolicy, match="offer_terms"):
        freshness.offer_terms_threshold_days(session)
