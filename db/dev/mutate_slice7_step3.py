"""Slice 7 step 3, the WhatsApp webhook: which test refuses which weakening.

    .venv/bin/python db/dev/mutate_slice7_step3.py [V1 S1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule (G7-2, G7-3, G7-4, G7-5, G7-9, G7-15, G7-16
(iv), G7-17, CORRECTION-007, CORRECTION-008), in `services/webhooks.py`, the
route, the access auditor, the problem catalogue or the contract loader:
- V: before T1: the secret, the signature, the size, the envelope, a known
  type's keys (G7-15, G7-17 (ii), (iii));
- E: the content-free event (G7-9 (1));
- M: a message's resolution and its writes (G7-3, G7-4, G7-9, G7-11, G7-16
  (iv));
- S: a status (G7-5);
- T: T1, T2 and the recovery (G7-2 (iv), (v));
- R: the route's answers and its access record (G7-17 (v), (vii),
  CORRECTION-007, CORRECTION-008);
- L: the `response_additions` loader, against
  `tests/test_correction_007_008.py`.

Not mutated, each with its reason:
- the message's pre-check of a recorded reference (`taken`): the insert's
  own refusal (the backstop, inside its savepoint) gives the same IGNORED
  `MESSAGE_REF_TAKEN` and writes nothing, so no test can tell a missing
  pre-check apart. The backstop is mutated (M5) and killed by the test that
  records the reference between the check and the insert;
- the recovery's `FOR UPDATE SKIP LOCKED`, against NOWAIT: on a held row,
  NOWAIT's 55P03 is mapped to the same IN_FLIGHT outcome, so the recovery's
  result is the same. SKIP LOCKED is the plan's choice (G7-2 (v), M4b), and is
  tested directly (`test_recovery_skips_a_row_another_processor_holds`);
- the claim's NOWAIT, against a plain FOR UPDATE: the replay would wait for
  the holder instead of answering at once. The test that holds the claim
  would then block on its own barrier until it times out. That is a kill,
  but a slow one, and it is left out of the run;
- the thread's `FOR UPDATE` is mutated (M1), but not against a test of two
  concurrent `last_message_at` moves: the insert's FOR KEY SHARE, then the
  UPDATE's re-check under READ COMMITTED, give the later time either way.
  M1 is killed by the binding that must wait (R-S7-2-01 by webhook).

`test_mandatory_test_1_concurrent_deliveries_make_one_message` is DESELECTED
from the mutation runs; it runs in the suite (`record_test_run.py`). Eight
deliveries race, so under a mutant its outcome can depend on timing: the
first pair of runs at 56659db (kept, `SLICE7-STEP3-MUTATIONS-RACE-PAIR*.txt`)
differed only there, under T3, failing it in one run and not the other. No
mutation was killed by it alone, in either run. T3's path is pinned
deterministically by `test_t2_on_a_final_event_is_final_and_writes_nothing`.

Run in two parts, one per test file; each part prints its own header. See
`mutation_runner.py`.
"""
import sys

from mutation_runner import ROOT, run

SVC = "src/turab/services/webhooks.py"
ROUTE = "src/turab/api/routes/webhooks.py"
AUDIT = "src/turab/auth/audit.py"
PROBLEMS = "src/turab/api/problems.py"
CONTRACT = "src/turab/auth/contract.py"
TESTS = "tests/test_slice7_step3.py"
CONTRACT_TESTS = "tests/test_correction_007_008.py"
DESELECT = ("test_mandatory_test_1_concurrent_deliveries_make_one_message",)

