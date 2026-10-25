# Slice 7 · step 2 — the staff thread and the staff message; CORRECTION-006

**Approved scope.**
- **Step 2 authorized** in the review of `7e8993d`.
- **G7-16 decided** as recommended, and CORRECTION-006's method approved, in
  the review of `0f423d2`. Plan revision 8 records both.
- **The two commands:**
  - `postCommunicationThreads`;
  - `postCommunicationThreadsThreadIdMessages`.
- **The rules they follow:**
  - G7-3 (the thread reference);
  - G7-4 (the message identity);
  - G7-6 (the links; mandatory test 3);
  - G7-7 with CORRECTION-006;
  - G7-9 (content and consent);
  - G7-11 (audit);
  - G7-16 (i)–(vi).

**What this step does not contain:**
- the webhook, CORRECTION-007 and the recovery command (step 3);
- the timeline, and any `interactions` row (G7-8, step 4);
- the phone decision and its confirmation link (G7-10, step 4). Their two
  message types are refused for now (G7-16 (v));
- the relay (R-1).

**Status:** delivered for review at `f7e5297`; **NOT closed** by the review of
`f7e5297`, for R-S7-2-01. The answer is §9. **Step 3 has not started.**

**Submitted for decision with this delivery:**
1. **The text of CORRECTION-006** (§4). The review of `0f423d2` approves it
   at the review of this delivery.
2. **A sentence of G7-16 (vi), corrected by us before any code** (plan
   revision 8):
   - **what it said:** "the 404 is kept for the path's thread";
   - **why it is wrong:** RFC-001 R5.3b decides that a failed staff object
     check is 403 `OBJECT_NOT_AUTHORIZED`, recorded;
   - **what the code does:** follows R5.3b (§1.2).
3. **One code the plan does not name,** `INTERNAL_MESSAGE_REF_NOT_ACCEPTED`:
   G7-4 says only "(422)" for an INTERNAL message with a reference.
4. **Six readings of ours,** stated in §3, none of them a decision of the
   plan.

**Commits:**
- `921a1d7`: plan revision 8 (the review of `0f423d2`);
- `732d81b`: the code, the tests, CORRECTION-006, the mutation script and
  the first trial run;
- `e61739f`, `02df74b`: the service
  imported where used, so that the before record measures each test; and
  the keyword test made non-vacuous (§5);
- `35958e7`: the before record;
- `11ea553`: the mutation records;
- `f9a480a`, `5a842ce`, `ca4dd1b`: the evidence round (§7).

---

## 1. What step 2 contains

`services/communication.py` and `api/routes/communication.py`. Every refusal
comes before the idempotency claim, in `prepare_thread` and
`prepare_message`, which only read and lock. A refusal therefore writes no
row and no audit row, and consumes no key. Every refusal test checks all
four of these.

### 1.1 The thread (`postCommunicationThreads`, 201 `{thread_id, opened_at}`)

In order:
1. **G7-3:** a WHATSAPP `external_thread_ref`, when given, has the form
   `<scope>:<id>`. Otherwise 422 `THREAD_REF_NOT_SCOPED`.
2. **G7-6 rule 4:** every id names a row. Otherwise 422
   `LINKED_RECORD_NOT_FOUND`, whose `field_errors` name each field (CORRECTION-006
   makes `party_id` required).
3. **G7-6 rule 0:** a named opportunity is a SALE. Its approved match's
   evaluated offer is a SALE offer, and its request's intent is BUY. Both
   are checked, and the opportunity is read `FOR SHARE`. Otherwise 422
   `OPPORTUNITY_NOT_SALE`.
4. **G7-6 rules 1–3:** the links agree. Otherwise 422
   `THREAD_LINKS_INCONSISTENT`, whose `field_errors` name the field and the
   rule:
   - with an opportunity: its request, its property, and its buyer or
     seller;
   - without one: the request's party; and an offer's party of the property,
     a relation not accepted.
5. **G7-3:** a WHATSAPP reference already held is 409 `THREAD_REF_TAKEN`.
   - **Pre-checked** before the claim.
   - **Backstopped** at the INSERT: a reference taken by a concurrent
     command between the check and the write is refused by
     `ux_whatsapp_thread_ref`, and answered as the same 409. The command's
     transaction then rolls back, the claim with it.

