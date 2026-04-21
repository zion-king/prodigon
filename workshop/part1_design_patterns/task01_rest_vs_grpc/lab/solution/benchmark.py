"""
REST vs gRPC Benchmark -- COMPLETE SOLUTION

Sends N identical inference requests to both the REST and gRPC servers,
measures latency for each request, and prints a comparison table with
avg, p50, p95, and p99 latencies.

Prerequisites:
    1. REST server running:   USE_MOCK=true uvicorn model_service.app.main:app --port 8001
    2. gRPC server running:   python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.solution.grpc_server

Run:
    python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.solution.benchmark
"""

import asyncio
import statistics
import sys
import time
from pathlib import Path

import httpx

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(ROOT_DIR / "baseline"))
sys.path.insert(0, str(ROOT_DIR / "baseline" / "protos"))

# ---------------------------------------------------------------------------
# gRPC imports (lazy -- benchmark can still show REST-only if gRPC unavailable)
# ---------------------------------------------------------------------------
try:
    import grpc
    from grpc import aio as grpc_aio
    import inference_pb2
    import inference_pb2_grpc
    GRPC_AVAILABLE = True
except ImportError:
    GRPC_AVAILABLE = False

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
REST_URL = "http://localhost:8001/inference"
GRPC_ADDRESS = "localhost:50051"
NUM_REQUESTS = 100
WARMUP_REQUESTS = 5

# The same payload for both protocols, ensuring a fair comparison
PROMPT = "Explain the difference between REST and gRPC in one sentence."
MODEL = "llama-3.3-70b-versatile"
MAX_TOKENS = 256
TEMPERATURE = 0.7


def percentile(data: list[float], p: float) -> float:
    """Calculate the p-th percentile of a sorted list."""
    sorted_data = sorted(data)
    k = (len(sorted_data) - 1) * (p / 100.0)
    f = int(k)
    c = f + 1
    if c >= len(sorted_data):
        return sorted_data[f]
    return sorted_data[f] + (k - f) * (sorted_data[c] - sorted_data[f])


async def benchmark_rest(num_requests: int) -> list[float]:
    """Send num_requests to the REST endpoint and return per-request latencies in ms.

    Uses a single httpx.AsyncClient for connection reuse (matching how gRPC
    reuses its HTTP/2 channel). This keeps the comparison fair.
    """
    latencies = []

    async with httpx.AsyncClient() as client:
        payload = {
            "prompt": PROMPT,
            "model": MODEL,
            "max_tokens": MAX_TOKENS,
            "temperature": TEMPERATURE,
        }

        # Warmup: establish connection, fill caches
        for _ in range(WARMUP_REQUESTS):
            await client.post(REST_URL, json=payload)

        # Benchmark
        for i in range(num_requests):
            start = time.perf_counter()
            response = await client.post(REST_URL, json=payload)
            elapsed_ms = (time.perf_counter() - start) * 1000
            response.raise_for_status()
            latencies.append(elapsed_ms)

    return latencies


async def benchmark_grpc(num_requests: int) -> list[float]:
    """Send num_requests to the gRPC server and return per-request latencies in ms.

    Uses a single channel for all requests (gRPC multiplexes over one HTTP/2
    connection by default).
    """
    if not GRPC_AVAILABLE:
        print("gRPC libraries not installed. Skipping gRPC benchmark.")
        return []

    latencies = []

    async with grpc_aio.insecure_channel(GRPC_ADDRESS) as channel:
        stub = inference_pb2_grpc.InferenceServiceStub(channel)

        request = inference_pb2.GenerateRequest(
            prompt=PROMPT,
            model=MODEL,
            max_tokens=MAX_TOKENS,
            temperature=TEMPERATURE,
        )

        # Warmup: establish HTTP/2 connection, initialize stubs
        for _ in range(WARMUP_REQUESTS):
            await stub.Generate(request)

        # Benchmark
        for i in range(num_requests):
            start = time.perf_counter()
            response = await stub.Generate(request)
            elapsed_ms = (time.perf_counter() - start) * 1000
            latencies.append(elapsed_ms)

    return latencies


