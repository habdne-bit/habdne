# CORRECTION-004 — the matching run requires `matching_policy_version`

| | |
|---|---|
| **Kind** | Request-body narrowing, through the corrections overlay. It only narrows |
| **Operation** | `postRequestsRequestIdMatchingRun` (POST `/requests/{request_id}/matching/run`) |
| **Decision** | G4-1, Slice 4 plan revision 2 (`docs/gate/SLICE_4_PLAN.md`), approved for step 1 on 2026-09-26 |
| **Frozen package** | `openapi_v0.2.3.yaml`, unchanged. The correction is applied in `docs/api/openapi_effective_v0.2.3.yaml` |

## 1. The defect in the frozen package

- `openapi_v0.2.3.yaml:1345–1347` declares `matching_policy_version`, a
  string, with `default: 0.1.0`, and does not require it.
- The frozen master seed (`seed_master_data_v0.2.3.sql:164–185`) creates
  exactly one matching policy, `0.2.0`, and it is the active one.
- So a run that omits the field names a policy that does not exist.
- Measured on PostgreSQL 16.13, before any code, at `75c7660`
  (`docs/gate/evidence/SLICE4-PLAN-MEASUREMENTS.txt` §A): the default is
  `0.1.0`, the rows are `[('0.2.0', active, immutable)]`, and there is no
  row for the default.

## 2. The correction

| | Frozen | Effective |
|---|---|---|
| `required` | — | `[matching_policy_version]` |
| `matching_policy_version.default` | `0.1.0` | removed |
| every other part of the operation | — | unchanged, byte for byte after parsing |

**Why this narrows, and only narrows:**
- Requiring the field accepts strictly fewer requests.
- A `default` applies only when the field is omitted, and omission is now
  refused. So removing the default changes no request that is still
  accepted.
- Roles are untouched: ADMIN, OPERATOR, REVIEWER.

**How it is kept honest.** `turab.auth.contract.load_request_body_narrowings`
is the one validator. It is used by the application at startup
(`build_policy_table`) and by the generator of the effective contract. It
refuses:
- a key that is not a narrowing;
- a missing or reused id;
- a missing decision;
- **a second narrowing of the same operation** (review of aad9f34). The
  generator indexes narrowings by operation, so a later entry would replace
  this one silently. The generator refuses that case on its own as well;
- **a field listed twice in `require`** (review of aad9f34);
- an operation that is also role-corrected, or absent from the frozen
  package;
- a field the body does not declare, or already requires;
- a narrowing that requires nothing;
- `frozen_defaults` that differ from what the package declares today. This
  is the staleness rule the role corrections already follow: if the package
  changes, the correction fails loudly instead of applying to new text.

## 3. The runtime rule, which is NOT delivered in step 1

The value must equal the version of the **active** matching policy
(`ux_matching_policy_one_active`). Any other value is refused with a typed
422, a version of an inactive policy included:
- the value is not echoed;
- nothing is written;
- the idempotency key is not consumed.

This follows the step-7 treatment of `algorithm_version`. The rule is
enforced by the matching run route, Slice 4 step 7, which does not exist yet.
Its tests come with that route:
- an omitted field;
- an unknown version;
- the version of an inactive policy;
- the active version.

## 4. Evidence

- `tests/test_correction_004.py`: 20 cases (15 at `aad9f34`, and 5 added for the review of aad9f34). They cover:
  - the effective contract;
  - the frozen package and the seed;
  - roles unchanged;
  - twelve refusals of the validator, the second narrowing and the
    repeated field included;
  - the refusal at startup, for a stale narrowing and for a second
    narrowing;
  - two refusals by the generator (through the validator, and on its own).
- `tests/test_correction_001.py`: the "changes nothing else" check now
  builds the expected operation by applying exactly this narrowing to the
  frozen one, and compares the two.
- `db/dev/mutate_correction_004.py`: eleven mutations of the validator and
  the generator, recorded in `docs/gate/evidence/SLICE4-STEP1-CORRECTION-004-MUTATIONS.txt`.
- Gate step 7: `generate_effective_contract.py --check`, the inventory
  `--check`, and `verify_policy_parity.py`.
