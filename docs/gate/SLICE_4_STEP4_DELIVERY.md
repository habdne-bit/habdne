# Slice 4 · step 4 — the criterion rules, the unknown classification, the hard and information gates

**Status: NOT closed.**
- The review of f789a59 found three defects. They are fixed and answered in
  **§10**, which supersedes the rows and choices it names below.
- The review of ba5f25e found that §10's pre-check and the rule judged
  different domains. That is answered in **§11**, which supersedes §10.2's
  first item where it says otherwise.

**Authorised:** the review of 6b833fb closed step 3 and allowed step 4 on
**G4-3, G4-4, G4-6, G4-7** and **the SALE table of G4-5 only**. G4-5R stays
open: "no numeric comparison of a rent price with the request's budget, and
no PASS or FAIL built on it, before the period of both sides is defined and
approved".

**Basis:**
- `docs/gate/SLICE_4_PLAN.md` revision 7: G4-3 to G4-7 as decided, §2, §3.2,
  §3.4 (corrected) and §8 step 4;
- Developer Spec §11 (Compatibility + Evidence + Reason), §12.1 (hard gate:
  REQUIRED criteria only), §13 and §13.1 (blocking and actionable unknowns);
- red-team C01, C03, D02, G01, G02; spec M-01 to M-04;
- the frozen seed: criterion codes (lines 118–131), reason codes (134–160),
  attribute options (91–115);
- RFC-001 R9.3.

**Nothing is written.** Every function here is a read or a pure function.
`test_evaluating_writes_nothing` counts eleven tables before and after, and
the package-wide `test_the_matching_package_reads_and_never_writes` covers
the three new modules.

**Not in this step:** eligibility and its precedence (G4-11, step 5),
freshness and permission (step 5), the soft score (step 6), and persistence
(step 7).

## 1. The modules

| Module | What it does |
|---|---|
| `criteria.py` | the criteria a request yields (columns, then rows), each validated; the typed refusals of G4-3 (b), G4-5R and G4-7 |
| `rules.py` | eight registered rules, version 1, each self-contained and pinned (G4-2) |
| `hard_gate.py` | runs the rules, sets `blocking` (G4-4), derives the hard gate, the information gate and the actionable unknowns |
| `snapshots.py` | the property snapshot gains `location_ancestry` (format 2); `stored_form` |

**The rules read the stored form only.** `snapshots.stored_form` gives a
snapshot exactly as a stored `jsonb` row returns it: canonical JSON, numbers
as `Decimal`, uuids and timestamps as strings. A live run and a replay from
stored rows therefore give the rules identical input.
`test_results_from_live_snapshots_equal_results_from_jsonb_round_trips` puts
the snapshots through PostgreSQL `jsonb` and back, and gets identical
results.

**Self-contained rules.** A rule's pin covers only its own source (G4-2). So
no rule reads a module-level name other than `Decimal` and the builtins.
`test_every_rule_is_self_contained` checks this on the compiled code of all
eight rules, and `test_the_detector_sees_a_module_constant` shows that the
check detects a violation.

## 2. The rules

