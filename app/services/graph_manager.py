import os
import time
import networkx as nx
from app.services.data_loader import OSMDataLoader
from app.services.quietness_processor import process_graph_quietness
from app.services.visibility_processor import process_graph_greenness, process_graph_greenness_fast

try:
    from flask import current_app, has_app_context
except ImportError:
    current_app = None
    def has_app_context(): return False

def get_greenness_mode() -> str:
    """Get the configured greenness processing mode."""
    if has_app_context() and current_app:
        return current_app.config.get('GREENNESS_MODE', 'FAST').upper()
    # Default to FAST when running outside Flask context
    return 'FAST'

class GraphManager:
    """
    Manages the retrieval and caching of the street network graph.
    Now optimised to use local PBF data via OSMDataLoader.
    """
    _graph = None
    _loader = None
    _timings = {}  # Stores execution timings for profiling
    
    @classmethod
    def get_graph(cls, bbox=None):
        """
        Returns the street network graph.
        
        Args:
            bbox (tuple, optional): Ignored in this implementation as we load the full region PBF.
                                    Maintained for interface compatibility.

        Returns:
            networkx.MultiDiGraph: The graph with .features attached.
        """
        if cls._graph is None:
            total_start = time.perf_counter()
            cls._timings = {}
            
            print("[GraphManager] Initialising Graph from Local PBF...")
            # Initialise loader (defaults to Bristol PBF)
            cls._loader = OSMDataLoader()
            
            # Load the graph for the specific bbox region
            t0 = time.perf_counter()
            cls._graph = cls._loader.load_graph(bbox)
            cls._timings['Graph Loading'] = time.perf_counter() - t0
            print(f"  [Timer] Graph Loading: {cls._timings['Graph Loading']:.2f}s")
            
            # Process quietness attributes (noise_factor)
            t0 = time.perf_counter()
            print("[GraphManager] Processing quietness attributes...")
            cls._graph = process_graph_quietness(cls._graph)
            cls._timings['Quietness Processing'] = time.perf_counter() - t0
            print(f"  [Timer] Quietness Processing: {cls._timings['Quietness Processing']:.2f}s")
            
            # Process greenness based on configured mode
            greenness_mode = get_greenness_mode()
            print(f"[GraphManager] Greenness mode: {greenness_mode}")
            
            if greenness_mode == 'NOVACK':
                # Full isovist ray-casting (slow but accurate)
                print("[GraphManager] Processing greenness visibility (NOVACK mode)...")
                
                t0 = time.perf_counter()
                green_gdf = cls._loader.extract_green_areas()
                cls._timings['Extract Green Areas'] = time.perf_counter() - t0
                print(f"  [Timer] Extract Green Areas: {cls._timings['Extract Green Areas']:.2f}s")
                
                t0 = time.perf_counter()
                buildings_gdf = cls._loader.extract_buildings()
                cls._timings['Extract Buildings'] = time.perf_counter() - t0
                print(f"  [Timer] Extract Buildings: {cls._timings['Extract Buildings']:.2f}s")
                
                t0 = time.perf_counter()
                cls._graph = process_graph_greenness(cls._graph, green_gdf, buildings_gdf)
                cls._timings['Greenness Processing (NOVACK)'] = time.perf_counter() - t0
                print(f"  [Timer] Greenness Processing (NOVACK): {cls._timings['Greenness Processing (NOVACK)']:.2f}s")
                
            elif greenness_mode == 'FAST':
                # Simple buffer intersection (quick scenic scoring)
                print("[GraphManager] Processing scenic scores (FAST mode)...")
                
                t0 = time.perf_counter()
                green_gdf = cls._loader.extract_green_areas()
                cls._timings['Extract Green Areas'] = time.perf_counter() - t0
                print(f"  [Timer] Extract Green Areas: {cls._timings['Extract Green Areas']:.2f}s")
                
                t0 = time.perf_counter()
                water_gdf = cls._loader.extract_water()
                cls._timings['Extract Water'] = time.perf_counter() - t0
                print(f"  [Timer] Extract Water: {cls._timings['Extract Water']:.2f}s")
                
                t0 = time.perf_counter()
                cls._graph = process_graph_greenness_fast(cls._graph, green_gdf, water_gdf)
                cls._timings['Scenic Processing (FAST)'] = time.perf_counter() - t0
                print(f"  [Timer] Scenic Processing (FAST): {cls._timings['Scenic Processing (FAST)']:.2f}s")
                
            else:  # OFF
                print("[GraphManager] Greenness processing disabled.")
            
            # Shim for compatibility if needed.
            if not hasattr(cls._graph, 'features'):
                cls._graph.features = None
            
            # Print timing summary
            total_time = time.perf_counter() - total_start
            cls._timings['TOTAL'] = total_time
            print("\n" + "="*50)
            print("[GraphManager] TIMING SUMMARY")
            print("="*50)
            for step, duration in cls._timings.items():
                if step != 'TOTAL':
                    pct = (duration / total_time) * 100
                    print(f"  {step}: {duration:.2f}s ({pct:.1f}%)")
            print("-"*50)
            print(f"  TOTAL: {total_time:.2f}s")
            print("="*50 + "\n")

        return cls._graph

    @classmethod
    def get_loaded_file_path(cls):
        """
        Returns the path of the currently loaded PBF file.
        """
        if cls._loader and cls._loader.file_path:
            return cls._loader.file_path
        return "None (Graph not initialised)"

    @classmethod
    def get_timings(cls):
        """Returns the timing breakdown from the last graph load."""
        return cls._timings.copy()
