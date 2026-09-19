"""Alembic: the frozen baseline is the initial migration.

Ref: RFC-001 R14.4-R14.7; `IMPLEMENTATION_SLICES_v0.2.md` slice-completion
criterion "migration can rebuild an empty environment".

Two comparisons run here, and they prove different things.

The weaker one compares object COUNTS against the static audit's independent
parse of the same file. Agreement is evidence about counts — the audit reads
text and counts statements while PostgreSQL reports what it built — but 48
tables with the wrong columns still counts as 48.

The stronger one compares a structural FINGERPRINT: every column, constraint
definition, index definition, trigger definition, function body and enum label
as the catalog reports them. `db/dev/baseline_fingerprint.py` documents
exactly what that covers and what it does not, and the limits are real: it
says nothing about row data, privileges or behaviour. Behaviour remains the
70-assertion gate's job, against the frozen SQL (R14.7).
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import sys

import pytest
from sqlalchemy import create_engine, text

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "db" / "dev"))
from baseline_fingerprint import describe, diff, fingerprint  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[1]
AUDIT_RESULTS = (
    REPO_ROOT / "docs" / "handoff" / "07_QA_ACCEPTANCE"
    / "STATIC_AUDIT_RESULTS_v0.2.3.json"
)
VERSIONS = REPO_ROOT / "db" / "migrations" / "versions"

PGHOST = os.environ.get("PGHOST", "127.0.0.1")
PGUSER = os.environ.get("PGUSER", "turab")
PGPASSWORD = os.environ.get("PGPASSWORD", "turab")
MIGRATION_DB = os.environ.get("TURAB_MIGRATION_DB", "turab_migration_test")
URL = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{MIGRATION_DB}"


#: The PG* variables the tests resolved, passed to every child process. Without
#: them a child falls back to the ambient defaults and talks to a different
#: server than the tests do.
PG_ENV = {"PGHOST": PGHOST, "PGUSER": PGUSER, "PGPASSWORD": PGPASSWORD}


def _alembic(*args: str, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    exe = REPO_ROOT / ".venv" / "bin" / "alembic"
    return subprocess.run(
        [str(exe) if exe.exists() else "alembic", *args],
        cwd=REPO_ROOT, capture_output=True, text=True,
        env={**os.environ, **PG_ENV, "TURAB_DATABASE_URL": URL, **(env_extra or {})},
    )


@pytest.fixture(scope="module")
def migrated():
    """An empty database brought up by `alembic upgrade head`, and nothing else.

    Deliberately NOT the suite's usual test database: that one is built by
    running the frozen SQL directly, which is the very thing this file is
    checking the migration against.
    """
    env = {**os.environ, "PGPASSWORD": PGPASSWORD}
    base = ["-h", PGHOST, "-U", PGUSER]
    subprocess.run(["dropdb", *base, "--if-exists", MIGRATION_DB],
                   check=True, env=env, capture_output=True)
    subprocess.run(["createdb", *base, MIGRATION_DB],
                   check=True, env=env, capture_output=True)

    result = _alembic("upgrade", "head")
    assert result.returncode == 0, result.stderr

    engine = create_engine(URL, future=True)
    yield engine
    engine.dispose()
    subprocess.run(["dropdb", *base, "--if-exists", MIGRATION_DB],
                   check=True, env=env, capture_output=True)


@pytest.fixture(scope="module")
def audit() -> dict:
    return json.loads(AUDIT_RESULTS.read_text(encoding="utf-8"))["metrics"]


# --- the migration rebuilds an empty environment ---------------------------

def test_a_migration_rebuilds_an_empty_environment(migrated):
    """The slice-completion criterion, taken literally."""
    with migrated.connect() as c:
        version = c.execute(
            text("SELECT value FROM turab.schema_metadata WHERE key='schema_version'")
        ).scalar_one()
        stamp = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert version == "0.2.3"
    assert stamp == "0001_frozen_baseline_v0_2_3"


@pytest.mark.parametrize(
    "metric, query",
    [
        ("tables",
         "SELECT count(*) FROM information_schema.tables "
         "WHERE table_schema='turab' AND table_type='BASE TABLE'"),
        ("types",
         "SELECT count(*) FROM pg_type t JOIN pg_namespace n ON n.oid=t.typnamespace "
         "WHERE n.nspname='turab' AND t.typtype='e'"),
        ("functions",
         "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
         "WHERE n.nspname='turab'"),
        ("triggers",
         "SELECT count(*) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid "
         "JOIN pg_namespace n ON n.oid=c.relnamespace "
         "WHERE n.nspname='turab' AND NOT t.tgisinternal"),
        ("foreign_key_refs",
         "SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace "
         "WHERE n.nspname='turab' AND c.contype='f'"),
    ],
)
def test_the_migrated_catalog_matches_the_static_audit(migrated, audit, metric, query):
    """Two independent derivations of the same baseline must agree.

    The audit counts statements in the SQL text; PostgreSQL reports what it
    actually built. A migration that applied a truncated or partly-failed
    file would pass "did it run" and fail here.
    """
    with migrated.connect() as c:
        assert c.execute(text(query)).scalar_one() == audit[metric], (
            f"{metric}: the migrated database disagrees with the static audit"
        )


# --- the baseline cannot be altered under the migration's feet -------------

def test_the_migration_refuses_a_baseline_that_is_not_the_frozen_one(tmp_path):
    """Otherwise editing the vendored package would silently become an
    approved schema change (R14.6)."""
    from importlib import util as importlib_util

    spec = importlib_util.spec_from_file_location(
        "frozen_baseline_rev", VERSIONS / "0001_frozen_baseline_v0_2_3.py"
    )
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)

    original = module.SCHEMA
    tampered = tmp_path / "schema_v0.2.3.sql"
    shutil.copy(original, tampered)
    tampered.write_text(tampered.read_text() + "\n-- one added comment\n")

    module.SCHEMA = tampered
    try:
        with pytest.raises(SystemExit) as exc:
            module._frozen_sql()
    finally:
        module.SCHEMA = original
    assert "not the frozen baseline" in str(exc.value)


def test_the_declared_digest_is_the_frozen_one():
    """The guard is only as good as the constant it compares against."""
    import hashlib
    from importlib import util as importlib_util

    spec = importlib_util.spec_from_file_location(
        "frozen_baseline_rev2", VERSIONS / "0001_frozen_baseline_v0_2_3.py"
    )
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    actual = hashlib.sha256(module.SCHEMA.read_bytes()).hexdigest()
    assert module.SCHEMA_SHA256 == actual


# --- the migration graph ---------------------------------------------------

def test_there_is_exactly_one_head():
    """Two heads mean two people added a root and neither noticed."""
    result = _alembic("heads")
    assert result.returncode == 0, result.stderr
    heads = [ln for ln in result.stdout.splitlines() if ln.strip()]
    assert len(heads) == 1, f"expected one head, got {heads}"
    assert "0001_frozen_baseline_v0_2_3" in heads[0]


def test_autogenerate_is_refused():
    """R14.4. With no declarative metadata to diff against, autogenerate would
    propose dropping the frozen baseline.

    Alembic itself refuses, because `env.py` sets `target_metadata = None`.
    That is the guard — it fires before any revision file is written. This
    test exists because the guard is a deliberate absence, and a deliberate
    absence is exactly the kind of thing a later "helpful" edit restores.
    """
    result = _alembic("revision", "--autogenerate", "-m", "should not be possible")
    output = result.stderr + result.stdout
    assert result.returncode != 0, output
    assert "--autogenerate" in output and "MetaData" in output, output
    created = [p for p in VERSIONS.glob("*.py")
               if p.name != "0001_frozen_baseline_v0_2_3.py"]
    assert not created, f"autogenerate left files behind: {created}"


def test_env_declares_no_metadata_to_diff_against():
    """The companion to the test above: it pins WHY autogenerate is refused,
    so the refusal cannot be silently converted into an empty migration by
    someone wiring up a MetaData object without reading R14.4."""
    env = (REPO_ROOT / "db" / "migrations" / "env.py").read_text(encoding="utf-8")
    assert "target_metadata = None" in env


def test_there_is_no_downgrade_from_the_baseline():
    from importlib import util as importlib_util

    spec = importlib_util.spec_from_file_location(
        "frozen_baseline_rev3", VERSIONS / "0001_frozen_baseline_v0_2_3.py"
    )
    module = importlib_util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with pytest.raises(NotImplementedError):
        module.downgrade()


# --- the stamp path, which is how a real database is actually built --------
#
# `db/dev/reset_db.sh` applies the frozen SQL directly and then STAMPS the
# initial revision, because R14.4 says the schema IS that revision rather than
# something to migrate up to. Skip the stamp and the database carries no
# `alembic_version` at all — so the next `alembic upgrade head` cheerfully
# applies the whole baseline on top of itself and dies on the first duplicate
# object. That is the trap Slice 2 would have walked into.

@pytest.fixture(scope="module")
def stamped():
    """A database built the way reset_db.sh builds one: SQL, then stamp."""
    db = f"{MIGRATION_DB}_stamped"
    url = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{db}"
    env = {**os.environ, "PGPASSWORD": PGPASSWORD}
    base = ["-h", PGHOST, "-U", PGUSER]
    schema = (REPO_ROOT / "docs" / "handoff" / "04_DATABASE" / "schema_v0.2.3.sql")

    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)
    subprocess.run(["createdb", *base, db], check=True, env=env, capture_output=True)
    subprocess.run(["psql", *base, "-d", db, "-v", "ON_ERROR_STOP=1", "-q",
                    "-f", str(schema)], check=True, env=env, capture_output=True)
    stamp = _alembic("stamp", "head", env_extra={"TURAB_DATABASE_URL": url})
    assert stamp.returncode == 0, stamp.stderr

    engine = create_engine(url, future=True)
    yield engine, url
    engine.dispose()
    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)


def test_a_stamped_database_is_already_at_head(stamped):
    engine, _ = stamped
    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() \
            == "0001_frozen_baseline_v0_2_3"


def test_upgrading_a_stamped_database_is_a_no_op(stamped):
    """The whole point of stamping: the baseline is not applied twice."""
    engine, url = stamped
    with engine.connect() as c:
        before = c.execute(
            text("SELECT count(*) FROM information_schema.tables "
                 "WHERE table_schema='turab'")
        ).scalar_one()

    result = _alembic("upgrade", "head", env_extra={"TURAB_DATABASE_URL": url})
    assert result.returncode == 0, result.stderr

    with engine.connect() as c:
        after = c.execute(
            text("SELECT count(*) FROM information_schema.tables "
                 "WHERE table_schema='turab'")
        ).scalar_one()
    assert after == before > 0


def test_the_dev_reset_script_stamps_through_the_guard(stamped):
    """A text check, and named as one: it pins the step into the script
    developers actually run, which no database assertion can reach.

    It must go through `stamp_baseline.py`, not `alembic stamp` — the bare
    command writes a version row and verifies nothing.
    """
    script = (REPO_ROOT / "db" / "dev" / "reset_db.sh").read_text(encoding="utf-8")
    assert "stamp_baseline.py" in script, (
        "reset_db.sh must stamp the initial revision, or every development "
        "database it builds is invisible to Alembic"
    )
    # Comment lines are stripped first: the script EXPLAINS why it does not
    # call `alembic stamp` directly, and a naive substring search would trip
    # over the explanation it is meant to protect.
    commands = [
        line for line in script.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    offenders = [ln for ln in commands if "stamp" in ln and "stamp_baseline" not in ln]
    assert not offenders, f"reset_db.sh stamps without the guard: {offenders}"


# --- structural equality, not just matching counts ------------------------

@pytest.fixture(scope="module")
def reference():
    """A database built by applying the frozen SQL directly — the reference
    every other way of arriving at the baseline is measured against."""
    db = f"{MIGRATION_DB}_reference"
    url = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{db}"
    env = {**os.environ, "PGPASSWORD": PGPASSWORD}
    base = ["-h", PGHOST, "-U", PGUSER]
    schema = REPO_ROOT / "docs" / "handoff" / "04_DATABASE" / "schema_v0.2.3.sql"

    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)
    subprocess.run(["createdb", *base, db], check=True, env=env, capture_output=True)
    subprocess.run(["psql", *base, "-d", db, "-v", "ON_ERROR_STOP=1", "-q",
                    "-f", str(schema)], check=True, env=env, capture_output=True)
    engine = create_engine(url, future=True)
    yield engine
    engine.dispose()
    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)


def test_the_migrated_database_is_structurally_identical_to_the_frozen_schema(
    migrated, reference
):
    """The claim the count comparison cannot make.

    Covers columns, constraint definitions, index definitions, trigger
    definitions, function BODIES and enum labels. It does not cover row data,
    privileges or behaviour — see baseline_fingerprint.py.
    """
    with migrated.connect() as m, reference.connect() as r:
        got, want = describe(m), describe(r)
        problems = diff(want, got)
        assert not problems, "migrated database differs structurally:\n  " + \
            "\n  ".join(problems)
        assert fingerprint(m) == fingerprint(r)


def test_the_fingerprint_notices_a_changed_function_body(reference):
    """A fingerprint that only saw names would pass this, and a changed
    trigger implementation is exactly the drift R14.7 exists to catch."""
    with reference.connect() as r:
        before = fingerprint(r)
    with reference.begin() as w:
        w.execute(text("""
            CREATE OR REPLACE FUNCTION turab.turab_touch_updated_at()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN NEW.updated_at := now(); RETURN NEW; END $$
        """))
    try:
        with reference.connect() as r:
            assert fingerprint(r) != before
    finally:
        with reference.begin() as w:
            w.execute(text("DROP FUNCTION IF EXISTS turab.turab_touch_updated_at()"))


def test_the_version_table_is_pinned_to_public(migrated):
    """The frozen schema sets search_path = turab, public, so an unpinned
    version table lands in `turab` when stamped and `public` when migrated —
    the same database keeping its history in different places depending on how
    it was built. Found by the fingerprint, fixed in env.py."""
    with migrated.connect() as c:
        schemas = c.execute(text(
            "SELECT table_schema FROM information_schema.tables "
            "WHERE table_name = 'alembic_version'"
        )).scalars().all()
    assert schemas == ["public"]


# --- the stamp guard ------------------------------------------------------

def test_stamping_a_database_that_is_not_the_baseline_is_refused(reference):
    """`alembic stamp` verifies nothing, and a stamp ASSERTS that the revision
    is already present. A false assertion surfaces much later, as a migration
    half-applying to a structure the history only claimed it had."""
    db = f"{MIGRATION_DB}_notbaseline"
    url = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{db}"
    env = {**os.environ, "PGPASSWORD": PGPASSWORD}
    base = ["-h", PGHOST, "-U", PGUSER]
    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)
    subprocess.run(["createdb", *base, db], check=True, env=env, capture_output=True)
    subprocess.run(["psql", *base, "-d", db, "-v", "ON_ERROR_STOP=1", "-q", "-c",
                    "CREATE SCHEMA turab; CREATE TABLE turab.parties (party_id uuid)"],
                   check=True, env=env, capture_output=True)
    try:
        result = subprocess.run(
            [str(REPO_ROOT / ".venv" / "bin" / "python"),
             str(REPO_ROOT / "db" / "dev" / "stamp_baseline.py")],
            cwd=REPO_ROOT, capture_output=True, text=True,
            env={**os.environ, **PG_ENV, "TURAB_DATABASE_URL": url},
        )
        assert result.returncode == 2, result.stdout + result.stderr
        assert "NOT the frozen baseline" in result.stderr

        engine = create_engine(url, future=True)
        try:
            with engine.connect() as c:
                assert c.execute(text(
                    "SELECT to_regclass('public.alembic_version') IS NULL"
                )).scalar_one(), "a refused stamp must write no version row"
        finally:
            engine.dispose()
    finally:
        subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                       capture_output=True)


def test_stamping_the_real_baseline_succeeds(reference):
    """The guard must not be so strict it refuses the case it exists to allow."""
    db = f"{MIGRATION_DB}_stampok"
    url = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{db}"
    env = {**os.environ, "PGPASSWORD": PGPASSWORD}
    base = ["-h", PGHOST, "-U", PGUSER]
    schema = REPO_ROOT / "docs" / "handoff" / "04_DATABASE" / "schema_v0.2.3.sql"
    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)
    subprocess.run(["createdb", *base, db], check=True, env=env, capture_output=True)
    subprocess.run(["psql", *base, "-d", db, "-v", "ON_ERROR_STOP=1", "-q",
                    "-f", str(schema)], check=True, env=env, capture_output=True)
    try:
        result = subprocess.run(
            [str(REPO_ROOT / ".venv" / "bin" / "python"),
             str(REPO_ROOT / "db" / "dev" / "stamp_baseline.py"),
             "--reference-db", f"{MIGRATION_DB}_refok"],
            cwd=REPO_ROOT, capture_output=True, text=True,
            env={**os.environ, **PG_ENV, "TURAB_DATABASE_URL": url},
        )
        assert result.returncode == 0, result.stdout + result.stderr
        engine = create_engine(url, future=True)
        try:
            with engine.connect() as c:
                assert c.execute(
                    text("SELECT version_num FROM public.alembic_version")
                ).scalar_one() == "0001_frozen_baseline_v0_2_3"
        finally:
            engine.dispose()
    finally:
        subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                       capture_output=True)
