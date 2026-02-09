"""
Social Processor Module

Calculates sociability of graph edges based on "Third Places" density.

Implements Novack et al. (2018) methodology:
- Uses specific OSM tags for social/third places (Table 1).
- Calculates social cost as: Length / Count of Third Places within 50 buffer.
- Lower cost = Higher sociability (better density of social spots).

Edge attribute added:
- raw_social_cost: Calculated density metric (lower = better).
"""

import time
import math
from typing import List, Tuple, Optional, Set
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point
from shapely.strtree import STRtree
from pyproj import Transformer


# Configuration constants
BUFFER_RADIUS: float = 50.0  # metres - as per Novack (2018)
MIN_social_COUNT: float = 0.1  # small epsilon to avoid div/0 for 0 POIs

# Novack (2018) Table 1: Third Place Tags
POI_AMENITY_TAGS = frozenset({
    'cafe', 'bar', 'pub', 'restaurant',
    'ice_cream', 'fast_food', 'food_court', 'biergarten'  # Expanded slightly for completeness
})

POI_SHOP_TAGS = frozenset({
    'bakery', 'convenience', 'supermarket', 'mall', 'department_store',
    'clothes', 'fashion', 'shoes', 'gift', 'books'
})

POI_LEISURE_TAGS = frozenset({
    'fitness_centre', 'sports_centre', 'gym', 'dance', 'bowling_alley'
})

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


def _build_spatial_index(gdf: Optional[gpd.GeoDataFrame]) -> Tuple[Optional[STRtree], List, List[dict]]:
    """
    Build R-tree spatial index for efficient geometry lookups.
    
    Args:
        gdf: GeoDataFrame of POI points/polygons (projected to metres).
    
    Returns:
        Tuple of (spatial_index, geometry_list, attributes_list).
    """
    if gdf is None or gdf.empty:
        return None, [], []
    
    geoms = list(gdf.geometry)
    
    # Store attributes if needed for filtering, though currently we rely on
    # the loader to pre-filter POIs based on tags.
    attrs = gdf.drop(columns='geometry').to_dict('records')
    
    sindex = STRtree(geoms)
    return sindex, geoms, attrs


def _calculate_novack_social_cost(
    midpoint: Point,
    length: float,
    poi_sindex: Optional[STRtree],
    poi_geoms: List,
    buffer_radius: float = BUFFER_RADIUS
) -> float:
    """
    Calculate Novack social cost: Length / Count of Third Places.
    
    Novack (2018): "The sociability factor was computed... by dividing its length
    by the number of third place features [in 50m buffer]."
    
    Args:
        midpoint: Edge midpoint (projected coordinates).
        length: Edge length in metres.
        poi_sindex: Spatial index for POIs.
        poi_geoms: List of POI geometries.
        buffer_radius: Search radius in metres.
    
    Returns:
        Float cost value (lower = better/more social).
    """
    if poi_sindex is None or len(poi_geoms) == 0:
        # No POIs at all -> Max cost (Length / epsilon)
        return length / MIN_social_COUNT
    
    buffer = midpoint.buffer(buffer_radius)
    
    candidate_indices = poi_sindex.query(buffer)
    if len(candidate_indices) == 0:
         return length / MIN_social_COUNT
    
    # Count actual intersections
    poi_count = 0
    for idx in candidate_indices:
        geom = poi_geoms[idx]
        try:
            if buffer.intersects(geom):
                poi_count += 1
        except Exception:
            continue
    
    # Apply Novack formula
    # If count is 0, use epsilon to avoid infinity
    # Higher count -> Lower cost
    effective_count = max(MIN_social_COUNT,  float(poi_count))
    return length / effective_count


def process_graph_social(
    graph: nx.MultiDiGraph,
    poi_gdf: Optional[gpd.GeoDataFrame]
) -> nx.MultiDiGraph:
    """
    Process all edges to assign social costs using Novack (2018) methodology.
    
    Args:
        graph: NetworkX MultiDiGraph with node coordinates.
        poi_gdf: GeoDataFrame of POI points/polygons (projected).
    
    Returns:
        Graph with raw_social_cost added to edges.
    """
    if graph is None:
        return graph
    
    if poi_gdf is None or poi_gdf.empty:
        print("[SocialProcessor] No POIs provided, skipping.")
        return graph
    
    print("[SocialProcessor] Building spatial index...")
    poi_sindex, poi_geoms, _ = _build_spatial_index(poi_gdf)
    
    poi_count = len(poi_geoms)
    print(f"[SocialProcessor] Found {poi_count} Third Places to analyse")
    
    edges_processed = 0
    total_edges = graph.number_of_edges()
    report_interval = max(1, total_edges // 10)
    
    print(f"[SocialProcessor] Processing {total_edges} edges (Novack Density)...")
    t0 = time.perf_counter()
    
    # Track stats for normalization advice
    costs = []
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        try:
            # Get geometry
            start_lon = graph.nodes[u].get('x', 0)
            start_lat = graph.nodes[u].get('y', 0)
            end_lon = graph.nodes[v].get('x', 0)
            end_lat = graph.nodes[v].get('y', 0)
            
            start_x, start_y = _transform_coords(start_lon, start_lat)
            end_x, end_y = _transform_coords(end_lon, end_lat)
            
            # Simple midpoint approximation for the "buffer around segment"
            # For short urban segments, this is very close to buffering the line
            mid_x = (start_x + end_x) / 2
            mid_y = (start_y + end_y) / 2
            midpoint = Point(mid_x, mid_y)
            
            length = data.get('length', 1.0) # Default to 1m if missing
            
            social_cost = _calculate_novack_social_cost(
                midpoint, length, poi_sindex, poi_geoms
            )
            
            graph[u][v][key]['raw_social_cost'] = social_cost
            costs.append(social_cost)
            
        except Exception:
            graph[u][v][key]['raw_social_cost'] = 1000.0 # High fallback cost
        
        edges_processed += 1
        if edges_processed % report_interval == 0:
            pct = (edges_processed / total_edges) * 100
            print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
    
    elapsed = time.perf_counter() - t0
    
    if costs:
        min_c, max_c = min(costs), max(costs)
        print(f"[SocialProcessor] Cost Range: {min_c:.2f} - {max_c:.2f}")
        
    print(f"[SocialProcessor] Processed {edges_processed} edges in {elapsed:.2f}s")
    
    return graph
