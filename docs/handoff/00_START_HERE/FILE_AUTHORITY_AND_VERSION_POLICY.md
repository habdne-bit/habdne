# TURAB — File Authority & Version Policy

## Authoritative baselines

1. Product meaning: `TURAB_Foundation_Baseline_v1.0_FINAL.docx`
2. Project decision method: `TURAB_Project_Instructions_v1.0.md`
3. Accepted technical architecture: `ARCHITECTURE_DECISIONS_v0.2.md`; database patch authority: `TECHNICAL_PATCH_v0.2.1.md`
4. Developer behavioral reference: `TURAB_Developer_Reference_Spec_v0.1.md`
5. API behavior: `API_CONTRACTS_v0.2.md` + `openapi_v0.2.yaml`
6. Database baseline: `schema_v0.2.1.sql` + `seed_master_data_v0.2.1.sql`
7. Build sequence: `IMPLEMENTATION_SLICES_v0.2.md`
8. Release/acceptance: `POSTGRES_EXECUTION_GATE.md` + `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md`

## Conflict rule

Do not silently resolve a contradiction. Product semantics defer upward to the Foundation. Technical remediations in v0.2 supersede v0.1 technical assumptions. Database Patch v0.2.1 supersedes `schema_v0.2.sql` and its old hashes; do not edit or silently reuse v0.2. If same-level contracts disagree, stop the affected implementation and raise a change/clarification before coding around it.

## Do not use as implementation baseline

- Foundation v0.1–v0.9.
- Technical Implementation Pack v0.1.
- schema/openapi/API contracts v0.1.
- historical review files except to understand rationale.

## Change discipline

A domain, state, permission, matching, privacy, verification or opportunity change requires an explicit approved design/architecture decision and synchronized changes to schema, OpenAPI, contracts, tests and relevant documentation.
