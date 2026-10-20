"""Operational tasks: the list and the completion (Slice 6, step 2).

Ref: the contract's `getTasks` and `postTasksTaskIdComplete` (ADMIN,
OPERATOR, REVIEWER; the completion takes an Idempotency-Key), the latter
narrowed by CORRECTION-005; `docs/gate/SLICE_6_PLAN.md` G6-8, G6-9;
`services/tasks.py`.

Like every route module: no session, no repository, no SQLAlchemy. The
completion calls `command.authorize` and `command.authorize_staff_only`
itself, where the architecture guard can see it.
"""
from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, field_validator

from ...auth.contract import effective_request_body
from ...services import tasks as task_service
from ...services import timeline as timeline_service
from ..deps import Access, Command
from ..problems import ProblemCode, coded, for_denial, trace_id_of
from ..responses import ExactJSONResponse
from .parties import _run

router = APIRouter(tags=["Tasks"])

LIST = "getTasks"
COMPLETE = "postTasksTaskIdComplete"

#: CORRECTION-005: the values the effective contract admits, read from the
#: one loader the generator uses, never a second list.
OUTCOME_CODES: tuple[str, ...] = tuple(
    effective_request_body(COMPLETE)["properties"]["outcome_code"]["enum"])


@router.get("/tasks", operation_id=LIST)
def list_tasks(
    request: Request,
    access: Access,
    status: Annotated[str | None, Query()] = None,
    priority: Annotated[str | None, Query()] = None,
    assigned_to_me: Annotated[bool, Query()] = False,
    page: Annotated[int, Query()] = 1,
    page_size: Annotated[int, Query()] = timeline_service.DEFAULT_PAGE_SIZE,
):
    """G6-9: every task, staff only, audited once for the page (R6.3c).
    `status` and `priority` are compared as text: a value naming none
    returns nothing, not a 422. `assigned_to_me=true` keeps the caller's
    tasks; no contract command assigns a task yet (F6-7), so it is empty
    today."""
    decision = access.authorize_operation(LIST)
    if not decision.allowed:
        return for_denial(decision.reason, trace_id_of(request),
                          customer_scoped=False, detail=decision.detail)
    try:
        page, page_size = timeline_service.validate_pagination(page, page_size)
    except timeline_service.InvalidPagination as exc:
        return coded(ProblemCode.VALIDATION_FAILED, trace_id_of(request), str(exc))
    items, total = access.list_tasks(
        status=status, priority=priority, assigned_to_me=assigned_to_me, page=page,
        page_size=page_size, operation_id=LIST)
    page_view = timeline_service.Page(items=tuple(items), page=page,
                                      page_size=page_size, total=total)
    return ExactJSONResponse(content={"items": items, "meta": page_view.meta()})


class TaskCompletionInput(BaseModel):
    """The effective `TaskCompletionInput` (CORRECTION-005), field for field,
    closed as the frozen component is (`additionalProperties: false`).
    - `outcome_code`: required, not null, one of `OUTCOME_CODES`. Typed `Any`
      so that every wrong value reaches the one message below, which never
      echoes the value;
    - `note` and `evidence_observation_id`: a string or null, as frozen."""

    model_config = ConfigDict(extra="forbid")

    outcome_code: Any
    note: str | None = None
    evidence_observation_id: uuid.UUID | None = None

    @field_validator("outcome_code", mode="before")
    @classmethod
    def _a_task_outcome_code(cls, value: Any) -> Any:
        if not isinstance(value, str) or value not in OUTCOME_CODES:
            raise ValueError("outcome_code must be one of the task outcome codes")
        return value


@router.post("/tasks/{task_id}/complete", operation_id=COMPLETE)
def complete_task(request: Request, task_id: uuid.UUID, body: TaskCompletionInput,
                  command: Command):
    """G6-8: append the completion event and mark the task DONE, in one
    transaction. A DONE or CANCELLED task is 409; an evidence observation
    that does not exist is 422. A refusal writes nothing."""
    for decision in (command.authorize(COMPLETE),
                     command.authorize_staff_only(COMPLETE,
                                                  "completing a task is a staff action"),
                     command.authorize_task_exists(task_id, COMPLETE)):
        if not decision.allowed:
            return for_denial(decision.reason, trace_id_of(request),
                              customer_scoped=False, detail=decision.detail)

    def prepare(session):
        return task_service.prepare(session, task_id=task_id,
                                    evidence_observation_id=body.evidence_observation_id)

    def handler(session, prepared):
        return 200, task_service.record(
            session, prepared, outcome_code=body.outcome_code, note=body.note,
            completed_by_account_id=command.subject.account_id)

    return _run(request, command, COMPLETE, f"POST /tasks/{task_id}/complete",
                body.model_dump(mode="json", exclude_unset=True), handler, 200,
                extra_errors=task_service.TaskRefused, prepare=prepare)
