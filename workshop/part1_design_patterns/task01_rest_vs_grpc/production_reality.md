# Production Reality Check: REST vs gRPC

This document answers the hard questions about running REST and gRPC in production
AI systems. It covers what breaks, what fails, what experienced engineers do
differently, and what you need to monitor.

---

## What Breaks at Scale?

### gRPC-Specific Issues

**1. Load Balancer Incompatibility**

gRPC uses HTTP/2, which multiplexes many requests over a single long-lived TCP
connection. A standard L4 (TCP) load balancer sees one connection and routes all
requests to a single backend -- defeating the purpose of having multiple replicas.

*What breaks:* You deploy 10 model service replicas behind an AWS NLB. All traffic
goes to replica #1. The other 9 sit idle. Replica #1 runs out of memory.

*Fix:* Use an L7 load balancer that understands HTTP/2 frames: Envoy, Linkerd, Istio,
or gRPC's built-in client-side load balancing (xDS protocol). AWS ALB added gRPC
support, but not all cloud providers are equal.

**2. Connection Stalling**

HTTP/2 connections are long-lived. If a backend pod is terminated (during a deployment
rollout), the connection does not automatically failover. The client holds a dead
connection and keeps sending requests into the void until a timeout fires.

*What breaks:* You deploy a new version of the model service. Requests fail for 30
seconds until the gRPC client detects the dead connection and reconnects.

*Fix:* Configure keepalive pings (`grpc.keepalive_time_ms`), set connection max age
on the server (`grpc.max_connection_age_ms`), and use retry policies.

**3. Proto Versioning Conflicts**

A team changes a field type in the proto file (e.g., `int32` to `int64`). Clients
compiled with the old proto silently interpret the data incorrectly.

*What breaks:* Silent data corruption. The prompt_tokens field reads as garbage
because the client expects 4 bytes but the server sends 8.

*Fix:* Never change field types. Never reuse field numbers. Use a proto registry
(Buf, protodep) and run backward-compatibility checks in CI.

### REST-Specific Issues

**4. JSON Parsing Overhead at High Throughput**

At thousands of requests per second, JSON serialization/deserialization becomes a
measurable CPU cost. For AI systems with large response payloads (long generated text),
this adds up.

*What breaks:* Your API gateway spends 15% of CPU on JSON parsing instead of routing.

*Fix:* For internal services, switch to gRPC. For external APIs, use orjson instead
of the default JSON library (5-10x faster in Python).

**5. No Schema Enforcement**

REST with JSON has no built-in schema enforcement. A client can send `"max_tokens":
"banana"` and the server only catches it if it validates explicitly.

*What breaks:* A client sends malformed requests that pass through your API gateway
(which does not validate) and crash the model service.

*Fix:* Use Pydantic models (FastAPI does this by default) or validate at the gateway.
OpenAPI spec helps but is documentation, not enforcement.

---

## What Fails in Production?

### 1. HTTP/2 + TLS Negotiation Failures

gRPC requires HTTP/2, and HTTP/2 requires ALPN (Application-Layer Protocol
Negotiation) in the TLS handshake. Old TLS libraries, misconfigured proxies, or
corporate firewalls that downgrade to HTTP/1.1 will cause gRPC to fail silently.

*Symptom:* "Connection reset" errors in production but everything works in development.

*Diagnosis:* Check that your TLS termination proxy (Nginx, HAProxy, cloud LB) supports
HTTP/2 and ALPN. Check TLS library versions.

### 2. gRPC Deadline Propagation

gRPC has built-in deadlines (timeouts). When service A calls service B with a 5s
deadline, and B calls C, the remaining deadline should propagate to C. If it does not,
C can run for 30s while A already timed out and moved on.

*Symptom:* Wasted compute. The model service generates a full response that nobody
will read because the gateway already returned a timeout error to the user.

*Fix:* Always propagate deadlines. In Python: pass `timeout=` on every stub call.
Use interceptors to enforce maximum deadlines.

### 3. REST Connection Pool Exhaustion

Under load, a REST client (httpx, requests) opens many TCP connections. If the
connection pool is too small, requests queue up. If it is too large, you run out of
file descriptors.

*Symptom:* Increasing latency under load, then sudden "too many open files" errors.

*Fix:* Tune `httpx.AsyncClient(limits=httpx.Limits(max_connections=100))`. Monitor
connection pool utilization.

### 4. gRPC Client Library Maturity

Not all languages have equally mature gRPC implementations. Python's grpcio, while
functional, has historically had issues with async support, memory leaks in
long-running processes, and platform-specific compilation problems.

*Symptom:* Memory usage grows over days. Segfaults in the native gRPC C core.

*Fix:* Pin grpcio versions carefully. Monitor memory. Consider grpclib (pure Python
alternative) for simpler deployments.

---

## What Would a Senior Engineer Change?

### 1. Use gRPC for Internal, REST for External

"We started with REST everywhere. When we hit 500 model service calls per second, JSON
serialization was eating 20% of gateway CPU. We moved internal calls to gRPC and kept
REST for the public API. A week of migration saved us 8 machines."

