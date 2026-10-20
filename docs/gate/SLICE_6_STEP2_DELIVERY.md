# Slice 6 · step 2 — `getTasks`, `postTasksTaskIdComplete`, CORRECTION-005

**Approved scope.** The review of `b6a08e7` authorized step 2 once the
addendum of step 1 was delivered, without waiting for OQ6-1 or OQ6-2, and
set its acceptance condition: **the proof that the completion locks the task
first, then the cited observation FOR SHARE, before it inserts the event**,
with the race orders tested and a typed refusal, writing nothing, when the
observation disappears. It also asked for CORRECTION-005 and the loader's
extension within the approved scope, and stated that OQ6-1 and OQ6-2 are no
licence to change the schema.

- **What this step does not contain.** No migration, no schema change, no
  diagnostic function (step 3), no write by the run (step 4). `0007` is
  unchanged.

**Status:** delivered, for review.

**Basis:** `docs/gate/SLICE_6_PLAN.md` revision 6: G6-8 (i)–(vii), G6-9,
§3.6, §3.7, §5.2, §6.2 (I02, K05), §6.3; F6-16 to F6-19; the measurements of
revision 3 (`evidence/SLICE6-PLAN-MEASUREMENTS-R3.txt`, R1–R3).

**Commits:** `038b6e8` (the code, its tests, the correction, the mutation
script, the "before" record); `93c4b3c` (the first mutation run kept; a test
added, a mutation corrected); `d09abbc` (the lock witness corrected); the
evidence commits `0a77a3d`, `31c1997`, `c3d2ec7`, `d4b8a11`, `b9a18e1`.

---

## 1. What step 2 contains

| Part | Where | What |
|---|---|---|
| the list (G6-9) | `services/tasks.py` `list_tasks`; `AccessService.list_tasks`; `GET /tasks` | every task, whichever writer raised it; `status` and `priority` compared as text; `assigned_to_me`; order URGENT, HIGH, NORMAL, LOW, then `created_at`, then `task_id`; `page`/`page_size` as the other lists; one LIST audit record with its count |
| the completion (G6-8) | `services/tasks.py` `prepare`, `record`; `POST /tasks/{task_id}/complete` | §2 below |
| the existence check | `CommandService.authorize_task_exists` | an unknown id is 403 `OBJECT_NOT_AUTHORIZED`, and the denial is recorded (§6, choice 1) |
| two problem codes | `api/problems.py` | `TASK_NOT_OPEN` 409; `EVIDENCE_OBSERVATION_NOT_FOUND` 422. Neither echoes an id |
| the audit (§3.7) | `audit_rows` | `task_completion_events` audited by the command; its `note` added to `WITHHELD` |
| CORRECTION-005 and the loader (§5.2, F6-19) | `auth/contract.py`; `CONTRACT_CORRECTIONS.yaml`; `CORRECTION-005-task-outcome-code.md`; the generator | §3 below |

## 2. The acceptance condition: the completion's locks

`services/tasks.py`, under READ COMMITTED, every refusal before the
idempotency key is claimed:
1. `SELECT … FROM tasks … FOR UPDATE`, the first statement on the task.
   DONE or CANCELLED: 409 `TASK_NOT_OPEN`;
2. if `evidence_observation_id` is given, `SELECT … FROM observations …
   FOR SHARE`. No row, including one deleted while the completion waited:
   422 `EVIDENCE_OBSERVATION_NOT_FOUND`;
3. the event; 4. the task DONE, with the event's `completed_at`.

**The proofs** (`tests/test_slice6_step2.py`). Each race test has a
`pg_blocking_pids` witness of the wait, and asserts the final rows:

| Test | The order | Observed |
|---|---|---|
| `test_the_task_is_locked_before_the_observation` | another transaction holds the task | C waits on it; **meanwhile an UPDATE of the observation under a 1 s `lock_timeout` goes through**: C holds no lock on it yet. Released, C completes |
| `test_r2a_r2c_…[R2a]` | C holds the observation; U updates its body | U waits on C; after C commits, part D refuses U; the body is the one cited |
| `test_r2a_r2c_…[R2c]` | C holds it; U deletes it | U waits; part D refuses it; the observation stays |
| `test_r2b_…` | U's UPDATE first, uncommitted | C waits on U; it cites the changed body; a later change is refused |
| `test_r2d_…` | U's DELETE first, uncommitted | C waits on U; then **422 `EVIDENCE_OBSERVATION_NOT_FOUND`: no event, the task OPEN, no audit row, no key consumed, the id not echoed** |
| `test_a_second_concurrent_completion_waits_and_is_refused` | two completions (F6-17, E4) | the second waits, reads DONE: 409; one event; its key not consumed |

