# TURAB — Architecture Decisions v0.2

**Status:** Accepted for implementation baseline, subject to PostgreSQL execution proof.  
**Date:** 2026-09-18  
**Supersedes:** technical assumptions in v0.1 where they conflict with this document.  
**Product baseline:** TURAB Foundation Baseline v1.0 + Developer Reference Specification v0.1.

## Purpose

This document records the architectural decisions adopted after the red-team review of Technical Pack v0.1. These decisions are not new product features. They are safeguards required so that the implementation preserves the product principles already approved: REQUEST and PROPERTY are first-class, PROPERTY is not a post, MATCH is not OPPORTUNITY, human review is mandatory before opportunity creation, and provenance/permission/freshness must remain auditable.

---

## ADR-01 — Matching Commercial Context

**Decision:** A match is still conceptually `REQUEST × PROPERTY`, but every match evaluation MUST also record the commercial context used to make price, transaction, permission and freshness decisions.

The request has an explicit `transaction_intent = BUY | RENT`. The match stores `evaluated_offer_id` when an offer is used. `evaluated_offer_id` may be null only for a `POTENTIAL` property evaluated from an internal willingness/commercial snapshot rather than an active offer. The immutable `commercial_context_snapshot` is the historical evidence of what the engine read.

**Why:** the same physical property may have multiple SALE offers, a RENT offer, different prices, different permissions and different freshness. Without commercial context, a price PASS cannot be reproduced or explained.

**Invariant:** Opportunity uniqueness remains at `REQUEST × canonical PROPERTY`, not `REQUEST × OFFER`.

---

## ADR-02 — Immutable Match Snapshots

**Decision:** Every `MATCH_CANDIDATE` stores immutable canonical snapshots of request, property, commercial context, permission and freshness, plus `input_hash`, rule/policy version and criterion results.

Version integers remain useful operational metadata but are not relied upon as the only replay mechanism.

**Why:** criteria, prices, documents, permissions and availability change. A reviewer must still be able to answer “why was this candidate proposed on that date?” without reading the current mutable state.

**Invariant:** match rows and human review rows are append-only historical records. A changed state produces a new evaluation/review; it does not mutate the old one.

---

## ADR-03 — Canonical Property Identity without Destructive Merge

**Decision:** Confirmed duplicate property records are resolved through `property_identity_aliases(alias_property_id → canonical_property_id)`. No source, offer, claim, evidence or historical record is deleted.

New matching MUST target canonical properties. An identity-resolution command is transactional: create alias mapping, mark the candidate `CONFIRMED_SAME`, then detect any affected open matches/opportunities and create review work where necessary.

**Why:** the same physical property may appear through several brokers/posts, but offers and provenance must remain separate.

**Invariant:** “same physical property” does not mean “same commercial offer.”

---

## ADR-04 — Resource-bound Consent

**Decision:** A consent grant by itself is insufficient proof for an operation. `resource_consent_bindings` binds a granted consent to a specific REQUEST, PROPERTY, PROPERTY_OFFER or communication thread and purpose.

The permission service validates party consistency, consent scope, current grant/revocation state and requested action. Match and opportunity snapshots record the permission evidence used at the time.

**Why:** a generic “this person consented” record can be mistakenly reused for the wrong property, request or purpose.

**Invariant:** revocation blocks future sharing/activation that relies on the revoked consent, while historical snapshots remain intact.

---

## ADR-05 — Operational Projection + Immutable Provenance

**Decision:** core tables (`requests`, `properties`, `property_offers`) are the current operational projection used by the product. Observations, claims, verification events and resolution history are immutable lineage.

Every command that changes a critical current fact MUST, in one transaction:

1. write or link the relevant observation/claim/evidence;
2. add the verification/resolution event when applicable;
3. update the operational projection;
4. write audit metadata.

The implementation MUST NOT expose a generic repository method that silently changes critical fields without the domain command.

**Why:** matching and UI need fast current fields, while trust and audit require the original history.

---

## ADR-06 — Public / Customer / Internal DTO Separation

**Decision:** the API does not expose one “Property” or “Opportunity” representation to every actor. Public, customer and staff views are different schemas.

Public browsing uses `PublicPropertySummary`. Customer-owned data is under `/me/*`. Internal arbitrary-id reads are restricted to staff roles. The server, not the frontend, performs field redaction based on sharing scope and authorization.

**Invariant:** internal fields such as seller expectation, consent ids, provenance internals, staff notes and management metadata MUST NOT appear in public/customer DTOs unless explicitly approved by the relevant sharing contract.

---

## ADR-07 — Contact Point ≠ Party ≠ Account

**Decision:** phone/email is modeled as a `CONTACT_POINT`. The same contact point may be linked to multiple parties; a phone number is not treated as the identity of a person/business. A USER_ACCOUNT optionally uses a verified login contact point.

Phone verification can occur without creating an account. Assisted PARTY records can therefore remain accountless.

**Why:** Algerian family/business/agency numbers can be shared, and assisted operations must not manufacture fake accounts.

---

## ADR-08 — Human Match Review is Append-only

**Decision:** `match_reviews` stores the sequence of decisions. `NEED_MORE_INFORMATION → APPROVED` produces two review rows. `latest_match_reviews` is a projection, not the history itself.

Opportunity creation requires the latest review to be `APPROVED` and all opportunity gates to pass.

---

## ADR-09 — Idempotency and Webhook Replay are First-class

**Decision:** mutating commands require `Idempotency-Key` unless the provider itself supplies a stable event id. The server persists idempotency records. WhatsApp/provider webhooks are deduplicated in `webhook_events(provider, provider_event_id)` before thread/message resolution.

**Why:** mobile retries, network timeouts and provider webhook retries are normal and must not create duplicate records/actions.

---

## ADR-10 — No Hard Delete of Core Market History

**Decision:** REQUEST, PROPERTY, OFFER, CLAIM, RESOLVED VALUE and OPPORTUNITY use state closure/supersession rather than normal hard deletion. The baseline schema contains defensive delete guards for core entities.

Join/technical tables may use cascade where the deletion does not erase market provenance.

---

## ADR-11 — Verification Cannot be Self-declared by API Clients

**Decision:** a newly created claim starts at `DECLARED`. `DOCUMENT_SEEN`, `DETAILS_MATCHED` and future professional verification levels are achieved only through `verification_events` and controlled service logic.

Resolved values that reference a claim must reference the same subject and attribute. The database includes lineage guards.

**Invariant:** AI extraction confidence is not a verification level.

---

## ADR-12 — Deterministic Core before AI

**Decision:** the foundational match engine uses deterministic, versioned rules for eligibility and diagnostic reasoning. Semantic/AI assistance may discover candidates or parse language, but cannot override hard gates, consent, freshness, verification or human approval.

The engine returns `PASS | FAIL | UNKNOWN` per criterion. Internal soft score is only an ordering aid.

---

## Explicitly Deferred

The following remain deliberately out of the foundational build: AVM, full event sourcing, RDF/W3C PROV storage, knowledge graph infrastructure, autonomous AI agents, Learning-to-Rank model, advanced solver/MaxSAT dependency, full CRM suite, in-app buyer/seller chat, payments, finance, digital signatures and complex monetization.

They may be prepared for structurally where inexpensive, but are not implementation requirements for the pilot.
