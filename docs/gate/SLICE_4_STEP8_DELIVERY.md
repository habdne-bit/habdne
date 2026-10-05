# Slice 4 · step 8 — the staff reads, the mandatory tests, STOP GATE D

**Status: delivered for review. Not closed.**
- Slice 4 closes only on the review of this step.
- G4-5R is open, and the RENT refusal is in force.
- **G4-19 is raised (§6), open.**

**Authorised:** the review of dcf834a closed step 7 at `dcf834a`, and
allowed step 8 "under the approved plan". The plan, revision 18, names step
8's content, §8:
- GET match and GET diagnostic;
- the ten mandatory tests;
- STOP GATE D;
- the matrix.

**Basis:**
- `docs/gate/SLICE_4_PLAN.md` §1, §3.5, §6.1, §6.2, §6.3, §7;
- `IMPLEMENTATION_SLICES_v0.2.md`, Slice 4: the ten mandatory tests, STOP
  GATE D;
- Developer Spec §24 (M-01 … M-06);
- red-team B04, C01, C03, C04, D02, E02, G01 … G06;
- RFC-001 R6.2, R6.3, R9.2;
- the contract's `getMatchesMatchId`, `getRequestsRequestIdDiagnostic`,
  `MatchCandidate`, `Diagnostic`.

**These are our runs.** Nobody else has re-run them.

---

## 1. What was built

| File | What it holds |
|---|---|
| `src/turab/api/routes/matching.py` | `GET /matches/{match_id}` and `GET /requests/{request_id}/diagnostic`, beside the run |
| `src/turab/services/access.py` | `read_match`, `read_latest_diagnostic`: staff reads, recorded |
| `src/turab/matching/reconstruct.py` (new, pure) | STOP GATE D: `reconstruct` and `replay`, from stored rows only |
| `db/gate/stop_gate_d_evidence.py` (new) | the STOP GATE D document, generated from the bound run |
| `db/gate/authorization_evidence.py` | two matrix rules: matching is staff-only; its reads are recorded |
| `tests/test_slice4_step8.py` (new) | the reads, the mandatory tests, the scenarios, the two proofs |
| `tests/test_slice4_stop_gate_d.py` (new) | the generator refuses what is not proven or not bound |
| `db/dev/mutate_slice4_step8.py` (new) | 17 mutations |

No migration, table, column, reason code or contract change. Nothing is
written by the reads.

---

## 2. The two staff reads

**`GET /matches/{match_id}`** (ADMIN, OPERATOR, REVIEWER):
- **The body.** The contract's `MatchCandidate`, read from the stored rows
  (`match_view`). Numbers are returned exactly (`ExactJSONResponse`), as
  step 7's review asked of the run.
