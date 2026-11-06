# Contract Delta · Slice 8 — the external-lead workflow (DRAFT)

**Status: DRAFT for review, Slice 8 plan revision 8** (§3.0 added after the
review of `f77f8aa`: no `404` on the three operations by `lead_id`). The review of
`b39ad10` authorized preparing this text; **it is not approved.** Nothing in
it is in force: its addendum is a draft under `docs/gate/drafts/`, which the
code never reads.
**Kind:** a contract **ADDITION**, as G3-6's: four operations the frozen
contract does not have. `openapi_v0.2.3.yaml` is not modified.
**Decision it would implement:** Slice 8 plan G8-2 to G8-4 and G8-6, with
the directions of the reviews of `3922850` and `b39ad10`.
**Its narrowing companion:** the conversion payload is NOT here. It narrows
a frozen operation, so it is a CORRECTION
(`docs/gate/drafts/CORRECTION-009-lead-conversion-payload.DRAFT.md`).

---

## 1. Why an addition

The frozen contract declares no operation that records a contact attempt,
moves a lead's status, reads a brief of a lead, or pages the leads queue
(plan F8-1, F8-3, F8-8). The correction overlay may only narrow; it cannot
create an operation (CONTRACT_CORRECTIONS.yaml, invariant 1). So these four
are an addition, carried by a standalone addendum bound to this text by its
sha256.

## 2. The operations

| operationId | Method and path | Roles | Kind |
|---|---|---|---|
| `postExternalLeadsLeadIdContactAttempts` | `POST /external-leads/{lead_id}/contact-attempts` | ADMIN, OPERATOR | command, idempotent |
| `postExternalLeadsLeadIdStatus` | `POST /external-leads/{lead_id}/status` | ADMIN, OPERATOR | command, idempotent |
| `getExternalLeadsLeadIdCallBrief` | `GET /external-leads/{lead_id}/call-brief` | ADMIN, OPERATOR, REVIEWER | audited read |
| `getBackofficeQueuesExternalLeadsPage` | `GET /backoffice/queues/external-leads/page` | ADMIN, OPERATOR, REVIEWER | audited read, per page |

All four are authenticated; none is reachable by a CUSTOMER. Their schemas
are the addendum's (`ADD-SLICE8_external_lead_workflow.DRAFT.yaml`).

## 3. The rules each operation carries

### 3.0 A `lead_id` that names no lead, or a lead not the caller's to act on

Decided in the review of `f77f8aa`, for the three operations addressed by
`lead_id` (contact attempts, status, Call Brief): **`403
OBJECT_NOT_AUTHORIZED`**, never `404`.

| Case | Answer |
|---|---|
| the role is not the operation's (a CUSTOMER; a REVIEWER on a command) | `403 ROLE_NOT_PERMITTED`, at the role stage, before any lead is read |
| **the `lead_id` names no lead** | **`403 OBJECT_NOT_AUTHORIZED`**, and the denial recorded with the kind and the id |
| the lead exists, and the caller's object check fails | `403 OBJECT_NOT_AUTHORIZED`, recorded: the same answer |

**The text each case rests on:**
- **R5.3b:** "Staff object checks that fail return `403` with
  `OBJECT_NOT_AUTHORIZED`".
- **The absent id is stated in RFC-001's own text,** not inferred from
  R5.3b. §10's decision pipeline, stage 5: "absent ⇒ 404 on /me/*, 403
  internal (R5.3)".
- **§12's table:** "Object check failed, internal endpoint: 403,
  `OBJECT_NOT_AUTHORIZED`".

**The precedents, each pinned by a test:** a staff path's unknown id is
`403`, recorded.
- property: `test_on_the_staff_path_an_unknown_property_is_403`;
- match: `test_an_unknown_match_is_403_and_recorded`;
- opportunity: `test_an_unknown_opportunity_is_403_for_staff_and_recorded`;
- task: `test_an_unknown_task_is_403_and_the_denial_is_recorded`;
- thread: `test_an_unknown_thread_is_403_and_the_denial_is_recorded`. The
  thread's case is the closest: Slice 7 plan revision 8 corrected a drafted
  "404 for the path's thread" to this answer.

