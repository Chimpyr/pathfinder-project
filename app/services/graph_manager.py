"""
Graph Manager Module

Manages the retrieval and caching of street network graphs with LRU eviction.
Supports multi-region routing by caching multiple graphs keyed by region name.
"""

import os
import time
import networkx as nx
from typing import Dict, Optional, Tuple, Any
from app.services.data_loader import OSMDataLoader
from app.services.quietness_processor import process_graph_quietness
from app.services.visibility_processor import process_graph_greenness, process_graph_greenness_fast
from app.services.elevation_processor import process_graph_elevation
from app.services.cache_manager import get_cache_manager

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
        """Load and process a graph for a specific region."""
        total_start = time.perf_counter()
        timings = {}
        
        print(f"[GraphManager] Loading graph for region: {region_name}")
        
        # Initialise loader
        loader = OSMDataLoader()
        
        # Load the graph
        t0 = time.perf_counter()
        graph = loader.load_graph(bbox)
        timings['Graph Loading'] = time.perf_counter() - t0
        print(f"  [Timer] Graph Loading: {timings['Graph Loading']:.2f}s")
        
        # Process quietness
        t0 = time.perf_counter()
        print("[GraphManager] Processing quietness attributes...")
        graph = process_graph_quietness(graph)
        timings['Quietness Processing'] = time.perf_counter() - t0
        print(f"  [Timer] Quietness Processing: {timings['Quietness Processing']:.2f}s")
        
        # Process greenness based on mode
        greenness_mode = get_greenness_mode()
        print(f"[GraphManager] Greenness mode: {greenness_mode}")
        
        if greenness_mode == 'NOVACK':
            print("[GraphManager] Processing greenness visibility (NOVACK mode)...")
            
            t0 = time.perf_counter()
            green_gdf = loader.extract_green_areas()
            timings['Extract Green Areas'] = time.perf_counter() - t0
            print(f"  [Timer] Extract Green Areas: {timings['Extract Green Areas']:.2f}s")
            
            t0 = time.perf_counter()
            buildings_gdf = loader.extract_buildings()
            timings['Extract Buildings'] = time.perf_counter() - t0
            print(f"  [Timer] Extract Buildings: {timings['Extract Buildings']:.2f}s")
            
            t0 = time.perf_counter()
            graph = process_graph_greenness(graph, green_gdf, buildings_gdf)
            timings['Greenness Processing (NOVACK)'] = time.perf_counter() - t0
            print(f"  [Timer] Greenness Processing: {timings['Greenness Processing (NOVACK)']:.2f}s")
            
        elif greenness_mode == 'FAST':
            print("[GraphManager] Processing scenic scores (FAST mode)...")
            
            t0 = time.perf_counter()
            green_gdf = loader.extract_green_areas()
            timings['Extract Green Areas'] = time.perf_counter() - t0
            print(f"  [Timer] Extract Green Areas: {timings['Extract Green Areas']:.2f}s")
            
            t0 = time.perf_counter()
            water_gdf = loader.extract_water()
            timings['Extract Water'] = time.perf_counter() - t0
            print(f"  [Timer] Extract Water: {timings['Extract Water']:.2f}s")
            
            t0 = time.perf_counter()
            graph = process_graph_greenness_fast(graph, green_gdf, water_gdf)
            timings['Scenic Processing (FAST)'] = time.perf_counter() - t0
            print(f"  [Timer] Scenic Processing: {timings['Scenic Processing (FAST)']:.2f}s")
            
        else:
            print("[GraphManager] Greenness processing disabled.")
        
        # Process elevation based on mode
        elevation_mode = get_elevation_mode()
        print(f"[GraphManager] Elevation mode: {elevation_mode}")
        
        if elevation_mode == 'FAST':
            print("[GraphManager] Processing elevation gradients (FAST mode)...")
            
            t0 = time.perf_counter()
            graph = process_graph_elevation(graph)
            timings['Elevation Processing (FAST)'] = time.perf_counter() - t0
            print(f"  [Timer] Elevation Processing: {timings['Elevation Processing (FAST)']:.2f}s")
            
        else:
            print("[GraphManager] Elevation processing disabled.")
        
        # Compatibility shim
        if not hasattr(graph, 'features'):
            graph.features = None
        
        # Print timing summary
        total_time = time.perf_counter() - total_start
        timings['TOTAL'] = total_time
        
        print("\n" + "="*50)
        print(f"[GraphManager] TIMING SUMMARY ({region_name})")
        print("="*50)
        for step, duration in timings.items():
            if step != 'TOTAL':
                pct = (duration / total_time) * 100
                print(f"  {step}: {duration:.2f}s ({pct:.1f}%)")
        print("-"*50)
        print(f"  TOTAL: {total_time:.2f}s")
        print("="*50 + "\n")
        
        # Save to disk cache for next time
        cache_mgr = get_cache_manager()
        cache_mgr.save_graph(graph, region_name, greenness_mode, elevation_mode, loader.file_path)
        
        return CachedGraph(graph, region_name, bbox, loader, timings)
    
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
        
        # Check disk cache
        cache_mgr = get_cache_manager()
        loader = OSMDataLoader()
        loader.ensure_data_for_bbox(bbox)  # Ensure PBF exists for mtime check
        
        if cache_mgr.is_cache_valid(region_name, greenness_mode, elevation_mode, loader.file_path):
            print(f"[GraphManager] Disk cache HIT for region: {region_name}")
            graph = cache_mgr.load_graph(region_name, greenness_mode, elevation_mode)
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
