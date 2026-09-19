"""Roles and the separation-of-duties invariant.

Ref: RFC-001 §2, §2.1, R2.1-R2.3; implementation invariant INV-2.
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    """`account_role` in the frozen schema. Closed set, flat, non-hierarchical."""

    ADMIN = "ADMIN"
    OPERATOR = "OPERATOR"
    REVIEWER = "REVIEWER"
    CUSTOMER = "CUSTOMER"


#: RFC-001 R2.3 / decision 3. Roles are evaluated by literal set intersection.
#: There is deliberately no ordering, no superset map and no `implies()` here:
#: computing ADMIN as a superset would silently hand OPERATOR the match-review
#: authority that §2.1 withholds from it.

#: INV-2. Holding both sides of the maker-checker split is invalid configuration.
#: ADMIN is exempt: the frozen contract lists it on both sides.
INCOMPATIBLE_ROLE_PAIRS: frozenset[frozenset[Role]] = frozenset(
    {frozenset({Role.OPERATOR, Role.REVIEWER})}
)

#: Operations whose whole point is the split. When an actor's roles are an
#: invalid combination, these fail closed even if a role check would pass.
#: These names are operationIds from the frozen contract. A misspelling here
#: would silently disable INV-2 rather than fail, so `verify_separation_
#: sensitive_operations` asserts every one of them exists in the contract.
SEPARATION_SENSITIVE_OPERATIONS: frozenset[str] = frozenset(
    {
        "postMatchesMatchIdReview",
        "postIdentityCandidatesCandidateIdReview",
        "postObservations",
        "postClaims",
        "postOpportunitiesOpportunityIdShare",
        "getAudit",
    }
)


def invalid_role_combination(roles: frozenset[Role]) -> frozenset[Role] | None:
    """Return the offending pair when `roles` is an invalid combination.

    ADMIN does not rescue an invalid pair: an account holding ADMIN, OPERATOR
    and REVIEWER still collapses the split for the OPERATOR/REVIEWER work it
    does, so the anomaly is reported and INV-2 fails closed.
    """
    for pair in INCOMPATIBLE_ROLE_PAIRS:
        if pair <= roles:
            return frozenset(pair)
    return None


def verify_separation_sensitive_operations(known_operation_ids: frozenset[str]) -> None:
    """Assert every separation-sensitive name is a real contract operation.

    INV-2 fails closed only for operations it can name. A typo would make the
    invariant quietly inert, which is worse than a loud error at startup.
    """
    unknown = SEPARATION_SENSITIVE_OPERATIONS - known_operation_ids
    if unknown:
        raise ValueError(
            "SEPARATION_SENSITIVE_OPERATIONS names operations absent from the "
            f"contract: {sorted(unknown)}"
        )
