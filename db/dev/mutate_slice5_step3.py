"""Slice 5 step 3, APPROVED and the opportunity: which test refuses which weakening.

    .venv/bin/python db/dev/mutate_slice5_step3.py [G1 C1 ...] > /outside/the/tree.txt

Each mutation weakens ONE rule of step 3 (the review of 60b0152; plan
§3.3, §3.7, G5-2 (a), G5-5 (a)):
- G: the stored gates, named before the frozen trigger (H02);
- S: supersession per offer (G5-2);
- C: the currency check and its table (§3.7);
- L: the locks that make the checked facts the facts at commit;
- O: one open opportunity per request and canonical property (§3.3);
- N: the opportunity's content (G5-5 (a), mandatory test 4);
- W: what the stored why_real and known_differences may show (§3.4);
- X: the reasons reaching the response.

See `mutation_runner.py`.
"""
import sys

from mutation_runner import run

SVC = "src/turab/services/match_review.py"
CUR = "src/turab/services/currency.py"
RUN = "src/turab/api/routes/parties.py"
TESTS = "tests/test_slice5_step3.py"

OPEN_ALIASES = ("""           AND (property_id = :p
                OR property_id IN (SELECT alias_property_id
                                     FROM turab.property_identity_aliases
                                    WHERE canonical_property_id = :p))""")

