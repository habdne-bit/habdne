# RFC-001 — Object-Level Authorization

**Status:** REVISED — all open questions now closed. **Awaiting final approval; if no
new contradiction appears this is FINAL and authorization implementation may begin.**
**Revision:** 3 (supersedes revisions 1 and 2)
**Slice:** 0 — Application Skeleton / Security Boundaries
**Date:** 2026-09-18
**Baseline:** Handoff v1.0.1, technical baseline frozen at commit `f833fe7d05e160b048a6de1c4120f2c79015c3bb`

## Decisions incorporated in this revision

Eight decisions were returned on revision 1. All are binding and are folded into the
rules below; §13 records how each was resolved and what remains open.

| # | Decision | Effect here |
|---|---|---|
| 1 | `relation_code` values do **not** grant write authority; domain relationship and authorization stay separate | §4 rewritten — this changes the authority model, not just a parameter |
| 2 | `/me/*` uses **404** for inaccessible/unowned; **403** only for a known accessible resource where the action is prohibited | §5.3, §12 |
| 3 | Roles are literal and non-hierarchical; no implicit ADMIN/REVIEWER/OPERATOR inheritance | §2 confirmed |
| 4 | Customer delegated authority is **not** implemented in v0.1; access is ownership-only | §4, Q7 closed |
| 5 | `GET /reason-codes` → `ADMIN`, `OPERATOR`, `REVIEWER`; not `CUSTOMER` | §10, Q8 closed |
| 6 | Three sharing scopes with server-side field filtering; internal data never exposed merely because the scope is higher | §8, §9 |
| 7 | Deny by default | §10 confirmed |
| 8 | Maker–checker separation is intentional and must be preserved | §2.1, now enforced |

A technology decision was returned with them and is recorded in §14.

### Revision 3 — the last three questions closed

| # | Decision | Effect here |
|---|---|---|
| Q4 | Audit successful **staff** reads of sensitive/non-public individual resources, and authorization-denied attempts. Audit a bulk list **once**, not per row. Public/master-data reads need no per-resource read audit. Audit metadata must not duplicate sensitive payloads. | §6.3 |
| Q6 | Enforce authorization **structurally**, not by banning a function name. Routes must not import repositories or SQLAlchemy sessions; loading passes through application services and actor-scoped, policy-checked loaders. Architecture tests prevent route→repository bypass; integration tests prove cross-account UUID access returns 404. | §10.3, §14.3, §15 |
| Q9 | `CUSTOMER` authority over a `PROPERTY_OFFER` requires the offer's creator account **or** the conjunction of a valid parent-property claim, party match and `CLAIMED` parent. `offer.party_id` alone and `party_property_relations` alone never grant it. | §4.6 |

Nothing else changed in revision 3.

## Sources

This RFC derives from the frozen artifacts and adds no new product semantics. As of
revision 3 **no question remains open**: §13 records every ruling, and the three items
deferred by Design Ledger are marked as deferred rather than left ambiguous.

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
which `OPERATOR` does not.

**Decision 8 makes preserving this split binding**, so it is enforced rather than
documented:

- **R2.1** A single account MUST NOT hold both `OPERATOR` and `REVIEWER`. The service
  rejects the grant at role-assignment time; a test asserts no account in the database
  holds both. `user_account_roles` has primary key `(account_id, role)` — verified —
  so the database permits the combination and the service is the only thing preventing
  it.
- **R2.2** `ADMIN` is exempt from R2.1 by construction, since the contract lists it on
  both sides of the split. That exemption is the reason `ADMIN` grants must be rare and
  auditable; it is not a licence to route ordinary work through `ADMIN`.
- **R2.3** Decision 3 forbids implicit inheritance. The check is literal set
  intersection against the operation's `x-roles`. No code computes a role ordering.

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
- **R3.3** When one account holds both a staff role and `CUSTOMER`, authorization is
  evaluated **per operation** against that operation's literal `x-roles` (decision 3).
  A staff role never widens `/me/*`; `CUSTOMER` never widens an internal endpoint.
  `OPERATOR` + `REVIEWER` on one account is prohibited outright by R2.1.

---

## 4. Resource ownership and relationships

**Decision 1 separates two things that revision 1 conflated.** A domain relationship
records *how a party relates to a thing in the market*. Authorization records *whether
a caller may act on a row*. `party_property_relations` is the former and is **not**
an authorization source. Decision 4 further restricts customer access to **ownership
only** in v0.1.

