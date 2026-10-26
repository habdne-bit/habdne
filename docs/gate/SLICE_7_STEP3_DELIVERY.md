# Slice 7 · step 3 — the WhatsApp webhook; CORRECTION-007 and CORRECTION-008

**Approved scope.**
- **Step 3 authorized** in the review of `6d8815d`, with no real event
  before R-1.
- **G7-17 decided** in the review of `bf1fe3d` (plan revision 13): the seven
  points of step 3, with a 503 `WEBHOOK_NOT_READY` under a new
  CORRECTION-008, and `response_additions` unique per (operation, status).
- **The review of `3dfb717`** (plan revision 14): the two 400 codes
  accepted; one contractual blocker, answered in `5e152ff` (§2); the stale
  statements of the plan corrected.
- **The operation:** `postWebhooksWhatsapp`, unauthenticated (RFC-001
  R10.4) and verified (R10.5).
- **The rules it follows:** G7-2 (the boundary, T1 and T2, the replay table,
  the recovery), G7-3, G7-4, G7-5, G7-9, G7-15, G7-16 (iv), G7-17 (i)–(vii).

**What this step does not contain:**
- any `interactions` row (G7-17 (i): step 4, with the one-time backfill of
  the earlier messages);
- the timeline (G7-8) and the confirmation link (G7-10), step 4;
- the relay (R-1). **R-1 is UNMET: no real event may be received.**

**Status: DELIVERED FOR REVIEW** with the commit that adds this note. **Not closed.**

**Submitted for decision with this delivery:**
1. **The texts of CORRECTION-007 and CORRECTION-008** (§4), and the
   resulting effective contract.
2. **Readings of ours,** stated in §3, none of them a decision of the plan.

**Commits:**
- `3dfb717`: the code, the tests, the two corrections, the mutation script
  and its first trial run (64/64 killed, on the working tree before the
  commit);
- `5e152ff`: the review of `3dfb717` answered (§2); plan revision 14;
- `56659db`: the before record (§5);
- `3de3e06`: the first mutation pair at `56659db` differed by one test
  under T3, by timing; a deterministic test added; both records kept (§6);
- `11e36b3`: the mutation records at `3de3e06` (§6);
- `e5fc64b`, `a7a4bad`, `6342c86`: the evidence round (§7).

---

## 1. What step 3 contains

### 1.1 Before T1: the checks, in G7-17 (iii)'s order, each writing nothing

| # | Check | Refused with |
|---|---|---|
| 1 | the body's size: over 64 KiB, on `Content-Length` before reading and counted while reading (G7-15) | 400 `WEBHOOK_BODY_TOO_LARGE` |
| 2 | the secret `TURAB_RELAY_SIGNING_SECRET`, absent or empty | 503 `WEBHOOK_NOT_READY` (CORRECTION-008) |
| 3 | `X-Turab-Relay-Signature: sha256=<64 lower-case hex>`, the HMAC-SHA256 of the raw body under the secret encoded UTF-8, compared with `hmac.compare_digest` | 401 `UNAUTHENTICATED` |
| 4 | the JSON and the envelope (`provider_event_id` a non-empty string, `event_type` a string, `payload` an object) | 400 `WEBHOOK_ENVELOPE_NOT_VALID` |
| 5 | for `message` and `status`, G7-3's keys, each a string; `occurred_at` an RFC 3339 date-time with its offset; `status` one of the six; `body_text` and `media_ref`, if present, strings | 400 `WEBHOOK_ENVELOPE_NOT_VALID` |

- **The signature proves the relay's origin, not Meta's** (S41). Meta's is
  the relay's to check (R-1).
- **An unknown `event_type`** passes, is stored by T1, and is IGNORED
  `UNKNOWN_EVENT_TYPE` (G7-3).
- **The details** name a key, never a value of the request.

### 1.2 T1, the event

- **The content-free payload** (G7-9 (1)), built from an allow-list:
  `provider_event_id`, `event_type`, `external_message_ref`, `thread_ref`,
  `occurred_at`, `message_type`, `status`, and `has_body`, `has_media`.
  Every other key, the content first, is dropped before the insert.
- `INSERT … ON CONFLICT (provider, provider_event_id) DO NOTHING`, then, on a
  conflict, the stored status (G7-2 (v)).

### 1.3 T2, the processing (READ COMMITTED, one connection)

