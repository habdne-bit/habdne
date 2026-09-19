# CORRECTION-001 — `POST /parties` is ADMIN and OPERATOR

| | |
|---|---|
| **Decision** | D7 |
| **Approved** | 2026-09-19 |
| **Baseline** | Developer Handoff v1.0.3, technical pack v0.2.3 |
| **Scope** | API contract and permissions only |
| **Database migration** | **None.** See §5. |
| **Status** | Implemented, verified, closed |

---

## 1. What changes

| | `x-roles` |
|---|---|
| Frozen `openapi_v0.2.3.yaml` declares | `ADMIN`, `OPERATOR`, `CUSTOMER` |
| Enforced from this correction | `ADMIN`, `OPERATOR` |

`POST /parties` creates a market PARTY on behalf of someone, performed by a
member of staff. No general self-service creation is adopted through it, and
`CUSTOMER` is not added to its permissions without a defined onboarding path.

**This does not touch the customer's own path.** A CUSTOMER creating their own
REQUEST remains in scope for Slice 2, using an account already bound to the
correct party. `POST /requests` keeps `ADMIN`, `OPERATOR`, `CUSTOMER`.

Self-service PARTY creation is held as **DL-04** in the Design Ledger: a
separate item requiring its own contract before implementation.

## 2. How it is applied without editing the published package

`docs/handoff/` is vendored **byte-for-byte** and is never edited in place.
The correction lives in `docs/contract/CONTRACT_CORRECTIONS.yaml` and is
applied when the policy table is built, so the published artifact remains the
published artifact and this file is the audited difference between it and what
is enforced.

Two invariants make the overlay safe rather than a quieter way to grant
access. Both are enforced in `src/turab/auth/contract.py` and fail at startup:

1. **A correction may only NARROW.** `corrected ⊆ frozen`. Adding a role is a
   grant of access and requires a new official package.
2. **`frozen` must describe the contract as it stands today.** If the package
   changes, a correction written against the old text fails loudly instead of
   applying silently to new text.

A correction must also name the decision that approved it. One without a
decision is an opinion.

## 3. Acceptance criteria and their evidence

All in `tests/test_correction_001.py` unless noted. 20 tests, all passing.

| Criterion (as approved) | Test |
|---|---|
| Creation succeeds for an authorized ADMIN or OPERATOR | `test_an_authorized_staff_role_creates_a_party` (parametrised over both) |
| CUSTOMER is refused **403** | `test_a_customer_is_refused_403` — code `ROLE_NOT_PERMITTED` |
| Unauthenticated is refused **401** | `test_an_unauthenticated_caller_is_refused_401` |
| No PARTY, no account, no role assignment on refusal | `test_a_refusal_creates_no_party_no_account_and_no_role` — counts `parties`, `user_accounts`, `user_account_roles` before and after, for both the 403 and the 401 |
| Idempotency guarantees continue to hold | `test_idempotency_is_unchanged_for_an_authorized_caller`, `test_the_key_is_still_required` |
| Audit guarantees continue to hold | `test_the_refusal_is_audited` |
| `POST /requests` stays available to CUSTOMER within their permissions | `test_the_customer_may_still_create_their_own_request` |

Beyond the stated criteria, three further properties are asserted because the
mechanism is new:

- `test_a_refusal_leaves_no_idempotency_record_to_replay` — a denied command
  must not consume its key. A claimed-but-never-executed key would answer a
  later legitimate request with a stale conflict; the test proves the same key
  then succeeds for an authorized caller.
- `test_no_other_operation_lost_a_role` — walks all 64 contract operations and
  asserts every one except `postParties` still equals its frozen `x-roles`. A
  correction file is a blunt instrument; this proves it cut once.
- `test_the_frozen_contract_is_not_edited` — asserts the package digest is
  still `b3b1eb86…c1f7b72`.

The overlay mechanism itself is tested by `test_a_correction_may_only_narrow`,
`test_a_correction_must_name_a_decision`,
`test_a_correction_cannot_empty_an_operation` and
`test_the_committed_correction_describes_the_contract_as_it_stands`.

## 4. Why the object gate was kept

The route still calls `authorize_staff_only` even though the role gate now
denies a customer first. The refusal code changed from
`OBJECT_NOT_AUTHORIZED` to `ROLE_NOT_PERMITTED`, which is a stronger position,
not a weaker one.

Deleting the object check as redundant would leave the contract as the only
thing between a customer and an unbounded write primitive — and a create has
no object to own, so there would be nothing else to fall back on.
`test_the_object_gate_on_party_creation_is_still_present` parses the route and
fails if it is removed.

## 5. No database migration

This correction changes the API contract and the permission table. It touches
no table, column, constraint, trigger or enum. **No migration was created**,
per the instruction not to produce a sham migration for a contract-only
change: an empty revision would add a node to the history that records nothing
and implies a schema change that did not happen.

The baseline digests are unchanged:

```
schema_v0.2.3.sql            789841a1a41d869ca78de256879e62950f0672c9719c40a94408c549e28d98a0
seed_master_data_v0.2.3.sql  21b31c4ed338bb4aac24ea5d724b265e5e5b941bc54dd627f3953f3c2ff6cf10
openapi_v0.2.3.yaml          b3b1eb864836d14e275d58e312f960e0e45c7e5b80d2170b54c0e8b39c1f7b72
```

Alembic history: one head, `0001_frozen_baseline_v0_2_3`, unchanged.

## 6. Synchronised artifacts

| Artifact | Change |
|---|---|
| `docs/handoff/05_API/openapi_v0.2.3.yaml` | **None** — byte-for-byte |
| `docs/contract/CONTRACT_CORRECTIONS.yaml` | CORRECTION-001 added |
| `src/turab/auth/contract.py` | corrections loaded, validated and applied; `verify_policy_matches_contract` expects the corrected roles |
| `src/turab/api/routes/parties.py` | rationale updated; object gate retained |
| `src/turab/services/command.py` | `authorize_staff_only` docstring updated |
| `tests/test_correction_001.py` | new, 20 tests |
| `tests/test_slice1_bola.py` | expected denial reason updated; object-gate-still-present test added |
| `docs/gate/AUTHORIZATION_EVIDENCE_MATRIX.md` | regenerated from a real run |
| `docs/DESIGN_LEDGER.md` | DL-01, DL-02, DL-03, DL-04 |
