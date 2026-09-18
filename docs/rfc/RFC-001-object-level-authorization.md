# RFC-001 — Object-Level Authorization

**Status:** PROPOSED — awaiting review. **No authorization code will be written until this is accepted.**
**Slice:** 0 — Application Skeleton / Security Boundaries
**Date:** 2026-09-18
**Baseline:** Handoff v1.0.1, technical baseline frozen at commit `f833fe7d05e160b048a6de1c4120f2c79015c3bb`

## Sources

This RFC derives from the frozen artifacts and adds no new product semantics. Where
it proposes something the artifacts do not already fix, that is marked **[DECISION]**
and listed in §13. Nothing marked **[DECISION]** is implemented before it is ruled on.

| Source | Used for |
|---|---|
| `05_API/openapi_v0.2.yaml` | `x-roles` and `x-authorization` on 57 operations — the machine-readable authority |
| `05_API/API_CONTRACTS_v0.2.md` §2.2, §3, §8 | object-authorization table, DTO boundary rules, minimum security |
| `03_ARCHITECTURE/ARCHITECTURE_DECISIONS_v0.2.md` ADR-04, ADR-06, ADR-07 | resource-bound consent, DTO separation, contact/party/account separation |
| `04_DATABASE/schema_v0.2.1.sql` | `account_role`, `user_account_roles`, `party_property_relations`, consent tables, `app.account_id` audit context |
| `00_START_HERE/TURAB_Developer_Handoff_Master_v1.0.1.md` §4, §6.6 | invariants 11–12, 17; API security boundaries |
| `07_QA_ACCEPTANCE/RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` K01–K04, D02 | mandatory acceptance cases |
| `docs/api/API_INVENTORY_GENERATED.md` | generated from the frozen contract; the table the policy layer is checked against |

Schema facts below were verified by query against the gate database, not read from prose.

---

## 1. Principles

1. **Deny by default.** An operation is permitted only by an explicit rule. Absence
   of a rule is denial, never a default allow.
2. **Role is necessary, never sufficient** (`API_CONTRACTS` §2.2). Every operation on
   an identified object requires a role check *and* an object check.
3. **Authorization is server-side** (Master §4, invariant 17; ADR-06). The frontend
   is never trusted to hide a field. A DTO that must not contain a value must not be
   constructed with it.
4. **Authorization is not consent** (§7). Both are required where both apply, and
   neither substitutes for the other.
5. **Authorization decisions are auditable.** Every decision runs inside the request
   transaction that sets `app.account_id`, so `audit_row_change()` attributes the
   actor.

---

## 2. Roles

`account_role` is a closed enum of four values. `user_account_roles` has primary key
`(account_id, role)` — verified — so **an account may hold several roles
simultaneously**.

| Role | Purpose | Object scope |
|---|---|---|
| `CUSTOMER` | A market participant acting for their own PARTY | Only objects reachable from `account.party_id` |
| `OPERATOR` | Staff who gather and record market truth | Arbitrary objects, with business purpose |
| `REVIEWER` | Staff who approve decisions | Arbitrary objects, read + decision endpoints |
| `ADMIN` | Full staff authority | Arbitrary objects |

**Roles are not hierarchical.** `ADMIN` is broader in practice only because it is
listed on every staff operation in the OpenAPI, not because the service computes
`ADMIN ⊃ REVIEWER ⊃ OPERATOR`. The service MUST evaluate the literal `x-roles` list
of the operation. Implementing implicit inheritance would silently grant `OPERATOR`
the match-review authority that §6 deliberately withholds.

### 2.1 Separation of duties is a real design, not an accident

Reading the frozen `x-roles` across all 57 operations, staff authority splits:

| Operation | ADMIN | OPERATOR | REVIEWER |
|---|:-:|:-:|:-:|
| `POST /observations`, `POST /claims` | ✓ | ✓ | — |
| `POST /external-leads`, `.../convert` | ✓ | ✓ | — |
| `POST /communication/threads[/messages]` | ✓ | ✓ | — |
| `POST /matches/{id}/review` | ✓ | — | ✓ |
| `POST /identity/candidates/{id}/review` | ✓ | — | ✓ |
| `GET /audit` | ✓ | — | ✓ |
| `POST /opportunities/{id}/share` | ✓ | ✓ | — |
| `POST /claims/{id}/verification-events` | ✓ | ✓ | ✓ |