- **Proven equal.** The raw body, read with `Decimal`, is the stored jsonb
  text read with `Decimal`, and it is the run's own response
  (`test_a_match_is_read_exactly_as_stored`, with step 7's numeric case).
- **Recorded** (R6.3). Each read is an access record of kind
  `MATCH_CANDIDATE`, with the operation and the actor.
- **An unknown id is refused 403 `OBJECT_NOT_AUTHORIZED`**, and recorded.
  That is the staff-read convention of every other staff loader
  (`test_on_the_staff_path_an_unknown_property_is_403`, Slice 3): one
  answer for "not there".
- **A customer is refused by the role gate (403).** No customer path to a
  match exists (R9.2).

**`GET /requests/{request_id}/diagnostic`** (ADMIN, OPERATOR, REVIEWER):
- **Which run.** The latest run: the greatest `run_at`, with equal instants
  ordered by `diagnostic_run_id`, descending, so the answer is
  deterministic.
- **The body.** The stored row as the contract's `Diagnostic`. G4-15 holds:
  the counts and the blocker summary, and `suggested_actions` and
  `relaxation_scenarios` empty.
- **The request is read first through its staff loader:**
  - an unknown request is refused 403, as `GET /requests/{id}` refuses it;
  - a request that was never run is **404 `NOT_FOUND`**. The request is
    visible to the caller, and no diagnostic exists to conceal.
- **Recorded:** the request read (kind `REQUEST`) and the diagnostic read
  (kind `MATCH_DIAGNOSTIC_RUN`).

**R9.2, acceptance condition 9.**
`test_no_customer_or_public_operation_returns_a_match_or_a_diagnostic`
reads the effective contract:
- no operation a CUSTOMER may call, and none without security, has a
  response schema that is, or contains, `MatchCandidate`, `CriterionResult`
  or `Diagnostic`;
- the three Slice 4 operations are exactly ADMIN, OPERATOR, REVIEWER.

---

## 3. The ten mandatory tests (plan §6.1)

The HTTP half of each test uses its planned name, in `test_slice4_step8.py`:
- **Same-named engine halves stay.** Some planned names already named an
  engine-level test in steps 3 to 7, for example step 6's
  `test_a_hard_fail_is_rejected_whatever_the_soft_score`. Those stay.
- **STOP GATE D maps by `module::name`,** so the two can never be confused
  (`test_the_same_name_in_another_module_does_not_count`).

| # | Test(s) | Note |
|---|---|---|
| 1 | `test_a_buy_request_never_evaluates_a_rent_offer` (HTTP); step 3's `test_the_schema_refuses_a_buy_match_on_a_rent_offer` | |
| 2 | `test_a_hard_fail_is_rejected_whatever_the_soft_score` (HTTP); `test_the_schema_refuses_to_approve_a_rejected_match` on a match the RUN wrote, rolled back | **narrowed**: the API review is Slice 5 |
| 3 | `test_a_required_unknown_is_need_more_information_never_pass_or_fail` | |
| 4 | `test_negotiable_above_max_is_unknown_not_pass` | |
| 5 | `test_seller_expectation_can_pass_price_and_is_never_exposed`; the contract test above | |
| 6 | `test_a_potential_property_without_willingness_context_is_not_evaluated` | **narrowed** (G4-9 (a)): the refusing half |
| 7 | `test_an_old_match_replays_from_its_snapshots_after_everything_changed` | see below |
| 8 | `test_match_rows_and_their_criterion_results_cannot_change`: UPDATE and DELETE refused on the run's own rows, in all three tables | |
| 9 | `test_an_alias_is_never_a_candidate` (HTTP); `test_the_schema_refuses_a_match_on_an_alias`: the run's own row re-inserted against an alias, refused, rolled back | |
| 10 | step 7's `test_no_candidate_is_a_valid_run` | |

**Test 7 (G04, C04).** After the run, four things change:
- the request's criteria, and its version;
- the property's document;
- the offer's price;
- the consent, now revoked.

Then:
- `GET` of the old match returns byte-identical text;
- its decisions are reconstructed from its rows alone;
- its criterion results and input hash replay;
- a new run is a new match beside the old one, with a later request
  version, REJECTED, with the permission gate FAIL.

---

## 4. STOP GATE D (plan §6.2)

**Reconstruction** (`reconstruct.reconstruct`) reads the match row and its
criterion rows, nothing else. From them it re-derives every decision the run
recorded, and compares each with what was stored:
- each criterion's `blocking`, from the stored request snapshot's
  `blocking_if_unknown`;
- the hard gate and the information gate;
- the freshness gate, the permission gate and the precedence, each by the
  version `explanation.engine` names;
- every reason;
- the soft score, from the rows, the stored request's targets and the
  stored commercial snapshot;
- the next action;
- the three freshness states.

**Replay** (`reconstruct.replay`) re-runs each criterion's rule, by the
version its row names, on the stored snapshots. It compares the result
field by field with the row, and with the rule's explanation stored in the
match. It then recomputes the input hash from the five stored snapshots.

**Over every match the run has written in the test database.** That covers
step 7's runs and this file's scenario suite, which reaches all four
eligibilities, a column target with a row target, a blocking soft unknown,
a negotiation unknown, an expectation PASS and a stale property.
- **Excluded:** rows inserted BY HAND as fixtures by Slice 3's identity
  tests. They are not engine output, and they carry no explanation in the
  run's format.
- **Counts:** both counts are recorded in the JUnit report (xunit1
  properties), and the document shows them.
- **In the bound run of this delivery** (`junit-run.xml` at `4446375`):
  - reconstruction checked **82** engine matches, 8 of them written by the
    test itself;
  - replay checked **90**, since it runs after reconstruction and writes 8
    more;
  - **9** hand-made fixture rows were excluded from each.

**Neither proof is vacuous.** Each tamper test alters a copy of the rows,
since the stored rows cannot change, and each alteration must be reported:
- **reconstruction:** a stored decision (eligibility, each gate, the soft
  score, the next action, the reasons), or a blocking flag;
- **replay:** the property snapshot, the commercial snapshot, a criterion
  result, a snapshot no rule reads (only the hash can tell), or a rule's
  explanation.

**Without an LLM.** Both are pure functions over stored rows and the pinned,
registered functions. Nothing calls a model; `ai_trace_ref` is null on
every row (step 7).

**The generator** (`db/gate/stop_gate_d_evidence.py`) mirrors STOP GATE C's.
- **Binding:** the JUnit digest and counts, the source fingerprint, and the
  gate run's fingerprint (`run_binding`).
- **Content:**
  - every mapped test, by `module::name`;
  - the recorded counts;
  - the three Slice 4 operations, read from the plan's §1;
  - the writers of the match tables, `match_reviews` and `opportunities`,
    computed from `src`;
  - the migrations;
  - the condition tests.
- **Proven able to fail** (`test_slice4_stop_gate_d.py`). Each of these is a
  problem:
  - a mapped test that is missing or failed;
  - a planned name passing only in another module;
  - a proof without its count;
  - a source change after the run;
  - a new writer of `match_reviews`;
  - a hand-edited document.

---

## 5. Reference scenarios

The scenarios run over HTTP: M-01 … M-06, G01 … G06, C01, C03, C04, D02,
B04 and E02. The STOP GATE D document maps each to its tests.

Two of them call for a statement:
- **M-02** ("+ blocking task") gives a HIGH `VERIFY_DOCUMENT` **next
  action**, with no task (G4-15 D1).
- **B04** is proven in its matching half here. Its public half is Slice 3's
  `test_only_active_consented_offers_are_projected`.

---

## 6. Raised for decision: G4-19

**The registry digest at evaluation time is not stored.**
- **The facts:**
  - G4-13 put `REGISTRY.digest()` into every input hash;
  - the digest covers every registered pair;
  - G4-2 adds each changed rule as a new version.
- **The consequence:**
  - once any version is registered after a match was written, that match's
    `input_hash` can no longer be recomputed from the database alone;
  - its criterion results and decisions still replay and reconstruct.
- **Today:** no version has been added since step 7, so the replay proof
  holds for every match in the run. STOP GATE D states the limit.

**Options**, detailed in the plan, G4-19:
- **(a)** Record the digest in each new match's `explanation.engine`. This
  is additive, and keeps G4-13. **Recommended.**
- **(b)** Narrow the hash to the pairs the match ran. That is a new input
  format, and changes G4-13.
- **(c)** Accept the limit, as stated. This is what is delivered.

(a) changes what step 7 stores, so it needs the reviewer's decision.
Nothing is changed until then.

---

## 7. Mutation evidence

`db/dev/mutate_slice4_step8.py`: **17 mutations**:
- **X1–X7**, reconstruction: a derivation or a comparison lost;
- **Y1–Y4**, replay: a comparison lost, or the wrong snapshot;
- **G1–G6**, the reads: not recorded, the earliest run read as the latest,
  a never-run request not 404, a match through floats.

Three tamper cases were added before ANY step-8 mutation was run:
- the reasons;
- a snapshot no rule reads;
- a rule's explanation.

The reason was read from the code, not measured: without them, no test
would tell X3, Y2 and Y3 apart from correct code. No trial run preceded the
clean-tree run.

**Clean-tree result: 17 of 17 fail, and none survives.**
- Recorded at `af6ae0e`, source fingerprint `b72de094…6cba1`, baseline 48
  passed (`evidence/SLICE4-STEP8-MUTATIONS.txt`).
- Every mutated file was restored and verified by sha256.

---

## 8. What remains

- **The review of step 8.** Slice 4 closes on it.
- **G4-19** (§6).
- **G4-5R:** the period is open, and the RENT refusal is in force.
- **The generated document:** `docs/gate/SLICE_4_STOP_GATE_D.md` was
  generated from the bound run (`4446375`, 1945/1945), and
  `stop_gate_d_evidence.py --check` exits 0 (plan §7, condition 3).