This is the corrected authority graph.

| Resource | Customer authority derives from | Column / table |
|---|---|---|
| `PARTY` | identity | `parties.party_id = subject.party_id` |
| `REQUEST` | ownership **and** claimed state | `requests.party_id = subject.party_id AND requests.claim_status = 'CLAIMED'` |
| `PROPERTY` | creation **or** a recorded claim | `properties.created_by_account_id = subject.account_id` **OR** a `record_claim_events` row for `(property_id, subject.account_id)` |
| `PROPERTY_OFFER` | creation, **or** parent-property claim **and** party match **and** parent `CLAIMED` | see §4.6 — `offer.party_id` alone never suffices |
| `OPPORTUNITY` | transitive via request | `opportunities.request_id → requests.party_id = subject.party_id` |
| `INTEREST` | ownership | `interests.party_id = subject.party_id` |
| `CONSENT_GRANT` | ownership | `consent_grants.party_id = subject.party_id` |
| `COMMUNICATION_THREAD` | ownership | `communication_threads.party_id = subject.party_id` |

### 4.1 Why PROPERTY needs two sources

`properties` carries **no `party_id`** — verified. With `relation_code` removed as an
authority source by decision 1, exactly two facts in the frozen schema tie a property
to a customer account:

1. **`properties.created_by_account_id`** — the self-service path. A customer creating
   their own property via `POST /properties` (`SELF_MANAGED + CLAIMED`) is its creator.
2. **`record_claim_events`** — the assisted path. The table records
   `claimed_by_account_id` with exactly one of `request_id` / `property_id`
   (`CHECK (num_nonnulls(request_id, property_id) = 1)`), and `POST /records/claim`
   moves the record `ASSISTED/UNCLAIMED → SHARED_MANAGEMENT/CLAIMED`.

- **R4.1** Property authority is the disjunction of those two facts and nothing else.
- **R4.2** Both are **account**-scoped, not party-scoped, because both columns
  reference `user_accounts`. A second account belonging to the same party does **not**
  inherit property authority. This is stricter than party-scoping and consistent with
  decision 4; if it proves too strict operationally it is a product decision, not an
  implementation liberty.
- **R4.3** `created_by_account_id` is `ON DELETE SET NULL` — verified. Deleting an
  account silently detaches authorship. Combined with R3.1, the predicate must guard
  `NULL` explicitly: a `NULL` creator matches nobody.
- **R4.4** For an **assisted** record `created_by_account_id` is the *operator's*
  account. It therefore grants that operator nothing as a customer — operators are
  authorized by role — and grants the subject party nothing until a claim event exists.

### 4.2 What `party_property_relations` is for

It remains a first-class domain fact and keeps three uses, none of which is
authorization:

1. **Eligibility to claim.** `x-authorization` on `POST /records/claim` requires
   "verified contact point and resource party relationship". The relation is a
   *precondition* the claim command checks; the claim event is the authority it
   produces. Decision 1 is exactly this ordering.
2. **Consent binding validity.** `enforce_consent_binding()` requires an active
   relation before a property-scoped consent may bind — verified in the schema.
3. **Matching and permission evidence**, recorded in snapshots.

- **R4.5** No read or write authorization predicate may reference
  `party_property_relations`. An architecture test asserts the policy layer does not
  query that table.
- **R4.6** Relation currency
  (`valid_from <= now() < valid_to`) still governs uses 1 and 2. It no longer governs
  access, so an expired relation cannot silently revoke a claimed owner's access to
  their own property — which is the correct behaviour and a direct benefit of
  decision 1.
- **R4.7** `verification_level` on a relation is not an authorization input, for the
  same reason as before: verification governs trust in market truth, not access.

### 4.3 REQUEST and the claim gate

`requests.party_id` is `NOT NULL`, so an **assisted** request already carries the
subject's party before any claim. Party match alone would therefore hand a customer
access to a record staff are still operating.

- **R4.8** Request authority requires `claim_status = 'CLAIMED'` in addition to the
  party match. An `ASSISTED + UNCLAIMED` request has no authorized customer (the
  schema invariant makes `ASSISTED` and `UNCLAIMED` equivalent, so either test works;
  both are written for clarity).

