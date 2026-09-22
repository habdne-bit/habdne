# G3-7 · `enforce_consent_binding()` ignores `valid_from`

**Status:** **RESOLVED.** Ratified and implemented as revision
`0003_consent_relation_currency`. The sections below keep the analysis as
submitted; §11 records what was decided and what was built.
**Raised by:** the reviewer, on the Slice 3 plan rev 3 / G3-6 Delta round.
**Classification:** a defect **in the frozen baseline**, not in TURAB's code.
**Confirmed:** by reading both sources and by execution on PostgreSQL 16.13.

---

## 1. The divergence

**RFC-001 R4.6** (`docs/rfc/RFC-001-object-level-authorization.md:230`) defines
relation currency and names the uses it governs:

> **R4.6** Relation currency (`valid_from <= now() < valid_to`) still governs
> uses 1 and 2.

And **use 2** is this function by name (`:218`):

> 2. **Consent binding validity.** `enforce_consent_binding()` requires an
>    active relation before a property-scoped consent may bind — verified in
>    the schema.

**The frozen schema** (`docs/handoff/04_DATABASE/schema_v0.2.3.sql:1092-1099`)
implements only half of that definition:

```sql
ELSIF NEW.property_id IS NOT NULL THEN
  IF NOT EXISTS (
    SELECT 1 FROM party_property_relations
    WHERE party_id = grant_party AND property_id = NEW.property_id
      AND (valid_to IS NULL OR valid_to > now())      -- valid_from is never read
  ) THEN
    RAISE EXCEPTION 'Property consent party has no active property relation';
  END IF;
```

`valid_from` is not referenced. So a relation that **has not started**, or that
has **no start at all**, satisfies a gate whose stated rule is
`valid_from <= now() < valid_to`.

This is not a reading of ambiguous text. The RFC names the function, states the
predicate, and the function implements a different one.

## 2. Demonstrated, not inferred

Run on the test database (PostgreSQL 16.13), each case in a rolled-back
transaction, on a property for which the consenting party had **no** relation:

```
=== CASE A: relation starting in 2099 — NOT active per R4.6 ===
INSERT 0 1        <- the relation
INSERT 0 1        <- the property-scoped consent binding: ACCEPTED

=== CASE B: valid_from = NULL — no start at all ===
INSERT 0 1        <- the relation
INSERT 0 1        <- the property-scoped consent binding: ACCEPTED
```

Both should have been refused. For contrast, with **no relation row at all**
the gate does fire:

```
ERROR:  Property consent party has no active property relation
CONTEXT:  PL/pgSQL function enforce_consent_binding() line 33 at RAISE
```

So the gate exists and works — it is simply checking a weaker predicate than
the one the RFC declares.

## 3. Why it matters, stated at its real size

A consent binding is ADR-04's proof that a specific consent authorises a
specific purpose on a specific resource. If the relation backing it is not yet
in force, the binding rests on a relationship that does not exist **yet**. The
failure mode is a property-scoped consent accepted on the strength of a future
or unstarted relation.

Two things keep this from being an active exploit today, and neither is a
reason to leave it:

- **No API creates a relation** (G3-6), so the row must be inserted directly by
  someone holding database credentials.
- **`party_property_relations` is never an authorization source** (R4.5,
  R4.12), so this cannot widen read or write access to a property or an offer.
  The damage is confined to consent-binding validity — which is precisely what
  ADR-04 exists to make trustworthy.

It becomes materially more important the moment G3-6 lands and relations become
creatable through the API. **G3-7 should therefore be fixed before or with
G3-6, not after it.**

## 4. TURAB's own code does not repeat the error

Checked, so the fix is scoped correctly: no module reads
`party_property_relations` for currency, or at all. `load_property`
(`src/turab/auth/loaders.py:190`) documents its absence deliberately, and an
architecture test asserts the policy layer never queries the table (R4.5). The
only consumer is the frozen trigger.

**Nothing in the service layer can fix this**, either: the function is a
`BEFORE INSERT OR UPDATE` trigger on `resource_consent_bindings`, so it runs
inside the database on every write, including writes our code does not make. A
pre-check in `postConsentsBindings` would tighten our own path while leaving the
gate itself weak. The correction belongs in the function.

## 5. Proposed migration

A new Alembic revision, `0003_consent_relation_currency`, replacing the
function with one that implements R4.6's predicate:

```sql
CREATE OR REPLACE FUNCTION enforce_consent_binding() ...
  -- unchanged except for the property branch:
  ELSIF NEW.property_id IS NOT NULL THEN
    IF NOT EXISTS (
      SELECT 1 FROM party_property_relations
      WHERE party_id = grant_party AND property_id = NEW.property_id
        AND (valid_from IS NOT NULL AND valid_from <= now())
        AND (valid_to   IS NULL     OR  valid_to   >  now())
    ) THEN
      RAISE EXCEPTION 'Property consent party has no active property relation';
    END IF;
```

Three points on which we want an explicit decision rather than our assumption:

**5.1 `valid_from IS NULL` — refuse, or treat as "always started"?**
R4.6 reads `valid_from <= now()`, which a NULL cannot satisfy, and the
reviewer's instruction is to prevent a `valid_from = NULL` relation from
passing. The proposal above therefore **refuses NULL**. The alternative reading
— NULL meaning "no known start, so unbounded" — is defensible for other
purposes, and is how `valid_to IS NULL` is treated on the closing side. We are
taking the stricter reading because this is a consent gate, but the asymmetry
is deliberate and worth your confirmation.

