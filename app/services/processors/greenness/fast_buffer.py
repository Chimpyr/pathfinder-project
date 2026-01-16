"""
Fast Buffer Greenness Processor

Calculates greenness using simple buffer intersection at edge midpoints.
This is the fastest method but may miss paths running alongside parks.

Algorithm:
    1. For each edge, find the midpoint
    2. Create a circular buffer (default 50m radius)
    3. Measure intersection area with green polygons
    4. Score = intersection_area / buffer_area

Typical processing time: ~30 seconds for 325,000 edges
"""

import time
from typing import Optional
import networkx as nx
import geopandas as gpd

from .base import GreennessProcessor
from .utils import (
    build_spatial_index,
    project_gdf,
    calculate_point_buffer_score,
    get_edge_midpoint,
)


# Default buffer radius in metres
DEFAULT_BUFFER_RADIUS: float = 50.0


class FastBufferProcessor(GreennessProcessor):
    """
    Fast greenness processor using point buffer intersection.
    
    Creates a buffer around each edge's midpoint and measures what fraction
    of the buffer area intersects with green space polygons.
    
    This is the fastest method but has limitations:
        - Only samples the midpoint (misses long edges)
        - Paths running alongside parks may not intersect
    
    Attributes:
        buffer_radius: Buffer size in metres (default: 50m).
    
    Example:
        >>> processor = FastBufferProcessor(buffer_radius=30.0)
        >>> graph = processor.process(graph, green_gdf)
    """
    
    def __init__(self, buffer_radius: float = DEFAULT_BUFFER_RADIUS):
        """
        Initialise the Fast Buffer processor.
        
        Args:
            buffer_radius: Buffer radius in metres (default: 50m).
                Larger values capture more green but may bleed onto
                adjacent streets.
        """
        self._buffer_radius = buffer_radius
    
    @property
    def name(self) -> str:
        """Human-readable processor name."""
        return "Fast Buffer"
    
    @property
    def buffer_radius(self) -> float:
        """Buffer radius in metres."""
        return self._buffer_radius
    
    def process(
        self,
        graph: nx.MultiDiGraph,
        green_gdf: Optional[gpd.GeoDataFrame],
        **kwargs
    ) -> nx.MultiDiGraph:
        """
        Process graph and add green costs using buffer intersection.
        
        Args:
            graph: NetworkX MultiDiGraph with node coordinates.
            green_gdf: GeoDataFrame of green area polygons.
            **kwargs: Ignored (for interface compatibility).
        
        Returns:
            Graph with 'raw_green_cost' attribute on each edge.
        """
        self.validate_graph(graph)
        
        print(f"[{self.name}] Processing {len(graph.edges)} edges "
              f"(buffer radius: {self.buffer_radius}m)...")
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
        
        for u, v, key, data in graph.edges(keys=True, data=True):
            # Get edge midpoint
            midpoint = get_edge_midpoint(graph, u, v)
            
            if midpoint is None:
                data['raw_green_cost'] = 1.0
            else:
                data['raw_green_cost'] = calculate_point_buffer_score(
                    midpoint, green_sindex, green_geoms, self.buffer_radius
                )
            
            edges_processed += 1
            if edges_processed % report_interval == 0:
                pct = (edges_processed / total_edges) * 100
                print(f"  > Progress: {pct:.0f}% ({edges_processed}/{total_edges})")
        
        elapsed = time.perf_counter() - t0
        print(f"[{self.name}] Processed {edges_processed} edges in {elapsed:.2f}s")
        
        self.log_distribution(graph)
        
        return graph
