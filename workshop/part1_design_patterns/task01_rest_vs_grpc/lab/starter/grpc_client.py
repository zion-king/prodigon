"""
gRPC Client for Model Inference -- STARTER CODE

This client connects to the gRPC InferenceService and makes both unary
and streaming calls.

Your task: Implement the call_generate and call_generate_stream functions.

Run (with the gRPC server already running):
    python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.starter.grpc_client
"""

import asyncio
import sys
from pathlib import Path

import grpc
from grpc import aio as grpc_aio

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT_DIR / "baseline" / "protos"))

# ---------------------------------------------------------------------------
# Import the compiled protobuf stubs
# ---------------------------------------------------------------------------
import inference_pb2
import inference_pb2_grpc

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
GRPC_SERVER_ADDRESS = "localhost:50051"


async def call_generate(stub: inference_pb2_grpc.InferenceServiceStub):
    """Send a unary Generate request and print the response.

    Steps:
        1. Create a GenerateRequest protobuf message
        2. Call stub.Generate(request) -- this is an async call
        3. Print the response fields

    Args:
        stub: The gRPC client stub for InferenceService
    """
    print("\n--- gRPC Generate (Unary) ---")

    # ---- YOUR CODE HERE ----
    # Hint: Create the request:
    #   request = inference_pb2.GenerateRequest(
    #       prompt="Explain gRPC in one sentence.",
    #       model="llama-3.3-70b-versatile",
    #       max_tokens=256,
    #       temperature=0.7,
    #   )
    #
    # Hint: Make the call (it's async):
    #   response = await stub.Generate(request)
    #
    # Hint: Print the response:
    #   print(f"Response text: {response.text}")
    #   print(f"Model: {response.model}")
    #   print(f"Usage: prompt_tokens={response.usage.prompt_tokens}, ...")
    #   print(f"Latency: {response.latency_ms}ms")
    #
    pass  # Remove this line when you add your implementation
    # ---- END YOUR CODE ----


async def call_generate_stream(stub: inference_pb2_grpc.InferenceServiceStub):
    """Send a streaming GenerateStream request and print tokens as they arrive.

    Steps:
        1. Create a GenerateRequest protobuf message
        2. Call stub.GenerateStream(request) to get an async iterator
        3. Iterate over chunks and print each token

    Args:
        stub: The gRPC client stub for InferenceService
    """
    print("\n--- gRPC GenerateStream (Server Streaming) ---")

    # ---- YOUR CODE HERE ----
    # Hint: Create the request (same as above, different prompt if you like):
    #   request = inference_pb2.GenerateRequest(
    #       prompt="Explain gRPC in one sentence.",
    #       model="llama-3.3-70b-versatile",
    #       max_tokens=256,
    #       temperature=0.7,
    #   )
    #
    # Hint: Iterate over the stream:
    #   async for chunk in stub.GenerateStream(request):
    #       if chunk.is_final:
    #           print("\n[Stream complete]")
    #       else:
    #           print(chunk.text, end="", flush=True)
    #
    pass  # Remove this line when you add your implementation
    # ---- END YOUR CODE ----


async def main():
    """Connect to the gRPC server and run both call types."""
    print(f"Connecting to gRPC server at {GRPC_SERVER_ADDRESS}...")

    async with grpc_aio.insecure_channel(GRPC_SERVER_ADDRESS) as channel:
        stub = inference_pb2_grpc.InferenceServiceStub(channel)

        # Run unary call
        await call_generate(stub)

        # Run streaming call
        await call_generate_stream(stub)

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(main())
