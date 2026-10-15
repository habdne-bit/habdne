# Slice 6 — Match Diagnostic / Information Work
## Implementation plan — **revision 2**

**Status:** submitted for review. **No code for this slice exists, and none
is written until this plan is approved.** Code is then written one approved
step at a time, never ahead of its approval (§8). Step 0 (measurements only)
was authorized in the review of `f7469e8` and is delivered with this
revision: `evidence/SLICE6-PLAN-MEASUREMENTS.txt`.

**What this revision does not decide.** Every choice below that is not
already fixed by a source is put to the reviewer as a decision (§5), with a
recommendation. A recommendation is not a decision.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | `f7469e8` | first plan |
| 2 | the commit that adds this revision | the review of `f7469e8` recorded; step 0 measured (`SLICE6-PLAN-MEASUREMENTS.txt`); G6-4 (iii)–(iv), G6-6, G6-8 and G6-11 rewritten on the measurements; F6-10 to F6-17 added; the text of migration `0007` proposed (§5.1) |

**The review of `f7469e8`. Step 0 is AUTHORIZED, for measurements only, with
no code. The decisions G6-1 to G6-12 and the implementation plan are NOT
approved** in their revision-1 form. The reviewer checked the file's full
sha256 (`589ba6a9…e3c`) against the one delivered.
- **Four points for revision 2, before any implementation is approved:**
  1. **G6-6 assumed one requested location.** `location_v2` accepts
     `LOCATION IN` with several locations, and passes when the property lies
     under ANY of them. The scenario must say which chain it chose among all
     the requested locations, how a tie is broken, and store enough to
     reproduce the result later. Measure an IN with two different locations,
     not EQ alone.
  2. **G6-11 did not say how the matches of an old diagnostic run are
     known.** The row names no match; its hash reduces its input list to a
     digest; a run may reuse an existing match row and still write a new
     diagnostic row. Format 2 must keep an ordered, stored link to each
     match and its input, and the exclusions. Test two runs of one request
     with an offer changed between them and an existing match reused.
  3. **G6-4 (iii)'s key was narrower than the subject of the work.**
     `action.next@1` can name a specific OFFER as the subject of
     CONFIRM_PRICE; the key could merge the work of two offers of one
     property. Restricting it to OPEN lets a second task in while the first
     is IN_PROGRESS. Build the key from `subject.entity`, `subject.id` and
     the specific reason; state the relation between an NMI task and a
     diagnostic task; measure the insert race with that key.
  4. **G6-8 needs measurement of how the completion's evidence is kept and
     what its outcome means.** The options allowed a general reason code that
     describes no task outcome. `evidence_observation_id` is ON DELETE SET
     NULL: verify what happens when the cited observation is deleted once an
     append-only guard exists, and what remains of the evidence if the
     observation's body is changed. Then offer an explicit choice between
     dedicated outcome codes and accepting null within stated limits.
- **Accepted:** F6-1's reading (150 million centimes = 1,500,000 DZD,
  consistent with spec §14). I03's wording is recorded literally in the
  test evidence; the frozen source is not changed.
- **Accepted:** K06 stays UNPROVEN; this slice's closure evidence is not
  called a new STOP GATE.
- **Still deferred to the approval of their decisions:** writing `0007`,
  the task paths, and any change to the run's writers.

**Step 0, delivered with this revision** (`SLICE6-PLAN-MEASUREMENTS.txt`,
measured at `f7469e8` on a clean tree, twice, each on a freshly rebuilt
scratch database; ours, not re-run by anyone else). Its results are F6-10 to
F6-17 (§4); each rewritten decision cites them.

**Baseline:** Handoff v1.0.3, technical pack v0.2.3, frozen.
**Authority for the scope:** `docs/handoff/06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md:246–272`.
**Predecessor:** Slice 5, CLOSED at `339dbc4`, within the SALE scope only;
not a release authorization (`docs/gate/SLICE_5_CLOSURE.md` §0).

**Sources read for this plan.** Each rule below cites one of these:
- `IMPLEMENTATION_SLICES_v0.2.md`:
  - §Slice 6 (objective, seven deliverables, the rule, three mandatory
    tests), lines 246–272;
  - the cross-slice Definition of Done, lines 384–395;
- Handoff Master v1.0.3:
  - §4, principle 19 ("No automatic preference relaxation"), line 110;
  - §7 (Matching Core), "the order of work when there is no Opportunity",
    lines 284–291;
