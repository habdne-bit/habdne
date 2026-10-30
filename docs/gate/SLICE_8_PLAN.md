# Slice 8 — External Acquisition / Assisted Entry / Self-service
## Implementation plan — **revision 1**

**Status: submitted for review.**
- **No code for this slice exists, and none is written before this plan is
  approved.** `SLICE_7_CLOSURE.md` §6: "No code for a next slice before its
  plan is approved". The instruction after the R-1 plan's revision 13, "واصل
  الخطوة الموالية" ("continue the next step"), is read as **permission to
  prepare this plan only**. If it meant something else, this revision is
  only a document and changes nothing.
- **Approved by no one yet:** every decision of §5, the proposed parts of a
  migration `0009`, the Contract Delta of G8-4, and the measurements of
  §6.5.

**What this revision does not decide.** Every choice that is not already
fixed by a source is put to the reviewer as a decision (§5), with options and
a recommendation. A recommendation is not a decision.

**What it rests on:**
- **Each finding of §4** rests on reading the frozen sources, the earlier
  slices' decisions and the code at the commit that adds this revision.
- **Nothing was run against PostgreSQL** for this revision. The
  measurements that would confirm the findings are proposed in §6.5.
- **One external fact is NOT verified against its official source:**
  Algerian personal-data law as it applies to copying third parties' posts
  from Facebook or Ouedkniss into `sources.raw_text` (OQ8-1). It is named
  only as an open question, and must be verified against the official text
  before any rule rests on it.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | the commit that adds this revision | first plan (planning only) |

---

## 0. What this slice is, and what it is not

### 0.1 The scope, as the approved slices document states it

`docs/handoff/06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md`, "Slice 8 —
External Acquisition / Assisted Operations / Self-service":

- **Objective:** "Connect real Adrar market behavior to the structured core."
- **Deliverables:**
  1. External Lead queues;
  2. short Call Brief: known / missing / permission needed;
  3. contact attempt outcome;
  4. assisted REQUEST/PROPERTY entry after consent;
  5. self-service create and claim flows;
  6. public browsing and Direct Interest.
- **Mandatory tests:**
  1. external Facebook/Ouedkniss discovery cannot become active property
     without consent/workflow;
  2. Direct Interest remains INTEREST until explicit REQUEST conversion;
  3. assisted record claim reuses existing domain id;
  4. public browsing requires publication eligibility, not
     `supply_mode=PUBLIC` alone.

The workflow it implements is the Developer Reference Spec's §5.5:

```text
EXTERNAL_LEAD -> CONTACT ATTEMPT -> PARTY identified/created -> CONSENT captured
  -> ASSISTED DRAFT -> PENDING_INFO if critical fields missing
  -> ACTIVE PROPERTY/REQUEST -> optional CLAIM by user account later
```

