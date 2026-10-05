# Slice 5 — Human Review → OPPORTUNITY
## Implementation plan — **revision 2**

**Status:** submitted for review. **No code for this slice exists, and none
is written until this plan is approved.** Slice 4 kept `match_reviews` and
`opportunities` closed by an approved boundary (G4-15 D1). Opening them is
the decision this plan asks for.

**The review of revision 1** authorized step 0 only: the PostgreSQL
measurements of §6.4, with no code change. It approved none of the twelve
decisions and not the sequence. It asked revision 2 to settle five points
before implementation is approved:
1. two offers of one property (G5-2, G5-11);
2. the inference of a private claim (G5-5);
3. the atomicity of a refused share (G5-8);
4. the number of tasks (G5-4);
5. the queue's interval (G5-11).

Each is answered at its decision, marked **[review point n]**. The
measurements are in §6.4, and their record is
`docs/gate/evidence/SLICE5-PLAN-MEASUREMENTS.txt`.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | `658a86d` | first plan |
| 2 | the commit that adds this revision | step 0 measured (§6.4, record above); §2 restated from the measurements; §3.1 gains the review-ordering rule (measured A3, A5, A6); the five review points answered at G5-2, G5-4, G5-5, G5-8, G5-11; G5-12 widened by the measurement; G5-13 added (the application role, measured D) |

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

