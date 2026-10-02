# Slice 4 · step 7 — the matching run: persistence, audit, the diagnostic row, concurrency

**Status: delivered for review. Not closed.** Slice 4 is not closed, and
G4-5R is not decided: the RENT refusal stays in force.

**Authorised:** the review of b3246b0 approved G4-15 with the constraints
D1–D6, and allowed step 7 on them, "with its seven earlier conditions as
recorded in the plan". The decisions are recorded under G4-15 in
`docs/gate/SLICE_4_PLAN.md`, revision 14.

**Basis:**
- `docs/gate/SLICE_4_PLAN.md` revision 14: §3.3 (one Repeatable Read
  transaction, measured), §3.6 (audit), G4-13, G4-15 (D1–D6 and the seven
  conditions);
- CORRECTION-004 (`docs/contract/CORRECTION-004-matching-policy-version.md`);
- the contract's `postRequestsRequestIdMatchingRun`, `MatchCandidate`,
  `CriterionResult`, `Diagnostic` and `Task.task_type`;
- `schema_v0.2.3.sql`: `match_candidates` (651–685),
  `match_criterion_results` (687–707), `match_diagnostic_runs` (719–737),
  `trg_match_commercial_context` (1170–1207);
- Developer Spec §13, §13.1 and §22.1;
- PostgreSQL 16 documentation §13.2.2 (Repeatable Read).

**These are our runs.** Nobody else has re-run them.

---

## 1. What was built

| File | What it holds |
|---|---|
| `src/turab/services/matching_run.py` (new) | `prepare`: every refusal, by reads alone. `execute`: evaluation, storage, the diagnostic row |
| `src/turab/matching/explain.py` (new, pure) | the explanation (D4), `next_action` (D5), the counts (D2, D3), `blocker_summary` (D3b) |
| `src/turab/matching/gates.py` | `action.next@1`, pinned like the gates (D5) |
| `src/turab/api/routes/matching.py` (new) | the route `postRequestsRequestIdMatchingRun` |
| `src/turab/services/command.py` | `run(prepare=…, isolation=…)`, below |
| `src/turab/services/idempotency.py` | `begin` split into `lookup` (reads) and `claim` (writes); `begin` behaves as before |
| `src/turab/db/session.py` | `audited_transaction(isolation=…)`, from a closed set |
| `src/turab/services/audit_rows.py` | the three match tables added to the command-audited tables |
| `src/turab/api/problems.py` | three problem codes (§4) |
| `db/gate/stop_gate_c_evidence.py` | Slice 3's condition 6 narrowed to one approved writer (§8) |

`rule_pins.py` gains one pin, `action.next@1`, added by `db/dev/pin_rules.py`.
No existing pin changed.

---

## 2. The seven conditions

### 2.1 One Repeatable Read transaction (condition 1)

- **Isolation.** The route asks for `REPEATABLE READ`. `audited_transaction`
  sets it with the transaction's FIRST statement, as `SET TRANSACTION`
  requires.
- **A guard.** `prepare` reads `transaction_isolation` and refuses anything
  else (`NotRepeatableRead`). The run therefore cannot read two states of
  the world.
- **One instant.** `as_of` is `transaction_timestamp()`. It is every match's
  `evaluated_at` and the diagnostic's `run_at`.
- **A SAVEPOINT per match.** The match, its criterion rows and their audit
  rows are written under one savepoint.
- **23505.** A unique violation on the frozen
  `UNIQUE(request_id, property_id, matching_policy_id, input_hash)` is an
  identical input. The constraint is checked by name. The savepoint is
  rolled back, and the stored match is returned:
  - in the run's snapshot, when it is visible there;
  - otherwise on a NEW connection (measured D5). The row is immutable, so
    that read returns what was written.
- **Any other integrity error propagates.**
- **No `ON CONFLICT`.** It fails with 40001 under Repeatable Read (measured
  D2 and D4).

Tests:
- `test_the_run_reads_one_repeatable_read_snapshot`;
- `test_the_run_refuses_a_transaction_that_is_not_repeatable_read`;
- `test_an_isolation_outside_the_closed_set_is_refused`;
- `test_a_unique_violation_on_another_constraint_is_not_taken_for_an_identical_input`;
- `test_the_identical_input_constraint_is_named_as_postgresql_names_it`.

### 2.2 The input hash, and the identical re-run (condition 2)

- The hash is G4-13's, with `evaluated_offer_id`. It is recomputed from the
  five STORED snapshots, and the result equals the stored hash
  (`test_the_stored_hash_is_recomputed_from_the_stored_snapshots`).
- **An identical re-run** returns the existing match and writes no second
  match. The re-run writes its own diagnostic row, since D1 asks for one per
  run, and that row's audit row. It writes nothing else
  (`test_an_identical_rerun_returns_the_existing_match_and_writes_no_second`).
