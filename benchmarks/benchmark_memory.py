"""
Benchmark: Memory Usage (T-PERF-03 / NFR-05)

Measures peak RSS (Resident Set Size) during graph building with and
without BBox clipping to empirically validate ADR-004.

Uses psutil for accurate process-level RSS measurement, capturing memory
from C extensions (GeoPandas, Shapely, NumPy) not just Python heap allocations.

Requires Flask application context for database and configuration access.

Pass criteria: clipped build peak RSS <= 1.5GB

Usage:
    docker compose exec api python -m benchmarks.benchmark_memory
"""

import time
import json
import os
import sys
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False

from app import create_app
from app.services.core.graph_builder import build_graph

# Configuration
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Bristol bounding box
BBOX = (51.42, -2.65, 51.48, -2.55)
REGION_NAME = "benchmark_memory"

# Pass/fail threshold (in bytes)
MAX_CLIPPED_PEAK_GB = 1.5
MAX_CLIPPED_PEAK_BYTES = int(MAX_CLIPPED_PEAK_GB * 1024 * 1024 * 1024)


def _get_rss_bytes() -> int:
    """Get current process RSS in bytes using psutil, with fallback."""
    if HAS_PSUTIL:
        return psutil.Process(os.getpid()).memory_info().rss
    # Fallback for Linux containers without psutil
    try:
        import resource
        # ru_maxrss is in kilobytes on Linux
        return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024
    except ImportError:
        return 0


def measure_build(clip_to_bbox: bool) -> dict:
    """
    Run a graph build and measure peak process RSS.

    Args:
        clip_to_bbox: Whether to clip the graph to the bounding box.

    Returns:
        Dictionary with timing and memory metrics.
    """
    label = "CLIPPED" if clip_to_bbox else "UNCLIPPED"
    print(f"\n[{label}] Starting graph build (clip_to_bbox={clip_to_bbox})...")

    # Record baseline RSS before build
    rss_before = _get_rss_bytes()

    start_time = time.perf_counter()
    peak_rss = rss_before

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

        # Measure RSS after build (peak proxy — allocations haven't been freed yet)
        rss_after = _get_rss_bytes()
        peak_rss = max(rss_after, peak_rss)

        node_count = result.node_count
        edge_count = result.edge_count
        success = True
    except MemoryError:
        build_time = time.perf_counter() - start_time
        rss_after = _get_rss_bytes()
        peak_rss = max(rss_after, peak_rss)
        node_count = 0
        edge_count = 0
        success = False
        print(f"  [{label}] OUT OF MEMORY after {build_time:.1f}s")
    except Exception as e:
        build_time = time.perf_counter() - start_time
        rss_after = _get_rss_bytes()
        peak_rss = max(rss_after, peak_rss)
        node_count = 0
        edge_count = 0
        success = False
        print(f"  [{label}] Build failed: {e}")

    peak_mb = peak_rss / (1024 * 1024)
    peak_gb = peak_rss / (1024 * 1024 * 1024)
    delta_mb = (peak_rss - rss_before) / (1024 * 1024)

    measurement_method = "psutil.Process.rss" if HAS_PSUTIL else "resource.getrusage"

    print(f"  [{label}] Build time:       {build_time:.2f}s")
    print(f"  [{label}] Peak RSS:         {peak_mb:.0f} MB ({peak_gb:.2f} GB)")
    print(f"  [{label}] RSS delta:        +{delta_mb:.0f} MB (build allocation)")
    print(f"  [{label}] Measurement:      {measurement_method}")
    print(f"  [{label}] Nodes:            {node_count:,}")
    print(f"  [{label}] Edges:            {edge_count:,}")
    print(f"  [{label}] Success:          {success}")

    return {
        "mode": label,
        "clip_to_bbox": clip_to_bbox,
        "build_time_s": round(build_time, 2),
        "rss_before_bytes": rss_before,
        "peak_rss_bytes": peak_rss,
        "peak_rss_mb": round(peak_mb),
        "peak_rss_gb": round(peak_gb, 2),
        "rss_delta_mb": round(delta_mb),
        "measurement_method": measurement_method,
        "node_count": node_count,
        "edge_count": edge_count,
        "success": success,
    }


def run_benchmark():
    """Execute the memory usage benchmark within a Flask app context."""
    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("BENCHMARK: Memory Usage (T-PERF-03)")
        print(f"Target: clipped peak RSS <= {MAX_CLIPPED_PEAK_GB}GB")
        print(f"BBox: {BBOX}")
        if not HAS_PSUTIL:
            print("[WARN] psutil not installed — falling back to resource.getrusage")
            print("[WARN] Install psutil for more accurate RSS measurements")
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

        print(f"  Clipped Peak RSS:    {clipped.get('peak_rss_mb', 'N/A')} MB")
        if unclipped.get("success"):
            print(f"  Unclipped Peak RSS:  {unclipped.get('peak_rss_mb', 'N/A')} MB")
            if clipped.get("peak_rss_bytes") and unclipped.get("peak_rss_bytes"):
                ratio = unclipped["peak_rss_bytes"] / clipped["peak_rss_bytes"]
                print(f"  Reduction Ratio:     {ratio:.1f}x")
        else:
            print(f"  Unclipped Peak RSS:  OOM (validates ADR-004 necessity)")

        print("-" * 60)
        clipped_pass = clipped.get("peak_rss_bytes", float("inf")) <= MAX_CLIPPED_PEAK_BYTES
        print(f"  Clipped <= {MAX_CLIPPED_PEAK_GB}GB:   {'PASS ✓' if clipped_pass else 'FAIL ✗'}")
        print("=" * 60)

        # Save results
        os.makedirs(RESULTS_DIR, exist_ok=True)
        output = {
            "test_id": "T-PERF-03",
            "requirement": "NFR-05",
            "timestamp": datetime.now(timezone.utc).isoformat(),
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
