# R-1 · step 2 — the transformation, the relay's signature, `thread_ref`

**Approved scope.**
- **Step 2 authorized** in the review of `e9fac51` (plan
  `docs/gate/R1_RELAY_PLAN.md`, revision 5): the transformation of Meta's
  notifications, the signing of the relay's envelopes, and the building of
  `thread_ref`, tested with TURAB's own code.
- **Not authorized:** deploying the relay, creating a secret, or receiving
  any real event. Steps 3 and 4.

**Status: CLOSED at `da3d778`** (review of `da3d778`, §8), after the correction
of §7 (not closed at `ced7df7`: document order inside one `value`).
R-1 stays **UNMET**.
- **What a reviewer has not done:** re-run the suite, the mutations or the
  gate. The results are ours.

**What this step does not contain:**
- **sending to TURAB, and the answer to Meta** (step 3, with §5.1's answer
  table). A verified POST is still answered 503 `RELAY_NOT_FORWARDING`
  (step 1); `transform.py` is not called by the application yet;
- **OVERSIZE** (R1-Q1 (a)) and the envelopes' sizes (step 4, duty 7);
- any change to TURAB's code under `src/`.

**Commits:**
- `a562c25`, `9cfdcc4`: plan revision 5 (the review of `e9fac51`);
- `5c8c1f0`: `transform.py`, its tests, its mutation script;
- `29d43c3`: the mutation records (§4);
- `4953ced`, `81f1f98`, `adb5dce`: the evidence round (§5).
- **The correction (§7):** `e1f8138`, `ef3c133`: plan revision 6 (the review of
  `ced7df7`); `5ddf055`: the order kept, its tests, X18 and X19, the before
  record; `80afe91`: the mutation records; `09a6dab`, `a6de9cf`, `47e0264`:
  the evidence round (§7.4).

---

## 1. What step 2 contains (`relay/turab_relay/transform.py`)

`elements(raw)` takes the bytes of a notification whose signature was
verified (duty 2), and returns **one element per message and per status,
in document order**, each in **exactly one class** of §5.1.

### 1.1 The classes, by element kind (§5.1, revision 3)

| Kind | ISOLATED when | DROPPED when |
|---|---|---|
| **a message** | `from`, `id`, `timestamp` or `type` missing or empty; no `metadata.phone_number_id`; the timestamp not Unix seconds in ASCII digits; `from` or `phone_number_id` empty or holding `:`; `contacts` holding `wa_id`s, none equal to `from` (R1-D8) | it carries `group_id` (R1-D7) |
| **a status** | `id`, `status`, `timestamp` or `recipient_id` missing or empty; no `phone_number_id`; the timestamp not Unix seconds; `recipient_id` or `phone_number_id` empty or holding `:`; **a status value Meta does not document** (§3) | `recipient_type` is `group` (R1-D7); the status is `played` (R1-D5) |
| **a change** | — | its `field` is not `messages`; each entry of `value.errors` (R1-D12) |
| **the notification** | its bytes are not JSON | its `object` is not `whatsapp_business_account` (R1-D12) |

- **A status is never checked for `from`, nor against `contacts`.**
- **R1-D8, as accepted:** `from` must equal one of the `wa_id`s present in
  `value.contacts`. The absence of `contacts`, or of any `wa_id` in it, does
  not isolate a message.
- **An ISOLATED or DROPPED element carries no envelope and no content:** its
  reason is a fixed code, never a value of the notification.

### 1.2 The envelope (duty 3)

| | A message | A status |
|---|---|---|
| `provider_event_id` | `message:<wamid>` | `status:<wamid>:<Meta's status>:<Meta's timestamp>` |
| `event_type` | `message` | `status` |
| `external_message_ref` | the wamid | the wamid |
| `thread_ref` | `<phone_number_id>:<from>` | `<phone_number_id>:<recipient_id>` |
| `occurred_at` | Meta's Unix `timestamp`, as RFC 3339 in UTC (`…Z`) | the same |
| `message_type` / `status` | §5.3's table | `sent`→`SENT`, `delivered`→`DELIVERED`, `read`→`READ`, `failed`→`FAILED` |
| content | `body_text`, `media_ref` as §5.3 states | none |

**§5.3, as built:**
- `text`: `TEXT`, with `text.body`;
- `image`, `video`, `document`: their own stored types, with the `caption`
  if present and the media `id`;
- `audio`, `sticker`: their own stored types, with the media `id` only;
- **any other type, documented or not: `OTHER`, without content.**

