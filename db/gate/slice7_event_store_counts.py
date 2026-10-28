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
- the test database's name and host, the whole destination, and the server
  reached, as the run's record names them;
- the count of each `processing_status`, and of FAILED events by
  `error_text`. Nothing else: no event id, no reference, no payload.

**It refuses** (writing nothing, connecting to nothing) unless:
- the recorded run is bound to the current tree, with no failed or errored
  case (`run_binding.check`);
- it skipped no case: Slice 7's evidence requires zero skipped, which
  `run_binding.check` does not refuse (review of 8dd7921);
- the run's record names where the suite's connections went, and the server
  they reached (`Test destination`, `Test server`, written by
  `record_test_run.py`; reviews of 8dd7921 and 84280c0);
- the environment names no other destination: `TURAB_TEST_DB`, `PGHOST`,
  `PGHOSTADDR` and `PGPORT`, when set, must be the recorded values (a
  `PGHOSTADDR` set where the run had none is another), and no `PGSERVICE`
  is set.

The connection then names every destination parameter explicitly, from the
record, never from the environment. **Before any count is read**, the server
it reached must be the run's: the same cluster system identifier, address,
port and database. Otherwise nothing is written.

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


def destination_problems(recorded: dict) -> list[str]:
    """Checked before connecting: the run's destination and server must be
    recorded, and the environment name no other destination."""
    missing = [k for k in ("destination", "server") if k not in recorded]
    if missing:
        return [f"the run's record names no test {' or '.join(missing)}: re-run "
                "record_test_run.py"]
    problems = []
    for key, var in run_binding.DESTINATION_VARS.items():
        value = recorded["destination"].get(key, "")
        if os.environ.get(var) not in (None, value):
            problems.append(f"{var} is {os.environ[var]!r}; the run used {value or '(none)'!r}: "
                            "the sample would be another server's or database's")
    for var in run_binding.SERVICE_VARS:
        if os.environ.get(var):
            problems.append(f"{var} is set: a service file could send the sample elsewhere")
    return problems


class ServerNotTheRuns(RuntimeError):
    pass


def skipped_problems(root: pathlib.Path = ROOT) -> list[str]:
    skipped = run_binding.counted(root / run_binding.REPORT).skipped
    return [f"the run skipped {skipped} cases; Slice 7's evidence requires none"] if skipped else []


def sample(destination: dict[str, str], server: dict[str, str]
           ) -> tuple[dict[str, int], dict[str, int]]:
    """Counts from `destination`, every parameter explicit, read only once the
    server reached is shown to be `server`."""
    with run_binding.connect(destination) as conn:
        reached = run_binding.server_identity(conn)
        if reached != server:
            raise ServerNotTheRuns(f"the server reached is {run_binding.server_line(reached)}; "
                                   f"the run's was {run_binding.server_line(server)}")
        by_status = dict(conn.execute("""
            SELECT processing_status::text, count(*) FROM turab.webhook_events
             GROUP BY 1""").fetchall())
        failed = dict(conn.execute("""
            SELECT coalesce(error_text, '(none)'), count(*) FROM turab.webhook_events
             WHERE processing_status = 'FAILED' GROUP BY 1""").fetchall())
    return {s: int(by_status.get(s, 0)) for s in STATUSES}, {k: int(v) for k, v in failed.items()}


def render(*, sampled_at: str, run_recorded: str, commit: str, fingerprint: str,
           report_sha256: str, destination: dict[str, str], server: dict[str, str],
           counts: dict[str, int],
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
        f"Test database     : {destination['dbname']}",
        f"Test host         : {destination['host']}",
        f"Test destination  : {run_binding.destination_line(destination)}",
        f"Server reached    : {run_binding.server_line(server)}",
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
    problems += skipped_problems() + destination_problems(recorded)
    if problems:
        for p in problems:
            print("REFUSED:", p, file=sys.stderr)
        print("REFUSED: no sample is taken unless the run is bound, passing, unskipped, "
              "and its recorded destination is the one sampled",
              file=sys.stderr)
        return 1
    provenance = (ROOT / run_binding.PROVENANCE).read_text()
    run_recorded = recorded_at(provenance)
    if run_recorded is None:
        print("REFUSED: the run's record names no time", file=sys.stderr)
        return 1
    try:
        counts, failed = sample(recorded["destination"], recorded["server"])
    except ServerNotTheRuns as exc:
        print(f"REFUSED: {exc}: nothing is counted", file=sys.stderr)
        return 1
    OUT.write_text(render(
        sampled_at=datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d %H:%M:%S UTC"),
        run_recorded=run_recorded, commit=recorded["commit"],
        fingerprint=recorded["fingerprint"], report_sha256=recorded["report_sha256"],
        destination=recorded["destination"], server=recorded["server"], counts=counts,
        failed=failed), encoding="utf-8")
    print(f"wrote {OUT.relative_to(ROOT)}: " + ", ".join(f"{s} {counts[s]}" for s in STATUSES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
