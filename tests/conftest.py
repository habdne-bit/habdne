"""Test fixtures: a real PostgreSQL database built from the frozen baseline.

The authorization predicates are SQL. Testing them against anything other than
the frozen schema would test a model of the rules rather than the rules.
"""
from __future__ import annotations

import os
import pathlib
import subprocess
import uuid

import pytest
from sqlalchemy import text

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
DB_DIR = REPO_ROOT / "docs" / "handoff" / "04_DATABASE"
FIXTURES = REPO_ROOT / "db" / "fixtures" / "dev_fixtures.sql"

TEST_DB = os.environ.get("TURAB_TEST_DB", "turab_authz_test")
PGHOST = os.environ.get("PGHOST", "127.0.0.1")
PGUSER = os.environ.get("PGUSER", "turab")
PGPASSWORD = os.environ.get("PGPASSWORD", "turab")


def _require_server() -> None:
    """Fail once, readably, instead of 200+ identical connection errors.

    See docs/gate/ENVIRONMENT_NOTES.md EN-01: this container restarts and
    PostgreSQL does not come back up with it, so an entire suite can fail for
    one reason that the output buries.
    """
    probe = subprocess.run(
        ["pg_isready", "-h", PGHOST, "-q"], capture_output=True
    )
    if probe.returncode != 0:
        raise pytest.UsageError(
            f"PostgreSQL is not accepting connections on {PGHOST}. "
            "Start it with `service postgresql start` and re-run. "
            "See docs/gate/ENVIRONMENT_NOTES.md EN-01 — a suite failing this "
            "way produced no result, and must not be reported as one."
        )


def _psql(db: str, *args: str) -> None:
    env = {**os.environ, "PGPASSWORD": PGPASSWORD}
    subprocess.run(
        ["psql", "-h", PGHOST, "-U", PGUSER, "-d", db, "-v", "ON_ERROR_STOP=1", "-q", *args],
        check=True, env=env, capture_output=True,
    )


def pytest_sessionstart(session) -> None:
    """One readable failure instead of a wall of identical ones (EN-01)."""
    _require_server()


@pytest.fixture(scope="session")
def database_url() -> str:
    env = {**os.environ, "PGPASSWORD": PGPASSWORD}
    subprocess.run(["dropdb", "-h", PGHOST, "-U", PGUSER, "--if-exists", TEST_DB],
                   check=True, env=env, capture_output=True)
    subprocess.run(["createdb", "-h", PGHOST, "-U", PGUSER, TEST_DB],
                   check=True, env=env, capture_output=True)
    _psql(TEST_DB, "-f", str(DB_DIR / "schema_v0.2.3.sql"))
    _psql(TEST_DB, "-f", str(DB_DIR / "seed_master_data_v0.2.3.sql"))
    _psql(TEST_DB, "-f", str(FIXTURES))

    # Build it the way a real database is built: the frozen baseline is
    # revision 0001, stamped rather than replayed, then every migration after
    # it runs forward. Without this the suite would test a database no
    # deployment can produce — one holding the baseline and nothing since.
    url = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{TEST_DB}"
    alembic = REPO_ROOT / ".venv" / "bin" / "alembic"
    exe = str(alembic) if alembic.exists() else "alembic"
    child = {**os.environ, "TURAB_DATABASE_URL": url,
             "PGHOST": PGHOST, "PGUSER": PGUSER, "PGPASSWORD": PGPASSWORD}
    subprocess.run([exe, "stamp", "0001_frozen_baseline_v0_2_3"],
                   cwd=REPO_ROOT, check=True, env=child, capture_output=True)
    subprocess.run([exe, "upgrade", "head"],
                   cwd=REPO_ROOT, check=True, env=child, capture_output=True)
    return url


@pytest.fixture(scope="session")
def engine(database_url):
    from turab.db.session import create_app_engine

    eng = create_app_engine(database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine):
    """A session whose work is rolled back, so tests cannot leak into each other."""
    from sqlalchemy.orm import Session

    connection = engine.connect()
    transaction = connection.begin()
    s = Session(bind=connection, expire_on_commit=False, future=True)
    s.execute(text("SET search_path = turab, public"))
    try:
        yield s
    finally:
        s.close()
        transaction.rollback()
        connection.close()


