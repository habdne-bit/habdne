# R-1 · step 5 — the run entry point, `python -m turab_relay`

**Approved scope.**
- **Step 5 authorized** in the review of `63a3e95` (plan
  `docs/gate/R1_RELAY_PLAN.md`, revision 12, §5.7 R1-Q4, §6 step 5):
  - build the run entry point `python -m turab_relay`;
  - test its access log and its mTLS configuration **through an actual
    process**.
- **Not authorized:** deploying the relay, a Callback setting, creating a
  secret, or receiving any real event. It is not a release authorization.

**Status: CLOSED at `4f2f430`** (review of `4f2f430`, §8; plan revision
13). Delivered for review at `c2bbfcf`.
- **R-1 stays UNMET.** Conditions 9 and 11 stay open (§6, §7).
  - Condition 11's part for the entry point is closed with this step.
  - What stays open of it: the logs of each layer in front of the relay,
    examined in the deployment environment (§5.7).
- **What a reviewer has not done:** re-run the suite, the mutations or the
  gate. The results are ours.

**Commits:**
- `c629937`, `1b046b4`: plan revision 12 (the review of `63a3e95`);
- `9dc7afd`: the entry point, its tests and mutations, the before record,
  the process's lines, the first mutation trial;
- `2155278`: the mutation records (§5);
- `1830194`, `8e6261f`, `428c9e2`: the evidence round (§6);
- `c2bbfcf`: this note, the closure record updated.

---

## 1. What step 5 contains (`relay/turab_relay/__main__.py`)

### 1.1 Configured by its environment only

| Variable | What |
|---|---|
| `TURAB_RELAY_BIND_HOST`, `TURAB_RELAY_BIND_PORT` | where it listens |
| `TURAB_RELAY_TLS_CERTFILE`, `TURAB_RELAY_TLS_KEYFILE` | the relay's own certificate and key |
| `TURAB_RELAY_META_CA_FILE` | Meta's outbound API CA certificate, the only anchor for the client's (§5.2) |

- **No command-line argument is accepted.** A process's arguments are
  visible to every user of its host.
- **The secrets and TURAB's URL** are read by the application at each
  request, as in steps 1 to 3. A missing or refused one fails closed there
  (503, nothing sent).

### 1.2 It refuses to start

Exit status 2, **before listening**, when:
- a setting is missing or empty;
- the port is not a port number (0 to 65535, digits only);
- the TLS files cannot be loaded as one certificate, its key, and a CA;
- an argument is given.

The refusal names the variables, **never a value**.

### 1.3 There is no other way to serve

- **No plain HTTP:** the server context is the relay's own
  (`tls.server_context`): a client certificate required, Meta's CA the only
  anchor, TLS 1.2 at least.
- **No way to drop the client certificate:** the application is
  `create_app()`, which requires Meta's identity on the validated
  certificate, through the relay's TLS extension protocol (`tls.py`).

### 1.4 What it writes (§5.5)

