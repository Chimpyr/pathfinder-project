"""
Benchmark: Extraction Methodology Comparison (T-PERF-04)

Compares the three implemented spatial feature extraction methods side by side:
  1. FAST (Point Buffer) — midpoint only
  2. EDGE_SAMPLING — interpolated every 20m
  3. NOVACK (Isovist ray-casting) — executed on a random sample of edges;
     full-graph time is extrapolated. Ray-casting on the full
     Bristol graph (~130k edges) takes ~190 minutes in pure Python;
     sampling 2,000 representative edges and extrapolating is the
     standard benchmarking technique for sub-linear runtimes.

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

# Number of randomly sampled edges used to time NOVACK.
# Full-graph time is extrapolated from this sample.
# At ~0.066 s/edge (measured), 2,000 edges ≈ 130 s of sampling.
NOVACK_SAMPLE_EDGES = 2000


def _time_extraction(graph, green_gdf, method_name: str, mode: str,
                     buildings_gdf=None, novack_sample_edges: int = 0) -> dict:
    """
    Time a single extraction method using the greenness processor factory.

    Args:
        graph: The NetworkX graph to process.
        green_gdf: GeoDataFrame of green area polygons.
        method_name: Human-readable name for the method.
        mode: Processor mode key (FAST, EDGE_SAMPLING, NOVACK).
        buildings_gdf: Building footprints (required for NOVACK mode only).
        novack_sample_edges: If > 0 and mode is NOVACK, time only this many
            randomly selected edges and extrapolate to the full graph count.

    Returns:
        Dictionary with timing and edge count (extrapolated for NOVACK sample).
    """
    from app.services.processors.greenness import get_processor

    print(f"\n  [{method_name}] Running...")
    full_edge_count = graph.number_of_edges()
    processor = get_processor(mode)
    graph_copy = copy.deepcopy(graph)

    # For NOVACK: subsample to make timing tractable, then extrapolate
    sampled = False
    sample_size = full_edge_count
    if mode == 'NOVACK' and novack_sample_edges > 0 and full_edge_count > novack_sample_edges:
        import random
        all_edges = list(graph_copy.edges(keys=True))
        edges_to_remove = random.sample(all_edges, full_edge_count - novack_sample_edges)
        graph_copy.remove_edges_from([(u, v, k) for u, v, k in edges_to_remove])
        sample_size = graph_copy.number_of_edges()
        sampled = True
        print(f"    Sampled {sample_size:,} / {full_edge_count:,} edges for timed run.")
        print(f"    Full-graph time will be extrapolated from this sample.")

    start = time.perf_counter()
    try:
        if mode == 'NOVACK':
            processor.process(graph_copy, green_gdf, buildings_gdf=buildings_gdf)
        else:
            processor.process(graph_copy, green_gdf)
        elapsed = time.perf_counter() - start
        success = True
        print(f"  [{method_name}] Sample completed in {elapsed:.2f}s ({sample_size:,} edges)")
    except Exception as e:
        elapsed = time.perf_counter() - start
        success = False
        print(f"  [{method_name}] Failed after {elapsed:.2f}s: {e}")
        import traceback
        traceback.print_exc()

    # Extrapolate to full graph if sampled
    if sampled and elapsed > 0 and success:
        extrapolated_time = elapsed * (full_edge_count / sample_size)
        print(f"  [{method_name}] Extrapolated full-graph time: {extrapolated_time:.0f}s "
              f"({extrapolated_time/60:.1f} min)")
    else:
        extrapolated_time = elapsed

    return {
        "method": method_name,
        "mode": mode,
        "time_s": round(extrapolated_time, 2),
        "sampled_time_s": round(elapsed, 2) if sampled else None,
        "sample_edges": sample_size if sampled else None,
        "edges_processed": full_edge_count,
        "edges_per_second": round(sample_size / elapsed) if elapsed > 0 else 0,
        "extrapolated": sampled,
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

        # Build a base graph using OSMDataLoader directly so we retain the
        # loader instance (needed to call extract_buildings() for NOVACK).
        # build_graph() discards its loader internally — using it here would
        # mean we have no way to call loader.extract_buildings() afterwards.
        from app.services.core.data_loader import OSMDataLoader
        import geopandas as gpd

        print("\n[Setup] Loading base graph via OSMDataLoader (no greenness)...")
        try:
            loader = OSMDataLoader()
            loader.ensure_data_for_bbox(BBOX)
            graph = loader.load_graph(bbox=BBOX, clip_bbox=BBOX)
            print(f"  Base graph: {graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges")
        except Exception as e:
            print(f"\n[FAIL] Base graph build failed: {e}")
            import traceback
            traceback.print_exc()
            return

        # Extract green area polygons from graph.features (already in memory).
        print("\n[Setup] Loading green area data from graph features...")
        try:
            features = getattr(graph, 'features', None)
            if features is None or features.empty:
                print("\n[FAIL] graph.features is empty — cannot extract green areas.")
                return

            green_gdf = features[features['feature_group'] == 'green'].copy()
            green_gdf = green_gdf[green_gdf.geometry.notna()]
            green_gdf = green_gdf[
                green_gdf.geometry.geom_type.isin(['Polygon', 'MultiPolygon'])
            ]

            # Project to metres (UTM zone 30N) — same CRS the greenness
            # processor expects from OSMDataLoader.extract_green_areas().
            if green_gdf.crs is None:
                green_gdf = green_gdf.set_crs('EPSG:4326')
            green_gdf = green_gdf.to_crs('EPSG:32630')

            print(f"  Green areas loaded: {len(green_gdf):,} polygons")
        except Exception as e:
            print(f"\n[FAIL] Green area loading failed: {e}")
            import traceback
            traceback.print_exc()
            return

        # Extract building polygons for NOVACK isovist occlusion.
        # loader._active_pbf_path is set to the osmium-clipped PBF after
        # load_graph(), so extract_buildings() reads the correct small file.
        print("\n[Setup] Extracting building footprints (required for NOVACK)...")
        try:
            buildings_gdf = loader.extract_buildings()
            if buildings_gdf is None or buildings_gdf.empty:
                print("  [WARN] No buildings found — NOVACK will use open-circle isovists.")
                buildings_gdf = gpd.GeoDataFrame()
            else:
                print(f"  Building polygons loaded: {len(buildings_gdf):,}")
        except Exception as e:
            print(f"  [WARN] Building extraction failed ({e}) — NOVACK will run without occlusion.")
            buildings_gdf = gpd.GeoDataFrame()

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

        # 3. Novack Isovist — executed on a random sample, full-graph time extrapolated
        print(f"\n  [Novack Isovist] Sampling {NOVACK_SAMPLE_EDGES:,} edges from {graph.number_of_edges():,}.")
        print("  Full-graph time will be extrapolated (pure-Python ray-casting is")
        print("  ~0.066 s/edge on this geometry — ~190 min for the full graph).")
        timings.append(_time_extraction(
            graph, green_gdf,
            "Novack Isovist (ray-casting)",
            "NOVACK",
            buildings_gdf=buildings_gdf,
            novack_sample_edges=NOVACK_SAMPLE_EDGES,
        ))

        # Print comparison table
        print("\n" + "=" * 60)
        print("RESULTS COMPARISON")
        print("=" * 60)
        print(f"  {'Method':<35} {'Time':>8} {'Edges/s':>10}")
        print("-" * 60)
        for t in timings:
            time_str = f"{t['time_s']:.1f}s"
            eps_str = f"{t['edges_per_second']:,}"
            extrap = " (extrapolated)" if t.get("extrapolated") else ""
            print(f"  {t['method']:<35} {time_str:>8} {eps_str:>10}{extrap}")
        print("-" * 60)

        if timings[0]["success"] and timings[1]["success"]:
            if timings[0]["time_s"] > 0:
                speedup = timings[1]["time_s"] / timings[0]["time_s"]
                print(f"  Edge Sampling is {speedup:.1f}x slower than Point Buffer")
        if timings[1]["success"] and timings[2]["success"] and timings[1]["time_s"] > 0:
            ratio = timings[2]["time_s"] / timings[1]["time_s"]
            print(f"  Novack Isovist (extrapolated) is {ratio:.0f}x slower than Edge Sampling")
        print("=" * 60)
        print(f"  * Novack timed on {NOVACK_SAMPLE_EDGES:,} sampled edges; full-graph time extrapolated.")

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
