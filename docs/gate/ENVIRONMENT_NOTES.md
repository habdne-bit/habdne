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

---

## EN-02 · The application connects as a superuser that owns every table

**Observed:** 2026-10-05, Slice 5 step 0, measurement D
(`docs/gate/evidence/SLICE5-PLAN-MEASUREMENTS.txt`, at `658a86d`).
**Recorded:** in the review of `288bfdb`, which allowed this note to be
recorded now and kept the decision on the role separate (Slice 5 plan,
G5-13).

### Evidence
- **The role.** The application, the test suite and the gate all connect as
  `turab`, with `rolsuper = true`.
- **Ownership.** `turab` owns every table of the `turab` schema.
- **Privileges.** `has_table_privilege` is true for INSERT, UPDATE, DELETE
  and TRUNCATE on each of the six tables measured:
  - `match_reviews`;
  - `opportunities`;
  - `tasks`;
  - `interactions`;
  - `task_completion_events`;
  - `opportunity_responses`.

### What the evidence supports
- **No GRANT restricts the application.** Every protection of market history
  is a trigger:
  - `prevent_core_delete`;
  - `prevent_immutable_history_change`;
  - the gate triggers.
- **An ordinary statement fires those triggers.** Gate T9 and Slice 5's B18
  and B19 measured a refused DELETE.
- **A superuser, or the owner, is not bound by them.** Each of the following
  would avoid them. This is reasoned from the PostgreSQL 16 documentation,
  not measured here:
  - `ALTER TABLE … DISABLE TRIGGER`, which the owner may run (*ALTER TABLE*);
  - `SET session_replication_role = replica`, which a superuser may set
    (*Server Configuration — Client Connection Defaults*);
  - `TRUNCATE`, which "will not fire any ON DELETE triggers that might exist for the tables" (*TRUNCATE*, Notes).

### What is deliberately NOT concluded
- **This note is not a K06 result.** K06 reads: "Application role cannot
  hard-delete protected REQUEST/PROPERTY/OFFER/CLAIM/RESOLUTION/OPPORTUNITY
  history". Under this role, that has not been shown.
- **T9 is narrower than K06.** It proves that the triggers refuse an
  ordinary DELETE, and is labelled as such. It is not evidence for K06, and
  it is not cited as K06.
- **No document under `docs/gate` declares K06 PASS** at the time of this
  note.
- **No harm is claimed.** No path of the application issues TRUNCATE,
  DISABLE TRIGGER or `session_replication_role`.

### Handling
Until a non-superuser, non-owner application role has been tested and shown
unable to get past the guards:
- K06, and any release gate that depends on it, is reported **UNPROVEN**,
  never PASS;
- every result that rests on a trigger states that it holds against the
  application's ordinary statements only.

The remedy, and the point at which it becomes mandatory, are decided under
the Slice 5 plan, G5-13 (b). They are not decided here.

**Decided in the review of `3a797d8`:** G5-13 (b), option (ii). The remedy
is a separate, cross-cutting step, mandatory before any release gate. Until
a test under a non-superuser, non-owner application role passes, K06 stays
UNPROVEN, and STOP GATE E's document states it so.
