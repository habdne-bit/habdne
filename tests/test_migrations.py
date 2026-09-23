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

import hashlib
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

sys.path.insert(0, str(REPO_ROOT / "db" / "gate"))
from migration_deltas import DELTAS, for_revision, split_row  # noqa: E402
BASELINE = "0001_frozen_baseline_v0_2_3"
HEAD = "0004_relation_overlap_guard"

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
    assert stamp == HEAD, "upgrade head must land on the current head"


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
    assert HEAD in heads[0]


def test_autogenerate_is_refused():
    """R14.4. With no declarative metadata to diff against, autogenerate would
    propose dropping the frozen baseline.

    Alembic itself refuses, because `env.py` sets `target_metadata = None`.
    That is the guard — it fires before any revision file is written. This
    test exists because the guard is a deliberate absence, and a deliberate
    absence is exactly the kind of thing a later "helpful" edit restores.
    """
    # Snapshot, rather than a hardcoded list: what this test must prove is
    # that autogenerate leaves NOTHING BEHIND, and that claim is independent of
    # how many migrations the project has. The hardcoded version had to be
    # edited for every new revision, which is exactly the kind of routine edit
    # that eventually gets made without reading what it is asserting.
    before = {p.name for p in VERSIONS.glob("*.py")}
    result = _alembic("revision", "--autogenerate", "-m", "should not be possible")
    output = result.stderr + result.stdout
    assert result.returncode != 0, output
    assert "--autogenerate" in output and "MetaData" in output, output
    after = {p.name for p in VERSIONS.glob("*.py")}
    assert after == before, f"autogenerate left files behind: {sorted(after - before)}"


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

def _migration_data(connection) -> dict[str, object]:
    """The ROW data a migration writes, which the structural fingerprint does
    not cover and a re-run could therefore disturb unnoticed.

    Only `0002` writes rows (three `reason_codes` in category
    `REQUEST_CLOSURE`); `0003` replaces a function body and `0004` adds a
    constraint, neither of which touches data. The whole `reason_codes` table
    is digested rather than just that category, so a migration that modified a
    SEEDED row — the thing a migration must never do — would also show up.
    """
    import hashlib

    rows = connection.execute(
        text("""SELECT code, category, label_ar, label_en, active
                  FROM turab.reason_codes ORDER BY code""")
    ).fetchall()
    digest = hashlib.sha256(
        "\n".join("\x1f".join(str(v) for v in r) for r in rows).encode()
    ).hexdigest()
    return {
        "reason_codes_digest": digest,
        "reason_codes_count": len(rows),
        "request_closure_count": connection.execute(
            text("SELECT count(*) FROM turab.reason_codes "
                 "WHERE category = 'REQUEST_CLOSURE'")
        ).scalar_one(),
    }


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
    stamp = _alembic("stamp", BASELINE, env_extra={"TURAB_DATABASE_URL": url})
    assert stamp.returncode == 0, stamp.stderr

    engine = create_engine(url, future=True)
    yield engine, url
    engine.dispose()
    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)


def test_a_stamped_database_is_at_the_baseline_not_head(stamped):
    """Renamed. It was `..._is_already_at_head`, which said the opposite of
    what it asserts — its own failure message already said "the BASELINE, not
    the head". The name was true when the baseline WAS the head, and stayed
    behind when `0002` arrived; the migration policy then cited it by that
    name, so a reader checking the claim met a test that disproved it.
    """
    engine, _ = stamped
    with engine.connect() as c:
        assert c.execute(text("SELECT version_num FROM alembic_version")).scalar_one() \
            == BASELINE, "stamping marks the BASELINE, not the head"


