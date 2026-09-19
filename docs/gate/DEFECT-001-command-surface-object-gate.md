# DEFECT-001 — The Slice 1 command surface shipped without an object gate

**Status:** CLOSED (fix committed, 10 regression tests, 1 architecture test)
**Severity:** Critical — Broken Object Level Authorization (OWASP API Security
Top 10 (2023), **API1:2023 Broken Object Level Authorization**; OWASP
Foundation, *OWASP API Security Top 10 — 2023*). CWE-639, *Authorization
Bypass Through User-Controlled Key* (MITRE, CWE List v4.14).
**Found:** 2026-09-19, by self-review of the Slice 1 surface before closure.
**Found by inspection, not by a test** — see §5.

---

## 1. What was wrong

RFC-001 r3 specifies two independent checks on every operation:

1. a **role gate** — does this actor's role appear in the operation's
   `x-roles`? and
2. an **object gate** — is this actor authorized over *this specific object*?

Slice 1's read paths satisfy both: a read reaches data only through a scoped
loader (`auth/loaders.py`), and a loader cannot return a row the caller may
not see. The check is structural, so it cannot be forgotten.

The **command** paths had no equivalent. A command has no loader — it names
its object by path parameter and writes to it. Four routes derived their whole
authorization from the role gate:

| Operation | Contract `x-roles` | Object check shipped |
|---|---|---|
| `PATCH /parties/{party_id}` | ADMIN, OPERATOR, CUSTOMER | none |
| `POST /parties/{party_id}/phones` | ADMIN, OPERATOR, CUSTOMER | none |
| `POST /parties/{party_id}/consents` | ADMIN, OPERATOR, CUSTOMER | none |
| `POST /parties` | ADMIN, OPERATOR, CUSTOMER | none |

Because `CUSTOMER` is a contract-authorized role on all four, the role gate
passed for **any** authenticated customer against **any** `party_id`.

## 2. Confirmed, not theorised

The defect was reproduced against the running application before any fix was
written (test database, seeded fixtures; one customer account acting on a
second customer's party):

```
PATCH /parties/{other_party}          -> 200   display_name now "PWNED"
POST  /parties/{other_party}/phones   -> 201   contact point attached
POST  /parties                        -> 201   party created with no owner
```

A customer could rename any party in the system, attach a phone number they
control to a stranger's party — which is the first half of an account-takeover
path once Slice 2 routes notifications by contact point — and mint
owner-less PARTY rows at will. The write damage was removed from the test
database immediately after confirmation.

## 3. The fix

`CommandService` now carries the two object rules a command can need, and the
route calls one before the command runs:

- `authorize_party_scope(party_id)` — staff are authorized by role and
  recorded; a CUSTOMER must **be** the party. Any other pairing is denied
  `OBJECT_NOT_AUTHORIZED` and audited.
- `authorize_staff_only(operation_id, reason)` — for a command whose object
  does not exist yet (`POST /parties`).

`POST /records/claim` is exempt **by design**, with the reason stated in the
route: claiming is how a customer *acquires* authority over a record they do
not yet hold, so an ownership pre-check would make the command unusable. Its
object rule is INV-1, enforced inside `services/claims.py`.
`POST /consents/bindings` is staff-only; the contract already excludes
CUSTOMER from its `x-roles`, and the object check restates the guarantee so it
does not depend on the contract staying that way.

## 4. Why it cannot recur

Restating the rule in prose would repeat the mistake. The rule is now
structural, in the same manner as Q6:

`tests/test_architecture.py::test_every_command_route_performs_an_object_check`
parses each route module's AST, and for every function decorated with a
mutating method (`post`, `patch`, `put`, `delete`) asserts that its body calls
`authorize_party_scope` or `authorize_staff_only`, or appears in an explicit,
named exemption set. **A new command route that forgets the object gate fails
the build.** `test_the_guard_check_is_not_vacuous` proves the check itself has
teeth by asserting it rejects a synthetic guard-less route.

Regression coverage: `tests/test_slice1_bola.py`, 10 tests — each of the three
confirmed exploits asserted closed (403, `OBJECT_NOT_AUTHORIZED`, and the
underlying row **unchanged**), the positive half (a customer may act on their
own party; staff may act on any party), the audit record, and the
no-party customer case.

## 5. Root cause

The object gate was made structural for reads and left conventional for
writes. Slice 0's authorization work built the loaders, and the Slice 0
evidence matrix proved the read rules thoroughly — which made the surface look
covered. The command paths were added in Slice 1, after that machinery, and
inherited none of it: `CommandService` enforced idempotency, concurrency and
the *role* gate, so it read like a complete authorization boundary.

No test failed, because no test asked the question. The Authorization Evidence
Matrix reported PASS on every rule it carried; none of its 73 rules was
"a customer cannot write to another customer's party". An evidence matrix
proves the rules it lists and is silent on the rules it lacks — that silence
is the actual failure mode here, and it is why the fix is an architecture test
rather than six more integration tests.

## 6. Open item requiring ratification — D7

`authorize_staff_only` on `POST /parties` **narrows** the frozen contract:
`openapi_v0.2.3.yaml` lists `CUSTOMER` in that operation's `x-roles`, and the
implementation now refuses a CUSTOMER caller at the object gate.

The narrowing is deliberate and fail-closed. `IMPLEMENTATION_SLICES_v0.2`
scopes Slice 1 to "create / read / update PARTY **for staff**"; no slice
before Slice 8 defines a self-service registration flow. Absent that flow, a
customer-created PARTY is an unbounded write primitive that produces a row
with no owner, which the creator cannot then read back through `/me/*`.

This is a **Permissions** decision and therefore requires approval under the
project's standing rule. It is implemented in the safe direction pending that
decision, and is recorded here rather than resolved silently. Two outcomes are
available:

- **(a) Ratify the narrowing.** `POST /parties` is staff-only in v0.1; the
  contract's `x-roles` is corrected in a later technical patch so the
  implementation and the contract agree again.
- **(b) Define self-service creation now.** A CUSTOMER caller may create a
  party only when their account has none, and the new party is bound to the
  calling account in the same transaction. This adds a domain rule to Slice 1
  and needs its own approval.

Until one is chosen, the contract-vs-implementation divergence on this single
operation stands, documented, as the only known deviation from
`openapi_v0.2.3.yaml`.

---

## References

- OWASP Foundation. *OWASP API Security Top 10 — 2023*, API1:2023 Broken
  Object Level Authorization.
- MITRE. *CWE-639: Authorization Bypass Through User-Controlled Key*, CWE List
  v4.14.
- TURAB `docs/rfc/RFC-001-object-level-authorization.md`, revision 3 (FINAL),
  §4 object authority and §10.1 deny by default.
- TURAB `docs/handoff/06_IMPLEMENTATION/IMPLEMENTATION_SLICES_v0.2.md`,
  Slice 1 and Slice 8 scope statements.
