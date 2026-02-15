"""
Geometric Loop Solver ("Triangle-Plateau")

Constructs round-trip routes by projecting a rigid geometric skeleton
(equilateral triangle) from the start node, snapping waypoints to real
graph nodes, then routing between vertices with WSM A*.

Key Design:
    - Equilateral-triangle skeleton sized via tortuosity factor τ
    - Diversity via equidistant rotation of the triangle bearing
    - "Critical Leg First" ordering: route the bridge leg (W1→W2) first
      and abort early if the route is excessively detoured
    - Clamped proportional feedback adjusts τ when distance is off-target
    - Out-and-back fallback when all triangle attempts fail

See docs/local/loop_solver_algorithms/geometric_loop_solver_design.md for
the full specification.
"""

import math
import time
from typing import Dict, List, Optional, Tuple

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


# ── Constants ────────────────────────────────────────────────────────────────

_EARTH_R = 6_371_000  # metres

# Default tortuosity: real walking paths are ~25 % longer than air distance
DEFAULT_TAU = 1.25

# Max feedback iterations before giving up on a single triangle candidate
MAX_FEEDBACK_RETRIES = 5

# Clamp bounds for τ update (± 15 % per iteration)
TAU_CLAMP_LOW = 0.85
TAU_CLAMP_HIGH = 1.15

# Asymmetric tolerance: runners prefer slightly long over short
TOLERANCE_UNDER = 0.05   # -5 %
TOLERANCE_OVER  = 0.15   # +15 %

# Bridge-leg abort threshold: if routed distance > 1.5× air distance
# Bridge-leg abort threshold: if routed distance > 3.0× air distance
# Relaxed from 1.5 to 3.0 to allow for scenic detours (e.g. parks, river crossings)
BRIDGE_LEG_DETOUR_FACTOR = 3.0

# Number of nearest graph nodes to consider when snapping a waypoint
SNAP_K = 10

# Highway tags considered "highway-only" (undesirable for waypoints)
_HIGHWAY_ONLY_TAGS = frozenset({
    'motorway', 'motorway_link', 'trunk', 'trunk_link',
    'primary', 'primary_link',
})


# ── Helpers ──────────────────────────────────────────────────────────────────

def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres between two (lat, lon) points."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (math.sin(dphi / 2) ** 2
         + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2)
    return _EARTH_R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _node_coords(graph, node) -> Tuple[float, float]:
    """Return (lat, lon) for a graph node."""
    d = graph.nodes[node]
    return (d.get('y', d.get('lat', 0.0)),
            d.get('x', d.get('lon', 0.0)))


def _project_point(lat: float, lon: float, bearing_deg: float,
                    distance_m: float) -> Tuple[float, float]:
    """
    Project a (lat, lon) point along a bearing for *distance_m* metres.

    Uses the direct geodesic formula (spherical approximation).

    Returns:
        (new_lat, new_lon) in decimal degrees.
    """
    brng = math.radians(bearing_deg)
    lat1 = math.radians(lat)
    lon1 = math.radians(lon)

    d_over_r = distance_m / _EARTH_R

    lat2 = math.asin(
        math.sin(lat1) * math.cos(d_over_r)
        + math.cos(lat1) * math.sin(d_over_r) * math.cos(brng)
    )
    lon2 = lon1 + math.atan2(
        math.sin(brng) * math.sin(d_over_r) * math.cos(lat1),
        math.cos(d_over_r) - math.sin(lat1) * math.sin(lat2),
    )

    return (math.degrees(lat2), math.degrees(lon2))


def _bearing_between(lat1: float, lon1: float,
                     lat2: float, lon2: float) -> float:
    """Geographic bearing in degrees [0, 360) from point 1 to point 2."""
    lat1r, lon1r = math.radians(lat1), math.radians(lon1)
    lat2r, lon2r = math.radians(lat2), math.radians(lon2)
    dlon = lon2r - lon1r
    x = math.sin(dlon) * math.cos(lat2r)
    y = (math.cos(lat1r) * math.sin(lat2r)
         - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon))
    return (math.degrees(math.atan2(x, y)) + 360) % 360


