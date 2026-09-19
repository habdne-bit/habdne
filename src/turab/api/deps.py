"""Composition root for request handling.

This module owns the session and the authentication boundary. It is deliberately
NOT part of the routes package: routes receive an AccessService and never see a
session, which is the structural guarantee of RFC-001 R10.3 / Q6.
"""
from __future__ import annotations

import uuid
from typing import Annotated, Iterator

from fastapi import Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session

from ..auth.audit import AccessAuditor
from ..auth.contract import build_policy_table
from ..auth.policy import PolicyTable
from ..auth.subject import AccountNotResolvable, Subject, resolve_subject
from ..db.session import read_session
from ..services.access import AccessService


def get_policies(request: Request) -> PolicyTable:
    return request.app.state.policies


def get_auditor(request: Request) -> AccessAuditor:
    return request.app.state.auditor


def get_session(request: Request) -> Iterator[Session]:
    factory = request.app.state.session_factory
    session = factory()
    try:
        with read_session(session):
            yield session
    finally:
        session.close()


def get_subject(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> Subject:
    """Resolve the actor.

    The bearer is treated as an opaque account reference for Slice 0; token
    issuance and signature verification belong to the authentication work and do
    not change anything below. What matters here, and is already final, is that
    party, roles and status are read from the database per request (R3.2) rather
    than trusted from the token.
    """
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED")
    raw = authorization.split(" ", 1)[1].strip()
    try:
        account_id = uuid.UUID(raw)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED") from exc
    try:
        return resolve_subject(session, account_id)
    except AccountNotResolvable as exc:
        # R4.11a: a disabled or suspended account is not merely role-less.
        raise HTTPException(status_code=401, detail="UNAUTHENTICATED") from exc


def get_access(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    subject: Annotated[Subject, Depends(get_subject)],
    policies: Annotated[PolicyTable, Depends(get_policies)],
    auditor: Annotated[AccessAuditor, Depends(get_auditor)],
) -> AccessService:
    return AccessService(
        session=session,
        subject=subject,
        policies=policies,
        auditor=auditor,
        trace_id=getattr(request.state, "trace_id", "-"),
    )


Access = Annotated[AccessService, Depends(get_access)]

__all__ = ["Access", "get_access", "get_policies", "get_auditor", "build_policy_table"]
