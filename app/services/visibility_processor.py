"""
Visibility Processor Module

Calculates green visibility scores for graph edges using isovist-based analysis.
Implements Novack et al. (2018) methodology where buildings occlude the view of green spaces.

The visibility score represents the proportion of visible green area within a 100m radius,
accounting for buildings blocking the line of sight.
"""

import math
from typing import List, Tuple, Optional
import numpy as np
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString
from shapely.strtree import STRtree
from shapely.ops import unary_union
from pyproj import Transformer

# Configuration constants
SEARCH_RADIUS: float = 100.0  # metres - visibility search radius
SAMPLE_INTERVAL: float = 50.0  # metres - edge discretisation interval
RAY_COUNT: int = 72  # Number of rays (360/72 = 5° resolution)
MIN_EDGE_LENGTH: float = 1.0  # Skip very short edges

# Isovist area for normalisation (π × radius²)
MAX_VISIBLE_AREA: float = math.pi * (SEARCH_RADIUS ** 2)

# Coordinate transformer: WGS84 (lat/lon) to UTM zone 30N (metres)
_transformer: Optional[Transformer] = None

def get_transformer() -> Transformer:
    """Get or create the coordinate transformer (WGS84 -> EPSG:32630)."""
    global _transformer
    if _transformer is None:
        _transformer = Transformer.from_crs("EPSG:4326", "EPSG:32630", always_xy=True)
    return _transformer

def transform_coords(lon: float, lat: float) -> Tuple[float, float]:
    """Transform WGS84 coordinates to projected metres."""
    transformer = get_transformer()
    x, y = transformer.transform(lon, lat)
    return x, y


def build_spatial_indices(
    green_gdf: gpd.GeoDataFrame,
    buildings_gdf: gpd.GeoDataFrame
) -> Tuple[Optional[STRtree], Optional[STRtree], List, List]:
    """
    Build R-tree spatial indices for efficient geometry lookups.
    
    Args:
        green_gdf: GeoDataFrame of green space polygons (projected to metres).
        buildings_gdf: GeoDataFrame of building polygons (projected to metres).
    
    Returns:
        Tuple of (green_sindex, buildings_sindex, green_geoms, building_geoms)
        where geoms lists are needed for index-to-geometry mapping.
    """
    green_geoms = []
    buildings_geoms = []
    green_sindex = None
    buildings_sindex = None
    
    if green_gdf is not None and not green_gdf.empty:
        green_geoms = list(green_gdf.geometry)
        green_sindex = STRtree(green_geoms)
    
    if buildings_gdf is not None and not buildings_gdf.empty:
        buildings_geoms = list(buildings_gdf.geometry)
        buildings_sindex = STRtree(buildings_geoms)
    
    return green_sindex, buildings_sindex, green_geoms, buildings_geoms


def discretise_edge(
    start_point: Point,
    end_point: Point,
    length: float,
    interval: float = SAMPLE_INTERVAL
) -> List[Point]:
    """
    Discretise an edge into sample points for visibility calculation.
    
    Short edges (< interval) return only start and end points.
    Longer edges are sampled at regular intervals along the line.
    
    Args:
        start_point: Edge start coordinate (projected).
        end_point: Edge end coordinate (projected).
        length: Edge length in metres.
        interval: Sampling interval in metres.
    
    Returns:
        List of shapely Points along the edge.
    """
    if length < MIN_EDGE_LENGTH:
        return [start_point]
    
    if length <= interval:
        return [start_point, end_point]
    
    # Interpolate along the edge
    line = LineString([start_point, end_point])
    num_points = max(2, int(length / interval) + 1)
    
    points = []
    for i in range(num_points):
        fraction = i / (num_points - 1)
        pt = line.interpolate(fraction, normalized=True)
        points.append(pt)
    
    return points


