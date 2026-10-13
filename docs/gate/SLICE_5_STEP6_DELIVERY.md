# Slice 5 · step 6 — the carried limits, the red-team cases, and STOP GATE E

**Authorized (review of `3a60b3b`).** "أُغلق الخطوة 5 عند 3a60b3b ضمن نطاقها
المعتمد، وأجيز بدء الخطوة 6. تبقى Slice 5 مفتوحة." The same review: L-S5-3a
and L-S5-3b must each be settled explicitly, by proof or by an accepted,
documented limit, before the slice closes. K06 stays UNPROVEN, G4-5R open,
and STOP GATE E covers SALE only.

**Status:** **DELIVERED, submitted for review.** Not closed. Slice 5 as a
whole is not closed; its closure record follows this review.

**What step 6 settles:**
- **L-S5-3a: PROVEN**, with no code change (§2);
- **L-S5-3b: measured, then CLOSED** by one lock in the approval (§3).

**One mutation survives:** C2, an equivalent mutant. It is stated in §7
and put to the reviewer.

**Commits:**
- `e9904c0`: the code, the tests, STOP GATE E's generator, the mutation
  script, the matrix rules, the before-fix record;
- `0183106`: step 3's L1/L2 rerun, and C2 added;
- `e63e693`, `cd5511f`, `975a448`, `82f7995`: the evidence (§8);
- the commit that adds this note: the note, STOP GATE E's generated
  document and plan revision 19.

---

## 1. What step 6 contains

| File | Role |
|---|---|
| `src/turab/services/match_review.py` | L-S5-3b: `_lock_request`, the approval's `FOR UPDATE` on the request, before the supersession check |
| `tests/test_slice5_step6.py` (new) | L-S5-3a, L-S5-3b, STOP GATE E's proof, E04, K05, the revalidate lock, K06's trigger-level refusals (15 cases) |
| `db/gate/stop_gate_e_evidence.py` (new) | STOP GATE E's generator, with `--check` |
| `tests/test_slice5_stop_gate_e.py` (new) | the generator's refusals, on a copy of the tree (17 cases) |
| `docs/gate/SLICE_5_STOP_GATE_E.md` (generated) | STOP GATE E, bound to the run |
| `db/dev/mutate_slice5_step6.py` (new) | 8 mutations (§7) |
| `db/gate/authorization_evidence.py` | five rules for step 6 |
| `tests/test_slice5_step3.py` | the concurrency test's witness widened (§3.5) |

**What did not change:**
- no migration and no contract change;
- Slice 4's run, engine, rules, pins and registry (acceptance condition 6);
- `docs/handoff/`.

## 2. L-S5-3a: supersession across two policies, PROVEN

**What was open (plan §8).** "Supersession across two policies is not
proven: no two-policy test, no mutation dropping `matching_policy_id`."

**The proof** is `test_l_s5_3a_a_later_match_under_another_policy_supersedes_nothing`.
1. Match A is a committed run under `0.2.0`.
2. In a later transaction, a second policy with `0.2.0`'s rules becomes
   active, and **the real run** evaluates the same request, property and
   offer under it. Match B is evaluated strictly later.
3. B supersedes nothing:
   - A stays in the match queue beside B;
   - the approval's `_superseded_by` finds nothing for A;
   - **the real approval** of A creates the opportunity.
4. The transaction is rolled back. `0.2.0` is the active policy again, and
   nothing remains.

**The control** is `test_l_s5_3a_a_later_match_under_the_same_policy_still_supersedes`:
a later committed run under the same policy supersedes, and the answer is
409 `MATCH_SUPERSEDED`.

**Why the second policy lives only in a rolled-back transaction.**
- `0005` makes `0.2.0` immutable, so a second policy is a new row.
- Once a match cites a policy, the policy can never be deleted, and
  matches are immutable.
- The suite pins the seed's one policy
  (`test_correction_004::test_the_frozen_default_names_no_policy_the_seed_creates`).
- So a committed second policy would stay in the shared test database for
  good.

**Can the proof fail?** Yes. Two mutations drop `matching_policy_id`, and
each is killed by the proof:
- **P1:** from the approval's supersession check;
- **P2:** from the match queue's.

**Measured before step 6 on the code as it was**
(`evidence/SLICE5-STEP6-L-S5-3-BEFORE-FIX.txt`): both tests pass. No
change was needed.

## 3. L-S5-3b: the window, measured, then closed

