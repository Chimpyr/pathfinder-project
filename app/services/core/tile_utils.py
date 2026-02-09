"""
Tile Grid Utilities for Graph Caching

Provides functions for calculating tile IDs and bounding boxes for the
snap-to-grid caching system. Routes are mapped to standardised tiles
instead of unique bounding boxes, improving cache reuse.

See ADR-007 for architectural rationale.
"""

from typing import List, Tuple, Set
import math


# Approximate degrees per kilometre at mid-latitudes (UK ~51°N)
DEG_PER_KM = 1 / 111.0


def get_tile_id(lat: float, lon: float, tile_size_km: float = 30) -> str:
    """
    Snap coordinates to the nearest tile grid cell.
    
    Uses a fixed grid aligned to round coordinates. Each tile is identified
    by its centre point, formatted as "lat_lon" with 2 decimal places.
    
    Args:
        lat: Latitude in degrees.
        lon: Longitude in degrees.
        tile_size_km: Size of each tile in kilometres.
    
    Returns:
        Tile ID string, e.g., "51.45_-2.55"
    
    Example:
        >>> get_tile_id(51.4567, -2.5891, 15)
        "51.45_-2.55"
    """
    tile_size_deg = tile_size_km * DEG_PER_KM
    
    # Snap to nearest grid cell centre
    snapped_lat = round(lat / tile_size_deg) * tile_size_deg
    snapped_lon = round(lon / tile_size_deg) * tile_size_deg
    
    return f"{snapped_lat:.2f}_{snapped_lon:.2f}"


def get_tiles_for_bbox(min_lat: float, min_lon: float, 
                       max_lat: float, max_lon: float,
                       tile_size_km: float = 30) -> List[str]:
    """
    Determine which tiles cover a bounding box.
    
    Returns only the tiles that the bbox corners fall into, not extra tiles
    beyond the bbox boundary.
    
    Args:
        min_lat: Minimum latitude of bbox.
        min_lon: Minimum longitude of bbox.
        max_lat: Maximum latitude of bbox.
        max_lon: Maximum longitude of bbox.
        tile_size_km: Size of each tile in kilometres.
    
    Returns:
        Sorted list of tile IDs covering the bbox.
    """
    tiles: Set[str] = set()
    
    # Get tile for each corner of the bbox
    tiles.add(get_tile_id(min_lat, min_lon, tile_size_km))
    tiles.add(get_tile_id(min_lat, max_lon, tile_size_km))
    tiles.add(get_tile_id(max_lat, min_lon, tile_size_km))
    tiles.add(get_tile_id(max_lat, max_lon, tile_size_km))
    
    # Also get tile for centre to catch edge cases
    centre_lat = (min_lat + max_lat) / 2
    centre_lon = (min_lon + max_lon) / 2
    tiles.add(get_tile_id(centre_lat, centre_lon, tile_size_km))
    
    return sorted(tiles)


def get_tiles_for_route(start: Tuple[float, float], 
                        end: Tuple[float, float],
                        tile_size_km: float = 30) -> List[str]:
    """
    Determine which tiles a route between two points requires.
    
    Calculates the bounding box of the route and returns all tiles
    that intersect with it.
    
    Args:
        start: Start point as (lat, lon).
        end: End point as (lat, lon).
        tile_size_km: Size of each tile in kilometres.
    
    Returns:
        Sorted list of tile IDs covering the route.
    
    Example:
        >>> get_tiles_for_route((51.45, -2.6), (51.48, -2.5), 15)
        ["51.45_-2.55"]  # If both points fall in same tile
    """
    min_lat = min(start[0], end[0])
    max_lat = max(start[0], end[0])
    min_lon = min(start[1], end[1])
    max_lon = max(start[1], end[1])
    
    # Get all candidate tiles based on grid intersection
    candidates = get_tiles_for_bbox(min_lat, min_lon, max_lat, max_lon, tile_size_km)
    
    # OPTIMIZATION: Check if any single candidate tile covers the ENTIRE route bbox
    # taking into account the overlap buffer. This avoids loading 2 tiles for a short
    # route that crosses a boundary but fits within the overlap of one tile.
    
    # We need to know the configured overlap. Since we don't have config here,
    # we'll assume a reasonable default or pass it in. Ideally meaningful overlap
    # is required for this optimization to work.
    
    # If the list is small (which it usually is), check coverage
    if len(candidates) > 1:
        # Import config here to avoid circular imports or assumptions
        try:
             from flask import current_app
             overlap_km = current_app.config.get('TILE_OVERLAP_KM', 2)
        except:
             overlap_km = 2  # Fallback
             
        for tile_id in candidates:
             bbox = get_tile_bbox(tile_id, tile_size_km, overlap_km)
             # bbox is (min_lat, min_lon, max_lat, max_lon)
             
             if (min_lat >= bbox[0] and max_lat <= bbox[2] and
                 min_lon >= bbox[1] and max_lon <= bbox[3]):
                 return [tile_id]
                 
    return candidates


def get_tile_bbox(tile_id: str, tile_size_km: float = 30,
                  overlap_km: float = 2) -> Tuple[float, float, float, float]:
    """
    Get the bounding box for a tile, including overlap buffer.
    
    The overlap ensures that nodes at tile boundaries exist in both
    adjacent tiles, enabling proper graph merging.
    
    Args:
        tile_id: Tile identifier string, e.g., "51.45_-2.55".
        tile_size_km: Size of each tile in kilometres.
        overlap_km: Overlap buffer in kilometres.
    
    Returns:
        Bounding box tuple: (min_lat, min_lon, max_lat, max_lon)
    
    Example:
        >>> get_tile_bbox("51.45_-2.55", 15, 1)
        (51.38, -2.62, 51.52, -2.48)  # Approximate values
    """
    parts = tile_id.split('_')
    centre_lat = float(parts[0])
    centre_lon = float(parts[1])
    
    half_size = (tile_size_km * DEG_PER_KM) / 2
    overlap = overlap_km * DEG_PER_KM
    
    return (
        centre_lat - half_size - overlap,  # min_lat
        centre_lon - half_size - overlap,  # min_lon
        centre_lat + half_size + overlap,  # max_lat
        centre_lon + half_size + overlap   # max_lon
    )


def parse_tile_id(tile_id: str) -> Tuple[float, float]:
    """
    Parse a tile ID into its centre coordinates.
    
    Args:
        tile_id: Tile identifier string, e.g., "51.45_-2.55".
    
    Returns:
        Tuple of (lat, lon) for the tile centre.
    """
    parts = tile_id.split('_')
    return float(parts[0]), float(parts[1])


def estimate_tile_size_nodes(tile_size_km: float, 
                             edges_per_km2: float = 150) -> int:
    """
    Estimate the number of nodes in a tile based on typical density.
    
    Bristol urban area has roughly 150-200 edges per km². This helps
    with memory planning.
    
    Args:
        tile_size_km: Size of each tile in kilometres.
        edges_per_km2: Estimated edge density per square kilometre.
    
    Returns:
        Estimated node count for the tile.
    """
    area_km2 = tile_size_km * tile_size_km
    # Approximate: nodes ≈ edges * 0.6 (typical graph ratio)
    return int(area_km2 * edges_per_km2 * 0.6)