# ── Directional bias mapping ────────────────────────────────────────────────

_BIAS_TO_BEARING: Dict[str, Optional[float]] = {
    'north': 0.0,
    'east':  90.0,
    'south': 180.0,
    'west':  270.0,
    'none':  None,
}


# ── Smart-snap logic ────────────────────────────────────────────────────────

def _smart_snap(graph, target_lat: float, target_lon: float,
                k: int = SNAP_K) -> Optional[int]:
    """
    Snap a theoretical point to the best nearby graph node.

    Strategy (§2.2 of design doc):
        1. Query the K nearest nodes to (target_lat, target_lon).
        2. Filter out nodes connected *only* to major highways.
        3. Score by distance (closer is better), connectivity (degree > 2),
           and average scenic quality of incident edges.
        4. Return the best node, or None if nothing suitable.
    """
    import osmnx as ox

    print(f"[GeometricSolver]     Smart-snap: target=({target_lat:.6f}, {target_lon:.6f})")

    try:
        # osmnx nearest_nodes returns a single node; use the graph's
        # spatial index manually via a brute-force K-nearest search.
        nodes = list(graph.nodes(data=True))
        if not nodes:
            print(f"[GeometricSolver]     Smart-snap: graph has no nodes")
            return None

        # Compute distances for all nodes and take top-K
        scored: List[Tuple[float, int, dict]] = []
        for nid, data in nodes:
            nlat = data.get('y', data.get('lat', 0.0))
            nlon = data.get('x', data.get('lon', 0.0))
            dist = _haversine(target_lat, target_lon, nlat, nlon)
            scored.append((dist, nid, data))

        scored.sort(key=lambda t: t[0])
        candidates = scored[:k]

        if not candidates:
            print(f"[GeometricSolver]     Smart-snap: no candidates found")
            return None

        print(f"[GeometricSolver]     Smart-snap: evaluating {len(candidates)} candidates")
        best_node = None
        best_score = float('inf')
        evaluated = 0

        for dist, nid, data in candidates:
            # --- Filter: skip highway-only nodes ---
            incident_highways = set()
            for _, _, edata in graph.edges(nid, data=True):
                hw = edata.get('highway', '')
                if isinstance(hw, list):
                    incident_highways.update(hw)
                elif hw:
                    incident_highways.add(hw)

            if incident_highways and incident_highways <= _HIGHWAY_ONLY_TAGS:
                continue  # all edges are major highways → skip

            # --- Score ---
            degree = graph.degree(nid)
            degree_bonus = 0.0 if degree > 2 else 200.0  # penalty for dead-ends

            # Average scenic quality of incident edges (lower norm = greener)
            scenic_costs = []
            for _, _, edata in graph.edges(nid, data=True):
                sc = edata.get('norm_green', 0.5)
                scenic_costs.append(sc)
            avg_scenic = sum(scenic_costs) / len(scenic_costs) if scenic_costs else 0.5
            scenic_penalty = avg_scenic * 100  # 0-100 range

            score = dist + degree_bonus + scenic_penalty
            evaluated += 1
            if score < best_score:
                best_score = score
                best_node = nid

        print(f"[GeometricSolver]     Smart-snap: evaluated {evaluated}/{len(candidates)} nodes, "
              f"selected node {best_node} (dist={best_score:.1f}m)")
        return best_node

    except Exception as e:
        print(f"[GeometricSolver] Smart-snap failed: {e}")
        return None


def _are_reachable(graph, node_a: int, node_b: int) -> bool:
    """Check whether node_a can reach node_b (directed path exists)."""
    import networkx as nx
    try:
        return nx.has_path(graph, node_a, node_b)
    except (nx.NetworkXError, nx.NodeNotFound):
        return False


# ── Point-to-point WSM A* leg router ────────────────────────────────────────

