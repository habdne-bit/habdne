# Slice 3 · step 5 — the truth layer

**Basis:**
- `docs/gate/SLICE_3_PLAN.md` §3.1, §3.2, §3.7 (G3-4, resolved), §3.8, §3.9,
  §6.1, §6.2 and §6.3;
- the contract's `postObservations`, `postClaims`,
  `postClaimsClaimIdVerificationEvents` and `postResolutions`;
- the schema triggers `trg_apply_verification_event`,
  `trg_resolution_lineage` and `trg_property_attribute_claim`, and the four
  `ux_resolved_current_*` indexes.

No table, column, migration or reason-code category was added. The ops count
stays at 67.

## 1. Rules, mechanisms, proofs

| Rule | Mechanism | Proving tests (mutation that fails them) |
|---|---|---|
| §3.1: a claim cannot be born verified | **the contract boundary**: `ClaimInput` is closed and has no level field | `test_a_claim_cannot_be_created_already_verified`, labelled as a boundary test |
| §3.1: born `DECLARED` | the schema default; the service sets no level | `test_a_claim_is_born_declared` |
| §3.1: only `CONFIRMED` raises the level, and the DATABASE raises it | `trg_apply_verification_event`; the service never writes the claim | `test_only_a_confirmed_verification_event_raises_the_level`, `…non_confirmed_outcome…` (NOT_CONFIRMED, INCONCLUSIVE), `…conflict_found…`, `…lower_confirmation_never_lowers…` |
| §3.2: a resolution cites only its own subject and attribute | service pre-check under `FOR SHARE` on the claim; the trigger stands behind it | `…cannot_cite_a_claim_about_another_subject` (T3), `…another_attribute` (T4), `…lineage_trigger_still_stands…` |
| §3.7 c1: `resolved_by` recorded | column | `test_resolved_by_account_is_recorded` |
| §3.7 c2: history preserved, never overwritten | close (`valid_to`, `SUPERSEDED`) and insert, in one command | `test_only_one_resolved_value_is_current_per_attribute`, `test_superseding_closes_the_previous_row_in_the_same_transaction` (T5) |
| §3.7 c3: `source_claim_id` stored | column, and the `property_attributes` projection | `test_the_source_claim_is_stored` (T12) |
| §3.7 c4: no resolution by a background job | `ActorRequired` when there is no acting account | `test_a_background_job_cannot_issue_a_resolution` (T6); see §3 for the limit |
| §3.7 c5: audited | `audit_resolved_values` | `test_every_resolution_write_is_audited` |
| §3.8: at least one origin; `recorded_by` is not one | service check | `test_a_claim_must_carry_at_least_one_origin`, `test_recorded_by_account_is_not_an_origin` (T1), `test_a_party_assertion_alone_is_a_valid_origin`, source-alone and observation-alone |
| §3.8: a source must agree with its observation's source | service check | `test_a_source_inconsistent_with_its_observation_is_refused` (T2) |
| §3.9: ONE validator, three call sites | `truth.validate_attribute`, called by claims, resolutions and `upsert_property_attribute` | inactive (T9), unregistered ENUM option (T8), not applicable to the property type (T7), unknown code: **each asserted at all three call sites** |
| §6.3: concurrent resolutions of one attribute | `FOR UPDATE` on the subject row; the `ux_resolved_current_*` index as backstop | `test_two_concurrent_resolutions_of_one_attribute_yield_one_current_value` (T10) |

`tests/test_slice3_truth.py`: 63 tests. Twelve mutations were each applied,
run and restored (checked with cmp). Every one fails its named tests.

**T10, with its cause** (the step-4 lesson applied). The race harness
releases the holder when PostgreSQL reports the contender blocked by it; the
holder's commit never waits for the contender to finish. Removing the subject
lock gives:

    waited=True holder=<id> contender=raised IntegrityError: (psycopg.errors.UniqueViolation)
    duplicate key value violates unique constraint "ux_resolved_current_property"

