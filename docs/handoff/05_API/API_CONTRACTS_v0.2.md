# TURAB — API Contracts v0.2

**Status:** implementation contract after Technical Architecture Review.  
**Machine-readable source:** `openapi_v0.2.yaml`  
**Database source:** `schema_v0.2.1.sql`  
**Product source:** TURAB Foundation Baseline v1.0 + Developer Reference Specification v0.1.

## 1. Contract hierarchy

When documents disagree, the order for implementation is:

1. TURAB Foundation Baseline v1.0 for product meaning and non-negotiable principles.
2. Architecture Decisions v0.2 for technical interpretation of those principles.
3. OpenAPI v0.2 for HTTP shape, role boundaries and DTOs.
4. Schema v0.2 for persistence invariants.
5. This document for command semantics and cross-cutting behavior.

No developer should infer product behavior from a single table or endpoint in isolation.

---

## 2. Mandatory cross-cutting behavior

### 2.1 Authentication and PARTY/ACCOUNT separation

A verified phone proves control of a contact point; it does **not** automatically create a PARTY or USER_ACCOUNT. Assisted records may exist with PARTY only. Account activation is an explicit flow.

### 2.2 Object-level authorization

Role checks are necessary but insufficient. The service MUST enforce object ownership/authorization:

| Actor | Resource | Authorization rule |
|---|---|---|
| CUSTOMER | own PARTY | bound to authenticated account.party_id |
| CUSTOMER | REQUEST | request.party_id = account.party_id or explicit delegated authority |
| CUSTOMER | PROPERTY | caller owns/manages/claimed it; otherwise public projection only |
| CUSTOMER | OPPORTUNITY | opportunity.request belongs to caller |
| STAFF | arbitrary entity | role + operational business purpose |
| PUBLIC | PROPERTY | only `PublicPropertySummary` produced by publication eligibility rules |

Customer arbitrary-id reads are intentionally separated under `/me/*`; staff reads use internal endpoints.

### 2.3 Idempotency

Every mutating authenticated POST command MUST accept a required `Idempotency-Key`. The server persists `(actor, route, key, request_hash, result)` in `idempotency_records`.

- same key + same payload hash → replay original result;
- same key + different payload hash → `409 Conflict`;
- provider webhook → deduplicate using provider event identity, not the API idempotency header.

### 2.4 Optimistic concurrency

Mutable projection PATCH requests require `If-Match-Version`. On stale version, return `409` and do not partially apply changes.

### 2.5 Error contract

Errors use `application/problem+json`. Domain failures should expose stable problem `type`/code values, not database exception text. Examples: `CONSENT_REVOKED`, `STALE_VERSION`, `HARD_GATE_FAILED`, `OBJECT_NOT_AUTHORIZED`, `IDENTITY_ALIAS_NOT_CANONICAL`.

### 2.6 Transaction boundaries

Commands changing critical market truth MUST be atomic. A price/document/location/availability command may write provenance + resolution + projection + audit in one transaction. Partial updates are unacceptable.

---

## 3. DTO boundary rules

### Public

`PublicPropertySummary` is the only public property representation. It MUST exclude staff notes, management mode, claim state, consent ids, seller expectations, provenance internals and hidden party data. Public properties require:

- `PROPERTY.supply_mode = PUBLIC`;
- at least one relevant active commercial context;
- active `PUBLIC_LISTING_ALLOWED` consent binding when consent is required by the flow;
- no withdrawn/closed offer as the only commercial context;
- price redaction according to `price_visibility`.

### Customer

Customer DTOs expose only information needed to manage their own requests/properties and consume opportunities. `CustomerOpportunityView` MUST enforce `sharing_scope`. Internal seller expectation or private claims are not customer fields even when used by matching.

### Staff

Staff DTOs may include operational metadata required for review, but access still requires a business purpose and audit context.

---

## 4. Command contracts by domain

## 4.1 OTP / Contact Point

### `POST /auth/otp/start`

Purpose is explicit:

- `VERIFY_PHONE_CONTROL`: verifies control without creating an account.
- `LOGIN`: may produce a session only when an account flow exists.