def calculate_isovist(
    point: Point,
    buildings_sindex: Optional[STRtree],
    buildings_geoms: List,
    radius: float = SEARCH_RADIUS,
    ray_count: int = RAY_COUNT
) -> Polygon:
    """
    Calculate the visible polygon (isovist) from a point using ray-casting.
    
    Casts rays in all directions from the observation point, trimming each ray
    at the first building intersection. The resulting polygon represents
    what is visible from that location.
    
    Args:
        point: Observation point (projected coordinates).
        buildings_sindex: Spatial index for buildings.
        buildings_geoms: List of building geometries.
        radius: Maximum visibility radius in metres.
        ray_count: Number of rays to cast (higher = more accurate but slower).
    
    Returns:
        Polygon representing the visible area from the point.
    """
    if buildings_sindex is None or len(buildings_geoms) == 0:
        # No buildings - full circle is visible
        return point.buffer(radius)
    
    # Get candidate buildings within the search radius
    search_buffer = point.buffer(radius)
    candidate_indices = buildings_sindex.query(search_buffer)
    
    if len(candidate_indices) == 0:
        return search_buffer
    
    # Collect candidate geometries
    candidates = [buildings_geoms[i] for i in candidate_indices]
    
    # Cast rays and find endpoints
    ray_endpoints = []
    angle_step = 2 * math.pi / ray_count
    px, py = point.x, point.y
    
    for i in range(ray_count):
        angle = i * angle_step
        
        # Ray endpoint at full radius
        rx = px + radius * math.cos(angle)
        ry = py + radius * math.sin(angle)
        ray_line = LineString([(px, py), (rx, ry)])
        
        # Check for building intersections
        min_dist = radius
        for building in candidates:
            if ray_line.intersects(building):
                intersection = ray_line.intersection(building)
                if intersection.is_empty:
                    continue
                
                # Get nearest intersection point
                if intersection.geom_type == 'Point':
                    dist = point.distance(intersection)
                elif intersection.geom_type in ('MultiPoint', 'GeometryCollection'):
                    dist = min(point.distance(geom) for geom in intersection.geoms 
                              if not geom.is_empty)
                elif intersection.geom_type == 'LineString':
                    # Use the start of the intersecting line segment
                    dist = point.distance(Point(intersection.coords[0]))
                else:
                    dist = point.distance(intersection)
                
                if dist < min_dist:
                    min_dist = dist
        
        # Endpoint is at intersection distance or full radius
        endpoint_x = px + min_dist * math.cos(angle)
        endpoint_y = py + min_dist * math.sin(angle)
        ray_endpoints.append((endpoint_x, endpoint_y))
    
    # Close the polygon
    if ray_endpoints:
        ray_endpoints.append(ray_endpoints[0])
        try:
            isovist = Polygon(ray_endpoints)
            if not isovist.is_valid:
                isovist = isovist.buffer(0)  # Fix self-intersections
            return isovist
        except Exception:
            return search_buffer
    
    return search_buffer


def calculate_green_score(
    isovist: Polygon,
    green_sindex: Optional[STRtree],
    green_geoms: List
) -> float:
    """
    Calculate the green visibility score for an isovist polygon.
    
    Implements Novack et al. (2018) Equation 1:
        relative_green_area = visible_green_area / max_visible_area
    
    Args:
        isovist: The visible polygon from calculate_isovist().
        green_sindex: Spatial index for green areas.
        green_geoms: List of green area geometries.
    
    Returns:
        Float between 0.0 and 1.0 representing proportion of visible green.
    """
    if green_sindex is None or len(green_geoms) == 0:
        return 0.0
    
    if isovist is None or isovist.is_empty:
        return 0.0
    
    # Query green areas that intersect the isovist
    candidate_indices = green_sindex.query(isovist)
    
    if len(candidate_indices) == 0:
        return 0.0
    
    # Calculate visible green area
    visible_green_area = 0.0
    for idx in candidate_indices:
        green_geom = green_geoms[idx]
        if isovist.intersects(green_geom):
            intersection = isovist.intersection(green_geom)
            if not intersection.is_empty:
                visible_green_area += intersection.area
    
    # Normalise by maximum possible visible area
    score = visible_green_area / MAX_VISIBLE_AREA
    return min(1.0, max(0.0, score))  # Clamp to [0, 1]


