"""Slice 5 step 2, the human match review: which test refuses which weakening.

    .venv/bin/python db/dev/mutate_slice5_step2.py [S1 R1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule of step 2 (plan revision 6; the review of
29a0f30), in `services/match_review.py`, the route, or `CommandService`:
- S: the review stamp and the match lock (§3.1, [R3-1]);
- D: a decided match (G5-3 (a): REJECTED and APPROVED final, NMI not, an
  opportunity decides);
- R: the reason rules (G5-3 input, G5-4, [R6-1]);
- T: the NMI task (G5-4 (a));
- A: APPROVED refused in step 2 with its own code, writing nothing;
- Z: authorization and the recorded denial of an unknown id.

See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

SVC = "src/turab/services/match_review.py"
ROUTE = "src/turab/api/routes/matching.py"
CMD = "src/turab/services/command.py"
TESTS = "tests/test_slice5_step2.py"

GREATEST = ("GREATEST(COALESCE(CAST(:clock AS timestamptz), clock_timestamp()),\n"
            "                    max(reviewed_at) + interval '1 microsecond')")
REJECT_CHECK = ("""if reason is None or not (reason["category"] in REJECT_CATEGORIES\n"""
                """                                      or reason["code"] == REJECT_OTHER):""")
APPROVED_REFUSAL = ('''        raise ReviewRefused(
            "REVIEW_DECISION_NOT_YET_AVAILABLE",
            "APPROVED is a valid decision; its execution (the currency check and "
            "the opportunity) is delivered in Slice 5 step 3. Nothing was recorded")''')
OPPORTUNITY_DECIDES = ('''    return session.execute(text(
        "SELECT EXISTS (SELECT 1 FROM turab.opportunities WHERE approved_match_id = :m)"),
        {"m": match_id}).scalar_one()''')
NMI_UNMAPPED = ('''    if reason_code not in NMI_TASK_TYPES:
        raise ReviewRefused(
            "REVIEW_REASON_NOT_ALLOWED",
            "NEED_MORE_INFORMATION takes a reason that names a specific task")
    return NMI_TASK_TYPES[reason_code]''')
DENIAL_RECORD = ('''            self._auditor.denied(
                subject=self._subject, operation_id=operation_id,
                trace_id=self._trace_id,
                reason_code=DenyReason.OBJECT_NOT_AUTHORIZED.value,
                resource_kind=MATCH_KIND, resource_id=match_id)
            return deny(DenyReason.OBJECT_NOT_AUTHORIZED, "not an available match")''')

MUTATIONS = [
    # --- S: the stamp and the lock (§3.1) ---------------------------------------------
    ("S1 stamp without the microsecond", SVC,
     "max(reviewed_at) + interval '1 microsecond'", "max(reviewed_at)"),
    ("S2 stamp is the clock alone", SVC,
     GREATEST, "COALESCE(CAST(:clock AS timestamptz), clock_timestamp())"),
    ("S3 match not locked", SVC,
     'WHERE match_id = :m FOR UPDATE"""', 'WHERE match_id = :m"""'),
    # --- D: decided (G5-3 (a)) ------------------------------------------------------
    ("D1 REJECTED not final", SVC,
     'FINAL = frozenset({"REJECTED", "APPROVED"})', 'FINAL = frozenset({"APPROVED"})'),
    ("D2 NMI final", SVC,
     'FINAL = frozenset({"REJECTED", "APPROVED"})',
     'FINAL = frozenset({"REJECTED", "APPROVED", "NEED_MORE_INFORMATION"})'),
    ("D3 an opportunity does not decide", SVC, OPPORTUNITY_DECIDES, "    return False"),
    ("D4 decided reads the OLDEST review", SVC,
     "ORDER BY reviewed_at DESC, match_review_id DESC LIMIT 1",
     "ORDER BY reviewed_at ASC, match_review_id ASC LIMIT 1"),
    ("D5 decided check removed", SVC,
     "    if _decided(session, match_id):", "    if False:"),
    # --- R: reasons (G5-3 input, G5-4, [R6-1]) --------------------------------------
    ("R1 APPROVED takes a reason", SVC,
     "        if reason_code is not None:\n            raise ReviewRefused(\"REVIEW_REASON_NOT_ALLOWED\"",
     "        if False:\n            raise ReviewRefused(\"REVIEW_REASON_NOT_ALLOWED\""),
    ("R2 a reason is not required", SVC,
     "    elif reason_code is None:", "    elif False:"),
    ("R3 REJECTED takes any category", SVC, REJECT_CHECK, "if reason is None:"),
    ("R4 an inactive reason is accepted", SVC,
     "WHERE code = :c AND active", "WHERE code = :c"),
    ("R5 NMI takes any reason", SVC, NMI_UNMAPPED,
     '    return NMI_TASK_TYPES.get(reason_code, "VERIFY_DOCUMENT")'),
    ("R6 ACTIONABLE_UNKNOWN takes OTHER", SVC,
     "        if kind not in SPECIFIC_NEXT_ACTION_TYPES:", "        if kind is None:"),
    ("R7 ACTIONABLE_UNKNOWN takes a null next_action", SVC,
     "        if kind not in SPECIFIC_NEXT_ACTION_TYPES:",
     '        if kind == "OTHER":'),
    ("R8 DOCUMENT_MISMATCH mapped to CONFIRM_PRICE", SVC,
     '"DOCUMENT_MISMATCH": "VERIFY_DOCUMENT"', '"DOCUMENT_MISMATCH": "CONFIRM_PRICE"'),
    ("R9 OFFER_STALE mapped to RECONFIRM_PROPERTY", SVC,
     '"OFFER_STALE": "CONFIRM_PRICE"', '"OFFER_STALE": "RECONFIRM_PROPERTY"'),
    # --- T: the NMI task (G5-4 (a)) -------------------------------------------------
    ("T1 no task for NMI", SVC,
     '    if prepared.decision == "NEED_MORE_INFORMATION":\n        task = _raise_task',
     '    if False:\n        task = _raise_task'),
    ("T2 priority always NORMAL", SVC,
     'priority = "HIGH" if _blocking_unknown(session, match["match_id"]) else "NORMAL"',
     'priority = "NORMAL"'),
    ("T3 a non-blocking unknown raises the priority", SVC,
     "WHERE match_id = :m AND blocking AND compatibility = 'UNKNOWN'",
     "WHERE match_id = :m AND compatibility = 'UNKNOWN'"),
    ("T4 payload without match_review_id", SVC,
     'payload = {"match_review_id": str(review_id), "next_action": match["next_action"]}',
     'payload = {"next_action": match["next_action"]}'),
    ("T5 task not audited", SVC,
     '    audit_rows.write(session, "tasks", row["task_id"], "INSERT", None,\n'
     '                     audit_rows.row_json(session, "tasks", row["task_id"]))\n',
     ""),
    ("T6 title is the reviewer's text", SVC,
     '"title": TASK_TITLES[prepared.task_type]',
     '"title": prepared.reason_text or TASK_TITLES[prepared.task_type]'),
    # --- A: APPROVED in step 2 ------------------------------------------------------
    ("A1 APPROVED executed", SVC, APPROVED_REFUSAL, "        pass"),
    ("A2 APPROVED refused as an input error", SVC,
     '            "REVIEW_DECISION_NOT_YET_AVAILABLE",\n            "APPROVED is a valid',
     '            "VALIDATION_FAILED",\n            "APPROVED is a valid'),
    ("A3 APPROVED refused as decided", SVC,
     '            "REVIEW_DECISION_NOT_YET_AVAILABLE",\n            "APPROVED is a valid',
     '            "MATCH_REVIEW_DECIDED",\n            "APPROVED is a valid'),
    # --- Z: authorization -----------------------------------------------------------
    ("Z1 an unknown id is not recorded", CMD, DENIAL_RECORD,
     '            return deny(DenyReason.OBJECT_NOT_AUTHORIZED, "not an available match")'),
    ("Z2 existence not checked by the route", ROUTE,
     "                     command.authorize_staff_only(REVIEW, \"a match review is a staff action\"),\n"
     "                     command.authorize_match_exists(match_id, REVIEW)):",
     "                     command.authorize_staff_only(REVIEW, \"a match review is a staff action\")):"),
    ("Z3 the role is not checked", ROUTE,
     "    for decision in (command.authorize(REVIEW),\n", "    for decision in (\n"),
]

if __name__ == "__main__":
    run("TURAB — Slice 5 step 2: which test refuses which weakening of the review",
        TESTS, MUTATIONS, sys.argv[1:])
