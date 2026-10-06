# Slice 5 — Human Review → OPPORTUNITY
## Implementation plan — **revision 11**

**Status:** submitted for review. **Code is written one approved step at a
time, never ahead of its approval** (§8). Step 1 (`0006`) is CLOSED; step 2
(the review, without APPROVED) is CLOSED at `1e0d919`; step 3 (APPROVED and
the one opportunity) is CLOSED at `921ed01`. Step 4 is authorized. No other
step's code exists.
Slice 4 kept `match_reviews` and `opportunities` closed by an approved
boundary (G4-15 D1). Step 2 opened `match_reviews` to the review command;
step 3 opens `opportunities` to the APPROVED review only (H03).

(Revisions 1–6 carried the sentence "No code for this slice exists, and
none is written until this plan is approved". It stopped being true when
step 1 was delivered; this revision corrects it.)

**The review of revision 1** authorized step 0 only: the PostgreSQL
measurements of §6.4, with no code change. It asked revision 2 to settle
five points:
1. two offers of one property (G5-2, G5-11);
2. the inference of a private claim (G5-5);
3. the atomicity of a refused share (G5-8);
4. the number of tasks (G5-4);
5. the queue's interval (G5-11).

Revision 2 answered each at its decision, marked **[review point n]**.

**The review of revision 2 (`288bfdb`)**
- **Step 0 is accepted** as a documented measurement round. The reviewer
  checked both files' digests, and the harness and its output in the
  record. The reviewer re-ran no PostgreSQL: the results A–J are ours.
- **Directions accepted.** These do not authorize code:
  - G5-1, the proposed scope;
  - G5-2, supersession per offer;
  - G5-4 (a), a new task linked to each NMI review;
  - G5-6 (a), the frozen contract first, with an explicit addendum;
  - G5-7 (a), no visibility before sharing;
  - G5-8, a share check that refuses without changing the row or consuming
    the key;
  - G5-11 (a), no time-based queue condition.
- **Four places block step 1.** Each is answered at its decision, marked
  **[R3-n]**:
  1. §3.1: the review stamp must exceed the previous one explicitly;
  2. G5-2 and G5-9: one table covering every request, offer and
     availability state, with creation consistent with the next
     revalidation;
  3. G5-12: B10 attributed to a service guard; closing a NEW opportunity
     directly;
  4. G5-13: documenting the role is separate from remedying it; K06 is not
     PASS until a non-superuser role is tested.
- **A smaller point:** LOCATION in G5-5's display list, marked **[R3-5]**.
- **The next step it names** is this revision: the plan and its planned
  tests, with no code. After it, G5-12 can be approved, and `0006` started
  on a precise, checkable text (§5, G5-12).

**The review of revision 3 (`3a797d8`).** The reviewer matched both
digests and reviewed the text and the available sources, without re-running
PostgreSQL.
- **Accepted:**
  - [R3-1], the review-ordering rule (§3.1);
  - §3.7, adopted as the basis of G5-2 and G5-9. Its proof is still the
    implementation and the planned tests;
  - [R3-5], LOCATION removed from the customer display;
  - **G5-13 (b), option (ii), decided:** the role is remedied in a separate,
    cross-cutting step, mandatory before any release gate. Until a test
    under a non-superuser, non-owner role passes, K06 stays UNPROVEN, and
    STOP GATE E's document states it so.
- **Not approved: G5-12 as written, and `0006` does not start.** The
  stamp rules 5 and 6 forced an invented `shared_at` on NEW → CLOSED, and
  an invented `engaged_at` on SHARED → CLOSED. Answered at G5-12 as
  **[R4-1]**.
- **A point for G5-5,** before the customer view is implemented: the key
  test does not prove derivability from THIS response when the type or an
  area changed after the evaluation. Answered at G5-5 as **[R4-2]**.
- **Still not approved:** G5-3, G5-5 and G5-10.

**The review of step 1 (`f5a9d88`). Step 1 is CLOSED within G5-12's
scope.**

What the review checked itself:
- the bundle's digest;
- the 348 manifest files;
- `run_binding.py` (`bound`, with the recorded source fingerprint), run
  inside the extracted tree;
- the migration, the tests and the mutation record, by reading.

It re-ran neither PostgreSQL nor the tests. 2027/2027 and the gate are
results of our runs, bound to the tree, not independent checks.

**Its three decisions:**
1. **The two functions and two triggers are the approved content.** "One
   function and two triggers" in G5-12 was a numerical error. It is
   corrected in this revision, and the migration is unchanged.
2. **STOP GATE D stays the record of the Slice 4 tree.** It is not
   regenerated during Slice 5. Its current `--check` failure, a stale
   document, is expected, and is not a pass that could be credited to the
   new tree. **STOP GATE E** is the document bound to Slice 5's run, when
   it is reached (§6.3).
3. **An `__main__` guard for `mutate_input_hardening.py`,** as a separate,
   limited maintenance change, with a test that importing it modifies no
   file and starts no run, and that direct invocation is unchanged. Done
   at `5d502b5`; §8 records it.

**What the closure does not change:**
- K06 is not proven, and stays UNPROVEN;
- step 2 is not authorized: G5-3 and its inputs must be decided first;
- G4-5R is open, and STOP GATE E is for SALE.

**The review of `2bed7c8`.** The maintenance change is accepted, and step
1's closure stands. The reviewer compared the direct run with the
2026-09-24 record: same failure counts, same failing tests, for all 16
mutations. It re-ran neither the suite nor the gate.

**Two corrections it asked for:**
- **The step 1 delivery note over-stated the AST test.** The test forbids a
  call standing as a module-level STATEMENT. It does not forbid a call
  inside a module-level assignment. The behavioural import test is the
  evidence that no effect appears. The wording is narrowed in the note
  (§8.1).
- **G5-4, ACTIONABLE_UNKNOWN.** The table took the task type from the
  match's stored `next_action`. But the pinned `action.next@1` can return
  `OTHER`, and G5-4 itself forbids an unspecific task. **[R6-1]**, at G5-4,
  answers it.

**Not authorized:** step 2. K06 stays UNPROVEN, and G4-5R open.

**The review of revision 6 (`29a0f30`).** The reviewer matched the
digests and blob ids of the four attachments. Step 1's closure stands.
- **Accepted:** the AST correction of the step 1 note (§8.1 there), and
  [R6-1] at G5-4.
- **G5-3 decided, option (a):**
  - **sequence:** NEED_MORE_INFORMATION is not final; REJECTED and
    APPROVED are final; a later review is 409 `MATCH_REVIEW_DECIDED`,
    consistent with Slice 3's `_OPEN_MATCHES`;
  - **input:** the narrowing is approved. A reason is required for
    REJECTED and NMI, and forbidden for APPROVED. REJECTED takes the
    categories MATCH, FRESHNESS and PERMISSION, or `OTHER`. NMI takes only
    a reason that yields a specific task (G5-4, [R6-1]). A violation is 422,
    before any write and before the key is consumed;
  - **codes:** the list is approved. The approval and opportunity codes
    belong to step 3, and are not attributed to step 2's tests. An unknown
    match id stays 403.
