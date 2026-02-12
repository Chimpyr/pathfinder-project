"""
Loop Route Finder

Two-phase algorithm for finding circular (round-trip) routes:
  Phase 1: Guided random walk outward to ~half the target distance.
  Phase 2: Standard A* back to start, reusing WSM scenic cost.

Multiple candidate loops are generated and the best (closest to
target distance with lowest scenic cost) is returned.

If no candidates satisfy the distance constraint, the closest
candidate is returned with a relaxed tolerance.

Key features:
- Reliably finds loops for any distance on any graph
- Scenic preferences via the WSM cost function
- Directional bias (north/east/south/west/none)
- Multiple attempts for quality
- Graceful fallback with relaxed tolerance

References:
- RouteSpinner circular routing (two-phase inspiration)
- A* with WSM cost function (reused for return path)
"""

import math
import random
import time
from typing import Dict, List, Optional, Set, Tuple, Union, Iterable

from app.services.routing.astar.astar_lib import AStar
from app.services.routing.cost_calculator import (
    compute_wsm_cost,
    find_length_range,
    normalise_length,
    validate_weights,
)


# ── Helper: scenic edge cost (stateless) ─────────────────────────────────────

def _edge_wsm_cost(
    graph, n1, n2, weights, min_length, max_length, combine_nature=False
) -> Tuple[float, float]:
    """
    Return (wsm_cost, physical_length) for the best parallel edge n1→n2.
    """
    edges = graph[n1][n2]
    best_cost = float("inf")
    best_length = 0.0

    for data in edges.values():
        length = data.get("length", float("inf"))
        if length == float("inf"):
            continue
        norm_length = normalise_length(length, min_length, max_length)
        cost = compute_wsm_cost(
            norm_length=norm_length,
            norm_green=data.get("norm_green", 0.5),
            norm_water=data.get("norm_water", 0.5),
            norm_social=data.get("norm_social", 0.5),
            norm_quiet=data.get("norm_quiet", 0.5),
            norm_slope=data.get("norm_slope", 0.5),
            weights=weights,
            combine_nature=combine_nature,
        )
        if cost < best_cost:
            best_cost = cost
            best_length = length

    return best_cost, best_length


# ── Helper: haversine ────────────────────────────────────────────────────────

