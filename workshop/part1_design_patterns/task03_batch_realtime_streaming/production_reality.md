# Production Reality Check: Batch vs Real-Time vs Streaming

## What Breaks at Scale

### Real-Time

| Problem | Cause | Impact |
|---------|-------|--------|
| Tail latency spikes | Garbage collection, cold model loads, network jitter | P99 latency jumps from 500ms to 5s; user sees spinner |
| Thundering herd | All users hit the endpoint at once (e.g., after an outage) | Model service overwhelmed, cascading timeouts |
| Memory pressure | Each request holds model context in memory | OOM kills under high concurrency |
| Cold start | Serverless or auto-scaled instances need to load the model | First request takes 30s instead of 500ms |

**Mitigation:** Rate limiting, request queuing, model warm-up, circuit breakers,
auto-scaling with warm pools.

### Batch

| Problem | Cause | Impact |
|---------|-------|--------|
| Poison pill | One malformed input crashes the processor | Entire batch stalls or restarts from zero |
| No checkpointing | System crashes at item 9,500 of 10,000 | Re-process all 10,000 items |
| Resource starvation | Batch job monopolizes GPU/CPU | Real-time endpoints become unresponsive |
| Stale results | Batch runs once per day | Users see data that is up to 24 hours old |
| Silent failures | One item fails but the batch "completes" | Missing results go undetected |

**Mitigation:** Checkpointing (write progress every N items), dead-letter queues
for failed items, resource quotas, separate compute pools for batch vs real-time.

### Streaming

| Problem | Cause | Impact |
|---------|-------|--------|
| Consumer lag | Consumers slower than producers | Queue grows without bound, memory exhaustion |
| Exactly-once is hard | Network failures cause re-deliveries | Duplicate processing, duplicate results |
| Ordering violations | Multiple consumers process out of order | Results arrive in wrong sequence |
| Rebalancing storms | Consumer joins/leaves trigger partition reassignment | Processing pauses for seconds |
| Schema evolution | Producer changes message format | Consumers fail to deserialize |

**Mitigation:** Bounded queues with backpressure, idempotent consumers, offset
tracking, consumer group management, schema registries.

---

## What Would a Senior Engineer Change

### Real-Time Pipeline

1. **Add circuit breakers.** If the model service is down, fail fast instead
   of timing out for 60 seconds per request. Use a library like `tenacity`
   with exponential backoff.

2. **Add response caching.** Identical prompts should return cached results.
   Even a 5-minute TTL cache eliminates redundant inference calls.

3. **Add request coalescing.** If 10 users send the same prompt within 100ms,
   deduplicate to a single inference call and share the result.

4. **Separate read and write paths.** Health checks and inference should not
   compete for the same thread pool.

### Batch Pipeline

1. **Add checkpointing.** Write progress to disk every N items. On restart,
   skip already-completed items.

2. **Add a dead-letter queue.** Failed items go to a separate queue for
   manual review instead of blocking the batch.

3. **Add adaptive concurrency.** Start with concurrency=2. If latency is
   low and error rate is zero, increase to 5, then 10. If errors spike,
   reduce. This adapts to downstream capacity automatically.

4. **Run on separate compute.** Batch jobs should not run on the same
   instances as real-time inference. Use dedicated worker nodes or spot
   instances.

### Streaming Pipeline

1. **Use a real message broker.** asyncio.Queue is single-process. For
   production, use Redis Streams, Kafka, or Pulsar for durability and
   multi-process/multi-node consumption.

2. **Add offset tracking.** Record the last successfully processed offset.
   On restart, resume from that offset instead of re-processing everything.

3. **Add consumer health checks.** If a consumer is stuck (no progress for
   N seconds), kill and restart it.

4. **Add metrics per consumer.** Track items/sec, error rate, and processing
   latency per consumer to identify slow consumers.

---

## Monitoring Requirements

### Real-Time

| Metric | What to Track | Alert Threshold |
|--------|---------------|-----------------|
| Request latency | P50, P95, P99 | P99 > 3x P50 |
| Error rate | 4xx and 5xx per minute | > 1% of requests |
| Throughput | Requests per second | Drop > 50% from baseline |
| Model service health | Health check success rate | Any failure |
| Connection pool | Active/idle connections | > 80% capacity |

