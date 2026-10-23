# Slice 6 — Match Diagnostic / Information Work
## Implementation plan — **revision 11**

**Status: the decisions G6-1 to G6-12, the text of `0007` (§5.1) and
CORRECTION-005 (§5.2) are APPROVED** (review of `bd54216`, recorded below).
Code is written one approved step at a time, never ahead of its approval
(§8). Step 1 (`0007`) is **CLOSED at `b6a08e7`** (review of `b6a08e7`, recorded
below), with an addendum that pins two limits of part C's index (M-1) and
states two more (M-2, M-3); the addendum changes no line of `0007`. Step 2
was authorized once the addendum was delivered, and is **CLOSED at
`315804b`** (review of `315804b`, recorded below). Step 3 is **CLOSED at
`922a100`** (review of `922a100`, recorded below), after its three replay gaps
were closed. Step 4 is **authorized**. Step 0 (measurements only)
was authorized in the review of `f7469e8`, delivered at `1fd7bdf`, and accepted
in the review of `1fd7bdf` as the basis for review:
`evidence/SLICE6-PLAN-MEASUREMENTS.txt`. Revision 3 adds the race the review
asked for: `evidence/SLICE6-PLAN-MEASUREMENTS-R3.txt`.

**What this revision does not decide.** Every choice below that is not
already fixed by a source is put to the reviewer as a decision (§5), with a
recommendation. A recommendation is not a decision.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | `f7469e8` | first plan |
| 2 | `1fd7bdf` | the review of `f7469e8` recorded; step 0 measured (`SLICE6-PLAN-MEASUREMENTS.txt`); G6-4 (iii)–(iv), G6-6, G6-8 and G6-11 rewritten on the measurements; F6-10 to F6-17 added; the text of migration `0007` proposed (§5.1) |
| 3 | `bd54216` | the review of `1fd7bdf` recorded; the completion/observation race measured (`SLICE6-PLAN-MEASUREMENTS-R3.txt`) and the completion's lock order specified (G6-8 (iv)); the suggestions kept pure, the task outcome read from the task rows (G6-4 (iii)); `stored` treated as a recorded fact (G6-11); the F6-12 staff-view test (G6-4 (v)); CORRECTION-005 proposed for `outcome_code` (§5.2); F6-18 to F6-20 |
| 4 | `62d3589` | the review of `bd54216` recorded: every recommendation of the decision table approved; each decision marked DECIDED; step 1 authorized |
| 5 | `b6a08e7` | step 1 delivered (`SLICE_6_STEP1_DELIVERY.md`): `0007` at `cd5b868`, 55 tests, 23/23 mutations; no other change |
| 6 | `caa9d33` | the review of `b6a08e7` recorded: step 1 closed at `b6a08e7`; M-1 accepted and pinned by an addendum; OQ6-1 and OQ6-2 opened (§5.3), neither approved; obligations added to steps 2 and 4 (§8); step 2 authorized after the addendum |
| 7 | `315804b` | step 2 delivered (`SLICE_6_STEP2_DELIVERY.md`): code at `038b6e8`, corrected at `93c4b3c` and `d09abbc`; mutations 34/34; suite 2511/2511. One reading put to the reviewer: §7 condition 10 and the completion's UPDATE of `tasks` (delivery note §6, choice 8); no other change |
| 8 | `a1d52d9` | the review of `315804b` recorded: step 2 closed; its seven choices accepted for step 2 only; §7 condition 10 rewritten to tell task creators from the completion's update, and §6.4 to inventory both; step 3 authorized |
| 9 | `220573a` | step 3 delivered (`SLICE_6_STEP3_DELIVERY.md`): code at `55dbee6`, its tests corrected at `83dd19a`, `0943e64`, `ef9c9ae`; mutations 34/34 twice; suite 2556/2556. Nine readings and the measured effect of the registration on match reuse put to the reviewer; no other change |
| 10 | `922a100` | the review of `220573a` recorded: step 3 not closed; the three replay gaps pinned by tests on `220573a`'s code (`e9d3a03`), then closed (`144ba96`); §3's readings and the digest's effect accepted; the measured supersession moved to step 4 |
| 11 | the commit that adds this revision | the review of `922a100` recorded: step 3 closed; the limit on `explain.blocker_summary` stated (§5.4); step 4 authorized with its two required experiments |

**The review of `922a100`. Step 3 is CLOSED at `922a100`, within its
approved scope. Step 4 is AUTHORIZED.**
- **What the reviewer checked:** the commits. `e9d3a03` added the tests
  and recorded the failures without touching `src/`. In the corrected
  code, (R) compares the property, offer and request; (D) compares
  `excluded_counts`; and the recomputation uses the versions the row
  records. The reviewer also read the single-change tests and the
  `@1`/`@2` test.
