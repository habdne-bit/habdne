# Slice 7 · step 4 — one interaction per message, the backfill, the timeline's `message`, the confirmation link

**Approved scope.**
- **Step 4 authorized** in the review of `23b99b6`, within the plan's scope.
- **G7-18 decided** in the review of `e18271a` (plan revision 18): the nine
  options (a), with the limits of that review's table.
- **The rules it follows:** G7-8 (a), G7-10 (a), G7-11, G7-17 (i), G7-18
  (i)–(ix).

**What this step does not contain:**
- a migration: **no `0009`**. "One interaction per message" holds within the
  service's paths, and is not a constraint of the database;
- any new HTTP operation: the timeline is the frozen
  `getPartiesPartyIdTimeline`, and the link is the existing message
  command;
- the relay (R-1). **R-1 is UNMET: no real event may be received.**

**Status: DELIVERED FOR REVIEW** with the commit that adds this note. **Not
closed.**

**Submitted for decision with this delivery:**
1. **Four codes the plan names** (G7-18 (vii)), with their statuses, and the
   removal of `MESSAGE_TYPE_RESERVED` (§3).
2. **The maintenance of three closed tests,** of step 2 and of Slice 5 (§4).
3. **Readings of ours,** stated in §5.

**Commits:**
- `e1bdcbc`: plan revision 18 (the review of `e18271a`);
- `747e5b0`: the code, the tests, the scripts, and the first trial run of
  the mutations (31/31 killed, on the working tree before the commit);
- `e357322`: the Slice 5 tests maintained (§4);
- `e02ee7e`, `11971a3`: four tests made non-vacuous; the before record (§6);
- `5ef657b`: the mutation records (§7);
- `3950308`: step 2's and step 3's mutations rerun on this tree (§7);
- `0183967`, `9162ca0`, `4c064e3`: the evidence round (§8).

---

## 1. What step 4 contains

### 1.1 One interaction per message (G7-8 (a), G7-18 (i)–(iv))

`services/message_interactions.py`, `write`, called by the two writers of a
message **in the message's own transaction**:
- the staff command (`postCommunicationThreadsThreadIdMessages`), after the
  message and the thread's move;
- the webhook's T2, inside its savepoint: a processing failure rolls the
  interaction back with the message.

| Column | Value |
|---|---|
| `interaction_type` | `NOTE` for every INTERNAL; otherwise by the thread's channel: WHATSAPP → `WHATSAPP`, PHONE → `CALL`, SMS → `SMS`, EMAIL → `EMAIL`, IN_PERSON → `IN_PERSON`, WEB and OTHER → `OTHER` |
| `channel` | the thread's |
| `summary` | "Inbound message", "Outbound message" or "Internal note": no body, no reference |
| `party_id`, `request_id`, `property_id`, `opportunity_id`, `thread_id` | the thread's |
| `occurred_at` | the message's |
| `operator_account_id` | the message's `sent_by_account_id` (NULL for the webhook) |
| `outcome_code` | NULL |
| `metadata` | exactly `{"message_id": "<uuid>"}` |

Each row is audited by `audit_rows`, with the transaction's actor and
context (NULL for the webhook), the summary withheld (review of `6c6e614`).

**The guarantee, as decided:** within the service's paths. The two writers
write one each; the backfill writes only where none exists. A statement
outside the service could write a second row: no constraint refuses it.

### 1.2 The backfill (G7-17 (i), G7-18 (v))

`db/ops/backfill_message_interactions.py`, `message_interactions.backfill`:
- one transaction, READ COMMITTED, actor-less (audit context
  `backfillMessageInteractions`);
- its first statement takes a transaction-level advisory lock: a second
  backfill waits for the first to end, then its next statement reads what
  the first committed, and finds nothing left;
- it writes for every message with no interaction (`NOT EXISTS` on
  `metadata->>'message_id'`);
- it prints the count, and nothing else.

