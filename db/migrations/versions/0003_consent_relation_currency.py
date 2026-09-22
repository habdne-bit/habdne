"""Relation currency in the property-scoped consent gate (G3-7).

Revision ID: 0003_consent_relation_currency
Revises: 0002_request_closure_reasons

**This is the first migration in TURAB that changes STRUCTURE.** `0002` added
rows; this replaces a function body. It does not edit the frozen baseline —
`schema_v0.2.3.sql` keeps its digest and revision `0001` still applies it
verbatim — it is the first legitimate structural evolution ON TOP of it.

## The defect

RFC-001 R4.6 defines relation currency as `valid_from <= now() < valid_to`, and
names the two uses that currency governs. Use 2 is this function, by name:

> 2. **Consent binding validity.** `enforce_consent_binding()` requires an
>    active relation before a property-scoped consent may bind.

The frozen function tests `valid_to` alone:

    AND (valid_to IS NULL OR valid_to > now())

`valid_from` is never read. Demonstrated on PostgreSQL 16.13 before this
migration: a relation starting in **2099**, and a relation with
**`valid_from = NULL`**, both let a property-scoped consent bind.

## The correction

The ratified predicate, adopted verbatim:

    valid_from IS NOT NULL
    AND valid_from <= now()
    AND (valid_to IS NULL OR now() < valid_to)

`valid_from IS NULL` is REFUSED rather than read as "unbounded start". A NULL
cannot satisfy `valid_from <= now()`, and this is a consent gate: a relation
whose start nobody recorded is not a relation anyone can show was in force.
The asymmetry with `valid_to IS NULL` — which does mean "still open" — is
deliberate and ratified, not an oversight.

## Scope

**Only the property branch changes.** The request, offer and thread branches
compare a party directly and have no temporal validity; they are reproduced
here byte for byte. The whole function must be restated because PostgreSQL has
no way to replace part of one.

## What it does not do

It does not touch existing `resource_consent_bindings` rows. The rule changes
for FUTURE bindings; historical snapshots stay intact, which is ADR-04's own
invariant. A binding already made that would not pass the new rule is a data
question to REPORT, not something a migration may silently rewrite — so the
upgrade counts them and raises them in the log rather than altering them.

## Re-runnable by design

`CREATE OR REPLACE FUNCTION` is idempotent, and the trigger is not recreated:
it already points at this function by name, so replacing the body is enough.
Re-running the migration produces the same catalog.
"""
from __future__ import annotations

from alembic import op

revision = "0003_consent_relation_currency"
down_revision = "0002_request_closure_reasons"
branch_labels = None
depends_on = None


#: The corrected function. Everything outside the property branch is the
#: frozen definition, unchanged.
CORRECTED = """
CREATE OR REPLACE FUNCTION turab.enforce_consent_binding()
RETURNS trigger LANGUAGE plpgsql AS $fn$
DECLARE
  grant_party uuid;
  grant_scope consent_scope;
  grant_status consent_status;
  resource_party uuid;
BEGIN
  SELECT party_id, scope, status INTO grant_party, grant_scope, grant_status
  FROM consent_grants WHERE consent_id = NEW.consent_id;
  IF NOT FOUND OR grant_status <> 'GRANTED' THEN
    RAISE EXCEPTION 'Consent grant must exist and be GRANTED';
  END IF;
  IF grant_scope <> NEW.purpose THEN
    RAISE EXCEPTION 'Consent grant scope % does not match binding purpose %', grant_scope, NEW.purpose;
  END IF;

  IF NEW.request_id IS NOT NULL THEN
    SELECT party_id INTO resource_party FROM requests WHERE request_id = NEW.request_id;
    IF resource_party IS DISTINCT FROM grant_party THEN
      RAISE EXCEPTION 'Request consent party mismatch';
    END IF;
  ELSIF NEW.offer_id IS NOT NULL THEN
    SELECT party_id INTO resource_party FROM property_offers WHERE offer_id = NEW.offer_id;
    IF resource_party IS DISTINCT FROM grant_party THEN
      RAISE EXCEPTION 'Offer consent party mismatch';
    END IF;
  ELSIF NEW.property_id IS NOT NULL THEN
    -- G3-7. RFC-001 R4.6: valid_from <= now() < valid_to. The frozen version
    -- read valid_to only, so a future or unstarted relation passed this gate.
    IF NOT EXISTS (
      SELECT 1 FROM party_property_relations
      WHERE party_id = grant_party AND property_id = NEW.property_id
        AND valid_from IS NOT NULL
        AND valid_from <= now()
        AND (valid_to IS NULL OR now() < valid_to)
    ) THEN
      RAISE EXCEPTION 'Property consent party has no active property relation';
    END IF;
  ELSIF NEW.thread_id IS NOT NULL THEN
    SELECT party_id INTO resource_party FROM communication_threads WHERE thread_id = NEW.thread_id;
    IF resource_party IS DISTINCT FROM grant_party THEN
      RAISE EXCEPTION 'Communication thread consent party mismatch';
    END IF;
  END IF;
  RETURN NEW;
END $fn$;
"""


def upgrade() -> None:
    op.execute("SET LOCAL search_path TO turab, public")

    # Report, never rewrite. A binding made under the old rule stays; this
    # only makes it visible that it exists.
    rows = op.get_bind().execute(
        __import__("sqlalchemy").text(
            """SELECT count(*) FROM turab.resource_consent_bindings b
                WHERE b.property_id IS NOT NULL
                  AND b.revoked_at IS NULL
                  AND NOT EXISTS (
                        SELECT 1 FROM turab.party_property_relations r
                         JOIN turab.consent_grants g ON g.consent_id = b.consent_id
                         WHERE r.party_id = g.party_id
                           AND r.property_id = b.property_id
                           AND r.valid_from IS NOT NULL
                           AND r.valid_from <= now()
                           AND (r.valid_to IS NULL OR now() < r.valid_to))"""
        )
    ).scalar_one()
    if rows:
        print(
            f"[0003] NOTE: {rows} existing property-scoped consent binding(s) "
            "would not satisfy the corrected relation-currency rule. They are "
            "LEFT AS THEY ARE: historical bindings are not rewritten by a "
            "migration (ADR-04). Review them operationally."
        )

    op.execute(CORRECTED)


def downgrade() -> None:
    """Refused.

    Reverting this restores a gate that accepts a property-scoped consent
    backed by a relation that has not started, or has no start at all. That is
    a **security regression**, and a `downgrade` that performed it silently
    would let one `alembic downgrade` reopen the hole with no record of the
    decision.

    Recovery, if it is ever genuinely wanted, is an explicit forward migration
    that states in its own docstring why the weaker rule is being restored —
    so the decision is reviewable, which a silent revert is not.
    """
    raise RuntimeError(
        "0003 has no downgrade: reverting it restores a consent gate that "
        "accepts an unstarted or future party-property relation (G3-7). If "
        "the weaker rule is genuinely wanted, write a forward migration that "
        "says why."
    )
