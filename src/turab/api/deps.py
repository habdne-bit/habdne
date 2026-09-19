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
from ..services.command import CommandService
from ..services.otp import OtpService, VerificationProvider


def get_policies(request: Request) -> PolicyTable:
    return request.app.state.policies


def get_auditor(request: Request) -> AccessAuditor:
    return request.app.state.auditor


def get_session(request: Request) -> Iterator[Session]:
    """A read-only unit of work for query paths."""
    factory = request.app.state.session_factory
    session = factory()
    try:
        with read_session(session):
            yield session
    finally:
        session.close()


def get_write_session(request: Request) -> Iterator[Session]:
    """A session for command paths.

    The transaction is opened by CommandService inside `audited_transaction`,
    so the actor reaches `audit_row_change()`. Anything left uncommitted when
    the request ends is rolled back.
    """
    factory = request.app.state.session_factory
    session = factory()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def get_verification_provider(request: Request) -> VerificationProvider:
    """The SMS/WhatsApp verification boundary.

    An integration, not a TURAB table: the provider owns the challenge, the
    code, the attempt count and the expiry.
    """
    return request.app.state.verification_provider


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
    return _resolve_from_header(session, authorization)


def _resolve_from_header(session: Session, authorization: str | None) -> Subject:
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


def get_command(
    request: Request,
    session: Annotated[Session, Depends(get_write_session)],
    read: Annotated[Session, Depends(get_session)],
    subject: Annotated[Subject, Depends(get_subject_for_write)],
    policies: Annotated[PolicyTable, Depends(get_policies)],
    auditor: Annotated[AccessAuditor, Depends(get_auditor)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> CommandService:
    return CommandService(
        session=session,
        subject=subject,
        policies=policies,
        auditor=auditor,
        trace_id=getattr(request.state, "trace_id", "-"),
        idempotency_key=idempotency_key,
        read_session=read,
    )


def get_subject_for_write(
    session: Annotated[Session, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> Subject:
    """Resolve the actor on the READ session.

    Deliberately not the write session: resolving there would open a
    transaction on it, and the command must own its transaction outright so
    that the idempotency claim, the work and the stored result commit or roll
    back as one. The subject is committed data either way, so reading it on a
    separate session loses nothing.
    """
    return _resolve_from_header(session, authorization)


def get_otp(
    request: Request,
    session: Annotated[Session, Depends(get_write_session)],
    provider: Annotated[VerificationProvider, Depends(get_verification_provider)],
) -> OtpService:
    return OtpService(session, provider, getattr(request.state, "trace_id", "-"))


Access = Annotated[AccessService, Depends(get_access)]
Command = Annotated[CommandService, Depends(get_command)]
Otp = Annotated[OtpService, Depends(get_otp)]

__all__ = [
    "Access", "Command", "Otp", "get_access", "get_command", "get_otp",
    "get_policies", "get_auditor", "build_policy_table",
]
