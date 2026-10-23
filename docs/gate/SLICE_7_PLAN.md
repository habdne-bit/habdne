# Slice 7 — Communication / WhatsApp Record
## Implementation plan — **revision 1**

**Status: submitted for review.**
- **No code for this slice exists, and none is written before this plan is
  approved.** The review of `8de5f7f` authorized **preparing this plan
  only**: "هذا إذن بالتخطيط، وليس اعتمادًا للقرارات أو إذنًا بكتابة
  الشيفرة". (Translated from the Arabic: "This is permission to plan, not
  approval of the decisions nor permission to write code".)
- **Approved by no one yet:** every decision of §5, the proposed parts of
  migration `0008`, and the measurements of §6.5.

**What this revision does not decide.** Every choice that is not already
fixed by a source is put to the reviewer as a decision (§5), with options and
a recommendation. A recommendation is not a decision.

**What it rests on:**
- **Each finding of §4** rests on reading the frozen sources and the code.
- **Nothing was run against PostgreSQL** for this revision. The
  measurements that would confirm the findings are proposed in §6.5, as
  Slice 6's step 0 was.
- **One external fact is NOT verified against its official source:** the
  signature format of WhatsApp Cloud API webhooks (§5, G7-2). It is stated
  as community-sourced. It is to be verified against Meta's developer
  documentation before any code relies on it.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | the commit that adds this revision | first plan (authorized as planning only in the review of `8de5f7f`) |

---

## 0. What this slice is, and what it is not

### 0.1 The scope, as the approved slices document states it

`docs/handoff/06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md`, "Slice 7 —
Communication / WhatsApp Record":

> **Objective:** Centralize operational communication history without
> building a full proprietary chat platform.
>
> **Deliverables:**
> - communication threads and messages.
> - interaction timeline.
> - official WhatsApp Business integration boundary.
> - provider event replay store.
> - delivery/read status.
> - staff notes and important confirmation linkage.
>
> **Mandatory tests:**
> - repeated provider webhook creates one message.
> - same provider message id cannot be inserted into another thread.
> - thread/opportunity links are checked by service invariant.
> - phone decision can be linked to later written confirmation observation.

