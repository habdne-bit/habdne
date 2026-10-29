# تُراب — TURAB

> منصة عقارية محلية تبدأ من حاجة المشتري، وتنظم العرض المتاح وغير المعلن،
> وتطابق بينهما للوصول إلى فرصة عقارية حقيقية.

## Project status

| Gate | Status |
|---|---|
| Hardened static audit (v0.2.3) | PASS — 131 FK references |
| **PostgreSQL 16+ Execution Gate** | **PASS** — 8 steps, 70/70 assertions |
| Technical database baseline | **FROZEN** at `schema_v0.2.3.sql` |
| Slice −1 — Tooling baseline | Complete |
| Slice 0 — Application Skeleton + Security Boundaries | **Complete** |
| Slice 1 — PARTY / Contact / Account / Consent | **Feature-complete; D7 closed**, submitted for closure review — all 11 contract operations wired |
| Slice 2 — REQUEST / Criteria / Freshness | **CLOSED within its agreed scope** (acceptance review of `73be3a7`) — see [`docs/gate/SLICE_2_PROGRESS.md`](docs/gate/SLICE_2_PROGRESS.md) |
| Slice 3 — PROPERTY / OFFER / SOURCE / Truth / Identity | **CLOSED at `96e36e6`**, within the approved exceptions — see [`docs/gate/SLICE_3_CLOSURE.md`](docs/gate/SLICE_3_CLOSURE.md) |
| Slice 4 — Deterministic Matching Core | **CLOSED at `58368d1`**, within the approved scope — see [`docs/gate/SLICE_4_CLOSURE.md`](docs/gate/SLICE_4_CLOSURE.md) |
| Slice 5 — Human Review → OPPORTUNITY | **CLOSED at `339dbc4`**, SALE only — see [`docs/gate/SLICE_5_CLOSURE.md`](docs/gate/SLICE_5_CLOSURE.md) |
| Slice 6 — Match Diagnostic / Information Work | **CLOSED at `ce8cfa0`**, SALE only — see [`docs/gate/SLICE_6_CLOSURE.md`](docs/gate/SLICE_6_CLOSURE.md) |
| Slice 7 — Communication / WhatsApp Record | **CLOSED at `abee0f9`**, SALE only — see [`docs/gate/SLICE_7_CLOSURE.md`](docs/gate/SLICE_7_CLOSURE.md); **R-1 UNMET: no real event may be received**; K06 UNPROVEN; not a release authorization |
| R-1 — the relay (Meta's boundary) | **Plan revision 7**; step 1 (Meta's GET, Meta's signature, the inbound limit, mutual TLS) **CLOSED at `e9fac51`** ([`docs/gate/R1_STEP1_DELIVERY.md`](docs/gate/R1_STEP1_DELIVERY.md)); step 2 (the transformation, the relay's signature, `thread_ref`) **CLOSED at `da3d778`** ([`docs/gate/R1_STEP2_DELIVERY.md`](docs/gate/R1_STEP2_DELIVERY.md)); step 3 (the delivery to TURAB, §5.1's answers) **DELIVERED for review** ([`docs/gate/R1_STEP3_DELIVERY.md`](docs/gate/R1_STEP3_DELIVERY.md)); the relay's code is tested on synthetic notifications only; no deployment, no secret — see [`docs/gate/R1_RELAY_PLAN.md`](docs/gate/R1_RELAY_PLAN.md) (Meta's requirements: [`docs/gate/evidence/R1-META-SOURCES.txt`](docs/gate/evidence/R1-META-SOURCES.txt)); **R-1 UNMET: no real event may be received** |

Standing: K06 **UNPROVEN** (EN-02); G4-5R open, SALE only. The current
suite count and its binding to the tree are in
[`docs/gate/evidence/TEST-RUN-PROVENANCE.txt`](docs/gate/evidence/TEST-RUN-PROVENANCE.txt);
the rules evidenced, in the authorization matrix below. The effective
contract holds 67 operations ([`docs/api/API_INVENTORY_GENERATED.md`](docs/api/API_INVENTORY_GENERATED.md)).

Handoff package: **v1.0.3** (official), vendored byte-for-byte.

- Gate results and artifact digests: **[`docs/gate/GATE_RUN_REPORT.md`](docs/gate/GATE_RUN_REPORT.md)**
- Freeze record and pinned commit: **[`docs/gate/TECHNICAL_BASELINE_FROZEN.md`](docs/gate/TECHNICAL_BASELINE_FROZEN.md)**
- Object-level authorization design, **FINAL / APPROVED**: **[`docs/rfc/RFC-001-object-level-authorization.md`](docs/rfc/RFC-001-object-level-authorization.md)**
- Authorization evidence: **[`docs/gate/AUTHORIZATION_EVIDENCE_MATRIX.md`](docs/gate/AUTHORIZATION_EVIDENCE_MATRIX.md)**
- Slice 0 closure: **[`docs/gate/SLICE_0_CLOSURE_PACK.md`](docs/gate/SLICE_0_CLOSURE_PACK.md)**
- Slice 1 closure: **[`docs/gate/SLICE_1_CLOSURE_PACK.md`](docs/gate/SLICE_1_CLOSURE_PACK.md)**
- Slice 2 progress, gaps and STOP GATE B: **[`docs/gate/SLICE_2_PROGRESS.md`](docs/gate/SLICE_2_PROGRESS.md)**
- Adopted REQUEST state transitions: **[`docs/gate/REQUEST_STATE_TRANSITIONS.md`](docs/gate/REQUEST_STATE_TRANSITIONS.md)**
- Response to the independent review: **[`docs/gate/REVIEW_RESPONSE_R-S2.md`](docs/gate/REVIEW_RESPONSE_R-S2.md)**
- RFC-001 Appendix A (INV-1 / INV-2): **[`docs/rfc/RFC-001-APPENDIX-A-invariants.md`](docs/rfc/RFC-001-APPENDIX-A-invariants.md)**
- Migration policy (R14.4–R14.7): **[`docs/gate/MIGRATION_POLICY.md`](docs/gate/MIGRATION_POLICY.md)**
- Alembic evidence pack and stated limits: **[`docs/gate/ALEMBIC_EVIDENCE_PACK.md`](docs/gate/ALEMBIC_EVIDENCE_PACK.md)**
- **Design Ledger** — adopted, deferred and blocked decisions: **[`docs/DESIGN_LEDGER.md`](docs/DESIGN_LEDGER.md)**
- Contract corrections (never edit the frozen package): **[`docs/contract/`](docs/contract/)**
- Environment notes: **[`docs/gate/ENVIRONMENT_NOTES.md`](docs/gate/ENVIRONMENT_NOTES.md)**
- INV-1 / INV-2, approved text and where each half is enforced: **[`docs/gate/INV-1-and-INV-2.md`](docs/gate/INV-1-and-INV-2.md)**
- Run evidence per commit: **[`docs/gate/evidence/`](docs/gate/evidence/)**
- Defect record (BOLA on the Slice 1 command surface, closed): **[`docs/gate/DEFECT-001-command-surface-object-gate.md`](docs/gate/DEFECT-001-command-surface-object-gate.md)**

Slices follow `06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md` in order; no
advanced AI work begins before the Core Hypothesis Stop Gate passes.

## Layout

| Path | Contents |
|---|---|
| `docs/handoff/` | The official Developer Handoff **v1.0.3** package, vendored **unmodified** — the authority baseline. Read `docs/handoff/README.md` first. Never edited in place: corrections arrive as a new official package. |
| `docs/gate/` | Execution gate run reports |
| `db/gate/` | Gate harness: contract tests, runner, OpenAPI lint, API inventory generator |
| `db/dev/` | Development database reset (`reset_db.sh`) — applies the frozen baseline, then **stamps** the initial Alembic revision |
| `db/migrations/` | Alembic. The frozen schema **is** the initial migration; autogenerate is refused. See [`docs/gate/MIGRATION_POLICY.md`](docs/gate/MIGRATION_POLICY.md) |
| `db/fixtures/` | Developer fixtures — a coherent Adrar world, authorization edge cases EC1–EC8, market edge cases MF1–MF8 |
| `docs/rfc/` | Design RFCs awaiting or carrying decisions |
| `docs/contract/` | Numbered contract corrections applied on top of the frozen OpenAPI. A correction may only **narrow**; the published package is never edited |
| `docs/api/` | Generated, do not edit: the **effective contract** (frozen package + approved corrections) and the API inventory derived from it |
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
./.venv/bin/python -m pytest -q        # needs a full git clone (EN-03)
./.venv/bin/python db/gate/authorization_evidence.py   # regenerate the matrix
```

Authorization is enforced structurally: routes import no session, repository or
SQLAlchemy, and reach data only through application services backed by
actor-scoped, policy-checked loaders. Architecture tests hold that line; the
cross-account 404 sweep proves it end to end.
