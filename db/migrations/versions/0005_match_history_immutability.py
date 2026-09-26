"""Match history and immutable policies cannot be rewritten.

Revision ID: 0005_match_history_immutability
Revises: 0004_relation_overlap_guard

Decision G4-14 (Slice 4 plan revision 2, `docs/gate/SLICE_4_PLAN.md`),
approved for step 1. Structural only: no table, no column, no reason code,
no data.

## What the frozen schema left open

Measured before this revision (`docs/gate/evidence/SLICE4-PLAN-MEASUREMENTS.txt`,
§B and §C):

- `match_candidates` and `match_reviews` refuse UPDATE and DELETE
  (`prevent_immutable_history_change`). **`match_criterion_results` and
  `match_diagnostic_runs` do not.** A criterion result was turned from FAIL
  to PASS, then deleted, under a match row that itself refused every change.
  That would defeat mandatory test 8 ("match rows are immutable") and G04
  (immutable replay), because a match IS its criterion results.
- `matching_policies.immutable` is read by nothing. A policy marked immutable
  accepted a change to its `rules` AND to its `version`. Renaming the version
  would silently break, for every stored match, the pairing that
  `trg_match_commercial_context` checked when it was inserted.

## What this revision adds

1. `prevent_match_criterion_result_update`: BEFORE UPDATE OR DELETE on
   `match_criterion_results`. It reuses the frozen
   `prevent_immutable_history_change()`, so the message and behaviour are the
   ones the frozen schema already gives a match row.
2. `prevent_match_diagnostic_run_update`: the same, on `match_diagnostic_runs`.
3. `enforce_matching_policy_immutability()` and its trigger
   `trg_matching_policy_immutable`, BEFORE UPDATE on `matching_policies`. When
   the OLD row is immutable, `version`, `name`, `rules` and `immutable` may not
   change. `active` and `activated_at` stay writable, because activating and
   deactivating policies is how a policy is chosen
   (`ux_matching_policy_one_active`).

**Not covered, because the approval does not name them:**
- DELETE of a policy. `match_candidates.matching_policy_id` is
  `ON DELETE RESTRICT`, so a policy any match cites cannot be deleted.
- `created_at` and `matching_policy_id`. A cited policy's id is held by the
  same foreign key.

A mutable policy (`immutable = false`) stays editable, and may be made
immutable. The reverse is refused.

## A known interaction, stated before approval (plan G4-14)

`match_criterion_results.request_criterion_id` and `.evidence_claim_id` are
`ON DELETE SET NULL`. With this guard, deleting a referenced request criterion
or claim would fail, because the SET NULL is an UPDATE of a guarded row.
Neither deletion exists:
- no code path deletes a request criterion;
- claims refuse DELETE (`prevent_delete_claims`).

If a deletion path is ever added, it must supersede instead.

## Downgrade

Refused, like 0003's. Reverting it would re-open match history to silent
rewriting. That is an integrity regression, and a silent `alembic downgrade`
must not be able to perform it.
"""
from __future__ import annotations

from alembic import op

revision = "0005_match_history_immutability"
down_revision = "0004_relation_overlap_guard"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path TO turab, public")
    op.execute(
        """CREATE TRIGGER prevent_match_criterion_result_update
             BEFORE UPDATE OR DELETE ON turab.match_criterion_results
             FOR EACH ROW EXECUTE FUNCTION turab.prevent_immutable_history_change()"""
    )
    op.execute(
        """CREATE TRIGGER prevent_match_diagnostic_run_update
             BEFORE UPDATE OR DELETE ON turab.match_diagnostic_runs
             FOR EACH ROW EXECUTE FUNCTION turab.prevent_immutable_history_change()"""
    )
    op.execute(
        """CREATE FUNCTION turab.enforce_matching_policy_immutability()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
             IF OLD.immutable AND (
                  NEW.version   IS DISTINCT FROM OLD.version
               OR NEW.name      IS DISTINCT FROM OLD.name
               OR NEW.rules     IS DISTINCT FROM OLD.rules
               OR NEW.immutable IS DISTINCT FROM OLD.immutable) THEN
               RAISE EXCEPTION 'Matching policy % is immutable: its version, name, rules and immutability cannot change; create a new policy version',
                 OLD.version;
             END IF;
             RETURN NEW;
           END $$"""
    )
    op.execute(
        """CREATE TRIGGER trg_matching_policy_immutable
             BEFORE UPDATE ON turab.matching_policies
             FOR EACH ROW EXECUTE FUNCTION turab.enforce_matching_policy_immutability()"""
    )


def downgrade() -> None:
    """Refused. See the module docstring."""
    raise RuntimeError(
        "0005 has no downgrade: reverting it lets match criterion results, "
        "diagnostic runs and immutable matching policies be rewritten (G4-14). "
        "If that is genuinely wanted, write a forward migration that says why."
    )