This is **maker–checker**: the actor who records market truth (`OPERATOR`) cannot
approve the match that turns it into an OPPORTUNITY, and the actor who approves
(`REVIEWER`) does not perform the outward share. `REVIEWER` also holds `/audit`,
which `OPERATOR` does not. The service MUST preserve this split exactly.

---

## 3. The subject

The authenticated subject is resolved once per request into an immutable value:

```
Subject {
  account_id : uuid          -- from the verified bearer token
  party_id   : uuid | null   -- user_accounts.party_id
  roles      : set<account_role>
}
```

Three verified schema facts drive the rules below:

1. **`user_accounts.party_id` is nullable.** A staff account need not have a PARTY.
2. **The FK is `ON DELETE SET NULL`.** Deleting a PARTY silently detaches its account
   rather than failing. (`parties` carries no hard-delete protection — only
   `requests`, `properties`, `property_offers`, `claims`, `resolved_values` and
   `opportunities` do. A PARTY holding any of those cannot be deleted because those
   FKs are `ON DELETE RESTRICT`, but a bare PARTY can.)
3. **An account may hold multiple roles.**

**Rules.**

- **R3.1** A subject with `CUSTOMER` and `party_id = NULL` is denied every
  object-scoped operation. A null owner never matches an owner check. This must be
  an explicit guard, not an emergent consequence of `NULL` comparison, because
  `NULL = NULL` is `NULL` in SQL and a careless predicate can invert into an allow.
- **R3.2** `party_id` is read from the database per request, never from the token.
  A token minted before a PARTY was detached must not keep conferring access.
- **R3.3 [DECISION]** When one account holds both a staff role and `CUSTOMER`
  (§13, Q3), authorization is evaluated **per operation** against the operation's
  `x-roles`, and the customer object check applies whenever the operation is reached
  via the `CUSTOMER` role. Proposed: a staff role never widens `/me/*`, and
  `CUSTOMER` never widens an internal endpoint.

---

## 4. Resource ownership and relationships

There is no generic "owner" column. Authority is derived per resource type from a
distinct relationship. This is the authority graph the policy layer implements.

| Resource | Customer authority derives from | Verified mechanism |
|---|---|---|
| `PARTY` | identity | `party.party_id = subject.party_id` |
| `REQUEST` | ownership | `requests.party_id = subject.party_id` |
| `PROPERTY` | **relationship, not a column** | a row in `party_property_relations` for `(subject.party_id, property_id)` that is currently valid |
| `PROPERTY_OFFER` | ownership | `property_offers.party_id = subject.party_id` |
| `OPPORTUNITY` | transitive via request | `opportunities.request_id → requests.party_id = subject.party_id` |
| `INTEREST` | ownership | `interests.party_id = subject.party_id` |
| `CONSENT_GRANT` | ownership | `consent_grants.party_id = subject.party_id` |
| `COMMUNICATION_THREAD` | ownership | `communication_threads.party_id = subject.party_id` |

### 4.1 Property authority

`properties` has **no `party_id`**. Authority comes from `party_property_relations`,
whose `relation_code` is constrained to `OWNER_DECLARED`, `BROKER`, `AGENCY`,
`DEVELOPER`, `OCCUPANT`, `CONTACT_PERSON`, `OTHER`, and which carries
`valid_from`/`valid_to`.

- **R4.1** A property relation authorizes only while current:
  `(valid_from IS NULL OR valid_from <= now()) AND (valid_to IS NULL OR valid_to > now())`.
  This is the same currency predicate `enforce_consent_binding()` already applies to
  property-scoped consent, so the two agree by construction.
- **R4.2 [DECISION]** Which `relation_code` values confer *write* authority. The
  schema treats all seven alike. Proposed: `OWNER_DECLARED`, `BROKER`, `AGENCY`,
  `DEVELOPER` confer read+write; `OCCUPANT`, `CONTACT_PERSON`, `OTHER` confer read
  only. Rationale: an occupant or a contact person is not commercially empowered to
  alter offers. See §13 Q1.
- **R4.3** `verification_level` on the relation is **not** an authorization input.
  A `DECLARED` relation authorizes exactly as a `PROFESSIONAL_CHECK` one does.
  Verification governs trust in market truth, not access. Conflating them would make
  access silently expand when an unrelated verification event fires.

