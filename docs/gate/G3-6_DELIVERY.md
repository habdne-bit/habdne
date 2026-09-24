# G3-6 · party–property relations — delivery note

**Basis:** Contract Delta revision 3, re-confirmed, with the two textual
corrections applied as **revision 3a**:
- §10: a future `valid_from` creates a relation that is not current until it
  starts.
- §7: only create and end mutate; retrieve is a read.

**Declared in:** `docs/contract/addenda/ADD-G3-6_party_property_relations.yaml`.
This is an approved ADDITION. It is not the frozen `openapi_v0.2.3.yaml`, which
is unmodified, and not the correction overlay. The addendum carries the
Delta's sha256. `auth/contract.load_addenda` refuses to start the service if
the Delta text changes without the addendum being re-bound. It also refuses
any addendum operation that already exists in the frozen contract, any
addendum operation without `x-roles`, and any correction aimed at an addendum
operation.

## The three operations

| operationId | roles | key |
|---|---|---|
| `postPropertiesPropertyIdRelations` | ADMIN, OPERATOR | Idempotency-Key |
| `getPropertiesPropertyIdRelations` | ADMIN, OPERATOR, REVIEWER | — (a read) |
| `postPropertyRelationEnd` | ADMIN, OPERATOR | Idempotency-Key |

The policy table now holds 67 operations: 64 frozen and 3 from the addendum.

## Each Delta clause and its proof (`tests/test_g3_6_relations.py`, 34 tests)

| Clause | Behaviour | Test (mutation that fails it) |
|---|---|---|
| §5.1 | omitted `valid_from` → `now()`, current at once | `…omitted_start_is_the_server_clock…` (M1: start left NULL) |
| §5.1 | explicit `null` refused; no offset refused | `…explicit_null_start…`, `…start_without_an_offset…` |
| §5.1 / 3a | future start allowed; not current in the list **or** at the consent gate | `…future_start_is_allowed…` (M2: currency by `valid_to` only), `…future_relation_does_not_satisfy_the_consent_gate` |
| §5 | always `DECLARED`; `verification_level` in the body refused | `…always_declared` |
| §6 / 6a | overlap → `409 RELATION_OVERLAP` naming the existing relation; other codes and parties never conflict | (M5: overlap unmapped) |
| §3.3 | end keeps the row; ending twice → `409 RELATION_ALREADY_ENDED`; end ≤ start → 422 | (M4: re-ending allowed) |
| §7 | refused create and refused end consume no key; replay returns the first result | per operation |
| §7 | audit written by the command layer (the table has no trigger): INSERT then UPDATE, with actor and context | (M3: no create audit) |
| §8 | **S12 and S16h end-to-end**: a relation created through the API opens neither the property nor an offer (404) | two tests |
| §1.1 | the consent gate's property branch is reachable through an API-created relation | `…api_created_relation_satisfies_the_consent_gate` |
| F-2 | no relation recorded on an identity alias (409) | `…not_recorded_on_an_identity_alias` |

## What this does not do

- **No customer path.** Delta §4 excludes it while G3-2 is open.
- **No operation raises `verification_level`.** Delta §5 records that a
  mechanism for doing so is a separate decision.
- **No loader reads `party_property_relations`.** A relation grants nothing
  (R4.5, R4.12).

## Slice 3 status

The relations deliverable is now delivered. Under plan §7 condition 10,
declaring Slice 3 closed still waits on the remaining steps and on review.
