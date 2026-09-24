# Slice 3 · step 7 — Identity Lite

**Basis.**
- The contract's `postIdentityCandidatesGenerate` (ADMIN, OPERATOR),
  `getIdentityCandidates` (ADMIN, OPERATOR, REVIEWER) and
  `postIdentityCandidatesCandidateIdReview` (ADMIN, REVIEWER;
  separation-sensitive).
- ADR-03, including its words: "create alias mapping, mark the candidate
  CONFIRMED_SAME, then detect any affected open matches/opportunities and
  create review work".
- Developer Spec §8: pipeline §8.1, signals §8.2, "لا merge أو حذف آلي" §8.3.
- Red-team E01–E04.
- `docs/gate/SLICE_3_PLAN.md` §3.10, §6.1 (mandatory tests 6 and 7), §6.2 and
  §6.3.

**Code.**
- `services/identity.py`
- `api/routes/identity.py`
- `services/access.py`: the list, audited once.
- `services/audit_rows.py`: three tables with no audit trigger.
- `api/problems.py`: one new 409 code.

No table, column, migration or reason code was added. The ops count stays at
67, and the frozen contract is untouched.

## 1. Rules, mechanisms, proofs

| Rule | Mechanism | Proving tests | Mutation |
|---|---|---|---|
| the contract's default version is written, never the column's (plan §3.10) | explicit `algorithm_version` on every INSERT | `test_an_omitted_algorithm_version_is_stored_as_the_contract_default`, which also pins the premise that the column's default is `'rules-0.2.0'` | I1 |
| a version names an algorithm | only `rules-0.1.0` is accepted; others get a typed 422, not echoed, key not consumed | `test_an_algorithm_version_that_names_no_implemented_algorithm_is_refused` | I2 |
| no automatic merge; generation writes only PENDING_REVIEW | the INSERT's literal | `test_generation_only_ever_writes_pending_review` | I3 |
| reproducibility | `signals_for` is pure and id-free | `test_generating_twice_produces_identical_signals`: two pairs with equal facts give equal `signals` and `explanation` | I12–I15 |
| idempotent for a pending pair | the existing PENDING candidate is returned unchanged | `test_generating_twice_is_idempotent_for_a_pending_pair` | I5 |
| a decided pair is not reopened | not returned, and no new row | `test_a_decided_pair_is_not_reopened_by_generation` | I6 |
| **the pair race** (plan §6.3, third row) | `ux_identity_pair`; the loser's INSERT fails inside a SAVEPOINT and reads the winner's row | `test_generating_the_same_pair_twice_concurrently_yields_one_candidate`: `waited=True`, both calls succeed with the same one candidate | I7 |
| pairs are stored least-first | `LEAST`/`GREATEST` | `test_a_pair_is_stored_least_first_whichever_side_generated_it` | I4 |
| blocking (Spec §8.1 step 2) | same type, same known canonical location, neither an alias | `test_blocking_proposes_no_pair_across_type_or_location` (type; location; no location); `test_generation_for_an_alias_is_refused_and_aliases_are_never_paired` | I8, I9; aliases: I37, I38 (I10, I11 retired, §6.3) |
| OPERATOR excluded from the decision (maker-checker) | `x-roles`; INV-2 through the shared policy path (`test_inv2_separation.py`) | `test_an_operator_cannot_review`; `test_an_operator_generates_and_a_reviewer_cannot` | — |
| mandatory test 6: SAME without a canonical | typed 422 naming what is missing | `test_confirmed_same_without_a_canonical_id_is_refused` | I16 |
| mandatory test 6: the canonical must be one of the pair | typed 422 | `test_the_canonical_must_be_one_of_the_candidate_pair` | I17 |
| a canonical id with another decision is refused | typed 422 (§3, choice 3) | `test_a_canonical_id_with_another_decision_is_refused` | I18 |
| review reason codes are IDENTITY codes | category check; the caller's text is not echoed | `test_a_reason_code_outside_the_identity_category_is_refused` (OWNER_REJECTED, an unknown code, `otp`) | I19 |
| **alias FIRST**, then the status (ADR-03) | the order of writes | `test_confirmed_same_writes_the_alias_before_the_status`; `test_the_trigger_refuses_a_same_status_without_its_alias` (a **schema** guarantee, labelled as such) | I22 |
| a final decision is not reviewed again | a check after `FOR UPDATE` on the candidate | `test_a_final_decision_is_not_reviewed_again` (three pairs of decisions); `test_unsure_may_be_reviewed_again` | I20 |
| **two concurrent reviews of one candidate** | the candidate row lock and the rule above | `test_two_concurrent_reviews_of_one_candidate_leave_one_final_decision`: `waited=True`; the second raises `AlreadyDecided` | I20, I21 |
| no alias chains (ADR-03): typed 409s instead of P0001s | pre-checks under the property row locks, for EVERY decision (§6) | `test_the_chosen_canonical_may_not_itself_be_an_alias`, `test_an_alias_may_not_become_an_alias_again`, `test_a_canonical_record_may_not_become_an_alias` | I24, I25, I26 |
| **a candidate whose property has since become an alias is not decided** (review of c3aac8a) | the same check, for all four decisions | `test_a_candidate_whose_property_has_since_become_an_alias_is_not_decided` (DISTINCT, UNSURE, SAME with either canonical) | I25, I35 |
| **generation's window** (reviews of c3aac8a and 1935dc1) | lock (`FOR SHARE`, §6.4) and re-check, after the lock, of aliases AND blocking facts | `test_generation_rechecks_aliases_after_its_lock`; `test_generation_for_a_property_that_became_an_alias_in_the_window_is_409`; `test_a_review_waits_for_a_generation_between_its_lock_and_its_insert` | I36, I37, I38, I23; blocking facts: I39, I40 (§6.4) |
| **no chain by concurrency** | both properties locked in id order before the checks | `test_two_concurrent_reviews_cannot_build_an_alias_chain`: `waited=True`; the second raises `NotCanonical`; zero chains | I23 |
| E01: nothing deleted or rewritten | no DELETE or UPDATE of any source, offer or claim | `test_e01_confirming_same_deletes_and_rewrites_nothing` | — |
| E03: DISTINCT for similar units | no alias row | `test_e03_similar_units_confirmed_distinct_create_no_alias` | — |
| **the corrective effect** (ADR-03) | `raise_review_work`: one `RESOLVE_IDENTITY` task per open match or opportunity on the alias | `test_confirming_same_raises_review_work_for_affected_open_records` | I27, I29, I30, I31 |
| a match is open unless its **latest** review is REJECTED | the ordering `enforce_opportunity_gate()` itself uses | `test_a_match_whose_latest_review_is_not_rejected_is_still_open` | I28 |
| E04: a duplicate open opportunity is surfaced, not closed | `duplicate_open_opportunity_ids` in the task | `test_e04_a_duplicate_open_opportunity_is_surfaced_not_closed` | I32 |
| E02: no new match on an alias | `enforce_match_commercial_context` (a **schema** guarantee) | `test_e02_a_new_match_on_the_alias_is_refused_by_the_schema` | — |
| mandatory test 7, **narrowed** (plan §6.4) | `resolve_canonical_property`, on an alias made through the API | `test_the_canonical_resolver_returns_the_canonical_for_an_alias` | — |
| every identity write audited | `audit_rows`, for candidates, aliases and tasks | `test_every_identity_write_is_audited` (exact sequence) | I33 |
| the list | status as text; `PageMeta`; audited once (R6.3c); CUSTOMER refused | `test_the_list_filters_by_status_and_pages`; `test_a_customer_cannot_list_candidates` | I34 |