### 4.2 Canonical identity and authority

- **R4.4** Authority checks resolve through `property_identity_aliases` to the
  canonical property first. A customer authorized on an alias property is authorized
  on the canonical record, because identity resolution is non-destructive (ADR-03)
  and must not strip a real party of access to their own property.

### 4.3 Management mode and claim state

`management_mode ∈ {SELF_MANAGED, ASSISTED, SHARED_MANAGEMENT}` with the schema
invariant `ASSISTED ⇔ UNCLAIMED` and `{SELF_MANAGED, SHARED_MANAGEMENT} ⇔ CLAIMED`.

Per `x-authorization` on `POST /records/claim`, claiming moves a record
`ASSISTED/UNCLAIMED → SHARED_MANAGEMENT/CLAIMED`.

- **R4.5** An `ASSISTED + UNCLAIMED` record has **no authorized customer**. It is
  staff-operated. Customer access begins at the claim command.
- **R4.6** `SHARED_MANAGEMENT` means staff authority and customer authority coexist.
  It does not reduce staff authority.

---

## 5. `/me/*` semantics

Four operations exist, all `CUSTOMER`-only: `GET /me/party`,
`/me/requests/{id}`, `/me/properties/{id}`, `/me/opportunities/{id}`.

- **R5.1** `/me/*` accepts **no arbitrary party id**. The subject is the only
  identity input (`x-authorization` on `GET /me/party`).
- **R5.2** A path id under `/me/*` is a *filter*, never a selector. The query is
  written as "this object **and** it belongs to me" in one statement. It is never
  "fetch, then compare in application code" — a fetch-then-compare has already read
  the row and invites a later refactor that returns it.
- **R5.3 [DECISION]** `/me/*` authorization failure returns **404**, not 403.
  Rationale: `GET /me/properties/{id}` carries `x-authorization` "otherwise 404/403",
  and both codes are declared on every operation, so the contract permits either.
  A 403 on `/me/*` confirms that an id exists, turning the endpoint into an existence
  oracle for UUIDs — precisely what K01/K02 guard against. Internal staff endpoints
  keep **403** with `OBJECT_NOT_AUTHORIZED`, since a staff caller is already trusted
  to know that objects exist. See §13 Q2.
- **R5.4** Staff do not use `/me/*`. Internal reads use
  `GET /parties|requests|properties|opportunities/{id}`, whose `x-roles` exclude
  `CUSTOMER` (K01).

---

## 6. Operator and reviewer access

Staff hold no ownership, so the object check takes a different form.

- **R6.1** Staff object access requires the operation's role **and** a recorded
  business purpose. `API_CONTRACTS` §2.2 and §3 both require purpose, and §8 requires
  audit actor/context per transaction.
- **R6.2** Purpose is satisfied structurally by the audit context: every staff request
  runs in a transaction that sets `app.account_id` and `app.audit_context`, which
  `audit_row_change()` reads — verified in the schema. A staff read of an arbitrary
  object is permitted but **recorded**.
- **R6.3 [DECISION]** Whether staff *reads* are logged to `audit_log` as well as
  writes. `audit_row_change()` fires on INSERT/UPDATE/DELETE only, so reads are not
  captured today. Proposed: staff reads of customer-scoped objects emit a structured
  access log entry (not an `audit_log` row, which is row-change shaped) carrying
  actor, object, operation and trace id. See §13 Q4.
- **R6.4** `REVIEWER` must not be granted the `OPERATOR` data-entry operations, and
  an account SHOULD NOT hold both, or maker–checker (§2.1) collapses into one person.
  **[DECISION]** whether this is enforced by the service or by administrative policy
  (§13 Q3).

---

## 7. Consent versus authorization

This distinction is the one most likely to be collapsed in implementation, so it is
stated sharply.

|  | Authorization | Consent |
|---|---|---|
| Question | *May this actor act on this object?* | *Has the data subject permitted this purpose for this resource?* |
| Subject | the **caller** | the **data subject** (often not the caller) |
| Source | roles + ownership/relationship | `consent_grants` + `resource_consent_bindings` |
| Failure | `403` / `404`, `OBJECT_NOT_AUTHORIZED` | `409`, `CONSENT_REVOKED` or a permission-gate failure |
| Revocation | not a concept | first-class, blocks future use (ADR-04) |

