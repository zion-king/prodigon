"""
Batch Inference Pipeline (Solution -- complete).

Reads a list of prompts from a JSON file and processes them concurrently
using asyncio.Semaphore to control parallelism. Results are written to an
output file with throughput statistics.

When to use batch:
    - Results are not time-sensitive (nightly reports, bulk embeddings).
    - You want maximum throughput (process 10,000 items as fast as possible).
    - You can tolerate higher latency for individual items.

Key design decisions:
    - asyncio.Semaphore limits concurrency to avoid overwhelming the model service.
    - asyncio.gather runs all tasks concurrently; the semaphore is the bottleneck.
    - Results are collected in order because gather preserves task order.

Architecture:
    Input File --> [Semaphore-controlled concurrent requests] --> Model Service
                                                               --> Output File

Usage:
    python batch_pipeline.py

Environment variables:
    MODEL_SERVICE_URL  Base URL of the model service (default: http://localhost:8001)
    BATCH_CONCURRENCY  Max concurrent requests (default: 5)
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
BATCH_CONCURRENCY = int(os.getenv("BATCH_CONCURRENCY", "5"))
PROMPTS_FILE = Path(__file__).parent.parent / "starter" / "sample_prompts.json"
OUTPUT_FILE = Path(__file__).parent / "batch_output.json"
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

async def process_single(
    client: httpx.AsyncClient,
    semaphore: asyncio.Semaphore,
    index: int,
    prompt: str,
    total: int,
) -> dict:
    """Process a single prompt, respecting the semaphore concurrency limit.

    The semaphore acts as a ticket counter: only N coroutines can hold it
    at the same time. The rest wait until a slot opens up. This prevents
    overwhelming the downstream model service while still achieving high
    throughput via concurrency.
    """
    async with semaphore:
        item_start = time.perf_counter()
        try:
            result = await call_inference(client, prompt)
            item_elapsed = (time.perf_counter() - item_start) * 1000  # ms
            print(f"  [{index + 1}/{total}] {item_elapsed:.0f}ms -- {prompt[:50]}...")
            return {
                "index": index,
                "prompt": prompt,
                "response": result.get("text", ""),
                "model": result.get("model", "unknown"),
                "latency_ms": round(item_elapsed, 1),
            }
        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            item_elapsed = (time.perf_counter() - item_start) * 1000
            print(f"  [{index + 1}/{total}] ERROR -- {prompt[:50]}...")
            return {
                "index": index,
                "prompt": prompt,
                "error": str(exc),
                "latency_ms": round(item_elapsed, 1),
            }


async def batch_pipeline(prompts: list[str], concurrency: int = 5) -> dict:
    """Process all prompts concurrently with a concurrency limit.

    How it works:
        1. Create one asyncio task per prompt.
        2. All tasks start immediately, but the semaphore inside process_single
           ensures only `concurrency` tasks are actively making HTTP requests.
        3. asyncio.gather waits for all tasks and returns results in order.

    Returns:
        dict with "results" (list of responses) and "stats" (timing info).
    """
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        base_url=MODEL_SERVICE_URL,
        timeout=httpx.Timeout(TIMEOUT),
    ) as client:
        pipeline_start = time.perf_counter()

        # Create one task per prompt. The semaphore inside process_single
        # ensures only `concurrency` tasks are actively calling the model
        # service at any given time.
        tasks = [
            process_single(client, semaphore, i, prompt, len(prompts))
            for i, prompt in enumerate(prompts)
        ]
        results = await asyncio.gather(*tasks)

        pipeline_elapsed = time.perf_counter() - pipeline_start

    # Convert gather output (tuple) to list
    results = list(results)

    # Calculate stats
    latencies = [r["latency_ms"] for r in results if "error" not in r]
    successful = len(latencies)

    stats = {
        "pipeline": "batch",
        "total_time_s": round(pipeline_elapsed, 2),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        "throughput_items_per_s": round(len(prompts) / pipeline_elapsed, 2) if pipeline_elapsed > 0 else 0,
        "total_items": len(prompts),
        "successful": successful,
        "concurrency": concurrency,
    }

    return {"results": results, "stats": stats}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    with open(PROMPTS_FILE) as f:
        prompts = json.load(f)

    print(f"Batch Pipeline: processing {len(prompts)} prompts (concurrency={BATCH_CONCURRENCY})")
    print(f"Model Service: {MODEL_SERVICE_URL}")
    print("-" * 60)

    output = await batch_pipeline(prompts, concurrency=BATCH_CONCURRENCY)
    stats = output["stats"]

    print("-" * 60)
    print(f"Total time:      {stats['total_time_s']}s")
    print(f"Avg latency:     {stats['avg_latency_ms']}ms per item")
    print(f"Throughput:      {stats['throughput_items_per_s']} items/sec")
    print(f"Success rate:    {stats['successful']}/{stats['total_items']}")
    print(f"Concurrency:     {stats['concurrency']}")

    # Write results to file
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    print(f"Results written to {OUTPUT_FILE}")

    return output


if __name__ == "__main__":
    asyncio.run(main())