def test_the_first_upgrade_after_stamping_applies_the_later_revisions(stamped):
    """**Corrects a claim this file used to make.**

    The old test compared TABLE COUNTS before and after the first
    `upgrade head` on a stamped database and called the result a no-op. That
    was true only while every revision after the baseline added DATA. Stamping
    marks `0001`, so the first upgrade necessarily applies `0002`, `0003` and
    `0004` — and a table count cannot see any of them, so the test passed
    while describing the opposite of what happened.

    Three assertions now, in the order they actually occur.
    """
    engine, url = stamped

    # 1. after stamping the database is at the BASELINE, not at head
    with engine.connect() as c:
        assert c.execute(
            text("SELECT version_num FROM alembic_version")).scalar_one() == BASELINE
        gate_before = c.execute(
            text("""SELECT pg_get_functiondef(p.oid)
                      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                     WHERE n.nspname='turab' AND p.proname='enforce_consent_binding'""")
        ).scalar_one()
    assert "valid_from" not in gate_before, (
        "a stamped database carries the FROZEN function, before 0003")

    # 2. the first upgrade reaches head and the deltas are visibly applied
    result = _alembic("upgrade", "head", env_extra={"TURAB_DATABASE_URL": url})
    assert result.returncode == 0, result.stderr
    with engine.connect() as c:
        assert c.execute(
            text("SELECT version_num FROM alembic_version")).scalar_one() == HEAD
        gate_after = c.execute(
            text("""SELECT pg_get_functiondef(p.oid)
                      FROM pg_proc p JOIN pg_namespace n ON n.oid = p.pronamespace
                     WHERE n.nspname='turab' AND p.proname='enforce_consent_binding'""")
        ).scalar_one()
        overlap = c.execute(text(
            "SELECT count(*) FROM pg_constraint "
            "WHERE conname='party_property_relations_no_overlap'")).scalar_one()
        reasons = c.execute(text(
            "SELECT count(*) FROM turab.reason_codes "
            "WHERE category='REQUEST_CLOSURE'")).scalar_one()
        after_first = fingerprint(c)
    assert "valid_from IS NOT NULL" in gate_after, "0003 was not applied"
    assert overlap == 1, "0004 was not applied"
    assert reasons == 3, "0002 was not applied"

    # 3. the SECOND upgrade changes nothing — structure, the rows the
    #    migrations write, AND the recorded version.
    #
    #    The structural fingerprint alone cannot carry this claim: it
    #    deliberately excludes row data (see baseline_fingerprint's docstring),
    #    so on its own it would prove only that the CATALOG is unchanged, while
    #    `0002` writes rows and no catalog object at all.
    #
    #    **What this does and does not establish**, established by experiment
    #    rather than assumed. A second `upgrade head` applies NOTHING: alembic
    #    reads `alembic_version`, sees the database already at head, and runs
    #    no migration body — confirmed by the absence of any "Running upgrade"
    #    line in its output. So what is proven here is that alembic's
    #    bookkeeping holds and that nothing drifted, NOT that the migration
    #    bodies are individually idempotent.
    #
    #    That separate property — 0002's body applied twice inserting nothing
    #    twice — is proven by `test_0002_body_re_executed_inserts_nothing_twice`,
    #    which winds `alembic_version` back and makes the body run again for
    #    real. Removing the `WHERE NOT EXISTS` guard fails THAT test with a
    #    duplicate-key violation and leaves this one passing.
    #
    #    An earlier version of this comment credited
    #    `..._is_additive_and_re_runnable` with executing the body. It did not:
    #    it ended with `upgrade head` on a database already at head, which
    #    applies nothing. The mutation that "confirmed" it had also changed the
    #    reason CODES, so it failed on the FIRST application's data — a true
    #    result under a false cause, which is the error this project keeps
    #    finding and this comment had reproduced.
    with engine.connect() as c:
        rows_before = _migration_data(c)
        version_before = c.execute(
            text("SELECT version_num FROM alembic_version")).scalar_one()

    again = _alembic("upgrade", "head", env_extra={"TURAB_DATABASE_URL": url})
    assert again.returncode == 0, again.stderr
    # State assertions alone cannot show that NO BODY RAN — a body that happens
    # to be idempotent would leave the same state. Alembic announces each
    # revision it applies, so its silence is the direct evidence.
    assert "Running upgrade" not in (again.stderr + again.stdout), (
        "the second upgrade applied a migration body; it must apply none:\n"
        + again.stderr + again.stdout)

    with engine.connect() as c:
        assert fingerprint(c) == after_first, (
            "a second upgrade changed the catalog; it must change nothing")
        assert _migration_data(c) == rows_before, (
            "a second upgrade changed the rows the migrations write; "
            "`INSERT ... WHERE NOT EXISTS` is what makes 0002 re-runnable")
        assert c.execute(
            text("SELECT version_num FROM alembic_version")).scalar_one() \
            == version_before == HEAD
        assert c.execute(
            text("SELECT count(*) FROM alembic_version")).scalar_one() == 1, (
            "alembic_version must hold exactly one row")


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