MUTATIONS = [
    # --- G: the stored gates ----------------------------------------------------------
    ("G1 the gates are not checked", SVC,
     "    failing = _gates_not_pass(match)\n", "    failing = []\n"),
    ("G2 the permission gate is ignored", SVC,
     '"freshness_gate_status",\n          "permission_gate_status")',
     '"freshness_gate_status")'),
    ("G3 the eligibility is ignored", SVC,
     'failing = [] if match["eligibility"] == "ELIGIBLE" else [',
     'failing = [] if True else ['),
    # --- S: supersession --------------------------------------------------------------
    ("S1 supersession is not checked", SVC,
     "    newer = _superseded_by(session, match)\n", "    newer = None\n"),
    ("S2 supersession across offers", SVC,
     "           AND evaluated_offer_id IS NOT DISTINCT FROM :o\n", ""),
    # --- C: the currency check --------------------------------------------------------
    ("C1 the check is not enforced", SVC,
     "    if checked.currency.validity != currency.VALID:",
     "    if False:"),
    ("C2 NEEDS_CONFIRMATION is accepted", SVC,
     "    if checked.currency.validity != currency.VALID:",
     "    if checked.currency.validity == currency.INVALID:"),
    ("C3 a PAUSED request is VALID", CUR,
     '"PAUSED": NEEDS_CONFIRMATION, "CLOSED": INVALID',
     '"PAUSED": VALID, "CLOSED": INVALID'),
    ("C4 a value outside the table is VALID", CUR,
     "cls = classes.get(value, INVALID)", "cls = classes.get(value, VALID)"),
    ("C5 only the first failing fact is named", CUR,
     "        if cls != VALID:\n            reasons.append(",
     "        if cls != VALID and not reasons:\n            reasons.append("),
    ("C6 the identity is not read", CUR,
     '"IDENTITY": "ALIAS" if rows["alias"] else "CANONICAL",',
     '"IDENTITY": "CANONICAL",'),
    ("C7 the match's thresholds are not used", CUR,
     '    days = match["threshold_days"]\n',
     '    days = {"request": 100000, "property": 100000, "offer_terms": 100000}\n'),
    ("C8 the permission gate is not read", CUR,
     '        "PERMISSION": gate,\n', '        "PERMISSION": "PASS",\n'),
    ("C9 the worst class is not the validity", CUR,
     "        if RANK[cls] > RANK[worst]:", "        if RANK[cls] > RANK[worst] + 1:"),
    # --- L: the locks -----------------------------------------------------------------
    ("L1 the request is not locked", CUR,
     "FROM turab.requests WHERE request_id = :r FOR NO KEY UPDATE",
     "FROM turab.requests WHERE request_id = :r"),
    ("L2 the request lock is shared", CUR,
     "FROM turab.requests WHERE request_id = :r FOR NO KEY UPDATE",
     "FROM turab.requests WHERE request_id = :r FOR SHARE"),
    ("L3 the property is not locked", CUR,
     "FROM turab.properties WHERE property_id = :p FOR SHARE",
     "FROM turab.properties WHERE property_id = :p"),
    ("L4 the offer is not locked", CUR,
     "FROM turab.property_offers WHERE offer_id = :o FOR SHARE",
     "FROM turab.property_offers WHERE offer_id = :o"),
    ("L5 the bindings are not locked", CUR,
     "           FOR SHARE OF b, g", ""),
    # --- O: one open opportunity ------------------------------------------------------
    ("O1 the open opportunity is not checked", SVC,
     "    already = _open_opportunity(session, match)\n", "    already = None\n"),
    ("O2 an alias's opportunity is not counted", SVC, OPEN_ALIASES,
     "           AND property_id = :p"),
    ("O3 a closed opportunity is counted", SVC,
     "         WHERE request_id = :r AND status <> 'CLOSED'\n",
     "         WHERE request_id = :r\n"),
    ("O4 the index's refusal is not mapped", SVC,
     '        if name == "ux_one_open_opportunity_per_pair":',
     '        if False:'),
    # --- N: the opportunity's content -------------------------------------------------
    ("N1 the scope is not the offer's at approval", SVC,
     '             "scope": checked.sharing_scope,', '             "scope": "SUMMARY_ONLY",'),
    ("N2 the context is not the match's", SVC,
     "                   m.commercial_context_snapshot, CAST(:permission AS jsonb),",
     # Inside an f-string: the braces are doubled. The first run's form,
     # '{}', did not compile, and was reported as a survivor (first-run record).
     "                   '{{}}'::jsonb, CAST(:permission AS jsonb),"),
    ("N3 property-bound before offer-bound", CUR,
     'return (binding["bound_to"] != "OFFER", binding["bound_at"],',
     'return (binding["bound_to"] == "OFFER", binding["bound_at"],'),
    ("N4 no confirmation time", SVC,
     '"acct": reviewer_account_id, "as_of": checked.as_of}',
     '"acct": reviewer_account_id, "as_of": None}'),
    # --- W: what is shown -------------------------------------------------------------
    ("W1 the scope is ignored", SVC,
     "    shown = set(SHOWN_BY_SCOPE[scope])",
     '    shown = set(SHOWN_BY_SCOPE["PROPERTY_DETAILS_ALLOWED"])'),
    ("W2 the rule version is not checked", SVC,
     '''    eligible = [r for r in results if r["criterion_code"] in shown
                and (r["rule_id"], r["rule_version"]) == SHOWN_RULES[r["criterion_code"]]]''',
     '''    eligible = [r for r in results if r["criterion_code"] in shown]'''),
    ("W3 a blocking unknown is a difference", SVC,
     '(r["compatibility"] == "UNKNOWN" and not r["blocking"])',
     'r["compatibility"] == "UNKNOWN"'),
    ("W4 a FLEXIBLE pass is a reason", SVC,
     'if r["importance"] in ("REQUIRED", "PREFERRED") and r["compatibility"] == "PASS"]',
     'if r["compatibility"] == "PASS"]'),
    ("W5 an area is shown at SUMMARY_ONLY", SVC,
     '    "SUMMARY_ONLY": ("PROPERTY_TYPE",),',
     '    "SUMMARY_ONLY": ("PROPERTY_TYPE", "LAND_AREA_MIN"),'),
    # --- X: the reasons reach the response --------------------------------------------
    ("X1 the facts are not in the problem", RUN,
     '''trace, str(exc), **({"field_errors": field_errors} if field_errors else {}),''',
     "trace, str(exc),"),
]

if __name__ == "__main__":
    run("TURAB — Slice 5 step 3: which test refuses which weakening of APPROVED",
        TESTS, MUTATIONS, sys.argv[1:])