| Code | Operators | Property side | UNKNOWN when | FAIL reason | Rule |
|---|---|---|---|---|---|
| TRANSACTION_INTENT | EQ NEQ IN NOT_IN | the evaluated offer's `transaction_type` | no offer | — | `transaction_intent@1` |
| PROPERTY_TYPE | EQ NEQ IN NOT_IN | `property_type` (NOT NULL) | never | PROPERTY_TYPE_MISMATCH | `property_type@1` |
| LOCATION | EQ IN | `location_ancestry` (G4-6: the subtree, as G3-14) | no location | LOCATION_MISMATCH, REQUIRED only (§10) | `location@2` |
| BUDGET_MAX (SALE) | LTE | asking price, negotiability, internal expectation | §3 | BUDGET_EXCEEDED | `budget_max_sale@1` |
| LAND_AREA_MIN / BUILT_AREA_MIN | GTE | `land_area_m2` / `built_area_m2` | null | AREA_BELOW_PREFERENCE, soft only (§10) | `area_min@2` |
| ROOMS_MIN / BEDROOMS_MIN | GTE | attribute ROOMS / BEDROOMS, with its claim; `attribute_applies_to` | applicable, and missing or non-numeric. **FAIL** when the attribute cannot apply to the type (G4-18 (b)) | — | `count_min@2` |
| DOCUMENT_TYPE / RIGHT_TYPE | EQ NEQ IN NOT_IN | attribute of the same code, with its claim | missing, `UNKNOWN`, `UNSPECIFIED_DOCUMENT` | DOCUMENT_MISMATCH, REQUIRED only (§10) / — | `attribute_option@2` |
| TEXT_SEMANTIC, CUSTOM_ATTRIBUTE, unregistered code (soft only) | — | — | always | — | `no_deterministic_rule@1` |

**Evidence (§3.4).**
- An attribute rule records the claim behind the resolved value, and that
  claim's level (`test_count_minimum_reads_the_resolved_attribute_and_its_evidence`).
- A projection column records both as null, with `"evidence":
  "NO_CLAIM_LINK"` in the explanation.

**Explanations are fixed codes** (`basis`, and `evidence` or `attribute`),
never free text. The set of texts a rule can emit is therefore its source's
string constants.

**Location replays from the snapshot.**
`test_the_location_rule_replays_from_the_snapshot_after_the_tree_changed`
moves a ksar to another commune after the snapshot is taken:
- the stored snapshot still gives PASS;
- a fresh snapshot gives FAIL.

## 3. G4-5, the SALE table, row by row

`test_the_sale_price_table` covers each row on PostgreSQL, plus "exp > max":

| Case | Result | Reason |
|---|---|---|
| max is null | UNKNOWN | — |
| ask is null | UNKNOWN | PRICE_NOT_KNOWN |
| ask ≤ max | PASS | — |
| ask > max, exp ≤ max | PASS | — |
| ask > max, negotiable YES | UNKNOWN | PRICE_NEGOTIATION_UNCONFIRMED |
| ask > max, negotiable NO | FAIL | BUDGET_EXCEEDED |
| ask > max, negotiable UNKNOWN | UNKNOWN | PRICE_NEGOTIATION_UNCONFIRMED |

**Mandatory test 4** (G02, M-04), at the criterion:
`test_negotiable_above_max_is_unknown_not_pass`.

**Mandatory test 5** (M-03, D02, R9.3), at the criterion:
`test_seller_expectation_can_pass_price_and_is_never_in_the_criterion_result`.
- A PASS decided by the expectation carries the same reason and explanation
  as a PASS on the asking price.
- The expectation's value appears in no field of the result.
- `test_no_rule_explanation_mentions_the_expectation` reads every string a
  rule can emit.
- The DTO half of the test is step 8.

**RENT (G4-5R, open).** The run is refused (§4). The SALE rule also raises
if a RENT offer ever reaches it (`test_the_sale_price_rule_refuses_a_rent_offer_outright`).

## 4. What the run refuses (`CriterionRefused`)

A refusal names the decision, the code and the criterion id. It never
echoes the value (`test_a_refusal_never_echoes_the_value`). Every row is
validated before any contradiction is judged, so the refusal a request gets
does not depend on row order.

