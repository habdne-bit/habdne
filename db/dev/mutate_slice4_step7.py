"""Slice 4 step 7: which run decision, refusal or record fails which test.

    .venv/bin/python db/dev/mutate_slice4_step7.py [T1 W1 ...] > /outside/the/tree.txt

Each mutation reintroduces one defect:
- T: the transaction (condition 1: one Repeatable Read snapshot; the
  savepoint and the identical input of G4-13, condition 2);
- W: what is written (conditions 3 and 6; D1; D4);
- R: the refusals (D6, CORRECTION-004, G4-8) and their order;
- D: the diagnostic (D2, D3, D3b; condition 4);
- A: the next action (D5, `action.next@1`);
- B, C, E, P: the review of bf052f4 (the body, one key in two concurrent
  calls, exact numbers, the typed 500).

The test file is step 7's only.
"""
import sys

from mutation_runner import run

RUN = "src/turab/services/matching_run.py"
EXP = "src/turab/matching/explain.py"
G = "src/turab/matching/gates.py"
CMD = "src/turab/services/command.py"
SES = "src/turab/db/session.py"
ROUTE = "src/turab/api/routes/matching.py"
IDEM = "src/turab/services/idempotency.py"
EXACT = "src/turab/exact_json.py"

#: `CommandService.run`: the refusals (`prepare`), then the key claimed under a
#: savepoint. R3 swaps the two.
PREPARE = '            prepared = prepare(session) if prepare is not None else None\n'
CLAIM_BLOCK = (
    '            if use_idempotency:\n'
    '                # Two calls with one key can both find no record, then both\n'
    '                # claim it. The second INSERT waits for the first transaction\n'
    '                # and, once that commits, fails 23505. Under its own savepoint\n'
    '                # that failure leaves this transaction usable, and the record\n'
    '                # the first call committed is replayed, or refused if the body\n'
    '                # differs (API_CONTRACTS §2.3; review of bf052f4, R-S4-7-02).\n'
    '                try:\n'
    '                    with session.begin_nested():\n'
    '                        idempotency.claim(\n'
    '                            session,\n'
    '                            actor_account_id=self._subject.account_id,\n'
    '                            route_key=route_key,\n'
    '                            idempotency_key=self._idempotency_key,\n'
    '                            payload=payload,\n'
    '                            expired_record_id=expired,\n'
    '                        )\n'
    '                except IntegrityError as exc:\n'
    '                    if not idempotency.key_taken(exc):\n'
    '                        raise\n'
    '                    replay = idempotency.committed(\n'
    '                        session,\n'
    '                        actor_account_id=self._subject.account_id,\n'
    '                        route_key=route_key,\n'
    '                        idempotency_key=self._idempotency_key,\n'
    '                        payload=payload,\n'
    '                    )\n'
    '                    return CommandResult(replay.status, replay.body, replayed=True)\n'
)

