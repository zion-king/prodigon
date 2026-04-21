"""
Batch Inference Pipeline (Starter -- YOUR CODE HERE).

This pipeline reads a list of prompts from a JSON file and processes them
concurrently using asyncio.Semaphore to control parallelism. It writes
results to an output file and reports throughput statistics.

Architecture:
    Input File --> [Semaphore-controlled concurrent requests] --> Model Service
                                                               --> Output File

Why a semaphore:
    Without a concurrency limit, sending 1000 prompts simultaneously would
    overwhelm the model service (and likely get rate-limited). A semaphore
    acts as a ticket counter -- only N requests run at the same time.

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
PROMPTS_FILE = Path(__file__).parent / "sample_prompts.json"
OUTPUT_FILE = Path(__file__).parent / "batch_output.json"
TIMEOUT = 60.0


# ---------------------------------------------------------------------------
# Inference helper (same as real-time pipeline)
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

    This function acquires the semaphore before making the HTTP request,
    ensuring no more than N requests are in flight at once.
    """
    # --- YOUR CODE HERE ---
    # 1. Acquire the semaphore (use `async with semaphore:`)
    # 2. Record the start time
    # 3. Call call_inference(client, prompt)
    # 4. Calculate elapsed time in milliseconds
    # 5. Print progress: [{index+1}/{total}] {elapsed}ms -- {prompt[:50]}...
    # 6. Return a dict with: prompt, response text, model, latency_ms
    # 7. Handle exceptions: return a dict with prompt, error message, latency_ms
    raise NotImplementedError("Implement process_single")
    # --- END YOUR CODE ---


async def batch_pipeline(prompts: list[str], concurrency: int = 5) -> dict:
    """Process all prompts concurrently with a concurrency limit.

    Returns:
        dict with "results" (list of responses) and "stats" (timing info).
    """
    semaphore = asyncio.Semaphore(concurrency)

    async with httpx.AsyncClient(
        base_url=MODEL_SERVICE_URL,
        timeout=httpx.Timeout(TIMEOUT),
    ) as client:
        pipeline_start = time.perf_counter()

        # --- YOUR CODE HERE ---
        # 1. Create a list of tasks using process_single for each prompt
        # 2. Use asyncio.gather() to run them all concurrently
        # 3. The semaphore inside process_single controls actual concurrency
        raise NotImplementedError("Implement batch_pipeline task creation")
        # --- END YOUR CODE ---

        pipeline_elapsed = time.perf_counter() - pipeline_start

    # Calculate stats
    latencies = [r["latency_ms"] for r in results if "error" not in r]
    successful = len(latencies)

    stats = {
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
    # Load prompts
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
