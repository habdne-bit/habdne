# R-1 — The relay between Meta and TURAB's webhook
## Plan — **revision 1** (planning only)

**Status: PLANNING ONLY, put up for review.** This document authorizes
nothing.
- **No code** is written under it.
- **No relay** is built or deployed.
- **No secret, verify token or Meta app setting** is created.
- **No real event** is received. R-1 stays **UNMET**: **no real event may be
  received** before it is met and reviewed (§4).

**What R-1 is.** The review of `4aed49b` decided (a2) for Meta's boundary
(Slice 7 plan, G7-2 (ii)):
- the relay is specified by Slice 7 as an interface, and built outside the
  slice;
- choosing (a2) created **condition R-1**: the relay is built, and its own
  tests prove its seven duties on synthetic notifications, **before TURAB
  receives any real event**;
- Slice 7 is closed at `abee0f9` with R-1 **UNMET** (`SLICE_7_CLOSURE.md`
  §1, limit 1). **TURAB's signature check proves the relay's origin, not
  Meta's.**

**Not reopened by this plan:**
- TURAB's webhook as closed in Slice 7: its contract, CORRECTION-007 and
  CORRECTION-008, the 64 KiB body limit (G7-15), the envelope and its
  required keys (G7-3, G7-17 (iii)), the transitions of G7-5, and
  `X-Turab-Relay-Signature`;
- the `provider_event_id` formats of G7-2 (ii): `message:<wamid>` and
  `status:<wamid>:<status>:<timestamp>`;
- the scope: **SALE only** (G4-5R open).

**K06 stays an independent condition before the release gate.** This plan
does not touch it.

The next slice's plan follows the review of this one.

---

## 0. Sources