| Decision | Refused | Tests |
|---|---|---|
| G4-7 | an operator that does not suit its code, at any importance. Evidence §E's `BUDGET_MAX IN ["a","b"]` is one of the cases | `test_an_operator_that_does_not_suit_its_code_is_refused` (14) |
| G4-7 | a value no rule can read (type, sign, fraction, unknown option). Evidence §E's LOCATION naming a random uuid is one of the cases | `test_a_value_no_rule_can_read_is_refused` (16); `test_a_location_naming_no_location_is_refused` |
| G4-7 | a unit no rule reads | `test_only_a_unit_the_rule_reads_is_accepted` (6) |
| G4-7 | a REQUIRED criterion without a deterministic rule | `test_a_required_criterion_without_a_deterministic_rule_is_refused` (3); `test_an_unregistered_code_is_treated_as_having_no_rule` |
| G4-7 | a soft criterion without a rule that sets `blocking_if_unknown` | `test_a_soft_criterion_without_a_rule_that_asks_to_block_is_refused` |
| G4-7 | a REQUIRED BUDGET_TARGET (soft only) | `test_budget_target_is_deferred_to_the_soft_score_and_never_required` |
| G4-3 (b) | a REQUIRED EQ/IN row disjoint from the REQUIRED column. Evidence §E's HOUSE_VILLA / APARTMENT is one of the cases; disjoint location subtrees and a transaction intent are covered too | `test_a_required_row_disjoint_from_the_required_column_is_refused`; `test_disjoint_required_location_subtrees_are_refused_nested_ones_are_not`; `test_a_required_transaction_intent_row_against_the_request_is_refused` |
| G4-5R | a RENT request's price criterion, with or without a budget | `test_a_rent_request_is_refused_naming_g4_5r` (3) |

**Evaluated, not refused (G4-3):**
- anything short of a provable contradiction
  (`test_anything_short_of_a_provable_contradiction_is_evaluated_both_ways`, 4);
- a stricter numeric row: both are evaluated, and the stricter one decides
  (`test_a_stricter_numeric_row_is_evaluated_and_prevails`).

**Soft criteria without a rule** are UNKNOWN and not blocking
(`test_a_soft_criterion_without_a_rule_is_unknown_and_not_blocking`, 4).

## 5. G4-4, the gates, and the actionable unknowns

**Blocking.** `blocking` is true when the result by itself keeps the
candidate from ELIGIBLE:
- a REQUIRED FAIL;
- a REQUIRED UNKNOWN, always;
- a soft UNKNOWN with `blocking_if_unknown`.

`test_blocking_is_g4_4` checks all 18 combinations against an independent
oracle.

**The gates:**
- **Hard gate** (§12.1, REQUIRED only): FAIL, else UNKNOWN, else PASS.
- **Information gate:** UNKNOWN if a blocking unknown exists, otherwise
  PASS. It is never FAIL.

**Actionable unknowns** (§13.1) are the blocking unknowns of a candidate
with no REQUIRED FAIL.

| Case | Test |
|---|---|
| C03 / mandatory test 3, at the gate: hard UNKNOWN, information UNKNOWN, actionable | `test_a_required_unknown_is_never_pass_or_fail_and_blocks` |
| G01 / M-01: a REQUIRED FAIL dominates; the unknown beside it is not actionable | `test_a_hard_fail_dominates_and_leaves_no_actionable_unknown` |
| soft FAIL and soft UNKNOWN decide nothing | `test_soft_criteria_never_decide_the_hard_gate` |
| `blocking_if_unknown` adds blocking | `test_blocking_if_unknown_adds_blocking_to_a_soft_criterion` |
| all PASS | `test_everything_passing_passes_both_gates` |
| a rule output the table cannot hold is refused | `test_a_rule_output_the_table_cannot_hold_is_refused` |

NEED_MORE_INFORMATION and REJECTED are eligibility values, and their
precedence is G4-11 (step 5). So:
- **Mandatory test 4** is a criterion fact, and it carries its planned
  name here.
- **Mandatory tests 3 and 5** are proven here at the gate and criterion
  level only. Their planned names come with step 5 (eligibility) and step 8
  (the DTO), which complete them.

## 6. Choices made in this step, stated for review

None of these adds a table, a column or a reason code.

