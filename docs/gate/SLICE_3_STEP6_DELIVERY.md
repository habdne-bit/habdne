# Slice 3 · step 6 — the public list

**Basis.**
- The effective contract's `getPublicProperties`: "Returns only PUBLIC
  properties with at least one active public commercial context backed by
  currently valid PUBLIC_LISTING_ALLOWED consent. Private/Potential records and
  internal fields are never projected here. Price fields obey price_visibility."
  Also `PublicPropertySummary`, `PublicOfferSummary`, `Page` and `PageSize`.
- API_CONTRACTS v0.2 §3 "Public"; red-team D04; Developer Spec §23,
  invariant 11.
- `docs/gate/SLICE_3_PLAN.md` §4.4 (the public list's consent binds to the
  **offer**) and §8 step 6.
- RFC-001 R10.4 (the closed list of unauthenticated operations) and R6.3 (no
  per-request read audit).

No table, column, migration or reason code was added. The ops count stays at
67. The frozen contract is untouched.

**Code.**
- `services/public_listing.py`: the conditions, in one SQL statement.
- `api/routes/public.py`: the route.
- `api/deps.py`: `Public`, which carries no subject.
- `dto/boundaries.py`: three rendering corrections to the pre-existing
  `PublicPropertySummary`.

## 1. The three conditions, and each clause's proof

A property is listed only when all three hold, and **by the same offer**.
Every exclusion test starts from a world that IS listed and changes exactly
one fact. An absence on an empty list would prove nothing.

| Condition | Clause (`_LISTABLE_OFFERS` / `_PAGE`) | Proving test | Mutation |
|---|---|---|---|
| 1. `supply_mode = PUBLIC` | `p.supply_mode = 'PUBLIC'` | `test_a_property_that_is_not_public_is_absent` (PRIVATE, POTENTIAL) | P1 |
| 2. an **active** offer | `o.status = 'ACTIVE'` | `…consented_offer_that_is_not_active…` (DRAFT, PENDING_INFO, PAUSED, WITHDRAWN, CLOSED); `test_d04_…all_withdrawn_is_absent` | P2 |
| 2+3 on the property's **own** offer | `EXISTS (… l.property_id = p.property_id)` | `test_a_property_is_listed_by_its_own_offer_not_by_a_neighbours` | P11 |
| 3. the binding is on **this offer** | `b.offer_id = o.offer_id` | `…active_offer_with_no_binding…`; `…bound_to_the_property_rather_than_the_offer…` | P3 |
| 3. binding purpose | `b.purpose = 'PUBLIC_LISTING_ALLOWED'` | `test_a_binding_whose_purpose_is_not_public_listing_does_not_list` | P4 |
| 3. binding not revoked | `b.revoked_at IS NULL` | `test_a_revoked_binding_does_not_list` | P5 |
| 3. binding started | `b.bound_at <= now()` | `test_a_binding_that_starts_in_the_future_does_not_list_yet` | P6 |
| 3. grant scope | `g.scope = 'PUBLIC_LISTING_ALLOWED'` | `test_a_grant_whose_scope_changed_after_binding_does_not_list` | P7 |
| 3. grant status | `g.status = 'GRANTED'` | `test_a_revoked_status_alone_delists_although_no_date_is_recorded` | P8 |
| 3. grant revocation date (review of 3a53b0a) | `g.revoked_at IS NULL` | `test_a_revocation_date_alone_delists_although_the_status_says_granted` | P8b |
| 3. both, end to end | the two above | `test_revoking_the_grant_delists_although_the_binding_row_survives` (through `revoke_consent`, which sets both; it isolates neither) | — |
| 3. grant started | `g.granted_at <= now()` | `test_a_grant_that_starts_in_the_future_does_not_list_yet` | P9 |
| 3. the offer's own party | `g.party_id = o.party_id` | `test_a_consent_from_a_party_other_than_the_offers_does_not_list` | P10 |