**What the schema leaves open, as measured in step 0** (§6.4; the letters
are the record's sections):
1. **The index keys on `property_id`, not the canonical property.** Two
   records that later become alias and canonical can each hold an open
   opportunity for one request. The index cannot see it (E04). This follows
   from the index definition, and needs no run.
2. **An opportunity's history is not protected (B4–B10, measured).** UPDATE
   was ACCEPTED on each of these columns:
   - `commercial_context_snapshot`;
   - `permission_snapshot`;
   - `why_real`;
   - `sharing_scope`;
   - `created_by_account_id`;
   - `created_at`;
   - `current_offer_id`, moved to another offer of the property. The
     initial-offer check of `trg_opportunity_gate` runs on INSERT only.

   `API_CONTRACTS` §4.2 says: "Historical match/opportunity snapshots remain
   immutable." Only `request_id`, `property_id` and `approved_match_id` are
   refused (B1–B3).
3. **Nothing orders `status` (B11–B17, measured).** Every move tried was
   ACCEPTED:
   - NEW → ENGAGED;
   - NEW → CLOSED without `closed_at`;
   - `closed_at` set while NEW;
   - CLOSED → NEW and CLOSED → SHARED;
   - SHARED → NEW;
   - clearing `shared_at`.
4. **`opportunity_responses` cascades on delete.** The rows are protected
   only because opportunities themselves cannot be deleted (B18: DELETE is
   refused).
5. **The "latest review" is the latest TRANSACTION START, not the latest
   decision (A3, A5, measured).** `reviewed_at` defaults to `now()`, the
   transaction's start time:
   - Two reviews in one transaction tie, and the random `match_review_id`
     decides. In 20 trials of APPROVED then NMI in one transaction, the
     trigger read APPROVED as the latest in 8 of the 20.
   - A transaction that starts first and commits APPROVED last is read as
     OLDER than an NMI committed in between. The opportunity is then
     refused, although the last decision taken was APPROVED.

   §3.1 states the rule this requires.
6. **The four tables Slice 5 might write besides these have no trigger at
   all (E).** They are `tasks`, `interactions`, `task_completion_events` and
   `opportunity_responses`. A review written with `app.account_id` unset is
   accepted, and audited with a NULL actor (E1). Only the application's
   `audited_transaction` (S23) refuses such a write.
7. **Every trigger refusal is P0001, with no constraint name (G).** Two
   messages carry a match id. Only the two unique violations name their
   constraint (`ux_one_open_opportunity_per_pair`,
   `opportunities_approved_match_id_key`). So every typed refusal must come
   from a pre-check made under lock, before the write, as Slice 3 did for
   the alias triggers. The trigger stays the backstop, and its text never
   reaches a response.
8. **The application role is a superuser (D).** It owns every table, so
   GRANTs restrict nothing. G5-13 addresses this.

**What the measurements confirmed:**
- A1: APPROVED, then NMI in a later transaction, refuses the opportunity.
- A2: APPROVED again accepts it. All three reviews are kept.
- A4: APPROVED on a NEED_MORE_INFORMATION match is refused by
  `trg_match_review_gate`.
- C: under READ COMMITTED and under REPEATABLE READ, the second concurrent
  insert for a pair waits on the first, then fails 23505 on
  `ux_one_open_opportunity_per_pair`.
- F2: closing frees the pair for the pair's other match.
- F3: the first match never yields a second opportunity
  (`opportunities_approved_match_id_key`).

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
- **The latest review is the last decision taken.** This follows from
  ADR-08: the sequence IS the history. §2 item 5 measured that the default
  `reviewed_at` does not guarantee it. So a review command:
  1. takes `SELECT … FOR UPDATE` on the match row as its first statement on
     the match. A6 measured that the immutable row accepts the lock and that
     a second locker waits;
  2. writes `reviewed_at = clock_timestamp()`, read after the lock is held.
     A6 measured `clock_timestamp() > now()` at that point;
  3. writes exactly one review per transaction.

  Two reviews of one match then serialize. Each is stamped after the
  previous one committed, so the schema's ordering equals the order of the
  decisions. The column is written, not changed: it keeps its type and its
  default, and no migration is needed.
- **The test reproduces A5 against the command and must find the order
  right:** a second command starts first and is held at the lock.

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
  1. the match is not superseded, in the sense defined below. Otherwise 409
     `MATCH_SUPERSEDED`;
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

**[review point 1] Supersession is per offer.** Revision 1 proposed "the
latest for its (request, property, policy)". Measurement H shows two things
that make this wrong:
- One run over a property with two offers stores two matches with the same
  request, property, policy, `evaluated_at` and `created_at`. The rule ties,
  falls to the random `match_id`, and keeps one of the two arbitrarily.
- After one offer's price changes and a new run, the rule keeps only that
  offer's match. The other offer's match is excluded, though it is still
  that offer's current evaluation.

The commercial context is part of a match's identity: it is ADR-01's
evaluated offer, an input of the hash (G4-13). The revised definition
follows from that:
- **Match M is superseded** when another match M′ exists with the same
  `request_id`, `property_id`, `matching_policy_id` AND `evaluated_offer_id`,
  and `(M′.evaluated_at, M′.created_at)` is strictly greater than M's.
  Every match has an evaluated offer under G4-9 (a).
- **A strict tie on both times is not supersession.** Measurement H found
  `evaluated_at` and `created_at` equal to each other, and equal for every
  match of one run: both are the run transaction's start. A run evaluates
  each offer once. So a tie for one offer can arise only between two runs
  whose transactions start in the same microsecond, with different inputs.
  An identical input is the same match (G4-13). Both
  matches stay current. No order is invented between them. Both remain
  reviewable, and §3.3 still lets at most one become an open opportunity.
  `match_id` is never used as a tie-break: it is random, so H's arbitrary
  survivor would return.
- **Matches of two different offers never supersede one another.** Each
  offer's latest match is current, and each is approvable. Only §3.3 limits
  the pair to one OPEN opportunity.

**Tests:**
- **Two offers, one run:** both matches are in the queue, and both are
  current.
- **Approving the first offer's match** creates the opportunity.
- **Approving the second offer's match while that is open** is 409
  `OPPORTUNITY_ALREADY_OPEN`.
- **After the first is closed,** approving the second creates the pair's
  new opportunity.
- **A price change on one offer and a new run** supersedes that offer's old
  match only.

**Decision asked:** (a) or (b); under (a), supersession per offer as
defined, compared within one policy.

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
- **The proposal: each NMI review's task is typed from the reviewer's
  `reason_code`** (how many tasks, below):

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
- **[review point 4] One semantics, not two.** Revision 1 said both "one
  task per NMI review" and "reuse an OPEN task". The two contradict each
  other. Measurement J shows `tasks` has no column naming a review, and
  `match_reviews` has no column naming a task. So the link between a review
  and its task can live only in the task's `payload`.
  - **(a) Recommended: exactly one NEW task per NMI review, never reused.**
    - The task is inserted in the review's transaction.
    - Its `payload.match_review_id` is the review's id, written once at
      insert and never updated.
    - The review's response returns that task.
    - The link is therefore 1:1 and immutable, in both directions:
      - a review's task is the one task whose `payload.match_review_id` is
        the review's id;
      - a task's review is the review that id names.
    - A repeated NMI on one match yields a second open task. That is the
      faithful record of a second request for information. Listing tasks,
      and any grouping of them, is Slice 6's.
  - **(b) At most one open task per (match, type), reused.** The review's
    id is appended to `payload.match_review_ids` by an UPDATE of the task,
    audited as an UPDATE by `audit_rows`. The link then rests on a mutable
    JSON array, on a table with no trigger (§2, item 6). The reused task's
    `title`, `priority` and `reason_code` are those of the first review.
  - **Tests under (a):**
    - two NMI reviews give two tasks;
    - each task's `payload.match_review_id` names its own review;
    - a refused NMI review (422) writes neither a review nor a task.
- **Decision asked:** the mapping, and (a) or (b).

### G5-5 · What a created opportunity contains
`sharing_scope` and `why_real` are NOT NULL. `MatchReviewInput` carries
neither.

**`sharing_scope`:**
- **(a) Recommended:** the evaluated offer's `permission_scope` (Slice 3
  default SUMMARY_ONLY), read at approval time and recorded in the
  opportunity's permission snapshot;
