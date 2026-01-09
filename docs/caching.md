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

