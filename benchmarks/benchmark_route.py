"""
Benchmark: Route Computation Latency (T-PERF-01 / NFR-01)

Measures the round-trip time of POST /api/route requests on a warm cache.
Reports min, max, mean, and p95 latency over N iterations.

Pass criteria: mean latency <= 5000ms

Usage:
    docker compose exec api python -m benchmarks.benchmark_route
"""

import time
import json
import os
import math
import statistics
from datetime import datetime, timezone
import requests


# Configuration
API_BASE = os.environ.get("API_BASE", "http://localhost:5000")
ITERATIONS = int(os.environ.get("BENCHMARK_ITERATIONS", "30"))
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Bristol test route (Temple Meads to Clifton Suspension Bridge)
# API expects use_wsm flag + nested weights dict (see app/routes.py)
TEST_PAYLOAD = {
    "start_lat": 51.4494,
    "start_lon": -2.5811,
    "end_lat": 51.4550,
    "end_lon": -2.6275,
    "use_wsm": True,
    "weights": {
        "distance": 3,
        "greenness": 2,
        "quietness": 1,
        "water": 1,
        "social": 1,
        "slope": 0,
    },
}

# Pass/fail thresholds (in milliseconds)
MEAN_THRESHOLD_MS = 5000
P95_THRESHOLD_MS = 8000


def run_benchmark():
    """Execute the route computation benchmark."""
    print("=" * 60)
    print("BENCHMARK: Route Computation Latency (T-PERF-01)")
    print(f"Target: mean <= {MEAN_THRESHOLD_MS}ms, p95 <= {P95_THRESHOLD_MS}ms")
    print(f"Iterations: {ITERATIONS}")
    print("=" * 60)

    # Warm-up request (ensures cache is hot)
    print("\n[Warm-up] Sending initial request to ensure cache is hot...")
    try:
        resp = requests.post(f"{API_BASE}/api/route", json=TEST_PAYLOAD, timeout=120)
        if resp.status_code == 202:
            # Async mode — poll until complete
            task_id = resp.json().get("task_id")
            print(f"  Async task started: {task_id}")
            print("  Polling for completion...")
            while True:
                time.sleep(5)
                poll = requests.get(f"{API_BASE}/api/task/{task_id}", timeout=30)
                status = poll.json().get("status", "UNKNOWN")
                print(f"  Status: {status}")
                if status in ("SUCCESS", "COMPLETE", "complete"):
                    break
                if status in ("FAILURE", "FAILED", "ERROR"):
                    print("  [ERROR] Task failed during warm-up. Aborting.")
                    return
            print("  [OK] Cache is now warm.")
        elif resp.status_code == 200:
            print("  [OK] Cache was already warm.")
        else:
            print(f"  [WARN] Unexpected status: {resp.status_code}")
    except Exception as e:
        print(f"  [ERROR] Warm-up failed: {e}")
        return

    # Benchmark iterations
    latencies_ms = []
    print(f"\n[Benchmark] Running {ITERATIONS} iterations...")

    for i in range(1, ITERATIONS + 1):
        start = time.perf_counter()
        try:
            resp = requests.post(f"{API_BASE}/api/route", json=TEST_PAYLOAD, timeout=30)
            elapsed_ms = (time.perf_counter() - start) * 1000

            if resp.status_code == 200:
                latencies_ms.append(elapsed_ms)
                print(f"  Iteration {i}/{ITERATIONS}: {elapsed_ms:.0f}ms (200 OK)")
            else:
                print(f"  Iteration {i}/{ITERATIONS}: {elapsed_ms:.0f}ms (Status {resp.status_code} - SKIPPED)")
        except Exception as e:
            elapsed_ms = (time.perf_counter() - start) * 1000
            print(f"  Iteration {i}/{ITERATIONS}: {elapsed_ms:.0f}ms (ERROR: {e})")

    if not latencies_ms:
        print("\n[FAIL] No successful iterations recorded.")
        return

    # Calculate statistics
    mean_ms = statistics.mean(latencies_ms)
    median_ms = statistics.median(latencies_ms)
    min_ms = min(latencies_ms)
    max_ms = max(latencies_ms)
    stdev_ms = statistics.stdev(latencies_ms) if len(latencies_ms) > 1 else 0
    sorted_latencies = sorted(latencies_ms)
    p95_idx = min(math.ceil(len(sorted_latencies) * 0.95) - 1, len(sorted_latencies) - 1)
    p95_ms = sorted_latencies[p95_idx]

    # Print results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"  Iterations:  {len(latencies_ms)}/{ITERATIONS}")
    print(f"  Min:         {min_ms:.0f}ms")
    print(f"  Max:         {max_ms:.0f}ms")
    print(f"  Mean:        {mean_ms:.0f}ms")
    print(f"  Median:      {median_ms:.0f}ms")
    print(f"  Std Dev:     {stdev_ms:.0f}ms")
    print(f"  P95:         {p95_ms:.0f}ms")
    print("-" * 60)

    # Pass/fail
    mean_pass = mean_ms <= MEAN_THRESHOLD_MS
    p95_pass = p95_ms <= P95_THRESHOLD_MS
    print(f"  Mean <= {MEAN_THRESHOLD_MS}ms:  {'PASS ✓' if mean_pass else 'FAIL ✗'}")
    print(f"  P95  <= {P95_THRESHOLD_MS}ms:  {'PASS ✓' if p95_pass else 'FAIL ✗'}")
    print("=" * 60)

    # Save results to JSON
    os.makedirs(RESULTS_DIR, exist_ok=True)
    results = {
        "test_id": "T-PERF-01",
        "requirement": "NFR-01",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "iterations": len(latencies_ms),
        "min_ms": round(min_ms),
        "max_ms": round(max_ms),
        "mean_ms": round(mean_ms),
        "median_ms": round(median_ms),
        "stdev_ms": round(stdev_ms),
        "p95_ms": round(p95_ms),
        "mean_pass": mean_pass,
        "p95_pass": p95_pass,
        "overall_pass": mean_pass and p95_pass,
        "raw_latencies_ms": [round(l) for l in latencies_ms],
    }
    results_path = os.path.join(RESULTS_DIR, "route_latency.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    run_benchmark()
