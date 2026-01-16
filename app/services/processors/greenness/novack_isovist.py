"""
Novack Isovist Greenness Processor

Calculates greenness using visibility-based isovist ray-casting.
This is the most accurate method but also the slowest.

Implements Novack et al. (2018) methodology:
    1. Discretise each edge into sample points
    2. Cast rays from each point, clipping at building boundaries
    3. Calculate visible green area within the isovist polygon
    4. Average scores across all sample points

Typical processing time: ~10+ minutes for 325,000 edges

Reference:
    Novack, T., Wang, Z., & Zipf, A. (2018). A System for Generating
    Customised Green Routes Based on OpenStreetMap Data.
"""

import math
import time
from typing import Optional, List, Tuple
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString

from .base import GreennessProcessor
from .utils import (
    build_spatial_index,
    project_gdf,
    transform_coords,
)


# Configuration constants for isovist calculation
SEARCH_RADIUS: float = 100.0   # metres - maximum visibility distance
SAMPLE_INTERVAL: float = 50.0  # metres - edge sampling interval
RAY_COUNT: int = 72            # number of rays (360/72 = 5° resolution)
MIN_EDGE_LENGTH: float = 1.0   # skip very short edges

# Maximum possible visible area (π × radius²) for normalisation
MAX_VISIBLE_AREA: float = math.pi * (SEARCH_RADIUS ** 2)


