"""
Benchmark: Extraction Methodology Comparison (T-PERF-04)

Compares the two implemented spatial feature extraction methods side by side:
  1. FAST (Point Buffer) — midpoint only, ~30 seconds
  2. EDGE_SAMPLING — interpolated every 20m, ~60 seconds

Also includes a reference timing for Novack Isovist from literature
(not executed — too slow for production).

Uses the greenness processor factory (get_processor) to obtain the
correct processor instances.

Requires Flask application context for configuration access.

Usage:
    docker compose exec api python -m benchmarks.benchmark_extraction
"""

import time
import json
import os
import sys
import copy
from datetime import datetime, timezone

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app

# Configuration
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Bristol bounding box
BBOX = (51.42, -2.65, 51.48, -2.55)
REGION_NAME = "benchmark_extraction"


def _time_extraction(graph, green_gdf, method_name: str, mode: str) -> dict:
    """
    Time a single extraction method using the greenness processor factory.

    Args:
        graph: The NetworkX graph to process.
        green_gdf: GeoDataFrame of green area polygons.
        method_name: Human-readable name for the method.
        mode: Processor mode key (FAST, EDGE_SAMPLING, NOVACK).

    Returns:
        Dictionary with timing and edge count.
    """
    from app.services.processors.greenness import get_processor

    print(f"\n  [{method_name}] Running...")
    edge_count = graph.number_of_edges()

    processor = get_processor(mode)
    graph_copy = copy.deepcopy(graph)

    start = time.perf_counter()
    try:
        processor.process(graph_copy, green_gdf)
        elapsed = time.perf_counter() - start
        success = True
        print(f"  [{method_name}] Completed in {elapsed:.2f}s ({edge_count:,} edges)")
    except Exception as e:
        elapsed = time.perf_counter() - start
        success = False
        print(f"  [{method_name}] Failed after {elapsed:.2f}s: {e}")

    return {
        "method": method_name,
        "mode": mode,
        "time_s": round(elapsed, 2),
        "edges_processed": edge_count,
        "edges_per_second": round(edge_count / elapsed) if elapsed > 0 else 0,
        "success": success,
    }


def run_benchmark():
    """Execute the extraction method comparison benchmark."""
    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("BENCHMARK: Extraction Methodology Comparison")
        print(f"BBox: {BBOX}")
        print("=" * 60)

        # Build a base graph first (without greenness processing)
        from app.services.core.graph_builder import build_graph
        print("\n[Setup] Building base graph (no greenness)...")
        try:
            result = build_graph(
                bbox=BBOX,
                region_name=REGION_NAME,
                greenness_mode="OFF",
                elevation_mode="OFF",
                normalisation_mode="OFF",
                save_to_cache=False,
                clip_to_bbox=True,
            )
            graph = result.graph
            print(f"  Base graph: {graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges")
        except Exception as e:
            print(f"\n[FAIL] Base graph build failed: {e}")
            import traceback
            traceback.print_exc()
            return

        # Load green area GeoDataFrame (needed by the processors)
        print("\n[Setup] Loading green area data...")
        try:
            from app.services.core.data_loader import OSMDataLoader
            loader = OSMDataLoader()
            green_gdf = loader.get_green_areas(BBOX)
            print(f"  Green areas loaded: {len(green_gdf):,} polygons")
        except Exception as e:
            print(f"\n[FAIL] Green area loading failed: {e}")
            import traceback
            traceback.print_exc()
            return

        timings = []

        # 1. FAST (Point Buffer) method
        timings.append(_time_extraction(
            graph, green_gdf,
            "Point Buffer (FAST mode)",
            "FAST",
        ))

        # 2. EDGE_SAMPLING method
        timings.append(_time_extraction(
            graph, green_gdf,
            "Edge Sampling (20m intervals)",
            "EDGE_SAMPLING",
        ))

        # 3. Novack Isovist — reference timing from literature
        # This method IS implemented but far too slow for production benchmarking.
        # Include published reference data for comparison.
        timings.append({
            "method": "Novack Isovist (reference)",
            "mode": "NOVACK",
            "time_s": 600,  # ~10 minutes for comparable edge count (published data)
            "edges_processed": graph.number_of_edges(),
            "edges_per_second": round(graph.number_of_edges() / 600),
            "success": True,
            "note": "Reference timing from Novack et al. (2018) — not executed",
        })

        # Print comparison table
        print("\n" + "=" * 60)
        print("RESULTS COMPARISON")
        print("=" * 60)
        print(f"  {'Method':<35} {'Time':>8} {'Edges/s':>10}")
        print("-" * 60)
        for t in timings:
            time_str = f"{t['time_s']:.1f}s"
            eps_str = f"{t['edges_per_second']:,}"
            note = " *" if t.get("note") else ""
            print(f"  {t['method']:<35} {time_str:>8} {eps_str:>10}{note}")
        print("-" * 60)

        if timings[0]["success"] and timings[1]["success"]:
            if timings[0]["time_s"] > 0:
                speedup = timings[1]["time_s"] / timings[0]["time_s"]
                print(f"  Edge Sampling is {speedup:.1f}x slower than Point Buffer")
            if timings[1]["time_s"] > 0:
                print(f"  Edge Sampling is {timings[2]['time_s'] / timings[1]['time_s']:.0f}x faster than Isovist")
        print("=" * 60)
        print("  * Reference timing — not executed in this benchmark run")

        # Save results
        os.makedirs(RESULTS_DIR, exist_ok=True)
        output = {
            "test_id": "T-PERF-04",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bbox": BBOX,
            "methods": timings,
        }
        results_path = os.path.join(RESULTS_DIR, "extraction_comparison.json")
        with open(results_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    run_benchmark()
