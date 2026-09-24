# Response to the review of `0a66f8e`

The review raised two blockers against accepting the delivery in full, and
decided G3-10. Nothing below claims F-4 or G3-6 closed: that is the
reviewer's decision, taken on this evidence.

## Blocker 1 · F-4 did not meet the structural authorization guarantee — fixed in `9f140bd`

**The defect, as stated in the review.** `load_offer`:
1. fetched the offer by `offer_id` alone;
2. then decided creator, party and claim in Python and in later queries.

RFC-001 R10.3 and R5.2 require one load statement bound to the actor's
authority, and forbid fetch-then-compare. No HTTP leak was shown. The defect
is that an unauthorized row was read before authority was decided, and 404
tests cannot distinguish the two shapes.

**The fix.** `_OFFER_AUTHORITY_SQL` is the loader's only statement. It
returns a row only through one of two arms, and each arm carries the
authority predicate:

| Arm | Predicate | What it returns |
|---|---|---|
| `GRANTED` | the actor created the offer, **or** (party match AND canonical parent `CLAIMED` AND the actor is its **only** claimant) | the offer |
| `CONTESTED` | not the creator AND party match AND the canonical parent has more than one claimant | the contested property and its claimants, plus the `offer_id` the caller supplied in the path; **every other offer column is NULL** |

- INV-1 is inside the predicate.
- The canonical parent is resolved in the same statement (R4.9).
- The creator arm consults no claim, so it stays independent of any conflict
  on the parent, as required.

**The structural test** is `tests/test_loader_shape.py`. It records the
statements a loader actually sends to PostgreSQL:
- `load_offer` sends exactly **one** statement, and it names the actor. This
  holds for granted, refused and unknown offers, across three accounts and
  four offers.
- A contested parent is decided in that same statement.
- For **every** customer loader: no statement reads the loader's resource
  table without an actor parameter in the same statement.

Against the previous loader, 14 of 22 fail. The 8 that pass are the other
loaders, which already had this shape.

The F-4 behaviour tests from `d3c016e` still pass unchanged, one per branch:
- a creator on a contested parent is admitted;
- a non-creator claimant is refused.

## Blocker 2 · the generated contract did not describe every served operation — fixed in `3fa2df7`

**The defect.**
- The policy table enforced 67 operations.
- `openapi_effective_v0.2.3.yaml` and `API_INVENTORY_GENERATED.md` described
  64.
- `generate_effective_contract.py` read only the frozen package and the
  corrections.
- The parity test walked the document into the table, one direction only.

**The fix.**
- The generator merges every approved addendum. It validates each one with
  the runtime's own `load_addenda`, so there is one implementation of the
  rules.
- Each added operation carries `x-turab-addendum`: id, kind, decision, Delta
  document and Delta sha256. The header lists each addendum's digest.
- Components may only be added. The frozen file is not modified.
- The inventory, regenerated, lists 67 operations.

**The gate check** is `db/gate/verify_policy_parity.py`, in step 7:
- documented, listed and enforced are compared as **one set of operations,
  in both directions**; roles are compared between the effective contract and
  the policy table. The inventory's text, roles included, is held to the
  effective contract by the separate `generate_api_inventory.py --check` in
  the same gate step;
- against the documents that shipped in `0a66f8e` it fails and names exactly
  the three G3-6 operations;
- `test_the_parity_check_fails_on_the_documents_that_shipped_in_0a66f8e`
  pins that.

**A consequence, stated rather than left to be found.** Step 7 now reads the
Delta documents under `docs/gate` (to verify addendum bindings) and imports
the policy code under `src/turab`. `gate_inputs.py` derives both prefixes by
itself. Under its two-level prefix rule, the evidence files in
`docs/gate/evidence` therefore classify as **gate inputs**. This round's gate
was run on a **clean tree** before any evidence file was written, so its
header shows no uncommitted path at all.

## G3-10 — decisions recorded in `0fcb854`

- Q-1 (b), Q-2 (b) and Q-3 (b): conversion stays refused, now by decision.
  The code is `EXTERNAL_LEAD_CONVERSION_NOT_AVAILABLE`; it was `…_UNDECIDED`,
  which is no longer true.
- Q-4 (c): recorded as a requirement on the future implementation.
- Q-5 to Q-8: accepted for Slice 3 only. The paging contract is recorded as a
  precondition for operational volume.

## Status, as the review set it

- **Reviewable as a partial delivery:** SOURCE capture, and linking a source
  to an offer.
- **Awaiting the reviewer on this evidence:** F-4 and G3-6.
- **Not closed:** Slice 3.

## Corrections after the review of `532af2d`

The reviewer accepted both blockers, and pointed out two descriptions that
claimed more than the mechanism guarantees. Both are corrected here and in the
code comments:

1. **CONTESTED arm.** It returns the `offer_id`, which the caller supplied in
   the path, plus the contested property and its claimants. "Every offer
   column is NULL" was inaccurate; *every other* offer column is NULL, so no
   offer detail is returned.
2. **Parity check.** `verify_policy_parity.py` compares operation **sets**
   across the effective contract, the inventory and the policy table, and
   compares **roles** only between the effective contract and the policy
   table. The inventory's text, roles included, is guaranteed by the separate
   `generate_api_inventory.py --check` in the same gate step. "Roles
   included", said of all three, overclaimed.
