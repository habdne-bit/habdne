# CORRECTION-005 — a task completion states its outcome

| | |
|---|---|
| **Kind** | Request-body narrowing, through the corrections overlay. It only narrows |
| **Operation** | `postTasksTaskIdComplete` (POST `/tasks/{task_id}/complete`) |
| **Decision** | G6-8 (ii) (a), Slice 6 plan (`docs/gate/SLICE_6_PLAN.md`), approved in the review of `bd54216`, recorded in plan revision 4 (`62d3589`, 2026-10-17) |
| **Frozen package** | `openapi_v0.2.3.yaml`, unchanged. The correction is applied in `docs/api/openapi_effective_v0.2.3.yaml` |

## 1. The frozen text, and why it does not suffice

`openapi_v0.2.3.yaml:4727–4743`, the body of the operation, given by `$ref`
(`openapi_v0.2.3.yaml:1551`):

```yaml
TaskCompletionInput:
  type: object
  additionalProperties: false
  properties:
    outcome_code:
      type: [string, 'null']
    note:
      type: [string, 'null']
    evidence_observation_id:
      type: [string, 'null']
      format: uuid
```

- `outcome_code` is optional, nullable, and has no enum.
- The database accepts any existing code, of any category, active or not
  (measured before any code, `docs/gate/evidence/SLICE6-PLAN-MEASUREMENTS.txt`
  §E3): `DEAL_CONFIRMED` and `BUYER_REJECTED`, category OPPORTUNITY, are
  accepted as a task's outcome, as is null, and a code made inactive. No
  seeded category describes the outcome of a task.
- Migration `0007`, part B, adds the four codes of category `TASK_OUTCOME`
  (plan §5.1). This correction makes the completion name one of them.

## 2. The correction

| | Frozen | Effective |
|---|---|---|
| the body | `$ref: '#/components/schemas/TaskCompletionInput'` | an operation-local copy of that component, narrowed below |
| `required` | — | `[outcome_code]` |
| `outcome_code.type` | `[string, 'null']` | `string` |
| `outcome_code.enum` | — | `[TASK_INFORMATION_OBTAINED, TASK_INFORMATION_UNAVAILABLE, TASK_PARTY_UNREACHABLE, TASK_NO_LONGER_NEEDED]` |
| `components.schemas.TaskCompletionInput` | — | unchanged |
| every other part of the operation | — | unchanged |

**Why this narrows, and only narrows:**
- Requiring the field, removing `null` from its type and fixing its values
  each accept strictly fewer bodies.
- The component is used by this operation alone: one `$ref` to it in the
  frozen file. So the copy changes no other operation, and the component
  itself is left as published.
- No default existed, so none is removed (`frozen_defaults: {}`).
- Roles are untouched: ADMIN, OPERATOR, REVIEWER.

**What a code means, and does not (G6-8 (ii) (a), review of `1fd7bdf`).**
`TASK_INFORMATION_OBTAINED` says that the work was done. It raises no
verification level, automatically or otherwise, and proves nothing about
whether the information is true. The completion changes no fact (G6-8 (v)).

## 3. The loader's extension (F6-19)

Before this correction, `turab.auth.contract.load_request_body_narrowings`
accepted an inline body and `require` only. It now also accepts, each as a
narrowing check:
- **a body given by `$ref`**, only when that component is referenced by this
  operation alone, counted in the frozen document. Otherwise it refuses: a
  narrowing of a shared component would narrow another operation too;
- **`non_null`**: each field's frozen type must be a list that admits null,
  and some other type; the effective type removes null;
- **`enum`**: each field's frozen schema must have no enum, or a superset of
  the values; every value must be of the field's (non-null) type; no value
  may repeat.

Refused, as before: an unknown key, a missing or reused id, a missing
decision, a field not in the body, a field already required, a second
narrowing of the operation, an operation also role-corrected, and a stale
`frozen_defaults`.

**One validation, one transformation.** `load_request_body_narrowings`
validates and `narrowed_body_schema` transforms. Both are used by the
application (at startup, and by the route through `effective_request_body`)
and by the generator of the effective contract. The generator no longer
transforms a body on its own. CORRECTION-004's effective text is unchanged
byte for byte (`generate_effective_contract.py --check` passed on the
refactored generator before this correction was added).

## 4. The runtime rule

`outcome_code` is required, not null, and one of the four codes. A body
that violates it is refused as any body that violates the effective schema:
422 `VALIDATION_FAILED`, writing nothing, with the value not echoed. The
route's body model reads the enum from `effective_request_body`, so it
cannot hold a list of its own.

## 5. Evidence

`tests/test_slice6_step2.py` and `tests/test_correction_005.py`:
- the effective contract, the frozen package and the unchanged component;
- the same bodies through the effective schema and through the route
  (absent, null, an empty string, each of the four codes, a seeded general
  code, an unknown code);
- the enum equals the ACTIVE codes of category `TASK_OUTCOME` in the
  database;
- each refusal of the extended loader.

Mutations: `db/dev/mutate_slice6_step2.py`.