`tests/test_slice3_identity.py` has 67 cases: 57 at c3aac8a, 7 added in the
review of c3aac8a, and 3 in the review of 1935dc1 (§6). Thirty-eight mutations
are active (I10 and I11 are retired, §6.3), and are run
by `db/dev/mutate_identity.py`, through the shared runner, and **every one
fails at least one test**. The output, bound to its commit and fingerprint, is
`docs/gate/evidence/STEP7-IDENTITY-MUTATIONS.txt`.

**Found by the mutations and corrected before commit.**
- I16 survived at first. Without the "canonical required" check, the next
  check (`not in pair`) still refused `None`, with a 422 but a less precise
  message. That message is the behavior the check exists for, so the test now
  asserts it.
- A CAS predicate in the decision's `UPDATE` duplicated the check made after
  `FOR UPDATE`. Under Read Committed, a locking read that waited returns the
  row's newest committed version (PostgreSQL 16 documentation, §13.2.1). So
  both guard the same column of the same locked row, and no data can
  separate them: unlike the step-6 revocation date, two writers cannot
  disagree here. It was removed. The two concurrency tests above prove the
  lock.

## 2. rules-0.1.0 — the signals, documented and versioned

Developer Spec §8.2 gives categories, not numbers. The numbers below are this
version's own, and changing any of them makes a new version.

