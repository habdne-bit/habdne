# PostgreSQL / Contract Execution Gate — v0.2.2

Technical Patch v0.2.2 changes the executable schema and OpenAPI contract. The previous v0.2.1 runtime PASS is evidence of the prior baseline, not a substitute for rerunning this candidate.

Before Slice 1 re-freeze, CI MUST run against PostgreSQL 16+:

```bash
createdb turab_contract_test
psql turab_contract_test -v ON_ERROR_STOP=1 -f schema_v0.2.2.sql
psql turab_contract_test -v ON_ERROR_STOP=1 -f seed_master_data_v0.2.2.sql
psql turab_contract_test -v ON_ERROR_STOP=1 -f seed_master_data_v0.2.2.sql   # idempotency
```

Then execute the existing database-level contract/red-team gate, including at minimum:

- opportunity gate;
- latest append-only match review;
- resolution lineage;
- verification upgrade path;
- consent resource binding;
- alias→canonical property constraint;
- match commercial context BUY/RENT checks;
- assisted claim-state checks;
- protected hard deletes;
- one active matching policy;
- one open opportunity per Request × canonical Property;
- Ksar Tililane and New City Tililane remain distinct canonical locations.

## v0.2.2 patch-specific checks

Database/schema checks:

1. new PARTY row starts at `version = 1`;
2. successful PARTY `UPDATE` increments version exactly once and refreshes `updated_at`;
3. the PARTY trigger calls `bump_version_and_timestamp()`;
4. the old timestamp-only PARTY trigger is absent;
5. FK count remains 131 and duplicate-FK checks remain PASS.

Application/HTTP checks (run with the Slice 0 suite):

1. `If-Match-Version` is the only documented/accepted concurrency header after adoption;
2. correct version permits mutation and returns the incremented Party projection;
3. stale version returns typed `409` with no partial write and no version bump;
4. `/me/party` exposes the current integer version;
5. internal Party GET exposes the current integer version;
6. REQUEST / PROPERTY / PROPERTY_OFFER concurrency behavior remains unchanged;
7. OpenAPI runtime drift check passes against `openapi_v0.2.2.yaml`.

A failure here is a release blocker even if static audit passes. Do not start Slice 1 until the rerun is green and the new baseline commit/hashes are recorded.
