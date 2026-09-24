"""The public property list — Slice 3, step 6.

Ref: the contract's `getPublicProperties` ("Returns only PUBLIC properties with
at least one active public commercial context backed by currently valid
PUBLIC_LISTING_ALLOWED consent"); API_CONTRACTS v0.2 §3 "Public"; red-team
D04; `docs/gate/SLICE_3_PLAN.md` §4.4 (the consent binds to the OFFER);
`docs/gate/SLICE_3_STEP6_DELIVERY.md`.

**The three conditions, each on its own line of SQL, all required:**

1. `properties.supply_mode = 'PUBLIC'`. Alone it is insufficient (D04).
2. An offer on the property whose `status = 'ACTIVE'`. The contract says
   "active commercial context", and API_CONTRACTS §3 adds "no withdrawn/closed
   offer as the only commercial context". DRAFT, PENDING_INFO and PAUSED are
   not active either.
3. THAT SAME offer carries a CURRENTLY VALID `PUBLIC_LISTING_ALLOWED`
   binding. "Currently valid" means all of the following:
   - the binding is not revoked;
   - its grant is `GRANTED` (the schema's own test of a live grant, the one
     `enforce_consent_binding()` applies);
   - both the binding and the grant have already started;
   - the binding's purpose AND the grant's scope are `PUBLIC_LISTING_ALLOWED`;
   - the grant is the offer's own party's.

   `enforce_consent_binding()` checks purpose, scope and party only when the
   binding is WRITTEN. Revoking a grant leaves its bindings in place, inert
   (ADR-04, `consent.revoke_consent`). A grant or an offer changed afterwards
   is not re-checked either. So the read checks all of it itself, now.

An offer that fails 2 or 3 is not projected, even when its property is listed
through another offer: a party that did not consent to public listing is not
listed.

**Two exclusions the contract's schema implies, stated for review** (the step-6
note, §3):
- a property whose `current_availability` the public schema cannot carry
  (`TEMPORARILY_UNAVAILABLE`, `UNAVAILABLE`);
- a property recorded as an identity alias of another. Its offers are not
  folded into the canonical record (G3-13).

This module reads only. It writes nothing, and it is not audited per request
(`NON_AUDITED_READ_OPERATIONS`, R6.3).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from ..auth.policy import ALLOW, Decision, DenyReason, PolicyTable, deny

#: `PublicPropertySummary.availability` in the effective contract. A property
#: whose availability is outside this set cannot be projected truthfully, so
#: it is not listed. `tests/test_slice3_public.py` pins this set to the
#: contract.
LISTABLE_AVAILABILITY = ("AVAILABLE", "POTENTIALLY_AVAILABLE", "UNDER_DISCUSSION",
                         "NEEDS_CONFIRMATION", "UNKNOWN")

#: Conditions 2 and 3: one offer, both facts. The consent predicate is
#: re-evaluated at read time; see the module docstring.
_LISTABLE_OFFERS = """
    SELECT o.offer_id, o.property_id, o.transaction_type::text AS transaction_type,
           o.asking_price_dzd, o.price_visibility::text AS price_visibility,
           o.price_negotiable::text AS price_negotiable, o.created_at
      FROM turab.property_offers o
     WHERE o.status = 'ACTIVE'
       AND EXISTS (
             SELECT 1
               FROM turab.resource_consent_bindings b
               JOIN turab.consent_grants g ON g.consent_id = b.consent_id
              WHERE b.offer_id = o.offer_id
                AND b.purpose = 'PUBLIC_LISTING_ALLOWED'
                AND b.revoked_at IS NULL
                AND b.bound_at <= now()
                AND g.scope = 'PUBLIC_LISTING_ALLOWED'
                AND g.status = 'GRANTED'
                AND g.granted_at <= now()
                AND g.party_id = o.party_id)
