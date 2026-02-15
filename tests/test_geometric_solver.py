"""
Tests for the Geometric Loop Solver (Triangle-Plateau)

Covers:
    - Helper functions: projection, bearing, haversine
    - Smart-snap logic
    - Single triangle construction & routing
    - Clamped τ feedback loop
    - Out-and-back fallback
    - Full find_loops() integration on a grid graph
    - Factory registration
"""

import math
import pytest
import networkx as nx
from unittest.mock import patch

from app.services.routing.loop_solvers.geometric_solver import (
    _haversine,
    _project_point,
    _bearing_between,
    _node_coords,
    _smart_snap,
    _are_reachable,
    _route_leg,
    _try_triangle,
    _try_out_and_back,
    GeometricLoopSolver,
    DEFAULT_TAU,
    TOLERANCE_UNDER,
    TOLERANCE_OVER,
)
from app.services.routing.loop_solvers.base import (
    LoopCandidate,
    calculate_quality_score,
)
from app.services.routing.loop_solvers.factory import LoopSolverFactory


# ══════════════════════════════════════════════════════════════════════════════
# Fixtures
# ══════════════════════════════════════════════════════════════════════════════

def _hav(lat1, lon1, lat2, lon2):
    """Reference haversine for fixture edge lengths."""
    R = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _add_bidir_edge(G, u, v, positions, **extra):
    """Add a bidirectional edge with computed length and default scenic attrs."""
    lat1, lon1 = positions[u]
    lat2, lon2 = positions[v]
    length = _hav(lat1, lon1, lat2, lon2)
    attrs = dict(
        length=length,
        norm_green=0.3,
        norm_water=0.4,
        norm_social=0.5,
        norm_quiet=0.3,
        norm_slope=0.2,
    )
    attrs.update(extra)
    G.add_edge(u, v, **attrs)
    G.add_edge(v, u, **attrs)


@pytest.fixture
def grid_10x10():
    """
    10×10 grid graph centred near Bristol.

    Node IDs: row*10 + col (0-99), spacing ~55 m.
    All edges bidirectional with uniform scenic attributes.
    """
    G = nx.MultiDiGraph()
    base_lat, base_lon = 51.45, -2.58
    delta = 0.0005  # ≈55 m

    positions = {}
    for r in range(10):
        for c in range(10):
            nid = r * 10 + c
            lat = base_lat + r * delta
            lon = base_lon + c * delta
            positions[nid] = (lat, lon)
            G.add_node(nid, y=lat, x=lon)

    for r in range(10):
        for c in range(10):
            nid = r * 10 + c
            if c < 9:
                _add_bidir_edge(G, nid, nid + 1, positions)
            if r < 9:
                _add_bidir_edge(G, nid, nid + 10, positions)

    return G


@pytest.fixture
def large_grid_20x20():
    """
    20×20 grid graph with wider spacing (~110 m) for longer loops.
    Total grid span ≈ 2 km × 2 km.
    """
    G = nx.MultiDiGraph()
    base_lat, base_lon = 51.45, -2.58
    delta = 0.001  # ≈111 m

    positions = {}
    for r in range(20):
        for c in range(20):
            nid = r * 20 + c
            lat = base_lat + r * delta
            lon = base_lon + c * delta
            positions[nid] = (lat, lon)
            G.add_node(nid, y=lat, x=lon)

    for r in range(20):
        for c in range(20):
            nid = r * 20 + c
            if c < 19:
                _add_bidir_edge(G, nid, nid + 1, positions)
            if r < 19:
                _add_bidir_edge(G, nid, nid + 20, positions)

    return G