**Why the read re-checks what the trigger already checked.**
`enforce_consent_binding()` compares purpose, scope and party when a binding
is **written**. Revoking a grant deliberately leaves its bindings in place,
inert (ADR-04, `consent.revoke_consent`). Nothing re-checks a grant or an
offer changed afterwards. The P7 and P10 tests model such later changes with
direct SQL, since no API path makes them. Each of those clauses is the only
thing that refuses its case.

**Correction after the review of 3a53b0a: the revocation date.** At
3a53b0a the read checked `g.status = 'GRANTED'` and not `g.revoked_at`.
- **The error in our reasoning.** We had removed `g.revoked_at IS NULL` as
  "unprovable", because `revoke_consent` sets both columns and so each
  masked the other. That confused one writer with the data. The frozen schema
  allows a `GRANTED` row with `revoked_at` filled (its only constraint is
  `CHECK (revoked_at IS NULL OR revoked_at >= granted_at)`).
- **What ADR-04 requires.** The permission service validates the "current
  grant/revocation state", i.e. both.
- **The fix.** Both clauses are now present. Each is proved by a test that
  changes ONLY its own column, on a grant whose offer was listed:
  - the date alone, status still `GRANTED` (P8b);
  - the status alone, date still NULL (P8).
- **A future-dated `revoked_at` also delists.** The read does not presume a
  revocation to be not yet effective.
- **Reproduction on the 3a53b0a service code, with the new tests kept:**
  exactly 1 failed, `test_a_revocation_date_alone_delists_although_the_status_says_granted`.

## 2. The projection

**Which offers.** Only offers that meet conditions 2 and 3 are projected.
- On a listed property, an ACTIVE offer from a party that did not consent is
  not shown; nor is a consented PAUSED offer, nor an offer whose grant was
  revoked. Test: `test_only_active_consented_offers_are_projected`, P17.
- The fixture world shows this unaided: the villa has three ACTIVE offers, and
  only `OFFER_OWNER_SALE` is listed.
- Offers are listed in creation order (P18).

**Three corrections to the pre-existing `PublicPropertySummary`** (Slice 1
code, first rendered over HTTP by this step):

| Defect | Evidence | Now | Test · mutation |
|---|---|---|---|
| `availability` passed any value, including `TEMPORARILY_UNAVAILABLE` and `UNAVAILABLE`, which the contract's enum does not declare | the contract's `PublicPropertySummary.availability` enum | a value outside the enum is omitted, never rendered | `test_the_dto_never_renders_an_availability_the_contract_does_not_declare` · P20 |
| the areas were `Decimal` | Pydantic 2.13.5 serializes `Decimal("220.00")` as `"220.00"`, a JSON **string** (measured); the contract declares `number` | typed `float`, so they serialize as JSON numbers. What the tests establish is that the JSON number written equals the value shown (`220.0`, `9999999999.99`, `0.01`). **No claim is made about binary representation** (corrected in the review of 3a53b0a) | `test_areas_are_json_numbers_equal_to_the_column` · P21 |
| `local_location_detail` copied unconditionally | Developer Spec §23 invariant 11 | withheld pending G3-12 (§4) | `test_the_local_location_detail_is_withheld_pending_g3_12` · P19 |

**The floor, redaction and schema conformance.**
- **Mandatory test 2, public half, over HTTP:**
  `test_seller_expectation_never_appears_in_the_public_list`. It searches the
  **raw body** for the distinctive value `987654321`, not only for the key.
- No `NEVER_SERIALIZED` key appears at any depth. The route also calls
  `assert_no_forbidden_fields(..., Audience.PUBLIC)`.
- Price redaction follows `price_visibility`: ON_REQUEST and PRIVATE give
  `null` (P22), and PUBLIC shows the price.
- `test_every_item_conforms_to_the_contracts_public_property_summary` checks
  every returned item against the contract's own schema: types, enums,
  `required`, `additionalProperties: false`, and the nested `offers`.
  - `jsonschema` is not installed and was not added. The checker implements
    only the constructs these two schemas use.
  - `test_the_conformance_check_is_not_vacuous` shows it catches a string area,
    an undeclared enum value and an undeclared key.

## 3. Choices within the rules, stated for review

