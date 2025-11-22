import networkx as nx
import osmnx as ox
from flask import current_app

class RouteFinder:
    """
    Service to calculate the shortest path between two points using just a simple A* algorithms (as MVP, so doesn't include constraints yet)
    """

    def __init__(self, graph):
        """
        Initialise with a graph.

        Args:
            graph (networkx.MultiDiGraph): The street network graph.
        """
        self.graph = graph

    def find_route(self, start_location, end_location):
        """
        Finds the shortest path between two locations.

        Args:
            start_location (str): The starting address/place.
            end_location (str): The ending address/place.

        Returns:
            list: A list of node IDs representing the path.
            tuple: (start_coords, end_coords) where coords are (lat, lon).
        """
        try:
            # Geocode the start and end locations to (lat, lon)
            start_point = ox.geocode(start_location)
            end_point = ox.geocode(end_location)

            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"\n[VERBOSE] Start Location: {start_location} -> {start_point}")
                print(f"[VERBOSE] End Location: {end_location} -> {end_point}")

            # Find the nearest nodes in the graph to these points
            start_node = ox.distance.nearest_nodes(self.graph, start_point[1], start_point[0])
            end_node = ox.distance.nearest_nodes(self.graph, end_point[1], end_point[0])

            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Start Node ID: {start_node}")
                print(f"[VERBOSE] End Node ID: {end_node}")

            # Calculate the shortest path using A*
            # weight='length' uses the distance in meters
            route = nx.shortest_path(self.graph, start_node, end_node, weight='length')

            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Route found: {len(route)} nodes")
                print(f"[VERBOSE] First 5 nodes: {route[:5]}")

            return route, start_point, end_point
        except Exception as e:
            print(f"Error finding route: {e}")
            return None, None, None
