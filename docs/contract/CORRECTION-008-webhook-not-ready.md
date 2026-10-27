# CORRECTION-008 — the webhook's 503: the event's acceptance not confirmed

| | |
|---|---|
| **Kind** | Response addition, through the corrections overlay (`response_additions`). It adds one error response, and grants nothing |
| **Operation** | `postWebhooksWhatsapp` (POST `/webhooks/whatsapp`) |
| **Decision** | Slice 7 plan G7-17 (ii) and (vi), decided in the review of `bf1fe3d`: "a missing or empty secret is not an authentication fault of the relay: its answer is 503, before any write, with the fixed code `WEBHOOK_NOT_READY`"; CORRECTION-008 "asks for a redelivery without claiming the event is recorded". **Widened in the review of `3dfb717`** to a T1 that raises after the request's checks passed, its description to "the event's acceptance could not be confirmed; deliver it again with the same identifier" |
| **Status of this text** | **APPROVED in the review of `23b99b6`** (2026-10-27), as delivered there, with Slice 7 step 3's closure. Submitted with the step's delivery; the entry carries its `approved` date since |
| **Frozen package** | `openapi_v0.2.3.yaml`, unchanged. The correction is applied in `docs/api/openapi_effective_v0.2.3.yaml` |

## 1. The frozen text, and why it does not suffice

The frozen operation declares 200, 400 and 401 only (CORRECTION-007 §1
quotes it).

**The two cases it leaves without a true answer.**
1. `TURAB_RELAY_SIGNING_SECRET` is absent or empty. TURAB then cannot verify
   any delivery. G7-2 (i) says "a missing secret fails closed", and does not
   say with what answer. **Here nothing is written, and that is known.**
2. **T1 raises** after every check of the request passed (the review of
   `3dfb717`). Its COMMIT may have taken effect or not: a client can lose
   its connection while a COMMIT is in progress, the case PostgreSQL 16's
   documentation names for `pg_xact_status` (§9.27, System Information
   Functions), as the review of `3dfb717` cites it (CORRECTION-007 §3 says
   what we could and could not check). **Here it is not known whether the
   event is recorded.**

- **Why 401 would be false.** The relay's signature may be correct: the
  fault is TURAB's configuration, not the relay's authentication. G7-17
  (ii)'s recommendation (a) was 401; the review of `bf1fe3d` amended it to
  this 503.
- **Why CORRECTION-007's 500 would be false.** That 500 states that the
  event is stored, which is false in case 1 and unknown in case 2. Before
  the review of `3dfb717`, case 2 answered the generic 500
  `INTERNAL_ERROR`: the same status then carried two meanings in the
  effective contract.
- **Why 200 would be false.** The event could be lost: the relay would not
  redeliver it.
- **Why the text claims neither "recorded" nor "nothing recorded".** Case 2
  allows both. The redelivery is decided by the event's own record (G7-2
  (v)), so the relay needs only to know that it must deliver again.

## 2. The correction

| | Frozen | Effective |
|---|---|---|
| `responses.503` | — | `application/problem+json`, `$ref: Problem`, code `WEBHOOK_NOT_READY` |
| its description | — | "The event's acceptance could not be confirmed: the webhook cannot verify deliveries now, or storing the event did not confirm. Deliver it again with the same provider_event_id." |
| its annotation | — | `x-turab-correction`, kind `RESPONSE_ADDITION`, the entry's id, decision, code, frozen statuses and reference |
| 200, 400, 401, and CORRECTION-007's 500 | declared | unchanged |
| `security`, the request body, every other operation | — | unchanged |

**The same rules as CORRECTION-007** bind it (§2 there). The pair
`(postWebhooksWhatsapp, 503)` is distinct from `(postWebhooksWhatsapp,
500)`, which is why uniqueness is per (operation, status) rather than per
operation (G7-17 (vi), amended).

**What separates the two meanings:**

| | CORRECTION-007 (500) | CORRECTION-008 (503) |
|---|---|---|
| the event | stored; its `provider_event_id` recorded | **not confirmed**: not recorded (a missing secret), or unknown (T1 raised) |
| the processing | its result not confirmed: FAILED (recorded) or `PROCESSING_LOST` | not reached |
| what is asked | deliver the same `provider_event_id` again | deliver the same `provider_event_id` again |
| when | after T1 committed | before any write, or when T1 raised |

## 3. The runtime rule

- **When the 503 is answered** (`api/routes/webhooks.py`, G7-17 (iii)):
  1. the size is checked first. A body over 64 KiB is 400 even without a
     secret (G7-15);
  2. **then the secret.** If `TURAB_RELAY_SIGNING_SECRET` is absent or
     empty, the answer is 503, and the signature is not computed;
  3. only then the signature (401), the envelope and a known type's keys
     (400), and T1.
- **For a missing secret, nothing is written:** no event row, no message, no
  audit row. The test the review of `bf1fe3d` asked for checks this:
  `test_ii_a_missing_or_empty_secret_is_503_with_no_event_row`.
- **When T1 raises** after the size, the secret, the signature and the
  envelope passed, the answer is the same 503, outcome
  `ACCEPTANCE_NOT_CONFIRMED`. Tested both ways: T1 failing before its
  COMMIT (no event row), and T1 committing with its answer lost (the event
  RECEIVED). In both, the redelivery completes the event once, with one
  message.
- **The secret is read on each request,** encoded UTF-8. Setting it makes
  the webhook ready without a restart.
- **The fault is logged** under the trace id, naming the variable, without
  the body, the signature or any value. The access auditor records the one
  answer (G7-17 (vii)): status 503, outcome `SECRET_NOT_CONFIGURED`.
- **The body:** a `Problem` with the code `WEBHOOK_NOT_READY`, the trace id,
  and one fixed detail for both cases ("The event's acceptance could not be
  confirmed. Deliver it again with the same provider_event_id."), naming
  neither the secret nor the database.
- **What the relay does with it** is R-1's duty 5, extended to the 503 in
  the review of `bf1fe3d`: it redelivers later. **R-1 must test the
  redelivery on 500, on 503 and on a timeout. R-1 is UNMET.**

## 4. Evidence

- **`tests/test_correction_007_008.py`:**
  - the entry, and its description against CORRECTION-007's;
  - the effective operation;
  - the code, a `ProblemCode` whose catalogue status is 503;
  - the loader's refusals. Among them is a second addition of the same pair,
    which is refused.
- **`tests/test_slice7_step3.py`:**
  - the 503 with the secret absent, and with it empty, writing nothing and
    leaving no event row;
  - the order: the size before the 503, and the 503 before the signature;
  - the log carries neither the body nor the secret;
  - a T1 failing before its COMMIT, and a T1 whose COMMIT's answer is lost:
    each 503, then the redelivery processes the event once.
- **Mutations:** `db/dev/mutate_slice7_step3.py`.
