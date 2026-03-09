"""
Benchmark: WSM Efficacy Test (T-ENG-01, T-ENG-04, T-ENG-05, T-ENG-06, T-ENG-07)

Systematically validates the mathematical efficacy of the Weighted Sum Model (WSM)
by sending routing requests against a warm cache. Assertions confirm that
adjusting weight parameters produces geometrically distinct path topologies,
proving multi-criteria algorithms natively affect A* expansion.

The /api/route response wraps coordinates under:
    response["routes"]["balanced"]["route_coords"]
This benchmark extracts and compares those coordinate arrays.

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
BASE_PAYLOAD = {
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
    "prefer_pedestrian": False,
    "prefer_lit": False,
}

# Maximum time to wait for an async graph build (seconds)
ASYNC_TIMEOUT_S = 900


def _extract_coords(response_json: dict) -> list | None:
    """
    Extract coordinate array from the /api/route JSON response.

    The API returns coordinates at:
        response["routes"]["balanced"]["route_coords"]

    Returns:
        List of coordinate pairs, or None if extraction fails.
    """
    try:
        routes = response_json.get("routes", {})
        balanced = routes.get("balanced", {})
        coords = balanced.get("route_coords")
        if coords and isinstance(coords, list) and len(coords) > 0:
            return coords
    except (AttributeError, TypeError):
        pass
    return None


def _fetch_route(payload_override: dict, name: str) -> list | None:
    """
    Send a route request and return the coordinate array.

    Handles both synchronous (200) and asynchronous (202 → poll) flows.
    Returns the coordinate list directly, or None on failure.
    """
    print(f"  [{name}] Requesting route...")
    payload = copy.deepcopy(BASE_PAYLOAD)

    # Merge overrides (nested dict for weights)
    for key, value in payload_override.items():
        if key == "weights":
            payload["weights"].update(value)
        else:
            payload[key] = value

    try:
        resp = requests.post(f"{API_BASE}/api/route", json=payload, timeout=120)

        if resp.status_code == 202:
            # Async — poll until complete then re-request from cache
            task_id = resp.json().get("task_id")
            print(f"    Async build started (task_id={task_id}). Polling...")
            deadline = time.time() + ASYNC_TIMEOUT_S
            while time.time() < deadline:
                time.sleep(5)
                poll = requests.get(f"{API_BASE}/api/task/{task_id}", timeout=30)
                status = poll.json().get("status", "UNKNOWN")
                if os.environ.get("VERBOSE_LOGGING") == "True":
                    print(f"      [POLL] Task {task_id} status: {status}")
                if status in ("SUCCESS", "COMPLETE", "complete"):
                    # Re-request — cache should now be warm
                    resp = requests.post(
                        f"{API_BASE}/api/route", json=payload, timeout=120
                    )
                    return _extract_coords(resp.json()) if resp.status_code == 200 else None
                if status in ("FAILURE", "FAILED", "ERROR"):
                    print(f"    [ERROR] Task {task_id} failed.")
                    return None
            print(f"    [ERROR] Async timeout after {ASYNC_TIMEOUT_S}s")
            return None

        elif resp.status_code == 200:
            return _extract_coords(resp.json())

        else:
            print(f"    [WARN] Unexpected status: {resp.status_code}")
            return None

    except Exception as e:
        print(f"    [ERROR] Request failed: {e}")
        return None


def _coords_are_distinct(geom_a: list, geom_b: list) -> bool:
    """
    Evaluate whether two coordinate arrays represent distinct paths.

    A simple equality check suffices: if the A* search took a different
    traversal, the node sequence (and therefore coordinate list) will differ.
    """
    if not geom_a or not geom_b:
        return False
    return geom_a != geom_b


def run_benchmark():
    """Execute the WSM efficacy benchmark suite."""
    print("=" * 60)
    print("BENCHMARK: WSM Efficacy Suite")
    print("Covering: T-ENG-01, T-ENG-04, T-ENG-05, T-ENG-06, T-ENG-07")
    print("=" * 60)

    # We expect 8 sub-tests (6 variance + 2 advanced toggles)
    total_tests = 8
    results = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "tests_passed": 0,
        "total_tests": total_tests,
        "details": [],
    }

    # ── Baseline (distance only = 5) ─────────────────────────────────
    print("\n[Setup] Establishing baseline (distance=5, all others=0)...")
    base_coords = _fetch_route({"weights": {"distance": 5}}, "Baseline")
    if not base_coords:
        print("\n[FATAL] Could not retrieve baseline route. Aborting.")
        # Save partial results so the runner log still has output
        os.makedirs(RESULTS_DIR, exist_ok=True)
        results["error"] = "Baseline route unavailable"
        results_path = os.path.join(RESULTS_DIR, "wsm_efficacy.json")
        with open(results_path, "w") as f:
            json.dump(results, f, indent=2)
        return

    print(f"  Baseline established ({len(base_coords)} coordinates).\n")

    # ── Helper ────────────────────────────────────────────────────────
    def _run_variance_test(
        test_id: str,
        requirement: str,
        label: str,
        overrides: dict,
        compare_coords: list | None = None,
    ):
        """Compare a weighted route against the baseline (or custom ref)."""
        ref = compare_coords if compare_coords is not None else base_coords
        print(f"[{test_id}] {label}")
        coords = _fetch_route(overrides, label)

        if coords is None:
            print(f"  -> FAIL (no route data returned)")
            results["details"].append(
                {"test_id": test_id, "requirement": requirement,
                 "name": label, "pass": False, "error": "No route data"}
            )
            return None

        passed = _coords_are_distinct(coords, ref)
        tag = "PASS" if passed else "FAIL"
        print(f"  -> {tag}: geometry is {'distinct from' if passed else 'IDENTICAL to'} reference")

        results["details"].append({
            "test_id": test_id,
            "requirement": requirement,
            "name": label,
            "pass": passed,
            "coords_length": len(coords),
        })
        if passed:
            results["tests_passed"] += 1
        return coords

    # ── T-ENG-01: Greenness deviation ─────────────────────────────────
    _run_variance_test("T-ENG-01", "FR-01", "Greenness (5)",
                       {"weights": {"greenness": 5}})

    # ── T-ENG-06: Multi-weight normalisation (one test per weight) ────
    _run_variance_test("T-ENG-06.q", "FR-01", "Quietness (5)",
                       {"weights": {"quietness": 5}})
    _run_variance_test("T-ENG-06.w", "FR-01", "Water (5)",
                       {"weights": {"water": 5}})
    _run_variance_test("T-ENG-06.s", "FR-01", "Social (5)",
                       {"weights": {"social": 5}})

    # ── T-ENG-05: Slope / elevation ───────────────────────────────────
    _run_variance_test("T-ENG-05", "FR-14", "Slope (5)",
                       {"weights": {"slope": 5}})

    # ── T-ENG-04: Dynamic multiplicative penalty / Advanced Options ──────
    _run_variance_test("T-ENG-04", "FR-10", "Unlit penalty",
                       {"heavily_avoid_unlit": True})
    
    _run_variance_test("T-ENG-04.p", "FR-10", "Prefer Pedestrian",
                       {"prefer_pedestrian": True})

    # ── T-ENG-07: Combine Nature OR vs AND semantics ──────────────────
    print("\n[T-ENG-07] Combine Nature semantic algebra...")
    and_coords = _fetch_route(
        {"weights": {"greenness": 5, "water": 5}, "combine_nature": False},
        "Nature (AND)",
    )
    or_coords = _fetch_route(
        {"weights": {"greenness": 5, "water": 5}, "combine_nature": True},
        "Nature (OR)",
    )

    if and_coords and or_coords:
        passed = _coords_are_distinct(and_coords, or_coords)
        tag = "PASS" if passed else "FAIL"
        print(f"  -> {tag}: OR geometry is {'distinct from' if passed else 'IDENTICAL to'} AND geometry")
        results["details"].append({
            "test_id": "T-ENG-07",
            "requirement": "FR-01",
            "name": "Combine Nature OR/AND",
            "pass": passed,
            "coords_length_and": len(and_coords),
            "coords_length_or": len(or_coords),
        })
        if passed:
            results["tests_passed"] += 1
    else:
        print("  -> FAIL (could not retrieve both Nature variants)")
        results["details"].append({
            "test_id": "T-ENG-07", "requirement": "FR-01",
            "name": "Combine Nature OR/AND", "pass": False,
            "error": "Missing route data",
        })

    # ── Summary ───────────────────────────────────────────────────────
    results["overall_pass"] = results["tests_passed"] == total_tests

    print("\n" + "=" * 60)
    print(f"RESULTS: {results['tests_passed']}/{total_tests} PASSED")
    print("=" * 60)

    os.makedirs(RESULTS_DIR, exist_ok=True)
    results_path = os.path.join(RESULTS_DIR, "wsm_efficacy.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nJSON saved to: {results_path}")


if __name__ == "__main__":
    run_benchmark()