MUTATIONS = [
 # --- V: before T1 ------------------------------------------------------------------------
 ("V1 any well-formed signature accepted", SVC,
  "    return hmac.compare_digest(expected, match.group(1))",
  "    return True"),
 ("V2 a signature found inside the header accepted", SVC,
  "    match = _SIGNATURE.fullmatch(header or \"\")",
  "    match = _SIGNATURE.search(header or \"\")"),
 ("V3 the HMAC over a re-encoded body, not the raw bytes", SVC,
  "    expected = hmac.new(secret, raw, hashlib.sha256).hexdigest()",
  "    expected = hmac.new(secret, json.dumps(json.loads(raw)).encode(), "
  "hashlib.sha256).hexdigest()"),
 ("V4 an empty secret accepted as a secret", SVC,
  "    return value.encode(\"utf-8\") if value else None",
  "    return value.encode(\"utf-8\") if value is not None else None"),
 ("V5 the secret not read as UTF-8", SVC,
  "    return value.encode(\"utf-8\") if value else None",
  "    return value.encode(\"latin-1\", \"replace\") if value else None"),
 ("V6 the limit one byte larger", SVC,
  "BODY_LIMIT = 64 * 1024\n", "BODY_LIMIT = 64 * 1024 + 1\n"),
 ("V7 Content-Length not checked before reading", ROUTE,
  "    if declared_over_limit(request.headers.get(\"content-length\")):",
  "    if False:"),
 ("V17 leading zeros counted as significant", ROUTE,
  "    significant = declared.lstrip(\"0\")", "    significant = declared"),
 ("V18 any Unicode digit taken as decimal", ROUTE,
  "    if declared is None or _DECIMAL.fullmatch(declared) is None:",
  "    if declared is None or not declared.isdigit():"),
 ("V19 a long value converted whole", ROUTE,
  "    if len(significant) > len(str(webhook_service.BODY_LIMIT)):\n        return True",
  "    if False:\n        return True"),
 ("V8 the body not counted while reading", ROUTE,
  "        if size > webhook_service.BODY_LIMIT:", "        if False:"),
 ("V9 the secret not checked", ROUTE,
  "    if secret is None:\n", "    if secret is None and False:\n"),
 ("V10 the signature not checked", ROUTE,
  "    if not webhook_service.verify(", "    if False and not webhook_service.verify("),
 ("V11 an empty provider_event_id accepted", SVC,
  "    if not (isinstance(event_id, str) and event_id):",
  "    if not isinstance(event_id, str):"),
 ("V12 a non-string event_type accepted", SVC,
  "    if not isinstance(event_type, str):\n        raise refuse(",
  "    if False:\n        raise refuse("),
 ("V13 a known type's keys not checked", SVC,
  "    for key in REQUIRED_KEYS.get(event_type, ()):", "    for key in ():"),
 ("V14 a time without a zone accepted", SVC,
  "([Zz]|[+-]\\d{2}:\\d{2})\")", "([Zz]|[+-]\\d{2}:\\d{2})?\")"),
 ("V15 a status outside the six accepted", SVC,
  "        if event_type == \"status\" and payload[\"status\"] not in STATUSES:",
  "        if False:"),
 ("V16 content of another type accepted", SVC,
  "            if key in payload and not isinstance(payload[key], str):",
  "            if False:"),
 # --- E: the content-free event -----------------------------------------------------------
 ("E1 the event keeps every key of the payload", SVC,
  "    kept = {k: envelope.payload[k] for k in STORED_KEYS\n",
  "    kept = {k: envelope.payload[k] for k in envelope.payload\n"),
 ("E2 has_body never set", SVC,
  "            \"has_body\": \"body_text\" in envelope.payload,",
  "            \"has_body\": False,"),
 # --- M: a message ------------------------------------------------------------------------
 ("M1 the thread not locked before the insert", SVC,
  "         WHERE channel = 'WHATSAPP' AND external_thread_ref = :r FOR UPDATE\"\"\"),",
  "         WHERE channel = 'WHATSAPP' AND external_thread_ref = :r\"\"\"),"),
 ("M2 a thread of any channel resolved", SVC,
  "         WHERE channel = 'WHATSAPP' AND external_thread_ref = :r FOR UPDATE\"\"\"),",
  "         WHERE external_thread_ref = :r FOR UPDATE\"\"\"),"),
 ("M3 an unknown thread_ref processed", SVC,
  "        return \"IGNORED\", UNKNOWN_THREAD",
  "        return \"PROCESSED\", None"),
 ("M4 the content archived without the consent", SVC,
  "        if _archive_consent_holds(session, thread_id=thread[\"thread_id\"],",
  "        if True or _archive_consent_holds(session, thread_id=thread[\"thread_id\"],"),
 ("M5 the reference's 23505 a failure, not IGNORED", SVC,
  "        return \"IGNORED\", MESSAGE_REF_TAKEN\n    audit_rows.write(",
  "        raise\n    audit_rows.write("),
 ("M6 the content kept when the consent does not hold", SVC,
  "            body = media = None\n", "            pass\n"),
 ("M7 the recovery's withheld reason not written", SVC,
  "    elif withheld_on_recovery:", "    elif False:"),
 ("M8 the message stored OUTBOUND", SVC,
  "                VALUES (:t, :p, :ref, 'INBOUND', :mt,",
  "                VALUES (:t, :p, :ref, 'OUTBOUND', :mt,"),
 ("M9 the message's insert not audited", SVC,
  "    audit_rows.write(session, \"communication_messages\", message, \"INSERT\", None,",
  "    (lambda *a: None)(session, \"communication_messages\", message, \"INSERT\", None,"),
 ("M10 the thread moved to an earlier time", SVC,
  "         WHERE thread_id = :t AND (last_message_at IS NULL OR last_message_at < :at)",
  "         WHERE thread_id = :t"),
 ("M11 a thread not moved is audited", SVC,
  "    if moved is not None:\n", "    if True:\n"),
 ("M12 the message's webhook_event_id not written", SVC,
  "                                \"webhook_event_id\": str(event_id)}",
  "                                }"),
 # --- S: a status -------------------------------------------------------------------------
 ("S1 UNKNOWN to FAILED accepted", SVC,
  "        return new in _ORDER\n", "        return new in _ORDER or new == \"FAILED\"\n"),
 ("S2 DELIVERED to FAILED accepted", SVC,
  "        return old in (\"QUEUED\", \"SENT\")",
  "        return old in (\"QUEUED\", \"SENT\", \"DELIVERED\")"),
 ("S3 the same status accepted", SVC,
  "        return _ORDER.index(new) > _ORDER.index(old)",
  "        return _ORDER.index(new) >= _ORDER.index(old)"),
 ("S4 a status for no message processed", SVC,
  "        return \"IGNORED\", UNKNOWN_MESSAGE", "        return \"PROCESSED\", None"),
 ("S5 the message not locked before the check", SVC,
  "         WHERE provider = :p AND external_message_ref = :r FOR UPDATE\"\"\"),",
  "         WHERE provider = :p AND external_message_ref = :r\"\"\"),"),
 ("S6 a status change not audited", SVC,
  "    audit_rows.write(session, \"communication_messages\", message[\"message_id\"], "
  "\"UPDATE\",",
  "    (lambda *a: None)(session, \"communication_messages\", message[\"message_id\"], "
  "\"UPDATE\","),
 ("S7 an unknown type processed", SVC,
  "    return \"IGNORED\", UNKNOWN_EVENT_TYPE", "    return \"PROCESSED\", None"),
 # --- T: T1, T2, the recovery -------------------------------------------------------------
 ("T1 the fixed code not written", SVC,
  "               processed_at = now(), error_text = :code",
  "               processed_at = now(), error_text = NULL"),
 ("T2 a replay of a final event taken as new", SVC,
  "        return row[\"webhook_event_id\"], row[\"status\"]",
  "        return row[\"webhook_event_id\"], \"RECEIVED\""),
 ("T3 the claim takes a final event", SVC,
  "                   AND processing_status IN ('RECEIVED', 'FAILED') {lock}\"\"\"),",
  "                   {lock}\"\"\"),"),
 ("T4 55P03 not mapped to in flight", SVC,
  "        if getattr(exc.orig, \"sqlstate\", None) == \"55P03\":",
  "        if getattr(exc.orig, \"sqlstate\", None) == \"XXXXX\":"),
 ("T5 no rollback to the savepoint", SVC,
  "                savepoint.rollback()\n", "                pass\n"),
 ("T6 the failure not recorded", SVC,
  "                finish(s, event_id, \"FAILED\", PROCESSING_FAILED)\n", ""),
 ("T7 the recovery takes a fresh RECEIVED event", SVC,
  "                        AND received_at < now() - make_interval(secs => :d)))",
  "                        AND :d IS NOT NULL))"),
 ("T8 the recovery passes over FAILED events", SVC,
  "               AND (processing_status = 'FAILED'",
  "               AND (processing_status = 'PROCESSED'"),
 ("T9 the recovery forgets that content existed", SVC,
  "                             skip_locked=True, withheld_on_recovery=had_content,",
  "                             skip_locked=True, withheld_on_recovery=False,"),
 # --- R: the route's answers --------------------------------------------------------------
 ("R1 an invalid envelope answered 422", ROUTE,
  "        return refused(ProblemCode.WEBHOOK_ENVELOPE_NOT_VALID,",
  "        return refused(ProblemCode.VALIDATION_FAILED,"),
 ("R2 a T1 that raised answered as CORRECTION-007", ROUTE,
  "        return coded(ProblemCode.WEBHOOK_NOT_READY, trace, NOT_READY)",
  "        return coded(ProblemCode.WEBHOOK_PROCESSING_FAILED, trace, NOT_CONFIRMED)"),
 ("R9 the 503 of a T1 that raised claims it stored", ROUTE,
  "NOT_READY = (\"The event's acceptance could not be confirmed. Deliver it again with the \"",
  "NOT_READY = (\"The event is stored. Deliver it again with the \""),
 ("R3 a replay of an IGNORED event processed again", ROUTE,
  "    if status in (\"PROCESSED\", \"IGNORED\"):", "    if status in (\"PROCESSED\",):"),
 ("R4 a T2 lost whole answered 200", ROUTE,
  "    if outcome in (\"FAILED\", \"PROCESSING_LOST\"):", "    if outcome in (\"FAILED\",):"),
 ("R5 the 200 carries a body", ROUTE,
  "    webhook.answered(200, outcome, event_id)\n    return Response(status_code=200)",
  "    webhook.answered(200, outcome, event_id)\n    return {\"outcome\": outcome}"),
 ("R6 a processed answer not recorded", ROUTE,
  "    webhook.answered(200, outcome, event_id)\n", ""),
 ("R7 a refusal recorded as allowed", AUDIT,
  "            decision=\"DENY\" if status in (400, 401) or outcome == "
  "\"SECRET_NOT_CONFIGURED\"\n",
  "            decision=\"DENY\" if status in (400, 401)\n"),
 ("R8 the 503's code a 500", PROBLEMS,
  "    ProblemCode.WEBHOOK_NOT_READY: (503,", "    ProblemCode.WEBHOOK_NOT_READY: (500,"),
]

