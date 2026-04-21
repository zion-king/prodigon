"""
gRPC Server for Model Inference -- COMPLETE SOLUTION

Implements the InferenceService defined in inference.proto with both unary
and server-streaming RPCs. Uses the same MockGroqClient as the REST service
to ensure identical inference behavior.

Architecture:
    This server sits alongside the REST FastAPI server. In production, you would
    either run both in the same process (using concurrent servers) or as separate
    services behind a service mesh.

Run:
    python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.solution.grpc_server
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
# Import compiled protobuf stubs and baseline modules
# ---------------------------------------------------------------------------
import inference_pb2
import inference_pb2_grpc

from model_service.app.services.groq_client import MockGroqClient

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
GRPC_PORT = 50051
DEFAULT_MODEL = "llama-3.3-70b-versatile"


class InferenceServiceServicer(inference_pb2_grpc.InferenceServiceServicer):
    """Implements the gRPC InferenceService.

    This servicer wraps the same MockGroqClient used by the REST endpoint,
    ensuring identical inference behavior regardless of the transport layer.

    Why a servicer class:
        gRPC uses the "servicer" pattern where you subclass the generated base
        class and override its methods. This is analogous to FastAPI route handlers
        but with protobuf messages instead of JSON.
    """

    def __init__(self):
        self.client = MockGroqClient()

    async def Generate(self, request, context):
        """Unary RPC: receive a prompt, return a complete response.

        This mirrors the REST POST /inference endpoint. The key differences:
        - Input is a protobuf message (not JSON)
        - Output is a protobuf message (not JSON)
        - No HTTP status codes; gRPC has its own status system
        - Schema is enforced at compile time, not runtime validation

        Args:
            request: inference_pb2.GenerateRequest with prompt, model, etc.
            context: grpc.aio.ServicerContext for metadata and error handling.

        Returns:
            inference_pb2.GenerateResponse with text, model, usage, latency_ms.
        """
        # Extract fields from the protobuf request.
        # Protobuf uses default values for unset fields (empty string, 0, 0.0),
        # so we apply our own defaults when the field is at its zero value.
        prompt = request.prompt
        model = request.model or DEFAULT_MODEL
        max_tokens = request.max_tokens or 1024
        temperature = request.temperature or 0.7
        system_prompt = request.system_prompt or None

        # Validate the prompt -- gRPC uses context.abort() instead of HTTP 400
        if not prompt.strip():
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "prompt must not be empty",
            )

        # Call the inference client (same interface as REST service uses)
        start = time.perf_counter()
        result = await self.client.generate(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
        )
        total_latency_ms = (time.perf_counter() - start) * 1000

        # Build the protobuf response.
        # Note: TokenUsage is a nested message, constructed separately.
        usage = inference_pb2.TokenUsage(
            prompt_tokens=result["usage"]["prompt_tokens"],
            completion_tokens=result["usage"]["completion_tokens"],
            total_tokens=result["usage"]["total_tokens"],
        )

        return inference_pb2.GenerateResponse(
            text=result["text"],
            model=result["model"],
            usage=usage,
            latency_ms=round(total_latency_ms, 2),
        )

    async def GenerateStream(self, request, context):
        """Server streaming RPC: receive a prompt, stream tokens back.

        This is where gRPC shines over REST. Instead of collecting the full
        response and sending it at once, we stream individual tokens as they
        are generated. The client receives each token immediately.

        With REST, achieving this requires:
        - Server-Sent Events (SSE) -- works but is unidirectional and awkward
        - WebSockets -- full duplex but complex connection management
        - Chunked transfer encoding -- non-standard for APIs

        With gRPC, streaming is a first-class concept defined in the proto file.

        Args:
            request: inference_pb2.GenerateRequest
            context: grpc.aio.ServicerContext

        Yields:
            inference_pb2.GenerateChunk for each token, then a final chunk.
        """
        prompt = request.prompt
        model = request.model or DEFAULT_MODEL
        max_tokens = request.max_tokens or 1024
        temperature = request.temperature or 0.7
        system_prompt = request.system_prompt or None

        if not prompt.strip():
            await context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "prompt must not be empty",
            )

        # Stream tokens from the inference client
        async for token in self.client.generate_stream(
            prompt=prompt,
            model=model,
            max_tokens=max_tokens,
            temperature=temperature,
            system_prompt=system_prompt,
        ):
            yield inference_pb2.GenerateChunk(text=token, is_final=False)

        # Send the final marker chunk
        yield inference_pb2.GenerateChunk(text="", is_final=True)


async def serve():
    """Initialize and start the gRPC async server.

    Why async (grpc.aio):
        The synchronous gRPC server spawns a thread per request. The async server
        uses asyncio, which integrates better with async inference clients and
        can handle thousands of concurrent connections on a single thread.
    """
    server = grpc_aio.server()

    # Register our servicer with the server
    inference_pb2_grpc.add_InferenceServiceServicer_to_server(
        InferenceServiceServicer(), server
    )

    listen_address = f"[::]:{GRPC_PORT}"
    server.add_insecure_port(listen_address)

    print(f"gRPC InferenceService starting on port {GRPC_PORT}...")
    await server.start()
    print(f"gRPC server listening on {listen_address}")
    print("Press Ctrl+C to stop.")

    try:
        await server.wait_for_termination()
    except KeyboardInterrupt:
        print("\nShutting down gRPC server...")
        await server.stop(grace=5)
        print("Server stopped.")


if __name__ == "__main__":
    asyncio.run(serve())
