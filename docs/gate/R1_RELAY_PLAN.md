# R-1 — The relay between Meta and TURAB's webhook
## Plan — **revision 6**

**Status: revision 2 ADOPTED; step 1 AUTHORIZED** (review of `3d8b593`,
recorded below), within its stated scope: Meta's GET, the verification of
Meta's signature, the inbound limit, and the synthetic mTLS tests.
- **Revision 1 was accepted as the basis for implementation** in the review
  of `1d00f41`, which adopted the recommended options of R1-D1 to R1-D15
  with binding specifications (§5).
- **R1-Q1 is decided: (a)** (§5.4).
- **Step 2 is delivered and NOT closed** (review of `ced7df7`, recorded
  below): the document order of R1-T3.3 was not kept inside one `value`.
  Step 3 is not authorized before the review of the correction.
- **Step 1 is CLOSED at `e9fac51`, and step 2 is AUTHORIZED** (review of
  `e9fac51`, recorded below): the transformation of Meta's notifications,
  the signing of the relay's envelopes, and `thread_ref`, tested with
  TURAB's own code.
- **The run entry point's access log is a binding condition** (§5.5,
  decided in the review of `8c64c64`).
- **Step 1's authorization does not allow** deploying the relay, creating a
  secret, or receiving any real event. Steps 3 and 4 are not authorized.
- **No relay** is deployed. **No secret, verify token or Meta app setting** is created.
  **No real event** is received. R-1 stays **UNMET**: **no real event may be
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
does not touch it. The next slice's plan follows the review of this one.

**Revision history**

| rev | commit | what changed |
|---|---|---|
| 1 | `1d00f41` | first plan, planning only |
| 6 | the commit that adds this revision | the review of `ced7df7` recorded: step 2 not closed (document order inside one `value`); R1-T3.3 made explicit; the undocumented status's reading accepted |
| 5 | `a562c25` | the review of `e9fac51` recorded: step 1 CLOSED; step 2 authorized |
| 4 | `00134ee` | the review of `8c64c64` recorded: step 1 not closed (the fingerprint did not cover `pyproject.toml`); the access-log condition decided (§5.5), in §4's order and §7 |
| 3 | `c601c25` | the review of `3d8b593` recorded: revision 2 adopted; step 1 authorized; R1-Q1 decided (a), §5.4 and R1-T7.2 set to it, with an OVERSIZE class in §5.1; R1-D8's reading accepted; §5.1's checks made explicit per element kind; R1-T1.5's count bounded to the requests that reach the comparison |
| 2 | `878745e` | the review of `1d00f41` recorded: R1-D1 to R1-D15 adopted as recommended, with binding specifications (R1-D8 and batches, R1-D10, R1-D14); R1-T1.5 and R1-T7 corrected; R1-D6's mapping table; one point found while writing it (R1-Q1), not decided |

---

## The review of `ced7df7`

**Step 2 is NOT closed at `ced7df7`.**

- **The reading of an undocumented status is accepted:** it is classed
  ISOLATED with `STATUS_NOT_KNOWN`, with no envelope or content, and is
  counted and alerted on in step 3.
- **The gap: R1-T3.3's "document order".** When `statuses` come before
  `messages` inside one `value`, the transformation always emits the
  messages first. The current test builds its keys in the order `messages`
  then `statuses`, so it cannot tell the two behaviours apart.
- **Asked:** pin an inverted case that shows the failure on the current
  code; then keep the elements in the order they came; then rebind the
  evidence to the corrected tree.
- **What the reviewer checked:** the source, and the two mutation records:
  29/29 killed, with identical test results once the run times are set
  aside. That the remote branch's head is `ced7df7`.
- **What it did not do:** re-run the suite, the mutations or the PostgreSQL
  gate; check the local tree's cleanliness.
- **Standing:** step 3 not authorized until the correction is reviewed;
  R-1 UNMET, no real events; K06 an independent condition before the
  release; SALE only.

## The review of `e9fac51`

**Step 1 is CLOSED at `e9fac51`. Step 2 is AUTHORIZED, within the approved
plan:** the transformation of Meta's notifications, the signing of the
relay's envelopes, and the building of `thread_ref`, tested with TURAB's own
code. **The authorization does not include** deploying the relay, creating
secrets, or receiving any real event.

- **What the reviewer checked:** the fingerprint's recipe, which now holds
  `pyproject.toml` and the pytest configuration files that may take
  precedence over it, a list and an order that agree with pytest's
  documentation; the isolated-copy test, which starts from an accepted
  binding and then proves the refusal after a changed setting or an added
  file; the two mutation records, each listing 28 mutations with none
  surviving and the same counts per mutation; and that the diff from their
  run tree, `7502961`, to `e9fac51` changes no source, test or pytest
  configuration.
- **What it did not do:** re-run the suite (3250/3250), the mutations, the
  PostgreSQL gate or `run_binding`. These are the implementing team's
  results. The tree's binding stays limited to what the delivery note
  states; it covers neither the packages' environment nor the database
  software.
- **The access-log condition stands** before any deployment or Callback
  setting: tested **through the actual run entry point and every layer in
  front of it**, since the current test server proves its own configuration
  only (§5.5).
- **Standing:** R-1 UNMET; K06 an independent condition before the release
  gate; SALE only.

## The review of `8c64c64`

**Step 1 stays delivered for review; it is NOT closed.** The reviewer read
the code and the delivery note at `8c64c64`. The remote head is at that
commit; the reviewer did not check the local tree's cleanliness, and did not
re-run the 3239 tests, the mutations or the gate.

