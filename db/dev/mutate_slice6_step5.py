"""Slice 6 step 5, the mandatory and red-team tests end to end: which test
refuses which weakening.

    .venv/bin/python db/dev/mutate_slice6_step5.py [E1 E2 ...] > /outside/the/tree.txt

Step 5 adds no code. Each mutation weakens ONE rule that an end-to-end test
of `tests/test_slice6_step5.py` claims (plan revision 13; §6.1, §6.2, the
review of 0fae42c). The rule may sit in any module the HTTP path reaches:
- M: the three mandatory tests (§6.1);
- S: the HIGH task shared by two candidates (review of 0fae42c);
- R: the red-team cases I03, D02 / R9.3, G06 (§6.2);
- T: the title of F6-22, decided in the review of 3657973.

Only `tests/test_slice6_step5.py` is run, so a kill is this file's, not an
earlier step's. See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

RULES = "src/turab/matching/diagnostic_rules.py"
WIRING = "src/turab/matching/diagnostic.py"
RUN = "src/turab/services/matching_run.py"
TASKS = "src/turab/services/tasks.py"
TESTS = "tests/test_slice6_step5.py"

MUTATIONS = [
    # --- M: the mandatory tests (§6.1) -------------------------------------------------
    ("M1 the location is not subordinate to the document's work", RULES,
     '        scenario["subordinate_to"] = list(subordinate_to)',
     '        scenario["subordinate_to"] = []'),
    ("M2 a REJECTED candidate gets work", RULES,
     'if candidate["eligibility"] not in ("NEED_MORE_INFORMATION", "NEEDS_CONFIRMATION"):',
     'if candidate["eligibility"] not in ("NEED_MORE_INFORMATION", "NEEDS_CONFIRMATION",\n'
     '                                         "REJECTED"):'),
    ("M3 three failures make a near match", RULES,
     'if not (candidate["eligibility"] == "REJECTED" and len(failing) == 1',
     'if not (candidate["eligibility"] == "REJECTED" and len(failing) >= 1'),
    ("M4 a rejected candidate's unknown is actionable", WIRING,
     '            if record["hard_gate_status"] != "FAIL":\n                entry["actionable"] += 1',
     '            if True:\n                entry["actionable"] += 1'),
    ("M5 the budget delta reversed", RULES,
     'value = c["property_value"]["asking_price_dzd"] - c["request_value"]["value"]',
     'value = c["request_value"]["value"] - c["property_value"]["asking_price_dzd"]'),
    ("M6 not stated at the asking price", RULES,
     '                    body["stated_at"] = "ASKING_PRICE"\n', "                    pass\n"),
    ("M7 a document scenario without the user's choice", RULES,
     '                entry["only_if_user_chooses"] = True\n', "                pass\n"),
    # --- S: the shared HIGH task (review of 0fae42c) ------------------------------------
    ("S1 a shared work's match chosen arbitrarily", RUN,
     '        match_id = None if single is None else matches[(single["property_id"],\n'
     '                                                        single["offer_id"])]',
     '        first = single or action["candidates"][0]\n'
     '        match_id = matches[(first["property_id"], first["offer_id"])]'),
    ("S2 a shared PROPERTY subject loses its property", RUN,
     '        property_id = (subject["id"] if subject["entity"] == "PROPERTY"\n'
     '                       else None if single is None else single["property_id"])',
     '        property_id = None if single is None else single["property_id"]'),
    ("S3 a shared subject is not merged", RULES,
     'key = (kind, subject["entity"], subject["id"], subject["gate"],',
     'key = (kind, candidate["property_id"], subject["entity"], subject["id"], subject["gate"],'),
    ("S4 the completion does not mark the task DONE", TASKS,
     "UPDATE turab.tasks SET status = 'DONE', completed_at = :at",
     "UPDATE turab.tasks SET status = status, completed_at = :at"),
    # --- R: red-team (§6.2) -----------------------------------------------------------
    ("R1 I03: the run writes the request", RUN,
     "    tally = explain.counts((ev.hard, ev.verdict) for ev in evaluations)",
     '    session.execute(text("UPDATE turab.requests SET updated_at = now() '
     'WHERE request_id = :r"), {"r": prepared.request_id})\n'
     "    tally = explain.counts((ev.hard, ev.verdict) for ev in evaluations)"),
    ("R2 D02: the commercial terms copied into the diagnostic", RUN,
     '"stored": "NEW" if new else "EXISTING"}',
     '"stored": "NEW" if new else "EXISTING", "terms": ev.commercial_context_snapshot}'),
    ("R3 G06: the exclusions not counted", WIRING,
     '        "excluded_counts": _excluded_counts(excluded),',
     '        "excluded_counts": {},'),
    # --- T: F6-22 (review of 3657973) ---------------------------------------------------
    ("T1 the REQUEST's work under the offer's title", RUN,
     '    ("CONFIRM_PRICE", "REQUEST"): "Confirm the request\'s maximum budget",\n', ""),
    ("T2 the request's title on every subject of the type", RUN,
     "    return DIAGNOSTIC_TASK_TITLES_BY_SUBJECT.get((task_type, entity),",
     "    return DIAGNOSTIC_TASK_TITLES_BY_SUBJECT.get((task_type, \"REQUEST\"),"),
]

if __name__ == "__main__":
    sys.exit(1 if run("TURAB — Slice 6 step 5: the mandatory and red-team tests end to end",
                      TESTS, MUTATIONS, tuple(sys.argv[1:])) else 0)
