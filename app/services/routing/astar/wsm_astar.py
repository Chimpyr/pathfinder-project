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
            
            if cost < best_cost:
                best_cost = cost
        
        return best_cost

    def heuristic_cost_estimate(self, current, goal) -> float:
        """
        Compute the estimated cost to the goal using Haversine distance.
        
        The heuristic must be admissible (never overestimate) to guarantee
        optimal paths. We use the minimum possible edge cost as a conservative
        lower bound, which is zero (a maximally scenic edge with zero length
        contribution has zero cost).
        
        Note: For WSM with scenic features, we cannot accurately estimate
        the scenic quality of remaining path, so we use a conservative heuristic.
        
        Args:
            current: Current node ID.
            goal: Goal node ID.
        
        Returns:
            Estimated cost to reach goal from current node.
        """
        # Use zero heuristic to guarantee admissibility
        # This degrades to Dijkstra's algorithm but ensures optimality
        # A more sophisticated heuristic could be developed later
        return 0.0

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
