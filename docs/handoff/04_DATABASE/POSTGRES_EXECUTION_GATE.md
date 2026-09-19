# PostgreSQL / Contract Execution Gate — v0.2.3

Technical Patch v0.2.3 changes only the authoritative schema-version stamp/package identity. v0.2.2 was runtime-validated on PostgreSQL 16.13 but intentionally not frozen because D6 left `schema_metadata.schema_version` at `0.2.1`. Those results remain evidence, not a substitute for rerunning this candidate.

Before Slice 1 re-freeze, CI MUST run against PostgreSQL 16+:

```bash
createdb turab_contract_test
psql turab_contract_test -v ON_ERROR_STOP=1 -f schema_v0.2.3.sql
psql turab_contract_test -v ON_ERROR_STOP=1 -f seed_master_data_v0.2.3.sql
psql turab_contract_test -v ON_ERROR_STOP=1 -f seed_master_data_v0.2.3.sql   # idempotency
```

Then verify live metadata:

```sql
SELECT value FROM turab.schema_metadata WHERE key='schema_version';
-- must return: 0.2.3
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

## v0.2.3 patch-specific checks

Version/baseline checks:

1. `verify_v023_baseline.py` passes;
2. `verify_version_consistency.py` passes and all eleven version claims resolve to `0.2.3`;
3. `technical_pack_static_audit_v0.2.3.py` passes and reports 131 FK references;
4. live `schema_metadata.schema_version` is `0.2.3`;
5. both prior duplicate-FK remediations remain present exactly once.

Preserved D1/D2 checks:

1. new PARTY row starts at `version = 1`;
2. successful PARTY `UPDATE` increments version exactly once and refreshes `updated_at`;
3. the PARTY trigger calls `bump_version_and_timestamp()`;
4. the old timestamp-only PARTY trigger is absent;
5. `If-Match-Version` is the only documented/accepted concurrency header and is integer-only;
6. correct version permits mutation and returns the incremented Party projection;
7. stale version returns typed `409` with no partial write and no version bump;
8. `/me/party` and internal Party GET expose the current integer version;
9. REQUEST / PROPERTY / PROPERTY_OFFER concurrency behavior remains unchanged;
10. OpenAPI runtime drift check passes against `openapi_v0.2.3.yaml`.

Full re-freeze checks:

1. expanded database gate passes;
2. current Slice 0 test suite passes completely;
3. Authorization Evidence Matrix has no `UNPROVEN` rule;
4. the full gate passes twice on recreated/clean database state;
5. new commit and SHA-256 values are recorded.

A failure here is a release blocker even if the rest of the static audit passes. Do not start Slice 1 until the rerun is green and v0.2.3 is explicitly recorded as FROZEN.
