# Slice 4 — Deterministic Matching Core
## Implementation plan — **revision 13**

**Status:** submitted for review. **No code for this slice exists, and none
is written until this plan is approved.** Matching stayed closed through
Slices 0–3 by a standing limit. Opening it is the decision this plan asks
for.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | `75c7660` | first plan |
| 2 | `a1f77ea` | the plan's facts measured on PostgreSQL before any code (§0a). §3.3 is settled by measurement. G4-3, G4-7 and G4-14 are corrected by what was measured. G4-16 is added. **No decision is taken** |
| 3 | `0d6c6cf` | decisions recorded where they apply: **G4-1 and G4-14** (approved for step 1, 2026-09-26); **G4-2 and G4-13** (approved in the review of aad9f34), each with the conditions the review attached. Step 2 starts only after step 1 is closed |
| 4 | `20383df` | **G4-8 and G4-9** decided (review of 4538a2d), recorded where they apply. G4-13's canonical form is corrected by the same review: numbers are JSON numbers, exact and context-free; the format tag becomes `turab.match-input/2`. Step 3 starts only after step 2 is closed |
| 5 | `6396505` | **G4-17** raised (open): an ACTIVE offer on an alias cannot be evaluated. Found while building the candidate set; reported, not decided |
| 6 | `5ec9a84` | decisions recorded where they apply: **G4-17 (a)**, with narrowed wording; **G4-3 (b)**, **G4-4**, **G4-6**, **G4-7**; **G4-5 for SALE**. The **RENT price comparison is NOT approved**: no rent period is defined, so it is recorded as the open question G4-5R. Step 4 starts only after step 3 is closed |
| 7 | `3391c86` | **Step 3 CLOSED at `6b833fb`** (review of 6b833fb); step 4 authorised on G4-3, G4-4, G4-6, G4-7 and the SALE table of G4-5 only. §3.4 corrected: `match_criterion_results` has no `explanation` column. The property snapshot gains `location_ancestry` (format 2), so that G4-6 replays. G4-5R: the step-4 behaviour, a typed refusal, is stated for review. **G4-18** raised (open) |
| 8 | `1805eef` | Step 4 **not closed**: three defects fixed (a value no property can pass; a deferred row not validated; reason codes naming another importance). **Decided:** the G4-5R interim refusal (the period stays open); **G4-18 (b)**; **G4-10** as proposed, with PUBLIC_LISTING_ALLOWED; **G4-11** as proposed, with the permission reason kept visible. Step 4's §6 choices recorded. Step 5 starts only after step 4 is closed |
| 9 | `99ffbaf` | Step 4 **not closed**: the pre-check "no property value can pass" judged the option domain from the ACTIVE options, while the rule compares any held value. Unified on the rule's domain; the meaning of `active` is stated under G4-7. A limit is stated under G4-2: version 1 of three rules is registered and pinned, but not a proof of historical replay. **No new decision is taken** |
| 10 | `02b9898` | **Step 4 CLOSED at `3c4816c`**: the review of 3c4816c authorised step 5, which by §8 follows step 4's closure. Step 5 delivered on G4-10 and G4-11. G4-5R's period stays open, and its interim refusal stays in force. The G4-2 limit stands. Step 6 waits on **G4-12** |
| 11 | `bb55a67` | **Step 5 CLOSED at `a5ea6f5`** (review of a5ea6f5, which also confirmed step 4's closure as intended). **Decided:** pin the freshness and permission gates and the eligibility precedence before step 7 (done in step 6, under their own ids); **G4-12** with its edge cases; PERMISSION_MISSING displayed from its basis. G4-5R unchanged. **Raised (open):** the weight of the request's `budget_target_dzd` column, which G4-12's decision does not give |
| 12 | `7b09da3` | Step 6 **not closed** until applied: **the column target's weight decided, option (a)** (PREFERRED, weight 2, its own COLUMN term, never merged with a BUDGET_TARGET row). Applied as `score.soft@2` beside `@1`. Step 5's closure at `a5ea6f5` confirmed. G4-5R unchanged; step 7 waits on G4-15 |
| 13 | the commit that records the review of ee7fbc0 | **Step 6 CLOSED at `ee7fbc0`.** G4-15 detailed for decision, D1–D6, with the conditions that already bind step 7. **No decision is taken; no code changes** |

**Baseline:** Handoff v1.0.3 / technical pack v0.2.3, frozen.
**Authority for the scope:** `docs/handoff/06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md:171–206`.
**Predecessor:** Slice 3, closed at `96e36e6` within its approved exceptions
(`docs/gate/SLICE_3_CLOSURE.md`).

**Sources read for this plan.** Each rule below cites one of these:
- `IMPLEMENTATION_SLICES_v0.2.md` §Slice 4 (objective, deliverables, ten
  mandatory tests, STOP GATE D);
- Handoff Master v1.0.3 §5.2, §6.1, §6.2, §6.5, §7;
- `ARCHITECTURE_DECISIONS_v0.2.md` ADR-01, ADR-02, ADR-03, ADR-04, ADR-08,
  ADR-12;
- Developer Reference Spec v0.1 §12, §13, §14, §15, §16, §22.1, §23, §24
  (M-01 … M-12), §30;
- `API_CONTRACTS_v0.2.md` §4.8, §4.9, §6;
- `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` B03, B04, C01, C03, C04, D02, D05,
  E02, G01–G06, H02;
- `schema_v0.2.3.sql`:
  - `matching_policies` (638–649);
  - `match_candidates` (651–685);
  - `match_criterion_results` (687–707);
  - `match_reviews` (709–717);
  - `match_diagnostic_runs` (719–737);
  - `enforce_approved_review_gate` (855–873);
  - `enforce_match_commercial_context` (1170–1207);
  - the immutability triggers (1289–1295);
- `seed_master_data_v0.2.3.sql`:
  - `criterion_definitions` (118–131);
  - `reason_codes` (134–161);
  - the one seeded policy, `0.2.0` (164–185);
- the frozen OpenAPI: `postRequestsRequestIdMatchingRun`, `MatchCandidate`,
  `CriterionResult`, `Diagnostic`;
- RFC-001 §2.1, R6.3, R9.2, R9.3.

---

## 0. What this slice is, and what it is not

**Objective, as written:** "Produce explainable candidates with immutable
historical inputs." STOP GATE D asks one thing: "A human reviewer must be able
to read a candidate and reconstruct every eligibility decision without an
LLM."

**The boundary with Slices 5 and 6**, proposed in G4-15 for the reviewer to
confirm:

| In Slice 4 | Not in Slice 4 |
|---|---|
| running matching; writing `match_candidates`, `match_criterion_results` and one `match_diagnostic_runs` row per run | `match_reviews` (the human decision) and `opportunities` (**Slice 5**) |
| reading a match; reading the latest diagnostic | the review queue `getBackofficeQueuesMatches` (**Slice 5**) |
| the diagnostic's COUNTS and blocker summary | suggested actions, relaxation scenarios, and the tasks raised from unknowns (**Slice 6**) |
| `next_action`, stored on the match | creating a task from it (**Slice 6**) |

**Standing limits carried from Slice 3**, restated as acceptance conditions
in §7:
- relations are never an authorization source, nor a matching input;
- G3-2 stays open: PROPERTY claims fail closed;
- no path writes an opportunity or a match review;
- AI takes no part. `generated_by` is always `RULE_ENGINE` and `ai_trace_ref`
  is always null (ADR-12).

---

## 0a. What was measured before any code (revision 2)

`docs/gate/evidence/SLICE4-PLAN-MEASUREMENTS.txt` records the measurements:
- a scratch database built by `db/dev/reset_db.sh --fixtures`;
- tree `75c7660`, clean before and after the run;
- PostgreSQL 16.13;
- the harness, reproduced verbatim.

No matching code exists. The harness writes fixture rows into the match
tables to observe what the schema permits.

| § | Plan statement | Measured |
|---|---|---|
| A | G4-1: the contract default names no policy | **Confirmed:** default `0.1.0`; only `0.2.0` exists |
| B | G4-14: criterion results and diagnostic runs are unguarded | **Confirmed:** a FAIL became PASS; both rows were updated and deleted; the match row itself refused |
| C | G4-14: an immutable policy's `rules` can be edited | **Confirmed and wider:** its `version` could be changed too |
| D | §3.3: a unique conflict under Repeatable Read | **Measured:** 23505 for a plain INSERT, 40001 for `ON CONFLICT DO NOTHING`, and the winner's row is invisible in the same transaction. Under Repeatable Read, the commercial-context trigger checks the snapshot's offer version (D7). Across two transactions it fails when the offer changed between them (D8) |
| E | G4-3 / G4-7: Slice 2 accepts duplicate and unevaluable criteria | **Confirmed and wider:** a REQUIRED row contradicting the request's own column was accepted, and so was a LOCATION naming no location |

---

## 1. Operations in scope — three

All three are declared in the frozen contract and are staff-only by their
`x-roles`.

| operationId | Method · Path | Roles | Slice |
|---|---|---|---|
| `postRequestsRequestIdMatchingRun` | POST `/requests/{id}/matching/run` | ADMIN, OPERATOR, REVIEWER | 4 |
| `getMatchesMatchId` | GET `/matches/{id}` | ADMIN, OPERATOR, REVIEWER | 4 |
| `getRequestsRequestIdDiagnostic` | GET `/requests/{id}/diagnostic` | ADMIN, OPERATOR, REVIEWER | 4 (counts only; G4-15) |
| `postMatchesMatchIdReview` | POST `/matches/{id}/review` | ADMIN, REVIEWER | **5** |
| `getBackofficeQueuesMatches` | GET `/backoffice/queues/matches` | ADMIN, OPERATOR, REVIEWER | **5** |

- **No customer path.** No `/me/matches` operation exists. Snapshots and
  seller expectation never leave staff DTOs (R9.2, R9.3).
- **No new operation.** One contract correction is proposed (G4-1), and it
  only narrows.

---

## 2. The engine, as the sources define it

**The evaluation order is fixed by `API_CONTRACTS` §4.8.**
1. transaction compatibility and the hard gates;
2. REQUIRED criteria, each PASS, FAIL or UNKNOWN;
3. actionable-unknown classification;
4. request freshness;
5. property freshness;
6. offer freshness;
7. permission scope;
8. soft ranking among eligible candidates;
9. the diagnostic's next action.

**What each match stores** (ADR-02, `API_CONTRACTS` §6):
- five immutable snapshots: request, property, commercial context,
  permission, freshness;
- `input_hash`;
- the policy id and version;
- one row per criterion, each carrying:
  - importance;
  - both values;
  - PASS, FAIL or UNKNOWN;
  - `blocking`;
  - `delta`;
  - the evidence level and the claim it rests on;
  - a reason code;
  - `rule_id` and `rule_version`.

**What the schema already enforces.** These are the backstops. The plan
proves each one by a schema-labelled test, and does not re-implement it:
- `trg_match_commercial_context` enforces all of the following:
  - the policy id matches its version;
  - no match targets an alias (E02);
  - the evaluated offer belongs to the property;
  - **BUY evaluates only SALE and RENT evaluates only RENT** (C01,
    mandatory test 1);
  - `offer_version` equals the offer's version;
  - a non-POTENTIAL property requires an offer.
- `prevent_match_candidate_update`: a match row is never updated or deleted
  (mandatory test 8, in part; see G4-14).
- `enforce_approved_review_gate`: a review cannot be APPROVED unless all
  four gates are PASS and eligibility is ELIGIBLE (H02; mandatory test 2
  at the schema level).
- `UNIQUE(request_id, property_id, matching_policy_id, input_hash)`.

**What the schema does NOT define is most of the engine.** The seeded policy
`0.2.0` holds the following, and nothing else:
- the hard-gate mapping: required unknown → NEED_MORE_INFORMATION; confirmed
  fail → REJECTED;
- the freshness thresholds: 30, 30 and 14 days;
- `automatic_request_relaxation: false`;
- `human_review_required_for_opportunity: true`.

It defines no rule for any criterion, no soft-score function, and no
permission rule. Each of those is a decision, listed in §4. **None is taken
by this plan.** Each has a recommendation, and the step it blocks is named
in §8.

---

## 3. Rules that follow from the sources without a decision

### 3.1 Canonical only, and no destructive change
- Only canonical properties are candidates (ADR-03, E02). A property that
  `property_identity_aliases` lists as an alias is excluded (the table that
  `auth/loaders.resolve_canonical_property` reads), and the trigger is the
  backstop.
- Matching writes only to the three match tables and to `audit_log`. It
  changes no request, property, offer, consent or criterion. A test asserts
  this with row digests taken before and after a run.
- `automatic_request_relaxation` is read, and the run **refuses** unless it
  is `false`. The same holds if `human_review_required_for_opportunity` is
  not `true`. A policy this code does not implement fails closed, as
  NoActiveFreshnessPolicy does today.

### 3.2 PASS, FAIL and UNKNOWN never collapse
- A REQUIRED criterion that is UNKNOWN never becomes PASS or FAIL (§12.1,
  C03, mandatory test 3). It makes the candidate NEED_MORE_INFORMATION.
- A soft score never overrides a hard FAIL or UNKNOWN (§4.8, §12.1). It is
  computed only for candidates whose hard gate is PASS; for all others it is
  `null` (mandatory deliverable "soft ranking only after hard eligibility").
- No candidate is a valid result (G06, mandatory test 10). An empty run
  returns `matches: []` with a diagnostic, and it is not an error.

### 3.3 One snapshot of the world per run
**The problem.** The engine reads the request, its criteria, properties,
offers, resolved attributes, consent bindings and the policy. Under Read
Committed, each statement sees its own snapshot (PostgreSQL 16 documentation,
§13.2.1). Step 6 of Slice 3 found exactly this defect in the public list.

**The proposal.** The run reads everything in a `REPEATABLE READ`
transaction, whose statements all see the snapshot taken at its first
statement (§13.2.2).

**Measured (revision 2; evidence §D).** Two designs were compared.

- **(i) Evaluate under Repeatable Read, then insert in a second, Read
  Committed transaction. REJECTED by measurement.**
  - Case D8: when the offer changed between the two transactions, the
    insert fails P0001 in `trg_match_commercial_context`.
  - Under that design, every change racing a run becomes a failed run.
- **(ii) Everything in ONE Repeatable Read transaction. RECOMMENDED.**
  - Case D7: the trigger reads the transaction's snapshot, so the insert
    matches what was evaluated, even when the offer changed after the
    snapshot. That is ADR-02's point: the match records what the engine
    read.
  - Each match is inserted with a plain `INSERT` under its own SAVEPOINT.
  - A 23505 means an identical-input match already exists (G4-13). The
    savepoint is rolled back and the run continues.
  - Once the run commits, the existing row is read in a NEW transaction,
    because it is invisible in the run's snapshot (case D5).
  - `ON CONFLICT DO NOTHING` is **not** used inside Repeatable Read: it
    fails 40001 (cases D2 and D4), which would need a retry loop.

The concurrency test (§6.3) asserts exactly these outcomes, with the witness
pattern of Slice 3.

### 3.4 Evidence on each criterion
- For an attribute criterion (DOCUMENT_TYPE, RIGHT_TYPE, ROOMS, BEDROOMS),
  the evidence is:
  - `evidence_claim_id`: the claim behind the current resolved value
    (`property_attributes.resolved_claim_id`);
  - `evidence_level`: that claim's `effective_verification_level`.
- For a projection column (type, location, areas, price), there is no
  claim link, so both fields are `null`. The result's explanation states
  this (`"evidence": "NO_CLAIM_LINK"`), so a `null` is never ambiguous (§30,
  "no ambiguous null semantics").
- **Corrected in revision 7.** Revisions 1–6 said "the criterion row states
  this in `explanation`". `match_criterion_results` has **no** `explanation`
  column (`schema_v0.2.3.sql:687–706`); only `match_candidates` has one
  (line 677). Step 4 carries each result's explanation beside the row's
  fields. Where it is stored, `match_candidates.explanation` keyed by
  (code, ordinal), is proposed with step 7. No column is added.

### 3.5 Staff DTO only
- `getMatchesMatchId` returns `MatchCandidate` with its snapshots and is
  staff-only.
- The commercial snapshot contains `seller_expectation_dzd` (R9.3: the
  engine may read it).
- A DTO test asserts that no customer or public schema can carry any match
  field (R9.2). No customer route exists.
- `explanation` never states the expectation, nor anything from which it
  can be inferred (R9.3, S36). This is proved by a test over every
  `reason_code` and text the engine can emit.

### 3.6 Audit
- `match_candidates`, `match_criterion_results` and `match_diagnostic_runs`
  carry no audit trigger in the schema. The service writes their audit rows
  in the same transaction (`services/audit_rows`, the step-7 precedent).
- Reads are access-audited per request (R6.3).

---

## 4. Decisions needed — none is taken by this plan

**Summary.** Each line below is detailed in its subsection. A reply may
accept a recommendation by number.

| # | Question | Recommendation | Blocks |
|---|---|---|---|
| G4-1 | The policy version, when the contract default names no policy | **APPROVED** (2026-09-26): CORRECTION-004 | step 1 |
| G4-2 | Where rules live | **APPROVED, (a)** (review of aad9f34): a code registry, with old versions kept replayable | step 2 |
| G4-3 | Criterion rows duplicating the request's columns | **APPROVED (b)** (review of cc3a7fe): typed refusal on a provable REQUIRED contradiction; otherwise both are evaluated | step 4 |
| G4-4 | When an UNKNOWN blocks | **APPROVED** (review of cc3a7fe): REQUIRED always; `blocking_if_unknown` adds blocking to others | step 4 |
| G4-5 | Price | **APPROVED for SALE** (review of cc3a7fe), `seller_expectation_dzd` internal. **RENT: not approved**, see G4-5R | step 4 |
| G4-5R | RENT price: the period of `budget_max_dzd` and of a RENT `asking_price_dzd` | **Period open.** No numeric PASS or FAIL for RENT until it is defined. **Interim behaviour APPROVED** (review of f789a59): a RENT run is refused, naming G4-5R, with or without a budget | step 4 (RENT price only) |
| G4-6 | Location | **APPROVED** (review of cc3a7fe): subtree, as G3-14 | step 4 |
| G4-7 | Criteria that cannot be evaluated | **APPROVED** (review of cc3a7fe): a typed refusal if the input is invalid, or REQUIRED and unevaluable; otherwise UNKNOWN, not blocking | step 4 |
| G4-8 | The candidate set | **APPROVED** (review of 4538a2d), as proposed: one match per qualifying offer; excluded ids reported in the diagnostic | step 3 |
| G4-9 | POTENTIAL without an offer | **APPROVED, (a)** (review of 4538a2d): not evaluated, the reason reported; mandatory test 6 narrowed to its refusal | step 3 |
| G4-10 | Permission | **APPROVED as proposed** (review of f789a59); a valid PUBLIC_LISTING_ALLOWED binding counts for internal matching of the same bound resource, and grants no new sharing | step 5 |
| G4-11 | Freshness mapping and eligibility precedence | **APPROVED as proposed** (review of f789a59); a missing or revoked permission stays visible in the diagnostic, even under NEEDS_CONFIRMATION | step 5 |
| G4-12 | Soft score | **APPROVED** (review of a5ea6f5), with its edge cases; the `budget_target_dzd` COLUMN weighs 2, as PREFERRED (review of 0cf6a7a, option (a)) | step 6 |
| G4-13 | Input hash; an identical re-run | **APPROVED** (review of aad9f34): canonical JSON; the existing match is returned; `evaluated_offer_id` is named in the input | step 2 |
| G4-14 | Migration `0005` (immutability) | **APPROVED** (2026-09-26), delivered in step 1 | step 1 |
| G4-15 | The boundary with Slices 5 and 6; "near match" | As §0; one REQUIRED FAIL | step 7 |
| G4-16 | Tightening Slice 2's criterion entry | Not now; refuse at run time instead | — |
| G4-17 | An ACTIVE offer on an alias (raised in step 3) | **APPROVED (a)** (review of cc3a7fe): kept and reported; nothing moved or re-linked | — |
| G4-18 | A count criterion on a type the attribute cannot apply to (raised in step 4) | **APPROVED (b)** (review of f789a59): FAIL when the attribute cannot apply; UNKNOWN when it applies and is not recorded; `count_min@2` beside version 1 | step 4 |

Each item has options and a recommendation. **Blocks** names the step in §8
that cannot start without it.

### G4-1 · The policy version: the contract default names a policy that does not exist
- **Facts:**
  - `openapi_v0.2.3.yaml:1347` sets `matching_policy_version` to default to
    `0.1.0`.
  - The seed creates only `0.2.0`, which is active.
  - The Developer Spec's example (§22.1) also says `0.1.0`.
  - So a call that omits the field names a missing policy.
- **Options:**
  - (a) Contract correction CORRECTION-004, through the overlay, which only
    narrows. The field becomes required and must equal the ACTIVE policy's
    version. Anything else gets a typed 422, as the step-7 treatment of
    `algorithm_version` does.
  - (b) Seed a `0.1.0` policy. This is a data change, and it invents a
    policy nobody approved.
  - (c) Map an omitted field to the active policy. This changes the default
    rather than narrowing it, so the overlay cannot express it.
- **Recommendation: (a).** Running under an inactive policy is also refused:
  one active policy is the only defined one (`ux_matching_policy_one_active`).
- **Blocks:** step 1.

> **DECIDED (2026-09-26, approved for step 1), and delivered:** CORRECTION-004 (`docs/contract/CORRECTION-004-matching-policy-version.md`). The review of aad9f34 found that a second narrowing of the same operation could silently undo it; that is now refused (`docs/gate/SLICE_4_STEP1_DELIVERY.md` §6).

### G4-2 · Where criterion rules live, and how a change is versioned
- **Facts:**
  - Every criterion result needs a `rule_id` and a `rule_version`.
  - Policy `0.2.0` names no rule.
  - Spec §30 requires that any rule change goes through the Design Ledger
    or a versioned policy, "not silently in code".
- **Options:**
  - (a) A rule registry in code. Each rule has an id, a version and a
    function. A test pins a digest of the registry (ids, versions and each
    rule's source text), so a code change without a version bump fails CI.
    The registry is listed in the plan and in the Design Ledger.
  - (b) A new policy row `0.3.0` whose `rules` list the rule ids and
    versions. This is a data change, and the new policy would be activated
    in place of `0.2.0`.
- **Recommendation: (a)** now, recorded against policy `0.2.0`, with (b)
  when the pilot tunes thresholds.
- **Blocks:** step 2.

> **DECIDED (review of aad9f34): option (a)**, with one condition.
> - The registry holds rules by id, version and digest.
> - **Every version that any stored match cites stays implemented and
>   replayable.** Raising a rule's version and deleting the previous
>   implementation does not achieve replay.
> - So the registry is keyed by `(rule_id, rule_version)`, and a new version
>   is ADDED beside the old one.
> - The digest pin covers every version. A test asserts that every
>   `(rule_id, rule_version)` pair ever recorded in the pin still resolves
>   to its implementation.
> - Removing a version is refused unless no match cites it, and even then
>   it needs a Design Ledger entry.
>
> **Extended in revision 11 (review of a5ea6f5): the gates are pinned too.**
> - The freshness and permission gates, the two state derivations and the
>   eligibility precedence are registered under their own ids
>   (`freshness.*`, `permission.*`, `eligibility.*`), as is the soft score
>   (`score.soft`). They are not criterion rules.
> - They are pinned, and `REGISTRY.digest()`, which is an input of the hash,
>   covers them.
> - A changed one is a new version beside the old.
> - The snapshots record the derivation they used (`derived_by`), and
>   eligibility records its versions (`engine`), for step 7 to store.
>
> **A limit, stated in revision 9 (review of ba5f25e):** registered and
> pinned does not mean replayable today.
> - `location@1`, `attribute_option@1` and `area_min@1` emit reason codes
>   that the step-4 backstop now refuses at the wrong importance.
> - No stored match cites any version 1: no match row exists before step 7,
>   and `criteria.RULES` selects version 2.
> - Their presence in the registry must therefore NOT be offered, at step 7
>   or step 8, as evidence of historical replay. A replay proof covers only
>   the versions stored matches actually cite.

### G4-3 · Which data each criterion reads, and duplicate request criteria
**The mapping proposed** (codes from the seed, lines 118–131; every rule
version is `1`):

| Criterion | Request side | Property / commercial side | Rule |
|---|---|---|---|
| TRANSACTION_INTENT | `requests.transaction_intent` | `offer.transaction_type` | structural: a mismatched offer is never evaluated (the trigger forbids it) |
| PROPERTY_TYPE | `desired_property_type` + `property_type_importance`, or a criterion row | `properties.property_type` | EQ / IN / NEQ / NOT_IN |
| LOCATION | `primary_location_id` + `location_importance`, or a row | `canonical_location_id` | G4-6 |
| BUDGET_MAX | `budget_max_dzd` + `budget_importance`, or a row | the offer's price context | G4-5 |
| BUDGET_TARGET | `budget_target_dzd` | the offer's price | soft only (G4-12) |
| LAND_AREA_MIN / BUILT_AREA_MIN | criterion row, GTE | `land_area_m2` / `built_area_m2` | null gives UNKNOWN |
| ROOMS_MIN / BEDROOMS_MIN | criterion row, GTE | attribute ROOMS / BEDROOMS | null gives UNKNOWN |
| DOCUMENT_TYPE / RIGHT_TYPE | criterion row, EQ / IN / NOT_IN | attribute of the same code, controlled options | null gives UNKNOWN (DOCUMENT_NOT_KNOWN) |
| CUSTOM_ATTRIBUTE | criterion row | — | G4-7 |

- **The duplication.** A request carries type, location and budget as
  COLUMNS. Slice 2 also accepts criterion ROWS with the same codes:
  `requests.add_criterion` admits every ACTIVE code in
  `criterion_definitions`, and these codes are active. **Measured (evidence
  §E):** on a request whose column says `HOUSE_VILLA`, a REQUIRED row
  `PROPERTY_TYPE EQ "APARTMENT"` was accepted (201).
- **The consequence measurement exposed.** Under "evaluate both", that
  request rejects every candidate, because no property is both types. The
  diagnostic would read "no match", which hides a data-entry contradiction.
- **Options:**
  - (a) Evaluate both. The diagnostic's `blocker_summary` names the
    criterion row behind each FAIL, so the contradiction is visible.
  - (b) Refuse the run with a typed 422 when a REQUIRED row and a REQUIRED
    column on the same code are DISJOINT (EQ or IN sets that do not
    intersect).
  - (c) Adopt one as authoritative. That invents a precedence.
- **Recommendation: (b)**, with (a) for every case that is not provably
  disjoint. A numeric row stricter than the column, such as
  `BUDGET_MAX LTE 20000000` against a column of 25,000,000, is not a
  contradiction. It is evaluated, and the stricter bound prevails.
- **Blocks:** step 4.

> **DECIDED (review of cc3a7fe): (b).**
> - A **provable contradiction** between a REQUIRED column and a REQUIRED
>   criterion row on the same code (disjoint EQ/IN sets) refuses the run
>   with a typed refusal.
> - In every other case, both are evaluated, and the stricter one prevails.

### G4-4 · When is an UNKNOWN blocking?
- **Facts:**
  - `request_criteria.blocking_if_unknown` defaults to `false`.
  - Yet mandatory test 3 and C03 say a REQUIRED unknown yields
    NEED_MORE_INFORMATION, with no condition.
- **Recommendation:**
  - A REQUIRED UNKNOWN is always blocking.
  - `blocking_if_unknown = true` makes a PREFERRED or FLEXIBLE unknown
    blocking too.
  - This reads the column as a way to widen blocking, never to narrow it.
    The alternative, a REQUIRED unknown that does not block, would
    contradict mandatory test 3.
- **Blocks:** step 4.

> **DECIDED (review of cc3a7fe):**
> - A REQUIRED criterion that is UNKNOWN is always blocking.
> - `blocking_if_unknown = true` ADDS blocking to a PREFERRED or FLEXIBLE
>   criterion.

### G4-5 · Price compatibility (M-03, M-04, G02, mandatory tests 4 and 5)
**The proposal.** `max` is the buyer's `budget_max_dzd`. `ask` is
`asking_price_dzd`. `exp` is `seller_expectation_dzd`, which exists for SALE
only (CHECK constraint).

| Case | Result | Reason code |
|---|---|---|
| `max` is null | UNKNOWN; not blocking unless the importance is REQUIRED (G4-4) | — |
| `ask` is null | UNKNOWN | PRICE_NOT_KNOWN |
| `ask ≤ max` | PASS | — |
| `ask > max` and `exp ≤ max` (SALE) | PASS, internally. The expectation is recorded in the snapshot and **never** in the explanation (mandatory test 5, R9.3) | — |
| `ask > max`, `price_negotiable = YES`, and no `exp ≤ max` | UNKNOWN (mandatory test 4, G02) | PRICE_NEGOTIATION_UNCONFIRMED |
| `ask > max`, `price_negotiable = NO`, and no `exp ≤ max` | FAIL | BUDGET_EXCEEDED |
| `ask > max`, `price_negotiable = UNKNOWN`, and no `exp ≤ max` | **decision:** UNKNOWN (negotiability not confirmed) or FAIL. **Recommendation: UNKNOWN**; the schema's default is UNKNOWN, so FAIL would reject most listings on a missing fact | PRICE_NEGOTIATION_UNCONFIRMED |

**Two further questions:**
- **The RENT budget:** is `budget_max_dzd` monthly for a RENT request? No
  source says so. **Recommendation:** treat it as the same unit as the RENT
  offer's `asking_price_dzd`, and state this in the snapshot, until a unit
  is decided. **NOT APPROVED (review of cc3a7fe)**, see the decision below.
- **`budget_flexibility`** (STRICT … HIGH): no source gives it a numeric
  effect. **Recommendation:** it is not used by the hard gate. It is
  recorded in the request snapshot.

**Blocks:** step 4.

> **DECIDED (review of cc3a7fe): the SALE table is approved, with
> `seller_expectation_dzd` kept internal.**
>
> **RENT is NOT approved: G4-5R, open.** The contract names both
> `budget_max_dzd` and a RENT offer's `asking_price_dzd` in dinars, and
> names no rental period for either. A common time unit cannot be
> confirmed. So no numeric comparison of a RENT price may be PASS or FAIL
> until the period is defined.
>
> The step-4 behaviour for a RENT price criterion is itself a choice. It is
> proposed with step 4, and it may not be a numeric verdict.
>
> **Step 4 (revision 7), stated for review:** a RENT request is REFUSED
> with a typed refusal naming G4-5R, with or without a budget (acceptance
> condition 1: anything undecided refuses, naming the rule). No RENT match
> can therefore be produced until G4-5R is decided. The alternative, "RENT
> price always UNKNOWN", is not a numeric verdict either. It would let RENT
> requests run, and every REQUIRED budget would then block. Choosing it is
> the reviewer's.
>
> **A source fact for G4-5R, not a decision:** red-team D01 describes "RENT
> 70k/month" for an offer. It states a period for that example offer only.
> It says nothing about `budget_max_dzd`.
>
> **DECIDED (review of f789a59): the interim refusal is accepted.** A RENT
> run is refused, naming G4-5R, whether a budget is given or not. This is a
> decision on interim behaviour only. The price period itself is still
> undecided, so no RENT match is produced before it is.

### G4-6 · Location
- **Recommendation:** the property's location is inside the requested
  location's subtree gives PASS. This follows G3-14, approved for the public
  list, and uses the same recursive query with UNION.
- A null `canonical_location_id` gives UNKNOWN.
- **Blocks:** step 4.

> **DECIDED (review of cc3a7fe):** the subtree rule, as G3-14.

### G4-7 · Criteria the deterministic engine cannot evaluate
- **Facts:**
  - `TEXT_SEMANTIC` and `CUSTOM_ATTRIBUTE` have no deterministic rule
    (§12.3: semantics may discover, never decide).
  - Slice 2 validates a criterion's code, not whether its operator suits
    that code, nor whether its value names something that exists.
    **Measured (evidence §E):** `BUDGET_MAX IN ["a","b"]` and a `LOCATION`
    naming a random uuid were both accepted (201).
- **Options:**
  - (a) The run is refused with a typed 422 naming the unsupported
    (code, operator) pair.
  - (b) UNKNOWN. If the criterion is REQUIRED, every candidate becomes
    NEED_MORE_INFORMATION for good.
  - (c) Skipped. This is a silent PASS, and it is excluded by §3.2.
- **Recommendation:**
  - (a) for any REQUIRED criterion, for an operator that does not suit its
    code, and for a value no rule can read (a location id that is no
    location, a non-numeric bound);
  - for a PREFERRED or FLEXIBLE `TEXT_SEMANTIC` or `CUSTOM_ATTRIBUTE`:
    UNKNOWN, not blocking, with no soft-score weight, recorded so a
    reviewer sees it.
- **Blocks:** step 4.

> **DECIDED (review of cc3a7fe):** as proposed.
> - A PREFERRED or FLEXIBLE criterion with no deterministic rule is
>   recorded UNKNOWN, not blocking.
> - An invalid input, or a REQUIRED criterion that cannot be evaluated, is
>   refused with a typed refusal.
>
> **What "no property value can pass" means, stated in revision 9 (review
> of ba5f25e).** The pre-check judges the domain the RULE compares, not
> the vocabulary active today.
> - **`attribute_options.active` governs what may be NEWLY recorded or
>   requested**:
>   - the Slice 3 validator writes only active options
>     (`truth.validate_attribute`);
>   - a request may name only active options.
> - **A value already recorded keeps its meaning after its option is
>   retired.** The schema allows it:
>   - `property_attributes.value` is `jsonb` and references no option;
>   - no table references an option row, so an option can be deactivated,
>     or deleted, while properties keep its value.
>
>   The rule compares such a value like any other.
> - **The option domain is therefore open.** An EQ/IN option criterion is
>   refused exactly when every value is a not-known option. A NEQ/NOT_IN
>   option criterion is never refused, because a retired value may satisfy
>   it.
> - **Enum codes are closed domains** (PostgreSQL enums of the frozen
>   schema). A set leaving no member is refused.
> - **The path not taken:** treating a retired option as UNKNOWN in the rule
>   would turn a recorded fact into a blocking unknown when an entry
>   vocabulary changes. It would also need the activity state in every
>   property snapshot, and a new rule version.

### G4-8 · The candidate set
- **Request status.** **Recommendation:** run for `ACTIVE` and
  `NEEDS_CONFIRMATION`; every other status gets a typed 409. A stale
  request is evaluated, and its freshness gate carries the staleness (M-06).
- **Offers:** only offers that are `ACTIVE` and of the matching transaction
  type. DRAFT, PENDING_INFO, PAUSED, WITHDRAWN and CLOSED offers are not
  evaluated.
- **Availability.** `UNAVAILABLE` excludes the property. Every other value
  is evaluated, and `NEEDS_CONFIRMATION`, `UNKNOWN` or a stale confirmation
  lead to NEEDS_CONFIRMATION (M-05).
- **Several qualifying offers on one property.** **Recommendation:** one
  match per (property, offer). Each has its own commercial snapshot and
  hash, as ADR-01 requires ("the same physical property may have multiple
  SALE offers … different prices"). Opportunity uniqueness per
  REQUEST × PROPERTY is Slice 5's to enforce (ADR-01, H04).
- **`property_ids` in the body** narrows the set. A listed id that is an
  alias, missing, or excluded by a rule above is reported in the diagnostic,
  never evaluated silently.
- **Blocks:** step 3.

> **DECIDED (review of 4538a2d):** the candidate set as proposed above.
> - Requests in `ACTIVE` or `NEEDS_CONFIRMATION` are run; any other status
>   gets a typed 409.
> - Offers are `ACTIVE` and of the matching transaction type.
> - `UNAVAILABLE` excludes the property.
> - **One independent match per qualifying offer** of the same property.
> - **Excluded ids are reported in the diagnostic.**
>
> Recording this decision does not close step 2.

### G4-9 · A POTENTIAL property without an offer: no willingness data exists
- **Facts:**
  - Mandatory test 6 and D05 allow evaluating it "only when structured
    willingness context exists".
  - The frozen schema has no table or column for willingness data.
    `grep -i willing` finds nothing in the schema or the OpenAPI.
- **Options:**
  - (a) Such a property is **not evaluated**, and the diagnostic reports it.
    Mandatory test 6 is then proven in its refusing half only, NARROWED as
    Slice 3 narrowed its test 7.
  - (b) A willingness contract as a Delta: a table or claims, and an
    operation.
- **Recommendation: (a)** in this slice.
- **Blocks:** step 3.


> **DECIDED (review of 4538a2d): option (a) for this slice.**
> - A POTENTIAL property with no offer, and no structured willingness
>   context, is **not evaluated**.
> - The reason for its exclusion is reported in the diagnostic.
> - The test for mandatory condition 6 proves only its narrowed, refusing
>   half.

### G4-10 · The permission gate (ADR-04, B04)
**The proposal.** Permission is PASS when the evaluated offer, or its
property, has a CURRENT binding with all of the following:
- purpose `PRIVATE_MATCHING_ONLY` or `PUBLIC_LISTING_ALLOWED`;
- the grant is `GRANTED` and not revoked;
- `granted_at ≤ now` and `bound_at ≤ now`;
- the grant's party is the offer's party.

These are the step-6 currency conditions.

- **No binding** gives UNKNOWN, with next action `CONFIRM_PERMISSION`.
- **Only revoked bindings** gives FAIL (`CONSENT_REVOKED`).
- The snapshot records the binding ids, their state at evaluation time, and
  `offer.permission_scope` (ADR-04, §6.5).
- **The buyer side** (sharing with the requester) is checked at share time,
  in Slice 5 (H05, B03). It is not a matching input.
- **Decision asked:** does `PUBLIC_LISTING_ALLOWED` imply consent to
  private matching?
- **Blocks:** step 5.

> **Display, decided in the review of a5ea6f5:** PERMISSION_MISSING is
> kept, with its basis. Its seeded label ("Permission scope insufficient")
> is NOT presented as an exact explanation of a missing binding. A displayed
> diagnostic words the explanation from the basis (`NO_CURRENT_BINDING`,
> `NOT_STARTED`). This binds steps 7 and 8.

> **DECIDED (review of f789a59): as proposed.**
> - A valid `PUBLIC_LISTING_ALLOWED` binding is accepted for INTERNAL
>   matching of the same bound resource.
> - It grants no new sharing permission. Sharing with the requester stays
>   Slice 5's check at share time.

### G4-11 · Freshness states, and the precedence of eligibility
**Freshness.** Slice 2 returns FRESH, STALE or NEVER_CONFIRMED. The match
enum is FRESH, STALE, UNKNOWN or NOT_APPLICABLE. **Proposal:**
- NEVER_CONFIRMED maps to UNKNOWN.
- Offer freshness is NOT_APPLICABLE only when no offer is evaluated.
- The freshness gate is:
  - PASS when all three are FRESH or NOT_APPLICABLE;
  - FAIL when any is STALE;
  - UNKNOWN otherwise.

**Eligibility precedence. Proposal:**
1. REJECTED if the hard gate is FAIL;
2. otherwise NEED_MORE_INFORMATION if a blocking unknown exists;
3. otherwise NEEDS_CONFIRMATION if the freshness or permission gate is not
   PASS;
4. otherwise ELIGIBLE.

`information_gate_status` is:
- UNKNOWN when a blocking unknown exists;
- PASS otherwise;
- never FAIL, because a confirmed failure belongs to the hard gate.

**Blocks:** step 5.

> **DECIDED (review of f789a59): the freshness mapping and the eligibility
> precedence, as proposed.** The reason for a missing or revoked permission
> stays visible in the diagnostic, even when the eligibility value is
> NEEDS_CONFIRMATION.

### G4-12 · The soft score
- **Facts:** the policy says `"method": "deterministic_explainable"` and
  defines no function.
- **Recommendation:** a weighted share of passing soft criteria:
  - weights: PREFERRED = 2, FLEXIBLE = 1;
  - UNKNOWN counts 0;
  - `BUDGET_TARGET` contributes `1 − min(1, |ask − target| / target)`;
  - rounded to 6 decimal places (the column is `numeric(7,6)`);
  - `null` unless the hard gate is PASS.
- The formula is itself a registry rule (G4-2), and each candidate's terms
  are stored in `explanation`.
- **Blocks:** step 6.

> **DECIDED (review of a5ea6f5): the plan's model, with its edge cases
> settled.**
> - **Weights:** PREFERRED = 2, FLEXIBLE = 1.
> - **Criteria:** a PASS contributes its full weight; a FAIL or an UNKNOWN
>   contributes 0.
> - **BUDGET_TARGET** contributes its proximity, as above:
>   - a zero target gives 1 for a zero price, and 0 for a positive one;
>   - a missing asking price gives 0.
> - **Null cases:** the score is null when there is no soft criterion, and
>   null unless the hard gate is PASS.
> - **Otherwise** the weighted share, rounded to six places.
> - `seller_expectation_dzd` stays out of the calculation.
>
> **Implemented in step 6** as `score.soft@1`. The share is computed exactly
> (as a fraction) and rounded once, half up, as PostgreSQL rounds into
> `numeric(7,6)`. G4-7 still holds: a soft criterion without a deterministic
> rule carries no weight.
>
> **Raised in step 6:** the request's own `budget_target_dzd` COLUMN has no
> importance of its own, so the decision gave it no weight. The first round
> (0cf6a7a) refused it, naming G4-12.
>
> **DECIDED (review of 0cf6a7a): option (a).** This is an explicit product
> decision, not an inference from the contract.
> - **The column is treated as a PREFERRED criterion, weight 2.** The target
>   expresses a preferred price point.
> - **`budget_importance` stays tied to `budget_max_dzd`**, and is never
>   carried over to the target.
> - **The column is recorded in the explanation as its own source
>   (COLUMN)**, with weight 2.
> - **A BUDGET_TARGET row beside it stays an independent criterion**, with
>   its own weight and effect. The two appear separately, and are never
>   merged silently.
>
> **Applied as `score.soft@2`, registered beside `@1`.** Version 1 is pinned,
> so it is not edited. Its digest and version 2's both enter the registry
> digest, and so the input hash.

### G4-13 · The canonical input hash, and what an identical re-run does
**The hash is proposed as:**
- sha256 over canonical JSON:
  - keys sorted;
  - separators `,` and `:`;
  - UTF-8 without ASCII escaping;
  - ~~decimals as strings~~ **numbers as JSON numbers, written exactly by
    value from their digits, independent of the decimal context** (corrected
    in the review of 4538a2d: as strings, the number `1` and the string `"1"`
    collided, and `normalize()` rounded to the context precision); never
    floats (the F-3 precedent);
- over the policy id and version, the registry digest (G4-2), and the five
  snapshots.
- It excludes `evaluated_at`. It includes the DERIVED freshness states, so a
  change of state changes the hash.

**An identical re-run.** Same request, property, offer, consent state and
freshness state give the same hash, and the UNIQUE constraint rejects a
second row. **Recommendation:** return the existing match, idempotently, and
write no new row.

**Blocks:** step 2.

> **DECIDED (review of aad9f34):** canonical JSON, and an identical run
> returns the existing match. One condition is added.
> - **`evaluated_offer_id` is named explicitly in the hashed input**, as a
>   top-level element and not only inside the commercial snapshot.
> - The reason: the uniqueness is `(request, property, policy, input_hash)`.
>   It does not contain the offer. Without the offer's identity in the
>   hash, two offers of the same property on identical terms could collide.
>   The second would then be treated as an "identical re-run" and never get
>   its own match.
> - Two tests are required:
>   1. two offers of one property on identical terms yield **two
>      independent matches**;
>   2. re-running the same offer writes **no second row**.

### G4-14 · Immutability that the schema does not enforce (migration `0005`)
**Facts:**
- `match_candidates` and `match_reviews` are guarded against UPDATE and
  DELETE (1294–1295).
- **`match_criterion_results` and `match_diagnostic_runs` are not.** A
  criterion result could be changed under an immutable match, which would
  defeat mandatory test 8 and G04.
- **`matching_policies` has an `immutable` column that no trigger reads.**
  Its `rules` could be edited under matches that cite its version.

**Measured (evidence §B, §C):**
- A criterion result was turned from FAIL to PASS, then deleted, under a
  match row that itself refused every change.
- A diagnostic run was updated and deleted.
- The policy marked `immutable` accepted a change to its `rules` **and to
  its `version`**. This is wider than revision 1 said. Renaming the version
  would silently break the pairing that `trg_match_commercial_context`
  checked, when they were inserted, for every match that cites it.

**Proposal:** migration `0005`, structural only, with no table, column or
reason code:
- `prevent_immutable_history_change` on UPDATE and DELETE of
  `match_criterion_results` and `match_diagnostic_runs`;
- a guard that refuses to UPDATE `version`, `name`, `rules` or `immutable`
  of a policy whose `immutable` is true, while `active` and `activated_at`
  stay writable.

**Known interaction, stated before approval:**
`match_criterion_results.request_criterion_id` is `ON DELETE SET NULL`. With
the guard in place, deleting a referenced request criterion would fail. No
code path deletes criteria today (checked). If one is added, it must supersede
the criterion instead.

**Blocks:** step 1.

> **DECIDED (2026-09-26, approved for step 1), and delivered:** migration `0005_match_history_immutability`. The review of aad9f34 found no blocker in it within G4-14's scope.

### G4-15 · The boundary with Slices 5 and 6, and "near match"
- **Recommendation:** the split in §0.
- The run's `diagnostic` carries the three counts and `blocker_summary`
  (blockers by reason code), with `suggested_actions` and
  `relaxation_scenarios` empty until Slice 6.
- **"Near match" has no numeric definition** (§13: "fails one or two
  conditions understandably"). **Proposal:** a REJECTED candidate with
  exactly one REQUIRED FAIL. It is counted only, and nothing is suggested
  from it in this slice.
- **Blocks:** step 7.

#### G4-15 in detail, for decision (revision 13)

Step 7 writes the rows, so every field it fills must have a decided
meaning. The contract gives the shapes:
- `MatchCandidate` has `explanation` (object), `next_action` (object or
  null) and `criteria`;
- `Diagnostic` has three required counts, `blocker_summary`,
  `suggested_actions` and `relaxation_scenarios`.

The contract does not give how they are filled.

| # | Question | Recommendation | Source |
|---|---|---|---|
| D1 | The boundary with Slices 5 and 6 | As §0: no `match_reviews` and no `opportunities` row; no task created; `suggested_actions` and `relaxation_scenarios` written as `[]` | §0; `IMPLEMENTATION_SLICES_v0.2.md` |
| D2 | "Near match" | A REJECTED candidate with exactly ONE REQUIRED FAIL. It is counted only; nothing is suggested from it | Spec §13 ("fails one or two conditions") |
| D3 | The three counts | `ready_opportunity_count`: candidates ELIGIBLE, the only ones a review may approve (`enforce_approved_review_gate`). `actionable_unknown_count`: candidates with at least one actionable unknown, i.e. the NEED_MORE_INFORMATION candidates; each counted once. `near_match_count`: as D2 | Spec §13, §13.1 |
| D3b | `blocker_summary` | The number of candidates per reason: the reason code, or `GATE:basis` when the code is null (e.g. `FRESHNESS:NEVER_CONFIRMED`, `PERMISSION:NO_CURRENT_BINDING`, so PERMISSION_MISSING is worded from its basis). Plus the candidate set's exclusions with their reasons and ids (G4-8: "excluded ids reported in the diagnostic") | G4-8, G4-10 display rule |
| D4 | Where the explanation is stored | `match_candidates.explanation`: each criterion's explanation keyed `CODE#ordinal`, the deferred and soft terms, every reason kept (step 5), and the engine versions (`derived_by`, `engine`, the score's). Each criterion's row stays in `match_criterion_results`. No column is added | §3.4 (corrected in revision 7) |
| D5 | `next_action` | A pinned function (like the gates) gives `{"type", "priority", "subject"}`, typed from the contract's `Task.task_type` vocabulary (as the spec's own example, §22.1). It takes the first actionable reason in §13.1's order: information first, then reconfirmation, then permission. **Mapping:** a blocking unknown on DOCUMENT_TYPE or RIGHT_TYPE gives VERIFY_DOCUMENT/HIGH; on BUDGET_MAX, CONFIRM_PRICE/HIGH; on any other code, OTHER/HIGH. A STALE or never-confirmed request gives RECONFIRM_REQUEST/NORMAL, a property RECONFIRM_PROPERTY/NORMAL, and an offer's terms CONFIRM_PRICE/NORMAL. Permission UNKNOWN or FAIL gives CONFIRM_PERMISSION/NORMAL. **null** for ELIGIBLE (the next step is a human review, Slice 5) and for REJECTED (relaxation is Slice 6). No task is created | Spec §13 ("blocking unknown → high-priority task"), §13.1, §22.1, M-12 |
| D6 | A refused run | Writes nothing: no match and no diagnostic row. A typed error naming the rule. 409 for a request status a run does not accept (G4-8, as recorded), and 422 for every other refusal: CORRECTION-004's version, G4-3 (b), G4-5R and G4-7 | G4-8; CORRECTION-004 |

**Conditions that already bind step 7**, recorded in earlier reviews:
1. **One Repeatable Read transaction per run.** Each insert runs under its
   own SAVEPOINT, and a 23505 means the identical input exists. It is read
   after commit. No `ON CONFLICT` (§3.3, measured).
2. **The input hash** (G4-13), with `evaluated_offer_id`. An identical
   re-run returns the existing match and writes no second row. Two offers
   on identical terms give two matches.
3. **The versions** each result names (`rule_id`/`rule_version` per
   criterion, `derived_by`, `engine`, `score.soft@2`) are stored with the
   match.
4. **PERMISSION_MISSING** is displayed from its basis, never from its
   seeded label (review of a5ea6f5).
5. **Version 1 of `location`, `attribute_option` and `area_min`** is not
   offered as replay evidence (G4-2 limit).
6. **The audit rows** of the three match tables are written in the same
   transaction (§3.6). `generated_by = 'RULE_ENGINE'` and
   `ai_trace_ref IS NULL` on every row.
7. **G4-5R:** a RENT run is refused.

### G4-16 · Should Slice 2 refuse these criteria at entry? (new in revision 2)
- **Fact:** the defects measured in §E enter through Slice 2's
  `POST /requests/{id}/criteria`, which is closed.
- **Options:**
  - (a) Leave Slice 2 unchanged. Slice 4 refuses the RUN (G4-3 (b),
    G4-7 (a)) and names the criterion, so staff correct it.
  - (b) A separate, approved correction to Slice 2. Criteria are checked at
    entry: operator against code, value shape, location existence, and
    disjointness with the request's columns. It is delivered with its own
    tests and evidence.
- **Recommendation: (a) now.** Nothing that cannot be evaluated can reach a
  match. (b) is proposed as a separate item, because it changes a closed
  slice's behaviour, and that needs its own approval.
- **Blocks:** nothing in Slice 4 if (a) is chosen.

### G4-17 · An ACTIVE offer stranded on an alias (raised in step 3; decided (a))
- **Facts:**
  - G3-13 decided that an alias's offers are not moved.
  - `trg_match_commercial_context` refuses a match on an alias.
  - The same trigger requires the evaluated offer to belong to the matched
    property.
  - So an ACTIVE offer attached to an alias can be evaluated neither under
    the alias nor under its canonical record.
- **Meanwhile:** the candidate set reports it as `OFFER_ON_ALIAS`, with the
  canonical id and the offer ids (`SLICE_4_STEP3_DELIVERY.md` §3).
- **Options:**
  - (a) keep the offer on the alias and report it. Nothing is moved or
    re-linked automatically;
  - (b) an identity-review step that re-creates, or re-points, open offers
    onto the canonical record. This changes G3-13, and the identity
    workflow;
  - (c) a schema change allowing a canonical match to cite an alias's
    offer. This is a Delta.
- **Recommendation: (a)** for this slice. It changes nothing decided. The
  diagnostic makes the stranded offer visible.
- **Blocks:** nothing.

> **DECIDED (review of cc3a7fe): (a) for this slice.** The offer stays on
> the alias and is reported, with no automatic move or re-link.
>
> **Narrowed wording:** revision 5 said the offer's party "re-creates the
> offer on the canonical record". That assumed a capability that does not
> exist. It is **not** assumed that the offer's party can create an offer on
> the canonical record. Any new offer there is a new creation. It passes
> through the property's authorization and a NEW consent, by the existing
> paths, like any other offer.
>
> Why the current offer cannot be matched is proven by the frozen trigger
> `trg_match_commercial_context` (`schema_v0.2.3.sql:1170–1207`).

### G4-18 · A count criterion on a property type the attribute does not apply to (raised in step 4)
- **Facts:**
  - `ROOMS` and `BEDROOMS` apply to HOUSE_VILLA and APARTMENT only
    (`seed_master_data_v0.2.3.sql:80–81`, `applies_to`).
  - `validate_attribute` refuses them on any other type
    (`services/truth.py:166–169`), so a LAND property can never carry
    either.
- **Step 4, as built:** a missing attribute is UNKNOWN (§11: UNKNOWN is not
  FAIL). A REQUIRED `ROOMS_MIN` therefore makes every LAND candidate a
  blocking unknown, and the missing fact can never be supplied.
- **Options:**
  - (a) keep UNKNOWN: conservative, and a human sees it;
  - (b) FAIL when the attribute cannot apply to the property's type: a
    confirmed incompatibility, not a missing fact. The rule would then read
    `applies_to`, which must enter the property snapshot for replay;
  - (c) refuse the run when a REQUIRED count criterion cannot apply to the
    request's own REQUIRED property type.
- **Recommendation: (b)**, with the `applies_to` recorded in the snapshot. It
  would be a NEW rule version (`criterion.count_min@2`), registered beside
  version 1 (G4-2).
- **Blocks:** nothing now. Until decided, (a) holds.

> **DECIDED (review of f789a59): (b).**
> - An attribute that cannot apply to the property's type gives FAIL.
> - An attribute that applies but is not recorded stays UNKNOWN.
> - Implemented as `count_min@2`, beside version 1. `applies_to` is
>   recorded in the property snapshot (format 3), and replay from it is
>   tested.

---

## 5. Authorization

- **Staff only**, by the literal `x-roles`, not by hierarchy (RFC-001 §2).
- **Maker–checker is untouched.** Running matching is open to OPERATOR,
  REVIEWER and ADMIN. The decision (`postMatchesMatchIdReview`) is Slice 5's,
  and is already in `SEPARATION_SENSITIVE_OPERATIONS`.
- **Reads are staff-internal and audited** (R6.3).
- **Relations are not read** by any matching or permission predicate (R4.5).
  The architecture test is extended to the matching module.

---

## 6. STOP GATE D and the tests

### 6.1 The ten mandatory tests

Each runs on PostgreSQL, over HTTP where an operation exists, and is shown to
fail against its defect by mutation.

| # | Handoff wording | Planned test | Proves |
|---|---|---|---|
| 1 | BUY request cannot evaluate RENT offer | `test_a_buy_request_never_evaluates_a_rent_offer` + `…_the_schema_refuses_a_buy_match_on_a_rent_offer` | service + schema |
| 2 | Hard FAIL always blocks Opportunity | `test_a_hard_fail_is_rejected_whatever_the_soft_score` + `…_the_schema_refuses_to_approve_a_rejected_match` | engine + schema. The API review is Slice 5, so this is **narrowed** |
| 3 | Required UNKNOWN → Need More Information | `test_a_required_unknown_is_need_more_information_never_pass_or_fail` | engine |
| 4 | `negotiable=true` above max is not automatic PASS | `test_negotiable_above_max_is_unknown_not_pass` | G4-5 |
| 5 | seller expectation supports price internally, unexposed | `test_seller_expectation_can_pass_price_and_is_never_exposed` | G4-5, R9.3 |
| 6 | potential property without offer only with willingness context | `test_a_potential_property_without_willingness_context_is_not_evaluated` | **narrowed** (G4-9) |
| 7 | old Match replayable after request, property and offer change | `test_an_old_match_replays_from_its_snapshots_after_everything_changed` | replay (§6.2) |
| 8 | match rows are immutable | `test_match_rows_and_their_criterion_results_cannot_change` | schema (after `0005`) |
| 9 | alias property cannot receive a new Match | `test_an_alias_is_never_a_candidate` + the schema test | service + schema |
| 10 | no valid match is a valid result | `test_no_candidate_is_a_valid_run` | engine |

### 6.2 STOP GATE D: reconstruction without an LLM, generated and bound

The evidence is `docs/gate/SLICE_4_STOP_GATE_D.md`, generated as STOP GATE C
was, from the provenance-bound report (`run_binding.check`). It holds two
proofs:

1. **Reconstruction.** For every match the scenario suite produces, a pure
   function reads ONLY the stored rows:
   - the criterion results;
   - the gate statuses;
   - the snapshots;
   - the rule ids and versions.

   It re-derives eligibility and each gate. Any disagreement fails.
2. **Replay.** Re-running the registry's rules on the stored snapshots, with
   the stored versions, reproduces the stored criterion results and the
   stored `input_hash`, after the request, property, offer and consent have
   all changed (G04, C04, mandatory test 7).

It also covers the reference scenarios that fall inside this slice: M-01,
M-02, M-03, M-04, M-05, M-06, G01–G06, C01, C03, C04, D02, B04 and E02. M-12
belongs to Slice 6.

### 6.3 Concurrency

| Race | Serialises on | Expected |
|---|---|---|
| two identical runs for one request | the UNIQUE `(request, property, policy, input_hash)` | both succeed, and one row per identical input (G4-13). The loser's 23505 is absorbed by its savepoint, and the existing row is returned after commit (§3.3, measured D1, D3, D5) |
| a run while the offer's price changes | nothing: the run reads one snapshot | the match reflects exactly one consistent state, and its hash is that state's. The insert succeeds against the snapshot (measured D7) |

No winner-and-loser outcome is planned. If one appears, condition 11 of
Slice 3 applies, in its approved wording.

---

## 7. Acceptance conditions

1. The three operations are implemented. Anything undecided refuses with a
   typed error naming the rule.
2. The ten mandatory tests pass, each shown to fail against its defect.
   Tests 2 and 6 are narrowed, as stated.
3. STOP GATE D is generated from the bound run, and `--check` exits 0.
4. **No new table, column or reason code.** Migration `0005` only, if G4-14
   is approved. CORRECTION-004 only, if G4-1 is approved.
5. The matrix has 0 UNPROVEN, and the gate is 8/8.
6. **No `match_reviews` row and no `opportunities` row is written by any
   path** (computed, as condition 6 of Slice 3 was).
7. Matching changes no request, property, offer, consent or criterion (row
   digests before and after).
8. `generated_by = 'RULE_ENGINE'` and `ai_trace_ref IS NULL` on every row. No
   LLM is called.
9. No customer or public DTO can carry a match field. The seller expectation
   is never rendered or inferable (R9.2, R9.3).
10. `party_property_relations` is not read by matching or by any
    authorization predicate.
11. G3-2 stays open, and PROPERTY claims fail closed.
12. Run provenance through `record_test_run.py` and `run_binding.check`; a
    sha256 for every delivered document.

---

## 8. Sequence

| Step | Content | Blocked by |
|---|---|---|
| 1 | CORRECTION-004 (policy version) and migration `0005` (immutability) | G4-1, G4-14 |
| 2 | Policy loader, rule registry and its digest, the canonical snapshots, `input_hash`: pure functions with unit tests | G4-2, G4-13 |
| 3 | Candidate set: canonical, commercial context, transaction compatibility, the POTENTIAL refusal | G4-8, G4-9 |
| 4 | Hard gate: every criterion rule, unknown classification, the information gate | G4-3 to G4-7 |
| 5 | Freshness and permission gates; eligibility precedence | G4-10, G4-11 |
| 6 | Soft score | G4-12 |
| 7 | The run operation: persistence, audit, the diagnostic row, and concurrency (design measured, §3.3) | G4-15 |
| 8 | GET match, GET diagnostic, the ten mandatory tests, STOP GATE D, the matrix | — |

Steps 2 and 3 may begin when their decisions are taken, in parallel with
step 1.

---

## 9. Document identity

This plan is delivered with its commit and its sha256, recorded in
`docs/gate/evidence/DOCUMENT-HASHES.txt`, as every document since Slice 3.
