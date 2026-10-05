"""Response classes.

Ref: review of bf052f4, R-S4-7-03; `turab.exact_json`.
"""
from __future__ import annotations

from typing import Any

from fastapi.responses import JSONResponse

from .. import exact_json


class ExactJSONResponse(JSONResponse):
    """JSON whose numbers are written exactly: a `Decimal` by its own digits,
    still a JSON number. Everything else renders as `JSONResponse` renders it."""

    def render(self, content: Any) -> bytes:
        return exact_json.dumps(content).encode("utf-8")
