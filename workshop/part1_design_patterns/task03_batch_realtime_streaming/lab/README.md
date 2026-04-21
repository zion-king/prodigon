# Lab: Batch vs Real-Time vs Streaming Inference

## Problem Statement

You have a Model Service that exposes `POST /inference` for text generation.
Your task is to build **three client-side pipelines** that process a set of
prompts using this endpoint in three different ways, then compare their
performance characteristics.

## Prerequisites

- The baseline Model Service running on `http://localhost:8001`
  (or set `MODEL_SERVICE_URL` env var).
- Set `USE_MOCK=true` if you do not have a Groq API key (the model service
  will return deterministic mock responses).
- Python 3.11+ with `httpx` installed (`pip install httpx`).

### Starting the Model Service

From the project root:

```bash
# Option 1: With Groq API key
GROQ_API_KEY=your-key-here python -m uvicorn baseline.model_service.app.main:app --port 8001

# Option 2: Mock mode (no API key needed)
USE_MOCK=true python -m uvicorn baseline.model_service.app.main:app --port 8001
```

---

## Lab Steps

### Step 1: Understand the Real-Time Pipeline (provided)

Open `starter/realtime_pipeline.py`. This file is **complete** and serves as
your reference for how to call the inference endpoint.

Run it:
```bash
python starter/realtime_pipeline.py
```

Observe:
- Each prompt is sent one at a time.
- Total time is the sum of all individual latencies.
- Low complexity but poor throughput for large datasets.

---

### Step 2: Implement the Batch Pipeline

Open `starter/batch_pipeline.py`. The file structure is ready but the core
processing loop is marked with `# --- YOUR CODE HERE ---`.

Your task:
1. Read prompts from `sample_prompts.json`.
2. Process all prompts concurrently using `asyncio.Semaphore` to limit
   concurrency (e.g., 5 at a time).
3. Collect results and write them to an output JSON file.
4. Print timing statistics.

Hints:
- Use `asyncio.gather()` to run concurrent tasks.
- The semaphore prevents overwhelming the model service.
- Track individual latencies for per-item stats.

Run your solution:
```bash
python starter/batch_pipeline.py
```

---

### Step 3: Implement the Streaming Pipeline

Open `starter/streaming_pipeline.py`. The producer and result collection are
provided. The consumer logic is marked with `# --- YOUR CODE HERE ---`.

Your task:
1. Implement the consumer that reads prompts from the `asyncio.Queue`.
2. Call the inference endpoint for each prompt.
3. Put results into the results queue.
4. Handle the sentinel value (`None`) to know when to stop.

Hints:
- Use `queue.get()` to read from the stream.
- A `None` sentinel signals end-of-stream.
- Put results into the results queue as they complete.

Run your solution:
```bash
python starter/streaming_pipeline.py
```

---

### Step 4: Compare All Three Pipelines

After implementing all three, run the comparison script:

```bash
python solution/compare_pipelines.py
```

This script runs all three pipelines on the same dataset and prints a
comparison table showing:
- Total execution time
- Average latency per item
- Throughput (items per second)

---

## Expected Output

```
=== Pipeline Comparison Results ===

Pipeline          Total Time   Avg Latency   Throughput
                  (seconds)    (ms/item)     (items/sec)
---------------------------------------------------------
Real-time         12.45        830.0          0.80
Batch (c=5)        3.12        208.0          3.21
Streaming (c=3)    4.67        311.3          2.14

Winner (throughput): Batch
Winner (latency):   Real-time (first result fastest)
```

*Exact numbers depend on your machine and whether you use mock mode.*

---

## Bonus Challenges

1. **Adaptive concurrency:** Modify the batch pipeline to dynamically adjust
   the semaphore size based on error rates (reduce concurrency on errors,
   increase on success streaks).

2. **Priority streaming:** Add a priority field to prompts. Modify the
   streaming pipeline to use `asyncio.PriorityQueue` so high-priority
   prompts are processed first.

3. **Checkpointing:** Add checkpoint logic to the batch pipeline so that
   if it crashes halfway, it can resume from the last completed prompt
   instead of restarting.

4. **Backpressure visualization:** Log the queue depth at each consumer
   iteration in the streaming pipeline. Plot the queue depth over time
   to visualize backpressure behavior.

5. **Rate limiting:** Add a token-bucket rate limiter to the batch pipeline
   that limits requests to N per second, simulating API rate limits.
