# Slice 3 — PROPERTY / OFFER / SOURCE / Truth Layer / Identity Lite
## Implementation plan, submitted for approval before any code is written

**Status:** proposal. Nothing in this plan has been implemented.
**Baseline:** Handoff v1.0.3 / technical pack v0.2.3, frozen.
**Authority for the scope:** `docs/handoff/06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md`
lines 127–166 (objective, deliverables, mandatory tests, STOP GATE C).
**Predecessor:** Slice 2, closed within its agreed scope at `73be3a7` + `94639a6`.

Two boundaries hold throughout, and are restated in §6 as acceptance conditions:

1. **Matching is not entered.** No candidate generation, no hard gate, no
   ranking, no `match_candidates` rows. Slice 4 owns all of it.
2. **PROPERTY claim eligibility is not decided, and not decided implicitly.**
   `PropertyClaimUndecided` stays exactly as it is. No path added by this slice
   may create a property-party authority link as a side effect.

Everything below is derived from the frozen schema, the effective contract and
RFC-001. Where a rule is **not** derivable, it appears in §4 as a decision
request, not as an assumption.

---

## 1. Operations in scope

Nineteen operations, all already declared in the effective contract
(`docs/api/openapi_effective_v0.2.3.yaml`). **No operation is invented, and no
contract correction is proposed by this plan.**

### 1.1 Physical property

| operationId | Method · Path | Roles | Object authorization |
|---|---|---|---|
| `postProperties` | POST `/properties` | ADMIN, OPERATOR, CUSTOMER | customer: own/managed party only |
| `getPropertiesPropertyId` | GET `/properties/{id}` | ADMIN, OPERATOR, REVIEWER | internal view |
| `getMePropertiesPropertyId` | GET `/me/properties/{id}` | CUSTOMER | must own/manage/claim it |
| `patchPropertiesPropertyId` | PATCH `/properties/{id}` | ADMIN, OPERATOR, CUSTOMER | customer: own only |
| `postPropertiesPropertyIdReconfirm` | POST `/properties/{id}/reconfirm` | ADMIN, OPERATOR, CUSTOMER | customer: own only |
| `getPublicProperties` | GET `/public/properties` | **unauthenticated** | closed list of six — see §3.4 |
| `getBackofficeQueuesProperties` | GET `/backoffice/queues/properties` | ADMIN, OPERATOR, REVIEWER | internal queue |

### 1.2 Commercial offers

| operationId | Method · Path | Roles | Object authorization |
|---|---|---|---|
| `postPropertiesPropertyIdOffers` | POST `/properties/{id}/offers` | ADMIN, OPERATOR, CUSTOMER | customer: own only |
| `patchOffersOfferId` | PATCH `/offers/{id}` | ADMIN, OPERATOR, CUSTOMER | customer: own offer only |
| `postOffersOfferIdState` | POST `/offers/{id}/state` | ADMIN, OPERATOR, CUSTOMER | customer: own offer; **state machine required — see G3-1** |
| `postOffersOfferIdReconfirm` | POST `/offers/{id}/reconfirm` | ADMIN, OPERATOR, CUSTOMER | customer: own offer; commercial freshness |
| `postOffersOfferIdSources` | POST `/offers/{id}/sources` | ADMIN, OPERATOR | — |

### 1.3 Truth layer

| operationId | Method · Path | Roles | Note |
|---|---|---|---|
| `postObservations` | POST `/observations` | ADMIN, OPERATOR | **separation-sensitive** |
| `postClaims` | POST `/claims` | ADMIN, OPERATOR | **separation-sensitive** |
| `postClaimsClaimIdVerificationEvents` | POST `/claims/{id}/verification-events` | ADMIN, OPERATOR, REVIEWER | the only way to raise a level |
| `postResolutions` | POST `/resolutions` | ADMIN, OPERATOR, REVIEWER | — |

### 1.4 Identity Lite

| operationId | Method · Path | Roles | Note |
|---|---|---|---|
| `postIdentityCandidatesGenerate` | POST `/identity/candidates/generate` | ADMIN, OPERATOR | deterministic signals only |
| `getIdentityCandidates` | GET `/identity/candidates` | ADMIN, OPERATOR, REVIEWER | — |
| `postIdentityCandidatesCandidateIdReview` | POST `/identity/candidates/{id}/review` | ADMIN, **REVIEWER** | **separation-sensitive**; OPERATOR is *not* a role here |

