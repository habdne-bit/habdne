# Slice 5 · step 5 — revalidate, share, close, the opportunity queue, and B10

**Authorized (review of `1556624`).** "الخطوة 5 مأذون ببدئها وفق القرارات
المعتمدة. الشريحة 5 ككل لم تُغلق بعد."

**Status:** **DELIVERED, submitted for review.** Not closed. Slice 5 as a
whole is not closed.

**Two points are PROVISIONAL.** G5-8 (i) and (iii) were put to the reviewer
in revision 2 and have no recorded decision. Each is implemented by the
narrower option, and isolated so that the decision changes one place (§2).

**Still open:**
- G4-5R (STOP GATE E is SALE only);
- K06 is UNPROVEN (G5-13 (b)(ii));
- L-S5-3a and L-S5-3b are carried to step 6 or the final closure (plan §8).

**Commits:**
- `93c7b37`: the code, the tests, the mutation script, the matrix rules, the
  before-fix record;
- `ab2ea1c`, `af47f26`, `10fc3c4`, `a1cf19f`: the evidence (§8);
- the commit that adds this note: the note and plan revision 15.

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
