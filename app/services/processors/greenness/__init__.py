"""
Greenness Processing Package

Provides multiple strategies for calculating greenness scores on graph edges.
Each strategy implements the GreennessProcessor abstract base class.

Available modes (set via config.py GREENNESS_MODE):
    - OFF: Skip greenness processing entirely
    - FAST: Point buffer intersection (quick, ~30 seconds)
    - EDGE_SAMPLING: Multi-point sampling along edges (balanced, ~60 seconds)
    - NOVACK: Full isovist ray-casting (accurate but slow, ~10+ minutes)

Usage:
    from app.services.processors.greenness import get_processor, process_graph
    
    # Using factory function
    processor = get_processor('EDGE_SAMPLING')
    graph = processor.process(graph, green_gdf)
    
    # Or using convenience function
    graph = process_graph(graph, green_gdf, mode='EDGE_SAMPLING')

Author: ScenicPathFinder
"""

from typing import Optional, Dict, Type
import networkx as nx
import geopandas as gpd

from .base import GreennessProcessor
from .fast_buffer import FastBufferProcessor
from .edge_sampling import EdgeSamplingProcessor
from .novack_isovist import NovackIsovistProcessor


# Registry of available processors
_PROCESSOR_REGISTRY: Dict[str, Type[GreennessProcessor]] = {
    'FAST': FastBufferProcessor,
    'EDGE_SAMPLING': EdgeSamplingProcessor,
    'NOVACK': NovackIsovistProcessor,
}


def get_processor(mode: str) -> GreennessProcessor:
    """
    Factory function to get a greenness processor by mode name.
    
    Args:
        mode: Processing mode string (case-insensitive).
              Valid values: FAST, EDGE_SAMPLING, NOVACK
    
    Returns:
        Instance of the appropriate GreennessProcessor subclass.
    
    Raises:
        ValueError: If mode is not recognised.
    
    Example:
        >>> processor = get_processor('EDGE_SAMPLING')
        >>> graph = processor.process(graph, green_gdf)
    """
    mode_upper = mode.upper().strip()
    
    if mode_upper not in _PROCESSOR_REGISTRY:
        available = ', '.join(sorted(_PROCESSOR_REGISTRY.keys()))
        raise ValueError(
            f"Unknown greenness mode: '{mode}'. "
            f"Available modes: {available}"
        )
    
    return _PROCESSOR_REGISTRY[mode_upper]()


def process_graph(
    graph: nx.MultiDiGraph,
    green_gdf: Optional[gpd.GeoDataFrame],
    mode: str = 'EDGE_SAMPLING',
    buildings_gdf: Optional[gpd.GeoDataFrame] = None,
    **kwargs
) -> nx.MultiDiGraph:
    """
    Convenience function to process graph greenness using specified mode.
    
    This is a shorthand for get_processor(mode).process(graph, green_gdf, ...).
    
    Args:
        graph: NetworkX MultiDiGraph with node coordinates.
        green_gdf: GeoDataFrame of green area polygons.
        mode: Processing mode (FAST, EDGE_SAMPLING, or NOVACK).
        buildings_gdf: Building footprints (required for NOVACK mode only).
        **kwargs: Additional arguments passed to processor.
    
    Returns:
        Graph with 'raw_green_cost' attribute added to each edge.
    
    Raises:
        ValueError: If mode is not recognised or required data is missing.
    """
    processor = get_processor(mode)
    
    # NOVACK requires buildings
    if mode.upper() == 'NOVACK':
        return processor.process(graph, green_gdf, buildings_gdf=buildings_gdf, **kwargs)
    
    return processor.process(graph, green_gdf, **kwargs)


def register_processor(mode: str, processor_class: Type[GreennessProcessor]) -> None:
    """
    Register a custom greenness processor.
    
    Allows extending the package with additional processing strategies
    without modifying this file.
    
    Args:
        mode: Mode name to register (will be uppercased).
        processor_class: Class implementing GreennessProcessor.
    
    Example:
        >>> class MyCustomProcessor(GreennessProcessor):
        ...     ...
        >>> register_processor('CUSTOM', MyCustomProcessor)
    """
    _PROCESSOR_REGISTRY[mode.upper()] = processor_class


# Public API
__all__ = [
    'GreennessProcessor',
    'FastBufferProcessor',
    'EdgeSamplingProcessor',
    'NovackIsovistProcessor',
    'get_processor',
    'process_graph',
    'register_processor',
]
