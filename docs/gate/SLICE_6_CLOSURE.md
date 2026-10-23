# Slice 6 — Closure record

**Slice 6 — Match Diagnostic / Information Work**

**Status: Slice 6 is CLOSED at `ce8cfa0`, within the SALE scope only.** The
review of `ce8cfa0` closed step 5 and the slice (§0). **This is the closure
of the slice. It is not a release authorization.**

**The scope closed:** the approved scope, **SALE only** (G4-5R open).

**Baseline:** Developer Handoff v1.0.3, technical pack v0.2.3, frozen.

**Plan:** `docs/gate/SLICE_6_PLAN.md`, revision 16 at `ce8cfa0`; revision 17
records the closure.

The decisions in this record are the reviewer's. It states them, and their
limits, as they were given, and adds no claim of its own.

---

## 0. The closing decision (review of `ce8cfa0`)

> I close step 5 and Slice 6 at `ce8cfa0`, within the SALE scope only. This
> is a decision to close the slice, not a release authorization.
> (The review of `ce8cfa0`; translated from the Arabic: "أُغلق الخطوة 5
> والشريحة 6 عند `ce8cfa0`، ضمن نطاق البيع (SALE) فقط. هذا قرار إغلاق
> للشريحة، وليس إجازة إصدار.")

**What the review checked itself:**
- **the diff since `3657973`:** the fix concerns the title of a
  `CONFIRM_PRICE` task whose subject is the `REQUEST`, and keeps the title
  of an offer subject;
- **the tests:** both cases are proven, and so is the fate of a task stored
  under its old title;
- **the documents:**
  - D02 is bounded in the plan;
  - the module docstrings of `diagnostic.py` and `diagnostic_replay.py` are
    corrected;
  - the closure evidence records both decisions, and both replay limits
    without calling them proven;
- **the record before the fix:** the defect was pinned in three places
  (`evidence/SLICE6-STEP5-F6-22-BEFORE-FIX.txt`).

**What it did not do.** 2614/2614, the mutations (16/16 twice), the gate and
`--check` are the implementing team's evidence, bound to the tree. The
reviewer did not re-run them independently.

## 1. The limits this closure carries, as given

1. **The replay (R)/(D) does not verify the diagnostic's own
   `input_hash`.** A replay of `{"R": [], "D": []}` is not a proof that every
   input of that hash is sound (plan §5.4; `SLICE_6_EVIDENCE.md` §5.1).
2. **`explain.blocker_summary` is not pinned.** The three pins of step 3 do
   not cover it. Before any later change of it that affects the summary:
   keep the historical computation (or a version of it), and test the
   replay of an old row and of a new row (plan §5.4;
   `SLICE_6_EVIDENCE.md` §5.2).
3. **OQ6-1 and OQ6-2 are open.** Neither is a licence to change the schema
   (plan §5.3).
4. **K06 is UNPROVEN** (G6-12; EN-02). **Its remedy is an independent
   condition before any release gate.**
5. **G4-5R is open.** The evidence's scope is SALE only.
6. **The tasks stored under the old title (F6-22).** The measurement
   (`evidence/SLICE6-STEP5-F6-22-STORED-TITLES.txt`):
   - **what it found:** two rows, in the test database;
   - **what it does not prove:** that no such row exists in a persistent
     database, which was not reachable from that environment.

   **When a persistent database is set up or migrated, it must be inspected
   before the old titles are considered handled.** The inspection:

   ```sql
   SELECT task_id, status, created_at
     FROM turab.tasks
    WHERE payload ->> 'source' = 'DIAGNOSTIC'
      AND task_type = 'CONFIRM_PRICE'
      AND payload -> 'subject' ->> 'entity' = 'REQUEST'
      AND title = 'Confirm the offer''s price terms';
   ```

   No path updates a title, so such a row keeps its old title, before and
   **after** it is DONE: completing a task does not change its title.
   - **While it is OPEN or IN_PROGRESS,** the open-work index refuses a new
     task for the same subject.
   - **Once it is DONE,** a later run that raises the work again creates a
     **new** task, which carries the corrected title. The old row stays as it
     was, with its old title.

   Both are shown by
   `test_f6_22_an_old_title_stays_after_done_and_new_work_gets_the_corrected_title`. It was named
   `test_f6_22_a_task_stored_with_the_old_title_keeps_it_until_done` at `ce8cfa0`, and renamed
   after the closure (§6). *(The documentary correction of the review of
   `3583b6a`: the earlier wording, "keeps its title until it is DONE",
   suggested that the title changes on completion.)*

## 2. The steps, and the reviews that closed them

| Step | Content | Closed at | Delivery note | Mutations |
|---|---|---|---|---|
| 0 | measurements | accepted in the review of `1fd7bdf` | `evidence/SLICE6-PLAN-MEASUREMENTS.txt`, `…-R3.txt` | — |
| 1 | migration `0007`, parts A–D (and the addendum of M-1) | `b6a08e7` | `SLICE_6_STEP1_DELIVERY.md` | 23/23 |
| 2 | `getTasks`, `postTasksTaskIdComplete`, CORRECTION-005, the completion's lock order | `315804b` | `SLICE_6_STEP2_DELIVERY.md` | 34/34 |
| 3 | the diagnostic's pure functions, their registry entries, replay | `922a100` | `SLICE_6_STEP3_DELIVERY.md` | 39/39, twice |
| 4 | the run writes the format-2 diagnostic and raises its tasks | `0fae42c` | `SLICE_6_STEP4_DELIVERY.md` | 19/19, twice |
| 5 | the mandatory and red-team tests end to end, the closure evidence; the correction of F6-21 and F6-22 | `ce8cfa0` | `SLICE_6_STEP5_DELIVERY.md` (§13: the correction) | 16/16, twice |

## 3. The decisions of the last two reviews

- **F6-21 (review of `3657973`): a documentary correction.**
  - §3.4 and §6.2's D02 bind what Slice 6 generates: the diagnostic, its
    tasks, and their audit.
  - The rule "the expectation appears in no output of the run" is not
    attributed to the system. Slice 4 §3.5 keeps it in the staff match's
    snapshot, and `API_CONTRACTS_v0.2.md` §8 forbids its serialization to
    public and customer DTOs.
  - `test_f6_21_the_staff_match_keeps_the_expectation_the_boundary_witness`
    is the boundary's witness.
- **F6-22 (review of `3657973`): the title by type and subject entity.**
  - `CONFIRM_PRICE` on the `REQUEST` is "Confirm the request's maximum
    budget";
  - on a `PROPERTY_OFFER`, the offer's title stays.
  - Pinned on the unfixed code (`a813b06`), then fixed (`fd648e8`).
  - Neither a pinned rule nor an input hash changed: the registry digest
    `47188d01…` is unchanged.

## 4. The evidence the closure rests on

**The evidence of `ce8cfa0`'s tree,** which the closure rests on. The
closure evidence as it stood there is `git show ce8cfa0:docs/gate/SLICE_6_EVIDENCE.md`.
The current file is the evidence of a later tree (§6).

| Evidence | Result | Record |
|---|---|---|
| Closure evidence (not a STOP GATE) | generated from the bound run; `slice6_evidence.py --check` exits 0 | `SLICE_6_EVIDENCE.md` at `ce8cfa0` (generated at `d4a1263`) |
| Suite | 2614 passed, 0 failed, 0 errors, 0 skipped; `bound`; source fingerprint `2858511a…cbde` | `evidence/TEST-RUN-PROVENANCE.txt` (`5d0cd09`) |
| PostgreSQL gate | PASS; 70 PASS notices; 67 operations equal | `evidence/gate-run.txt` (`c627551`) |
| Authorization matrix | 189 rules | `AUTHORIZATION_EVIDENCE_MATRIX.md` (`130b725`) |
| Writes to `tasks`, by kind | INSERT: `identity.py`, `match_review.py`, `matching_run.py`; UPDATE: `tasks.py` (`status`, `completed_at`); no DELETE | `SLICE_6_EVIDENCE.md` §7 |

**These results are ours.** The reviewer did not re-run them independently
(§0).

## 5. Next

- **No code for the next slice** before its plan is approved.
- **K06's remedy** stays an independent condition before any release gate
  (§1, limit 4).

## 6. After the closure: the evidence of a later tree (review of `1c27241`)

**Decided** (review of `1c27241`):
- correct the two remaining places where "keeps it until DONE" suggested
  that an old row loses its title on completion:
  - the generator's text;
  - the test's name;
- update the name's references in the generator, and regenerate the
  evidence;
- run again the evidence round the new tree needs, recorded as a new run.

**Not reopened.** This is a correction of the evidence of a later tree. It
does not reopen Slice 6, and it is not a release authorization. The closure
at `ce8cfa0`, and its evidence (§4), stay attributed to their tree.

**What changed** (`c25ec48`):
- **the test is renamed.** It was
  `test_f6_22_a_task_stored_with_the_old_title_keeps_it_until_done`, and is
  now
  `test_f6_22_an_old_title_stays_after_done_and_new_work_gets_the_corrected_title`.
  Its assertions are unchanged, and its docstring states the old name;
- **the generator's text** now reads: "such a row keeps its old title, also
  after it is DONE; a later run that raises the work again creates a new row
  with the corrected title". So does the F6-22 decision's wording, and the
  mapping now uses the new name;
- **no line of `src/` changed.** The source fingerprint changes through
  `tests/` and `db/gate/`.

**The records of `ce8cfa0`'s tree keep the old name, as written then:**
- the mutation runs at `fd648e8`;
- `SLICE6-STEP5-F6-22-STORED-TITLES.txt`;
- `SLICE6-STEP5-F6-22-BEFORE-FIX.txt`.

**The evidence round of the later tree,** a new run. Every row was run on a
clean tree, with source fingerprint
`2d11e774856f78ba9217880297422066ea03fb6d5592e315588d7c157c3c5563`, on
PostgreSQL 16.15.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations, step 5, twice | 16/16 each, none survives; counts identical to `fd648e8`'s | `54fa81c` (runs at `c25ec48`) | `evidence/SLICE6-STEP5-MUTATIONS-AT-c25ec48.txt`, `…-REPEAT.txt` |
| Authorization matrix | 2614 passed; the document is unchanged (189 rules; it names no renamed test), so nothing was committed | — (run at `54fa81c`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS. The body is identical to the run at `c627551`; only the header differs | `0cdc714` (run at `54fa81c`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | 2614 passed, 0 failed, 0 errors, 0 skipped; `bound` | `846de5e` (run at `0cdc714`) | `evidence/TEST-RUN-PROVENANCE.txt` |
| Closure evidence | regenerated from that run; `--check` exits 0; "until DONE" no longer appears | `8a7e6fa` | `SLICE_6_EVIDENCE.md` |

**These results are ours.** The reviewer did not re-run them.

## 7. The review of `8de5f7f`: the correction accepted

- **Accepted:**
  - the test's name and the generated evidence now state that an old row
    keeps its title after `DONE`, and that work raised later creates a new
    row with the corrected title;
  - the test's assertions check both;
  - this record separates the historical evidence of `ce8cfa0`'s tree from
    the later tree's;
  - the diff does not touch `src/`.
- **What the reviewer checked:** the new round's records, and their binding
  to the source fingerprint `2d11e774…3c5563`.
- **What the reviewer did not re-run:** the tests, the mutations,
  PostgreSQL or `--check`. Their stated results remain the implementing
  team's.
- **Slice 6 stays CLOSED at `ce8cfa0`,** for SALE only. This is not a
  release authorization.
- **Each tree's evidence stays attributed to that tree:**
  - `ce8cfa0`'s, as §4 lists it;
  - the later tree's (`8de5f7f`), as §6 lists it.
- **K06's remedy** stays an independent condition before any release gate.