- **Step 2 authorized, within its limit:** REJECTED, NMI and its task, and
  §3.1's ordering rule. APPROVED stays refused until step 3, by a typed
  refusal with no footprint. Its test must show that APPROVED is a valid
  decision of the contract, not executed in this step, and is not classed
  as a gate failure.
- **Still open:** G5-5, G5-10, G4-5R. K06 stays UNPROVEN.

Step 2's delivery: `SLICE_5_STEP2_DELIVERY.md`.

**The review of `7e84702` (step 2).** The reviewer checked the bundle's
digest, its 358 manifest entries and `run_binding.py` (`bound`). It re-ran
neither PostgreSQL nor the mutations.
- **Accepted:**
  - `REVIEW_DECISION_NOT_YET_AVAILABLE` (409), within step 2. It describes
    an APPROVED that is valid in the contract and not executable now,
    without claiming a gate failure. It is removed when step 3 executes the
    approval;
  - STOP GATE D kept as the Slice 4 tree's record. Its `--check` failure
    counts as neither a pass nor a new failure of that record.
- **Blocking (step 2 not closed): the Idempotency-Key raced with a final
  decision.**
  - The cause: `CommandService.run` read the key before `prepare`. A review
    that waited on the match lock of a same-key call was then refused as
    decided, instead of being answered by the key (API_CONTRACTS §2.3).
  - Measured over HTTP, fixed, and re-evidenced: step 2 delivery §10.

**The review of `1e0d919`. Step 2 is CLOSED within its approved scope.**

What the review checked itself:
- the archive's digest;
- its 360 manifest entries;
- `bound`;
- the extracted source fingerprint against the run's record.

It re-ran neither the suite, the mutations nor the gate.

What it accepted:
- the fix, and its race test as evidence in Read Committed;
- the REPEATABLE READ limit, which stays as stated.

What stands:
- the temporary APPROVED code, and STOP GATE D as the Slice 4 record;
- G5-10 and G4-5R open, and K06 UNPROVEN.

**Step 3 is not authorized:** it waits on G5-5.

**The review of `60b0152`. G5-5 decided (a); step 3 authorized.** The
reviewer could not check `60b0152` itself (it was not attached); the
acceptance of step 2 rests on the bundle of `1e0d919`. The decision:

| Item | Decision |
|---|---|
| `sharing_scope` | the evaluated offer's `permission_scope` as it is at approval, recorded with the permission snapshot |
| `why_real`, `known_differences` | the render-derivability rule, by the fixed list by criterion code and scope; a code's presence never depends on `evidence_claim_id` |
| SUMMARY_ONLY | `CustomerPropertyView` with four fields only: id, type, `supply_mode`, `canonical_location_id`; no area. This settles the branch of G5-6 that G5-5 needs; the customer-response tests stay step 4's |
| a field changed after the evaluation | the entry is withheld from the customer response when the current value differs from the match snapshot's, even with the same outcome; the stored `why_real` and the internal view are unchanged |
| the initial content | the plan's shapes, the evaluated context copied, `current_offer_id` = `evaluated_offer_id`, the binding order, NEW and VALID, the approval time in `last_confirmed_at` |

- **Scope of step 3:** APPROVED, the check of the facts now, and one
  opportunity with its uniqueness and concurrency guards. Not share, close
  or the customer view.
- **Conditional:** the proof that no private expectation or claim leaks,
  and of the withholding, rests on the HTTP tests in their planned places
  (step 4).
- **Standing:** G5-10 and G4-5R open; K06 UNPROVEN.

Step 3's delivery: `SLICE_5_STEP3_DELIVERY.md`.

**The review of `921ed01`. Step 3 is CLOSED within its approved scope.**

**What the review checked itself:**
- the bundle's SHA-256;
- its 366 manifest entries;
- `bound`;
- the recomputed source fingerprint;
- the two documents' digests;
- **§3.7's pure table over all 47 628 combinations, independently**, the
  fail-closed handling included.

It did not re-run PostgreSQL or the mutations. Those stay our results,
bound to the fingerprint.

**Approved as implemented:** the five interpretations of step 3 delivery
§2.2. The meaning of `last_confirmed_at` is stated precisely there (§11.2):
the system's confirmation at approval, not a manual confirmation by anyone.

**Carried to step 6 and the final closure:** L-S5-3a and L-S5-3b (§8).

**Step 4 is authorized** after this documentation commit:
- **scope:** the internal read, the customer read and the match queue
  (G5-6, G5-7, G5-11);
- **a condition of its acceptance:** proof of the withholding, and of no
  leak of a private expectation or a claim.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | `658a86d` | first plan |
| 2 | `288bfdb` | step 0 measured (§6.4, record above); §2 restated from the measurements; §3.1 gains the review-ordering rule (measured A3, A5, A6); the five review points answered at G5-2, G5-4, G5-5, G5-8, G5-11; G5-12 widened by the measurement; G5-13 added (the application role, measured D) |
| 3 | `3a797d8` | the review of `288bfdb` recorded; [R3-1] a strictly increasing review stamp (§3.1); [R3-2] one currency table, §3.7, used by approval, revalidate and share; [R3-3] the exact text of `0006` and the B-case attribution (G5-12); [R3-4] G5-13 split into (a) documentation, done as EN-02, and (b) remedy and enforcement point, with K06 UNPROVEN; [R3-5] LOCATION removed from the display list (G5-5) |
| 4 | `6ba73ce` | the review of `3a797d8` recorded, and its acceptances marked in place; [R4-1] G5-12 rules 5 and 6 rewritten as event stamps, set only on their own edge, with a test table for both closing edges; [R4-2] G5-5: an entry is withheld at render when its field's current value differs from the snapshot's |
| 5 | `2bed7c8` | the review of `f5a9d88` recorded: step 1 CLOSED; G5-12's "one function and two triggers" corrected to two functions and two triggers; STOP GATE D not regenerated in Slice 5, STOP GATE E bound to Slice 5's run (§6.3); the input-hardening import guard (§8) |
| 6 | `29a0f30` | the review of `2bed7c8` recorded; [R6-1] G5-4: ACTIONABLE_UNKNOWN is refused when the stored `next_action` is absent or of type OTHER, with its tests |
| 7 | `7e84702` | the review of `29a0f30` recorded: G5-3 decided (a), with its input narrowing and codes; [R6-1] and the AST correction accepted; step 2 authorized and delivered (`SLICE_5_STEP2_DELIVERY.md`) |
| 8 | `1e0d919` | the review of `7e84702` recorded: the temporary APPROVED code and STOP GATE D's status accepted; the Idempotency-Key race with a final decision measured and fixed (step 2 delivery §10) |
| 9 | `60b0152` | the review of `1e0d919` recorded: step 2 CLOSED (step 2 delivery §11); step 3 waits on G5-5 |
| 10 | `921ed01` | the review of `60b0152` recorded: G5-5 decided (a), with G5-6's SUMMARY_ONLY branch (four fields); step 3 authorized and delivered (`SLICE_5_STEP3_DELIVERY.md`) |
| 11 | the commit that adds this revision | the review of `921ed01` recorded: step 3 CLOSED (step 3 delivery §11); the five interpretations approved; L-S5-3a and L-S5-3b carried to step 6 (§8); step 4 authorized |

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
- `prevent_delete_opportunities` (ADR-10). It is the trigger level of K06
  only: K06 itself is UNPROVEN under the current role (EN-02, G5-13).

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
  `reviewed_at` does not guarantee it.
