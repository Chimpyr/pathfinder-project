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
from app.services.processors.greenness.utils import (
    build_spatial_index,
    project_gdf,
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
SNAP_K = 50

# Highway tags considered "highway-only" (undesirable for waypoints)
_HIGHWAY_ONLY_TAGS = frozenset({
    'motorway', 'motorway_link', 'trunk', 'trunk_link',
    'primary', 'primary_link',
})

_LOOP_DEMO_SCHEMA_VERSION = 1
_LOOP_DEMO_DEFAULT_MAX_FRAMES = 400
_LOOP_DEMO_MAX_PATH_POINTS = 80


def _demo_event(loop_demo_context, event, **payload):
    """Append a bounded demo frame when loop demo capture is enabled."""
    if loop_demo_context is None:
        return

    frames = loop_demo_context.setdefault('frames', [])
    max_frames = int(loop_demo_context.get('max_frames', _LOOP_DEMO_DEFAULT_MAX_FRAMES))
    if len(frames) >= max_frames:
        loop_demo_context['truncated'] = True
        return

    frame = {'event': event}
    frame.update(payload)
    frames.append(frame)


def _round_coord_pair(lat, lon):
    return [round(float(lat), 6), round(float(lon), 6)]


def _sample_route_coords(graph, path_nodes, max_points=_LOOP_DEMO_MAX_PATH_POINTS):
    """Convert a routed node path to a bounded list of rounded coordinates."""
    if not path_nodes:
        return []

    coords = [_round_coord_pair(*_node_coords(graph, node)) for node in path_nodes]
    if len(coords) <= max_points:
        return coords

    step = max(1, math.ceil((len(coords) - 1) / max(1, max_points - 1)))
    sampled = coords[::step]
    if sampled[-1] != coords[-1]:
        sampled.append(coords[-1])
    return sampled


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


# ── Smart Bearing Logic ─────────────────────────────────────────────────────

def _analyze_scenic_sectors(graph, start_node: int, radius_m: float) -> List[Tuple[float, float]]:
    """
    Analyze surrounding scenic features to find the best bearings.

    1. Projects start node to metres.
    2. Builds spatial index for graph.features (if not present).
    3. Queries features within radius_m.
    4. Bins them into 12 sectors (30-degree slices).
    5. Returns list of (bearing, score) tuples, sorted by score descending.
    """
    import geopandas as gpd
    from shapely.geometry import Point, box

    # 1. Get start node projected coords
    nd = graph.nodes[start_node]
    # Check if graph is projected (x, y) or geographic (lon, lat)
    # The greenness utils expect projected features, so we should allow both
    # but strictly we need the features to be in meters.
    # We'll assume graph.features is loaded.
    
    if not hasattr(graph, 'features') or graph.features is None or graph.features.empty:
        print("[GeometricSolver]   Smart Bearing: No features found in graph")
        return []

    # Ensure spatial index exists on the features GDF
    if not hasattr(graph, 'sindex_features') or graph.sindex_features is None:
        print("[GeometricSolver]   Smart Bearing: Building spatial index...")
        # Project features if needed
        # Note: In a real app, this should be done at load time.
        # We'll do a quick check here.
        # For safety, we use the utility which handles projection
        if graph.features.crs and graph.features.crs.is_geographic:
             # This might be slow if we do it every time, but let's assume it's okay for now
             # or better, strict check
             pass 
        
        # We'll use the helper to get/build sindex.
        # However, to avoid modifying graph state implicitly too much, we'll just build it locally
        # if it doesn't exist.
        sindex, _ = build_spatial_index(graph.features)
        # Cache it? Maybe not for this prototype to avoid side effects.
    else:
        sindex = graph.sindex_features

    if sindex is None:
         # Fallback if build failed
         sindex, _ = build_spatial_index(graph.features)

    if sindex is None:
        return []

    # Get start point in projected coords (meters) for distance checks
    # conversion
    # We need a robust way to get meters.
    # We'll use the transformer from utils if needed, or just relying on the fact
    # that 'graph.features' usually comes from OSMDataLoader which might be WGS84.
    # WAIT: loading.py loads features as WGS84 usually.
    # We need to project everything to meters for "radius" and "area" to make sense.
    
    # Let's do a simplified approach:
    # 1. work in WGS84 (degrees).
    # 2. Convert radius_m to degrees (approx).
    
    # Latitude normalization
    lat = nd.get('y', nd.get('lat'))
    lon = nd.get('x', nd.get('lon'))
    
    # 1 deg lat ~= 111,000m
    buffer_deg = radius_m / 111000.0
    
    # Create a bounding box in WGS84
    bbox = box(lon - buffer_deg, lat - buffer_deg, lon + buffer_deg, lat + buffer_deg)
    
    # Query candidates
    candidate_idxs = sindex.query(bbox)
    
    if len(candidate_idxs) == 0:
        return []
        
    # Initialize 12 sectors (0-30, 30-60, ...)
    # 0 is North.
    sector_scores = [0.0] * 12
    
    # Process candidates
    # We need the actual geometries.
    features = graph.features.iloc[candidate_idxs]
    
    start_point = Point(lon, lat)
    
    for _, row in features.iterrows():
        # Tag filtering? (parks, water)
        # Assumption: loaded features are already "scenic"
        
        # Calculate bearing to centroid
        centroid = row.geometry.centroid
        brng = _bearing_between(lat, lon, centroid.y, centroid.x)
        
        # Bin index
        bin_idx = int(brng // 30) % 12
        
        # Weight = Area * DistanceFactor?
        # In WGS84 area is weird. Let's just use a simple heuristic:
        # 1. Distance from start (closer = better)
        dist = _haversine(lat, lon, centroid.y, centroid.x)
        if dist > radius_m:
            continue
            
        # 2. "Mass" ~ approximate area or just 1.0 for existence?
        # A large park is better than a small one.
        # Area in deg^2 is tiny.
        # Let's scale up.
        area_weight = row.geometry.area * 1e8 # Arbitrary scaling
        
        # Decay with distance
        decay = 1.0 - (dist / radius_m)
        
        score = area_weight * decay
        
        # Add to bin
        sector_scores[bin_idx] += score
        
    # Smoothing (Window size 3) to find "broad" sectors
    smoothed = []
    for i in range(12):
        prev = sector_scores[(i-1)%12]
        curr = sector_scores[i]
        next_ = sector_scores[(i+1)%12]
        smoothed.append( (prev + 2*curr + next_) / 4 )
        
    # Create (bearing, score) tuples (center of sector)
    results = []
    for i, score in enumerate(smoothed):
        center_bearing = (i * 30) + 15
        results.append((center_bearing, score))
        
    # Sort descending
    results.sort(key=lambda x: x[1], reverse=True)
    
    # Debug print
    # print(f"[GeometricSolver]   Smart Bearing Scores: {[(int(b), f'{s:.2f}') for b,s in results[:3]]}")
    
    return results


# ── Smart-snap logic ────────────────────────────────────────────────────────

def _smart_snap(
    graph, 
    target_lat: float, 
    target_lon: float,
    k: int = SNAP_K,
    prev_point: Optional[Tuple[float, float]] = None,
    next_point: Optional[Tuple[float, float]] = None
) -> Optional[int]:
    """
    Snap a theoretical point to the best nearby graph node.

    Strategy (§2.2 of design doc) + Flow Awareness:
        1. Query the K nearest nodes to (target_lat, target_lon).
        2. Filter out nodes connected *only* to major highways.
        3. Score by distance, connectivity, greenness.
        4. **Flow Awareness**: Usage vectors P->Candidate and Candidate->Next.
           If the angle implies a sharp turn (> 120°), penalize heavily.
           This prevents "backtracking" at corners.
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
        scored: List[Tuple[float, int]] = [] # Store (distance, nid)
        for nid, data in nodes:
            nlat = data.get('y', data.get('lat', 0.0))
            nlon = data.get('x', data.get('lon', 0.0))
            dist = _haversine(target_lat, target_lon, nlat, nlon)
            scored.append((dist, nid))

        if not scored:
            print(f"[GeometricSolver]     Smart-snap: no candidates found")
            return None

        if not scored:
            print(f"[GeometricSolver]     Smart-snap: no candidates found")
            return None

        # Sort by distance so we check closest nodes first
        scored.sort(key=lambda x: x[0])

        # EXPANDING SEARCH (Flat Loop):
        # Iterate through candidates sorted by distance.
        # We process at least 'min_search' (K) candidates.
        # If we find a good one within K, we pick the best.
        # If not, we keep searching up to 'max_search' (500).
        
        min_search = k
        max_search = 500
        
        candidates_pool = scored
        best_node = None
        best_score = float('inf')
        
        for i, (dist, nid) in enumerate(candidates_pool):
            data = graph.nodes[nid]

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
            
            # STRICT BAN: Dead ends (Degree 1) guarantee a U-turn / Backtrack.
            if degree < 2: 
                continue

            # Small bonus for junctions (deg > 2), small penalty for simple corners (deg=2)
            # JUNCTION PRIORITY: Heavily penalize degree 2 nodes (mid-block) to force turns at junctions.
            degree_bonus = 0.0 if degree > 2 else 500.0

            # Average scenic quality of incident edges (lower norm = greener)
            scenic_costs = []
            for _, _, edata in graph.edges(nid, data=True):
                sc = edata.get('norm_green', 0.5)
                scenic_costs.append(sc)
            avg_scenic = sum(scenic_costs) / len(scenic_costs) if scenic_costs else 0.5
            scenic_penalty = avg_scenic * 100  # 0-100 range
            
            # --- Flow Awareness (Anti-Backtracking) ---
            flow_penalty = 0.0
            if prev_point and next_point:
                nlat = data.get('y', data.get('lat', 0.0))
                nlon = data.get('x', data.get('lon', 0.0))
                
                # Vector In: Prev -> Node
                # Vector Out: Node -> Next
                
                # Calculate bearings
                bearing_in = _bearing_between(prev_point[0], prev_point[1], nlat, nlon)
                bearing_out = _bearing_between(nlat, nlon, next_point[0], next_point[1])
                
                # Turn Angle: Difference between In and Out?
                # No, standard deviation from straight line.
                # If we continue expanding the loop, In and Out should differ by ~60-120 deg (positive turn).
                # A U-turn means they differ by ~180 deg relative to forward direction.
                
                # Angle difference
                diff = abs(bearing_in - bearing_out)
                diff = min(diff, 360 - diff)
                
                # "Good" turn for a loop is roughly 30-150 degrees.
                # "Bad" turn ("Sharp U-Turn/Spike") is > 150 deg (Backtracking) or < 20 deg (Straight line? No straight is fine).
                # Wait:
                # If Prev->Node is North (0), Node->Next is South (180). Diff = 180. That's a spike.
                # If Prev->Node is North (0), Node->Next is North (0). Diff = 0. That's straight.
                # 
                # Ideally, for a loop, we want "some turn" but not "reverse turn".
                # Actually, in a geometric skeleton, the *theoretical* locations already form the shape.
                # So we just want the snapped node to RESPECT that flow.
                # The theoretical turn is already ~60-120deg.
                # So we penalize deviation from THEORETICAL flow?
                # OR simpler: Penalize U-turns (Diff > 135).
                
                if diff > 135: # Sharp turn / U-turn
                     flow_penalty = 500.0 # Huge penalty (500m equivalent)
                elif diff > 100: # Mild sharp turn
                     flow_penalty = 50.0

            # --- Junction Awareness (Edge Alignment) ---
            # Does this node have an edge that actually points to 'next_point'?
            alignment_penalty = 0.0
            if next_point:
                nlat = data.get('y', data.get('lat', 0.0))
                nlon = data.get('x', data.get('lon', 0.0))
                
                # We need the bearing from Node -> Next (Already calculated as bearing_out above? 
                # If not, calculate it)
                if 'bearing_out' not in locals():
                     bearing_out = _bearing_between(nlat, nlon, next_point[0], next_point[1])
                
                has_aligned_edge = False
                
                # Check all outgoing edges (Junction Awareness)
                # Ensure we have a valid exit that matches the target bearing
                # AND is not a motorway/trunk/primary road.
                
                # Added 'primary' to forbidden to favor quieter roads for waypoints
                forbidden_exits = {'motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary', 'primary_link'}
                
                debug_edge_checks = [] # Store logs to print only if needed (or verbose)
                
                for _, neighbor, edge_data in graph.edges(nid, data=True):
                    hw = edge_data.get('highway', '')
                    
                    # Log snippet
                    hw_str = str(hw)
                    
                    if isinstance(hw, list):
                        if set(hw) & forbidden_exits:
                            debug_edge_checks.append(f"    - Edge -> {neighbor}: SKIP (Forbidden {hw})")
                            continue
                    elif hw in forbidden_exits:
                        debug_edge_checks.append(f"    - Edge -> {neighbor}: SKIP (Forbidden {hw})")
                        continue
                        
                    try:
                        neighbor_data = graph.nodes[neighbor]
                        n2_lat = neighbor_data.get('y', neighbor_data.get('lat'))
                        n2_lon = neighbor_data.get('x', neighbor_data.get('lon'))
                        
                        edge_bearing = _bearing_between(nlat, nlon, n2_lat, n2_lon)
                        
                        ediff = abs(edge_bearing - bearing_out)
                        ediff = min(ediff, 360 - ediff)
                        
                        debug_edge_checks.append(f"    - Edge -> {neighbor}: bearing={edge_bearing:.0f}, diff={ediff:.0f}, hw={hw}")
                        
                        if ediff < 90: # Relaxed alignment (+/- 90 deg = Forward Hemisphere)
                            has_aligned_edge = True
                            # Found one! No need to check others for *validity*, but keep checking for debug?
                            # Break for performance.
                            break
                    except KeyError:
                        continue
                        
                if not has_aligned_edge:
                    # No road goes in the direction we want!
                    # OR the only roads going there are motorways.
                    # This implies we'd have to take a road going elsewhere and finding a turn.
                    # PENALTY TUNING: 2000m was too high, causing the solver to pick nodes 1km away just to satisfy this.
                    # Reduced to 400m to balance "bad alignment" vs "huge detour".
                    alignment_penalty = 400.0 
                else:
                     # It passed!
                     # Find which edge passed to log it
                     # print(f"[GeometricSolver]   Node {nid} PASSED. Edge checks:")
                     # for l in debug_edge_checks:
                     #     print(l)
                     pass
                        
            # --- Main Road Penalty ---
            # Penalize snapping to nodes that touch major roads, even if they have valid exits.
            # We prefer waypoints to be in quiet areas.
            main_road_penalty = 0.0
            major_roads = {'motorway', 'motorway_link', 'trunk', 'trunk_link', 'primary', 'primary_link', 'secondary', 'secondary_link'}
            
            if incident_highways & major_roads:
                # PENALTY TUNING: Reduced to 300m. 
                # If the nearest quiet road is >300m away, we accept the main road to avoid 
                # "going too far" and creating awkward loops.
                main_road_penalty = 300.0
                # print(f"[GeometricSolver]   Node {nid} PENALIZED (Touching Major Road). Penalty=2000.0")
                
            # DISTANCE SCALING:
            # We scale distance by 0.5 so that a "clean" node 600m away (Score=300) 
            # can beat a "messy" node 100m away (Score=50 + 400 penalty = 450).
            score = (dist * 0.5) + degree_bonus + scenic_penalty + flow_penalty + alignment_penalty + main_road_penalty
            
            # print(f"[GeometricSolver]   Node {nid} Score {score:.1f} (D={dist:.0f}, F={flow_penalty}, A={alignment_penalty}, M={main_road_penalty})")
            
            if score < best_score:
                best_score = score
                best_node = nid
                
            # TERMINATION CHECK:
            # If we have evaluated enough candidates (min_search) AND found at least one valid node, stop.
            if (i + 1) >= min_search and best_node is not None:
                break
                
            if (i + 1) >= max_search:
                # Hard limit reached
                break

        if best_node:
            print(f"[GeometricSolver]     Smart-snap selected {best_node} (Score={best_score:.1f})")
        
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


def _recalculate_route_stats(
    graph, route: List[int], weights: Dict[str, float],
    combine_nature: bool, length_range: Tuple[float, float]
) -> Tuple[float, float]:
    """
    Recalculate total distance and scenic cost for a route.
    Used after spur pruning to get accurate metrics.
    """
    total_dist = 0.0
    total_cost = 0.0
    min_len, max_len = length_range

    for i in range(len(route) - 1):
        u, v = route[i], route[i+1]
        edges = graph.get_edge_data(u, v)
        if not edges:
            continue
            
        # Find best edge (same logic as _route_leg)
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
        
    return total_dist, total_cost



# ── Point-to-point WSM A* leg router ────────────────────────────────────────

def _route_leg(graph, source: int, target: int,
               weights: Dict[str, float],
               combine_nature: bool = False,
               length_range: Optional[Tuple[float, float]] = None,
               prefer_dedicated_pavements: bool = False,
               prefer_nature_trails: bool = False,
               prefer_paved: bool = False,
               prefer_lit: bool = False,
               avoid_unsafe_roads: bool = False,
               heavily_avoid_unlit: bool = False,
               activity: str = 'walking',
               lighting_context: str = 'night',
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
            prefer_dedicated_pavements=prefer_dedicated_pavements,
            prefer_nature_trails=prefer_nature_trails,
            prefer_paved=prefer_paved,
            prefer_lit=prefer_lit,
            avoid_unsafe_roads=avoid_unsafe_roads,
            heavily_avoid_unlit=heavily_avoid_unlit,
            activity=activity,
            lighting_context=lighting_context,
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

def _try_polygon(
    graph,
    start_node: int,
    target_distance: float,
    weights: Dict[str, float],
    combine_nature: bool,
    bearing: float,
    tau: float,
    length_range: Tuple[float, float],
    num_vertices: int = 3,  # Total vertices including Start (3=Triangle, 4=Quad)
    arc_angle: float = 90.0,  # Total spread of the shape
    irregularity: float = 0.0,  # 0.0 = perfect symmetry, 1.0 = high jitter
    prefer_dedicated_pavements: bool = False,
    prefer_nature_trails: bool = False,
    prefer_paved: bool = False,
    prefer_lit: bool = False,
    avoid_unsafe_roads: bool = False,
    heavily_avoid_unlit: bool = False,
    activity: str = 'walking',
    lighting_context: str = 'night',
    loop_demo_context=None,
) -> Optional[Tuple[List[int], float, float, float]]:
    """
    Attempt to build and route a 'Natural Shape' polygon loop.
    
    Instead of a rigid triangle, this places N-1 waypoints along an arc 
    centered on the main bearing.
    
    Logic:
        1. Calculate Radius R based on total length D/tau and arc geometry.
           Approx: Length = 2R + ArcLength = R(2 + theta_rad)
           So R = (D/tau) / (2 + theta_radians)
        2. Distribute N-1 waypoints along the arc from (bearing - arc/2) to (bearing + arc/2).
        3. Apply random jitter to angles and radii if irregularity > 0.
        4. Route legs S -> W1 -> W2 ... -> Wn -> S.
    """
    import random
    
    s_lat, s_lon = _node_coords(graph, start_node)
    
    # 1. Calculate Geometry
    angle_rad = math.radians(arc_angle)
    # Estimate Radius: D/tau = 2R (out/back) + Arc (R*theta)
    # This is an approximation assuming the path follows the perimeter
    radius = (target_distance / tau) / (2.0 + angle_rad)
    
    # Sanity check radius
    if radius < 50:
        return None

    # 2. Determine Waypoint Angles
    num_waypoints = num_vertices - 1
    waypoints_data = [] # (lat, lon, node)
    
    # Start angle (relative to symmetry axis 'bearing')
    start_angle_rel = -arc_angle / 2.0
    
    if num_waypoints > 1:
        step_angle = arc_angle / (num_waypoints - 1)
    else:
        # Fallback for degenerate line (shouldn't happen with N>=3)
        step_angle = 0 
        start_angle_rel = 0
        
    print(f"[GeometricSolver]   Polygon attempt (N={num_vertices}): bearing={bearing:.1f}, "
          f"arc={arc_angle}°, tau={tau:.3f}, radius={radius:.0f}m, jitter={irregularity:.2f}")
    _demo_event(
        loop_demo_context,
        'polygon_attempt_started',
        bearing=round(float(bearing), 3),
        num_vertices=int(num_vertices),
        arc_angle=round(float(arc_angle), 3),
        tau=round(float(tau), 6),
        radius_m=round(float(radius), 2),
    )

    # 3. Project Waypoints (Theoretical)
    theoretical_points = [] # List of (lat, lon)
    
    prev_node_coords = (s_lat, s_lon)
    
    for i in range(num_waypoints):
        # Nominal angle
        angle_rel = start_angle_rel + (i * step_angle)
        
        # Apply Jitter
        jitter_angle = 0.0
        jitter_radius = 1.0
        
        if irregularity > 0:
            # Jitter angle: +/- 20% of step
            angle_noise = (random.random() - 0.5) * step_angle * irregularity * 0.8
            # Ensure monotonicity is preserved (simplified check)
            angle_rel += angle_noise
            
            # Jitter radius: +/- 15%
            rad_noise = (random.random() - 0.5) * 0.3 * irregularity
            jitter_radius = 1.0 + rad_noise
            
        final_bearing = (bearing + angle_rel) % 360
        final_radius = radius * jitter_radius
        
        w_lat, w_lon = _project_point(s_lat, s_lon, final_bearing, final_radius)
        theoretical_points.append((w_lat, w_lon))

    _demo_event(
        loop_demo_context,
        'skeleton_projected',
        start=_round_coord_pair(s_lat, s_lon),
        points=[_round_coord_pair(lat, lon) for lat, lon in theoretical_points],
        bearing=round(float(bearing), 3),
        num_vertices=int(num_vertices),
    )

    # 4. Snap Waypoints with Flow Awareness
    # We need to know previous and next points to penalize U-turns.
    # Sequence: Start -> W1 -> W2 ... -> Wn -> Start
    
    # We snap W_i using:
    #   prev_point = snapped W_{i-1} (or Start)
    #   target_point = theoretical W_i
    #   next_point = theoretical W_{i+1} (or Start)
    
    prev_node = start_node
    # We need coords of prev_node for angle calc
    prev_coords = _node_coords(graph, start_node) 
    snapped_points = []
    
    for i in range(num_waypoints):
        w_lat, w_lon = theoretical_points[i]
        
        # Determine next point (theoretical)
        if i < num_waypoints - 1:
            next_coords = theoretical_points[i+1]
        else:
            # Last waypoint goes back to start
            next_coords = (s_lat, s_lon)
            
        # Smart Snap with Flow Awareness
        w_node = _smart_snap(
            graph, w_lat, w_lon, 
            prev_point=prev_coords, 
            next_point=next_coords
        )
        
        if w_node is None or w_node == start_node or w_node == prev_node:
            print(f"[GeometricSolver]   [FAILED] Waypoint {i+1} snap failed or duplicate")
            _demo_event(
                loop_demo_context,
                'waypoint_snap_failed',
                waypoint_index=i + 1,
                bearing=round(float(bearing), 3),
                target_point=_round_coord_pair(w_lat, w_lon),
            )
            return None
            
        waypoints_data.append(w_node)
        prev_node = w_node
        prev_coords = _node_coords(graph, w_node)
        snapped_points.append(_round_coord_pair(prev_coords[0], prev_coords[1]))
        
    # Check if waypoints are unique
    if len(set(waypoints_data)) != len(waypoints_data):
         print(f"[GeometricSolver]   [FAILED] Duplicate waypoints in shape")
         _demo_event(
             loop_demo_context,
             'waypoint_snap_failed',
             bearing=round(float(bearing), 3),
             reason='duplicate_waypoints',
         )
         return None

    _demo_event(
        loop_demo_context,
        'skeleton_snapped',
        points=snapped_points,
        bearing=round(float(bearing), 3),
    )

    # 5. Route Legs
    # Sequence: Start -> W1 -> W2 ... -> Wn -> Start
    full_route = []
    total_dist = 0.0
    total_cost = 0.0
    
    # Points sequence including start/end
    sequence = [start_node] + waypoints_data + [start_node]
    
    print(f"[GeometricSolver]   Routing {len(sequence)-1} legs: {sequence}")
    
    # Route sequentially
    # Enhancement: We could try "Critical Step First" (Bridge) logic for Polygons too,
    # but sequential is simpler for N-points.
    # For N=3 (Triangle), critical is W1-W2.
    # For N=4 (Quad), critical might be W1-W2 or W2-W3.
    # Let's stick to sequential for now to support generic N.
    
    # Validation: Check air-distance feasibility before routing?
    # Skipping for now to keep it simple.
    
    legs_routed = 0
    total_legs = len(sequence) - 1
    
    for i in range(len(sequence) - 1):
        u = sequence[i]
        v = sequence[i+1]
        
        leg_res = _route_leg(graph, u, v, weights, combine_nature, length_range,
                             prefer_dedicated_pavements=prefer_dedicated_pavements,
                             prefer_nature_trails=prefer_nature_trails,
                             prefer_paved=prefer_paved,
                             prefer_lit=prefer_lit, heavily_avoid_unlit=heavily_avoid_unlit,
                             avoid_unsafe_roads=avoid_unsafe_roads,
                             activity=activity,
                             lighting_context=lighting_context)
        if leg_res is None:
            print(f"[GeometricSolver]   [FAILED] Leg {i+1} ({u}->{v}) failed")
            _demo_event(
                loop_demo_context,
                'leg_failed',
                leg_index=i + 1,
                bearing=round(float(bearing), 3),
            )
            return None
            
        l_path, l_dist, l_cost = leg_res
        
        # Check for excessive detour on this leg (bridge leg check logic)
        u_c = _node_coords(graph, u)
        v_c = _node_coords(graph, v)
        air_d = _haversine(u_c[0], u_c[1], v_c[0], v_c[1])
        if air_d > 0 and l_dist > BRIDGE_LEG_DETOUR_FACTOR * air_d:
             print(f"[GeometricSolver]   [FAILED] Leg {i+1} detour too high ({l_dist/air_d:.1f}x)")
             _demo_event(
                 loop_demo_context,
                 'leg_failed',
                 leg_index=i + 1,
                 bearing=round(float(bearing), 3),
                 reason='detour_factor_exceeded',
                 detour_factor=round(float(l_dist / air_d), 3),
             )
             return None

        _demo_event(
            loop_demo_context,
            'leg_routed',
            leg_index=i + 1,
            total_legs=total_legs,
            bearing=round(float(bearing), 3),
            num_vertices=int(num_vertices),
            path=_sample_route_coords(graph, l_path),
            leg_distance_m=round(float(l_dist), 2),
            scenic_cost=round(float(l_cost), 4),
        )
             
        if i == 0:
            full_route.extend(l_path)
        else:
            full_route.extend(l_path[1:]) # Skip duplicate join node
            
        total_dist += l_dist
        total_cost += l_cost
        legs_routed += 1
        
    print(f"[GeometricSolver]   [SUCCESS] Polygon complete: {total_dist:.0f}m, cost={total_cost:.4f}")
    _demo_event(
        loop_demo_context,
        'polygon_attempt_completed',
        bearing=round(float(bearing), 3),
        total_distance_m=round(float(total_dist), 2),
        scenic_cost=round(float(total_cost), 4),
    )
    return (full_route, total_dist, total_cost, tau)


def _try_out_and_back(
    graph,
    start_node: int,
    target_distance: float,
    weights: Dict[str, float],
    combine_nature: bool,
    bearing: float,
    tau: float,
    length_range: Tuple[float, float],
    prefer_dedicated_pavements: bool = False,
    prefer_nature_trails: bool = False,
    prefer_paved: bool = False,
    prefer_lit: bool = False,
    avoid_unsafe_roads: bool = False,
    heavily_avoid_unlit: bool = False,
    activity: str = 'walking',
    lighting_context: str = 'night',
    loop_demo_context=None,
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

    _demo_event(
        loop_demo_context,
        'fallback_out_and_back_started',
        bearing=round(float(bearing), 3),
        tau=round(float(tau), 6),
        projected_distance_m=round(float(half_dist), 2),
    )

    print(f"[GeometricSolver]   Projecting waypoint at {half_dist:.0f}m")
    w_lat, w_lon = _project_point(s_lat, s_lon, bearing, half_dist)
    _demo_event(
        loop_demo_context,
        'fallback_waypoint_projected',
        waypoint=_round_coord_pair(w_lat, w_lon),
        start=_round_coord_pair(s_lat, s_lon),
    )
    w_node = _smart_snap(graph, w_lat, w_lon)

    if w_node is None or w_node == start_node:
        print(f"[GeometricSolver]   [FAILED] Out-and-back snap failed or degenerate")
        _demo_event(loop_demo_context, 'fallback_out_and_back_failed', reason='snap_failed')
        return None

    print(f"[GeometricSolver]   Snapped to W={w_node}")

    if not (_are_reachable(graph, start_node, w_node)
            and _are_reachable(graph, w_node, start_node)):
        print(f"[GeometricSolver]   [FAILED] Out-and-back reachability failed")
        _demo_event(loop_demo_context, 'fallback_out_and_back_failed', reason='reachability_failed')
        return None

    print(f"[GeometricSolver]   -> Routing outbound leg: S->W")
    leg_out = _route_leg(graph, start_node, w_node, weights,
                         combine_nature, length_range,
                         prefer_dedicated_pavements=prefer_dedicated_pavements,
                         prefer_nature_trails=prefer_nature_trails,
                         prefer_paved=prefer_paved,
                         prefer_lit=prefer_lit, heavily_avoid_unlit=heavily_avoid_unlit,
                         avoid_unsafe_roads=avoid_unsafe_roads,
                         activity=activity,
                         lighting_context=lighting_context)
    if leg_out is None:
        print(f"[GeometricSolver]   [FAILED] Outbound leg failed")
        _demo_event(loop_demo_context, 'fallback_out_and_back_failed', reason='outbound_failed')
        return None

    print(f"[GeometricSolver]   -> Routing return leg: W->S")
    leg_back = _route_leg(graph, w_node, start_node, weights,
                          combine_nature, length_range,
                          prefer_dedicated_pavements=prefer_dedicated_pavements,
                          prefer_nature_trails=prefer_nature_trails,
                          prefer_paved=prefer_paved,
                          prefer_lit=prefer_lit, heavily_avoid_unlit=heavily_avoid_unlit,
                          avoid_unsafe_roads=avoid_unsafe_roads,
                          activity=activity,
                          lighting_context=lighting_context)
    if leg_back is None:
        print(f"[GeometricSolver]   [FAILED] Return leg failed")
        _demo_event(loop_demo_context, 'fallback_out_and_back_failed', reason='return_failed')
        return None

    path_out, dist_out, cost_out = leg_out
    path_back, dist_back, cost_back = leg_back

    _demo_event(
        loop_demo_context,
        'fallback_leg_routed',
        leg_index=1,
        total_legs=2,
        bearing=round(float(bearing), 3),
        direction='outbound',
        path=_sample_route_coords(graph, path_out),
        leg_distance_m=round(float(dist_out), 2),
        scenic_cost=round(float(cost_out), 4),
    )
    _demo_event(
        loop_demo_context,
        'fallback_leg_routed',
        leg_index=2,
        total_legs=2,
        bearing=round(float(bearing), 3),
        direction='return',
        path=_sample_route_coords(graph, path_back),
        leg_distance_m=round(float(dist_back), 2),
        scenic_cost=round(float(cost_back), 4),
    )

    route = path_out + path_back[1:]
    total_distance = dist_out + dist_back
    total_cost = cost_out + cost_back
    print(f"[GeometricSolver]   [SUCCESS] Out-and-back complete: {len(route)} nodes, "
          f"{total_distance:.0f}m, scenic_cost={total_cost:.4f}")
    _demo_event(
        loop_demo_context,
        'fallback_out_and_back_completed',
        total_distance_m=round(float(total_distance), 2),
        scenic_cost=round(float(total_cost), 4),
    )
    return (route, total_distance, total_cost)


def _prune_spurs(path: List[int]) -> List[int]:
    """
    Removes 'A -> B -> A' artifacts from a path list.
    Repeats until no spurs remain (handling nested spurs).
    """
    clean_path = list(path)
    changed = True
    
    while changed:
        changed = False
        i = 0
        while i < len(clean_path) - 2:
            # Check for A -> B -> A pattern
            if clean_path[i] == clean_path[i+2]:
                # Remove the spur (B and the return A)
                del clean_path[i+1:i+3] 
                changed = True
            else:
                i += 1
                
    return clean_path


# ══════════════════════════════════════════════════════════════════════════════
# GeometricLoopSolver
# ══════════════════════════════════════════════════════════════════════════════

def _prune_spurs(path: List[int]) -> List[int]:
    """
    Removes 'A -> B -> A' artifacts from a path list.
    Repeats until no spurs remain (handling nested spurs).
    """
    clean_path = list(path)
    changed = True
    
    while changed:
        changed = False
        i = 0
        while i < len(clean_path) - 2:
            # Check for A -> B -> A pattern
            if clean_path[i] == clean_path[i+2]:
                # Remove the spur (B and the return A)
                del clean_path[i+1:i+3] 
                changed = True
            else:
                i += 1
                
    return clean_path


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
        prefer_dedicated_pavements: bool = False,
        prefer_nature_trails: bool = False,
        prefer_paved: bool = False,
        prefer_lit: bool = False,
        avoid_unsafe_roads: bool = False,
        use_smart_bearing: bool = False,
        heavily_avoid_unlit: bool = False,
        activity: str = 'walking',
        lighting_context: str = 'night',
        loop_demo_context=None,
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

        if loop_demo_context is not None:
            loop_demo_context.setdefault('schema_version', _LOOP_DEMO_SCHEMA_VERSION)
            loop_demo_context.setdefault('frames', [])
            loop_demo_context.setdefault('max_frames', _LOOP_DEMO_DEFAULT_MAX_FRAMES)
            loop_demo_context.setdefault('truncated', False)

            start_lat, start_lon = _node_coords(graph, start_node)
            _demo_event(
                loop_demo_context,
                'solver_started',
                start=_round_coord_pair(start_lat, start_lon),
                target_distance_m=round(float(target_distance), 2),
                directional_bias=str(directional_bias),
                variety_level=int(variety_level),
            )

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
        print(f"[GeometricSolver] Smart Bearing: {use_smart_bearing}")
        lit_mode = 'heavily_avoid_unlit' if heavily_avoid_unlit else ('prefer_lit' if prefer_lit else 'off')
        print(f"[GeometricSolver] Lit mode: {lit_mode}")
        print(f"[GeometricSolver] ======================================================\n")

        # ── Determine rotation bearings ──────────────────────────────────
        base_bearing = _BIAS_TO_BEARING.get(directional_bias.lower())

        # Number of candidate attempts — more variety = more attempts
        num_attempts = max(num_candidates + 1, 3 + variety_level)
        rotation_step = 360.0 / num_attempts

        if base_bearing is not None:
            # User requested a direction: start from that bearing
            raw_bearings = [
                (base_bearing + i * rotation_step) % 360
                for i in range(num_attempts)
            ]
        elif use_smart_bearing:
            # Smart Bearing Strategy
            # Analyze sectors to find top scenic directions
            # Radius: roughly half the target dist (to reach the 'tip' of the loop)
            scan_radius = target_distance / 2.0
            print(f"[GeometricSolver] Scanning for scenic sectors (radius={scan_radius:.0f}m)...")
            
            scenic_sectors = _analyze_scenic_sectors(graph, start_node, scan_radius)
            
            if not scenic_sectors or sum(s for _, s in scenic_sectors) == 0:
                 print("[GeometricSolver] No scenic data found, falling back to equidistant.")
                 raw_bearings = [(i * rotation_step) % 360 for i in range(num_attempts)]
            else:
                 # Pick top N distinct sectors
                 # We want to avoid picking two bearing that are too close (e.g. 15 and 45)
                 # unless we really need more candidates.
                 selected_bearings = []
                 min_sep = 45.0 # Min separation degrees
                 
                 for b, score in scenic_sectors:
                     if len(selected_bearings) >= num_attempts:
                         break
                     
                     # Check separation
                     is_distinct = True
                     for existing in selected_bearings:
                         diff = abs(b - existing)
                         diff = min(diff, 360 - diff)
                         if diff < min_sep:
                             is_distinct = False
                             break
                     
                     if is_distinct:
                         selected_bearings.append(b)
                
                 # Fill remaining slots with standard rotations if needed (to ensure we have enough candidates)
                 # Or just loop the best ones with offsets?
                 # Let's just fill with equidistant if we strictly need N attempts, 
                 # but usually fewer GOOD candidates is better than many BAD ones.
                 # However, the loop logic expects 'num_attempts'.
                 
                 while len(selected_bearings) < num_attempts:
                     # Add a fallback bearing (e.g. 0, 90, 180...) that isn't covered
                     for angle in [0, 90, 180, 270]:
                         is_distinct = True
                         for existing in selected_bearings:
                             diff = abs(angle - existing)
                             diff = min(diff, 360 - diff)
                             if diff < min_sep:
                                 is_distinct = False
                                 break
                         if is_distinct:
                             selected_bearings.append(angle)
                             if len(selected_bearings) >= num_attempts:
                                 break
                     # If still stuck, just force random generic ones
                     if len(selected_bearings) < num_attempts:
                         selected_bearings.append( (len(selected_bearings) * rotation_step) % 360 )
                 
                 raw_bearings = selected_bearings[:num_attempts]
                 print(f"[GeometricSolver] Smart Bearings selected: {raw_bearings}")

        else:
            # No bias: use equidistant bearings starting from 0°
            raw_bearings = [
                (i * rotation_step) % 360
                for i in range(num_attempts)
            ]

        _demo_event(
            loop_demo_context,
            'bearings_selected',
            bearings=[round(float(b), 3) for b in raw_bearings],
            target_distance_m=round(float(target_distance), 2),
            use_smart_bearing=bool(use_smart_bearing),
        )
        
        # Define candidate configurations: (num_vertices, arc_angle, irregularity)
        # We generate a mix of shapes for each bearing.
        # N=3: Triangle (stable)
        # N=4: Quad (wider)
        # N=5: Pentagon (organic, rounded)
        
        configs = []
        # Basic Triangle (Stable)
        configs.append({'n': 3, 'arc': 90.0, 'irr': 0.05, 'tau': DEFAULT_TAU})
        
        if variety_level >= 1:
            # Irregular Quad
            configs.append({'n': 4, 'arc': 110.0, 'irr': 0.15, 'tau': DEFAULT_TAU * 1.05})
            
        if variety_level >= 2:
            # High-irregularity Pentagon
            configs.append({'n': 5, 'arc': 130.0, 'irr': 0.25, 'tau': DEFAULT_TAU * 1.1})
            
        # Ensure we have enough configs if variety is low but num_candidates is high
        # Cycle through configs if needed, or add variations
        while len(configs) < 1:
             configs.append({'n': 3, 'arc': 90.0, 'irr': 0.0, 'tau': DEFAULT_TAU})

        all_candidates: List[Tuple[List[int], float, float]] = []

        for idx, bearing in enumerate(raw_bearings):
            elapsed = time.time() - t0
            if elapsed > max_search_time:
                print(f"\n[GeometricSolver] [TIME LIMIT] Reached ({elapsed:.1f}s > {max_search_time}s)")
                break

            # For each bearing, try the enabled shape configurations
            # We limit attempts per bearing to avoid explosion
            # If variety is high, we might try multiple shapes per bearing.
            # Logic: Try config 0. If it fails or we need variety, try config 1.
            
            # Simple approach: Alternate configs based on bearing index?
            # Or try all valid configs for this bearing?
            # Let's try up to 2 configs per bearing to get variety.
            
            bearing_configs = configs[:2] # Try max 2 shapes per bearing to save time
            
            for cfg in bearing_configs:
                n_verts = cfg['n']
                tau = cfg['tau']

                _demo_event(
                    loop_demo_context,
                    'shape_attempt_started',
                    bearing=round(float(bearing), 3),
                    shape_sides=int(n_verts),
                    arc_angle=round(float(cfg['arc']), 3),
                    tau=round(float(tau), 6),
                )
                
                print(f"\n[GeometricSolver] ------------------------------------------------")
                print(f"[GeometricSolver] Bearing {bearing:.0f}° | Shape N={n_verts} (elapsed: {elapsed:.1f}s)")
                print(f"[GeometricSolver] ------------------------------------------------")

                shape_success = False

                # ── Clamped proportional feedback loop ───────────────────
                for retry in range(MAX_FEEDBACK_RETRIES):
                    if time.time() - t0 > max_search_time:
                        break

                    _demo_event(
                        loop_demo_context,
                        'retry_started',
                        bearing=round(float(bearing), 3),
                        shape_sides=int(n_verts),
                        retry=int(retry),
                        tau=round(float(tau), 6),
                    )

                    result = _try_polygon(
                        graph, start_node, target_distance, weights,
                        combine_nature, bearing, tau, length_range,
                        num_vertices=n_verts,
                        arc_angle=cfg['arc'],
                        irregularity=cfg['irr'],
                        prefer_dedicated_pavements=prefer_dedicated_pavements,
                        prefer_nature_trails=prefer_nature_trails,
                        prefer_paved=prefer_paved,
                        prefer_lit=prefer_lit,
                        avoid_unsafe_roads=avoid_unsafe_roads,
                        heavily_avoid_unlit=heavily_avoid_unlit,
                        activity=activity,
                        lighting_context=lighting_context,
                        loop_demo_context=loop_demo_context,
                    )

                    if result is None:
                        # Shape construction failed entirely -- no feedback
                        print(f"[GeometricSolver]   [FAILED] Retry {retry}: shape construction failed")
                        _demo_event(
                            loop_demo_context,
                            'shape_attempt_failed',
                            bearing=round(float(bearing), 3),
                            shape_sides=int(n_verts),
                            retry=int(retry),
                            reason='shape_construction_failed',
                        )
                        break

                    route, actual_dist, scenic_cost, _ = result

                    # ── PRUNE SPURS & RECALCULATE ────────────────────────
                    # Remove A->B->A artifacts immediately so we check the
                    # TRUE distance against the tolerance.
                    # ─────────────────────────────────────────────────────
                    route = _prune_spurs(route)
                    
                    # If route collapsed (e.g. was entirely a spur), fail this attempt
                    if len(route) < 3: 
                        print(f"[GeometricSolver]   [REJECT] Route collapsed after pruning")
                        # Force feedback to grow
                        actual_dist = 0 
                    else:
                        # Recalculate stats for the clean route
                        actual_dist, scenic_cost = _recalculate_route_stats(
                            graph, route, weights, combine_nature, length_range
                        )

                    # -- Check asymmetric tolerance -------------------
                    frac = (actual_dist - target_distance) / target_distance
                    deviation_pct = frac * 100
                    print(f"[GeometricSolver]   Distance check (clean): {actual_dist:.0f}m "
                          f"(target: {target_distance:.0f}m, deviation: {deviation_pct:+.1f}%)")

                    _demo_event(
                        loop_demo_context,
                        'distance_evaluated',
                        bearing=round(float(bearing), 3),
                        shape_sides=int(n_verts),
                        retry=int(retry),
                        actual_distance_m=round(float(actual_dist), 2),
                        target_distance_m=round(float(target_distance), 2),
                        deviation_percent=round(float(deviation_pct), 3),
                    )
                    
                    if -TOLERANCE_UNDER <= frac <= TOLERANCE_OVER:
                        # Success!
                        all_candidates.append((
                            route, actual_dist, scenic_cost, 
                            {'bearing': bearing, 'shape': f"N={n_verts}", 'tau': tau}
                        ))
                        _demo_event(
                            loop_demo_context,
                            'candidate_accepted',
                            bearing=round(float(bearing), 3),
                            shape_sides=int(n_verts),
                            retry=int(retry),
                            actual_distance_m=round(float(actual_dist), 2),
                            scenic_cost=round(float(scenic_cost), 4),
                        )
                        shape_success = True
                        break # Break retry loop

                    # -- Clamped update --------------------------------
                    if target_distance > 0:
                        tau_before = tau
                        raw_ratio = actual_dist / target_distance
                        clamped_ratio = max(
                            TAU_CLAMP_LOW,
                            min(TAU_CLAMP_HIGH, raw_ratio),
                        )
                        tau_new = tau * clamped_ratio
                        print(f"[GeometricSolver]   Tau adjustment: {tau:.3f} -> {tau_new:.3f}")
                        _demo_event(
                            loop_demo_context,
                            'tau_adjusted',
                            bearing=round(float(bearing), 3),
                            shape_sides=int(n_verts),
                            retry=int(retry),
                            tau_before=round(float(tau_before), 6),
                            tau_after=round(float(tau_new), 6),
                            clamp_ratio=round(float(clamped_ratio), 6),
                        )
                        tau = tau_new
                    else:
                        break

                if shape_success:
                    # Found a valid shape for this bearing
                    break # Stop trying other shapes for this bearing (e.g. don't try Quad if Tri worked)

            # -- Fallback: out-and-back if NO shapes worked for this bearing ------------
            if not shape_success:
                if time.time() - t0 > max_search_time:
                    print(f"[GeometricSolver]   [SKIP] Skipping fallback (time limit)")
                    continue
                    
                print(f"\n[GeometricSolver]   [WARNING] All polygon attempts failed for bearing {bearing:.0f}°, trying out-and-back...")
                _demo_event(
                    loop_demo_context,
                    'fallback_started',
                    bearing=round(float(bearing), 3),
                )
                oab = _try_out_and_back(
                    graph, start_node, target_distance, weights,
                    combine_nature, bearing, DEFAULT_TAU, length_range,
                    prefer_dedicated_pavements=prefer_dedicated_pavements,
                    prefer_nature_trails=prefer_nature_trails,
                    prefer_paved=prefer_paved,
                    prefer_lit=prefer_lit,
                    avoid_unsafe_roads=avoid_unsafe_roads,
                    heavily_avoid_unlit=heavily_avoid_unlit,
                    activity=activity,
                    lighting_context=lighting_context,
                    loop_demo_context=loop_demo_context,
                )
                if oab is not None:
                    route_oab, dist_oab, cost_oab = oab
                    
                    # ── PRUNE SPURS & RECALCULATE ────────────────────────
                    route_oab = _prune_spurs(route_oab)
                    if len(route_oab) >= 3:
                         dist_oab, cost_oab = _recalculate_route_stats(
                            graph, route_oab, weights, combine_nature, length_range
                        )
                    else:
                        dist_oab = 0
                    # ─────────────────────────────────────────────────────

                    frac_oab = (dist_oab - target_distance) / target_distance
                    deviation_oab_pct = frac_oab * 100
                    print(f"[GeometricSolver]   Out-and-back check (clean): {dist_oab:.0f}m "
                          f"({deviation_oab_pct:+.1f}%), tolerance=+/-{distance_tolerance*100:.0f}%")
                    
                    if abs(frac_oab) <= distance_tolerance:
                        all_candidates.append((
                            route_oab, dist_oab, cost_oab,
                            {'bearing': bearing, 'type': 'out-and-back'}
                        ))
                        _demo_event(
                            loop_demo_context,
                            'fallback_accepted',
                            bearing=round(float(bearing), 3),
                            actual_distance_m=round(float(dist_oab), 2),
                            scenic_cost=round(float(cost_oab), 4),
                        )
                        print(f"[GeometricSolver]   [SUCCESS] Out-and-back ACCEPTED: "
                              f"{dist_oab:.0f}m ({deviation_oab_pct:+.1f}%)")
                    else:
                        _demo_event(
                            loop_demo_context,
                            'fallback_rejected',
                            bearing=round(float(bearing), 3),
                            deviation_percent=round(float(deviation_oab_pct), 3),
                        )
                        print(f"[GeometricSolver]   [FAILED] Out-and-back outside tolerance")

        # -- Convert to LoopCandidates ------------------------------------
        elapsed = time.time() - t0
        print(f"\n[GeometricSolver] ======================================================")
        print(f"[GeometricSolver] Search complete: {len(all_candidates)} raw candidates found")
        print(f"[GeometricSolver] Total time: {elapsed:.1f}s")
        print(f"[GeometricSolver] ======================================================\n")
        
        if not all_candidates:
            print(f"[GeometricSolver] [FAILED] No viable loops found")
            _demo_event(
                loop_demo_context,
                'solver_completed',
                elapsed_seconds=round(float(elapsed), 3),
                raw_candidates=0,
                returned_candidates=0,
                labels=[],
            )
            return []

        max_cost = max(c for _, _, c, _ in all_candidates) if all_candidates else 1.0
        max_cost = max(max_cost, 0.001)
        print(f"[GeometricSolver] Max scenic cost (for normalization): {max_cost:.4f}")

        candidates: List[LoopCandidate] = []
        for route, distance, scenic_cost, meta in all_candidates:
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
                    **meta,
                    'directional_bias': directional_bias,
                    'variety_level': variety_level,
                    'use_smart_bearing': use_smart_bearing,
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

        _demo_event(
            loop_demo_context,
            'solver_completed',
            elapsed_seconds=round(float(elapsed), 3),
            raw_candidates=int(len(all_candidates)),
            returned_candidates=int(len(result)),
            labels=[candidate.label for candidate in result],
        )

        return result
