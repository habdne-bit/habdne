# R-1 — closure record (prepared for review; R-1 NOT closed)

**What this record is.**
- **The plan's step 4 asks for it:** "R-1's evidence; the barriers' state
  measured (§4); the closure record" (`R1_RELAY_PLAN.md`, revision 10, §6;
  revision 11 since the review of `18e4aec`).
- **It maps §7's twelve acceptance conditions to their evidence**, and
  records the barriers' state as far as it can be measured from here.
- **R1-D15 decides how R-1 closes:** tests and mutations bound to a
  clean-tree run; this record, **with the barriers' measured state**; and
  the reviewer's decision.

**Status: R-1 is UNMET.**
- **Two conditions are open,** and cannot be met inside this repository:
  - **condition 9:** the barriers' state;
  - **condition 11:** the run entry point's access log.
- **No real event may be received.**
- **K06** stays an independent condition before the release gate.
- **SALE only.** This is not a release authorization.

**Prepared at:** `ede11fc`; **updated by step 4's addendum** (review of
`18e4aec`) at ADD_COMMIT, on the tree whose run is bound (`001f429`, source
fingerprint `71f705bd33d0083467daa96c30dbe26b4f859bb05edc5f08db2a9cd0a0c9835e`). **The reviewer has not re-run anything.** Every
result here is ours.

---

## 1. §7's conditions, and their evidence

| # | Condition (§7) | State | Evidence |
|---|---|---|---|
| 1 | each of the seven duties, and §5.2's mTLS, proven by the tests of §3 and §5.2, every one passing, on synthetic notifications only | **met**, subject to step 4's review | duties 1, 2 and mTLS: `tests/test_r1_step1.py` (step 1 closed at `e9fac51`); duties 3, 4, 6: `test_r1_step2.py` (closed at `da3d778`); duty 5: `test_r1_step3.py` (closed at `79c232b`); duty 7: `test_r1_step4.py` (this step); suite **3488 passed, 0 failed, 0 errors, 0 skipped**, bound |
| 2 | the relay's output accepted by TURAB's own parser and signature check (R1-T3.7, R1-T4.2), its redelivery shown against TURAB's real application (R1-T5.6) | **met** | `parse_envelope` and `verify` called on every forwarded envelope (steps 2 and 3); R1-T5.6 against TURAB's application behind uvicorn and the test database (step 3); R1-T7.1 and R1-T7.2 against the same (step 4) |
| 3 | every guard fails closed: no token, no secret, no key | **met** | R1-T1.4, R1-T2.5 (step 1); R1-T4.4 (steps 2 and 3: 503, nothing sent); no TURAB URL, a refused URL (step 3, §5.6) |
| 4 | the constant-time comparisons proven by their call path | **met** | R1-T1.5, R1-T2.8 (step 1) |
| 5 | §5.1's classes and answers proven (R1-T3.8, R1-T6.7); §5.3's table type by type (R1-T3.5) | **met**, OVERSIZE subject to step 4's review | R1-T3.5, R1-T6.7 (step 2); R1-T3.8 (step 3); OVERSIZE's answer, R1-T7.2 (step 4) |
| 6 | the envelope's size bounded by its serialized bytes (R1-T7.1 to R1-T7.5); no limit attributed to Meta beyond its documentation | **met**, subject to step 4's review | `test_r1_step4.py`; the room per type, `evidence/R1-STEP4-ENVELOPE-ROOM.txt`; no field maximum attributed to Meta (plan §1) |
| 7 | no content in any log of the relay; no content from an ISOLATED element anywhere | **met** | R1-T2.7 (step 1); every logger, `httpx`'s included, across 200, 500, 400 and no answer (step 3); OVERSIZE's alert and logs (step 4); ISOLATED elements carry no envelope (step 2) |
| 8 | each mutation of the relay's guards killed, in two identical runs | **met**, subject to step 4's review | steps 1 to 4: `evidence/R1-STEP{1,2,3,4}-MUTATIONS*.txt`, §2 below |
| **9** | **the barriers' state measured and recorded at closure (§4)** | **NOT MET** | §3 below: measurable here only in part; under R1-Q3 (decided, review of `18e4aec`) the operators of Meta's app and of each deployed environment measure B1 to B4; `UNKNOWN` until they do |
| 10 | K06 UNPROVEN, SALE only; not a release authorization | **stated** | — |
| **11** | **the run entry point meets §5.5, tested through it, before any deployment or Callback setting** | **NOT MET** | no run entry point exists. The tests run uvicorn programmatically with `access_log=False` (step 1), which proves that test server only, as §5.5 says. Under R1-Q4 (decided, review of `18e4aec`), step 5 builds and tests it through an actual process, after step 4's closure; each layer in front of it is examined in the deployment environment |
| 12 | TURAB's URL meets §5.6, the refusals and their sending nothing tested | **met** | step 3's §9 and §10: the rule, the relay's path, behind uvicorn |

