# Slice 2 — REQUEST + Criteria + Freshness · progress report

**Status:** **CLOSED within its agreed scope**, 2026-09-20, on the acceptance
review of commit `73be3a7` plus the two instrument corrections E-01 and E-02
recorded in `REVIEW_RESPONSE_R-S2.md`. R-S2-01…R-S2-05 are closed.
**Baseline:** Handoff v1.0.3 / pack v0.2.3, frozen.

**What closure does NOT mean.** It is not operational readiness. Account
provisioning remains a declared operational gap and D4 is open, so this slice
supports development and review, not a live trial. DL-08a, DL-10, DL-11,
account provisioning and D4 keep the classification they already had; this
round revisited none of them. Matching is not started, and PROPERTY claim
eligibility is not decided — neither may be settled implicitly.

The 485 test cases and the 8/8 gate are the developer's own run, recorded in
`docs/gate/evidence/RUN-PROVENANCE.txt`. The acceptance review states it did
not re-run the PostgreSQL suite or the concurrency tests on an independent
server, and its acceptance is not presented as confirmation that they did.

**Revision 2 (2026-09-19, closing round).** This report previously classified
the claim eligibility gap as an open Workflow decision. That was wrong — the
frozen contract already declares the rule — and it is corrected throughout.
Items marked *corrected* below were changed in this round.

Results below are the developer's own run; they stand as reported until the
evidence is reviewed.

---

## 1. Scope delivered

| Authorised item | Status | Where |
|---|---|---|
| Self-managed REQUEST creation by the customer, bound to the correct party | **Done** | `POST /requests`, `authorize_request_scope` |
| Assisted creation as `ASSISTED + UNCLAIMED` | **Done** | same endpoint, staff only for that mode |
| BUY / RENT transaction intent | **Done** | required on create |
| Structured criteria registry | **Done** | FK to `criterion_definitions`; unknown code refused |
| Typed updates with provenance | **Done** | `PATCH /requests/{id}` → `observations` + `claims` |
| State transitions | **Done** | `POST /requests/{id}/state`, documented edges only |
| Freshness / reconfirmation | **Done** | `POST /requests/{id}/reconfirm`, policy-driven |
| Claim flow without duplication | **Done** | `POST /records/claim`, in-place conversion |

**Not started, as instructed:** Matching, PROPERTY, OFFER. The endpoints
`postRequestsRequestIdMatchingRun` and `getRequestsRequestIdDiagnostic` remain
unwired and denied by default.

Operations wired: **23** of 64. Nothing is served that the contract does not
declare.

## 2. The three separations

`PATCH /requests/{id}`, `POST .../state` and `POST .../reconfirm` are three
commands taking three different contract bodies, and none performs another's
work. Asserted directly: a data update leaves `status` and
`last_confirmed_at` untouched; a transition leaves the data and the
confirmation untouched; a reconfirmation changes neither the budget nor the
intent.

The one coupling that IS present is deliberate and documented: reconfirming a
`NEEDS_CONFIRMATION` request returns it to `ACTIVE`, because §5.2 defines that
edge and reconfirming is how it is taken. The transition is a consequence of
the confirmation, not a state the caller picks.

## 3. Freshness — policy-driven, nothing invented

The Reference Spec §15.1 is explicit that the duration «يجب أن تكون
Configurable وليست hard-coded داخل الكود». It is:

- the threshold lives in the **active** `matching_policies` row, seeded by the
  frozen master data as `freshness_threshold_days.request = 30`;
- `ux_matching_policy_one_active` guarantees at most one active policy, so
  "the threshold" is well defined at any moment;
- `services/freshness.py` contains **no day count** — asserted by a test that
  parses the module and fails on any integer literal outside its docstrings;
- **a missing policy raises.** No fallback, because a fallback that runs *is*
  the policy — one nobody approved and nobody can find by reading
  `matching_policies`;
- the staff read reports the policy VERSION alongside the verdict, so a reader
  knows which policy judged the request.

`NEVER_CONFIRMED` is kept distinct from `STALE`: a request that was never
confirmed has not gone out of date, it has not yet been put in date. They need
different operational handling.

## 4. Provenance — the actor is not the source

A typed update writes one `observations` row (the utterance: who, when, in
what form) and one `claims` row per changed attribute (the assertion about
this request). The frozen schema already models exactly this —
`idx_claims_request_attr` exists for the lookup — so it is used as modelled
rather than reinvented.

**The distinction the record now keeps**, because a staff member typing a
value is not evidence that the customer asked for it:

| Recorded | Meaning |
|---|---|
| `recorded_by_account_id` | the authenticated actor — never inferred |
| `channel` | `SELF_SERVICE` when the party's own account submitted it; `STAFF_RECORDED` when a member of staff did |
| `asserted_by_party_id` | the party **only** for a self-service change; **null** for a staff-recorded one, which asserts nothing about what the party said |
| `source_recorded` / `source_id` | whether a call, message or document was recorded behind the change — and `false` is an honest statement, not silence |
| `payload.before` / `payload.after` | what the value was and what it became |
| `effective_verification_level` | `DECLARED` on every row this path writes. **No update raises it.** Raising it is what `verification_events` is for; retyping a value is not verifying it. |

The staff read exposes all of this as `provenance`, so the three states — the
customer said it, a staff member recorded it with a source, a staff member
recorded it with none — are distinguishable by a reader rather than
collapsed.

## 5. Gaps — what was corrected, and what remains open

### Corrected in this round

