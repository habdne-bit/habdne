# Slice 5 · step 1 — migration `0006` (G5-12)

**Approved scope.** The review of `6ba73ce` approved G5-12 as written in
plan revision 4, and authorized step 1: "migration `0006` alone".

- **What this step does not contain.** No review, opportunity, task or
  share code was written. G5-3, G5-5 and G5-10 stay open.
- **What the approval is not.** It approved a text. It is not a prior proof
  that the implementation is correct. Running the edge tests and the
  mutations on the actual migration is required before step 1 closes, and
  §3 and §4 report those runs.

**Status:** delivered for review; not closed.

**Basis:**
- `docs/gate/SLICE_5_PLAN.md`, revision 4, G5-12: the five edges, rules 1–6,
  the birth rule, the B-case table, the event-stamp cases and the
  mutations;
- step 0's measurements (`evidence/SLICE5-PLAN-MEASUREMENTS.txt` §B).

**Commits:** `e0892ce` (the migration and its tests) and `4011558` (rule 2
tested apart from the frozen gate; no-op mutations refused). The evidence
commits follow them.

---

## 1. What `0006` contains

`db/migrations/versions/0006_opportunity_history.py`, sha256 `bc29a03a…`.

| Object | Rules |
|---|---|
| `enforce_opportunity_history()` + `trg_opportunity_history`, BEFORE UPDATE | 1 a CLOSED row is final · 2 the ten creation fields are written once · 3 only the five edges · 4 `closed_at` and `close_reason_code` exactly when CLOSED · 5 `shared_at` fixed once set, set only on NEW → SHARED, otherwise null · 6 `engaged_at`, the same, on SHARED → ENGAGED |
| `enforce_opportunity_birth()` + `trg_opportunity_birth`, BEFORE INSERT | NEW, VALID, no shared, engaged or closing time, no close reason |

**Other properties:**
- **Writable columns.** These stay writable:
  - `validity_status`, `last_confirmed_at`, `last_activity_at`;
  - `current_permission_binding_id`;
  - `current_offer_id` (**B10, a service guard, not `0006`**);
  - the status fields, along the graph.
- **Error texts.** Each refusal is P0001 with a fixed text that names no id
  (`test_no_refusal_text_names_an_id`).
- **Downgrade** is refused (`test_0006_refuses_to_downgrade`).
- **Ledger.** The four objects are declared in `db/gate/migration_deltas.py`,
  each with its catalog digest. The head-delta check passes, and
  `test_the_declared_deltas_for_0006_are_exactly_its_four_objects` pins the
  scope. The static-audit counts follow from the ledger, as for `0005`.

**A discrepancy in the approved text, stated here and not settled
silently.** G5-12 opens with "It adds one function and two triggers". The
same paragraph then names TWO functions, each with its own rules:
`enforce_opportunity_history()` and `enforce_opportunity_birth()`. The
migration implements what is named in detail: two functions and two
triggers. If one function was meant, the change is mechanical, and the
behaviour and the tests do not change.

**Trigger order** (PostgreSQL fires BEFORE triggers in name order):
- `trg_opportunity_birth` fires before the frozen `trg_opportunity_gate`, so
  a refused birth reports the birth rule;
- `trg_opportunity_gate` fires before `trg_opportunity_history`, so B1–B3
  report the frozen gate first, and rule 2 guards behind it (§4.2).

## 2. Before the fix (measured)

`evidence/SLICE5-STEP1-0006-BEFORE-FIX.txt`.

**Part 1: the shipped test file, run at `6ba73ce`, before the migration
existed.** The tree held one untracked file, the test file itself, whose
sha256 is recorded.
- **45 failed**, every one "DID NOT RAISE";
- **19 passed**: the writes that must still succeed (B10, the writable
  columns, the five accepted stamp cases, the pair freed after closing, the
  birth of a NEW row).

**Part 2: the full suite with `0006` applied, before any existing test was
changed.** 2022 passed and 1 failed, as the next section explains.

## 3. Existing tests that changed, and why

1. **`test_slice3_identity._opportunity(status="CLOSED")`** inserted an
   opportunity born CLOSED, a history it never lived. The birth rule
   refused it (part 2 above). The fixture now inserts NEW, then closes
   along NEW → CLOSED with `closed_at` and `BUYER_REJECTED`.
2. **The same test then failed on `ux_one_open_opportunity_per_pair`.** It
   built an open opportunity, then a closed one for the same pair. Born
   NEW, the second collided with the first. The born-CLOSED insert had hidden
   that order. A closed opportunity beside an open one is one that closed
   before the other opened, so the two lines are swapped.

   The test's intent is unchanged: a closed opportunity on the alias raises
   no task.
