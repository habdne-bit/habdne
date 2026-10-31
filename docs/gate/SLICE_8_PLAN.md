# Slice 8 — External Acquisition / Assisted Entry / Self-service
## Implementation plan — **revision 4**

**Status: revision 4 submitted for review (planning only).**
- **The review of `0a78e91`** decided Q-B1 (a), Q-B2 (b) and Q-B3 (a); did
  **not** approve `0009`'s text or CORRECTION-009; did **not** authorize
  Slice 8's step 1; authorized **one bounded preparatory step** for Q-B3
  (`add_all_of`), delivered separately (`SLICE_8_PREP_ADD_ALL_OF_DELIVERY.md`).
  Recorded below.
- **This revision's corrections:** the draft of `0009` carries its Alembic
  metadata and was run **through Alembic** in the real chain (M12); the clock
  rule is bounded precisely, `recorded_at` assigned by the server (M13); the
  wording of Q-B1 is restricted after measuring a `CONVERTED` lead (M14).
- **Nothing of the slice is applied:** no file under `db/migrations/` or
  `docs/contract/` changed for it; no slice command exists.
- **The drafts** stay under `docs/gate/drafts/`; CORRECTION-009's literal
  YAML and its generated diff come after the preparatory step, as the review
  asked.

**What it rests on:**
- **The findings of §4** rest on reading the frozen sources, the earlier
  slices' decisions and the code; F8-13 to F8-18 on the measurements.
- **The measurements** ran twice each on scratch databases, with identical
  outputs. They say nothing about any deployed database.
- **OQ8-1** stays open. The reviewer could not verify its citations
  independently; they are ours and unconfirmed.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 4 | `1c8a6ba` | the review of `0a78e91` recorded: Q-B1 (a), Q-B2 (b), Q-B3 (a); the draft of `0009` with its revision metadata, run through Alembic (M12); `recorded_at` assigned by the server (M13); Q-B1's wording restricted after the `CONVERTED` case (M14); R3 re-run on the revised draft, unchanged |
| 3 | `1eafe4c` | the review of `b39ad10` recorded; Q-A1 to Q-A8 applied; §5A.8's guarantee rewritten to the query (Delta §3.4); `0009`'s clock rule and the party-deletion consequence settled in its draft and measured (M7 to M11); the drafts as files under `docs/gate/drafts/`, with the expected effective contract generated |
| 2 | `3db08bb` | the review of `3922850` recorded; §6.5's measurements run, with the two the review added; §0.4 (delivered and deferred); §5A's drafts (status machine, Contract Delta, `0009`, Call Brief, Direct Interest, conversion, audit, queue paging), not applied; OQ8-1 checked against the Journal Officiel |
| 1 | `3922850` | first plan (planning only) |

---

## The review of `0a78e91`

**Q-B1 to Q-B3 are decided as below. `0009`'s text and CORRECTION-009 are
not approved yet, and Slice 8's step 1 is not authorized.** The reviewer
read the drafts and the records; the measurements are ours, not re-run.

| | Decision |
|---|---|
| **Q-B1** | **(a):** keep the frozen key's `ON DELETE SET NULL`, declaring that a NULL written by hand passes the guard too; **prove the service never writes it**. M9 proves deleting a party linked to a `DECLINED` lead; **do not generalize it to deleting a `CONVERTED` lead's target**: the frozen check requires `CONVERTED` to keep its target. **Measure that case and restrict "links may become NULL".** Deleting a party proves neither the erasure of `raw_payload` nor the fulfilment of a data-erasure request |
| **Q-B2** | **(b), now:** the frozen operation's roles stay as they are. Narrowing them to `ADMIN` would not make its unpaged query safe at operational volume: `ADMIN` could still run it. **The new paged operation is the approved operating path; the old one's limit of use is carried into the closure and the operational setup** |
| **Q-B3** | **(a):** a **separate, limited preparatory step** is authorized: `add_all_of` in the corrections loader, the contract generator and their tests. **Not included:** activating CORRECTION-009, moving `0009` into Alembic, or writing the slice's commands. **Prove** the addition applies to an operation-local copy of the body, that **the effective contract and the runtime validation reject the same payload**, with tests refusing invalid correction input and showing **no other operation changes** |