def _route_leg(graph, source: int, target: int,
               weights: Dict[str, float],
               combine_nature: bool = False,
               length_range: Optional[Tuple[float, float]] = None,
               ) -> Optional[Tuple[List[int], float, float]]:
    """
    Route one leg (source -> target) using the WSM A* solver.

    Returns:
        (path, distance_m, scenic_cost)  or  None on failure.
    """
    from app.services.routing.astar.wsm_astar import WSMNetworkXAStar

    print(f"[GeometricSolver]     Routing leg: {source} -> {target}")

    try:
        solver = WSMNetworkXAStar(
            graph, weights, length_range=length_range,
            combine_nature=combine_nature,
        )
        result = solver.astar(source, target)
        if result is None:
            return None

        path = list(result)
        if len(path) < 2:
            return None  # degenerate

        # Compute physical distance and scenic cost along path
        total_dist = 0.0
        total_cost = 0.0
        min_len, max_len = length_range if length_range else find_length_range(graph)

        for i in range(len(path) - 1):
            u, v = path[i], path[i + 1]
            edges = graph[u][v]
            if not edges:
                continue
            # Pick shortest physical edge
            best_len = float('inf')
            best_data = None
            for edata in edges.values():
                el = edata.get('length', float('inf'))
                if el < best_len:
                    best_len = el
                    best_data = edata
            if best_data is None:
                continue

            total_dist += best_len

            norm_length = normalise_length(best_len, min_len, max_len)
            cost = compute_wsm_cost(
                norm_length=norm_length,
                norm_green=best_data.get('norm_green', 0.5),
                norm_water=best_data.get('norm_water', 0.5),
                norm_social=best_data.get('norm_social', 0.5),
                norm_quiet=best_data.get('norm_quiet', 0.5),
                norm_slope=best_data.get('norm_slope', 0.5),
                weights=weights,
                combine_nature=combine_nature,
            )
            total_cost += cost

        print(f"[GeometricSolver]     Leg complete: {len(path)} nodes, "
              f"distance={total_dist:.1f}m, scenic_cost={total_cost:.4f}")
        return (path, total_dist, total_cost)

    except Exception as e:
        print(f"[GeometricSolver] Leg routing failed {source}→{target}: {e}")
        return None


# ── Triangle construction & routing ──────────────────────────────────────────

