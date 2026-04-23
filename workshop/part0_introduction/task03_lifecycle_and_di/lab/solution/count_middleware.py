"""
Lab 0.3 SOLUTION — count_middleware.py

Reference implementation. Drops into
`baseline/api_gateway/app/middleware/count.py` as-is.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp

from ..dependencies_counter import get_counter


class CountMiddleware(BaseHTTPMiddleware):
    """Middleware that increments the global request counter on every request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        # Count first so failed downstream requests still count toward the
        # "requests received" metric the ops team asked for.
        get_counter().increment()
        return await call_next(request)