1. the claim, `FOR UPDATE NOWAIT` (55P03: in flight, an empty 200);
2. `SAVEPOINT`;
3. resolution and its writes:
   - **a message:** the WHATSAPP thread of `thread_ref`, `FOR UPDATE` first
     (G7-16 (iv)), else IGNORED `UNKNOWN_THREAD`; a recorded reference is
     IGNORED `MESSAGE_REF_TAKEN`, by the pre-check or by the insert's 23505
     on the reference's key (the backstop); the content kept only under the
     archive consent of the thread's party, bound to the thread and
     current, read `FOR SHARE`, else stored without it
     (`NO_ARCHIVE_CONSENT`); an INBOUND message, its metadata
     `content_archived`, `webhook_event_id` and the reason withheld; the
     thread's `last_message_at`, moved to a later time only; audit rows
     with a NULL actor, the content withheld;
   - **a status:** the message `FOR UPDATE`, else IGNORED `UNKNOWN_MESSAGE`;
     G7-5's table checked before the UPDATE, else IGNORED
     `STATUS_TRANSITION_NOT_ACCEPTED`; the UPDATE audited;
4. the event PROCESSED or IGNORED, with its code; COMMIT.

A failure in step 3 rolls back to the savepoint, which keeps the claim's
lock, and records FAILED `PROCESSING_FAILED` in the same T2.

### 1.4 The answers

| Case | Answer | Access record's outcome |
|---|---|---|
| new, processed or ignored | 200, empty | `PROCESSED`, `IGNORED` |
| a replay of a final event | 200, empty, nothing written | `REPLAYED` |
| in flight (55P03) | 200, empty, nothing written | `IN_FLIGHT` |
| T1 raised | 503 `WEBHOOK_NOT_READY` | `ACCEPTANCE_NOT_CONFIRMED` |
| T2 FAILED, recorded | 500 `WEBHOOK_PROCESSING_FAILED` | `FAILED` |
| T2 raised | 500 `WEBHOOK_PROCESSING_FAILED` | `PROCESSING_LOST` |
| the four refusals of §1.1 | 400, 503, 401, 400 | `BODY_TOO_LARGE`, `SECRET_NOT_CONFIGURED`, `SIGNATURE_NOT_VALID`, `ENVELOPE_NOT_VALID` |

**One access record per answer** (G7-17 (vii)), to the log stream, never to
`audit_log`: the HTTP status, the outcome and, once stored, the event's id.
Never the body, the signature, the secret, or a reference the envelope
carried.

### 1.5 The recovery command

`db/ops/recover_webhook_events.py`: T2 again on every FAILED event and every
RECEIVED one older than 5 minutes, `FOR UPDATE SKIP LOCKED`, from the
content-free payload. A message whose content existed is stored without it
(`RECOVERED_WITHOUT_CONTENT`): **the accepted limit of G7-2 (v); not a full
recovery of the archive.** It prints the count of each outcome and nothing
else; its audit rows carry the context `recoverWebhookEvents`.

## 2. The review of `3dfb717`: the blocker and its answer

**The blocker.** A T1 that raised was answered `500 INTERNAL_ERROR`, while
CORRECTION-007 gives the same operation a 500 with the fixed code
`WEBHOOK_PROCESSING_FAILED` and a description presuming the event recorded.
One status carried two meanings in the effective contract.

**The answer (`5e152ff`):**
- **a T1 that raised, after every check of the request passed, is
  `503 WEBHOOK_NOT_READY`.** CORRECTION-008's description: "The event's
  acceptance could not be confirmed: the webhook cannot verify deliveries
  now, or storing the event did not confirm. Deliver it again with the same
  provider_event_id." It claims neither "recorded" nor "nothing recorded";
- **CORRECTION-007's description:** "The event is stored (its
  provider_event_id is recorded); the result of its processing could not be
  confirmed. Deliver it again with the same provider_event_id; the event's
  record decides the redelivery, which completes it once or replays it."
  Its note tells FAILED (recorded) from `PROCESSING_LOST` (T2 raised;
  whether its COMMIT took effect is unknown);
- **the route answers no other 5xx** (tested: no `INTERNAL_ERROR` in the
  route, and its codes are exactly the five);
- **the three tests asked for:**

  | Test | Answer | The event | The redelivery |
  |---|---|---|---|
  | T1 fails before its COMMIT | 503 | no row | stored and processed: one message |
  | T1's COMMIT takes effect, its answer lost | 503 | RECEIVED | processed once: one event, one message |
  | T2's COMMIT takes effect, its answer lost | 500, `PROCESSING_LOST` | PROCESSED | a replay: an empty 200, nothing written, one message |

- **`archived_at`** (§3, reading 7): resolution and the consent check
  unchanged, tested.

**What we could not check.** The review cites PostgreSQL 16's documentation
of `pg_xact_status` (§9.27) for a client disconnected while a COMMIT is in
progress. This environment could not fetch the page (DNS: `ENOTFOUND
www.postgresql.org`) and holds no local copy. The notes state it as the
reviewer's citation, not as our quotation. Measured locally: PostgreSQL
16.15 has the function ("commit status of transaction").

