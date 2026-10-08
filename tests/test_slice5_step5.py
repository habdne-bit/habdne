"""Slice 5 step 5: revalidate, share, close, the opportunity queue, and B10.

Ref: `docs/gate/SLICE_5_PLAN.md`: §3.7 [R3-2] (the currency check, one table,
three users); G5-8 (share: direction accepted in the review of 288bfdb);
G5-9 (revalidate); G5-10 (close: decided in the review of d0e0bc9); G5-11 (a)
(the opportunity queue, no time-based membership); G5-12 (B10, the service
guard); §6.1 mandatory test 6 through the real close; H05, B03.

**PROVISIONAL, not decided** (G5-8's open points, recorded in
`SLICE_5_STEP5_DELIVERY.md`):
- (i) the share's `channel` and `note` are stored nowhere (option (b)'s
  narrower reading: no Slice 7 table is written);
- (iii) a CURRENT `CONTACT_BEFORE_SHARING` binding refuses the share (the
  plan's recommended option (a)).
The tests of these two are marked so, and change with the decision.

**What is a fixture here.** ENGAGED has no Slice 5 path (G5-1): the one
ENGAGED opportunity is written by SQL, SHARED -> ENGAGED with its stamp, as
migration 0006 admits. A fact changed after creation is written by SQL, as
an operator's correction would land.

**No new module is imported at module level,** so the whole file collects at
the step's base commit and the before-fix record measures each test.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.test_slice4_step7 import _all, _exec, _one, _run
from tests.test_slice5_step3 import _approve, _make_alias, _world
from tests.test_slice5_step3 import _opportunity as _by_match
from tests.test_slice5_step4 import SCHEMAS, _customer, _get, _opportunity, _validate
from turab.auth.audit import AccessAuditor, RecordingAuditSink

ROOT = Path(__file__).resolve().parents[1]
#: G5-10, written out here and not read from the module under test.
EIGHT = ("OWNER_REJECTED", "BUYER_REJECTED", "PROPERTY_UNAVAILABLE", "REQUEST_CHANGED",
         "UNREACHABLE", "DEAL_CONFIRMED", "DUPLICATE_OPPORTUNITY_CONSOLIDATED", "OTHER")


@pytest.fixture
def sink():
    return RecordingAuditSink()


@pytest.fixture
def client(engine, sink):
    from turab.app import create_app

    app = create_app(engine=engine, auditor=AccessAuditor(sink))
    with TestClient(app, raise_server_exceptions=True) as c:
        yield c


# --- the commands, and what a refusal must leave behind ---------------------------------

def _cmd(client, opportunity, verb, body=None, account=None, key=None, ids=None):
    account = account or (ids.ACC_OPERATOR if ids is not None else None)
    return client.post(f"/opportunities/{opportunity}/{verb}", json={} if body is None else body,
                       headers={"Authorization": f"Bearer {account}",
                                "Idempotency-Key": key or str(uuid.uuid4())})


def _revalidate(client, ids, opportunity, account=None, key=None):
    return _cmd(client, opportunity, "revalidate", {}, account or ids.ACC_OPERATOR, key)


def _share(client, ids, opportunity, account=None, key=None, body=None):
    return _cmd(client, opportunity, "share", body or {"channel": "WEB"},
                account or ids.ACC_OPERATOR, key)


def _close(client, ids, opportunity, reason="BUYER_REJECTED", account=None, key=None):
    return _cmd(client, opportunity, "close", {"reason_code": reason},
                account or ids.ACC_OPERATOR, key)


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _row(engine, opportunity):
    """The whole stored row, as PostgreSQL renders it."""
    return json.loads(_one(engine, "SELECT to_jsonb(o)::text FROM turab.opportunities o "
                                   "WHERE opportunity_id = :o", o=opportunity))


def _footprint(engine, opportunity, key):
    """Everything a command could write: the row, the audit high-water mark,
    the key, and the Slice 7 tables a share might be tempted to write."""
    return {"row": _row(engine, opportunity),
            "audit": _one(engine, "SELECT coalesce(max(audit_id), 0) FROM turab.audit_log"),
            "key": _one(engine, "SELECT count(*) FROM turab.idempotency_records "
                                "WHERE idempotency_key = :k", k=key),
            "interactions": _one(engine, "SELECT count(*) FROM turab.interactions"),
            "opportunities": _one(engine, "SELECT count(*) FROM turab.opportunities")}


def _refused(client, engine, ids, opportunity, verb, status, code, body=None, account=None):
    """The refusal, and nothing written: no change of the row, no audit row,
    no key consumed, no interaction."""
    key = str(uuid.uuid4())
    before = _footprint(engine, opportunity, key)
    default = {"revalidate": {}, "share": {"channel": "WEB"},
               "close": {"reason_code": "BUYER_REJECTED"}}[verb]
    r = _cmd(client, opportunity, verb, default if body is None else body,
             account or ids.ACC_OPERATOR, key)
    assert (r.status_code, r.json().get("code")) == (status, code), r.text
    assert _footprint(engine, opportunity, key) == before, "a refusal writes nothing"
    return r.json()


def _fresh(ids, engine, client, **kw):
    """One APPROVED opportunity, NEW and VALID, through the real run and the
    real review (step 4's world), not shared."""
    return _opportunity(client, engine, ids, share=False, **kw)


def _set(engine, sql, **params):
    _exec(engine, sql, **params)


# ======================================================================================
# G5-9: revalidate, the one writer of validity (§3.7)
# ======================================================================================

def test_revalidate_right_after_approval_is_valid_and_changes_no_validity(client, engine,
                                                                          ids):
    """§3.7 over HTTP: approval, then an immediate revalidate: VALID, with no
    change of `validity_status`; the confirmation and activity times move;
    nothing else does."""
    world = _fresh(ids, engine, client)
    before = _row(engine, world["opportunity"])
    body = _ok(_revalidate(client, ids, world["opportunity"]))
    after = _row(engine, world["opportunity"])
    assert (body["validity_status"], body["status"]) == ("VALID", "NEW")
    assert body["validity_reasons"] == []
    assert after["validity_status"] == before["validity_status"] == "VALID"
    assert after["last_confirmed_at"] > before["last_confirmed_at"]
    assert after["last_activity_at"] == after["last_confirmed_at"]
    unchanged = set(before) - {"last_confirmed_at", "last_activity_at"}
    assert {k: after[k] for k in unchanged} == {k: before[k] for k in unchanged}
    # The response is the open `InternalOpportunityView`, plus the reasons.
    _validate(body, SCHEMAS["InternalOpportunityView"])
    assert set(body) == set(SCHEMAS["InternalOpportunityView"]["properties"]) | {
        "validity_reasons"}


def test_with_the_clock_pinned_approval_and_revalidate_agree(engine, ids, client):
    """§3.7, "approval accepted ⇔ revalidate immediately after returns VALID,
    with the clock pinned between the calls". Both read `currency.check`
    (the forced-check tests below and step 3's); here the real check, on the
    same facts, at one instant T. The same opportunity judged 400 days on is
    NEEDS_CONFIRMATION: time is the one exception the plan names."""
    from sqlalchemy.orm import Session

    from turab.services import match_review, opportunity_commands

    *_, [m] = _world(client, engine, ids)
    s = Session(bind=engine)
    try:
        s.execute(text("SELECT set_config('app.account_id', :a, true)"),
                  {"a": str(ids.ACC_REVIEWER)})
        t = s.execute(text("SELECT clock_timestamp()")).scalar_one()
        prepared = match_review.prepare(s, match_id=uuid.UUID(m["match_id"]),
                                        decision="APPROVED", reason_code=None,
                                        reason_text=None, clock=t)
        made = match_review.record(s, prepared, reviewer_account_id=ids.ACC_REVIEWER, clock=t)
        opportunity = uuid.UUID(made["opportunity"]["opportunity_id"])
        again = opportunity_commands.prepare_revalidate(s, opportunity_id=opportunity, clock=t)
        assert again.checked.as_of == t
        assert again.checked.currency.validity == "VALID"
        assert again.checked.facts == prepared.checked.facts
        later = s.execute(text("SELECT CAST(:t AS timestamptz) + interval '400 days'"),
                          {"t": t}).scalar_one()
        stale = opportunity_commands.prepare_revalidate(s, opportunity_id=opportunity,
                                                        clock=later)
        assert stale.checked.currency.validity == "NEEDS_CONFIRMATION"
        assert [r["fact"] for r in stale.checked.currency.reasons] == [
            "REQUEST_FRESHNESS", "PROPERTY_FRESHNESS", "OFFER_FRESHNESS"]
    finally:
        s.rollback()
        s.close()


def test_revalidate_stores_exactly_what_the_check_returns(client, engine, ids, monkeypatch):
    """§3.7: revalidate's one source of validity is `currency.check`. With
    every fact unchanged, forcing the check's answer decides what is stored,
    for each class, and back (not monotonic)."""
    from turab.services import currency

    world = _fresh(ids, engine, client)
    real = currency.check

    def forced(validity):
        def check(session, **kw):
            got = real(session, **kw)
            reasons = () if validity == "VALID" else (
                {"fact": "IDENTITY", "value": "ALIAS", "class": validity, "reason_code": None},)
            return currency.Checked(currency.Currency(validity, reasons), got.facts,
                                    got.sharing_scope, got.permission_snapshot,
                                    got.current_permission_binding_id, got.as_of)
        return check
    for validity in ("INVALID", "NEEDS_CONFIRMATION", "VALID", "INVALID", "VALID"):
        monkeypatch.setattr(currency, "check", forced(validity))
        body = _ok(_revalidate(client, ids, world["opportunity"]))
        assert body["validity_status"] == _row(engine, world["opportunity"])[
            "validity_status"] == validity
        assert len(body["validity_reasons"]) == (validity != "VALID")


@pytest.mark.parametrize("change,validity,reasons", [
    ("offer_paused", "NEEDS_CONFIRMATION", [("OFFER_STATUS", "PAUSED", None)]),
    ("offer_withdrawn", "INVALID", [("OFFER_STATUS", "WITHDRAWN", None)]),
    ("unavailable", "INVALID", [("AVAILABILITY", "UNAVAILABLE", "PROPERTY_UNAVAILABLE")]),
    ("request_closed", "INVALID", [("REQUEST_STATUS", "CLOSED", None)]),
    ("request_stale", "NEEDS_CONFIRMATION", [("REQUEST_FRESHNESS", "STALE", "REQUEST_STALE")]),
    ("consent_revoked", "INVALID", [("PERMISSION", "FAIL", "CONSENT_REVOKED")]),
])
def test_a_fact_changed_after_creation_is_recorded_by_revalidate(client, engine, ids, change,
                                                                 validity, reasons):
    """§3.7 over HTTP: a PAUSED offer after creation gives NEEDS_CONFIRMATION,
    an UNAVAILABLE property INVALID, and so on. The validity is stored; the
    confirmation time is not moved; the reasons are in the response."""
    world = _fresh(ids, engine, client)
    sql = {
        "offer_paused": ("UPDATE turab.property_offers SET status = 'PAUSED' "
                         "WHERE offer_id = :v", world["offer"]),
        "offer_withdrawn": ("UPDATE turab.property_offers SET status = 'WITHDRAWN' "
                            "WHERE offer_id = :v", world["offer"]),
        "unavailable": ("UPDATE turab.properties SET current_availability = 'UNAVAILABLE' "
                        "WHERE property_id = :v", world["property"]),
        "request_closed": ("UPDATE turab.requests SET status = 'CLOSED' WHERE request_id = :v",
                           world["request"]),
        "request_stale": ("UPDATE turab.requests SET last_confirmed_at = now() - "
                          "interval '400 days' WHERE request_id = :v", world["request"]),
        "consent_revoked": ("UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                            "WHERE offer_id = :v", world["offer"]),
    }[change]
    before = _row(engine, world["opportunity"])
    _set(engine, sql[0], v=sql[1])
    body = _ok(_revalidate(client, ids, world["opportunity"]))
    after = _row(engine, world["opportunity"])
    assert body["validity_status"] == after["validity_status"] == validity
    assert [(r["fact"], r["value"], r["reason_code"]) for r in body["validity_reasons"]] == \
        reasons
    assert all(r["class"] == validity for r in body["validity_reasons"])
    assert after["last_confirmed_at"] == before["last_confirmed_at"], \
        "only a VALID check confirms"
    assert after["last_activity_at"] is not None
    for column in ("commercial_context_snapshot", "permission_snapshot", "why_real",
                   "known_differences", "sharing_scope", "current_offer_id"):
        assert after[column] == before[column], column


def test_validity_returns_to_valid_when_the_facts_do(client, engine, ids):
    """G5-9: validity is not monotonic."""
    world = _fresh(ids, engine, client)
    _set(engine, "UPDATE turab.properties SET current_availability = 'UNAVAILABLE' "
                 "WHERE property_id = :p", p=world["property"])
    assert _ok(_revalidate(client, ids, world["opportunity"]))["validity_status"] == "INVALID"
    confirmed = _row(engine, world["opportunity"])["last_confirmed_at"]
    _set(engine, "UPDATE turab.properties SET current_availability = 'AVAILABLE' "
                 "WHERE property_id = :p", p=world["property"])
    body = _ok(_revalidate(client, ids, world["opportunity"]))
    assert (body["validity_status"], body["validity_reasons"]) == ("VALID", [])
    assert _row(engine, world["opportunity"])["last_confirmed_at"] > confirmed


def test_revalidate_records_the_current_binding_and_null_when_none(client, engine, ids):
    """G5-9 with G5-5's order: the binding is the first CURRENT one; after a
    revocation it is null; a new CURRENT binding on the offer is recorded."""
    world = _fresh(ids, engine, client)
    first = _row(engine, world["opportunity"])["current_permission_binding_id"]
    assert first is not None
    _set(engine, "UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                 "WHERE offer_id = :o", o=world["offer"])
    assert _ok(_revalidate(client, ids, world["opportunity"]))[
        "current_permission_binding_id"] is None
    grant = _one(engine, """
        INSERT INTO turab.consent_grants (party_id, scope, channel, consent_version, granted_at)
        VALUES (:party, 'PRIVATE_MATCHING_ONLY', 'PHONE_CONFIRMED', 'v2',
                now() - interval '1 hour') RETURNING consent_id""", party=ids.BRAHIM)
    second = _one(engine, """
        INSERT INTO turab.resource_consent_bindings (consent_id, purpose, offer_id, bound_at)
        VALUES (:c, 'PRIVATE_MATCHING_ONLY', :o, now() - interval '1 minute')
        RETURNING consent_binding_id""", c=grant, o=world["offer"])
    body = _ok(_revalidate(client, ids, world["opportunity"]))
    assert (body["validity_status"], body["current_permission_binding_id"]) == (
        "VALID", str(second))


def test_revalidate_is_audited_once_with_its_actor(client, engine, ids):
    world = _fresh(ids, engine, client)
    mark = _one(engine, "SELECT coalesce(max(audit_id), 0) FROM turab.audit_log")
    _ok(_revalidate(client, ids, world["opportunity"], account=ids.ACC_REVIEWER))
    rows = _all(engine, """SELECT entity_table, action, actor_account_id FROM turab.audit_log
                            WHERE audit_id > :m AND entity_id = :o""",
                m=mark, o=world["opportunity"])
    assert [(r["entity_table"], r["action"], r["actor_account_id"]) for r in rows] == [
        ("opportunities", "UPDATE", ids.ACC_REVIEWER)]


# ======================================================================================
# G5-8: share — the check never persists
# ======================================================================================

def test_share_moves_new_to_shared_once_and_a_later_share_moves_activity_only(client, engine,
                                                                             ids):
    world = _fresh(ids, engine, client)
    assert _customer(client, ids, world).status_code == 404, "G5-7 (a): unseen until shared"
    interactions = _one(engine, "SELECT count(*) FROM turab.interactions")
    first = _ok(_share(client, ids, world["opportunity"]))
    row = _row(engine, world["opportunity"])
    assert (first["status"], row["status"]) == ("SHARED", "SHARED")
    assert row["shared_at"] is not None and row["last_activity_at"] == row["shared_at"]
    assert row["validity_status"] == "VALID" and row["engaged_at"] is None
    _validate(first, SCHEMAS["InternalOpportunityView"])
    assert _customer(client, ids, world).status_code == 200, "G5-7 (a): seen once shared"

    second = _ok(_share(client, ids, world["opportunity"], body={"channel": "EMAIL"}))
    again = _row(engine, world["opportunity"])
    assert second["status"] == "SHARED" and again["shared_at"] == row["shared_at"]
    assert again["last_activity_at"] > row["last_activity_at"]
    assert _one(engine, "SELECT count(*) FROM turab.interactions") == interactions, \
        "no message is sent, and no interaction is written (G5-8 (i): PROVISIONAL)"


def test_share_writes_no_validity_binding_or_confirmation(client, engine, ids):
    """G5-8: share calls the check and never persists its result."""
    world = _fresh(ids, engine, client)
    before = _row(engine, world["opportunity"])
    _ok(_share(client, ids, world["opportunity"]))
    after = _row(engine, world["opportunity"])
    changed = {k for k in before if before[k] != after[k]}
    assert changed == {"status", "shared_at", "last_activity_at"}


def test_b03_h05_a_share_after_a_revocation_is_refused_and_changes_nothing(client, engine,
                                                                         ids):
    """H05, B03: the consent is revoked after the opportunity was created. The
    share is refused, 409 CONSENT_REVOKED, naming the permission; the row,
    the audit log's high-water mark and the idempotency table are unchanged.
    The downgrade is not stored by the refusal: revalidate stores it, and the
    next share is then refused on the recorded validity."""
    world = _fresh(ids, engine, client)
    _set(engine, "UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                 "WHERE offer_id = :o", o=world["offer"])
    body = _refused(client, engine, ids, world["opportunity"], "share", 409, "CONSENT_REVOKED")
    assert [(e["field"], e["code"]) for e in body["field_errors"]] == [
        ("PERMISSION", "CONSENT_REVOKED")]
    assert _row(engine, world["opportunity"])["validity_status"] == "VALID"
    assert _ok(_revalidate(client, ids, world["opportunity"]))["validity_status"] == "INVALID"
    body = _refused(client, engine, ids, world["opportunity"], "share", 409,
                    "OPPORTUNITY_NOT_VALID")
    assert [(e["field"], e["code"]) for e in body["field_errors"]] == [
        ("VALIDITY_STATUS", "INVALID")]
    assert _customer(client, ids, world).status_code == 404


def test_a_stored_needs_confirmation_is_refused_until_revalidate_records_valid(client, engine,
                                                                              ids):
    """G5-8 item 2: the facts pass now, but the RECORDED validity is
    NEEDS_CONFIRMATION; the share is refused until revalidate records VALID."""
    world = _fresh(ids, engine, client)
    _set(engine, "UPDATE turab.property_offers SET status = 'PAUSED' WHERE offer_id = :o",
         o=world["offer"])
    assert _ok(_revalidate(client, ids, world["opportunity"]))[
        "validity_status"] == "NEEDS_CONFIRMATION"
    _set(engine, "UPDATE turab.property_offers SET status = 'ACTIVE' WHERE offer_id = :o",
         o=world["offer"])
    _refused(client, engine, ids, world["opportunity"], "share", 409, "OPPORTUNITY_NOT_VALID")
    assert _ok(_revalidate(client, ids, world["opportunity"]))["validity_status"] == "VALID"
    assert _ok(_share(client, ids, world["opportunity"]))["status"] == "SHARED"


@pytest.mark.parametrize("sql,field,code", [
    ("UPDATE turab.property_offers SET status = 'PAUSED' WHERE offer_id = :offer",
     "OFFER_STATUS", "PAUSED"),
    ("UPDATE turab.properties SET current_availability = 'UNAVAILABLE' "
     "WHERE property_id = :prop", "AVAILABILITY", "PROPERTY_UNAVAILABLE"),
    ("UPDATE turab.requests SET status = 'PAUSED' WHERE request_id = :req",
     "REQUEST_STATUS", "PAUSED"),
])
def test_a_share_on_facts_that_are_not_valid_now_is_refused(client, engine, ids, sql, field,
                                                            code):
    """G5-8 item 3, other than permission: 409 OPPORTUNITY_NOT_VALID, every
    failing fact named, the recorded validity untouched."""
    world = _fresh(ids, engine, client)
    _set(engine, sql, **{k: v for k, v in (("offer", world["offer"]),
                                           ("prop", world["property"]),
                                           ("req", world["request"])) if f":{k}" in sql})
    body = _refused(client, engine, ids, world["opportunity"], "share", 409,
                    "OPPORTUNITY_NOT_VALID")
    assert [(e["field"], e["code"]) for e in body["field_errors"]] == [(field, code)]


def test_a_revoked_consent_and_another_failing_fact_answer_consent_revoked(client, engine,
                                                                          ids):
    """G5-8: permission FAIL decides the code; every failing fact is named."""
    world = _fresh(ids, engine, client)
    _set(engine, "UPDATE turab.property_offers SET status = 'PAUSED' WHERE offer_id = :o",
         o=world["offer"])
    _set(engine, "UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                 "WHERE offer_id = :o", o=world["offer"])
    body = _refused(client, engine, ids, world["opportunity"], "share", 409, "CONSENT_REVOKED")
    assert [e["field"] for e in body["field_errors"]] == ["OFFER_STATUS", "PERMISSION"]


def test_a_narrowed_scope_refuses_the_share_and_a_wider_one_does_not(client, engine, ids):
    """G5-8 item 4: the offer's permission scope now, against the
    opportunity's `sharing_scope`. A wider scope changes nothing stored: the
    opportunity keeps the scope it was approved with."""
    world = _fresh(ids, engine, client, scope="PROPERTY_DETAILS_ALLOWED")
    _set(engine, "UPDATE turab.property_offers SET permission_scope = 'SUMMARY_ONLY' "
                 "WHERE offer_id = :o", o=world["offer"])
    body = _refused(client, engine, ids, world["opportunity"], "share", 409,
                    "SHARING_SCOPE_NARROWED")
    assert [(e["field"], e["code"]) for e in body["field_errors"]] == [
        ("SHARING_SCOPE", "SUMMARY_ONLY")]
    _set(engine, "UPDATE turab.property_offers SET permission_scope = "
                 "'CONTACT_AFTER_CONFIRMATION' WHERE offer_id = :o", o=world["offer"])
    assert _ok(_share(client, ids, world["opportunity"]))[
        "sharing_scope"] == "PROPERTY_DETAILS_ALLOWED"


def _contact_first(engine, ids, offer, *, revoked=False):
    grant = _one(engine, """
        INSERT INTO turab.consent_grants (party_id, scope, channel, consent_version, granted_at)
        VALUES (:party, 'CONTACT_BEFORE_SHARING', 'PHONE_CONFIRMED', 'v1',
                now() - interval '1 hour') RETURNING consent_id""", party=ids.BRAHIM)
    return _one(engine, """
        INSERT INTO turab.resource_consent_bindings (consent_id, purpose, offer_id, bound_at,
                                                     revoked_at)
        VALUES (:c, 'CONTACT_BEFORE_SHARING', :o, now() - interval '1 minute',
                CASE WHEN :r THEN now() END)
        RETURNING consent_binding_id""", c=grant, o=offer, r=revoked)


def test_provisional_a_current_contact_before_sharing_binding_refuses_the_share(client,
                                                                              engine, ids):
    """PROVISIONAL, G5-8 (iii) (a), recommended and not yet decided: a CURRENT
    CONTACT_BEFORE_SHARING binding refuses the share; a revoked one does not.
    It is not a matching purpose, so the validity is untouched."""
    world = _fresh(ids, engine, client)
    _contact_first(engine, ids, world["offer"], revoked=True)
    binding = _contact_first(engine, ids, world["offer"])
    body = _refused(client, engine, ids, world["opportunity"], "share", 409,
                    "CONTACT_BEFORE_SHARING_REQUIRED")
    assert [(e["field"], e["code"]) for e in body["field_errors"]] == [
        ("PERMISSION", "CONTACT_BEFORE_SHARING")]
    assert str(binding) in body["field_errors"][0]["message"]
    assert _ok(_revalidate(client, ids, world["opportunity"]))["validity_status"] == "VALID"
    _set(engine, "UPDATE turab.resource_consent_bindings SET revoked_at = now() "
                 "WHERE consent_binding_id = :b", b=binding)
    assert _ok(_share(client, ids, world["opportunity"]))["status"] == "SHARED"


def test_a_refused_share_consumes_no_key_and_the_same_key_is_evaluated_afresh(client, engine,
                                                                             ids):
    """G5-8, as Slice 4 D6: the refusal comes before the claim, so the same
    key, once the facts change, is a new call."""
    world = _fresh(ids, engine, client)
    _set(engine, "UPDATE turab.property_offers SET status = 'PAUSED' WHERE offer_id = :o",
         o=world["offer"])
    key = str(uuid.uuid4())
    r = _share(client, ids, world["opportunity"], key=key)
    assert (r.status_code, r.json()["code"]) == (409, "OPPORTUNITY_NOT_VALID")
    _set(engine, "UPDATE turab.property_offers SET status = 'ACTIVE' WHERE offer_id = :o",
         o=world["offer"])
    assert _ok(_share(client, ids, world["opportunity"], key=key))["status"] == "SHARED"


def test_a_share_replays_and_a_different_body_on_its_key_conflicts(client, engine, ids):
    world = _fresh(ids, engine, client)
    key = str(uuid.uuid4())
    first = _ok(_share(client, ids, world["opportunity"], key=key))
    mark = _one(engine, "SELECT coalesce(max(audit_id), 0) FROM turab.audit_log")
    assert _ok(_share(client, ids, world["opportunity"], key=key)) == first
    assert _one(engine, "SELECT coalesce(max(audit_id), 0) FROM turab.audit_log") == mark
    r = _share(client, ids, world["opportunity"], key=key, body={"channel": "SMS"})
    assert (r.status_code, r.json()["code"]) == (409, "IDEMPOTENCY_KEY_CONFLICT")


@pytest.mark.parametrize("body", [{"channel": "PHONE"}, {"channel": None}, {"note": None},
                                  {"note": 3}])
def test_the_share_body_is_typed_as_the_contract_types_it(client, engine, ids, body):
    """`channel` is one of the contract's four values; `note` a string; an
    explicit null is refused. 422, nothing written."""
    world = _fresh(ids, engine, client)
    _refused(client, engine, ids, world["opportunity"], "share", 422, "VALIDATION_FAILED",
             body=body)


def test_the_share_body_is_open_and_carries_nothing_stored(client, engine, ids):
    """The contract leaves the body open (no `additionalProperties: false`):
    an undeclared field is accepted, as for the matching run; the channel and
    the note are stored nowhere (G5-8 (i): PROVISIONAL)."""
    world = _fresh(ids, engine, client)
    note = f"note-{uuid.uuid4().hex}"
    _ok(_share(client, ids, world["opportunity"],
               body={"channel": "WHATSAPP", "note": note, "extra": 1}))
    assert note not in json.dumps(_row(engine, world["opportunity"]))
    assert not _one(engine, "SELECT count(*) FROM turab.audit_log "
                            "WHERE old_row::text LIKE :n OR new_row::text LIKE :n "
                            "OR context::text LIKE :n", n=f"%{note}%")


# ======================================================================================
# G5-10: close
# ======================================================================================

@pytest.mark.parametrize("reason", EIGHT)
def test_close_from_new_writes_status_time_reason_and_activity_together(client, engine, ids,
                                                                        reason):
    world = _fresh(ids, engine, client)
    body = _ok(_close(client, ids, world["opportunity"], reason))
    row = _row(engine, world["opportunity"])
    assert (body["status"], row["status"], row["close_reason_code"]) == (
        "CLOSED", "CLOSED", reason)
    assert row["closed_at"] is not None and row["last_activity_at"] == row["closed_at"]
    assert row["shared_at"] is None and row["engaged_at"] is None
    assert row["validity_status"] == "VALID"


def test_close_from_shared_and_from_engaged_keeps_the_event_stamps(client, engine, ids):
    shared = _fresh(ids, engine, client)
    _ok(_share(client, ids, shared["opportunity"]))
    stamp = _row(engine, shared["opportunity"])["shared_at"]
    _ok(_close(client, ids, shared["opportunity"], "OWNER_REJECTED"))
    row = _row(engine, shared["opportunity"])
    assert (row["status"], row["shared_at"], row["engaged_at"]) == ("CLOSED", stamp, None)

    engaged = _fresh(ids, engine, client)
    _ok(_share(client, ids, engaged["opportunity"]))
    # FIXTURE: SHARED -> ENGAGED has no Slice 5 path (G5-1).
    _set(engine, "UPDATE turab.opportunities SET status = 'ENGAGED', engaged_at = now() "
                 "WHERE opportunity_id = :o", o=engaged["opportunity"])
    before = _row(engine, engaged["opportunity"])
    _ok(_close(client, ids, engaged["opportunity"], "DEAL_CONFIRMED"))
    row = _row(engine, engaged["opportunity"])
    assert row["status"] == "CLOSED"
    assert (row["shared_at"], row["engaged_at"]) == (before["shared_at"], before["engaged_at"])


def test_a_closed_opportunity_can_be_closed_whatever_its_validity(client, engine, ids):
    world = _fresh(ids, engine, client)
    _set(engine, "UPDATE turab.properties SET current_availability = 'UNAVAILABLE' "
                 "WHERE property_id = :p", p=world["property"])
    _ok(_revalidate(client, ids, world["opportunity"]))
    assert _ok(_close(client, ids, world["opportunity"], "PROPERTY_UNAVAILABLE"))[
        "validity_status"] == "INVALID"


@pytest.mark.parametrize("body,status,code", [
    ({"reason_code": "CONSENT_REVOKED"}, 422, "CLOSE_REASON_NOT_ALLOWED"),
    ({"reason_code": "DOCUMENT_NOT_KNOWN"}, 422, "CLOSE_REASON_NOT_ALLOWED"),
    ({"reason_code": "NOT_A_CODE"}, 422, "CLOSE_REASON_NOT_ALLOWED"),
    ({"reason_code": "buyer_rejected"}, 422, "CLOSE_REASON_NOT_ALLOWED"),
    ({}, 422, "VALIDATION_FAILED"),
    ({"reason_code": None}, 422, "VALIDATION_FAILED"),
    ({"reason_code": "OTHER", "note": None}, 422, "VALIDATION_FAILED"),
    ({"reason_code": "OTHER", "extra": 1}, 422, "VALIDATION_FAILED"),
])
def test_a_close_reason_outside_the_eight_is_refused(client, engine, ids, body, status, code):
    """G5-10: the category OPPORTUNITY plus OTHER; `CloseCommand` is closed in
    the contract, and its reason required."""
    world = _fresh(ids, engine, client)
    _refused(client, engine, ids, world["opportunity"], "close", status, code, body=body)


def test_the_eight_are_the_seeded_category_opportunity_and_other(engine):
    from turab.services import opportunity_commands

    seeded = {r["code"] for r in _all(engine, """
        SELECT code FROM turab.reason_codes
         WHERE active AND (category = 'OPPORTUNITY' OR code = 'OTHER')""")}
    assert set(opportunity_commands.CLOSE_REASONS) == seeded == set(EIGHT)


@pytest.mark.parametrize("verb", ["revalidate", "share", "close"])
def test_closed_is_final_for_every_command(client, engine, ids, verb):
    """G5-10: any later command on a CLOSED opportunity is 409
    OPPORTUNITY_CLOSED; nothing is written and no key consumed."""
    world = _fresh(ids, engine, client)
    _ok(_close(client, ids, world["opportunity"]))
    _refused(client, engine, ids, world["opportunity"], verb, 409, "OPPORTUNITY_CLOSED")


def test_a_close_replays_on_its_key_after_the_opportunity_is_closed(client, engine, ids):
    """The key answers before the state does (API_CONTRACTS §2.3): the same
    key and body replay the close; another key is refused as closed."""
    world = _fresh(ids, engine, client)
    key = str(uuid.uuid4())
    first = _ok(_close(client, ids, world["opportunity"], key=key))
    assert _ok(_close(client, ids, world["opportunity"], key=key)) == first
    _refused(client, engine, ids, world["opportunity"], "close", 409, "OPPORTUNITY_CLOSED")


def test_mandatory_6_the_real_close_frees_the_pair(client, engine, ids):
    """§6.1 test 6 through the close command (step 3 used an SQL fixture):
    while one opportunity is open the other offer's match is refused; once it
    is CLOSED by the command, that match is approved."""
    req, prop, _, [m1, m2] = _world(client, engine, ids, offers=2)
    _ok(_approve(client, m1["match_id"], ids.ACC_REVIEWER))
    r = _approve(client, m2["match_id"], ids.ACC_REVIEWER)
    assert (r.status_code, r.json()["code"]) == (409, "OPPORTUNITY_ALREADY_OPEN")
    first = _by_match(engine, m1["match_id"])["opportunity_id"]
    _ok(_close(client, ids, first, "DUPLICATE_OPPORTUNITY_CONSOLIDATED"))
    _ok(_approve(client, m2["match_id"], ids.ACC_REVIEWER))
    assert _one(engine, """SELECT count(*) FROM turab.opportunities
                            WHERE request_id = :r AND status <> 'CLOSED'""", r=req) == 1


def test_a_closed_opportunitys_match_yields_no_second_opportunity(client, engine, ids):
    """G5-10, the accepted consequence of `approved_match_id` UNIQUE: the
    closed opportunity's match is decided; another review is refused."""
    world = _fresh(ids, engine, client)
    _ok(_close(client, ids, world["opportunity"]))
    r = _approve(client, world["match"]["match_id"], ids.ACC_REVIEWER)
    assert (r.status_code, r.json()["code"]) == (409, "MATCH_REVIEW_DECIDED")


def test_a_close_waits_for_a_command_holding_the_opportunity_and_reads_its_result(
        client, engine, ids):
    """The lock is the first statement on the row: a close that arrives while
    another transaction holds the opportunity waits (witness:
    `pg_blocking_pids`), then reads what that transaction committed. Here the
    holder closes it, so the waiting close is 409 OPPORTUNITY_CLOSED, not a
    second close."""
    from turab.app import create_app

    world = _fresh(ids, engine, client)
    writer = engine.connect()
    try:
        tx = writer.begin()
        writer.execute(text("SELECT set_config('app.account_id', :a, true)"),
                       {"a": str(ids.ACC_ADMIN)})
        wpid = writer.execute(text("SELECT pg_backend_pid()")).scalar_one()
        writer.execute(text("SELECT 1 FROM turab.opportunities WHERE opportunity_id = :o "
                            "FOR UPDATE"), {"o": world["opportunity"]})
        writer.execute(text("""UPDATE turab.opportunities
                                  SET status = 'CLOSED', closed_at = now(),
                                      close_reason_code = 'OTHER'
                                WHERE opportunity_id = :o"""), {"o": world["opportunity"]})
        out = {}

        def send():
            with TestClient(create_app(engine=engine)) as c:
                out["r"] = _close(c, ids, world["opportunity"], "BUYER_REJECTED")

        t = threading.Thread(target=send)
        t.start()
        deadline, waiting = time.monotonic() + 30, []
        while not waiting:
            waiting = _all(engine, """
                SELECT pid FROM pg_stat_activity
                 WHERE pid <> :w AND wait_event_type = 'Lock'
                   AND :w = ANY(pg_blocking_pids(pid))""", w=wpid)
            assert waiting or time.monotonic() < deadline, "the close never waited"
            time.sleep(0.02)
        tx.commit()
    finally:
        writer.close()
    t.join(30)
    r = out["r"]
    assert (r.status_code, r.json()["code"]) == (409, "OPPORTUNITY_CLOSED"), r.text
    assert _row(engine, world["opportunity"])["close_reason_code"] == "OTHER"


# ======================================================================================
# Who may act
# ======================================================================================

@pytest.mark.parametrize("verb", ["revalidate", "share", "close"])
def test_an_unknown_opportunity_is_refused_and_recorded(client, ids, sink, verb):
    unknown = uuid.uuid4()
    r = _cmd(client, unknown, verb, {"reason_code": "OTHER"} if verb == "close" else {},
             ids.ACC_ADMIN)
    assert (r.status_code, r.json()["code"]) == (403, "OBJECT_NOT_AUTHORIZED")
    [record] = [x for x in sink.records if x.resource_id == unknown]
    assert (record.event.value, record.resource_kind) == ("DENIED", "OPPORTUNITY")


@pytest.mark.parametrize("verb,allowed", [
    ("revalidate", ("ACC_ADMIN", "ACC_OPERATOR", "ACC_REVIEWER")),
    ("share", ("ACC_ADMIN", "ACC_OPERATOR")),
    ("close", ("ACC_ADMIN", "ACC_OPERATOR", "ACC_REVIEWER")),
])
def test_the_roles_are_the_contracts(client, engine, ids, verb, allowed):
    """`x-roles`: share is ADMIN and OPERATOR; revalidate and close add
    REVIEWER. A customer, the request's own party included, is refused, and
    nothing is written."""
    world = _fresh(ids, engine, client)
    for name in ("ACC_ADMIN", "ACC_OPERATOR", "ACC_REVIEWER", "ACC_BRAHIM", "ACC_AMINA"):
        if name in allowed:
            continue
        _refused(client, engine, ids, world["opportunity"], verb, 403, "ROLE_NOT_PERMITTED",
                 account=getattr(ids, name))
    body = {"close": {"reason_code": "OTHER"}}.get(verb, {})
    for name in allowed:
        r = _cmd(client, world["opportunity"], verb, body, getattr(ids, name))
        assert r.status_code in (200, 409), (name, r.text)


# ======================================================================================
# B10: the service guard on `current_offer_id` (G5-12)
# ======================================================================================

def _sql_strings(path):
    import ast

    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            yield node.value
        elif isinstance(node, ast.JoinedStr):
            yield "".join(v.value for v in node.values
                          if isinstance(v, ast.Constant) and isinstance(v.value, str))


def _updates_of_opportunities():
    found = {}
    for path in sorted((ROOT / "src").rglob("*.py")):
        for sql in _sql_strings(path):
            for statement in re.findall(r"UPDATE\s+turab\.opportunities\b.*?(?:WHERE|$)",
                                        sql, re.S):
                found.setdefault(str(path.relative_to(ROOT)), []).append(statement)
    return found


def test_b10_static_no_update_of_an_opportunity_names_current_offer_id():
    """G5-12, proof 1, computed from the tree like STOP GATE C's writer check:
    the Slice 5 UPDATEs of `opportunities` are the three commands', and none
    of their SET clauses names `current_offer_id`. A new writer fails here."""
    found = _updates_of_opportunities()
    assert set(found) == {"src/turab/services/opportunity_commands.py"}
    assert len(found["src/turab/services/opportunity_commands.py"]) == 3
    for statement in found["src/turab/services/opportunity_commands.py"]:
        assert "current_offer_id" not in statement, statement


def test_b10_the_offer_is_never_switched_by_any_command(client, engine, ids):
    """G5-12, proof 2: the evaluated offer is withdrawn while another ACTIVE
    SALE offer of the property exists. Revalidate gives INVALID (§3.7) and
    keeps `current_offer_id`; share is refused and close succeeds, and
    neither changes it."""
    req, prop, [offer_1, offer_2], [m1, _] = _world(client, engine, ids, offers=2)
    _ok(_approve(client, m1["match_id"], ids.ACC_REVIEWER))
    opportunity = _by_match(engine, m1["match_id"])["opportunity_id"]
    assert _row(engine, opportunity)["current_offer_id"] == str(offer_1)
    _set(engine, "UPDATE turab.property_offers SET status = 'WITHDRAWN' WHERE offer_id = :o",
         o=offer_1)
    assert _one(engine, "SELECT status::text FROM turab.property_offers WHERE offer_id = :o",
                o=offer_2) == "ACTIVE"
    body = _ok(_revalidate(client, ids, opportunity))
    assert (body["validity_status"], body["current_offer_id"]) == ("INVALID", str(offer_1))
    assert [(r["fact"], r["value"]) for r in body["validity_reasons"]] == [
        ("OFFER_STATUS", "WITHDRAWN")]
    _refused(client, engine, ids, opportunity, "share", 409, "OPPORTUNITY_NOT_VALID")
    assert _ok(_close(client, ids, opportunity, "PROPERTY_UNAVAILABLE"))[
        "current_offer_id"] == str(offer_1)
    assert _row(engine, opportunity)["current_offer_id"] == str(offer_1)


# ======================================================================================
# G5-11 (a): the opportunity queue
# ======================================================================================

def _queue(client, account):
    r = _get(client, "/backoffice/queues/opportunities", account)
    assert r.status_code == 200, r.text
    return r.json()


def test_the_queue_holds_exactly_the_three_cases_with_their_vocabulary(client, engine, ids):
    new = _fresh(ids, engine, client)
    shared = _fresh(ids, engine, client)
    _ok(_share(client, ids, shared["opportunity"]))
    invalid = _fresh(ids, engine, client)
    _set(engine, "UPDATE turab.properties SET current_availability = 'UNAVAILABLE' "
                 "WHERE property_id = :p", p=invalid["property"])
    _ok(_revalidate(client, ids, invalid["opportunity"]))
    pending = _fresh(ids, engine, client)
    _ok(_share(client, ids, pending["opportunity"]))
    _set(engine, "UPDATE turab.property_offers SET status = 'PAUSED' WHERE offer_id = :o",
         o=pending["offer"])
    _ok(_revalidate(client, ids, pending["opportunity"]))
    closed = _fresh(ids, engine, client)
    _ok(_close(client, ids, closed["opportunity"]))
    closed_invalid = _fresh(ids, engine, client)
    _set(engine, "UPDATE turab.properties SET current_availability = 'UNAVAILABLE' "
                 "WHERE property_id = :p", p=closed_invalid["property"])
    _ok(_revalidate(client, ids, closed_invalid["opportunity"]))
    _ok(_close(client, ids, closed_invalid["opportunity"]))

    page = _queue(client, ids.ACC_REVIEWER)
    _validate(page, SCHEMAS["QueuePage"])
    assert page["next_cursor"] is None
    mine = {w["opportunity"]: name for name, w in (
        ("new", new), ("shared", shared), ("invalid", invalid), ("pending", pending),
        ("closed", closed), ("closed_invalid", closed_invalid))}
    got = {mine[uuid.UUID(i["id"])]: (i["kind"], i["priority"], i["reason"])
           for i in page["items"] if uuid.UUID(i["id"]) in mine}
    assert got == {
        "new": ("OPPORTUNITY", "NORMAL", "NOT_YET_SHARED"),
        "invalid": ("OPPORTUNITY", "HIGH", "VALIDITY_INVALID"),
        "pending": ("OPPORTUNITY", "NORMAL", "VALIDITY_NEEDS_CONFIRMATION"),
    }
    for item in page["items"]:
        assert set(SCHEMAS["QueueItem"]["required"]) <= set(item)


def test_an_unshared_invalid_opportunity_is_high_and_named_by_its_validity(client, engine,
                                                                          ids):
    world = _fresh(ids, engine, client)
    _set(engine, "UPDATE turab.requests SET status = 'CLOSED' WHERE request_id = :r",
         r=world["request"])
    _ok(_revalidate(client, ids, world["opportunity"]))
    [item] = [i for i in _queue(client, ids.ACC_OPERATOR)["items"]
              if i["id"] == str(world["opportunity"])]
    assert (item["priority"], item["reason"], item["status"]) == (
        "HIGH", "VALIDITY_INVALID", "NEW")


def test_the_queue_has_no_time_based_membership(client, engine, ids):
    """G5-11 (a): a shared, VALID opportunity confirmed long ago is not in the
    queue; only stored states are."""
    world = _fresh(ids, engine, client)
    _ok(_share(client, ids, world["opportunity"]))
    _set(engine, "UPDATE turab.opportunities SET last_confirmed_at = now() - "
                 "interval '4000 days', last_activity_at = now() - interval '4000 days' "
                 "WHERE opportunity_id = :o", o=world["opportunity"])
    ids_in = {i["id"] for i in _queue(client, ids.ACC_ADMIN)["items"]}
    assert str(world["opportunity"]) not in ids_in


def test_the_queue_is_ordered_by_priority_then_creation(client, engine, ids):
    first = _fresh(ids, engine, client)
    second = _fresh(ids, engine, client)
    _set(engine, "UPDATE turab.properties SET current_availability = 'UNAVAILABLE' "
                 "WHERE property_id = :p", p=second["property"])
    _ok(_revalidate(client, ids, second["opportunity"]))
    third = _fresh(ids, engine, client)
    items = _queue(client, ids.ACC_ADMIN)["items"]
    order = [i["id"] for i in items]
    assert order.index(str(second["opportunity"])) < order.index(str(first["opportunity"])) \
        < order.index(str(third["opportunity"]))
    ranks = [{"HIGH": 0, "NORMAL": 1}[i["priority"]] for i in items]
    assert ranks == sorted(ranks)
    for a, b in zip(items, items[1:]):
        if a["priority"] == b["priority"]:
            assert (a["created_at"], a["id"]) <= (b["created_at"], b["id"])


def test_the_queue_is_staff_only_and_audited_once(client, engine, ids, sink):
    _fresh(ids, engine, client)
    for account in (ids.ACC_BRAHIM, ids.ACC_AMINA):
        r = _get(client, "/backoffice/queues/opportunities", account)
        assert (r.status_code, r.json()["code"]) == (403, "ROLE_NOT_PERMITTED")
    before = len(sink.records)
    page = _queue(client, ids.ACC_OPERATOR)
    [record] = [r for r in sink.records[before:] if r.event.value == "LIST"]
    assert record.resource_kind == "OPPORTUNITY" and record.resource_id is None
    assert record.result_count == len(page["items"])
