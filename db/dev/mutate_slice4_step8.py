"""Slice 4 step 8: which read, proof or comparison fails which test.

    .venv/bin/python db/dev/mutate_slice4_step8.py [X1 G1 ...] > /outside/the/tree.txt

Each mutation reintroduces one defect:
- X: reconstruction (STOP GATE D, proof 1) loses a derivation or a comparison;
- Y: replay (proof 2) loses a comparison;
- G: the two staff reads (recording, order, the never-run case, exact numbers);
- X8, X9: the review of c657bd9 (R-S4-8-01): the states re-derived;
- Y5–Y9, R1: G4-19 (a): the digest a match was evaluated under.

The test file is step 8's only.
"""
import sys

from mutation_runner import run

REC = "src/turab/matching/reconstruct.py"
ACC = "src/turab/services/access.py"
ROUTE = "src/turab/api/routes/matching.py"
RUN = "src/turab/services/matching_run.py"

MUTATIONS = [
 # --- X: reconstruction ----------------------------------------------------------------
 ("X1 blocking copied from the row, not derived", REC,
  '            blocking=blocking(r["importance"], r["compatibility"],\n'
  '                              flagged.get(str(rcid), False) if rcid is not None else False),',
  '            blocking=r["blocking"],'),
 ("X2 eligibility not compared", REC,
  'GATE_FIELDS = ("eligibility", "hard_gate_status",', 'GATE_FIELDS = ("hard_gate_status",'),
 ("X3 the reasons not compared", REC,
  '    if _without_wording(explanation["reasons"]) != snapshots.stored_form(verdict["reasons"]):',
  "    if False:"),
 ("X4 the soft score not compared", REC,
  '    if (score["soft_score"] is None) != (stored_score is None) or (',
  "    if False and ("),
 ("X5 the next action not compared", REC,
  '    if snapshots.stored_form(action) != match["next_action"]:', "    if False:"),
 ("X6 blocking_if_unknown ignored", REC,
  '    flagged = {str(c["request_criterion_id"]): bool(c["blocking_if_unknown"])',
  '    flagged = {str(c["request_criterion_id"]): False'),
 ("X7 the column target left out of the soft score", REC,
  '    if request.get("budget_target_dzd") is not None:', "    if False:"),
 # --- Y: replay ------------------------------------------------------------------------
 ("Y1 compatibility not compared", REC,
  '        for field in ("compatibility", "property_value", "delta", "evidence_level",',
  '        for field in ("property_value", "delta", "evidence_level",'),
 ("Y2 the input hash not compared", REC,
  '    if recomputed != match["input_hash"]:', "    if False:"),
 ("Y3 the rule's explanation not compared", REC,
  '        if out["explanation"] != stored[key]["rule_explanation"]:', "        if False:"),
 ("Y4 the rule run on the property snapshot of no one", REC,
  "                                    .evaluate(criterion, request, prop, offer))",
  "                                    .evaluate(criterion, request, {}, offer))"),
 # --- G: the staff reads ---------------------------------------------------------------
 ("G1 a match read not recorded", ACC,
  "        self._auditor.read(subject=self._subject, operation_id=operation_id,\n"
  "                           trace_id=self._trace_id, resource_kind=MATCH_KIND,\n"
  "                           resource_id=match_id)\n", ""),
 ("G2 an unknown match's denial not recorded", ACC,
  "                resource_kind=MATCH_KIND, resource_id=match_id)\n"
  "            return AccessDenied(DenyReason.OBJECT_NOT_AUTHORIZED)",
  "                resource_kind=MATCH_KIND, resource_id=match_id) if False else None\n"
  "            return AccessDenied(DenyReason.OBJECT_NOT_AUTHORIZED)"),
 ("G3 the earliest diagnostic read as the latest", ACC,
  "             ORDER BY run_at DESC, diagnostic_run_id DESC LIMIT 1",
  "             ORDER BY run_at ASC, diagnostic_run_id ASC LIMIT 1"),
 ("G4 a diagnostic read not recorded", ACC,
  "        self._auditor.read(subject=self._subject, operation_id=operation_id,\n"
  "                           trace_id=self._trace_id, resource_kind=DIAGNOSTIC_KIND,\n"
  "                           resource_id=row[\"diagnostic_run_id\"])\n", ""),
 ("G5 a request never run is not a 404", ROUTE,
  "    if result is None:\n        return coded(ProblemCode.NOT_FOUND,",
  "    if result is None:\n        return ExactJSONResponse(content={}) or coded(ProblemCode.NOT_FOUND,"),
 # --- review of c657bd9: R-S4-8-01 (states re-derived) ---------------------------------
 ("X8 freshness states read, not re-derived", REC,
  "            again = snapshots.stored_form(state(match[source][field],\n"
  "                                                int(stored[\"threshold_days\"][key]), as_of))",
  "            again = stored[subject]"),
 ("X9 binding states read, not re-derived", REC,
  '        again = state(b, stored["offer_party_id"], as_of)', '        again = b["state"]'),
 # --- G4-19 (a): the digest each match was evaluated under ------------------------------
 ("Y5 a format-2 row without its digest replayed with the current one", REC,
  '            return None, "a format-2 match records no registry digest"',
  "            return REGISTRY.digest(), None"),
 ("Y6 an unknown format replayed with the current digest", REC,
  '    return None, f"no registry digest is attributed to explanation format {fmt!r}"',
  "    return REGISTRY.digest(), None"),
 ("Y7 a recorded digest accepted outside the history", REC,
  "        if not registry_history.known(digest):", "        if False:"),
 ("Y8 format 1 replayed with the current digest", REC,
  "        return registry_history.FORMAT_DIGESTS[fmt], None", "        return REGISTRY.digest(), None"),
 ("Y9 a format-2 row replayed with the current digest", REC,
  "        return digest, None", "        return REGISTRY.digest(), None"),
 ("R1 the explanation records another digest than the hash used", RUN,
  "                            prepared.registry_digest),", '                            "0" * 64),'),
 ("G6 a match returned through floats", ACC,
  "        return match_view(self._session, match_id)",
  "        import json as _j\n        from .. import exact_json as _e\n"
  "        return _j.loads(_e.dumps(match_view(self._session, match_id)))"),
]

if __name__ == "__main__":
    run("TURAB — Slice 4 step 8: which read, proof or comparison fails which test",
        "tests/test_slice4_step8.py", MUTATIONS, sys.argv[1:])
