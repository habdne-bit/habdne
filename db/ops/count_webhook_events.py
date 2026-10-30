#!/usr/bin/env python3
"""R-1's count check (R1-D14 (a), plan §4): the rows of `webhook_events`,
counts only, in each database named.

    .venv/bin/python db/ops/count_webhook_events.py DATABASE [DATABASE ...]

Plan: `docs/gate/R1_RELAY_PLAN.md` §4: "an operator command counts the rows
of `webhook_events` in each non-test database, counts only [...]. The
expected count before the first real event is zero."

**What it reads, and how:**
- the server from the standard `PGHOST` (required), `PGHOSTADDR` and
  `PGPORT` (5432 when unset), with `PGUSER` and `PGPASSWORD`; **`PGSERVICE`
  and `PGDATABASE` are refused**, so the databases are the ones named on the
  command line and no other;
- **every destination parameter pinned at the connection** (review of
  `18e4aec`): `host`, `hostaddr` (empty when none), `port` and `dbname` are
  each passed explicitly, so libpq fills none of them from anywhere else;
- each database in a **read-only** transaction, its read-only state read
  back and printed;
- **the identity of what answered**, read from the server itself: its
  cluster's system identifier, the address and port it answered on, and the
  database (`pg_control_system()`, `inet_server_addr()`,
  `inet_server_port()`, `current_database()`);
- `count(*)` of `turab.webhook_events`, and nothing else: no row, no id, no
  payload.

**What it prints**, one line per database:

    DATABASE: webhook_events=N read_only=on | answered: system_identifier=...
    address=... port=... database=... | asked: host=... hostaddr=... port=...

- **The count is the answering server's.** `asked` is only what the
  environment named. With `PGHOSTADDR` set, libpq connects to that address
  and never resolves `PGHOST`, so `PGHOST` alone can name a host nothing
  reached; the line never attributes a count to it.
- `webhook_events=NO_TABLE` when the database has no such table.
- A database the connection to which fails (no server, refused, not
  authenticated): `DATABASE: CONNECTION_FAILED asked:
  ...` on stderr, no count, and exit status 1. Exit status 0 when every
  count was read; 2 when refused before connecting.

It decides nothing about which databases are "non-test": the operator names
them, and the record says which they were.
"""
from __future__ import annotations

import os
import sys

import psycopg


def destination(database: str) -> dict[str, str]:
    """Where a connection to `database` goes: every parameter, none left to
    libpq. An empty `hostaddr` means none."""
    return {"host": os.environ["PGHOST"], "hostaddr": os.environ.get("PGHOSTADDR", ""),
            "port": os.environ.get("PGPORT") or "5432", "dbname": database}


def asked(dest: dict[str, str]) -> str:
    return f"host={dest['host']} hostaddr={dest['hostaddr'] or '-'} port={dest['port']}"


def count(database: str) -> str:
    """One database's line: its count, and the server and database that
    answered it."""
    dest = destination(database)
    with psycopg.connect(**dest) as conn:
        conn.execute("SET TRANSACTION READ ONLY")
        read_only = conn.execute("SHOW transaction_read_only").fetchone()[0]
        sid, address, port, answered_db = conn.execute("""
            SELECT (SELECT system_identifier FROM pg_control_system())::text,
                   coalesce(host(inet_server_addr()), 'local-socket'),
                   coalesce(inet_server_port()::text, 'local-socket'),
                   current_database()""").fetchone()
        table = conn.execute("SELECT to_regclass('turab.webhook_events')").fetchone()[0]
        rows = ("NO_TABLE" if table is None else
                conn.execute("SELECT count(*) FROM turab.webhook_events").fetchone()[0])
    return (f"{database}: webhook_events={rows} read_only={read_only} | answered: "
            f"system_identifier={sid} address={address} port={port} database={answered_db} | "
            f"asked: {asked(dest)}")


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: count_webhook_events.py DATABASE [DATABASE ...]", file=sys.stderr)
        return 2
    for variable in ("PGSERVICE", "PGDATABASE"):
        if os.environ.get(variable):
            print(f"refused: {variable} is set; name the databases on the command line",
                  file=sys.stderr)
            return 2
    if not os.environ.get("PGHOST"):
        print("refused: PGHOST is not set; name the server", file=sys.stderr)
        return 2
    status = 0
    for database in argv:
        try:
            line = count(database)
        except psycopg.OperationalError:
            print(f"{database}: CONNECTION_FAILED asked: {asked(destination(database))}",
                  file=sys.stderr)
            status = 1
            continue
        print(line)
    return status


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
