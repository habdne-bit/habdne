# Slice 5 — Human Review → OPPORTUNITY
## Implementation plan — **revision 1**

**Status:** submitted for review. **No code for this slice exists, and none
is written until this plan is approved.** Slice 4 kept `match_reviews` and
`opportunities` closed by an approved boundary (G4-15 D1). Opening them is
the decision this plan asks for.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | the commit that adds this file | first plan |

**Baseline:** Handoff v1.0.3, technical pack v0.2.3, frozen.
**Authority for the scope:** `docs/handoff/06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md:210–242`.
**Predecessor:** Slice 4, closed at `58368d1`, within the approved scope
(`docs/gate/SLICE_4_CLOSURE.md`).

**Sources read for this plan.** Each rule below cites one of these:
- `IMPLEMENTATION_SLICES_v0.2.md` §Slice 5 (objective, eight deliverables,
  six mandatory tests, STOP GATE E);
- Handoff Master v1.0.3:
  - §3 (the order of authority);
  - §4, principles 5, 6, 8, 12, 16 and 17;
  - §5.2, §5.3, §6.1, §6.5, §6.6, §10, §16;
- `ARCHITECTURE_DECISIONS_v0.2.md` ADR-01, ADR-04, ADR-06, ADR-08, ADR-10,
  ADR-12;
- Developer Reference Spec v0.1:
  - §5.4, §15.2, §15.3;
  - §19, §19.1;
  - §21 (OPPORTUNITY);
  - §23 (invariants 1, 3, 6, 7, 11);
  - §24 (M-05, M-06, M-07, M-08, O-01, O-02, O-03);
  - §28;
  - Annex A and Annex B;
- `API_CONTRACTS_v0.2.md` §2.2, §2.3, §2.5, §3, §4.2 (revoke), §4.7, §4.8,
  §4.10, §4.11, §5, §7, §8;
- `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` B03, B04, E04, H01–H05, I02, K05, K06;
- `schema_v0.2.3.sql`:
  - the enums `task_type`, `task_priority`, `task_status`,
    `opportunity_status`, `opportunity_validity`, `sharing_scope`,
    `opportunity_response` (80–89);
  - `match_reviews` (709–717);
  - `tasks` and `task_completion_events` (741–770);
  - `opportunities` and `ux_one_open_opportunity_per_pair` (775–801);
  - `opportunity_responses` (803–811);
  - `enforce_opportunity_gate` (814–854);
  - `enforce_approved_review_gate` (856–873);
  - `enforce_opportunity_offer_context` (1209–1228);
  - `prevent_match_review_update`, `prevent_delete_opportunities` (1295, 1307);
  - `latest_match_reviews` (1309–1312);
- `seed_master_data_v0.2.3.sql`: `reason_codes` (134–161), categories
  MATCH, FRESHNESS, PERMISSION, OPPORTUNITY and GENERAL;
- the frozen OpenAPI:
  - `postMatchesMatchIdReview`, `MatchReviewInput`;
  - `getOpportunitiesOpportunityId`, `InternalOpportunityView`;
  - `getMeOpportunitiesOpportunityId`, `CustomerOpportunityView`,
    `CustomerPropertyView`;
  - `postOpportunitiesOpportunityIdShare`, `…Revalidate`, `…Close`,
    `CloseCommand`;
  - `postOpportunitiesOpportunityIdResponses`, `OpportunityResponseInput`;
  - `getTasks`, `postTasksTaskIdComplete`, `Task`, `TaskCompletionInput`;
  - `getBackofficeQueuesMatches`, `getBackofficeQueuesOpportunities`,
    `QueuePage`, `QueueItem`;
- RFC-001 §2.1, R6.1–R6.3, R7.1–R7.4, R8.1–R8.4, R9.1–R9.5, S33–S36a;
- the current code (read, not changed):
  - `src/turab/dto/boundaries.py` (`render_opportunity_for_scope`);
  - `src/turab/api/routes/me.py` (`getMeOpportunitiesOpportunityId`, from
    Slice 0);
  - `src/turab/services/identity.py` (`raise_review_work`, `_OPEN_MATCHES`,
    from Slice 3);
  - `src/turab/matching/gates.py` (`permission.gate@1`, `action.next@1`);
  - `src/turab/matching/snapshots.py` (`permission_snapshot`).

---

## 0. What this slice is, and what it is not

**Objective, as written:** "Make OPPORTUNITY a meaningful reviewed outcome,
not an algorithmic score."

**STOP GATE E (the Core Hypothesis Gate), as written:** "without AI, the
system must demonstrate end-to-end:
`REQUEST → PROPERTY/OFFER → deterministic candidate → human review →
OPPORTUNITY`. If this cannot be done correctly, stop."

**The eight deliverables**, and where each is planned:

| Deliverable | Where |
|---|---|
| pending review queue | `getBackofficeQueuesMatches` (§1; G5-11) |
| append-only human review sequence | `postMatchesMatchIdReview` (§3.1; G5-3) |
| APPROVED / REJECTED / NEED_MORE_INFORMATION | the same (§3.1) |
| automatic focused Task when information is missing | the same, on NEED_MORE_INFORMATION (G5-4) |
| guarded Opportunity creation | the same, on APPROVED (§3.2; G5-2, G5-5) |
| one open Opportunity per Request × canonical Property | §3.3 (schema index, service pre-check, alias check) |
| current commercial context with revalidation path | `postOpportunitiesOpportunityIdRevalidate` (G5-9) |
| customer-safe Opportunity view | `getMeOpportunitiesOpportunityId` (G5-6, G5-7) |

