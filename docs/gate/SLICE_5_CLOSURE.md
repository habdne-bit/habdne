# Slice 5 — Closure record

**Slice 5 — Human Review → OPPORTUNITY**

**Status: Slice 5 is CLOSED at `339dbc4`, within the SALE scope only.**
The review of `339dbc4` approved this record and closed the slice (§0).
**This is the closure of the slice within its scope. It is not a release
authorization.**

**The scope closed:** the approved scope, **SALE only**.

**Baseline:** Developer Handoff v1.0.3, technical pack v0.2.3, frozen.

**Plan:** `docs/gate/SLICE_5_PLAN.md`, revision 20 at `339dbc4`; revision 21
records the closure and the RENT qualification.

The decisions in this record are the reviewer's. It states them, and their
limits, as they were given, and adds no claim of its own.

---

## 0. The closing decision (review of `339dbc4`)

> I approve the closure record, and I close Slice 5 at `339dbc4`, within the
> SALE scope only. This is a closure of the slice within its scope, not a
> release authorization.
> (The review of `339dbc4`; translated from the Arabic: "أعتمد سجل الإغلاق،
> وأُغلق Slice 5 عند 339dbc4 في نطاق البيع (SALE) فقط. هذا إغلاق للشريحة
> ضمن نطاقها، وليس إجازة إصدار.")

**What the review checked itself:**
- the bundle's digest and its 398 manifest entries;
- that the record attached matches its copy in the bundle;
- that `src` and `tests` are unchanged since step 6, and the source
  fingerprint with them;
- `bound`, and `stop_gate_e_evidence.py --check` (exit 0).

**What it did not do:** it re-ran no suite and no mutation. 2367/2367 and
7/8 remain our results (§2, limit 1).

**The limits it kept, as this record states them:**
- C2 and L2 survive; C2 is not counted as killed (§4);
- K06 is UNPROVEN; the application role must be remedied before any
  release gate (§2, limit 3);
- G4-5R is open; STOP GATE E covers SALE (§2, limit 2);
- STOP GATE D is the record of Slice 4's tree (§7).

**A documentary correction, not blocking.** The phrase "no RENT opportunity
can exist" (§2, limit 2, and the plan's §0) is qualified to "is not created
through the currently approved matching and approval path". The unqualified
phrase does not prove that a direct insert is impossible, the more so while
K06 is UNPROVEN. The correction is made in place, at both places, and
marked. It does not reopen the slice: "لا حاجة لإعادة فتح Slice 5 لهذا
التصويب".

**Next:** no code for the next slice before its plan is approved (§8).

## 1. The decision this record follows

> I accept step 6 at `735211c` and authorize preparing the closure record of
> Slice 5, within the declared SALE scope. I do not consider the slice
> closed before the closure record itself is reviewed.
> (The review of `735211c`; translated from the Arabic.)

**What the review checked itself:**
- the bundle's digest, its 397 manifest entries, the full source
  fingerprint, `bound`, and `stop_gate_e_evidence.py --check` (exit 0);
- the tests of the two carried limits, and the place of the lock: the
  request lock precedes the supersession check, and the two tests separate
  the two orders of the race with a wait witness.

**What it accepted:**
- **the remedy of L-S5-3b, by the lock;**
- **the proof of L-S5-3a, within its declared limit.** The second policy,
  and the match made under it, live inside a transaction that is rolled
  back;
- **the decision on C2 (§4 below).**

**What it requires this record to state:**
- STOP GATE E covers SALE only;
- K06 is still UNPROVEN, and G4-5R is open;
- STOP GATE D remains the record of Slice 4's tree;
- C2's and L2's survival, and the difference between `FOR NO KEY UPDATE`
  and `FOR SHARE` (§4).

## 2. The limits of the decision

These limits are part of the decision. They are not caveats added by the
implementer.

1. **The results are ours, bound to the tree.** The reviewer re-ran no
   PostgreSQL, no suite and no mutation. These rest on our own runs, each
   bound to its tree by commit and source fingerprint:
   - the suite, 2367/2367;
   - the gate;
   - step 6's mutations, 7/8;
   - every earlier step's mutation records.

   None is an independent run.
2. **SALE only.** STOP GATE E's proof is one SALE. G4-5R is open: a RENT
   request is never matched, so no RENT opportunity is created through the
   currently approved matching and approval path. This does not prove that
   a direct insert of one is impossible, the more so while K06 is UNPROVEN
   (limit 3).
   *(Qualified in the review of `339dbc4`. As submitted at `339dbc4`, it
   read "so no RENT opportunity can exist".)*
3. **K06 is UNPROVEN.**
   - The application role is a superuser and owns every table (EN-02,
     G5-13).
   - K06 needs a test under a role that is neither. That is G5-13
     (b)(ii)'s separate, cross-cutting step, mandatory before any release
     gate.
   - The trigger-level refusals are listed as trigger-level, never as K06.
4. **L-S5-3a is proven within its declared limit.** The second policy and
   its match live inside a rolled-back transaction. The run and the
   approval in it are the real services.
5. **Step 6's mutations stay 7/8.** C2 is not counted as killed (§4).

## 3. The evidence the decision rests on

The final source fingerprint is
`9e6c68cc5c12971ff8d4e188b029e3c9b65266fe0802b00bee3cf5349ba584d7`. The
commits after `e63e693` are evidence and documents only.

| Evidence | Result | Commit | Tree | Record |
|---|---|---|---|---|
| Application suite (`record_test_run.py`) | 2367 passed, 0 failed, 0 errors, 0 skipped | `82f7995` (run at `975a448`) | clean | `evidence/TEST-RUN-PROVENANCE.txt` |
| PostgreSQL execution gate | PASS; 70 database-level PASS notices, 0 FAIL; 67 operations in parity | `975a448` (run at `cd5511f`) | clean | `evidence/gate-run.txt` |
| STOP GATE E | generated from the run at `975a448`; 49 rows PASS; `--check` exits 0 | `735211c` | clean | `SLICE_5_STOP_GATE_E.md` |
| Authorization matrix | 183 rules, 183 PASS | `cd5511f` | clean | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| Step 6 mutations | **7/8 fail; C2 survives** (§4) | `0183106` | clean | `evidence/SLICE5-STEP6-MUTATIONS.txt` |
| Step 5 mutations (after the note change) | 51/51 fail | `37701ce` | clean | `evidence/SLICE5-STEP5-MUTATIONS-AFTER-NOTES.txt` |
| Step 3 L1/L2, after L-S5-3b | **both survive step 3's tests** (§4) | `e9904c0` | clean | `evidence/SLICE5-STEP3-MUTATIONS-L1-L2-AFTER-L-S5-3B.txt` |
| Step 3 L3/L4, after the share's lock mode | 2/2 fail | `0a5c446` | clean | `evidence/SLICE5-STEP3-MUTATIONS-L3-L4-AFTER-LOCK-MODE.txt` |

**Measurements before a fix**, each in an isolated worktree at its base
commit:
- R-S5-5-01 (`SLICE5-STEP5-R-S5-5-01-BEFORE-FIX.txt`);
- the dropped notes (`SLICE5-STEP5-NOTES-BEFORE-FIX.txt`);
- L-S5-3a and L-S5-3b (`SLICE5-STEP6-L-S5-3-BEFORE-FIX.txt`);
- and those of steps 1–5, listed in their delivery notes.

The earlier mutation records stay in git history, each at the commit it was
taken on.

## 4. C2 and L2: recorded as decided, not counted as killed

**The mutations:**
- **C2** (step 6) weakens the currency check's lock on the request from
  `FOR NO KEY UPDATE` to `FOR SHARE`;
- **L2** (step 3) is the same weakening;
- **L1** (step 3) removes the lock.

None of the three changes any test's result in its own step's file:
- L1 and L2 stopped failing step 3's tests once the approval took the
  request `FOR UPDATE` before the currency check (L-S5-3b);
- L1 is killed in step 6 by C1;
- C2 and L2 survive.

**The decision (review of `735211c`).**
- `FOR NO KEY UPDATE` is kept.
- C2 is classified as **a mutation not required by the approved
  correctness condition**. It is **not counted as killed**: step 6's
  record stays 7/8, not 8/8.
- It is **not called "equivalent" without qualification**: `FOR SHARE`
  changes how two checkers on the same request wait.

**The difference, stated.**
- **What `FOR SHARE` changes.** `FOR NO KEY UPDATE` conflicts with itself,
  and `FOR SHARE` does not (PostgreSQL 16, §13.3.2, Table 13.3). Under C2,
  two checkers on the same request (two revalidates, two shares, or one of
  each, on different opportunities) no longer wait for each other at the
  request.
- **What the tests prove necessary.** A lock that conflicts with a writer
  of the request is necessary, and both modes are such a lock.
  `test_a_revalidate_waits_for_a_request_writer_and_reads_its_commit` shows
  the revalidate waiting on an uncommitted status change, then recording
  it. C1, which removes the lock, is killed by it.
- **What the approval's own lock provides.** The approval's new
  `FOR UPDATE` provides the serialization the approval requires (L-S5-3b,
  and one open opportunity per pair).
- **What is not required.** No approved condition requires two revalidates
  or shares on one request to serialize at the request: they write
  different rows, and shares already serialize on the property (R-S5-5-01).

The step 6 note (§3.4, §7) first called C2 "equivalent". It is corrected
in its §11 by this decision.

## 5. What was delivered, by step

| Step | Content | Closed |
|---|---|---|
| 0 | the PostgreSQL measurements of the plan, no code | accepted in the review of `288bfdb` |
| 1 | migration `0006`: the opportunity history (two functions, two triggers; rules 1–6 and the birth rule) | in the review of `f5a9d88` |
| 2 | the review: REJECTED and NEED_MORE_INFORMATION with its one task; the review stamp (§3.1); the key race fixed | at `1e0d919` |
| 3 | APPROVED: the currency check (§3.7), the one opportunity (G5-5 (a)), its uniqueness and concurrency | at `921ed01` |
| 4 | the internal read, the customer read (frozen type, [R4-2] withholding, no free text), the match queue | at `1556624` |
| 5 | revalidate, share, close, the opportunity queue, B10; R-S5-5-01; the interactions of share, close and revalidate | at `3a60b3b` |
| 6 | L-S5-3a proven; L-S5-3b closed; E04, K05, K06 (UNPROVEN); STOP GATE E | accepted at `735211c` |

**Contract and schema changes:**
- **Contract:** none. The eight Slice 5 operations are declared in the
  frozen contract.
- **RFC-001 Appendix B (DL-13)** amends R8.2, R8.3, S33, S34 and S36a
  without editing the approved document: the frozen contract first.
- **Migration:** `0006` only.
- **No new table, column or reason code.**

## 6. Decisions, as recorded in the plan

| # | Decision |
|---|---|
| G5-1 | the scope as proposed |
| G5-2 | (a): approval requires the stored gates and the facts now (§3.7); supersession per request, property, policy and offer |
| G5-3 | (a): one decision per review row; REJECTED and APPROVED final; the input narrowed |
| G5-4 | (a): one task per NMI review, with [R6-1] |
| G5-5 | (a): the scope from the offer at approval; the render-derivability list; SUMMARY_ONLY four fields; [R4-2] withholding |
| G5-6 | (a): the frozen contract first, with Appendix B; B.1a, the free-text location detail withheld |
| G5-7 | (a): no customer visibility before sharing |
| G5-8 | the share check that refuses without writing; (i) (a) one interaction per successful share; (ii) as proposed; (iii) (a) CONTACT_BEFORE_SHARING refuses |
| G5-9 | revalidate on §3.7, the one writer of validity; no offer switch |
| G5-10 | the eight close reasons; CLOSED final; the note in a STATUS_CHANGE interaction (review of `1f8a8df`) |
| G5-11 | the match queue as proposed; the opportunity queue (a), no time-based membership |
| G5-12 | `0006` exactly as written; B10 left to the service guard and its three proofs |
| G5-13 | (a) documented (EN-02); (b)(ii): the role's remedy is a separate step; K06 UNPROVEN |
| step 5 I1–I8 | accepted; I4 amended by G5-8 (i) |
| L-S5-3a | proven, within its declared limit |
| L-S5-3b | closed by the approval's request lock |
| C2 | not required by the approved correctness condition; not counted as killed (§4) |

## 7. Carried forward, unchanged by this closure

- **G4-5R is open.** SALE only, and STOP GATE E covers SALE only.
- **K06 is UNPROVEN.** G5-13 (b)(ii)'s step is mandatory before any
  release gate.
- **STOP GATE D remains the record of Slice 4's tree.**
  - It is not regenerated in Slice 5 (review of `f5a9d88`).
  - Its `--check` reports it stale against the current tree, with three
    known problems: the writers of `match_reviews` and `opportunities`,
    and staleness.
  - That report is neither a pass nor a failure of Slice 5.
- **`SLICE_3_STOP_GATE_C.md`** stays stale against the current tree, as
  Slice 4 recorded.
- **The boundary with Slices 6 and 7:**
  - the tasks operations (`getTasks`, `postTasksTaskIdComplete`) are Slice
    6's;
  - the customer's response to an opportunity, ENGAGED, messages and
    threads are Slice 7's;
  - an `interactions` row written here records a command, and is never
    proof of a message or a contact.
- **No contact is released through the customer opportunity view**
  (Appendix B.3).
- **Stamps from `now()`** (`bound_at`, `audit_log.occurred_at`) are the
  start of their transaction. The serialization proven here is by commit
  (step 5 §13.9).
- **The cost of the locks, stated:**
  - a share waits for open key locks on its property and offer;
  - an approval holds its request `FOR UPDATE` until it commits.
- **Carried from earlier slices, unchanged:**
  - relations are never an authorization source, nor a matching input;
  - G3-2 is open, and PROPERTY claims fail closed;
  - account provisioning (G3-5) and D4 are open.
- **The evidence discipline carries into the next slice:**
  - results are bound to commit and source fingerprint;
  - a defect is measured before it is fixed;
  - mutation evidence is taken on a clean tree;
  - every delivered document carries a sha256.

## 8. Next

- ~~**The review of this record.** Slice 5 closes only on that review.~~
  Done: the review of `339dbc4` approved this record and closed the slice,
  SALE only (§0).
- The planning of the next slice, when the reviewer directs it. No code
  for it until its plan is approved.
- Before any release gate: G5-13 (b)(ii), the application role's remedy
  and K06's test under a role that is neither superuser nor owner.