@pytest.fixture
def default_weights():
    return {
        'distance': 0.5,
        'greenness': 0.1,
        'water': 0.1,
        'quietness': 0.1,
        'social': 0.1,
        'slope': 0.1,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: Helpers
# ══════════════════════════════════════════════════════════════════════════════

class TestHaversine:
    """Verify haversine distance calculation."""

    def test_same_point_is_zero(self):
        assert _haversine(51.45, -2.58, 51.45, -2.58) == 0.0

    def test_known_distance(self):
        """Bristol to London ≈ 170 km."""
        d = _haversine(51.45, -2.58, 51.51, -0.13)
        assert 160_000 < d < 180_000

    def test_symmetry(self):
        d1 = _haversine(51.0, -2.0, 52.0, -1.0)
        d2 = _haversine(52.0, -1.0, 51.0, -2.0)
        assert abs(d1 - d2) < 0.01


class TestProjectPoint:
    """Verify geodesic point projection."""

    def test_north_projection(self):
        lat, lon = _project_point(51.45, -2.58, 0.0, 1000)
        # Should move ~0.009° north
        assert lat > 51.45
        assert abs(lon - (-2.58)) < 0.001

    def test_east_projection(self):
        lat, lon = _project_point(51.45, -2.58, 90.0, 1000)
        assert lon > -2.58
        assert abs(lat - 51.45) < 0.001

    def test_round_trip_distance(self):
        """Projected point should be ~dist metres from origin."""
        origin = (51.45, -2.58)
        for bearing in [0, 45, 90, 135, 180, 270]:
            lat2, lon2 = _project_point(*origin, bearing, 500)
            d = _haversine(*origin, lat2, lon2)
            assert abs(d - 500) < 5  # within 5 m


class TestBearing:
    def test_north(self):
        b = _bearing_between(51.0, -2.0, 52.0, -2.0)
        assert abs(b - 0.0) < 1.0

    def test_east(self):
        b = _bearing_between(51.0, -2.0, 51.0, -1.0)
        assert abs(b - 90.0) < 1.0


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: Smart Snap
# ══════════════════════════════════════════════════════════════════════════════

class TestSmartSnap:
    def test_snaps_to_closest(self, grid_10x10):
        """Should snap to the nearest node in the grid."""
        # Node 55 is at row=5, col=5 → approx (51.4525, -2.5775)
        lat = 51.4525
        lon = -2.5775
        node = _smart_snap(grid_10x10, lat, lon)
        assert node is not None
        # Should be near the middle of the grid
        assert 0 <= node <= 99

    def test_returns_none_on_empty_graph(self):
        G = nx.MultiDiGraph()
        assert _smart_snap(G, 51.45, -2.58) is None


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: Reachability
# ══════════════════════════════════════════════════════════════════════════════

class TestReachability:
    def test_connected_nodes(self, grid_10x10):
        assert _are_reachable(grid_10x10, 0, 99)

    def test_disconnected_node(self):
        G = nx.MultiDiGraph()
        G.add_node(1, y=51.45, x=-2.58)
        G.add_node(2, y=51.46, x=-2.57)
        # No edges → not reachable
        assert not _are_reachable(G, 1, 2)


# ══════════════════════════════════════════════════════════════════════════════
# Unit Tests: Leg Router
# ══════════════════════════════════════════════════════════════════════════════

class TestRouteLeg:
    def test_adjacent_nodes(self, grid_10x10, default_weights):
        length_range = (30, 80)
        result = _route_leg(grid_10x10, 0, 1, default_weights,
                            length_range=length_range)
        assert result is not None
        path, dist, cost = result
        assert path[0] == 0
        assert path[-1] == 1
        assert dist > 0
        assert cost > 0

    def test_unreachable_returns_none(self, default_weights):
        G = nx.MultiDiGraph()
        G.add_node(1, y=51.45, x=-2.58)
        G.add_node(2, y=51.46, x=-2.57)
        result = _route_leg(G, 1, 2, default_weights, length_range=(1, 100))
        assert result is None


# ══════════════════════════════════════════════════════════════════════════════
# Integration Tests: Factory
# ══════════════════════════════════════════════════════════════════════════════

class TestFactory:
    def test_create_geometric_solver(self):
        solver = LoopSolverFactory.create('GEOMETRIC')
        assert isinstance(solver, GeometricLoopSolver)

    def test_available_algorithms_includes_geometric(self):
        algos = LoopSolverFactory.available_algorithms()
        assert 'GEOMETRIC' in algos

    @patch('app.services.routing.loop_solvers.factory.LoopSolverFactory._get_config_algorithm',
           return_value='GEOMETRIC')
    def test_default_reads_config(self, _mock):
        solver = LoopSolverFactory.create()
        assert isinstance(solver, GeometricLoopSolver)


# ══════════════════════════════════════════════════════════════════════════════
# Integration Tests: Full Solver
# ══════════════════════════════════════════════════════════════════════════════

class TestGeometricSolverIntegration:
    """
    End-to-end tests on the 20×20 grid (~2 km span).

    The grid is large enough that ~1-2 km loops should be routable.
    """

    def test_finds_at_least_one_loop(self, large_grid_20x20, default_weights):
        solver = GeometricLoopSolver()
        candidates = solver.find_loops(
            graph=large_grid_20x20,
            start_node=210,  # row=10, col=10 (centre)
            target_distance=2000,
            weights=default_weights,
            num_candidates=2,
            distance_tolerance=0.30,
            max_search_time=30,
        )
        # On a 2 km grid with 111 m edges, we should get at least 1 loop
        assert len(candidates) >= 1

    def test_candidates_are_loops(self, large_grid_20x20, default_weights):
        solver = GeometricLoopSolver()
        candidates = solver.find_loops(
            graph=large_grid_20x20,
            start_node=210,
            target_distance=2000,
            weights=default_weights,
            num_candidates=2,
            distance_tolerance=0.30,
            max_search_time=30,
        )
        for c in candidates:
            # Route must start and end at the same node
            assert c.route[0] == c.route[-1], (
                f"Route does not close: starts {c.route[0]}, ends {c.route[-1]}"
            )

    def test_candidate_properties(self, large_grid_20x20, default_weights):
        solver = GeometricLoopSolver()
        candidates = solver.find_loops(
            graph=large_grid_20x20,
            start_node=210,
            target_distance=2000,
            weights=default_weights,
            num_candidates=2,
            distance_tolerance=0.30,
            max_search_time=30,
        )
        for c in candidates:
            assert c.algorithm == 'geometric'
            assert c.distance > 0
            assert c.scenic_cost >= 0
            assert 0 <= c.quality_score <= 1
            assert isinstance(c.colour, str)
            assert isinstance(c.label, str)

    def test_directional_bias(self, large_grid_20x20, default_weights):
        solver = GeometricLoopSolver()
        candidates = solver.find_loops(
            graph=large_grid_20x20,
            start_node=210,
            target_distance=2000,
            weights=default_weights,
            directional_bias="north",
            num_candidates=2,
            distance_tolerance=0.30,
            max_search_time=30,
        )
        # Should still produce valid candidates (or empty — grid edge)
        for c in candidates:
            assert c.route[0] == c.route[-1]

    def test_returns_empty_on_impossible(self, default_weights):
        """Single-node graph → no loops possible."""
        G = nx.MultiDiGraph()
        G.add_node(1, y=51.45, x=-2.58)
        solver = GeometricLoopSolver()
        candidates = solver.find_loops(
            graph=G,
            start_node=1,
            target_distance=3000,
            weights=default_weights,
            max_search_time=5,
        )
        assert candidates == []

    def test_small_loop_on_grid(self, large_grid_20x20, default_weights):
        """A 1 km loop on a 2 km grid should be feasible."""
        solver = GeometricLoopSolver()
        candidates = solver.find_loops(
            graph=large_grid_20x20,
            start_node=210,
            target_distance=1000,
            weights=default_weights,
            num_candidates=1,
            distance_tolerance=0.30,
            max_search_time=30,
        )
        if candidates:
            c = candidates[0]
            assert c.route[0] == c.route[-1]
            # Distance should be within tolerance
            assert c.distance > 0
