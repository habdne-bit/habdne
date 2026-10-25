# CORRECTION-006 — a staff-created thread names its party

| | |
|---|---|
| **Kind** | Request-body narrowing, through the corrections overlay. It only narrows |
| **Operation** | `postCommunicationThreads` (POST `/communication/threads`) |
| **Decision** | G7-7 (a), Slice 7 plan (`docs/gate/SLICE_7_PLAN.md`). Direction approved in the review of `4aed49b`; the method approved in the review of `0f423d2`: written in step 2, its text, the effective contract and their agreement test delivered for review, as for CORRECTION-005 |
| **Status of this text** | **Submitted for approval with Slice 7 step 2's delivery. Not yet approved.** The entry in `CONTRACT_CORRECTIONS.yaml` carries no `approved` date for that reason |
| **Frozen package** | `openapi_v0.2.3.yaml`, unchanged. The correction is applied in `docs/api/openapi_effective_v0.2.3.yaml` |

## 1. The frozen text, and why it does not suffice

The body of the operation is given by `$ref` to `CommunicationThreadCreate`:

```yaml
CommunicationThreadCreate:
  type: object
  required: [channel]
  additionalProperties: false
  properties:
    channel:       {type: string, enum: [WHATSAPP, PHONE, SMS, EMAIL, WEB, IN_PERSON, OTHER]}
    party_id:      {anyOf: [{type: string, format: uuid}, {type: 'null'}]}
    request_id:    {anyOf: [{type: string, format: uuid}, {type: 'null'}]}
    property_id:   {anyOf: [{type: string, format: uuid}, {type: 'null'}]}
    opportunity_id: {anyOf: [{type: string, format: uuid}, {type: 'null'}]}
    external_thread_ref: {type: string}
```

- **`party_id` is optional and nullable.**
- **What the source says:** `API_CONTRACTS_v0.2.md` §4.12 states that the
  command "creates a thread linked to the relevant PARTY and optional domain
  context".
- **Why a party-less thread is a dead end:** it can never carry a
  COMMUNICATION_ARCHIVE consent. The frozen binding trigger refuses the
  binding for a thread with no party (measured before any code: M5,
  `docs/gate/evidence/SLICE7-PLAN-MEASUREMENTS.txt`). Under G7-9, no content
  could ever be archived in it.

## 2. The correction

| | Frozen | Effective |
|---|---|---|
| the body | `$ref: '#/components/schemas/CommunicationThreadCreate'` | an operation-local copy of that component, narrowed below |
| `required` | `[channel]` | `[channel, party_id]` |
| `party_id` | `anyOf: [{type: string, format: uuid}, {type: 'null'}]` | `{type: string, format: uuid}` |
| `components.schemas.CommunicationThreadCreate` | — | unchanged |
| every other part of the operation | — | unchanged |

**Why this narrows, and only narrows:**
- Requiring the field accepts strictly fewer bodies.
- Removing the `{type: 'null'}` branch of the field's `anyOf` refuses `null`
  and nothing else. The branch left, `{type: string, format: uuid}`, admits no
  null, so the field accepts exactly what it accepted, less `null`.
- The component is used by this operation alone: one `$ref` to it in the
  frozen file. So the copy changes no other operation, and the component is
  left as published.
- No default existed, so none is removed (`frozen_defaults: {}`).
- Roles are untouched: ADMIN, OPERATOR.

## 3. The loader's extension (`anyOf`)

**Why it was needed.** Before this correction, `non_null` accepted only a
field whose `type` is a list holding `null` (CORRECTION-005). `party_id` is
written instead with `anyOf` and a null branch.

**What `load_request_body_narrowings` now also accepts,** as a narrowing
check: a field whose `anyOf` holds exactly one `{type: 'null'}` branch,
beside at least one other branch, none of which may admit null.

**Refused, each tested in `tests/test_correction_006.py`:**
- two null branches, or none;
- a null branch alone;
- another branch whose type list holds `null`;
- another branch with no `type`;
- another branch given by `$ref`, or carrying its own combinator. Neither
  can be shown not to admit null, so neither is assumed not to;
- a `type` beside the `anyOf`.

**The transformation** (`narrowed_body_schema`, the one implementation, used
by the runtime and by the generator):
- the null branch is removed;
- one branch left replaces the `anyOf`, and the field's other keywords are
  kept;
- several branches left stay an `anyOf`.

**One change to the copy, measured.**
- **The old method:** a body given by `$ref` was copied with `deepcopy`,
  which keeps the objects the component shares within itself shared in the
  copy. For this component, the three `anyOf` string branches are one
  object, so the dump wrote them as YAML aliases, and every later anchor of
  the effective file was renumbered (168 changed lines, for no change of
  meaning).
- **The new method:** the copy is a JSON round trip, which shares nothing.
- **The result:** the regenerated effective contract differs from the
  previous one by CORRECTION-006 only. CORRECTION-004's and CORRECTION-005's
  texts are unchanged byte for byte (`generate_effective_contract.py --check`
  passes, and `tests/test_correction_001.py` compares every operation with
  its independent expectation).

## 4. The runtime rule

- **`party_id` is required, not null, and a uuid.** A body that violates it
  is refused as any body that violates the effective schema: 422
  `VALIDATION_FAILED`, writing nothing.
- **A uuid naming no party** is 422 `LINKED_RECORD_NOT_FOUND` (G7-6 rule 4,
  G7-16 (vi)).
- **Its consistency with the other links** is G7-6's.
- **The route's body model mirrors the effective schema.**
  `test_the_route_refuses_exactly_what_the_effective_schema_refuses` sends
  twelve bodies to both, and requires the same verdict from each.

## 5. Evidence

- **`tests/test_correction_006.py`:**
  - the entry;
  - the effective body, against an expectation built from the frozen
    component, independently of the transformation;
  - the frozen component, unchanged, and used by this operation alone;
  - the roles;
  - the annotation;
  - the twelve bodies, through the route and the schema;
  - the eight refusals of the extension, and its transformation with
    several branches.
- **`tests/test_slice7_step2.py`:** the absent and null `party_id` through
  the route, writing nothing.
- **`tests/test_correction_001.py`:** the effective contract changes nothing
  but what the corrections name. Its independent expectation is extended to
  the `anyOf` form.
- **Mutations:** `db/dev/mutate_slice7_step2.py`.
