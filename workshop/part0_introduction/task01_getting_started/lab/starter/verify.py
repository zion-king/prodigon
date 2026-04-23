"""
Lab 0.1 STARTER — verify.py

A minimal integration smoke test that exercises the three most important
paths through the baseline:
  1. Gateway health
  2. Sync generate
  3. Chat session round-trip (POST then GET)

Fill in each TODO. Run with:

    python workshop/part0_introduction/task01_getting_started/lab/starter/verify.py

All three tests should print "OK" and the script should exit 0.
"""

from __future__ import annotations

import sys
from urllib.parse import urljoin

import httpx

BASE_URL = "http://localhost:8000"


def test_gateway_health() -> None:
    """GET /health — should return 200 with a JSON body containing status:'ok'."""
    # TODO: httpx.get(...), assert 200, assert body['status'] == 'ok'
    raise NotImplementedError("Fill in test_gateway_health")


def test_generate() -> None:
    """POST /api/v1/generate with a short prompt — should return 200 with non-empty response."""
    # TODO: httpx.post(urljoin(BASE_URL, '/api/v1/generate'), json={"prompt": "hello"})
    # TODO: assert response.status_code == 200
    # TODO: assert len(response.json()['response']) > 0
    raise NotImplementedError("Fill in test_generate")


def test_chat_session_roundtrip() -> None:
    """POST /api/v1/chat/sessions, then GET it back; assert the ID matches."""
    # TODO: create a session via POST, capture the returned 'id'
    # TODO: GET /api/v1/chat/sessions/{id} and confirm the ID matches
    raise NotImplementedError("Fill in test_chat_session_roundtrip")


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
        except Exception as exc:  # noqa: BLE001 — we want to see everything
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
