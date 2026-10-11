"""Command-layer audit rows for tables the frozen schema does not audit.

Ref: schema_v0.2.3.sql §13 (`audit_row_change()` and the eight tables it is
attached to); Contract Delta G3-6 §7.

The frozen schema attaches `audit_row_change()` to eight tables. Several that
commands now write — `party_property_relations`, `sources`, `external_leads` —
carry no such trigger. Adding one would be a schema change; writing nothing
would leave those commands unaudited. This writes the row the trigger WOULD
have written: the same columns, with actor and context read from the same
transaction settings (`app.account_id`, `app.audit_context`) that
`audited_transaction` sets for every command.
"""
from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.orm import Session

#: Tables whose rows this helper may audit, with their key column. Closed, so
#: a typo cannot write an audit row about a table that does not exist.
AUDITED_BY_COMMAND = {
    "party_property_relations": "party_property_relation_id",
    "sources": "source_id",
    "external_leads": "external_lead_id",
    # Slice 3 step 5: the truth-layer tables without a trigger. `claims` and
    # `resolved_values` HAVE one (audit_claims, audit_resolved_values).
    "observations": "observation_id",
    "verification_events": "verification_event_id",
    "property_attributes": "property_attribute_id",
    # Slice 3 step 7: Identity Lite, and the review work it raises. None of
    # the three has an audit trigger in the frozen schema.
    "property_identity_candidates": "identity_candidate_id",
    "property_identity_aliases": "alias_property_id",
    "tasks": "task_id",
    # Slice 4 step 7: the matching run (plan §3.6). None of the three match
    # tables has an audit trigger in the frozen schema.
    "match_candidates": "match_id",
    "match_criterion_results": "match_criterion_result_id",
    "match_diagnostic_runs": "diagnostic_run_id",
    # Slice 5 step 5 (G5-8 (i), decided (a) in the review of 6c6e614): the
    # share's interaction. `interactions` has no audit trigger.
    "interactions": "interaction_id",
}

#: Columns a command-layer audit row leaves out. The review of 6c6e614
#: decided that the share's free-text note (`interactions.summary`) is kept
#: in the interaction and is not carried into the audit log: free text can
#: hold contact data (the review of d0e0bc9). The audit row is the row the
#: trigger would have written, less these columns.
WITHHELD: dict[str, tuple[str, ...]] = {
    "interactions": ("summary",),
}


def row_json(session: Session, table: str, entity_id: uuid.UUID) -> str:
    key = AUDITED_BY_COMMAND[table]
    withheld = "".join(f" - '{column}'" for column in WITHHELD.get(table, ()))
    return session.execute(
        text(f"SELECT (to_jsonb(r){withheld})::text FROM turab.{table} r WHERE {key} = :id"),
        {"id": entity_id},
    ).scalar_one()


def write(session: Session, table: str, entity_id: uuid.UUID, action: str,
          old: str | None, new: str | None) -> None:
    if table not in AUDITED_BY_COMMAND:
        raise ValueError(f"{table} is not audited by the command layer")
    session.execute(
        text(
            """INSERT INTO turab.audit_log
                      (entity_table, entity_id, action, old_row, new_row,
                       actor_account_id, context)
               VALUES (:table, :id, :action,
                       CAST(:old AS jsonb), CAST(:new AS jsonb),
                       NULLIF(current_setting('app.account_id', true), '')::uuid,
                       COALESCE(NULLIF(current_setting('app.audit_context', true),
                                       '')::jsonb, '{}'::jsonb))"""
        ),
        {"table": table, "id": entity_id, "action": action, "old": old, "new": new},
    )
