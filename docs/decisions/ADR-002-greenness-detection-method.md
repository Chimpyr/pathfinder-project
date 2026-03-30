# ADR-002: Greenness Detection Method Selection

**Status:** Accepted  
**Date:** 2025-11 (Retrospective)

---

## Context

The ScenicPathFinder needs to score each graph edge for "greenness" - how green/vegetated the surrounding area is. This score is used in the WSM cost function to route pedestrians through greener areas.

Multiple detection methods exist with varying trade-offs between accuracy, computation time, and data requirements.

---

## Decision

**Implement a tiered approach starting with Edge Geometry Sampling using OSM polygon data.**

### Primary Method: Edge Sampling with Buffer

Sample multiple points along each edge geometry, create 50m buffer around each sample point, and calculate intersection with green OSM polygons (parks, forests, etc.).

```python
def calculate_green_score_edge(edge_geom, green_index, buffer_radius=50):
    length = edge_geom.length
    sample_count = max(2, int(length / 20))  # Sample every ~20m

    points = [edge_geom.interpolate(i / (sample_count-1), normalized=True)
              for i in range(sample_count)]

    scores = [point_buffer_score(p, green_index, buffer_radius) for p in points]
    return np.mean(scores)
```

### Configuration

```python
GREENNESS_MODE = 'FAST'  # Options: OFF | FAST | NOVACK
```

---

## Consequences

### Positive

- **Fast processing:** ~30-60 seconds for Bristol region (325,000 edges)
- **Good coverage:** Detects parks, forests, green spaces along entire edge
- **Free data:** Uses OSM polygon data, no external APIs required
- **Configurable:** Buffer radius can be tuned per deployment

### Negative

- **Limited to mapped polygons:** Street trees, private gardens not detected
- **Binary detection:** Area is either green or not, no density gradient
- **OSM quality dependent:** Unmapped parks won't be detected

---

## Alternatives Considered

For detailed comparison of all methods, see [Greenness Methods Comparison](../features/research/greenness_methods_comparison.md).

| Method                     | Accuracy   | Speed      | Why Not Selected                                     |
| -------------------------- | ---------- | ---------- | ---------------------------------------------------- |
| **Point Buffer (simpler)** | ⭐⭐       | ⭐⭐⭐⭐⭐ | Misses long edges, only samples midpoint             |
| **NDVI Raster**            | ⭐⭐⭐⭐   | ⭐⭐⭐     | Requires satellite data download, seasonal variation |
| **Green View Index (GVI)** | ⭐⭐⭐⭐⭐ | ⭐⭐       | Requires street imagery API, expensive at scale      |
| **Isovist Ray-casting**    | ⭐⭐⭐⭐   | ⭐         | Too slow (~10+ min), complex implementation          |

---

## Future Enhancements

1. **NDVI overlay:** Add Sentinel-2 NDVI as secondary signal for street trees
2. **Tag-based boost:** Increase scores for `highway=path` in parks, `surface=grass`
3. **Caching:** Pre-compute green scores and store in disk cache (implemented)

---

## References

- [Greenness Methods Comparison](../features/research/greenness_methods_comparison.md) - Detailed research document
- Novack et al. (2018) - Isovist-based greenness visibility
- MIT Senseable City Lab - Green View Index methodology