with its rules: no contact and no consent, no active record; self-service by
an invitation; assisted entry within the consent's scope; a claim never
copies the record; **no fake accounts** ("الموظف لا ينشئ كلمة مرور أو حساب
دخول فعلي باسم العميل": staff never create a password or a login account in
the customer's name).

### 0.2 What it is not

- **Not a scraper or an importer.** Facebook and Ouedkniss are discovery
  channels, "not Inventory copied automatically" (spec §5.5). A lead is
  captured by staff through `postExternalLeads`, as today.
- **Not outbound messaging.** A contact attempt is a **record** of an
  attempt made outside TURAB. Nothing is sent from TURAB (as G7-14 in Slice
  7).
- **Not a reception of WhatsApp events.** R-1 is UNMET; this slice does not
  touch the webhook or the relay.
- **Not AI** (Slice 9).
- **Not a user-management system.** Account provisioning stays as
  `ACCOUNT_PROVISIONING_MINI_CONTRACT.md` (DL-07) leaves it, unless G8-9
  decides otherwise.

### 0.3 Carried, unchanged

1. **R-1 is UNMET** (`R1_CLOSURE_RECORD.md`). No real WhatsApp event may be
   received. A contact attempt by WhatsApp is recorded by staff, never
   received.
2. **K06 is UNPROVEN** (EN-02). Any refusal this slice adds at trigger or
   constraint level is never counted as K06.
3. **G4-5R is open.** The scope is SALE only.
4. **G3-10's decisions** (review of `0a66f8e`): conversion refused until a
   path records contact (Q-1 (b)); PROPERTY conversion refused until an
   explicit relation and binding path (Q-2 (b)); a conversion schema only by
   an approved contract change (Q-3 (b)); lineage both ways in one
   transaction (Q-4 (c)); the queue's choices Q-5 to Q-8 accepted for Slice
   3 only, with the **condition on Q-8**: "a contract that allows paging is
   required before the queue is used at operational volume".
5. **G3-2 is open:** PROPERTY claim eligibility. `POST /records/claim` with
   a PROPERTY fails closed (`test_property_claiming_fails_closed`).
6. **D7 / CORRECTION-001:** `POST /parties` is ADMIN and OPERATOR only.
7. **DL-07:** nothing in TURAB creates a `user_accounts` row, binds an
   account to a party, or sets its login contact point. Accounts exist only
   through fixtures.
8. **Slice 3's publication rule** (`services/public_listing.py`): three SQL
   conditions, and the precautionary rule R6-P1, accepted "for now" in the
   review of `3a53b0a`.

## 1. Operations

**In the frozen contract** (`openapi_v0.2.3.yaml`), and where they stand:

| operationId | Roles | State today |
|---|---|---|
| `postExternalLeads` | ADMIN, OPERATOR | **implemented** (Slice 3 step 3): capture only, "never inventory" |
| `postExternalLeadsLeadIdConvert` | ADMIN, OPERATOR | **refused by decision** G3-10: `409 EXTERNAL_LEAD_CONVERSION_NOT_AVAILABLE` |
| `getBackofficeQueuesExternalLeads` | ADMIN, OPERATOR, REVIEWER | **implemented**, Q-5 to Q-8 provisional; no paging |
| `postRecordsClaim` | CUSTOMER, ADMIN, OPERATOR | **REQUEST implemented** (CORRECTION-003); **PROPERTY fails closed** (G3-2) |
| `getPublicProperties` | unauthenticated | **implemented** (Slice 3 step 6) |
| `postInterests` | CUSTOMER, ADMIN, OPERATOR | **not implemented**: no route |
| `postRequests`, `postProperties` | ADMIN, OPERATOR, CUSTOMER | **implemented**: a CUSTOMER creates `SELF_MANAGED`/`CLAIMED` for their own party; staff create `ASSISTED`/`UNCLAIMED` |

**Not in the frozen contract** (F8-1, F8-3, F8-5, F8-6): recording a contact
attempt; moving a lead between its statuses; a Call Brief; converting an
INTEREST into a REQUEST; a conversion payload schema; paging the leads
queue; creating an account or binding it to a party.

## 2. What the schema and the earlier slices give, and what they leave open

**`external_leads`** (frozen):
- `lead_kind` PROPERTY or REQUEST; `source_id` required; `status`, ten
  values: `DISCOVERED`, `CONTACT_ATTEMPTED`, `CONTACTED`, `CONSENT_PENDING`,
  `CONSENTED`, `PENDING_INFO`, `CONVERTED`, `DECLINED`, `UNREACHABLE`,
  `CLOSED`;
- `party_id`, `last_contact_at`, `close_reason_code` (a reason code),
  `converted_request_id` / `converted_property_id`;
- two checks only: the converted target matches the kind, and `CONVERTED`
  requires the target. **No rule on which status may follow which.**

**`interests`:** `party_id`, `property_id`, `status` (`ACTIVE`,
`CONVERTED_TO_REQUEST`, `CLOSED`), `converted_request_id`; one `ACTIVE`
interest per (party, property) by a partial unique index.

**`record_claim_events`** and the management-mode/claim-state check:
`ASSISTED` ⇔ `UNCLAIMED`; `SELF_MANAGED`, `SHARED_MANAGEMENT` ⇔ `CLAIMED`.

**`consent_grants` / `resource_consent_bindings`:** the `ASSISTED_ENTRY`
scope exists. A PROPERTY binding needs a current relation of the consenting
party to the property (`0003`).

**`interactions`** (Slice 7's timeline): party, request, property,
opportunity or thread; **no column names an external lead.**

**`sources.kind`** includes `FACEBOOK_POST`, `OUEDKNISS_POST`,
`OTHER_WEB_POST`.

## 3. Rules that follow from the sources without a decision

### 3.1 A discovery is never inventory
A lead becomes an active PROPERTY or REQUEST only through contact, a party,
a consent, an assisted draft (spec §5.5; API_CONTRACTS §4.3: "Conversion is
allowed only after contact/consent/data gates"). Mandatory test 1.

### 3.2 INTEREST ≠ REQUEST
`postInterests` never creates a REQUEST ("it must never auto-create a
request": the contract's description; spec §10.1; red-team C02). Mandatory
test 2.

### 3.3 A claim reuses the record
"It MUST reuse the existing REQUEST/PROPERTY; creating a duplicate is
forbidden" (API_CONTRACTS §4.3; red-team C05). Mandatory test 3.

### 3.4 Publication eligibility, not `supply_mode` alone
The three conditions of `public_listing.py` (red-team D04). Mandatory test
4.

### 3.5 No fake accounts
Staff never create a login, a password or an account in a customer's name
(spec §5.5). Assisted records live with a PARTY and no account (red-team
A03).

### 3.6 Lineage, both ways, in one transaction
When conversion exists, the lead records the produced resource, and the
resource's provenance carries the lead's `source_id` (G3-10 Q-4 (c)).

### 3.7 A pre-consent lead carries no more than its discovery
Until a consent exists, a lead is a discovery record: its source, its raw
payload as captured, its status. The queue projects no floor field (G3-10
§3); this stays.

## 4. Findings from reading (not measured, not fixed)

| # | Finding | Where |
|---|---|---|
| F8-1 | No contract operation records a contact attempt or moves a lead's status. A lead can only be `DISCOVERED` through the API (as G3-10 §1 already found) | the frozen contract |
| F8-2 | No table records a contact attempt. `external_leads` keeps only `last_contact_at`; `interactions` cannot name a lead, and a lead before contact has no party | schema |
| F8-3 | The Call Brief has no operation, no schema and no table. "Known / missing / permission needed" is a projection to define | slices document; contract; schema |
| F8-4 | `postInterests` has no route. `InterestCreate` carries `party_id` and `property_id` and nothing else; the contract says nothing about which properties may receive an interest | contract; `api/routes/` |
| F8-5 | No contract operation converts an INTEREST into a REQUEST ("The API may later offer an explicit convert-to-request action") | contract |
| F8-6 | **Self-service rests on accounts nothing can create** (DL-07). A CUSTOMER can create a SELF_MANAGED record only when an account already bound to a party exists; only fixtures provide one. `POST /parties` is staff-only (D7) | DL-07; CORRECTION-001 |
| F8-7 | PROPERTY claims fail closed (G3-2): "claim flows" exist for REQUEST only | CORRECTION-003 §5 |
| F8-8 | The queue has no paging; G3-10 attached a condition before operational volume | G3-10 Q-8 |
| F8-9 | No rule says which lead status may follow which. Ten statuses; the schema checks only `CONVERTED` | schema |
| F8-10 | **An interest can disclose a property.** If `postInterests` answers differently for a private property and for a non-existent one (`201`/`409` against `404`), a customer can learn that a private or potential property exists | contract (`404`, `409` declared) |
| F8-11 | `postInterests` is tagged "Public" but requires a bearer token (`CUSTOMER`): Direct Interest also rests on accounts (F8-6) | contract |
| F8-12 | A PROPERTY conversion would create a property with no relation, so its consent cannot be bound (`0003`): G3-10 Q-2 stands | G3-10; `0003` |

## 5. Decisions needed — none is taken by this plan

### G8-1 · Scope of Slice 8
- **(a) recommended:** the acquisition workflow (contact attempts, lead
  statuses, Call Brief, REQUEST conversion), Direct Interest, and the four
  mandatory tests as evidence; **self-service account creation outside**
  (G8-9) and **PROPERTY conversion and claim outside** unless G8-5 (ii) and
  G8-10 decide them.
- (b) all six deliverables in full, which requires deciding G8-9 and G8-10
  first.
- *Why (a):* each excluded part waits on a decision of permissions or of
  ownership that the frozen sources do not make (F8-6, F8-7, F8-12).

### G8-2 · How a contact attempt is recorded (F8-2)
- **(a) recommended:** a new append-only table `external_lead_contact_attempts`
  in migration `0009`: the lead, the channel (`communication_channel`), an
  outcome code, `occurred_at`, the operator; no free text. Immutable by
  trigger, as `0005`/`0006` made match history and opportunity history.
- (b) `interactions` with a new nullable `external_lead_id` column
  (`0009`): one timeline, but the lead's attempts precede any party, and
  `interactions`' foreign keys are `ON DELETE SET NULL`.
- (c) `interactions.metadata` only, no migration: the lead is named in JSON,
  unchecked by the database. Not recommended.
- **The outcome codes** (G8-3) are proposed in revision 2 as reason codes,
  as `0002` added request-closure reasons.

### G8-3 · The lead's status machine (F8-9)
Proposed, for decision:

| From | To | By |
|---|---|---|
| `DISCOVERED`, `CONTACT_ATTEMPTED`, `UNREACHABLE` | `CONTACT_ATTEMPTED` | an attempt with no answer |
| same | `UNREACHABLE` | an attempt whose outcome says the number is wrong or unused |
| `DISCOVERED`, `CONTACT_ATTEMPTED`, `UNREACHABLE` | `CONTACTED` | an attempt that reached the person |
| `CONTACTED` | `CONSENT_PENDING` | staff, when consent was asked |
| `CONTACTED`, `CONSENT_PENDING` | `CONSENTED` | **only** when a `GRANTED`, unrevoked `ASSISTED_ENTRY` grant of the lead's party exists; the lead's `party_id` is set |
| `CONSENTED` | `PENDING_INFO` | staff, when critical fields are missing |
| `CONSENTED`, `PENDING_INFO` | `CONVERTED` | **only** the conversion (G8-5) |
| any open status | `DECLINED` | the person declined; a reason code required |
| any open status | `CLOSED` | staff; a reason code required |

- **Questions within it:**
  - (i) is `CONTACT_ATTEMPTED` / `CONTACTED` / `UNREACHABLE` **derived**
    from the attempt (recommended), or set by hand?
  - (ii) may `CLOSED` or `DECLINED` be reopened? Recommended: **no**; a new
    discovery is a new lead.
  - (iii) enforced in the service only, or also by a trigger in `0009`?
    Recommended: service, with a trigger for `CONVERTED` and the terminal
    statuses only.

### G8-4 · The Contract Delta (F8-1, F8-3, F8-8)
The frozen contract declares none of these. The precedent is G3-6: a Delta
document, approved, then a standalone addendum under `docs/contract/addenda/`
that the code binds by digest. The frozen file is never edited.

| Operation proposed | Roles proposed |
|---|---|
| `POST /external-leads/{lead_id}/contact-attempts` | ADMIN, OPERATOR |
| `POST /external-leads/{lead_id}/status` (decline, close, consent pending, pending info) | ADMIN, OPERATOR |
| `GET /external-leads/{lead_id}/call-brief` | ADMIN, OPERATOR, REVIEWER |
| paging on `getBackofficeQueuesExternalLeads` (a cursor parameter): a change to a frozen operation, so a CORRECTION cannot carry it (it may only narrow) | — |
| a conversion payload schema for REQUEST (G3-10 Q-3 (b)) | — |

- **Decision asked:** (a) prepare this Delta in revision 2, as text for
  approval, **recommended**; (b) a narrower Delta; (c) none, and the
  workflow stays outside the contract (not recommended: F8-1 blocks
  mandatory test 1's workflow).
- **The queue's paging** may also be (d) left as it is, with no cap, under
  G3-10's condition, if Slice 8 does not bring operational volume.

### G8-5 · Conversion (G3-10 carried)
- **(i) REQUEST conversion, recommended:**
  - allowed from `CONSENTED` or `PENDING_INFO` only;
  - requires the lead's party and its unrevoked `ASSISTED_ENTRY` grant,
    bound to the new request in the same transaction (a REQUEST binding
    checks `requests.party_id`, which succeeds);
  - produces `ASSISTED` / `UNCLAIMED`, status `RAW` (G8-5 question: or
    `CONTACTED`, since contact is proven);
  - lineage both ways (§3.6);
  - payload: the schema of G8-4.
- **(ii) PROPERTY conversion:** stays refused (G3-10 Q-2 (b)), unless an
  explicit path is decided: for instance, the conversion creates the
  property **and** records the party's relation through G3-6 in the same
  transaction, from a relation the operator states, never inferred. Not
  recommended in this slice.

### G8-6 · The Call Brief (F8-3)
A read-only projection for staff, computed, stored nowhere:
- **known:** the lead's kind, source kind, status, attempts (count, last
  outcome), its party if identified, that party's contact points' kinds and
  control status;
- **missing:** for a REQUEST lead, the fields a conversion requires (from
  G8-4's schema); for a PROPERTY lead, stated but not actionable (G8-5 (ii));
- **permission needed:** the consent scopes absent (`ASSISTED_ENTRY` before
  conversion; `CONTACT_BEFORE_SHARING` where relevant).
- **Question:** does it show the source's raw text? Recommended: **no**, as
  the queue (G3-10 §3); the source is read through its own access path.

### G8-7 · Direct Interest (`postInterests`; F8-4, F8-10, F8-11)
- **Who:** a CUSTOMER for their own party only (`x-authorization`); staff
  for any party.
- **Which property, for a CUSTOMER:**
  - **(a) recommended:** only a property currently in the public list, by
    the same three conditions; any other property answers exactly as a
    non-existent one (`404`), so an interest cannot disclose a private or
    potential property (F8-10);
  - (b) any property, which F8-10 rules out.
- **A second interest on the same pair:**
  - (a) the idempotency key replays the first;
  - (b) without it, `409` (declared), naming no other party.
- **Never** a REQUEST, a match, or a task (mandatory test 2).
- **Audit:** the command layer, as every command.

### G8-8 · INTEREST → REQUEST (F8-5)
- **(a) recommended:** outside Slice 8. The interest stays INTEREST;
  mandatory test 2 needs no conversion to exist, only that none happens
  implicitly.
- (b) an explicit convert operation by Contract Delta (G8-4), creating a
  REQUEST for the interest's party and setting `CONVERTED_TO_REQUEST`.

### G8-9 · Self-service and accounts (F8-6, F8-11)
- **(a) recommended:** Slice 8 does not create accounts. Self-service
  creation and claiming stay as implemented, usable by accounts DL-07 does
  not yet create; the plan's closure states that a real self-service path
  does not exist until DL-07 is decided.
- (b) DL-07's administrative commands (CLI, no API), decided separately.
- (c) a self-registration flow by Contract Delta: a security change (RFC-001
  R10.4) and a permissions decision.

### G8-10 · PROPERTY claim eligibility (G3-2, F8-7)
- **(a) recommended:** stays open and fails closed.
- (b) decide a rule. It must not read `party_property_relations` as an
  authorization source (RFC-001 decision 1, R4.5).

### G8-11 · Public browsing
Already delivered (Slice 3 step 6). **Asked:** confirm that R6-P1 stays, and
that Slice 8's evidence for mandatory test 4 is the existing tests plus the
alias exclusion, rerun on this slice's tree.

### G8-12 · Migration `0009` (parts proposed; text in revision 2)
Only what G8-2 and G8-3 decide: the attempts table and its immutability
trigger; reason codes for outcomes; possibly a trigger guarding `CONVERTED`
and the terminal statuses. No change to the frozen baseline's tables beyond
what is decided.

### G8-13 · Audit
Every new command audited by the command layer; the Call Brief and the queue
as audited reads (R6), like the queue today.

### G8-14 · K06 and R-1 (not blocking this plan)
Unchanged and independent: nothing in this slice receives an event or claims
K06.

### Open questions (not decisions)
- **OQ8-1 · Personal data in captured posts.** A captured Facebook or
  Ouedkniss post can hold a third party's name and phone number, copied into
  `sources.raw_text` before any consent. Algerian law on the protection of
  personal data (Law No. 18-07 of 10 June 2018, as this revision recalls it;
  **NOT verified against the Journal Officiel**) may bear on this. It is to
  be verified against the official text before a rule is drawn from it.
- **OQ8-2 · Retention of a declined or closed lead's raw payload.** Not
  claimed, as OQ7-1 in Slice 7.

## 6. Tests and closure evidence

### 6.1 The four mandatory tests

| # | Test | Existing evidence | To add |
|---|---|---|---|
| 1 | discovery cannot become an active property without consent/workflow | `test_capture_writes_a_discovery_record_and_nothing_else`; `test_conversion_is_refused_with_a_typed_409_and_changes_nothing` | a FACEBOOK_POST and an OUEDKNISS_POST lead through every status short of `CONSENTED`: no PROPERTY, no REQUEST, no listing; PROPERTY conversion still refused |
| 2 | Direct Interest remains INTEREST | none (no route) | an interest writes one `interests` row and no `requests` row, no match, no task; replay and second-interest cases |
| 3 | assisted record claim reuses the domain id | `test_the_rightful_claimant_converts_the_record_in_place`; `test_two_concurrent_claims_produce_one_claim_and_no_ambiguity` | a REQUEST converted from a lead, then claimed: same id, one claim event, no copy |
| 4 | publication eligibility, not `supply_mode` alone | `test_d04_…`, `test_a_property_that_is_not_public_is_absent`, the alias exclusion | rerun; an interest refused on a property absent from the list (G8-7 (a)) |

### 6.2 Red-team cases
A03 (assisted party without login), C02 (interest is not request), C05
(assisted request claim), D04 (public property without an active public
offer), K02 (BOLA: a customer's own records only), K03 (public DTO
leakage), K04 (typed PATCH) and K05 (idempotency replay) for every new
projection and command (the Call Brief, the interest, the attempt).

### 6.3 Authorization
Every new operation's roles in the addendum; a CUSTOMER refused on every
staff operation; a CUSTOMER's interest for another party refused without
disclosing it; the architecture test of DEFECT-001 extended to each new
command.

### 6.4 Closure evidence
As Slice 7: a bound suite run, the matrix, the gate, mutation pairs for each
step, a closure record listing the limits carried (§0.3).

### 6.5 Measurements proposed for revision 2 (PostgreSQL 16; no code; NOT authorized yet)
- whether any application path writes `external_leads.status` other than
  its default (expected: none);
- the behaviour of the partial unique index on `interests` under two
  concurrent inserts (expected: one row, one unique violation);
- whether `enforce_consent_binding()` accepts a REQUEST binding for an
  `ASSISTED_ENTRY` grant of the request's party, as G8-5 (i) assumes.

## 7. Acceptance conditions
1. The four mandatory tests pass, with mutation pairs killing each guard.
2. No path creates an active PROPERTY or REQUEST from a lead without
   contact and consent (§3.1).
3. No path creates a REQUEST from an interest implicitly (§3.2).
4. No new path creates a duplicate on claim (§3.3).
5. No new projection exposes a floor field (red-team K03; G3-10 §3).
6. Every new operation is in an approved addendum bound by digest (G8-4).
7. The limits of §0.3 are carried into the closure record.
8. Not a release authorization.

## 8. Sequence (proposed; each step reviewed before the next)

| Step | Content | Depends on |
|---|---|---|
| 0 | the decisions G8-1 to G8-14; revision 2 with the Delta text, `0009`'s text and §6.5's measurements | this review |
| 1 | `0009` as approved; the attempts record and the status machine (service); tests | step 0 |
| 2 | the addendum's operations: contact attempts, status, Call Brief; tests | step 1 |
| 3 | REQUEST conversion (G8-5 (i)), lineage, claim after conversion; tests | step 2 |
| 4 | Direct Interest (G8-7); tests | step 0 (independent of 1 to 3) |
| 5 | mandatory tests end to end, closure evidence | 1 to 4 |

## 9. Document identity

This file's sha256 is recorded in `docs/gate/evidence/DOCUMENT-HASHES.txt`
at the commit that adds each revision.