def print_results(rest_latencies: list[float], grpc_latencies: list[float]):
    """Print a formatted comparison table."""
    width = 60
    print("\n" + "=" * width)
    print(f"  REST vs gRPC Benchmark Results ({NUM_REQUESTS} requests)")
    print("=" * width)

    headers = f"{'Metric':<20} {'REST':>15} {'gRPC':>15}"
    print(headers)
    print("-" * width)

    def fmt(label: str, rest_val: float, grpc_val: float):
        print(f"{label:<20} {rest_val:>12.2f} ms {grpc_val:>12.2f} ms")

    if rest_latencies and grpc_latencies:
        rest_avg = statistics.mean(rest_latencies)
        grpc_avg = statistics.mean(grpc_latencies)
        fmt("Avg latency", rest_avg, grpc_avg)

        rest_p50 = percentile(rest_latencies, 50)
        grpc_p50 = percentile(grpc_latencies, 50)
        fmt("P50 latency", rest_p50, grpc_p50)

        rest_p95 = percentile(rest_latencies, 95)
        grpc_p95 = percentile(grpc_latencies, 95)
        fmt("P95 latency", rest_p95, grpc_p95)

        rest_p99 = percentile(rest_latencies, 99)
        grpc_p99 = percentile(grpc_latencies, 99)
        fmt("P99 latency", rest_p99, grpc_p99)

        rest_total = sum(rest_latencies) / 1000
        grpc_total = sum(grpc_latencies) / 1000
        print(f"{'Total time':<20} {rest_total:>13.2f} s {grpc_total:>13.2f} s")

        print("-" * width)

        if grpc_avg > 0:
            speedup = rest_avg / grpc_avg
            print(f"gRPC speedup: {speedup:.2f}x")
        print("=" * width)

        # Interpretation
        print("\nInterpretation:")
        print("  - gRPC is faster primarily because of binary serialization (protobuf)")
        print("    and HTTP/2 multiplexing over a single connection.")
        print("  - The gap is most pronounced for small payloads and sequential requests.")
        print("  - For network-bound calls (e.g., actual LLM inference with 1s+ latency),")
        print("    the serialization overhead becomes negligible.")
        print("  - gRPC's advantage is greatest for high-throughput internal service calls.")

    elif rest_latencies:
        rest_avg = statistics.mean(rest_latencies)
        print(f"{'Avg latency':<20} {rest_avg:>12.2f} ms {'N/A':>15}")
        print("\ngRPC server not available. Start it to see the comparison.")

    elif grpc_latencies:
        grpc_avg = statistics.mean(grpc_latencies)
        print(f"{'Avg latency':<20} {'N/A':>15} {grpc_avg:>12.2f} ms")
        print("\nREST server not available. Start it to see the comparison.")


async def main():
    """Run benchmarks for both REST and gRPC servers."""
    print(f"Benchmarking REST vs gRPC ({NUM_REQUESTS} requests each)")
    print(f"Prompt: \"{PROMPT[:50]}...\"")
    print(f"Warmup: {WARMUP_REQUESTS} requests per protocol\n")

    rest_latencies = []
    grpc_latencies = []

    # Benchmark REST
    print(f"[1/2] Benchmarking REST ({REST_URL})...")
    try:
        rest_latencies = await benchmark_rest(NUM_REQUESTS)
        print(f"  Done. Avg: {statistics.mean(rest_latencies):.2f}ms")
    except httpx.ConnectError:
        print(f"  SKIP: REST server not available at {REST_URL}")
    except Exception as e:
        print(f"  ERROR: {e}")

    # Benchmark gRPC
    print(f"[2/2] Benchmarking gRPC ({GRPC_ADDRESS})...")
    try:
        grpc_latencies = await benchmark_grpc(NUM_REQUESTS)
        if grpc_latencies:
            print(f"  Done. Avg: {statistics.mean(grpc_latencies):.2f}ms")
    except Exception as e:
        if "UNAVAILABLE" in str(e) or "Connect" in str(e):
            print(f"  SKIP: gRPC server not available at {GRPC_ADDRESS}")
        else:
            print(f"  ERROR: {e}")

    # Print results
    if rest_latencies or grpc_latencies:
        print_results(rest_latencies, grpc_latencies)
    else:
        print("\nNo servers available. Start at least one:")
        print("  REST:  USE_MOCK=true uvicorn model_service.app.main:app --port 8001")
        print("  gRPC:  python -m workshop.part1_design_patterns.task01_rest_vs_grpc.lab.solution.grpc_server")


if __name__ == "__main__":
    asyncio.run(main())
