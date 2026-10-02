# Slice 4 · step 6 — the soft score, and the pinned gates

**Status: CLOSED at `ee7fbc0`** (review of ee7fbc0). The review of 0cf6a7a
decided the column target's weight (option (a)), and it is applied in
**§9**. §9 supersedes §4, the S1 mutation of §6, and the remaining items of
§7. Step 7 waits on G4-15, detailed for decision in the plan's revision 13.

**Authorised:** the review of a5ea6f5 closed step 5 and allowed step 6 under
these decisions:
- **Pin** the logic of the freshness and permission gates and the
  eligibility precedence before step 7 writes matches. It may take an
  identity and a version of its own, provided its digest enters the input
  hash, and earlier versions stay replayable.
- **G4-12:** the plan's model, with its edge cases settled (§2).
- **PERMISSION_MISSING:** kept with its basis. Its seeded label is not
  presented as an exact explanation of a missing binding.
- **G4-5R:** the RENT refusal stays in force. RENT matching stays outside
  this step.

**Basis:**
- `docs/gate/SLICE_4_PLAN.md` revision 11: G4-2 (extended), G4-7, G4-12,
  G4-13;
- Developer Spec §12.1 ("no soft score overrides a hard FAIL"), §12.2;
- plan §3.2;
- mandatory test 2;
- `enforce_approved_review_gate` (`schema_v0.2.3.sql:856–873`).

**Nothing is written.** `test_scoring_writes_nothing` checks this. The
engine writes no match row; the mandatory test's schema half writes fixture
rows inside the rolled-back session.

## 1. The gates are pinned

**`gates.py` holds six registered functions**, each under its own id and
version. They are in the same `REGISTRY` as the criterion rules, but they
are not criterion rules:

| id@version | What |
|---|---|
| `freshness.state@1` | one subject's freshness (G4-11) |
| `freshness.gate@1` | the freshness gate and its reasons |
| `permission.binding_state@1` | one binding's state (G4-10) |
| `permission.gate@1` | the permission gate and its reasons |
| `eligibility.precedence@1` | G4-11's precedence, every reason kept |
| `score.soft@1` | G4-12 |

**The review's conditions:**
- **Own identity and version:** each function above has its own
  `(id, version)`.
- **The digest enters the input hash:** `REGISTRY.digest()` covers them, and
  it is an input of the hash (G4-13).
  `test_a_change_to_a_gate_changes_the_registry_digest_and_so_the_hash`
  rebuilds the registry with `eligibility.precedence@1` replaced by a
  different source: the digest differs.
- **Earlier versions stay replayable:** G4-2's mechanism applies. A change
  is a new version beside the old one, and the pins (18 now) make an edit
  without a version bump fail
  (`test_the_production_registry_agrees_with_the_committed_pins`).

**Recorded with each result**, for step 7 to store:
- the freshness snapshot's `derived_by` (`freshness.state@1`);
- the permission snapshot's `derived_by` (`permission.binding_state@1`);
- `Eligibility.engine`, the three gate and precedence versions;
- `SoftScore.engine` (`score.soft@1`).

Both snapshot formats are now 2.

**Self-contained** (`test_every_registered_function_is_self_contained`): no
registered function calls a helper or reads a module constant. Beyond the
builtins they read only these stable names: `Decimal`, `Fraction`,
`datetime`, `timedelta`, `timezone`.

**Registered without help** (`test_the_engine_registers_every_pinned_function_on_its_own`).
- A fresh interpreter, importing only what the engine imports, finds every
  pinned function, and the pins agree.
- This test exists because mutation K4 first survived: the test module
  imports `gates` itself, which hid a registry that did not.

**The move preserved behaviour.**
- Step 5's 122 tests pass unchanged.
- Step 5's 32 mutations were re-anchored into `gates.py`, each
  reintroducing the same defect, and re-run: **32 of 32 still fail**
  (`evidence/SLICE4-STEP5-MUTATIONS.txt`, re-recorded).
- Step 4's self-containment test now checks the `criterion.*` rules
  only; this step checks the rest.

## 2. The soft score (G4-12), as decided

`score.soft@1`; `soft.py` gathers its inputs.

