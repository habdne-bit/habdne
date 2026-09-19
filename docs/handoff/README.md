# TURAB Developer Handoff v1.0.3 — START HERE

This is the official adoption package for **Technical Patch v0.2.3**.

**Current status:** v0.2.2 passed the real PostgreSQL 16.13 execution gate and the complete Slice 0 rerun, but was intentionally **not frozen** because final live verification found D6: `schema_metadata.schema_version` remained `0.2.1`. Patch v0.2.3 is a narrow metadata/version-consistency correction only. It preserves all v0.2.1 FK fixes and all v0.2.2 D1/D2 concurrency/PARTY-version semantics. The **v0.2.3 PostgreSQL/OpenAPI/Slice 0 rerun is release-blocking before Slice 1**.

## Read first

1. `00_START_HERE/TURAB_Developer_Handoff_Master_v1.0.3.md`
2. `03_ARCHITECTURE/TECHNICAL_PATCH_v0.2.3.md`
3. `00_START_HERE/FILE_AUTHORITY_AND_VERSION_POLICY.md`
4. `04_DATABASE/schema_v0.2.3.sql`
5. `05_API/openapi_v0.2.3.yaml`
6. `04_DATABASE/POSTGRES_EXECUTION_GATE.md`
7. `07_QA_ACCEPTANCE/verify_v023_baseline.py`
8. `07_QA_ACCEPTANCE/verify_version_consistency.py`

The product baseline, architecture v0.2, API contracts v0.2, implementation slices, and red-team suite remain authoritative except where the technical patches explicitly supersede them. `TECHNICAL_PATCH_v0.2.3.md` is the latest patch authority; it preserves the semantics introduced by v0.2.2.

**Do not patch v0.2.2 in place. Do not begin Slice 1 until v0.2.3 is adopted, rerun, and re-frozen.**