- **`explain.blocker_summary`, decided (§5.4):** left without a further
  pin in step 3.
- **Required of step 4:**
  - a run that writes a real format-2 row, which is then replayed;
  - the measured supersession of an older match, in the match queue and at
    approval, after the registry digest changed.
- **Not attributed to the reviewer:** 2562/2562 and 39/39 twice remain the
  implementing team's runs.
- **Carried, unchanged:** OQ6-1 and OQ6-2 open; K06 UNPROVEN; G4-5R open,
  SALE only.

**The review of `220573a`. Step 3 is NOT closed; step 4 does not start.**
- **What the reviewer found,** by reading the code and the tests (not by a
  PostgreSQL run): the replay G6-11 requires had three gaps.
  1. (R) did not compare an entry's `property_id` and `offer_id` with the
     match's row, nor check that the match is of the diagnostic's request;
  2. (D) did not compare `excluded_counts`, which `compute` derives;
  3. `compute` chose the three versions from its `@1` constants, and the
     replay did not pass the versions the row records: after a `@2` became
     the default, an old row would not be recomputed by its own versions.
- **Asked:** pin each case by a test on `220573a`'s code first, then fix
  the replay and present step 3 again.
- **Accepted:** the nine readings of the step 3 note (§3), as stated
  interpretations, including NEED_MORE_INFORMATION as a possible
  `would_reach`, NOT_PROPOSED as a diagnosis rather than a proposed change,
  and `turab.diagnostic-input/2` left to step 4; and the registry digest's
  effect, as G4-13's consequence.
- **Moved to step 4:** the test of the ACTUAL supersession of an older
  match, in the match queue and at approval; the note presented it as
  derived, not measured.
- **Not attributed to the reviewer:** 2556/2556 and 34/34 remain the
  implementing team's runs.
- **Carried, unchanged:** OQ6-1 and OQ6-2 open; K06 UNPROVEN; G4-5R open.

**The review of `315804b`. Step 2 is CLOSED at `315804b`, within its
approved scope. Step 3 is AUTHORIZED, as §8 describes it.**
- **What the reviewer checked.** The code and tests at that commit: the
  completion locks the task `FOR UPDATE`, then the observation `FOR SHARE`,
  before it inserts the event and updates the task; the race tests check the
  order of the waits and the refusal that writes nothing. This is consistent
  with the row-lock conflicts PostgreSQL 16 documents (§13.3.2).
- **What the reviewer did not do.** Re-run PostgreSQL, the suite or the
  mutations: 2511/2511, 34/34 and the gate's result remain the implementing
  team's results.
- **§7 condition 10, decided.** The reading of the delivery note (§6,
  choice 8) is accepted in its intent, but the words "the writers of
  `tasks`" were not exact: `tasks.py` IS a writer, by UPDATE. Condition 10
  is rewritten to tell task creators (INSERT) from the completion command
  (UPDATE of `status` and `completed_at`), and §6.4's closure evidence
  inventories both kinds. `tasks.py` may never be dropped from the
  inventory of writes. This corrects the closure evidence; it asks for no
  change to step 2's implementation.
- **The seven other choices of §6 are accepted for step 2 only:** the
  recorded 403 for an unknown id; the existing order of body and role
  checks; `assigned_to_me` false when absent; the task's completion instant
  equal to the event's; `TASK_NOT_OPEN`'s detail without an id; the exact
  response of the list; CORRECTION-005's recorded date. **Accepting the
  order of the body and role checks here makes it no rule for later
  routes.**
- **Carried, unchanged:** OQ6-1 and OQ6-2 give no licence to change the
  schema; K06 UNPROVEN; G4-5R open; SALE only.

**The review of `b6a08e7`. Step 1 is CLOSED at `b6a08e7`.**
- **The reading of «اعتمد» is confirmed.** The decisions G6-1 to G6-12, the
  text of `0007` and CORRECTION-005 are approved as revision 4 records
  them, and that approval extends to no other change of the schema.
- **M-1, accepted.** Part C's index implements the approved text, but it
  does not guarantee uniqueness for an incomplete diagnostic payload, nor
  for a `source` spelled otherwise. This is a substantive limit to be pinned
  before step 2 begins, not a reason to rewrite the migration.
  - **What the reviewer checked.** The text of the index in `0007`: `entity`,
    `id`, `gate` and `basis` are not coalesced, and the predicate compares
    `source` with `DIAGNOSTIC` literally; and that PostgreSQL treats NULLs
    as distinct in a unique index by default.
  - **What the reviewer did not do.** Re-run the two cases on PostgreSQL.
    They are our stated measurement
    (`evidence/SLICE6-STEP1-ADDENDUM-INDEX-LIMITS.txt`).