- **Accepted in the review of `3a797d8`.** The rule below is accepted.
- **[R3-1] What A6 proved, and what it did not.** A6 proved two things:
  - the lock serializes the writers;
  - under the lock, `clock_timestamp()` is later than the waiting
    transaction's own start, `now()`.

  It did NOT prove that `clock_timestamp()` is later than the PREVIOUS
  review's `reviewed_at`. Two cases can defeat that:
  1. **Equal readings.** Two readings of the clock can be equal at
     `timestamptz`'s resolution of one microsecond. The stamps then tie, and
     the trigger falls back to the random `match_review_id`, which is A3's
     defect.
  2. **A previous stamp in the future.** A previous `reviewed_at` can lie
     later than the clock reads now, after a clock step backwards on the
     server. The new review would then read as OLDER than one already
     recorded.

  The rule therefore makes the order explicit, not assumed.
- **The rule.** A review command:
  1. takes `SELECT … FOR UPDATE` on the match row as its first statement on
     the match (A6: accepted on the immutable row; a second locker waits);
  2. under the lock, computes its stamp in ONE statement, from the match's
     existing reviews:

         SELECT GREATEST(COALESCE(CAST(:clock AS timestamptz), clock_timestamp()),
                         max(reviewed_at) + interval '1 microsecond')
           FROM turab.match_reviews WHERE match_id = :m

     `max(…)` over no row is NULL, and `GREATEST` ignores NULL. So the first
     review takes the clock, and every later one takes a stamp STRICTLY
     greater than every stamp before it. One microsecond is the type's
     resolution;
  3. inserts the review with `reviewed_at` set to that stamp, in the same
     transaction, under the same lock;
  4. writes exactly one review per transaction.

  The stamps of one match then increase strictly, in the order the
  decisions were taken. No two can tie, so the trigger's order never
  reaches `match_review_id`.
- **What it costs.** In case 2, the new stamp is the future stamp plus one
  microsecond, not the clock. Order is kept, and wall-clock accuracy is not.
  `reviewed_at` is an ordering key here, and the audit log keeps its own
  `occurred_at`. The column keeps its type and its default; no migration is
  needed.
- **How tests reach the two cases.** Neither can be produced on demand from
  a real clock. So the stamp statement takes its clock reading as a bound
  parameter, `:clock`. Production binds NULL, and the statement reads
  `clock_timestamp()`; a test binds a fixed value. The seam is the
  parameter only: the `GREATEST` and the `max(…) + 1 µs` are the same
  statement in both. The planned tests:
  1. **equal reading:** a previous review at T, and the new reading bound
     to T. The new stamp is T + 1 µs, and the trigger reads the new review
     as the latest;
  2. **future previous stamp:** a previous review at the clock + 1 day, and
     the real clock. The new stamp is that + 1 µs, and the new review is
     the latest;
  3. **A5 against the command:** a second command starts first and is held
     at the lock. Its review, committed last, is the latest;
  4. **A3 against the command:** two reviews of one match in one command
     transaction are impossible, because the command writes one.
     Separately, twenty APPROVED → NMI sequences by the command each end
     with NMI as the latest, 20/20, not about half;
  5. **the mutation record** includes dropping the `+ 1 µs` term, and
     dropping the `max(…)` term. Tests 1 and 2 must fail under each.

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
   that is an alias now. The identity row of §3.7 classes an alias
   INVALID, so the answer is 409 `MATCH_CONTEXT_NOT_VALID`, and its reason
   names the alias.
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

### 3.7 [R3-2] The currency check: one table, three users

> **Adopted in the review of `3a797d8`** as the basis of G5-2 and G5-9.
> Its proof is the implementation and the planned tests below.

**Why one table.** Revision 2 stated currency twice, and the two did not
agree:
- G5-2 required an ACTIVE offer, and accepted any request status a run
  accepts, including NEEDS_CONFIRMATION;
- G5-9 classed that same request NEEDS_CONFIRMATION at once, and never
  named PAUSED offers. An opportunity could therefore be VALID with a
  PAUSED offer.

There is now ONE read-only function, the **currency check**. It applies the
table below to the facts as they are now, and returns a validity and every
reason. Three operations use it, and only it:

| Operation | Requires | Writes the result |
|---|---|---|
| APPROVED review (G5-2 (a)) | the check returns **VALID**. Otherwise 409 `MATCH_CONTEXT_NOT_VALID`, with the reasons | no: a refusal writes nothing |
| `revalidate` (G5-9) | — | yes: the only writer of `validity_status` |
| `share` (G5-8) | the stored validity is VALID, AND the check returns VALID | no |

**The consequence is consistency by construction.** An opportunity is
created only when the check returns VALID, and the opportunity is created
VALID. A `revalidate` run straight after creation applies the same function
to the same facts, so it returns VALID. The only exception is time itself:
a freshness threshold crossed between the two calls. The test pins the
clock for that reason (below).

**The table.** Each fact is classed independently. The validity is the
worst class found, in the order INVALID > NEEDS_CONFIRMATION > VALID. Every
class other than VALID adds a reason, by code, so the reasons name every
failing fact, not only the worst.

