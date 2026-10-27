# CORRECTION-007 — the webhook's 500: stored, the processing's result not confirmed

| | |
|---|---|
| **Kind** | Response addition, through the corrections overlay (`response_additions`). It adds one error response, and grants nothing |
| **Operation** | `postWebhooksWhatsapp` (POST `/webhooks/whatsapp`) |
| **Decision** | Slice 7 plan §5.2 (`docs/gate/SLICE_7_PLAN.md`): adopted in the review of `4aed49b`. Its mechanism (`response_additions`, unique per (operation, HTTP status)) was decided in the review of `bf1fe3d` (G7-17 (vi)). Its meaning was narrowed in the review of `3dfb717`: the result of the processing is **not confirmed** to the sender, rather than "not processed" |
| **Status of this text** | **APPROVED in the review of `23b99b6`** (2026-10-27), as delivered there, with Slice 7 step 3's closure. Submitted with the step's delivery; the entry carries its `approved` date since |
| **Frozen package** | `openapi_v0.2.3.yaml`, unchanged. The correction is applied in `docs/api/openapi_effective_v0.2.3.yaml` |

## 1. The frozen text, and why it does not suffice

```yaml
/webhooks/whatsapp:
  post:
    operationId: postWebhooksWhatsapp
    security: []
    responses:
      '200': {description: Accepted}
      '400': {description: Request rejected, content: {application/problem+json: {schema: {$ref: '#/components/schemas/Problem'}}}}
      '401': {description: Request rejected, content: {application/problem+json: {schema: {$ref: '#/components/schemas/Problem'}}}}
```

- **Before this correction, the effective contract declared a `500` for no
  operation** (searched: no `'500'` in `openapi_effective_v0.2.3.yaml`, plan
  §5.2).
- **The case it leaves without an answer** (G7-2 (iv), (v)): T1 has
  committed the event, and **the result of its processing is not confirmed
  to the sender.** Two outcomes lead there (§3):
  - T2 ended FAILED: its processing raised, and the failure is recorded;
  - T2 raised outside its savepoint (`PROCESSING_LOST`). Whether its COMMIT
    took effect is then unknown: the event may keep its previous status
    (RECEIVED, or FAILED from an earlier attempt), or be PROCESSED or
    IGNORED with only the COMMIT's answer lost.
- **Why 200 would be wrong.** A 200 tells the relay that nothing more is
  needed. An event left unprocessed could then be recovered only by the
  operator command, from the content-free payload, so **without its
  content** (G7-2 (v), accepted limit). The relay's redelivery is the one
  recovery that keeps the content (G7-9), and it needs a signal.
- **Why 400 or 401 would be wrong.** The request was valid and verified;
  the fault is TURAB's.
- **Why the precedent did not settle it.** Slice 4's typed 500 for its
  policy faults was set by a review decision without a contract entry
  (`SLICE_4_PLAN.md` G4-15). Here the 500 is a signal the relay acts on, so
  it is in the contract (§5.2).

## 2. The correction

| | Frozen | Effective |
|---|---|---|
| `responses.500` | — | `application/problem+json`, `$ref: Problem`, code `WEBHOOK_PROCESSING_FAILED` |
| its description | — | "The event is stored (its provider_event_id is recorded); the result of its processing could not be confirmed. Deliver it again with the same provider_event_id; the event's record decides the redelivery, which completes it once or replays it." |
| its annotation | — | `x-turab-correction`, kind `RESPONSE_ADDITION`, the entry's id, decision, code, frozen statuses and reference |
| 200, 400, 401 | declared | unchanged |
| `security`, the request body, every other operation | — | unchanged |

**What makes it an addition of one error response, and nothing more**
(`turab.auth.contract.load_response_additions`; each rule tested in
`tests/test_correction_007_008.py`):
- one entry per (operation, HTTP status). CORRECTION-008 adds the same
  operation's 503, a different pair;
- an operation of the frozen contract, and a status it does not declare;
- a 5xx, written as three digits: never a success, never a 4xx;
- `application/problem+json` with the contract's `Problem`, and a fixed code
  written as an upper-case identifier;
