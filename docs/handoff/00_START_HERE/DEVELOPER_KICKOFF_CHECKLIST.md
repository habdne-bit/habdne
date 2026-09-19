# TURAB — Developer Adoption Checklist v1.0.3

This checklist is for adopting Technical Patch v0.2.3 before Slice 1.

## A. Package integrity and authority

- [ ] I read `README.md` and the complete `00_START_HERE` folder.
- [ ] I read `TECHNICAL_PATCH_v0.2.3.md` and understand that D6 is metadata/version consistency only.
- [ ] I understand that v0.2.2 was runtime-validated but intentionally not frozen because of D6.
- [ ] I did not patch v0.2.2 locally or reuse old hashes as v0.2.3.
- [ ] `verify_handoff.py` returns PASS on the official package.
- [ ] `verify_v023_baseline.py` returns PASS.
- [ ] `verify_version_consistency.py` returns PASS and all version claims are `0.2.3`.
- [ ] `technical_pack_static_audit_v0.2.3.py` returns PASS with 131 FK references.

## B. Preserved technical decisions

- [ ] `If-Match-Version` remains the only canonical concurrency header and accepts integer versions only.
- [ ] `If-Match` and ETag syntax are not compatibility aliases.
- [ ] `parties.version` remains `integer NOT NULL DEFAULT 1 CHECK (version > 0)`.
- [ ] PARTY updates use `bump_version_and_timestamp()`.
- [ ] `Party` and `CustomerPartyView` expose `version`; `PartyCreate` and `PartyPatch` do not accept it.
- [ ] Both v0.2.1 duplicate-FK corrections remain present and each corrected FK exists exactly once.
- [ ] `party_property_relations` is not treated as authorization authority.
- [ ] RFC-001 r3 remains final; maker-checker and deny-by-default rules are unchanged.

## C. D6-specific checks

- [ ] schema filename = `schema_v0.2.3.sql`.
- [ ] schema header declares v0.2.3.
- [ ] `schema_metadata.schema_version = '0.2.3'`.
- [ ] seed filename/header declare v0.2.3 and seed semantics are unchanged.
- [ ] OpenAPI filename and `info.version` declare 0.2.3; API operation/role semantics are unchanged.
- [ ] static-audit script/result and technical-pack manifest filenames declare v0.2.3.
- [ ] `HANDOFF_MANIFEST.json` declares technical baseline v0.2.3 candidate.

## D. Runtime re-freeze gate

- [ ] PostgreSQL 16+ clean DB accepts `schema_v0.2.3.sql`.
- [ ] Live query confirms `turab.schema_metadata.schema_version = '0.2.3'`.
- [ ] `seed_master_data_v0.2.3.sql` executes twice without failure.
- [ ] Expanded database/red-team gate passes.
- [ ] Current Slice 0 suite passes completely.
- [ ] Authorization Evidence Matrix has no `UNPROVEN` rule.
- [ ] OpenAPI runtime drift check passes against `openapi_v0.2.3.yaml`.
- [ ] Full gate passes twice on clean/recreated database state.
- [ ] New baseline commit and SHA-256 values are recorded.

## E. Release rule

- [ ] v0.2.3 is not called FROZEN merely because this package exists.
- [ ] Slice 1 does not start until the complete rerun is green and v0.2.3 is explicitly re-frozen.
