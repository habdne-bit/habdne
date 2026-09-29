"""Slice 4 step 5: which freshness, permission or eligibility decision fails which test.

    .venv/bin/python db/dev/mutate_slice4_step5.py [F1 P1 ...] > /outside/the/tree.txt

Each mutation reintroduces one defect:
- F: a freshness state or clock (G4-11);
- P: a binding's state or which bindings are read (G4-10);
- E: a gate, the eligibility precedence (G4-11), or a reason dropped
  (the condition of the review of f789a59).

The test file is step 5's only.
"""
import sys

from mutation_runner import run

S = "src/turab/matching/snapshots.py"
E = "src/turab/matching/eligibility.py"

MUTATIONS = [
 # --- freshness (G4-11) ------------------------------------------------------------------
 ("F1 stale AT the threshold, not past it", S,
  "    stale = as_of - last > timedelta(days=days)",
  "    stale = as_of - last >= timedelta(days=days)"),
 ("F2 never confirmed taken as FRESH", S,
  '        return {"state": "UNKNOWN", "basis": "NEVER_CONFIRMED", "confirmed_at": None}',
  '        return {"state": "FRESH", "basis": "NEVER_CONFIRMED", "confirmed_at": None}'),
 ("F3 the offer judged on last_confirmed_at, not its terms", S,
  '_state(offer["commercial_terms_last_confirmed_at"]', '_state(offer["last_confirmed_at"]'),
 ("F4 the offer judged on the property's threshold", S,
  '                  _state(offer["commercial_terms_last_confirmed_at"], days["offer_terms"],',
  '                  _state(offer["commercial_terms_last_confirmed_at"], days["property"],'),
 ("F5 no evaluated offer taken as FRESH", S,
  '        "offer": ({"state": "NOT_APPLICABLE", "basis": "NO_EVALUATED_OFFER",',
  '        "offer": ({"state": "FRESH", "basis": "NO_EVALUATED_OFFER",'),
 ("F6 the instant written into the snapshot (G4-13)", S,
  '        "policy_version": policy_version,\n        "threshold_days": days,',
  '        "policy_version": policy_version,\n        "as_of": as_of,\n'
  '        "threshold_days": days,'),
 ("F7 a naive instant accepted", S,
  "    if not isinstance(as_of, datetime) or as_of.tzinfo is None or as_of.utcoffset() is None:",
  "    if False:"),
 # --- permission (G4-10) -----------------------------------------------------------------
 ("P1 another party's consent counts", S,
  '    if str(b["grant_party_id"]) != str(offer_party_id):', "    if False:"),
 ("P2 a grant whose scope changed counts", S,
  '    if b["grant_scope"] != b["purpose"]:', "    if False:"),
 ("P3 a revoked binding counts", S,
  '    if (b["binding_revoked_at"] is not None or b["grant_status"] != "GRANTED"',
  '    if (False or b["grant_status"] != "GRANTED"'),
 ("P4 a REVOKED grant counts", S,
  'or b["grant_status"] != "GRANTED"\n', 'or False\n'),
 ("P5 a grant with a revocation date counts", S,
  '            or b["grant_revoked_at"] is not None):', "            ):"),
 ("P6 a binding not yet started counts", S,
  '    if _instant(b["bound_at"]) > as_of or _instant(b["granted_at"]) > as_of:',
  "    if False:"),
 ("P7 a grant not yet started counts", S,
  '    if _instant(b["bound_at"]) > as_of or _instant(b["granted_at"]) > as_of:',
  '    if _instant(b["bound_at"]) > as_of:'),
 ("P8 bindings on the property are not read", S,
  "             WHERE (b.offer_id = :o OR b.property_id = :p)",
  "             WHERE (b.offer_id = :o)"),
 ("P9 PUBLIC_LISTING_ALLOWED does not count (G4-10 decision)", S,
  'MATCHING_PURPOSES = ("PRIVATE_MATCHING_ONLY", "PUBLIC_LISTING_ALLOWED")',
  'MATCHING_PURPOSES = ("PRIVATE_MATCHING_ONLY",)'),
 ("P10 every purpose counts", S,
  "               AND b.purpose::text = ANY(:purposes)\n", ""),
 # --- gates and eligibility --------------------------------------------------------------
 ("E1 bindings that do not count are counted", E,
  'NOT_COUNTED = ("OTHER_PARTY", "SCOPE_MISMATCH")', "NOT_COUNTED = ()"),
 ("E2 one revoked binding fails the gate", E,
  '    if counted and all(b["state"] == "REVOKED" for b in counted):',
  '    if any(b["state"] == "REVOKED" for b in counted):'),
 ("E3 STALE does not fail the freshness gate", E,
  '    if any(state == "STALE" for state in states.values()):', "    if False:"),
 ("E4 UNKNOWN freshness passes", E,
  '    elif all(state in ("FRESH", "NOT_APPLICABLE") for state in states.values()):',
  '    elif all(state in ("FRESH", "NOT_APPLICABLE", "UNKNOWN") for state in states.values()):'),
 ("E5 a hard FAIL is not REJECTED", E,
  '    if hard.hard_gate_status == "FAIL":', "    if False:"),
 ("E6 a blocking unknown is not NEED_MORE_INFORMATION", E,
  '    elif hard.information_gate_status != "PASS":', "    elif False:"),
 ("E7 only a REQUIRED unknown is NEED_MORE_INFORMATION", E,
  '    elif hard.information_gate_status != "PASS":', '    elif hard.hard_gate_status == "UNKNOWN":'),
 ("E8 permission ignored by eligibility", E,
  '    elif fresh_status != "PASS" or perm_status != "PASS":', '    elif fresh_status != "PASS":'),
 ("E9 freshness ignored by eligibility", E,
  '    elif fresh_status != "PASS" or perm_status != "PASS":', '    elif perm_status != "PASS":'),
 ("E10 the permission reason dropped (the review's condition)", E,
  "    reasons += fresh_reasons + perm_reasons", "    reasons += fresh_reasons"),
 ("E11 the freshness reasons dropped", E,
  "    reasons += fresh_reasons + perm_reasons", "    reasons += perm_reasons"),
 ("E12 request and property stale codes swapped", E,
  'FRESHNESS_SUBJECTS = (("request", "REQUEST_STALE"), ("property", "PROPERTY_STALE"),',
  'FRESHNESS_SUBJECTS = (("request", "PROPERTY_STALE"), ("property", "REQUEST_STALE"),'),
 ("E13 a binding not yet started reported as none", E,
  '"basis": "NO_CURRENT_BINDING" if not counted else "NOT_STARTED",',
  '"basis": "NO_CURRENT_BINDING",'),
 ("E14 the next action dropped", E,
  ',\n                        "next_action": "CONFIRM_PERMISSION"}]', "}]"),
 ("E15 the hard gate's reasons dropped", E,
  "               for code, ordinal in hard.required_failures]",
  "               for code, ordinal in ()]"),
]

if __name__ == "__main__":
    run("TURAB — Slice 4 step 5: which freshness, permission or eligibility decision fails "
        "which test", "tests/test_slice4_step5.py", MUTATIONS, sys.argv[1:])
