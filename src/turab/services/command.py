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
from ..auth.policy import Decision, DenyReason, PolicyTable
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