# --- identifiers from db/fixtures/dev_fixtures.sql -------------------------
class Ids:
    # parties
    AMINA = uuid.UUID("f1000000-0000-4000-8000-000000000001")
    BRAHIM = uuid.UUID("f1000000-0000-4000-8000-000000000002")
    AGENCY = uuid.UUID("f1000000-0000-4000-8000-000000000003")
    KHADIJA = uuid.UUID("f1000000-0000-4000-8000-000000000004")
    NO_ACCOUNT_PARTY = uuid.UUID("f1000000-0000-4000-8000-000000000005")
    # accounts
    ACC_AMINA = uuid.UUID("f3000000-0000-4000-8000-000000000001")
    ACC_OPERATOR = uuid.UUID("f3000000-0000-4000-8000-000000000002")
    ACC_REVIEWER = uuid.UUID("f3000000-0000-4000-8000-000000000003")
    ACC_KHADIJA = uuid.UUID("f3000000-0000-4000-8000-000000000004")
    ACC_ADMIN = uuid.UUID("f3000000-0000-4000-8000-000000000005")
    ACC_AMINA_SECOND = uuid.UUID("f3000000-0000-4000-8000-000000000006")
    #: Bound to BRAHIM, login contact point is the SHARED line that also
    #: reaches the agency — the shared-phone claim test (DL-02).
    ACC_BRAHIM = uuid.UUID("f3000000-0000-4000-8000-000000000007")
    # properties
    # SELF_MANAGED/CLAIMED, created by the OPERATOR account: related parties
    # exist but nobody claimed it, so no customer is authorized.
    VILLA_SELF_MANAGED = uuid.UUID("f4000000-0000-4000-8000-000000000001")
    # ASSISTED/UNCLAIMED, so genuinely claimable.
    ASSISTED_APARTMENT = uuid.UUID("f4000000-0000-4000-8000-000000000003")
    POTENTIAL_LAND = uuid.UUID("f4000000-0000-4000-8000-000000000002")
    CLAIMED_HOUSE = uuid.UUID("f4000000-0000-4000-8000-000000000004")
    ORPHAN_LAND = uuid.UUID("f4000000-0000-4000-8000-000000000005")
    ALL_WITHDRAWN = uuid.UUID("f4000000-0000-4000-8000-000000000006")
    UNKNOWN_DOC_LAND = uuid.UUID("f4000000-0000-4000-8000-000000000007")
    # offers
    OFFER_OWNER_SALE = uuid.UUID("f6000000-0000-4000-8000-000000000001")
    OFFER_BROKER_SALE = uuid.UUID("f6000000-0000-4000-8000-000000000002")
    OFFER_ON_CLAIMED = uuid.UUID("f6000000-0000-4000-8000-000000000005")
    # requests
    REQ_AMINA = uuid.UUID("f7000000-0000-4000-8000-000000000001")
    REQ_AGENCY_ASSISTED = uuid.UUID("f7000000-0000-4000-8000-000000000002")
    REQ_KHADIJA = uuid.UUID("f7000000-0000-4000-8000-000000000003")
    #: ASSISTED/UNCLAIMED for KHADIJA's party — the one record in the fixture
    #: world that an account may LEGITIMATELY claim (contract x-authorization).
    REQ_KHADIJA_ASSISTED = uuid.UUID("f7000000-0000-4000-8000-000000000005")
    #: ASSISTED/UNCLAIMED for AMINA's party — claimable by EITHER of the two
    #: accounts bound to that party, which is what makes INV-1's write half
    #: testable now that eligibility is enforced.
    REQ_AMINA_ASSISTED = uuid.UUID("f7000000-0000-4000-8000-000000000006")
    # contact points
    CP_AMINA = uuid.UUID("f2000000-0000-4000-8000-000000000001")
    #: The shared line: reaches BRAHIM and the AGENCY, and is ACC_BRAHIM's login.
    CP_SHARED = uuid.UUID("f2000000-0000-4000-8000-000000000002")
    CP_KHADIJA = uuid.UUID("f2000000-0000-4000-8000-000000000004")
    CP_AMINA_SECOND = uuid.UUID("f2000000-0000-4000-8000-000000000005")


@pytest.fixture
def ids() -> type[Ids]:
    return Ids


@pytest.fixture
def subject_of(session):
    from turab.auth.subject import resolve_subject

    def _make(account_id: uuid.UUID):
        return resolve_subject(session, account_id)

    return _make


@pytest.fixture
def auditor():
    from turab.auth.audit import AccessAuditor, RecordingAuditSink

    sink = RecordingAuditSink()
    a = AccessAuditor(sink)
    a.sink_records = sink  # type: ignore[attr-defined]
    return a


@pytest.fixture(scope="session")
def policies():
    from turab.auth.contract import build_policy_table

    return build_policy_table()


@pytest.fixture
def access_for(session, policies, auditor):
    from turab.services.access import AccessService

    def _make(subject, trace_id="test-trace"):
        return AccessService(session, subject, policies, auditor, trace_id)

    return _make