### 3.1 The measurement, before any change

`evidence/SLICE5-STEP6-L-S5-3-BEFORE-FIX.txt`, at `c9e676b`:
- over HTTP, with the real approval and the real run, each in its own
  transaction;
- one of them held at a fixed point;
- witness: `pg_blocking_pids`;
- a committed change of the offer's terms confirmation makes the run store
  a NEW match of the same offer (G4-13: identical facts return the same
  match).

**Order A.** The approval is held after its supersession check, before its
commit. The run is then sent.
- **Measured:** the run did not wait. It committed a newer match while the
  approval was held, and the approval then committed an opportunity from a
  match that a committed run had already superseded.
- **The window is confirmed.**

**Order B.** The run is held after storing its match, before its commit.
The approval is then sent.
- **Measured:** the approval did not wait, and it committed first.
- That order is serial: at the approval's commit, no newer match was
  committed. It is recorded because the remedy changes it.

**Why.** The run's foreign key on `match_candidates.request_id` locks the
request `FOR KEY SHARE`. The approval locked the request `FOR NO KEY
UPDATE`, which does not conflict with it, and only after its supersession
check.

### 3.2 The remedy

**`match_review._lock_request`:** the approval locks its request `FOR
UPDATE` immediately before the supersession check.

**Why `FOR UPDATE` and not another mode.** Of the row-lock modes, only
`FOR UPDATE` conflicts with `FOR KEY SHARE` (PostgreSQL 16, §13.3.2, Table
13.3). Mutation **R2** uses `FOR NO KEY UPDATE`, and is killed.

**Why before the check.** Mutation **R3** takes the lock after the check,
and is killed: in order A, the run then commits inside the window again.

**What the remedy gives:**
- **Order A:** the run waits on the approval and commits after it, so the
  opportunity's match was current when the approval committed;
- **Order B:** the approval waits on the run, reads again after the wait,
  and is refused 409 `MATCH_SUPERSEDED`. It writes no review, no
  opportunity and no audit row, and consumes no key.

Both orders are tests over HTTP with witnesses:
- `test_l_s5_3b_a_run_while_an_approval_is_held_waits_for_it`;
- `test_l_s5_3b_an_approval_waits_for_a_run_in_flight_and_is_refused_superseded`.

**Why the remedy is in the approval.** The run (Slice 4) is unchanged, and
acceptance condition 6 holds. Any writer of a match, through the API or
not, takes the foreign key's lock.

### 3.3 The lock order, with the remedy

| command | its locks, in order |
|---|---|
| approval | the match `FOR UPDATE` → **the request `FOR UPDATE`** → the property and the offer `FOR SHARE` → the bindings |
| share | the opportunity → the request `FOR NO KEY UPDATE` → the property and the offer `FOR UPDATE` → the bindings |
| revalidate | the opportunity → the request `FOR NO KEY UPDATE` → the property and the offer `FOR SHARE` → the bindings |
| run (Slice 4) | per match row, its foreign keys: the request, the property, the offer, `FOR KEY SHARE` (trigger order, step 5 §13.4) |

**Why no cycle.**
- Every path takes the request before the property, and the property
  before the offer.
- No path locks a match row except the review, which locks it first.
- No path locks an opportunity row after the request: the share, the
  revalidate and the close lock it first, and the approval inserts a new
  one.

**The cost:**
- during an approval, a new criterion of the request, a run inserting a
  match of the request, and any other foreign-key reference to the request
  wait until it commits;
- an approval waits for a run in flight on its request.

An approval is short: a few reads, the review row and the opportunity,
with their audit rows.

### 3.4 The currency check's own request lock

**The lock is still needed.** Revalidate and share take no approval lock.
`test_a_revalidate_waits_for_a_request_writer_and_reads_its_commit`: a
revalidate waits on an uncommitted change of the request's status, then
records it. Mutation **C1** removes the lock, and is killed.

**Its strength is no longer observable: C2.** C2 weakens the lock to
`FOR SHARE`, and survives. That is an **equivalent mutant**:
- `FOR SHARE` conflicts with a request writer's UPDATE just as
  `FOR NO KEY UPDATE` does;
- the only difference, serializing two checkers on one request, is now
  done for approvals by the approval's own `FOR UPDATE`;
- revalidates and shares on one request need no such serialization: they
  write different rows, and shares already serialize on the property.

The stronger mode is kept. Changing it would be a change with no
measurable effect. **Put to the reviewer:** accept C2 as equivalent, or
weaken the lock to `FOR SHARE` (the measured-sufficient mode).