**On the maker-checker split.** `postObservations`, `postClaims` and
`postIdentityCandidatesCandidateIdReview` are already in
`SEPARATION_SENSITIVE_OPERATIONS` (`src/turab/auth/roles.py:35`), so an account
carrying an OPERATOR+REVIEWER anomaly fails closed on all three under INV-2.
That machinery exists and is tested; this slice inherits it and adds no
exception. Note the asymmetry the contract already draws and which we will
**not** smooth over: an OPERATOR may *generate* identity candidates but may not
*review* them.

---

## 2. Deliverables mapped to the frozen schema

Every table below exists in `schema_v0.2.3.sql`. **This slice proposes no new
table, no new column and no new migration.** If implementation shows one is
needed, that is a finding to bring back, not a thing to add.

| Deliverable (slices doc) | Tables | Lines |
|---|---|---|
| physical PROPERTY record | `properties`, `property_attributes` | 415, 437 |
| PUBLIC / PRIVATE / POTENTIAL supply modes | `supply_mode` enum on `properties` | — |
| multiple offers for one physical property | `property_offers` (FK `property_id`, no uniqueness on the pair) | 447 |
| offer terms, visibility, negotiability, seller expectation, separate commercial freshness | `property_offers.asking_price_dzd`, `price_visibility`, `price_negotiable`, `seller_expectation_dzd`, `last_confirmed_at`, `commercial_terms_last_confirmed_at` | 447 |
| sources and offer-source links | `sources`, `property_offer_sources` | — |
| party-property relations | `party_property_relations` | — |
| observation → claim → verification → resolution | `observations`, `claims`, `verification_events`, `resolved_values` | 498–571 |
| controlled right/document options | `attribute_definitions`, `attribute_options` | — |
| identity candidate generation | `property_identity_candidates` | 603 |
| human review, non-destructive alias→canonical | `property_identity_aliases` | 623 |

Four schema facts shape the design and are worth stating, because each one
removes a decision rather than creating one:

- `property_offers` has **no** unique constraint over `(property_id,
  transaction_type, party_id)`. Owner sale + broker sale + rent on one property
  is therefore permitted *by the schema*, not by a service rule we would add.
- `claims` has `CHECK (num_nonnulls(party_id, request_id, property_id,
  offer_id) = 1)` — exactly one subject. `ClaimInput.subject` carries
  `{type, id}`, so the mapping is total and unambiguous.
- `resolved_values` has four partial unique indexes on `(subject,
  attribute_code) WHERE valid_to IS NULL AND resolution_status = 'CURRENT'`.
  "One current value per attribute" is a database guarantee. Resolution must
  therefore close the previous row and insert the new one **in one
  transaction**, and the collision must be mapped the way the criteria slot
  collision now is — a typed 409 from a named constraint inside a SAVEPOINT,
  not a 500. This is the direct reuse of the R-S2-03 work.
- `property_identity_aliases.source_identity_candidate_id` is `NOT NULL
  UNIQUE`. An alias without a reviewed candidate is impossible, and one
  candidate cannot produce two aliases. Triggers add the rest (§3.5).

**A correction to an earlier draft of this plan.** We first wrote that the
lineage and identity-pair rules were the service's to enforce and that "the
schema cannot check it". Reading the trigger definitions showed the opposite:
`trg_resolution_lineage`, `trg_identity_alias` and
`trg_identity_same_requires_alias` already enforce them. The plan below is
built on what the schema does, not on what we assumed it left to us — the
difference changes the write ORDER in §3.5 and reclassifies two tests in §5.

---

## 3. Rules derived from the frozen sources

### 3.1 A claim may not be born verified — and the database, not the service, raises the level

`ClaimInput` (effective contract) has properties `subject`, `attribute_code`,
`claimed_value`, `asserted_by_party_id`, `source_id`, `observation_id`,
`extracted_by`, `extraction_model_version`, `extraction_confidence`,
`observed_at`, `valid_from`, `valid_to` — with `additionalProperties: false`.
There is **no** verification-level field. `claims.effective_verification_level`
defaults to `DECLARED`.