- **The addendum, required before step 2.** Two tests that pin the
  acceptance of the duplicate (`basis` absent; `source` = `"diagnostic"`),
  beside the NULL `request_id` pin; the limits of the index and TRUNCATE
  stated in the delivery note; EN-03 for the suite's dependence on a full
  git history; the README's status table. `0007` is not changed.
  - The two tests pin existing behaviour, so no failure "before the fix" is
    expected. The SQL measurement taken before they were written is kept,
    and they are shown to pass on the same text.
  - The suite's run is bound again to the new tree.
- **OQ6-1 and OQ6-2 are open questions, not approved changes** (§5.3).
- **Step 2 is authorized** once the addendum is delivered, without waiting
  for OQ6-1 or OQ6-2. **Its acceptance requires** the proof that the
  completion command locks the cited observation FOR SHARE (G6-8 (iv)).
- **M-3, stated precisely.** The UPDATE OR DELETE triggers of parts A and D
  do not fire on TRUNCATE. That does not mean every TRUNCATE succeeds: the
  foreign keys and the privileges still apply. A TRUNCATE trigger is itself
  statement-level.
- **Evidence status.** The reviewer does not attribute to themselves the
  2426/2426 and 102/102 we re-ran in a fresh container: they are additional
  evidence, described with their environment. Nor can the package's digest
  be confirmed by that re-run: `reports/` was not in our copy.
- **Carried, unchanged:** K06 UNPROVEN; G4-5R open; SALE only.

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

**The review of `bd54216`. APPROVED: «اعتمد» ("I approve").**
- **What was answered.** After revision 3, the reply to a bare "continue"
  stated that it was not an approval. It set out a table of the open
  decisions with the plan's recommendation for each, and said that an
  answer of «أعتمد» per item would suffice. The reviewer answered «اعتمد»
  once, for the table.
- **How this plan reads it, stated so it can be corrected.** Every
  recommendation of that table is approved, as follows. No alternative
  option was chosen.

  | Decision | Approved |
  |---|---|
  | G6-1 | the scope as proposed |
  | G6-2 | (a): high-value is the unknown that ALONE stands between the candidate and ELIGIBLE; HIGH for it, NORMAL otherwise |
  | G6-3 | `diagnostic.actions@1` as specified; computed once, before any task insert |
  | G6-4 | (a): the run raises tasks for its HIGH suggestions only; (iii) the subject key and the partial unique index over OPEN and IN_PROGRESS, diagnostic tasks only; (iv) (a) NMI tasks independent; (v) the F6-12 staff-view test; the trace is the task rows |
  | G6-5 | (i) (a), (ii) (a), (iii) the table, (iv) the budget from the asking price, (v), (vi) |
  | G6-6 | as revision 2: every requested location, the total order, the chains stored |
  | G6-7 | `blocker_summary` format 2 |
  | G6-8 | (i); (ii) (a), the four codes, required, through CORRECTION-005; (iii); (iv) (a), parts A and D with the completion's FOR SHARE lock; (v)–(vii) |
  | G6-9 | as proposed |
  | G6-10 | (a): no automatic change |
  | G6-11 | as revision 3: `evaluated` stored; checks (R) and (D) kept apart |
  | G6-12 | decided independently of this plan; this plan schedules nothing for K06 |
  | `0007` | parts A, B, C and D of §5.1, as written |
  | CORRECTION-005 | §5.2, with the loader's extension |

  - If that reading is wrong for any item, the reviewer says so. The step
    that depends on the item has not been written yet.
- **Carried, unchanged:** K06 is UNPROVEN; G4-5R is open; SALE only.
- **Authorized:** step 1, migration `0007`, exactly as §5.1 writes it, with
  its tests and mutation record (§8). The later steps follow one at a time.

**The review of `1fd7bdf`.** The reviewer checked both files' digests
against the stated values, and re-ran no PostgreSQL: the measurements are
ours.
- **Accepted:**
  - step 0's results, as the basis for review;
  - two directions: LOCATION IN handled by evaluating every requested
    location and storing their chains (G6-6); each diagnostic linked
    explicitly to the matches it evaluated (G6-11);
  - the measurement supports a partial unique index over OPEN and
    IN_PROGRESS for diagnostic tasks (G6-4 (iii)).
