"""The audited transaction wrapper.

Ref: RFC-001 R6.2, S23; Slice 0 deliverable "transaction wrapper setting
app.account_id and audit context".
"""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from turab.db.session import MissingAuditActor, audited_transaction


@pytest.fixture
def plain_session(engine):
    s = Session(bind=engine, expire_on_commit=False, future=True)
    yield s
    s.close()


def test_write_without_an_actor_is_refused(plain_session, ids):
    """S23. Refused rather than recorded anonymously."""
    with pytest.raises(MissingAuditActor):
        with audited_transaction(plain_session, None):
            pass


def test_actor_and_context_are_visible_to_the_audit_trigger(plain_session, ids):
    with audited_transaction(
        plain_session, ids.ACC_OPERATOR, {"operation": "test", "trace_id": "t1"}
    ) as s:
        actor = s.execute(text("SELECT current_setting('app.account_id', true)")).scalar_one()
        ctx = s.execute(text("SELECT current_setting('app.audit_context', true)")).scalar_one()
        assert actor == str(ids.ACC_OPERATOR)
        assert "trace_id" in ctx
        s.rollback()


def test_a_write_inside_the_wrapper_is_attributed(plain_session, ids):
    """audit_row_change() reads app.account_id; prove it lands in audit_log."""
    party_id = uuid.uuid4()
    with audited_transaction(plain_session, ids.ACC_OPERATOR, {"op": "test"}) as s:
        s.execute(
            text(
                """INSERT INTO turab.parties (party_id, kind, status, display_name)
                   VALUES (:p, 'PERSON', 'DISCOVERED', 'audit probe')"""
            ),
            {"p": party_id},
        )
        s.execute(
            text(
                """INSERT INTO turab.requests
                     (request_id, party_id, management_mode, claim_status)
                   VALUES (:r, :p, 'ASSISTED', 'UNCLAIMED')"""
            ),
            {"r": uuid.uuid4(), "p": party_id},
        )
        actor = s.execute(
            text(
                """SELECT actor_account_id FROM turab.audit_log
                    WHERE entity_table = 'requests'
                    ORDER BY occurred_at DESC LIMIT 1"""
            )
        ).scalar_one()
        assert actor == ids.ACC_OPERATOR
        s.rollback()
