# TURAB — Implementation Slices v0.2

**Goal:** build the foundational pilot in vertical slices that preserve the approved domain rules and stop early if the core hypothesis cannot be represented cleanly.

This plan supersedes `IMPLEMENTATION_SLICES_v0.1.md` where they differ.

---

# Slice -1 — Architecture Gate / Tooling Baseline

## Objective

Prove that the remediated technical pack is executable before product code begins.

## Deliverables

- PostgreSQL 16 local/CI service.
- `schema_v0.2.sql` executes on an empty database.
- `seed_master_data_v0.2.sql` executes cleanly.
- migration reset script for development.
- OpenAPI lint/parse in CI.
- generated API inventory or SDK stubs using stable `operationId` values.
- static audit `PASS`.
- test fixtures for Adrar locations, parties, requests, properties/offers and consents.

## Mandatory tests

- all FKs/constraints/triggers install;
- second seed run is idempotent;
- only one matching policy can be active;
- Ksar Tililane and New City Tililane remain distinct canonical locations;
- hard delete of protected core entities fails.

## STOP GATE A

Do not continue if schema/seed cannot be rebuilt from zero reproducibly in CI.

---

# Slice 0 — Application Skeleton / Security Boundaries

## Objective

Create the service shell without prematurely implementing product features.

## Deliverables

- API service with structured problem responses.
- database transaction wrapper setting `app.account_id` and audit context.
- authentication middleware.
- role authorization middleware.
- object authorization policy layer.
- idempotency middleware backed by `idempotency_records`.
- optimistic concurrency helper for `If-Match-Version`.
- public/customer/internal serializer boundary.
- health/readiness endpoint and structured logs.

## Mandatory tests

- duplicate idempotency key with same payload replays result;
- duplicate key with different payload returns 409;
- customer cannot read another customer's resource by UUID;
- public DTO never contains internal consent/management/seller expectation fields.

---

# Slice 1 — PARTY / Contact Point / Account / Consent

## Objective

Represent real participants without manufacturing accounts and establish trustworthy permission foundations.

## Domain scope

`PARTY`, `CONTACT_POINT`, `PARTY_CONTACT_POINT`, `USER_ACCOUNT`, roles, consent grants, resource consent bindings.

## Deliverables

- create/read/update PARTY for staff.
- verified phone control independent from account activation.
- attach one contact point to several parties without merging them.
- activate account from a verified login contact point.
- create/revoke consent grant.
- bind consent to a specific resource/purpose.

## Mandatory tests

- phone verification alone creates no account unless LOGIN flow is explicitly completed;
- same phone can be related to two PARTY records;
- revoked consent cannot authorize a new share/activation;
- consent for Party A cannot bind to Request of Party B;
- property consent requires an active Party↔Property relationship.

---

# Slice 2 — REQUEST + Criteria + Freshness

## Objective

Make REQUEST a real operational entity rather than a saved filter.

## Deliverables

- self-managed request creation.
- assisted request creation (`ASSISTED + UNCLAIMED`).
- BUY/RENT transaction intent.
- structured criteria registry.
- typed request updates with provenance.
- state transitions.
- reconfirmation/freshness.
- record claim flow converting assisted record to shared/claimed management without duplication.

## Mandatory tests

- INTEREST never silently creates REQUEST.
- criteria mutation bumps request version.
- Required/Preferred/Flexible values cannot be changed by AI or background jobs.
- stale request becomes `NEEDS_CONFIRMATION` according to policy/workflow.
- assisted request cannot be inserted as CLAIMED.

## STOP GATE B

A staff operator must be able to understand exactly what the buyer wants, what is hard vs preferred, and when that information was last confirmed.

---

# Slice 3 — PROPERTY / OFFER / SOURCE / Truth Layer / Identity Lite

## Objective

Represent the physical market accurately before matching.

## Deliverables

- physical PROPERTY record.
- PUBLIC / PRIVATE / POTENTIAL supply modes.
- multiple PROPERTY_OFFER rows for same physical property.
- offer transaction type, price, price visibility, negotiability, seller expectation and separate commercial freshness.
- sources and offer-source links.
- party-property relations.
- observation → claim → verification → resolution workflow.
- controlled right/document options.
- identity candidate generation using deterministic signals.
- human identity review and non-destructive alias→canonical mapping.

## Mandatory tests

- same property may have owner sale + broker sale + rent offer simultaneously.
- seller expectation is not returned in public/customer DTOs.
- claim cannot be created as DOCUMENT_SEEN directly.
- verification event is required to upgrade effective verification.
- resolution cannot point to a claim from another property or another attribute.
- CONFIRMED_SAME without canonical alias mapping fails.
- new matching inputs must use canonical property, not alias.

## STOP GATE C

Before matching exists, the team must be able to answer:

- what is the physical property?
- what offers exist for it?
- who supplied each fact?
- what is current vs historical?
- which facts are declared vs checked?
- is the record canonical or an identity alias?

If any answer is ambiguous, do not start the match engine.

---

# Slice 4 — Deterministic Matching Core v0.2

## Objective

Produce explainable candidates with immutable historical inputs.

## Deliverables

- active matching policy loader.
- canonical property candidate generation.
- Request transaction intent ↔ Offer transaction compatibility.
- Hard Gate with `PASS / FAIL / UNKNOWN`.
- actionable unknown classification.
- soft ranking only after hard eligibility.
- request/property/offer freshness checks.
- permission gate using resource consent binding.
- immutable request/property/commercial/permission/freshness snapshots.
- canonical input hashing.
- criterion result persistence with reason and rule versions.

## Mandatory tests