**Step 3's own L1 and L2** remove and weaken the same lock. Both now
survive step 3's tests, because the approval's lock precedes it
(`evidence/SLICE5-STEP3-MUTATIONS-L1-L2-AFTER-L-S5-3B.txt`). L1 is killed
in step 6 by C1; L2 is C2.

### 3.5 Step 3's concurrency test, widened

`test_mandatory_6_two_concurrent_approvals_of_one_pair_make_one_opportunity`
selected its witness by the text of the waiting statement,
`FOR NO KEY UPDATE`.
- Approval B now waits at the earlier `FOR UPDATE` on the same row, so the
  test failed on its witness while the behaviour was unchanged.
- The witness now matches the request's locking read in either mode.
- What it proves is unchanged: B waits on A's request lock, then is
  refused.

## 4. The mandatory and red-team tests

**The six mandatory tests (plan §6.1)** are mapped by `module::name` in
STOP GATE E §2, all PASS. Tests 2 and 4 each include a schema refusal with
the service check bypassed, labelled as schema.

**The red-team cases (plan §6.2):**

| case | proof |
|---|---|
| B03, H05 | step 5's revocation test: the share is refused, nothing changes |
| H01–H04 | the mandatory tests 1, 2, 3, 6 |
| **E04** | **new, on real opportunities** (below) |
| **K05** | **new**: `test_k05_each_slice_5_post_replays_and_a_changed_body_is_409` (below) |
| K06 | **UNPROVEN** (below) |
| S33–S36a | step 4's tests on the real route (STOP GATE E §4) |

**E04.** `test_e04_consolidation_with_two_real_open_opportunities_surfaces_work_and_closes_none`.
- One request and two properties that are the same place, each with its
  own ACTIVE offer.
- Both are matched by the real run, and both matches are approved. That
  gives two open opportunities, which is allowed while they are two
  properties.
- The identity review then confirms them SAME.
- One RESOLVE_IDENTITY task names the alias's opportunity and lists the
  canonical's as the duplicate. Neither opportunity changes.
- Slice 3's E04 test made its opportunities by SQL, before Slice 5
  existed.

**K05.** For each of the six Slice 5 POSTs (REJECTED, NMI, APPROVED,
revalidate, share, close):
- the same key and body return the first response and write nothing more
  (counts of reviews, opportunities, tasks, interactions, and the audit
  high-water mark);
- another body on the key is 409 `IDEMPOTENCY_KEY_CONFLICT`.

**K06 stays UNPROVEN** (EN-02, G5-13 (b)(ii)).
`test_trigger_level_a_review_row_cannot_be_changed_or_deleted` is new. It
and step 1's `test_the_frozen_delete_guard_is_unchanged` are listed as
trigger-level, never as K06, in STOP GATE E §3 and in the matrix.

## 5. STOP GATE E (plan §6.3)

**The proof:** `test_stop_gate_e_a_sale_from_a_new_party_to_the_customer_view_over_http`.
**Over HTTP only, 17 commands:**
1. a seller party, and its consent grant;
2. the buyer's request (the existing customer party of ACC_AMINA, who
   reads it at the end) and its criterion, through RAW → CONTACTED →
   QUALIFIED → ACTIVE, then confirmed;
3. a property, confirmed AVAILABLE;
4. its SALE offer, made ACTIVE, its terms confirmed;
5. the consent bound to the offer;
6. the run: one ELIGIBLE match;
7. the APPROVED review: one opportunity;
8. the share;
9. the internal read and the customer's read. The latter is validated
   against the frozen `CustomerOpportunityView`.

**Then on the very match approved:** STOP GATE D's `reconstruct` and
`replay`, from its stored rows, each with no problem.

**"From an empty database"** is read as: every business row of the proof is
made by the API. Only the seed's reference data (the location, the policy,
the reason codes) and the test accounts pre-exist. The document says so.

**The generator,** `db/gate/stop_gate_e_evidence.py`, has the D pattern. It
refuses (each refusal tested on a copy of the tree,
`tests/test_slice5_stop_gate_e.py`):
- a mapped test missing or failed, including a name passing in another
  module;
- the proof without its recorded properties, or of a transaction type other
  than SALE;
- a source change after the run, a stale document, or an unbound report;
- a new writer of `opportunities`, `match_reviews` or `interactions`;
- a general `POST /opportunities`.