1. **Slice 7 plan** (`SLICE_7_PLAN.md`, revision 27): G7-2 (ii) (the relay's
   four duties, the envelope mapping, the header, R-1's seven duties), G7-3,
   G7-5, G7-15, §3.9.
2. **TURAB's code at `b52bd58`**, read for the boundary the relay must meet:
   - `services/webhooks.py`: `BODY_LIMIT`, `SIGNATURE_HEADER`,
     `REQUIRED_KEYS`, `STATUSES`, `_ORDER`, `_accepted`;
   - `services/communication.py`: `SCOPED`, the pattern a WHATSAPP
     `thread_ref` must match (`^[^:]+:[^:]+$`).
3. **Meta's official documentation, retrieved for this plan:**
   `evidence/R1-META-SOURCES.txt` holds each page's URL, its final URL, its
   status and sha256, and **27 excerpts quoted verbatim** (E1–E27). Each
   excerpt was checked against the extracted text before it was written.
   - **This settles the limit of Slice 7's §3.9.** That section rested on the
     reviewer's citation, because this environment could not resolve
     `developers.facebook.com` then. The three facts it cited are now
     confirmed from the pages themselves: the GET (E1–E4), the
     `X-Hub-Signature-256` (E5, E6), and `object` with `entry[].changes[]`
     (E18, E24–E26).
   - **Meta's pages change.** The plan cites the excerpts as retrieved; a
     later reader compares them against the live pages.

## 1. What Meta requires, verified

| # | Requirement | Excerpt | Consequence for the relay |
|---|---|---|---|
| M1 | A valid TLS certificate; self-signed not supported | E10 | the relay's public endpoint is HTTPS with a CA-issued certificate |
| M2 | Setting or editing the Callback URL or Verify token makes Meta send a GET with `hub.mode`, `hub.challenge`, `hub.verify_token` | E1 | duty 1 |
| M3 | The GET is valid when `hub.verify_token` equals the stored string; answer 200 with `hub.challenge`; otherwise anything but 200 | E2, E3 | duty 1 |
| M4 | **Meta begins sending webhooks only once the GET is answered with 200 and the challenge; otherwise none are sent** | E4 | **the first barrier of §4** |
| M5 | POSTs carry `X-Hub-Signature-256: sha256=<hash>`, an HMAC-SHA256 of the payload with the app secret | E5, E6 | duty 2 |
| M6 | A POST batches up to 1000 updates | E7 | duty 3: one POST, many envelopes |
| M7 | A failed POST is retried immediately, then with decreasing frequency, for up to 7 days; duplicates occur; unacknowledged deliveries are dropped after 7 days | E8, E9, E12, E13 | duty 5; §2 R1-F6 |
| M8 | Payloads can be up to 3 MB | E11 | §2 R1-F1 |
| M9 | mTLS is supported (client certificate CN `client.webhooks.fbclientcerts.com`) | E14, E17 | §5 R1-D10 |
| M10 | Some webhooks are not sent while the app is in Dev mode | E15 | not a barrier (§4) |
| M11 | Incoming messages carry `messages`; statuses carry `statuses`; up to three statuses per outgoing message; `delivered` is skipped when a message is read at once | E18, E19, E21 | duty 3 |
| M12 | Statuses include `played` (a voice message's first play) | E22 | §2 R1-F2 |
| M13 | A status of a group message carries the group's ID in `recipient_id`, and the user in `recipient_participant_id` | E23 | §2 R1-F4 |
| M14 | Unsupported incoming messages have `type` `unsupported` | E20 | §2 R1-F5 |
| M15 | The business number's ID is `metadata.phone_number_id`; the customer is `messages[].from` (incoming) and `statuses[].recipient_id` (statuses) | E24, E25, E26 | duty 6 |

**A divergence in Meta's own pages:** the WhatsApp pages state retries for
up to **7 days** (E8, E12); the general Graph API page states **36 hours**
(E16). This plan relies on the WhatsApp pages, which are specific to the
product, and states both.

**Not found in the pages read, and not claimed:**
- a time limit for the endpoint's answer;
- a rule on how the signed bytes are encoded beyond "the JSON payload as the
  message input" (E6). The relay checks the signature over the raw bytes it
  received, never over a re-serialized body.

## 2. Gaps between Meta and TURAB (findings)

| # | Finding | Source | Where it is settled |
|---|---|---|---|
| R1-F1 | Meta's payload can reach 3 MB; TURAB refuses a body over 64 KiB. The 64 KiB limit applies to **each envelope** the relay sends, not to Meta's request to the relay | M8; G7-15 | duty 7; R1-D4 (the relay's own inbound limit) |
| R1-F2 | `played` has no TURAB status (`STATUSES`: QUEUED, SENT, DELIVERED, READ, FAILED, UNKNOWN) | M12 | R1-D5 |
| R1-F3 | `delivered` may never come; TURAB's `_ORDER` accepts any forward move (`SENT` → `READ`), so this is **consistent with G7-5**, not a gap | M11; `_accepted` | stated; tested (R1-T3.6) |
| R1-F4 | A group's status names the group, not a customer: `<phone_number_id>:<group id>` would make a thread per group | M13 | R1-D7 |
| R1-F5 | TURAB stores `message_type` as free text; Meta's types include `unsupported`. Without a mapping, any string Meta sends becomes a stored type, including one that collides with an internal type's meaning | M14; schema `message_type text` | R1-D6 |
| R1-F6 | Meta retries a failed POST **whole**, up to 7 days; a POST may hold several events. A partly failed batch is therefore redelivered whole. TURAB's replay rule (S42: a completed event is 200 and writes nothing) makes that safe for TURAB | M6, M7; Slice 7 J01, S42 | R1-D2 |
| R1-F7 | Retried statuses: whether Meta keeps a status's `timestamp` on a retry is **not documented** in the pages read. If it changes, the same status yields a new `provider_event_id`; TURAB then refuses the repeated status by G7-5 (the same status is not accepted), so no state changes | M7; G7-5 | stated; tested (R1-T5.5) |
| R1-F8 | The relay handles message content (`text.body`) in transit. Slice 7's J03 binds TURAB, not the relay | Slice 7 J03 | R1-D9 |
| R1-F9 | For an incoming message, the customer appears in `messages[].from` and in `contacts[].wa_id`; Meta's example shows them equal, and the pages read do not state that they always are | M15 | R1-D8 |

## 3. The seven duties, and their acceptance tests

Every test runs on **synthetic** notifications built from the documented
structures (E18–E26), signed with a **test** app secret. None uses Meta's
servers, a real number or a real customer. Each duty's test names a
**refusal** where the duty is a guard: the relay's output is checked, and
so is what it does **not** forward.

### Duty 1 — Meta's GET verification (M2–M4)

| Test | Input | Expected |
|---|---|---|
| R1-T1.1 | `hub.mode=subscribe`, the right token, a challenge | 200; the body is exactly the challenge |
| R1-T1.2 | a wrong token | not 200 (R1-D11 fixes the code); no challenge in the body |
| R1-T1.3 | no token; no challenge; a mode other than `subscribe` | not 200 |
| R1-T1.4 | the verify token absent from the relay's environment | not 200 for any request: **fails closed** |
| R1-T1.5 | the comparison | constant-time (`hmac.compare_digest` or its equivalent), shown by a mutation that makes it `==` being killed by a test of equal-length tokens differing in the last byte |

### Duty 2 — Meta's `X-Hub-Signature-256` (M5)

| Test | Input | Expected |
|---|---|---|
| R1-T2.1 | a payload signed with the test app secret | accepted |
| R1-T2.2 | no header; a header without `sha256=`; a non-hex or short hash | refused **before parsing**: no JSON parse, no envelope, nothing sent to TURAB |
| R1-T2.3 | a valid signature over different bytes (one byte changed) | refused, nothing sent |
| R1-T2.4 | the same JSON re-serialized (whitespace, key order) under the original signature | refused: the HMAC is over the raw bytes |
| R1-T2.5 | the app secret absent | every POST refused: **fails closed** |
| R1-T2.6 | a body over the relay's inbound limit (R1-D4) | refused without reading it whole |
| R1-T2.7 | any refusal | the log names the refusal and the trace, **never the body or a header's value** |

### Duty 3 — the transformation, one envelope per message and per status (M6, M11)

| Test | Input | Expected |
|---|---|---|
| R1-T3.1 | one text message | one envelope: `provider_event_id` `message:<wamid>`, `event_type` `message`, `payload` with `external_message_ref` (the wamid), `thread_ref` (duty 6), `occurred_at` (RFC 3339, UTC, from the Unix `timestamp`), `message_type` (R1-D6), `body_text` |
| R1-T3.2 | one status | one envelope: `status:<wamid>:<status>:<timestamp>`, `event_type` `status`, `payload` with `external_message_ref`, `status` (R1-D5), `occurred_at` |
| R1-T3.3 | one POST with several `entry`, several `changes`, mixed messages and statuses | exactly one envelope per message and per status, none lost, none doubled |
| R1-T3.4 | a `field` other than `messages`; an `object` other than `whatsapp_business_account` | no envelope (R1-D12) |
| R1-T3.5 | `unsupported` messages; `errors` arrays | as R1-D6 decides; never a stored body from an error |
| R1-T3.6 | `sent` then `read`, with no `delivered` | two envelopes, which TURAB accepts in order (R1-F3) |
| R1-T3.7 | **each envelope the relay produces, given to TURAB's own `parse_envelope`** | accepted: the relay's output is a valid envelope by TURAB's code, not by a copy of its rules |

### Duty 4 — the relay's own signature (G7-2 (ii) 4)

| Test | Input | Expected |
|---|---|---|
| R1-T4.1 | an envelope the relay sends | `X-Turab-Relay-Signature: sha256=<hex>`, the HMAC-SHA256 of **the exact bytes sent**, with the relay's key |
| R1-T4.2 | **TURAB's own `verify`**, given those bytes and that header | true. With another key: false |
| R1-T4.3 | the relay's key equal to Meta's app secret | the relay refuses to start (the keys are distinct by G7-2 (ii)) |
| R1-T4.4 | the relay's key absent | the relay sends nothing (fails closed) |

### Duty 5 — redelivery of what TURAB did not complete (G7-2 (ii) 5; CORRECTION-007, -008)

| Test | TURAB's answer (a test double of TURAB, and TURAB's real app in R1-T5.6) | Expected (under R1-D2 (a)) |
|---|---|---|
| R1-T5.1 | 200 for every envelope of the POST | the relay answers Meta 200 |
| R1-T5.2 | a 500 for one envelope | the relay answers Meta **not 200**, so Meta retries the POST whole (M7) |
| R1-T5.3 | a 503 for one envelope | the same |
| R1-T5.4 | no answer within the relay's timeout (R1-D2) | the same |
| R1-T5.5 | the retried POST, after the first attempt completed some envelopes | TURAB answers 200 for the completed ones and writes nothing (S42); the incomplete ones are completed once (J01); a repeated status changes nothing (R1-F7) |
| R1-T5.6 | the same as R1-T5.2 and R1-T5.5, **against TURAB's real application and test database** | one event, one message and one interaction per message, as Slice 7's mandatory test 1 states |
| R1-T5.7 | a 400 or a 401 from TURAB | as R1-D3 decides; logged without the body |

### Duty 6 — the scope of `thread_ref` (G7-2 (ii) 6; M15)

| Test | Input | Expected |
|---|---|---|
| R1-T6.1 | an incoming message | `thread_ref` = `<metadata.phone_number_id>:<the customer's id>` (R1-D8 fixes the field) |
| R1-T6.2 | a status | `<metadata.phone_number_id>:<recipient_id>` |
| R1-T6.3 | the same customer writing to two business numbers | two different `thread_ref`s |
| R1-T6.4 | every `thread_ref` produced | matches TURAB's `SCOPED` (`^[^:]+:[^:]+$`): exactly one colon |
| R1-T6.5 | an identifier containing `:`; an empty identifier | no envelope (it could not be scoped) |
| R1-T6.6 | a group status (`recipient_type` `group`) | as R1-D7 decides |

### Duty 7 — the size of the relay's envelopes (G7-15; R1-F1)

| Test | Input | Expected |
|---|---|---|
| R1-T7.1 | for each message type the relay forwards (R1-D6), a synthetic message at the documented maximum of each field the envelope carries | the envelope's bytes ≤ 64 KiB, **measured and recorded** per type |
| R1-T7.2 | a field over its documented maximum | the relay's behaviour as R1-D4 decides; never an envelope over 64 KiB sent to TURAB |
| R1-T7.3 | the real envelopes | **not measurable before real traffic.** R1-D13 decides what stands in for them |

**Not tested by R-1, and not claimed:** Meta's delivery itself, Meta's
retries, and Meta's certificate. They are Meta's behaviour, documented (§1),
not proven by synthetic tests.

## 4. How real events stay blocked until R-1 passes

**Four barriers, each sufficient on its own to stop a real event reaching
TURAB's database. None is lifted by this plan.**

| # | Barrier | Holds because | Evidence |
|---|---|---|---|
| B1 | **No verified callback URL at Meta** | Meta sends webhooks only after the GET is answered with 200 and the challenge (M4, E4). No relay is deployed, so no endpoint can answer it, and no verify token exists | Meta's documentation (E4) |
| B2 | **No relay key in TURAB's environment** | without `TURAB_RELAY_SIGNING_SECRET`, TURAB answers every delivery 503 `WEBHOOK_NOT_READY` and writes nothing (CORRECTION-008) | Slice 7: `test_ii_a_missing_or_empty_secret_is_503_with_no_event_row` |
| B3 | **TURAB's webhook route not exposed** to Meta's or the relay's traffic | G7-2 (ii): an operational condition, stated, not a code switch | none in code; R1-D14 |
| B4 | **Meta's app not subscribed to the `messages` field** | the fields to subscribe to appear only once the URL's GET is answered properly (E27), and Meta sends webhooks only after verification (E4) | Meta's documentation |

**Not a barrier:** Meta's Dev mode. Meta says *some* webhooks are not sent
in Dev mode (E15), not all.

**The order in which they may be lifted, after R-1 is reviewed and closed,
each step a decision of its own:**
1. the review closes R-1;
2. the relay's key is created, and set in the relay and in TURAB, in a
   **non-production** environment first (R1-D13);
3. the relay is deployed behind TLS (M1), with mTLS if R1-D10 decides it;
4. the callback URL and the verify token are set at Meta, and the GET
   verified (M4);
5. the `messages` field is subscribed (B4);
6. the first real event.

**How a breach would be seen:** before step 6, **TURAB's
`webhook_events` holds no row in any non-test database.** R1-D14 decides
whether that is checked by an operator command, counts only, as Slice 7's
sample tool reads them.

## 5. Open decisions (none is taken here; a recommendation is not a decision)

| # | Decision | Options | Recommended, and why |
|---|---|---|---|
| R1-D1 | **Where the relay lives** | (a) a separate component in this repository (`relay/`), its own tests in the same suite; (b) a separate repository; (c) a managed function | **(a)**: R1-T3.7, R1-T4.2 and R1-T5.6 run the relay's output through **TURAB's own code**, which (b) and (c) would replace by a copy |
| R1-D2 | **The delivery model** | (a) **synchronous**: the relay answers Meta 200 only after every envelope of the POST got 200 from TURAB, otherwise not 200, and Meta redelivers (M7); a timeout of its own per envelope; (b) **store and forward**: the relay persists the notification, answers 200, and redelivers itself | **(a)**: the relay stores no content (R1-F8), and Meta's 7-day redelivery plus TURAB's replay rule (S42, J01) give at-least-once delivery without a second store. **Its limit:** after 7 days without success, Meta drops the delivery (E9) |
| R1-D3 | **TURAB's 400 or 401 to the relay** | (a) not 200 to Meta, and an alert; (b) 200 to Meta, the envelope dropped, and an alert | **(a)**: a 400 is a relay defect and a 401 a key mismatch; neither should be acknowledged as delivered. Meta's 7-day limit bounds the retries |
| R1-D4 | **The relay's inbound limit, and an oversize field** | (a) 3 MiB (3 × 2²⁰ bytes, at least Meta's "3 MB" under either reading), refused before reading; (b) Meta's figure read as 3 × 10⁶; an oversize envelope: (i) refused, not 200 to Meta; (ii) sent without its content | **(a) and (i)**: never truncate content silently |
| R1-D5 | **`played`** | (a) no envelope, counted; (b) an envelope with a TURAB status | **(a)**: TURAB has no status for it, and Slice 7 does not widen `STATUSES` |
| R1-D6 | **The message types forwarded** | (a) an allow-list of Meta types, each mapped to a stored value; any other type forwarded as one fixed value without content; (b) Meta's `type` passed through as is | **(a)**: no stored type ever comes from outside the list (R1-F5) |
| R1-D7 | **Group messages** | (a) no envelope, counted; (b) a thread per group | **(a)**: Slice 7 has no group model, and the scope is SALE only |
| R1-D8 | **The customer's identifier in an incoming message** | (a) `messages[].from`; (b) `contacts[].wa_id`; (c) both, refused when they differ | **(c)**: Meta's pages do not state they are always equal (R1-F9); a disagreement is refused, not guessed |
| R1-D9 | **Content in the relay** | the relay forwards `text.body` and a media identifier only; holds them in memory for the request; never logs or persists them | as stated: J03's rule extended to the relay. **Retention is not claimed** (OQ7-1) |
| R1-D10 | **mTLS** | (a) required, the client certificate's CN checked (E17); (b) not used | **(a)**, as defence in depth beside the signature; Meta says it is supported (E14) |
| R1-D11 | **The relay's refusal codes** | the status codes of the GET's and the POST's refusals | 403 for a wrong token, 401 for a signature, 413 for size; all "not 200" for Meta (E3) |
| R1-D12 | **Fields and objects other than `messages` on `whatsapp_business_account`** | (a) acknowledged 200, no envelope, counted; (b) not 200 | **(a)**: they are not TURAB's; refusing them would make Meta retry them for 7 days |
| R1-D13 | **What stands in for real envelopes before real traffic (duty 7)** | (a) synthetic envelopes at documented maxima only; (b) also Meta's test payloads (App Dashboard) to a **non-production** relay and TURAB, after the reviewer authorizes it | **(a)** for R-1's closure; **(b)** only as a separate, explicit authorization, since it is traffic from Meta |
| R1-D14 | **B3, and the breach check** | (a) B3 stays operational, with an operator command counting `webhook_events` rows (counts only); (b) a code switch refusing the route until an R-1 record is present | **(a)**, as G7-2 (ii) states; (b) would change TURAB's closed code |
| R1-D15 | **How R-1 is closed** | the relay's tests and mutations, bound to a clean-tree run as Slice 7's evidence is; a closure record; the reviewer's decision | as stated |

## 6. Sequence (none of it authorized by this plan)

| Step | Content | Depends on |
|---|---|---|
| 0 | the decisions R1-D1 to R1-D15 | the review of this plan |
| 1 | duties 1 and 2 (the GET; Meta's signature; the inbound limit), with their refusals | step 0 |
| 2 | duties 3, 4 and 6 (the transformation; the relay's signature; `thread_ref`), checked by TURAB's own `parse_envelope` and `verify` | step 1 |
| 3 | duty 5 (redelivery), against a test double and against TURAB's real application and test database | step 2 |
| 4 | duty 7 (the envelopes' sizes), measured and recorded; R-1's evidence and closure record | step 3 |

Each step is delivered with its tests and its mutation record, and reviewed
before the next. A defect found is measured before it is fixed. **Lifting a
barrier of §4 is not a step of this plan.**

## 7. R-1's acceptance conditions

1. Each of the seven duties is proven by the tests of §3, every one
   passing, on synthetic notifications only.
2. The relay's output is accepted by **TURAB's own** envelope parser and
   signature check (R1-T3.7, R1-T4.2), and its redelivery is shown against
   TURAB's real application (R1-T5.6).
3. Every guard fails closed: no token, no secret, no key (R1-T1.4, R1-T2.5,
   R1-T4.4).
4. No content in any log of the relay (R1-T2.7, R1-D9).
5. Each mutation of the relay's guards is killed, in two identical runs.
6. The four barriers of §4 still hold when R-1 is closed; lifting them is
   decided separately.
7. **K06 UNPROVEN, SALE only.** Not a release authorization.

## 8. What this plan does not do

- write code, create a secret or a verify token, or configure Meta's app;
- deploy anything, expose any route, or receive any event;
- change TURAB's webhook, contract or tests;
- prove Meta's behaviour: §1 is Meta's documentation, retrieved and quoted,
  not a test result;
- touch K06, which stays an independent condition before the release gate.

## 9. Document identity

This file's sha256 is recorded in `docs/gate/evidence/DOCUMENT-HASHES.txt`
at the commit that adds it.
