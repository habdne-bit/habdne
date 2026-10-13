# Slice 5 · step 5 — revalidate, share, close, the opportunity queue, and B10

**Authorized (review of `1556624`).** "الخطوة 5 مأذون ببدئها وفق القرارات
المعتمدة. الشريحة 5 ككل لم تُغلق بعد."

**Status:** **CLOSED at `3a60b3b`**, within its approved scope (§15).
Slice 5 as a whole is not closed. Step 6 is authorized.
- **The review of `6c6e614`** found one blocker, R-S5-5-01: a consent
  binding created while a share runs. It is measured, and fixed at
  `0a5c446` (§13).
- **The same review decided G5-8 (i) and (iii) as (a).** Both are
  implemented (§13.5, §13.6).
- **The review of `1f8a8df`** accepted the remedy and G5-8 (i) and (iii).
  It decided the `note` of close (a STATUS_CHANGE interaction) and of
  revalidate (a NOTE interaction, when given). Measured, and done at
  `37701ce` (§14).
- **The review of `3a60b3b` closed step 5** and authorized step 6 (§15).

*As first delivered, G5-8 (i) and (iii) were PROVISIONAL (§2.1, kept as
written).*

**Still open:**
- G4-5R (STOP GATE E is SALE only);
- K06 is UNPROVEN (G5-13 (b)(ii));
- L-S5-3a and L-S5-3b are carried to step 6 or the final closure (plan §8).

**Commits:**
- `93c7b37`: the code, the tests, the mutation script, the matrix rules, the
  before-fix record;
- `ab2ea1c`, `af47f26`, `10fc3c4`, `a1cf19f`: the evidence (§8);
- `6c6e614`: the note and plan revision 15;
- after the review of `6c6e614`: `0a5c446` (the fix and G5-8 (i)), then
  `f3dd4c3`, `04095e3`, `a7648b9`, `b3f4d9f` (the evidence), then the
  commit that adds §13 and plan revision 16 (`1f8a8df`);
- after the review of `1f8a8df`: `37701ce` (the note of close and
  revalidate), then `2b55e20`, `3301208`, `ee48c4f`, `30bccf5` (the
  evidence), then the commit that adds §14 and plan revision 17.

---

## 1. What step 5 contains

| File | Role |
|---|---|
| `src/turab/services/opportunity_commands.py` (new) | revalidate, share, close: the checks (`prepare_*`, read-only, before the key) and the writes |
| `src/turab/services/opportunity_views.py` | the opportunity queue (G5-11 (a)) |
| `src/turab/services/access.py` | `opportunity_queue`, audited once with its count |
| `src/turab/services/command.py` | `authorize_opportunity_exists`: an unknown id is 403 and recorded |
| `src/turab/api/routes/matching.py` | the three commands and `GET /backoffice/queues/opportunities` |
| `src/turab/api/problems.py` | five codes (§1.6) |
| `db/gate/authorization_evidence.py` | seven rules for step 5 |
| `tests/test_slice5_step5.py` (new) | 68 test cases |
| `db/dev/mutate_slice5_step5.py` (new) | 31 mutations (§7) |

**What did not change:**
- no migration and no contract change: the four operations are declared in
  the frozen contract;
- no INSERT writer: `match_review.py` is still the one writer of
  `opportunities` (H03), and the writer tests are unchanged;
- no existing test changed;
- `docs/handoff/` is untouched.

### 1.1 The order shared by the three commands

1. The route: the role gate (`x-roles`), the staff-only second lock, and
   the object check. An unknown opportunity is 403 `OBJECT_NOT_AUTHORIZED`
   and recorded (kind `OPPORTUNITY`), as the internal read answers it.
2. `prepare`, after the replay lookup and before the claim of the key
   (G4-15 D6). Its FIRST statement on the opportunity is
   `SELECT … FOR UPDATE`. So two commands on one opportunity serialize, and
   the second reads what the first committed. A CLOSED opportunity is 409
   `OPPORTUNITY_CLOSED` here, for every command.
3. A refusal raised in `prepare` writes nothing:
   - no change of the row;
   - no audit row, since the frozen `audit_opportunities` trigger fires only
     on a write;
   - no key consumed.
4. The write, after the claim: ONE `UPDATE` of the row. The audit row is
   the frozen trigger's, with the caller as actor.

### 1.2 Revalidate (G5-9; §3.7)

**The check.** `currency.check`, the function the APPROVED review uses:
- on the facts now;
- for the opportunity's `current_offer_id`;
- with the rule versions and thresholds the approved match recorded.

**What it writes, in one UPDATE:**
- `validity_status`, the check's class. It is not monotonic: INVALID returns
  to VALID when the facts do;
- `last_activity_at`, the check's instant;
- `last_confirmed_at`, the check's instant, **only when VALID**;
- `current_permission_binding_id`, the first CURRENT binding by G5-5's
  order, or null when none is CURRENT.

**What it never writes:** a snapshot (rule 2 of `0006` would refuse it
anyway), the status, the scope, or `current_offer_id` (B10).

**The response** is the `InternalOpportunityView`, plus `validity_reasons`:
every failing fact (`fact`, `value`, `class`, `reason_code`), in the
table's order. See §2, I1.

### 1.3 Share (G5-8)

`prepare_share`, read-only, in this order:
1. open, else 409 `OPPORTUNITY_CLOSED`;
2. the RECORDED `validity_status` is VALID, else 409
   `OPPORTUNITY_NOT_VALID` (`field_errors`: `VALIDITY_STATUS`);
3. the check now is VALID:
   - else 409 `CONSENT_REVOKED` when the permission fact is FAIL;
   - else 409 `OPPORTUNITY_NOT_VALID`;
   - `field_errors` names every failing fact;
4. the offer's `permission_scope` now is not narrower than the
   opportunity's `sharing_scope`, else 409 `SHARING_SCOPE_NARROWED`;
5. **PROVISIONAL** (G5-8 (iii) (a)): no CURRENT `CONTACT_BEFORE_SHARING`
   binding on the offer or its property, else 409
   `CONTACT_BEFORE_SHARING_REQUIRED`. The state of each binding is read by
   the rule version the match recorded.

