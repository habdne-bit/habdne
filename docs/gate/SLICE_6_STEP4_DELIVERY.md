# Slice 6 · step 4 — the run writes the format-2 diagnostic and raises its tasks

**Approved scope.** The review of `922a100` authorized step 4 as plan §8
describes it:

> the run writes them; tasks from the diagnostic only if G6-4 (a); G6-10.

It added two required experiments:
1. a run that writes a REAL format-2 row, which is then replayed;
2. the MEASURED supersession of an older match, in the match queue and at
   approval, after the registry digest changed.

The step's evidence also restates the limit of §5.4 (§6 below).

**Status:** delivered for review. Not closed.

**Basis:** `docs/gate/SLICE_6_PLAN.md` revision 11:
- G6-4 (a) with (i)–(iii), (iv) (a), (v) and (vi);
- G6-10 (a) and G6-11;
- §5.3 (OQ6-1's obligation), §5.4, §7 condition 10, §8 step 4.

**Commits:**
- `c67e42d`: plan revision 11, the review of `922a100`;
- `820bec7`: the code and its tests;
- `c4b8c98`: the before record and the mutation script;
- the evidence commits `7ae9cec`, `bc3dfec`, `b07cd3f` and `3381525`.

---

## 1. What the run does now (`services/matching_run.py`)

In one transaction, in this order (G6-4 (i)):

1. It stores each match, or finds the identical one, as before. `_store`
   now also returns whether THIS run inserted the row.
2. It builds `evaluated`. Each entry carries:
   - `property_id`, `offer_id` and `match_id`;
   - `input_hash`;
   - `stored`: `NEW` if this run inserted the match, otherwise
     `EXISTING`.

   This is the fact (R) verifies (G6-11).
3. It reads the location chains of the requested locations
   (`diagnostic.read_location_chains`).
4. It calls `diagnostic.compute` (step 3) on the stored matches, the
   chains, `evaluated` and the exclusions.
5. It writes the diagnostic row with:
   - `blocker_summary` format 2 (`turab.blocker-summary/2`);
   - `suggested_actions` and `relaxation_scenarios` as computed;
   - the input hash of the document `turab.diagnostic-input/2`, which adds
     `requested_location_chains` to format 1's document.
6. It raises one task per HIGH entry (`_raise_tasks`; §2).

**The suggestions stay what was computed.** `suggested_actions` is written
before any task insert, and nothing about tasks enters it (G6-4 (iii),
revision 3).

**D1's "no task" is replaced** (G6-4 (vi)). `matching_run.py` is the third
creator of `tasks`, after `identity.py` and `match_review.py`. This is
stated in the module docstring.

## 2. The tasks (G6-4 (ii), (iii))

| Field | Value |
|---|---|
| `task_type`, `reason_code` | the entry's type; the subject's `reason_code` |
| `priority` | `HIGH`: only HIGH entries are raised |
| `title` | fixed English per type: `VERIFY_DOCUMENT` "Verify the property's document"; `CONFIRM_PRICE` "Confirm the offer's price terms"; `OTHER` "Obtain the missing information" |
| `request_id` | the run's request |
| `property_id` | the subject itself for a `PROPERTY` subject; otherwise the property of the entry's single candidate; **null** when the entry has several candidates |
| `match_id` | the match of the entry's single candidate; **null** when the entry has several candidates |
| `payload` | `{diagnostic_run_id, "source": "DIAGNOSTIC", subject}`, where `subject` is exactly the six keys `entity`, `id`, `gate`, `criterion`, `ordinal`, `basis` |

**How each insert runs:**
- each insert has its own savepoint, and its INSERT is audited
  (`audit_rows`);
- a unique violation **whose `constraint_name` is
  `ux_one_open_task_per_subject`** means the work is already open. The
  savepoint is rolled back, nothing is written about it, and the next entry
  is tried;
- **any other error fails the whole run,** which writes nothing.

## 3. The two required experiments (review of `922a100`)

### 3.1 A real format-2 row, written by the run, then replayed

`test_a_row_the_run_wrote_is_format_2_and_replays`.

**The world:** a request with a LOCATION criterion and a DOCUMENT_TYPE
criterion. It has three properties:
- one whose document is UNKNOWN;
- one in another location;
- one without an offer, which is excluded.

**What the test reads.** It reads the row **as the database holds it**,
through `jsonb_build_object(...)::text` and `exact_json`, and asserts:
- the format is `turab.blocker-summary/2`;
- `versions` are `diagnostic.value@1`, `actions@1` and `relaxation@1`;
- both entries are `NEW`;
- `suggested_actions`, `relaxation_scenarios`, `excluded_counts` and
  `requested_location_chains` are all non-empty;
- the response's `suggested_actions` equals the row's.

**The result:** `diagnostic_replay.replay` gives `{"R": [], "D": []}`. A
second run on the same facts records both entries `EXISTING`, and also
replays with no problem.

**The input document** (`test_the_input_hash_covers_the_requested_chains`):
- two runs on unchanged facts give the same diagnostic input hash;
- re-parenting the requested location alone, and nothing else, changes it;
- the location is restored afterwards.

### 3.2 The supersession of an older match, measured

`test_an_older_match_is_superseded_in_the_queue_and_at_approval`.

1. **The old match.** It is written under `HISTORY[0]`'s registry (digest
   `7ddf4747…`, 20 pairs, before step 3), through Slice 4's
   `_registry_of`. It is ELIGIBLE and appears in
   `GET /backoffice/queues/matches`.