- **R7.1 Both are required, neither substitutes.** An `OPERATOR` is authorized to call
  `POST /opportunities/{id}/share` yet MUST be refused when no valid consent binding
  covers the share. Conversely a party's `PUBLIC_LISTING_ALLOWED` grant confers no
  read access on any *other* customer: consent is not a grant of access to a caller.
- **R7.2** Consent is resource-bound and purpose-bound (ADR-04). The database already
  enforces this in `enforce_consent_binding()` — verified: grant must exist and be
  `GRANTED`, `grant.scope` must equal `binding.purpose`, and the consenting party must
  actually relate to the resource. The service MUST NOT re-implement a looser version
  of a rule the database enforces strictly.
- **R7.3** Revocation blocks future use and never rewrites history (ADR-04, Master
  §6.5). An already-created OPPORTUNITY keeps its immutable permission snapshot; what
  fails is the *next* share or activation.
- **R7.4** Authorization is evaluated **before** consent. A caller with no authority
  must not learn from an error message whether a consent exists for an object they
  cannot see.
- **R7.5** `POST /consents/bindings` is `ADMIN`/`OPERATOR` only — customers cannot
  bind their own consent — while `POST /consents/{id}/revoke` admits `CUSTOMER` for
  their own grant. Revocation is deliberately easier than granting. The service MUST
  NOT "helpfully" let a customer create bindings.

---

## 8. Sharing scopes

`sharing_scope ∈ {SUMMARY_ONLY, PROPERTY_DETAILS_ALLOWED, CONTACT_AFTER_CONFIRMATION}`,
stored `NOT NULL` on `opportunities` and as `permission_scope` on `property_offers`.

- **R8.1** `sharing_scope` is an **output filter**, not an access gate. It does not
  decide whether a caller may read an opportunity — §4 does. It decides how much of
  it is rendered.
- **R8.2 [DECISION]** The exact field sets. The enum names the levels; no frozen
  artifact enumerates fields per level. Proposed, and intentionally the narrowest
  reading consistent with `x-authorization` on `GET /me/opportunities/{id}`:

  | Scope | `CustomerOpportunityView` renders |
  |---|---|
  | `SUMMARY_ONLY` | `opportunity_id`, `status`, `validity_status`, `sharing_scope`, `why_real`, `known_differences`, `created_at`, `shared_at`; `property` reduced to type, location and area bands |
  | `PROPERTY_DETAILS_ALLOWED` | the above plus the full `CustomerPropertyView` and public offer terms subject to `price_visibility` |
  | `CONTACT_AFTER_CONFIRMATION` | the above plus counterparty contact, released **only** after a recorded confirmation event |

  See §13 Q5.
- **R8.3** `CONTACT_AFTER_CONFIRMATION` releases contact data only on evidence of the
  confirmation, never on the scope value alone. The scope names a precondition; it is
  not itself the satisfaction of it.
- **R8.4** Scope is re-evaluated at **every** share (`API_CONTRACTS` §4.11): "Historical
  approval is not permanent authority after consent withdrawal." A cached rendering
  is not reused across shares.

---

## 9. Field-level DTO filtering

- **R9.1 Separate types, not filtered dictionaries.** `PublicPropertySummary`,
  `CustomerPropertyView`, `OperatorPropertyView` and `InternalOpportunityView` are
  distinct schemas in the frozen OpenAPI. The service constructs the target type
  explicitly. It never serializes an internal entity and deletes keys — a
  delete-keys approach fails open the moment a column is added.
- **R9.2 Never-serialized set.** These MUST NOT appear in any public or customer DTO
  (`API_CONTRACTS` §3, §8; Master §6.6; K03, D02):
  `seller_expectation_dzd`, consent ids and consent internals, `management_mode`,
  `claim_status`, staff notes, provenance internals (observation/claim/resolution
  internals), match and permission snapshots, `approved_match_id`, and internal
  identity metadata.
- **R9.3** `seller_expectation_dzd` may be read by the matching engine and MUST NOT be
  rendered, nor inferable from a customer-facing explanation (D02). An explanation
  that says "below the seller's private expectation" leaks it just as surely as the
  number would.
