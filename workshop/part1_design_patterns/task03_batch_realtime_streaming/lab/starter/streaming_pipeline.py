"""
Streaming Inference Pipeline (Starter -- YOUR CODE HERE).

This pipeline uses asyncio.Queue as an in-memory stream. A producer pushes
prompts onto the queue, one or more consumers pull prompts off and process
them, and results are collected via a separate results queue.

Architecture:
    Producer --> [asyncio.Queue (stream)] --> Consumer(s) --> Model Service
                                                          --> [Results Queue] --> Collector

Why asyncio.Queue:
    In production you would use Redis Streams, Kafka, or Pulsar. But
    asyncio.Queue provides the same semantics (bounded buffer, backpressure
    via maxsize, async get/put) without external dependencies. The pattern
    translates directly to real stream processors.

Backpressure:
    The queue has a maxsize. When the producer tries to put() into a full
    queue, it blocks until a consumer frees a slot. This is backpressure --
    the producer cannot outrun the consumer.

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
# Producer
# ---------------------------------------------------------------------------

async def producer(
    prompts: list[str],
    stream: asyncio.Queue,
):
    """Push prompts onto the stream queue one at a time.

    After all prompts are pushed, sends a None sentinel for each consumer
    to signal end-of-stream.
    """
    for i, prompt in enumerate(prompts):
        await stream.put((i, prompt))
        print(f"  [producer] enqueued prompt {i + 1}/{len(prompts)} (queue size: {stream.qsize()})")

    # Send sentinel values -- one per consumer so each consumer knows to stop
    for _ in range(NUM_CONSUMERS):
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
    """Pull prompts from the stream and process them.

    Reads from the stream queue until it receives a None sentinel.
    Results are pushed to the results_queue for collection.
    """
    # --- YOUR CODE HERE ---
    # Implement the consumer loop:
    # 1. Loop forever using `while True:`
    # 2. Get the next item from the stream using `await stream.get()`
    # 3. If the item is None, break out of the loop (end-of-stream sentinel)
    # 4. Unpack the item as (index, prompt)
    # 5. Record the start time
    # 6. Call call_inference(client, prompt)
    # 7. Calculate elapsed time in milliseconds
    # 8. Print: [consumer-{consumer_id}] processed prompt {index+1} in {elapsed}ms
    # 9. Put the result dict into results_queue:
    #    {"index": index, "prompt": prompt, "response": ..., "model": ..., "latency_ms": ...}
    # 10. Handle exceptions: put an error dict into results_queue
    # 11. After the loop, print: [consumer-{consumer_id}] shutting down
    raise NotImplementedError("Implement the consumer loop")
    # --- END YOUR CODE ---


# ---------------------------------------------------------------------------
# Results collector
# ---------------------------------------------------------------------------

async def collect_results(
    results_queue: asyncio.Queue,
    total_items: int,
) -> list[dict]:
    """Collect results from consumers until all items are accounted for."""
    results = []
    while len(results) < total_items:
        result = await results_queue.get()
        results.append(result)
    # Sort by original index to preserve order
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

    Returns:
        dict with "results" and "stats".
    """
    stream: asyncio.Queue = asyncio.Queue(maxsize=buffer_size)
    results_queue: asyncio.Queue = asyncio.Queue()

    async with httpx.AsyncClient(
        base_url=MODEL_SERVICE_URL,
        timeout=httpx.Timeout(TIMEOUT),
    ) as client:
        pipeline_start = time.perf_counter()

        # Launch producer, consumers, and collector concurrently
        producer_task = asyncio.create_task(producer(prompts, stream))

        consumer_tasks = [
            asyncio.create_task(consumer(i, stream, results_queue, client))
            for i in range(num_consumers)
        ]

        collector_task = asyncio.create_task(
            collect_results(results_queue, len(prompts))
        )

        # Wait for everything to finish
        await producer_task
        await asyncio.gather(*consumer_tasks)
        results = await collector_task

        pipeline_elapsed = time.perf_counter() - pipeline_start

    latencies = [r["latency_ms"] for r in results if "error" not in r]
    successful = len(latencies)

    stats = {
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