2. **The new match.** A run under the current registry (digest
   `47188d01…`), on UNCHANGED facts, stores a **NEW** match. The registry
   digest differs, so the input hash differs (G4-13).
3. **The queue** shows the new match and not the old.
4. **Approving the old match** is refused with **409 `MATCH_SUPERSEDED`**,
   and its `match_reviews` count is unchanged.
5. **Approving the new match** returns 200.

**Reading.** The supersession is Slice 5's (G5-2), and step 4's code takes
no part in it. The test therefore **passes on both trees**, before and
after step 4 (§5). It measures what the step 3 note had only derived (its
§5 and §8.3).

## 4. The tests of G6-4, G6-10, OQ6-1 and §7(10)

`tests/test_slice6_step4.py` has 13 tests. Besides the three of §3:

| Test | What it proves |
|---|---|
| `test_a_high_suggestion_raises_one_task_with_its_subject` | G6-4 (ii): type, priority, status, title, reason; request, property and match; the payload is **exactly** the three keys, and its subject is exactly the six keys and equals the suggestion's subject; one audit INSERT |
| `test_every_diagnostic_task_carries_a_complete_key` | **OQ6-1's obligation** (§5.3), over **every** diagnostic task the suite has written so far in the database (selected by `diagnostic_run_id` or by a `source` matching `diagnostic` case-insensitively): `request_id`, `entity`, `id`, `gate` and `basis` are non-NULL, and `source` is `"DIAGNOSTIC"` exactly. The test writes one task itself, so the check is never empty |
| `test_normal_suggestions_raise_no_task` | G6-4 (a): two unknowns, neither high-value, both suggested as NORMAL; no task |
| `test_g6_4_re_run_writes_a_second_diagnostic_and_no_new_task` | G6-4 (iii): identical suggestions; one task, still naming the first diagnostic; **no audit row** about the refused attempt; the second row replays |
| `test_work_taken_up_is_not_raised_again_and_done_work_is` | F6-15: an IN_PROGRESS task is not raised again. Once the task is completed through the contract (DONE), the next run raises a new task naming its own diagnostic |
| `test_g6_10_a_task_whose_cause_has_gone_stays_open` | G6-10 (a): once the document is recorded, the run no longer suggests the work, and the task stays OPEN, stating its work by itself |
| `test_a_task_failure_other_than_open_work_fails_the_run_writing_nothing` | G6-4 (iii): the task's audit write fails (injected). The run answers 500 `INTERNAL_ERROR` and writes no match, no diagnostic, no task and no idempotency key |
| `test_an_nmi_task_and_a_diagnostic_task_are_independent_records` | G6-4 (iv) (a): two tasks on one match, one per source |
| `test_g6_4_concurrent_runs_raise_one_task_and_staff_see_a_self_contained_task` | G6-4 (iii) and (v): see below |
| `test_the_writes_to_tasks_are_exactly_those_decided` | §7 condition 10, **by kind**: INSERT in `identity.py`, `match_review.py` and `matching_run.py`; UPDATE in `tasks.py` only, setting exactly `status = 'DONE', completed_at = :at`; no DELETE. `tasks.py` is in the inventory |