**What the refusal does:**
- **For the two commands:** it writes nothing and consumes no idempotency
  key, as the thread's message does. The check runs before the command's
  transaction.
- **For the brief:** no brief is computed; the denial is recorded, as
  `read_opportunity` records it.
- **Its `detail`** names no lead and no reason beyond "not an available
  lead".

**Not this Delta's:** the frozen `postExternalLeadsLeadIdConvert` answers
`404` for an unknown lead today (Slice 3, G3-10; `services/external_leads.py`
`refuse_conversion`, pinned by `test_converting_an_unknown_lead_is_404`). It
is outside the three operations decided here. Whether it follows the same
rule when Slice 8 implements the conversion is plan question Q-C2.

### 3.1 Contact attempts

- **Body:** `channel` (PHONE, WHATSAPP, SMS, IN_PERSON, OTHER), `outcome_code`
  (one of four `LEAD_CONTACT` codes), `occurred_at`. **No free-text field:**
  the row is audited whole by `audit_row_change` (plan Q-A4), so nothing said
  on a call may enter it.
- **`occurred_at` is not in the future** by the server's clock: refused `422`
  by the service; in the database, `recorded_at` is assigned by the server at
  insert (a BEFORE INSERT trigger overwrites any supplied value), and
  `ck_lead_attempt_not_future` compares `occurred_at <= recorded_at`, no
  margin (plan M13). One rule, one clock.
- **The lead's status is derived** (plan §5A.1): `LEAD_NO_ANSWER` →
  `CONTACT_ATTEMPTED`; `LEAD_WRONG_NUMBER` or `LEAD_NUMBER_NOT_IN_SERVICE` →
  `UNREACHABLE`; `LEAD_REACHED` → `CONTACTED`; each from `DISCOVERED`,
  `CONTACT_ATTEMPTED` or `UNREACHABLE` only. From `CONTACTED` onward, the
  status is unchanged.
- **A terminal lead** (`CONVERTED`, `DECLINED`, `CLOSED`): `409
  EXTERNAL_LEAD_TERMINAL`, nothing written, no idempotency key consumed.
- **An unknown lead:** §3.0.
- **`201`** `{attempt_id, lead_id, lead_status}`. Sends nothing to anyone.

### 3.2 Status

- **`to`** one of `CONSENT_PENDING`, `CONSENTED`, `PENDING_INFO`, `DECLINED`,
  `CLOSED`. **`CONVERTED` is never set here** (only by the conversion).
- **`CONSENTED`** requires `party_id` and `consent_id`, and **in its
  transaction**: the grant row locked `FOR SHARE`, then `status = 'GRANTED'`,
  `revoked_at IS NULL`, `scope = 'ASSISTED_ENTRY'`, the grant's party =
  `party_id`; otherwise `409 CONSENT_NOT_CURRENT`. The status records that a
  current grant was seen; **it authorizes nothing later** (plan §5A.1).
