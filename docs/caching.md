# Graph Caching Architecture

The routing engine uses an **LRU (Least Recently Used) cache** to store multiple region graphs efficiently.

## Overview

When a route query arrives, the system:
1. Identifies which OSM region the query falls within
2. Checks if that region's graph is already cached
3. **Cache hit**: Returns cached graph immediately
4. **Cache miss**: Loads graph, caches it, evicts oldest if at capacity

## Configuration

In `config.py`:

```python
MAX_CACHED_REGIONS = 3  # Number of regions to keep in memory
```

Higher values use more RAM but reduce reload frequency for multi-region routing.

## Cache Behaviour

| Scenario | Action | Performance |
|----------|--------|-------------|
| Same region as last query | Cache hit | Instant |
| Different region, not cached | Load + cache | ~30-60s |
| Cache full | Evict oldest, load new | ~30-60s |

## API Methods

```python
from app.services.graph_manager import GraphManager

# Get graph (uses cache automatically)
graph = GraphManager.get_graph(bbox)

# Check cache state
info = GraphManager.get_cache_info()
# {'cached_regions': ['bristol', 'london'], 'cache_size': 2, 'max_regions': 3}

# Clear all cached graphs
GraphManager.clear_cache()

# Get timing breakdown
timings = GraphManager.get_timings()
```

## Memory Considerations

Each cached graph uses approximately:
- **100-300 MB** for a city-sized region (e.g., Bristol)
- **1-3 GB** for a country-sized region (e.g., England)

Set `MAX_CACHED_REGIONS` according to available device or server memory.
