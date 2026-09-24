# Slice 3 · step 8 — the authorization matrix, and STOP GATE C

**Basis.**
- `docs/gate/SLICE_3_PLAN.md`: §5.1 (the RFC-001 scenarios, "each is a
  test, named for its scenario"); §6 (STOP GATE C: six questions, each with
  named tests); §6.1 (the seven mandatory tests); §6.3 (concurrency); §7
  (the twelve acceptance conditions).
- RFC-001 §4 and its scenario matrix.

**The evidence is generated, not written.**
- `docs/gate/SLICE_3_STOP_GATE_C.md` is produced by
  `db/gate/stop_gate_c_evidence.py` from the JUnit report of the clean-tree
  run (`docs/gate/evidence/junit-run.xml`), which
  `TEST-RUN-PROVENANCE.txt` binds to its commit and source fingerprint.
- Any other report is labelled UNBOUND, and `--check` fails on it.
- `--check` also fails on a mapped test that is missing without a documented
  exception, or that did not pass, and on a stale document.
- The authorization matrix (`AUTHORIZATION_EVIDENCE_MATRIX.md`) now has 149
  rules: the scenario-named HTTP tests are added to the R4 rules they prove,
  with four new rows (§2).

## 1. Found by the generator: an operation step 1 never delivered

On its first run the generator reported
`plan operations without a route: ['getBackofficeQueuesProperties']`. Plan
§1.1 lists `GET /backoffice/queues/properties` (ADMIN, OPERATOR, REVIEWER).
Step 1 did not implement it, and no review caught it. **This omission is
ours.**

