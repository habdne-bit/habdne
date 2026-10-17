"""Task work and its evidence.

Revision ID: 0007_task_work_and_evidence
Revises: 0006_opportunity_history

Slice 6 plan revision 4 (`docs/gate/SLICE_6_PLAN.md`), §5.1, parts A-D,
approved in the review of bd54216 with the decisions they rest on: G6-8 (iv)
(a) for parts A and D, G6-8 (ii) (a) for part B, G6-4 (iii) for part C. This
revision implements that text exactly.

## What the frozen schema left open

Measured before this revision (`docs/gate/evidence/SLICE6-PLAN-MEASUREMENTS.txt`
§T4, §E; `SLICE6-PLAN-MEASUREMENTS-R3.txt`; again by the shipped tests,
`SLICE6-STEP1-0007-BEFORE-FIX.txt`):
- a completion event could be updated and deleted, although the contract says
  a completion "Appends" its event and that its outcome and evidence "must not
  be discarded" (`API_CONTRACTS_v0.2.md` §4.10);
- the observation an event cites could be updated, or deleted, and the event's
  `evidence_observation_id` then silently became NULL (ON DELETE SET NULL);
- no seeded reason code describes the outcome of a task, while the outcome FK
  accepts any code of any category, active or not;
- nothing prevented two OPEN tasks for the same work, and under REPEATABLE
  READ only a unique index prevents the duplicate: a lock-then-check does not.

## What this revision adds

**A.** `prevent_task_completion_event_change`, BEFORE UPDATE OR DELETE on
`task_completion_events`, calling the FROZEN `prevent_immutable_history_change()`
as `0005`'s triggers do. Measured consequence (F6-16): deleting an observation
an event cites is refused, because the FK's SET NULL is an UPDATE of the event.

**B.** Four reason codes, category `TASK_OUTCOME`, inserted as `0002` inserts
its codes (`WHERE NOT EXISTS`). Their meanings are fixed by G6-8 (ii) (a):
`TASK_INFORMATION_OBTAINED` says that the work was done. It raises no
verification level and proves nothing about whether the information is true
(review of 1fd7bdf). The codes change no fact.

**C.** `ux_one_open_task_per_subject`: one OPEN or IN_PROGRESS task per subject
of work, for the run's tasks only (`payload ->> 'source' = 'DIAGNOSTIC'`).
Slice 3's and Slice 5's tasks carry no `source` key and are outside it. Two
NULL `request_id`s never conflict (PostgreSQL 16 documentation, §11.6); the
run always sets its request.

**D.** `prevent_cited_observation_change()` and `trg_cited_observation_unchanged`,
BEFORE UPDATE OR DELETE on `observations`: an observation a completion event
cites cannot change. **Not sufficient alone** (F6-18, R1a-R1b): a concurrent
completion's event, still uncommitted, is invisible to the guard, and the FK's
FOR KEY SHARE does not conflict with a non-key UPDATE. The completion command
therefore locks the observation FOR SHARE before inserting its event (G6-8
(iv), step 2). Consequence, stated in the plan and measured by the tests:
deleting a source, party or account that a cited observation references is
refused, because the SET NULL it causes is an UPDATE of that observation.

No table, no column. Proven at trigger level only, under the superuser role
(EN-02): K06 stays UNPROVEN.

## Downgrade

Refused. Reverting it lets a completion's evidence be rewritten (G6-8 (iv)),
and removing part B's codes would break, or strip, the outcome of every event
that names one, as `0002`'s downgrade explains for its codes.
"""
from __future__ import annotations

from alembic import op

revision = "0007_task_work_and_evidence"
down_revision = "0006_opportunity_history"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("SET LOCAL search_path TO turab, public")
    # --- A. The events are append-only ---------------------------------------------
    op.execute(
        """CREATE TRIGGER prevent_task_completion_event_change
             BEFORE UPDATE OR DELETE ON turab.task_completion_events
             FOR EACH ROW EXECUTE FUNCTION turab.prevent_immutable_history_change()"""
    )
    # --- B. The task outcome codes ------------------------------------------------
    op.execute(
        """INSERT INTO turab.reason_codes (code, category, label_ar, label_en, active)
           SELECT v.code, 'TASK_OUTCOME', v.label_ar, v.label_en, true
             FROM (VALUES
               ('TASK_INFORMATION_OBTAINED',    'تم الحصول على المعلومة المطلوبة', 'The information asked for was obtained'),
               ('TASK_INFORMATION_UNAVAILABLE', 'تعذر الحصول على المعلومة المطلوبة', 'The information asked for could not be obtained'),
               ('TASK_PARTY_UNREACHABLE',       'تعذر الوصول إلى الطرف', 'The party could not be reached'),
               ('TASK_NO_LONGER_NEEDED',        'لم تعد المهمة لازمة', 'The task is no longer needed')
             ) AS v(code, label_ar, label_en)
            WHERE NOT EXISTS (SELECT 1 FROM turab.reason_codes r WHERE r.code = v.code)"""
    )
    # --- C. One open task per subject of work -----------------------------------------
    op.execute(
        """CREATE UNIQUE INDEX ux_one_open_task_per_subject ON turab.tasks (
               request_id,
               (payload -> 'subject' ->> 'entity'),
               (payload -> 'subject' ->> 'id'),
               (payload -> 'subject' ->> 'gate'),
               (coalesce(payload -> 'subject' ->> 'criterion', '')),
               (coalesce(payload -> 'subject' ->> 'ordinal', '')),
               (payload -> 'subject' ->> 'basis'))
             WHERE status IN ('OPEN', 'IN_PROGRESS')
               AND payload ->> 'source' = 'DIAGNOSTIC'"""
    )
    # --- D. A cited observation is kept as cited ------------------------------------
    op.execute(
        """CREATE FUNCTION turab.prevent_cited_observation_change()
           RETURNS trigger LANGUAGE plpgsql AS $$
           BEGIN
             IF EXISTS (SELECT 1 FROM turab.task_completion_events
                         WHERE evidence_observation_id = OLD.observation_id) THEN
               RAISE EXCEPTION 'Observation % is the evidence of a task completion and cannot change',
                 OLD.observation_id;
             END IF;
             RETURN CASE TG_OP WHEN 'DELETE' THEN OLD ELSE NEW END;
           END $$"""
    )
    op.execute(
        """CREATE TRIGGER trg_cited_observation_unchanged
             BEFORE UPDATE OR DELETE ON turab.observations
             FOR EACH ROW EXECUTE FUNCTION turab.prevent_cited_observation_change()"""
    )


def downgrade() -> None:
    """Refused. See the module docstring."""
    raise RuntimeError(
        "0007 has no downgrade: reverting it lets a task completion's evidence be "
        "rewritten (G6-8 (iv)) and strips the outcome codes events may name. If that "
        "is genuinely wanted, write a forward migration that says why."
    )