3. **`test_migrations.py`.**
   - `HEAD` is `0006`.
   - Since `0006`, `alembic downgrade` from head stops at `0006`'s own
     refusal and never reaches `0005`'s. So `0005`'s refusal is now asserted
     on the revision itself (its `downgrade()` raises "0005 has no
     downgrade"), and the alembic-level refusal is asserted generically.
   - `test_0006_refuses_to_downgrade` and the scope test are new.

## 4. Mutation evidence

### 4.1 The first run, kept

`evidence/SLICE5-STEP1-0006-MUTATIONS-FIRST-RUN.txt`, at `e0892ce`, clean
tree. It reported **six survivors**, of two kinds.

- **Four were not mutations: H2c, H2f, H2i and H2j.**
  - `_without()` in `db/dev/mutate_0006.py` removed a column from rule 2
    only when the column was followed by `", "`.
  - `approved_match_id`, `why_real` and `created_by_account_id` end their
    lines, and `created_at` is last. For these four, the "mutant" was
    identical to the original.
  - This was measured by comparing each mutated text with the source.
- **Two were real: H2a and H2b,** `request_id` and `property_id` removed
  from rule 2. With the frozen gate present, no UPDATE that changes either
  column alone is accepted by the gate. So the B1–B3 tests, which accept
  the gate's refusal, could not tell rule 2 from it.

**The fixes, in `4011558`:**
- `_without()` handles all three positions, and asserts that it removed
  something;
- **`mutation_runner.py` now refuses a mutation that changes nothing.** All
  14 mutation scripts were audited against the current tree: 386
  mutations, no anchor missing, no no-op;
- **`test_rule_2_refuses_a_match_change_the_frozen_gate_accepts`.**
  `approved_match_id` is moved to the pair's other APPROVED, ELIGIBLE match.
  The gate accepts that change, and only rule 2 refuses it;
- **`test_rule_2_alone_refuses_the_pair_and_the_match`.** B1–B3 run with the
  frozen `trg_opportunity_gate` disabled inside the test's rolled-back
  transaction. It uses the superuser's ability to disable a trigger
  (EN-02) to TEST a guard. It makes no claim about K06.

### 4.2 The record

`evidence/SLICE5-STEP1-0006-MUTATIONS.txt`.
- **Run:** at `4011558`, on a clean tree, source fingerprint
  `7edec361…c5f5`.
- **Result: 29 of 29 fail, none survives.** The baseline is 68 passed.
- **Restoration:** every mutated file was restored, and verified by sha256.

The 29 mutations:
- rules 1–4: H1, H2 and H3, H3b, H3c (one forbidden edge each), H4, H4b
  (one-way), H4c (no reason check);
- rule 2, one column at a time: H2a–H2j;
- rule 5's three cases (H5a–H5c) and rule 6's three cases (H6a–H6c);
- the birth rule: B1–B4;
- the history trigger: T1.

### 4.3 An incident during the audit, stated

The audit first imported each mutation script. `mutate_input_hardening.py`
has no `__main__` guard, so importing it STARTED its mutation run:
- it mutated `src/turab/services/relations.py`, then
  `src/turab/services/requests.py`;
- the process was stopped;
- both files were restored from git. The backup of `requests.py` was first
  compared with `HEAD`, and was identical.

`git diff HEAD -- src tests db/migrations` was then empty, no `.orig` file
remained, and nothing was committed in between. The audit was redone
without importing that script: its list was read with `ast`.

The script is unchanged: adding the guard is outside this step's scope. It
is reported here for a decision.

## 5. The evidence round

Each row below ran on a clean tree, source fingerprint `7edec361…c5f5`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Suite (`record_test_run.py`) | 2027 passed, 0 failed, 0 errors, 0 skipped | `5f61963` | `evidence/TEST-RUN-PROVENANCE.txt`, `run_binding.py`: `bound` |
| PostgreSQL gate (`record_gate_run.sh`) | PASS; 70 database-level PASS notices, 0 FAIL; contract, inventory and policy table hold 67 operations | `fca3c65` | `evidence/gate-run.txt` |
| Authorization matrix | 151 rules, PASS; no rule added (`0006` adds no authorization rule) | `fca3c65` (suite run at `3f21224`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| `0006` mutations | 29/29 fail | `4011558` | §4.2 |

**Limits that are part of these results:**
- **The guards hold against the application's ordinary statements only.**
  The tests run as `turab`, a superuser and the owner of every table
  (EN-02). Such a role can disable these triggers, as §4.1's own test does
  inside a rolled-back transaction.
- **K06 stays UNPROVEN** (G5-13 (b), decided as (ii)). `0006` is not
  evidence for K06.
- **These results are ours.** No independent run exists.

## 6. STOP GATE C and D documents, after this step

`SLICE_3_STOP_GATE_C.md` stayed the record of the Slice 3 tree after
Slice 3 closed. `SLICE_4_STOP_GATE_D.md` is treated the same way after
Slice 4 closed: it is **not regenerated**. It stays bound to the run it was
generated from (`333b5f7`), as `SLICE_4_CLOSURE.md` cites it.

**Measured on this step's tree:**
- `stop_gate_d_evidence.py --check` exits 1, with ONE problem: the document
  is stale. It reports no missing or failed mapped test, no unbound run,
  and no writer of `match_reviews` or `opportunities`.
- **What regeneration would change.** The generator was run, its diff
  read, and the document restored. Three lines would change:
  - the run's binding;
  - the case count, 1957 → 2027;
  - the migration list, with `0006` added.

  The reconstruction and replay counts would not change.
- `stop_gate_c_evidence.py --check` reports the problem it has reported
  since Slice 4 step 1 (stale against the current tree).

If the reviewer wants D regenerated at each Slice 5 step instead, it is
one command, and it binds to the step's run.

## 7. What remains

- **Step 1 closes on review.**
- **Steps 2–6** need G5-3, G5-5 and G5-10, and the rest of the plan's
  open details. They do not start before these are decided.
- **Standing:**
  - G4-5R is open; STOP GATE E is for SALE only;
  - K06 is UNPROVEN until G5-13 (b)'s separate step;
  - `mutate_input_hardening.py` has no `__main__` guard (§4.3).