"""

#: ONE statement, so one snapshot. Read as two statements, the page and its
#: offers could disagree: under Read Committed each statement sees its own
#: snapshot, so a consent revoked between them would list a property with no
#: consented offer, breaking condition 3. `now()` is also one instant for the
#: whole statement.
_PAGE = f"""
    WITH listable AS ({_LISTABLE_OFFERS}),
    page AS (
        SELECT p.property_id, p.property_type::text AS property_type,
               p.canonical_location_id, p.local_location_detail,
               p.land_area_m2, p.built_area_m2, p.supply_mode::text AS supply_mode,
               p.current_availability::text AS current_availability, p.created_at
          FROM turab.properties p
         WHERE p.supply_mode = 'PUBLIC'
           AND EXISTS (SELECT 1 FROM listable l WHERE l.property_id = p.property_id)
           -- NOT NULL in the frozen schema (DEFAULT 'UNKNOWN'), so no NULL arm.
           AND p.current_availability::text = ANY(:listable_availability)
           AND NOT EXISTS (SELECT 1 FROM turab.property_identity_aliases a
                            WHERE a.alias_property_id = p.property_id)
           AND (CAST(:location_id AS uuid) IS NULL
                OR p.canonical_location_id = CAST(:location_id AS uuid))
           AND (CAST(:property_type AS text) IS NULL
                OR p.property_type::text = CAST(:property_type AS text))
         ORDER BY p.created_at DESC, p.property_id
         LIMIT :limit OFFSET :offset)
    SELECT page.*,
           (SELECT json_agg(json_build_object(
                       'offer_id', l.offer_id,
                       'transaction_type', l.transaction_type,
                       'asking_price_dzd', l.asking_price_dzd,
                       'price_visibility', l.price_visibility,
                       'price_negotiable', l.price_negotiable)
                   ORDER BY l.created_at, l.offer_id)
              FROM listable l WHERE l.property_id = page.property_id) AS offers
      FROM page
     ORDER BY page.created_at DESC, page.property_id
"""


@dataclass(frozen=True, slots=True)
class ListedProperty:
    row: Mapping[str, Any]
    offers: list[Mapping[str, Any]]


def list_public_properties(
    session: Session, *, location_id: uuid.UUID | None, property_type: str | None,
    page: int, page_size: int,
) -> list[ListedProperty]:
    """One page, newest property first (`created_at DESC, property_id`).

    `property_type` is compared as TEXT. The contract types the parameter as a
    plain string with no enum, so a value naming no type matches nothing and
    returns an empty page. Casting it to the enum would have turned any
    unknown value into a database error.

    `location_id` is an exact match on `canonical_location_id`: the literal
    reading. Whether it should also match the locations beneath it (G3-14) is
    not decided here.
    """
    rows = session.execute(text(_PAGE), {
        "listable_availability": list(LISTABLE_AVAILABILITY),
        "location_id": location_id, "property_type": property_type,
        "limit": page_size, "offset": (page - 1) * page_size,
    }).mappings().all()
    # `offers` is never NULL here: the page admits only properties with a
    # listable offer, and both come from the same snapshot.
    return [ListedProperty(row=r, offers=list(r["offers"])) for r in rows]


class PublicReads:
    """All that an unauthenticated route may reach: a read session and the
    policy table. There is no subject, because none was presented, and none
    is invented.

    `authorize` fails closed. It allows an operation only when its policy
    exists AND is public (R10.4, the closed `PUBLIC_OPERATIONS` list). An
    operation that stopped being public would be refused here with a typed
    denial. It would not reach `PolicyTable.check_role` with no subject, which
    would be a 500.
    """

    def __init__(self, session: Session, policies: PolicyTable) -> None:
        self._session = session
        self._policies = policies

    def authorize(self, operation_id: str) -> Decision:
        policy = self._policies.get(operation_id)
        if policy is None or not policy.public:
            return deny(DenyReason.NO_POLICY,
                        f"{operation_id} is not an unauthenticated operation")
        return ALLOW

    def list_properties(self, **criteria: Any) -> list[ListedProperty]:
        return list_public_properties(self._session, **criteria)
