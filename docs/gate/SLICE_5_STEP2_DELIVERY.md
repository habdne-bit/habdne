# Slice 5 · step 2 — the match review: REJECTED and NEED_MORE_INFORMATION

**Approved scope (review of `29a0f30`).** "أعتمد G5-3 بالخيار (أ)، وأجيز البدء
بالخطوة 2 في نطاقها المحدد في الخطة":
- **sequence:** NEED_MORE_INFORMATION (NMI) is not final; REJECTED and
  APPROVED are final; a later review is 409 `MATCH_REVIEW_DECIDED`,
  consistent with Slice 3's `_OPEN_MATCHES`;
- **input:**
  - a reason is required for REJECTED and NMI, and forbidden for APPROVED;
  - REJECTED takes the categories MATCH, FRESHNESS and PERMISSION, or `OTHER`;
  - NMI takes only a reason that yields a specific task (G5-4, [R6-1]);
  - a violation is 422, before any write and before the key is consumed;
- **codes:** approved. The approval and opportunity codes are step 3's, and
  are not attributed to step 2's tests. An unknown match id stays 403;
- **the limit:** REJECTED, NMI and its task, and §3.1's ordering rule.
  APPROVED stays refused until step 3, by a typed refusal with no
  footprint. Its test must show that APPROVED is a valid decision of the
  contract, not executed in this step, and is not classed as a gate failure.

**Status:** delivered for review. **Not** closed. The review of `7e84702`
found one blocker, an Idempotency-Key race with a final decision. It is
measured and fixed in §10.

**Still open:** G5-5, G5-10 and G4-5R (STOP GATE E is SALE only). **K06 stays
UNPROVEN** (EN-02; G5-13 (b), decided (ii)).

**Commits:**
- `65883ec`: the code, the tests, the mutation script, the matrix rows, the
  before-fix record;
- `5df5660`: six tests for the seven mutations the first run left alive
  (§6.1);
- `84a35b5`, `7a3f540`, `55f1ae3`, `6558e32`: the evidence (§7).

---

## 1. What step 2 contains

| File | Role |
|---|---|
| `src/turab/services/match_review.py` (new, sha256 `84bf4e10…7069`) | the rules: shape, lock, decided, reasons, task, stamp |
| `src/turab/api/routes/matching.py` | `MatchReviewInput` (closed, as in the contract) and the route `postMatchesMatchIdReview` |
| `src/turab/services/command.py` | `authorize_match_exists`: an unknown match id is 403 `OBJECT_NOT_AUTHORIZED` and **recorded** (R6.3a), as `read_match` already does |
| `src/turab/api/problems.py` | four codes (§2.3) |
| `tests/test_slice5_step2.py` (new, sha256 `c15b2982…6777` at `5df5660`) | 76 test cases |
| `db/dev/mutate_slice5_step2.py` (new) | 29 mutations (§5) |
| `db/gate/authorization_evidence.py` | five rows for step 2 (§7.1) |

No migration. No change to the contract, the overlay, the engine, the
rules, the pins or the registry. `docs/handoff/` untouched.

### 1.1 The order of the checks

Every refusal is decided before any write. The command runs `prepare`
inside the transaction, after the replay lookup and **before** the
idempotency claim (G4-15 D6). A refused review therefore writes no review,
no task and no audit row, and consumes no key.

