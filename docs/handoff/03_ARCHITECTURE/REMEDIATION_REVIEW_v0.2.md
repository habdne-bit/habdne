> **Supersession note (2026-09-19):** the v0.2 remediation work remains valid. Runtime FK corrections were released in v0.2.1; D1/D2 concurrency/PARTY-version corrections were runtime-validated in v0.2.2 but that candidate was not frozen because of D6 metadata version drift. The current adoption candidate is `TECHNICAL_PATCH_v0.2.3.md` / `schema_v0.2.3.sql` / `openapi_v0.2.3.yaml`, which changes only the authoritative version stamp/packaging identity while preserving all prior semantics. This document is remediation evidence, not proof that v0.2.3 passed its required rerun.

# TURAB — Technical Remediation Review v0.2

**Review date:** 2026-09-18  
**Input:** Technical Pack v0.1 + strict Architecture Review v0.1  
**Output:** Technical Pack v0.2

## Executive result

All P0 findings from the v0.1 Architecture Review have been addressed in the v0.2 technical contracts. The static contract audit passes with zero detected errors/warnings. The only release gate still open is **real execution of schema + seed + database contract tests on PostgreSQL 16+**, which is impossible in the current artifact environment because PostgreSQL binaries are not installed.

**Decision:**

> **CONDITIONAL GO for implementation preparation.**  
> **NO-GO for coding Slice 0/1 until PostgreSQL Execution Gate passes in CI/local PostgreSQL 16+.**

This distinction is intentional: the architecture is remediated, but static analysis does not prove PostgreSQL execution semantics.

---

## Closure matrix — P0

| Finding | v0.2 closure | Status |
|---|---|---|
| P0-01 Match lacks commercial context | request BUY/RENT intent; evaluated offer; offer version/freshness; commercial snapshot; DB compatibility trigger | CLOSED |
| P0-02 Match not historically replayable | immutable request/property/commercial/permission/freshness snapshots + input hash; match history immutable | CLOSED |
| P0-03 CONFIRMED_SAME does not resolve identity | non-destructive alias→canonical table, chain guards, canonical-only matching, transactional review contract | CLOSED |
| P0-04 Consent not resource-safe | resource consent bindings + party/scope/status validation + revoke command + permission snapshot | CLOSED |
| P0-05 Public/customer privacy boundary | separate DTOs; `/me/*`; internal endpoints exclude customer arbitrary reads; public property summary | CLOSED |
| P0-06 Generic PATCH bypass | typed whitelist PATCH schemas; stateful changes moved to dedicated commands | CLOSED |
| P0-07 Truth lineage can be corrupted | claim verification cannot self-upgrade; verification event projection; resolution/property-attribute lineage triggers | CLOSED |
| P0-08 Multiple current-truth sources | operational projection + immutable provenance ADR; atomic domain-command contract; parent version touches | CLOSED |

---

## Closure matrix — P1

| Finding | Closure | Status |
|---|---|---|
| Audit entity id missing | generic audit trigger receives PK column | CLOSED |
| One match review row | append-only review history + latest view | CLOSED |
| Task outcome lost | task completion events | CLOSED |
| Idempotency incomplete | persistent idempotency store + required command header | CLOSED |
| Phone/account duplication | contact point model + party many-to-many + account login contact point | CLOSED |
| Assisted defaults wrong | explicit management/claim invariant | CLOSED |
| Policy integrity | policy FK, immutable version, one-active-policy unique index | CLOSED |
| Offer freshness missing | independent commercial/offer freshness | CLOSED |
| Legal master options free-form | controlled attribute options seed | CLOSED |
| Reason code drift | single seed registry normalized for v0.2 | CLOSED |
| Back Office queues missing | explicit queue endpoints | CLOSED |
| Consent revoke / phone verify flow | revoke + binding + OTP purpose without account | CLOSED |
| Public publication eligibility unclear | public DTO/contract requires active commercial + permission context | CLOSED contract; runtime test pending |
| Communication link consistency | strengthened service invariants and red-team tests | CLOSED contract; runtime test pending |
| WhatsApp replay | webhook event store + provider global external message identity | CLOSED |
| Hard deletes risk | core delete guards + RESTRICT where critical | CLOSED contract; runtime test pending |

---

## Static audit result

Latest `STATIC_AUDIT_RESULTS_v0.2.3.json` reports:

- 48 tables
- 54 enum/types
- 17 PL/pgSQL functions
- 37 triggers
- 55 indexes
- 133 FK references with valid static targets
- 16 Adrar commune seed codes
- OpenAPI 3.1.0
- 61 paths / 64 operations
- 59 component schemas
- 527 local `$ref` occurrences checked
- unique operationIds
- no generic arbitrary PATCH body detected
- idempotency coverage on authenticated mutating POST commands
- no CUSTOMER arbitrary GET outside `/me/*`
- separate public property DTO
- claim API cannot set verification level directly

---

## Residual risks / deliberate limits

### PostgreSQL parser/runtime not yet proven

Static checks cannot prove PL/pgSQL execution, enum comparison behavior, trigger ordering or all CHECK/constraint behavior. Run `POSTGRES_EXECUTION_GATE.md` before coding.

### Identity consolidation of already-shared duplicate opportunities

The contract intentionally requires human review rather than silent merge/closure. Exact UI/workflow behavior belongs to Slice 3/5 implementation tests.

### Public publication eligibility

The API contract is explicit, but the exact repository/query implementation is not yet code. It must be tested against revoked consent, withdrawn offers and price visibility.

### Communication context consistency

Some thread links can be contextually legitimate even when the primary PARTY is not the request owner (e.g. seller conversation about buyer opportunity). Therefore this is primarily a service invariant, not an over-restrictive DB trigger.

### Full database lineage automation intentionally avoided

v0.2 does not implement full event sourcing, temporal DB engine or RDF provenance. This is deliberate and consistent with the Foundation's simplicity rule.

---

## Implementation authorization

Once the PostgreSQL Execution Gate passes, the team may freeze v0.2 and begin `Slice 0` as specified in `IMPLEMENTATION_SLICES_v0.2.md`.

No developer should begin AI matching, frontend polish or WhatsApp integration before the deterministic core and human-reviewed Opportunity path pass the Core Hypothesis Gate.
