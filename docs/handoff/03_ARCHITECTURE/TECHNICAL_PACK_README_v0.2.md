> **Handoff layout note:** this is the v0.2 technical README copied into the final developer handoff. Files have been reorganized into numbered folders. Use the root `README.md` and `00_START_HERE/TURAB_Developer_Handoff_Master_v1.0.md` for actual paths and authority order.

# TURAB Technical Implementation Pack v0.2

**Purpose:** implementation-ready technical baseline after the strict Architecture Review of v0.1.

## Status

**STATIC REVIEW: PASS**  
**POSTGRESQL EXECUTION PROOF: PENDING** — the artifact environment does not include PostgreSQL. Run the required CI execution gate before coding against this pack.

v0.2 closes the P0/P1 architecture findings from `REFERENCE_Architecture_Review_v0.1.md`. It should replace v0.1 as the technical baseline.

## Files

| File | Purpose |
|---|---|
| `schema_v0.2.sql` | Clean PostgreSQL 16+ baseline schema with v0.2 invariants |
| `seed_master_data_v0.2.sql` | Adrar location master data, controlled document/right options, reason codes, matching policy |
| `openapi_v0.2.yaml` | OpenAPI 3.1 contract with DTO separation, operationIds, idempotency and queues |
| `API_CONTRACTS_v0.2.md` | Behavioral API/domain contract |
| `API_INVENTORY_v0.2.md` | Human-readable inventory of all HTTP operations |
| `ARCHITECTURE_DECISIONS_v0.2.md` | Accepted remediation ADRs |
| `IMPLEMENTATION_SLICES_v0.2.md` | Slice-by-slice build plan and stop gates |
| `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` | Mandatory edge-case acceptance scenarios |
| `POSTGRES_EXECUTION_GATE.md` | Required PostgreSQL 16 migration/runtime proof |
| `technical_pack_static_audit_v0.2.py` | Repeatable local static contract audit |
| `STATIC_AUDIT_RESULTS_v0.2.json` | Latest static audit result and file hashes |
| `CHANGELOG_v0.2.md` | Differences from v0.1 |
| `REFERENCE_Developer_Spec_v0.1.md` | Product-to-developer reference retained as upstream source |
| `REFERENCE_Architecture_Review_v0.1.md` | Red-team findings that caused this remediation |

## Required reading order for a developer

1. `REFERENCE_Developer_Spec_v0.1.md`
2. `ARCHITECTURE_DECISIONS_v0.2.md`
3. `API_CONTRACTS_v0.2.md`
4. `schema_v0.2.sql`
5. `openapi_v0.2.yaml`
6. `IMPLEMENTATION_SLICES_v0.2.md`
7. `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md`

## Core invariants

- REQUEST and PROPERTY are equal first-class entities.
- PROPERTY is the physical real-estate identity; PROPERTY_OFFER is commercial context; SOURCE is provenance.
- Confirmed duplicate property records resolve to a canonical property without deleting sources/offers/history.
- INTEREST is not REQUEST.
- MATCH_CANDIDATE is not OPPORTUNITY.
- Hard FAIL cannot be overridden by ranking.
- Required UNKNOWN is explicit information work.
- Matching commercial context and historical inputs are snapshotted immutably.
- Opportunity requires latest human APPROVED review and all gates PASS.
- Consent is resource-bound and revocable.
- Public/customer/internal DTOs are separate.
- Declared fact is not verified fact.
- No automatic destructive merge, automatic preference relaxation or autonomous AI opportunity creation.

## Static audit

Run:

```bash
python technical_pack_static_audit_v0.2.py
```

The packaged result is PASS and checks SQL structural references, remediation markers, seed coverage, OpenAPI refs/parameters/operationIds/idempotency/DTO boundaries and file hashes.

## PostgreSQL execution gate

Before starting Slice 0/1, run schema + seed on clean PostgreSQL 16+ as described in `POSTGRES_EXECUTION_GATE.md`. This is a release blocker. Static parsing is not a substitute for the PostgreSQL parser and trigger/constraint execution.

## Build rule

Do not start with AI. Follow `IMPLEMENTATION_SLICES_v0.2.md`; prove the deterministic end-to-end core through the Human Review → OPPORTUNITY gate first.
