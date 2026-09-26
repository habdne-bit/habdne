# Slice 4 · step 3 — the candidate set

**Authorised:** the review of 431e896 closed step 2, and allowed step 3 on
decisions **G4-8** and **G4-9 (a)**. Matching stays without row writes
until its own step. Step 4 (the criterion rules) waits on G4-3 to G4-7.

**Basis:**
- `docs/gate/SLICE_4_PLAN.md` revision 4: G4-8 and G4-9 as decided, and
  §8 step 3;
- ADR-01 and ADR-03;
- `API_CONTRACTS_v0.2` §4.8;
- red-team C01, D05 and E02;
- `trg_match_commercial_context` (`schema_v0.2.3.sql:1170–1207`).

**Read-only.** `src/turab/matching/candidates.py` issues SELECTs only. The
package-wide test `test_the_matching_package_reads_and_never_writes` covers
the new module. `test_computing_the_set_writes_nothing` also counts the rows
of the request, property, offer, match, diagnostic, audit and task tables,
before and after.

## 1. The rules, and what proves each

| Rule (G4-8 / G4-9) | Proven by |
|---|---|
| **BUY evaluates only SALE, RENT only RENT** (mandatory test 1, C01) | `test_a_request_evaluates_only_offers_of_its_transaction_type` (both intents); `test_a_property_with_only_the_other_type_is_reported_not_evaluated`; the backstop `test_the_schema_refuses_a_buy_match_on_a_rent_offer` (the frozen trigger, labelled) |
| **one candidate per qualifying offer** | `test_every_qualifying_offer_of_a_property_is_its_own_candidate` |
| only **ACTIVE** offers qualify | `test_an_offer_that_is_not_active_does_not_qualify` (DRAFT, PENDING_INFO, PAUSED, WITHDRAWN, CLOSED) |
| **ACTIVE or NEEDS_CONFIRMATION** requests only; anything else refused | `test_an_active_or_stale_request_is_matched` (2); `test_any_other_request_status_is_refused` (5); `test_a_missing_request_is_refused` |
| **canonical only** (mandatory test 9, E02); a listed alias is reported with its canonical id | `test_an_alias_is_never_a_candidate_and_is_reported_with_its_canonical`. The schema's own refusal is `test_e02_a_new_match_on_the_alias_is_refused_by_the_schema` (Slice 3) |
| **UNAVAILABLE excluded and reported**; every other availability evaluated | `test_an_unavailable_property_is_excluded_and_reported` (listed and full scan); `test_every_other_availability_is_evaluated` (6) |
| **POTENTIAL without an offer: not evaluated, reason reported** (G4-9 (a); mandatory test 6, NARROWED) | `test_a_potential_property_without_willingness_context_is_not_evaluated` (listed and full scan); `test_a_potential_property_with_a_qualifying_offer_is_evaluated_through_it` |
| PUBLIC and PRIVATE supply both matched (B04) | `test_public_and_private_supply_are_both_matched` |
| `property_ids` narrows, de-duplicates and orders; a missing id is reported | `test_listed_ids_narrow_the_set_are_deduplicated_and_ordered`; `test_an_empty_list_evaluates_nothing` |
| deterministic order | `test_the_candidate_set_is_deterministic`. Offers are inserted with descending ids, so the order must come from the query, not the heap |

## 2. The exclusions, reported, never silent (G4-8)

| Reason | When |
|---|---|
| `PROPERTY_NOT_FOUND` | a listed id names no property |
| `IDENTITY_ALIAS` | a listed alias, reported with its canonical id |
| `OFFER_ON_ALIAS` | a qualifying offer sits on an alias (finding below) |
| `PROPERTY_UNAVAILABLE` | availability `UNAVAILABLE` |
| `POTENTIAL_WITHOUT_OFFER` | G4-9 (a) |
| `NO_QUALIFYING_OFFER` | a listed property without an ACTIVE offer of the right type |

**Two choices, stated for review.**
1. **What a full scan reports.** A full scan (no `property_ids`) reports
   what could otherwise have been a candidate:
   - excluded properties that have a qualifying offer;
   - POTENTIAL properties without one.

   It does not enumerate every property lacking a relevant offer: a BUY
   run would otherwise list every rental in the market.
   `test_a_full_scan_finds_every_qualifying_offer_and_stays_silent_on_the_rest`
   pins this.
2. **These labels are exclusion reasons of the diagnostic**, not rows of
   `reason_codes`. They will be stored in the diagnostic row's
   `blocker_summary` in step 7. No reason-code category is added.

## 3. A finding: an ACTIVE offer on an alias cannot be evaluated

The frozen schema leaves such an offer with no evaluation path. Three facts
combine:
- G3-13 decided that an alias's offers are **not moved** to its canonical
  record;
- `trg_match_commercial_context` **refuses a match on an alias**;
- the same trigger requires the **evaluated offer to belong to the matched
  property**, so the offer cannot be evaluated under the canonical record
  either.

This step **reports** it (`OFFER_ON_ALIAS`, with the canonical id and the
offer ids, in a full scan too) and decides nothing more
(`test_a_qualifying_offer_on_an_alias_is_reported_as_unevaluable`).

Whether such offers should be moved, re-created on the canonical record, or
stay reported is a decision. **It is raised here, as G4-17, for review.**

## 4. Mutation evidence

`db/dev/mutate_slice4_step3.py`: 16 mutations, one per rule and reported
exclusion. The result on this round's clean tree is in
`evidence/SLICE4-STEP3-MUTATIONS.txt`.

**Equivalent mutations are left out.** A mutation that changes only the
READ scope of a full scan, and not its classification, is equivalent: rows
outside that scope are silent either way. It could only show up as a false
survivor. The script says so.

## 5. What remains

- Step 4 (the criterion rules) waits on **G4-3 to G4-7**.
- **G4-17** (offers stranded on aliases) is raised above.