### `POST /auth/otp/verify`

Returns `PHONE_CONTROL_VERIFIED` or `SESSION_CREATED`. `account_id` is nullable by design. This preserves `PARTY ≠ USER_ACCOUNT`.

### `POST /parties/{party_id}/contact-points/phone`

Creates or reuses a normalized phone `CONTACT_POINT`, then links it to the PARTY. A contact point may be linked to multiple parties. The command MUST NOT merge parties merely because the phone matches.

---

## 4.2 Consent

### `POST /parties/{party_id}/consents`

Creates a granular grant (`ASSISTED_ENTRY`, `PUBLIC_LISTING_ALLOWED`, `PRIVATE_MATCHING_ONLY`, `CONTACT_BEFORE_SHARING`, or `COMMUNICATION_ARCHIVE`). The grant is not yet proof for a particular resource.

### `POST /consents/bindings`

Binds a granted consent to exactly one REQUEST, PROPERTY, PROPERTY_OFFER or communication thread for the same purpose. The server validates:

- grant exists and is GRANTED;
- purpose equals grant scope;
- consent party is related to the resource;
- binding is not already revoked.

### `POST /consents/{consent_id}/revoke`

Revokes future authority. Historical match/opportunity snapshots remain immutable. Any later share/activation that depended on the revoked consent MUST fail or move the opportunity to `NEEDS_CONFIRMATION` as appropriate.

---

## 4.3 External Leads / Assisted Entry

### `POST /external-leads`

Creates a discovery record only. It is not an active REQUEST or PROPERTY.

### `POST /external-leads/{lead_id}/convert`

Conversion is allowed only after contact/consent/data gates. A PROPERTY lead cannot convert to a REQUEST and vice versa. Conversion produces one domain resource and preserves source lineage.

### `POST /records/claim`

Claims an assisted record after verified control. It MUST reuse the existing REQUEST/PROPERTY; creating a duplicate is forbidden. The transaction records a claim event and changes the resource from `ASSISTED + UNCLAIMED` to the approved claimed/shared-management state.

---

## 4.4 REQUEST

### `POST /requests`

Required semantics include:

- explicit `transaction_intent = BUY | RENT`;
- party binding;
- management mode + claim state consistent with schema invariant;
- canonical DZD budgets;
- criteria using registry-backed codes.

Self-service creation uses `SELF_MANAGED + CLAIMED`. Assisted creation uses `ASSISTED + UNCLAIMED` until a claim command.

### `PATCH /requests/{request_id}`

Typed projection update only. It cannot set status, consent, claim ownership or silently change state. Critical value changes must still produce provenance/resolution inside the command implementation.

### `POST /requests/{request_id}/criteria`

Adds/changes structured criteria. A criteria mutation bumps the parent request version. No AI process may change Required/Preferred/Flexible values without explicit confirmed command.

### `POST /requests/{request_id}/state`

Dedicated state transition. Server validates allowed transition graph.

### `POST /requests/{request_id}/reconfirm`

Updates request freshness and records interaction/provenance. Reconfirmation is not equivalent to qualification.

---

## 4.5 PROPERTY / OFFER / SOURCE

### `POST /properties`

Creates a physical PROPERTY record. It is not a listing. For an externally discovered record, source and assisted consent must be preserved.

### `POST /properties/{property_id}/offers`

Creates a commercial OFFER by a specific PARTY. Multiple offers may coexist for one physical property.

### `PATCH /offers/{offer_id}`

Typed commercial terms update. Seller expectation is internal/confidential. A price change must update offer version and provenance.

### `POST /offers/{offer_id}/state`

Dedicated offer state transition. `WITHDRAWN/CLOSED` cannot continue as a current public commercial context.

### `POST /offers/{offer_id}/reconfirm`

Reconfirms commercial terms/freshness separately from physical property availability freshness.

### `POST /offers/{offer_id}/sources`

Links one or more source records. One source may be marked primary, but other sources are preserved.

### `POST /properties/{property_id}/reconfirm`