1. BUY request cannot evaluate RENT offer.
2. Hard FAIL always blocks Opportunity.
3. Required UNKNOWN creates Need More Information, never silent PASS/FAIL.
4. `negotiable=true` above max budget is not automatic PASS.
5. seller expectation may support internal price compatibility without being exposed.
6. potential property may be evaluated without an offer only when structured willingness context exists.
7. old Match remains replayable after request, property and offer change.
8. match rows are immutable.
9. alias property cannot receive a new Match.
10. no valid match is a valid engine result.

## STOP GATE D

A human reviewer must be able to read a candidate and reconstruct every eligibility decision without an LLM.

---

# Slice 5 — Human Review → OPPORTUNITY

## Objective

Make OPPORTUNITY a meaningful reviewed outcome, not an algorithmic score.

## Deliverables

- pending review queue.
- append-only human review sequence.
- APPROVED / REJECTED / NEED_MORE_INFORMATION.
- automatic focused Task when information is missing.
- guarded Opportunity creation.
- one open Opportunity per Request × canonical Property.
- current commercial context with revalidation path.
- customer-safe Opportunity view.

## Mandatory tests

- `NEED_MORE_INFORMATION → APPROVED` preserves both decisions.
- approval fails if any required gate is not PASS.
- Opportunity cannot be created through a generic endpoint.
- initial offer context equals evaluated match offer when an offer exists.
- customer Opportunity never reveals private seller expectation/claims.
- same Request + same canonical Property cannot have two open Opportunities.

## STOP GATE E — Core Hypothesis Gate

At this point, without AI, the system must demonstrate end-to-end:

`REQUEST → PROPERTY/OFFER → deterministic candidate → human review → OPPORTUNITY`.

If this cannot be done correctly, stop. Do not add AI, WhatsApp, CRM or visual polish to hide a broken core.

---

# Slice 6 — Match Diagnostic / Information Work

## Objective

Answer not only “what matches?” but “what information/action is most valuable now?”

## Deliverables

- ready-candidate counts.
- blocking vs non-blocking unknowns.
- blocker summary.
- high-value information gap detection.
- focused operational tasks.
- near-match diagnostics.
- minimal meaningful relaxation suggestions for staff only.

## Rules

Information acquisition takes priority over preference relaxation when resolving the unknown could create an exact candidate. Relaxation never updates REQUEST automatically.

## Mandatory tests

- document UNKNOWN on otherwise exact candidate becomes higher-priority task than suggesting a new location.
- candidate failing three hard criteria does not receive high-priority task for an unrelated unknown.
- relaxation scenario reports magnitude (e.g. +150M centimes / adjacent area), not only “remove criterion.”

---

# Slice 7 — Communication / WhatsApp Record

## Objective

Centralize operational communication history without building a full proprietary chat platform.

## Deliverables

- communication threads and messages.
- interaction timeline.
- official WhatsApp Business integration boundary.
- provider event replay store.
- delivery/read status.
- staff notes and important confirmation linkage.

## Mandatory tests

- repeated provider webhook creates one message.
- same provider message id cannot be inserted into another thread.
- thread/opportunity links are checked by service invariant.
- phone decision can be linked to later written confirmation observation.

---

# Slice 8 — External Acquisition / Assisted Operations / Self-service

## Objective

Connect real Adrar market behavior to the structured core.

## Deliverables

- External Lead queues.
- short Call Brief: known / missing / permission needed.
- contact attempt outcome.
- assisted REQUEST/PROPERTY entry after consent.
- self-service create and claim flows.
- public browsing and Direct Interest.

## Mandatory tests

- external Facebook/Ouedkniss discovery cannot become active property without consent/workflow.
- Direct Interest remains INTEREST until explicit REQUEST conversion.
- assisted record claim reuses existing domain id.
- public browsing requires publication eligibility, not `supply_mode=PUBLIC` alone.

---

# Slice 9 — AI Assistance / Advanced Identity Signals

## Objective

Reduce manual work after deterministic core behavior is proven.

## Allowed AI scope

- extract proposed structured fields from Arabic/French/Algerian text;
- normalize local expressions and prices;
- propose location mapping;
- propose semantic candidate discovery;
- propose property-identity candidates;
- summarize calls/messages;
- verbalize deterministic explanation;
- flag contradictions/missing information.

## Prohibited AI scope

- creating Opportunity autonomously;
- changing REQUEST criteria silently;
- declaring legal verification;
- merging properties autonomously;
- exposing private commercial facts;
- sending sensitive communications without approved workflow.

## Data to retain

- model/provider/version;
- parser/prompt version;
- source observation;
- extraction confidence;
- proposal;
- human confirmation/correction/rejection;
- final outcome where applicable.

---

# Slice 10 — Pilot Instrumentation

## Objective

Measure whether TURAB proves the foundational hypothesis.

## Minimum pilot metrics

- Active Qualified Requests.
- Active / Potential Properties.
- Candidate Matches generated.
- AI/rule Candidate Approval Rate.
- Opportunities created.
- Time to First Opportunity.
- Actionable Unknown resolution time.
- Opportunity acceptance / rejection reasons.
- Stale Opportunity rate.
- identity-resolution review outcomes.
- source contribution by Facebook / WhatsApp / broker / self-service / other.

No vanity metric should replace Opportunity quality.

---

# Cross-slice non-functional Definition of Done

Every slice is complete only if:

- unit + integration tests pass;
- authorization tests cover positive and negative cases;
- idempotency/retry behavior is tested for commands;
- audit/provenance is not silently skipped;
- OpenAPI remains synchronized with implementation;
- migration can rebuild an empty environment;
- no new feature bypasses Foundation/Design Ledger;
- data needed by future learning is preserved without adding premature ML complexity.
