# INV-1 and INV-2 — the two fail-closed implementation invariants

## A finding, stated first

**RFC-001 does not contain the strings `INV-1` or `INV-2` anywhere.** Verified:

```
$ grep -c "INV-" docs/rfc/RFC-001-object-level-authorization.md
0
```

The two invariants were added **at the moment RFC-001 was approved**, in the
approval instruction, and were never folded back into the RFC itself. Their
text lives today in the approval message, in the closure packs, in this
bundle, and in the docstrings of the code that enforces them.

A reviewer asked to read these constraints "from their actual texts" would
therefore find no canonical paragraph in the RFC. That is a documentation gap
in the project, not in this bundle, and it is reported rather than papered
over by quoting a paraphrase as if it were the source. **Folding both into
RFC-001 as numbered rules is the obvious remedy; it is not done here because
it would edit an approved document outside this review's scope.**

What follows is the authoritative text as approved, and then the code that is,
today, the only normative statement of it inside the repository.

---

## The invariants as approved

> Add two mandatory fail-closed implementation invariants:
>
> 1. If more than one distinct account appears as claim authority for a
>    resource, grant authority to **none** of them, audit the condition as
>    `CLAIM_AUTHORITY_CONFLICT`, and reject a second claim except as an
>    idempotent replay by the same actor.
>
> 2. `OPERATOR` + `REVIEWER` is an invalid role combination: rejected at grant
>    time, and failing closed for separation-sensitive operations where it is
>    nonetheless found in existing data.

Later clarification, on disclosure (accepted at the Slice 0 authorization
sub-gate):

> `CLAIM_AUTHORITY_CONFLICT` must be explicit internally (audit/operations),
> but external disclosure remains concealment-safe. An unrelated actor still
> receives 404. A known conflicting claimant or authorized staff may receive a
> typed 409 without disclosure of the other claimant's identity or conflict
> details.

---

## Where each half is enforced, in the files included here

| Invariant | Half | File in this bundle | Symbol |
|---|---|---|---|
| INV-1 | read | `03_IMPLEMENTATION/auth/loaders.py` | `claim_authority_accounts`, `ClaimAuthorityConflict` |
| INV-1 | write | `03_IMPLEMENTATION/services/claims.py` | `claim_record`, `ResourceAlreadyClaimed`, `ClaimAuthorityConflictExists` |
| INV-1 | disclosure | `03_IMPLEMENTATION/services/access.py` | `_may_learn_of_conflict` |
| INV-2 | grant time | `03_IMPLEMENTATION/services/roles.py`, `auth/roles.py` | `grant_role`, `invalid_role_combination`, `INCOMPATIBLE_ROLE_PAIRS` |
| INV-2 | fail closed | `03_IMPLEMENTATION/auth/policy.py` | `DenyReason.ROLE_CONFIGURATION_ANOMALY`, `SEPARATION_SENSITIVE_OPERATIONS` |
| INV-2 | detection in existing data | `03_IMPLEMENTATION/services/roles.py` | `find_role_anomalies` |

## Tests

- INV-1: `05_TESTS/test_inv1_claim_authority.py` (12 cases) and, for the
  disclosure clarification, `tests/test_conflict_disclosure.py` inside the
  source archive (13 cases).
- INV-2: `tests/test_inv2_separation.py` inside the source archive (15 cases).

## Relevance to this review

INV-1 is what Slice 2's claim work sits on top of. CORRECTION-003 adds the
**eligibility** half the frozen contract declares — whether this claimant is
the right person at all — which INV-1 never covered: INV-1 governs conflicts
*between* claimants. Both now run inside the same write transaction, under a
row lock, so a race cannot create the ambiguous state INV-1 exists to detect.
See `01_CONTRACT/CORRECTION-003-claim-eligibility.md` §3.