Reconfirms physical/property availability only. It does not automatically reconfirm price or permission.

---

## 4.6 Observation / Claim / Verification / Resolution

### `POST /observations`

Stores the raw observation: call note, message, post, form, image, document, import, etc.

### `POST /claims`

Creates an atomic claim at `DECLARED`. API clients cannot submit a higher verification level.

### `POST /claims/{claim_id}/verification-events`

Adds a verification event. A confirmed event may raise the claim's effective verification projection; conflict events mark the claim conflicting. Verification procedure and operator are auditable.

### `POST /resolutions`

Creates/supersedes the current operational resolved value. If a `source_claim_id` is used, subject and attribute MUST match the resolution. The command updates operational projection transactionally where the attribute maps to a core field.

---

## 4.7 Property Identity Resolution

### `POST /identity/candidates/generate`

Generates candidate pairs using deterministic/blocking signals. It never merges records automatically.

### `POST /identity/candidates/{candidate_id}/review`

Decisions:

- `CONFIRMED_DISTINCT`: preserve both records;
- `UNSURE`: keep pending information/review state;
- `CONFIRMED_SAME`: requires `canonical_property_id` from the candidate pair and creates `property_identity_aliases` in the same transaction.

No destructive merge. New matching targets canonical properties. Existing open opportunities affected by identity consolidation must be reviewed; duplicate open opportunities for the same request/canonical property are consolidated by an explicit workflow, not silent deletion.

---

## 4.8 Matching

### `POST /requests/{request_id}/matching/run`

The engine evaluates canonical properties only. Evaluation order:

1. transaction compatibility and hard gates;
2. Required criteria `PASS/FAIL/UNKNOWN`;
3. actionable unknown classification;
4. request freshness;
5. property freshness;
6. commercial/offer freshness;
7. permission scope;
8. soft ranking among eligible candidates;
9. diagnostic next action.

The result stores immutable snapshots and `input_hash`. If an OFFER is used, `evaluated_offer_id` and `offer_version` must be consistent. A non-POTENTIAL property requires an evaluated offer. A POTENTIAL property may use a structured commercial-context snapshot with no offer id.

### Match criteria

Each criterion result MUST retain:

- importance;
- request value;
- property/commercial value;
- `PASS | FAIL | UNKNOWN`;
- whether it blocks opportunity eligibility;
- delta when meaningful;
- evidence level/reference;
- stable reason code;
- rule id + rule version.

A soft score may exist only for internal ordering. It never overrides a hard FAIL or UNKNOWN gate.

### `POST /matches/{match_id}/review`

Human review is append-only. `NEED_MORE_INFORMATION` usually creates a focused Task. `APPROVED` is accepted only when all gates pass. Opportunity creation is a consequence of approved review, not a general public create endpoint.

---

## 4.9 Match Diagnostic

### `GET /requests/{request_id}/diagnostic`

Returns:

- opportunities/candidates ready;
- actionable blocking unknowns;
- near matches;
- main blocker counts;
- highest-value next information action;
- optional minimal meaningful relaxation scenarios.

Unknown-resolution work takes precedence over suggesting that the user relax a preference when resolving the unknown could yield an exact match.

The diagnostic never mutates REQUEST criteria automatically.

---

## 4.10 Tasks

### `GET /tasks`

Internal operational task list.

### `POST /tasks/{task_id}/complete`

Appends `task_completion_events` and marks task done in one transaction. `outcome_code`, note and evidence observation must be preserved; they must not disappear into application logs.

---

## 4.11 Opportunity

There is intentionally **no general `POST /opportunities`**.

Opportunity creation requires:

- canonical REQUEST × PROPERTY pair;
- candidate eligibility = `ELIGIBLE`;
- hard, information, freshness and permission gates all `PASS`;
- latest human match review = `APPROVED`;
- initial offer context equal to the evaluated commercial context when an offer exists.

Only one open Opportunity is allowed for the same REQUEST × PROPERTY.

### `POST /opportunities/{id}/revalidate`

