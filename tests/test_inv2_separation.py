"""INV-2 — OPERATOR + REVIEWER is invalid configuration.

Half one: rejected at role-assignment time.
Half two: when found in existing data, separation-sensitive actions fail closed
          and the anomaly is audited.
"""
from __future__ import annotations

import pytest
from sqlalchemy import text

from turab.auth.audit import AccessEvent
from turab.auth.policy import DenyReason
from turab.auth.roles import Role
from turab.auth.subject import resolve_subject
from turab.services.roles import (
    InvalidRoleCombination,
    find_role_anomalies,
    grant_role,
)


def _force_both_roles(session, account_id):
    """Write the invalid combination directly, as legacy data would have it."""
    for role in ("OPERATOR", "REVIEWER"):
        session.execute(
            text(
                """INSERT INTO turab.user_account_roles (account_id, role)
                   VALUES (:a, :r) ON CONFLICT DO NOTHING"""
            ),
            {"a": account_id, "r": role},
        )


# --- half one: assignment time --------------------------------------------

def test_granting_reviewer_to_an_operator_is_rejected(session, ids):
    """S21a."""
    with pytest.raises(InvalidRoleCombination) as exc:
        grant_role(session, ids.ACC_OPERATOR, Role.REVIEWER)
    assert exc.value.offending == frozenset({Role.OPERATOR, Role.REVIEWER})


def test_granting_operator_to_a_reviewer_is_rejected(session, ids):
    with pytest.raises(InvalidRoleCombination):
        grant_role(session, ids.ACC_REVIEWER, Role.OPERATOR)


def test_rejected_grant_writes_nothing(session, ids):
    before = session.execute(
        text("SELECT count(*) FROM turab.user_account_roles WHERE account_id=:a"),
        {"a": ids.ACC_OPERATOR},
    ).scalar_one()
    with pytest.raises(InvalidRoleCombination):
        grant_role(session, ids.ACC_OPERATOR, Role.REVIEWER)
    after = session.execute(
        text("SELECT count(*) FROM turab.user_account_roles WHERE account_id=:a"),
        {"a": ids.ACC_OPERATOR},
    ).scalar_one()
    assert after == before


def test_valid_grants_are_allowed(session, ids):
    assert Role.CUSTOMER in grant_role(session, ids.ACC_OPERATOR, Role.CUSTOMER)
    assert Role.ADMIN in grant_role(session, ids.ACC_OPERATOR, Role.ADMIN)


def test_the_fixture_data_holds_no_anomaly(session):
    """The fixtures assert this too; here it is checked through the service."""
    assert find_role_anomalies(session) == []


# --- half two: existing data ----------------------------------------------

def test_anomaly_in_existing_data_is_detected(session, ids):
    _force_both_roles(session, ids.ACC_ADMIN)
    anomalies = find_role_anomalies(session)
    assert [a for a, _ in anomalies] == [ids.ACC_ADMIN]


def test_subject_carries_the_anomaly(session, ids):
    _force_both_roles(session, ids.ACC_ADMIN)
    subject = resolve_subject(session, ids.ACC_ADMIN)
    assert subject.role_anomaly == frozenset({Role.OPERATOR, Role.REVIEWER})


@pytest.mark.parametrize(
    "operation_id",
    [
        "postMatchesMatchIdReview",
        "postIdentityCandidatesCandidateIdReview",
        "postObservations",
        "postClaims",
        "postOpportunitiesOpportunityIdShare",
        "getAudit",
    ],
)
def test_separation_sensitive_actions_fail_closed(session, ids, policies, operation_id):
    """INV-2. The role check would otherwise pass — ADMIN is on all of these."""
    _force_both_roles(session, ids.ACC_ADMIN)
    subject = resolve_subject(session, ids.ACC_ADMIN)
    assert subject.has_any_role(policies.get(operation_id).roles)  # would pass...
    decision = policies.check_role(operation_id, subject)
    assert not decision.allowed  # ...and is refused anyway
    assert decision.reason is DenyReason.ROLE_CONFIGURATION_ANOMALY


def test_non_sensitive_operations_still_work_under_an_anomaly(session, ids, policies):
    """Fail closed where the split matters; do not brick the account entirely."""
    _force_both_roles(session, ids.ACC_ADMIN)
    subject = resolve_subject(session, ids.ACC_ADMIN)
    assert policies.check_role("getReasonCodes", subject).allowed
    assert policies.check_role("getRequestsRequestId", subject).allowed


def test_the_anomaly_is_audited(session, ids, access_for, auditor):
    _force_both_roles(session, ids.ACC_ADMIN)
    subject = resolve_subject(session, ids.ACC_ADMIN)
    access = access_for(subject)
    decision = access.authorize_operation("postMatchesMatchIdReview")
    assert not decision.allowed

    records = auditor.sink.of(AccessEvent.ROLE_CONFIGURATION_ANOMALY)
    assert len(records) == 1
    assert records[0].reason_code == "ROLE_CONFIGURATION_ANOMALY"
    assert records[0].extra["offending_roles"] == ["OPERATOR", "REVIEWER"]