MUTATIONS = [
 # --- T: the transaction --------------------------------------------------------------
 ("T1 the run accepts a Read Committed transaction", RUN,
  '    if isolation != "repeatable read":', "    if False:"),
 ("T2 the route asks for no isolation", ROUTE,
  'isolation="REPEATABLE READ")', "isolation=None)"),
 ("T3 the session ignores the isolation asked", SES,
  '            session.execute(text(f"SET TRANSACTION ISOLATION LEVEL {isolation}"))',
  "            pass"),
 ("T4 a unique violation is never taken for an identical input", RUN,
  '    return (getattr(orig, "sqlstate", None) == "23505"', "    return (False"),
 ("T5 any unique violation is taken for an identical input", RUN,
  '            and getattr(getattr(orig, "diag", None), "constraint_name", None) == IDENTICAL_INPUT)',
  "            )"),
 ("T6 the invisible row is read in the run's own snapshot", RUN,
  "    with session.get_bind().engine.connect() as fresh:\n"
  "        return fresh.execute(text(_EXISTING), key).scalar_one(), False",
  "    return session.execute(text(_EXISTING), key).scalar_one(), False"),
 ("T7 the evaluated offer left out of the hash", RUN,
  "            evaluated_offer_id=candidate.offer_id,", "            evaluated_offer_id=None,"),
 ("T8 the match's instant is not the run's", RUN,
  ":request_version, :property_version, :offer_version, :as_of,",
  ":request_version, :property_version, :offer_version, clock_timestamp(),"),
 # --- W: what is written --------------------------------------------------------------
 ("W1 ai_trace_ref filled", RUN, "'RULE_ENGINE', NULL)", "'RULE_ENGINE', 'trace')"),
 ("W2 the criterion rows not audited", RUN,
  '        audit_rows.write(session, "match_criterion_results", row_id, "INSERT", None,\n'
  '                         audit_rows.row_json(session, "match_criterion_results", row_id))\n',
  ""),
 ("W3 the diagnostic row not audited", RUN,
  '    audit_rows.write(session, "match_diagnostic_runs", diagnostic_id, "INSERT", None,\n'
  '                     audit_rows.row_json(session, "match_diagnostic_runs", diagnostic_id))\n',
  ""),
 ("W4 suggested actions written (D1)", RUN,
  "CAST(:summary AS jsonb), '[]'::jsonb, '[]'::jsonb)",
  "CAST(:summary AS jsonb), '[{}]'::jsonb, '[]'::jsonb)"),
 ("W5 the next action's version not recorded (condition 3)", EXP,
  '                   "next_action": "@".join(NEXT_ACTION)},', "                   },"),
 ("W6 the score's version not recorded (condition 3)", EXP,
  '                   "soft_score": score.engine,\n', ""),
 ("W7 the explanation cites the claim (D4)", EXP,
  '            "rule_explanation": dict(r.explanation)}',
  '            "rule_explanation": dict(r.explanation), "claim": r.evidence_claim_id}'),
 ("W8 the explanation carries the commercial snapshot (D4, R9.3)", RUN,
  "        explain.explanation(prepared.plan, hard, verdict, score, freshness, permission),\n",
  "        {**explain.explanation(prepared.plan, hard, verdict, score, freshness, permission),"
  ' "offer": snapshots.stored_form(offer)},\n'),
 ("W9 the response is computed, not read from the rows", RUN,
  "        if visible:\n            matches.append(match_view(session, match_id))",
  "        if visible:\n            matches.append({**match_view(session, match_id),"
  ' "input_hash": ""})'),
 # --- R: the refusals -----------------------------------------------------------------
 ("R1 the policy version not checked (CORRECTION-004)", RUN,
  "        policy.require_active_version(active, matching_policy_version)", "        pass"),
 ("R2 the refusals mapped to a generic 422", ROUTE,
  "extra_errors=(matching_run.RunRefused, matching_run.RequestMissing),",
  "extra_errors=(matching_run.RequestMissing,),"),
 ("R3 the key claimed before the refusals are decided", CMD,
  PREPARE + "\n" + CLAIM_BLOCK, CLAIM_BLOCK + "\n" + PREPARE),
 ("R4 the refusals decided before the replay lookup", CMD,
  "            if use_idempotency:\n"
  "                replay, expired = idempotency.lookup(",
  "            prepared = prepare(session) if prepare is not None else None\n"
  "            if use_idempotency:\n"
  "                replay, expired = idempotency.lookup("),
 ("R5 the request checked before the version", RUN,
  "    try:\n"
  "        policy.require_active_version(active, matching_policy_version)",
  "    candidates.candidate_set(session, request_id, property_ids)\n"
  "    try:\n"
  "        policy.require_active_version(active, matching_policy_version)"),
 # --- D: the diagnostic ---------------------------------------------------------------
 ("D1 a near match may have a REQUIRED UNKNOWN (D2)", EXP,
  '            and required.count("UNKNOWN") == 0)', "            )"),
 ("D2 a near match may have several FAILs (D2)", EXP,
  'required.count("FAIL") == 1', 'required.count("FAIL") >= 1'),
 ("D3 the actionable count read from the information gate", EXP,
  '        if verdict.eligibility == "NEED_MORE_INFORMATION":',
  '        if verdict.information_gate_status != "PASS":'),
 ("D4 a candidate counted once per reason, not per key (D3b)", EXP,
  "            if (key,) not in seen:", "            if True:"),
 ("D5 a null code keyed by its gate alone (D3b)", EXP,
  "    return code if code is not None else f\"{reason['gate']}:{reason['basis']}\"",
  "    return code if code is not None else reason[\"gate\"]"),
 ("D6 the exclusions not listed (G4-8)", EXP,
  '    exclusions = [{"property_id": e.property_id, "reason": e.reason.value,\n'
  '                   "detail": dict(e.detail)} for e in excluded]',
  "    exclusions = []"),
 ("D7 PERMISSION_MISSING worded from its seeded label (condition 4)", EXP,
  '        out["wording"] = PERMISSION_WORDING[reason["basis"]]',
  '        out["wording"] = "Permission scope insufficient"'),
 ("D8 the summary carries no wording for the permission basis", EXP,
  '            if reason["gate"] == "PERMISSION":\n'
  '                entry.setdefault("wording", {})[reason["basis"]] = (\n'
  '                    PERMISSION_WORDING[reason["basis"]])\n', ""),
 # --- A: the next action --------------------------------------------------------------
 ("A1 a next action for REJECTED", G,
  '    if eligibility in ("ELIGIBLE", "REJECTED"):', '    if eligibility == "ELIGIBLE":'),
 ("A2 no tie-break: REQUIRED not first", G,
  '        ranked = sorted(information, key=lambda u: 0 if u["importance"] == "REQUIRED" else 1)',
  "        ranked = list(information)"),
 ("A3 an information action at NORMAL priority", G,
  '        return {"type": kind, "priority": "HIGH",', '        return {"type": kind, "priority": "NORMAL",'),
 ("A4 the offer reconfirmed before the request", G,
  '    for subject, entity, kind in (("REQUEST", "REQUEST", "RECONFIRM_REQUEST"),\n'
  '                                  ("PROPERTY", "PROPERTY", "RECONFIRM_PROPERTY"),\n'
  '                                  ("OFFER", "PROPERTY_OFFER", "CONFIRM_PRICE")):',
  '    for subject, entity, kind in (("OFFER", "PROPERTY_OFFER", "CONFIRM_PRICE"),\n'
  '                                  ("REQUEST", "REQUEST", "RECONFIRM_REQUEST"),\n'
  '                                  ("PROPERTY", "PROPERTY", "RECONFIRM_PROPERTY")):'),
 ("A5 permission before reconfirmation", G,
  "        for reason in freshness_reasons:\n            if reason[\"subject\"] == subject:",
  "        for reason in []:\n            if reason[\"subject\"] == subject:"),
 ("A6 every unknown on the property", G,
  '            entity = "REQUEST"\n        elif', '            entity = "PROPERTY"\n        elif'),
 ("A7 a budget unknown typed OTHER", G,
  '"BUDGET_MAX": "CONFIRM_PRICE"}.get(', '"BUDGET_MAX": "OTHER"}.get('),
 ("A8 an information action for any unknown, actionable or not", EXP,
  "                   for r in hard.results if (r.criterion_code, r.ordinal) in actionable]",
  '                   for r in hard.results if r.compatibility == "UNKNOWN"]'),
 # --- review of bf052f4 ---------------------------------------------------------------
 # B: the body (R-S4-7-01)
 ("B1 property_ids: null accepted", ROUTE, "        if value is None:", "        if False:"),
 ("B2 the body closed", ROUTE, 'model_config = ConfigDict(extra="allow")',
  'model_config = ConfigDict(extra="forbid")'),
 ("B3 an undeclared field dropped before the idempotency hash", ROUTE,
  'model_config = ConfigDict(extra="allow")', 'model_config = ConfigDict(extra="ignore")'),
 # C: one key in two concurrent calls (R-S4-7-02)
 ("C1 a taken key not handled", CMD, "                    if not idempotency.key_taken(exc):",
  "                    if True:"),
 ("C2 the competitor's record read in this snapshot", IDEM,
  "    with session.get_bind().engine.connect() as fresh:\n"
  "        replay, _ = lookup(fresh,",
  "    if True:\n        fresh = session\n        replay, _ = lookup(fresh,"),
 ("C3 another body under the same key replayed", IDEM,
  '    if existing["request_hash"] != request_hash:\n        raise IdempotencyKeyConflict(route_key, key)',
  '    if False:\n        raise IdempotencyKeyConflict(route_key, key)'),
 # E: exact numbers (R-S4-7-03)
 ("E1 stored numbers read as floats", EXACT, "    return json.loads(text, parse_float=Decimal)",
  "    return json.loads(text)"),
 ("E2 a Decimal written through a float", EXACT, "        out.append(str(value))\n",
  "        out.append(json.dumps(float(value)))\n"),
 ("E3 a replayed body read as floats", IDEM,
  "        body=None if body is None else exact_json.loads(body),",
  "        body=None if body is None else json.loads(body),"),
 # P: the typed 500 (decided in the review of bf052f4)
 ("P1 a policy fault left untyped", RUN,
  "    except (freshness.NoActiveFreshnessPolicy, policy.PolicyNotImplemented) as exc:",
  "    except () as exc:"),
]

if __name__ == "__main__":
    run("TURAB — Slice 4 step 7: which run decision, refusal or record fails which test",
        "tests/test_slice4_step7.py", MUTATIONS, sys.argv[1:])
