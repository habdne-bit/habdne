# Slice 6 · step 1 — migration `0007` (plan §5.1, parts A–D)

**Approved scope.** The review of `bd54216` approved every recommendation of
the decision table, among them the text of `0007` in plan §5.1 (parts A–D),
and so authorized step 1: "migration `0007`, exactly as §5.1 writes it, with
its tests and mutation record". Plan revision 4 records the approval, and
how its one-word form («اعتمد») is read (`SLICE_6_PLAN.md`, the review of
`bd54216`).

- **What this step does not contain.** No task, completion, diagnostic or
  correction code was written. `getTasks`, `postTasksTaskIdComplete`,
  CORRECTION-005 and the loader's extension are step 2's; the diagnostic's
  functions step 3's; the run's writes step 4's.
- **What the approval is not.** It approved a text. It is not a prior proof
  that the implementation is correct. §2–§4 report the runs on the actual
  migration.

**Status:** delivered, for review.

**Basis:**
- `docs/gate/SLICE_6_PLAN.md`, revision 4, §5.1 and the decisions it rests
  on: G6-4 (iii), G6-8 (ii) (a), G6-8 (iv) (a);
- step 0's measurements (`evidence/SLICE6-PLAN-MEASUREMENTS.txt` §T4, §E)
  and revision 3's (`evidence/SLICE6-PLAN-MEASUREMENTS-R3.txt`).

**Commits:** `62d3589` (plan revision 4), `cd5b868` (the migration, its
tests, its mutation script and the before-fix record), then the evidence
commits `d264628`, `a48d01d`, `37de36a`, `c6f59b0`.

---

## 1. What `0007` contains

`db/migrations/versions/0007_task_work_and_evidence.py`, sha256 `6b11a0f8…`.
The SQL is §5.1's text; only the Alembic wrapping is added.

| Part | Object | What it refuses | Decision |
|---|---|---|---|
| A | `prevent_task_completion_event_change`, BEFORE UPDATE OR DELETE on `task_completion_events`, calling the frozen `prevent_immutable_history_change()` | rewriting or deleting a completion event; and, through the FK's SET NULL, deleting an observation an event cites | G6-8 (iv) (a) |
| B | four `reason_codes`, category `TASK_OUTCOME`: `TASK_INFORMATION_OBTAINED`, `TASK_INFORMATION_UNAVAILABLE`, `TASK_PARTY_UNREACHABLE`, `TASK_NO_LONGER_NEEDED` | — (data; `WHERE NOT EXISTS`) | G6-8 (ii) (a) |
| C | `ux_one_open_task_per_subject`, partial unique index on `tasks` | a second OPEN or IN_PROGRESS diagnostic task for the same `(request, entity, id, gate, criterion, ordinal, basis)` | G6-4 (iii) |
| D | `prevent_cited_observation_change()` + `trg_cited_observation_unchanged`, BEFORE UPDATE OR DELETE on `observations` | changing or deleting an observation a completion event cites | G6-8 (iv) (a) |

**Properties stated, each tested:**
- **Part D is not sufficient alone** (F6-18, R1a). An uncommitted event is
  invisible to it, and the FK's FOR KEY SHARE does not conflict with a
  non-key UPDATE. `test_the_guard_alone_does_not_see_an_uncommitted_citation`
  pins this. The completion command's FOR SHARE lock, step 2, completes it.
- **Part D's consequence** for the rows an observation references: deleting
  its source, party or recording account is refused once it is cited, since
  the SET NULL is an UPDATE of the observation. The plan stated this as
  derived and unmeasured; it is now measured
  (`test_deleting_what_a_cited_observation_references_is_refused`), next to
  the same deletes accepted for an uncited observation. No application path
  deletes a source, a party or an account.
- **Part C covers diagnostic tasks only.** The NMI task, the identity task, a
  task without `source` and one of another source stay outside it
  (`test_tasks_of_the_other_writers_are_outside_the_index`).
- **Two NULL request ids never conflict** in part C's index: the approved
  text does not use NULLS NOT DISTINCT (PostgreSQL 16 documentation,
  §11.6). Pinned (`test_a_diagnostic_task_with_no_request_is_not_deduplicated`),
  not endorsed: the run always sets its request, and step 4's tests assert
  it.
- **Part B's codes change no fact.** `TASK_INFORMATION_OBTAINED` raises no
  verification level and proves nothing (review of `1fd7bdf`). This step
  has no command that could do either; step 2's completion test asserts it.
- **Part D's message carries the observation id.** It must never reach a
  response body; step 2's tests assert that.
- **Downgrade refused**, as `0005` and `0006`.

## 2. Before the fix (measured)

`evidence/SLICE6-STEP1-0007-BEFORE-FIX.txt`: the 55 tests, run in an isolated
worktree at `62d3589` (no `0007`), into which only the test file was copied.