- **R9.4** `price_visibility ∈ {PUBLIC, ON_REQUEST, PRIVATE}` governs price rendering
  independently of scope; the stricter of the two always wins.
- **R9.5 Enforced by test, not by review.** A DTO test asserts the *full* key set of
  each public/customer response against an allow-list, so a newly added column fails
  the test rather than silently shipping (K03).

---

## 10. Deny-by-default and the decision pipeline

Every authenticated request passes the same ordered pipeline. Each stage can only
deny; none can re-grant what an earlier stage denied.

```
1. Authenticate            → 401 if the bearer token is absent or invalid
2. Resolve Subject         → account_id, party_id (from DB), roles
3. Route policy lookup     → NO POLICY ⇒ DENY (fail closed)
4. Role check              → 403 unless subject.roles ∩ operation.x-roles ≠ ∅
5. Load object scoped      → single query filtered by the authority predicate
                             absent ⇒ 404 on /me/*, 403 internal (R5.3)
6. Object authorization    → the §4 predicate for this resource type
7. Consent / permission    → only for operations that share or activate (§7)
8. Execute in transaction  → sets app.account_id + app.audit_context
9. Render                  → target DTO type by actor class, then sharing scope (§8, §9)
```

- **R10.1** Stage 3 is the deny-by-default guarantee: the policy table is keyed by
  `(method, route template)` and a request that matches no entry is denied. A new
  endpoint is therefore unreachable until someone writes its policy — the failure
  mode is an outage, not a leak.
- **R10.2** A startup assertion cross-checks the policy table against
  `openapi_v0.2.yaml`: every operation with `x-roles` MUST have a policy entry whose
  roles equal the contract's, and no policy may exist for an unknown operation. The
  contract and the code cannot drift silently.
- **R10.3** Stage 5 is a single scoped query. There is no unscoped `findById`
  reachable from a request path. **[DECISION]** whether this is enforced by
  architecture test (§13 Q6).
- **R10.3a** Exactly one authenticated operation carries no `x-roles`:
  `GET /reason-codes`. Under R10.1 it is therefore denied to everyone until
  §13 Q8 is decided. Generated evidence: `docs/api/API_INVENTORY_GENERATED.md`.
- **R10.4** The six unauthenticated operations — `GET /locations`,
  `GET /master/criterion-definitions`, `GET /public/properties`, `POST /auth/otp/start`,
  `POST /auth/otp/verify`, `POST /webhooks/whatsapp` — are an explicit closed list
  asserted in a test. Anything else lacking `security` is a defect.
- **R10.5** `POST /webhooks/whatsapp` is unauthenticated but **not** unverified: it
  requires provider signature verification and `(provider, provider_event_id)`
  deduplication (`API_CONTRACTS` §4.12, §8), outside domain tables.

---

## 11. Representative allow / deny scenarios

Each becomes an executable test. **A** = allow, **D** = deny.

### Customer scope

| # | Scenario | Expected |
|---|---|---|
| S01 | Customer A reads own request via `GET /me/requests/{A}` | **A** 200 |
| S02 | Customer A reads Customer B's request id via `/me/requests/{B}` | **D** 404 (K02) |
| S03 | Customer A calls internal `GET /requests/{A}` — own object, wrong endpoint | **D** 403, role excludes `CUSTOMER` (K01) |
| S04 | Customer A reads a party by guessed UUID via `GET /parties/{B}` | **D** 403 (K01) |
| S05 | Customer with `party_id = NULL` calls any `/me/*` | **D** 403 (R3.1) |
| S06 | Customer A `PATCH /requests/{B}` | **D** 404/403 before any field validation |
| S07 | Customer A sends `status` or `claim_status` in a typed PATCH | **D** 422 (K04) |
| S08 | Customer A `POST /interests` with `party_id` = B | **D** 403 (R4, interests) |
| S09 | Customer A responds to an opportunity whose request is B's | **D** 404 |

### Property relationships

