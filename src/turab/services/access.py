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
    STAFF_LOADERS,
    ClaimAuthorityConflict,
    LoadResult,
    ResourceKind,
)
from ..auth.policy import Decision, DenyReason, PolicyTable
from ..auth.roles import Role
from ..auth.subject import Subject
from . import freshness, timeline
from . import requests as request_service


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

    def read_staff_resource(
        self, kind: ResourceKind, resource_id: uuid.UUID, operation_id: str
    ) -> LoadResult:
        """A staff read of an arbitrary object.

        Permitted by role, and RECORDED: RFC-001 R6.2 satisfies the
        business-purpose requirement structurally rather than by asking the
        caller to assert one, and R6.3 makes the read auditable.
        """
        result = STAFF_LOADERS[kind](self._session, self._subject, resource_id)
        if result.authorized:
            self._auditor.read(
                subject=self._subject, operation_id=operation_id,
                trace_id=self._trace_id, resource_kind=kind.value,
                resource_id=result.resource_id,
            )
        else:
            self._auditor.denied(
                subject=self._subject, operation_id=operation_id,
                trace_id=self._trace_id,
                reason_code=(result.reason or DenyReason.OBJECT_NOT_AUTHORIZED).value,
                resource_kind=kind.value, resource_id=resource_id,
            )
        return result

    def read_party_timeline(
        self, party_id: uuid.UUID, operation_id: str, *, page: int, page_size: int
    ) -> LoadResult | timeline.Page:
        """A scoped list: one party's interactions.

        A list about one object still needs that object's gate, so the party
        is loaded through the staff loader first. Without it the endpoint
        would answer "no interactions" for an id that does not exist and for
        an id that does but is empty, and a caller could enumerate parties by
        the difference — or, worse, read a timeline for a party the loader
        would have refused.

        Returns the denial when the gate refuses, and the page when it does
        not. R6.3c: the page is audited once, for the access, never per row.
        """
        gate = STAFF_LOADERS[ResourceKind.PARTY](self._session, self._subject, party_id)
        if not gate.authorized:
            self._auditor.denied(
                subject=self._subject, operation_id=operation_id,
                trace_id=self._trace_id,
                reason_code=(gate.reason or DenyReason.OBJECT_NOT_AUTHORIZED).value,
                resource_kind=ResourceKind.PARTY.value, resource_id=party_id,
            )
            return gate

        page_result = timeline.read_party_timeline(
            self._session, party_id, page=page, page_size=page_size
        )
        self.record_list_access(
            operation_id=operation_id,
            resource_kind="INTERACTION",
            result_count=len(page_result.items),
            query_shape={"party_id": str(party_id), "page": page_result.page,
                         "page_size": page_result.page_size},
        )
        return page_result

    def list_property_relations(
        self, property_id: uuid.UUID, *, include_ended: bool, page: int,
        page_size: int, operation_id: str,
    ):
        """G3-6 retrieve, on the READ session, audited once for the page.

        Staff-only by role (ADMIN, OPERATOR, REVIEWER); a relation is not a
        customer resource and has no loader. Raises the relations service's
        `PropertyNotFound` for an unknown property, which the route maps.
        """
        from . import relations as relation_service

        items, total = relation_service.list_relations(
            self._session, property_id=property_id, include_ended=include_ended,
            page=page, page_size=page_size,
        )
        self.record_list_access(
            operation_id=operation_id,
            resource_kind="PARTY_PROPERTY_RELATION",
            result_count=len(items),
            query_shape={"property_id": str(property_id),
                         "include_ended": include_ended,
                         "page": page, "page_size": page_size},
        )
        return items, total

    def evaluate_request_freshness(self, last_confirmed_at):
        """Freshness as a DERIVED value, computed on the read session.

        Not stored: the contract has no field for it, and a copy of a derived
        value is a second truth that can disagree with `last_confirmed_at`.
        The threshold comes from the active matching policy, never from code
        (Reference Spec §15.1).
        """
        return freshness.evaluate(self._session, last_confirmed_at=last_confirmed_at)

    def request_provenance(self, request_id: uuid.UUID):
        """The change history of a request already cleared by its gate."""
        return request_service.provenance_for(self._session, request_id)

    def request_criteria(self, request_id: uuid.UUID):
        """The structured criteria of a request already cleared by its gate.

        Called only after `read_staff_resource` has authorized the request, so
        it carries no gate of its own — and takes the id it was given rather
        than re-deriving it, so there is no path here that reaches a request
        the caller was not already handed.
        """
        return request_service.criteria_for(self._session, request_id)

    def property_provenance(self, property_id: uuid.UUID):
        """The recorded provenance of a property already cleared by its gate.

        Same contract as `request_criteria`: no gate of its own, because it is
        called only after `read_staff_resource` authorized the property, and it
        takes the id it was given rather than re-deriving one.
        """
        from . import properties as property_service

        return property_service.provenance_for(self._session, property_id)

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
