#!/usr/bin/env python3
"""A structural fingerprint of the TURAB schema.

Ref: RFC-001 R14.4-R14.7.

## Why this exists

Comparing object COUNTS between a migrated database and the static audit
proves something about counts. It does not prove that the objects are the
same objects: 48 tables with the wrong columns still counts as 48. This
module raises the claim from "the same number of things" to "the same
definitions", by hashing what PostgreSQL itself reports for every object it
built.

## What it covers, and what it does not

Covered, as normalised text straight from the catalog:

  * every column: table, name, ordinal, FULL type including its modifier
    (`numeric(14,2)`, not just `numeric`), nullability, default;
  * every constraint: `pg_get_constraintdef`, so check expressions, foreign
    key targets and delete rules are all inside the hash;
  * every index: `pg_get_indexdef`;
  * every trigger: `pg_get_triggerdef`, which carries timing, events and the
    function it calls;
  * every function: `pg_get_functiondef`, which carries the BODY — so a
    changed trigger implementation changes the fingerprint. Identity is
    `name(identity arguments)`, so an added OVERLOAD is a new object rather
    than one that hides behind the original;
  * every enum type: its labels, in order.

NOT covered, and deliberately named rather than implied:

  * row data of any kind, including the master seed and `schema_metadata`;
  * privileges, ownership, row-level security and tablespaces;
  * comments, and the physical ordering of anything;
  * anything outside the `turab` schema EXCEPT installed extensions, which
    are listed by name, schema and version because a migration can install one
    and a `turab`-only view would not see it;
  * `alembic_version` wherever it
    lives. It exists in a migrated or stamped database and not in a freshly
    loaded one, so including it would make every comparison fail for the one
    reason that carries no information. `env.py` pins it to `public`; the
    exclusion below is belt-and-braces, because it was NOT always in `public`
    and this module is what found that out.

A matching fingerprint therefore means: the same tables, columns, types,
constraints, indexes, triggers and function bodies, as PostgreSQL reports
them. It does not mean the two databases are interchangeable in every
respect, and it is not a substitute for the 70-assertion gate, which tests
BEHAVIOUR against the frozen SQL (R14.7).
"""
from __future__ import annotations

import hashlib
from typing import Any, Mapping

SCHEMA = "turab"

#: Alembic's own bookkeeping, excluded for the reason in the module docstring.
EXCLUDED_TABLES = ("alembic_version",)

