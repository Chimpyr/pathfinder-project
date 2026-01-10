"""
Scenic Orchestrator Module

Coordinates the scenic processing pipeline based on configuration.
Calls enabled processors in sequence and manages data extraction.

Processor modes are read from Flask config:
- GREENNESS_MODE: OFF | FAST | NOVACK
- WATER_MODE: OFF | FAST
- SOCIAL_MODE: OFF | FAST
"""

import time
from typing import Any, Optional, Dict
import networkx as nx

from app.services.processors.greenness import (
    process_graph_greenness_fast,
    process_graph_greenness_novack
)
from app.services.processors.water import process_graph_water
from app.services.processors.social import process_graph_social

try:
    from flask import current_app, has_app_context
except ImportError:
    current_app = None
    def has_app_context(): return False


def _get_config(key: str, default: Any) -> Any:
    """Get configuration value from Flask app or return default."""
    if has_app_context() and current_app:
        return current_app.config.get(key, default)
    return default


def get_greenness_mode() -> str:
    """Get the configured greenness processing mode."""
    return _get_config('GREENNESS_MODE', 'FAST').upper()


def get_water_mode() -> str:
    """Get the configured water processing mode."""
    return _get_config('WATER_MODE', 'OFF').upper()


def get_social_mode() -> str:
    """Get the configured social/POI processing mode."""
    return _get_config('SOCIAL_MODE', 'OFF').upper()


def process_scenic_attributes(
    graph: nx.MultiDiGraph,
    loader,
    timings: Optional[Dict[str, float]] = None
) -> nx.MultiDiGraph:
    """
    Run all enabled scenic processors on the graph.
    
    Reads config for GREENNESS_MODE, WATER_MODE, SOCIAL_MODE
    and calls corresponding processors in sequence.
    
    Args:
        graph: NetworkX MultiDiGraph with node coordinates.
        loader: OSMDataLoader instance for extracting feature geodataframes.
        timings: Optional dict to store timing information.
    
    Returns:
        Graph with scenic attributes added based on enabled modes.
    
    Raises:
        ValueError: If graph is None.
    """
    if graph is None:
        raise ValueError("Graph cannot be None")
    
    if timings is None:
        timings = {}
    
    greenness_mode = get_greenness_mode()
    water_mode = get_water_mode()
    social_mode = get_social_mode()
    
    print(f"[ScenicOrchestrator] Modes: GREENNESS={greenness_mode}, "
          f"WATER={water_mode}, SOCIAL={social_mode}")
    
    # Process greenness
    if greenness_mode == 'FAST':
        print("[ScenicOrchestrator] Processing greenness (FAST mode)...")
        t0 = time.perf_counter()
        
        green_gdf = loader.extract_green_areas()
        timings['Extract Green Areas'] = time.perf_counter() - t0
        
        t0 = time.perf_counter()
        graph = process_graph_greenness_fast(graph, green_gdf)
        timings['Greenness Processing (FAST)'] = time.perf_counter() - t0
        
    elif greenness_mode == 'NOVACK':
        print("[ScenicOrchestrator] Processing greenness (NOVACK mode)...")
        t0 = time.perf_counter()
        
        green_gdf = loader.extract_green_areas()
        timings['Extract Green Areas'] = time.perf_counter() - t0
        
        t0 = time.perf_counter()
        buildings_gdf = loader.extract_buildings()
        timings['Extract Buildings'] = time.perf_counter() - t0
        
        t0 = time.perf_counter()
        graph = process_graph_greenness_novack(graph, green_gdf, buildings_gdf)
        timings['Greenness Processing (NOVACK)'] = time.perf_counter() - t0
        
    else:
        print("[ScenicOrchestrator] Greenness processing disabled.")
    
    # Process water
    if water_mode == 'FAST':
        print("[ScenicOrchestrator] Processing water (FAST mode)...")
        t0 = time.perf_counter()
        
        water_gdf = loader.extract_water()
        timings['Extract Water'] = time.perf_counter() - t0
        
        t0 = time.perf_counter()
        graph = process_graph_water(graph, water_gdf)
        timings['Water Processing'] = time.perf_counter() - t0
        
    else:
        print("[ScenicOrchestrator] Water processing disabled.")
    
    # Process social/POI
    if social_mode == 'FAST':
        print("[ScenicOrchestrator] Processing social POIs (FAST mode)...")
        t0 = time.perf_counter()
        
        poi_gdf = loader.extract_pois()
        timings['Extract POIs'] = time.perf_counter() - t0
        
        t0 = time.perf_counter()
        graph = process_graph_social(graph, poi_gdf)
        timings['Social Processing'] = time.perf_counter() - t0
        
    else:
        print("[ScenicOrchestrator] Social processing disabled.")
    
    return graph
