# Slice 6 · step 3 — the diagnostic's pure functions, registered, and replay

**Approved scope.** The review of `315804b` authorized step 3 "as the plan
describes it" (§8): the pure functions of G6-2, G6-3, G6-5, G6-6 and G6-7,
their registry entries and replay (G6-11), **with no write yet**.

- **What this step does not contain.** The run is unchanged
  (`services/matching_run.py` and the HTTP layer have no diff since
  `a1d52d9`). It still writes `blocker_summary` format 1 and empty
  `suggested_actions` and `relaxation_scenarios` (tested). No file of `src/`
  calls the new functions; only the tests do. Writing them, the
  `turab.diagnostic-input/2` document and the tasks of G6-4 are step 4's.
- **The one effect this step has on the run, measured** (§5): registering
  three functions changes the registry digest, which enters every match's
  input hash (G4-13).

**Status:** **CLOSED at `922a100`** (review of `922a100`), after the three replay gaps of the review of `220573a` were closed (§8). The limit on `explain.blocker_summary` is plan §5.4.

**Basis:** `docs/gate/SLICE_6_PLAN.md` revision 8: G6-2 (a), G6-3, G6-5 (i)
(a), (ii) (a), (iii)–(vi), G6-6, G6-7, G6-11; §3.2–§3.5; F6-1, F6-2, F6-6,
F6-8, F6-10, F6-11; step 0's measurements L1–L4 and D.

**Commits:** `a1d52d9` (plan revision 8, the review of `315804b`); `55dbee6`
(the code and its tests); `8dbfa8c` (`HISTORY` names `55dbee6`); `4d0e125`
(the pin test in its own file; the mutation script); `83dd19a` (the first
mutation run kept; three tests added; four equivalent mutations removed);
`0943e64`, `ef9c9ae` (two tests made deterministic); then the evidence
commits `6726018`, `be089e7`, `798919b`, `90ad2ab`.

---

## 1. What step 3 contains

| Part | Where | Decision |
|---|---|---|
| `diagnostic.value@1` | `matching/diagnostic_rules.py` | G6-2 (a): HIGH only for the unknown that ALONE stands between the candidate and ELIGIBLE |
| `diagnostic.actions@1` | same | G6-3: every actionable unknown, freshness and permission reason of the NMI and NEEDS_CONFIRMATION candidates, one entry per subject, the fixed order |
| `diagnostic.relaxation@1` | same | G6-5, G6-6: D2's near matches only, the table of (iii), the location choice |
| the record, the chains, `would_reach`, the format-2 summary, `compute` | `matching/diagnostic.py` | G6-5 (v), G6-6 (stored chains), G6-7, the one entry point step 4 will call |
| replay (R) and (D) | `services/diagnostic_replay.py` | G6-11 |
| registry | `registry.py` (import), `rule_pins.py` (3 pins), `registry_history.py` (the 23-pair entry, since `55dbee6`) | G6-11, G4-2, G4-19 |

**Properties stated, each tested:**
- **The functions read the STORED match.** `candidate_record` builds a
  candidate's input from `matching_run.match_view` alone (the gates, the
  criterion rows, the recorded reasons, the property's location chain).
  The run of step 4 and the replay therefore give the functions the same
  input. **A record carries no commercial snapshot:** the seller
  expectation is absent from the input, not merely unused (§3.4). The
  budget magnitude is `asking_price_dzd − max`, from the stored criterion
  row.
- **Self-contained and pinned** (G4-2): the three functions read no
  module-level name; they do not call one another; the wiring passes one's
  output to the next. The pins and `HISTORY` are tested in their own file
  (`test_slice6_step3_registry.py`).
- **`would_reach`** (G6-5 (v)) is `eligibility.precedence` at the version
  the MATCH recorded, run on its stored gates with the one failure removed.
  It is not re-implemented.
- **Replay reads no `tasks`:** every statement the replay executes is
  captured, with an open task on the match in the world; none names
  `turab.tasks`.
- **`compute` and replay write nothing:** the row counts of the match,
  diagnostic, task, location and audit tables are unchanged.

## 2. Mandatory tests and step 0's cases, on real runs

The inputs of the mandatory tests are built here; their END-TO-END proof
(the run writing, the tasks) is step 5's (§8).

