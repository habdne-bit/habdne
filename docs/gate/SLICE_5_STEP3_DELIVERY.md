# Slice 5 · step 3 — APPROVED, the currency check, and the one opportunity

**Approved scope (review of `60b0152`).** "أعتمد G5-5 وفق الخيار (أ)، وأجيز
بدء الخطوة 3". The decision, item by item:

| Item | Decision |
|---|---|
| `sharing_scope` | the evaluated offer's `permission_scope`, as it is at approval, recorded with the permission snapshot |
| `why_real`, `known_differences` | the render-derivability rule, by the fixed list by criterion code and scope. A code's presence does not depend on `evidence_claim_id` |
| SUMMARY_ONLY | the property is rendered in `CustomerPropertyView` by four fields only: id, type, `supply_mode`, `canonical_location_id`. No area. This settles the G5-6 branch G5-5 needs; the customer-response tests stay step 4's |
| a field changed after the evaluation | the entry is withheld from the customer response when the current value differs from the match snapshot's, even if the outcome is unchanged. The stored `why_real` and the internal view are unchanged |
| the initial content | the plan's shapes of `why_real` and `known_differences`; the evaluated commercial context copied; `current_offer_id` = `evaluated_offer_id`; the binding order; NEW and VALID; the approval time in `last_confirmed_at` |

**Scope of the step:**
- **In scope:** APPROVED, the check of the facts now, and the creation of ONE
  opportunity with its uniqueness and concurrency guards.
- **Not in scope:** sharing, closing, revalidating, and the customer view.
- **Conditional, per the review:** the proof that no private expectation or
  claim leaks, and that withholding is correct when values change. Both
  depend on the HTTP tests in their planned places (step 4).

**Status:** **CLOSED** at `921ed01`, within the approved scope (§11).

**Still open:**
- G5-10 and G4-5R (STOP GATE E is SALE only). *[G5-10 decided since, in the review of `d0e0bc9`.]*
- K06 stays **UNPROVEN** (EN-02; G5-13 (b), decided (ii)).

**Commits:**
- `1a4839a`: the code, the tests, the mutation script, the matrix rows, the
  before-fix record;
- `5ee0c14`: the mutation N2 made valid (§7.1);
- `ed73dc3`, `359d660`, `30ca1b9`, `e98390e`: the evidence (§8).

---

## 1. What step 3 contains

| File | Role |
|---|---|
| `src/turab/services/currency.py` (new) | §3.7: `classify` (pure) and `check` (the facts now, read under locks) |
| `src/turab/services/match_review.py` | APPROVED: the checks 5a–5d, then the review and the opportunity; `shown_content`; `opportunity_view` |
| `src/turab/api/problems.py` | four codes in; `REVIEW_DECISION_NOT_YET_AVAILABLE` out |
| `src/turab/api/routes/parties.py` (`_run`) | a typed refusal may carry `Problem.field_errors` |
| `tests/test_slice5_step3.py` (new) | 57 test cases |
| `db/dev/mutate_slice5_step3.py` (new) | 33 mutations (§7) |
| `db/gate/authorization_evidence.py` | six rows for step 3, and one step-2 row replaced (§6) |

**What did not change:**
- no migration;
- no change to the contract, the overlay, the engine, the rules, the pins
  or the registry;
- `docs/handoff/` is untouched.

### 1.1 The order of the checks

Every refusal comes before any write, and before the idempotency claim
(G4-15 D6). A refused APPROVED writes:
- no review;
- no opportunity;
- no audit row;

and consumes no key.

| # | Check | Refusal |
|---|---|---|
| 0–1 | role, existence, key, the input's shape (step 2) | 403 / 400 / 422 |
| 2 | the match row, `FOR UPDATE` (§3.1) | — |
| 3 | decided: latest review REJECTED or APPROVED, or an opportunity exists | 409 `MATCH_REVIEW_DECIDED` |
| 5a | the stored eligibility ELIGIBLE and the four gates PASS. The frozen `trg_match_review_gate` refuses the same, untyped; this check names it first | 409 `MATCH_GATES_NOT_PASS`, the failing gates in `field_errors` |
| 5b | supersession per offer (G5-2): a match with the same request, property, policy AND evaluated offer, strictly later on (`evaluated_at`, `created_at`). A tie is not supersession; `match_id` never breaks one | 409 `MATCH_SUPERSEDED`, naming the later match |
| 5c | the currency check of §3.7 on the facts now, under locks (§1.3) | 409 `MATCH_CONTEXT_NOT_VALID`, every failing fact in `field_errors` |
| 5d | no open opportunity for the request on the property or on any alias of it (§3.3) | 409 `OPPORTUNITY_ALREADY_OPEN`, naming it |

