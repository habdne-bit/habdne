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

Usage (PG* variables as for the suite):
  .venv/bin/python db/gate/record_test_run.py
Exit status: pytest's, or 2 if the tree was dirty or changed during the run.
"""
from __future__ import annotations

import datetime as dt
import subprocess
import sys

from run_binding import PROVENANCE, REPORT, ROOT, counted, fingerprint, provenance_text


def _git(*args: str) -> str:
    return subprocess.run(["git", *args], cwd=ROOT, check=True, capture_output=True,
                          text=True).stdout


def main() -> int:
    if _git("status", "--porcelain"):
        print("refused: the working tree has uncommitted changes", file=sys.stderr)
        return 2
    commit = _git("rev-parse", "HEAD").strip()
    before = fingerprint(ROOT)
    recorded = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    status = subprocess.run([sys.executable, "-m", "pytest", "-q",
                             f"--junitxml={REPORT.as_posix()}"], cwd=ROOT).returncode
    changed = [line[3:] for line in _git("status", "--porcelain").splitlines()
               if line[3:] != REPORT.as_posix()]
    if changed or fingerprint(ROOT) != before or _git("rev-parse", "HEAD").strip() != commit:
        print(f"refused: the tree changed during the run: {changed}", file=sys.stderr)
        return 2
    (ROOT / PROVENANCE).write_text(provenance_text(
        recorded=recorded, commit=commit, source_fingerprint=before,
        report=ROOT / REPORT, report_name=REPORT.as_posix()))
    print(f"wrote {PROVENANCE}: {counted(ROOT / REPORT)}")
    return status


if __name__ == "__main__":
    sys.exit(main())