- **A changed input is a new match.** After a price change, a new match is
  stored beside the old one, and the old one is unchanged
  (`test_a_changed_input_is_a_new_match`).
- **Two offers on identical terms give two matches**
  (`test_two_offers_on_identical_terms_are_two_matches`).

### 2.3 The versions used (condition 3)

- Each criterion row carries its `rule_id` and `rule_version`.
- `explanation.engine` names every other pinned function that ran:
  - `freshness.state@1`;
  - `permission.binding_state@1`;
  - `freshness.gate@1`;
  - `permission.gate@1`;
  - `eligibility.precedence@1`;
  - `score.soft@2`;
  - `action.next@1`.

Test: `test_every_version_used_is_stored_and_no_version_1_rule_is_cited`.

### 2.4 PERMISSION_MISSING worded from its basis (condition 4)

- The match's `explanation.reasons` carries a `wording` written from the
  basis (`explain.PERMISSION_WORDING`).
- The diagnostic's `blocker_summary` carries the same wording.
- The seeded label, "Permission scope insufficient", appears nowhere in the
  explanation, the next action or the diagnostic. This is checked against
  the label read from the database.

Tests:
- `test_permission_missing_is_worded_from_its_basis`;
- `test_every_permission_basis_has_a_wording`.

### 2.5 Version 1 is not replay evidence (condition 5)

- `criteria.RULES` selects version 2 of `location`, `area_min` and
  `attribute_option`, and of `count_min`.
- No stored criterion row in the test database cites a version 1 of any of
  them. Measured over the whole suite's database, not only this test's rows.
- **G4-2's limit stands.** This step offers no historical replay. The
  replay proof belongs to step 8, and it will cover only the versions that
  stored matches cite.

### 2.6 Audit, generated_by, ai_trace_ref (condition 6)

- Every row written has its audit row, in the same transaction:
  - each match (`match_candidates`);
  - each criterion row (`match_criterion_results`);
  - the diagnostic (`match_diagnostic_runs`).
- Each audit row carries the actor and the operation, from
  `audited_transaction`.
- `generated_by = 'RULE_ENGINE'` and `ai_trace_ref` is NULL, both written
  explicitly.

Test: `test_a_run_stores_each_match_with_its_criteria_audit_and_one_diagnostic`.

### 2.7 G4-5R (condition 7)

A RENT run is refused with 422 `MATCHING_INPUT_REFUSED`, whose detail starts
with `G4-5R`. This holds with or without a budget, and nothing is written
(`test_a_rent_request_is_refused`).

---

## 3. D1–D6, as applied

### D1 — the boundary
- No `match_reviews`, `opportunities` or `tasks` row is written:
  - **counted** before and after a run
    (`test_no_review_opportunity_or_task_is_written`);
  - **computed** from the tree: no file inserts into `match_reviews` or
    `opportunities`; the three match tables have one writer, the run; and
    neither the run nor the matching package inserts a task
    (`test_no_path_writes_a_review_or_an_opportunity_and_matching_writes_no_task`).
- `suggested_actions` and `relaxation_scenarios` are `[]`.
- `next_action` is stored on the match. It is a recommendation.

### D2 — the near match
- **Rule:** REJECTED, exactly one REQUIRED FAIL, and every other REQUIRED
  criterion PASS.
- **Tests** (`test_a_near_match_is_one_required_fail_and_every_other_required_pass`):
  - six cases, among them one FAIL with one REQUIRED UNKNOWN, which is not a
    near match;
  - over HTTP, in `test_the_counts_take_each_candidate_once_in_each`.

### D3 — the counts
In one run of five candidates:
- ELIGIBLE → ready: 1;
- NEED_MORE_INFORMATION → actionable unknown: 1;
- REJECTED with one FAIL and all else PASS → near match: 1;
- REJECTED with two FAILs, and REJECTED with one FAIL plus one REQUIRED
  UNKNOWN → none.

The counts are (1, 1, 1), both in the response and in the stored row.

### D3b — `blocker_summary`
- **Format:** `turab.blocker-summary/1`.
- **`by_reason`:**
  - keyed by the reason code, or by `GATE:basis` when the code is null;
  - each key gives `candidates` (each candidate counted once), `gates`,
    `bases` and `criteria` (each counted once per candidate);
  - a PERMISSION key also gives `wording`.
- **`excluded`:** the candidate set's exclusions, each with its id, reason
  and detail.
- **`excluded_counts`** and **`candidates_evaluated`.**

Tests:
- `test_the_blocker_summary_counts_a_candidate_once_per_key`: a candidate
  with two REQUIRED FAILs whose code is null counts once under
  `HARD:REQUIRED_FAIL`;