| # | Check | Where | Refusal |
|---|---|---|---|
| 0 | role ADMIN or REVIEWER (contract `x-roles`; INV-2), staff only | route | 403 `ROLE_NOT_PERMITTED` |
| 0′ | the match exists; an unknown id is recorded as DENIED | route, `authorize_match_exists` | 403 `OBJECT_NOT_AUTHORIZED` |
| — | Idempotency-Key present; a replay returns the original | command | 400 `IDEMPOTENCY_KEY_REQUIRED`; 409 `IDEMPOTENCY_KEY_CONFLICT` |
| 1 | the input's shape: decision; reason required (REJECTED, NMI) or forbidden (APPROVED); explicit null and unknown fields refused | model, `check_shape` | 422 `VALIDATION_FAILED` (unknown decision, explicit null, unknown field), `REVIEW_REASON_REQUIRED`, `REVIEW_REASON_NOT_ALLOWED` |
| 2 | **the match row, `SELECT … FOR UPDATE`, the first statement on it** (§3.1) | `_lock_match` | — |
| 3 | decided: the latest review (ordered `reviewed_at DESC, match_review_id DESC`, as the schema's `latest_match_reviews`) is REJECTED or APPROVED, or an opportunity exists for the match | `_decided` | 409 `MATCH_REVIEW_DECIDED` |
| 4 | the reason: active in `reason_codes`; REJECTED: category MATCH, FRESHNESS or PERMISSION, or `OTHER`; NMI: a reason that maps to a specific task (G5-4), ACTIONABLE_UNKNOWN only with a specific stored `next_action` ([R6-1]) | `prepare`, `task_type_for` | 422 `REVIEW_REASON_NOT_ALLOWED` |
| 5 | APPROVED | `prepare` | 409 `REVIEW_DECISION_NOT_YET_AVAILABLE` (step 2 only, §2.3) |

Check 3 precedes check 5: APPROVED on a REJECTED match is answered
`MATCH_REVIEW_DECIDED` (`test_rejected_is_final[then2]`).

### 1.2 What is written, after the claim

- **One** `match_reviews` row. `reviewer_account_id` is the authenticated
  subject, never the body (the body is closed). `reviewed_at` is the §3.1
  stamp: `GREATEST(COALESCE(CAST(:clock AS timestamptz), clock_timestamp()),
  max(reviewed_at) + interval '1 microsecond')` over the match's reviews,
  under the lock. Production binds `:clock` NULL; a test binds a fixed value
  to reach the equal-reading case. The statement is the plan's, compared by
  `test_the_stamp_statement_is_the_plans`.
- **For NMI, one NEW task** (G5-4 (a)), never reused:
  - its type from the reason (G5-4's table) or, for ACTIONABLE_UNKNOWN, the
    stored `next_action.type` when specific ([R6-1]);
  - a fixed title per type, never the reviewer's free text;
  - priority HIGH when the match has a blocking UNKNOWN criterion, NORMAL
    otherwise;
  - `request_id`, `property_id` and `match_id` from the match;
  - `payload = {match_review_id, next_action}`: the link to its review
    (step 0, measurement J: no column names a review);
  - written to the audit log through `audit_rows`, as Slice 3's tasks.
- **The response** is the contract's 200 body: `{match_id, decision,
  opportunity: null, task}`, with `task` the contract's `Task` (12 keys) for
  NMI and null for REJECTED.
- **Never written:** an opportunity (§7 condition 3).

## 2. The decisions, as implemented

### 2.1 G5-3 (a), the sequence
- `FINAL = {"REJECTED", "APPROVED"}`. NMI is not final: NMI then NMI, NMI
  then REJECTED are accepted (`test_nmi_is_not_final`).
- An opportunity created from the match decides it too
  (`test_a_match_with_an_opportunity_is_decided`). No step-2 path creates
  one: that test writes an APPROVED review and an opportunity by SQL, as a
  fixture.

### 2.2 G5-4 (a) with [R6-1]
- The nine reason codes of G5-4's table map to the five specific types.
  Every other reason, `OTHER` included, is refused for NMI.
- ACTIONABLE_UNKNOWN takes the type of the match's stored `next_action`
  only when it is one of the five specific types. When `next_action` is
  null or its type is `OTHER`, it is refused. Both refusals are tested over
  HTTP on real engine output (an APARTMENT with ROOMS unknown gives
  `OTHER`; an ELIGIBLE match gives null), and the pure function is tested
  over the whole vocabulary of `action.next@1`, read from the pinned
  function's source.

### 2.3 The codes

| Code | Status | Approved list | Note |
|---|---|---|---|
| `REVIEW_REASON_REQUIRED` | 422 | yes | |
| `REVIEW_REASON_NOT_ALLOWED` | 422 | yes | |
| `MATCH_REVIEW_DECIDED` | 409 | yes | |
| `REVIEW_DECISION_NOT_YET_AVAILABLE` | 409 | **no** | **my temporary step-2 code**, below |
| `OBJECT_NOT_AUTHORIZED` | 403 | yes (existing) | an unknown match id |

**`REVIEW_DECISION_NOT_YET_AVAILABLE` is not in the approved list.** The
review asked for "a typed refusal with no footprint" for APPROVED, and for a
test that shows it is a valid decision not executed in this step, not a
gate failure. No approved code says that:
- `MATCH_GATES_NOT_PASS` would say the gates failed, on a match whose gates
  all PASS;
- `VALIDATION_FAILED` would say the body is invalid, and APPROVED is valid
  in the contract;
- `MATCH_REVIEW_DECIDED` would say the match is decided, and it is not.

So step 2 adds this one code. It is 409 (declared for this operation in the
contract): the body is valid, and the state of the service does not yet
execute it. Its detail reads: "APPROVED is a valid decision; its execution
(the currency check and the opportunity) is delivered in Slice 5 step 3.
Nothing was recorded". **It is removed in step 3**, when APPROVED is
executed. If the reviewer prefers another code or status, it is one line.

`test_approved_is_refused_in_step_2_as_not_yet_available` asserts the
code, the detail, the zero footprint, and that the code is not a gate code.
It runs on an ELIGIBLE match (every gate PASS) and on an NMI match, with
the same answer, so the answer is not a gate verdict.
`test_the_step_3_codes_are_not_introduced_by_step_2` asserts that
`MATCH_GATES_NOT_PASS`, `MATCH_SUPERSEDED`, `MATCH_CONTEXT_NOT_VALID` and
`OPPORTUNITY_ALREADY_OPEN` do not exist yet: no step-2 test is attributed to
them.

## 3. §3.1, the ordering rule, against the command

**How each is driven.** The clock cases and the two races call the service
(`prepare` then `record`, as the route does) in their own sessions. The
clock cases need the seam, and the races need two transactions held open
together. A3 goes over HTTP.

| Planned test (§3.1, §7 condition 4) | Test | What it shows |
|---|---|---|
| equal reading | `test_an_equal_clock_reading_still_stamps_strictly_after` | two reviews with the same clock value: the second is stamped `t + 1 µs` and is the latest |
| future previous stamp | `test_a_previous_stamp_in_the_future_is_still_exceeded` | a previous stamp after the clock is still exceeded |
| first review | `test_the_first_review_takes_the_clock` | with no earlier review, the stamp is the clock |
| A5 | `test_a5_the_waiting_review_committed_last_is_the_latest` | B waits on A's lock (witness: `pg_blocking_pids`), commits last, and is the latest |
| A5, decided | `test_a_review_waiting_behind_a_rejection_is_refused_as_decided` | B waits behind A's REJECTED, then sees it and is refused `MATCH_REVIEW_DECIDED` |
| A3 | `test_a3_twenty_sequences_end_with_the_last_decision` | 20 of 20 pairs end with the second decision |

**A3 is tested as NMI → NMI, over HTTP.** The plan's form is APPROVED → NMI,
and APPROVED is step 3's. One command writes one review, so two reviews in
one transaction cannot arise. The test commits two NMI reviews with
different reasons, twenty times, and each ends with the second as the
latest. Step 3 adds the APPROVED form.

## 4. Before the change (measured)

`evidence/SLICE5-STEP2-BEFORE-FIX.txt`, in an isolated worktree at
`29a0f30`, with the test file of `65883ec` (sha256 `c0afd6e3…8555`, 70
cases). The six tests added at `5df5660` (§6.1) import the same module, so
they cannot run at `29a0f30` either. The record was not re-taken for them.
- **the shipped test file** cannot be collected: `turab.services.match_review`
  does not exist (0 tests run);
- **a probe** that does not import it shows that the operation is absent:
  REJECTED, NMI and APPROVED each get the generic 404 `NOT_FOUND`, with no
  review and no task written. The probe's source and digest are in the
  record.

**A deviation from the discipline, stated.** The code was written before
this record was taken. The record was then taken at the base commit, in a
worktree holding none of the new code, so it measures what a record taken
first would have measured.

## 5. Existing tests that changed, and why

Step 2 gives `match_reviews` its first writer. Two existing tests encoded
the Slice 4 boundary "no file writes `match_reviews`" (G4-15 D1).

1. **`test_slice4_step7::test_no_path_writes_a_review_or_an_opportunity_and_matching_writes_no_task`.**
   - Before: no file may insert into `match_reviews` or `opportunities`.
   - Now: neither the run nor the `matching` package inserts into
     `match_reviews`, `opportunities` or `tasks` (Slice 4's own claim,
     unchanged); and the current writers are pinned: `match_reviews` by
     `services/match_review.py` alone, `opportunities` by none.
   - Name kept: `SLICE_4_STEP7_DELIVERY.md` cites it.
2. **`test_slice4_stop_gate_d.py`, its `tree` fixture.** These tests prove
   that STOP GATE D's generator refuses what is not proven, on a copy of
   the tree. The copy's baseline must pass. D's condition 6 requires no
   writer of `match_reviews`, so a copy of the current `src` has no passing
   baseline, and all ten tests errored in the fixture.
   - Now the copy's `src` is taken by `git archive` from the commit the
     committed D document is bound to (`333b5f7`), the Slice 4 tree D
     records. `tests`, `db` and `docs/gate` are the current tree's.
   - Before step 2, `git diff 333b5f7 29a0f30 -- src` is empty, so the
     fixture tested the same `src` until now.
   - **Cost:** the fixture now needs the git history (it fails, not skips,
     without it).
   - **The alternative,** if the reviewer prefers: change the generator to
     admit the review command. I did not, because D is the record of the
     Slice 4 tree (review of `f5a9d88`, decision 2), and its condition 6 is
     Slice 4's boundary.

## 6. Mutation evidence

`db/dev/mutate_slice5_step2.py`, 29 mutations, each weakening ONE rule:
- **S1–S3:** the stamp and the lock;
- **D1–D5:** decided;
- **R1–R9:** the reasons;
- **T1–T6:** the task;
- **A1–A3:** APPROVED in step 2;
- **Z1–Z3:** authorization and the recorded denial.

### 6.1 The first run, kept

`evidence/SLICE5-STEP2-MUTATIONS-FIRST-RUN.txt`, at `65883ec`, clean tree,
source fingerprint `e3481c19…fa07`. **22 of 29 failed; 7 survived.** Each
survivor was a gap in the tests, not a defect in the code:

| Survivor | Why no test failed | Test added or changed at `5df5660` |
|---|---|---|
| D3 an opportunity does not decide | the opportunity test also had an APPROVED latest review, which decides alone | `test_an_opportunity_decides_even_when_the_latest_review_is_not_final`: a later NMI review (SQL) is the latest, so only the opportunity can decide |
| D4 decided reads the OLDEST review | every decided test had one review, so the oldest was the latest | `test_nmi_is_not_final` now checks that NMI then REJECTED is final (its docstring said so; it did not test it) |
| R4 an inactive reason is accepted | every reason used was active | `test_an_inactive_reason_is_refused`: deactivated inside the service's transaction, rolled back, and checked active afterwards |
| R8, R9 a mapping changed | the NMI test was parametrized FROM `NMI_TASK_TYPES`, the module under test, so it agreed with any change | G5-4's table written out in the test; `test_the_nmi_mapping_is_g5_4s_table` |
| T3 a non-blocking UNKNOWN raises the priority | the NORMAL case had no UNKNOWN at all | a PREFERRED DOCUMENT_TYPE unknown (measured: UNKNOWN, `blocking` false) gives NORMAL |
| T6 the title is the reviewer's text | no NMI test sent a `reason_text` | `test_the_task_title_is_fixed_and_never_the_reviewers_text` |

Before the record, those seven were re-run against the new tests, on a
dirty tree (a check, not evidence): each failed, by the intended test.

### 6.2 The record

`evidence/SLICE5-STEP2-MUTATIONS.txt`.
- **Run:** at `5df5660`, clean tree, source fingerprint `1405da35…8ec3`.
- **Result: 29 of 29 fail, none survives.** The baseline is 76 passed.
- **Restoration:** every mutated file was restored, and verified by sha256.

**Each mutation fails a test of its own rule, not only a text check:**
- S1 fails the equal-reading and future-stamp tests, as well as
  `test_the_stamp_statement_is_the_plans`;
- S3 (no `FOR UPDATE`) fails both race tests, on their `pg_blocking_pids`
  witness;
- A2 and A3 (APPROVED answered as an input error, or as decided) fail
  `test_approved_is_refused_in_step_2_as_not_yet_available`, on both
  matches.

### 6.3 An observation for step 3, from A1

A1 removes the APPROVED refusal. On the NMI match, the review INSERT then
reaches the frozen schema trigger `enforce_approved_review_gate`, which
raises "Cannot approve match … before all opportunity gates pass" as a
database exception, not a typed refusal. On the ELIGIBLE match, the
response carries no `code` (the test fails with `KeyError: 'code'`): the
APPROVED review was accepted. Step 3 must refuse before the trigger, with a
named code. That is G5-3's `MATCH_GATES_NOT_PASS` ("named before the trigger
fires"). This is noted for step 3. No step-2 path reaches it: the refusal
comes first, and A1 is killed.

## 7. The evidence round

Each row ran on a clean tree, source fingerprint `1405da35…8ec3` (the code
and tests of `5df5660`; the evidence commits change neither).

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations | 29/29 fail | `5df5660` → `84a35b5` | §6.2 |
| Authorization matrix | **156 rules**, all PASS: 151 + 5 for step 2 (§7.1); suite 2135/2135 | `7a3f540` | `AUTHORIZATION_EVIDENCE_MATRIX.md`; `--check --no-run`: current |
| PostgreSQL gate (`record_gate_run.sh`) | PASS; 70 database-level PASS notices, 0 FAIL; effective contract, inventory and policy table hold 67 operations | `55f1ae3` (run at `7a3f540`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **2135 passed**, 0 failed, 0 errors, 0 skipped | `6558e32` (run at `55f1ae3`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |

### 7.1 The five matrix rows

| Ref | What it holds |
|---|---|
| `S5-2 / RFC-001 §2.1 / R6.3a` | only ADMIN and REVIEWER review (not the OPERATOR); the reviewer is the subject; an unknown id is 403 and recorded |
| `S5-2 / G5-3 (a)` | REJECTED and APPROVED final, NMI not; an opportunity decides; the input narrowed before any write; an inactive reason refused; no key consumed |
| `S5-2 / G5-4 (a) / R6-1` | G5-4's table; one specific task per NMI review; a fixed title; ACTIONABLE_UNKNOWN refused without a specific next action |
| `S5-2 / §3.1 [R3-1]` | the lock and the strictly increasing stamp: equal reading, future stamp, A5, A5 decided, A3 |
| `S5-2 / step boundary` | APPROVED refused with its own code, no footprint; no opportunity writer; one review writer |

### 7.2 STOP GATE C and D, after this step

Neither is regenerated (review of `f5a9d88`, decision 2).
- **`stop_gate_d_evidence.py --check` exits 1, with two problems:**
  1. the document is stale, as since step 1;
  2. **new:** `match_reviews written by ['src/turab/services/match_review.py']`.
     D's condition 6 is Slice 4's boundary. Step 2 crosses it by design,
     and the document stays the record of the Slice 4 tree (`333b5f7`).
     It is not a pass credited to this tree, and is not presented as one.
- `stop_gate_c_evidence.py --check` reports what it has reported since
  Slice 4 step 1: stale against the current tree.

## 8. Limits that are part of these results

- **The application role is a superuser and the owner** (EN-02). The guards
  hold against the application's statements; such a role could bypass a
  trigger. K06 stays **UNPROVEN** (G5-13 (b), decided (ii)), and nothing in
  this step is evidence for it.
- **Authorization is by role, per the contract.** No relation is read, for
  authorization or anything else (§7 condition 7).
- **APPROVED is not executed.** Nothing here proves the currency check,
  the opportunity, its uniqueness or its concurrency: step 3.
- **These results are ours.** No independent run exists.

## 9. What remains

- **Step 2 closes on review.**
- **Step 3** (APPROVED: §3.7, the opportunity, uniqueness, concurrency)
  needs G5-2 and G5-5. G5-5 is open. Step 3 removes
  `REVIEW_DECISION_NOT_YET_AVAILABLE` and adds the APPROVED → NMI form of A3.
- **Standing:** G5-5, G5-10 and G4-5R open; K06 UNPROVEN; STOP GATE D is
  not regenerated in Slice 5, and STOP GATE E binds to Slice 5's run.

## 10. The review of `7e84702`: the key and a final decision

**What the review checked itself:**
- the bundle's digest;
- its 358 manifest entries;
- `run_binding.py`: `bound`.

These check the attachments and their binding. They are not a re-run of
the PostgreSQL tests or of the mutations.

**Accepted:**
- `REVIEW_DECISION_NOT_YET_AVAILABLE` (409), within step 2's limits. It
  describes an APPROVED that is valid in the contract and not executable
  now, without claiming a gate failure. It is removed when step 3 executes
  the approval.
- STOP GATE D stays the record of the Slice 4 tree. Its current `--check`
  failure counts as neither a pass nor a new failure of that record.

**The blocker: the Idempotency-Key raced with a final decision.**
`CommandService.run` reads the key BEFORE `prepare`.
`match_review.prepare` locks the match, then refuses it if it is decided,
and both happen before the key is claimed. So:
1. A and B start with the same actor, path and key. B's first read does not
   see A's uncommitted record.
2. B waits on the match lock A holds. A commits REJECTED and its result.
3. Once the lock is released, B sees the final decision and returns 409
   `MATCH_REVIEW_DECIDED`. It should have returned A's result when the body
   matches, or 409 `IDEMPOTENCY_KEY_CONFLICT` when it differs
   (API_CONTRACTS §2.3).

The review inferred this from the code's order, without a concurrent run.
The existing replay test is sequential. The concurrent lock tests use two
actors and call the service directly, so they never reach the key's path.

### 10.1 Measured before the fix

`evidence/SLICE5-STEP2-KEY-RACE-BEFORE-FIX.txt`.
- **Commit and tree:** at `7e84702`, on a tree clean except the new test
  file.
- **Same file shipped:** sha256 `9446936a…f76a`, the file committed with
  the fix.
- **Three runs, identical:**
  - **final-same-body:** B returns 409 `MATCH_REVIEW_DECIDED` instead of
    A's response;
  - **final-other-body:** B returns 409 `MATCH_REVIEW_DECIDED` instead of
    `IDEMPOTENCY_KEY_CONFLICT`;
  - **controls, all passing:** NMI with the same body, NMI with another
    body, and another key.

**How the test drives it:**
`test_a_same_key_review_waiting_on_the_match_lock_is_answered_by_the_key`.
- **Over HTTP, one actor,** two app clients on two threads.
- **A's pause:** A's request is paused inside `match_review.record`. By then
  it has read the key, locked the match, claimed the key and inserted its
  review, and it has not committed.
- **B:** sent with the key of the case.
- **The witness, asserted before A is released:**
  - B's backend waits on a Lock, in the `SELECT … FOR UPDATE` of
    `_lock_match`;
  - `pg_blocking_pids(B)` names A's backend;
  - a third connection sees no review of the match and no record of
    either key.

  So B read the key before A's commit, then waited on A's lock.
- **After A commits, the test checks:**
  - B's answer;
  - **one** review row;
  - the task count: one for NMI, none for REJECTED;
  - the key records: one for the shared key, or, with another key, one for
    A's key and **none** for B's.

### 10.2 The fix (`ef58077`)

`CommandService.run`: a refusal raised by `prepare` is checked against the
key once more, before it is returned.
- **The read:** `idempotency.committed_if_any`, a `lookup` on a NEW
  connection. `committed` (Slice 4, R-S4-7-02) now uses it too.
- **A same-key call committed meanwhile:** the key answers, with A's result
  for the same body, or `IDEMPOTENCY_KEY_CONFLICT` for another.
- **Otherwise:** the refusal stands. Nothing is written, and the key is not
  consumed. The read is a SELECT on another connection.
- **A database error** (`DBAPIError`) is re-raised unchanged. It is not a
  refusal decided by the state.

**Why a new connection.** Under Read Committed, which the review uses, the
transaction's own session would also see A's commit. Under REPEATABLE READ,
which the matching run uses, it would not. A new connection sees a
committed record under both, as `committed` already did.

### 10.3 After the fix

| Evidence | Result |
|---|---|
| The new test | 5/5 cases pass: final-same-body and final-other-body as §2.3 requires; the three controls unchanged |
| Step 2's file | 81/81 |
| Ordinary refusals | still write nothing and consume no key (`_refused` footprint tests; `test_a_refused_review_does_not_consume_its_key`) |
| Mutations | 30/30 fail, none survives, at `ef58077`, clean tree, fingerprint `fcb5f91b…aa9a` (`evidence/SLICE5-STEP2-MUTATIONS-AFTER-KEY-FIX.txt`). The new K1 removes the check, and fails exactly final-same-body and final-other-body |
| Suite, gate, matrix | §10.4 |

### 10.4 The evidence round after the fix

Each row ran on a clean tree, source fingerprint `fcb5f91b…aa9a`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations | 30/30 fail | `ef58077` → `288a6a1` | §10.3 |
| Authorization matrix | **157 rules**, all PASS (one new: `S5-2 / API_CONTRACTS §2.3`); suite 2140/2140 | `5aed43e` | `AUTHORIZATION_EVIDENCE_MATRIX.md`; `--check --no-run`: current |
| PostgreSQL gate | PASS; 70 database-level PASS notices, 0 FAIL; 67 operations in parity | `fbc8549` (run at `5aed43e`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **2140 passed**, 0 failed, 0 errors, 0 skipped | `22d1880` (run at `fbc8549`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |

The step-2 records of §6 and §7 stay as they were: they are bound to
`5df5660` and its fingerprint `1405da35…8ec3`. The table above supersedes
them for the current tree. STOP GATE D's `--check` reports the same two
problems as in §7.2.

### 10.5 Limits of the fix, stated

- **Every non-database exception from `prepare` is checked against the key,**
  not only `ReviewRefused`. A same-key result therefore answers any such
  exception, but only when that result is committed, so the call's outcome
  is already known.
- **The opposite order is not changed.** Suppose B is refused without
  waiting for A (A still uncommitted, and B's refusal not caused by A).
  B returns its refusal, because no record is committed when B decides. A
  retry with the key after A's commit replays A.
- **The new-connection choice is tested only under Read Committed.** No
  current REPEATABLE READ command has a `prepare` refusal that a same-key
  call can cause: the matching run refuses on the policy version, a request
  that cannot be matched, or RENT. So no test tells the new connection from
  the transaction's own session.
- **The shared machinery changed.** The whole suite passes: 2140/2140 in our
  run on the uncommitted tree that became `ef58077`, and in the bound run of
  §10.4. The
  Slice 4 test `test_a_refusal_is_decided_before_any_write` still observes
  no INSERT, UPDATE or DELETE during a refused matching run.
