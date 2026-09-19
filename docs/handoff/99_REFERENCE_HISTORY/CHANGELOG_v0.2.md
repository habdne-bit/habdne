# TURAB Technical Pack — v0.2 Remediation Changelog

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

## Technical Patch v0.2.3 — 2026-09-19

- D6 correction: `schema_metadata.schema_version` now matches the published schema baseline (`0.2.3`).
- Operative machine artifacts are version-synchronized as v0.2.3 (schema, seed, OpenAPI, static audit/result, technical manifest).
- Added `verify_version_consistency.py` and integrated version-consistency checks into the static audit.
- Added `verify_v023_baseline.py` to preserve v0.2.1 FK fixes and v0.2.2 D1/D2 semantics while checking D6.
- v0.2.2 retained historically as runtime-validated but not frozen because of metadata mismatch.
- No domain, authorization, matching, consent, API-operation, role, or master-data semantic change.