| Fact | VALID | NEEDS_CONFIRMATION | INVALID |
|---|---|---|---|
| **request status** (7 values) | ACTIVE | NEEDS_CONFIRMATION, PAUSED | CLOSED; RAW, CONTACTED, QUALIFIED |
| **offer status** (6 values; the opportunity's `current_offer_id`) | ACTIVE | PENDING_INFO, PAUSED | WITHDRAWN, CLOSED; DRAFT |
| **property availability** (7 values) | AVAILABLE, POTENTIALLY_AVAILABLE | UNDER_DISCUSSION, TEMPORARILY_UNAVAILABLE, NEEDS_CONFIRMATION, UNKNOWN | UNAVAILABLE |
| **property identity** | canonical | — | an alias now |
| **request freshness** (`freshness.state@1`) | FRESH | STALE, UNKNOWN | — |
| **property freshness** (`freshness.state@1`) | FRESH | STALE, UNKNOWN | — |
| **offer freshness** (`freshness.state@1`) | FRESH | STALE, UNKNOWN | — |
| **permission** (`permission.gate@1` over `permission.binding_state@1`) | PASS | UNKNOWN | FAIL (only revoked bindings) |

**Where each row comes from, and why each class:**
- **Request.**
  - ACTIVE is Spec §15.3's "Active".
  - NEEDS_CONFIRMATION and PAUSED can return to ACTIVE by reconfirmation
    or reactivation (`REQUEST_STATE_TRANSITIONS.md`).
  - CLOSED can return only by "explicit reactivation" (Spec §5.2). It is
    INVALID now, and validity is not monotonic (G5-9).
  - RAW, CONTACTED and QUALIFIED are unreachable after ACTIVE: no edge of
    the adopted table leads back to them. They are classed INVALID, so that
    an unreachable state fails closed.
- **Offer.**
  - PENDING_INFO and PAUSED can return to ACTIVE (`services/offers.py`,
    `TRANSITIONS`).
  - WITHDRAWN and CLOSED are terminal there.
  - DRAFT is unreachable after ACTIVE, and is INVALID.
- **Availability.**
  - The two VALID values are Spec §15.3's "available, or Potential that
    can be confirmed".
  - UNAVAILABLE is the one value Slice 4's candidate set excludes (G4-8).
  - Every other value is a question to settle, not an end.
- **Freshness and permission** are the Slice 4 rules, as pinned, on
  snapshots taken now. So a fact Slice 4 called FRESH or PASS is called the
  same here.

**What a run accepts versus what approval accepts.** Approval is now
STRICTER than a run, and this is deliberate. A run still evaluates a
NEEDS_CONFIRMATION request (G4-8), and the match may be ELIGIBLE. Approving
it is refused until the request is reconfirmed, because the opportunity
would be born NEEDS_CONFIRMATION. Spec §15.3 asks for an "Active" request at
creation. Revision 2's G5-2 (a), item 2, admitted it; this revision does
not.

**Planned tests:**
- **The table, exhaustively, without PostgreSQL.** Every combination of
  request status (7) × offer status (6) × availability (7) × identity (2) ×
  each freshness (3 × 3 values) × permission (3): the check's validity
  equals the table's worst class, and its reasons list every
  non-VALID fact.
- **For the same combinations,** "approval accepted" ⇔ "check returns
  VALID" ⇔ "revalidate immediately after returns VALID", with the clock
  pinned between the calls.
- **Over HTTP:**
  - a NEEDS_CONFIRMATION request whose match is ELIGIBLE: approval is 409,
    and nothing is written;
  - a PAUSED offer: approval is 409; after creation, revalidate gives
    NEEDS_CONFIRMATION;
  - an UNAVAILABLE property after creation: revalidate gives INVALID;
  - approval, then an immediate revalidate: VALID, with no change of
    `validity_status`.

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

> **Direction accepted in the review of `288bfdb`:** G5-1, the proposed scope. This does
> not authorize code: the approval rules, the transitions and the
> database guards are tied to [R3-1]–[R3-4].

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

- **(a) Recommended; supersession per offer accepted in the review of
  `288bfdb`.** APPROVED requires the stored gates (the schema) AND, at
  approval time, both of the following:
  1. the match is not superseded, in the sense defined below. Otherwise 409
     `MATCH_SUPERSEDED`;
  2. **[R3-2]** the currency check of §3.7 returns VALID. Otherwise 409
     `MATCH_CONTEXT_NOT_VALID`, with every reason by code.

  The check applies the **same pinned rules** Slice 4 recorded on the match
  (`freshness.state`, `permission.binding_state`, `permission.gate`), on
  snapshots taken now. It covers:
  - the request status;
  - the offer status;
  - the availability;
  - the identity;
  - the three freshness states;
  - the permission.

  Revision 2's six items are its rows. `REQUEST_NOT_MATCHABLE` and
  `IDENTITY_ALIAS_NOT_CANONICAL` are no longer used at approval; the
  check's reasons name the same facts.

  A failure is a 409 that names what changed. The remedy is a
  reconfirmation, or a new run. Nothing is written.
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

> **Decided (a) in the review of `29a0f30`,** with the input narrowing and
> the codes below. The approval and opportunity codes are step 3's.
> Implemented for REJECTED and NMI in step 2 (`SLICE_5_STEP2_DELIVERY.md`).
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
  - `MATCH_SUPERSEDED`, and `MATCH_CONTEXT_NOT_VALID` with the reasons of
    §3.7 (G5-2 (a));
  - `OPPORTUNITY_ALREADY_OPEN` (§3.3);
  - the existing `CONSENT_REVOKED`, for a share (G5-8).
- **Unknown match id:** 403 `OBJECT_NOT_AUTHORIZED`, the staff convention of
  Slice 4.

**Decision asked:** (a) or (b); the narrowing of the input; the codes.

### G5-4 · The focused task on NEED_MORE_INFORMATION

> **Direction accepted in the review of `288bfdb`:** G5-4 (a), one new task linked to each NMI review. This does
> not authorize code: the approval rules, the transitions and the
> database guards are tied to [R3-1]–[R3-4].

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
  | ACTIONABLE_UNKNOWN | the type of the match's stored `next_action` when it is one of the five SPECIFIC types below; **refused (422) when `next_action` is absent or its type is `OTHER`** [R6-1] |

  The mapping repeats Slice 4's `action.next@1` wherever the two overlap
  (DOCUMENT → VERIFY_DOCUMENT, offer terms → CONFIRM_PRICE, request and
  property reconfirmation). Any other code is refused for NMI (422), `OTHER`
  included, because Spec §19.1 forbids an unspecific task.
- **[R6-1] ACTIONABLE_UNKNOWN never yields an unspecific task.**
  - **What `action.next@1` can return.** Read from the pinned function
    (`gates.py`, `next_action_v1`):
    - **null**, for an ELIGIBLE or REJECTED match;
    - **one of six types:** VERIFY_DOCUMENT, CONFIRM_PRICE, OTHER,
      RECONFIRM_REQUEST, RECONFIRM_PROPERTY or CONFIRM_PERMISSION. **OTHER**
      is what it gives for a blocking unknown on any criterion other than
      DOCUMENT_TYPE, RIGHT_TYPE or BUDGET_MAX, for example ROOMS_MIN, or a
      code with no deterministic rule.
  - **The rule.** For ACTIONABLE_UNKNOWN, the task type is the stored
    `next_action.type` only when it is one of the five specific types:
    VERIFY_DOCUMENT, CONFIRM_PRICE, RECONFIRM_REQUEST, RECONFIRM_PROPERTY,
    CONFIRM_PERMISSION. When `next_action` is null, or its type is OTHER, the
    review is refused before any write:
    - 422 `REVIEW_REASON_NOT_ALLOWED`;
    - its detail says that this match has no specific task for
      ACTIONABLE_UNKNOWN;
    - no review, no task, and no idempotency key consumed.

    The reviewer may then give a reason code that names the information
    itself (the table above). If no code fits, ACTIONABLE_UNKNOWN is not a
    way round the ban on an unspecific task (Spec §19.1).
  - **Why 422, not 409.** The same input is refused whatever the match's
    later history, because a match's `next_action` is immutable (G4-14). It
    is a property of the input against this match, not of a state that may
    change.
  - **Planned tests:**
    - **the OTHER case.** A NEED_MORE_INFORMATION match whose blocking
      unknown is on ROOMS_MIN (`next_action.type = OTHER`). An NMI with
      ACTIONABLE_UNKNOWN is 422, and the footprint is unchanged: reviews,
      tasks, the audit log's high-water mark, idempotency records;
    - **the absent case.** An ELIGIBLE match (`next_action` null). An NMI
      with ACTIONABLE_UNKNOWN is 422, with the same unchanged footprint;
    - **the accepted case.** A match whose `next_action.type` is
      VERIFY_DOCUMENT. An NMI with ACTIONABLE_UNKNOWN creates ONE task of
      type VERIFY_DOCUMENT, whose `payload.match_review_id` is the review;
    - **a vocabulary guard, without PostgreSQL.** The set of types the
      pinned `action.next@1` can return, read from its code, is exactly the
      six above. The mapping accepts exactly the five specific ones. A
      later rule version that adds a type fails this test, and so forces
      the mapping to be decided again;
    - **the mutation record** includes accepting OTHER, and accepting a null
      `next_action`. Each must fail its test.
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

> **Decided (a) in the review of `60b0152`,** item by item as recorded at the
> top of this plan, with SUMMARY_ONLY rendering the four fields. Implemented
> for the stored opportunity in step 3 (`SLICE_5_STEP3_DELIVERY.md`); the
> customer render and its withholding are step 4's.
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
| SUMMARY_ONLY | PROPERTY_TYPE (if G5-6 (a) renders the four fields; none if `property` is omitted) |
| PROPERTY_DETAILS_ALLOWED, CONTACT_AFTER_CONFIRMATION | the above, plus LAND_AREA_MIN and BUILT_AREA_MIN |
| never, at any scope | **LOCATION** [R3-5], DOCUMENT_TYPE, RIGHT_TYPE, ROOMS_MIN, BEDROOMS_MIN, BUDGET_MAX, BUDGET_TARGET, TRANSACTION_INTENT, and any code with no deterministic rule |

**[R3-5] Why LOCATION is removed (accepted in the review of `3a797d8`).** `criterion.location@2` decides PASS when
a requested location is the property's location OR ONE OF ITS ANCESTORS.
It reads `location_ancestry` from the property snapshot (`rules.py`,
`location_v2`). The customer view renders `canonical_location_id`, never
the ancestry. So LOCATION does not satisfy the rule literally:
- **Deriving the ancestry now** from the public location tree
  (`/locations`) would not preserve the snapshot's historical meaning.
  The tree is master data, and the snapshot records the ancestry as it
  stood at evaluation.
- **No customer field carries that historical ancestry.**

LOCATION is therefore never shown in this slice. Showing it would need a
proof that the customer can derive the same result from data available to
them. That proof is a later decision, not assumed here.

**The rule, stated at field level.** "Every value its rule reads is
rendered" means three things:
- every FIELD the rule reads is a field the customer view renders at that
  scope;
- the request's own criterion value is the customer's own data;
- the value used is that field's value in the snapshot at evaluation.

The rules that remain qualify by reading their code:
- `criterion.property_type@1` reads `property_type` only;
- `criterion.area_min@2` reads `land_area_m2` or `built_area_m2` only.

Both read their field from the snapshot, which is the field's value at
evaluation. A pinned-rule test asserts, for each shown code, the exact set
of snapshot keys its rule reads. A later version that reads another key
fails that test.

**[R4-2] When the field has changed since the evaluation.** The key test
above proves only WHICH field a rule reads. It does not prove that the
customer can derive the result from THIS response. The rule read the
snapshot's value, while `CustomerPropertyView` renders the property's
current row. An example:
- the area was 137.5 m² at evaluation, and LAND_AREA_MIN 120 was PASS;
- it was later corrected to 110 m²;
- the response would then show a PASS that its own `property` contradicts.

The PASS also states a fact, "at least 120 then", that nothing rendered
shows. There are two ways out:
- **(a) Recommended: withhold the result when the value differs.** At
  render time, the customer view compares each shown entry's field in the
  match's `property_snapshot` with the property's current value, at the
  same scope. The fields are `property_type`, `land_area_m2` and
  `built_area_m2`, compared exactly (Decimal, as `exact_json`). When they
  differ, the entry is dropped from that response's `why_real.criteria` or
  `known_differences`.
  - **Where the filter applies.** The stored row is not touched: `why_real`
    is written once (G5-12, rule 2). The internal view shows the stored
    entries unfiltered.
  - **The comparison is on the value, not on the outcome.** A change that
    would leave the result unchanged (150 → 160 against a minimum of 120)
    still withholds the entry. The response therefore never rests on a
    re-evaluation the engine did not make.
  - **What remains visible is stated.** An absent entry tells the customer
    that a field shown to them has changed since evaluation. It reveals no
    value they cannot see, and nothing private.
- **(b) Render the historical value with the result.** Rejected:
  - it puts snapshot content into a customer DTO, which R9.2 forbids
    ("match and permission snapshots");
  - the frozen `CustomerPropertyView` has no field for a value other than
    the current one.

**Planned tests under (a), over HTTP at PROPERTY_DETAILS_ALLOWED:**
- **unchanged area:** LAND_AREA_MIN is present;
- **area corrected after creation, outcome flipped (137.5 → 110):** absent
  from the customer body, and present in the internal view's `why_real`;
- **area changed with the outcome unchanged (137.5 → 150):** absent;
- **the area changed back to 137.5:** present again, because the
  comparison is made at each render;
- **`property_type` changed:** PROPERTY_TYPE is absent at every scope;
- **at SUMMARY_ONLY:** an area change cannot show, since LAND_AREA_MIN is
  never shown there.

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
- **[R3-5]** a REQUIRED LOCATION that is PASS by an ANCESTOR, and one that
  is PASS by the property's own location: neither customer body names
  LOCATION, at any scope.
- the pinned-rule key test above, for PROPERTY_TYPE and the two area codes.

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

> **Its SUMMARY_ONLY branch decided in the review of `60b0152`:** the four
> fields, no area. The rest of G5-6 is as accepted in the review of
> `288bfdb`, and its tests are step 4's.

> **Direction accepted in the review of `288bfdb`:** G5-6 (a), the frozen contract first, with an explicit addendum for R8. This does
> not authorize code: the approval rules, the transitions and the
> database guards are tied to [R3-1]–[R3-4].

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

> **Direction accepted in the review of `288bfdb`:** G5-7 (a), no visibility before the opportunity is shared. This does
> not authorize code: the approval rules, the transitions and the
> database guards are tied to [R3-1]–[R3-4].

RFC-001 §4 makes the opportunity readable by the requester's party. Nothing
says whether a NEW, not yet shared, opportunity is visible.
- **(a) Recommended:** the customer sees an opportunity only once
  `shared_at` is set. Before that, the answer is the customer-scoped 404
  (`for_denial`, as for an unknown id). "Mark/share" is the act that makes it
  the customer's.
- **(b)** Any opportunity on the caller's request, from creation.
- **Decision asked:** (a) or (b).

### G5-8 · Share

> **Direction accepted in the review of `288bfdb`:** G5-8, a share check that refuses without changing the row or consuming the key. This does
> not authorize code: the approval rules, the transitions and the
> database guards are tied to [R3-1]–[R3-4].

`API_CONTRACTS` §4.11 and R8.4: "Before every share, revalidate current
permission/consent and field-level sharing scope." H05 and B03 apply.

**[review point 3] Two different things, kept apart.** Revision 1 said both
that share "runs the revalidation inside its own transaction" and that a
refused share "writes nothing". Those contradict each other. The two
operations are separated as follows:
- **The currency check** is a read-only function, defined once in §3.7
  **[R3-2]**. It uses the same pinned rules, on snapshots taken now. It
  RETURNS a validity and its reasons, and writes nothing.
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

**The proposal.** It runs the currency check of §3.7 **[R3-2]**, the same
function approval and share use, and persists its result. Revalidate is the
only command that writes validity. Supersession concerns a match not yet
approved, and plays no part here.

Revision 2's own mapping table is withdrawn. It named no PAUSED offer, and
it disagreed with G5-2 on a NEEDS_CONFIRMATION request. §3.7 replaces it,
for revalidate as for approval.

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

**Decision asked:** the table of §3.7, and whether the offer is never
switched in this slice.

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
  `last_activity_at`, all in one UPDATE, as rule 4 of `0006` requires. The
  note follows G5-8 (i).
- **From which status [R3-3].** Close is permitted from NEW, SHARED and
  ENGAGED: these are the three closing edges of G5-12. A never-shared
  opportunity is closed directly, and the "closing frees the pair" test
  closes a NEW one.
- **CLOSED is terminal.** Any later command on the opportunity gives 409
  `OPPORTUNITY_CLOSED`.
- **A consequence to confirm.** `approved_match_id` is UNIQUE, so a closed
  opportunity's match can never yield another. Identical facts return the
  same match (G4-13). The pair therefore gets a new opportunity only in
  one of two ways:
  - its facts change, and the new match is approved;
  - another offer's current match is approved (G5-2, per offer; measured
    F2).