- **`DECLINED`, `CLOSED`** require a `LEAD_CLOSURE` reason code; any other
  `to` refuses one (the schema's `allOf`).
- **A transition the table refuses:** `409 EXTERNAL_LEAD_TRANSITION_NOT_ALLOWED`.
- **An unknown lead:** §3.0.
- **`200`** `{lead_id, status}`.

### 3.3 The Call Brief

| Field | Content |
|---|---|
| `lead_id`, `lead_kind`, `status`, `source_kind`, `discovered_at` | the lead and its source's kind |
| `attempts` | `{count, last_outcome_code, last_occurred_at}` |
| `known` | of `PARTY_IDENTIFIED`, `CONTACT_POINT_VERIFIED`, `CONSENT_CURRENT`: those TURAB holds as records **at the read** |
| `missing` | those of the three absent; for a REQUEST lead, the conversion payload's required fields (CORRECTION-009), which no record holds before the conversion |
| `permission_needed` | `ASSISTED_ENTRY` when `CONSENT_CURRENT` is absent; `PROPERTY_CONVERSION_NOT_AVAILABLE` for a PROPERTY lead |
| `as_of` | the read's time |

- `CONTACT_POINT_VERIFIED`: a contact point of the lead's party whose
  control status is `VERIFIED_CONTROL`.
- `CONSENT_CURRENT`: an `ASSISTED_ENTRY` grant of the lead's party,
  `GRANTED` and unrevoked at the read. **It authorizes nothing:** every
  command re-checks the grant itself, under its lock.
- **Never in it:** `raw_text`, the source's URL or reference, `raw_payload`,
  metadata, a contact point's value.
- **An unknown lead:** §3.0; no brief, the denial recorded.

### 3.4 The paged queue

**The query of each page**, one statement, so one snapshot under READ
COMMITTED (PostgreSQL 16, §13.2.1):

```sql
SELECT external_lead_id, lead_kind, status, discovered_at
  FROM turab.external_leads
 WHERE status NOT IN ('CONVERTED', 'DECLINED', 'CLOSED')
   AND (discovered_at, external_lead_id) > (:cursor_at, :cursor_id)  -- absent on page 1
 ORDER BY discovered_at, external_lead_id
 LIMIT :limit + 1                                                     -- one more: is there a next page?
```

- **The cursor:** opaque, base64url of `{"v":1,"at":<discovered_at, to the
  microsecond>,"id":<external_lead_id>}`, the key of the page's last item;
  `null` when no row followed. Malformed: `422`. It carries what the caller
  already saw, nothing more.
- **Its keys never change:** no application path updates `discovered_at` or
  `external_lead_id` (plan M1).

**What a walk guarantees** (a walk: page 1 without a cursor, then each
`next_cursor` in turn), and no more:
1. **No lead twice in one walk:** each page's keys are strictly greater than
   the previous page's last key.
2. **Every lead that is committed before the walk's first page is read, and
   is open at the read of the page its key falls in, is returned once.**
3. **Each item's `status`** is the one at the read of its page.

**What it does not guarantee**, each case stated:

| Case | What the walk does |
|---|---|
| a lead committed **during** the walk, its key greater than the cursor at the next read | returned on a later page of this walk, if open then |
| a lead committed **during** the walk, its key **at or below** the cursor (its transaction began before the cursor's row and committed later: measured, M6) | **not returned by this walk** |
| a lead that becomes terminal before its page is read | not returned |
| a lead that becomes terminal after its page was read | already returned; the caller's copy is stale |
| a lead that moves between open statuses | returned once, at its unchanged key, with the status of its page's read |

- **A new walk** (no cursor) reconsiders every lead **that is still open**
  at its pages' reads: a lead missed by one walk is returned by a later one
  only if it is still in the queue then.
- **No snapshot spans the pages.** A walk is a sequence of independent
  reads; nothing in a response claims otherwise. (Revision 2's
  `walk_started_at` is withdrawn: a value in a response is not a snapshot,
  as the review of `b39ad10` noted.)

### 3.5 Operational volume

- **At operational volume, the paged operation is the one used.**
- **The frozen `getBackofficeQueuesExternalLeads` stays as it is:** unpaged
  and uncapped (G3-10 Q-8), **its roles unchanged** (plan Q-B2 (b), review of
  `0a78e91`: narrowing them would not make an unpaged query safe). **It does
  not become safe because this one exists.** Its use at operational volume
  stays forbidden; that limit is carried into the slice's closure record and
  the operational setup.

## 4. Audit

Each command audited by the command layer, once per accepted command,
refusals as every refusal (an unknown lead: a recorded `OBJECT_NOT_AUTHORIZED`
denial with the lead's kind and id, §3.0); the brief audited once per read; the page once
per page; `external_lead_contact_attempts` by `audit_row_change` on INSERT.

## 5. What this Delta does not do

- convert a lead (the frozen `postExternalLeadsLeadIdConvert`, narrowed by
  CORRECTION-009);
- record an interest (the frozen `postInterests`);
- send anything to anyone, or receive any event;
- give a CUSTOMER any access;
- change a frozen operation, schema or component.
