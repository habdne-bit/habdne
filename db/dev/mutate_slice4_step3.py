"""Slice 4 step 3: which rule of the candidate set fails which test.

    .venv/bin/python db/dev/mutate_slice4_step3.py [T1 T2 ...] > /outside/the/tree.txt

Mutations that would only change the full scan's READ scope, and not its
result, are not listed. They are equivalent by construction: rows outside
that scope are classified silent anyway. So they could only be reported as
false survivors. See `mutation_runner.py`.
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
 ("T9 POTENTIAL without an offer passes silently", M,
  '        elif head["supply_mode"] == "POTENTIAL":', "        elif False:"),
 ("T10 a missing listed id is not reported", M,
  "            excluded.append(Excluded(property_id, Exclusion.PROPERTY_NOT_FOUND))\n",
  "            pass\n"),
 ("T11 listed ids not de-duplicated", M,
  "sorted(set(property_ids))", "list(property_ids)"),
 ("T12 an offer on an alias reported as a plain alias", M,
  "Exclusion.OFFER_ON_ALIAS, {", "Exclusion.IDENTITY_ALIAS, {"),
 ("T13 an unavailable property with an offer is silent in a full scan", M,
  "            if offers or listed is not None:", "            if listed is not None:"),
 ("T14 a listed alias is not reported", M,
  "                excluded.append(Excluded(property_id, Exclusion.IDENTITY_ALIAS, detail))",
  "                pass"),
 ("T15 no declared order", M, "     ORDER BY p.property_id, q.offer_id\n", ""),
 ("T16 a listed property without a qualifying offer is silent", M,
  "            excluded.append(Excluded(property_id, Exclusion.NO_QUALIFYING_OFFER))",
  "            pass"),
]

if __name__ == "__main__":
    run("TURAB — Slice 4 step 3: which rule of the candidate set fails which test",
        "tests/test_slice4_step3.py", MUTATIONS, sys.argv[1:])