## 3. Readings of ours (not decisions of the plan)

1. **The 400 codes** `WEBHOOK_BODY_TOO_LARGE` and
   `WEBHOOK_ENVELOPE_NOT_VALID` are our names. **Accepted in the review of
   `3dfb717`.** The 401 is the existing `UNAUTHENTICATED`.
2. **An inbound message's `message_type` is not restricted.** G7-16 (v)
   reserves `PHONE_DECISION` and `CONFIRMATION_LINK` for the staff command
   until G7-10. A webhook message of either type is stored as given
   (tested with `CONFIRMATION_LINK`); it carries no meaning until step 4
   gives one.
3. **A status equal to the message's current one is IGNORED
   `STATUS_TRANSITION_NOT_ACCEPTED`**, as G7-5's table accepts only a later
   status. `test_g7_5_the_table_is_the_triggers` shows the service's table
   is exactly `0008` part B's, pair for pair.
4. **A status event's `occurred_at` orders nothing.** Statuses apply in
   arrival order; a backward one is refused by the table.
5. **An inbound message's `delivery_status` is UNKNOWN,** the column's
   default.
6. **The size limit is inclusive:** 65,536 bytes are read; 65,537 refused.
7. **`archived_at` alone refuses nothing** (the review of `3dfb717`): no
   rule of the plan makes it a refusal. Measured: `0008`'s thread guard
   refuses an UPDATE of `archived_at` ("a thread's links never change"), so
   a thread carries one only from its insert, and no command sets it
   (F7-9).
8. **`message_type` is not checked against a list** (G7-3 gives none), so
   any string is stored.
9. **An `Authorization` header is not read** on this operation (R10.4):
   tested with an unknown bearer and with an administrator's.

## 4. CORRECTION-007 and CORRECTION-008

- **The texts:** `docs/contract/CORRECTION-007-webhook-processing-failed.md`
  and `CORRECTION-008-webhook-not-ready.md`. **Submitted, not approved:**
  neither entry carries an `approved` date.
- **The mechanism** (G7-17 (vi)): `response_additions`, validated by
  `load_response_additions`; refused: an unknown key, a missing or reused
  id, no decision, an operation absent from the frozen contract, a status
  that is not a 5xx of three digits, a second addition of the same
  (operation, status), a status the operation already declares, stale
  `frozen_statuses`, a code that is not an upper-case identifier, a blank
  description. The overlay's header names this as the one exception to its
  invariant 1.
- **The effective contract** gains exactly two responses on
  `postWebhooksWhatsapp`, 500 and 503, each `application/problem+json` with
  `Problem` and an `x-turab-correction` of kind `RESPONSE_ADDITION`.
  `test_correction_001.py` and `test_correction_007_008.py` compare it with
  expectations written independently of `added_response`.
- **Each code** is a `ProblemCode` whose catalogue status is its entry's.

## 5. Before the fix (measured)

`evidence/SLICE7-STEP3-BEFORE.txt`: the 151 tests of the two new files, at
their state of `5e152ff`, in an isolated worktree at `e64ba93`. **150 failed, 1 passed.**
- **Failed on:** the absent route (404), the absent service (ImportError),
  the absent `response_additions` (KeyError) and codes.
- **Passed:** the frozen operation unchanged, a fact of the package.
- **Two measurements, the record says so:** the first had 119 setup errors
  (alembic not on PATH), which measure nothing; the second is the record.

## 6. Mutation evidence

`evidence/SLICE7-STEP3-MUTATIONS.txt` and `-REPEAT.txt`, both at `3de3e06`
(a clean tree, source fingerprint `4a09506f…3ed7`), in two parts, one per
test file. **65/65 fail; none survives**, in both runs, which are identical
line for line.

| Group | Mutations, tests failing |
|---|---|
| V: before T1 | V1 7 · V2 1 · V3 6 · V4 1 · V5 1 · V6 3 · V7 1 · V8 2 · V9 3 · V10 13 · V11 1 · V12 2 · V13 13 · V14 2 · V15 2 · V16 2 |
| E: the content-free event | E1 2 · E2 2 |
| M: a message | M1 1 · M2 1 · M3 1 · M4 7 · M5 1 · M6 6 · M7 1 · M8 2 · M9 2 · M10 2 · M11 1 · M12 4 |
| S: a status | S1 2 · S2 2 · S3 2 · S4 2 · S5 1 · S6 10 · S7 1 |
| T: T1, T2, the recovery | T1 20 · T2 4 · T3 2 · T4 1 · T5 2 · T6 4 · T7 1 · T8 1 · T9 1 |
| R: the answers | R1 39 · R2 2 · R3 1 · R4 2 · R5 59 · R6 4 · R7 3 · R8 5 · R9 2 |
| L: the loader | L1 2 · L2 1 · L3 1 · L4 2 · L5 1 · L6 1 · L7 3 · L8 1 · L9 1 · L10 1 |

