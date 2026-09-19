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

## 2. What is mechanically prevented

| Hazard | What stops it | Test |
|---|---|---|
| A local edit to the vendored schema silently becoming an approved schema change | The revision verifies the file's SHA-256 **before executing it** and refuses on mismatch | `test_the_migration_refuses_a_baseline_that_is_not_the_frozen_one` |
| The digest guard being compared against a stale constant | The declared digest is asserted equal to the file's | `test_the_declared_digest_is_the_frozen_one` |
| Autogenerate proposing a migration that drops the baseline | `env.py` sets `target_metadata = None`, so Alembic refuses `--autogenerate` before writing any revision file | `test_autogenerate_is_refused`, `test_env_declares_no_metadata_to_diff_against` |
| A second root revision nobody noticed | One head asserted | `test_there_is_exactly_one_head` |
| A development database invisible to Alembic | `reset_db.sh` stamps the initial revision, so `upgrade head` is a no-op instead of re-applying the baseline onto itself | `test_a_stamped_database_is_already_at_head`, `test_upgrading_a_stamped_database_is_a_no_op`, `test_the_dev_reset_script_stamps` |
| A migration that "runs" but builds a partial schema | The migrated catalog is compared to the static audit's **independent parse** of the same file | `test_the_migrated_catalog_matches_the_static_audit` |

The last row is the one that carries weight. The other checks ask whether the
migration ran; that one asks whether it produced the right database, and it
answers using a number derived by different means from a different
representation: `STATIC_AUDIT_RESULTS_v0.2.3.json` counts statements in SQL
text, and PostgreSQL reports what it actually built. Agreement across 48
tables, 54 enum types, 17 functions, 37 triggers and 131 foreign keys is
evidence; a single run of the file compared against itself would not be.

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
