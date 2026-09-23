# Response to the independent review of `50f9961`

**Reviewed commit:** `50f9961a708b291b208059e68b8d4ed4fc319edd`
**Decision received:** Slice 2 not closed; R-S2-01 … R-S2-05 to be corrected.
**This response:** all five corrected, within the existing scope. No new
product features; no Slice 3 work.

**Every one of the five findings was valid.** Each is answered below with the
defect confirmed, the fix, and the acceptance test — including, for each, the
demonstration that the new test FAILS against the reviewed code.

---

## R-S2-01 · the version guard read without a lock

**Confirmed.** `concurrency.check` issued
`SELECT version FROM turab.requests WHERE request_id = :id` with no lock, the
engine sets no stricter isolation, and the `UPDATE` carries no version
predicate. Under Read Committed — where each statement takes its own snapshot
and a plain `SELECT` acquires no lasting lock — two transactions can both read
version *N*, both pass, and both write. The reviewer's reading of the SQL was
exactly right.

**Fix.** The guard now takes `FOR UPDATE`. The lock is acquired **before** the
version is read and is held by the caller's transaction until commit, so the
read and the write that follows are one decision. The second transaction
blocks, then sees *N+1* and gets the 409 it should always have had.

**Acceptance.** Two engines, two threads, both holding version *N*:
exactly one success and one `StaleVersion`; the row ends at *N+1*; the loser's
value appears neither in the row nor in the provenance trail.
`tests/test_slice2_concurrency.py`.

**Demonstrated against the defect.** Reverting the `FOR UPDATE` makes both
tests fail.

## R-S2-02 · state and staleness decisions unprotected at write time

**Confirmed, on both counts.** `transition` and `reconfirm` read through
`_row` without a lock and then wrote without re-asserting the state they had
decided from; the staleness pass put its conditions in the sub-select and
updated by id alone.

**Fix.**
- `_row` takes a `for_update` flag; every command that *decides* from the row
  it reads now locks it. A read for rendering does not.
- `transition` repeats the status it decided from in the `UPDATE … WHERE`.
- `reconfirm` restates `AND status = 'NEEDS_CONFIRMATION'` in its
  reactivating update, so that statement is correct on its own terms.
- The staleness pass selects candidates `FOR UPDATE SKIP LOCKED` and
  **re-asserts** status and the freshness window on the target row in the
  outer `UPDATE`.

**Acceptance.** Four two-connection tests with an explicit event order: a
reconfirmation racing a close does not reopen the CLOSED request; two
transitions from the same state do not both apply; the pass marks neither a
concurrently reconfirmed request nor a concurrently closed one.

**Demonstrated against the defect.** Reverting the locks and predicates makes
all four fail.

## R-S2-03 · the criteria path could not change a criterion

**Confirmed.** `API_CONTRACTS v0.2` says the endpoint "Adds/**changes**
structured criteria", and the contract's `RequestCriterion` declares
`request_criterion_id` — which the input model did not, so the reviewer's
payload was rejected. The service always inserted, so a resend hit
`UNIQUE(request_id, criterion_code, sort_order)`, and changing `sort_order`
to get around it left the old criterion in place.

**Fix.** The model accepts the **already-declared** `request_criterion_id`;
no field was invented. With it, the criterion is updated in place; without
it, one is added. The id is matched *together with* the request id, so a
criterion belonging to another request simply does not match — ownership is
part of the predicate, not a separate check. The request version is bumped
either way, and the change is recorded with its previous value. A collision
on the unique slot is now a typed 409 naming the change path.

**Acceptance.** Seven tests in `tests/test_slice2_http.py`: the id is
accepted; a change does not duplicate; the version bumps; an id from another
request is refused and that request is untouched; an unknown id is refused;
re-adding the same slot returns 409; the previous value is in the trail.

## R-S2-04 · reactivation did not apply the freshness condition

**Confirmed.** The closing decision kept reactivation "subject to the
activation and freshness conditions"; the implementation relied on the
transition table alone and never read the policy. The reviewer's probe proved
it with a stub that raises if the policy reader is called — it was not.