### 1.2 What is written, after the claim

**One APPROVED review**, stamped by §3.1.

**One opportunity, after the review.** The frozen gate reads the latest
review.

| Column | Value |
|---|---|
| `request_id`, `property_id`, `approved_match_id` | the match's |
| `current_offer_id` | `evaluated_offer_id` (mandatory test 4) |
| `commercial_context_snapshot` | the match's, copied **in SQL**, so it is the stored bytes |
| `permission_snapshot` | the snapshot of the approval's instant. Its `permission_scope` is the offer's now, and its `derived_by` is the version the match recorded |
| `sharing_scope` | that `permission_scope` (G5-5 (a)) |
| `current_permission_binding_id` | the first CURRENT binding: offer-bound before property-bound, then `bound_at`, then id |
| `why_real`, `known_differences` | §2.3 |
| `status`, `validity_status` | NEW, VALID: the birth rule of `0006` |
| `last_confirmed_at` | the check's instant (§2.2 (iii)) |
| `created_by_account_id` | the reviewer |
| `last_activity_at`, `shared_at`, `engaged_at`, `closed_at` | null |

**Audit:** by the frozen `audit_match_reviews` and `audit_opportunities`
triggers, with the reviewer as actor (tested).

**The response:** `{match_id, decision: "APPROVED", opportunity, task:
null}`. `opportunity` is the contract's `InternalOpportunityView`, key for
key. The operation is staff only (R9.2).

### 1.3 Locks, and why

`currency.check` locks, in this order, after the match lock:

| Row | Lock | What it gives |
|---|---|---|
| the request | `FOR NO KEY UPDATE` | two approvals on one request serialize here, so 5d sees every opportunity committed before it, aliases included. The index cannot see aliases (§3.3) |
| the property, the offer | `FOR SHARE` | — |
| the consent bindings and their grants | `FOR SHARE` | — |

**The check's instant is read after the locks.** So a writer of any checked
fact either commits before the check reads, or waits for the approval's
commit. The facts classed are the facts at commit.

## 2. The decisions, as implemented

### 2.1 G5-2 (a) and §3.7

**The table is `currency.TABLE`, one row per fact**, in this order:
1. the request status;
2. the offer status;
3. the availability;
4. the identity;
5. the request freshness;
6. the property freshness;
7. the offer freshness;
8. the permission.

**How the table is applied:**
- The validity is the worst class: INVALID > NEEDS_CONFIRMATION > VALID.
- Every fact that is not VALID is a reason.
- A value the table does not name is INVALID: an unreachable or new state
  fails closed.

**A reason's code is seeded only where its name states the fact** (as
`eligibility.py` does):
- REQUEST_STALE, PROPERTY_STALE and OFFER_STALE;
- PROPERTY_UNAVAILABLE;
- CONSENT_REVOKED and PERMISSION_MISSING.

Otherwise the fact's value is its code.

### 2.2 Interpretations to confirm

The plan did not settle these details. I took them as below. Each is one
place in the code if the reviewer prefers another.

1. **The rules and thresholds are the match's.** G5-2: "the same pinned
   rules Slice 4 recorded on the match … on snapshots taken now".
   - **What the check uses:**
     - the versions in the match's `explanation.engine`:
       `freshness.state`, `permission.binding_state`, `permission.gate`;
     - the thresholds in its `freshness_snapshot.threshold_days`.
   - **Consequence:** a later change of the active policy's thresholds
     does not change the approval of an earlier match. A new run, under
     the new policy, is a new match.
   - **Tested** by `test_the_check_uses_the_thresholds_and_versions_the_match_recorded`.
2. **The reasons are carried in `Problem.field_errors`**, the field the
   contract declares for a problem, rather than in a new key. The response
   is therefore not widened.
   - Each entry is `{field: the fact, code: the seeded code or the value,
     message}`.
   - `MATCH_GATES_NOT_PASS` lists its failing gates the same way.
