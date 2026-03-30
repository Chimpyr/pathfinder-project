# 5. Extraction Methodologies Benchmark

**Section:** Performance Optimisation and Efficiency Testing  
**Format:** Empirical Benchmark Chart (Bar Chart)

## What it should include:

A visual comparison chart of the three algorithmic extraction logic methods your system prototyped:

1. **Point Buffer (Base):** Value at ~30 seconds. (Colour this red or grey to show it is mathematically flawed and discarded).
2. **Edge Geometry Sampling (Selected):** Value at ~73 seconds (1-2 minutes). (Colour this green to show it is your optimal selection).
3. **Novack Isovist Ray-Casting (Reference):** Value at ~10+ minutes (600+ seconds). (Colour this red or grey to show it breaks real-time Web API latency limits).

## Data Required & Where to Find it:

- **The ADRs:** `docs/decisions/ADR-002-greenness-detection-method.md`
- **The Docs:** `docs/greenness_methods_comparison.md`
- **The Benchmark Script:** [`benchmarks/benchmark_extraction.py`](../../benchmarks/benchmark_extraction.py) — **already implemented**
- **The Visualiser:** [`benchmarks/visualise_results.py`](../../benchmarks/visualise_results.py) — generates charts from benchmark JSON output

## Implementation Status: ✅ SCRIPT EXISTS

The benchmark script is **already implemented** at `benchmarks/benchmark_extraction.py`. It:

- Uses the `get_processor()` factory to obtain `FAST` and `EDGE_SAMPLING` processor instances
- Times each on a Bristol bounding box (51.42, -2.65, 51.48, -2.55) with ~325,000 edges
- Records a reference entry for Novack Isovist (not executed — too slow for production)
- Outputs JSON results to `benchmarks/results/`

**To generate the chart:**

```bash
# Run the benchmark (requires Flask app context + cached .pbf data)
docker compose exec api python -m benchmarks.benchmark_extraction

# Generate visualisation from results
docker compose exec api python -m benchmarks.visualise_results
```

See also: [`benchmarks/README.md`](../../benchmarks/README.md) for full usage instructions.

## What it Proves & Why it is Positive:

The highest grading band demands **"empirical observation"** and **"testing"**. This chart acts as visual proof that your final architecture (`EDGE_SAMPLING`) wasn't a guess—it was a highly engineered, mathematically measured compromise between the reckless speed of Point Buffering and the extreme latency of Novack Isovists. It proves you benchmark systems like a senior engineer.
