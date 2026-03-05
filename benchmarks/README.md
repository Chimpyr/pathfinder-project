# Benchmarks

Performance benchmark scripts for the Scenic Pathfinding Engine. These scripts are designed to be run **inside the Docker container** to produce empirical data for the report.

## Usage

All benchmarks should be run from inside the `scenic-api` container:

```bash
# Route computation latency (T-PERF-01 / NFR-01)
docker compose exec api python -m benchmarks.benchmark_route

# Graph build timing (T-PERF-02 / NFR-02)
docker compose exec api python -m benchmarks.benchmark_graph_build

# Memory usage comparison (T-PERF-03 / NFR-05)
docker compose exec api python -m benchmarks.benchmark_memory

# Concurrent tile lock verification (T-REL-01 / NFR-03)
docker compose exec api python -m benchmarks.benchmark_concurrency
```

## Output

Each benchmark prints results to stdout and optionally writes a JSON summary to `benchmarks/results/` for inclusion in the report appendix.
