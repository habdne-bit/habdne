# Slice 5 · step 4 — the internal read, the customer read, and the match queue

**Approved scope (review of `921ed01`).** "نطاق Step 4 يبقى كما في الخطة:
internal read + customer read + match queue، وفق G5-6/G5-7/G5-11، مع إثبات
withholding وعدم تسريب أي private expectation/claim. هذه النقطة الأخيرة
ستكون من أهم شروط قبولي للخطوة 4."

**Status:** delivered for review. **Not** closed.

**Still open:**
- G5-10 and G4-5R;
- K06 is UNPROVEN;
- L-S5-3a and L-S5-3b are carried to step 6 (plan §8).

**Commits:**
- `6c8498a`: the code, the tests, RFC-001 Appendix B, DL-13, the mutation
  script, the matrix rows, the before-fix record;
- `5b2b5af`: one queue test for the gap the first mutation run found
  (§7.1);
- `ebe05a0`, `282edd6`, `dca4536`, `bb37715`: the evidence (§8).

---

## 1. What step 4 contains

| File | Role |
|---|---|
| `src/turab/services/opportunity_views.py` (new) | the customer render with [R4-2]'s withholding; the internal view; the match queue |
| `src/turab/auth/loaders.py` (`load_opportunity`) | G5-7 (a): a SHARED opportunity only |
| `src/turab/dto/boundaries.py` | `CustomerOpportunityView` and its renderer conform to the frozen types; `CustomerPropertySummary` (four fields) |
| `src/turab/services/access.py` | `read_opportunity` (recorded), `customer_opportunity`, `match_queue` (audited once) |
| `src/turab/api/routes/me.py`, `matching.py` | the three routes |
| `docs/rfc/RFC-001-APPENDIX-B-opportunity-view.md` (new), `docs/DESIGN_LEDGER.md` (DL-13) | the numbered addendum G5-6 (a) requires (§6) |
| `tests/test_slice5_step4.py` (new) | 40 test cases |
| `db/dev/mutate_slice5_step4.py` (new) | 23 mutations (§7) |

**What did not change:**
- no migration and no contract change: the three operations are declared in
  the frozen contract;
- no write path: step 4 only reads;
- `docs/handoff/` is untouched.

### 1.1 The customer read, `GET /me/opportunities/{id}`

**Who may see it (RFC-001 §4; G5-7 (a)).** The loader admits an
opportunity when:
- its request's party is the caller's (`opportunities.request_id →
  requests.party_id`; no relation is read); and
- **it is shared** (`shared_at IS NOT NULL`).

Otherwise the answer is the customer-scoped one an unknown id gets, and the
attempt is recorded as a denial.

**What is rendered (G5-6 (a); RFC-001 Appendix B).** The frozen
`CustomerOpportunityView`, key for key:

| Scope | `property` |
|---|---|
| SUMMARY_ONLY | `CustomerPropertySummary`: `property_id`, `property_type`, `supply_mode`, `canonical_location_id`. No area, no band |
| PROPERTY_DETAILS_ALLOWED, CONTACT_AFTER_CONFIRMATION | the full frozen `CustomerPropertyView` |

**Never rendered, at any scope:**
- `contact`: the frozen type has no field for it (F5-1);
- an offer term;
- a snapshot, `approved_match_id`, `current_offer_id` or a binding (R9.2).

**[R4-2], at each render.** For each entry of `why_real.criteria` and of
`known_differences`:
1. The field its pinned rule reads is the property's: `property_type`,
   `land_area_m2` or `built_area_m2`.
2. The entry is kept only when that field's **current** value equals the
   match's `property_snapshot` value. The comparison is exact: `Decimal`
   for areas, null included (§2, item 4).
3. A code not shown at the scope is dropped too, so the rule fails closed.

**What the rule never touches:**
- the stored row (`why_real` is written once, `0006` rule 2);
- the internal view.

**Exact numbers:** the area is the stored `numeric`, written by its digits
(`exact_json`).

### 1.2 The internal read, `GET /opportunities/{id}`

**Who:** ADMIN, OPERATOR and REVIEWER, by the contract's `x-roles`.

**What:** the stored `InternalOpportunityView`, unfiltered. Its stored
`why_real` is shown even where the customer's response withholds an entry.

