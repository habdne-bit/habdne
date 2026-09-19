# تُراب — TURAB

> منصة عقارية محلية تبدأ من حاجة المشتري، وتنظم العرض المتاح وغير المعلن،
> وتطابق بينهما للوصول إلى فرصة عقارية حقيقية.

## Project status

| Gate | Status |
|---|---|
| Hardened static audit (v0.2.3) | PASS — 131 FK references |
| **PostgreSQL 16+ Execution Gate** | **PASS** — twice on v0.2.3, 7 steps, 70/70 assertions |
| Technical database baseline | **FROZEN** at `schema_v0.2.3.sql` |
| Slice −1 — Tooling baseline | Complete |
| Slice 0 — Application Skeleton + Security Boundaries | **Complete** |
| Slice 1 — PARTY / Contact / Account / Consent | **In progress** — 267 tests, 71 rules evidenced |

Handoff package: **v1.0.3** (official), vendored byte-for-byte.

- Gate results and artifact digests: **[`docs/gate/GATE_RUN_REPORT.md`](docs/gate/GATE_RUN_REPORT.md)**
- Freeze record and pinned commit: **[`docs/gate/TECHNICAL_BASELINE_FROZEN.md`](docs/gate/TECHNICAL_BASELINE_FROZEN.md)**
- Object-level authorization design, **FINAL / APPROVED**: **[`docs/rfc/RFC-001-object-level-authorization.md`](docs/rfc/RFC-001-object-level-authorization.md)**
- Authorization evidence: **[`docs/gate/AUTHORIZATION_EVIDENCE_MATRIX.md`](docs/gate/AUTHORIZATION_EVIDENCE_MATRIX.md)**
- Slice 0 closure: **[`docs/gate/SLICE_0_CLOSURE_PACK.md`](docs/gate/SLICE_0_CLOSURE_PACK.md)**

Slices follow `06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md` in order; no
advanced AI work begins before the Core Hypothesis Stop Gate passes.

## Layout

| Path | Contents |
|---|---|
| `docs/handoff/` | The official Developer Handoff **v1.0.3** package, vendored **unmodified** — the authority baseline. Read `docs/handoff/README.md` first. Never edited in place: corrections arrive as a new official package. |
| `docs/gate/` | Execution gate run reports |
| `db/gate/` | Gate harness: contract tests, runner, OpenAPI lint, API inventory generator |
| `db/dev/` | Development database reset (`reset_db.sh`) |
| `db/fixtures/` | Developer fixtures — a coherent Adrar world, authorization edge cases EC1–EC8, market edge cases MF1–MF8 |
| `docs/rfc/` | Design RFCs awaiting or carrying decisions |
| `docs/api/` | Generated API inventory (do not edit) |
| `src/turab/` | The service. `auth/` holds actor resolution, the policy layer, scoped loaders and access audit; `services/` the application layer; `api/` the HTTP edge |
| `tests/` | Architecture, policy, authorization, INV-1/INV-2, audit and HTTP tests |
| `.github/workflows/` | CI — rebuilds a clean database from zero, then runs the authorization suite |

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


## Running the service and its tests

```bash
python3.12 -m venv .venv && ./.venv/bin/pip install -e ".[dev]"
db/dev/reset_db.sh --fixtures          # a database to work against
./.venv/bin/pytest -q                  # 267 tests
./.venv/bin/python db/gate/authorization_evidence.py   # regenerate the matrix
```

Authorization is enforced structurally: routes import no session, repository or
SQLAlchemy, and reach data only through application services backed by
actor-scoped, policy-checked loaders. Architecture tests hold that line; the
cross-account 404 sweep proves it end to end.