def _try_triangle(
    graph,
    start_node: int,
    target_distance: float,
    weights: Dict[str, float],
    combine_nature: bool,
    bearing: float,
    tau: float,
    length_range: Tuple[float, float],
) -> Optional[Tuple[List[int], float, float, float]]:
    """
    Attempt to build and route one equilateral-triangle skeleton.

    Steps:
        1. Compute side length a = D / (3 × τ).
        2. Project W1 at *bearing*, W2 at *bearing + 60°* from start.
        3. Smart-snap W1, W2 to real graph nodes.
        4. Route legs in "critical leg first" order (W1→W2, S→W1, W2→S).
        5. Concatenate and return full loop.

    Returns:
        (route, distance, scenic_cost, actual_tau) or None on failure.
    """
    s_lat, s_lon = _node_coords(graph, start_node)
    side_length = target_distance / (3.0 * tau)

    print(f"[GeometricSolver]   Triangle attempt: start_node={start_node}, "
          f"bearing={bearing:.1f} deg, tau={tau:.3f}, side_length={side_length:.1f}m")

    # -- Step 1: Project waypoints ------------------------------------
    w1_lat, w1_lon = _project_point(s_lat, s_lon, bearing, side_length)
    w2_lat, w2_lon = _project_point(s_lat, s_lon, (bearing + 60) % 360,
                                     side_length)
    print(f"[GeometricSolver]   Projected W1=({w1_lat:.6f}, {w1_lon:.6f}), "
          f"W2=({w2_lat:.6f}, {w2_lon:.6f})")

    # -- Step 2: Smart-snap to graph nodes ----------------------------
    print(f"[GeometricSolver]   Snapping waypoints...")
    w1_node = _smart_snap(graph, w1_lat, w1_lon)
    w2_node = _smart_snap(graph, w2_lat, w2_lon)

    if w1_node is None or w2_node is None:
        print(f"[GeometricSolver]   [FAILED] Snap failed (W1={w1_node}, W2={w2_node})")
        return None

    print(f"[GeometricSolver]   Snapped to W1={w1_node}, W2={w2_node}")

    # Avoid degenerate triangles
    if w1_node == w2_node or w1_node == start_node or w2_node == start_node:
        print(f"[GeometricSolver]   [FAILED] Degenerate triangle "
              f"(S={start_node}, W1={w1_node}, W2={w2_node})")
        return None

    # -- Step 2b: Reachability check ----------------------------------
    print(f"[GeometricSolver]   Checking graph connectivity...")
    reach_s_w1 = _are_reachable(graph, start_node, w1_node)
    reach_w1_w2 = _are_reachable(graph, w1_node, w2_node)
    reach_w2_s = _are_reachable(graph, w2_node, start_node)
    
    if not (reach_s_w1 and reach_w1_w2 and reach_w2_s):
        print(f"[GeometricSolver]   [FAILED] Reachability check failed: "
              f"S->W1={reach_s_w1}, W1->W2={reach_w1_w2}, W2->S={reach_w2_s}")
        return None
    
    print(f"[GeometricSolver]   [OK] All nodes reachable")

    # -- Step 3: Route legs -- Critical Leg First ----------------------
    print(f"[GeometricSolver]   Routing legs (Critical Leg First)...")

    # Leg B (Bridge Crosser): W1 -> W2
    print(f"[GeometricSolver]   -> Leg B (Bridge): W1->W2")
    leg_b = _route_leg(graph, w1_node, w2_node, weights,
                       combine_nature, length_range)
    if leg_b is None:
        print(f"[GeometricSolver]   [FAILED] Leg B (W1->W2) failed")
        return None

    path_b, dist_b, cost_b = leg_b

    # Bridge-leg detour check: routed dist vs air distance
    w1_lat_a, w1_lon_a = _node_coords(graph, w1_node)
    w2_lat_a, w2_lon_a = _node_coords(graph, w2_node)
    air_b = _haversine(w1_lat_a, w1_lon_a, w2_lat_a, w2_lon_a)
    detour_ratio = dist_b / air_b if air_b > 0 else 1.0
    print(f"[GeometricSolver]   Bridge leg: routed={dist_b:.0f}m, "
          f"air={air_b:.0f}m, ratio={detour_ratio:.2f}x")
    
    if air_b > 0 and dist_b > BRIDGE_LEG_DETOUR_FACTOR * air_b:
        print(f"[GeometricSolver]   [FAILED] Bridge leg too detoured "
              f"({detour_ratio:.2f}x > {BRIDGE_LEG_DETOUR_FACTOR}x threshold)")
        return None
    
    print(f"[GeometricSolver]   [OK] Bridge leg acceptable")

    # Leg A: S -> W1
    print(f"[GeometricSolver]   -> Leg A: S->W1")
    leg_a = _route_leg(graph, start_node, w1_node, weights,
                       combine_nature, length_range)
    if leg_a is None:
        print(f"[GeometricSolver]   [FAILED] Leg A (S->W1) failed")
        return None
    path_a, dist_a, cost_a = leg_a

    # Leg C: W2 -> S
    print(f"[GeometricSolver]   -> Leg C: W2->S")
    leg_c = _route_leg(graph, w2_node, start_node, weights,
                       combine_nature, length_range)
    if leg_c is None:
        print(f"[GeometricSolver]   [FAILED] Leg C (W2->S) failed")
        return None
    path_c, dist_c, cost_c = leg_c

    # -- Step 4: Concatenate ------------------------------------------
    # path_a ends at W1, path_b starts at W1 -> skip first node of B
    # path_b ends at W2, path_c starts at W2 -> skip first node of C
    full_route = path_a + path_b[1:] + path_c[1:]

    total_distance = dist_a + dist_b + dist_c
    total_cost = cost_a + cost_b + cost_c

    print(f"[GeometricSolver]   [SUCCESS] Triangle complete: {len(full_route)} nodes, "
          f"{total_distance:.0f}m, scenic_cost={total_cost:.4f}")
    print(f"[GeometricSolver]   Leg breakdown: A={dist_a:.0f}m, B={dist_b:.0f}m, C={dist_c:.0f}m")

    return (full_route, total_distance, total_cost, tau)


