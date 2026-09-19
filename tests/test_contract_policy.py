"""Contract/policy conformance and the role rules.

Ref: RFC-001 R10.1, R10.2, R10.3a, R10.4, R2.1-R2.3; decisions 3, 5, 7.
"""
from __future__ import annotations

import pytest

from turab.auth.contract import (
    CONTRACT_ROLE_EXCEPTIONS,
    ContractError,
    build_policy_table,
    load_contract,
    verify_policy_matches_contract,
)
from turab.auth.policy import PUBLIC_OPERATIONS, DenyReason, PolicyTable
from turab.auth.roles import Role, invalid_role_combination


def test_policy_matches_the_frozen_contract(policies):
    """R10.2. Every annotated operation, role for role."""
    verify_policy_matches_contract(policies)


def test_every_contract_operation_has_a_policy(policies):
    doc = load_contract()
    ops = {
        op["operationId"]
        for item in doc["paths"].values()
        for method, op in item.items()
        if method in ("get", "put", "post", "delete", "patch")
    }
    assert ops <= policies.operations(), sorted(ops - policies.operations())


def test_unauthenticated_operations_are_a_closed_list_of_six(policies):
    """R10.4."""
    public = {o for o in policies.operations() if policies.get(o).public}
    assert public == PUBLIC_OPERATIONS
    assert len(public) == 6


def test_reason_codes_is_the_only_role_exception():
    """R10.3a / decision 5."""
    assert set(CONTRACT_ROLE_EXCEPTIONS) == {"getReasonCodes"}
    assert CONTRACT_ROLE_EXCEPTIONS["getReasonCodes"] == frozenset(
        {Role.ADMIN, Role.OPERATOR, Role.REVIEWER}
    )
    assert Role.CUSTOMER not in CONTRACT_ROLE_EXCEPTIONS["getReasonCodes"]


def test_unknown_operation_is_denied(policies, subject_of, ids):
    """S38 / R10.1. Deny by default: no policy entry, no access."""
    subject = subject_of(ids.ACC_ADMIN)
    decision = policies.check_role("someOperationThatDoesNotExist", subject)
    assert not decision.allowed
    assert decision.reason is DenyReason.NO_POLICY


def test_empty_policy_table_denies_everything(subject_of, ids):
    """The fail-closed property does not depend on the table being populated."""
    subject = subject_of(ids.ACC_ADMIN)
    assert not PolicyTable({}).check_role("getMeParty", subject).allowed


def test_roles_are_literal_with_no_inheritance(policies, subject_of, ids):
    """S18-S21 / decision 3. The maker-checker split must hold exactly."""
    operator = subject_of(ids.ACC_OPERATOR)
    reviewer = subject_of(ids.ACC_REVIEWER)
    admin = subject_of(ids.ACC_ADMIN)

    # OPERATOR records truth but cannot approve a match.
    assert not policies.check_role("postMatchesMatchIdReview", operator).allowed
    assert policies.check_role("postObservations", operator).allowed
    # REVIEWER approves but does not enter data, nor perform the outward share.
    assert policies.check_role("postMatchesMatchIdReview", reviewer).allowed
    assert not policies.check_role("postObservations", reviewer).allowed
    assert not policies.check_role("postOpportunitiesOpportunityIdShare", reviewer).allowed
    # /audit is REVIEWER's, not OPERATOR's.
    assert policies.check_role("getAudit", reviewer).allowed
    assert not policies.check_role("getAudit", operator).allowed
    # ADMIN is admitted because the contract lists it, not by inheritance.
    assert policies.check_role("postMatchesMatchIdReview", admin).allowed
    assert policies.check_role("postObservations", admin).allowed


def test_customer_is_refused_reason_codes_and_staff_allowed(policies, subject_of, ids):
    """S21b / S21c, decision 5."""
    assert not policies.check_role("getReasonCodes", subject_of(ids.ACC_AMINA)).allowed
    for account in (ids.ACC_OPERATOR, ids.ACC_REVIEWER, ids.ACC_ADMIN):
        assert policies.check_role("getReasonCodes", subject_of(account)).allowed


def test_customer_cannot_use_internal_endpoints(policies, subject_of, ids):
    """S03 / K01. Own object, wrong endpoint, still refused."""
    customer = subject_of(ids.ACC_AMINA)
    for op in ("getRequestsRequestId", "getPartiesPartyId", "getPropertiesPropertyId"):
        decision = policies.check_role(op, customer)
        assert not decision.allowed
        assert decision.reason is DenyReason.ROLE_NOT_PERMITTED


def test_staff_cannot_use_me_endpoints(policies, subject_of, ids):
    """R5.4 / R3.3. A staff role never widens /me/*."""
    operator = subject_of(ids.ACC_OPERATOR)
    for op in ("getMeParty", "getMeRequestsRequestId"):
        assert not policies.check_role(op, operator).allowed


def test_invalid_role_combination_detection():
    """INV-2 / R2.1-R2.2."""
    assert invalid_role_combination(frozenset({Role.OPERATOR, Role.REVIEWER})) == frozenset(
        {Role.OPERATOR, Role.REVIEWER}
    )
    assert invalid_role_combination(frozenset({Role.ADMIN, Role.OPERATOR})) is None
    assert invalid_role_combination(frozenset({Role.CUSTOMER, Role.OPERATOR})) is None
    # ADMIN does not rescue the pair: the split is still collapsed.
    assert invalid_role_combination(
        frozenset({Role.ADMIN, Role.OPERATOR, Role.REVIEWER})
    ) == frozenset({Role.OPERATOR, Role.REVIEWER})


def test_separation_sensitive_operations_all_exist(policies):
    """INV-2 guard: a misspelled operationId would make the invariant inert."""
    from turab.auth.roles import (
        SEPARATION_SENSITIVE_OPERATIONS,
        verify_separation_sensitive_operations,
    )

    verify_separation_sensitive_operations(policies.operations())
    assert SEPARATION_SENSITIVE_OPERATIONS <= policies.operations()

    with pytest.raises(ValueError, match="absent from the contract"):
        verify_separation_sensitive_operations(frozenset({"getAudit"}))
