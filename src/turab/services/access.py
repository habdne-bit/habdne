"""The application service routes talk to.

Ref: RFC-001 R10.3 (structural enforcement), R14.8, Q4 audit rules, INV-1/INV-2.

This is the only thing a route is given. It owns the session; the route never
sees one. That is the structural half of Q6: a route that cannot reach a
session cannot issue an unscoped query, whatever the query is called.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.orm import Session

from ..auth.audit import AccessAuditor
from ..auth.loaders import (
    LOADERS,
    ClaimAuthorityConflict,
    LoadResult,
    ResourceKind,
)
from ..auth.policy import Decision, DenyReason, PolicyTable
from ..auth.roles import Role
from ..auth.subject import Subject


@dataclass(frozen=True, slots=True)
class AccessDenied:
    reason: DenyReason
    detail: str | None = None


class AccessService:
    """Role gate, scoped load, and the audit each outcome requires."""

    def __init__(
        self,
        session: Session,
        subject: Subject,
        policies: PolicyTable,
        auditor: AccessAuditor,
        trace_id: str,
    ) -> None:
        self._session = session
        self._subject = subject
        self._policies = policies
        self._auditor = auditor
        self._trace_id = trace_id

    @property
    def subject(self) -> Subject:
        return self._subject

    def authorize_operation(self, operation_id: str) -> Decision:
        """Stages 3-4 plus the INV-2 gate, auditing every denial."""
        decision = self._policies.check_role(operation_id, self._subject)
        if decision.allowed:
            return decision

        if decision.reason is DenyReason.ROLE_CONFIGURATION_ANOMALY:
            # INV-2: the anomaly itself is the finding, not just the denial.
            self._auditor.role_configuration_anomaly(
                subject=self._subject,
                operation_id=operation_id,
                trace_id=self._trace_id,
                offending=self._subject.role_anomaly or frozenset(),
            )
        else:
            self._auditor.denied(
                subject=self._subject,
                operation_id=operation_id,
                trace_id=self._trace_id,
                reason_code=decision.reason.value if decision.reason else "DENY",
            )
        return decision

    def _may_learn_of_conflict(self, conflict: ClaimAuthorityConflict) -> bool:
        """Who may be told that a claim conflict exists.

        A known conflicting claimant already knows they claimed the resource,
        so confirming that the claim is contested tells them nothing they could
        not infer, and leaves them able to act on it. Authorized staff need it
        to resolve the condition. Everyone else is an unrelated actor and gets
        the ordinary concealment.

        This says only WHETHER a conflict exists. The other claimant's identity
        and the conflict's details never leave the audit record.
        """
        if self._subject.account_id in conflict.accounts:
            return True
        return bool(self._subject.roles - {Role.CUSTOMER})

    def read_resource(
        self, kind: ResourceKind, resource_id: uuid.UUID, operation_id: str
    ) -> LoadResult:
        """Load one resource through its actor-scoped loader.

        Routes call this; they never call a loader directly, so the audit below
        cannot be skipped by forgetting it at a call site.
        """
        loader = LOADERS[kind]
        try:
            result = loader(self._session, self._subject, resource_id)
        except ClaimAuthorityConflict as conflict:
            # INV-1. The condition is always explicit INTERNALLY: the audit
            # record below carries the full detail for operations regardless of
            # what the caller is told.
            entitled = self._may_learn_of_conflict(conflict)
            self._auditor.claim_authority_conflict(
                subject=self._subject,
                operation_id=operation_id,
                trace_id=self._trace_id,
                resource_kind=conflict.kind.value,
                resource_id=conflict.resource_id,
                accounts=conflict.accounts,
                disclosed=entitled,
            )
            if not entitled:
                # An unrelated actor learns nothing: a 409 here would reveal
                # that the id exists and that something notable is true of it,
                # which is the disclosure /me/* concealment exists to prevent.
                return LoadResult(
                    kind, resource_id, None, DenyReason.OBJECT_NOT_AUTHORIZED,
                )
            return LoadResult(
                kind, resource_id, None, DenyReason.CLAIM_AUTHORITY_CONFLICT,
            )

        if result.authorized:
            self._auditor.read(
                subject=self._subject,
                operation_id=operation_id,
                trace_id=self._trace_id,
                resource_kind=kind.value,
                resource_id=result.resource_id,
            )
        else:
            self._auditor.denied(
                subject=self._subject,
                operation_id=operation_id,
                trace_id=self._trace_id,
                reason_code=(result.reason or DenyReason.OBJECT_NOT_AUTHORIZED).value,
                resource_kind=kind.value,
                resource_id=resource_id,
            )
        return result

    def record_list_access(
        self, *, operation_id: str, resource_kind: str, result_count: int,
        query_shape: dict | None = None,
    ) -> None:
        """R6.3c. One record for the whole list."""
        self._auditor.list_access(
            subject=self._subject,
            operation_id=operation_id,
            trace_id=self._trace_id,
            resource_kind=resource_kind,
            result_count=result_count,
            query_shape=query_shape,
        )