To stderr, one line each: `time level logger message`.
- **Every logger at INFO and above, except two:**
  - **uvicorn's access log, off** (`access_log=False`). It is **the only
    thing keeping request lines out**: the access log's lines are INFO,
    which this configuration writes (§5's A1);
  - **`httpx`, held at WARNING:** its INFO line names TURAB's URL for every
    request. `httpcore` logs at DEBUG only, below INFO.
- **What remains:**
  - uvicorn's own logger, `uvicorn.error`: its start, its stop, fixed
    warnings;
  - the relay's refusals and alerts: a fixed reason and a trace id.

### 1.5 Readings submitted for review

| # | Reading | Why |
|---|---|---|
| 1 | Port 0 is accepted | the system chooses a free port; the tests use it. A deployment sets its port |
| 2 | The secrets and TURAB's URL are not checked at start | each is already refused at each request, failing closed, as steps 1 to 3 prove; checking them at start too would add a second rule to test |
| 3 | uvicorn's `proxy_headers` keeps its default | it rewrites only the scope's client address and scheme; the relay reads neither, and trusts no header (§5.2, R1-T10.7) |
| 4 | uvicorn's `Exception in ASGI application` line, with its traceback, stays enabled | an exception's message could carry data. No test reaches one (no line of §4 holds `Traceback`), and step 4 removed the one found (`UnicodeEncodeError`). Silencing it would hide a fault |

## 2. Before (`evidence/R1-STEP5-BEFORE.txt`)

**The tree:** `relay/turab_relay/` as at `63a3e95`, with no `__main__.py`;
only the new tests added.
- **`python -m turab_relay` did not exist:** 29 of 29 tests failed, the
  refusals to start included (exit 1, Python's own).
- **The way left to run the relay was uvicorn's own command line.**
  Measured through an actual process: one GET of Meta's subscription, and
  uvicorn's default access log wrote
  `"GET /whatsapp/webhook?hub.mode=subscribe&hub.challenge=...&hub.verify_token=... HTTP/1.1" 403`.
  The token and the challenge, in a log (synthetic values).

## 3. The tests (`tests/test_r1_step5.py`, 29)

**Each starts `python -m turab_relay` as an operating-system process**, from
a directory outside the repository, with an environment holding nothing of
the test run's but `PATH`, and reads every line it writes, stdout and
stderr.

| Test | What it shows |
|---|---|
| Meta's GET over mutual TLS | 200, the challenge exactly |
| a signed POST | delivered to a double of TURAB on loopback; 200 |
| **every line read** | after Meta's GET; a wrong token; `%ff` in the query; another path with the token in its query; a signed POST delivered; a wrong signature; another CN; no certificate; another CA; a clear-text request to the TLS port; SIGTERM: **no line holds** the token, the challenge, `hub.`, `?`, `%ff`, the content, the app secret, the relay's key, Meta's signature, TURAB's URL or path, TURAB's answer, the envelope, or `Traceback`; **no request line** (`GET /`, `POST /`, `HTTP/1.x`); **every line is the configured format**; no `uvicorn.access` line |
| R1-T10.2 to 10.6, through the process | no certificate, self-signed, another CA, expired, not yet valid: refused at the handshake |
| R1-T10.5, through the process | Meta's CA, another CN or two CNs: 403 |
| R1-T10.7, through the process | another CN, with headers naming Meta's CN: 403 |
| refusals to start | each of the 5 settings missing, and empty (10 tests); the port `https`, `65536`, `-1`; a CA or certificate file that does not exist; a key that is not the certificate's; an argument: exit 2, nothing listening, the variable named, no traceback |
| no value named | a refused port's value, the token, the secrets, TURAB's URL: absent from the refusal |

**Every line the process wrote** in the "every line read" test:
`evidence/R1-STEP5-PROCESS-LINES.txt`, written by
`db/dev/r1_entry_point_lines.py` (deterministic: the same tree writes the
same record).
- uvicorn's 8 lifecycle lines (start, stop);
- 5 refusals of the relay: `refused 403 VERIFY_TOKEN_MISMATCH`,
  `400 SUBSCRIPTION_PARAMETERS_MISSING_OR_REPEATED`, `404 NOT_FOUND`,
  `401 SIGNATURE_NOT_VALID`, `403 CLIENT_CERTIFICATE_NOT_META`, each with a
  trace id;
- **nothing else.** The refused handshakes and the clear-text request wrote
  no line.
- **`%ff`:** `parse_qs` replaces a percent-escape that is not UTF-8, so the
  answer is 400 for the parameters missing, not `QUERY_NOT_UTF8`.
- **Raw bytes outside ASCII in the request line** are not sent by these
  tests: Python's `http.client` refuses to encode such a target
  (`UnicodeEncodeError`, measured).
- **A finding, while writing this note (F5-1):** the branch of
  `meta.subscription` that answers 400 `QUERY_NOT_UTF8` (step 1's code) is
  reached by no test (`grep QUERY_NOT_UTF8 tests/`: nothing), and no
  mutation covers it. **Measured through the entry point**
  (`evidence/R1-STEP5-F51-NON-ASCII-TARGET.txt`): a raw `0xff`, raw UTF-8,
  or a control byte in the request target is refused by h11 itself, 400
  `Invalid HTTP request received.`, **before the application**. h11 accepts
  a target of bytes 0x21 to 0x7E only.
  - So the branch **cannot be reached through this entry point**: it is a
    guard for any other server, and fails closed as written.
  - **uvicorn's warning line** for those requests holds no request line, no
    query and no token (the same record).
  - **Proposed, not done, for decision:** a process test pinning h11's 400
    and its warning line without the query. Step 1 is closed, and the
    measurement is outside the suite, so this is left to the reviewer.

## 4. Mutations (`db/dev/mutate_r1_step5.py`, 15)

| Group | Mutations |
|---|---|
| A, what the process writes (§5.5) | A1 the access log on; A2 uvicorn's default logging configuration; A3 `httpx` at INFO |
| T, mTLS through the process (§5.2) | T1 no TLS; T2 uvicorn's own protocol, without the TLS extension; T3 the client certificate not required; T4 the server's certificate as the client's anchor |
| R, refusing to start | R1 an argument accepted; R2 a missing setting not refused; R3 an empty setting accepted; R4 a port above 65535; R5 a signed port; R6 a TLS file that cannot be loaded not caught; R7 a refusal exits 1; R8 a refusal names the value |

**A finding of the first trial** (`evidence/R1-STEP5-MUTATIONS-TRIAL.txt`,
on the uncommitted tree):
- **A1 survived.** With the root logger at WARNING, the access log's INFO
  lines were dropped by the level, so `access_log=False` was not what kept
  them out.
- **Corrected before the commit:** the root at INFO. `access_log=False` is
  now the only guard, and A1 is killed by the "every line read" test.

**Not mutated,** with the reasons in the script:
- `lifespan="on"`: operational lines;
- the root level INFO: lowering it only writes less;
- a refusal on stderr rather than stdout: the tests read both together.

| Record | Tree | Result |
|---|---|---|
| `R1-STEP5-MUTATIONS.txt`, `-REPEAT.txt` | `9dc7afd` | 15/15 killed, twice, outcomes identical |

**What "identical" means here.**
- **The outcomes are identical:** every mutation, its failing tests, and
  the result line.
- **The text is identical** once the measured seconds, trace ids, process
  ids, ephemeral ports and clock times are replaced.
- **The last three are new to this step.** The entry point runs as a
  process, so the failure messages quote its process id, its port and the
  time of its log lines. A first comparison that did not replace them
  stopped the chain. Nothing else differed.

**Steps 1 to 4 were not re-run.** Their code, tests and scripts are
unchanged since their pairs (`__main__.py` is new; no other file of
`relay/` changed).

## 5. The evidence round

Every row ran on a clean tree with source fingerprint `4571a1c09003bc06511a1f2a66ebf05da3b33318afefa4f81a85bd528a5f5dc6`, the mutation
runs' own.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules; suite **3524/3524** | `1830194` (run at `2155278`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS: all database-level contract tests passed; the same 67 operations | `8e6261f` (run at `1830194`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3524 passed, 0 failed, 0 errors, 0 skipped** | `428c9e2` (run at `8e6261f`) | `evidence/TEST-RUN-PROVENANCE.txt`; **`bound`** |

**The count:** 3524 = 3493 + 29 (this step's tests) + 2 (`test_mutation_tools.py`'s two checks, parametrized by mutation script, now including `mutate_r1_step5.py`).

## 6. Condition 11

§7's condition 11: "the run entry point meets §5.5, tested through it
(step 5), and each layer in front of it examined in the deployment
environment (§5.7), before any deployment or Callback setting."

| Part | State |
|---|---|
| the entry point exists, and meets §5.5 tested through it | **delivered here,** subject to this review |
| its mTLS configuration, through an actual process | **delivered here,** subject to this review |
| **each layer in front of it** (load balancer, proxy, TLS terminator), examined in the deployment environment | **not examined: no deployment exists.** Under R1-Q4 it is examined there |

**Condition 11 stays NOT MET.**

## 7. What remains

- **The review of this delivery,** and the decision on F5-1 (§3).
- **Conditions 9 and 11** stay open: the operators' measurement of the
  barriers and the deployment's layers, and the review of its record (R1-Q3,
  R1-Q4).
- **§5.5's access-log condition** stands before any deployment or Callback
  setting.
- **R-1 UNMET:** no deployment, no Callback setting, no real event. K06 an
  independent condition before the release gate; SALE only; not a release
  authorization.

---

## 8. The closure

**The review of `4f2f430` closed step 5 at `4f2f430`. R-1 is not closed.**
Recorded in the plan, revision 13.
- **The reviewer checked:** the entry point's start (TLS, the client
  certificate required, the access log off); the tests of the actual
  process; the record of the lines and the two mutation records; that no
  source or test changed after the implementation's commit.
- **The reviewer did not re-run anything.** 3524/3524 and `bound` are our
  recorded results.
- **§1.5's four readings are accepted, within their limits:**
  - port `0`, for tests;
  - the secrets and TURAB's URL checked at each request;
  - `proxy_headers` as it is, as long as the application uses none of the
    values it changes;
  - the ASGI exception's logging stays enabled. **The test of the lines
    does not prove that every future exception's message is free of
    content; no absolute guarantee is drawn from it.**
- **F5-1:** no change to step 1 and no new test required. The measurement
  is a judgement on the entry point tested, not on any other server.
- **Conditions 9 and 11 stay open** (§6, §7).
- **This closure does not** allow deploying the relay, a Callback setting,
  or receiving any real event. It is not a release authorization.
- **Standing:** the access-log condition (§5.5 of the plan); **R-1 UNMET;
  no real event;** K06 an independent condition before the release gate;
  SALE only.
