# TURAB — Migration policy

**Ref:** RFC-001 §14.2 (R14.4–R14.7); `IMPLEMENTATION_SLICES_v0.2.md`
slice-completion criterion *"migration can rebuild an empty environment"*.
**Established:** 2026-09-19, before Slice 2 — the first slice that changes the
schema.

---

## 1. The rule

**The frozen schema is the initial migration.** Revision
`0001_frozen_baseline_v0_2_3` applies
`docs/handoff/04_DATABASE/schema_v0.2.3.sql` **verbatim**, as bytes read from
the vendored handoff package. It contains no transcription of that file, so
there is no second copy of the baseline that can drift from the first.

Everything else follows from not having a second copy.

## 1a. The guarantee, split — added at revision `0003`

Until `0003`, every migration added DATA, so a database at `head` was
structurally IDENTICAL to one built from the frozen file, and the suite
asserted exactly that. `0003` changes a function body. The sentence stops being
true, and the wrong response would be to weaken the fingerprint until it passes
again.

The guarantee is **split into two**, and each half is stronger for being stated
separately:

**Baseline guarantee — absolute, no exceptions.**

    upgrade 0001  ⇒  structurally identical to schema_v0.2.3.sql

Function bodies included. Nothing excluded. **No delta may ever apply here** —
a delta naming revision `0001` would be editing the frozen schema through the
back door, and a test refuses it.

**Head guarantee — the baseline plus named, digested deltas, and nothing else.**

    upgrade head  ⇒  the frozen baseline + the deltas declared in
                     db/gate/migration_deltas.py, with no undeclared difference

**What "no undeclared difference" covers, stated to match the machine.** The
structural description is `turab`'s objects **plus every installed extension**
(name, schema and version) — `plpgsql` included. An earlier version excluded
`plpgsql` as "always there", which is an unexplained exception in a check whose
value is having none: it is installed by default, but it can be dropped and its
version moves with the server. Listing it costs one constant row on each side
of every comparison and removes a carve-out that would otherwise need
defending. Extensions were added to it when `0004` needed
`btree_gist`: a `turab`-only view could not see an extension at all, which made
the sentence wider than the check behind it. Anything else outside `turab` —
privileges, ownership, other schemas, row data — is still **not** covered, and
is named here rather than implied.

There is deliberately **no general "ignore these objects" list**. Each delta
names one object and records six things:

| field | why it is required |
|---|---|
| `revision` | one delta belongs to one migration, so a change is attributable |
| `object_name` + `section` | which catalog object, in which part of the fingerprint |
| `kind` | what it is, in words, for a reader rather than for code |
| `digest_before` / `digest_after` | **both** pinned, so the entry cannot widen: if the object changes again, `digest_after` stops matching and the check fails until a new delta is declared |
| `reason` | why it changed — a sentence, not a ticket number |
| `proven_by` | the BEHAVIOURAL test. A digest proves the text changed; only a test proves the change was the right one |

Both directions are checked. An undeclared difference fails, **and** a declared
delta that is not actually present fails — so the ledger can neither hide a
change nor claim one that never happened.

So the strongest sentence in this policy is not lost. It becomes more precise:

> Revision `0001` matches the frozen baseline exactly, and `head` matches that
> baseline plus named, digested, approved deltas, with no undeclared
> difference.

**What this cost, stated plainly.** Before `0003`, "head is the frozen
baseline" needed no list to read. Now a reviewer must also read the ledger and
judge each entry. That is the real price of correcting a frozen baseline at
all, and it is paid deliberately rather than by loosening a check.

**It found three defects on its first real uses**, each recorded rather than
tidied away:

1. `0004` ran `CREATE EXTENSION btree_gist` under
   `search_path = turab, public`, installing about sixty support functions into
   `turab`. The head check reported every one. Pinned with `SCHEMA public` —
   and, because `IF NOT EXISTS` does **not** relocate an extension that already
   exists elsewhere, `0004` now refuses outright when it finds `btree_gist` in
   another schema, before adding the constraint.
2. The head check itself compared every section as `(name, definition)`. For
   constraints that keyed by TABLE and hashed the constraint NAME, so several
   constraints on one table collapsed into one entry and an added constraint
   was invisible. Fixed with a per-section identity split that raises on an
   unclassified section rather than comparing it blindly.
3. The fingerprint had two blind spots of its own: columns were described by
   `information_schema.data_type`, so `numeric(14,2)` and `numeric(20,3)` were
   both "numeric"; and functions were identified by bare name, so an added
   OVERLOAD hid behind the original. Now `format_type(atttypid, atttypmod)`
   and `name(identity arguments)`, each with a mutation test that makes the
   change and asserts it is reported.

### 1b. A claim this policy used to make, corrected

This table previously said that after stamping, `upgrade head` "is a no-op".
That was true only while every revision after the baseline added DATA. Stamping
marks `0001`, so the **first** upgrade necessarily applies `0002`, `0003` and
`0004`. The test behind the claim compared table counts, which none of those
three changes — so it passed while describing the opposite of what happened.

The accurate statement, and what is now asserted in three steps:

1. after stamping, the version is `0001` and the database carries the **frozen**
   `enforce_consent_binding` (no `valid_from`);
2. the first `upgrade head` reaches head and the deltas are visibly applied —
   the corrected gate, the overlap constraint, and the `REQUEST_CLOSURE` codes;
