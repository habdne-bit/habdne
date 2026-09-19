# RFC-001 — Appendix A · INV-1 and INV-2

**Status:** numbered appendix to RFC-001 revision 3 (FINAL).
**Purpose:** carry the approved text of the two fail-closed implementation
invariants and name its source, **without editing the approved document**.
**Raised as:** DL-12. **Answers:** the independent review's note that DL-12 is
reference documentation to be handled by a numbered appendix that transfers
the approved text and its source rather than a silent edit of the original.

---

## A.0 Why this appendix exists

RFC-001 contains no occurrence of `INV-1` or `INV-2`:

```
$ grep -c "INV-" docs/rfc/RFC-001-object-level-authorization.md
0
```

Both invariants were added **at the moment RFC-001 was approved**, in the
approval instruction, and were never folded back into the RFC. Their text has
since lived only in that message, in the closure packs, and in the docstrings
of the code enforcing them — so a reviewer asked to read the constraint from
its own source found no canonical paragraph.

This appendix is that paragraph. It adds nothing to the invariants and
reinterprets nothing: it transfers the approved wording, states where it came
from, and records where each half is enforced. **The body of RFC-001 is
unchanged.**

## A.1 INV-1 — ambiguous claim authority fails closed

> If more than one distinct account appears as claim authority for a resource,
> grant authority to **none** of them, audit the condition as
> `CLAIM_AUTHORITY_CONFLICT`, and reject a second claim except as an
> idempotent replay by the same actor.

*Source: the RFC-001 revision 3 approval instruction, "Add two mandatory
fail-closed implementation invariants", item 1.*

### A.1.1 Disclosure clarification

> `CLAIM_AUTHORITY_CONFLICT` must be explicit internally (audit/operations),
> but external disclosure remains concealment-safe. An unrelated actor still
> receives 404. A known conflicting claimant or authorized staff may receive a
> typed 409 without disclosure of the other claimant's identity or conflict
> details.

*Source: the Slice 0 authorization sub-gate acceptance.*

### A.1.2 Relationship to the contract's own claim condition

INV-1 governs conflicts **between** claimants. It says nothing about whether a
claimant is the right person at all — that is the frozen contract's
`x-authorization` on `postRecordsClaim`, enforced by CORRECTION-003. The two
are complementary and both run inside the same write transaction under a row
lock.

## A.2 INV-2 — an invalid role combination fails closed

> `OPERATOR` + `REVIEWER` is an invalid role combination: rejected at grant
> time, and failing closed for separation-sensitive operations where it is
> nonetheless found in existing data.

*Source: the same approval instruction, item 2.*

Both halves are required because `user_account_roles` is keyed
`(account_id, role)`, so the database permits the combination: the service is
the only thing preventing it going forward, and data predating the guard can
already hold it.

## A.3 Where each half is enforced

| Invariant | Half | File | Symbol |
|---|---|---|---|
| INV-1 | read | `src/turab/auth/loaders.py` | `claim_authority_accounts`, `ClaimAuthorityConflict` |
| INV-1 | write | `src/turab/services/claims.py` | `claim_record`, `ResourceAlreadyClaimed`, `ClaimAuthorityConflictExists` |
| INV-1 | disclosure | `src/turab/services/access.py` | `_may_learn_of_conflict` |
| INV-2 | grant time | `src/turab/services/roles.py`, `src/turab/auth/roles.py` | `grant_role`, `invalid_role_combination` |
| INV-2 | fail closed | `src/turab/auth/policy.py` | `ROLE_CONFIGURATION_ANOMALY`, `SEPARATION_SENSITIVE_OPERATIONS` |
| INV-2 | detection | `src/turab/services/roles.py` | `find_role_anomalies` |

## A.4 Tests

| Invariant | Tests |
|---|---|
| INV-1 | `tests/test_inv1_claim_authority.py` (12), `tests/test_conflict_disclosure.py` (13) |
| INV-2 | `tests/test_inv2_separation.py` (15) |

## A.5 Standing

This appendix is documentation. It creates no new rule and changes no
behaviour. Folding the two invariants into the body of RFC-001 as numbered
rules remains available as a later editorial decision; it is not taken here
because it would edit an approved document.