LOADER_MUTATIONS = [
 ("L1 an unknown key accepted", CONTRACT,
  "        if unknown:\n            raise ContractError(f\"{cid}: unknown key(s) "
  "{sorted(unknown)}; a response \"",
  "        if False:\n            raise ContractError(f\"{cid}: unknown key(s) "
  "{sorted(unknown)}; a response \""),
 ("L2 an id of another section accepted", CONTRACT,
  "                                \"addition only adds one error response\")\n"
  "        if not cid or cid in seen or cid in taken:",
  "                                \"addition only adds one error response\")\n"
  "        if not cid or cid in seen:"),
 ("L3 an addition without a decision accepted", CONTRACT,
  "        seen.add(cid)\n        if not entry.get(\"decision\"):\n"
  "            raise ContractError(f\"{cid}: names no decision\")\n"
  "        operation_id = entry.get(\"operation_id\")\n        op = by_operation",
  "        seen.add(cid)\n        if False:\n"
  "            raise ContractError(f\"{cid}: names no decision\")\n"
  "        operation_id = entry.get(\"operation_id\")\n        op = by_operation"),
 ("L4 any status accepted", CONTRACT,
  "re.fullmatch(r\"5[0-9]{2}\", status)", "re.fullmatch(r\"[0-9]{3}\", status)"),
 ("L5 a second addition of a pair accepted", CONTRACT,
  "        if (operation_id, status) in pairs:", "        if False:"),
 ("L6 a declared status re-added", CONTRACT,
  "        if status in declared:", "        if False:"),
 ("L7 stale frozen statuses accepted", CONTRACT,
  "        if sorted(str(s) for s in entry.get(\"frozen_statuses\") or ()) != declared:",
  "        if False:"),
 ("L8 a code of any form accepted", CONTRACT,
  "        if not (isinstance(code, str) and _CODE.match(code)):",
  "        if not isinstance(code, str):"),
 ("L9 a blank description accepted", CONTRACT,
  "        if not (isinstance(entry.get(\"description\"), str) and "
  "entry[\"description\"].strip()):",
  "        if not isinstance(entry.get(\"description\"), str):"),
 ("L10 the added response not a problem", CONTRACT,
  "        \"content\": {\"application/problem+json\": {\"schema\": {\"$ref\": _PROBLEM_REF}}},",
  "        \"content\": {\"application/json\": {\"schema\": {\"$ref\": _PROBLEM_REF}}},"),
]


def _check_anchors() -> None:
    """Each anchor names ONE site: the runner replaces every occurrence. Run
    before a run, never on import."""
    for name, rel, old, _new in MUTATIONS + LOADER_MUTATIONS:
        count = (ROOT / rel).read_text().count(old)
        assert count == 1, (name, count)
    labels = [m[0].split()[0] for m in MUTATIONS + LOADER_MUTATIONS]
    assert len(set(labels)) == len(labels)


if __name__ == "__main__":
    _check_anchors()
    only = tuple(sys.argv[1:])
    survivors = run("TURAB — Slice 7 step 3: the WhatsApp webhook", TESTS, MUTATIONS, only,
                    deselect=DESELECT)
    print()
    survivors += run("TURAB — Slice 7 step 3: CORRECTION-007 and CORRECTION-008, the "
                     "response_additions loader", CONTRACT_TESTS, LOADER_MUTATIONS, only)
    sys.exit(1 if survivors else 0)
