# R-1 · step 3 — the delivery to TURAB, and the answer to Meta

**Approved scope.**
- **Step 3 authorized** in the review of `da3d778` (plan
  `docs/gate/R1_RELAY_PLAN.md`, revision 7): duty 5 and §5.1's classes and
  answers, against a test double and against TURAB's real application and
  test database.
- **Not authorized:** deploying the relay, creating a secret, or receiving
  any real event. Step 4.

**Status: CLOSED at `79c232b`** (review of `79c232b`, §11), after the corrections
of §9 and §10. R-1 stays **UNMET**.
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
- **The correction (§9):** `598526c`, `2e31160`: plan revision 8 (the review
  of `c480474`); `3c19543`: the deadline, the URL rule, their tests and
  mutations, the before record; `c9c16f9`: a first pair of mutation records,
  not identical (§9.4); `648bec0`: the test corrected; `ddda6b5`: the
  mutation records; `18220ad`, `14e17d5`, `b5501ef`: the evidence round.
- **The correction (§10):** `7b2e4ed`, `8dd4490`: plan revision 9 (the review
  of `3dac09f`); `9a17cc1`: the catch, the tests, U10, the before and after
  records; `e5be82a`: the mutation records; `879a376`, `0c08bc0`, `740b348`:
  the evidence round.

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

**Superseded by §9.5** on the corrected tree. The rows below are readable
at their own commits.

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

## 7. An open question (decided in the review of `c480474`: §9)

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

---

## 9. The review of `c480474`, and the correction

**Step 3 was not closed at `c480474`.** Recorded in the plan, revision 8
(`598526c`, named in `2e31160`).
- **Accepted:**
  - §4.1, the stop at the first envelope not completed;
  - §4.2, an alert on every answer other than 200, 500 and 503;
  - §4.3, 503 when the key or the URL is missing, with its cost.
- **To correct:**
  1. the effective deadline;
  2. R1-Q2, decided (the plan's §5.6, §7 condition 12).

### 9.1 Before: the two points, pinned on `c480474`'s code

`evidence/R1-STEP3-CORRECTIONS-BEFORE.txt`:
- **The tree:** `forward.py` byte-identical to `c480474`'s; only the new
  tests were added, with the double's URL set to `https`.
- **The deadline:** **TURAB silent for 6 s got 504 after 5.06 s,** under
  the stated 10 s.
  - The reviewer inferred this; it is now measured.
  - The cause is HTTPX's own default, `Timeout(timeout=5.0)`
    (`httpx/_config.py:246`, httpx 0.28.1), applied because the client set
    none.
- **TURAB's URL:** every external `http` URL, and every URL with
  credentials, a query or a fragment, was used. The envelopes were sent,
  and the relay answered 200 where 503 is due. The rule did not exist.
- **Already true before:** TURAB's certificate was verified (httpx's
  default, `verify=True`, with the `certifi` roots under
  `trust_env=False`); the correction makes it explicit.
- **Cases added after the record:** seven refused URLs and three allowed
  ones. They are not in it:
  - the loopback spellings;
  - the escaped hosts;
  - the default ports.

### 9.2 The correction (`3c19543`; one test corrected in `648bec0`, §9.4)

- **The deadline:**
  - `httpx.AsyncClient(timeout=httpx.Timeout(limit))`: no phase of HTTPX
    (connect, write, read, pool) ends an envelope before the relay's limit;
  - the outer limit (`asyncio.timeout`) still bounds the whole.
- **TURAB's certificate:** `verify=True`, stated.
- **`url_refusal` (§5.6), checked before anything is sent.** A refusal is
  503 `TURAB_URL_NOT_ALLOWED`, with an alert that names the fixed reason,
  never the URL:

| Reason | Refused |
|---|---|
| `MALFORMED` | a character outside printable ASCII, a space or a backslash; no host; an invalid port; an escape (`%`) in the host; `urllib` and `httpx` reading a different scheme, host or port |
| `SCHEME` | any scheme but `https` and `http` |
| `CREDENTIALS` | `@` in the authority |
| `QUERY` | `?` or `#` anywhere |
| `UNENCRYPTED` | `http` to anything but a **loopback IP literal**: `127.0.0.0/8`, `::1` |

- **Two readings of ours inside the decision:**
  - **"Loopback" is an IP literal, never a name.** `http://localhost` is
    refused, because a resolver could point the name elsewhere. Other
    spellings of loopback are refused too: `127.1`, `0x7f.1`,
    `2130706433`, and `::ffff:127.0.0.1` (Python's `ipaddress` does not
    take it as loopback).
  - **A default port counts as none.** `:443` and `:80` are allowed:
    `httpx` drops them and `urllib` keeps them, so they are normalised
    before the comparison.
- **Found while testing, before the commit:**
  - an escaped host (`turab%2Eexample`) was refused only because the two
    parsers keep the escape's letter case differently; `turab%2eexample`
    would have passed. Hence the explicit `%` rule;
  - the parser comparison itself is reached by no input we found once the
    earlier rules hold. It stays as a guard, and is declared unmutated
    (§9.4).