| # | Scenario | Expected |
|---|---|---|
| S10 | Customer with current `OWNER_DECLARED` relation reads `/me/properties/{id}` | **A** 200 |
| S11 | Same customer after `valid_to` has passed | **D** 404 (R4.1) |
| S12 | Customer with `OCCUPANT` relation calls `PATCH /offers/{id}` | **D** 403 under proposed R4.2 |
| S13 | Customer authorized on an alias property reads the canonical | **A** 200 (R4.4) |
| S14 | Any customer reads an `ASSISTED + UNCLAIMED` property | **D** 404 (R4.5) |
| S15 | Same record after a successful `POST /records/claim` | **A** 200, now `SHARED_MANAGEMENT` |
| S16 | Customer relation is `DECLARED` rather than verified | **A** 200 (R4.3) |

### Staff and separation of duties

| # | Scenario | Expected |
|---|---|---|
| S17 | `OPERATOR` reads an arbitrary request internally | **A** 200, audit context recorded |
| S18 | `OPERATOR` calls `POST /matches/{id}/review` | **D** 403 (§2.1) |
| S19 | `REVIEWER` calls `POST /observations` | **D** 403 (§2.1) |
| S20 | `REVIEWER` calls `POST /opportunities/{id}/share` | **D** 403 (§2.1) |
| S21 | `OPERATOR` calls `GET /audit` | **D** 403 (§2.1) |
| S22 | `REVIEWER` approves a match with every gate `PASS` | **A** 201 |
| S23 | Any staff writes with `app.account_id` unset | **D** — transaction wrapper refuses |

### Consent versus authorization

| # | Scenario | Expected |
|---|---|---|
| S24 | `OPERATOR` shares an opportunity with a valid binding | **A** 200 |
| S25 | Same share after the consent is revoked | **D** 409 `CONSENT_REVOKED` (R7.3) |
| S26 | Historical match snapshot read after that revocation | **A** — snapshot intact (R7.3) |
| S27 | Customer B grants `PUBLIC_LISTING_ALLOWED`; Customer A reads B's property | **D** 404 — consent is not access (R7.1) |
| S28 | Binding whose purpose ≠ grant scope | **D** 409, DB-enforced (R7.2) |
| S29 | Customer calls `POST /consents/bindings` for own grant | **D** 403 (R7.5) |
| S30 | Customer revokes own grant | **A** 200 (R7.5) |
| S31 | Unauthorized caller probes a consent-bearing object | **D** 404 before consent is evaluated (R7.4) |

### DTO and scope

| # | Scenario | Expected |
|---|---|---|
| S32 | `GET /public/properties` response key set | **A** — allow-list exact; no management/claim/consent/seller fields (K03) |
| S33 | Opportunity at `SUMMARY_ONLY` | **A** — no full property detail (R8.2) |
| S34 | Opportunity at `CONTACT_AFTER_CONFIRMATION`, no confirmation recorded | **D** — contact withheld (R8.3) |
| S35 | Offer with `price_visibility = PRIVATE` inside a permissive scope | **A** — price still redacted (R9.4) |
| S36 | Customer explanation for a match influenced by seller expectation | **A** — explanation present, expectation not stated or inferable (R9.3, D02) |
| S37 | A new column is added to `properties` | **D** — DTO allow-list test fails (R9.5) |

### Pipeline

| # | Scenario | Expected |
|---|---|---|
| S38 | A route with no policy entry | **D** 403; startup assertion also fails (R10.1–R10.2) |
| S39 | Operation whose policy roles ≠ OpenAPI `x-roles` | **D** — startup assertion fails (R10.2) |
| S40 | An unauthenticated operation outside the closed list of six | **D** — test fails (R10.4) |
| S41 | Webhook with an invalid provider signature | **D** — rejected before domain resolution (R10.5) |
| S42 | Webhook replayed with the same `provider_event_id` | **A** 200, no duplicate message (ADR-09) |

---

## 12. Error semantics

| Condition | Status | `code` |
|---|---|---|
| No/invalid token | 401 | `UNAUTHENTICATED` |
| Role mismatch | 403 | `ROLE_NOT_PERMITTED` |
| Object check failed, `/me/*` | 404 | `NOT_FOUND` |
| Object check failed, internal | 403 | `OBJECT_NOT_AUTHORIZED` |
| Consent missing/revoked | 409 | `CONSENT_REVOKED` |
| Stale `If-Match-Version` | 409 | `STALE_VERSION` |
| Undeclared PATCH field | 422 | `UNKNOWN_FIELD` |

