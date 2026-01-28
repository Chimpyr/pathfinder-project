# Greenness Detection Methods - Research Comparison

This document compares different approaches for detecting greenness along pedestrian routes, balancing accuracy vs computation time.

---

## Method Comparison Matrix

| Method                     | Accuracy   | Speed      | Data Requirements  | Complexity |
| -------------------------- | ---------- | ---------- | ------------------ | ---------- |
| **Point Buffer (Current)** | ⭐⭐       | ⭐⭐⭐⭐⭐ | OSM polygons       | Low        |
| **Edge Sampling**          | ⭐⭐⭐     | ⭐⭐⭐⭐   | OSM polygons       | Low-Medium |
| **NDVI Raster**            | ⭐⭐⭐⭐   | ⭐⭐⭐     | Sentinel-2/Landsat | Medium     |
| **Green View Index (GVI)** | ⭐⭐⭐⭐⭐ | ⭐⭐       | Street imagery     | High       |
| **Isovist (Novack)**       | ⭐⭐⭐⭐   | ⭐         | OSM + buildings    | High       |

---

## 1. Point Buffer

**How it works:** Create circular buffer around edge midpoint, calculate intersection with green polygons.

```
Edge midpoint:  ●
Buffer (50m):   ◯──────50m──────◯
Green polygons: ████████
Score = intersection_area / buffer_area
```

**Pros:**

- Very fast (~30 seconds for 325,000 edges)
- Simple to implement and understand
- Uses freely available OSM polygon data

**Cons:**

- Only samples one point per edge (misses long edges)
- Paths running _alongside_ parks may not intersect
- Binary detection (in polygon or not)

**Current Result:** 70% of edges score "no green" (0.8-1.0)

---

## 2. Edge Geometry Sampling

**How it works:** Sample multiple points along the entire edge, not just midpoint.

```python
def calculate_green_score_edge(edge_geom, green_index, buffer_radius=30):
    """Sample every 20m along edge, return average score."""
    length = edge_geom.length
    sample_count = max(2, int(length / 20))

    points = [edge_geom.interpolate(i / (sample_count-1), normalized=True)
              for i in range(sample_count)]

    scores = [point_buffer_score(p, green_index, buffer_radius) for p in points]
    return np.mean(scores)
```

**Pros:**

- Much better coverage for long edges
- Detects parks along the entire path, not just midpoint
- Still uses fast buffer intersection
- Moderate speed increase (~2-3x slower, still <2 min)

**Cons:**

- Requires edge geometry (OSM provides this)
- More complex code

**Expected Result:** Should significantly reduce "no green" percentage for edges near parks.

---

## 3. NDVI Raster Overlay

**How it works:** Use satellite vegetation indices (NDVI) from Sentinel-2 or Landsat to score edges based on pixel values.

NDVI = (NIR - Red) / (NIR + Red)

- Values: -1.0 to 1.0
- > 0.3 = vegetation
- > 0.6 = dense vegetation

```python
def calculate_ndvi_score(edge_geom, ndvi_raster):
    """Sample NDVI values along edge from pre-computed raster."""
    coords = list(edge_geom.coords)
    values = [ndvi_raster.sample(coord) for coord in coords]
    return np.mean([max(0, v) for v in values])  # Normalize to 0-1
```

**Pros:**

- Captures actual vegetation (trees, grass) not just tagged polygons
- Detects street trees, gardens, verges not in OSM
- Global coverage from Copernicus/Landsat (free)
- 10m resolution (Sentinel-2)

**Cons:**

- Requires raster data download (~50-200MB per region)
- Pre-processing needed (cloud masking, compositing)
- Overhead view misses vertical greenery (walls, trellises)
- Updates seasonally (less accurate in winter)

**Data Sources:**

- Copernicus Sentinel-2 (10m, free): https://scihub.copernicus.eu
- Landsat 8/9 (30m, free): https://earthexplorer.usgs.gov
- Pre-computed NDVI: https://land.copernicus.eu

---

## 4. Green View Index (GVI)

**How it works:** Analyse street-level imagery to calculate percentage of visible green at eye-level.

```python
# Conceptual - requires image analysis
def calculate_gvi(street_image):
    """Use semantic segmentation to detect green pixels."""
    segmented = deeplab_model.predict(street_image)
    green_pixels = count_pixels(segmented, class='vegetation')
    total_pixels = image.width * image.height
    return green_pixels / total_pixels
```

**Pros:**

- Most accurate representation of pedestrian experience
- Captures vertical greenery (hedges, tree canopy, walls)
- Well-established metric in urban studies
- Correlates with perceived walkability

**Cons:**

- Requires street-level imagery (Google Street View, Mapillary)
- API costs for commercial imagery
- Computationally intensive (deep learning)
- Coverage gaps in rural/private areas
- Not real-time (images may be outdated)

**Data Sources:**

- Google Street View API (paid, per-request)
- Mapillary (free, crowd-sourced): https://www.mapillary.com
- Pre-computed GVI datasets: Some cities publish these

---

## 5. Isovist Ray-casting (Novack Method - Already Implemented)

**How it works:** Cast rays from sample points, clip at building boundaries, measure visible green area.

```
Sample point:     ●
Rays:         ╱╲╱╲╱╲
Buildings:   █████  █████
Visible:        ━━━━━━
Green in view:  ████
Score = visible_green / total_visible
```

**Pros:**

- Accounts for visibility (buildings block views)
- Theoretically most accurate for "what can pedestrian see"
- Academic foundation (Novack et al. 2018)

**Cons:**

- Very slow (~10+ minutes for 325,000 edges)
- Requires building footprints (OSM quality varies)
- Complex geometry operations

---

## Recommended Approach: Hybrid Multi-Method

For the best balance of accuracy and speed, combine methods:

### Tier 1: Edge Sampling with Buffer (Primary)

- Sample every 20m along edge geometry
- 50m buffer intersection with OSM green polygons
- ~1-2 minutes processing time

### Tier 2: NDVI Overlay (Enhancement)

- Download Sentinel-2 NDVI for region (one-time)
- Add NDVI sample values to edge score
- Captures street trees, gardens not in OSM
- Combined score: `0.6 * polygon_score + 0.4 * ndvi_score`

### Tier 3: Tag-based Boost (Fallback)

- Boost scores for edges with green-related OSM tags:
  - `highway=path` in `landuse=park` → +0.3
  - `surface=grass` → +0.4
  - Adjacent to `natural=tree_row` → +0.2

---

## Implementation Priority

1. **Immediate:** Increase buffer to 50m ✅ (Done)
2. **Short-term:** Implement edge geometry sampling (1-2 hours)
3. **Medium-term:** Add NDVI raster overlay (requires data download)
4. **Long-term:** Investigate GVI for dense urban areas

---

## References

- Novack et al. (2018): Isovist-based greenness visibility
- MIT Senseable City Lab: Green View Index methodology
- Copernicus Land Monitoring: NDVI products
- OpenStreetMap: Green space tagging guidelines
