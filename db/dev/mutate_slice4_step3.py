"""Slice 4 step 3: which rule of the candidate set fails which test.

    .venv/bin/python db/dev/mutate_slice4_step3.py [T1 T2 ...] > /outside/the/tree.txt

Since the review of cc3a7fe, every property in the full scan's scope ends as
a candidate or with exactly one reason, so a change of scope changes the
result and is not equivalent: T18 restores the revision-1 scope. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import run

M = "src/turab/matching/candidates.py"

MUTATIONS = [
 ("T1 any request status matched", M,
  '    if request["status"] not in MATCHABLE_REQUEST_STATUSES:', "    if False:"),
 ("T2 a stale request refused", M,
  'MATCHABLE_REQUEST_STATUSES = ("ACTIVE", "NEEDS_CONFIRMATION")',
  'MATCHABLE_REQUEST_STATUSES = ("ACTIVE",)'),
 ("T3 BUY evaluates RENT (intent mapping swapped)", M,
  'OFFER_TYPE_FOR_INTENT = {"BUY": "SALE", "RENT": "RENT"}',
  'OFFER_TYPE_FOR_INTENT = {"BUY": "RENT", "RENT": "SALE"}'),
 ("T4 offers of any status qualify", M,
  "         WHERE o.status = 'ACTIVE'\n           AND o.transaction_type",
  "         WHERE o.transaction_type"),
 ("T5 offers of any transaction type qualify", M,
  "\n           AND o.transaction_type = CAST(:offer_type AS turab.transaction_type)", ""),
 ("T6 aliases are candidates", M, '        if head["alias_of"] is not None:', "        if False:"),
 ("T7 unavailable properties are candidates", M,
  '        if head["availability"] == "UNAVAILABLE":', "        if False:"),
 ("T8 one candidate per property, not per offer", M,
  'r["offer_version"]) for r in offers)', 'r["offer_version"]) for r in offers[:1])'),
 ("T9 POTENTIAL without an offer not recognised", M,
  '        elif head["supply_mode"] == "POTENTIAL" and head["offers_on_property"] == 0:',
  "        elif False:"),
 ("T10 a missing listed id is not reported", M,
  "            excluded.append(Excluded(property_id, Exclusion.PROPERTY_NOT_FOUND))\n",
  "            pass\n"),
 ("T11 listed ids not de-duplicated", M,
  "sorted(set(property_ids))", "list(property_ids)"),
 ("T12 an offer on an alias reported as a plain alias", M,
  "Exclusion.OFFER_ON_ALIAS, {", "Exclusion.IDENTITY_ALIAS, {"),
 ("T13 an unavailable property without a qualifying offer is silent (review of cc3a7fe)", M,
  "            excluded.append(Excluded(property_id, Exclusion.PROPERTY_UNAVAILABLE))\n",
  "            if offers:\n"
  "                excluded.append(Excluded(property_id, Exclusion.PROPERTY_UNAVAILABLE))\n"),
 ("T14 an alias without a qualifying offer is silent", M,
  "                excluded.append(Excluded(property_id, Exclusion.IDENTITY_ALIAS, detail))",
  "                pass"),
 ("T15 no declared order", M, "     ORDER BY p.property_id, q.offer_id\n", ""),
 ("T16 a listed property without a qualifying offer is silent", M,
  "            excluded.append(Excluded(property_id, Exclusion.NO_QUALIFYING_OFFER,\n"
  "                                     {\"offers_on_property\": head[\"offers_on_property\"]}))",
  "            pass"),
 ("T17 a POTENTIAL property with non-qualifying offers called offerless (review of cc3a7fe)", M,
  '        elif head["supply_mode"] == "POTENTIAL" and head["offers_on_property"] == 0:',
  '        elif head["supply_mode"] == "POTENTIAL":'),
 ("T18 the full scan takes every POTENTIAL property into scope (revision 1 scope)", M,
  "(p.supply_mode = 'POTENTIAL' AND NOT EXISTS \"\n"
  "              \"(SELECT 1 FROM turab.property_offers ao WHERE ao.property_id = p.property_id)))",
  "p.supply_mode = 'POTENTIAL')"),
 ("T19 only ACTIVE offers counted as offers on the property", M,
  "             WHERE ao.property_id = p.property_id) AS offers_on_property,",
  "             WHERE ao.property_id = p.property_id AND ao.status = 'ACTIVE') AS offers_on_property,"),
]

if __name__ == "__main__":
    run("TURAB — Slice 4 step 3: which rule of the candidate set fails which test",
        "tests/test_slice4_step3.py", MUTATIONS, sys.argv[1:])