- **Not approved:** the text of `0007`; writing any code. Three reasons:
  1. **The observation guard does not close a concurrent race.** Part D
     checks for a completion event before an observation changes, but the
     event may be inserted by another transaction after the check and
     before the commit. The FK's FOR KEY SHARE lock does not conflict with
     an UPDATE that leaves the key unchanged. So the guard alone cannot keep
     the body that existed at completion. Measure both orders; then specify
     the lock the completion takes on the observation before inserting the
     event, its order with the task lock, and test the wait and the final
     result.
  2. **ALREADY_OPEN makes the suggestions not derivable from their stored
     inputs.** G6-4 marked a suggested action after an index conflict, while
     G6-11 promised to re-derive the suggestions from the matches and the
     location chains. An open task, possibly committed after the
     REPEATABLE READ snapshot, is not among those inputs. Keep the computed
     suggestion fixed; record the task's creation in a separate trace of
     defined source if one is needed; test the replay and the concurrent
     conflict. The report on snapshot visibility agrees with the PostgreSQL
     16 documentation.
  3. **Requiring `outcome_code` needs an explicit contract correction.** The
     frozen `TaskCompletionInput` makes the field optional and accepts null.
     G6-8 (ii) (a) refuses both. That is a reasonable narrowing, but it must
     appear in the effective contract, with the application and the
     contract generator using the same validation, on the precedent of
     CORRECTION-004. The four codes' stated meanings are not objected to,
     provided `TASK_INFORMATION_OBTAINED` is never read as an automatic
     raise of a verification level, nor as proof that the information is
     true.
- **G6-11:** treat `stored: NEW/EXISTING` as a recorded fact of storage. It
  cannot be re-derived from the match row alone after the run. The
  reconstruction test must separate verifying this recorded fact from
  recomputing the decisions from the inputs.
- **F6-12 stays declared.** If tasks are raised by the run, a task may point
  to a diagnostic that the "latest" read does not return, because of the
  `run_at` order. A test must show what staff will see in that case before
  G6-4 is closed.
- **Next:** revision 3 may present the race measurement, the form of the
  contract correction, and the separation of the suggestion from the task's
  trace. G6-1 to G6-12 and the text of `0007` are decided then. K06 stays
  UNPROVEN and G4-5R open.

**Revision 3's measurement** (`SLICE6-PLAN-MEASUREMENTS-R3.txt`, at
`1fd7bdf`, twice, each on a freshly rebuilt scratch database; ours): F6-18.

