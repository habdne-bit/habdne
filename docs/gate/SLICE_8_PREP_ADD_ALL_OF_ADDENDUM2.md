# Slice 8 · preparatory step `add_all_of` — second addendum (review of `44c3d65`)

**What the review found** (by reading the text and the code; nothing re-run):
- **`integer`:** JSON Schema 2020-12 counts `1.0` as an integer, a number with
  a zero fractional part (Validation §6.1.1).
  - CORRECTION-009 declares `budget_max_dzd` an integer.
  - `_type_holds` admitted only a Python `int`, so `body_violations` refused
    `1.0`, which the generated schema accepts.
  - The test's independent judge used the same Python check, so the
    agreement cases could not see the difference.
- **A smaller bound:** in `_value_problems`, `math.isfinite` on a very large
  int may raise `OverflowError` instead of giving a verdict.
- **`0009`:** the plan's §6.6 acceptance test for a party's deletion
  generalized `DECLINED`'s result to every terminal lead, while M14 measures
  the deletion of a `CONVERTED` request's party refused.

**What it asked:**
1. the same body with a budget of `1.0`, tested on the current code;
2. then `integer` fixed to agree with the schema, the agreement tested after
   the fix;
3. the overflow handled, or its acceptance restricted by a test;
4. the evidence rebound to the new tree;
5. §6.6's two cases named, each with its verdict.

**Status: DELIVERED for review.** The preparatory step is **not closed**
until it is reviewed.
- **Not approved:** CORRECTION-009, the Delta and `0009` stay drafts, not
  activated.
- **Not authorized:** step 1.
- **What a reviewer has not done:** re-run anything. The results are ours.

**Commits:**
- `66c4aa9`: the fix, the tests, the before record, the mutations and their
  trial; §6.6 and the `0009` draft's wording;
- `7dd8c2d`, `d26fcfd`: the expected contract regenerated;
- `fb708b2`: the mutation pairs;
- `5589b68`, `83de5d7`, `699706f`: the evidence round;
- `02651aa`: this note, plan revision 7.

---

## 1. Before (`evidence/PREP-ADD-ALL-OF-ADDENDUM2-BEFORE.txt`)

**The tree:** `contract.py` and the generator byte-identical to `44c3d65`'s;
only the test file changed. **5 of 78 tests failed, each for its pinned
reason:**

| Test | How it failed on `44c3d65`'s code |
|---|---|
| **the same payload, a budget of `1.0`** (agreement) | the independent judge, now written to the specification, **accepts**; `body_violations` **refuses**: `body.payload.budget_max_dzd: not of type integer` |
| a `minimum` of `10**400` | **`OverflowError: int too large to convert to float`** |
| equality item by item | `[True]` accepted for `const: [1]` |
| distinct values in an `enum` | `[[1], [True]]` refused as duplicates |
| a number JSON cannot carry | `1e400` (parsed as infinity) accepted as a `number` |

**The three after the review's two:** the same class of difference, found
by checking each of the judge's type and equality functions against the
specification after the review's finding.
- **The equality:** `_json_same` compared arrays and objects as Python
  values. A boolean inside an array passed for a number, against Core §4.2.2
  ("Instance Equality").
- **The non-finite float:** a value no JSON text can carry.

**Passing already:** the budget of `1.5` (refused by both), and the budget
of `10**400` (accepted by both).

## 2. The fix (`src/turab/auth/contract.py`)

**`_type_holds`,** to JSON Schema 2020-12 Validation §6.1.1:
- **a number** is an `int` that is not a boolean, or a **finite** `float`;
- **an `integer`** is a number with a zero fractional part: an `int`, or a
  float for which `is_integer()` holds. So `1.0` is one, `1.5` is not.
- **A Python `int` is never converted to a float:** no `OverflowError`, and
  every comparison is exact.

**`_value_problems`, `minimum`:** a number by that same test. The
`math.isfinite` call that overflowed is gone. A `minimum` of `10**400` is
**admitted**, and compared exactly; the test pins both.

**`_json_same`,** to Core §4.2.2:
- numbers by their mathematical value (`1` equals `1.0`);
- arrays item by item;
- objects key by key;
- a boolean never a number, at any depth.

