# R-1 · step 1 — Meta's GET, Meta's signature, the inbound limit, mutual TLS

**Approved scope.**
- **Step 1 authorized** in the review of `3d8b593` (plan
  `docs/gate/R1_RELAY_PLAN.md`, revision 3), within its stated scope: Meta's
  GET, the verification of Meta's signature, the inbound limit, and the
  synthetic mTLS tests.
- **Not authorized:** deploying the relay, creating a secret, or receiving
  any real event. Steps 2 to 4.

**Status: DELIVERED again for review** (review of `8c64c64` answered, §8).
R-1 stays **UNMET**.
- *History:* delivered at `8c64c64`; NOT closed by the review of `8c64c64`,
  because the evidence's fingerprint did not cover `pyproject.toml`. §8
  answers it, with the evidence on the corrected tree. **§8.4 is the current
  round; §5's and §6's results are the earlier tree's.**
- **What a reviewer has not done:** re-run the suite, the mutations or the
  gate. The results are ours.

**What this step does not contain:**
- **forwarding to TURAB:** none. A POST whose signature verifies is
  answered **503 `RELAY_NOT_FORWARDING`, never 200**, so no delivery is
  acknowledged to Meta. Steps 2 and 3 build the transformation and the
  forwarding;
- a run entry point, a deployment, a secret, a verify token, or any Meta
  setting;
- any change to TURAB's code under `src/`.

**Commits:**
- `c601c25`, `970aff3`: plan revision 3 (the review of `3d8b593`);
- `1ccaed4`: the relay, its tests, the mutation script, the fingerprint
  covering `relay/`;
- `2c3b942`: the mutation records (§5);
- `f112e35`, `6b52b40`, `5d8396a`: the evidence round (§6).

---

## 1. What step 1 contains

The relay is a separate component in this repository (R1-D1 (a)):
`relay/turab_relay/`.

### 1.1 Duty 1: Meta's GET (`meta.py`, `subscription`)

| Request | Answer |
|---|---|
| the verify token not configured (absent or empty) | **503**, for every request: fails closed (R1-T1.4) |
| a parameter missing, empty or repeated; a mode other than `subscribe` | **400** |
| a wrong token | **403**; no challenge in the body |
| the right token | **200**, the body exactly the challenge, `text/plain`, `nosniff`, `no-store` |

The token is compared **as UTF-8 bytes through `compare_digest`**,
imported into the module's namespace so its call path is observable
(R1-T1.5). It is called **exactly once for each GET that reaches the
comparison**, and **not at all** for a GET refused before it.

### 1.2 Duty 2: Meta's signature, and the inbound limit (`app.py`, `meta.py`)

**The order of a POST's checks:**
1. **the inbound limit, 3 MiB** (R1-D4 (a)):
   - a `Content-Length` declaring more is refused **unread**, compared
     without converting an unbounded string to an integer;
   - the bytes are counted as they arrive, and reading stops at the chunk
     that passes the limit: **413**;
2. no app secret: **503**;
3. `X-Hub-Signature-256`: exactly `sha256=<64 lowercase hex>`, an HMAC-SHA256
   **over the raw bytes received**, compared as bytes through
   `compare_digest` (R1-T2.8): **401** when missing, malformed or wrong;
4. verified: **503 `RELAY_NOT_FORWARDING`**.

**The limit comes before the secret,** as in TURAB's own route: an oversize
body is never read whole, configured or not.

### 1.3 Mutual TLS (`tls.py`, plan §5.2)

1. **The chain and the validity period, by the handshake** (`server_context`):
   - a client certificate is **required**;
   - **the one CA file given is the only anchor.** `PROTOCOL_TLS_SERVER`
     loads no default roots, and none are added;
   - TLS 1.2 at least.
   
   A certificate that fails never reaches the application.
2. **The identity, by `meta_identity`:**
   - the subject of the certificate **the handshake validated** must hold
     **exactly one** common name, `client.webhooks.fbclientcerts.com`;
   - the subject reaches the application through the **ASGI scope's TLS
     extension**. `TLSExtensionH11Protocol`, a subclass of uvicorn's h11
     protocol, sets it from the connection's own TLS object;
   - **nothing a client sends can set it;** a header naming the right CN
     counts for nothing.
