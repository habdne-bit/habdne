"""Operational tasks: the list and the completion (Slice 6, step 2).

Ref: the contract's `getTasks` and `postTasksTaskIdComplete` (ADMIN,
OPERATOR, REVIEWER; Idempotency-Key on the completion), the latter narrowed
by CORRECTION-005; `docs/gate/SLICE_6_PLAN.md`: §3.6, §3.7, G6-8, G6-9;
`API_CONTRACTS_v0.2.md` §4.10.

**The completion, in G6-8 (iv)'s order, under READ COMMITTED.** Every
refusal comes before any write. `prepare` runs before the idempotency
claim (G4-15 D6), so a refused completion writes no event, no task change,
no audit row, and consumes no key:
1. the task row, locked `FOR UPDATE` as the first statement on it. A second,
   concurrent completion waits here, then reads DONE and is refused 409
   `TASK_NOT_OPEN` (F6-17, E4). Only OPEN and IN_PROGRESS are completed;
2. if `evidence_observation_id` is given, that observation, locked `FOR
   SHARE`. No row, including one deleted while the completion waited for it,
   is 422 `EVIDENCE_OBSERVATION_NOT_FOUND` (R2d).

Then `record` writes:
3. the event: `outcome_code`, `note`, `evidence_observation_id`, exactly as
   received (§3.6);
4. the task: DONE, with the event's `completed_at`.

**Why FOR SHARE, and why this order (F6-18).** Migration `0007` part D
refuses a change to an observation an event cites, but it cannot see an
event not yet committed, and the foreign key's FOR KEY SHARE does not
conflict with a body UPDATE (R1a, R1b). FOR SHARE conflicts with the FOR NO
KEY UPDATE of a body UPDATE and with the FOR UPDATE of a DELETE (PostgreSQL
16, §13.3.2, Table 13.3). So once the lock is granted, the body cited is the
committed one, and after the commit part D refuses any change (R2a, R2c). The
task is locked before the observation. No path locks an observation and then
a task: no application path writes observations. So the order cannot
invert.

**What a completion does not do (G6-8 (v), (vii)).** It changes no
property, offer, request, claim, verification level or consent, runs no
matching and closes no opportunity. `TASK_INFORMATION_OBTAINED` says that
the work was done; it proves nothing about the information. No path here
reopens a DONE task.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Mapping

from sqlalchemy import text
from sqlalchemy.orm import Session

from . import audit_rows
from .match_review import task_view

#: G6-8 (i): the statuses a completion accepts.
COMPLETABLE = ("OPEN", "IN_PROGRESS")
#: G6-9: the list's order, URGENT first.
PRIORITY_ORDER = ("URGENT", "HIGH", "NORMAL", "LOW")

_COLUMNS = """task_id, task_type::text AS task_type, priority::text AS priority,
              status::text AS status, title, reason_code, party_id, request_id,
              property_id, match_id, due_at, payload::text AS payload"""


class TaskRefused(Exception):
    """A typed refusal. `code` is a `ProblemCode` name; the route maps it.
    The detail names no id."""

    def __init__(self, code: str, detail: str) -> None:
        super().__init__(detail)
        self.code = code


# --- getTasks (G6-9) -------------------------------------------------------------

def list_tasks(session: Session, *, status: str | None, priority: str | None,
               assigned_to: uuid.UUID | None, page: int,
               page_size: int) -> tuple[list[Mapping[str, Any]], int]:
    """Every task, whichever writer raised it.
    - `status` and `priority` are compared as TEXT: the contract types them as
      plain strings with no enum, so a value naming none returns nothing;
    - `assigned_to`: the caller's account when `assigned_to_me` is true. No
      contract command assigns a task (F6-7), so this is empty today;
    - order: priority (URGENT, HIGH, NORMAL, LOW), then `created_at`, then
      `task_id`."""
    where = """(CAST(:s AS text) IS NULL OR status::text = CAST(:s AS text))
           AND (CAST(:p AS text) IS NULL OR priority::text = CAST(:p AS text))
           AND (CAST(:a AS uuid) IS NULL OR assigned_account_id = CAST(:a AS uuid))"""
    params = {"s": status, "p": priority, "a": assigned_to}
    total = session.execute(text(f"SELECT count(*) FROM turab.tasks WHERE {where}"),
                            params).scalar_one()
    rows = session.execute(text(f"""
        SELECT {_COLUMNS} FROM turab.tasks WHERE {where}
         ORDER BY array_position(CAST(:order AS text[]), priority::text), created_at, task_id
         LIMIT :limit OFFSET :offset"""),
        {**params, "order": list(PRIORITY_ORDER), "limit": page_size,
         "offset": (page - 1) * page_size}).mappings().all()
    return [task_view(r) for r in rows], total


# --- postTasksTaskIdComplete (G6-8) ---------------------------------------------------

@dataclass(frozen=True, slots=True)
class Prepared:
    """What `prepare` decided, under its locks, for `record` to write."""

    task_id: uuid.UUID
    evidence_observation_id: uuid.UUID | None


def _lock_task(session: Session, task_id: uuid.UUID) -> Mapping[str, Any] | None:
    """Step 1, the FIRST statement on the task."""
    return session.execute(text(
        "SELECT task_id, status::text AS status FROM turab.tasks "
        "WHERE task_id = :t FOR UPDATE"), {"t": task_id}).mappings().first()


def _lock_observation(session: Session, observation_id: uuid.UUID) -> bool:
    """Step 2. After a wait on a writer of the row, READ COMMITTED reads the
    committed version: the changed body (R2b), or no row if it was deleted
    (R2d)."""
    return session.execute(text(
        "SELECT 1 FROM turab.observations WHERE observation_id = :o FOR SHARE"),
        {"o": observation_id}).scalar_one_or_none() is not None


def prepare(session: Session, *, task_id: uuid.UUID,
            evidence_observation_id: uuid.UUID | None) -> Prepared:
    """Steps 1 and 2, read-only, before the idempotency claim."""
    task = _lock_task(session, task_id)
    if task is None:
        # The route checked existence first, and no path deletes a task;
        # the same answer, kept in case it is reached.
        raise TaskRefused("OBJECT_NOT_AUTHORIZED", "not an available task")
    if task["status"] not in COMPLETABLE:
        raise TaskRefused("TASK_NOT_OPEN",
                          f"the task is {task['status']}; only an OPEN or IN_PROGRESS "
                          "task is completed")
    if evidence_observation_id is not None and not _lock_observation(
            session, evidence_observation_id):
        raise TaskRefused("EVIDENCE_OBSERVATION_NOT_FOUND",
                          "the evidence observation does not exist")
    return Prepared(task_id=task_id, evidence_observation_id=evidence_observation_id)


def record(session: Session, prepared: Prepared, *, outcome_code: str, note: str | None,
           completed_by_account_id: uuid.UUID) -> dict[str, Any]:
    """Steps 3 and 4, after the claim, in the command's one transaction: the
    event and the DONE task land together or not at all (§3.6, I02). Both
    rows are audited; the note is withheld from the audit row (§3.7)."""
    event = session.execute(text("""
        INSERT INTO turab.task_completion_events
               (task_id, outcome_code, note, evidence_observation_id, completed_by_account_id)
        VALUES (:t, :code, :note, :obs, :acct)
        RETURNING task_completion_event_id, completed_at"""),
        {"t": prepared.task_id, "code": outcome_code, "note": note,
         "obs": prepared.evidence_observation_id,
         "acct": completed_by_account_id}).mappings().one()
    audit_rows.write(session, "task_completion_events", event["task_completion_event_id"],
                     "INSERT", None, audit_rows.row_json(
                         session, "task_completion_events",
                         event["task_completion_event_id"]))
    before = audit_rows.row_json(session, "tasks", prepared.task_id)
    row = session.execute(text(f"""
        UPDATE turab.tasks SET status = 'DONE', completed_at = :at
         WHERE task_id = :t
        RETURNING {_COLUMNS}"""),
        {"t": prepared.task_id, "at": event["completed_at"]}).mappings().one()
    audit_rows.write(session, "tasks", prepared.task_id, "UPDATE", before,
                     audit_rows.row_json(session, "tasks", prepared.task_id))
    return task_view(row)
