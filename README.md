# تُراب — TURAB

> منصة عقارية محلية تبدأ من حاجة المشتري، وتنظم العرض المتاح وغير المعلن،
> وتطابق بينهما للوصول إلى فرصة عقارية حقيقية.

## Project status

| Gate | Status |
|---|---|
| Hardened static audit (v0.2.1) | PASS — 131 FK references |
| **PostgreSQL 16+ Execution Gate** | **PASS** — twice, 65/65 assertions |
| Technical database baseline | **FROZEN** at `schema_v0.2.1.sql` |
| Slice 0 — Application Skeleton + Security Boundaries | **Open** |

Handoff package: **v1.0.1** (official), vendored unmodified.

- Gate results and artifact digests: **[`docs/gate/GATE_RUN_REPORT.md`](docs/gate/GATE_RUN_REPORT.md)**
- Freeze record and pinned commit: **[`docs/gate/TECHNICAL_BASELINE_FROZEN.md`](docs/gate/TECHNICAL_BASELINE_FROZEN.md)**

Slices follow `06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md` in order; no
advanced AI work begins before the Core Hypothesis Stop Gate passes.

## Layout

| Path | Contents |
|---|---|
| `docs/handoff/` | The official Developer Handoff **v1.0.1** package, vendored **unmodified** — the authority baseline. Read `docs/handoff/README.md` first. Never edited in place: corrections arrive as a new official package. |
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
