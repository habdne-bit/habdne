"""Step 6, the public list: which clause refuses which case.

    .venv/bin/python db/dev/mutate_public_list.py [P1 P2 ...] > /outside/the/tree.txt

Each mutation removes or weakens ONE clause of `services/public_listing.py`,
one rendering rule of `dto.PublicPropertySummary`, or one check of the route,
then runs the shipped `tests/test_slice3_public.py`. See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

SVC = "src/turab/services/public_listing.py"
DTO = "src/turab/dto/boundaries.py"
ROUTE = "src/turab/api/routes/public.py"

MUTATIONS = [
 # condition 1
 ("P1 supply_mode = PUBLIC dropped", SVC, "WHERE p.supply_mode = 'PUBLIC'", "WHERE TRUE"),
 # condition 2
 ("P2 offer status = ACTIVE dropped", SVC, "WHERE o.status = 'ACTIVE'", "WHERE TRUE"),
 # condition 3, clause by clause
 ("P3 binding not tied to THIS offer", SVC, "WHERE b.offer_id = o.offer_id", "WHERE TRUE"),
 ("P4 binding purpose dropped", SVC,
  "AND b.purpose = 'PUBLIC_LISTING_ALLOWED'", ""),
 ("P5 binding revocation ignored", SVC, "AND b.revoked_at IS NULL", ""),
 ("P6 binding start ignored", SVC, "AND b.bound_at <= now()", ""),
 ("P7 grant scope dropped", SVC, "AND g.scope = 'PUBLIC_LISTING_ALLOWED'", ""),
 ("P8 grant status dropped", SVC, "AND g.status = 'GRANTED'\n", "\n"),
 ("P8b grant revocation date ignored (review of 3a53b0a)", SVC,
  "AND g.revoked_at IS NULL", ""),
 ("P9 grant start ignored", SVC, "AND g.granted_at <= now()", ""),
 ("P10 grant party not the offer's", SVC, "AND g.party_id = o.party_id)", ")"),
 # the page
 ("P11 property listed by any listable offer", SVC,
  "EXISTS (SELECT 1 FROM listable l WHERE l.property_id = p.property_id)",
  "EXISTS (SELECT 1 FROM listable l)"),
 ("P12 availability outside the public enum allowed", SVC,
  "AND p.current_availability::text = ANY(:listable_availability)", ""),
 ("P13 aliases listed", SVC,
  "AND NOT EXISTS (SELECT 1 FROM turab.property_identity_aliases a\n"
  "                            WHERE a.alias_property_id = p.property_id)", ""),
 ("P14 location filter ignored", SVC,
  "OR p.canonical_location_id IN (SELECT location_id FROM region))", "OR TRUE)"),
 ("P14b location filter exact only (G3-14)", SVC,
  "        UNION\n        SELECT l.location_id FROM turab.locations l\n"
  "          JOIN region r ON l.parent_id = r.location_id),",
  "        ),"),
 ("P15 property_type filter ignored", SVC,
  "OR p.property_type::text = CAST(:property_type AS text))", "OR TRUE)"),
 ("P16 page taken oldest first", SVC,
  "ORDER BY p.created_at DESC, p.property_id", "ORDER BY p.created_at ASC, p.property_id"),
 # the projected offers
 ("P17 every offer of the property projected", SVC,
  "FROM listable l WHERE l.property_id = page.property_id) AS offers",
  "FROM (SELECT o.offer_id, o.property_id, o.transaction_type::text AS transaction_type,"
  " o.asking_price_dzd, o.price_visibility::text AS price_visibility,"
  " o.price_negotiable::text AS price_negotiable, o.created_at"
  " FROM turab.property_offers o) l WHERE l.property_id = page.property_id) AS offers"),
 ("P18 offers newest first", SVC,
  "ORDER BY l.created_at, l.offer_id", "ORDER BY l.created_at DESC, l.offer_id"),
 # the DTO
 ("P19 local_location_detail rendered", DTO,
  "local_location_detail=None,", 'local_location_detail=row.get("local_location_detail"),'),
 ("P20 availability outside the enum rendered", DTO,
  "if availability is not None and str(availability) not in PUBLIC_AVAILABILITY:",
  "if False:"),
 ("P21 area fields typed Decimal again", DTO,
  "    land_area_m2: float | None = None\n    built_area_m2: float | None = None\n"
  "    supply_mode: str\n    availability: str | None = None",
  "    land_area_m2: Decimal | None = None\n    built_area_m2: Decimal | None = None\n"
  "    supply_mode: str\n    availability: str | None = None"),
 ("P22 price redaction removed", DTO,
  "        if visibility != PriceVisibility.PUBLIC:\n            price = None",
  "        pass"),
 # the route and its gate
 ("P23 public gate no longer requires a public policy", "src/turab/services/public_listing.py",
  "if policy is None or not policy.public:", "if policy is None:"),
 ("P24 page bounds not validated", ROUTE,
  "        page, page_size = timeline_service.validate_pagination(page, page_size)",
  "        pass"),
]

if __name__ == "__main__":
    run("TURAB — step 6: which clause refuses which case in the public list",
        "tests/test_slice3_public.py", MUTATIONS, sys.argv[1:])
