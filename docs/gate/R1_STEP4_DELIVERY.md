# R-1 · step 4 — duty 7, OVERSIZE, R-1's evidence, the closure record

**Approved scope.**
- **Step 4 authorized** in the review of `79c232b` (plan
  `docs/gate/R1_RELAY_PLAN.md`, revision 10):
  - the size of **each envelope after its serialization**;
  - the OVERSIZE class and the redelivery (R1-Q1 (a), §5.4);
  - R-1's evidence, the barriers' state measured (§4), and the closure
    record.
- **Not authorized:** deploying the relay, creating a secret, or receiving
  any real event. It is not a release authorization.

**Status: the addendum DELIVERED for review (§8).** The review of
`18e4aec` accepted duty 7 and the encoding fix, did not close step 4, and
asked for one addendum on the count check's destination. R-1 stays
**UNMET**: two of its twelve conditions cannot be met inside this
repository (§6, §8, and `R1_CLOSURE_RECORD.md`).
- **What a reviewer has not done:** re-run the suite, the mutations or the
  gate. The results are ours.

**Commits:**
- `453cde7`, `1e7ea3e`: plan revision 10 (the review of `79c232b`);
- `db8fcf8`: OVERSIZE, the encoding refusal, the count check, their tests
  and mutations, the before record, the room record;
- `3385456`: the mutation records (§4);
- `e8cd4f3`, `000a796`, `e49d2a3`: the evidence round (§5);
- `ede11fc`: the barriers' measurement, this note, the closure record.
- `8cbd718`, `f50a104`: plan revision 11 (the review of `18e4aec`);
- `c751bd6`: the addendum: the count check's destination, its tests and
  mutations, the before record (§8);
- `257a28e`: step 4's mutation records again (§8.4);
- `994c895`, `19fc3f2`, `001f429`: the evidence round again (§8.5);
- ADD_COMMIT: the barriers measured again, §8, the closure record updated.

---

## 1. What step 4 contains

### 1.1 Duty 7: the serialized size (`transform.py`)

- **The limit:** `transform.ENVELOPE_LIMIT` = 64 × 1024 = **65 536 bytes**.
  - It is TURAB's own `BODY_LIMIT`, tested equal to it.
  - It is measured on **the bytes each envelope serializes to**: compact
    JSON, UTF-8. Never a content's length.
- **The class OVERSIZE (§5.1, R1-Q1 (a)):** an element that passes every
  check of its kind, but whose envelope exceeds the limit.
  - **Its envelope is not kept:** the element carries its event id only,
    so nothing can send it or shorten it.

### 1.2 OVERSIZE in the delivery (`forward.py`)

- **Not sent, and not shortened.**
- **Counted, and alerted without content.** The alert is
  `alert OVERSIZE message`: the element's kind, never its text.
- **The other elements are delivered, the ones after it included**
  (R1-T7.2). This is unlike a failure from TURAB, which stops the delivery
  (step 3).
- **Meta's answer is not 200:** 503 `ENVELOPE_OVERSIZE`, whatever TURAB
  answered, so the redelivery window stays open (§5.4).
- **On the redelivery,** the delivered elements are 200 replays at TURAB
  that write nothing (S42), and the element is OVERSIZE again.

### 1.3 A fault found in step 2's serialization, corrected here

- **The fault:**
  - JSON may escape a **lone surrogate** (`"\ud800"`), and `json.loads`
    accepts it;
  - the resulting string cannot be encoded in UTF-8;
  - `transform._serialize` raised `UnicodeEncodeError`, and so did the
    relay;
  - a notification whose Meta signature verifies could carry one.
- **Pinned before the fix:** `evidence/R1-STEP4-BEFORE.txt`.
- **Now:** the element is **ISOLATED, `NOT_UTF8_ENCODABLE`**, with no
  envelope and an alert; the other elements are delivered.
- **A surrogate pair** (`"😀"`) is one character of four bytes,
  and is forwarded.

### 1.4 §4's count check (`db/ops/count_webhook_events.py`)

The operator command of R1-D14 (a):
- **reads** `count(*)` of `turab.webhook_events` in each database named on
  the command line, and nothing else;
- **runs** in a read-only transaction, whose state it reads back and
  prints;
- **refuses** `PGSERVICE` and `PGDATABASE`, so no database other than the
  ones named can be read.

## 2. Before (`evidence/R1-STEP4-BEFORE.txt`)

