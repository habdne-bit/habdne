# Slice 3 · step 4 — availability, the staleness pass, offer freshness

**Basis:**
- `docs/gate/SLICE_3_PLAN.md` §3.3 (G3-3, ratified) and §3.4 (ratified);
- the test names in §6.2;
- the contract's `postPropertiesPropertyIdReconfirm` and
  `postOffersOfferIdReconfirm`.

No table, column, migration, reason-code category or policy was added. The
thresholds come from the seeded active policy:

    freshness_threshold_days: {request: 30, property: 30, offer_terms: 14}

## 1. What each ratified rule became

| Rule | Mechanism | Proving tests |
|---|---|---|
| §3.3 r1: any value → any value | no transition table | `test_reconfirm_moves_between_any_two_availability_values`, all 42 ordered pairs |
| §3.3 r2: the value is stated | `availability` required and never null | `test_reconfirm_requires_an_explicit_availability`: absent, `null`, and body with `confirmed_at` only |
| §3.3 r3: time, actor, channel, provenance | `availability_last_confirmed_at`; a provenance claim with the previous value, actor, channel and `notes` | `…stamps_time_actor_channel_and_provenance`, `…staff_reconfirmation_is_recorded_as_staff` |
| PATCH does not change availability | `PropertyPatch` is closed | `test_patch_cannot_change_availability` (step 1), `…patch_cannot_change_availability_and_reconfirm_is_the_path` |
| §3.3 r4: the pass converts **four** values only | `STALE_CONVERTIBLE`, a predicate in the `UPDATE` | `test_the_sweep_converts_each_of_the_four_named_values` (4 cases) |
| … and never `UNKNOWN`, `NEEDS_CONFIRMATION`, `UNAVAILABLE` | the same predicate | **three separate tests, one value each** |
| the threshold is the policy's | `freshness.property_threshold_days`; no default | `…reads_the_threshold_from_the_active_policy` (29 days fresh, 31 days stale) |
| §3.4: `offer_terms` on `commercial_terms_last_confirmed_at` | `freshness.evaluate_offer` | `test_offer_staleness_is_measured_on_commercial_terms_last_confirmed_at`, `test_a_stale_offer_is_reported_stale_on_its_commercial_terms_clock` |
| §3.4: reconfirm writes both columns together | one `UPDATE`, one instant | `test_reconfirming_an_offer_updates_both_confirmation_columns`, `…stated_confirmation_time_is_written_to_both_columns` |
| §3.4: no offset → refused on **this** endpoint | validator on `StateReconfirm` | `test_a_confirmation_without_a_timezone_is_refused_on_the_offer_endpoint` |
| no policy value → refused | `NoActiveFreshnessPolicy` | `…policy_without_an_offer_terms_threshold_is_refused_not_defaulted` |

**Also delivered:**
- A confirmation time in the future is refused; a historical one is stored
  as stated.
- A refused reconfirm consumes no idempotency key.
- A customer is refused on a property or offer that is not theirs (404).
- F-2 applies to property reconfirmation: an identity alias is refused with
  409.
- Offer reconfirmation changes neither the terms nor the state. The offer
  machine (§3.5) has no edge that a confirmation takes.

## 2. Choices within the ratified rules, stated so they can be reviewed

1. **A never-confirmed availability is not stale.** `NULL` in
   `availability_last_confirmed_at` is not converted: the value has not gone
   out of date, it was never put in date. This is the rule the REQUEST pass
   already applies. Test: `test_a_never_confirmed_availability_is_not_stale`.
2. **The pass is not a confirmation.** It changes `current_availability` and
   never `availability_last_confirmed_at`, and writes no provenance claim.
   The audit trigger on `properties` records it with
   `context.operation = "freshness-pass:property"`.
3. **It is not scheduled.** It runs when
   `db/dev/run_freshness_pass.py --kind property` is run, exactly like the
   request pass (`--kind request`, the unchanged default). Nothing in this
   version schedules either pass.

## 3. The write-time re-check: what is proven, and what is not

### 3.1 Correction (review of `0db04c4`)

The first version of this section said the re-check was "proven by the
concurrency tests, which fail when the row lock is removed (M4)". That
attributed too much.

