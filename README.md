# تُراب — TURAB

> منصة عقارية محلية تبدأ من حاجة المشتري، وتنظم العرض المتاح وغير المعلن،
> وتطابق بينهما للوصول إلى فرصة عقارية حقيقية.

## Project status

| Gate | Status |
|---|---|
| Static architecture audit | PASS |
| **PostgreSQL 16+ Execution Gate** | **PASS** (database baseline at v0.2.1) |
| Slice 0 — Application Skeleton + Security Boundaries | Unblocked, not yet started |

Full run results, including the one blocker found and corrected, are in
**[`docs/gate/GATE_RUN_REPORT.md`](docs/gate/GATE_RUN_REPORT.md)**.

The Pre-Slice Gate of
`docs/handoff/00_START_HERE/TURAB_Developer_Handoff_Master_v1.0.md` §10 is
satisfied. Slices follow `06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md` in
order; no advanced AI work begins before the Core Hypothesis Stop Gate passes.

## Layout

| Path | Contents |
|---|---|
| `docs/handoff/` | The Developer Handoff v1.0 package — the authority baseline. Read `docs/handoff/README.md` first. Database schema is at patch revision v0.2.1; every other artifact is as shipped. |
| `docs/gate/` | Execution gate run reports |
| `db/gate/` | Gate harness: contract tests, runner, OpenAPI lint |
| `.github/workflows/` | CI — rebuilds a clean database from zero on every push |

Authority order when two documents disagree is fixed by
`docs/handoff/00_START_HERE/FILE_AUTHORITY_AND_VERSION_POLICY.md`. Contradictions
are never resolved silently in code — implementation stops at the affected point
and a decision is raised.

## Running the gate

```bash
db/gate/run_gate.sh      # requires PostgreSQL 16+, standard PG* env vars
```

The runner verifies package integrity, runs the static audit, rebuilds a clean
database, applies the schema, applies the seed twice for idempotency, runs the
database-level contract tests, and lints the OpenAPI contract. Any failure is a
release blocker.