The same scope is restated, in agreement, in three places:
- Developer Handoff Master v1.0.3 §8 ("Official WhatsApp Business integration
  boundary … provider message id + replay protection … the ability to link a
  phone decision to a later written confirmation");
- the Developer Reference Spec §18;
- `API_CONTRACTS_v0.2.md` §4.12.

### 0.2 What it is not

- **Not a chat platform** (the objective, and the Spec's §2 table: "Native
  chat between users — deferred").
- **No AI.** Slice 9 is the AI slice.
- **No customer access.** The contract gives no customer role on any
  communication operation (§1).
- **No change to matching, review, opportunities or tasks.** Slice 7 adds
  links to them, not behaviour.
- **No RENT** (G4-5R open). An opportunity a thread may name is a SALE
  opportunity: only the approved path creates opportunities, and it is SALE
  only.
- **No legal-evidence claim.** `API_CONTRACTS` §4.12 states that phone
  decisions are stored "as operational records rather than claiming
  guaranteed legal evidentiary status", and the Spec's §18 says the same.

### 0.3 Carried from Slice 6, unchanged (`SLICE_6_CLOSURE.md` §1)

Slice 6 is CLOSED at `ce8cfa0`, SALE only, not a release authorization. Its
limits travel with this slice as they were given:

| Limit | Its bearing on Slice 7 |
|---|---|
| **K06 UNPROVEN** (G6-12; EN-02): the application role is a superuser that owns every table. **Its remedy is an independent condition before any release gate.** | Every append-only or immutability guard Slice 7 proposes (§5, G7-12) can be proven **at trigger level only**, and is labelled so. K06 is not claimed. |
| **G4-5R open:** SALE only | Threads naming an opportunity are tested on SALE opportunities. No RENT path is claimed |
| **OQ6-1 and OQ6-2 open** | Untouched. G7-10 cites observations, but no Slice 7 path writes `task_completion_events`, and no index is proposed for OQ6-2 |
| **The replay (R)/(D) does not verify the diagnostic's own `input_hash`; `explain.blocker_summary` is not pinned** | Untouched: Slice 7 changes no matching or diagnostic code. Restated in Slice 7's closure evidence as carried, not as proven |
| **The stored-titles inspection** (F6-22): a persistent database is inspected before old titles are considered handled | Untouched, and carried as an operational condition |
| **F6-21:** R9.3's rule binds what a slice generates; the staff match keeps `seller_expectation_dzd` (Slice 4 §3.5) | Slice 7 copies no snapshot into a thread, message or interaction (§3.8) |
| **Relations are never an authorization source** (Slice 6 condition 7; RFC-001 R4.5, R4.12) | The thread-link invariant (G7-6) may read relations as **consistency** evidence. It never reads them as authority |
| **Environment notes EN-01 to EN-03** | They apply to every run of this slice |
| **STOP GATE E is the record of Slice 5's tree** | Its generator lists `opportunity_commands.py` as the one writer of `interactions`. A Slice 7 writer would change that (F7-7, G7-8) |

---

## 1. Operations

Every Slice 7 operation in the effective contract
(`docs/api/openapi_effective_v0.2.3.yaml`, tag `Communication`; inventory
`docs/api/API_INVENTORY_GENERATED.md`):

| operationId | Method, path | Roles | Idempotency | Today | Slice 7 |
|---|---|---|---|---|---|
| `postCommunicationThreads` | POST `/communication/threads` | ADMIN, OPERATOR | `Idempotency-Key` | **no route** | **7** |
| `postCommunicationThreadsThreadIdMessages` | POST `/communication/threads/{thread_id}/messages` | ADMIN, OPERATOR | `Idempotency-Key` | **no route** | **7** |
| `postWebhooksWhatsapp` | POST `/webhooks/whatsapp` | **none: unauthenticated**, one of the closed list of six (RFC-001 R10.4) | none: provider event identity (`API_CONTRACTS` §2.3) | **no route** | **7** |
| `getPartiesPartyIdTimeline` | GET `/parties/{party_id}/timeline` | ADMIN, OPERATOR, REVIEWER | — | routed (Slice 1, `services/timeline.py`); reads `interactions` only | **read, perhaps widened by G7-8** |

**The bodies:**
- **`CommunicationThreadCreate`** requires `channel`. `party_id`,
  `request_id`, `property_id` and `opportunity_id` are optional and
  nullable; `external_thread_ref` is optional. `additionalProperties:
  false`. Its 201 is `{thread_id, opened_at}`.
- **`MessageCreate`** requires `direction` (INBOUND, OUTBOUND, INTERNAL) and
  `occurred_at`. It also carries `external_message_ref`, `message_type`
  (default TEXT), `body_text`, `media_ref`, `delivery_status` (QUEUED, SENT,
  DELIVERED, READ, FAILED, UNKNOWN) and `metadata`. **It has no `provider`
  field.** `additionalProperties: false`. Its 201 is `{message_id,
  delivery_status}`.
- **`WhatsAppWebhookEnvelope`** requires `provider_event_id`, `event_type`
  and `payload`. It is `additionalProperties: true`, with `security: []`.
  Its responses are 200, 400 and 401.

**No read operation exists for threads or messages** (F7-3).

---

## 2. What the schema and the earlier slices already give, and what they leave open

**Tables** (`schema_v0.2.3.sql` §12; migrations `0001`–`0007` add nothing
to them):

| Table | Given | Left open |
|---|---|---|
| `communication_threads` | the channel; the nullable links `party_id`, `request_id`, `property_id`, `opportunity_id` (all `ON DELETE SET NULL`); `external_thread_ref`, `opened_at`, `last_message_at`, `archived_at`, `created_by_account_id` | **no check of the links' mutual consistency** (by design, §3.4); no guard on UPDATE or DELETE; no audit trigger |
| `communication_messages` | `thread_id` (`ON DELETE RESTRICT`), `provider`, `external_message_ref`, `direction`, `message_type`, `body_text`, `media_ref`, `delivery_status` (default UNKNOWN), `occurred_at`, `sent_by_account_id`, `metadata`; **`UNIQUE(provider, external_message_ref)`** | the uniqueness does not hold when `provider` is NULL (F7-1); no guard on UPDATE or DELETE; no audit trigger |
| `webhook_events` | `provider`, `provider_event_id`, `event_type`, `payload`, `processing_status` (RECEIVED, PROCESSED, IGNORED, FAILED), `received_at`, `processed_at`, `error_text`; **`UNIQUE(provider, provider_event_id)`**; commented "Provider event replay protection and processing audit" | no guard on UPDATE or DELETE |
| `interactions` | the type (CALL, WHATSAPP, SMS, EMAIL, IN_PERSON, INFO_REQUEST, VISIT, NEGOTIATION, STATUS_CHANGE, NOTE, OTHER), the channel, the links including `thread_id` (`ON DELETE SET NULL`), `summary`, `outcome_code`, `occurred_at`, `operator_account_id`, `metadata` | one writer today, `opportunity_commands.py` (Slice 5, G5-8 (i)); no audit trigger |
| `resource_consent_bindings` with `thread_id` | `trg_consent_binding` refuses a binding whose grant's party is not the thread's party (`Communication thread consent party mismatch`) | F7-8 |
| `observations` | `kind` includes MESSAGE and CALL_NOTE; `party_id`, `observed_at`, `raw_text`, `payload` | **no column links an observation to a message, interaction or thread** (F7-11) |

**What the earlier slices give:**
- **Slice 1:**
  - the timeline service (`services/timeline.py`): an allow-list of
    `interactions` columns, with `metadata` excluded;
  - the idempotency records;
  - the policy table, with `postWebhooksWhatsapp` in `PUBLIC_OPERATIONS`
    (`auth/policy.py`).
- **Slice 3:**
  - the consent service, which knows the resource type
    `COMMUNICATION_THREAD` and the scope `COMMUNICATION_ARCHIVE`
    (`services/consent.py`);
  - `POST /observations`.
- **The customer ownership loader:** `load_thread` (`auth/loaders.py`), for
  RFC-001's `COMMUNICATION_THREAD` ownership. No contract operation uses it
  yet.
- **Slices 5 and 6:** the service-level audit `audit_rows`, which already
  covers `interactions` with `summary` withheld, and `observations`.

---

## 3. Rules that follow from the sources without a decision

### 3.1 A webhook event is stored and deduplicated before anything is resolved
- **The sources:**
  - `API_CONTRACTS` §4.12: "Provider event is first written to
    `webhook_events` and deduplicated by `(provider, provider_event_id)`.
    Only then is thread/message resolution performed. Replayed webhooks must
    not duplicate a message or interaction";
  - ADR-09; the contract's description of `postWebhooksWhatsapp`.
- **Consequence:** a replay answers 200 and writes no message and no
  interaction (S42; J01; mandatory test 1).

### 3.2 Unauthenticated, but verified
- **The sources:**
  - RFC-001 R10.5: the webhook "requires provider signature verification
    and `(provider, provider_event_id)` deduplication … outside domain
    tables";
  - `API_CONTRACTS` §8: "Secrets/provider webhook verification outside
    domain tables";
  - S41: an invalid signature is "rejected before domain resolution".
- **Consequence:** the secret lives in the environment, not in the
  database.

### 3.3 A provider message identity is global
- **The sources:**
  - mandatory test 2;
  - J02: "Same provider external message id cannot be inserted under a
    second thread";
  - the schema's `UNIQUE(provider, external_message_ref)`.
- **Consequence:** the identity is the pair, across all threads (F7-1 for
  the NULL case).

### 3.4 Link consistency is a service invariant, not a trigger
- **The source:** the Remediation Review v0.2, "Communication context
  consistency": "Some thread links can be contextually legitimate even when
  the primary PARTY is not the request owner (e.g. seller conversation about
  buyer opportunity). Therefore this is primarily a service invariant, not
  an over-restrictive DB trigger."
- **Consequence:**
  - mandatory test 3 is proven on the service;
  - **no trigger on the links is proposed** (G7-6 decides the rule;
    G7-12 (D) only freezes the links after creation).

### 3.5 A phone decision is an operational record
- **The sources:** `API_CONTRACTS` §4.12 and the Spec's §18. Critical phone
  decisions "SHOULD" be confirmed in writing "where practical". The
  platform stores them "as operational records".
- **Consequence:** linking them (mandatory test 4) claims no legal value.

### 3.6 Not a chat platform
- No inbox, no unread counters, no real-time delivery.
- What is built is a record that can be retrieved.

### 3.7 Staff commands are idempotent; the webhook is deduplicated by event
- **The source:** `API_CONTRACTS` §2.3.
- **Consequence:**
  - the two staff POSTs replay the first response for the same key and
    payload, and answer 409 for the same key with another payload (K05);
  - the webhook does not use the header.

### 3.8 What never enters a communication record
- R9.2 and R9.3: `seller_expectation_dzd`, private claims, staff notes and
  provenance internals are never serialized to a public or customer DTO.
- Slice 7 adds no customer DTO. It copies no match, offer or permission
  snapshot into a thread, message, interaction or webhook row (F6-21's
  boundary).

---

## 4. Findings from reading (not measured, not fixed)

Each finding cites its source. §6.5 proposes the measurement that would
confirm each one on PostgreSQL 16.

- **F7-1 · A NULL `provider` escapes the global identity.**
  - **The PostgreSQL rule:** a UNIQUE constraint treats NULLs as distinct
    unless declared `NULLS NOT DISTINCT` (PostgreSQL 16 documentation,
    §5.4.3 "Unique Constraints").
  - **The contract gap:** `MessageCreate` has no `provider` field. So a
    staff-archived message with an `external_message_ref` would carry a
    NULL provider, unless the service sets one.
  - **The consequence:** the same reference could then be stored twice, in
    two threads, contrary to J02.
- **F7-2 · Nothing guards the communication rows.**
  - No trigger refuses an UPDATE or DELETE of `communication_messages`,
    `webhook_events` or a thread's links.
  - None of the four tables has an audit trigger. The schema's
    `audit_row_change` triggers cover eight other tables: `requests`,
    `properties`, `property_offers`, `consent_grants`, `claims`,
    `resolved_values`, `match_reviews`, `opportunities`.
- **F7-3 · Archived content has no read operation.** The contract has no GET
  for a thread or a message. The only Communication read is the party
  timeline, which reads `interactions` alone (`services/timeline.py`). So a
  message's content is visible through the API only if something carries it
  into the timeline (G7-8).
- **F7-4 · The contract has no webhook verification handshake.** It declares
  only `POST /webhooks/whatsapp`. Registering a webhook with Meta's Cloud API
  is described (community sources, not verified against Meta's
  documentation) as needing a GET answering a `hub.challenge`. That GET would
  be a contract addition, outside this slice (G7-1).
- **F7-5 · The envelope is TURAB's, not the provider's.**
  `WhatsAppWebhookEnvelope` requires a top-level `provider_event_id`,
  `event_type` and `payload`. Meta's Cloud API posts its own shape
  (`object`, `entry[].changes[]`; community sources, not verified). So
  either a relay adapts Meta's events to the envelope, or the contract does
  not match the provider. Who produces the envelope is a boundary decision
  (G7-2).
- **F7-6 · J03's retention rules are not defined in any source.**
  - J03 asks that archive behaviour respect "consent policy and retention
    rules defined for pilot/legal review". No document of the frozen pack
    defines those rules.
  - `webhook_events.payload` is `NOT NULL` and stores the event as received,
    content included.
  - **J03 can be proven for consent only** (G7-9); retention stays an open
    question (OQ7-1).
- **F7-7 · STOP GATE E's writer check names one writer of `interactions`.**
  `db/gate/stop_gate_e_evidence.py` lists
  `src/turab/services/opportunity_commands.py` as the approved writer of
  `interactions` (G5-8 (i)). A Slice 7 writer would make that generator
  report an unapproved writer, beside the stale document it already reports.
- **F7-8 · A thread without a party cannot carry an archive consent.**
  `trg_consent_binding` compares the thread's `party_id` with the grant's
  party (`IS DISTINCT FROM`). A thread whose `party_id` is NULL therefore
  refuses every binding.
- **F7-9 · `archived_at` has no command.** No contract operation archives a
  thread, so `archived_at` stays NULL under this contract.
- **F7-10 · Delivery status has one source after creation.** No staff
  command updates a message. After `MessageCreate`, its `delivery_status`
  can change only through the webhook (G7-5).
- **F7-11 · Nothing links an observation to a message.** Mandatory test 4
  needs a link between a phone decision and a later written confirmation
  observation. No column holds it, so the link must be a record of its own
  (G7-10).

---

## 5. Decisions needed — none is taken by this plan

### G7-1 · Scope
- **Recommended:**
  - the three operations of §1, and the timeline as G7-8 decides;
  - migration `0008` as G7-12 decides;
  - no outbound sending to a provider (G7-14);
  - no webhook verification GET (F7-4: a contract addition, put to the
    contract's owner, not built here);
  - no customer operation.
- **Blocks:** everything.

### G7-2 · The webhook boundary
- **(i) Verification, before any write (S41, R10.5):**
  - an HMAC-SHA256 of the **raw** request body with a secret read from the
    environment, compared in constant time with the `X-Hub-Signature-256`
    header (`sha256=<hex>`);
  - a missing or wrong signature is 401, and writes nothing, not even
    `webhook_events`;
  - a missing secret fails closed (500, typed).
  - **The format is to be verified against Meta's official documentation
    before step 3** (§0, the unverified fact).
- **(ii) Who produces the envelope (F7-5):**
  - **(a) recommended:** a relay outside TURAB, which adapts the provider's
    events to `WhatsAppWebhookEnvelope` and signs the envelope. The contract
    stays as frozen;
  - **(b):** TURAB accepts Meta's native shape. This contradicts the frozen
    schema's required fields, so it is a contract change.
- **(iii) The provider** is the constant `whatsapp` for this route.
- **(iv) Two transactions:**
  1. the event row is inserted alone and committed. A conflict on
     `(provider, provider_event_id)` answers 200 and does nothing else;
  2. resolution and its writes run in a second transaction, which ends by
     setting `processing_status` (PROCESSED, IGNORED, or FAILED with
     `error_text`) and `processed_at`.
- **(v) A replay of any recorded event,** FAILED included, answers 200 and is
  **not** reprocessed. Reprocessing a FAILED event is left to a later
  operational command (not in the contract).
- **Blocks:** step 3.

### G7-3 · Event types and thread resolution
- **(a) Recommended. The envelope's `payload` is given a documented
  internal shape.** The contract leaves it `additionalProperties: true`, and
  the envelope is TURAB's (G7-2 (ii)). Two `event_type`s are handled:
  - **`message`:** `external_message_ref`, `thread_ref`, `occurred_at`,
    `message_type`, and optional `body_text` and `media_ref`. It is stored as
    an INBOUND message in the WHATSAPP thread whose `external_thread_ref`
    equals `thread_ref`;
  - **`status`:** `external_message_ref`, `status` and `occurred_at`. It
    updates that message's `delivery_status` (G7-5).
- **Anything else is IGNORED:** an unknown type, an unknown thread, or an
  unknown message for a status.
- **No thread, party or identity is created from a webhook.** Identity is
  Slice 3's human-reviewed process.
- **(b)** Create a thread, without a party, for an unknown `thread_ref`. Not
  recommended: it creates records nobody reviewed, and such a thread cannot
  carry an archive consent (F7-8).
- **Blocks:** step 3.

### G7-4 · The global message identity (mandatory test 2, J02, F7-1)
- **(a) Recommended. The service sets the provider, and the database backs
  it.**
  - The service sets `provider` whenever `external_message_ref` is given: the
    constant of the thread's channel, `whatsapp` for WHATSAPP. It refuses an
    `external_message_ref` on an INTERNAL message (422).
  - `0008` part A adds `CHECK (external_message_ref IS NULL OR provider IS
    NOT NULL)`.
  - The same pair in another thread is refused by the existing UNIQUE
    constraint. The service maps that, by its constraint name, to a typed
    409.
- **(b)** `NULLS NOT DISTINCT` on the constraint. Not recommended: it would
  also make two messages with neither provider nor reference collide.
- **Blocks:** steps 1–3.

### G7-5 · Delivery and read status
- **(a) Recommended.**
  - **The order:** QUEUED < SENT < DELIVERED < READ.
  - **Moves:**
    - a status event moves a message forward only;
    - an older status arriving late is recorded (`webhook_events`) and
      IGNORED;
    - FAILED is accepted from QUEUED or SENT, and is final.
  - **UNKNOWN** is the initial state when none is known; any status
    replaces it.
  - **The only path** that changes a message after its creation is the
    webhook (F7-10).
- **(b)** Store the last status received, whatever its order. Not
  recommended: providers may deliver statuses out of order, and READ must not
  be overwritten by DELIVERED.
- **Blocks:** step 3, and `0008` part B.

### G7-6 · The thread/opportunity link invariant (mandatory test 3)
- **Checked at creation;** the links are frozen afterwards (`0008` part D).
- **(a) Recommended rules:**
  1. if `opportunity_id` is given:
     - `request_id`, when given, equals the opportunity's request;
     - `property_id`, when given, equals the opportunity's property;
     - `party_id` is the opportunity's buyer (the request's party) or its
       seller (the party of its current offer). The Remediation Review's
       example, "seller conversation about buyer opportunity", is the
       reason;
  2. if `request_id` is given without an opportunity, `party_id` is the
     request's party;
  3. if `property_id` is given without an opportunity, `party_id` is the
     party of one of the property's offers. A current property relation is
     **not** accepted as the reason (§0.3: relations are not authority, and
     here they would decide a link);
  4. every id names an existing row. Otherwise the answer is a typed 404 or
     422, writing nothing.
- **(b)** Rules 1–2 only, with any party for a property. Weaker, and it
  leaves seller threads unchecked.
- **(c)** A trigger. Contrary to §3.4.
- **Blocks:** step 2.

### G7-7 · Must a thread name its party?
- **The tension:** the contract makes `party_id` optional. `API_CONTRACTS`
  §4.12 says a thread is "linked to the relevant PARTY". And F7-8: without a
  party, no archive consent can be bound.
- **(a) Recommended:** a staff-created thread requires `party_id`. This
  narrows the contract, so it is a correction, CORRECTION-006, written as
  CORRECTION-005 was.
- **(b)** Keep it optional. Such a thread then never archives content
  (G7-9).
- **Blocks:** step 2.

### G7-8 · Messages in the interaction timeline (F7-3, F7-7)
- **(a) Recommended. Each message writes one `interactions` row, in the same
  transaction:**
  - the type by channel and direction: WHATSAPP for a WHATSAPP thread, CALL
    for PHONE, and so on; NOTE for INTERNAL;
  - its `thread_id`, and the thread's links;
  - **a fixed `summary`, never the body;**
  - the webhook's replay writes neither the message nor the interaction
    (§3.1).
  - **The cost:**
    - a second writer of `interactions`, a change to G5-8 (i)'s single
      writer, which requires this decision;
    - STOP GATE E's generator would report it. **Recommended:** STOP GATE E
      stays the record of Slice 5's tree, as STOP GATE D stays Slice 4's
      (`SLICE_5_CLOSURE.md`), and Slice 7's closure evidence inventories the
      writers of `interactions` by kind.
- **(b)** The timeline unions messages and interactions. This changes Slice
  1's timeline service and its allow-list.
- **(c)** No timeline entry. The archived content then has no read path
  (F7-3).
- **Blocks:** step 4.

### G7-9 · Content and consent (J03, F7-6)
- **(a) Recommended:**
  - `body_text` and `media_ref` are stored **only** when the thread's party
    has an ACTIVE `COMMUNICATION_ARCHIVE` grant bound to the thread;
  - otherwise the message is stored without content: direction, times,
    status and references, with `metadata.content_archived = false`;
  - this holds for staff messages and for webhook messages alike.
- **(b)** Store content always, as an operational record; consent governs
  only sharing.
- **Either way, OQ7-1 stays open:** `webhook_events.payload` keeps the event
  as received, and no retention rule is defined in the sources.
- **Blocks:** steps 2–3.

### G7-10 · Linking a phone decision to a later written confirmation (mandatory test 4, F7-11)
- **(a) Recommended. The link is a record of its own, append-only:**
  1. the phone decision is an INTERNAL message, `message_type`
     `PHONE_DECISION`, in a PHONE thread of the party;
  2. the written confirmation is an observation of kind MESSAGE, made by
     `POST /observations` (Slice 3), or from an inbound message;
  3. the link is a later INTERNAL message, `message_type`
     `CONFIRMATION_LINK`, whose metadata names `decision_message_id` and
     `observation_id`. The service checks four things:
     - both exist;
     - the decision is in the same thread;
     - the observation is of the thread's party;
     - its `observed_at` is not before the decision's `occurred_at`.
  - Nothing earlier is updated. The link claims no legal value (§3.5).
- **(b)** The observation's `payload` names the decision. This changes Slice
  3's `POST /observations` to validate a reference into Slice 7's tables.
- **(c)** Update the decision's metadata. Not recommended: it mutates a
  message (G7-12 (B)).
- **Blocks:** step 4.

### G7-11 · Audit
- **Recommended:**
  - `audit_rows` for threads, messages and interactions, with `body_text`
    withheld, as `interactions.summary` is;
  - `webhook_events` is its own processing record (the schema's comment) and
    is not audited twice;
  - an invalid signature is logged without the payload (`API_CONTRACTS` §8:
    no sensitive payloads in logs).
- **Blocks:** steps 2–4.

### G7-12 · Migration `0008` (parts proposed; the text in revision 2, after §6.5)
- **(A)** `CHECK (external_message_ref IS NULL OR provider IS NOT NULL)`
  on `communication_messages` (G7-4).
- **(B)** Messages are append-only, except `delivery_status`, which moves
  forward only (G7-5). DELETE is refused.
- **(C)** A `webhook_events` row is immutable, except its processing
  fields, set once from RECEIVED. DELETE is refused.
- **(D)** A thread's links (`party_id`, `request_id`, `property_id`,
  `opportunity_id`, `channel`) are immutable after INSERT (G7-6).
  `last_message_at` may move forward. Their `ON DELETE SET NULL` stays as
  frozen.
- **Labelled as trigger level:** each guard is proven at trigger level, not
  as K06 (G7-13).
- **Blocks:** step 1.

### G7-13 · K06 (not blocking this plan)
- **Carried unchanged.** K06 is UNPROVEN, and its remedy is an independent
  condition before any release gate.
- Nothing in Slice 7 claims K06. G7-12's guards are trigger-level.

### G7-14 · Outbound sending
- **(a) Recommended. Archive only.**
  - An OUTBOUND message records what was sent through the official channel,
    with its `external_message_ref` when known, and its status from then on
    by webhook;
  - TURAB calls no provider API in this slice: no network, no provider
    credentials.
- **(b)** Send through the provider's API. This needs credentials and a
  network boundary that no source specifies.

### Open questions (not decisions)

- **OQ7-1 · Retention** of message content and of `webhook_events.payload`
  (J03, F7-6). The sources leave it to "pilot/legal review". Nothing is built
  for it, and J03 is claimed for consent only.
- **OQ7-2 · The verification GET** (F7-4): a contract addition, for the
  contract's owner.

---

## 6. Tests and closure evidence

### 6.1 The four mandatory tests

| # | Test, as written | Proof planned |
|---|---|---|
| 1 | "repeated provider webhook creates one message" | the same signed envelope posted twice, and concurrently: one `webhook_events` row, one message, one interaction (G7-8); the second answer 200 |
| 2 | "same provider message id cannot be inserted into another thread" | the same `(whatsapp, ref)`, over HTTP and by webhook, into a second thread: typed 409 or IGNORED, no row. The NULL-provider path (F7-1) is refused by the service, and by `0008` (A) at trigger level |
| 3 | "thread/opportunity links are checked by service invariant" | each rule of G7-6 with an inconsistent link refused, writing nothing; the seller's thread about the buyer's opportunity accepted; the links frozen afterwards |
| 4 | "phone decision can be linked to later written confirmation observation" | G7-10 end to end over HTTP: decision, observation, link; each of the four checks refused when broken; nothing earlier updated |

### 6.2 Red-team and RFC-001 cases

| Case | Planned |
|---|---|
| **J01** | mandatory test 1 |
| **J02** | mandatory test 2 |
| **J03** | for consent only (G7-9): content stored with an active archive binding; none without, or after revocation. **Retention not claimed (OQ7-1)** |
| **S41** | a wrong or missing signature is 401 before any write |
| **S42** | a replay is 200, with no duplicate |
| **K05** | each staff POST replays with its key; another body on the key is 409 |
| **K06** | not claimed; trigger-level guards listed as trigger level |

### 6.3 Authorization
- **The two staff POSTs:** ADMIN and OPERATOR allowed; REVIEWER and CUSTOMER
  refused (403) and recorded; anonymous refused (401).
- **The webhook:** stays in the closed list of six (R10.4).
- **The matrix** (`authorization_evidence.py`) gains the three operations.

### 6.4 Closure evidence (no STOP GATE)

As Slice 6's:
- a generated `SLICE_7_EVIDENCE.md` with `--check`, bound to a clean-tree
  run;
- the mandatory and red-team mapping;
- the writes to `communication_threads`, `communication_messages`,
  `webhook_events` and `interactions`, inventoried **by kind** (INSERT,
  UPDATE, DELETE), refusing a write not decided;
- Slice 6's carried limits restated (§0.3), none as proven.

### 6.5 Measurements proposed for revision 2 (PostgreSQL 16; no code; NOT authorized yet)

| # | Measures | Confirms |
|---|---|---|
| M1 | two messages with NULL provider and the same reference, in two threads: accepted | F7-1 |
| M2 | the same `(provider, ref)` in a second thread: 23505, and the constraint's name | G7-4 |
| M3 | UPDATE and DELETE of a message, of a webhook event and of a thread's links, as the application role: accepted | F7-2 |
| M4 | two concurrent inserts of one `(provider, provider_event_id)`: one waits, then conflicts; `pg_blocking_pids` witness | G7-2 (iv) |
| M5 | a consent binding to a thread with NULL party: refused, with its message | F7-8 |
| M6 | `stop_gate_e_evidence.py --check` with a second `interactions` writer in a copy of the tree | F7-7 |
| M7 | the size of `webhook_events.payload` for a representative envelope, and the body limit the app enforces today | G7-2 |

---

## 7. Acceptance conditions

1. **The contract is unchanged,** apart from CORRECTION-006 if G7-7 (a) is
   decided, written and approved as CORRECTION-005 was.
2. **A replayed webhook writes no second message or interaction**
   (J01, S42).
3. **A provider message identity is global** (J02), the NULL case included.
4. **An unverified webhook writes nothing** (S41, R10.5); no secret in a
   domain table.
5. **Thread links are consistent at creation, and frozen** (G7-6).
6. **A phone decision's confirmation link is append-only,** and claims no
   legal value.
7. **Content is archived only under consent** (G7-9). Retention is not
   claimed (OQ7-1).
8. **No snapshot, expectation or private value** enters a communication
   record (§3.8).
9. **The writes to the four tables are exactly those decided,** by kind.
10. **SALE only** (G4-5R open). **K06 UNPROVEN.** **No AI.**

---

## 8. Sequence

| Step | Content | Depends on |
|---|---|---|
| 0 | the measurements of §6.5, folded into revision 2; no code | authorization of the measurements |
| 1 | migration `0008`, as G7-12 decides; tests, mutations | G7-4, G7-5, G7-6, G7-12 |
| 2 | `postCommunicationThreads` and the link invariant; `postCommunicationThreadsThreadIdMessages` (staff), the identity and consent rules; CORRECTION-006 if decided | G7-4, G7-6, G7-7, G7-9, G7-11 |
| 3 | `postWebhooksWhatsapp`: verification, the event store, resolution, statuses | G7-2, G7-3, G7-5, G7-9; the signature format verified against Meta's documentation |
| 4 | the timeline (G7-8) and the confirmation link (G7-10) | G7-8, G7-10 |
| 5 | the mandatory and red-team tests end to end, mutations, the closure evidence | all |

Each step is delivered with its tests and its mutation record, and is
reviewed before the next begins. A defect found in a step is measured before
it is fixed.

---

## 9. Document identity

This file's sha256 is recorded in `docs/gate/evidence/DOCUMENT-HASHES.txt`
at the commit that adds it.