The thread records `created_by_account_id` (the caller), and is audited.

### 1.2 The message (`postCommunicationThreadsThreadIdMessages`, 201 `{message_id, delivery_status}`)

**The route** calls `authorize`, `authorize_staff_only` and
`authorize_thread_exists`.
- **An unknown thread** is 403 `OBJECT_NOT_AUTHORIZED`, recorded with its
  kind (`COMMUNICATION_THREAD`) and its id (RFC-001 R5.3b).

**The service then works in this order:**
1. **The body alone:**
   - INBOUND is 422 `DIRECTION_NOT_ACCEPTED` (i);
   - a non-empty `metadata` is 422 `MESSAGE_METADATA_NOT_ACCEPTED` (iii);
   - `PHONE_DECISION` and `CONFIRMATION_LINK` are 422 `MESSAGE_TYPE_RESERVED`
     (v);
   - an INTERNAL message stating a status other than UNKNOWN is 422
     `DELIVERY_STATUS_NOT_ACCEPTED` (ii);
   - an INTERNAL message with a reference is 422
     `INTERNAL_MESSAGE_REF_NOT_ACCEPTED` (G7-4).
2. **The thread, `FOR UPDATE`, as the first statement on it (iv).**
3. **The reference:**
   - outside a WHATSAPP thread, it is 422 `EXTERNAL_REF_WITHOUT_PROVIDER`;
   - in one, the service sets the provider `whatsapp`;
   - a reference already recorded is 409 `MESSAGE_REF_TAKEN`, pre-checked
     and backstopped as the thread's.
4. **Content** (`body_text` or `media_ref`) needs the archive consent:
   - **what is read:** a binding of the thread's party, for this thread and
     COMMUNICATION_ARCHIVE, unrevoked, whose grant is GRANTED, read
     `FOR SHARE OF b, g`;
   - **otherwise:** 422 `CONTENT_NOT_ARCHIVABLE`;
   - **who is held to it:** an INTERNAL note, like any message (G7-10).

**The writes, after the claim:**
- **the message:**
  - `sent_by_account_id`, the caller;
  - `delivery_status`, as stated for OUTBOUND (default UNKNOWN), and UNKNOWN
    for INTERNAL (ii);
  - `metadata`, `{"content_archived": …}` and nothing else;
- **`last_message_at`:** moved to the later of its value and
  `occurred_at` (iv), and only when it moves;
- **the audit:** both writes are audited, with `body_text` and `media_ref`
  withheld (G7-11).

## 2. The points the reviews named

**G7-16 (iv): the thread locked before the message is inserted, tested with
two concurrent messages of different times.**
`test_iv_two_concurrent_messages_serialize_on_the_thread_and_keep_the_later`,
two cases:
1. the first message is held inside its transaction, after its lock, at the
   start of its writes;
2. the second, in another transaction, **waits** on it: `pg_blocking_pids`
   names the first's backend;
3. the second does not answer while the first is held;
4. released, both commit, and `last_message_at` is the later time.

This holds whichever message is held: the later one first, or the earlier
one first.
- **Mutation M17 (no `FOR UPDATE`):** the second does not wait, and both
  cases fail.
- **M19:** `last_message_at` written backwards is refused by `0008`'s guard,
  and both cases fail with it.
- **A sequential test** shows that a message that moves nothing writes no
  thread audit row.

**G7-16 (vi): `field_errors` carry no row id and no database text.**
`test_no_refusal_carries_an_id_or_database_text` reads the whole body of ten
typed refusals of both commands, the two backstop paths among them. It finds
no uuid but the trace id, and none of these:
- the reference;
- the content;
- `turab.`, `constraint`, `violates`, `SELECT`, `INSERT`;
- a constraint or key suffix.

Every `field_errors` entry is `{field, code, message}`, naming a field and a
rule.

**CORRECTION-006: the text, the effective contract and their agreement** (§4).

