"""STOP GATE B, as one operational scenario.

Ref: IMPLEMENTATION_SLICES_v0.2.md, Slice 2:

    A staff operator must be able to understand exactly what the buyer wants,
    what is hard vs preferred, and when that information was last confirmed.

The gate is about an operator's understanding, so it is tested the way an
operator would meet it: one continuous scenario, end to end, answered from
the API alone. The three questions are asserted explicitly at the end, each
against the single staff read an operator actually performs.

Scenario. Khadija rings the office about renting a flat. An operator records
an assisted request while she is on the phone. She later claims it — and
before she does, an unrelated account tries to claim it and is refused
without leaving a trace that would block her. Her budget changes. Four months
pass without contact and the request goes stale. The operator rings to check,
and reconfirms.

The counter-scenario is part of the gate, not an extra: an operator's
understanding of a record is worth nothing if the record could have been
captured by whoever asked first.
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.auth.audit import AccessAuditor, RecordingAuditSink
from turab.services import freshness


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


def operator(ids):
    return {"Authorization": f"Bearer {ids.ACC_OPERATOR}"}


def khadija(ids):
    return {"Authorization": f"Bearer {ids.ACC_KHADIJA}"}


def test_stop_gate_b_a_staff_operator_can_understand_the_request(client, ids, engine):
    # --- 1. the operator records what Khadija says, while she is on the phone
    created = client.post(
        "/requests",
        json={
            "party_id": str(ids.KHADIJA),
            "transaction_intent": "RENT",
            "intent": "ACTIVE_SEARCH",
            "management_mode": "ASSISTED",
            "claim_status": "UNCLAIMED",
            "payment": "BANK_FINANCING",
            "desired_property_type": "APARTMENT",
            "property_type_importance": "REQUIRED",
            "local_location_detail": "sgb-near the university",
            "budget_target_dzd": 45_000,
            "budget_max_dzd": 55_000,
            "budget_importance": "REQUIRED",
            "budget_flexibility": "LOW",
            "criteria": [
                {"criterion_code": "ROOMS_MIN", "importance": "REQUIRED",
                 "operator": "GTE", "value": 3},
                {"criterion_code": "BUILT_AREA_MIN", "importance": "PREFERRED",
                 "operator": "GTE", "value": 80, "unit": "m2"},
                {"criterion_code": "DOCUMENT_TYPE", "importance": "FLEXIBLE",
                 "operator": "EQ", "value": "ACTE_NOTARIE",
                 "blocking_if_unknown": False},
            ],
        },
        headers={**operator(ids), "Idempotency-Key": "sgb-create"},
    )
    assert created.status_code == 201, created.text
    rid = created.json()["request_id"]
    assert created.json()["management_mode"] == "ASSISTED"
    assert created.json()["claim_status"] == "UNCLAIMED"

    # --- 2a. an unrelated account tries first, and is refused with no trace
    total_before = _count(engine)
    intruder = client.post(
        "/records/claim",
        json={"resource_type": "REQUEST", "resource_id": rid,
              "verification_contact_point_id": str(ids.CP_AMINA)},
        headers={"Authorization": f"Bearer {ids.ACC_AMINA}",
                 "Idempotency-Key": "sgb-intruder"},
    )
    assert intruder.status_code == 403, intruder.text
    assert intruder.json()["code"] == "CLAIM_NOT_ELIGIBLE"
    with Session(bind=engine, future=True) as s:
        assert s.execute(
            text("SELECT count(*) FROM turab.record_claim_events "
                 "WHERE request_id = :r"),
            {"r": uuid.UUID(rid)},
        ).scalar_one() == 0, "a refused claim must leave no blocking trace"

    # --- 2b. Khadija claims it. Same row, no duplicate.
    claimed = client.post(
        "/records/claim",
        json={"resource_type": "REQUEST", "resource_id": rid,
              "verification_contact_point_id": str(ids.CP_KHADIJA)},
        headers={**khadija(ids), "Idempotency-Key": "sgb-claim"},
    )
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["outcome"] == "CLAIMED"
    assert _count(engine) == total_before, "claiming must not duplicate the record"

    # --- 3. it is qualified and activated through the documented path
    for target in ("CONTACTED", "QUALIFIED", "ACTIVE"):
        moved = client.post(
            f"/requests/{rid}/state", json={"target_status": target},
            headers={**operator(ids), "Idempotency-Key": f"sgb-{target}"},
        )
        assert moved.status_code == 200, moved.text

    # --- 4. her budget changes; the data update records who said so
    current = client.get(f"/requests/{rid}", headers=operator(ids)).json()
    raised = client.patch(
        f"/requests/{rid}", json={"budget_max_dzd": 65_000},
        headers={**khadija(ids), "If-Match-Version": str(current["version"])},
    )
    assert raised.status_code == 200, raised.text
    assert raised.json()["status"] == "ACTIVE", "a data update is not a state change"

    # --- 5. four months pass with no contact
    _age(engine, rid, days=125)
    from turab.services import requests as request_service

    with Session(bind=engine, future=True) as s:
        moved = request_service.mark_stale_as_needing_confirmation(s)
        s.commit()
    assert uuid.UUID(rid) in moved

    stale_view = client.get(f"/requests/{rid}", headers=operator(ids)).json()
    assert stale_view["status"] == "NEEDS_CONFIRMATION"
    assert stale_view["freshness"]["state"] == "STALE"

    # --- 6. the operator rings and reconfirms
    confirmed = client.post(
        f"/requests/{rid}/reconfirm", json={"notes": "rang, still looking"},
        headers={**operator(ids), "Idempotency-Key": "sgb-reconfirm"},
    )
    assert confirmed.status_code == 200, confirmed.text

    # =====================================================================
    # STOP GATE B — the three questions, answered from ONE staff read.
    # =====================================================================
    view = client.get(f"/requests/{rid}", headers=operator(ids))
    assert view.status_code == 200
    brief = view.json()

    # Q1: what does the buyer want?
    assert brief["transaction_intent"] == "RENT"
    assert brief["desired_property_type"] == "APARTMENT"
    assert brief["budget_target_dzd"] == 45_000
    assert brief["budget_max_dzd"] == 65_000, "the raise she asked for is here"
    assert brief["local_location_detail"] == "sgb-near the university"
    assert brief["intent"] == "ACTIVE_SEARCH"

    # Q2: what is hard, and what is merely preferred?
    importance = {c["criterion_code"]: c["importance"] for c in brief["criteria"]}
    assert importance == {
        "ROOMS_MIN": "REQUIRED",
        "BUILT_AREA_MIN": "PREFERRED",
        "DOCUMENT_TYPE": "FLEXIBLE",
    }
    assert brief["property_type_importance"] == "REQUIRED"
    assert brief["budget_importance"] == "REQUIRED"
    assert brief["budget_flexibility"] == "LOW"

    # Q3: when was this last confirmed — and judged against which policy?
    assert brief["last_confirmed_at"] is not None
    assert brief["freshness"]["state"] == "FRESH"
    assert brief["freshness"]["threshold_days"] == 30
    assert brief["freshness"]["policy_version"] == "0.2.0"
    assert brief["status"] == "ACTIVE", "reconfirming returned it to ACTIVE"

    # And the record says who changed what, so "she asked for more" is
    # evidence rather than recollection.
    with Session(bind=engine, future=True) as s:
        trail = request_service.provenance_for(s, uuid.UUID(rid))
    raise_entry = next(
        c for c in trail
        if c["attribute_code"] == "budget_max_dzd" and c["claimed_value"] == 65_000
    )
    assert raise_entry["recorded_by_account_id"] == ids.ACC_KHADIJA
    assert raise_entry["recorded_at"] is not None
    assert any(c["attribute_code"] == "status" for c in trail)


def test_the_gate_scenario_would_fail_if_importance_were_not_carried(client, ids):
    """Guards the gate itself: Q2 is the assertion most easily made vacuous,
    because it passes trivially if `criteria` is absent and the dict is empty.
    """
    created = client.post(
        "/requests",
        json={"party_id": str(ids.KHADIJA), "transaction_intent": "BUY",
              "intent": "EXPLORING", "management_mode": "ASSISTED",
              "claim_status": "UNCLAIMED", "local_location_detail": "sgb-empty"},
        headers={**operator(ids), "Idempotency-Key": "sgb-empty"},
    )
    rid = created.json()["request_id"]
    brief = client.get(f"/requests/{rid}", headers=operator(ids)).json()
    assert "criteria" in brief, "the staff read must always carry the key"
    assert brief["criteria"] == [], "and an empty list when there are none"


def _count(engine) -> int:
    with Session(bind=engine, future=True) as s:
        return s.execute(text("SELECT count(*) FROM turab.requests")).scalar_one()


def _age(engine, request_id, *, days: int) -> None:
    with Session(bind=engine, future=True) as s:
        s.execute(
            text("UPDATE turab.requests SET last_confirmed_at = :t "
                 "WHERE request_id = :r"),
            {"t": datetime.now(UTC) - timedelta(days=days), "r": uuid.UUID(request_id)},
        )
        s.commit()
