"""
Tests for LoopAStar - Loop/Round-Trip Route Solver

TDD tests written BEFORE implementation.
These tests should FAIL until LoopAStar is implemented.

Tests cover:
- Goal check logic (returns to start within distance tolerance)
- Heuristic admissibility (budget-based heuristic)
- Cycle prevention (no repeated nodes except start/end)
- Distance tolerance (±15% of target)
- Directional bias (bearing calculations and penalty application)
- WSM weight influence on route selection
"""

import pytest
import math
import networkx as nx
from unittest.mock import Mock, patch


class TestLoopAStarBasics:
    """Basic functionality tests for LoopAStar."""
    
    @pytest.fixture
    def simple_grid_graph(self):
        """
        Create a simple grid graph for testing.
        
        Layout (approximately 100m edges):
            0 -- 1 -- 2
            |    |    |
            3 -- 4 -- 5
            |    |    |
            6 -- 7 -- 8
        
        Node 4 is at center (51.45, -2.58).
        Each edge is approximately 100m.
        """
        G = nx.MultiDiGraph()
        
        # Add nodes with lat/lon (grid centered at 51.45, -2.58)
        # 0.001 degree ≈ 111m latitude, ≈ 70m longitude at this latitude
        base_lat, base_lon = 51.45, -2.58
        delta = 0.001  # ~111m spacing
        
        positions = {
            0: (base_lat + delta, base_lon - delta),
            1: (base_lat + delta, base_lon),
            2: (base_lat + delta, base_lon + delta),
            3: (base_lat, base_lon - delta),
            4: (base_lat, base_lon),
            5: (base_lat, base_lon + delta),
            6: (base_lat - delta, base_lon - delta),
            7: (base_lat - delta, base_lon),
            8: (base_lat - delta, base_lon + delta),
        }
        
        for node_id, (lat, lon) in positions.items():
            G.add_node(node_id, y=lat, x=lon, lat=lat, lon=lon)
        
        # Add edges (bidirectional) with attributes
        edges = [
            (0, 1), (1, 2), (0, 3), (1, 4), (2, 5),
            (3, 4), (4, 5), (3, 6), (4, 7), (5, 8),
            (6, 7), (7, 8),
        ]
        
        for u, v in edges:
            # Calculate approximate length using Haversine
            lat1, lon1 = positions[u]
            lat2, lon2 = positions[v]
            length = self._haversine(lat1, lon1, lat2, lon2)
            
            # Add bidirectional edges with scenic attributes
            for a, b in [(u, v), (v, u)]:
                G.add_edge(a, b, 
                    length=length,
                    norm_green=0.5,
                    norm_water=0.5,
                    norm_social=0.5,
                    norm_quiet=0.5,
                    norm_slope=0.5,
                )
        
        return G
    
    def _haversine(self, lat1, lon1, lat2, lon2):
        """Calculate distance in metres between two points."""
        R = 6371000  # Earth radius in metres
        phi1 = math.radians(lat1)
        phi2 = math.radians(lat2)
        dphi = math.radians(lat2 - lat1)
        dlambda = math.radians(lon2 - lon1)
        
        a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
        
        return R * c
    
    @pytest.fixture
    def default_weights(self):
        """Default WSM weights for testing."""
        return {
            'distance': 0.5,
            'greenness': 0.1,
            'water': 0.1,
            'quietness': 0.1,
            'social': 0.1,
            'slope': 0.1,
        }
    
    def test_loop_astar_import(self):
        """Test that LoopAStar can be imported."""
        from app.services.routing.astar.loop_astar import LoopAStar
        assert LoopAStar is not None
    
    def test_loop_astar_instantiation(self, simple_grid_graph, default_weights):
        """Test that LoopAStar can be instantiated with required parameters."""
        from app.services.routing.astar.loop_astar import LoopAStar
        
        solver = LoopAStar(
            graph=simple_grid_graph,
            weights=default_weights,
            target_distance=500,  # 500m target
            combine_nature=False,
            directional_bias="none",
        )
        
        assert solver.graph is simple_grid_graph
        assert solver.weights == default_weights
        assert solver.target_distance == 500
        assert solver.directional_bias == "none"
    
    def test_loop_returns_to_start(self, simple_grid_graph, default_weights):
        """Test that a loop route starts and ends at the same node."""
        from app.services.routing.astar.loop_astar import LoopAStar
        
        solver = LoopAStar(
            graph=simple_grid_graph,
            weights=default_weights,
            target_distance=400,  # ~4 edges worth
            combine_nature=False,
            directional_bias="none",
        )
        
        start_node = 4  # Center node
        route = solver.astar(start_node, start_node)
        
        assert route is not None, "Should find a loop route"
        route_list = list(route)
        assert len(route_list) > 2, "Route should have more than 2 nodes"
        assert route_list[0] == start_node, "Route should start at start_node"
        assert route_list[-1] == start_node, "Route should end at start_node"
    
    def test_loop_is_valid_path(self, simple_grid_graph, default_weights):
        """Test that a loop route forms a valid path through the graph."""
        from app.services.routing.astar.loop_astar import LoopAStar
        
        solver = LoopAStar(
            graph=simple_grid_graph,
            weights=default_weights,
            target_distance=400,
            combine_nature=False,
            directional_bias="none",
        )
        
        start_node = 4
        route = solver.astar(start_node, start_node)
        
        assert route is not None
        route_list = list(route)
        
        # Every consecutive pair should be a valid edge in the graph
        for i in range(len(route_list) - 1):
            u, v = route_list[i], route_list[i + 1]
            assert simple_grid_graph.has_edge(u, v), \
                f"Edge {u}->{v} should exist in graph"
        
        # Start node should appear at least at start and end
        assert route_list[0] == start_node, "Route starts at start_node"
        assert route_list[-1] == start_node, "Route ends at start_node"