**Recorded:** each read (R6.2, R6.3; plan §3.6; kind `OPPORTUNITY`). An
unknown id is 403 `OBJECT_NOT_AUTHORIZED`, and that denial is recorded, as
`read_match` does.

### 1.3 The match queue, `GET /backoffice/queues/matches` (G5-11)

**Membership.** Every condition reads a stored column, and no engine runs
per row:
- not superseded, **per offer** (G5-2): no later match of the same request,
  property, policy and evaluated offer. A strict tie keeps both;
- the property is canonical now;
- the eligibility is not REJECTED;
- no opportunity was created from the match;
- its latest review is absent, or is NEED_MORE_INFORMATION.

**Priority and reason:**

| Case | `priority` | `reason` |
|---|---|---|
| ELIGIBLE | HIGH | `READY_FOR_REVIEW` |
| ELIGIBLE, latest review NMI | HIGH | `AWAITING_INFORMATION` |
| NEEDS_CONFIRMATION, NEED_MORE_INFORMATION | NORMAL | the first reason's seeded code, or its `basis` when it has none (§2, item 2) |

**The page:**
- **Order:** priority, then `evaluated_at`, then `match_id`.
- **Each item** carries `id`, `kind: MATCH`, `priority`, `created_at` (the
  match's) and `reason`. `QueueItem` is open, so it also carries
  `request_id`, `property_id` and `eligibility`.
- **Paging:** as the Slice 3 queues, the whole queue with `next_cursor`
  null.
- **Audit:** one record, with its count and no ids (R6.3c).

## 2. Interpretations to confirm

The plan left these details open. Each is one place in the code.

1. **The match queue's vocabulary is G5-11's proposal, as written.**
   - The review of `288bfdb` accepted G5-11 (a) for the OPPORTUNITY queue.
     For the match queue the plan asked for the membership, priority and
     reason vocabulary to be decided.
   - The review of `921ed01` authorized the match queue "per G5-11", so the
     proposal is implemented as written.
   - **The vocabulary itself is put to the reviewer for confirmation.**
2. **The reason of a NORMAL item** is the first reason of the match's
   `explanation.reasons`, by its seeded code. Measured on real matches, the
   first reason of a never-confirmed freshness has no code
   (`reason_code: null`, `basis: NEVER_CONFIRMED`). There the item's reason
   is the basis. A null reason would say nothing actionable (API_CONTRACTS
   §5: "state why it is actionable now").
3. **The item's `created_at` is the match's creation time.** The Slice 3
   precedent is the property's own time.
4. **Null against null is not a change** ([R4-2]: "when they differ").
   - A `BUILT_AREA_MIN` UNKNOWN difference exists because no built area was
     recorded, and the customer sees that same null in `property`. So the
     entry stays.
   - A null on one side only is a change, and withholds the entry.
   - My first version withheld every null. I corrected it before any test
     ran, and `test_an_unknown_difference_stays_while_the_area_is_still_unknown`
     fixes the rule.
5. **The full `CustomerPropertyView` includes `local_location_detail`** at
   PROPERTY_DETAILS_ALLOWED and above.
   - The frozen type declares it. G3-12 withheld it in the PUBLIC list only.
   - Its content is free text that a staff member records. If the reviewer
     wants it withheld from customers too, that is a narrowing, and one
     line.
6. **The property rendered is the opportunity's own row**, even if it later
   became an alias. Identity consolidation after creation is Slice 3's
   RESOLVE_IDENTITY work, and E04 (step 6).

## 3. Tests (40 cases, `tests/test_slice5_step4.py`)

**The condition of acceptance.** Proof of the withholding, and of no leak
of a private expectation or a claim. Every test below is over HTTP, through
the real run and the real APPROVED review.

**No leak (mandatory test 5; R8.2a; R9.3):**
- **at each scope,** with a seller expectation that DECIDES the budget
  (asking 35M over a 30M maximum; expectation 27 777 777: PASS internally)
  and a document known from a CLAIM that the engine linked to its result.
  The body contains none of:
  - the expectation, in any form;
  - the claim's id;
  - the document's value;
  - DOCUMENT_TYPE or BUDGET_MAX;
  - a snapshot, `approved_match_id`, `current_offer_id`, a binding, a
    delta, a rule or a score;
  - `contact` or a phone;
- **pairs, at each scope, whose two customer bodies are identical apart
  from ids and times:**
  - DOCUMENT_TYPE backed by a claim, and not;
  - ROOMS_MIN backed by a claim, and not;
  - BUDGET_MAX PASS by the price, and by the expectation;
  - LOCATION PASS by an ancestor, and by the property's own location. Neither
    body names LOCATION.

**The frozen type (G5-6 (a); R9.5; F5-1, F5-2, F5-3):**
- at each scope, the body validates against the frozen schema;
- its keys are the frozen type's;
- the property is the four fields at SUMMARY_ONLY, and the full view above;
- `contact` is absent;
- an area is an exact JSON number (`1234567.89`).

**The withholding ([R4-2]):**
- **at PROPERTY_DETAILS_ALLOWED, in order:**
  - unchanged: present;
  - 110 (the outcome flipped): absent from the customer, present in the
    internal view;
  - 150 (the outcome unchanged): absent;
  - back to 137.50: present again;
  - the stored `why_real` unchanged throughout;
- a changed `property_type`: PROPERTY_TYPE absent at every scope;
- at SUMMARY_ONLY, an area change cannot show;
- an unknown difference stays while the area is still unknown, and goes
  once it is recorded;
- **pure:** exact `Decimal` equality, the scope's list, fail-closed.

**Visibility (G5-7 (a)):** each of these is answered as an unknown id:
- an unshared opportunity. The denial is recorded, and the opportunity is
  visible once shared;
- another party's opportunity;
- an opportunity reached through a relation to the property.

**The internal read:**
- each staff role reads the stored view, which equals the approval's
  response;
- the read is recorded;
- an unknown id is 403 and recorded;
- a customer is refused.

**The queue:**
- **membership, priority and reason** on nine real matches:
  - in, with their priority and reason: ELIGIBLE; ELIGIBLE with an NMI
    review; permission missing; never confirmed; document unknown;
  - out: REJECTED by the run; REJECTED by review; approved;
- **per offer:** two offers give two items. A new evaluation of one offer
  replaces that offer's item only;
- **an opportunity:** it keeps the match out even when the latest review is
  NMI (SQL fixture, as in step 3; added at `5b2b5af`, §7.1);
- **an alias:** its match leaves the queue;
- **order and audit:** HIGH before NORMAL; one LIST record with the count;
- **a customer** is refused.

## 4. Before the change (measured)

`evidence/SLICE5-STEP4-BEFORE-FIX.txt`, in an isolated worktree at
`cb1a828`, with the test file of `6c8498a` (39 cases). The file collects
there: it imports no new module at module level. **37 of 39 fail:**
- **G5-7 (a) was not enforced:** an UNSHARED opportunity was returned to its
  customer (200);
- **F5-1:** a `contact` key at every scope;
- **no property was joined:** `property` was null, so neither the summary
  nor the full view existed;
- **[R4-2] was absent:** a corrected area and a changed type left their
  entries; an unknown difference stayed after the area was recorded;
- **the internal read and the queue were not routed** (404).

**The two that pass** (another party; a relation) were already correct.
They are kept as regression guards.

**The fortieth test** (§7.1) was added after this record. The rule it tests
is a condition of a queue that did not exist at `cb1a828`.

**The code was written before this record, as in steps 2 and 3.**

## 5. Existing tests that changed, and why

**`tests/test_dto_boundaries.py`** tested the Slice 0 renderer, which G5-6 (a)
corrects:
- **S33 (`test_summary_only_withholds_property_detail`):** the property at
  SUMMARY_ONLY was the public summary (`availability`, `offers`, areas). It
  is now the four fields.
- **S34 and the release test** (`test_contact_is_withheld_…`,
  `test_contact_is_released_…`):
  - the renderer took a contact, and released it at the highest scope;
  - both tests are replaced by
    `test_the_customer_view_has_no_contact_at_any_scope`, per Appendix B;
  - the matrix row `R8.3 / S34` becomes `R8.3 / S34 (Appendix B)`.
- **R8.2a (`test_no_scope_lifts_the_never_serialized_floor`):** unchanged
  in what it asserts. It no longer passes a contact.

## 6. RFC-001 Appendix B and DL-13

G5-6 (a): "RFC-001's affected rows … are amended by a numbered addendum, not
by editing its body". The precedent is Appendix A, for INV-1 and INV-2.

`docs/rfc/RFC-001-APPENDIX-B-opportunity-view.md` amends:
- R8.2's three rows: the four fields, no band, no offer term, no contact;
- R8.3: no contact through this DTO;
- S33, S34 and S36a.

R8.2a stands, and is strengthened. `DESIGN_LEDGER.md` DL-13 records the
gap and its answer. The RFC body is unchanged.

## 7. Mutation evidence

`db/dev/mutate_slice5_step4.py`, 23 mutations, each weakening ONE rule:
- **V1–V4:** visibility and the frozen type;
- **W1–W6:** the withholding;
- **I1–I2:** the internal read;
- **Q1–Q11:** the queue.

Before the run, every mutated text was checked by hand to compile (the
lesson of step 3's N2). The runner itself does not check this.

### 7.1 The first run, kept

`evidence/SLICE5-STEP4-MUTATIONS-FIRST-RUN.txt`, at `6c8498a`, clean tree.
**22 of 23 failed. Q3 survived:** "an approved match stays queued", which
drops the no-opportunity condition.
- **Why it survived.** An approved match also leaves the queue through its
  latest review, because APPROVED is final. So no test separated the two
  conditions.
- **Why it is not redundant.** An opportunity can coexist with a later,
  non-final review: the case step 3 tests for "decided".
- **The fix.** At `5b2b5af`,
  `test_a_match_with_an_opportunity_leaves_the_queue_whatever_its_latest_review`
  builds that case: an APPROVED review and its opportunity, then a later NMI
  review, written by SQL. Only the opportunity can keep the match out.

### 7.2 The record

`evidence/SLICE5-STEP4-MUTATIONS.txt`.
- **Run:** at `5b2b5af`, on a clean tree, source fingerprint
  `6ed8ab7a…c655`.
- **Result: 23 of 23 fail, none survives.** The baseline is 40 passed.
- **Restoration:** every mutated file was restored, and verified by sha256.

**For the condition of acceptance:**
- **V3** (a `contact` field) and **V4** (the internal view served to the
  customer) are killed by the frozen-type tests and by the no-leak tests.
  V4 alone fails 26 tests;
- **W1–W6** (each part of the withholding) are each killed by their own
  over-HTTP or pure test.

## 8. The evidence round

Each row ran on a clean tree, source fingerprint `6ed8ab7a…c655`.

| Evidence | Result | Commit | Record |
|---|---|---|---|
| Mutations | 23/23 fail | `5b2b5af` → `ebe05a0` | §7.2 |
| Authorization matrix | **168 rules**, all PASS (six new for step 4; one replaced, §5); suite 2239/2239 | `282edd6` | `AUTHORIZATION_EVIDENCE_MATRIX.md`; `--check --no-run`: current |
| PostgreSQL gate | PASS; 70 database-level PASS notices, 0 FAIL; 67 operations in parity | `dca4536` (run at `282edd6`) | `evidence/gate-run.txt` |
| Suite (`record_test_run.py`) | **2239 passed**, 0 failed, 0 errors, 0 skipped | `bb37715` (run at `dca4536`) | `evidence/TEST-RUN-PROVENANCE.txt`; `run_binding.py`: `bound` |

**The suite count.** 2236 at the first full run of step 4. Then:
- +1 for the queue test of §7.1;
- +2 for `test_mutation_tools.py`'s import-safety tests of the new script,
  which did not yet exist at the first run.

**STOP GATE D is not regenerated.** Its `--check` reports the same three
problems as after step 3: the writers of `match_reviews` and
`opportunities`, and staleness. Nothing new.

## 9. Limits that are part of these results

- **Sharing is a SQL fixture in these tests:** NEW → SHARED with
  `shared_at`, the edge `0006` admits. The share operation, with its
  checks (G5-8), is step 5's.
- **The corrected area and type are SQL fixtures,** as an operator's
  correction would land.
- **The queue is not paged:** the whole queue, as the Slice 3 queues. The
  opportunity queue is step 5's.
- **Carried, unchanged:**
  - L-S5-3a and L-S5-3b (step 6);
  - K06 UNPROVEN (EN-02);
  - G4-5R and G5-10 open.
- **These results are ours.** No independent run exists.

## 10. What remains

- **Step 4 closes on review.**
- **Step 5:** revalidate, share (G5-8), close (G5-10, open), the
  opportunity queue (G5-11 (a)) and the B10 service guard. It needs G5-10.