- `test_the_run_reports_its_exclusions_with_ids`.

### D4 — the explanation
- **Format:** `turab.match-explanation/1`.
- **Content:**
  - `criteria`, keyed `CODE#ordinal`: importance, compatibility, blocking,
    reason code, source, `request_criterion_id`, the rule as `id@version`,
    and the rule's own explanation;
  - `deferred`: the deferred criteria, without their values;
  - `soft_score`: its basis and terms;
  - `reasons`, each kept;
  - `engine`.
- **It carries nothing from a claim.** Neither its id nor its value
  appears; the criterion row cites the claim
  (`test_the_explanation_carries_nothing_taken_from_a_claim`).
- **It never states the seller expectation.** In the test, the price passes
  on the expectation alone (ask 35M > max 30M ≥ expectation 27,777,777).
  Neither the field name nor the value appears in the explanation, the next
  action or the diagnostic
  (`test_the_explanation_never_states_the_seller_expectation`).

### D5 — `next_action`, by `action.next@1`
- **Null** for ELIGIBLE and REJECTED.
- **The order is §13.1's:**
  1. information, for an ACTIONABLE blocking unknown only;
  2. reconfirmation, in the order request → property → offer;
  3. permission.
- **Tie-break among unknowns:** REQUIRED first, then the order in which the
  criteria were evaluated, which `criteria_of` fixes.
- **Types:**

  | Case | Type | Priority |
  |---|---|---|
  | unknown on DOCUMENT_TYPE or RIGHT_TYPE | VERIFY_DOCUMENT | HIGH |
  | unknown on BUDGET_MAX | CONFIRM_PRICE | HIGH |
  | unknown on any other code | OTHER | HIGH |
  | request not fresh | RECONFIRM_REQUEST | NORMAL |
  | property not fresh | RECONFIRM_PROPERTY | NORMAL |
  | offer terms not fresh | CONFIRM_PRICE | NORMAL |
  | permission not PASS | CONFIRM_PERMISSION | NORMAL |

- **`subject`:**
  - the entity: REQUEST, PROPERTY or PROPERTY_OFFER, with its id;
  - for a criterion, also its code, ordinal and `request_criterion_id`;
  - the reason code and the basis.

  The entity follows the basis:
  - **the request** when its own maximum is not stated, or when no rule
    reads the criterion;
  - **the offer** when its price or negotiation is unknown;
  - **the property** otherwise.
- **Every type is a value of the contract's `Task.task_type`**
  (`test_every_type_is_a_task_type_of_the_contract`).
- **No task is created.**

