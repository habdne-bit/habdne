# Slice 3 · step 2 (OFFER) — delivery note and findings

Scope: `postPropertiesPropertyIdOffers`, `patchOffersOfferId`,
`postOffersOfferIdState`, `postOffersOfferIdSources` (plan rev 6, §8 step 2).
`postOffersOfferIdReconfirm` belongs to step 4 and is **not** delivered here.

No table, column, migration or reason-code category was added. No
`match_candidates` row and no `party_property_relations` row is written by any
path added here. G3-2 (`PropertyClaimUndecided`) is unchanged.

---

## 1. What was implemented, and the one design point that differs from Slice 2

### 1.1 State transitions use a compare-and-set, not lock-then-re-read

`requests.transition` locks the row and then decides from what it reads. On
the offer machine that design is wrong. A second transition waiting on the
lock would re-read the new state and decide from it. Most offer edges exist
from most states, so `ACTIVE → PAUSED` racing `ACTIVE → WITHDRAWN` would apply
both: the second from a `PAUSED` its caller never saw.

Plan §6.3 declares a genuine winner and loser, and names the mechanism: `AND
status = :expected` in the `UPDATE`. `offers.transition` therefore decides from
an **unlocked** read, and the `UPDATE` applies only if the row is still in that
state. Under Read Committed, a concurrent `UPDATE` that holds the row lock makes
this one wait. PostgreSQL then re-evaluates the `WHERE` clause against the
committed new row version and skips the row if it no longer matches. Source:
PostgreSQL 16 documentation, §13.2.1 "Read Committed Isolation Level". Zero
rows is the losing outcome, reported as `409 OFFER_STATE_CHANGED`.

**Demonstrated to fail against the defect it names.** I mutated the service to
lock-then-re-read. `test_two_concurrent_offer_transitions_from_one_state_do_not_both_apply`
then fails with the contender's outcome `('ok', 'WITHDRAWN')`, which is the
double application described above.

### 1.2 Mutation checks (each test fails against the defect it names)

Each mutation below was applied to the source, the named tests were run, and
the source was restored (verified by `diff`):

| Mutation | Tests that fail |
|---|---|
| lock-then-re-read in place of the compare-and-set | `…offer_transitions_from_one_state_do_not_both_apply` |
| `seller_expectation_dzd` rendered to every audience, floor check removed | `test_seller_expectation_never_appears_in_a_public_or_customer_payload` |
| the same leak, floor check kept | the same test (the leak becomes a 500, `FieldLeak`) |
| CUSTOMER narrowing removed | 8 tests: `…staff_only_edge…` ×7, `test_a_customer_cannot_close_an_offer` |
| clear-before-set removed from primary linking | `…transfers_the_flag`, `…leave_exactly_one_primary` |
| party scope removed from customer offer creation | `test_a_customer_cannot_create_an_offer_in_another_partys_name` |
| `reason_code` not merged into the audit context | `test_a_supplied_reason_code_is_readable_back` |
| lax `int` for `asking_price_dzd` | `test_a_price_must_be_a_json_integer[True]`, `[123]` |
| RENT pre-check removed | `test_a_rent_offer_cannot_carry_a_seller_expectation` |

### 1.3 Choices made within the ratified rules, stated so they can be reviewed

1. **`reason_code` validation** means the code exists and is `active` in
   `reason_codes`. No category is required, because none is defined for offer
   states and the plan forbids creating one. So any active code is accepted,
   including one whose category is `MATCH`. The code is stored in two places:
   the provenance claim, readable through `offers.state_history`, and
   `audit_log.context`. The context is merged, never replaced, so `operation`
   and `trace_id` are kept.
2. **Customer offer creation** requires two things, both taken from the
   operation's `x-authorization` ("may act only on resources owned/managed by
   authenticated party"):
   - authority over the parent property under R4.1, evaluated by reusing
     `load_property`. A property that is not the customer's gets the same 404
     body as one that does not exist.
   - `party_id` equal to the customer's own party. Otherwise §4.6 condition 1
     would give them creator authority over an offer in another party's name.
     The refusal is 403, as for `postRequests`.
3. **`seller_expectation_dzd`** may be *sent* by a customer, because
   `OfferCreate` and `OfferPatch` declare it for every role the operation
   admits, and it is stored. It is never rendered to a CUSTOMER audience,
   including the customer who sent it. Omitting it conforms to the contract:
   it is optional in `PropertyOffer`, whose own description says "Never
   expose in customer/public DTOs".
4. **A new offer is never confirmed.** Both confirmation columns stay `NULL`
   until `/reconfirm` (step 4) sets them, the same as a new request.
5. **Two problem codes were added:** `OFFER_STATE_CHANGED` (409) and
   `PRIMARY_SOURCE_CONFLICT` (409). The first applies to the compare-and-set
   loser. The second applies only if `ux_offer_primary_source` is reached
   despite the parent-offer lock. §2.5 of API_CONTRACTS lists codes as
   examples, and Slice 2 added `DUPLICATE_CRITERION_SLOT` the same way.
6. **The `postOffersOfferIdSources` body is open in the contract** (no
   `additionalProperties: false`). Unknown keys are refused anyway, which is
   the same choice Slice 2 made for the equally open `RequestCriterion`.
7. **Money fields use `JsonInteger`** (`src/turab/api/json_types.py`). It
   accepts exactly the JSON Schema `integer` set, which includes `5.0` (JSON
   Schema 2020-12, Core §4.2.1). It refuses `true` and `"123"`. See F-3.

### 1.4 A defect in step 1, found and fixed here