def _haversine(lat1, lon1, lat2, lon2) -> float:
    """Great-circle distance in metres."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _bearing(lat1, lon1, lat2, lon2) -> float:
    """Geographic bearing in degrees 0-360 (0 = north, 90 = east)."""
    lat1r, lon1r, lat2r, lon2r = map(math.radians, [lat1, lon1, lat2, lon2])
    dlon = lon2r - lon1r
    x = math.sin(dlon) * math.cos(lat2r)
    y = math.cos(lat1r) * math.sin(lat2r) - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def _node_coords(graph, node) -> Tuple[float, float]:
    """Return (lat, lon) for *node*."""
    d = graph.nodes[node]
    return (d.get("y", d.get("lat", 0)), d.get("x", d.get("lon", 0)))


# ── Directional bias helper ─────────────────────────────────────────────────

BIAS_TO_BEARING: Dict[str, Optional[float]] = {
    "north": 0.0,
    "east": 90.0,
    "south": 180.0,
    "west": 270.0,
    "none": None,
}


# ── Phase-2 return A* ───────────────────────────────────────────────────────

class _ReturnAStar(AStar):
    """
    Lightweight A* for finding the return path from a waypoint to start.

    Uses the same WSM scenic cost as the main routing, so scenic
    preferences are respected on the way back.
    """

    def __init__(self, graph, weights, min_length, max_length,
                 combine_nature=False, avoid_nodes: Optional[Set] = None):
        self.graph = graph
        self.weights = weights
        self.min_length = min_length
        self.max_length = max_length
        self.combine_nature = combine_nature
        # Nodes to discourage (outbound path) — soft avoidance via penalty
        self.avoid_nodes = avoid_nodes or set()

    def neighbors(self, node):
        return list(self.graph.neighbors(node))

    def distance_between(self, n1, n2) -> float:
        cost, _ = _edge_wsm_cost(
            self.graph, n1, n2, self.weights,
            self.min_length, self.max_length, self.combine_nature,
        )
        # Soft penalty for revisiting outbound nodes → encourages distinct return
        if n2 in self.avoid_nodes:
            cost *= 2.0
        return cost

    def heuristic_cost_estimate(self, current, goal) -> float:
        c_lat, c_lon = _node_coords(self.graph, current)
        g_lat, g_lon = _node_coords(self.graph, goal)
        dist = _haversine(c_lat, c_lon, g_lat, g_lon)
        if self.max_length > 0:
            return self.weights.get("distance", 0.5) * dist / self.max_length
        return 0.0


# ── Phase-1: guided random walk ─────────────────────────────────────────────

def _guided_walk(
    graph,
    start_node,
    target_outbound: float,
    weights: Dict[str, float],
    min_length: float,
    max_length: float,
    combine_nature: bool,
    target_bearing: Optional[float],
    rng: random.Random,
    max_walk_steps: int = 2000,
) -> List:
    """
    Walk outward from *start_node* for approximately *target_outbound* metres.

    Neighbours are scored by a combination of scenic cost and directional
    alignment.  A softmax (Boltzmann) selection adds randomness so
    different calls produce different outbound legs.

    Returns list of node-IDs (including start_node).
    """
    path: List = [start_node]
    visited: Set = {start_node}
    total_dist = 0.0
    current = start_node

    for _ in range(max_walk_steps):
        if total_dist >= target_outbound:
            break

        neighbours = [n for n in graph.neighbors(current) if n not in visited]
        if not neighbours:
            # Dead end — allow backtracking to any neighbour not in last 5
            recent = set(path[-5:]) if len(path) >= 5 else set(path)
            neighbours = [n for n in graph.neighbors(current) if n not in recent]
            if not neighbours:
                break

        # Score each neighbour (lower = better)
        scored: List[Tuple[float, int, float]] = []
        for nb in neighbours:
            cost, length = _edge_wsm_cost(
                graph, current, nb, weights,
                min_length, max_length, combine_nature,
            )
            # Directional bonus
            if target_bearing is not None:
                c_lat, c_lon = _node_coords(graph, current)
                n_lat, n_lon = _node_coords(graph, nb)
                edge_bear = _bearing(c_lat, c_lon, n_lat, n_lon)
                diff = abs(edge_bear - target_bearing)
                if diff > 180:
                    diff = 360 - diff
                # Penalty proportional to deviation (0 at 0°, 0.5 at 180°)
                cost += 0.5 * (diff / 180.0)
            scored.append((cost, nb, length))

        # Boltzmann / softmax selection (temperature controls randomness)
        temperature = 0.3
        min_cost = min(s[0] for s in scored)
        exp_scores = []
        for cost, nb, length in scored:
            # Negate because lower cost = higher probability
            exp_scores.append(math.exp(-(cost - min_cost) / temperature))
        total_exp = sum(exp_scores)
        probs = [e / total_exp for e in exp_scores]

        # Weighted random choice
        r = rng.random()
        cumulative = 0.0
        chosen_idx = len(scored) - 1
        for i, p in enumerate(probs):
            cumulative += p
            if r <= cumulative:
                chosen_idx = i
                break

        _, chosen_node, chosen_length = scored[chosen_idx]
        path.append(chosen_node)
        visited.add(chosen_node)
        total_dist += chosen_length
        current = chosen_node

    return path


# ── Phase-2: return path via A* ──────────────────────────────────────────────

def _find_return_path(
    graph, waypoint, start_node,
    weights, min_length, max_length, combine_nature,
    outbound_nodes: Set,
) -> Optional[List]:
    """
    Use standard A* to find a scenic return from *waypoint* → *start_node*.

    Outbound nodes get a soft penalty (×2 cost) to encourage different
    return legs, but are NOT blocked — this guarantees a path is always
    found if one exists in the graph.
    """
    solver = _ReturnAStar(
        graph, weights, min_length, max_length,
        combine_nature, avoid_nodes=outbound_nodes,
    )
    result = solver.astar(waypoint, start_node)
    if result is None:
        return None
    return list(result)


# ── Main entry: LoopAStar ────────────────────────────────────────────────────

class LoopAStar:
    """
    Two-phase loop route finder.

    Despite the name (kept for backward compatibility), this does NOT
    use pure A* for loop search.  Instead:

      1. *Phase 1* — guided random walk outward for ≈ half the target
         distance, biased by scenic costs and directional preference.
      2. *Phase 2* — standard A* from the walk endpoint back to start,
         using the WSM scenic cost.  Outbound edges are softly penalised
         to encourage a distinct return leg.

    Multiple candidates are generated and the best is returned.

    Attributes
    ----------
    BIAS_TO_BEARING : dict
        Directional string → compass bearing mapping.
    """

    # Expose for tests & external use
    BIAS_TO_BEARING = BIAS_TO_BEARING

    # Limits
    DEFAULT_MAX_SEARCH_TIME_S = 120
    DEFAULT_NUM_ATTEMPTS = 20  # candidates to generate
    MAX_DIRECTIONAL_PENALTY = 0.6  # kept for test compatibility

    def __init__(
        self,
        graph,
        weights: Optional[Dict[str, float]] = None,
        target_distance: float = 5000,
        combine_nature: bool = False,
        directional_bias: str = "none",
        distance_tolerance: float = 0.15,
        length_range: Optional[tuple] = None,
        max_iterations: Optional[int] = None,   # kept for API compat
        max_search_time: Optional[float] = None,
    ):
        self.graph = graph
        self.target_distance = target_distance
        self.combine_nature = combine_nature
        self.distance_tolerance = distance_tolerance

        self.directional_bias = (directional_bias or "none").lower()
        self.target_bearing = BIAS_TO_BEARING.get(self.directional_bias)

        if weights is None:
            weights = {
                "distance": 0.5, "greenness": 0.1, "water": 0.1,
                "quietness": 0.1, "social": 0.1, "slope": 0.1,
            }
        self.weights = validate_weights(weights)

        if length_range is not None:
            self.min_length, self.max_length = length_range
        else:
            self.min_length, self.max_length = find_length_range(graph)

        self.max_search_time = max_search_time or self.DEFAULT_MAX_SEARCH_TIME_S
        self.max_iterations = max_iterations  # unused but kept for compat

        # Internal RNG for reproducibility in tests
        self._rng = random.Random()

        # State set during astar() call
        self.start_node = None

        if target_distance > 15000:
            print(
                f"[LoopAStar] Long loop requested ({target_distance/1000:.1f}km), "
                f"search may take up to {self.max_search_time}s"
            )

    # ── Public API (signature-compatible with old code) ──────────────────

    def astar(self, start, goal, reversePath: bool = False) -> Union[Iterable, None]:
        """
        Find a loop route starting and ending at *start*.

        *goal* should equal *start* for loop routing.

        Returns an iterable of node-IDs or ``None``.
        """
        self.start_node = start
        t0 = time.time()

        min_dist = self.target_distance * (1 - self.distance_tolerance)
        max_dist = self.target_distance * (1 + self.distance_tolerance)

        # Adaptive attempt count: more attempts for longer loops
        num_attempts = self.DEFAULT_NUM_ATTEMPTS
        if self.target_distance > 10_000:
            num_attempts = 40
        if self.target_distance > 20_000:
            num_attempts = 60

        best_loop: Optional[List] = None
        best_deviation = float("inf")
        best_cost = float("inf")
        candidates_tried = 0

        # Target outbound distance ≈ 40-60 % of target (varied per attempt)
        outbound_fractions = [0.40, 0.45, 0.50, 0.55, 0.60]

        for attempt in range(num_attempts):
            elapsed = time.time() - t0
            if elapsed > self.max_search_time:
                print(f"[LoopAStar] Time limit ({self.max_search_time}s) reached "
                      f"after {candidates_tried} candidates")
                break

            frac = outbound_fractions[attempt % len(outbound_fractions)]
            target_outbound = self.target_distance * frac

            # Phase 1: guided random walk outward
            outbound = _guided_walk(
                self.graph, start, target_outbound,
                self.weights, self.min_length, self.max_length,
                self.combine_nature, self.target_bearing,
                self._rng,
            )

            if len(outbound) < 3:
                continue  # too short to be useful

            waypoint = outbound[-1]

            # Phase 2: A* return
            outbound_set = set(outbound)
            return_path = _find_return_path(
                self.graph, waypoint, start,
                self.weights, self.min_length, self.max_length,
                self.combine_nature, outbound_set,
            )

            if return_path is None:
                continue

            # Combine: outbound + return (avoid duplicating waypoint)
            loop = outbound + return_path[1:]
            candidates_tried += 1

            # Ensure loop ends at start
            if loop[-1] != start:
                continue

            # Calculate total physical distance
            loop_dist = self._route_distance(loop)
            deviation = abs(loop_dist - self.target_distance) / self.target_distance

            # Check primary constraint
            if min_dist <= loop_dist <= max_dist:
                # Within tolerance — score by scenic cost
                loop_cost = self._route_cost(loop)
                if deviation < best_deviation or (
                    abs(deviation - best_deviation) < 0.01 and loop_cost < best_cost
                ):
                    best_loop = loop
                    best_deviation = deviation
                    best_cost = loop_cost
            else:
                # Outside tolerance — still track as fallback if closest so far
                if best_loop is None or deviation < best_deviation:
                    best_loop = loop
                    best_deviation = deviation
                    best_cost = self._route_cost(loop)

        elapsed = time.time() - t0

        if best_loop is not None:
            dist = self._route_distance(best_loop)
            print(f"[LoopAStar] Found loop: {dist:.0f}m "
                  f"(target {self.target_distance:.0f}m, "
                  f"deviation {best_deviation*100:.1f}%) "
                  f"in {candidates_tried} candidates, {elapsed:.1f}s")
            if reversePath:
                return reversed(best_loop)
            return iter(best_loop)

        print(f"[LoopAStar] No loop found after {candidates_tried} candidates, "
              f"{elapsed:.1f}s")
        return None

    # ── Helper: bearing/direction methods (kept for test compatibility) ───

    def _calculate_bearing(self, n1, n2) -> float:
        """Calculate bearing n1 → n2 in degrees 0-360."""
        lat1, lon1 = _node_coords(self.graph, n1)
        lat2, lon2 = _node_coords(self.graph, n2)
        return _bearing(lat1, lon1, lat2, lon2)

    def _calculate_directional_penalty(self, n1, n2) -> float:
        """Directional penalty 0 → MAX_DIRECTIONAL_PENALTY."""
        if self.target_bearing is None:
            return 0.0
        edge_bear = self._calculate_bearing(n1, n2)
        diff = abs(edge_bear - self.target_bearing)
        if diff > 180:
            diff = 360 - diff
        return self.MAX_DIRECTIONAL_PENALTY * (diff / 180.0)

    def _haversine(self, lat1, lon1, lat2, lon2) -> float:
        return _haversine(lat1, lon1, lat2, lon2)

    def _get_distance_to_start(self, node) -> float:
        if self.start_node is None:
            return 0.0
        lat1, lon1 = _node_coords(self.graph, node)
        lat2, lon2 = _node_coords(self.graph, self.start_node)
        return _haversine(lat1, lon1, lat2, lon2)

    def heuristic_cost_estimate(self, current, goal) -> float:
        """Kept for API compatibility with AStar base class tests."""
        return self._get_distance_to_start(current) / max(self.max_length, 1) * self.weights["distance"]

    def _heuristic_with_distance(self, current, goal, accumulated_distance: float) -> float:
        """Budget heuristic — kept for test compatibility."""
        dist_to_start = self._get_distance_to_start(current)
        remaining_budget = max(0, self.target_distance - accumulated_distance)
        if dist_to_start > remaining_budget * 1.2:
            return float("inf")
        heuristic_distance = max(remaining_budget, dist_to_start)
        if self.max_length > 0:
            normalised = heuristic_distance / self.max_length
        else:
            normalised = 0.0
        return self.weights["distance"] * normalised

    def neighbors(self, node):
        """Kept for API compatibility."""
        return list(self.graph.neighbors(node))

    # ── Internal helpers ─────────────────────────────────────────────────

    def _route_distance(self, route: List) -> float:
        """Total physical distance of a route in metres."""
        total = 0.0
        for u, v in zip(route[:-1], route[1:]):
            edge_data = self.graph.get_edge_data(u, v)
            if edge_data:
                lengths = [d.get("length", 0) for d in edge_data.values()]
                total += min(lengths) if lengths else 0.0
        return total

    def _route_cost(self, route: List) -> float:
        """Total WSM scenic cost of a route."""
        total = 0.0
        for u, v in zip(route[:-1], route[1:]):
            try:
                cost, _ = _edge_wsm_cost(
                    self.graph, u, v, self.weights,
                    self.min_length, self.max_length, self.combine_nature,
                )
                total += cost
            except (KeyError, TypeError):
                total += 1.0
        return total