**Stated, as the review of `bf1fe3d` asks:** for the messages that existed
before step 4, the atomicity of a message with its interaction **does not
hold retroactively**. Their interaction is written later, by the backfill:
its `created_at` is the backfill's time, its `occurred_at` the message's.

### 1.3 The timeline's `message` (G7-8 (a), G7-18 (vi))

`services/timeline.py`:
- **one key added, `message`, on the item of an interaction that names a
  message, and on no other.** Every other item keeps Slice 1's exact keys;
- its keys: `message_id`, `direction`, `message_type`, `delivery_status`,
  `occurred_at`, `content_archived`; and `body_text` and `media_ref`, both,
  **only when `content_archived` is true**;
- read live from `communication_messages`, joined by the interaction's
  `metadata.message_id` through a uuid-guarded condition on the messages'
  primary key; `interactions.metadata` itself stays withheld;
- **REVIEWER reads archived content too,** within the operation's existing
  roles (ADMIN, OPERATOR, REVIEWER);
- the list stays audited once (R6.3c).

### 1.4 The confirmation link (G7-10 (a), G7-18 (vii), (viii))

In the existing staff message command:
- `PHONE_DECISION` and `CONFIRMATION_LINK` are accepted **only INTERNAL, in a
  PHONE thread** (reserved until now, G7-16 (v));
- a `CONFIRMATION_LINK` carries `metadata` with **exactly**
  `decision_message_id` and `observation_id`, each a uuid; every other type
  keeps G7-16 (iii) (`metadata` absent or empty);
- the decision: it exists, is an INTERNAL `PHONE_DECISION`, in the same
  thread; read `FOR SHARE`;
- the observation: it exists, is of kind `MESSAGE`, its `party_id` is the
  thread's party, its `observed_at` is **not NULL** and not before the
  decision's; read `FOR SHARE`, so a change in flight is waited for, then
  seen;
- the two ids are stored in the link's metadata, beside `content_archived`;
  nothing earlier is updated; several links may name one decision;
- **every refusal comes before the idempotency claim:** nothing written, no
  key consumed;
- G7-9's consent applies to a link's content as to any message;
- **an inbound message of either type** keeps step 3's behaviour: stored as
  given, never linkable (G7-18 (viii)).

**The link's limit, as decided:** it is valid **at its writing only**. 0007's
guard protects an observation cited by the tables it names, and a message's
metadata is not one of them, so the observation's survival or stability
afterwards is not claimed (tested: it can still change). **The link has no
legal value.**

## 2. The writers of `interactions`, by kind (G7-18 (ix))

| Writer | Module | Kind | Since |
|---|---|---|---|
| Slice 5's share, close and revalidate with a note | `services/opportunity_commands.py` (`_record`) | `STATUS_CHANGE` (share, close), `NOTE` (revalidate with a note) | Slice 5 |
| a staff message | `services/message_interactions.py` (`write`), from `services/communication.py` | by direction and channel (§1.1) | step 4 |
| a webhook message | the same `write`, from `services/webhooks.py` | `WHATSAPP`, INBOUND | step 4 |
| the backfill | the same `write`, from `backfill` | as for the message it backfills | step 4 |

- **One INSERT per module:** `test_g5_8_i_the_share_is_the_one_writer_of_interactions`
  computes the set from the tree (§4).
- **STOP GATE E stays the record of Slice 5's tree** (as decided): its
  `--check` on this tree reports the new writer, and that its document is
  stale. It is not regenerated.

## 3. Codes

- **Added, each 422; `field_errors` name a field, never a value or an id:**
  - `PHONE_DECISION_NOT_ACCEPTED`: the type outside an INTERNAL message of a
    PHONE thread;
  - `CONFIRMATION_LINK_NOT_ACCEPTED`: the same for a link, or its metadata
    not exactly its two uuids;
  - `DECISION_NOT_LINKABLE`: missing, another type or direction, another
    thread;
  - `OBSERVATION_NOT_LINKABLE`: missing, another kind or party, no party, no
    time, or before the decision.
