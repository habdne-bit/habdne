# Slice 3 — PROPERTY / OFFER / SOURCE / Truth Layer / Identity Lite
## Implementation plan — **revision 3**

**Status:** **steps 1–8 authorised**; G3-6 awaits its Contract Delta.
**Baseline:** Handoff v1.0.3 / technical pack v0.2.3, frozen.
**Authority for the scope:** `docs/handoff/06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md:127–166`.
**Predecessor:** Slice 2, closed within its agreed scope at `94639a6`.

### Revision 3 — the authorisation and the two corrections

Steps 1–8 are authorised on the scope reported, under five standing limits,
each of which is an acceptance condition in §7:

1. No Matching, and nothing written to `match_candidates`.
2. No party-property relation inferred from any act.
3. `party_property_relations` never used as an authorization source.
4. No code on the G3-6 path before its contract addition is approved (§4.4).
5. **Slice 3 is not declared closed** until G3-6 is delivered or its deferral
   is explicitly approved in a later decision.

The 485 tests and the 8/8 gate remain **our own saved run**; the reviewer
states they did not independently re-run commit `3447a7d`, and we do not
present the authorisation as confirmation that they did.

Two things changed in the plan itself:

- **G3-6 is decided** — option A, delivered as a Contract Delta before any code
  on that path (§4.4).
- **The contention claim is corrected, in four places not one** (§2.1, §3.6,
  §6.3). A unique index is not a concurrency contract: where a lock serialises
  two paths, both succeed. We found the same flawed claim in the resolution
  test, which the review had not named, and corrected it too.

### What changed in revision 2

Revision 1 was accepted in outline and returned with ten items. All ten are
folded in below. Three were decisions we had asked for, one resolved a question,
and six were corrections to our work — five of which we confirm, and **one of
which we must correct back**, because the schema does not say what the review
took it to say (§3.6).

| # | Item | Disposition |
|---|---|---|
| 1 | G3-1 offer state machine | **Ratified** — §3.5, §4.1 |
| 2 | G3-3 availability and freshness | **Ratified** — §3.3, §3.4, §4.2 |
| 3 | G3-4 resolution authority | **Resolved, no contract correction** — §3.7, §4.3 |
| 4 | SOURCE is not creatable — add 3 operations | **Confirmed; scope now 22 operations** — §1.5 |
| 5 | `party_property_relations` has no create path | **Confirmed; recorded as G3-6, blocking** — §4.4 |
| 6 | The authorization table was too coarse | **Confirmed; rewritten from RFC-001 §4.6** — §5 |
| 7 | The claim-provenance test was narrower than the contract | **Confirmed; test replaced** — §3.8 |
| 8 | "the schema allows several `is_primary=true`" | **Corrected back** — the index exists (§3.6) |
| 9 | Controlled options must be read, not copied | **Confirmed; added** — §3.9 |
| 10 | Identity: corrective effect, version, reproducibility, race | **Confirmed; added** — §3.10 |

Two boundaries hold throughout, restated as acceptance conditions in §7:

1. **Matching is not entered.** No candidate generation, no hard gate, no
   ranking, no `match_candidates` row written by any path in this slice. The
   corrective effect in §3.10 acts on records that already exist; it creates
   no match.
2. **PROPERTY claim eligibility is not decided, and not decided implicitly.**
   `PropertyClaimUndecided` stays exactly as it is, and no path added here may
   create a property-party authority link as a side effect.

---

## 1. Operations in scope — twenty-two

All twenty-two are already declared in the effective contract
(`docs/api/openapi_effective_v0.2.3.yaml`). **No operation is invented, no
contract correction is proposed, and no migration is proposed.**

### 1.1 Physical property

| operationId | Method · Path | Roles |
|---|---|---|
| `postProperties` | POST `/properties` | ADMIN, OPERATOR, CUSTOMER |
| `getPropertiesPropertyId` | GET `/properties/{id}` | ADMIN, OPERATOR, REVIEWER |
| `getMePropertiesPropertyId` | GET `/me/properties/{id}` | CUSTOMER |
| `patchPropertiesPropertyId` | PATCH `/properties/{id}` | ADMIN, OPERATOR, CUSTOMER |
| `postPropertiesPropertyIdReconfirm` | POST `/properties/{id}/reconfirm` | ADMIN, OPERATOR, CUSTOMER |
| `getPublicProperties` | GET `/public/properties` | **unauthenticated** |
| `getBackofficeQueuesProperties` | GET `/backoffice/queues/properties` | ADMIN, OPERATOR, REVIEWER |

### 1.2 Commercial offers

| operationId | Method · Path | Roles |
|---|---|---|
| `postPropertiesPropertyIdOffers` | POST `/properties/{id}/offers` | ADMIN, OPERATOR, CUSTOMER |
| `patchOffersOfferId` | PATCH `/offers/{id}` | ADMIN, OPERATOR, CUSTOMER |
| `postOffersOfferIdState` | POST `/offers/{id}/state` | ADMIN, OPERATOR, CUSTOMER |
| `postOffersOfferIdReconfirm` | POST `/offers/{id}/reconfirm` | ADMIN, OPERATOR, CUSTOMER |
| `postOffersOfferIdSources` | POST `/offers/{id}/sources` | ADMIN, OPERATOR |

### 1.3 Truth layer

| operationId | Method · Path | Roles | Note |
|---|---|---|---|
| `postObservations` | POST `/observations` | ADMIN, OPERATOR | separation-sensitive |
| `postClaims` | POST `/claims` | ADMIN, OPERATOR | separation-sensitive |
| `postClaimsClaimIdVerificationEvents` | POST `/claims/{id}/verification-events` | ADMIN, OPERATOR, REVIEWER | the only level-raising path |
| `postResolutions` | POST `/resolutions` | ADMIN, OPERATOR, REVIEWER | §3.7 |