**The blocker:** the evidence's fingerprint does not cover a setting the
step changed. `relay` was added to `pyproject.toml`'s `pythonpath`, but
`source_fingerprint.py` does not collect that file, and `run_binding.py`
compares the fingerprint alone against the current tree. So, reasoning from
the code, a later commit could change how the relay's tests are collected
while `bound` stays. This does not deny the run's result on `8c64c64`'s
tree; it limits what the binding check proves.

| # | Asked to close step 1 |
|---|---|
| 1 | add `pyproject.toml` to the fingerprint's recipe, and update the description of its limits in the run record |
| 2 | a test that changes `pythonpath` in an isolated copy, and proves the binding check refuses it |
| 3 | the evidence round again on the corrected tree, with the mutation records attributed exactly to the tree each ran on |

**Decided: the access log** (§5.5). A binding condition of the relay's run
entry point, before any deployment or Callback setting: the logging of the
request line is disabled, or its query removed, in the HTTP server and in
every layer in front of it, and this is tested through the actual run entry
point. The current test server's `access_log=False` does not prove the
configuration of an entry point not yet built. *(Uvicorn documents disabling
its access log in its settings; the reviewer's citation.)*

- **The reviewer's reading confirms:** a correctly signed POST is answered
  503 now, so no undelivered event is acknowledged; the mTLS tests use
  synthetic certificates, and are not a test of Meta's real certificate.
- **Standing:** R-1 UNMET, no real events; K06 an independent condition
  before the release; SALE only.

## The review of `3d8b593`

**Revision 2 is adopted. Step 1 is authorized, within its stated scope:
Meta's GET, the verification of Meta's signature, the inbound limit, and
the synthetic mTLS tests.** The diff since revision 1 is documentary. This
does not authorize deploying the relay, creating secrets, or receiving real
events.

| # | Decision or request | Recorded in |
|---|---|---|
| 1 | **R1-Q1: option (a).** Meta's answer stays not 200 for an envelope over 65 536 bytes. That envelope is not sent to TURAB and its content is not shortened; an alert is raised, without the message's content. The redelivery of the elements already delivered is tested to write nothing a second time. *The reviewer's reason:* to keep the redelivery window open, so a size or mapping policy can be fixed; a 200 would remove that possibility at once. *The reviewer's note:* the "up to 7 days" comes from our record of the WhatsApp pages' excerpts; the reviewer could not confirm it from Meta's live page | §5.4; §5.1 (the OVERSIZE class); R1-T7.2 |
| 2 | **R1-D8's reading of `contacts` is accepted:** `messages[].from` is used; it suffices that it matches one `wa_id` when several are present; the absence of `contacts` alone does not isolate a message | §5.1 |
| 3 | **Before step 2:** make §5.1's classification explicit by element kind. The `from` condition belongs to a message; a status is checked on `recipient_id` and its own required fields. The wording "`from` missing" in ISOLATED could be read against every status | §5.1 (done in this revision) |
| 4 | **R1-T1.5:** the call-path check kills the `==` mutation, with the result tests kept separate. Bound "once per GET" to the requests that actually reach a comparison of two tokens; a request without a token fails before it | §3, R1-T1.5 |

- **What the reviewer did not do:** run tests or a migration, or verify
  independently that Meta's excerpts match their pages.
- **Standing:** R-1 UNMET until its seven duties are delivered and its
  closure reviewed; K06 an independent condition before the release gate;
  SALE only.

## The review of `1d00f41`

**Revision 1 is accepted as the basis for implementation. Step 1 is not
authorized before a second review of the points below.** The diff since
`b52bd58` is documentary only.

**The decisions R1-D1 to R1-D15:** the recommended options are adopted,
with these binding specifications:

| # | Specification |
|---|---|
| 1 | **R1-D8 and batches.** The sender's identifier is taken from `messages[].from`. If `contacts[].wa_id` is present, it must match; its absence alone does not refuse the message. An element whose two identifiers differ is isolated, counted and alerted on, **without forwarding its content**. The plan must state that dropping an element classified this way does not make a batch holding valid elements be redelivered whole, while a failure to deliver a valid element to TURAB keeps Meta's answer not 200, under R1-D2 |
| 2 | **R1-D10.** mTLS means verifying the client certificate, its chain of trust and the decided identity, not checking the CN's text alone. It is proven by refusal tests for an untrusted or a mismatched certificate |
| 3 | **R1-D14.** The operational barrier with the count check is accepted, but it is presented as a **configuration state measured at closure**. The absence of a `messages` subscription blocks that field's events only: B4 may not be described as blocking every real event if the app subscribes other fields. Meta's documentation does not by itself prove the state of the app's configuration or of TURAB's environment |

**Two acceptance conditions corrected:**
- **R1-T1.5:** two different tokens are refused by both `compare_digest` and
  `==`, so that test does not kill the mutation described. The use of the
  constant-time comparison is to be proven by checking the call path, or by
  a tool that observes it, with the behavioural accept and refuse tests kept;
- **R1-T7.1 and R1-T7.2:** the sources record states no maximum per field of
  the envelope. Name the limits that have a basis; test the serialized
  bytes' size at 64 KiB and above it, including UTF-8, escaped characters
  and a batch of several elements. No undocumented limit is attributed to
  Meta.

**What the reviewer did not verify:** the five Meta pages were not
re-fetched. Direct access returned 429 or a sign-in page. **The excerpts'
match with the pages remains our recorded check, not an independent
verification.**

**Asked:** revision 2 of this plan only, with these decisions and **R1-D6's
specific mapping table**. Step 1 may begin after its review.

**Standing:** R-1 UNMET, no real events; K06 an independent condition before
the release gate; SALE only.

**Answered in this revision:** §5.1 (the batch rule, R1-D8), §5.2 (R1-D10),
§4 (R1-D14, the barriers as measured state), §5.3 (R1-D6's table), §3
(R1-T1.5, R1-T2.8, R1-T7), §5.4 (R1-Q1).

---

## 0. Sources

1. **Slice 7 plan** (`SLICE_7_PLAN.md`, revision 27): G7-2 (ii), G7-3,
   G7-5, G7-15, §3.9.
2. **TURAB's code at `b52bd58`**, read for the boundary the relay must meet:
   - `services/webhooks.py`: `BODY_LIMIT` (64 × 1024), `SIGNATURE_HEADER`,
     `REQUIRED_KEYS`, `STATUSES`, `_ORDER`, `_accepted`, `verify`,
     `parse_envelope`;
   - `api/routes/webhooks.py`: the body is refused when `size >
     BODY_LIMIT`, so **65 536 bytes pass and 65 537 do not**;
   - `services/communication.py`: `SCOPED` (`^[^:]+:[^:]+$`), and the
     internal types `PHONE_DECISION` and `CONFIRMATION_LINK`;
   - the contract: `message_type` is a string, default `TEXT`; the column is
     `message_type text NOT NULL DEFAULT 'TEXT'`, with no check.
3. **Meta's official documentation:** `evidence/R1-META-SOURCES.txt`.
   - **First retrieval** (for revision 1): five pages, E1–E27.
   - **Second retrieval** (2026-10-29, for this revision): the eighteen
     message-type reference pages in Meta's Markdown form, E28–E59; and
     three mTLS excerpts from the first retrieval's Graph API page,
     E53–E55.
   - Each page's sha256 is recorded, and **each excerpt was checked against
     the page's extracted text before it was written.** As the review of
     `1d00f41` states, that check is ours: the reviewer could not re-fetch
     the pages (429, or a sign-in page).
4. **Python's documentation** for `hmac.compare_digest` (P1–P3, same
   record): its constant-time approach (P1); `str` arguments must be ASCII,
   otherwise bytes (P2); and, for arguments of different lengths, a timing
   attack could reveal their types and lengths, not their values (P3).

## 1. What Meta requires, verified

| # | Requirement | Excerpt | Consequence for the relay |
|---|---|---|---|
| M1 | A valid TLS certificate; self-signed not supported | E10 | HTTPS with a CA-issued certificate |
| M2 | Setting or editing the Callback URL or Verify token makes Meta send a GET with `hub.mode`, `hub.challenge`, `hub.verify_token` | E1 | duty 1 |
| M3 | The GET is valid when `hub.verify_token` equals the stored string; answer 200 with `hub.challenge`; otherwise anything but 200 | E2, E3 | duty 1 |
| M4 | Meta begins sending webhooks only once the GET is answered with 200 and the challenge; otherwise none are sent | E4 | barrier B1 (§4) |
| M5 | POSTs carry `X-Hub-Signature-256: sha256=<hash>`, an HMAC-SHA256 of the payload with the app secret | E5, E6 | duty 2 |
| M6 | A POST batches up to 1000 updates | E7 | duty 3; §5.1 |
| M7 | A failed POST is retried immediately, then with decreasing frequency, for up to 7 days; duplicates occur; dropped after 7 days | E8, E9, E12, E13 | duty 5; §5.1 |
| M8 | Payloads can be up to 3 MB | E11 | R1-D4 |
| M9 | mTLS: trust Meta's outbound API CA certificate (`meta-outbound-api-ca-2025-12.pem`); verify the client certificate against it; verify its common name `client.webhooks.fbclientcerts.com` | E14, E17, E53, E54, E55 | R1-D10, §5.2 |
| M10 | Some webhooks are not sent while the app is in Dev mode | E15 | not a barrier |
| M11 | Incoming messages carry `messages`; statuses carry `statuses`; up to three statuses per outgoing message; `delivered` skipped when read at once | E18, E19, E21 | duty 3 |
| M12 | Statuses include `played` | E22 | R1-D5 |
| M13 | **Groups:** an incoming group message carries `messages[].group_id`; a status of a message sent to a group carries `"recipient_type": "group"`, the group's ID in `recipient_id` | E51, E52, E23 | R1-D7 |
| M14 | The message types documented, each with its literal `type` (E28, E30, E33, E35, E37, E40–E50), and their content fields: `text.body`; `caption` on image, video, document; `filename` on document; the media `id` on image, audio, video, document, sticker | E28–E50, E56–E59 | R1-D6, §5.3 |
| M15 | The business number's ID is `metadata.phone_number_id`; the customer is `messages[].from` (incoming) and `statuses[].recipient_id` (statuses) | E24, E25, E26 | duty 6; R1-D8 |
| M16 | The fields to subscribe to appear only once the URL's GET is answered properly | E27 | barrier B4 |

**A divergence in Meta's own pages:** retries for up to **7 days** in the
WhatsApp pages (E8, E12), **36 hours** in the general Graph API page (E16).
This plan relies on the WhatsApp pages, and states both.

**Not found in the pages read, and not claimed:**
- a time limit for the endpoint's answer;
- a rule on how the signed bytes are encoded beyond "the JSON payload as the
  message input" (E6). The relay checks the signature over the raw bytes it
  received, never over a re-serialized body;
- **a maximum size for any field** of a notification (a text's body, a
  caption, a file name). None is attributed to Meta here (§3, duty 7).

## 2. Gaps between Meta and TURAB (findings)

| # | Finding | Source | Where it is settled |
|---|---|---|---|
| R1-F1 | Meta's payload can reach 3 MB; TURAB refuses a body over 65 536 bytes. The 64 KiB limit applies to **each envelope**, not to Meta's request | M8; G7-15 | duty 7; R1-D4 |
| R1-F2 | `played` has no TURAB status | M12 | R1-D5 |
| R1-F3 | `delivered` may never come; TURAB's `_ORDER` accepts `SENT` → `READ`, so this is **consistent with G7-5** | M11; `_accepted` | R1-T3.6 |
| R1-F4 | Groups would make a thread per group | M13 | R1-D7 |
| R1-F5 | TURAB's `message_type` is free text; without a mapping, a type from outside could collide with an internal type's meaning | M14 | R1-D6, §5.3 |
| R1-F6 | Meta retries a failed POST **whole**; TURAB's replay rule (S42) makes that safe for TURAB | M6, M7 | §5.1 |
| R1-F7 | Whether Meta keeps a status's `timestamp` on a retry is not documented; if it changes, TURAB refuses the repeated status by G7-5 | M7; G7-5 | R1-T5.5 |
| R1-F8 | The relay handles content in transit; Slice 7's J03 binds TURAB, not the relay | J03 | R1-D9 |
| R1-F9 | The customer appears in `messages[].from` and `contacts[].wa_id`; Meta's pages do not state they are always equal | M15 | R1-D8, §5.1 |
| R1-F10 | **(New.)** Meta documents `edit` and `revoke` messages (E49, E50). TURAB's messages are append-only, with no edit or withdrawal. An edit's new content is not carried (§5.3); content archived before a revocation stays, as Slice 7's retention limit already states (OQ7-1) | E49, E50; Slice 7 §1 limit 4 | §5.3; stated as a limit |

## 3. The seven duties, and their acceptance tests

Every test runs on **synthetic** notifications built from the documented
structures, signed with a **test** app secret. None uses Meta's servers, a
real number or a real customer.

### Duty 1 — Meta's GET verification (M2–M4)

| Test | Input | Expected |
|---|---|---|
| R1-T1.1 | `hub.mode=subscribe`, the right token, a challenge | 200; the body is exactly the challenge |
| R1-T1.2 | a wrong token: of the same length, and of another length | 403 (R1-D11); no challenge in the body |
| R1-T1.3 | no token; no challenge; a mode other than `subscribe` | not 200 |
| R1-T1.4 | the verify token absent from the relay's environment | not 200 for any request: fails closed |
| R1-T1.5 | **(Corrected.)** the comparison's call path. The token received and the stored token, each encoded UTF-8, go through `hmac.compare_digest` (P1, P2). The test replaces `compare_digest` **in the relay's namespace** with a recording wrapper around the real function, and asserts it was called **exactly once for each GET that reaches the comparison** (the verify token configured, `hub.mode` `subscribe`, a challenge and a token present), with the two byte strings, for both a matching and a non-matching token; and **not at all** for a GET refused before it (no token, another mode, no challenge, no configured token). R1-T1.1 and R1-T1.2 stay as the behavioural tests | a mutation replacing the call by `==` is killed by the call-path test, since the wrapper is then never called. **What it does not prove:** the CPU's timing. That is Python's documented property (P1), with its stated limit for unequal lengths (P3) |

### Duty 2 — Meta's `X-Hub-Signature-256` (M5)

| Test | Input | Expected |
|---|---|---|
| R1-T2.1 | a payload signed with the test app secret | accepted |
| R1-T2.2 | no header; a header without `sha256=`; a non-hex or short hash | refused before parsing; nothing sent to TURAB |
| R1-T2.3 | a valid signature over different bytes | refused |
| R1-T2.4 | the same JSON re-serialized under the original signature | refused: the HMAC is over the raw bytes |
| R1-T2.5 | the app secret absent | every POST refused: fails closed |
| R1-T2.6 | a body over the relay's inbound limit (R1-D4: 3 MiB) | 413, without reading it whole |
| R1-T2.7 | any refusal | the log names the refusal and the trace, never the body or a header's value |
| R1-T2.8 | **(New, as R1-T1.5.)** the signature's comparison | goes through `hmac.compare_digest` on bytes, shown by the same call-path test |

### Duty 3 — the transformation, one envelope per message and per status (M6, M11, M14)

| Test | Input | Expected |
|---|---|---|
| R1-T3.1 | one text message | one envelope: `message:<wamid>`, `event_type` `message`, `external_message_ref`, `thread_ref` (duty 6), `occurred_at` (RFC 3339, UTC, from the Unix `timestamp`), `message_type` `TEXT`, `body_text` |
| R1-T3.2 | one status | one envelope: `status:<wamid>:<status>:<timestamp>`, `event_type` `status`, `external_message_ref`, `status` (R1-D5), `occurred_at` |
| R1-T3.3 | one POST with several `entry`, several `changes`, mixed messages and statuses; **and, inside one `value`, `statuses` before `messages`, and `errors` between them** (review of `ced7df7`) | one envelope per forwarded element, none lost, none doubled, **in the order the elements appear in the document**: the order of `entry`, of `changes`, and of the keys inside each `value`, not a fixed order of kinds |
| R1-T3.4 | a `field` other than `messages`; an `object` other than `whatsapp_business_account` | no envelope; counted (R1-D12) |
| R1-T3.5 | each Meta type of §5.3's table | the stored value and the content of §5.3, exactly; no content for any type the table gives none |
| R1-T3.6 | `sent` then `read`, with no `delivered` | two envelopes, which TURAB accepts in order |
| R1-T3.7 | each envelope the relay produces, given to **TURAB's own `parse_envelope`** | accepted |
| R1-T3.8 | **(New, §5.1.)** batches mixing forwarded, isolated and dropped elements | the answer to Meta as §5.1 states, in each case of its table |

### Duty 4 — the relay's own signature

| Test | Input | Expected |
|---|---|---|
| R1-T4.1 | an envelope the relay sends | `X-Turab-Relay-Signature: sha256=<hex>`, over the exact bytes sent |
| R1-T4.2 | **TURAB's own `verify`**, given those bytes and that header | true; with another key, false |
| R1-T4.3 | the relay's key equal to Meta's app secret | the relay refuses to start |
| R1-T4.4 | the relay's key absent | the relay sends nothing |

### Duty 5 — redelivery of what TURAB did not complete

| Test | TURAB's answer | Expected (R1-D2 (a), §5.1) |
|---|---|---|
| R1-T5.1 | 200 for every forwarded element | 200 to Meta |
| R1-T5.2 | a 500 for one forwarded element | not 200 to Meta |
| R1-T5.3 | a 503 for one forwarded element | not 200 to Meta |
| R1-T5.4 | no answer within the relay's timeout | not 200 to Meta |
| R1-T5.5 | the retried POST, after some elements completed | TURAB answers 200 for those and writes nothing (S42); the others are completed once (J01); a repeated status changes nothing (R1-F7) |
| R1-T5.6 | R1-T5.2 and R1-T5.5 against **TURAB's real application and test database** | one event, one message and one interaction per message |
| R1-T5.7 | a 400 or a 401 from TURAB | not 200 to Meta, and an alert (R1-D3 (a)); logged without the body |

### Duty 6 — the scope of `thread_ref` (M15, R1-D8)

| Test | Input | Expected |
|---|---|---|
| R1-T6.1 | an incoming message | `<metadata.phone_number_id>:<messages[].from>` |
| R1-T6.2 | a status | `<metadata.phone_number_id>:<recipient_id>` |
| R1-T6.3 | the same customer writing to two business numbers | two `thread_ref`s |
| R1-T6.4 | every `thread_ref` produced | matches TURAB's `SCOPED` |
| R1-T6.5 | an identifier containing `:`, or empty | isolated (§5.1) |
| R1-T6.6 | an incoming message with `group_id`; a status with `recipient_type` `group` | dropped, counted (R1-D7) |
| R1-T6.7 | **(New, R1-D8.)** `contacts` absent; `contacts` with a `wa_id` equal to `from`; `contacts` whose `wa_id` differs from `from` | forwarded; forwarded; **isolated**, counted, alerted, its content neither forwarded nor logged |

### Duty 7 — the size of the relay's envelopes (corrected)

**The limits that have a basis, and only those:**
- **TURAB's body limit:** `BODY_LIMIT` = 64 × 1024 = **65 536 bytes**, a
  body refused when larger (TURAB's code, §0);
- **Meta's payload:** up to **3 MB** (E11); the relay's inbound limit is
  **3 MiB** (R1-D4);
- **Meta's batch:** up to **1000 updates** per POST (E7).

**No maximum is attributed to any field.** The pages read state none (§1).
The envelope's size is therefore bounded by testing the **bytes the relay
actually sends**, not by an assumed field size.

| Test | Input | Expected |
|---|---|---|
| R1-T7.1 | an envelope whose serialized bytes are **exactly 65 536** | sent; **TURAB's real route accepts it** |
| R1-T7.2 | **(Set to R1-Q1 (a).)** content that makes one element's envelope **65 537** bytes, in a POST that also holds valid elements | that envelope is **not sent** to TURAB and **not shortened**; an alert is raised **without the message's content**; the valid elements are delivered; **Meta's answer is not 200**. On Meta's redelivery of the same POST, the delivered elements are 200 replays at TURAB that **write nothing a second time**, and the oversize element is OVERSIZE again |
| R1-T7.3 | content that crosses the limit only once serialized: 2-, 3- and 4-byte UTF-8 characters; characters JSON escapes (`"`, `\`, U+0000–U+001F) | the size measured is the serialized bytes, never the content's length; each case at 65 536 and 65 537 bytes |
| R1-T7.4 | a batch of several elements, each producing an envelope near the limit | each envelope measured on its own; none sent above 65 536 |
| R1-T7.5 | a POST at 3 MiB, and one byte above, holding many elements | the first accepted, the second 413 (R1-T2.6) |
| R1-T7.6 | each type of §5.3 that carries content | the envelope's bytes **without content** recorded per type: the room left for content, measured |
| R1-T7.7 | the real envelopes | not measurable before real traffic; synthetic only (R1-D13 (a)) |

## 4. How real events stay blocked until R-1 passes (corrected, R1-D14)

**Each barrier is a mechanism, and a state.**
- **The mechanism** is documented by Meta or proven by TURAB's tests.
- **The state** is a fact about Meta's app and the deployed environments.
  **This plan does not know it:** this repository has no deployment and no
  access to Meta's app, and Meta's documentation does not prove either's
  configuration.
- **The state is measured and recorded at R-1's closure.** It is not
  inferred from the documentation.

| # | Barrier | What it blocks | Mechanism | State to measure at closure |
|---|---|---|---|---|
| B1 | **No verified callback URL at Meta** | **every** webhook to that app's callback: Meta sends none before the GET succeeds (E4) | Meta's documentation (E4) | whether a callback URL is set and verified for the app, read from the App Dashboard by the app's operator |
| B2 | **No relay key in TURAB's environment** | every delivery to that TURAB: answered 503 `WEBHOOK_NOT_READY`, nothing written | Slice 7: `test_ii_a_missing_or_empty_secret_is_503_with_no_event_row` | whether `TURAB_RELAY_SIGNING_SECRET` is set in each deployed environment: presence only, never the value |
| B3 | **TURAB's webhook route not exposed** | traffic that cannot reach it | operational (G7-2 (ii)) | the route's exposure in each deployed environment, as the operator records it |
| B4 | **No subscription to the `messages` field** | **the `messages` field's events only.** If the app subscribes other fields, B4 does not block their events. Under R1-D12 they would produce no envelope, but that is the relay's behaviour, not a barrier | Meta's documentation (E27) | the list of fields the app subscribes to |

**The count check (R1-D14 (a)):** an operator command counts the rows of
`webhook_events` in each non-test database, **counts only**, as Slice 7's
sample tool reads them. The expected count before the first real event is
**zero**. Its result is part of the state measured at closure.

**Not a barrier:** Meta's Dev mode (E15: *some* webhooks are not sent).

**The order in which the barriers may be lifted, after R-1 is reviewed and
closed, each a decision of its own:**
1. the review closes R-1;
2. the relay's key is created, and set in the relay and in TURAB, in a
   non-production environment first;
3. the relay is deployed behind TLS (M1) and mTLS (R1-D10), **only through
   a run entry point that meets §5.5** (no request line with its query in any
   log), tested through that entry point;
4. the callback URL and verify token are set at Meta, and the GET verified;
5. the `messages` field is subscribed;
6. the first real event.

## 5. The decisions (adopted in the review of `1d00f41`), and their specifications

| # | Decision | Adopted |
|---|---|---|
| R1-D1 | Where the relay lives | (a): a separate component in this repository (`relay/`), its tests in the same suite |
| R1-D2 | The delivery model | (a): synchronous; 200 to Meta only as §5.1 states; a timeout per envelope; **its limit:** Meta drops a delivery after 7 days without success (E9) |
| R1-D3 | TURAB's 400 or 401 | (a): not 200 to Meta, and an alert |
| R1-D4 | The inbound limit; an oversize envelope | (a) 3 MiB; (i) an oversize envelope refused, never truncated. **See R1-Q1** |
| R1-D5 | `played` | (a): no envelope, counted |
| R1-D6 | The message types | (a): an allow-list; **§5.3** |
| R1-D7 | Groups | (a): no envelope, counted; recognised by `group_id` or `recipient_type` `group` (M13) |
| R1-D8 | The customer's identifier | **as specified in the review:** `from`, checked against `contacts[].wa_id` when present; §5.1 |
| R1-D9 | Content in the relay | forwarded as §5.3 states; held in memory for the request; never logged or persisted. Retention not claimed |
| R1-D10 | mTLS | (a), **as specified in the review:** §5.2 |
| R1-D11 | Refusal codes | 403 for a wrong token, 401 for a signature, 413 for size |
| R1-D12 | Other fields and objects | (a): 200, no envelope, counted |
| R1-D13 | Real envelopes before real traffic | (a): synthetic only; Meta's test payloads only under a separate, explicit authorization |
| R1-D14 | B3, and the breach check | (a), **as specified in the review:** §4 |
| R1-D15 | How R-1 is closed | tests and mutations bound to a clean-tree run; a closure record **with the barriers' measured state**; the reviewer's decision |

### 5.1 Each element's class, and the answer to Meta (R1-D2, R1-D8, the review's specification 1)

Each element of a POST is one message of `messages[]` or one status of
`statuses[]`, in one `change`. Each element is placed in exactly one class:

| Class | Which elements | What the relay does |
|---|---|---|
| **FORWARD** | an element of `field` `messages` that passes every check of its kind below | builds its envelope (§5.3), sends it to TURAB in document order |
| **ISOLATED** | an element that fails a check of **its kind** (below) | **no envelope; its content neither forwarded nor logged;** counted by reason; an alert |
| **DROPPED** | an element documented and decided out of scope: `played` (R1-D5); a group message or a group status (R1-D7); `value.errors` | no envelope; counted by reason |
| **OVERSIZE** | **(R1-Q1 (a).)** an element that passes every check, whose envelope's serialized bytes exceed 65 536 | **not sent, not shortened;** an alert without the message's content; **keeps the answer not 200** |

**The checks, by element kind** (each element is one kind, by the array it
comes from):

| Kind | Required, else ISOLATED | Also ISOLATED when |
|---|---|---|
| **a message** (`value.messages[]`) | `from`, `id`, `timestamp`, `type`; `value.metadata.phone_number_id` | `value.contacts` is present and `from` equals none of its `wa_id`s (R1-D8); `from` or `phone_number_id` empty, or containing `:` |
| **a status** (`value.statuses[]`) | `id`, `status`, `timestamp`, `recipient_id`; `value.metadata.phone_number_id` | `recipient_id` or `phone_number_id` empty, or containing `:`. **A status has no `from`, and is never checked for it**; nor against `contacts` |

**R1-D8, as accepted in the review of `3d8b593`:** `messages[].from` is the
sender's identifier. When `value.contacts` is present, `from` must equal at
least one of its `wa_id`s: with one entry, that entry's; with several, any
one of them. **The absence of `contacts` alone does not isolate a
message.**

**The answer to Meta for a POST:**

| Case | Answer |
|---|---|
| every FORWARD element got 200 from TURAB; ISOLATED and DROPPED elements present or not | **200** |
| at least one FORWARD element got a 500, a 503, no answer in time, a 400 or a 401 from TURAB | **not 200**: Meta redelivers the POST whole (M7). On that redelivery, the completed elements are 200 replays at TURAB (S42), and the ISOLATED and DROPPED elements are classed the same way again |
| at least one OVERSIZE element (R1-Q1 (a)) | **not 200**, whatever the FORWARD elements' answers: the redelivery window stays open (§5.4) |
| no FORWARD and no OVERSIZE element | **200** |

- **ISOLATED and DROPPED elements never make the answer not 200.** Their
  class is a function of the notification's bytes, so a redelivery cannot
  change it. Answering not 200 for them would make Meta redeliver a batch
  whose valid elements are already delivered, for nothing.
- **An OVERSIZE element always makes the answer not 200,** although its
  class is also fixed by the bytes. That is the reviewer's decision on
  R1-Q1, for a different end: to keep the redelivery window open while a
  size or mapping policy is fixed (§5.4).
- **A failure to deliver a FORWARD element always keeps the answer not
  200** (R1-D2, R1-D3). That is how Meta's redelivery completes it.

### 5.2 mTLS (R1-D10, the review's specification 2)

**What is verified, by the component that terminates the relay's TLS, on
the certificate itself:**
1. a client certificate is presented;
2. **its chain is validated to Meta's outbound API CA certificate** (E53,
   E54), configured as **the only trust anchor** for this endpoint. Not the
   system's public roots;
3. its validity period;
4. **the decided identity:** the subject's common name is
   `client.webhooks.fbclientcerts.com` (E55), read **from the validated
   certificate**, never from a header or a text passed along.

**If TLS is terminated before the relay** (a load balancer), that component
is part of what the tests prove. A header carrying a certificate's subject
is not trusted on its own.

| Test | Input (a synthetic test CA stands for Meta's in the tests) | Expected |
|---|---|---|
| R1-T10.1 | a certificate from the test CA, the right CN, valid | handshake and request accepted |
| R1-T10.2 | no client certificate | refused |
| R1-T10.3 | a **self-signed** certificate with the right CN | refused: **untrusted** |
| R1-T10.4 | a certificate from **another CA** (for instance one a public root trusts) with the right CN | refused: the only anchor is the configured CA |
| R1-T10.5 | a certificate from the test CA with **another CN** | refused: **mismatched** |
| R1-T10.6 | a certificate from the test CA, expired or not yet valid | refused |
| R1-T10.7 | a request with no valid certificate, carrying a header that names the right CN | refused |

**Not claimed:** the rotation of Meta's CA certificate. Its file name
carries a date (E53); replacing it is an operational change outside R-1's
tests.

### 5.3 R1-D6: the mapping table

**The rule:** only the types below are forwarded with content. Any other
type, documented or not, is forwarded as `OTHER`, **without content**. No
stored value equals an internal type (`PHONE_DECISION`,
`CONFIRMATION_LINK`). The values follow TURAB's convention, uppercase, as
`TEXT` is the contract's default.

| Meta `type` | Excerpt | Stored `message_type` | `body_text` | `media_ref` |
|---|---|---|---|---|
| `text` | E28, E29 | `TEXT` | `text.body` | none |
| `image` | E30, E31, E32 | `IMAGE` | `image.caption`, if present | `image.id` |
| `video` | E35, E36, E57 | `VIDEO` | `video.caption`, if present | `video.id` |
| `document` | E37, E38, E58 | `DOCUMENT` | `document.caption`, if present | `document.id` |
| `audio` | E33, E56 | `AUDIO` | none | `audio.id` |
| `sticker` | E40, E59 | `STICKER` | none | `sticker.id` |
| `location` | E41 | `OTHER` | none | none |
| `contacts` | E42 | `OTHER` | none | none |
| `interactive` | E43 | `OTHER` | none | none |
| `button` | E44 | `OTHER` | none | none |
| `reaction` | E45 | `OTHER` | none | none |
| `order` | E46 | `OTHER` | none | none |
| `system` | E47 | `OTHER` | none | none |
| `unsupported` | E48 | `OTHER` | none | none |
| `edit` | E49 | `OTHER` | none (R1-F10) | none |
| `revoke` | E50 | `OTHER` | none (R1-F10) | none |
| any other value | — | `OTHER` | none | none |

**Notes:**
- **Content travels only in `body_text` and `media_ref`**, the two content
  keys of TURAB's envelope (`OPTIONAL_CONTENT`). TURAB then applies its own
  archive consent (G7-9). A document's `filename` (E39) is content, and is
  not carried; neither are the media's `mime_type`, `sha256` or `url`.
- **`media_ref` is Meta's media identifier, not the media.** The relay
  downloads nothing.
- **What `OTHER` loses:** a location, a shared contact card, a button or list
  reply's text, a reaction's emoji, an order's items, an edit's new text.
  None reaches TURAB. Widening the list is a later decision, with its own
  consent review.

### 5.4 R1-Q1 · An oversize envelope inside a batch: DECIDED (a) (review of `3d8b593`)

**R1-Q1 · An oversize envelope inside a batch.** R1-D4 (i), adopted, refuses
an envelope over 65 536 bytes and keeps Meta's answer not 200. Under §5.1,
that oversize is a function of the notification's bytes: every redelivery
fails the same way. For 7 days Meta would redeliver a POST whose other
elements are already delivered, then drop it (E9).

| Option | Effect |
|---|---|
| (a) **keep R1-D4 (i)**: not 200 | the element is retried for 7 days, then dropped by Meta; the valid elements are delivered on the first attempt and replayed as 200 |
| (b) **class it ISOLATED**: no envelope, counted, an alert; the answer may be 200 | the element is not delivered, and an operator is alerted at once; no futile redelivery |

*Revision 2 recommended (b).* **The review of `3d8b593` decided (a):**
- Meta's answer stays **not 200** for an envelope over 65 536 bytes;
- that envelope is **not sent** to TURAB, and its content is **not
  shortened**;
- an **alert** is raised, **without the message's content**;
- the redelivery of the elements already delivered is **tested to write
  nothing a second time** (R1-T7.2).

**The reviewer's reason:** to keep the redelivery window open, so a size or
mapping policy can be fixed while Meta still redelivers; a 200 would remove
that possibility at once.

**Its limit, as recorded:** the window is Meta's documented "up to 7 days"
(E8, E12), in our record of the WhatsApp pages. The reviewer could not
confirm it from Meta's live page. After the window, Meta drops the delivery
(E9), with its valid elements already delivered.

### 5.5 The run entry point's access log (DECIDED in the review of `8c64c64`)

**Why:** Meta sends `hub.verify_token` in the GET's query string (E1). Any
log of the request line records it. uvicorn's access log does: found in R-1
step 1 (`R1_STEP1_DELIVERY.md` §2).

**The condition, binding before any deployment or Callback setting:**
- the logging of the request line is **disabled, or its query removed,** in
  the HTTP server **and in every layer in front of it** (a load balancer, a
  proxy, a TLS terminator);
- it is **tested through the actual run entry point**, as deployed. The step
  1 test server's `access_log=False` proves that server's configuration
  only, not an entry point not yet built.

**Where it binds:** §4's order (step 3, the deployment), and §7 (condition
11).

## 6. Sequence

| Step | Content | Depends on |
|---|---|---|
| 0 | the decisions R1-D1 to R1-D15 | **adopted** (review of `1d00f41`); R1-Q1 **decided (a)** (review of `3d8b593`) |
| 1 | duties 1 and 2 (the GET; Meta's signature, with R1-T1.5 and R1-T2.8; the inbound limit) and mTLS (§5.2) | **CLOSED at `e9fac51`** (review of `e9fac51`; `R1_STEP1_DELIVERY.md`) |
| 2 | duties 3, 4 and 6 (the transformation and §5.3's table; the relay's signature; `thread_ref` and R1-D8), checked by TURAB's own `parse_envelope` and `verify` | **AUTHORIZED** (review of `e9fac51`); delivered; **NOT closed** (review of `ced7df7`: document order); no deployment, no secret, no real event |
| 3 | duty 5 and §5.1's classes and answers, against a test double and against TURAB's real application and test database | step 2 |
| 4 | duty 7 (the serialized sizes, with R1-Q1 (a)); R-1's evidence; the barriers' state measured (§4); the closure record | step 3 |

Each step is delivered with its tests and its mutation record, and reviewed
before the next. **Lifting a barrier of §4 is not a step of this plan.**

## 7. R-1's acceptance conditions

1. Each of the seven duties, and §5.2's mTLS, proven by the tests of §3
   and §5.2, every one passing, on synthetic notifications only.
2. The relay's output accepted by **TURAB's own** parser and signature
   check (R1-T3.7, R1-T4.2), and its redelivery shown against TURAB's real
   application (R1-T5.6).
3. Every guard fails closed: no token, no secret, no key (R1-T1.4, R1-T2.5,
   R1-T4.4).
4. The constant-time comparisons proven by their call path (R1-T1.5,
   R1-T2.8).
5. §5.1's classes and answers proven (R1-T3.8, R1-T6.7), and §5.3's table
   proven type by type (R1-T3.5).
6. The envelope's size bounded by its serialized bytes (R1-T7.1 to
   R1-T7.5). No limit attributed to Meta beyond its documentation.
7. No content in any log of the relay (R1-T2.7, R1-D9); no content from an
   ISOLATED element anywhere.
8. Each mutation of the relay's guards killed, in two identical runs.
9. **The barriers' state measured and recorded at closure** (§4). Lifting a
   barrier is decided separately.
10. **K06 UNPROVEN, SALE only.** Not a release authorization.
11. **The run entry point meets §5.5,** tested through it, before any
    deployment or Callback setting.

## 8. What this plan does not do

- write code, create a secret or a verify token, or configure Meta's app;
- deploy anything, expose any route, or receive any event;
- change TURAB's webhook, contract or tests;
- prove Meta's behaviour or the state of any deployment: §1 is Meta's
  documentation, retrieved and quoted; §4's states are measured at closure;
- touch K06, which stays an independent condition before the release gate.

## 9. Document identity

This file's sha256 is recorded in `docs/gate/evidence/DOCUMENT-HASHES.txt`
at the commit that adds each revision.