So "a claim cannot be created as `DOCUMENT_SEEN` directly" is enforced at the
**contract boundary**. The mandatory test for it is a boundary test, not a
service rule, and we will say so rather than add a service check and take
credit for a guarantee the contract already gives.

The upgrade is likewise **not ours**. `trg_apply_verification_event`
(`schema_v0.2.3.sql:1149`) fires `AFTER INSERT ON verification_events` and does
the whole job in the database:

```sql
IF NEW.outcome = 'CONFIRMED' THEN
  UPDATE claims SET effective_verification_level =
      GREATEST(effective_verification_level, NEW.level) WHERE claim_id = NEW.claim_id;
ELSIF NEW.outcome = 'CONFLICT_FOUND' THEN
  UPDATE claims SET status = 'CONFLICTING' WHERE claim_id = NEW.claim_id;
END IF;
```

Three consequences, each of which removes work rather than adding it:

- **The service must not also update the claim.** Writing the level in Python
  as well would be a second, redundant write racing the trigger. The endpoint
  inserts the event and reads the claim back.
- `GREATEST` means a later `CONFIRMED` event at a *lower* level cannot lower an
  already-raised claim. This is a single-statement guarantee, so it needs no
  lock — and the concurrency test we first sketched for it would have proved
  nothing about our code (§5.2).
- `NOT_CONFIRMED` and `INCONCLUSIVE` are handled by the trigger doing nothing,
  which is the required behaviour.

### 3.2 A resolution may not point outside its own subject — also enforced in the database

`trg_resolution_lineage` (`schema_v0.2.3.sql:1134`) fires `BEFORE INSERT OR
UPDATE ON resolved_values` and refuses a `source_claim_id` whose
`attribute_code` differs, or whose subject columns differ, from the row being
written.

An earlier draft of this plan claimed this check was ours to write. **That was
wrong**, and the correction matters for how we implement the endpoint: the
service's job is not to *enforce* the rule but to **surface it as a typed 4xx**
instead of letting a raw database error become a 500 — the R-S2-03 lesson,
applied to a different mechanism.

And the mechanism *is* different, which is the trap here. These triggers use
`RAISE EXCEPTION`, i.e. SQLSTATE **P0001**, so `exc.orig.diag.constraint_name`
is **empty**. The constraint-name mapping we built for the criteria slot
**cannot** be reused for them. Two distinct error paths, deliberately:

| violation | mechanism | mapping |
|---|---|---|
| two current values for one attribute | `ux_resolved_current_*` (a named unique index) | SAVEPOINT + `constraint_name`, exactly as `DUPLICATE_CRITERION_SLOT` |
| resolution cites a foreign claim | `trg_resolution_lineage` → P0001 | **pre-check under a row lock on the claim**, inside the write transaction; the trigger remains as the backstop |

We will not match on the exception's *message text* to identify a P0001 — a
message is not an interface. The pre-check is the mapping, and the trigger is
what makes a missed pre-check safe rather than silent.

### 3.3 Freshness: three independent clocks

The seeded active policy already carries all three thresholds
(`seed_master_data_v0.2.3.sql:178`):

```
"freshness_threshold_days": {"request": 30, "property": 30, "offer_terms": 14}
```

So property and offer freshness need **no new policy decision** — only two
accessors beside the existing `request_threshold_days`, refusing in the same
way when the policy carries no usable value rather than assuming a default.
The three clocks stay separate: `properties.availability_last_confirmed_at`,
`property_offers.last_confirmed_at`, and
`property_offers.commercial_terms_last_confirmed_at`.

### 3.4 The public list is the tightest surface in the system

`getPublicProperties` is unauthenticated — one of the closed list of six
(RFC-001 R10.4). The contract's own description is the specification:

> Returns only PUBLIC properties with at least one active public commercial
> context backed by currently valid `PUBLIC_LISTING_ALLOWED` consent.
> Private/Potential records and internal fields are never projected here.
> Price fields obey `price_visibility`.

Three independent conditions, all required, plus a projection rule. We will
implement it as an explicit conjunction and test each condition's removal
separately, because a single over-broad predicate here leaks private supply to
anonymous callers. `seller_expectation_dzd` is already in the forbidden-field
lists at `src/turab/dto/boundaries.py:27`, `src/turab/auth/audit.py:37` and
`src/turab/observability.py:24`; this slice adds the offer DTOs to that
existing machinery rather than writing a parallel one.

