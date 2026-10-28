#!/usr/bin/env python3
"""Sample the event store of the suite's test database, right after a run.

    db/gate/record_test_run.py            # the run, bound to a clean tree
    db/gate/slice7_event_store_counts.py  # then, at once: this sample

Plan: `docs/gate/SLICE_7_PLAN.md` §6.4 and G7-19 (i), decided in the review
of d04d5c8. The plan asks for "the event store's RECEIVED and FAILED counts
at the end of the run"; they live in the suite's database, not in the JUnit
report or the source. This script reads them, and writes
`docs/gate/evidence/SLICE7-EVENT-STORE-COUNTS.txt` with:
- the time the sample was taken;
- the run's identifier (its recorded time and commit), its source
  fingerprint and its JUnit report's sha256, read from
  `TEST-RUN-PROVENANCE.txt`;
- the test database's name and host, as the run's record names them;
- the count of each `processing_status`, and of FAILED events by
  `error_text`. Nothing else: no event id, no reference, no payload.

**It refuses** (writing nothing, connecting to nothing) unless:
- the recorded run is bound to the current tree, with no failed or errored
  case (`run_binding.check`);
- it skipped no case: Slice 7's evidence requires zero skipped, which
  `run_binding.check` does not refuse (review of 8dd7921);
- the run's record names its database (`Test database`, written by
  `record_test_run.py`), and the environment names no other: `TURAB_TEST_DB`
  and `PGHOST`, when set, must be the recorded ones (review of 8dd7921). The
  sample is then taken from the recorded database, never from the
  environment's.

**What the sample is, and is not.** A sample measured right after the run,
from the run's test database: not the state at the moment of the last test,
and never a PASS. These are the suite's test events. No reception of a real
event, and no proof of Meta's path, is claimed (R-1).
"""
from __future__ import annotations

import datetime
import os
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "db" / "gate"))

import run_binding  # noqa: E402

OUT = ROOT / "docs" / "gate" / "evidence" / "SLICE7-EVENT-STORE-COUNTS.txt"
STATUSES = ("RECEIVED", "PROCESSED", "IGNORED", "FAILED")
HEADING = "a sample measured right after the run"


def recorded_at(provenance: str) -> str | None:
    m = re.search(r"^Recorded    : (.+)$", provenance, re.M)
    return m.group(1).strip() if m else None


def database_problems(recorded: dict) -> list[str]:
    """The run's database must be recorded, and the environment name no other."""
    if "database" not in recorded:
        return ["the run's record names no test database: re-run record_test_run.py"]
    name, host = recorded["database"]
    problems = []
    for var, value in (("TURAB_TEST_DB", name), ("PGHOST", host)):
        if os.environ.get(var) not in (None, value):
            problems.append(f"{var} is {os.environ[var]!r}; the run used {value!r}: "
                            "the sample would be another database's")
    return problems


def skipped_problems(root: pathlib.Path = ROOT) -> list[str]:
    skipped = run_binding.counted(root / run_binding.REPORT).skipped
    return [f"the run skipped {skipped} cases; Slice 7's evidence requires none"] if skipped else []


def sample(name: str, host: str) -> tuple[dict[str, int], dict[str, int]]:
    import psycopg

    dsn = (f"host={host} user={os.environ.get('PGUSER', 'turab')} "
           f"password={os.environ.get('PGPASSWORD', 'turab')} dbname={name}")
    with psycopg.connect(dsn) as conn:
        by_status = dict(conn.execute("""
            SELECT processing_status::text, count(*) FROM turab.webhook_events
             GROUP BY 1""").fetchall())
        failed = dict(conn.execute("""
            SELECT coalesce(error_text, '(none)'), count(*) FROM turab.webhook_events
             WHERE processing_status = 'FAILED' GROUP BY 1""").fetchall())
    return {s: int(by_status.get(s, 0)) for s in STATUSES}, {k: int(v) for k, v in failed.items()}


def render(*, sampled_at: str, run_recorded: str, commit: str, fingerprint: str,
           report_sha256: str, database: str, host: str, counts: dict[str, int],
           failed: dict[str, int]) -> str:
    lines = [
        "TURAB — Slice 7: the event store, " + HEADING,
        "=" * 72,
        "Written by db/gate/slice7_event_store_counts.py (plan §6.4, G7-19 (i)).",
        "",
        f"Sampled at        : {sampled_at}",
        f"Run recorded at   : {run_recorded}",
        f"Run commit        : {commit}",
        f"Source fingerprint: {fingerprint}",
        f"Report sha256     : {report_sha256}",
        f"Test database     : {database}",
        f"Test host         : {host}",
        "",
        "webhook_events, by processing_status:",
        *[f"  {s:<10} {counts[s]}" for s in STATUSES],
        "FAILED, by error_text:",
        *([f"  {k:<20} {v}" for k, v in sorted(failed.items())] or ["  (none)"]),
        "",
        "WHAT THIS IS AND IS NOT",
        "  * A sample measured right after the run, from the run's test database. Not",
        "    the state at the moment of the last test, and never a PASS.",
        "  * The suite's test events. No reception of a real event, and no proof of",
        "    Meta's path, is claimed (R-1).",
        "  * Counts only: no event id, no reference, no payload.",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    recorded, problems = run_binding.check(ROOT)
    problems += skipped_problems() + database_problems(recorded)
    if problems:
        for p in problems:
            print("REFUSED:", p, file=sys.stderr)
        print("REFUSED: no sample is taken unless the run is bound, passing, unskipped, "
              "and its recorded database is the one sampled",
              file=sys.stderr)
        return 1
    provenance = (ROOT / run_binding.PROVENANCE).read_text()
    run_recorded = recorded_at(provenance)
    if run_recorded is None:
        print("REFUSED: the run's record names no time", file=sys.stderr)
        return 1
    database, host = recorded["database"]
    counts, failed = sample(database, host)
    OUT.write_text(render(
        sampled_at=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        run_recorded=run_recorded, commit=recorded["commit"],
        fingerprint=recorded["fingerprint"], report_sha256=recorded["report_sha256"],
        database=database, host=host, counts=counts, failed=failed), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: " + ", ".join(f"{s} {counts[s]}" for s in STATUSES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
