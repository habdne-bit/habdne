"""Structured logging.

Ref: API_CONTRACTS v0.2 §8 ("structured logging without leaking PII/sensitive
claims"; "logs must not contain OTP codes or sensitive document payloads");
RFC-001 R6.3b.

JSON lines, with the trace id on every record so a client holding a `trace_id`
from a problem response can be matched to the log without the log having
carried anything sensitive in the first place.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from typing import Any

#: Values that must never be logged, whatever the log call passes. Redaction is
#: last-resort: the real defence is not putting these in a log record. But a
#: careless `logger.info(row)` should be defanged rather than shipped.
_SENSITIVE_KEYS = {
    "otp", "otp_code", "code", "password", "secret", "token", "authorization",
    "seller_expectation_dzd", "claimed_value", "raw_text", "payload",
    "document", "external_url", "external_ref", "notes",
}

_OTP_PATTERN = re.compile(r"\b\d{4,8}\b")
REDACTED = "[REDACTED]"

_RESERVED = {
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "module", "msecs", "message",
    "msg", "name", "pathname", "process", "processName", "relativeCreated",
    "stack_info", "thread", "threadName", "taskName",
}


def redact(value: Any, key: str | None = None) -> Any:
    if key and key.lower() in _SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, dict):
        return {k: redact(v, k) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value


class JsonFormatter(logging.Formatter):
    """One JSON object per line, with sensitive keys redacted."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in record.__dict__.items():
            if key not in _RESERVED and not key.startswith("_"):
                payload[key] = redact(value, key)
        if record.exc_info:
            # The type and message, never the full traceback: a traceback can
            # carry query text and bound parameters.
            exc_type, exc, _ = record.exc_info
            payload["error"] = {
                "type": exc_type.__name__ if exc_type else "Error",
                "message": str(exc)[:500],
            }
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level: int = logging.INFO) -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    # Access records are emitted by the auditor; they inherit this handler.
    logging.getLogger("turab").setLevel(level)
