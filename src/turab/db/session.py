"""Engine, session factory and the audited transaction wrapper.

Ref: RFC-001 R6.2 (audit context per transaction), Slice 0 deliverable
"database transaction wrapper setting app.account_id and audit context".

`audit_row_change()` in the frozen schema reads `app.account_id` and
`app.audit_context` via current_setting(), so a write outside this wrapper is
recorded with a NULL actor. The wrapper is therefore the only supported way to
open a writing transaction.
"""
from __future__ import annotations

import json
import os
import uuid
from contextlib import contextmanager
from typing import Any, Iterator

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.orm import Session, sessionmaker

DEFAULT_DSN = "postgresql+psycopg:///turab_dev"


def database_url() -> str:
    return os.environ.get("TURAB_DATABASE_URL", DEFAULT_DSN)


def create_app_engine(url: str | None = None, **kwargs: Any) -> Engine:
    return create_engine(url or database_url(), future=True, **kwargs)


def session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)


class MissingAuditActor(RuntimeError):
    """A writing transaction was opened with no actor. Refused."""


@contextmanager
def audited_transaction(
    session: Session,
    account_id: uuid.UUID | None,
    context: dict[str, Any] | None = None,
    *,
    require_actor: bool = True,
) -> Iterator[Session]:
    """Run inside a transaction that carries the audit actor.

    S23: a write with `app.account_id` unset is refused rather than recorded
    anonymously. `require_actor=False` is for genuinely actor-less system work
    and is not reachable from a request path.
    """
    if require_actor and account_id is None:
        raise MissingAuditActor(
            "a writing transaction needs an actor; audit_row_change() would "
            "otherwise attribute the change to nobody"
        )

    with session.begin():
        session.execute(
            text("SELECT set_config('app.account_id', :v, true)"),
            {"v": str(account_id) if account_id else ""},
        )
        session.execute(
            text("SELECT set_config('app.audit_context', :v, true)"),
            {"v": json.dumps(context or {}, ensure_ascii=False)},
        )
        session.execute(text("SET LOCAL search_path = turab, public"))
        yield session


@contextmanager
def read_session(session: Session) -> Iterator[Session]:
    """A read-only unit of work. No actor is set: nothing is written."""
    session.execute(text("SET LOCAL search_path = turab, public"))
    try:
        yield session
    finally:
        session.rollback()
