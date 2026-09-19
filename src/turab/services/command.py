"""The mutating-command boundary.

Ref: API_CONTRACTS v0.2 §2.3 (idempotency), §2.4 (concurrency), §2.6
(transaction boundaries); RFC-001 R6.2, R10.3.

Slice 0 built idempotency and optimistic concurrency as services and left them
unwired, because the 34 idempotent and 4 version-checked operations were all
domain commands that did not exist yet. Slice 1 introduces the first of them,
so this is where they are applied.

A command runs in ONE transaction that carries the audit actor. Either the
whole command lands or none of it does: §2.6 says partial updates are
unacceptable, and that is enforced by structure rather than by cleanup.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable

from sqlalchemy.orm import Session

from ..auth.audit import AccessAuditor
from ..auth.policy import ALLOW as ALLOW_DECISION
from ..auth.policy import Decision, DenyReason, PolicyTable, deny
from ..auth.roles import Role
from ..auth.subject import Subject
from ..db.session import audited_transaction
from . import idempotency
from .concurrency import StaleVersion, check as check_version


@dataclass(frozen=True, slots=True)
class CommandResult:
    status: int
    body: dict[str, Any] | None
    replayed: bool = False


class CommandService:
    """Runs one mutating command: role gate, idempotency, transaction, audit.

    Routes receive this and never a session, which keeps the structural
    guarantee of RFC-001 R10.3 intact for write paths as well as reads.
    """

    def __init__(
        self,
        session: Session,
        subject: Subject,
        policies: PolicyTable,
        auditor: AccessAuditor,
        trace_id: str,
        idempotency_key: str | None = None,
    ) -> None:
        self._session = session
        self._subject = subject
        self._policies = policies
        self._auditor = auditor
        self._trace_id = trace_id
        self._idempotency_key = idempotency_key

    @property
    def subject(self) -> Subject:
        return self._subject

    @property
    def trace_id(self) -> str:
        return self._trace_id

    def authorize(self, operation_id: str) -> Decision:
        decision = self._policies.check_role(operation_id, self._subject)
        if decision.allowed:
            return decision
        if decision.reason is DenyReason.ROLE_CONFIGURATION_ANOMALY:
            self._auditor.role_configuration_anomaly(
                subject=self._subject, operation_id=operation_id,
                trace_id=self._trace_id,
                offending=self._subject.role_anomaly or frozenset(),
            )
        else:
            self._auditor.denied(
                subject=self._subject, operation_id=operation_id,
                trace_id=self._trace_id,
                reason_code=decision.reason.value if decision.reason else "DENY",
            )
        return decision

    # ------------------------------------------------------------------
    # Object authorization for commands
    # ------------------------------------------------------------------
    #
    # The read paths get their object check from the scoped loaders: a loader
    # cannot return a row the caller may not see. A command has no loader, so
    # the check has to be made explicitly — and that is exactly the kind of
    # step that gets forgotten, so an architecture test asserts every command
    # route calls one of these before it runs.

    def _staff(self) -> bool:
        return bool(self._subject.roles - {Role.CUSTOMER})

    def authorize_party_scope(self, party_id: uuid.UUID) -> Decision:
        """A CUSTOMER may act only on their own party (RFC-001 §4, decision 4).

        Staff are authorized by role and recorded; a customer must BE the
        party. Without this a customer could patch, re-phone or grant consent
        on any party id they could guess, which is precisely K01/K02.
        """
        if self._staff():
            return ALLOW_DECISION
        if not self._subject.has_party or self._subject.party_id != party_id:
            self._auditor.denied(
                subject=self._subject, operation_id="party-scope",
                trace_id=self._trace_id,
                reason_code=DenyReason.OBJECT_NOT_AUTHORIZED.value,
                resource_kind="PARTY", resource_id=party_id,
            )
            return deny(DenyReason.OBJECT_NOT_AUTHORIZED, "not your party")
        return ALLOW_DECISION

    def authorize_staff_only(self, operation_id: str, reason: str) -> Decision:
        """For commands whose object does not exist yet.

        `POST /parties` lists CUSTOMER in x-roles, but a create has no object
        to own, and Slice 1's deliverable is "create/read/update PARTY **for
        staff**". Self-service party creation belongs to Slice 8, which defines
        that flow; until then a customer creating an arbitrary PARTY is an
        unbounded write primitive producing a record with no owner and no way
        to read it back. The role check still passes, and the OBJECT check
        denies — which is what the contract's x-authorization demands.
        """
        if self._staff():
            return ALLOW_DECISION
        self._auditor.denied(
            subject=self._subject, operation_id=operation_id,
            trace_id=self._trace_id,
            reason_code=DenyReason.OBJECT_NOT_AUTHORIZED.value,
        )
        return deny(DenyReason.OBJECT_NOT_AUTHORIZED, reason)

    def run(
        self,
        *,
        operation_id: str,
        route_key: str,
        payload: Any,
        handler: Callable[[Session], tuple[int, dict[str, Any] | None]],
        success_status: int = 200,
        version_guard: tuple[str, uuid.UUID, int] | None = None,
    ) -> CommandResult:
        """Execute, or replay an identical earlier call.

        Idempotency applies only where the contract declares Idempotency-Key.
        The four PATCH operations declare If-Match-Version instead: a
        version-checked update is already idempotent, since a replay would
        carry a version that is no longer current.

        `version_guard` is checked INSIDE the transaction and before the
        handler runs, so a stale version applies nothing at all (§2.4).
        """
        policy = self._policies.get(operation_id)
        use_idempotency = policy.requires_idempotency if policy else True
        with audited_transaction(
            self._session,
            self._subject.account_id,
            {"operation": operation_id, "trace_id": self._trace_id},
        ) as session:
            # Claimed inside the transaction, so a command that fails does not
            # burn its key and a retry is treated as new, which is correct:
            # nothing happened.
            if use_idempotency:
                outcome, replay = idempotency.begin(
                    session,
                    actor_account_id=self._subject.account_id,
                    route_key=route_key,
                    idempotency_key=self._idempotency_key,
                    payload=payload,
                )
                if outcome is idempotency.IdempotencyOutcome.REPLAYED and replay:
                    return CommandResult(replay.status, replay.body, replayed=True)

            if version_guard is not None:
                table, resource_id, expected = version_guard
                check_version(session, table, resource_id, expected)

            status, body = handler(session)

            if use_idempotency:
                idempotency.complete(
                    session,
                    actor_account_id=self._subject.account_id,
                    route_key=route_key,
                    idempotency_key=self._idempotency_key or "",
                    status=status or success_status,
                    body=body,
                )
        return CommandResult(status or success_status, body)


__all__ = ["CommandResult", "CommandService", "StaleVersion"]