### Batch

| Metric | What to Track | Alert Threshold |
|--------|---------------|-----------------|
| Items processed | Count per minute | < expected rate |
| Failure rate | Failed items / total items | > 0.1% |
| Batch duration | Wall-clock time | > 2x expected |
| Checkpoint progress | Last checkpoint timestamp | Stale > 5 minutes |
| Resource usage | CPU, memory, GPU utilization | > 90% sustained |

### Streaming

| Metric | What to Track | Alert Threshold |
|--------|---------------|-----------------|
| Consumer lag | Queue depth / unprocessed messages | > 1000 messages |
| Processing rate | Items/sec per consumer | Drop > 50% |
| End-to-end latency | Time from produce to result | > SLA threshold |
| Consumer health | Heartbeat / liveness | Missing heartbeat |
| Backpressure events | Producer block count per minute | > 10/min |

---

## Common Mistakes

1. **Using real-time for everything.** Engineers default to synchronous
   request-response because it is familiar. But processing 100K items
   via real-time endpoints is 100x slower and more expensive than batch.

2. **No concurrency limit on batch.** Firing 10,000 concurrent requests
   crashes the model service. Always use a semaphore or worker pool.

3. **Unbounded queues in streaming.** "It works in dev" because the
   queue never fills up with 10 test items. In production with 10M items,
   memory exhaustion is guaranteed.

4. **Ignoring partial failures in batch.** A batch of 10,000 items where
   50 fail silently means 50 missing results that nobody notices until
   a customer complains.

5. **Over-engineering early.** Starting with Kafka for a system that
   processes 100 items/day. asyncio.Queue or Redis is sufficient until
   you hit thousands of items/second.

6. **Not measuring.** Teams choose batch or streaming based on intuition
   instead of benchmarking. Always measure with realistic data volumes.

---

## Interview-Style Questions

### Conceptual

1. **Q:** Explain the difference between batch, real-time, and streaming
   processing. When would you use each?

   **A:** Real-time processes one item at a time with minimal latency
   (chatbots, search). Batch processes many items together for maximum
   throughput (embeddings, retraining). Streaming processes a continuous
   flow of items with bounded latency (log analysis, moderation).
   Most production systems combine all three.

2. **Q:** What is backpressure and why does it matter in streaming systems?

   **A:** Backpressure is a mechanism that slows producers when consumers
   cannot keep up. Without it, the queue grows until memory is exhausted.
   Bounded buffers (e.g., `asyncio.Queue(maxsize=N)`) provide natural
   backpressure by blocking the producer when the buffer is full.

3. **Q:** How would you handle failures in a batch processing pipeline?

   **A:** Implement checkpointing (save progress every N items), use a
   dead-letter queue for failed items, make processing idempotent so
   retries are safe, and add monitoring to detect stalled batches.

### System Design

4. **Q:** Design a system that processes 1 million product descriptions
   to generate embeddings for a search index. What pattern would you
   use and how would you architect it?

   **A:** Batch processing with checkpointing. Split the 1M items into
   chunks of 1,000. Use a semaphore-controlled async pipeline with
   concurrency of 20-50 (tuned to the embedding API's rate limits).
   Write checkpoints after each chunk. Use a dead-letter queue for
   failures. Schedule as a nightly job with monitoring on items/sec
   and failure rate.

5. **Q:** You have a content moderation system that must process user
   posts within 10 seconds of creation. Posts arrive at 500/second
   during peak. Design the system.

   **A:** Streaming with Kafka or Redis Streams. Posts are published
   to a topic when created. A consumer group with 10+ consumers
   reads from partitions. Each consumer calls the moderation model.
   Bounded queue on the consumer side provides backpressure. Monitor
   consumer lag to ensure the 10-second SLA. Add auto-scaling based
   on lag metrics.

### Debugging

6. **Q:** Your batch job processed 100,000 items but the output file
   only has 99,847 results. How do you investigate?

   **A:** First, check the logs for errors during processing. Look for
   HTTP 429 (rate limited), 500 (server error), or timeout errors.
   Check if the semaphore was too aggressive (too much concurrency).
   Compare the input list against the output to find which items are
   missing. Check if any items had malformed input that caused silent
   failures. Add item-level tracking and a dead-letter queue to
   prevent this in the future.
