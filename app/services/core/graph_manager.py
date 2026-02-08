"""
Graph Manager Module

Manages the retrieval and caching of street network graphs with LRU eviction.
Supports multi-region routing by caching multiple graphs keyed by region name.
"""

import os
import time
import networkx as nx
from typing import Dict, Optional, Tuple, Any
from app.services.core.data_loader import OSMDataLoader
from app.services.processors.quietness import process_graph_quietness
from app.services.processors.orchestrator import process_scenic_attributes
from app.services.processors.elevation import process_graph_elevation
from app.services.processors.normalisation import normalise_graph_costs
from app.services.core.cache_manager import get_cache_manager

try:
    from flask import current_app, has_app_context
except ImportError:
    current_app = None
    def has_app_context(): return False


def get_config(key: str, default: Any) -> Any:
    """Get configuration value from Flask app or return default."""
    if has_app_context() and current_app:
        return current_app.config.get(key, default)
    return default


def get_greenness_mode() -> str:
    """Get the configured greenness processing mode."""
    return get_config('GREENNESS_MODE', 'FAST').upper()


def get_max_cached_regions() -> int:
    """Get the maximum number of regions to cache."""
    return get_config('MAX_CACHED_REGIONS', 3)


def get_elevation_mode() -> str:
    """Get the configured elevation processing mode."""
    return get_config('ELEVATION_MODE', 'FAST').upper()


class CachedGraph:
    """Container for a cached graph with metadata."""
    
    def __init__(self, graph: nx.MultiDiGraph, region_name: str, 
                 bbox: Optional[Tuple], loader: OSMDataLoader, timings: Dict):
        self.graph = graph
        self.region_name = region_name
        self.bbox = bbox
        self.loader = loader
        self.timings = timings
        self.last_used = time.time()
    
    def touch(self):
        """Update last used timestamp."""
        self.last_used = time.time()


