#!/usr/bin/env python3
"""Run the suite on a clean tree and write the record that binds its JUnit
report to that tree: `docs/gate/evidence/TEST-RUN-PROVENANCE.txt`.

Earlier rounds wrote that record by hand after the run. It now has one
writer, and one checker (`run_binding.check`), which read the same fields.

- Refuses to start on a tree with uncommitted changes.
- Writes the record only if, when the suite ends, the source fingerprint is
  unchanged and nothing but the report has changed.
- The record states what the report holds: its digest and its counted cases,
  failing ones included. A failing run is recorded as failing, and the
  check refuses it.
- The record names where the suite's connections went, and the server they
  reached (reviews of 8dd7921 and 84280c0):
  - the destination: the database `tests/conftest.py` names, and the host,
    host address and port libpq takes from the environment for every
    parameter a connection leaves unset. It is resolved once and set whole in
    the suite's own environment (`PGHOSTADDR` removed when none); a
    `PGSERVICE` is refused, since its file could name another;
  - the server: after the suite, a connection with every destination
    parameter explicit reads the cluster's system identifier, the address
    and port that answered, and the database. Without it, no record.
  Slice 7's event-store sample is bound to both.

Usage (PG* variables as for the suite):
  .venv/bin/python db/gate/record_test_run.py
Exit status: pytest's, or 2 if the tree was dirty or changed during the run.
"""
from __future__ import annotations

import datetime as dt
import os
import subprocess
import sys

from run_binding import (PROVENANCE, REPORT, ROOT, SERVICE_VARS, connect, counted,
                         destination_env, destination_line, fingerprint, provenance_text,
                         server_identity, server_line, test_destination)


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def main() -> int:
    if _git("status", "--porcelain"):
        print("refused: the working tree has uncommitted changes", file=sys.stderr)
        return 2
    service = [v for v in SERVICE_VARS if os.environ.get(v)]
    if service:
        print(f"refused: {', '.join(service)} is set: a service file could send the suite's "
              "connections to a server this record cannot name", file=sys.stderr)
        return 2
    commit = _git("rev-parse", "HEAD").strip()
    before = fingerprint(ROOT)
    recorded = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    destination = test_destination()
    status = subprocess.run([sys.executable, "-m", "pytest", "-q",
                             f"--junitxml={REPORT.as_posix()}"], cwd=ROOT,
                            env=destination_env(destination)).returncode
    changed = [line[3:] for line in _git("status", "--porcelain").splitlines()
               if line[3:] != REPORT.as_posix()]
    if changed or fingerprint(ROOT) != before or _git("rev-parse", "HEAD").strip() != commit:
        print(f"refused: the tree changed during the run: {changed}", file=sys.stderr)
        return 2
    try:
        with connect(destination) as conn:
            server = server_identity(conn)
    except Exception as exc:  # noqa: BLE001 - any failure leaves no record
        print(f"refused: the server at {destination_line(destination)} could not be "
              f"identified ({type(exc).__name__})", file=sys.stderr)
        return 2
    (ROOT / PROVENANCE).write_text(provenance_text(
        recorded=recorded, commit=commit, source_fingerprint=before,
        report=ROOT / REPORT, report_name=REPORT.as_posix(), destination=destination,
        server=server))
    print(f"wrote {PROVENANCE}: {counted(ROOT / REPORT)}; {destination_line(destination)}; "
          f"{server_line(server)}")
    return status


if __name__ == "__main__":
    sys.exit(main())