- **Two corrections asked before the texts are approved:**
  1. **`0009` was not yet a complete Alembic revision:** "Would-be Revision
     ID" in its docstring, but no `revision`/`down_revision` as `0008` has.
     M7 to M11 tested its statements, not its place in Alembic's chain.
     **Add the revision metadata, then test upgrade and downgrade through
     Alembic on a temporary database, the downgrade refused with data.**
  2. **The clock rule needs a tighter description.** `occurred_at <=
     recorded_at` is measured, but `recorded_at DEFAULT clock_timestamp()`
     does not stop an INSERT from supplying an explicit value, so "both
     sides are always the server's clock" claimed more than the database
     guarantees. **Either the draft makes the server assign `recorded_at`,
     or the constraint is described as a comparison of two columns**, the
     service relying on the server's value and the explicit value tested.
     Neither counts as a remedy for K06.
- **Paging:** the new wording is closer to what the pages do (each query its
  own snapshot under READ COMMITTED; no snapshot for the walk). The late
  commit and the status change are accepted as Delta §3.4 states them, **to
  be proved by tests of the actual path**.
- **CORRECTION-009 is not complete for approval:** its `payload` entry is
  still a descriptive placeholder between `<…>`, and part 3 of the expected
  contract is marked not generated. **After the preparatory step, show the
  literal YAML schema and the effective-contract diff the generator
  produces; then the correction, the Delta and the migration are reviewed in
  final form before step 1.**
- **OQ8-1 stays open;** `raw_text` capture is not widened.
- **Standing:** R-1 UNMET; K06 UNPROVEN; SALE only; not a release
  authorization.

---

## The review of `b39ad10`

**Revision 2's measurements are accepted as a basis for planning. The texts
of `0009` and of the Delta are not approved in their current form, and code
is not authorized.** A planning revision 3 is authorized, with the
corrections, the Delta's and the correction's texts and the resulting
contract, and `0009`'s text with its downgrade and the tests of its
consequences. **The reviewer re-ran neither the measurements nor
`run_binding`.**

- **M4 is decisive.** `FOR KEY SHARE` does not order a conversion against a
  revocation; `FOR SHARE` orders them in both directions measured. **Adopted:
  the conversion locks the grant row `FOR SHARE` and re-checks its state in
  its transaction, with a race test through the actual conversion command
  when it is implemented.** `CONSENTED` stays a historical fact, not a
  standing permission. The decision rests on the measurement within its
  limits: probe transactions, not the conversion command, which is not
  written.
- **Q-A1 to Q-A8:**

| | Decision | Where applied |
|---|---|---|
| Q-A1 | yes: the `DECLINED` test supplies a valid reason when `0009` is applied; the guard stays as it is | §6.6; M7 |
| Q-A2 | the eight codes accepted in principle; `LEAD_NUMBER_NOT_IN_SERVICE`'s Arabic label is «خارج الخدمة», not «غير مستعمل»; the final text fixed in the next revision | §5A.2; the draft |
| Q-A3 | yes: the guard checks the `LEAD_CLOSURE` category when a reason is set, not only that the code exists; **state what changing the reason of a closed row does** | the draft; M9 |
| Q-A4 | yes: `INSERT` on the attempts audited by `audit_row_change('attempt_id')`. The frozen function records the whole row, so **no free text and no content of a contact in that table** stays a required condition | the draft; M10 |
| Q-A5 | a **CORRECTION** narrowing the open `payload` is reasonable, but **show the correction's text and the expected effective contract in full** for approval; §5A.6's description is not enough to approve a contract correction | CORRECTION-009 draft; the expected contract |
| Q-A6 | do not limit a `RAW` request to `BUY` because RENT matching is not approved: the existing contract accepts recording it. **Prove that a conversion activates no RENT request and opens no matching or opportunity for it, and that this slice's evidence stays SALE only** | §5A.6; §6.7 |
| Q-A7 | a **new** paging operation in the addendum, not a change to the frozen one. **State that operational volume uses it; the old unbounded operation does not become safe because the new path exists** | Delta §3.5; Q-B2 |
| Q-A8 | **not adopted:** `discovered_at` does not move to `clock_timestamp()` now. It does not order rows by commit time, and could change the meaning of the discovery time without closing the gap. Keep the current time, the measured limit of a walk, and test a new walk | §5A.8; §6.8 |