It serves `const`, `enum`, and the loader's duplicate check, so `[[1],
[True]]` is no longer two copies of one value.

**The test's independent judge** was rewritten from the specification's
text (`_number`, `_same`, `integer` as `value == math.floor(value)`), not
from the code.
- **Why it matters:** it can now disagree with `body_violations`, which is
  how the `1.0` case failed before.

## 3. A limit, declared and pinned by a test

**What happens:**
- Python's `json` reads the text `1e400` as **infinity**, and accepts `NaN`
  and `Infinity`, which are not JSON.
- The judge refuses all three as **not a number**.
- **The disagreement:** `1e400` written in a body is mathematically an
  integer, which the generated contract would accept, but the parser has
  lost it before the judge sees it.

**Its scope:**
- no field of CORRECTION-009 has a bound near the double range;
- the judge is wired to no route yet;
- the parser is decided where a route uses it, not here.

**Tested:** `test_a_number_json_cannot_carry_is_refused_and_the_limit_is_stated`.

## 4. Tests (`tests/test_contract_add_all_of.py`, 78: the 71, and 7)

| Added | What it shows |
|---|---|
| agreement: a budget of `1.0`, of `1.5`, of `10**400` | the generated contract (independent judge) and `body_violations` agree: accepted, refused, accepted |
| a `minimum` too large for a float | admitted at load; judged exactly (`10**400` passes, `10**400 - 1` is below) |
| equality item by item | `[True]` is not `[1]`; `[1.0]` is; `{"a": true}` is not `{"a": 1}` |
| distinct values in an `enum` | `[[1], [True]]` admitted |
| a number JSON cannot carry | §3's limit |

## 5. Mutations (`db/dev/mutate_prep_add_all_of.py`, 53 = the 47 and J1–J6)

**Re-anchored where the code moved:**
- V9 (a boolean taken for a number);
- S2 (`minimum`'s structure);
- S18, now "a non-finite float taken for a number": its old anchor, the
  `isfinite` call, is gone.

| J | Weakening |
|---|---|
| J1 | `integer` only a Python `int` (the review's finding, restored) |
| J2 | `integer` any number |
| J3 | `minimum`'s finiteness checked through a float again (the overflow, restored) |
| J4, J5 | arrays, objects compared as Python values |
| J6 | numbers equal only when of one Python type |

**The trial** (`evidence/PREP-ADD-ALL-OF-ADDENDUM2-MUTATIONS-TRIAL.txt`, tree
not clean, by design) killed all 53.

**The pairs**, on a clean tree at `d26fcfd`, with the four earlier scripts
that mutate `contract.py`:

| Record | Result |
|---|---|
| `PREP-ADD-ALL-OF-ADDENDUM2-MUTATIONS.txt`, `-REPEAT.txt` | 53 mutations; **none survives**; pair identical |
| `PREP-ADD-ALL-OF-ADDENDUM2-RERUN-CORRECTION-004-MUTATIONS*.txt` | 11; **none survives**; identical |
| `PREP-ADD-ALL-OF-ADDENDUM2-RERUN-SLICE6-STEP2-MUTATIONS*.txt` | 33; **none survives**; identical |
| `PREP-ADD-ALL-OF-ADDENDUM2-RERUN-SLICE7-STEP2-MUTATIONS*.txt` | 51; **none survives**; identical |
| `PREP-ADD-ALL-OF-ADDENDUM2-RERUN-SLICE7-STEP3-MUTATIONS*.txt` | 68; **none survives**; identical |

**"Identical"** as in the step's note §4. The cause lines carrying a sampled
`trace_id` are left out of the text: 52 in each Slice 7 step 3 run, none in the other eight, as in the earlier rounds. Each run was made in a batch of its own, on a clean tree, to stay within the background time limit; a run is reused only when its last line is its last section's verdict.

## 6. The evidence round

Every row ran on a clean tree with source fingerprint `567ef5f4fcb189dc64029881dd5889d999fbc08f8ad6a424a524f08b70f0f15c`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules, all PASS; **3604/3604** | `5589b68` (run at `fb708b2`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | **PASS** | `83de5d7` (run at `5589b68`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | tests=3604, failures=0, errors=0, skipped=0; `run_binding`: **`bound`** | `699706f` (run at `83de5d7`) | `evidence/TEST-RUN-PROVENANCE.txt` |

**The count:** **3604 = 3597 + 7**, from a diff of the junit files (`d071cdf` → `699706f`):
- **+7:** `tests/test_contract_add_all_of.py`;
- **one id changed, not a test:** `test_slice3_step4`'s time-parametrized
  test, as in the earlier rounds;
- **removed:** none other.

## 7. The expected effective contract

Regenerated at `66c4aa9` by `db/dev/generate_slice8_expected_contract.sh`
(`7dd8c2d`, `d26fcfd`). Its generated content, part 0's verdicts and both diffs, is
identical to `7e7da47`'s.
- **What changed:** the header, which names the tree.
- **Why the verdicts did not move:** none of part 0's seven payloads carries
  a float or a nested value.
- **The script's fixed header text** now says exactly what the earlier
  versions share: `d26fcfd` corrected `7dd8c2d`'s first wording.

## 8. `0009`: a party's deletion, each terminal status named

**In the plan's §6.6**, replacing the one sentence that generalized
`DECLINED`'s result:

| Terminal status | Deleting the lead's party | Basis |
|---|---|---|
| `DECLINED` | **accepted**; `party_id` NULL; `raw_payload` and `raw_text` kept | measured: M9, M14 |
| `CLOSED` | **accepted** expected, by the same guard rule | **not measured**: the test measures it, and a refusal is a finding |
| `CONVERTED` to a request | **refused** by `requests_party_id_fkey` (`ON DELETE RESTRICT`); its target cannot become NULL; its request cannot be deleted | measured: M14 |

**In every status:**
- re-pointing `party_id` is refused;
- **a NULL written by hand** passes the guard, by the guard's text: for
  `CONVERTED` too, **not measured**;
- the service never writes one.

**The same restriction** is applied where the plan's Q-B1 and the `0009`
draft said "a `CONVERTED` lead's links never become NULL": **no deletion**
makes them NULL.
- **Only the draft's docstring changed;** its statements, which M12–M14
  measured, did not.

## 9. What remains

- **The review of this second addendum**, which closes the preparatory step
  or does not.
- **Then the review** of CORRECTION-009, the Delta and `0009` in final form,
  before step 1.
- **Standing conditions:**
  - OQ8-1 open; `raw_text` capture not widened.
  - R-1 UNMET; K06 UNPROVEN.
  - SALE only.
  - Not a release authorization.