### 3.5 Identity resolution is non-destructive — and the database already says so

Three triggers, not one service rule (`schema_v0.2.3.sql:1230–1263`):

- `trg_identity_alias` refuses an alias whose `(alias, canonical)` pair is not
  the candidate's own pair; refuses a canonical that is itself an alias; and
  refuses turning a property that is already canonical into an alias
  ("consolidate explicitly").
- `trg_identity_same_requires_alias` refuses setting a candidate to
  `CONFIRMED_SAME` **unless the alias row already exists** for that candidate.
- `property_identity_aliases.source_identity_candidate_id` is `NOT NULL
  UNIQUE`, so one candidate yields at most one alias.

The second trigger dictates the **write order** inside the transaction, and
this is the single most important implementation detail in this section:

```
BEGIN
  INSERT INTO property_identity_aliases (...)          -- alias FIRST
  UPDATE property_identity_candidates SET review_status = 'CONFIRMED_SAME'
COMMIT
```

The intuitive order — decide, then record the consequence — **fails**, because
the trigger on the candidate update looks for an alias that does not yet exist.
We would have discovered this by running into it; better to have read it first.

`CONFIRMED_DISTINCT` and `UNSURE` write no alias. **No property row is ever
deleted or merged** (`prevent_delete_properties`), and no `property_id` is
rewritten anywhere.

As in §3.2, these are P0001 exceptions with no constraint name, so the service
pre-checks — candidate exists, is `PENDING_REVIEW`, `canonical_property_id` is
one of its pair — under a lock on the candidate row, and the triggers are the
backstop.

Because Slice 4 is out of scope, the canonical-resolution helper
(`alias → canonical`) will be written and tested **as a query**, with the
consumer left unbuilt. This is the honest reading of the mandatory test "new
matching inputs must use canonical property, not alias": we can prove the
resolver; we cannot prove a matching input that does not exist. That limit
goes in the test docstring rather than being left implied.

---

## 4. Gaps: decisions required before implementation

### G3-1 · The offer state machine has no declared edges — **Workflow decision**

`OfferStateCommand` accepts any of `DRAFT, PENDING_INFO, ACTIVE, PAUSED,
WITHDRAWN, CLOSED`. The contract says "State machine validation required" and
declares **no edges anywhere** — not in the OpenAPI document, not in the
schema, not in the developer spec. This is the same shape as Slice 2's G-3,
which required your approval for `ACTIVE→PAUSED/CLOSED`.

We will not invent the graph. Proposed for ratification, by analogy with the
approved REQUEST table and no further:

| from | to |
|---|---|
| `DRAFT` | `PENDING_INFO`, `ACTIVE`, `WITHDRAWN` |
| `PENDING_INFO` | `ACTIVE`, `WITHDRAWN` |
| `ACTIVE` | `PAUSED`, `CLOSED`, `WITHDRAWN` |
| `PAUSED` | `ACTIVE`, `CLOSED`, `WITHDRAWN` |
| `WITHDRAWN` | *(terminal)* |
| `CLOSED` | *(terminal)* |

Open sub-questions we are **not** answering ourselves:
(a) may a CUSTOMER reach `CLOSED`, or only staff?
(b) does `ACTIVE` require a non-null price or a source link?
(c) is a reason code mandatory for `WITHDRAWN`/`CLOSED`, as
`REQUEST_CLOSURE` codes are for requests?

**Until this is ratified, `postOffersOfferIdState` will refuse every transition
with a typed 4xx naming the undecided rule** — the standing instruction that an
affected path rejects what it cannot prove. It will not be silently permissive.

### G3-2 · PROPERTY claim eligibility — **unchanged, still open (DL-08a)**

`PropertyClaimUndecided` (`src/turab/services/claims.py:108`) stays. This plan
neither resolves it nor routes around it. Two consequences we accept rather
than paper over:

- A customer gets authority over a property **only** as its creator account
  (RFC-001 R4.1). `party_property_relations` is not an authorization source
  (R4.5), and nothing in this slice will make it one.
- An `ASSISTED`/`UNCLAIMED` property created by staff therefore cannot be
  taken over by its real owner in this version. That is a product limitation,
  stated plainly, not a defect to be quietly fixed inside Slice 3.

