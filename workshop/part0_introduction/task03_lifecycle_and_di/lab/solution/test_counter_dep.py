"""
Lab 0.3 SOLUTION — test_counter_dep.py

Pytest that verifies the counter increments once per request. Drop this into
`baseline/tests/test_counter_dep.py` (or run from the solution dir with the
repo root on `PYTHONPATH`).

Run with:

    pytest baseline/tests/test_counter_dep.py -v
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_counter_increments_per_request() -> None:
    """After N requests through TestClient, counter.value should equal N."""
    # Import inside the test so the app-level lifespan has a clean slate.
    from api_gateway.app.main import app
    from api_gateway.app.dependencies_counter import get_counter

    # TestClient as context manager runs the lifespan — init_counter() runs here.
    with TestClient(app) as client:
        # Baseline: counter is 0 right after lifespan startup.
        # Note: we read via the dependency function, the same path the route uses.
        assert get_counter().value == 0, "counter should start at 0"

        N = 10
        for _ in range(N):
            r = client.get("/health")
            assert r.status_code == 200

        assert get_counter().value == N, f"expected counter == {N}, got {get_counter().value}"


def test_metrics_endpoint_returns_count() -> None:
    """The /api/v1/metrics/requests endpoint reports the current counter value."""
    from api_gateway.app.main import app

    with TestClient(app) as client:
        # Fire 5 requests, then query the metrics endpoint.
        for _ in range(5):
            client.get("/health")

        r = client.get("/api/v1/metrics/requests")
        assert r.status_code == 200
        body = r.json()
        # The /metrics call itself counts, so we expect 6 total (5 + the metrics call).
        assert body["count"] == 6, f"expected count == 6, got {body['count']!r}"


def test_dependency_override_isolates_counter() -> None:
    """Demonstrates dependency_overrides — the pattern Part I Task 4 expands on."""
    from api_gateway.app.main import app
    from api_gateway.app.dependencies_counter import RequestCounter, get_counter

    # A pre-populated fake counter. Route should see this, not the real one.
    fake = RequestCounter()
    for _ in range(999):
        fake.increment()

    app.dependency_overrides[get_counter] = lambda: fake
    try:
        with TestClient(app) as client:
            r = client.get("/api/v1/metrics/requests")
            assert r.status_code == 200
            assert r.json()["count"] == 999
    finally:
        # Always clear overrides so other tests see the real dependency.
        app.dependency_overrides.clear()
