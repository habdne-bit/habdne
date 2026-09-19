"""Optimistic concurrency — API_CONTRACTS §2.4."""
from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text

from turab.services.concurrency import (
    HEADER,
    VERSIONED_TABLES,
    IfMatchRequired,
    MalformedIfMatch,
    StaleVersion,
    check,
    current_version,
    parse_if_match,
)


def test_header_name_follows_the_openapi_contract():
    """API_CONTRACTS §2.4 says If-Match-Version; the frozen OpenAPI declares
    If-Match. Per the authority order in §1, OpenAPI governs HTTP shape."""
    from turab.auth.contract import load_contract

    declared = load_contract()["components"]["parameters"]["IfMatchVersion"]
    assert declared["name"] == HEADER == "If-Match"
    assert declared["required"] is True


@pytest.mark.parametrize("raw,expected", [("1", 1), ("42", 42), ('"7"', 7), ('W/"3"', 3)])
def test_parse_accepts_plain_and_etag_forms(raw, expected):
    assert parse_if_match(raw) == expected


def test_the_prose_header_name_is_accepted_as_an_alias():
    """A client following API_CONTRACTS §2.4 is not silently rejected."""
    assert parse_if_match(None, "5") == 5


@pytest.mark.parametrize("raw", [None, "", "   "])
def test_a_missing_header_is_rejected(raw):
    with pytest.raises(IfMatchRequired):
        parse_if_match(raw)


@pytest.mark.parametrize("raw", ["abc", "1.5", "-1", "0"])
def test_a_malformed_header_is_rejected(raw):
    with pytest.raises(MalformedIfMatch):
        parse_if_match(raw)


def test_matching_version_passes(session, ids):
    version = current_version(session, "requests", ids.REQ_AMINA)
    guard = check(session, "requests", ids.REQ_AMINA, version)
    assert guard.version == version


def test_stale_version_is_rejected(session, ids):
    version = current_version(session, "requests", ids.REQ_AMINA)
    with pytest.raises(StaleVersion):
        check(session, "requests", ids.REQ_AMINA, version + 1)


def test_a_concurrent_bump_makes_the_held_version_stale(session, ids):
    """The real scenario: someone else wrote while this caller was deciding."""
    held = current_version(session, "requests", ids.REQ_AMINA)
    session.execute(
        text("UPDATE turab.requests SET status='PAUSED' WHERE request_id=:r"),
        {"r": ids.REQ_AMINA},
    )
    assert current_version(session, "requests", ids.REQ_AMINA) == held + 1
    with pytest.raises(StaleVersion):
        check(session, "requests", ids.REQ_AMINA, held)


def test_an_unknown_resource_is_stale_not_a_crash(session):
    with pytest.raises(StaleVersion):
        check(session, "requests", uuid.uuid4(), 1)


def test_parties_is_not_versioned_in_the_frozen_schema(session):
    """PATCH /parties/{id} requires If-Match in the contract, but `parties`
    has no version column. Recorded as a deviation, not faked."""
    assert "parties" not in VERSIONED_TABLES
    columns = session.execute(
        text(
            """SELECT column_name FROM information_schema.columns
                WHERE table_schema='turab' AND table_name='parties'"""
        )
    ).scalars().all()
    assert "version" not in columns
    with pytest.raises(ValueError):
        check(session, "parties", uuid.uuid4(), 1)


@pytest.mark.parametrize("table", sorted(VERSIONED_TABLES))
def test_every_versioned_table_really_has_a_version_column(session, table):
    columns = session.execute(
        text(
            """SELECT column_name FROM information_schema.columns
                WHERE table_schema='turab' AND table_name=:t"""
        ),
        {"t": table},
    ).scalars().all()
    assert "version" in columns
