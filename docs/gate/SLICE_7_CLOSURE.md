# Slice 7 — Closure record

**Slice 7 — Communication / WhatsApp Record**

**Status: PREPARED for review. Slice 7 is NOT closed.** The review of
`4b72ad5` closed step 5 and asked for this record (§0). The review of
`40338be` did not close the slice: the plan's statements of status
contradicted this record, and are corrected in its revision 26. **The slice
stays open until this record is reviewed.** **This is not a release
authorization.**

**The scope:** the approved scope, **SALE only** (G4-5R open).

**Baseline:** Developer Handoff v1.0.3, technical pack v0.2.3, frozen.

**Plan:** `docs/gate/SLICE_7_PLAN.md`, revision 24 at `4b72ad5`; revision 25
(`40338be`) records the closure of step 5 and this record's preparation;
revision 26 corrects the plan's statements of status (review of `40338be`).

The decisions in this record are the reviewer's. It states them, and their
limits, as they were given, and adds no claim of its own. Where it maps an
acceptance condition to its evidence (§3), it names the record that holds
it; it does not re-judge it.

---

## 0. The decision of the review of `4b72ad5`

> I accept the closure of step 5 at `4b72ad5`. […] The decision to close
> step 5 may be recorded, and Slice 7's closure record prepared for review.
> The slice itself stays open until its record is reviewed. R-1 stays unmet
> before any real event, K06 is unproven, and the scope is SALE only; this
> is not a release authorization.
> (The review of `4b72ad5`; translated from the Arabic: "أقبل إغلاق الخطوة 5
> عند `4b72ad5`. […] يمكن تسجيل قرار إغلاق الخطوة 5 وإعداد سجل إغلاق الشريحة 7
> للمراجعة. الشريحة نفسها تبقى مفتوحة إلى حين مراجعة سجلها. يبقى R-1 غير
> مستوفًى قبل أي حدث حقيقي، وK06 غير مثبتة، والنطاق SALE فقط؛ وهذا ليس إجازة
> إصدار.")

**What the review checked itself:**
- **the code:** the run's recorder fixes the connection's destination and
  records the server's identity; the sample tool compares that identity
  before counting; the generated evidence shows the counts as a measurement,
  not PASS;
- **the two mutation records:** each lists 33 mutations, none surviving.

**What it did not do, as it states:**
- re-run the suite (3173/3173), the PostgreSQL gate, `bound` or `--check`.
  These are the team's runs;
- take the binding for more than it says: it does not prove the test
  database was not dropped and recreated between the run and the sample, as
  the delivery note states (`SLICE_7_STEP5_DELIVERY.md` §8.5).

---

## 1. The limits the slice carries, as given

1. **R-1 is UNMET** (G7-2 (ii), (a2) decided in the review of `4aed49b`).
   The relay is not built, and its seven duties are untested. **No real
   event may be received before R-1 is met.** The relay's signature proves
   the relay's origin, **not Meta's**: Meta's verification is never counted
   as done in this slice.
2. **K06 is UNPROVEN** (G7-13; EN-02). The application role is a superuser
   and owns every table. `0008`'s refusals are trigger- and
   constraint-level, and are never counted as K06.
3. **G4-5R is open.** The scope is SALE only.
4. **Retention is not claimed** (OQ7-1). Content archived under a consent
   stays after the consent's revocation.
5. **One interaction per message holds within the service's paths only**
   (G7-18 (iv)). It is not a database constraint, and there is no `0009`. A
   message written outside the service's paths has none.
6. **A confirmation link is valid at its writing only** (G7-18 (vii)). The
   observation it names can still change afterwards, and the link has no
   legal value.
7. **The operator recovery command recovers a message without its content**
   (G7-2 (v), accepted in the review of `58a0067`).
8. **The writes' inventory reads the application's statements** under
   `src/`. It is not a guarantee against a superuser's writes (G7-19 (ii)).
9. **The event-store sample is a measurement, never a PASS** (G7-19 (i)).
   It is taken from the run's test database after the run, on the server the
   run's connections reached. It is not the state at the last test's moment,
   and it does not prove the database was not dropped and recreated between
   the run and the sample (§0).
10. **The results are ours.** No independent run exists (§0).
11. **The earlier slices' records stay their trees' records.**
    `SLICE_5_STOP_GATE_E.md`, `SLICE_6_EVIDENCE.md` and
    `SLICE_3_STOP_GATE_C.md` report stale on this tree. Slice 7's generator
    reads none of them (G7-19 (iii)).

## 2. The steps, and the reviews that closed them

| Step | Content | Closed at | Delivery note | Mutations (last record) |
|---|---|---|---|---|
| 0 | measurements M1–M8 | done (authorized in the review of `dcebe46`) | plan revision 2 | — |
| 1 | migration `0008`, parts E, A, B, C, D2 | `7e8993d` | `SLICE_7_STEP1_DELIVERY.md` | 77/77, twice |
| 2 | threads, the link invariant, staff messages, identity and consent; CORRECTION-006 | `6d8815d` | `SLICE_7_STEP2_DELIVERY.md` | 51/51, twice |
| 3 | the WhatsApp webhook; CORRECTION-007 and CORRECTION-008; the recovery command | `23b99b6` | `SLICE_7_STEP3_DELIVERY.md` | 68/68, twice |
| 4 | one interaction per message, the backfill, the timeline's `message`, the confirmation link | `2f968f4` | `SLICE_7_STEP4_DELIVERY.md` | 33/33, twice |
| 5 | the mandatory and red-team tests end to end; the event-store sample; the closure evidence | `4b72ad5` | `SLICE_7_STEP5_DELIVERY.md` | 33/33, twice |

**The decisions:**
- **in the review of `4aed49b`:** D2, CORRECTION-007, (a2) with R-1, and
  G7-4 decided. The directions of G7-1, the other parts of G7-2, G7-3, G7-5,
  G7-6, G7-7, G7-8 (a), G7-9 (a), G7-10, G7-11, G7-13, G7-14 and G7-15 were
  approved as the plan's basis (plan §5);
- **in later reviews:**
  - `0008`'s text: approved in the review of `38281ab`;
  - G7-16: decided in the review of `0f423d2`;
  - G7-17: decided in the review of `bf1fe3d`;
  - G7-18: decided in the review of `e18271a`;
  - G7-19: decided in the review of `d04d5c8`.

## 3. The acceptance conditions (plan §7), and where each is held

| # | Condition | Held by | Not claimed |
|---|---|---|---|
| 1 | the contract changes only by CORRECTION-006, -007 and -008 | `SLICE_7_EVIDENCE.md` §8: each approved (2026-10-25, 2026-10-27, 2026-10-27); the gate: the effective contract regenerated and checked, the same 67 operations | the relay's header is outside the OpenAPI (G7-2 (ii)) |
| 2 | a completed event, replayed, writes nothing; an incomplete one is completed once | `SLICE_7_EVIDENCE.md` §1 (mandatory 1) and §2 (J01, S42, G7-2 (iv)) | — |
| 3 | a provider message identity is global, the NULL case included | §1 (mandatory 2): both orders across threads, and the NULL-provider path refused by the service and by `0008` | `0008`'s CHECK is constraint-level, not K06 |
| 4 | an unverified webhook writes nothing; the check is the relay's origin | §2 (S41) | never Meta's signature (limit 1) |
| 5 | thread links consistent at creation, SALE checked, never changed; a WHATSAPP reference scoped and unique | §1 (mandatory 3); §4 (concurrency: "two threads with one WHATSAPP reference") | the freeze is trigger-level (limit 2) |
| 6 | a phone decision's confirmation link is append-only, with no legal value | §1 (mandatory 4); the K06 list: a message cannot be deleted (`0008` part B) | valid at its writing only (limit 6); trigger-level (limit 2) |
| 7 | no content without a consent valid at write time, in any table or log | §2 (J03): messages, the event store, logs, the audit log, the timeline | retention (limit 4) |
| 8 | what staff can read is exactly what G7-8 decides, by key sets | §3: the timeline's item by exact key sets for ADMIN, OPERATOR and REVIEWER | — |
| 9 | the writes to the four tables are exactly those decided, by kind | §5: INSERT, UPDATE (with each UPDATE's columns) and DELETE, as decided; the INSERT module told from its callers | not a guarantee against a superuser (limit 8) |
| 10 | SALE only, checked; K06 UNPROVEN; no AI | SALE: §1 (mandatory 3) with step 2's rule 0 test (a named opportunity must be a SALE). K06: limit 2. No AI: a search of `src/`, `db/ops/` and the dependencies at `4b72ad5` finds no model client and no call to one (a search, not a test) | K06 (limit 2) |
| 11 | a processing failure is recorded, or the event keeps its status, and no half-written message remains | §2 (G7-2 (iv)): the four failure tests, and the answers whose result is not confirmed | — |
| 12 | R-1 listed as UNMET, required before any real event | `SLICE_7_EVIDENCE.md` header and §7; this record, limit 1 | Meta's verification (limit 1) |

## 4. The evidence the slice rests on

**The evidence of the tree with source fingerprint `7cd994f1…0762`**, the
tree of `4b72ad5`. The commits between the evidence round and `4b72ad5`
touch `docs/` only.

| Evidence | Result | Record |
|---|---|---|
| Closure evidence (not a STOP GATE) | generated from the bound run; `slice7_evidence.py --check` exits 0 | `SLICE_7_EVIDENCE.md` (`01b1708`) |
| Suite | 3173 passed, 0 failed, 0 errors, 0 skipped; `bound` | `evidence/TEST-RUN-PROVENANCE.txt` (`01b1708`, run at `50ad5c2`) |
| The run's destination and server | `host=127.0.0.1 hostaddr=- port=5432 dbname=turab_authz_test`; system identifier `7697828029857667607` at `127.0.0.1:5432` | the same |
| The event-store sample (a measurement, never PASS) | RECEIVED 1, PROCESSED 74, IGNORED 26, FAILED 0, on the recorded server | `evidence/SLICE7-EVENT-STORE-COUNTS.txt` (`01b1708`) |
| PostgreSQL gate | PASS; all database-level contract tests passed; the same 67 operations | `evidence/gate-run.txt` (`50ad5c2`) |
| Authorization matrix | 222 rules; 3173/3173 | `AUTHORIZATION_EVIDENCE_MATRIX.md` (`b97bede`) |
| Step 5 mutations | 33/33, twice, identical, at `101df75` | `evidence/SLICE7-STEP5-MUTATIONS.txt`, `-REPEAT.txt` (`2874380`) |

**These results are ours.** The reviewer did not re-run them independently
(§0).

## 5. Asked of the review of this record

- **whether Slice 7 is closed, and at which commit,** within the SALE scope
  only, with the limits of §1;
- nothing else: no new decision is proposed here.

## 6. Next, whatever the decision

- **R-1 before any real event:** the relay, and its seven duties tested.
- **K06's remedy** stays an independent condition before any release gate.
- **No code for a next slice** before its plan is approved.
- **This is not a release authorization.**
