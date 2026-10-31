# CORRECTION-009 — the REQUEST conversion's payload (DRAFT)

| | |
|---|---|
| **Status** | **DRAFT for review**, Slice 8 plan revision 4 (Q-A5). Not approved; not in `docs/contract/CONTRACT_CORRECTIONS.yaml`. **Incomplete for approval** (review of `0a78e91`): its `payload` below is a placeholder; the literal YAML and the generated diff follow the preparatory step (Q-B3 (a)) |
| **Classification** | a narrowing of a frozen operation's request body |
| **Operation** | `postExternalLeadsLeadIdConvert` (`POST /external-leads/{lead_id}/convert`) |
| **Decision it would implement** | G3-10 Q-3 (b) ("a conversion schema must be declared by an approved contract change"); Slice 8 G8-5, REQUEST conversion only, as directed in the reviews of `3922850` and `b39ad10` |
| **Expected effective contract** | `docs/gate/drafts/SLICE8_EFFECTIVE_CONTRACT_EXPECTED.txt`, parts 2 and 3 |

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

## 3. The entry, as it would appear

```yaml
  - id: CORRECTION-009
    decision: >-
      G3-10 Q-3 (b); Slice 8 plan G8-5 (REQUEST conversion only) and Q-A5.
      DRAFT: approval pending.
    approved: null
    operation_id: postExternalLeadsLeadIdConvert
    require: [target, payload]
    add_all_of:                       # NOT SUPPORTED TODAY: plan Q-B3
      - if: {properties: {target: {const: REQUEST}}, required: [target]}
        then:
          properties:
            payload: <RequestCreate without party_id, management_mode, claim_status;
                      additionalProperties false; required [intent, transaction_intent]>
    frozen_defaults: {}
    rationale: >-
      The payload is an open object, and G3-10 Q-3 (b) requires its schema to
      be declared before a conversion exists. REQUEST only: PROPERTY stays
      refused by decision (409), not by schema.
    runtime_rule: >-
      A body without target or payload, or a REQUEST payload outside the
      schema, is refused 422 VALIDATION_FAILED, writing nothing and consuming
      no idempotency key.
    reference: docs/contract/CORRECTION-009-lead-conversion-payload.md
```

## 4. What today's mechanism can and cannot carry

**Measured by running the generator** on a temporary worktree:
- **`require: [target, payload]` is carried today.** The effective contract
  gains it, with `x-turab-correction: CORRECTION-009` on the operation (the
  expected file, part 2).
- **The `payload` schema is not.** `contract.py` accepts only `require`,
  `non_null`, `enum` and `frozen_defaults` on a body's own properties
  (`_BODY_NARROWING_KEYS`). Nothing can constrain a property's inner schema.
- **So the payload part needs a new narrowing key** (plan Q-B3), `add_all_of`:
  a list of schemas appended to the body's `allOf`, accepted by the loader
  only if it adds no `$defs` and no components, then written by the generator
  and enforced by the runtime's validation. That is a change to
  `src/turab/auth/contract.py`, the generator and their tests: code, which no
  review has authorized. The body it would produce is the expected file's
  part 3.

## 5. Tests it would carry (when implemented)

- the effective contract regenerated, `--check` passing, and the policy
  parity gate unchanged;
- a body without `target`, or without `payload`: `422`, nothing written, the
  key free;
- `target = REQUEST` with a payload carrying `party_id`, `management_mode`,
  `claim_status` or any unknown field: `422`;
- `target = PROPERTY`: `409 EXTERNAL_LEAD_CONVERSION_NOT_AVAILABLE`,
  unchanged;
- the loader refusing an `add_all_of` that adds a component or a `$defs`,
  or that is not a list of schema objects.
