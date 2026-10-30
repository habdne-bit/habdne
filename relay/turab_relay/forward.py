"""Duty 5 and §5.1's answers: each FORWARD element sent to TURAB, signed, in
document order; Meta's answer decided from TURAB's.

Plan: `docs/gate/R1_RELAY_PLAN.md` (revision 10) §3 duties 5 and 7, §5.1 (each
class, and the answer to Meta), R1-D2 (synchronous, a timeout per envelope),
R1-D3 (TURAB's 400 or 401: not 200, and an alert), §5.6 (R1-Q2, TURAB's
URL). Step 3, authorized in the review of `da3d778`; corrected after the
review of `c480474`.

**A verified POST** (duty 2 passed), in this order:
1. the relay's key (`transform.signing_key`) and TURAB's URL: either
   missing, the key refused, or **the URL refused by §5.6** (`url_refusal`),
   is 503 and **nothing is sent** (R1-T4.4);
2. every element classed (`transform.elements`), and counted by its class
   and reason. **An ISOLATED element raises an alert** (its fixed reason,
   never a value of the notification);
3. each FORWARD envelope POSTed to TURAB with `X-Turab-Relay-Signature`
   over its exact bytes, **one at a time, in document order**, each under
   its own deadline (R1-D2). **The deadline is the whole limit:** HTTPX's
   own timeout, 5 s by default without network activity, is set to the
   same limit, so it never ends an envelope before the relay's limit does
   (the review of `c480474`);
4. **the first envelope TURAB does not answer 200 stops the delivery:** the
   elements after it are not sent in this attempt, and Meta's answer is not
   200, so Meta redelivers the POST whole (M7). On that redelivery, the
   envelopes TURAB completed are 200 replays that write nothing (S42).
   *Why stop:* §5.1 sends in document order. Going on past a failure would
   let TURAB process a later element before the one that failed, which
   completes only on the redelivery: two statuses of one message, for
   instance, would reach it out of order (G7-5 then refuses the earlier
   one). Stopped, TURAB processes the elements in document order across
   attempts; the cost is that the elements after the failure wait for the
   redelivery;
5. every envelope answered 200: **200 to Meta**, unless an element is
   OVERSIZE. ISOLATED and DROPPED elements never change the answer (§5.1).

**OVERSIZE (step 4, R1-Q1 (a), §5.4):** an element whose envelope's
serialized bytes exceed TURAB's 64 KiB (`transform.ENVELOPE_LIMIT`) is **not
sent and not shortened**; it is counted and **alerted, without content**
(its kind only); the other elements are delivered as above, **the ones
after it included**; and Meta's answer is **not 200** (503
`ENVELOPE_OVERSIZE`), whatever TURAB answered, so the redelivery window
stays open (§5.4). On that redelivery the delivered elements are 200
replays at TURAB that write nothing (S42), and the element is OVERSIZE
again.

**TURAB's answers:**
- 200: completed;
- 500 or 503: not completed, retryable (CORRECTION-007, CORRECTION-008):
  502 to Meta;
- no answer before the deadline, or no connection: 504 to Meta;
- any other status, 400 and 401 among them (R1-D3): **502 to Meta and an
  alert.** TURAB does not refuse an envelope it can read; such an answer
  means a configuration to fix, not a delivery to wait for.


**The relay's logs and alerts carry fixed codes, TURAB's status number and
the trace id: never an envelope, a content, a signature, a key or TURAB's
answer body.** An alert is a record on the `turab_relay.alert` logger;
routing it to an operator is the deployment's, not claimed here. The
`httpx` library logs each request's method, URL and status on its own
logger, never a body or a header; TURAB's URL carries no secret.

**The HTTP client:** `httpx`, with `trust_env=False` (no proxy, `.netrc`
or certificate file taken from the environment), no redirect followed (a
3xx is "any other status"), and **TURAB's certificate verified**
(`verify=True`: the `certifi` roots, with the host name checked).

**TURAB's URL (§5.6, R1-Q2, decided in the review of `c480474`):** `https`
for every address that is not loopback; `http` only on a loopback address
written as an IP literal (`127.0.0.0/8`, `::1`), not a name a resolver
could point elsewhere; no credentials, query or fragment; printable ASCII
only, no escape in the host, read the same by `urllib` and by `httpx`
(scheme, host and port compared; a default port counts as none). Refused
before anything is sent; the alert names the fixed reason, never the URL.
"""
from __future__ import annotations

import asyncio
import ipaddress
import logging
import os
import re
from collections import Counter
from urllib.parse import urlsplit

import httpx

from turab_relay import meta, transform

LOG = logging.getLogger("turab_relay")
ALERT = logging.getLogger("turab_relay.alert")
TURAB_URL_VARIABLE = "TURAB_RELAY_TURAB_WEBHOOK_URL"
#: R1-D2: each envelope's deadline. Meta documents no time limit for its
#: own request (§1), so none is derived from it.
TIMEOUT_SECONDS = 10.0
#: TURAB's retryable answers: CORRECTION-007 (500) and CORRECTION-008 (503).
RETRYABLE = (500, 503)
COMPLETED, NOT_COMPLETED, NO_ANSWER, REFUSED = (
    "COMPLETED", "NOT_COMPLETED", "NO_ANSWER", "REFUSED")