**Fix.** Reactivation from `PAUSED`/`CLOSED` to `ACTIVE` evaluates the
**active** policy. A stale or never-confirmed request is refused with
`ReactivationNeedsConfirmation`, naming the reason and the policy version and
telling the operator to reconfirm first. `/reconfirm` still does not move a
paused request, so the two steps stay explicit and each is recorded.
`last_confirmed_at` is never touched to get past the check.

**Also fixed, from the related note.** `reconfirm` refused nothing about its
date: a `confirmed_at` of 2099 was accepted and returned the request to
ACTIVE. A future confirmation is now refused; **historical confirmations
remain accepted**, which the review explicitly asked not to break.

**Acceptance.** Six tests, including that the check reads the active policy
(with no active policy it fails rather than assuming) and that a
seven-day-old confirmation still works.

**The reviewer's own instrument now reports the fix.** Re-running their probe
unchanged, the assertion they wrote — `policy lookup should be observed` —
fires.

## R-S2-05 · input models diverged from the contract

**Confirmed, all three cases.** `{"intent": null}` was accepted against a
`NOT NULL` column; `desired_property_type` took any string; a create with
target 200 and max 100 passed the model and would have reached the schema
`CHECK`.

**Fix.**
- `intent`, `payment` and `budget_flexibility` are non-nullable in the
  contract and the schema, so they are no longer `str | None`; an explicit
  `null` is refused by name. The genuinely nullable fields keep `null` as a
  real value that clears them.
- `desired_property_type` is constrained to the contract's enumeration, in
  both the create and the patch models, from one declaration.
- The budget pair is validated in the model when both values are present, and
  in the route **against the merged values** when a patch supplies only one —
  which is the case the reviewer specifically named.

**Acceptance.** Six tests: each rejection is a 4xx, writes nothing, **consumes
no idempotency key** (proved by a corrected retry with the same key
succeeding), and leaks no database text. The schema constraints remain as the
outer guard; SQL errors are not blanket-mapped to 422.

---

## Re-running the reviewer's probes against the corrected source

| Probe | Before | After |
|---|---|---|
| `declared_criterion_id` | rejected | **accepted** |
| `patch_null_intent` | accepted | **rejected** |
| `patch_unknown_property_type` | accepted | **rejected** |
| `create_inconsistent_budgets` | accepted | **rejected** |
| `actual_version_guard_sql` | `uses_row_lock: false` | **`true`** |
| `stale_paused_reactivation` | `policy_reader_called: false` | **the reviewer's own assertion fires** |
| `future_confirmation` | accepted, returned ACTIVE | **refused** |

Three adaptations were forced by the fixes and are declared in the re-run
script: the `_row` stub accepts `**kwargs` (it now takes `for_update`); probes
that the corrected code makes *raise* are recorded as raising rather than
aborting the script; and `reconfirm`'s clock query is answered by the stub.
The probes' intent is unchanged, and the reactivation stub is kept exactly as
written so the fix is shown by **their** assertion, not mine.

## On concurrency testing

The review required two connections and two transactions on real PostgreSQL,
not sequential ordering in one session. `tests/test_slice2_concurrency.py`
opens two engines and drives them from two threads with an explicit event
order and a settle delay, so the second transaction reaches its lock while the
first still holds one. Each test also asserts the **loser changed nothing** —
the half that distinguishes "serialised" from "both ran".

Every one of the six was confirmed to fail against the reviewed
implementation before the fix was kept.

## Items carried, unchanged in classification

- **DL-08a** — PROPERTY claim eligibility, deferred to its own scope; the
  operation stays refused.
- **DL-10** — the documented manual freshness pass is accepted for this slice.
- **DL-11** — the source reference in `PATCH` remains a declared constraint.
- **Account provisioning and D4** — not implemented; the bearer remains a
  temporary account reference and is not a documented login session. Nothing
  here presents the model as ready for real use on that basis.
- **DL-12** — answered by a numbered appendix that carries the approved text
  and its source without silently editing the original: see
  `docs/rfc/RFC-001-APPENDIX-A-invariants.md`.


---

# Follow-up review of `3f84f0e` — the three remaining items