- **Removed:** `MESSAGE_TYPE_RESERVED`. It was step 2's refusal of the two
  types until step 4 (G7-16 (v)); nothing answers it now, and a catalogue
  entry no path can answer would be a false statement.

## 4. Closed tests maintained (submitted for review)

Each follows from a decision; none changes a gate.
1. **Step 2,** `test_v_the_types_g7_10_gives_a_meaning_are_reserved`, renamed
   `…_are_internal_phone_only`: the reservation it tested is lifted by G7-18
   (vii); it now tests the rule that replaces it (refused OUTBOUND, and in a
   thread of another channel). Its matrix rule follows. Step 2's mutation
   script: M3 re-anchored on that rule, M21 on the line that now also
   carries a link's ids.
2. **Slice 5,** `test_g5_8_i_the_share_is_the_one_writer_of_interactions`:
   G7-8 (a) "changes G5-8 (i)'s single writer". It now pins the decided set,
   the opportunity commands and `message_interactions.py`, one INSERT each.
   Its name is kept, as the matrix and STOP GATE E cite it.
3. **Slice 5,** STOP GATE E's tests (`test_slice5_stop_gate_e.py`): their
   fixture runs the gate on a copy of the tree, and requires a passing
   baseline. The copy is now given Slice 5's writer set (Slice 7's writer
   removed from the copy only), so each experiment still refuses for its
   own reason; the gate itself is unchanged, and still reports the new
   writer on the real tree.

**What made them visible:** the first full run on `747e5b0` had 1 failure and
17 errors, all this one cause. The run after the maintenance: 3088 passed.

## 5. Readings of ours (not decisions of the plan)

1. **The decision's lock is not mutated:** a message's thread, type and
   direction are frozen by `0008` part B, so no change in flight can alter the
   decision's verdict. Kept as the plan's lock discipline; claimed by no
   test.
2. **The link's metadata is checked twice,** in the body and after the
   thread's lock, with the same refusal, both before the claim. The first is
   an equivalent mutant, and is not mutated.
3. **An observation with no party** is refused (`OBSERVATION_NOT_LINKABLE`):
   it cannot be "of the thread's party".
4. **A message interaction's party** is the thread's at the write. A thread
   whose party was nulled (`ON DELETE SET NULL`) gives an interaction no
   timeline shows, as for any interaction.
5. **The backfill's order** is the messages' `occurred_at`, then id: it
   decides only the order of the interaction ids' creation, nothing shown.

## 6. Before the fix (measured)

`evidence/SLICE7-STEP4-BEFORE.txt`: the 59 tests of the new file, in an
isolated worktree at `e1bdcbc`. **57 failed, 2 passed.**
- **Failed on:** no interaction written; the two types refused
  `MESSAGE_TYPE_RESERVED`; the module and the script absent; no `message`
  key.
