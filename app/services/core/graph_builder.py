"""
Graph Builder Module

Stateless graph building functions extracted from GraphManager.
Designed to be called from both synchronous Flask requests and
asynchronous Celery workers.

This module contains no Flask dependencies and no class-level state,
making it safe for use in distributed worker processes.

Author: ScenicPathFinder
"""

import time
import networkx as nx
from typing import Dict, Optional, Tuple, Any

from app.services.core.data_loader import OSMDataLoader
from app.services.processors.quietness import process_graph_quietness
from app.services.processors.orchestrator import process_scenic_attributes
from app.services.processors.elevation import process_graph_elevation
from app.services.processors.normalisation import normalise_graph_costs
from app.services.core.cache_manager import get_cache_manager


class GraphBuildResult:
    """
    Container for graph build results.
    
    Attributes:
        graph: The processed NetworkX graph.
        region_name: Name of the region (e.g., 'bristol').
        timings: Dictionary of processing stage timings.
        node_count: Number of nodes in the graph.
        edge_count: Number of edges in the graph.
        pbf_path: Path to the source PBF file.
    """
    
    def __init__(
        self,
        graph: nx.MultiDiGraph,
        region_name: str,
        timings: Dict[str, float],
        pbf_path: Optional[str] = None
    ):
        """
        Initialise a GraphBuildResult.
        
        Args:
            graph: The processed NetworkX graph.
            region_name: Name of the region.
            timings: Dictionary of processing stage timings.
            pbf_path: Path to the source PBF file.
        """
        self.graph = graph
        self.region_name = region_name
        self.timings = timings
        self.node_count = graph.number_of_nodes()
        self.edge_count = graph.number_of_edges()
        self.pbf_path = pbf_path
    
    def to_metadata(self) -> Dict[str, Any]:
        """
        Convert to metadata dictionary (primitives only, no graph).
        
        Suitable for returning from Celery tasks where we want to
        avoid pickling the entire graph.
        
        Returns:
            Dictionary containing build metadata.
        """
        return {
            'region_name': self.region_name,
            'node_count': self.node_count,
            'edge_count': self.edge_count,
            'timings': self.timings,
            'pbf_path': self.pbf_path,
            'total_time': self.timings.get('TOTAL', 0),
        }


