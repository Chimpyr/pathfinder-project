# Elevation Data Feature

Adds satellite elevation data to graph nodes and calculates edge gradients for terrain-aware routing.

---

## Overview

The elevation processor fetches Digital Elevation Model (DEM) data from the **Open Topo Data API** and calculates gradients for each road segment. This enables the WSM A* algorithm to factor in terrain difficulty when calculating routes.

---

## Data Source

| Dataset | Resolution | Coverage | Provider |
|---------|------------|----------|----------|
| ASTER Global DEM | ~30m | Global | Open Topo Data API |

The ASTER dataset is comparable to AW3D30 and SRTM in resolution and accuracy.

---

## Configuration

```python
# config.py
ELEVATION_MODE = 'FAST'  # Options: 'OFF', 'FAST'
```

| Mode | Description | Performance |
|------|-------------|-------------|
| `OFF` | Skip elevation processing | Fastest |
| `FAST` | Fetch from Open Topo Data API | ~30-60s for large graphs |

---

## Edge Attribute

After processing, each edge has a `raw_slope_cost` attribute:

```python
edge = G[node_u][node_v][0]
edge['raw_slope_cost']  # 0.0 = flat, 0.1 = 10% grade
```

**Formula:**
```
raw_slope_cost = |elevation_v - elevation_u| / length
```

Uses absolute value because both uphill and downhill can be undesirable for walking routes.

---

## API Details

| Property | Value |
|----------|-------|
| Endpoint | `https://api.opentopodata.org/v1/aster30m` |
| Batch size | 100 locations per request |
| Rate limits | ~1000 requests/minute |
| Authentication | None required |

---

## Cache Behaviour

The disk cache includes `elevation_mode` in the cache key:
```
cornwall_fast_fast_v1.0.0.pickle
         ^--- greenness_mode
              ^--- elevation_mode
```

Changing `ELEVATION_MODE` will trigger reprocessing on the next request.

---

## Performance

| Graph Size | Elevation Processing Time |
|------------|--------------------------|
| Small (~10k edges) | ~5-10s |
| Medium (~100k edges) | ~15-30s |
| Large (1M+ edges) | ~45-90s |

Times depend on API response latency and are cached after first processing.

---

## Future Enhancements

- **RASTER mode**: Local DEM file support for offline processing
- **Directional gradients**: Separate uphill/downhill costs
- **Route elevation profile**: Visualise elevation changes along route
