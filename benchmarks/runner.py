"""
Benchmark Runner

Executes multiple benchmarks sequentially.
Can run all benchmarks or a specific subset based on arguments.
Logs all outputs to a combined text results file for background automation,
while individual benchmarks continue to output their own specific JSONs.

Usage:
    docker compose exec api python -m benchmarks.runner --all
    docker compose exec api python -m benchmarks.runner -b route extraction
"""

import argparse
import subprocess
import sys
import os
import time
from datetime import datetime, timezone

# Benchmarks available in the module
AVAILABLE_BENCHMARKS = [
    "benchmark_route",
    "benchmark_graph_build",
    "benchmark_memory",
    "benchmark_concurrency",
    "benchmark_extraction",
    "benchmark_loop",
    "benchmark_pruning",
    "benchmark_wsm",
]

RESULTS_DIR = os.path.join(os.path.dirname(__file__), "results")

def main():
    parser = argparse.ArgumentParser(description="Sequential Benchmark Runner")
    parser.add_argument("--all", action="store_true", help="Run all available benchmarks")
    parser.add_argument("-b", "--benchmarks", nargs="+", choices=AVAILABLE_BENCHMARKS, help="Specific benchmarks to run")
    parser.add_argument("--output", type=str, help="Output log file name (saved in results/)", default=None)
    parser.add_argument("-v", "--visualise", action="store_true", help="Automatically run visualise_results.py afterwards")
    
    args = parser.parse_args()

    # Allow --visualise to run standalone (no benchmarks required)
    if not args.all and not args.benchmarks and not args.visualise:
        parser.error("Must specify --all, -b/--benchmarks, and/or -v/--visualise.")

    to_run = AVAILABLE_BENCHMARKS if args.all else (args.benchmarks or [])
    
    # Ensure results directory exists
    os.makedirs(RESULTS_DIR, exist_ok=True)
    
    # Setup logging
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    log_filename = args.output if args.output else f"runner_log_{timestamp}.txt"
    log_path = os.path.join(RESULTS_DIR, log_filename)

    with open(log_path, "w", encoding="utf-8") as f:
        f.write(f"Benchmark Runner Started at {timestamp}\n")
        f.write(f"Benchmarks to run: {', '.join(to_run)}\n")
        f.write("=" * 60 + "\n\n")

    print(f"Starting Benchmark Runner. Logging to {log_path}")
    
    total_start = time.perf_counter()
    success_count = 0

    if to_run:
        print(f"Benchmarks to run: {', '.join(to_run)}")
        # Execute benchmarks sequentially
        for idx, bench in enumerate(to_run, 1):
            print(f"\n[{idx}/{len(to_run)}] Running {bench}...")
            
            start_time = time.perf_counter()
            
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"--- START: {bench} at {datetime.now(timezone.utc).isoformat()} ---\n")
                
            # Run as a subprocess to ensure isolation and capture stdout/stderr
            process = subprocess.run(
                [sys.executable, "-m", f"benchmarks.{bench}"],
                capture_output=True,
                text=True
            )
            
            elapsed = time.perf_counter() - start_time
            
            with open(log_path, "a", encoding="utf-8") as f:
                # Append standard output
                if process.stdout:
                    f.write(process.stdout)
                    if not process.stdout.endswith("\n"):
                        f.write("\n")
                
                # Append standard error if any
                if process.stderr:
                    f.write("\nSTDERR:\n")
                    f.write(process.stderr)
                    if not process.stderr.endswith("\n"):
                        f.write("\n")
                
                status = "SUCCESS" if process.returncode == 0 else "FAILED"
                f.write(f"--- END: {bench} ({status} in {elapsed:.2f}s) ---\n\n")
                
            if process.returncode == 0:
                print(f"  -> Completed successfully in {elapsed:.2f}s.")
                success_count += 1
            else:
                print(f"  -> Failed with return code {process.returncode} in {elapsed:.2f}s. Check log for details.")

        total_elapsed = time.perf_counter() - total_start
        
        summary = (
            f"Runner Completed in {total_elapsed:.2f}s.\n"
            f"Successful: {success_count}/{len(to_run)}\n"
        )
        
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("=" * 60 + "\n")
            f.write(summary)
            
        print("\n" + "=" * 60)
        print(summary.strip())
        print(f"Full log available at: {log_path}")
    
    # Trigger visualisation if requested
    if args.visualise:
        print("\n" + "=" * 60)
        print("Triggering Visualisation Generation...")
        subprocess.run(
            [sys.executable, "-m", "benchmarks.visualise_results"],
        )

if __name__ == "__main__":
    main()