### 1.4 Identity Lite

| operationId | Method · Path | Roles | Note |
|---|---|---|---|
| `postIdentityCandidatesGenerate` | POST `/identity/candidates/generate` | ADMIN, OPERATOR | deterministic signals |
| `getIdentityCandidates` | GET `/identity/candidates` | ADMIN, OPERATOR, REVIEWER | — |
| `postIdentityCandidatesCandidateIdReview` | POST `/identity/candidates/{id}/review` | ADMIN, **REVIEWER** | separation-sensitive; **OPERATOR excluded** |

### 1.5 SOURCE — the three operations added in revision 2

**The review is right, and the gap was real.** `postOffersOfferIdSources`
takes `{source_id, is_primary}` and links a source that must already exist. We
checked every path and schema in the effective contract: **no operation creates
a `sources` row except through `ExternalLeadCreate`**, whose `source` object
(`kind` required, plus `external_url`, `external_ref`, `title`, `raw_text`,
`captured_at`, `metadata`) is the only declared shape for one.

So revision 1 planned a "sources and offer-source links" deliverable with no
way to create a source. Adding these is not a new feature; it is the contractual
path that makes the deliverable reachable:

| operationId | Method · Path | Roles | Why it is required |
|---|---|---|---|
| `postExternalLeads` | POST `/external-leads` | ADMIN, OPERATOR | the only declared SOURCE creation path |
| `postExternalLeadsLeadIdConvert` | POST `/external-leads/{lead_id}/convert` | ADMIN, OPERATOR | body requires **`party_id` and `consent_id`** — the conversion is where provenance and consent are captured |
| `getBackofficeQueuesExternalLeads` | GET `/backoffice/queues/external-leads` | ADMIN, OPERATOR, REVIEWER | the queue that makes an unconverted lead visible rather than lost |

Note what the convert body's two required fields mean: a lead cannot become a
PROPERTY or REQUEST without naming both the party and the consent that permits
it. That is ADR-04 (resource-bound consent) enforced at the contract boundary,
and it is the reason this operation belongs with the other two rather than
being deferred.

---

## 2. Deliverables mapped to the frozen schema

Every table exists in `schema_v0.2.3.sql`. **No new table, column or migration
is proposed.** If implementation shows one is needed, that is a finding to
bring back, not a thing to add quietly — and specifically, **no `OFFER_STATE`
reason-code category will be created**.

| Deliverable | Tables |
|---|---|
| physical PROPERTY record | `properties`, `property_attributes` |
| PUBLIC / PRIVATE / POTENTIAL supply modes | `supply_mode` on `properties` |
| several offers for one physical property | `property_offers` |
| terms, visibility, negotiability, seller expectation, commercial freshness | `property_offers` columns |
| sources and offer-source links | `sources`, `property_offer_sources`, `external_leads` |
| party-property relations | `party_property_relations` — **but see G3-6, §4.4** |
| observation → claim → verification → resolution | `observations`, `claims`, `verification_events`, `resolved_values` |
| controlled right/document options | `attribute_definitions`, `attribute_options` |
| identity candidate generation | `property_identity_candidates` |
| human review, non-destructive alias→canonical | `property_identity_aliases` |

### 2.1 What the database already enforces

Revision 1's first draft assumed the service owned rules the schema enforces
itself. Reading the trigger and index definitions corrected that, and the
correction changes the design rather than decorating it:

| Guarantee | Mechanism | Line |
|---|---|---|
| a claim's level rises only via a `CONFIRMED` event, and never falls | `trg_apply_verification_event`, using `GREATEST(...)` | 1149 |
| a resolution cannot cite a claim about another subject or attribute | `trg_resolution_lineage` | 1134 |
| one current resolved value per subject+attribute | `ux_resolved_current_*` (4 partial unique indexes) | — |
| `CONFIRMED_SAME` requires the alias row **already present** | `trg_identity_same_requires_alias` | 1262 |
| alias/canonical must be the candidate's own pair; no alias chains | `trg_identity_alias` | 1249 |
| **at most one primary source per offer** | `ux_offer_primary_source` — partial unique index | **1352** |
| one identity candidate per unordered pair | `ux_identity_pair` | 618 |
| core records cannot be deleted | `prevent_delete_*` | 1302–1307 |

The schema also states the §3.8 rule in its own words:

> `COMMENT ON COLUMN claims.effective_verification_level IS 'Derived
> operational verification level. API clients MUST NOT set this above DECLARED
> directly.'`

**Two error paths, deliberately distinct.** The triggers use `RAISE EXCEPTION`
(SQLSTATE **P0001**), so `exc.orig.diag.constraint_name` is **empty** and the
constraint-name mapping we built for `DUPLICATE_CRITERION_SLOT` **cannot** be
reused for them:

| violation | mechanism | how it becomes a typed 4xx |
|---|---|---|
| duplicate current value; two primary sources; duplicate candidate pair | **named unique index** | SAVEPOINT + `constraint_name`, exactly as in R-S2-03 |
| lineage, identity pair, `CONFIRMED_SAME` without alias | **trigger → P0001** | **pre-check under a row lock**, inside the write transaction; the trigger stays as the backstop |

We will not match on an exception's message text to identify a P0001 — a
message is not an interface. The pre-check is the mapping; the trigger is what
makes a missed pre-check safe rather than silent.

