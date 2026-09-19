# TURAB — Developer Adoption Checklist v1.0.2

This checklist is for adopting Technical Patch v0.2.2 before Slice 1.

## Integrity and authority

- [ ] I verified the handoff package against `HANDOFF_MANIFEST.json`.
- [ ] I read `TECHNICAL_PATCH_v0.2.2.md`.
- [ ] I did not patch v0.2.1 locally or reuse old hashes as v0.2.2.
- [ ] `verify_v022_baseline.py` returns PASS on the official package.

## D1 — canonical concurrency header

- [ ] OpenAPI parameter component remains named `IfMatchVersion`.
- [ ] Its actual HTTP header name is **`If-Match-Version`**.
- [ ] Its schema is integer, minimum 1.
- [ ] No mutable operation declares the old `If-Match` header.
- [ ] Runtime implementation removes the undocumented `If-Match` alias after adoption.

## D2 — PARTY optimistic versioning

- [ ] `parties.version` is `integer NOT NULL DEFAULT 1 CHECK (version > 0)`.
- [ ] PARTY updates use `bump_version_and_timestamp()`.
- [ ] The old timestamp-only PARTY trigger is absent.
- [ ] `Party` response schema exposes required `version`.
- [ ] `CustomerPartyView` exposes required `version`.
- [ ] `PartyCreate` and `PartyPatch` do **not** accept client-supplied `version`.

## Runtime re-freeze

- [ ] PostgreSQL 16+ clean DB accepts `schema_v0.2.2.sql`.
- [ ] `seed_master_data_v0.2.2.sql` executes twice without failure.
- [ ] FK count remains 131; prior duplicate-FK fixes remain intact.
- [ ] PostgreSQL Execution Gate passes.
- [ ] Existing expanded gate suite passes.
- [ ] Slice 0 suite passes after updating expectations.
- [ ] Party optimistic-concurrency acceptance tests pass (default 1, success increments, stale 409, failed mutation no bump).
- [ ] `/me/party` and internal Party responses expose the current version.
- [ ] OpenAPI drift check passes against `openapi_v0.2.2.yaml`.
- [ ] New baseline commit and SHA-256 values are recorded before Slice 1.

**Developer:** ____________________  
**Date:** ____________________  
**Product/Technical approval:** ____________________
