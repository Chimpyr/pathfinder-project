import time
import json
import os
import threading
from datetime import datetime, timezone
import requests
import statistics

API_BASE = os.environ.get("API_BASE", "http://localhost:5000")
RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

# Ensure this is a route that will be quick to route, but we must ensure it's cached
PAYLOAD = {
    "start_lat": 51.4500,
    "start_lon": -2.6000,
    "end_lat": 51.4600,
    "end_lon": -2.5900,
    "use_wsm": True,
    "weights": {"distance": 5, "greenness": 0, "quietness": 0, "water": 0, "social": 0, "slope": 0}
}

CONCURRENCY_LEVELS = [1, 5, 10, 20]

def send_request(results_list, barrier):
    try:
        barrier.wait(timeout=10)
    except threading.BrokenBarrierError:
        return
        
    start = time.perf_counter()
    try:
        resp = requests.post(f"{API_BASE}/api/route", json=PAYLOAD, timeout=120)
        elapsed = (time.perf_counter() - start) * 1000
        if resp.status_code == 200:
            results_list.append(elapsed)
        else:
            print(f"    Failed Request: Status {resp.status_code}")
    except Exception as e:
        print(f"    Failed Request Exception: {e}")

def run_benchmark():
    print("=" * 60)
    print("BENCHMARK: API Stress Test under Load (T-PERF-06)")
    print("=" * 60)
    
    # Warm up cache
    print("[Warmup] Sending initial request to cache graph...")
    resp = requests.post(f"{API_BASE}/api/route", json=PAYLOAD, timeout=300)
    if resp.status_code == 202:
        print("  Waiting for async build to complete...")
        time.sleep(15) # Assuming it might take a bit, or it might be small. 
        # Actually our standard route takes < 10s to build if local bbox
    
    # Ensure it's cached
    requests.post(f"{API_BASE}/api/route", json=PAYLOAD, timeout=60)
    
    stress_results = []
    
    for level in CONCURRENCY_LEVELS:
        print(f"\n[Test] Testing {level} concurrent requests...")
        threads = []
        latencies = []
        barrier = threading.Barrier(level)
        
        for _ in range(level):
            t = threading.Thread(target=send_request, args=(latencies, barrier))
            threads.append(t)
            
        for t in threads:
            t.start()
        for t in threads:
            t.join()
            
        if latencies:
            avg_lat = statistics.mean(latencies)
            p95_lat = np.percentile(latencies, 95) if 'np' in globals() else sorted(latencies)[int(len(latencies)*0.95)-1 if len(latencies)>=20 else -1]
            print(f"  -> {len(latencies)}/{level} succeeded. Avg: {avg_lat:.0f}ms, Max: {max(latencies):.0f}ms")
            stress_results.append({
                "users": level,
                "success_rate": len(latencies) / level,
                "avg_latency_ms": avg_lat,
                "max_latency_ms": max(latencies)
            })
        else:
            print("  -> All failed!")
            
    os.makedirs(RESULTS_DIR, exist_ok=True)
    out_path = os.path.join(RESULTS_DIR, "stress_test.json")
    with open(out_path, "w") as f:
        json.dump({"test_id": "T-PERF-06", "timestamp": datetime.now(timezone.utc).isoformat(), "results": stress_results}, f, indent=2)
    print(f"\nResults saved to {out_path}")

if __name__ == "__main__":
    run_benchmark()