3. **The application requires the identity by default** (`create_app`). Only
   the tests of duties 1 and 2 turn it off, explicitly.

### 1.4 The binding covers the relay

`db/dev/source_fingerprint.py` now collects `relay/` with `src/`, `tests/`
and `db/` (R1-D1 (a): a bound run must cover the relay's code), and
`db/gate/gate_inputs.py`'s list of covered prefixes follows it. **This
changes the recipe:** every fingerprint from this tree on differs from one
computed by the earlier recipe on the same files. `pyproject.toml` adds
`relay` to the tests' `pythonpath`.

## 2. A finding: the verify token in an access log

**Meta sends `hub.verify_token` in the GET's query string** (E1). A server
that logs the request line records it. **uvicorn's access log does.**

Found when R1-T2.7 first failed. The leak it caught came from the tests' own
HTTP client (`httpx`), which logs the full URL; the relay's logger held
nothing of it.

**What is done in step 1:**
- R1-T2.7 checks every logger except the test client's own;
- the TLS test server runs with **uvicorn's access log off**, and
  `test_the_relay_server_runs_without_an_access_log` checks it.

**What it asks of a later step:** the relay's run entry point, not built and
not authorized here, must disable the access log, or redact the query, and
be tested for it. This is put to the reviewer as a condition of that step,
not decided here.

## 3. The tests (`tests/test_r1_step1.py`, 64)

All synthetic: a test verify token, a test app secret, and certificates
generated with `openssl` (3.0.13) in the test's temporary directory. A test
CA stands in for Meta's.

| Plan | Tests |
|---|---|
| R1-T1.1 to R1-T1.4 | the right token; wrong tokens of the same and other lengths; each malformed or repeated request; no configured token, absent or empty |
| **R1-T1.5** | **the call path:** `compare_digest` replaced, in the relay's namespace, by a recorder around the real function. Exactly one call with the two byte strings, for a matching and a non-matching token. No call for a GET refused before it (no token, another mode, no challenge, no configured token) |
| R1-T2.1 | a verified POST: 503, `RELAY_NOT_FORWARDING` in the log |
| R1-T2.2 | no header, empty, `sha256=` alone, another algorithm, short, non-hex, uppercase prefix, a leading space; an uppercase digest; **a valid digest inside a longer header** (four shapes) |
| R1-T2.3, R1-T2.4 | a valid signature over other bytes, or with another secret; the same JSON re-serialized |
| R1-T2.5 | no app secret, absent or empty |
| R1-T2.6 | exactly 3 MiB passes the limit, one byte more is 413; declared lengths over the limit refused **unread** (including 5000 digits, and 4000 leading zeros); leading zeros alone are not over it; the count stops at the chunk that passes; the limit before the secret |
| R1-T2.7 | no log holds the body, a signature, the token, the challenge or a secret |
| **R1-T2.8** | the signature's comparison through `compare_digest`, on bytes; not called for a malformed header |
| §5.2 | the identity required by default; R1-T10.7 (headers naming Meta's CN: 403); the identity check exactly one CN (six subjects) |
| **R1-T10, end to end** | a real uvicorn TLS server with the relay's context and protocol: the server trusts the configured CA only; **R1-T10.1** Meta's certificate from the CA: 200; **R1-T10.2 to 10.6** no certificate, self-signed with the right CN, another CA with the right CN, expired, not yet valid: refused at the TLS layer, no request reaches the relay; **R1-T10.5** the right CA with another CN, or two CNs: 403 |
| the finding of §2 | the test server runs without an access log |

## 4. What is not claimed

- **The CPU's timing.** R1-T1.5 and R1-T2.8 prove the call to
  `compare_digest`, not its timing. Its constant-time approach is Python's
  documented property (P1), with the documented limit for arguments of
  different lengths (P3).
- **Meta's real CA, real certificate and real requests.** The tests use a
  synthetic CA in Meta's place. The file Meta names (E53) is configuration,
  not provided or tested here.
- **A deployment.** No run entry point, no TLS terminator in front, no
  secret. The barriers of the plan's §4 are unchanged, and their state is
  not measured at this step.

## 5. Mutation evidence

`db/dev/mutate_r1_step1.py`, 25 mutations, each weakening one rule:

| Group | Mutations |
|---|---|
| G, duty 1 | `==` for the token (G1); no comparison; no configured token fails open; any mode; a repeated parameter; an empty challenge or token; the challenge not echoed |
| S, duty 2 | `search` for `fullmatch`; any well-formed signature; the HMAC over a re-serialized body; no secret fails open; `==` for the signature (S5); a verified POST acknowledged 200 |
| L, the limit | one byte larger; the declared length not checked; the body not counted as it arrives; leading zeros counted; a long value converted whole |
| T, mTLS | a client certificate optional; the system's roots trusted too; no minimum TLS version; any identity; Meta's CN among others; the certificate not required by default; the validated subject not passed to the application |

- **The official runs:** two, at `1ccaed4`, clean tree: **25/25 killed in
  each, outcomes identical**. `evidence/R1-STEP1-MUTATIONS.txt` and
  `-REPEAT.txt`.
- **The trial run**, outside the record: 25/25 (`-TRIAL.txt`).
- **G1 and S5, the `==` mutations, are killed only by the call-path tests**
  (`test_r1_t1_5_…`, `test_r1_t2_8_…`). That is the review of `3d8b593`'s
  point: no accept or refuse test can tell `==` from `compare_digest`.
- **One mutation was corrected before the runs.** S3's replacement first
  used `json`, which `meta.py` does not import. Its kill would have been a
  `NameError`, not a test. It imports within the line now, and compiles on
  its own.
- **Not mutated**, with the reasons in the script: the limit's place before
  the secret (a reordering, pinned by its own test); the 404 and 405
  answers.

## 6. The evidence round

Every row ran on a clean tree with source fingerprint `f89c6965…bb65`,
which covers `relay/` (§1.4).

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules; suite **3239/3239** | `f112e35` (run at `2c3b942`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS: all database-level contract tests passed; the same 67 operations | `6b52b40` (run at `f112e35`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3239 passed, 0 failed, 0 errors, 0 skipped** | `5d8396a` (run at `6b52b40`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: **`bound`** |
| Mutations | 25/25, twice, identical | `2c3b942` (run at `1ccaed4`) | §5 |

- **The matrix has no rule for the relay.** It maps RFC-001's authorization
  rules and their invariants; the relay is not one of them. Its tests are
  in the suite, and counted in its 3239.
- **`SLICE_7_EVIDENCE.md` is stale on this tree:** its run is no longer the
  bound one, and the fingerprint's recipe changed (§1.4). It stays the
  record of its tree, at `abee0f9`, like the earlier slices' records.

## 7. What remains

- **The review of this delivery.**
- **Steps 2 to 4,** not authorized: the transformation and §5.3's table, the
  relay's signature, `thread_ref` and R1-D8 (step 2); the redelivery and
  §5.1's classes (step 3); the serialized sizes with R1-Q1 (a), the
  evidence, the barriers' measured state and the closure record (step 4).
- **The condition of §2** for the relay's run entry point.
- **R-1 UNMET;** K06 an independent condition before the release gate; SALE
  only. **No real event.**

---

## 8. Addendum: the review of `8c64c64`, pytest's configuration in the binding

### 8.1 What was wrong

Step 1 added `relay` to `pyproject.toml`'s `pythonpath`, which makes the
relay's tests importable. But `source_fingerprint.py` did not collect
`pyproject.toml`, and `run_binding.py` compares that fingerprint alone with
the current tree. **A later commit could change how the relay's tests are
collected, and the check would still answer `bound`.** That does not deny the
run's result at `8c64c64`; it limited what the binding check proved.

The run record's limits text was also stale: it named `src/`, `tests/`,
`db/` and `alembic.ini`, but not `relay/`, which step 1 had added.

### 8.2 What changed (`00134ee`)

- **The recipe** (`db/dev/source_fingerprint.py`) collects, at the root and
  when present:
  - **pytest's configuration files**, as pytest's documentation lists them
    ("Configuration file formats", pytest 9.1; 9.1.1 is installed):
    `pyproject.toml`, `pytest.toml`, `.pytest.toml`, `pytest.ini`,
    `.pytest.ini`, `tox.ini`, `setup.cfg`. The whole list, not
    `pyproject.toml` alone: `pytest.toml` and `pytest.ini` take precedence
    over it, so one of them added later would change collection outside the
    fingerprint;
  - **a root `conftest.py`, as a precaution of ours.** The page read does not
    list it; the recipe says so.
  
  An absent file of the list is not collected, so adding one later changes
  the fingerprint. Only `alembic.ini` and `pyproject.toml` exist today.
- **`gate_inputs.py`'s list of covered prefixes** follows the recipe.
- **The run record's limits text** (`run_binding.py`) names everything
  covered, and states what is not: **the installed environment** (`.venv`:
  the interpreter and the packages' versions) **and the database server's
  software.**

### 8.3 The test, and the mutations

**`tests/test_evidence_binding.py`, on an isolated copy** holding a bound,
passing run (`run_binding.check` must accept it first):

| Experiment | Expected |
|---|---|
| `pythonpath` with a path added; `relay` removed from it; `testpaths` changed | refused: the fingerprint is not the run's |
| each of the seven configuration files added (`pytest.toml`, `.pytest.toml`, `pytest.ini`, `.pytest.ini`, `tox.ini`, `setup.cfg`, `conftest.py`) | refused |
| the recipe's lists | `relay` in its trees; every file above in its root list; `pyproject.toml` collected |

**Mutations, part 2, F1–F3** (the recipe weakened): pytest's files all
removed; `relay/` removed; `pyproject.toml` alone removed. All killed by
these tests.

**The official runs, at `7502961`, clean tree, source fingerprint
`78c05bde…9e13`:** **28/28 killed in each** (25 by `tests/test_r1_step1.py`,
3 by `tests/test_evidence_binding.py`), outcomes identical.

**The records, each attributed to the tree it ran on:**

| Record | Tree | Recipe | Result |
|---|---|---|---|
| `R1-STEP1-MUTATIONS.txt`, `-REPEAT.txt` | `7502961` | the corrected recipe (`78c05bde…9e13`) | 28/28, twice, identical |
| `R1-STEP1-MUTATIONS-AT-1ccaed4.txt`, `-AT-1ccaed4-REPEAT.txt` | `1ccaed4` | the earlier recipe | 25/25, twice, identical |
| `R1-STEP1-MUTATIONS-TRIAL.txt` | the working tree before `1ccaed4` | outside the record | 25/25 |
| `R1-STEP1-MUTATIONS-TRIAL-F.txt` | the working tree before `00134ee` | outside the record | F1–F3, 3/3 |

`7502961` and `00134ee` hold the same code: `7502961` only names
revision 4's commit in the plan, under `docs/`.

### 8.4 The evidence round on the corrected tree

Every row ran on a clean tree with source fingerprint **`78c05bde…9e13`**,
the mutation runs' own.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules; suite **3250/3250** | `4b4878f` (run at `78bbd36`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS: all database-level contract tests passed; the same 67 operations | `d6ac6b3` (run at `4b4878f`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3250 passed, 0 failed, 0 errors, 0 skipped**; the corrected limits text in the record | `bdd5c49` (run at `d6ac6b3`) | `evidence/TEST-RUN-PROVENANCE.txt`; **`bound`** |
| Mutations | 28/28, twice, identical | `78bbd36` (run at `7502961`) | §8.3 |

### 8.5 The access log: decided

**The review of `8c64c64` decided the condition §2 put forward.** It is
binding before any deployment or Callback setting:
- the logging of the request line is disabled, or its query removed, in the
  HTTP server and in every layer in front of it;
- this is tested **through the actual run entry point**.

Recorded in the plan, revision 4: §5.5, §4's order, §7 condition 11.
**Step 1's test server proves its own configuration only**
(`access_log=False`), not an entry point not yet built.

### 8.6 What remains

- **The review of this answer.** Step 1 is not closed.
- Steps 2 to 4, not authorized. **R-1 UNMET; no real event;** K06 an
  independent condition before the release gate; SALE only.
