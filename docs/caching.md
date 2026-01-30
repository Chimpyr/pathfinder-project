# Graph Caching Architecture

The routing engine uses a **two-tier caching system**:
1. **Memory cache** (LRU) - Fast runtime lookups
2. **Disk cache** (Pickle) - Persistence across restarts

## Cache Hierarchy

```
Request → Memory Cache → Disk Cache → Full Processing
            (instant)    (~2-5s)       (~355s)
```

## How It Works

1. **Memory cache hit**: Return immediately (~1ms)
2. **Disk cache hit**: Load pickle file (~2-5s)
3. **Full miss**: Load PBF, process everything, save to disk (~355s)

## Configuration

In `config.py`:

```python
MAX_CACHED_REGIONS = 3  # Memory cache capacity
GREENNESS_MODE = 'FAST' # Also affects cache keys
```

## Disk Cache Location

```
app/data/cache/
├── cornwall_fast_v1.0.0.pickle    # Processed graph
├── bristol_fast_v1.0.0.pickle
└── manifest.json                   # Validation metadata
```

## Cache Invalidation

Disk cache invalidates automatically when:
- `CACHE_VERSION` changes (code updates)
- PBF file modified time changes
- `GREENNESS_MODE` changes

## API Methods

```python
from app.services.graph_manager import GraphManager
from app.services.cache_manager import get_cache_manager

# Get graph (uses cache automatically)
graph = GraphManager.get_graph(bbox)

# Clear memory cache
GraphManager.clear_cache()

# Clear disk cache
get_cache_manager().clear_all()

# View cache stats
get_cache_manager().get_cache_stats()
```

## Memory Considerations

| Cache Type | Typical Size |
|------------|--------------|
| Memory | 100-300 MB per region |
| Disk | 50-150 MB per pickle |

## Implementation Notes

### Cache Key Generation

Cache keys are generated from `(region_name, greenness_mode, elevation_mode, clip_bbox)`:

```python
# Key format: bristol_edge_sampling_local_bbox_a1b2c3d4_v1.5.0.pickle
base_key = f"{region}_{greenness}_{elevation}"
bbox_hash = md5("51.41_-2.61_51.57_-2.46")[:8]  # Deterministic
```

> [!IMPORTANT]
> `clip_bbox` must be computed consistently across all code paths:
> - `routes.py` (cache check before async)
> - `GraphBuilder.build_graph` (save)
> - `GraphManager.get_graph` (load)

### Known Issues (Fixed)

| Issue | Cause | Fix |
|-------|-------|-----|
| Cache miss after async build | `GraphManager` didn't pass `clip_bbox` to `is_cache_valid` | Added `clip_bbox` calculation to `get_graph()` |
| Infinite loop after cache delete | Redis task locks persisted after completion | `TaskManager` checks task state before returning locked ID |
| Admin crash on cache list | `CacheManager` used string paths | Updated to `pathlib.Path` |