**The concurrency test, in detail:**
- **Run A** raises its task and is held before its commit, in
  `_raise_tasks`.
- **Run B**, started later, inserts the same work. The `pg_blocking_pids`
  witness shows that B waits on A's backend. B does not end while A is
  held; it ends after A commits.
- **Both runs answer 201.** One OPEN task results, naming A's diagnostic.
  Both suggestion lists are equal, and both rows replay.
- **What staff see:**
  - `GET /requests/{id}/diagnostic` returns B's row (F6-12);
  - `GET /tasks` lists the task naming A, with its type, priority, reason
    and subject (if the task lies past the first page, the test reads every
    page);
  - `GET /matches/{match_id}` returns 200.

**One setup choice, stated.** The F6-15 test puts the task IN_PROGRESS by
direct SQL. No contract operation sets IN_PROGRESS (F6-7), so only the
test can create this state. The DONE transition goes through the contract
(`postTasksTaskIdComplete`).

## 5. Delivered tests changed, each because G6-4 replaced D1

| File | Change | Why |
|---|---|---|
| `tests/test_slice4_step7.py` | The D1 test now accepts NORMAL suggestions and no task. The race test expects `(match_id, True, True), (match_id, False, False)`. The writer test is renamed `…_and_the_run_creates_its_tasks_only` and names the three creators | D1's "no task" and empty suggestions end with G6-4 (vi). `_store` returns a third value |
| `tests/test_slice5_step2.py` | `_tasks` filters `payload ? 'match_review_id'`; the writers test includes `matching_run.py` | a match may now also have a diagnostic task (G6-4 (iv) (a)) |
| `tests/test_slice6_step2.py` | two queries filter `payload ? 'match_review_id'` | same |
| `tests/test_slice6_step3.py` | the boundary test `test_the_run_still_writes_format_1_and_no_suggestion` is **removed**, and the docstring updated | it asserted step 3's boundary ("the run is unchanged"), which step 4's authorization ends |

No other assertion of a delivered test was weakened.

**The suite count:** 2562 → 2576. The change is −1 (the boundary test
removed), +13 (this file) and +2 (the two parametrized checks that
`test_mutation_tools` runs on each mutation script).

## 6. The limit of §5.4, restated (review of `922a100`)

- **What is and is not pinned.** `by_reason`, `candidates_evaluated` and
  the summary's base come from `explain.blocker_summary`, Slice 4's
  format-1 builder. That builder is **not pinned**. The three pins of step 3
  (`diagnostic.value@1`, `diagnostic.actions@1`, `diagnostic.relaxation@1`)
  **do not cover it**, and this note credits them with no such coverage.
- **What its explicit failure is, and is not.** A change of its output
  would make the replay of an old row fail (D), loudly. That failure is
  **not** a proof that the old row can be replayed.
- **Required before any later change** of this function that affects the
  summary:
  - keep the historical computation (or a version of it);
  - test the replay of an old row and of a new row.
- **Step 4 does not change it.** The diff of `820bec7` touches
  `matching_run.py` only in `src/`.
- **But step 4 widens what depends on it.** Every row the run now writes is
  format 2, built on that function's output, so every such row depends on
  it.

## 7. The before record (`evidence/SLICE6-STEP4-BEFORE.txt`)

The 13 tests were run on `c67e42d` (the unchanged code), in a worktree:
- **12 failed,** each for the absence of step 4:
  - the row is format 1;
  - the diagnostic's input hash ignores the chains;
  - no task is raised;
  - the run is not a writer of `tasks`.
- **1 passed,** as it must: the supersession test (§3.2).
- **A first attempt is discarded,** and named in the record. It ran without
  the venv on `PATH`, so `alembic` was not found and the 13 tests ended in
  ERROR.

## 8. Mutations (`db/dev/mutate_slice6_step4.py`)

19 mutations, each of which weakens one rule in `matching_run.py`. They are
run against `tests/test_slice6_step4.py` alone.

- **W1–W6, the row:**
  - no suggestion written;
  - no scenario written;
  - `evaluated` empty;
  - every entry recorded `NEW`;
  - the chains missing from the input hash;
  - the chains not read.
