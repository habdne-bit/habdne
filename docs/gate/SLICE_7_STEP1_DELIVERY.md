# Slice 7 · step 1 — migration `0008` (plan §5.1, parts E, A, B, C, D2)

**Approved scope.** The review of `38281ab` approved the text of `0008`,
parts E, A, B, C and D2, and authorized step 1 "in the plan's sequence".
Plan revision 5 records it. The approval covers a text and its testing: "the
migration has not been run yet, so I do not count the guards as proven by
execution". This document reports that execution.

- **What this step does not contain:**
  - no webhook, no command, no read endpoint;
  - no CORRECTION-007 (step 3);
  - no relay (R-1).

  `0008` is database guards only. No application path writes a thread, a
  message or an event yet.
- **How the review said it would judge this delivery:**
  - the refusal of old non-conforming data (§2.1);
  - the race on one reference (§2.2);
  - the status transitions (§2.3);
  - the six keys and their guard (§2.4);
  - the downgrade (§2.5), and a downgrade refused by `0007` (§2.6).

  Each has its own section, with the tests that prove it and the mutations
  that weaken it.

**Status: CLOSED at `7e8993d`** (review of `7e8993d`; `SLICE_7_PLAN.md`
revision 7). Step 2 is authorized. Slice 7 is not closed.
- **The review accepted D2's reading of R14.6 (§1) for these six keys
  only.** It does not extend to a correction of the baseline file itself.
- **The review chose remedy (b) for the Slice 5 test (§6.1):**
  `share_committed_first` is removed (`ddd012d`), and its effect is measured
  in `evidence/SLICE7-S5-RACE-FIELD-AFTER.txt`.
- **What the review did not do:** re-run PostgreSQL, the suite or the
  mutations. The numbers are ours, bound to the tree.

*As delivered:* delivered for review. Step 2 had not started.

**The review of the progress report.** An earlier account of this step was
a progress report, not this delivery (review of the progress report, after
`dc35b50`). The review asked that the delivery show:
- the full suite on the final tree (§6);
- both runs of the 77 mutations (§4);
- the state of the Slice 5 concurrency test that failed once (§6.1). Its
  ten passes alone "do not by themselves prove the failure is incidental";
- the state of the database after a downgrade that `0007` refuses (§2.6).

The review could not open `dc35b50` (404). It had not been pushed: the
remote stood at `6313b9a`. Since then, every commit has been pushed after
it was made, and the local and remote heads were compared after each push.

**Basis:**
- `docs/gate/SLICE_7_PLAN.md` revision 5, §5.1 (the text), and the decisions
  it rests on: G7-3 (part E), G7-4 (part A), G7-5 (part B), G7-2 (v)
  (part C), G7-12 D2 (part D);
- step 0's measurements, `evidence/SLICE7-PLAN-MEASUREMENTS.txt` (M1, M3,
  M8).

**Commits:**
- `1e200fe`: the migration, its deltas, its tests, its mutation script, the
  before record;
- `9817d44`: the pre-check cases made independent (§5);
- `93c5acb`: a test for `provider` alone, after B6 survived (§4);
- `d2c6431`: the refused-downgrade test (§2.6), and the Slice 5 race
  measured (§6.1);
- `e1649a0`: the downgrade test returns to head in a `finally` (§5);
- `6313b9a`, `dc35b50`, `81de574`, `4d9e4ec`: the before record, re-measured
  on each version of the test file (§3);
- `7eedd77`: `mutate_0008.py`'s anchor check moved under its `__main__`
  guard (§6);
- `3d28741`, `6069f43`: the mutation records, at `4d9e4ec` and then at
  `7eedd77` (§4);
- then the evidence commits listed in §6.

---

## 1. What `0008` contains

`db/migrations/versions/0008_communication_records.py`, sha256 `731423d6…`.
`UPGRADE` is §5.1's block, statement by statement, in its order: fourteen
statements. `test_the_migration_executes_the_approved_text` compares the two,
whitespace aside, against the plan file itself. Only the Alembic wrapping is
added: `SET LOCAL search_path` and the loop.

