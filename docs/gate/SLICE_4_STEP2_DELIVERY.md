# Slice 4 · step 2 — the canonical form, the input hash, the rule registry, the policy loader, the snapshots

**Authorised:** the review of 95f0732 closed step 1 and allowed step 2 "under
the recorded decisions G4-2 and G4-13". Later steps still wait on their own
decisions.

**Basis:**
- `docs/gate/SLICE_4_PLAN.md` revision 3: G4-2 and G4-13 with their
  conditions, §3.1, §3.3, §3.4 and §8 step 2;
- `API_CONTRACTS_v0.2` §6;
- ADR-02.

**What this step does NOT do.**
- It generates no candidate, evaluates no gate, and writes no match row.
  The matching package contains only SELECTs, and a test asserts it
  (`test_the_matching_package_reads_and_never_writes`).
- It does not read `party_property_relations`, and a test asserts that too.
- The production rule registry is **empty**. The criterion rules are step
  4, and wait on G4-3 to G4-7.

## 1. The canonical form and the input hash (G4-13)

`src/turab/matching/canonical.py`.

| Rule | Proven by |
|---|---|
| keys sorted, no whitespace, UTF-8 without ASCII escaping | `test_key_order_does_not_change_the_bytes`; `test_arabic_is_hashed_as_written_and_a_bool_is_not_an_integer` |
| **no float anywhere**, at any depth | `test_a_float_is_refused_wherever_it_is` (4 cases) |
| a Decimal is written **by value** (`268.50` = `268.5` = `2.685E+2`; `-0` = `0`; `100`, not `1E+2`); non-finite refused | `test_decimals_are_written_by_value`; `test_a_non_finite_decimal_is_refused` |
| one instant, one string: UTC with microseconds and `Z`; a naive datetime refused | `test_one_instant_gives_one_string_whatever_its_zone`; `test_a_naive_datetime_is_refused` |
| a non-string key, or an unknown type, is refused, never stringified | two tests, 5 cases |
| the form is pinned by a golden vector | `test_the_canonical_form_is_pinned` |

**The input document** holds:
- `format`;
- the policy id and version;
- `rule_registry_digest`;
- **`evaluated_offer_id` as a top-level element**, the condition of the
  review of aad9f34;
- the five snapshots.

`input_hash` is sha256 over its canonical bytes.
`test_the_input_hash_is_the_sha256_of_this_exact_document` writes that
document **by hand** and compares hashes. It pins the set of inputs and
their form, not only a value the code produced.

- **Every input changes the hash** (10 cases, `None` offer included).
- **Two offers on identical terms hash differently.** The two commercial
  snapshots are made IDENTICAL on purpose, so the difference can come only
  from the top-level `evaluated_offer_id`.
- `evaluated_at` and `input_hash` are refused as inputs, at any depth. So an
  identical run gives an identical hash (G4-13: the existing match is
  returned). No input can be omitted: the arguments are required and
  keyword-only.

**The two tests the review required** run against the real uniqueness
constraint, with fixture match rows hashed by the real functions from the
real snapshots:
1. `test_two_offers_on_identical_terms_give_two_independent_match_rows`:
   both rows insert under `UNIQUE(request, property, policy, input_hash)`;
2. `test_the_same_offer_on_the_same_state_hashes_identically_and_cannot_be_stored_twice`:
   the second insert fails on the unique key.

What the RUN does with that second case (return the existing match, write
nothing) is the run operation, in step 7. It is tested there, over HTTP.

## 2. The rule registry (G4-2)

`src/turab/matching/registry.py`, `src/turab/matching/rule_pins.py`,
`db/dev/pin_rules.py`.

**How the condition of the review is met: "every cited version stays
replayable".**
- The registry is keyed by **(rule_id, rule_version)**. A new version is
  registered BESIDE the old one, and a second implementation of an existing
  pair is refused. Both versions resolve and behave as written
  (`test_a_new_version_is_registered_beside_the_old_and_both_resolve`).