3. **`last_confirmed_at` is the check's instant**, read after the locks.
   That is the instant the facts were confirmed current. It precedes the
   review's `reviewed_at`, which §3.1 stamps strictly after earlier
   reviews.
4. **A shown code must have been evaluated by its pinned rule:**
   `criterion.property_type@1` or `criterion.area_min@2`.
   - A result of another rule or version is not shown, because its keys
     were never checked.
   - This fails closed.
5. **Entry order, and labels:**
   - the entries of `why_real` and `known_differences` are ordered by
     criterion code, then ordinal;
   - the Arabic label is `criterion_definitions.label_ar`.

### 2.3 What may be shown (G5-5 (a); §3.4)

`SHOWN_BY_SCOPE`:

| Scope | Codes shown |
|---|---|
| SUMMARY_ONLY | PROPERTY_TYPE |
| PROPERTY_DETAILS_ALLOWED | PROPERTY_TYPE, LAND_AREA_MIN, BUILT_AREA_MIN |
| CONTACT_AFTER_CONFIRMATION | PROPERTY_TYPE, LAND_AREA_MIN, BUILT_AREA_MIN |

Everything else is never shown, LOCATION included [R3-5].

**`why_real`:**
- format `turab.why-real/1`;
- one entry per shown REQUIRED or PREFERRED criterion that is PASS;
- each entry is `{code, label_ar, importance}`.

**`known_differences`:**
- one entry per shown PREFERRED or FLEXIBLE criterion that is FAIL or a
  non-blocking UNKNOWN;
- each entry is `{code, compatibility}`.

**What is never written:** no value, delta, evidence, claim, rule or score.

**What is filtered when:**
- **The stored content is filtered by the scope at creation.**
  `sharing_scope` and `why_real` are written once (`0006`, rule 2).
- **The withholding of a changed field is a render-time rule** of the
  customer view (step 4). The stored row is not touched.

### 2.4 The codes

| Code | Status | In G5-3's approved list |
|---|---|---|
| `MATCH_GATES_NOT_PASS` | 409 | yes |
| `MATCH_SUPERSEDED` | 409 | yes |
| `MATCH_CONTEXT_NOT_VALID` | 409 | yes |
| `OPPORTUNITY_ALREADY_OPEN` | 409 | yes |
| `REVIEW_DECISION_NOT_YET_AVAILABLE` | — | **removed**, as accepted in the review of `7e84702` |

## 3. Tests (57 cases, `tests/test_slice5_step3.py`)

**§3.7 and G5-2:**
- **The table, without PostgreSQL:**
  - it is the plan's, written out in the test;
  - all **47 628** combinations: the validity is the worst class, and the
    reasons name every failing fact, in order;
  - the table names every value of the schema's three enums;
  - an unknown value fails closed;
  - every reason code is seeded.
- **Over HTTP, one fact changed after an ELIGIBLE run, ten cases:**
  - the request paused, or closed;
  - the offer paused, or withdrawn;
  - the property unavailable, or under discussion;
  - each freshness stale;
  - the consent revoked.

  Each gives 409, `field_errors` names exactly that fact, and nothing is
  written.
- **Several facts at once:** every one is named, and the worst decides.
- **A NEEDS_CONFIRMATION request:** its match is ELIGIBLE, and approval is
  409 (§3.7: approval is stricter than a run).
- **Approval ⇔ VALID:** forcing the check's answer decides the approval
  alone.
- **The locks:** a writer holds an uncommitted change of the request, the
  property, the offer or the binding.
  - The approval waits on it (`pg_blocking_pids`).
  - It then reads the committed change and is refused.
- **Supersession:**
  - a price change and a new run supersede that offer's old match only;
  - the other offer's match stays approvable;
  - two offers of one run, at equal times, are both current.

**Mandatory tests:**
- **1:**
  - NMI then APPROVED on one match: both rows kept, one opportunity;
  - the cross-match case (NMI on M1, APPROVED on M2 of the pair).
- **2:** one case per gate and per non-ELIGIBLE eligibility (hard,
  information, freshness, permission):
  - 409 `MATCH_GATES_NOT_PASS`, naming the gate, with nothing written;
  - the frozen trigger's refusal with the service bypassed, labelled
    SCHEMA.