@pytest.fixture(scope="module")
def at_baseline():
    """A database at revision 0001 exactly — `upgrade 0001`, nothing after it.

    This is what the BASELINE guarantee is asserted against, and it is built by
    Alembic rather than by running the SQL, because the whole question is
    whether Alembic's 0001 produces the frozen schema.
    """
    db = f"{MIGRATION_DB}_at_0001"
    url = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{db}"
    env = {**os.environ, **PG_ENV}
    base = ["-h", PGHOST, "-U", PGUSER]
    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)
    subprocess.run(["createdb", *base, db], check=True, env=env, capture_output=True)
    result = _alembic("upgrade", BASELINE, env_extra={"TURAB_DATABASE_URL": url})
    assert result.returncode == 0, result.stderr
    engine = create_engine(url, future=True)
    yield engine
    engine.dispose()
    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)


# --- level 1: the BASELINE guarantee, absolute and without exception --------

def test_revision_0001_is_structurally_identical_to_the_frozen_schema(
    at_baseline, reference
):
    """**No delta may ever apply here.** Revision 0001 IS the frozen baseline.

    Covers columns, constraint definitions, index definitions, trigger
    definitions, function BODIES and enum labels. Nothing is excluded and the
    fingerprint is not weakened: this is the guarantee that stays absolute now
    that later revisions may change structure.
    """
    with at_baseline.connect() as m, reference.connect() as r:
        problems = diff(describe(r), describe(m))
        assert not problems, "revision 0001 differs from the frozen schema:\n  " + \
            "\n  ".join(problems)
        assert fingerprint(m) == fingerprint(r)


def test_no_delta_is_ever_declared_against_the_baseline_revision():
    """A delta describes evolution AFTER 0001. One claiming to change the
    baseline would be editing the frozen schema through the back door."""
    offenders = [d.revision for d in DELTAS if d.revision == BASELINE]
    assert not offenders, offenders


# --- level 2: the HEAD guarantee — baseline + declared deltas, nothing else --

def test_head_is_the_baseline_plus_exactly_the_declared_deltas(
    migrated, reference
):
    """The precise form of the old sentence, not a weaker one.

    Every structural difference between `head` and the frozen baseline must be
    a DECLARED delta, and every declared delta must actually be present with
    the digest it promised. Both directions are checked, so the ledger can
    neither hide a difference nor claim one that is not there.
    """
    with migrated.connect() as m, reference.connect() as r:
        got, want = describe(m), describe(r)

    declared = {(d.section, d.object_name): d for d in DELTAS}
    seen: set[tuple[str, str]] = set()
    problems: list[str] = []

    for section in sorted(set(got) | set(want)):
        a = dict(split_row(section, row) for row in want.get(section, []))
        b = dict(split_row(section, row) for row in got.get(section, []))
        for name in sorted(set(a) | set(b)):
            if a.get(name) == b.get(name):
                continue
            key = (section, name)
            delta = declared.get(key)
            if delta is None:
                problems.append(
                    f"UNDECLARED structural difference: {section}/{name}. "
                    "Declare it in db/gate/migration_deltas.py with its "
                    "revision, digests, reason and proving test — or remove it."
                )
                continue
            seen.add(key)
            before = (hashlib.sha256(a[name].encode()).hexdigest()
                      if name in a else None)
            after = (hashlib.sha256(b[name].encode()).hexdigest()
                     if name in b else None)
            if before != delta.digest_before:
                problems.append(
                    f"{section}/{name}: baseline digest {before} does not match "
                    f"the declared digest_before {delta.digest_before}"
                )
            if after != delta.digest_after:
                problems.append(
                    f"{section}/{name}: head digest {after} does not match the "
                    f"declared digest_after {delta.digest_after}"
                )

    for key, delta in declared.items():
        if key not in seen:
            problems.append(
                f"declared delta {delta.revision} {key[0]}/{key[1]} is NOT "
                "present at head; a delta that does not exist is a false claim"
            )

    assert not problems, "head does not match baseline + declared deltas:\n  " + \
        "\n  ".join(problems)