- **The pins.** `rule_pins.py` maps `rule_id@version` to the sha256 of that
  rule's source. `verify_pins` reports three things:
  - a rule changed without a version bump;
  - a version that is not pinned;
  - **a pinned version that is no longer implemented**, whose matches could
    then no longer be replayed.

  Each case has its own test. The standing guard is
  `test_the_production_registry_agrees_with_the_committed_pins`.
- **The pin tool only adds.** It refuses, and writes nothing, when a pinned
  source changed or a pinned version vanished
  (`test_the_pin_tool_only_adds_and_refuses_to_move_a_pin`).
- **The pins file is Python, not JSON**, so the source fingerprint (which
  covers `.py`) binds every run to its pins. It is read with
  `ast.literal_eval`, never executed. An expression in it is refused.
- **The digest** covers every version's source. It is an input of the
  hash, so a run under different rule code is a different input.

**Stated limit.** The source digest covers the rule function's own text. A
helper it calls is not covered unless it is itself registered. The step-4
rules will be written to that constraint.

**Found and fixed during the step:**
- **`load_pins` bound its default path when the function was defined**, so
  the pin tool read the real file even when pointed elsewhere. The tool's
  own test failed on this; the path is now resolved at call time. Mutation
  S22 restores the old behaviour and is killed.
- **A survivor in the trial mutation run: S13, "the digest ignores the
  source".** No test compared the SAME pair with different source. That
  matters, because the digest is a hash input.
  `test_the_digest_changes_when_a_rule_source_changes_under_the_same_version`
  was added, and S13 is now killed. The trial run, on a dirty tree, is kept:
  `evidence/SLICE4-STEP2-MUTATIONS-TRIAL.txt`.

## 3. The policy loader (§3.1) and CORRECTION-004's rule

`src/turab/matching/policy.py`.

**`load_active_policy` refuses a policy this engine does not implement**
(`PolicyNotImplemented`):
- `automatic_request_relaxation` true or absent;
- `human_review_required_for_opportunity` not true;
- any hard-gate mapping other than 0.2.0's.

With no active policy, it refuses rather than defaulting. The variants are
NEW policies, activated in place of 0.2.0, because 0005 makes 0.2.0
immutable.

**`require_active_version`** is CORRECTION-004's runtime rule. It accepts
only the active version. `None`, `0.1.0`, an inactive version, a
non-string and `"0.2.0 "` are refused, without echoing the value. The route
that answers 422 is step 7.

## 4. The snapshots (§6)

`src/turab/matching/snapshots.py`.

| Snapshot | Delivered | Proven by |
|---|---|---|
| request | id, version, intent, stage, budgets and flexibility, type and location with importances, confirmation time, and **all criteria in a total order** | `test_the_request_snapshot_is_complete_exact_and_ordered`; the same state gives the same bytes, and a changed criterion gives different bytes (C04's basis) |
| property | areas as `Decimal`, availability and its time, supply mode, **identity** (`is_alias`, canonical id), **all current attributes with their claim and evidence level** | `test_the_property_snapshot_records_areas_attributes_evidence_and_identity`, built through the real HTTP flow (claim, CONFIRMED verification, resolution, CONFIRMED_SAME) |
| commercial (offer) | the offer's commercial fields, including the internal `seller_expectation_dzd` (R9.3) | `test_the_commercial_snapshot_carries_the_internal_expectation` |

**Two choices, stated for review:**
- **All current attributes are recorded**, not only "those used by rules".
  Which attributes a rule reads is G4-3. A superset decides nothing, and
  lets a reviewer see all the engine could see.
- **jsonb is read as text**, and every JSON number is parsed as `Decimal`.
  psycopg's default JSON loader yields floats, which the canonical form
  refuses.

**Not delivered, each waiting on its decision:**
- the permission snapshot (G4-10);
- the freshness snapshot (G4-11);
- the context of a POTENTIAL property without an offer (G4-9).

## 5. Evidence

Recorded in this round, on a clean tree:
- `SLICE4-STEP2-MUTATIONS.txt`: 22 mutations, each failing at least one
  test;
- the matrix, the gate and the bound test run.

## 6. Also in this round

The review of 95f0732 noted that the step-1 note opened by calling G4-2 and
G4-13 open, contradicting its §5. The first paragraph is corrected
(`SLICE_4_STEP1_DELIVERY.md`).
