"""
Test suite for the WSM A* Implementation.

Tests the WSMNetworkXAStar class and integration with RouteFinder.
Uses mocked graphs to verify correct path selection based on scenic weights.
"""

import pytest
import networkx as nx
from unittest.mock import MagicMock, patch


@pytest.fixture
def simple_graph():
    """
    Creates a simple graph with two paths between nodes.
    
    Structure:
        1 -----(direct, short, not scenic)----- 3
         \\                                     /
          \\---(via 2, longer, very scenic)---/
    
    Node positions:
        1: (0, 0)
        2: (0.001, 0.0005) - detour
        3: (0.002, 0)
    
    Normalised values use cost semantics: 0 = good, 1 = bad
    - norm_green=0 means very green (good), norm_green=1 means no green (bad)
    - norm_quiet=0 means quiet (good), norm_quiet=1 means noisy (bad)
    
    Edge design:
    - Direct path: 100m, no scenic features (high norm costs)
    - Scenic path: 2x150m=300m, excellent scenic features (low norm costs)
    """
    G = nx.MultiDiGraph()
    
    # Add nodes with coordinates
    G.add_node(1, x=0.0, y=0.0)
    G.add_node(2, x=0.001, y=0.0005)  # Slight detour
    G.add_node(3, x=0.002, y=0.0)
    
    # Direct path: SHORTER but NOT scenic (high costs)
    G.add_edge(1, 3, 0,
        length=100.0,             # Shortest edge in graph
        norm_green=1.0,           # No greenness (bad - cost=1)
        norm_water=1.0,           # No water (bad - cost=1)
        norm_social=1.0,          # No POIs (bad - cost=1)
        norm_quiet=1.0,           # Very noisy (bad - cost=1)
        norm_slope=1.0            # Very steep (bad - cost=1)
    )
    
    # Via node 2: LONGER but excellent scenic features (low costs)
    G.add_edge(1, 2, 0,
        length=150.0,             # Longer edge
        norm_green=0.0,           # Very green (good - cost=0)
        norm_water=0.0,           # Near water (good - cost=0)
        norm_social=0.0,          # Near POIs (good - cost=0)
        norm_quiet=0.0,           # Very quiet (good - cost=0)
        norm_slope=0.0            # Flat (good - cost=0)
    )
    G.add_edge(2, 3, 0,
        length=150.0,             # Longer edge (total 300m via scenic route)
        norm_green=0.0,           # Very green
        norm_water=0.0,           # Near water
        norm_social=0.0,          # Near POIs
        norm_quiet=0.0,           # Very quiet
        norm_slope=0.0            # Flat
    )
    
    return G


@pytest.fixture
def distance_only_weights():
    """Weights that mimic standard shortest path."""
    return {
        'distance': 1.0,
        'greenness': 0.0,
        'water': 0.0,
        'quietness': 0.0,
        'social': 0.0,
        'slope': 0.0,
    }


@pytest.fixture
def greenness_focused_weights():
    """Weights that heavily favour green routes."""
    return {
        'distance': 0.2,
        'greenness': 0.6,
        'water': 0.05,
        'quietness': 0.05,
        'social': 0.05,
        'slope': 0.05,
    }


class TestWSMNetworkXAStar:
    """Tests for the WSMNetworkXAStar class."""
    
    def test_finds_path(self, simple_graph):
        """Should find a valid path between nodes."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        
        solver = WSMNetworkXAStar(simple_graph)
        path = list(solver.astar(1, 3))
        
        assert path is not None
        assert len(path) >= 2
        assert path[0] == 1
        assert path[-1] == 3
    
    def test_distance_only_chooses_direct_path(self, simple_graph, distance_only_weights):
        """With distance-only weights, should choose direct (shorter) path."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        
        solver = WSMNetworkXAStar(simple_graph, weights=distance_only_weights)
        path = list(solver.astar(1, 3))
        
        # Direct path is 1 -> 3 (150m)
        # Via path is 1 -> 2 -> 3 (200m)
        assert path == [1, 3], f"Expected direct path [1, 3], got {path}"
    
    def test_greenness_focused_chooses_scenic_path(self, simple_graph, greenness_focused_weights):
        """With high greenness weight, should choose greener (longer) path."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        
        solver = WSMNetworkXAStar(simple_graph, weights=greenness_focused_weights)
        path = list(solver.astar(1, 3))
        
        # Scenic path via node 2 has norm_green=1.0 (best)
        # Direct path has norm_green=0.0 (worst)
        assert path == [1, 2, 3], f"Expected scenic path [1, 2, 3], got {path}"
    
    def test_neighbors_returns_adjacent_nodes(self, simple_graph):
        """neighbors() should return correct adjacent nodes."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        
        solver = WSMNetworkXAStar(simple_graph)
        neighbors = solver.neighbors(1)
        
        assert 2 in neighbors
        assert 3 in neighbors
    
    def test_distance_between_returns_wsm_cost(self, simple_graph):
        """distance_between() should return WSM cost, not raw length."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        
        # Weights that heavily favour greenness over distance
        weights = {
            'distance': 0.1,
            'greenness': 0.7,      # Heavily weighted
            'water': 0.05,
            'quietness': 0.05,
            'social': 0.05,
            'slope': 0.05,
        }
        
        solver = WSMNetworkXAStar(simple_graph, weights=weights)
        
        # Edge 1->3: length=100 (min), norm_green=0.0 (worst)
        # Edge 1->2: length=150 (max), norm_green=1.0 (best)
        # With greenness weight high, scenic edge should have lower total cost
        
        cost_direct = solver.distance_between(1, 3)
        cost_scenic = solver.distance_between(1, 2)
        
        # Scenic edge should have lower cost due to greenness benefit
        assert cost_scenic < cost_direct, f"Expected scenic {cost_scenic} < direct {cost_direct}"
    
    def test_heuristic_is_admissible(self, simple_graph, distance_only_weights):
        """Heuristic should never overestimate actual cost."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        
        solver = WSMNetworkXAStar(simple_graph, weights=distance_only_weights)
        
        # Heuristic from 1 to 3
        h = solver.heuristic_cost_estimate(1, 3)
        
        # Actual cost (direct path)
        actual = solver.distance_between(1, 3)
        
        assert h <= actual, f"Heuristic {h} overestimates actual cost {actual}"