**What the check found is never stored by a share.** It is stored by
revalidate, which every refusal's detail names as the remedy.

**On success, one UPDATE:**
- NEW → SHARED, with `shared_at` the check's instant, the first time;
- a later share keeps the status and `shared_at`, and moves
  `last_activity_at`;
- no validity, binding, confirmation or offer is written;
- no message is sent, and no `interactions` row is written.

**After a share,** the customer of the request reads the opportunity
(G5-7 (a), step 4's loader). The test shows 404 before and 200 after.

### 1.4 Close (G5-10, decided in the review of `d0e0bc9`)

1. The reason first (input): one of the eight codes, else 422
   `CLOSE_REASON_NOT_ALLOWED`. `CloseCommand` is closed in the contract: an
   undeclared field, a missing reason or a null is 422
   `VALIDATION_FAILED`.
2. The lock, and the closed check: 409 `OPPORTUNITY_CLOSED`.
3. One UPDATE writes `status = CLOSED`, `closed_at`, `close_reason_code`
   and `last_activity_at`, the last equal to `closed_at`.

**Notes:**
- Close is permitted from NEW, SHARED and ENGAGED, whatever the validity.
  The event stamps are left as they are: `0006` rules 5 and 6 refuse
  anything else.
- CLOSED is final. Any later revalidate, share or close is 409
  `OPPORTUNITY_CLOSED`, and writes nothing.
- A replay of the close on its own key answers before the state does: the
  same key and body return the original body (API_CONTRACTS §2.3).
- A test pins the eight codes to the seed: category OPPORTUNITY, active,
  plus `OTHER`.

### 1.5 The opportunity queue (G5-11 (a))

**Membership.** Open opportunities that are:
- INVALID;
- NEEDS_CONFIRMATION;
- or VALID and NEW (not yet shared: `0006` rule 5 keeps `shared_at` null
  exactly while NEW).

Every condition is a stored column. There is no time-based condition, and
no engine runs per row.

**Priority and reason:**

| case | `priority` | `reason` |
|---|---|---|
| INVALID | HIGH | `VALIDITY_INVALID` |
| NEEDS_CONFIRMATION | NORMAL | `VALIDITY_NEEDS_CONFIRMATION` |
| VALID and NEW | NORMAL | `NOT_YET_SHARED` |

The validity decides first: a NEW, INVALID opportunity is HIGH,
`VALIDITY_INVALID`.

**The page:**
- `kind` is `OPPORTUNITY`; `created_at` is the opportunity's own;
- the extra item keys are `request_id`, `property_id`, `status` and
  `validity_status` (`QueueItem` is open);
- the order is priority, then `created_at`, then `opportunity_id` (§2, I3);
- the whole queue is returned, `next_cursor` null, as the Slice 3 queues;
- staff only (ADMIN, OPERATOR, REVIEWER); audited once with its count, not
  its ids (R6.3c).

### 1.6 B10: the service guard on `current_offer_id` (G5-12)

The three proofs the plan asks for:
1. **Static.** A test parses every Python source under `src/` and extracts
   each `UPDATE turab.opportunities … WHERE` statement from its SQL strings.
   It requires:
   - the only file is `opportunity_commands.py`;
   - there are exactly three statements;
   - none names `current_offer_id`.

   A new writer, or a fourth statement, fails it.
2. **Over HTTP.** Two ACTIVE SALE offers on one property. The first offer's
   match is approved, then that offer is WITHDRAWN:
   - revalidate gives INVALID (`OFFER_STATUS`, `WITHDRAWN`) and keeps the
     first offer;
   - share is refused (the recorded validity is INVALID);
   - close succeeds.

   `current_offer_id` stays the first offer throughout.
3. **Mutation.** R7 injects into revalidate an update of `current_offer_id`
   to another ACTIVE offer of the property. It must fail proof 2 (§7).

### 1.7 The new problem codes

| code | status | when |
|---|---|---|
| `OPPORTUNITY_CLOSED` | 409 | any command on a CLOSED opportunity |
| `OPPORTUNITY_NOT_VALID` | 409 | share: recorded validity, or the check now (permission aside) |
| `SHARING_SCOPE_NARROWED` | 409 | share: the offer's scope is now narrower |
| `CONTACT_BEFORE_SHARING_REQUIRED` | 409 | share, PROVISIONAL (G5-8 (iii)) |
| `CLOSE_REASON_NOT_ALLOWED` | 422 | close: a reason outside the eight |

`CONSENT_REVOKED` (409) already existed.

## 2. PROVISIONAL choices and interpretations to confirm

### 2.1 The two open points of G5-8, implemented PROVISIONALLY

*[Decided since, in the review of `6c6e614`: (i) and (iii) as (a). (i) is
implemented as decided (§13.5); P1 below no longer describes the code.]*

**P1 — G5-8 (i), where the share's `channel` and `note` are kept.**
- **The choice: stored nowhere.** Both are accepted as the contract types
  them: `channel` is one of WHATSAPP, SMS, EMAIL, WEB; `note` is a string;
  an explicit null is refused.
- **Why this option.** Option (a) writes an `interactions` row, a Slice 7
  table, and needs its approval. Writing the free-text note into the audit
  context would carry free text, which can hold contact data (the lesson of
  `d0e0bc9`), into the audit log.
- **The cost:** the channel and the note are lost. The tests assert that no
  interaction is written, and that the note appears in no row and no audit
  row.
- **On decision (a),** one INSERT is added to `share()`.

**P2 — G5-8 (iii), `CONTACT_BEFORE_SHARING`.**
- **The choice:** the plan's recommended option (a). A CURRENT binding with
  this purpose, on the offer or its property, refuses the share with 409
  `CONTACT_BEFORE_SHARING_REQUIRED`. A revoked one does not.
- **Why this option.** It fails closed. Ignoring it, option (b), would make
  an opportunity visible to the buyer, by G5-7 (a), while the owner's
  consent asks for contact first.
- **On decision (b),** step 5 of `prepare_share` and its one test are
  removed.

**P3 — G5-8 (ii), the buyer side.** As proposed: no buyer-side consent
check, and no invented scope.

### 2.2 Interpretations the plan left open

1. **I1 — The reasons in the revalidate response.** G5-9: "the result's
   reasons name the failing checks, by code, in the response; there is no
   column for them".
   - The `InternalOpportunityView` is open (no `additionalProperties:
     false`), so the response carries one more key, `validity_reasons`.
   - The internal read (`GET /opportunities/{id}`) does not carry it: it is
     not stored.
2. **I2 — `CLOSE_REASON_NOT_ALLOWED`, 422.** The plan named no code for a
   reason outside the eight. It is a typed input refusal, as
   `REVIEW_REASON_NOT_ALLOWED` is for the review.
3. **I3 — The opportunity queue's order.** G5-11 gives the match queue's
   order, but not the opportunity queue's. It is priority, then
   `created_at`, then `opportunity_id`: the match queue's rule, on the
   opportunity's own time. The vocabulary is G5-11 (a)'s proposal, put for
   confirmation as the match queue's was.
4. **I4 — Bodies.** Revalidate and share have inline bodies with no
   `additionalProperties: false`, so they stay open, as the matching run's
   does (review of `bf052f4`). An undeclared field is accepted and counts
   for idempotency. `CloseCommand` is closed in the contract.
5. **I5 — A share of an ENGAGED opportunity** keeps ENGAGED and moves
   `last_activity_at` ("a later share keeps the status"). No Slice 5 path
   reaches ENGAGED.
6. **I6 — Permission FAIL with other failing facts** answers
   `CONSENT_REVOKED`. The code follows the permission; `field_errors` names
   every fact.
7. **I7 — The order of the share's checks:** recorded validity → check now
   → scope → contact-first. A recorded NEEDS_CONFIRMATION is refused even
   when the facts now pass. That is G5-8 item 2: the remedy is revalidate.
8. **I8 — The instants.**
   - Revalidate's and share's writes take the check's own instant, read
     after the locks (§3.7).
   - Close reads `clock_timestamp()` in its UPDATE.

### 2.3 Locks, and why no new deadlock cycle

*[Superseded by §13.4 after the review of `6c6e614`: the share now takes the
property and the offer `FOR UPDATE`.]*

**The lock order of each command:**

| command | locks, in order |
|---|---|
| revalidate, share | the opportunity (`FOR UPDATE`), then the check's locks: request, property and offer, bindings and grants |
| approval | the match, then the same check's locks |
| close | the opportunity only |

**Why no cycle.** No path locks an opportunity after the check's locks:
- the approval's INSERT does not wait on an existing opportunity row, since
  its open-opportunity read takes no lock;
- the unique index makes the INSERT wait only on an in-progress
  transaction that holds an index entry of the same open pair. Revalidate
  and share never change the indexed columns or the status that decides
  membership: share's NEW → SHARED keeps the row in the index.

This is reasoned, and tested only for close against a holder of the
opportunity (§3).

## 3. Tests (68 cases, `tests/test_slice5_step5.py`)

**Revalidate (G5-9, §3.7):**
- right after approval: VALID, no change of validity, only the two times
  move, and the response is the open view plus the reasons;
- **with the clock pinned:** approval and revalidate at one instant T agree
  (VALID, the same facts). At T + 400 days the three freshness facts are
  STALE. This is §3.7's "approval accepted ⇔ revalidate immediately VALID";
- forced check: what is stored is exactly what `currency.check` returns,
  for each class and back. With step 3's forced-check test and the
  exhaustive table test, this covers the plan's "for the same combinations";
- a fact changed after creation (six cases, among them the plan's PAUSED
  offer → NEEDS_CONFIRMATION and UNAVAILABLE property → INVALID): the
  validity stored, the reasons in the response, the confirmation time
  unmoved, and no snapshot, scope or offer changed;
- not monotonic; the current binding, and null once revoked; audited once
  with the actor.

**Share (G5-8; H05; B03):**
- NEW → SHARED once; a later share moves activity only; nothing else is
  written; no interaction; the customer reads it only after;
- **B03/H05:** a revocation, then a refused share with nothing changed
  (row, audit high-water mark, key, interactions); then revalidate records
  INVALID, and the next share is refused on the record;
- a recorded NEEDS_CONFIRMATION is refused until revalidate records VALID;
- the facts now not VALID (three cases); permission FAIL with another
  failing fact; a narrowed scope refused, a wider one not;
- PROVISIONAL: contact-before-sharing;
- a refused share consumes no key, and the same key is evaluated afresh; a
  replay, and IDEMPOTENCY_KEY_CONFLICT on another body;
- the body typed as the contract types it (four cases); the open body, and
  nothing of channel or note stored.

**Close (G5-10):**
- each of the eight from NEW;
- from SHARED, and from ENGAGED (SQL fixture), with the stamps kept;
- an INVALID opportunity closes;
- eight refused bodies;
- the eight pinned to the seed;
- CLOSED final for each command (three cases);
- a close replay;
- **mandatory test 6 through the real close;** the closed opportunity's
  match yields no second opportunity (the accepted consequence);
- a close waits on a transaction holding the opportunity (witness:
  `pg_blocking_pids`), then reads its committed CLOSED: 409, not a second
  close.

**Who may act:**
- an unknown opportunity is 403 and recorded, for each command;
- the contract's roles for each command: a customer, the request's own
  party included, is refused and nothing is written.

**B10:** the static test and the HTTP test (§1.6).

**The queue:**
- the three cases and their vocabulary, with the shared, closed, and
  closed-INVALID opportunities absent;
- a NEW INVALID opportunity is HIGH;
- no time-based membership;
- the order;
- staff only, audited once with its count.

## 4. Before the change (measured)

`evidence/SLICE5-STEP5-BEFORE-FIX.txt`.
- **Where:** at `fc450f0` (step 4 CLOSED), in an isolated worktree, with
  the step-5 test file (sha256 `1d7d269d…26c5a1`).
- **Result: 68 failed, 0 passed.**
- **The causes:**
  - the three commands and the queue are not routed: the generic 404
    NOT_FOUND of an unknown path;
  - the service module does not exist;
  - no source file UPDATEs `opportunities`;
  - no command exists to wait on the lock.

**The code was written before this record, as in steps 2–4.**

## 5. Existing tests

None changed. The full suite, run after the change and before the commit,
was 2310 passed: the 2242 of step 4 and the 68 of step 5.

## 6. Documents

**`docs/gate/SLICE_5_PLAN.md`, revision 15:**
- records step 5 as delivered;
- marks G5-8 (i) and (iii) as implemented PROVISIONALLY, pending a
  decision;
- records the interpretations of §2.2 at their decisions.

RFC-001, Appendix B, the design ledger and the contract are unchanged.

## 7. Mutation evidence

`db/dev/mutate_slice5_step5.py`: 31 mutations, each weakening ONE rule.
- **R1–R7:** revalidate. R7 is B10's proof 3;
- **S1–S10:** share. S6 and S7 are G5-8 (iii), PROVISIONAL;
- **C1–C4:** close;
- **L1–L2:** the lock, and the recorded unknown id;
- **Q1–Q8:** the opportunity queue.

**Before the run,** a script checked every mutated text: each anchor
matches exactly once, each mutation changes the file, and each mutated file
compiles. The runner itself checks only the first two.

**The record:** `evidence/SLICE5-STEP5-MUTATIONS.txt`.
- **Run:** at `93c7b37`, on a clean tree, source fingerprint
  `c93a8f86…f32d`.
- **Result: 31 of 31 fail, none survives.** The baseline is 68 passed.
- **Restoration:** every mutated file was restored, and verified by sha256.

**What each critical mutation is killed by:**

| mutation | killed by |
|---|---|
| **R7** (revalidate switches the offer) | both B10 tests: the static one, which finds `current_offer_id` in the UPDATE, and the HTTP one, which finds another offer stored |
| **S1** (the recorded validity ignored) | the NEEDS_CONFIRMATION test, and the B03/H05 test |
| **S2** (the check now ignored) | six tests |
| **S8** (share persists the check) | `test_share_writes_no_validity_binding_or_confirmation` |
| **C4** (CLOSED not final) | the three closed-is-final cases, the replay and the lock-witness test |
| **L1** (no lock) | the lock-witness test |

**About L1.** Without the lock, the waiting close is not a typed 409. Its
UPDATE waits on the row and then hits rule 1 of `0006`, which raises an
untyped server error. The test fails because no response arrives
(`KeyError: 'r'`). So the database still refuses the second close; what
the lock adds is the typed answer read after the commit.

## 8. The evidence round

Each row ran on a clean tree, source fingerprint `c93a8f86…f32d`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Before the change | 68 failed, 0 passed, at `fc450f0` | `93c7b37` | §4 |
| Mutations | 31/31 fail | `93c7b37` → `ab2ea1c` | §7 |
| Authorization matrix | **175 rules**, all PASS (seven new for step 5); suite 2312/2312 | `af47f26` | `AUTHORIZATION_EVIDENCE_MATRIX.md`; `--check --no-run`: current |
| PostgreSQL gate | PASS; 70 database-level PASS notices, 0 FAIL; 67 operations in parity | `10fc3c4` (run at `af47f26`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **2312 passed**, 0 failed, 0 errors, 0 skipped | `a1cf19f` (run at `10fc3c4`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |

**The suite count.** 2242 at step 4's closure. Then:
- +68 for `tests/test_slice5_step5.py`;
- +2 for `test_mutation_tools.py`'s import-safety tests of the new
  mutation script.

**On "67 operations in parity".** The gate compares the effective contract,
the inventory and the policy table: 67 operations, unchanged. The four
operations step 5 routes were already declared in the frozen contract and
in the policy table. Step 5 adds routes, not operations.

**STOP GATE D is not regenerated.** Its `--check` reports the same three
problems as after steps 3 and 4: the writers of `match_reviews` and
`opportunities`, and staleness. Nothing new: step 5 adds no INSERT
writer.

## 9. Limits that are part of these results

- **ENGAGED is an SQL fixture** (SHARED → ENGAGED with its stamp): no
  Slice 5 path reaches it (G5-1).
- **Facts changed after creation are SQL fixtures,** as an operator's
  correction would land.
- **The deadlock analysis of §2.3 is reasoned.** One lock interaction is
  tested.
- **The queue is not paged.**
- **Carried, unchanged:**
  - L-S5-3a and L-S5-3b (step 6 or the final closure; step 5 does not touch
    supersession);
  - K06 UNPROVEN (EN-02);
  - G4-5R open: STOP GATE E is SALE only.
- **STOP GATE D is not regenerated in Slice 5.** Its stale `--check` is
  neither a pass nor a failure.
- **These results are ours.** No independent run exists.

## 10. What remains

- **Decisions:** G5-8 (i) and (iii); the interpretations of §2.2.
- **Step 6:**
  - the mandatory and red-team tests, STOP GATE E and E04;
  - L-S5-3a and L-S5-3b: settle each by test, by documented consistency
    model, or by synchronization;
  - K06 listed UNPROVEN.

## 13. The review of `6c6e614`: R-S5-5-01, and G5-8 (i) and (iii) decided

### 13.1 What the review checked itself, and what it decided

**Checked by the reviewer:**
- the bundle's SHA-256 (`2495decb…4068`) and its 380 manifest entries;
- the source fingerprint `c93a8f86…f32d`, recomputed;
- `bound`.

The PostgreSQL, suite and mutation results remain ours, bound to the tree.

**Not closed: one blocker, R-S5-5-01.** It was inferred from the code and
the lock rules, and not measured by the reviewer:
- `currency._lock` held the property and the offer `FOR SHARE`;
- `FOR SHARE` does not conflict with the `FOR KEY SHARE` that the binding
  INSERT's foreign-key check takes;
- a lock on existing rows does not cover a binding that does not exist yet.

So a CURRENT `CONTACT_BEFORE_SHARING` binding could be inserted after the
share's negative check, and before its commit.

**Decided:**
- **G5-8 (i): option (a).**
  - One `interactions` row, STATUS_CHANGE, written on a successful share in
    the share's own transaction. It keeps the channel, the note, the actor
    and the opportunity.
  - It is not proof that a message was sent or a contact made.
  - The free-text note goes neither to the audit log nor to the customer's
    response.
  - A replay creates no second row, and a refusal creates none.
- **G5-8 (iii): option (a).** A CURRENT `CONTACT_BEFORE_SHARING` binding
  refuses the share with a typed refusal, until a path records the
  contact. Approving the rule does not make the implementation immune to
  the window.
- **I1–I8 accepted** within their scope. I4 is amended by the decision on
  `channel` and `note` (§13.5).

**Still in force:**
- step 6 is not authorized until this correction is reviewed;
- L-S5-3a, L-S5-3b, K06 and G4-5R keep their stated limits.

### 13.2 R-S5-5-01, measured before the fix

`evidence/SLICE5-STEP5-R-S5-5-01-BEFORE-FIX.txt`:
- **at `6c6e614`**, in an isolated worktree;
- with the review's tests added to `tests/test_slice5_step5.py`, and no
  source file changed.

**The tests the review asked for.** Each runs over HTTP, through:
- the real share command;
- the real binding command (`POST /consents/bindings`, purpose
  `CONTACT_BEFORE_SHARING`, as an OPERATOR).

Each command runs in its own transaction, and the witness is
`pg_stat_activity` with `pg_blocking_pids`. Both binding targets are tried:
the offer (`PROPERTY_OFFER`) and the property (`PROPERTY`).

**Order A.** The share is held after its contact check and before its
UPDATE. The binding is then created in another transaction.

**Order B.** The binding is inserted and held before its commit. The share
then runs.

| order | target | measured at `6c6e614` |
|---|---|---|
| A | offer | **the binding did not wait.** It committed while the share was held; the share then committed SHARED over a CURRENT CONTACT_BEFORE_SHARING binding |
| A | property | the same |
| B | offer | **the share did not wait.** It did not see the uncommitted binding, committed SHARED and consumed its key; the binding then committed |
| B | property | the same |

**The window is confirmed in PostgreSQL**, in both orders and on both
targets, as the review inferred.

### 13.3 The fix

**The share alone takes the property and the offer `FOR UPDATE`**
(`currency.check(..., exclusive=True)` from `prepare_share`). The other
users of the check keep `FOR SHARE`.

**Why `FOR UPDATE`, and not another mode.**
- A new binding's INSERT checks `fk_consent_binding_offer` or
  `fk_consent_binding_property` with `FOR KEY SHARE` on the referenced row.
- Of the four row-lock modes, **only `FOR UPDATE` conflicts with
  `FOR KEY SHARE`** (PostgreSQL 16 documentation, §13.3.2, Table 13.3
  "Conflicting Row-Level Locks").
- Mutation **W2** replaces it with `FOR NO KEY UPDATE`, which is stronger
  than `FOR SHARE` but does not conflict with `FOR KEY SHARE`. W2 is killed
  by the window tests (§13.7).

**What it gives, in each order:**
- **Order A:** the binding's foreign-key check waits on the share. It
  commits after the share has committed, so the share was right at its
  commit.
- **Order B:** the share waits on the binding at the offer or the property.
  Once the binding commits, the share's next statements read the facts
  again. Each statement under Read Committed takes a new snapshot
  (PostgreSQL 16, §13.2.1), and the check reads every fact after its locks.
  The binding is seen, and the share is refused with 409
  `CONTACT_BEFORE_SHARING_REQUIRED`:
  - it writes nothing: no row, no audit row, no interaction;
  - it consumes no key, since the refusal comes before the claim.

**Why the remedy is at the row and not in the binding command.**
- The foreign-key check binds any writer of `resource_consent_bindings`,
  through the API or not.
- No migration is needed, and none is added.
- An advisory lock in `consent.bind_consent` would bind the service only.

### 13.4 The effect of the stronger lock on its ordering (as the review asked)

**The share's order:** the opportunity, then the request (`FOR NO KEY
UPDATE`), then the property, then the offer (both `FOR UPDATE`), then the
existing bindings and grants (`FOR SHARE`). It is the approval's order, with
two locks made stronger. A cycle would need a transaction that holds the
offer and then waits on the property, or one that holds what the share
locked first.

| neighbour | its order | effect, tested |
|---|---|---|
| **approval** (another request, same property) | match → request → property `FOR SHARE` → offer `FOR SHARE` | waits on the share at the property; then creates its opportunity. `test_an_approval_on_the_same_property_waits_for_a_held_share_and_both_succeed` |
| **a second share** (another opportunity, same property) | opportunity → request → property `FOR UPDATE` → offer | waits at the property; then succeeds. `test_two_shares_on_one_property_serialize_and_both_succeed` |
| **revalidate** | opportunity → request → property `FOR SHARE` → offer `FOR SHARE` | the same order as the approval; it serializes with a share at the property |
| **the matching run** (REPEATABLE READ) | the foreign keys of each `match_candidates` row: request → property → offer | waits on the share at the property; then completes 201, with no deadlock and no serialization failure. `test_a_matching_run_on_the_property_waits_for_a_held_share_and_completes` |
| **a binding INSERT** | one foreign key, on the offer or the property | serialized: §13.3 |
| **offer writers** (`services/offers.py`) | the offer `FOR UPDATE`, then provenance rows that name the offer only (`num_nonnulls(...) = 1`) | never wait on a property after holding an offer |
| **property writers, identity review, truth layer** | one property (or two, ordered by id), then rows that name that property only | never hold an offer |

**Measured for the run's order.**
- The run's foreign-key triggers on `match_candidates` are
  `RI_ConstraintTrigger_c_…`, in the order request, property, offer (read
  from `pg_trigger` on the suite's database).
- PostgreSQL fires the triggers of one event "in alphabetical order by trigger
  name" (documentation of `CREATE TRIGGER`).
- So a run blocked at a property holds no lock on that property's offers
  for that row, and an offer belongs to one property.

**The cost, stated.**
- A share now waits for any open transaction that holds a key lock on its
  property or offer: a matching run that already inserted a match on the
  property, an approval, or another share. The longest is a matching run.
- An approval and a revalidate on that property wait for the share. A share
  is short: a few reads and two writes.

**Not changed:**
- revalidate and the approval keep `FOR SHARE`: neither depends on the
  absence of a binding;
- an inserted binding cannot lower the permission gate, since `PASS` needs
  one CURRENT binding and a revocation is an UPDATE of a row already
  locked.

### 13.5 G5-8 (i), implemented as decided

**One `interactions` row per successful share**, written in its transaction
after the opportunity's UPDATE:

| column | value |
|---|---|
| `interaction_type` | `STATUS_CHANGE` |
| `channel` | the body's channel (WHATSAPP, SMS, EMAIL, WEB, all values of `communication_channel`), or null |
| `summary` | the body's note, or null |
| `party_id` | the request's party |
| `opportunity_id` | the opportunity |
| `operator_account_id` | the actor |
| `occurred_at` | the share's instant (`shared_at` on the first share) |
| `thread_id`, `outcome_code` | null |
| `metadata` | `source_operation` (`postOpportunitiesOpportunityIdShare`), `status_before`, `status_after` |

**Not proof of a message or a contact.**
- No thread is linked, no message is sent, and no check reads the row as a
  contact.
- `test_g5_8_iii_an_interaction_recorded_by_a_share_is_not_a_recorded_contact`:
  after a share, a CURRENT `CONTACT_BEFORE_SHARING` binding still refuses
  the next one.

**The note stays out of the audit log and the responses.**
- `interactions` has no audit trigger. The command layer writes the audit
  row the trigger would have written (`audit_rows`), **less `summary`**
  (`audit_rows.WITHHELD`), by the decision.
- This is the one departure from `audit_rows`' rule ("the same columns"),
  and it is named there.
- The note is in no response: not the share's, which is the
  `InternalOpportunityView` and has no note field, and not the customer's.

**A replay and a refusal.**
- A replay returns the stored response without running the handler, so it
  writes no second row.
- A refusal comes before the claim and the handler, so it writes none.

**Each successful share is recorded, the later ones included.** A later
share keeps the status (I5) and still carries its own channel and note.
Recording only the first would drop them, which the decision refused.
`status_before` and `status_after` say which share it was.

**I4, amended.** The bodies of revalidate and share stay open, as the
contract leaves them. The share's `channel` and `note` are now kept in the
interaction.

*[Decided since, in the review of `1f8a8df`, and done: §14.]*
**Put to the reviewer: the `note` of revalidate and close.**
- G5-10 wrote "the note follows G5-8 (i)", but the decision names the
  share.
- Both notes are still accepted and stored nowhere. A close is a status
  change too: the same row, of type STATUS_CHANGE, would carry it.
- I have not extended the decision on my own.

### 13.6 G5-8 (iii)

The rule is unchanged, and now serialized (§13.3). The PROVISIONAL marks
are removed from the code, the tests, the matrix and the problem catalogue.

### 13.7 Mutations

**Step 5:** `db/dev/mutate_slice5_step5.py` has 42 mutations: the 31 of §7,
S6 and S7 renamed, and eleven new ones:
- **W1** the share takes the shared lock;
- **W2** `FOR NO KEY UPDATE` instead of `FOR UPDATE`;
- **W3** the property not locked exclusively;
- **W4** the offer not locked exclusively;
- **I1** no interaction;
- **I2** the note not kept;
- **I3** the channel not kept;
- **I4** the operator not kept;
- **I5** the audit row carries the note;
- **I6** the interaction not audited;
- **I7** the status before not recorded.

**The record:** `evidence/SLICE5-STEP5-MUTATIONS-AFTER-R-S5-5-01.txt`.
- **Run:** at `0a5c446`, on a clean tree, source fingerprint
  `c7a5e436…8d632f`.
- **Result: 42 of 42 fail, none survives.** The baseline is 81 passed.
- **Restoration:** every mutated file was restored, and verified by sha256.
- **Before the run,** a script checked each anchor (exactly one site), that
  each mutation changes its file, and that each mutated file compiles.

**What kills each new mutation:**

| mutation | killed by |
|---|---|
| **W1** (the shared lock) | the four window cases, plus the run, approval and two-share tests (7 failed) |
| **W2** (`FOR NO KEY UPDATE`) | the four window cases and the run test (5 failed) |
| **W3** (property not exclusive) | the two PROPERTY window cases |
| **W4** (offer not exclusive) | the two PROPERTY_OFFER window cases |
| **I1–I7** | each by its own interaction test: 6, 3, 3, 1, 1, 1 and 2 failures |

**About W2.** The approval and two-share tests do not kill it, because
`FOR NO KEY UPDATE` already conflicts with `FOR SHARE` and with itself.
Only the binding's and the run's foreign-key `FOR KEY SHARE` tell it apart
from `FOR UPDATE`. That is the reason for the mode chosen in §13.3.

**Step 3:** mutations L3 and L4 of `db/dev/mutate_slice5_step3.py` anchored
on the text `FOR SHARE"""` that the refactor replaced. They now remove the
lock in either mode, the same weakening. They were run again alone.

**The record:** `evidence/SLICE5-STEP3-MUTATIONS-L3-L4-AFTER-LOCK-MODE.txt`,
at `0a5c446`, on a clean tree.
- **Result: 2 of 2 fail**, each killed by its original test,
  `test_a_fact_being_changed_is_waited_for_and_read_after_its_commit`
  (`property-…` and `offer-…`).
- **Baseline:** 57 passed.

### 13.8 The evidence after the fix

Each row ran on a clean tree, source fingerprint `c7a5e436…8d632f`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Before the fix | at `6c6e614`: the window confirmed in both orders on both targets; 13 failed, 67 passed | `0a5c446` | `evidence/SLICE5-STEP5-R-S5-5-01-BEFORE-FIX.txt` |
| The fix | `currency.py`, `opportunity_commands.py`, `audit_rows.py`, the share route | `0a5c446` | §13.3, §13.5 |
| Mutations | step 5: 42/42 fail; step 3 L3/L4: 2/2 fail | `0a5c446` → `f3dd4c3` | §13.7 |
| Authorization matrix | **177 rules**, all PASS (two new: R-S5-5-01 and G5-8 (i); G5-8 (iii) renamed); suite 2325/2325 | `04095e3` | `AUTHORIZATION_EVIDENCE_MATRIX.md`; `--check --no-run`: current |
| PostgreSQL gate | PASS; 70 database-level PASS notices, 0 FAIL; 67 operations in parity | `a7648b9` (run at `04095e3`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **2325 passed**, 0 failed, 0 errors, 0 skipped | `b3f4d9f` (run at `a7648b9`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |

**The suite count:** 2312 at `6c6e614`, then +13 in
`tests/test_slice5_step5.py`:
- the four window cases;
- the three neighbour tests;
- six for G5-8 (i);
- one for G5-8 (iii) and the interaction;

less the one test it replaces
(`test_the_share_body_is_open_and_carries_nothing_stored`, now
`test_g5_8_i_the_note_is_kept_in_the_interaction_only`). That is 81 in the
file.

**Repetition.** Before the commit, the eight lock and witness tests passed
10 runs out of 10.

**STOP GATE D is not regenerated.** Its `--check` reports the same three
problems as after steps 3 and 4. Step 5 adds no INSERT into
`match_reviews` or `opportunities`.

### 13.9 Limits

- **`bound_at` is the binding transaction's start** (`now()`, the frozen
  default). A binding command whose transaction started before a share, and
  whose INSERT then waited on it, commits after the share with a `bound_at`
  earlier than `shared_at`. The serialization is by commit; the stamp
  records when the binding's transaction began. This changes nothing that
  the share decided.
- **The cost of §13.4:** a share can wait for a matching run on its
  property.
- **The trigger-order argument holds on this schema's names.** It rests on
  the `pg_trigger` names read here (equal-length OIDs), and the run test
  exercises it. A rebuilt database with OIDs of different lengths would
  need the read again.
- **Carried, unchanged:**
  - L-S5-3a and L-S5-3b;
  - K06 UNPROVEN;
  - G4-5R open: STOP GATE E is SALE only;
  - STOP GATE D is not regenerated in Slice 5.
- **These results are ours.** No independent run exists.
- **Step 6 is not authorized.**

## 14. The review of `1f8a8df`: the note of close and revalidate

### 14.1 What the review accepted, and what it left open

**Checked by the reviewer:**
- the archive's digest, its 384 manifest entries, and `bound` inside the
  extracted tree;
- the command path and the two window tests: the share locks the property
  and the offer `FOR UPDATE` before it reads the bindings again, and the
  tests separate the two orders of the race, on the offer and on the
  property;
- the interaction row written in the share's transaction, with `summary`
  left out of the audit.

PostgreSQL, the suite and the mutations were not re-run by the reviewer.
The 2325 tests, the 42 mutations and the gate stay our results.

**Accepted:**
- the remedy of R-S5-5-01;
- G5-8 (i) and (iii) as implemented.

**Not closed: one place.** Two commands accepted a `note` and dropped it.

**Decided:**
- **Close.** G5-10's "the note follows G5-8 (i)" covers it. Each
  successful close writes one STATUS_CHANGE `interactions` row with:
  - the actor, the opportunity and the request's party;
  - the reason, and the source operation;
  - the note, which stays out of the audit log and the responses.
- **Revalidate.** A note, when given, is kept in one NOTE `interactions`
  row, with the source operation, the actor, the opportunity and the
  request's party. With no note, no row. The row is no evidence of a
  contact.
- **In both,** the write is atomic with the command: no row on a refusal,
  and none on a replay with the same key.
- **The order asked for:**
  1. measure the drop on the current code with two HTTP tests;
  2. then pin the keeping, the absence of leaks and the replay with
     dedicated tests and mutations.

**Until this is reviewed:** step 5 and Slice 5 stay open, and step 6 is not
authorized. L-S5-3a, L-S5-3b, K06 and G4-5R keep their stated limits.

### 14.2 The drop, measured before the change

`evidence/SLICE5-STEP5-NOTES-BEFORE-FIX.txt`:
- **at `1f8a8df`**, in an isolated worktree;
- with the new tests added, and no source file changed.

**What the two HTTP tests show:**
- **Close.** `POST /opportunities/{id}/close` with `reason_code` and a note
  answered **200**, and the opportunity is CLOSED. Afterwards **no
  `interactions` row** exists for it, and the note is nowhere.
- **Revalidate.** `POST /opportunities/{id}/revalidate` with a note, on an
  UNAVAILABLE property, answered **200** and recorded INVALID. Again **no
  row**.

**The result: 6 failed, 83 passed.**
- All six failures are the missing rows.
- The two tests that hold already are kept as regression guards: no row
  for a revalidate without a note, and a note that is not a recorded
  contact.

### 14.3 The change (`37701ce`)

**One writer, `_record`,** used by the share, the close and the revalidate.
It writes one `interactions` row in the command's transaction, after the
command's UPDATE:
- the request's party, the opportunity and the operator;
- the note as `summary`, and no thread;
- `metadata` with the source operation.

The audit row is the row less `summary` (`audit_rows.WITHHELD`, unchanged
since §13.5). A test pins one INSERT into `interactions` in one module.

| command | when | `interaction_type` | `outcome_code` | `occurred_at` | `metadata` |
|---|---|---|---|---|---|
| share | each success | STATUS_CHANGE | null | the share's instant | `source_operation`, `status_before`, `status_after` |
| **close** | **each success, note or not** | **STATUS_CHANGE** | **the close reason** | **`closed_at`** | `source_operation`, `status_before`, `status_after` |
| **revalidate** | **only when a note is given** | **NOTE** | null | the check's instant (= `last_activity_at`) | `source_operation`, `validity_before`, `validity_after` |

**Two notes on the choices made:**
- **The close reason goes into `outcome_code`.** That is the column of the
  frozen schema that references `reason_codes`, and the eight close reasons
  are seeded codes.
- **"Given" means present in the body.** An absent field is no note. An
  explicit null is refused 422, as before. An empty string is a given
  note, and is kept.

**Atomicity.**
- A refusal is decided in `prepare`, before the claim and the handler, so
  it writes no row.
- A replay with the same key returns the stored response without running
  the handler, so it writes no second row.
- The tests check both, for close and for revalidate.

**No leak.** The tests check that the note is in none of these:
- the command's response;
- the opportunity row;
- the audit log.

### 14.4 Tests: 8 new, 89 in the file

**Close:**
- the note kept, with the reason, the actor, the party, `closed_at`, the
  source operation and the statuses;
- without a note, the row is still written;
- from SHARED, its own `status_before`, after the share's row;
- a 422 refusal, a replay, and a 409 on a closed opportunity write no row.

**Revalidate:**
- the note kept, with the validity before and after;
- without a note, or with only an undeclared field, no row;
- a replay and a 409 on a closed opportunity write no row;
- a revalidate note is not a recorded contact: a CURRENT
  CONTACT_BEFORE_SHARING binding still refuses the share.

**The writer test** now pins one module and one INSERT.

### 14.5 Mutations

`db/dev/mutate_slice5_step5.py`: **51 mutations.**
- **I1–I7** follow the one writer: I1 and I7 act on the share's call, I2–I6
  on the writer every command uses.
- **N1–N9 are new:**
  - **N1** the close writes no row;
  - **N2** the close note is not kept;
  - **N3** the close reason is not recorded;
  - **N4** the close records the share's source;
  - **N5** the revalidate note is not kept;
  - **N6** a revalidate without a note writes a row;
  - **N7** the revalidate note is typed STATUS_CHANGE;
  - **N8** the validity before is not recorded;
  - **N9** the revalidate writes no row.

**The record:** `evidence/SLICE5-STEP5-MUTATIONS-AFTER-NOTES.txt`.
- **Run:** at `37701ce`, on a clean tree, source fingerprint
  `48b42ec4…c9f5f`.
- **Result: 51 of 51 fail, none survives.** The baseline is 89 passed.
- **Restoration:** every mutated file was restored, and verified by sha256.
- **Before the run,** a script checked each anchor (exactly one site), that
  each mutation changes its file, and that each mutated file compiles.

**What kills each of N1–N9:**

| mutation | failed | killed by |
|---|---|---|
| N1 | 4 | the four close tests |
| N2 | 2 | the close note test, and the close-from-SHARED test |
| N3 | 3 | the close tests that read `outcome_code` |
| N4 | 2 | the tests that read `source_operation` |
| N5 | 1 | the revalidate note test |
| N6 | 1 | `test_revalidate_without_a_note_writes_no_interaction` |
| N7 | 1 | the revalidate note test, which reads the type |
| N8 | 1 | the revalidate note test, which reads `validity_before` |
| N9 | 2 | the revalidate note test, and the revalidate replay test |

**No leak, per command.** I5 restores `summary` to the audit row, and it is
now killed by the share's, the close's and the revalidate's no-leak tests
(3 failed).

### 14.6 The evidence

Each row ran on a clean tree, source fingerprint `48b42ec4…c9f5f`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Before the change | at `1f8a8df`: both commands answer 200 and store the note nowhere; 6 failed, 83 passed | `37701ce` | `evidence/SLICE5-STEP5-NOTES-BEFORE-FIX.txt` |
| The change | `opportunity_commands.py` (`_record`, close, revalidate), the two routes | `37701ce` | §14.3 |
| Mutations | 51/51 fail | `37701ce` → `2b55e20` | §14.5 |
| Authorization matrix | **178 rules**, all PASS (one new); suite 2333/2333 | `3301208` | `AUTHORIZATION_EVIDENCE_MATRIX.md`; `--check --no-run`: current |
| PostgreSQL gate | PASS; 70 database-level PASS notices, 0 FAIL; 67 operations in parity | `ee48c4f` (run at `3301208`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **2333 passed**, 0 failed, 0 errors, 0 skipped | `30bccf5` (run at `ee48c4f`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |

**The suite count.** 2325 at `0a5c446`, plus the 8 tests of §14.4.

**STOP GATE D is not regenerated.** Its `--check` reports the same three
problems as before.

### 14.7 Limits

- **No interaction is written for a refused command.** The decision says
  so; an attempt is not a fact about the opportunity.
- **An empty string is kept as a note** (§14.3). The contract types `note`
  as a string, and nothing narrows it.
- **Carried, unchanged:**
  - L-S5-3a and L-S5-3b;
  - K06 UNPROVEN;
  - G4-5R open: STOP GATE E is SALE only;
  - STOP GATE D is not regenerated in Slice 5.
- **These results are ours.** No independent run exists.
- **Step 6 is not authorized.**

## 15. The review of `3a60b3b`: step 5 CLOSED

**Decision.** "أُغلق الخطوة 5 عند 3a60b3b ضمن نطاقها المعتمد، وأجيز بدء
الخطوة 6. تبقى Slice 5 مفتوحة."

**What the reviewer checked:**
- the bundle's SHA-256, matching the value delivered;
- its 385 manifest entries;
- `bound`, from `run_binding.py` in the extracted tree;
- in the code: the close writes a STATUS_CHANGE row with its reason and its
  note, and the revalidate writes a NOTE row only when a note is given.
  Both rows are written after the opportunity's UPDATE, in the command's
  transaction;
- in the HTTP tests: the refusal, the replay, and the absence of the note
  from the response and the audit log.

**What the review relies on.** This was a check of the bundle, the code and
the recorded evidence, not an independent run of PostgreSQL, the tests or
the mutations. 2333/2333, 51/51 and the gate remain the implementation
team's results.

**Accepted:** the two interpretations of §14.3:
- the close reason in `outcome_code`;
- an empty string kept as a note, and an explicit null refused.

**Carried to step 6, and binding on the closure of Slice 5:**
- **L-S5-3a and L-S5-3b** must each be settled explicitly before the
  slice closes: by proof, or by an accepted, documented limit;
- **K06** stays UNPROVEN;
- **G4-5R** stays open;
- **STOP GATE E** covers SALE only.