No stored value equals an internal type. A document's `filename`, the
media's `mime_type`, `sha256` and `url` are not carried.

**The bytes sent:** compact JSON, UTF-8, non-ASCII kept as UTF-8. The serialization is
fixed here; duty 7 (step 4) measures these bytes.

### 1.3 The relay's signature (duty 4)

- `sign(envelope, key)`: `sha256=<hex>`, an HMAC-SHA256 over **the exact
  bytes** of the envelope; the header is `X-Turab-Relay-Signature`.
- `signing_key()`: `TURAB_RELAY_SIGNING_SECRET`, **the variable TURAB itself
  reads**, so the two sides cannot name different keys. **Refused:** absent
  or empty (R1-T4.4); **equal to Meta's app secret** (R1-T4.3), compared
  through `compare_digest`.

## 2. The tests (`tests/test_r1_step2.py`, 80)

Every notification is synthetic, built on the structures Meta documents
(E18–E26, E28–E52). **The relay's output is checked by TURAB's own code:**
`parse_envelope`, `verify`, `SCOPED`, `_accepted`, `STATUSES`, `LINK_TYPES`,
`SECRET_VARIABLE`, `SIGNATURE_HEADER`.

| Plan | Tests |
|---|---|
| R1-T3.1, R1-T3.2 | a text message and a status, each one envelope **TURAB's `parse_envelope` accepts**, payload compared exactly; each Meta status to TURAB's |
| R1-T3.3 | a POST with two entries, three changes, messages and statuses: one envelope per element, **in document order**, each with its own business number |
| R1-T3.4 | another `field`, another `object`: DROPPED, no envelope |
| **R1-T3.5** | **§5.3 type by type (18 rows)**: the stored type and the exact content keys; for every type the table gives no content, **the content string is absent from the envelope's bytes**. An undocumented `caption` on `audio` and `sticker` is not carried |
| R1-T3.6 | `sent` then `read` without `delivered`: accepted by TURAB's `_accepted` in that order |
| R1-T3.7 | every forwarded envelope of every test goes through `parse_envelope` |
| the timestamp | three known instants; nine malformed values (empty, letters, negative, decimal, exponent, a space, Arabic-Indic digits, 5000 digits, a year past 9999): isolated, for both kinds |
| §5.1 by kind | each required field of a message, and of a status, missing; **a status is never checked for `from` or against `contacts`**; no business number; `played`; an undocumented status; `value.errors`; non-JSON and non-WhatsApp notifications |
| **R1-T4.1, R1-T4.2** | the signature over the exact bytes: **TURAB's `verify`** true; another key, one byte changed: false; the header and the variable are TURAB's own |
| R1-T4.3, R1-T4.4 | a key equal to Meta's app secret; no key, absent or empty: refused |
| R1-T6.1 to R1-T6.6 | `thread_ref` for a message and a status; two business numbers; **TURAB's `SCOPED`** on every `thread_ref`; an identifier with `:` or empty, for the customer, the business and a status's recipient: isolated; group messages and group statuses: dropped |
| **R1-T6.7** | R1-D8: `contacts` absent, empty, without `wa_id`, with `from`, with `from` among others: forwarded; one other `wa_id`, several others: **isolated, no content** |
| no content | a batch mixing the classes: only FORWARD elements carry anything |

## 3. A reading of ours, submitted for decision

**A status value Meta does not document** (anything outside `sent`,
`delivered`, `read`, `failed`, `played`) is **ISOLATED**, reason
`STATUS_NOT_KNOWN`. The plan does not decide it.
- **Why not forward it:** TURAB's own parser refuses a status outside its six
  (`parse_envelope`), so the envelope would be answered 400. Under R1-D3 (a)
  that keeps Meta's answer not 200, and Meta would redeliver it for up to 7
  days for nothing.
- **Why not drop it:** DROPPED is for what the plan decided out of scope; an
  unknown value is a notification the relay cannot read, which is ISOLATED's
  meaning, with its alert.

**Submitted to the reviewer.** It is tested
(`test_a_status_value_meta_does_not_document_is_isolated`).

## 4. Mutation evidence

`db/dev/mutate_r1_step2.py`, 29 mutations:

| Group | Mutations |
|---|---|
| X, duty 3 | a text's body not carried; a caption carried for every media type; a media id not carried; an unlisted type passed through; an unlisted type carrying content; an image's caption dropped; a message's event id without its prefix; a status's without its timestamp; `delivered` mapped to `READ`; `played` not dropped; the instant without its zone; the timestamp not checked as digits; non-ASCII digits accepted; any object; any field; `value.errors` not counted; a missing timestamp not reported as a missing field |
| I, duty 6 | a message's `thread_ref` reversed; a status's reversed; a message's identifiers not scoped; a status's; a colon accepted; contacts not checked; a message without a `wa_id` isolated; a group message forwarded; a group status forwarded |
| K, duty 4 | the signature over other bytes; a key equal to Meta's app secret accepted; an empty key accepted |

- **The official runs:** two, at `5c8c1f0`, clean tree, source fingerprint
  `9d6319a4…e172`: **29/29 killed in each, outcomes identical**.
  `evidence/R1-STEP2-MUTATIONS-AT-5c8c1f0.txt` and `-AT-5c8c1f0-REPEAT.txt`
  (renamed to their tree in `80afe91`; see §7.3).
- **The trial run**, outside the record: 29/29 (`-AT-5c8c1f0-TRIAL.txt`).
- **One test was strengthened before it:** the `audio` and `sticker` rows of
  R1-T3.5 now carry an undocumented `caption`. Without it, "a caption carried
  for every media type" (X2) would have passed the table test.
- **Not mutated**, with the reasons in the script: the refusal of an
  undocumented status (its removal is a crash, `KeyError`, not a weakening);
  the `business is None` part of the required checks (the scoping check that
  follows isolates the element anyway).

## 5. The evidence round

**Superseded by §7.4** on the corrected tree. `gate-run.txt` and
`TEST-RUN-PROVENANCE.txt` now hold that tree's runs. The rows below are
readable at their own commits.

Every row ran on a clean tree with source fingerprint `9d6319a4…e172`,
the mutation runs' own.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules; suite **3332/3332** | `4953ced` (run at `29d43c3`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS | `81f1f98` (run at `4953ced`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3332 passed, 0 failed, 0 errors, 0 skipped** | `adb5dce` (run at `81f1f98`) | `evidence/TEST-RUN-PROVENANCE.txt`; **`bound`** |
| Mutations | 29/29, twice, identical | `29d43c3` (run at `5c8c1f0`) | §4 |

The matrix has no rule for the relay (it maps RFC-001's authorization
rules); the relay's tests are in the suite's count.

## 6. What remains

- **The review of this delivery,** and the decision on §3.
- **Step 3,** not authorized: sending each FORWARD envelope to TURAB, signed;
  §5.1's answer table; duty 5's redelivery against a test double and against
  TURAB's real application and test database (R1-T5.6).
- **Step 4,** not authorized: duty 7 with R1-Q1 (a); R-1's evidence; the
  barriers' measured state; the closure record.
- **The access-log condition** (§5.5) stands before any deployment or
  Callback setting.
- **R-1 UNMET; no real event;** K06 an independent condition before the
  release gate; SALE only.

---

## 7. The review of `ced7df7`, and the correction

**Step 2 was not closed at `ced7df7`.** Recorded in the plan, revision 6
(`e1f8138`, named in `ef3c133`).
- **§3 is decided:** an undocumented status is ISOLATED with
  `STATUS_NOT_KNOWN`, with no envelope or content, and is counted and
  alerted on in step 3.
- **The gap:** R1-T3.3's "document order" was not kept inside one `value`.
  The loop walked the kinds in a fixed order (`errors`, then `messages`,
  then `statuses`), so when `statuses` came first in `value`, the messages
  still came out first. The test of §2 wrote `messages` before
  `statuses`, so it could not tell the two behaviours apart.

### 7.1 Before: the failure, pinned on the code of `ced7df7`

`evidence/R1-STEP2-ORDER-BEFORE.txt`:
- `transform.py` was **byte-identical to `ced7df7`'s** (sha256 `b4cb878e…8e53`
  in the tree and at HEAD); only the new tests were added.
- **6 failed:**
  - five of the six orders of `errors`, `messages` and `statuses` inside
    one `value`. The sixth, `errors-messages-statuses`, is the code's own
    fixed order and passes by coincidence;
  - `statuses` before `messages`, written directly as bytes.
- **3 passed:** the old R1-T3.3 test, the coincidental order, and the
  `metadata`/`contacts` test below (it guards the correction, not the
  defect).

### 7.2 The correction (`5ddf055`)

- `elements()` now walks `value`'s own keys **in the order they came**,
  emitting the elements of `errors`, `messages` and `statuses` where each
  key stands. The order of `entry` and of `changes` was already the
  document's.
