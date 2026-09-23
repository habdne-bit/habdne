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

from sqlalchemy import text
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
        read_session: Session | None = None,
    ) -> None:
        self._session = session
        # Pre-command object checks query HERE, never on the write session.
        # A SELECT on the write session opens a transaction, and the command
        # must own its transaction outright so the idempotency claim, the work
        # and the stored result commit or roll back as one. `get_subject_for_write`
        # already resolves the actor on the read session for the same reason.
        self._read_session = read_session if read_session is not None else session
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

    @property
    def is_staff(self) -> bool:
        """Any role other than CUSTOMER.

        Deliberately not `roles == {CUSTOMER}`: that phrasing calls a
        role-less subject "staff", and would be load-bearing the day a route
        asked this question before the role gate rather than after it.
        """
        return bool(self._subject.roles - {Role.CUSTOMER})

    def _staff(self) -> bool:
        return self.is_staff

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

    def read_current(self, table: str, resource_id: uuid.UUID, columns):
        """Read named columns on the READ session, for pre-command validation.

        Never the write session: a read there opens the transaction the
        command must own outright (the ordering that produced a 500 on every
        guarded command earlier in Slice 2).
        """
        id_column = {"requests": "request_id", "parties": "party_id"}[table]
        names = ", ".join(columns)
        return self._read_session.execute(
            text(f"SELECT {names} FROM turab.{table} WHERE {id_column} = :id"),
            {"id": resource_id},
        ).mappings().first()

    def authorize_request_scope(self, request_id: uuid.UUID) -> Decision:
        """A CUSTOMER may command only a REQUEST belonging to their own party.

        The party comes from the ACCOUNT's binding, resolved per request
        (R3.2) — never from a phone number, a contact point or any other
        shared attribute (Design Ledger DL-02). Two people on one line reach
        two parties, and neither inherits the other's records.

        Staff are authorized by role and recorded. A customer whose account
        has no party is authorized over nothing, which is the explicit guard
        R3.1 requires rather than a NULL comparison that quietly matches.
        """
        if self.is_staff:
            return ALLOW_DECISION
        owner = self._read_session.execute(
            text("SELECT party_id FROM turab.requests WHERE request_id = :r"),
            {"r": request_id},
        ).scalar_one_or_none()
        if (
            owner is None
            or not self._subject.has_party
            or self._subject.party_id != owner
        ):
            self._auditor.denied(
                subject=self._subject, operation_id="request-scope",
                trace_id=self._trace_id,
                reason_code=DenyReason.OBJECT_NOT_AUTHORIZED.value,
                resource_kind="REQUEST", resource_id=request_id,
            )
            return deny(DenyReason.OBJECT_NOT_AUTHORIZED, "not your request")
        return ALLOW_DECISION

    def _conflict_denial(self, conflict, operation_id: str, message: str) -> Decision:
        """INV-1 on the command path, with the READ path's disclosure rule
        (`AccessService._may_learn_of_conflict`).

        A claimant already knows they claimed the resource and is told it is
        contested; anyone else gets the ordinary concealment. The audit record
        carries the full detail either way. Uncaught, this was a 500.
        """
        entitled = self._subject.account_id in conflict.accounts
        self._auditor.claim_authority_conflict(
            subject=self._subject, operation_id=operation_id,
            trace_id=self._trace_id, resource_kind=conflict.kind.value,
            resource_id=conflict.resource_id, accounts=conflict.accounts,
            disclosed=entitled,
        )
        return deny(DenyReason.CLAIM_AUTHORITY_CONFLICT if entitled
                    else DenyReason.OBJECT_NOT_AUTHORIZED, message)

    def authorize_property_scope(self, property_id: uuid.UUID) -> Decision:
        """A CUSTOMER may command only a PROPERTY they have authority over.

        The rule is R4.1 exactly — the creator account, or a recorded claim
        event for that account — and it is evaluated by reusing
        `load_property`, the same loader the READ path uses, rather than by a
        second query written to the same rule. Two implementations of one
        authority rule is how they come to disagree, and the one that drifts
        is always the one nobody reads.

        Three things follow from using the loader, all of them wanted:
        `party_property_relations` is never consulted (R4.5); an alias
        resolves to its canonical property first (R4.9); and an ambiguous
        claim raises `ClaimAuthorityConflict` so authority goes to nobody
        (INV-1) instead of to whichever account claimed first.

        Staff are authorized by role and recorded, as everywhere else.
        """
        if self.is_staff:
            return ALLOW_DECISION
        from ..auth.loaders import ClaimAuthorityConflict, ResourceKind, load_property

        try:
            result = load_property(self._read_session, self._subject, property_id)
        except ClaimAuthorityConflict as conflict:
            return self._conflict_denial(conflict, "property-scope",
                                         "not your property")
        if not result.authorized:
            self._auditor.denied(
                subject=self._subject, operation_id="property-scope",
                trace_id=self._trace_id,
                reason_code=(result.reason or DenyReason.OBJECT_NOT_AUTHORIZED).value,
                resource_kind=ResourceKind.PROPERTY.value, resource_id=property_id,
            )
            return deny(result.reason or DenyReason.OBJECT_NOT_AUTHORIZED,
                        "not your property")
        return ALLOW_DECISION

    def authorize_offer_scope(self, offer_id: uuid.UUID) -> Decision:
        """A CUSTOMER may command only an OFFER they have authority over.

        RFC-001 §4.6 exactly, by reusing `load_offer` — the one
        implementation of that rule — for the same reason
        `authorize_property_scope` reuses `load_property`: the creator
        account, OR a parent-property claim AND a party match AND a `CLAIMED`
        parent. `offer.party_id` alone never grants (R4.12), and a claim on
        the property never opens another party's offer on it (R4.13).
        """
        if self.is_staff:
            return ALLOW_DECISION
        from ..auth.loaders import ClaimAuthorityConflict, ResourceKind, load_offer

        try:
            result = load_offer(self._read_session, self._subject, offer_id)
        except ClaimAuthorityConflict as conflict:
            # Raised only from condition 2, after the creator branch has
            # already declined: the parent is contested, so a claim on it
            # grants nothing (INV-1).
            return self._conflict_denial(conflict, "offer-scope", "not your offer")
        if not result.authorized:
            self._auditor.denied(
                subject=self._subject, operation_id="offer-scope",
                trace_id=self._trace_id,
                reason_code=(result.reason or DenyReason.OBJECT_NOT_AUTHORIZED).value,
                resource_kind=ResourceKind.OFFER.value, resource_id=offer_id,
            )
            return deny(result.reason or DenyReason.OBJECT_NOT_AUTHORIZED,
                        "not your offer")
        return ALLOW_DECISION

    def authorize_staff_only(self, operation_id: str, reason: str) -> Decision:
        """For commands whose object does not exist yet.

        A create has no object to own, so ownership cannot be the rule; the
        rule is who may perform it at all.

        For `POST /parties` this is now settled at the contract layer too:
        decision D7 / CORRECTION-001 narrows it to ADMIN and OPERATOR, so the
        role gate denies a customer before reaching here. This check remains
        as the second lock, because a customer creating an arbitrary PARTY is
        an unbounded write primitive producing a record with no owner and no
        way to read it back — and a guard that only exists in the contract is
        one edit away from not existing.
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