So the **index** keeps exactly one CURRENT value in every case, and the
**subject lock** is what lets both writers succeed in order. With the lock in
place, both succeed, the second closes the first, and both rows are kept.

## 2. Finding G3-11 — a vocabulary for PARTY, REQUEST and OFFER attributes

**The problem.** `ClaimInput` and `ResolutionInput` accept four subject
types. §3.9 validates `attribute_code` against `attribute_definitions`,
whose `applies_to` is a **list of property types** and whose seeded rows are
all property attributes: BEDROOMS, ROOMS, RIGHT_TYPE, DOCUMENT_TYPE and the
rest. Nothing registers what may be claimed about a party, a request or an
offer.

- Applied literally, §3.9 would accept a property code such as `RIGHT_TYPE`
  about a party. That would be permissive by accident.
- Inventing a vocabulary for those subjects would be a decision.

**What is delivered.**
- PROPERTY subjects are complete.
- PARTY, REQUEST and OFFER subjects are **refused** for claims and
  resolutions with `422 ATTRIBUTE_VOCABULARY_UNDECIDED`, a message naming
  G3-11, nothing written, and the key not consumed. This follows plan §7
  condition 1: refuse with a typed error naming an undecided rule.
- Verification events work on any existing claim, whatever its subject.

**Options.**
- (a) Register attribute definitions per subject type. This needs a
  subject-type column or a separate registry, which is a schema change.
- (b) Allow non-property subjects to use only `applies_to IS NULL`
  definitions.
- (c) Keep them refused until a later slice needs them.

**Recommendation:** (c) for Slice 3. Nothing in STOP GATE C requires claims
about parties, requests or offers.

## 3. Choices within the rules, and one limit, stated for review

1. **No machine-account type exists in the schema.** §3.7 condition 4 is
   enforced as "no resolution without an acting account". A background job
   runs actor-less and is refused. A machine holding a user's token cannot be
   distinguished, and that is not claimed.
2. **Time rules.**
   - `observed_at` and a resolution's `valid_from` must carry an offset and
     may not be in the future. This is the rule already applied to
     confirmation times.
   - A backdated resolution must still start after the current one, so
     history cannot interleave.
3. **The previous value is closed at the new one's `valid_from`**
   (`valid_to = new.valid_from`). The two rows therefore tile time without a
   gap or an overlap.
4. **`property_attributes` is the projection of the current resolved
   PROPERTY value.** It is written in the same transaction, through the same
   validator. Its `resolved_claim_id` is the resolution's `source_claim_id`,
   which `trg_property_attribute_claim` checks.
5. **Value types are checked against `value_type`**: NUMBER is a JSON
   number, BOOLEAN a JSON boolean, TEXT a string, DATE `YYYY-MM-DD`, and JSON
   is any value. This goes beyond §3.9's ENUM rule, and is stated as such.
6. **Audit.**
   - `claims` and `resolved_values` are audited by their triggers.
   - `observations`, `verification_events` and `property_attributes` have
     no trigger. They are audited by the command layer through the shared
     `audit_rows` helper, as for relations and leads.
7. **A property that is an identity alias is refused** for claims and
   resolutions with 409, per decision F-2.

## 4. Not in this step

The STOP GATE C row "who supplied each fact?" also names two tests:
- `test_a_source_is_created_only_through_an_external_lead`: the property is
  proven in step 3 under other names; it will be mapped in step 8;
- `test_converting_a_lead_records_its_party_and_consent`: conversion is
  refused by decision G3-10.

The STOP GATE C evidence is step 8's.

## 5. Caught by the architecture guard during this step

The first version of the routes checked authorization in a shared `_gate`
helper. `test_every_command_route_performs_an_object_check` refused it,
because the check was not visible in the route itself. The guard was right
and was left as it is. Each route now calls `command.authorize` and
`command.authorize_staff_only` directly.