1. **"Active" means `status = 'ACTIVE'`.** API_CONTRACTS §3 adds "no
   withdrawn/closed offer as the only commercial context". DRAFT,
   PENDING_INFO and PAUSED are not active either.
2. **The consent must bind to the offer** (plan §4.4). A property-scoped
   PUBLIC_LISTING_ALLOWED binding does not list.
3. **Publication rule R6-P1 (precautionary, OURS):** a property whose
   availability is `TEMPORARILY_UNAVAILABLE` or `UNAVAILABLE` is not
   published.
   - **Corrected in the review of 3a53b0a:** this is not something the
     response schema forces. `availability` is OPTIONAL in
     `PublicPropertySummary`, so such a property could be listed without the
     field.
   - It is a publication rule we chose, accepted for now as a precaution.
   - Its code and test name it: `LISTABLE_AVAILABILITY` and
     `test_rule_r6_p1_…`.
   - `current_availability` is `NOT NULL DEFAULT 'UNKNOWN'` (schema line 422),
     so there is no null case.
   - **A correction during the work:** the first draft handled a NULL
     availability, and its DTO note named a "None" rendering defect. The
     schema makes both impossible, so both were withdrawn before commit.
4. **`property_type` is compared as text.** The contract types the parameter
   as a plain `string` with no enum. So a value naming no type returns `[]`,
   not a 422, which would narrow the contract. Marker text such as `otp` or
   `SELECT 1` also returns `[]`: no 500, no echo.
5. **Paging applies to properties**, newest first
   (`created_at DESC, property_id`). The contract's `Page` (≥ 1) and
   `PageSize` (1..100, default 25) are enforced: 422 outside them (P24). The
   pages are disjoint and complete (P16).
6. **One statement, one snapshot.** The page and its offers are read in one
   statement. Read as two under Read Committed, a consent revoked between them
   would list a property with no consented offer. This is pinned structurally
   by `test_the_list_is_read_in_one_statement`.
7. **Unauthenticated, and the header is not read.** `Public` resolves no
   subject. A malformed or unknown bearer changes nothing, and no access audit
   is recorded (R6.3).
   - The gate fails closed: `PublicReads.authorize` allows only a policy that
     exists **and** is public (P23).
   - It does not call `PolicyTable.check_role` with no subject, which for a
     non-public policy would be an `AttributeError`, i.e. a 500.

## 4. Findings for decision

### G3-12 · `sharing_scope` and the public projection

Developer Spec §23, invariant 11: "Public visibility لا تعني أن كل التفاصيل
قابلة للمشاركة؛ sharing_scope يحكم التفصيل." The rule is stated, but no
field-to-scope mapping exists.
- `permission_scope` is set **per offer**, while `local_location_detail` and
  the areas belong to the **property**.
- The order of the three scopes is not declared.

**Delivered (the conservative reading):**
- the free-text `local_location_detail` is withheld at every scope, since it is
  the field most likely to locate a home exactly;
- the areas are shown exactly, as `PublicPropertySummary` declares them.

**Options.**
- (a) Keep withholding `local_location_detail`.
- (b) Show it only when every projected offer carries a scope that permits
  details. This needs the scopes' order decided.
- (c) Treat consent to public listing as consent to every declared field.

A related observation, not decided here: the opportunity code's `SUMMARY_ONLY`
comment speaks of "area **bands**", and no code implements bands.

### G3-13 · identity aliases in the public list

A property recorded as an alias of another is **not listed**, and its offers
are **not folded** into the canonical record
(`test_an_alias_is_not_listed_and_its_offers_are_not_folded_in`, P13).
Folding would move a party's consented offer onto a record it did not name.

**Options.**
- (a) As delivered.
- (b) Fold an alias's listable offers into its canonical record.
- (c) List both records.

Step 7 (Identity Lite) creates aliases through the API. The integration
test the review of 3a53b0a asked for is there, with an alias made by that API:
`test_an_alias_made_through_the_api_leaves_the_public_list` (step-7 note, §4).

### G3-14 · what `location_id` matches — implemented as subtree, for review

