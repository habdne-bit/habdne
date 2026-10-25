"""The WhatsApp webhook (Slice 7, step 3).

Ref: the contract's `postWebhooksWhatsapp`, unauthenticated (RFC-001 R10.4)
and verified (R10.5), with CORRECTION-007 (500) and CORRECTION-008 (503);
`docs/gate/SLICE_7_PLAN.md` G7-2, G7-15, G7-17; `services/webhooks.py`.

Like every route module: no session, no repository, no SQLAlchemy. The
checks run in G7-17 (iii)'s order, each writing nothing:
1. the body's size, on `Content-Length` and while reading (400, G7-15);
2. the secret (503 `WEBHOOK_NOT_READY`, CORRECTION-008);
3. the relay's signature over the raw bytes (401);
4. the envelope, and the keys of a known type (400).
Then T1 stores the event, and T2 processes it. Every 200 has an empty body
(G7-17 (v)): a new event, a replay, an event in flight, an IGNORED one. A
FAILED T2, or a T2 lost whole after T1 committed, is CORRECTION-007's 500.

Each answer is recorded once by the access auditor (G7-17 (vii)); a refusal
is logged by its fixed outcome, never with the body, the signature or the
secret.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response
from fastapi.concurrency import run_in_threadpool

from ...services import webhooks as webhook_service
from ..deps import Webhook
from ..problems import ProblemCode, coded, trace_id_of

router = APIRouter(prefix="/webhooks", tags=["Communication"])
logger = logging.getLogger("turab.webhook")

#: The fixed details. None repeats what the request carried.
TOO_LARGE = "The body exceeds 64 KiB."
NOT_READY = "The webhook cannot verify deliveries now. Deliver the same event again later."
NOT_VERIFIED = "The relay signature is missing or does not match the body."
NOT_PROCESSED = ("The event is stored and was not processed. Deliver the same "
                 "provider_event_id again.")


async def _read_limited(request: Request) -> bytes | None:
    """The raw body, or None past `BODY_LIMIT` (G7-15). `Content-Length` is
    checked first; the count while reading covers a missing or false one."""
    declared = request.headers.get("content-length")
    if declared is not None and declared.isdigit() and \
            int(declared) > webhook_service.BODY_LIMIT:
        return None
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > webhook_service.BODY_LIMIT:
            return None
        chunks.append(chunk)
    return b"".join(chunks)


@router.post("/whatsapp", operation_id="postWebhooksWhatsapp", status_code=200)
async def receive_whatsapp(request: Request, webhook: Webhook):
    trace = trace_id_of(request)

    def refused(code: ProblemCode, outcome: str, detail: str):
        response = coded(code, trace, detail)
        logger.warning("webhook refused", extra={"trace_id": trace, "outcome": outcome})
        webhook.answered(response.status_code, outcome)
        return response

    raw = await _read_limited(request)
    if raw is None:
        return refused(ProblemCode.WEBHOOK_BODY_TOO_LARGE, "BODY_TOO_LARGE", TOO_LARGE)
    secret = webhook_service.signing_secret()
    if secret is None:
        logger.error("webhook signing secret not configured",
                     extra={"trace_id": trace, "variable": webhook_service.SECRET_VARIABLE})
        return refused(ProblemCode.WEBHOOK_NOT_READY, "SECRET_NOT_CONFIGURED", NOT_READY)
    if not webhook_service.verify(raw, request.headers.get(webhook_service.SIGNATURE_HEADER),
                                  secret):
        return refused(ProblemCode.UNAUTHENTICATED, "SIGNATURE_NOT_VALID", NOT_VERIFIED)
    try:
        envelope = webhook_service.parse_envelope(raw)
    except webhook_service.EnvelopeRefused as exc:
        return refused(ProblemCode.WEBHOOK_ENVELOPE_NOT_VALID, "ENVELOPE_NOT_VALID", str(exc))

    try:
        event_id, status = await run_in_threadpool(webhook.store, envelope)
    except Exception as exc:
        # T1 did not commit: nothing is stored, so CORRECTION-007 would be false.
        logger.error("webhook event not stored",
                     extra={"trace_id": trace, "cause": type(exc).__name__})
        webhook.answered(500, "NOT_STORED")
        return coded(ProblemCode.INTERNAL_ERROR, trace)
    if status in ("PROCESSED", "IGNORED"):
        webhook.answered(200, "REPLAYED", event_id)
        return Response(status_code=200)

    try:
        outcome = await run_in_threadpool(webhook.process, event_id, envelope)
    except Exception as exc:
        logger.error("webhook processing lost",
                     extra={"trace_id": trace, "webhook_event_id": str(event_id),
                            "cause": type(exc).__name__})
        outcome = "PROCESSING_LOST"
    if outcome in ("FAILED", "PROCESSING_LOST"):
        webhook.answered(500, outcome, event_id)
        return coded(ProblemCode.WEBHOOK_PROCESSING_FAILED, trace, NOT_PROCESSED)
    webhook.answered(200, outcome, event_id)
    return Response(status_code=200)