**RFC-001 R5.3b.** `test_an_unknown_thread_is_403_and_the_denial_is_recorded`
shows the 403 and its record (`DENIED`, `OBJECT_NOT_AUTHORIZED`,
`COMMUNICATION_THREAD`, the id). Mutation R1 removes the route's check: the
service still answers 403, but nothing is recorded, and the test fails.

**G7-9 (3): a revocation in flight.**
`test_g7_9_a_revocation_in_flight_is_waited_for_then_seen`, two cases:
- **the setup:** a transaction holds the grant's revocation;
- **the witness:** the message waits on it (`pg_blocking_pids`);
- **committed:** the message is refused 422 `CONTENT_NOT_ARCHIVABLE`, and no
  message exists;
- **rolled back:** the content is archived.

Mutation M16 (no `FOR SHARE`) fails both cases.

**Mandatory test 2 (J02) for staff:** `test_g7_4_a_recorded_reference_is_409_in_any_thread`.
**Mandatory test 3 (links checked by service invariant):** the rule 0–4
tests.

## 3. Readings of ours (not decisions of the plan)

1. **The provider is set only when the message carries a reference.**
   - **The rule read:** G7-4 gives the WHATSAPP channel the provider
     `whatsapp`, "set by the service". It does not say whether a message
     without a reference has one.
   - **Our reading:** the provider names the namespace of the reference, so
     a message without one has none (NULL).
   - **What is unaffected:** the CHECKs of `0008` part A accept both.
2. **An empty `body_text` counts as content,** and needs the consent. This
   is the stricter side.
3. **Without an opportunity, a request and a property given together** are
   held to both rules 2 and 3. That can be met only by a party that is both
   the request's party and an offer's party of the property.
4. **An opportunity without a current offer has no seller,** so only its
   buyer is accepted under rule 1.
5. **An opportunity's status is not checked** at the thread's creation. No
   rule of the plan asks for it.
6. **~~A consent bound while the message is in flight is not waited for.~~
   WRONG, and corrected after measuring (R-S7-2-01, review of `f7e5297`;
   §9).**
   - **What this item said:** "the binding table has no foreign key to the
     thread", so a binding in flight is not waited for.
   - **Why it is wrong:** the frozen schema declares
     `fk_consent_binding_thread`. The binding's INSERT takes FOR KEY SHARE on
     the thread row, which conflicts with the message's FOR UPDATE.
   - **What is measured** through both commands
     (`evidence/SLICE7-STEP2-R-S7-2-01.txt`):
     - a binding in flight makes the message wait. Committed, the binding is
       SEEN and the content is archived; rolled back, the message is refused;
     - a message holding the thread makes the binding wait.

## 4. CORRECTION-006

`docs/contract/CORRECTION-006-thread-party-required.md` is the text submitted.
- **The entry:** `CONTRACT_CORRECTIONS.yaml`, `request_body_narrowings`,
  with `require: [party_id]`, `non_null: [party_id]` and
  `frozen_defaults: {}`. It carries no `approved` date, since the text is not
  yet approved.
- **The effective body:** the frozen component, copied into the operation,
  with `party_id` required and its `anyOf` null branch removed, which leaves
  `{type: string, format: uuid}`.
  - **The frozen component** is unchanged, and used by this operation alone
    (one `$ref`).
  - **The roles** are unchanged.
- **Their agreement:**
  - `test_the_effective_body_is_the_frozen_component_with_party_id_required_and_not_null`
    compares the committed effective contract, and the runtime's
    `effective_request_body`, with an expectation built from the frozen
    component independently of the transformation;
  - `test_the_route_refuses_exactly_what_the_effective_schema_refuses` sends
    twelve bodies to the route and to a judge of the effective schema, and
    requires the same verdict from each.
- **The loader's extension:** `non_null` now also accepts an `anyOf` with
  exactly one `{type: 'null'}` branch, whose other branches cannot admit
  null. Ten refusals are tested. Two of them were added after the first trial
  run (§6).
- **The copy of a `$ref` body,** changed from `deepcopy` to a JSON round
  trip, and measured:
  - with `deepcopy`, the effective file changed by 168 lines of renumbered
    YAML anchors, for no change of meaning;
  - with the round trip, it changes by CORRECTION-006 only.
  - CORRECTION-004's and CORRECTION-005's texts are unchanged.
    `test_correction_001.py` compares every operation with its independent
    expectation, extended here to the `anyOf` form.

