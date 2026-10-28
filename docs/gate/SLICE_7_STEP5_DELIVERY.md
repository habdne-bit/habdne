# Slice 7 · step 5 — the mandatory and red-team tests end to end, the event-store sample, the closure evidence

**Approved scope.**
- **Step 5 authorized** in the review of `2f968f4`, within the plan's scope.
- **G7-19 decided** in the review of `d04d5c8` (plan revision 22): direction
  (a) in its three points, as specified there.
- **The review of `8dd7921`:** step 5 not closed. It asked for three changes
  on the tree before the official round. §2 answers them; the mutation runs
  and the evidence round below are on the resulting tree.

**What this step does not contain:**
- **product code:** nothing under `src/` changes. The step adds tests, two
  evidence tools, a mutation script and five matrix rules, and changes
  `db/gate/record_test_run.py` and `db/gate/run_binding.py` (§2.1);
- a migration, or an HTTP operation;
- the relay (R-1). **R-1 is UNMET: no real event may be received.**

**Status: DELIVERED for review, NOT CLOSED.** Slice 7 is not closed.
- **What the reviewer did not do:** re-run the suite, the mutations or the
  gate. The results are ours.

**Commits:**
- `8dd7921`: the tests, the sample tool, the generator, the mutation script,
  the matrix rules (reviewed);
- `fd1d570`: the review of `8dd7921` answered (§2);
- `94769e0`: the mutation records (§4);
- `5095d11`: one matrix rule's text corrected (§3.4);
- `b61c4bb`, `88fb6dc`, `436d4ca`: the evidence round (§5).

---

## 1. What step 5 contains

### 1.1 The end-to-end tests (`tests/test_slice7_step5.py`, 12 tests)

The four mandatory tests (plan §6.1) and J01, J02, J03, S41, S42 and K05
(§6.2):

| Plan | Tests |
|---|---|
| mandatory 1, J01, S42 | the same envelope twice; eight concurrent deliveries; a FAILED event completed by the redelivery: each one event, one message and **one interaction** |
| mandatory 2, J02 | staff first then the webhook into another thread (IGNORED `MESSAGE_REF_TAKEN`, writing nothing else); the webhook first then staff (409, writing nothing and no key); the NULL-provider path refused by the service and by `0008` |
| mandatory 3 | the seller's thread naming the buyer's SALE opportunity accepted; an inconsistent link refused writing nothing; the links frozen; the named parent's deletion refused |
| mandatory 4 | the decision, the confirmation (the observation command) and the link; the decision and the link read back through the timeline, each as a NOTE |
| J03 | content in a message only under the archive consent, never in the event store; shown by the timeline only when archived |
| K05 | each staff command replays with its key, and **another body on the key is 409**, writing nothing |
| S41 | an unsigned or missigned delivery is 401, writing nothing; the relay's origin, not Meta's |

**The two gaps G7-19 named are closed:** mandatory test 1's concurrent
delivery now counts the interaction, and K05's other body is tested for both
staff commands.

**What goes over HTTP, and what does not** (wording corrected in the review
of `8dd7921`, §2.2):
- **Over HTTP:** the operations each test proves (the two staff commands, the
  webhook, the observation command, the timeline), and the matching run and
  the review that make the SALE opportunity.
