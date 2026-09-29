# Slice 4 · step 5 — the freshness gate, the permission gate, and eligibility

**Authorised:** the review of 3c4816c allowed step 5 on **G4-10 and G4-11**,
as decided in the review of f789a59. The decision carried two conditions:
- a valid PUBLIC_LISTING_ALLOWED binding counts for internal matching of the
  same bound resource, and grants no new sharing;
- the reason for a missing or revoked permission stays visible in the
  diagnostic, even under NEEDS_CONFIRMATION.

G4-5R's period stays open, and the RENT refusal stays in force.

**Basis:**
- `docs/gate/SLICE_4_PLAN.md` revision 10: G4-10, G4-11, G4-13 ("excludes
  `evaluated_at`, includes the DERIVED freshness states"), §2 steps 4–7,
  §8 step 5;
- the currency conditions of Slice 3 step 6
  (`services/public_listing._LISTABLE_OFFERS`);
- `services/freshness` (Slice 2 and Slice 3 §3.4);
- ADR-04;
- red-team B04, C03, G01; spec M-05, M-06;
- the frozen seed's FRESHNESS and PERMISSION reason codes (lines 143–145,
  155–156);
- `enforce_approved_review_gate`.

**Nothing is written.** `test_evaluating_writes_nothing` counts ten tables,
and the package-wide read-only test covers the new module.
`party_property_relations` is never read: the package-wide test forbids it.

## 1. What was built

| Where | What |
|---|---|
| `snapshots.freshness_snapshot` | pure; the three derived states (request, property, offer terms) at the run's instant |
| `snapshots.permission_snapshot` | a read; the offer's party and sharing scope, and every binding for a matching purpose on the offer or on its property, each with its grant and its state |
| `snapshots.binding_state` | pure; one binding's state |
| `eligibility.freshness_gate`, `permission_gate` | pure; the gates of G4-11 and G4-10, with their reasons |
| `eligibility.eligibility_of` | pure; G4-11's precedence over the four gates, keeping every reason |

**The run's instant (`as_of`).** One timezone-aware instant is given by the
caller. The run takes it once (step 7), and it is stored as
`evaluated_at`.
- It is written into no snapshot, so it is not hashed (G4-13).
- Two runs that see the same states give identical snapshot bytes. A state
  change gives different bytes
  (`test_the_instant_is_not_in_the_snapshot_and_states_decide_the_hash`).
- A naive instant is refused.

## 2. Freshness (G4-11)

- **The mapping:** FRESH and STALE stay as they are; NEVER_CONFIRMED maps to
  UNKNOWN. The offer is NOT_APPLICABLE only when no offer is evaluated.
- **The comparison** is Slice 2's: STALE exactly when
  `as_of − confirmed_at > days`.
  `test_freshness_agrees_with_the_slice_2_service_at_the_boundary` runs the
  engine and `services.freshness.evaluate` on the same instants, for all
  three keys, at 0, AT the threshold, and one microsecond past it.
- **The clocks:**
  - the request's `last_confirmed_at`;
  - the property's `availability_last_confirmed_at`;
  - the offer's `commercial_terms_last_confirmed_at`, not its
    `last_confirmed_at` (`test_the_freshness_snapshot_reads_the_three_clocks`).
- **The gate:** PASS when all three are FRESH or NOT_APPLICABLE; FAIL on any
  STALE; UNKNOWN otherwise. All 36 combinations are checked against an
  oracle (`test_the_freshness_gate_is_g4_11`).

## 3. Permission (G4-10)

**A binding's state, in precedence:**
1. `OTHER_PARTY`: the grant is not the offer's party. It does not count.
2. `SCOPE_MISMATCH`: the grant's scope changed after the binding. The
   trigger checks this on write only. It does not count.
3. `REVOKED`: any one marker is enough:
   - the binding is revoked;
   - the grant's status is REVOKED;
   - the grant carries a revocation date. A future date is not guessed to
     be ineffective, as in Slice 3.
4. `NOT_STARTED`: the binding or the grant starts after `as_of`.
5. `CURRENT`.

**The gate:**
- **PASS** if one counted binding is CURRENT.
- **FAIL** (CONSENT_REVOKED) if there are counted bindings and every one is
  REVOKED.
- **UNKNOWN** otherwise (PERMISSION_MISSING, next action
  `CONFIRM_PERMISSION`).

