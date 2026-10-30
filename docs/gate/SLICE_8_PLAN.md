# Slice 8 — External Acquisition / Assisted Entry / Self-service
## Implementation plan — **revision 2**

**Status: revision 2 submitted for review.**
- **Revision 1 was accepted as a basis for planning** in the review of
  `3922850`, which authorized §6.5's measurements and preparing this
  revision. It is recorded below.
- **No code for this slice exists, and none is written.** The review did
  **not** approve the Contract Delta's text or migration `0009`, and did not
  authorize writing Slice 8's code. **§5A's texts are drafts for review:
  nothing in them is applied** (no addendum under `docs/contract/addenda/`,
  no migration under `db/migrations/`).
- **What this revision adds:** the review's directions (the section "The
  review of `3922850`", below); the measurements, run (§6.5,
  `evidence/SLICE8-PLAN-MEASUREMENTS.txt`); what Slice 8 delivers and what it
  declares deferred (§0.4); the drafts of §5A; OQ8-1 checked against the
  Journal Officiel.

**What it rests on:**
- **The findings of §4** rest on reading the frozen sources, the earlier
  slices' decisions and the code; F8-13 to F8-16 on the measurements.
- **The measurements** ran twice on a scratch database rebuilt from the
  frozen schema and the fixtures, with identical outputs. They say nothing
  about any deployed database.
- **OQ8-1** now cites the official texts it could read (§5, OQ8-1); it
  still decides nothing.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 2 | REV2_COMMIT | the review of `3922850` recorded; §6.5's measurements run, with the two the review added; §0.4 (delivered and deferred); §5A's drafts (status machine, Contract Delta, `0009`, Call Brief, Direct Interest, conversion, audit, queue paging), not applied; OQ8-1 checked against the Journal Officiel |
| 1 | `3922850` | first plan (planning only) |

---

## The review of `3922850`

**Revision 1 is accepted as a basis for planning.** §6.5's measurements and
preparing revision 2 are authorized. **The Contract Delta's text and
migration `0009` are not approved, and writing Slice 8's code is not
authorized.**

- **What the reviewer read:** the plan, the commit's diff (the plan, README
  and the hashes only), the slices document, the contract and G3-10. **The
  reviewer re-ran neither `run_binding` nor any test.**
- **The directions, decision by decision:**

| Decision | Direction for revision 2 |
|---|---|
| G8-1 | (a), on condition that what this slice delivers and what stays deferred are **named explicitly**. PROPERTY assisted entry and real self-service are **not declared complete** on the strength of a REQUEST test and fixture accounts: both are deliverables of the slices document |
| G8-2, G8-3 | a separate append-only record of attempts; contact statuses derived from the attempt; `CLOSED` and `DECLINED` never reopened. **Show the transitions and their guards in `0009`'s text before approval.** Distinguish `CONSENTED` recorded historically from **the consent's current validity**: the conversion re-checks validity and the binding in its own transaction, and does not rely on the status |
| G8-4 | preparing the **text** of the Delta and the addendum is authorized, the queue's paging included; applying them is not. Define the cursor's shape, its stable order, and **the behaviour under concurrent inserts**. G3-10's condition forbids operational volume before a contract that allows paging |
| G8-5 | REQUEST conversion only; PROPERTY stays refused. **`RAW` for the produced record**, until the plan proves a contractual reason for another status; never activated automatically. Show the payload schema, the current-consent check, and lineage both ways in one transaction |
| G8-6 | a computed Call Brief for staff, without `raw_text`. Define `known / missing / permission needed` in the Delta; a consent seen earlier never replaces checking it when a command runs |
| G8-7 | an interest on a property **eligible for publication at the moment of writing**; a uniform `404` to a customer for a property absent or not eligible, disclosing no id and **consuming no idempotency key** on refusal. The same key replays the result; a second insert with a new key for an active pair is `409`. **State whether the same eligibility applies to staff recording an interest for a party; recommended: to everyone** in this Direct Interest operation. Eligibility is the whole publication rule: the active offer, its current consent, R6-P1 and the alias exclusion (`public_listing.py`) |
| G8-8 to G8-11 | INTEREST conversion, account creation and PROPERTY claims stay outside, as declared; R6-P1 stays and is tested again. **A declared deferral, not a proof of those deliverables** |
| G8-12 to G8-14 | `0009` drafted for viewing only; the audit inventory proposed; K06 and R-1 carried as they are. **A database guard is never counted as K06** |

- **Added to the measurements:** the race between revoking `ASSISTED_ENTRY`
  and converting; the rows that exist before any new constraint.
- **Added to Direct Interest's tests:** refusing a property not published
  differs in **nothing** from a property that does not exist: the code, the
  body, and the writes.
