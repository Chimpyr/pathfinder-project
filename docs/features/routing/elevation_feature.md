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

## Edge Attributes

After processing, each edge has the following slope-related attributes:

| Attribute | Type | Description |
|-----------|------|-------------|
| `uphill_gradient` | float | Gradient when going uphill (0 if downhill/flat) |
| `downhill_gradient` | float | Gradient when going downhill (0 if uphill/flat) |
| `slope_time_cost` | float | Tobler cost multiplier (1.0 = flat terrain) |
| `raw_slope_cost` | float | Absolute gradient (backwards compatibility) |

```python
edge = G[node_u][node_v][0]
edge['slope_time_cost']   # 1.0 = flat, 0.83 = mild downhill, 1.85 = 10% uphill
edge['uphill_gradient']   # 0.1 = 10% uphill grade
edge['downhill_gradient'] # 0.1 = 10% downhill grade
```

---

## Tobler's Hiking Function

The `slope_time_cost` attribute uses **Tobler's hiking function**, an empirically-validated model for walking speed on sloped terrain.

### Why Tobler's Function?

Evaluated three approaches:

| Approach | Accuracy | Complexity | Pros & Cons |
|----------|----------|------------|-------------|
| **Signed Gradient** | Medium | Low | Simple but treats 20% downhill as "easy" |
| **Tobler's Function** | High | Medium | Captures non-linear effort, well-documented |
| **Metabolic Cost Model** | Highest | High | Requires J/kg/m units, too complex for consumer apps |

**Tobler wins because:**
1. **Scientifically grounded** Based on Swiss military walking data (Eduard Imhof, 1920s)
2. **Captures reality** Mild downhill is *faster* than flat; steep downhill is *slower*
3. **Widely used** Implemented in QGIS, ArcGIS, and terrain routing algorithms
4. **Running-compatible** Same formula works for running with different parameters

### The Formula

```python
speed = max_speed × exp(-decay_rate × |gradient - optimal_grade|)
cost_multiplier = flat_speed / speed
```

For walking:
- `max_speed = 6.0 km/h` (on optimal downhill)
- `flat_speed = 5.0 km/h`  
- `decay_rate = 3.5`
- `optimal_grade = -0.05` (5% downhill)

### Cost Multiplier Values

| Gradient | Description | Speed (km/h) | Cost Multiplier |
|----------|-------------|--------------|-----------------|
| -5% | Mild downhill (optimal) | **6.0** | **0.83** |
| 0% | Flat terrain | 5.0 | 1.00 |
| +5% | Gentle uphill | 3.7 | 1.35 |
| +10% | Moderate uphill | 2.7 | 1.85 |
| +20% | Steep uphill | 1.5 | 3.33 |
| -20% | Steep downhill | 1.5 | 3.33 |

> **Note**: The function is *not* symmetric. Mild downhill is actually easier than flat terrain because gravity assists forward momentum. But steep downhill becomes hard again due to braking forces on knees.

---

## Understanding the Debug Display

When hovering over route segments, you'll see elevation data like:

```
📍 62.6m → 58.9m (-3.7m)
⏱️ Tobler: 2.097×
```

### What This Means

| Display | Interpretation |
|---------|----------------|
| `62.6m → 58.9m` | Start elevation → End elevation (metres above sea level) |
| `(-3.7m)` | You're going **downhill** by 3.7 metres on this segment |
| `Tobler: 2.097×` | This segment takes **2× longer** than flat terrain |

### Why Might Downhill Be "Slow"?

A Tobler cost > 1.0 on a downhill segment indicates a **steep descent**:

```
gradient = elevation_change / edge_length
```

**Example:** A 3.7m drop over a 20m edge = **18.5% downhill gradient**

At 18.5% gradient, you'd walk at ~1.7 km/h (bracing against gravity, protecting knees), compared to 5 km/h on flat terrain. Hence **2× slower**.

### Quick Reference

| Tobler Value | What It Means | Gradient Range |
|--------------|---------------|----------------|
| **0.83-0.95** | Faster than flat (mild downhill) | -2% to -8% |
| **1.0** | Flat terrain baseline | ~0% |
| **1.2-1.5** | Gentle incline | 5-10% |
| **1.5-2.5** | Noticeable climb or steep descent | 10-20% |
| **2.5+** | Very steep (stairs, rocky paths) | 20%+ |

### Real-World Examples

| Scenario | Typical Tobler Cost |
|----------|---------------------|
| Flat pavement | 1.0× |
| Gentle park path | 0.9-1.1× |
| Hilly street | 1.3-1.8× |
| Steep steps | 2.5-4.0× |

---

## User Preference Slider

The slope preference slider controls how much the A* algorithm penalises terrain:

```
Slope Preference
[Flat routes] ─────●───── [Any terrain]
```

- **Slider at left** → Strongly avoids hills in either direction
- **Slider at right** → Ignores slope entirely

The slider applies a weight to the Tobler cost:

```python
cost = length × (1 + slope_weight × (slope_time_cost - 1))
```

---

## Running Mode (Future)

The architecture supports different activity modes:

```python
ACTIVITY_PARAMS = {
    'walking': {'max_speed': 6.0, 'decay_rate': 3.5, 'optimal_grade': -0.05},
    'running': {'max_speed': 15.0, 'decay_rate': 2.5, 'optimal_grade': -0.10},
}
```

Running has a different optimal downhill grade (~10%) because runners can handle steeper descents at speed.

---

## LOCAL Mode Details

### Tile Management

- Tiles are 1°×1° GeoTIFF files (~25MB each)
- Downloaded automatically on first use for each region
- Stored in `app/data/dem/` directory
- Loaded into memory for fast batch lookups

### Storage Requirements

| Coverage | Approximate Storage |
|----------|---------------------|
| Single UK city | ~25MB (1 tile) |
| UK-wide | ~500MB-1GB |
| Global | Not recommended for bulk download |

---

## Performance Comparison

| Mode | First Run (new region) | Subsequent Runs |
|------|------------------------|-----------------|
| OFF | 0s | 0s |
| API | ~30-60s | ~30-60s |
| LOCAL | ~10-15s (with download) | ~1-3s |

LOCAL mode is **10-30× faster** for cached regions.

---

## Technical References

1. Tobler, W. (1993). "Three Presentations on Geographical Analysis and Modeling"
2. Imhof, E. (1950). "Gelände und Karte" (Terrain and Map)
3. Minetti, A.E. et al. (2002). "Energy cost of walking and running at extreme uphill and downhill slopes"