**The boundary with Slice 4 and Slice 6**, proposed in G5-1:

| In Slice 5 | Not in Slice 5 |
|---|---|
| writing `match_reviews` and `opportunities` | any change to `match_candidates`, `match_criterion_results` or `match_diagnostic_runs` (immutable, Slice 4) |
| ONE task per NEED_MORE_INFORMATION review | tasks raised from a diagnostic, and their priority among each other (**Slice 6**, I01) |
| reading the match a reviewer decides on | relaxation scenarios and suggested actions (**Slice 6**) |
| marking an opportunity shared, through its scope | sending any message on any channel (**Slice 7**) |

**Standing limits carried from Slices 3 and 4**, restated as acceptance
conditions in §7:
- relations are never an authorization source, nor a matching input;
- G3-2 stays open: PROPERTY claims fail closed;
- **G4-5R stays open.** A RENT request is never matched, so no RENT
  opportunity can arise. STOP GATE E is demonstrated for SALE only, and says
  so;
- AI takes no part (ADR-12; Master §5.3: AI may not "approve an Opportunity
  alone").

---

## 1. Operations

All are declared in the frozen contract. None is added.

| operationId | Method · Path | Roles (x-roles) | Proposed (G5-1) |
|---|---|---|---|
| `postMatchesMatchIdReview` | POST `/matches/{id}/review` | ADMIN, REVIEWER | **5** |
| `getBackofficeQueuesMatches` | GET `/backoffice/queues/matches` | ADMIN, OPERATOR, REVIEWER | **5** |
| `getOpportunitiesOpportunityId` | GET `/opportunities/{id}` | ADMIN, OPERATOR, REVIEWER | **5** |
| `getMeOpportunitiesOpportunityId` | GET `/me/opportunities/{id}` | CUSTOMER | **5** (exists since Slice 0; completed here) |
| `postOpportunitiesOpportunityIdRevalidate` | POST `/opportunities/{id}/revalidate` | ADMIN, OPERATOR, REVIEWER | **5** |
| `postOpportunitiesOpportunityIdShare` | POST `/opportunities/{id}/share` | ADMIN, OPERATOR | **5** |
| `postOpportunitiesOpportunityIdClose` | POST `/opportunities/{id}/close` | ADMIN, OPERATOR, REVIEWER | **5** |
| `getBackofficeQueuesOpportunities` | GET `/backoffice/queues/opportunities` | ADMIN, OPERATOR, REVIEWER | **5** |
| `getTasks` | GET `/tasks` | ADMIN, OPERATOR, REVIEWER | 6 |
| `postTasksTaskIdComplete` | POST `/tasks/{id}/complete` | ADMIN, OPERATOR, REVIEWER | 6 |
| `postOpportunitiesOpportunityIdResponses` | POST `/opportunities/{id}/responses` | CUSTOMER, ADMIN, OPERATOR | 7 |

- **There is no `POST /opportunities`** (`API_CONTRACTS` §4.11: "There is
  intentionally no general `POST /opportunities`"; H03). An opportunity is
  created only as the consequence of an APPROVED review.
- **Maker–checker is already in force.** `postMatchesMatchIdReview` and
  `postOpportunitiesOpportunityIdShare` are separation-sensitive
  (`src/turab/auth/roles.py`, INV-2). OPERATOR cannot approve; REVIEWER
  cannot share (RFC-001 §2.1).
- **Every POST takes a required `Idempotency-Key`** (`API_CONTRACTS` §2.3;
  K05), as in Slices 1–4.

---

## 2. What the schema already enforces, and what it leaves open

**Backstops the plan proves by schema-labelled tests, and does not
re-implement:**
- `trg_match_review_gate` (`enforce_approved_review_gate`, BEFORE INSERT on
  `match_reviews`): an APPROVED review is refused unless eligibility is
  ELIGIBLE and the hard, information, freshness and permission gates are all
  PASS (H02).
- `prevent_match_review_update`: a review is never updated or deleted
  (ADR-08, H01).
- `trg_opportunity_gate` (BEFORE INSERT, and UPDATE OF `approved_match_id`,
  `request_id`, `property_id`):
  - the match exists;
  - its **latest** review, ordered `reviewed_at DESC, match_review_id DESC`,
    is APPROVED;
  - the opportunity's request and property are the match's;
  - the match is ELIGIBLE with all four gates PASS;
  - on INSERT, `current_offer_id` equals `evaluated_offer_id` (mandatory
    test 4).
- `trg_opportunity_offer_context`: the current offer belongs to the property,
  and BUY takes SALE only, RENT takes RENT only.
- `approved_match_id UNIQUE`: one opportunity per match, ever.
- `ux_one_open_opportunity_per_pair` on `(request_id, property_id) WHERE
  status <> 'CLOSED'` (mandatory test 6, H04).
- `prevent_delete_opportunities` (ADR-10, K06).

**What the schema leaves open.** Each item is to be measured in revision 2
(§6.4) before any fix is proposed:
1. **The index keys on `property_id`, not the canonical property.** Two
   records that later become alias and canonical can each hold an open
   opportunity for one request. The index cannot see it (E04).
2. **Nothing visible protects an opportunity's history.** No trigger is
   visible on UPDATE of `commercial_context_snapshot`, `permission_snapshot`,
   `why_real`, `created_by_account_id` or `created_at`. `API_CONTRACTS` §4.2
   says: "Historical match/opportunity snapshots remain immutable."
3. **Nothing visible orders `status`.** A CLOSED opportunity could be set
   back to NEW or SHARED by an UPDATE. That the index then catches a second
   open row is a side effect, not a rule.
4. **`opportunity_responses` cascades on delete.** The rows are protected
   only because opportunities themselves cannot be deleted.

---

## 3. Rules that follow from the sources without a decision

### 3.1 The review is append-only, and one decision is one row
- **One review is one row.** A review never updates a match and never
  rewrites an earlier review (ADR-08).
- **The latest review is read** by the ordering the schema itself uses:
  `reviewed_at DESC, match_review_id DESC`. That ordering is
  `latest_match_reviews` and `enforce_opportunity_gate`.
- **`reviewer_account_id` is the authenticated subject.** It is never taken
  from the body. The body is `MatchReviewInput`, closed
  (`additionalProperties: false`).
- **The review, its task and its opportunity are written in one
  transaction** (`API_CONTRACTS` §2.6). A refused review writes nothing and
  consumes no idempotency key (as Slice 4 D6).

### 3.2 Where H01 can happen, and where it cannot
A match row is immutable (Slice 4, migration `0005`), and so are its gates.
So:
- **A match whose eligibility is not ELIGIBLE can never be APPROVED.**
  `trg_match_review_gate` refuses it, whatever the facts become later. When
  the missing information arrives, a new run evaluates the new facts as a
  **new** match, with a new input hash (G4-13), and that new match is
  reviewed.
- **H01 (NEED_MORE_INFORMATION → APPROVED, both rows kept)** is therefore,
  on ONE match, the case of an ELIGIBLE match on which a reviewer first asked
  for more information. Mandatory test 1 is written on that case. It also
  shows the cross-match case: an NMI review on match M1, then an APPROVED
  review on match M2 for the same pair, with both rows kept.

### 3.3 One open opportunity per REQUEST × canonical PROPERTY
Master §6.1 states the rule ("REQUEST × canonical PROPERTY, not
REQUEST × OFFER"), as do Spec §15.3, invariant 6, H04 and M-08. Three layers
enforce it:
1. **The service, at approval.** No opportunity is created on a property
   that is an alias now. That is 409 `IDENTITY_ALIAS_NOT_CANONICAL`, a
   code that already exists.
2. **The service, at approval.** No opportunity is created when an open one
   exists for the same request and the same canonical property, counting the
   property's aliases. That is a 409; its code is in G5-3.
3. **The schema backstop.** `ux_one_open_opportunity_per_pair`. A 23505 on
   that index name maps to the same 409, as Slice 4 mapped its own unique
   violations.

**Identity consolidation after creation (E04) is already surfaced.**
Slice 3's `raise_review_work` (`services/identity.py`) writes a
`RESOLVE_IDENTITY` task for every open opportunity on a property that becomes
an alias. It names any open opportunity of the same request on the
canonical record (`duplicate_open_opportunity_ids`). Until now that path ran
with no opportunity in existence. Slice 5 gives it its first real case, and
tests it. It does not change it.

### 3.4 The customer never sees what the engine used privately
Sources: R9.2, R9.3, R8.2a, `API_CONTRACTS` §3 and §8, invariant 7, M-03,
M-07, S36.
- Nothing written to `why_real` or `known_differences` may carry:
  - `seller_expectation_dzd`, or anything derived from it;
  - a claim id or a claim's content;
  - a rule id, a score, a delta or a snapshot.

  Both fields are rendered to the customer (`CustomerOpportunityView`).
- **The opportunity's snapshots, `approved_match_id`,
  `current_permission_binding_id` and `current_offer_id` are staff-only**
  (R9.2: "match and permission snapshots, `approved_match_id`").

### 3.5 Revocation blocks the future, never the past
Sources: ADR-04, R7.3, `API_CONTRACTS` §4.2, B03, H05.
- A revoked consent never edits an opportunity's `permission_snapshot`.
- It makes the next share fail.
- It moves the next revalidation's validity.

### 3.6 Audit
- Row changes are audited by the frozen triggers `audit_match_reviews` and
  `audit_opportunities`, and by `audit_rows` for `tasks`, as Slice 3 does.
- Staff reads of one opportunity are recorded (R6.3). The access kind is
  `OPPORTUNITY`.
- A queue read is recorded once, with its count, not its ids (R6.3c).
- A denied attempt is recorded for every actor (R6.3a).

---

## 4. Findings measured while planning (not fixed)

Measured at `3277476`, on a clean tree, source fingerprint
`5906ae50…4012`. The record is
`docs/gate/evidence/SLICE5-PLAN-FINDINGS.txt`. No PostgreSQL is involved:
the renderer is a pure function.

| # | Finding | Measured |
|---|---|---|
| **F5-1** | `CustomerOpportunityView` is `additionalProperties: false`, and its frozen properties have no `contact`. The Slice 0 renderer emits a `contact` key at every scope, `null` when withheld. | rendered extra keys `['contact']` at all three scopes |
| **F5-2** | The frozen `property` is `$ref CustomerPropertyView` (`additionalProperties: false`). At SUMMARY_ONLY the renderer emits a `PublicPropertySummary`, whose keys `availability` and `offers` the frozen type does not allow. | `not in CustomerPropertyView: ['availability', 'offers']` |
| **F5-3** | RFC-001 R8.2 says SUMMARY_ONLY renders "area bands". The renderer emits the exact area. The frozen type is a number, so a band has no field. | `built_area_m2=137.5` rendered as `137.5` |

**Why none of this has failed until now.** No opportunity row has ever
existed. `getMeOpportunitiesOpportunityId` has always answered 404 or 403,
so its 200 body was never produced over HTTP. The function-level tests
(`test_dto_boundaries.py`, matrix rows R8.2, R8.3/S34) test the ladder, not
its conformance to the frozen type.

**This is a conflict between two approved documents.** One is RFC-001 R8.2
and R8.3, a project decision that contact is released at
CONTACT_AFTER_CONFIRMATION. The other is the frozen contract, which has no
field for it. Master §3 says: "the implementation stops at the affected point,
and an explicit decision is opened. **The developer may not silently choose
one of the two readings.**" G5-6 opens that decision.

---

## 5. Decisions needed — none is taken by this plan

### G5-1 · Scope: which operations are Slice 5's
**The proposal** is the "Proposed" column of §1:
- **In Slice 5:**
  - the review;
  - the match queue;
  - both opportunity reads;
  - revalidate, share and close;
  - the opportunity queue.
- **`getTasks` and `postTasksTaskIdComplete` to Slice 6**, where focused
  operational tasks and I02 sit. The cost: tasks Slice 5 writes, like the
  ones Slice 3 already writes, are readable only in the review's response
  and the audit until Slice 6.
- **`postOpportunitiesOpportunityIdResponses` to Slice 7.** `API_CONTRACTS`
  §4.11 says a response "produces interaction/outcome data", and
  interactions are communication records. The consequence: ENGAGED (Spec
  §5.4) is unreachable in Slice 5. No path sets it.

**Why share and close are proposed in.** They are not among the eight
deliverables, but:
- G4-10, as decided, placed "the buyer side (sharing with the requester)"
  in "Slice 5's check at share time". B03 and H05 test share itself.
- Without close, the CLOSED half of mandatory test 6 cannot be shown: a
  closed opportunity frees the pair.

**The alternative (b):** the review, the match queue, both reads and
revalidate only. Share, close and the opportunity queue would go later. H05
and B03 would then stay untested in Slice 5.

**Decision asked:** (a) as proposed, or (b). Where the task endpoints and
responses go.

### G5-2 · What may be approved: the stored gates, or the stored gates and the facts now
The schema checks the gates **as evaluated**. A match ELIGIBLE thirty days
ago passes `trg_match_review_gate` today, even if, since then:
- the consent was revoked;
- the request was paused;
- the property was sold, or became an alias;
- a newer run evaluated the pair differently.

Spec §15.3 asks, at creation, for a request that is "Active … and fresh
enough". M-05 and M-06 tie freshness to the opportunity.

- **(a) Recommended.** APPROVED requires the stored gates (the schema) AND,
  at approval time, all of the following. Each is checked with the **same
  pinned rules** Slice 4 recorded on the match (`freshness.state`,
  `permission.binding_state`, `permission.gate`), on snapshots taken now:
  1. the match is the latest for its (request, property, policy). Otherwise
     409, superseded;
  2. the request status is one a run accepts (G4-8). Otherwise 409
     `REQUEST_NOT_MATCHABLE`, the existing code;
  3. the property is canonical. Otherwise 409
     `IDENTITY_ALIAS_NOT_CANONICAL`;
  4. the evaluated offer is still ACTIVE;
  5. request, property and offer freshness are each FRESH;
  6. the permission gate is PASS.

  A failure is a 409 that names what changed. The remedy is a new run.
  Nothing is written.
- **(b)** The stored gates only. The opportunity is created VALID, and
  currency is left to revalidate and share.

**Decision asked:** (a) or (b). Under (a), does item 1 compare within the
same policy only, or across policies?

### G5-3 · The sequence of reviews on one match, and the input
**Sequence.** Slice 3's `_OPEN_MATCHES` (`services/identity.py`) already
treats a match as closed when its latest review is REJECTED, or when an
opportunity was created from it.
- **(a) Recommended, consistent with that definition:**
  - NEED_MORE_INFORMATION is not terminal: any decision may follow it;
  - REJECTED is terminal for the match: a later review gives 409
    `MATCH_REVIEW_DECIDED`;
  - APPROVED is terminal: the opportunity's lifecycle takes over, and closing
    it is how it ends.
- **(b)** REJECTED may be followed by another decision. Slice 3's definition
  of "open" would then need to change with it.

**Consequence of (a):** a run on identical facts returns the same match
(G4-13), so a rejected pair stays rejected until its facts change. That is
the intent of an append-only, reasoned rejection.

**Input (a narrowing of `MatchReviewInput`, on the authority of Spec §19.1,
rank 4, above the contract, rank 5):**
- REJECTED requires a `reason_code` ("في REJECT يجب reason_code");
- NEED_MORE_INFORMATION requires a `reason_code` that maps to a task type
  (G5-4) ("يجب Task محددة … لا «اتصل بالعميل» فقط");
- APPROVED takes none;
- every code must exist in `reason_codes`. REJECTED takes the categories
  MATCH, FRESHNESS, PERMISSION and `OTHER`;
- a violation is 422 before any write.

**Status codes and problem codes, proposed:**
- **422**, input:
  - `VALIDATION_FAILED`, `UNKNOWN_FIELD` (existing);
  - `REVIEW_REASON_REQUIRED`, `REVIEW_REASON_NOT_ALLOWED` (new).
- **409**, state:
  - `MATCH_GATES_NOT_PASS` (the schema gate, named before the trigger
    fires);
  - `MATCH_REVIEW_DECIDED`;
  - `MATCH_SUPERSEDED`, `MATCH_CONTEXT_CHANGED` (G5-2 (a));
  - `OPPORTUNITY_ALREADY_OPEN` (§3.3);
  - the existing `REQUEST_NOT_MATCHABLE`, `IDENTITY_ALIAS_NOT_CANONICAL` and
    `CONSENT_REVOKED`.
- **Unknown match id:** 403 `OBJECT_NOT_AUTHORIZED`, the staff convention of
  Slice 4.

**Decision asked:** (a) or (b); the narrowing of the input; the codes.

### G5-4 · The focused task on NEED_MORE_INFORMATION
`postMatchesMatchIdReview` says: "NEED_MORE_INFORMATION should create a
focused task where applicable". O-03 says: "Create task; candidate remains
non-opportunity". The input carries a `reason_code` and nothing else.
- **The proposal: exactly one task per NMI review, typed from the
  reviewer's `reason_code`:**

  | `reason_code` | `task_type` |
  |---|---|
  | DOCUMENT_NOT_KNOWN, DOCUMENT_MISMATCH | VERIFY_DOCUMENT |
  | PRICE_NOT_KNOWN, PRICE_NEGOTIATION_UNCONFIRMED, OFFER_STALE | CONFIRM_PRICE |
  | REQUEST_STALE | RECONFIRM_REQUEST |
  | PROPERTY_STALE | RECONFIRM_PROPERTY |
  | PERMISSION_MISSING, CONSENT_REVOKED | CONFIRM_PERMISSION |
  | ACTIONABLE_UNKNOWN | the type of the match's stored `next_action`, when it has one; otherwise refused |

  The mapping repeats Slice 4's `action.next@1` wherever the two overlap
  (DOCUMENT → VERIFY_DOCUMENT, offer terms → CONFIRM_PRICE, request and
  property reconfirmation). Any other code is refused for NMI (422), `OTHER`
  included, because Spec §19.1 forbids an unspecific task.
- **The task's fields:**
  - `match_id`, `request_id` and `property_id` from the match;
  - `reason_code`, from the review;
  - `priority`: HIGH when the match has a blocking unknown, NORMAL
    otherwise. This is Spec §13, as `action.next@1` applies it;
  - `payload`: the review id, and the match's stored `next_action` for
    reference;
  - `title`: a fixed text per type, never the reviewer's free text;
  - no `assigned_account_id`, and no `due_at`.
- **The proposal on repetition:** when the match already has an OPEN or
  IN_PROGRESS task of the same type, no second task is written. The review
  returns the existing one.
- **Decision asked:** the mapping; one task per review; the repetition rule.

### G5-5 · What a created opportunity contains
`sharing_scope` and `why_real` are NOT NULL. `MatchReviewInput` carries
neither.

**`sharing_scope`:**
- **(a) Recommended:** the evaluated offer's `permission_scope` (Slice 3
  default SUMMARY_ONLY), read at approval time and recorded in the
  opportunity's permission snapshot;
- (b) always SUMMARY_ONLY at creation; widening it is a later, separate
  decision.

**`why_real`** (customer-visible, §3.4), built deterministically from the
match's stored criterion rows:
- `{"format": "turab.why-real/1", "criteria": [...]}`;
- one entry per REQUIRED or PREFERRED criterion that is PASS: its code, its
  seeded Arabic label and its importance. No value, no delta, no evidence;
- **BUDGET_MAX is never listed, whatever its result.** `criterion.budget_max@1`
  may decide a PASS on `seller_expectation_dzd` while the asking price is
  above the maximum (`rules.py`, R9.3). Listing the PASS only when the asking
  price decided it would make the absence itself a signal. S36 asks that the
  expectation be "not stated or inferable".

**`known_differences`:**
- the PREFERRED or FLEXIBLE criteria that are FAIL or non-blocking UNKNOWN,
  under the same exclusions;
- each entry carries a code and a compatibility only.

**The rest:**
- `commercial_context_snapshot`: the match's, copied. The initial context is
  the evaluated one (`API_CONTRACTS` §4.11; mandatory test 4).
- `permission_snapshot`: under G5-2 (a), the snapshot derived at approval;
  under (b), the match's.
- `current_offer_id`: `evaluated_offer_id`.
- `current_permission_binding_id`: the CURRENT binding, taken by a fixed
  order: offer-bound before property-bound, then `bound_at`, then the id.
- `status`: NEW. `validity_status`: VALID.
- `created_by_account_id`: the reviewer.
- `last_confirmed_at`: the approval time under (a); null under (b).

**Decision asked:** the scope's source; the content and exclusions of
`why_real` and `known_differences`.

### G5-6 · The customer view against the frozen contract (F5-1, F5-2, F5-3)
- **(a) Recommended: conform to the frozen contract.** The overlay may only
  narrow.
  - The customer type loses `contact`. R8.3 then holds without exception: no
    contact is ever released through this DTO.
  - At SUMMARY_ONLY, `property` is a `CustomerPropertyView` holding only
    `property_id`, `property_type`, `supply_mode` and
    `canonical_location_id`. No area is rendered, since a band has no field
    (F5-3).
  - At PROPERTY_DETAILS_ALLOWED and at CONTACT_AFTER_CONFIRMATION, `property`
    is the full `CustomerPropertyView`.
  - RFC-001's affected rows (R8.2's third row, R8.3, S34, S36a) are amended
    by a numbered addendum, not by editing its body. That is how the Slice 2
    documentation gap was handled (`DESIGN_LEDGER.md`).
  - The full key set at each scope is asserted against the frozen schema
    (R9.5).
- **(b) A contract widening** that adds `contact`, and offer terms, to the
  customer type. The standing rule forbids this ("the overlay may only
  narrow"). It would need an explicit exception.
- **Decision asked:** (a) or (b). Under (a): omit `property` at SUMMARY_ONLY,
  or render the four fields?

### G5-7 · When a customer can see an opportunity
RFC-001 §4 makes the opportunity readable by the requester's party. Nothing
says whether a NEW, not yet shared, opportunity is visible.
- **(a) Recommended:** the customer sees an opportunity only once
  `shared_at` is set. Before that, the answer is the customer-scoped 404
  (`for_denial`, as for an unknown id). "Mark/share" is the act that makes it
  the customer's.
- **(b)** Any opportunity on the caller's request, from creation.
- **Decision asked:** (a) or (b).

### G5-8 · Share
`API_CONTRACTS` §4.11 and R8.4: "Before every share, revalidate current
permission/consent and field-level sharing scope." H05 and B03 apply.

**The proposal.** Share runs the revalidation of G5-9 inside its own
transaction. It proceeds only when:
- the opportunity is open;
- the result is VALID;
- the offer's current `permission_scope` is not narrower than the
  opportunity's `sharing_scope`. Otherwise 409 `SHARING_SCOPE_NARROWED`.

A refused share writes nothing (409 `CONSENT_REVOKED` when permission is
FAIL; `OPPORTUNITY_NOT_VALID` otherwise). The validity change is recorded by
calling revalidate itself, not as a side effect of a refusal.

**On success:**
- NEW → SHARED, and `shared_at` is set the first time;
- a later share keeps the status and moves `last_activity_at`;
- **no message is sent** (Slice 7).

**The open points:**
- **(i) Where the share's `channel` and `note` are kept.** No opportunity
  column holds them.
  - (a) Recommended: one `interactions` row (`STATUS_CHANGE`, the channel,
    the opportunity, the request's party, the note as `summary`, the
    operator), so the data does not end in logs only;
  - (b) only the audit context. That writes no Slice 7 table, but loses the
    channel and the note.
- **(ii) The buyer side.** No `consent_scope` in the frozen enum covers
  "receiving opportunities". The proposal adds no buyer-side consent check
  and invents no scope.
- **(iii) `CONTACT_BEFORE_SHARING`.** A CURRENT binding with this purpose on
  the offer or its property suggests contact before sharing. Nothing in the
  pack records that contact.
  - (a) Recommended: refuse the share, 409 `CONTACT_BEFORE_SHARING_REQUIRED`,
    until Slice 7 records the contact;
  - (b) ignore the purpose in Slice 5.

**Decision asked:** the proposal, and (i), (ii), (iii).

### G5-9 · Revalidate, and the validity mapping
`API_CONTRACTS` §4.11: revalidate "re-evaluates current
request/property/offer freshness and permission without rewriting historical
match snapshots. It may update current offer context or move validity to
NEEDS_CONFIRMATION/INVALID."

**The proposal.** It takes the same checks as G5-2 (a), with the same pinned
rules, on snapshots taken now.

| validity | when |
|---|---|
| **INVALID** | any of the following: the request is CLOSED; the offer is WITHDRAWN or CLOSED; the property is UNAVAILABLE; the property is now an alias; the permission gate is FAIL (only revoked bindings) |
| **NEEDS_CONFIRMATION** | otherwise, any of the following: any freshness is STALE or UNKNOWN; the permission gate is UNKNOWN; the request is PAUSED or NEEDS_CONFIRMATION; the availability is anything other than AVAILABLE or POTENTIALLY_AVAILABLE |
| **VALID** | otherwise |

**What it writes:**
- `validity_status` and `last_activity_at`;
- `last_confirmed_at`, when VALID;
- `current_permission_binding_id`, by the order of G5-5.

**Validity is not monotonic.** INVALID may return to VALID once the facts
do.

**What it never does:**
- write a snapshot;
- switch to another offer. **No automatic offer switch in Slice 5.** Another
  offer is a new run and a new review. The contract's "may update current
  offer context" is used only for the binding;
- act on a CLOSED opportunity. That is 409 `OPPORTUNITY_CLOSED`.

**The result's reasons** name the failing checks, by code, in the response.
There is no column for them.

**Decision asked:** the mapping, and whether the offer is never switched in
this slice.

### G5-10 · Close
- **`CloseCommand.reason_code` is required** by the contract. The proposal
  narrows it to the category OPPORTUNITY, plus `OTHER`:
  - OWNER_REJECTED;
  - BUYER_REJECTED;
  - PROPERTY_UNAVAILABLE;
  - REQUEST_CHANGED;
  - UNREACHABLE;
  - DEAL_CONFIRMED;
  - DUPLICATE_OPPORTUNITY_CONSOLIDATED;
  - OTHER.

  Spec §28 lists `DEAL_REPORTED` as a suggestion. The seed has
  `DEAL_CONFIRMED`, and the seed is what exists.
- **What close writes:** CLOSED, `closed_at`, `close_reason_code`,
  `last_activity_at`. The note follows G5-8 (i).
- **CLOSED is terminal.** Any later command on the opportunity gives 409
  `OPPORTUNITY_CLOSED`.
- **A consequence to confirm.** `approved_match_id` is UNIQUE, so a closed
  opportunity's match can never yield another. Identical facts return the
  same match (G4-13), so the pair gets a new opportunity only after its
  facts change and a new match is approved.
- **Decision asked:** the narrowing; the terminal state; the consequence.

### G5-11 · The two queues
`API_CONTRACTS` §5: "Queues are not generic search endpoints. Each item must
state why it is actionable now and expose stable priority/reason
information." `QueueItem` requires `id`, `kind`, `priority` and
`created_at`; `reason` is optional.

**Matches, proposed.**
- **Membership:**
  - only the latest match per (request, canonical property, policy);
  - eligibility other than REJECTED;
  - no opportunity;
  - latest review absent or NEED_MORE_INFORMATION.
- **`kind`:** `MATCH`.
- **`priority` and `reason`:**

  | eligibility | `priority` | `reason` |
  |---|---|---|
  | ELIGIBLE | HIGH | `READY_FOR_REVIEW` |
  | NEEDS_CONFIRMATION | NORMAL | the first reason code |
  | NEED_MORE_INFORMATION | NORMAL | the first reason code |

  An ELIGIBLE match whose latest review is NMI gets
  `reason = AWAITING_INFORMATION`.
- **Order:** priority, then `evaluated_at`, then `match_id`.

**Opportunities, proposed.**
- **Membership:** open opportunities that are not VALID, or NEW and not yet
  shared, or whose `last_confirmed_at` is older than the policy's shortest
  freshness threshold (14 days, `offer_terms`).
- **`kind`:** `OPPORTUNITY`.
- **`priority` and `reason`:**

  | case | `priority` | `reason` |
  |---|---|---|
  | INVALID | HIGH | `VALIDITY_INVALID` |
  | NEEDS_CONFIRMATION | NORMAL | `VALIDITY_NEEDS_CONFIRMATION` |
  | not yet shared | NORMAL | `NOT_YET_SHARED` |
  | revalidation due | LOW | `REVALIDATION_DUE` |

- **No engine call per row.** "Revalidation due" reads a stored time.

**Paging** follows the Slice 3 queues.

**Decision asked:** membership, priority and reason vocabulary for both
queues.

### G5-12 · Opportunity history in the schema (migration `0006`), after measurement
§2 lists what the schema leaves open. The proposal follows G4-14's
precedent:
1. measure each gap on PostgreSQL in revision 2, with nothing changed;
2. then propose a structural migration `0006`, with no table, column, reason
   code or data, covering:
   - **(i)** the immutability of `request_id`, `property_id`,
     `approved_match_id`, `commercial_context_snapshot`,
     `permission_snapshot`, `why_real`, `sharing_scope`,
     `created_by_account_id` and `created_at`;
   - **(ii)** the status order NEW → SHARED → ENGAGED → CLOSED, with CLOSED
     terminal and `closed_at` set exactly on closing.

`sharing_scope` is in (i) only if G5-8 never narrows it after creation, as
proposed. The canonical-property uniqueness (§2, item 1) is NOT proposed for
the schema: an alias relation is not visible to a partial index. It stays
the service check of §3.3, with E04's tasks as the after-the-fact net.

**Decision asked:** whether to measure, and then whether `0006` is in scope.

---

## 6. Tests and STOP GATE E

### 6.1 The six mandatory tests

| # | Mandatory test | Planned proof |
|---|---|---|
| 1 | `NEED_MORE_INFORMATION → APPROVED` preserves both decisions | over HTTP on one ELIGIBLE match: two rows in `match_reviews`, in order, and one opportunity. The cross-match case of §3.2 as well |
| 2 | approval fails if any required gate is not PASS | over HTTP, one case per gate (hard, information, freshness, permission) and per non-ELIGIBLE eligibility: 409, no review row, no opportunity, no key consumed. The schema refusal with the service check removed, labelled as schema |
| 3 | Opportunity cannot be created through a generic endpoint | `POST /opportunities` is not routed (405 or 404, as the existing catch-all answers). A static writer check, as STOP GATE C condition 6: `INSERT INTO turab.opportunities` appears in exactly one module, the review service |
| 4 | initial offer context equals evaluated match offer when an offer exists | over HTTP: `current_offer_id = evaluated_offer_id` and `commercial_context_snapshot` equals the match's. The trigger's refusal of a different offer, labelled as schema |
| 5 | customer Opportunity never reveals private seller expectation/claims | at each scope, the full key set equals the frozen schema's allow-list (R9.5). Sentinel values (a seller expectation, a claim id, a claim's value) are absent from the body. A BUDGET_MAX PASS decided by the expectation leaves no trace in `why_real` or `known_differences` |
| 6 | same Request + same canonical Property cannot have two open Opportunities | two offers give two matches for one pair: the second approval is 409. Two reviewers approve concurrently: one opportunity. After close, a new match is approvable. An alias with an open opportunity on its canonical record: 409 |

### 6.2 Red-team cases carried
- B03, H05: the consent is revoked after approval, and the share is refused.
  The snapshot is unchanged.
- H01–H04, as §6.1.
- E04: identity consolidation with an open opportunity on the alias gives
  one `RESOLVE_IDENTITY` task, listing the duplicate. Nothing is closed.
- K05: replay of each POST.
- K06: delete refused.
- S33–S36a, re-proved on the real route, not only on the function.

### 6.3 STOP GATE E, generated and bound
As STOP GATE C and D: a generator (`db/gate/stop_gate_e_evidence.py`)
writes `docs/gate/SLICE_5_STOP_GATE_E.md` from the bound JUnit run, and has
a `--check` mode. It refuses when any of the following holds:
- a mapped test is missing or failed;
- the source changed after the run;
- the document is stale;
- an unapproved writer of `opportunities` or `match_reviews` exists.

**The proof is one test, over HTTP only, from an empty database:**
1. a party, a request and its criteria (Slice 2);
2. a property, its SALE offer and a consent binding (Slice 3);
3. a run (Slice 4);
4. the review APPROVED (Slice 5);
5. the internal and customer reads of the opportunity.

It shows the reconstruction of the match's decision (STOP GATE D's
`reconstruct`) on the very match approved.

