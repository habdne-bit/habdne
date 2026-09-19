# REQUEST — the adopted state transition table

**Authority:** Developer Reference Spec §5.2, plus the additions adopted
2026-09-19 and recorded here and in `CONTRACT_CORRECTIONS.yaml`
(CORRECTION-002).
**Enforced by:** `src/turab/services/requests.py:TRANSITIONS`.
**Tested by:** `tests/test_slice2_mandatory.py`.

---

## 1. The table

| From | Permitted targets | Source |
|---|---|---|
| `RAW` | `CONTACTED` | §5.2 |
| `CONTACTED` | `QUALIFIED` | §5.2 |
| `QUALIFIED` | `ACTIVE` | §5.2 |
| `ACTIVE` | `NEEDS_CONFIRMATION`, **`PAUSED`**, **`CLOSED`** | §5.2 + **adopted** |
| `NEEDS_CONFIRMATION` | `ACTIVE`, `PAUSED`, `CLOSED` | §5.2 |
| `PAUSED` | `ACTIVE` | §5.2, explicit reactivation |
| `CLOSED` | `ACTIVE` | §5.2, explicit reactivation |

Anything not in this table is refused, and the refusal names the permitted
targets from the current state. A transition to the state a request is
already in is refused as well.

## 2. What was adopted, and why it was not assumed

**`ACTIVE → PAUSED` and `ACTIVE → CLOSED` directly.** §5.2 writes the
lifecycle as `ACTIVE -> NEEDS_CONFIRMATION -> ACTIVE | PAUSED | CLOSED`, which
read literally requires a request to be marked stale before it can be paused
or closed. That is not how a buyer telling an operator "I've bought
something" behaves. The two edges are now **adopted explicitly** rather than
inferred from convenience, and this table is where they are recorded.

Everything else in the table is §5.2 transcribed edge for edge.

## 3. Reactivation

§5.2: *"PAUSED/CLOSED -> ACTIVE only by explicit reactivation or materially
new request logic."*

**The explicit act is the command itself.** Sending `target_status=ACTIVE` to
`POST /requests/{id}/state` from `PAUSED` or `CLOSED` is the request to
reactivate. An earlier implementation demanded an additional `reactivate`
flag; that field was not in the contract, and it was a second way of saying
something the contract already expresses. It has been removed, and
`extra="forbid"` means no undeclared field can reappear unnoticed.

Two consequences:

- **Reactivation does not refresh `last_confirmed_at`.** A request paused for
  six months is not made current by restarting it. It is subject to the
  freshness rules from the moment it is active again, exactly like any other
  active request.
- **`POST /requests/{id}/reconfirm` does not reactivate.** It returns a
  `NEEDS_CONFIRMATION` request to `ACTIVE`, because §5.2 defines that edge and
  reconfirming is how it is taken. It leaves `PAUSED` and `CLOSED` alone: a
  request stopped for a reason unrelated to freshness must not be restarted by
  confirming that its details are still true.

## 4. Closing

Closing requires a `reason_code` from the **`REQUEST_CLOSURE`** category,
added by migration `0002_request_closure_reasons`:

| Code | Meaning |
|---|---|
| `REQUEST_FULFILLED` | The requester reported their need was met, inside or outside TURAB |
| `REQUEST_WITHDRAWN` | The requester reported they ended the search or withdrew the request |
| `REQUEST_CLOSED_OTHER` | Another reason, explained in a **mandatory** note |

Rules enforced in the service:

- a close with no reason is refused;
- a code from any other category is refused, including the historical
  `GENERAL`/`OTHER`, which keeps its own meaning and is not repurposed, and
  `OPPORTUNITY` codes, which describe a different entity;
- `REQUEST_CLOSED_OTHER` with a blank or whitespace note is refused — a
  free-text escape hatch with nothing written in it is the same as no reason.

**Closing is not a substitute for staleness or for pausing.** All three codes
describe what the REQUESTER reported. None means "we lost track of it", which
is `NEEDS_CONFIRMATION`; none means "on hold", which is `PAUSED`. And
fulfilment is never inferred from an opportunity being created or engaged
with — only from the requester saying so.