Re-evaluates current request/property/offer freshness and permission without rewriting historical match snapshots. It may update current offer context or move validity to `NEEDS_CONFIRMATION/INVALID`.

### `POST /opportunities/{id}/share`

Before every share, revalidate current permission/consent and field-level sharing scope. Historical approval is not permanent authority after consent withdrawal.

### Customer response

`INTERESTED`, `NEED_MORE_INFORMATION`, `NOT_SUITABLE` produce interaction/outcome data. Rejection feedback can inform future diagnostics but never silently rewrites the REQUEST.

---

## 4.12 Communication / WhatsApp

Communication is a structured record, not merely a UI chat feature.

### `POST /communication/threads`

Creates a thread linked to the relevant PARTY and optional domain context.

### `POST /communication/threads/{thread_id}/messages`

Stores outbound/internal messages. Provider ids and delivery/read status are preserved.

### `POST /webhooks/whatsapp`

Provider event is first written to `webhook_events` and deduplicated by `(provider, provider_event_id)`. Only then is thread/message resolution performed. Replayed webhooks must not duplicate a message or interaction.

Critical decisions made by phone should be confirmed through a written official channel when operationally appropriate, but the platform stores them as operational records rather than claiming guaranteed legal evidentiary status.

---

## 5. Back Office queues

The API exposes explicit queue contracts for:

- external leads requiring contact/consent;
- requests requiring qualification/reconfirmation;
- properties requiring review/reconfirmation;
- candidate matches pending review;
- opportunities requiring follow-up/revalidation.

Queues are not generic search endpoints. Each item must state why it is actionable now and expose stable priority/reason information.

---

## 6. Matching snapshots — canonical minimum

A matching input snapshot MUST include enough data to replay the decision without reading current mutable state.

### Request snapshot

- request id/version;
- transaction intent;
- intent stage;
- budgets and flexibility;
- requested type/location;
- complete active criteria with importance/operator/value;
- request freshness timestamp/state.

### Property snapshot

- property id;
- property version;
- type/location/areas;
- resolved critical attributes used by rules;
- availability + confirmation time;
- identity status/canonicality.

### Commercial context snapshot

- offer id/version when present;
- transaction type;
- asking price / internal seller expectation used by rules;
- negotiability;
- price visibility;
- offer/commercial freshness;
- POTENTIAL willingness data when no offer exists.

### Permission snapshot

- consent/binding identifiers or structured reason for permission;
- purpose/scope;
- grant/binding status at evaluation time;
- allowed sharing scope.

### Freshness snapshot

- request, property and offer freshness source timestamps;
- thresholds/policy version;
- derived states.

Snapshots are internal and subject to privacy rules; they are not customer DTOs.

---

## 7. State-change rules that MUST NOT be implemented as PATCH

Dedicated commands are required for:

- request state transition;
- request/property/offer reconfirmation;
- offer state transition;
- consent grant/revoke/bind;
- assisted record claim;
- identity resolution;
- claim verification;
- resolution of current fact;
- match review;
- opportunity share/revalidate/close;
- task completion.

This prevents accidental bypass of audit, consent, provenance and business gates.

---

## 8. Minimum security requirements

- BOLA/IDOR tests for every customer resource endpoint.
- Secrets/provider webhook verification outside domain tables.
- `seller_expectation_dzd`, internal claims and staff notes never serialized to public/customer DTOs.
- Application role has no ordinary hard-delete capability on core market history.
- Audit actor/context set per database transaction where supported.
- Logs must not contain OTP codes or sensitive document payloads.
- Media/document URLs must be short-lived/authorized rather than globally public.

---

## 9. API freeze gate

The API may be declared **v0.2 implementation-frozen** only when:

- OpenAPI parses cleanly;
- every operation has a unique `operationId`;
- no local `$ref` is broken;
- mutating commands have required idempotency coverage;
- PATCH inputs are typed and reject undeclared fields;
- public/customer/internal DTO separation tests pass;
- object authorization rules have executable tests;
- PostgreSQL schema + seed execute successfully on a clean PostgreSQL 16 database.
