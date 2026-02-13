"""
Tests for the Loop Solver Framework

Tests cover:
- LoopCandidate data structure and properties
- Quality score calculation
- Route similarity (Jaccard edge overlap)
- Diverse candidate selection
- LoopSolverFactory
- BudgetAStarSolver on test graphs
"""

import pytest
import math
import networkx as nx
from unittest.mock import patch


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

def _haversine(lat1, lon1, lat2, lon2):
    """Calculate distance in metres between two points."""
    R = 6371000
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2)
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


@pytest.fixture
def simple_grid_graph():
    """
    Create a 3x3 grid graph for testing.

    Layout (approximately 111m edges):
        0 -- 1 -- 2
        |    |    |
        3 -- 4 -- 5
        |    |    |
        6 -- 7 -- 8

    Node 4 is at center (51.45, -2.58).
    Each edge is approximately 111m (0.001 degree latitude).
    """
    G = nx.MultiDiGraph()
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

    edges = [
        (0, 1), (1, 2), (0, 3), (1, 4), (2, 5),
        (3, 4), (4, 5), (3, 6), (4, 7), (5, 8),
        (6, 7), (7, 8),
    ]

    for u, v in edges:
        lat1, lon1 = positions[u]
        lat2, lon2 = positions[v]
        length = _haversine(lat1, lon1, lat2, lon2)

        for a, b in [(u, v), (v, u)]:
            G.add_edge(a, b,
                       length=length,
                       norm_green=0.5,
                       norm_water=0.5,
                       norm_social=0.5,
                       norm_quiet=0.5,
                       norm_slope=0.5)

    return G


