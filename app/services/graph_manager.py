import osmnx as ox
import networkx as nx
import os

class GraphManager:
    """
    Manages the loading and caching of the OpenStreetMap graph.
    """
    _graph = None
    _city = None

    @classmethod
    def get_graph(cls, city_name):
        """
        Returns the graph for the specified city.
        If the graph is already loaded for that city, returns the cached version.
        Otherwise, downloads it.

        Args:
            city_name (str): The name of the city to load (e.g., "Bristol, UK").

        Returns:
            networkx.MultiDiGraph: The street network graph.
        """
        if cls._graph is None or cls._city != city_name:
            print(f"Loading graph for {city_name}...")
            # Download the graph from OSM
            # network_type='walk' ensures we get walkable paths
            cls._graph = ox.graph_from_place(city_name, network_type='walk')
            cls._city = city_name
            print(f"Graph loaded for {city_name}.")
        
        return cls._graph
