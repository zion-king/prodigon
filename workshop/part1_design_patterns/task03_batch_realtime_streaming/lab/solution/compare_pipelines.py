"""
Pipeline Comparison Script.

Runs all three inference pipelines (real-time, batch, streaming) on the same
dataset and prints a side-by-side comparison of their performance.

This script imports the pipeline functions from the solution modules and
executes them sequentially so the model service is not overwhelmed by
running multiple pipelines simultaneously.

Usage:
    python compare_pipelines.py

Environment variables:
    MODEL_SERVICE_URL       Base URL (default: http://localhost:8001)
    BATCH_CONCURRENCY       Batch concurrency limit (default: 5)
    STREAM_CONSUMERS        Streaming consumer count (default: 3)
    STREAM_BUFFER_SIZE      Streaming queue buffer (default: 5)
"""

import asyncio
import json
import os
import sys
from pathlib import Path

# Ensure the solution directory is importable
sys.path.insert(0, str(Path(__file__).parent))

from realtime_pipeline import realtime_pipeline  # noqa: E402
from batch_pipeline import batch_pipeline  # noqa: E402
from streaming_pipeline import streaming_pipeline  # noqa: E402

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

PROMPTS_FILE = Path(__file__).parent.parent / "starter" / "sample_prompts.json"
BATCH_CONCURRENCY = int(os.getenv("BATCH_CONCURRENCY", "5"))
STREAM_CONSUMERS = int(os.getenv("STREAM_CONSUMERS", "3"))
STREAM_BUFFER_SIZE = int(os.getenv("STREAM_BUFFER_SIZE", "5"))


# ---------------------------------------------------------------------------
# Comparison runner
# ---------------------------------------------------------------------------

async def run_comparison():
    """Run all three pipelines and collect their stats."""

    # Load the shared dataset
    with open(PROMPTS_FILE) as f:
        prompts = json.load(f)

    print("=" * 65)
    print(f"  Pipeline Comparison: {len(prompts)} prompts")
    print("=" * 65)

    all_stats = []

    # --- 1. Real-time pipeline ---
    print("\n[1/3] Running Real-Time Pipeline...")
    print("-" * 60)
    rt_output = await realtime_pipeline(prompts)
    all_stats.append(rt_output["stats"])
    print()

    # --- 2. Batch pipeline ---
    print(f"\n[2/3] Running Batch Pipeline (concurrency={BATCH_CONCURRENCY})...")
    print("-" * 60)
    batch_output = await batch_pipeline(prompts, concurrency=BATCH_CONCURRENCY)
    all_stats.append(batch_output["stats"])
    print()

    # --- 3. Streaming pipeline ---
    print(f"\n[3/3] Running Streaming Pipeline "
          f"(consumers={STREAM_CONSUMERS}, buffer={STREAM_BUFFER_SIZE})...")
    print("-" * 60)
    stream_output = await streaming_pipeline(
        prompts,
        num_consumers=STREAM_CONSUMERS,
        buffer_size=STREAM_BUFFER_SIZE,
    )
    all_stats.append(stream_output["stats"])
    print()

    return all_stats


# ---------------------------------------------------------------------------
# Results table
# ---------------------------------------------------------------------------

def print_comparison_table(all_stats: list[dict]):
    """Print a formatted comparison table."""

    print()
    print("=" * 65)
    print("  PIPELINE COMPARISON RESULTS")
    print("=" * 65)
    print()

    # Table header
    header = f"{'Pipeline':<22} {'Total Time':>12} {'Avg Latency':>14} {'Throughput':>14}"
    units  = f"{'':<22} {'(seconds)':>12} {'(ms/item)':>14} {'(items/sec)':>14}"
    print(header)
    print(units)
    print("-" * 65)

    for stats in all_stats:
        pipeline_name = stats.get("pipeline", "unknown")

        # Add configuration details to the name
        if pipeline_name == "batch":
            pipeline_name = f"Batch (c={stats.get('concurrency', '?')})"
        elif pipeline_name == "streaming":
            pipeline_name = f"Streaming (c={stats.get('num_consumers', '?')})"
        elif pipeline_name == "realtime":
            pipeline_name = "Real-time"

        row = (
            f"{pipeline_name:<22} "
            f"{stats['total_time_s']:>12.2f} "
            f"{stats['avg_latency_ms']:>14.1f} "
            f"{stats['throughput_items_per_s']:>14.2f}"
        )
        print(row)

    print("-" * 65)

    # Determine winners
    fastest = min(all_stats, key=lambda s: s["total_time_s"])
    highest_throughput = max(all_stats, key=lambda s: s["throughput_items_per_s"])
    lowest_avg_latency = min(all_stats, key=lambda s: s["avg_latency_ms"])

    print()
    print(f"  Fastest overall:      {fastest['pipeline']}")
    print(f"  Best throughput:      {highest_throughput['pipeline']}")
    print(f"  Lowest avg latency:   {lowest_avg_latency['pipeline']}")
    print()

    # Speedup calculations
    rt_time = next(s["total_time_s"] for s in all_stats if s["pipeline"] == "realtime")
    for stats in all_stats:
        if stats["pipeline"] != "realtime" and rt_time > 0:
            speedup = rt_time / stats["total_time_s"]
            print(f"  {stats['pipeline']} speedup vs real-time: {speedup:.1f}x")

    print()


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------

def print_analysis():
    """Print teaching notes about the results."""
    print("=" * 65)
    print("  ANALYSIS")
    print("=" * 65)
    print("""
  What you should observe:

  1. REAL-TIME is the slowest overall because it processes prompts
     sequentially. Total time = sum of all individual latencies.
     But it has the simplest implementation and gives you the first
     result fastest.

  2. BATCH is typically the fastest because it runs multiple requests
     concurrently. With concurrency=5, it can process ~5 prompts in
     the time real-time processes 1. The semaphore prevents overload.

  3. STREAMING falls between the two. It has concurrent consumers
     (like batch) but adds overhead from the queue and producer/consumer
     coordination. The bounded queue demonstrates backpressure.

  Key insight:
     The "best" pipeline depends on your requirements:
     - Need instant responses?     --> Real-time
     - Need maximum throughput?    --> Batch
     - Need continuous processing? --> Streaming
""")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    all_stats = await run_comparison()
    print_comparison_table(all_stats)
    print_analysis()


if __name__ == "__main__":
    asyncio.run(main())
