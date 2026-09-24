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

> **DECIDED (review of 1c2f6c5): option (c).** The truth layer is
> **PROPERTY-only** in this version. Claims and resolutions about a PARTY, a
> REQUEST or an OFFER stay refused with `422 ATTRIBUTE_VOCABULARY_UNDECIDED`.
> The refusal's `detail` states this: "the truth layer covers PROPERTY
> subjects only (decision G3-11)". It is pinned by
> `test_claims_and_resolutions_about_other_subjects_are_refused_naming_g3_11`
> and recorded at `truth.DELIVERED_SUBJECTS`. A vocabulary for those subjects
> is a later slice's decision, and needs one of the options below.

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

**Recommendation (as submitted):** (c) for Slice 3. Nothing in STOP GATE C
requires claims about parties, requests or offers. This option was approved.

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

## 6. Input hardening (review of 1c2f6c5): two families of routes to a 500

The review found two inputs that turned a refusal into a 500. Step 5 stays
open until both are refused over HTTP and tested. Each was treated as a
**family**: every member found in the code base is fixed, including Slice 2
and earlier-step members of the same defect.

### 6.1 Family 1: the caller's text echoed into `detail`

**Mechanism.** `problems._check_detail` refuses a `detail` containing an
implementation marker (`otp`, `turab.`, `SELECT `, … compared
case-insensitively) and raises `DetailLeak`, which is a 500. A typed domain
error that quoted the caller's own text therefore became a 500 whenever that
text contained a marker. The validation handler already followed the rule of
never echoing input values; the domain errors did not.

**Members, all fixed.** Each now names the field, never its value:

| Site | Operation | Slice |
|---|---|---|
| `truth.validate_attribute`: unknown `attribute_code` | `postClaims`, `postResolutions`, and the `property_attributes` projection (one validator) | 3 · step 5 |
| `truth.validate_attribute`: unregistered ENUM value (the reviewer's `"otp"`) | the same | 3 · step 5 |
| `truth.resolve`: unknown `resolution_reason_code` | `postResolutions` | 3 · step 5 |
| `offers.UnknownReasonCode` | `POST /offers/{id}/state` | 3 · step 1 |
| `relations.UnknownReasonCode` | `POST /properties/{id}/relations/{rid}/end` | G3-6 |
| `requests.UnknownCriterionCode` | `POST /requests/{id}/criteria` | **2** |
| `requests.UnknownReasonCode` (closure) | `POST /requests/{id}/state` | **2** |

**What a `detail` may still quote.** Only text that did not come from the
caller as free text:
- a value that has **matched a registry row**, such as "`'ROOMS'` takes a JSON
  number". `test_no_registered_code_contains_a_leak_marker` pins that none of
  the 68 seeded codes contains a marker. The codes are those in
  `attribute_definitions`, `attribute_options`, `criterion_definitions` and
  `reason_codes`.
- a value **held to a closed pattern** by the route, such as `management_mode`
  or `target_status`;
- UUIDs and timestamps. Their characters are hexadecimal digits, digits and
  separators, and cannot spell a marker.

The remaining interpolations in `src/turab` were audited against these three
cases. No other member was found.

### 6.2 Family 2: a number the database cannot store

**Mechanism.** Python's `json.loads`, which parses every request body,
accepts `1e400` (as `inf`), `NaN`, `Infinity` and `-Infinity`. None of these
is a JSON number: RFC 8259 §6 says "Numeric values that cannot be represented
in the grammar below (such as Infinity and NaN) are not permitted". Inside a
free JSON field they reached `json.dumps` as `Infinity`, then
`CAST(... AS jsonb)`, which PostgreSQL refuses. Through a typed field, an
out-of-range integer or area reached a column that cannot hold it.

**Fix** (`src/turab/api/json_types.py`):
- `JsonNumber` refuses a non-finite value.
- `JsonInteger` already did: `float.is_integer()` is False for inf and NaN
  (Python documentation: "finite with integral value").
- `FiniteJson` and `FiniteJsonObject` type every free JSON field and refuse a
  non-finite number **at any depth**. The walk is iterative and names neither
  path nor value.
- Column bounds are the frozen columns' own, so nothing storable is refused:
  - `bigint` (PostgreSQL 16 documentation §8.1.1, Table 8.2);
  - `smallint` (the same table);
  - `numeric(12,2)` (§8.1.2).

  The contract declares no maximum. This is not a contract change: it refuses
  earlier, with a typed 422, what the frozen schema already refused with an
  error.

| Field | Operation | Refusal |
|---|---|---|
| `claimed_value`, `extraction_confidence` | `postClaims` | non-finite at any depth; `[0,1]` |
| `resolved_value` | `postResolutions` | non-finite at any depth |
| `payload` (nested) | `postObservations` | non-finite at any depth |
| `source.metadata`, `raw_payload` (nested) | `postExternalLeads` | non-finite at any depth |
| convert `payload` | `postExternalLeadsLeadIdConvert` | typed the same way (\*) |
| `value` of a criterion | `POST /requests/{id}/criteria` (Slice **2**) | non-finite at any depth |
| `sort_order` of a criterion | the same (Slice **2**) | `smallint` range |
| `budget_target_dzd`, `budget_max_dzd` | `postRequests`, request PATCH (Slice **2**) | `≤ 2⁶³−1` |
| `asking_price_dzd`, `seller_expectation_dzd` | offer create and PATCH | `≤ 2⁶³−1` |
| `land_area_m2`, `built_area_m2` | property create and PATCH | finite, `≤ 9 999 999 999.99` |

(\*) The conversion is refused by decision G3-10 and writes nothing. Its
payload is typed like the others for consistency, and is not separately tested
over HTTP.

### 6.3 Tests: `tests/test_input_hardening.py`, 86 cases over HTTP on PostgreSQL

Each HTTP case asserts three things:
1. a typed 4xx with a stable code (`VALIDATION_FAILED` or `UNKNOWN_FIELD`),
   never a 500;
2. **nothing written**, as a row count or version before and after;
3. **the refusal consumed nothing**: the SAME `Idempotency-Key`, or the SAME
   `If-Match-Version` for a PATCH, then succeeds with a valid body.

The marked values are `otp`, `turab.x` and `SELECT 1`. This covers both cases
the review required: the ENUM value `"otp"`, and an unknown attribute code
containing `turab.`. The non-finite values are `1e400`, `-1e400`, `NaN`,
`Infinity` and `-Infinity`, each sent as raw JSON text exactly as a client
sends it.

**The cause, not only the status.** This file's test client raises server
exceptions. A regression to a 500 therefore fails with its exception
(`DetailLeak`, a psycopg `DataError`), not merely with a status code.

Before any fix, the file reproduced the defects: **71 failed, 3 passed**.

### 6.4 Mutations, with the cause each failure reports

The mutations are run by `db/dev/mutate_input_hardening.py`. Its output,
bound to the commit and source fingerprint it ran on, is
`docs/gate/evidence/STEP5-INPUT-HARDENING-MUTATIONS.txt`.

| # | Mutation (production code) | Tests failing | Cause reported |
|---|---|---|---|
| M1 | echo the unknown `attribute_code` | 3 | `DetailLeak` |
| M2 | echo the ENUM value | 3 | `DetailLeak` |
| M3 | echo `resolution_reason_code` | 3 | `DetailLeak` |
| M4 | echo the offer reason code | 3 | `DetailLeak` |
| M5 | echo the relation reason code | 3 | `DetailLeak` |
| M6 | echo the criterion code (Slice 2) | 3 | `DetailLeak` |
| M7 | echo the closure reason (Slice 2) | 3 | `DetailLeak` |
| M8 | drop `JsonNumber`'s finite check | 5 (type level only) | `DID NOT RAISE` |
| M9 | drop the `FiniteJson` walk | 31 | `InvalidTextRepresentation: invalid input syntax for type json` |
| M10 | drop the offer `bigint` bound | 3 | `NumericValueOutOfRange: bigint out of range` |
| M11 | drop the request `bigint` bound | 2 | the same |
| M12 | drop the `smallint` bound | 2 | `NumericValueOutOfRange: smallint out of range` |
| M13 | drop the `numeric(12,2)` bound | 3 | `NumericValueOutOfRange: numeric field overflow` |

**A limit, stated.** M8 fails **no HTTP test**. Every `JsonNumber` field in
the API today also carries `ge`, `gt` or `le` bounds, and those bounds refuse
inf and NaN on their own: NaN fails every comparison, and inf exceeds `le`.
The type's own check guards a future field with no bounds. It is proven on the
type itself: `test_json_number_refuses_a_non_finite_value_with_no_bounds`.
It is not claimed as the HTTP mechanism.