| Case | Observed |
|---|---|
| Mandatory 1 (M-12, I01): P08 document UNKNOWN, P03 LOCATION FAIL | the first action is P08's VERIFY_DOCUMENT, HIGH; P03's location scenario is `subordinate_to` it |
| Mandatory 2: a property failing LOCATION, BUDGET_MAX and PROPERTY_TYPE, document UNKNOWN | no action, no scenario; its unknown counted blocking, not actionable |
| Mandatory 3 (F6-1): a property at max + 1,500,000, not negotiable | `budget_delta_dzd = 1500000`, `stated_at = ASKING_PRICE`, would reach ELIGIBLE |
| D02 / R9.3: an expectation between the maximum and the asking price | magnitude `ask − max` (2,000,000); neither the expectation nor `exp − max` appears; the output is the same for two expectations |
| L1–L4 and EQ as IN of one | the chosen location, `widen_to`, its level and the widening equal step 0's measurement; every requested location is listed |
| G6-11's replay test | run 2 reuses P1's match (EXISTING, run 1's id) and stores P2's (NEW); both documents pass (R) and (D); an altered `stored` alone, or a hash alone, fails (R) only; an altered suggestion, or scenario, fails (D) only; after a requested location is re-parented, the replay gives the stored scenario |

## 3. Readings the plan did not fix, stated for review

1. **The subject key** of an entry is G6-3's
   `(type, entity, id, criterion, ordinal)` **plus the gate and the basis**,
   G6-4 (iii)'s key, so that an entry and the task step 4 raises from it
   name the same work. Within one run the gate is determined by the type
   and the criterion (mutation A10 is equivalent: §4).
2. **A shared entry is HIGH** when it is the high-value unknown of at least
   one of its candidates.
3. **`would_reach` may be NEED_MORE_INFORMATION** (a blocking PREFERRED or
   FLEXIBLE unknown stays). G6-5 (v) names ELIGIBLE and NEEDS_CONFIRMATION;
   the precedence gives the third case, and it is stated as such.
4. **Aggregation (G6-5 (v)):**
   - a numeric scenario turns every near match whose own change is no
     larger (cumulative);
   - a widening turns every near match under the location, whichever
     location it chose;
   - order: numeric by magnitude, smallest first; widenings by the levels
     the REQUEST is widened, fewest first; named ones by count, descending,
     then the name.
5. **NOT_PROPOSED** entries: TRANSACTION_INTENT (never, C01), and a count
   FAIL whose attribute cannot apply to the type (`count_min@2`'s
   ATTRIBUTE_NOT_APPLICABLE: no lowering passes it). The plan's row
   "attribute options" matches no code today: DOCUMENT_TYPE and RIGHT_TYPE
   are the only option codes, and their own row applies.
6. **`subordinate_to`** lists every HIGH action of the run on every
   scenario.
7. **Replay runs (D) only when (R) passes**, so a failure names one check.
8. **The chain reader is in `matching/`** (it reads `locations`, as
   `snapshots.py` reads the database); **replay is in `services/`**, which
   may import the run's `match_view`.
9. **`turab.diagnostic-input/2`** (G6-11) is the run's input hash; it is
   left to step 4, with the write.

## 4. Defects found during the step, measured before the fix

**In the code, caught by the step's own tests before any commit:**
- **The order of widenings.** It was first written by `property_below`,
  which is relative to each property: two scenarios tied, and the id
  decided. The scenario's magnitude is the widening of the REQUEST
  (`levels_widened`). Corrected.
- **(R)'s instant check.** It compared a `datetime` serialized in Python
  with the JSON text of `run_at`; the two forms differ, and every NEW entry
  failed. The comparison is now made in SQL, between two `timestamptz`.

**In a delivered Slice 4 test** (`evidence/SLICE6-STEP3-S4-REPLAY-BEFORE-FIX.txt`).
- **What failed.** `test_an_old_match_without_the_digest_and_a_new_one_replay_after_a_version_is_added`
  failed once the three functions were registered.
- **Why.** The test stood a match written NOW in for a format-1 row
  (`7a223d7`'s code). That held only while the current registry WAS
  `HISTORY[0]`; this is the first real registration of a new version
  (G4-2's case).
- **The fix.** The old match is now written under `HISTORY[0]`'s registry,
  built from its 20 recorded pairs and checked against its digest. Every
  assertion is unchanged.

**In the mutation evidence: five runs, all kept.**

| Run | Commit | Survivors | What was done |
|---|---|---|---|
| first (`…-FIRST-RUN.txt`) | `4d0e125` | 7 | A9, L6, R2: a test was missing; added. V4, A10, L4, L10: EQUIVALENT, argued in the script, removed |
| second (`…-SECOND-RUN.txt`) | `83dd19a` | A8 | killed in the first run **by chance**: the order test's ids were random. Fixed ids now contradict the class order |
| third (`…-THIRD-RUN.txt`) | `0943e64` | L12 | the pair of runs at `0943e64` differed: L12 killed in one, survived in the other. The seeded locations' ids are generated at each build. A test with fixed ids against the widening order was added |
| final, twice (`…-MUTATIONS.txt`, `…-REPEAT.txt`) | `ef9c9ae` | none | 34/34 in each run, identical counts |

**The four equivalent mutations:**
- **V4, dropping NEED_MORE_INFORMATION.** The remaining conditions give it
  under `eligibility.precedence@1`.
- **A10, dropping the gate from the key.** It is determined by the type
  and the criterion.
- **L4, reversing an inner sort.** The final sort overrides it.
- **L10, `property_value is not None` for the COUNT_MINIMUM basis.** In
  `count_min@2`'s FAIL results they are the same condition.

**Since a kill can be luck,** the final record is two runs on one tree,
compared line by line.

## 5. What the registration changes for the run, measured

`evidence/SLICE6-STEP3-REGISTRY-DIGEST.txt`: one request, run with
`a1d52d9`'s code, then twice with step 3's, on UNCHANGED facts, in a
separate probe database.

| Run | Registry digest | Match | Reused |
|---|---|---|---|
| base `a1d52d9` | `7ddf4747…` | `30d122de…` | no (first) |
| step 3 | `47188d01…` | `146dc8a8…`, a NEW match | **no** |
| step 3, again | `47188d01…` | `146dc8a8…` | yes |

- **Why.** G4-13 puts the registry digest in every match's input hash,
  and G6-11 registers the three functions in that registry. So the first
  run after step 3 stores a new match even on unchanged facts; it is reused
  from then on. The old match is unchanged and verifiable through
  `HISTORY[0]`.
- **Derived, not measured here.** The new match is a later match of the
  same request, property, policy and offer, so it supersedes the old one
  for an approval and in the match queue (G5-2).
- **This is G4-2's designed behaviour** for any registered version. Step 3
  is the first time it happens; G6-11 decided the registration. **It is
  stated here so the reviewer can weigh it before step 4,** which adds no
  further version.

## 6. The evidence round

Each row was run on a clean tree, source fingerprint `76bf18ad…f7c1` (from
`ef9c9ae`; the later commits are evidence only). PostgreSQL 16.15.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations, twice | 34/34 and 34/34, identical counts; none survives | `6726018` (runs at `ef9c9ae`) | `evidence/SLICE6-STEP3-MUTATIONS.txt`, `…-REPEAT.txt` |
| Authorization matrix | 189 rules (step 3 adds none: no operation); suite 2556/2556 | `be089e7` (run at `6726018`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS; 70 PASS notices; 67 operations equal | `798919b` (run at `be089e7`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | 2556 passed, 0 failed, 0 errors, 0 skipped; `bound` | `90ad2ab` (run at `798919b`) | `evidence/TEST-RUN-PROVENANCE.txt` |

- **The suite count:** 2511 → 2556. That is the step's 42 cases, the
  registry test, and 2 cases of `test_mutation_tools.py` for the new
  script.
- **Before** (`evidence/SLICE6-STEP3-BEFORE.txt`): at `a1d52d9` the main
  file fails at collection (`cannot import name 'diagnostic'`).
- **STOP GATE E:** `--check` exits 1 with the one problem of step 1: the
  document is stale.

**Limits that are part of these results:**
- **No format-2 row exists yet.** The tests replay documents that
  `compute` builds from real stored matches. Replaying rows the run itself
  wrote is step 4's proof.
- **Only the inputs of the mandatory tests are proven here.** Their
  end-to-end proof, with the run writing and the tasks raised, is step 5's.
- **These results are ours.** No one else has run them. K06 UNPROVEN.

## 7. What remains

- **Step 3 closes on review** of §8. §3's readings and §5's consequence were
  accepted in the review of `220573a`; §8.4's observation is put to the
  reviewer.
- **Step 4:**
  - the run writes `compute`'s output and `turab.diagnostic-input/2`;
  - it raises the HIGH entries as tasks (G6-4 (a), with the index of
    `0007`), proving the writer's complete payload (OQ6-1's obligation);
  - the measured supersession of an older match by the new one, in the
    match queue and at approval (review of `220573a`);
  - G6-10.
- **Standing:**
  - OQ6-1 and OQ6-2 are open;
  - G4-5R is open, SALE only;
  - K06 is UNPROVEN.

---

## 8. The review of `220573a`: three gaps of the replay, closed

The review did not close step 3. It found three gaps in the replay G6-11
requires, by reading the code and tests (not by a PostgreSQL run), and asked
for each to be pinned by a test on `220573a`'s code before the fix.

### 8.1 Pinned before the fix (`evidence/SLICE6-STEP3-REPLAY-GAPS-BEFORE-FIX.txt`)

Five cases were added to `tests/test_slice6_step3.py` and run on `220573a`'s
unchanged code. They were committed in that state at `e9d3a03`. All five
failed, each for the reason the review gave:

| Case | At `220573a` |
|---|---|
| (R) an entry's `property_id` changed alone | `{'R': [], 'D': []}`: passes unseen |
| (R) an entry's `offer_id` changed alone | `{'R': [], 'D': []}`: passes unseen |
| (R) an entry naming another request's match, with that match's own hash, property and offer | (R) fails only on the NEW instant (another run); the request is not compared, so an EXISTING entry would pass |
| (D) one `excluded_counts` value changed alone | `{'R': [], 'D': []}`: passes unseen |
| an old row (`diagnostic.actions@1`) after a later `@2`, which suggests nothing, becomes the version new computations use | (D) fails: recomputed with `@2`, not with the `@1` it records |

### 8.2 The fix (`144ba96`)

- **(R)** compares, for every entry, the match's `property_id` and
  `evaluated_offer_id` with the entry's, and the match's `request_id`
  with the diagnostic's.
- **(D)** compares `excluded_counts` with what the stored exclusions
  give.
- **`compute` takes the versions it runs.** By default these are the
  current ones, and the summary records whichever were run. The replay
  passes the versions the row RECORDS. A row whose versions are missing,
  or name a version no code implements, is a (D) problem, not an
  exception (a sixth test).
- **After the fix:** the six cases pass, and the step's 42 earlier cases
  are unchanged. In the version test, the old row replays by `@1`, and a
  new row records `@2` and replays by `@2`.

### 8.3 What the review accepted, and what moves to step 4

- **Accepted:** the nine readings of §3, as the implementation's stated
  interpretations, including NEED_MORE_INFORMATION as a possible
  `would_reach`, NOT_PROPOSED as a diagnosis rather than a proposed change,
  and `turab.diagnostic-input/2` left to step 4.
- **Accepted:** the registry digest's effect (§5), as G4-13's consequence.
- **To step 4:** the test of the ACTUAL supersession of an older match,
  in the match queue and at approval. This note presents it as derived,
  not measured.

### 8.4 One observation, not fixed

- **The source.** `by_reason`, `candidates_evaluated` and the format
  field come from `explain.blocker_summary`, Slice 4's format-1 builder,
  which is not pinned.
- **The consequence.** A later change to it would make an old row fail
  (D), loudly. It would not pass silently.
- **Not changed here.** That is the safe direction, and pinning it is
  outside what the review asked. It is put to the reviewer.

### 8.5 The evidence round, again

Each row was run on a clean tree, source fingerprint `2b497bba…48ee` (from
`144ba96`; the later commits are evidence only). PostgreSQL 16.15, in a
container that had restarted (EN-01).

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations, twice | 39/39 and 39/39, identical counts; none survives. R6–R10 are new: the request, the property, the offer, `excluded_counts`, the recorded versions | `8f044e5` (runs at `144ba96`) | `evidence/SLICE6-STEP3-MUTATIONS.txt`, `…-REPEAT.txt`. These replace the records at `ef9c9ae`, which stay in git history |
| Authorization matrix | 189 rules; suite 2562/2562 | `2d82025` (run at `8f044e5`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS; 70 PASS notices; 67 operations equal | `ebce6ee` (run at `2d82025`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | 2562 passed, 0 failed, 0 errors, 0 skipped; `bound` | `2a546f1` (run at `ebce6ee`) | `evidence/TEST-RUN-PROVENANCE.txt` |

- **The suite count:** 2556 → 2562, the six cases of §8.
- **`e9d3a03`'s suite fails five cases.** That commit holds the tests on
  the unfixed code, as the review asked. No run of it is reported as a
  result.
- **During the runs,** the stop hook reported an uncommitted change. It
  was the runner's temporary mutation of `diagnostic_replay.py`, with its
  `.orig` backup. It was NOT committed; the runner restored the file and
  checked its digest.
- **STOP GATE E:** `--check` exits 1, with the one known problem: the
  document is stale.
- **These results are ours.** The reviewer did not re-run them.
