"""
Streaming Inference Pipeline (Solution -- complete).

Uses asyncio.Queue as an in-memory stream to demonstrate the streaming
processing pattern. A producer pushes prompts onto a bounded queue, multiple
consumers pull and process them, and a collector gathers results.

When to use streaming:
    - Data arrives continuously (logs, user events, sensor readings).
    - You need near-real-time results but can tolerate seconds of delay.
    - You want steady resource utilization instead of idle-then-burst.

Key design decisions:
    - Bounded queue (maxsize) provides backpressure: the producer blocks when
      the queue is full, preventing memory exhaustion.
    - Multiple consumers provide parallelism without needing a semaphore --
      the queue itself serializes access.
    - Sentinel values (None) signal end-of-stream cleanly.

Architecture:
    Producer --> [asyncio.Queue (bounded)] --> Consumer 0 --> Model Service
                                           --> Consumer 1 --> Model Service
                                           --> Consumer 2 --> Model Service
                                                           --> [Results Queue] --> Collector

Usage:
    python streaming_pipeline.py

Environment variables:
    MODEL_SERVICE_URL       Base URL of the model service (default: http://localhost:8001)
    STREAM_CONSUMERS        Number of consumer coroutines (default: 3)
    STREAM_BUFFER_SIZE      Max items in the stream queue (default: 5)
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
NUM_CONSUMERS = int(os.getenv("STREAM_CONSUMERS", "3"))
BUFFER_SIZE = int(os.getenv("STREAM_BUFFER_SIZE", "5"))
PROMPTS_FILE = Path(__file__).parent.parent / "starter" / "sample_prompts.json"
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
# Producer
# ---------------------------------------------------------------------------

async def producer(
    prompts: list[str],
    stream: asyncio.Queue,
    num_consumers: int,
):
    """Push prompts onto the stream queue, then send end-of-stream sentinels.

    The producer simulates data arriving over time. In a real system this
    would be reading from Kafka, Redis Streams, or a websocket.

    Backpressure: when the queue is full (maxsize reached), the put() call
    blocks until a consumer frees a slot. This naturally throttles the
    producer to match consumer speed.
    """
    for i, prompt in enumerate(prompts):
        await stream.put((i, prompt))
        print(f"  [producer] enqueued prompt {i + 1}/{len(prompts)} "
              f"(queue depth: {stream.qsize()}/{BUFFER_SIZE})")

    # Send one None sentinel per consumer so each one knows to shut down.
    # This is a common pattern in producer-consumer systems.
    for _ in range(num_consumers):
        await stream.put(None)

    print("  [producer] all prompts enqueued, sentinels sent")


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------

async def consumer(
    consumer_id: int,
    stream: asyncio.Queue,
    results_queue: asyncio.Queue,
    client: httpx.AsyncClient,
):
    """Pull prompts from the stream, process them, push results.

    Each consumer runs in its own coroutine and competes with other consumers
    for items in the queue. The queue handles synchronization -- no locks needed.

    The consumer stops when it receives a None sentinel from the producer.
    """
    processed = 0

    while True:
        # Block until an item is available
        item = await stream.get()

        # None sentinel means end-of-stream for this consumer
        if item is None:
            print(f"  [consumer-{consumer_id}] shutting down after {processed} items")
            break

        index, prompt = item
        item_start = time.perf_counter()

        try:
            result = await call_inference(client, prompt)
            item_elapsed = (time.perf_counter() - item_start) * 1000  # ms

            print(f"  [consumer-{consumer_id}] processed prompt {index + 1} "
                  f"in {item_elapsed:.0f}ms (queue depth: {stream.qsize()})")

            await results_queue.put({
                "index": index,
                "prompt": prompt,
                "response": result.get("text", ""),
                "model": result.get("model", "unknown"),
                "latency_ms": round(item_elapsed, 1),
            })

        except (httpx.HTTPStatusError, httpx.RequestError) as exc:
            item_elapsed = (time.perf_counter() - item_start) * 1000

            print(f"  [consumer-{consumer_id}] ERROR on prompt {index + 1}: {exc}")

            await results_queue.put({
                "index": index,
                "prompt": prompt,
                "error": str(exc),
                "latency_ms": round(item_elapsed, 1),
            })

        processed += 1


# ---------------------------------------------------------------------------
# Results collector
# ---------------------------------------------------------------------------

async def collect_results(
    results_queue: asyncio.Queue,
    total_items: int,
) -> list[dict]:
    """Collect results from all consumers until every item is accounted for.

    Results may arrive out of order (since multiple consumers process
    concurrently), so we sort by original index at the end.
    """
    results = []
    while len(results) < total_items:
        result = await results_queue.get()
        results.append(result)

    # Restore original ordering
    results.sort(key=lambda r: r.get("index", 0))
    return results


# ---------------------------------------------------------------------------
# Pipeline orchestrator
# ---------------------------------------------------------------------------

async def streaming_pipeline(
    prompts: list[str],
    num_consumers: int = 3,
    buffer_size: int = 5,
) -> dict:
    """Run the full streaming pipeline: producer, consumers, collector.

    Orchestration:
        1. Create bounded stream queue and unbounded results queue.
        2. Launch producer, consumers, and collector as concurrent tasks.
        3. Wait for all to complete.
        4. Compute and return statistics.

    Returns:
        dict with "results" and "stats".
    """
    # Bounded queue provides backpressure
    stream: asyncio.Queue = asyncio.Queue(maxsize=buffer_size)
    # Results queue is unbounded -- results are consumed as fast as produced
    results_queue: asyncio.Queue = asyncio.Queue()

    async with httpx.AsyncClient(
        base_url=MODEL_SERVICE_URL,
        timeout=httpx.Timeout(TIMEOUT),
    ) as client:
        pipeline_start = time.perf_counter()

        # Launch all components concurrently
        producer_task = asyncio.create_task(
            producer(prompts, stream, num_consumers)
        )
        consumer_tasks = [
            asyncio.create_task(
                consumer(i, stream, results_queue, client)
            )
            for i in range(num_consumers)
        ]
        collector_task = asyncio.create_task(
            collect_results(results_queue, len(prompts))
        )

        # Wait for completion in dependency order
        await producer_task          # Producer finishes first (just enqueues)
        await asyncio.gather(*consumer_tasks)  # Consumers process all items
        results = await collector_task         # Collector returns sorted results

        pipeline_elapsed = time.perf_counter() - pipeline_start

    # Compute statistics
    latencies = [r["latency_ms"] for r in results if "error" not in r]
    successful = len(latencies)

    stats = {
        "pipeline": "streaming",
        "total_time_s": round(pipeline_elapsed, 2),
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        "throughput_items_per_s": round(len(prompts) / pipeline_elapsed, 2) if pipeline_elapsed > 0 else 0,
        "total_items": len(prompts),
        "successful": successful,
        "num_consumers": num_consumers,
        "buffer_size": buffer_size,
    }

    return {"results": results, "stats": stats}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    with open(PROMPTS_FILE) as f:
        prompts = json.load(f)

    print(f"Streaming Pipeline: processing {len(prompts)} prompts")
    print(f"  Consumers: {NUM_CONSUMERS}, Buffer size: {BUFFER_SIZE}")
    print(f"  Model Service: {MODEL_SERVICE_URL}")
    print("-" * 60)

    output = await streaming_pipeline(prompts, NUM_CONSUMERS, BUFFER_SIZE)
    stats = output["stats"]

    print("-" * 60)
    print(f"Total time:      {stats['total_time_s']}s")
    print(f"Avg latency:     {stats['avg_latency_ms']}ms per item")
    print(f"Throughput:      {stats['throughput_items_per_s']} items/sec")
    print(f"Success rate:    {stats['successful']}/{stats['total_items']}")
    print(f"Consumers:       {stats['num_consumers']}")
    print(f"Buffer size:     {stats['buffer_size']}")

    return output


if __name__ == "__main__":
    asyncio.run(main())
