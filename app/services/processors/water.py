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
FAST_BUFFER_RADIUS: float = 30.0  # metres - buffer for FAST mode

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


def _calculate_water_score_fast(
    midpoint: Point,
    water_sindex: Optional[STRtree],
    water_geoms: List,
    buffer_radius: float = FAST_BUFFER_RADIUS
) -> float:
    """
    Calculate water proximity score using buffer intersection (FAST mode).
    
    Args:
        midpoint: Edge midpoint (projected coordinates).
        water_sindex: Spatial index for water features.
        water_geoms: List of water feature geometries.
        buffer_radius: Search radius in metres.
    
    Returns:
        Float between 0.0 and 1.0 representing water coverage proportion.
    """
    if water_sindex is None or len(water_geoms) == 0:
        return 0.0
    
    buffer = midpoint.buffer(buffer_radius)
    buffer_area = buffer.area
    
    if buffer_area <= 0:
        return 0.0
    
    candidate_indices = water_sindex.query(buffer)
    if len(candidate_indices) == 0:
        return 0.0
    
    water_area = 0.0
    for idx in candidate_indices:
        geom = water_geoms[idx]
        try:
            if not geom.is_valid:
                geom = geom.buffer(0)
            if buffer.intersects(geom):
                intersection = buffer.intersection(geom)
                if not intersection.is_empty:
                    water_area += intersection.area
        except Exception:
            continue
    
    return min(1.0, water_area / buffer_area)


def process_graph_water(
    graph: nx.MultiDiGraph,
    water_gdf: Optional[gpd.GeoDataFrame]
) -> nx.MultiDiGraph:
    """
    Process all edges to assign water proximity scores.
    
    Uses 30m buffer around edge midpoints to calculate proximity
    to water features (rivers, lakes, canals).
    
    Args:
        graph: NetworkX MultiDiGraph with node coordinates.
        water_gdf: GeoDataFrame of water feature polygons (projected).
    
    Returns:
        Graph with raw_water_cost added to edges (0.0 = water, 1.0 = no water).
    """
    if graph is None:
        return graph
    
    if water_gdf is None or water_gdf.empty:
        print("[WaterProcessor] No water features provided, skipping.")
        return graph
    
    print("[WaterProcessor] Building spatial index...")
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
            
            water_score = _calculate_water_score_fast(midpoint, water_sindex, water_geoms)
            
            # Convert to cost (lower = better)
            graph[u][v][key]['raw_water_cost'] = 1.0 - water_score
            
        except Exception:
            graph[u][v][key]['raw_water_cost'] = 1.0
        
        edges_processed += 1
        if edges_processed % report_interval == 0:
            pct = (edges_processed / total_edges) * 100
            print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
    
    elapsed = time.perf_counter() - t0
    print(f"[WaterProcessor] Processed {edges_processed} edges in {elapsed:.2f}s")
    
    return graph
