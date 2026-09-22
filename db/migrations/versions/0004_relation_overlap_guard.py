"""No two overlapping relations for one (party, property, relation_code).

Revision ID: 0004_relation_overlap_guard
Revises: 0003_consent_relation_currency

Deliberately a SEPARATE revision from `0003`, so each structural change stays
attributable to one decision. `0003` corrects when a relation is in force;
this decides how many may be in force at once. They are different rules and a
reviewer should be able to revert or re-examine either without the other.

## The rule

At most one relation may be current at a time for the same
`(party_id, property_id, relation_code)`. Creating a second while one is
current is refused.

Different `relation_code` values never conflict — a party may be both
`OWNER_DECLARED` and `CONTACT_PERSON` — and two different parties may hold the
same code on one property, which is how two brokers are represented.

## Why in the database, not the service

The G3-6 Delta proposed enforcing this in the service under a lock, and noted
honestly that it would then be the one uniqueness rule in the slice with **no
database backstop**. With a migration now authorised, that weakness is
unnecessary: an exclusion constraint makes the rule true of every writer,
including an importer, a fixture and a hand-run `INSERT`. The service still
pre-checks so the caller gets a typed 409 rather than a raw violation, but the
guarantee no longer depends on that pre-check being remembered.

## Why an EXCLUSION constraint rather than a partial unique index

"Current" is an interval, not a flag. A partial unique index on
`WHERE valid_to IS NULL` would stop two open-ended relations but allow an
open-ended one to overlap a closed one that has not ended yet — which is the
same rule failing on the case it exists for. `tstzrange` with `&&` states the
rule as what it actually is: no two ranges for the same triple may intersect.

`valid_from` is NULL-able in the frozen schema, and a NULL start is refused by
the `0003` gate rather than treated as unbounded. The range therefore uses
`coalesce(valid_from, '-infinity')`, so a row with no start still participates
in the check instead of escaping it — a row that cannot satisfy the consent
gate should not be able to sit invisibly under this one either.

## Existing data

Overlaps already present would make `ADD CONSTRAINT` fail. The upgrade counts
them FIRST and raises a clear error naming them, rather than letting PostgreSQL
report a constraint violation with no context. It does not delete or adjust any
row: resolving an overlap is an operational decision about which relation is
real, and a migration must not make it.

## btree_gist, and a mistake the delta check caught

An exclusion constraint mixing equality on uuid/text with `&&` on a range needs
`btree_gist`. The first version of this migration ran
`CREATE EXTENSION IF NOT EXISTS btree_gist` after `SET LOCAL search_path TO
turab, public` — which installed roughly sixty support functions **into the
`turab` schema**. The head-delta check reported every one of them as an
undeclared structural difference, and the static-audit function count failed
too. Both were right: the schema really had changed in a way nobody had
declared.

It is therefore pinned to `public` with an explicit `SCHEMA public`, so the
only thing this revision adds to `turab` is the constraint itself — which is
the one declared delta. This is exactly the failure the split guarantee exists
to make visible, caught on its first real use.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0004_relation_overlap_guard"
down_revision = "0003_consent_relation_currency"
branch_labels = None
depends_on = None

CONSTRAINT = "party_property_relations_no_overlap"

RANGE = (
    "tstzrange(coalesce(valid_from, '-infinity'::timestamptz), "
    "valid_to, '[)')"
)


def upgrade() -> None:
    # Pinned to `public`: without SCHEMA the extension follows search_path and
    # installs its support functions into `turab` (see the docstring).
    op.execute("CREATE EXTENSION IF NOT EXISTS btree_gist SCHEMA public")
    op.execute("SET LOCAL search_path TO turab, public")

    overlaps = op.get_bind().execute(
        sa.text(
            f"""SELECT count(*) FROM turab.party_property_relations a
                  JOIN turab.party_property_relations b
                    ON a.party_property_relation_id < b.party_property_relation_id
                   AND a.party_id = b.party_id
                   AND a.property_id = b.property_id
                   AND a.relation_code = b.relation_code
                   AND {RANGE.replace('valid_from', 'a.valid_from').replace('valid_to', 'a.valid_to')}
                    && {RANGE.replace('valid_from', 'b.valid_from').replace('valid_to', 'b.valid_to')}"""
        )
    ).scalar_one()
    if overlaps:
        raise RuntimeError(
            f"{overlaps} overlapping party-property relation pair(s) already "
            "exist. This migration will not choose which of them is real — "
            "resolve them operationally (end one, or correct its dates) and "
            "re-run. No row has been changed."
        )

    op.execute(
        f"""ALTER TABLE turab.party_property_relations
            ADD CONSTRAINT {CONSTRAINT} EXCLUDE USING gist (
                party_id WITH =,
                property_id WITH =,
                relation_code WITH =,
                {RANGE} WITH &&
            )"""
    )


def downgrade() -> None:
    """Allowed, unlike 0003's.

    Dropping this constraint permits overlapping relations again. That is a
    data-quality regression, not a security one: relations grant no access
    authority (R4.5, R4.12), and the `0003` consent gate still refuses a
    relation that is not in force. So a reversible constraint is the honest
    classification here, and the asymmetry with 0003 is deliberate rather than
    an inconsistency.
    """
    op.execute(
        f"ALTER TABLE turab.party_property_relations "
        f"DROP CONSTRAINT IF EXISTS {CONSTRAINT}"
    )
