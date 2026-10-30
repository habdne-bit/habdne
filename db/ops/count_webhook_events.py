#!/usr/bin/env python3
"""R-1's count check (R1-D14 (a), plan §4): the rows of `webhook_events`,
counts only, in each database named.

    .venv/bin/python db/ops/count_webhook_events.py DATABASE [DATABASE ...]

Plan: `docs/gate/R1_RELAY_PLAN.md` §4: "an operator command counts the rows
of `webhook_events` in each non-test database, counts only [...]. The
expected count before the first real event is zero."

**What it reads, and how:**
- the server from the standard `PGHOST`, `PGPORT`, `PGUSER` and
  `PGPASSWORD`; **`PGSERVICE` and `PGDATABASE` are refused**, so the
  databases are the ones named on the command line and no other;
- each database in a **read-only** transaction, its read-only state read
  back and printed;
- `count(*)` of `turab.webhook_events`, and nothing else: no row, no id, no
  payload.

**What it prints**, one line per database: its name, the host, whether the
transaction was read-only, and the count; or that the database has no
`turab.webhook_events` table. Exit status 0 when every count was read.

It decides nothing about which databases are "non-test": the operator names
them, and the record says which they were.
"""
from __future__ import annotations

import os
import sys

import psycopg


def count(database: str) -> str:
    """One database's line."""
    host = os.environ.get("PGHOST", "")
    with psycopg.connect(dbname=database) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        read_only = conn.execute("SHOW transaction_read_only").fetchone()[0]
        table = conn.execute("SELECT to_regclass('turab.webhook_events')").fetchone()[0]
        if table is None:
            return f"{database} host={host} read_only={read_only} webhook_events=NO_TABLE"
        rows = conn.execute("SELECT count(*) FROM turab.webhook_events").fetchone()[0]
        return f"{database} host={host} read_only={read_only} webhook_events={rows}"


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: count_webhook_events.py DATABASE [DATABASE ...]", file=sys.stderr)
        return 2
    for variable in ("PGSERVICE", "PGDATABASE"):
        if os.environ.get(variable):
            print(f"refused: {variable} is set; name the databases on the command line",
                  file=sys.stderr)
            return 2
    for database in argv:
        print(count(database))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