## 5. Before the fix (measured)

`evidence/SLICE7-STEP2-BEFORE.txt`: the 101 tests of the two new files, run
in an isolated worktree at `921a1d7`, with no step 2 code.
**99 failed, 2 passed.**
- **72 failed on the absent route** (404).
- **The rest failed on the absent narrowing and extension.**
- **The 2 that passed** are facts of the frozen package: the component
  unchanged, and the roles.

**Three measurements, the record says so:**
- **the first collected nothing:** the service was imported at module
  level;
- **the second found a vacuous pass:** the keyword test passed with no
  schema at all;
- **both are fixed,** and the third is the record.

## 6. Mutation evidence

`evidence/SLICE7-STEP2-MUTATIONS.txt` and `-REPEAT.txt`, both at `35958e7`
(a clean tree, source fingerprint `9dd247c3…4091`), in two parts, one per
test file. **51/51 fail; none survives**, in both runs, which are identical
line for line.

| Group | Mutations, tests failing |
|---|---|
| T: the thread | T1 6 · T2 5 · T3 1 · T4 1 · T5 1 · T6 1 · T7 1 · T8 1 · T9 2 · T10 1 · T11 1 · T12 1 · T13 2 · T15 2 · T16 2 |
| M: the message | M1 2 · M2 2 · M3 2 · M4 5 · M5 1 · M6 6 · M7 4 · M8 5 · M9 1 · M11 11 · M12 1 · M13 1 · M14 1 · M15 2 · M16 2 · M17 2 · M18 3 · M19 2 · M20 2 · M21 2 · M22 2 · M23 1 · M24 1 |
| R: the route | R1 1 · R2 2 · R3 1 |
| K: the loader | K1 1 · K2 1 · K3 1 · K4 6 · K5 1 · K6 1 · K10 1 · K7 1 · K8 3 · K9 1 |

