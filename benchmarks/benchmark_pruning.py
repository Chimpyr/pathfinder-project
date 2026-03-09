"""
Benchmark: Graph Pruning Verification (T-ENG-03 scripted)

Scripted verification that the walking filter correctly removes
all motorway, trunk, and private-access edges from the routing graph.
Replaces the manual "Python shell" approach for reproducible testing.

Requires Flask application context.

Usage:
    docker compose exec api python -m benchmarks.benchmark_pruning
"""

import json
import os
import sys
from datetime import datetime, timezone
from collections import Counter

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app
from app.services.core.graph_builder import build_graph
from app.services.core.data_loader import OSMDataLoader
from pyrosm import OSM

# Configuration
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
BBOX = (51.42, -2.65, 51.48, -2.55)
REGION_NAME = "benchmark_pruning"

# Highway types that MUST be absent after walking filter
FORBIDDEN_HIGHWAY_TYPES = {"motorway", "motorway_link", "trunk", "trunk_link"}


def run_benchmark():
    """Execute the pruning verification benchmark."""
    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("BENCHMARK: Graph Pruning Verification (T-ENG-03)")
        print(f"BBox: {BBOX}")
        print("=" * 60)

        # Build graph with walking filter applied
        print("\n[Setup] Building graph with walking filter...")
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
            print(f"  Graph: {graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges")
        except Exception as e:
            print(f"[FAIL] Graph build failed: {e}")
            return
            
        print("\n[Setup] Measuring RAW unpruned OSM data for the bounding box...")
        try:
            import glob
            # We must use the pre-extracted osmium PBF so we don't crash from OOM loading 1.5GB england.osm.pbf
            # The Graph Builder applies a 5km buffer, changing the exact filename, so we glob it:
            extracts = glob.glob(os.path.join("app/data", "extracted_*.osm.pbf"))
            
            if not extracts:
                 print(f"[WARN] Expected pre-extracted file missing!")
                 temp_path = os.path.join("app/data", "england.osm.pbf") # high risk fallback
            else:
                 # Sort by modified time to get the one we just built
                 extracts.sort(key=os.path.getmtime, reverse=True)
                 temp_path = extracts[0]
                 print(f"[Info] Found extracted cache for raw parsing: {temp_path}")
            
            osm = OSM(temp_path)
            nodes, edges = osm.get_network(network_type="all", nodes=True)
            
            raw_highways = edges['highway'].apply(lambda x: x[0] if isinstance(x, list) else x)
            raw_highway_counts = raw_highways.value_counts().to_dict()
            print(f"  Raw OSM Data: {len(nodes):,} nodes, {len(edges):,} edges")
        except Exception as e:
            print(f"[FAIL] Raw data fetch failed: {e}")
            raw_highway_counts = {}

        # Analyse edge highway types
        print("\n[Analysis] Checking edge highway attributes...")
        highway_counts = Counter()
        forbidden_edges = []
        private_without_foot = []
        unique_segments = set()

        for u, v, k, data in graph.edges(keys=True, data=True):
            # To match Pyrosm's literal raw OSM Way count exactly,
            # we track the unique OSM parent ID. This eliminates both 
            # bi-directional double-counting AND intersection-splitting inflation.
            osmid = data.get("osmid", id(data))
            if isinstance(osmid, list):
                osmid = tuple(osmid)
            
            if osmid not in unique_segments:
                unique_segments.add(osmid)
                highway = data.get("highway", "unknown")
                if isinstance(highway, list):
                    highway = highway[0] if highway else "unknown"
                highway_counts[highway] += 1

                if highway in FORBIDDEN_HIGHWAY_TYPES:
                    forbidden_edges.append({
                        "u": u, "v": v,
                        "highway": highway,
                        "name": data.get("name", "unnamed"),
                    })

                # Check private access without foot permission
                access = data.get("access", "")
                foot = data.get("foot", "")
                if access == "private" and foot not in ("yes", "designated", "permissive"):
                    private_without_foot.append({
                        "u": u, "v": v,
                        "highway": highway,
                        "access": access,
                        "foot": foot,
                        "name": data.get("name", "unnamed"),
                    })

        # Print results
        print("\n" + "=" * 60)
        print("RESULTS")
        print("=" * 60)
        print("  Highway Type Distribution (top 15):")
        for hw_type, count in highway_counts.most_common(15):
            print(f"    {hw_type:<25} {count:>6}")
        print("-" * 60)

        motorway_pass = len(forbidden_edges) == 0
        private_pass = len(private_without_foot) == 0

        print(f"  Forbidden highway edges:   {len(forbidden_edges)}")
        if forbidden_edges:
            for fe in forbidden_edges[:5]:
                print(f"    !! {fe['highway']}: {fe['name']} ({fe['u']}→{fe['v']})")

        print(f"  Private without foot=yes:  {len(private_without_foot)}")
        if private_without_foot:
            for pe in private_without_foot[:5]:
                print(f"    !! {pe['highway']}/{pe['access']}: {pe['name']} ({pe['u']}→{pe['v']})")

        print("-" * 60)
        print(f"  No motorway/trunk edges: {'PASS ✓' if motorway_pass else 'FAIL ✗'}")
        print(f"  No private unpermitted:  {'PASS ✓' if private_pass else 'FAIL ✗'}")
        print("=" * 60)

        # Save results
        os.makedirs(RESULTS_DIR, exist_ok=True)
        output = {
            "test_id": "T-ENG-03",
            "requirement": "FR-09",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "total_edges": graph.number_of_edges(),
            "total_nodes": graph.number_of_nodes(),
            "raw_highway_distribution": raw_highway_counts,
            "pruned_highway_distribution": dict(highway_counts.most_common()),
            "highway_distribution": dict(highway_counts.most_common()), # Keep for retro-compatibility if needed
            "forbidden_edge_count": len(forbidden_edges),
            "private_unpermitted_count": len(private_without_foot),
            "forbidden_edges_sample": forbidden_edges[:10],
            "private_unpermitted_sample": private_without_foot[:10],
            "motorway_pass": motorway_pass,
            "private_pass": private_pass,
            "overall_pass": motorway_pass and private_pass,
        }
        results_path = os.path.join(RESULTS_DIR, "pruning_verification.json")
        with open(results_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    run_benchmark()