`command.authorize_property_scope` reuses `load_property`, which raises
`ClaimAuthorityConflict` (INV-1) when two accounts have claimed one property.
Nothing on the command path caught it, so a customer command on such a
property returned **500**. This was reproduced first: 500 for a claimant, 500
for an unrelated customer, and no audit record.

The fix applies the read path's disclosure rule
(`AccessService._may_learn_of_conflict`):
- a claimant gets `409 CLAIM_AUTHORITY_CONFLICT`;
- anyone else gets a 404;
- the conflict is audited either way.

Four tests cover it: three on `PATCH /properties`, one on offer creation.

Reachability today: none through the API. PROPERTY claim eligibility is
undecided (G3-2), so the claim events come only from fixtures.

---

## 2. Findings that need a decision — nothing below has been changed

### F-1 (proposed G3-8) · `management_mode` / `claim_status` in customer command responses

**The conflict.**
- The contract's `Property` requires `claim_status`. It is
  `allOf [PropertyCreate, …]`, and `PropertyCreate` requires both
  `management_mode` and `claim_status`. `Request` is built the same way on
  `RequestCreate`.
- These are the 2xx responses of operations whose `x-roles` include CUSTOMER:
  - `postProperties`, `patchPropertiesPropertyId`,
    `postPropertiesPropertyIdReconfirm`;
  - `postRequests`, `patchRequestsRequestId`, `postRequestsRequestIdState`,
    `postRequestsRequestIdReconfirm`.
- ADR-06 (ARCHITECTURE_DECISIONS_v0.2.md line 85) states that management
  metadata "MUST NOT appear in public/customer DTOs **unless explicitly
  approved by the relevant sharing contract**". The Handoff Master (line 256)
  says "management metadata غير المصرح بها".
- `dto/boundaries.py` `NEVER_SERIALIZED` lists both fields without that
  qualification.

**Current behaviour.** Both fields are returned to customers:
- by the Slice 2 REQUEST routes, which were accepted at Slice 2 closure;
- by the step-1 PROPERTY routes.

This conforms to the contract, but it does not agree with the unqualified
`NEVER_SERIALIZED` list.

**Why nothing is disclosed in practice (a verified argument, not a decision).**
- Both fields are **required inputs** of the create body.
- A customer is limited to `SELF_MANAGED` / `CLAIMED`: the route refuses
  anything else.
- Both fields are create-only for PROPERTY and not patchable for REQUEST.
- The one later change, `UNCLAIMED → CLAIMED` by `postRecordsClaim`, is
  visible to a customer only once they hold authority, and holding it implies
  `CLAIMED`.

**Options.**
- **A.** Record the operation response schemas as the explicit approval ADR-06
  allows, and qualify `NEVER_SERIALIZED`'s docstring accordingly.
- **B.** Omit the fields for customers. That violates `required` in the
  response schema. The correction overlay can only narrow, so it cannot do
  this, and it would need a Contract Delta.

**Recommendation: A.** No code change until decided.

### F-2 (proposed G3-9) · a write aimed at an alias property

Authorization resolves an alias to its canonical property (R4.9). The *write
target*, however, is the path id as given:
- `PATCH /properties/{id}` (step 1);
- `POST /properties/{id}/offers` (step 2);
- later `POST /properties/{id}/reconfirm` (step 4).

So a write can land on a merged-away record. The schema already refuses
matches against aliases (`schema_v0.2.3.sql` line 1186), and the contract
names `IDENTITY_ALIAS_NOT_CANONICAL`.

**Options.**
- refuse with `409 IDENTITY_ALIAS_NOT_CANONICAL`;
- redirect the write to the canonical property;
- allow the write as today.

**Reachability today: none through the API.** Aliases are created only by
identity review (step 7). This must be decided before step 7 is delivered.
**Recommendation: refuse (409)**, because it fails closed and uses the code
the contract already names.

### F-3 · lax numeric input in Slice 2 and step 1

Verified with the project's Pydantic 2.13.5:
- a plain `int` field accepts `true` (as 1) and `"123"`;
- a plain `float` field accepts `true` (as 1.0) and `"1.5"`.

The contract's `integer` / `number` accept none of these. Affected fields:
- `RequestCreate` / `RequestPatch`: `budget_target_dzd`, `budget_max_dzd`;
- `RequestCriterionInput.sort_order`;
- `PropertyCreate` / `PropertyPatch`: `land_area_m2`, `built_area_m2`.

The fix is mechanical: `JsonInteger`, plus a matching `JsonNumber`. It only
brings input validation into line with the contract. It is **not** applied
here because it changes closed Slice 2 code, so it is proposed as a separate
commit, awaiting a go-ahead.

### F-4 · `load_offer` omits two guards that `load_property` applies

`load_offer` implements Q9 / §4.6 as written. However, condition 2 ("a valid
claim on the parent property") is evaluated by a bare `EXISTS` on
`record_claim_events`, with two consequences:

- **No INV-1 guard.** If the parent property is claimed by two accounts,
  `load_property` grants authority to nobody. Condition 2 of `load_offer`
  still admits the claimant whose party matches the offer.
- **No R4.9 resolution.** A claim on the canonical property is not consulted
  for an offer attached to an alias.

`authorize_offer_scope` reuses `load_offer` unchanged, so both paths behave
identically. Changing the loader is a change to Permissions, so it is **not**
done without approval. Reachability today: none through the API (G3-2; aliases
arrive in step 7).

---

## 3. Evidence

- Tests: `tests/test_slice3_offers.py` (111).
- INV-1 command-path tests: 3 in `tests/test_slice3_properties.py`, 1 in the
  offers file.
- Full suite: **678 passed** on PostgreSQL 16.13. The bound run is recorded in
  `docs/gate/evidence/TEST-RUN-PROVENANCE.txt` and `junit-run.xml` at the
  commit named there.
