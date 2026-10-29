"""Meta's two checks: the subscription GET (duty 1) and the signature of a
notification (duty 2).

Plan: `docs/gate/R1_RELAY_PLAN.md` §1 (M2-M5), §3 duties 1 and 2, R1-D11.
Meta's requirements are quoted in `docs/gate/evidence/R1-META-SOURCES.txt`:
- the GET carries `hub.mode`, `hub.challenge` and `hub.verify_token`; it is
  valid when the token equals the stored string, and is then answered 200
  with the challenge, otherwise with anything but 200 (E1-E3);
- a POST carries `X-Hub-Signature-256: sha256=<hash>`, an HMAC-SHA256 of the
  payload with the app secret (E5, E6). It is computed here over the **raw
  bytes received**, never over a re-serialized body.

**Every comparison of a secret goes through `hmac.compare_digest`, on
bytes** (R1-T1.5, R1-T2.8), imported into this module's namespace so its
call path can be observed there. Python documents it as avoiding content-based
short circuiting, with `str` arguments limited to ASCII (P1, P2), hence the
UTF-8 encoding here; and documents that arguments of different lengths may
reveal their lengths, not their values (P3).

Both secrets are read from the environment at each request; an absent or
empty one fails closed (R1-T1.4, R1-T2.5).
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from hmac import compare_digest
from urllib.parse import parse_qs

VERIFY_TOKEN_VARIABLE = "TURAB_RELAY_META_VERIFY_TOKEN"
APP_SECRET_VARIABLE = "TURAB_RELAY_META_APP_SECRET"
SIGNATURE_HEADER = "x-hub-signature-256"
_SIGNATURE = re.compile(r"sha256=([0-9a-f]{64})")


def _secret(variable: str) -> bytes | None:
    value = os.environ.get(variable)
    return value.encode("utf-8") if value else None


@dataclass(frozen=True)
class Answer:
    """What the relay answers, and the fixed reason it logs (never a value)."""
    status: int
    reason: str
    body: bytes = b""


def subscription(query_string: bytes) -> Answer:
    """Duty 1: Meta's subscription GET (E1-E3, R1-D11)."""
    stored = _secret(VERIFY_TOKEN_VARIABLE)
    if stored is None:
        return Answer(503, "VERIFY_TOKEN_NOT_CONFIGURED")
    try:
        params = parse_qs(query_string.decode("utf-8"), keep_blank_values=True,
                          strict_parsing=False)
    except UnicodeDecodeError:
        return Answer(400, "QUERY_NOT_UTF8")
    values = {k: params.get(k, []) for k in ("hub.mode", "hub.challenge", "hub.verify_token")}
    if any(len(v) != 1 for v in values.values()):
        return Answer(400, "SUBSCRIPTION_PARAMETERS_MISSING_OR_REPEATED")
    mode, challenge, token = (values[k][0] for k in ("hub.mode", "hub.challenge",
                                                      "hub.verify_token"))
    if mode != "subscribe":
        return Answer(400, "SUBSCRIPTION_MODE_NOT_SUBSCRIBE")
    if not challenge or not token:
        return Answer(400, "SUBSCRIPTION_PARAMETERS_EMPTY")
    if not compare_digest(token.encode("utf-8"), stored):
        return Answer(403, "VERIFY_TOKEN_MISMATCH")
    return Answer(200, "SUBSCRIPTION_VERIFIED", challenge.encode("utf-8"))


def signature_valid(raw: bytes, header: str | None, secret: bytes) -> bool:
    """Duty 2: `X-Hub-Signature-256` over the raw bytes received (E5, E6)."""
    match = _SIGNATURE.fullmatch(header or "")
    if match is None:
        return False
    expected = hmac.new(secret, raw, hashlib.sha256).hexdigest()
    return compare_digest(expected.encode("ascii"), match.group(1).encode("ascii"))