**Mutations that remove or move the lock** (`evidence/SLICE6-STEP2-MUTATIONS.txt`):
- **L2, no observation lock:** R2a gives exactly R1a's result: U did not
  wait (`u_waited_on_c: False`), C answered 200, and part D did not refuse
  U, so the cited body was changed after the citation. R2b, R2c and R2d fail
  too (4 tests).
- **L3, FOR KEY SHARE (the foreign key's mode):** R2a and R2b fail; R2c does
  not. A key-share lock does not conflict with a body UPDATE, and does
  conflict with a DELETE (PostgreSQL 16, §13.3.2, Table 13.3), as R1 measured.
- **L4, the observation before the task:** the order test fails.
- **L1, no task lock:** the second completion and the order test fail.

## 3. CORRECTION-005 and the loader's extension

- **The effective body** is an operation-local copy of `TaskCompletionInput`:
  - `outcome_code` required, of type `string`, one of the four codes;
  - `note` and `evidence_observation_id` unchanged.

  The frozen component is unchanged in the effective contract, in its text
  too. The component is referenced once in the frozen file.
- **The loader** (`load_request_body_narrowings`) now accepts three things,
  each with its narrowing check (the correction's note, §3):
  - a `$ref` body, when this operation alone uses the component;
  - `non_null`;
  - `enum`.
- **One transformation.** `narrowed_body_schema` is used by the runtime
  (`effective_request_body`, which the route reads its enum from) and by the
  generator. The generator no longer transforms a body on its own.
- **CORRECTION-004's effective text is unchanged byte for byte.** Measured:
  `--check` passed on the refactored generator before CORRECTION-005 was
  added. A first version broke a YAML anchor (`*id002`), and that was
  corrected before any commit. A test checks that the runtime body equals
  the committed effective body.
- **The same bodies through both** (`test_the_route_refuses_exactly_what_the_effective_schema_refuses`,
  15 bodies): absent, null, an empty string, each of the four codes, `OTHER`,
  `DEAL_CONFIRMED`, an unknown code, a number, an undeclared field, a note of
  null, a malformed id.
  - The schema's verdict comes from a checker limited to the keywords the
    schema uses; a test asserts it uses no other.
  - Every refused body is 422 and writes nothing; the value is not echoed.
- **The enum equals the ACTIVE codes of category `TASK_OUTCOME`** in the
  database (`test_the_enum_is_the_active_task_outcome_codes_of_the_database`).

## 4. The other properties, each tested

- **§3.6, I02:**
  - the event keeps `outcome_code`, `note` and `evidence_observation_id`
    exactly;
  - a failure injected between the event and the task leaves neither row,
    no audit row, and no key.
- **G6-8 (v):** a VERIFY_DOCUMENT task, raised by a real NEED_MORE_INFORMATION
  review, is completed with `TASK_INFORMATION_OBTAINED` and an evidence
  observation. The digests of 17 tables are unchanged:
  - properties, attributes, offers;
  - requests and their criteria;
  - claims, claim evidence, verification events, resolved values;
  - consents and bindings;
  - matches, criterion results, reviews, diagnostics, opportunities;
  - observations.
- **G6-8 (vii):** a DONE task stays DONE; a second completion is 409 and
  changes nothing.
- **§3.7:** two audit rows (the event INSERT, the task UPDATE), by the
  caller's account. The note is absent from the audit row and kept in the
  event.
- **Part D's message never reaches a response.** It was forced to fire
  inside the command: the response is `INTERNAL_ERROR`, with neither the id
  nor the message, and nothing is written.
- **K05:** a replay returns the first response and writes nothing; another
  body on the key is 409.
- **G6-9:**
  - the order holds over every page of the whole list;
  - a value naming no status or priority returns nothing, with 200;
  - `assigned_to_me` keeps the caller's tasks only (the assignment is a SQL
    fixture: no command assigns, F6-7);
  - paging bounds are 422.
- **G6-9, every writer's task is listed:**
  - the NMI task comes from the review command;
  - the identity task comes from `identity.raise_review_work`, called on a
    real open match;
  - the diagnostic task is a fixture of step 4's payload shape.

  No seller expectation, reviewer text or observation body reaches the
  list.
- **§6.3:**
  - ADMIN, OPERATOR and REVIEWER each list and complete;
  - a customer is 403 on both, writing nothing, and both denials are
    recorded;
  - anonymous is 401 on both.

  The matrix has six rules for the two operations (§7).

## 5. Before, and what changed during the step (measured)

- **Before** (`evidence/SLICE6-STEP2-BEFORE.txt`). The two test files were
  run in a worktree at `4e9748e`. Both fail at collection: they import names
  this step adds. No test can therefore be read as "failing for the right
  reason" from this run; the mutations are what tie each rule to its tests.
  An HTTP probe at the base: `GET /tasks` and `POST /tasks/{id}/complete` are
  404, and nothing is written.
- **The first mutation run** (`evidence/SLICE6-STEP2-MUTATIONS-FIRST-RUN.txt`,
  at `038b6e8`) left two survivors:
  - **K2** showed a missing test: a type LIST without null. Only a plain
    `string` was tested, which is refused by the half of the condition K2
    leaves. The case was added;
  - **W4** was an EQUIVALENT mutation: `now()` is the transaction's start,
    and so is the event's default. It now writes `clock_timestamp()`.
- **A failed witness** (`evidence/SLICE6-STEP2-R2D-WITNESS.txt`). In one full
  run, R2d's witness failed while the behaviour was right (422, nothing
  written).
  - **Refuted, by measurement:** slow app start-up; an exhausted pool (0
    connections checked out at every test); a database wait (no lock wait
    over 1 s, sampled every 0.5 s through a full run).
  - **What the runs show instead:** stalls of several seconds, outside the
    database, in tests of Slices 3–6 alike. Their cause is not identified.
  - **The fix:** the witness waits until the thread waits or ends, with a
    60 s cap, not a fixed 8 s. The mutations were run again on that tree,
    with the same counts.
  - **Not changed:** the Slice 5 tests that share the 8 s pattern carry the
    same fragility.