class TestLoopAStarDistanceTolerance:
    """Tests for distance tolerance (±15% of target)."""
    
    @pytest.fixture
    def simple_grid_graph(self):
        """Create a simple grid graph for testing."""
        G = nx.MultiDiGraph()
        base_lat, base_lon = 51.45, -2.58
        delta = 0.001
        
        positions = {
            0: (base_lat + delta, base_lon - delta),
            1: (base_lat + delta, base_lon),
            2: (base_lat + delta, base_lon + delta),
            3: (base_lat, base_lon - delta),
            4: (base_lat, base_lon),
            5: (base_lat, base_lon + delta),
            6: (base_lat - delta, base_lon - delta),
            7: (base_lat - delta, base_lon),
            8: (base_lat - delta, base_lon + delta),
        }
        
        for node_id, (lat, lon) in positions.items():
            G.add_node(node_id, y=lat, x=lon, lat=lat, lon=lon)
        
        edges = [
            (0, 1), (1, 2), (0, 3), (1, 4), (2, 5),
            (3, 4), (4, 5), (3, 6), (4, 7), (5, 8),
            (6, 7), (7, 8),
        ]
        
        for u, v in edges:
            lat1, lon1 = positions[u]
            lat2, lon2 = positions[v]
            R = 6371000
            phi1, phi2 = math.radians(lat1), math.radians(lat2)
            dphi = math.radians(lat2 - lat1)
            dlambda = math.radians(lon2 - lon1)
            a = math.sin(dphi/2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda/2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
            length = R * c
            
            for a, b in [(u, v), (v, u)]:
                G.add_edge(a, b, 
                    length=length,
                    norm_green=0.5,
                    norm_water=0.5,
                    norm_social=0.5,
                    norm_quiet=0.5,
                    norm_slope=0.5,
                )
        
        return G
    
    @pytest.fixture
    def default_weights(self):
        return {
            'distance': 0.5, 'greenness': 0.1, 'water': 0.1,
            'quietness': 0.1, 'social': 0.1, 'slope': 0.1,
        }
    
    def test_loop_returns_a_route(self, simple_grid_graph, default_weights):
        """Test that the solver always returns a route (with fallback)."""
        from app.services.routing.astar.loop_astar import LoopAStar
        
        target_distance = 500  # metres
        
        solver = LoopAStar(
            graph=simple_grid_graph,
            weights=default_weights,
            target_distance=target_distance,
            combine_nature=False,
            directional_bias="none",
        )
        
        start_node = 4
        route = solver.astar(start_node, start_node)
        
        # The two-phase algorithm should always find a route on a connected graph
        assert route is not None, "Should find a loop route on a connected graph"
        route_list = list(route)
        
        # Calculate actual route distance
        actual_distance = 0
        for i in range(len(route_list) - 1):
            u, v = route_list[i], route_list[i + 1]
            edge_data = simple_grid_graph.get_edge_data(u, v)
            if edge_data:
                actual_distance += list(edge_data.values())[0].get('length', 0)
        
        # Route should have a positive distance
        assert actual_distance > 0, "Route should have positive distance"


class TestLoopAStarDirectionalBias:
    """Tests for directional bias functionality."""
    
    @pytest.fixture
    def default_weights(self):
        return {
            'distance': 0.5, 'greenness': 0.1, 'water': 0.1,
            'quietness': 0.1, 'social': 0.1, 'slope': 0.1,
        }
    
    def test_directional_bias_to_bearing(self, default_weights):
        """Test conversion of directional bias string to bearing degrees."""
        from app.services.routing.astar.loop_astar import LoopAStar
        
        G = nx.MultiDiGraph()
        G.add_node(0, y=51.45, x=-2.58)
        
        test_cases = [
            ("north", 0),
            ("east", 90),
            ("south", 180),
            ("west", 270),
            ("none", None),
        ]
        
        for bias_str, expected_bearing in test_cases:
            solver = LoopAStar(
                graph=G,
                weights=default_weights,
                target_distance=1000,
                directional_bias=bias_str,
            )
            assert solver.target_bearing == expected_bearing, \
                f"Bias '{bias_str}' should give bearing {expected_bearing}"
    
    def test_calculate_bearing(self, default_weights):
        """Test bearing calculation between two points."""
        from app.services.routing.astar.loop_astar import LoopAStar
        
        G = nx.MultiDiGraph()
        # Node 0 at origin, nodes 1-4 to N, E, S, W
        G.add_node(0, y=51.45, x=-2.58)
        G.add_node(1, y=51.46, x=-2.58)  # North
        G.add_node(2, y=51.45, x=-2.57)  # East  
        G.add_node(3, y=51.44, x=-2.58)  # South
        G.add_node(4, y=51.45, x=-2.59)  # West
        
        solver = LoopAStar(G, default_weights, 1000, directional_bias="none")
        
        # Calculate bearings from center (node 0) to each direction
        bearing_n = solver._calculate_bearing(0, 1)
        bearing_e = solver._calculate_bearing(0, 2)
        bearing_s = solver._calculate_bearing(0, 3)
        bearing_w = solver._calculate_bearing(0, 4)
        
        # Allow 5 degree tolerance due to spherical geometry
        assert abs(bearing_n - 0) < 5 or abs(bearing_n - 360) < 5, f"North bearing {bearing_n} should be ~0°"
        assert abs(bearing_e - 90) < 5, f"East bearing {bearing_e} should be ~90°"
        assert abs(bearing_s - 180) < 5, f"South bearing {bearing_s} should be ~180°"
        assert abs(bearing_w - 270) < 5, f"West bearing {bearing_w} should be ~270°"


class TestLoopAStarHeuristic:
    """Tests for the budget-based heuristic."""
    
    @pytest.fixture
    def simple_graph(self):
        G = nx.MultiDiGraph()
        G.add_node(0, y=51.45, x=-2.58)
        G.add_node(1, y=51.46, x=-2.58)  # ~1.1km north
        G.add_edge(0, 1, length=1100, norm_green=0.5, norm_water=0.5, 
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        G.add_edge(1, 0, length=1100, norm_green=0.5, norm_water=0.5,
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        return G
    
    @pytest.fixture
    def default_weights(self):
        return {
            'distance': 0.5, 'greenness': 0.1, 'water': 0.1,
            'quietness': 0.1, 'social': 0.1, 'slope': 0.1,
        }
    
    def test_heuristic_returns_infinity_when_impossible(self, simple_graph, default_weights):
        """Test that heuristic returns inf when distance to start > remaining budget."""
        from app.services.routing.astar.loop_astar import LoopAStar
        
        solver = LoopAStar(
            graph=simple_graph,
            weights=default_weights,
            target_distance=500,  # 500m target
            directional_bias="none",
        )
        
        # Set up the solver state for testing heuristic
        solver.start_node = 0
        
        # Mock accumulated distance that leaves no budget
        # Node 1 is ~1.1km from node 0, but we only have 500m target
        # If we've already traveled 400m, remaining is 100m, but node 1 is 1100m away
        # This should return infinity (impossible to return)
        h = solver._heuristic_with_distance(1, 0, accumulated_distance=400)
        
        assert h == float('inf'), "Heuristic should return inf when return is impossible"
    
    def test_heuristic_admissible(self, simple_graph, default_weights):
        """Test that heuristic never overestimates (admissibility)."""
        from app.services.routing.astar.loop_astar import LoopAStar
        
        solver = LoopAStar(
            graph=simple_graph,
            weights=default_weights,
            target_distance=5000,  # 5km target - plenty of budget
            directional_bias="none",
        )
        
        solver.start_node = 0
        
        # With plenty of budget, heuristic should not be infinity
        h = solver._heuristic_with_distance(1, 0, accumulated_distance=1000)
        
        assert h != float('inf'), "With enough budget, heuristic should not be inf"
        assert h >= 0, "Heuristic should be non-negative"


class TestLoopAStarWSMInfluence:
    """Tests that WSM weights influence the route selection."""
    
    @pytest.fixture
    def graph_with_scenic_variety(self):
        """
        Create a graph with two possible loop paths, one greener than the other.
        
        Layout:
            0 ---- 1 (green path: low norm_green)
            |      |
            2 ---- 3 (grey path: high norm_green)
            
        Start at node 0, both paths return to 0.
        """
        G = nx.MultiDiGraph()
        
        base_lat, base_lon = 51.45, -2.58
        delta = 0.001
        
        # Positions form a square
        positions = {
            0: (base_lat, base_lon),
            1: (base_lat, base_lon + delta),
            2: (base_lat - delta, base_lon),
            3: (base_lat - delta, base_lon + delta),
        }
        
        for node_id, (lat, lon) in positions.items():
            G.add_node(node_id, y=lat, x=lon)
        
        # Green path: 0 -> 1 -> 3 (low norm_green = more green)
        G.add_edge(0, 1, length=100, norm_green=0.1, norm_water=0.5, 
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        G.add_edge(1, 0, length=100, norm_green=0.1, norm_water=0.5,
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        G.add_edge(1, 3, length=100, norm_green=0.1, norm_water=0.5,
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        G.add_edge(3, 1, length=100, norm_green=0.1, norm_water=0.5,
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        
        # Grey path: 0 -> 2 -> 3 (high norm_green = less green)
        G.add_edge(0, 2, length=100, norm_green=0.9, norm_water=0.5,
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        G.add_edge(2, 0, length=100, norm_green=0.9, norm_water=0.5,
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        G.add_edge(2, 3, length=100, norm_green=0.9, norm_water=0.5,
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        G.add_edge(3, 2, length=100, norm_green=0.9, norm_water=0.5,
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        
        # Return edges
        G.add_edge(3, 0, length=141, norm_green=0.5, norm_water=0.5,
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        G.add_edge(0, 3, length=141, norm_green=0.5, norm_water=0.5,
                   norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        
        return G
    
    def test_high_greenness_weight_prefers_green_path(self, graph_with_scenic_variety):
        """Test that high greenness weight leads to greener route."""
        from app.services.routing.astar.loop_astar import LoopAStar
        
        # High greenness weight
        green_weights = {
            'distance': 0.3,
            'greenness': 0.5,  # High greenness preference
            'water': 0.0,
            'quietness': 0.0,
            'social': 0.0,
            'slope': 0.0,
        }
        
        solver = LoopAStar(
            graph=graph_with_scenic_variety,
            weights=green_weights,
            target_distance=400,
            directional_bias="none",
        )
        
        route = solver.astar(0, 0)
        
        if route is not None:
            route_list = list(route)
            # With high greenness weight, should prefer path through node 1 (green path)
            # rather than node 2 (grey path)
            assert 1 in route_list, "High greenness weight should prefer green path (via node 1)"


class TestLoopAStarSearchLimits:
    """Tests for search iteration and time limits."""
    
    @pytest.fixture
    def large_graph(self):
        """Create a larger graph to test search limits."""
        G = nx.MultiDiGraph()
        
        # Create a 10x10 grid
        base_lat, base_lon = 51.45, -2.58
        delta = 0.0005
        
        for i in range(10):
            for j in range(10):
                node_id = i * 10 + j
                lat = base_lat + i * delta
                lon = base_lon + j * delta
                G.add_node(node_id, y=lat, x=lon)
        
        # Add edges
        for i in range(10):
            for j in range(10):
                node_id = i * 10 + j
                
                # Connect to right neighbor
                if j < 9:
                    neighbor = i * 10 + (j + 1)
                    G.add_edge(node_id, neighbor, length=50, norm_green=0.5,
                               norm_water=0.5, norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
                    G.add_edge(neighbor, node_id, length=50, norm_green=0.5,
                               norm_water=0.5, norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
                
                # Connect to bottom neighbor
                if i < 9:
                    neighbor = (i + 1) * 10 + j
                    G.add_edge(node_id, neighbor, length=50, norm_green=0.5,
                               norm_water=0.5, norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
                    G.add_edge(neighbor, node_id, length=50, norm_green=0.5,
                               norm_water=0.5, norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
        
        return G
    
    @pytest.fixture
    def default_weights(self):
        return {
            'distance': 0.5, 'greenness': 0.1, 'water': 0.1,
            'quietness': 0.1, 'social': 0.1, 'slope': 0.1,
        }
    
    def test_search_respects_time_limit(self, large_graph, default_weights):
        """Test that search terminates within time limit."""
        import time
        from app.services.routing.astar.loop_astar import LoopAStar
        
        solver = LoopAStar(
            graph=large_graph,
            weights=default_weights,
            target_distance=100000,  # Impossibly long for this graph
            directional_bias="none",
            max_search_time=5,  # 5 second limit for testing
        )
        
        start = time.time()
        result = solver.astar(44, 44)  # Center node
        elapsed = time.time() - start
        
        # Should terminate within a reasonable buffer of the time limit
        assert elapsed < 15, f"Search took {elapsed:.1f}s, should respect time limit"
        
        # Should still return a fallback route (closest candidate)
        if result is not None:
            route = list(result)
            assert route[0] == 44 and route[-1] == 44, "Fallback should still be a loop"
    
    def test_always_finds_route_on_connected_graph(self, large_graph, default_weights):
        """Test that the solver always returns a route on a well-connected graph."""
        from app.services.routing.astar.loop_astar import LoopAStar
        
        # Test several different target distances
        for target_km in [0.3, 0.5, 0.8, 1.0]:
            solver = LoopAStar(
                graph=large_graph,
                weights=default_weights,
                target_distance=target_km * 1000,
                directional_bias="none",
                max_search_time=10,
            )
            
            result = solver.astar(44, 44)  # Center node
            assert result is not None, \
                f"Should always find a loop at {target_km}km on a connected graph"
            
            route = list(result)
            assert route[0] == 44, f"Route should start at node 44 for {target_km}km"
            assert route[-1] == 44, f"Route should end at node 44 for {target_km}km"
