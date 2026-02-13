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


# ── Route analysis helpers ───────────────────────────────────────────────────

def _path_overlap_ratio(route: List[int]) -> float:
    """
    Fraction of path edges that retrace an already-walked street segment.

    An edge (u, v) is direction-agnostic: walking A→B then later B→A
    counts as overlap.  Values:
        0.0 = perfectly unique (no edge repeated)
        0.5 = half the route is out-and-back
        1.0 = entirely doubled-back
    """
    edge_set: Set[Tuple[int, int]] = set()
    duplicate_count = 0
    for u, v in zip(route[:-1], route[1:]):
        edge = (min(u, v), max(u, v))  # direction-agnostic
        if edge in edge_set:
            duplicate_count += 1
        else:
            edge_set.add(edge)
    total_edges = len(route) - 1
    return duplicate_count / total_edges if total_edges > 0 else 0.0


def _route_dominant_bearing(
    graph, route: List[int], start_node: int,
) -> Optional[float]:
    """
    Bearing from *start_node* to the point on *route* farthest from start.

    Returns None if the farthest point is closer than 10 m (degenerate).
    This captures the general direction the loop "bulges" toward.
    """
    start_lat, start_lon = _node_coords(graph, start_node)
    max_dist = 0.0
    farthest_lat, farthest_lon = start_lat, start_lon
    for node in route:
        lat, lon = _node_coords(graph, node)
        d = _haversine(lat, lon, start_lat, start_lon)
        if d > max_dist:
            max_dist = d
            farthest_lat, farthest_lon = lat, lon
    if max_dist < 10:
        return None
    return _bearing(start_lat, start_lon, farthest_lat, farthest_lon)


# ── Graph preprocessing ──────────────────────────────────────────────────────

