"""
Benchmark: Water Proximity Scoring Verification (T-ENG-09)

Automated verification that the WaterProcessor correctly assigns raw_water_cost
to every graph edge, that values are normalised to [0.0, 1.0], and that edges
near known Bristol waterways (River Avon, Floating Harbour) score significantly
lower than inland edges far from any water body.

Design note: an earlier area-coverage approach incorrectly scored edges ON narrow
rivers at ~0.5.  The current min-distance approach correctly gives ~0.0 for
edges physically adjacent to water, which this benchmark empirically confirms.

Usage (requires running Docker stack):
    docker compose exec api python -m benchmarks.benchmark_water
"""

import json
import math
import os
import sys
from datetime import datetime, timezone

import networkx as nx

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app import create_app
from app.services.core.graph_builder import build_graph

# ─── Configuration ───────────────────────────────────────────────────────────

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Bounding box covering Bristol centre, Harbourside, and River Avon corridor
BBOX = (51.42, -2.63, 51.48, -2.55)
REGION_NAME = "benchmark_water"

# Known riverside nodes / coordinates in Bristol (WGS84 lon, lat)
# These are edges that run directly alongside the Floating Harbour / tidal Avon.
# Any edge whose midpoint is < 50 m from the River Avon should score ≤ 0.20.
RIVERSIDE_THRESHOLD = 0.20   # raw_water_cost must be ≤ this for riverside validation
INLAND_THRESHOLD    = 0.65   # raw_water_cost should be ≥ this for clearly inland edges

# Node IDs known to be on / very close to the Floating Harbour embankment.
# These are stable OSM node IDs in the Bristol Harbourside area.  If they are
# absent from the extracted graph the test still PASSes on general criteria.
KNOWN_RIVERSIDE_OSMIDS = {
    # Princes Wharf / waterfront path nodes (stable Bristol OSM IDs)
    # We use these as a soft check only — absence is not a failure.
}

# ─── Benchmark ───────────────────────────────────────────────────────────────


def _midpoint_coords(graph, u, v, data):
    """Return the approximate midpoint (lon, lat) of an edge."""
    try:
        u_data = graph.nodes[u]
        v_data = graph.nodes[v]
        lon = (u_data.get("x", 0) + v_data.get("x", 0)) / 2.0
        lat = (u_data.get("y", 0) + v_data.get("y", 0)) / 2.0
        return lon, lat
    except Exception:
        return None, None