### 4.4 Canonical identity

- **R4.9** Authority resolves through `property_identity_aliases` to the canonical
  property first. A customer authorized on an alias is authorized on the canonical
  record: identity resolution is non-destructive (ADR-03) and must not strip a real
  owner of access.

### 4.5 Management mode and claim state

- **R4.10** `ASSISTED + UNCLAIMED` ⇒ no authorized customer, on every resource type.
- **R4.11** `SHARED_MANAGEMENT` means staff and customer authority coexist. It does
  not reduce staff authority.

### 4.5a Design Ledger — per-account claim revocation is deferred

**Entry:** *Defer.* Per-account revocation of a record claim is **not implemented in
v0.1**.

A `record_claim_events` row grants **continuing** authority. The schema offers no way to
withdraw one: the table is append-only in practice, carries no revoked/valid-to column,
and `POST /records/claim` has no inverse in the frozen contract — verified.

Consequences to hold in mind while building:

- **R4.11a** The only thing that currently ends claim-derived authority is the
  **account** ceasing to be usable. Subject resolution therefore admits only accounts
  whose `status = 'ACTIVATED'`; `INVITED`, `SUSPENDED` and `DISABLED` accounts resolve
  to no authority at all. This is the mechanism the deferral relies on, so it is a rule,
  not a convenience.
- **R4.11b** Disabling an account is consequently the **only** operational lever if a
  claim turns out to be wrong. That is coarse, and it is accepted for v0.1 rather than
  worked around: inventing a revocation column or a compensating "unclaim" event would
  be a domain change without approval.
- **R4.11c** A future explicit lifecycle mechanism — claim revocation, expiry, or
  transfer — is a domain change requiring its own decision, schema change and gate
  re-run. Nothing in Slice 0 should be built in a way that assumes claims are forever;
  the authority predicate stays a function of rows, so adding a validity term later is
  a predicate change, not a rewrite.

### 4.6 PROPERTY_OFFER authority (Q9 closed)

Offers have no claim state of their own, so the gate is borrowed from the parent
property **and** narrowed by a party match. Customer authority over an offer exists
when **either**:

1. `property_offers.created_by_account_id = subject.account_id` — the actor created
   the offer; **or**
2. all three of:
   - a valid `record_claim_events` row exists for the **parent property** and
     `subject.account_id`;
   - `property_offers.party_id = subject.party_id`;
   - the parent property is `CLAIMED`.

- **R4.12** `offer.party_id` **alone never grants authority**, and
  `party_property_relations` never does, at all. Condition 2 uses the party match only
  as a *narrowing* term on top of a claim, never as an authority source of its own.
- **R4.13 Claiming a property does not open other parties' offers on it.** This is the
  point of the party match in condition 2. On one physical property an owner and a
  broker may each hold an offer (D01); the owner's claim reaches the owner's offer and
  stops there. Nothing in the frozen schema would have prevented the wider reading, so
  this rule is the only thing standing between a property claim and a competitor's
  commercial terms.
- **R4.14** No offer-specific claim model is introduced in v0.1. If offers ever need
  independent claiming, that is a domain change with its own approval.
- **R4.15** `property_offers.created_by_account_id` is `ON DELETE SET NULL` — verified,
  like every other creator column. Condition 1 must therefore guard `NULL` explicitly
  (R3.1, R4.3).

## 5. `/me/*` semantics

Four operations exist, all `CUSTOMER`-only: `GET /me/party`,
`/me/requests/{id}`, `/me/properties/{id}`, `/me/opportunities/{id}`.

- **R5.1** `/me/*` accepts **no arbitrary party id**. The subject is the only
  identity input (`x-authorization` on `GET /me/party`).
- **R5.2** A path id under `/me/*` is a *filter*, never a selector. The query is
  written as "this object **and** it belongs to me" in one statement. It is never
  "fetch, then compare in application code" — a fetch-then-compare has already read
  the row and invites a later refactor that returns it.
- **R5.3 Concealment vs prohibition (decision 2).** The two codes answer different
  questions and must not be used interchangeably:

  | Situation | Code |
  |---|---|
  | The object does not exist | `404` |
  | The object exists but the caller has no authority over it | `404` — indistinguishable from the above, by design |
  | The caller **is** authorized on the object, but the requested **action** is not permitted to them | `403` |

  A `403` is therefore an admission that the object exists *and* that the caller may
  see it. It is only ever returned once authority has already been established, so it
  discloses nothing the caller did not already know. Any `403` from `/me/*` that could
  be triggered by an unauthorized caller would turn the endpoint into an existence
  oracle for UUIDs, which is what K01/K02 forbid.
