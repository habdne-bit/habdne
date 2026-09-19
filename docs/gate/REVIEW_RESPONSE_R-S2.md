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
