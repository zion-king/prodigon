"""
Real-Time Inference Pipeline (Starter -- complete reference implementation).

This pipeline processes prompts one at a time, waiting for each response
before sending the next request. It is the simplest pattern: low complexity,
low throughput, best user-perceived latency for a single request.

Architecture:
    Client ---> Model Service ---> Client (one prompt at a time)

Usage:
    python realtime_pipeline.py

Environment variables:
    MODEL_SERVICE_URL  Base URL of the model service (default: http://localhost:8001)
"""

import asyncio
import json
import os
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

MODEL_SERVICE_URL = os.getenv("MODEL_SERVICE_URL", "http://localhost:8001")
PROMPTS_FILE = Path(__file__).parent / "sample_prompts.json"
TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# Inference helper
# ---------------------------------------------------------------------------

async def call_inference(
    client: httpx.AsyncClient,
    prompt: str,
    max_tokens: int = 256,
) -> dict:
    """Send a single prompt to the model service and return the response."""
    payload = {
        "prompt": prompt,
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }
    response = await client.post("/inference", json=payload)
    response.raise_for_status()
    return response.json()


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------

async def realtime_pipeline(prompts: list[str]) -> dict:
    """Process prompts sequentially, one request at a time.

    Returns:
        dict with "results" (list of responses) and "stats" (timing info).
    """
    results = []
    latencies = []

    async with httpx.AsyncClient(
        base_url=MODEL_SERVICE_URL,
        timeout=httpx.Timeout(TIMEOUT),
    ) as client:
        pipeline_start = time.perf_counter()

        for i, prompt in enumerate(prompts):
            item_start = time.perf_counter()
            try:
                result = await call_inference(client, prompt)
                item_elapsed = (time.perf_counter() - item_start) * 1000  # ms
                latencies.append(item_elapsed)
                results.append({
                    "prompt": prompt,
                    "response": result.get("text", ""),
                    "model": result.get("model", "unknown"),
                    "latency_ms": round(item_elapsed, 1),
                })
                print(f"  [{i + 1}/{len(prompts)}] {item_elapsed:.0f}ms -- {prompt[:50]}...")
            except httpx.HTTPStatusError as exc:
                print(f"  [{i + 1}/{len(prompts)}] ERROR {exc.response.status_code} -- {prompt[:50]}...")
                results.append({
                    "prompt": prompt,
                    "response": None,
                    "error": str(exc),
                    "latency_ms": round((time.perf_counter() - item_start) * 1000, 1),
                })

        pipeline_elapsed = time.perf_counter() - pipeline_start

    stats = {
        "total_time_s": round(pipeline_elapsed, 2),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        "throughput_items_per_s": round(len(prompts) / pipeline_elapsed, 2) if pipeline_elapsed > 0 else 0,
        "total_items": len(prompts),
        "successful": len(latencies),
    }

    return {"results": results, "stats": stats}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    # Load prompts
    with open(PROMPTS_FILE) as f:
        prompts = json.load(f)

    print(f"Real-Time Pipeline: processing {len(prompts)} prompts sequentially")
    print(f"Model Service: {MODEL_SERVICE_URL}")
    print("-" * 60)

    output = await realtime_pipeline(prompts)
    stats = output["stats"]

    print("-" * 60)
    print(f"Total time:      {stats['total_time_s']}s")
    print(f"Avg latency:     {stats['avg_latency_ms']}ms per item")
    print(f"Throughput:      {stats['throughput_items_per_s']} items/sec")
    print(f"Success rate:    {stats['successful']}/{stats['total_items']}")

    return output


if __name__ == "__main__":
    asyncio.run(main())
