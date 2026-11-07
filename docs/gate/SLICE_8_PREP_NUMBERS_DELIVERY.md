# Slice 8 · preparatory step — exact numbers (Q-C1 (a))

**Approved scope.** The review of `5054bd0`: "a limited preparatory step for
numbers before CORRECTION-009 is approved":
- parse the body from its bytes before its numbers become `float`;
- update the judge and its comparison for exact values;
- agreement tests for the four examples and `1.0`;
- a test for an integer beyond Python's default limit of 4300 digits;
- any refusal at the parsing limit a classified answer, not a general
  exception, nor a consumed idempotency key;
- no claim that every accepted body agrees, until the accepted value is
  tested on its way to the conversion and to storage;
- no business ceiling for the budget.

**Before delivery, the reviewer added:**
- the before record's ten route tests errored in their fixture, which shows
  nothing of the old code: keep that record, and run the same cases on the
  old code with a working setup;
- in the fixed tree, prove through the real path:
  - that a refusal at parsing or at the storage bound gives its classified
    answer before the key is claimed;
  - that an accepted integer reaches storage with its exact value.
- F-3's storage bound (`BIGINT_MAX`) may refuse a budget, the schema's
  verdict and the column's kept distinct.

**Status: DELIVERED for review.**
- **Not approved:** CORRECTION-009.
- **Not authorized:** Slice 8's step 1.
- **Activates nothing:** no production route uses the parser yet.
- **What a reviewer has not done:** re-run anything. The results are ours.

**Commits:**
- `1da86d1`: the parser, the dependency, the judge's exact number, the
  schema's exact numbers; tests; the mutation script; the first before
  record and trial;
- `39b3796`: storage through the real parts, `JsonInteger` on `Decimal`,
  `validated`; the before record with today's parsing; the second trial;
- `7e7ed36`: M16;
- `f4a160b`: the mutation pairs;
- `65adf09`, `d74187f`, `0eece56`: the evidence round;
- CLOSE_COMMIT: this note, plan revision 9.

---

## 1. What the step contains

### 1.1 The parser (`src/turab/api/exact_json.py`)

`parse_exact(raw: bytes)`:

| A JSON number literal | becomes |
|---|---|
| an integer | an `int`; beyond 4300 digits, an exact `Decimal` (not a refusal: the schema accepts it) |
| any other (`1.0`, `1e-400`, `1e400`) | a `decimal.Decimal`, exact for every decimal literal |
| `NaN`, `Infinity`, `-Infinity` (Python accepts them, JSON does not: RFC 8259 §6) | refused |

**Every refusal is classified** (`BodyNotParsed`), never a general
exception. Each takes the status FastAPI's own parsing gives the same body
(M16.1, measured on the conversion route):

| The body | Answer |
|---|---|
| not UTF-8 (RFC 8259 §8.1) | `400 VALIDATION_FAILED` |
| nested beyond the parser's recursion (`RecursionError`) | `400 VALIDATION_FAILED` |
| not JSON, or empty | `422 VALIDATION_FAILED` |
| a non-JSON constant | `422 VALIDATION_FAILED` |

**`ExactJsonBody`**, a FastAPI dependency, raises them before the route's
handler runs, so before any command claims a key.

**`validated(model, value)`** applies a route's own body model, the
columns' storage bounds included (`json_types`, decision F-3). A refusal is
the `422 VALIDATION_FAILED` FastAPI gives a body model: the field named, no
value echoed.

### 1.2 `JsonInteger` on an exact number (`src/turab/api/json_types.py`)

- **A `Decimal` with a zero fractional part** becomes the exact `int`.
  - The fractional part is read from its digits, with no arithmetic context.
  - **Its digit count is bounded before `int()`:** beyond 4300 digits it is
    refused as beyond any column.
- **Why the bound is there, measured:** a mutant without it, given
  `1E+100000000`, was still building the integer after seven minutes (§4).
- **No existing route is affected:** FastAPI's parsing never produces a
  `Decimal`.

### 1.3 The judge (`src/turab/auth/contract.py`)

- **A finite `Decimal` is a JSON number.**
- **Integral by its digits** (`_integral`), with no context: no exponent can
  round, overflow or trap.
- **It compares exactly** with an `int` or a `float`.
- **The schema's own numbers must be exact too.** The loader refuses a
  non-integral number in a `const`, `enum`, `default` or `minimum`: YAML
  reads `0.1` as the nearest binary float, which an exact instance `0.1`
  would not equal.
  - The frozen contract's numeric keywords hold no float at all (M16.2).