- **Passed:** two facts of Slice 1's timeline, which step 4 must leave as they
  are (another item's keys; a customer refused).
- **Two measurements, the record says so:** the first gave 53 failed, 6
  passed. **Four of the six passed vacuously:** the base writes no
  interaction at all, so the three "writes no interaction" tests held, and
  the inventory test counted the deliberate non-message rows. Each was given
  a positive precondition the base fails; the second measurement is the
  record.

## 7. Mutation evidence

`evidence/SLICE7-STEP4-MUTATIONS.txt` and `-REPEAT.txt`, both at `11971a3`
(clean, source fingerprint `d06a9ac1…a9b6`). **31/31 fail; none survives**,
in both runs, which are identical line for line.

| Group | Mutations, tests failing |
|---|---|
| I: the interaction | I1 9 · I2 2 · I3 1 · I4 8 · I5 1 · I6 1 · I7 1 · I8 2 · I9 3 · I10 27 · I11 6 |
| B: the backfill | B1 2 · B2 4 · B3 2 |
| T: the timeline | T1 6 · T2 1 · T3 1 · T4 1 |
| L: the link | L1 1 · L2 1 · L3 1 · L4 1 · L5 1 · L6 1 · L7 1 · L8 2 · L9 2 · L10 1 · L11 1 · L12 2 · L13 2 |

**Not mutated, each with its reason** (`mutate_slice7_step4.py`): the
metadata's first check (equivalent, §5.2); the decision's `FOR SHARE` (§5.1);
the thread's lock and the webhook's savepoint, step 2's and step 3's.

**Step 2's and step 3's mutations, rerun on this tree** (`5ef657b`, clean):
51/51 and 68/68, none survives
(`evidence/SLICE7-STEP2-MUTATIONS-ON-STEP4-TREE.txt`,
`SLICE7-STEP3-MUTATIONS-ON-STEP4-TREE.txt`). Step 4 changed code both
cover, and two of step 2's anchors.

## 8. The evidence round

Every row ran on a clean tree, with source fingerprint `d06a9ac1…a9b6`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Suite (`record_test_run.py`) | **3088 passed, 0 failed, 0 errors, 0 skipped** | `4c064e3` (run at `9162ca0`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |
| PostgreSQL gate | PASS: ALL DATABASE-LEVEL CONTRACT TESTS PASSED, 70 PASS notices; the effective contract current (10 entries); the same 67 operations | `9162ca0` (run at `0183967`) | `evidence/gate-run.txt` |
| Authorization matrix | 217 rules (five for step 4); suite 3088/3088 | `0183967` (run at `3950308`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| Step 4 mutations | 31/31 fail, twice, identical | `5ef657b` (run at `11971a3`) | §7 |
| Steps 2 and 3 mutations on this tree | 51/51 and 68/68 | `3950308` (run at `5ef657b`) | §7 |
| Before the fix | 57 failed, 2 passed, at `e1bdcbc` | `11971a3` | §6 |

**The interactions in the suite's database at the end of the run:**
- 181 messages: **180 with exactly one interaction**; **one with none**, the
  OUTBOUND `PHONE_DECISION` that
  `test_vii_the_decision_must_be_an_internal_phone_decision_of_this_thread`
  inserts directly by SQL, after the backfill's tests ran (a message written
  outside the service's paths, which the guarantee does not cover, as
  decided);
- **no message with two interactions**;
- 182 interactions name a `message_id`: the 180, and the two rows
  `test_vi_any_other_interaction_keeps_slice_1s_exact_keys` writes on purpose
  (`not-a-uuid`, and a uuid naming no message); 64 others name none (Slice
  5's writer, and tests' own rows).
- The event store: PROCESSED 68, IGNORED 25, RECEIVED 1 (the recovery test's
  fresh event, by design), FAILED 0.

**The earlier slices' records are not regenerated.**
- `slice6_evidence.py --check`: ONE problem, the document is stale.
- `stop_gate_e_evidence.py --check`: two problems, the document is stale,
  and **`interactions` is written by `message_interactions.py` beside the
  opportunity commands**: the decided second writer (§2), reported by Slice
  5's gate as it stands.

**Limits that are part of these results:**
- **One interaction per message within the service's paths only;** no
  database constraint, no `0009`.
- **The link is valid at its writing only,** with no legal value.
- **The guards hold against the application's ordinary statements only**
  (EN-02); **K06 stays UNPROVEN.**
- **R-1 stays UNMET.** The SALE scope is not widened.
- **These results are ours.** No independent run exists.

## 9. What remains

- **The review of this delivery.**
- **Step 5** of the plan does not start before that review.
- **R-1:** the relay and its seven duties. **No real event before it.**
- **K06 UNPROVEN;** the scope SALE only. **This is not a release
  authorization.**
