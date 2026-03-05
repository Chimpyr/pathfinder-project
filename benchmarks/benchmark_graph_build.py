"""
Benchmark: Graph Build Timing (T-PERF-02 / NFR-02)

Triggers a full graph build for the Bristol test region and measures
total wall-clock time plus per-stage timings.

Requires Flask application context for database and configuration access.

Pass criteria: total build time <= 120s for ~325,000 edges

Usage:
    docker compose exec api python -m benchmarks.benchmark_graph_build
"""

import time
import json
import os
import sys
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app
from app.services.core.graph_builder import build_graph

# Configuration
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Bristol bounding box (standard test region)
BBOX = (51.42, -2.65, 51.48, -2.55)
REGION_NAME = "benchmark_bristol"

# Pass/fail threshold
MAX_BUILD_TIME_S = 120
MIN_EXPECTED_EDGES = 200_000


def run_benchmark():
    """Execute the graph build benchmark within a Flask app context."""
    # Create Flask application context so config and logging are available
    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("BENCHMARK: Graph Build Timing (T-PERF-02)")
        print(f"Target: total build <= {MAX_BUILD_TIME_S}s")
        print(f"Region: {REGION_NAME}")
        print(f"BBox: {BBOX}")
        print("=" * 60)

        print("\n[Benchmark] Starting full graph build...")
        start_time = time.perf_counter()

        try:
            result = build_graph(
                bbox=BBOX,
                region_name=REGION_NAME,
                greenness_mode="EDGE_SAMPLING",
                elevation_mode="LOCAL",
                normalisation_mode="STATIC",
                save_to_cache=False,  # Don't pollute cache with benchmark data
                clip_to_bbox=True,
            )
        except Exception as e:
            print(f"\n[FAIL] Graph build failed: {e}")
            import traceback
            traceback.print_exc()
            return

        total_time = time.perf_counter() - start_time

        # Print results
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print(f"  Total Build Time:  {total_time:.2f}s")
        print(f"  Node Count:        {result.node_count:,}")
        print(f"  Edge Count:        {result.edge_count:,}")
        print(f"  PBF Source:        {result.pbf_path}")
        print("-" * 60)
        print("  Per-Stage Timings:")
        for stage, duration in result.timings.items():
            if stage != "TOTAL":
                pct = (duration / total_time) * 100 if total_time > 0 else 0
                print(f"    {stage}: {duration:.2f}s ({pct:.1f}%)")
        print("-" * 60)

        # Pass/fail
        time_pass = total_time <= MAX_BUILD_TIME_S
        edge_pass = result.edge_count >= MIN_EXPECTED_EDGES
        print(f"  Build <= {MAX_BUILD_TIME_S}s:     {'PASS ✓' if time_pass else 'FAIL ✗'} ({total_time:.1f}s)")
        print(f"  Edges >= {MIN_EXPECTED_EDGES:,}:  {'PASS ✓' if edge_pass else 'FAIL ✗'} ({result.edge_count:,})")
        print("=" * 60)

        # Save results to JSON
        os.makedirs(RESULTS_DIR, exist_ok=True)
        results = {
            "test_id": "T-PERF-02",
            "requirement": "NFR-02",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_build_time_s": round(total_time, 2),
            "node_count": result.node_count,
            "edge_count": result.edge_count,
            "pbf_path": result.pbf_path,
            "timings": {k: round(v, 2) for k, v in result.timings.items()},
            "time_pass": time_pass,
            "edge_pass": edge_pass,
            "overall_pass": time_pass and edge_pass,
        }
        results_path = os.path.join(RESULTS_DIR, "graph_build.json")
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    run_benchmark()