#: §5.6: printable ASCII, no space and no backslash, which parsers read
#: differently.
_URL_CHARACTERS = re.compile(r"[!-\[\]-~]+")
_DEFAULT_PORT = {"https": 443, "http": 80}


def _loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def url_refusal(url: str) -> str | None:
    """§5.6: None when TURAB's URL may be used; otherwise the fixed reason."""
    if _URL_CHARACTERS.fullmatch(url) is None:
        return "MALFORMED"
    try:
        parts = urlsplit(url)
    except ValueError:
        # `urlsplit` refuses it: an unclosed bracket, or brackets around
        # something that is not an IPv6 address (the review of `3dac09f`).
        return "MALFORMED"
    scheme = parts.scheme.lower()
    if scheme not in ("https", "http"):
        return "SCHEME"
    if "@" in parts.netloc:
        return "CREDENTIALS"
    if "?" in url or "#" in url:
        return "QUERY"
    if "%" in parts.netloc:
        return "MALFORMED"   # an escaped host: `urllib` and `httpx` read it differently
    try:
        host, port = parts.hostname, parts.port
        parsed = httpx.URL(url)
    except (ValueError, httpx.InvalidURL):
        return "MALFORMED"
    if port == _DEFAULT_PORT[scheme]:
        port = None   # `httpx` drops a default port; `urllib` keeps it
    if not host or (parsed.scheme, parsed.host, parsed.port) != (scheme, host, port):
        return "MALFORMED"
    if scheme == "http" and not _loopback(host):
        return "UNENCRYPTED"
    return None


def alert(reason: str, trace: str) -> None:
    ALERT.error("alert %s trace=%s", reason, trace)


async def deliver(client: httpx.AsyncClient, url: str, envelope: bytes, signature: str,
                  timeout: float) -> tuple[str, int | None]:
    """One envelope to TURAB: its outcome, and TURAB's status if it answered."""
    try:
        async with asyncio.timeout(timeout):
            response = await client.post(url, content=envelope, headers={
                "content-type": "application/json",
                transform.SIGNATURE_HEADER: signature})
    except (TimeoutError, httpx.HTTPError, httpx.InvalidURL):
        return NO_ANSWER, None
    if response.status_code == 200:
        return COMPLETED, 200
    if response.status_code in RETRYABLE:
        return NOT_COMPLETED, response.status_code
    return REFUSED, response.status_code


async def post(raw: bytes, *, counts: Counter, trace: str, timeout: float = TIMEOUT_SECONDS,
               transport: httpx.AsyncBaseTransport | None = None) -> meta.Answer:
    """A verified POST: its elements delivered as this module states, and
    Meta's answer."""
    try:
        key = transform.signing_key()
    except transform.RelayKeyRefused:
        alert("RELAY_KEY_REFUSED", trace)
        return meta.Answer(503, "RELAY_KEY_REFUSED")
    url = os.environ.get(TURAB_URL_VARIABLE)
    if not url:
        alert("TURAB_URL_NOT_CONFIGURED", trace)
        return meta.Answer(503, "TURAB_URL_NOT_CONFIGURED")
    refusal = url_refusal(url)
    if refusal is not None:
        alert(f"TURAB_URL_NOT_ALLOWED {refusal}", trace)
        return meta.Answer(503, "TURAB_URL_NOT_ALLOWED")
    elements = transform.elements(raw)
    for element in elements:
        counts[(element.cls, element.reason)] += 1
        if element.cls == transform.ISOLATED:
            alert(f"ISOLATED {element.reason}", trace)
        elif element.cls == transform.OVERSIZE:
            alert(f"OVERSIZE {element.kind}", trace)
    oversize = any(element.cls == transform.OVERSIZE for element in elements)
    failed: meta.Answer | None = None
    async with httpx.AsyncClient(transport=transport, trust_env=False,
                                 follow_redirects=False, verify=True,
                                 timeout=httpx.Timeout(timeout)) as client:
        for element in elements:
            if element.cls != transform.FORWARD:
                continue
            outcome, status = await deliver(client, url, element.envelope,
                                            transform.sign(element.envelope, key), timeout)
            counts[("DELIVERY", outcome)] += 1
            if outcome != COMPLETED:
                failed = _not_completed(outcome, status, trace)
                break
    if failed is None and oversize:
        failed = meta.Answer(503, "ENVELOPE_OVERSIZE")
    return failed or meta.Answer(200, "DELIVERED")


def _not_completed(outcome: str, status: int | None, trace: str) -> meta.Answer:
    """Meta's answer for an envelope TURAB did not complete: never 200."""
    if outcome == NO_ANSWER:
        return meta.Answer(504, "TURAB_NO_ANSWER")
    if outcome == NOT_COMPLETED:
        LOG.warning("turab not completed %s trace=%s", status, trace)
        return meta.Answer(502, "TURAB_NOT_COMPLETED")
    alert(f"TURAB_REFUSED {status}", trace)
    return meta.Answer(502, "TURAB_REFUSED")