def test_every_delta_names_a_revision_object_reason_and_proving_test():
    """A ledger entry that omits any of the six required fields is a note, not
    evidence. The behavioural test matters most: a digest proves the text
    changed, only a test proves the change was the right one."""
    for d in DELTAS:
        assert d.revision and (VERSIONS / f"{d.revision}.py").exists(), d
        assert d.section and d.object_name and d.kind, d
        assert d.digest_before or d.digest_after, d
        assert len(d.reason) > 60, f"{d.revision}: reason is too thin to review"
        assert d.proven_by, f"{d.revision}: no behavioural test named"


def test_the_only_declared_delta_for_0003_is_the_consent_binding_function():
    """Ratified scope: 0003 may change that function body and nothing else."""
    deltas = for_revision("0003_consent_relation_currency")
    assert len(deltas) == 1, deltas
    assert deltas[0].section == "functions"
    assert deltas[0].object_name == "enforce_consent_binding()"


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
                ).scalar_one() == BASELINE
        finally:
            engine.dispose()
    finally:
        subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                       capture_output=True)


def test_every_revision_id_fits_the_version_column():
    """`alembic_version.version_num` is varchar(32).

    A longer id passes every local check and then fails at the moment the
    migration is recorded — after its work has run. Found the hard way by a
    33-character id.
    """
    import re

    too_long = []
    for path in VERSIONS.glob("*.py"):
        match = re.search(r'^revision = "([^"]+)"', path.read_text(encoding="utf-8"),
                          re.M)
        assert match, f"{path.name} declares no revision id"
        if len(match.group(1)) > 32:
            too_long.append((path.name, len(match.group(1))))
    assert not too_long, f"revision ids exceed varchar(32): {too_long}"


def test_the_closure_reason_migration_is_additive(migrated):
    """It adds rows; it changes nothing that was seeded.

    **Renamed.** It was `..._is_additive_and_re_runnable`, and the second half
    of that name was unsupported: the test ended with `alembic upgrade head` on
    a database ALREADY at head, which applies nothing at all. It therefore said
    nothing about running 0002's body twice. Re-runnability is proven by
    `test_0002_body_re_executed_inserts_nothing_twice` below, which forces the
    body to run again for real.
    """
    with migrated.connect() as c:
        adopted = c.execute(text(
            "SELECT code FROM turab.reason_codes WHERE category = 'REQUEST_CLOSURE' "
            "ORDER BY code"
        )).scalars().all()
        touched_other = c.execute(text(
            "SELECT count(*) FROM turab.reason_codes WHERE code = 'OTHER'"
        )).scalar_one()
    assert adopted == [
        "REQUEST_CLOSED_OTHER", "REQUEST_FULFILLED", "REQUEST_WITHDRAWN"
    ]
    # This database has the schema but not the master seed, so the historical
    # OTHER row is absent — and the migration must not have invented one.
    assert touched_other == 0, "the migration must not create or alter OTHER"