**All three were valid.** R-S2-01, R-S2-02, R-S2-04 and DL-12 were accepted;
what follows completes R-S2-03 and R-S2-05 and hardens the concurrency
evidence.

## F-1 · R-S2-03, the slot collision

**Confirmed, both halves.** The pre-check lived only in the ADD branch, so
moving a criterion onto an occupied slot reached
`UNIQUE(request_id, criterion_code, sort_order)` and surfaced as a 500 — the
reviewer's injected `IntegrityError` showed the real path producing it, and
the reviewer was explicit that the collision itself was not raised on
PostgreSQL. And the ADD pre-check was unprotected: two concurrent commands
could both read "the slot is free".

**Fix, two layers.**
1. **The parent request is locked before the slot is inspected.** That is what
   makes the check meaningful: criteria commands on one request serialise, so
   neither can read a free slot the other is about to take. Locking the
   *criterion* row — which the CHANGE branch did — protects that row, not the
   slot a second command is racing for.
2. **One slot check for both branches**, excluding the criterion itself on
   CHANGE, plus a `SAVEPOINT`-guarded mapping of that **one named
   constraint** to the typed 409. The savepoint is what makes catching it
   safe; without one the failed statement poisons the transaction. Every
   other database error propagates unchanged — turning all of them into 409
   would hide real faults, which the review warned against.

**Acceptance.** A move onto an occupied slot returns 409 with both criteria
unchanged; the refused move records no provenance and **frees its key**
(proved by the same key then succeeding for a legitimate move); a move to a
free slot still succeeds; and on real PostgreSQL, two concurrent adds of the
same slot give one success and one `DuplicateCriterionSlot`, and a concurrent
move onto a slot being filled is refused with the criterion left where it was.

## F-2 · R-S2-05, the two regressions

**a. An empty string is not a null.** Confirmed: the sentinel check was
applied to *every* field, so `{"local_location_detail": ""}` — which the
contract allows with no minimum length — was refused with a message that
wrongly called it null. The reviewer's correction is also accepted: Pydantic
already rejects an explicit `null` for the three non-nullable fields, and
`exclude_unset=True` drops them when omitted, so the check could never have
been doing the job its comment claimed. It is now **scoped to those three
fields as a narrow assertion that must never fire**.

Tested: the empty string is accepted; `null` clears a nullable field;
omission changes nothing; and `null` is still refused for each non-nullable
field, by name.

**b. A datetime without an offset.** Confirmed: the model accepted it and the
comparison against the database clock raised
`TypeError: can't compare offset-naive and offset-aware datetimes` → 500.
`format: date-time` is RFC 3339 and requires an offset; a naive value is a
wall-clock reading, not a moment. It is refused in the model, as a field
error on `confirmed_at`. A historical confirmation with `Z` or an offset is
still accepted; a correctly-offset future one is still refused by the
service, for its own reason. The rejection writes nothing and consumes no
key.

## F-3 · the concurrency evidence

**Confirmed — and the strict assertions immediately found a real flaw in the
harness, not in the locks.** With outcomes actually inspected, it emerged
that a `Barrier` only starts two threads together; which one acquires the
contended lock first was still a race, and the tests had assumed an answer
they had not established.

**What changed.**
- **A deterministic handshake.** The holder takes its lock and signals; the
  contender does not begin until that signal arrives.
- **Interleaving is observed, not assumed.** The holder then waits until
  `pg_stat_activity` reports a backend on this database with
  `wait_event_type = 'Lock'` — the database witnessing that the contender
  really reached the contended point — and the test fails if that never
  happens within a deadline.
- **Every worker's outcome is asserted.** `assert_outcome` states, for both
  workers, either the value they must have returned or exactly which domain
  exception they must have raised, and fails on anything else.
- **The harness is self-checked.**
  `test_an_unexpected_worker_error_fails_the_assertions` injects an error into
  a worker and asserts the assertions bite — the precise weakness the review
  identified.

**One claim deliberately narrowed.** The two staleness-pass tests prove the
`FOR UPDATE SKIP LOCKED` behaviour: a row held by another transaction is
skipped. They do **not** exercise the repeated predicates in the outer
`UPDATE`, which guard a window inside a single statement that cannot be opened
from another connection. Those remain defence in depth, and reverting them
alone does not fail these tests. That is stated in the test docstrings rather
than left as an implied claim.

