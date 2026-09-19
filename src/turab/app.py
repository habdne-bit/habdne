"""FastAPI application assembly.

Ref: RFC-001 R10.2 (startup cross-check), §14.
"""
from __future__ import annotations

import logging
import uuid

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text as sa_text

from .api import handlers
from .api.routes import (
    auth, consents, internal, me, parties, records, requests as request_routes,
)
from .auth.audit import AccessAuditor
from .auth.contract import build_policy_table, verify_policy_matches_contract
from .auth.roles import verify_separation_sensitive_operations
from .db.session import create_app_engine, session_factory
from .observability import configure_logging
from .services.otp import FakeVerificationProvider

logger = logging.getLogger("turab")


def create_app(
    engine=None,
    auditor: AccessAuditor | None = None,
    configure_logs: bool = False,
    provider=None,
) -> FastAPI:
    if configure_logs:
        configure_logging()
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
    # The verification provider is an integration boundary. A real deployment
    # injects the SMS/WhatsApp client here; this stand-in keeps the default
    # runnable without one. TURAB stores no challenge state either way.
    app.state.verification_provider = provider or FakeVerificationProvider()

    @app.middleware("http")
    async def attach_trace_id(request: Request, call_next):
        request.state.trace_id = request.headers.get("x-trace-id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["x-trace-id"] = request.state.trace_id
        return response

    @app.get("/health", operation_id="getHealth", include_in_schema=False)
    def health():
        """Liveness: the process is up. No dependencies are touched."""
        return {"status": "ok"}

    @app.get("/ready", operation_id="getReady", include_in_schema=False)
    def ready():
        """Readiness: the database answers and the policy table is loaded.

        A readiness probe that only reports the process is alive will keep a
        broken instance in the load balancer, so this checks the one dependency
        every request needs.
        """
        checks = {"policy_operations": len(app.state.policies)}
        try:
            with app.state.session_factory() as session:
                session.execute(sa_text("SELECT 1"))
            checks["database"] = "ok"
        except Exception:
            logger.exception("readiness check failed")
            checks["database"] = "unavailable"
            return JSONResponse(
                status_code=503, content={"status": "not_ready", **checks}
            )
        return {"status": "ready", **checks}

    handlers.install(app)
    app.include_router(me.router)
    app.include_router(internal.router)
    app.include_router(parties.router)
    app.include_router(consents.router)
    app.include_router(auth.router)
    app.include_router(records.router)
    app.include_router(request_routes.router)
    return app