- **3:**
  - `POST /opportunities` is not routed;
  - the APPROVED review is the one writer of `opportunities`.
- **4:**
  - `current_offer_id = evaluated_offer_id`, and the context equals the
    match's;
  - the trigger's refusal of another initial offer, labelled SCHEMA.
- **6:**
  - a second offer's match is refused while one is open;
  - after a close (SQL fixture: the close operation is step 5), the other
    match is approvable;
  - an alias's open opportunity blocks its canonical;
  - a match on a property that is now an alias is refused, by the identity
    fact;
  - two concurrent approvals of one pair over HTTP: B waits on A's request
    lock (witness), then is refused, typed, having written nothing. One
    opportunity;
  - the index backstop with the service check disabled maps to the same
    409. Labelled SCHEMA BACKSTOP.

**The opportunity:**
- the content of §1.2;
- the audit, with the reviewer as actor;
- the scope read at approval (changed after the run);
- the offer-bound binding chosen over an older property-bound one;
- a replay returns the same opportunity;
- an APPROVED match is final.

**The stored content:**
- **pure:**
  - only the listed codes, at every importance and compatibility;
  - the exact shapes;
  - another rule version is not shown;
  - a claim link, a value or a delta on any result changes nothing;
  - each shown rule reads only its rendered field and links no claim;
- **over HTTP:**
  - at PROPERTY_DETAILS_ALLOWED and at SUMMARY_ONLY, the stored fields are
    exactly as decided;
  - a sentinel seller expectation, the document's value, DOCUMENT_TYPE and
    BUDGET_MAX never appear.

## 4. Before the change (measured)

`evidence/SLICE5-STEP3-BEFORE-FIX.txt`. It was taken in an isolated
worktree at `60b0152`, with the final test file
(sha256 `2a460ef2…1371`).
- **The test file:** it cannot be collected, because `currency` does not
  exist.
- **A probe, over HTTP:** APPROVED is the step-2 refusal
  `REVIEW_DECISION_NOT_YET_AVAILABLE` in every case, with nothing written.
  This holds:
  - on an ELIGIBLE match;
  - on a match whose request was paused after its run;
  - on an NMI match.
- **Writers:** no file inserts into `opportunities`.

**As in step 2, the code was written before this record.** The record is
taken at the base commit, in a worktree without the new code.

## 5. Uniqueness and concurrency (§3.3), in one place

**Layer 1: the identity fact** (5c) refuses a property that is an alias now.

**Layer 2: the open-opportunity check** (5d) counts the property and its
aliases. It is made under the request lock.

**Layer 3: `ux_one_open_opportunity_per_pair`.** Its 23505 maps to the same
409. `opportunities_approved_match_id_key` maps to `MATCH_REVIEW_DECIDED`.

**Two approvals of the same match** serialize on the match lock (step 2).

**Two approvals of one request, on any matches,** serialize on the request
lock.

## 6. Existing tests that changed, and why

1. **`tests/test_slice5_step2.py`:**
   - **Removed:** `test_approved_is_refused_in_step_2_as_not_yet_available`
     and `test_the_step_3_codes_are_not_introduced_by_step_2`. They tested
     the step-2 boundary and its code, which step 3 removes.
   - **Writers:** `…_and_nothing_writes_opportunities` becomes
     `test_only_the_review_command_writes_match_reviews_and_opportunities`.
   - **Narrowed:** `test_step_2_never_writes_an_opportunity` becomes
     `test_nmi_and_rejected_never_write_an_opportunity`. APPROVED is now
     meant to write one.
2. **`tests/test_slice4_step7.py`, the D1 writer test:** the matching-side
   claim is unchanged. The pinned writer of `opportunities` is now
   `services/match_review.py`.
3. **`db/dev/mutate_slice5_step2.py`:** A1–A3 are removed. They mutated the
   step-2 refusal, which no longer exists. Their results stay in the step-2
   records.
4. **The matrix:** the row `S5-2 / step boundary` is replaced by
   `S5-2/3 / writers`.

## 7. Mutation evidence

