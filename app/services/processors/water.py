"""
Water Processor Module

Calculates proximity to water features (rivers, lakes, canals) for each graph edge.

Edge attribute added:
- raw_water_cost: 0.0 = near water, 1.0 = no water (lower = better for routing)
"""

import time
from typing import List, Tuple, Optional
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point
from shapely.strtree import STRtree
from pyproj import Transformer


# Configuration constants
MAX_WATER_DISTANCE: float = 250  # metres - edges beyond this get score 1.0

# Coordinate transformer: WGS84 (lat/lon) to UTM zone 30N (metres)
_transformer: Optional[Transformer] = None


def _get_transformer() -> Transformer:
    """Get or create the coordinate transformer (WGS84 -> EPSG:32630)."""
    global _transformer
    if _transformer is None:
        _transformer = Transformer.from_crs("EPSG:4326", "EPSG:32630", always_xy=True)
    return _transformer


def _transform_coords(lon: float, lat: float) -> Tuple[float, float]:
    """Transform WGS84 coordinates to projected metres."""
    transformer = _get_transformer()
    x, y = transformer.transform(lon, lat)
    return x, y


def _build_spatial_index(gdf: Optional[gpd.GeoDataFrame]) -> Tuple[Optional[STRtree], List]:
    """
    Build R-tree spatial index for efficient geometry lookups.
    
    Args:
        gdf: GeoDataFrame of polygons (projected to metres).
    
    Returns:
        Tuple of (spatial_index, geometry_list).
    """
    if gdf is None or gdf.empty:
        return None, []
    
    geoms = list(gdf.geometry)
    sindex = STRtree(geoms)
    return sindex, geoms


def _calculate_water_score_distance(
    midpoint: Point,
    water_sindex: Optional[STRtree],
    water_geoms: List,
    max_distance: float = MAX_WATER_DISTANCE,
    debug: bool = False
) -> float:
    """
    Calculate water proximity score using minimum distance (lower = closer to water).
    
    Uses distance to nearest water feature normalised to 0-1 range.
    This approach correctly scores edges ON rivers as near 0.0,
    unlike area coverage which gave ~0.5 for edges on narrow rivers.
    
    Args:
        midpoint: Edge midpoint (projected coordinates).
        water_sindex: Spatial index for water features.
        water_geoms: List of water feature geometries.
        max_distance: Maximum distance in metres beyond which score is 1.0.
        debug: If True, print debug information.
    
    Returns:
        Float between 0.0 (on water) and 1.0 (no water nearby).
    """
    if water_sindex is None or len(water_geoms) == 0:
        return 1.0  # No water = max cost
    
    # Create search area
    search_buffer = midpoint.buffer(max_distance)
    
    # Find candidate water features within search radius
    candidate_indices = water_sindex.query(search_buffer)
    
    # Handle numpy array vs list
    num_candidates = len(candidate_indices) if hasattr(candidate_indices, '__len__') else 0
    
    if debug:
        print(f"[WaterProcessor DEBUG] Midpoint: {midpoint.x:.0f}, {midpoint.y:.0f}")
        print(f"[WaterProcessor DEBUG] Candidates found: {num_candidates}")
    
    if num_candidates == 0:
        return 1.0  # No water within max distance
    
    # Find minimum distance to any water feature
    min_distance = max_distance
    errors = 0
    for idx in candidate_indices:
        try:
            geom = water_geoms[idx]
            if not geom.is_valid:
                geom = geom.buffer(0)
            dist = midpoint.distance(geom)
            if dist < min_distance:
                min_distance = dist
        except Exception as e:
            errors += 1
            if debug:
                print(f"[WaterProcessor DEBUG] Error processing idx {idx}: {type(e).__name__}: {e}")
            continue
    
    if debug and errors > 0:
        print(f"[WaterProcessor DEBUG] Errors: {errors}/{num_candidates}")
        print(f"[WaterProcessor DEBUG] Min distance: {min_distance:.1f}m")
    
    # Normalise: 0m = 0.0, max_distance = 1.0
    return min(1.0, min_distance / max_distance)



def process_graph_water(
    graph: nx.MultiDiGraph,
    water_gdf: Optional[gpd.GeoDataFrame]
) -> nx.MultiDiGraph:
    """
    Process all edges to assign water proximity scores.
    
    Uses minimum distance from edge midpoint to nearest water feature,
    normalised to 0-1 range. Edges directly on water score near 0.0.
    
    Args:
        graph: NetworkX MultiDiGraph with node coordinates.
        water_gdf: GeoDataFrame of water feature polygons (projected).
    
    Returns:
        Graph with raw_water_cost added to edges (0.0 = on water, 1.0 = far from water).
    """
    if graph is None:
        return graph
    
    if water_gdf is None or water_gdf.empty:
        print("[WaterProcessor] No water features provided, skipping.")
        return graph
    
    print("[WaterProcessor] Building spatial index...")
    
    # Debug: Print water GeoDataFrame info
    print(f"[WaterProcessor DEBUG] Water CRS: {water_gdf.crs}")
    bounds = water_gdf.total_bounds
    print(f"[WaterProcessor DEBUG] Water bounds: minx={bounds[0]:.0f}, miny={bounds[1]:.0f}, maxx={bounds[2]:.0f}, maxy={bounds[3]:.0f}")
    water_sindex, water_geoms = _build_spatial_index(water_gdf)
    
    edges_processed = 0
    total_edges = graph.number_of_edges()
    report_interval = max(1, total_edges // 10)
    
    print(f"[WaterProcessor] Processing {total_edges} edges...")
    t0 = time.perf_counter()
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        try:
            start_lon = graph.nodes[u].get('x', 0)
            start_lat = graph.nodes[u].get('y', 0)
            end_lon = graph.nodes[v].get('x', 0)
            end_lat = graph.nodes[v].get('y', 0)
            
            start_x, start_y = _transform_coords(start_lon, start_lat)
            end_x, end_y = _transform_coords(end_lon, end_lat)
            
            mid_x = (start_x + end_x) / 2
            mid_y = (start_y + end_y) / 2
            midpoint = Point(mid_x, mid_y)
            
            # Debug: Print first edge midpoint coordinates
            is_first_edge = edges_processed == 0
            if is_first_edge:
                print(f"[WaterProcessor DEBUG] First edge midpoint: x={mid_x:.0f}, y={mid_y:.0f}")
            
            water_score = _calculate_water_score_distance(
                midpoint, water_sindex, water_geoms, debug=is_first_edge
            )
            
            # Score is already in cost format (0 = near water, 1 = far from water)
            graph[u][v][key]['raw_water_cost'] = water_score
            
        except Exception:
            graph[u][v][key]['raw_water_cost'] = 1.0
        
        edges_processed += 1
        if edges_processed % report_interval == 0:
            pct = (edges_processed / total_edges) * 100
            print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
    
    elapsed = time.perf_counter() - t0
    print(f"[WaterProcessor] Processed {edges_processed} edges in {elapsed:.2f}s")
    
    return graph