def calculate_edge_green_score(
    edge_data: dict,
    graph: nx.MultiDiGraph,
    u: int,
    v: int,
    green_sindex: Optional[STRtree],
    green_geoms: List,
    buildings_sindex: Optional[STRtree],
    buildings_geoms: List
) -> float:
    """
    Calculate the average green visibility score for a single edge.
    
    Args:
        edge_data: Edge attribute dictionary.
        graph: The NetworkX graph (for node coordinates).
        u: Source node ID.
        v: Target node ID.
        green_sindex: Spatial index for green areas.
        green_geoms: List of green geometries.
        buildings_sindex: Spatial index for buildings.
        buildings_geoms: List of building geometries.
    
    Returns:
        Average green visibility score across sample points.
    """
    # Get node coordinates (x=longitude, y=latitude in WGS84)
    try:
        start_lon = graph.nodes[u].get('x', 0)
        start_lat = graph.nodes[u].get('y', 0)
        end_lon = graph.nodes[v].get('x', 0)
        end_lat = graph.nodes[v].get('y', 0)
    except KeyError:
        return 0.0
    
    # Transform to projected coordinates (metres)
    start_x, start_y = transform_coords(start_lon, start_lat)
    end_x, end_y = transform_coords(end_lon, end_lat)
    
    start_point = Point(start_x, start_y)
    end_point = Point(end_x, end_y)
    
    # Get edge length
    length = edge_data.get('length', 0.0)
    if not isinstance(length, (int, float)) or length < MIN_EDGE_LENGTH:
        return 0.0
    
    # Discretise edge into sample points
    sample_points = discretise_edge(start_point, end_point, length)
    
    if not sample_points:
        return 0.0
    
    # Calculate score at each sample point
    scores = []
    for pt in sample_points:
        isovist = calculate_isovist(pt, buildings_sindex, buildings_geoms)
        score = calculate_green_score(isovist, green_sindex, green_geoms)
        scores.append(score)
    
    return sum(scores) / len(scores) if scores else 0.0