| Was | Now |
|---|---|
| **G-6 / DL-08** — claim eligibility described as an open decision | **Declared condition, now enforced.** `CORRECTION-003`. Five conditions checked inside the write transaction under `SELECT … FOR UPDATE`. DL-08 withdrawn. |
| **G-4** — no closure reason for a REQUEST | **Adopted.** Migration `0002_request_closure_reasons` adds the `REQUEST_CLOSURE` category, re-runnably, without touching the published baseline or the historical `OTHER`. |
| **G-3** — an undeclared `reactivate` field | **Removed.** The state command with `target_status=ACTIVE` is the explicit reactivation. It does not refresh `last_confirmed_at`, and `/reconfirm` never resurrects `PAUSED` or `CLOSED`. |
| **G-2** — `ACTIVE → PAUSED` / `CLOSED` undefined | **Adopted** as `CORRECTION-002`, recorded in the transitions table and annotated on the effective contract. |
| **G-1** — provenance limited to what the contract carries | **Corrected.** The record now distinguishes the ACTOR from the SOURCE: channel (`SELF_SERVICE` / `STAFF_RECORDED`), the asserting party (null for staff-recorded), whether a source was recorded, the previous and new values, and a verification level that no update path raises. |
| **G-5** — an uncalled function described as a freshness mechanism | **Corrected in fact and in wording.** `db/dev/run_freshness_pass.py` is a documented administrative command. Freshness does **not** maintain itself. |

### Still open

| # | Item | Status |
|---|---|---|
| **DL-08a** | Claim eligibility for a **PROPERTY** | The adopted rule does not transfer: `properties` has no `party_id`, and `party_property_relations` is forbidden as an authorization source by RFC-001 decision 1. The path **fails closed** and names the undecided rule. Not a Slice 2 deliverable; it will block PROPERTY claiming in Slice 3. |
| **DL-10** | What runs the freshness pass | Narrowed to "someone runs the documented command". The schedule is undecided. |
| **DL-11** | `RequestPatch` cannot carry a source reference | The service can carry a `source_id`; the contract cannot supply one, so `source_recorded` is `false` on every update through the contract as frozen. Accepting one needs a contract change. |

### On gap-documenting tests

The earlier revision counted `test_no_master_reason_code_describes_closing_a_request`
among its evidence. A test that documents an absence is not evidence that the
requirement is met — it is evidence that it is not. That test has been
**replaced** by behaviour tests of the adopted codes, and the principle is
noted here so the same substitution is not made again.

## 6. Verification

| Check | Result |
|---|---|
| Application suite | **446 passing** |
| Authorization Evidence Matrix | **120 rules, 0 UNPROVEN** |
| PostgreSQL Execution Gate | **PASS — 8/8**, 70/70 assertions |
| Effective contract + API inventory | current |
| Version consistency · handoff integrity | 11/11 · 36/36 |

STOP GATE B: `tests/test_slice2_stop_gate_b.py` runs the scenario in §7 and
asserts the three questions against one staff read.

Migrations: `0001_frozen_baseline_v0_2_3` → `0002_request_closure_reasons`.
The test database is now built the way a real one is — the baseline stamped,
then migrations run forward — so the suite cannot pass against a database no
deployment can produce.

## 7. STOP GATE B — the operational scenario

> A staff operator must be able to understand exactly what the buyer wants,
> what is hard vs preferred, and when that information was last confirmed.

Khadija rings the office about renting a flat. An operator records an
**assisted** request while she is on the phone, with three criteria at three
different importances.

**An unrelated account then tries to claim it first, and is refused 403 with
no claim event written** — so nothing blocks the rightful claimant. Khadija
**claims** it: the same row converts to `SHARED_MANAGEMENT/CLAIMED`, and the
request count does not change. It is
qualified and activated through the documented path. Her budget ceiling rises,
recorded as a **data update** that leaves the status alone. Four months pass
with no contact; the staleness pass moves it to `NEEDS_CONFIRMATION`. The
operator rings, **reconfirms**, and it returns to `ACTIVE`.

The operator then performs one read, `GET /requests/{id}`, and answers:

| Question | Answered by |
|---|---|
| **What does she want?** | RENT, APARTMENT, 45 000–65 000 DZD, near the university, ACTIVE_SEARCH |
| **What is hard, what is preferred?** | `ROOMS_MIN` **REQUIRED**, `BUILT_AREA_MIN` **PREFERRED**, `DOCUMENT_TYPE` **FLEXIBLE**; property type and budget **REQUIRED**, flexibility **LOW** |
| **When was it last confirmed?** | `last_confirmed_at`, plus `freshness: {state: FRESH, threshold_days: 30, policy_version: "0.2.0"}` |

And the provenance trail shows the raise was recorded against **Khadija's own
account**, so "she asked for more" is evidence rather than recollection.

A companion test guards the gate itself: Q2 would pass vacuously if `criteria`
were absent and the dict came out empty, so the staff read is asserted to
always carry the key, with an empty list when there are none.

## 8. On the account bootstrap contract

`docs/contract/ACCOUNT_PROVISIONING_MINI_CONTRACT.md` remains **documentation
only**. Nothing in it is implemented: no `bootstrap-admin`, no `grant-role`,
no `provision-customer`. The revisions made to it in the previous round —
`--roles` at bootstrap, `asserted_actor` in the audit record, the withdrawal
of the "verified against the database" claim — are **changes to a proposal**,
not to running code. No authorisation to implement account provisioning has
been given, and none was assumed.

Accounts and roles still reach the database only through fixtures.

## 9. One defect found and fixed during this slice

`authorize_request_scope` queried the **write** session before
`CommandService.run()` opened its transaction, producing
`A transaction is already begun on this Session` — a 500 on every guarded
command. The same class of error was fixed in Slice 1 for the idempotency
claim. Fixed properly rather than locally: `CommandService` now takes a
separate read session for pre-command object checks, the way
`get_subject_for_write` already resolves the actor. Caught by the Slice 2 HTTP
tests before any of this was reported as working.
