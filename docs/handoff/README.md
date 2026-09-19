# TURAB Developer Handoff v1.0.2 — START HERE

This is the official adoption package for **Technical Patch v0.2.2**.

**Current status:** v0.2.1 previously passed the real PostgreSQL 16.13 execution gate and Slice 0 was closed successfully. Patch v0.2.2 is a narrow baseline correction for D1/D2 only: canonical `If-Match-Version` semantics and PARTY optimistic versioning. Because schema and OpenAPI changed, the **v0.2.2 PostgreSQL/OpenAPI/Slice 0 rerun is release-blocking before Slice 1**.

## Read first

1. `00_START_HERE/TURAB_Developer_Handoff_Master_v1.0.2.md`
2. `03_ARCHITECTURE/TECHNICAL_PATCH_v0.2.2.md`
3. `00_START_HERE/FILE_AUTHORITY_AND_VERSION_POLICY.md`
4. `04_DATABASE/schema_v0.2.2.sql`
5. `05_API/openapi_v0.2.2.yaml`
6. `04_DATABASE/POSTGRES_EXECUTION_GATE.md`
7. `07_QA_ACCEPTANCE/verify_v022_baseline.py`

The product baseline, architecture v0.2, API contracts v0.2, implementation slices, and red-team suite remain authoritative except where `TECHNICAL_PATCH_v0.2.2.md` explicitly supersedes them.

**Do not patch v0.2.1 in place. Do not begin Slice 1 until v0.2.2 is adopted, rerun, and re-frozen.**