**And a unique index is not a concurrency contract.** Mapping a named index to
a typed 409 says what happens *if* it is violated. It does not make a violation
the expected outcome of contention: where a lock serialises two paths, both
succeed, and only a **declared** version guard produces a winner and a loser.
Revision 2 confused the two; §6.3 states the corrected expectation for each
concurrency test.

---

## 3. Rules, as ratified and as derived

### 3.1 A claim may not be born verified; the database raises the level

`ClaimInput` has `additionalProperties: false` and **no** verification-level
field; `claims.effective_verification_level` defaults to `DECLARED`. The rule
is enforced at the **contract boundary**, and the mandatory test for it is a
boundary test — we will label it as one rather than add a service check and
take credit for a guarantee the contract already gives.

The upgrade is the database's: `trg_apply_verification_event` fires
`AFTER INSERT ON verification_events` and, on `CONFIRMED`, sets
`GREATEST(effective_verification_level, NEW.level)`; on `CONFLICT_FOUND` it
sets `status = 'CONFLICTING'`. Consequences: the service **must not also write
the level** (a second write racing the trigger); `NOT_CONFIRMED` and
`INCONCLUSIVE` are handled by the trigger doing nothing; and a later lower-level
`CONFIRMED` cannot lower the claim, in a single statement, without any lock.

### 3.2 A resolution cannot point outside its own subject

Enforced by `trg_resolution_lineage`. The service pre-checks under a row lock
on the claim so the refusal is a typed 4xx rather than a 500 (§2.1).

### 3.3 Property availability is a fact, not a workflow — **ratified (G3-3)**

`availability_status` is an operational fact that changes, not a state machine
with edges. The contract already draws the line, and we verified it:

- `PropertyPatch` has `additionalProperties: false` and its properties are
  exactly `property_type`, `canonical_location_id`, `local_location_detail`,
  `land_area_m2`, `built_area_m2`. **Availability is not among them** — so
  PATCH cannot change it, by the contract, not by our choice.
- `POST /properties/{id}/reconfirm` **requires** `availability` (enum of all
  seven values) and accepts `confirmed_at`. This is the change path.
- `PropertyCreate` does carry `current_availability`, so the initial value is
  set at creation and every later change goes through reconfirm.

Ratified rules:

1. Reconfirmation may move between **any** two availability values. It records
   a new fact; it does not traverse an edge. No transition table exists and
   none will be invented.
2. The sender states the confirmed value **explicitly**. Reconfirmation never
   restores an implicitly remembered previous state.
3. Every reconfirmation stamps the confirmation time, its actor and its channel,
   and writes the provenance trail — the Slice 2 machinery, unchanged.
4. **The staleness pass converts to `NEEDS_CONFIRMATION` only** properties whose
   current value is one of:
   `AVAILABLE`, `POTENTIALLY_AVAILABLE`, `UNDER_DISCUSSION`,
   `TEMPORARILY_UNAVAILABLE`.
   It **never touches** `UNKNOWN`, `NEEDS_CONFIRMATION` or `UNAVAILABLE`.

The four-value set is a predicate in the `UPDATE`'s `WHERE` clause and is
re-asserted inside the statement, the way the request sweep now is. A test will
assert each of the three excluded values is left alone, individually — a single
"the others are untouched" assertion would pass on a predicate that excluded
only one of them.

### 3.4 Offer freshness — one policy, two columns — **ratified**

Correcting revision 1, which implied three independent freshness policies:

- The **policy** for an offer is `offer_terms` (seeded at 14 days), and it is
  evaluated on **`commercial_terms_last_confirmed_at`**. That column, not
  `last_confirmed_at`, is the one the policy reads.
- `postOffersOfferIdReconfirm` updates **both** `last_confirmed_at` and
  `commercial_terms_last_confirmed_at` **together** in v0.1.
- The two are therefore **not** presented as two independent freshness
  policies. One declared policy governs commercial terms.

The seeded active policy already carries all three thresholds
(`seed_master_data_v0.2.3.sql:178`):

```
"freshness_threshold_days": {"request": 30, "property": 30, "offer_terms": 14}
```

so no new policy decision is needed — only two accessors beside the existing
`request_threshold_days`, refusing the same way when the policy carries no
usable value rather than assuming a default.

Note that `/offers/{id}/reconfirm` takes `StateReconfirm` — the same body as
the request reconfirm — so the naive-datetime refusal corrected in R-S2-05b
applies to it for free, and will be tested on this endpoint too rather than
assumed to carry over.

### 3.5 The offer state machine — **ratified (G3-1)**

Adopted exactly as given.

| from | allowed to |
|---|---|
| `DRAFT` | `PENDING_INFO`, `ACTIVE`, `WITHDRAWN`, `CLOSED` |
| `PENDING_INFO` | `ACTIVE`, `WITHDRAWN`, `CLOSED` |
| `ACTIVE` | `PENDING_INFO`, `PAUSED`, `WITHDRAWN`, `CLOSED` |
| `PAUSED` | `PENDING_INFO`, `ACTIVE`, `WITHDRAWN`, `CLOSED` |
| `WITHDRAWN` | terminal |
| `CLOSED` | terminal |

**CUSTOMER is narrower**, and the narrowing is a second gate applied after the
edge check, not a separate table:

| from | CUSTOMER may reach |
|---|---|
| `DRAFT` | `ACTIVE`, `WITHDRAWN` |
| `PENDING_INFO` | `ACTIVE`, `WITHDRAWN` |
| `ACTIVE` | `PAUSED`, `WITHDRAWN` |
| `PAUSED` | `ACTIVE`, `WITHDRAWN` |

A CUSTOMER may **never** set `PENDING_INFO` or `CLOSED`; both are staff-only.
The distinction is recorded in the code, not only here: `CLOSED` is an
**operational closure**, `WITHDRAWN` is **the offer holder withdrawing**. A
customer refused `CLOSED` gets a message that says so, rather than a bare 403.