- **R5.3a** Concretely: `GET /me/requests/{someone-elses-id}` → `404`.
  `POST /requests/{own-id}/state` attempting a transition reserved to staff → `403`,
  because the caller owns the request and is merely barred from that action.
- **R5.3b** The same rule applies on internal endpoints. Staff object checks that fail
  return `403` with `OBJECT_NOT_AUTHORIZED` — a staff caller is already trusted to know
  that objects exist, so concealment buys nothing and a precise error is more useful.

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
- **R6.3 Read auditing (Q4 closed).** `audit_row_change()` fires on INSERT/UPDATE/DELETE
  only — verified — so reads are invisible to it. Read auditing is therefore a separate,
  application-emitted access record, governed by four rules:

  | Event | Audited? |
  |---|---|
  | Successful **staff** read of a sensitive / non-public **individual** resource | **Yes** |
  | **Authorization-denied attempt**, by any actor | **Yes** |
  | Staff read of a **bulk list** (queues, search) | **Once, for the list access** — never one event per row |
  | Public or master-data read (`/locations`, `/public/properties`, `/master/*`) | **No** per-resource read audit |

- **R6.3a** A denied attempt is audited for **every** actor class, not staff alone: a
  customer probing UUIDs is precisely the signal worth keeping (K01/K02).
- **R6.3b Audit metadata must not duplicate sensitive payloads.** An access record
  carries *references*, not content: actor account, role used, operation, resource type
  and id, decision, reason code, trace id, timestamp. It MUST NOT carry the rendered
  DTO, `seller_expectation_dzd`, private claims, staff notes, source-private data, OTP
  codes or document payloads. The audit trail is not a second copy of the data it
  protects — that would relocate the leak rather than prevent it, and `API_CONTRACTS` §8
  already forbids it for logs.
- **R6.3c** A list access records the query shape and result count, not the identifiers
  returned. Per-row auditing of a queue would generate volume proportional to browsing
  and bury the individual reads that matter.
- **R6.3d** These records are **not** `audit_log` rows: that table's shape is
  row-change specific (`old_row`, `new_row`, `action`). Read access is emitted as
  structured application audit. **[OPEN — implementation detail, not blocking]** whether
  it lands in a dedicated table or the structured log stream; both satisfy the rules
  above, and the choice can be made when the logging stack is set up.

- **R6.4** An account MUST NOT hold both `OPERATOR` and `REVIEWER`, or maker–checker
  (§2.1) collapses into one person. Decision 8 makes this binding and R2.1 enforces it
  at role-grant time, with a database test as the backstop.

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
- **R8.2 Field sets (decision 6).** Three scopes, filtered **server-side**:

  | Scope | `CustomerOpportunityView` renders |
  |---|---|
  | `SUMMARY_ONLY` | `opportunity_id`, `status`, `validity_status`, `sharing_scope`, `why_real`, `known_differences`, `created_at`, `shared_at`; `property` reduced to type, location and area bands |
  | `PROPERTY_DETAILS_ALLOWED` | the above plus the full `CustomerPropertyView` and public offer terms, subject to `price_visibility` |
  | `CONTACT_AFTER_CONFIRMATION` | the above plus counterparty contact, released **only** after a recorded confirmation event |

- **R8.2a Scope raises the ceiling, it never opens the floor (decision 6).** The
  following are **never** rendered at *any* scope, including the highest:

  - internal pricing expectations (`seller_expectation_dzd` and anything derived from it);
  - private claims and claim internals;
  - internal/staff notes;
  - source-private data (`sources.raw_text`, `external_url`, `external_ref`, `metadata`
    and observation payloads);
  - AI internals (`ai_trace_ref`, model versions, extraction confidences, raw scores).

  These belong to the never-serialized set of §9.2 and are outside the scope ladder
  entirely. A reviewer reading a future diff should be able to check this by asking one
  question: *does a higher scope add this field?* For anything in this list the answer
  is always no.

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
- **R10.3 Structural enforcement (Q6 closed).** Banning a function name is not
  enforcement; a rule that only forbids a spelling is bypassed by the next refactor.
  Authorization is enforced by **layering**:

  1. **API routes must not import repositories or SQLAlchemy sessions.** A route that
     cannot reach a session cannot issue an unscoped query, whatever it is called.
  2. **All resource loading passes through application services**, which obtain rows
     from **actor-scoped, policy-checked loaders**. A loader takes the subject and
     returns only what the §4 predicate admits; there is no variant that takes an id
     alone.
  3. The scoped query remains a single statement — "this object **and** it is mine" —
     never fetch-then-compare (R5.2).