- **T1–T13, the tasks:**
  - no task raised;
  - NORMAL entries raised;
  - every error swallowed;
  - open work not skipped;
  - no savepoint;
  - no `source`;
  - no `basis` in the subject;
  - no `diagnostic_run_id`;
  - no property;
  - no match;
  - priority NORMAL;
  - no audit;
  - no reason.

| Run | Result | Counts |
|---|---|---|
| `SLICE6-STEP4-MUTATIONS.txt` | 19/19 killed; none survives | W1:5 W2:1 W3:3 W4:3 W5:1 W6:2 T1:8 T2:1 T3:1 T4:6 T5:6 T6:7 T7:6 T8:4 T9:1 T10:3 T11:2 T12:2 T13:2 |
| `SLICE6-STEP4-MUTATIONS-REPEAT.txt` | 19/19 killed; none survives | **identical, line by line** |

**The conditions of both runs:**
- base `c4b8c98`, on a clean tree;
- source fingerprint `dbe27b8d…2daa`;
- `src` identical to `c4b8c98` after each run.

**No equivalent mutation and no accidental kill** was found, so none was
removed or fixed.

## 9. The evidence round

Every row was run on a clean tree, with source fingerprint
`dbe27b8d68fea129a4f84413d04b2cc9064d0af07cad7953a8a908bab2bd2daa`, on
PostgreSQL 16.15.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations, twice | 19/19 and 19/19, identical counts | `7ae9cec` (runs at `c4b8c98`) | `evidence/SLICE6-STEP4-MUTATIONS.txt`, `…-REPEAT.txt` |
| Authorization matrix | 189 rules, unchanged (step 4 adds no operation); suite 2576/2576 | `bc3dfec` | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS; 70 PASS notices; 67 operations equal. The body is identical to step 3's run at `ebce6ee`; only the header differs | `b07cd3f` (run at `bc3dfec`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | 2576 passed, 0 failed, 0 errors, 0 skipped; `run_binding.py`: `bound` | `3381525` (run at `b07cd3f`) | `evidence/TEST-RUN-PROVENANCE.txt` |

- **STOP GATE E:** `--check` exits 1, with the one known problem: the
  document is stale. This is unchanged from earlier steps.
- **One discarded gate run.** It ran without the `PG*` variables, so it
  connected as `root`. It was not committed.
- **During the mutation runs,** nothing was committed. The runner mutates a
  source file temporarily, with a `.orig` backup.

## 10. Choices made in this step, put to the reviewer

1. **A shared subject.** When an entry has several candidates,
   `property_id` and `match_id` are null, unless the subject is itself a
   PROPERTY. The task then states its work through its subject and
   `request_id`. The alternative was to choose one candidate, which would
   name a match the work is not specific to.
2. **The OTHER title,** "Obtain the missing information". G6-4 (ii) fixes a
   title per type but does not word it.
3. **The payload holds exactly three keys.** It is
   `{diagnostic_run_id, source, subject}`, with no copy of the suggestion's
   other fields. The trace of creation is the task row (G6-4 (iii)).
4. **Open work is recognized by the constraint name** (`constraint_name`),
   not by SQLSTATE 23505 alone. A unique violation on another constraint
   therefore fails the run, as G6-4 (iii) requires ("any other error").
5. **The order inside the transaction:** matches, then the diagnostic row,
   then the tasks. This follows G6-4 (i); a refused run writes nothing.

## 11. Limits, carried unchanged

- **The application role.** The tests run as a superuser (EN-02). K06 is
  **UNPROVEN** (G6-12). An OPEN task can be deleted by a superuser, which is
  the stated limit of the trace in G6-4 (iii).
- **OQ6-1 and OQ6-2 stay open.** Step 4 proves OQ6-1's obligation by test
  (§4) and changes no schema.
- **G4-5R is open,** and the scope is SALE only.
- **These results are ours.** The reviewer did not re-run them.

## 12. What remains: step 5

Step 5, authorized only after this step is closed, covers:
- the mandatory and red-team tests end to end (§6.1, §6.2);
- their mutations;
- the closure evidence `SLICE_6_EVIDENCE.md` (§6.4), which:
  - inventories the writes to `tasks` by kind (§7(10));
  - restates the limit of §5.4.
