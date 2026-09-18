# TURAB — Technical Patch v0.2.1

**Date:** 2026-09-18  
**Scope:** PostgreSQL executable baseline only  
**Supersedes:** `schema_v0.2.sql` and its published hashes  
**Does not change:** Product semantics, Architecture Decisions v0.2, API/OpenAPI v0.2, implementation scope, matching rules, permissions model, or Foundation baseline.

## Why this patch exists

The first real PostgreSQL execution gate against the v0.2 handoff exposed a duplicate foreign-key declaration that the previous static audit did not detect. The failure is valid and is treated as a release-blocking defect in the executable baseline.

The execution gate behaved exactly as intended: it prevented feature implementation from starting on a schema that had not yet proven clean runtime execution.

## Runtime blocker fixed

`consent_grants.evidence_observation_id -> observations.observation_id` was declared twice with the same constraint name `fk_consent_evidence_observation`:

- once immediately after `CREATE TABLE observations`;
- once in the authoritative `LATE FKs / CROSS-SECTION CONSTRAINTS` section.

**Resolution:** remove the earlier declaration and retain the late cross-section declaration.

Rationale: cross-section FKs are intentionally centralized late in the schema, after all participating tables exist. Retaining the late declaration makes the schema structure more consistent and easier to audit.

## Additional redundancy found during the patch review

A second semantic duplicate FK was found even though it did not use the same constraint name and therefore might not fail immediately:

`property_attributes.resolved_claim_id -> claims.claim_id`

It appeared once after `CREATE TABLE claims` and again in the v0.2 remediation-invariants section.

**Resolution:** remove the earlier declaration and retain the remediation-section declaration `fk_property_attribute_resolved_claim`.

This avoids redundant constraint enforcement and eliminates ambiguity about the authoritative declaration.

## Versioning decision

The original v0.2 artifact remains immutable as an historical failed-runtime candidate. Its published SHA-256 values are not rewritten.

The correction is released as:

- `schema_v0.2.1.sql`
- `seed_master_data_v0.2.1.sql`
- updated static audit `technical_pack_static_audit_v0.2.1.py`
- updated `STATIC_AUDIT_RESULTS_v0.2.1.json`

The handoff package is versioned as **v1.0.1**.

## Static-audit hardening

The v0.2.1 audit adds two checks that v0.2 lacked:

1. duplicate constraint-name detection on the same table;
2. semantic duplicate-FK detection when different constraint names enforce the same local columns -> referenced table/columns/delete behavior.

The corrected schema passes these checks with zero detected duplicate named or semantic FKs.

## Release status

v0.2.1 is still **CONDITIONAL GO** until the PostgreSQL 16+ execution gate is rerun successfully on a clean database:

1. create a fresh database;
2. execute `schema_v0.2.1.sql` with `ON_ERROR_STOP=1`;
3. execute `seed_master_data_v0.2.1.sql`;
4. execute the seed a second time for idempotency;
5. run the database contract / red-team tests;
6. only then freeze the technical database baseline and begin Slice 0.

## Developer instruction

Do not patch `schema_v0.2.sql` in place. Do not reuse its published hash. Use `schema_v0.2.1.sql` as the only executable database authority from this patch forward.