| Decision | Implementation | Test |
|---|---|---|
| PREFERRED = 2, FLEXIBLE = 1 | `weight_of` | `test_weights_and_contributions` (6) |
| PASS gives the full weight; FAIL or UNKNOWN gives 0 | contribution 1 / 0 | same |
| BUDGET_TARGET contributes `1 − min(1, \|ask − target\| / target)` | an exact fraction on the ASKING price | `test_a_budget_target_contributes_its_proximity` (7) |
| a zero target gives 1 for a zero price, 0 for a positive one | | same |
| a missing asking price gives 0 | basis PRICE_NOT_KNOWN | same |
| a target weighted by its importance | | `test_a_target_is_weighted_by_its_importance` |
| null unless the hard gate is PASS | basis HARD_GATE_NOT_PASS | `test_no_score_unless_the_hard_gate_passes` (2) |
| null without a soft criterion | basis NO_SOFT_CRITERION | `test_no_score_without_a_soft_term` |
| the weighted share, six places | exact fraction, rounded once, half up | `test_rounding_is_half_up_like_postgresql_numeric` |
| `seller_expectation_dzd` outside | never read | `test_the_seller_expectation_is_never_read` |

**Rounding.** The share is computed as a fraction and rounded once to six
places, half up, which is how PostgreSQL rounds into `numeric(7,6)`.
- The test compares the score with PostgreSQL's
  `round(n::numeric / d, 6)` in four cases, one of them an exact half
  (0.0000005 → 0.000001, where half-even would give 0).
- No decimal context is involved.
- `test_the_score_fits_the_column` shows the value is stored unchanged.

**Two consequences of approved decisions, stated:**
- A soft criterion without a deterministic rule carries no weight, as
  decided in G4-7. So does a REQUIRED one: it belongs to the hard gate.
- A target on a non-SALE offer is refused (G4-5R), as the SALE price rule
  already is (`test_a_target_on_a_rent_offer_is_refused`).

**Terms.** Each candidate's terms (kind, criterion or source, weight, and
the contribution as an exact `"n/d"`) are returned for `explanation`, as
G4-12 says. A target gets no `match_criterion_results` row: its proximity is
not a PASS, FAIL or UNKNOWN, and inventing one would be a decision.

## 3. Mandatory test 2, completed with its planned names

- **The engine half: `test_a_hard_fail_is_rejected_whatever_the_soft_score`.**
  - Every soft criterion of the candidate passes, and its target is met
    exactly. A REQUIRED document mismatch still makes it REJECTED, with no
    score.
  - With the right document, the same candidate is ELIGIBLE with 1.000000.
- **The schema half: `test_the_schema_refuses_to_approve_a_rejected_match`.**
  `enforce_approved_review_gate` refuses an APPROVED review of a REJECTED
  match.

## 4. Raised: one case G4-12's decision does not give

**The request's own `budget_target_dzd` column has no importance of its
own.** `budget_importance` is the maximum's, and G4-12 gives weights by
importance, so the column has no weight. Under acceptance condition 1, a
request carrying it is **refused, naming G4-12**
(`SoftScoreUndecided`), whatever its hard gate says
(`test_the_request_target_column_is_refused_until_its_weight_is_decided`).

**Options for the reviewer:**
- (a) weigh it as PREFERRED (2);
- (b) weigh it as FLEXIBLE (1);
- (c) weigh it by `budget_importance` when that is PREFERRED or FLEXIBLE,
  and refuse when it is REQUIRED, since a target cannot be a hard
  criterion;
- (d) keep the refusal.

**No recommendation is made.** None of the options follows from a source.

A BUDGET_TARGET row carries its own importance, and is scored.

## 5. PERMISSION_MISSING

The decision binds the display, which comes in steps 7 and 8.
- `permission.gate@1` emits the code with a basis: `NO_CURRENT_BINDING` or
  `NOT_STARTED`.
- Its docstring records that the seeded label is not an exact reading.
- The plan's G4-10 section records the display rule.

## 6. Mutation evidence

`db/dev/mutate_slice4_step6.py`: **19 mutations**:
- **G1–G13** on the soft score: the weights, the contributions, the edge
  cases, rounding, the expectation, and RENT;
- **S1–S2** on `soft.py`: the column refusal, and the targets given to the
  formula;
- **K1–K4** on the pinning: the versions recorded, and the registry.

The trial run killed 18. **K4 survived**, for the reason in §1, and the
fresh-interpreter test now kills it.

**Clean-tree result: 19 of 19 fail, and none survives.**
- Recorded at `bb55a67`, source fingerprint `336180a3…2582a`, baseline 30
  passed (`evidence/SLICE4-STEP6-MUTATIONS.txt`).