def _try_out_and_back(
    graph,
    start_node: int,
    target_distance: float,
    weights: Dict[str, float],
    combine_nature: bool,
    bearing: float,
    tau: float,
    length_range: Tuple[float, float],
) -> Optional[Tuple[List[int], float, float]]:
    """
    Fallback: out-and-back route when all triangle attempts fail.

    Collapses W1 and W2 to a single waypoint at D / (2 × τ).
    Routes S → W → S.

    Returns:
        (route, distance, scenic_cost) or None on failure.
    """
    print(f"[GeometricSolver]   Out-and-back: bearing={bearing:.1f} deg, tau={tau:.3f}")
    s_lat, s_lon = _node_coords(graph, start_node)
    half_dist = target_distance / (2.0 * tau)

    print(f"[GeometricSolver]   Projecting waypoint at {half_dist:.0f}m")
    w_lat, w_lon = _project_point(s_lat, s_lon, bearing, half_dist)
    w_node = _smart_snap(graph, w_lat, w_lon)

    if w_node is None or w_node == start_node:
        print(f"[GeometricSolver]   [FAILED] Out-and-back snap failed or degenerate")
        return None

    print(f"[GeometricSolver]   Snapped to W={w_node}")

    if not (_are_reachable(graph, start_node, w_node)
            and _are_reachable(graph, w_node, start_node)):
        print(f"[GeometricSolver]   [FAILED] Out-and-back reachability failed")
        return None

    print(f"[GeometricSolver]   -> Routing outbound leg: S->W")
    leg_out = _route_leg(graph, start_node, w_node, weights,
                         combine_nature, length_range)
    if leg_out is None:
        print(f"[GeometricSolver]   [FAILED] Outbound leg failed")
        return None

    print(f"[GeometricSolver]   -> Routing return leg: W->S")
    leg_back = _route_leg(graph, w_node, start_node, weights,
                          combine_nature, length_range)
    if leg_back is None:
        print(f"[GeometricSolver]   [FAILED] Return leg failed")
        return None

    path_out, dist_out, cost_out = leg_out
    path_back, dist_back, cost_back = leg_back

    route = path_out + path_back[1:]
    total_distance = dist_out + dist_back
    total_cost = cost_out + cost_back
    print(f"[GeometricSolver]   [SUCCESS] Out-and-back complete: {len(route)} nodes, "
          f"{total_distance:.0f}m, scenic_cost={total_cost:.4f}")
    return (route, total_distance, total_cost)


# ══════════════════════════════════════════════════════════════════════════════
# GeometricLoopSolver
# ══════════════════════════════════════════════════════════════════════════════