**The tests: 66 new, 99 in the file.**

| What | Tests |
|---|---|
| **the deadline** | a real server on loopback that reads the request, then stays silent 6 s: **200 under the default 10 s**, between 6 and 10 s; a limit of 2 s, an answer after 1 s: 200; after 3 s: **504, between 2 and 3 s**, at the limit, not before |
| **the rule** | 9 URLs allowed; 26 refused, each with its reason |
| **no sending** | each refused URL through the relay: 503, one alert naming the reason, **nothing reaching TURAB**, and no URL, password or query in any log |
| **the certificate** | an `https` TURAB whose certificate a test CA issued, outside the default roots: **refused at the handshake, no request reaching it**, 504; the same TURAB with its CA trusted: delivered |

**The double's URL** is now `https://turab.test/...`, which §5.6 allows.

### 9.3 What did not change

- `app.py`, `meta.py`, `tls.py`, `transform.py`, and the files of steps 1
  and 2: unchanged since `3f86b1f`.
- **Step 1's mutation records at `3f86b1f` stand:** its code and its tests
  are the same.

### 9.4 Mutation evidence on the corrected tree

**`db/dev/mutate_r1_step3.py`, 29 mutations:**
- **T1** HTTPX's timeout left at its 5 s default;
- **T2** HTTPX's timeout shorter than the limit;
- **V1** TURAB's certificate not verified;
- **U1 to U9:**
  - the URL not checked;
  - `http` allowed for any host;
  - a name taken as loopback;
  - credentials allowed;
  - a query allowed;
  - a fragment allowed;
  - any scheme allowed;
  - any character allowed;
  - an escaped host allowed.

D6's anchor follows its line. **Not mutated,** with the reasons in the
script:
- the parser comparison: no input reaches it;
- the default-port normalisation: removing it refuses more, not less.

**The first official pair, at `3c19543`, did not have identical outcomes.**
- **What differed:** one test case under T2 (HTTPX's timeout at half the
  2 s limit, so 1.0 s). Its server answered after 1.0 s. It passed in one
  run and failed in the other: the answer raced the timer.
- **T2 was killed in both runs,** by two other tests. The outcomes still
  differed, so that pair does not meet the condition.
- **What was done:**
  - the evidence round already started on that tree was stopped before it
    recorded anything;
  - the pair is kept, renamed `-AT-3c19543`;
  - **the test was corrected in `648bec0`:** the answer now comes after
    0.5 s, at least 0.5 s from the limit and from its half. T2 then gave
    the same outcome three times in a row;
  - the official pair was run again.
- **The other timed tests were checked against every mutant.** Each keeps
  at least 1 s from its nearest boundary.

| Record | Tree | Result |
|---|---|---|
| `R1-STEP3-MUTATIONS.txt`, `-REPEAT.txt` | `648bec0`, clean, fingerprint `99af4583…9b2c` | **29/29, twice, outcomes identical**; the text differs only in random trace ids and measured seconds |
| `R1-STEP3-MUTATIONS-AT-3c19543.txt`, `-AT-3c19543-REPEAT.txt` | `3c19543` | 29/29 in each; **outcomes not identical** (T2, above) |
| `R1-STEP3-MUTATIONS-TRIAL.txt` | the working tree before `3c19543` | 29/29, outside the record |
| `R1-STEP3-MUTATIONS-AT-3f86b1f*.txt` | `3f86b1f` (renamed) | 17/17, as §5 states |

**Killed by the tests meant for them:**
- **T1:** the 6 s test (504 after 5.04 s in the official run);
- **V1:** the certificate test (200 where 504 is due);
- **U3:** the `localhost` cases.

### 9.5 The evidence round on the corrected tree

Every row ran on a clean tree with source fingerprint `99af4583…9b2c`,
the mutation runs' own.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules; suite **3441/3441** | `18220ad` (run at `ddda6b5`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS: all database-level contract tests passed; the same 67 operations | `14e17d5` (run at `18220ad`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3441 passed, 0 failed, 0 errors, 0 skipped** | `b5501ef` (run at `14e17d5`) | `evidence/TEST-RUN-PROVENANCE.txt`; **`bound`** |

**The count:** 3441 = 3375 + 66. The 66 new tests: the 6 s test, the two
2 s cases, 9 allowed URLs, 26 refused URLs tested twice (the rule, and
through the relay), and the two certificate tests.

### 9.6 What remained (superseded by §10)

- **The review of this correction.** Step 3 is not closed.
- **Step 4 stays unauthorized** until that review.
- **§5.5's access-log condition** stands, independent of §5.6.
- **R-1 UNMET; no real event;** K06 an independent condition before the
  release gate; SALE only.

---

## 10. The review of `3dac09f`, and the correction

**Step 3 was not closed at `3dac09f`.** Recorded in the plan, revision 9
(`7b2e4ed`, named in `8dd4490`).
- **Accepted:** §9.2's two readings: loopback as an IP literal only, and a
  default port counting as none.