`db/dev/mutate_slice5_step3.py`, 33 mutations, each weakening ONE rule:
- **G1–G3:** the stored gates;
- **S1–S2:** supersession;
- **C1–C9:** the check and its table;
- **L1–L5:** the locks;
- **O1–O4:** one open opportunity;
- **N1–N4:** the content;
- **W1–W5:** what is shown;
- **X1:** the reasons reaching the response.

### 7.1 The first run, kept

`evidence/SLICE5-STEP3-MUTATIONS-FIRST-RUN.txt`, at `1a4839a`, clean tree.
**32 of 33 failed. N2 was reported as surviving, but it was not a valid
mutant:**
- its replacement `'{}'::jsonb` sat inside a Python f-string;
- the mutated module therefore did not compile (`SyntaxError`), and no test
  ran;
- the runner counted it as a survivor. That is the safe direction: a
  mutant that does not run is never counted as killed.

At `5ee0c14` the braces are doubled, and every one of the 33 mutated texts
of the script is checked to compile. The step-2 script's 27 also compile.

### 7.2 The record

`evidence/SLICE5-STEP3-MUTATIONS.txt`.
- **Run:** at `5ee0c14`, on a clean tree, source fingerprint
  `0e70f363…61e8be`.
- **Result: 33 of 33 fail, none survives.** The baseline is 57 passed.
- **Restoration:** every mutated file was restored, and verified by sha256.

**Each lock mutation is killed by the test of its own lock:**
- L1–L2 (the request): the concurrent-approval test fails on its witness,
  and for L1 the request's writer test as well;
- L3, L4 and L5 (the property, the offer, the bindings): the writer test of
  that fact, each alone.

**Each of these mutations is killed by the one test written for its rule:**
- S2 by the per-offer supersession test;
- N3 by the binding-order test;
- C6 by the alias test;
- C4 by the fail-closed test;
- N2 by the context comparison (mandatory test 4).

## 8. The evidence round