- **A correction required in §5A.8 before the contract is approved:**
  "a walk returns every open lead committed before its first page was read"
  was stronger than the cursor proves. `walk_started_at` is a value in a
  response, not a database snapshot held across pages, and a lead's status
  can change between two pages; M6 shows a late commit falling behind the
  cursor. **Word the guarantee to what the queries actually do; say that a
  new walk reconsiders the row if it is still eligible for the queue; show
  the cursor's query and the cases of committed inserts and status changes
  between pages.** (Delta draft §3.4.)
- **Two points of `0009` to settle in its text before approval:**
  - the Delta said `occurred_at` is "not in the future", while the SQL
    accepted up to five minutes after `recorded_at`: **choose one rule**,
    and justify a clock margin if one is chosen;
  - the guard freezing a terminal lead's columns forbids making `party_id`
    NULL, while the frozen key `external_leads.party_id` is `ON DELETE SET
    NULL`: deleting a party a terminal lead names may be refused. **State
    and measure that consequence before the text is approved; do not present
    it as the earlier schema's behaviour.**
- **OQ8-1:** the reviewer could not fetch the two Journal Officiel files and
  verify them independently in that session, so cannot confirm the quotes or
  apply the legal exception to capturing posts. It stays open; `raw_text`'s
  use is not widened on an unsettled legal reading.
- **The reviewer's own correction:** an automated citation token in the
  reviewer's previous message led to no source actually fetched, and is
  **withdrawn**. The direct links to the repository's files are what was
  reviewed.
- **Standing:** R-1 UNMET; K06 UNPROVEN; the evidence's scope SALE only; not
  a release authorization.

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
9. **The frozen unpaged queue is not for operational volume** (G3-10 Q-8;
   Q-B2 (b), review of `0a78e91`). The paged operation is the operating path;
   this limit goes into the closure record and the operational setup.

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
| **F8-17** | **A guard freezing a terminal lead's `party_id` refuses a party's deletion.** The frozen `external_leads.party_id` is `ON DELETE SET NULL`; the foreign key's action is an `UPDATE`, and fires the guard. Measured on the draft's strict variant: the deletion of a party a `DECLINED` lead names is refused; for an open lead it passes. As `0008`'s M8 found for thread links | **M9** |
| **F8-18** | **The correction overlay cannot narrow an inner schema.** `contract.py` accepts `require`, `non_null`, `enum`, `frozen_defaults` on a body's own properties only; the open `payload` cannot be given a schema without a new narrowing key (Q-B3) | `_BODY_NARROWING_KEYS`; the generator run |

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
  - **Not confirmed by the reviewer** (review of `b39ad10`): the quotes above
    are ours, read by automated extraction; the reviewer could not fetch the
    files to verify them.
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
- **in `0009`'s trigger** (§5A.3, revision 3): **the whole transition
  table above** (27 pairs; M8); `CONSENTED` only with a `party_id`;
  `DECLINED` and `CLOSED` only with a `LEAD_CLOSURE` reason, and no reason on
  any other status; a terminal lead's reason frozen and its links only
  NULLable (Q-B1).