def _prune_dead_ends(graph, start_node: int, max_iterations: int = 3):
    """
    Remove short topological dead-ends from a graph copy.

    Uses **batch** removal capped at *max_iterations* rounds.  Each round
    collects all current degree-1 nodes and removes them simultaneously,
    so one round = exactly one layer of dead-end depth.

    Why the cap matters:
        Tile-based OSM extracts sever roads at the tile boundary, creating
        hundreds of artificial degree-1 nodes at the edge.  Unlimited
        iterative pruning cascades inward from those severed ends,
        potentially removing 50%+ of the graph.  Capping at 3 iterations
        clips genuine cul-de-sac tips (typically 2-5 nodes deep) without
        cascading to tile boundaries.

    A **safety cap** of 5% of graph nodes provides an additional guard:
    if any single round would push total removals above this threshold,
    that round is skipped entirely.

    The *start_node* is always preserved.
    Returns a new graph; the original is never mutated.
    """
    pruned = graph.copy()
    total_removed = 0
    max_removable = max(graph.number_of_nodes() // 20, 50)  # 5% safety cap, min 50

    for iteration in range(max_iterations):
        # Batch-collect all current degree-1 nodes
        to_remove = []
        for node in pruned.nodes():
            if node == start_node:
                continue
            # In a MultiDiGraph, degree() counts in+out edges, so a
            # bidirectional dead-end street (A↔B) gives degree 2.
            # Instead, count unique neighbours (successors ∪ predecessors).
            unique_neighbours = set(pruned.successors(node)) | set(pruned.predecessors(node))
            if len(unique_neighbours) <= 1:
                to_remove.append(node)

        if not to_remove:
            break  # No dead-ends left

        # Safety cap: if this batch would exceed 5%, stop pruning
        if total_removed + len(to_remove) > max_removable:
            print(f"[BudgetA*] Pruning safety cap hit at iteration "
                  f"{iteration + 1} ({total_removed + len(to_remove)} "
                  f"> {max_removable} limit), stopping with "
                  f"{total_removed} removed")
            break

        for node in to_remove:
            pruned.remove_node(node)
        total_removed += len(to_remove)

    if total_removed:
        print(f"[BudgetA*] Pruned {total_removed} dead-end nodes "
              f"(over {min(iteration + 1, max_iterations)} iterations)")
    return pruned


# ── Recency-window helper ───────────────────────────────────────────────────

def _make_recency_window(
    current_window: Tuple, new_node: int, max_size: int
) -> Tuple:
    """
    Append *new_node* to the recency window and trim to *max_size*.

    The recency window is a lightweight tuple of the last N visited nodes,
    used to prevent trivial oscillation while still allowing backtracking
    out of dead-ends (nodes that fell off the window are revisitable).
    """
    return (current_window + (new_node,))[-max_size:]


# ── Search strategy builder ─────────────────────────────────────────────────

def _build_search_strategy(
    target_distance: float,
    directional_bias: Optional[float],
    tolerance: float = 0.15,
    max_search_time: float = 60,
) -> List[Dict]:
    """
    Build an ordered list of search-run configurations.

    The strategy escalates tolerance and drops directional constraints when
    earlier runs fail.  Each entry is a dict with keys:
        bearing, tolerance, time_budget, label

    Time budgets are split so their sum ≈ *max_search_time*.
    """
    strategies = []

    # ── Tier 1: primary direction, tight tolerance ───────────────────────
    strategies.append({
        'bearing': directional_bias,
        'tolerance': tolerance,
        'time_budget': max_search_time * 0.30,
        'label': 'primary',
    })

    # ── Tier 2: opposite direction (diversity) ───────────────────────────
    opposite = None
    if directional_bias is not None:
        opposite = (directional_bias + 180) % 360
    else:
        opposite = 90.0  # arbitrary diversity bearing
    strategies.append({
        'bearing': opposite,
        'tolerance': tolerance,
        'time_budget': max_search_time * 0.20,
        'label': 'diversity',
    })

    # ── Tier 3: perpendicular ────────────────────────────────────────────
    perp = None
    if directional_bias is not None:
        perp = (directional_bias + 90) % 360
    else:
        perp = 0.0  # north
    strategies.append({
        'bearing': perp,
        'tolerance': tolerance,
        'time_budget': max_search_time * 0.20,
        'label': 'perpendicular',
    })

    # ── Tier 4: relaxed tolerance, user bearing ──────────────────────────
    strategies.append({
        'bearing': directional_bias,
        'tolerance': 0.30,
        'time_budget': max_search_time * 0.20,
        'label': 'relaxed',
    })

    # ── Tier 5: emergency — wide tolerance, no directional constraint ────
    strategies.append({
        'bearing': None,
        'tolerance': 0.50,
        'time_budget': max_search_time * 0.10,
        'label': 'emergency',
    })

    return strategies


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
    max_states: int = 500_000,
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
        max_states: Maximum states to explore before termination.

    Returns:
        List of (route, distance, scenic_cost) tuples.
    """
    t0 = time.time()

    min_dist = target_distance * (1 - distance_tolerance)
    max_dist = target_distance * (1 + distance_tolerance)

    # Pre-compute start node coordinates
    start_lat, start_lon = _node_coords(graph, start_node)

    # Recency window size: scale with target distance.
    # Must be large enough to prevent local zigzag (revisiting nearby
    # nodes to accumulate distance without extending outward).
    # For 5km loop (~100 edges), window of 50 blocks the last ~50%.
    recency_window_size = max(30, int(target_distance // 100))

    # State: (node_id, distance_bin)
    initial_state = (start_node, 0)

    # Priority queue: (f_score, counter, state, accumulated_distance, recent_nodes)
    counter = 0
    open_set = []

    # g_score tracks WSM cost per state
    g_score = {initial_state: 0.0}
    # came_from tracks path reconstruction
    came_from = {}
    # actual accumulated distance per state
    actual_distance = {initial_state: 0.0}

    heapq.heappush(open_set, (0.0, counter, initial_state, 0.0, ()))
    counter += 1

    found_loops = []
    states_explored = 0

    # Track how many times each physical node is popped from the heap.
    # Nodes visited often are in well-explored territory; gently penalising
    # re-expansion encourages the return leg to use different streets.
    node_expansions: Dict[int, int] = {}

    while open_set:
        # Time check
        if time.time() - t0 > max_search_time:
            break

        # State cap
        if states_explored >= max_states:
            break

        # Enough candidates found
        if len(found_loops) >= max_candidates:
            break

        f, _, current_state, current_dist, recent_nodes = heapq.heappop(open_set)
        current_node, current_dist_bin = current_state

        states_explored += 1
        node_expansions[current_node] = node_expansions.get(current_node, 0) + 1

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

            # 3. Recency-window cycle prevention: only ban nodes visited
            #    within the last N steps (allows backtracking out of
            #    dead-ends while preventing A→B→A oscillation).
            if neighbor_node in recent_nodes and neighbor_node != start_node:
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

            # Current node coords (needed for bearing calculations)
            c_lat, c_lon = _node_coords(graph, current_node)

            # ── Exploration penalty: discourage retracing ────────────
            # Nodes already expanded many times are in well-trodden
            # territory.  A mild penalty steers the return leg toward
            # parallel streets instead of retracing the outbound path.
            prior_visits = node_expansions.get(neighbor_node, 0)
            if prior_visits > 0:
                wsm_cost += min(0.5, 0.12 * prior_visits)

            # ── Turn-angle penalty: discourage sharp U-turns ─────────
            # Natural walking/cycling routes rarely reverse direction.
            # Penalise edges that double back on the incoming bearing.
            if current_state in came_from:
                prev_node = came_from[current_state][0]
                p_lat, p_lon = _node_coords(graph, prev_node)
                incoming_bear = _bearing(p_lat, p_lon, c_lat, c_lon)
                outgoing_bear = _bearing(c_lat, c_lon, n_lat, n_lon)
                turn = abs(outgoing_bear - incoming_bear)
                if turn > 180:
                    turn = 360 - turn
                # turn ∈ [0, 180]; 0 = straight, 180 = U-turn
                if turn > 150:
                    wsm_cost += 0.8   # heavy penalty for U-turns
                elif turn > 120:
                    wsm_cost += 0.3   # moderate penalty for sharp turns

            # ── Directional bias (multiplicative) ────────────────────
            # Must be multiplicative so the penalty scales with scenic
            # cost: a scenic edge (cost 0.1) going the wrong way
            # becomes 0.1 * 3.0 = 0.3, which can now lose to a
            # non-scenic edge (cost 0.4) going the right way.
            if target_bearing is not None:
                edge_bear = _bearing(c_lat, c_lon, n_lat, n_lon)
                diff = abs(edge_bear - target_bearing)
                if diff > 180:
                    diff = 360 - diff
                # Applied during outbound phase (first 65% of budget)
                if current_dist < target_distance * 0.65:
                    direction_factor = 1.0 + 2.0 * (diff / 180.0)
                    wsm_cost *= direction_factor

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

            new_recent_nodes = _make_recency_window(
                recent_nodes, current_node, recency_window_size
            )

            heapq.heappush(open_set, (
                f_new, counter, neighbor_state, new_dist, new_recent_nodes
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

        Strategy (Plan 003 — adaptive escalation):
            1. Prune dead-end nodes from graph copy.
            2. Build a strategy list with escalating tolerance.
            3. Iterate runs; early-exit when enough candidates collected.
            4. If a run finds 0 results, skip remaining same-tolerance
               runs and escalate immediately.
            5. Select top-K diverse candidates.
        """
        t0 = time.time()

        weights = validate_weights(weights)
        min_length, max_length = find_length_range(graph)

        user_bearing = BIAS_TO_BEARING.get(directional_bias.lower(), None)

        # ── Dead-end pruning (Milestone 1) ───────────────────────────────
        pruned_graph = _prune_dead_ends(graph, start_node)

        # Determine bin size based on target distance
        if target_distance <= 3000:
            bin_size = 50.0
        elif target_distance <= 10000:
            bin_size = 100.0
        else:
            bin_size = 200.0

        # ── Build strategy list (Milestone 3) ────────────────────────────
        strategies = _build_search_strategy(
            target_distance, user_bearing, distance_tolerance, max_search_time,
        )

        all_raw_loops = []
        current_tolerance = None  # Track tolerance tier for escalation

        for strategy in strategies:
            elapsed = time.time() - t0
            remaining_time = max_search_time - elapsed

            # Global time guard
            if remaining_time < 5:
                break

            # Early-exit: require candidates from multiple strategy
            # tiers so directional diversity actually takes effect.
            if len(all_raw_loops) >= num_candidates * 4:
                break

            # ── Escalation: if the previous run at this tolerance found
            #    nothing and we've moved to the same tolerance tier,
            #    skip it (directional diversity is pointless if primary
            #    already exhausted the state space at this tolerance).
            if (current_tolerance is not None
                    and strategy['tolerance'] == current_tolerance
                    and len(all_raw_loops) == 0):
                print(f"[BudgetA*] Escalating past '{strategy['label']}' "
                      f"(same tolerance, 0 results)")
                continue

            time_budget = min(strategy['time_budget'], remaining_time)

            print(f"[BudgetA*] Run '{strategy['label']}': "
                  f"bearing={strategy['bearing']}, "
                  f"tolerance=±{strategy['tolerance']*100:.0f}%, "
                  f"time={time_budget:.0f}s")

            run_loops = _budget_astar_search(
                pruned_graph, start_node, target_distance, weights,
                min_length, max_length, combine_nature,
                target_bearing=strategy['bearing'],
                distance_tolerance=strategy['tolerance'],
                max_search_time=time_budget,
                distance_bin_size=bin_size,
                max_candidates=num_candidates,  # fewer per run → multiple directions explored
            )
            all_raw_loops.extend(run_loops)
            current_tolerance = strategy['tolerance']

        # ── Convert to LoopCandidates ────────────────────────────────────
        if not all_raw_loops:
            print(f"[BudgetA*] No loops found for "
                  f"{target_distance/1000:.1f}km target")
            return []

        max_cost = max(cost for _, _, cost in all_raw_loops) if all_raw_loops else 1.0
        max_cost = max(max_cost, 0.001)

        candidates = []
        for route, distance, scenic_cost in all_raw_loops:
            deviation = abs(distance - target_distance) / target_distance
            quality = calculate_quality_score(
                deviation, scenic_cost, max_scenic_cost=max_cost
            )

            # ── Penalise out-and-back routes ─────────────────────────
            overlap = _path_overlap_ratio(route)
            if overlap > 0.15:
                quality *= max(0.1, 1.0 - overlap)

            # ── Penalise routes that ignore the user's direction ─────
            if user_bearing is not None:
                route_bear = _route_dominant_bearing(
                    graph, route, start_node,
                )
                if route_bear is not None:
                    diff = abs(route_bear - user_bearing)
                    if diff > 180:
                        diff = 360 - diff
                    # 0° diff → ×1.0, 180° diff → ×0.3
                    direction_match = 1.0 - (diff / 180.0)
                    quality *= 0.3 + 0.7 * direction_match

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
                    'path_overlap': round(overlap, 3),
                },
            ))

        # ── Select diverse candidates ────────────────────────────────────
        result = select_diverse_candidates(candidates, k=num_candidates)

        elapsed = time.time() - t0
        print(f"[BudgetA*] Returning {len(result)} candidates from "
              f"{len(all_raw_loops)} raw loops, {elapsed:.1f}s total")

        return result
