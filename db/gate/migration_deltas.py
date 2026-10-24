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
    Delta(
        revision="0005_match_history_immutability",
        section="triggers",
        object_name="match_criterion_results.prevent_match_criterion_result_update",
        kind="BEFORE UPDATE OR DELETE trigger, reusing prevent_immutable_history_change()",
        digest_before=None,
        digest_after="8b64a3152f3f224ffe524d499f50122d3110ccc4ffbe4070cf62f4a033df55e1",
        reason=(
            "The frozen schema guards match_candidates and match_reviews but not "
            "match_criterion_results. A criterion result was measured turning from "
            "FAIL to PASS, and being deleted, under a match row that refused every "
            "change. A match IS its criterion results, so without this guard "
            "mandatory test 8 and G04 cannot hold (G4-14)."
        ),
        proven_by=(
            "test_a_criterion_result_cannot_be_turned_from_fail_to_pass",
            "test_a_criterion_result_cannot_be_deleted",
            "test_a_criterion_result_can_still_be_appended",
            "test_deleting_a_request_criterion_a_result_cites_is_refused",
        ),
    ),
    Delta(
        revision="0005_match_history_immutability",
        section="triggers",
        object_name="match_diagnostic_runs.prevent_match_diagnostic_run_update",
        kind="BEFORE UPDATE OR DELETE trigger, reusing prevent_immutable_history_change()",
        digest_before=None,
        digest_after="5e7d82fabe089a2539206951662a8c89aa90c2831a0efe0d06d76f5a56e8a4a5",
        reason=(
            "A diagnostic run records what a run found for one request version and "
            "policy. It was measured being updated and deleted; a diagnostic that "
            "can be rewritten after the fact is not a record of the run (G4-14)."
        ),
        proven_by=(
            "test_a_diagnostic_run_cannot_be_updated",
            "test_a_diagnostic_run_cannot_be_deleted",
        ),
    ),
    Delta(
        revision="0005_match_history_immutability",
        section="functions",
        object_name="enforce_matching_policy_immutability()",
        kind="trigger function",
        digest_before=None,
        digest_after="7a91ef3bf133d9fdc15bfef1f5f942267bda12a8401db00f16873d30d5e8e54f",
        reason=(
            "matching_policies.immutable is read by nothing in the frozen schema: "
            "an immutable policy was measured accepting a change to its rules and "
            "to its version. This function refuses a change to version, name, "
            "rules or immutable of an immutable policy, and leaves active and "
            "activated_at writable (G4-14)."
        ),
        proven_by=(
            "test_an_immutable_policy_cannot_change",
            "test_an_immutable_policy_can_still_be_activated_and_deactivated",
            "test_a_mutable_policy_is_editable_until_it_is_made_immutable",
        ),
    ),
    Delta(
        revision="0005_match_history_immutability",
        section="triggers",
        object_name="matching_policies.trg_matching_policy_immutable",
        kind="BEFORE UPDATE trigger calling enforce_matching_policy_immutability()",
        digest_before=None,
        digest_after="e543a3551748ea3f225f855d7f8291df86a75875a7a1c4d4f4d057ee1c2aeb14",
        reason=(
            "Attaches the policy guard above to matching_policies. Declared "
            "separately because the check compares catalog objects one by one, "
            "and a function without its trigger would guard nothing."
        ),
        proven_by=(
            "test_an_immutable_policy_cannot_change",
        ),
    ),
    Delta(
        revision="0006_opportunity_history",
        section="functions",
        object_name="enforce_opportunity_history()",
        kind="trigger function",
        digest_before=None,
        digest_after="e5e9c38bfda941027f78680286557c89539d1d4ea999a5427eaf8ae2b5e1b631",
        reason=(
            "The frozen schema refuses a change to an opportunity's request, "
            "property or approved match only through trg_opportunity_gate's "
            "re-check, and nothing else: its snapshots, why_real, sharing_scope, "
            "creator and creation time were measured being rewritten, and every "
            "status move was accepted, CLOSED -> NEW included (step 0, B4-B17). "
            "This function enforces G5-12 (plan revision 4) rules 1-6: a CLOSED "
            "row is final; the creation fields are written once; only the five "
            "edges; the closing fields go with CLOSED; shared_at and engaged_at "
            "are set only on the edge of their own event."
        ),
        proven_by=(
            "test_a_field_written_at_creation_cannot_be_rewritten",
            "test_a_status_change_off_the_graph_is_refused",
            "test_the_closing_fields_go_with_the_closed_status",
            "test_a_closed_opportunity_is_final",
            "test_event_stamps",
            "test_the_writable_columns_stay_writable",
        ),
    ),
    Delta(
        revision="0006_opportunity_history",
        section="triggers",
        object_name="opportunities.trg_opportunity_history",
        kind="BEFORE UPDATE trigger calling enforce_opportunity_history()",
        digest_before=None,
        digest_after="403236d56fdbee127e0c6be43e38d3016ed25edd1e166c2c49b6d53467cc7430",
        reason=(
            "Attaches the history guard above to opportunities. Declared "
            "separately because the check compares catalog objects one by one, "
            "and a function without its trigger would guard nothing."
        ),
        proven_by=(
            "test_a_field_written_at_creation_cannot_be_rewritten",
        ),
    ),
    Delta(
        revision="0006_opportunity_history",
        section="functions",
        object_name="enforce_opportunity_birth()",
        kind="trigger function",
        digest_before=None,
        digest_after="b951d86c956096ae22b6bbab88a4ba6fa724900b5f8b00b98cba103b860718cf",
        reason=(
            "An opportunity could be inserted already SHARED, ENGAGED or CLOSED, "
            "or not VALID, or carrying event times: a history it never lived. "
            "G5-12's birth rule: a new opportunity is NEW and VALID, with no "
            "shared, engaged or closing time and no close reason."
        ),
        proven_by=(
            "test_an_opportunity_is_born_new_and_valid_with_no_event_time",
            "test_any_other_birth_is_refused",
        ),
    ),
    Delta(
        revision="0006_opportunity_history",
        section="triggers",
        object_name="opportunities.trg_opportunity_birth",
        kind="BEFORE INSERT trigger calling enforce_opportunity_birth()",
        digest_before=None,
        digest_after="02cebe3364c3fd3cc82f2d0cd658e6c3e5fbe5c8d435baeb6c325ac818b8420f",
        reason=(
            "Attaches the birth guard above to opportunities. Declared "
            "separately for the same reason as the history trigger."
        ),
        proven_by=(
            "test_any_other_birth_is_refused",
        ),
    ),
    Delta(
        revision="0007_task_work_and_evidence",
        section="triggers",
        object_name="task_completion_events.prevent_task_completion_event_change",
        kind="BEFORE UPDATE OR DELETE trigger calling the frozen "
             "prevent_immutable_history_change()",
        digest_before=None,
        digest_after="fd7e4d5f148f347d6face087fefd28933cec14b6567c18e3e757dd971e5bc087",
        reason=(
            "A completion event could be updated and deleted, although the "
            "contract says the completion appends it and that its outcome and "
            "evidence must not be discarded (measured, step 0 E1). Slice 6 plan "
            "§5.1 part A (G6-8 (iv) (a)). It reuses the frozen function, so no "
            "function is added for it."
        ),
        proven_by=(
            "test_a_completion_event_cannot_be_updated",
            "test_a_completion_event_cannot_be_deleted",
            "test_a_completion_event_can_still_be_appended",
            "test_part_a_alone_refuses_the_set_null_of_a_deleted_observation",
        ),
    ),
    Delta(
        revision="0007_task_work_and_evidence",
        section="indexes",
        object_name="tasks.ux_one_open_task_per_subject",
        kind="partial unique expression index",
        digest_before=None,
        digest_after="9458c0de1029b93a0b23fc428fb0fe2acb643bfceab92f1c09ad1e022f4c0dfc",
        reason=(
            "Nothing prevented two open tasks for the same work, and under "
            "REPEATABLE READ a lock-then-check does not prevent the duplicate "
            "(measured, step 0 T4-T5). Slice 6 plan §5.1 part C (G6-4 (iii)): "
            "one OPEN or IN_PROGRESS diagnostic task per subject of work."
        ),
        proven_by=(
            "test_the_same_open_work_is_refused",
            "test_each_component_of_the_key_separates_two_subjects",
            "test_tasks_of_the_other_writers_are_outside_the_index",
            "test_two_concurrent_runs_raise_one_task",
        ),
    ),
    Delta(
        revision="0007_task_work_and_evidence",
        section="functions",
        object_name="prevent_cited_observation_change()",
        kind="trigger function",
        digest_before=None,
        digest_after="680baf51be46c3cac5a6412406c21a791ad4ef6facd141fbe79928bb39499bd6",
        reason=(
            "The observation a completion cites could be updated or deleted, the "
            "event's reference then becoming NULL silently (measured, step 0 E1). "
            "Slice 6 plan §5.1 part D (G6-8 (iv) (a)): a cited observation cannot "
            "change. Not sufficient alone (F6-18): the completion command's FOR "
            "SHARE lock completes it (step 2)."
        ),
        proven_by=(
            "test_a_cited_observation_cannot_be_updated",
            "test_a_cited_observation_cannot_be_deleted",
            "test_an_uncited_observation_stays_writable",
            "test_deleting_what_a_cited_observation_references_is_refused",
        ),
    ),
    Delta(
        revision="0007_task_work_and_evidence",
        section="triggers",
        object_name="observations.trg_cited_observation_unchanged",
        kind="BEFORE UPDATE OR DELETE trigger calling prevent_cited_observation_change()",
        digest_before=None,
        digest_after="7a7401aefd2d76d2eaf29a5a9a6424270472a484bff7e65ace63d1d256664de7",
        reason=(
            "Attaches the guard above to observations. Declared separately because "
            "the check compares catalog objects one by one, and a function without "
            "its trigger would guard nothing."
        ),
        proven_by=(
            "test_a_cited_observation_cannot_be_updated",
        ),
    ),
    Delta(
        revision='0008_communication_records',
        section='constraints',
        object_name='communication_threads.ck_whatsapp_thread_ref_scoped',
        kind='CHECK constraint',
        digest_before=None,
        digest_after='a4958970980400de6cdb9a1b63f9e23573b1d771d4cd0b0bb758e2876e16c6a0',
        reason=("Slice 7 plan §5.1 part E (G7-3, review of 4aed49b): a WHATSAPP thread's reference is scoped, <scope>:<id>, so one relay serving several business numbers never gives two of them one reference."),
        proven_by=('test_e_an_unscoped_whatsapp_reference_is_refused',),
    ),
    Delta(
        revision='0008_communication_records',
        section='indexes',
        object_name='communication_threads.ux_whatsapp_thread_ref',
        kind='partial unique index',
        digest_before=None,
        digest_after='657a5e321ee88b4583ccac5f6eb2e2f82f3c72f0c5d417d05d7a2ed859f6de89',
        reason=("Slice 7 plan §5.1 part E (G7-3, review of 4aed49b): nothing made a WHATSAPP thread's reference unique, so an inbound message could resolve to two threads and its party be undetermined. At most one WHATSAPP thread holds a reference."),
        proven_by=('test_e_a_second_whatsapp_thread_with_one_reference_is_refused', 'test_e_two_concurrent_threads_with_one_reference_make_one'),
    ),
    Delta(
        revision='0008_communication_records',
        section='constraints',
        object_name='communication_messages.ck_message_ref_needs_provider',
        kind='CHECK constraint',
        digest_before=None,
        digest_after='81dabdcfe95706b18915e56dfb77c35637feeafaf2435cd2600f100ef994ee41',
        reason=('With provider NULL, one external_message_ref was stored twice, in two threads, because UNIQUE(provider, external_message_ref) treats NULLs as distinct (measured, step 0 M1). Slice 7 plan §5.1 part A (G7-4).'),
        proven_by=('test_a_a_reference_needs_a_provider',),
    ),
    Delta(
        revision='0008_communication_records',
        section='constraints',
        object_name='communication_messages.ck_message_provider_known',
        kind='CHECK constraint',
        digest_before=None,
        digest_after='d636314609926800e9879c3d8c4e7f07192f3bf76659dfe7a34e0690fd725b0a',
        reason=("Slice 7 plan §5.1 part A (G7-4, decided in the review of 4aed49b): a provider is defined by the sources for one channel only, WHATSAPP, so 'whatsapp' is the one provider a message may name."),
        proven_by=('test_a_the_provider_is_whatsapp',),
    ),
    Delta(
        revision='0008_communication_records',
        section='constraints',
        object_name='communication_messages.ck_internal_message_has_no_ref',
        kind='CHECK constraint',
        digest_before=None,
        digest_after='823b181745c2a050faca9be625ed3a6b1f9e02aace096aea2531ffc8e63abd6f',
        reason=('Slice 7 plan §5.1 part A (G7-4): an INTERNAL message is a staff note that no provider carried, so it never holds a provider message reference.'),
        proven_by=('test_a_an_internal_message_has_no_reference',),
    ),
    Delta(
        revision='0008_communication_records',
        section='functions',
        object_name='enforce_message_provider_channel()',
        kind='trigger function',
        digest_before=None,
        digest_after='b6ea3bbf63af8fa67f8c80f31149c0e4fd108be4e3179b76b751ea8af002050b',
        reason=('Slice 7 plan §5.1 part A (G7-4, review of 4aed49b): a message naming a provider belongs to a WHATSAPP thread; the reference is refused in every channel with no defined provider.'),
        proven_by=('test_a_a_provider_needs_a_whatsapp_thread',),
    ),
    Delta(
        revision='0008_communication_records',
        section='triggers',
        object_name='communication_messages.trg_message_provider_channel',
        kind='BEFORE INSERT trigger calling enforce_message_provider_channel()',
        digest_before=None,
        digest_after='f6089bb8d2cc0c50ab5b9677fe2747d63d7159cb14ba5f543b1a91026de98ba1',
        reason=('Attaches the channel rule above to message inserts. Declared separately because the check compares catalog objects one by one, and a function without its trigger guards nothing.'),
        proven_by=('test_a_a_provider_needs_a_whatsapp_thread',),
    ),
    Delta(
        revision='0008_communication_records',
        section='functions',
        object_name='guard_communication_message()',
        kind='trigger function',
        digest_before=None,
        digest_after='bf3708b86c6ece265ddd4e606512307db8564dae9a4ca1464005c7b1d5671b6e',
        reason=('Every UPDATE and DELETE of a message was accepted, its delivery status backwards included (measured, step 0 M3). Slice 7 plan §5.1 part B (G7-5, corrected in revision 4): a message never changes but for its delivery status, by the decided transitions; UNKNOWN never becomes FAILED.'),
        proven_by=('test_b_delivery_status_transitions_are_exactly_the_decided_ones', 'test_b_no_other_column_of_a_message_changes'),
    ),
    Delta(
        revision='0008_communication_records',
        section='triggers',
        object_name='communication_messages.trg_guard_communication_message',
        kind='BEFORE UPDATE OR DELETE trigger calling guard_communication_message()',
        digest_before=None,
        digest_after='dc89ab5e1e6dce6663c4e4294c887c8d2ebb71666f80e0515b09339d5260b551',
        reason=('Attaches the message guard above. Declared separately because the check compares catalog objects one by one, and a function without its trigger guards nothing.'),
        proven_by=('test_b_a_message_cannot_be_deleted',),
    ),
    Delta(
        revision='0008_communication_records',
        section='functions',
        object_name='guard_webhook_event()',
        kind='trigger function',
        digest_before=None,
        digest_after='ef60ec6653fd53b00f464a2813f54afaa1f4471d4dcea7d438604fa64cf51048',
        reason=("A webhook event's payload and status could be rewritten, back to RECEIVED included, and the row deleted (measured, step 0 M3). Slice 7 plan §5.1 part C (G7-2 (v)): an event never changes but for its processing, from RECEIVED or FAILED only."),
        proven_by=('test_c_the_immutable_fields_of_an_event_never_change', 'test_c_processing_moves_only_from_received_or_failed'),
    ),
    Delta(
        revision='0008_communication_records',
        section='triggers',
        object_name='webhook_events.trg_guard_webhook_event',
        kind='BEFORE UPDATE OR DELETE trigger calling guard_webhook_event()',
        digest_before=None,
        digest_after='33774c4a9e86b1d7a15860cc119a2b39d4665af956449db86c3abe1682d0d3fc',
        reason=('Attaches the event guard above. Declared separately because the check compares catalog objects one by one, and a function without its trigger guards nothing.'),
        proven_by=('test_c_an_event_cannot_be_deleted',),
    ),
    Delta(
        revision='0008_communication_records',
        section='functions',
        object_name='guard_communication_thread()',
        kind='trigger function',
        digest_before=None,
        digest_after='f8e4f96fdda2b40cc9a72ef76613051cf84e2e78f1482fdc1c3cef098204b5dd',
        reason=("A thread's links could be re-pointed (measured, step 0 M3). Slice 7 plan §5.1 part D, D2 (review of 4aed49b): a thread never changes after INSERT, at any trigger depth, but for last_message_at moving forward; DELETE is refused."),
        proven_by=('test_d_a_thread_never_changes_after_insert', 'test_d_a_nested_update_is_refused_too'),
    ),
    Delta(
        revision='0008_communication_records',
        section='triggers',
        object_name='communication_threads.trg_guard_communication_thread',
        kind='BEFORE UPDATE OR DELETE trigger calling guard_communication_thread()',
        digest_before=None,
        digest_after='ae92314f62e1082ce3d9a409232dd0e7d4e0204fe21e2defb75069129fff444b',
        reason=('Attaches the thread guard above. Declared separately because the check compares catalog objects one by one, and a function without its trigger guards nothing.'),
        proven_by=('test_d_a_thread_cannot_be_deleted',),
    ),
    Delta(
        revision='0008_communication_records',
        section='constraints',
        object_name='communication_threads.communication_threads_party_id_fkey',
        kind='FOREIGN KEY, ON DELETE SET NULL made ON DELETE RESTRICT',
        digest_before='d4d851c042dc4fb33fc258e2c8c5f36bd84b0aeb545a7eb9f0bf2e6980c8d28c',
        digest_after='b186c8f6a3302fdf8252823810b4ab28ea0d9c3de78ad67db552908731250255',
        reason=("Slice 7 plan §5.1 part D, D2 (decided in the review of 4aed49b): the frozen ON DELETE SET NULL would let a deletion erase a thread's party, and a guard freezing it would refuse that SET NULL (measured, step 0 M8). The key becomes ON DELETE RESTRICT: the named row cannot be deleted while a communication record names it."),
        proven_by=('test_d_a_named_parent_cannot_be_deleted', 'test_d_the_six_keys_are_restrict'),
    ),
    Delta(
        revision='0008_communication_records',
        section='constraints',
        object_name='communication_threads.communication_threads_request_id_fkey',
        kind='FOREIGN KEY, ON DELETE SET NULL made ON DELETE RESTRICT',
        digest_before='f0e9177ef5071b796a7b078f32a242fd68c090ccc96afc9a7a504bceaeda1faf',
        digest_after='a25db5a4953083bca0774e35f0bff5936810240ae89dc4ae1f3ac3623c4a8c46',
        reason=("Slice 7 plan §5.1 part D, D2 (decided in the review of 4aed49b): the frozen ON DELETE SET NULL would let a deletion erase a thread's request, and a guard freezing it would refuse that SET NULL (measured, step 0 M8). The key becomes ON DELETE RESTRICT: the named row cannot be deleted while a communication record names it."),
        proven_by=('test_d_a_named_parent_cannot_be_deleted', 'test_d_the_six_keys_are_restrict'),
    ),
    Delta(
        revision='0008_communication_records',
        section='constraints',
        object_name='communication_threads.communication_threads_property_id_fkey',
        kind='FOREIGN KEY, ON DELETE SET NULL made ON DELETE RESTRICT',
        digest_before='2f7941d1254eec75b887081fb42d9695f7c976e29ecc9d10c734598e23f3b01c',
        digest_after='2dfb56236acc3f057adf2634a05fcc5b177e219fc593e28c9c157f26dbb9f38e',
        reason=("Slice 7 plan §5.1 part D, D2 (decided in the review of 4aed49b): the frozen ON DELETE SET NULL would let a deletion erase a thread's property, and a guard freezing it would refuse that SET NULL (measured, step 0 M8). The key becomes ON DELETE RESTRICT: the named row cannot be deleted while a communication record names it."),
        proven_by=('test_d_a_named_parent_cannot_be_deleted', 'test_d_the_six_keys_are_restrict'),
    ),
    Delta(
        revision='0008_communication_records',
        section='constraints',
        object_name='communication_threads.communication_threads_opportunity_id_fkey',
        kind='FOREIGN KEY, ON DELETE SET NULL made ON DELETE RESTRICT',
        digest_before='6ab508bf86dde7b6d3cbc0bdd05a8e5c8f6152af514aedfe483128d4b5850db7',
        digest_after='f5e93ec5c613f77726a60ec2449c91c7cfba3b4456c1a19309dadc9961faa0dc',
        reason=("Slice 7 plan §5.1 part D, D2 (decided in the review of 4aed49b): the frozen ON DELETE SET NULL would let a deletion erase a thread's opportunity, and a guard freezing it would refuse that SET NULL (measured, step 0 M8). The key becomes ON DELETE RESTRICT: the named row cannot be deleted while a communication record names it."),
        proven_by=('test_d_a_named_parent_cannot_be_deleted', 'test_d_the_six_keys_are_restrict'),
    ),
    Delta(
        revision='0008_communication_records',
        section='constraints',
        object_name='communication_threads.communication_threads_created_by_account_id_fkey',
        kind='FOREIGN KEY, ON DELETE SET NULL made ON DELETE RESTRICT',
        digest_before='a68c541212cd89cfc47852276f5dacf868aca392a6d7d1a4887ba0cedec0c3b6',
        digest_after='0cf0a9af519d76d55f1c8c16ab56d7b33df7b8af69de38c338ead99071033971',
        reason=("Slice 7 plan §5.1 part D, D2 (decided in the review of 4aed49b): the frozen ON DELETE SET NULL would let a deletion erase a thread's creating account, and a guard freezing it would refuse that SET NULL (measured, step 0 M8). The key becomes ON DELETE RESTRICT: the named row cannot be deleted while a communication record names it."),
        proven_by=('test_d_a_named_parent_cannot_be_deleted', 'test_d_the_six_keys_are_restrict'),
    ),
    Delta(
        revision='0008_communication_records',
        section='constraints',
        object_name='communication_messages.communication_messages_sent_by_account_id_fkey',
        kind='FOREIGN KEY, ON DELETE SET NULL made ON DELETE RESTRICT',
        digest_before='8a8371cb45e179e5fa072bc5a992fa6d000c3b7614e885a437494d8d7b842e75',
        digest_after='850b7933552e2a12523d15ee7143eb1730badd68b736daf17da94c33a1a44ad8',
        reason=("Slice 7 plan §5.1 part D, D2 (decided in the review of 4aed49b): the frozen ON DELETE SET NULL would let a deletion erase a thread's sending account (on a message), and a guard freezing it would refuse that SET NULL (measured, step 0 M8). The key becomes ON DELETE RESTRICT: the named row cannot be deleted while a communication record names it."),
        proven_by=('test_d_a_named_parent_cannot_be_deleted', 'test_d_the_six_keys_are_restrict'),
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
