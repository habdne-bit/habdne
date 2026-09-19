"""Access auditing — reads, denials and configuration anomalies.

Ref: RFC-001 R6.3-R6.3d (Q4), INV-1, INV-2.

`audit_row_change()` in the frozen schema covers INSERT/UPDATE/DELETE only, so
read access is emitted here as a structured application record. These are NOT
`audit_log` rows: that table's shape is row-change specific (R6.3d).

R6.3b is the rule that matters most: a record carries REFERENCES, never
content. An audit trail that copies what it protects relocates the leak instead
of preventing it.
"""
from __future__ import annotations

import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, Protocol

logger = logging.getLogger("turab.audit.access")


class AccessEvent(StrEnum):
    READ = "READ"
    LIST = "LIST"
    DENIED = "DENIED"
    CLAIM_AUTHORITY_CONFLICT = "CLAIM_AUTHORITY_CONFLICT"
    ROLE_CONFIGURATION_ANOMALY = "ROLE_CONFIGURATION_ANOMALY"


#: R6.3b. Keys that must never appear in audit metadata. Enforced, not merely
#: documented: a future caller passing one of these fails the emit.
FORBIDDEN_METADATA_KEYS: frozenset[str] = frozenset(
    {
        "seller_expectation_dzd",
        "asking_price_dzd",
        "claimed_value",
        "raw_text",
        "payload",
        "external_url",
        "external_ref",
        "notes",
        "staff_notes",
        "why_real",
        "otp",
        "otp_code",
        "code",
        "document",
        "metadata",
        "request_snapshot",
        "property_snapshot",
        "commercial_context_snapshot",
        "permission_snapshot",
        "dto",
        "body",
        "response",
    }
)


class AuditMetadataViolation(RuntimeError):
    """Audit metadata tried to carry a sensitive payload (R6.3b)."""


@dataclass(frozen=True, slots=True)
class AccessRecord:
    """References only: who, what, which decision, when. Never content."""

    event: AccessEvent
    occurred_at: datetime
    trace_id: str
    actor_account_id: uuid.UUID | None
    actor_roles: tuple[str, ...]
    operation_id: str
    resource_kind: str | None = None
    resource_id: uuid.UUID | None = None
    decision: str = "ALLOW"
    reason_code: str | None = None
    result_count: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["occurred_at"] = self.occurred_at.isoformat()
        d["actor_account_id"] = str(self.actor_account_id) if self.actor_account_id else None
        d["resource_id"] = str(self.resource_id) if self.resource_id else None
        return d


class AccessAuditSink(Protocol):
    def emit(self, record: AccessRecord) -> None: ...


class LoggingAuditSink:
    """Default sink: the structured log stream.

    R6.3d leaves the destination open as a non-blocking implementation detail.
    The rules above hold whichever sink is used, so swapping in a table-backed
    sink later changes no call site.
    """

    def emit(self, record: AccessRecord) -> None:
        logger.info("access", extra={"access_record": record.as_dict()})


class RecordingAuditSink:
    """In-memory sink for tests."""

    def __init__(self) -> None:
        self.records: list[AccessRecord] = []

    def emit(self, record: AccessRecord) -> None:
        self.records.append(record)

    def of(self, event: AccessEvent) -> list[AccessRecord]:
        return [r for r in self.records if r.event is event]

    def clear(self) -> None:
        self.records.clear()


#: R6.3. Public and master-data reads need no per-resource read audit.
NON_AUDITED_READ_OPERATIONS: frozenset[str] = frozenset(
    {
        "getLocations",
        "getMasterCriterionDefinitions",
        "getPublicProperties",
        "getReasonCodes",
    }
)


def _check_metadata(extra: dict[str, Any]) -> None:
    offending = sorted(set(extra) & FORBIDDEN_METADATA_KEYS)
    if offending:
        raise AuditMetadataViolation(
            f"audit metadata may not carry {offending}: access records hold "
            "references, not content (RFC-001 R6.3b)"
        )


