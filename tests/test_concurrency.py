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
    """D1, settled in v0.2.2: the canonical header is If-Match-Version, and the
    contract now types the value as an integer rather than a string."""
    from turab.auth.contract import load_contract

    declared = load_contract()["components"]["parameters"]["IfMatchVersion"]
    assert declared["name"] == HEADER == "If-Match-Version"
    assert declared["required"] is True
    assert declared["schema"]["type"] == "integer"
    assert declared["schema"]["minimum"] == 1


@pytest.mark.parametrize("raw,expected", [("1", 1), ("42", 42), (" 7 ", 7)])
def test_parse_accepts_a_version_integer(raw, expected):
    assert parse_if_match(raw) == expected


@pytest.mark.parametrize("raw", ['"7"', 'W/"3"'])
def test_etag_forms_are_no_longer_accepted(raw):
    """The contract types the value `integer, minimum: 1`.

    `If-Match` conventionally carries an ETag, which is why v0.2.1 tolerated
    quoted and weak forms. `If-Match-Version` carries a version integer, so
    accepting ETag syntax would be a liberality the contract does not describe.
    """
    with pytest.raises(MalformedIfMatch):
        parse_if_match(raw)


def test_the_old_if_match_alias_is_gone():
    """D1: no production client required backward compatibility, so the
    undocumented alias was removed rather than carried."""
    import inspect

    from turab.services import concurrency

    assert not hasattr(concurrency, "HEADER_ALIAS")
    assert list(inspect.signature(parse_if_match).parameters) == ["value"]


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


def test_parties_is_now_versioned(session, ids):
    """D2, resolved in v0.2.2. This test previously asserted the opposite: it
    recorded the contract/schema contradiction that blocked Slice 1."""
    assert "parties" in VERSIONED_TABLES
    version = current_version(session, "parties", ids.AMINA)
    assert version == 1
    assert check(session, "parties", ids.AMINA, 1).version == 1
    with pytest.raises(StaleVersion):
        check(session, "parties", ids.AMINA, 2)


def test_updating_a_party_bumps_its_version(session, ids):
    """D2 swapped the timestamp-only trigger for bump_version_and_timestamp()."""
    before = current_version(session, "parties", ids.AMINA)
    session.execute(
        text("UPDATE turab.parties SET display_name = :n WHERE party_id = :p"),
        {"n": "renamed", "p": ids.AMINA},
    )
    assert current_version(session, "parties", ids.AMINA) == before + 1
    with pytest.raises(StaleVersion):
        check(session, "parties", ids.AMINA, before)


def test_the_parties_version_check_constraint_holds(session):
    """`CHECK (version > 0)` as D2 specified.

    The constraint can only fire on INSERT: on UPDATE the trigger overwrites
    NEW.version before the constraint is evaluated (see the test below).
    """
    from sqlalchemy.exc import IntegrityError

    with pytest.raises(IntegrityError):
        session.execute(
            text(
                """INSERT INTO turab.parties (party_id, kind, status, version)
                   VALUES (gen_random_uuid(), 'PERSON', 'DISCOVERED', 0)"""
            )
        )


def test_a_client_cannot_forge_a_party_version(session, ids):
    """A stronger guarantee than the CHECK, and the reason the trigger matters.

    `bump_version_and_timestamp()` sets NEW.version := OLD.version + 1 on every
    UPDATE, so a caller writing an arbitrary version — by mistake or on purpose
    — cannot make one stick. Optimistic concurrency would be worthless if the
    value it compares were client-settable.
    """
    before = current_version(session, "parties", ids.AMINA)
    session.execute(
        text("UPDATE turab.parties SET version = 999 WHERE party_id = :p"),
        {"p": ids.AMINA},
    )
    assert current_version(session, "parties", ids.AMINA) == before + 1


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