- **`metadata` and `contacts` are still read before any element,**
  wherever they are written: keeping the order does not make `value` a
  stream.
- **`json.loads` keeps the key order of the bytes** (Python ≥ 3.7, dicts
  keep insertion order; checked here on `{"statuses":…,"messages":…,"errors":…}`).

**The tests, 8 new (88 in the file):**

| Test | What it fixes |
|---|---|
| `…keep_the_order_of_its_keys`, six orders | inside one `value`: each kind's elements where its key stands; the test first checks that the parsed `value` really has that key order |
| `…statuses_before_messages_in_the_bytes_meta_sends` | the review's case, written as bytes: no dict in the test chooses the order |
| `…metadata_and_contacts_after_the_messages_still_apply` | a `contacts` written after the messages still isolates a mismatched `from` (`CONTACT_MISMATCH`, no content); a matching one forwards with the business number written after |

**One existing expectation was the defect itself:**
`test_no_element_ever_carries_content_unless_forwarded` expected `errors`
first, though `_notification` writes them last. It now expects the
document's order. Its assertion of no content is unchanged.

**A limit, not claimed:** duplicate keys inside one JSON object. Python's
`json.loads` keeps the **last** value (checked: `{"a":1,"a":2}` →
`{"a": 2}`), so a `value` with two `messages` keys yields the second
array's elements, at the place of the **first** key. RFC 8259 §4 says
names "SHOULD be unique" and leaves duplicates' behaviour to the
implementation. Meta documents no duplicate keys. This is neither tested
nor claimed.

### 7.3 Mutation evidence on the corrected tree

`db/dev/mutate_r1_step2.py`, **31 mutations**:
- **X18:** the fixed order of kinds restored;
- **X19:** `contacts` read as a stream (only what comes before the
  messages counts).

| Record | Tree | Result |
|---|---|---|
| `R1-STEP2-MUTATIONS.txt`, `-REPEAT.txt` | `5ddf055`, clean, fingerprint `c183eacf…34f1` | **31/31 killed, twice; identical outcomes** once run times are set aside |
| `R1-STEP2-MUTATIONS-AT-5c8c1f0.txt`, `-AT-5c8c1f0-REPEAT.txt`, `-AT-5c8c1f0-TRIAL.txt` | `5c8c1f0` (renamed from the records of §4) | 29/29, as §4 states |

- **X18 is killed** by the five order tests and the bytes test.
- **X19 is killed** by the `contacts` test.

### 7.4 The evidence round on the corrected tree

Every row ran on a clean tree with source fingerprint
**`c183eacf…34f1`**, the mutation runs' own.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Authorization matrix | 222 rules; suite **3340/3340** | `09a6dab` (run at `80afe91`) | `AUTHORIZATION_EVIDENCE_MATRIX.md` |
| PostgreSQL gate | PASS: all database-level contract tests passed; the same 67 operations | `a6de9cf` (run at `09a6dab`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **3340 passed, 0 failed, 0 errors, 0 skipped** | `47e0264` (run at `a6de9cf`) | `evidence/TEST-RUN-PROVENANCE.txt`; **`bound`** |
| Mutations | 31/31, twice, identical | `80afe91` (run at `5ddf055`) | §7.3 |

**The first gate attempt** ran without the `PG*` variables and stopped at
step 2: `dropdb` could not connect as `root`. The run was not reported as
a result, and its record was restored. It was re-run with the suite's own
local settings (`PGHOST=127.0.0.1`, `PGUSER=turab`).

### 7.5 What remains

- **The review of this correction.** Step 2 is not closed.
- **Step 3 stays unauthorized** until that review.
- **The access-log condition** (§5.5) stands.
- **R-1 UNMET; no real event;** K06 an independent condition before the
  release gate; SALE only.

---

## 8. The closure

**The review of `da3d778` closed step 2 at `da3d778`, and authorized step
3** within the plan's scope. Recorded in the plan, revision 7.
- **The reviewer checked:** the correction, the before record, the new
  tests, and the two mutation records (31/31, the same tests killing each
  mutation).
- **The reviewer did not re-run anything.** The suite's 3340/3340, `bound`
  and the gate's PASS are our recorded results.
- **This closure does not** close R-1, or allow deploying the relay,
  creating a secret, or receiving any real event. The access-log condition
  (§5.5 of the plan) stands. **R-1 UNMET; no real event;** K06 an
  independent condition before the release gate; SALE only.