| Signal | Rule | Spec category |
|---|---|---|
| blocking | same `property_type`, same non-null `canonical_location_id`, neither record an alias | §8.1 step 2 |
| `land_area`, `built_area` | ratio of the larger to the smaller: ≤ 1.10 `CLOSE`; ≥ 1.50 `CONTRADICTION`; otherwise `APART`; `ONE_UNKNOWN` or `BOTH_UNKNOWN` | "مساحة متقاربة" medium; "270 مقابل 600" contradiction |
| `shared_offer_party` | one party has an offer (any status) on both properties | "نفس PARTY" strong |
| `local_location_detail` | equal after whitespace collapse and casefold: `EQUAL`, `DIFFERENT` or `UNKNOWN` | "وصف مميز" medium |

- `explanation` lists the strong, medium and contradiction signals, and says
  that the signals propose and a reviewer decides.
- Neither object carries an id or a time.
- The boundaries are pinned by `test_area_signal_boundaries_of_rules_0_1_0`:
  100/110 is CLOSE, 100/110.01 APART, 100/149.99 APART, 100/150 CONTRADICTION.
- A contradiction does not suppress the candidate. The spec says a
  contradiction "قد تمنع SAME": it may prevent SAME, so the reviewer sees it.

## 3. Choices within the rules, stated for review

1. **Generation returns every PENDING candidate for the pairs it considered**,
   new or already pending. Decided and UNSURE pairs are neither reopened nor
   returned.
2. **An unimplemented `algorithm_version` is refused with a typed 422.** Plan
   §3.10 says to store "the caller's value when given". Storing a version that
   was not run would misdescribe the candidate, so only the implemented one
   is accepted.
3. **A `canonical_property_id` sent with CONFIRMED_DISTINCT or UNSURE is
   refused (422).** The contract's own description says it is "required only
   for CONFIRMED_SAME". Accepting it silently would record a value with no
   meaning.
4. **Review reason codes must be `IDENTITY` codes.** The FK accepts any code,
   but an `OPPORTUNITY` reason on an identity decision would misdescribe it.
5. **UNSURE is not final.** It may be reviewed again. CONFIRMED_SAME and
   CONFIRMED_DISTINCT are final: a new `IDENTITY_CANDIDATE_DECIDED` (409).
6. **The review work** goes into `tasks`:
   - type `RESOLVE_IDENTITY` (the only identity-related `task_type`);
   - reason `IDENTITY_CONSOLIDATED` (seeded, category IDENTITY);
   - `property_id` is the alias;
   - `request_id` and `match_id` are those of the affected record;
   - the payload carries the pair, the candidate, and any duplicate
     opportunities on the canonical record.

   **What counts as "open"**, which ADR-03 does not define:
   - a match, unless its latest review is REJECTED or an opportunity carries
     it;
   - an opportunity, unless CLOSED.

   Nothing is modified.
7. **The generate body is closed** (`extra="forbid"`), although the contract
   does not close it. Every sibling body in this code base is closed, and an
   unknown field here would otherwise be dropped in silence.
8. **Seeded matches and opportunities** (plan §6.4). The corrective-effect
   tests insert them with SQL, since no slice creates them yet. Each passes
   the schema's own match, review and opportunity gates. Acceptance condition
   6 ("no `match_candidates` row written by any path") concerns code paths;
   no code path here writes one.

## 4. Integration with steps 1 and 6 (the step-6 closure item)

The review of 3a53b0a asked for the alias case of the public list to be tested
with an alias made by this step's API, not by fixture SQL:
- `test_an_alias_made_through_the_api_leaves_the_public_list`: before the
  review, both records are listed with their own consented offer. After
  CONFIRMED_SAME, only the canonical record is listed, with only its own
  offer (G3-13, as delivered).
