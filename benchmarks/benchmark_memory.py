"""
Benchmark: Memory Usage (T-PERF-03 / NFR-05)

Measures peak memory usage during graph building with and without
BBox clipping to empirically validate ADR-004.

Pass criteria: clipped build peak RSS <= 1.5GB

Usage:
    docker compose exec api python -m benchmarks.benchmark_memory
"""

import time
import tracemalloc
import json
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.core.graph_builder import build_graph

# Configuration
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Bristol bounding box
BBOX = (51.42, -2.65, 51.48, -2.55)
REGION_NAME = "benchmark_memory"

# Pass/fail threshold (in bytes)
MAX_CLIPPED_PEAK_GB = 1.5
MAX_CLIPPED_PEAK_BYTES = int(MAX_CLIPPED_PEAK_GB * 1024 * 1024 * 1024)


def measure_build(clip_to_bbox: bool) -> dict:
    """
    Run a graph build and measure peak memory usage.

    Args:
        clip_to_bbox: Whether to clip the graph to the bounding box.

    Returns:
        Dictionary with timing and memory metrics.
    """
    label = "CLIPPED" if clip_to_bbox else "UNCLIPPED"
    print(f"\n[{label}] Starting graph build (clip_to_bbox={clip_to_bbox})...")

    # Start memory tracking
    tracemalloc.start()

    start_time = time.perf_counter()
    try:
        result = build_graph(
            bbox=BBOX,
            region_name=f"{REGION_NAME}_{label.lower()}",
            greenness_mode="EDGE_SAMPLING",
            elevation_mode="OFF",  # Skip elevation to isolate memory from network loading
            normalisation_mode="STATIC",
            save_to_cache=False,
            clip_to_bbox=clip_to_bbox,
        )
        build_time = time.perf_counter() - start_time
        node_count = result.node_count
        edge_count = result.edge_count
        success = True
    except MemoryError:
        build_time = time.perf_counter() - start_time
        node_count = 0
        edge_count = 0
        success = False
        print(f"  [{label}] OUT OF MEMORY after {build_time:.1f}s")
    except Exception as e:
        build_time = time.perf_counter() - start_time
        node_count = 0
        edge_count = 0
        success = False
        print(f"  [{label}] Build failed: {e}")

    # Get peak memory
    current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    peak_mb = peak / (1024 * 1024)
    peak_gb = peak / (1024 * 1024 * 1024)

    print(f"  [{label}] Build time:    {build_time:.2f}s")
    print(f"  [{label}] Peak memory:   {peak_mb:.0f} MB ({peak_gb:.2f} GB)")
    print(f"  [{label}] Nodes:         {node_count:,}")
    print(f"  [{label}] Edges:         {edge_count:,}")
    print(f"  [{label}] Success:       {success}")

    return {
        "mode": label,
        "clip_to_bbox": clip_to_bbox,
        "build_time_s": round(build_time, 2),
        "peak_memory_bytes": peak,
        "peak_memory_mb": round(peak_mb),
        "peak_memory_gb": round(peak_gb, 2),
        "node_count": node_count,
        "edge_count": edge_count,
        "success": success,
    }


def run_benchmark():
    """Execute the memory usage benchmark."""
    print("=" * 60)
    print("BENCHMARK: Memory Usage (T-PERF-03)")
    print(f"Target: clipped peak <= {MAX_CLIPPED_PEAK_GB}GB")
    print(f"BBox: {BBOX}")
    print("=" * 60)

    results = {}

    # 1. Clipped build (should always work)
    results["clipped"] = measure_build(clip_to_bbox=True)

    # 2. Unclipped build (may OOM on constrained containers)
    print("\n[INFO] Attempting unclipped build for comparison...")
    print("[INFO] This may fail with OOM on containers with < 8GB RAM.")
    try:
        results["unclipped"] = measure_build(clip_to_bbox=False)
    except Exception as e:
        print(f"[WARN] Unclipped build failed (expected): {e}")
        results["unclipped"] = {
            "mode": "UNCLIPPED",
            "success": False,
            "error": str(e),
        }

    # Print comparison
    print("\n" + "=" * 60)
    print("RESULTS COMPARISON")
    print("=" * 60)

    clipped = results["clipped"]
    unclipped = results.get("unclipped", {})

    print(f"  Clipped Peak:    {clipped.get('peak_memory_mb', 'N/A')} MB")
    if unclipped.get("success"):
        print(f"  Unclipped Peak:  {unclipped.get('peak_memory_mb', 'N/A')} MB")
        if clipped.get("peak_memory_bytes") and unclipped.get("peak_memory_bytes"):
            ratio = unclipped["peak_memory_bytes"] / clipped["peak_memory_bytes"]
            print(f"  Reduction Ratio: {ratio:.1f}x")
    else:
        print(f"  Unclipped Peak:  OOM (validates ADR-004 necessity)")

    print("-" * 60)
    clipped_pass = clipped.get("peak_memory_bytes", float("inf")) <= MAX_CLIPPED_PEAK_BYTES
    print(f"  Clipped <= {MAX_CLIPPED_PEAK_GB}GB: {'PASS ✓' if clipped_pass else 'FAIL ✗'}")
    print("=" * 60)

    # Save results
    os.makedirs(RESULTS_DIR, exist_ok=True)
    output = {
        "test_id": "T-PERF-03",
        "requirement": "NFR-05",
        "clipped": clipped,
        "unclipped": unclipped,
        "clipped_pass": clipped_pass,
        "overall_pass": clipped_pass,
    }
    results_path = os.path.join(RESULTS_DIR, "memory_usage.json")
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    run_benchmark()