Also ratified, and each one removes a check we might otherwise have added:

- **No non-null price is required to activate.** The contract permits an
  unknown price, `ON_REQUEST` and `PRIVATE`; requiring one would narrow the
  contract without a correction.
- **No SOURCE is required to activate a self-entered offer.**
- **`reason_code` stays optional** in this slice. If supplied it must be
  **validated against `reason_codes` and persisted in a durable trail** — never
  accepted and dropped. Since `property_offers` has no reason column and no
  migration is permitted, it is persisted through the provenance trail
  (`observations` + `claims`) and the audit row, which are durable and
  reviewable. A supplied code that does not exist is a typed 422.

A test asserts a supplied `reason_code` is **readable back** after the
transition. "Persisted" must mean retrievable, not merely written somewhere.

### 3.6 Offer sources — a correction back to the review

The review states the schema permits more than one `is_primary = true` per
offer and asks us to implement the rule in the service. **The schema already
enforces it**, at `schema_v0.2.3.sql:1352`:

```sql
CREATE UNIQUE INDEX ux_offer_primary_source ON property_offer_sources(offer_id) WHERE is_primary;
```

This is a partial unique index in the frozen baseline. A second primary link
raises a unique violation, not a silent duplicate.

The requirement is adopted in full regardless, and the mechanism makes it
cleaner rather than redundant:

1. Linking a new source as primary **transfers** the flag: inside one
   transaction, under a lock on the **parent offer**, the existing primary is
   cleared and the new link is set primary. **No other link is deleted.**
2. Ordering matters — clear first, then set — because the index would otherwise
   reject the intermediate state.
3. Because this is a **named** index, the collision maps by `constraint_name`
   inside a SAVEPOINT, exactly as `DUPLICATE_CRITERION_SLOT` does. It is in the
   first row of §2.1's table, not the second.
4. The contention test is added — **but with the assertion the second review
   corrected, not the one revision 2 first wrote.**

**The corrected contention claim.** Revision 2 implied that two concurrent
primary links produce a winner and a 409 loser. That was wrong, and the reason
matters: **the parent-offer lock is precisely what prevents the collision.**
Two transactions that both follow the clear-then-set path serialise on that
lock, and the second then clears the primary the first has just set before
setting its own. With no `expected_version` and no declared compare-and-set in
the contract for this operation, **both legitimately succeed**, and the final
primary is the one the last committer set. Demanding a 409 would have been a
test asserting a behaviour the contract does not specify — and, worse, one that
could only be made to pass by *removing* the lock.

The SAVEPOINT mapping of `ux_offer_primary_source` to a typed 409 stays
required for when the index is genuinely violated. It is simply not the normal
outcome of two lock-serialised paths.

So `test_two_concurrent_primary_source_links_leave_exactly_one_primary` asserts:

1. **No committed moment and no final state has more than one primary** — the
   invariant, checked on the committed rows, not on a timing guess.
2. **Both workers' outcomes are asserted**, by the Slice 2 harness rule: each
   either returns its value or raises a named domain refusal, and anything else
   fails the test.
3. **The final primary matches the lock-acquisition / commit order**, which the
   deterministic handshake establishes rather than assumes.
4. **No 500 appears** from either worker.
5. **No worker is required to lose.** If a real winner/loser outcome is ever
   wanted here, it needs a **declared version guard**; it will not be inferred
   from the index, and we will not add one unasked.

### 3.7 Resolution authority — **resolved (G3-4)**

No contract correction. `postResolutions` stays open to ADMIN, OPERATOR and
REVIEWER.

We accept the reasoning and record it, because it corrects a
misunderstanding on our side worth writing down:
`SEPARATION_SENSITIVE_OPERATIONS` prevents **one account from holding both
OPERATOR and REVIEWER**. It is not a row-level maker/checker check, and adding
`postResolutions` to it would not have stopped one OPERATOR from writing a
claim and then resolving it. We had raised the question as though it would.

In v0.1 an OPERATOR may record the current operational value, on five
conditions, each of which is a test:

1. `resolved_by_account_id` is recorded on every resolution.
2. History is **preserved, never overwritten**: the previous row is closed
   (`valid_to`, `resolution_status`), and `prevent_delete_resolutions` makes
   deletion impossible anyway.
3. `source_claim_id` is stored whenever one was used.
4. **AI and background jobs may not issue a resolution on their own.** The
   command requires an acting human account; a machine channel is refused.
5. The whole operation stays audited and reviewable —
   `audit_resolved_values` fires on every insert and update.

### 3.8 Claim provenance — the test we had was too narrow

Confirmed, and our proposed test was wrong. "Every claim carries a source or an
observation" would refuse a **direct assertion by a party**, which the contract
permits: `ClaimInput` offers `asserted_by_party_id`, `source_id` and
`observation_id`, and requires none of them.

Adopted rule:

> Every claim must carry **at least one** origin among
> `asserted_by_party_id`, `source_id`, `observation_id`.

And the distinction that makes it meaningful: `recorded_by_account_id`
identifies **who entered** the information; it does not establish **where it
came from**, and it does not satisfy the rule. A claim recorded by an operator
with none of the three origins is refused.

Consistency rule: if a claim carries **both** `source_id` and `observation_id`,
and that observation itself has a `source_id`, the two must agree. A claim that
names one source while citing an observation from another is refused rather
than silently keeping both.

### 3.9 Controlled options are read, never copied

Confirmed and adopted. The service reads `attribute_definitions` and
`attribute_options`; no list is duplicated in Python, for the same reason the
criterion registry is not:

- `attribute_code` must exist and be `active`.
- If `value_type = 'ENUM'`, the value must be a **registered, active**
  `option_code` for that definition.
- `applies_to` (a `property_type[]`) is honoured: a definition that does not
  apply to the property's type is refused for that property.
- The rule applies to **`claims`, `resolutions` and `property_attributes`
  updates alike** — one validator, three call sites, so the three cannot drift.

`attribute_definitions` carries `value_type IN ('TEXT','NUMBER','BOOLEAN',
'ENUM','DATE','JSON')`, and `trg_property_attribute_claim` already enforces
that `property_attributes.resolved_claim_id` refers to the same property and
attribute — another P0001 to pre-check (§2.1).

### 3.10 Identity Lite — **corrective effect, version, reproducibility, race**

**The corrective effect is required, and ADR-03 says so in its own words**
(`ARCHITECTURE_DECISIONS_v0.2.md:42`):

> An identity-resolution command is transactional: create alias mapping, mark
> the candidate `CONFIRMED_SAME`, **then detect any affected open
> matches/opportunities and create review work where necessary.**

So `CONFIRMED_SAME` is three steps, not two. The third acts on **records that
already exist** — it starts no matching, generates no candidate, and writes no
`match_candidates` row. It finds open matches and opportunities pointing at the
property that has just become an alias, and raises review work for them.

The write order is dictated by the schema, and it is the opposite of the
intuitive one:

```
BEGIN
  INSERT INTO property_identity_aliases (...)        -- alias FIRST
  UPDATE property_identity_candidates SET review_status = 'CONFIRMED_SAME'
  -- then: detect affected open matches/opportunities, raise review work
COMMIT
```

`trg_identity_same_requires_alias` rejects the candidate update unless the
alias already exists, so "decide, then record the consequence" fails.

**Version.** The contract defaults `algorithm_version` to `rules-0.1.0`; the
column defaults to `rules-0.2.0`. The stored value would otherwise depend on
which default applied — a silent dependency on where the field was omitted. The
service therefore **writes the value explicitly, always**: the contractual
`rules-0.1.0` when the caller omits it, the caller's value when given. The
column default is never allowed to decide. A test asserts an omitted version is
stored as `rules-0.1.0`, which fails if the service ever lets the column
default through.

**Reproducibility.** The signals and their algorithm are documented, versioned
and deterministic: same inputs, same version ⇒ same candidate set, same
`signals` and `explanation` payloads. A test generates twice and compares.

**No automatic merge.** Signals propose; a human decides. Generation only ever
writes `PENDING_REVIEW` rows, and no code path sets `CONFIRMED_SAME` without a
reviewer account.

**The pair race.** `ux_identity_pair` is unique on
`(LEAST(a,b), GREATEST(a,b))`, so generating the same pair twice — sequentially
or concurrently — must be handled, not crash. Re-generation is idempotent for a
pending pair, and the concurrent case maps the named index inside a SAVEPOINT
(§2.1, first row). Test:
`test_generating_the_same_pair_twice_concurrently_yields_one_candidate`.

**Authority follows the alias (R4.9).** A customer authorized on an alias
property is authorized on the canonical record — identity resolution must not
strip a real owner of access. This is an authorization consequence of this
slice and is tested as S13 in §5.

---

## 4. Gaps and decisions

### 4.1 G3-1 · offer state machine — **RATIFIED**, closed

§3.5. `postOffersOfferIdState` implements the edge table and the CUSTOMER
narrowing. It no longer refuses every transition.

### 4.2 G3-3 · availability and freshness — **RATIFIED**, closed

§3.3 and §3.4. The staleness pass may run against properties, restricted to
the four named source values.

### 4.3 G3-4 · resolution authority — **RESOLVED**, closed

§3.7. No contract correction; five conditions, each tested.

### 4.4 G3-6 · party-property relations — **DECIDED: option A, via a Contract Delta**

The gap is confirmed and was accepted: no operation, path or schema creates
`party_property_relations`; neither `PropertyCreate` nor `OfferCreate` carries
`relation_code`; the only contract schema whose text mentions a relation at all
is `PhoneInput`, which is unrelated.

**Ratified: option A — explicit operations for managing a party's relation to a
property.** The reasons given, recorded because they rule out the alternatives
on principle rather than convenience:

- A field on `PropertyCreate` (option B) **binds two independent concepts** and
  cannot express a relation added later, nor several relations on one property.
- Routing it through the truth layer (option C) **conflates the party asserting
  a fact with the party related to the property**, and reuses provenance
  machinery as though it were a domain fact. We had leaned toward C for costing
  no contract change; that was the wrong criterion.
- Deferral (option D) leaves a Slice 3 deliverable absent and blocks closure.

**This is a contract ADDITION, not a narrowing correction**, so the overlay
cannot carry it. Binding constraints:

1. `openapi_v0.2.3.yaml` stays **untouched**.
2. The operation is **not** added through the correction overlay.
3. A next contract package, or a standalone **Contract Delta**, is submitted and
   approved **before any code for this path is written**.
4. **No relation row is written**, and neither `claims` nor `observations` is
   repurposed to create one implicitly, until that approval.

The Contract Delta must cover, at minimum: creation, retrieval and **ending the
validity** of a relation; the permitted roles; `relation_code` and the temporal
values; that the **default creation level is `DECLARED`** and a customer cannot
assert a higher verification level without a declared verification mechanism;
idempotency and audit; the meaning of duplicate or temporally overlapping rows
if they are to be forbidden; and an **explicit statement that a relation grants
no access authority**.