- **Decision asked:** the narrowing; the terminal state; the consequence.

### G5-11 · The two queues

> **Direction accepted in the review of `288bfdb`:** G5-11 (a) for the opportunity queue, no time-based condition. This does
> not authorize code: the approval rules, the transitions and the
> database guards are tied to [R3-1]–[R3-4].

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
**Measured in step 0** (§2, items 2 and 3; sections B1–B19). The proposal
follows G4-14's precedent: one structural migration `0006`, with no table,
column, reason code or data. Revision 3 gives its exact content **[R3-3]**,
so that the approval names a checkable text.

**The transition graph [R3-3].** Revision 2 wrote "NEW → SHARED → ENGAGED →
CLOSED". Read literally, that forbids closing a NEW opportunity. Closing
one is needed:
- a never-shared opportunity can be closed, for instance after
  `PROPERTY_UNAVAILABLE`;
- the test "closing frees the pair" (§6.1, test 6; measured F2) closes a NEW
  one.

The permitted edges are exactly these five:

| from | to | required on the same UPDATE | event stamps after the UPDATE [R4-1] |
|---|---|---|---|
| NEW | SHARED | `shared_at` set (not null) | `shared_at` set; `engaged_at` null |
| NEW | CLOSED | `closed_at` AND `close_reason_code` set | `shared_at` AND `engaged_at` both **null** |
| SHARED | ENGAGED | `engaged_at` set | `shared_at` unchanged; `engaged_at` set |
| SHARED | CLOSED | `closed_at` AND `close_reason_code` set | `shared_at` unchanged; `engaged_at` **null** |
| ENGAGED | CLOSED | `closed_at` AND `close_reason_code` set | `shared_at` and `engaged_at` unchanged |