- **R10.3b** Two test families hold the line, one structural and one behavioural:
  - **Architecture tests** asserting no module under the routes package imports a
    repository, a session factory, or `sqlalchemy` directly, and that the policy layer
    never imports `party_property_relations` (R4.5).
  - **Integration tests** proving cross-account access by raw UUID returns **404** on
    every customer-reachable resource — the behavioural proof that the layering
    actually holds end to end, since an architecture test alone cannot show that the
    predicate is correct.

- **R10.3a `GET /reason-codes` (decision 5).** It is the only authenticated operation
  in the frozen contract carrying no `x-roles`. Its policy entry is
  `{ADMIN, OPERATOR, REVIEWER}` — **not** `CUSTOMER`. It stays authenticated: it is not
  added to the closed unauthenticated list of R10.4. Because this policy entry has no
  counterpart in the contract, R10.2's cross-check treats it as an explicit, named
  exception rather than a drift, and the test asserts that it is the **only** such
  exception.

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
| S06 | Customer A `PATCH /requests/{B}` | **D** 404 before any field validation (R5.3) |
| S06a | Customer A attempts a staff-only transition on **own** request | **D** 403 — owns it, action prohibited (R5.3a) |
| S07 | Customer A sends `status` or `claim_status` in a typed PATCH | **D** 422 (K04) |
| S08 | Customer A `POST /interests` with `party_id` = B | **D** 403 (R4, interests) |
| S09 | Customer A responds to an opportunity whose request is B's | **D** 404 |

### Property relationships

| # | Scenario | Expected |
|---|---|---|
| S10 | Customer reads a property they created (`created_by_account_id` match) | **A** 200 (R4.1) |
| S11 | Customer reads a property whose `created_by_account_id` is `NULL` | **D** 404 — a null creator matches nobody (R4.3) |
| S12 | Customer with **any** `relation_code`, including `OWNER_DECLARED`, but no claim event and not the creator | **D** 404 — relationship is not authority (decision 1, R4.5) |
| S13 | Customer authorized on an alias property reads the canonical | **A** 200 (R4.9) |
| S14 | Any customer reads an `ASSISTED + UNCLAIMED` property | **D** 404 (R4.10) |
| S15 | Same record after a successful `POST /records/claim` | **A** 200, now `SHARED_MANAGEMENT`, authority from the claim event (R4.1) |
| S16 | Customer relation is `DECLARED` rather than verified, and a claim event exists | **A** 200 — verification is not an access input (R4.7) |
| S16a | Claimed owner whose `party_property_relations` row has **expired** | **A** 200 — expiry cannot revoke a claimed owner (R4.6) |
| S16b | Second account of the **same party** reads a property claimed by the first | **D** 404 — property authority is account-scoped (R4.2) |
| S16c | Customer reads an `ASSISTED + UNCLAIMED` request whose `party_id` is theirs | **D** 404 — party match alone is insufficient (R4.8) |
| S16d | Owner who claimed a property reads **their own** offer on it | **A** 200 — §4.6 condition 2 |
| S16e | Same owner reads the **broker's** offer on that same property | **D** 404 — a claim never opens another party's offer (R4.13) |
| S16f | Broker reads the offer they created, with no claim on the parent property | **A** 200 — §4.6 condition 1 |
| S16g | Customer whose `party_id` matches an offer, with no parent claim and not the creator | **D** 404 — `offer.party_id` alone never grants (R4.12) |
| S16h | Customer holding only a `party_property_relations` row reads an offer | **D** 404 — relations never grant (R4.12) |
| S16i | Authorized owner whose account is later `DISABLED` | **D** 401 at authentication — claim authority ends with the account (R4.11a; corrected, G3-15) |
| S16j | Account in `INVITED` or `SUSPENDED` status | **D** 401 at authentication (R4.11a; corrected, G3-15) |

