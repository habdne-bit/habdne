"""Alembic environment for TURAB.

Ref: RFC-001 §14.2 — R14.4 (the frozen schema IS the initial migration),
R14.5 (models match the schema, never the reverse), R14.6 (a migration that
alters the baseline needs the schema-change approval path), R14.7 (the
70-assertion gate keeps running against the frozen SQL).

Two decisions are enforced here rather than written down and hoped for.

**`target_metadata` is None, and that is itself the guard.** Alembic's
autogenerate compares model metadata to a live database and emits the
difference. TURAB has no declarative models — the services issue explicit SQL
against the frozen schema — so the comparison would be "nothing declared"
versus "48 tables", and the obliging output is a migration dropping the entire
baseline.

With `target_metadata = None`, Alembic refuses `--autogenerate` outright:
"Can't proceed with --autogenerate option; environment script ... does not
provide a MetaData object". That refusal happens before any revision file is
written, which is stronger than a `process_revision_directives` hook that
inspects a directive Alembic never gets far enough to produce. An earlier
draft of this file carried such a hook; it was unreachable, and an unreachable
check reads as a guarantee while providing none. `test_autogenerate_is_refused`
pins the real behaviour instead.

A migration against this baseline is therefore written by hand, reviewed as a
proposed change to a frozen artifact, and approved as one (R14.6).

**The URL is not in `alembic.ini`.** It comes from `TURAB_DATABASE_URL`, the
same variable the application reads, so there is no second place that decides
which database gets migrated.
"""
from __future__ import annotations

import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT / "src"))

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

#: R14.5. Deliberately None — see the module docstring.
target_metadata = None


def _database_url() -> str:
    url = os.environ.get("TURAB_DATABASE_URL")
    if url:
        return url
    from turab.db.session import database_url

    return database_url()


def run_migrations_offline() -> None:
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    section = config.get_section(config.config_ini_section, {})
    section["sqlalchemy.url"] = _database_url()
    connectable = engine_from_config(
        section, prefix="sqlalchemy.", poolclass=pool.NullPool
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
        )
        with context.begin_transaction():
            context.run_migrations()
    connectable.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