## 2. Before

### 2.1 `evidence/PREP-NUMBERS-BEFORE.txt` (kept as committed)

**33 failed, 10 errored, 1 passed.**
- **The ten errors:** the route tests' fixture imported the absent module.
- **As the reviewer noted,** that shows nothing of the old code.

### 2.2 `evidence/PREP-NUMBERS-BEFORE-TODAY-PARSING.txt`

**The same cases, on `5054bd0`'s `contract.py` and `json_types.py`, the
parser absent.** On a tree without the parser, the tests measure today's
parsing:
- FastAPI's `json.loads`;
- the body model as `POST /requests` declares it.

**32 failed, 0 errors, 24 passed: every failure an assertion about the old
behaviour.** Among them:

| Case | Today |
|---|---|
| `NaN`, `Infinity`, `-Infinity` | reach the command (`201`) |
| a budget of `1e-400` | **stored as 0** (`201`) |
| a budget of `9007199254740993.0` | **stored as `9007199254740992`** |
| a budget of `9223372036854775807.0` (`BIGINT_MAX`) | refused |
| a 5000-digit integer | a generic `400`; in the unit tests, `ValueError` |
| the review's four | the judge disagrees with the schema |

## 3. The tests (`tests/test_exact_numbers.py`, 58)

| Group | What it shows |
|---|---|
| parsing keeps the value | each non-integer literal an exact `Decimal`; an integer an `int`; 5000 digits exact; no `float` anywhere in a parsed body |
| **agreement** | the review's four and `1.0` (and `1`, `0`, `1.5`, `-1`, `-0.0`, `1E+2`, 5000 digits): `body_violations` on the exact value gives the schema's verdict, computed independently from the text; the same in a body narrowed as CORRECTION-009's |
| the judge's exact number | `Decimal` as number and integer; equality; `minimum`; non-finite refused |
| the schema's exact numbers | a non-integral number in `minimum`, `const`, `enum`, nested `const`, `default` refused; `0.0` admitted |
| **refused at parsing** | through the application and the real command plumbing: not UTF-8, nested 100000 deep (`400`), not JSON, empty, `NaN`, `Infinity`, `-Infinity` (`422`); each a problem with `VALIDATION_FAILED`, **the key unused**; the control, a body that parses, claims it |
| **storage** | through a route built of the real parts (the application, the command plumbing that claims the key, `RequestCreate` with its bounds, the request service): `9007199254740993.0`, `9223372036854775807`, `9223372036854775807.0`, `1E+3`, `1.0` **reach the `bigint` column with their exact value**; `9223372036854775808`(`.0`), 5000 digits, `1e400`, `1e-400`, `1.5`, `-1` **refused `422` naming `budget_max_dzd`, before the key, no row written, no value echoed** |
| the digit bound | `JsonInteger` on `Decimal`; `1e5000` refused by the bound, not by the column's `le` |

**The schema's verdict and the column's, distinct (review of `5054bd0`):**
- `1e400` and a 5000-digit integer are `integer`s the contract accepts. They
  are refused as **not storable**.
- `9223372036854775808` is likewise beyond `bigint`.
- **This step claims no more than that.**

**The suite:** 3664 passed (3604, `+58` here, `+2` `test_mutation_tools`
over the new script).

## 4. Mutations (`db/dev/mutate_prep_numbers.py`, 25)

| Group | Mutations |
|---|---|
| P, the parser and `validated` | P1 floats; P2 a long integer refused; P3 `NaN` accepted; P4 non-UTF-8 decoded; P5 recursion unclassified; P6 a 400 answered as 422; P7, P9 a refusal raised as a general exception; P8 invalid JSON unclassified; P10 the body model not applied |
| T, `JsonInteger` | T1 `Decimal` not an integer; T2 its fraction ignored; T3 no digit bound before `int()`; T4 non-finite not refused first; T5 through a float |
| E, the judge | E1, E2 `Decimal` number or not; E3–E5 integrality; E6–E10 the schema's exact numbers |

**Not mutated:** the message texts; `BodyNotParsed.__init__`; `validated`'s
"body" prefix (equivalent: the problem handler drops it).

**Two trials:**
- **The first** (`PREP-NUMBERS-MUTATIONS-TRIAL.txt`, 18 mutations, at
  `1da86d1`).
- **The second** (`-TRIAL-2.txt`, 25): **all killed**.
  - A first run of it was **stopped**: under T3, a test with `1E+100000000`
    made the mutant build the integer, still running after seven minutes.
  - The tests use `1e5000` since. A mutant without the bound ends, and is
    caught by its message.