**Correction G3-15** (decided in the review of Slice 3, commit d0d58c3; not a
new revision). S16i and S16j said **404**. That contradicted this RFC's own
pipeline (§10, stage 1: 401 when the bearer token is absent or invalid).
Since Slice 1, `resolve_subject` admits only `ACTIVATED` accounts (R4.11a),
so such an account is refused at authentication, before any resource is
looked up. The 401 is identical for a claimed property and a missing one,
so it reveals nothing about existence. Proven by
`test_s16i_an_owner_whose_account_is_later_disabled_is_denied` and
`test_s16j_an_invited_or_suspended_account_is_denied`.

### Staff and separation of duties

| # | Scenario | Expected |
|---|---|---|
| S17 | `OPERATOR` reads an arbitrary request internally | **A** 200, audit context recorded |
| S18 | `OPERATOR` calls `POST /matches/{id}/review` | **D** 403 (§2.1) |
| S19 | `REVIEWER` calls `POST /observations` | **D** 403 (§2.1) |
| S20 | `REVIEWER` calls `POST /opportunities/{id}/share` | **D** 403 (§2.1) |
| S21 | `OPERATOR` calls `GET /audit` | **D** 403 (§2.1) |
| S21a | Granting `REVIEWER` to an account already holding `OPERATOR` | **D** rejected at grant time; DB-level test finds no such account (R2.1) |
| S21b | `CUSTOMER` calls `GET /reason-codes` | **D** 403 (decision 5, R10.3a) |
| S21c | `OPERATOR` calls `GET /reason-codes` | **A** 200 (decision 5) |
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
| S36a | Opportunity at `CONTACT_AFTER_CONFIRMATION`, confirmation recorded — response inspected for internal pricing, private claims, staff notes, source-private data, AI internals | **A** contact released; **D** none of the five appear at any scope (R8.2a) |
| S37 | A new column is added to `properties` | **D** — DTO allow-list test fails (R9.5) |

### Pipeline

| # | Scenario | Expected |
|---|---|---|
| S38 | A route with no policy entry | **D** 403; startup assertion also fails (R10.1–R10.2) |
| S39 | Operation whose policy roles ≠ OpenAPI `x-roles` | **D** — startup assertion fails (R10.2) |
| S40 | An unauthenticated operation outside the closed list of six | **D** — test fails (R10.4) |
| S41 | Webhook with an invalid provider signature | **D** — rejected before domain resolution (R10.5) |
| S42 | Webhook replayed with the same `provider_event_id` | **A** 200, no duplicate message (ADR-09) |

### Audit and structural enforcement

| # | Scenario | Expected |
|---|---|---|
| S43 | `OPERATOR` reads one customer request internally | **A** 200, one access record emitted (R6.3) |
| S44 | Any actor is denied on an object check | **A** denial recorded, for staff and customers alike (R6.3a) |
| S45 | `OPERATOR` opens a back-office queue returning 50 rows | **A** exactly **one** access record, not 50 (R6.3c) |
| S46 | Anonymous `GET /public/properties` | **A** no per-resource read audit (R6.3) |
| S47 | An access record is inspected for content | **D** no rendered DTO, seller expectation, private claim, staff note, source-private data, OTP or document payload (R6.3b) |
| S48 | A route module imports a repository, a session factory or `sqlalchemy` | **D** architecture test fails (R10.3b) |
| S49 | The policy layer imports `party_property_relations` | **D** architecture test fails (R4.5) |
| S50 | Cross-account raw-UUID access, every customer-reachable resource | **D** 404 in integration, end to end (R10.3b) |

---

## 12. Error semantics

| Condition | Status | `code` |
|---|---|---|
| No/invalid token | 401 | `UNAUTHENTICATED` |
| Role mismatch | 403 | `ROLE_NOT_PERMITTED` |
| Object check failed, `/me/*` (unowned or absent) | 404 | `NOT_FOUND` |
| Authorized on the object, action prohibited | 403 | `ACTION_NOT_PERMITTED` |
| Object check failed, internal endpoint | 403 | `OBJECT_NOT_AUTHORIZED` |
| Consent missing/revoked | 409 | `CONSENT_REVOKED` |
| Stale `If-Match-Version` | 409 | `STALE_VERSION` |
| Undeclared PATCH field | 422 | `UNKNOWN_FIELD` |