- **Correction:** revision 1's history row names `3922850` (done above).
- **OQ8-1 stays open.** The reviewer could not fetch the official source.
  **No rule is drawn from it, and `raw_text` capture is neither widened nor
  put into operation on this assumption** before the official text is
  checked and a data policy is set.
- **Standing:** R-1 UNMET; K06 UNPROVEN; SALE only. This decision authorizes
  **measuring and drafting revision 2 for review**: no migration, no
  implementation, no release.

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

### 0.4 What Slice 8 delivers, and what it declares deferred (G8-1)

**The slices document's six deliverables and four mandatory tests, one by
one.** "Deferred" means **declared not delivered**; it is never reported as
complete.

| Deliverable or test | In Slice 8 | Deferred, and why |
|---|---|---|
| External Lead queues | the queue as it is, **plus paging** if the Delta is approved (§5A.8) | — |
| Call Brief | for staff, computed (§5A.4) | — |
| contact attempt outcome | the attempts record and the status machine (§5A.1, §5A.3) | — |
| assisted REQUEST entry after consent | REQUEST conversion (§5A.6) | — |
| **assisted PROPERTY entry after consent** | — | **deferred:** PROPERTY conversion stays refused (G3-10 Q-2 (b)); no relation path is decided |
| **self-service create** | — | **deferred:** works only for accounts nothing in TURAB can create (DL-07); fixture accounts prove nothing about it |
| **self-service claim** | REQUEST claim as it exists (CORRECTION-003) | **PROPERTY claim deferred** (G3-2) |
| public browsing | as it exists; R6-P1 kept and tested again | — |
| Direct Interest | `postInterests` (§5A.5) | **INTEREST → REQUEST conversion deferred** (G8-8) |
| mandatory test 1 | REQUEST and PROPERTY leads, every status short of conversion; PROPERTY conversion refused | — |
| mandatory test 2 | an interest never creates a REQUEST | the explicit conversion does not exist (G8-8) |
| mandatory test 3 | an **assisted REQUEST** converted from a lead, then claimed: same id | **not for a PROPERTY** (G3-2) |
| mandatory test 4 | rerun, plus an interest refused on a property not eligible | — |

**So Slice 8 cannot close as "all six deliverables delivered".** Its closure
record will list the deferred rows above as limits, as Slice 7's record listed
its own.

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
| **F8-13** | **A revocation can commit before a conversion that binds the revoked grant.** `enforce_consent_binding()` reads the grant without a lock, and the foreign key takes only `FOR KEY SHARE`, which does not conflict with the revocation's `UPDATE` of a non-key column. Measured: with no lock or with `FOR KEY SHARE`, the revocation commits first and the conversion still commits its binding. With `FOR SHARE` on the grant, the revocation waits; a revocation already in progress makes the conversion wait, then find no `GRANTED` grant | **M4** |
| **F8-14** | **Keyset paging on `(discovered_at, id)` skips a late-committed lead.** `discovered_at` is `now()`, the inserting transaction's start; a lead whose transaction began before a page's last row and committed after the page was read sorts before the cursor | **M6** |
| F8-15 | The application writes `external_leads` by one `INSERT` only. The suite's database holds one `DECLINED` lead, written **by a test** through SQL, not by the application | M1, M5 |
| F8-16 | Two concurrent `ACTIVE` interests for a pair: the second waits for the first's commit, then fails `23505` on `ux_active_interest_per_pair` | M2 |

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
  - produces `ASSISTED` / `UNCLAIMED`, status `RAW` (**directed in the
    review of `3922850`**: `RAW` until a contractual reason for another
    status is proven; never activated automatically);
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
- **OQ8-1 · Personal data in captured posts. Open; no rule is drawn from it.**
  - **The concern:** a captured Facebook or Ouedkniss post can hold a third
    party's name and phone number, copied into `sources.raw_text` before any
    consent.
  - **Checked against the Journal Officiel** (for revision 2, through the
    official PDFs on `joradp.dz`, read by automated text extraction):
    - **Law No. 18-07 of 25 Ramadhan 1439, 10 June 2018**, "relative à la
      protection des personnes physiques dans le traitement des données à
      caractère personnel": JORADP 2018 No. 34
      (`https://www.joradp.dz/FTP/jo-francais/2018/F2018034.pdf`);
    - its **article 7**: "Le traitement des données à caractère personnel ne
      peut être effectué qu'avec le consentement exprès de la personne
      concernée", followed by exceptions, among them a processing
      "nécessaire … à la réalisation d'un intérêt légitime poursuivi par le
      responsable du traitement ou par le destinataire, sous réserve de
      l'intérêt et/ou des droits et libertés fondamentaux de la personne
      concernée";
    - its **article 9**: the data are processed "de manière licite et
      loyale", collected for "finalités déterminées, explicites et
      légitimes", "adéquates, pertinentes et non excessives", and kept no
      longer than the purposes need;
    - **Law No. 25-11 of 28 Moharram 1447, 24 July 2025**, amends it:
      JORADP 2025 No. 48
      (`https://www.joradp.dz/FTP/jo-francais/2025/F2025048.pdf`). Its
      article 2 amends **articles 3 and 6** of Law 18-07; its article 7
      **repeals articles 10 and 11**; its other articles add chapters (a data
      protection officer, registers of processing, an impact study, data
      breaches). **Articles 7 and 9 are not named among those amended in the
      text read.** The definitions (article 3) were amended, so the 2018
      wording of a definition is not quoted here as current.
  - **What this does not settle:** whether capturing a public post is a
    processing that needs the person's consent or falls under the
    legitimate-interest exception, what the purpose limits allow, and what
    the declaration regime requires of TURAB. **These are legal judgements,
    for counsel and the national authority (ANPDP), not for this plan.** The
    automated extraction is to be checked against the printed text by a
    reader of the law.
  - **The review's direction stands:** `raw_text` capture is neither widened
    nor put into operation on this basis before the official text is read by
    a competent person and a data policy is set.
