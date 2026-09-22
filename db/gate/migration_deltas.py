#!/usr/bin/env python3
"""The declared structural deltas between the frozen baseline and `head`.

Ref: RFC-001 R14.4-R14.7; `docs/gate/MIGRATION_POLICY.md` §1a.

## Why this file exists

Until revision `0003`, every migration added DATA, so a database at `head` was
structurally IDENTICAL to one built from `schema_v0.2.3.sql`, and the migration
suite asserted exactly that. `0003` changes a function body, which is
structure, so that sentence stops being true — and the wrong response would be
to weaken the fingerprint until it passes.

The guarantee is SPLIT instead, and each half is stronger for being stated
separately:

  * **Baseline guarantee — unchanged, absolute, no exceptions.**
    `upgrade 0001` is structurally identical to the frozen file. Function
    bodies included; nothing excluded; no delta may apply to it.

  * **Head guarantee — the frozen baseline PLUS these deltas, and nothing
    else.** Every difference is named here with the revision that causes it,
    the object, its kind, its digest BEFORE and AFTER, why it changed, and the
    behavioural test that proves the change does what it claims.

There is deliberately no general "ignore these objects" list. A delta names one
object and pins BOTH of its digests, so it cannot silently widen: if the object
changes again, the recorded `after` digest stops matching and the test fails
until a new delta is declared. An entry here is therefore a statement that can
become false, which is what makes it evidence.

So the strongest sentence in the migration policy is not lost; it becomes more
precise:

    revision 0001 matches the frozen baseline exactly, and `head` matches that
    baseline plus named, digested, approved deltas — with no undeclared
    difference.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Delta:
    """One approved structural difference between the baseline and `head`."""

    #: The Alembic revision that introduces it. One delta, one revision.
    revision: str
    #: The catalog section it appears in, as `baseline_fingerprint.describe`
    #: names it: columns, constraints, indexes, triggers, functions, enums.
    section: str
    #: The object's identity WITHIN that section — its row minus the definition
    #: text. For a function that is its name; for an index, table and name.
    object_name: str
    #: What kind of object, in words, for a reader rather than for code.
    kind: str
    #: sha256 of the object's definition as the catalog reports it, BEFORE.
    #: `None` means the object does not exist in the baseline at all.
    digest_before: str | None
    #: sha256 of the same definition AFTER the migration. `None` means the
    #: migration removes it.
    digest_after: str | None
    #: Why it changed. A sentence, not a ticket number.
    reason: str
    #: The BEHAVIOURAL test that proves the new definition does what the reason
    #: claims. A fingerprint proves the text changed; only this proves the
    #: change was the right one.
    proven_by: tuple[str, ...]


def digest(definition: str) -> str:
    """The digest recorded in a delta: sha256 of the definition text."""
    return hashlib.sha256(definition.encode()).hexdigest()


#: How many leading columns of a `describe()` row IDENTIFY the object, the rest
#: being its definition. Getting this wrong is not a cosmetic bug: a first
#: version of the head check treated every section as `(name, definition)`, so
#: for constraints it keyed by TABLE and hashed the constraint NAME. Several
#: constraints on one table collapsed into one entry, and an added constraint
#: was invisible. It was found by adding one in `0004` and noticing the check
#: stayed silent — so the table below is written out per section rather than
#: guessed from the row length.
_IDENTITY_COLUMNS = {
    "columns": 2,      # (table, column) + type, nullability, default, ordinal
    "constraints": 2,  # (table, name)   + pg_get_constraintdef
    "indexes": 2,      # (table, name)   + indexdef
    "triggers": 2,     # (table, name)   + pg_get_triggerdef
    "functions": 1,    # (name,)         + pg_get_functiondef
    "enums": 2,        # (type, label)   + sort order
    "extensions": 1,   # (name,)         + schema, version
}


def split_row(section: str, row) -> tuple[str, str]:
    """Return `(object_name, definition)` for one `describe()` row.

    An unknown section is a hard error rather than a guess: a section added to
    the fingerprint without being classified here would otherwise be compared
    the wrong way round and quietly stop detecting anything.
    """
    if section not in _IDENTITY_COLUMNS:
        raise KeyError(
            f"section {section!r} has no identity/definition split declared in "
            "migration_deltas._IDENTITY_COLUMNS; add one rather than letting "
            "the head-delta check compare it blindly"
        )
    n = _IDENTITY_COLUMNS[section]
    parts = [str(x) for x in row]
    return ".".join(parts[:n]), "\x1f".join(parts[n:])


#: Every approved delta, in revision order. Adding an entry here is a decision;
#: it is not a way to make a failing test pass.
DELTAS: tuple[Delta, ...] = (
    Delta(
        revision="0003_consent_relation_currency",
        section="functions",
        object_name="enforce_consent_binding()",
        kind="trigger function body",
        # Filled from the live catalog by `record_digests()` and pinned below.
        digest_before="c1c1a38278e644e59c32a3bd862a7f46ee500f9694ca70ca94c19088d1c8a614",
        digest_after="8b339c86fe950a17310b364b0086f7b1fcfb432626251a1456bcf7a04371dea6",
        reason=(
            "The frozen function tests `valid_to` only, so a party-property "
            "relation that has not started — or has no start at all — passes "
            "the property-scoped consent gate. RFC-001 R4.6 defines relation "
            "currency as `valid_from <= now() < valid_to` and names "
            "`enforce_consent_binding()` as use 2, which that currency governs. "
            "The migration makes the function implement the predicate the RFC "
            "declares (G3-7)."
        ),
        proven_by=(
            "test_a_current_relation_permits_a_property_consent_binding",
            "test_a_future_relation_is_refused",
            "test_a_relation_with_no_start_is_refused",
            "test_an_expired_relation_is_refused",
            "test_no_relation_at_all_is_refused",
            "test_another_partys_relation_is_refused",
        ),
    ),
    Delta(
        revision="0004_relation_overlap_guard",
        section="constraints",
        object_name="party_property_relations.party_property_relations_no_overlap",
        kind="EXCLUDE USING gist constraint",
        digest_before=None,          # it does not exist in the baseline
        digest_after="d47372e163c0f26319889edea06fb477002651b96f16dcc68f17d96fb882e9f7",
        reason=(
            "At most one relation may be current at a time for the same "
            "(party_id, property_id, relation_code). The frozen schema has no "
            "uniqueness or exclusion constraint on the triple, so the rule "
            "would otherwise be the one uniqueness rule in Slice 3 with no "
            "database backstop, depending on a service pre-check being "
            "remembered. `tstzrange` with `&&` states it as what it is — no "
            "two validity periods for one triple may intersect — where a "
            "partial unique index would miss an open-ended row overlapping a "
            "closed one that has not ended yet."
        ),
        proven_by=(
            "test_two_overlapping_relations_for_one_triple_are_refused",
            "test_a_relation_resumed_after_the_previous_one_ended_is_allowed",
            "test_a_different_relation_code_never_conflicts",
            "test_a_different_party_never_conflicts",
            "test_a_relation_with_no_start_still_participates_in_the_guard",
        ),
    ),
    Delta(
        revision="0004_relation_overlap_guard",
        section="indexes",
        object_name="party_property_relations.party_property_relations_no_overlap",
        kind="gist index backing the EXCLUDE constraint",
        digest_before=None,
        digest_after="700eef3d7a3ad8b60dc487706b6ad578aa77ea23cbe7d37215cf1da1f645eae6",
        reason=(
            "PostgreSQL implements an EXCLUDE constraint with an index of the "
            "same name, so the constraint above necessarily brings a second "
            "catalog object. It is declared separately rather than folded into "
            "the constraint's entry, because the check compares objects and a "
            "delta that covered two would have to guess which digest belonged "
            "to which. Finding this was the point: the first version of the "
            "head check keyed constraints by TABLE and hashed the constraint "
            "NAME, so it saw neither object."
        ),
        proven_by=(
            "test_two_overlapping_relations_for_one_triple_are_refused",
        ),
    ),
    Delta(
        revision="0004_relation_overlap_guard",
        section="extensions",
        object_name="btree_gist",
        kind="PostgreSQL extension, installed in `public`",
        digest_before=None,          # not installed in the baseline
        digest_after="f992ad1dfc4bc45e858b9bab5b868074265dc443f6fe4a9866b0b83c40f2695e",
        reason=(
            "An EXCLUDE constraint mixing equality on uuid/text with `&&` on a "
            "range requires `btree_gist`. It is declared here because the "
            "fingerprint now covers extensions: it previously saw only the "
            "`turab` schema, so an extension installed by a migration was "
            "outside the machine that the phrase 'no undeclared difference' "
            "rested on. Its schema is part of the digest, so moving it would "
            "be a change this check reports rather than tolerates."
        ),
        proven_by=(
            "test_btree_gist_is_installed_in_public",
            # NOTE: the digest covers name, schema AND version, as required.
            # That makes it server-dependent: a PostgreSQL shipping
            # btree_gist 1.8 would report a different digest and fail this
            # check until the delta is updated. That is the intended
            # behaviour — an extension version IS part of what the database
            # is — but it is stated here rather than discovered on an
            # upgrade.
            "test_0004_refuses_a_btree_gist_installed_outside_public",
        ),
    ),
)


def for_revision(revision: str) -> tuple[Delta, ...]:
    return tuple(d for d in DELTAS if d.revision == revision)


def expected_after(section: str, object_name: str) -> str | None:
    """The digest an object is approved to have at `head`, or `None` if it has
    no delta and must therefore match the baseline exactly."""
    for d in DELTAS:
        if d.section == section and d.object_name == object_name:
            return d.digest_after
    return None


def declared_objects() -> frozenset[tuple[str, str]]:
    return frozenset((d.section, d.object_name) for d in DELTAS)