- Developer Reference Spec v0.1:
  - §13 (Match Diagnostic and Actionable Unknowns: blocking, non-blocking,
    hard fail, near match), lines 377–386;
  - §13.1 (the order of work, and the high-value rule), lines 388–396;
  - §14 (Constraint Relaxation: diagnosis, not automatic change; magnitude),
    lines 398–409;
  - §17.1–§17.2 (AI may suggest a relaxation scenario to staff; may not
    change a REQUEST);
  - §19.2 (the request page's diagnostic), line 536;
  - §23, invariants 4, 5 and 8;
  - §24, M-12 and M-13, lines 720–721;
  - §25 (P03, P08) and §25.1 (R-001);
- `API_CONTRACTS_v0.2.md` §4.8 (evaluation order, step 9: "diagnostic next
  action"), §4.9 (Match Diagnostic, lines 287–302), §4.10 (Tasks, lines
  306–314);
- `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` I01, I02, I03 (lines 132–141); C03,
  D02, G04, G06, K05;
- `schema_v0.2.3.sql`:
  - the enums `task_type`, `task_priority`, `task_status` (80–84);
  - `locations` (132–148);
  - `observations` (496–507);
  - `match_diagnostic_runs` (719–735);
  - `tasks` (741–759) and `task_completion_events` (761–769);
  - `audit_row_change` and the tables it is attached to (987–1040);
- `seed_master_data_v0.2.3.sql`: `reason_codes` (134–161); the policy 0.2.0,
  its `priority` list (ending in `diagnostic_relaxation`) and
  `automatic_request_relaxation: false` (163–183);
- the frozen OpenAPI:
  - `getRequestsRequestIdDiagnostic` (path at line 1456), `Diagnostic`
    (3925);
  - `getTasks` (1486), `postTasksTaskIdComplete` (1533), `Task` (3954),
    `TaskCompletionInput` (4727);
- RFC-001 R6.1–R6.3d, R9.2, R9.3;
- the decisions already taken, and their records:
  - Slice 4: G4-4 (blocking), G4-11 (precedence), G4-15 D1–D6 (the boundary,
    the near match, the counts, `blocker_summary`, `next_action`), G4-19
    (the registry digest and its history) — `SLICE_4_PLAN.md`,
    `SLICE_4_CLOSURE.md` §6;
  - Slice 5: G5-1 (`getTasks` and `postTasksTaskIdComplete` assigned to
    Slice 6), G5-4 (a) (one task per NEED_MORE_INFORMATION review) —
    `SLICE_5_PLAN.md`, `SLICE_5_CLOSURE.md` §7;
- the current code (read, not changed):
  - `src/turab/matching/hard_gate.py` (blocking, actionable unknowns);
  - `src/turab/matching/gates.py` (`eligibility.precedence@1`,
    `action.next@1`);
  - `src/turab/matching/explain.py` (D2, D3, D3b, D5);
  - `src/turab/matching/rules.py` (`delta` per rule);
  - `src/turab/matching/snapshots.py` (`location_ancestry`);
  - `src/turab/services/matching_run.py` (the diagnostic row);
  - `src/turab/services/match_review.py` (`_create_task`, `task_view`);
  - `src/turab/services/identity.py` (the RESOLVE_IDENTITY tasks);
  - `src/turab/services/requests.py` (`add_criterion`, the explicit change
    of a criterion).

---

## 0. What this slice is, and what it is not

**Objective, as written:** "Answer not only 'what matches?' but 'what
information/action is most valuable now?'"

**The rule, as written:** "Information acquisition takes priority over
preference relaxation when resolving the unknown could create an exact
candidate. Relaxation never updates REQUEST automatically."

**There is no STOP GATE for Slice 6** in the authority (STOP GATEs A–E
end at Slice 5). This plan proposes closure evidence instead (§6.4). It
does not invent a gate.

**The seven deliverables**, what already exists, and where each is planned:

| Deliverable | Exists since | Planned here |
|---|---|---|
| ready-candidate counts | Slice 4 (`ready_opportunity_count`, D3) | unchanged |
| blocking vs non-blocking unknowns | Slice 4 counts NEED_MORE_INFORMATION candidates only | §3.2; G6-7 |
| blocker summary | Slice 4 (`blocker_summary`, D3b) | extended by G6-7 only |
| high-value information gap detection | — (D5 marks every actionable unknown HIGH) | G6-2 |
| focused operational tasks | tasks written by Slice 3 (identity) and Slice 5 (NMI); no read, no completion | `getTasks`, `postTasksTaskIdComplete` (G6-8, G6-9); tasks from the diagnostic (G6-4) |
| near-match diagnostics | Slice 4 (`near_match_count`, D2: counted only) | G6-5 |
| minimal meaningful relaxation suggestions for staff only | — (`relaxation_scenarios` written `[]`, D1) | G6-5, G6-6 |

**The boundary with Slices 4, 5 and 7, proposed in G6-1:**

| In Slice 6 | Not in Slice 6 |
|---|---|
| filling `suggested_actions` and `relaxation_scenarios` in NEW diagnostic rows | rewriting any existing diagnostic row (immutable, migration `0005`) |
| reading and completing tasks | sending a message on any channel (**Slice 7**) |
| tasks raised from a diagnostic, if G6-4 (a) is decided | any change to `match_candidates`, their criterion rows, or a stored `next_action` (immutable, Slice 4) |
| a relaxation SCENARIO shown to staff | any change to a REQUEST or its criteria (I03; principle 19) |
| — | the customer's response to an opportunity (**Slice 7**) |

**Standing limits carried, restated as acceptance conditions in §7:**
- relations are never an authorization source, nor a matching input;
- G3-2 stays open: PROPERTY claims fail closed;
- **G4-5R stays open.** A RENT request is refused by the run, so no RENT
  diagnostic is produced through the currently approved matching path.
  Every scenario and test here is SALE;
- **K06 stays UNPROVEN** (G5-13 (b)(ii); G6-12);
- AI takes no part (ADR-12). Spec §17.1 allows AI to "suggest a Task or a
  Relaxation scenario to staff"; this slice computes both
  deterministically, and no AI path is added.

---

## 1. Operations

All are declared in the frozen contract. None is added, none is changed.

| operationId | Method · Path | Roles (x-roles) | State today | Proposed (G6-1) |
|---|---|---|---|---|
| `getRequestsRequestIdDiagnostic` | GET `/requests/{id}/diagnostic` | ADMIN, OPERATOR, REVIEWER | routed (Slice 4): returns the latest row | unchanged route; the rows it returns gain content |
| `postRequestsRequestIdMatchingRun` | POST `/requests/{id}/matching/run` | ADMIN, OPERATOR, REVIEWER | routed (Slice 4) | writes the new diagnostic content; writes tasks only if G6-4 (a) |
| `getTasks` | GET `/tasks` | ADMIN, OPERATOR, REVIEWER | **not routed** | **6** |
| `postTasksTaskIdComplete` | POST `/tasks/{id}/complete` | ADMIN, OPERATOR, REVIEWER | **not routed** | **6** |

**Measured on the current tree:** of the 64 operations in
`API_INVENTORY_v0.2.md`, the six not routed are `getTasks`,
`postTasksTaskIdComplete`, `postOpportunitiesOpportunityIdResponses`,
`postInterests`, `postCommunicationThreads` and
`postCommunicationThreadsThreadIdMessages`. Only the first two are this
slice's.

- **There is no operation that creates a task** in the contract. A task
  exists only as the consequence of another command: Slice 3's identity
  consolidation, Slice 5's NEED_MORE_INFORMATION review, and, if G6-4 (a)
  is decided, the matching run.
- **There is no operation that assigns, starts or cancels a task.**
  `assigned_account_id`, `IN_PROGRESS` and `CANCELLED` exist in the schema
  and the contract's `Task` type, with no command that sets them (F6-7).
- **Every POST takes a required `Idempotency-Key`** (`API_CONTRACTS` §2.3;
  K05), as in Slices 1–5.

---

## 2. What the schema and the earlier slices already give, and what they leave open

**Given:**
- `match_diagnostic_runs` has the three counts, `blocker_summary`,
  `suggested_actions` and `relaxation_scenarios`. Every row is immutable
  (`prevent_match_diagnostic_run_update`, migration `0005`).
- **The run writes a NEW diagnostic row on every run**, identical input or
  not: unlike `match_candidates`, the table has no uniqueness on its input
  hash (`matching_run.py`, `execute`).
- `tasks`: `task_type` (nine values), `priority` (LOW, NORMAL, HIGH, URGENT),
  `status` (OPEN, IN_PROGRESS, DONE, CANCELLED), `reason_code` (FK to
  `reason_codes`), the subject ids, `payload`, `completed_at` with the check
  `completed_at >= created_at`.
- `task_completion_events`: `outcome_code` (FK to `reason_codes`), `note`,
  `evidence_observation_id` (FK to `observations`), `completed_by_account_id`
  (NOT NULL), `completed_at`.
- `action.next@1` (D5) already gives each candidate ONE typed, prioritised
  recommendation (`{"type", "priority", "subject"}`), from the contract's
  `Task.task_type` vocabulary. It is stored on the match and creates nothing.
- `explain.is_near_match` (D2): REJECTED, exactly one REQUIRED FAIL, every
  other REQUIRED criterion PASS.
- Each criterion row keeps `delta` where its rule gives one: BUDGET_MAX
  `{"dzd": ask - max}`, the area rules `{"m2": area - min}`, the count rule
  `{"count": value - min}`. LOCATION, PROPERTY_TYPE, the transaction intent
  and the attribute options give none (`rules.py`).

**Left open by the schema:**
1. **No append-only guard on `task_completion_events`.** No trigger
   prevents its UPDATE or DELETE, although `API_CONTRACTS` §4.10 says the
   completion "Appends" an event and that "outcome_code, note and evidence
   observation must be preserved" (G6-8 (iv)).
2. **No database audit trigger on `tasks` or `task_completion_events`**
   (`audit_row_change` is attached to eight other tables, lines 1033–1040).
   `tasks` is audited by the application (`audit_rows`, since Slice 3);
   `task_completion_events` is not yet in its registry.
3. **No uniqueness on open tasks.** Nothing in the schema prevents two OPEN
   tasks for the same subject (G6-4 (iii)).
4. **No seeded reason code for a task outcome** (F6-4).

---

## 3. Rules that follow from the sources without a decision

### 3.1 The diagnostic never changes a REQUEST

- `API_CONTRACTS` §4.9: "The diagnostic never mutates REQUEST criteria
  automatically." Principle 19, invariant 5, I03, policy
  `automatic_request_relaxation: false` (already refused otherwise by
  `policy.py`).
- **Consequence.** No path in this slice writes `requests` or
  `request_criteria`. A relaxation is taken only through the existing
  explicit commands: `postRequestsRequestIdCriteria` (Slice 2,
  `add_criterion`) or `patchRequestsRequestId`, by the actor the contract
  names, as a separate request. I03's test asserts the request's row, its
  `version` and its criteria are byte-identical before and after a run
  that produces a scenario.

### 3.2 Blocking, actionable and high-value are three different sets

From Slice 4 (`hard_gate.py`, G4-4) and spec §13.1:

| Set | Definition | Source |
|---|---|---|
| **blocking unknown** | a REQUIRED UNKNOWN, or a PREFERRED/FLEXIBLE UNKNOWN with `blocking_if_unknown` | G4-4 |
| **non-blocking unknown** | any other UNKNOWN | spec §13 |
| **actionable unknown** | a blocking unknown of a candidate whose hard gate is NOT FAIL | G4-4; §13.1 |
| **high-value unknown** | an actionable unknown that **alone** stands between the candidate and an exact (ELIGIBLE) result | §13.1, "when the missing information alone can produce an Exact Match"; `API_CONTRACTS` §4.9 |

The first three are stored and counted today. The fourth is not
distinguished: D5 gives HIGH to every actionable unknown (F6-6). Its exact
reading is G6-2.

### 3.3 A REJECTED candidate gets no information work

- On a REJECTED candidate the hard gate is FAIL, so it has no actionable
  unknown (G4-4), and `action.next@1` returns null for it.
- **Consequence for mandatory test 2** ("candidate failing three hard
  criteria does not receive high-priority task for an unrelated unknown"):
  whatever G6-2 and G6-4 decide, no task and no suggested information action
  is raised from a REJECTED candidate. A REJECTED candidate appears only in
  the relaxation scenarios, and only if it is a near match (G6-5).

### 3.4 The seller's expectation is never rendered, nor inferable

- R9.3: `seller_expectation_dzd` "may be read by the matching engine and
  MUST NOT be rendered". D02.
- **Consequence.** No suggested action, scenario, task payload or task
  title carries it, or a magnitude computed from it. A budget magnitude is
  computed from the asking price only (G6-5 (iv)). The internal views to
  staff are bound by the same rule: R9.3 does not limit itself to customers.

### 3.5 What the run stores stays replayable

- G04, G05, and Slice 4's replay condition: the stored rows are reproduced
  from the stored snapshots and the stored versions.
- **Consequence.** Every function that fills `suggested_actions` or
  `relaxation_scenarios` is pinned in the rule registry, with its version
  stored beside its output, and an entry in `registry_history.HISTORY` in
  the same change (`SLICE_4_CLOSURE.md` §6). Any input it reads that is not
  already in a stored snapshot is stored with the scenario (F6-2).

### 3.6 Completion is one transaction, and loses nothing

- `API_CONTRACTS` §4.10 and the contract's description: "Append a
  task_completion_event and mark task DONE in one transaction.
  Outcome/evidence must not be discarded." I02.
- **Consequence.** The event row and the task's `status = DONE`,
  `completed_at` are written together, or neither. The `outcome_code`,
  `note` and `evidence_observation_id` received are stored exactly. None of
  them goes only to a log.

### 3.7 Audit

- Every row written is audited (Definition of Done: "audit/provenance is not
  silently skipped"): `tasks` by `audit_rows`, as since Slice 3, and
  `task_completion_events` added to its registry.
- Free text written by staff is withheld from the audit row, as the review
  of `1f8a8df` decided for `interactions.summary` (R6.3b: "staff notes"):
  `task_completion_events.note` is added to `audit_rows.WITHHELD`. The note
  stays in its own row.
- A read of the task list is audited once for the list (R6.3, R6.3c).

---

## 4. Findings measured while planning (not fixed)

**F6-1 · A unit discrepancy in the frozen sources.**
- Spec §14: "raising the budget by 150 million centimes", represented as
  `budget_delta_dzd = +1,500,000`.
- The mandatory test: "+150M centimes".
- I03: "Suggested `+150M DZD max budget`".
- The spec states the equivalence itself (150 million centimes ↔
  1,500,000 DZD), and its dataset is consistent with it: R-001's
  `budget_max = 24,000,000 DZD` against prices of "2.18B–2.55B centimes"
  (§25, §25.1). I03's "150M DZD" is a hundred times larger.
- **Proposed reading (G6-5 (iv)):** prices are stored in DZD
  (`asking_price_dzd`), so a magnitude is stated in DZD. The test of
  mandatory test 3 and I03 is the spec's scenario, `+1,500,000 DZD`. The
  handoff is not patched. The discrepancy is recorded here and in the test.

**F6-2 · The request snapshot does not carry the ancestry of a requested
location.** The property snapshot carries `location_ancestry` (format 2);
the request snapshot carries the requested location ids only. A location
magnitude (G6-6) needs both chains, so the requested chain must be read at
the run and stored with the scenario, or the scenario cannot be replayed.

**F6-3 · The schema has no adjacency between locations.** `locations` has a
parent chain, a `location_type` and optional coordinates. The spec's
`adjacent_zone` cannot be derived from it. `same_city` and `other_commune`
can only be approximated by the `location_type` of the nearest common
ancestor (G6-6).

**F6-4 · No reason code is seeded for a task outcome.**
`task_completion_events.outcome_code` is FK-constrained to `reason_codes`.
The seed has 26 codes (lines 135–160) in the categories MATCH, FRESHNESS,
PERMISSION, IDENTITY, OPPORTUNITY and GENERAL, plus Slice 2's REQUEST_CLOSURE codes
(migration `0002`). None names the outcome of an information task
("document verified", "no answer", …). G6-8 (ii).

**F6-5 · `task_completion_events` is not append-only in the schema**, and
neither table has a database audit trigger (§2, items 1 and 2).

**F6-6 · D5 and "high-value" may disagree.** `action.next@1` gives HIGH to
every actionable unknown. Under G6-2 (a), a task's priority would be HIGH
only for a high-value unknown. A match's stored `next_action` and the task
raised for it could then show different priorities. `action.next@1` is
pinned and stored; it is not changed (§3.5).

**F6-7 · Three task fields have no write path in the contract:**
`assigned_account_id`, `IN_PROGRESS` and `CANCELLED`. So `assigned_to_me`
returns nothing until a later slice assigns tasks (G6-9).

**F6-8 · "Near match" is narrower than the spec's words.** Spec §13: "fails
one or two conditions understandably"; spec §14 gives the failure set
`{location, document}`. D2 (Slice 4, decided) counts exactly one REQUIRED
FAIL, and `SLICE_4_CLOSURE.md` §6 records that it "does not claim every form
of that phrase" (G6-5 (ii)).

**F6-9 · Slice 5's NMI task is typed and prioritised differently from D5.**
`match_review._create_task` takes the reviewer's `task_type` and sets HIGH
when the match has any blocking unknown. A task raised by the run for the
same unknown (G6-4 (a)) would be a second, independent record (G6-4 (iv)).


**Measured in step 0** (`SLICE6-PLAN-MEASUREMENTS.txt`, sections L, D, T,
E):

**F6-10 · A requested location's chain is stored nowhere, and can change
(L1–L5).**
- A match stores the requested ids (`request_value.value`), the property's
  location and the property's chain (its snapshot). In L3, ADR-KSOUR, an
  ancestor of the requested ADR-KSAR-TILILANE and not of the property, is
  in none of the match, criterion or diagnostic rows.
- `locations.parent_id` can be updated; the only trigger stamps
  `updated_at`. No application path writes `locations` today.
- With `LOCATION IN`, two requested locations can give different nearest
  common ancestors (L1: C-ADRAR, COMMUNE; W-ADRAR, WILAYA), or the same one
  (L2, L3). Every common ancestor lies on the property's chain, so a tie is
  never between two different ancestors at one depth: it is between the
  requested locations that reach the same ancestor, widened by the same or
  by a different number of levels (L3: 2 against 1).

**F6-11 · A diagnostic row cannot name the matches it evaluated (D).**
- Run 2, after offer O2's price changed, reused P1's match (same id) and
  stored a new one for P2. The diagnostic row has no column naming a match.
- The reused match keeps run 1's `evaluated_at`: only P2's match carries
  run 2's `run_at`.
- The `input_hash` digests a document listing `[property, offer, match
  input_hash]` per candidate; the document is not stored. The exclusions
  are stored (`blocker_summary.excluded`, with ids).

**F6-12 · "Latest" diagnostic is by transaction start (D4).** Of two
overlapping runs, the one that committed last is not the one
`read_latest_diagnostic` returns (`ORDER BY run_at DESC`, `run_at` being the
transaction's start). Recorded, not changed: it is Slice 4's delivered read
(§0's boundary). Tasks under G6-4 (a) are raised by the run from its own
evaluations, never from "the latest" row, so they do not depend on it.

**F6-13 · The narrow task key merges distinct work (T).** One property with
two offers, both above the maximum and negotiable: `action.next@1` names two
subjects (PROPERTY_OFFER A and B), each CONFIRM_PRICE on BUDGET_MAX. The key
(request, property, type, criterion, ordinal) gives ONE key for the two; the
key (entity, id, gate, criterion, ordinal, basis) gives two. Offer B also
carries OFFER_STALE on the OFFER: the same type, another gate and basis.

**F6-14 · An NMI task's reason and its stored recommendation can name
different work (T3).** Slice 5's NMI task stores `payload =
{match_review_id, next_action}`. A second NMI on the same match with the
reason OFFER_STALE made a task with `reason_code = OFFER_STALE` and a
`next_action.subject` naming the INFORMATION unknown on BUDGET_MAX.

**F6-15 · Under REPEATABLE READ only a unique index prevents the duplicate
(T4, T5).**
- A partial unique index on the subject key: the second of two concurrent
  inserts waits on the first, then fails 23505 once it commits.
  `WHERE status = 'OPEN'` lets a second OPEN task in while the first is
  IN_PROGRESS; `WHERE status IN ('OPEN','IN_PROGRESS')` refuses it.
- A lock-then-check does NOT prevent it, with an advisory lock on the key
  or with the request row `FOR NO KEY UPDATE`: the second transaction's
  snapshot predates the first's commit, it sees no task, and two result.
  The run is REPEATABLE READ (Slice 4, condition 1). PostgreSQL 16
  documentation, §13.2.2: a Repeatable Read transaction "sees a snapshot as
  of the start of the first non-transaction-control statement in the
  transaction".

**F6-16 · An append-only guard on completion events also forbids deleting
the cited observation; it does not protect the observation's body (E1,
E2).**
- No trigger exists on `observations`, `evidence_artifacts`, `tasks` or
  `task_completion_events`. Unlike claims, observations have no
  hard-delete guard (schema lines 1302–1307).
- Without a guard: the observation's body can be updated; the observation
  can be deleted, and the event's `evidence_observation_id` silently
  becomes NULL; an event can be updated and deleted; a DONE task can be
  reopened.
- With a candidate append-only trigger on the events: UPDATE of an event is
  refused, and DELETE of the cited observation is refused too, because its
  SET NULL action is an UPDATE of the event that fires the trigger. UPDATE
  of the observation's body is still accepted.
- No application path updates or deletes an observation today.

**F6-17 · The outcome FK accepts any code, of any category, active or not
(E3); and a second completion under REPEATABLE READ fails 40001 (E4).**
- `DEAL_CONFIRMED` and `BUYER_REJECTED` (category OPPORTUNITY) are accepted,
  as is a code made inactive; null is accepted; an unknown code is refused
  (23503). No seeded category describes the outcome of a task.
- Two completions of one task, the second waiting on `FOR UPDATE`: under
  READ COMMITTED, the default of every command except the run, the second
  reads DONE once the first commits; under REPEATABLE READ it fails 40001.

---

## 5. Decisions needed — none is taken by this plan

### G6-1 · Scope: which operations and writes are Slice 6's

- **Recommendation:** §0 and §1 as proposed.
  - Route `getTasks` and `postTasksTaskIdComplete`.
  - The run fills `suggested_actions` and `relaxation_scenarios` in the
    diagnostic rows it writes from now on. Rows already written stay `[]`.
  - Tasks from the diagnostic: G6-4.
- **Blocks:** everything.

### G6-2 · What "high-value" means, and the priority of information work

- **(a) Recommended. High-value = the unknown alone stands between the
  candidate and ELIGIBLE.** For a NEED_MORE_INFORMATION candidate:
  - it has exactly ONE actionable unknown;
  - and its freshness and permission gates are PASS.

  Priority **HIGH** for it. Every other actionable unknown: **NORMAL**.
  Reconfirmation and permission work: **NORMAL**, as in D5. **LOW** and
  **URGENT** are not used.
  - **Source:** spec §13.1 ("alone"), `API_CONTRACTS` §4.9 ("when resolving
    the unknown could yield an exact match").
  - **Cost:** F6-6, a visible difference from the stored `next_action`.
- **(b) Keep D5's reading.** Every actionable unknown is HIGH. Simpler and
  consistent with the stored `next_action`. But it does not tell a
  candidate one fact away from ELIGIBLE apart from one three facts away,
  which is the deliverable "high-value information gap detection".
- **Under both,** mandatory test 1 holds: the document UNKNOWN on an
  otherwise exact candidate (M-12, P08 against R-001) is HIGH and ranks
  above any relaxation scenario (G6-5 (i)). Mandatory test 2 holds by §3.3.
- **Blocks:** step 3.

### G6-3 · `suggested_actions`: content and order

- **Recommendation:** a pinned function, `diagnostic.actions@1`, over the
  run's own evaluations. It is stored with its version.
  - **One entry per distinct subject of work:**
    `(type, entity, entity id, criterion, ordinal)`. A subject shared by
    several candidates appears once, with the ids of the candidates it
    concerns.
  - **Entries come from** NEED_MORE_INFORMATION and NEEDS_CONFIRMATION
    candidates, as typed by D5's mapping (VERIFY_DOCUMENT, CONFIRM_PRICE,
    OTHER, RECONFIRM_REQUEST, RECONFIRM_PROPERTY, CONFIRM_PERMISSION). It
    covers EVERY actionable unknown, freshness reason and permission reason
    of each candidate, not only its first.
  - **Order, fixed:**
    1. priority (G6-2);
    2. §13.1's class order: information, reconfirmation (request, property,
       offer), permission;
    3. the number of candidates the entry concerns, descending;
    4. the entity id, then the criterion and ordinal, ascending (a total,
       reproducible order).
  - **The first entry is the contract's "highest-value next information
    action"** (§4.9). Every entry is a recommendation; none is a task by
    itself (G6-4).
  - **Never in an entry:** a value of the property, the offer or a claim; a
    seller expectation (§3.4). Ids, codes, the basis and the count only.
- **Blocks:** step 3.

### G6-4 · Tasks raised from the diagnostic

- **(a) Recommended. The run materializes its suggested actions as tasks.**
  - **Which:** every HIGH entry of `suggested_actions` (G6-2 (a): the
    high-value unknowns). NORMAL entries stay recommendations, so staff are
    not flooded (spec §13: a non-blocking unknown "does not … burden the
    staff to collect it now"; the same restraint is proposed for
    non-high-value work).
  - **(i) Where:** in the run's transaction, after its diagnostic row. A
    refused run still writes nothing (D6).
  - **(ii) What it stores:**
    - `task_type`, `priority`, `reason_code` from the entry;
    - the request, property and match ids;
    - a fixed English `title` per type, as Slice 5's `TASK_TITLES`;
    - `payload`:
      - `diagnostic_run_id`;
      - the subject (entity, id, gate, criterion, ordinal, basis);
      - `"source": "DIAGNOSTIC"`.
  - **(iii) No duplicate open work (revision 2, on F6-13 and F6-15).**
    - **The key is the subject of the work**, as `action.next@1` and
      `diagnostic.actions@1` name it:
      `(request_id, subject.entity, subject.id, subject.gate,
      subject.criterion, subject.ordinal, subject.basis)`. The entity and id
      are the request, the property or the specific OFFER. The gate,
      criterion, ordinal and basis are the specific reason.
      - Two offers of one property are two subjects (F6-13).
      - Offer B's price unknown (INFORMATION, BUDGET_MAX) and its stale
        terms (FRESHNESS, OFFER) are two subjects of the same type
        CONFIRM_PRICE: two tasks.
    - **It covers OPEN and IN_PROGRESS**, so work taken up is not raised
      again (F6-15).
    - **The mechanism is a partial unique index** (§5.1, part C). A lock
      cannot do it inside the run's REPEATABLE READ snapshot (F6-15).
      - Each task insert runs under its own savepoint, as the run's match
        inserts do.
      - A 23505 on this index means the work is already open. The savepoint
        is rolled back, and the suggested action records
        `"task": "ALREADY_OPEN"`. The existing task may have been committed
        after the run's snapshot, so its id is not read.
    - **The index covers only the run's tasks**
      (`payload->>'source' = 'DIAGNOSTIC'`). Slice 3's and Slice 5's tasks
      are outside it and unchanged.
  - **(iv) The relation with Slice 5's NMI task (F6-14).**
    - **(a) Recommended: independent records.**
      - An NMI task records a reviewer's request. G5-4 (a) decided that a
        repeated NMI makes a second task, so it cannot share the index.
      - The run does not consult NMI tasks. An NMI task and a diagnostic
        task may therefore name the same work. `GET /tasks` shows both;
        each says its source (`match_review_id` against
        `"source": "DIAGNOSTIC"`).
      - No race and no inference.
    - **(b) The run skips a subject named by an OPEN or IN_PROGRESS NMI
      task's `payload.next_action.subject`.** Not recommended:
      - the check reads the run's snapshot, so an NMI committed after it is
        not seen (F6-15);
      - an NMI task's reason may name other work than its stored
        recommendation (F6-14), so the skip could suppress work no reviewer
        asked for.
  - **(v) Cost:** it changes Slice 4's approved boundary (G4-15 D1: "no task
    created"). `matching_run.py` becomes a third writer of `tasks`, after
    `identity.py` and `match_review.py`. That is a writer change requiring
    this decision.
- **(b) No task from the diagnostic.**
  - `suggested_actions` stays a recommendation.
  - Tasks continue to be raised only by an NMI review (Slice 5) and an
    identity consolidation (Slice 3).
  - Mandatory tests 1 and 2 are then proven on `suggested_actions`' order
    and priority, not on task rows.
  - **Cost:** "focused operational tasks" from information gaps would exist
    only after a reviewer's NMI decision on each match.
- **Blocks:** step 4.

### G6-5 · Relaxation scenarios

- **(i) When they are computed.**
  - **(a) Recommended:** on every run, stored, and **ranked after every
    HIGH information action**. Each scenario carries `"subordinate_to"`:
    the ids of the high-value actions that exist in the same run.
    - Mandatory test 1 and I01 compare a task with a relaxation suggestion,
      so both must exist to be compared.
    - The rule's own condition ("when resolving the unknown could create an
      exact candidate") is then visible, not hidden.
  - **(b) Strict reading of §13.1, step 5:** a scenario is computed only
    when the run has no ELIGIBLE candidate and no high-value unknown ("if
    the result still has no Opportunity"). Simpler. Mandatory test 1 then
    holds because the scenario is absent.
- **(ii) Which candidates.**
  - **(a) Recommended:** D2's near matches only: one REQUIRED FAIL, every
    other REQUIRED PASS. The count and the scenarios then use one definition.
  - **(b)** One or two REQUIRED FAILs, as spec §13 and §14's
    `{location, document}` suggest (F6-8). A two-criterion scenario is
    reported as one scenario with both magnitudes, never as two independent
    ones. `near_match_count` keeps D2's meaning in both options.
- **(iii) Which criteria, and how each is stated.** One table, fixed in the
  pinned function `diagnostic.relaxation@1`:

  | Criterion | Scenario | Magnitude |
  |---|---|---|
  | BUDGET_MAX (SALE) | raise the maximum | `{"budget_delta_dzd": ask − max}`, from the asking price (iv) |
  | LAND_AREA_MIN, BUILT_AREA_MIN | lower the minimum | `{"area_delta_m2": area − min}` (negative) |
  | ROOMS_MIN, BEDROOMS_MIN (`criterion.count_min`) | lower the minimum | `{"count_delta": value − min}` (negative) |
  | LOCATION | widen the area | G6-6 |
  | PROPERTY_TYPE | accept another type | the property's type, named; no number |
  | attribute options | accept another option | the property's option, named |
  | DOCUMENT_TYPE, RIGHT_TYPE | **not proposed as a lowering.** The scenario states the effect only "if the user explicitly chooses it" (spec §14) | the property's document type, named |
  | the transaction intent | **never** (BUY ↔ SALE only, C01) | — |

- **(iv) The budget magnitude and R9.3.** The magnitude is `ask − max`, from
  the asking price. It is labelled "at the asking price". It is **not**
  called the minimum, because the rule also passes a price when the
  seller's private expectation is within the maximum (G4-5). Stating the
  smaller, expectation-based amount would render the expectation (§3.4).
  In DZD (F6-1).
- **(v) Aggregation.** Per criterion and direction, the scenarios are
  ordered by magnitude, smallest first. Each states how many near matches it
  would turn into a hard-gate PASS, and which. It states the eligibility
  those candidates **would reach** on the stored facts (ELIGIBLE, or
  NEEDS_CONFIRMATION with its reasons). It never says "would become an
  opportunity": that needs a human review (Slice 5).
- **(vi) Staff only.** Scenarios appear in the internal diagnostic. No
  customer DTO carries them. `CustomerOpportunityView` has no field for
  them, and R9.5's allow-list tests keep it so.
- **Blocks:** step 3.

### G6-6 · The location magnitude (revision 2, on F6-10)

- **Which requested location.** A LOCATION criterion is EQ (one requested
  location, including the column `primary_location_id`) or IN (several:
  `location_v2` passes when the property lies under ANY of them). For a FAIL,
  the function evaluates **every** requested location `w`, in the order the
  stored `request_value.value` gives:
  - `common(w)`: the first location of the property's chain (nearest first)
    that is also in `w`'s chain; null if none;
  - `property_below(w)`: the position of `common(w)` in the property's chain;
  - `widened(w)`: its position in `w`'s chain, the number of levels `w`
    would be widened by.
- **The choice, total and reproducible:**
  1. the smallest `property_below`: the nearest ancestor of the property,
     so the narrowest widening;
  2. then the smallest `widened`: the requested location closest to it
     (L3: ADR-NEW-TIL, 1 level, before ADR-KSAR-TILILANE, 2 levels);
  3. then the earliest position in `request_value.value`.

  As F6-10 shows, step 1 already fixes WHICH ancestor. Steps 2 and 3 only
  fix which requested location is named. A requested location with no common
  ancestor is ranked last; if none has one, the scenario is
  `{"widen_to": null, "level": "NONE"}`.
- **Stated as:**
  - `{"widen_to": <common id>, "level": <its location_type>,
    "from": <the chosen w>, "levels_widened": <widened>}`;
  - with every evaluated `w` listed with its own three values, so the
    choice can be checked.
  - The scenario reads "add `widen_to` to the requested locations". It is
    taken only through `postRequestsRequestIdCriteria` (§3.1).
- **What is stored, so the scenario replays without reading `locations`
  again** (F6-10: chains can change):
  - each requested location's chain, as read in the run's snapshot, as
    `[{location_id, location_type}, …]`, nearest first;
  - it is stored in the diagnostic row (§5, G6-11), and enters the
    diagnostic's input document.
  - The property's chain is already in the match's snapshot (format 2).
- **`adjacent_zone` is not produced:** the schema has no adjacency (F6-3).
- **The measured cases L1–L4 become the tests:** two different ancestors;
  a full tie on one ancestor; one ancestor by different widenings; two
  ancestors at two depths. EQ is tested as IN of one.
- **Blocks:** step 3.

### G6-7 · Blocking and non-blocking unknowns in the diagnostic

- **Recommendation:** `blocker_summary` format 2 (`turab.blocker-summary/2`)
  adds `unknowns`: per criterion key (`CODE#ordinal`), the number of
  candidates with that criterion UNKNOWN. These are split into `blocking`
  and `non_blocking` (G4-4), and within `blocking`, `actionable` and
  `high_value` (§3.2).
  - Format 2 also names the versions of `diagnostic.actions` and
    `diagnostic.relaxation` used. An empty `suggested_actions` or
    `relaxation_scenarios` in a format-2 row then means "none", and in a
    format-1 row "not computed" (Slice 4, D1).
  - The three counts keep D3's meaning.
- **Blocks:** step 3.

### G6-8 · Completing a task (`postTasksTaskIdComplete`) (revision 2, on F6-16 and F6-17)

- **(i) Which tasks.**
  - An OPEN or IN_PROGRESS task is completed.
  - A DONE or CANCELLED task: **409** `TASK_NOT_OPEN`, writing nothing.
  - A replay of the same key returns the first response (K05).
  - The command runs READ COMMITTED, as every command but the run. It locks
    the task row `FOR UPDATE` before the check. A second, concurrent
    completion then waits, reads DONE, and is refused 409 (F6-17, E4).
    Under REPEATABLE READ it would fail 40001 instead, a 500 the command
    does not need.
- **(ii) `outcome_code`: an explicit choice (F6-17).** The general codes are
  withdrawn as an option: the FK accepts OPPORTUNITY codes such as
  `DEAL_CONFIRMED`, which would misdescribe a task.
  - **(a) Recommended: dedicated outcome codes**, by migration `0007`
    (§5.1, part B), category `TASK_OUTCOME`. Proposed, for approval as
    domain vocabulary:

    | code | label_en | label_ar |
    |---|---|---|
    | `TASK_INFORMATION_OBTAINED` | The information asked for was obtained | تم الحصول على المعلومة المطلوبة |
    | `TASK_INFORMATION_UNAVAILABLE` | The information asked for could not be obtained | تعذر الحصول على المعلومة المطلوبة |
    | `TASK_PARTY_UNREACHABLE` | The party could not be reached | تعذر الوصول إلى الطرف |
    | `TASK_NO_LONGER_NEEDED` | The task is no longer needed | لم تعد المهمة لازمة |

    - `outcome_code` is then REQUIRED, and only these four are accepted;
      anything else is **422** `TASK_OUTCOME_NOT_ALLOWED`. Requiring it
      narrows the contract's nullable field; it adds nothing to it.
    - **What a code means, and does not:**
      - `TASK_INFORMATION_OBTAINED` says only that the work was done;
      - the fact itself is recorded through its own command (Slice 3's
        truth layer);
      - the code changes no fact (v).
  - **(b) Null only.**
    - `outcome_code` must be null; any code is **422**.
    - **The meaning of null, stated:** "this task is done; its outcome is
      not coded; what happened is in the note and the evidence".
    - **Its limits:** no structured outcome exists for reporting or later
      learning (Definition of Done: "data needed by future learning is
      preserved"). I02's "stores outcome code" is met only by storing null.
- **(iii) `evidence_observation_id`.**
  - Null, or an existing observation: **422** otherwise.
  - The observation is not required to concern the task's subject. The
    schema links an observation to a property or a request only through
    claims and sources.
- **(iv) The evidence, kept (F6-16).**
  - **(a) Recommended: two guards, in `0007` (§5.1, parts A and D):**
    - the events are append-only (part A). As measured, this also refuses
      deleting an observation cited by an event, because the FK's SET NULL
      is an UPDATE of the event. That consequence is intended ("evidence
      must not be discarded") and is tested explicitly;
    - an observation cited by an event cannot be updated or deleted
      (part D), with its own message, so the refusal is not the SET NULL's
      side effect.
    - **Cost:** part D touches a Slice 3 table, `observations`. No
      application path updates or deletes an observation today.
  - **(b) Part A only.** The reference is kept, but the cited observation's
    body can still change, with no audit trigger on `observations`. **The
    stated limit:** the event proves which observation was cited, not what
    it said at completion.
  - Both are proven at trigger level only, under the superuser role (K06
    UNPROVEN).
- **(v) No side effect on facts.**
  - Completing a task changes no property, offer, request, claim,
    verification level or consent.
  - It runs no matching and closes no opportunity.
  - Facts change only through their own commands (Slice 3's truth layer).
  - Spec §17.2, invariant 9, and F01–F02 (no self-upgrade of verification).
  - The operator re-runs matching to see the effect.
- **(vi) The response** is the contract's `Task`, now DONE. The note is not
  returned: `Task` has no field for it.
- **(vii) A DONE task stays DONE.**
  - No path reopens it. The schema permits it (F6-16), so a test asserts
    the command never does.
  - Guarding it in the database is not proposed: `tasks` has no history
    trigger, and none is asked for.
- **Blocks:** step 2.

### G6-9 · Listing tasks (`getTasks`)

- **Recommendation:**
  - **`status` and `priority`** are compared as TEXT: the contract types
    them as plain strings with no enum, as `identity.list_candidates`
    already does. A value naming no status returns nothing; it is not a 422.
  - **`assigned_to_me=true`** filters on `assigned_account_id` = the
    caller's account. It is empty today (F6-7), and this is stated in the
    route's docstring.
  - **Order:** priority (URGENT, HIGH, NORMAL, LOW), then `created_at`,
    then `task_id`.
  - **Page and PageSize** as the other queues.
  - **The list read is audited once** (R6.3c).
  - **Every task is returned,** whichever writer raised it. The payloads
    of the three writers carry ids, codes and bases only. A test asserts
    no payload carries a seller expectation, a claim value or free text.
- **Blocks:** step 2.

### G6-10 · Tasks whose cause has gone

- **(a) Recommended. No automatic change.** A later run that no longer
  finds the unknown leaves the task OPEN. The task records that the work was
  asked for, and staff complete it with an outcome. The diagnostic no longer
  suggests it.
- **(b)** The run cancels its own OPEN tasks whose subject is resolved
  (`status = CANCELLED`). There is no contract command for CANCELLED (F6-7),
  and this adds a second write path to task state.
- **Blocks:** step 4.

### G6-11 · Versions and replay (revision 2, on F6-11)

- **Versions.** `diagnostic.actions@1`, `diagnostic.relaxation@1`, and,
  under G6-2 (a), `diagnostic.value@1` (the high-value classification) are
  registered in the registry. They are recorded in
  `registry_history.HISTORY` in the same change.
- **The stored link from a diagnostic row to what it evaluated.**
  `blocker_summary` format 2 (G6-7) carries `evaluated`: one entry per
  candidate, in the run's evaluation order. Each entry has:
  - `property_id` and `offer_id`;
  - `match_id`: the row the run wrote, or the identical row it found and
    reused (G4-13);
  - the match's `input_hash`;
  - `stored`: `NEW` or `EXISTING`.

  It also carries:
  - `requested_location_chains` (G6-6);
  - the exclusions, as in format 1.

  The table has no column for the link; the plan adds none. The size grows
  with the candidates, one entry each (§6.5 could not measure format 2
  before its code).
- **The input document.** `turab.diagnostic-input/2` adds the requested
  location chains to format 1's document. The match ids are not in it: they
  are outputs, and an identical input must give an identical hash.
- **Replay.**
  - A reconstruction, run as a test in every run of the suite, reads the
    diagnostic row.
  - It loads the match rows that `evaluated` names, by id and in that
    order, and checks each one's `input_hash` against the entry.
  - It re-derives `suggested_actions`, `relaxation_scenarios` and the
    format-2 summary from those rows and the stored chains. Any difference
    fails.
  - It never infers the evaluated matches from `evaluated_at` (F6-11).
- **The test the review asked for:**
  - two runs of one request, with an offer's price changed between them;
  - run 2's `evaluated` names P1's REUSED match (`EXISTING`, run 1's id)
    and P2's NEW one;
  - both diagnostic rows replay;
  - after a requested location is re-parented, the replay still gives the
    stored scenario.
- **Blocks:** step 3.

### G6-12 · K06 and the application role (not blocking this plan)

- G5-13 (b)(ii) is a separate, cross-cutting step, mandatory before any
  release gate. It is not a Slice 6 deliverable.
- **The question:** whether it is scheduled before Slice 6's code, in
  parallel, or after. Recommended: decided by the reviewer independently of
  this plan. Nothing here depends on it, and nothing here claims K06.


### 5.1 The proposed text of migration `0007` (for approval; not written)

`0007_task_work_and_evidence`, revising `0006_opportunity_history`. Four
parts, each tied to its decision. A part whose decision is not approved is
left out; the others stand alone. Structural only, except part B's codes.
Proven at trigger level only, under the superuser role (K06 UNPROVEN).

**A. The events are append-only** (G6-8 (iv)). It reuses the frozen
function `prevent_immutable_history_change()`, as `0005`'s triggers do:

```sql
CREATE TRIGGER prevent_task_completion_event_change
  BEFORE UPDATE OR DELETE ON turab.task_completion_events
  FOR EACH ROW EXECUTE FUNCTION turab.prevent_immutable_history_change();
```

Consequence, measured (F6-16) and tested: deleting a cited observation is
refused through the FK's SET NULL.

**B. The task outcome codes** (G6-8 (ii) (a)), inserted as `0002` inserts
its codes. `downgrade()` refuses, for the same reason as `0002`'s: an event
may reference them.

```sql
INSERT INTO turab.reason_codes (code, category, label_ar, label_en, active)
SELECT v.code, 'TASK_OUTCOME', v.label_ar, v.label_en, true
  FROM (VALUES
    ('TASK_INFORMATION_OBTAINED',    'تم الحصول على المعلومة المطلوبة', 'The information asked for was obtained'),
    ('TASK_INFORMATION_UNAVAILABLE', 'تعذر الحصول على المعلومة المطلوبة', 'The information asked for could not be obtained'),
    ('TASK_PARTY_UNREACHABLE',       'تعذر الوصول إلى الطرف', 'The party could not be reached'),
    ('TASK_NO_LONGER_NEEDED',        'لم تعد المهمة لازمة', 'The task is no longer needed')
  ) AS v(code, label_ar, label_en)
 WHERE NOT EXISTS (SELECT 1 FROM turab.reason_codes r WHERE r.code = v.code);
```

**C. One open task per subject of work** (G6-4 (a) (iii)):

```sql
CREATE UNIQUE INDEX ux_one_open_task_per_subject ON turab.tasks (
    request_id,
    (payload -> 'subject' ->> 'entity'),
    (payload -> 'subject' ->> 'id'),
    (payload -> 'subject' ->> 'gate'),
    (coalesce(payload -> 'subject' ->> 'criterion', '')),
    (coalesce(payload -> 'subject' ->> 'ordinal', '')),
    (payload -> 'subject' ->> 'basis'))
  WHERE status IN ('OPEN', 'IN_PROGRESS')
    AND payload ->> 'source' = 'DIAGNOSTIC';
```

Measured (T4) with the same key and status predicate, without the `source`
predicate. The `source` predicate only narrows which rows the index
covers; step 1's tests prove the race again with this exact text. Neither
existing writer of `tasks` puts a `source` key in the payload
(`identity.py`: alias, canonical, candidate and affected ids;
`match_review.py`: `match_review_id`, `next_action`), so the index applies
to no task they write.

**D. A cited observation is kept as cited** (G6-8 (iv) (a)):

```sql
CREATE FUNCTION turab.prevent_cited_observation_change()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF EXISTS (SELECT 1 FROM turab.task_completion_events
              WHERE evidence_observation_id = OLD.observation_id) THEN
    RAISE EXCEPTION 'Observation % is the evidence of a task completion and cannot change',
      OLD.observation_id;
  END IF;
  RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
END $$;
CREATE TRIGGER trg_cited_observation_unchanged
  BEFORE UPDATE OR DELETE ON turab.observations
  FOR EACH ROW EXECUTE FUNCTION turab.prevent_cited_observation_change();
```

- **Its message carries an id.** Like every trigger message (Slice 5,
  §6.4.7), it never reaches a response body.
- **A further consequence, stated (derived from the schema; not measured).**
  `observations` references `sources`, `parties` and `user_accounts`, each
  ON DELETE SET NULL (schema lines 498, 500, 505). Deleting one of them
  would UPDATE a cited observation, and part D refuses that UPDATE.
  - No application path deletes a source, a party or an account (grep of
    `src/` at `f7469e8`).
  - Step 1's tests prove this consequence by measurement.

---

## 6. Tests and closure evidence

### 6.1 The three mandatory tests

| # | Test, as written | Proof planned |
|---|---|---|
| 1 | "document UNKNOWN on otherwise exact candidate becomes higher-priority task than suggesting a new location" | R-001 with P08 (document UNKNOWN, everything else PASS) and P03 (location FAIL only). Over HTTP: one run. The VERIFY_DOCUMENT entry is first in `suggested_actions`, HIGH; under G6-4 (a), it is a HIGH task. The location scenario for P03 is ranked after it and `subordinate_to` it (G6-5 (i) (a)). M-12, I01 |
| 2 | "candidate failing three hard criteria does not receive high-priority task for an unrelated unknown" | a property failing LOCATION, BUDGET_MAX and PROPERTY_TYPE, with an UNKNOWN document. No task, no suggested information action, no scenario (not a near match) for it (§3.3) |
| 3 | "relaxation scenario reports magnitude (e.g. +150M centimes / adjacent area), not only 'remove criterion.'" | after the document of P08 is resolved to a FAIL (M-13), the near matches yield: `budget_delta_dzd = 1500000` for a property at max + 1,500,000 DZD, not negotiable (F6-1); the location scenario with its level (G6-6; `adjacent_zone` not produced, F6-3) |

### 6.2 Red-team cases

- **I01:** mandatory test 1.
- **I02:** a completion stores `outcome_code`, `note` and
  `evidence_observation_id` in one event, and the task is DONE, in one
  transaction. A failure injected between the two writes leaves neither.
- **I03:** a run producing `+1,500,000 DZD` leaves the request's row,
  `version` and criteria unchanged (§3.1). Then an explicit
  `postRequestsRequestIdCriteria` changes it, and the next run sees it.
- **D02 / R9.3:** a near match whose seller expectation lies between the
  maximum and the asking price. The scenario's magnitude is `ask − max`;
  no output of the run, the diagnostic, the task list or the audit contains
  the expectation (§3.4).
- **K05:** a completion replayed with its key returns the first response
  and writes nothing. A different body with the same key is refused.
- **G04 / G06:** replay (G6-11); a run with no candidate produces an empty,
  valid diagnostic (format 2).
- **K06:** not claimed. The append-only trigger of G6-8 (iv) is proven at
  trigger level only, and labelled so.

### 6.3 Authorization

- Positive and negative cases for both new operations, per the Definition
  of Done: each of ADMIN, OPERATOR, REVIEWER allowed; CUSTOMER and
  anonymous refused (401/403); the refusal audited (R6.3a).
- The authorization matrix (`authorization_evidence.py`) gains the two
  operations.

### 6.4 Closure evidence (no STOP GATE)

- The evidence round of Slices 4–5: the suite on a clean tree bound to its
  commit and source fingerprint; mutations per step; the authorization
  matrix; the PostgreSQL gate; document hashes.
- **Proposed:** a generated evidence document, `SLICE_6_EVIDENCE.md`, by a
  generator with `--check`, as STOP GATE E's, mapping each mandatory test
  and red-team case to its bound test. It is not called a STOP GATE.

### 6.5 Measurements (step 0, delivered)

Delivered in `evidence/SLICE6-PLAN-MEASUREMENTS.txt` (sections L, D, T, E,
S). Its results are F6-10 to F6-17.

**What it could not measure:**
- the size of `blocker_summary` format 2, which does not exist before its
  code;
- the index of §5.1 part C with its `source` predicate. Step 1 measures
  both, in its tests.

---

## 7. Acceptance conditions

1. **The contract is unchanged.** No operation, field or type added; the
   overlay only narrows.
2. **No REQUEST changes** through a diagnostic, a scenario, a task or a
   completion (§3.1, I03).
3. **The seller expectation** appears in no output of this slice, and no
   magnitude is computed from it (§3.4, D02).
4. **The GET diagnostic writes nothing,** and no diagnostic row is ever
   updated (`0005`).
5. **The stored diagnostic replays** (G6-11).
6. **A completion is atomic, append-only and keeps everything it
   received** (§3.6, G6-8).
7. **Relations are never an authorization source, nor a matching input.**
8. **SALE only** (G4-5R open). **K06 UNPROVEN** (G6-12).
9. **No AI** in any path.
10. **The writers of `tasks`** are exactly those decided: `identity.py`,
    `match_review.py`, and `matching_run.py` only if G6-4 (a). The closure
    evidence checks this as STOP GATE E checked its writers.

---

## 8. Sequence

| Step | Content | Depends on |
|---|---|---|
| 0 | the measurements of §6.5, folded into revision 2; no code | **done** (authorized in the review of `f7469e8`); `SLICE6-PLAN-MEASUREMENTS.txt` |
| 1 | migration `0007`, the parts of §5.1 whose decisions are approved, exactly as approved; tests, mutations | G6-4 (iii), G6-8 (ii), G6-8 (iv) |
| 2 | `getTasks` and `postTasksTaskIdComplete` | G6-8, G6-9 |
| 3 | the pure functions: high-value (G6-2), `suggested_actions` (G6-3), relaxation (G6-5, G6-6), `blocker_summary` format 2 (G6-7), their registry entries and replay (G6-11) — no write yet | G6-2, G6-3, G6-5, G6-6, G6-7, G6-11 |
| 4 | the run writes them; tasks from the diagnostic only if G6-4 (a); G6-10 | G6-4, G6-10 |
| 5 | the mandatory and red-team tests end to end, mutations, the closure evidence (§6.4) | all |

Each step is delivered with its tests and mutation record, and reviewed
before the next begins. A defect found in a step is measured before it is
fixed.

---

## 9. Document identity

This file's sha256 is recorded in `docs/gate/evidence/DOCUMENT-HASHES.txt`
at the commit that adds it.
