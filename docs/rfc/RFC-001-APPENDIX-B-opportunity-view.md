# RFC-001 — Appendix B · The customer opportunity view and the frozen contract

**Status:** numbered appendix to RFC-001 revision 3 (FINAL).
**Purpose:** amend the rows of RFC-001 that the frozen contract cannot carry,
**without editing the approved document**, as Appendix A did for INV-1 and
INV-2 (DL-12).
**Raised as:** DL-13.
**Decided by:**
- G5-6 (a), direction accepted in the review of `288bfdb`: the frozen
  contract first, with an explicit addendum for R8;
- its SUMMARY_ONLY branch, decided in the review of `60b0152`: four fields,
  no area.

**Implemented in:** Slice 5 step 4 (`docs/gate/SLICE_5_PLAN.md` G5-6;
`docs/gate/SLICE_5_STEP4_DELIVERY.md`).

---

## B.0 Why this appendix exists

Three findings were measured while planning Slice 5 (plan §4), on the Slice 0
renderer of `getMeOpportunitiesOpportunityId`:

| # | Finding |
|---|---|
| F5-1 | The frozen `CustomerOpportunityView` is `additionalProperties: false` and has no `contact`. The renderer emitted a `contact` key at every scope. |
| F5-2 | At SUMMARY_ONLY the renderer emitted a `PublicPropertySummary`, whose `availability` and `offers` the frozen `CustomerPropertyView` does not allow. |
| F5-3 | R8.2 says SUMMARY_ONLY renders "area bands". The frozen type has no field for a band: an area is a number. |

**The conflict.** R8.2 and R8.3 are a project decision. The frozen contract
has no field for what they release. Master §3 forbids choosing silently
between two approved documents. G5-6 opened the decision, and (a) was taken:
**the frozen contract first**. The rows below are amended accordingly. The
body of RFC-001 is unchanged.

## B.1 R8.2, as amended

| Scope | `CustomerOpportunityView` renders |
|---|---|
| `SUMMARY_ONLY` | `opportunity_id`, `status`, `validity_status`, `sharing_scope`, `why_real`, `known_differences`, `created_at`, `shared_at`; `property` reduced to **four fields of `CustomerPropertyView`: `property_id`, `property_type`, `supply_mode`, `canonical_location_id`**. **No area, and no band**: the frozen type has no field for a band (F5-3) |
| `PROPERTY_DETAILS_ALLOWED` | the above, with `property` the **`CustomerPropertyView` without `local_location_detail`** (B.1a). **No offer term**: the frozen type has no field for one |
| `CONTACT_AFTER_CONFIRMATION` | the same as `PROPERTY_DETAILS_ALLOWED`. **No contact**: the frozen type has no field for one (F5-1), and the free-text location detail is withheld (B.1a) |

**What the amendment removes.** Two releases that the frozen contract cannot
carry:
- the public offer terms of the second row;
- the counterparty contact of the third row.

**Where they may go.** Releasing either would need a contract widening.
G5-6 (b) proposed one, and it was not taken. "The overlay may only narrow."

### B.1a Free text is withheld (review of `d0e0bc9`)

`local_location_detail` is free text with no constraint on its content. It
can carry a phone number or the address of a person.
- **What a missing key does not prove.** A response without a `contact` key
  is not thereby without contact data.
- **The decision.** The opportunity response therefore withholds the field
  at **every** scope. It is optional in the frozen `CustomerPropertyView`, so
  leaving it out narrows the response and widens nothing.
- **Where it stays:**
  - in the staff property read;
  - in the owner's own view of their property (`getMePropertiesPropertyId`),
    which this appendix does not govern.
- **Proved by** an HTTP test that writes a phone and an e-mail address into
  the field, then checks the customer's raw body at all three scopes.

*Revised in the review of `d0e0bc9`. The first delivered version of this
appendix rendered the full `CustomerPropertyView` above SUMMARY_ONLY.*

## B.2 R8.2a, unchanged and strengthened

The floor stands as written. Under B.1 no rung adds anything to the property
beyond the frozen `CustomerPropertyView`, less its free text. So the answer to R8.2a's question,
"does a higher scope add this field?", is **no** for every field of the floor,
and also no for contact and offer terms.

## B.3 R8.3, as amended

> **R8.3** `CustomerOpportunityView` releases **no contact data at any
> scope**. `CONTACT_AFTER_CONFIRMATION` names a precondition for a release
> through a channel the frozen contract does not define in this version. Its
> satisfaction is not a field of this DTO.

## B.4 The affected scenarios

| # | Scenario | Expected, as amended |
|---|---|---|
| S33 | Opportunity at `SUMMARY_ONLY` | **A**: the four property fields; no area, no availability, no offers (B.1) |
| S34 | Opportunity at `CONTACT_AFTER_CONFIRMATION`, no confirmation recorded | **D**: no contact (B.3), as before |
| S36a | Opportunity at `CONTACT_AFTER_CONFIRMATION`, confirmation recorded; response inspected for internal pricing, private claims, staff notes, source-private data, AI internals | **D**: **no contact is released** (B.3); **D** none of the five appear at any scope (R8.2a) |

## B.5 Related, and not amended here

**[R4-2], decided in the review of `60b0152`.** An entry of `why_real` or
`known_differences` is withheld from the customer response when the
property's current value of the field its rule read differs from the match
snapshot's value.
- This is a rendering rule of Slice 5, recorded in the plan (G5-5).
- It narrows what is rendered, and amends no row of RFC-001.

**G5-7 (a), direction accepted in the review of `288bfdb`.** A customer sees
an opportunity only once it is shared. Before that, the answer is the one an
unknown id gets.
- This is §4's authorization, applied with one more stored condition
  (`shared_at`).
- It amends no row.
