# Slice 8 · preparatory step — the `add_all_of` narrowing key

**Approved scope.** The review of `0a78e91` (Slice 8 plan Q-B3 (a)):
"a **separate, limited preparatory step** for adding `add_all_of` to the
corrections loader, the contract generator and their tests". **Not
included:** activating CORRECTION-009, moving `0009` into Alembic, or writing
the slice's commands. What it had to prove:
- the addition applies to an **operation-local copy** of the body;
- **the effective contract and the runtime validation refuse the same
  payload**;
- invalid correction input is refused;
- **no other operation changes**.

**Status: DELIVERED; NOT CLOSED** (review of `a7a4fe9`). The loader checked
the names of the admitted keywords, not the structure of their values. The
addendum `SLICE_8_PREP_ADD_ALL_OF_ADDENDUM.md` changes what §1.2 and §1.3 say:
- each keyword's value is checked, by the loader and the judge alike;
- `format` is `uuid` only: `date-time` is not admitted.

Slice 8's step 1 is not authorized; the texts of CORRECTION-009, the Delta
and `0009` are not approved.
- **What a reviewer has not done:** re-run the suite, the mutations or the
  gate. The results are ours.

**Commits:**
- `0c54875`: the key, the loader's check, the copy, the runtime's judge, the
  generator's annotation; the tests; the mutation script; the before record;
  the mutation trial;
- `6567503`: the mutation pairs (§4);
- `0990109`, `d9f8a5e`, `9100a70`: the evidence round (§5);
- `405f418`: this note; CORRECTION-009's literal text and the
  regenerated expected contract (§6); plan revision 5.

---

## 1. What the step contains

### 1.1 The key (`src/turab/auth/contract.py`)

- **`add_all_of`** joins the keys a request-body narrowing may carry
  (`_BODY_NARROWING_KEYS`): a non-empty list of schema objects, **appended** to
  the body's `allOf`.
- **Why it is a narrowing:** an appended `allOf` branch only removes
  documents. Every body the effective schema accepts, the frozen one accepts.
- **The operation-local copy:** `narrowed_body_schema` builds a new `allOf`
  list, and copies the entry's branches by a JSON round trip. Neither the
  frozen body nor the corrections document is reachable from the effective
  schema.

### 1.2 What the loader accepts (`_check_add_all_of`)

- **A declared keyword subset, and nothing else** (`_ALL_OF_KEYWORDS`):
  `type`, `enum`, `const`, `required`, `properties`, `additionalProperties`,
  `items`, `anyOf`, `if`, `then`, `minimum`, `format`, `default`, `$ref`.
- **Every `$ref` followed** into the frozen components, whose own keywords
  must be in the subset too: a branch referring to `PhoneInput` (which uses
  `pattern`) is refused.
- **No new schema anywhere:** `$defs` refused; a `$ref` outside
  `#/components/schemas/`, or to no component, refused.
- **In the entry's own branches,** `additionalProperties` may only be
  `false`; `if` and `then` come together; `format` is `uuid` or `date-time`,
  the ones the validator asserts; `type` is a JSON type.
- **The existing rules hold:** one narrowing per operation; `require`
  non-empty; the staleness check of `frozen_defaults`.

### 1.3 The runtime's judge (`body_violations`)

