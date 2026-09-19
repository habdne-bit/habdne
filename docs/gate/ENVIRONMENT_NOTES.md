# Environment notes

Observations about the development environment that affect how results should
be read. Kept separate from engineering records on purpose: an environmental
interruption is not a defect, and a defect must not be excused as one.

---

## EN-01 · PostgreSQL is not running after a container restart

**Observed:** 2026-09-19, several times during one working session.
**Effect on results:** a test run started while the server is down reports
200+ errors that are all one connection failure. Those runs are not results.

### Evidence

| Observation | Value |
|---|---|
| `starting PostgreSQL 16.13` entries in `postgresql-16-main.log` | many, most recently 16:01:03, 16:17:08, 17:02:53 UTC |
| `database system was not properly shut down; automatic recovery in progress` | **12** occurrences |
| Log lines recording a shutdown request (`received … shutdown request`, `shutting down`) | **0** |
| Host uptime, measured at 17:12 UTC | **11 minutes** — the host booted at ≈17:01, immediately before the 17:02 start |
| Memory at the time of a restart | 576 MB used of 16 095 MB; no cgroup memory limit exposed |
| `dmesg` | not readable in this container, so an OOM kill could be neither confirmed nor excluded from that source |

### What the evidence supports

The server was **never asked to stop**: not once in the log. Combined with a
host uptime shorter than the session, the observations are consistent with
**the container being restarted by the platform, with PostgreSQL not
configured to start at boot**. Memory pressure is not supported — 3.6% of RAM
was in use — though the absence of `dmesg` means an external kill cannot be
excluded on that evidence alone.

### What is deliberately NOT concluded

No cause is asserted beyond the above. In particular this note does **not**
claim the application, the test suite or any migration caused it: no such link
was tested, and none of the restarts coincided with a specific operation in a
way that would support one. Equally it is not filed as "just the environment"
and forgotten — if a restart is ever observed to follow a particular operation
reproducibly, that is a new observation and this note is wrong.

### Handling

- `service postgresql start` and re-run; the affected run is discarded, not
  reported.
- `tests/conftest.py` now fails fast with one readable message naming this
  note, instead of 200+ identical connection errors. The check is
  `test_postgres_is_reachable`-adjacent and costs one connection attempt.
- Every result reported in the engineering records was produced by a run that
  completed against a live server. Where a run was interrupted, it was re-run
  and the re-run is what is reported.
