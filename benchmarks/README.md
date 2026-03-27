# Benchmarks

Performance benchmark scripts for the Scenic Pathfinding Engine. These scripts are designed to be run **inside the Docker container** to produce empirical data for the report.

## Usage

All benchmarks are designed to be run from inside the `scenic-api` container.

### Sequential Benchmark Runner

To automate the execution of multiple benchmarks and log their output sequentially to a text file (saved in `benchmarks/results/`), use the `runner.py` script:

```bash
# Run all benchmarks sequentially
docker compose exec api python -m benchmarks.runner --all

# Run specific benchmarks
docker compose exec api python -m benchmarks.runner -b benchmark_route benchmark_extraction benchmark_pruning
```

### Individual Benchmarks

You can also run individual benchmarks:

```bash
# Route computation latency (T-PERF-01 / NFR-01)
docker compose exec api python -m benchmarks.benchmark_route

# Graph build timing (T-PERF-02 / NFR-02)
docker compose exec api python -m benchmarks.benchmark_graph_build

# Memory usage comparison (T-PERF-03 / NFR-05)
docker compose exec api python -m benchmarks.benchmark_memory

# Concurrent tile lock verification (T-REL-01 / NFR-03)
docker compose exec api python -m benchmarks.benchmark_concurrency

# Extraction method comparison (T-PERF-04)
docker compose exec api python -m benchmarks.benchmark_extraction

# Loop solver performance (T-PERF-05 / FR-03)
docker compose exec api python -m benchmarks.benchmark_loop

# Graph pruning verification (T-ENG-03 / FR-09)
docker compose exec api python -m benchmarks.benchmark_pruning

# Water proximity scoring verification (T-ENG-09 / FR-01)
docker compose exec api python -m benchmarks.benchmark_water
```

## Script Summary

| Script                     | Test ID                                          | Requirement         | What It Measures                                                                                       |
| -------------------------- | ------------------------------------------------ | ------------------- | ------------------------------------------------------------------------------------------------------ |
| `benchmark_route.py`       | T-PERF-01                                        | NFR-01              | Route latency (min/max/mean/p95 over 30 iterations)                                                    |
| `benchmark_graph_build.py` | T-PERF-02                                        | NFR-02              | Graph build time + per-stage breakdown                                                                 |
| `benchmark_memory.py`      | T-PERF-03                                        | NFR-05              | Peak process RSS with/without BBox clipping                                                            |
| `benchmark_concurrency.py` | T-REL-01                                         | NFR-03              | Redis lock prevents duplicate builds (barrier-synchronised)                                            |
| `benchmark_extraction.py`  | T-PERF-04                                        | —                   | Point Buffer vs Edge Sampling vs Isovist timing                                                        |
| `benchmark_loop.py`        | T-PERF-05                                        | FR-03               | Loop convergence, timing, accuracy, self-intersection                                                  |
| `benchmark_pruning.py`     | T-ENG-03                                         | FR-09               | Walking filter verification (scripted, not manual)                                                     |
| `benchmark_wsm.py`         | T-ENG-01, T-ENG-04, T-ENG-05, T-ENG-06, T-ENG-07 | FR-01, FR-10, FR-14 | WSM mathematical efficacy and path geometry distinctness                                               |
| `benchmark_water.py`       | T-ENG-09                                         | FR-01               | Water proximity scoring: 100% edge coverage, [0,1] range, riverside < inland mean score (Bristol Avon) |

## Output

Each benchmark prints results to stdout and writes a JSON summary to `benchmarks/results/` for inclusion in the report appendix. All JSON files include an ISO 8601 timestamp.

## Visualisations

The JSON outputs can be directly converted into academic, publication-ready graphs mapping to the `REPORT.md` arguments.
To do this, ensure the visualisation dependencies are installed (these are separate from the core API dependencies):

```bash
pip install -r benchmarks/requirements-vis.txt
```

You can then run the visualiser standalone or passing the `-v` flag to the runner:

```bash
# Standalone
python -m benchmarks.visualise_results

# Execute sequentially and visualise afterwards
docker compose exec api python -m benchmarks.runner --all -v
```

This will save `.png` plots to `benchmarks/visualisations/`.

## Notes

- Scripts importing application code (`benchmark_graph_build`, `benchmark_memory`, `benchmark_extraction`, `benchmark_pruning`) require the Flask application context and must be run inside the Docker container.
- Scripts using the HTTP API (`benchmark_route`, `benchmark_concurrency`, `benchmark_loop`) can be run from any host with network access to the API.
- Install `psutil` in the container for accurate RSS memory measurements (falls back to `resource.getrusage` on Linux).