### G3-3 · Availability transitions — **Workflow decision, smaller**

`availability_status` has seven values. Who may move a property to
`UNAVAILABLE` versus `NEEDS_CONFIRMATION`, and whether the staleness sweep may
set `NEEDS_CONFIRMATION` on properties the way it does on requests, is not
declared. Proposed: mirror the request rule exactly — the sweep sets
`NEEDS_CONFIRMATION` on a stale property, and reconfirmation clears it.
Everything else is a `PATCH` under the normal object-authority rules. **Awaiting
your ratification**; until then the sweep will not run against properties.

### G3-4 · Resolution authority and the maker-checker split — **Permissions question**

`postResolutions` allows ADMIN, OPERATOR and REVIEWER, and is **not** in
`SEPARATION_SENSITIVE_OPERATIONS`, while `postClaims` is. So as declared, one
OPERATOR may record a claim and then resolve it as the current value. We are
**not** treating that as a defect to fix, because the contract is the authority
and a correction may only narrow. We raise it as a question: is that intended,
or should resolution be separation-sensitive too? A narrowing correction is
available if you want it; we will not apply one unasked.

### G3-5 · Account provisioning — **unchanged operational gap**

Still open, still classified as before. It bounds what an end-to-end customer
trial can demonstrate in this slice exactly as it did in Slice 2.

---

## 5. STOP GATE C — the tests

STOP GATE C asks six questions. Each is answered by named tests, on real
PostgreSQL, and each test must fail against the defect it names.

| STOP GATE C question | Proving tests |
|---|---|
| what is the physical property? | `test_a_property_is_created_with_its_type_location_and_supply_mode`, `test_property_attributes_are_unique_per_definition` |
| what offers exist for it? | `test_owner_sale_broker_sale_and_rent_coexist_on_one_property`, `test_listing_a_property_returns_all_of_its_offers` |
| who supplied each fact? | `test_every_claim_names_its_source_or_observation`, `test_an_offer_links_to_its_sources_with_one_primary` |
| what is current vs historical? | `test_only_one_resolved_value_is_current_per_attribute`, `test_superseding_a_value_closes_the_previous_row_in_the_same_transaction`, `test_a_stale_offer_is_reported_stale_on_its_own_clock` |
| declared vs checked? | `test_a_claim_is_born_declared`, `test_only_a_confirmed_verification_event_raises_the_level`, `test_a_non_confirmed_outcome_records_the_event_and_changes_nothing` |
| canonical or alias? | `test_confirmed_same_writes_the_alias_and_the_review_together`, `test_the_canonical_resolver_returns_the_canonical_for_an_alias` |

### 5.1 The seven mandatory tests from the slices document

| Mandatory test | Planned test | Kind |
|---|---|---|
| same property may have owner sale + broker sale + rent simultaneously | `test_owner_sale_broker_sale_and_rent_coexist_on_one_property` | DB |
| seller expectation is not in public/customer DTOs | `test_seller_expectation_never_appears_in_a_public_or_customer_payload` | DTO boundary |
| claim cannot be created as `DOCUMENT_SEEN` directly | `test_a_claim_cannot_be_created_already_verified` | **contract boundary** (§3.1) |
| verification event required to upgrade | `test_only_a_confirmed_verification_event_raises_the_level` | **schema trigger** (§3.1) |
| resolution cannot point to a claim from another property or attribute | `test_a_resolution_cannot_cite_a_claim_about_another_subject`, `test_a_resolution_cannot_cite_a_claim_about_another_attribute` | **schema trigger** + service pre-check for the typed 4xx (§3.2) |
| `CONFIRMED_SAME` without canonical alias mapping fails | `test_confirmed_same_without_a_canonical_id_is_refused`, `test_the_canonical_must_be_one_of_the_candidate_pair` | **schema trigger** + service pre-check (§3.5) |
| new matching inputs must use canonical, not alias | `test_the_canonical_resolver_returns_the_canonical_for_an_alias` | **narrowed — see §3.5** |

### 5.2 Concurrency tests, on the method Slice 2 ended with

Two engines, two transactions, interleaving witnessed through
`pg_stat_activity`, every worker's outcome asserted:

- `test_two_concurrent_resolutions_of_one_attribute_yield_one_current_value`
  — the partial unique index is the contended resource; the loser must get a
  typed 409 from the named constraint, not a 500.
- `test_two_concurrent_reviews_of_one_candidate_produce_one_alias`
  — `source_identity_candidate_id` is UNIQUE; same shape.
- `test_a_concurrent_verification_event_does_not_lower_a_raised_level`
  — **reclassified.** `GREATEST(...)` inside the trigger's single `UPDATE`
  makes this a database guarantee, not a locking problem, so this test proves
  the schema and not our code. It is kept for the STOP GATE C answer and
  labelled as a schema test. Sketching it as a locking test would have been
  the same error the acceptance review caught in E-01: a true result filed
  under a false cause.

### 5.3 What these tests will not claim

Stated now, so it is not discovered later:

- The canonical resolver is proven **as a query**. No matching input exists to
  consume it (§3.5).
- Consent-backed public listing is proven against seeded consent rows. It does
  not prove any consent *capture* flow, which is not in this slice.
- With G3-1 unratified, the offer state tests prove only the **refusal**. The
  edge table is untested until it is approved.
- Several guarantees in §5.1 are the **schema's**, not ours (§3.1, §3.2, §3.5).
  We will label each test with what it proves, and we will not present a
  passing schema test as evidence that our service does something.

### 5.4 So what IS the service's work?

Worth stating explicitly, since §3 moved so much of it into the database. What
remains on our side is real, and it is where the defects will be:

1. **Authorization and object scope** on all nineteen operations — the whole of
   §1, none of which the schema knows about.
2. **Turning database refusals into typed HTTP errors**, by pre-check under the
   right lock, since P0001 carries no constraint name (§3.2).
3. **Transaction composition** — the alias-before-status order (§3.5); closing
   the previous resolved value and inserting the new one atomically.
4. **Projection and DTO boundaries**, above all the unauthenticated public list
   (§3.4). The schema will not stop us leaking `seller_expectation_dzd`.
5. **Freshness evaluation** on two new clocks (§3.3).
6. **Deterministic candidate generation** — `postIdentityCandidatesGenerate` is
   entirely ours; the schema stores its output and reviews, not its signals.
7. **Idempotency, provenance and audit plumbing** for every new command, on the
   Slice 1/2 machinery.

---

## 6. Acceptance conditions for this slice

1. Every operation in §1 implemented, or explicitly refusing with a typed
   error that names an undecided rule (§4). No operation silently permissive.
2. Every mandatory test in §5.1 passing on real PostgreSQL, each demonstrated
   to fail against the defect it names.
3. STOP GATE C answerable on all six questions, with the named evidence.
4. No new table, column or migration (§2) — or an explicit finding if one
   proves necessary.
5. The evidence matrix regenerated with 0 UNPROVEN, and the gate still 8/8.
6. **Matching not started.** No `match_candidates` row is written by any code
   path in this slice.
7. **PROPERTY claim eligibility still undecided**, and no path creates a
   property-party authority link as a side effect.
8. Run provenance recorded at run time, with the committed fingerprint recipe.

---

## 7. Sequence, and where we would stop

| Step | Content | Stops at |
|---|---|---|
| 1 | PROPERTY: create, read, patch, `/me` view, internal view | needs nothing from §4 |
| 2 | OFFER: create, patch, sources; **state refuses** | **G3-1** |
| 3 | Freshness for property and offer; reconfirm on both | **G3-3** for the sweep only |
| 4 | Truth layer: observation → claim → verification → resolution | needs nothing; **G3-4** is a question, not a blocker |
| 5 | Public list, with its three conditions and projection | needs nothing |
| 6 | Identity Lite: generate, list, review, alias, resolver | needs nothing |
| 7 | STOP GATE C evidence and the concurrency tests | — |

Steps 1, 4, 5 and 6 can begin on approval of this plan alone. Step 2 delivers a
refusing endpoint until **G3-1** is ratified. Step 3's sweep waits on **G3-3**.

**We are asking for:** approval of this scope and sequence; a decision on
**G3-1** (the edge table and its three sub-questions); a decision on **G3-3**;
and an answer on **G3-4**. **G3-2** and **G3-5** we expect to remain open, and
this plan is built so that they can.
