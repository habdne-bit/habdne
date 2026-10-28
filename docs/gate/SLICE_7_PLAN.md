# Slice 7 — Communication / WhatsApp Record
## Implementation plan — **revision 21**

**Status: step 4 is CLOSED at `2f968f4`, and step 5 is AUTHORIZED** (review
of `2f968f4`, recorded below), within the approved plan. Step 3 is CLOSED at
`23b99b6`. **G7-19 (revision 21) puts three points of step 5 as decisions;
no step 5 code is written before they are decided.** **G7-18 is DECIDED** (review of `e18271a`,
recorded below): the nine options (a), with limits. **Step 4 is CLOSED
at `2f968f4`** (`SLICE_7_STEP4_DELIVERY.md`). Steps 1 and 2 are
CLOSED at `7e8993d` and `6d8815d`. Slice 7 is not closed.
- **Step 3's authorization does not allow receiving real events** before R-1
  is met.
- **G7-17 is DECIDED** (review of `bf1fe3d`, recorded below), with a 503
  `WEBHOOK_NOT_READY` under a new CORRECTION-008.
- **Step 3 is CLOSED at `23b99b6`** (`SLICE_7_STEP3_DELIVERY.md`).
  CORRECTION-007's and CORRECTION-008's texts are APPROVED as delivered
  there.
- **The slice's code so far:**
  - step 1's migration `0008`, with its tests and mutation script;
  - step 2's two staff commands, `postCommunicationThreads` and
    `postCommunicationThreadsThreadIdMessages` (`services/communication.py`,
    `api/routes/communication.py`), with CORRECTION-006, approved;
  - step 3's webhook, its recovery command and CORRECTION-007 and 008,
    approved (`services/webhooks.py`, `api/routes/webhooks.py`,
    `db/ops/recover_webhook_events.py`);
  - step 4's message interactions, their backfill, the timeline's `message`
    and the confirmation link (`services/message_interactions.py`,
    `db/ops/backfill_message_interactions.py`), closed.
- **The review of step 1's progress report** (after `dc35b50`; recorded
  below) did not close step 1. It set what the delivery must show.
- **What the review of `4aed49b` did** (recorded below):
  - **decided** D2 (G7-12 (D)), CORRECTION-007, (a2) with R-1 a condition
    before any real event, and G7-4's provider rule;
  - **approved the directions** of the other recommended options, G7-8 (a),
    G7-9 (a) and G7-15 among them;
  - **did not approve the text of `0008`,** nor the start of step 1, because
    of two gaps in it: the thread reference's identity, and UNKNOWN →
    FAILED. Both are settled here, and the resulting text is §5.1, in full.
- **What the review of `58a0067` did** (recorded below):
  - accepted step 0 as measurement documented by the implementing team;
  - accepted the directions of G7-8 (a) and G7-9 (a), their limits to be
    proven by the implementation's tests;
  - asked for four points to be settled, and for the proposed text of
    `0008`. Both are this revision (§5.1, §5.2).
- **What the review of `dcebe46` did:**
  - accepted revision 1 as a basis for review and measurement;
  - authorized step 0's measurements (M1–M8), which are delivered here;
  - asked for five gaps to be settled in the plan's text before it is put
    up for approval (recorded below).
- **Not yet approved:**
  - the text of migration `0008` (§5.1), and with it the start of step 1.
    **That text has not been executed:** it is first run in step 1, with
    its tests, once approved;
  - the decisions are approved as directions (§5, the status table). The
    review of `4aed49b` states: "This is an approval of the directions, not
    of the defective migration text".

**What this revision does not decide.** Every choice that is not already
fixed by a source is put to the reviewer as a decision (§5), with options and
a recommendation. A recommendation is not a decision.

**What it rests on:**
- **The sources** (§0.1, §3).
- **Step 0's measurements** on PostgreSQL 16.15:
  `evidence/SLICE7-PLAN-MEASUREMENTS.txt`, with its script beside it, run
  twice with identical results.
- **Three facts about Meta's webhooks,** as the review of `dcebe46` cites
  Meta's official documentation (§3.9). **This environment could not fetch
  that page** (DNS: `ENOTFOUND developers.facebook.com`). The facts are
  therefore stated as the reviewer's citation of the official source, not as
  our own reading of it.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | `91762f6` | first plan (authorized as planning only in the review of `8de5f7f`) |