- (b) always SUMMARY_ONLY at creation; widening it is a later, separate
  decision.

**[review point 2] Which criterion results may be shown to the customer.**
Revision 1 excluded the claim's id and value, and BUDGET_MAX. That is not
enough. A DOCUMENT_TYPE PASS states the property's document, and the
document may be known only from a private claim. Measurement I confirms the
facts:
- A DOCUMENT_TYPE PASS carries `evidence_claim_id` when the attribute was
  resolved from a claim, and none otherwise. Both are PASS, under the same
  rule `criterion.attribute_option@2`.
- No column of `claims` marks a claim private or public. "Private claim"
  (R8.2a, `API_CONTRACTS` §3) is therefore not a property the data can
  test.
- No frozen customer or public type renders ROOMS, BEDROOMS, DOCUMENT_TYPE,
  RIGHT_TYPE, or any offer field. Both render `property_type`,
  `canonical_location_id`, `land_area_m2` and `built_area_m2`.

**The proposed rule: render-derivability.** A criterion result may appear
in `why_real` or `known_differences` only when every value its rule reads
is itself rendered to that customer, at that opportunity's `sharing_scope`,
by the customer view of G5-6. The result then tells the customer nothing
they could not read in the same response. Concretely, under G5-6 (a):

| scope | codes whose results may be shown |
|---|---|
| SUMMARY_ONLY | PROPERTY_TYPE, LOCATION (if G5-6 (a) renders the four fields; none if `property` is omitted) |
| PROPERTY_DETAILS_ALLOWED, CONTACT_AFTER_CONFIRMATION | the above, plus LAND_AREA_MIN and BUILT_AREA_MIN |
| never, at any scope | DOCUMENT_TYPE, RIGHT_TYPE, ROOMS_MIN, BEDROOMS_MIN, BUDGET_MAX, BUDGET_TARGET, TRANSACTION_INTENT, and any code with no deterministic rule |

**Why the rule is a fixed list by code, and not a filter on
`evidence_claim_id`.** A filter that hid a result only when it is
claim-backed would make the ABSENCE depend on a claim. A customer would then
learn from a missing DOCUMENT_TYPE that a claim stands behind it. Under the
fixed list:
- what is shown depends only on the request's criteria, the scope and the
  results of shown codes;
- it never depends on whether a claim exists.

This also settles BUDGET_MAX (S36): it is never shown, whatever its result
and whatever decided it.

**A guard for later rule versions.** The rules of the shown codes link no
claim today, on two grounds:
- in `rules.py`, `evidence_claim_id` is set from a resolved claim only by
  `count_min` and `attribute_option`;
- measurement I records `evidence_claim_id=None` for LAND_AREA_MIN. A test asserts that the rule pinned for each shown code
returns no `evidence_claim_id`. A future rule version that links a claim to
a shown code fails that test, and so forces a decision instead of shipping
silently.

**The shapes.**
- **`why_real`:** `{"format": "turab.why-real/1", "criteria": [...]}`, one
  entry per shown REQUIRED or PREFERRED criterion that is PASS. Each entry
  carries its code, its seeded Arabic label and its importance. No value,
  no delta, no evidence. `criteria` may be empty: no shown code means
  nothing to say, and nothing is said.
