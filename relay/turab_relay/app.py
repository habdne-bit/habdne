"""The relay's HTTP boundary: Meta's GET, the inbound limit, Meta's
signature, the client certificate's identity (step 1), and the delivery of a
verified POST to TURAB (step 3).

Plan: `docs/gate/R1_RELAY_PLAN.md` §3 duties 1, 2 and 5, §5.1, §5.2
(R1-D10), R1-D2, R1-D4, R1-D11.

**The order of a POST's checks:**
1. the inbound limit (R1-D4: 3 MiB), before the body is read whole: a
   `Content-Length` declaring more is refused unread, and the bytes are
   counted as they arrive (413);
2. the app secret, absent: 503;
3. `X-Hub-Signature-256` over the raw bytes: 401 when missing or wrong;
4. **verified: delivered to TURAB, and answered, as `forward.py` states**
   (step 3). 200 only when TURAB answered 200 for every envelope sent.

**The client certificate (§5.2):** the TLS layer validates the certificate's
chain to Meta's CA, its only anchor, and its validity (`tls.py`); this
application then requires the identity, `client.webhooks.fbclientcerts.com`,
**read from the validated certificate** the server puts in the ASGI scope's
TLS extension. A header naming it counts for nothing. Without a validated
certificate in the scope, every request is 403. `create_app` requires it by
default; only a test of duties 1 and 2 turns it off, explicitly.

**Logs:** a refusal's fixed reason and the request's trace id. Never the
body, a header's value, the token, the challenge or the signature.
"""
from __future__ import annotations

import logging
import os
import re
import uuid

from collections import Counter

from turab_relay import forward, meta, tls

LOG = logging.getLogger("turab_relay")
PATH = "/whatsapp/webhook"
#: R1-D4 (a): 3 MiB, at least Meta's "3 MB" (E11) under either reading.
INBOUND_LIMIT = 3 * 1024 * 1024
_DECIMAL = re.compile(r"[0-9]+")


def declared_over_limit(declared: str | None) -> bool:
    """Whether `Content-Length` declares more than the limit, compared without
    converting an unbounded string to an integer."""
    if declared is None or _DECIMAL.fullmatch(declared) is None:
        return False
    significant = declared.lstrip("0")
    if len(significant) > len(str(INBOUND_LIMIT)):
        return True
    return bool(significant) and int(significant) > INBOUND_LIMIT


async def _read_body(receive) -> bytes | None:
    """The raw body, or None as soon as it passes the limit."""
    chunks, size = [], 0
    while True:
        message = await receive()
        if message["type"] == "http.disconnect":
            return None
        chunk = message.get("body", b"")
        size += len(chunk)
        if size > INBOUND_LIMIT:
            return None
        chunks.append(chunk)
        if not message.get("more_body", False):
            return b"".join(chunks)


async def _send(send, answer: meta.Answer, trace: str) -> None:
    if answer.status != 200:
        LOG.info("refused %s %s trace=%s", answer.status, answer.reason, trace)
    headers = [(b"content-type", b"text/plain; charset=utf-8"),
               (b"x-content-type-options", b"nosniff"), (b"cache-control", b"no-store"),
               (b"content-length", str(len(answer.body)).encode())]
    await send({"type": "http.response.start", "status": answer.status, "headers": headers})
    await send({"type": "http.response.body", "body": answer.body})


def _header(scope, name: bytes) -> str | None:
    found = [v for k, v in scope.get("headers", []) if k.lower() == name]
    return found[0].decode("latin-1") if len(found) == 1 else None


async def _post(scope, receive, trace: str, deliver) -> meta.Answer:
    if declared_over_limit(_header(scope, b"content-length")):
        return meta.Answer(413, "BODY_TOO_LARGE")
    raw = await _read_body(receive)
    if raw is None:
        return meta.Answer(413, "BODY_TOO_LARGE")
    secret = os.environ.get(meta.APP_SECRET_VARIABLE)
    if not secret:
        return meta.Answer(503, "APP_SECRET_NOT_CONFIGURED")
    if not meta.signature_valid(raw, _header(scope, meta.SIGNATURE_HEADER.encode()),
                                secret.encode("utf-8")):
        return meta.Answer(401, "SIGNATURE_NOT_VALID")
    return await deliver(raw, trace)


def create_app(*, require_client_certificate: bool = True,
               turab_timeout: float = forward.TIMEOUT_SECONDS, turab_transport=None):
    """The relay's ASGI application. `require_client_certificate` is True
    unless a test of duties 1 and 2 turns it off explicitly. `app.counts`
    counts each element by class and reason, and each delivery by outcome,
    for this process. `turab_transport` is an `httpx` transport a test may
    put in place of the network."""
    counts: Counter = Counter()

    async def deliver(raw: bytes, trace: str) -> meta.Answer:
        return await forward.post(raw, counts=counts, trace=trace, timeout=turab_timeout,
                                  transport=turab_transport)

    async def app(scope, receive, send):
        if scope["type"] == "lifespan":
            while True:
                message = await receive()
                if message["type"] == "lifespan.startup":
                    await send({"type": "lifespan.startup.complete"})
                elif message["type"] == "lifespan.shutdown":
                    await send({"type": "lifespan.shutdown.complete"})
                    return
        if scope["type"] != "http":
            return
        trace = uuid.uuid4().hex
        if require_client_certificate and not tls.meta_identity(scope):
            await _send(send, meta.Answer(403, "CLIENT_CERTIFICATE_NOT_META"), trace)
            return
        if scope["path"] != PATH:
            await _send(send, meta.Answer(404, "NOT_FOUND"), trace)
            return
        if scope["method"] == "GET":
            answer = meta.subscription(scope.get("query_string", b""))
        elif scope["method"] == "POST":
            answer = await _post(scope, receive, trace, deliver)
        else:
            answer = meta.Answer(405, "METHOD_NOT_ALLOWED")
        await _send(send, answer, trace)

    app.counts = counts
    return app