- **OQ8-2 · Retention of a declined or closed lead's raw payload.** Not
  claimed, as OQ7-1 in Slice 7.

## 5A. Revision 2's drafts — for review, NOT applied

**Status of everything in §5A:** drafts the review of `3922850` authorized
preparing. **None is approved, and none is applied:** no addendum file, no
migration file, no code. Where a draft still holds a choice, it is marked
**Q**, with a recommendation.

### 5A.1 The lead's status machine, with its guards (G8-3)

**Terminal statuses:** `CONVERTED`, `DECLINED`, `CLOSED`. Never left, never
reopened (the review's direction); a new discovery is a new lead.

**Transitions caused by a contact attempt** (derived, never set by hand; the
attempt's outcome codes are §5A.2's):

| Lead's status before | Outcome `LEAD_NO_ANSWER` | `LEAD_WRONG_NUMBER`, `LEAD_NUMBER_NOT_IN_SERVICE` | `LEAD_REACHED` |
|---|---|---|---|
| `DISCOVERED`, `CONTACT_ATTEMPTED`, `UNREACHABLE` | → `CONTACT_ATTEMPTED` | → `UNREACHABLE` | → `CONTACTED` |
| `CONTACTED`, `CONSENT_PENDING`, `CONSENTED`, `PENDING_INFO` | unchanged | unchanged | unchanged |
| a terminal status | **refused, `409`**; nothing written | same | same |

Every accepted attempt sets `last_contact_at` to its `occurred_at` when that
is later than the current value.

**Transitions by the status command** (§5A.4, operation 2):

| From | To | Guard, checked in the command's transaction |
|---|---|---|
| `CONTACTED` | `CONSENT_PENDING` | — |
| `CONTACTED`, `CONSENT_PENDING` | `CONSENTED` | `party_id` and `consent_id` given; **the grant row locked `FOR SHARE`** (F8-13), then: `status = 'GRANTED'`, `revoked_at IS NULL`, `scope = 'ASSISTED_ENTRY'`, the grant's party = `party_id`. Sets `external_leads.party_id` |
| `CONSENTED` | `PENDING_INFO` | — |
| any non-terminal | `DECLINED` | a reason code of category `LEAD_CLOSURE` |
| any non-terminal | `CLOSED` | a reason code of category `LEAD_CLOSURE` |

**`CONVERTED`** is reached by the conversion only (§5A.6).

**`CONSENTED` is history, not authority** (the review's direction). It
records that a current grant was seen when the status was set. **It never
authorizes a conversion by itself:** the conversion re-checks the grant's
current validity, under the same lock, in its own transaction (§5A.6). A
grant revoked after `CONSENTED` leaves the status as it is, and makes the
conversion refuse.

**Where each rule is enforced:**
- **in the service:** the whole table above;
- **in `0009`'s trigger** (§5A.3): a terminal status never changes; `CONVERTED`
  only from `CONSENTED` or `PENDING_INFO`; `CONSENTED` only with a `party_id`;
  `DECLINED` and `CLOSED` only with a `close_reason_code`.
- **Not K06:** the trigger guards what a careless write can do through the
  application role; with the application role a superuser that owns every
  table, it is not a privilege boundary (G8-14).

**Q-A1 · The existing test that writes `DECLINED` by SQL without a reason
code** (`test_the_queue_lists_open_leads_oldest_first_and_omits_closed_ones`,
F8-15) would be refused by the trigger. Recommended: that test sets a
reason code, in the step that applies `0009`. The trigger acts on `UPDATE`
only: the row already in the suite's database (M5) is not touched.

### 5A.2 Reason codes (inserted by `0009`)

None named `LEAD_*` exists in any database measured (M5).

| Code | Category | `label_ar` | `label_en` |
|---|---|---|---|
| `LEAD_NO_ANSWER` | `LEAD_CONTACT` | لم يُجب | No answer |
| `LEAD_REACHED` | `LEAD_CONTACT` | تم التواصل | Reached |
| `LEAD_WRONG_NUMBER` | `LEAD_CONTACT` | رقم خاطئ | Wrong number |
| `LEAD_NUMBER_NOT_IN_SERVICE` | `LEAD_CONTACT` | رقم غير مستعمل | Number not in service |
| `LEAD_DECLINED_BY_PERSON` | `LEAD_CLOSURE` | رفض الشخص | Declined by the person |
| `LEAD_DUPLICATE` | `LEAD_CLOSURE` | مكرّر | Duplicate |
| `LEAD_NOT_RELEVANT` | `LEAD_CLOSURE` | خارج النطاق | Not relevant |
| `LEAD_STALE` | `LEAD_CLOSURE` | قديم | Stale |

**Q-A2:** the labels are proposals; the reviewer may replace them.

### 5A.3 Migration `0009` — draft text, for viewing only

```sql
-- 0009_external_lead_workflow — DRAFT for review (Slice 8 plan rev 2, §5A.3).
-- NOT APPLIED. No file under db/migrations/ holds this text.

-- 1. The attempts record: append-only (G8-2 (a)).
CREATE TABLE turab.external_lead_contact_attempts (
  attempt_id          uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_lead_id    uuid NOT NULL REFERENCES turab.external_leads(external_lead_id)
                        ON DELETE RESTRICT,
  channel             turab.communication_channel NOT NULL,
  outcome_code        text NOT NULL REFERENCES turab.reason_codes(code),
  occurred_at         timestamptz NOT NULL,
  operator_account_id uuid NOT NULL REFERENCES turab.user_accounts(account_id)
                        ON DELETE RESTRICT,
  recorded_at         timestamptz NOT NULL DEFAULT clock_timestamp(),
  CHECK (occurred_at <= recorded_at + interval '5 minutes')
);
CREATE INDEX idx_lead_attempts_lead ON turab.external_lead_contact_attempts
  (external_lead_id, occurred_at, attempt_id);

-- Its outcome must be a LEAD_CONTACT code.
CREATE FUNCTION turab.enforce_lead_attempt_outcome() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM turab.reason_codes
                  WHERE code = NEW.outcome_code AND category = 'LEAD_CONTACT') THEN
    RAISE EXCEPTION 'outcome_code % is not a LEAD_CONTACT code', NEW.outcome_code;
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_lead_attempt_outcome BEFORE INSERT
  ON turab.external_lead_contact_attempts
  FOR EACH ROW EXECUTE FUNCTION turab.enforce_lead_attempt_outcome();

-- Append-only, as 0005 and 0006 made match and opportunity history.
CREATE FUNCTION turab.prevent_lead_attempt_change() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  RAISE EXCEPTION 'external_lead_contact_attempts is append-only';
END $$;
CREATE TRIGGER trg_lead_attempt_immutable BEFORE UPDATE OR DELETE
  ON turab.external_lead_contact_attempts
  FOR EACH ROW EXECUTE FUNCTION turab.prevent_lead_attempt_change();

-- 2. The lead's guards (§5A.1). UPDATE only: existing rows are not re-checked.
CREATE FUNCTION turab.enforce_external_lead_transition() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.status IS DISTINCT FROM OLD.status THEN
    IF OLD.status IN ('CONVERTED', 'DECLINED', 'CLOSED') THEN
      RAISE EXCEPTION 'a lead in status % is terminal', OLD.status;
    END IF;
    IF NEW.status = 'CONVERTED' AND OLD.status NOT IN ('CONSENTED', 'PENDING_INFO') THEN
      RAISE EXCEPTION 'CONVERTED only from CONSENTED or PENDING_INFO, not %', OLD.status;
    END IF;
    IF NEW.status = 'CONSENTED' AND NEW.party_id IS NULL THEN
      RAISE EXCEPTION 'CONSENTED requires party_id';
    END IF;
    IF NEW.status IN ('DECLINED', 'CLOSED') AND NEW.close_reason_code IS NULL THEN
      RAISE EXCEPTION '% requires close_reason_code', NEW.status;
    END IF;
  END IF;
  IF OLD.status IN ('CONVERTED', 'DECLINED', 'CLOSED')
     AND (NEW.party_id, NEW.converted_request_id, NEW.converted_property_id,
          NEW.close_reason_code)
         IS DISTINCT FROM
         (OLD.party_id, OLD.converted_request_id, OLD.converted_property_id,
          OLD.close_reason_code) THEN
    RAISE EXCEPTION 'a terminal lead''s workflow columns are frozen';
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_external_lead_transition BEFORE UPDATE ON turab.external_leads
  FOR EACH ROW EXECUTE FUNCTION turab.enforce_external_lead_transition();

-- 3. The reason codes of §5A.2.
INSERT INTO turab.reason_codes (code, category, label_ar, label_en) VALUES
  ('LEAD_NO_ANSWER',             'LEAD_CONTACT', 'لم يُجب',        'No answer'),
  ('LEAD_REACHED',               'LEAD_CONTACT', 'تم التواصل',     'Reached'),
  ('LEAD_WRONG_NUMBER',          'LEAD_CONTACT', 'رقم خاطئ',       'Wrong number'),
  ('LEAD_NUMBER_NOT_IN_SERVICE', 'LEAD_CONTACT', 'رقم غير مستعمل', 'Number not in service'),
  ('LEAD_DECLINED_BY_PERSON',    'LEAD_CLOSURE', 'رفض الشخص',      'Declined by the person'),
  ('LEAD_DUPLICATE',             'LEAD_CLOSURE', 'مكرّر',           'Duplicate'),
  ('LEAD_NOT_RELEVANT',          'LEAD_CLOSURE', 'خارج النطاق',    'Not relevant'),
  ('LEAD_STALE',                 'LEAD_CLOSURE', 'قديم',           'Stale');
-- DECLINED/CLOSED reason codes must be LEAD_CLOSURE: enforced by the service
-- (close_reason_code's foreign key admits any reason code). Q-A3 below.
```

**Q-A3 · Should the trigger also require `close_reason_code`'s category to
be `LEAD_CLOSURE`?** Recommended: yes, one more `IF` in the same function.
Left out of the draft so the reviewer decides it.

**Q-A4 · The audit trigger** that the frozen schema puts on core tables
(`audit_row_change`): recommended on `external_lead_contact_attempts` too, as
on `claims`. To be read against the frozen audit function before revision 3.

**Before applying:** the "existing rows" check (M5) is repeated on the
database the migration targets, and its counts recorded, as the review asked.

### 5A.4 The Contract Delta — draft operations (G8-4)

**Mechanism, as G3-6:** a Delta document (`CONTRACT_DELTA_SLICE8_*.md`) for
approval, then a standalone addendum (`docs/contract/addenda/ADD-SLICE8_*.yaml`)
whose operations are all NEW (their `operationId` and METHOD+PATH absent from
the frozen contract), bound by the Delta's digest. The frozen file is never
edited.

**1. `postExternalLeadsLeadIdContactAttempts`**
- `POST /external-leads/{lead_id}/contact-attempts`; roles ADMIN, OPERATOR;
  `Idempotency-Key` required.
- Body `ContactAttemptCreate`, `additionalProperties: false`:
  `channel` (one of `PHONE`, `WHATSAPP`, `SMS`, `IN_PERSON`, `OTHER`),
  `outcome_code` (one of §5A.2's `LEAD_CONTACT` codes), `occurred_at`
  (date-time, not in the future). **No free-text field** (§3.7).
- `201` `{attempt_id, lead_id, lead_status}`; `404` no such lead; `409`
  `EXTERNAL_LEAD_TERMINAL`; `422` the body.

**2. `postExternalLeadsLeadIdStatus`**
- `POST /external-leads/{lead_id}/status`; roles ADMIN, OPERATOR;
  `Idempotency-Key` required.
- Body `LeadStatusChange`, `additionalProperties: false`: `to` (one of
  `CONSENT_PENDING`, `CONSENTED`, `PENDING_INFO`, `DECLINED`, `CLOSED`);
  `party_id` and `consent_id` (required exactly when `to = CONSENTED`);
  `reason_code` (required exactly when `to` is `DECLINED` or `CLOSED`).
- `200` `{lead_id, status}`; `404`; `409` `EXTERNAL_LEAD_TRANSITION_NOT_ALLOWED`
  or `CONSENT_NOT_CURRENT`; `422`.

**3. `getExternalLeadsLeadIdCallBrief`** (G8-6)
- `GET /external-leads/{lead_id}/call-brief`; roles ADMIN, OPERATOR,
  REVIEWER; an audited read.
- Response `CallBrief`, computed at the read, stored nowhere:

| Field | Content |
|---|---|
| `lead_id`, `lead_kind`, `status`, `source_kind`, `discovered_at` | from the lead and its source |
| `attempts` | `{count, last_outcome_code, last_occurred_at}` |
| `known` | a list of codes for what TURAB holds **as records**: `PARTY_IDENTIFIED`, `CONTACT_POINT_VERIFIED` (a contact point of the party with `VERIFIED_CONTROL`), `CONSENT_CURRENT` (an `ASSISTED_ENTRY` grant of the party, `GRANTED` and unrevoked **at the read**) |
| `missing` | the codes of `known` that are absent, plus, for a REQUEST lead, the conversion payload's required fields (§5A.6), which no record holds before the conversion: they are collected on the call |
| `permission_needed` | `ASSISTED_ENTRY` when `CONSENT_CURRENT` is absent; for a PROPERTY lead, `PROPERTY_CONVERSION_NOT_AVAILABLE` (G3-10 Q-2) |
| `as_of` | the read's time |

- **Never in it:** `raw_text`, the source's URL or reference, `raw_payload`,
  metadata, a contact point's value (the review's direction; G3-10 §3).
- **A brief's `CONSENT_CURRENT` authorizes nothing:** every command re-checks
  the grant itself, under its lock (the review's direction).

**4. Queue paging** (§5A.8).

**5. The REQUEST conversion payload** (§5A.6), declared as the schema of
`postExternalLeadsLeadIdConvert`'s `payload` for `target = REQUEST`. **Q-A5:**
the frozen operation's `payload` is an open object; declaring its schema is
a narrowing a CORRECTION can carry (it may only narrow), not an addendum
operation. Recommended: CORRECTION, bound like CORRECTION-001 to 008.

**6. `postInterests`** needs no Delta: it is frozen. Its rules are §5A.5.

### 5A.5 Direct Interest (`postInterests`; G8-7)

1. **Eligibility at the moment of writing**, for **every caller**, customer
   and staff alike (recommended, as the review recommends): the property
   satisfies the whole publication rule of `public_listing.py` (the
   `PUBLIC` supply mode, an `ACTIVE` offer, that offer's currently valid
   `PUBLIC_LISTING_ALLOWED` binding of its own party, R6-P1, not an
   identity alias), **evaluated inside the write's transaction**.
   - An interest written while eligible **stays** when the property later
     leaves the public list. It records a moment, not a standing right.
2. **A CUSTOMER** names their own party only. Another party, as every
   customer-scoped denial (`for_denial`, `customer_scoped=True`): concealed.
3. **Refusal: absent and not eligible are identical.**
   - `404`, `code = NOT_FOUND`, the same `title`, the same `detail` (or none),
     no `field_errors`: **the same body except `trace_id`**, which is per
     request by design (`Problem` schema).
   - **The same writes:** no `interests` row, **no idempotency key consumed**
     (as G3-10's refusal), and **the same audit trace** for both, or none for
     either. The test compares the rows of every table before and after, for
     both cases.
4. **The same `Idempotency-Key`** replays the first result.
5. **A new key for a pair already `ACTIVE`:** `409`
   `INTEREST_ALREADY_ACTIVE`. Concurrent inserts are serialized by
   `ux_active_interest_per_pair` (M2): the loser's `23505` is mapped to the
   same `409`.
6. **Never** a REQUEST, a match, a task, an opportunity or a thread.
7. **Response:** `201` `{interest_id, status: "ACTIVE"}`, as declared.

### 5A.6 REQUEST conversion (G8-5)

**One transaction, in this order:**
1. lock the lead `FOR UPDATE`; refuse unless `lead_kind = 'REQUEST'`,
   `status IN ('CONSENTED', 'PENDING_INFO')`, `party_id IS NOT NULL`;
2. the body's `consent_id` (required by the frozen operation): lock the
   grant **`FOR SHARE`** (F8-13, M4), then require `status = 'GRANTED'`,
   `revoked_at IS NULL`, `scope = 'ASSISTED_ENTRY'`, the grant's party = the
   lead's party = the body's `party_id`. **The lead's `CONSENTED` is not
   evidence** (§5A.1);
3. insert the request: the lead's party, `management_mode = 'ASSISTED'`,
   `claim_status = 'UNCLAIMED'`, **`status = 'RAW'`** (the review's
   direction); its fields from the payload;
4. bind the grant to the request, purpose `ASSISTED_ENTRY` (M3: accepted for
   the request's party's grant);
5. provenance: the request's fields recorded through `provenance` (an
   `observations` row and `claims` rows), **each carrying the lead's
   `source_id`** (G3-10 Q-4 (c));
6. the lead: `status = 'CONVERTED'`, `converted_request_id` set.

Any refusal writes nothing and consumes no idempotency key. **Never
activated:** nothing moves the request beyond `RAW`.

**The payload schema** (`target = REQUEST`): `RequestCreate` without
`party_id`, `management_mode` and `claim_status`, which the conversion sets;
`additionalProperties: false`. **Q-A6:** `transaction_intent` limited to
`BUY` in this slice, since G4-5R refuses RENT matching? Recommended: no
limit at conversion (a RENT request may be recorded, as `postRequests`
allows); matching stays refused for RENT, as today.

**PROPERTY:** `409 EXTERNAL_LEAD_CONVERSION_NOT_AVAILABLE`, as today.

### 5A.7 Audit inventory (G8-13)

| Operation | Kind | Audit |
|---|---|---|
| `postExternalLeadsLeadIdContactAttempts` | command | the command layer, once per accepted command; a refusal as every refusal |
| `postExternalLeadsLeadIdStatus` | command | same |
| `postExternalLeadsLeadIdConvert` (REQUEST) | command | same; the produced request id in the audit row |
| `postInterests` | command | same; **refusals for absent and not eligible identical** (§5A.5) |
| `getExternalLeadsLeadIdCallBrief` | read | audited once per read (R6), like the queue |
| the paged queue (§5A.8) | read | audited once per page |
| `external_lead_contact_attempts` | table | `audit_row_change` (Q-A4) |

### 5A.8 Queue paging (G8-4; F8-14, M6)

- **A new operation** (Q-A7), since an addendum carries only new
  operations: `GET /backoffice/queues/external-leads/page`, roles ADMIN,
  OPERATOR, REVIEWER; query `cursor` (optional), `limit` (1 to 200, default
  50). The frozen `getBackofficeQueuesExternalLeads` stays as it is.
- **Order:** `discovered_at ASC, external_lead_id ASC`: total and stable.
- **Cursor:** opaque, base64url of `{"v":1,"at":<discovered_at, microseconds>,
  "id":<lead id>,"walk":<walk_started_at>}`; malformed: `422`. It carries
  nothing a staff member did not already see.
- **Concurrent inserts, as measured (M6):** a lead whose inserting
  transaction began before the cursor's row and committed after the page was
  read sorts before the cursor, and **that walk never returns it**.
  `discovered_at` is the transaction's start; commit order is not timestamp
  order.
- **The rule proposed, stated rather than hidden:**
  - **a walk returns every open lead committed before its first page was
    read** (`walk_started_at`, carried in every cursor and every page);
  - a lead committed during a walk may be missed **by that walk only**; the
    next walk, started from no cursor, returns it;
  - every page carries `walk_started_at`, so a client knows which leads the
    walk guarantees.
- **Q-A8:** narrow the gap by setting `discovered_at = clock_timestamp()` at
  capture, in a short transaction? It narrows the window; it does not close
  it (commit order ≠ timestamp order). Recommended: yes, with the rule above
  unchanged.
- **G3-10's condition:** "the absence of a page parameter must never become
  a silent drop". With the rule above, nothing is dropped: a lead missed by
  one walk is returned by the next, and the response says what a walk
  guarantees.

## 6. Tests and closure evidence

### 6.1 The four mandatory tests

| # | Test | Existing evidence | To add |
|---|---|---|---|
| 1 | discovery cannot become an active property without consent/workflow | `test_capture_writes_a_discovery_record_and_nothing_else`; `test_conversion_is_refused_with_a_typed_409_and_changes_nothing` | a FACEBOOK_POST and an OUEDKNISS_POST lead through every status short of `CONSENTED`: no PROPERTY, no REQUEST, no listing; PROPERTY conversion still refused |
| 2 | Direct Interest remains INTEREST | none (no route) | an interest writes one `interests` row and no `requests` row, no match, no task, no opportunity, no thread; replay with the same key; `409` with a new key; two concurrent inserts (one row, one `409`) |
| 3 | assisted record claim reuses the domain id | `test_the_rightful_claimant_converts_the_record_in_place`; `test_two_concurrent_claims_produce_one_claim_and_no_ambiguity` | a REQUEST converted from a lead, then claimed: same id, one claim event, no copy |
| 4 | publication eligibility, not `supply_mode` alone | `test_d04_…`, `test_a_property_that_is_not_public_is_absent`, the alias exclusion | rerun, R6-P1 included; **an interest on a property not eligible (each of: not `PUBLIC`, no `ACTIVE` offer, the binding revoked, R6-P1, an alias) answers exactly as one on a property that does not exist: the same status, `code`, `title`, `detail` and fields (`trace_id` aside), the same rows in every table before and after, and the idempotency key still free** (§5A.5, the review's direction) |

### 6.2 Red-team cases
A03 (assisted party without login), C02 (interest is not request), C05
(assisted request claim), D04 (public property without an active public
offer), K02 (BOLA: a customer's own records only), K03 (public DTO
leakage), K04 (typed PATCH) and K05 (idempotency replay) for every new
projection and command (the Call Brief, the interest, the attempt).

### 6.2a The races, as tests (from M4 and M2)
- a revocation committed while a conversion holds the grant `FOR SHARE`:
  the conversion commits first, the revocation after (the binding inert,
  ADR-04);
- a revocation in progress when the conversion starts: the conversion
  waits, then refuses `409 CONSENT_NOT_CURRENT`, writing nothing;
- a lead `CONSENTED` whose grant is revoked afterwards: the conversion
  refuses (§5A.1, "history, not authority");
- a mutation removing the `FOR SHARE` lock must be killed: the test that
  revokes during the conversion's window, with the revocation committing
  first, must fail on it.

### 6.3 Authorization
Every new operation's roles in the addendum; a CUSTOMER refused on every
staff operation; a CUSTOMER's interest for another party refused without
disclosing it; the architecture test of DEFECT-001 extended to each new
command.

### 6.4 Closure evidence
As Slice 7: a bound suite run, the matrix, the gate, mutation pairs for each
step, a closure record listing the limits carried (§0.3).

### 6.5 Measurements (run for revision 2; `evidence/SLICE8-PLAN-MEASUREMENTS.txt`)

Authorized in the review of `3922850`. Run twice on a scratch database
(the frozen schema, the seed, the migrations, the dev fixtures), with
identical outputs; the script is kept beside its record, outside the
fingerprinted trees.

| # | Measurement | Result |
|---|---|---|
| M1 | which application statements write `external_leads` | one `INSERT` (`services/external_leads.py`); no status write (F8-15) |
| M2 | two concurrent `ACTIVE` interests for one pair | the second waits, then `23505` on `ux_active_interest_per_pair`; one row (F8-16) |
| M3 | `enforce_consent_binding()`, REQUEST, `ASSISTED_ENTRY` | the request's party's grant accepted; another party's, a revoked one, and another purpose refused |
| M4 | **the review's addition:** revocation racing a conversion | no lock or `FOR KEY SHARE`: the revocation commits first, the binding still commits; `FOR SHARE`: ordered; revocation first: the conversion waits, then refuses (F8-13) |
| M5 | **the review's addition:** rows before any new constraint | no workflow column set anywhere; the suite's one `DECLINED` lead is a test's; no duplicate active interest; no `LEAD_*` code; no attempts table. Test and probe databases only |
| M6 | keyset paging, a late commit | the late-committed lead sorts before the cursor and is never returned by that walk (F8-14) |

**Before `0009` is applied:** M5 repeated on the target database, its counts
recorded (§5A.3).

## 7. Acceptance conditions
1. The four mandatory tests pass, with mutation pairs killing each guard.
2. No path creates an active PROPERTY or REQUEST from a lead without
   contact and consent (§3.1).
3. No path creates a REQUEST from an interest implicitly (§3.2).
4. No new path creates a duplicate on claim (§3.3).
5. No new projection exposes a floor field (red-team K03; G3-10 §3).
6. Every new operation is in an approved addendum bound by digest (G8-4).
6a. Every conversion re-checks the grant's current validity under `FOR
    SHARE`, in its transaction; a `CONSENTED` status is never evidence
    (§5A.1, §5A.6).
6b. An interest's refusal for a property not eligible is indistinguishable
    from one for a property that does not exist (§5A.5).
6c. The deferred rows of §0.4 are listed as limits in the closure record;
    none is reported delivered.
7. The limits of §0.3 are carried into the closure record.
8. Not a release authorization.

## 8. Sequence (proposed; each step reviewed before the next)

| Step | Content | Depends on |
|---|---|---|
| 0 | the decisions G8-1 to G8-14; revision 2 with the Delta text, `0009`'s text and §6.5's measurements | **revision 2 delivered for review**; the Delta's and `0009`'s texts **not approved**, code **not authorized** (review of `3922850`) |
| 1 | `0009` as approved; the attempts record and the status machine (service); tests | step 0 |
| 2 | the addendum's operations: contact attempts, status, Call Brief; tests | step 1 |
| 3 | REQUEST conversion (G8-5 (i)), lineage, claim after conversion; tests | step 2 |
| 4 | Direct Interest (G8-7); tests | step 0 (independent of 1 to 3) |
| 5 | mandatory tests end to end, closure evidence | 1 to 4 |

## 9. Document identity

This file's sha256 is recorded in `docs/gate/evidence/DOCUMENT-HASHES.txt`
at the commit that adds each revision.