### 2. Add gRPC-Gateway for Dual Protocol

Instead of maintaining separate REST and gRPC handlers, use gRPC-Gateway (or a
similar tool) to auto-generate a REST proxy from the proto definition. Write the
logic once, serve it both ways.

```
Client --REST--> gRPC-Gateway --gRPC--> Model Service
Client --gRPC--> Model Service (direct)
```

In Python, this can be done with `grpcio-gateway` or by using Envoy as a transcoding
proxy.

### 3. Proto-First API Design

Define all APIs in proto files first, even if you only expose REST. The proto file
serves as a machine-readable contract. Generate OpenAPI specs from protos. Generate
client SDKs from protos. The proto is the single source of truth.

### 4. Interceptors for Cross-Cutting Concerns

gRPC interceptors are the equivalent of middleware. Use them for:
- Request logging (method, latency, status code)
- Authentication (extract and validate tokens)
- Deadline enforcement (reject requests with insufficient remaining time)
- Metrics collection (Prometheus counters per method)

### 5. Graceful Degradation

When the gRPC model service is down, the API gateway should fall back to a cached
response or a simpler model, not return a 503. Implement circuit breakers
(e.g., with tenacity or pybreaker) on the gRPC client.

---

## What Monitoring Is Needed?

### For REST Services

| Metric | Why |
|---|---|
| Request rate by endpoint | Capacity planning |
| Latency percentiles (p50, p95, p99) | SLA tracking |
| Error rate by status code | Detect failures |
| Request/response body size | Identify large payloads |
| Connection pool utilization | Prevent exhaustion |

### For gRPC Services

| Metric | Why |
|---|---|
| Request rate by method | Capacity planning |
| Latency percentiles by method | SLA tracking |
| Error rate by gRPC status code | Detect failures (UNAVAILABLE, DEADLINE_EXCEEDED) |
| Active streams count | Detect stream leaks |
| HTTP/2 connection count | Detect connection issues |
| Proto compatibility check results | Prevent deployment of breaking changes |
| Keepalive ping success rate | Detect stale connections |

### Tools

- **Prometheus + Grafana:** Standard for metrics. py-grpc-prometheus provides
  automatic gRPC metrics.
- **Jaeger / Zipkin:** Distributed tracing across REST and gRPC calls.
- **Buf:** Proto linting and backward-compatibility checking in CI.

---

## Common Mistakes

### Mistake 1: Using gRPC for Everything

"We made our public API gRPC because it was faster. Then customers complained they
could not use curl to debug. Then our documentation team could not generate examples.
Then the mobile team needed grpc-web. We spent months building workarounds for a
problem we created."

**Lesson:** Use gRPC where it shines (internal, high-throughput, streaming). Use REST
where developer experience matters.

### Mistake 2: Ignoring Proto Evolution Rules

"We renamed a field and kept the same field number. Old clients crashed. We had to
do an emergency rollback."

**Lesson:** Proto field numbers are sacred. Add new fields, deprecate old ones, never
reuse numbers. Run `buf breaking` in CI.

### Mistake 3: Not Setting Deadlines

"Our gRPC calls had no timeout. When the model service hung, the gateway held open
thousands of connections waiting for responses that would never come. The gateway OOMed
and took down the entire platform."

**Lesson:** Always set deadlines on gRPC calls. Propagate them across service
boundaries.

### Mistake 4: TCP Load Balancing for gRPC

"We put gRPC behind an Nginx L4 proxy. One backend got all the traffic. We thought
gRPC was slower than REST. It was actually faster, but all requests were hitting one
pod."

**Lesson:** gRPC requires L7 load balancing. Use Envoy or configure Nginx with
`grpc_pass`.

---

## Interview Questions

1. **When would you choose gRPC over REST for an AI inference service?**
   Expected: Internal services, low-latency requirements, streaming token delivery,
   strict schema contracts. REST for external/public APIs.

2. **How does gRPC load balancing differ from REST load balancing?**
   Expected: HTTP/2 multiplexing means a single connection carries all requests.
   L4 load balancers see one connection. Need L7 (Envoy, client-side LB).

3. **What happens if you change a field type in a proto file?**
   Expected: Binary incompatibility. Old clients interpret bytes incorrectly.
   Silent data corruption. Never change types; add new fields instead.

4. **How would you implement token streaming for an LLM with REST vs gRPC?**
   Expected: gRPC server streaming (native). REST options: SSE (simpler but
   unidirectional), WebSocket (bidirectional but complex).

5. **Your gRPC service has increasing p99 latency after each deployment. What do you
   investigate?**
   Expected: Connection draining (old connections not closed), keepalive configuration,
   max_connection_age, graceful shutdown handling, client reconnection behavior.

6. **Design an API gateway that accepts REST from external clients and talks gRPC to
   internal services.**
   Expected: Envoy as gRPC-JSON transcoding proxy, or application-level translation
   in the gateway (parse JSON, construct protobuf, forward). Mention proto-first
   design where the proto defines both interfaces.