- **The gap:** `url_refusal` called `urlsplit(url)` outside its `try`. A URL
  with an unclosed bracket passes the character check, then `urlsplit`
  raises `ValueError`, and §5.6's 503 and fixed alert are never reached.

### 10.1 Before (`evidence/R1-STEP3-UNSPLITTABLE-BEFORE.txt`)

**The tree:** `forward.py` byte-identical to `3dac09f`'s; only eight URLs
added to the tests' `REFUSED`.

**Seven of the eight make `urlsplit` raise `ValueError`:**

| URL (path `/webhooks/whatsapp`) | `urlsplit`'s error |
|---|---|
| `https://[::1`, `https://::1]`, `http://[::1]x`, `https://[::1]]` | `Invalid IPv6 URL` |
| `https://[[::1]` | `'[::1' does not appear to be an IPv4 or IPv6 address` |
| `http://[zz]` | `'zz' does not appear to be an IPv4 or IPv6 address` |
| `http://[127.0.0.1]` | `An IPv4 address cannot be in brackets` |

- **The eighth,** `http://[v1.x]`, `urlsplit` accepts; it was already
  refused, because the two parsers read it differently.
- **14 tests failed:** the 7 URLs through the rule, and through the relay's
  path.
- **What the relay answered, behind uvicorn** (the review did not state
  it):
  - **500**, uvicorn's own, with a traceback in `uvicorn.error` ending in
    `ValueError: Invalid IPv6 URL`;
  - no alert, and no `503 TURAB_URL_NOT_ALLOWED`;
  - neither the URL nor the content in any log.
- **What that means:** not 200, so Meta would redeliver, but not the
  refusal §5.6 decides.

### 10.2 The correction (`9a17cc1`)

- **`urlsplit` inside its own `ValueError` catch, at its place:**
  `MALFORMED`.
  - The other reasons keep their order and their codes.
  - No general catch around `url_refusal` was added: it would hide a
    future fault of the rule, and mutation U10 would survive it.
- **After, behind uvicorn** (`evidence/R1-STEP3-UNSPLITTABLE-AFTER.txt`):
  - **503 `TURAB_URL_NOT_ALLOWED`**;
  - the alert `TURAB_URL_NOT_ALLOWED MALFORMED`;
  - no traceback;
  - neither the URL nor the content in any log.
- **The tests:** the eight URLs in `REFUSED`, so each runs twice:
  - through the rule;
  - **through the relay's path: 503, nothing sent to TURAB, one alert
    naming the reason, and no URL in any log.**
  - That makes 16 new tests, 115 in the file.

### 10.3 Mutation evidence

**`db/dev/mutate_r1_step3.py`, 30 mutations:** U10 is added (the catch
removed: a URL `urlsplit` refuses raises instead of being refused). It is
killed by the 14 cases.

| Record | Tree | Result |
|---|---|---|
| `R1-STEP3-MUTATIONS.txt`, `-REPEAT.txt` | `9a17cc1`, clean, fingerprint `f03d8788…ae1d` | **30/30, twice, outcomes identical**; the text differs only in random trace ids and measured seconds |
| `R1-STEP3-MUTATIONS-AT-648bec0*.txt` | `648bec0` (renamed) | 29/29, twice, outcomes identical (§9.4) |

**This time the chain gated itself.** It compared the two runs before
recording them, and would have stopped before the evidence round had their
outcomes differed (§9.4).

### 10.4 The evidence round on the corrected tree

Every row ran on a clean tree with source fingerprint `f03d8788…ae1d`,
the mutation runs' own.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules; suite **3457/3457** | `879a376` (run at `e5be82a`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS: all database-level contract tests passed; the same 67 operations | `0c08bc0` (run at `879a376`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3457 passed, 0 failed, 0 errors, 0 skipped** | `740b348` (run at `0c08bc0`) | `evidence/TEST-RUN-PROVENANCE.txt`; **`bound`** |

**The count:** 3457 = 3441 + 16.

### 10.5 What remains

- **The review of this correction.** Step 3 is not closed.
- **Step 4 stays unauthorized** until that review.
- **§5.5's access-log condition** stands.
- **R-1 UNMET; no real event;** K06 an independent condition before the
  release gate; SALE only.

---

## 11. The closure

**The review of `79c232b` closed step 3 at `79c232b`, and authorized step
4** as the plan states it. Recorded in the plan, revision 10.
- **The reviewer checked:**
  - the fix of §10;
  - the URL tests, through the rule and the relay's path;
  - the two mutation records on the same fingerprint.
- **The reviewer did not re-run anything.** 3457/3457, the gate and `bound`
  are our recorded results.
- **This closure does not** close R-1, or allow deploying the relay,
  creating a secret, or receiving any real event. It is not a release
  authorization.
- **Standing:** the access-log condition (§5.5 of the plan); **R-1 UNMET;
  no real event;** K06 an independent condition before the release gate;
  SALE only.