It also computes, from the tree:
- the plan's eight Slice 5 operations, all routed;
- the writers;
- the migrations (`0001`–`0006`);
- K06 UNPROVEN, and SALE only.

**The document**, `docs/gate/SLICE_5_STOP_GATE_E.md`:
- generated from the bound run of `975a448`;
- **49 rows, all PASS**;
- `--check` exits 0.

## 6. Tests: 32 new cases, and one changed

- **`tests/test_slice5_step6.py`, 15 cases:**
  - L-S5-3a: 2;
  - L-S5-3b: 2;
  - the proof: 1;
  - E04: 1;
  - K05: 6;
  - the revalidate lock: 1;
  - K06 trigger-level: 2.
- **`tests/test_slice5_stop_gate_e.py`, 17 cases.**
- **Changed:** step 3's concurrency witness (§3.5).

**The suite:** 2333 at step 5's closure, then:
- +15 and +17, the two new files;
- +2 for `test_mutation_tools.py`'s import-safety tests of the new script.

That makes **2367**.

## 7. Mutations

`db/dev/mutate_slice5_step6.py`, 8 mutations:

| mutation | weakening | killed by |
|---|---|---|
| P1 | the approval's supersession ignores the policy | the L-S5-3a proof |
| P2 | the queue's supersession ignores the policy | the L-S5-3a proof |
| R1 | the approval takes no request lock | both L-S5-3b tests |
| R2 | the lock is `FOR NO KEY UPDATE` | both L-S5-3b tests |
| R3 | the lock is taken after the check | both L-S5-3b tests |
| C1 | the currency check takes no request lock | the revalidate test |
| **C2** | the currency check's lock is `FOR SHARE` | **survives: equivalent (§3.4)** |
| E1 | the consolidation task names no duplicate | the E04 test |

**The record:** `evidence/SLICE5-STEP6-MUTATIONS.txt`.
- **Run:** at `0183106`, on a clean tree, source fingerprint
  `9e6c68cc…84d7`.
- **Result: 7 of 8 fail.** The baseline is 15 passed.
- **Restoration:** every mutated file was restored and verified.
- **Before the run,** a script checked each anchor (one site each), that
  each mutation changes its file, and that each mutated file compiles.

**Step 3's L1/L2, rerun:**
`evidence/SLICE5-STEP3-MUTATIONS-L1-L2-AFTER-L-S5-3B.txt`, at `e9904c0`.
Both survive step 3's tests (§3.4).

## 8. The evidence round

Each row ran on a clean tree, source fingerprint `9e6c68cc…84d7`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Before any change | L-S5-3a proven; L-S5-3b's window confirmed (order A) | `e9904c0` | `evidence/SLICE5-STEP6-L-S5-3-BEFORE-FIX.txt` |
| Mutations | 7/8 fail; C2 equivalent | `0183106` → `e63e693` | §7 |
| Authorization matrix | **183 rules**, all PASS (five new); suite 2367/2367 | `cd5511f` | `AUTHORIZATION_EVIDENCE_MATRIX.md`; `--check --no-run`: current |
| PostgreSQL gate | PASS; 70 database-level PASS notices, 0 FAIL; 67 operations in parity | `975a448` (run at `cd5511f`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **2367 passed**, 0 failed, 0 errors, 0 skipped | `82f7995` (run at `975a448`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |
| **STOP GATE E** | 49 rows PASS; `--check` exits 0 | this note's commit | `SLICE_5_STOP_GATE_E.md` |

**STOP GATE D is not regenerated.** Its `--check` reports its three known
problems.

## 9. Limits that are part of these results

- **K06 is UNPROVEN.** It needs G5-13 (b)(ii)'s separate step.
- **SALE only.** G4-5R is open, and no RENT path is claimed.
- **"From an empty database"** is read as stated in §5.
- **L-S5-3a's second policy** lives inside one rolled-back transaction.
  The proof uses the real run and the real approval.
- **C2 survives as an equivalent mutant** (§3.4).
- **The cost of the approval's request lock** is stated in §3.3.
- **These results are ours.** No independent run exists.

## 10. What remains

- **The review of this step.**
- **If it closes the step:** the Slice 5 closure record (as
  `SLICE_4_CLOSURE.md`).
- **Two points put to the reviewer:**
  - C2 (§3.4);
  - the remedy of L-S5-3b itself. It is a proof, and the reviewer may
    prefer the documented-limit alternative the plan named.
