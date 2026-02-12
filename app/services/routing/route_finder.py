import networkx as nx
import osmnx as ox
from flask import current_app
from app.services.routing.astar.astar import OSMNetworkXAStar


class RouteFinder:
    """
    Service to calculate paths between two points.
    
    Supports both standard A* (shortest path by distance) and WSM A*
    (weighted scenic routing) depending on the use_wsm parameter.
    """

    def __init__(self, graph):
        """
        Initialise with a graph.

        Args:
            graph (networkx.MultiDiGraph): The street network graph.
        """
        self.graph = graph

    def find_route(self, start_point, end_point, use_wsm=False, weights=None, combine_nature=False):
        """
        Finds a path between two locations (coordinates).
        
        Supports two routing modes:
        - Standard A*: Uses physical distance only (use_wsm=False)
        - WSM A*: Uses Weighted Sum Model combining distance with scenic features
        
        Args:
            start_point (tuple): (lat, lon) start location.
            end_point (tuple): (lat, lon) end location.
            use_wsm (bool): If True, use WSM cost function for scenic routing.
            weights (dict): Feature weights for WSM mode. Uses defaults if None.
            combine_nature (bool): If True, combine greenness and water into single "nature" score.

        Returns:
            tuple: (route, start_point, end_point, distance, time_seconds)
                   - route: List of node IDs representing the path.
                   - distance: Total distance in metres.
                   - time_seconds: Estimated walking time.
        """
        try:
            if current_app.config.get('VERBOSE_LOGGING'):
                mode = 'WSM' if use_wsm else 'Standard'
                print(f"[VERBOSE] Finding route ({mode}): {start_point} -> {end_point}")

            # Find the nearest nodes in the graph to these points
            start_node = ox.distance.nearest_nodes(self.graph, start_point[1], start_point[0])
            end_node = ox.distance.nearest_nodes(self.graph, end_point[1], end_point[0])

            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Start Node ID: {start_node}")
                print(f"[VERBOSE] End Node ID: {end_node}")

            # Select A* solver based on mode
            if use_wsm:
                from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
                
                # Use provided weights or fall back to config defaults
                if weights is None:
                    weights = current_app.config.get('WSM_DEFAULT_WEIGHTS')
                
                astar_solver = WSMNetworkXAStar(self.graph, weights, combine_nature=combine_nature)
                
                if current_app.config.get('VERBOSE_LOGGING'):
                    print(f"[VERBOSE] WSM weights: {weights}, combine_nature: {combine_nature}")
            else:
                # Standard A* using distance only
                astar_solver = OSMNetworkXAStar(self.graph)
            
            # Find path
            route_generator = astar_solver.astar(start_node, end_node)
            
            if route_generator is None:
                print(f"No route found between {start_node} and {end_node}")
                return None, None, None, 0, 0
                
            route = list(route_generator)

            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Route found: {len(route)} nodes")
                print(f"[VERBOSE] First 5 nodes: {route[:5]}")

            # Calculate total distance
            distance = self._calculate_total_distance(route)

            # Calculate time
            time_seconds = self._calculate_estimated_time(distance)
            
            # Log total WSM cost if in verbose mode
            if use_wsm and current_app.config.get('VERBOSE_LOGGING'):
                total_wsm_cost = self._calculate_total_wsm_cost(route, weights)
                print(f"[VERBOSE] Total WSM cost: {total_wsm_cost:.2f}")
                print(f"[VERBOSE] Total distance: {distance:.0f}m in {len(route)} edges")

            return route, start_point, end_point, distance, time_seconds
        except Exception as e:
            print(f"Error finding route: {e}")
            import traceback
            traceback.print_exc()
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
    
    def _calculate_total_wsm_cost(self, route, weights):
        """
        Calculate total WSM cost for a route to verify A* optimality.
        
        Args:
            route: List of node IDs.
            weights: WSM weight dictionary.
        
        Returns:
            Total WSM cost of the route.
        """
        from app.services.routing.cost_calculator import compute_wsm_cost, normalise_length, find_length_range
        
        min_len, max_len = find_length_range(self.graph)
        
        total_cost = 0.0
        water_sum = 0.0
        length_sum = 0.0
        
        for u, v in zip(route[:-1], route[1:]):
            edge_data = self.graph.get_edge_data(u, v)
            if edge_data:
                # Use first edge data
                data = list(edge_data.values())[0]
                
                length = data.get('length', 0)
                norm_length = normalise_length(length, min_len, max_len)
                
                norm_water = data.get('norm_water', 0.5)
                norm_green = data.get('norm_green', 0.5)
                norm_social = data.get('norm_social', 0.5)
                norm_quiet = data.get('norm_quiet', 0.5)
                norm_slope = data.get('norm_slope', 0.5)
                
                cost = compute_wsm_cost(
                    norm_length, norm_green, norm_water,
                    norm_social, norm_quiet, norm_slope, weights
                )
                total_cost += cost
                water_sum += norm_water
                length_sum += length
        
        avg_water = water_sum / max(1, len(route) - 1)
        print(f"[VERBOSE] Avg norm_water on route: {avg_water:.3f}")
        print(f"[VERBOSE] Total length: {length_sum:.0f}m")
        
        return total_cost