- `test_an_alias_made_through_the_api_refuses_writes`: F-2 (step 1), now
  reachable through the API. A PATCH on the alias is a 409
  `IDENTITY_ALIAS_NOT_CANONICAL`.

## 5. Not in this step

- The authorization-matrix rules for these operations, and the STOP GATE C
  evidence ("canonical or alias?"), are step 8's.
- No matching exists to consume the resolver: mandatory test 7 stays narrowed
  (plan §6.4).

## 6. The review of c3aac8a — a blocker, and a race measured then closed

### 6.1 The review blocker: deciding a pair after one of its properties became an alias

**The reviewer's finding** (from reading the code). The alias-structure
checks ran only in the CONFIRMED_SAME branch. So given A–B and B–C, with B
then confirmed an alias of A, a CONFIRMED_DISTINCT or UNSURE decision on B–C
was accepted.

**Reproduced over HTTP on PostgreSQL** on the c3aac8a `identity.py`, with the
new test kept:
- DISTINCT and UNSURE were **accepted (200)**;
- the two SAME variants were already refused, by the SAME-only pre-checks.

**Fixed.** `_lock_pair_and_check` now runs for EVERY decision:
1. it locks both properties in id order;
2. it refuses (409 `IDENTITY_ALIAS_NOT_CANONICAL`) if either is an alias;
3. for SAME it also refuses when the property to become the alias already
   acts as canonical.

**The test** (`test_a_candidate_whose_property_has_since_become_an_alias_is_not_decided`,
4 cases):
- the candidates exist BEFORE the alias;
- each refusal is a typed 409;
- the candidate row, its audit rows and the alias table are unchanged;
- no idempotency record is stored under the key;
- the SAME key then serves a valid review of the canonical pair A–C.

**What happens to such a candidate.** It stays PENDING and cannot be
decided. The question is re-posed by generating on the canonical record,
which now proposes A–C.

### 6.2 Generation's window: measured before the fix

**The reviewer's question.** Between reading `_BLOCKED_PAIRS` and inserting,
generation neither locked the properties nor re-checked aliases. Can a review
that commits an alias inside that window lead to a candidate that pairs the
alias?

**Measured, on the c3aac8a code: yes.** The generator was paused after
reading its pairs, and a review then made B an alias of A and committed.
Resumed, the generator inserted C–B and returned it as a new candidate. The
harness and its output are in
`docs/gate/evidence/STEP7-GENERATION-RACE-BEFORE-FIX.txt`.

**Fixed: `_lock_and_recheck`**, in the same transaction, after reading the
pairs. (Its lock mode was changed from `FOR KEY SHARE` to `FOR SHARE` in the
review of 1935dc1, §6.4; the text below describes the c3aac8a round.)
- every involved property is locked in ONE statement, in id order, with
  `FOR KEY SHARE`. That mode conflicts with the review's `FOR UPDATE` and not
  with an ordinary property UPDATE (PostgreSQL 16 documentation, §13.3.2).
  One ordered acquisition does not deadlock with a review, which also locks
  in id order;
- aliases are then read AGAIN. A pair with an alias is dropped, and a focus
  property that became an alias is the typed 409.

**Two windows, two tests.**

| Window | Test | What it shows | On the c3aac8a code |
|---|---|---|---|
| (a) BEFORE the lock | `test_generation_rechecks_aliases_after_its_lock`; `…became_an_alias_in_the_window_is_409` | the review commits the alias inside the window; the re-check drops every pair with B, or refuses a focus B | fails (structurally: the function did not exist); the behavioral evidence is the measurement above |
| (b) AFTER the lock, BEFORE the INSERT | `test_a_review_waits_for_a_generation_between_its_lock_and_its_insert` | the review WAITS on generation (witnessed by `pg_blocking_pids`), so C–B is written while B is still canonical, before the alias | **fails**: `waited=False`, the review committed inside the window |

**A test of ours that proved nothing, found and rewritten.** The first
version of the window-(b) test paused AFTER the generator's INSERT. It passed
on the unfixed code, because an INSERT's foreign keys already take
`FOR KEY SHARE` on the referenced property rows (PostgreSQL 16
documentation, §13.3.2). The pause was moved inside `_candidate_for_pair`,
which runs after the lock and before the INSERT. Since then the test fails on
the unfixed code, and I36 (the lock removed) fails it.