1. **Criteria from the columns.**
   - An unset `desired_property_type` or `primary_location_id` states no
     criterion.
   - A null `budget_max_dzd` still yields a BUDGET_MAX criterion (G4-5: "max
     is null" gives UNKNOWN), unless a BUDGET_MAX row gives a maximum
     (`test_a_null_budget_column_yields_to_a_budget_row`).
   - TRANSACTION_INTENT is recorded as a REQUIRED criterion, so that it is
     reconstructable.
2. **Order and ordinals.** Columns first, then rows in the snapshot's order.
   The ordinal counts per code from 1
   (`test_columns_come_first_then_rows_and_ordinals_count_per_code`).
3. **`blocking` also marks a REQUIRED FAIL**, and not only unknowns, so the
   stored rows alone say what blocks.
4. **The hard gate can be UNKNOWN.** It is UNKNOWN when a REQUIRED criterion
   is UNKNOWN (§3.2: "a soft score never overrides a hard FAIL or UNKNOWN").
5. **Actionable** = blocking unknown on a candidate with no REQUIRED FAIL
   (§13.1).
6. **The option values `UNKNOWN` and `UNSPECIFIED_DOCUMENT` are UNKNOWN**,
   not values to compare (§11's own example; M-02).
7. **Reason codes.** Only seeded codes are used:
   - AREA_BELOW_PREFERENCE for any area FAIL. It is the seed's only area
     code, and its label says "preference".
   - No seeded code exists for a RIGHT_TYPE or a ROOMS/BEDROOMS FAIL, so the
     reason is null and `basis` names the outcome.
   - ACTIONABLE_UNKNOWN is not used on a criterion row, because
     actionability depends on the other criteria.
8. **Units.** Accepted units:
   - BUDGET_MAX: none or `DZD`;
   - areas: none, `m2` or `m²`;
   - counts: none.

   Anything else is refused.
9. **LOCATION** accepts EQ and IN, with values normalised to canonical uuid
   strings.
10. **G4-3 (b) literally.** Only a REQUIRED EQ/IN row against the REQUIRED
    column is refused. Two contradicting rows, or a NEQ/NOT_IN row, are
    evaluated, and every candidate then fails visibly.
11. **G4-5R: a RENT request is refused**, with or without a budget. This is
    the fail-closed default of acceptance condition 1. The alternative, the
    RENT price always UNKNOWN, is not a numeric verdict either. It is the
    reviewer's to choose (plan revision 7, G4-5).
12. **The property snapshot format becomes 2** (`location_ancestry`). This
    changes a step-2 artifact. No match row exists yet, so no stored hash is
    affected.

## 7. Raised

- **G4-18, decided (b) in the review of f789a59:** a REQUIRED `ROOMS_MIN`
  on a LAND property was a blocking unknown that could never be resolved.
  It is now FAIL (`count_min@2`, §10).
- **§3.4 corrected:** `match_criterion_results` has no `explanation`
  column. Where the explanation is stored is proposed with step 7.
- **A source fact for G4-5R:** red-team D01 writes "RENT 70k/month" for one
  offer. That is not a period for the budget.

## 8. Mutation evidence

*This section records the first round, at `3391c86`. The round after the
review of f789a59 is in §10.4.*

`db/dev/mutate_slice4_step4.py`: **52 mutations**:
- 25 in the rules;
- 15 in the refusals;
- 10 in the gates;
- 2 in the ancestry.

**52 of 52 fail**, and none survives.
- Recorded on a clean tree at `3391c86`, source fingerprint
  `02538087…c0c95` (`evidence/SLICE4-STEP4-MUTATIONS.txt`), baseline 147
  passed.
- Every mutated file was restored and verified by sha256.
- The trial run on the dirty tree also killed all 52. After it:
  - the rules were pinned;
  - two docstrings changed, the test module's and the package's.

  No test body and no rule changed.
- For the key mutations, the recorded causes are the intended assertions,
  for example:
  - R7 fails the price table's "exp ≤ max" row, and mandatory test 5;
  - R12 fails on the leaked value;
  - C12 fails with "DID NOT RAISE CriterionRefused";
  - H6 fails with an actionable unknown on a rejected candidate.

**Left out:** removing the ancestry query's cycle guard. Its failure mode is
non-termination, which the runner cannot observe. The guard is tested
directly by `test_location_ancestry_is_nearest_first_and_survives_a_cycle`.

## 9. What remains

- **Step 5** (freshness, permission, eligibility): G4-10 and G4-11 were
  decided in the review of f789a59. Step 5 starts only after this step is
  closed.
- **G4-5R:** the rent period is open. The interim refusal is approved.

## 10. The review of f789a59: three defects, and G4-18 (b)

The reviewer checked:
- the archive digest and the manifest;
- the source fingerprint `02538087…c0c95`;
- `run_binding.py` (`bound`).

They then probed the functions directly, without a database, for the
first two findings. They did not re-run PostgreSQL.

### 10.1 Measured before the fix

`evidence/SLICE4-STEP4-REVIEW-BEFORE-FIX.txt`: the review's tests, run on
PostgreSQL against the production code exactly as at `f789a59` (the tree
differed by the test file only).
- **27 failed.**
- **9 passed.** Those are the cases whose old behaviour was already right:
  - a passable set;
  - a valid target deferred;
  - a reason code at the importance its label names;
  - an applicable count not recorded.

### 10.2 The three defects, and what changed

**1. A requested value no property can PASS was accepted (G4-7).**
- `DOCUMENT_TYPE EQ UNKNOWN`, `EQ UNSPECIFIED_DOCUMENT` and `RIGHT_TYPE EQ
  UNKNOWN` were accepted. A property holding that value is UNKNOWN, and any
  other value is FAIL, so no property could PASS.
- Now `criteria._can_pass` refuses, at any importance, a set criterion whose
  passable values are empty: "no property value can satisfy it". The passable
  values are:
  - the domain (the enum; or the active options minus
    `NOT_KNOWN_OPTIONS`), within an EQ/IN set;
  - or the domain outside a NEQ/NOT_IN set.
- This also refuses `IN` of not-known values only, `PROPERTY_TYPE NOT_IN` all
  seven types, and `TRANSACTION_INTENT NOT_IN [BUY, RENT]`.
- *Superseded in §11:* this round also refused `NOT_IN` of every ACTIVE
  document type. That refusal was the contradiction the review of ba5f25e
  found, because a property can hold a retired option.
- An IN set holding one passable option is accepted, as the review asked.
  So are `NEQ UNKNOWN` and `NOT_IN [UNKNOWN, UNSPECIFIED_DOCUMENT]`
  (`test_a_set_with_a_passable_known_option_is_accepted`).
- `test_not_known_options_are_exactly_those_the_rule_calls_unknown` runs
  every active option through `attribute_option@2`. It proves that
  `NOT_KNOWN_OPTIONS` is exactly the set the rule calls UNKNOWN, so the two
  cannot drift apart.
- Choice 6 of §6 is thereby bounded on the request side, as the review
  asked. The property side is unchanged.

**2. A deferred row skipped validation (G4-7).**
- A PREFERRED BUDGET_TARGET row was deferred as it was, even with IN, an
  object value, unit HOURS, or `blocking_if_unknown`.
- Now a deferred row passes the same `_read_value` as every other row:
  - operator EQ only. The target is a point: G4-12 uses `|ask − target|`;
  - a whole, non-negative DZD amount;
  - unit none or `DZD`.
- `blocking_if_unknown` on it is refused: the flag has no meaning until its
  rule exists (step 6). This is the first of the two remedies the review
  offered.
- Tests: `test_a_deferred_budget_target_is_validated_before_it_is_deferred`
  (6) and `test_a_valid_budget_target_row_is_deferred_with_its_value_read`.

**3. Reason codes that name another importance.** Three seeded labels name
an importance (seed lines 135, 141, 142):
- "Required location mismatch";
- "Required document mismatch";
- "Area below preference".

Version 1 emitted these codes at every importance. Now:
- **Version 2 of `location`, `attribute_option` and `area_min`** emits each
  such code only at the importance its label names. Otherwise the reason is
  null, and `basis` names the outcome:
  - `test_an_area_fail_carries_the_preference_code_only_when_soft`;
  - `test_a_location_fail_carries_the_required_code_only_when_required`;
  - `test_a_document_fail_carries_the_required_code_only_when_required`.

  Each is tested at REQUIRED, PREFERRED and FLEXIBLE.
- **A backstop in `hard_gate`:** a rule output whose reason code names
  another importance is refused (`test_a_rule_output_naming_another_importance_is_refused`).
- **The table `REASON_IMPORTANCE` is derived from the labels in the
  database** (`test_the_importance_of_each_reason_code_is_its_seeded_label`).
- Choice 7 of §6 is corrected accordingly.

### 10.3 G4-18 (b), decided in the same review

- **`count_min@2`, beside version 1:**
  - an attribute that cannot apply to the property's type is FAIL, with
    basis ATTRIBUTE_NOT_APPLICABLE and a null reason;
  - an applicable attribute that is not recorded stays UNKNOWN.
- **The property snapshot, format 3,** records `attribute_applies_to` for
  every attribute code.
- **Replay:**
  - `test_applicability_replays_from_the_snapshot_after_the_definition_changed`
    extends ROOMS to LAND after the snapshot. The stored snapshot still gives
    FAIL, and a fresh one gives UNKNOWN.
  - A snapshot without applicability is refused
    (`test_count_min_2_refuses_a_snapshot_without_applicability`).
- **G4-2:** four rules gained version 2, and every version 1 stays
  registered and pinned.
  - No match row exists before step 7, so no stored match cites version 1.
  - `criteria.RULES` selects version 2
    (`test_version_2_is_used_and_version_1_stays_registered_beside_it`).
  - Replayed today, version 1 of `location`, `attribute_option` and
    `area_min` would be refused by the new backstop, because their reason
    codes were the defect.

### 10.4 Mutation evidence, second round

- **68 mutations.** The first round's 52, plus:
  - R26–R30: G4-18 and the importance of reason codes;
  - C16–C24: satisfiability, deferred validation, versions in use;
  - H11: the backstop;
  - S3: applicability.
- **R23, C3 and C5** were re-anchored on the new code.
- **A survivor in the trial run, and its cause.** R22 "survived". Its anchor
  matched only `attribute_option@1`, which no evaluation selects (1 site).
  Re-anchored on version 2, it is killed.
  - `tests/test_slice4_mutation_anchors.py` now fails whenever a rule
    mutation reaches no version in use.
  - It was shown to fail on R22's old anchor, and to pass on the corrected
    one.
  - It runs in the full suite, not in the mutation run, where it would kill
    every rule mutation for the wrong reason.
- **Clean-tree result: 68 of 68 fail, and none survives.**
  - Recorded at `1805eef`, source fingerprint `145a8bf8…27280`, baseline
    188 passed (`evidence/SLICE4-STEP4-MUTATIONS.txt`).
  - Every mutated file was restored and verified by sha256.
  - The first round's record (52/52 at `3391c86`) is superseded, and stays
    in git history.

### 10.5 Decisions recorded (plan revision 8)

- **G4-5R:** the interim refusal is accepted. The period is still open.
- **G4-18:** (b).
- **G4-10:** as proposed. A valid PUBLIC_LISTING_ALLOWED binding counts for
  internal matching of the same bound resource, and grants no new sharing.
- **G4-11:** as proposed. A missing or revoked permission stays visible in
  the diagnostic, even under NEEDS_CONFIRMATION.
- **§6 choices:** 1–5, 8–10 and 12 accepted as described. Choice 6 is
  bounded on the request side. Choice 7 is corrected. Choice 11 is accepted
  provisionally, under G4-5R.

## 11. The review of ba5f25e: the pre-check and the rule judged different domains

**The finding.**
- `_can_pass` took the option domain from the options ACTIVE now.
- `attribute_option@2` compares whatever value the property holds.
- The schema lets a property keep a value whose option was deactivated.

So the pre-check could refuse, as unsatisfiable, a criterion that a real
property passes.

### 11.1 Measured before the fix

`evidence/SLICE4-STEP4-REVIEW2-BEFORE-FIX.txt`, on the `ba5f25e` production
code.

1. **On PostgreSQL:** `test_a_retired_option_held_by_a_property_gets_the_same_verdict_from_both`.
   - OTHER is written through the Slice 3 validator while it is active.
   - Every document type but LAND_BOOK is then deactivated, and OTHER is
     deactivated, or **deleted**.
   - For `DOCUMENT_TYPE NOT_IN [LAND_BOOK, UNKNOWN]`, the rule gives the
     property PASS, and the pre-check refuses. **Both variants failed.**
2. **Exhaustively**, with the seed's active vocabulary, over 68 criteria:
   **4 disagreements**.
   - All four are EQ/IN on a value no option names. `criteria_of` never
     reaches the pre-check with them, because a request may name only
     active options.
   - They are recorded because they show the two domains differed. The
     reachable contradiction is case 1.

### 11.2 The path taken, and its meaning

The reviewer's first path, "a retired option stays comparable in the
pre-check", taken to its consequence: **the option domain is open**.
- **What the schema says.**
  - `attribute_options.active` (schema line 181) is read only when a value
    is written (`truth.validate_attribute`).
  - `property_attributes.value` is `jsonb` and references no option.
  - No table references an option row. An option can be deactivated, and
    deleted too; the second variant of the test deletes one.
- **The meaning adopted.**
  - `active` governs what may be NEWLY recorded or requested.
  - A recorded value keeps its meaning after its option is retired, and the
    rule compares it like any other.
  - A request may still name active options only (`_normalise`, unchanged).
- **`criteria.can_pass`** (public, documented) therefore judges the rule's
  own domain:
  - option codes: an EQ/IN is refused exactly when every value is in
    `NOT_KNOWN_OPTIONS`; a NEQ/NOT_IN is never refused;
  - enum codes (PROPERTY_TYPE, TRANSACTION_INTENT): a closed domain, as
    before.
- **Agreement is proven, not assumed.**
  `test_the_pre_check_refuses_exactly_what_the_rule_can_never_pass` runs
  every EQ/NEQ/IN/NOT_IN over a pool of known, not-known and unregistered
  values (68 criteria). `can_pass` accepts exactly when some property value
  gets PASS from `attribute_option@2`. No vocabulary is read, so no state
  of `attribute_options` can make them disagree.
- **Consequence:** `NOT_IN` of every ACTIVE document type is now accepted
  (`test_not_in_every_active_document_type_is_accepted_because_the_domain_is_open`).
- **The path not taken,** "the rule treats a retired option as UNKNOWN":
  - a recorded fact would become a blocking unknown whenever an entry
    vocabulary changes;
  - it would need the activity state in every property snapshot, and a new
    rule version.
- **No rule changed, and no pin changed.**

### 11.3 A limit stated (plan revision 9, G4-2)

Version 1 of `location`, `attribute_option` and `area_min` stays registered
and pinned. Some of its outputs would be refused by the new reason-code
backstop, and no stored match cites it. It must not be offered as evidence
of historical replay at step 7 or 8. A replay proof covers only the
versions stored matches cite.

### 11.4 Mutations

- C16 and C17 are re-anchored on `can_pass`.
- Added:
  - **C25:** the option NEQ/NOT_IN judged on a closed domain again. It is
    killed by both variants of the PostgreSQL test and by the exhaustive
    agreement test.
  - **C26:** an option criterion judged on the enum branch.
- The clean-tree result is in `evidence/SLICE4-STEP4-MUTATIONS.txt`.