**The first trial run had four survivors, and is kept**
(`evidence/SLICE7-STEP2-MUTATIONS-FIRST-RUN.txt`, on the working tree before
the code's commit):
- **T14 and M10:**
  - **what they were:** labelled "neither pre-checked nor backstopped", but
    each removed the pre-check only. The backstop answered the same 409;
  - **what was done:** both were withdrawn as the equivalent mutants they
    are. The backstops are T13 and M9, each killed by the test that blinds
    the pre-check.
- **M13:**
  - **what it was:** it removed the purpose condition only, and the scope
    condition still refused;
  - **what was done:** the two conditions are now on adjacent lines, and M13
    removes both.
- **K6:**
  - **what it was:** a `$ref` branch has no `type`, so the no-type fallback
    refused it, not the reference check;
  - **what was done:** a case with a `$ref` and a `type`, and one with a
    combinator and a `type`, were added, and K10 was added for the
    combinator check.

**Not mutated, each with its reason** (`mutate_slice7_step2.py`):
- **the pre-checks alone:** equivalent to the backstop;
- **`b.purpose` alone, or `g.scope` alone:** B01 makes each imply the other;
- **the consent's party condition:** the binding trigger, M5;
- **the opportunity's `FOR SHARE`:** no command today changes
  `current_offer_id`, so no test can claim it;
- **`authorize_staff_only`:** the contract's roles refuse every other caller
  first.

## 7. The evidence round

Every row ran on a clean tree, with source fingerprint `9dd247c3…4091`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Suite (`record_test_run.py`) | **2846 passed, 0 failed, 0 errors, 0 skipped** | `ca4dd1b` (run at `5a842ce`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |
| PostgreSQL gate | PASS: ALL DATABASE-LEVEL CONTRACT TESTS PASSED, 70 PASS notices; the effective contract current (8 entries); the effective contract, inventory and policy table hold the same 67 operations | `5a842ce` (run at `f9a480a`) | `evidence/gate-run.txt` |
| Authorization matrix | 198 rules (nine for step 2); suite 2846/2846 | `f9a480a` (run at `11ea553`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| Step 2 mutations | 51/51 fail, twice, identical | `11ea553` (run at `35958e7`) | §6 |
| Before the fix | 99 failed, 2 passed, at `921a1d7` | `35958e7` | §5 |

**The earlier slices' records are not regenerated.**
- `slice6_evidence.py --check` and `stop_gate_e_evidence.py --check` each
  report ONE problem: the document is stale.
- **STOP GATE E reports no new writer of `interactions`.** Step 2 writes
  none (G7-8 is step 4's).

**Limits that are part of these results:**
- **The guards hold against the application's ordinary statements only.**
  The tests run as `turab`, a superuser (EN-02).
  - **K06 stays UNPROVEN,** an independent condition before the release
    gate.
- **R-1 stays unmet.** Nothing here receives a real event.
- **The SALE scope is not widened.** G7-6 rule 0 refuses a named opportunity
  that is not a SALE.
- **These results are ours.** No independent run exists.

## 8. What remains

- **Step 2 closes on review,** with CORRECTION-006's text.
- **Step 3** (CORRECTION-007, the webhook) does not start before that
  review.

---

## 9. Addendum: the review of `f7e5297` and R-S7-2-01

**What the review decided:**
- **CORRECTION-006's text is APPROVED.**
  - **What it means:** `party_id` is required and not null in the effective
    body, and the frozen component is unchanged.
  - **Where it is recorded:** the entry now carries `approved: "2026-10-25"`.
    The effective contract was regenerated, and changes in that annotation
    only.
- **Accepted:**
  - the 403 `OBJECT_NOT_AUTHORIZED`, recorded, for an unknown thread
    (R5.3b);
  - the code `INTERNAL_MESSAGE_REF_NOT_ACCEPTED`;
  - the first five readings of §3, as decisions for this scope. They are not
    a widening of an opportunity's sharing authority.
- **Not closed, and step 3 not authorized, for one gap: R-S7-2-01**, the
  sixth reading.
  - **The review's inference:** the frozen schema defines
    `fk_consent_binding_thread`; the binding command inserts `thread_id`; and
    FOR UPDATE conflicts with FOR KEY SHARE. So a binding in flight can make
    the message wait, and be seen after the wait.
  - **Its status:** inferred, not measured, by the review.

**Measured** (`evidence/SLICE7-STEP2-R-S7-2-01.txt`, at `c56fe4f`):
- **How:** through the real `POST /consents/bindings` and the real message
  command, with a `pg_blocking_pids` witness, the responses, the rows and both
  idempotency keys asserted. Five consecutive runs, 15/15 cases.
- **`test_r_s7_2_01_a_message_holding_the_thread_makes_a_new_binding_wait`:**
  - the message holds the thread, stopped before its consent check, and the
    binding WAITS on it;
  - the message reads no committed binding, and answers 422
    `CONTENT_NOT_ARCHIVABLE`. It writes no message and consumes no key;
  - the binding then commits (200, one binding, its key consumed).
- **`test_r_s7_2_01_a_binding_in_flight_makes_the_message_wait_then_is_seen`,
  committed and rolled back:**
  - the binding is inserted and held, and the message WAITS on it at its
    thread lock;
  - **committed:** the message's consent check, a later statement under READ
    COMMITTED, sees the binding. The answer is 201 and the content is
    archived; one message and one binding exist, and both keys are consumed;
  - **rolled back:** the binding command is refused after its insert. The
    message answers 422 `CONTENT_NOT_ARCHIVABLE`, and no message, no binding
    and no key remain.

**The review's inference is CONFIRMED**, and §3 (6) was wrong. Corrected:
- §3 (6) above;
- the docstring of `services/communication.py`;
- plan revision 10.

**No behaviour changed.** The code was correct and its account was not.
- **What did not change:** no source line beyond the docstring. The guarantee
  of G7-9 was never weaker than stated: a committed binding is seen, an
  uncommitted one is not.
- **What changed:**
  - the tests (the three cases);
  - the matrix (one rule);
  - the documents;
  - CORRECTION-006's recorded approval.
- **The evidence round,** and the step's mutations, are bound to the new
  tree (§10).

## 10. The evidence round on the new tree

[ADDENDUM EVIDENCE]

