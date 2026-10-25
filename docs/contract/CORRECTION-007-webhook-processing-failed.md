# CORRECTION-007 — the webhook's 500: stored, not processed

| | |
|---|---|
| **Kind** | Response addition, through the corrections overlay (`response_additions`). It adds one error response, and grants nothing |
| **Operation** | `postWebhooksWhatsapp` (POST `/webhooks/whatsapp`) |
| **Decision** | Slice 7 plan §5.2 (`docs/gate/SLICE_7_PLAN.md`): adopted in the review of `4aed49b`. Its mechanism (`response_additions`, unique per (operation, HTTP status)) was decided in the review of `bf1fe3d` (G7-17 (vi)) |
| **Status of this text** | **SUBMITTED for approval with Slice 7 step 3's delivery, not yet approved.** The entry carries no `approved` date |
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

- **Today the effective contract declares a `500` for no operation.**
- **The case it leaves without an answer** (G7-2 (iv), (v)): T1 has
  committed the event, and T2 did not process it. Either T2 ended FAILED,
  with the failure recorded, or T2 was lost whole and the event kept its
  status (RECEIVED, or FAILED from an earlier attempt).
- **Why 200 would be wrong.** A 200 tells the relay that nothing more is
  needed. The event could then be recovered only by the operator command,
  from the content-free payload, so **without its content** (G7-2 (v),
  accepted limit). The relay's redelivery is the one recovery that keeps the
  content (G7-9), and it needs a signal.
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
| its description | — | "The event is stored (its provider_event_id is recorded) and was not processed. Deliver the same provider_event_id again; a later delivery completes it once." |
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

- **When the 500 is answered** (`api/routes/webhooks.py`):
  - T2 ended FAILED: its processing raised, every write of step 3 was
    rolled back to the savepoint, and the event was recorded FAILED with
    `error_text = PROCESSING_FAILED`, in the same T2;
  - T2 was lost whole after T1 committed (a failure of step 4's UPDATE, of
    the COMMIT or of the connection). The event keeps its status.
- **Never before T1 commits.** A T1 that does not commit stores nothing, so
  the claim "the event is stored" would be false. That case answers the
  generic 500 `INTERNAL_ERROR`, not this code.
- **The body:** a `Problem` with the code `WEBHOOK_PROCESSING_FAILED`, the
  trace id, and a fixed detail. No exception text, no reference and no
  content from the envelope. The cause's type is logged under the trace id,
  without the body.
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
- **`tests/test_slice7_step3.py`:** the 500 through the route, for the three
  cases of G7-2 (iv): a failure in processing, by SQL and by a Python
  exception; a failure of step 4's UPDATE; and a T1 that does not commit,
  which answers `INTERNAL_ERROR` instead.
- **Mutations:** `db/dev/mutate_slice7_step3.py`.
