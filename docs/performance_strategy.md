# Performance Optimisation Strategy

> **Status**: ✅ Phases 1-2 Implemented (2026-01-30)  
> **Author**: Senior Engineering Review  
> **Focus**: Memory-efficient parallelism for graph processing

---

## 1. Problem Statement

Graph building for large regions (e.g., Somerset: 1.1M nodes, 2.3M edges) exhibited:

| Metric | Before | After (Phase 1-2) |
|--------|--------|-------------------|
| Build time | ~15 minutes | **~73 seconds** |
| Cache load time | ~54 seconds | **~2 seconds** |
| Memory usage | 12-14 GB | **~1 GB** |
| Worker concurrency | 1 | **4** |
| Nodes loaded (Bath) | 1,114,246 | **62,581** |

**Key insight**: Memory was the primary bottleneck, not CPU. Adding workers without addressing memory caused OOM failures.

---

## 2. Root Cause Analysis

### 2.1 Memory Consumption Breakdown

| Stage | Memory Impact | Cause |
|-------|---------------|-------|
| PBF parsing | ~4 GB | Entire county loaded into pyrosm |
| NetworkX graph | ~6 GB | 2.3M edges with 10+ attributes each |
| Scenic scoring | ~2 GB | Shapely STRtree for spatial queries |
| Pickle cache | ~2 GB on disk | Full graph serialised |
| **Total peak** | **~12-14 GB** | |

### 2.2 Why Simple Parallelism Didn't Work

```
Before: 1 worker × 12 GB = 12 GB required
Naive:  2 workers × 12 GB = 24 GB required ❌ OOM
After:  4 workers × 1 GB = 4 GB required ✅
```

**Solution**: Reduce per-task memory via bbox clipping before scaling workers.

---

## 3. Implementation Summary

### Phase 1: Bounding Box Clipping ✅

**Objective**: Only load graph data within the route's bounding box + 5km buffer.

**Implementation**:
```python
# OSMDataLoader.load_graph()
osm = OSM(pbf_path, bounding_box=[min_lon, min_lat, max_lon, max_lat])
nodes, edges = osm.get_network(network_type="walking")
```

**Verified Results**:

| Metric | Before | After |
|--------|--------|-------|
| Nodes loaded (Bath route) | 1,114,246 | **62,581** |
| Memory usage | 12 GB | **~1 GB** |
| Build time | 15 min | **73 sec** |
| Cache file size | ~2 GB | **~100 MB** |

**Cache Key Strategy**:
- Includes MD5 hash of rounded bbox (0.01 degree precision ≈ 1km)
- Example: `somerset_edge_sampling_local_bbox_99603911_v1.5.0.pickle`

---

### Phase 2: Worker Concurrency ✅

**Change**: `--concurrency=1` → `--concurrency=4` in docker-compose.yml

**Verification**: Two simultaneous builds tested:
- `ForkPoolWorker-1`: Oxford (65,222 nodes, 77s)
- `ForkPoolWorker-3`: Bath (62,001 nodes, 74s)

Both completed without OOM or resource contention.

---

### Phase 3: Within-Task Parallelism (Deferred)

**Status**: Not implemented - marginal gains with smaller graphs.

With bbox clipping reducing graphs to ~60K nodes, edge scoring takes ~30-50s. Parallelising this would add complexity for minimal gain (~15-25s savings).

**Recommended only if**:
- Routes regularly exceed 20km
- Build time >2 minutes becomes common

---

## 4. Decision Matrix

| Enhancement | Impact | Effort | Memory Reduction | Status |
|-------------|--------|--------|------------------|--------|
| Bbox clipping | High | Medium | ~95% | ✅ Done |
| Worker concurrency | Medium | Low | N/A (enables scaling) | ✅ Done |
| Within-task parallelism | Low-Medium | High | 0% | Deferred |

---

## 5. Issues Encountered

### Bug: Cache Key Mismatch

**Symptom**: Routes returned 202 (processing) even when cache existed.

**Root Cause**: Inconsistent clip_bbox calculation:
- `routes.py` calculated from raw start/end coordinates
- `graph_builder.py` calculated from buffered bbox

The MD5 hashes differed, so cache lookup failed.

**Fix**: Both files now calculate clip_bbox from the same source (buffered bbox).

See [ADR-004](decisions/ADR-004-bbox-clipping.md) for full details.

---

## 6. Files Modified

| File | Changes |
|------|---------|
| `OSMDataLoader.load_graph()` | Added `clip_bbox` parameter |
| `GraphBuilder.build_graph()` | Added `clip_to_bbox` parameter, 5km buffer calculation |
| `CacheManager` | Bbox-aware cache keys |
| `routes.py` | Clip_bbox calculation for cache lookup |
| `docker-compose.yml` | `--concurrency=4` |

---

## 7. Testing

See [Docker Testing Guide](guides/docker_testing.md) for:
- Concurrent worker testing with curl
- Cache management commands
- Troubleshooting common issues

---

## 8. Final Metrics

| Metric | Original | Target | Achieved |
|--------|----------|--------|----------|
| Avg build time (5km route) | 15 min | <2 min | **73 sec** ✅ |
| Cache load time | 54 sec | <5 sec | **~2 sec** ✅ |
| Concurrent builds | 1 | 4 | **4** ✅ |
| Memory per build | 12 GB | <4 GB | **~1 GB** ✅ |

---

## 9. References

- [ADR-004: Bbox Clipping](decisions/ADR-004-bbox-clipping.md)
- [Celery Redis Architecture](celery_redis_architecture.md)
- [Docker Testing Guide](guides/docker_testing.md)
