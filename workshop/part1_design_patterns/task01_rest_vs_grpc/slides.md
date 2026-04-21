# Slide Deck: REST vs gRPC for AI Systems

**Duration:** ~30 minutes
**Audience:** Backend engineers building AI/ML services

---

## Slide 1: Title

**REST vs gRPC: Choosing the Right Protocol for AI Inference**

- Two dominant approaches to API design
- Different tradeoffs for different use cases
- The answer is usually "both"

---

## Slide 2: Agenda

1. What is REST? What is gRPC?
2. Side-by-side comparison
3. How each works under the hood
4. When to use which
5. The hybrid pattern
6. Live demo and benchmark
7. Production considerations

---

## Slide 3: REST -- The Universal API

- **R**epresentational **S**tate **T**ransfer
- Built on HTTP/1.1 (or HTTP/2)
- JSON as the default serialization format
- Resource-oriented: `GET /users/123`, `POST /inference`
- Universal: works in browsers, curl, Postman, any language
- Schema is optional (OpenAPI/Swagger for documentation)

**Key point:** REST is the lingua franca of web APIs.

---

## Slide 4: gRPC -- The Performance Protocol

- **g**oogle **R**emote **P**rocedure **C**all
- Built on HTTP/2 (mandatory)
- Protocol Buffers (protobuf) for binary serialization
- Method-oriented: `service.Generate(request)`
- Code generation: `.proto` file compiles to client + server stubs
- Schema is mandatory and enforced at compile time

**Key point:** gRPC trades universal accessibility for performance and type safety.

---

## Slide 5: Head-to-Head Comparison

| Dimension | REST | gRPC |
|---|---|---|
| Protocol | HTTP/1.1 | HTTP/2 |
| Serialization | JSON (text) | Protobuf (binary) |
| Schema | Optional | Required |
| Streaming | Workarounds | Native |
| Browser support | Native | Requires proxy |
| Debugging | Easy (curl) | Harder (grpcurl) |
| Payload size | Larger | ~3-10x smaller |
| Latency | Higher | Lower |

---

## Slide 6: Under the Hood -- REST

```
POST /inference HTTP/1.1
Host: model-service:8001
Content-Type: application/json

{
  "prompt": "Explain gRPC",
  "model": "llama-3.3-70b-versatile",
  "max_tokens": 256
}
```

- Human-readable on the wire
- Self-describing (field names in every request)
- Parsed at runtime (validation is opt-in)

---

## Slide 7: Under the Hood -- gRPC

```protobuf
service InferenceService {
    rpc Generate (GenerateRequest) returns (GenerateResponse);
}
```

```
[binary frame: 48 bytes]
field 1 (string): "Explain gRPC"
field 2 (string): "llama-3.3-70b-versatile"
field 3 (varint): 256
```

- Binary on the wire (not human-readable)
- Field numbers instead of names (smaller)
- Schema enforced at compile time
- HTTP/2 frames with multiplexing

---

## Slide 8: The Four gRPC Streaming Modes

1. **Unary:** Client sends one message, server sends one response (like REST)
2. **Server streaming:** Client sends one, server sends many (token streaming)
3. **Client streaming:** Client sends many, server sends one (batch upload)
4. **Bidirectional streaming:** Both sides send streams (real-time chat)

**For AI systems:** Server streaming is the killer feature. Stream tokens as they are
generated instead of waiting for the full response.

---

## Slide 9: Streaming -- REST vs gRPC

**REST streaming options:**
- Server-Sent Events (SSE): One-directional, text-only, connection held open
- WebSocket: Bidirectional but complex (connection upgrade, framing, heartbeats)
- Chunked transfer: Non-standard for APIs

**gRPC streaming:**
- Defined in the proto: `returns (stream GenerateChunk)`
- Client code: `async for chunk in stub.GenerateStream(request)`
- Built-in flow control, backpressure, and cancellation

---

## Slide 10: When to Use REST

- Public-facing APIs (customers, partners, browsers)
- CRUD operations and simple request-response
- Rapid prototyping and developer onboarding
- Webhooks and third-party integrations
- When human debuggability matters

**Examples:** OpenAI API, Stripe, GitHub API

---

## Slide 11: When to Use gRPC

- Internal service-to-service communication
- High-throughput, low-latency paths
- Token-by-token streaming from LLMs
- Polyglot environments (Go, Java, Python, Rust)
- When you need strict contracts between teams

**Examples:** Google (internal), Netflix (backend), Uber (microservices)

---

## Slide 12: The Hybrid Pattern

```
Browser/Mobile  --REST-->  API Gateway  --gRPC-->  Model Service
External APIs   --REST-->  API Gateway  --gRPC-->  Worker Service
                                        --gRPC-->  Feature Store
```

- REST for external (universal, debuggable, familiar)
- gRPC for internal (fast, typed, streaming)
- API Gateway translates between them
- This is how Google, Netflix, and Uber do it

---

## Slide 13: Live Demo

1. Start the REST Model Service
2. Start the gRPC Model Service
3. Send the same request to both
4. Compare response formats
5. Run the benchmark

---

## Slide 14: Benchmark Results

```
Metric              REST            gRPC
Avg latency         12.45 ms        3.21 ms
P50 latency         11.89 ms        2.98 ms
P95 latency         18.23 ms        5.12 ms
P99 latency         24.67 ms        6.89 ms
gRPC speedup: 3.76x
```

- gRPC wins on raw latency for local calls
- The gap narrows when network latency dominates
- For actual LLM inference (1s+ per call), transport overhead is noise
- Biggest impact: high-throughput internal services (thousands of calls/sec)

---

## Slide 15: Production Gotchas

- **Load balancing:** gRPC needs L7 (Envoy, Istio), not L4
- **Debugging:** Cannot use browser dev tools or curl easily
- **Proto versioning:** Never reuse field numbers; use a proto registry
- **TLS:** gRPC strongly expects TLS; plan for certificate management
- **Client libraries:** Not all languages have mature gRPC support
- **Connection management:** Long-lived HTTP/2 connections can stall

---

## Slide 16: Key Takeaways

1. REST and gRPC are not competitors -- they solve different problems
2. Use REST for external APIs, gRPC for internal services
3. gRPC streaming is a natural fit for token-by-token LLM output
4. The performance gap matters most for high-throughput internal calls
5. Always benchmark with your actual workload, not synthetic tests

---

## Slide 17: Exercise

**Hands-on lab:** Implement a gRPC server that mirrors the REST /inference endpoint

- 30 minutes
- Starter code provided
- Compile the proto, implement the servicer, test with the client
- Bonus: Add streaming, error handling, deadlines

---

## Slide 18: Discussion Questions

1. If your AI service only has 10 requests per second, does gRPC matter?
2. How would you expose gRPC to browser clients? (Hint: grpc-web, Envoy)
3. What happens when you need to add a field to GenerateRequest?
4. How do you monitor gRPC services differently from REST?
5. When would you choose WebSocket over gRPC streaming?
