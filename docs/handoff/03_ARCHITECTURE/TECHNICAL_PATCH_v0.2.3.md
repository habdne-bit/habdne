# TURAB — Technical Patch v0.2.3

**Date:** 2026-09-19  
**Handoff:** v1.0.3  
**Scope:** D6 schema-version metadata consistency only  
**Supersedes for new adoption:** Technical Patch v0.2.2 candidate  
**Preserves:** all v0.2.1 FK remediations and all v0.2.2 D1/D2 concurrency/PARTY-version semantics.

## 1. Why this patch exists

The developer executed the complete v0.2.2 adoption flow successfully on PostgreSQL 16.13, including the full database gate, the expanded gate suite, the Slice 0 suite and OpenAPI drift checks. During the final live-baseline verification, one non-functional but authoritative inconsistency was found:

- **D6:** `schema_v0.2.2.sql` identified itself in its filename/header as v0.2.2, while the seeded row `schema_metadata.schema_version` still contained `0.2.1`.

No current trigger, constraint, application rule or API behavior depended on that metadata value, so the v0.2.2 runtime results remain valid evidence. However a published baseline must not report a different internal schema version from the artifact that created it.

Therefore v0.2.2 is retained historically as:

> `RUNTIME_VALIDATED_BUT_NOT_FROZEN_DUE_TO_D6_METADATA_MISMATCH`

and this narrow correction is published as v0.2.3.

## 2. D6 — authoritative correction

The operative schema is `04_DATABASE/schema_v0.2.3.sql` and MUST contain:

```sql
('schema_version','0.2.3')
```

The following version claims are synchronized to `0.2.3`:

- schema filename;
- seed filename;
- OpenAPI filename;
- static-audit script filename;
- static-audit result filename;
- technical-pack manifest filename;
- schema header;
- `schema_metadata.schema_version`;
- seed header;
- OpenAPI `info.version`;
- `HANDOFF_MANIFEST.json` technical-baseline declaration.

## 3. Version-consistency invariant

This patch adds a release-blocking consistency check. The baseline MUST fail adoption if any of the version claims above disagree.

The dedicated tool is:

`07_QA_ACCEPTANCE/verify_version_consistency.py`

The static audit also enforces the same invariant and reports a version mismatch as a release error, including the specific `SCHEMA_VERSION_STAMP_MISMATCH` condition when the database metadata stamp disagrees.

This check becomes part of the mandatory PostgreSQL/contract gate before any future freeze.

## 4. Files changed by this patch

Authoritative machine artifacts:

- `04_DATABASE/schema_v0.2.3.sql`
- `04_DATABASE/seed_master_data_v0.2.3.sql` — master-data semantics unchanged; version/header references only
- `05_API/openapi_v0.2.3.yaml` — HTTP/API semantics unchanged; artifact/info version only
- `07_QA_ACCEPTANCE/technical_pack_static_audit_v0.2.3.py`
- `07_QA_ACCEPTANCE/verify_v023_baseline.py`
- `07_QA_ACCEPTANCE/verify_version_consistency.py`

Synchronized handoff, gate, manifest and checksum artifacts are updated to reference them.

## 5. Semantics intentionally NOT changed

v0.2.3 does **not** change:

- the canonical `If-Match-Version` integer-only header semantics;
- PARTY optimistic concurrency or `parties.version`;
- PARTY/CONTACT_POINT/USER_ACCOUNT separation;
- object-level authorization;
- maker-checker rules;
- consent or record-claim authority;
- REQUEST / PROPERTY / PROPERTY_OFFER behavior;
- matching, provenance, identity resolution or Opportunity gates;
- master-data meaning;
- AI role;
- any role assignment or API operation authorization.

The Foreign-Key count remains **131**. A different count is a regression requiring investigation.

## 6. Release status

The developer reported v0.2.2 PASS on PostgreSQL 16.13 twice, the expanded gate at 70/70, the Slice 0 suite at 218/218 or later, and OpenAPI drift PASS. Those remain historical runtime evidence but do not freeze v0.2.3 automatically.

**v0.2.3 status on publication:** `PATCH_CANDIDATE — FULL RERUN REQUIRED`.

Before Slice 1, the developer must:

1. verify handoff integrity;
2. run `verify_v023_baseline.py`;
3. run `verify_version_consistency.py`;
4. run `technical_pack_static_audit_v0.2.3.py`;
5. rebuild a clean PostgreSQL 16+ database from `schema_v0.2.3.sql`;
6. run `seed_master_data_v0.2.3.sql` twice;
7. run the complete database/red-team gate;
8. run the complete current Slice 0 suite and Authorization Evidence Matrix checks;
9. run OpenAPI runtime drift checks against `openapi_v0.2.3.yaml`;
10. record the new commit and SHA-256 values.

Only after all checks pass may v0.2.3 be declared **FROZEN** and Slice 1 open.

## 7. Migration stance

This remains a pre-Slice-1 baseline correction with no production migration history to preserve. Rebuild a clean database from `schema_v0.2.3.sql`; do not create a product Alembic migration solely for the v0.2.2→v0.2.3 metadata correction.
