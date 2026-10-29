# R-1 · step 3 — the delivery to TURAB, and the answer to Meta

**Approved scope.**
- **Step 3 authorized** in the review of `da3d778` (plan
  `docs/gate/R1_RELAY_PLAN.md`, revision 7): duty 5 and §5.1's classes and
  answers, against a test double and against TURAB's real application and
  test database.
- **Not authorized:** deploying the relay, creating a secret, or receiving
  any real event. Step 4.

**Status: DELIVERED for review.** R-1 stays **UNMET**.
- **What a reviewer has not done:** re-run the suite, the mutations or the
  gate. The results are ours.

**What this step does not contain:**
- **OVERSIZE** (R1-Q1 (a)) and the envelopes' sizes: step 4, duty 7. Until
  then, an envelope over TURAB's 64 KiB is sent, and TURAB's 400 is answered
  as §1.2 states: not 200, and an alert;
- the run entry point and its access log (§5.5 of the plan): a condition
  before any deployment, not built here;
- any change to TURAB's code under `src/`.

**Commits:**
- `bf330c4`, `8b74a52`: plan revision 7 (the review of `da3d778`);
- `3f86b1f`: `forward.py`, its wiring, its tests, its mutation script, the
  measurement of §4.1;
- `2d42061`: the mutation records (§5);
- `e56bb93`, `636e1f1`, `19eddeb`: the evidence round (§6).

---

## 1. What step 3 contains (`relay/turab_relay/forward.py`)

### 1.1 A verified POST, in order