**Delivered now.** The contract declares only the name ("Properties requiring
review/reconfirmation") and the `QueuePage` shape. Developer Spec §19 defines
the queue: "Properties needing review | تعارض/نقص/إتاحة قديمة أو Identity
candidate". Three of those criteria are defined in data, and each is one
rule:

| Reason | Rule |
|---|---|
| `CLAIM_CONFLICT_FOUND` (تعارض) | a claim about the property has a verification event with outcome `CONFLICT_FOUND` |
| `IDENTITY_CANDIDATE_PENDING` (Identity candidate) | the property is in a candidate that is `PENDING_REVIEW` or `UNSURE` |
| `AVAILABILITY_NEEDS_CONFIRMATION` (إتاحة قديمة) | `current_availability = 'NEEDS_CONFIRMATION'`, the value the step-4 pass sets |

**Choices, stated for review.**
- **"نقص" (missing) is not implemented.** It names no required-field rule,
  and inventing one would be a decision.
- **One item per property.** `reason` is the first reason in the order above;
  `reasons` lists all of them (`QueueItem` is open,
  `additionalProperties: true`).
- **`priority` is `NORMAL`**, since no priority rule exists (the step-3
  precedent, Q-4).
- **`created_at` is the property's creation time.** Whether it should be the
  moment the item entered the queue is an open question.
- **An identity alias is not queued.** Writes to it are refused (F-2), so
  its work belongs to its canonical record.
- **No paging**, since the contract declares no parameters. This is the
  stance accepted for this slice's queues (review of 0a66f8e, Q-5 to Q-8).
  `next_cursor` is `null`.
- Staff only by `x-roles`, and audited once for the list (R6.3c).

**Tests:** `tests/test_slice3_property_queue.py`, 9 cases. Each criterion
ENTERS a property that was not queued before. The mutation script is
`db/dev/mutate_property_queue.py`: 8 mutations, each failing at least one
test (`STEP8-PROPERTY-QUEUE-MUTATIONS.txt`, clean tree at a558e4c).

**Q8 is killed by a crash, not by an assertion.** The mutation admits
properties with no reason. `review_queue_item` then indexes an empty
`reasons` list, and all 9 tests fail with `IndexError`. Four tests do assert
that a property is absent before it is given a reason
(`assert pid not in _queue(...)`). Those assertions are never reached under
Q8, so this run does not show that they would catch it.

**Observed, not changed:** `getBackofficeQueuesRequests` (an earlier slice)
returns an always-empty list, a placeholder. It is outside this slice and is
recorded here so it is not mistaken for a working queue.

## 2. The RFC-001 scenarios (§5.1)

Seven scenarios had no test named for them. They are now tests over HTTP
(`GET /me/properties/{id}`) in `tests/test_slice3_scenarios.py`: S11, S15,
S16, S16a, S16b, S16i, and S16j (INVITED and SUSPENDED). The rules were
already proven at loader level; these tests prove them at the API.

PROPERTY claim eligibility is still undecided (G3-2), so the claim rows are
inserted as fixture. The tests prove what a claim grants, not that a claim
flow exists.

**The authorization matrix** now cites these tests and S10–S16h under the
R4 rules they prove. It also has four new rows:
- R4.7 / S16;
- the public list's unauthenticated read (R10.4);
- the public list's missing per-request audit (R6.3);
- the Identity Lite maker-checker split.

### Finding G3-15 — S16i / S16j: 401 or 404

RFC-001's scenario table (lines 605–606) expects **404** for a claimant
whose account is DISABLED, INVITED or SUSPENDED. Since Slice 1, the
implementation refuses such an account at **authentication**, with **401**:
`resolve_subject` admits only ACTIVATED accounts (R4.11a). RFC-001's own
pipeline says "1. Authenticate → 401 if the bearer token is absent or
invalid". **The RFC contradicts itself.** The tests assert the behavior that
exists:
- the request is denied;
- no property data is returned;
- the 401 is identical for the claimed property and for a property id that
  does not exist, so it is not an existence oracle.

**Options:**
- (a) keep 401, and amend the scenario table's expectation;
- (b) resolve non-ACTIVATED accounts to a subject with no authority, and
  answer 404 per resource.

**Recommendation: (a).** It follows the RFC's pipeline, and leaks nothing.
Not changed without a decision.

## 3. STOP GATE C (§6)

Every named test of the six questions exists and passes, except two. Those
two are recorded as **documented exceptions**, which the generator enforces:
it lists them, shows the tests that answer each question instead, and fails
if those tests do not pass.

| Planned test | Why it cannot be written | Answered instead by |
|---|---|---|
| `test_listing_a_property_returns_all_of_its_offers` | **Finding G3-16:** the frozen contract declares no operation that lists a property's offers (`/properties/{property_id}/offers` has only POST) | `test_owner_sale_broker_sale_and_rent_coexist_on_one_property` (data level); `test_only_active_consented_offers_are_projected` (the public subset) |
| `test_converting_a_lead_records_its_party_and_consent` | **Decision G3-10:** conversion is refused until its schema is decided | `test_conversion_is_refused_with_a_typed_409_and_changes_nothing` |

**Finding G3-16.** "What offers exist for it?" has no staff-facing answer
through the API: offers are read one by one. If back-office staff need the
list, it is a contract addition (a Delta), not an implementation choice. This
is recorded here, and not added.

The three STOP GATE C tests that could be written and did not exist are in
`tests/test_slice3_stop_gate_c.py`:
- `…created_with_its_type_location_and_supply_mode`;
- `…property_attributes_are_unique_per_definition`;
- `…a_source_is_created_only_through_an_external_lead`, which also proves,
  structurally, that exactly one statement in `src/` inserts into
  `turab.sources`.

## 4. The acceptance conditions (§7)

| # | Condition | Evidence |
|---|---|---|
| 1 | every §1 operation implemented, or refusing with a typed error | computed in the STOP GATE C document: every operation the plan names has a route (after §1 above). Conversion refuses with a typed 409 (G3-10); PROPERTY claims refuse (G3-2) |
| 2 | the seven mandatory tests pass, each shown to fail against its defect | STOP GATE C document §2; each step's mutation evidence. Test 7 is **narrowed** (plan §6.4) |
| 3 | STOP GATE C answerable on all six questions | STOP GATE C document §1, with two documented exceptions (§3 above) |
| 4 | no new table, column or migration, and no new reason-code category, or an explicit finding | no table, column or reason-code category was added in Slice 3. Two structural migrations were: `0003` (G3-7, the relation currency in the consent gate, approved) and `0004` (the G3-6 overlap guard, approved with the Delta). New problem codes are not reason codes |
| 5 | matrix at 0 UNPROVEN; gate 8/8 | `AUTHORIZATION_EVIDENCE_MATRIX.md`; `evidence/gate-run.txt` |
| 6 | Matching not started; no `match_candidates` row written by any path | computed: no file in `src/` inserts into `match_candidates`. The rows in the corrective-effect tests are fixtures, as plan §6.4 states |
| 7 | PROPERTY claim eligibility undecided; no side-effect authority link | `test_property_claiming_fails_closed`; only `services/claims.py` inserts `record_claim_events` |
| 8, 10 | relations | amended by the approved G3-6 Delta: relations are delivered through their own operations |
| 9 | relations never read as an authorization source | `test_authorization_sql_never_reads_party_property_relations` |
| 11 | no winner-and-loser outcome without a **declared compare-and-set** | **stated for review, below** |
| 12 | run provenance and document digests | `TEST-RUN-PROVENANCE.txt`, `gate-run.txt`, `DOCUMENT-HASHES.txt` |

**Condition 11, stated precisely.** Three concurrency tests assert a winner
and a loser:

| Test | What makes the loser |
|---|---|
| offer transitions | a declared CAS predicate, `AND status = :expected` |
| two reviews of one identity candidate (step 7) | the declared rule "a final decision is not reviewed again", checked after `FOR UPDATE` on the candidate |
| two reviews building an alias chain (step 7) | the ADR-03 structure check, made after `FOR UPDATE` on both properties |

The second and third have no CAS predicate in the UPDATE. Step 7 removed one
as redundant: a locking read that waited returns the newest committed row, so
the rule is checked against the winner's result. The loser is backed by a
declared rule under a serialising lock, not by a predicate. Whether that
satisfies condition 11 as written is for review.

## 5. Also corrected in this step (review of e72432b)

Two comments said generation "locks no parent row", in `services/identity.py`
and the pair-race test. They are corrected: generation locks every property
it may pair, `FOR SHARE`. Those locks are compatible between two generators
(§13.3.2), so what decides a pair race between generators is the pair index.

## 6. What remains for Slice 3 to close

- A review of this evidence.
- Decisions on **G3-15** (401 or 404) and **G3-16** (a staff list of a
  property's offers, as a Delta or not).
- Whether condition 11 is met as stated in §4.