**Its stated limit:** SALE only. G4-5R is open.

### 6.4 Measurements for revision 2 (PostgreSQL, no code)
These are the plan facts this revision states from reading. Revision 2
measures them on PostgreSQL 16.13, on a clean tree, into
`docs/gate/evidence/SLICE5-PLAN-MEASUREMENTS.txt`:
1. the latest-review ordering of `trg_opportunity_gate`: APPROVED then NMI
   on the same match refuses an opportunity;
2. §2 items 2 and 3: an UPDATE of each historical column, and CLOSED → NEW,
   on an opportunity;
3. the index under two concurrent inserts for one pair (23505 and its
   constraint name);
4. the application role's privileges on `match_reviews`, `opportunities`,
   `tasks` and `interactions`;
5. the audit rows written by `audit_match_reviews` and
   `audit_opportunities`;
6. that a closed opportunity frees the pair for a different match;
7. the trigger message texts, which must never reach a response.

---

## 7. Acceptance conditions

1. The six mandatory tests pass, over HTTP, each mapped by `module::name`.
2. STOP GATE E: the generated document's `--check` exits 0 on the bound run.
3. **No path writes an opportunity except the APPROVED review.** The writer
   check of §6.1 test 3 enforces this.
4. **No path writes `match_reviews` except the review command.**
5. No contract change, unless G5-6 (b) is approved as an explicit exception.
   No migration other than `0006`, if G5-12 approves it.
