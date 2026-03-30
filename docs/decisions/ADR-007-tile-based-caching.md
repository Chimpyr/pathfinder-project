# ADR-007: Tile-Based Graph Caching

**Status:** Accepted  
**Date:** 2026-02-08  
**Supersedes:** [ADR-004](./ADR-004-bbox-clipping.md) (Bounding Box Clipping)

---

## Context

ADR-004 introduced per-route bounding box clipping to reduce memory usage from full-county graph builds (~12 GB) to route-specific subgraphs (~1 GB). However, this created a cache fragmentation problem.

### The Problem

| Scenario                            | Cache Key        | Result                |
| ----------------------------------- | ---------------- | --------------------- |
| Stoke Park → Fishponds              | `hash(bbox_abc)` | Build graph (~70s)    |
| Stoke Park → Staple Hill (1km away) | `hash(bbox_def)` | Build again (~70s) ❌ |

Even though these routes share 90%+ of the same area, different bounding boxes produce different cache keys, triggering unnecessary rebuilds.

### User Impact

- **Poor UX**: Users exploring an area trigger repeated ~70 second builds
- **Wasted computation**: Same roads processed multiple times
- **Cache bloat**: Many overlapping cache files

---

## Decision

**Replace per-route bbox clipping with snap-to-grid tiles.**

Routes are mapped to standardised tiles (e.g., 15km × 15km) instead of unique bounding boxes. Tiles that are already cached are reused; only missing tiles are built.

### Key Concepts

```
Grid Tiles (15km each):
┌─────────────┬─────────────┐
│ Tile        │ Tile        │
│ 51.45,-2.70 │ 51.45,-2.55 │
├─────────────┼─────────────┤
│ Tile        │ Tile        │
│ 51.30,-2.70 │ 51.30,-2.55 │
└─────────────┴─────────────┘

Route A: Uses tile 51.45,-2.55 → Build, cache ✓
Route B: Also uses 51.45,-2.55 → Cache hit ✓
Route C: Crosses two tiles → Merge cached tiles ✓
```

### Implementation

1. **Tile calculation** (`tile_utils.py`): Snap coordinates to grid, enumerate tiles for route
2. **Tile-based cache keys**: `region_tile_51.45_-2.55_v1.5.0.pickle`
3. **Incremental building**: Only build tiles not in cache
4. **Graph merging**: `nx.compose()` joins overlapping tiles via shared OSM node IDs

```python
# Example: Get graph for route using tiles
graph = GraphManager.get_graph_for_route(start_point, end_point)
```

---

## Configuration

```python
# config.py
TILE_SIZE_KM = 30        # Size of each tile (30km covers greater Bristol area)
TILE_OVERLAP_KM = 2      # Buffer for boundary connectivity
PREWARM_TILES = []       # Optional: Pre-build tiles on startup
```

---

## Consequences

### Positive

- **Cache reuse**: Nearby routes share tiles, eliminating redundant builds
- **Predictable tiles**: Deterministic cache keys from grid coordinates
- **Incremental building**: Only missing tiles are built for cross-tile routes
- **Memory bounded**: Each tile ~2-3 GB, predictable resource usage

### Negative

- **Tile boundaries**: Routes near tile edges may need 2+ tiles
- **Initial build**: First request to new tile still takes ~2-3 minutes
- **Merge overhead**: Cross-tile routes require graph composition (~0.5s)

### Trade-offs Accepted

| Metric             | ADR-004 (bbox)  | ADR-007 (tiles)     |
| ------------------ | --------------- | ------------------- |
| Cache reuse        | Poor            | Excellent           |
| Build time (cold)  | ~70s per route  | ~2-3 min per tile   |
| Build time (warm)  | Miss every time | Instant (cache hit) |
| Memory per request | ~1 GB           | ~2-3 GB per tile    |

---

## Files Modified

| File               | Changes                                                  |
| ------------------ | -------------------------------------------------------- |
| `config.py`        | Added `TILE_SIZE_KM`, `TILE_OVERLAP_KM`, `PREWARM_TILES` |
| `tile_utils.py`    | New module for tile grid calculations                    |
| `cache_manager.py` | Added `tile_id` parameter to cache methods               |
| `graph_manager.py` | Added `get_graph_for_route()` with tile merging          |
| `routes.py`        | Updated to use tile-based API                            |

---

## References

- [ADR-004: Bounding Box Clipping](./ADR-004-bbox-clipping.md) (superseded)
- [Performance Strategy](../architecture/performance_strategy.md)