- **`known_differences`:** the shown PREFERRED or FLEXIBLE criteria that are
  FAIL or non-blocking UNKNOWN. Each entry carries a code and a
  compatibility only.

**Tests (the customer body, compared whole):**
- a DOCUMENT_TYPE PASS backed by a claim, and one backed by no claim, on
  two otherwise identical opportunities. The two customer bodies are
  identical apart from ids and times, and neither names DOCUMENT_TYPE;
- the same pair for ROOMS_MIN;
- a BUDGET_MAX PASS decided by the asking price, and one decided by the
  seller expectation. The bodies are identical apart from ids and times;
- LAND_AREA_MIN is shown at PROPERTY_DETAILS_ALLOWED and not at
  SUMMARY_ONLY.

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

**Decision asked:** the scope's source; the render-derivability rule and its
table; the shapes of `why_real` and `known_differences`.

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

**[review point 3] Two different things, kept apart.** Revision 1 said both
that share "runs the revalidation inside its own transaction" and that a
refused share "writes nothing". Those contradict each other. The two
operations are separated as follows:
- **The currency CHECK** is a read-only function. It applies the checks of
  G5-9 (the same pinned rules, on snapshots taken now) and RETURNS a
  validity and its reasons. It writes nothing.
- **`revalidate`** is the only command that PERSISTS a check's result:
  `validity_status`, `last_confirmed_at`, `current_permission_binding_id`
  and `last_activity_at`.
- **`share` calls the check. It never persists the check's result.** It
  proceeds only when all of the following hold:
  1. the opportunity is open;
  2. its STORED `validity_status` is VALID. A NEEDS_CONFIRMATION or INVALID
     opportunity must first be revalidated, by the command that records it;
  3. the check made now returns VALID;
  4. the offer's current `permission_scope` is not narrower than the
     opportunity's `sharing_scope`.

**A refused share, and what it leaves behind:**

| item | on a refused share |
|---|---|
| response | 409, with a typed code: `OPPORTUNITY_CLOSED`, `OPPORTUNITY_NOT_VALID` (item 2, or item 3 other than permission), `CONSENT_REVOKED` (item 3, permission FAIL), `SHARING_SCOPE_NARROWED` (item 4). The body names the failing checks by code |
| `opportunities` row | unchanged: no validity, status, time or binding is written |
| `audit_log` | no row: nothing changed, so the frozen `audit_opportunities` trigger does not fire |
| access record (R6.3) | the staff read of the object is recorded as for any command; the refusal is a domain refusal, not an authorization denial |
| `interactions` | no row |
| idempotency key | NOT consumed. The refusal comes before the claim of the key, as in Slice 4 D6. The same key may be retried once the facts change, and is then evaluated afresh |

The validity downgrade that the check found is NOT stored by the refusal.
It is stored when an operator calls `revalidate`, which the refusal's body
names as the remedy.

**Tests:**
- a share refused after a revocation (H05, B03). The opportunity row, the
  audit log's high-water mark and the idempotency table are unchanged;
- `revalidate` then records INVALID;
- a share with a stored NEEDS_CONFIRMATION and current facts that pass is
  refused until `revalidate` records VALID.

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

**The proposal.** It runs the currency CHECK of G5-8, which takes items 2–6
of G5-2 (a), with the same pinned rules, on snapshots taken now.
Supersession (item 1) concerns a match not yet approved, and plays no part
here. It
then persists the result. Revalidate is the only command that writes
validity.

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
  - only matches not superseded, PER OFFER, as G5-2 defines it **[review
    point 1]**. Two offers of one property are two items. A strict tie
    keeps both;
  - the property is canonical now. An alias's matches are left to Slice 3's
    `RESOLVE_IDENTITY` work;
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
- **[review point 5] No borrowed interval.** Revision 1 used 14 days, the
  seeded policy's `offer_terms` freshness threshold, as the interval after
  which an opportunity needs revalidation. That conflates two different
  quantities:
  - **14 days is the age** at which an offer's commercial terms count as
    stale. It applies to the terms' last confirmation.
  - **`opportunities.last_confirmed_at`** is the time of the opportunity's
    approval or last revalidation.

  Measurement J records that policy `0.2.0` has no key for an opportunity
  revalidation interval. It is also immutable (migration `0005`), so no key
  can be added to it. No document of the pack names such an interval.
  Spec §15.1 forbids hard-coding a freshness duration.
  - **(a) Recommended: no time-based membership in Slice 5.** The queue
    holds only states that are stored. A time-based "revalidation due"
    waits until a source for its interval is decided. The engine's own
    freshness thresholds still apply wherever revalidate or share check
    currency; they simply do not schedule queue entries.
  - **(b) A new policy version carrying a named key**
    (`opportunity_revalidation_days`). A new version is a new row, since
    `0.2.0` is immutable. The queue reads the key from the ACTIVE policy at
    query time, and each item records the policy version it was computed
    under. When the policy changes, membership follows the new active
    policy at the next read; nothing stored changes. This is a policy and
    data change. It needs its own approval, and the value its own source.
