#!/usr/bin/env python3
"""Stamp the initial Alembic revision — only on a database that IS the baseline.

Ref: RFC-001 R14.4.

`alembic stamp head` writes a version row and verifies nothing. That is the
correct behaviour for Alembic and the wrong behaviour for us: a stamp asserts
"this database already contains revision 0001", and if it does not, every
later migration runs against a structure the history says it has and does not.
The failure surfaces much later, as a migration that half-applies.

So this refuses to stamp unless the target database is structurally identical
to a reference database built by applying the frozen `schema_v0.2.3.sql` to an
empty database — same columns, constraints, indexes, triggers, function bodies
and enum labels (see `baseline_fingerprint.py` for exactly what that covers
and what it does not).

Usage:
  TURAB_DATABASE_URL=... db/dev/stamp_baseline.py [--reference-db NAME]

Exit codes: 0 stamped or already at head; 2 the target is not the baseline;
3 the target is stamped at a different revision.
"""
from __future__ import annotations

import argparse
import os
import pathlib
import subprocess
import sys

from sqlalchemy import create_engine, text

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from baseline_fingerprint import describe, diff, fingerprint  # noqa: E402

REPO_ROOT = pathlib.Path(__file__).resolve().parents[2]
SCHEMA_SQL = REPO_ROOT / "docs" / "handoff" / "04_DATABASE" / "schema_v0.2.3.sql"
HEAD = "0001_frozen_baseline_v0_2_3"


def _pg_args() -> list[str]:
    args = ["-h", os.environ.get("PGHOST", "/var/run/postgresql")]
    if os.environ.get("PGPORT"):
        args += ["-p", os.environ["PGPORT"]]
    if os.environ.get("PGUSER"):
        args += ["-U", os.environ["PGUSER"]]
    return args


def _reference_fingerprint(db_name: str) -> tuple[str, dict]:
    """Build a throwaway database from the frozen SQL and describe it."""
    base = _pg_args()
    env = dict(os.environ)
    subprocess.run(["dropdb", *base, "--if-exists", db_name],
                   check=True, env=env, capture_output=True)
    subprocess.run(["createdb", *base, db_name], check=True, env=env,
                   capture_output=True)
    try:
        subprocess.run(
            ["psql", *base, "-d", db_name, "-v", "ON_ERROR_STOP=1", "-q",
             "-f", str(SCHEMA_SQL)],
            check=True, env=env, capture_output=True,
        )
        host = os.environ.get("PGHOST", "/var/run/postgresql")
        port = os.environ.get("PGPORT", "5432")
        user = os.environ.get("PGUSER", "")
        password = os.environ.get("PGPASSWORD", "")
        auth = f"{user}:{password}@" if user else ""
        engine = create_engine(
            f"postgresql+psycopg://{auth}{host}:{port}/{db_name}", future=True
        )
        try:
            with engine.connect() as c:
                return fingerprint(c), describe(c)
        finally:
            # A pooled connection keeps the reference database open, and
            # `dropdb` then fails on a database still in use.
            engine.dispose()
    finally:
        subprocess.run(["dropdb", *base, "--if-exists", db_name],
                       check=True, env=env, capture_output=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reference-db", default="turab_baseline_reference",
                    help="throwaway database used to build the reference")
    args = ap.parse_args()

    url = os.environ.get("TURAB_DATABASE_URL")
    if not url:
        print("TURAB_DATABASE_URL is not set", file=sys.stderr)
        return 2

    engine = create_engine(url, future=True)
    with engine.connect() as c:
        stamped = c.execute(
            text("SELECT to_regclass('public.alembic_version') IS NOT NULL")
        ).scalar_one()
        current = None
        if stamped:
            current = c.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one_or_none()
        target_fp = fingerprint(c)
        target_desc = describe(c)

    if current is not None and current != HEAD:
        print(f"refusing: the database is stamped at {current!r}, not {HEAD!r}. "
              "Resolve the history before stamping.", file=sys.stderr)
        return 3

    reference_fp, reference_desc = _reference_fingerprint(args.reference_db)

    if target_fp != reference_fp:
        print("refusing to stamp: this database is NOT the frozen baseline.",
              file=sys.stderr)
        print(f"  reference {reference_fp}", file=sys.stderr)
        print(f"  target    {target_fp}", file=sys.stderr)
        for line in diff(reference_desc, target_desc)[:20]:
            print(f"  {line}", file=sys.stderr)
        print("A stamp asserts the database already contains revision "
              f"{HEAD}. Stamping one that does not makes every later migration "
              "run against a structure the history only claims it has.",
              file=sys.stderr)
        return 2

    if current == HEAD:
        print(f"already at {HEAD}; nothing to do")
        return 0

    alembic = REPO_ROOT / ".venv" / "bin" / "alembic"
    result = subprocess.run(
        [str(alembic) if alembic.exists() else "alembic", "stamp", HEAD],
        cwd=REPO_ROOT, env={**os.environ, "TURAB_DATABASE_URL": url},
    )
    if result.returncode == 0:
        print(f"stamped {HEAD} (structure verified against the frozen schema)")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
