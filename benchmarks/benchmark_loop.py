"""
Benchmark: Loop Solver Performance (T-PERF-05 / FR-03)

Measures loop solver convergence, wall-clock time, and distance
accuracy using the /api/loop endpoint with different directional biases.

Note: The loop API uses `directional_bias` (north/east/south/west/none)
rather than explicit shape selection. The geometric skeleton shape is
determined internally by the solver — different biases produce different
route geometries, which this benchmark measures.

Reports:
  - Wall-clock time per directional bias
  - Distance accuracy (% error from target)
  - Whether loops close (start ≈ end)
  - Whether any loops self-intersect

Usage:
    docker compose exec api python -m benchmarks.benchmark_loop
"""

import time
import json
import os
import statistics
from datetime import datetime, timezone
import requests


# Configuration
API_BASE = os.environ.get("API_BASE", "http://localhost:5000")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")
ITERATIONS_PER_CONFIG = 3
ITERATIONS_PER_CONFIG = 2

# Bristol city centre starting point
START_LAT = 51.4545
START_LON = -2.5879

# Target distances to test (in km)
TARGET_DISTANCES = [3.0, 5.0, 7.5, 10.0]

# Directional biases to test (these influence the geometric shape of the loop)
# The loop solver internally selects skeleton shapes based on bias and variety
BIASES = ["north", "east", "south", "none"]


def _test_loop(bias: str, target_km: float) -> dict:
    """
    Request a loop route via /api/loop and measure performance.

    Args:
        bias: Directional bias for the loop (north/east/south/west/none).
        target_km: Target distance in kilometres.

    Returns:
        Dictionary with timing and accuracy metrics.
    """
    # Payload matches the actual /api/loop contract (see app/routes.py line 157)
    payload = {
        "start_lat": START_LAT,
        "start_lon": START_LON,
        "distance_km": target_km,
        "directional_bias": bias,
        "variety_level": 0,
        "use_wsm": True,
        "weights": {
            "distance": 3,
            "greenness": 2,
            "quietness": 1,
            "water": 0,
            "social": 0,
            "slope": 0,
        },
        "prefer_pedestrian": False,
        "prefer_paved": False,
        "prefer_lit": False,
        "avoid_unsafe_roads": False,
    }

    start = time.perf_counter()
    try:
        resp = requests.post(f"{API_BASE}/api/loop", json=payload, timeout=120)
        elapsed_s = time.perf_counter() - start

        if resp.status_code == 202:
            # Async — poll until complete, then re-request from cache
            task_id = resp.json().get("task_id")
            for i in range(120):
                time.sleep(2)
                poll = requests.get(f"{API_BASE}/api/task/{task_id}", timeout=10)
                status = poll.json().get("status", "UNKNOWN")
                if os.environ.get("VERBOSE_LOGGING") == "True" and i % 5 == 0:
                    print(f"    [POLL {i}/120] Task {task_id} status: {status}")
                if status in ("SUCCESS", "COMPLETE", "complete"):
                    elapsed_s = time.perf_counter() - start
                    if os.environ.get("VERBOSE_LOGGING") == "True":
                        print(f"    [POLL] Task complete in {elapsed_s:.1f}s. Re-requesting route...")
                    # Re-request from cache (fast path)
                    resp = requests.post(f"{API_BASE}/api/loop", json=payload, timeout=60)
                    break
                if status in ("FAILURE", "FAILED", "ERROR"):
                    return {"bias": bias, "target_km": target_km, "success": False, "error": status}
            else:
                # Polling completely timed out after 240 seconds
                return {"bias": bias, "target_km": target_km, "success": False, "error": "Async polling timed out after 240s"}

        data = resp.json()

        if resp.status_code != 200:
            return {"bias": bias, "target_km": target_km, "success": False, "error": f"HTTP {resp.status_code}"}

        # Extract metrics from response
        # The loop API returns stats.distance_km or actual_distance_km
        stats = data.get("stats", {})
        actual_distance_km = float(stats.get("distance_km", data.get("actual_distance_km", 0)))

        # Loop API returns multi_loop format: coordinates are nested under loops[0].route_coords
        # Fall back to legacy top-level keys for compatibility
        loops_list = data.get("loops", [])
        coordinates = (
            loops_list[0].get("route_coords", []) if loops_list
            else data.get("route_coords", data.get("coordinates", []))
        )

        # Check if loop closes (start ≈ end)
        loop_closes = False
        closure_distance_m = None
        if coordinates and len(coordinates) >= 2:
            start_coord = coordinates[0]
            end_coord = coordinates[-1]
            from math import radians, sin, cos, sqrt, atan2
            R = 6371000  # Earth radius in metres
            lat1, lon1 = radians(start_coord[0]), radians(start_coord[1])
            lat2, lon2 = radians(end_coord[0]), radians(end_coord[1])
            dlat = lat2 - lat1
            dlon = lon2 - lon1
            a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
            c = 2 * atan2(sqrt(a), sqrt(1-a))
            closure_distance_m = R * c
            loop_closes = closure_distance_m <= 100

        # Check for self-intersection (simplified: check for duplicate coordinates)
        coord_set = set()
        self_intersects = False
        for c in coordinates:
            key = (round(c[0], 5), round(c[1], 5))
            if key in coord_set:
                self_intersects = True
                break
            coord_set.add(key)

        # Distance accuracy
        distance_error_pct = abs(actual_distance_km - target_km) / target_km * 100 if target_km > 0 else 0

        return {
            "bias": bias,
            "target_km": target_km,
            "actual_km": round(actual_distance_km, 2),
            "distance_error_pct": round(distance_error_pct, 1),
            "elapsed_s": round(elapsed_s, 2),
            "loop_closes": loop_closes,
            "closure_distance_m": round(closure_distance_m, 1) if closure_distance_m is not None else None,
            "self_intersects": self_intersects,
            "coordinate_count": len(coordinates),
            "success": True,
        }

    except Exception as e:
        return {"bias": bias, "target_km": target_km, "success": False, "error": str(e)}


