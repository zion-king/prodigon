"""
REST Client for Model Inference -- COMPLETE REFERENCE

This client calls the Model Service's REST /inference endpoint using httpx.
Use this as a reference to compare REST and gRPC call patterns.

Run (with the REST server already running on port 8001):
    python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.starter.rest_client
"""

import asyncio
import time

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REST_BASE_URL = "http://localhost:8001"
INFERENCE_ENDPOINT = f"{REST_BASE_URL}/inference"


async def call_inference():
    """Send a POST request to the REST /inference endpoint."""
    print("\n--- REST /inference ---")

    payload = {
        "prompt": "Explain gRPC in one sentence.",
        "model": "llama-3.3-70b-versatile",
        "max_tokens": 256,
        "temperature": 0.7,
    }

    async with httpx.AsyncClient() as client:
        start = time.perf_counter()
        response = await client.post(INFERENCE_ENDPOINT, json=payload)
        latency_ms = (time.perf_counter() - start) * 1000

    response.raise_for_status()
    data = response.json()

    print(f"Status code: {response.status_code}")
    print(f"Response text: {data['text']}")
    print(f"Model: {data['model']}")
    print(f"Usage: {data['usage']}")
    print(f"Server latency: {data['latency_ms']}ms")
    print(f"Round-trip latency: {latency_ms:.2f}ms")

    return data


async def call_health():
    """Check the REST health endpoint."""
    print("\n--- REST /health ---")

    async with httpx.AsyncClient() as client:
        response = await client.get(f"{REST_BASE_URL}/health")

    response.raise_for_status()
    data = response.json()
    print(f"Health: {data}")

    return data


async def main():
    """Run REST client calls."""
    print(f"Calling REST API at {REST_BASE_URL}")

    try:
        await call_health()
        await call_inference()
    except httpx.ConnectError:
        print(
            f"\nERROR: Could not connect to {REST_BASE_URL}. "
            "Make sure the Model Service is running:\n"
            "  USE_MOCK=true uvicorn model_service.app.main:app --port 8001"
        )
    except httpx.HTTPStatusError as e:
        print(f"\nERROR: HTTP {e.response.status_code}: {e.response.text}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
