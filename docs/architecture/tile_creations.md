# Tile Creation and Grid Snapping

## Overview

The transformation of a start location into a standardised grid location is handled by the [`get_tile_id()`](../../app/services/core/tile_utils.py#L35) function. This mathematical snapping process guarantees that any coordinate within a specific area always resolves to the exact same grid anchor, ensuring perfect cache reuse across different user requests.

## Implementation Details

### Constants

- **`DEG_PER_KM`**: Defined as `1 / 111.0` [line 13](../../app/services/core/tile_utils.py#L13) — the approximate degrees per kilometre at mid-latitudes (UK ~51°N)
- **`DEFAULT_TILE_SIZE_KM`**: Imported from [Config](../../config.py) with a fallback of 15 km [lines 20-30](../../app/services/core/tile_utils.py#L20-L30)

### Snapping Algorithm

The coordinate snapping follows a three-step mathematical process:

1. **Convert to Degrees**
   - The system establishes a fixed tile size (default: 15 km)
   - This physical distance is converted into geographic degrees: `tile_size_deg = tile_size_km * DEG_PER_KM`
   - For a 15 km tile: `15 * (1/111.0) ≈ 0.135 degrees`

2. **Round to Grid**
   - The precise coordinates are divided by the tile size in degrees
   - The quotient is rounded to the **nearest integer** (not down) using Python's `round()` function [line 55](../../app/services/core/tile_utils.py#L55)
   - This step strips away the precision of the user's exact position

3. **Generate Anchor Coordinate**
   - The rounded integer is multiplied back by the degree step size
   - The result is formatted as a string with 2 decimal places: `"{lat:.2f}_{lon:.2f}"` [line 58](../../app/services/core/tile_utils.py#L58)
   - Example output: `"51.45_-2.55"`

### Code Implementation

```python
def get_tile_id(lat: float, lon: float, tile_size_km: float = DEFAULT_TILE_SIZE_KM) -> str:
    tile_size_deg = tile_size_km * DEG_PER_KM

    # Snap to nearest grid cell centre
    snapped_lat = round(lat / tile_size_deg) * tile_size_deg
    snapped_lon = round(lon / tile_size_deg) * tile_size_deg

    return f"{snapped_lat:.2f}_{snapped_lon:.2f}"
```

**See [lines 35-58](../../app/services/core/tile_utils.py#L35-L58) in tile_utils.py**

## Grid Properties

Because this arithmetic is anchored to absolute latitude and longitude coordinates in fixed increments, the grid boundaries are **completely deterministic**:

- Boundaries **never shift** — they are universally aligned to Earth's coordinate system
- Any two points within the same tile always return the identical tile ID
- Points at tile edges are assigned to the nearest tile centre via rounding
- Whether a user starts at the edge or centre of a 15 km area, the rounding mechanics force identical inputs to map to the same grid coordinate

## Related Functions

- **[`get_tiles_for_bbox()`](../../app/services/core/tile_utils.py#L67)** — Determines which tiles cover a bounding box
- **[`get_tiles_for_route()`](../../app/services/core/tile_utils.py#L100)** — Determines which tiles a route between two points requires

## Architecture Reference

See ADR-007 for the full architectural rationale behind the tile-based caching system.