| Case | Test |
|---|---|
| PRIVATE_MATCHING_ONLY (B04), and PUBLIC_LISTING_ALLOWED (G4-10's decision), on the offer | `test_a_current_matching_binding_on_the_offer_passes` (2) |
| no binding | `test_no_binding_is_unknown_with_the_next_action` |
| each revocation marker | `test_only_revoked_bindings_fail_with_consent_revoked` (3) |
| revoked beside current | `test_a_revoked_binding_beside_a_current_one_passes` |
| a binding or grant starting later: UNKNOWN now, PASS after it starts | `test_a_binding_that_has_not_started_is_unknown_until_it_starts` (2) |
| a property binding: another party's does not count, the offer party's does | `test_a_property_binding_counts_only_for_the_offers_own_party` |
| a grant's scope changed after binding | `test_a_grant_whose_scope_changed_after_binding_does_not_count` |
| other purposes are not matching permission | `test_other_purposes_are_not_matching_permission` |
| the gate over 11 state mixes | `test_the_permission_gate_is_g4_10` |
| the gate from the stored `jsonb` form | `test_the_permission_snapshot_is_hashable_and_replays` |

**The relations.** The relation rows in the property-binding test exist only
because the frozen trigger requires one to WRITE a property binding.
Matching does not read them.

## 4. Eligibility (G4-11), and every reason kept

**The precedence:**
1. REJECTED if the hard gate is FAIL;
2. otherwise NEED_MORE_INFORMATION if a blocking unknown exists;
3. otherwise NEEDS_CONFIRMATION if freshness or permission is not PASS;
4. otherwise ELIGIBLE.

`test_eligibility_precedence_is_g4_11` checks all 36 combinations of four
hard-gate kinds and three states of each other gate. The hard-gate kinds
are: PASS, REQUIRED FAIL, REQUIRED UNKNOWN, and a soft unknown made blocking
by `blocking_if_unknown`.

**Every gate that is not PASS keeps its reason, whatever the eligibility.**
The same test asserts this in every combination. This is the review's
condition, and wider than it.

| Case | Test |
|---|---|
| **Mandatory test 3, completed with its planned name** (C03, M-02): NEED_MORE_INFORMATION, and the stale property and missing permission still listed | `test_a_required_unknown_is_need_more_information_never_pass_or_fail` |
| G01: REJECTED whatever freshness and permission, with every reason | `test_a_hard_fail_is_rejected_whatever_freshness_and_permission` |
| M-05: a stale property, all criteria passing | `test_a_stale_property_with_every_criterion_passing_needs_confirmation` |
| M-06: a stale request | `test_a_stale_request_needs_confirmation` |
| the review's condition, on PostgreSQL: missing, then revoked | `test_a_permission_reason_stays_visible_under_needs_confirmation` (2) |
| all four gates PASS and ELIGIBLE, the only state `enforce_approved_review_gate` admits | `test_every_gate_passing_is_eligible_with_no_reason` |
| the values are the schema's enums; the reason codes are seeded in their category | `test_the_values_produced_are_the_schema_enums`; `test_every_reason_code_emitted_is_seeded_in_its_category` |

Mandatory test 2's planned name, "whatever the soft score", waits for step
6.

## 5. Choices made in this step, stated for review

1. **One instant, given by the caller, recorded in no snapshot.** It is
   G4-13's reading, and step 7 stores it as `evaluated_at`.
2. **The freshness snapshot** records, for each subject, the state, its
   basis and the confirmation timestamp, plus the thresholds and the policy
   version. The timestamps repeat what the other snapshots hold. They are
   kept here so that the snapshot is readable on its own.
3. **The binding states and their precedence**, as in §3. Any revocation
   marker revokes, even a future-dated one: the Slice 3 rule, applied to
   matching.
4. **FAIL needs every counted binding revoked.** A revoked binding beside
   one not yet started is UNKNOWN, with basis NOT_STARTED.
5. **Only the two matching purposes are read.** Bindings for other purposes
   are absent from the snapshot.
6. **A property binding counts** when its grant's party is the offer's
   party. Relations are not read.
7. **Reason codes:**
   - the `*_STALE` codes ("needs reconfirmation") for STALE;
   - no code for NEVER_CONFIRMED (basis NEVER_CONFIRMED);
   - CONSENT_REVOKED for revocation;
   - PERMISSION_MISSING for "no current binding". Its label reads
     "Permission scope insufficient": the code's name states the fact, and
     the label is close but not exact. This is stated here so that it is
     not assumed.
8. **The hard gate's reasons** are the REQUIRED FAILs and the blocking
   unknowns, each with its criterion's own reason code (which may be null).
9. **A limit, stated:** the gates and the precedence are engine code, not
   registry rules.
   - They are not pinned, and the registry digest does not cover them.
   - A change to them is visible in review and in the source fingerprint,
     not by a pin.
   - If the reviewer wants them versioned like the criterion rules, they
     can be registered as rules in step 7. That would be a decision.

## 6. Mutation evidence

`db/dev/mutate_slice4_step5.py`: **32 mutations**:
- 7 on freshness;
- 10 on the binding states and on which bindings are read;
- 15 on the gates, the precedence, and the reasons.

The trial run on the dirty tree killed all 32. The recorded causes are the
intended assertions, for example:
- F6 (the instant written into the snapshot) fails the hash test;
- P9 (PUBLIC_LISTING_ALLOWED not counted) fails the G4-10 decision's test;
- E10 (the permission reason dropped) fails 28 tests.

The clean-tree result is in `evidence/SLICE4-STEP5-MUTATIONS.txt`.

## 7. What remains

- **Step 6 (the soft score) waits on G4-12**, which is not yet decided. The
  recommendation is in the plan.
- **G4-5R:** the rent period is open, and the refusal is in force.
- **Choice 9** (versioning the gates) is the reviewer's to take up or
  leave.