**The pairs, on a clean tree at `7e7ed36`**, with every script mutating a
file this step changed:

| Record | Result |
|---|---|
| `PREP-NUMBERS-MUTATIONS.txt`, `-REPEAT.txt` | 25 mutations; **none survives**; pair identical |
| `PREP-NUMBERS-RERUN-PREP-ADD-ALL-OF-MUTATIONS*.txt` | 53; **none survives**; identical |
| `PREP-NUMBERS-RERUN-CORRECTION-004-MUTATIONS*.txt` | 11; **none survives**; identical |
| `PREP-NUMBERS-RERUN-INPUT-HARDENING-MUTATIONS*.txt` | 16; each refused by at least one test (counted from the record); identical |
| `PREP-NUMBERS-RERUN-SLICE6-STEP2-MUTATIONS*.txt` | 33; **none survives**; identical |
| `PREP-NUMBERS-RERUN-SLICE7-STEP2-MUTATIONS*.txt` | 51; **none survives**; identical |
| `PREP-NUMBERS-RERUN-SLICE7-STEP3-MUTATIONS*.txt` | 68; **none survives**; identical |

**"Identical"** as in the earlier rounds.
- **The cause lines carrying a sampled `trace_id`** are left out of the text
  comparison, and counted:
  - 52 in each Slice 7 step 3 run, as before;
  - **25 in each of this step's own runs:** its route tests read problem
    answers, each with a trace id;
  - none in the other runs.
- **The outcomes are compared whole.**
- **Input hardening's runner prints no verdict line.** Its survivors are
  counted from its record: a mutation with no `FAILED` line. None.

## 5. The evidence round

Every row ran on a clean tree with source fingerprint `1baf5b74072089f9a23795c4cab66f259700e4ac846c87d32006f3d6a5da50bb` (the same in all 20 sections of the mutation records).

| Evidence | Result | Commit |
|---|---|---|
| Authorization matrix | 222 rules, all PASS; **3664/3664** | `65adf09` |
| PostgreSQL gate | **PASS** | `d74187f` |
| Suite (`record_test_run.py`) | tests=3664, failures=0, errors=0, skipped=0; `run_binding`: **`bound`** | `0eece56` |

**The count:** **3664 = 3604 + 60**, from a diff of the junit files (`9b2aaa6` → `0eece56`):
- **+58:** `tests/test_exact_numbers.py`;
- **+2:** `tests/test_mutation_tools.py` over `mutate_prep_numbers.py`;
- **one id changed, not a test:** `test_slice3_step4`'s time-parametrized
  test, as in every round;
- **removed:** none other.

## 6. What this step does not show, and what step 3 must

**Not claimed:** that every accepted conversion body agrees with the
contract. The conversion is not wired.

**When step 3 wires it,** it must show, each by a test through the
conversion route:
- the body parsed by `ExactJsonBody`, and validated by its model with
  `validated`;
- the conversion's request model reading the budgets as `JsonInteger`, with
  `BIGINT_MAX` (F-3);
- the idempotency fingerprint of a body that holds a `Decimal`.
  `json.dumps` cannot serialize one, and the test routes here fingerprint a
  model dump of `int`s;
- any `jsonb` written from such a body (a criterion's `value`) serialized
  exactly;
- a `number` field holding an exact non-integer: none in RequestCreate's
  stored columns; criteria values are free JSON;
- **Q-C2:** the unknown lead's `403`, pinned at `404` first.

## 7. A finding outside the step (M16.3), not changed

**The production `POST /requests` today**, with FastAPI's parsing:
- **stores `1e-400` as a budget of 0,** where the schema refuses it as not
  an integer;
- **stores `9007199254740993.0` as `9007199254740992`,** another number;
- **refuses `9223372036854775807.0`,** a value the column holds.

**The same parsing serves** `PATCH /requests` and the offers' prices, which
are also `JsonInteger`. This is read from the code, **not measured**.

**Applying `ExactJsonBody` and `validated` to those routes** would correct
it. That changes production routes outside this step, so it is **plan
question Q-C3**, for decision.

## 8. What remains

- **The review of this step.**
- **Then CORRECTION-009's approval,** and the final package per sequence
  row `0b`, before step 1.
- **Q-C3 to decide.**
- **Standing conditions:**
  - OQ8-1 open; R-1 UNMET; K06 UNPROVEN.
  - SALE only.
  - Not a release authorization.