**`test_mandatory_test_1_concurrent_deliveries_make_one_message` is
deselected from the mutation runs** (it runs in the suite, §7):
- **why:** the first pair, at `56659db`, killed 65/65 in each run, but was
  not identical. Under T3 (the claim takes a final event), the eight-way
  concurrent test failed in the second run only: whether a second delivery
  reaches the claim after the first one's COMMIT depends on timing. The
  real code passed it in both baselines;
- **what was checked first:** no mutation, in either run, was killed by that
  test alone;
- **what replaces it for T3:** `test_t2_on_a_final_event_is_final_and_writes_nothing`,
  deterministic. T3 now fails it and the recovery test;
- **the precedent:** `mutate_0008.py` deselects a test the same way;
- **both records of the first pair are kept**
  (`evidence/SLICE7-STEP3-MUTATIONS-RACE-PAIR.txt`, `-REPEAT.txt`).

**The first trial run** (`evidence/SLICE7-STEP3-MUTATIONS-FIRST-RUN.txt`, on
the working tree before `3dfb717`): 64/64 killed. The answer to the review
of `3dfb717` changed R2's anchor and added R9.

**Not mutated, each with its reason** (`mutate_slice7_step3.py`):
- **the message's pre-check of a recorded reference:** the insert's
  backstop gives the same IGNORED, so it is equivalent; the backstop is M5;
- **the recovery's SKIP LOCKED against NOWAIT:** 55P03 maps to the same
  IN_FLIGHT; tested directly;
- **the claim's NOWAIT against a plain FOR UPDATE:** a kill, but only by the
  barrier test timing out; left out of the run.

## 7. The evidence round

Every row ran on a clean tree, with source fingerprint `4a09506f…3ed7`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Suite (`record_test_run.py`) | **3005 passed, 0 failed, 0 errors, 0 skipped** | `6342c86` (run at `a7a4bad`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |
| PostgreSQL gate | PASS: ALL DATABASE-LEVEL CONTRACT TESTS PASSED, 70 PASS notices; the effective contract current (10 entries); the effective contract, inventory and policy table hold the same 67 operations | `a7a4bad` (run at `e5fc64b`) | `evidence/gate-run.txt` |
| Authorization matrix | 212 rules (13 for step 3); suite 3005/3005 | `e5fc64b` (run at `11e36b3`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| Step 3 mutations | 65/65 fail, twice, identical | `11e36b3` (run at `3de3e06`) | §6 |
| Before the fix | 150 failed, 1 passed, at `e64ba93` | `56659db` | §5 |

**The event store at the end of the suite run** (G7-2 (v), §6.4), in the
suite's database:

| Status | Code | Count |
|---|---|---|
| PROCESSED | — | 58 |
| IGNORED | `STATUS_TRANSITION_NOT_ACCEPTED` | 13 |
| IGNORED | `MESSAGE_REF_TAKEN` | 5 |
| IGNORED | `UNKNOWN_MESSAGE` | 2 |
| IGNORED | `UNKNOWN_THREAD` | 2 |
| IGNORED | `UNKNOWN_EVENT_TYPE` | 1 |
| **RECEIVED** | — | **1** |
| **FAILED** | — | **0** |

- **The one RECEIVED event** is left on purpose by
  `test_recovery_completes_a_failed_event_and_skips_a_fresh_received_one`:
  younger than 5 minutes, the recovery must skip it. Checked: its thread
  holds one other event, PROCESSED (the FAILED one the recovery completed),
  and no message names it.
- **No FAILED event remains:** every test that makes one completes it, by a
  redelivery or by the recovery.
- **These are test events.** No real event was received.

**The earlier slices' records are not regenerated.**
`slice6_evidence.py --check` and `stop_gate_e_evidence.py --check` each
report ONE problem: the document is stale.

**Limits that are part of these results:**
- **The guards hold against the application's ordinary statements only.**
  The tests run as `turab`, a superuser (EN-02). **K06 stays UNPROVEN,** an
  independent condition before the release gate.
- **The relay's signature proves the relay's origin, not Meta's.** R-1
  stays UNMET.
- **The SALE scope is not widened.**
- **These results are ours.** No independent run exists.

## 8. What remains

- **The review of this delivery,** and the approval of CORRECTION-007's and
  CORRECTION-008's texts.
- **Step 4** (the timeline, the interactions with their one-time backfill,
  the confirmation link) does not start before that review.
- **R-1:** the relay and its seven duties, the redelivery on 500, on 503 and
  on a timeout among them. **No real event before it.**
- **K06 UNPROVEN;** the scope SALE only. **This is not a release
  authorization.**
