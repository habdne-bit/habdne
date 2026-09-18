# PostgreSQL Execution Gate

The current artifact environment does not include a PostgreSQL server/client, so static validation cannot replace real migration execution.

Before implementation freeze, CI MUST run against PostgreSQL 16+:

```bash
createdb turab_contract_test
psql turab_contract_test -v ON_ERROR_STOP=1 -f schema_v0.2.1.sql
psql turab_contract_test -v ON_ERROR_STOP=1 -f seed_master_data_v0.2.sql
psql turab_contract_test -v ON_ERROR_STOP=1 -f seed_master_data_v0.2.sql   # idempotency check
```

Then execute database-level contract tests for:

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
- one open opportunity per Request × canonical Property.

A failure here is a release blocker even if static audit passes.