class AccessAuditor:
    """Emits the access records RFC-001 R6.3 requires."""

    def __init__(self, sink: AccessAuditSink | None = None) -> None:
        self.sink = sink or LoggingAuditSink()

    def _emit(self, **kwargs: Any) -> AccessRecord:
        extra = kwargs.pop("extra", None) or {}
        _check_metadata(extra)
        record = AccessRecord(occurred_at=datetime.now(UTC), extra=extra, **kwargs)
        self.sink.emit(record)
        return record

    @staticmethod
    def _roles(subject) -> tuple[str, ...]:
        return tuple(sorted(r.value for r in subject.roles)) if subject else ()

    def read(
        self, *, subject, operation_id: str, trace_id: str,
        resource_kind: str, resource_id: uuid.UUID, sensitive: bool = True,
    ) -> AccessRecord | None:
        """Successful STAFF read of a sensitive, non-public individual resource.

        A customer reading their own resource is not audited as a staff read:
        Q4 names staff reads specifically, and auditing every customer self-read
        would bury the staff access that the control exists to make visible.
        """
        if operation_id in NON_AUDITED_READ_OPERATIONS or not sensitive:
            return None
        from .roles import Role

        if not (subject.roles - {Role.CUSTOMER}):
            return None
        return self._emit(
            event=AccessEvent.READ,
            trace_id=trace_id,
            actor_account_id=subject.account_id,
            actor_roles=self._roles(subject),
            operation_id=operation_id,
            resource_kind=resource_kind,
            resource_id=resource_id,
            decision="ALLOW",
        )

    def list_access(
        self, *, subject, operation_id: str, trace_id: str,
        resource_kind: str, result_count: int, query_shape: dict[str, Any] | None = None,
    ) -> AccessRecord | None:
        """R6.3c. ONE record for the list access, never one per row.

        The query shape and the count are recorded; the identifiers returned are
        not. Per-row auditing of a queue would generate volume proportional to
        browsing and bury the individual reads that matter.
        """
        if operation_id in NON_AUDITED_READ_OPERATIONS:
            return None
        return self._emit(
            event=AccessEvent.LIST,
            trace_id=trace_id,
            actor_account_id=subject.account_id,
            actor_roles=self._roles(subject),
            operation_id=operation_id,
            resource_kind=resource_kind,
            decision="ALLOW",
            result_count=result_count,
            extra={"query_shape": sorted(query_shape or {})},
        )

    def denied(
        self, *, subject, operation_id: str, trace_id: str, reason_code: str,
        resource_kind: str | None = None, resource_id: uuid.UUID | None = None,
    ) -> AccessRecord:
        """R6.3a. Every denial, for every actor class.

        Customers probing UUIDs are precisely the signal worth keeping (K01/K02),
        so this is not limited to staff.
        """
        return self._emit(
            event=AccessEvent.DENIED,
            trace_id=trace_id,
            actor_account_id=getattr(subject, "account_id", None),
            actor_roles=self._roles(subject),
            operation_id=operation_id,
            resource_kind=resource_kind,
            resource_id=resource_id,
            decision="DENY",
            reason_code=reason_code,
        )

    def claim_authority_conflict(
        self, *, subject, operation_id: str, trace_id: str,
        resource_kind: str, resource_id: uuid.UUID, accounts: frozenset[uuid.UUID],
    ) -> AccessRecord:
        """INV-1. Ambiguous claim authority; nobody is granted access."""
        return self._emit(
            event=AccessEvent.CLAIM_AUTHORITY_CONFLICT,
            trace_id=trace_id,
            actor_account_id=getattr(subject, "account_id", None),
            actor_roles=self._roles(subject),
            operation_id=operation_id,
            resource_kind=resource_kind,
            resource_id=resource_id,
            decision="DENY",
            reason_code="CLAIM_AUTHORITY_CONFLICT",
            extra={
                "claim_account_count": len(accounts),
                "claim_account_ids": sorted(str(a) for a in accounts),
                "requires": "OPERATIONAL_RESOLUTION",
            },
        )

    def role_configuration_anomaly(
        self, *, subject, operation_id: str, trace_id: str, offending: frozenset,
    ) -> AccessRecord:
        """INV-2. An account holds an invalid role combination."""
        return self._emit(
            event=AccessEvent.ROLE_CONFIGURATION_ANOMALY,
            trace_id=trace_id,
            actor_account_id=subject.account_id,
            actor_roles=self._roles(subject),
            operation_id=operation_id,
            decision="DENY",
            reason_code="ROLE_CONFIGURATION_ANOMALY",
            extra={"offending_roles": sorted(r.value for r in offending)},
        )