### D6 — a refused run
- **Status codes:**
  - **409:** a request status a run does not accept;
  - **422:** every other refusal of the run. These are CORRECTION-004
    (omitted, null, unknown, mistyped, the frozen default `0.1.0`, an
    INACTIVE policy's version), G4-3 (b), G4-7 and G4-5R;
  - **404:** an unknown request.
- **Before any write, observed.** The refusals are decided in `prepare`.
  `CommandService.run` calls it after the idempotency LOOKUP, which only
  reads, and BEFORE the key is CLAIMED. Every statement the database
  receives during a refused call is recorded, and none is an INSERT, UPDATE
  or DELETE. The same recording on a valid call shows inserts
  (`test_a_refusal_is_decided_before_any_write`).
- **Nothing is changed, counted.** Each refusal test compares, before and
  after:
  - the request's matches, criterion rows and diagnostic rows;
  - the audit log's high-water mark;
  - the idempotency records under the call's key.

  The same key then serves a valid run.
- **A replay still replays.** The lookup precedes the refusals. So an
  identical call with the same key returns its stored result even after the
  request stopped being matchable
  (`test_a_replay_is_returned_even_after_the_request_stopped_being_matchable`),
  as API_CONTRACTS §2.3 promises.
- **The refusal order is fixed:**
  1. the version;
  2. the request (404, then 409);
  3. the criteria, in step 4's order (G4-7, then G4-3 (b), then G4-5R).

---

## 4. The problem codes

| Code | Status | Rule |
|---|---|---|
| `MATCHING_POLICY_VERSION_REFUSED` | 422 | CORRECTION-004; the value is never echoed (tested for each string case) |
| `REQUEST_NOT_MATCHABLE` | 409 | G4-8 |
| `MATCHING_INPUT_REFUSED` | 422 | G4-3 (b), G4-5R, G4-7; the detail names the rule and the criterion, never the value |

`matching_policy_version` is typed `Any` in the body model, deliberately.
Every wrong version therefore reaches the one typed refusal, not a generic
validation error that could echo the input. The body is closed: an unknown
field is 422.

---

## 5. Concurrency (plan §6.3)

| Race | Witness | Result |
|---|---|---|
| two identical runs | run A has inserted its match and not committed. Run B is OBSERVED waiting on a lock in `pg_stat_activity`, on its insert into `match_candidates` | Both succeed. One match row, two diagnostic rows. A found its row in its own snapshot; B found it only on a new connection (`(id, True)` then `(id, False)`, asserted). Both return the same match |
| a run while the offer's price changes | the run has read its snapshot; the price change COMMITS; then the run inserts | The insert succeeds against the snapshot (measured D7). The match records the old price and the old offer version. A later run stores a new match, with a new hash |

No winner-and-loser outcome appeared.

---

## 6. The response

`{"matches": [MatchCandidate…], "diagnostic": Diagnostic}`, status 201.

- **Each match is READ from its stored rows** (`match_view`), not
  assembled from what was computed (`test_the_response_is_the_stored_rows`).
- **Two fields are added beyond the contract's schemas.** The schemas do
  not close `additionalProperties`. Stated here so the addition is seen:
  - each criterion carries `ordinal` and `request_criterion_id`, the key of
    `explanation.criteria`;
  - the diagnostic carries `diagnostic_run_id`.
- **Left out:** the row columns that `MatchCandidate` does not define
  (`generated_by`, `ai_trace_ref`, `created_at`).
- **Numbers.** Every number is stored exactly, in canonical form
  (`test_decimal_values_are_stored_exactly`). The JSON response carries
  them as JSON numbers.
- **Staff only.** The role gate admits ADMIN, OPERATOR and REVIEWER, the
  contract's `x-roles`. `authorize_staff_only` is the second lock. A
  customer is refused with 403, and nothing is written.

---

## 7. Mutation evidence

`db/dev/mutate_slice4_step7.py`: **38 mutations** over the step-7 test file:
- **T1–T8:** the transaction, the savepoint, the identical input;
- **W1–W9:** what is written;
- **R1–R5:** the refusals and their order;
- **D1–D8:** the diagnostic;
- **A1–A8:** the next action.

The anchor guard (`tests/test_slice4_mutation_anchors.py`) now covers
step 7's mutations of `gates.py`.

The trial run, on the uncommitted tree, killed all 38. **Two tests were
added BEFORE the trial**, because the existing tests could not tell these
mutations apart from correct code:
- `test_a_refusal_is_decided_before_any_write`: R3 claims the key before
  the refusal, and the rollback then erases the claim, so counting rows
  after the call cannot see it;
- `test_a_soft_unknown_that_does_not_block_gives_no_information_action`: A8.

**Clean-tree result: 38 of 38 fail, and none survives.**
- Recorded at `7a223d7`, source fingerprint `e8d48071…5709a`, baseline 76
  passed (`evidence/SLICE4-STEP7-MUTATIONS.txt`).
- Every mutated file was restored and verified by sha256.

---

## 8. A change to a Slice 3 evidence script, stated

**What the script checked.** `db/gate/stop_gate_c_evidence.py` computed
Slice 3's condition 6, "no path writes `match_candidates`", and treated any
writer as a PROBLEM. That condition was Slice 3's boundary: matching was
closed. Slice 4 opened matching, and G4-15 approves the run as its writer.

**The change.** The script now names ONE approved writer,
`src/turab/services/matching_run.py`, with its decision. Any other writer is
still a PROBLEM. The generated text states the approval.

**Consequences:**
- The committed `SLICE_3_STOP_GATE_C.md` is already reported stale. That
  PROBLEM is expected and documented in `SLICE_4_STEP1_DELIVERY.md` §4.
  This change adds to the same staleness.
- Without the change, `test_evidence_binding.py` failed on this tree.

---

## 9. For the reviewer: one point the decisions do not settle

**The policy refusals of §3.1.** The active policy may promise behaviour
this engine lacks (`PolicyNotImplemented`), or there may be no active policy
at all (`NoActiveFreshnessPolicy`). In either case `prepare` raises.
- **As delivered:** the result is a 500, with nothing written, as Slice 2
  treats `NoActiveFreshnessPolicy`.
- **The question.** D6 says "422 for every other defined run refusal".
  These two are configuration faults, not the caller's input, so 422
  ("Unprocessable Content") would describe them wrongly.
- **Options:**
  - (a) keep 500;
  - (b) a typed 422;
  - (c) a typed 503.

**No option is chosen in code beyond the existing behaviour, (a).** With
the seeded policy `0.2.0`, neither case can occur.

---

## 10. What remains

- **Step 8:**
  - GET match and GET diagnostic;
  - the ten mandatory tests under their planned names;
  - STOP GATE D (reconstruction and replay);
  - the matrix.
- **G4-5R:** the period is open, and the RENT refusal is in force.
- **§9:** the status of the two policy refusals.
