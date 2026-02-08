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


def get_tile_id(lat: float, lon: float, tile_size_km: float = 15) -> str:
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
                       tile_size_km: float = 15) -> List[str]:
    """
    Determine which tiles cover a bounding box.
    
    Iterates through the bbox area and collects all tile IDs that
    intersect with it.
    
    Args:
        min_lat: Minimum latitude of bbox.
        min_lon: Minimum longitude of bbox.
        max_lat: Maximum latitude of bbox.
        max_lon: Maximum longitude of bbox.
        tile_size_km: Size of each tile in kilometres.
    
    Returns:
        Sorted list of tile IDs covering the bbox.
    """
    tile_size_deg = tile_size_km * DEG_PER_KM
    tiles: Set[str] = set()
    
    # Step through bbox with half-tile increments to catch all overlaps
    step = tile_size_deg / 2
    
    lat = min_lat
    while lat <= max_lat + tile_size_deg:
        lon = min_lon
        while lon <= max_lon + tile_size_deg:
            tiles.add(get_tile_id(lat, lon, tile_size_km))
            lon += step
        lat += step
    
    return sorted(tiles)


def get_tiles_for_route(start: Tuple[float, float], 
                        end: Tuple[float, float],
                        tile_size_km: float = 15) -> List[str]:
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
    
    return get_tiles_for_bbox(min_lat, min_lon, max_lat, max_lon, tile_size_km)


def get_tile_bbox(tile_id: str, tile_size_km: float = 15,
                  overlap_km: float = 1) -> Tuple[float, float, float, float]:
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