- no key beyond the listed ones, so no role, no schema and no security can
  be carried;
- `frozen_statuses: ["200", "400", "401"]`, compared with what the package
  declares. If the package changes, the entry is stale and is refused until
  it is approved again.

**The overlay's header** names this as the one exception to its first
invariant ("a correction may only NARROW"), decided in G7-17 (vi).

## 3. The runtime rule

- **When the 500 is answered** (`api/routes/webhooks.py`), always after T1
  has committed, in two cases the access record tells apart:

  | Outcome | What is known | The event's record |
  |---|---|---|
  | `FAILED` | T2's processing raised; every write of step 3 was rolled back to the savepoint, and the failure was **recorded**, `error_text = PROCESSING_FAILED`, in the same T2, which committed | FAILED |
  | `PROCESSING_LOST` | T2 raised outside the savepoint: step 4's UPDATE, the COMMIT, or the connection. **Whether its COMMIT took effect is not known** | its previous status (RECEIVED or FAILED), or PROCESSED or IGNORED if the COMMIT took effect and only its answer was lost |

- **Why the text says "not confirmed", not "not processed"** (the review of
  `3dfb717`). A client can lose its connection while a COMMIT is in
  progress, and then cannot tell from the error whether the transaction
  committed. PostgreSQL 16's documentation of `pg_xact_status` (§9.27,
  System Information Functions) names this case, as the review of `3dfb717`
  cites it: a client disconnected while a COMMIT is in progress must find
  out whether its transaction was committed. *This environment could not
  fetch that page (DNS: `ENOTFOUND www.postgresql.org`), and holds no local
  copy of the documentation; the statement is the reviewer's citation, not
  our quotation. What we measured locally: PostgreSQL 16.15 has the function,
  described in its catalogue as "commit status of transaction".* "Not
  processed" would then be a claim the server cannot make.
- **Why the redelivery is right in every case.** The event's record decides
  (G7-2 (v)): a PROCESSED or IGNORED event is a replay, an empty 200 and
  nothing written; a RECEIVED or FAILED one is processed once. Tested for a
  COMMIT that took effect and whose answer was lost: the redelivery is a
  replay, and no second message is made.
- **Never when T1 raised.** A T1 that raised may or may not have committed,
  so "the event is stored" cannot be claimed. That case is CORRECTION-008's
  503 (the review of `3dfb717`; before it, the route answered a generic 500
  `INTERNAL_ERROR`, which gave the same status two meanings in the effective
  contract).
- **The body:** a `Problem` with the code `WEBHOOK_PROCESSING_FAILED`, the
  trace id, and a fixed detail ("The event is stored; the result of its
  processing could not be confirmed. Deliver it again with the same
  provider_event_id."). No exception text, no reference and no content from
  the envelope. The cause's type is logged under the trace id, without the
  body.
- **What the relay does with it** is R-1's duty 5 (G7-2 (ii)): it redelivers
  the same `provider_event_id`, with its content. A redelivery of a RECEIVED
  or FAILED event runs T2 again (G7-2 (v)), so the event is completed once.
  **R-1 is UNMET:** no relay exists, and no real event may be received
  before it does.

## 4. Evidence

- **`tests/test_correction_007_008.py`:**
  - the entry, and its description against CORRECTION-008's;
  - the effective operation, against an expectation written independently
    of `added_response`;
  - the frozen operation, unchanged;
  - the code, a `ProblemCode` whose catalogue status is 500;
  - the loader's refusals.
- **`tests/test_correction_001.py`:** the effective contract changes nothing
  but what the corrections name. Its independent expectation now pops each
  added response and compares it.
- **`tests/test_slice7_step3.py`:** the 500 through the route:
  - a failure in processing, by SQL and by a Python exception (FAILED,
    recorded);
  - a failure of step 4's UPDATE (`PROCESSING_LOST`, the event unchanged);
  - a T2 that committed and whose answer was lost (`PROCESSING_LOST`, the
    event PROCESSED): the redelivery is a replay, with no second message;
  - and the route answers no other 5xx than this one and CORRECTION-008's.
- **Mutations:** `db/dev/mutate_slice7_step3.py`.
