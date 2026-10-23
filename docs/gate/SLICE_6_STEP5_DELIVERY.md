# Slice 6 · step 5 — the mandatory and red-team tests end to end, and the closure evidence

**Approved scope.** The review of `0fae42c` closed step 4 and authorized
step 5 "as the plan defines it" (§8):

> the mandatory and red-team tests end to end, mutations, the closure
> evidence (§6.4).

It added two requirements:
1. **The end-to-end tests cover a HIGH task shared by two candidates,** whose
   `match_id` is null and which stays understandable in `GET /tasks`.
2. **The closure evidence states two limits explicitly:**
   - the replay does not recompute the diagnostic row's `input_hash`, nor
     compare it with the stored one;
   - `explain.blocker_summary` is not pinned (§5.4).

**Status:** delivered at `3657973`; **not closed** in the review of `3657973`,
which decided F6-21 and F6-22 and asked for a correction. The correction is
delivered for review (§13). **Slice 6 is not declared closed here;** that is
the reviewer's decision.

**Basis:** `docs/gate/SLICE_6_PLAN.md` revision 13: §6.1, §6.2, §6.4, §7,
§5.4, §8 step 5; the review of `0fae42c`.

**Commits:**
- `4dd8cf4`: plan revision 13, the review of `0fae42c`;
- `a64b5ec`: the end-to-end tests, the before record and the mutation
  script;
- `15032f2`: the first mutation run kept, and mandatory test 2 strengthened;
- `b6d0d19`: the two mutation runs;
- `7f15581`: the closure-evidence generator and its tests;
- the evidence commits `0fcd66b`, `a2c1018`, `0ec7204` and `352493a`
  (`SLICE_6_EVIDENCE.md`).

---

## 1. What step 5 contains

**No line of `src/` changes.** `src/` is identical to `0fae42c`; the source
fingerprint changes only through the new files of `db/` and `tests/`.

| Part | Where | What it is |
|---|---|---|
| the end-to-end tests | `tests/test_slice6_step5.py` (11) | §6.1, §6.2, the review of `0fae42c`, over HTTP |
| the closure-evidence generator | `db/gate/slice6_evidence.py` | `SLICE_6_EVIDENCE.md` from the bound run, with `--check` (§6.4); not a STOP GATE |
| its tests | `tests/test_slice6_evidence.py` (20) | STOP GATE E's experiments, repeated on a copy of the tree |
| the mutation script | `db/dev/mutate_slice6_step5.py` (14) | M (mandatory), S (shared task), R (red-team) |
| the closure evidence | `docs/gate/SLICE_6_EVIDENCE.md` | generated; do not edit |

## 2. "End to end": what it means here

**Made by the API, in every test of `test_slice6_step5.py`:**
- the request, its criteria, its state (CONTACTED → QUALIFIED → ACTIVE) and
  its confirmation;
- the seller parties and their consent grants;
- the properties, their confirmation and their documents (through
  `POST /resolutions`);
- the offers, their state, their terms confirmation and their consent
  bindings.

**Not made here:** the seed's reference data (locations, the policy, the
reason codes) and the test accounts.

**Driven over HTTP:** the run, `GET /requests/{id}/diagnostic`,
`GET /tasks`, `GET /properties/{id}`, `GET /matches/{id}`,
`POST /observations` and `POST /tasks/{id}/complete`.

**Where the database is read directly,** and why:
- to replay a stored row (`diagnostic_replay.replay`, as G6-11 defines it);
- to check what was NOT written (I03's versions, D02's audit rows, F6-21's
  audit row).

## 3. The three mandatory tests (§6.1)

| # | End-to-end test | What it shows |
|---|---|---|
| 1 | `test_mandatory_1_over_http_the_document_task_outranks_the_new_location` | R-001, P08 and P03. The first suggested action is P08's VERIFY_DOCUMENT, HIGH. The location is a scenario only, `subordinate_to` that action. `GET /tasks` lists one task for the request: HIGH, P08's match. No action or task names P03. The row replays |
| 2 | `test_mandatory_2_over_http_three_hard_failures_raise_no_task` | Two APARTMENTs, each failing LOCATION, BUDGET_MAX and PROPERTY_TYPE: one with its document UNKNOWN and **no consent** (so a permission reason too), one with its document **known**. No action, no scenario, no task. The unknown is counted blocking, not actionable |
| 3 | `test_mandatory_3_over_http_the_magnitudes_after_the_document_fails` | M-13: P08's document is resolved to another document (a FAIL), and a third property is at max + 1,500,000, not negotiable. Three magnitudes: `budget_delta_dzd` 1,500,000 at the asking price; the widening `COMMUNE` to the parent of ADR-NEW-TIL; the document named, only if the user chooses it. No `adjacent_zone` (F6-3). Each near match would reach ELIGIBLE |

