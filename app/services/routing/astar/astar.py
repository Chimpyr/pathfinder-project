from app.services.routing.astar.astar_lib import AStar
import networkx as nx
from math import radians, cos, sin, asin, sqrt

class OSMNetworkXAStar(AStar):
    """
    A* implementation for OpenStreetMap graphs using NetworkX.
    Inherits from the custom AStar library.
    """

    def __init__(self, graph):
        self.graph = graph

    def neighbors(self, node):
        """
        Returns the list of neighbors for a given node.
        """
        return list(self.graph.neighbors(node))

    def distance_between(self, n1, n2):
        """
        Gives the real distance between two adjacent nodes n1 and n2.
        Uses the 'length' attribute of the edge.
        """
        # NetworkX MultiDiGraph edges are accessed using [u][v][key]
        # We take the minimum length if there are multiple edges
        edges = self.graph[n1][n2]
        if not edges:
            return float('inf')
        
        # Return the shortest edge length between the two nodes
        return min(data.get('length', float('inf')) for data in edges.values())

    def heuristic_cost_estimate(self, current, goal):
        """
        Computes the estimated (rough) distance between a node and the goal.
        Uses the Haversine formula (great-circle distance) as the heuristic.
        """
        # Get coordinates
        # OSMnx graphs store node attributes including 'y' (lat) and 'x' (lon)
        try:
            n1_data = self.graph.nodes[current]
            n2_data = self.graph.nodes[goal]
            
            lat1, lon1 = n1_data['y'], n1_data['x']
            lat2, lon2 = n2_data['y'], n2_data['x']
            
            return self._haversine(lat1, lon1, lat2, lon2)
        except KeyError:
            # Fallback if node data is missing (shouldn't happen in valid graph)
            return float('inf')

    def _haversine(self, lat1, lon1, lat2, lon2):
        """
        Calculate the great circle distance between two points 
        on the earth (specified in decimal degrees)
        """
        # convert decimal degrees to radians 
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])

        # haversine formula 
        dlon = lon2 - lon1 
        dlat = lat2 - lat1 
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * asin(sqrt(a)) 
        r = 6371000 # Radius of earth in meters
        return c * r