It is delivered as `docs/gate/CONTRACT_DELTA_G3-6_party_property_relations.md`
for review before implementation. The rest of Slice 3 proceeds in parallel.

**Closure condition carried forward:** Slice 3 is not declared closed until
G3-6 is delivered, or its deferral is approved in an explicit later decision.

**A consequence found while drafting the Delta, and demonstrated on the live
database.** `enforce_consent_binding` requires an **active party-property
relation** before a **property-scoped** consent binding may be created
(`schema_v0.2.3.sql:1092-1099`). With no way to create a relation, that branch
of `postConsentsBindings` — an operation already implemented in Slice 1 — is
**unreachable**:

```
ERROR:  Property consent party has no active property relation
CONTEXT:  PL/pgSQL function enforce_consent_binding() line 33 at RAISE
```

The public list is **not** affected: its consent binds to the **offer**, whose
branch of the trigger checks `property_offers.party_id`. But this means G3-6 is
a blocking dependency, not only a missing deliverable. The current suite does
not reveal it because the fixtures insert relation rows directly; that is noted
in the Delta rather than left for someone to trip over.

### 4.5 G3-2 · PROPERTY claim eligibility — **open, unchanged**

`PropertyClaimUndecided` stays. A customer obtains authority over a property
only as its creator account (R4.1); an `ASSISTED`/`UNCLAIMED` property cannot
be taken over by its real owner in this version. Stated as a product
limitation, not quietly fixed inside this slice.

### 4.6 G3-5 · account provisioning — **open, unchanged**

Bounds what an end-to-end customer trial can demonstrate, exactly as in
Slice 2.

---

## 5. Object authorization, rewritten from RFC-001 §4.6

Revision 1 wrote "customer: own only" in a table column. That is too coarse to
implement from and too coarse to review, and the review is right to reject it.
The actual rules, quoted from their source:

**PROPERTY** (RFC-001 R4.1; §4.4 resource table, line 181):

> creator account **or** a valid `record_claim_event` for that account — the
> disjunction of those two facts **and nothing else**.

**PROPERTY_OFFER** (RFC-001 §4.6; Q9 at line 34; §4.4 resource table, line 182) — a disjunction of two
conditions, the second of which is itself a **conjunction of three**:

> 1. the offer's **creator account**; **or**
> 2. a valid **claim on the parent property** **and** `offer.party_id` matching
>    the account's party **and** the parent property being **`CLAIMED`**.

And the two negatives, which are where the bugs would be:

- **Party match alone never grants** (R4.12). `offer.party_id` equal to the
  account's party is one of three conjuncts, never sufficient by itself.
- **`party_property_relations` alone never grants** (R4.5, R4.12), whatever the
  `relation_code`, and whatever its `verification_level`.
- **Claiming a property does not open other parties' offers on it** (R4.13).

**Alias resolution (R4.9):** authority resolves through
`property_identity_aliases` to the canonical property first. A customer
authorized on an alias is authorized on the canonical record.

### 5.1 The RFC-001 scenarios this slice must prove

Taken from the RFC's own matrix (lines 590–606), restricted to the resources
this slice introduces. Each is a test, named for its scenario.

| # | Scenario | Expected |
|---|---|---|
| S10 | customer reads a property they created | **allow** 200 (R4.1) |
| S11 | property whose `created_by_account_id` is `NULL` | **deny** 404 (R4.3) |
| S12 | customer with any `relation_code`, incl. `OWNER_DECLARED`, no claim, not creator | **deny** 404 (R4.5) |
| S13 | customer authorized on an **alias** reads the **canonical** | **allow** 200 (R4.9) |
| S14 | any customer reads an `ASSISTED + UNCLAIMED` property | **deny** 404 (R4.10) |
| S15 | the same record after a successful claim | **allow** 200 (R4.1) |
| S16 | relation is `DECLARED` not verified, but a claim exists | **allow** 200 (R4.7) |
| S16a | claimed owner whose relation row has **expired** | **allow** 200 (R4.6) |
| S16b | second account of the **same party** reads a property claimed by the first | **deny** 404 (R4.2) |
| S16d | owner who claimed a property reads **their own** offer on it | **allow** 200 (§4.6 cond. 2) |
| S16e | the same owner reads the **broker's** offer on that property | **deny** 404 (R4.13) |
| S16f | broker reads the offer **they created**, no claim on the parent | **allow** 200 (§4.6 cond. 1) |
| S16g | party match on the offer, no parent claim, not creator | **deny** 404 (R4.12) |
| S16h | customer holding only a relations row reads an offer | **deny** 404 (R4.12) |
| S16i | authorized owner whose account is later `DISABLED` | **deny** 404 (R4.11a) |
| S16j | account in `INVITED` or `SUSPENDED` | **deny** 404 (R4.11a) |

S12, S16g and S16h are the three that a plausible-looking implementation would
get wrong, and S16e is the one a "the owner owns the property, so they own its
offers" shortcut would break. They are listed individually so none can be
satisfied by a single over-broad rule.

**A note on S12 and S16h under G3-6.** With no path creating relation rows
(§4.4), these two tests must insert the relation directly in their fixture to
set up the case. That is legitimate — they prove a relation row grants nothing
— but it will be stated in the docstring, so nobody later reads them as
evidence that a relations *flow* exists.

---

## 6. STOP GATE C — the tests

Each test is on real PostgreSQL and must be demonstrated to fail against the
defect it names.

