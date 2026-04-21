# Production Reality Check: Microservices vs Monolith

What actually breaks in real systems, and what senior engineers do about it.

---

## What Breaks at Scale with Microservices?

### Network Partitions

In production, services run on different machines. Networks fail. When Gateway
cannot reach Model Service:

- **Symptom:** Sporadic 503 errors, timeouts, or partial failures
- **Root cause:** Network partition, DNS resolution failure, or service crash
- **What we built:** Nothing -- the baseline has no retry or circuit breaker logic
- **What production needs:** Retry with exponential backoff, circuit breakers (fail fast
  after N failures instead of waiting for timeout), bulkhead pattern (isolate failures)

### Cascading Failures

When Model Service slows down (e.g., GPU overloaded):

1. Worker Service threads block waiting for inference responses
2. Worker falls behind, job queue grows
3. Gateway threads block waiting for Worker
4. All services become unresponsive
5. Total system outage from one slow component

**Fix:** Timeouts at every boundary, circuit breakers, backpressure (reject work when
overloaded rather than accepting and failing slowly).

### Distributed Debugging

A user reports: "My generation request returned an error." Which service failed?

- Gateway log shows: "502 Bad Gateway"
- Model Service log shows: nothing (the request never arrived? or the log was lost?)
- Worker Service log shows: unrelated job processing

Without a correlation ID (request trace), you cannot connect these events.

**Fix:** Distributed tracing (OpenTelemetry, Jaeger). Propagate `X-Request-ID` in every
HTTP call. Log it in every service. Use a trace aggregator to reconstruct the full path.

### Data Consistency

The monolith submits a job and reads its status from the same dictionary. In microservices:

- Gateway sends "submit job" to Worker Service
- Worker acknowledges with job_id
- Network blip occurs
- Gateway does not receive the acknowledgment
- Gateway retries -- Worker creates a SECOND job
- User now has duplicate jobs

**Fix:** Idempotency keys. The client sends a unique key with each request. The server
deduplicates based on this key. The Worker must check "have I seen this key before?"
before creating a new job.

### Deployment Coordination

You change the `GenerateRequest` schema (add a field). Which services need updating?

- If you update Model Service first, the Gateway sends requests without the new field -- OK (backward compatible)
- If you require the new field, Gateway must be updated first
- If both must change atomically, you have a **distributed monolith**

**Fix:** Backward-compatible schema changes. Add fields as optional. Never remove or rename
fields without a deprecation period. Version your APIs (`/v1/`, `/v2/`).

---

## What Breaks at Scale with Monoliths?

### Deployment Coupling

You want to fix a typo in an error message. With a monolith, you must:

1. Build the entire application
2. Run ALL tests (inference, jobs, API)
3. Deploy the entire application
4. If anything fails, roll back everything

With 50+ engineers, this means a deployment queue and coordination overhead.

### Scaling Bottlenecks

Your inference endpoint gets 100x more traffic than your job processing endpoint.
With a monolith, you scale everything 100x -- wasting resources on the idle job
processing code running in every instance.

With microservices, you run 100 Model Service instances and 1 Worker Service instance.

### Team Conflicts

Two teams work on the same monolith:
- Team A modifies the inference pipeline
- Team B modifies the job queue
- Both change `monolith.py`
- Merge conflict
- Team A's change breaks Team B's code
- Finger pointing, slow releases

### Memory and Startup

A monolith loads everything into one process. As it grows:
- Model loading takes 30 seconds at startup
- The process uses 4GB of RAM (model weights + job queue + API buffers)
- Cold starts in auto-scaling take too long
- Memory leaks in any component affect the entire process

---

## What Would a Senior Engineer Change?

### Add Circuit Breakers

```
Gateway -> [Circuit Breaker] -> Model Service
```

If Model Service fails 5 times in 10 seconds, the circuit "opens" and subsequent requests
fail immediately (no timeout wait) for 30 seconds. After 30 seconds, one request is allowed
through (half-open). If it succeeds, the circuit closes.

Libraries: `pybreaker`, `tenacity`, or a service mesh (Istio handles this at the infrastructure level).

### Add Health Check Aggregation

The Gateway should report not just its own health, but the health of all downstream services:

```json
{
  "status": "degraded",
  "services": {
    "api-gateway": {"status": "healthy", "latency_ms": 1},
    "model-service": {"status": "unhealthy", "error": "connection refused"},
    "worker-service": {"status": "healthy", "latency_ms": 3}
  }
}
```

This enables load balancers and orchestrators to make routing decisions.

### Consider the Modular Monolith

For teams of 5-15 engineers, a senior engineer might argue against microservices:

"Let's keep one deployment but enforce strict module boundaries. The Model module
cannot import from the Worker module. Communication goes through defined interfaces.
When we NEED independent scaling, we extract that module into a service."

This gives you 80% of the organizational benefits at 20% of the operational cost.

### Add Async Communication

Replace synchronous HTTP chains with an event-driven architecture where appropriate:

- Gateway publishes "GenerateRequested" event to a message queue
- Model Service subscribes, processes, publishes "GenerateCompleted"
- Gateway (or a websocket) delivers the result

This decouples services temporally -- they do not need to be running at the same time.

### Implement Graceful Degradation

When Model Service is down, instead of returning 503:

- Return a cached response if one exists
- Return a degraded response ("Service is temporarily unavailable, please retry")
- Queue the request for later processing
- Fall back to a simpler/cheaper model

---

## What Monitoring Is Needed?

### For the Monolith

| Metric | Tool | Why |
|---|---|---|
| Request latency (p50, p95, p99) | Prometheus + Grafana | Detect slowdowns |
| Error rate | Log aggregation | Detect failures |
| CPU / memory usage | System metrics | Capacity planning |
| Active connections | uvicorn metrics | Detect overload |

### For Microservices (all of the above, PLUS)

| Metric | Tool | Why |
|---|---|---|
| Inter-service latency | Distributed tracing (Jaeger) | Find slow hops |
| Service dependency map | Service mesh / tracing | Understand blast radius |
| Error budgets per service | SLO monitoring | Prioritize reliability work |
| Queue depth (Worker) | Custom metric | Detect job backlog |
| Circuit breaker state | Custom metric | Know when services are isolated |
| DNS resolution time | Infrastructure metrics | Detect service discovery issues |
| Container restart count | Kubernetes metrics | Detect crash loops |

**Rule of thumb:** Monitoring cost for microservices is roughly proportional to the number
of services squared (every service can call every other service).

---

## Common Mistakes

### 1. Distributed Monolith

Services that must be deployed together, share a database, or have synchronous circular
dependencies. You get all the complexity of microservices with none of the benefits.

**How to detect:** If changing service A requires simultaneously changing service B,
they are not independent.

### 2. Too Many Services Too Soon

Splitting into 15 services when you have 3 engineers. Each engineer now maintains 5
services, 5 CI pipelines, 5 Docker images, and 5 monitoring dashboards.

**Guideline:** One team (2-5 people) per service. If you have fewer engineers than
services, you have too many services.

### 3. Ignoring the Network

Treating HTTP calls like function calls. They are not:
- Function calls take nanoseconds; HTTP calls take milliseconds
- Function calls do not fail due to network issues
- Function calls have consistent latency; HTTP calls have variable latency

### 4. Shared Database

Two services reading from the same database table. Any schema change requires
coordinated deployments. The database becomes the coupling point.

**Fix:** Each service owns its data. If another service needs it, expose it via API.

### 5. No Timeouts

A single missing timeout on an HTTP call can block a thread forever, leading to
thread exhaustion and total service failure.

**Rule:** Every external call (HTTP, database, API) must have an explicit timeout.

---

## Interview Questions

1. **"You have a monolithic ML inference API. Traffic has grown 10x. What do you do?"**

   Good answer: First, profile to find the bottleneck. If it is inference (GPU), extract
   inference into a separate service that can scale independently. If it is I/O (database,
   network), optimize that first. Do not split into microservices unless the bottleneck
   requires independent scaling.

2. **"Your microservices system has intermittent failures. How do you debug it?"**

   Good answer: Check distributed traces to find which service is failing. Look at the
   circuit breaker state. Check inter-service latency percentiles. The issue is likely
   a timeout, a retry storm, or a cascading failure from one slow service.

3. **"When would you recommend a monolith over microservices?"**

   Good answer: Small team, early stage, unclear domain boundaries, need to iterate fast.
   The operational overhead of microservices (monitoring, deployment, debugging) is not
   justified until you have specific pain points that microservices solve.

4. **"How do you migrate from a monolith to microservices without downtime?"**

   Good answer: Strangler Fig pattern. Extract one service at a time. Run both the old
   monolith path and the new service path in parallel. Route a percentage of traffic to
   the new service. Monitor for errors. Gradually shift traffic. Remove the old code
   from the monolith once the new service is stable.

5. **"What is a distributed monolith and how do you avoid it?"**

   Good answer: Services that are tightly coupled -- they share databases, must be
   deployed together, or have synchronous circular dependencies. Avoid it by enforcing
   clear service contracts (APIs, not shared databases), allowing independent deployment,
   and preferring async communication where possible.