All use `application/problem+json` with the frozen `Problem` schema
(`title`, `status`, `code`, `trace_id` required). Per `API_CONTRACTS` §2.5, `detail`
MUST NOT carry database exception text, and per §8 it MUST NOT carry OTP codes or
document payloads.

---

## 13. Decision register

### Resolved

| # | Question | Ruling |
|---|---|---|
| Q1 | Which `relation_code` values confer write authority? | **None.** Domain relationship and authorization are separate concerns. Revision 1 proposed a write-conferring subset; that proposal is withdrawn and §4 rewritten. |
| Q2 | `404` or `403` on a failed object check? | **404** for inaccessible or unowned; **403** only where the caller is authorized on the object but the action is prohibited (R5.3). |
| Q3 | May one account hold several roles? | Roles are **literal and non-hierarchical**, no implicit inheritance (decision 3). `OPERATOR` + `REVIEWER` on one account is prohibited, enforced at grant time (R2.1, decision 8). Staff + `CUSTOMER` is allowed and evaluated per operation (R3.3). |
| Q5 | Field sets per `sharing_scope` | The three scopes of R8.2, server-side filtered, with the never-exposed floor of R8.2a. |
| Q7 | Delegated authority | **Not implemented in v0.1.** Customer access is ownership-only. No delegation model is invented (decision 4). The gap between `API_CONTRACTS` §2.2 and the schema stands recorded and unresolved-by-design. |
| Q8 | `GET /reason-codes` with no `x-roles` | `ADMIN`, `OPERATOR`, `REVIEWER`; **not** `CUSTOMER`. Remains authenticated (R10.3a). |

### Resolved in revision 3

| # | Question | Ruling |
|---|---|---|
| Q4 | Are staff reads audited? | Yes for successful staff reads of sensitive/non-public **individual** resources, and for authorization-denied attempts by any actor. Bulk lists are audited **once** as a list access. Public/master-data reads need no per-resource read audit. Metadata carries references, never sensitive payloads (R6.3–R6.3d). |
| Q6 | How is unscoped loading prevented? | **Structurally.** Routes import no repositories or SQLAlchemy sessions; loading goes through application services and actor-scoped, policy-checked loaders. Architecture tests prevent route→repository bypass; integration tests prove cross-account UUID access returns 404 (R10.3, R10.3b). |
| Q9 | Customer authority over a `PROPERTY_OFFER` | Offer creator account, **or** parent-property claim **and** party match **and** parent `CLAIMED`. `offer.party_id` alone and `party_property_relations` alone never grant it. A property claim never opens another party's offer. No offer-specific claim model in v0.1 (§4.6). |

**No open questions remain.** One implementation detail is explicitly non-blocking:
whether read-access records land in a dedicated table or the structured log stream
(R6.3d); both satisfy the approved rules.

### Deferred by Design Ledger

| Item | Status |
|---|---|
| Per-account claim revocation | **Defer** to a future version; see §4.5a. Authority continues until the account is no longer `ACTIVATED`. |
| Customer delegated authority | **Defer**; ownership only in v0.1 (decision 4). |
| Offer-specific claim model | **Defer**; not introduced in v0.1 (R4.14). |

## 14. Technology decision

Returned with the authorization decisions and recorded here so the RFC is the single
reference for Slice 0.

| Concern | Decision |
|---|---|
| Shape | **Modular monolith** — no microservices |
| Language | Python 3.12+ |
| HTTP | FastAPI |
| Validation / DTOs | Pydantic v2 |
| Persistence | SQLAlchemy 2.x |
| Migrations | Alembic |
| Database | PostgreSQL 16+ |
| Tests | pytest |

**Not introduced without a demonstrated need:** microservices, Redis, Celery, external
policy engines, or any additional infrastructure. A policy layer written in ordinary
Python against the tables in §4 is the default; an external engine would have to earn
its place.

### 14.1 The contract stays frozen and stays first

FastAPI generates an OpenAPI document from the code. That generated document is **not**
the contract.

- **R14.1** `openapi_v0.2.yaml` remains the contract. The generated document is
  **checked against it** and never replaces, overwrites or regenerates it.
