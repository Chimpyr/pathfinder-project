import os
import networkx as nx
from app.services.data_loader import OSMDataLoader
from app.services.quietness_processor import process_graph_quietness

class GraphManager:
    """
    Manages the retrieval and caching of the street network graph.
    Now optimised to use local PBF data via OSMDataLoader.
    """
    _graph = None
    _loader = None
    
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
            print("[GraphManager] Initialising Graph from Local PBF...")
            # Initialise loader (defaults to Bristol PBF)
            cls._loader = OSMDataLoader()
            
            # Load the graph for the specific bbox region
            # This triggers Geofabrik Index lookup and download if needed
            cls._graph = cls._loader.load_graph(bbox)
            
            # Process quietness attributes (noise_factor, raw_quiet_cost)
            print("[GraphManager] Processing quietness attributes...")
            cls._graph = process_graph_quietness(cls._graph)
            
            # Shim for compatibility if needed.
            if not hasattr(cls._graph, 'features'):
                cls._graph.features = None # or empty DataFrame if code breaks

        return cls._graph

    @classmethod
    def get_loaded_file_path(cls):
        """
        Returns the path of the currently loaded PBF file.
        """
        if cls._loader and cls._loader.file_path:
            return cls._loader.file_path
        return "None (Graph not initialised)"
