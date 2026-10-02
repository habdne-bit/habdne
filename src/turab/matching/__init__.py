"""Slice 4 — the deterministic matching core.

Built step by step, under the decisions recorded in `docs/gate/SLICE_4_PLAN.md`.
What exists so far (steps 2 to 6):

- `canonical`: the canonical JSON form and the input hash (G4-13);
- `registry`: the rule registry, keyed by (rule_id, rule_version), with
  append-only source pins (G4-2);
- `policy`: the active-policy loader, which fails closed, and the
  policy-version rule of CORRECTION-004;
- `snapshots`: the request, property and commercial-context snapshots
  (`API_CONTRACTS_v0.2` §6);
- `candidates`: the candidate set and its reported exclusions (G4-8,
  G4-9 (a));
- `criteria`: the criteria a request yields, and the input a run refuses
  (G4-3 (b), G4-5R, G4-7);
- `rules`: the registered criterion rules (G4-4 to G4-7; G4-5 for SALE);
- `hard_gate`: blocking (G4-4), the hard gate and the information gate;
- `eligibility`: the freshness and permission gates, and eligibility
  (G4-10, G4-11), with every reason kept;
- `gates`: the pinned functions behind freshness, permission, eligibility
  and the soft score (review of a5ea6f5);
- `soft`: the soft score (G4-12).

Nothing here writes. No match row is inserted. The run (step 7) waits on its
own decision (G4-15).
"""
