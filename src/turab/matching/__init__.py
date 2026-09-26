"""Slice 4 — the deterministic matching core.

Built step by step, under the decisions recorded in `docs/gate/SLICE_4_PLAN.md`.
What exists so far (steps 2 and 3):

- `canonical`: the canonical JSON form and the input hash (G4-13);
- `registry`: the rule registry, keyed by (rule_id, rule_version), with
  append-only source pins (G4-2);
- `policy`: the active-policy loader, which fails closed, and the
  policy-version rule of CORRECTION-004;
- `snapshots`: the request, property and commercial-context snapshots
  (`API_CONTRACTS_v0.2` §6);
- `candidates`: the candidate set and its reported exclusions (G4-8,
  G4-9 (a)).

Nothing here writes. No gate is evaluated and no match row is inserted:
those are steps 4 to 7, and each waits on its own decisions.
"""
