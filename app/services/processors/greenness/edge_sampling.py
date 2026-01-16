"""
Edge Sampling Greenness Processor

Calculates greenness by sampling multiple points along each edge geometry.
This provides better coverage than midpoint-only sampling, particularly for
long edges running alongside parks.

Algorithm:
    1. For each edge, extract or construct the line geometry
    2. Sample points every N metres along the line (default: 20m)
    3. Calculate buffer intersection score at each sample point
    4. Return the average score across all samples

Typical processing time: ~60-90 seconds for 325,000 edges
"""

import time
from typing import Optional, List
import numpy as np
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, LineString

from .base import GreennessProcessor
from .utils import (
    build_spatial_index,
    project_gdf,
    calculate_point_buffer_score,
    get_edge_geometry,
    get_edge_midpoint,
)


# Default configuration
# Buffer radius increased to 50m to capture more green space - 30m had same
# variance problem as FAST mode (70% edges with no green detected)
DEFAULT_BUFFER_RADIUS: float = 50.0    # metres - buffer around each sample
DEFAULT_SAMPLE_INTERVAL: float = 20.0  # metres - distance between samples
MIN_SAMPLES: int = 2                    # minimum samples per edge


class EdgeSamplingProcessor(GreennessProcessor):
    """
    Edge sampling greenness processor.
    
    Samples multiple points along each edge geometry to calculate an
    average greenness score. This provides much better coverage than
    midpoint-only sampling, especially for long edges bordering parks.
    
    Attributes:
        buffer_radius: Buffer size in metres (default: 30m).
        sample_interval: Distance between samples in metres (default: 20m).
    
    Example:
        >>> processor = EdgeSamplingProcessor(
        ...     buffer_radius=30.0,
        ...     sample_interval=20.0
        ... )
        >>> graph = processor.process(graph, green_gdf)
    """
    
    def __init__(
        self,
        buffer_radius: float = DEFAULT_BUFFER_RADIUS,
        sample_interval: float = DEFAULT_SAMPLE_INTERVAL
    ):
        """
        Initialise the Edge Sampling processor.
        
        Args:
            buffer_radius: Buffer radius around each sample point in metres.
                Smaller values (20-30m) are more precise but may miss
                green spaces slightly further from the path.
            sample_interval: Distance between sample points in metres.
                Smaller values give more accurate results but are slower.
        """
        self._buffer_radius = buffer_radius
        self._sample_interval = sample_interval
    
    @property
    def name(self) -> str:
        """Human-readable processor name."""
        return "Edge Sampling"
    
    @property
    def buffer_radius(self) -> float:
        """Buffer radius in metres."""
        return self._buffer_radius
    
    @property
    def sample_interval(self) -> float:
        """Sample interval in metres."""
        return self._sample_interval
    
    def _sample_edge(self, geometry: LineString) -> List[Point]:
        """
        Generate sample points along an edge geometry.
        
        Args:
            geometry: LineString geometry in projected coordinates.
        
        Returns:
            List of Points sampled along the edge.
        """
        length = geometry.length
        
        if length <= 0:
            return [geometry.centroid]
        
        # Calculate number of samples
        num_samples = max(MIN_SAMPLES, int(length / self._sample_interval) + 1)
        
        # Generate evenly spaced sample points
        samples = []
        for i in range(num_samples):
            fraction = i / (num_samples - 1) if num_samples > 1 else 0.5
            point = geometry.interpolate(fraction, normalized=True)
            samples.append(point)
        
        return samples
    
    def _calculate_edge_score(
        self,
        geometry: LineString,
        green_sindex,
        green_geoms: List
    ) -> float:
        """
        Calculate greenness score for an edge by averaging sample scores.
        
        Args:
            geometry: Edge geometry (projected LineString).
            green_sindex: R-tree spatial index for green polygons.
            green_geoms: List of green polygon geometries.
        
        Returns:
            Average green cost (0.0 = green, 1.0 = no green).
        """
        samples = self._sample_edge(geometry)
        
        if not samples:
            return 1.0
        
        scores = [
            calculate_point_buffer_score(
                point, green_sindex, green_geoms, self._buffer_radius
            )
            for point in samples
        ]
        
        return sum(scores) / len(scores)
    
    def process(
        self,
        graph: nx.MultiDiGraph,
        green_gdf: Optional[gpd.GeoDataFrame],
        **kwargs
    ) -> nx.MultiDiGraph:
        """
        Process graph and add green costs using edge sampling.
        
        Args:
            graph: NetworkX MultiDiGraph with node coordinates.
            green_gdf: GeoDataFrame of green area polygons.
            **kwargs: Ignored (for interface compatibility).
        
        Returns:
            Graph with 'raw_green_cost' attribute on each edge.
        """
        self.validate_graph(graph)
        
        print(f"[{self.name}] Processing {len(graph.edges)} edges "
              f"(buffer: {self.buffer_radius}m, interval: {self.sample_interval}m)...")
        t0 = time.perf_counter()
        
        # Project green areas to metres
        green_gdf_proj = project_gdf(green_gdf)
        
        # Build spatial index
        green_sindex, green_geoms = build_spatial_index(green_gdf_proj)
        
        if green_sindex is None:
            print(f"  > [{self.name}] No green areas found, setting all edges to 1.0")
            for u, v, key, data in graph.edges(keys=True, data=True):
                data['raw_green_cost'] = 1.0
            return graph
        
        # Process edges
        total_edges = len(graph.edges)
        report_interval = max(1, total_edges // 10)
        edges_processed = 0
        fallback_count = 0
        
        for u, v, key, data in graph.edges(keys=True, data=True):
            # Get edge geometry
            geometry = get_edge_geometry(graph, u, v, key, data)
            
            if geometry is None:
                # Fallback to midpoint if no geometry available
                midpoint = get_edge_midpoint(graph, u, v)
                if midpoint is not None:
                    data['raw_green_cost'] = calculate_point_buffer_score(
                        midpoint, green_sindex, green_geoms, self._buffer_radius
                    )
                else:
                    data['raw_green_cost'] = 1.0
                fallback_count += 1
            else:
                # Sample along edge geometry
                data['raw_green_cost'] = self._calculate_edge_score(
                    geometry, green_sindex, green_geoms
                )
            
            edges_processed += 1
            if edges_processed % report_interval == 0:
                pct = (edges_processed / total_edges) * 100
                print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
        
        elapsed = time.perf_counter() - t0
        print(f"[{self.name}] Processed {edges_processed} edges in {elapsed:.2f}s")
        
        if fallback_count > 0:
            print(f"  > [{self.name}] Fallback to midpoint for {fallback_count} edges "
                  f"({100*fallback_count/total_edges:.1f}%)")
        
        self.log_distribution(graph)
        
        return graph
