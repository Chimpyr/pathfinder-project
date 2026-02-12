"""
Budget-Constrained A* Loop Solver

Primary loop routing algorithm using state-augmented A* search.

Key Design:
    - State = (node_id, discretized_accumulated_distance)
    - Budget heuristic drives exploration outward then pulls back
    - Cycle prevention via visited-node tracking in path
    - Multiple candidates via varied directional biases and perturbations
    - Diversity selection for final output

This correctly implements the RouteSpinner budget heuristic that the
previous implementation only described in comments but never used.

See 002-loop-route-refactor.md §Algorithm 1 for full specification.
"""

import heapq
import math
import random
import time
from typing import Dict, List, Optional, Set, Tuple

from app.services.routing.cost_calculator import (
    compute_wsm_cost,
    find_length_range,
    normalise_length,
    validate_weights,
)
from app.services.routing.loop_solvers.base import (
    LoopCandidate,
    LoopSolverBase,
    calculate_quality_score,
    select_diverse_candidates,
)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _node_coords(graph, node) -> Tuple[float, float]:
    """Return (lat, lon) for a graph node."""
    d = graph.nodes[node]
    return (d.get('y', d.get('lat', 0)), d.get('x', d.get('lon', 0)))


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Geographic bearing in degrees 0-360 (0=north, 90=east)."""
    lat1r, lon1r = math.radians(lat1), math.radians(lon1)
    lat2r, lon2r = math.radians(lat2), math.radians(lon2)
    dlon = lon2r - lon1r
    x = math.sin(dlon) * math.cos(lat2r)
    y = (math.cos(lat1r) * math.sin(lat2r)
         - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


BIAS_TO_BEARING: Dict[str, Optional[float]] = {
    'north': 0.0,
    'east': 90.0,
    'south': 180.0,
    'west': 270.0,
    'none': None,
}


def _edge_wsm_cost(
    graph, n1, n2, weights, min_length, max_length, combine_nature=False
) -> Tuple[float, float]:
    """
    Return (wsm_cost, physical_length) for the best parallel edge n1→n2.
    """
    edges = graph[n1][n2]
    best_cost = float('inf')
    best_length = 0.0

    for data in edges.values():
        length = data.get('length', float('inf'))
        if length == float('inf'):
            continue
        norm_length = normalise_length(length, min_length, max_length)
        cost = compute_wsm_cost(
            norm_length=norm_length,
            norm_green=data.get('norm_green', 0.5),
            norm_water=data.get('norm_water', 0.5),
            norm_social=data.get('norm_social', 0.5),
            norm_quiet=data.get('norm_quiet', 0.5),
            norm_slope=data.get('norm_slope', 0.5),
            weights=weights,
            combine_nature=combine_nature,
        )
        if cost < best_cost:
            best_cost = cost
            best_length = length

    return best_cost, best_length


def _get_edge_length(graph, n1, n2) -> float:
    """Get minimum physical length of edges between n1 and n2."""
    edge_data = graph.get_edge_data(n1, n2)
    if not edge_data:
        return float('inf')
    lengths = [d.get('length', float('inf')) for d in edge_data.values()]
    return min(lengths) if lengths else float('inf')


def _route_distance(graph, route: List[int]) -> float:
    """Total physical distance of a route in metres."""
    total = 0.0
    for u, v in zip(route[:-1], route[1:]):
        total += _get_edge_length(graph, u, v)
    return total


def _route_cost(graph, route, weights, min_length, max_length, combine_nature) -> float:
    """Total WSM scenic cost of a route."""
    total = 0.0
    for u, v in zip(route[:-1], route[1:]):
        try:
            cost, _ = _edge_wsm_cost(
                graph, u, v, weights, min_length, max_length, combine_nature
            )
            total += cost
        except (KeyError, TypeError):
            total += 1.0
    return total


# ── Distance discretization ─────────────────────────────────────────────────

def _discretize_distance(distance: float, bin_size: float = 100.0) -> int:
    """
    Discretize accumulated distance into bins to limit state space.

    Using 100m bins: a 10km loop has ~100 distance bins per node,
    keeping state space manageable while maintaining reasonable precision.
    """
    return int(distance // bin_size)


# ── Budget A* core search ────────────────────────────────────────────────────

def _budget_astar_search(
    graph,
    start_node: int,
    target_distance: float,
    weights: Dict[str, float],
    min_length: float,
    max_length: float,
    combine_nature: bool = False,
    target_bearing: Optional[float] = None,
    distance_tolerance: float = 0.15,
    max_search_time: float = 60,
    distance_bin_size: float = 100.0,
    max_candidates: int = 10,
) -> List[Tuple[List[int], float, float]]:
    """
    Budget-constrained A* search for loop routes.

    State = (node_id, discretized_distance).
    Returns list of (route, distance, scenic_cost) tuples.

    Args:
        graph: NetworkX MultiDiGraph.
        start_node: Loop start/end node.
        target_distance: Target loop distance in metres.
        weights: WSM weight dict.
        min_length, max_length: Edge length range for normalisation.
        combine_nature: Combine greenness+water.
        target_bearing: Directional bias bearing (degrees) or None.
        distance_tolerance: Acceptable deviation fraction.
        max_search_time: Time limit in seconds.
        distance_bin_size: Distance discretization bin size in metres.
        max_candidates: Maximum candidates to collect before stopping.

    Returns:
        List of (route, distance, scenic_cost) tuples.
    """
    t0 = time.time()

    min_dist = target_distance * (1 - distance_tolerance)
    max_dist = target_distance * (1 + distance_tolerance)

    # Pre-compute start node coordinates
    start_lat, start_lon = _node_coords(graph, start_node)

    # State: (node_id, distance_bin)
    initial_state = (start_node, 0)

    # Priority queue: (f_score, counter, state, accumulated_distance, path_nodes_set)
    counter = 0
    open_set = []

    # g_score tracks WSM cost per state
    g_score = {initial_state: 0.0}
    # came_from tracks path reconstruction
    came_from = {}
    # actual accumulated distance per state
    actual_distance = {initial_state: 0.0}

    heapq.heappush(open_set, (0.0, counter, initial_state, 0.0, frozenset()))
    counter += 1

    found_loops = []
    states_explored = 0

    while open_set:
        # Time check
        if time.time() - t0 > max_search_time:
            break

        # Enough candidates found
        if len(found_loops) >= max_candidates:
            break

        f, _, current_state, current_dist, path_nodes = heapq.heappop(open_set)
        current_node, current_dist_bin = current_state

        states_explored += 1

        # Periodic progress logging
        if states_explored % 10000 == 0:
            elapsed = time.time() - t0
            print(f"[BudgetA*] {states_explored} states explored, "
                  f"{len(found_loops)} candidates, {elapsed:.1f}s")

        # ── Goal check ───────────────────────────────────────────────────
        if (current_node == start_node
                and current_dist >= min_dist
                and current_dist <= max_dist
                and current_state in came_from):
            # Valid loop found! Reconstruct path.
            path = _reconstruct_path(came_from, current_state)
            if len(path) >= 3:  # Minimum viable loop
                cost = _route_cost(
                    graph, path, weights, min_length, max_length, combine_nature
                )
                found_loops.append((path, current_dist, cost))
                continue  # Don't expand further from goal state

        # ── Expand neighbours ────────────────────────────────────────────
        for neighbor_node in graph.neighbors(current_node):
            edge_length = _get_edge_length(graph, current_node, neighbor_node)
            if edge_length == float('inf'):
                continue

            new_dist = current_dist + edge_length

            # ── Pruning rules ────────────────────────────────────────────

            # 1. Exceeds max distance and not returning to start
            if new_dist > max_dist and neighbor_node != start_node:
                continue

            # 2. Can't return to start within budget
            n_lat, n_lon = _node_coords(graph, neighbor_node)
            dist_to_start = _haversine(n_lat, n_lon, start_lat, start_lon)
            remaining_budget = max_dist - new_dist
            if dist_to_start > remaining_budget * 1.5:
                # Can't possibly get back (with 50% slack for non-straight paths)
                continue

            # 3. Cycle prevention: don't revisit nodes in current path
            #    (except start_node when distance is sufficient)
            if neighbor_node in path_nodes and neighbor_node != start_node:
                continue
            if neighbor_node == start_node and new_dist < min_dist:
                # Too early to return to start
                continue

            # ── State creation ───────────────────────────────────────────
            new_dist_bin = _discretize_distance(new_dist, distance_bin_size)
            neighbor_state = (neighbor_node, new_dist_bin)

            # WSM cost for this edge
            wsm_cost, _ = _edge_wsm_cost(
                graph, current_node, neighbor_node,
                weights, min_length, max_length, combine_nature,
            )

            # Directional bonus/penalty
            if target_bearing is not None:
                c_lat, c_lon = _node_coords(graph, current_node)
                edge_bear = _bearing(c_lat, c_lon, n_lat, n_lon)
                diff = abs(edge_bear - target_bearing)
                if diff > 180:
                    diff = 360 - diff
                # Small penalty proportional to deviation from desired bearing
                # Only apply in outbound phase (first half of budget)
                if current_dist < target_distance * 0.5:
                    wsm_cost += 0.3 * (diff / 180.0)

            tentative_g = g_score.get(current_state, float('inf')) + wsm_cost

            # Only explore if this is a better path to this state
            if tentative_g >= g_score.get(neighbor_state, float('inf')):
                continue

            # ── Heuristic ────────────────────────────────────────────────
            h = _budget_heuristic(
                neighbor_node, new_dist, start_node, start_lat, start_lon,
                target_distance, max_dist, min_dist, max_length, weights, graph,
            )
            if h == float('inf'):
                continue  # Prune: impossible state

            f_new = tentative_g + h

            # Record state
            g_score[neighbor_state] = tentative_g
            came_from[neighbor_state] = current_state
            actual_distance[neighbor_state] = new_dist

            new_path_nodes = path_nodes | {current_node}

            heapq.heappush(open_set, (
                f_new, counter, neighbor_state, new_dist, new_path_nodes
            ))
            counter += 1

    elapsed = time.time() - t0
    print(f"[BudgetA*] Search complete: {states_explored} states, "
          f"{len(found_loops)} loops found, {elapsed:.1f}s")

    return found_loops


def _budget_heuristic(
    node, current_dist, start_node, start_lat, start_lon,
    target_dist, max_dist, min_dist, max_length, weights, graph,
) -> float:
    """
    Budget-based admissible heuristic for loop routing.

    Key insight (RouteSpinner): drives exploration AWAY from start when
    budget is large, pulls BACK toward start as budget shrinks.

    h(n) = max(0, target_dist - current_dist - dist_to_start)

    Returns infinity if the state is provably unreachable (can't return
    to start within remaining budget).
    """
    n_lat, n_lon = _node_coords(graph, node)
    dist_to_start = _haversine(n_lat, n_lon, start_lat, start_lon)
    remaining_budget = target_dist - current_dist

    # Pruning: can't return to start even in a straight line
    if dist_to_start > (max_dist - current_dist) * 1.2:
        return float('inf')

    # Budget heuristic: encourage using remaining budget
    heuristic_distance = max(0.0, remaining_budget - dist_to_start)

    # Normalise to WSM cost scale
    if max_length > 0:
        normalised = heuristic_distance / max_length
    else:
        normalised = 0.0

    return weights.get('distance', 0.5) * normalised


def _reconstruct_path(came_from, state) -> List[int]:
    """Reconstruct path from came_from dict, returning list of node IDs."""
    path = []
    current = state
    while current in came_from:
        node_id, _ = current
        path.append(node_id)
        current = came_from[current]
    # Add start node
    node_id, _ = current
    path.append(node_id)
    path.reverse()
    return path


# ── BudgetAStarSolver class ─────────────────────────────────────────────────

class BudgetAStarSolver(LoopSolverBase):
    """
    Budget-constrained A* loop solver.

    Uses state augmentation (node_id, discretized_distance) to correctly
    handle the loop routing problem where the same node may be visited
    at different accumulated distances.

    Generates multiple candidates through:
        1. Multiple runs with different directional biases
        2. Varied distance bin sizes for different granularity
        3. Diversity selection from the candidate pool

    This is the PRIMARY solver — set LOOP_SOLVER_ALGORITHM = 'BUDGET_ASTAR'.
    """

    def find_loops(
        self,
        graph,
        start_node: int,
        target_distance: float,
        weights: Dict[str, float],
        combine_nature: bool = False,
        directional_bias: str = "none",
        num_candidates: int = 3,
        distance_tolerance: float = 0.15,
        max_search_time: float = 120,
    ) -> List[LoopCandidate]:
        """
        Find multiple diverse loop candidates using Budget A* search.

        Strategy for generating multiple candidates:
            1. Run with user's directional bias (or no bias)
            2. Run with perpendicular biases for diversity
            3. Run with relaxed tolerance if needed
            4. Select top-K diverse candidates
        """
        t0 = time.time()

        weights = validate_weights(weights)
        min_length, max_length = find_length_range(graph)

        user_bearing = BIAS_TO_BEARING.get(directional_bias.lower(), None)

        # Determine bin size based on target distance
        # Shorter loops need finer granularity
        if target_distance <= 3000:
            bin_size = 50.0
        elif target_distance <= 10000:
            bin_size = 100.0
        else:
            bin_size = 200.0

        all_raw_loops = []

        # ── Run 1: User's preferred direction ────────────────────────────
        time_per_run = max(10, max_search_time / 4)

        run1_loops = _budget_astar_search(
            graph, start_node, target_distance, weights,
            min_length, max_length, combine_nature,
            target_bearing=user_bearing,
            distance_tolerance=distance_tolerance,
            max_search_time=time_per_run,
            distance_bin_size=bin_size,
            max_candidates=num_candidates * 2,
        )
        all_raw_loops.extend(run1_loops)

        # ── Run 2: Opposite direction for diversity ──────────────────────
        elapsed = time.time() - t0
        remaining_time = max_search_time - elapsed

        if remaining_time > 10 and len(all_raw_loops) < num_candidates * 2:
            opposite_bearing = None
            if user_bearing is not None:
                opposite_bearing = (user_bearing + 180) % 360
            else:
                # No user bias — try east
                opposite_bearing = 90.0

            run2_loops = _budget_astar_search(
                graph, start_node, target_distance, weights,
                min_length, max_length, combine_nature,
                target_bearing=opposite_bearing,
                distance_tolerance=distance_tolerance,
                max_search_time=min(time_per_run, remaining_time),
                distance_bin_size=bin_size,
                max_candidates=num_candidates,
            )
            all_raw_loops.extend(run2_loops)

        # ── Run 3: Perpendicular direction ───────────────────────────────
        elapsed = time.time() - t0
        remaining_time = max_search_time - elapsed

        if remaining_time > 10 and len(all_raw_loops) < num_candidates * 2:
            perp_bearing = None
            if user_bearing is not None:
                perp_bearing = (user_bearing + 90) % 360
            else:
                perp_bearing = 0.0  # North

            run3_loops = _budget_astar_search(
                graph, start_node, target_distance, weights,
                min_length, max_length, combine_nature,
                target_bearing=perp_bearing,
                distance_tolerance=distance_tolerance,
                max_search_time=min(time_per_run, remaining_time),
                distance_bin_size=bin_size,
                max_candidates=num_candidates,
            )
            all_raw_loops.extend(run3_loops)

        # ── Fallback: Relax tolerance if no results ──────────────────────
        elapsed = time.time() - t0
        remaining_time = max_search_time - elapsed

        if not all_raw_loops and remaining_time > 10:
            print(f"[BudgetA*] No loops found at ±{distance_tolerance*100:.0f}%, "
                  f"relaxing to ±40%")

            relaxed_loops = _budget_astar_search(
                graph, start_node, target_distance, weights,
                min_length, max_length, combine_nature,
                target_bearing=user_bearing,
                distance_tolerance=0.40,
                max_search_time=remaining_time,
                distance_bin_size=bin_size,
                max_candidates=num_candidates,
            )
            all_raw_loops.extend(relaxed_loops)

        # ── Convert to LoopCandidates ────────────────────────────────────
        if not all_raw_loops:
            print(f"[BudgetA*] No loops found for {target_distance/1000:.1f}km target")
            return []

        # Find max scenic cost for quality normalisation
        max_cost = max(cost for _, _, cost in all_raw_loops) if all_raw_loops else 1.0
        max_cost = max(max_cost, 0.001)  # Avoid division by zero

        candidates = []
        for route, distance, scenic_cost in all_raw_loops:
            deviation = abs(distance - target_distance) / target_distance
            quality = calculate_quality_score(
                deviation, scenic_cost, max_scenic_cost=max_cost
            )
            candidates.append(LoopCandidate(
                route=route,
                distance=distance,
                scenic_cost=scenic_cost,
                deviation=deviation,
                quality_score=quality,
                algorithm='budget_astar',
                metadata={
                    'directional_bias': directional_bias,
                    'target_distance': target_distance,
                    'distance_bin_size': bin_size,
                },
            ))

        # ── Select diverse candidates ────────────────────────────────────
        result = select_diverse_candidates(candidates, k=num_candidates)

        elapsed = time.time() - t0
        print(f"[BudgetA*] Returning {len(result)} candidates from "
              f"{len(all_raw_loops)} raw loops, {elapsed:.1f}s total")

        return result
