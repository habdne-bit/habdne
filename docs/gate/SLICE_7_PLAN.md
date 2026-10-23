# Slice 7 — Communication / WhatsApp Record
## Implementation plan — **revision 2**

**Status: submitted for review.**
- **No code for this slice exists, and none is written before this plan is
  approved.** Slice 7 is in **planning only**.
- **What the review of `dcebe46` did:**
  - accepted revision 1 as a basis for review and measurement;
  - authorized step 0's measurements (M1–M8), which are delivered here;
  - asked for five gaps to be settled in the plan's text before it is put
    up for approval (recorded below).
- **Approved by no one yet:** the decisions G7-1 to G7-15, and the text of
  migration `0008`.

**What this revision does not decide.** Every choice that is not already
fixed by a source is put to the reviewer as a decision (§5), with options and
a recommendation. A recommendation is not a decision.

**What it rests on:**
- **The sources** (§0.1, §3).
- **Step 0's measurements** on PostgreSQL 16.15:
  `evidence/SLICE7-PLAN-MEASUREMENTS.txt`, with its script beside it, run
  twice with identical results.
- **Three facts about Meta's webhooks,** as the review of `dcebe46` cites
  Meta's official documentation (§3.9). **This environment could not fetch
  that page** (DNS: `ENOTFOUND developers.facebook.com`). The facts are
  therefore stated as the reviewer's citation of the official source, not as
  our own reading of it.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | `91762f6` | first plan (authorized as planning only in the review of `8de5f7f`) |
| 2 | `7200b3c` | the review of `dcebe46` recorded; step 0 measured (M1–M8); the five gaps settled in the text: content and consent (G7-9), the stuck event and its recovery (G7-2 (v)), Meta and the relay (G7-2 (ii), §3.9), what staff can read (G7-8), the SALE boundary (§0.2, G7-6 rule 0); new: F7-12, G7-15; G7-12 (D) rewritten on M8 |

**The review of `dcebe46`. The plan is accepted as a basis for review and
measurement; G7-1 to G7-14 and the text of `0008` are not yet approved.**
- **Step 0 authorized,** in four terms:
  - M1–M7, on a temporary database, with rolled-back transactions where
    needed, and no implementation code;
  - M7's envelope is named a **synthetic sample** until G7-2 decides who
    produces it;
  - **M8 added:** what happens to `ON DELETE SET NULL` if `0008`'s proposed
    guard forbids changing a thread's links, since "the two statements in
    the plan may not both hold".
- **Required before revision 2 is put up for approval:**
  1. **Content and consent.** G7-9 drops `body_text` and `media_ref` without
     archive consent, but G7-2 stores `webhook_events.payload` before
     processing, and the payload may carry the same text or media. State
     what the payload and `metadata` keep, and how the consent condition
     actually holds. "Deferring retention to OQ7-1 is not enough if the
     payload stores the content in the first place."
  2. **The stuck event.** A RECEIVED event may stop before the second
     transaction. A replay of any recorded event, FAILED included, answers
     200 without reprocessing, and there is no recovery command. Settle the
     fate of RECEIVED and FAILED, and their recovery, before G7-2 is
     approved.
  3. **Meta and the relay.** The reviewer cites Meta's official
     documentation:
     - a GET carrying `hub.challenge` and `hub.verify_token`;
     - notifications signed in `X-Hub-Signature-256`;
     - a native payload of `object` and `entry[].changes[]`.

     If the relay is chosen, define who verifies Meta's signature before the
     transformation, who signs TURAB's envelope after it, and where the GET
     lives. The transformed envelope's signature proves the relay's origin,
     by its key. "It may not be described as a direct verification of Meta's
     signature on the transformed envelope."
  4. **Readability of the archive.** The plan says a message's content has
     no read operation, then proposes a timeline entry with a fixed summary
     and no body. State what "retrievable" means within the slice, and what
     a staff member can actually read, "without silently widening the
     contract".
  5. **The SALE boundary.** Bound the statement that every linkable
     opportunity "is SALE" to what the approved path creates, as Slice 5's
     record does, or make the opportunity's type an explicit check in the
     thread service. "We do not infer that a directly inserted row is
     impossible while K06 is unproven."
- **Not a run by the reviewer:** this is a review of the plan and the
  sources, not an independent run of the PostgreSQL measurements.
- **K06** stays an independent condition before any release gate.

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
- Developer Handoff Master v1.0.3 §8;
- the Developer Reference Spec §18;
- `API_CONTRACTS_v0.2.md` §4.12.

### 0.2 What it is not