No other change of `status` is permitted. CLOSED has no outgoing edge.
ENGAGED is in the graph although no Slice 5 path reaches it (G5-1).

**The exact content of `0006`.** It adds two functions and two triggers on
`turab.opportunities`. Revision 4 said "one function", a numerical error the
review of `f5a9d88` named; the two named functions below were always the
content, and the migration is unchanged.
- **`enforce_opportunity_history()`, BEFORE UPDATE, in this order:**
  1. **A CLOSED row is final.** If `OLD.status = 'CLOSED'`, any UPDATE is
     refused.
  2. **Written once.** The row
     `(request_id, property_id, approved_match_id,
     commercial_context_snapshot, permission_snapshot, why_real,
     known_differences, sharing_scope, created_by_account_id, created_at)`
     of NEW must not be DISTINCT FROM that of OLD.
  3. **The status edge.** If `NEW.status IS DISTINCT FROM OLD.status`, the
     pair `(OLD.status, NEW.status)` must be one of the five edges above.
  4. **The closing fields.** `NEW.closed_at IS NOT NULL`, and also
     `NEW.close_reason_code IS NOT NULL`, each exactly when
     `NEW.status = 'CLOSED'`.
  5. **`shared_at` records an event that happened [R4-1].** Exactly one of
     three cases applies:
     - **once set, fixed:** if `OLD.shared_at` is not null, `NEW.shared_at`
       is not DISTINCT FROM it;
     - **set on its own edge:** otherwise, if `(OLD.status, NEW.status) =
       ('NEW', 'SHARED')`, `NEW.shared_at` is not null;
     - **otherwise, it stays null.**
  6. **`engaged_at` records an event that happened [R4-1].** The same three
     cases, with the edge `('SHARED', 'ENGAGED')`:
     - **once set, fixed:** if `OLD.engaged_at` is not null,
       `NEW.engaged_at` is not DISTINCT FROM it;
     - **set on its own edge:** otherwise, if the edge is taken,
       `NEW.engaged_at` is not null;
     - **otherwise, it stays null.**

  **[R4-1] Why the rules changed.** Revision 3 wrote rule 5 as "null
  exactly while NEW". That required a `shared_at` on every non-NEW row, so
  NEW → CLOSED could pass only with an invented sharing time. Rule 6 forced
  an invented `engaged_at` on SHARED → CLOSED in the same way. Both closing
  edges the graph permits would have passed their guards only by
  fabricating history.

  Now a stamp can be set ONLY on the edge of its own event, and never
  afterwards. So:
  - an event that did not happen has no stamp, however the opportunity
    ends;
  - no UPDATE can write a stamp for an event that did not happen, whether
    it closes the row or leaves it NEW.