**Mutations added:**

| Mutation | Change | Test that fails |
|---|---|---|
| I35 | the check only for SAME (the reported defect) | the DISTINCT and UNSURE cases |
| I36 | generation's lock removed | window (b) |
| I37 | the re-check removed | window (a) |
| I38 | the focus re-check removed | the focus test |

**The lesson carried forward.** Passing generation mutations do not measure a
window that no test enters. The reviewer said so, and it was true of our
first window-(b) test as well.

### 6.3 Two pre-lock checks, subsumed by the fix and removed

The mutation run at e7bab83 found two survivors:
- I10: the `NOT EXISTS` alias filter in `_BLOCKED_PAIRS`;
- I11: the focus-alias check at entry.

Both read `property_identity_aliases` BEFORE generation's lock.
`_lock_and_recheck` reads the same table AFTER it, so both became subsumed.
No data can separate the two reads: the same rows are read earlier and then
later. That differs from step 6's revocation date, where two columns could
disagree. The two checks were removed. Their numbers are retired, not reused,
so the evidence files stay comparable across rounds. The behavior they
provided is proven by I37 and I38.

### 6.4 The review of 1935dc1: the blocking facts change inside the window

**The reviewer's finding** (from reading the code and the PostgreSQL
rules). Generation re-checked only aliases after its lock. A PATCH may change
`property_type` or `canonical_location_id`. Under Read Committed, the pair
read and the lock can see two different states, and a lock does not
re-evaluate the earlier query's condition. Also, `FOR KEY SHARE` does not
conflict with an UPDATE of non-key columns, while `FOR SHARE` does.

**Measured before the fix**, on the 1935dc1 code
(`docs/gate/evidence/STEP7-PATCH-RACE-BEFORE-FIX.txt`):
- **Window (a), before the lock: defect confirmed, for both fields.** An
  HTTP PATCH committed inside the window, and B–C was created with signals
  claiming the same type and location, although the facts had already
  changed.
- **Window (b), after the lock: the HTTP PATCH waited.** The reason was not
  generation's lock mode. The PATCH path's own version guard takes
  `SELECT … FOR UPDATE` (`services/concurrency.py`), which does conflict with
  `FOR KEY SHARE`. So window (b) was protected only **incidentally**, by a
  lock chosen elsewhere. Any writer that updates the columns without that
  guard would pass: a plain UPDATE takes `FOR NO KEY UPDATE` (PostgreSQL 16
  documentation, §13.3.2).

**Fixed: one statement locks every involved property `FOR SHARE` and reads
its blocking facts.**
- A locking read that waited returns the newest committed version
  (§13.2.1), so these are post-lock facts.
- A pair is kept only if its type and known location still match and neither
  side is an alias.
- Until the generating transaction ends, no writer of any kind can change
  those facts on a proposed property.
- The facts used for the signals (`_FACTS`) are read after the lock too.

**Tests.**

| Window | Test | On the 1935dc1 code | Mutation |
|---|---|---|---|
| (a) before the lock | `test_a_patch_in_generations_window_leaves_no_stale_candidate` (the type; the location), over HTTP: B–C is not created, D–C (unchanged facts) is | **fails**: B–C created | I39 |
| (b) after the lock | `test_generations_lock_holds_the_blocking_facts_against_any_writer`: a PLAIN `UPDATE` of `property_type` must wait on generation (witnessed) | **fails**: `waited=False` | I40 (`FOR KEY SHARE` restored), I36 |

**Two further corrections, ours.**
- **Timestamps cannot order commits.** Two concurrency tests compared
  `generated_at` with `resolved_at` or `updated_at`. Each column is `now()`,
  i.e. its transaction's START time, so the comparison held whether or not
  the second writer had waited. Both comparisons were removed. The witnessed
  wait is the proof of order.
- **A defect in the mutation runner.** It made its backup copy before
  checking the anchor. A missing anchor therefore aborted the run and left a
  stray `.orig` file. The working file was verified byte-identical to that
  backup, which shows it was never mutated. The runner now checks the anchor
  first.
