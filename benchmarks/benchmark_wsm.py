"""
Benchmark: WSM Efficacy Test (T-ENG-01, T-ENG-04, T-ENG-05, T-ENG-06, T-ENG-07)

Systematically validates the mathematical efficacy of the Weighted Sum Model (WSM)
by sending routing parameters against a warm cache. Assertions are made that
adjusting parameters correctly evaluates and produces mathematically distinct
path geometries, confirming Multi-Criteria algorithms natively affect the A* expansion.

Usage:
    docker compose exec api python -m benchmarks.benchmark_wsm
"""

import time
import json
import os
import copy
from datetime import datetime, timezone
import requests

# Configuration
API_BASE = os.environ.get("API_BASE", "http://localhost:5000")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Bristol test route (Temple Meads to Clifton Suspension Bridge)
TEST_PAYLOAD = {
    "start_lat": 51.4494,
    "start_lon": -2.5811,
    "end_lat": 51.4550,
    "end_lon": -2.6275,
    "use_wsm": True,
    "weights": {
        "distance": 5,
        "greenness": 0,
        "quietness": 0,
        "water": 0,
        "social": 0,
        "slope": 0,
    },
    "combine_nature": False,
    "heavily_avoid_unlit": False,
    "prefer_pedestrian": False
}


def _fetch_route(payload_override: dict, name: str) -> dict:
    """Helper to synchronously fetch a route and extract its geometry coordinates."""
    print(f"  [{name}] Fetching route...")
    payload = copy.deepcopy(TEST_PAYLOAD)
    
    # Merge overrides
    for key, value in payload_override.items():
        if key == "weights":
            payload["weights"].update(value)
        else:
            payload[key] = value

    try:
        resp = requests.post(f"{API_BASE}/api/route", json=payload, timeout=120)
        
        # If caching triggered async
        if resp.status_code == 202:
            task_id = resp.json().get("task_id")
            print(f"    Async task started: {task_id}. Polling...")
            while True:
                time.sleep(5)
                poll = requests.get(f"{API_BASE}/api/task/{task_id}", timeout=30)
                status = poll.json().get("status", "UNKNOWN")
                if status in ("SUCCESS", "COMPLETE", "complete"):
                    return poll.json().get("result", {})
                if status in ("FAILURE", "FAILED", "ERROR"):
                    print(f"    [ERROR] Task {task_id} failed.")
                    return {}
        elif resp.status_code == 200:
            return resp.json()
        else:
            print(f"    [WARN] Unexpected GET status: {resp.status_code}")
            return {}
            
    except Exception as e:
        print(f"    [ERROR] Fetch failed: {e}")
        return {}


def _is_distinct(geom_a: list, geom_b: list) -> bool:
    """
    Evaluates if two coordinate geometries are distinct.
    Exact sequence equality means the algorithm didn't alter the path.
    """
    if not geom_a or not geom_b:
        return False
    return geom_a != geom_b