## 2. The mutation records

| Step | Mutations | Tree of the current pair | Result |
|---|---|---|---|
| 1 | 28 | `3f86b1f` | 28/28, twice, outcomes identical (its code and tests unchanged since) |
| 2 | 31 | `db8fcf8` | 31/31 killed, twice, outcomes identical |
| 3 | 30 | `db8fcf8` | 30/30 killed, twice, outcomes identical |
| 4 | 20 | `c751bd6` | 20/20 killed, twice, outcomes identical (the pair at `db8fcf8`, 13/13, kept as `-AT-db8fcf8`) |

## 3. The barriers (§4), as measured

§4 says each barrier is a mechanism and a state. **The state is a fact about
Meta's app and the deployed environments. The plan does not know it, and
it is to be measured, not inferred.**

| # | Barrier | Who measures its state (R1-Q3, decided) | Measured here | State |
|---|---|---|---|---|
| B1 | no verified callback URL at Meta | the app's operator, in the App Dashboard | **not measurable:** this session has no access to Meta's app, and none was given | **unknown** |
| B2 | no relay key in TURAB's environment | the operator of each deployed environment (presence only) | **this session's environment:** no variable named `TURAB*`, `WHATSAPP*` or `META*` is set (names read, never values), `TURAB_RELAY_SIGNING_SECRET` included. Deployed environments: none known to this repository | **unknown** for deployed environments |
| B3 | TURAB's webhook route not exposed | the operator of each deployed environment | **the repository** holds no deployment configuration: no Dockerfile, compose file, Procfile, Kubernetes, Terraform, proxy or service file (`git ls-files`, `evidence/R1-STEP4-BARRIERS-MEASURED.txt`). That is a fact about the repository, not about any deployment | **unknown** |
| B4 | no subscription to the `messages` field | the app's operator, in the App Dashboard | **not measurable** (as B1) | **unknown** |

**The count check (R1-D14 (a)).**
- **Built in step 4:** `db/ops/count_webhook_events.py` (read-only, counts
  only, the databases named).
- **Its destination, since the addendum (review of `18e4aec`):** every
  destination parameter pinned at the connection (`host`, `hostaddr`,
  `port`, `dbname`), `PGHOST` required; each count printed with the
  identity of the server and database that answered it: the cluster's
  system identifier, its address and port, `current_database()`. A count
  is never attributed to a `PGHOST` the connection did not reach.
- **Run on every database of this session's server:** `evidence/R1-STEP4-BARRIERS-MEASURED.txt`.
  - **The server holds no non-test TURAB database.** Its databases are
    `postgres`, the suite's (`turab_authz_test`), the gate's
    (`turab_contract_test`), and a probe database left by Slice 6's work
    (`turab_probe`). Their counts are test rows, and say nothing of a real
    event.
  - **The counts, read-only on each, measured again with the fixed tool
    on the bound tree:** `postgres` NO_TABLE; `turab_authz_test` 112 (the suite's synthetic events); `turab_contract_test` 0; `turab_probe` 0. Every line names the same
    answering cluster, system identifier `7697828029857667607`, at
    127.0.0.1:5432. Exit status 0.
  - **The earlier measurement**, at `e49d2a3` with the old tool, is kept as
    `evidence/R1-STEP4-BARRIERS-MEASURED-AT-e49d2a3.txt`.
  - **These counts are no evidence of the state of any deployed
    environment** (review of `18e4aec`).
  - **The non-test databases R1-D14 means** are those of the deployed
    environments. None is reachable from here.

## 4. What closing R-1 still needs

**R1-Q3 · Measuring the barriers (condition 9): DECIDED** in the review of
`18e4aec` (plan §5.7).
- **The operator of Meta's app and the operator of each deployed
  environment** measure the barriers: B1 and B4 in the App Dashboard; B2,
  B3 and the count check in each environment.
- **They record** the date, what was seen, and the count of events, in a
  record that is reviewed.
- **Where nothing was measured, the state stays `UNKNOWN`.** That is every
  row of §3 now: **condition 9 is not met.**

**R1-Q4 · The run entry point (condition 11): DECIDED** in the review of
`18e4aec` (plan §5.7, §6 step 5).
- **Step 5** builds `python -m turab_relay`, and tests its log and its mTLS
  configuration **through an actual process**.
- **Its local test does not prove** the logs of a load balancer or a TLS
  terminator: each layer in front of the relay is examined in the
  deployment environment before condition 11 is met.
- **Step 5 waits on step 4's closure.** Condition 11 is not met.

## 5. Standing

- **R-1 UNMET.** No real event may be received.
- **No relay is deployed.** No secret, verify token or Meta app setting is
  created.
- **The access-log condition (§5.5)** stands before any deployment or
  Callback setting.
- **K06** stays an independent condition before the release gate.
- **SALE only.** This is not a release authorization.
