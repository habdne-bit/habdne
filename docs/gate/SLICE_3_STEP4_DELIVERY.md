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

The pass selects candidates in a subquery with `FOR UPDATE SKIP LOCKED`. The
outer `UPDATE` then **re-asserts** every condition, including the four-value
set, on the row it writes.

**Proven.** A reconfirmation in flight while the pass runs — whether to a
fresh `AVAILABLE` or to the excluded `UNAVAILABLE` — stands after both
commit:
- test: `test_the_sweep_does_not_overwrite_a_concurrent_reconfirmation`, 2
  cases;
- witness: the pass runs entirely inside the holder's open transaction, and
  the holder commits only after the pass has finished. `SKIP LOCKED` never
  blocks, so a blocked-backend witness would be the wrong evidence;
- mutation: removing the lock (M4) fails both cases.

**Not independently proven: the outer re-assertion.** With the outer
predicate removed and the lock kept, all 76 tests still pass.

That is expected. In Read Committed, a row locked by `FOR UPDATE` has the
subquery's `WHERE` re-evaluated against its latest committed version, and a
row another transaction holds is skipped. So the re-check at write time is
already performed inside the same statement. Sources: PostgreSQL 16
documentation, §13.2.1 "Read Committed Isolation Level", and SELECT, "The
Locking Clause". The outer predicate is kept as redundant defence, as in the
REQUEST pass. No test can make it the sole guard while the lock is present,
and none is claimed to.

## 4. Mutations (each applied, run, restored and verified)

| Mutation | Tests that fail |
|---|---|
| M1: the pass also converts `UNKNOWN` | `test_the_sweep_leaves_unknown_untouched` |
| M2: the pass also converts `NEEDS_CONFIRMATION` | `test_the_sweep_leaves_needs_confirmation_untouched` |
| M3: the pass also converts `UNAVAILABLE` | `test_the_sweep_leaves_unavailable_untouched` |
| M4: no `FOR UPDATE SKIP LOCKED` in the pass | both concurrent-reconfirmation cases |
| M5: offer reconfirm writes only `last_confirmed_at` | `…updates_both_confirmation_columns`, `…stated_confirmation_time…`, and 4 more (the empty column also breaks the provenance record) |
| M6: offer freshness reads `last_confirmed_at` | `…measured_on_commercial_terms_last_confirmed_at` |
| M7: offer freshness uses the `property` threshold | the same test, and `…stale_on_its_commercial_terms_clock` |
| M8: no alias refusal on property reconfirm | `test_reconfirming_an_alias_is_refused` |
| outer re-assertion only | **none** — see §3 |

`tests/test_slice3_step4.py`: 76 tests.
