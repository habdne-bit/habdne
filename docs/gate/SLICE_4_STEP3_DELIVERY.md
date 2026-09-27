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
| `POTENTIAL_WITHOUT_OFFER` | G4-9 (a): a POTENTIAL property with **no offer at all** |
| `NO_QUALIFYING_OFFER` | a listed property without an ACTIVE offer of the right type, **POTENTIAL included**, with the count of the offers it does have |

**Two choices, stated for review.**
1. **What a full scan reports.** A full scan (no `property_ids`) takes
   into scope what could otherwise have been a candidate:
   - properties that have a qualifying offer;
   - POTENTIAL properties with **no offer at all** (narrowed in the review
     of cc3a7fe, §6).

   Every property in scope ends as a candidate or with exactly one reason.
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
stay reported is a decision. It was raised here as G4-17.

> **DECIDED (review of cc3a7fe): (a)**, recorded in plan revision 6. The
> offer stays on the alias and is reported, with no automatic move or
> re-link. It is not assumed that the offer's party can create an offer on
> the canonical record. Any new offer there is a new creation, through the
> property's authorization and a new consent, by the existing paths.

## 4. Mutation evidence

`db/dev/mutate_slice4_step3.py`: **19 of 19 fail**, none survive, one per
rule and reported exclusion.
- Recorded on a clean tree at `5ec9a84`, source fingerprint
  `61236271…afcfc` (`evidence/SLICE4-STEP3-MUTATIONS.txt`), baseline 44
  passed.
- Every mutated file was restored and verified by sha256.
- The trial run on the dirty tree also killed all 19, and no test changed
  after it.
- The first round (16 of 16 at `6396505`, fingerprint `acbcd44c…1ef7`) is
  superseded by this one; it is in the file's git history.

**Revision 1 (6396505) left out mutations of the full scan's READ scope as
equivalent.** Since the review of cc3a7fe that no longer holds: every
property in scope is reported, so the scope changes the result. T18
restores the old scope and is killed (§6).

## 5. What remains

- Step 4 (the criterion rules) waits on **G4-3 to G4-7**.
- **G4-17** is decided (a).
- The step-4 decisions G4-3, G4-4, G4-6 and G4-7, and G4-5 for SALE, are
  recorded in plan revision 6.
- **G4-5R, the rent period, is open.** No numeric PASS or FAIL for a RENT
  price until it is decided.

## 6. The review of cc3a7fe: two diagnostic defects, and a third the invariant found

**The two cases of the review**, reproduced on the database, with the new
tests run on `candidates.py` exactly as at cc3a7fe
(`evidence/SLICE4-STEP3-DIAGNOSTIC-BEFORE-FIX.txt`):
1. **A BUY request, and a POTENTIAL property with only a RENT offer**, or
   only a non-ACTIVE offer, was reported `POTENTIAL_WITHOUT_OFFER`.
   - Cause: the query kept qualifying offers only, and the classification
     read their absence as "no offer".
2. **A full scan, and a POTENTIAL property that is UNAVAILABLE with no
   offer.** It entered the scope, and was then dropped with no reason.

**A third, found by the invariant test:** in a full scan, a POTENTIAL
**alias** with no offer, available or not, was also dropped silently.

Seven failures in total: 4 parametrised cases of case 1, case 2, and both
modes of the invariant test. The one plain no-offer case passed.

**The fix** (`candidates.py`):
- **"No offer at all" is distinguished from "no qualifying offer".** The
  query now reads `offers_on_property`, counting every offer of any status
  or type.
  - `POTENTIAL_WITHOUT_OFFER` is reported only when it is 0.
  - A POTENTIAL property with non-qualifying offers is
    `NO_QUALIFYING_OFFER`, with that count.
- **The full scan's scope** is now: a qualifying offer, or a POTENTIAL
  property with **no offer at all**.
- **Every property in scope ends as a candidate, or with exactly one
  reason.** The branches that could drop an in-scope property are gone.
- **The precedence is stated and tested:** alias > `PROPERTY_UNAVAILABLE` >
  candidate > `POTENTIAL_WITHOUT_OFFER` > `NO_QUALIFYING_OFFER`.
  `PROPERTY_UNAVAILABLE` comes before `POTENTIAL_WITHOUT_OFFER` because even
  with willingness data, an unavailable property would not be evaluated.

**Tests** (8 new, all failing at cc3a7fe except the plain no-offer case):
- `test_a_potential_property_whose_offers_do_not_qualify_is_not_called_offerless`,
  with 4 cases: a RENT offer, and non-ACTIVE SALE and RENT offers;
- `test_a_potential_property_with_no_offer_at_all_is_still_potential_without_offer`;
- `test_an_unavailable_offerless_potential_property_gets_exactly_one_reason`,
  listed and in a full scan: exactly `[PROPERTY_UNAVAILABLE]`;
- `test_every_property_in_scope_is_a_candidate_or_has_exactly_one_reason`
  (listed, and full scan).
  - It builds all **32 combinations** of supply, availability, alias and
    offer state, and checks each against the precedence and scope, which
    are written in the test independently of the implementation.
  - It checks both ways: nothing in scope unreported, and nothing out of
    scope reported.

**Mutations:**
- T13, T14 and T16 are re-anchored, and T13 now restores case 2's defect.
- New: T17 (case 1's defect), T18 (the old scope), and T19 (counting only
  ACTIVE offers).
- The trial run on the dirty tree killed all 19.

**The two diagnostic choices** of §2 were accepted within their declared
scope. As the review says, that acceptance does not excuse any property the
scan took into scope and then dropped. The invariant test above now guards
that.

