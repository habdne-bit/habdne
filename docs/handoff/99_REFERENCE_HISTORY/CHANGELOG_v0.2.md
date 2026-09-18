# TURAB Technical Pack — v0.2 Remediation Changelog

## v0.2.1 — PostgreSQL Execution Gate correction (2026-09-18)

Patch revision issued after the first real execution of the gate in
`04_DATABASE/POSTGRES_EXECUTION_GATE.md` on PostgreSQL 16.13.

**Defect.** `schema_v0.2.sql` declared `fk_consent_evidence_observation` twice —
once immediately after `CREATE TABLE observations` (section 9) and once in
section 15, *LATE FKs / CROSS-SECTION CONSTRAINTS*. Both declarations were
equivalent. PostgreSQL rejected the second:

```
ERROR:  constraint "fk_consent_evidence_observation" for relation
        "consent_grants" already exists
```

A clean database therefore could not accept the v0.2 schema at all. The static
audit did not detect this because it counts `REFERENCES` occurrences in file
text (133) rather than constraints a server actually creates (132).

**Resolution.** The section 9 declaration was removed. The constraint keeps its
home in section 15, which is the file's own designated place for cross-section
constraints, and remains byte-for-byte what v0.2 intended: same column, same
target, same `ON DELETE SET NULL`.

**Scope of change.** None of the domain model, workflow, permissions or matching
logic changes. Verified on the live database: 132 foreign-key constraints, with
`fk_consent_evidence_observation` present and enforcing.

**Affected artifacts** (synchronised per Handoff Master v1.0 §13):

- `04_DATABASE/schema_v0.2.sql` → renamed `04_DATABASE/schema_v0.2.1.sql`, duplicate removed, header notes the revision.
- `07_QA_ACCEPTANCE/technical_pack_static_audit_v0.2.py` — schema path updated; reported `foreign_key_refs` is now 132, matching the constraints actually created.
- `07_QA_ACCEPTANCE/STATIC_AUDIT_RESULTS_v0.2.json` — regenerated.
- `CHECKSUMS_SHA256.txt`, `07_QA_ACCEPTANCE/TECHNICAL_PACK_MANIFEST_SHA256_v0.2.txt`, `HANDOFF_MANIFEST.json` — regenerated.
- Filename references updated in `README.md`, `00_START_HERE/` (all three documents), `03_ARCHITECTURE/TECHNICAL_PACK_README_v0.2.md`, `04_DATABASE/POSTGRES_EXECUTION_GATE.md`, `05_API/API_CONTRACTS_v0.2.md`, `06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md`. Pointer updates only, no semantic change.
- `99_REFERENCE_HISTORY/MIGRATION_NOTES_v0.1_TO_v0.2.md` deliberately left untouched: it records the v0.1→v0.2 migration as performed and is history, not an implementation baseline.

**Gate status after this revision.** PASS — schema applies to a clean database,
seed is idempotent across two runs, 65/65 database-level contract tests pass
across all eleven areas the gate names, OpenAPI lints clean. See
`docs/gate/GATE_RUN_REPORT.md` in the implementation repository.

**Note on Handoff Master v1.0 §2.** That section records `133` foreign-key
references from the static audit of v0.2. The figure is now `132`. This is the
same database either way; the earlier number counted a textual duplicate that no
server ever created.

---

This release is a **breaking pre-implementation remediation** of v0.1. No production migration is assumed because v0.1 was explicitly marked NO-GO before implementation.

## P0 closures

### Matching commercial context
- Added request `transaction_intent` (`BUY|RENT`).
- Match stores `evaluated_offer_id`, offer version, commercial snapshot and offer freshness.
- Database rejects BUY↔RENT commercial mismatch.
- Potential property may omit offer id only under POTENTIAL supply mode.

### Historical replay
- Match stores immutable request/property/commercial/permission/freshness snapshots.
- Added canonical `input_hash` field.
- Match rows and match-review history are protected as immutable/append-only.

### Canonical property identity
- Added `property_identity_aliases` for non-destructive alias→canonical resolution.
- Added safeguards against alias chains.
- New matching is prohibited against alias property records.

### Consent
- Added `resource_consent_bindings` tying grant + purpose to exact domain resource.
- Added validation for request/offer/property/thread party consistency.
- Added API consent revoke and resource-binding commands.

### Privacy / BOLA
- Added separate Public, Customer and Internal DTOs.
- Customer arbitrary-id reads moved to `/me/*` contracts.
- Internal arbitrary-id endpoints exclude CUSTOMER role.
- Public properties no longer return internal Property DTO.

### PATCH bypass
- Generic arbitrary PATCH schemas replaced by typed whitelists.
- Stateful operations use dedicated commands.

### Truth lineage
- Claim creation can no longer self-upgrade verification.
- Effective verification is raised by verification events.
- Resolution/source-claim subject + attribute lineage enforced.
- Property attribute resolved-claim lineage enforced.

### Operational projection
- Explicitly adopted core current projection + immutable provenance contract.
- Request criteria and resolved current values touch parent versions.

## P1 closures

- Audit trigger now captures normalized entity id using trigger PK argument.
- Match review history changed from one row/match to append-only sequence.
- Task completion outcome/note/evidence persisted in `task_completion_events`.
- Added server-side `idempotency_records`.
- Added `contact_points` + many-to-many party linkage; removed phone-as-party-identity assumption.
- Assisted records require `ASSISTED + UNCLAIMED`; claimed resources move to shared/self-managed state through command.
- Matching policy is FK-backed through `matching_policy_id`, immutable and one-active-policy enforced.
- Added separate offer/commercial freshness.
- Added controlled legal/document options and criterion registry in seed data.
- Normalized reason codes and added remediation reasons.
- Added explicit Back Office queue API contracts.
- OTP verification can verify phone control without creating an account.
- Public publication contract requires active commercial/permission context.
- Added provider webhook replay store and provider-global external message identity.
- Added defensive hard-delete guards for core market history.

## P2 improvements

- All OpenAPI operations have stable unique `operationId`.
- Mutating POST commands have required idempotency coverage.
- `If-Match-Version` is required for typed PATCH operations.
- Request input schemas reject undeclared fields where appropriate.
- Locations are anonymous-safe for pre-login request/browse flows.
- Added API inventory and red-team acceptance tests.

## Still intentionally not done

- No AVM.
- No full event sourcing.
- No knowledge graph/RDF persistence.
- No autonomous AI match approval.
- No Learning-to-Rank model.
- No advanced solver dependency.
- No full in-app chat replacement for WhatsApp.
- No payments/finance/signature stack.