- **In SQL:** the rows the tests start from: the fixture accounts and
  parties `tests/conftest.py` loads, and through the helpers of
  `tests/test_slice7_step2.py`, `_party` (a party), `_archive_consent` (a
  consent grant and its thread binding) and `_sale_world` (the request, its
  criterion, the property with its attributes, and the offer, by
  `tests/test_slice4_step7.py`'s helpers). SQL also reads the results, and
  probes `0008`'s own refusals, which no HTTP path reaches.

### 1.2 The event-store sample (`db/gate/slice7_event_store_counts.py`, G7-19 (i))

Run right after `record_test_run.py`. It writes
`evidence/SLICE7-EVENT-STORE-COUNTS.txt`:
- the sample's time;
- the run's recorded time, commit, source fingerprint and report sha256;
- the database's name and host, as the run's record names them;
- the count of each `processing_status`, and FAILED's by `error_text`.

Nothing else: no event id, no reference, no payload. The heading is "a
sample measured right after the run"; it is never PASS.

### 1.3 The closure evidence (`db/gate/slice7_evidence.py` → `SLICE_7_EVIDENCE.md`)

Built as Slice 6's, every status from the bound JUnit report:
- the mandatory, red-team, authorization, review-obligation and concurrency
  tests, each with its status;
- K06's trigger- and constraint-level tests, listed and **never counted as
  K06**;
- **the writes to the four tables** by `INSERT`, `UPDATE` and `DELETE`, and
  each UPDATE's columns, computed from `src/` (G7-19 (ii)). A writer or a
  column not decided is a problem. The module holding the interaction's
  INSERT (`message_interactions.py`) is told apart from its callers: the
  staff command, the webhook, and `db/ops/backfill_message_interactions.py`.
  **It is not a guarantee against a superuser's writes;**
- the sample, refused unless it names the bound run and its recorded
  database (§2.1);
- **every limit, none PASS** (G7-19 (iii));
- CORRECTION-006, -007 and -008 approved; the four operations routed.

`tests/test_slice7_evidence.py`: 47 experiments on a copy of the tree, the
generator and the tools run as subprocesses; the baseline must pass before
each refusal is asked for.

### 1.4 The matrix

Five rules for step 5 (`S7-5`).

## 2. The review of `8dd7921`

### 2.1 The sample bound to the database the suite ran on

**What was wrong:** the sample tool chose its database from `TURAB_TEST_DB`
at sampling time. The generator compared the run's fingerprint and report,
but not the database: a variable changed between the two commands would
have been accepted with another database's counts.

**What changed:**
- `record_test_run.py` resolves the database's name and host once, as
  `tests/conftest.py` reads them (`TURAB_TEST_DB`, `PGHOST`), **sets them in
  the suite's own environment**, and writes them to the run's record:
  `Test database: <name> on host <host>`. The record cannot name a database
  the suite did not use.
- `run_binding.py` reads the field when present. It is **optional**:
  `run_binding.check` binds every slice's run, and the earlier slices' tests
  write records without it.
- `slice7_event_store_counts.py` refuses, **before connecting and writing
  nothing**: a record naming no database; a `TURAB_TEST_DB` or `PGHOST` that
  names another. It then samples **the recorded database, never the
  environment's**.
- `slice7_evidence.py` refuses a sample whose database or host is not the
  record's, and a record naming none.

The host is bound with the name, since another host with the same name would
be another database.

### 2.2 The wording of the end-to-end tests

"Every business row made over HTTP" was wider than the tests. Corrected in
the generator and in the test file's docstring as §1.1 states it, each helper
named. Mandatory test 4's docstring is corrected the same way.

### 2.3 No skipped case

`run_binding.check` refuses failed and errored cases, not skipped ones. Both
Slice 7 tools now **refuse a skipped case explicitly**. `run_binding.check`
is unchanged: the other slices' generators depend on it.

### 2.4 How each change is tested

| Change | Test (`tests/test_slice7_evidence.py`) | Mutation |
|---|---|---|
| the sample's database and host compared | `test_s7_a_sample_of_another_database_is_refused` (database; host) | E1 |
| a record naming no database refused by the generator | `test_s7_a_run_record_naming_no_database_is_refused` | E2 |
| a skipped case refused by the generator | `test_s7_a_skipped_case_is_refused_by_the_generator` | E3 |
| the tool samples the recorded database, not the default | `test_s7_the_sample_tool_connects_to_the_recorded_database_not_the_default` | E4 |
| the environment compared by the tool | `test_s7_the_sample_tool_refuses_an_environment_naming_another_database` (name; host) | E5 |
| a record naming no database refused by the tool | `test_s7_the_sample_tool_refuses_a_record_naming_no_database` | E6 |
| a skipped case refused by the tool | `test_s7_the_sample_tool_refuses_a_skipped_case` | E7 |
| the suite run on the recorded database | `test_s7_the_recorder_runs_the_suite_on_the_database_it_records` | E8 |
| the record names the database | the same | E9 |
| the wording | `test_s7_the_end_to_end_tests_are_described_as_they_are` | — |

`test_s7_the_sample_tool_connects_to_the_recorded_database_not_the_default`
was added because, here, the recorded database and the default have the same
name. A tool that read the environment by mistake would have passed every
other test. In this test the record names a database that does not exist,
with no variable set, and the tool must fail naming it.

## 3. Readings of ours (not decisions of the plan)

1. **"Run recorded at" is when the run started.** It is the record's
   `Recorded` field, written before the suite runs. In this round the run
   was recorded at 13:03:40 UTC and took 10 min 29 s, so it ended about
   13:14:10. The sample was taken at 13:15:27, about a minute after the end.
2. **The one RECEIVED event in the sample** is consistent with the event
   `test_recovery_completes_a_failed_event_and_skips_a_fresh_received_one`
   stores and leaves unprocessed on purpose. It was a message event, stored
   at 13:13:29, which we read from the test database after the round. The
   sample holds counts only and does not say which test left a row.
3. **The concurrent test of mandatory 1 is not deselected** from the
   mutation runs, unlike step 3's. None of the mutations touches the claim's
   lock or the thread's lock, so its result does not depend on timing under
   them. The two official runs agree.
4. **One matrix rule's text was corrected after the mutation runs**
   (`5095d11`). Mandatory test 4's rule said the decision, the confirmation
   and the link were "each read back through the timeline as a NOTE"; the
   test reads back the decision and the link only. Between the mutation tree
   (`fd1d570`) and the evidence tree, the source differs by those three
   lines of `db/gate/authorization_evidence.py`, which no mutated test reads.
   This is why the fingerprints differ (`0fbf60e4…71eb` and
   `481f5ec5…c6ed`).

## 4. Mutation evidence

`db/dev/mutate_slice7_step5.py`, in two parts. **No before record:** step 5
adds no product code, so there is no "before the fix" state to measure, as
in Slice 6's step 5.

**The two official runs at `fd1d570`, clean tree:**

| Part | Tests | Result |
|---|---|---|
| 1. W, D, L, C, J, K, S: rules the end-to-end tests claim | `tests/test_slice7_step5.py` | **15/15 killed** |
| 2. E1–E9: the closure evidence's refusals (§2.4) | `tests/test_slice7_evidence.py` | **9/9 killed** |

Both runs are identical in every outcome:
`evidence/SLICE7-STEP5-MUTATIONS.txt` and `-REPEAT.txt`.

**The trial runs**, outside the record, on a dirty tree, kept as they were:
- `-TRIAL.txt`, 18 mutations: **four survived.**
  - **J2** (the webhook keeps content when the consent does not hold):
    **a real gap of the J03 test.** It read only the timeline, which hides
    an unarchived body anyway, so it did not check its own claim that the
    message holds content only under the consent. The test now reads the
    message rows; J2 is killed.
  - **W1** (a replay of a final event taken as new): the claim re-reads the
    status and takes no final event. Removed: equivalent here; step 3
    mutates both guards against its own tests.
  - **D1** (the webhook's 23505 backstop): the read before the insert
    answers IGNORED first. Removed: equivalent here.
  - **C4** (a `message` key on every timeline item): every item of the
    parties these tests read is a message's. Removed: step 4's
    `test_vi_any_other_interaction_keeps_slice_1s_exact_keys` claims it.

  The three removals are stated in the script's docstring.
- `-TRIAL-E.txt`: E1–E9, all killed.

**Steps 2–4's mutations are not re-run:** nothing under `src/` changed.

## 5. The evidence round

Every row ran on a clean tree with source fingerprint `481f5ec5…c6ed`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | **222 rules** (five for step 5); suite **3152/3152** | `b61c4bb` (run at `5095d11`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | **PASS**: all database-level contract tests passed; the effective contract, inventory and policy table hold the same 67 operations | `88fb6dc` (run at `b61c4bb`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3152 passed, 0 failed, 0 errors, 0 skipped**, on `turab_authz_test` at `127.0.0.1` (recorded) | `436d4ca` (run at `88fb6dc`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: **`bound`** |
| The event-store sample | RECEIVED 1, PROCESSED 74, IGNORED 26, FAILED 0; **never PASS** | `436d4ca` | `evidence/SLICE7-EVENT-STORE-COUNTS.txt` |
| Closure evidence | generated; `--check` passes after the commit | `436d4ca` | `SLICE_7_EVIDENCE.md` |
| Step 5 mutations | 24/24, twice, identical | `94769e0` (run at `fd1d570`) | §4 |

**The interactions at the end of the run** (read after the round, not part
of any record): 196 messages; **195 with exactly one interaction**; **one
with none**, the OUTBOUND `PHONE_DECISION` a step 4 test inserts directly by
SQL, outside the service's paths, as step 4's note reported; no message with
two.

**The earlier slices' records are not regenerated.** They stay their trees'
records, and `--check` reports them stale on this tree:
- `slice6_evidence.py --check`: one problem, the document is stale;
- `stop_gate_e_evidence.py --check`: the document is stale, and
  `interactions` is written by `message_interactions.py` beside the
  opportunity commands. That second writer was decided in step 4, and Slice
  5's gate reports it as it stands;
- `stop_gate_c_evidence.py --check`: the document is stale.

## 6. Limits that are part of these results

- **R-1 UNMET.** The relay is not built. Its signature proves the relay's
  origin, not Meta's. No reception of a real event is claimed.
- **K06 UNPROVEN** (EN-02). `0008`'s refusals are trigger- and
  constraint-level.
- **Retention is not claimed** (OQ7-1).
- **One interaction per message within the service's paths only.**
- **The link is valid at its writing only,** with no legal value.
- **The content-less recovery** (G7-2 (v)).
- **The writes' inventory reads the application's statements;** it is not a
  guarantee against a superuser's writes.
- **The sample is from the run's test database, after the run;** it is not
  the state at the last test's moment.
- **SALE only.** **These results are ours.** No independent run exists.

## 7. What remains

- **The review of this delivery.** Step 5 is not closed.
- **R-1:** the relay and its seven duties. **No real event before it.**
- **K06 UNPROVEN;** the scope SALE only. **This is not a release
  authorization.**