**5.2 Existing rows.** The migration changes the rule for **future** bindings.
It does not, and should not, retroactively invalidate bindings already made —
historical snapshots stay intact (ADR-04's invariant). If any existing binding
would not pass the new rule, that is a data question to report, not something a
migration should silently rewrite. The migration will therefore **report** such
rows rather than alter them. On the current test database, none exist.

**5.3 Whether the other branches change.** They do not. The request, offer and
thread branches compare a party directly and involve no temporal validity. Only
the property branch is touched.

## 6. The consequence for the gate machinery — the part that needs deciding

`0003` would be **the first migration that changes the baseline's structure.**
`0002_request_closure_reasons` inserts rows only, and row data is invisible to
the structural fingerprint. A function body is not.

`tests/test_migrations.py:340`,
`test_the_migrated_database_is_structurally_identical_to_the_frozen_schema`,
asserts a database at head is structurally **identical** to one built from the
frozen schema, and the fingerprint deliberately covers **function bodies** —
`test_the_fingerprint_notices_a_changed_function_body` exists precisely to
prove it would catch this.

So the migration that fixes G3-7 **will make that test fail, by design.** That
is the machinery working, not breaking. It needs a decision:

| Option | Shape |
|---|---|
| **A — a declared delta list** *(proposed)* | the test asserts: migrated == frozen baseline **+ the approved structural deltas**, each named with its revision and its reason. Anything not on that list still fails. The guarantee narrows from "identical" to "identical except where we approved a change, and here is the list" |
| **B — compare against a new reference** | regenerate the reference from head. Rejected: it compares the migrations against themselves and destroys the independent second source that gives the test its value |
| **C — leave the baseline unfixed** | the defect stands; the gate keeps its simple invariant |

We propose **A**, and note what it costs: the strongest sentence in the
migration policy — "the migrated catalog matches an independent parse of the
frozen file" — becomes conditional, and every future condition must be
justified. That is the honest price of correcting a frozen baseline at all, and
it should be paid deliberately, once, with the list starting at exactly one
entry.

**We will not write `0003` until this is decided**, because choosing wrong here
quietly weakens the one check that proves a migration built the right database.

## 7. What is asked

1. Confirmation of the predicate in §5, including the **NULL `valid_from`**
   reading in §5.1.
2. A decision on §6 — option A, B or C.
3. Confirmation that G3-7 is fixed **before or with** G3-6, so relations are
   never creatable through the API while the gate is weak.

Until then: no migration is written, no relation row is created by any path,
and the property-scoped consent branch stays as described in the G3-6 Delta.


---

## 11. Decided and implemented

**The predicate, adopted verbatim as ratified:**

```sql
valid_from IS NOT NULL
AND valid_from <= now()
AND (valid_to IS NULL OR now() < valid_to)
```

`valid_from IS NULL` is **refused**. The asymmetry with `valid_to IS NULL` —
which does mean "still open" — is deliberate, and both halves are pinned by
tests (`test_a_relation_with_no_start_is_refused`,
`test_an_open_ended_relation_is_still_current`).

**Classification, as confirmed:** a defect in the frozen baseline; the baseline
file is **not** edited; it is corrected by a forward migration; a service check
would not be sufficient, because the trigger is the database-level guarantee
for every write path.

**The eight required proofs**, each a separate test:

| case | test |
|---|---|
| a current relation permits the binding | `test_a_current_relation_permits_a_property_consent_binding` |
| a future relation is refused | `test_a_future_relation_is_refused` |
| `valid_from = NULL` is refused | `test_a_relation_with_no_start_is_refused` |
| an expired relation is refused | `test_an_expired_relation_is_refused` |
| no relation at all is refused | `test_no_relation_at_all_is_refused` |
| another party's relation is refused | `test_another_partys_relation_is_refused` |
| re-running the migration is safe | `test_0003_is_re_runnable` |
| `0001` then `upgrade head` equals a direct upgrade | `test_building_from_0001_then_upgrading_head_matches_a_direct_upgrade` |

plus `test_an_open_ended_relation_is_still_current`, which pins the other half
of the NULL asymmetry, and `test_the_migrated_function_reads_valid_from`, so a
database that was never migrated fails with one clear reason rather than six
confusing ones.

**Mutation check, as required.** Removing `AND valid_from IS NOT NULL AND
valid_from <= now()` from the migration fails exactly the targeted tests —
`test_a_future_relation_is_refused`, `test_a_relation_with_no_start_is_refused`
and `test_the_migrated_function_reads_valid_from` — and nothing else.

**`downgrade()` refuses.** Reverting restores a gate that accepts an unstarted
or future relation, so it raises rather than performing a silent security
rollback, and `test_0003_refuses_to_downgrade` asserts both the refusal and
that the version is left untouched. Recovery, if ever wanted, is an explicit
forward migration that states why.

**The fingerprint is not weakened**, it is split — see
`docs/gate/MIGRATION_POLICY.md` §1a. `0003`'s only approved delta is the body
of `turab.enforce_consent_binding()`, pinned by both its before and after
digests. `test_the_delta_check_catches_an_undeclared_structural_change` proves
the detector bites.

**The overlap guard is `0004`, separately**, so each structural change stays
attributable to one decision. It is an `EXCLUDE USING gist` constraint rather
than a service check — which removes the weakness the G3-6 Delta §6 had to
declare, that the rule would otherwise have no database backstop.