- **`enforce_opportunity_birth()`, BEFORE INSERT.** A new row has
  `status = 'NEW'`, `validity_status = 'VALID'`, and null `shared_at`,
  `engaged_at`, `closed_at` and `close_reason_code`.

**The columns left writable** by an UPDATE that passes 1–6:
- `validity_status`;
- `last_confirmed_at`;
- `last_activity_at`;
- `current_permission_binding_id`;
- `current_offer_id`, under a service guard (B10, below);
- the status fields, along the graph.

**The error texts.** Each refusal raises P0001, with a fixed text per rule
that names no id. The service maps none of them: every typed answer comes
from a pre-check (§2, item 7).

**Each measured case, and what refuses it after `0006` [R3-3]:**

| case (step 0) | today | after `0006` | refused by |
|---|---|---|---|
| B1 request_id, B2 property_id, B3 approved_match_id | refused | refused | `trg_opportunity_gate` (unchanged), and rule 2 |
| B4 commercial_context_snapshot | accepted | refused | rule 2 |
| B5 permission_snapshot | accepted | refused | rule 2 |
| B6 why_real | accepted | refused | rule 2 |
| B7 sharing_scope | accepted | refused | rule 2 |
| B8 created_by_account_id | accepted | refused | rule 2 |
| B9 created_at | accepted | refused | rule 2 |
| **B10 current_offer_id → another offer** | accepted | **still accepted by the schema** | **the service guard, not `0006`** |
| B11 NEW → ENGAGED | accepted | refused | rule 3 |
| B12 NEW → CLOSED without `closed_at` | accepted | refused | rule 4 (NEW → CLOSED WITH both fields is permitted) |
| B13 `closed_at` while NEW | accepted | refused | rule 4 |
| B14 CLOSED → NEW, B15 CLOSED → SHARED | accepted | refused | rule 1 |
| B16 SHARED → NEW | accepted | refused | rule 3 |
| B17 clearing `shared_at` | accepted | refused | rule 5 |
| B18 DELETE | refused | refused | `prevent_delete_opportunities` (unchanged) |

**B10 belongs to the service, and is tested there [R3-3].**
`API_CONTRACTS` §4.11 lets revalidate "update current offer context".
`0006` therefore does not freeze the column, and a later slice may use it
under `trg_opportunity_offer_context`. In Slice 5, no command writes
`current_offer_id` after the insert (G5-9). The guard is proven three ways:
1. **A static check.** No UPDATE statement in the Slice 5 services names
   `current_offer_id`. This is checked like STOP GATE C's writer check, and
   a new writer fails it.
2. **An HTTP test.** The evaluated offer is withdrawn while another ACTIVE
   SALE offer exists on the property. Revalidate, share and close each
   leave `current_offer_id` equal to `evaluated_offer_id`, and revalidate
   gives INVALID (§3.7).
3. **A mutation.** An injected `current_offer_id` update in revalidate must
   fail test 2.

**Planned tests and mutations of `0006`:**
- **Every refused row of the table:** refused after `0006`, under its rule.
- **Every permitted edge:** accepted when the fields are supplied, refused
  when they are not. NEW → CLOSED is included.
- **The writable columns:** accepted.
- **The INSERT shape:** refused for any other status, validity or time.
- **[R4-1] The event stamps, case by case:**

  | UPDATE from a row in | change | expected |
  |---|---|---|
  | NEW | → CLOSED, `shared_at` and `engaged_at` null | **accepted** |
  | NEW | → CLOSED, `shared_at` supplied | refused (rule 5, third case) |
  | NEW | → CLOSED, `engaged_at` supplied | refused (rule 6, third case) |
  | SHARED | → CLOSED, `engaged_at` null | **accepted**; `shared_at` unchanged |
  | SHARED | → CLOSED, `engaged_at` supplied | refused (rule 6, third case) |
  | ENGAGED | → CLOSED | **accepted**; both stamps unchanged |
  | NEW | → SHARED without `shared_at` | refused (rule 5, second case) |
  | NEW | → SHARED with `shared_at` | **accepted** |
  | NEW | → SHARED, `engaged_at` also supplied | refused (rule 6, third case) |
  | SHARED | → ENGAGED without `engaged_at` | refused (rule 6, second case) |
  | SHARED | → ENGAGED with `engaged_at` | **accepted** |
  | NEW | status unchanged, `shared_at` supplied | refused (rule 5, third case) |
  | SHARED | status unchanged, `engaged_at` supplied | refused (rule 6, third case) |
  | SHARED | `shared_at` moved or cleared (B17) | refused (rule 5, first case) |
  | ENGAGED | `engaged_at` moved or cleared | refused (rule 6, first case) |

  These are the "closing frees the pair" path's own preconditions: test 6
  of §6.1 closes a NEW opportunity, with both stamps null.
- **The mutation record:** each removal must let its own case through, and
  so fail its test. The removals, one at a time:
  - each of rules 1–4;
  - each of the three cases of rule 5;
  - each of the three cases of rule 6;
  - the birth trigger.

  Removing the third case of rule 5 must let "NEW → CLOSED, `shared_at`
  supplied" through. Removing the second case must let "NEW → SHARED
  without `shared_at`" through.
- **B10:** stays ACCEPTED by the schema after `0006`, recorded as such, and
  is attributed to the service guard above.

**Not proposed for the schema:** the canonical-property uniqueness (§2,
item 1). An alias relation is not visible to a partial index. It stays the
service check of §3.3, with E04's tasks as the after-the-fact net.

**Decision asked:** whether `0006` is approved with exactly this content:
- the two functions and their rules 1–6 and birth rule;
- the edge table;
- B10 left to the service.

### G5-13 · The application role is a superuser (measured D) **[R3-4]**
Revision 2 asked one question: document the role, or fix it in Slice 5.
The review of `288bfdb` separated the two, and so does this revision.

**The facts (D):**
- the application connects as `turab`, a superuser that owns every table;
- `has_table_privilege` is true for INSERT, UPDATE, DELETE and TRUNCATE on
  all six tables measured;
- every protection of market history is therefore a trigger.

As the owner and a superuser, this role can avoid the triggers. Each of the
following would bypass them. This is reasoned from the PostgreSQL 16
documentation, not measured:
- `ALTER TABLE … DISABLE TRIGGER`;
- `SET session_replication_role = replica`;
- `TRUNCATE`, which "will not fire any ON DELETE triggers that might exist for the tables" (*TRUNCATE*, Notes).

**G5-13 (a) — documentation of the current state. Done in this revision.**
The review allowed the note to be recorded now. It is
`docs/gate/ENVIRONMENT_NOTES.md`, **EN-02**, and it states:
- **K06 is UNPROVEN.** K06 reads: "Application role cannot hard-delete
  protected REQUEST/PROPERTY/OFFER/CLAIM/RESOLUTION/OPPORTUNITY history".