| STOP GATE C question | Proving tests |
|---|---|
| what is the physical property? | `test_a_property_is_created_with_its_type_location_and_supply_mode`, `test_property_attributes_are_unique_per_definition` |
| what offers exist for it? | `test_owner_sale_broker_sale_and_rent_coexist_on_one_property`, `test_listing_a_property_returns_all_of_its_offers` |
| who supplied each fact? | `test_a_claim_must_carry_at_least_one_origin`, `test_a_source_is_created_only_through_an_external_lead`, `test_converting_a_lead_records_its_party_and_consent` |
| what is current vs historical? | `test_only_one_resolved_value_is_current_per_attribute`, `test_superseding_closes_the_previous_row_in_the_same_transaction`, `test_a_stale_offer_is_reported_stale_on_its_commercial_terms_clock` |
| declared vs checked? | `test_a_claim_is_born_declared`, `test_only_a_confirmed_verification_event_raises_the_level`, `test_a_non_confirmed_outcome_records_the_event_and_changes_nothing` |
| canonical or alias? | `test_confirmed_same_writes_the_alias_before_the_status`, `test_the_canonical_resolver_returns_the_canonical_for_an_alias`, `test_confirming_same_raises_review_work_for_affected_open_records` |

### 6.1 The seven mandatory tests

| Mandatory test | Planned test | Proves |
|---|---|---|
| owner sale + broker sale + rent coexist | `test_owner_sale_broker_sale_and_rent_coexist_on_one_property` | schema (no uniqueness on the triple) |
| seller expectation absent from public/customer DTOs | `test_seller_expectation_never_appears_in_a_public_or_customer_payload` | **service** — DTO boundary |
| a claim cannot be created `DOCUMENT_SEEN` | `test_a_claim_cannot_be_created_already_verified` | **contract boundary** (§3.1) |
| a verification event is required to upgrade | `test_only_a_confirmed_verification_event_raises_the_level` | schema trigger (§3.1) |
| a resolution cannot cite a foreign claim | `test_a_resolution_cannot_cite_a_claim_about_another_subject`, `..._another_attribute` | schema trigger + **service** pre-check (§3.2) |
| `CONFIRMED_SAME` without alias fails | `test_confirmed_same_without_a_canonical_id_is_refused`, `test_the_canonical_must_be_one_of_the_candidate_pair` | schema trigger + **service** pre-check (§3.10) |
| matching inputs use canonical, not alias | `test_the_canonical_resolver_returns_the_canonical_for_an_alias` | **narrowed** — §6.4 |

### 6.2 Tests added by revision 2

**Offer state (§3.5)** — every allowed edge; every refused edge; the four
CUSTOMER-allowed transitions; `test_a_customer_cannot_set_pending_info`;
`test_a_customer_cannot_close_an_offer`;
`test_an_unknown_reason_code_is_refused`;
`test_a_supplied_reason_code_is_readable_back_from_the_trail`;
`test_an_offer_activates_without_a_price`;
`test_a_self_entered_offer_activates_without_a_source`.

**Availability (§3.3)** — `test_patch_cannot_change_availability`;
`test_reconfirm_moves_between_any_two_availability_values`;
`test_reconfirm_requires_an_explicit_availability`;
three separate tests that the sweep leaves `UNKNOWN`,
`NEEDS_CONFIRMATION` and `UNAVAILABLE` untouched, one value each;
`test_the_sweep_converts_each_of_the_four_named_values`.

**Offer freshness (§3.4)** —
`test_offer_staleness_is_measured_on_commercial_terms_last_confirmed_at`;
`test_reconfirming_an_offer_updates_both_confirmation_columns`;
`test_a_confirmation_without_a_timezone_is_refused_on_the_offer_endpoint`.

**SOURCE (§1.5)** — `test_a_source_is_created_only_through_an_external_lead`;
`test_converting_a_lead_requires_a_party_and_a_consent`;
`test_an_unconverted_lead_appears_in_the_backoffice_queue`;
`test_converting_a_lead_twice_is_refused`.

**Offer sources (§3.6)** —
`test_linking_a_new_primary_transfers_the_flag_without_deleting_links`;
`test_two_concurrent_primary_source_links_leave_exactly_one_primary`.

**Resolution authority (§3.7)** — one test per condition, five in all,
including `test_a_background_job_cannot_issue_a_resolution`.

**Claim provenance (§3.8)** — `test_a_claim_must_carry_at_least_one_origin`;
`test_a_party_assertion_alone_is_a_valid_origin`;
`test_recorded_by_account_is_not_an_origin`;
`test_a_source_inconsistent_with_its_observation_is_refused`.

**Controlled options (§3.9)** — `test_an_inactive_attribute_code_is_refused`;
`test_an_unregistered_enum_option_is_refused`;
`test_an_attribute_not_applicable_to_this_property_type_is_refused`;
and the same three asserted at **all three** call sites.

**Identity (§3.10)** — `test_an_omitted_algorithm_version_is_stored_as_the_contract_default`;
`test_generating_twice_produces_identical_signals`;
`test_generation_only_ever_writes_pending_review`;
`test_confirming_same_raises_review_work_for_affected_open_records`;
`test_generating_the_same_pair_twice_concurrently_yields_one_candidate`.

**Authorization (§5.1)** — the sixteen RFC-001 scenarios, named individually.

### 6.3 Concurrency tests

Two engines, two transactions, interleaving witnessed through
`pg_stat_activity`, every worker's outcome asserted — the harness Slice 2
ended with, including the E-02 correction:

**The principle the second review established, applied to all four.** A lock
that serialises two paths makes *both* succeed; a winner-and-loser outcome
needs either no serialising lock or a **declared** compare-and-set. It cannot
be inferred from a unique index. We checked each test against that rule rather
than only the one it was raised about:

| test | serialises on | expected outcome |
|---|---|---|
| `test_two_concurrent_primary_source_links_leave_exactly_one_primary` | the parent **offer** row | **both succeed**; last committer's source is primary; invariant holds throughout (§3.6) |
| `test_two_concurrent_resolutions_of_one_attribute_yield_one_current_value` | the **subject** row | **both succeed**; the second closes the first's row and inserts its own; exactly one CURRENT at every committed moment; full history preserved |
| `test_generating_the_same_pair_twice_concurrently_yields_one_candidate` | **nothing** — generation is a batch over pairs with no single parent row to lock | `ux_identity_pair` is the real guard; the SAVEPOINT maps it to **keeping the existing candidate** (idempotent), **not** to a 409 raised at the caller |
| `test_two_concurrent_offer_transitions_from_one_state_do_not_both_apply` | the **offer** row, with `AND status = :expected` re-asserted in the `UPDATE` | **a genuine winner and loser** — the predicate *is* a declared compare-and-set, so the second transition matches no row and gets a typed refusal (the R-S2-02 shape) |

The second row corrects revision 2, which claimed a 409 loser there too. Had we
locked the subject *and* asserted a 409, the only way to make the test pass
would have been to remove the lock — a test driving the design backwards.

Every one of the four asserts both workers' outcomes, checks the committed rows
and the trail, and fails if no interleaving was observed.

### 6.4 What these tests will not claim

- The canonical resolver is proven **as a query**. No matching input exists to
  consume it, so the mandatory test "matching inputs use canonical" is proven
  to the edge of this slice and no further. Stated in the docstring.
- The corrective effect (§3.10) is tested against **seeded** open matches and
  opportunities, since this slice creates none.
- Consent-backed public listing is tested against seeded consent rows; no
  consent *capture* flow is in this slice.
- **Several guarantees are the schema's, not ours** (§2.1). Each test is
  labelled with what it proves, and a passing schema test is never presented as
  evidence that our service does something. This is the E-01 lesson: a true
  result filed under a false cause is worse than no result.
- With G3-6 open, **no test claims a relations flow exists** (§5.1 note).

---

## 7. Acceptance conditions

1. Every operation in §1 implemented, or explicitly refusing with a typed error
   naming an undecided rule. None silently permissive.
2. Every mandatory test in §6.1 passing on real PostgreSQL, each demonstrated
   to fail against the defect it names.
3. STOP GATE C answerable on all six questions, with the named evidence.
4. **No new table, column or migration**, and **no new reason-code category**
   — or an explicit finding if one proves necessary.
5. Evidence matrix regenerated with 0 UNPROVEN; gate still 8/8.
6. **Matching not started.** No `match_candidates` row written by any path.
7. **PROPERTY claim eligibility still undecided**; no path creates a
   property-party authority link as a side effect.
8. **No `party_property_relations` row written by any path**, and no `claim`
   or `observation` repurposed to create one implicitly, until the G3-6
   Contract Delta is approved (§4.4). The relations deliverable is reported
   *not delivered* rather than partially claimed.
9. **`party_property_relations` is never read as an authorization source**, in
   any path, whatever the `relation_code` or `verification_level` (R4.5,
   R4.12).
10. **Slice 3 is not declared closed** until G3-6 is delivered or its deferral
    is explicitly approved.
11. No concurrency test asserts a winner-and-loser outcome that is not backed
    by a **declared** compare-and-set (§6.3).
12. Run provenance recorded at run time, with the committed fingerprint
    recipe, and every delivered document accompanied by its sha256 (§9).

---

## 8. Sequence, and where we stop

| Step | Content | Blocked by |
|---|---|---|
| 1 | PROPERTY: create, read, patch, `/me`, internal, backoffice queue | — |
| 2 | OFFER: create, patch, **state machine (§3.5)**, sources with primary transfer | — |
| 3 | SOURCE: external leads, convert, queue (§1.5) | — |
| 4 | Availability reconfirm + the restricted staleness pass (§3.3); offer reconfirm and `offer_terms` freshness (§3.4) | — |
| 5 | Truth layer: observation → claim → verification → resolution, with controlled options (§3.9) | — |
| 6 | Public list, its three conditions and its projection | — |
| 7 | Identity Lite: generate, list, review, alias, corrective effect, resolver (§3.10) | — |
| 8 | Authorization matrix (§5.1), STOP GATE C evidence, concurrency tests (§6.3) | — |
| — | party-property relations | **G3-6** — not attempted |

With G3-1, G3-3 and G3-4 ratified, **steps 1 through 8 can all begin on
approval of this revision**. Only the relations deliverable waits, on G3-6.

All of steps 1–8 are authorised and begin now. The relations deliverable waits
on the G3-6 Contract Delta, which is submitted separately and before any code
for that path.

---

## 9. Document identity

A revision of this plan was reported as delivered while the reviewer held the
previous one, so an approval could have been recorded against a text nobody had
read. From here on, every delivered document is named with the commit it comes
from and is accompanied by its `sha256`, and the hashes are recorded in the
repository at `docs/gate/evidence/DOCUMENT-HASHES.txt` so the claim is
checkable rather than asserted.

| revision | commit | sha256 of `docs/gate/SLICE_3_PLAN.md` |
|---|---|---|
| 1 | `c0e6ed5` | `36f569f72b0769f29d9b5c48b9483db0a0f7690639696ef06bd9187a7fe014e7` |
| 2 | `3447a7d` | `607bd2050aecbb7e5253ae5a8b8008357be49040d68f2bd839e078bdb30d5a12` |
| 3 | this commit | recorded in `DOCUMENT-HASHES.txt` |

The reviewer's reported hash matched revision 1 exactly, which confirms the
diagnosis: revision 2 never reached them, and the fault is ours to prevent, not
theirs to detect.