def test_0002_body_re_executed_inserts_nothing_twice():
    """Run 0002's BODY a second time, for real, and require no duplication.

    This is the test that was missing. Alembic will not re-run a migration it
    has already recorded, so "run `upgrade head` again" can never exercise a
    body — which is exactly why the previous claim was unsupported. The version
    row is therefore wound back to `0001` and `upgrade 0002` is invoked again,
    so the real body executes twice through the real machinery.

    Winding back `alembic_version` by hand is something production must never
    do. It is legitimate here because forcing the re-execution IS the
    experiment: the property under test is what the body does when it runs on a
    database that already carries its effects, which is the situation after a
    partial failure or a restored backup.

    `INSERT ... WHERE NOT EXISTS` is what makes it safe, and an unconditional
    INSERT fails here — verified by mutation.
    """
    db = f"{MIGRATION_DB}_rerun0002"
    url = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{db}"
    env = {**os.environ, **PG_ENV}
    base = ["-h", PGHOST, "-U", PGUSER]
    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)
    subprocess.run(["createdb", *base, db], check=True, env=env, capture_output=True)
    engine = create_engine(url, future=True)
    try:
        first = _alembic("upgrade", "0002_request_closure_reasons",
                         env_extra={"TURAB_DATABASE_URL": url})
        assert first.returncode == 0, first.stderr
        assert "Running upgrade" in first.stderr + first.stdout, (
            "the first upgrade must actually have applied migrations")

        with engine.connect() as c:
            before = _migration_data(c)
        assert before["request_closure_count"] == 3, before

        # Force the body to run again: alembic will only re-apply a revision
        # it does not believe is already applied.
        with engine.begin() as w:
            w.execute(text("UPDATE alembic_version SET version_num = :v"),
                      {"v": BASELINE})

        second = _alembic("upgrade", "0002_request_closure_reasons",
                          env_extra={"TURAB_DATABASE_URL": url})
        # A non-zero exit here IS the failure this test exists to catch: the
        # body raised on a database that already carries its rows. Reported as
        # that, rather than as a bare stderr dump, so the diagnosis is in the
        # failure and not only in the traceback.
        assert second.returncode == 0, (
            "0002's body failed when applied to a database that already has "
            "its rows — it is not safe to re-run. Removing the "
            "`WHERE NOT EXISTS` guard produces exactly this:\n"
            + second.stderr)
        assert "Running upgrade" in second.stderr + second.stdout, (
            "the body did NOT run a second time, so this test proved nothing; "
            "that was the defect in the claim this test replaces")

        with engine.connect() as c:
            after = _migration_data(c)
        assert after == before, (
            "re-running 0002's body changed the data: "
            f"{before} -> {after}. `INSERT ... WHERE NOT EXISTS` is what makes "
            "the migration safe to apply to a database that already has its rows")
        assert after["request_closure_count"] == 3
    finally:
        engine.dispose()
        subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                       capture_output=True)


# --- 0003 specifically -----------------------------------------------------

