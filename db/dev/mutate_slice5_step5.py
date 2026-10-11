"""Slice 5 step 5, the opportunity commands and queue: which test refuses which weakening.

    .venv/bin/python db/dev/mutate_slice5_step5.py [R1 S1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule of step 5 (plan §3.7, G5-8, G5-9, G5-10,
G5-11 (a), G5-12 B10):
- R: revalidate, the one writer of validity (R7 is B10's proof 3: an
  injected `current_offer_id` update);
- S: share, the check that never persists (S6 and S7 are G5-8 (iii),
  decided (a) in the review of 6c6e614);
- W: R-S5-5-01, the share's lock that serializes a binding being created
  (review of 6c6e614);
- I: G5-8 (i), the share's interaction (decided (a) in the review of
  6c6e614);
- C: close, the eight reasons and the final state;
- L: the lock on the opportunity, and who may act;
- Q: the opportunity queue's membership, priority, reason, order and audit.

See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

COMMANDS = "src/turab/services/opportunity_commands.py"
VIEWS = "src/turab/services/opportunity_views.py"
ACCESS = "src/turab/services/access.py"
ROUTES = "src/turab/api/routes/matching.py"
CURRENCY = "src/turab/services/currency.py"
AUDIT = "src/turab/services/audit_rows.py"
TESTS = "tests/test_slice5_step5.py"

CONFIRMED = ("               last_confirmed_at = CASE WHEN CAST(:v AS text) = 'VALID' THEN :at\n"
             "                                        ELSE last_confirmed_at END,\n")
BINDING = "               current_permission_binding_id = :binding\n"
SWITCH = ("               current_permission_binding_id = :binding,\n"
          "               current_offer_id = COALESCE((\n"
          "                   SELECT p.offer_id FROM turab.property_offers p\n"
          "                    WHERE p.property_id = turab.opportunities.property_id\n"
          "                      AND p.status = 'ACTIVE'\n"
          "                      AND p.offer_id <> turab.opportunities.current_offer_id\n"
          "                    ORDER BY p.offer_id LIMIT 1), current_offer_id)\n")
QUEUE_AUDIT = ('''        self.record_list_access(
            operation_id=operation_id, resource_kind=OPPORTUNITY_KIND,
            result_count=len(items),
            query_shape={"membership": "G5-11 (a)", "excluded_status": ["CLOSED"]})
''')

MUTATIONS = [
    # --- R: revalidate ----------------------------------------------------------------
    ("R1 revalidate stores no validity", COMMANDS,
     "           SET validity_status = CAST(:v AS turab.opportunity_validity),\n",
     "           SET validity_status = validity_status,\n"),
    ("R2 a check that is not VALID confirms", COMMANDS, CONFIRMED,
     "               last_confirmed_at = :at,\n"),
    ("R3 a VALID check does not confirm", COMMANDS, CONFIRMED,
     "               last_confirmed_at = last_confirmed_at,\n"),
    ("R4 the current binding is not recorded", COMMANDS, BINDING,
     "               current_permission_binding_id = current_permission_binding_id\n"),
    ("R5 the reasons are not in the response", COMMANDS,
     '    return {**view, "validity_reasons": reasons_of(checked)}',
     '    return {**view, "validity_reasons": []}'),
    ("R6 revalidate moves no activity", COMMANDS,
     "               last_activity_at = :at,\n               last_confirmed_at",
     "               last_activity_at = last_activity_at,\n               last_confirmed_at"),
    ("R7 revalidate switches the offer (B10)", COMMANDS, BINDING, SWITCH),
    # --- S: share ---------------------------------------------------------------------
    ("S1 the recorded validity is ignored", COMMANDS,
     '    if opportunity["validity_status"] != currency.VALID:\n',
     "    if False:\n"),
    ("S2 the check now is ignored", COMMANDS,
     "    if checked.currency.validity != currency.VALID:\n", "    if False:\n"),
    ("S3 a revoked consent is answered as not valid", COMMANDS,
     '"CONSENT_REVOKED" if revoked else "OPPORTUNITY_NOT_VALID"', '"OPPORTUNITY_NOT_VALID"'),
    ("S4 a narrowed scope is ignored", COMMANDS,
     '    if SCOPE_RANK[checked.sharing_scope] < SCOPE_RANK[opportunity["sharing_scope"]]:\n',
     "    if False:\n"),
    ("S5 the scope is compared the wrong way", COMMANDS,
     '    if SCOPE_RANK[checked.sharing_scope] < SCOPE_RANK[opportunity["sharing_scope"]]:\n',
     '    if SCOPE_RANK[checked.sharing_scope] != SCOPE_RANK[opportunity["sharing_scope"]]:\n'),
    ("S6 contact before sharing is ignored", COMMANDS,
     "    if contact:\n", "    if False:\n"),
    ("S7 a revoked contact binding still refuses", COMMANDS,
     'party, checked.as_of) == "CURRENT":', 'party, checked.as_of) != "OTHER_PARTY":'),
    ("S8 share persists the check", COMMANDS,
     "               shared_at = CASE WHEN status = 'NEW' THEN :at ELSE shared_at END,\n",
     "               shared_at = CASE WHEN status = 'NEW' THEN :at ELSE shared_at END,\n"
     "               last_confirmed_at = :at,\n"),
    ("S9 a later share moves no activity", COMMANDS,
     "               last_activity_at = :at\n         WHERE opportunity_id = :o\"\"\",\n"
     "        {\"at\": prepared.checked.as_of",
     "               last_activity_at = CASE WHEN status = 'NEW' THEN :at "
     "ELSE last_activity_at END\n         WHERE opportunity_id = :o\"\"\",\n"
     "        {\"at\": prepared.checked.as_of"),
    ("S10 share never moves NEW to SHARED", COMMANDS,
     "           SET status = CASE WHEN status = 'NEW' THEN 'SHARED'::turab.opportunity_status\n"
     "                             ELSE status END,\n"
     "               shared_at = CASE WHEN status = 'NEW' THEN :at ELSE shared_at END,\n",
     "           SET status = status,\n"),
    # --- W: R-S5-5-01, the share's lock (review of 6c6e614) ----------------------------
    ("W1 the share takes the shared lock", COMMANDS,
     "                             clock=clock, exclusive=True)",
     "                             clock=clock)"),
    ("W2 the exclusive lock does not conflict with FOR KEY SHARE", CURRENCY,
     '    mode = "FOR UPDATE" if exclusive else "FOR SHARE"',
     '    mode = "FOR NO KEY UPDATE" if exclusive else "FOR SHARE"'),
    ("W3 the share locks the offer only", CURRENCY,
     'FROM turab.properties WHERE property_id = :p """ + mode)',
     'FROM turab.properties WHERE property_id = :p FOR SHARE""")'),
    ("W4 the share locks the property only", CURRENCY,
     'FROM turab.property_offers WHERE offer_id = :o """ + mode)',
     'FROM turab.property_offers WHERE offer_id = :o FOR SHARE""")'),
    # --- I: G5-8 (i), the share's interaction (review of 6c6e614) ----------------------
    ("I1 the share writes no interaction", COMMANDS,
     "    _record_share(session, prepared, view, channel=channel, note=note,\n"
     "                  operator_account_id=operator_account_id)\n", ""),
    ("I2 the note is not kept", COMMANDS,
     "               :o, :note, :at, :operator,", "               :o, NULL, :at, :operator,"),
    ("I3 the channel is not kept", COMMANDS,
     "        SELECT 'STATUS_CHANGE', CAST(:channel AS turab.communication_channel), r.party_id,",
     "        SELECT 'STATUS_CHANGE', NULL, r.party_id,"),
    ("I4 the operator is not kept", COMMANDS,
     "               :o, :note, :at, :operator,", "               :o, :note, :at, NULL,"),
    ("I5 the audit row carries the note", AUDIT,
     '    "interactions": ("summary",),\n', ""),
    ("I6 the interaction is not audited", COMMANDS,
     '    audit_rows.write(session, "interactions", interaction_id, "INSERT", None,\n'
     '                     audit_rows.row_json(session, "interactions", interaction_id))',
     "    pass"),
    ("I7 the status before is not recorded", COMMANDS,
     '"status_before": prepared.opportunity["status"],',
     '"status_before": view["status"],'),
    # --- C: close ---------------------------------------------------------------------
    ("C1 any reason closes", COMMANDS, "    if reason_code not in CLOSE_REASONS:\n",
     "    if False:\n"),
    ("C2 a reason of another category is admitted", COMMANDS,
     '"DUPLICATE_OPPORTUNITY_CONSOLIDATED", "OTHER")',
     '"DUPLICATE_OPPORTUNITY_CONSOLIDATED", "OTHER", "CONSENT_REVOKED")'),
    ("C3 close moves no activity", COMMANDS, "               last_activity_at = c.at\n",
     "               last_activity_at = last_activity_at\n"),
    ("C4 CLOSED is not final", COMMANDS,
     '    if row["status"] == "CLOSED":\n', '    if False:\n'),
    # --- L: the lock and who may act --------------------------------------------------
    ("L1 the opportunity is read without a lock", COMMANDS,
     'WHERE opportunity_id = :o FOR UPDATE"""', 'WHERE opportunity_id = :o"""'),
    ("L2 an unknown opportunity is not recorded (share)", ROUTES,
     "                     command.authorize_staff_only(SHARE, \"sharing is a staff action\"),\n"
     "                     command.authorize_opportunity_exists(opportunity_id, SHARE)):",
     "                     command.authorize_staff_only(SHARE, \"sharing is a staff action\")):"),
    # --- Q: the opportunity queue -----------------------------------------------------
    ("Q1 a CLOSED opportunity is queued", VIEWS,
     "     WHERE status <> 'CLOSED'\n       AND (validity_status <> 'VALID' OR status = 'NEW')\n",
     "     WHERE (validity_status <> 'VALID' OR status = 'NEW')\n"),
    ("Q2 a shared VALID opportunity is queued", VIEWS,
     "       AND (validity_status <> 'VALID' OR status = 'NEW')\n", ""),
    ("Q3 a NEW VALID opportunity is not queued", VIEWS,
     "       AND (validity_status <> 'VALID' OR status = 'NEW')\n",
     "       AND validity_status <> 'VALID'\n"),
    ("Q4 a time-based condition joins the queue", VIEWS,
     "       AND (validity_status <> 'VALID' OR status = 'NEW')\n",
     "       AND (validity_status <> 'VALID' OR status = 'NEW'\n"
     "            OR last_confirmed_at < now() - interval '14 days')\n"),
    ("Q5 INVALID is NORMAL", VIEWS,
     '    "INVALID": ("HIGH", "VALIDITY_INVALID"),',
     '    "INVALID": ("NORMAL", "VALIDITY_INVALID"),'),
    ("Q6 an unshared opportunity is named by its status first", VIEWS,
     '''    case = (row["validity_status"] if row["validity_status"] != "VALID"
            else "NOT_YET_SHARED")''',
     '''    case = ("NOT_YET_SHARED" if row["status"] == "NEW"
            else row["validity_status"])'''),
    ("Q7 the order ignores the priority", VIEWS,
     "    items.sort(key=lambda pair: (PRIORITY_ORDER[pair[0][\"priority\"]],\n"
     "                                 pair[1][\"created_at\"], str(pair[1][\"opportunity_id\"])))",
     "    items.sort(key=lambda pair: (pair[1][\"created_at\"], "
     "str(pair[1][\"opportunity_id\"])))"),
    ("Q8 the queue is not audited", ACCESS, QUEUE_AUDIT, ""),
]

if __name__ == "__main__":
    run("TURAB — Slice 5 step 5: which test refuses which weakening of the opportunity "
        "commands and queue", TESTS, MUTATIONS, sys.argv[1:])