The function-level tests of step 3 stay mapped beside them in the closure
evidence.

## 4. The review of `0fae42c`

### 4.1 A HIGH task shared by two candidates

Two shapes were found end to end. Both are tested.

| Test | Shared by | `property_id` | `match_id` |
|---|---|---|---|
| `test_a_high_task_shared_by_two_offers_names_no_match_and_is_understood` | two offers of one property (the PROPERTY's document) | the property | **null** |
| `test_a_high_task_shared_by_two_properties_names_only_the_request` | two properties (the REQUEST's maximum, REQUIRED and not stated) | **null** | **null** |

**What makes the task understandable in `GET /tasks`,** as asserted:
- **two offers:**
  - the type, priority, title ("Verify the property's document") and reason
    (`DOCUMENT_NOT_KNOWN`);
  - the subject (PROPERTY, the property, DOCUMENT_TYPE), which equals the
    diagnostic entry's subject;
  - the entry's two candidates are the run's two matches, and the property
    and both matches are readable.

  The work is then completed over HTTP, with an observation as evidence,
  and the document resolved. The next run suggests nothing and raises
  nothing, and the task stays DONE. Both rows replay.
- **two properties:**
  - `request_id` and the subject: entity REQUEST, criterion BUDGET_MAX,
    basis BUDGET_MAX_NOT_STATED;
  - `reason_code` is null (the basis has none), and the request's
    `budget_max_dzd` is null.

  **Its title is the subject of F6-22 (§6).**

### 4.2 The two limits, stated in the closure evidence

- **The diagnostic's own `input_hash`.** Measured by
  `test_limit_the_replay_does_not_read_the_diagnostics_own_input_hash`:
  - a document carrying the stored hash, sixty-four zeros, or none replays
    with `{"R": [], "D": []}`;
  - `diagnostic_replay.py` reads no row of `match_diagnostic_runs`.

  The generator lists this test as a **LIMIT**, never PASS (its §5.1).
- **`explain.blocker_summary`.** The generator computes from `rule_pins.py`
  that the three pins of step 3 are present, and that no pin names
  `blocker_summary`. It restates §5.4 (its §5.2).

## 5. Red-team (§6.2)

| Case | Test(s) |
|---|---|
| I01 | mandatory test 1 |
| I02 | step 2's `test_i02_a_failure_between_the_two_writes_leaves_neither` and the completion test (over HTTP) |
| I03 | `test_i03_a_scenario_changes_no_request_and_an_explicit_criterion_does`: the run that produces +1,500,000 leaves `GET /requests/{id}` identical. A criterion added by `POST /requests/{id}/criteria` moves the version; the next run's match evaluates the new criterion, and its diagnostic records the new version |
| D02 / R9.3 | `test_d02_the_expectation_reaches_no_diagnostic_task_or_slice_6_audit`: the magnitude is ask − max (2,000,000). Neither the expectation (25,000,000) nor exp − max is a number, nor `seller_expectation_dzd` a key, of `GET /requests/{id}/diagnostic`, the run's `diagnostic`, `GET /tasks`, or the audit rows of the diagnostic and of the task. **See F6-21** |
| K05 | step 2's `test_k05_a_replay_returns_the_first_response_and_writes_nothing` |
| G04 / G06 | `test_g06_a_run_with_no_candidate_writes_an_empty_valid_format_2_that_replays`, and the replay tests of steps 3 and 4 |
| K06 | **not claimed.** Four trigger-level refusals of `0007` are listed as trigger-level |

**One reading, stated.** In I03, the version moves by more than one: 5 → 7
in the measured run. That is Slice 2's (`add_criterion` and the request's
version trigger). The test asserts that the version moved and that the next
run records it, not a step of one.

## 6. Two findings, measured and put to the reviewer (not fixed)

Both were found by the end-to-end tests. Under §8 ("a defect found in a step
is measured before it is fixed"), each is recorded by a test of the present
state and is **not** changed here.

### F6-21 · D02 as worded, and the staff match of Slice 4

- **Measured** (`test_f6_21_...`):
  - the run's 201 body holds the expectation, in
    `matches[].commercial_context_snapshot.seller_expectation_dzd`;
  - the match's audit row holds the same value.

  This is Slice 4 §3.5, decided: "The commercial snapshot contains
  `seller_expectation_dzd` (R9.3: the engine may read it)". The staff
  `MatchCandidate` is staff-only, and no customer or public operation
  returns a match (Slice 4, R9.2).
- **The conflict.** Plan §6.2 words D02 as "no output of the run … or the
  audit contains the expectation", and §3.4 adds that "the internal views
  to staff are bound by the same rule". As worded, this does not hold of the
  run's `matches`, nor of the match's audit row.
- **What holds:** everything Slice 6 adds (§5, D02).
- **The sources:**
  - RFC-001 R9.2 lists `seller_expectation_dzd` among the fields that must
    not appear in a **public or customer** DTO;
  - R9.3: "MUST NOT be rendered, nor inferable from a customer-facing
    explanation";
  - `API_CONTRACTS_v0.2.md` §8: "never serialized to public/customer DTOs".
- **Options:**
  - **(a)** correct §3.4's last sentence and §6.2's D02 so that they apply to
    what Slice 6 renders and writes (the diagnostic, the tasks, their audit).
    Slice 4 §3.5 stays the decision for the staff match. No code changes;
  - **(b)** remove the expectation from the staff match and/or its audit.
    This is a change to Slice 4's decided DTO and to its reconstruction
    input (G4-13), outside Slice 6.
- **Recommendation: (a).** It agrees with the sources, which bound the
  never-serialized set to public and customer DTOs, and with a decision
  already taken.

### F6-22 · The REQUEST's own work carries an offer's title

- **Measured** (`test_f6_22_...`): when the request's maximum is REQUIRED
  and not stated, `diagnostic.actions@1` types the work CONFIRM_PRICE
  (criterion BUDGET_MAX). Step 4's fixed title for that type is "Confirm
  the offer's price terms". The work names no offer; only the subject
  (entity REQUEST, basis BUDGET_MAX_NOT_STATED) states it. The review of
  `0fae42c` accepted the per-type title for step 4.
- **Options:**
  - **(a)** title by type **and** subject entity: CONFIRM_PRICE on a REQUEST
    subject becomes "Confirm the request's maximum budget". It is one table
    in `matching_run.py`. It is not a registered function, so neither the
    registry digest nor any input hash changes. Tasks already written keep
    their title, since no path updates a title;
  - **(b)** a new `diagnostic.actions@2` that types this work OTHER. It
    changes the registry digest, and therefore every match's input hash:
    the supersession measured in step 4;
  - **(c)** no change: the subject states the work.
- **Recommendation: (a),** as the smallest change that makes the title
  true. It changes a choice the review of `0fae42c` accepted, so it waits
  for a decision.

## 7. The closure evidence (`SLICE_6_EVIDENCE.md`, §6.4)

`db/gate/slice6_evidence.py`, modelled on STOP GATE E's generator. It reads
every status from the bound JUnit report, and `run_binding.check` must bind
that report to the tree.

**Its sections:**
1. the three mandatory tests;
2. red-team (K06 trigger-level only);
3. what each review of Slice 6 asked to be proven:
   - `b6a08e7`: OQ6-1, and the completion's FOR SHARE lock;
   - `220573a`: the supersession;
   - `922a100`: a real format-2 row;
   - `0fae42c`: the shared task;
4. concurrency;
5. **the two limits (never PASS);**
6. **the findings F6-21 and F6-22, MEASURED (never decided);**
7. **the writes, computed from the tree:**
   - `tasks` by kind (condition 10, with the completion's SET clause);
   - `match_diagnostic_runs` and `task_completion_events`;
   - the writers of `requests` and `request_criteria`, of which no Slice 6
     module is one;
   - the two operations routed;
8. what is carried, unchanged.

**It refuses (exit 1) when:**
- a mapped test is missing or failed (the findings' and the limit's tests
  included), or the same name sits in another module;
- the source changed after the run, the document is stale, or the report is
  unbound;
- a write is not decided: a new INSERT, UPDATE or DELETE on `tasks`, the
  completion setting another column, an UPDATE of `match_diagnostic_runs`,
  another writer of `task_completion_events`, or a Slice 6 module writing a
  request.

Each refusal is tested in `tests/test_slice6_evidence.py` (20 cases), on a
copy of the tree.

## 8. Mutations (`db/dev/mutate_slice6_step5.py`, 14)

The mutations target rules the end-to-end tests claim, wherever the HTTP
path reaches them: `diagnostic_rules.py`, `diagnostic.py`,
`matching_run.py` and `tasks.py`. Only `tests/test_slice6_step5.py` is run.

- **The first run** (`SLICE6-STEP5-MUTATIONS-FIRST-RUN.txt`, at `a64b5ec`):
  12/14. **M2** (a REJECTED candidate gets work) and **M3** (three failures
  make a near match) survived. **Neither is equivalent.** Mandatory test 2's
  world lacked:
  - a REJECTED candidate with a freshness or permission reason, so M2
    changed nothing;
  - a three-failure candidate whose other REQUIRED criteria are known, since
    the UNKNOWN document already kept it from being a near match (M3).

  Both shapes were added at `15032f2`, and M2 and M3 then failed it.
- **Then twice, on one tree** (`SLICE6-STEP5-MUTATIONS.txt`,
  `…-REPEAT.txt`): 14/14 each time, none survives, with counts identical line
  by line: M1:1 M2:1 M3:1 M4:1 M5:3 M6:1 M7:1 S1:2 S2:1 S3:1 S4:1 R1:1 R2:2
  R3:1. Base `15032f2`, on a clean tree; `src` identical after each run.

## 9. The evidence round

Every row was run on a clean tree, with source fingerprint
`7a06d51840425a53f5c0c540734d4d7ba081932c44b65d30eb555ed37c578597` (from
`7f15581`; `src/` identical to `0fae42c`), on PostgreSQL 16.15.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations, twice | 14/14 and 14/14, identical counts | `b6d0d19` (runs at `15032f2`) | `evidence/SLICE6-STEP5-MUTATIONS.txt`, `…-REPEAT.txt`; the first run in `…-FIRST-RUN.txt` |
| Authorization matrix | 189 rules, unchanged (step 5 adds no operation); suite 2609/2609 | `0fcd66b` | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS; 70 PASS notices; 67 operations equal. The body is identical to step 4's run; only the header differs | `a2c1018` (run at `0fcd66b`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | 2609 passed, 0 failed, 0 errors, 0 skipped; `run_binding.py`: `bound` | `0ec7204` (run at `a2c1018`) | `evidence/TEST-RUN-PROVENANCE.txt` |
| Closure evidence | generated from that run; `slice6_evidence.py --check` exits 0 | `352493a` | `SLICE_6_EVIDENCE.md` |

- **The suite count:** 2576 → 2609. The change is +11 (the end-to-end
  tests), +20 (the generator's tests) and +2 (`test_mutation_tools` on the
  new script).
- **STOP GATE E:** `--check` exits 1, with the one known problem: the
  document is stale. This is unchanged from earlier steps.
- **One command was interrupted.** A `pkill` meant for two finished
  watchers matched its own command line, and stopped before any step; it
  was repeated without it. Nothing was written by the interrupted run.
- **During the mutation runs,** nothing was committed. The generator was
  written and tested on a copy of the tree in the scratchpad.

## 10. An observation, not changed

The docstring of `services/diagnostic_replay.py` still says "Step 3 writes
no format-2 row; the tests replay documents built by `compute`". This has
been stale since step 4, whose rows the tests replay. Step 5 changes no line
of `src/`, so it is put to the reviewer, not edited.

## 11. Limits, carried unchanged

- **The application role.** The tests run as a superuser (EN-02). **K06 is
  UNPROVEN** (G6-12).
- **OQ6-1 and OQ6-2 stay open.** Neither is a licence to change the schema.
- **G4-5R is open:** the proof's scope is SALE only.
- **These results are ours.** The reviewer did not re-run them.

## 12. What remained at `3657973`

- the reviewer's decision on F6-21 and F6-22, and on the observation of §10;
- the decision whether Slice 6 is closed.

The first was given in the review of `3657973`; §13 delivers what it asked.

---

## 13. The review of `3657973`: the correction

**Decided** (plan revision 15, `ce40208`):
- **F6-21:** the documentary correction (option (a));
- **F6-22:** the title by type and subject entity (option (a));
- the stale module docstrings corrected;
- the generator records both decisions;
- the evidence is bound to a run of the corrected tree;
- the tasks stored with the old title are counted, and their fate stated.

**§1's "no line of `src/` changes" held at `3657973`.** The correction changes
three files of `src/` (§13.3).

### 13.1 The stored tasks with the old title, counted before the fix

Record: `evidence/SLICE6-STEP5-F6-22-STORED-TITLES.txt`.

**Every database on the server was measured.** There are three:
- `turab_authz_test`, the suite's, which `tests/conftest.py` drops and
  rebuilds at every pytest session;
- `turab_contract_test`, the gate's, rebuilt from zero, seed only;
- `turab_probe`, which has no tasks table.

No deployed or persistent TURAB database is reachable from this environment,
and none is claimed.

**The two measurements:**
1. **First:** no REQUEST-subject task. The suite's database then held only a
   session that ran no step 5 test.
2. **After a full run of the unfixed code** (2609 passed): **2** tasks
   `CONFIRM_PRICE | REQUEST | "Confirm the offer's price terms" | OPEN`.
   They were written by the two step 5 tests whose request states no
   maximum. The 3 CONFIRM_PRICE tasks on a PROPERTY_OFFER subject carry the
   offer's title, which stays.

**Their fate:**
- **These rows:** test data, dropped with the database at the next pytest
  session. Nothing rewrites them.
- **A row of this kind in a database that keeps it:**
  - no path updates a title: the completion's UPDATE sets `status` and
    `completed_at` only (condition 10);
  - so the row keeps its old title. While it is OPEN or IN_PROGRESS, the
    index refuses a new task for the same subject;
  - the new title appears only when the work is raised again after DONE.

  Tested (§13.2).

### 13.2 F6-22 pinned on the unfixed code, then fixed

**Pinned** (`a813b06`; record `evidence/SLICE6-STEP5-F6-22-BEFORE-FIX.txt`).
On `src/` identical to `3657973`, **3 tests fail, each at its title
assertion only:**
- `test_a_high_task_shared_by_two_properties_names_only_the_request`, which
  now asserts the title;
- `test_f6_22_the_request_tasks_title_names_the_request`, the measurement
  delivered at `3657973`, inverted;
- `test_f6_22_a_task_stored_with_the_old_title_keeps_it_until_done`. Every
  step holds except the last: the work raised again still got the old
  title.

**Passes on both trees, as it must:**
`test_f6_22_an_offer_subject_keeps_the_offers_title`. It is a CONFIRM_PRICE
on a PROPERTY_OFFER (the price above the maximum, negotiation not
confirmed), HIGH, naming its match.

**The fate test, and how its row is made.** The run's own task has its title
set to the old one by SQL. That is the only way to hold, in this database, a
row as the code before the fix wrote it, and the test says so. Then:
1. a later run changes nothing and raises nothing;
2. the task is completed over HTTP (DONE), and keeps the old title;
3. the next run raises the work again, under the new title.

### 13.3 The fix (`fd648e8`)

**`services/matching_run.py`:**
- `DIAGNOSTIC_TASK_TITLES_BY_SUBJECT = {("CONFIRM_PRICE", "REQUEST"): "Confirm
  the request's maximum budget"}`;
- `_title(type, entity)` takes that title, otherwise the type's.

**What it does not change:**
- **No pinned function, so no input hash.** The registry digest, measured
  after the fix, is `47188d01…`, the same as `HISTORY[-1]` (since
  `55dbee6`).
- **No other title.** `VERIFY_DOCUMENT` and `OTHER` keep theirs, and so
  does `CONFIRM_PRICE` on a PROPERTY_OFFER.

**The docstrings:**
- **`matching/diagnostic.py`:** the head said "Step 3 writes nothing … the
  run still writes format 1". It now states who calls `compute`: the run
  since step 4, and the replay.
- **`services/diagnostic_replay.py`:** the head said "Step 3 writes no
  format-2 row". It now says that the run writes format-2 rows and that the
  tests replay them, and it states the limit on the diagnostic's own
  `input_hash`.

**The `src/` diff from `3657973`:** these three files only.

### 13.4 F6-21: the correction is documentary

**Plan revision 15:**
- **§3.4's last sentence** ("The internal views to staff are bound by the
  same rule") is replaced by the rule's scope. It binds what Slice 6
  generates: the diagnostic, its tasks and the task list, and their audit
  rows. It is not a rule of every output of the run: Slice 4 §3.5 keeps the
  expectation in the staff match's snapshot, and `API_CONTRACTS_v0.2.md` §8
  forbids its serialization to public and customer DTOs.
- **§6.2's D02** is bounded the same way.

**The test of the staff match and its audit is kept as the boundary's
witness.** Its assertions are unchanged, and it is renamed
`test_f6_21_the_staff_match_keeps_the_expectation_the_boundary_witness`.

### 13.5 The generator

`SLICE_6_EVIDENCE.md` §6 is now **"Findings decided in the review of
`3657973`"**:
- **F6-21:** the decision, held by the boundary's witness and the D02 test;
- **F6-22:** the fix, held by its four tests.

**Two facts are computed from the tree:**
- **the decided title,** as `matching_run.py` fixes it. A problem if it is
  not that title;
- **the stored-titles record,** whose REQUEST lines are quoted. A problem if
  the record is absent.

`tests/test_slice6_evidence.py` has 23 cases, 3 more than at `3657973`:
- a decision's test absent (one more victim);
- the old title put back in the code;
- the record removed.

### 13.6 Mutations

| Run | Result | Counts |
|---|---|---|
| step 5, at `fd648e8`, twice (`SLICE6-STEP5-MUTATIONS.txt`, `…-REPEAT.txt`) | 16/16 each; none survives | M1:1 M2:1 M3:1 M4:1 M5:3 M6:1 M7:1 S1:2 S2:1 S3:1 S4:2 R1:1 R2:2 R3:1 T1:3 T2:1, **identical** |
| step 4's script, once at the fix (`SLICE6-STEP4-MUTATIONS-AT-F6-22-FIX.txt`) | 19/19; none survives | identical to step 4's delivered counts |

**What changed in the step 5 runs:**
- **T1 and T2 are new.** T1 puts the REQUEST's work back under the offer's
  title; T2 gives the request's title to every subject of the type.
- **S4 now has 2 kills, not 1.** The fate test also completes a task.

The records at `15032f2` are replaced by these, and stay in git history.

### 13.7 The evidence round of the corrected tree

Every row was run on a clean tree, with source fingerprint
`2858511a5bfc1798b3eeb6f3d11977701df9065967b29e55ccd8de5bfa0fcbde`, on
PostgreSQL 16.15. The container had restarted, and PostgreSQL was started
again (EN-01).

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations | §13.6 | `17849f8` (runs at `fd648e8`) | as §13.6 |
| Authorization matrix | 189 rules, unchanged; suite 2614/2614 | `130b725` | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS; 70 PASS notices; 67 operations equal. The body is identical to the run at `a2c1018` | `c627551` (run at `130b725`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | 2614 passed, 0 failed, 0 errors, 0 skipped; `bound` | `5d0cd09` | `evidence/TEST-RUN-PROVENANCE.txt` |
| Closure evidence | regenerated from that run; `--check` exits 0 | `d4a1263` | `SLICE_6_EVIDENCE.md` |

- **The suite count:** 2609 → 2614. The change is +2 in step 5 (13 tests:
  the measurement inverted, plus the offer's title and the fate test) and
  +3 in the generator's tests.
- **STOP GATE E:** `--check` exits 1, with the one known problem: the
  document is stale. This is unchanged.

### 13.8 Carried, unchanged

- **OQ6-1 and OQ6-2 stay open.** K06 is UNPROVEN, and G4-5R is open: the
  evidence's scope is SALE only.
- **These results are ours.** The reviewer did not re-run them.
- **What remains:** the review of this correction, then the decision on the
  slice's closure.
