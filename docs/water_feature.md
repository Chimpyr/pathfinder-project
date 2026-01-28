# Water Proximity Feature

This document explains the water proximity scoring system used for scenic routing.

## Overview

The water proximity feature allows routes to prefer paths near water features such as rivers, canals, lakes, and wetlands. Users control this via the **Near Water** slider (0-10) in the UI.

## How It Works

### Data Extraction

Water features are extracted from OpenStreetMap data using these tags:

- `natural`: water, wetland
- `landuse`: reservoir, basin
- `waterway`: river, canal, riverbank, stream

**Important**: Rivers in OSM are mapped as LineString geometries, so the extraction process buffers them by 10 metres to create polygon proximity areas.

### Proximity Scoring (Minimum Distance)

For each graph edge, we calculate water proximity using **minimum distance** to the nearest water feature:

1. Project the edge midpoint to UTM coordinates (metres)
2. Create a 50m search buffer to find candidate water features
3. Calculate the minimum distance from midpoint to any water feature
4. Normalise to 0-1 range: `score = distance / 50m`

This produces a **cost** value where:

- **0.0** = Edge is on/touching water (best for water preference)
- **0.5** = Edge is 25m from water
- **1.0** = No water within 50m (worst for water preference)

## -

### Fix 1: Rivers Not Detected

**Problem**: Rivers are LineString geometries in OSM, but the original code only kept Polygon geometries.

**Solution**: Buffer LineString waterway features by 10m to create polygons.

```python
# In data_loader.py extract_water()
RIVER_BUFFER_METRES = 10
line_mask = gdf.geometry.geom_type.isin(['LineString', 'MultiLineString'])
gdf.loc[line_mask, 'geometry'] = gdf.loc[line_mask, 'geometry'].buffer(RIVER_BUFFER_METRES)
```

### Fix 2: Area Coverage Scoring Gave Wrong Values

**Problem**: Original scoring calculated what percentage of a 50m circular buffer was covered by water. A 20m-wide river could only cover ~50% of the buffer area, so edges _on_ a river scored ~0.5 instead of 0.0.

**Solution**: Changed to **minimum distance** scoring. If an edge is directly on water, distance = 0, so score = 0.0.

```python
# Old approach (flawed):
water_area / buffer_area  # River covering 50% → score 0.5

# New approach (correct):
min_distance / max_distance  # On river → distance 0 → score 0.0
```

## Configuration

| Constant              | Value | Location         | Purpose                                   |
| --------------------- | ----- | ---------------- | ----------------------------------------- |
| `RIVER_BUFFER_METRES` | 10m   | `data_loader.py` | Width to buffer river LineStrings         |
| `MAX_WATER_DISTANCE`  | 50m   | `water.py`       | Distance beyond which water has no effect |

## Related Components

- **Data Loader** (`app/services/core/data_loader.py`): Extracts and buffers water features
- **Water Processor** (`app/services/processors/water.py`): Scores edges by distance to water
- **Normalisation** (`app/services/processors/normalisation.py`): Copies `raw_water_cost` to `norm_water`
- **WSM A\*** (`app/services/routing/astar/wsm_astar.py`): Uses `norm_water` in cost calculation