| Part | Objects | What it refuses | Decision |
|---|---|---|---|
| E | a pre-check (`DO` block); `ck_whatsapp_thread_ref_scoped`; partial unique index `ux_whatsapp_thread_ref` | the migration itself, while an existing WHATSAPP reference is unscoped or shared; an unscoped WHATSAPP reference; a second WHATSAPP thread with one reference | G7-3 |
| A | `ck_message_ref_needs_provider`, `ck_message_provider_known`, `ck_internal_message_has_no_ref`; `enforce_message_provider_channel()` + `trg_message_provider_channel` (BEFORE INSERT) | a reference without a provider; a provider other than `whatsapp`; an INTERNAL message with a reference; a provider in a thread that is not WHATSAPP | G7-4 |
| B | `guard_communication_message()` + `trg_guard_communication_message` (BEFORE UPDATE OR DELETE) | any change but `delivery_status`; every transition but G7-5's twelve; DELETE | G7-5 |
| C | `guard_webhook_event()` + `trg_guard_webhook_event` (BEFORE UPDATE OR DELETE) | a change of an immutable field; leaving PROCESSED or IGNORED; moving to RECEIVED; DELETE | G7-2 (v) |
| D2 | six keys `ON DELETE SET NULL` → `RESTRICT`; `guard_communication_thread()` + `trg_guard_communication_thread` (BEFORE UPDATE OR DELETE) | deleting a party, request, property, opportunity or account a thread or message names; any change of a thread but `last_message_at` forward; DELETE | G7-12 D2 |

**Nineteen declared deltas** (`db/gate/migration_deltas.py`):
- **thirteen new objects:** four CHECKs, one index, four functions, four
  triggers;
- **six changed frozen keys,** each digested before (the frozen `SET NULL`
  definition) and after (`RESTRICT`).

`test_the_declared_deltas_for_0008_are_exactly_its_nineteen_objects`
pins the list; `test_head_is_the_baseline_plus_exactly_the_declared_deltas`
proves head is the baseline plus these, and nothing else.

**A frozen object changes, and how this is read.** Part D alters six
constraints that `schema_v0.2.3.sql` declares:
- **Precedent.** This is the second time a revision changes a frozen object.
  The first was `0003`, which changed a function body (G3-7 §6, option A,
  decided). `0008` follows the same path:
  - `schema_v0.2.3.sql` keeps its digest;
  - revision `0001` still applies it verbatim, and the baseline guarantee is
    unchanged (`MIGRATION_POLICY.md` §1a);
  - each change is a declared delta with its digest before and after, and
    with its behavioural test.
- **The rule it must meet.** `MIGRATION_POLICY.md` §4 (2) and RFC-001
  R14.6 require "the same approval path as a schema change" for a migration
  that alters the frozen schema.