- **R14.2** A conformance test compares the generated document to the frozen one over
  paths, methods, `operationId` values, required request fields and response codes.
  A divergence fails the build; the resolution is to change the code, or to raise a
  contract change through the handoff process — never to re-export the contract from
  the code.
- **R14.3** This test is the natural home for R10.2's policy cross-check, since both
  compare running code against the frozen contract.

### 14.2 Alembic must not redefine the frozen baseline

Alembic autogeneration compares models to a live database and emits a migration. Pointed
at the frozen schema it will happily produce a diff that quietly becomes the new truth.

- **R14.4** `schema_v0.2.1.sql` is the **initial** migration. Alembic's first revision
  stamps that state; it does not recreate it from models.
- **R14.5** SQLAlchemy models are written to **match** the frozen schema. Where a model
  and the schema disagree, the schema is right and the model is a defect.
- **R14.6** Autogenerated migrations are reviewed as proposed *changes to a frozen
  baseline*, not as routine output. A migration altering anything in `schema_v0.2.1.sql`
  requires the same approval path as a schema change, and CI still verifies the frozen
  digests (`TECHNICAL_BASELINE_FROZEN.md`).
- **R14.7** The 70-assertion gate suite keeps running against the frozen SQL, not
  against models. It is the independent check that the ORM has not drifted.

### 14.3 Where authorization lives

- **R14.8** The policy layer is a module with no HTTP and no ORM-session
  construction of its own: it receives a subject and a resource reference and returns a
  decision. That keeps §11's scenarios testable without a running server.
- **R14.9** Pydantic v2 models are the DTO boundary of §9. Public, customer and internal
  views are **separate model classes** (R9.1), never one model with conditional fields
  — a conditional field is exactly the delete-keys pattern R9.1 rejects, wearing a type.

## 15. Test plan

Authorization tests are written **with** the implementation, not after (kickoff
checklist: object-level authorization tests included from Slice 0).

1. **Contract conformance** — the R10.2 startup assertion, run as a test: policy table
   ≡ OpenAPI `x-roles`, over all 57 annotated operations.
2. **BOLA/IDOR matrix** — S01–S16 for every customer-reachable resource
   (`API_CONTRACTS` §8: "BOLA/IDOR tests for every customer resource endpoint").
3. **Separation of duties** — S17–S23.
4. **Consent vs authorization** — S24–S31, including the ordering guarantee R7.4.
5. **DTO allow-lists** — S32–S37, asserting exact key sets so new columns fail closed,
   plus S36a proving the R8.2a floor holds at the highest scope.
6. **Pipeline** — S38–S42.
7. **Authority-model invariants** — the rules decision 1 introduced, which are the most
   likely to be undone by a well-meaning refactor:
   - an architecture test asserting the policy layer never queries
     `party_property_relations` (R4.5);
   - a database test asserting no account holds both `OPERATOR` and `REVIEWER` (R2.1);
   - a null-safety test for `created_by_account_id IS NULL` and `party_id IS NULL`
     (R3.1, R4.3).
8. **Contract conformance of the running app** — R14.2, comparing FastAPI's generated
   document to the frozen `openapi_v0.2.yaml`.
9. **Read audit** — S43–S47: emission on staff individual reads and on denials, exactly
   one record per list access, silence on public/master data, and a content assertion
   that access records carry references only (R6.3b).
10. **Structural enforcement** — S48–S50: the two architecture tests, plus the
    cross-account 404 integration sweep over every customer-reachable resource, which is
    the behavioural proof the layering actually holds (R10.3b).
11. **Regression** — K01–K05 and D02 from `RED_TEAM_ACCEPTANCE_TESTS_v0.2.md` run in CI
   alongside the PostgreSQL Execution Gate.

---

## 16. Explicitly out of scope

Customer delegated authority (decision 4 — ownership only in v0.1); per-account claim
revocation and any claim expiry or transfer (§4.5a, Design Ledger: Defer); an
offer-specific claim model (R4.14);
row-level security in PostgreSQL as the enforcement mechanism (the schema sets
`app.account_id` for *audit*, not RLS, and no policies exist); field-level encryption; rate limiting; multi-tenancy; any change to the frozen
`schema_v0.2.1.sql` or `openapi_v0.2.yaml`.

This RFC proposes **no change** to the domain model, workflow, permissions model or
matching logic as frozen. It specifies how the already-approved rules are enforced.
