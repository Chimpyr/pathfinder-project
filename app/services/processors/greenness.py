"""
Greenness Processor Module

Calculates proximity or visibility of green spaces for each graph edge.
Supports FAST (buffer intersection) and NOVACK (isovist ray-casting) modes.

Edge attribute added:
- raw_green_cost: 0.0 = very green, 1.0 = no green (lower = better for routing)

Based on Novack et al. (2018) methodology for isovist-based green visibility.
"""

import math
import time
from typing import List, Tuple, Optional
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString
from shapely.strtree import STRtree
from pyproj import Transformer


# Configuration constants
SEARCH_RADIUS: float = 100.0  # metres - visibility search radius for NOVACK
SAMPLE_INTERVAL: float = 50.0  # metres - edge discretisation interval
RAY_COUNT: int = 72  # Number of rays (360/72 = 5° resolution)
MIN_EDGE_LENGTH: float = 1.0  # Skip very short edges
FAST_BUFFER_RADIUS: float = 30.0  # metres - buffer for FAST mode

# Isovist area for normalisation (π × radius²)
MAX_VISIBLE_AREA: float = math.pi * (SEARCH_RADIUS ** 2)

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


def _discretise_edge(
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


def _calculate_isovist(
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
        return point.buffer(radius)
    
    # Get candidate buildings within the search radius
    search_buffer = point.buffer(radius)
    candidate_indices = buildings_sindex.query(search_buffer)
    
    if len(candidate_indices) == 0:
        return search_buffer
    
    candidates = [buildings_geoms[i] for i in candidate_indices]
    
    # Cast rays and find endpoints
    ray_endpoints = []
    angle_step = 2 * math.pi / ray_count
    px, py = point.x, point.y
    
    for i in range(ray_count):
        angle = i * angle_step
        rx = px + radius * math.cos(angle)
        ry = py + radius * math.sin(angle)
        ray_line = LineString([(px, py), (rx, ry)])
        
        min_dist = radius
        for building in candidates:
            if ray_line.intersects(building):
                try:
                    intersection = ray_line.intersection(building)
                    if intersection.is_empty:
                        continue
                    
                    if intersection.geom_type == 'Point':
                        dist = point.distance(intersection)
                    elif intersection.geom_type in ('MultiPoint', 'GeometryCollection'):
                        dist = min(point.distance(geom) for geom in intersection.geoms 
                                   if not geom.is_empty)
                    elif intersection.geom_type == 'LineString':
                        dist = point.distance(Point(intersection.coords[0]))
                    else:
                        dist = point.distance(intersection)
                    
                    if dist < min_dist:
                        min_dist = dist
                except Exception:
                    continue
        
        endpoint_x = px + min_dist * math.cos(angle)
        endpoint_y = py + min_dist * math.sin(angle)
        ray_endpoints.append((endpoint_x, endpoint_y))
    
    if ray_endpoints:
        ray_endpoints.append(ray_endpoints[0])
        try:
            isovist = Polygon(ray_endpoints)
            if not isovist.is_valid:
                isovist = isovist.buffer(0)
            return isovist
        except Exception:
            return search_buffer
    
    return search_buffer


def _calculate_green_score_novack(
    isovist: Polygon,
    green_sindex: Optional[STRtree],
    green_geoms: List
) -> float:
    """
    Calculate green visibility score for an isovist polygon (NOVACK mode).
    
    Implements Novack et al. (2018) Equation 1:
        relative_green_area = visible_green_area / max_visible_area
    
    Args:
        isovist: The visible polygon from _calculate_isovist().
        green_sindex: Spatial index for green areas.
        green_geoms: List of green area geometries.
    
    Returns:
        Float between 0.0 and 1.0 representing proportion of visible green.
    """
    if green_sindex is None or len(green_geoms) == 0:
        return 0.0
    
    if isovist is None or isovist.is_empty:
        return 0.0
    
    candidate_indices = green_sindex.query(isovist)
    if len(candidate_indices) == 0:
        return 0.0
    
    visible_green_area = 0.0
    for idx in candidate_indices:
        green_geom = green_geoms[idx]
        try:
            if isovist.intersects(green_geom):
                intersection = isovist.intersection(green_geom)
                if not intersection.is_empty:
                    visible_green_area += intersection.area
        except Exception:
            continue
    
    score = visible_green_area / MAX_VISIBLE_AREA
    return min(1.0, max(0.0, score))


def _calculate_green_score_fast(
    midpoint: Point,
    green_sindex: Optional[STRtree],
    green_geoms: List,
    buffer_radius: float = FAST_BUFFER_RADIUS
) -> float:
    """
    Calculate green proximity score using buffer intersection (FAST mode).
    
    Args:
        midpoint: Edge midpoint (projected coordinates).
        green_sindex: Spatial index for green areas.
        green_geoms: List of green area geometries.
        buffer_radius: Search radius in metres.
    
    Returns:
        Float between 0.0 and 1.0 representing green coverage proportion.
    """
    if green_sindex is None or len(green_geoms) == 0:
        return 0.0
    
    buffer = midpoint.buffer(buffer_radius)
    buffer_area = buffer.area
    
    if buffer_area <= 0:
        return 0.0
    
    candidate_indices = green_sindex.query(buffer)
    if len(candidate_indices) == 0:
        return 0.0
    
    green_area = 0.0
    for idx in candidate_indices:
        geom = green_geoms[idx]
        try:
            if not geom.is_valid:
                geom = geom.buffer(0)
            if buffer.intersects(geom):
                intersection = buffer.intersection(geom)
                if not intersection.is_empty:
                    green_area += intersection.area
        except Exception:
            continue
    
    return min(1.0, green_area / buffer_area)


def process_graph_greenness_fast(
    graph: nx.MultiDiGraph,
    green_gdf: Optional[gpd.GeoDataFrame]
) -> nx.MultiDiGraph:
    """
    Process all edges to assign green proximity scores (FAST mode).
    
    Uses 30m buffer around edge midpoints to calculate proximity
    to green spaces. Much faster than isovist ray-casting.
    
    Args:
        graph: NetworkX MultiDiGraph with node coordinates.
        green_gdf: GeoDataFrame of green space polygons (projected).
    
    Returns:
        Graph with raw_green_cost added to edges (0.0 = green, 1.0 = no green).
    """
    if graph is None:
        return graph
    
    if green_gdf is None or green_gdf.empty:
        print("[GreennessProcessor FAST] No green areas provided, skipping.")
        return graph
    
    print("[GreennessProcessor FAST] Building spatial index...")
    green_sindex, green_geoms = _build_spatial_index(green_gdf)
    
    edges_processed = 0
    total_edges = graph.number_of_edges()
    report_interval = max(1, total_edges // 10)
    
    print(f"[GreennessProcessor FAST] Processing {total_edges} edges...")
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
            
            green_score = _calculate_green_score_fast(midpoint, green_sindex, green_geoms)
            
            # Convert to cost (lower = better)
            graph[u][v][key]['raw_green_cost'] = 1.0 - green_score
            
        except Exception:
            graph[u][v][key]['raw_green_cost'] = 1.0
        
        edges_processed += 1
        if edges_processed % report_interval == 0:
            pct = (edges_processed / total_edges) * 100
            print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
    
    elapsed = time.perf_counter() - t0
    print(f"[GreennessProcessor FAST] Processed {edges_processed} edges in {elapsed:.2f}s")
    
    return graph


def process_graph_greenness_novack(
    graph: nx.MultiDiGraph,
    green_gdf: Optional[gpd.GeoDataFrame],
    buildings_gdf: Optional[gpd.GeoDataFrame]
) -> nx.MultiDiGraph:
    """
    Process all edges to assign green visibility scores (NOVACK mode).
    
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
        Graph with raw_green_cost added to edges (0.0 = green, 1.0 = no green).
    """
    if graph is None:
        return graph
    
    if green_gdf is None or green_gdf.empty:
        print("[GreennessProcessor NOVACK] No green areas provided, skipping.")
        return graph
    
    print("[GreennessProcessor NOVACK] Building spatial indices...")
    green_sindex, green_geoms = _build_spatial_index(green_gdf)
    buildings_sindex, buildings_geoms = _build_spatial_index(buildings_gdf)
    
    edges_processed = 0
    total_edges = graph.number_of_edges()
    report_interval = max(1, total_edges // 20)
    
    print(f"[GreennessProcessor NOVACK] Processing {total_edges} edges...")
    t0 = time.perf_counter()
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        try:
            start_lon = graph.nodes[u].get('x', 0)
            start_lat = graph.nodes[u].get('y', 0)
            end_lon = graph.nodes[v].get('x', 0)
            end_lat = graph.nodes[v].get('y', 0)
            
            start_x, start_y = _transform_coords(start_lon, start_lat)
            end_x, end_y = _transform_coords(end_lon, end_lat)
            
            start_point = Point(start_x, start_y)
            end_point = Point(end_x, end_y)
            
            length = data.get('length', 0.0)
            if not isinstance(length, (int, float)) or length < MIN_EDGE_LENGTH:
                graph[u][v][key]['raw_green_cost'] = 1.0
                edges_processed += 1
                continue
            
            sample_points = _discretise_edge(start_point, end_point, length)
            
            scores = []
            for pt in sample_points:
                isovist = _calculate_isovist(pt, buildings_sindex, buildings_geoms)
                score = _calculate_green_score_novack(isovist, green_sindex, green_geoms)
                scores.append(score)
            
            avg_score = sum(scores) / len(scores) if scores else 0.0
            graph[u][v][key]['raw_green_cost'] = 1.0 - avg_score
            
        except Exception:
            graph[u][v][key]['raw_green_cost'] = 1.0
        
        edges_processed += 1
        if edges_processed % report_interval == 0:
            pct = (edges_processed / total_edges) * 100
            print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
    
    elapsed = time.perf_counter() - t0
    print(f"[GreennessProcessor NOVACK] Processed {edges_processed} edges in {elapsed:.2f}s")
    
    return graph
