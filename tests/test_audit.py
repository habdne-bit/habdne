"""Read auditing — Q4.

Ref: RFC-001 R6.3-R6.3d.
"""
from __future__ import annotations

import uuid

import pytest

from turab.auth.audit import (
    AccessAuditor,
    AccessEvent,
    AuditMetadataViolation,
    RecordingAuditSink,
)
from turab.auth.loaders import ResourceKind
from turab.auth.subject import resolve_subject


def test_staff_read_of_an_individual_resource_is_audited(session, subject_of, ids,
                                                         access_for, auditor):
    """R6.3 row 1."""
    staff = subject_of(ids.ACC_OPERATOR)
    access = access_for(staff)
    access._auditor.read(
        subject=staff, operation_id="getRequestsRequestId", trace_id="t",
        resource_kind=ResourceKind.REQUEST.value, resource_id=ids.REQ_AMINA,
    )
    reads = auditor.sink.of(AccessEvent.READ)
    assert len(reads) == 1
    assert reads[0].resource_id == ids.REQ_AMINA
    assert reads[0].actor_roles == ("OPERATOR",)


def test_customer_self_read_is_not_audited_as_a_staff_read(session, subject_of, ids,
                                                           access_for, auditor):
    """Q4 names STAFF reads. Auditing every customer self-read would bury them."""
    access = access_for(subject_of(ids.ACC_AMINA))
    result = access.read_resource(
        ResourceKind.REQUEST, ids.REQ_AMINA, "getMeRequestsRequestId"
    )
    assert result.authorized
    assert auditor.sink.of(AccessEvent.READ) == []


def test_denials_are_audited_for_every_actor_class(session, subject_of, ids,
                                                   access_for, auditor):
    """R6.3a. A customer probing UUIDs is the signal worth keeping."""
    access = access_for(subject_of(ids.ACC_KHADIJA))
    result = access.read_resource(
        ResourceKind.REQUEST, ids.REQ_AMINA, "getMeRequestsRequestId"
    )
    assert not result.authorized
    denials = auditor.sink.of(AccessEvent.DENIED)
    assert len(denials) == 1
    assert denials[0].actor_roles == ("CUSTOMER",)
    assert denials[0].reason_code == "OBJECT_NOT_AUTHORIZED"


def test_a_list_is_audited_once_not_per_row(session, subject_of, ids, access_for, auditor):
    """R6.3c. Per-row auditing of a queue would bury the reads that matter."""
    access = access_for(subject_of(ids.ACC_OPERATOR))
    access.record_list_access(
        operation_id="getBackofficeQueuesRequests",
        resource_kind=ResourceKind.REQUEST.value,
        result_count=50,
        query_shape={"status": "ACTIVE", "limit": 50},
    )
    lists = auditor.sink.of(AccessEvent.LIST)
    assert len(lists) == 1
    assert lists[0].result_count == 50
    assert auditor.sink.of(AccessEvent.READ) == []
    # the shape is recorded, the identifiers returned are not
    assert lists[0].extra["query_shape"] == ["limit", "status"]
    assert lists[0].resource_id is None


@pytest.mark.parametrize(
    "operation_id",
    ["getLocations", "getMasterCriterionDefinitions", "getPublicProperties", "getReasonCodes"],
)
def test_public_and_master_data_reads_are_not_audited(session, subject_of, ids, operation_id):
    """R6.3 row 4."""
    sink = RecordingAuditSink()
    auditor = AccessAuditor(sink)
    assert auditor.read(
        subject=subject_of(ids.ACC_OPERATOR), operation_id=operation_id, trace_id="t",
        resource_kind="PROPERTY", resource_id=uuid.uuid4(),
    ) is None
    assert sink.records == []


@pytest.mark.parametrize(
    "key",
    ["seller_expectation_dzd", "raw_text", "otp_code", "dto", "permission_snapshot", "notes"],
)
def test_audit_metadata_cannot_carry_sensitive_payloads(key):
    """R6.3b. Enforced, not merely documented.

    An audit trail that copies what it protects relocates the leak.
    """
    auditor = AccessAuditor(RecordingAuditSink())
    with pytest.raises(AuditMetadataViolation):
        auditor._emit(
            event=AccessEvent.DENIED, trace_id="t", actor_account_id=None,
            actor_roles=(), operation_id="x", extra={key: "secret"},
        )


def test_access_records_carry_references_not_content(session, subject_of, ids,
                                                     access_for, auditor):
    """R6.3b, positively: inspect a real record's keys."""
    access = access_for(subject_of(ids.ACC_KHADIJA))
    access.read_resource(ResourceKind.PROPERTY, ids.CLAIMED_HOUSE, "getMePropertiesPropertyId")
    record = auditor.sink.of(AccessEvent.DENIED)[0].as_dict()
    assert set(record) == {
        "event", "occurred_at", "trace_id", "actor_account_id", "actor_roles",
        "operation_id", "resource_kind", "resource_id", "decision",
        "reason_code", "result_count", "extra",
    }
    serialized = str(record)
    for leak in ("seller_expectation", "asking_price", "raw_text", "why_real"):
        assert leak not in serialized