## F-4 · re-running your own probe script against the corrected source

Your `followup_probes.py` is a DB-free instrument that drives the real route
and model code behind explicit stubs. Re-run unchanged against the corrected
source it **raises `JSONDecodeError`** before writing any result, because it
calls `r.json()` on a response whose body is empty. That is worth stating
plainly rather than quietly working around:

- **Probes 2, 3 and 4 flip as intended.** The naive `confirmed_at` is now a
  422 field error on `confirmed_at` instead of a 500; the injected
  `IntegrityError` on the criterion `UPDATE` is now a typed 409
  (`DUPLICATE_CRITERION_SLOT`) instead of a 500; the stale reactivation is
  still refused. The recorded queries also show the new slot check running
  before the write.
- **Probe 1's 500 is the harness, not the route.** With
  `raise_server_exceptions=True` the cause is
  `AttributeError: 'Command' object has no attribute 'read_current'`. The
  stub `Command` never needed that method before, because the generic sentinel
  check refused `{"local_location_detail": ""}` and returned first. Reaching
  `read_current` is therefore the *evidence* that the corrected, scoped gate
  passes the field.

The adapted script is committed at
`docs/gate/evidence/followup_probes_rerun.py` with its output at
`docs/gate/evidence/followup-probes-after.json`. It differs from yours in
three ways, each annotated in the file: the three `assert` statements that
pin the *defects* are replaced by recorded outcomes carrying
`expected_by_reviewer`; a response is recorded without assuming it has a JSON
body; and probe 1 measures the reached point rather than a status.

**A finding your probe surfaced, reported against ourselves.** Probing
`{"intent": ""}` returns 422 — but from the **model's pattern**
(`string_pattern_mismatch` on `body.intent`), not from the route gate. All
three non-nullable fields carry a pattern that an empty string fails, so the
scoped gate **cannot be reached through the HTTP surface at all**. It is a
residual assertion, not a filter. We kept it and said so at the call site and
in the JSON rather than present it as the thing doing the work. The behaviour
the correction is actually claimed on — the PATCH returning 200 and storing
the empty string — is proven on PostgreSQL by
`tests/test_slice2_http.py::test_an_empty_free_text_field_is_accepted`, not by
this DB-free probe.

---

# Acceptance review of `73be3a7` — closure, and two corrections to the instruments

Slice 2 is closed within its agreed scope; R-S2-01…R-S2-05 are closed. The
acceptance review raised **no new blocking defect in the product**. It raised
two defects **in our instruments**, both confirmed here, plus one attribution
we were overstating. All three are corrected below.

## E-01 · the attached probe never reached the SAVEPOINT

**Confirmed, and the criticism is exact.** In the version shipped with the
`73be3a7` bundle, `Result.first()` returned one non-empty row for *every*
query, including the slot pre-check. The service therefore raised
`DuplicateCriterionSlot` **before the write**, and the recorded `queries` list
— the definitions query and the slot check, with no `UPDATE` and no savepoint
— says so plainly. The note attributing that 409 to an `IntegrityError`
intercepted inside a savepoint was **wrong for that run**. A recorded query
list that contradicts the note beside it is the worst kind of evidence,
because it reads as proof.

We took the second of the two offered remedies: the stub now answers each
query separately, and the probe reports what it actually did.

`docs/gate/evidence/followup_probes_rerun.py` now runs the same code four
times, differing only in what the stub answers:

| run | pre-check sees | write trips | reached the write | savepoint | result |
|---|---|---|---|---|---|
| a | slot taken | — | **no** | not opened | 409 `DUPLICATE_CRITERION_SLOT` |
| b | slot free | the slot constraint, on `UPDATE` (CHANGE) | **yes** | opened, rolled back | 409 `DUPLICATE_CRITERION_SLOT` |
| c | slot free | the slot constraint, on `INSERT` (ADD) | **yes** | opened, rolled back | 409 `DUPLICATE_CRITERION_SLOT` |
| d | slot free | `request_criteria_request_id_fkey` | **yes** | opened, rolled back | **not** mapped — propagates, 500 |