class NovackIsovistProcessor(GreennessProcessor):
    """
    Novack isovist greenness processor.
    
    Uses ray-casting to calculate what can be seen from each point
    along an edge, accounting for building occlusion. This provides
    the most realistic representation of pedestrian-perceived greenness.
    
    Attributes:
        search_radius: Maximum visibility distance in metres.
        sample_interval: Distance between sample points in metres.
        ray_count: Number of rays to cast (higher = more accurate).
    
    Example:
        >>> processor = NovackIsovistProcessor()
        >>> graph = processor.process(
        ...     graph, green_gdf, buildings_gdf=buildings_gdf
        ... )
    """
    
    def __init__(
        self,
        search_radius: float = SEARCH_RADIUS,
        sample_interval: float = SAMPLE_INTERVAL,
        ray_count: int = RAY_COUNT
    ):
        """
        Initialise the Novack Isovist processor.
        
        Args:
            search_radius: Maximum visibility distance in metres.
            sample_interval: Distance between sample points in metres.
            ray_count: Number of rays to cast for isovist calculation.
        """
        self._search_radius = search_radius
        self._sample_interval = sample_interval
        self._ray_count = ray_count
    
    @property
    def name(self) -> str:
        """Human-readable processor name."""
        return "Novack Isovist"
    
    def _discretise_edge(
        self,
        start_point: Point,
        end_point: Point,
        length: float
    ) -> List[Point]:
        """
        Discretise an edge into sample points.
        
        Args:
            start_point: Edge start (projected coordinates).
            end_point: Edge end (projected coordinates).
            length: Edge length in metres.
        
        Returns:
            List of sample Points along the edge.
        """
        if length < MIN_EDGE_LENGTH:
            return [start_point]
        
        if length <= self._sample_interval:
            return [start_point, end_point]
        
        line = LineString([start_point, end_point])
        num_points = max(2, int(length / self._sample_interval) + 1)
        
        points = []
        for i in range(num_points):
            fraction = i / (num_points - 1)
            pt = line.interpolate(fraction, normalized=True)
            points.append(pt)
        
        return points
    
    def _calculate_isovist(
        self,
        point: Point,
        buildings_sindex,
        buildings_geoms: List
    ) -> Polygon:
        """
        Calculate the visible polygon (isovist) from a point.
        
        Casts rays in all directions and trims each at the first
        building intersection.
        
        Args:
            point: Observation point (projected coordinates).
            buildings_sindex: R-tree spatial index for buildings.
            buildings_geoms: List of building geometries.
        
        Returns:
            Polygon representing the visible area.
        """
        radius = self._search_radius
        
        if buildings_sindex is None or len(buildings_geoms) == 0:
            return point.buffer(radius)
        
        # Query candidate buildings within search radius
        search_buffer = point.buffer(radius)
        candidate_indices = buildings_sindex.query(search_buffer)
        
        if len(candidate_indices) == 0:
            return search_buffer
        
        candidates = [buildings_geoms[i] for i in candidate_indices]
        
        # Cast rays
        ray_endpoints = []
        angle_step = 2 * math.pi / self._ray_count
        px, py = point.x, point.y
        
        for i in range(self._ray_count):
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
                            dist = min(
                                point.distance(geom) 
                                for geom in intersection.geoms 
                                if not geom.is_empty
                            )
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
        
        # Construct isovist polygon
        if ray_endpoints:
            ray_endpoints.append(ray_endpoints[0])  # Close the polygon
            try:
                isovist = Polygon(ray_endpoints)
                if not isovist.is_valid:
                    isovist = isovist.buffer(0)  # Fix invalid geometry
                return isovist
            except Exception:
                return search_buffer
        
        return search_buffer
    
    def _calculate_green_score(
        self,
        isovist: Polygon,
        green_sindex,
        green_geoms: List
    ) -> float:
        """
        Calculate green visibility score for an isovist.
        
        Implements Novack et al. (2018) Equation 1:
            relative_green = visible_green_area / max_visible_area
        
        Args:
            isovist: Visible polygon from ray-casting.
            green_sindex: R-tree spatial index for green areas.
            green_geoms: List of green polygon geometries.
        
        Returns:
            Green visibility score (0.0 to 1.0).
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
    
    def process(
        self,
        graph: nx.MultiDiGraph,
        green_gdf: Optional[gpd.GeoDataFrame],
        buildings_gdf: Optional[gpd.GeoDataFrame] = None,
        **kwargs
    ) -> nx.MultiDiGraph:
        """
        Process graph and add green costs using isovist ray-casting.
        
        Args:
            graph: NetworkX MultiDiGraph with node coordinates.
            green_gdf: GeoDataFrame of green area polygons.
            buildings_gdf: GeoDataFrame of building footprints.
                Required for accurate isovist calculation.
            **kwargs: Ignored (for interface compatibility).
        
        Returns:
            Graph with 'raw_green_cost' attribute on each edge.
        """
        self.validate_graph(graph)
        
        print(f"[{self.name}] Processing {len(graph.edges)} edges "
              f"(radius: {self._search_radius}m, rays: {self._ray_count})...")
        t0 = time.perf_counter()
        
        # Project data to metres
        green_gdf_proj = project_gdf(green_gdf)
        buildings_gdf_proj = project_gdf(buildings_gdf)
        
        # Build spatial indices
        print(f"  > [{self.name}] Building spatial indices...")
        green_sindex, green_geoms = build_spatial_index(green_gdf_proj)
        buildings_sindex, buildings_geoms = build_spatial_index(buildings_gdf_proj)
        
        if green_sindex is None:
            print(f"  > [{self.name}] No green areas found, setting all edges to 1.0")
            for u, v, key, data in graph.edges(keys=True, data=True):
                data['raw_green_cost'] = 1.0
            return graph
        
        # Process edges
        total_edges = len(graph.edges)
        report_interval = max(1, total_edges // 20)  # 5% intervals
        edges_processed = 0
        
        for u, v, key, data in graph.edges(keys=True, data=True):
            try:
                # Get node coordinates
                start_lon = graph.nodes[u].get('x', 0)
                start_lat = graph.nodes[u].get('y', 0)
                end_lon = graph.nodes[v].get('x', 0)
                end_lat = graph.nodes[v].get('y', 0)
                
                # Transform to projected coordinates
                start_x, start_y = transform_coords(start_lon, start_lat)
                end_x, end_y = transform_coords(end_lon, end_lat)
                
                start_point = Point(start_x, start_y)
                end_point = Point(end_x, end_y)
                
                length = data.get('length', 0.0)
                if not isinstance(length, (int, float)) or length < MIN_EDGE_LENGTH:
                    data['raw_green_cost'] = 1.0
                    edges_processed += 1
                    continue
                
                # Sample points along edge
                sample_points = self._discretise_edge(start_point, end_point, length)
                
                # Calculate green score at each sample point
                scores = []
                for pt in sample_points:
                    isovist = self._calculate_isovist(
                        pt, buildings_sindex, buildings_geoms
                    )
                    score = self._calculate_green_score(
                        isovist, green_sindex, green_geoms
                    )
                    scores.append(score)
                
                # Average scores and convert to cost (invert)
                avg_score = sum(scores) / len(scores) if scores else 0.0
                data['raw_green_cost'] = 1.0 - avg_score
                
            except Exception:
                data['raw_green_cost'] = 1.0
            
            edges_processed += 1
            if edges_processed % report_interval == 0:
                pct = (edges_processed / total_edges) * 100
                print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
        
        elapsed = time.perf_counter() - t0
        print(f"[{self.name}] Processed {edges_processed} edges in {elapsed:.2f}s")
        
        self.log_distribution(graph)
        
        return graph
