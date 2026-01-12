# Elevation Data Feature

Adds satellite elevation data to graph nodes and calculates edge gradients for terrain-aware routing.

---

## Overview

The elevation processor fetches Digital Elevation Model (DEM) data and calculates gradients for each road segment. This enables the WSM A* algorithm to factor in terrain difficulty when calculating routes.

Two modes are available:
- **API**: Remote lookups via Open Topo Data (slower, no storage needed)
- **LOCAL**: Fast lookups from downloaded Copernicus GLO-30 tiles

---

## Data Sources

| Mode | Dataset | Resolution | RMSE | Provider |
|------|---------|------------|------|----------|
| `API` | ASTER Global DEM | ~30m | ~8m | Open Topo Data API |
| `LOCAL` | Copernicus GLO-30 | ~30m | ~4m | AWS Open Data (no API key!) |

The LOCAL mode uses Copernicus GLO-30 from the [AWS Open Data Registry](https://registry.opendata.aws/copernicus-dem/), which has the best vertical accuracy (~4m RMSE) among freely available 30m DEMs. **No API key is required** - tiles are downloaded directly from AWS S3.

---

## Configuration

```python
# config.py
ELEVATION_MODE = 'LOCAL'  # Options: 'OFF', 'API', 'LOCAL'
```

| Mode | Description | Performance | Storage |
|------|-------------|-------------|---------|
| `OFF` | Skip elevation processing | Fastest | None |
| `API` | Fetch from Open Topo Data API | ~30-60s | None |
| `LOCAL` | Download Copernicus GLO-30 tiles | ~1-3s | ~25MB per tile |

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

## LOCAL Mode Details

### Tile Management

- Tiles are 1°×1° GeoTIFF files (~25MB each)
- Downloaded automatically on first use for each region
- Stored in `app/data/dem/` directory
- Loaded into memory for fast batch lookups

### First Run Behaviour

On first request for a new region:
1. Required tiles are identified from the graph bounding box
2. Missing tiles are downloaded from OpenTopography
3. Tiles are cached locally for subsequent requests

### Storage Requirements

| Coverage | Approximate Storage |
|----------|---------------------|
| Single UK city | ~25MB (1 tile) |
| UK-wide | ~500MB-1GB |
| Global | Not recommended for bulk download |

---

## API Mode Details

| Property | Value |
|----------|-------|
| Endpoint | `https://api.opentopodata.org/v1/aster30m` |
| Batch size | 100 locations per request |
| Rate limits | 1 request/second (free tier) |
| Authentication | None required |

---

## Cache Behaviour

The disk cache includes `elevation_mode` in the cache key:
```
cornwall_fast_local_v1.0.0.pickle
         ^--- greenness_mode
              ^--- elevation_mode
```

Changing `ELEVATION_MODE` will trigger reprocessing on the next request.

---

## Performance Comparison

| Mode | First Run (new region) | Subsequent Runs |
|------|------------------------|-----------------|
| OFF | 0s | 0s |
| API | ~30-60s | ~30-60s |
| LOCAL | ~10-15s (with download) | ~1-3s |

LOCAL mode is **10-30× faster** for subsequent requests after tiles are downloaded.

---

## Future Enhancements

- **Directional gradients**: Separate uphill/downhill costs for more realistic walking effort
- **Route elevation profile**: Visualise elevation changes along the calculated route
- **Alternative datasets**: Support for UK Environment Agency LiDAR (1m resolution)
