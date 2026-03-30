# ADR-004: Bounding Box Clipping for Graph Loading

**Status:** Superseded by [ADR-007](./ADR-007-tile-based-caching.md)  
**Date:** 2026-01-30

> [!NOTE]
> This approach has been superseded by tile-based caching (ADR-007) which provides better cache reuse for nearby routes while maintaining the memory benefits described here.

---

## Context

The ScenicPathFinder async graph building pipeline faced critical memory constraints that blocked worker scaling.

### The Problem

| Metric         | Full-Region Load            | Impact                  |
| -------------- | --------------------------- | ----------------------- |
| Somerset PBF   | 1,114,246 nodes, 2.3M edges | ~12 GB RAM per build    |
| Build time     | ~15 minutes                 | Poor UX for cold starts |
| Worker scaling | OOM at 2 workers            | Cannot parallelise      |

With each graph build consuming ~12 GB of RAM, running even 2 concurrent Celery workers exceeded typical Docker memory limits. This fundamentally limited the system's ability to handle multiple simultaneous route requests to different regions.

### Root Cause

The entire county PBF file was being loaded and parsed, even when the user only needed a small route within that county (e.g., a 2km walk in Bath loads all of Somerset).

---

## Decision

**Clip graph loading to a buffered bounding box around the route.**

### Implementation

1. **Calculate clip_bbox**: Route's bounding box + 5km buffer
2. **Pass to pyrosm**: `OSM(pbf_path, bounding_box=[min_lon, min_lat, max_lon, max_lat])`
3. **Per-route caching**: Include bbox hash in cache key

```python
# In graph_builder.py
buffer_km = 5
buffer_deg = buffer_km / 111.0  # ~0.045 degrees per km
clip_bbox = (
    bbox[0] - buffer_deg,  # min_lat
    bbox[1] - buffer_deg,  # min_lon
    bbox[2] + buffer_deg,  # max_lat
    bbox[3] + buffer_deg   # max_lon
)

# Pass to pyrosm
osm = OSM(pbf_path, bounding_box=[clip_bbox[1], clip_bbox[0], clip_bbox[3], clip_bbox[2]])
```

### Cache Key Strategy

Cache keys include a hash of the rounded clip_bbox (rounded to 0.01 degrees ≈ 1km):

```python
# Example cache key
somerset_edge_sampling_local_bbox_99603911_v1.5.0.pickle
#                                ^^^^^^^^ MD5 hash of rounded bbox
```

This enables per-route caching while allowing cache reuse for nearby routes.

---

## Verified Results

| Metric                  | Before       | After      | Improvement    |
| ----------------------- | ------------ | ---------- | -------------- |
| Node count (Bath route) | 1,114,246    | **62,581** | 95% reduction  |
| Build time              | ~15 min      | **73 sec** | 12× faster     |
| Memory per build        | ~12 GB       | **~1 GB**  | ~90% reduction |
| Concurrent workers      | 1 (OOM at 2) | **4**      | 4× capacity    |

---

## Consequences

### Positive

- **Enables worker scaling**: 4 concurrent builds stay within 8GB Docker limit
- **Faster cold starts**: 73 seconds vs 15 minutes
- **Smaller cache files**: ~100 MB vs ~2 GB per cache entry
- **Simple implementation**: ~50 lines of code across 4 files

### Negative

- **Cache fragmentation**: Different routes create different cache entries
- **Buffer sensitivity**: Routes near bbox boundary may fail pathfinding (mitigated by 5km buffer)
- **Reduced cache reuse**: Nearby but not identical routes won't share cache

---

## Issues Encountered

### Bug: Cache Key Mismatch

**Symptom**: After graph build completed, subsequent requests to same route returned 202 (cache miss) instead of using cached graph.

**Root cause**: Inconsistent clip_bbox calculation:

- `routes.py` calculated clip_bbox from raw start/end coordinates
- `graph_builder.py` calculated clip_bbox from bbox (which had 0.02 buffer)

The cache lookup used different coordinates than the cache save, producing different MD5 hashes.

**Fix**: Both files now calculate clip_bbox from the buffered bbox, not raw coordinates.

```python
# CORRECT (both files use this)
clip_bbox = (
    bbox[0] - clip_buffer_deg,  # From bbox, not raw coords
    bbox[1] - clip_buffer_deg,
    bbox[2] + clip_buffer_deg,
    bbox[3] + clip_buffer_deg
)
```

---

## Files Modified

| File                                                  | Changes                                               |
| ----------------------------------------------------- | ----------------------------------------------------- |
| `OSMDataLoader.load_graph()`                          | Added `clip_bbox` parameter, passes to pyrosm         |
| `GraphBuilder.build_graph()`                          | Added `clip_to_bbox` parameter, calculates 5km buffer |
| `CacheManager._get_cache_key()`                       | Added optional `bbox` parameter for hash              |
| `CacheManager.is_cache_valid/load_graph/save_graph()` | Accept and pass `bbox` parameter                      |
| `routes.py`                                           | Calculates clip_bbox for cache lookup                 |
| `docker-compose.yml`                                  | Increased `--concurrency=1` to `--concurrency=4`      |

---

## Testing Validation

Concurrent build test:

1. Oxford route: `ForkPoolWorker-1` - 65,222 nodes, 77s build time
2. Bath route: `ForkPoolWorker-3` - 62,001 nodes, 74s build time
3. Both completed successfully without OOM

---

## References

- [Performance Strategy](../architecture/performance_strategy.md)
- [Celery Redis Architecture](../architecture/celery_redis_architecture.md)
- [Testing Guide](../guides/docker_testing.md)
