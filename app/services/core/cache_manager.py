"""
Cache Manager Module

Provides disk-based caching for processed graph objects.
Saves fully-processed graphs (with scenic scores) to disk for fast reload.
"""

import os
import pickle
import hashlib
import json
import time
from typing import Optional, Dict, Any
from pathlib import Path
import networkx as nx


# Cache version - increment when graph processing logic changes significantly
CACHE_VERSION = "1.0.0"


class CacheManager:
    """
    Manages disk caching of processed NetworkX graphs.
    
    Caches are validated against:
    - Cache version (code changes)
    - PBF file modification time
    - Greenness mode setting
    - Elevation mode setting
    """
    
    def __init__(self, cache_dir: str = "app/data/cache"):
        """
        Initialise the cache manager.
        
        Args:
            cache_dir: Directory for cache files (relative to project root).
        """
        # Navigate from app/services/core/ up to project root (4 levels)
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
        self.cache_dir = os.path.join(base_dir, cache_dir)
        self.manifest_path = os.path.join(self.cache_dir, "manifest.json")
        
        # Ensure cache directory exists
        os.makedirs(self.cache_dir, exist_ok=True)
        
        # Load or create manifest
        self._manifest = self._load_manifest()
    
    def _load_manifest(self) -> Dict[str, Any]:
        """Load the cache manifest from disk."""
        if os.path.exists(self.manifest_path):
            try:
                with open(self.manifest_path, 'r') as f:
                    return json.load(f)
            except (json.JSONDecodeError, IOError):
                return {"version": CACHE_VERSION, "entries": {}}
        return {"version": CACHE_VERSION, "entries": {}}
    
    def _save_manifest(self):
        """Save the cache manifest to disk."""
        try:
            with open(self.manifest_path, 'w') as f:
                json.dump(self._manifest, f, indent=2)
        except IOError as e:
            print(f"[CacheManager] Warning: Could not save manifest: {e}")
    
    def _get_cache_key(self, region_name: str, greenness_mode: str, 
                        elevation_mode: str = 'OFF') -> str:
        """Generate a unique cache key for a region + mode combination."""
        return f"{region_name}_{greenness_mode.lower()}_{elevation_mode.lower()}"
    
    def _get_cache_path(self, cache_key: str) -> str:
        """Get the file path for a cache entry."""
        return os.path.join(self.cache_dir, f"{cache_key}_v{CACHE_VERSION}.pickle")
    
    def is_cache_valid(self, region_name: str, greenness_mode: str,
                       elevation_mode: str = 'OFF',
                       pbf_path: Optional[str] = None) -> bool:
        """
        Check if a valid cache exists for the given region and mode.
        
        Args:
            region_name: Name of the region (e.g., 'cornwall').
            greenness_mode: Processing mode ('OFF', 'FAST', 'NOVACK').
            elevation_mode: Elevation mode ('OFF', 'FAST').
            pbf_path: Path to the PBF file (for mtime validation).
        
        Returns:
            True if valid cache exists, False otherwise.
        """
        cache_key = self._get_cache_key(region_name, greenness_mode, elevation_mode)
        cache_path = self._get_cache_path(cache_key)
        
        # Check file exists
        if not os.path.exists(cache_path):
            return False
        
        # Check manifest entry
        if cache_key not in self._manifest.get("entries", {}):
            return False
        
        entry = self._manifest["entries"][cache_key]
        
        # Check version
        if entry.get("version") != CACHE_VERSION:
            print(f"[CacheManager] Cache version mismatch for {cache_key}")
            return False
        
        # Check PBF modification time if provided
        if pbf_path and os.path.exists(pbf_path):
            pbf_mtime = os.path.getmtime(pbf_path)
            if entry.get("pbf_mtime") != pbf_mtime:
                print(f"[CacheManager] PBF modified since cache creation for {cache_key}")
                return False
        
        # Check greenness mode
        if entry.get("greenness_mode") != greenness_mode:
            return False
        
        return True
    
    def load_graph(self, region_name: str, greenness_mode: str,
                   elevation_mode: str = 'OFF') -> Optional[nx.MultiDiGraph]:
        """
        Load a cached graph from disk.
        
        Args:
            region_name: Name of the region.
            greenness_mode: Processing mode.
            elevation_mode: Elevation mode.
        
        Returns:
            The cached graph, or None if not found/invalid.
        """
        cache_key = self._get_cache_key(region_name, greenness_mode, elevation_mode)
        cache_path = self._get_cache_path(cache_key)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            print(f"[CacheManager] Loading cached graph from {cache_path}...")
            t0 = time.perf_counter()
            
            with open(cache_path, 'rb') as f:
                graph = pickle.load(f)
            
            load_time = time.perf_counter() - t0
            print(f"[CacheManager] Cache loaded in {load_time:.2f}s")
            
            return graph
            
        except (pickle.PickleError, IOError, EOFError) as e:
            print(f"[CacheManager] Error loading cache: {e}")
            # Remove corrupt cache
            self._remove_cache(cache_key)
            return None
    
    def save_graph(self, graph: nx.MultiDiGraph, region_name: str, 
                   greenness_mode: str, elevation_mode: str = 'OFF',
                   pbf_path: Optional[str] = None):
        """
        Save a processed graph to disk cache.
        
        Args:
            graph: The fully-processed NetworkX graph.
            region_name: Name of the region.
            greenness_mode: Processing mode used.
            elevation_mode: Elevation mode used.
            pbf_path: Path to source PBF (for invalidation tracking).
        """
        cache_key = self._get_cache_key(region_name, greenness_mode, elevation_mode)
        cache_path = self._get_cache_path(cache_key)
        
        try:
            print(f"[CacheManager] Saving graph to cache: {cache_path}...")
            t0 = time.perf_counter()
            
            with open(cache_path, 'wb') as f:
                pickle.dump(graph, f, protocol=pickle.HIGHEST_PROTOCOL)
            
            save_time = time.perf_counter() - t0
            cache_size_mb = os.path.getsize(cache_path) / (1024 * 1024)
            print(f"[CacheManager] Cache saved in {save_time:.2f}s ({cache_size_mb:.1f} MB)")
            
            # Update manifest
            self._manifest["entries"][cache_key] = {
                "version": CACHE_VERSION,
                "greenness_mode": greenness_mode,
                "pbf_mtime": os.path.getmtime(pbf_path) if pbf_path and os.path.exists(pbf_path) else None,
                "created": time.time(),
                "size_mb": cache_size_mb
            }
            self._save_manifest()
            
        except (pickle.PickleError, IOError) as e:
            print(f"[CacheManager] Error saving cache: {e}")
    
    def _remove_cache(self, cache_key: str):
        """Remove a cache entry."""
        cache_path = self._get_cache_path(cache_key)
        
        if os.path.exists(cache_path):
            os.remove(cache_path)
        
        if cache_key in self._manifest.get("entries", {}):
            del self._manifest["entries"][cache_key]
            self._save_manifest()
    
    def clear_all(self):
        """Clear all cached graphs."""
        print("[CacheManager] Clearing all cached graphs...")
        
        for cache_key in list(self._manifest.get("entries", {}).keys()):
            self._remove_cache(cache_key)
        
        self._manifest = {"version": CACHE_VERSION, "entries": {}}
        self._save_manifest()
        
        print("[CacheManager] Cache cleared.")
    
    def get_cache_stats(self) -> Dict[str, Any]:
        """Get statistics about the current cache state."""
        entries = self._manifest.get("entries", {})
        total_size = sum(e.get("size_mb", 0) for e in entries.values())
        
        return {
            "cached_regions": list(entries.keys()),
            "total_entries": len(entries),
            "total_size_mb": total_size,
            "cache_version": CACHE_VERSION,
            "cache_dir": self.cache_dir
        }


# Singleton instance
_cache_manager: Optional[CacheManager] = None


def get_cache_manager() -> CacheManager:
    """Get the singleton cache manager instance."""
    global _cache_manager
    if _cache_manager is None:
        _cache_manager = CacheManager()
    return _cache_manager