3. the **second** upgrade is the real no-op, asserted by an unchanged
   structural fingerprint rather than by a count.

## 2. What is mechanically prevented

| Hazard | What stops it | Test |
|---|---|---|
| A local edit to the vendored schema silently becoming an approved schema change | The revision verifies the file's SHA-256 **before executing it** and refuses on mismatch | `test_the_migration_refuses_a_baseline_that_is_not_the_frozen_one` |
| The digest guard being compared against a stale constant | The declared digest is asserted equal to the file's | `test_the_declared_digest_is_the_frozen_one` |
| Autogenerate proposing a migration that drops the baseline | `env.py` sets `target_metadata = None`, so Alembic refuses `--autogenerate` before writing any revision file | `test_autogenerate_is_refused`, `test_env_declares_no_metadata_to_diff_against` |
| A second root revision nobody noticed | One head asserted | `test_there_is_exactly_one_head` |
| A development database invisible to Alembic | `reset_db.sh` stamps the **initial** revision, so the baseline is not re-applied onto itself. The first `upgrade head` then applies `0002`–`0004`; the SECOND is the no-op — see the correction below | `test_a_stamped_database_is_already_at_head`, `test_the_first_upgrade_after_stamping_applies_the_later_revisions`, `test_the_dev_reset_script_stamps` |
| A migration that "runs" but builds a partial schema | The migrated catalog is compared to the static audit's **independent parse** of the same file | `test_the_migrated_catalog_matches_the_static_audit` |

The last row is the one that carries weight. The other checks ask whether the
migration ran; that one asks whether it produced the right database, and it
answers using a number derived by different means from a different
representation: `STATIC_AUDIT_RESULTS_v0.2.3.json` counts statements in SQL
text, and PostgreSQL reports what it actually built. Agreement across 48
tables, 54 enum types, 17 functions, 37 triggers and 131 foreign keys is
evidence; a single run of the file compared against itself would not be.


## 2a. The approved stamping path, and what lies outside it

Stated exactly, because a protection described more broadly than it is becomes
a false assurance:

| | |
|---|---|
| **Protected** | the approved administrative path: `db/dev/reset_db.sh`, and any direct use of `db/dev/stamp_baseline.py`. A stamp there is refused unless the database is structurally identical to one built from the frozen schema, and refused if the database is already stamped at a different revision. |
| **Outside it** | a hand-run `alembic stamp`, or any direct `INSERT` into `alembic_version`. Whoever holds database credentials can do either. |

**This is not treated as a gap to close.** The project does not attempt to
prevent a database administrator from bypassing the project's own tooling —
that person can already run arbitrary DDL, so a tool-level guard would be
theatre. What is in scope is that TURAB's own tooling never stamps blindly,
and that the approved path is documented so it can be the one people use.

The two kinds of evidence stay complementary and neither substitutes for the
other:

- the **structural fingerprint** compares definitions — columns, constraints,
  indexes, triggers, function bodies, enum labels;
- the **70-assertion gate** tests BEHAVIOUR against the frozen SQL (R14.7).

Two schemas can be structurally identical and still behave differently under
data and concurrency, which is why the gate is not replaced by the
fingerprint; and behaviour tests can pass on a schema with a silently renamed
index, which is why the fingerprint is not replaced by the gate.

## 3. Deliberate absences

Two things are missing on purpose, and both are pinned by a test, because a
deliberate absence is exactly what a later well-meaning edit restores.

**No `target_metadata`.** TURAB has no declarative models — the services issue
explicit SQL against the frozen schema — so autogenerate would compare
"nothing declared" against 48 tables and obligingly emit a migration dropping
the baseline. `None` makes Alembic refuse outright.

**No `downgrade()` from the baseline.** Dropping the baseline is not a
migration. It is `db/dev/reset_db.sh`, which says so in its name and refuses
to run against a database whose name looks like production or staging.

An earlier draft of `env.py` carried a `process_revision_directives` hook
meant to refuse autogenerate with a fuller message. Alembic rejects the
command before that hook is ever reached, so the hook was unreachable — a
check that reads as a guarantee while providing none. It was removed rather
than kept, and the test now pins Alembic's real refusal.

## 4. Writing a migration from here

1. **Write it by hand.** Autogenerate is unavailable, by design.
2. **A migration that alters anything in the frozen schema needs the
   schema-change approval path** (R14.6) — the same path that produced
   v0.2.2 and v0.2.3. Corrections to the baseline arrive as a new official
   handoff package, not as a local migration.
3. **A migration that adds new objects** (Slice 2 onward) is ordinary work and
   does not touch the frozen digests.
4. **The 70-assertion gate keeps running against the frozen SQL**, never
   against models or migrations (R14.7). It is the independent check that the
   application has not drifted from the baseline.

## 5. Commands

```bash
# Build a development database and stamp it (the normal path)
PGDATABASE=turab_dev db/dev/reset_db.sh --fixtures

# Build one by migrating instead, to prove the migration still rebuilds zero
createdb turab_migration_check
TURAB_DATABASE_URL=postgresql+psycopg:///turab_migration_check alembic upgrade head

alembic current      # which revision a database is at
alembic heads        # must print exactly one
```

`TURAB_DATABASE_URL` is the only source of the connection URL — the same
variable the application reads. `alembic.ini` deliberately declares none, so a
migration cannot be run against a database nobody named.