- **Membership under (a):** open opportunities that are:
  - INVALID;
  - NEEDS_CONFIRMATION;
  - or VALID, NEW and not yet shared.
- **`kind`:** `OPPORTUNITY`.
- **`priority` and `reason`:**

  | case | `priority` | `reason` |
  |---|---|---|
  | INVALID | HIGH | `VALIDITY_INVALID` |
  | NEEDS_CONFIRMATION | NORMAL | `VALIDITY_NEEDS_CONFIRMATION` |
  | not yet shared | NORMAL | `NOT_YET_SHARED` |

- **No engine call per row.** Every membership condition reads a stored
  column.

**Paging** follows the Slice 3 queues.

**Decision asked:**
- membership, priority and reason vocabulary for both queues;
- for the opportunity queue, (a) or (b).

### G5-12 · Opportunity history in the schema (migration `0006`)
**Measured in step 0** (§2, items 2 and 3; sections B4–B17). The proposal
follows G4-14's precedent: one structural migration `0006`, with no table,
column, reason code or data. It reuses the frozen
`prevent_immutable_history_change()` where it can.
- **(i) Fields written once, at creation:**
  - `request_id`, `property_id` and `approved_match_id`. These are already
    refused today, but only through `trg_opportunity_gate`'s re-check, which
    is a side effect and not a guard;
  - `commercial_context_snapshot` and `permission_snapshot`;
  - `why_real`, `known_differences` and `sharing_scope`. `why_real` and
    `known_differences` are computed against the creation-time scope
    (G5-5), so a later scope change would make them wrong;
  - `created_by_account_id` and `created_at`.
- **(ii) Status order:**
  - NEW → SHARED → ENGAGED → CLOSED, never backwards; CLOSED is terminal;
  - `closed_at` and `close_reason_code` are set exactly when, and only when,
    the status becomes CLOSED;
  - `shared_at` is set at the first move to SHARED, and never cleared or
    moved;
  - `engaged_at` follows the same rule at ENGAGED.
- **(iii) `current_offer_id` stays out of `0006`.** `API_CONTRACTS` §4.11
  lets revalidate "update current offer context". Slice 5 never does so
  (G5-9), and the service enforces that. A later slice that does so keeps
  `trg_opportunity_offer_context` as its guard.

**Every case of B4–B17 is the mutation record's starting point.** Each must
be refused after `0006`, and each refusal is mapped by a pre-check, never by
the P0001 text (§2, item 7).

**Not proposed for the schema:** the canonical-property uniqueness (§2,
item 1). An alias relation is not visible to a partial index. It stays the
service check of §3.3, with E04's tasks as the after-the-fact net.

**Decision asked:** whether `0006` is in scope, with (i), (ii) and (iii) as
listed.

### G5-13 · The application role is a superuser (measured D), new in revision 2
The application connects as `turab`. That role is a superuser and owns every
table: `has_table_privilege` is true for INSERT, UPDATE, DELETE and TRUNCATE
on all six tables measured. Consequences:
- **GRANTs restrict nothing.** K06 ("application role cannot hard-delete")
  holds only through triggers. Every ordinary statement fires them, as
  B18, B19 and Slices 3–4 measured.
- **A superuser can disable triggers.** `session_replication_role`, or
  `ALTER TABLE … DISABLE TRIGGER`, would bypass every backstop this plan
  relies on.

