"""
gRPC Client for Model Inference -- COMPLETE SOLUTION

Demonstrates both unary and server-streaming gRPC calls to the
InferenceService. Compare this with rest_client.py to see how the
two protocols differ in call patterns.

Key differences from the REST client:
    - No URL construction or HTTP verb selection
    - Method calls look like local function calls
    - Responses are typed protobuf objects, not dicts
    - Streaming is native (async for), not SSE/WebSocket

Run (with the gRPC server already running):
    python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.solution.grpc_client
"""

import asyncio
import sys
import time
from pathlib import Path

import grpc
from grpc import aio as grpc_aio

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT_DIR / "baseline" / "protos"))

# ---------------------------------------------------------------------------
# Import compiled protobuf stubs
# ---------------------------------------------------------------------------
import inference_pb2
import inference_pb2_grpc

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GRPC_SERVER_ADDRESS = "localhost:50051"


async def call_generate(stub: inference_pb2_grpc.InferenceServiceStub):
    """Send a unary Generate request and print the response.

    This is the gRPC equivalent of:
        POST /inference {"prompt": "...", "model": "..."}

    The stub.Generate() call:
    1. Serializes the request to protobuf binary
    2. Sends it over HTTP/2
    3. Receives the response as protobuf binary
    4. Deserializes it into a GenerateResponse object
    """
    print("\n--- gRPC Generate (Unary) ---")

    request = inference_pb2.GenerateRequest(
        prompt="Explain gRPC in one sentence.",
        model="llama-3.3-70b-versatile",
        max_tokens=256,
        temperature=0.7,
    )

    start = time.perf_counter()
    response = await stub.Generate(request)
    round_trip_ms = (time.perf_counter() - start) * 1000

    print(f"Response text: {response.text}")
    print(f"Model: {response.model}")
    print(
        f"Usage: prompt_tokens={response.usage.prompt_tokens}, "
        f"completion_tokens={response.usage.completion_tokens}, "
        f"total_tokens={response.usage.total_tokens}"
    )
    print(f"Server latency: {response.latency_ms}ms")
    print(f"Round-trip latency: {round_trip_ms:.2f}ms")

    return response


async def call_generate_stream(stub: inference_pb2_grpc.InferenceServiceStub):
    """Send a streaming GenerateStream request and print tokens as they arrive.

    This demonstrates gRPC server streaming. The client sends one request and
    receives a stream of GenerateChunk messages. Each chunk contains a token
    (or partial text) and a flag indicating whether it is the final chunk.

    Compare with REST streaming alternatives:
    - SSE: requires custom parsing of text/event-stream
    - WebSocket: requires connection upgrade, framing, ping/pong
    - gRPC: just "async for chunk in stream"
    """
    print("\n--- gRPC GenerateStream (Server Streaming) ---")

    request = inference_pb2.GenerateRequest(
        prompt="Explain gRPC in one sentence.",
        model="llama-3.3-70b-versatile",
        max_tokens=256,
        temperature=0.7,
    )

    start = time.perf_counter()
    token_count = 0

    async for chunk in stub.GenerateStream(request):
        if chunk.is_final:
            total_ms = (time.perf_counter() - start) * 1000
            print(f"\n[Stream complete] {token_count} chunks in {total_ms:.2f}ms")
        else:
            print(chunk.text, end="", flush=True)
            token_count += 1


async def call_generate_with_error_handling(stub: inference_pb2_grpc.InferenceServiceStub):
    """Demonstrate gRPC error handling.

    gRPC errors are delivered as RpcError exceptions with a status code
    and a detail message. This is analogous to HTTP status codes but with
    a different set of codes (OK, INVALID_ARGUMENT, INTERNAL, etc.).
    """
    print("\n--- gRPC Error Handling ---")

    # Send an empty prompt to trigger INVALID_ARGUMENT
    request = inference_pb2.GenerateRequest(
        prompt="",  # This should trigger a validation error
        model="llama-3.3-70b-versatile",
    )

    try:
        response = await stub.Generate(request)
        print(f"Response: {response.text}")
    except grpc.aio.AioRpcError as e:
        print(f"gRPC error code: {e.code()}")
        print(f"gRPC error details: {e.details()}")
        print("(This is expected -- empty prompts are rejected)")


async def main():
    """Connect to the gRPC server and run all demonstration calls."""
    print(f"Connecting to gRPC server at {GRPC_SERVER_ADDRESS}...")

    try:
        async with grpc_aio.insecure_channel(GRPC_SERVER_ADDRESS) as channel:
            stub = inference_pb2_grpc.InferenceServiceStub(channel)

            # Unary call
            await call_generate(stub)

            # Streaming call
            await call_generate_stream(stub)

            # Error handling
            await call_generate_with_error_handling(stub)

    except grpc.aio.AioRpcError as e:
        if e.code() == grpc.StatusCode.UNAVAILABLE:
            print(
                f"\nERROR: Could not connect to gRPC server at {GRPC_SERVER_ADDRESS}. "
                "Make sure the server is running:\n"
                "  python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.solution.grpc_server"
            )
        else:
            raise

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