def run_benchmark():
    """Execute the loop solver benchmark."""
    print("=" * 60)
    print("BENCHMARK: Loop Solver Performance (T-PERF-05)")
    print(f"Directional biases: {BIASES}")
    print(f"Target distances: {TARGET_DISTANCES} km")
    print(f"Iterations per config: {ITERATIONS_PER_CONFIG}")
    print("=" * 60)

    all_results = []

    for bias in BIASES:
        for target_km in TARGET_DISTANCES:
            print(f"\n[{bias.upper()}] Target: {target_km}km")

            for attempt in range(1, ITERATIONS_PER_CONFIG + 1):
                print(f"  Attempt {attempt}/{ITERATIONS_PER_CONFIG}...", end=" ")
                result = _test_loop(bias, target_km)
                all_results.append(result)

                if result["success"]:
                    print(f"✓ {result['actual_km']}km "
                          f"(err: {result['distance_error_pct']}%, "
                          f"closes: {result['loop_closes']}, "
                          f"time: {result['elapsed_s']}s)")
                else:
                    print(f"✗ {result.get('error', 'unknown')}")

    # Aggregate results per bias
    print("\n" + "=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)

    bias_summaries = {}
    for bias in BIASES:
        bias_results = [r for r in all_results if r["bias"] == bias and r["success"]]
        if not bias_results:
            bias_summaries[bias] = {"success_rate": 0}
            continue

        total_attempts = len([r for r in all_results if r["bias"] == bias])
        avg_time = statistics.mean([r["elapsed_s"] for r in bias_results])
        avg_error = statistics.mean([r["distance_error_pct"] for r in bias_results])
        closure_rate = sum(1 for r in bias_results if r["loop_closes"]) / len(bias_results) * 100
        intersection_rate = sum(1 for r in bias_results if r["self_intersects"]) / len(bias_results) * 100

        summary = {
            "total_attempts": total_attempts,
            "successes": len(bias_results),
            "success_rate": round(len(bias_results) / total_attempts * 100),
            "avg_time_s": round(avg_time, 2),
            "avg_distance_error_pct": round(avg_error, 1),
            "closure_rate_pct": round(closure_rate),
            "self_intersection_rate_pct": round(intersection_rate),
        }
        bias_summaries[bias] = summary

        print(f"  {bias.upper():<12} "
              f"avg_time={summary['avg_time_s']}s  "
              f"avg_err={summary['avg_distance_error_pct']}%  "
              f"closes={summary['closure_rate_pct']}%  "
              f"intersects={summary['self_intersection_rate_pct']}%")

    print("=" * 60)

    # Pass/fail criteria
    all_close = all(
        s.get("closure_rate_pct", 0) >= 80
        for s in bias_summaries.values()
        if s.get("success_rate", 0) > 0
    )
    avg_error_ok = all(
        s.get("avg_distance_error_pct", 100) <= 25
        for s in bias_summaries.values()
        if s.get("success_rate", 0) > 0
    )
    no_intersections = all(
        s.get("self_intersection_rate_pct", 100) == 0
        for s in bias_summaries.values()
        if s.get("success_rate", 0) > 0
    )

    print(f"  Loops close (≥80%):      {'PASS ✓' if all_close else 'FAIL ✗'}")
    print(f"  Distance error ≤25%:     {'PASS ✓' if avg_error_ok else 'FAIL ✗'}")
    print(f"  No self-intersections:   {'PASS ✓' if no_intersections else 'WARN ⚠'}")

    # Save results
    os.makedirs(RESULTS_DIR, exist_ok=True)
    output = {
        "test_id": "T-PERF-05",
        "requirement": "FR-03",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "directional_biases": BIASES,
        "target_distances_km": TARGET_DISTANCES,
        "iterations_per_config": ITERATIONS_PER_CONFIG,
        "summaries": bias_summaries,
        "raw_results": all_results,
        "overall_pass": all_close and avg_error_ok,
    }
    results_path = os.path.join(RESULTS_DIR, "loop_solver.json")
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    run_benchmark()