def run_benchmark():
    """Execute the WSM coverage suite."""
    print("=" * 60)
    print("BENCHMARK: WSM Efficacy Suite")
    print("Covering: T-ENG-01, T-ENG-04, T-ENG-05, T-ENG-06, T-ENG-07")
    print("=" * 60)

    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tests_passed": 0,
        "total_tests": 8,
        "details": []
    }

    # 1. Warm-up and fetch Baseline
    print("\n[Setup] Establishing Baseline Geography (Distance Only = 5)...")
    base_data = _fetch_route({"weights": {"distance": 5}}, "Baseline (Dist: 5)")
    if not base_data or "geometry" not in base_data:
        print("\n[FATAL] Failed to retrieve base geometry. Aborting.")
        return
        
    base_geom = base_data["geometry"]["coordinates"]
    print(f"  Baseline established ({len(base_geom)} coordinates).")

    # Tracking paths to ensure they differ from each other (T-ENG-06)
    geometries_cache = {"Baseline": base_geom}

    # Helper for running standard variance tests
    def _test_variance(test_id: str, requirement: str, name: str, overrides: dict, compare_against: str = "Baseline"):
        print(f"\n[{test_id}] {name}...")
        route_data = _fetch_route(overrides, name)
        
        if not route_data or "geometry" not in route_data:
            print(f"  -> FAIL (No route data returned)")
            metrics = {"test_id": test_id, "name": name, "pass": False, "error": "No route data"}
            results["details"].append(metrics)
            return

        test_geom = route_data["geometry"]["coordinates"]
        
        if compare_against in geometries_cache:
            compare_geom = geometries_cache[compare_against]
        else:
            compare_geom = geometries_cache["Baseline"]

        passed = _is_distinct(test_geom, compare_geom)
        status = "PASS" if passed else "FAIL"
        print(f"  -> {status}: Path geometry is {'distinct from' if passed else 'IDENTICAL to'} {compare_against}")
        
        results["details"].append({
            "test_id": test_id,
            "requirement": requirement,
            "name": name,
            "pass": passed,
            "coords_length": len(test_geom)
        })
        
        if passed:
            results["tests_passed"] += 1
            geometries_cache[name] = test_geom

    # Execute T-ENG-01 (Greenness Deviation) & T-ENG-06 component
    _test_variance("T-ENG-01", "FR-01", "Greenness Weight (5)", {"weights": {"greenness": 5}})
    
    # Execute T-ENG-06 (Multi-Weight Variance)
    _test_variance("T-ENG-06.1", "FR-01", "Quietness Weight (5)", {"weights": {"quietness": 5}})
    _test_variance("T-ENG-06.2", "FR-01", "Water Weight (5)", {"weights": {"water": 5}})
    _test_variance("T-ENG-06.3", "FR-01", "Social Weight (5)", {"weights": {"social": 5}})
    
    # Execute T-ENG-05 (Elevation/Slope Weighting)
    _test_variance("T-ENG-05", "FR-14", "Slope Weight (5)", {"weights": {"slope": 5}})
    
    # Execute T-ENG-04 (Dynamic Multiplicative Penalty)
    _test_variance("T-ENG-04", "FR-10", "Unlit Penalty", {"heavily_avoid_unlit": True})

    # Execute T-ENG-07 (Combine Nature OR/AND semantics)
    print("\n[T-ENG-07] Testing Combine Nature Semantic Algebra...")
    # Generate AND semantics (combine_nature = False)
    and_data = _fetch_route({"weights": {"greenness": 5, "water": 5}, "combine_nature": False}, "Nature (AND)")
    # Generate OR semantics (combine_nature = True)
    or_data = _fetch_route({"weights": {"greenness": 5, "water": 5}, "combine_nature": True}, "Nature (OR)")

    if and_data and or_data and "geometry" in and_data and "geometry" in or_data:
        and_geom = and_data["geometry"]["coordinates"]
        or_geom = or_data["geometry"]["coordinates"]
        
        passed = _is_distinct(and_geom, or_geom)
        status = "PASS" if passed else "FAIL"
        print(f"  -> {status}: OR semantic path geometry is {'distinct from' if passed else 'IDENTICAL to'} AND semantic path")
        
        results["details"].append({
            "test_id": "T-ENG-07",
            "requirement": "FR-01",
            "name": "Combine Nature Semantics",
            "pass": passed,
            "coords_length_and": len(and_geom),
            "coords_length_or": len(or_geom)
        })
        if passed:
             results["tests_passed"] += 1
    else:
        print(f"  -> FAIL (No route data returned for Nature Combinatorics)")
        results["details"].append({"test_id": "T-ENG-07", "name": "Combine Nature Semantics", "pass": False, "error": "No route data"})


    # Final Summary & Output
    results["overall_pass"] = results["tests_passed"] == results["total_tests"]
    
    print("\n" + "=" * 60)
    print(f"OVERALL RESULTS: {results['tests_passed']}/{results['total_tests']} PASSED")
    print("=" * 60)

    # Save Results
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results_path = os.path.join(RESULTS_DIR, "wsm_efficacy.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nDetailed JSON saved to: {results_path}")


if __name__ == "__main__":
    run_benchmark()