- **The flaw.** The old harness made the holder's COMMIT wait for the pass
  to FINISH. With the lock removed, the pass waited for the holder's row
  while the holder waited for the pass.
- **What M4 showed.** The test failed by **timeout**, so the failure showed
  a mutual wait, not that any predicate had protected the value. It proved
  the no-wait skip and that the pass does not touch a still-locked row;
  nothing more.

### 3.2 The experiment that replaces it

`test_which_mechanism_protects_a_concurrent_reconfirmation` (in
`tests/test_slice3_step4.py`) works as follows:

- **Holder:** reconfirms the property and holds the row lock, uncommitted.
- **Pass:** runs the staleness SQL.
- **Witness:** releases the holder as soon as the pass has **finished**, or
  PostgreSQL reports it **blocked by the holder** (`pg_blocking_pids(pass)`
  contains the holder's pid). The holder's commit never depends on the pass
  finishing.
- **Recorded:** each run records whether the pass **waited**, whether it
  **wrote** the row, and the **final** value. These facts are saved as JUnit
  properties in `junit-run.xml`.

The same experiment runs over five controlled variants of the pass's own SQL
(`_STALE_AVAILABILITY_SQL`). Each variant is checked to differ from the
production text, and each is run with a concurrent `AVAILABLE` and a
concurrent `UNAVAILABLE`:

| Variant | Waited | Wrote | Value kept | What protected it |
|---|---|---|---|---|
| `production` | no | no | yes | `SKIP LOCKED` skipped the locked row |
| `for_update_without_skip` | yes | no | yes | `FOR UPDATE` re-evaluated the subquery `WHERE` after the wait |
| `no_lock` | yes | no | yes | **the outer re-asserted predicate**, re-evaluated after the wait |
| `no_lock_no_outer_predicate` | yes | **yes** | **no** | nothing: the lost update |
| `lock_without_outer_predicate` | no | no | yes | `SKIP LOCKED` alone |

The "What protected it" column rests on PostgreSQL 16 documentation, §13.2.1
"Read Committed Isolation Level", and SELECT, "The Locking Clause".

### 3.3 What is now proven

- The shipped pass does not wait for a locked row and does not write it.
- **With the lock removed, the outer re-assertion alone prevents the lost
  update:** compare `no_lock`, where the value is kept, with
  `no_lock_no_outer_predicate`, where it is overwritten. This is the evidence
  the earlier harness could not give.
- With the lock present, the outer predicate is redundant
  (`lock_without_outer_predicate`). It is a second line, and there is now a
  test of what it does when it is the only line.

## 4. Mutations (each applied, run, restored and verified)

| Mutation | Tests that fail |
|---|---|
| M1: the pass also converts `UNKNOWN` | `test_the_sweep_leaves_unknown_untouched` |
| M2: the pass also converts `NEEDS_CONFIRMATION` | `test_the_sweep_leaves_needs_confirmation_untouched` |
| M3: the pass also converts `UNAVAILABLE` | `test_the_sweep_leaves_unavailable_untouched` |
| M4: no `FOR UPDATE SKIP LOCKED` in the pass | both concurrent-reconfirmation cases — **with the cause now visible**: the pass WAITED and did NOT write, because the outer predicate protected the value (see `05_results/STEP4-CONCURRENCY-ATTRIBUTION.txt`). The old harness failed by timeout here. |
| M4 + outer predicate removed | both cases: the pass waited and WROTE, and the concurrent value was overwritten |
| M5: offer reconfirm writes only `last_confirmed_at` | `…updates_both_confirmation_columns`, `…stated_confirmation_time…`, and 4 more (the empty column also breaks the provenance record) |
| M6: offer freshness reads `last_confirmed_at` | `…measured_on_commercial_terms_last_confirmed_at` |
| M7: offer freshness uses the `property` threshold | the same test, and `…stale_on_its_commercial_terms_clock` |
| M8: no alias refusal on property reconfirm | `test_reconfirming_an_alias_is_refused` |
| outer re-assertion only, lock kept | **none** — expected (§3.3): with the lock present the predicate is redundant; `no_lock` proves it guards when alone |

`tests/test_slice3_step4.py`: 86 tests (the attribution experiment adds 10).
