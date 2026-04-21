# Lab: Implement a gRPC Server for Model Inference

## Problem Statement

The baseline Model Service exposes inference via a REST endpoint (`POST /inference`).
Your task is to implement a **gRPC server** that provides the same functionality using
the proto definition at `baseline/protos/inference.proto`.

By the end of this lab, you will have both REST and gRPC interfaces serving inference
and will benchmark their relative performance.

---

## Prerequisites

- Python 3.11+
- The baseline codebase running (or at least importable)
- Basic familiarity with FastAPI and async Python

---

## Setup

### Step 1: Install gRPC Dependencies

```bash
pip install grpcio grpcio-tools
```

### Step 2: Compile the Proto File

From the repository root:

```bash
cd baseline/protos

python -m grpc_tools.protoc \
    -I. \
    --python_out=. \
    --grpc_python_out=. \
    inference.proto
```

This generates two files:
- `inference_pb2.py` -- Message classes (GenerateRequest, GenerateResponse, etc.)
- `inference_pb2_grpc.py` -- Server and client stubs (InferenceServiceServicer, InferenceServiceStub)

Verify they were created:

```bash
ls inference_pb2*.py
```

### Step 3: Understand the Proto Definition

Open `baseline/protos/inference.proto` and study:
- `InferenceService` defines two RPCs: `Generate` (unary) and `GenerateStream` (server streaming)
- `GenerateRequest` has fields: prompt, model, max_tokens, temperature, system_prompt
- `GenerateResponse` has fields: text, model, usage (TokenUsage), latency_ms
- `GenerateChunk` is used for streaming: text + is_final flag

---

## Tasks

### Task 1: Implement the gRPC Server (30 min)

Open `lab/starter/grpc_server.py`. You will see the boilerplate is provided:
- Imports and server setup code
- The `InferenceServiceServicer` class skeleton

**Your job:** Implement the two methods:

1. **`Generate`** -- Unary RPC
   - Extract fields from the protobuf request
   - Call `MockGroqClient.generate()` to get a response
   - Build and return a `GenerateResponse` protobuf message

2. **`GenerateStream`** -- Server Streaming RPC
   - Extract fields from the protobuf request
   - Call `MockGroqClient.generate_stream()` to get an async iterator
   - Yield `GenerateChunk` messages for each token
   - Yield a final chunk with `is_final=True`

**Run your server:**

```bash
# From the repository root
python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.starter.grpc_server
```

### Task 2: Implement the gRPC Client (15 min)

Open `lab/starter/grpc_client.py`. Implement:

1. **`call_generate`** -- Send a unary Generate request
2. **`call_generate_stream`** -- Send a streaming request and print tokens as they arrive

**Test your client:**

```bash
# In another terminal (server must be running)
python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.starter.grpc_client
```

### Task 3: Compare REST and gRPC (10 min)

1. Start the Model Service REST server:

```bash
# From the repository root
USE_MOCK=true uvicorn model_service.app.main:app --port 8001
```

2. Start your gRPC server (from Task 1)

3. Run the REST client to verify it works:

```bash
python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.starter.rest_client
```

4. Run your gRPC client (from Task 2)

5. Compare the output formats and response shapes.

### Task 4: Run the Benchmark (10 min)

Use the provided benchmark script (or the solution version):

```bash
python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.solution.benchmark
```

**Expected output:** A table showing gRPC is approximately 2-5x faster than REST for
local calls, primarily due to:
- Binary serialization (protobuf) vs text (JSON)
- HTTP/2 multiplexing vs HTTP/1.1 sequential requests
- No JSON parse/serialize overhead

Note: The performance gap is most pronounced for small payloads and high request
rates. For large payloads or network-bound calls, the difference narrows.

---

## Expected Output

### gRPC Unary Call

```
--- gRPC Generate ---
Response text: [Mock response for model=llama-3.3-70b-versatile] ...
Model: llama-3.3-70b-versatile-mock
Usage: prompt_tokens=6, completion_tokens=20, total_tokens=26
Latency: 5.0ms
```

### gRPC Streaming Call

```
--- gRPC GenerateStream ---
[Mock stream for llama-3.3-70b-versatile] Simulated response to: Explain gRPC in one
```

### Benchmark Output

```
============================================================
  REST vs gRPC Benchmark Results (100 requests)
============================================================
Metric              REST            gRPC
------------------------------------------------------------
Avg latency         12.45 ms        3.21 ms
P50 latency         11.89 ms        2.98 ms
P95 latency         18.23 ms        5.12 ms
P99 latency         24.67 ms        6.89 ms
Total time          1.28 s          0.34 s
------------------------------------------------------------
gRPC speedup: 3.76x
============================================================
```

*(Exact numbers will vary by machine.)*

---

## Bonus Challenges

### Bonus 1: Add Error Handling to gRPC
Implement proper gRPC error codes:
- `INVALID_ARGUMENT` for empty prompts
- `INTERNAL` for inference failures

Use `context.abort()` or `context.set_code()`/`context.set_details()`.

### Bonus 2: Implement a Deadline/Timeout
Add a 5-second deadline to the gRPC client call. Observe what happens when the
server takes longer (simulate with `asyncio.sleep`).

### Bonus 3: Add Reflection
Enable gRPC server reflection so clients can discover available services at runtime:

```bash
pip install grpcio-reflection
```

This lets tools like `grpcurl` introspect your service without the proto file.

### Bonus 4: Bidirectional Streaming
Extend the proto with a new RPC:
```protobuf
rpc Chat (stream GenerateRequest) returns (stream GenerateChunk);
```
Implement a chat-like interface where the client streams prompts and the server
streams responses.
