# Debug Features

This document describes the debug and development features available in ScenicPathFinder.

---

## Enabling Debug Mode

Debug features are controlled by the `DEBUG` flag in `config.py`:

```python
class Config:
    DEBUG = True  # Enable debug features
```

---

## Debug Edge Features Visualisation

When `DEBUG` is enabled, the application displays detailed edge (street segment) feature information to help understand the scenic scoring data.

### First 5 Edges Panel

The debug info panel always shows the **first 5 edges** of any calculated route with their feature values:

| Emoji | Feature | Description | Scale |
|-------|---------|-------------|-------|
| 🔊 | Noise Factor | Road type quietness classification | 1 (quiet) → 5 (noisy) |
| 🌿 | Green Cost | Proximity to parks and green spaces | 0 (very green) → 1 (no green) |
| 💧 | Water Cost | Proximity to water features | 0 (near water) → 1 (far from water) |
| 🏛️ | Social Cost | Proximity to tourist/social POIs | 0 (near POIs) → 1 (no POIs) |
| ⛰️ | Slope Cost | Edge gradient (elevation change) | Decimal gradient (0.05 = 5%) |

### Visual Edge Overlays (Short Routes Only)

For routes **under 5km**, coloured polyline segments overlay the route on the map:

| Colour | Dominant Feature | Meaning |
|--------|-----------------|---------|
| 🟢 Green | Greenness | Edge is near parks/green spaces |
| 🔵 Blue | Water | Edge is near water features |
| 🟡 Amber | Social | Edge is near tourist/social POIs |
| ⚫ Grey | None | No dominant scenic feature detected |

The colour indicates the **best-scoring feature** (lowest cost value) for each edge.

### Hover Tooltips

When visual overlays are displayed, **hover over any edge segment** to see a tooltip with:

- Edge number and highway type
- Length in metres
- All 5 feature values (noise, green, water, social, slope)


Visual overlays are limited to short routes to:
1. Avoid performance issues with many polyline segments
2. Focus debugging on detailed analysis of specific areas
3. Keep the map readable for longer routes

---

## Raw Debug Data

The debug panel includes a **collapsible "Raw Debug Data"** section containing the full JSON response, including:

- Start/end coordinates
- Route node count
- Graph node count
- Bounding box used
- Loaded PBF file path
- `visual_debug_enabled` flag and reason if disabled

---

## API Response Debug Fields

When `DEBUG` or `VERBOSE_LOGGING` is enabled, the `/api/route` endpoint includes additional fields:

```json
{
    "debug_info": {
        "start_coord": [51.45, -2.63],
        "end_coord": [51.46, -2.62],
        "node_count": 42,
        "graph_nodes": 325000,
        "bbox": [...],
        "loaded_pbf": "app/data/bristol.osm.pbf",
        "edge_preview": [...],               // First 5 edges
        "visual_debug_enabled": true
    },
    "edge_features": [...]  // All edges (only if route < 5km currently)
}
```

---

## Cached Tiles Visualisation

To debug the graph caching system and verify which tiles are being used for routing, a visualisation tool is available in the frontend.

### Usage

1.  Toggle the **"Show Cached Tiles"** checkbox at the bottom of the sidebar (always visible).
2.  The map will overlay the grid of currently cached tiles.
    -   *Note: If the cache is empty, the label will show "(no tiles cached)".*

### Color Coding

| Color | Meaning | Description |
|-------|---------|-------------|
| **Purple** | Cached Tile | The tile exists in the backend cache (ready for use). |
| **Orange** | Used in Route | The tile was specifically required and loaded for the most recent route calculation. |

### Behavior

-   **On Load**: If the checkbox is checked, the available tiles are fetched immediately from the backend.
-   **Before Routing**: Shows the set of all currently cached tiles (useful to see what's already built).
-   **After Routing**: Automatically updates to highlight (in Orange) the specific tiles used to construct the graph for that route.