_QUERIES: dict[str, str] = {
    # `information_schema.data_type` reports the base type only, so
    # numeric(14,2) and numeric(20,3) are both "numeric" and a precision change
    # was invisible. `format_type(atttypid, atttypmod)` carries the modifier,
    # which is the whole point of hashing the definition rather than the name.
    "columns": """
        SELECT c.relname, a.attname, a.attnum::text,
               format_type(a.atttypid, a.atttypmod),
               CASE WHEN a.attnotnull THEN 'NO' ELSE 'YES' END,
               coalesce(pg_get_expr(d.adbin, d.adrelid), '')
          FROM pg_attribute a
          JOIN pg_class c ON c.oid = a.attrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
          LEFT JOIN pg_attrdef d ON d.adrelid = a.attrelid AND d.adnum = a.attnum
         WHERE n.nspname = :schema
           AND c.relkind IN ('r', 'p', 'v', 'm')
           AND a.attnum > 0 AND NOT a.attisdropped
           AND c.relname <> ALL(:excluded)
         ORDER BY c.relname, a.attnum
    """,
    "constraints": """
        SELECT c.conrelid::regclass::text, c.conname,
               pg_get_constraintdef(c.oid)
          FROM pg_constraint c
          JOIN pg_namespace n ON n.oid = c.connamespace
         WHERE n.nspname = :schema
           AND c.conrelid::regclass::text <> ALL(:excluded)
         ORDER BY 1, 2
    """,
    "indexes": """
        SELECT tablename, indexname, indexdef
          FROM pg_indexes
         WHERE schemaname = :schema AND tablename <> ALL(:excluded)
         ORDER BY tablename, indexname
    """,
    "triggers": """
        SELECT c.relname, t.tgname, pg_get_triggerdef(t.oid)
          FROM pg_trigger t
          JOIN pg_class c ON c.oid = t.tgrelid
          JOIN pg_namespace n ON n.oid = c.relnamespace
         WHERE n.nspname = :schema AND NOT t.tgisinternal
         ORDER BY 1, 2
    """,
    # Identity is name + ARGUMENTS, not name alone. PostgreSQL allows
    # overloads, and a check keyed by bare name collapses them: a new overload
    # would sit on top of the original in a dict and neither would be
    # reported. `pg_get_function_identity_arguments` is what distinguishes
    # them, and it is part of the object's identity rather than its body.
    "functions": """
        SELECT p.proname || '(' || pg_get_function_identity_arguments(p.oid) || ')',
               pg_get_functiondef(p.oid)
          FROM pg_proc p
          JOIN pg_namespace n ON n.oid = p.pronamespace
         WHERE n.nspname = :schema
         ORDER BY 1, 2
    """,
    # Extensions live outside `turab`, so nothing below the `turab` filter can
    # see them — which made "no undeclared difference" a wider claim than the
    # machine behind it. `btree_gist` (revision 0004) is exactly such a case.
    #
    # EVERY extension is listed, `plpgsql` included. A first version excluded
    # it as "always there", which is an unexplained exception in a check whose
    # whole value is having none: it is installed by default, but it can be
    # dropped, and its version moves with the server. Listing it costs one
    # constant row on both sides of every comparison and removes a carve-out
    # that would otherwise need defending.
    "extensions": """
        SELECT e.extname, n.nspname, e.extversion
          FROM pg_extension e
          JOIN pg_namespace n ON n.oid = e.extnamespace
         ORDER BY 1
    """,
    "enums": """
        SELECT t.typname, e.enumlabel, e.enumsortorder
          FROM pg_type t
          JOIN pg_namespace n ON n.oid = t.typnamespace
          JOIN pg_enum e ON e.enumtypid = t.oid
         WHERE n.nspname = :schema
         ORDER BY t.typname, e.enumsortorder
    """,
}


def describe(connection) -> dict[str, list[tuple]]:
    """Every covered object, as the catalog reports it."""
    from sqlalchemy import text

    out: dict[str, list[tuple]] = {}
    for name, sql in _QUERIES.items():
        rows = connection.execute(
            text(sql), {"schema": SCHEMA, "excluded": list(EXCLUDED_TABLES)}
        ).fetchall()
        out[name] = [tuple(str(v) for v in row) for row in rows]
    return out


def fingerprint(connection) -> str:
    """A single sha256 over the whole structural description."""
    digest = hashlib.sha256()
    for name, rows in sorted(describe(connection).items()):
        digest.update(f"[{name}]\n".encode())
        for row in rows:
            digest.update(("\x1f".join(row) + "\n").encode())
    return digest.hexdigest()


def diff(left: Mapping[str, list[tuple]], right: Mapping[str, list[tuple]]) -> list[str]:
    """Readable first differences, so a mismatch is actionable."""
    problems: list[str] = []
    for name in sorted(set(left) | set(right)):
        a, b = set(left.get(name, [])), set(right.get(name, []))
        for missing in sorted(a - b)[:5]:
            problems.append(f"{name}: only in the reference: {missing}")
        for extra in sorted(b - a)[:5]:
            problems.append(f"{name}: only in the target:    {extra}")
    return problems


def summarise(connection) -> dict[str, Any]:
    described = describe(connection)
    return {name: len(rows) for name, rows in sorted(described.items())}


if __name__ == "__main__":  # pragma: no cover - a convenience entry point
    import os
    import sys

    from sqlalchemy import create_engine

    url = os.environ.get("TURAB_DATABASE_URL")
    if not url:
        sys.exit("set TURAB_DATABASE_URL")
    engine = create_engine(url, future=True)
    with engine.connect() as c:
        print(fingerprint(c))
        for name, count in summarise(c).items():
            print(f"  {name:12} {count}")