| 2 | `7200b3c` | the review of `dcebe46` recorded; step 0 measured (M1–M8); the five gaps settled in the text: content and consent (G7-9), the stuck event and its recovery (G7-2 (v)), Meta and the relay (G7-2 (ii), §3.9), what staff can read (G7-8), the SALE boundary (§0.2, G7-6 rule 0); new: F7-12, G7-15; G7-12 (D) rewritten on M8 |
| 3 | `dcc1c74` | the review of `58a0067` recorded; the four points settled: (D) put as an explicit choice between D2 (strict, six foreign keys made RESTRICT, its consequences) and D3 (a narrower guarantee stated exactly), D1's "FK-only" name withdrawn; the failure inside the processing transaction (a savepoint, the FAILED record, the stop after RECEIVED, their tests), and the 500 settled by a proposed CORRECTION-007; the relay made condition R-1 before any real event; the provider rule for every channel. The proposed text of `0008` (§5.1) and of CORRECTION-007 (§5.2), neither executed nor approved |
| 4 | `587f8b3` | the review of `4aed49b` recorded: D2, CORRECTION-007, (a2) with R-1, and G7-4 decided; the other directions approved. Its two gaps settled: a WHATSAPP thread's reference is scoped and unique (G7-3; `0008` part E; R-1 duty 6), and UNKNOWN → FAILED is refused (G7-5; part B rewritten). R-1 measures the relay's real envelopes against G7-15's limit (duty 7). §7 (1) and OQ7-2 aligned with CORRECTION-007. The full text of `0008` (§5.1), not executed |
| 5 | `33434a8` | the review of `38281ab` recorded: the text of `0008` (parts E, A, B, C, D2) approved; step 1 authorized; no other change |
| 6 | `7e8993d` | the review of step 1's progress report recorded; step 1 delivered (`SLICE_7_STEP1_DELIVERY.md`); the status and §8 updated; no decision, and no text of `0008`, changed |
| 7 | `fe27c67` | the review of `7e8993d` recorded: step 1 CLOSED, step 2 authorized, D2's reading of R14.6 accepted for the six keys only, the Slice 5 race test's remedy (b) applied; G7-16 added: six points of step 2 put as decisions, and CORRECTION-006's reading |
| 8 | `921a1d7` | the review of `0f423d2` recorded: G7-16 decided as recommended; CORRECTION-006's reading approved; one sentence of G7-16 (vi) corrected to RFC-001 R5.3b |
| 9 | `f7e5297` | step 2 delivered (`SLICE_7_STEP2_DELIVERY.md`); CORRECTION-006's text submitted; §8 updated; no decision changed |
| 10 | `f21a113` | the review of `f7e5297` recorded: CORRECTION-006 approved; R5.3b and INTERNAL_MESSAGE_REF_NOT_ACCEPTED accepted; readings 1–5 accepted; R-S7-2-01 measured, reading 6 corrected |
| 11 | `af61400` | the review of `6d8815d` recorded: step 2 CLOSED, step 3 authorized (no real event before R-1); the two stale statements corrected |
| 12 | `bf1fe3d` | G7-17 added: seven points of step 3 put as decisions, each with a recommendation; no other change |
| 13 | `e64ba93` | the review of `bf1fe3d` recorded: G7-17 decided, a 503 `WEBHOOK_NOT_READY` (CORRECTION-008) for a missing secret, `response_additions` unique per (operation, status), R-1 duty 5 extended to the 503 |
| 14 | `5e152ff` | the review of `3dfb717` recorded: a T1 that raised is CORRECTION-008's 503, whose meaning is widened to "acceptance not confirmed"; CORRECTION-007's narrowed to "the processing's result not confirmed"; `archived_at` read; the stale statements corrected: the introduction (no webhook yet), "the interaction" among T2's writes (G7-2 (iv), its test 1, §3.1, §6.1), CORRECTION-007's meaning (G7-2 (v), §5.2), the 500 "for no operation" (§5.2), the two corrections of §7 (1) |
| 15 | `23b99b6` | the review of `34d6122` recorded: T1 and T2, the 400 codes and `archived_at` accepted; CORRECTION-007 §1 and an unbounded `int()` of `Content-Length` to answer; both answered (`SLICE_7_STEP3_DELIVERY.md` §9) |
| 16 | `bc334f8` | the review of `23b99b6` recorded: step 3 CLOSED, CORRECTION-007 and CORRECTION-008 approved, step 4 authorized; a pointer at G7-17 (vi) to CORRECTION-007's later meaning |
| 17 | `e18271a` | G7-18 added: nine points of step 4 put as decisions, each with a recommendation; measured facts of the schema stated; no other change |
| 18 | `e1bdcbc` | the review of `e18271a` recorded: G7-18 decided, the nine options (a), with limits; no 0009; the link valid at its writing only |
| 19 | `2f968f4` | the review of `a659587` recorded: step 4 not closed; R-S7-4-01 (the backfill's isolation) and the stale introduction of `services/communication.py`; both answered (`SLICE_7_STEP4_DELIVERY.md` §10) |
| 20 | `ef9e248` | the review of `2f968f4` recorded: step 4 CLOSED; step 5 authorized |
| 21 | this revision | G7-19 added: three points of step 5 put as decisions (the event store's counts, the decided writes, what is never PASS); two test gaps stated; no other change |

**The review of `2f968f4`. Step 4 is CLOSED at `2f968f4`; step 5 is
AUTHORIZED within the approved plan.** Slice 7 stays open.
- **What the reviewer read:** R-S7-4-01's measurement, which shows the
  duplication under REPEATABLE READ before the fix; the code, where
  `audited_transaction` sets the isolation before the transaction's
  statements and the backfill imposes READ COMMITTED, then checks the
  actual level before writing; the tests (a connection defaulting to
  REPEATABLE READ, the second backfill's wait, the re-run, the refusal when
  the imposition is absent); the corrected introduction of
  `communication.py`.
- **What the reviewer checked:** the commits after the fix at `f075ab8`
  change nothing in `src`, `tests` or `db`.
- **What the reviewer did not do:** re-run the 3091 tests, the 33/33
  mutations or the gate. The results are the implementing team's.
- **The decision's limits stand:** one interaction per message within the
  service's paths and the backfill; a confirmation link valid at its
  writing only.
- **Standing:** R-1 is a condition before any real event; K06 is UNPROVEN;
  the scope is SALE only. This is not a release authorization.

**The review of `a659587`. Step 4 is delivered and NOT closed.** The
reviewer read the diff, the code and the delivery note; the recorded results
(3088/3088, 31/31 twice, the gate) are the implementing team's, not re-run.
- **Accepted:** the four 422 codes; the removal of `MESSAGE_TYPE_RESERVED`;
  the maintenance of step 2's and Slice 5's tests, within the limits the
  note states.
- **The blocker, R-S7-4-01, the backfill's isolation.** The backfill says
  READ COMMITTED, but its script connects at the server's default, and
  `audited_transaction` sets no level for it; no test checks the level it
  runs under. Under REPEATABLE READ, a second backfill could keep a
  snapshot from before its lock wait, not see the first's interactions,
  and, with no unique constraint, write them again. The reviewer states
  this as inferred from the code, not measured; PostgreSQL 16 documents
  that READ COMMITTED takes a snapshot per statement and REPEATABLE READ one
  per transaction. **Asked:** measure the concurrent order under REPEATABLE
  READ first; then make the backfill impose READ COMMITTED, or refuse
  explicitly to run otherwise, with a test of the actual level and of a
  re-run without duplicates.
- **Also:** correct the introduction of `services/communication.py`, which
  still says the two types are reserved and that `metadata` holds
  `content_archived` only.
- **Then:** the evidence round bound to the resulting tree's fingerprint.
- **Standing:** step 5 awaits the review of the answer; R-1 is a condition
  before any real event; K06 is UNPROVEN; the scope is SALE only.

**The review of `e18271a`. G7-18 is DECIDED: the nine options (a), with the
limits below. Step 4 may be implemented accordingly.** The diff since
`334a2f0` is documentary. The reviewer did not re-run the database
measurements or `bound`.

| Point | Decision |
|---|---|
| (i) the interaction's type | `NOTE` for every INTERNAL; the other directions follow the thread's channel as in the table, with `OTHER` for WEB and OTHER. |
| (ii) the summary | the three proposed fixed texts, with no body and no reference. |
| (iii) the columns | the thread's links, the message's time, the actor, and `metadata.message_id` alone, as detailed. |
| (iv) one interaction per message | guaranteed by the message writers and the backfill, **within the service's paths**. The backfill and its lock run under READ COMMITTED; its re-run and its concurrency are tested. **It is not described as a uniqueness constraint of the database; `0009` is not authorized by this decision.** |
| (v) the backfill | the proposed operator's script, with the statement that a message's atomicity with its interaction does not apply retroactively to the earlier messages. |
| (vi) the timeline | the `message` key on message items only, with the keys and the withholding specified. REVIEWER reads archived content within the operation's existing roles. The other items' keys stay as they are. |
| (vii) the confirmation link | the `metadata` exception with its two ids for this type only; `observed_at = NULL` refused; the checks, locks and four 422 codes as proposed. **The link's validity is established at its writing only:** 0007's guard does not protect an observation a message names, so neither the observation's survival nor its stability afterwards is claimed, and the link has no legal value. |
| (viii) an inbound message of either type | the delivered webhook's behaviour stays; an inbound message gains no meaning of a phone decision, and is not accepted as one to link. |
| (ix) the writers' inventory | by kind in step 4's delivery; STOP GATE E stays the record of Slice 5's tree. |

- **What step 4's tests must prove:** the exact keys of the item, and the
  withholding of unarchived content, for each of the three roles; the
  link's refusals before any write or idempotency key is consumed; the
  backfill run concurrently and re-run. These are conditions of proof, not
  a claim that the tests ran.
- **Standing:** Slice 7 stays open; R-1 is a condition before any real
  event; K06 is UNPROVEN; the scope is SALE only. This decision is not a
  release authorization.

**The review of `23b99b6`. Step 3 is CLOSED at `23b99b6`; CORRECTION-007
and CORRECTION-008 are APPROVED as delivered there; step 4 is AUTHORIZED
within the plan's scope.** Slice 7 stays open.
- **What the reviewer read:** the diff from `34d6122`, the webhook's route,
  CORRECTION-007's text, the `Content-Length` tests and their measurement
  record.
- **What the closure rests on:**
  - the 500 describes an event stored **whose processing's result is not
    confirmed to the sender**; the 503 does not claim the event's
    acceptance is confirmed;
  - the new comparison drops leading zeros before converting a number of at
    most six digits; the tests cover the refusal before the body is read,
    and a small size written with long zeros.
- **What the reviewer did not do:** re-run the 3027 tests, the 68/68
  mutations or the PostgreSQL gate. They are the implementing team's
  results, bound to the tree.
- **A documentary note, not blocking:** the decision table at G7-17 (vi)
  still shortens the 500 to "processing failed". A pointer from that place
  to the meaning later approved is added in this revision, without
  rewriting the decision.
- **Standing:** R-1 is a condition before any real event is received; K06
  is UNPROVEN; the scope is SALE only. This closure is not a release
  authorization.

**The review of `34d6122`. Step 3 is NOT closed, and CORRECTION-007's text
is not approved as it stood.**
- **Accepted:** the handling of T1 and T2 as intended (the three tests, each
  redelivery without a second message); the two 400 codes; the stated
  reading of `archived_at`. The reviewer did not re-run the 3005 tests or
  the mutations: they are the implementing team's results.
- **Two reasons:**
  1. **CORRECTION-007 §1** kept "T2 did not process it" and "the event kept
     its status", false for `PROCESSING_LOST`, which §3 admits may have
     committed. Correct the introduction to "the result of the processing is
     not confirmed to the sender", and make "no operation has a 500" a
     description of the contract before the correction. CORRECTION-008's
     text is accepted in meaning: its 503 asserts neither that T1 is
     recorded nor that it is not.
  2. **`_read_limited`** checks that `Content-Length` is numeric, then calls
     `int(declared)`. The reviewer showed that `int('9' * 5000)` raises
     `ValueError` in the current Python, a documented CPython limit; such a
     header, reaching the route, would bypass the decided 400 and its
     record. **Measure first whether it reaches the route through HTTP or
     ASGI;** then compare with 65536 without an unbounded conversion, and
     test a 400 without reading the body or writing a row, and long leading
     zeros, so a small size is not wrongly refused.
- **Then:** the evidence for the resulting tree, and the delivery for
  review.
- **Standing:** step 4 not started; R-1 a condition before any real event;
  K06 UNPROVEN; the scope SALE only.

**The review of `3dfb717`. Step 3 is NOT delivered and NOT closed.** The
numbers (119 tests, 64 mutations) are the implementing team's; the reviewer
did not re-run them.
- **Accepted:** the two 400 codes, `WEBHOOK_BODY_TOO_LARGE` and
  `WEBHOOK_ENVELOPE_NOT_VALID`; their details name fields, never a value of
  the request.
- **The blocker:** a T1 that raised was answered `500 INTERNAL_ERROR`, while
  CORRECTION-007 gives the same operation a 500 with the fixed code
  `WEBHOOK_PROCESSING_FAILED` and a description that presumes the event is
  recorded. One status may not carry both meanings in the effective
  contract.
- **The decision:**
  - **a T1 that raises, after the request's checks passed, is answered
    `503 WEBHOOK_NOT_READY`.** CORRECTION-008's description is widened to
    "the event's acceptance could not be confirmed; deliver it again with
    the same identifier". With a missing secret, nothing is written, and that
    is known; with a connection lost during the COMMIT, it may not be
    asserted. The reviewer cites PostgreSQL 16's documentation, which names a
    client disconnected while a COMMIT is in progress, and the need to
    determine whether the transaction committed;
  - **the same care for T2:** after T1 committed, CORRECTION-007's 500 stays
    the signal to redeliver, but its description and detail say that **the
    result of the processing is not confirmed to the sender**. The note
    tells a FAILED event actually recorded apart from `PROCESSING_LOST`. A
    redelivery with the same identifier decides both through the event's
    record;
  - **three tests:** T1 failing before its COMMIT; T1's COMMIT succeeding and
    its answer lost; the same after T2's COMMIT. Each answer is retryable,
    and no second message is made;
  - **`archived_at`** adds, alone, no rule of refusal: the thread is resolved
    by its reference and the consent checked as they are; this reading is
    recorded and tested, without changing how archiving is marked;
  - **the stale statements of this plan** are corrected in this revision.
- **Then:** after this answer and an evidence round bound to the tree, step
  3 may be delivered for review.
- **Standing:** R-1 is a condition before any real event; K06 is UNPROVEN;
  the scope is SALE only.

**The review of `bf1fe3d`. G7-17 is DECIDED; step 3 may be implemented.** The
recording of step 2's closure is correct.
- **What the reviewer did:** read the texts and the code; re-ran no test.
- **The decisions:**

| Point | Decision |
|---|---|
| (i) the interaction | **(a):** step 3 writes none. **In step 4:** one row is created for every message that exists before it, with no duplicate on a re-run of the backfill; then the row is written with every new message, in the message's own transaction. **State explicitly** that the atomicity with the message's creation does not apply retroactively to the old rows. |
| (ii) the signature and the secret | `sha256=<64 lowercase hex>`, an HMAC over the raw body bytes, the secret from `TURAB_RELAY_SIGNING_SECRET` encoded UTF-8, compared in constant time. A missing or wrong signature is **401**. **A missing or empty secret is not an authentication fault of the relay:** its answer is **503**, before any write, with the fixed code `WEBHOOK_NOT_READY`, and the fault logged without the request's body. |
| (iii) the order of the checks | **(a):** the size, then the signature, then the envelope, then the keys of a known type, all before T1. The time must carry a zone. An unknown type is stored, then IGNORED, as the plan says. |
| (iv) the codes | **(a):** the proposed IGNORED list, and `PROCESSING_FAILED` for FAILED, with no exception text. |
| (v) the 200 | an empty body, for every case named. |
| (vi) the contract correction | the `response_additions` mechanism with its proposed controls, **its uniqueness per pair (operation, HTTP status)** rather than one entry per operation. **CORRECTION-007** stays the 500, which means the event is recorded and its processing failed. *(Revision 16, a pointer only, the decision left as it was: the meaning later narrowed in the review of `3dfb717` and approved in the review of `23b99b6` is "the event is stored; the result of its processing is not confirmed to the sender"; see CORRECTION-007.)* **CORRECTION-008** is added, the 503, which asks for a redelivery without claiming the event is recorded. **R-1 must test the redelivery on 500, on 503 and on a timeout.** The two corrections' texts, and the resulting contract, are delivered with step 3. |
| (vii) the audit | **(a).** The access auditor sends a record to the log stream, not to `audit_log`, so it can record a 400/401/503 refusal without breaking "nothing written to the database". **One record per answer**, with no body, signature or secret. The message's insert and the thread's actual move are audited by `audit_rows` with a NULL actor, without copying the content or auditing the webhook event twice. |

- **Two tests asked for, pinning the two limits this decision changes:**
  - a 503 when the secret is absent, with no event row;
  - the one-time backfill of the earlier messages' interactions, in step 4.
- **Standing:**
  - **R-1 is a condition before any real event is received;**
  - K06 is UNPROVEN;
  - the scope is SALE;
  - this is not a release authorization.

**The review of `6d8815d`. Step 2 is CLOSED at `6d8815d`; step 3 is
AUTHORIZED, in the approved plan. Slice 7 stays open.**
- **R-S7-2-01 is closed.** What it rests on:
  - the three tests use the two real HTTP commands, witness the wait with
    `pg_blocking_pids`, and check the responses, the rows and both
    idempotency keys, in both orders (the message first; the binding first,
    committed or rolled back);
  - the record keeps 15/15 cases in five runs;
  - the reviewer compared the code before and after the change: past the
    docstring of `communication.py`, it is identical. The account of the
    behaviour and the tests changed; the service's logic did not.
- **Read by the reviewer:** the run's binding record and the two mutation
  records (2849 tests passing; 51 mutations failing in each run, the same
  mutations and failing tests in both).
- **What the reviewer did not do:** re-run the suite or PostgreSQL. The
  results are the implementing team's.
- **CORRECTION-006's approval stands,** as decided in the previous review.
- **Two stale statements, corrected with this revision.** The correction is
  documentary, and does not suspend the closure:
  - §4 of the step 2 delivery said CORRECTION-006 carried no approval date;
  - this plan's introduction said the slice's code was step 1's only.
- **Standing:**
  - step 3's authorization does not allow receiving real events before R-1
    is met;
  - K06 is UNPROVEN, an independent condition before the release gate;
  - the approved scope is SALE only.

**The review of `f7e5297`. Step 2 is NOT closed, and step 3 is not
authorized, for one gap: R-S7-2-01.**
- **What the review did not do:** re-run the tests or PostgreSQL. 2846/2846,
  51/51 and the gate are the implementing team's results.
- **Decided:**
  - **CORRECTION-006's text is APPROVED.** `party_id` is required and not
    null in the effective body; the frozen component is unchanged;
  - **accepted:** the recorded 403 `OBJECT_NOT_AUTHORIZED` for an unknown
    thread on the staff path, and the code 422
    `INTERNAL_MESSAGE_REF_NOT_ACCEPTED`;
  - **accepted:** the first five readings of the delivery's §3, as decisions
    for this scope:
    - the provider only when a reference is given;
    - `body_text=""` is content, needing consent;
    - the request's and the property's rules applied together;
    - only the buyer for an opportunity without a current offer;
    - no particular status of the opportunity required.

    They are not a widening of an opportunity's sharing authority.
- **R-S7-2-01, the sixth reading.**
  - **What it said:** the binding table has no foreign key to the thread, so
    a message does not wait for an uncommitted binding.
  - **What the review read:** the frozen schema defines
    `fk_consent_binding_thread`, and the binding command inserts
    `thread_id`. FOR UPDATE conflicts with FOR KEY SHARE (PostgreSQL 16 lock
    table). Hence "binding inserted and uncommitted, then the message" may
    make the message wait and see the result under READ COMMITTED: the
    reverse of the reading. This was inferred, not measured.
  - **What it asked:** measure, through the two real HTTP commands with a
    `pg_blocking_pids` witness, both orders:
    - the message holding the thread, then the binding;
    - the binding inserted and uncommitted, then the message, with the
      binding committed and rolled back.

    Prove the response, the rows and the idempotency key; correct the reading
    and the service's comment by the result; and, if the change is tests and
    documents only, bind the evidence round to the new tree.
- **Answered** in `SLICE_7_STEP2_DELIVERY.md` §9: **the inference is
  confirmed.** The reading and the comment are corrected; no behaviour
  changed.
- **Standing:**
  - step 1 stays CLOSED, and Slice 7 is open;
  - R-1 is a condition before real traffic;
  - K06 is UNPROVEN;
  - the scope is SALE only.

**The review of `0f423d2`. G7-16 is DECIDED, as recommended, and
CORRECTION-006's reading is APPROVED. Step 2 may be implemented in full.**
- **The Slice 5 race test's maintenance (remedy (b)) is ACCEPTED.**
  - **What it rests on:** the waiting witness, and the check that the
    binding does not complete while the share is held, both remain. The
    mutation records show W1–W4 still detected.
  - **What it does not show:** twenty runs under load without a failure are
    not taken as a guarantee that all flakiness is gone.
  - **What the reviewer did not do:** re-run the 2741 tests, the 51
    mutations or the gate. They are our runs, bound to the tree.
- **G7-16, decided:**

  | Point | Decision |
  |---|---|
  | (i) | INBOUND in the staff command is refused, 422 `DIRECTION_NOT_ACCEPTED`. Inbound comes from the webhook; a phone conversation is recorded as INTERNAL. |
  | (ii) | An OUTBOUND message keeps the `delivery_status` it states, default UNKNOWN. INTERNAL accepts only an absent field or UNKNOWN; otherwise 422 `DELIVERY_STATUS_NOT_ACCEPTED`. |
  | (iii) | The staff command accepts `metadata` absent or an empty object only. Any key is refused, 422 `MESSAGE_METADATA_NOT_ACCEPTED`. The service writes G7-9's keys itself. |
  | (iv) | `last_message_at` is set to the later of its value and `occurred_at`, in the message's transaction. **The thread row is locked `FOR UPDATE` before the message is inserted**, in both the staff path and the webhook path. Tested with two concurrent messages of different times. |
  | (v) | `PHONE_DECISION` and `CONFIRMATION_LINK` are reserved for step 4, and refused now, 422 `MESSAGE_TYPE_RESERVED`. |
  | (vi) | The refusal names and their statuses are adopted as G7-16 gives them, among them `THREAD_REF_NOT_SCOPED`, `OPPORTUNITY_NOT_SALE`, `THREAD_LINKS_INCONSISTENT`, `LINKED_RECORD_NOT_FOUND` and `MESSAGE_REF_TAKEN`. **`field_errors` carry no row id and no database text.** |
- **CORRECTION-006: the proposed method is approved.**
  - **What step 2 does:** write the text that narrows `party_id`.
  - **What the delivery carries:** that text, the effective contract, and
    the test that the two agree, as for CORRECTION-005.
  - **What remains to approve:** this authorizes step 2 in full. The
    correction's text, and the results of the execution, are approved when
    the delivery is reviewed.
- **One sentence of G7-16 (vi) corrected, by us, before any code** (revision
  8):
  - **Our sentence:** "The 404 is kept for the path's thread."
  - **Why it is wrong:** it contradicts RFC-001 R5.3b, which decides that "staff object checks that fail
    return `403` with `OBJECT_NOT_AUTHORIZED`" and are recorded, as every
    staff command does (`authorize_task_exists`, `authorize_match_exists`).
    The RFC takes precedence over a sentence of the plan.
  - **What step 2 does:** an unknown `thread_id` in the path is 403
    `OBJECT_NOT_AUTHORIZED`, with the denial recorded.
  - **What is unchanged:** `LINKED_RECORD_NOT_FOUND` (422) for an id in the
    body, which is an input check, not an object check.
  - **Put to the reviewer** with the delivery, and not assumed accepted.
- **Standing:**
  - step 1 stays CLOSED at `7e8993d`, and Slice 7 is open;
  - R-1 is a condition before any real traffic;
  - K06 is UNPROVEN, an independent condition before the release gate;
  - the approved scope is SALE only.

**The review of `7e8993d`. Step 1 is CLOSED at `7e8993d`; step 2 is
AUTHORIZED, in the plan's sequence. Slice 7 is not closed.**
- **What the closure rests on:** the reviewer read the migration, its tests,
  the delivery and the evidence records:
  - the suite, 2741/2741;
  - the two mutation runs;
  - the gate.

  The reviewer also checked that the difference after the mutations' tree
  `7eedd77` is documents and evidence only. **The reviewer did not re-run
  PostgreSQL, the suite or the mutations.** The numbers are the
  implementing team's, bound to the tree.
- **D2 and R14.6: the implementation's reading is ACCEPTED, in this case
  only.**
  - **Why:**
    - decision D2 named the change of the six frozen foreign keys, and the
      migration text that makes it was then approved;
    - `schema_v0.2.3.sql`, and its application by `0001`, are unchanged;
    - each change is a declared delta, with its digests before and after.
  - **What follows:** it is an approved evolution on top of the baseline,
    under the distinction of `MIGRATION_POLICY.md` §1a and §4. No new
    official handoff package is required for these six.
  - **What it does not cover:** a correction of the baseline file itself.
    `MIGRATION_POLICY.md` §4 records this (revision of `7e8993d`'s review).
- **The Slice 5 concurrency test: remedy (b) chosen.**
  - **What is removed:** `share_committed_first`, which compared the return
    times of the two HTTP responses.
  - **What is kept:**
    - the `pg_blocking_pids` witness;
    - the assertion that the binding did not complete while the share was
      held;
    - the final result.
  - **What the measurement shows, and does not:** 9/20 against 3/20 under
    load shows the failure exists before `0008`. It does not show that the
    two trees fail at the same rate, and that is not concluded.
  - **How it is done:** as a maintenance change of known effect, with the
    new tree's evidence bound to it. It does not delay `0008`'s closure.
- **Standing:**
  - R-1 unmet for real traffic;
  - K06 UNPROVEN;
  - the SALE scope unchanged.

**The review of step 1's progress report (after `dc35b50`). Step 1 is NOT
closed by it.**
- **What it read:** a progress report, not a delivery. B6 had survived the
  first mutation run, and a test was then added for it, but the two final
  runs had not been shown. A full run had failed one Slice 5 concurrency
  test, and its ten passes alone "do not by themselves prove the failure is
  incidental".
- **What the delivery must show:**
  - the full suite on the final tree;
  - both runs of the 77 mutations;
  - the state of that concurrency test;
  - the state of the database after a downgrade that `0007` refuses.
- **What it could not check:** `dc35b50` returned 404. It had not been
  pushed. The review ran no test.
- **What stands:** the approval of `0008`'s text, and the authorization of
  step 1.
- **Where each point is answered** (`SLICE_7_STEP1_DELIVERY.md`):
  - the suite: §6, 2741 passed, 0 failed, at `f9df6ab`;
  - the mutations: §4, 77/77 twice, identical, at `7eedd77`;
  - the concurrency test: §6.1. It fails under load on `582b522`, which has
    no Slice 7 code, and the cause is in the field it measures. The test is
    unchanged, and a remedy is proposed;
  - the refused downgrade: §2.6, a new test asserting the database's state;
  - every commit is pushed.

**The review of `38281ab`. The text of `0008` is APPROVED, parts E, A, B, C
and D2, and step 1 is AUTHORIZED, in the plan's sequence.**
- **What is approved:** the proposed text and its testing. "The migration has
  not been run yet, so I do not count the guards as proven by execution."
- **The two gaps are closed:**
  - **the thread's identity:** part E enforces the reference's form and a
    partial unique index for WHATSAPP threads, after checking the existing
    violations, so resolving an inbound message finds zero or one thread
    within the defined scope. Proving that the business number's and the
    customer's identifiers are extracted from Meta's notification stays
    within R-1, before any real traffic;
  - **the delivery status:** part B refuses UNKNOWN → FAILED, in agreement
    with G7-5's table and the test list. A provider's status of that kind
    stays an IGNORED event, with the reason the plan states.
- **Also matched by the reviewer:** the recording of D2, CORRECTION-007 and
  (a2) with R-1; §7 (1); OQ7-2's status.
- **Not checked by the reviewer:** that the local and remote heads of the
  branch match. M1–M8 were not re-measured, and no SQL was run.
- **How step 1's delivery is judged:** by running the migration and its
  tests, in particular:
  - the refusal of old non-conforming data;
  - the race on one reference;
  - the status transitions;
  - the six keys and their guard;
  - the downgrade.
- **Step 2 does not start** before step 1's delivery is reviewed.
- **Carried:**
  - R-1 stays unmet for real traffic;
  - K06 stays UNPROVEN, an independent condition before the release gate;
  - this approval does not widen the approved SALE scope.

**The review of `4aed49b`. The four points are accepted as directions. The
text of `0008` is not approved, and step 1 does not start, for two gaps in
that text.**
- **What the reviewer checked:** the diff `58a0067..4aed49b`, documentary
  only; revision 3; and `0008`'s text against the frozen schema.
- **Decided:**

  | Item | Decision |
  |---|---|
  | **G7-12 (D)** | **D2**: the strict guard, and the six keys made `RESTRICT`, with the consequences for deleting a party or an account, and the limit on erasure requests, as worded. D3 is not chosen |
  | **A failure of the webhook's processing** | **CORRECTION-007**: `500 WEBHOOK_PROCESSING_FAILED` once the event is stored and its processing failed, with redelivery under the same identifier. The savepoint path and the FAILED record are accepted. A failure of the COMMIT or of the connection leaves the previous status, as worded. A savepoint keeps the writes made before it, and rolling back to it undoes what followed (PostgreSQL 16, `SAVEPOINT`) |
  | **Meta's boundary** | **(a2), with R-1 a condition required before any real event.** TURAB's test proves the relay's signature only. The relay's verification of Meta stays unproven in the slice's evidence until the relay is built and its five duties are tested |
  | **G7-4** | `whatsapp` for the WHATSAPP channel; the external reference refused in every other channel; the three CHECKs and the channel guard as proposed |
  | **The other directions** | the recommended options are accepted as the plan's basis, G7-8 (a), G7-9 (a) and G7-15's 64 KiB among them, **provided the size of the relay's real envelopes is tested within R-1** before real traffic. "This is an approval of the directions, not of the defective migration text below" |
- **What stops `0008` now:**
  1. **The thread reference is not unique.**
     - G7-3 resolves an inbound message by `external_thread_ref`, but
       `communication_threads` does not make it unique, and `0008` adds no
       constraint on it. Two WHATSAPP threads can then share a reference,
       and the message's party is undetermined.
     - **Asked for:** an explicit identity rule. The reviewer recommends a
       partial unique index for WHATSAPP when the reference is not NULL,
       with existing rows checked and two concurrent inserts tested.
     - **R-1 must define the reference's scope** if the relay serves more
       than one WhatsApp account or number: an index on a reference of
       undefined scope is not enough.
     - The reviewer cites PostgreSQL 16, §11.6 "Unique Indexes".
  2. **The delivery-status transition contradicts itself.** G7-5 accepts
     FAILED from QUEUED or SENT. But part B's SQL accepts UNKNOWN → FAILED,
     because its `OLD.delivery_status = 'UNKNOWN'` branch comes before any
     restriction. Restrict UNKNOWN to the non-FAILED statuses, and test that
     the intended transitions are accepted and this one refused. If allowing
     it was intended, change G7-5 explicitly, rather than letting the
     trigger decide it silently.
- **A documentary alignment with CORRECTION-007:**
  - §7 (1) still says the contract changes only by CORRECTION-006;
  - CORRECTION-007's status in the open questions must be updated.
- **Asked for:** a short revision that fixes the thread reference's identity
  and removes the UNKNOWN → FAILED contradiction, with the resulting text of
  `0008` in full. Then the reviewer reviews approving the migration and
  starting step 1.
- **Not run by the reviewer:** the migration and the tests. M1–M8 remain
  the implementing team's results.
- **K06** stays UNPROVEN, an independent condition before any release gate.

**The review of `58a0067`. Step 0 is accepted as measurement documented by
the implementing team. The decisions and `0008` stay unapproved, for four
reasons.**
- **Not re-run by the reviewer:** step 0's measurements.
- **The five gaps of the review of `dcebe46`** are addressed by the text.
- **Directions accepted, limits to be proven by the implementation's
  tests:**
  - G7-8 (a): reading a message through the timeline;
  - G7-9 (a): the content-free event payload, and content stored only under
    consent.

  "Recovering an event from the content-free payload, without its content,
  is a correct and stated limit, so it is not counted as a full recovery of
  the archive."
- **The four points:**
  1. **G7-12 (D1).** `pg_trigger_depth() > 1` shows that triggers are
     nested, not that the update comes from a foreign key. The plan says so,
     yet names the option "FK-only" and calls the links frozen. A nested
     update may come from a trigger on any table that updates the thread.
     **D1 is not approved as described.** Revision 3 offers an explicit
     choice between D2, with the consequences of refusing the deletion of
     referenced rows, and a narrower guarantee worded with its exact limits.
     The reviewer cites PostgreSQL 16, §9.26 System Information Functions.
  2. **G7-2: a failure between the two transactions.** A failed SQL
     statement aborts the processing transaction, which then cannot commit
     a status update as it stands.
     - State where the rollback or savepoint is, and which transaction
       records the failure.
     - Test the stop after RECEIVED is committed.
     - The typed 500 is not among the operation's responses in the effective
       contract. Offer an explicit contractual settlement, rather than
       inferring its permission from the general error rule.
  3. **G7-2 (a2).** A relay outside the slice may be accepted as a defined
     integration boundary, but Meta's verification is not counted as done in
     the slice's evidence. If (a2) is chosen, building the relay and testing
     the GET verification, Meta's signature and the redelivery of failures
     become an independent condition before any real event is received.
  4. **G7-4.** State the fate of `external_message_ref` in a thread that is
     not WHATSAPP. The text sets `provider = whatsapp` for one channel,
     while the staff command accepts others. Either a known provider for
     each defined channel, or the reference refused in channels with no
     defined provider, before `0008` (A) is approved.
- **Then:** revision 3, with the proposed text of `0008` and the four points
  settled, without implementation code.
- **K06** stays UNPROVEN, an independent condition before any release gate.

**The review of `dcebe46`. The plan is accepted as a basis for review and
measurement; G7-1 to G7-14 and the text of `0008` are not yet approved.**
- **Step 0 authorized,** in four terms:
  - M1–M7, on a temporary database, with rolled-back transactions where
    needed, and no implementation code;
  - M7's envelope is named a **synthetic sample** until G7-2 decides who
    produces it;
  - **M8 added:** what happens to `ON DELETE SET NULL` if `0008`'s proposed
    guard forbids changing a thread's links, since "the two statements in
    the plan may not both hold".
- **Required before revision 2 is put up for approval:**
  1. **Content and consent.** G7-9 drops `body_text` and `media_ref` without
     archive consent, but G7-2 stores `webhook_events.payload` before
     processing, and the payload may carry the same text or media. State
     what the payload and `metadata` keep, and how the consent condition
     actually holds. "Deferring retention to OQ7-1 is not enough if the
     payload stores the content in the first place."
  2. **The stuck event.** A RECEIVED event may stop before the second
     transaction. A replay of any recorded event, FAILED included, answers
     200 without reprocessing, and there is no recovery command. Settle the
     fate of RECEIVED and FAILED, and their recovery, before G7-2 is
     approved.
  3. **Meta and the relay.** The reviewer cites Meta's official
     documentation:
     - a GET carrying `hub.challenge` and `hub.verify_token`;
     - notifications signed in `X-Hub-Signature-256`;
     - a native payload of `object` and `entry[].changes[]`.

     If the relay is chosen, define who verifies Meta's signature before the
     transformation, who signs TURAB's envelope after it, and where the GET
     lives. The transformed envelope's signature proves the relay's origin,
     by its key. "It may not be described as a direct verification of Meta's
     signature on the transformed envelope."
  4. **Readability of the archive.** The plan says a message's content has
     no read operation, then proposes a timeline entry with a fixed summary
     and no body. State what "retrievable" means within the slice, and what
     a staff member can actually read, "without silently widening the
     contract".
  5. **The SALE boundary.** Bound the statement that every linkable
     opportunity "is SALE" to what the approved path creates, as Slice 5's
     record does, or make the opportunity's type an explicit check in the
     thread service. "We do not infer that a directly inserted row is
     impossible while K06 is unproven."
- **Not a run by the reviewer:** this is a review of the plan and the
  sources, not an independent run of the PostgreSQL measurements.
- **K06** stays an independent condition before any release gate.

---

## 0. What this slice is, and what it is not

### 0.1 The scope, as the approved slices document states it

`docs/handoff/06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md`, "Slice 7 —
Communication / WhatsApp Record":

> **Objective:** Centralize operational communication history without
> building a full proprietary chat platform.
>
> **Deliverables:**
> - communication threads and messages.
> - interaction timeline.
> - official WhatsApp Business integration boundary.
> - provider event replay store.
> - delivery/read status.
> - staff notes and important confirmation linkage.
>
> **Mandatory tests:**
> - repeated provider webhook creates one message.
> - same provider message id cannot be inserted into another thread.
> - thread/opportunity links are checked by service invariant.
> - phone decision can be linked to later written confirmation observation.

The same scope is restated, in agreement, in three places:
- Developer Handoff Master v1.0.3 §8;
- the Developer Reference Spec §18;
- `API_CONTRACTS_v0.2.md` §4.12.

### 0.2 What it is not

- **Not a chat platform:** no inbox, no unread counters, no real-time
  delivery (the objective; the Spec's §2 table: "Native chat between users —
  deferred").
- **No AI.**
- **No customer access.** The contract gives no customer role on any
  communication operation (§1).
- **No change to matching, review, opportunities or tasks.**
- **No RENT** (G4-5R open). *(Revision 2, review of `dcebe46`, point 5.)*
  The currently approved matching and approval path creates SALE
  opportunities only. That does **not** prove that no other opportunity row
  can exist, the more so while K06 is UNPROVEN: a direct insert is not shown
  impossible. So the thread service **checks** the type of a named
  opportunity (G7-6, rule 0); it does not assume it.
- **No legal-evidence claim:** phone decisions are stored "as operational
  records" (`API_CONTRACTS` §4.12; the Spec's §18).

### 0.3 Carried from Slice 6, unchanged (`SLICE_6_CLOSURE.md` §1)

Slice 6 is CLOSED at `ce8cfa0`, SALE only, not a release authorization. Its
limits travel with this slice as they were given:

| Limit | Its bearing on Slice 7 |
|---|---|
| **K06 UNPROVEN** (G6-12; EN-02). **Its remedy is an independent condition before any release gate.** | Measured again: the connecting role is a superuser, and every UPDATE and DELETE on the four communication tables is accepted (M3). Every guard Slice 7 proposes (G7-12) is proven **at trigger level only**, and is labelled so |
| **G4-5R open:** SALE only | §0.2; G7-6, rule 0 checks the type |
| **OQ6-1 and OQ6-2 open** | Untouched |
| **The replay limits of the diagnostic** (its own `input_hash`; `explain.blocker_summary` not pinned) | Untouched; restated as carried in Slice 7's closure evidence |
| **The stored-titles inspection** (F6-22) | Untouched; carried as an operational condition |
| **F6-21:** R9.3 binds what a slice generates | Slice 7 copies no match, offer or permission snapshot into a communication record (§3.8) |
| **Relations are never an authorization source** | G7-6 does not read relations as a reason for a link |
| **EN-01 to EN-03** | They apply to every run |
| **STOP GATE E is the record of Slice 5's tree** | M6: a second writer of `interactions` makes its `--check` report it (F7-7, G7-8) |

---

## 1. Operations

Every Slice 7 operation in the effective contract
(`docs/api/openapi_effective_v0.2.3.yaml`, tag `Communication`):

| operationId | Method, path | Roles | Idempotency | Today | Slice 7 |
|---|---|---|---|---|---|
| `postCommunicationThreads` | POST `/communication/threads` | ADMIN, OPERATOR | `Idempotency-Key` | **no route** | **7** |
| `postCommunicationThreadsThreadIdMessages` | POST `/communication/threads/{thread_id}/messages` | ADMIN, OPERATOR | `Idempotency-Key` | **no route** | **7** |
| `postWebhooksWhatsapp` | POST `/webhooks/whatsapp` | **none: unauthenticated**, one of the closed list of six (RFC-001 R10.4) | provider event identity (`API_CONTRACTS` §2.3) | **no route** | **7** |
| `getPartiesPartyIdTimeline` | GET `/parties/{party_id}/timeline` | ADMIN, OPERATOR, REVIEWER | — | routed (Slice 1); reads `interactions` only; items are `additionalProperties: true` | **read; its allow-list is widened only if G7-8 decides it** |

**The bodies:**
- **`CommunicationThreadCreate`** requires `channel`. `party_id`,
  `request_id`, `property_id` and `opportunity_id` are optional and
  nullable; `external_thread_ref` is optional.
- **`MessageCreate`** requires `direction` and `occurred_at`. It also
  carries `external_message_ref`, `message_type`, `body_text`, `media_ref`,
  `delivery_status` and `metadata`. **It has no `provider` field.**
- **`WhatsAppWebhookEnvelope`** requires `provider_event_id`, `event_type`
  and `payload`. It is `additionalProperties: true`, with `security: []`,
  and **no header parameter declared**. Its responses are 200, 400 and 401.

**No read operation exists for threads or messages** (F7-3; G7-8).

---

## 2. What the schema and the earlier slices already give, and what they leave open

**Tables** (`schema_v0.2.3.sql` §12; migrations `0002`–`0007` add nothing
to them):

| Table | Given | Left open (measured) |
|---|---|---|
| `communication_threads` | the channel; the nullable links `party_id`, `request_id`, `property_id`, `opportunity_id` (all `ON DELETE SET NULL`); `external_thread_ref`, `opened_at`, `last_message_at`, `archived_at`, `created_by_account_id` | **no user trigger** (M3); its links can be updated (M3); deleting a thread that has a message is refused by the frozen FK `communication_messages_thread_id_fkey` (`ON DELETE RESTRICT`, M3) |
| `communication_messages` | `thread_id`, `provider`, `external_message_ref`, `direction`, `message_type`, `body_text`, `media_ref`, `delivery_status` (default UNKNOWN), `occurred_at`, `sent_by_account_id`, `metadata`; `UNIQUE(provider, external_message_ref)`, named `communication_messages_provider_external_message_ref_key` (M2) | the identity does not hold for a NULL provider (M1); any UPDATE and DELETE are accepted, the delivery status backwards included (M3) |
| `webhook_events` | `provider`, `provider_event_id`, `event_type`, `payload` (`NOT NULL`), `processing_status`, `received_at`, `processed_at`, `error_text`; `UNIQUE(provider, provider_event_id)`, which holds under concurrency (M4) | its payload and status can be changed, back to RECEIVED included, and the row deleted (M3); the stored payload holds a message's text (M7) |
| `interactions` | the type, channel, links including `thread_id`, `summary`, `outcome_code`, `occurred_at`, `operator_account_id`, `metadata` | one writer today, `opportunity_commands.py` (G5-8 (i)); no audit trigger |
| `resource_consent_bindings` with `thread_id` | `trg_consent_binding`: a COMMUNICATION_ARCHIVE binding only to a thread of the grant's own party (M5) | — |
| `observations` | `kind` includes MESSAGE and CALL_NOTE; `party_id`, `observed_at`, `raw_text`, `payload` | no column links an observation to a message (F7-11) |

**What the earlier slices give:**
- **Slice 1:** the timeline service and its allow-list (`metadata`
  excluded); idempotency records; `postWebhooksWhatsapp` in
  `PUBLIC_OPERATIONS`.
- **Slice 3:** the consent service, which knows `COMMUNICATION_THREAD` and
  `COMMUNICATION_ARCHIVE`; `POST /observations`.
- **The thread loader:** `load_thread`.
- **Slices 5 and 6:** `audit_rows`.
- **The app enforces no request-body limit today** (M7: 8 MiB accepted;
  F7-12).

---

## 3. Rules that follow from the sources without a decision

### 3.1 A webhook event is stored and deduplicated before anything is resolved
- **The sources:** `API_CONTRACTS` §4.12; ADR-09; the contract's
  description of `postWebhooksWhatsapp`.
- **Consequence:** a replay of a **completed** event writes no second
  message (S42, J01, mandatory test 1), and, from step 4, no second
  interaction.
- **Measured:** the store deduplicates under concurrency (M4).
- **What "stored" means** is settled by G7-9 (a): the event row is stored
  first, and its payload is the content-free event.

### 3.2 Unauthenticated, but verified
- **The sources:** RFC-001 R10.5; `API_CONTRACTS` §8 ("Secrets/provider
  webhook verification outside domain tables"); S41 ("rejected before domain
  resolution").

### 3.3 A provider message identity is global
- **The sources:** mandatory test 2; J02; the schema's UNIQUE.
- **Measured:** M1 and M2.

### 3.4 Link consistency is a service invariant, not a trigger
- **The source:** the Remediation Review v0.2, "Communication context
  consistency".
- **Consequence:** the rule is the service's (G7-6). `0008` only freezes the
  links after creation (G7-12 (D)).

### 3.5 A phone decision is an operational record
- **The sources:** `API_CONTRACTS` §4.12; the Spec's §18.

### 3.6 Not a chat platform
- No inbox, no unread counters, no real-time delivery.

### 3.7 Staff commands are idempotent; the webhook is deduplicated by event
- **The source:** `API_CONTRACTS` §2.3 (K05).

### 3.8 What never enters a communication record
- R9.2 and R9.3. No match, offer or permission snapshot is copied into a
  thread, message, interaction or webhook row.

### 3.9 Meta's webhook, as the review of `dcebe46` cites Meta's official documentation

These are the reviewer's citation of Meta's developer documentation, page
"Create a webhook endpoint". This environment could not fetch the page:
- **subscription** is verified by a **GET** carrying `hub.mode`,
  `hub.verify_token` and `hub.challenge`;
- **notifications** are signed in **`X-Hub-Signature-256`**;
- **the native payload** of a notification is `object` with
  `entry[].changes[]`.

The frozen contract declares neither that GET nor that payload shape (F7-4,
F7-5). G7-2 decides how TURAB meets them.

---

## 4. Findings

### 4.1 Confirmed by step 0 (`evidence/SLICE7-PLAN-MEASUREMENTS.txt`)

| Finding | Measurement | Result |
|---|---|---|
| **F7-1** A NULL provider escapes the global identity | M1 | two rows, two threads, one reference |
| **F7-2** Nothing guards the communication rows | M3 | every UPDATE and DELETE accepted, as a superuser; **0 user triggers** on the four tables |
| **F7-7** STOP GATE E's writer check names one writer of `interactions` | M6 | a second writer is reported as unapproved |
| **F7-8** A thread without a party cannot carry an archive consent | M5 | refused, and also for a thread of another party |
| **F7-13 (new; from M7)** The stored webhook payload holds the content | M7 | the message text is inside `webhook_events.payload` (synthetic samples) |
| **F7-14 (new; from M8)** A link-freezing guard and `ON DELETE SET NULL` conflict | M8 | a strict guard refuses the FK's SET NULL on the party's deletion. Parties have no delete guard, so the path is reachable |

### 4.2 From reading (not measurable on PostgreSQL)

- **F7-3 · Archived content has no read operation.** The contract has no GET
  for a thread or a message. The party timeline is the only Communication
  read.
- **F7-4 · The contract has no webhook verification GET.** Meta's
  subscription needs one (§3.9).
- **F7-5 · The envelope is TURAB's, not Meta's.** The contract's required
  top-level `provider_event_id`, `event_type` and `payload` are not Meta's
  native `object`/`entry[].changes[]` (§3.9).
- **F7-6 · Retention is not defined in any source** (J03 refers it to
  "pilot/legal review").
- **F7-9 · `archived_at` has no command.**
- **F7-10 · After creation, delivery status changes only through the
  webhook.**
- **F7-11 · No column links an observation to a message.**
- **F7-12 · No request-body limit** (M7: an 8 MiB body is accepted by a
  delivered route). The unauthenticated webhook must read its whole raw
  body to verify a signature (G7-2 (i)), so the limit must apply before
  that read (G7-15).

---

## 5. Decisions

**Their status after the review of `4aed49b`:**

| Decision | Status |
|---|---|
| G7-12 (D) | **DECIDED: D2** |
| G7-2, the answer to a FAILED processing | **DECIDED: CORRECTION-007** (§5.2) |
| G7-2 (ii), Meta's boundary | **DECIDED: (a2), with R-1 required before any real event** |
| G7-4 | **DECIDED** as proposed (the provider rule, the three CHECKs, the channel guard) |
| G7-1, G7-2 (other parts), G7-3, G7-5, G7-6, G7-7, G7-8 (a), G7-9 (a), G7-10, G7-11, G7-13, G7-14, G7-15 (64 KiB, R-1 measuring real envelopes) | **directions approved** as the plan's basis; G7-3 and G7-5 completed in revision 4 |
| The text of `0008` (§5.1) | **not approved**; step 1 does not start |

**Since then:**
- the text of `0008` was approved (review of `38281ab`);
- step 1 was closed at `7e8993d`, with D2's reading of R14.6 accepted for the
  six keys only (review of `7e8993d`);
- G7-16 (i–vi) was put as decisions (revision 7) and **DECIDED as
  recommended**, and CORRECTION-006's reading approved (review of
  `0f423d2`). The path's unknown thread follows RFC-001 R5.3b (revision 8).


### G7-1 · Scope
- **Recommended:**
  - the three operations of §1, and the timeline as G7-8 decides;
  - migration `0008` as G7-12 decides;
  - an operator recovery command for stuck events, run by an operator and
    not an HTTP operation (G7-2 (v));
  - no outbound sending (G7-14);
  - no customer operation;
  - no Meta-facing GET in TURAB (G7-2 (ii)).
- **Blocks:** everything.

### G7-2 · The webhook boundary

#### (i) What TURAB verifies, before any write (S41, R10.5)
- an HMAC-SHA256 of the **raw** body, compared in constant time, with a
  secret read from the environment (not a domain table). A missing secret
  fails closed;
- a missing or wrong signature is 401 and writes **nothing**, not even
  `webhook_events`;
- an invalid request is logged without its body (`API_CONTRACTS` §8);
- **the body limit applies before the body is read** (G7-15).

#### (ii) Meta, the relay, and what each signature proves (review of `dcebe46`, point 3)

**(a) Recommended. A relay outside TURAB's API adapts Meta to the frozen
contract.** The relay:
1. **answers Meta's subscription GET** (`hub.mode`, `hub.verify_token`,
   `hub.challenge`). **The GET lives in the relay,** so TURAB's frozen
   contract needs none, and OQ7-2 is settled by placement;
2. **verifies Meta's `X-Hub-Signature-256`** over Meta's raw body, with
   Meta's app secret, **before** transforming anything. It drops what fails;
3. **transforms** each message and each status inside `entry[].changes[]`
   into one `WhatsAppWebhookEnvelope`, with a `provider_event_id` unique per
   event:
   - `message:<wamid>` for a message;
   - `status:<wamid>:<status>:<timestamp>` for a status;
4. **signs the envelope** with its own key, which is distinct from Meta's
   secret, in a header of its own: **`X-Turab-Relay-Signature`**,
   HMAC-SHA256 of the envelope's raw bytes.

**TURAB** verifies the relay's signature (i).

**What each signature proves, stated in the closure evidence as worded
here:**
- TURAB's check proves that the envelope **comes from the holder of the
  relay's key**, unchanged since it was signed;
- it is **not** a verification of Meta's signature: Meta's signature is
  checked by the relay alone, and TURAB **trusts the relay** for it;
- Slice 7's tests prove TURAB's side;
- **the relay's verification of Meta is UNPROVEN in Slice 7** unless (a1)
  is chosen.

**The relay's two variants:**
- **(a1)** The relay is built in this repository as a separate component,
  with its own tests of Meta's GET and signature on synthetic notifications.
  It widens the slice.
- **(a2) DECIDED in the review of `4aed49b`.** The relay is specified here as an
  interface (its four duties above, the envelope mapping, the header), and
  is built outside the slice. **(Revision 3, review of `58a0067`, point 3.)**
  Choosing (a2) creates **condition R-1**, independent of the slice, as K06
  is.
  - **What must happen before TURAB receives any real event:** the relay is
    built, and its own tests prove, on synthetic notifications:
    1. Meta's GET verification (`hub.mode`, `hub.verify_token`,
       `hub.challenge`), answered only for the right token;
    2. Meta's `X-Hub-Signature-256` over Meta's raw body, a wrong or missing
       signature dropped before any transformation;
    3. the transformation to envelopes, one per message and per status;
    4. its own signature;
    5. the **redelivery** of an event TURAB did not complete, **on its 500,
       on its 503 and on a timeout** (review of `bf1fe3d`: CORRECTION-008's
       503 added);
    6. **(Revision 4, review of `4aed49b`.) The scope of `thread_ref`.**
       - The relay forms every `thread_ref` as `<business number id>:<customer
         id>`: the identifier of the WhatsApp business number the
         notification was addressed to, then the customer's WhatsApp
         identifier.
       - So two business numbers served by one relay never share a
         reference.
       - Which fields of Meta's notification carry the two identifiers is
         confirmed by these tests against Meta's documentation. This
         environment could not fetch it;
    7. **(Revision 4.) The size of the relay's real envelopes** against
       G7-15's 64 KiB limit, on the message types the relay forwards,
       before real traffic.
  - **Slice 7's closure evidence** lists R-1 as **UNMET**. It never counts
    Meta's verification as done. Its tests prove TURAB's side only.
  - **The route is not exposed** to Meta's or the relay's traffic before R-1
    is met. That is an operational condition, stated, not a code switch.

**The header is not declared by the contract** (`parameters: []`). It is a
security mechanism outside the OpenAPI, as R10.5's verification is.
Declaring it in the contract would be a correction for the contract's owner
(OQ7-2).

**(b) TURAB accepts Meta's native payload, and verifies Meta's signature
directly.**
- It needs the GET and a different body schema: **two contract changes.**
- It proves Meta's signature in Slice 7.
- It keeps Meta's app secret in TURAB's environment.

#### (iii) The provider
- The constant `whatsapp` for this route.

#### (iv) The transactions, and where a failure is recorded (revision 3, review of `58a0067`, point 2)

**T1, the event.**
- The event row is inserted alone, with the **content-free payload** of
  G7-9 (a), and committed.
- A conflict on `(provider, provider_event_id)` goes to (v).

**T2, the processing.** READ COMMITTED, on one connection:
1. **The claim:** `SELECT … FROM webhook_events WHERE webhook_event_id = :e
   AND processing_status IN ('RECEIVED','FAILED') FOR UPDATE NOWAIT`.
   - 55P03 means another processor holds the event (M4b). T2 rolls back, and
     the answer is 200, nothing written.
   - No row means the event is already final. T2 rolls back, and the answer
     is 200.
2. **`SAVEPOINT processing`.**
3. **Resolution and its writes** (G7-3, G7-9): the message, the thread's
   `last_message_at`, the audit rows. *(Revision 14: "the interaction" was
   listed here; G7-17 (i) decided that step 3 writes none, step 4 adds it.)*
4. **Success:** `UPDATE webhook_events SET processing_status = 'PROCESSED'`
   (or IGNORED, with its fixed reason), `processed_at = now()`; COMMIT.
5. **Failure inside step 3** (an SQL error aborts only what follows the
   savepoint; a Python exception likewise):
   - `ROLLBACK TO SAVEPOINT processing`. It undoes every write of step 3 and
     **keeps the claim's row lock**, because a lock taken before a savepoint
     is kept when the savepoint is rolled back to (PostgreSQL 16, §13.3,
     "Explicit Locking": only a lock acquired after the savepoint is
     released);
   - then **in the same T2:** `UPDATE webhook_events SET processing_status =
     'FAILED', error_text = <a fixed code, never the exception's text>,
     processed_at = now()`; COMMIT;
   - the cause is logged under the trace id, without the body.
6. **What the savepoint cannot cover:** a failure of step 4's UPDATE, of the
   COMMIT, of the connection, or of the process itself.
   - T2 is then lost whole, and the event keeps its previous status
     (RECEIVED, or FAILED from an earlier attempt).
   - No message is half-written: everything was in T2.
   - It is recovered by (v).

**The tests (step 3):**
1. **A failure injected in step 3,** by SQL: the event is FAILED with its
   code; no message, no audit row; the answer as §5.2 decides. *(Step 3
   writes no interaction: G7-17 (i).)*
2. **A stop after T1 is committed,** with T2 never run: the event stays
   RECEIVED. A redelivery then completes it, PROCESSED, one message. The
   recovery command completes another one, PROCESSED, without content.
3. **A failure of step 4's UPDATE** (injected): the event keeps its status,
   and nothing of step 3 remains.
4. **A replay while T2 holds the claim** (held by a barrier): the replay's
   claim is refused 55P03; it answers 200 and writes nothing; the holder
   completes the event.

#### (v) The fate of RECEIVED and FAILED, and their recovery

M4b: a replay's `ON CONFLICT DO NOTHING` returns nothing whatever the stored
status, and a processor's lock is visible to NOWAIT.

**A replay reads the stored status:**

| Stored status | The replay's effect |
|---|---|
| PROCESSED or IGNORED | a true replay: 200, nothing written (S42) |
| RECEIVED or FAILED | T2 again, with the replayed envelope, which carries the content again (G7-9) |
| in flight (55P03) | 200, nothing written |

**The answer when T2 ends FAILED** is settled contractually (§5.2), not
inferred from `API_CONTRACTS` §2.5:
- **(a) Recommended. CORRECTION-007** adds a `500` response to
  `postWebhooksWhatsapp` in the effective contract, typed
  `WEBHOOK_PROCESSING_FAILED`. Its meaning: "stored, not processed; deliver
  the same `provider_event_id` again". The relay's redelivery (R-1) is then
  the recovery that keeps the content. *(Revision 14, the review of
  `3dfb717`: its meaning is "stored; the result of its processing not
  confirmed", since a T2 whose COMMIT's answer is lost may have committed.
  A T1 that raised is CORRECTION-008's 503.)*
- **(b) No contract change.** The answer is always 200 once T1 is committed.
  A FAILED event is then recovered only by the command below, **without its
  content**: the relay has no signal to redeliver.

**The operator recovery command:**
- a script under `db/ops/`, not an HTTP operation;
- it re-runs T2 on events RECEIVED for longer than a stated delay
  (5 minutes) and on FAILED events, skipping rows it cannot claim (`FOR
  UPDATE SKIP LOCKED`, M4b);
- **its limit, accepted in the review of `58a0067`:** it recovers from the
  content-free payload, so a message is stored **without** content
  (`RECOVERED_WITHOUT_CONTENT`). **It is not counted as a full recovery of
  the archive.**

**The transitions** (`0008` (C), §5.1):
- RECEIVED → PROCESSED, IGNORED or FAILED;
- FAILED → PROCESSED, IGNORED or FAILED;
- nothing leaves PROCESSED or IGNORED.

**The closure evidence** counts the RECEIVED and FAILED events at the end of
the run.

**Blocks:** step 3; §5.2.

### G7-3 · Event types and thread resolution

**Direction approved in the review of `4aed49b`.**

- **(a) Recommended.** The envelope's `payload` has a documented internal
  shape. **This is the relay's output** (G7-2 (ii)).
  - **`message`:** `external_message_ref`, `thread_ref`, `occurred_at`,
    `message_type`, and optional `body_text` and `media_ref`. It is stored as
    an INBOUND message in **the** WHATSAPP thread whose `external_thread_ref`
    is `thread_ref`;
  - **`status`:** `external_message_ref`, `status` and `occurred_at` (G7-5).
- **The thread reference's identity (revision 4, review of `4aed49b`,
  point 1):**
  - **Its form:** a WHATSAPP thread's `external_thread_ref`, when given, is
    **scoped**: `<scope>:<id>`, two non-empty parts. The relay forms it as
    `<business number id>:<customer id>` (R-1, duty 6).
  - **Who must use it:** a staff-created WHATSAPP thread meant to receive
    webhook messages carries the same form.
  - **Uniqueness:** **at most one WHATSAPP thread holds a given
    reference.** `0008` part E adds:
    - a CHECK of the form;
    - the partial unique index `ux_whatsapp_thread_ref` on
      `(external_thread_ref) WHERE channel = 'WHATSAPP' AND
      external_thread_ref IS NOT NULL`;
    - a pre-check that refuses the migration, naming the counts, if
      existing rows break either rule.
  - **Concurrency:** two concurrent creations of one reference resolve to
    one, the second refused, as M4 measured for the event store. Step 1
    tests it with a witness.
  - **The staff command:** a second WHATSAPP thread with a taken reference
    is a typed 409 `THREAD_REF_TAKEN`, writing nothing.
  - **What resolution then means:** "the thread whose reference is
    `thread_ref`" names zero or one thread. Zero is IGNORED.
  - **Other channels:** their references stay unconstrained. No resolution
    reads them.
  - **The links are frozen** by part D, so a reference, once set, never
    moves to another thread.
- **IGNORED,** with a fixed reason: an unknown type, an unknown thread, or an
  unknown message for a status.
- **No thread, party or identity is created from a webhook** (identity is
  Slice 3's reviewed process).
- **(b)** Create a party-less thread for an unknown `thread_ref`. Not
  recommended.
- **Blocks:** step 3, and `0008` part E.

### G7-4 · The global message identity (mandatory test 2, J02, F7-1)

**(a) Recommended. Revision 3, review of `58a0067`, point 4: a provider is
known for exactly one channel; every other channel refuses a reference.**

| Thread channel | Provider | `external_message_ref` |
|---|---|---|
| WHATSAPP | `whatsapp` (set by the service) | accepted |
| PHONE, SMS, EMAIL, WEB, IN_PERSON, OTHER | **none defined** by any source | **refused**: typed 422 `EXTERNAL_REF_WITHOUT_PROVIDER`, writing nothing |

- **An INTERNAL message never carries a reference** (422).
- **The database backs all three rules** (`0008` (A), §5.1):
  - `CHECK (external_message_ref IS NULL OR provider IS NOT NULL)`;
  - `CHECK (provider IS NULL OR provider = 'whatsapp')`;
  - `CHECK (direction <> 'INTERNAL' OR external_message_ref IS NULL)`;
  - a BEFORE INSERT trigger: a message with a provider belongs to a
    WHATSAPP thread.
- **A provider for another channel** would be a later decision: a new
  provider value, its own constraint change, and its own source.
- **A 23505 on `communication_messages_provider_external_message_ref_key`**
  (M2) maps to a typed 409 for staff, and to IGNORED for a webhook.

**(b) `NULLS NOT DISTINCT`.** Not recommended.

**Blocks:** steps 1–3.

### G7-5 · Delivery and read status

**Direction approved; the rule corrected in revision 4 (review of
`4aed49b`, point 2).**

- **(a) Recommended.**
  - **The order:** QUEUED < SENT < DELIVERED < READ.
  - **The accepted changes, and no others:**

    | From | To |
    |---|---|
    | UNKNOWN | QUEUED, SENT, DELIVERED or READ: **never FAILED** |
    | QUEUED, SENT, DELIVERED | any later status in the order (steps may be skipped) |
    | QUEUED or SENT | FAILED, which is final |
    | DELIVERED, READ, FAILED | nothing further (except READ after DELIVERED) |

  - **Why UNKNOWN → FAILED is refused:**
    - UNKNOWN means that TURAB never knew the message's state;
    - FAILED is accepted only for a message known to be QUEUED or SENT;
    - a provider's FAILED for an UNKNOWN message is therefore recorded
      (`webhook_events`) and **IGNORED**, with the reason
      `STATUS_TRANSITION_NOT_ACCEPTED`, like a late or backward status.
  - **The service checks the transition before its UPDATE,** so an accepted
    flow never meets the trigger's refusal. Part B refuses the same set, as
    the backstop.
  - **The only path** after creation is the webhook (F7-10).
  - **M3 shows the schema accepts READ, then SENT;** part B refuses it.
- **(b)** Last-received wins. Not recommended.
- **Blocks:** step 3; `0008` part B.

### G7-6 · The thread/opportunity link invariant (mandatory test 3)

**Checked at creation;** the links are frozen afterwards (G7-12 (D)).

- **(a) Recommended rules:**
  0. **(Revision 2, review of `dcebe46`, point 5.)** A named opportunity must
     be of a **SALE** transaction: its approved match's evaluated offer is a
     SALE offer, and its request's intent is BUY. Otherwise a typed 422,
     writing nothing. The type is **checked, not assumed** (§0.2).
  1. **If `opportunity_id` is given:**
     - `request_id`, when given, equals the opportunity's request;
     - `property_id`, when given, equals the opportunity's property;
     - `party_id` is the opportunity's buyer (the request's party) or its
       seller (the party of its current offer), per the Remediation
       Review's example.
  2. **If `request_id` is given without an opportunity,** `party_id` is the
     request's party.
  3. **If `property_id` is given without an opportunity,** `party_id` is the
     party of one of the property's offers. A relation is not accepted as
     the reason.
  4. **Every id names an existing row.** Otherwise a typed 404 or 422,
     writing nothing.
- **(b)** Rules 0–2 only.
- **(c)** A trigger. Contrary to §3.4.
- **Blocks:** step 2.

### G7-7 · Must a staff-created thread name its party?
- **(a) Recommended: yes,** by CORRECTION-006, written as CORRECTION-005 was.
  A narrowing; M5 shows that a party-less thread can never carry an archive
  consent.
- **(b)** Optional. Such a thread never archives content (G7-9).
- **Blocks:** step 2.

### G7-8 · What a staff member can read, and the timeline (review of `dcebe46`, point 4; F7-3, F7-7)

*Direction (a) accepted in the review of `58a0067`; its limits are to be
proven by the implementation's tests. Not yet a decision of the slice.*

**What "retrievable" means within Slice 7, stated.** Under the frozen
contract the only Communication read is `getPartiesPartyIdTimeline`, for
ADMIN, OPERATOR and REVIEWER. Its item is `additionalProperties: true`: the
contract leaves the field set to the implementation, and Slice 1 fixed it by
an allow-list (`services/timeline.py`). **Anything a staff member reads of a
message, they read there, or nowhere.**

- **(a) Recommended. The record is readable through the timeline, by an
  explicit, tested widening of the allow-list.**
  - **The new rows:** each message writes one `interactions` row in the same
    transaction:
    - a type by channel and direction (WHATSAPP, CALL, …; NOTE for
      INTERNAL);
    - its `thread_id` and links;
    - a fixed `summary`;
    - `metadata.message_id`.
  - **What the item of such an interaction carries:** one added key,
    **`message`**:
    - `message_id`, `direction`, `message_type`, `delivery_status` and
      `occurred_at`;
    - `content_archived`;
    - `body_text` and `media_ref` **only when `content_archived` is
      true** (G7-9).
  - **Why this is not a silent widening of the contract:**
    - the item's schema is open, so the OpenAPI is unchanged;
    - the allow-list change is decided here, named in the delivery, and held
      by a DTO test of the item's exact key set (R9.5).

    It is still a change of Slice 1's delivered output, and it is stated as
    such.
  - **What stays unreadable through the API:**
    - a message's content when it was not archived;
    - a thread's own row (its links, `external_thread_ref`): only the
      `thread_id` and the item's links are shown;
    - `webhook_events`.
  - **The cost:**
    - a second writer of `interactions`, changing G5-8 (i)'s single writer;
    - STOP GATE E's `--check` reports it (M6). **Recommended:** STOP GATE E
      stays the record of Slice 5's tree, as STOP GATE D stays Slice 4's,
      and Slice 7's evidence inventories the writers of `interactions` by
      kind.
- **(b) Metadata only.**
  - The timeline shows the message's existence, direction, time and status,
    never its content.
  - "Retrievable" then means: retrievable by staff through the timeline as
    a record of what happened. The **content** is retrievable only from the
    database, by an operator, outside the API.
  - **Reading content needs a contract addition** (a GET of a thread's
    messages: OQ7-3).
- **(c)** New GET operations now. A contract addition, outside the slice.
- **Blocks:** step 4.

### G7-9 · Content and consent (review of `dcebe46`, point 1; J03; F7-6; F7-13)

*Direction (a) accepted in the review of `58a0067`; its limits are to be
proven by the implementation's tests.*

**The rule: no content is stored anywhere unless the thread's party has
consented, at the moment of writing.** M7 shows that storing the event as
received would store the text, so the rule binds the event store too.

**(a) Recommended. Content is kept only in `communication_messages`, under a
consent checked at write time.**

**1. `webhook_events.payload` is the content-free event,** built from the
verified envelope before the first insert:
- **kept:** `provider_event_id`, `event_type`, `external_message_ref`,
  `thread_ref`, `occurred_at`, `message_type`, `status`, and two flags:
  `has_body` and `has_media`;
- **dropped:** `body_text`, `media_ref`, and **every key not on this list**.
  An allow-list, so a key the relay adds later is dropped, not stored;
- **what it records:** enough to deduplicate, to process statuses, to
  recover identifiers, and to say that content existed. Never the content.

**2. `communication_messages.metadata`** carries:
- `content_archived` (bool);
- `content_withheld_reason`: `NO_ARCHIVE_CONSENT`,
  `RECOVERED_WITHOUT_CONTENT` or none;
- for a webhook message, `webhook_event_id`.

It never carries content, a digest of content, or the provider's raw
fields.

**3. The consent condition, as it actually holds:**
- **What is checked:** in the transaction that writes the message, the
  service reads, under `FOR SHARE`, an ACTIVE `COMMUNICATION_ARCHIVE` grant
  of the thread's party, bound to that thread and unrevoked. The same lock
  pattern as Slice 5's share against a binding (R-S5-5-01), so a revocation
  committing meanwhile is waited for, then seen.
- **If it holds,** `body_text` and `media_ref` are written.
- **If it does not hold:**
  - **a staff message** that carries content is refused with a typed 422
    `CONTENT_NOT_ARCHIVABLE`, writing nothing (the operator resends without
    content). Silently dropping what an operator typed would hide the
    refusal;
  - **a webhook message** is stored without content, with
    `content_withheld_reason = NO_ARCHIVE_CONSENT`. The content existed only
    in the request's memory, and is discarded.

**4. Logs** carry no body, of either kind (`API_CONTRACTS` §8).

**5. Revocation** stops future archiving from its commit on. **Content
already archived stays.** Erasing it on revocation is a retention rule
(OQ7-1), and is not claimed.

**6. J03 is claimed exactly as:** no content is stored without a consent
valid when it was written. Retention is not claimed (OQ7-1).

**The cost:**
- a message whose processing FAILED and is recovered by the command loses
  its content for good. Only a redelivery can bring it back (G7-2 (v));
- a relay that adds content under an unlisted key has it dropped, by
  design.

**(b) Keep the event as received, and redact it after processing.** Not
recommended:
- the content would exist in the database without consent between the two
  transactions, and for good in a RECEIVED or FAILED event;
- the redaction is an UPDATE of `payload`, contrary to G7-12 (C).

**(c) Store content always.** Contrary to J03 as worded.

**Blocks:** steps 2–3.

### G7-10 · Linking a phone decision to a later written confirmation (mandatory test 4, F7-11)
- **(a) Recommended. The link is a record of its own, append-only:**
  - **the decision:** an INTERNAL message, `message_type` `PHONE_DECISION`,
    in a PHONE thread of the party;
  - **the confirmation:** an observation of kind MESSAGE, made by `POST
    /observations` (Slice 3);
  - **the link:** a later INTERNAL message, `message_type`
    `CONFIRMATION_LINK`, whose metadata names `decision_message_id` and
    `observation_id`. The service checks four things:
    - both exist;
    - the decision is in the same thread;
    - the observation is of the thread's party;
    - its `observed_at` is not before the decision.
  - **Nothing earlier is updated.** No legal value is claimed.
  - **An INTERNAL message carries staff text,** so G7-9's consent rule
    applies to its `body_text` as to any message.
- **(b)** The observation's `payload` names the decision. This changes Slice
  3's route.
- **(c)** Update the decision's metadata. Contrary to G7-12 (B).
- **Blocks:** step 4.

### G7-11 · Audit
- **Recommended:**
  - `audit_rows` for threads, messages and interactions, with `body_text`
    and `media_ref` withheld;
  - `webhook_events` is its own processing record, not audited twice;
  - a refused webhook is logged without its body.
- **Blocks:** steps 2–4.

### G7-12 · Migration `0008` (the text of §5.1; approved in the review of `38281ab`; executed in step 1)

- **(A)** The message identity (G7-4).
- **(B)** Messages are append-only; `delivery_status` forward only (G7-5).
- **(C)** A `webhook_events` row is immutable except its processing fields,
  by the transitions of G7-2 (v).
- **(D) A thread's links. DECIDED in the review of `4aed49b`: D2.** D3 is
  not chosen; its description stays below as the alternative that was put.
  (Revision 3, review of `58a0067`, point 1: an explicit choice.)

  **What M8 measured, and why D1 is withdrawn:**
  - M8 measured three candidates: strict, permissive and depth-based.
  - The depth-based one was called "FK-only" in revision 2. **That name is
    withdrawn.** `pg_trigger_depth()` returns the current nesting level of
    triggers (PostgreSQL 16, §9.26). Depth > 1 shows that the UPDATE runs
    inside a trigger. It does not show that the trigger is a foreign key's
    referential action. A trigger on **any** table that updates a thread
    would pass the same test.

  **The scope of the conflict is wider than revision 2 said.** It is not the
  four links alone: every `ON DELETE SET NULL` key on a guarded table meets
  the guard the same way. There are six:
  - on `communication_threads`: `party_id`, `request_id`, `property_id`,
    `opportunity_id`, `created_by_account_id`;
  - on `communication_messages`: `sent_by_account_id`.

  **The two variants put in revision 3 (D2 decided):**

  - **(D2) DECIDED. Strict, with the six foreign keys made `ON DELETE
    RESTRICT`.**
    - **The guarantee:** a thread's links and attribution, and a message's
      attribution, **never change** after INSERT, by any statement at any
      depth. `last_message_at` moves forward only.
    - **Its consequences:**
      - a party, request, property, opportunity or account that a thread or
        message names **cannot be deleted**. The deletion is refused, and
        the deleting transaction fails;
      - **requests, properties and opportunities** already have delete
        guards (`prevent_core_delete`), so nothing changes for them;
      - **parties** have no delete guard. Their deletion becomes impossible
        while a thread names them;
      - **accounts** are disabled, not deleted (`account_status` has
        DISABLED). No application path deletes either a party or an account
        (`src/` searched: no `DELETE FROM` either table);
      - **an erasure request** (a party's data removed) would then need a
        procedure of its own: the threads' fate first. That is a retention
        question (OQ7-1), not answered here;
      - **six frozen constraints change.** The migration drops and re-adds
        each by its name. The names follow PostgreSQL's default
        `<table>_<column>_fkey`, as M3's
        `communication_messages_thread_id_fkey` shows, and the migration
        fails if a name differs.
  - **(D3) Not chosen. The frozen keys kept, and a narrower guarantee,
    stated exactly.**
    - **The guarantee:**
      - **no top-level statement** (`pg_trigger_depth() = 1`) changes a
        thread's links or attribution, or a message's attribution;
      - **a statement run inside a trigger** (`pg_trigger_depth() > 1`, on
        **any** table: a foreign key's referential action, or any other
        trigger that updates these rows) may set them **to NULL**. It can
        never set them to another value.
      - The links are therefore **not frozen**. They are "never re-pointed,
        possibly erased by a nested statement".
    - **What bounds it:** the closure evidence lists every trigger function
      in the database whose body updates `communication_threads` or
      `communication_messages`. Today there is none (M3). A new one would
      have to be reviewed against this guarantee.
    - **Its advantage:** no frozen constraint changes, and the deletion of a
      party keeps working as frozen.
- **Each guard is proven at trigger level,** not as K06 (G7-13).
- **Blocks:** step 1. §5.1's part D is D2.

### G7-13 · K06 (not blocking this plan)
- **Carried unchanged.** The application role is a superuser (M3). K06 is
  UNPROVEN, and its remedy is an independent condition before any release
  gate.

### G7-14 · Outbound sending
- **(a) Recommended. Archive only.**
  - An OUTBOUND message records what was sent through the official channel;
    its status arrives by webhook.
  - No provider API call, no network, no provider credentials in TURAB.
- **(b)** Send through the provider. Its credentials and network boundary
  are specified by no source.

### G7-15 · The body limit of the unauthenticated webhook (new; F7-12)
- **(a) Recommended.**
  - The webhook route refuses a body larger than **64 KiB** with 400,
    writing nothing. The limit is checked on `Content-Length` and while
    reading, **before** the signature is computed.
  - The value is set from M7's synthetic samples (under 1 KB) with a wide
    margin, and is to be revisited on the relay's real envelopes.
- **(b)** An app-wide limit. A change beyond this slice's routes, though
  F7-12 concerns them all: put as a separate question (OQ7-4).
- **Blocks:** step 3.

### G7-16 · What step 2 needs and the plan does not decide (revision 7; found preparing step 2; DECIDED as recommended in the review of `0f423d2`, (vi)'s 404 corrected to R5.3b in revision 8)

**Why this exists.** Preparing step 2 against the contract and
`API_CONTRACTS_v0.2.md` §4.12 found six points on which neither the sources
nor G7-1 to G7-15 fix the behaviour. Each is put as a decision, with a
recommendation; a recommendation is not a decision.
- **What depends on them:** the message command only. Thread creation
  (G7-6, G7-7 with CORRECTION-006, G7-3's reference, G7-11) depends on none
  of (i)–(vi), but it does depend on the reading of CORRECTION-006 below.
- **What waits:** **no step 2 code is written before these points and that
  reading are decided,** so that step 2 is delivered as one.

The sources read:
- **`API_CONTRACTS` §4.12:**
  - the thread is "linked to the relevant PARTY and optional domain
    context";
  - the message route "stores outbound/internal messages. Provider ids and
    delivery/read status are preserved";
- **`MessageCreate`:**
  - `direction` admits INBOUND, OUTBOUND and INTERNAL;
  - `delivery_status` admits all six statuses;
  - `metadata` is an open object;
  - `message_type` is free text, default `TEXT`.

**(i) A message with direction INBOUND, written by staff.**
- **(a) Recommended: refused,** with a typed 422 `DIRECTION_NOT_ACCEPTED`,
  writing nothing.
  - **The source:** §4.12 gives the route outbound and internal messages.
  - **Where inbound comes from:** an inbound message enters through the
    webhook (step 3).
  - **What staff record instead:** what a party said on a call, as an
    INTERNAL message (G7-10 records a phone decision that way).
  - **The consequence:** `sent_by_account_id` is then always the caller.
- **(b) Accepted, with `sent_by_account_id` NULL.** The party sent it, and the
  staff member who wrote it is in the audit row.

**(ii) The `delivery_status` a staff message states.**
- **(a) Recommended:**
  - **OUTBOUND:** the stated status is stored, default UNKNOWN, as §4.12's
    "preserved" says. After creation it changes through the webhook only
    (F7-10, G7-5);
  - **INTERNAL:** absent or UNKNOWN only. A note has no delivery, so any
    other value is a typed 422 `DELIVERY_STATUS_NOT_ACCEPTED`.
- **(b) UNKNOWN only, for every direction.** It would not preserve a status
  that staff know.

**(iii) The `metadata` a staff message carries.**
- **What constrains it:** G7-9 (2) fixes what `metadata` holds
  (`content_archived`, `content_withheld_reason`, and a webhook event id),
  and says that it never holds content.
- **(a) Recommended:** an absent or empty `metadata` only. Any key is a typed
  422 `MESSAGE_METADATA_NOT_ACCEPTED`, writing nothing. The service writes
  the keys G7-9 names.
  - **Why:** an open object could carry content outside the consent rule,
    and no source names a staff key to allow.
- **(b) An allow-list of staff keys.** No source names one.
- **(c) Stored as given.** Contrary to G7-9 (2).

Dropping it silently is not offered: G7-9 (3) refuses to hide what an
operator sent.

**(iv) `communication_threads.last_message_at`.**
- **(a) Recommended:** each message sets it to the later of its value and the
  message's `occurred_at`, in the message's transaction, with the thread row
  locked `FOR UPDATE`. Part D allows that change, and only that one.
- **(b) Not maintained** by Slice 7.

**(v) The message types G7-10 gives a meaning.**
- **(a) Recommended:** step 2 refuses the `message_type` values
  `PHONE_DECISION` and `CONFIRMATION_LINK`, with a typed 422
  `MESSAGE_TYPE_RESERVED`, until step 4 implements G7-10's rules for them.
  - **Why:** a `CONFIRMATION_LINK` written without G7-10's four checks would
    be a link nobody checked.
  - **Every other value** stays free text, as frozen.
- **(b) Accepted now,** without the checks.

**(vi) The names of the typed refusals.**
- **Named by the plan, and kept:**
  - `EXTERNAL_REF_WITHOUT_PROVIDER` (G7-4);
  - `THREAD_REF_TAKEN` (G7-3);
  - `CONTENT_NOT_ARCHIVABLE` (G7-9).
- **Recommended for the rest:**
  - 422 `THREAD_REF_NOT_SCOPED`: a WHATSAPP reference not of the form
    `<scope>:<id>`;
  - 422 `OPPORTUNITY_NOT_SALE` (G7-6 rule 0);
  - 422 `THREAD_LINKS_INCONSISTENT` (G7-6 rules 1–3), whose `field_errors`
    name the fields, never the ids;
  - 422 `LINKED_RECORD_NOT_FOUND`: a body id naming no row (G7-6 rule 4).
    The 404 is kept for the path's thread;
  - 409 `MESSAGE_REF_TAKEN`: the 23505 of M2 (G7-4).

**And a reading to confirm: CORRECTION-006.**
- **The basis:** G7-7 (a) was approved as a direction, and §7 (1) applies
  CORRECTION-006 "once written and approved".
- **The precedent:** CORRECTION-005 was written in Slice 6 step 2 from an
  approved direction, and its text was reviewed with that step's delivery.
- **The reading:** step 2 writes CORRECTION-006 the same way. Its text is
  submitted for approval with the delivery.

**Blocks:** step 2's message command (i–vi); step 2's thread command, for
CORRECTION-006's reading.

### G7-17 · What step 3 needs and the plan does not decide (revision 12; found preparing step 3; DECIDED in the review of `bf1fe3d`, with (ii) and (vi) amended: see that review's table)

**Why this exists.** Preparing step 3 against G7-2, G7-3, G7-5, G7-9,
G7-15, §5.2, RFC-001 R10.4 and R10.5, and the webhook's frozen contract
(responses 200 "Accepted" with no body schema, 400, 401; the envelope
`provider_event_id`, `event_type`, `payload`, all open) found seven points on
which neither the sources nor G7-1 to G7-16 fix the behaviour. Each is put as
a decision, with a recommendation; a recommendation is not a decision. **No
step 3 code is written before they are decided.** The decided parts are not
reopened: T1 and T2, the savepoint and the FAILED record, the 55P03 answer,
the replay table, the recovery command, the content-free payload, the 64 KiB
limit, and CORRECTION-007's adoption.

**(i) The interaction row in T2.** G7-2 (iv) step 3 lists "the interaction"
among T2's writes. G7-8, which decides that each message writes one
`interactions` row, is step 4's ("Blocks: step 4"), as are its allow-list
and its key-set test.
- **(a) Recommended:** step 3 writes no `interactions` row. Step 4 adds the
  row for every message, staff and webhook alike, with G7-8's tests. T2's
  writes in step 3 are then the message, the thread's `last_message_at`, and
  the audit rows.
- **(b)** Step 3 writes the webhook's interaction now, ahead of G7-8's
  allow-list and tests, and step 4 adds the staff ones.

**(ii) The relay signature's form, and a missing secret.** G7-2 (ii) names
the header `X-Turab-Relay-Signature`, "HMAC-SHA256 of the envelope's raw
bytes", without its encoding; (i) says "a missing secret fails closed",
without the answer.
- **(a) Recommended:**
  - **the value is `sha256=<64 lowercase hex digits>`.** This is the form of
    Meta's `X-Hub-Signature-256`, which the relay already reads. It is
    compared in constant time with the HMAC of the raw body under the secret
    of the environment variable `TURAB_RELAY_SIGNING_SECRET`. Any other form
    is 401;
  - **a missing or empty secret** is 401 for every request, writing
    nothing, with the configuration fault logged under the trace id. The
    500 of CORRECTION-007 means "stored, deliver again", which would be
    false here.
- **(b)** Bare hex, or base64.
- **(c)** A missing secret answered 500.

**(iii) The order of the checks, and a valid signature on an invalid
body.**
- **(a) Recommended:** in this order, each writing nothing:
  1. the size: more than 64 KiB is 400, on `Content-Length` and while
     reading (G7-15);
  2. the signature: 401 ((ii));
  3. the JSON and the envelope (`provider_event_id` a non-empty string,
     `event_type` a string, `payload` an object): 400;
  4. **for `event_type` `message` or `status`, the keys G7-3 gives it**
     (`message`: `external_message_ref`, `thread_ref`, `occurred_at`,
     `message_type`; `status`: `external_message_ref`, `status`,
     `occurred_at`), each a string, `occurred_at` an RFC 3339 instant, and
     `status` one of the six. A missing or mistyped key is 400, writing
     nothing. The relay, which formed it, then sees its fault, where an
     IGNORED event would hide it.

  Every refusal is logged without the body. **An unknown `event_type`** is
  stored by T1 and IGNORED (G7-3).
- **(b)** The event stored by T1 and IGNORED (`PAYLOAD_NOT_VALID`) instead of 400.

**(iv) The fixed codes of IGNORED and FAILED.** G7-3 and G7-5 decide when an
event is IGNORED, and name one code (`STATUS_TRANSITION_NOT_ACCEPTED`); G7-2
(iv) decides that a FAILED event carries "a fixed code".
- **(a) Recommended:** written to `webhook_events.error_text`, the column
  0008 part C leaves writable:
  - **IGNORED:** `UNKNOWN_EVENT_TYPE`; `UNKNOWN_THREAD` (no WHATSAPP thread
    holds `thread_ref`); `UNKNOWN_MESSAGE` (a status for no recorded
    message); `MESSAGE_REF_TAKEN` (the message's reference is already
    recorded: G7-4's 23505); `STATUS_TRANSITION_NOT_ACCEPTED` (G7-5);
  - **FAILED:** `PROCESSING_FAILED`.

  None carries the exception's text.

**(v) The 200's body.**
- **(a) Recommended:** no body. The contract's 200 is "Accepted" with no
  content, and the relay needs only the status. The same 200 answers a new
  event, a replay, an event in flight (55P03) and an IGNORED one: none of
  them asks the relay to act.
- **(b)** A small JSON body naming the outcome. That would tell an
  unauthenticated caller what TURAB holds.

**(vi) CORRECTION-007's mechanism.**
- **The constraint:** the corrections overlay accepts only narrowings
  (`CONTRACT_CORRECTIONS.yaml`, its header: "A correction may only
  NARROW"), and §5.2 calls CORRECTION-007 "an addition to the frozen
  contract's responses".
- **(a) Recommended:** a new section, `response_additions`, with its own
  loader rules, each refused otherwise:
  - one entry per operation;
  - an operation of the frozen contract;
  - a status code the frozen operation does not declare;
  - a 5xx;
  - `application/problem+json` with `$ref: Problem`;
  - a fixed `code`;
  - the frozen responses pinned (`frozen_statuses`), so a changed package
    makes the entry stale.

  The effective contract gains the response and an `x-turab-correction`
  annotation of kind `RESPONSE_ADDITION`. The overlay's header is amended
  to say that this one kind adds an error response and nothing else. Its
  text is submitted with step 3's delivery, as CORRECTION-006's was.
- **(b)** The 500 enforced in code, outside the effective contract: contrary
  to §5.2.

**(vii) The webhook in the authorization matrix and the audit log.**
- **(a) Recommended:**
  - every answer of the route is recorded by the access auditor, with the
    operation and the outcome (accepted, refused 400 or 401, failed), and
    no body;
  - the message and the thread's move are audited by `audit_rows`, the
    actor NULL (no account) and the context `postWebhooksWhatsapp`;
  - `webhook_events` is its own record and is not audited twice (G7-11).
- **(b)** The route unaudited beyond `webhook_events`.

**Blocks:** step 3.

### G7-18 · What step 4 needs and the plan does not decide (revision 17; found preparing step 4; DECIDED in the review of `e18271a`: the nine options (a), with the limits of that review's table)

**Why this exists.** Preparing step 4 against G7-8 (a), G7-10 (a), G7-11,
G7-17 (i) and the schema found nine points on which neither the sources nor
G7-1 to G7-17 fix the behaviour. Each is put as a decision, with a
recommendation; a recommendation is not a decision. **No step 4 code is
written before they are decided.** The decided parts are not reopened: one
`interactions` row per message in the message's transaction; the backfill
of the earlier messages, once, with no duplicate on a re-run, and the
statement that atomicity does not apply to them retroactively (G7-17 (i));
the item's added key `message` and its content only when archived (G7-8
(a)); the link as an append-only INTERNAL message (G7-10 (a)).

**What was measured for it** (the suite's database, head `0008`):
- `interactions` has no user trigger and no unique constraint;
  `interaction_type` is `CALL, WHATSAPP, SMS, EMAIL, IN_PERSON, INFO_REQUEST,
  VISIT, NEGOTIATION, STATUS_CHANGE, NOTE, OTHER`; `communication_channel` is
  `WHATSAPP, PHONE, SMS, EMAIL, WEB, IN_PERSON, OTHER`: **WEB has no
  interaction type of its own**;
- `observations.observed_at` is **nullable**; `party_id` is nullable
  (`ON DELETE SET NULL`); `trg_cited_observation_unchanged` protects an
  observation cited by the tables it names, and **a message's metadata is
  not one of them**;
- the contract's `MessageCreate.metadata` is an open object, but G7-16
  (iii) makes the staff command refuse any non-empty `metadata`;
- `getPartiesPartyIdTimeline` is for ADMIN, OPERATOR **and REVIEWER**;
- `services/timeline.py` withholds `interactions.metadata` at every
  audience (Slice 1).

**(i) The interaction's type.**
- **(a) Recommended:** by direction, then channel. INTERNAL is `NOTE` in any
  channel. Otherwise the thread's channel: WHATSAPP → `WHATSAPP`, PHONE →
  `CALL`, SMS → `SMS`, EMAIL → `EMAIL`, IN_PERSON → `IN_PERSON`, WEB and
  OTHER → `OTHER`. The interaction's `channel` is the thread's.
- **(b)** `OTHER` for every message, the channel alone telling them apart.

**(ii) The fixed `summary`.**
- **(a) Recommended:** one fixed text per direction, naming no content and
  no reference: "Inbound message", "Outbound message", "Internal note". The
  channel is in its own column. `interactions.summary` is already withheld
  from the audit rows (WITHHELD, review of `6c6e614`).
- **(b)** No summary (NULL).

**(iii) The interaction's other columns.**
- **(a) Recommended:**
  - `party_id`, `request_id`, `property_id`, `opportunity_id`, `thread_id`:
    the thread's, read in the message's transaction (the links are frozen,
    G7-12 (D); a party nulled by `ON DELETE SET NULL` gives an interaction
    no timeline shows, as for any interaction);
  - `occurred_at`: the message's; `operator_account_id`: the message's
    `sent_by_account_id` (NULL for the webhook);
  - `outcome_code`: NULL;
  - `metadata`: exactly `{"message_id": "<uuid>"}`;
  - audited by `audit_rows` with the message's actor and context.
- **(b)** Only `party_id` and `thread_id`.

**(iv) One interaction per message: where the guarantee lives.**
- **(a) Recommended: the service, no migration.**
  - The two writers of a message (the staff command, the webhook's T2)
    write its interaction in the same transaction, and nothing else writes a
    message.
  - The backfill inserts for the messages that have none (`NOT EXISTS` on
    `metadata->>'message_id'`), under a transaction-level advisory lock, so
    two backfills cannot interleave. A message committed before the
    backfill's statement already has its interaction; one not yet committed
    is invisible to it, and brings its own.
  - Tested: a re-run writes nothing; a backfill concurrent with a message
    makes no duplicate; two backfills at once make no duplicate.
  - **Its limit:** a statement outside the service (a superuser, K06) can
    write a second row; no constraint refuses it.
- **(b) A migration `0009`:** a unique partial index on
  `((metadata->>'message_id'))` where the key exists. Stronger, and a
  schema change with its own approval cycle.

**(v) The backfill.**
- **(a) Recommended:** `db/ops/backfill_message_interactions.py`, an
  operator's script like the recovery command: one transaction, actor-less,
  the audit context `backfillMessageInteractions`; it prints counts only.
  - **Stated, as G7-17 (i) asks:** for the messages that existed before step
    4, the interaction is written later, by the backfill, so the atomicity
    of a message with its interaction does not hold for them; their
    `created_at` is the backfill's time, their `occurred_at` the message's.
  - Run in the tests on messages written without an interaction (the state
    a pre-step-4 database is in).
- **(b)** A migration that backfills. A data change inside a schema
  migration, which `0008` did not do.

**(vi) The timeline item's `message` key.**
- **(a) Recommended:**
  - present **only** on an item whose interaction names a message; every
    other item keeps Slice 1's exact key set, unchanged;
  - its keys: `message_id`, `direction`, `message_type`,
    `delivery_status`, `occurred_at`, `content_archived`; and `body_text`
    and `media_ref`, both, only when `content_archived` is true (each as
    stored, possibly null);
  - read live from `communication_messages`, so a later delivery status is
    shown; `interactions.metadata` itself stays withheld;
  - **REVIEWER reads it too:** the operation's roles are ADMIN, OPERATOR and
    REVIEWER. Stated, not changed;
  - the list stays audited once (R6.3c); no per-message access record;
  - two exact key-set tests (R9.5): a message item, with and without
    archived content; and an item of any other interaction, unchanged.
- **(b)** `message` present on every item, null when none: one key set,
  and a change to every item Slice 1 delivered.

**(vii) G7-10's request: where the two ids go, and the refusals.**
- **(a) Recommended:**
  - `CONFIRMATION_LINK` carries `metadata: {"decision_message_id",
    "observation_id"}`, exactly these two keys, each a uuid. Every other
    type keeps G7-16 (iii): `metadata` absent or empty. The service stores
    the two ids beside its own keys;
  - `PHONE_DECISION` and `CONFIRMATION_LINK` are no longer reserved (G7-16
    (v)), and each is accepted only INTERNAL, in a PHONE thread;
  - the link's checks, the decision first: it exists, is `PHONE_DECISION`,
    INTERNAL, and in the same thread; the observation exists, is of kind
    `MESSAGE`, its `party_id` is the thread's party, its `observed_at` is
    **not NULL** and not before the decision's `occurred_at`;
  - the decision and the observation read `FOR SHARE` in the link's
    transaction, so a change in flight is waited for, then seen;
  - one typed 422 per rule, `field_errors` naming the field, never a value or
    an id: `PHONE_DECISION_NOT_ACCEPTED` (not INTERNAL, or not a PHONE
    thread), `CONFIRMATION_LINK_NOT_ACCEPTED` (the same for the link, or
    its metadata's shape), `DECISION_NOT_LINKABLE` (missing, another type,
    another thread), `OBSERVATION_NOT_LINKABLE` (missing, another kind,
    another party, no time, or before the decision);
  - several links may name one decision: each is its own append-only
    record;
  - **its limit:** the observation is not "cited" in the trigger's sense, so
    after the link it can still change or be deleted by a path that allows
    it; the checks hold at the link's writing. No legal value is claimed.
- **(b)** A NULL `observed_at` accepted, the order then unchecked.

**(viii) An inbound message of either type.**
- **(a) Recommended:** unchanged from step 3. The webhook stores the type as
  given; the meaning G7-10 gives belongs to an INTERNAL message only, so an
  inbound `PHONE_DECISION` can never be linked (tested).
- **(b)** The webhook IGNORES such a message (`MESSAGE_TYPE_RESERVED`). It
  would change step 3's closed behaviour, and lose an inbound message.

**(ix) The writers of `interactions`.**
- **(a) Recommended:** as G7-8 states. STOP GATE E stays Slice 5's record,
  stale; step 4's delivery inventories the writers by kind: Slice 5's
  share, the staff message, the webhook's message, the backfill.

**Blocks:** step 4.

### G7-19 · What step 5 needs and the plan does not decide (revision 21; found preparing step 5; NOT YET DECIDED)

**Why this exists.** §6.4 asks for a generated `SLICE_7_EVIDENCE.md` "as
Slice 6's", bound to a clean-tree run. Slice 6's generator takes every status
from the bound JUnit report and computes the writes from the source. Three
points have no precedent there, and are put as decisions with a
recommendation; a recommendation is not a decision. **No step 5 code is
written before they are decided.** Not reopened: §6.1-§6.4, the
mandatory and red-team mapping, R-1 UNMET, STOP GATE E as Slice 5's record.

**Found while preparing it, and to be added in step 5 without a decision**
(gaps of the existing tests against §6.1 and §6.2):
- mandatory test 1's concurrent delivery checks one event and one message,
  not one interaction;
- K05's "another body on the key is 409" is not tested for either staff
  command (their replays are).

**(i) The event store's RECEIVED and FAILED counts "at the end of the run".**
They live in the suite's database, not in the report or the source.
- **(a) Recommended:**
  - a script, `db/gate/slice7_event_store_counts.py`, run right after
    `record_test_run.py` on the suite's database, writes
    `evidence/SLICE7-EVENT-STORE-COUNTS.txt`: the count of each
    `processing_status` (and FAILED's `error_text`), the run's commit and
    source fingerprint read from `TEST-RUN-PROVENANCE.txt`, and nothing
    else (no id, no reference, no payload);
  - the generator refuses unless that file names the bound run's
    fingerprint, and shows its counts as **measured**, never as PASS;
  - **stated:** these are the suite's test events. A RECEIVED left by the
    recovery test is there by design (younger than 5 minutes). **No real
    event exists** (R-1).
- **(b)** The generator queries the database itself. Its result would then
  depend on the database's state when it runs, not on the bound run.

**(ii) The writes "exactly those decided, by kind" (§7 (9)).** Computed from
the source, as Slice 6's; the generator refuses any other.
- **(a) Recommended, the decided set:**

  | Table | INSERT | UPDATE | DELETE |
  |---|---|---|---|
  | `communication_threads` | `communication.py` | `communication.py`, `webhooks.py`: `last_message_at` only | none |
  | `communication_messages` | `communication.py`, `webhooks.py` | `webhooks.py`: `delivery_status` only | none |
  | `webhook_events` | `webhooks.py` | `webhooks.py`: the processing fields only | none |
  | `interactions` | `opportunity_commands.py` (Slice 5), `message_interactions.py` | none | none |

  The trigger-level refusals of `0008` (frozen links, append-only rows, the
  event's transitions) are listed as trigger-level, never as K06.
- **(b)** Tables only, without the columns of each UPDATE.

**(iii) What is never PASS.**
- **(a) Recommended:** listed as limits, each with what holds it:
  - **R-1 UNMET;** the relay's signature proves the relay's origin, not
    Meta's (G7-2 (ii), as worded there);
  - **K06 UNPROVEN** (EN-02);
  - **retention not claimed** (OQ7-1);
  - **one interaction per message within the service's paths,** not a
    database constraint (G7-18 (iv));
  - **a confirmation link valid at its writing only,** with no legal value
    (G7-18 (vii));
  - **the recovery command's content-less recovery** (G7-2 (v));
  - Slice 6's carried limits: SALE only (G4-5R open), K06, and its two
    stated limits (§5 of `SLICE_6_EVIDENCE.md`);
  - `SLICE_6_EVIDENCE.md` and STOP GATE E stay their slices' records, stale;
    this generator does not depend on them.
- **(b)** The same, without Slice 6's limits.

**Blocks:** step 5.

### Open questions (not decisions)
- **OQ7-1 · Retention:** of archived content, and its fate on revocation
  (J03, F7-6). The sources leave it to "pilot/legal review".
- **OQ7-2 · The contract's owner:**
  - whether to declare the relay's signature header;
  - whether ever to accept Meta's native shape (G7-2 (b)).
  - CORRECTION-007 is no longer open: **decided** in the review of
    `4aed49b` (§5.2), to be written in step 3.
- **OQ7-3 · A read operation for a thread's messages,** if G7-8 (b) is
  decided.
- **OQ7-4 · An app-wide request-body limit** (F7-12).

### 5.1 The text of migration `0008` (APPROVED in the review of `38281ab`; executed in step 1)

**Revision 4.** Part D is D2 (chosen in the review of `4aed49b`). Part B's
status rule is corrected (UNKNOWN → FAILED refused). Part E is new: a
WHATSAPP thread's reference is scoped and unique.

**Executed in step 1** (revision 6). `0008_communication_records.py` runs
this block statement by statement, and
`test_the_migration_executes_the_approved_text` compares the two. Its
execution, tests and mutations are reported in `SLICE_7_STEP1_DELIVERY.md`.
The block below is unchanged since revision 4.

```sql
-- 0008 — communication records: identity, append-only rows, frozen threads
-- Plan: docs/gate/SLICE_7_PLAN.md revision 4: G7-3, G7-4, G7-5, G7-2 (v),
-- G7-12 (D2, review of 4aed49b).

-- Part E first: a WHATSAPP thread's reference is scoped and unique (G7-3) -------
-- Existing rows are checked before the index, so a failure names its cause.
DO $$
DECLARE
  malformed integer;
  duplicated integer;
BEGIN
  SELECT count(*) INTO malformed FROM turab.communication_threads
   WHERE channel = 'WHATSAPP' AND external_thread_ref IS NOT NULL
     AND external_thread_ref !~ '^[^:]+:[^:]+$';
  SELECT count(*) INTO duplicated FROM (
    SELECT external_thread_ref FROM turab.communication_threads
     WHERE channel = 'WHATSAPP' AND external_thread_ref IS NOT NULL
     GROUP BY external_thread_ref HAVING count(*) > 1) d;
  IF malformed > 0 OR duplicated > 0 THEN
    RAISE EXCEPTION '0008: % WHATSAPP thread reference(s) not scoped, % reference(s) shared; resolve them before this migration',
      malformed, duplicated;
  END IF;
END $$;

ALTER TABLE turab.communication_threads
  ADD CONSTRAINT ck_whatsapp_thread_ref_scoped
      CHECK (channel <> 'WHATSAPP' OR external_thread_ref IS NULL
             OR external_thread_ref ~ '^[^:]+:[^:]+$');
CREATE UNIQUE INDEX ux_whatsapp_thread_ref
    ON turab.communication_threads (external_thread_ref)
 WHERE channel = 'WHATSAPP' AND external_thread_ref IS NOT NULL;

-- Part A: a provider message identity is whole, and known (G7-4) ----------------
ALTER TABLE turab.communication_messages
  ADD CONSTRAINT ck_message_ref_needs_provider
      CHECK (external_message_ref IS NULL OR provider IS NOT NULL),
  ADD CONSTRAINT ck_message_provider_known
      CHECK (provider IS NULL OR provider = 'whatsapp'),
  ADD CONSTRAINT ck_internal_message_has_no_ref
      CHECK (direction <> 'INTERNAL' OR external_message_ref IS NULL);

CREATE FUNCTION turab.enforce_message_provider_channel() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.provider IS NOT NULL AND NOT EXISTS (
       SELECT 1 FROM turab.communication_threads
        WHERE thread_id = NEW.thread_id AND channel = 'WHATSAPP') THEN
    RAISE EXCEPTION 'communication_messages: provider % outside a WHATSAPP thread',
      NEW.provider;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_message_provider_channel
  BEFORE INSERT ON turab.communication_messages
  FOR EACH ROW EXECUTE FUNCTION turab.enforce_message_provider_channel();

-- Part B: messages are append-only; delivery_status moves forward (G7-5) --------
-- Accepted changes of delivery_status, and no other:
--   UNKNOWN -> QUEUED | SENT | DELIVERED | READ        (never UNKNOWN -> FAILED)
--   QUEUED -> SENT -> DELIVERED -> READ, forward only, steps may be skipped
--   QUEUED | SENT -> FAILED                            (FAILED is final)
CREATE FUNCTION turab.guard_communication_message() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
  rank_old integer;
  rank_new integer;
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'communication_messages: DELETE refused (append-only)';
  END IF;
  IF (NEW.message_id, NEW.thread_id, NEW.provider, NEW.external_message_ref,
      NEW.direction, NEW.message_type, NEW.body_text, NEW.media_ref,
      NEW.occurred_at, NEW.sent_by_account_id, NEW.metadata, NEW.created_at)
     IS DISTINCT FROM
     (OLD.message_id, OLD.thread_id, OLD.provider, OLD.external_message_ref,
      OLD.direction, OLD.message_type, OLD.body_text, OLD.media_ref,
      OLD.occurred_at, OLD.sent_by_account_id, OLD.metadata, OLD.created_at) THEN
    RAISE EXCEPTION 'communication_messages: only delivery_status may change';
  END IF;
  IF NEW.delivery_status IS NOT DISTINCT FROM OLD.delivery_status THEN
    RETURN NEW;
  END IF;
  rank_old := array_position(ARRAY['QUEUED','SENT','DELIVERED','READ']::text[],
                             OLD.delivery_status::text);
  rank_new := array_position(ARRAY['QUEUED','SENT','DELIVERED','READ']::text[],
                             NEW.delivery_status::text);
  IF (OLD.delivery_status = 'UNKNOWN' AND rank_new IS NOT NULL)
     OR (rank_old IS NOT NULL AND rank_new IS NOT NULL AND rank_new > rank_old)
     OR (NEW.delivery_status = 'FAILED' AND OLD.delivery_status IN ('QUEUED', 'SENT')) THEN
    RETURN NEW;
  END IF;
  RAISE EXCEPTION 'communication_messages: delivery_status % -> % refused',
    OLD.delivery_status, NEW.delivery_status;
END $$;
CREATE TRIGGER trg_guard_communication_message
  BEFORE UPDATE OR DELETE ON turab.communication_messages
  FOR EACH ROW EXECUTE FUNCTION turab.guard_communication_message();

-- Part C: a webhook event is immutable but for its processing (G7-2 (v)) --------
CREATE FUNCTION turab.guard_webhook_event() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'webhook_events: DELETE refused';
  END IF;
  IF (NEW.webhook_event_id, NEW.provider, NEW.provider_event_id, NEW.event_type,
      NEW.payload, NEW.received_at)
     IS DISTINCT FROM
     (OLD.webhook_event_id, OLD.provider, OLD.provider_event_id, OLD.event_type,
      OLD.payload, OLD.received_at) THEN
    RAISE EXCEPTION 'webhook_events: only the processing fields may change';
  END IF;
  IF OLD.processing_status NOT IN ('RECEIVED', 'FAILED') THEN
    RAISE EXCEPTION 'webhook_events: a % event is final', OLD.processing_status;
  END IF;
  IF NEW.processing_status NOT IN ('PROCESSED', 'IGNORED', 'FAILED') THEN
    RAISE EXCEPTION 'webhook_events: % -> % refused',
      OLD.processing_status, NEW.processing_status;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_guard_webhook_event
  BEFORE UPDATE OR DELETE ON turab.webhook_events
  FOR EACH ROW EXECUTE FUNCTION turab.guard_webhook_event();

-- Part D (D2, decided in the review of 4aed49b): six keys RESTRICT; a thread never
-- changes after INSERT, but for last_message_at moving forward ----------------
ALTER TABLE turab.communication_threads
  DROP CONSTRAINT communication_threads_party_id_fkey,
  ADD CONSTRAINT communication_threads_party_id_fkey FOREIGN KEY (party_id)
      REFERENCES turab.parties(party_id) ON DELETE RESTRICT,
  DROP CONSTRAINT communication_threads_request_id_fkey,
  ADD CONSTRAINT communication_threads_request_id_fkey FOREIGN KEY (request_id)
      REFERENCES turab.requests(request_id) ON DELETE RESTRICT,
  DROP CONSTRAINT communication_threads_property_id_fkey,
  ADD CONSTRAINT communication_threads_property_id_fkey FOREIGN KEY (property_id)
      REFERENCES turab.properties(property_id) ON DELETE RESTRICT,
  DROP CONSTRAINT communication_threads_opportunity_id_fkey,
  ADD CONSTRAINT communication_threads_opportunity_id_fkey FOREIGN KEY (opportunity_id)
      REFERENCES turab.opportunities(opportunity_id) ON DELETE RESTRICT,
  DROP CONSTRAINT communication_threads_created_by_account_id_fkey,
  ADD CONSTRAINT communication_threads_created_by_account_id_fkey
      FOREIGN KEY (created_by_account_id)
      REFERENCES turab.user_accounts(account_id) ON DELETE RESTRICT;
ALTER TABLE turab.communication_messages
  DROP CONSTRAINT communication_messages_sent_by_account_id_fkey,
  ADD CONSTRAINT communication_messages_sent_by_account_id_fkey
      FOREIGN KEY (sent_by_account_id)
      REFERENCES turab.user_accounts(account_id) ON DELETE RESTRICT;

CREATE FUNCTION turab.guard_communication_thread() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF TG_OP = 'DELETE' THEN
    RAISE EXCEPTION 'communication_threads: DELETE refused';
  END IF;
  IF (NEW.thread_id, NEW.channel, NEW.party_id, NEW.request_id, NEW.property_id,
      NEW.opportunity_id, NEW.external_thread_ref, NEW.opened_at, NEW.archived_at,
      NEW.created_by_account_id)
     IS DISTINCT FROM
     (OLD.thread_id, OLD.channel, OLD.party_id, OLD.request_id, OLD.property_id,
      OLD.opportunity_id, OLD.external_thread_ref, OLD.opened_at, OLD.archived_at,
      OLD.created_by_account_id) THEN
    RAISE EXCEPTION 'communication_threads: a thread''s links never change';
  END IF;
  IF OLD.last_message_at IS NOT NULL
     AND (NEW.last_message_at IS NULL OR NEW.last_message_at < OLD.last_message_at) THEN
    RAISE EXCEPTION 'communication_threads: last_message_at moves forward only';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_guard_communication_thread
  BEFORE UPDATE OR DELETE ON turab.communication_threads
  FOR EACH ROW EXECUTE FUNCTION turab.guard_communication_thread();
```

**The downgrade, in reverse order:**
- drops the four triggers and their functions;
- drops the three CHECKs of part A, and part E's CHECK and index;
- restores the six keys to `ON DELETE SET NULL`.

**The step 1 tests,** each refusal named by its message:
- **Part E:**
  - the pre-check refuses a database holding an unscoped or a shared
    WHATSAPP reference, naming the counts;
  - an unscoped reference is refused (CHECK);
  - a second WHATSAPP thread with the same reference is refused (23505 on
    `ux_whatsapp_thread_ref`);
  - **two concurrent inserts of one reference:** the second waits on the
    first (a `pg_blocking_pids` witness), and is refused after its COMMIT,
    or accepted after its ROLLBACK (M4's pattern);
  - the same reference on a PHONE thread, and a NULL reference, are not
    constrained.
- **Part A:** the four refusals.
- **Part B:**
  - **accepted:**
    - UNKNOWN → QUEUED, SENT, DELIVERED and READ;
    - every forward move between QUEUED and READ, skipped steps included;
    - QUEUED → FAILED and SENT → FAILED;
    - an UPDATE that does not change the status;
  - **refused, each by its message:**
    - **UNKNOWN → FAILED;**
    - every backward move; anything → UNKNOWN;
    - DELIVERED → FAILED and READ → FAILED;
    - anything from FAILED;
    - every change of another column; DELETE.
- **Part C:**
  - every immutable field; DELETE; leaving PROCESSED and IGNORED refused;
  - RECEIVED → FAILED → PROCESSED accepted.
- **Part D:**
  - the deletion of each of the six named parents refused;
  - every link and attribution change refused, at depth 1 and from inside a
    test trigger (depth 2);
  - `last_message_at` backwards refused, forwards accepted;
  - a thread's DELETE refused.
- **Every guard is labelled trigger-level** (K06).

### 5.2 CORRECTION-007 (DECIDED in the review of `4aed49b`): a 500 for the webhook

**Decided: the correction is adopted.** It is to be written as CORRECTION-005
was:
- an entry of `docs/contract/CONTRACT_CORRECTIONS.yaml`, with its own
  `CORRECTION-007-*.md`;
- the effective contract regenerated from it, and checked by the gate ("the
  effective contract is current");
- delivered in step 3, before the route.

When this section was written, the effective contract stated a `500` for
**no** operation (searched: no `'500'` in `openapi_effective_v0.2.3.yaml`).
*(Revision 14: it now states CORRECTION-007's, and CORRECTION-008's 503, on
this operation only.)*

- **The operation:** `postWebhooksWhatsapp`.
- **The change:** a `500` response, `application/problem+json`, with the code
  `WEBHOOK_PROCESSING_FAILED`.
- **Its description, as adopted:** "The event is stored (its
  `provider_event_id` is recorded) and was not processed. Deliver the same
  `provider_event_id` again; a later delivery completes it once."
  *(Revision 14, the review of `3dfb717`: "The event is stored (its
  provider_event_id is recorded); the result of its processing could not be
  confirmed. Deliver it again with the same provider_event_id; the event's
  record decides the redelivery, which completes it once or replays it.")*
- **Its nature:** an **addition** to the frozen contract's responses, not a
  narrowing.
- **Unchanged:** 200, 400 and 401.
- **The precedent, and why it did not settle this:** Slice 4's typed 500
  for its policy faults was set by a review decision without a contract
  entry (`SLICE_4_PLAN.md` G4-15). Here the 500 is a signal the relay acts
  on, so it is in the contract.

---

## 6. Tests and closure evidence

### 6.1 The four mandatory tests

| # | Test, as written | Proof planned |
|---|---|---|
| 1 | "repeated provider webhook creates one message" | the same signed envelope posted twice, and concurrently: one event row, one message (one interaction from step 4, G7-17 (i)). A PROCESSED replay writes nothing; a FAILED or RECEIVED event is completed by the replay, still one message (G7-2 (v)) |
| 2 | "same provider message id cannot be inserted into another thread" | the same `(whatsapp, ref)`, by staff and by webhook, into a second thread: a typed 409, or IGNORED, and no row. The NULL-provider path is refused by the service and by `0008` (A) |
| 3 | "thread/opportunity links are checked by service invariant" | each rule of G7-6, rule 0 (SALE) included, with an inconsistent link refused, writing nothing; the seller's thread about the buyer's opportunity accepted; the links never changed afterwards, and the named parents' deletion refused (D2) |
| 4 | "phone decision can be linked to later written confirmation observation" | G7-10 end to end over HTTP |

### 6.2 Red-team and RFC-001 cases

| Case | Planned |
|---|---|
| **J01** | mandatory test 1 |
| **J02** | mandatory test 2 |
| **J03** | as claimed in G7-9 (6): **no content stored without a consent valid at write time**, in messages, in the event store and in logs. Retention is not claimed |
| **S41** | a wrong or missing relay signature is 401 before any write. The test's own wording: it proves the relay's origin, not Meta's |
| **S42** | a replay of a completed event is 200, with no duplicate |
| **G7-2 (iv)** | the four failure tests: a failure in processing, a stop after RECEIVED, a failure of the status update, a replay during the claim |
| **K05** | each staff POST replays with its key; another body on the key is 409 |
| **K06** | not claimed; trigger-level guards listed as trigger level |

### 6.3 Authorization
- **The two staff POSTs:** ADMIN and OPERATOR allowed; REVIEWER and CUSTOMER
  refused (403) and recorded; anonymous refused (401).
- **The webhook:** stays in the closed list of six.
- **The timeline:** its widened item checked by an exact key-set test
  (R9.5).
- **The matrix** gains the three operations.

### 6.4 Closure evidence (no STOP GATE)

As Slice 6's:
- a generated `SLICE_7_EVIDENCE.md` with `--check`, bound to a clean-tree
  run;
- the writes to the four tables inventoried **by kind**;
- **the event store's RECEIVED and FAILED counts** at the end of the run;
- **the trust boundary of G7-2 (ii), as worded there;**
- **condition R-1 listed as UNMET** until the relay is built and its seven
  duties are tested (G7-2 (ii); (a2) decided);
- Slice 6's carried limits, none as proven.

### 6.5 Step 0: done

The measurements are recorded in `evidence/SLICE7-PLAN-MEASUREMENTS.txt` and
its script. They were authorized in the review of `dcebe46`, run twice with
identical results, and are ours.

---

## 7. Acceptance conditions

1. **The contract changes only by three corrections** *(revision 14; two
   before G7-17 (ii) added CORRECTION-008)*:
   - **CORRECTION-006,** which narrows `CommunicationThreadCreate.party_id`
     to required (G7-7 (a)), approved;
   - **CORRECTION-007,** which adds the webhook's `500
     WEBHOOK_PROCESSING_FAILED` (decided in the review of `4aed49b`; its
     meaning narrowed in the review of `3dfb717`);
   - **CORRECTION-008,** which adds the webhook's `503 WEBHOOK_NOT_READY`
     (G7-17 (ii), (vi); widened in the review of `3dfb717`).

   Each is an entry of `CONTRACT_CORRECTIONS.yaml`, from which the
   effective contract is regenerated and checked by the gate. The relay's
   header is outside the OpenAPI (G7-2 (ii)).
2. **A completed webhook event, replayed, writes nothing;** an incomplete
   one is completed once (J01, S42, G7-2 (v)).
3. **A provider message identity is global** (J02), the NULL case included.
4. **An unverified webhook writes nothing** (S41). Its check is described
   as the relay's origin, never as Meta's signature.
5. **Thread links are consistent at creation, SALE checked, and never
   changed afterwards** (D2); a WHATSAPP thread's reference is scoped and
   unique (G7-3).
6. **A phone decision's confirmation link is append-only,** and claims no
   legal value.
7. **No content is stored without a consent valid at write time,** in any
   table or log (G7-9). Retention is not claimed (OQ7-1).
8. **What staff can read is exactly what G7-8 decides,** held by a key-set
   test.
9. **The writes to the four tables are exactly those decided,** by kind.
10. **SALE only,** checked (G4-5R open). **K06 UNPROVEN.** **No AI.**
11. **A processing failure is recorded,** or the event keeps its previous
    status, and no half-written message remains (G7-2 (iv)).
12. **Condition R-1** ((a2), decided) is listed as UNMET, and is required
    before any real event. Meta's verification is never counted as done in
    this slice.

---

## 8. Sequence

| Step | Content | Depends on |
|---|---|---|
| 0 | the measurements M1–M8 | **done** (authorized in the review of `dcebe46`) |
| 1 | migration `0008` (parts E, A, B, C, D2); tests, mutations | **CLOSED at `7e8993d`** (review of `7e8993d`; `SLICE_7_STEP1_DELIVERY.md`) |
| 2 | threads, the link invariant, staff messages, identity and consent rules; CORRECTION-006 if decided | G7-4, G7-6, G7-7, G7-9, G7-11; **G7-16** (i–vi) and CORRECTION-006's reading, **decided** (review of `0f423d2`); **CLOSED at `6d8815d`** (review of `6d8815d`; `SLICE_7_STEP2_DELIVERY.md`) |
| 3 | CORRECTION-007 written; the webhook: body limit, verification, the content-free event store, the transactions and their failure record, resolution, statuses, replay and the recovery command | G7-2, G7-3, G7-5, G7-9, G7-15; CORRECTION-007; **authorized** (review of `6d8815d`); no real event before R-1; **G7-17 decided** (review of `bf1fe3d`) |
| 4 | the timeline (G7-8) and the confirmation link (G7-10) | G7-8, G7-10; G7-17 (i); **G7-18, decided** (review of `e18271a`) |
| 5 | the mandatory and red-team tests end to end, mutations, the closure evidence | all; **G7-19, to be decided** |

Each step is delivered with its tests and its mutation record, and is
reviewed before the next begins. A defect found in a step is measured before
it is fixed.

---

## 9. Document identity

This file's sha256 is recorded in `docs/gate/evidence/DOCUMENT-HASHES.txt`
at the commit that adds it.
