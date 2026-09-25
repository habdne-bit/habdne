"""Step 8, the properties review queue: which rule puts which property in it.

    .venv/bin/python db/dev/mutate_property_queue.py [Q1 Q2 ...] > /outside/the/tree.txt

See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

SVC = "src/turab/services/properties.py"

MUTATIONS = [
 ("Q1 a conflict is not a reason", SVC,
  "WHERE c.property_id = p.property_id AND v.outcome = 'CONFLICT_FOUND')",
  "WHERE c.property_id = p.property_id AND FALSE)"),
 ("Q2 a pending identity candidate is not a reason", SVC,
  "                  AND i.review_status IN ('PENDING_REVIEW', 'UNSURE')\n",
  "                  AND FALSE\n"),
 ("Q3 UNSURE is not a reason", SVC,
  "i.review_status IN ('PENDING_REVIEW', 'UNSURE')\n", "i.review_status IN ('PENDING_REVIEW')\n"),
 ("Q4 a decided candidate is a reason", SVC,
  "i.review_status IN ('PENDING_REVIEW', 'UNSURE')\n",
  "i.review_status IN ('PENDING_REVIEW', 'UNSURE', 'CONFIRMED_DISTINCT')\n"),
 ("Q5 stale availability is not a reason", SVC,
  "CASE WHEN p.current_availability = 'NEEDS_CONFIRMATION'", "CASE WHEN FALSE"),
 ("Q6 aliases are queued", SVC,
  "     WHERE NOT EXISTS (SELECT 1 FROM turab.property_identity_aliases a\n"
  "                        WHERE a.alias_property_id = p.property_id)\n", ""),
 ("Q7 newest first", SVC,
  "ORDER BY q.created_at, q.property_id", "ORDER BY q.created_at DESC, q.property_id"),
 ("Q8 properties with no reason are queued", SVC,
  "WHERE cardinality(q.reasons) > 0", "WHERE TRUE"),
 ("Q9 a candidate with an alias member still queues its other member", SVC,
  "                  AND NOT EXISTS (SELECT 1 FROM turab.property_identity_aliases x\n"
  "                                   WHERE x.alias_property_id\n"
  "                                         IN (i.property_a_id, i.property_b_id)))\n",
  "                  )\n"),
]

if __name__ == "__main__":
    run("TURAB — step 8: which rule puts which property in the review queue",
        "tests/test_slice3_property_queue.py", MUTATIONS, sys.argv[1:])