- **Our reading:** that path was taken. The change was put to the reviewer
  as a change to frozen constraints, by name and number ("six frozen
  constraints change", G7-12 D2). It was decided in the review of `4aed49b`,
  and its text was approved in the review of `38281ab`.
- **What we did not do.** §4 (2) also says that "corrections to the
  baseline arrive as a new official handoff package". We do not read D2 as a
  correction to the baseline: the baseline is unchanged, and this is an
  evolution on top of it, as `0003` was. That reading is ours. It is put to
  the reviewer, and is not assumed accepted.

**Properties stated, each tested or measured:**
- **The pre-check runs in the migration's transaction.** All revisions run
  in one transaction (`db/migrations/env.py`), so a refused pre-check
  applies none of `0008`. The test asserts the version, which stays `0007`
  (§2.1). The database's state is asserted for the refused downgrade
  (§2.6), not here.
- **Part E's index is partial.** It covers WHATSAPP threads with a
  reference. A PHONE thread may carry the same reference, and NULL references
  never conflict (`test_e_other_channels_and_null_references_are_not_constrained`).
- **The `external_thread_ref IS NOT NULL` conjunct of the index predicate
  changes no write.** A unique index treats NULLs as distinct (PostgreSQL 16
  documentation, §11.6 and §5.4.3), so the predicate without it accepts and
  refuses the same rows. It is not mutated, and no test is claimed for it.
- **D2 holds at any trigger depth,** unlike D3 (review of `58a0067`). An
  UPDATE issued from another table's trigger is refused like a direct one
  (`test_d_a_nested_update_is_refused_too`; mutation D20 adds D3's bypass and
  that test fails).
- **The core delete guards fire first.** Requests, properties and
  opportunities already refuse DELETE through their frozen guards. The six
  keys' own refusal is therefore tested with that guard disabled, inside the
  rolled-back transaction, and against parents no other key names, since
  another referencing row would refuse first. The catalog check
  (`confdeltype = 'r'`) is separate.
- **A frozen fact, measured at the base, not changed:** a thread's
  `thread_id` could already not change while a message referenced it (the
  messages' key). The guard now refuses it whether or not a message exists
  (§3).

## 2. The points the reviews named

### 2.1 Old non-conforming data is refused

`test_e_the_precheck_refuses_unscoped_and_shared_references`, three cases, on
a scratch database built by `db/dev/reset_db.sh`. Each case:
1. brings the database down to `0007`;
2. writes the old rows (case 1: one unscoped reference; case 2: one
   reference held by two WHATSAPP threads; case 3: both). In every case it
   also writes two PHONE threads, one carrying the shared reference and one an
   unscoped one, which neither count may include;
3. runs `alembic upgrade head`, which must be refused with the exact counts
   ("0008: 1 WHATSAPP thread reference(s) not scoped, 0 reference(s) shared",
   and so on);
4. checks the version is still `0007`;
5. removes the rows; the upgrade then applies.

Mutations:
- **E1, the pre-check not run:** all three cases fail. The upgrade is still
  refused, but by the CHECK or the index, without the counts.
- **E2, unscoped only:** the shared-only case fails.
- **E3, shared counted across channels:** cases 1 and 3 fail, because the
  PHONE rows enter the count.

### 2.2 The race on one reference

`test_e_two_concurrent_threads_with_one_reference_make_one`, two cases:
- **The setup.** Two sessions insert a WHATSAPP thread with one fresh
  reference.
- **The witness.** The contender WAITS on the holder's uncommitted row:
  `pg_blocking_pids` names the holder.
- **After the holder's COMMIT:** the contender is refused with SQLSTATE 23505
  on `ux_whatsapp_thread_ref`.
- **After its ROLLBACK:** the contender is accepted.
- **Either way,** one thread holds the reference.
- **At the base:** the contender was not blocked, and both committed (§3).
- **Mutation E6,** the index not unique: both cases fail, and so does the
  direct second-thread test.

The threads these tests commit stay in the suite's database. Their DELETE is
refused, and each uses a reference of its own.

### 2.3 The status transitions

- **Delivery status (part B).** All 30 ordered pairs of distinct statuses are
  tested against an independent statement of G7-5's table (`_decided`):
  - 12 are accepted: UNKNOWN → QUEUED, SENT, DELIVERED or READ; forward
    within QUEUED < SENT < DELIVERED < READ; QUEUED or SENT → FAILED;
  - 18 are refused, each with its own message. **UNKNOWN → FAILED is
    refused**;
  - a pure test pins the table itself: 30 pairs, 12 accepted, UNKNOWN →
    FAILED not among them;
  - the no-op update is accepted.
  - Mutations B16–B23: each rule's weakening fails a named transition.
- **Processing status (part C).** 16 cases. RECEIVED or FAILED → PROCESSED,
  IGNORED or FAILED is accepted, as is the path RECEIVED → FAILED → FAILED →
  PROCESSED. Every move from PROCESSED or IGNORED is refused, as is any move
  to RECEIVED. Mutations C10–C12.

### 2.4 The six keys and their guard

- **`test_d_the_six_keys_are_restrict`:** the catalog shows the six keys,
  and the messages' frozen `thread_id` key, as `'r'`, and no `SET NULL` key
  left on the two tables.
- **`test_d_a_named_parent_cannot_be_deleted`, six cases:** each deletion is
  refused with 23503, and the constraint named is the key's own.
- **The thread guard:**
  - every one of the twelve changes of a thread is refused at depth 1. At
    depth 2, one change is tested: a test trigger on `parties` clears a
    thread's `party_id`, and is refused;
  - `last_message_at` moves forward, and is refused backwards or cleared;
  - DELETE is refused.
- **Mutations:**
  - D1–D6, each key left `SET NULL`: three tests fail, namely the catalog
    test, that key's deletion case and the refused-downgrade test (§2.6).
    The deletion is then refused by a guard instead of the key: the thread
    guard ("a thread's links never change") for the five thread keys, and
    the message guard ("only delivery_status may change") for the sender's.
    This is M8's conflict, shown;
  - D7–D19, the guard absent or narrowed, one column at a time;
  - D20, D3's depth bypass;
  - D21 and D22, `last_message_at`;
  - D23, the threads' ALTER not run.

### 2.5 The downgrade

`test_the_downgrade_restores_the_frozen_definitions_and_keeps_the_rows`, on
the scratch database:
- it writes a thread and a message at head, and downgrades to `0007`;
- every object of the 19 deltas then has its `digest_before`: absent for the
  13 new ones, and the frozen `SET NULL` definition for the six keys
  (`confdeltype` `'n'` read directly for one of them);
- the rows written at head are kept;
- upgraded again, every object is as it was at head.

That head matches the ledger's `digest_after` is proven by
`test_head_is_the_baseline_plus_exactly_the_declared_deltas`. Mutations
G1–G5: the downgrade leaves a key RESTRICT, the index, a CHECK of part A,
or the scoped CHECK.

### 2.6 A downgrade that `0007` refuses

`test_a_downgrade_refused_by_0007_leaves_0008_whole`, on the scratch
database, at head:
1. it writes a party, a WHATSAPP thread naming it, and a message, and takes
   the digests of the 19 objects;
2. `alembic downgrade 0006_opportunity_history` is refused. The output shows
   `Running downgrade 0008_communication_records -> 0007_task_work_and_evidence`
   and then `0007 has no downgrade`: 0008's downgrade RAN, and 0007's refusal
   came after it;
3. **the database, not only the version:**
   - the version is `0008_communication_records`;
   - the 19 objects have their head digests;
   - the six keys are `'r'`;
   - the message is kept;
   - deleting the thread is refused by its guard;
   - deleting the party is refused by `communication_threads_party_id_fkey`.

**Why.** Every revision runs in one transaction (`db/migrations/env.py`),
and the refusal rolls 0008's downgrade back with it.
`test_0007_refuses_to_downgrade` (`tests/test_migrations.py`) asserts the
version only. This test asserts the state.

**Mutations** (`evidence/SLICE7-STEP1-0008-MUTATIONS.txt`). The test fails
under 16 mutations, for three causes:
- **what it reads at head is weakened:** D1–D6 and D23 (a key not
  RESTRICT); D7 and D8 (the thread guard);
- **0008's own downgrade fails before 0007 is reached,** because it drops an
  object the mutated upgrade never created: E4, A5, B1, C1. alembic then
  reports that error, not 0007's refusal;
- **the scratch database cannot return to head:** G3–G5. The mutated
  downgrade leaves an object behind, so the next upgrade fails with "already
  exists". This is a consequence of the mutation itself, not of the order of
  the tests.

Since `e1649a0` it no longer fails as a consequence of the downgrade test's
own failure: under G1 and G2, only the downgrade test fails (§5).

## 3. Before the fix (measured)

`evidence/SLICE7-STEP1-0008-BEFORE.txt`: the 124 tests, run in an isolated
worktree at `582b522` (no `0008`), into which only the test file was copied.
**98 failed, 26 passed.**
- **88 failed, "DID NOT RAISE":** every refusal of parts E (7), A (12), B
  (32), C (17) and D (20), among them the six parent deletions, accepted
  under `SET NULL`.
- **10 failed with another cause, each read:**
  - the `thread_id` change, refused by the messages' key and not by a guard
    (a thread without a message would be accepted);
  - the keys' catalog (`'n'`, not `'r'`);
  - the two races: the contender was NOT blocked, and both inserts
    committed (two WHATSAPP threads, one reference);
  - the three pre-check cases ("the upgrade was accepted");
  - the downgrade test and the refused-downgrade test (version `0007`);
  - the approved text (no migration file).
- **26 passed, as they must at the base too:**
  - the writes that stay accepted;
  - the frozen global message identity;
  - the pure check of G7-5's table.

**Measured five times,** once on each version of the test file. Each time,
the tests common to two versions gave the same result, and each test added
failed at the base. The record lists the five, with their hashes. The one
kept is that of the final file, sha256 `263570a5…0959`.

## 4. Mutation evidence

`evidence/SLICE7-STEP1-0008-MUTATIONS.txt` and `-REPEAT.txt`. Both were run
on the clean tree at `7eedd77`, source fingerprint `0fff3ec5…b6ad`, the
source of the final tree, with `test_the_migration_executes_the_approved_text`
deselected. **77/77 fail; none survives**, in both runs.
- The failing tests and their counts are identical line for line.
- The causes differ only in the ids the tests generate.
- **The runs are also identical to two earlier runs at `4d9e4ec`,** kept as
  `-AT-4d9e4ec` and `-AT-4d9e4ec-REPEAT`. They were repeated only because
  the mutation script itself changed (§6).

| Mutations | Tests failing |
|---|---|
| E1 pre-check not run · E2 unscoped only · E3 shared across channels | 3 · 1 · 2 |
| E4 scoped CHECK absent · E5 one colon anywhere · E6 index not unique · E7 index over every channel | 11 · 4 · 3 · 1 |
| A1 reference without provider · A2 any provider · A3 case-insensitive · A4 INTERNAL with reference | 1 · 4 · 1 · 1 |
| A5 channel trigger absent · A6 on UPDATE · A7 any channel | 11 · 6 · 6 |
| B1 message guard absent · B2 UPDATE only · B3 DELETE only | 37 · 1 · 31 |
| B4–B15 each of the 12 frozen message columns | 1 each |
| B16 UNKNOWN → FAILED · B17 UNKNOWN nowhere · B18 backwards · B19 FAILED from DELIVERED · B20 not from SENT · B21 order without DELIVERED · B22 no-op refused · B23 returns instead of raising | 1 · 4 · 6 · 1 · 1 · 4 · 1 · 18 |
| C1 event guard absent · C2 UPDATE only · C3 DELETE only | 22 · 1 · 16 |
| C4–C9 each of the 6 immutable event fields | 1 each |
| C10 PROCESSED reprocessed · C11 FAILED final · C12 back to RECEIVED | 3 · 4 · 2 |
| D1–D6 each key left SET NULL | 3 each |
| D7 thread guard absent · D8 UPDATE only · D9 DELETE only | 20 · 2 · 14 |
| D10–D19 each of the 10 frozen thread columns | 1, except `party_id` 3 and `external_thread_ref` 2 |
| D20 D3's depth bypass · D21 `last_message_at` back · D22 cleared · D23 the threads' ALTER not run | 1 · 1 · 1 · 7 |
| G1 party key left RESTRICT · G2 sender key · G3 index left · G4 a CHECK left · G5 scoped CHECK left | 1 · 1 · 5 · 5 · 5 |

**Which tests kill the five points:**
- **Old rows:** E1–E3, the three pre-check cases.
- **The race:** E6, both race cases and the second-thread test.
- **The transitions:** B16–B23 and C10–C12, each through the named
  transition.
- **The six keys:**
  - D1–D6 fail the catalog test and that key's deletion case. The deletion
    is then refused by the thread guard ("a thread's links never change")
    or, for the sender, by the message guard, instead of by the key: M8's
    conflict, shown;
  - D1–D6 also fail the refused-downgrade test.
- **The guard:** D7–D22, D20 by the depth-2 test alone.
- **The downgrade:** G1–G5.

**A first full run had a survivor, and the record keeps it.**
`evidence/SLICE7-STEP1-0008-MUTATIONS-FIRST-RUN.txt` is that run, at
`6313b9a`: 76 of 77 failed, and **B6 survived**.
- **What B6 weakens:** the message guard, comparing `provider` NEW with
  NEW.
- **Why it survived.** No test changed `provider` alone; the case that
  clears it also clears `external_message_ref`.
- **The write that got through.** Part A's CHECKs accept a message with
  `provider` `'whatsapp'` and no reference, and the channel trigger runs on
  INSERT only. So on a WHATSAPP thread, a message with no provider could
  gain one, and only the guard refuses that.
- **The fix.** `test_b_a_message_without_a_provider_never_gains_one`
  (`93c5acb`); B6 now fails it.
- **The other runs, none of them the record:**
  - at `1e200fe`: stopped after three mutations, for the cascade fixed in
    `9817d44` (§5);
  - at `6313b9a`: a repeat, stopped once the survivor was known;
  - at `dc35b50`: stopped when the refused-downgrade test was added (a test
    change changes the source fingerprint);
  - at `81de574`: two complete runs, both 77/77, identical. They showed the
    cascade fixed in `e1649a0`, under G1 and G2, and that commit superseded
    them.

**Not mutated:**
- **The index predicate's `external_thread_ref IS NOT NULL`.** A unique
  index treats NULLs as distinct (PostgreSQL 16 documentation, §11.6,
  §5.4.3), so no write differs without it. No test is claimed for it.
- **`db/migrations/env.py`'s single transaction.** It is not part of `0008`;
  the refused-downgrade test (§2.6) depends on it.

## 5. Existing files that changed, and why

- **`tests/test_migrations.py`:**
  - `HEAD` is `0008_communication_records`;
  - added: `test_the_declared_deltas_for_0008_are_exactly_its_nineteen_objects`,
    which also asserts that exactly six deltas carry a `digest_before`, all
    of them foreign keys;
  - `test_0007_refuses_to_downgrade`'s docstring: the single transaction.
- **`db/gate/migration_deltas.py`:** the 19 deltas, with their digests and
  proving tests.
- **`db/dev/mutation_runner.py`: an optional `deselect` argument,** printed
  in the header.
  - **Why it exists.** `0008`'s approved-text test fails under every mutation
    of `UPGRADE`, and would hide which behaviour test refuses the weakened
    write. The runs deselect it; the suite runs it.
  - **The other scripts** do not pass the argument, so their output is
    unchanged.
- **The test file, after its first commit, for the evidence's precision:**
  - `9817d44`: each pre-check case removes its rows and returns to head in a
    `finally`, and its assertion names the database's error, not alembic's
    log. A first mutation run, at `1e200fe`, was stopped and discarded
    because of this: a failing case left the scratch database at `0007`, and
    later tests failed as consequences.
  - `93c5acb`: the `provider` test (§4).
  - `d2c6431`: the refused-downgrade test (§2.6).
  - `e1649a0`: the downgrade test returns to head in a `finally`, for the
    same reason as `9817d44`, shown under G1 and G2.

## 6. The evidence round

Every row ran on a clean tree with the source fingerprint
`0fff3ec5…b6ad`. The commits after `7eedd77` are evidence and documents
only, and `docs/` is outside the fingerprint.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Suite (`record_test_run.py`) | **2741 passed, 0 failed, 0 errors, 0 skipped** | `ef0d96b` (run at `f9df6ab`) | `evidence/TEST-RUN-PROVENANCE.txt`, `junit-run.xml`; `run_binding.py`: `bound` |
| PostgreSQL gate (`record_gate_run.sh`) | PASS: ALL DATABASE-LEVEL CONTRACT TESTS PASSED, 70 PASS notices; the effective contract, inventory and policy table hold the same 67 operations | `f9df6ab` (run at `804e450`) | `evidence/gate-run.txt` |
| Authorization matrix | 189 rules; suite 2741/2741; no rule added (`0008` adds no authorization rule) | `804e450` (run at `6069f43`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| `0008` mutations | 77/77 fail, twice, identical | `6069f43` (run at `7eedd77`) | §4 |
| Before the fix | 98 failed, 26 passed, at `582b522` | `4d9e4ec` | §3 |
| The Slice 5 race under load | 9/20 and 3/20 under load, 0/20 idle | `d2c6431` | §6.1 |

**The earlier slices' records are not regenerated.** Each records its own
tree (the review of `8de5f7f`).
- **What `--check` gives:** `slice6_evidence.py --check` and
  `stop_gate_e_evidence.py --check` each exit 1, with ONE problem: the
  document is stale. They report no missing or failed mapped test, and no
  unbound run.
- **What regeneration would change.** Each generator was run, its word diff
  read, and the document restored. It would change:
  - the run's binding: the commit, the source fingerprint and the report
    digest;
  - the case count (2614 → 2741 and 2367 → 2741);
  - in STOP GATE E, the proof's generated id, and the migration list, which
    gains `0007` and `0008`.

  Their rows stay PASS: 39 and 49.

**One document changed after the recorded suite run.** Plan revision 6
updates the headings of §5.1 and G7-12, and §5.1's first paragraph, which
said the text was neither approved nor executed.
- **Why it matters:** `test_the_migration_executes_the_approved_text` reads
  §5.1 when it runs.
- **What was checked:** its SQL block is unchanged, and the test was run
  again against revision 6: 1 passed.
- **The fingerprint** is unaffected, since `docs/` is outside it.

**A run that was discarded, and why.** The first authorization matrix run, at
`3d28741`, ran the suite: 2740 passed, **1 failed**.
- **The failure:**
  `tests/test_mutation_tools.py::test_a_mutation_script_runs_only_under_its_main_guard[mutate_0008.py]`.
  That rule refuses a loop at a mutation script's module level (review of
  `f5a9d88`), and `mutate_0008.py` checked its anchors in one.
- **The fix.** The check moved into `_check_anchors()`, called under the
  `__main__` guard; the mutation list is unchanged. That run's matrix was
  not committed.
- **Why it was missed earlier.** The earlier full run (§6.1) had started
  before `mutate_0008.py` existed, so it never collected that case.
- **What followed.** Because the script changed, the two mutation runs at
  `4d9e4ec` (§4) were repeated at `7eedd77`, the tree they are bound to.
  Before that, the whole suite was run on the working tree: 2741 passed,
  0 failed.

### 6.1 The Slice 5 concurrency test

`tests/test_slice5_step5.py::test_r_s5_5_01_a_binding_created_while_a_share_is_held_waits_for_it`.

- **The observation.** It failed once, in a full run on the working tree
  before this step's commits: case PROPERTY, field `share_committed_first`
  False. Every other field held.
- **Measured, not dismissed** (`evidence/SLICE7-STEP1-S5-RACE-UNDER-LOAD.txt`):
  20 runs per condition, each in an isolated worktree on a database of its
  own, under four busy processes on the four CPUs, or idle.

  | Tree | Load | Runs with a failing case |
  |---|---|---|
  | `582b522` (no Slice 7 code) | 4 busy processes | 9 / 20 |
  | `dc35b50` (with `0008`) | 4 busy processes | 3 / 20 |
  | `582b522` | idle | 0 / 20 |
  | `dc35b50` | idle | 0 / 20 |

  In every failing case, the one differing field is `share_committed_first`.
- **Reading:**
  - **It is not caused by `0008`.** It reproduces under load on the tree
    that has no Slice 7 code. The 9 against 3 is not a difference between
    the trees: the test and the code it exercises are identical in both.
  - **The cause is the field's measurement.**
    - **What it compares:** two `time.monotonic()` readings, each taken in
      its thread after its HTTP response has returned through TestClient,
      not at commit.
    - **Why the order can invert.** The binding is blocked on a lock the
      share's transaction holds, so it can only proceed once that
      transaction ends. Under CPU load, the binder's thread can finish its
      response before the share's thread finishes its own.
    - **What is inferred, not measured:** that the commit order itself is
      right, which follows from that lock.
  - **What stays proven by the other fields:** the wait (the
    `pg_blocking_pids` witness), no commit of the binding while the share is
    held, both answering 200, SHARED, and one current binding.
- **Its state in the recorded runs:**
  - it passes in the full suite on the working tree (2741 passed, 0 failed);
  - it passes in the suite run of the evidence round, both cases
    (`junit-run.xml`, at `f9df6ab`);
  - both ran on an idle machine.
- **What this does not settle.** The field remains able to fail under load,
  on any tree. The test is outside this step and is not changed.
- **Proposed, for decision:**
  - (a) replace `share_committed_first` by a measurement taken on the
    database side;
  - or (b) remove it, since `binding_committed_while_the_share_was_held` and
    the witness already state what can be measured.

**Limits that are part of these results:**
- **The guards hold against the application's ordinary statements only.**
  - **Why.** The tests run as `turab`, a superuser and the owner of every
    table (EN-02), which can disable these triggers. One test does so for
    the core delete guards, inside a rolled-back transaction.
  - **K06 stays UNPROVEN.** `0008` is not evidence for K06, which stays an
    independent condition before the release gate.
- **R-1 stays unmet.** Nothing here receives a real event.
  - **What `0008` makes possible.** A thread's reference can be scoped and
    unique.
  - **What it does not prove.** That the relay extracts that scope from
    Meta's notification is R-1's duty 6, before any real traffic.
- **The SALE scope is not widened.**
- **These results are ours.** No independent run exists.

## 7. What remains

- **Step 1 closes on review.**
- **Step 2 does not start before that review.**
- **Standing:**
  - G4-5R open, SALE only;
  - K06 UNPROVEN;
  - R-1 unmet for real traffic.