def process_graph_greenness(
    graph: nx.MultiDiGraph,
    green_gdf: Optional[gpd.GeoDataFrame],
    buildings_gdf: Optional[gpd.GeoDataFrame]
) -> nx.MultiDiGraph:
    """
    Process all edges to assign green visibility scores.
    
    Implements Novack et al. (2018) methodology:
    1. Discretise each edge into sample points
    2. Calculate isovist (visible polygon) at each point
    3. Measure visible green area within the isovist
    4. Store averaged score on edge attributes
    
    Args:
        graph: NetworkX MultiDiGraph with node coordinates.
        green_gdf: GeoDataFrame of green space polygons (projected).
        buildings_gdf: GeoDataFrame of building polygons (projected).
    
    Returns:
        The same graph with green_visibility_score added to edges.
    """
    if graph is None:
        return graph
    
    # Validate inputs
    if green_gdf is None or green_gdf.empty:
        print("[VisibilityProcessor] No green areas provided, skipping.")
        return graph
    
    # Build spatial indices
    print("[VisibilityProcessor] Building spatial indices...")
    green_sindex, buildings_sindex, green_geoms, buildings_geoms = \
        build_spatial_indices(green_gdf, buildings_gdf)
    
    edges_processed = 0
    total_edges = graph.number_of_edges()
    
    print(f"[VisibilityProcessor] Processing {total_edges} edges...")
    
    # Progress reporting interval
    report_interval = max(1, total_edges // 20)
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        # Calculate green visibility score
        score = calculate_edge_green_score(
            data, graph, u, v,
            green_sindex, green_geoms,
            buildings_sindex, buildings_geoms
        )
        
        # Store on edge
        graph[u][v][key]['green_visibility_score'] = score
        
        # TODO: raw_green_cost will be computed when WSM A* is implemented
        # Formula: raw_green_cost = length / (score + 0.5)
        
        edges_processed += 1
        
        if edges_processed % report_interval == 0:
            pct = (edges_processed / total_edges) * 100
            print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
    
    print(f"[VisibilityProcessor] Processed {edges_processed} edges with green_visibility_score.")
    
    return graph


# =============================================================================
# FAST Buffer Algorithm (Alternative to Novack Isovist)
# =============================================================================

# FAST mode constants
FAST_BUFFER_RADIUS: float = 30.0  # metres - buffer around edge midpoint

def calculate_edge_scenic_score_fast(
    edge_data: dict,
    graph: nx.MultiDiGraph,
    u: int,
    v: int,
    green_sindex: Optional[STRtree],
    green_geoms: List,
    water_sindex: Optional[STRtree],
    water_geoms: List
) -> Tuple[float, float]:
    """
    Calculate scenic score using simple buffer intersection (FAST mode).
    
    Uses edge midpoint buffered by 30m and calculates intersection with
    green areas and water features. Much faster than isovist ray-casting.
    
    Args:
        edge_data: Edge attribute dictionary.
        graph: The NetworkX graph.
        u: Source node ID.
        v: Target node ID.
        green_sindex: Spatial index for green areas.
        green_geoms: List of green geometries.
        water_sindex: Spatial index for water features.
        water_geoms: List of water geometries.
    
    Returns:
        Tuple of (green_score, water_score) both 0.0-1.0.
    """
    # Get node coordinates
    try:
        start_lon = graph.nodes[u].get('x', 0)
        start_lat = graph.nodes[u].get('y', 0)
        end_lon = graph.nodes[v].get('x', 0)
        end_lat = graph.nodes[v].get('y', 0)
    except KeyError:
        return 0.0, 0.0
    
    # Transform to projected coordinates
    start_x, start_y = transform_coords(start_lon, start_lat)
    end_x, end_y = transform_coords(end_lon, end_lat)
    
    # Use edge midpoint for buffer
    mid_x = (start_x + end_x) / 2
    mid_y = (start_y + end_y) / 2
    midpoint = Point(mid_x, mid_y)
    
    # Create search buffer
    buffer = midpoint.buffer(FAST_BUFFER_RADIUS)
    buffer_area = buffer.area
    
    if buffer_area <= 0:
        return 0.0, 0.0
    
    # Calculate green intersection
    green_score = 0.0
    if green_sindex is not None and green_geoms:
        candidates = green_sindex.query(buffer)
        green_area = 0.0
        for idx in candidates:
            geom = green_geoms[idx]
            if buffer.intersects(geom):
                intersection = buffer.intersection(geom)
                if not intersection.is_empty:
                    green_area += intersection.area
        green_score = min(1.0, green_area / buffer_area)
    
    # Calculate water intersection
    water_score = 0.0
    if water_sindex is not None and water_geoms:
        candidates = water_sindex.query(buffer)
        water_area = 0.0
        for idx in candidates:
            geom = water_geoms[idx]
            if buffer.intersects(geom):
                intersection = buffer.intersection(geom)
                if not intersection.is_empty:
                    water_area += intersection.area
        water_score = min(1.0, water_area / buffer_area)
    
    return green_score, water_score


def process_graph_greenness_fast(
    graph: nx.MultiDiGraph,
    green_gdf: Optional[gpd.GeoDataFrame],
    water_gdf: Optional[gpd.GeoDataFrame] = None
) -> nx.MultiDiGraph:
    """
    FAST scenic scoring using buffer intersection.
    
    Simpler and faster alternative to Novack isovist method.
    Uses 30m buffer around edge midpoints to calculate proximity
    to green spaces and water features.
    
    Args:
        graph: NetworkX MultiDiGraph with node coordinates.
        green_gdf: GeoDataFrame of green space polygons (projected).
        water_gdf: GeoDataFrame of water feature polygons (projected).
    
    Returns:
        Graph with green_proximity_score and water_proximity_score on edges.
    """
    if graph is None:
        return graph
    
    # Validate inputs
    has_green = green_gdf is not None and not green_gdf.empty
    has_water = water_gdf is not None and not water_gdf.empty
    
    if not has_green and not has_water:
        print("[VisibilityProcessor FAST] No green/water areas provided, skipping.")
        return graph
    
    # Build spatial indices
    print("[VisibilityProcessor FAST] Building spatial indices...")
    green_sindex = None
    green_geoms = []
    water_sindex = None
    water_geoms = []
    
    if has_green:
        green_geoms = list(green_gdf.geometry)
        green_sindex = STRtree(green_geoms)
    
    if has_water:
        water_geoms = list(water_gdf.geometry)
        water_sindex = STRtree(water_geoms)
    
    edges_processed = 0
    total_edges = graph.number_of_edges()
    
    print(f"[VisibilityProcessor FAST] Processing {total_edges} edges...")
    
    # Progress reporting
    report_interval = max(1, total_edges // 10)
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        # Calculate scenic scores
        green_score, water_score = calculate_edge_scenic_score_fast(
            data, graph, u, v,
            green_sindex, green_geoms,
            water_sindex, water_geoms
        )
        
        # Store on edge
        graph[u][v][key]['green_proximity_score'] = green_score
        graph[u][v][key]['water_proximity_score'] = water_score
        
        # Combined scenic score (weighted: green 70%, water 30%)
        scenic_score = (green_score * 0.7) + (water_score * 0.3)
        graph[u][v][key]['scenic_score'] = scenic_score
        
        edges_processed += 1
        
        if edges_processed % report_interval == 0:
            pct = (edges_processed / total_edges) * 100
            print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
    
    print(f"[VisibilityProcessor FAST] Processed {edges_processed} edges with scenic scores.")
    
    return graph

