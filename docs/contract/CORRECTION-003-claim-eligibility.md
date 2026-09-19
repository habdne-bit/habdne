# CORRECTION-003 — claim eligibility is a declared condition, now enforced

| | |
|---|---|
| **Classification** | **Declared authorization condition, not fully implemented.** Not an open design question. |
| **Raised as** | G-6 / DL-08 in `SLICE_2_PROGRESS.md`, misclassified there as an open decision |
| **Corrected** | 2026-09-19 |
| **Scope** | REQUEST claims. PROPERTY claims fail closed — see §5. |
| **Blocking** | Slice 2 closure |

---

## 1. The condition, as the frozen contract states it

`openapi_v0.2.3.yaml`, on `postRecordsClaim`:

> **`x-authorization`:** "For customer, verified contact point and resource
> party relationship are mandatory. Command changes ASSISTED/UNCLAIMED to
> SHARED_MANAGEMENT/CLAIMED transactionally; no duplicate resource is
> created."

The earlier report treated the missing half as a Workflow decision to be
raised. **That was wrong, and the reclassification is accepted**: the contract
already declares the rule, so the gap was an unimplemented requirement. It was
also not enough to record it in the Design Ledger while the path kept
accepting the cases it could not justify.

## 2. The adopted rule for REQUEST claims

All five conditions are checked **inside the write transaction**, after
`SELECT … FOR UPDATE` on the record.

| # | Condition | Why not the weaker version |
|---|---|---|
| 1 | The account is **ACTIVATED and bound to a party** | A staff account has no party. Staff roles alone do not confer the right to claim another party's record under the staff member's own account: claiming records *who holds* a record, and an operator is not its holder. Acting for someone else is delegation, undefined in this version (RFC-001 decision 4), so it has no path here. |
| 2 | **`account.party_id = request.party_id`** | The binding is read from `user_accounts`, established out of band today (DL-07) — never inferred from a phone number, which DL-02 forbids. |
| 3 | The presented contact point is the **account's own `login_contact_point_id`** | `control_status = VERIFIED_CONTROL` says *somebody* proved control, not that *this account* did. On a shared line either party's account could otherwise borrow the other's proof. The trusted link between an account and a number is the login contact point, which the OTP LOGIN flow is what sets. |
| 4 | That contact point **reaches the record's party** (`party_contact_points`) | Condition 2 alone would let an account claim using a number unrelated to the record. |
| 5 | The record is **ASSISTED + UNCLAIMED** | Unchanged; a self-managed record is not claimable. |

**A party mismatch is raised for review, never repaired.** `PartyLinkageNeedsReview`
refuses the claim; nothing re-links or merges parties. Two parties that look
like one person is an identity question for a human, and an automatic merge
would destroy the evidence needed to answer it (ADR-07, DL-02).

**One external message for every failing reason.** Distinguishing "not your
party" from "that contact point is not yours" would let a caller map which
records belong to which party by probing. The specific reason is internal.

## 3. Why the checks are inside the write transaction

A pre-command check on a separate read session says what was true *then*. Two
concurrent claims would both pass it, both insert, and produce exactly the
ambiguous state INV-1 exists to prevent — with INV-1 then refusing everybody.

So `claim_record` takes a row lock first and runs eligibility after it. The
lock is load-bearing and was verified as such: removing the `FOR UPDATE`
makes `test_two_concurrent_claims_produce_one_claim_and_no_ambiguity` fail on
every one of three consecutive runs.

## 4. Acceptance tests

| Case | Test |
|---|---|
| A different party | `test_an_account_of_a_different_party_cannot_claim` |
| A phone shared by two parties | `test_a_shared_phone_does_not_make_one_party_the_other` |
| A contact point belonging to another account | `test_a_contact_point_of_another_account_does_not_prove_control` |
| Two concurrent attempts | `test_two_concurrent_claims_produce_one_claim_and_no_ambiguity` |
| Staff acting under their own account | `test_staff_roles_alone_do_not_confer_the_right_to_claim` |
| The rightful claimant succeeds | `test_the_rightful_claimant_converts_the_record_in_place` |
| A refusal does not block the rightful claimant | `test_a_refused_attempt_does_not_block_the_rightful_claimant` |
| INV-1 still applies on top | `test_a_second_eligible_claim_is_still_rejected` |

Every refusal case asserts, through `_assert_no_trace`, that **no claim event
was written and the record did not change** — which is what makes the
denial-of-claim exposure closed rather than merely narrowed.

## 5. PROPERTY claims fail closed

The adopted rule is for REQUEST, and it does not transfer mechanically:
`properties` has **no `party_id` column at all**. A property's party
relationship lives in `party_property_relations`, and RFC-001 decision 1 /
R4.5 states that relations are never an authorization source. Reading the
contract's "resource party relationship" as that table would contradict a
FINAL decision; reading it any other way would be inventing one.

So `POST /records/claim` with `resource_type=PROPERTY` is refused, naming the
undecided rule — per the instruction that an affected path must reject the
cases whose eligibility it cannot prove. `test_property_claiming_fails_closed`
pins it.

**This is an open decision, and it is not a Slice 2 deliverable** — Slice 2
covers REQUEST. It will block PROPERTY claiming in Slice 3.

## 6. Fixtures

The base fixtures had **no record any account could legitimately claim** —
every assisted record belonged to a party with no account — so the condition
could only ever have been tested negatively. Added, with a `DO $$` assertion
at load time that exactly one account is eligible for the new record:

- `f7…005` — ASSISTED/UNCLAIMED for KHADIJA's party, claimable by `f3…004`;
- `f3…007` — an account for BRAHIM whose login contact point is the **shared
  line** that also reaches the agency, which is what makes the shared-phone
  case testable;
- `f7…006` + a second contact-point link — an assisted record for AMINA's
  party that **either** of the two accounts bound to it may claim, so INV-1's
  write half is still reachable with two *eligible* claimants rather than
  being masked by the eligibility check.

## 7. Consequences elsewhere

- The `CLAIM_NOT_ELIGIBLE` problem code is catalogued at **403**.
- Six INV-1 tests moved from PROPERTY to REQUEST claiming, and now use
  eligible actors, so each still tests INV-1 rather than eligibility.
- `test_a_shared_line_does_not_authenticate_as_the_party_that_shares_it`
  became sharper: the shared line now has a legitimate owner account, so the
  assertion is that LOGIN resolves to **that** account and to no other —
  stronger than the previous "to nobody".
