# Slide Outline: Batch vs Real-Time vs Streaming Inference

**Duration:** ~30 minutes (20 min presentation + 10 min discussion)

---

## Slide 1: Title

**Batch vs Real-Time vs Streaming**
*Three ways to process data in AI systems*

Speaker notes: Every AI system must decide how it processes requests. This
choice affects latency, cost, complexity, and user experience. Today we
explore the three fundamental patterns.

---

## Slide 2: The Restaurant Analogy

| Pattern | Analogy | Key Trait |
|---------|---------|-----------|
| Real-time | Drive-thru | Instant, one at a time |
| Batch | Catering order | Efficient, delayed |
| Streaming | Conveyor belt | Continuous flow |

Speaker notes: Before diving into systems, let us build intuition. These
three patterns map to how restaurants serve food. The drive-thru optimizes
for getting one customer served fast. Catering optimizes for feeding
hundreds efficiently. A conveyor belt sushi restaurant handles a continuous
flow of demand.

---

## Slide 3: Real-Time Inference

```
Client --> API --> Model --> Response
         (one request at a time)
```

**Characteristics:**
- Latency: milliseconds to low seconds
- Throughput: low (sequential)
- Complexity: low
- Use cases: chatbots, search, autocomplete

Speaker notes: This is what most people think of first. A user sends a
request and waits. FastAPI + Groq API is a textbook example. Simple to
build, simple to reason about, but does not scale well for bulk workloads.

---

## Slide 4: Batch Inference

```
[1000 prompts] --> Batch Processor --> [1000 results]
                  (concurrent, scheduled)
```

**Characteristics:**
- Latency: minutes to hours
- Throughput: very high
- Complexity: medium
- Use cases: embeddings, retraining, evaluations

Speaker notes: When nobody is waiting for the result, batch is king. You
can saturate GPUs, use spot instances, and process millions of items
overnight. The key tool here is concurrency control -- a semaphore or
worker pool prevents overloading downstream services.

---

## Slide 5: Streaming Inference

```
Producer --> [Queue/Stream] --> Consumer(s) --> Results
            (bounded buffer)
```

**Characteristics:**
- Latency: seconds to minutes
- Throughput: high (continuous)
- Complexity: high
- Use cases: log analysis, content moderation, recommendations

Speaker notes: Streaming sits between real-time and batch. Data flows
continuously. The bounded queue provides backpressure -- if consumers
cannot keep up, the producer slows down. This prevents memory exhaustion
and cascading failures.

---

## Slide 6: Comparison Table

| Dimension | Real-Time | Batch | Streaming |
|-----------|-----------|-------|-----------|
| Latency | ms-seconds | min-hours | sec-minutes |
| Throughput | Low | Very high | High |
| Resource use | Bursty | Saturated | Steady |
| Complexity | Low | Medium | High |
| Cost/item | Highest | Lowest | Middle |
| Failure mode | Per-request retry | Restart/checkpoint | Offset replay |

Speaker notes: No pattern is universally best. The right choice depends on
your latency SLA, data volume, and operational maturity. Most production
systems use a combination of all three.

---

## Slide 7: Concurrency Control Deep Dive

```python
semaphore = asyncio.Semaphore(5)

async def process(prompt):
    async with semaphore:       # Only 5 at a time
        return await call_model(prompt)

# Launch ALL tasks; semaphore limits actual concurrency
results = await asyncio.gather(*[process(p) for p in prompts])
```

**Why not just fire all requests at once?**
- Model service has finite capacity
- API rate limits
- Memory pressure from concurrent connections

Speaker notes: The semaphore is the most important pattern in the batch
pipeline. Without it, 10,000 concurrent requests would crash the model
service. With it, only 5 run at a time -- the rest wait their turn.

---

## Slide 8: Backpressure in Streaming

```python
queue = asyncio.Queue(maxsize=5)  # Bounded!

# Producer blocks when queue is full
await queue.put(item)  # Waits if 5 items already queued

# Consumer pulls items as fast as it can
item = await queue.get()
```

**Without backpressure:** producer fills memory until OOM kill.
**With backpressure:** producer slows to match consumer speed.

Speaker notes: Backpressure is the single most important concept in
streaming systems. It is the difference between a system that degrades
gracefully and one that crashes at 2 AM.

---

## Slide 9: Real-World Architecture

```
Users --> API Gateway --> Real-time inference (chatbot)
                      --> Batch jobs (nightly embeddings)
                      --> Kafka --> Streaming consumers (moderation)
```

Most production AI platforms use ALL THREE patterns:
- Real-time for user-facing features
- Batch for background data processing
- Streaming for event-driven pipelines

Speaker notes: Do not think of these as competing patterns. Think of them
as tools in your toolbox. A mature AI platform uses all three, chosen per
feature based on latency and throughput requirements.

---

## Slide 10: When to Use Each

| Scenario | Pattern | Why |
|----------|---------|-----|
| User asks chatbot a question | Real-time | User is waiting |
| Generate embeddings for 1M docs | Batch | No urgency, maximize throughput |
| Moderate user posts as they arrive | Streaming | Continuous, near-real-time |
| Daily model evaluation | Batch | Scheduled, bulk |
| Live dashboard of sentiment | Streaming | Continuous aggregation |
| Code autocomplete in IDE | Real-time | <200ms latency needed |

---

## Slide 11: Lab Preview

In the hands-on lab you will:
1. Run the provided real-time pipeline
2. Implement a batch pipeline with semaphore concurrency
3. Implement a streaming pipeline with asyncio.Queue
4. Compare all three on the same dataset

**Key metrics to measure:** total time, avg latency, throughput

---

## Slide 12: Production Reality Check

Things that break at scale:
- Real-time: tail latency spikes under load
- Batch: single failure can stall the entire batch
- Streaming: consumer lag causes unbounded queue growth

Things to monitor:
- P50/P95/P99 latency (real-time)
- Items processed per minute (batch)
- Consumer lag and queue depth (streaming)

---

## Slide 13: Key Takeaways

1. **Real-time** = lowest latency, simplest, lowest throughput.
2. **Batch** = highest throughput, most cost-effective, highest latency.
3. **Streaming** = continuous processing, backpressure, highest complexity.
4. Most systems use a **combination** of all three.
5. **Concurrency control** (semaphore, bounded queue) is essential.

---

## Slide 14: Discussion Questions

1. Your AI product needs to process 50,000 customer support tickets per day
   and generate summaries. Which pattern would you choose? Why?

2. You have a content moderation system that must flag harmful posts within
   5 seconds. Real-time or streaming? What are the tradeoffs?

3. How would you handle a batch job that fails halfway through 100,000 items?

4. What happens to a streaming pipeline when one consumer is 10x slower
   than the others?
