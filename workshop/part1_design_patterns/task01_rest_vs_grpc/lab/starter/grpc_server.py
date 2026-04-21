"""
gRPC Server for Model Inference -- STARTER CODE

This server implements the InferenceService defined in inference.proto.
It mirrors the functionality of the REST /inference endpoint.

Your task: Implement the Generate and GenerateStream methods in the servicer class.

Run:
    python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.starter.grpc_server
"""

import asyncio
import sys
import time
from pathlib import Path

import grpc
from grpc import aio as grpc_aio

# ---------------------------------------------------------------------------
# Path setup: ensure the baseline modules are importable
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[5]  # prod-ai-system-design/
sys.path.insert(0, str(ROOT_DIR / "baseline"))
sys.path.insert(0, str(ROOT_DIR / "baseline" / "protos"))

# ---------------------------------------------------------------------------
# Import the compiled protobuf stubs
# Make sure you compiled inference.proto first (see lab README, Step 2)
# ---------------------------------------------------------------------------
import inference_pb2
import inference_pb2_grpc

# Import the mock client so we can run without a Groq API key
from model_service.app.services.groq_client import MockGroqClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GRPC_PORT = 50051
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class InferenceServiceServicer(inference_pb2_grpc.InferenceServiceServicer):
    """Implements the gRPC InferenceService.

    This servicer uses a MockGroqClient (same as the REST service in mock mode)
    to handle inference requests.
    """

    def __init__(self):
        self.client = MockGroqClient()

    async def Generate(self, request, context):
        """Unary RPC: receive a prompt, return a complete response.

        Steps:
            1. Extract prompt, model, max_tokens, temperature, system_prompt from request
            2. Call self.client.generate(...) to get a result dict
            3. Build and return a GenerateResponse protobuf message

        Args:
            request: inference_pb2.GenerateRequest
            context: grpc.aio.ServicerContext

        Returns:
            inference_pb2.GenerateResponse
        """
        # ---- YOUR CODE HERE ----
        # Hint: Extract fields from the request protobuf message.
        #   prompt = request.prompt
        #   model = request.model or DEFAULT_MODEL
        #   max_tokens = request.max_tokens or 1024
        #   temperature = request.temperature or 0.7
        #   system_prompt = request.system_prompt or None
        #
        # Hint: Call the client (it's async):
        #   result = await self.client.generate(prompt=..., model=..., ...)
        #
        # Hint: Build the response. Note that TokenUsage is a nested message:
        #   usage = inference_pb2.TokenUsage(
        #       prompt_tokens=result["usage"]["prompt_tokens"],
        #       ...
        #   )
        #   return inference_pb2.GenerateResponse(text=..., model=..., usage=usage, latency_ms=...)
        #
        pass  # Remove this line when you add your implementation
        # ---- END YOUR CODE ----

    async def GenerateStream(self, request, context):
        """Server streaming RPC: receive a prompt, stream tokens back.

        Steps:
            1. Extract fields from the request (same as Generate)
            2. Call self.client.generate_stream(...) to get an async iterator
            3. For each token, yield a GenerateChunk message
            4. After all tokens, yield a final chunk with is_final=True

        Args:
            request: inference_pb2.GenerateRequest
            context: grpc.aio.ServicerContext

        Yields:
            inference_pb2.GenerateChunk
        """
        # ---- YOUR CODE HERE ----
        # Hint: Extract fields the same way as Generate above.
        #
        # Hint: Iterate over the async stream:
        #   async for token in self.client.generate_stream(prompt=..., model=...):
        #       yield inference_pb2.GenerateChunk(text=token, is_final=False)
        #
        # Hint: After the loop, yield the final chunk:
        #   yield inference_pb2.GenerateChunk(text="", is_final=True)
        #
        pass  # Remove this line when you add your implementation
        # ---- END YOUR CODE ----


async def serve():
    """Start the gRPC server on the configured port."""
    server = grpc_aio.server()
    inference_pb2_grpc.add_InferenceServiceServicer_to_server(
        InferenceServiceServicer(), server
    )
    listen_address = f"[::]:{GRPC_PORT}"
    server.add_insecure_port(listen_address)

    print(f"gRPC server starting on port {GRPC_PORT}...")
    await server.start()
    print(f"gRPC server listening on {listen_address}")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        print("Shutting down gRPC server...")
        await server.stop(grace=5)


if __name__ == "__main__":
    asyncio.run(serve())