All use `application/problem+json` with the frozen `Problem` schema
(`title`, `status`, `code`, `trace_id` required). Per `API_CONTRACTS` §2.5, `detail`
MUST NOT carry database exception text, and per §8 it MUST NOT carry OTP codes or
document payloads.

---

## 13. Open questions requiring a decision

Implementation of the affected rule does not begin until each is ruled on.

| # | Question | Proposal | Blocks |
|---|---|---|---|
| **Q1** | Which `relation_code` values confer **write** authority on a PROPERTY/OFFER? The schema treats all seven alike. | `OWNER_DECLARED`, `BROKER`, `AGENCY`, `DEVELOPER` → read+write; `OCCUPANT`, `CONTACT_PERSON`, `OTHER` → read only | R4.2, S12 |
| **Q2** | `404` or `403` for a failed object check on `/me/*`? Both are declared; `x-authorization` says "404/403". | `404` on `/me/*`; `403` internally | R5.3, S02 |
| **Q3** | May one account hold `OPERATOR` **and** `REVIEWER`, or staff **and** `CUSTOMER`? The PK permits it. | Service rejects `OPERATOR`+`REVIEWER` on one account; staff+`CUSTOMER` allowed but evaluated per operation | R3.3, R6.4 |
| **Q4** | Are staff **reads** of customer-scoped objects recorded? `audit_row_change()` covers writes only. | Structured access-log entry, not an `audit_log` row | R6.3 |
| **Q5** | Exact field sets per `sharing_scope`. No artifact enumerates them. | The table in R8.2 | R8.2, S33–S34 |
| **Q6** | Is "no unscoped `findById` from a request path" enforced by architecture test or by convention? | Architecture test | R10.3 |
| **Q8** | `GET /reason-codes` (`getReasonCodes`) declares `security: BearerAuth` but **no `x-roles`** — the only operation in the contract in that state. Under deny-by-default it is unreachable by every role. Its two sibling master-data reads, `GET /locations` and `GET /master/criterion-definitions`, are unauthenticated. | Treat reason codes as master data and allow all four authenticated roles to read it. Do **not** silently make it unauthenticated: that widens the closed list in R10.4. | R10.1, S38 |
| **Q7** | **"Explicit delegated authority" has no representation in the frozen schema.** `API_CONTRACTS` §2.2 and the `x-authorization` on `GET /me/requests/{id}` both invoke it; no table, column or endpoint models it. | Treat as **out of scope for Slice 0**: implement ownership only, and let any future delegation arrive as an approved domain change. Do **not** improvise a mechanism. | R4, S01–S02 |

**Q7 is the significant one.** It is a genuine gap between the API contract and the
database baseline, of the kind `FILE_AUTHORITY_AND_VERSION_POLICY.md` says must not be
resolved silently in code. Inventing a delegation table would change the domain model
without approval; ignoring the phrase entirely would contradict the contract. The
proposal — implement strict ownership now, raise delegation as its own decision when a
real case appears — keeps both documents honest and leaves no half-built mechanism.

---

## 14. Test plan

Authorization tests are written **with** the implementation, not after (kickoff
checklist: object-level authorization tests included from Slice 0).

1. **Contract conformance** — the R10.2 startup assertion, run as a test: policy table
   ≡ OpenAPI `x-roles`, over all 57 annotated operations.
2. **BOLA/IDOR matrix** — S01–S16 for every customer-reachable resource
   (`API_CONTRACTS` §8: "BOLA/IDOR tests for every customer resource endpoint").
3. **Separation of duties** — S17–S23.
4. **Consent vs authorization** — S24–S31, including the ordering guarantee R7.4.
5. **DTO allow-lists** — S32–S37, asserting exact key sets so new columns fail closed.
6. **Pipeline** — S38–S42.
7. **Regression** — K01–K05 and D02 from `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` run in CI
   alongside the PostgreSQL Execution Gate.

---

## 15. Explicitly out of scope

Row-level security in PostgreSQL as the enforcement mechanism (the schema sets
`app.account_id` for *audit*, not RLS, and no policies exist); delegated authority
(Q7); field-level encryption; rate limiting; multi-tenancy; any change to the frozen
`schema_v0.2.1.sql` or `openapi_v0.2.yaml`.

This RFC proposes **no change** to the domain model, workflow, permissions model or
matching logic as frozen. It specifies how the already-approved rules are enforced.
