import networkx as nx
import osmnx as ox
from flask import current_app
from app.services.routing.astar.astar import OSMNetworkXAStar

class RouteFinder:
    """
    Service to calculate the shortest path between two points using WSM A* implementation.
    """

    def __init__(self, graph):
        """
        Initialise with a graph.

        Args:
            graph (networkx.MultiDiGraph): The street network graph.
        """
        self.graph = graph

    def find_route(self, start_point, end_point):
        """
        Finds the shortest path between two locations (coordinates).

        Args:
            start_point (tuple): (lat, lon) start location.
            end_point (tuple): (lat, lon) end location.

        Returns:
            list: A list of node IDs representing the path.
            tuple: (start_coords, end_coords) where coords are (lat, lon).
            float: Total distance in meters.
            float: Estimated time in seconds.
        """
        try:
            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Finding route for coords: {start_point} -> {end_point}")

            # Find the nearest nodes in the graph to these points
            start_node = ox.distance.nearest_nodes(self.graph, start_point[1], start_point[0])
            end_node = ox.distance.nearest_nodes(self.graph, end_point[1], end_point[0])

            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Start Node ID: {start_node}")
                print(f"[VERBOSE] End Node ID: {end_node}")

            # Calculate the shortest path using custom A* implementation
            # weight='length' uses the distance in meters
            # route = nx.shortest_path(self.graph, start_node, end_node, weight='length')
            
            # Initialise custom A* adapter
            astar_solver = OSMNetworkXAStar(self.graph)
            
            # Find path
            # The library returns a generator or list, we need a list of node IDs
            route_generator = astar_solver.astar(start_node, end_node)
            
            if route_generator is None:
                print(f"No route found between {start_node} and {end_node}")
                return None, None, None
                
            route = list(route_generator)

            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Route found: {len(route)} nodes")
                print(f"[VERBOSE] First 5 nodes: {route[:5]}")

            # Calculate total distance
            distance = self._calculate_total_distance(route)

            # Calculate time
            time_seconds = self._calculate_estimated_time(distance)

            return route, start_point, end_point, distance, time_seconds
        except Exception as e:
            print(f"Error finding route: {e}")
            return None, None, None, 0, 0

    def _calculate_total_distance(self, route):
        """
        Calculates the total distance of the route in meters.
        """
        distance = 0.0
        for u, v in zip(route[:-1], route[1:]):
            try:
                edge_data = self.graph.get_edge_data(u, v)
                # edge_data is a dict keyed by key (0, 1, ...). We want the one with min length.
                lengths = [d.get('length', 0) for d in edge_data.values()]
                distance += min(lengths)
            except Exception:
                pass
        return distance

    def _calculate_estimated_time(self, distance):
        """
        Calculates the estimated walking time in seconds based on config speed.
        """
        speed_kmh = current_app.config.get('WALKING_SPEED_KMH', 5.0)
        speed_ms = speed_kmh * 1000 / 3600
        return distance / speed_ms if speed_ms > 0 else 0