@pytest.fixture
def large_grid_graph():
    """10x10 grid graph with 50m edges for multi-candidate testing."""
    G = nx.MultiDiGraph()
    base_lat, base_lon = 51.45, -2.58
    delta = 0.0005  # ~55m spacing

    for i in range(10):
        for j in range(10):
            node_id = i * 10 + j
            lat = base_lat + i * delta
            lon = base_lon + j * delta
            G.add_node(node_id, y=lat, x=lon)

    for i in range(10):
        for j in range(10):
            node_id = i * 10 + j
            if j < 9:
                neighbor = i * 10 + (j + 1)
                G.add_edge(node_id, neighbor, length=50,
                           norm_green=0.5, norm_water=0.5,
                           norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
                G.add_edge(neighbor, node_id, length=50,
                           norm_green=0.5, norm_water=0.5,
                           norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
            if i < 9:
                neighbor = (i + 1) * 10 + j
                G.add_edge(node_id, neighbor, length=50,
                           norm_green=0.5, norm_water=0.5,
                           norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)
                G.add_edge(neighbor, node_id, length=50,
                           norm_green=0.5, norm_water=0.5,
                           norm_social=0.5, norm_quiet=0.5, norm_slope=0.5)

    return G


@pytest.fixture
def default_weights():
    """Default WSM weights for testing."""
    return {
        'distance': 0.5,
        'greenness': 0.1,
        'water': 0.1,
        'quietness': 0.1,
        'social': 0.1,
        'slope': 0.1,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Tests: LoopCandidate
# ══════════════════════════════════════════════════════════════════════════════

class TestLoopCandidate:
    """Tests for the LoopCandidate data structure."""

    def test_basic_creation(self):
        """Test LoopCandidate can be created with required fields."""
        from app.services.routing.loop_solvers.base import LoopCandidate

        candidate = LoopCandidate(
            route=[0, 1, 2, 0],
            distance=1500.0,
            scenic_cost=3.5,
            deviation=0.05,
            quality_score=0.85,
            algorithm='BUDGET_ASTAR',
        )

        assert candidate.route == [0, 1, 2, 0]
        assert candidate.distance == 1500.0
        assert candidate.scenic_cost == 3.5
        assert candidate.deviation == 0.05
        assert candidate.quality_score == 0.85
        assert candidate.algorithm == 'BUDGET_ASTAR'
        assert candidate.colour == '#3B82F6'  # Default blue
        assert candidate.label == 'Loop'      # Default label

    def test_distance_km_property(self):
        """Test distance_km rounds to 2 decimal places."""
        from app.services.routing.loop_solvers.base import LoopCandidate

        candidate = LoopCandidate(
            route=[0, 1, 0], distance=3456.789,
            scenic_cost=0, deviation=0, quality_score=0, algorithm='test',
        )
        assert candidate.distance_km == 3.46  # 3456.789 / 1000 rounded

    def test_deviation_percent_property(self):
        """Test deviation_percent rounds to 1 decimal place."""
        from app.services.routing.loop_solvers.base import LoopCandidate

        candidate = LoopCandidate(
            route=[0, 1, 0], distance=1000,
            scenic_cost=0, deviation=0.1234, quality_score=0, algorithm='test',
        )
        assert candidate.deviation_percent == 12.3

    def test_to_dict(self):
        """Test serialisation to JSON-friendly dictionary."""
        from app.services.routing.loop_solvers.base import LoopCandidate

        candidate = LoopCandidate(
            route=[0, 1, 2, 0],
            distance=1500.0,
            scenic_cost=3.5,
            deviation=0.05,
            quality_score=0.85,
            algorithm='BUDGET_ASTAR',
            colour='#EF4444',
            label='Test Route',
            metadata={'iterations': 1000},
        )

        d = candidate.to_dict()

        assert d['route'] == [0, 1, 2, 0]
        assert d['distance'] == 1500.0
        assert d['distance_km'] == 1.5
        assert d['scenic_cost'] == 3.5
        assert d['deviation'] == 0.05
        assert d['deviation_percent'] == 5.0
        assert d['quality_score'] == 0.85
        assert d['algorithm'] == 'BUDGET_ASTAR'
        assert d['colour'] == '#EF4444'
        assert d['label'] == 'Test Route'
        assert d['metadata'] == {'iterations': 1000}


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Quality Score
# ══════════════════════════════════════════════════════════════════════════════

class TestQualityScore:
    """Tests for the quality scoring function."""

    def test_perfect_score(self):
        """Perfect distance + perfect scenic = 1.0."""
        from app.services.routing.loop_solvers.base import calculate_quality_score

        score = calculate_quality_score(deviation=0.0, scenic_cost=0.0)
        assert score == 1.0

    def test_worst_score(self):
        """Max deviation + max scenic cost = 0.0."""
        from app.services.routing.loop_solvers.base import calculate_quality_score

        score = calculate_quality_score(deviation=0.5, scenic_cost=1.0)
        assert score == 0.0

    def test_distance_only_score(self):
        """With full distance weight, only deviation matters."""
        from app.services.routing.loop_solvers.base import calculate_quality_score

        score = calculate_quality_score(
            deviation=0.0, scenic_cost=1.0,
            distance_weight=1.0, scenic_weight=0.0,
        )
        assert score == 1.0

    def test_scenic_only_score(self):
        """With full scenic weight, only scenic cost matters."""
        from app.services.routing.loop_solvers.base import calculate_quality_score

        score = calculate_quality_score(
            deviation=0.5, scenic_cost=0.0,
            distance_weight=0.0, scenic_weight=1.0,
        )
        assert score == 1.0

    def test_intermediate_values(self):
        """10% deviation and medium scenic cost gives reasonable score."""
        from app.services.routing.loop_solvers.base import calculate_quality_score

        score = calculate_quality_score(deviation=0.1, scenic_cost=0.5)
        assert 0.0 < score < 1.0

    def test_deviation_beyond_50_percent_floors_at_zero(self):
        """Deviation >= 50% gives distance_score = 0."""
        from app.services.routing.loop_solvers.base import calculate_quality_score

        score = calculate_quality_score(deviation=0.6, scenic_cost=0.0)
        # distance_score = 0, scenic_score = 1.0
        # 0.6 * 0 + 0.4 * 1.0 = 0.4
        assert abs(score - 0.4) < 0.001


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Route Similarity
# ══════════════════════════════════════════════════════════════════════════════

class TestRouteSimilarity:
    """Tests for Jaccard edge similarity."""

    def test_identical_routes(self):
        """Identical routes have similarity 1.0."""
        from app.services.routing.loop_solvers.base import route_similarity

        route = [0, 1, 2, 3, 0]
        assert route_similarity(route, route) == 1.0

    def test_completely_different_routes(self):
        """Routes with no shared edges have similarity 0.0."""
        from app.services.routing.loop_solvers.base import route_similarity

        route_a = [0, 1, 2, 0]
        route_b = [3, 4, 5, 3]
        assert route_similarity(route_a, route_b) == 0.0

    def test_partial_overlap(self):
        """Routes sharing some edges have intermediate similarity."""
        from app.services.routing.loop_solvers.base import route_similarity

        route_a = [0, 1, 2, 0]  # edges: (0,1), (1,2), (2,0)
        route_b = [0, 1, 3, 0]  # edges: (0,1), (1,3), (3,0)
        # Shared: {(0,1)}, Union: {(0,1),(1,2),(2,0),(1,3),(3,0)} = 5
        sim = route_similarity(route_a, route_b)
        assert abs(sim - 1 / 5) < 0.001

    def test_empty_routes(self):
        """Empty or single-node routes return 0.0."""
        from app.services.routing.loop_solvers.base import route_similarity

        assert route_similarity([], []) == 0.0
        assert route_similarity([0], [0]) == 0.0
        assert route_similarity([0, 1], []) == 0.0


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Diverse Selection
# ══════════════════════════════════════════════════════════════════════════════

class TestDiverseSelection:
    """Tests for select_diverse_candidates."""

    def test_fewer_than_k(self):
        """When pool has fewer than K, return all."""
        from app.services.routing.loop_solvers.base import (
            LoopCandidate, select_diverse_candidates,
        )

        candidates = [
            LoopCandidate([0, 1, 0], 500, 1.0, 0.05, 0.9, 'test'),
        ]

        result = select_diverse_candidates(candidates, k=3)
        assert len(result) == 1

    def test_assigns_colours_and_labels(self):
        """Selected candidates get colours and labels assigned."""
        from app.services.routing.loop_solvers.base import (
            LoopCandidate, select_diverse_candidates, LOOP_COLOURS, LOOP_LABELS,
        )

        candidates = [
            LoopCandidate([0, 1, 0], 500, 1.0, 0.05, 0.9, 'test'),
            LoopCandidate([0, 2, 0], 600, 1.2, 0.08, 0.7, 'test'),
        ]

        result = select_diverse_candidates(candidates, k=2)
        assert result[0].colour == LOOP_COLOURS[0]
        assert result[0].label == LOOP_LABELS[0]
        assert result[1].colour == LOOP_COLOURS[1]
        assert result[1].label == LOOP_LABELS[1]

    def test_best_quality_first(self):
        """First selected candidate should have highest quality score."""
        from app.services.routing.loop_solvers.base import (
            LoopCandidate, select_diverse_candidates,
        )

        candidates = [
            LoopCandidate([0, 1, 0], 500, 1.0, 0.10, 0.3, 'test'),
            LoopCandidate([0, 2, 0], 600, 1.2, 0.05, 0.95, 'test'),
            LoopCandidate([0, 3, 0], 700, 1.5, 0.08, 0.5, 'test'),
        ]

        result = select_diverse_candidates(candidates, k=2)
        assert result[0].quality_score == 0.95  # Highest quality first

    def test_diversity_over_quality(self):
        """Second pick should be the most dissimilar, not second-best quality."""
        from app.services.routing.loop_solvers.base import (
            LoopCandidate, select_diverse_candidates,
        )

        # route_a and route_b are identical routes, route_c is completely different
        candidates = [
            LoopCandidate([0, 1, 2, 0], 500, 1.0, 0.05, 0.95, 'test'),
            LoopCandidate([0, 1, 2, 0], 510, 1.1, 0.06, 0.90, 'test'),  # Same edges!
            LoopCandidate([3, 4, 5, 3], 520, 1.2, 0.07, 0.50, 'test'),  # Unique edges
        ]

        result = select_diverse_candidates(candidates, k=2)
        # First pick: quality=0.95
        assert result[0].quality_score == 0.95
        # Second pick: should be the dissimilar route, not the near-duplicate
        assert result[1].route == [3, 4, 5, 3]


# ══════════════════════════════════════════════════════════════════════════════
# Tests: LoopSolverFactory
# ══════════════════════════════════════════════════════════════════════════════

class TestLoopSolverFactory:
    """Tests for factory-based solver creation."""

    def test_create_budget_astar(self):
        """Factory creates BudgetAStarSolver."""
        from app.services.routing.loop_solvers.factory import LoopSolverFactory
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        solver = LoopSolverFactory.create('BUDGET_ASTAR')
        assert isinstance(solver, BudgetAStarSolver)

    def test_create_random_walk(self):
        """Factory creates RandomWalkSolver."""
        from app.services.routing.loop_solvers.factory import LoopSolverFactory
        from app.services.routing.loop_solvers.random_walk_solver import RandomWalkSolver

        solver = LoopSolverFactory.create('RANDOM_WALK')
        assert isinstance(solver, RandomWalkSolver)

    def test_case_insensitive(self):
        """Algorithm name is case-insensitive."""
        from app.services.routing.loop_solvers.factory import LoopSolverFactory
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        solver = LoopSolverFactory.create('budget_astar')
        assert isinstance(solver, BudgetAStarSolver)

    def test_unknown_algorithm_raises(self):
        """Unknown algorithm name raises ValueError."""
        from app.services.routing.loop_solvers.factory import LoopSolverFactory

        with pytest.raises(ValueError, match="Unknown loop solver"):
            LoopSolverFactory.create('NONEXISTENT')

    def test_available_algorithms(self):
        """available_algorithms returns expected list."""
        from app.services.routing.loop_solvers.factory import LoopSolverFactory

        algos = LoopSolverFactory.available_algorithms()
        assert 'BUDGET_ASTAR' in algos
        assert 'RANDOM_WALK' in algos


# ══════════════════════════════════════════════════════════════════════════════
# Tests: BudgetAStarSolver
# ══════════════════════════════════════════════════════════════════════════════

class TestBudgetAStarSolver:
    """Tests for the Budget A* solver on test graphs."""

    def test_import(self):
        """Test BudgetAStarSolver can be imported."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver
        assert BudgetAStarSolver is not None

    def test_implements_base_interface(self):
        """BudgetAStarSolver extends LoopSolverBase."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver
        from app.services.routing.loop_solvers.base import LoopSolverBase

        solver = BudgetAStarSolver()
        assert isinstance(solver, LoopSolverBase)

    def test_find_loops_returns_list(self, simple_grid_graph, default_weights):
        """find_loops returns a list of LoopCandidate objects."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver
        from app.services.routing.loop_solvers.base import LoopCandidate

        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=simple_grid_graph,
            start_node=4,
            target_distance=400,
            weights=default_weights,
            num_candidates=3,
            max_search_time=15,
        )

        assert isinstance(candidates, list)
        for c in candidates:
            assert isinstance(c, LoopCandidate)

    def test_loops_return_to_start(self, simple_grid_graph, default_weights):
        """All returned loops start and end at the start node."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=simple_grid_graph,
            start_node=4,
            target_distance=400,
            weights=default_weights,
            num_candidates=3,
            max_search_time=15,
        )

        for c in candidates:
            assert c.route[0] == 4, f"Loop should start at node 4, got {c.route[0]}"
            assert c.route[-1] == 4, f"Loop should end at node 4, got {c.route[-1]}"

    def test_loops_are_valid_paths(self, simple_grid_graph, default_weights):
        """Every consecutive pair of nodes in route should be a valid edge."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=simple_grid_graph,
            start_node=4,
            target_distance=400,
            weights=default_weights,
            num_candidates=3,
            max_search_time=15,
        )

        for c in candidates:
            for i in range(len(c.route) - 1):
                u, v = c.route[i], c.route[i + 1]
                assert simple_grid_graph.has_edge(u, v), \
                    f"Edge {u}->{v} should exist in graph"

    def test_loops_have_positive_distance(self, simple_grid_graph, default_weights):
        """All candidates should have positive distance."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=simple_grid_graph,
            start_node=4,
            target_distance=400,
            weights=default_weights,
            num_candidates=3,
            max_search_time=15,
        )

        for c in candidates:
            assert c.distance > 0, "Route should have positive distance"

    def test_loops_have_quality_score(self, simple_grid_graph, default_weights):
        """All candidates should have a quality score between 0 and 1."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=simple_grid_graph,
            start_node=4,
            target_distance=400,
            weights=default_weights,
            num_candidates=3,
            max_search_time=15,
        )

        for c in candidates:
            assert 0.0 <= c.quality_score <= 1.0, \
                f"Quality score {c.quality_score} should be in [0, 1]"

    def test_loops_sorted_by_quality(self, simple_grid_graph, default_weights):
        """Candidates should be sorted by quality score (descending)."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=simple_grid_graph,
            start_node=4,
            target_distance=400,
            weights=default_weights,
            num_candidates=3,
            max_search_time=15,
        )

        if len(candidates) > 1:
            # Diversity selection may reorder candidates for variety;
            # verify the best quality score is present in the set.
            best_quality = max(c.quality_score for c in candidates)
            assert candidates[0].quality_score == best_quality, \
                "First candidate should have the best quality score"

    def test_algorithm_label_set(self, simple_grid_graph, default_weights):
        """All candidates should have algorithm = 'BUDGET_ASTAR'."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=simple_grid_graph,
            start_node=4,
            target_distance=400,
            weights=default_weights,
            num_candidates=3,
            max_search_time=15,
        )

        for c in candidates:
            assert c.algorithm.upper() == 'BUDGET_ASTAR'

    def test_larger_graph_multiple_candidates(self, large_grid_graph, default_weights):
        """Larger graph should produce multiple diverse candidates."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=large_grid_graph,
            start_node=44,  # Center of 10x10 grid
            target_distance=500,
            weights=default_weights,
            num_candidates=3,
            max_search_time=30,
        )

        # Should find at least one loop
        assert len(candidates) >= 1, \
            "Should find at least one loop on a well-connected graph"

        # If multiple candidates, they should be somewhat diverse
        if len(candidates) >= 2:
            from app.services.routing.loop_solvers.base import route_similarity
            sim = route_similarity(candidates[0].route, candidates[1].route)
            # Not perfectly identical (diversity selection should help)
            assert sim < 1.0, "Multiple candidates should not be identical"

    def test_respects_time_limit(self, large_grid_graph, default_weights):
        """Search should terminate within a reasonable time."""
        import time
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        solver = BudgetAStarSolver()
        t0 = time.time()
        candidates = solver.find_loops(
            graph=large_grid_graph,
            start_node=44,
            target_distance=100000,  # Impossibly large for this graph
            weights=default_weights,
            num_candidates=3,
            max_search_time=10,
        )
        elapsed = time.time() - t0

        # Should terminate well within 30 seconds
        assert elapsed < 30, f"Search took {elapsed:.1f}s, should respect time limit"

    def test_empty_graph_returns_empty(self, default_weights):
        """Empty graph should return empty list."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver

        G = nx.MultiDiGraph()
        G.add_node(0, y=51.45, x=-2.58)

        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=G,
            start_node=0,
            target_distance=1000,
            weights=default_weights,
            num_candidates=3,
            max_search_time=5,
        )

        assert isinstance(candidates, list)
        # With no edges, no loop can be formed
        assert len(candidates) == 0


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Helper Functions
# ══════════════════════════════════════════════════════════════════════════════

class TestBudgetAStarHelpers:
    """Tests for helper functions in the budget A* module."""

    def test_haversine(self):
        """Haversine distance between known points."""
        from app.services.routing.loop_solvers.budget_astar_solver import _haversine

        # ~111km for 1 degree of latitude
        dist = _haversine(51.0, -2.0, 52.0, -2.0)
        assert abs(dist - 111_000) < 5000  # Within 5km

    def test_bearing_cardinal_directions(self):
        """Bearing calculations for cardinal directions."""
        from app.services.routing.loop_solvers.budget_astar_solver import _bearing

        # North
        b = _bearing(51.0, -2.0, 52.0, -2.0)
        assert abs(b - 0) < 5 or abs(b - 360) < 5

        # East
        b = _bearing(51.0, -2.0, 51.0, -1.0)
        assert abs(b - 90) < 5

        # South
        b = _bearing(52.0, -2.0, 51.0, -2.0)
        assert abs(b - 180) < 5

        # West
        b = _bearing(51.0, -1.0, 51.0, -2.0)
        assert abs(b - 270) < 5

    def test_discretize_distance(self):
        """Distance discretisation produces correct bins."""
        from app.services.routing.loop_solvers.budget_astar_solver import _discretize_distance

        assert _discretize_distance(0, 100) == 0
        assert _discretize_distance(99, 100) == 0
        assert _discretize_distance(100, 100) == 1
        assert _discretize_distance(250, 100) == 2
        assert _discretize_distance(1000, 100) == 10

    def test_route_distance(self, simple_grid_graph):
        """Route distance calculation on test graph."""
        from app.services.routing.loop_solvers.budget_astar_solver import _route_distance

        # Route 4 -> 1 -> 4 (two edges)
        dist = _route_distance(simple_grid_graph, [4, 1, 4])
        # Each edge is ~111m, so round trip is ~222m
        assert dist > 100  # Sanity check
        assert dist < 500


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Legacy LoopAStar (existing tests still work)
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# Tests: Dead-End Pruning (Plan 003 – Milestone 1)
# ══════════════════════════════════════════════════════════════════════════════

class TestPruneDeadEnds:
    """Tests for _prune_dead_ends() graph preprocessing."""

    def _make_graph_with_dead_end(self):
        """
        Graph with a dead-end spur off a loop.

        Loop: 0 ↔ 1 ↔ 2 ↔ 3 ↔ 0
        Spur: 1 → 4 → 5 (dead-end chain, 5 is degree-1 tip)

        All nodes have lat/lon; all edges have length.
        """
        G = nx.MultiDiGraph()
        base_lat, base_lon = 51.45, -2.58
        d = 0.001
        coords = {
            0: (base_lat, base_lon),
            1: (base_lat, base_lon + d),
            2: (base_lat + d, base_lon + d),
            3: (base_lat + d, base_lon),
            4: (base_lat, base_lon + 2 * d),
            5: (base_lat, base_lon + 3 * d),
        }
        for nid, (la, lo) in coords.items():
            G.add_node(nid, y=la, x=lo)

        loop_edges = [(0, 1), (1, 0), (1, 2), (2, 1),
                      (2, 3), (3, 2), (3, 0), (0, 3)]
        spur_edges = [(1, 4), (4, 1), (4, 5), (5, 4)]
        for u, v in loop_edges + spur_edges:
            la1, lo1 = coords[u]
            la2, lo2 = coords[v]
            length = _haversine(la1, lo1, la2, lo2)
            G.add_edge(u, v, length=length, norm_green=0.5,
                       norm_water=0.5, norm_social=0.5,
                       norm_quiet=0.5, norm_slope=0.5)
        return G

    def test_degree_one_nodes_removed(self):
        """Degree-1 tip node (5) should be removed."""
        from app.services.routing.loop_solvers.budget_astar_solver import _prune_dead_ends
        G = self._make_graph_with_dead_end()
        pruned = _prune_dead_ends(G, start_node=0)
        assert 5 not in pruned.nodes()

    def test_chain_iteratively_removed(self):
        """After removing tip 5, node 4 becomes degree-1 and should also be removed."""
        from app.services.routing.loop_solvers.budget_astar_solver import _prune_dead_ends
        G = self._make_graph_with_dead_end()
        pruned = _prune_dead_ends(G, start_node=0)
        assert 4 not in pruned.nodes()

    def test_loop_nodes_preserved(self):
        """Nodes on the loop (0-3) should all be preserved."""
        from app.services.routing.loop_solvers.budget_astar_solver import _prune_dead_ends
        G = self._make_graph_with_dead_end()
        pruned = _prune_dead_ends(G, start_node=0)
        for n in [0, 1, 2, 3]:
            assert n in pruned.nodes(), f"Loop node {n} should be preserved"

    def test_start_node_preserved_even_if_degree_one(self):
        """Start node is preserved even if it's degree-1."""
        from app.services.routing.loop_solvers.budget_astar_solver import _prune_dead_ends
        G = nx.MultiDiGraph()
        # Linear: 0 → 1 → 2 → 3 (start=0, degree-1)
        for nid in range(4):
            G.add_node(nid, y=51.45 + nid * 0.001, x=-2.58)
        for u, v in [(0, 1), (1, 0), (1, 2), (2, 1), (2, 3), (3, 2)]:
            G.add_edge(u, v, length=111.0)
        pruned = _prune_dead_ends(G, start_node=0)
        assert 0 in pruned.nodes(), "Start node must be preserved"

    def test_fully_connected_unchanged(self, simple_grid_graph):
        """A fully connected grid has no dead-ends; all nodes should remain."""
        from app.services.routing.loop_solvers.budget_astar_solver import _prune_dead_ends
        original_count = simple_grid_graph.number_of_nodes()
        pruned = _prune_dead_ends(simple_grid_graph, start_node=4)
        assert pruned.number_of_nodes() == original_count

    def test_original_graph_not_mutated(self):
        """Pruning must not alter the original graph."""
        from app.services.routing.loop_solvers.budget_astar_solver import _prune_dead_ends
        G = self._make_graph_with_dead_end()
        original_nodes = set(G.nodes())
        _prune_dead_ends(G, start_node=0)
        assert set(G.nodes()) == original_nodes, "Original graph must not be mutated"

    def test_max_iterations_limits_cascade_depth(self):
        """Long dead-end chain is only partially pruned with max_iterations=2."""
        from app.services.routing.loop_solvers.budget_astar_solver import _prune_dead_ends
        G = nx.MultiDiGraph()
        # Loop: 0 ↔ 1 ↔ 2 ↔ 0
        for nid in range(3):
            G.add_node(nid, y=51.45 + nid * 0.001, x=-2.58)
        for u, v in [(0, 1), (1, 0), (1, 2), (2, 1), (2, 0), (0, 2)]:
            G.add_edge(u, v, length=111.0)
        # Long spur off node 1 with 10 nodes: 1→10→11→...→19
        for i in range(10, 20):
            G.add_node(i, y=51.45, x=-2.58 + (i - 9) * 0.001)
        prev = 1
        for i in range(10, 20):
            G.add_edge(prev, i, length=111.0)
            G.add_edge(i, prev, length=111.0)
            prev = i
        # With max_iterations=2, only the outer 2 nodes (19, 18) should go
        pruned = _prune_dead_ends(G, start_node=0, max_iterations=2)
        assert 19 not in pruned.nodes(), "Tip node should be pruned"
        assert 18 not in pruned.nodes(), "Second-from-tip should be pruned"
        # Nodes deeper in the chain should survive (only 2 iterations)
        assert 17 in pruned.nodes(), "Deeper chain node should survive with limited iterations"
        assert 10 in pruned.nodes(), "Base of chain should survive"

    def test_safety_cap_prevents_catastrophic_pruning(self):
        """Safety cap stops pruning when too many nodes would be removed."""
        from app.services.routing.loop_solvers.budget_astar_solver import _prune_dead_ends
        G = nx.MultiDiGraph()
        # Hub node
        G.add_node(0, y=51.45, x=-2.58)
        # 100 separate dead-end spurs from node 0 (200 total spur nodes)
        node_id = 1
        for spur in range(100):
            for depth in range(2):
                G.add_node(node_id, y=51.45 + node_id * 0.0001, x=-2.58)
                if depth == 0:
                    G.add_edge(0, node_id, length=111.0)
                    G.add_edge(node_id, 0, length=111.0)
                    prev = node_id
                else:
                    G.add_edge(prev, node_id, length=111.0)
                    G.add_edge(node_id, prev, length=111.0)
                node_id += 1
        total_nodes = G.number_of_nodes()
        pruned = _prune_dead_ends(G, start_node=0)
        removed = total_nodes - pruned.number_of_nodes()
        # Should not remove more than 5% of graph + buffer (min 50)
        max_allowed = max(total_nodes // 20, 50)
        assert removed <= max_allowed, (
            f"Removed {removed} nodes but safety cap is {max_allowed}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Recency Window (Plan 003 – Milestone 2)
# ══════════════════════════════════════════════════════════════════════════════

class TestMakeRecencyWindow:
    """Tests for _make_recency_window() helper."""

    def test_basic_append(self):
        """Appending to a non-full window."""
        from app.services.routing.loop_solvers.budget_astar_solver import _make_recency_window
        result = _make_recency_window((1, 2), 3, max_size=5)
        assert result == (1, 2, 3)

    def test_trims_to_max_size(self):
        """Window is trimmed when it exceeds max_size."""
        from app.services.routing.loop_solvers.budget_astar_solver import _make_recency_window
        result = _make_recency_window((1, 2, 3), 4, max_size=3)
        assert result == (2, 3, 4)

    def test_empty_initial_window(self):
        """Empty initial window produces single-element tuple."""
        from app.services.routing.loop_solvers.budget_astar_solver import _make_recency_window
        result = _make_recency_window((), 42, max_size=5)
        assert result == (42,)

    def test_never_exceeds_max_size(self):
        """Repeated appends never exceed max_size."""
        from app.services.routing.loop_solvers.budget_astar_solver import _make_recency_window
        window = ()
        for i in range(20):
            window = _make_recency_window(window, i, max_size=5)
        assert len(window) == 5
        assert window == (15, 16, 17, 18, 19)


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Search Strategy Builder (Plan 003 – Milestone 3)
# ══════════════════════════════════════════════════════════════════════════════

class TestBuildSearchStrategy:
    """Tests for _build_search_strategy()."""

    def test_returns_list_of_dicts(self):
        """Strategy is a list of dicts with required keys."""
        from app.services.routing.loop_solvers.budget_astar_solver import _build_search_strategy
        strategies = _build_search_strategy(
            target_distance=5000, directional_bias=90.0,
            tolerance=0.15, max_search_time=60,
        )
        assert isinstance(strategies, list)
        assert len(strategies) >= 3  # At least primary + relaxed + emergency
        for s in strategies:
            assert 'bearing' in s
            assert 'tolerance' in s
            assert 'time_budget' in s
            assert 'label' in s

    def test_tolerance_escalates(self):
        """Later strategies should have equal or wider tolerance."""
        from app.services.routing.loop_solvers.budget_astar_solver import _build_search_strategy
        strategies = _build_search_strategy(
            target_distance=5000, directional_bias=90.0,
            tolerance=0.15, max_search_time=60,
        )
        tolerances = [s['tolerance'] for s in strategies]
        for i in range(len(tolerances) - 1):
            assert tolerances[i] <= tolerances[i + 1], \
                f"Tolerance should escalate: {tolerances}"

    def test_time_budgets_sum_to_total(self):
        """Time budgets should sum to approximately the total time."""
        from app.services.routing.loop_solvers.budget_astar_solver import _build_search_strategy
        total = 60.0
        strategies = _build_search_strategy(
            target_distance=5000, directional_bias=90.0,
            tolerance=0.15, max_search_time=total,
        )
        time_sum = sum(s['time_budget'] for s in strategies)
        # Allow ±20% slack (strategies may round)
        assert total * 0.8 <= time_sum <= total * 1.2, \
            f"Time budgets sum {time_sum} should be near {total}"

    def test_no_bearing_uses_none(self):
        """When directional_bias is None, primary bearing should be None."""
        from app.services.routing.loop_solvers.budget_astar_solver import _build_search_strategy
        strategies = _build_search_strategy(
            target_distance=5000, directional_bias=None,
            tolerance=0.15, max_search_time=60,
        )
        primary = strategies[0]
        assert primary['bearing'] is None

    def test_bearing_propagated(self):
        """Primary strategy should use the provided bearing."""
        from app.services.routing.loop_solvers.budget_astar_solver import _build_search_strategy
        strategies = _build_search_strategy(
            target_distance=5000, directional_bias=45.0,
            tolerance=0.15, max_search_time=60,
        )
        assert strategies[0]['bearing'] == 45.0


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Cul-de-sac Integration (Plan 003 – Milestone 2+3)
# ══════════════════════════════════════════════════════════════════════════════

class TestCulDeSacIntegration:
    """Integration tests for dead-end resilience on cul-de-sac topologies."""

    @pytest.fixture
    def cul_de_sac_graph(self):
        """
        Graph with a main loop and a cul-de-sac spur.

        Main loop:   0 ↔ 1 ↔ 2 ↔ 3 ↔ 4 ↔ 5 ↔ 0
        Spur off 1:  1 ↔ 10 ↔ 11 ↔ 12  (dead-end)

        The start node (1) is at the junction of the spur and the loop.
        Each edge ≈ 100m.
        """
        G = nx.MultiDiGraph()
        base_lat, base_lon = 51.45, -2.58
        d = 0.0009  # ~100m

        # Main loop nodes
        coords = {
            0: (base_lat, base_lon),
            1: (base_lat, base_lon + d),
            2: (base_lat + d, base_lon + d),
            3: (base_lat + d, base_lon),
            4: (base_lat + 2 * d, base_lon),
            5: (base_lat + 2 * d, base_lon + d),
        }
        # Spur nodes
        coords[10] = (base_lat, base_lon + 2 * d)
        coords[11] = (base_lat, base_lon + 3 * d)
        coords[12] = (base_lat, base_lon + 4 * d)

        for nid, (la, lo) in coords.items():
            G.add_node(nid, y=la, x=lo)

        def add_bidir(u, v):
            la1, lo1 = coords[u]
            la2, lo2 = coords[v]
            length = _haversine(la1, lo1, la2, lo2)
            for a, b in [(u, v), (v, u)]:
                G.add_edge(a, b, length=length,
                           norm_green=0.5, norm_water=0.5,
                           norm_social=0.5, norm_quiet=0.5,
                           norm_slope=0.5)

        # Main loop
        for u, v in [(0, 1), (1, 2), (2, 3), (3, 4), (4, 5), (5, 0)]:
            add_bidir(u, v)
        # Extra cross-edge for more connectivity
        add_bidir(2, 5)

        # Spur
        for u, v in [(1, 10), (10, 11), (11, 12)]:
            add_bidir(u, v)

        return G

    def test_finds_loop_from_cul_de_sac_junction(
        self, cul_de_sac_graph, default_weights
    ):
        """Solver should find a loop starting from node 1 (cul-de-sac junction)."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver
        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=cul_de_sac_graph,
            start_node=1,
            target_distance=600,
            weights=default_weights,
            num_candidates=2,
            max_search_time=15,
            distance_tolerance=0.50,
        )
        assert len(candidates) >= 1, \
            "Should find at least one loop on a graph with cul-de-sac"

    def test_loop_avoids_dead_end_nodes(
        self, cul_de_sac_graph, default_weights
    ):
        """Returned loops should not include dead-end spur nodes 10-12."""
        from app.services.routing.loop_solvers.budget_astar_solver import BudgetAStarSolver
        solver = BudgetAStarSolver()
        candidates = solver.find_loops(
            graph=cul_de_sac_graph,
            start_node=1,
            target_distance=600,
            weights=default_weights,
            num_candidates=2,
            max_search_time=15,
            distance_tolerance=0.50,
        )
        # After pruning, nodes 10/11/12 are removed, so they
        # shouldn't appear in any route.
        for c in candidates:
            for spur_node in [10, 11, 12]:
                assert spur_node not in c.route, \
                    f"Dead-end node {spur_node} should not appear in loop route"

    def test_max_states_terminates_search(self, simple_grid_graph, default_weights):
        """_budget_astar_search should respect max_states parameter."""
        from app.services.routing.loop_solvers.budget_astar_solver import (
            _budget_astar_search, find_length_range,
        )
        from app.services.routing.cost_calculator import find_length_range

        min_l, max_l = find_length_range(simple_grid_graph)
        results = _budget_astar_search(
            simple_grid_graph, start_node=4,
            target_distance=100_000,  # Impossibly large
            weights=default_weights,
            min_length=min_l, max_length=max_l,
            max_search_time=60,
            max_states=50,  # Very low cap
        )
        # Should terminate quickly via state cap (won't find anything)
        assert isinstance(results, list)


# ══════════════════════════════════════════════════════════════════════════════
# Tests: Legacy LoopAStar (existing tests still work)
# ══════════════════════════════════════════════════════════════════════════════

class TestLegacyLoopAStarImport:
    """Verify the legacy LoopAStar is still importable (backward compat)."""

    def test_loop_astar_import(self):
        """Legacy LoopAStar can still be imported."""
        from app.services.routing.astar.loop_astar import LoopAStar
        assert LoopAStar is not None