No document under `docs/gate` stated this before. It predates Slice 5.
- **(a) Recommended: record it as an environment finding.** It goes in
  `docs/gate/ENVIRONMENT_NOTES.md`, and Slice 5 states its limit: K06 and
  the history guards hold against the application's statements, not
  against a superuser who disables them. Separating a non-owner,
  non-superuser application role is a deployment change. It touches every
  slice's tests and is decided outside Slice 5.
- **(b) Make it part of Slice 5.**
- **Decision asked:** (a) or (b).

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

### 6.4 Step 0: the measurements (done)
**The run.**
- **Record:** `docs/gate/evidence/SLICE5-PLAN-MEASUREMENTS.txt`. It carries
  the summary, the full output and the harness verbatim.
- **Tree:** commit `658a86d`, clean before and after the run; source
  fingerprint `5906ae50…4012`.
- **Database:** a scratch database rebuilt by `db/dev/reset_db.sh
  --fixtures`, on PostgreSQL 16.13.
- **How the rows were made:** matches by the delivered Slice 4 route;
  reviews and opportunities by plain SQL.
- **Reproducibility:** two earlier runs on fresh databases gave the same
  results, ids, times and the random A3 counts aside.
- **No repository file was changed.**
- **These results are ours.**

| §6.4 item, or review point | Section | Result |
|---|---|---|
| 1. latest-review ordering | A1, A2, A3, A5, A6 | confirmed, and WIDER: the ordering is by transaction start, and two reviews in one transaction tie at random (§2, item 5; the rule of §3.1) |
| 2. history columns, status order | B1–B19 | confirmed, and WIDER: seven columns and every status move are accepted (§2, items 2 and 3; G5-12) |
| 3. concurrent inserts for a pair | C | the second waits, then 23505 `ux_one_open_opportunity_per_pair`, under READ COMMITTED and REPEATABLE READ |
| 4. the application role | D | superuser and owner of every table (G5-13) |
| 5. audit rows | E | written, with actor, for `match_reviews` and `opportunities`; no trigger on four other tables; a NULL actor is accepted (§2, item 6) |
| 6. closing frees the pair | F | for the pair's other match, yes; for the same match, never |
| 7. trigger messages | G | all P0001 with no constraint name; two carry a match id (§2, item 7) |
| review point 1 | H | two offers, one run: identical (request, property, policy, times); answered at G5-2 |
| review point 2 | I | claim-backed and plain DOCUMENT_TYPE PASS alike; no privacy column; the rendered fields; answered at G5-5 |
| review points 4, 5 | J | no review column on `tasks`; no revalidation key in the policy; answered at G5-4, G5-11 |

The HTTP 200 of the customer view (F5-1, F5-2) cannot be measured before
Slice 5 code exists: no path creates an opportunity. §4's limit stands, and
the conformance test of G5-6 is written over HTTP in step 4.

---

## 7. Acceptance conditions

1. The six mandatory tests pass, over HTTP, each mapped by `module::name`.
2. STOP GATE E: the generated document's `--check` exits 0 on the bound run.
3. **No path writes an opportunity except the APPROVED review.** The writer
   check of §6.1 test 3 enforces this.
4. **No path writes `match_reviews` except the review command.** That
   command locks the match row first and stamps `reviewed_at` with
   `clock_timestamp()` under the lock (§3.1). The A5 case, reproduced
   against the command, reads the last decision as the latest.
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
| 0 | the measurements of §6.4, folded into revision 2; no code | **done** (this revision) |
| 1 | migration `0006`, with its mutation record | G5-12 |
| 2 | the review: REJECTED and NMI, with its task, under the ordering rule of §3.1. APPROVED stays refused. | G5-3, G5-4 |
| 3 | APPROVED: the currency check, the opportunity, the uniqueness layers, concurrency | G5-2, G5-5 |
| 4 | the reads: internal, customer (F5-1, F5-2, F5-3 corrected), and the match queue | G5-6, G5-7, G5-11 |
| 5 | revalidate, share, close, and the opportunity queue | G5-1, G5-8, G5-9, G5-10, G5-11 |
| 6 | the mandatory and red-team tests, mutations, STOP GATE E, and the closure evidence | all |

---

## 9. Document identity

This file's sha256 is appended to `docs/gate/evidence/DOCUMENT-HASHES.txt`
in the commit that adds it.
