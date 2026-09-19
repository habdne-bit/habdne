"""FastAPI application assembly.

Ref: RFC-001 R10.2 (startup cross-check), §14.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request

from .api.routes import internal, me
from .auth.audit import AccessAuditor
from .auth.contract import build_policy_table, verify_policy_matches_contract
from .auth.roles import verify_separation_sensitive_operations
from .db.session import create_app_engine, session_factory

logger = logging.getLogger("turab")


def create_app(engine=None, auditor: AccessAuditor | None = None) -> FastAPI:
    app = FastAPI(title="TURAB", version="0.1.0")

    # R10.2. The cross-check runs at startup, not only in CI: a policy table
    # that disagrees with the frozen contract must not serve a single request.
    policies = build_policy_table()
    verify_policy_matches_contract(policies)
    # INV-2 can only fail closed for operations it can name.
    verify_separation_sensitive_operations(policies.operations())

    app.state.policies = policies
    app.state.auditor = auditor or AccessAuditor()
    app.state.engine = engine or create_app_engine()
    app.state.session_factory = session_factory(app.state.engine)

    @app.middleware("http")
    async def attach_trace_id(request: Request, call_next):
        request.state.trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["x-trace-id"] = request.state.trace_id
        return response

    @app.get("/health", operation_id="getHealth", include_in_schema=False)
    def health():
        return {"status": "ok"}

    @app.get("/ready", operation_id="getReady", include_in_schema=False)
    def ready():
        return {"status": "ready", "policy_operations": len(app.state.policies)}

    app.include_router(me.router)
    app.include_router(internal.router)
    return app