Run (a) is now labelled as evidence of the pre-check and nothing more. Runs
(b) and (c) are what the savepoint claim rests on, in both branches. Run (d)
is the one that matters most for honesty: the mapping is **specific**, not a
catch-all that would hide unrelated faults.

The limits are stated in the file: the constraint violation is **injected by
name**. This probe proves the exception-handling path. It does not simulate
or prove PostgreSQL's isolation behaviour, and it does not prove the unique
index fires — the two-connection tests do that on a real server.

## E-02 · the injected error was not the injected error

**Confirmed.** `explode()` was declared with no parameter while `_run_ordered`
calls the holder as `holder(locked)`. The worker therefore died of `TypeError`
before reaching the `RuntimeError("injected")` the test names. The assertions
did bite — but on the wrong exception, and the contender was released by the
`finally` in `run_holder` rather than by the handshake the test claims to
exercise. A self-check that does not perform the check it describes is worth
less than no self-check.

Corrected to `def explode(locked): locked(); raise RuntimeError("injected")`,
and the recorded outcome is now asserted to carry the intended error **before**
it is asserted to be refused:

```python
first, second = _run_ordered(explode, fine)
assert first == ("raised", "RuntimeError: injected"), first
with pytest.raises(UnexpectedWorkerError):
    assert_outcome(first, expect="anything", label="injected")
```

Verified by reverting the signature alone: the test then fails with
`AssertionError: ('raised', 'TypeError: ... takes 0 positional arguments but 1
was given') == ('raised', 'RuntimeError: injected')`. It now fails on exactly
the defect the review named, which is the property it lacked before.

## Attribution: concurrency evidence and idempotency-key evidence are separate

**Accepted.** The two concurrent criteria tests call the **service** directly,
not `CommandService`, so they cannot say anything about whether an idempotency
key was consumed. Our prose claimed both guarantees for both test families.
The test code never claimed it — the word does not appear in
`tests/test_slice2_concurrency.py` — but the report did, and the report is
what gets read. The correct division:

| guarantee | proven by | mechanism |
|---|---|---|
| two concurrent commands do not both take one slot; a move onto a slot another transaction holds is refused | `tests/test_slice2_concurrency.py` — `test_two_concurrent_adds_of_the_same_slot_yield_one_success_and_one_409`, `test_a_concurrent_move_onto_a_slot_being_taken_is_refused` | two engines, two transactions; interleaving witnessed by `pg_stat_activity` |
| the row and the provenance trail are unchanged after a refusal | `tests/test_slice2_http.py::test_the_refused_move_records_no_provenance_and_frees_its_key` | full HTTP stack through `CommandService` |
| a refused command does not consume its idempotency key | `tests/test_slice2_http.py` — `test_a_refused_input_consumes_no_idempotency_key`, `test_the_refused_move_records_no_provenance_and_frees_its_key`, `test_a_confirmation_without_a_timezone_is_refused` | `SELECT count(*) FROM turab.idempotency_records` after the refusal, then a corrected retry on the same key |

The command-transaction rollback that makes the third row true is unchanged by
this round.

## What closure does and does not mean

**Closed:** R-S2-01…R-S2-05, and Slice 2 within its agreed scope — REQUEST,
criteria, freshness — at commit `73be3a7` plus the two instrument corrections
recorded here.

**Not closed, and unchanged in classification:** DL-08a, DL-10, DL-11, account
provisioning, and D4. They keep the classification they were given; nothing in
this round revisited them.

**Closure is not operational readiness.** With account provisioning still an
declared operational gap and D4 open, this slice supports development and
review, not a live trial.

**Source of the results.** The 485 test cases and the 8/8 gate are **our**
saved run, recorded in `docs/gate/evidence/ARCHIVE-RUN-PROVENANCE-2026-09-22.txt` (renamed from `RUN-PROVENANCE.txt`, so it cannot be mistaken for a later round's log). The acceptance
review states it did not re-run the PostgreSQL suite or the concurrency tests
on an independent server, and we do not present its acceptance as
independent confirmation that they ran.