def test_0003_is_re_runnable(migrated):
    """`CREATE OR REPLACE FUNCTION` is idempotent, and the trigger is not
    recreated — it already points at the function by name. Applying the body a
    second time must leave the catalog identical, digest included."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "m0003", VERSIONS / "0003_consent_relation_currency.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with migrated.connect() as c:
        before = fingerprint(c)
    with migrated.begin() as w:
        w.execute(text("SET LOCAL search_path TO turab, public"))
        w.execute(text(module.CORRECTED))
    with migrated.connect() as c:
        assert fingerprint(c) == before, "re-applying 0003 changed the catalog"


def test_building_from_0001_then_upgrading_head_matches_a_direct_upgrade(migrated):
    """Stepwise and direct must agree.

    A migration chain that only works when run in one go is a chain nobody can
    apply to an existing database — which is every real database.
    """
    db = f"{MIGRATION_DB}_stepwise"
    url = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{db}"
    env = {**os.environ, **PG_ENV}
    base = ["-h", PGHOST, "-U", PGUSER]
    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)
    subprocess.run(["createdb", *base, db], check=True, env=env, capture_output=True)
    try:
        for step in (BASELINE, "0002_request_closure_reasons", HEAD):
            result = _alembic("upgrade", step, env_extra={"TURAB_DATABASE_URL": url})
            assert result.returncode == 0, f"{step}: {result.stderr}"
        stepwise = create_engine(url, future=True)
        try:
            with stepwise.connect() as a, migrated.connect() as b:
                problems = diff(describe(b), describe(a))
                assert not problems, "stepwise differs from direct:\n  " + \
                    "\n  ".join(problems)
                assert fingerprint(a) == fingerprint(b)
        finally:
            stepwise.dispose()
    finally:
        subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                       capture_output=True)


def test_0003_refuses_to_downgrade(migrated):
    """Reverting 0003 restores a gate that accepts an unstarted or future
    relation. A silent revert would reopen that hole with no record, so the
    revision refuses and says why — and the refusal is asserted here so it
    cannot be quietly replaced by a working downgrade later."""
    result = _alembic("downgrade", "0002_request_closure_reasons")
    output = result.stderr + result.stdout
    assert result.returncode != 0, output
    assert "no downgrade" in output or "G3-7" in output, output
    with migrated.connect() as c:
        still = c.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
    assert still == HEAD, "a refused downgrade must leave the version untouched"


def test_the_delta_check_catches_an_undeclared_structural_change(migrated, reference):
    """The detector must bite.

    An extra structural change beyond the approved function body has to be
    reported as UNDECLARED — otherwise the head guarantee would be a list of
    what we remembered to write down rather than a check.
    """
    with migrated.begin() as w:
        w.execute(text("""
            CREATE OR REPLACE FUNCTION turab.turab_undeclared_probe()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN RETURN NEW; END $$
        """))
    try:
        with migrated.connect() as m, reference.connect() as r:
            got, want = describe(m), describe(r)
        declared = {(d.section, d.object_name) for d in DELTAS}
        undeclared = []
        for section in set(got) | set(want):
            a = dict(split_row(section, row) for row in want.get(section, []))
            b = dict(split_row(section, row) for row in got.get(section, []))
            for name in set(a) | set(b):
                if a.get(name) != b.get(name) and (section, name) not in declared:
                    undeclared.append((section, name))
        assert ("functions", "turab_undeclared_probe()") in undeclared, undeclared
    finally:
        with migrated.begin() as w:
            w.execute(text("DROP FUNCTION IF EXISTS turab.turab_undeclared_probe()"))


# --- the detector's own blind spots, closed and proven ---------------------

def _undeclared(migrated, reference):
    """Every structural difference not covered by a declared delta."""
    with migrated.connect() as m, reference.connect() as r:
        got, want = describe(m), describe(r)
    declared = {(d.section, d.object_name) for d in DELTAS}
    out = []
    for section in set(got) | set(want):
        a = dict(split_row(section, row) for row in want.get(section, []))
        b = dict(split_row(section, row) for row in got.get(section, []))
        for name in set(a) | set(b):
            if a.get(name) != b.get(name) and (section, name) not in declared:
                out.append((section, name))
    return out


def test_the_detector_catches_a_column_precision_change(migrated, reference):
    """`information_schema.data_type` reports "numeric" for both
    `numeric(14,2)` and `numeric(20,3)`, so a precision change was invisible.

    `format_type(atttypid, atttypmod)` carries the modifier. Asserted by
    actually making the change, because the previous version of this check
    would have passed this test while missing the change.
    """
    with migrated.begin() as w:
        w.execute(text("ALTER TABLE turab.properties "
                       "ALTER COLUMN land_area_m2 TYPE numeric(20,3)"))
    try:
        found = _undeclared(migrated, reference)
        assert ("columns", "properties.land_area_m2") in found, found
    finally:
        with migrated.begin() as w:
            w.execute(text("ALTER TABLE turab.properties "
                           "ALTER COLUMN land_area_m2 TYPE numeric(12,2)"))
    assert ("columns", "properties.land_area_m2") not in _undeclared(migrated, reference)


def test_the_detector_catches_an_added_function_overload(migrated, reference):
    """A function keyed by bare NAME collapses overloads: a new one sits on top
    of the original in a dict and neither is reported.

    Identity is now `name(identity arguments)`. The overload added here shares
    its name with a real baseline function, which is the case that used to
    hide.
    """
    with migrated.begin() as w:
        w.execute(text("""
            CREATE OR REPLACE FUNCTION turab.enforce_consent_binding(probe integer)
            RETURNS integer LANGUAGE sql AS $$ SELECT probe $$
        """))
    try:
        found = _undeclared(migrated, reference)
        assert ("functions", "enforce_consent_binding(probe integer)") in found, found
        # and the real one is still matched by its own declared delta
        assert ("functions", "enforce_consent_binding()") not in found, found
    finally:
        with migrated.begin() as w:
            w.execute(text(
                "DROP FUNCTION IF EXISTS turab.enforce_consent_binding(integer)"))


def test_btree_gist_is_installed_in_public(migrated):
    """The extension invariant. `0004` needs `btree_gist`, and WHERE it lives
    matters: installed into `turab` it pollutes the schema, which is how the
    first version of that migration was caught."""
    with migrated.connect() as c:
        row = c.execute(
            text("""SELECT n.nspname FROM pg_extension e
                      JOIN pg_namespace n ON n.oid = e.extnamespace
                     WHERE e.extname = 'btree_gist'""")
        ).scalar_one_or_none()
    assert row == "public", f"btree_gist is in {row!r}, not public"


def test_0004_refuses_a_btree_gist_installed_outside_public():
    """`CREATE EXTENSION IF NOT EXISTS ... SCHEMA public` does NOT move an
    extension that already exists elsewhere — `IF NOT EXISTS` leaves it where
    it is. A clean environment therefore proves nothing about this case, so it
    is built deliberately: the extension is installed into another schema
    FIRST, and the migration must refuse rather than silently proceed with the
    constraint while the extension sits somewhere unexpected.
    """
    db = f"{MIGRATION_DB}_extsplace"
    url = f"postgresql+psycopg://{PGUSER}:{PGPASSWORD}@{PGHOST}/{db}"
    env = {**os.environ, **PG_ENV}
    base = ["-h", PGHOST, "-U", PGUSER]
    subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                   capture_output=True)
    subprocess.run(["createdb", *base, db], check=True, env=env, capture_output=True)
    try:
        pre = create_engine(url, future=True)
        with pre.begin() as w:
            w.execute(text("CREATE SCHEMA elsewhere"))
            w.execute(text("CREATE EXTENSION btree_gist SCHEMA elsewhere"))
        pre.dispose()

        result = _alembic("upgrade", "head", env_extra={"TURAB_DATABASE_URL": url})
        output = result.stderr + result.stdout
        assert result.returncode != 0, f"0004 accepted a misplaced extension:\n{output}"
        assert "btree_gist" in output and "elsewhere" in output, output

        # and it refused BEFORE adding the constraint
        after = create_engine(url, future=True)
        try:
            with after.connect() as c:
                exists = c.execute(text(
                    "SELECT count(*) FROM pg_constraint "
                    "WHERE conname = 'party_property_relations_no_overlap'"
                )).scalar_one()
            assert exists == 0, "the constraint was added despite the refusal"
        finally:
            after.dispose()
    finally:
        subprocess.run(["dropdb", *base, "--if-exists", db], check=True, env=env,
                       capture_output=True)


# --- the gate-run recorder's own claims ------------------------------------

def test_the_gate_input_list_follows_the_scripts_the_gate_invokes():
    """The classification must reach inputs of INVOKED scripts, not only paths
    written in the entry script.

    This is the defect that made the previous version of this test useless. It
    parsed `run_gate.sh` for literal paths and compared them against a
    hand-written prefix list — so both sides missed
    `docs/contract/CONTRACT_CORRECTIONS.yaml`, which step 7's
    `generate_effective_contract.py` reads. The file was labelled "[other]
    cannot affect this run" while a comment-only edit to it flipped the
    contract check from PASS to FAIL.

    The check is now the other way round: every path mentioned by any script
    reachable from the entry point must classify as a gate input. A test that
    compares a list against itself proves nothing; this one compares the
    classifier against the scripts.
    """
    import re
    sys.path.insert(0, str(REPO_ROOT / "db" / "gate"))
    import gate_inputs

    missed = []
    for script in sorted(gate_inputs.reachable_paths()):
        if not script.endswith((".py", ".sh")):
            continue
        text = (REPO_ROOT / script).read_text(encoding="utf-8", errors="replace")
        for path in re.findall(r"(?<![\w./-])(?:docs|db)/[A-Za-z0-9_./-]+", text):
            if gate_inputs.classify(path) != "gate-input":
                missed.append((script, path, gate_inputs.classify(path)))
    assert not missed, (
        "these paths are read by a script the gate runs, but are not "
        f"classified as gate inputs: {missed}"
    )


def test_the_contract_corrections_file_is_a_gate_input():
    """Named explicitly, because this is the file the general rule missed.

    `generate_effective_contract.py --check` is step 7 of the gate and reads
    it; a comment-only change there makes the effective contract stale and the
    step fail. It must never again be labelled as unable to affect the run.
    """
    sys.path.insert(0, str(REPO_ROOT / "db" / "gate"))
    import gate_inputs

    corrections = "docs/contract/CONTRACT_CORRECTIONS.yaml"
    assert (REPO_ROOT / corrections).is_file(), corrections
    assert gate_inputs.classify(corrections) == "gate-input"
    assert "docs/contract" in gate_inputs.input_prefixes()


def test_the_recorder_derives_its_labels_rather_than_declaring_them():
    """A hand-kept list in the recorder is what drifted. It must call the
    derivation, not restate it."""
    recorder = (REPO_ROOT / "db" / "gate" / "record_gate_run.sh").read_text(
        encoding="utf-8")
    assert "gate_inputs.py --classify" in recorder, (
        "the recorder must classify through db/gate/gate_inputs.py")
    assert "docs/handoff/*|docs/api/*" not in recorder, (
        "the hand-written prefix case is back; it is what drifted from the "
        "scripts and missed docs/contract")


def test_the_gate_recorder_takes_one_snapshot_for_the_count_and_the_list():
    """The count and the list must come from the SAME snapshot.

    They did not: the count was taken before the output file was created and
    the list after, so the header read "2 uncommitted path(s)" above a list of
    three. Pinned as a text check, and named as one — there is no way to assert
    it from a database.
    """
    recorder = (REPO_ROOT / "db" / "gate" / "record_gate_run.sh").read_text(
        encoding="utf-8")
    assert 'SNAPSHOT="$(git status --porcelain' in recorder, (
        "the recorder must capture one snapshot into a variable")
    assert recorder.count("git status --porcelain") == 1, (
        "git status is called more than once; the count and the list can "
        "then disagree, which is the defect this test exists to prevent")
    assert 'printf \'%s\' "$SNAPSHOT" | grep -c' in recorder, (
        "the count must be derived from the snapshot, not from a second call")
    assert 'printf \'%s\\n\' "$SNAPSHOT" | while read' in recorder, (
        "the list must be derived from the same snapshot")


def test_the_other_label_makes_no_guarantee_the_scan_cannot_give():
    """`[other]` means "not found by a TEXTUAL scan", nothing more.

    It read "cannot affect this run" — a guarantee a text scan cannot give,
    since a path assembled at run time never appears as text. Pinned as a text
    check, and named as one: the reviewer's point is about what the header
    CLAIMS, and a claim is text.
    """
    recorder = (REPO_ROOT / "db" / "gate" / "record_gate_run.sh").read_text(
        encoding="utf-8")
    echoed = "\n".join(line for line in recorder.splitlines()
                        if line.lstrip().startswith("echo"))
    assert "cannot affect" not in echoed, (
        "the header must not promise that an [other] path cannot affect the run")
    assert "not a proof" in echoed, "the header must state the label's limit"
    doc = (REPO_ROOT / "db" / "gate" / "gate_inputs.py").read_text(encoding="utf-8")
    assert "UNDER-include" in doc, "the derivation must document its blind spot"


def test_gate_inputs_refuses_to_answer_outside_a_checkout(tmp_path):
    """A copy run from outside a checkout must FAIL, not answer partially.

    One did: shipped detached in a review bundle, it printed `db/gate` alone and
    exited 0. Its root was computed from its own location, the entry script was
    not found, and a helper that turned a missing file into "" let the walk end
    at step one. The reviewer caught it by comparing it with the in-tree copy.

    Both halves are asserted: the refusal outside a checkout, and the correct
    answer when `--root` names one — so the fix is not simply "always fail".
    """
    import shutil

    detached = tmp_path / "gate_inputs.py"
    shutil.copy(REPO_ROOT / "db" / "gate" / "gate_inputs.py", detached)
    python = str(REPO_ROOT / ".venv" / "bin" / "python")

    refused = subprocess.run([python, str(detached)], capture_output=True, text=True)
    assert refused.returncode == 2, (
        f"a detached copy must refuse, got exit {refused.returncode} with "
        f"stdout={refused.stdout!r}")
    assert refused.stdout == "", (
        "a refusal must print NO prefixes — a partial list is the defect")
    assert "not a TURAB checkout" in refused.stderr

    answered = subprocess.run([python, str(detached), "--root", str(REPO_ROOT)],
                              capture_output=True, text=True)
    assert answered.returncode == 0, answered.stderr
    assert set(answered.stdout.split()) >= {
        "db/gate", "docs/api", "docs/contract", "docs/handoff"}