- **in the service only:** the derivation of a status from an attempt's
  outcome, and the consent check under `FOR SHARE` (the trigger cannot lock
  another table's row for a later statement).
- **Not K06:** the trigger guards what a careless write can do through the
  application role; with the application role a superuser that owns every
  table, it is not a privilege boundary (G8-14).

**Q-A1 (decided, review of `b39ad10`): the existing test that writes
`DECLINED` by SQL without a reason** (`test_the_queue_lists_open_leads_oldest_first_and_omits_closed_ones`,
F8-15) supplies a valid `LEAD_CLOSURE` reason when `0009` is applied; the
guard stays as it is. Measured (M7): its statement is refused after the
draft, and accepted with `LEAD_DUPLICATE`. The trigger acts on UPDATE only:
the row already in the suite's database is not touched.

### 5A.2 Reason codes (inserted by `0009`)

None named `LEAD_*` exists in any database measured (M5).

| Code | Category | `label_ar` | `label_en` |
|---|---|---|---|
| `LEAD_NO_ANSWER` | `LEAD_CONTACT` | لم يُجب | No answer |
| `LEAD_REACHED` | `LEAD_CONTACT` | تم التواصل | Reached |
| `LEAD_WRONG_NUMBER` | `LEAD_CONTACT` | رقم خاطئ | Wrong number |
| `LEAD_NUMBER_NOT_IN_SERVICE` | `LEAD_CONTACT` | رقم خارج الخدمة | Number not in service |
| `LEAD_DECLINED_BY_PERSON` | `LEAD_CLOSURE` | رفض الشخص | Declined by the person |
| `LEAD_DUPLICATE` | `LEAD_CLOSURE` | مكرّر | Duplicate |
| `LEAD_NOT_RELEVANT` | `LEAD_CLOSURE` | خارج النطاق | Not relevant |
| `LEAD_STALE` | `LEAD_CLOSURE` | قديم | Stale |

**Q-A2 (decided, review of `b39ad10`):** accepted in principle;
`LEAD_NUMBER_NOT_IN_SERVICE` reads «رقم خارج الخدمة». **The final text, for
fixing:** the table above, as the draft of `0009` carries it.

### 5A.3 Migration `0009` — the draft, with its downgrade (revision 3)

**The text is the file** `docs/gate/drafts/0009_external_lead_workflow.DRAFT.py`:
`UPGRADE` and `DOWNGRADE` as statement lists, in `0008`'s form. Revision 2's
inline SQL is replaced by it. **Measured by executing those statements**
(M7 to M11, `evidence/SLICE8-PLAN-MEASUREMENTS-R3.txt`).

**What the draft settles, point by point:**

| Point | The draft | Measured |
|---|---|---|
| the transitions (G8-3) | **the whole table of §5A.1 in the trigger**, not a subset: 27 allowed pairs; a terminal status is never left | M8: of 90 ordered pairs, the 27 accepted, no other |
| `CONSENTED` | only with `party_id` | M9 |
| `DECLINED`, `CLOSED` (Q-A3) | a `close_reason_code` of category `LEAD_CLOSURE`; a reason on any other status refused | M9: a `MATCH` code refused; a reason on an open lead refused |
| **changing a closed row's reason** (Q-A3) | **refused:** a terminal lead's reason is frozen | M9 |
| the clock (reviews of `b39ad10`, `0a78e91`) | **`recorded_at` assigned by the server:** the BEFORE INSERT trigger sets `NEW.recorded_at := clock_timestamp()`, overwriting any value an INSERT supplies; then **`CHECK (occurred_at <= recorded_at)`, no margin**. The CHECK compares two columns; the trigger is what makes one of them the server's clock. The service refuses a future `occurred_at` with `422`. Not K06 (a superuser can disable a trigger) | M10: one second after the insert's clock refused; **M13:** `recorded_at` given as 2099 does not save a future `occurred_at`; given as 2000, it is replaced by the server's clock |
| Alembic (review of `0a78e91`) | `revision = "0009_external_lead_workflow"`, `down_revision = "0008_communication_records"`, as `0008` | **M12:** the only head, after `0008`; upgrade 0008 → 0009 by Alembic; downgrade refused with an attempt recorded, the database left at 0009; without data, downgrade to 0008 and upgrade again |
| the attempts' outcome | a `LEAD_CONTACT` code (trigger) | M10 |
| append-only | UPDATE and DELETE refused | M10 |
| audit (Q-A4) | `AFTER INSERT ... audit_row_change('attempt_id')`; the table has **no free-text column** | M10: one `audit_log` row per insert, the whole row |
| **a party's deletion** (F8-17) | **Q-B1**, below | M9a, M9 |
| existing rows | the guard acts on UPDATE only; a pre-check refuses the upgrade if a `LEAD_*` code exists | M7: the test's `DECLINED` row without a reason survives the upgrade unchanged |
| **downgrade** | **refused** while an attempt or a `LEAD_*` reason exists, naming the counts; otherwise drops the triggers, functions and table, then the eight codes. Nothing recorded is lost by a downgrade that runs | M11: refused twice with data; with none, run, then the upgrade again |

**Q-B1 · A party's deletion and the terminal freeze (F8-17): DECIDED (a)**
(review of `0a78e91`), with the wording restricted after M14:
- **a terminal lead's `party_id` may become NULL**, never another value: the
  frozen `ON DELETE SET NULL` keeps working (M9: a `DECLINED` lead's party
  deleted, the link NULL);
- **a NULL written by hand passes the guard too** (M9). Declared; **the
  service never writes it**, pinned by an inventory of its statements (§6.6);
- **a `CONVERTED` lead's links never become NULL** (M14): its target cannot
  (`ck_external_lead_converted_target`, frozen), its request cannot be
  deleted (`prevent_core_delete`), and its party cannot be deleted either
  (the request's `party_id` is `ON DELETE RESTRICT`);
- **deleting a party erases nothing captured** (M14): the lead's
  `raw_payload` and its source's `raw_text` stay. It is **not** an erasure of
  personal data, and proves nothing about a data-erasure request (OQ8-1).

**Tests of the draft's consequences** (§6.6).

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

**The texts, revision 3:** the Delta draft and its addendum draft under
`docs/gate/drafts/`; the effective contract they produce, generated by the
gate's own generators on a temporary worktree:
`SLICE8_EFFECTIVE_CONTRACT_EXPECTED.txt` (71 operations, 64 role-annotated;
no frozen operation's roles change).

**5. The REQUEST conversion payload: CORRECTION-009** (Q-A5, decided as a
CORRECTION), drafted in full in
`docs/gate/drafts/CORRECTION-009-lead-conversion-payload.DRAFT.md`:
`require: [target, payload]`, and, for `target = REQUEST`, the payload
closed to `RequestCreate` without the three fields the conversion sets.
PROPERTY is not narrowed: it stays a `409` by decision.

**Q-B3 · The overlay cannot carry the payload's schema (F8-18): DECIDED (a)**
(review of `0a78e91`). A separate, limited preparatory step adds
`add_all_of` to the corrections loader, the contract generator and their
tests, with one runtime validator reading the effective body; delivered in
`SLICE_8_PREP_ADD_ALL_OF_DELIVERY.md`. **It activates nothing:** CORRECTION-009
stays a draft, `0009` stays outside Alembic, no slice command is written.
CORRECTION-009's literal YAML and the generator's diff follow it.

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

**The payload schema:** CORRECTION-009 (draft).

**Q-A6 (decided): RENT is not refused at conversion.** A `RAW` RENT request
may be recorded, as `postRequests` already allows. What must be **proved**
(§6.7): a conversion activates no request, RENT or BUY (it stays `RAW`); it
runs no matching, writes no candidate, opportunity, task or thread; and a
later matching run on a RENT request stays refused with G4-5R's `422`. This
slice's evidence is SALE only.

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

### 5A.8 Queue paging (G8-4; F8-14, M6) — revised after the review of `b39ad10`

**The text is the Delta draft's §3.4:** the page's query, the cursor, the
three guarantees, and the table of what a walk does not guarantee. In brief:
- each page is **one statement, one snapshot**; no snapshot spans the pages;
- **a lead committed before the walk's first page, and open when its page
  is read, is returned once**; no lead twice in a walk;
- a lead committed during the walk with a key at or below the cursor (M6)
  is not returned by that walk; a lead that turns terminal before its page
  is not returned; one that moves between open statuses keeps its place;
- **a new walk reconsiders a lead only if it is still open** at its read;
- **revision 2's `walk_started_at` is withdrawn**: a value in a response
  is not a snapshot.

**Q-A7 (decided):** the paged operation is new, in the addendum; at
operational volume it is the one used. **The frozen unpaged operation does
not become safe because the new one exists** (Delta §3.5).

**Q-B2 · The frozen unpaged queue: DECIDED (b)** (review of `0a78e91`).
Its roles stay as they are: narrowing them to ADMIN would not make an
unpaged query safe at volume, since ADMIN could still run it. **The paged
operation is the approved operating path. The old operation's limit of use
(not at operational volume, G3-10 Q-8) is carried into the slice's closure
record and the operational setup** (§0.3, item 9).

**Q-A8 (decided): `discovered_at` stays `now()`.** Revision 2's proposal to
move it to `clock_timestamp()` is withdrawn: it would not order rows by
commit, and could change what the discovery time means.

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

**Revision 4's measurements** (`evidence/SLICE8-PLAN-MEASUREMENTS-R4.txt`),
twice, identical:

| # | Measurement | Result |
|---|---|---|
| M12 | the draft as an Alembic revision after `0008` | the only head; upgrade; downgrade refused with an attempt (database stays at 0009); without data, downgrade to 0008, upgrade again |
| M13 | an explicit `recorded_at` in an INSERT | overwritten by the server's clock: a future `occurred_at` refused even with `recorded_at` 2099 |
| M14 | a `CONVERTED` lead; a `DECLINED` lead's party deleted | the target cannot be NULLed, the request not deleted, the party not deleted; a `DECLINED` lead's party deleted, `raw_payload` and `raw_text` kept |

**Revision 3's measurements** (`evidence/SLICE8-PLAN-MEASUREMENTS-R3.txt`),
on the draft of `0009`, its own statements executed (re-run on the draft as
revised for revision 4: the same results, line for line):

| # | Measurement | Result |
|---|---|---|
| M9a | a party's deletion, frozen schema alone | accepted; the lead's `party_id` NULL |
| M7 | the draft on a database with a `DECLINED` lead without a reason | applied; the row unchanged; the queue test's statement refused, then accepted with a `LEAD_CLOSURE` reason |
| M8 | the 90 ordered pairs of statuses | 27 accepted, exactly the draft's table |
| M9 | each guard; a party's deletion under the draft and a strict variant | each refuses what it names; the draft lets the deletion through; the strict variant refuses it for a terminal lead (F8-17) |
| M10 | the attempts table | the clock rule, the outcome's category, append-only, one audit row per insert, no free-text column |
| M11 | the downgrade | refused with an attempt or a `LEAD_*` reason; with neither, run; the upgrade again |

### 6.6 Tests of `0009`'s consequences (when it is applied)
- the migration test comparing the applied text with the approved text,
  statement by statement, as `0008`'s;
- **through Alembic** (M12): upgrade from `0008`, downgrade refused with
  data, downgrade and upgrade without;
- **the clock** (M13): an explicit `recorded_at` overwritten; a future
  `occurred_at` refused whatever `recorded_at` is supplied;
- **a `CONVERTED` lead** (M14): its target never NULL, its request and its
  party never deleted;
- M8's whole matrix, as a test, against `TRANSITIONS`;
- each guard of M9 and M10, and a mutation of each killed;
- **Q-A1:** the queue test's `DECLINED` row written with
  `LEAD_DUPLICATE`, the guard unchanged;
- **Q-B1 (a):** deleting a party a terminal lead names: accepted, the link
  NULL; re-pointing it: refused; **no service path writes a NULL to a
  terminal lead** (an inventory of the statements, as G7-19 (ii));
- the downgrade refused with data, run without, the upgrade again;
- the "existing rows" check (M5) repeated on the database the migration
  targets, its counts recorded before applying.

### 6.7 RENT through the conversion (Q-A6)
- a RENT payload converts to a `RAW` request, `ASSISTED`/`UNCLAIMED`;
- in the same test, nothing else is written: no `match_runs`, no candidate,
  no opportunity, no task, no thread (rows of each table before and after);
- `postRequestsRequestIdMatchingRun` on it: `422` naming G4-5R, as today;
- the BUY case writes the same and nothing more.

### 6.8 Queue paging (Delta §3.4)
- a walk over committed open leads returns each once, in order, with
  `next_cursor` null at the end;
- **M6's case as a test:** a lead whose transaction began before the
  cursor's row and committed after the page: not in this walk; **in a new
  walk, if it is still open**;
- a lead closed between two pages: absent from the later page; a lead moved
  between open statuses: once, at its key;
- a malformed cursor: `422`; `limit` outside 1 to 200: `422`.

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
| 0 | the decisions G8-1 to G8-14; the texts of the Delta, CORRECTION-009 and `0009` | **revision 4 delivered for review**; Q-B1 to Q-B3 decided; the texts **not approved; step 1 not authorized** (review of `0a78e91`) |
| P | **the preparatory step (Q-B3):** `add_all_of` in the loader, the generator and their tests; a runtime validator of the effective body | **authorized, limited** (review of `0a78e91`); activates nothing |
| 0b | CORRECTION-009's literal YAML and the generator's diff; the correction, the Delta and the migration in final form | after P; then the review before step 1 |
| 1 | `0009` as approved; the attempts record and the status machine (service); tests | step 0 |
| 2 | the addendum's operations: contact attempts, status, Call Brief; tests | step 1 |
| 3 | REQUEST conversion (G8-5 (i)), lineage, claim after conversion; tests | step 2 |
| 4 | Direct Interest (G8-7); tests | step 0 (independent of 1 to 3) |
| 5 | mandatory tests end to end, closure evidence | 1 to 4 |

## 9. Document identity

This file's sha256 is recorded in `docs/gate/evidence/DOCUMENT-HASHES.txt`
at the commit that adds each revision.
