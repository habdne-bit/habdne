"""Slice 5 step 6: which test refuses which weakening.

    .venv/bin/python db/dev/mutate_slice5_step6.py [P1 R1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule that step 6 proves (plan §6, §8; the review
of 3a60b3b):
- P: L-S5-3a, supersession per POLICY, in the approval and in the queue;
- R: L-S5-3b, the approval's request lock: present, of the one mode that
  conflicts with the run's foreign key, and taken BEFORE the supersession
  check;
- C: the currency check's own request lock, which revalidate and share still
  depend on;
- E: E04, the duplicate the consolidation task must name.

See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

REVIEW = "src/turab/services/match_review.py"
VIEWS = "src/turab/services/opportunity_views.py"
CURRENCY = "src/turab/services/currency.py"
IDENTITY = "src/turab/services/identity.py"
TESTS = "tests/test_slice5_step6.py"

MUTATIONS = [
    # --- P: L-S5-3a -------------------------------------------------------------------
    ("P1 the approval's supersession ignores the policy", REVIEW,
     "         WHERE request_id = :r AND property_id = :p AND matching_policy_id = :pol\n",
     "         WHERE request_id = :r AND property_id = :p\n"),
    ("P2 the match queue's supersession ignores the policy", VIEWS,
     "                          AND n.matching_policy_id = m.matching_policy_id\n", ""),
    # --- R: L-S5-3b -------------------------------------------------------------------
    ("R1 the approval takes no request lock", REVIEW,
     '    _lock_request(session, match["request_id"])\n    newer = _superseded_by(session, match)',
     '    newer = _superseded_by(session, match)'),
    ("R2 the request lock does not conflict with FOR KEY SHARE", REVIEW,
     'WHERE request_id = :r FOR UPDATE"),', 'WHERE request_id = :r FOR NO KEY UPDATE"),'),
    ("R3 the request lock is taken after the supersession check", REVIEW,
     '    _lock_request(session, match["request_id"])\n    newer = _superseded_by(session, match)',
     '    newer = _superseded_by(session, match)\n    _lock_request(session, match["request_id"])'),
    # --- C: the currency check's request lock -----------------------------------------
    ("C1 the currency check does not lock the request", CURRENCY,
     "FROM turab.requests WHERE request_id = :r FOR NO KEY UPDATE",
     "FROM turab.requests WHERE request_id = :r"),
    # --- E: E04 -----------------------------------------------------------------------
    ("E1 the consolidation task names no duplicate", IDENTITY,
     '"duplicate_open_opportunity_ids": [str(d) for d in o["duplicates"]]',
     '"duplicate_open_opportunity_ids": []'),
]

if __name__ == "__main__":
    run("TURAB — Slice 5 step 6: which test refuses which weakening (L-S5-3a, L-S5-3b, "
        "the request lock, E04)", TESTS, MUTATIONS, sys.argv[1:])