- **Gate T9 is narrower than K06.** T9 proves that triggers refuse an
  ordinary DELETE. It is labelled as such and is not cited as K06.
- **No document under `docs/gate` declared K06 PASS** at the time of the
  note. This was checked by search.

**G5-13 (b) — the remedy, and the point at which it is binding. DECIDED
in the review of `3a797d8`: option (ii).**
- **The remedy, proposed.** Two roles:
  - the **owner role** runs migrations and owns the schema;
  - the **application role** (`turab_app`) is `NOSUPERUSER`, owns nothing,
    and holds only the privileges the application uses:
    - SELECT, INSERT and UPDATE where a command needs them;
    - DELETE only on the technical tables that ADR-10 allows to cascade or
      be deleted;
    - no TRUNCATE anywhere;
    - no SET privilege on `session_replication_role`.
  - Default privileges cover tables added later.
  - The application, the test suite's HTTP tests and the gate's application
    probes connect as `turab_app`. Migrations and fixture loading run as the
    owner.
- **The K06 test, under `turab_app`**, for each of the six protected tables
  (`requests`, `properties`, `property_offers`, `claims`, `resolved_values`,
  `opportunities`):
  - `DELETE` is refused;
  - `TRUNCATE` is refused (42501);
  - `ALTER TABLE … DISABLE TRIGGER` is refused (42501, not the owner);
  - `SET session_replication_role = replica` is refused (42501);
  - and the full suite passes as `turab_app`, which shows the application
    needs nothing more.

  Only that test may report K06 PASS.
- **The enforcement point. Options:**
  - **(i) Inside Slice 5**, as a step before STOP GATE E. It touches every
    slice's fixtures, `conftest.py`, the gate scripts and the run binding.
  - **(ii) Recommended: a separate cross-cutting step with its own plan,**
    mandatory before ANY release gate. Until it is done:
    - K06 is reported UNPROVEN everywhere, including the Slice 5 closure and
      the authorization matrix;
    - every guard result in this slice states "against the application's
      ordinary statements".

    STOP GATE E is the core-hypothesis gate. It is not a release gate and
    does not rest on K06, but its generated document lists K06 as UNPROVEN,
    with EN-02.
- **Decided: (ii).** The remedy's exact shape belongs to that step's own
  plan. The shape above is a proposal for it, not a decision.

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
- K06: **UNPROVEN** (EN-02, G5-13). The trigger's refusal of an ordinary
  DELETE is tested, and is labelled trigger-level, never K06.
- S33–S36a, re-proved on the real route, not only on the function.

### 6.3 STOP GATE E, generated and bound
**Decided in the review of `f5a9d88`.** STOP GATE D stays bound to the
Slice 4 run, and is not regenerated during Slice 5. Its `--check` reports
it stale, as expected, and that report is not a pass. STOP GATE E is the
document bound to Slice 5's own run.

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
   command locks the match row first. Under the lock, it stamps
   `reviewed_at` strictly above every earlier stamp of the match (§3.1,
   [R3-1]). The planned tests of §3.1 pass:
   - the equal reading;
   - the future previous stamp;
   - A5 and A3 against the command.
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
9a. **One currency check** (§3.7, [R3-2]) is the only source of validity, for
    approval, revalidate and share. Its exhaustive table test passes, and so
    does "approval accepted ⇔ immediate revalidate VALID".
9b. **`0006` is exactly G5-12's text.** Every refused case of its table is
    refused, and every permitted edge is accepted. B10 is refused by the
    service guard and its three proofs, and is recorded as still accepted
    by the schema.
9c. **K06 is reported UNPROVEN** in every Slice 5 document, matrix and gate
    output (EN-02, G5-13), unless G5-13 (b)'s test under a non-superuser
    role has passed first. A trigger-level DELETE refusal is never labelled
    K06.
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
| 0 | the measurements of §6.4, folded into revision 2; no code | **done**; accepted in the review of `288bfdb` |
| 1 | migration `0006`, exactly G5-12's text, with its mutation record | G5-12; **CLOSED** in the review of `f5a9d88` (`SLICE_5_STEP1_DELIVERY.md`) |
| 2 | the review: REJECTED and NMI, with its task, under the ordering rule of §3.1. APPROVED stays refused. | G5-3 (decided (a)), G5-4; **CLOSED** at `1e0d919` (`SLICE_5_STEP2_DELIVERY.md` §11); the key race of the review of `7e84702` fixed (§10 there) |
| 3 | APPROVED: the currency check of §3.7 and its exhaustive test, the opportunity, the uniqueness layers, concurrency | G5-2, G5-5 (decided (a)), §3.7; **CLOSED** at `921ed01` (`SLICE_5_STEP3_DELIVERY.md` §11) |
| 4 | the reads: internal, customer (F5-1, F5-2, F5-3 corrected), and the match queue | G5-6, G5-7, G5-11; **authorized** in the review of `921ed01` |
| 5 | revalidate, share, close, the opportunity queue, and the B10 service guard | G5-1, G5-8, G5-9, G5-10, G5-11, G5-12 |
| 6 | the mandatory and red-team tests, mutations, STOP GATE E (K06 listed UNPROVEN unless G5-13 (b) is done), and the closure evidence | all |

**Carried to step 6 and the final closure of Slice 5 (review of `921ed01`).**
These are not closed by any step before them. Each is settled explicitly at
step 6 or in the closure record:

| Id | What | To settle |
|---|---|---|
| **L-S5-3a** | supersession across two policies is not proven: no two-policy test, no mutation dropping `matching_policy_id` | prove it, or record the weaker proof as accepted |
| **L-S5-3b** | a new matching run can commit between the approval's supersession check and its commit: the Slice 4 engine does not take the request lock | either accept it as a documented consistency model, or add a synchronization mechanism if "the current match at commit" is decided strict |

**A maintenance change, outside this sequence (review of `f5a9d88`,
decision 3).** `db/dev/mutate_input_hardening.py` ran its mutations when
imported (step 1 delivery §4.3).
- **The defect, measured** in an isolated worktree:
  `evidence/MUTATE-INPUT-HARDENING-IMPORT-BEFORE-FIX.txt`.
- **The guard,** at `5d502b5`.
- **The tests:** `tests/test_mutation_tools.py`, for every mutation script.
  Against the old script, exactly its three tests fail.
- **The direct run, after the guard:**
  `evidence/MUTATE-INPUT-HARDENING-RERUN-AFTER-GUARD.txt`, identical per
  mutation to the 2026-09-24 record.

**Outside this sequence (G5-13 (b), decided as (ii)).** The remedy of the
application role is a separate, cross-cutting step, with its own plan. It is
mandatory before any release gate. It is not a step of Slice 5. K06 stays
UNPROVEN until that step's test passes.

---

## 9. Document identity

This file's sha256 is appended to `docs/gate/evidence/DOCUMENT-HASHES.txt`
in the commit that adds it.