class TestRouteFinderWSMToggle:
    """
    Tests for RouteFinder WSM toggle functionality.
    
    Note: These tests verify the WSM toggle logic at the integration level.
    They require mocking Flask's current_app for configuration access.
    """
    
    def test_wsm_solver_imported_correctly(self):
        """Verify WSMNetworkXAStar can be imported from the expected location."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        from app.services.routing.astar.astar import OSMNetworkXAStar
        
        assert WSMNetworkXAStar is not None
        assert OSMNetworkXAStar is not None
    
    def test_wsm_and_standard_produce_different_paths(self, simple_graph, distance_only_weights, greenness_focused_weights):
        """WSM and standard A* should produce different paths when weights differ."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        from app.services.routing.astar.astar import OSMNetworkXAStar
        
        # Standard A* (distance only)
        standard_solver = OSMNetworkXAStar(simple_graph)
        standard_path = list(standard_solver.astar(1, 3))
        
        # WSM A* with greenness focus
        wsm_solver = WSMNetworkXAStar(simple_graph, weights=greenness_focused_weights)
        wsm_path = list(wsm_solver.astar(1, 3))
        
        # They should produce different routes
        assert standard_path == [1, 3]  # Shortest distance
        assert wsm_path == [1, 2, 3]    # Greenest route
    
    def test_wsm_with_distance_only_matches_standard(self, simple_graph, distance_only_weights):
        """WSM with distance=1.0 should behave like standard A*."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        from app.services.routing.astar.astar import OSMNetworkXAStar
        
        standard_solver = OSMNetworkXAStar(simple_graph)
        standard_path = list(standard_solver.astar(1, 3))
        
        wsm_solver = WSMNetworkXAStar(simple_graph, weights=distance_only_weights)
        wsm_path = list(wsm_solver.astar(1, 3))
        
        # Both should choose the shortest distance path
        assert standard_path == wsm_path
    
    def test_route_finder_accepts_wsm_parameters(self, simple_graph):
        """RouteFinder.find_route() should accept use_wsm and weights parameters."""
        from app.services.routing.route_finder import RouteFinder
        import inspect
        
        sig = inspect.signature(RouteFinder.find_route)
        params = list(sig.parameters.keys())
        
        assert 'use_wsm' in params
        assert 'weights' in params


class TestWSMEdgeCases:
    """Tests for edge cases in WSM implementation."""
    
    def test_handles_missing_norm_attributes(self):
        """Should use defaults when norm_* attributes are missing."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        
        G = nx.MultiDiGraph()
        G.add_node(1, x=0.0, y=0.0)
        G.add_node(2, x=0.001, y=0.0)
        G.add_edge(1, 2, 0, length=100.0)  # No norm_* attributes
        
        solver = WSMNetworkXAStar(G)
        cost = solver.distance_between(1, 2)
        
        # Should not raise, should use default 0.5 values
        assert cost > 0
    
    def test_handles_empty_edge_data(self):
        """Should return infinity for nodes with no connecting edges."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        
        G = nx.MultiDiGraph()
        G.add_node(1, x=0.0, y=0.0)
        G.add_node(2, x=0.001, y=0.0)
        # No edge between 1 and 2
        
        solver = WSMNetworkXAStar(G)
        
        # Should handle gracefully (KeyError or return infinity)
        try:
            cost = solver.distance_between(1, 2)
            assert cost == float('inf')
        except KeyError:
            pass  # Also acceptable
    
    def test_single_node_path(self):
        """Should handle start=goal case."""
        from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
        
        G = nx.MultiDiGraph()
        G.add_node(1, x=0.0, y=0.0)
        
        solver = WSMNetworkXAStar(G)
        path = list(solver.astar(1, 1))
        
        assert path == [1]
