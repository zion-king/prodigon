"""
Lab 0.3 STARTER — count_middleware.py

Copy this file into `baseline/api_gateway/app/middleware/count.py` and
fill in the TODO inside `dispatch`.

Reference: `baseline/api_gateway/app/middleware/timing.py` for the shape of
a production Starlette middleware.
"""

from __future__ import annotations

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import ASGIApp


class CountMiddleware(BaseHTTPMiddleware):
    """Middleware that increments the global request counter on every request."""

    def __init__(self, app: ASGIApp) -> None:
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:  # type: ignore[override]
        """
        TODO:
        - Import `get_counter` from `..dependencies_counter` (absolute import
          `from api_gateway.app.dependencies_counter import get_counter` also
          works depending on your module layout; imitate how timing.py resolves
          its imports)
        - Call `get_counter().increment()` BEFORE calling `call_next(request)`
          so failed downstream requests still count (the ops team wants
          "requests received", not "requests served successfully")
        - Await `call_next(request)` to produce the response
        - Return the response unchanged

        Hint: look at `TimingMiddleware.dispatch` for the canonical shape.
        Keep it this simple — don't try to add per-path breakdown here;
        that's the bonus challenge.
        """
        raise NotImplementedError("Task 3: implement dispatch()")
