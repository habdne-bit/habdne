"""The policy layer — role gate, deny-by-default, and the contract cross-check.

Ref: RFC-001 §10 (R10.1-R10.4), §2, §12; decisions 3, 5, 7; INV-2.

This module is deliberately free of HTTP and of any database session. It takes
a subject and a reference to a resource and returns a decision, so every
scenario in RFC-001 §11 is testable without a running server (R14.8).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from .roles import SEPARATION_SENSITIVE_OPERATIONS, Role


class Effect(StrEnum):
    ALLOW = "ALLOW"
    DENY = "DENY"


class DenyReason(StrEnum):
    """Stable codes. §12 maps these to HTTP status and problem `code`."""

    NO_POLICY = "NO_POLICY"
    ACCOUNT_NOT_USABLE = "ACCOUNT_NOT_USABLE"
    ROLE_NOT_PERMITTED = "ROLE_NOT_PERMITTED"
    ROLE_CONFIGURATION_ANOMALY = "ROLE_CONFIGURATION_ANOMALY"
    NO_PARTY = "NO_PARTY"
    OBJECT_NOT_AUTHORIZED = "OBJECT_NOT_AUTHORIZED"
    CLAIM_AUTHORITY_CONFLICT = "CLAIM_AUTHORITY_CONFLICT"


@dataclass(frozen=True, slots=True)
class Decision:
    effect: Effect
    reason: DenyReason | None = None
    detail: str | None = None

    @property
    def allowed(self) -> bool:
        return self.effect is Effect.ALLOW


ALLOW: Final = Decision(Effect.ALLOW)


def deny(reason: DenyReason, detail: str | None = None) -> Decision:
    return Decision(Effect.DENY, reason, detail)


@dataclass(frozen=True, slots=True)
class RoutePolicy:
    """One row of the policy table."""

    operation_id: str
    method: str
    path: str
    roles: frozenset[Role]
    #: True for the closed list of unauthenticated operations (R10.4).
    public: bool = False
    #: True when the route is under /me/*, which changes concealment (R5.3).
    customer_scoped: bool = False
    #: Derived from the contract's parameters, never hardcoded: 34 operations
    #: declare Idempotency-Key and 4 declare If-Match-Version, and which is
    #: which is the contract's business, not ours.
    requires_idempotency: bool = False
    requires_if_match: bool = False


#: R10.4. The closed list of unauthenticated operations. Anything else lacking
#: `security` in the contract is a defect, asserted by test.
PUBLIC_OPERATIONS: Final[frozenset[str]] = frozenset(
    {
        "getLocations",
        "getMasterCriterionDefinitions",
        "getPublicProperties",
        "postAuthOtpStart",
        "postAuthOtpVerify",
        "postWebhooksWhatsapp",
    }
)

#: R10.3a / decision 5. The single authenticated operation the frozen contract
#: leaves without `x-roles`. Named here as an explicit exception so the
#: cross-check can treat it as intentional rather than drift, and assert it is
#: the ONLY such exception.
CONTRACT_ROLE_EXCEPTIONS: Final[dict[str, frozenset[Role]]] = {
    "getReasonCodes": frozenset({Role.ADMIN, Role.OPERATOR, Role.REVIEWER}),
}


class PolicyTable:
    """Keyed by operationId. A request matching no entry is denied (R10.1)."""

    def __init__(self, policies: dict[str, RoutePolicy]) -> None:
        self._by_operation = dict(policies)

    def __len__(self) -> int:
        return len(self._by_operation)

    def __contains__(self, operation_id: object) -> bool:
        return operation_id in self._by_operation

    def get(self, operation_id: str) -> RoutePolicy | None:
        return self._by_operation.get(operation_id)

    def operations(self) -> frozenset[str]:
        return frozenset(self._by_operation)

    def check_role(self, operation_id: str, subject) -> Decision:
        """Stages 3, 4 and the INV-2 gate of the §10 pipeline.

        Object authorization is NOT performed here: it needs the database and
        lives in the scoped loaders (§10 stage 6).
        """
        policy = self.get(operation_id)
        if policy is None:
            # R10.1. Fail closed: an endpoint with no policy is unreachable.
            return deny(DenyReason.NO_POLICY, f"no policy for {operation_id!r}")

        if policy.public:
            return ALLOW

        if not subject.is_usable:
            return deny(DenyReason.ACCOUNT_NOT_USABLE, subject.account_status)

        # INV-2. An invalid role combination fails closed for the operations
        # whose purpose is the maker-checker split, even where the role check
        # would otherwise pass. The anomaly is audited by the caller.
        if subject.role_anomaly and operation_id in SEPARATION_SENSITIVE_OPERATIONS:
            offending = "+".join(sorted(r.value for r in subject.role_anomaly))
            return deny(DenyReason.ROLE_CONFIGURATION_ANOMALY, offending)

        if not subject.has_any_role(policy.roles):
            return deny(
                DenyReason.ROLE_NOT_PERMITTED,
                f"{operation_id} requires one of "
                f"{sorted(r.value for r in policy.roles)}",
            )

        # R3.1. A customer reaching a customer-scoped route with no party can
        # never satisfy an ownership predicate; refuse before touching the row.
        if policy.customer_scoped and not subject.has_party:
            return deny(DenyReason.NO_PARTY, "account has no party")

        return ALLOW
