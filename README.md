# تُراب — TURAB

> منصة عقارية محلية تبدأ من حاجة المشتري، وتنظم العرض المتاح وغير المعلن،
> وتطابق بينهما للوصول إلى فرصة عقارية حقيقية.

## Project status

**Implementation has not started. It is gated.**

| Gate | Status |
|---|---|
| Static architecture audit (Technical Pack v0.2) | PASS |
| **PostgreSQL 16+ Execution Gate** | **FAIL — release blocker open** |
| Slice 0 and all feature slices | Not started (blocked by the gate) |

The blocker and the full run results are in
**[`docs/gate/GATE_RUN_REPORT.md`](docs/gate/GATE_RUN_REPORT.md)**.

Per `docs/handoff/00_START_HERE/TURAB_Developer_Handoff_Master_v1.0.md` §10–§11,
no feature slice may begin until the gate is green.

## Layout

| Path | Contents |
|---|---|
| `docs/handoff/` | The Developer Handoff v1.0 package, vendored **unmodified**. Read `docs/handoff/README.md` first. This is the authority baseline. |
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