**Step 0, delivered with revision 2** (`SLICE6-PLAN-MEASUREMENTS.txt`,
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


**Measured for revision 3** (`SLICE6-PLAN-MEASUREMENTS-R3.txt`), and read from
the contract and the code:

**F6-18 · The guard on cited observations needs a lock taken by the
completion (R1–R3).** The completion C and a change U race on one
observation O, under READ COMMITTED.
- **The guard alone (part D):**
  - with U an UPDATE of O's body, in either order, neither transaction
    waits, both commit, and the event cites a body changed after the
    citation (R1a, R1b). The FK check takes FOR KEY SHARE, and a non-key
    UPDATE takes FOR NO KEY UPDATE; they do not conflict (PostgreSQL 16
    documentation, §13.3.2, Table 13.3);
  - with U a DELETE: U waits on C's FK lock, then the guard refuses it
    (R1c); or C's FK check waits on U, then fails 23503 (R1d).
- **The guard plus a FOR SHARE lock taken by C on O, after the task's lock
  and before the event:**
  - C first: U waits, then the guard refuses it (R2a, R2c);
  - U first, an UPDATE: C waits, then reads the changed body and cites it.
    Nothing can change it afterwards (R2b);
  - U first, a DELETE: C waits, its read finds no row, and it refuses,
    writing nothing (R2d).
- **Under REPEATABLE READ,** R2b's order makes the completion fail 40001
  (R3).

**F6-19 · The existing narrowing mechanism cannot express the outcome
correction.**
- `load_request_body_narrowings` (`src/turab/auth/contract.py`) accepts an
  inline body only, and only `require`. The frozen
  `postTasksTaskIdComplete` body is `$ref: TaskCompletionInput`
  (`openapi_v0.2.3.yaml:1551`), a component used by this operation alone
  (one `$ref` in the file).
- Its `outcome_code` is `type: [string, null]`, with no enum. Requiring the
  field alone would still accept null.

**F6-20 · The run's response has no place for a task trace.** The frozen
201 of `postRequestsRequestIdMatchingRun` is `{matches, diagnostic}`. A
field reporting task outcomes would widen the contract.

---

## 5. Decisions (all DECIDED in the review of `bd54216`)

### G6-1 · Scope: which operations and writes are Slice 6's

> **DECIDED (review of `bd54216`): the scope as proposed.**

- **Recommendation:** §0 and §1 as proposed.
  - Route `getTasks` and `postTasksTaskIdComplete`.
  - The run fills `suggested_actions` and `relaxation_scenarios` in the
    diagnostic rows it writes from now on. Rows already written stay `[]`.
  - Tasks from the diagnostic: G6-4.
- **Blocks:** everything.

### G6-2 · What "high-value" means, and the priority of information work

> **DECIDED (review of `bd54216`): option (a).**

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

> **DECIDED (review of `bd54216`): as recommended.**

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

> **DECIDED (review of `bd54216`): option (a), with (iii), (iv) (a) and (v).**

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
        is rolled back and the run continues. **Nothing is written about it**
        (revision 3, review of `1fd7bdf`, point 2).
    - **The suggestions stay what was computed** (revision 3):
      - `suggested_actions` is written once, from the run's evaluations,
        before any task insert. Nothing about tasks enters it.
      - So G6-11's replay re-derives it from its stored inputs alone.
    - **The trace of task creation is the task rows themselves**, a source
      already defined (the run, audited by `audit_rows`):
      - each task the run creates names `diagnostic_run_id` and the
        suggestion's subject key in its `payload`;
      - every HIGH suggestion is attempted, and an attempt has exactly two
        outcomes: the task is created, or the index refuses it (any other
        error fails the whole run, writing nothing).
      - So a HIGH suggestion of diagnostic D with no task naming D in its
        payload is one whose work was already open. That reading is exact
        from stored rows.
      - **Its stated limit:** it holds while no task is deleted. No path
        deletes a task, and a task with a completion event cannot be
        deleted (F6-16, the FK RESTRICT); an OPEN one can be, by a
        superuser (K06).
      - No other trace is proposed. The run's response has no field for one
        (F6-20).
    - **The index covers only the run's tasks**
      (`payload->>'source' = 'DIAGNOSTIC'`). Slice 3's and Slice 5's tasks
      are outside it and unchanged.
    - **Tests (revision 3):**
      - **replay:** the reconstruction re-derives `suggested_actions` from
        the stored inputs, and never reads `tasks`;
      - **re-run:** a second run on unchanged facts writes a second
        diagnostic with an identical `suggested_actions` and no new task;
        the existing task still names the first diagnostic;
      - **concurrent conflict:** two runs on one subject, the second
        inserting while the first holds its uncommitted task. A
        `pg_blocking_pids` witness shows the wait. One task results; it
        names one of the two diagnostics. Both diagnostics replay, and
        their suggestions are equal.
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
  - **(v) What staff see when a task's diagnostic is not "the latest"
    (F6-12), a test before G6-4 is closed (revision 3).**
    - **Built at service level:** two sessions, the real run function, and
      a controlled start order. Run A starts first and raises the task. Run B
      starts later, finds the work open, and commits last.
    - **What the test asserts staff see:**
      - `GET /requests/{id}/diagnostic` returns B's row: the later
        `run_at`, F6-12;
      - `GET /tasks` returns the task, whose `payload.diagnostic_run_id`
        names A's row;
      - no contract operation reads a diagnostic by id, so A's row is not
        reachable from the task through the API;
      - the task is therefore self-contained: its type, priority,
        `reason_code`, `match_id` and `payload.subject` state the work
        without A's row;
      - `GET /matches/{match_id}` returns the match the task names.
    - Also asserted: when B's facts changed and B no longer suggests the
      subject, the task stays OPEN and says so by itself (G6-10 (a)).
  - **(vi) Cost:** it changes Slice 4's approved boundary (G4-15 D1: "no task
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

> **DECIDED (review of `bd54216`): (i) (a), (ii) (a), (iii)–(vi).**

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

> **DECIDED (review of `bd54216`): as written.**

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

> **DECIDED (review of `bd54216`): as recommended.**

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

> **DECIDED (review of `bd54216`): (ii) (a) and (iv) (a), with (i), (iii) and (v)–(vii).**

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

    - `outcome_code` is then REQUIRED, NOT NULL, and one of these four.
      The frozen `TaskCompletionInput` makes it optional and nullable, so
      this is a **contract correction**, CORRECTION-005 (§5.2), applied in
      the effective contract. The application and the generator of the
      effective contract validate it with the same loader, on
      CORRECTION-004's precedent.
      - A body that violates it is refused as any body that violates the
        effective schema: 422, writing nothing.
      - **The loader must first be extended** (F6-19), as §5.2 states.
        That extension is code, written only once this decision is
        approved.
    - **What a code means, and does not:**
      - `TASK_INFORMATION_OBTAINED` says only that the work was done;
      - it raises no verification level, automatically or otherwise, and
        it proves nothing about whether the information is true (review of
        `1fd7bdf`);
      - the fact itself is recorded through its own command (Slice 3's
        truth layer), with its own evidence and level;
      - the code changes no fact (v). A test completes a VERIFY_DOCUMENT
        task with it and asserts that no claim, resolved value, attribute,
        verification level, match or opportunity changed.
  - **(b) Null only.**
    - `outcome_code` must be null or absent; any code is **422**. That
      also narrows the frozen type, so it too is a correction (§5.2's
      mechanism, with `enum: [null]`).
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
  - **Under (a), the completion locks the observation (revision 3,
    F6-18).** Part D alone does not keep the cited body (R1a, R1b). The
    command's order, under READ COMMITTED:
    1. lock the task `FOR UPDATE`, and check that it is OPEN or
       IN_PROGRESS (409 otherwise);
    2. if `evidence_observation_id` is given, lock that observation
       `FOR SHARE`. If no row is found, including one deleted while it
       waited, refuse with **422** `EVIDENCE_OBSERVATION_NOT_FOUND`,
       writing nothing (R2d);
    3. insert the event;
    4. set the task DONE with `completed_at`.

    - **Why FOR SHARE:** it conflicts with the FOR NO KEY UPDATE of a body
      UPDATE and with the FOR UPDATE of a DELETE; FOR KEY SHARE, the FK's
      lock, conflicts with neither UPDATE (Table 13.3).
    - **Why this order:** task, then observation. No other path locks an
      observation and then a task: no application path writes
      observations at all (step 0). So the order cannot invert.
    - **The body cited is the one committed when the lock is granted.**
      After the completion commits, part D refuses any change (R2a, R2c).
      A change committed before the lock is granted is the body cited
      (R2b).
    - **Tests:** R2a–R2d as tests, each with a `pg_blocking_pids` witness
      of the wait and the final rows asserted. A mutation removing the
      FOR SHARE must turn R2a into R1a's result.
  - **Under (b),** no observation lock is taken: without part D, the lock
    would only delay a change it cannot refuse.
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

> **DECIDED (review of `bd54216`): as recommended.**

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

> **DECIDED (review of `bd54216`): option (a).**

- **(a) Recommended. No automatic change.** A later run that no longer
  finds the unknown leaves the task OPEN. The task records that the work was
  asked for, and staff complete it with an outcome. The diagnostic no longer
  suggests it.
- **(b)** The run cancels its own OPEN tasks whose subject is resolved
  (`status = CANCELLED`). There is no contract command for CANCELLED (F6-7),
  and this adds a second write path to task state.
- **Blocks:** step 4.

### G6-11 · Versions and replay (revision 2, on F6-11)

> **DECIDED (review of `bd54216`): as written.**

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
- **Replay, in two separate checks (revision 3, review of `1fd7bdf`).**
  - **(R) The recorded facts are verified, not re-derived.** `evaluated`
    and `stored` are what the run recorded when it stored or found each
    match. They cannot be re-derived after the run: a reused match may have
    been committed by a concurrent run and read on another connection
    (Slice 4, measured D5). The check verifies only their consistency with
    the stored rows:
    - every listed `match_id` exists, and its `input_hash` equals the
      entry's;
    - an entry `NEW` has `evaluated_at` equal to the diagnostic's `run_at`
      (one transaction, one instant).
    - An entry `EXISTING` is checked only for existence and hash. Nothing
      is inferred from its timestamps.
  - **(D) The decisions are recomputed from the inputs:**
    - the match rows `evaluated` names, by id and in that order;
    - the stored location chains.

    From these it re-derives `suggested_actions`, `relaxation_scenarios`
    and the computed parts of the format-2 summary, and compares them. Any
    difference fails. It never infers the evaluated matches from
    `evaluated_at` (F6-11), and never reads `tasks` (G6-4 (iii)).
  - A failure names which check failed, (R) or (D).
- **The test the review asked for:**
  - two runs of one request, with an offer's price changed between them;
  - run 2's `evaluated` names P1's REUSED match (`EXISTING`, run 1's id)
    and P2's NEW one;
  - both diagnostic rows pass (R) and (D);
  - a stored entry altered in the test's copy (a wrong `stored`, a wrong
    hash) fails (R), not (D); a stored suggestion altered fails (D);
  - after a requested location is re-parented, the replay still gives the
    stored scenario.
- **Blocks:** step 3.

### G6-12 · K06 and the application role (not blocking this plan)

> **DECIDED (review of `bd54216`): decided independently of this plan.**

- G5-13 (b)(ii) is a separate, cross-cutting step, mandatory before any
  release gate. It is not a Slice 6 deliverable.
- **The question:** whether it is scheduled before Slice 6's code, in
  parallel, or after. Recommended: decided by the reviewer independently of
  this plan. Nothing here depends on it, and nothing here claims K06.


### 5.1 The text of migration `0007` (APPROVED in the review of `bd54216`; step 1)

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

**D. A cited observation is kept as cited** (G6-8 (iv) (a)). **Not
sufficient alone** (F6-18): it holds only with the completion's FOR SHARE
lock of G6-8 (iv), which is part of the same decision.

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


### 5.2 CORRECTION-005 (APPROVED in the review of `bd54216`; step 2)

**Kind:** a request-body narrowing, through the corrections overlay, on
CORRECTION-004's precedent. Only under G6-8 (ii) (a), or, in the form
`enum: [null]`, (b).

**What it would add to `docs/contract/CONTRACT_CORRECTIONS.yaml`:**

```yaml
  - id: CORRECTION-005
    decision: "G6-8 (ii) (a), Slice 6 plan revision 3 (docs/gate/SLICE_6_PLAN.md)"
    approved: "<the date of approval>"
    operation_id: postTasksTaskIdComplete
    require: [outcome_code]
    non_null: [outcome_code]
    enum:
      outcome_code: [TASK_INFORMATION_OBTAINED, TASK_INFORMATION_UNAVAILABLE,
                     TASK_PARTY_UNREACHABLE, TASK_NO_LONGER_NEEDED]
    frozen_defaults: {}
    rationale: >-
      A completion states its outcome, from the codes of category
      TASK_OUTCOME (migration 0007, part B). The general seeded codes are
      accepted by the FK but describe no task outcome (measured,
      SLICE6-PLAN-MEASUREMENTS.txt §E3).
    runtime_rule: >-
      outcome_code is required, not null, and one of the four codes. A code
      changes no fact and raises no verification level.
    reference: docs/contract/CORRECTION-005-task-outcome-code.md
```

**What the loader must accept first (F6-19); each check is a narrowing
check:**
- **A body given by `$ref`** to a component:
  - accepted only when that component is referenced by this operation
    alone (counted in the frozen file);
  - the generator writes an operation-local, narrowed copy into the
    effective contract;
  - the frozen component stays as it is.
- **`non_null`:** each field's frozen type must include `null`; the
  effective type removes it.
- **`enum`:** each field's frozen schema must have no enum, or a superset
  of the given values; the given values must be of the field's type.
- **Refused, as today:** an unknown key, a field not in the body, a second
  narrowing of the operation, a stale `frozen_defaults`.

**One validation, in three places:**
- the generator and the runtime use the same loader (as CORRECTION-004);
- the route's body model refuses what the effective schema refuses. A test
  runs the same bodies through both:
  - absent;
  - null;
  - an empty string;
  - each of the four codes;
  - a seeded general code;
  - an unknown code;
- a test asserts that the enum equals the ACTIVE codes of category
  TASK_OUTCOME in the database.

**Its note,** `CORRECTION-005-task-outcome-code.md`, follows CORRECTION-004's
form: the frozen text (`openapi_v0.2.3.yaml:4727–4743`), the measured
reason, the effective text, and why it only narrows.

---

### 5.3 Open questions (review of `b6a08e7`; NOT decisions, NOT approved)

**OQ6-1 · A constraint on the diagnostic payload.** A CHECK on `tasks`
that would make part C's key complete for every diagnostic task (M-1).
- **Not decided before** its effect on every writer of `tasks` is
  established: `identity.py`, `match_review.py`, and the run's writer of
  step 4.
- **Meanwhile, step 4 must prove** that the diagnostic writer sets
  `request_id` and the four keys `entity`, `id`, `gate` and `basis` to
  non-NULL values, and `source` to `"DIAGNOSTIC"` exactly.

**OQ6-2 · An index on `task_completion_events.evidence_observation_id`.**
Part D's guard looks events up by this column, on every UPDATE or DELETE of
an observation; no index covers it (measured, P5 of the addendum record).
A foreign key creates no index on its referencing columns.
- **A later performance decision,** preceded by a measurement at a
  representative volume. Nothing is built for it now.

### 5.4 A stated limit: `explain.blocker_summary` (review of `922a100`)

`by_reason`, `candidates_evaluated` and the summary's base come from
`explain.blocker_summary`, Slice 4's format-1 builder. It is **not pinned**,
and the three pins of step 3 (`diagnostic.value@1`, `diagnostic.actions@1`,
`diagnostic.relaxation@1`) **do not cover it**.
- **What protects an old row today:** a change of its output makes the
  replay of an old row fail (D), loudly. That failure is **not** a proof
  that the old row can be replayed.
- **Required before any later change** of this function that affects the
  summary: keep the historical computation (or a version of it), and test
  the replay of an old row and of a new row.
- Recorded with step 4's evidence; restated in the closure evidence (§6.4).

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
- **The inventory of writes to `tasks` (review of `315804b`).** The closure
  evidence lists every statement of `src/` that writes `tasks`, by kind, and
  refuses one that is not decided (condition 10):
  - **INSERT (task creators):** `identity.py`, `match_review.py`, and
    `matching_run.py` from step 4 under G6-4 (a);
  - **UPDATE:** `tasks.py`, the completion, setting `status` and
    `completed_at` only;
  - **DELETE:** none.

  Measured at `315804b`: exactly these three statements, the two INSERTs
  and the one UPDATE, and no DELETE.

### 6.5 Measurements (step 0, delivered)

Delivered in `evidence/SLICE6-PLAN-MEASUREMENTS.txt` (sections L, D, T, E,
S). Its results are F6-10 to F6-17. Revision 3's race is in
`evidence/SLICE6-PLAN-MEASUREMENTS-R3.txt` (F6-18).

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
10. **The writes to `tasks` are exactly those decided** (rewritten in the
    review of `315804b`):
    - **task creators, by INSERT:** `identity.py`, `match_review.py`, and
      `matching_run.py` only if G6-4 (a);
    - **the completion command, by UPDATE:** `tasks.py`, which sets
      `status` and `completed_at` and nothing else;
    - **no DELETE.**

    The closure evidence checks both kinds, as STOP GATE E checked its
    writers (§6.4); `tasks.py` is never left out of it.

---

## 8. Sequence

| Step | Content | Depends on |
|---|---|---|
| 0 | the measurements of §6.5, folded into revision 2; no code | **done** (authorized in the review of `f7469e8`); `SLICE6-PLAN-MEASUREMENTS.txt` |
| 1 | migration `0007`, parts A–D of §5.1, exactly as approved; tests, mutations | G6-4 (iii), G6-8 (ii), G6-8 (iv); **authorized** in the review of `bd54216`; delivered at `cd5b868`; **CLOSED at `b6a08e7`** (review of `b6a08e7`) |
| 1a | addendum: the two pins of M-1, the limits of the index and TRUNCATE stated, EN-03, the README; the suite bound again. `0007` unchanged | review of `b6a08e7`; **required before step 2** |
| 2 | `getTasks` and `postTasksTaskIdComplete`, with the completion's lock order (G6-8 (iv)); CORRECTION-005 and the loader's extension (§5.2). **Accepted only with** the proof that the completion locks the cited observation FOR SHARE | G6-8, G6-9; **authorized** after step 1a (review of `b6a08e7`); delivered (`SLICE_6_STEP2_DELIVERY.md`); **CLOSED at `315804b`** (review of `315804b`) |
| 3 | the pure functions: high-value (G6-2), `suggested_actions` (G6-3), relaxation (G6-5, G6-6), `blocker_summary` format 2 (G6-7), their registry entries and replay (G6-11) — no write yet | G6-2, G6-3, G6-5, G6-6, G6-7, G6-11; **authorized** (review of `315804b`); not closed in the review of `220573a`; **CLOSED at `922a100`** (review of `922a100`) |
| 4 | the run writes them; tasks from the diagnostic only if G6-4 (a); G6-10. **Its tests measure** the supersession of an older match by the new one, in the match queue and at approval (review of `220573a`), and **replay a real format-2 row the run wrote** (review of `922a100`); its evidence restates the limit of §5.4. **Its tests prove** that each diagnostic task has `request_id` and the four keys `entity`, `id`, `gate`, `basis` non-NULL, and `source` = `"DIAGNOSTIC"` exactly (OQ6-1) | G6-4, G6-10; **authorized** (review of `922a100`) |
| 5 | the mandatory and red-team tests end to end, mutations, the closure evidence (§6.4) | all |

Each step is delivered with its tests and mutation record, and reviewed
before the next begins. A defect found in a step is measured before it is
fixed.

---

## 9. Document identity

This file's sha256 is recorded in `docs/gate/evidence/DOCUMENT-HASHES.txt`
at the commit that adds it.
