# TURAB — File Authority & Version Policy

## 1. Authority order

1. Product meaning: `TURAB_Foundation_Baseline_v1.0_FINAL.docx`
2. Decision method: `TURAB_Project_Instructions_v1.0.md`
3. Accepted technical architecture: `ARCHITECTURE_DECISIONS_v0.2.md`; latest patch authority: `TECHNICAL_PATCH_v0.2.3.md`
4. Detailed behavior: `TURAB_Developer_Reference_Spec_v0.1.*`
5. API behavior: `API_CONTRACTS_v0.2.md` + `openapi_v0.2.3.yaml`; v0.2.3 preserves the v0.2.2 D1/D2 semantics and changes only the D6 version-stamp baseline identity
6. Database baseline candidate: `schema_v0.2.3.sql` + `seed_master_data_v0.2.3.sql`
7. Build order: `IMPLEMENTATION_SLICES_v0.2.md`
8. Release/acceptance: `POSTGRES_EXECUTION_GATE.md` + `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` + `verify_v023_baseline.py` + `verify_version_consistency.py`

## 2. Conflict rule

Do not silently resolve a contradiction. Product semantics defer upward to the Foundation. Technical Patch v0.2.3 supersedes v0.2.2 only for the explicit D6 metadata/version-consistency correction documented in the patch. All v0.2.2 D1/D2 semantics and all v0.2.1 FK remediations remain in force. If same-level contracts disagree, stop the affected implementation and raise a change/clarification before coding around it.

## 3. Immutability and supersession

- Published packages are immutable evidence. Never edit an older handoff in place.
- v0.2.1 is retained as the previously frozen executable baseline before D1/D2.
- v0.2.2 is retained as `RUNTIME_VALIDATED_BUT_NOT_FROZEN_DUE_TO_D6_METADATA_MISMATCH`.
- v0.2.3 is a new adoption candidate. It becomes the active frozen baseline only after the full rerun and re-freeze.
- Any later correction must receive a new technical patch and handoff version with new checksums.

## 4. Files not to use for new implementation

Do not use old machine baselines for new work after v0.2.3 adoption, including:

- `schema_v0.2.sql`, `schema_v0.2.1.sql`, or `schema_v0.2.2.sql`;
- `openapi_v0.2.yaml` or `openapi_v0.2.2.yaml`;
- technical manifests from older baselines except as historical evidence.

Files in `99_REFERENCE_HISTORY` explain history; they do not override the current baseline.
