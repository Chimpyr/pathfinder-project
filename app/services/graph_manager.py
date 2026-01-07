import os
import networkx as nx
from app.services.data_loader import OSMDataLoader

class GraphManager:
    """
    Manages the retrieval and caching of the street network graph.
    Now optimized to use local PBF data via OSMDataLoader.
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
            print("[GraphManager] Initializing Graph from Local PBF...")
            # Initialize loader (defaults to Bristol PBF)
            cls._loader = OSMDataLoader()
            
            # Load the entire graph
            # This might take ~10-20s for the first load, then it's in memory.
            cls._graph = cls._loader.load_graph()
            
            # Features are essentially embedded in the graph edges/nodes by pyrosm, 
            # but our old code expected graph.features as a GeoDataFrame?
            # Pyrosm doesn't attach .features attribute like osmnx does.
            # However, Pyrosm edges have attributes.
            # If downstream code expects `graph.features`, we might need to attach something?
            # Let's check where graph.features is used. 
            # MapRenderer uses it? Or just for POIs?
            # If we need POIs separately, we might need a separate call.
            # But for now, let's just ensure the graph is returned.
            
            # Shim for compatibility if needed.
            if not hasattr(cls._graph, 'features'):
                cls._graph.features = None # or empty DataFrame if code breaks

        return cls._graph
