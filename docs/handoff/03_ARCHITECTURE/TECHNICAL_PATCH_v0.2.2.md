# TURAB — Technical Patch v0.2.2

**Date:** 2026-09-19  
**Handoff:** v1.0.2  
**Scope:** optimistic-concurrency contract alignment + PARTY version projection only  
**Supersedes for new adoption:** Technical Patch v0.2.1 executable/API baseline  
**Preserves:** all v0.2.1 duplicate-FK remediations and all product/domain semantics not explicitly listed below.

## 1. Why this patch exists

Slice 0 closure exposed two same-level contract/schema discrepancies before PARTY implementation:

- **D1:** prose and implementation guidance require `If-Match-Version`, while the frozen OpenAPI parameter component `IfMatchVersion` declared the actual HTTP header as `If-Match`;
- **D2:** `PATCH /parties/{party_id}` requires optimistic concurrency, but `parties` had no `version` column and Party response DTOs did not expose a version to the caller.

The approved decision is to keep integer projection versioning, make the custom header name explicit, and complete PARTY versioning rather than remove concurrency from PARTY.

## 2. D1 — canonical HTTP header

The component identifier remains `IfMatchVersion`, but its wire-level name is now:

```text
If-Match-Version
```

Its schema is integer with minimum 1. `If-Match` is not a compatibility alias in the corrected baseline. This avoids implying an HTTP ETag/strong-validator design that TURAB v0.1 does not implement.

## 3. D2 — PARTY optimistic versioning

`parties` gains:

```sql
version integer NOT NULL DEFAULT 1 CHECK (version > 0)
```

The PARTY update trigger uses the existing `bump_version_and_timestamp()` function. No new trigger function is introduced.

The response schemas `Party` and `CustomerPartyView` both expose required integer `version >= 1`. Input schemas `PartyCreate` and `PartyPatch` do not accept a client-supplied version.

Expected flow:

```text
GET /me/party -> version = 4
PATCH /parties/{party_id}
If-Match-Version: 4
-> success, returned version = 5

retry with If-Match-Version: 4
-> 409 stale version; no partial write
```

## 4. Files changed by this patch

Authoritative machine artifacts:

- `04_DATABASE/schema_v0.2.2.sql`
- `04_DATABASE/seed_master_data_v0.2.2.sql` (seed semantics unchanged; version/header reference only)
- `05_API/openapi_v0.2.2.yaml`

Synchronized handoff/QA artifacts are updated to reference them.

## 5. Files/semantics intentionally NOT changed

This patch does **not** redesign:

- PARTY/CONTACT_POINT/USER_ACCOUNT separation;
- object-level authorization;
- consent;
- record claims;
- REQUEST/PROPERTY/OFFER matching semantics;
- truth/provenance;
- OPPORTUNITY gates;
- AI role;
- master-data content;
- REQUEST/PROPERTY/PROPERTY_OFFER version behavior.

The Foreign-Key count remains **131**. A different FK count is a regression requiring investigation.

## 6. Release status

The developer previously reported a real PostgreSQL 16.13 PASS and Slice 0 closure on v0.2.1. Because v0.2.2 changes both schema and OpenAPI, those results remain historical evidence but do not freeze this new candidate.

**v0.2.2 status on publication:** `PATCH_CANDIDATE — FULL RERUN REQUIRED`.

The developer must run `verify_v022_baseline.py`, the full PostgreSQL gate, the expanded gate suite, the Slice 0 suite, and OpenAPI drift checks. Only after PASS may v0.2.2 be recorded as the new frozen technical baseline and Slice 1 begin.

## 7. Migration stance

This is a pre-Slice-1 baseline correction. No production database migration history exists that must be preserved. Rebuild a clean database from `schema_v0.2.2.sql`; do not create a product Alembic migration solely to carry the v0.2.1→v0.2.2 correction.