6. **No change to Slice 4's engine, rules, pins or registry.** The approval
   check of G5-2 (a) calls the pinned rules; it does not fork them.
   `test_the_current_registry_is_recorded_in_the_history` stays green
   unchanged.
7. Relations are read by no path of this slice, for authorization or
   anything else.
8. The customer path authorizes through `opportunities.request_id →
   requests.party_id` only (RFC-001 §4).
9. Every refusal is typed, and is written before any write. No database
   message text reaches a response.
10. The authorization matrix gains a row per rule of this plan; PASS for
    each, or UNPROVEN stated.
11. **The evidence discipline of Slices 3 and 4:**
    - each defect is measured before it is fixed;
    - mutations run on a clean tree;
    - results are bound to commit and source fingerprint;
    - every delivered document carries a sha256 in `DOCUMENT-HASHES.txt`.

---

## 8. Sequence

Each step is delivered, evidenced and reviewed before the next starts.

| Step | Content | Depends on |
|---|---|---|
| 0 | revision 2: the measurements of §6.4, folded in; no code | this review |
| 1 | migration `0006`, with its mutation record | G5-12 |
| 2 | the review: REJECTED and NMI, with its task. APPROVED stays refused. | G5-3, G5-4 |
| 3 | APPROVED: the currency check, the opportunity, the uniqueness layers, concurrency | G5-2, G5-5 |
| 4 | the reads: internal, customer (F5-1, F5-2, F5-3 corrected), and the match queue | G5-6, G5-7, G5-11 |
| 5 | revalidate, share, close, and the opportunity queue | G5-1, G5-8, G5-9, G5-10, G5-11 |
| 6 | the mandatory and red-team tests, mutations, STOP GATE E, and the closure evidence | all |

---

## 9. Document identity

This file's sha256 is appended to `docs/gate/evidence/DOCUMENT-HASHES.txt`
in the commit that adds it.