- **One validator for the subset**, JSON Schema 2020-12 semantics (OpenAPI
  3.1's dialect), with `format` asserted for `uuid` and `date-time`, as the
  project's routes and CORRECTION-006's judge already treat `uuid`.
- **It fails closed:** a schema carrying any keyword outside the subset is
  refused (`ContractError`), never judged as if the keyword were absent.
- **A violation names its place** (`body.payload.intent`), **never the
  value**.
- **It is not wired to any route.** No approved correction uses the key, so
  `effective_request_body` returns None for every operation it could
  concern; the step activates nothing.

**No dependency is added.** A full JSON Schema library (`jsonschema`) is not
installed, and adding one is a decision this step did not carry; the subset
is what CORRECTION-009 needs, measured on the frozen components.

### 1.4 The generator (`db/gate/generate_effective_contract.py`)

It writes the body `narrowed_body_schema` returns, as for every narrowing,
and annotates it: `x-turab-correction.add-all-of` holds the branches.

## 2. Before (`evidence/PREP-ADD-ALL-OF-BEFORE.txt`)

**The tree:** `contract.py` and the generator byte-identical to `749fdc2`'s;
only the new tests added. **36 of 37 tests failed:**
- 20: the loader refused the key itself (`unknown key(s) ['add_all_of']`);
- 14: each refusal test, on that message instead of its own;
- 2: `body_violations` did not exist.
- **Passing already:** no approved correction uses the key.

## 3. The tests (`tests/test_contract_add_all_of.py`, 37)

**A test entry**, `TEST-ADD-ALL-OF`, on `postExternalLeadsLeadIdConvert`, in a
temporary copy of the corrections file: `require: [target, payload]` and a
branch requiring, when `target = REQUEST`, a closed payload. It is not
CORRECTION-009.

| Test | What it shows |
|---|---|
| the copy | the effective body = the frozen body + the two required fields + the branch; **the frozen contract unchanged** (deep comparison); the body, its `allOf` and its first branch new objects |
| the generator | it writes that body, annotates it, and **every other operation and every component is equal** to the baseline effective contract |
| not activated | no approved correction uses `add_all_of`; `effective_request_body` is None for the operation |
| **the same refusals** (18 payloads) | for each: the body **the generator wrote**, judged by **an independent judge written in the test**, and **`body_violations`** on the body the loader gives the runtime, **agree, and agree with the stated verdict** |
| a violation's message | names `body.payload.intent`, never the value |
| fail closed | `body_violations` refuses a schema carrying `pattern` |
| invalid input (14) | not a list; empty; a non-object branch; an unread keyword; `$defs`; a `$ref` outside the components; to no component; to a component using `pattern`; format `uri`; `additionalProperties` true or a schema; `then` without `if`; `if` without `then`; an unknown type |

**One verdict the tests state rather than assume:** the frozen conversion
body declares no `additionalProperties: false`, so **an unknown top-level key
is accepted** by the effective contract; the narrowing closes the payload,
not the body.

## 4. Mutations (`db/dev/mutate_prep_add_all_of.py`, 28)

| Group | Mutations |
|---|---|
| K, the loader | K1 the key not admitted; K2 the check never called; K3 an unread keyword admitted; K4 a referenced component not inspected; K5 a `$ref` to no component; K6 any format; K7 `additionalProperties` other than false; K8 `then` without `if`; K9 `if` without `then`; K10 any type |
| N, the copy | N1 the branches not appended; N2 the frozen body changed; N3 the entry's own objects in the body |
| G, the generator | G1 the annotation omitted |
| V, the judge | V1 `if`/`then`; V2 `required`; V3 `additionalProperties`; V4 `enum`; V5 `const`; V6 `items`; V7 `anyOf` read as `allOf`; V8 `minimum`; V9 a boolean taken for an integer; V10 an unread keyword judged as absent; V11 `format`; V12 a `$ref` not followed; V13 the `allOf` branches not applied; V14 a violation names the value |

**Not mutated,** with the reasons in the script: `default` (an annotation);
the `date-time` branch of `_format_holds` (no narrowed schema carries one
yet); the `seen` guard against a reference loop (no frozen component refers
to itself).

**`contract.py` changed, so the four earlier scripts that mutate it were
re-run twice too:** CORRECTION-004, Slice 6 step 2, Slice 7 steps 2 and 3.
Their earlier records stay their trees' records; the re-runs are new files.

| Record | Tree | Result |
|---|---|---|
| `PREP-ADD-ALL-OF-MUTATIONS.txt`, `-REPEAT.txt` | `0c54875` | 28 mutations; **none survives**; pair identical |
| `PREP-ADD-ALL-OF-RERUN-CORRECTION-004-MUTATIONS*.txt` | `0c54875` | 11 mutations; **none survives**; pair identical |
| `PREP-ADD-ALL-OF-RERUN-SLICE6-STEP2-MUTATIONS*.txt` | `0c54875` | 33 mutations; **none survives**; pair identical |
| `PREP-ADD-ALL-OF-RERUN-SLICE7-STEP2-MUTATIONS*.txt` | `0c54875` | 51 mutations; **none survives**; pair identical |
| `PREP-ADD-ALL-OF-RERUN-SLICE7-STEP3-MUTATIONS*.txt` | `0c54875` | 68 mutations; **none survives**; pair identical (outcomes; text without its 52 `trace_id` cause lines, §4 below the table) |

**"Identical", exactly:**
- **the outcomes**, compared line by line in order: each mutation's header,
  its pass/fail count line, its `FAILED` test names, and the survivors;
- **the text**, compared as a multiset of lines once measured seconds, trace
  ids, times and datetime values, process ids, ports, random uuids and hex
  tokens (whole, or as pytest truncates them) are replaced;
- **one class of line is left out of the text comparison, and stated:** a
  `cause:` line carrying a problem body's `trace_id`.
  `db/dev/mutation_runner.py` prints **the first six** of a set of causes
  **sorted by their text**, and that text includes a random `trace_id`, so
  *which* six are shown varies between runs.
  - **Measured on the Slice 7 step 3 pair:** 52 such lines in each run; the
    first comparison, which kept them, failed on them alone.
  - **Not affected:** the tests and counts they come from are identical.
  - **In the other four pairs:** none.
  - **Not changed here:** the runner, which every earlier record used.
    Masking the `trace_id` before sorting would make the sample stable; it
    is a change to shared tooling, proposed, not made (§7).

## 5. The evidence round

Every row ran on a clean tree with source fingerprint `92c05844779ea8e8e4e5c8b3549ed6ba929bef77420fc659b3a60a69b3cc5228`, the mutation
runs' own.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules, all PASS; **3563/3563** test cases passing | `0990109` (run at `6567503`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | **PASS** | `d9f8a5e` (run at `0990109`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | tests=3563, failures=0, errors=0, skipped=0; `run_binding`: **`bound`** | `9100a70` (run at `d9f8a5e`) | `evidence/TEST-RUN-PROVENANCE.txt`; **`bound`** |

**The count:** **3563 = 3524 + 39**, from a diff of the junit files (`749fdc2`'s
bound run → `9100a70`'s):
- **+37:** `tests/test_contract_add_all_of.py`;
- **+2:** `tests/test_mutation_tools.py`, its two checks run over the new
  script `mutate_prep_add_all_of.py`;
- **one id changed, not a test:** `test_slice3_step4`'s
  `test_a_bad_confirmation_time_is_refused_and_writes_nothing`, whose
  parameter is a time computed at collection ("in the future"); one id out,
  one in;
- **removed:** none other..

## 6. After the step: CORRECTION-009's literal text, and its generated diff

As the review asked, **after** the step:
- **the literal YAML** of CORRECTION-009, `add_all_of` included, is in
  `docs/gate/drafts/CORRECTION-009-lead-conversion-payload.DRAFT.md` §3;
  no placeholder remains;
- **the effective contract it produces**, with the Delta's addendum, was
  generated by the gate's generators on a temporary worktree of `0c54875`:
  `docs/gate/drafts/SLICE8_EFFECTIVE_CONTRACT_EXPECTED.txt` (regenerated; no
  part is hand-written now). Its part 0: **the generated body equals the
  runtime's effective body**, and the runtime's verdicts on seven payloads.
- **Still drafts:** the repository's `CONTRACT_CORRECTIONS.yaml` and
  `addenda/` are unchanged; `generate_effective_contract.py --check` passes
  on the repository.

## 7. What remains

- **The review of this step**, and of CORRECTION-009, the Delta and `0009` in
  final form, **before Slice 8's step 1** (review of `0a78e91`).
- **Proposed, not made:** `mutation_runner.py` to mask a `trace_id` before
  sorting its causes (§4), so a pair's text compares whole.
- **OQ8-1 stays open;** `raw_text` capture is not widened.
- **R-1 UNMET; K06 UNPROVEN; SALE only;** not a release authorization.