1. **The relay's key and TURAB's URL.** Either missing, or the key refused
   (empty, or equal to Meta's app secret): **503, nothing sent, an alert**
   (R1-T4.4).
2. **Every element classed** by step 2's `elements`, and **counted** by its
   class and reason. **An ISOLATED element raises an alert**, with its
   fixed reason. This includes `STATUS_NOT_KNOWN`, as the review of
   `ced7df7` accepted.
3. **Each FORWARD envelope POSTed to TURAB:**
   - with `X-Turab-Relay-Signature` over its exact bytes;
   - one at a time, in document order;
   - each under its own deadline (R1-D2; 10 s by default).
4. **The first envelope TURAB does not answer 200 stops the delivery**
   (§4.1). The elements after it are not sent in this attempt, and Meta's
   answer is not 200.
5. **All answered 200: 200 to Meta.** ISOLATED and DROPPED elements never
   change the answer (§5.1).

### 1.2 TURAB's answer, and Meta's

| TURAB | Outcome | Meta's answer | Alert |
|---|---|---|---|
| 200 | completed | 200 once every envelope is | — |
| 500, 503 (CORRECTION-007, CORRECTION-008) | not completed | **502** | no: retryable |
| no answer before the deadline; no connection | no answer | **504** | no |
| any other status: 400, 401 (R1-D3), 403, 404, a 3xx, a 201… | refused | **502** | **yes**, with TURAB's status number |

### 1.3 The HTTP client, the logs, the counts

- **`httpx`, with `trust_env=False`:** no proxy, `.netrc` or certificate
  file is taken from the environment. **No redirect is followed.**
  - `httpx` moves from the dev dependencies to the runtime ones, at the
    version already installed (0.28.1).
- **Logs and alerts carry fixed codes, TURAB's status number and the trace
  id.** They never carry an envelope, a content, a signature, a key or
  TURAB's answer body.
  - An alert is a record on the `turab_relay.alert` logger.
  - The `httpx` library logs each request's method, URL and status on its
    own logger.
- **`app.counts`:** per process and in memory, each element by class and
  reason, and each delivery by outcome. Counted per POST received, so a
  redelivered POST counts its elements again.

### 1.4 What changes in step 1's code and tests (intended)

| Where | Before | Now |
|---|---|---|
| `app._post`, last line | `503 RELAY_NOT_FORWARDING` | the delivery (`forward.post`) |
| `test_r1_t2_1…` | expected `RELAY_NOT_FORWARDING` | `…_without_the_relay_key_is_503_never_200`: the file's environment now removes the relay key and TURAB's URL, so a verified POST is 503 `RELAY_KEY_REFUSED`, never 200 |
| mutation S6 ("a verified POST acknowledged 200") | anchored on the old line | anchored on the delivery's line; same meaning |
| mutation T6 | anchored on `create_app`'s old signature | its new first line |

Step 1's 28 mutations were re-run on this code (§5).

## 2. The tests (`tests/test_r1_step3.py`, 33)

**Three kinds of TURAB:**
- **a test double:** an `httpx.MockTransport` handler that records each
  envelope with its signature, and answers as told;
- **real sockets:** one that accepts and never answers, and a closed port;
- **TURAB's real application and test database,** behind uvicorn on the
  loopback interface. The relay reaches it over HTTP, while `HTTP_PROXY` and
  `ALL_PROXY` in the environment point to a closed port.

| Plan | Tests |
|---|---|
| R1-T5.1 | three elements, all 200: 200; **the exact bytes of step 2**, in document order; each signature checked by **TURAB's `verify`**, each envelope parsed by **TURAB's `parse_envelope`**; the review of `ced7df7`'s inverted case, through the delivery |
| R1-T5.2 to R1-T5.4 | a 500, a 503, no answer: 502, 502, 504, never 200; **the element after it not sent**; no alert; the deadline holds against a double that waits 30 s, against a real socket that never answers, and against a closed port |
| R1-T5.5 | Meta's redelivery: everything sent again, in order, the same bytes and signature |
| **R1-T5.6** | **against TURAB's real application:** a 500 on the second message, so 502 with one event PROCESSED, one FAILED and the status not sent; Meta's redelivery, so 200, with **one event per element, one message and one interaction per message**, and the status applied; a duplicate delivery **writes nothing** (S42). And two statuses of one message, the first failing once: both PROCESSED, **QUEUED → DELIVERED → READ**, in order |
| R1-T5.5 (R1-F7) | against TURAB's real application: a repeated status, same timestamp, is a replay; with another timestamp, TURAB records it IGNORED `STATUS_TRANSITION_NOT_ACCEPTED`; nothing else changes |
| R1-T5.7 | 400, 401, 403, 404, 302, 201 from the double: 502, an alert naming the status, and the redirect not followed; **TURAB's real 401** (the two sides holding different keys): 502, an alert, nothing written |
| R1-T3.8 | ISOLATED and DROPPED beside a FORWARD answered 200: 200, with an alert for each ISOLATED element only; no FORWARD element: 200, nothing sent; an ISOLATED element does not rescue a failed delivery |
| fail closed | no key, an empty key, a key equal to Meta's app secret, no URL, an empty URL: 503, **nothing sent**, one alert |
| counts | each element by class and reason; each delivery by outcome; `STATUS_NOT_KNOWN` counted and alerted |
| logs | across 200, 500, 400 and no answer, **every logger** (`httpx`'s included): no content, envelope, relay signature, Meta signature, key, app secret, or TURAB answer body |

## 3. What TURAB's real application showed

R1-T5.6 runs TURAB as it is: its route, T1 and T2, its test database.
- **The failure is injected the way Slice 7's own tests inject it:** TURAB's
  `process` runs, then a division by zero, once, for one event.
- **The 401** is TURAB's `signing_secret` returning another key: the two
  sides holding different keys.
- Nothing under `src/` changed.

## 4. Readings of ours, submitted for decision

### 4.1 The delivery stops at the first element not completed

§5.1 sends "in document order", and says nothing of the elements after a
failure.
- **Measured** in `evidence/R1-STEP3-STOP-MEASURED.txt`, against TURAB's
  real application, with the stop replaced by going on:
  - `read` is processed first (QUEUED → READ);
  - the redelivered `delivered` is then IGNORED with
    `STATUS_TRANSITION_NOT_ACCEPTED`;
  - so TURAB's record departs from the document's order.
- **With the stop:** QUEUED → DELIVERED → READ, both events PROCESSED.
- **The cost:** the elements after a failure wait for Meta's redelivery.
- **A first wording of this reason was wrong, and was corrected before the
  commit.** It said a status sent after its message failed would be lost.
  But Meta's statuses name messages the business sent, not the inbound
  `messages` of the same POST, so that case does not arise from Meta.

### 4.2 What raises an alert

R1-D3 names TURAB's 400 and 401.
- **Our reading:** every answer other than 200, 500 and 503 is a refusal
  with an alert. That includes 403, 404, a redirect, and a 2xx other than
  200.
- **Why:** TURAB does not answer them for an envelope it can read; each
  means a configuration to fix.
- **Not alerted:** 500, 503 and no answer, which Meta's redelivery is there
  to complete.

### 4.3 No key or no URL: 503, even with nothing to forward

A POST holding only DROPPED elements is also answered 503 when the key or
the URL is missing. This fails closed; the cost is futile redeliveries
while the configuration is missing.

### 4.4 The deadline: 10 s per envelope

- **No basis from Meta:** its documentation gives no time limit for the
  answer (§1 of the plan).
- **The total time of one POST** is up to the number of forwarded elements
  times 10 s. If Meta stops waiting first, it redelivers, and TURAB's replay
  makes that safe (S42).

## 5. Mutation evidence

**`db/dev/mutate_r1_step3.py`, 17 mutations:**

| Group | Mutations |
|---|---|
| D, duty 5 | an element not completed acknowledged 200; **the delivery going on past it**; TURAB's 500 taken as completed; no deadline; no answer taken as completed; a redirect followed; **the environment's proxy used**; the signature over other bytes; the signature under another header |
| A, answers | an ISOLATED element not alerted; TURAB's refusal not alerted; a refusal taken as retryable; a retryable answer alerted as a refusal; the elements not counted; the deliveries not counted |
| F, fail closed | the relay's key not checked; an empty TURAB URL not refused |

- **Not mutated**, with the reasons in the script:
  - the 502 and 504 codes themselves: §5.1 asks only "not 200";
  - the content type: TURAB's route does not read it.
- **The official runs:** two, at `3f86b1f`, clean tree, source fingerprint
  `e99380d3…bddf8`: **17/17 killed in each**.
  - **Outcomes identical:** the same tests fail for each mutation in both
    runs.
  - **Text not identical:** it differs only in random trace ids (`uuid4`)
    and in D4's measured seconds (5.06 s and 5.07 s against a 5 s bound).
- **Step 1, on this code:** its 28 mutations, twice: **28/28 killed in each, outcomes identical**.
  Its text, too, differs only in random trace ids.
- **Step 2's records stand:** `transform.py` and its tests are unchanged.

| Record | Tree | Result |
|---|---|---|
| `R1-STEP3-MUTATIONS.txt`, `-REPEAT.txt` | `3f86b1f` | 17/17, twice, outcomes identical |
| `R1-STEP3-MUTATIONS-TRIAL.txt` | the working tree before `3f86b1f`, without the order test of R1-T5.6 | 17/17, outside the record |
| `R1-STEP1-MUTATIONS.txt`, `-REPEAT.txt` | `3f86b1f` | 28/28, twice, outcomes identical |
| `R1-STEP1-MUTATIONS-AT-7502961.txt`, `-AT-7502961-REPEAT.txt` | `7502961` (renamed) | 28/28, as `R1_STEP1_DELIVERY.md` §8.3 states |

## 6. The evidence round

Every row ran on a clean tree with source fingerprint `e99380d3…bddf8`,
the mutation runs' own.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules; suite **3375/3375** | `e56bb93` (run at `2d42061`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS: all database-level contract tests passed; the same 67 operations | `636e1f1` (run at `e56bb93`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3375 passed, 0 failed, 0 errors, 0 skipped** | `19eddeb` (run at `636e1f1`) | `evidence/TEST-RUN-PROVENANCE.txt`; **`bound`** |

**The count:** 3375 = 3340 (step 2's corrected tree) + 33 (this file) + 2
(`test_mutation_tools` runs over every mutation script, now
`mutate_r1_step3.py` too).

## 7. An open question

**R1-Q2 · The scheme between the relay and TURAB.**
- **What the plan does not decide:** whether the relay must reach TURAB
  over TLS. The relay carries content to TURAB (`body_text`, `media_ref`).
- **What the code does:** it accepts any URL. TLS is verified as `httpx`
  does by default when the URL is `https`. The tests use HTTP on the
  loopback interface.
- **Proposed:** require `https` outside the tests, as a condition before any
  deployment, like §5.5.
- **A related limit:** with `trust_env=False`, a deployment that needs an
  egress proxy to reach TURAB cannot use one. That is to be decided at
  deployment.

## 8. What remains

- **The review of this delivery,** and the decisions on §4 and §7.
- **Step 4,** not authorized:
  - duty 7 with R1-Q1 (a), the OVERSIZE class;
  - R-1's evidence, the barriers' measured state, and the closure record.
- **The access-log condition** (§5.5) stands before any deployment or
  Callback setting.
- **R-1 UNMET; no real event;** K06 an independent condition before the
  release gate; SALE only.