def build_graph(
    bbox: Optional[Tuple[float, float, float, float]],
    region_name: str,
    greenness_mode: str = 'FAST',
    elevation_mode: str = 'OFF',
    normalisation_mode: str = 'STATIC',
    save_to_cache: bool = True,
    clip_to_bbox: bool = True
) -> GraphBuildResult:
    """
    Build and process a graph for the specified region.
    
    This is a stateless function that can be called from either
    the Flask application or a Celery worker.
    
    Args:
        bbox: Bounding box tuple (min_lat, min_lon, max_lat, max_lon).
              If None, defaults to Bristol.
        region_name: Name identifier for the region (e.g., 'bristol').
        greenness_mode: Greenness processing mode ('FAST', 'EDGE_SAMPLING', 'NOVACK').
        elevation_mode: Elevation processing mode ('OFF', 'API', 'LOCAL').
        normalisation_mode: Normalisation mode ('STATIC', 'DYNAMIC').
        save_to_cache: Whether to save the processed graph to disk cache.
        clip_to_bbox: Whether to clip the graph to a buffered bbox for memory efficiency.
                      Default True. Set False for full-region loading.
    
    Returns:
        GraphBuildResult containing the processed graph and metadata.
    
    Raises:
        ValueError: If region_name is empty.
        RuntimeError: If graph loading fails.
    """
    if not region_name:
        raise ValueError("region_name cannot be empty")
    
    total_start = time.perf_counter()
    timings = {}
    
    print(f"[GraphBuilder] Building graph for region: {region_name}")
    print(f"[GraphBuilder] Modes - Greenness: {greenness_mode}, Elevation: {elevation_mode}")
    
    # Calculate buffered bbox for clipping (if enabled)
    # 5km buffer allows for scenic detours without hitting graph boundary
    clip_bbox = None
    if clip_to_bbox and bbox is not None:
        buffer_km = 5
        buffer_deg = buffer_km / 111.0  # ~0.045 degrees per km at mid-latitudes
        clip_bbox = (
            bbox[0] - buffer_deg,  # min_lat
            bbox[1] - buffer_deg,  # min_lon
            bbox[2] + buffer_deg,  # max_lat
            bbox[3] + buffer_deg   # max_lon
        )
        print(f"[GraphBuilder] Clipping enabled with {buffer_km}km buffer")
    
    # Initialise data loader
    loader = OSMDataLoader()
    
    # Load the base graph from PBF (optionally clipped)
    t0 = time.perf_counter()
    try:
        graph = loader.load_graph(bbox, clip_bbox=clip_bbox)
    except Exception as e:
        raise RuntimeError(f"Failed to load graph for region '{region_name}': {e}") from e
    
    timings['Graph Loading'] = time.perf_counter() - t0
    print(f"  [Timer] Graph Loading: {timings['Graph Loading']:.2f}s")
    
    # Process quietness attributes
    t0 = time.perf_counter()
    print("[GraphBuilder] Processing quietness attributes...")
    graph = process_graph_quietness(graph)
    timings['Quietness Processing'] = time.perf_counter() - t0
    print(f"  [Timer] Quietness Processing: {timings['Quietness Processing']:.2f}s")
    
    # Process scenic attributes (greenness, water, social) via orchestrator
    # The orchestrator will use the greenness_mode from the loader or fallback
    print("[GraphBuilder] Processing scenic attributes via orchestrator...")
    t0 = time.perf_counter()
    graph = process_scenic_attributes(graph, loader, timings)
    timings['Scenic Processing (Total)'] = time.perf_counter() - t0
    
    # Process elevation based on mode
    if elevation_mode.upper() in ('API', 'FAST', 'LOCAL'):
        actual_mode = 'LOCAL' if elevation_mode.upper() == 'LOCAL' else 'API'
        print(f"[GraphBuilder] Processing elevation gradients ({actual_mode} mode)...")
        
        t0 = time.perf_counter()
        graph = process_graph_elevation(graph, mode=actual_mode)
        timings[f'Elevation Processing ({actual_mode})'] = time.perf_counter() - t0
        print(f"  [Timer] Elevation Processing: {timings[f'Elevation Processing ({actual_mode})']:.2f}s")
    else:
        print("[GraphBuilder] Elevation processing disabled.")
    
    # Normalise all cost attributes to 0-1 range
    print(f"[GraphBuilder] Normalising cost attributes ({normalisation_mode})...")
    t0 = time.perf_counter()
    graph = normalise_graph_costs(graph, mode=normalisation_mode)
    timings['Normalisation'] = time.perf_counter() - t0
    print(f"  [Timer] Normalisation: {timings['Normalisation']:.2f}s")
    
    # Compatibility shim for older code expecting graph.features
    if not hasattr(graph, 'features'):
        graph.features = None
    
    # Calculate total time
    total_time = time.perf_counter() - total_start
    timings['TOTAL'] = total_time
    
    # Print timing summary
    _print_timing_summary(region_name, timings, total_time)
    
    # Create result object
    result = GraphBuildResult(
        graph=graph,
        region_name=region_name,
        timings=timings,
        pbf_path=loader.file_path
    )
    
    # Save to disk cache if requested
    if save_to_cache:
        cache_mgr = get_cache_manager()
        cache_mgr.save_graph(
            graph,
            region_name,
            greenness_mode,
            elevation_mode,
            loader.file_path,
            bbox=clip_bbox  # Use clip_bbox for cache key (must match routes.py lookup)
        )
        print(f"[GraphBuilder] Graph saved to disk cache for region: {region_name}")
    
    return result


def _print_timing_summary(region_name: str, timings: Dict[str, float], total_time: float) -> None:
    """
    Print a formatted timing summary to console.
    
    Args:
        region_name: Name of the region being processed.
        timings: Dictionary of timing values.
        total_time: Total processing time.
    """
    print("\n" + "=" * 50)
    print(f"[GraphBuilder] TIMING SUMMARY ({region_name})")
    print("=" * 50)
    
    for step, duration in timings.items():
        if step != 'TOTAL':
            pct = (duration / total_time) * 100 if total_time > 0 else 0
            print(f"  {step}: {duration:.2f}s ({pct:.1f}%)")
    
    print("-" * 50)
    print(f"  TOTAL: {total_time:.2f}s")
    print("=" * 50 + "\n")


def find_region_for_bbox(bbox: Optional[Tuple[float, float, float, float]]) -> Tuple[str, Optional[str]]:
    """
    Determine which region a bounding box falls within.
    
    Args:
        bbox: Bounding box tuple (min_lat, min_lon, max_lat, max_lon).
              If None, defaults to Bristol.
    
    Returns:
        Tuple of (region_name, pbf_url).
    """
    loader = OSMDataLoader()
    
    if bbox is None:
        return 'bristol', None
    
    # Calculate centre point
    lat = (bbox[0] + bbox[2]) / 2
    lon = (bbox[1] + bbox[3]) / 2
    
    # Use loader's method to find the right PBF
    pbf_url, region_name = loader._find_pbf_url_for_location(lat, lon)
    
    if region_name is None:
        region_name = 'unknown'
    
    return region_name, pbf_url