`locations` is a hierarchy (`parent_id`). The seed has four levels: 1 WILAYA,
16 COMMUNE, 5 AREA, 8 KSAR. Properties are recorded at the lower levels; the
fixture villa sits on a KSAR. The contract does not say whether `location_id`
matches exactly or also matches what lies beneath it.

**History.**
- At 3a53b0a an exact match was delivered and raised as an open question.
- The review of 3a53b0a asked for G3-14 to be treated.
- The explicit choice put to the reviewer was declined.
- So the recommended option is **implemented**, and remains subject to review.

**Delivered: the location AND every location beneath it.**
- The mechanism is a recursive CTE over `parent_id`, inside the listing's
  single statement.
- It uses `UNION`, not `UNION ALL`. `UNION` discards rows already produced, so
  the recursion ends even on a cycle, which the schema does not forbid
  (PostgreSQL 16 documentation, §7.8.2).
- An unknown `location_id` matches nothing.

| Test | Asserts | Mutation |
|---|---|---|
| `test_the_location_filter_matches_the_location_and_everything_beneath_it` | a wilaya returns its own property, the commune's and the ksar's (depth 3), and a sibling branch's; a commune returns only its branch; a ksar only itself | P14b (exact only): 2 fail |
| `test_the_location_filter_ends_on_a_cycle_in_the_hierarchy` | two locations made each other's parent: the answer is both, each once, and the request ends | P14b |
| `test_an_unknown_location_matches_nothing` | `[]` | — |

**A correction to our own option list at 3a53b0a.** It offered "(c) subtree
plus location aliases". `location_aliases` maps **text** to a `location_id`,
and the filter takes a UUID, so aliases play no part in it. That option was
withdrawn.

**If exact match is preferred:** P14b is exactly that change, and its two
failing tests are what would be rewritten.

## 5. Observed outside this step, recorded and not changed

Both are on paths that no route serves yet. Matching and opportunities are
not started.
- `render_opportunity_for_scope` renders `PublicPropertySummary` for any
  property at `SUMMARY_ONLY`. A PRIVATE property would then carry
  `supply_mode = PRIVATE`, which the public schema's enum (`PUBLIC` only) does
  not declare.
- `CustomerPropertyView` still types the areas as `Decimal`, which would
  serialize them as JSON strings.

## 6. Tests and mutations

`tests/test_slice3_public.py`: 70 cases, over HTTP on PostgreSQL. There
were 66 at 3a53b0a. The review of 3a53b0a added the two revocation-isolation
tests, and G3-14 replaced the exact-match test with three. Each test
builds its rows under its own location, because the database is shared across
the run.

Twenty-six mutations (P8b and P14b added in the review of 3a53b0a) are run by `db/dev/mutate_public_list.py`, through the
shared `db/dev/mutation_runner.py`. The output is bound to its commit and
source fingerprint in `docs/gate/evidence/STEP6-PUBLIC-LIST-MUTATIONS.txt`.
**Every one fails at least one test.**

The first run found one survivor: P21, "areas left as `Decimal`". Pydantic's
lax `float` field already converted the `Decimal`, so the conversion helper
proved nothing. The helper was removed, and P21 now mutates the field types
back to `Decimal`: 3 tests fail on `'220.00' == 220.0`.

## 7. Not in this step

- The authorization-matrix rules for the public list, and the STOP GATE C
  evidence, are step 8's.
- No consent-capture flow is in this slice (plan §6.4). Consents here are
  seeded or granted through the Slice 1 service.

## 8. The review of 3a53b0a — the three closure items

| Item | Where |
|---|---|
| the grant revocation date (`g.revoked_at IS NULL`), with a test changing only that column | §1 (correction note), P8b; reproduction on 3a53b0a: exactly that test fails |
| G3-14 | §4: subtree match implemented after the question was declined; P14b |
| the alias integration test with step 7 | step-7 note §4: `test_an_alias_made_through_the_api_leaves_the_public_list` |

The two wordings were also corrected:
- rule R6-P1 is stated as OUR precautionary rule, not something the schema
  forces (§3, item 3);
- the float claim is limited to what the tests show (§2).
