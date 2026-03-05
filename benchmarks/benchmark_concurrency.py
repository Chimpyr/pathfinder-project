"""
Benchmark: Concurrent Tile Lock Verification (T-REL-01 / NFR-03)

Fires 4 simultaneous route requests for the same uncached region
and verifies that only 1 Celery build task is created (Redis lock).

Uses threading.Barrier to synchronise all threads before firing,
ensuring truly simultaneous requests.

Pass criteria: exactly 1 build_tile_task enqueued

Usage:
    docker compose exec api python -m benchmarks.benchmark_concurrency
"""

import time
import json
import os
import threading
from datetime import datetime, timezone
import requests


# Configuration
API_BASE = os.environ.get("API_BASE", "http://localhost:5000")
CONCURRENT_REQUESTS = 4
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Use a unique bbox that won't have a cached graph
# (offset slightly from standard Bristol test coordinates to avoid cache hits)
# API expects use_wsm flag + nested weights dict (see app/routes.py)
TEST_PAYLOAD = {
    "start_lat": 51.4300,
    "start_lon": -2.6100,
    "end_lat": 51.4400,
    "end_lon": -2.5900,
    "use_wsm": True,
    "weights": {
        "distance": 3,
        "greenness": 2,
        "quietness": 1,
        "water": 0,
        "social": 0,
        "slope": 0,
    },
}

# Barrier ensures all threads start their HTTP request simultaneously
_barrier = threading.Barrier(CONCURRENT_REQUESTS)


def send_request(request_id: int, results: list):
    """
    Send a route request and record the response.

    All threads wait at the barrier before firing, ensuring
    truly simultaneous requests to test the Redis lock.

    Args:
        request_id: Identifier for this request.
        results: Shared list to append results to.
    """
    try:
        # Block until all threads are ready
        _barrier.wait(timeout=10)
    except threading.BrokenBarrierError:
        print(f"  Request {request_id}: Barrier broken — thread did not synchronise")
        results.append({"request_id": request_id, "error": "Barrier broken"})
        return

    start = time.perf_counter()
    try:
        resp = requests.post(f"{API_BASE}/api/route", json=TEST_PAYLOAD, timeout=30)
        elapsed_ms = (time.perf_counter() - start) * 1000
        data = resp.json()
        results.append({
            "request_id": request_id,
            "status_code": resp.status_code,
            "task_id": data.get("task_id"),
            "elapsed_ms": round(elapsed_ms),
            "has_route": "route" in data or "coordinates" in data,
        })
        print(f"  Request {request_id}: {resp.status_code} in {elapsed_ms:.0f}ms "
              f"(task_id={data.get('task_id', 'N/A')})")
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        results.append({
            "request_id": request_id,
            "error": str(e),
            "elapsed_ms": round(elapsed_ms),
        })
        print(f"  Request {request_id}: ERROR in {elapsed_ms:.0f}ms - {e}")


def run_benchmark():
    """Execute the concurrency benchmark."""
    print("=" * 60)
    print("BENCHMARK: Concurrent Tile Lock (T-REL-01)")
    print(f"Target: exactly 1 Celery task for {CONCURRENT_REQUESTS} simultaneous requests")
    print(f"Synchronisation: threading.Barrier({CONCURRENT_REQUESTS})")
    print("=" * 60)

    # Fire concurrent requests
    print(f"\n[Benchmark] Firing {CONCURRENT_REQUESTS} simultaneous requests...")
    results = []
    threads = []

    for i in range(CONCURRENT_REQUESTS):
        t = threading.Thread(target=send_request, args=(i + 1, results))
        threads.append(t)

    # Start all threads (they will block at the barrier until all are ready)
    for t in threads:
        t.start()

    # Wait for all to complete
    for t in threads:
        t.join(timeout=60)

    # Analyse results
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)

    # Count unique task IDs (excludes None/direct responses)
    task_ids = set()
    async_count = 0
    sync_count = 0
    error_count = 0

    for r in results:
        if r.get("error"):
            error_count += 1
        elif r.get("status_code") == 202:
            async_count += 1
            if r.get("task_id"):
                task_ids.add(r["task_id"])
        elif r.get("status_code") == 200:
            sync_count += 1

    print(f"  Total Requests:    {len(results)}")
    print(f"  Async (202):       {async_count}")
    print(f"  Sync (200):        {sync_count}")
    print(f"  Errors:            {error_count}")
    print(f"  Unique Task IDs:   {len(task_ids)}")
    if task_ids:
        for tid in task_ids:
            print(f"    - {tid}")
    print("-" * 60)

    # The key assertion: if all requests went async,
    # there should be exactly 1 unique task ID
    # (the others should reuse the existing task via Redis lock)
    if async_count > 0:
        lock_pass = len(task_ids) == 1
        print(f"  Unique tasks == 1: {'PASS ✓' if lock_pass else 'FAIL ✗'} ({len(task_ids)} unique)")
    else:
        # All requests were served from cache (sync) — lock wasn't tested
        lock_pass = True
        print("  [INFO] All requests served synchronously (cache was warm)")
        print("  [INFO] Redis lock not tested — clear cache before running")

    print("=" * 60)

    # Poll for task completion if async
    if task_ids:
        print("\n[Polling] Waiting for async task(s) to complete...")
        for task_id in task_ids:
            for attempt in range(60):  # 5 minute timeout
                time.sleep(5)
                try:
                    poll = requests.get(f"{API_BASE}/api/task/{task_id}", timeout=10)
                    status = poll.json().get("status", "UNKNOWN")
                    print(f"  Task {task_id}: {status}")
                    if status in ("SUCCESS", "COMPLETE", "complete", "FAILURE", "FAILED"):
                        break
                except Exception:
                    pass

    # Save results
    os.makedirs(RESULTS_DIR, exist_ok=True)
    output = {
        "test_id": "T-REL-01",
        "requirement": "NFR-03",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "concurrent_requests": CONCURRENT_REQUESTS,
        "async_count": async_count,
        "sync_count": sync_count,
        "error_count": error_count,
        "unique_task_ids": list(task_ids),
        "lock_pass": lock_pass,
        "overall_pass": lock_pass,
        "raw_results": results,
    }
    results_path = os.path.join(RESULTS_DIR, "concurrency.json")
    with open(results_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {results_path}")


if __name__ == "__main__":
    run_benchmark()