- Every mutated file was restored and verified by sha256.

**Step 5's 32 mutations, re-anchored, were run on the same clean tree:
32 of 32 fail.** That record replaces step 5's file, and the earlier record
(at `02b9898`) stays in git history.

## 7. What remains

- **Step 7** (the run: persistence, audit, the diagnostic row, concurrency)
  waits on **G4-15**.
  - It must store each result's versions (§1).
  - It must word PERMISSION_MISSING from its basis.
- **The column target's weight** (§4) is open.
- **G4-5R:** the rent period is open, and the refusal is in force.

## 9. The review of 0cf6a7a: the column target weighs as PREFERRED

**The decision, option (a).** This is an explicit product decision, not an
inference from the contract.
- **The request's `budget_target_dzd` column is a PREFERRED criterion, of
  weight 2.**
- **`budget_importance` stays the maximum's**, and is never carried over to
  the target.
- **The column is its own term** in the explanation (source COLUMN, weight
  2).
- **A BUDGET_TARGET row beside it stays a separate term**, with its own
  weight. The two are never merged.

### 9.1 Measured before the fix

`evidence/SLICE4-STEP6-REVIEW-BEFORE-FIX.txt`, on the `0cf6a7a` production
code:
- **six PostgreSQL cases** fail with `SoftScoreUndecided` (G4-12), the
  refusal the first round was built to give;
- **the seventh** fails because `score.soft@2` does not exist yet.

**A first measurement was discarded, and the record says so.** Its fixtures
used a 40,000,000 column target above the request's 30,000,000
`budget_max_dzd`. The schema's CHECK (`budget_target_dzd <= budget_max_dzd`,
`schema_v0.2.3.sql:385`) refused those rows, so the failures were the
fixture's, not the defect's. The target is now 16,000,000.

### 9.2 Applied as `score.soft@2`, beside version 1

`score.soft@1` is pinned, so it is not edited (G4-2). `score.soft@2`:
- is version 1 with one change: a target whose source is COLUMN weighs 2,
  whatever `budget_importance` says;
- states `weight_basis` on every target term: `COLUMN_AS_PREFERRED` for the
  column, `IMPORTANCE` for a row.

Around it:
- `soft.py` runs version 2, and the refusal is removed.
- Version 1 stays registered with its pin unchanged. It never received a
  column: the first round refused one before calling it.
- Both versions' digests enter the registry digest, and so the input hash.
  The pins number 19.

| Case | Test |
|---|---|
| the column alone: (2 + 1 + 2 × 3/4) / 5 = 0.900000, one COLUMN term of weight 2 | `test_the_target_column_alone_weighs_as_preferred` |
| the column and a row: two separate terms (COLUMN 2 × 3/4, ROW 2 × 1), 13/14 = 0.928571, each with its own source, id and weight basis | `test_the_target_column_and_a_target_row_are_two_separate_terms` |
| `budget_importance` REQUIRED, PREFERRED or FLEXIBLE: the column still weighs 2 | `test_budget_importance_never_moves_to_the_target` (3) |
| a hard FAIL: no score, column or not | `test_the_column_target_gives_no_score_when_the_hard_gate_fails` |
| version 1 registered with its pin; version 2 used | `test_version_1_of_the_score_stays_registered_and_version_2_is_used` |

### 9.3 Mutations

- **Retired:** S1 (the refusal is gone).
- **Added:**
  - **S1:** version 1 run again;
  - **G14:** the column weighs 1;
  - **G15:** the column dropped;
  - **G16:** its weight basis not stated.
- **G13** is re-anchored on version 2. Its old text now exists only in
  version 1, where a mutation would prove nothing.
  `tests/test_slice4_mutation_anchors.py` now guards every `gates.py`
  mutation of steps 5 and 6, as it already guarded the step-4 rules. It was
  shown to flag G13's old anchor, which reaches only `soft_score_v1`.
- **Clean-tree result: 22 of 22 fail, and none survives.**
  - Recorded at `7b09da3`, source fingerprint `401ce897…e2577`, baseline 36
    passed (`evidence/SLICE4-STEP6-MUTATIONS.txt`).
  - Step 5's 32 mutations were run on the same tree: 32 of 32 fail.
  - The first round's records (at `bb55a67`) stay in git history.

### 9.4 What remains

- **Step 7 waits on G4-15.**
- **G4-5R:** the RENT refusal stays in force.