class GraphManager:
    """
    Manages the retrieval and caching of street network graphs.
    
    Uses LRU (Least Recently Used) eviction to cache multiple region graphs.
    This allows efficient multi-region routing without reloading for each query.
    """
    
    # Class-level cache: region_name -> CachedGraph
    _cache: Dict[str, CachedGraph] = {}
    _current_region: Optional[str] = None
    
    @classmethod
    def _find_region_for_bbox(cls, bbox: Optional[Tuple]) -> Tuple[str, str]:
        """
        Determine which region a bbox falls within.
        
        Returns:
            Tuple of (region_name, pbf_url)
        """
        loader = OSMDataLoader()
        
        if bbox is None:
            # Default to Bristol
            return 'bristol', None
        
        # Calculate centre point
        lat = (bbox[0] + bbox[2]) / 2
        lon = (bbox[1] + bbox[3]) / 2
        
        # Use loader's method to find the right PBF
        pbf_url, region_name = loader._find_pbf_url_for_location(lat, lon)
        
        if region_name is None:
            region_name = 'unknown'
        
        return region_name, pbf_url
    
    @classmethod
    def _evict_lru(cls):
        """Evict the least recently used cache entry."""
        if not cls._cache:
            return
        
        oldest_key = min(cls._cache.keys(), 
                        key=lambda k: cls._cache[k].last_used)
        
        print(f"[GraphManager] Evicting cached region: {oldest_key}")
        del cls._cache[oldest_key]
    
    @classmethod
    def _load_graph_for_region(cls, bbox: Optional[Tuple], 
                                region_name: str) -> CachedGraph:
        """
        Load and process a graph for a specific region.
        
        Delegates to the stateless GraphBuilder for actual processing.
        
        Args:
            bbox: Bounding box tuple (min_lat, min_lon, max_lat, max_lon).
            region_name: Name identifier for the region.
        
        Returns:
            CachedGraph containing the processed graph and metadata.
        """
        from app.services.core.graph_builder import build_graph
        
        # Get processing modes from config
        greenness_mode = get_greenness_mode()
        elevation_mode = get_elevation_mode()
        normalisation_mode = get_config('NORMALISATION_MODE', 'STATIC')
        
        print(f"[GraphManager] Delegating graph build to GraphBuilder for: {region_name}")
        
        # Use stateless builder
        result = build_graph(
            bbox=bbox,
            region_name=region_name,
            greenness_mode=greenness_mode,
            elevation_mode=elevation_mode,
            normalisation_mode=normalisation_mode,
            save_to_cache=True
        )
        
        # Create CachedGraph from result
        # Note: We need the loader for compatibility, so create one
        loader = OSMDataLoader()
        loader.ensure_data_for_bbox(bbox)
        
        return CachedGraph(
            graph=result.graph,
            region_name=region_name,
            bbox=bbox,
            loader=loader,
            timings=result.timings
        )

    
    @classmethod
    def get_graph(cls, bbox: Optional[Tuple] = None) -> nx.MultiDiGraph:
        """
        Returns the street network graph for the given bbox.
        
        Uses LRU cache to store multiple region graphs. If the region is
        already cached, returns the cached graph. Otherwise loads a new
        graph and caches it, evicting the oldest if at capacity.
        
        Args:
            bbox: Bounding box tuple (min_lat, min_lon, max_lat, max_lon).
                  If None, defaults to Bristol.

        Returns:
            networkx.MultiDiGraph: The processed graph with features.
        """
        # Determine which region this bbox falls within
        region_name, _ = cls._find_region_for_bbox(bbox)
        greenness_mode = get_greenness_mode()
        elevation_mode = get_elevation_mode()
        
        # Check memory cache first
        if region_name in cls._cache:
            print(f"[GraphManager] Memory cache HIT for region: {region_name}")
            cached = cls._cache[region_name]
            cached.touch()
            cls._current_region = region_name
            return cached.graph
        
        # Calculate clip_bbox for cache key (must match GraphBuilder's calculation)
        # 5km buffer to allow for scenic detours
        clip_bbox = None
        if bbox is not None:
            buffer_km = 5
            buffer_deg = buffer_km / 111.0  # ~0.045 degrees per km
            clip_bbox = (
                bbox[0] - buffer_deg,  # min_lat
                bbox[1] - buffer_deg,  # min_lon
                bbox[2] + buffer_deg,  # max_lat
                bbox[3] + buffer_deg   # max_lon
            )
        
        # Check disk cache
        cache_mgr = get_cache_manager()
        loader = OSMDataLoader()
        loader.ensure_data_for_bbox(bbox)  # Ensure PBF exists for mtime check
        
        if cache_mgr.is_cache_valid(region_name, greenness_mode, elevation_mode, loader.file_path, bbox=clip_bbox):
            print(f"[GraphManager] Disk cache HIT for region: {region_name}")
            graph = cache_mgr.load_graph(region_name, greenness_mode, elevation_mode, bbox=clip_bbox)
            if graph is not None:
                # Store in memory cache too
                cached = CachedGraph(graph, region_name, bbox, loader, {})
                cls._cache[region_name] = cached
                cls._current_region = region_name
                return cached.graph
        
        # Full cache miss - need to load and process
        print(f"[GraphManager] Cache MISS for region: {region_name} - full processing required")
        
        # Check memory capacity and evict if needed
        max_regions = get_max_cached_regions()
        if len(cls._cache) >= max_regions:
            cls._evict_lru()
        
        # Load, process, and cache
        cached = cls._load_graph_for_region(bbox, region_name)
        cls._cache[region_name] = cached
        cls._current_region = region_name
        
        return cached.graph
    
    @classmethod
    def get_loaded_file_path(cls) -> str:
        """Returns the path of the currently loaded PBF file."""
        if cls._current_region and cls._current_region in cls._cache:
            loader = cls._cache[cls._current_region].loader
            if loader and loader.file_path:
                return loader.file_path
        return "None (Graph not initialised)"
    
    @classmethod
    def get_timings(cls) -> Dict[str, float]:
        """Returns the timing breakdown from the current region's load."""
        if cls._current_region and cls._current_region in cls._cache:
            return cls._cache[cls._current_region].timings.copy()
        return {}
    
    @classmethod
    def get_cache_info(cls) -> Dict[str, Any]:
        """Returns information about the current cache state."""
        return {
            'cached_regions': list(cls._cache.keys()),
            'current_region': cls._current_region,
            'max_regions': get_max_cached_regions(),
            'cache_size': len(cls._cache)
        }
    
    @classmethod
    def clear_cache(cls):
        """Clear all cached graphs."""
        cls._cache.clear()
        cls._current_region = None
        print("[GraphManager] Cache cleared.")
    
    @classmethod
    def get_graph_for_route(cls, start: Tuple[float, float], 
                            end: Tuple[float, float]) -> nx.MultiDiGraph:
        """
        Get a graph covering a route using tile-based caching (ADR-007).
        
        This method uses snap-to-grid tiles instead of per-route bounding boxes.
        Only builds tiles that aren't already cached, then merges them.
        
        Args:
            start: Start point as (lat, lon).
            end: End point as (lat, lon).
        
        Returns:
            networkx.MultiDiGraph: Merged graph covering all required tiles.
        """
        from app.services.core.tile_utils import (
            get_tiles_for_route, get_tile_bbox
        )
        from app.services.core.graph_builder import build_graph
        
        # Get config values
        tile_size_km = get_config('TILE_SIZE_KM', 15)
        tile_overlap_km = get_config('TILE_OVERLAP_KM', 1)
        greenness_mode = get_greenness_mode()
        elevation_mode = get_elevation_mode()
        normalisation_mode = get_config('NORMALISATION_MODE', 'STATIC')
        
        # Determine required tiles
        tile_ids = get_tiles_for_route(start, end, tile_size_km)
        print(f"[GraphManager] Route requires {len(tile_ids)} tile(s): {tile_ids}")
        
        # Determine region for this route
        mid_lat = (start[0] + end[0]) / 2
        mid_lon = (start[1] + end[1]) / 2
        bbox = (min(start[0], end[0]), min(start[1], end[1]),
                max(start[0], end[0]), max(start[1], end[1]))
        region_name, _ = cls._find_region_for_bbox(bbox)
        
        # Ensure PBF data exists
        loader = OSMDataLoader()
        loader.ensure_data_for_bbox(bbox)
        
        cache_mgr = get_cache_manager()
        graphs = []
        build_times = []
        
        for tile_id in tile_ids:
            # Check disk cache for this tile
            # Note: Don't pass pbf_path - each tile may use a different PBF
            # The tile's pbf_mtime was recorded at build time
            if cache_mgr.is_cache_valid(region_name, greenness_mode, elevation_mode,
                                         pbf_path=None, tile_id=tile_id):
                print(f"[TileCache] HIT: {tile_id}")
                graph = cache_mgr.load_graph(region_name, greenness_mode, 
                                             elevation_mode, tile_id=tile_id)
                if graph is not None:
                    graphs.append(graph)
                    continue
            
            # Cache miss - need to build this tile
            print(f"[TileCache] MISS: {tile_id} - building...")
            t0 = time.time()
            
            tile_bbox = get_tile_bbox(tile_id, tile_size_km, tile_overlap_km)
            
            # Build graph for this tile
            result = build_graph(
                bbox=tile_bbox,
                region_name=region_name,
                greenness_mode=greenness_mode,
                elevation_mode=elevation_mode,
                normalisation_mode=normalisation_mode,
                save_to_cache=False  # We'll save with tile_id ourselves
            )
            
            # Save to cache with tile_id
            cache_mgr.save_graph(
                result.graph, region_name, greenness_mode, elevation_mode,
                pbf_path=loader.file_path, tile_id=tile_id
            )
            
            build_time = time.time() - t0
            build_times.append(build_time)
            print(f"[TileCache] Built {tile_id} in {build_time:.1f}s")
            
            graphs.append(result.graph)
        
        # Merge all tiles into single graph
        if len(graphs) == 0:
            raise ValueError("No graphs were loaded for the route")
        
        if len(graphs) == 1:
            merged_graph = graphs[0]
            print(f"[GraphManager] Single tile, no merge needed")
        else:
            print(f"[GraphManager] Merging {len(graphs)} tiles...")
            t0 = time.time()
            merged_graph = graphs[0]
            for g in graphs[1:]:
                merged_graph = nx.compose(merged_graph, g)
            merge_time = time.time() - t0
            print(f"[GraphManager] Merged in {merge_time:.2f}s - "
                  f"{merged_graph.number_of_nodes()} nodes, "
                  f"{merged_graph.number_of_edges()} edges")
        
        # Update class state for compatibility with existing code
        cls._current_region = region_name
        
        return merged_graph