## 6. Choices the plan did not fix, stated for review

1. **An unknown task id is 403 `OBJECT_NOT_AUTHORIZED`, recorded.** This is
   the staff convention of `authorize_match_exists` (Slice 5). The plan names
   no answer for it.
2. **The body is validated before the role check,** as on every route with
   a body model. Measured: a customer with a malformed body gets 422, on this
   route as on the Slice 5 review.
3. **`assigned_to_me` absent means false.**
4. **The task's `completed_at` is the event's,** which is the transaction's
   start.
5. **`TASK_NOT_OPEN`'s detail names the status** (DONE or CANCELLED), never
   an id.
6. **The list is returned exactly** (`ExactJSONResponse`), as the other
   staff reads that carry stored payloads.
7. **CORRECTION-005's `approved` date** is 2026-10-17, the date of the
   commit that recorded the approval (`62d3589`). The review message carries
   no date in the repository.
8. **§7, condition 10 (the writers of `tasks`).**
   - The completion UPDATEs a task (`status`, `completed_at`) and raises
     none. I read the condition as being about who RAISES tasks, so
     `tasks.py` would not be counted among those writers.
   - That reading is the reviewer's to confirm. It affects the closure
     evidence of §6.4.

## 7. The evidence round

Each row was run on a clean tree, source fingerprint `be9900a0…a92e` (from
`d09abbc`; the later commits are evidence only). PostgreSQL 16.15, in a fresh
cloud container.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations | 26/26 and 8/8 fail; none survives | `31c1997` (run at `d09abbc`) | `evidence/SLICE6-STEP2-MUTATIONS.txt` |
| Authorization matrix | 189 rules (6 added, all PASS); suite 2511/2511 | `c3d2ec7` (run at `31c1997`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS; 70 PASS notices; effective contract and inventory current; 67 operations equal | `d4b8a11` (run at `c3d2ec7`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | 2511 passed, 0 failed, 0 errors, 0 skipped; `bound` | `b9a18e1` (run at `d4b8a11`) | `evidence/TEST-RUN-PROVENANCE.txt` |

- **Discarded, and named:**
  - the matrix run in which R2d's witness failed (§5);
  - one gate run, started without the `PG*` variables, which connected as
    `root` and stopped at step 2.

  Neither is reported as a result.
- **STOP GATE E:** `--check` exits 1 with the one problem of step 1: the
  document is stale. It is not regenerated.
- **Suite count:** 2428 → 2511. That is 50 + 29 new tests, plus 2
  architecture cases for the new route module, plus 2 parametrized cases of
  `test_mutation_tools.py` for the new script.

**Limits that are part of these results:**
- **The superuser.** The guards and locks are proven under `turab`, a
  superuser (EN-02). **K06 stays UNPROVEN.**
- **U is raw SQL.** In the race tests, U is a SQL statement, because no
  application path writes observations (step 0). If one is ever added, its
  lock order must be checked against §2.
- **These results are ours.** No one else has run them. The package of
  step 1's addendum was not rebuilt.

## 8. What remains

- **Step 2 closes on review.** Choice 8 of §6 needs a decision.
- **Step 3:** the pure functions (G6-2, G6-3, G6-5, G6-6, G6-7), their
  registry entries and replay (G6-11), with no write yet.
- **Standing:**
  - OQ6-1 and OQ6-2 are open, not approved;
  - G4-5R is open, SALE only;
  - K06 is UNPROVEN.