**The tree:** `transform.py` and `forward.py` byte-identical to `79c232b`'s;
only the new tests added.
- **No limit and no OVERSIZE class.**
- **One byte over, against TURAB's real application:**
  - the relay sent the 65 537-byte envelope, and TURAB answered 400;
  - the relay alerted `TURAB_REFUSED 400` and stopped;
  - so the valid elements after it were never delivered, on any attempt:
    one event where three were due.
- **The lone surrogate:** `UnicodeEncodeError`.
- **Already passing (not defects):**
  - 65 536 bytes against TURAB's real route;
  - the 3 MiB request;
  - the surrogate pair.

## 3. The tests (`tests/test_r1_step4.py`, 29)

| Plan | Tests |
|---|---|
| the limit | `ENVELOPE_LIMIT == webhooks.BODY_LIMIT == 65 536` |
| **R1-T7.1** | an envelope of exactly 65 536 bytes forwarded; **TURAB's real route accepts it** (one event PROCESSED, one message) |
| **R1-T7.2** | 65 537 bytes among valid elements: OVERSIZE, no envelope kept; **not sent, not shortened**, every byte sent ≤ 65 536; **the elements after it delivered**; answer not 200; one alert, no content in any log. **Against TURAB's real application:** the first delivery writes the valid elements and answers not 200; **Meta's redelivery writes nothing a second time** and is not 200 again |
| **R1-T7.3** | é (2), € (3), 😀 (4), `"` (2), `\` (2), a newline (2), U+0001 and U+001F (6 each): each at 65 536 bytes (forwarded, exactly) and 65 537 (OVERSIZE); the content's length is under the limit while its bytes are not |
| **R1-T7.4** | a batch: 65 536, 65 535, 65 537, 65 536 in 3-byte characters, and an image with a long caption; each measured on its own; nothing sent above 65 536 |
| **R1-T7.5** | Meta's request at exactly 3 MiB, 52 messages of 60 000 characters: accepted, all forwarded; one byte more: 413, nothing sent |
| **R1-T7.6** | per type of §5.3 that carries content: the envelope grows by exactly the content's serialized bytes; the room is measured, filled exactly (65 536, forwarded), and one byte more (OVERSIZE) |
| R1-T7.7 | not measurable: no real traffic (R1-D13 (a)) |
| encoding | a lone surrogate in a text or in `from`: ISOLATED `NOT_UTF8_ENCODABLE`, the others delivered, 200, one alert; a surrogate pair forwarded |
| §4 count check | the count equal to SQL's, `read_only=on`, one line and nothing else; `NO_TABLE`; `PGSERVICE` or `PGDATABASE` set: refused, nothing printed |

**The room per type** (`evidence/R1-STEP4-ENVELOPE-ROOM.txt`, written by
`db/dev/r1_envelope_room.py`, deterministic):

| Meta type | variable content | room for content |
|---|---|---|
| text | `text.body` | 65 202 bytes |
| image, video | the caption | 65 170 |
| document | the caption | 65 167 |
| audio | the media id | 65 201 |
| sticker | the media id | 65 199 |

- **These hold for the identifiers of Meta's examples** (wamid 62
  characters, 15-digit business number, 11-digit customer).
- **Each further character costs room:**
  - of the wamid: 2 bytes (it appears twice);
  - of `from` or `phone_number_id`: 1 byte.

## 4. Mutation evidence

**`db/dev/mutate_r1_step4.py`, 13 mutations:**

| Group | Mutations |
|---|---|
| Z, the limit | one byte larger; one byte smaller; **measured in characters**; not checked |
| O, OVERSIZE | shortened and sent; the answer 200; not alerted; **stopping the delivery**; its envelope kept |
| E, encoding | the `UnicodeEncodeError` not caught |
| C, the count check | not read-only; `PGDATABASE` accepted; `PGSERVICE` accepted |

- **Z3 (characters)** is killed by the 2-, 3- and 4-byte cases. The
  escapes are ASCII, so for them characters and bytes coincide.
- **Not mutated,** with the reasons in the script:
  - the 503 code: §5.1 asks only "not 200";
  - the OVERSIZE element's event id: it is not content.

**`transform.py` and `forward.py` changed, so steps 2 and 3 were re-run
twice on this code. Step 1's code and tests did not change.**

| Record | Tree | Result |
|---|---|---|
| `R1-STEP4-MUTATIONS.txt`, `-REPEAT.txt` | `db8fcf8` | 13/13 killed, twice, outcomes identical |
| `R1-STEP3-MUTATIONS.txt`, `-REPEAT.txt` | `db8fcf8` | 30/30 killed, twice, outcomes identical |
| `R1-STEP2-MUTATIONS.txt`, `-REPEAT.txt` | `db8fcf8` | 31/31 killed, twice, outcomes identical |
| the earlier pairs | renamed `-AT-<their tree>` | as their notes state |

## 5. The evidence round

Every row ran on a clean tree with source fingerprint `884519ff684dc8678cb85f704a66a0651fa87832af3830425c27e3573be34ade`, the mutation
runs' own.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules; suite **3488/3488** | `e8cd4f3` (run at `3385456`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS: all database-level contract tests passed; the same 67 operations | `000a796` (run at `e8cd4f3`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3488 passed, 0 failed, 0 errors, 0 skipped** | `e49d2a3` (run at `000a796`) | `evidence/TEST-RUN-PROVENANCE.txt`; **`bound`** |

## 6. R-1's evidence and the barriers' state

`docs/gate/R1_CLOSURE_RECORD.md` maps §7's twelve conditions to their
evidence, and records the barriers as measured.
- **Ten conditions are met by the tests and records of steps 1 to 4,**
  subject to this delivery's review.
- **Two are not, and cannot be from inside this repository:**
  - **condition 9:** the barriers' state. B1 and B4 are read from Meta's
    App Dashboard, and B2 and B3 from the deployed environments; this
    session has neither;
  - **condition 11:** the run entry point and its access log (§5.5). None
    exists to test through, and no step of the plan builds one.
- **What was measured here** (`evidence/R1-STEP4-BARRIERS-MEASURED.txt`,
  on the bound tree):
  - this server's four databases are all test or maintenance databases;
    the count check, read-only on each: NO_TABLE, 112 (the suite's), 0, 0;
  - this session's environment: no `TURAB*`, `WHATSAPP*` or `META*`
    variable;
  - the repository: no deployment configuration, and no
    `turab_relay/__main__.py`.
  - **None of this is the state of B1 to B4,** which stays unknown.
- **Two questions are submitted:** R1-Q3 (who measures the barriers) and
  R1-Q4 (the run entry point).

## 7. What remains

- **The review of this delivery.**
- **The decisions on R1-Q3 and R1-Q4.**
- **R-1 UNMET; no real event;** K06 an independent condition before the
  release gate; SALE only; not a release authorization.

---

## 8. Addendum: the count check's destination (review of `18e4aec`)

**The review of `18e4aec` did not close step 4.** It accepted duty 7 and
the fix of `UnicodeEncodeError`, and asked for one addendum (plan revision
11, `8cbd718`).

**The gap.**
- `count_webhook_events.py` printed `PGHOST`, but neither pinned `hostaddr`
  nor refused `PGHOSTADDR`.
- libpq connects to `PGHOSTADDR` and never resolves `PGHOST`. So a count
  could be printed against a host the tool never reached.
- The tests deleted `PGHOSTADDR` in their setup, so they did not reveal it.

**What was asked:**
1. every destination parameter pinned at the connection;
2. the identity of the server and database that answered recorded;
3. a test that changes `PGHOSTADDR` and shows the count is not attributed
   to the mismatched `PGHOST`;
4. the evidence of the resulting tree bound again.

### 8.1 Before (`evidence/R1-STEP4-ADDENDUM-BEFORE.txt`)

**The tree:** `count_webhook_events.py` byte-identical to `18e4aec`'s; only
the new tests added.
- **Shown directly:** `PGHOST=elsewhere.invalid` and `PGHOSTADDR=127.0.0.1`
  printed `turab_authz_test host=elsewhere.invalid read_only=on
  webhook_events=0`, exit 0. The count was attributed to a host that does
  not exist.
- **The tests:** 6 failed, 2 passed (the two existing refusals).
  - The connection was given `dbname` only (`KeyError: 'host'`).
  - Without `PGHOST`, libpq fell back to a local socket, a destination
    nobody named.
  - A `PGHOSTADDR` with no server raised an unhandled `OperationalError`.

### 8.2 The fix (`c751bd6`)

- **Every destination parameter is pinned:**
  - `host`, `hostaddr` (empty when none), `port` (5432 when `PGPORT` is
    unset) and `dbname` are each passed to the connection;
  - libpq fills none of them from anywhere else;
  - **`PGHOST` is required.**
- **The count is attributed to what answered.** Each line names:
  - the server, read from itself: its cluster's system identifier, the
    address and port it answered on (`pg_control_system()`,
    `inet_server_addr()`, `inet_server_port()`);
  - the database: `current_database()`;
  - what was asked, separately.

  ```
  DATABASE: webhook_events=N read_only=on | answered: system_identifier=...
  address=... port=... database=... | asked: host=... hostaddr=... port=...
  ```
- **A failed connection is never a count:** `DATABASE: CONNECTION_FAILED
  asked: ...` on stderr, nothing on stdout, exit status 1.
- **Unchanged:** `PGSERVICE` and `PGDATABASE` refused; a read-only
  transaction, its state read back; `count(*)` and nothing else.
- **The identifier is readable without superuser:** on this server PUBLIC
  holds EXECUTE on `pg_control_system()` (measured,
  `has_function_privilege`).

### 8.3 The tests (`tests/test_r1_step4.py`, now 34)

| Test | What it shows |
|---|---|
| the count printed, read-only | the whole line equals the count read by SQL, the suite server's own identifier, address and port, and what was asked |
| `NO_TABLE` | the same line, for `postgres` |
| **`PGHOSTADDR` reached, `PGHOST` mismatched** (the review's test) | `PGHOST=elsewhere.invalid`, `PGHOSTADDR` = the suite server's address: the count is the answering server's, named by its identifier and address; `elsewhere.invalid` appears in `asked` only, never in `answered` |
| a `PGHOSTADDR` where no server listens | `PGHOST` names the suite's server, `PGHOSTADDR` 127.0.0.2: no count printed, for either; `CONNECTION_FAILED` on stderr; exit 1 |
| every parameter pinned | the connection receives `host`, `hostaddr` (empty), `port` and `dbname` explicitly |
| an unset `PGPORT` | pinned to 5432, and printed |
| no `PGHOST` | refused, nothing printed |
| `PGSERVICE`, `PGDATABASE` | refused, as before |

### 8.4 Mutations (`db/dev/mutate_r1_step4.py`, now 20)

| Mutation | Killed by |
|---|---|
| D1 an empty `hostaddr` not passed | every parameter pinned |
| D2 the unset port left to libpq | an unset `PGPORT` |
| D3 the answering address taken from `PGHOST` | the review's test |
| D4 the answering server's identifier not read | the line tests, the review's test |
| D5 `PGHOST` not required | no `PGHOST` |
| D6 a failed connection exits 0 | no server listening |
| D7 a failed connection printed as a line of counts | no server listening |

- **Not mutated:** the answered database printed from the request's name.
  A connection's `current_database()` is the `dbname` it was given, so no
  test can tell them apart.
- **Steps 1 to 3 were not re-run.** Their code, tests and mutation scripts
  are byte-identical to their pairs' trees (`git diff db8fcf8` on
  `relay/`, their test files, their scripts and `mutation_runner.py`:
  empty).

| Record | Tree | Result |
|---|---|---|
| `R1-STEP4-MUTATIONS.txt`, `-REPEAT.txt` | `c751bd6` | 20/20 killed, twice, outcomes identical |
| `R1-STEP4-MUTATIONS-AT-db8fcf8.txt`, `-REPEAT.txt` | `db8fcf8` | 13/13 killed, twice, outcomes identical (§4) |

### 8.5 The evidence round, again

Every row ran on a clean tree with source fingerprint `71f705bd33d0083467daa96c30dbe26b4f859bb05edc5f08db2a9cd0a0c9835e`, the mutation
runs' own.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules; suite **3493/3493** | `994c895` (run at `257a28e`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS: all database-level contract tests passed; the same 67 operations | `19fc3f2` (run at `994c895`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3493 passed, 0 failed, 0 errors, 0 skipped** | `001f429` (run at `19fc3f2`) | `evidence/TEST-RUN-PROVENANCE.txt`; **`bound`** |

**The count:** 3493 = 3488 + 5 (the count check: 4 tests before, 9 now).

### 8.6 The barriers measured again (`evidence/R1-STEP4-BARRIERS-MEASURED.txt`)

**Measured with the fixed tool, on the bound tree.** Its earlier version,
measured at `e49d2a3` with the old tool, is kept as
`R1-STEP4-BARRIERS-MEASURED-AT-e49d2a3.txt`.
- **Every count now names the server that answered.** All four databases
  answered from the same cluster, system identifier `7697828029857667607`,
  at 127.0.0.1:5432.
- **This is the test server.** As the review states, **its counts are no
  evidence of the state of any deployed environment.**
- **B1 to B4 stay `UNKNOWN`.** Under R1-Q3 (§5.7 of the plan), the
  operators measure them; condition 9 is not met.

### 8.7 What remains

- **The review of this addendum.** Step 4 is not closed.
- **Step 5** (the run entry point, R1-Q4) waits on step 4's closure.
- **§5.5's access-log condition** stands before any deployment or Callback
  setting.
- **R-1 UNMET:** no real event, no deployment, no Callback setting. K06 an
  independent condition before the release gate; SALE only; not a release
  authorization.