- **34 failed:** every refusal of parts A, C and D ("DID NOT RAISE"); part
  B's five tests (no code); the index text; part A alone (the trigger to
  disable does not exist); and the race, where the contender was NOT blocked
  and both tasks committed.
- **21 passed, as they must at the base too:** the closed-work and
  key-component cases, the other writers' tasks, the NULL-request pin, the
  uncited deletes, and R1a's pin.
- **A first measurement was discarded, and the record says so.** Its event
  fixture used a part B code by default, so parts A and D failed on the
  outcome FK, not on the missing guard. The fixture now records events with
  no outcome code, as the frozen schema permits.

## 3. Existing tests that changed, and why

- `tests/test_migrations.py`:
  - `HEAD` is `0007_task_work_and_evidence`;
  - `test_0006_refuses_to_downgrade` asserts `0006`'s refusal on the
    revision itself, as `0005`'s has been since `0006`: `alembic downgrade`
    from head now stops at `0007`'s refusal;
  - added: `test_0007_refuses_to_downgrade`,
    `test_the_declared_deltas_for_0007_are_exactly_its_four_objects`;
  - `_migration_data`'s docstring now names `0007` as the second revision
    that writes rows.
- `db/gate/migration_deltas.py`: the four structural objects, with their
  digests and proving tests. Part B is data, not structure.

## 4. Mutation evidence

`evidence/SLICE6-STEP1-0007-MUTATIONS.txt`, run on the clean tree at
`cd5b868`, source fingerprint `190e31a9…6889`: **23/23 fail; none survives.**

| Mutation | Tests failing |
|---|---|
| A1 part A not created · A2 UPDATE only · A3 DELETE only | 10 · 1 · 9 |
| B1 a code missing · B2 another category · B3 inactive · B4 another label | 2 · 2 · 1 · 1 |
| C1 not unique · C2 OPEN only · C3 no `source` predicate | 8 · 5 · 3 |
| C4–C10 the key without request, entity, id, gate, criterion, ordinal, basis | 3 · 2 · 2 · 2 · 2 · 2 · 2 |
| C11 criterion not coalesced · C12 ordinal not coalesced | 1 · 1 |
| D1 part D not created · D2 UPDATE only · D3 DELETE only · D4 refuses nothing | 12 · 1 · 10 · 11 |

Each mutation was applied to the migration, the suite's database rebuilt by
`alembic upgrade head`, and the file restored with its sha256 checked.

## 5. The evidence round

Each row ran on a clean tree, source fingerprint `190e31a9…6889` (the
commits after `cd5b868` are evidence and documents only).

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Suite (`record_test_run.py`) | 2426 passed, 0 failed, 0 errors, 0 skipped | `c6f59b0` (run at `37de36a`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |
| PostgreSQL gate (`record_gate_run.sh`) | PASS; 70 database-level PASS notices; contract, inventory and policy table hold the same 67 operations | `37de36a` (run at `a48d01d`) | `evidence/gate-run.txt` |
| Authorization matrix | 183 rules; suite 2426/2426; no rule added (`0007` adds no authorization rule) | `a48d01d` (run at `d264628`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| `0007` mutations | 23/23 fail | `d264628` (run at `cd5b868`) | §4 |
| Before the fix | 34 failed, 21 passed, at `62d3589` | `cd5b868` | §2 |

**Limits that are part of these results:**
- **The guards hold against the application's ordinary statements only.**
  The tests run as `turab`, a superuser and the owner of every table
  (EN-02), which can disable these triggers, as one test does inside a
  rolled-back transaction.
- **K06 stays UNPROVEN.** `0007` is not evidence for K06.
- **These results are ours.** No independent run exists.

## 6. STOP GATE E after this step

`SLICE_5_STOP_GATE_E.md` is the record of Slice 5's tree, as STOP GATE D is
of Slice 4's. It is not regenerated.

**Measured on this step's tree:**
- `stop_gate_e_evidence.py --check` exits 1, with ONE problem: the document
  is stale. It reports no missing or failed mapped test, no unbound run, and
  no new writer.
- **What regeneration would change.** The generator was run, its word diff
  read, and the document restored:
  - the run's binding (commit, source fingerprint, report digest);
  - the case count, 2367 → 2426;
  - the proof's `approved_match_id`, a fresh id on every run;
  - the migration list, with `0007` added.

  Its 49 rows stay PASS.

## 7. What remains

- **Step 1 closes on review.**
- **Step 2:** `getTasks`, `postTasksTaskIdComplete` with the lock order of
  G6-8 (iv), CORRECTION-005 and the loader's extension (§5.2).
- **Standing:** G4-5R open, SALE only; K06 UNPROVEN.
