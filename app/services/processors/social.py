"""
Social Processor Module

Calculates proximity to tourist and social points of interest for each graph edge.

OSM tags used:
- tourism: attraction, viewpoint, museum, artwork, gallery, information
- historic: castle, monument, memorial, ruins, archaeological_site
- amenity: cafe, restaurant, pub, theatre, cinema

Edge attribute added:
- raw_social_cost: 0.0 = near POIs, 1.0 = no POIs (lower = better for routing)
"""

import time
from typing import List, Tuple, Optional
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point
from shapely.strtree import STRtree
from pyproj import Transformer


# Configuration constants
FAST_BUFFER_RADIUS: float = 50.0  # metres - larger buffer for POIs (sparse features)

# POI categories and their OSM tags
POI_TOURISM_TAGS = frozenset({
    'attraction', 'viewpoint', 'museum', 'artwork', 'gallery', 
    'information', 'picnic_site', 'zoo', 'theme_park'
})

POI_HISTORIC_TAGS = frozenset({
    'castle', 'monument', 'memorial', 'ruins', 'archaeological_site',
    'church', 'manor', 'fort', 'battlefield', 'boundary_stone'
})

POI_AMENITY_TAGS = frozenset({
    'cafe', 'restaurant', 'pub', 'bar', 'theatre', 'cinema',
    'arts_centre', 'community_centre', 'library'
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


def _build_spatial_index(gdf: Optional[gpd.GeoDataFrame]) -> Tuple[Optional[STRtree], List]:
    """
    Build R-tree spatial index for efficient geometry lookups.
    
    Args:
        gdf: GeoDataFrame of POI points/polygons (projected to metres).
    
    Returns:
        Tuple of (spatial_index, geometry_list).
    """
    if gdf is None or gdf.empty:
        return None, []
    
    geoms = list(gdf.geometry)
    sindex = STRtree(geoms)
    return sindex, geoms


def _calculate_social_score_fast(
    midpoint: Point,
    poi_sindex: Optional[STRtree],
    poi_geoms: List,
    buffer_radius: float = FAST_BUFFER_RADIUS
) -> float:
    """
    Calculate social/POI proximity score using buffer intersection (FAST mode).
    
    For point POIs, we count the number within the buffer.
    For polygon POIs (e.g., parks with attractions), we measure intersection area.
    
    The score is normalised: presence of any POI within buffer gives a score,
    with diminishing returns for additional POIs.
    
    Args:
        midpoint: Edge midpoint (projected coordinates).
        poi_sindex: Spatial index for POIs.
        poi_geoms: List of POI geometries.
        buffer_radius: Search radius in metres.
    
    Returns:
        Float between 0.0 and 1.0 representing POI proximity.
    """
    if poi_sindex is None or len(poi_geoms) == 0:
        return 0.0
    
    buffer = midpoint.buffer(buffer_radius)
    
    candidate_indices = poi_sindex.query(buffer)
    if len(candidate_indices) == 0:
        return 0.0
    
    # Count POIs within buffer and calculate proximity score
    poi_count = 0
    total_proximity = 0.0
    
    for idx in candidate_indices:
        geom = poi_geoms[idx]
        try:
            if buffer.intersects(geom):
                # Calculate distance-weighted score
                if geom.geom_type == 'Point':
                    distance = midpoint.distance(geom)
                else:
                    distance = midpoint.distance(geom.centroid)
                
                # Closer POIs score higher (inverse distance, normalised)
                if distance < buffer_radius:
                    proximity = 1.0 - (distance / buffer_radius)
                    total_proximity += proximity
                    poi_count += 1
        except Exception:
            continue
    
    if poi_count == 0:
        return 0.0
    
    # Diminishing returns: 1 POI = 0.5, 2 = 0.7, 3+ = 0.85, 5+ = 0.95
    # Using average proximity weighted by count
    avg_proximity = total_proximity / poi_count
    count_factor = min(1.0, 0.3 + (poi_count * 0.15))  # Caps at 1.0 around 5 POIs
    
    return min(1.0, avg_proximity * count_factor * 1.5)


def process_graph_social(
    graph: nx.MultiDiGraph,
    poi_gdf: Optional[gpd.GeoDataFrame]
) -> nx.MultiDiGraph:
    """
    Process all edges to assign social/POI proximity scores.
    
    Uses 50m buffer around edge midpoints to calculate proximity
    to tourist attractions, historic sites, and social amenities.
    
    Args:
        graph: NetworkX MultiDiGraph with node coordinates.
        poi_gdf: GeoDataFrame of POI points/polygons (projected).
    
    Returns:
        Graph with raw_social_cost added to edges (0.0 = near POIs, 1.0 = no POIs).
    """
    if graph is None:
        return graph
    
    if poi_gdf is None or poi_gdf.empty:
        print("[SocialProcessor] No POIs provided, skipping.")
        return graph
    
    print("[SocialProcessor] Building spatial index...")
    poi_sindex, poi_geoms = _build_spatial_index(poi_gdf)
    
    poi_count = len(poi_geoms)
    print(f"[SocialProcessor] Found {poi_count} POIs in dataset")
    
    edges_processed = 0
    total_edges = graph.number_of_edges()
    report_interval = max(1, total_edges // 10)
    
    print(f"[SocialProcessor] Processing {total_edges} edges...")
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
            
            social_score = _calculate_social_score_fast(midpoint, poi_sindex, poi_geoms)
            
            # Convert to cost (lower = better)
            graph[u][v][key]['raw_social_cost'] = 1.0 - social_score
            
        except Exception:
            graph[u][v][key]['raw_social_cost'] = 1.0
        
        edges_processed += 1
        if edges_processed % report_interval == 0:
            pct = (edges_processed / total_edges) * 100
            print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
    
    elapsed = time.perf_counter() - t0
    print(f"[SocialProcessor] Processed {edges_processed} edges in {elapsed:.2f}s")
    
    return graph
