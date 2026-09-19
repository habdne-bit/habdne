# Slice 2 — REQUEST + Criteria + Freshness · progress report

**Status:** implementation complete for the authorised scope; **STOP GATE B
demonstrated by an executable scenario**; submitted for review.
**Prepared:** 2026-09-19. **Baseline:** Handoff v1.0.3 / pack v0.2.3, frozen.

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

## 4. Provenance

A typed update writes one `observations` row (the utterance: who, when, in
what form) and one `claims` row per changed attribute (the assertion about
this request). The frozen schema already models exactly this —
`idx_claims_request_attr` exists for the lookup — so it is used as modelled
rather than reinvented. State changes are recorded the same way, carrying
`{from, to, reason_code}`.

## 5. Contractual gaps — surfaced, not filled

Each is pinned by a test, so it is visible and will announce itself when the
contract changes.

### G-1 · `RequestPatch` carries no provenance field
A client cannot say where a value came from, or attach an observation it
already recorded. The provenance captured is therefore what the server itself
can witness: the acting account, the moment, and the submitted values, with
`extracted_by = 'HUMAN_API'`. Richer provenance — a call note, a forwarded
message, a document — needs the contract to accept an `observation_id`.
**Not invented as an undeclared field.**

### G-2 · The state machine defines fewer edges than the contract permits
`RequestStateCommand` accepts six target states. §5.2 defines:

```
RAW -> CONTACTED -> QUALIFIED -> ACTIVE
ACTIVE -> NEEDS_CONFIRMATION -> ACTIVE | PAUSED | CLOSED
PAUSED/CLOSED -> ACTIVE only by explicit reactivation
```

Undefined edges — `ACTIVE -> CLOSED` directly, `RAW -> PAUSED`, and others —
are **refused**, naming the defined targets. Inventing one would add a
workflow rule to TURAB by implementation accident. If any of them is wanted,
it is a Workflow decision.

### G-3 · No way to express "explicit reactivation" in the contract
§5.2 requires leaving `PAUSED`/`CLOSED` to be explicit, and
`RequestStateCommand` provides no field to say so. An optional `reactivate`
flag is accepted **as an extra**, rather than inferring intent from the
target. It is the only field this slice accepts that the contract does not
declare, and it is named here for that reason.

### G-4 · No master reason code describes closing a REQUEST
`requests.close_reason_code` is FK-constrained to `reason_codes`, whose
categories are FRESHNESS, GENERAL, IDENTITY, MATCH, OPPORTUNITY and
PERMISSION. An operator closing a request can record only `OTHER`, or misuse
an OPPORTUNITY code that means something about a different entity. Adding
codes means editing the frozen seed, which is forbidden.
`test_no_master_reason_code_describes_closing_a_request` will fail the day a
`REQUEST_CLOSURE` category appears — which is the moment to revisit the
closing flow.

### G-5 · Nothing schedules the staleness pass
`mark_stale_as_needing_confirmation()` is an invocable operational function,
fully tested. The contract declares no scheduled-job operation and the handoff
names no schedule, so **what calls it and how often is an open decision**. No
timer was invented here.

### G-6 · A claim does not verify the claimant's relationship to the record
`POST /records/claim` carries a `verification_contact_point_id`, and the
implementation does not check that the contact point is verified, that it
belongs to the claiming account, or that it reaches the record's party. INV-1
governs *conflicts* between claimants; it says nothing about whether a
claimant is the right person.

The safe half is proved: after claiming, read access is still decided by the
account's own party binding, so an account whose party differs from the
record's gains an ownership event and **no readable record**
(`test_claiming_does_not_infer_ownership_from_the_phone` asserts the 404).
Nothing leaks.

The unsafe half is real: an account can record an ownership claim over an
assisted record it has no relationship to, and thereby **block the rightful
person** from claiming it, since INV-1 refuses the second claim. That is a
denial-of-claim, not a disclosure.

**Deciding what makes a claim legitimate is a Workflow and Permissions
decision**, so it is raised rather than resolved: per the standing rule, and
because DL-02 forbids the obvious shortcut — "this phone reaches that party"
must not become "this account owns that party's records".

## 6. Verification

| Check | Result |
|---|---|
| Application suite | **415 passing** (52 new) |
| Authorization Evidence Matrix | **113 rules, 0 UNPROVEN** |
| PostgreSQL Execution Gate | **PASS — 8/8**, 70/70 assertions |
| Effective contract + API inventory | current |
| Version consistency · handoff integrity | 11/11 · 36/36 |

STOP GATE B: `tests/test_slice2_stop_gate_b.py` runs the scenario in §7 and
asserts the three questions against one staff read.

## 7. STOP GATE B — the operational scenario

> A staff operator must be able to understand exactly what the buyer wants,
> what is hard vs preferred, and when that information was last confirmed.

Khadija rings the office about renting a flat. An operator records an
**assisted** request while she is on the phone, with three criteria at three
different importances. She later **claims** it — the same row converts to
`SHARED_MANAGEMENT/CLAIMED`, and the request count does not change. It is
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

## 8. One defect found and fixed during this slice

`authorize_request_scope` queried the **write** session before
`CommandService.run()` opened its transaction, producing
`A transaction is already begun on this Session` — a 500 on every guarded
command. The same class of error was fixed in Slice 1 for the idempotency
claim. Fixed properly rather than locally: `CommandService` now takes a
separate read session for pre-command object checks, the way
`get_subject_for_write` already resolves the actor. Caught by the Slice 2 HTTP
tests before any of this was reported as working.
