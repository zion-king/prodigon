"""
Lab 0.3 STARTER — custom_dep.py

Copy this file into `baseline/api_gateway/app/dependencies_counter.py` and
fill in the two TODOs. The `RequestCounter` class is already complete — your
job is to wire it up using the module-global singleton pattern you saw in
`baseline/api_gateway/app/dependencies.py`.

Reference: Lesson 0.3 README, section "Level 2 — how the baseline wires it".
"""

from __future__ import annotations

import threading


class RequestCounter:
    """Thread-safe monotonic counter. One instance per process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._value = 0

    def increment(self) -> None:
        with self._lock:
            self._value += 1

    @property
    def value(self) -> int:
        with self._lock:
            return self._value


# -----------------------------------------------------------------------------
# Module-global singleton — the pattern from `dependencies.py`
# -----------------------------------------------------------------------------

_counter: RequestCounter | None = None


def init_counter() -> RequestCounter:
    """
    Initialize the module-global counter. Called from `lifespan` at startup.

    TODO:
    - Declare `global _counter`
    - Assign a fresh `RequestCounter()` instance
    - Return it

    Imitate `init_dependencies` in `baseline/api_gateway/app/dependencies.py`.
    """
    raise NotImplementedError("Task 2: implement init_counter()")


def get_counter() -> RequestCounter:
    """
    FastAPI dependency — returns the module-global counter.

    TODO:
    - If `_counter is None`, raise `RuntimeError("Counter not initialized.")`
      (matches the pattern in `get_model_client` — fail-fast if someone forgot
      to call `init_counter()` in `lifespan`)
    - Otherwise return `_counter`
    """
    raise NotImplementedError("Task 2: implement get_counter()")
