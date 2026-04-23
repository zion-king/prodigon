"""
Lab 0.1 SOLUTION — verify.py

End-to-end smoke test: gateway health, sync generate, chat session round-trip.

Run with:

    python workshop/part0_introduction/task01_getting_started/lab/solution/verify.py

Assumes the stack is already running (see walkthrough.sh). Exits 0 on all
tests passing; exits 1 with a readable failure summary otherwise.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urljoin

import httpx

BASE_URL = os.environ.get("PRODIGON_BASE_URL", "http://localhost:8000")
TIMEOUT = httpx.Timeout(15.0)


def test_gateway_health() -> None:
    r = httpx.get(urljoin(BASE_URL, "/health"), timeout=TIMEOUT)
    assert r.status_code == 200, f"/health returned {r.status_code}"
    body = r.json()
    assert body.get("status") == "ok", f"unexpected body: {body!r}"


def test_generate() -> None:
    r = httpx.post(
        urljoin(BASE_URL, "/api/v1/generate"),
        json={"prompt": "Say the word 'pong' and nothing else."},
        timeout=TIMEOUT,
    )
    assert r.status_code == 200, f"/generate returned {r.status_code}: {r.text}"
    body = r.json()
    # Response shape: {"response": "...", "model": "...", "latency_ms": N}
    assert "response" in body, f"missing 'response' key in body: {body!r}"
    assert len(body["response"]) > 0, "empty response string"


def test_chat_session_roundtrip() -> None:
    # Create
    create = httpx.post(
        urljoin(BASE_URL, "/api/v1/chat/sessions"),
        json={"title": "Lab 0.1 verify"},
        timeout=TIMEOUT,
    )
    assert create.status_code in (200, 201), f"POST /chat/sessions returned {create.status_code}: {create.text}"
    session_id = create.json()["id"]

    # Read back
    read = httpx.get(urljoin(BASE_URL, f"/api/v1/chat/sessions/{session_id}"), timeout=TIMEOUT)
    assert read.status_code == 200, f"GET /chat/sessions/{session_id} returned {read.status_code}"
    assert read.json()["id"] == session_id, "session ID mismatch on round-trip"

    # Cleanup — not required for the assertion but keeps the DB tidy between runs
    httpx.delete(urljoin(BASE_URL, f"/api/v1/chat/sessions/{session_id}"), timeout=TIMEOUT)


def main() -> int:
    tests = [
        ("test_gateway_health", test_gateway_health),
        ("test_generate", test_generate),
        ("test_chat_session_roundtrip", test_chat_session_roundtrip),
    ]
    failures = 0
    for name, fn in tests:
        try:
            fn()
            print(f"{name:<32} OK")
        except Exception as exc:  # noqa: BLE001 — we want every failure visible
            print(f"{name:<32} FAIL — {exc}")
            failures += 1

    print()
    if failures:
        print(f"{failures} failed out of {len(tests)}")
        return 1
    print(f"{len(tests)} passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