Each row ran on a clean tree, source fingerprint `0e70f363…61e8be`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations | 33/33 fail | `5ee0c14` → `ed73dc3` | §7.2 |
| Authorization matrix | **162 rules**, all PASS (six new for step 3); suite 2196/2196 | `359d660` | `AUTHORIZATION_EVIDENCE_MATRIX.md`; `--check --no-run`: current |
| PostgreSQL gate | PASS; 70 database-level PASS notices, 0 FAIL; 67 operations in parity | `30ca1b9` (run at `359d660`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **2196 passed**, 0 failed, 0 errors, 0 skipped | `e98390e` (run at `30ca1b9`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |

**STOP GATE D is not regenerated** (review of `f5a9d88`, decision 2). Its
`--check` now reports three problems:
1. the writer of `match_reviews`;
2. **new:** the writer of `opportunities`. D's condition 6 is Slice 4's
   boundary, and step 3 crosses it by design;
3. the document is stale.

It stays the record of the Slice 4 tree. Its failure counts as neither a
pass nor a new failure of that record.

## 9. Limits that are part of these results

- **Supersession across policies is not tested by a two-policy case.** The
  query filters on `matching_policy_id`, and no test builds a second active
  policy. The mutation that would drop the filter is not in the script, so
  it is not reported as killed.
- **A run committing after the approval's supersession check is not seen.**
  The check is made under the match and request locks, and a run takes
  neither. Making it take one would change Slice 4's engine, which this
  slice may not. The window is the approval's own duration.
- **What is not in this step:**
  - the customer render and its withholding rule (step 4);
  - revalidate, share and close (step 5);
  - the "revalidate immediately after → VALID" half of §3.7's planned
    test (step 5, with revalidate);
  - E04's identity consolidation with an open opportunity (§6.2; step 6).
- **The application role is a superuser and the owner** (EN-02). K06 stays
  UNPROVEN.
- **These results are ours.** No independent run exists.

## 10. What remains

- **Step 3 is CLOSED** (§11).
- **Step 4:** the reads. The internal view, the customer view (G5-6 (a)
  with the four SUMMARY_ONLY fields, F5-1/F5-2/F5-3, R4-2's withholding,
  mandatory test 5), and the match queue.
- **Standing:**
  - G5-10 and G4-5R are open; *[G5-10 decided since, in the review of `d0e0bc9`.]*
  - K06 is UNPROVEN;
  - STOP GATE D is not regenerated in Slice 5. Its `--check` now also
    reports a writer of `opportunities` (§8).

## 11. The review of `921ed01`: step 3 CLOSED

**Step 3 is closed at `921ed01`, within its approved scope:** APPROVED, the
currency check, and the creation of one opportunity, with its guards
against duplication and concurrency.

### 11.1 What the review checked itself

- the bundle's SHA-256, `358999e6…87e0b`;
- the 366 entries of `MANIFEST.sha256`, all OK;
- `run_binding.py`: `bound`;
- the source fingerprint, recomputed: `0e70f363…61e8be`, equal to the
  evidence records';
- the digests of `SLICE_5_STEP3_DELIVERY.md` (`c41e11da…f865`) and of
  `SLICE_5_PLAN.md` (`4325bf2a…8dfe`);
- **the pure logic of §3.7's table, run independently over all 47 628
  combinations.** Every combination passed, the fail-closed handling of
  unknown values included;
- by reading:
  - the order MATCH_GATES_NOT_PASS → MATCH_SUPERSEDED →
    MATCH_CONTEXT_NOT_VALID → OPPORTUNITY_ALREADY_OPEN;
  - the lock order;
  - the creation of the opportunity;
  - the content of `why_real` and `known_differences`.

**What it did not re-run:** PostgreSQL, the mutation suite and the gate.
Its environment has no PostgreSQL client. It checked their records and
their binding to the fingerprint:
- 57/57 tests;
- 33/33 mutations;
- 2196/2196 in the suite;
- the gate: 70 PASS, 67 operations in parity;
- the matrix: 162 rules.

These stay **our** results, not an independent run.

### 11.2 The five interpretations of §2.2, approved as implemented

1. **The rules and thresholds are those pinned in the match itself.** This
   is G5-2's reading. A policy change after the match was created does not
   reinterpret the old match; it requires a new run.
2. **`Problem.field_errors` carries the reasons.** The contract already
   declares it, so the response schema is not widened by a new key.
3. **`last_confirmed_at` is the `as_of` of the check, read after the locks.**
   Its meaning, stated precisely: **the instant the SYSTEM confirmed that the
   opportunity's context was valid at approval**.
   - It is not a claim that the customer, the owner, or anyone else
     confirmed anything by hand at that instant.
   - The human confirmations stay where they are recorded: the request's,
     the property's and the offer's own `last_confirmed_at` and
     `commercial_terms_last_confirmed_at`.
4. **A criterion is shown only if it was evaluated by the known pinned
   version of the display rules.** This fail-closed rule prevents leaking an
   inference whose derivability was not proven.
5. **The order is `criterion_code`, then `ordinal`; the label is
   `criterion_definitions.label_ar`.** This keeps the output deterministic.

### 11.3 Two limits carried to step 6 and the slice's closure

§9's limits do not keep the step open. Two of them **must not disappear**.
They are carried, by name, to step 6 and to the final closure record of
Slice 5 (plan §8, "Carried to step 6"):

- **L-S5-3a: supersession across two policies is not proven.** No test
  builds a two-policy case, and no mutation drops `matching_policy_id`.
  - The implementation follows the decision ("within one policy").
  - Its proof is weaker than the rest of G5-2.
- **L-S5-3b: a new matching run can commit between the supersession check
  and the approval's commit.** The Slice 4 engine does not take the request
  lock.
  - This is stated, not hidden, and does not block step 3.
  - At step 6 or the final closure it must be either:
    - **accepted** as a documented consistency model; or
    - **closed** by a synchronization mechanism, if "the current match at
      commit" is decided to be a strict condition.

### 11.4 Unchanged

- **STOP GATE D:** its stale `--check` is not a failure of this step. It is
  the Slice 4 tree's record, and is not regenerated.
- **K06** is UNPROVEN.
- **G4-5R** and **G5-10** are open. *[G5-10 decided since, in the review of `d0e0bc9`.]*

None of these blocks the closure.

**Step 4 is authorized by the same review,** once this documentation
commit is made:
- **Scope:** the internal read, the customer read and the match queue,
  under G5-6, G5-7 and G5-11.
- **Its condition of acceptance:** proof of the withholding, and of no leak
  of any private expectation or claim.