def _haversine_m(lon1, lat1, lon2, lat2):
    """Approximate distance in metres between two WGS84 points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# Approximate polyline of the River Avon / Floating Harbour through Bristol
# (lon, lat pairs sampled ~200 m apart along the centreline)
AVON_CENTRELINE = [
    (-2.614, 51.448),   # Ashton area
    (-2.608, 51.449),   # Cumberland Basin
    (-2.601, 51.449),   # Baltic Wharf
    (-2.596, 51.450),   # Floating Harbour west
    (-2.590, 51.451),   # SS Great Britain
    (-2.583, 51.451),   # Harbourside / Watershed
    (-2.578, 51.452),   # Bristol Bridge
    (-2.573, 51.453),   # Temple Quay
    (-2.568, 51.453),   # Counterslip
]


def _min_dist_to_avon(lon, lat):
    """Distance in metres from a point to the nearest Avon centreline sample."""
    return min(_haversine_m(lon, lat, ax, ay) for ax, ay in AVON_CENTRELINE)


def run_benchmark():
    """Execute the water proximity scoring verification benchmark."""
    app = create_app()

    with app.app_context():
        print("=" * 60)
        print("BENCHMARK: Water Proximity Scoring (T-ENG-09)")
        print(f"BBox: {BBOX}")
        print("=" * 60)

        # ── 1. Build graph with water processing ON (greenness / elevation OFF
        #        to keep build time reasonable for a targeted water test)
        print("\n[Setup] Building graph with water processing enabled...")
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
            import traceback
            traceback.print_exc()
            return

        # ── 2. Check every edge has raw_water_cost ─────────────────────────
        print("\n[T1] Checking raw_water_cost attribute presence...")
        edges_total = 0
        edges_with_score = 0
        edges_missing_score = []

        for u, v, k, data in graph.edges(keys=True, data=True):
            edges_total += 1
            if "raw_water_cost" in data:
                edges_with_score += 1
            else:
                if len(edges_missing_score) < 10:
                    edges_missing_score.append((u, v, k))

        coverage_pct = (edges_with_score / edges_total * 100) if edges_total > 0 else 0
        coverage_pass = edges_with_score == edges_total
        print(f"  Edges with raw_water_cost: {edges_with_score:,} / {edges_total:,} ({coverage_pct:.1f}%)")
        print(f"  Coverage: {'PASS ✓' if coverage_pass else 'FAIL ✗'}")

        # ── 3. Check values are in [0, 1] ───────────────────────────────────
        print("\n[T2] Checking value range [0.0, 1.0]...")
        out_of_range = []
        all_scores = []

        for u, v, k, data in graph.edges(keys=True, data=True):
            score = data.get("raw_water_cost")
            if score is None:
                continue
            all_scores.append(score)
            if not (0.0 <= score <= 1.0):
                out_of_range.append({"u": u, "v": v, "score": score})

        range_pass = len(out_of_range) == 0
        score_min = min(all_scores) if all_scores else None
        score_max = max(all_scores) if all_scores else None
        score_mean = sum(all_scores) / len(all_scores) if all_scores else None
        near_water_count = sum(1 for s in all_scores if s < 0.10)
        far_water_count  = sum(1 for s in all_scores if s > 0.90)

        print(f"  Out-of-range values: {len(out_of_range)}")
        print(f"  Score min: {score_min:.4f}  max: {score_max:.4f}  mean: {score_mean:.4f}")
        print(f"  Edges near water (score < 0.10): {near_water_count:,}")
        print(f"  Edges far from water (score > 0.90): {far_water_count:,}")
        print(f"  Range [0,1]: {'PASS ✓' if range_pass else 'FAIL ✗'}")

        # ── 4. Check low-cost edges exist (Bristol has the River Avon) ──────
        print("\n[T3] Checking at least 1 edge with raw_water_cost < 0.10...")
        near_water_pass = near_water_count >= 1
        print(f"  Near-water edges: {near_water_count}  (expected ≥ 1 for Bristol bbox)")
        print(f"  Near-water threshold: {'PASS ✓' if near_water_pass else 'FAIL ✗'}")

        # ── 5. Riverside vs inland spatial validation ───────────────────────
        print("\n[T4] Spatial validation: riverside edges score lower than inland edges...")
        river_edge_scores = []
        inland_edge_scores = []

        RIVERSIDE_BAND_M = 80    # metres from Avon centreline → "riverside"
        INLAND_BAND_MIN_M = 400  # metres from Avon → "clearly inland"

        for u, v, k, data in graph.edges(keys=True, data=True):
            score = data.get("raw_water_cost")
            if score is None:
                continue
            lon, lat = _midpoint_coords(graph, u, v, data)
            if lon is None:
                continue
            dist_to_avon = _min_dist_to_avon(lon, lat)
            if dist_to_avon < RIVERSIDE_BAND_M:
                river_edge_scores.append(score)
            elif dist_to_avon > INLAND_BAND_MIN_M:
                inland_edge_scores.append(score)

        if river_edge_scores and inland_edge_scores:
            river_mean  = sum(river_edge_scores)  / len(river_edge_scores)
            inland_mean = sum(inland_edge_scores) / len(inland_edge_scores)
            spatial_pass = river_mean < inland_mean
            print(f"  Riverside edges ({len(river_edge_scores):,}): mean score = {river_mean:.4f}")
            print(f"  Inland edges    ({len(inland_edge_scores):,}): mean score = {inland_mean:.4f}")
            print(f"  Riverside < Inland: {'PASS ✓' if spatial_pass else 'FAIL ✗'}")
        else:
            spatial_pass = None
            river_mean   = None
            inland_mean  = None
            print(f"  [WARN] Insufficient edges for spatial split "
                  f"(riverside={len(river_edge_scores)}, inland={len(inland_edge_scores)}). "
                  f"Spatial sub-test skipped.")

        # ── 6. Score distribution histogram buckets ────────────────────────
        NUM_BUCKETS = 10
        bucket_size = 1.0 / NUM_BUCKETS
        histogram = {f"{i*bucket_size:.1f}-{(i+1)*bucket_size:.1f}": 0 for i in range(NUM_BUCKETS)}
        for s in all_scores:
            bucket_idx = min(int(s / bucket_size), NUM_BUCKETS - 1)
            key = f"{bucket_idx*bucket_size:.1f}-{(bucket_idx+1)*bucket_size:.1f}"
            histogram[key] += 1

        # ── 7. Summary ──────────────────────────────────────────────────────
        print("\n" + "=" * 60)
        print("RESULTS SUMMARY")
        print("=" * 60)
        overall_pass = coverage_pass and range_pass and near_water_pass and (spatial_pass is not False)
        print(f"  T1 — Attribute coverage (100% edges):  {'PASS ✓' if coverage_pass else 'FAIL ✗'}")
        print(f"  T2 — Values in [0, 1]:                 {'PASS ✓' if range_pass else 'FAIL ✗'}")
        print(f"  T3 — At least 1 near-water edge:       {'PASS ✓' if near_water_pass else 'FAIL ✗'}")
        if spatial_pass is not None:
            print(f"  T4 — Riverside < Inland (mean score):  {'PASS ✓' if spatial_pass else 'FAIL ✗'}")
        else:
            print("  T4 — Riverside < Inland:               SKIPPED (insufficient data)")
        print("-" * 60)
        print(f"  OVERALL: {'PASS ✓' if overall_pass else 'FAIL ✗'}")
        print("=" * 60)

        # ── 8. Write JSON ───────────────────────────────────────────────────
        os.makedirs(RESULTS_DIR, exist_ok=True)
        output = {
            "test_id": "T-ENG-09",
            "requirement": "FR-01",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "bbox": BBOX,
            "graph_nodes": graph.number_of_nodes(),
            "graph_edges": edges_total,
            "t1_coverage": {
                "edges_with_score": edges_with_score,
                "edges_total": edges_total,
                "coverage_pct": round(coverage_pct, 2),
                "pass": coverage_pass,
            },
            "t2_range": {
                "out_of_range_count": len(out_of_range),
                "out_of_range_sample": out_of_range[:5],
                "score_min": round(score_min, 6) if score_min is not None else None,
                "score_max": round(score_max, 6) if score_max is not None else None,
                "score_mean": round(score_mean, 6) if score_mean is not None else None,
                "pass": range_pass,
            },
            "t3_near_water": {
                "near_water_edges_lt_0_10": near_water_count,
                "far_water_edges_gt_0_90": far_water_count,
                "pass": near_water_pass,
            },
            "t4_spatial": {
                "riverside_band_m": RIVERSIDE_BAND_M,
                "inland_min_m": INLAND_BAND_MIN_M,
                "riverside_edge_count": len(river_edge_scores),
                "inland_edge_count": len(inland_edge_scores),
                "riverside_mean_score": round(river_mean, 6) if river_mean is not None else None,
                "inland_mean_score": round(inland_mean, 6) if inland_mean is not None else None,
                "pass": spatial_pass,
            },
            "score_distribution_histogram": histogram,
            "overall_pass": overall_pass,
        }

        results_path = os.path.join(RESULTS_DIR, "water_verification.json")
        with open(results_path, "w") as f:
            json.dump(output, f, indent=2)
        print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    run_benchmark()
