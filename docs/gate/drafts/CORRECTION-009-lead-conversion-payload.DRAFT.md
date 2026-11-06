# CORRECTION-009 — the REQUEST conversion's payload (DRAFT)

| | |
|---|---|
| **Status** | **DRAFT in final form, for review; one point open before approval** (review of `f77f8aa`). §3 is the literal entry. **§6:** the number the judge sees differs from the number the schema judges; a solution must be chosen and tested before this text is approved or the judge is wired to the conversion (plan Q-C1). Not approved; not in `docs/contract/CONTRACT_CORRECTIONS.yaml` |
| **Classification** | a narrowing of a frozen operation's request body |
| **Operation** | `postExternalLeadsLeadIdConvert` (`POST /external-leads/{lead_id}/convert`) |
| **Decision it would implement** | G3-10 Q-3 (b) ("a conversion schema must be declared by an approved contract change"); Slice 8 G8-5, REQUEST conversion only, as directed in the reviews of `3922850` and `b39ad10` |
| **Expected effective contract** | `docs/gate/drafts/SLICE8_EFFECTIVE_CONTRACT_EXPECTED.txt`: part 0 (the runtime's verdicts on the generated body), part 2 (the operation, from `+        id: CORRECTION-009`) |

---

## 1. What the frozen contract declares

```yaml
required: [party_id, consent_id]
properties:
  party_id: {type: string, format: uuid}
  consent_id: {type: string, format: uuid}
  target: {type: string, enum: [REQUEST, PROPERTY]}
  payload: {type: object, additionalProperties: true}
```

`payload` is an open object. API_CONTRACTS §4.3 says conversion "produces one
domain resource and preserves source lineage", and G3-10 decided that its
schema needs an approved contract change before anything is implemented.

## 2. The narrowing

1. **`target` and `payload` become required.** A conversion names what it
   produces, and carries what it produces.
2. **When `target = REQUEST`, `payload` must match the frozen `RequestCreate`
   without `party_id`, `management_mode` and `claim_status`**, closed
   (`additionalProperties: false`); `intent` and `transaction_intent`
   required, as in `RequestCreate`. The conversion sets the three removed
   fields itself: the lead's party, `ASSISTED`, `UNCLAIMED`.
3. **`target = PROPERTY` is not narrowed here.** It stays refused by
   decision: `409 EXTERNAL_LEAD_CONVERSION_NOT_AVAILABLE` (G3-10 Q-2 (b)).
   Narrowing its enum to REQUEST would turn that decided refusal into a `422`
   of the schema; this draft does not do it.

**Why each is a narrowing:** every body the corrected schema accepts, the
frozen schema accepts. Requiring a declared property, and adding an `allOf`
branch, only remove documents.

## 3. The entry, literally

As it would be appended to `request_body_narrowings` in
`docs/contract/CONTRACT_CORRECTIONS.yaml`. **This is the text the expected
file was generated from**, character for character (the generator read this
entry; nothing in the expected file is hand-written).

```yaml
  - id: CORRECTION-009
    decision: 'G3-10 Q-3 (b); Slice 8 plan G8-5 (REQUEST conversion only), Q-A5 and Q-B3 (a). DRAFT: approval
      pending.'
    approved: null
    operation_id: postExternalLeadsLeadIdConvert
    require:
    - target
    - payload
    add_all_of:
    - if:
        properties:
          target:
            const: REQUEST
        required:
        - target
      then:
        properties:
          payload:
            type: object
            additionalProperties: false
            required:
            - intent
            - transaction_intent
            properties:
              intent:
                type: string
                enum:
                - EXPLORING
                - ACTIVE_SEARCH
                - READY_TO_ACT
              payment:
                type: string
                enum:
                - CASH
                - BANK_FINANCING
                - MIXED
                - UNDECIDED
              desired_property_type:
                anyOf:
                - type: string
                  enum:
                  - HOUSE_VILLA
                  - APARTMENT
                  - LAND
                  - SHOP_COMMERCIAL
                  - AGRICULTURAL_PROPERTY
                  - BUILDING
                  - OTHER
                - type: 'null'
              property_type_importance:
                type: string
                enum:
                - REQUIRED
                - PREFERRED
                - FLEXIBLE
              primary_location_id:
                anyOf:
                - type: string
                  format: uuid
                - type: 'null'
              location_importance:
                type: string
                enum:
                - REQUIRED
                - PREFERRED
                - FLEXIBLE
              local_location_detail:
                type: string
              budget_target_dzd:
                type: integer
                minimum: 0
              budget_max_dzd:
                type: integer
                minimum: 0
              budget_importance:
                type: string
                enum:
                - REQUIRED
                - PREFERRED
                - FLEXIBLE
              budget_flexibility:
                type: string
                enum:
                - STRICT
                - LOW
                - MODERATE
                - HIGH
                - UNSPECIFIED
              criteria:
                type: array
                items:
                  $ref: '#/components/schemas/RequestCriterion'
              transaction_intent:
                type: string
                enum:
                - BUY
                - RENT
    frozen_defaults: {}
    rationale: 'The payload is an open object, and G3-10 Q-3 (b) requires its schema to be declared before
      a conversion exists. REQUEST only: PROPERTY stays refused by decision (409), not by schema.'
    runtime_rule: A body without target or payload, or a REQUEST payload outside the schema, is refused
      422 VALIDATION_FAILED, writing nothing and consuming no idempotency key.
    reference: docs/contract/CORRECTION-009-lead-conversion-payload.md
```

**What the payload schema is, checked by a script against the frozen
contract** (`docs/handoff/05_API/openapi_v0.2.3.yaml`, `RequestCreate`):
- its 13 properties are the frozen `RequestCreate`'s 16 **minus**
  `party_id`, `management_mode` and `claim_status`;
- each of the 13 is **equal** to the frozen one (parsed YAML compared);
- `additionalProperties: false`, as the frozen `RequestCreate`;
- `required: [intent, transaction_intent]`: the frozen required list minus
  the three removed fields;
- `criteria` refers to the frozen `#/components/schemas/RequestCriterion`;
  no schema is added (the loader refuses `$defs` and any `$ref` outside the
  frozen components, and inspects the referred component's keywords).

## 4. What carries it

- **`require: [target, payload]`:** the existing narrowing key.
- **`add_all_of`:** the key added by the preparatory step
  (`docs/gate/SLICE_8_PREP_ADD_ALL_OF_DELIVERY.md`, and its addendum
  `SLICE_8_PREP_ADD_ALL_OF_ADDENDUM.md`). The loader accepts this entry,
  each keyword's value checked (it was loaded in the worktree that generated
  the expected file, and `test_the_draft_correction_009_entry_is_accepted_by_the_loader`
  loads it from this file's §3); it uses no `date-time`; the
  generator writes the body with the branch appended to its `allOf` and
  annotates it `x-turab-correction.add-all-of`; the runtime's judge
  (`contract.body_violations`) **gives the verdicts of the expected file's
  part 0 on the body the generator wrote**, which equals the runtime's
  effective body.
- **What still separates it from force:** this entry is not in the
  repository's corrections file, `approved` is null, and no route reads
  `body_violations` yet. Approval, then Slice 8's step that wires the
  conversion, do that; neither is authorized.

## 5. Tests it would carry (when implemented)

- the effective contract regenerated, `--check` passing, and the policy
  parity gate unchanged;
- a body without `target`, or without `payload`: `422`, nothing written, the
  key free;
- `target = REQUEST` with a payload carrying `party_id`, `management_mode`,
  `claim_status` or any unknown field, or without `intent` or
  `transaction_intent`: `422`, nothing written, the key free;
- `target = PROPERTY`: `409 EXTERNAL_LEAD_CONVERSION_NOT_AVAILABLE`,
  unchanged (the schema accepts it: expected file, part 0);
- the route's verdicts equal `body_violations`' on the same bodies.

## 6. The number the judge sees (review of `f77f8aa`; plan Q-C1)

**The budget fields:** `budget_target_dzd` and `budget_max_dzd` are
`integer`, `minimum: 0`, **with no maximum** (§3, as the frozen
`RequestCreate`).
- **So the second addendum's sentence was wrong:** "no field of
  CORRECTION-009 has a bound near the double range". These fields have no
  upper bound, so the number `1e400` is within the schema.

**Measured** (M15, `evidence/SLICE8-NUMBER-PARSING-MEASUREMENTS.txt`, run
twice, identical; no database, no code changed), for `{"type": "integer",
"minimum": 0}`:

| Text | The schema (exact) | The judge today, after `json.loads` |
|---|---|---|
| `1e400` | accepted | **refused** (parsed as infinity) |
| `1e-400` | refused: not an integer | **accepted** (parsed as `0.0`) |
| `1.0000000000000001` | refused: not an integer | **accepted** (parsed as `1.0`) |
| `0.99999999999999999` | refused: not an integer | **accepted** (parsed as `1.0`) |

**Four differences, three the other way.** The judge **accepts** bodies the
contract refuses, because the float parser rounds them to an integer.
- **Those values sit near 0 and 1,** so **a maximum on the range alone does
  not remove them**. Narrowing the domain is not enough by itself.

**The two ways the review named, measured:**

| | Preserve the value at parsing | Narrow the domain by an approved bound |
|---|---|---|
| **What** | a non-integer literal parsed as `decimal.Decimal` (exact); `NaN`, `Infinity` refused at parsing; the judge's number test admits a finite `Decimal` | a `maximum` on each budget field, approved and declared |
| **M15's four differences** | **0** (the prototype, in the measurement script only) | 1 removed (`1e400`); **3 stay** (`1e-400`, `1.0000000000000001`, `0.99999999999999999`) |
| **What it needs** | a change to `contract.py` (`_type_holds`, `_json_same` admit `Decimal`), and a body parser used where the judge is wired | the `maximum` keyword admitted by the loader and the judge (a change to `contract.py`), and a business bound to approve |

**One more bound, shared by both columns and stated:** Python refuses an
integer literal over **4300 digits** at parsing (`sys.int_max_str_digits`),
where the schema, having no maximum, accepts it. Only an approved `maximum`
makes the schema refuse it too; the two would then refuse with different
statuses (a parse error, a schema refusal).

**Recommended (Q-C1):** preserve the value at parsing, the only way M15
shows agreeing on every JSON text. An approved `maximum` is optional, and
would close the 4300-digit case.
- **Either is a change to `contract.py`,** which no review has authorized.
  It would be a step of its own, or a part of Slice 8's step 3, which wires
  the conversion, with M15's texts as agreement tests.

