"""
WSM A* Implementation

Weighted Sum Model extension of A* for scenic routing.
Uses normalised feature costs combined with configurable weights
to find routes that balance distance with scenic preferences.
"""

from app.services.routing.astar.astar_lib import AStar
from app.services.routing.cost_calculator import (
    compute_wsm_cost,
    find_length_range,
    normalise_length,
    validate_weights,
)
from math import radians, cos, sin, asin, sqrt
from typing import Dict, Optional


class WSMNetworkXAStar(AStar):
    """
    A* implementation using Weighted Sum Model cost function.
    
    Extends the base AStar class to use a combined cost that weights
    distance against scenic features (greenness, water, quietness, etc.).
    
    Attributes:
        graph: NetworkX MultiDiGraph with normalised scenic attributes.
        weights: Feature weight dictionary for WSM calculation.
        min_length: Minimum edge length in graph (for normalisation).
        max_length: Maximum edge length in graph (for normalisation).
    """

    def __init__(
        self, 
        graph, 
        weights: Optional[Dict[str, float]] = None,
        length_range: Optional[tuple[float, float]] = None
    ):
        """
        Initialise WSM A* solver.
        
        Args:
            graph: NetworkX MultiDiGraph with norm_* edge attributes.
            weights: Feature weights dictionary. If None, uses equal weights.
            length_range: Pre-computed (min, max) length tuple. If None, computed from graph.
        """
        self.graph = graph
        
        # Validate and set weights
        if weights is None:
            weights = {
                'distance': 0.5,
                'greenness': 0.1,
                'water': 0.1,
                'quietness': 0.1,
                'social': 0.1,
                'slope': 0.1,
            }
        self.weights = validate_weights(weights)
        
        # Get or compute length range for normalisation
        if length_range is not None:
            self.min_length, self.max_length = length_range
        else:
            self.min_length, self.max_length = find_length_range(graph)

    def neighbors(self, node):
        """
        Returns the list of neighbours for a given node.
        
        Args:
            node: OSM node ID.
        
        Returns:
            List of neighbouring node IDs.
        """
        return list(self.graph.neighbors(node))

    def distance_between(self, n1, n2) -> float:
        """
        Compute the WSM cost between two adjacent nodes.
        
        Uses the Weighted Sum Model formula combining normalised distance
        with normalised scenic features according to configured weights.
        
        Args:
            n1: Source node ID.
            n2: Target node ID.
        
        Returns:
            WSM cost value (lower is better).
        """
        edges = self.graph[n1][n2]
        if not edges:
            return float('inf')
        
        # Get data from the first edge (shortest if multiple)
        # Find edge with minimum length
        best_cost = float('inf')
        
        for data in edges.values():
            length = data.get('length', float('inf'))
            if length == float('inf'):
                continue
            
            # Normalise length to 0-1 range
            norm_length = normalise_length(length, self.min_length, self.max_length)
            
            # Get normalised scenic attributes (default to 0.5 if missing)
            norm_green = data.get('norm_green', 0.5)
            norm_water = data.get('norm_water', 0.5)
            norm_social = data.get('norm_social', 0.5)
            norm_quiet = data.get('norm_quiet', 0.5)
            norm_slope = data.get('norm_slope', 0.5)
            
            # Compute WSM cost
            cost = compute_wsm_cost(
                norm_length=norm_length,
                norm_green=norm_green,
                norm_water=norm_water,
                norm_social=norm_social,
                norm_quiet=norm_quiet,
                norm_slope=norm_slope,
                weights=self.weights
            )
            
            # Debug logging for first few edges (to see greenness variance)
            if not hasattr(self, '_debug_count'):
                self._debug_count = 0
            if self._debug_count < 5:
                print(f"[WSM Debug] Edge {n1}->{n2}: norm_green={norm_green}, norm_quiet={norm_quiet}, cost={cost:.4f}")
                self._debug_count += 1
            
            if cost < best_cost:
                best_cost = cost
        
        return best_cost

    def heuristic_cost_estimate(self, current, goal) -> float:
        """
        Compute the estimated cost to the goal using dual-bound heuristic.
        
        The heuristic must be admissible (never overestimate) to guarantee
        optimal paths. We use:
        - Distance component: straight-line distance normalised by max edge length
        - Scenic components: assumed to be 0 (best case - optimistic bound)
        
        This is admissible because:
        1. Haversine distance ≤ actual path distance (straight line is shortest)
        2. Actual scenic costs ≥ 0 (we assume 0, reality can only be worse)
        
        Formula: h(n) = w_d × (haversine / max_edge_length) + 0
        
        Args:
            current: Current node ID.
            goal: Goal node ID.
        
        Returns:
            Estimated cost to reach goal from current node.
        """
        # Get coordinates from graph nodes
        current_data = self.graph.nodes[current]
        goal_data = self.graph.nodes[goal]
        
        current_lat = current_data.get('y', current_data.get('lat', 0))
        current_lon = current_data.get('x', current_data.get('lon', 0))
        goal_lat = goal_data.get('y', goal_data.get('lat', 0))
        goal_lon = goal_data.get('x', goal_data.get('lon', 0))
        
        # Calculate straight-line distance in metres
        straight_line_distance = self._haversine(current_lat, current_lon, goal_lat, goal_lon)
        
        # Normalise by max edge length (same scale as edge costs)
        # Note: can exceed 1.0 if distance > max_edge, which is valid
        if self.max_length > 0:
            normalised_distance = straight_line_distance / self.max_length
        else:
            normalised_distance = 0.0
        
        # Apply distance weight only; assume scenic costs = 0 (optimistic bound)
        # This guarantees admissibility: h(n) ≤ actual remaining cost
        h = self.weights.get('distance', 0.5) * normalised_distance
        
        return h

    def _haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate great circle distance between two points.
        
        Args:
            lat1, lon1: First point coordinates (decimal degrees).
            lat2, lon2: Second point coordinates (decimal degrees).
        
        Returns:
            Distance in metres.
        """
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        r = 6371000  # Earth radius in metres
        return c * r