class GeometricLoopSolver(LoopSolverBase):
    """
    Geometric Loop Solver — "Triangle-Plateau" strategy.

    Builds equilateral-triangle skeletons at varied bearings, routes
    each leg with WSM A*, and uses clamped proportional feedback to
    converge on the target distance.

    See the design document for full algorithm specification.
    """

    # ── Interface ────────────────────────────────────────────────────────

    def find_loops(
        self,
        graph,
        start_node: int,
        target_distance: float,
        weights: Dict[str, float],
        combine_nature: bool = False,
        directional_bias: str = "none",
        num_candidates: int = 7,
        distance_tolerance: float = 0.15,
        max_search_time: float = 120,
        variety_level: int = 0,
        prefer_pedestrian: bool = False,
        prefer_paved: bool = False,
        prefer_lit: bool = False,
        avoid_unsafe_roads: bool = False,
    ) -> List[LoopCandidate]:
        """
        Find multiple loop route candidates using the geometric skeleton
        approach.

        For each rotational bearing we attempt up to MAX_FEEDBACK_RETRIES
        iterations of τ-feedback.  If all triangle attempts fail for a
        bearing, we fall back to out-and-back.
        """
        t0 = time.time()
        weights = validate_weights(weights)
        length_range = find_length_range(graph)

        print(f"\n[GeometricSolver] ======================================================")
        print(f"[GeometricSolver] Starting Geometric Loop Solver")
        print(f"[GeometricSolver] Graph: {graph.number_of_nodes()} nodes, {graph.number_of_edges()} edges")
        print(f"[GeometricSolver] Start node: {start_node}")
        print(f"[GeometricSolver] Target distance: {target_distance:.0f}m ({target_distance/1000:.2f}km)")
        print(f"[GeometricSolver] Weights: {weights}")
        print(f"[GeometricSolver] Combine nature: {combine_nature}")
        print(f"[GeometricSolver] Directional bias: {directional_bias}")
        print(f"[GeometricSolver] Num candidates: {num_candidates}")
        print(f"[GeometricSolver] Distance tolerance: +/-{distance_tolerance*100:.0f}%")
        print(f"[GeometricSolver] Max search time: {max_search_time:.0f}s")
        print(f"[GeometricSolver] Variety level: {variety_level}")
        print(f"[GeometricSolver] ======================================================\n")

        # ── Determine rotation bearings ──────────────────────────────────
        base_bearing = _BIAS_TO_BEARING.get(directional_bias.lower())

        # Number of candidate attempts — more variety = more attempts
        num_attempts = max(num_candidates + 1, 3 + variety_level)
        rotation_step = 360.0 / num_attempts

        if base_bearing is not None:
            # User requested a direction: start from that bearing
            bearings = [
                (base_bearing + i * rotation_step) % 360
                for i in range(num_attempts)
            ]
        else:
            # No bias: use equidistant bearings starting from 0°
            bearings = [
                (i * rotation_step) % 360
                for i in range(num_attempts)
            ]

        print(f"[GeometricSolver] Generated {len(bearings)} bearings: {[f'{b:.0f}°' for b in bearings]}")
        print(f"")

        all_candidates: List[Tuple[List[int], float, float]] = []

        for idx, bearing in enumerate(bearings):
            elapsed = time.time() - t0
            if elapsed > max_search_time:
                print(f"\n[GeometricSolver] [TIME LIMIT] Reached ({elapsed:.1f}s > {max_search_time}s)")
                break

            print(f"\n[GeometricSolver] ------------------------------------------------")
            print(f"[GeometricSolver] Bearing {idx+1}/{len(bearings)}: {bearing:.1f} deg (elapsed: {elapsed:.1f}s)")
            print(f"[GeometricSolver] ------------------------------------------------")

            tau = DEFAULT_TAU
            triangle_success = False

            # ── Clamped proportional feedback loop ───────────────────
            for retry in range(MAX_FEEDBACK_RETRIES):
                if time.time() - t0 > max_search_time:
                    break

                result = _try_triangle(
                    graph, start_node, target_distance, weights,
                    combine_nature, bearing, tau, length_range,
                )

                if result is None:
                    # Triangle construction failed entirely -- no feedback
                    print(f"[GeometricSolver]   [FAILED] Retry {retry}: triangle construction failed")
                    break

                route, actual_dist, scenic_cost, _ = result

                # -- Check asymmetric tolerance -------------------
                frac = (actual_dist - target_distance) / target_distance
                deviation_pct = frac * 100
                print(f"[GeometricSolver]   Distance check: {actual_dist:.0f}m "
                      f"(target: {target_distance:.0f}m, deviation: {deviation_pct:+.1f}%)")
                print(f"[GeometricSolver]   Tolerance range: [{-TOLERANCE_UNDER*100:.1f}%, +{TOLERANCE_OVER*100:.1f}%]")
                
                if -TOLERANCE_UNDER <= frac <= TOLERANCE_OVER:
                    # Success!
                    all_candidates.append((route, actual_dist, scenic_cost))
                    triangle_success = True
                    print(f"[GeometricSolver]   [SUCCESS] ACCEPTED: {actual_dist:.0f}m ({deviation_pct:+.1f}%), tau={tau:.3f}")
                    break

                # -- Clamped update --------------------------------
                if target_distance > 0:
                    raw_ratio = actual_dist / target_distance
                    clamped_ratio = max(
                        TAU_CLAMP_LOW,
                        min(TAU_CLAMP_HIGH, raw_ratio),
                    )
                    tau_new = tau * clamped_ratio
                    print(f"[GeometricSolver]   Tau adjustment: raw_ratio={raw_ratio:.3f}, "
                          f"clamped={clamped_ratio:.3f}")
                    print(f"[GeometricSolver]   --> Tau {tau:.3f} -> {tau_new:.3f}")
                    tau = tau_new
                else:
                    break

            # -- Fallback: out-and-back if triangle failed ------------
            if not triangle_success:
                if time.time() - t0 > max_search_time:
                    print(f"[GeometricSolver]   [SKIP] Skipping fallback (time limit)")
                    continue
                print(f"\n[GeometricSolver]   [WARNING] All triangle attempts failed, trying out-and-back...")
                oab = _try_out_and_back(
                    graph, start_node, target_distance, weights,
                    combine_nature, bearing, DEFAULT_TAU, length_range,
                )
                if oab is not None:
                    route_oab, dist_oab, cost_oab = oab
                    frac_oab = (dist_oab - target_distance) / target_distance
                    deviation_oab_pct = frac_oab * 100
                    print(f"[GeometricSolver]   Out-and-back check: {dist_oab:.0f}m "
                          f"({deviation_oab_pct:+.1f}%), tolerance=+/-{distance_tolerance*100:.0f}%")
                    # Accept with wider tolerance for fallback
                    if abs(frac_oab) <= distance_tolerance:
                        all_candidates.append((route_oab, dist_oab, cost_oab))
                        print(f"[GeometricSolver]   [SUCCESS] Out-and-back ACCEPTED: "
                              f"{dist_oab:.0f}m ({deviation_oab_pct:+.1f}%)")
                    else:
                        print(f"[GeometricSolver]   [FAILED] Out-and-back outside tolerance")

        # -- Convert to LoopCandidates ------------------------------------
        elapsed = time.time() - t0
        print(f"\n[GeometricSolver] ======================================================")
        print(f"[GeometricSolver] Search complete: {len(all_candidates)} raw candidates found")
        print(f"[GeometricSolver] Total time: {elapsed:.1f}s")
        print(f"[GeometricSolver] ======================================================\n")
        
        if not all_candidates:
            print(f"[GeometricSolver] [FAILED] No viable loops found")
            return []

        max_cost = max(c for _, _, c in all_candidates) if all_candidates else 1.0
        max_cost = max(max_cost, 0.001)
        print(f"[GeometricSolver] Max scenic cost (for normalization): {max_cost:.4f}")

        candidates: List[LoopCandidate] = []
        for route, distance, scenic_cost in all_candidates:
            deviation = abs(distance - target_distance) / target_distance
            quality = calculate_quality_score(
                deviation, scenic_cost, max_scenic_cost=max_cost,
            )

            candidates.append(LoopCandidate(
                route=route,
                distance=distance,
                scenic_cost=scenic_cost,
                deviation=deviation,
                quality_score=quality,
                algorithm='geometric',
                metadata={
                    'directional_bias': directional_bias,
                    'target_distance': target_distance,
                    'solver': 'triangle_plateau',
                },
            ))

        # -- Select diverse candidates ------------------------------------
        print(f"[GeometricSolver] Selecting {num_candidates} diverse candidates from {len(candidates)} total...")
        result = select_diverse_candidates(candidates, k=num_candidates)

        print(f"\n[GeometricSolver] ======================================================")
        print(f"[GeometricSolver] Final Results:")
        for i, candidate in enumerate(result):
            print(f"[GeometricSolver]   [{i+1}] {candidate.label}: "
                  f"{candidate.distance:.0f}m ({candidate.deviation_percent:+.1f}%), "
                  f"quality={candidate.quality_score:.3f}, "
                  f"scenic_cost={candidate.scenic_cost:.4f}, "
                  f"{len(candidate.route)} nodes")
        print(f"[GeometricSolver] Total time: {elapsed:.1f}s")
        print(f"[GeometricSolver] ======================================================\n")

        return result