- **Not a chat platform:** no inbox, no unread counters, no real-time
  delivery (the objective; the Spec's §2 table: "Native chat between users —
  deferred").
- **No AI.**
- **No customer access.** The contract gives no customer role on any
  communication operation (§1).
- **No change to matching, review, opportunities or tasks.**
- **No RENT** (G4-5R open). *(Revision 2, review of `dcebe46`, point 5.)*
  The currently approved matching and approval path creates SALE
  opportunities only. That does **not** prove that no other opportunity row
  can exist, the more so while K06 is UNPROVEN: a direct insert is not shown
  impossible. So the thread service **checks** the type of a named
  opportunity (G7-6, rule 0); it does not assume it.
- **No legal-evidence claim:** phone decisions are stored "as operational
  records" (`API_CONTRACTS` §4.12; the Spec's §18).

### 0.3 Carried from Slice 6, unchanged (`SLICE_6_CLOSURE.md` §1)

Slice 6 is CLOSED at `ce8cfa0`, SALE only, not a release authorization. Its
limits travel with this slice as they were given:

| Limit | Its bearing on Slice 7 |
|---|---|
| **K06 UNPROVEN** (G6-12; EN-02). **Its remedy is an independent condition before any release gate.** | Measured again: the connecting role is a superuser, and every UPDATE and DELETE on the four communication tables is accepted (M3). Every guard Slice 7 proposes (G7-12) is proven **at trigger level only**, and is labelled so |
| **G4-5R open:** SALE only | §0.2; G7-6, rule 0 checks the type |
| **OQ6-1 and OQ6-2 open** | Untouched |
| **The replay limits of the diagnostic** (its own `input_hash`; `explain.blocker_summary` not pinned) | Untouched; restated as carried in Slice 7's closure evidence |
| **The stored-titles inspection** (F6-22) | Untouched; carried as an operational condition |
| **F6-21:** R9.3 binds what a slice generates | Slice 7 copies no match, offer or permission snapshot into a communication record (§3.8) |
| **Relations are never an authorization source** | G7-6 does not read relations as a reason for a link |
| **EN-01 to EN-03** | They apply to every run |
| **STOP GATE E is the record of Slice 5's tree** | M6: a second writer of `interactions` makes its `--check` report it (F7-7, G7-8) |

---

## 1. Operations

Every Slice 7 operation in the effective contract
(`docs/api/openapi_effective_v0.2.3.yaml`, tag `Communication`):

| operationId | Method, path | Roles | Idempotency | Today | Slice 7 |
|---|---|---|---|---|---|
| `postCommunicationThreads` | POST `/communication/threads` | ADMIN, OPERATOR | `Idempotency-Key` | **no route** | **7** |
| `postCommunicationThreadsThreadIdMessages` | POST `/communication/threads/{thread_id}/messages` | ADMIN, OPERATOR | `Idempotency-Key` | **no route** | **7** |
| `postWebhooksWhatsapp` | POST `/webhooks/whatsapp` | **none: unauthenticated**, one of the closed list of six (RFC-001 R10.4) | provider event identity (`API_CONTRACTS` §2.3) | **no route** | **7** |
| `getPartiesPartyIdTimeline` | GET `/parties/{party_id}/timeline` | ADMIN, OPERATOR, REVIEWER | — | routed (Slice 1); reads `interactions` only; items are `additionalProperties: true` | **read; its allow-list is widened only if G7-8 decides it** |

**The bodies:**
- **`CommunicationThreadCreate`** requires `channel`. `party_id`,
  `request_id`, `property_id` and `opportunity_id` are optional and
  nullable; `external_thread_ref` is optional.
- **`MessageCreate`** requires `direction` and `occurred_at`. It also
  carries `external_message_ref`, `message_type`, `body_text`, `media_ref`,
  `delivery_status` and `metadata`. **It has no `provider` field.**
- **`WhatsAppWebhookEnvelope`** requires `provider_event_id`, `event_type`
  and `payload`. It is `additionalProperties: true`, with `security: []`,
  and **no header parameter declared**. Its responses are 200, 400 and 401.

**No read operation exists for threads or messages** (F7-3; G7-8).

---

## 2. What the schema and the earlier slices already give, and what they leave open

**Tables** (`schema_v0.2.3.sql` §12; migrations `0002`–`0007` add nothing
to them):

| Table | Given | Left open (measured) |
|---|---|---|
| `communication_threads` | the channel; the nullable links `party_id`, `request_id`, `property_id`, `opportunity_id` (all `ON DELETE SET NULL`); `external_thread_ref`, `opened_at`, `last_message_at`, `archived_at`, `created_by_account_id` | **no user trigger** (M3); its links can be updated (M3); deleting a thread that has a message is refused by the frozen FK `communication_messages_thread_id_fkey` (`ON DELETE RESTRICT`, M3) |
| `communication_messages` | `thread_id`, `provider`, `external_message_ref`, `direction`, `message_type`, `body_text`, `media_ref`, `delivery_status` (default UNKNOWN), `occurred_at`, `sent_by_account_id`, `metadata`; `UNIQUE(provider, external_message_ref)`, named `communication_messages_provider_external_message_ref_key` (M2) | the identity does not hold for a NULL provider (M1); any UPDATE and DELETE are accepted, the delivery status backwards included (M3) |
| `webhook_events` | `provider`, `provider_event_id`, `event_type`, `payload` (`NOT NULL`), `processing_status`, `received_at`, `processed_at`, `error_text`; `UNIQUE(provider, provider_event_id)`, which holds under concurrency (M4) | its payload and status can be changed, back to RECEIVED included, and the row deleted (M3); the stored payload holds a message's text (M7) |
| `interactions` | the type, channel, links including `thread_id`, `summary`, `outcome_code`, `occurred_at`, `operator_account_id`, `metadata` | one writer today, `opportunity_commands.py` (G5-8 (i)); no audit trigger |
| `resource_consent_bindings` with `thread_id` | `trg_consent_binding`: a COMMUNICATION_ARCHIVE binding only to a thread of the grant's own party (M5) | — |
| `observations` | `kind` includes MESSAGE and CALL_NOTE; `party_id`, `observed_at`, `raw_text`, `payload` | no column links an observation to a message (F7-11) |

**What the earlier slices give:**
- **Slice 1:** the timeline service and its allow-list (`metadata`
  excluded); idempotency records; `postWebhooksWhatsapp` in
  `PUBLIC_OPERATIONS`.
- **Slice 3:** the consent service, which knows `COMMUNICATION_THREAD` and
  `COMMUNICATION_ARCHIVE`; `POST /observations`.
- **The thread loader:** `load_thread`.
- **Slices 5 and 6:** `audit_rows`.
- **The app enforces no request-body limit today** (M7: 8 MiB accepted;
  F7-12).

---

## 3. Rules that follow from the sources without a decision

### 3.1 A webhook event is stored and deduplicated before anything is resolved
- **The sources:** `API_CONTRACTS` §4.12; ADR-09; the contract's
  description of `postWebhooksWhatsapp`.
- **Consequence:** a replay of a **completed** event writes no second
  message and no second interaction (S42, J01, mandatory test 1).
- **Measured:** the store deduplicates under concurrency (M4).
- **What "stored" means** is settled by G7-9 (a): the event row is stored
  first, and its payload is the content-free event.

### 3.2 Unauthenticated, but verified
- **The sources:** RFC-001 R10.5; `API_CONTRACTS` §8 ("Secrets/provider
  webhook verification outside domain tables"); S41 ("rejected before domain
  resolution").

### 3.3 A provider message identity is global
- **The sources:** mandatory test 2; J02; the schema's UNIQUE.
- **Measured:** M1 and M2.

### 3.4 Link consistency is a service invariant, not a trigger
- **The source:** the Remediation Review v0.2, "Communication context
  consistency".
- **Consequence:** the rule is the service's (G7-6). `0008` only freezes the
  links after creation (G7-12 (D)).

### 3.5 A phone decision is an operational record
- **The sources:** `API_CONTRACTS` §4.12; the Spec's §18.

### 3.6 Not a chat platform
- No inbox, no unread counters, no real-time delivery.

### 3.7 Staff commands are idempotent; the webhook is deduplicated by event
- **The source:** `API_CONTRACTS` §2.3 (K05).

### 3.8 What never enters a communication record
- R9.2 and R9.3. No match, offer or permission snapshot is copied into a
  thread, message, interaction or webhook row.

### 3.9 Meta's webhook, as the review of `dcebe46` cites Meta's official documentation

These are the reviewer's citation of Meta's developer documentation, page
"Create a webhook endpoint". This environment could not fetch the page:
- **subscription** is verified by a **GET** carrying `hub.mode`,
  `hub.verify_token` and `hub.challenge`;
- **notifications** are signed in **`X-Hub-Signature-256`**;
- **the native payload** of a notification is `object` with
  `entry[].changes[]`.

The frozen contract declares neither that GET nor that payload shape (F7-4,
F7-5). G7-2 decides how TURAB meets them.

---

## 4. Findings

### 4.1 Confirmed by step 0 (`evidence/SLICE7-PLAN-MEASUREMENTS.txt`)

| Finding | Measurement | Result |
|---|---|---|
| **F7-1** A NULL provider escapes the global identity | M1 | two rows, two threads, one reference |
| **F7-2** Nothing guards the communication rows | M3 | every UPDATE and DELETE accepted, as a superuser; **0 user triggers** on the four tables |
| **F7-7** STOP GATE E's writer check names one writer of `interactions` | M6 | a second writer is reported as unapproved |
| **F7-8** A thread without a party cannot carry an archive consent | M5 | refused, and also for a thread of another party |
| **F7-13 (new; from M7)** The stored webhook payload holds the content | M7 | the message text is inside `webhook_events.payload` (synthetic samples) |
| **F7-14 (new; from M8)** A link-freezing guard and `ON DELETE SET NULL` conflict | M8 | a strict guard refuses the FK's SET NULL on the party's deletion. Parties have no delete guard, so the path is reachable |

### 4.2 From reading (not measurable on PostgreSQL)

- **F7-3 · Archived content has no read operation.** The contract has no GET
  for a thread or a message. The party timeline is the only Communication
  read.
- **F7-4 · The contract has no webhook verification GET.** Meta's
  subscription needs one (§3.9).
- **F7-5 · The envelope is TURAB's, not Meta's.** The contract's required
  top-level `provider_event_id`, `event_type` and `payload` are not Meta's
  native `object`/`entry[].changes[]` (§3.9).
- **F7-6 · Retention is not defined in any source** (J03 refers it to
  "pilot/legal review").
- **F7-9 · `archived_at` has no command.**
- **F7-10 · After creation, delivery status changes only through the
  webhook.**
- **F7-11 · No column links an observation to a message.**
- **F7-12 · No request-body limit** (M7: an 8 MiB body is accepted by a
  delivered route). The unauthenticated webhook must read its whole raw
  body to verify a signature (G7-2 (i)), so the limit must apply before
  that read (G7-15).

---

## 5. Decisions needed — none is taken by this plan

### G7-1 · Scope
- **Recommended:**
  - the three operations of §1, and the timeline as G7-8 decides;
  - migration `0008` as G7-12 decides;
  - an operator recovery command for stuck events, run by an operator and
    not an HTTP operation (G7-2 (v));
  - no outbound sending (G7-14);
  - no customer operation;
  - no Meta-facing GET in TURAB (G7-2 (ii)).
- **Blocks:** everything.

### G7-2 · The webhook boundary

#### (i) What TURAB verifies, before any write (S41, R10.5)
- an HMAC-SHA256 of the **raw** body, compared in constant time, with a
  secret read from the environment (not a domain table). A missing secret
  fails closed;
- a missing or wrong signature is 401 and writes **nothing**, not even
  `webhook_events`;
- an invalid request is logged without its body (`API_CONTRACTS` §8);
- **the body limit applies before the body is read** (G7-15).

#### (ii) Meta, the relay, and what each signature proves (review of `dcebe46`, point 3)

**(a) Recommended. A relay outside TURAB's API adapts Meta to the frozen
contract.** The relay:
1. **answers Meta's subscription GET** (`hub.mode`, `hub.verify_token`,
   `hub.challenge`). **The GET lives in the relay,** so TURAB's frozen
   contract needs none, and OQ7-2 is settled by placement;
2. **verifies Meta's `X-Hub-Signature-256`** over Meta's raw body, with
   Meta's app secret, **before** transforming anything. It drops what fails;
3. **transforms** each message and each status inside `entry[].changes[]`
   into one `WhatsAppWebhookEnvelope`, with a `provider_event_id` unique per
   event:
   - `message:<wamid>` for a message;
   - `status:<wamid>:<status>:<timestamp>` for a status;
4. **signs the envelope** with its own key, which is distinct from Meta's
   secret, in a header of its own: **`X-Turab-Relay-Signature`**,
   HMAC-SHA256 of the envelope's raw bytes.

**TURAB** verifies the relay's signature (i).

**What each signature proves, stated in the closure evidence as worded
here:**
- TURAB's check proves that the envelope **comes from the holder of the
  relay's key**, unchanged since it was signed;
- it is **not** a verification of Meta's signature: Meta's signature is
  checked by the relay alone, and TURAB **trusts the relay** for it;
- Slice 7's tests prove TURAB's side;
- **the relay's verification of Meta is UNPROVEN in Slice 7** unless (a1)
  is chosen.

**The relay's two variants:**
- **(a1)** The relay is built in this repository as a separate component,
  with its own tests of Meta's GET and signature on synthetic notifications.
  It widens the slice.
- **(a2) Recommended within (a).** The relay is specified here as an
  interface (its four duties above, the envelope mapping, the header), and
  is built outside the slice. Meta's verification is stated as an UNPROVEN
  boundary, as K06 is.

**The header is not declared by the contract** (`parameters: []`). It is a
security mechanism outside the OpenAPI, as R10.5's verification is.
Declaring it in the contract would be a correction for the contract's owner
(OQ7-2).

**(b) TURAB accepts Meta's native payload, and verifies Meta's signature
directly.**
- It needs the GET and a different body schema: **two contract changes.**
- It proves Meta's signature in Slice 7.
- It keeps Meta's app secret in TURAB's environment.

#### (iii) The provider
- The constant `whatsapp` for this route.

#### (iv) The two transactions, and what the first stores
1. **The event row,** inserted and committed alone, with the
   **content-free payload** of G7-9 (a). A conflict on `(provider,
   provider_event_id)` goes to (v).
2. **Resolution and its writes** (G7-3, G7-9) in a second transaction:
   - it begins by claiming the event row `FOR UPDATE NOWAIT` (M4b);
   - it ends by setting `processing_status` (PROCESSED, IGNORED, or FAILED
     with a fixed `error_text` code, never the exception's text) and
     `processed_at`.

#### (v) The fate of RECEIVED and FAILED, and their recovery (review of `dcebe46`, point 2)

M4b shows that a replay's `ON CONFLICT DO NOTHING` returns nothing whatever
the stored status. It also shows that a processor's row lock is visible to a
NOWAIT claim (55P03) and gone once the processor ends. So:

- **A replay reads the stored status:**

  | Stored status | The replay's effect |
  |---|---|
  | **PROCESSED** or **IGNORED** | a true replay: 200, nothing written (S42) |
  | **RECEIVED** or **FAILED** | the replay **processes the event again**, with the replayed envelope (which carries the content again: G7-9) |
  | **in flight** (the claim fails 55P03) | 200, nothing written; the holder finishes it |

- **The answer to a first delivery:**
  - **200** when processing ended PROCESSED or IGNORED;
  - **500**, typed `WEBHOOK_PROCESSING_FAILED`, when it ended FAILED. A 500
    makes the relay (or the provider) deliver the event again, and the
    redelivery is the recovery.

  **This answer needs a decision.** The contract lists 200, 400 and 401 for
  this operation. `API_CONTRACTS` §2.5 governs errors generally and does
  not exclude a 500. The alternative is 200 with the event left FAILED:
  then only the recovery command below recovers it, **without** its
  content.
- **An operator recovery command** for an event that no redelivery reaches:
  - a script under `db/ops/`, not an HTTP operation, so the contract is not
    widened. It lists and re-processes:
    - events RECEIVED for longer than a stated delay (e.g. 5 minutes);
    - FAILED events;
  - it skips any row it cannot claim (`FOR UPDATE SKIP LOCKED`, M4b);
  - **its stated limit:** the stored payload is content-free (G7-9), so it
    recovers identifiers, threads and statuses, and stores a message
    **without** content (`metadata.content_archived = false`, reason
    `RECOVERED_WITHOUT_CONTENT`).
- **The transitions** (G7-12 (C)):
  - RECEIVED → PROCESSED, IGNORED or FAILED;
  - FAILED → PROCESSED, IGNORED or FAILED (a retry);
  - **nothing leaves PROCESSED or IGNORED.**
- **The closure evidence** counts the events in RECEIVED and FAILED at the
  end of the run. A test proves that no event stays RECEIVED after a
  redelivery or after the recovery command.

**Blocks:** step 3.

### G7-3 · Event types and thread resolution
- **(a) Recommended.** The envelope's `payload` has a documented internal
  shape. **This is the relay's output, (ii).**
  - **`message`:** `external_message_ref`, `thread_ref`, `occurred_at`,
    `message_type`, and optional `body_text` and `media_ref`. It is stored as
    an INBOUND message in the WHATSAPP thread whose `external_thread_ref` is
    `thread_ref`;
  - **`status`:** `external_message_ref`, `status` and `occurred_at` (G7-5).
- **IGNORED,** with a fixed reason: an unknown type, an unknown thread, or an
  unknown message for a status.
- **No thread, party or identity is created from a webhook** (identity is
  Slice 3's reviewed process).
- **(b)** Create a party-less thread for an unknown `thread_ref`. Not
  recommended: it makes records nobody reviewed, and such a thread can never
  archive content (M5).
- **Blocks:** step 3.

### G7-4 · The global message identity (mandatory test 2, J02, F7-1)
- **(a) Recommended.**
  - The service sets `provider` whenever `external_message_ref` is given:
    `whatsapp` for a WHATSAPP thread.
  - It refuses an `external_message_ref` on an INTERNAL message (422).
  - `0008` (A): `CHECK (external_message_ref IS NULL OR provider IS NOT
    NULL)`.
  - A 23505 whose constraint is
    `communication_messages_provider_external_message_ref_key` (M2) maps to
    a typed 409 for staff, and to IGNORED for a webhook.
- **(b)** `NULLS NOT DISTINCT`. Not recommended: two messages with neither a
  provider nor a reference would collide.
- **Blocks:** steps 1–3.

### G7-5 · Delivery and read status
- **(a) Recommended.**
  - **The order:** QUEUED < SENT < DELIVERED < READ.
  - **Moves:** forward only; a late, older status is IGNORED. FAILED is
    accepted from QUEUED or SENT, and is final. UNKNOWN is replaced by any
    status.
  - **The only path** after creation is the webhook (F7-10).
  - **M3 shows the schema accepts READ, then SENT;** `0008` (B) refuses it.
- **(b)** Last-received wins. Not recommended.
- **Blocks:** step 3; `0008` (B).

### G7-6 · The thread/opportunity link invariant (mandatory test 3)

**Checked at creation;** the links are frozen afterwards (G7-12 (D)).

- **(a) Recommended rules:**
  0. **(Revision 2, review of `dcebe46`, point 5.)** A named opportunity must
     be of a **SALE** transaction: its approved match's evaluated offer is a
     SALE offer, and its request's intent is BUY. Otherwise a typed 422,
     writing nothing. The type is **checked, not assumed** (§0.2).
  1. **If `opportunity_id` is given:**
     - `request_id`, when given, equals the opportunity's request;
     - `property_id`, when given, equals the opportunity's property;
     - `party_id` is the opportunity's buyer (the request's party) or its
       seller (the party of its current offer), per the Remediation
       Review's example.
  2. **If `request_id` is given without an opportunity,** `party_id` is the
     request's party.
  3. **If `property_id` is given without an opportunity,** `party_id` is the
     party of one of the property's offers. A relation is not accepted as
     the reason.
  4. **Every id names an existing row.** Otherwise a typed 404 or 422,
     writing nothing.
- **(b)** Rules 0–2 only.
- **(c)** A trigger. Contrary to §3.4.
- **Blocks:** step 2.

### G7-7 · Must a staff-created thread name its party?
- **(a) Recommended: yes,** by CORRECTION-006, written as CORRECTION-005 was.
  A narrowing; M5 shows that a party-less thread can never carry an archive
  consent.
- **(b)** Optional. Such a thread never archives content (G7-9).
- **Blocks:** step 2.

### G7-8 · What a staff member can read, and the timeline (review of `dcebe46`, point 4; F7-3, F7-7)

**What "retrievable" means within Slice 7, stated.** Under the frozen
contract the only Communication read is `getPartiesPartyIdTimeline`, for
ADMIN, OPERATOR and REVIEWER. Its item is `additionalProperties: true`: the
contract leaves the field set to the implementation, and Slice 1 fixed it by
an allow-list (`services/timeline.py`). **Anything a staff member reads of a
message, they read there, or nowhere.**

- **(a) Recommended. The record is readable through the timeline, by an
  explicit, tested widening of the allow-list.**
  - **The new rows:** each message writes one `interactions` row in the same
    transaction:
    - a type by channel and direction (WHATSAPP, CALL, …; NOTE for
      INTERNAL);
    - its `thread_id` and links;
    - a fixed `summary`;
    - `metadata.message_id`.
  - **What the item of such an interaction carries:** one added key,
    **`message`**:
    - `message_id`, `direction`, `message_type`, `delivery_status` and
      `occurred_at`;
    - `content_archived`;
    - `body_text` and `media_ref` **only when `content_archived` is
      true** (G7-9).
  - **Why this is not a silent widening of the contract:**
    - the item's schema is open, so the OpenAPI is unchanged;
    - the allow-list change is decided here, named in the delivery, and held
      by a DTO test of the item's exact key set (R9.5).

    It is still a change of Slice 1's delivered output, and it is stated as
    such.
  - **What stays unreadable through the API:**
    - a message's content when it was not archived;
    - a thread's own row (its links, `external_thread_ref`): only the
      `thread_id` and the item's links are shown;
    - `webhook_events`.
  - **The cost:**
    - a second writer of `interactions`, changing G5-8 (i)'s single writer;
    - STOP GATE E's `--check` reports it (M6). **Recommended:** STOP GATE E
      stays the record of Slice 5's tree, as STOP GATE D stays Slice 4's,
      and Slice 7's evidence inventories the writers of `interactions` by
      kind.
- **(b) Metadata only.**
  - The timeline shows the message's existence, direction, time and status,
    never its content.
  - "Retrievable" then means: retrievable by staff through the timeline as
    a record of what happened. The **content** is retrievable only from the
    database, by an operator, outside the API.
  - **Reading content needs a contract addition** (a GET of a thread's
    messages: OQ7-3).
- **(c)** New GET operations now. A contract addition, outside the slice.
- **Blocks:** step 4.

### G7-9 · Content and consent (review of `dcebe46`, point 1; J03; F7-6; F7-13)

**The rule: no content is stored anywhere unless the thread's party has
consented, at the moment of writing.** M7 shows that storing the event as
received would store the text, so the rule binds the event store too.

**(a) Recommended. Content is kept only in `communication_messages`, under a
consent checked at write time.**

**1. `webhook_events.payload` is the content-free event,** built from the
verified envelope before the first insert:
- **kept:** `provider_event_id`, `event_type`, `external_message_ref`,
  `thread_ref`, `occurred_at`, `message_type`, `status`, and two flags:
  `has_body` and `has_media`;
- **dropped:** `body_text`, `media_ref`, and **every key not on this list**.
  An allow-list, so a key the relay adds later is dropped, not stored;
- **what it records:** enough to deduplicate, to process statuses, to
  recover identifiers, and to say that content existed. Never the content.

**2. `communication_messages.metadata`** carries:
- `content_archived` (bool);
- `content_withheld_reason`: `NO_ARCHIVE_CONSENT`,
  `RECOVERED_WITHOUT_CONTENT` or none;
- for a webhook message, `webhook_event_id`.

It never carries content, a digest of content, or the provider's raw
fields.

**3. The consent condition, as it actually holds:**
- **What is checked:** in the transaction that writes the message, the
  service reads, under `FOR SHARE`, an ACTIVE `COMMUNICATION_ARCHIVE` grant
  of the thread's party, bound to that thread and unrevoked. The same lock
  pattern as Slice 5's share against a binding (R-S5-5-01), so a revocation
  committing meanwhile is waited for, then seen.
- **If it holds,** `body_text` and `media_ref` are written.
- **If it does not hold:**
  - **a staff message** that carries content is refused with a typed 422
    `CONTENT_NOT_ARCHIVABLE`, writing nothing (the operator resends without
    content). Silently dropping what an operator typed would hide the
    refusal;
  - **a webhook message** is stored without content, with
    `content_withheld_reason = NO_ARCHIVE_CONSENT`. The content existed only
    in the request's memory, and is discarded.

**4. Logs** carry no body, of either kind (`API_CONTRACTS` §8).

**5. Revocation** stops future archiving from its commit on. **Content
already archived stays.** Erasing it on revocation is a retention rule
(OQ7-1), and is not claimed.

**6. J03 is claimed exactly as:** no content is stored without a consent
valid when it was written. Retention is not claimed (OQ7-1).

**The cost:**
- a message whose processing FAILED and is recovered by the command loses
  its content for good. Only a redelivery can bring it back (G7-2 (v));
- a relay that adds content under an unlisted key has it dropped, by
  design.

**(b) Keep the event as received, and redact it after processing.** Not
recommended:
- the content would exist in the database without consent between the two
  transactions, and for good in a RECEIVED or FAILED event;
- the redaction is an UPDATE of `payload`, contrary to G7-12 (C).

**(c) Store content always.** Contrary to J03 as worded.

**Blocks:** steps 2–3.

### G7-10 · Linking a phone decision to a later written confirmation (mandatory test 4, F7-11)
- **(a) Recommended. The link is a record of its own, append-only:**
  - **the decision:** an INTERNAL message, `message_type` `PHONE_DECISION`,
    in a PHONE thread of the party;
  - **the confirmation:** an observation of kind MESSAGE, made by `POST
    /observations` (Slice 3);
  - **the link:** a later INTERNAL message, `message_type`
    `CONFIRMATION_LINK`, whose metadata names `decision_message_id` and
    `observation_id`. The service checks four things:
    - both exist;
    - the decision is in the same thread;
    - the observation is of the thread's party;
    - its `observed_at` is not before the decision.
  - **Nothing earlier is updated.** No legal value is claimed.
  - **An INTERNAL message carries staff text,** so G7-9's consent rule
    applies to its `body_text` as to any message.
- **(b)** The observation's `payload` names the decision. This changes Slice
  3's route.
- **(c)** Update the decision's metadata. Contrary to G7-12 (B).
- **Blocks:** step 4.

### G7-11 · Audit
- **Recommended:**
  - `audit_rows` for threads, messages and interactions, with `body_text`
    and `media_ref` withheld;
  - `webhook_events` is its own processing record, not audited twice;
  - a refused webhook is logged without its body.
- **Blocks:** steps 2–4.

### G7-12 · Migration `0008` (parts proposed; the text in revision 3, once these are decided)
- **(A)** `CHECK (external_message_ref IS NULL OR provider IS NOT NULL)`
  (G7-4).
- **(B) Messages are append-only.** The one exception is `delivery_status`,
  forward only, by G7-5's order. DELETE is refused.
- **(C) A `webhook_events` row is immutable,** except its processing fields:
  - `processing_status` may move from RECEIVED or FAILED only (G7-2 (v));
  - `payload` and the identity never change;
  - DELETE is refused.
- **(D) A thread's links are frozen** (revision 2, rewritten on M8,
  F7-14).

  M8 measured three candidates. **The first two are refused:**
  - **strict** (no change of a link): it **also refuses the FK's `ON DELETE
    SET NULL`**. Deleting a thread's party then fails, so revision 1's two
    statements could not both hold;
  - **permissive** (a link may become NULL): it lets the FK act, but **also
    accepts a direct UPDATE of a link to NULL**.

  **Two remain, and one is to be chosen:**
  - **(D1) Recommended: FK-only.**
    - A link may become NULL only **below a referential action**
      (`pg_trigger_depth() > 1`; M8: depth 1 for a direct UPDATE, 2 under
      the FK).
    - Every direct change is refused; `channel` never changes;
      `last_message_at` may move forward.
    - The frozen FKs stay as they are.
    - **Its stated limit:** depth > 1 is also true for an UPDATE issued from
      inside another trigger. The threads table has none today (M3). A
      future trigger on it would have to be reviewed against this guard,
      and the closure evidence lists the table's triggers.
  - **(D2) Strict, with the four link FKs altered** from `ON DELETE SET
    NULL` to `ON DELETE RESTRICT`.
    - Deleting a party, request, property or opportunity that a thread
      names is then refused. Three of the four parents (`requests`,
      `properties`, `opportunities`) already have delete guards;
      `parties` has none (M8).
    - It changes four frozen constraints, the price of a simpler guard.
- **Labelled as trigger level:** each guard is proven at trigger level, not
  as K06 (G7-13).
- **Blocks:** step 1.

### G7-13 · K06 (not blocking this plan)
- **Carried unchanged.** The application role is a superuser (M3). K06 is
  UNPROVEN, and its remedy is an independent condition before any release
  gate.

### G7-14 · Outbound sending
- **(a) Recommended. Archive only.**
  - An OUTBOUND message records what was sent through the official channel;
    its status arrives by webhook.
  - No provider API call, no network, no provider credentials in TURAB.
- **(b)** Send through the provider. Its credentials and network boundary
  are specified by no source.

### G7-15 · The body limit of the unauthenticated webhook (new; F7-12)
- **(a) Recommended.**
  - The webhook route refuses a body larger than **64 KiB** with 400,
    writing nothing. The limit is checked on `Content-Length` and while
    reading, **before** the signature is computed.
  - The value is set from M7's synthetic samples (under 1 KB) with a wide
    margin, and is to be revisited on the relay's real envelopes.
- **(b)** An app-wide limit. A change beyond this slice's routes, though
  F7-12 concerns them all: put as a separate question (OQ7-4).
- **Blocks:** step 3.

### Open questions (not decisions)
- **OQ7-1 · Retention:** of archived content, and its fate on revocation
  (J03, F7-6). The sources leave it to "pilot/legal review".
- **OQ7-2 · The contract's owner:**
  - whether to declare the relay's signature header;
  - whether ever to accept Meta's native shape (G7-2 (b)).
- **OQ7-3 · A read operation for a thread's messages,** if G7-8 (b) is
  decided.
- **OQ7-4 · An app-wide request-body limit** (F7-12).

---

## 6. Tests and closure evidence

### 6.1 The four mandatory tests

| # | Test, as written | Proof planned |
|---|---|---|
| 1 | "repeated provider webhook creates one message" | the same signed envelope posted twice, and concurrently: one event row, one message, one interaction. A PROCESSED replay writes nothing; a FAILED or RECEIVED event is completed by the replay, still one message (G7-2 (v)) |
| 2 | "same provider message id cannot be inserted into another thread" | the same `(whatsapp, ref)`, by staff and by webhook, into a second thread: a typed 409, or IGNORED, and no row. The NULL-provider path is refused by the service and by `0008` (A) |
| 3 | "thread/opportunity links are checked by service invariant" | each rule of G7-6, rule 0 (SALE) included, with an inconsistent link refused, writing nothing; the seller's thread about the buyer's opportunity accepted; the links frozen afterwards, and the FK's SET NULL still working (M8, D1) |
| 4 | "phone decision can be linked to later written confirmation observation" | G7-10 end to end over HTTP |

### 6.2 Red-team and RFC-001 cases

| Case | Planned |
|---|---|
| **J01** | mandatory test 1 |
| **J02** | mandatory test 2 |
| **J03** | as claimed in G7-9 (6): **no content stored without a consent valid at write time**, in messages, in the event store and in logs. Retention is not claimed |
| **S41** | a wrong or missing relay signature is 401 before any write. The test's own wording: it proves the relay's origin, not Meta's |
| **S42** | a replay of a completed event is 200, with no duplicate |
| **K05** | each staff POST replays with its key; another body on the key is 409 |
| **K06** | not claimed; trigger-level guards listed as trigger level |

### 6.3 Authorization
- **The two staff POSTs:** ADMIN and OPERATOR allowed; REVIEWER and CUSTOMER
  refused (403) and recorded; anonymous refused (401).
- **The webhook:** stays in the closed list of six.
- **The timeline:** its widened item checked by an exact key-set test
  (R9.5).
- **The matrix** gains the three operations.

### 6.4 Closure evidence (no STOP GATE)

As Slice 6's:
- a generated `SLICE_7_EVIDENCE.md` with `--check`, bound to a clean-tree
  run;
- the writes to the four tables inventoried **by kind**;
- **the event store's RECEIVED and FAILED counts** at the end of the run;
- **the triggers on `communication_threads`** (D1's limit);
- **the trust boundary of G7-2 (ii), as worded there;**
- Slice 6's carried limits, none as proven.

### 6.5 Step 0: done

The measurements are recorded in `evidence/SLICE7-PLAN-MEASUREMENTS.txt` and
its script. They were authorized in the review of `dcebe46`, run twice with
identical results, and are ours.

---

## 7. Acceptance conditions

1. **The contract is unchanged,** apart from CORRECTION-006 if G7-7 (a) is
   decided and approved. The relay's header is outside the OpenAPI
   (G7-2 (ii)).
2. **A completed webhook event, replayed, writes nothing;** an incomplete
   one is completed once (J01, S42, G7-2 (v)).
3. **A provider message identity is global** (J02), the NULL case included.
4. **An unverified webhook writes nothing** (S41). Its check is described
   as the relay's origin, never as Meta's signature.
5. **Thread links are consistent at creation, SALE checked, and frozen,**
   with the FK's SET NULL working (G7-6, G7-12 (D)).
6. **A phone decision's confirmation link is append-only,** and claims no
   legal value.
7. **No content is stored without a consent valid at write time,** in any
   table or log (G7-9). Retention is not claimed (OQ7-1).
8. **What staff can read is exactly what G7-8 decides,** held by a key-set
   test.
9. **The writes to the four tables are exactly those decided,** by kind.
10. **SALE only,** checked (G4-5R open). **K06 UNPROVEN.** **No AI.**

---

## 8. Sequence

| Step | Content | Depends on |
|---|---|---|
| 0 | the measurements M1–M8 | **done** (authorized in the review of `dcebe46`) |
| 1 | migration `0008`, as G7-12 decides; tests, mutations | G7-4, G7-5, G7-6, G7-12; the text approved in revision 3 |
| 2 | threads, the link invariant, staff messages, identity and consent rules; CORRECTION-006 if decided | G7-4, G7-6, G7-7, G7-9, G7-11 |
| 3 | the webhook: body limit, verification, the content-free event store, resolution, statuses, replay and the recovery command | G7-2, G7-3, G7-5, G7-9, G7-15 |
| 4 | the timeline (G7-8) and the confirmation link (G7-10) | G7-8, G7-10 |
| 5 | the mandatory and red-team tests end to end, mutations, the closure evidence | all |

Each step is delivered with its tests and its mutation record, and is
reviewed before the next begins. A defect found in a step is measured before
it is fixed.

---

## 9. Document identity

This file's sha256 is recorded in `docs/gate/evidence/DOCUMENT-HASHES.txt`
at the commit that adds it.
