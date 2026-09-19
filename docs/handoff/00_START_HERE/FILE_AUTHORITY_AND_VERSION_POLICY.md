# TURAB — File Authority & Version Policy

## Authoritative baselines

1. Product meaning: `TURAB_Foundation_Baseline_v1.0_FINAL.docx`
2. Project decision method: `TURAB_Project_Instructions_v1.0.md`
3. Accepted technical architecture: `ARCHITECTURE_DECISIONS_v0.2.md`; latest patch authority: `TECHNICAL_PATCH_v0.2.2.md`
4. Developer behavioral reference: `TURAB_Developer_Reference_Spec_v0.1.md`
5. API behavior: `API_CONTRACTS_v0.2.md` + `openapi_v0.2.2.yaml`, with v0.2.2 taking precedence on the concurrency-header/Party-version delta
6. Database baseline candidate: `schema_v0.2.2.sql` + `seed_master_data_v0.2.2.sql`
7. Build sequence: `IMPLEMENTATION_SLICES_v0.2.md`
8. Release/acceptance: `POSTGRES_EXECUTION_GATE.md` + `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` + `verify_v022_baseline.py`

## Conflict rule

Do not silently resolve a contradiction. Product semantics defer upward to the Foundation. Technical Patch v0.2.2 supersedes v0.2.1 only for the explicit D1/D2 corrections documented in the patch. All v0.2.1 FK remediations remain in force. If same-level contracts disagree, stop the affected implementation and raise a change/clarification before coding around it.

## Immutability / supersession

- v0.2 remains an historical runtime-failed candidate.
- v0.2.1 remains the previously executed/frozen baseline and is not edited in place.
- v0.2.2 is a new adoption candidate. It becomes the active frozen baseline only after the full rerun and re-freeze.
- Published hashes for older packages are never rewritten.

## Do not use as implementation baseline

- Foundation v0.1–v0.9.
- Technical Implementation Pack v0.1.
- schema/openapi/API contracts v0.1.
- `schema_v0.2.sql` or `schema_v0.2.1.sql` for new work after v0.2.2 adoption.
- historical review files except to understand rationale.

## Change discipline

A domain, state, permission, matching, privacy, verification, opportunity, persistence, or HTTP-contract change requires an explicit approved decision and synchronized changes to schema, OpenAPI, contracts, tests, manifests, and relevant documentation.
