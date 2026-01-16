"""
Greenness Processing Utilities

Shared spatial functions used by multiple greenness processing strategies.
Includes coordinate transformation, spatial indexing, and buffer calculations.
"""

import math
from typing import List, Tuple, Optional
from shapely.geometry import Point, Polygon, LineString
from shapely.strtree import STRtree
from pyproj import Transformer
import geopandas as gpd


# Coordinate transformer: WGS84 (lat/lon) to UTM zone 30N (metres)
# Cached globally for performance
_transformer: Optional[Transformer] = None


def get_transformer() -> Transformer:
    """
    Get or create the coordinate transformer (WGS84 -> EPSG:32630).
    
    Uses UTM zone 30N which covers the UK. The transformer is cached
    globally to avoid repeated initialisation overhead.
    
    Returns:
        Transformer: pyproj Transformer for WGS84 to UTM 30N.
    """
    global _transformer
    if _transformer is None:
        _transformer = Transformer.from_crs(
            "EPSG:4326", "EPSG:32630", always_xy=True
        )
    return _transformer


def transform_coords(lon: float, lat: float) -> Tuple[float, float]:
    """
    Transform WGS84 coordinates to projected metres (UTM 30N).
    
    Args:
        lon: Longitude in degrees.
        lat: Latitude in degrees.
    
    Returns:
        Tuple of (x, y) in metres.
    """
    transformer = get_transformer()
    x, y = transformer.transform(lon, lat)
    return x, y


def build_spatial_index(
    gdf: Optional[gpd.GeoDataFrame]
) -> Tuple[Optional[STRtree], List]:
    """
    Build R-tree spatial index for efficient geometry lookups.
    
    The R-tree allows O(log n) queries for geometries within a bounding box,
    dramatically improving performance for large datasets.
    
    Args:
        gdf: GeoDataFrame of polygons (should be projected to metres).
    
    Returns:
        Tuple of (spatial_index, geometry_list).
        Returns (None, []) if gdf is None or empty.
    """
    if gdf is None or gdf.empty:
        return None, []
    
    geoms = list(gdf.geometry)
    sindex = STRtree(geoms)
    return sindex, geoms


def project_gdf(gdf: Optional[gpd.GeoDataFrame], crs: str = "EPSG:32630") -> Optional[gpd.GeoDataFrame]:
    """
    Project a GeoDataFrame to the specified CRS if not already projected.
    
    Args:
        gdf: GeoDataFrame to project.
        crs: Target CRS (default: EPSG:32630 / UTM 30N).
    
    Returns:
        Projected GeoDataFrame, or None if input is None.
    """
    if gdf is None or gdf.empty:
        return gdf
    
    if gdf.crs is None:
        # Assume WGS84 if no CRS set
        gdf = gdf.set_crs("EPSG:4326")
    
    if gdf.crs.to_string() != crs:
        gdf = gdf.to_crs(crs)
    
    return gdf


def calculate_point_buffer_score(
    point: Point,
    green_sindex: Optional[STRtree],
    green_geoms: List[Polygon],
    buffer_radius: float
) -> float:
    """
    Calculate green score for a single point using buffer intersection.
    
    Creates a circular buffer around the point and measures what fraction
    of the buffer area intersects with green polygons.
    
    Args:
        point: Observation point (projected coordinates in metres).
        green_sindex: R-tree spatial index for green polygons.
        green_geoms: List of green polygon geometries.
        buffer_radius: Buffer radius in metres.
    
    Returns:
        Green cost (0.0 = very green, 1.0 = no green).
    """
    if green_sindex is None or len(green_geoms) == 0:
        return 1.0  # No green data, assume no greenness
    
    buffer = point.buffer(buffer_radius)
    buffer_area = buffer.area
    
    if buffer_area <= 0:
        return 1.0
    
    # Query R-tree for candidate polygons
    candidate_indices = green_sindex.query(buffer)
    
    if len(candidate_indices) == 0:
        return 1.0  # No green polygons nearby
    
    # Calculate intersection area with all candidates
    green_area = 0.0
    for idx in candidate_indices:
        try:
            intersection = buffer.intersection(green_geoms[idx])
            if not intersection.is_empty:
                green_area += intersection.area
        except Exception:
            # Skip invalid geometries
            continue
    
    # Clamp to buffer area (avoid > 1.0 from overlapping polygons)
    green_area = min(green_area, buffer_area)
    
    # Convert to cost: more green = lower cost
    green_score = green_area / buffer_area
    green_cost = 1.0 - green_score
    
    return max(0.0, min(1.0, green_cost))


def get_edge_geometry(
    graph,
    u: int,
    v: int,
    key: int,
    data: dict
) -> Optional[LineString]:
    """
    Extract or construct the geometry for a graph edge.
    
    Checks for existing 'geometry' attribute, otherwise constructs
    a straight line from node coordinates. Always returns geometry
    in projected coordinates (UTM 30N metres) to match green polygons.
    
    Args:
        graph: NetworkX graph with node coordinates.
        u: Source node ID.
        v: Target node ID.
        key: Edge key (for MultiDiGraph).
        data: Edge data dictionary.
    
    Returns:
        LineString geometry in projected coordinates, or None if unavailable.
    """
    transformer = get_transformer()
    
    # Check for existing geometry - must project it from WGS84 to UTM
    if 'geometry' in data and data['geometry'] is not None:
        geom = data['geometry']
        if isinstance(geom, LineString):
            try:
                # Project all coordinates from WGS84 to UTM
                projected_coords = [
                    transformer.transform(x, y)
                    for x, y in geom.coords
                ]
                return LineString(projected_coords)
            except Exception:
                pass  # Fall through to construct from nodes
    
    # Construct from node coordinates (already projects them)
    try:
        u_data = graph.nodes[u]
        v_data = graph.nodes[v]
        
        u_x = u_data.get('x')
        u_y = u_data.get('y')
        v_x = v_data.get('x')
        v_y = v_data.get('y')
        
        if None in (u_x, u_y, v_x, v_y):
            return None
        
        # Transform to projected coordinates
        u_proj = transform_coords(u_x, u_y)
        v_proj = transform_coords(v_x, v_y)
        
        return LineString([u_proj, v_proj])
    
    except (KeyError, TypeError):
        return None


def get_edge_midpoint(
    graph,
    u: int,
    v: int
) -> Optional[Point]:
    """
    Get the midpoint of an edge in projected coordinates.
    
    Args:
        graph: NetworkX graph with node coordinates.
        u: Source node ID.
        v: Target node ID.
    
    Returns:
        Point at edge midpoint (projected), or None if unavailable.
    """
    try:
        u_data = graph.nodes[u]
        v_data = graph.nodes[v]
        
        u_x = u_data.get('x')
        u_y = u_data.get('y')
        v_x = v_data.get('x')
        v_y = v_data.get('y')
        
        if None in (u_x, u_y, v_x, v_y):
            return None
        
        # Transform to projected coordinates
        u_proj = transform_coords(u_x, u_y)
        v_proj = transform_coords(v_x, v_y)
        
        # Calculate midpoint
        mid_x = (u_proj[0] + v_proj[0]) / 2
        mid_y = (u_proj[1] + v_proj[1]) / 2
        
        return Point(mid_x, mid_y)
    
    except (KeyError, TypeError):
        return None
