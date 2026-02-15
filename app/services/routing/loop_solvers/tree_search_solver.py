"""
Tree-Search Loop Solver 


Key Design:
    - **Tree search**: each frontier entry carries its full path — no
      g-score merging.  Multiple paths to the same node coexist, enabling
      many diverse loop closures from a single search run.
    - **Equirectangular distance**: distance is computed as straight-line
      between consecutive nodes (matching RS's ``_calculateDistance``),
      NOT from edge length attributes.  This matches how OTHER ALG
      works — it never reads edge/way length data.
    - **Simple heuristic**: h = max(remaining_target, dist_to_start).
      No phase transitions or blending — naturally pushes outward early
      and pulls homeward late.
    - **Minimal pruning**: only physical feasibility checks (too long,
      too deep, can't return, U-turn).  No exploration / way-name /
      turn-angle penalties inflating the cost.
    - **Post-hoc deduplication**: grid-cell Jaccard similarity suppresses
      routes >85% overlapping with already-found loops.
    - **Single search run**: 500K iterations, 300s timeout, max 10
      routes (all matching RS's ``search(500000, 300000)``).
    - **Pipeline**: crop → filter (Oe) → cluster (Ee) → simplify (Ae) → prune dead-ends (Ie) →
      search → expand → score → select.

Penalty terms are kept light and directly proportional to
``target_distance``, so they never dominate.
"""

import heapq
import math
import time
from typing import Dict, FrozenSet, List, Optional, Set, Tuple

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

def _node_coords(graph, node) -> Tuple[float, float]:
    """Return (lat, lon) for a graph node."""
    d = graph.nodes[node]
    return (d.get('y', d.get('lat', 0.0)), d.get('x', d.get('lon', 0.0)))


def _equirectangular_dist(
    lat1: float, lon1: float, lat2: float, lon2: float, lat_cos: float,
) -> float:
    """Fast equirectangular distance in metres (same formula as OTHER ALG)."""
    R = 6_371_000
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1) * lat_cos
    return R * math.sqrt(dlon * dlon + dlat * dlat)


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """
    Flat-earth bearing 0-360 — exact port of OTHER ALG's P() function.

    Uses cos((lat1+lat2)/2) for the longitude scaling, matching RS exactly.
    RS's _calculateDistance uses cos(startLat), but P() uses cos(avgLat).
    """
    avg_lat_rad = math.radians((lat1 + lat2) / 2.0)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1) * math.cos(avg_lat_rad)
    deg = math.degrees(math.atan2(dlon, dlat))
    return (deg + 360.0) % 360.0


def _bearing_diff(a: float, b: float) -> float:
    """Signed difference b - a in [-180, 180]."""
    d = (b - a + 360.0) % 360.0
    if d > 180.0:
        d -= 360.0
    return d


# Road-type penalty lookup (same values as OTHER ALG's ce() function)
_HIGHWAY_PENALTY: Dict[str, float] = {
    'footway': 0, 'path': 0, 'pedestrian': 0, 'cycleway': 0,
    'track': 1, 'living_street': 1, 'residential': 1, 'service': 1,
    'unclassified': 2, 'tertiary': 3, 'tertiary_link': 3,
    'secondary': 4, 'secondary_link': 4,
    'primary': 6, 'primary_link': 6,
    'trunk': 8, 'trunk_link': 8,
    'motorway': 10, 'motorway_link': 10,
}
_HIGHWAY_DEFAULT: float = 5


def _edge_highway_penalty(graph, n1: int, n2: int) -> float:
    """Get the OTHER ALG-style highway penalty score for the edge."""
    edges = graph.get_edge_data(n1, n2)
    if not edges:
        return _HIGHWAY_DEFAULT
    best = _HIGHWAY_DEFAULT
    for data in edges.values():
        tag = data.get('highway')
        if isinstance(tag, list):
            tag = tag[0] if tag else None
        if tag is None:
            continue
        penalty = _HIGHWAY_PENALTY.get(str(tag).lower(), _HIGHWAY_DEFAULT)
        if penalty < best:
            best = penalty
    return best


def _get_edge_length(graph, n1: int, n2: int) -> float:
    """Get minimum physical length of edges between n1 and n2."""
    edge_data = graph.get_edge_data(n1, n2)
    if not edge_data:
        return float('inf')
    best = float('inf')
    for d in edge_data.values():
        length = d.get('length', float('inf'))
        if length < best:
            best = length
    return best


def _get_edge_name(graph, n1: int, n2: int) -> Optional[str]:
    """Return the 'name' tag for the shortest edge between n1 and n2."""
    edges = graph.get_edge_data(n1, n2)
    if not edges:
        return None
    best_length = float('inf')
    best_name = None
    for data in edges.values():
        length = data.get('length', float('inf'))
        if length < best_length:
            best_length = length
            name = data.get('name')
            if isinstance(name, list):
                name = name[0] if name else None
            best_name = name
    return best_name


def _get_edge_highway(graph, n1: int, n2: int) -> Optional[str]:
    """Return the highway tag for the shortest edge between n1 and n2."""
    edges = graph.get_edge_data(n1, n2)
    if not edges:
        return None
    best_length = float('inf')
    best_hw = None
    for data in edges.values():
        length = data.get('length', float('inf'))
        if length < best_length:
            best_length = length
            hw = data.get('highway')
            if isinstance(hw, list):
                hw = hw[0] if hw else None
            best_hw = hw
    return best_hw


# ── Grid-cell deduplicator (OTHER ALG's de class) ─────────────────────────

class _RouteDeduplicator:
    """
    Spatial grid-cell deduplication — port of OTHER ALG ``de``.

    Divides the map into cells of ``grid_size`` degrees.  Each route is
    fingerprinted by the set of grid cells its nodes occupy.  Two routes
    with Jaccard similarity > ``threshold`` are considered duplicates.
    """

    def __init__(self, grid_size: float = 0.00045):
        self._grid_size = grid_size
        self._fingerprints: List[FrozenSet[Tuple[int, int]]] = []
        self.duplicates_found = 0
        self.total_checked = 0

    def _fingerprint(self, route: List[int], graph) -> FrozenSet[Tuple[int, int]]:
        cells: Set[Tuple[int, int]] = set()
        for node in route:
            lat, lon = _node_coords(graph, node)
            cells.add((
                int(lat // self._grid_size),
                int(lon // self._grid_size),
            ))
        return frozenset(cells)

    @staticmethod
    def _jaccard(a: FrozenSet, b: FrozenSet) -> float:
        if not a and not b:
            return 0.0
        return len(a & b) / len(a | b)

    def is_duplicate(
        self, route: List[int], graph, threshold: float = 0.85,
    ) -> bool:
        self.total_checked += 1
        fp = self._fingerprint(route, graph)
        for existing in self._fingerprints:
            if self._jaccard(fp, existing) > threshold:
                self.duplicates_found += 1
                return True
        self._fingerprints.append(fp)
        return False


# ── Route state (lightweight — mirrors OTHER ALG's z class) ───────────────

class _RouteState:
    """
    Mutable route state carried by each frontier entry.

    Tracks the same metrics as OTHER ALG's ``z`` class:
    path, distance, bearing, turn count, bearing change totals,
    way-name changes, way-type changes, highway-type penalty score.

    ``clone()`` makes a shallow copy for branching in the tree search.
    """

    __slots__ = (
        'path', 'path_set', 'distance', 'previous_bearing',
        'current_bearing', 'turn_count', 'total_bearing_change',
        'unsigned_bearing_change', 'way_name_changes', 'way_type_changes',
        'highway_penalty_score', 'current_way_name', 'current_highway',
        'start_node', 'lat_cos',
    )

    def __init__(self, start_node: int, lat_cos: float):
        self.path: List[int] = [start_node]
        self.path_set: Set[int] = {start_node}
        self.distance: float = 0.0
        self.previous_bearing: Optional[float] = None
        self.current_bearing: Optional[float] = None
        self.turn_count: int = 0
        self.total_bearing_change: float = 0.0
        self.unsigned_bearing_change: float = 0.0
        self.way_name_changes: int = 0
        self.way_type_changes: int = 0
        self.highway_penalty_score: float = 0.0
        self.current_way_name: Optional[str] = None
        self.current_highway: Optional[str] = None
        self.start_node: int = start_node
        self.lat_cos: float = lat_cos

    @property
    def current_node(self) -> int:
        return self.path[-1]

    @property
    def depth(self) -> int:
        return len(self.path)

    def push_node(
        self, node: int,
        node_lat: float, node_lon: float,
        graph,
    ) -> None:
        """Append *node* and update all tracked metrics.

        CRITICAL: Distance is computed via equirectangular formula
        between consecutive nodes (matching RS's _calculateDistance),
        NOT from edge length attributes.  This is how OTHER ALG
        works — it never reads edge/way length data.
        """
        prev = self.path[-1]
        prev_lat, prev_lon = _node_coords(graph, prev)

        # Distance — equirectangular between prev and node (matching RS)
        seg_dist = _equirectangular_dist(
            prev_lat, prev_lon, node_lat, node_lon, self.lat_cos,
        )
        self.distance += seg_dist

        # Way name / type changes
        edge_name = _get_edge_name(graph, prev, node)
        edge_highway = _get_edge_highway(graph, prev, node)

        if self.current_way_name is not None and edge_name is not None:
            if edge_name != self.current_way_name:
                self.way_name_changes += 1

        if self.current_highway is not None and edge_highway is not None:
            if edge_highway != self.current_highway:
                self.way_type_changes += 1

        self.current_way_name = edge_name
        self.current_highway = edge_highway

        # Highway-type penalty (distance-weighted, as OTHER ALG does)
        hw_penalty = _edge_highway_penalty(graph, prev, node)
        self.highway_penalty_score += hw_penalty * seg_dist

        # Bearing (reusing prev_lat/prev_lon from above)
        # RS's P() uses cos(avgLat), not cos(startLat)
        new_bearing = _bearing(prev_lat, prev_lon, node_lat, node_lon)

        if self.current_bearing is not None:
            diff = _bearing_diff(self.current_bearing, new_bearing)
            abs_diff = abs(diff)
            if abs_diff > 60:
                self.turn_count += 1
            self.total_bearing_change += diff
            if abs_diff > 20:       # MINIMUM_BEARING_CHANGE_TO_COUNT
                self.unsigned_bearing_change += abs_diff

        self.previous_bearing = self.current_bearing
        self.current_bearing = new_bearing

        # Path
        self.path.append(node)
        self.path_set.add(node)

    def clone(self) -> '_RouteState':
        """Shallow copy for tree-search branching."""
        rs = _RouteState.__new__(_RouteState)
        rs.path = self.path.copy()
        rs.path_set = self.path_set.copy()
        rs.distance = self.distance
        rs.previous_bearing = self.previous_bearing
        rs.current_bearing = self.current_bearing
        rs.turn_count = self.turn_count
        rs.total_bearing_change = self.total_bearing_change
        rs.unsigned_bearing_change = self.unsigned_bearing_change
        rs.way_name_changes = self.way_name_changes
        rs.way_type_changes = self.way_type_changes
        rs.highway_penalty_score = self.highway_penalty_score
        rs.current_way_name = self.current_way_name
        rs.current_highway = self.current_highway
        rs.start_node = self.start_node
        rs.lat_cos = self.lat_cos
        return rs


# ── Seeded RNG (OTHER ALG's LCG) ─────────────────────────────────────────

class _SeededRNG:
    """Linear congruential generator — exact match to OTHER ALG."""
    _MOD = 2 ** 32

    def __init__(self, seed: int):
        self._state = seed % self._MOD

    def random(self, lo: float = 0.0, hi: float = 1.0) -> float:
        self._state = (1664525 * self._state + 1013904223) % self._MOD
        t = self._state / self._MOD
        return lo + t * (hi - lo)


# ── Min-heap wrapper ─────────────────────────────────────────────────────────
# Python's heapq is already a min-heap.  We use a simple counter for tie-
# breaking to match OTHER ALG's insertion-order semantics.

_heap_counter = 0


def _heap_push(heap: list, f_score: float, state: _RouteState) -> None:
    global _heap_counter
    heapq.heappush(heap, (f_score, _heap_counter, state))
    _heap_counter += 1


def _heap_pop(heap: list) -> Tuple[float, _RouteState]:
    f, _cnt, state = heapq.heappop(heap)
    return f, state


def _heap_trim(heap: list, keep: int) -> list:
    """Keep only the *keep* lowest-f entries.  Returns new heap."""
    smallest = heapq.nsmallest(keep, heap)
    new_heap: list = []
    for item in smallest:
        heapq.heappush(new_heap, item)
    return new_heap


# ── Node-coord cache ─────────────────────────────────────────────────────────

def _build_coord_cache(graph) -> Dict[int, Tuple[float, float]]:
    """Pre-compute lat/lon for every node in the graph."""
    cache: Dict[int, Tuple[float, float]] = {}
    for node in graph.nodes():
        d = graph.nodes[node]
        cache[node] = (
            d.get('y', d.get('lat', 0.0)),
            d.get('x', d.get('lon', 0.0)),
        )
    return cache


# ── Neighbour cache ──────────────────────────────────────────────────────────

def _build_neighbour_cache(graph) -> Dict[int, List[int]]:
    """
    Pre-compute undirected neighbour list for every node.

    Uses successors ∪ predecessors to match OTHER ALG's bidirectional
    way-based neighbour finding (``getNeighbourNodes``).
    """
    cache: Dict[int, List[int]] = {}
    for node in graph.nodes():
        nbrs = set(graph.successors(node)) | set(graph.predecessors(node))
        cache[node] = list(nbrs)
    return cache


# ── Geographic crop (OTHER ALG's radius filtering) ────────────────────────

def _calculate_search_radius_km(target_km: float) -> float:
    """
    OTHER ALG's ``calculateSearchRadius`` — exact port.

    For a 5km route → 2.5 km radius.
    For a 10km route → 4.5 km radius.
    Clamped to [1.5, 5.0] km.
    """
    multiplier = 0.55 - target_km * 0.01
    radius = target_km * max(multiplier, 0.20)
    radius = max(radius, 1.5)
    radius = min(radius, 5.0)
    return radius


def _crop_to_radius(graph, start_node: int, radius_m: float):
    """
    Remove all nodes farther than *radius_m* metres (straight-line) from
    ``start_node``.  Mirrors OTHER ALG's geographic radius filter.

    This is the single most important preprocessing step: it reduces a
    city-wide tile (47K+ intersections) to a tight search area (~3-7K),
    matching the data size OTHER ALG works with.

    Returns a new graph; the original is never mutated.
    """
    s_lat, s_lon = _node_coords(graph, start_node)
    lat_cos = math.cos(math.radians(s_lat))

    remove = []
    for node in graph.nodes():
        if node == start_node:
            continue
        n_lat, n_lon = _node_coords(graph, node)
        dist = _equirectangular_dist(n_lat, n_lon, s_lat, s_lon, lat_cos)
        if dist > radius_m:
            remove.append(node)

    cropped = graph.copy()
    for node in remove:
        cropped.remove_node(node)

    print(f"[TreeSearch] Cropped to {radius_m/1000:.1f}km radius: "
          f"{graph.number_of_nodes()} → {cropped.number_of_nodes()} nodes")
    return cropped


# ── Road-type filter (OTHER ALG's Oe / Overpass exclusions) ───────────────

def _filter_road_types(graph, start_node: int):
    """
    Port of the exclusion clauses in OTHER ALG's Overpass query.

    RS requests::

        way["highway"~"^(primary|secondary|...)$"]
           ["footway"!="sidewalk"]["footway"!="crossing"]
           ["access"!="private"]["service"!="driveway"]["area"!="yes"]

    Since pyrosm gives us *all* walkable ways, we must retroactively
    remove the edges RS would never have fetched.  This is essential to
    match RS's graph density (~3-5K intersection nodes vs our 15K+).

    Returns a new (pruned) graph.
    """
    import networkx as nx

    edges_to_remove = []
    for u, v, key, data in graph.edges(keys=True, data=True):
        fw = data.get('footway')
        sv = data.get('service')
        ac = data.get('access')
        # RS: ["footway"!="sidewalk"]
        if fw is not None and str(fw) == 'sidewalk':
            edges_to_remove.append((u, v, key))
            continue
        # RS: ["footway"!="crossing"]
        if fw is not None and str(fw) == 'crossing':
            edges_to_remove.append((u, v, key))
            continue
        # RS: ["access"!="private"]
        if ac is not None and str(ac) == 'private':
            edges_to_remove.append((u, v, key))
            continue
        # RS: ["service"!="driveway"]
        if sv is not None and str(sv) == 'driveway':
            edges_to_remove.append((u, v, key))
            continue

    filtered = graph.copy()
    for u, v, key in edges_to_remove:
        if filtered.has_edge(u, v, key=key):
            filtered.remove_edge(u, v, key=key)

    # Remove isolated nodes (degree 0 after edge removal), except start
    isolated = [n for n in filtered.nodes()
                if n != start_node and filtered.degree(n) == 0]
    for n in isolated:
        filtered.remove_node(n)

    print(f"[TreeSearch] Road filter (Oe): removed {len(edges_to_remove)} edges, "
          f"{len(isolated)} isolated nodes → "
          f"{filtered.number_of_nodes()} nodes, "
          f"{filtered.number_of_edges()} edges")
    return filtered


# ── Node clustering (OTHER ALG's Ee / Fe) ────────────────────────────────

def _cluster_nearby_nodes(graph, start_node: int, threshold_m: float = 20.0):
    """
    Port of OTHER ALG's ``Ee()`` / ``Fe()`` — cluster nearby nodes.

    OTHER ALG groups nodes within ``threshold_m`` metres of each other
    into single representative nodes (centroids).  This dramatically
    reduces the node count at complex junctions where roads, sidewalks,
    and crossings create many closely-spaced nodes.

    The algorithm is *complete-linkage*: a candidate node must be within
    ``threshold_m`` of **every** existing member of the cluster, not just
    one.  This prevents chain-like cluster growth.

    Returns a new graph with merged nodes.
    """
    import networkx as nx
    from collections import defaultdict

    # 1. Build coord dict + spatial grid
    coords: Dict[int, Tuple[float, float]] = {}
    for node in graph.nodes():
        d = graph.nodes[node]
        coords[node] = (
            d.get('y', d.get('lat', 0.0)),
            d.get('x', d.get('lon', 0.0)),
        )

    start_lat = coords[start_node][0]
    lat_cos = math.cos(math.radians(start_lat))

    # Grid cell size — slightly larger than threshold to ensure we check
    # all potential neighbours.  RS uses threshold / 111000 * 1.5.
    cell_deg = (threshold_m / 111_000.0) * 1.5
    grid: Dict[Tuple[int, int], List[int]] = defaultdict(list)
    for node, (lat, lon) in coords.items():
        cx = int(math.floor(lat / cell_deg))
        cy = int(math.floor(lon / cell_deg))
        grid[(cx, cy)].append(node)

    # 2. Greedy complete-linkage clustering (RS's Fe algorithm)
    unvisited = set(graph.nodes())
    node_to_rep: Dict[int, int] = {}

    while unvisited:
        seed = next(iter(unvisited))
        unvisited.discard(seed)
        cluster = [seed]
        cluster_coords_list = [coords[seed]]

        # Grow cluster greedily
        changed = True
        while changed:
            changed = False
            # Collect candidate nodes from grid cells near any member
            candidates: Set[int] = set()
            for mlat, mlon in cluster_coords_list:
                cx = int(math.floor(mlat / cell_deg))
                cy = int(math.floor(mlon / cell_deg))
                for dx in (-1, 0, 1):
                    for dy in (-1, 0, 1):
                        for cand in grid.get((cx + dx, cy + dy), []):
                            if cand in unvisited:
                                candidates.add(cand)

            for cand in list(candidates):
                if cand not in unvisited:
                    continue
                clat, clon = coords[cand]
                # Must be within threshold of ALL cluster members
                all_close = True
                for mlat, mlon in cluster_coords_list:
                    d = _equirectangular_dist(clat, clon, mlat, mlon, lat_cos)
                    if d > threshold_m:
                        all_close = False
                        break
                if all_close:
                    cluster.append(cand)
                    cluster_coords_list.append((clat, clon))
                    unvisited.discard(cand)
                    changed = True

        # Choose representative (RS picks centroid; we pick the existing
        # node closest to centroid, ensuring start_node stays as-is)
        if start_node in cluster:
            rep = start_node
        elif len(cluster) == 1:
            rep = cluster[0]
        else:
            avg_lat = sum(c[0] for c in cluster_coords_list) / len(cluster)
            avg_lon = sum(c[1] for c in cluster_coords_list) / len(cluster)
            rep = min(cluster, key=lambda n: _equirectangular_dist(
                coords[n][0], coords[n][1], avg_lat, avg_lon, lat_cos))

        for n in cluster:
            node_to_rep[n] = rep

    # 3. Build new graph with only representatives
    reps = set(node_to_rep.values())
    new_graph = nx.MultiDiGraph()
    for rep in reps:
        new_graph.add_node(rep, **graph.nodes[rep])

    # 4. Add edges, redirecting endpoints to representatives
    for u, v, data in graph.edges(data=True):
        ru = node_to_rep.get(u)
        rv = node_to_rep.get(v)
        if ru is None or rv is None or ru == rv:
            continue  # self-loop from merging — skip
        new_graph.add_edge(ru, rv, **data)

    # 5. Remove duplicate parallel edges (keep shortest) like RS does
    # after Ee it also calls deleteDuplicateWays
    edges_to_remove = []
    for u in new_graph.nodes():
        for v in set(new_graph.successors(u)):
            edge_data = new_graph.get_edge_data(u, v)
            if edge_data and len(edge_data) > 1:
                best_key = min(
                    edge_data,
                    key=lambda k: edge_data[k].get('length', float('inf')),
                )
                for k in list(edge_data.keys()):
                    if k != best_key:
                        edges_to_remove.append((u, v, k))
    for u, v, k in edges_to_remove:
        if new_graph.has_edge(u, v, key=k):
            new_graph.remove_edge(u, v, key=k)

    merged = sum(1 for n, r in node_to_rep.items() if n != r)
    print(f"[TreeSearch] Clustered ({threshold_m:.0f}m): "
          f"{len(coords)} → {len(reps)} nodes ({merged} merged)")

    return new_graph


# ── Dead-end pruning (matches OTHER ALG's Ie function) ────────────────────

def _prune_dead_ends(graph, start_node: int):
    """
    Iteratively remove cul-de-sacs (degree-1 nodes) until stable.

    OTHER ALG removes entire *ways* whose nodes each appear in ≤1 way.
    Our graph doesn't have explicit way objects, so we prune nodes with
    only one unique neighbour (degree-1 in the undirected sense).

    Runs until convergence — matching OTHER ALG's Ie function which
    has no cap on removal rounds.

    Returns a new graph; the original is never mutated.
    """
    pruned = graph.copy()
    total_removed = 0

    while True:
        to_remove = []
        for node in pruned.nodes():
            if node == start_node:
                continue
            unique_neighbours = set(pruned.successors(node)) | set(pruned.predecessors(node))
            if len(unique_neighbours) <= 1:
                to_remove.append(node)

        if not to_remove:
            break

        for node in to_remove:
            pruned.remove_node(node)
        total_removed += len(to_remove)

    if total_removed:
        print(f"[TreeSearch] Pruned {total_removed} dead-end nodes")
    return pruned


# ── Graph simplification (OTHER ALG's Ae — removeNonIntersectionNodes) ────

def _simplify_graph(graph, start_node: int):
    """
    Contract degree-2 chains into single edges, keeping only intersection
    nodes.  Mirrors OTHER ALG's ``removeNonIntersectionNodes`` (``Ae``).

    A node is an *intersection* if its undirected degree ≠ 2 (i.e. it has
    1, 3, 4 … neighbours).  ``start_node`` is always kept.

    Each contracted edge stores the summed ``length``, plus ``highway``
    and ``name`` from the first original segment so that the search's
    penalty / way-change tracking still works.

    Returns
    -------
    simplified : networkx.MultiDiGraph
        Intersection-only graph.
    expansion_map : dict[(int, int), list[int]]
        Maps ``(from_node, to_node)`` → list of intermediate original
        node IDs, used by ``_expand_route`` to restore full detail.
    """
    import networkx as nx

    # 1. Identify nodes to keep (intersections + endpoints + start)
    keep: set = set()
    for node in graph.nodes():
        if node == start_node:
            keep.add(node)
            continue
        undirected_nbrs = set(graph.successors(node)) | set(graph.predecessors(node))
        if len(undirected_nbrs) != 2:
            keep.add(node)

    # 2. Build the simplified graph
    simplified = nx.MultiDiGraph()
    for node in keep:
        simplified.add_node(node, **graph.nodes[node])

    expansion_map: Dict[Tuple[int, int], List[int]] = {}
    processed_chains: Set[Tuple[int, int]] = set()

    for from_node in keep:
        for initial_nbr in graph.successors(from_node):
            # ── Direct connection between two kept nodes ──────────
            if initial_nbr in keep:
                edge_data = graph.get_edge_data(from_node, initial_nbr)
                if edge_data:
                    best_key = min(
                        edge_data,
                        key=lambda k: edge_data[k].get('length', float('inf')),
                    )
                    simplified.add_edge(
                        from_node, initial_nbr, **dict(edge_data[best_key]),
                    )
                    expansion_map.setdefault((from_node, initial_nbr), [])
                    expansion_map.setdefault((initial_nbr, from_node), [])
                continue

            # ── Walk along degree-2 chain ─────────────────────────
            if (from_node, initial_nbr) in processed_chains:
                continue
            processed_chains.add((from_node, initial_nbr))

            chain: List[int] = []
            total_length = 0.0
            first_highway: Optional[str] = None
            first_name: Optional[str] = None
            prev = from_node
            current = initial_nbr

            while current not in keep:
                chain.append(current)

                ed = graph.get_edge_data(prev, current)
                if ed:
                    bk = min(ed, key=lambda k: ed[k].get('length', float('inf')))
                    seg = ed[bk]
                    el = seg.get('length', 0)
                    total_length += el if el < float('inf') else 0
                    if first_highway is None:
                        hw = seg.get('highway')
                        if isinstance(hw, list):
                            hw = hw[0] if hw else None
                        first_highway = hw
                    if first_name is None:
                        nm = seg.get('name')
                        if isinstance(nm, list):
                            nm = nm[0] if nm else None
                        first_name = nm

                # Next node along the chain (undirected, skip prev)
                nbrs = set(graph.successors(current)) | set(graph.predecessors(current))
                nbrs.discard(prev)
                if len(nbrs) != 1:
                    break  # dead end or unexpected topology
                prev = current
                current = nbrs.pop()

            if current in keep:
                # Final segment to the end intersection
                ed = graph.get_edge_data(prev, current)
                if ed:
                    bk = min(ed, key=lambda k: ed[k].get('length', float('inf')))
                    seg = ed[bk]
                    el = seg.get('length', 0)
                    total_length += el if el < float('inf') else 0
                    if first_highway is None:
                        hw = seg.get('highway')
                        if isinstance(hw, list):
                            hw = hw[0] if hw else None
                        first_highway = hw
                    if first_name is None:
                        nm = seg.get('name')
                        if isinstance(nm, list):
                            nm = nm[0] if nm else None
                        first_name = nm

                simplified.add_edge(
                    from_node, current,
                    length=total_length,
                    highway=first_highway,
                    name=first_name,
                )
                if (from_node, current) not in expansion_map:
                    expansion_map[(from_node, current)] = chain
                if (current, from_node) not in expansion_map:
                    expansion_map[(current, from_node)] = chain[::-1]

    return simplified, expansion_map


def _expand_route(
    route: List[int],
    expansion_map: Dict[Tuple[int, int], List[int]],
) -> List[int]:
    """
    Expand a simplified (intersection-only) route back to the full
    original node sequence using the expansion map.

    Mirrors OTHER ALG's ``RouteDetailRestorer.expandRoute``.
    """
    if len(route) < 2:
        return list(route)

    expanded: List[int] = [route[0]]
    for i in range(len(route) - 1):
        a, b = route[i], route[i + 1]
        intermediates = expansion_map.get((a, b), [])
        expanded.extend(intermediates)
        expanded.append(b)
    return expanded


def _restore_original_detail(
    expanded_route: List[int],
    original_graph,
    gap_threshold_m: float = 150.0,
) -> List[int]:
    """
    Second-pass expansion: fill in original-graph road geometry for
    segments where the clustered representatives are far apart.

    Only processes consecutive pairs whose straight-line distance
    exceeds ``gap_threshold_m``.  Uses a **bounded** Dijkstra on the
    original graph — the search radius is capped at 2× the straight-
    line distance and path length at 3×.  This prevents the search
    from wandering through side streets (the issue with the original
    unbounded ``nx.shortest_path`` approach).
    """
    import heapq

    if len(expanded_route) < 2:
        return list(expanded_route)

    # Pre-compute lat_cos for distance calculations
    d0 = original_graph.nodes.get(expanded_route[0], {})
    start_lat = d0.get('y', d0.get('lat', 51.0))
    lat_cos = math.cos(math.radians(start_lat))

    full: List[int] = [expanded_route[0]]
    filled_count = 0

    for i in range(len(expanded_route) - 1):
        u, v = expanded_route[i], expanded_route[i + 1]
        if u == v:
            continue

        # Check if both nodes exist in the original graph
        if u not in original_graph.nodes or v not in original_graph.nodes:
            full.append(v)
            continue

        u_lat, u_lon = _node_coords(original_graph, u)
        v_lat, v_lon = _node_coords(original_graph, v)
        straight_dist = _equirectangular_dist(
            u_lat, u_lon, v_lat, v_lon, lat_cos,
        )

        # Short segment — no infill needed
        if straight_dist <= gap_threshold_m:
            full.append(v)
            continue

        # Bounded Dijkstra: only search nodes within spatial radius
        # and give up if path length exceeds cutoff
        search_radius = straight_dist * 2.0
        path_cutoff = straight_dist * 3.0

        # Midpoint for radius check
        mid_lat = (u_lat + v_lat) / 2.0
        mid_lon = (u_lon + v_lon) / 2.0

        # Dijkstra with distance cutoff
        dist_so_far = {u: 0.0}
        prev = {u: None}
        heap = [(0.0, u)]
        found = False

        while heap:
            d, node = heapq.heappop(heap)
            if d > dist_so_far.get(node, float('inf')):
                continue
            if node == v:
                found = True
                break
            if d > path_cutoff:
                break

            # Expand neighbours (bidirectional)
            neighbours = set()
            try:
                neighbours.update(original_graph.successors(node))
            except Exception:
                pass
            try:
                neighbours.update(original_graph.predecessors(node))
            except Exception:
                pass

            for nbr in neighbours:
                if nbr not in original_graph.nodes:
                    continue
                # Spatial radius check — skip nodes far from midpoint
                n_lat, n_lon = _node_coords(original_graph, nbr)
                if abs(n_lat - mid_lat) * 111_000 > search_radius:
                    continue
                if abs(n_lon - mid_lon) * 111_000 * lat_cos > search_radius:
                    continue

                # Edge length
                edge_data = original_graph.get_edge_data(node, nbr)
                if edge_data:
                    edge_len = min(
                        ed.get('length', 50.0)
                        for ed in (edge_data.values()
                                   if hasattr(edge_data, 'values')
                                   else [edge_data])
                    )
                else:
                    # Try reverse edge
                    edge_data_rev = original_graph.get_edge_data(nbr, node)
                    if edge_data_rev:
                        edge_len = min(
                            ed.get('length', 50.0)
                            for ed in (edge_data_rev.values()
                                       if hasattr(edge_data_rev, 'values')
                                       else [edge_data_rev])
                        )
                    else:
                        edge_len = _equirectangular_dist(
                            _node_coords(original_graph, node)[0],
                            _node_coords(original_graph, node)[1],
                            n_lat, n_lon, lat_cos,
                        )

                new_dist = d + edge_len
                if new_dist < dist_so_far.get(nbr, float('inf')):
                    dist_so_far[nbr] = new_dist
                    prev[nbr] = node
                    heapq.heappush(heap, (new_dist, nbr))

        if found:
            # Reconstruct path
            path = []
            node = v
            while node is not None and node != u:
                path.append(node)
                node = prev.get(node)
            path.reverse()
            full.extend(path)
            filled_count += 1
        else:
            full.append(v)  # fallback: direct connection

    if filled_count > 0:
        print(f"[TreeSearch] Detail restoration: filled {filled_count} "
              f"large gaps (>{gap_threshold_m:.0f}m)")

    return full

# ── Core tree search ─────────────────────────────────────────────────────────

def _tree_search(
    graph,
    start_node: int,
    target_distance: float,
    weights: Dict[str, float],
    min_length: float,
    max_length: float,
    combine_nature: bool = False,
    target_bearing: Optional[float] = None,
    distance_tolerance: float = 0.20,
    max_search_time: float = 120.0,
    max_iterations: int = 500_000,
    max_routes: int = 10,
    variety_level: int = 0,
    prefer_pedestrian: bool = False,
    depth_limit: int = 1000,
    random_seed: Optional[int] = None,
    allowed_turns: Optional[int] = 10,
) -> List[Tuple[List[int], float, float]]:
    """
    OTHER ALG-style tree-search A* for loop routes.

    Each frontier entry carries the full path.  No g-score merging —
    multiple paths to the same node coexist.  Post-hoc deduplication
    filters overlapping routes.

    Returns list of (route, distance, scenic_cost) tuples.
    """
    global _heap_counter
    _heap_counter = 0

    t0 = time.time()

    # Pre-compute coordinate and neighbour caches
    coord_cache = _build_coord_cache(graph)
    neighbour_cache = _build_neighbour_cache(graph)

    start_lat, start_lon = coord_cache[start_node]
    lat_cos = math.cos(math.radians(start_lat))

    max_distance = target_distance * 1.5   # OTHER ALG uses 1.5x
    tolerance_window = target_distance * distance_tolerance

    # Variety / randomisation (OTHER ALG's fe._initializeRandomization)
    rng: Optional[_SeededRNG] = None
    weight_mult_turn = 1.0
    weight_mult_bearing = 1.0
    weight_mult_way_change = 1.0
    f_noise_range = 0.0

    if variety_level > 0:
        seed = random_seed if random_seed is not None else int(time.time() * 1000)
        rng = _SeededRNG(seed)
        spread = {1: 0.1, 2: 0.2, 3: 0.3}.get(variety_level, 0.3)
        f_noise_range = {1: 0.02, 2: 0.05, 3: 0.08}.get(variety_level, 0.08)
        weight_mult_turn = rng.random(1 - spread, 1 + spread)
        weight_mult_bearing = rng.random(1 - spread, 1 + spread)
        weight_mult_way_change = rng.random(1 - spread, 1 + spread)
        print(f"[TreeSearch] Variety level {variety_level}: "
              f"mult=(turn={weight_mult_turn:.2f}, bearing={weight_mult_bearing:.2f}, "
              f"wayChange={weight_mult_way_change:.2f}), noise=±{f_noise_range*100:.0f}%")

    # Directional bias
    preferred_bearing: Optional[float] = None
    if target_bearing is not None:
        preferred_bearing = target_bearing

    # ── Heuristic function (OTHER ALG's _calculateHeuristic) ──────
    def heuristic(state: _RouteState) -> float:
        node = state.current_node
        n_lat, n_lon = coord_cache[node]
        dist_to_start = _equirectangular_dist(
            n_lat, n_lon, start_lat, start_lon, lat_cos,
        )
        if dist_to_start == float('inf'):
            return float('inf')

        remaining = max(0.0, target_distance - state.distance)

        # h = max(remaining, dist_to_start)  — the OTHER ALG core
        h = remaining if remaining > dist_to_start else dist_to_start

        # Turn penalty (proportional to target_distance, as RS does)
        turn_p = (state.turn_count *
                  (target_distance * 0.02) *
                  weight_mult_turn)

        # Bearing-change penalty
        bearing_p = (abs(state.total_bearing_change) *
                     (target_distance * 0.0001) *
                     weight_mult_bearing)

        # Way name/type change penalty
        way_p = ((state.way_name_changes + state.way_type_changes) *
                 (target_distance * 0.01) *
                 weight_mult_way_change)

        # Pedestrian preference penalty
        ped_p = 0.0
        if prefer_pedestrian:
            ped_p = state.highway_penalty_score * 0.02

        # Directional bias (OTHER ALG's _calculateDirectionalBias)
        dir_p = 0.0
        if preferred_bearing is not None:
            edge_bear = _bearing(start_lat, start_lon, n_lat, n_lon)
            diff = abs(edge_bear - preferred_bearing)
            if diff > 180:
                diff = 360 - diff
            alignment = diff / 180.0  # 0 = aligned, 1 = opposite

            progress = min(state.distance / target_distance, 1.0)
            # Fade: full strength below 30%, zero above 70%
            if progress < 0.3:
                fade = 1.0
            else:
                fade = max(0.0, (0.7 - progress) / 0.4)

            # (alignment - 0.5) * 2  maps [0,1] to [-1,1]
            dir_p = (alignment - 0.5) * 2.0 * (target_distance * 0.35) * fade

        return h + turn_p + bearing_p + way_p + ped_p + dir_p

    # ── f-score ──────────────────────────────────────────────────────
    def f_score(state: _RouteState) -> float:
        g = state.distance
        h = heuristic(state)
        f = g + h
        if f_noise_range > 0.0 and rng is not None:
            noise = rng.random(-f_noise_range, f_noise_range)
            f *= (1.0 + noise)
        return f

    # ── State key for visited set (OTHER ALG's _getStateKey) ──────
    def state_key(state: _RouteState) -> str:
        tail = state.path[-min(3, len(state.path)):]
        dist_bin = int(state.distance // 200)
        # Use tuple for faster hashing
        return (tuple(tail), dist_bin)

    # ── Initialise search ────────────────────────────────────────────
    initial = _RouteState(start_node, lat_cos)
    open_set: list = []
    _heap_push(open_set, f_score(initial), initial)

    visited: Set = set()
    deduplicator = _RouteDeduplicator()

    found_routes: List[Tuple[List[int], float, float]] = []
    iterations = 0
    max_open_size = 1
    nodes_explored = 0
    max_depth = 0
    start_arrivals = 0

    # Frontier trimming thresholds (OTHER ALG: 50K → trim to 25K)
    FRONTIER_MAX = 50_000
    FRONTIER_TRIM = 25_000

    print(f"[TreeSearch] Starting search: target={target_distance:.0f}m, "
          f"tolerance=±{distance_tolerance*100:.0f}%, "
          f"max_iter={max_iterations}, max_routes={max_routes}")

    while open_set:
        # ── Time check ───────────────────────────────────────────────
        if time.time() - t0 > max_search_time:
            print(f"[TreeSearch] Time limit reached after {iterations} iterations")
            break

        # ── Iteration cap ────────────────────────────────────────────
        if iterations >= max_iterations:
            print(f"[TreeSearch] Iteration limit reached")
            break

        iterations += 1

        # ── Progress logging ─────────────────────────────────────────
        if iterations % 5000 == 0:
            elapsed = time.time() - t0
            print(f"[TreeSearch] Iteration {iterations}: "
                  f"open={len(open_set)}, found={len(found_routes)}, "
                  f"time={elapsed:.1f}s")

        # ── Pop best state ───────────────────────────────────────────
        current_f, state = _heap_pop(open_set)
        nodes_explored += 1
        if len(open_set) > max_open_size:
            max_open_size = len(open_set)
        if state.depth > max_depth:
            max_depth = state.depth

        node = state.current_node

        # ── Track start-node arrivals (for diagnostics) ──────────────
        if state.depth > 1 and node == start_node:
            start_arrivals += 1

        # ── Goal check (OTHER ALG's loop-closure test) ────────────
        # depth > 1 ensures we have actual edges, not just start node
        if (state.depth > 1
                and node == start_node
                and abs(state.distance - target_distance) <= tolerance_window):
            # Deduplication check
            if deduplicator.is_duplicate(state.path, graph, threshold=0.85):
                continue

            # Scenic cost is computed after route expansion in find_loops
            found_routes.append((list(state.path), state.distance, 0.0))
            print(f"[TreeSearch] Route found: {state.distance:.0f}m, "
                  f"{state.turn_count} turns, f={current_f:.0f}")

            if len(found_routes) >= max_routes:
                print(f"[TreeSearch] Found {max_routes} routes, stopping")
                break
            continue

        # ── Pruning ──────────────────────────────────────────────────
        # Too long
        if state.distance > max_distance:
            continue

        # Too deep
        if state.depth > depth_limit:
            continue

        # Can't return to start within remaining budget
        n_lat, n_lon = coord_cache[node]
        dist_to_start = _equirectangular_dist(
            n_lat, n_lon, start_lat, start_lon, lat_cos,
        )
        remaining_budget = max_distance - state.distance
        if dist_to_start > remaining_budget:
            continue

        # Too many turns (OTHER ALG's shouldPrune: turnCount > allowedTurns)
        if allowed_turns is not None and state.turn_count > allowed_turns:
            continue

        # U-turn detection (OTHER ALG prunes 170-190° reversals)
        if (state.current_bearing is not None
                and state.previous_bearing is not None):
            turn = abs(_bearing_diff(state.previous_bearing,
                                     state.current_bearing))
            if 170 < turn < 190:
                continue

        # ── Visited check (OTHER ALG's _getStateKey dedup) ────────
        sk = state_key(state)
        if sk in visited:
            continue
        visited.add(sk)

        # ── Expand neighbours ────────────────────────────────────────
        neighbours = neighbour_cache.get(node)
        if not neighbours:
            continue

        for nbr in neighbours:
            # Cycle prevention: don't revisit any node already in path
            # (except start_node for loop closure).
            # This matches OTHER ALG's filter:
            #    .filter(C => C && !f.path.slice(1).includes(C))
            if nbr != start_node and nbr in state.path_set:
                continue

            child = state.clone()
            nbr_lat, nbr_lon = coord_cache[nbr]
            child.push_node(nbr, nbr_lat, nbr_lon, graph)

            child_f = f_score(child)
            _heap_push(open_set, child_f, child)

        # ── Frontier trimming (OTHER ALG: 50K → 25K) ──────────────
        if len(open_set) > FRONTIER_MAX:
            open_set = _heap_trim(open_set, FRONTIER_TRIM)

    elapsed = time.time() - t0
    dedup_stats = deduplicator
    print(f"\n[TreeSearch] Search complete:")
    print(f"  Max depth: {max_depth}")
    print(f"  Start arrivals: {start_arrivals}")
    print(f"  Iterations: {iterations}")
    print(f"  Nodes explored: {nodes_explored}")
    print(f"  Max open set: {max_open_size}")
    print(f"  Routes found: {len(found_routes)}")
    print(f"  Duplicates suppressed: {dedup_stats.duplicates_found}")
    print(f"  Time: {elapsed:.1f}s")

    return found_routes


# ── Scenic cost helper ───────────────────────────────────────────────────────

def _route_scenic_cost(
    graph, route: List[int], weights: Dict[str, float],
    min_length: float, max_length: float, combine_nature: bool,
) -> float:
    """Total WSM scenic cost of a route."""
    total = 0.0
    for u, v in zip(route[:-1], route[1:]):
        edges = graph.get_edge_data(u, v)
        if not edges:
            total += 1.0
            continue
        best_cost = float('inf')
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
        total += best_cost if best_cost < float('inf') else 1.0
    return total


# ── Path overlap ratio ──────────────────────────────────────────────────────

def _path_overlap_ratio(route: List[int]) -> float:
    """Fraction of edges that retrace an already-walked segment."""
    edge_set: Set[Tuple[int, int]] = set()
    duplicate_count = 0
    for u, v in zip(route[:-1], route[1:]):
        edge = (min(u, v), max(u, v))
        if edge in edge_set:
            duplicate_count += 1
        else:
            edge_set.add(edge)
    total_edges = len(route) - 1
    return duplicate_count / total_edges if total_edges > 0 else 0.0


# ── Dominant bearing ─────────────────────────────────────────────────────────

def _route_dominant_bearing(
    graph, route: List[int], start_node: int,
) -> Optional[float]:
    """Bearing from start to the farthest point on the route."""
    s_lat, s_lon = _node_coords(graph, start_node)
    lat_cos = math.cos(math.radians(s_lat))
    max_dist = 0.0
    far_lat, far_lon = s_lat, s_lon
    for node in route:
        n_lat, n_lon = _node_coords(graph, node)
        d = _equirectangular_dist(n_lat, n_lon, s_lat, s_lon, lat_cos)
        if d > max_dist:
            max_dist = d
            far_lat, far_lon = n_lat, n_lon
    if max_dist < 10:
        return None
    return _bearing(s_lat, s_lon, far_lat, far_lon)


# ── Bearing constants ────────────────────────────────────────────────────────

BIAS_TO_BEARING: Dict[str, Optional[float]] = {
    'north': 0.0,
    'east': 90.0,
    'south': 180.0,
    'west': 270.0,
    'none': None,
}


# ── TreeSearchSolver class ──────────────────────────────────────────────────

class TreeSearchSolver(LoopSolverBase):
    """
    OTHER ALG-style tree-search loop solver.

    Runs a single A* search where each frontier entry carries its full
    path.  Collects up to ``max_routes`` unique loops via post-hoc
    grid-cell deduplication.

    This is a faithful port of the OTHER ALG algorithm to Python.
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
        variety_level: int = 0,
        prefer_pedestrian: bool = False,
        prefer_paved: bool = False,
        prefer_lit: bool = False,
        avoid_unsafe_roads: bool = False,
    ) -> List[LoopCandidate]:
        """
        Find multiple diverse loop candidates using tree search.

        Mirrors OTHER ALG's search flow:
            1. Crop to geographic radius.
            2. Simplify graph (remove non-intersection nodes).
            3. Prune dead-end nodes.
            4. Run one A* tree search collecting up to 10 loops.
            5. Expand, score and rank results.
            6. Select diverse top-K candidates.
        """
        t0 = time.time()

        weights = validate_weights(weights)
        min_length, max_length = find_length_range(graph)

        user_bearing = BIAS_TO_BEARING.get(directional_bias.lower(), None)

        # OTHER ALG hardcodes max 10 routes
        max_routes = 10

        # ── 1. Geographic crop (OTHER ALG's radius filtering) ─────
        # OTHER ALG queries Overpass with `way(around:RADIUS, ...)`,
        # so its graph only contains roads within a small circle.
        # Our tile is ~20×20 km — far too large.  Crop to match RS.
        target_km = target_distance / 1000.0
        search_radius_km = _calculate_search_radius_km(target_km)
        search_radius_m = search_radius_km * 1000.0
        cropped_graph = _crop_to_radius(graph, start_node, search_radius_m)

        # ── 2. Road-type filter (OTHER ALG's Oe / Overpass) ───────
        # RS's Overpass query excludes footway=sidewalk, footway=crossing,
        # access=private, service=driveway.  Our pyrosm graph includes
        # all of these.  Filter them out to match RS's data density.
        filtered_graph = _filter_road_types(cropped_graph, start_node)

        # ── 3. Node clustering (OTHER ALG's Ee / Fe) ──────────────
        # RS merges nodes within 20 m of each other into single
        # representative nodes.  This collapses complex junctions where
        # sidewalks, crossings, and road lanes create many closely-
        # spaced nodes (e.g. a 4-way junction → 1 node instead of 6+).
        #
        # RS hardcodes 20 m; however our pyrosm graph has many more
        # closely-spaced intersection nodes than RS's Overpass graph
        # (RS averages ~200 m between intersections; ours ~56 m).
        # To achieve a comparable search-graph density (~5 K intersection
        # nodes after simplification), we adaptively increase the
        # clustering distance.  This keeps 5 km routes at 20 m (already
        # working) while bringing 10 km+ routes into a searchable range.
        TARGET_SEARCH_NODES = 5_000
        cluster_threshold = 20.0
        for attempt in range(5):
            test_clustered = _cluster_nearby_nodes(
                filtered_graph, start_node, threshold_m=cluster_threshold)
            test_simplified, _ = _simplify_graph(test_clustered, start_node)
            test_pruned = _prune_dead_ends(test_simplified, start_node)
            est_nodes = test_pruned.number_of_nodes()
            print(f"[TreeSearch] Clustering trial {attempt+1}: "
                  f"threshold={cluster_threshold:.0f}m → "
                  f"{est_nodes} intersection nodes (target ≤{TARGET_SEARCH_NODES})")
            if est_nodes <= TARGET_SEARCH_NODES:
                break
            # Scale up proportionally to overshoot
            ratio = est_nodes / TARGET_SEARCH_NODES
            cluster_threshold *= max(ratio ** 0.6, 1.3)  # conservative increase
            cluster_threshold = min(cluster_threshold, 200.0)  # cap at 200m

        clustered_graph = test_clustered

        # ── 4. Graph simplification (OTHER ALG's Ae) ──────────────
        # RS does Ae (removeNonIntersectionNodes) BEFORE Ie (removeCulDeSacs).
        # Contracts degree-2 chains so the search operates on
        # intersections only.
        simplified, expansion_map = _simplify_graph(clustered_graph, start_node)
        print(f"[TreeSearch] Simplified: {clustered_graph.number_of_nodes()} → "
              f"{simplified.number_of_nodes()} nodes "
              f"({simplified.number_of_edges()} edges)")

        # ── 5. Dead-end pruning (OTHER ALG's Ie) ──────────────────
        search_graph = _prune_dead_ends(simplified, start_node)

        # Depth limit — OTHER ALG uses 1000
        depth_limit = 1000

        # Distance tolerance: OTHER ALG hardcodes ±20% for the goal
        # check (targetLength * 0.2), regardless of the input tolerance.
        # Match that for the tree search; tighter selection happens in
        # candidate scoring.
        search_tolerance = 0.20

        # Run the search on the simplified (intersection-only) graph
        # OTHER ALG: search(500_000 iterations, 300_000 ms timeout)
        raw_loops = _tree_search(
            search_graph,
            start_node,
            target_distance,
            weights,
            min_length,
            max_length,
            combine_nature=combine_nature,
            target_bearing=user_bearing,
            distance_tolerance=search_tolerance,
            max_search_time=300.0,       # RS uses 300 seconds
            max_iterations=5_000_000,    # High cap; time limit governs
            max_routes=max_routes,
            variety_level=variety_level,
            prefer_pedestrian=prefer_pedestrian,
            depth_limit=depth_limit,
            random_seed=None,
            allowed_turns=10,            # RS default 8-10; hard prune
        )

        if not raw_loops:
            print(f"[TreeSearch] No loops found for "
                  f"{target_distance/1000:.1f}km target")
            return []

        # ── Expand routes to original node sequences ─────────────────
        # The search ran on the simplified graph; now restore every
        # intermediate node so scenic cost + display are accurate.
        # Use the ORIGINAL (uncropped) graph for expansion so that
        # edge attributes (scenic scores etc.) are available.
        expanded_loops: List[Tuple[List[int], float, float]] = []
        start_lat_exp, _ = _node_coords(graph, start_node)
        lat_cos_exp = math.cos(math.radians(start_lat_exp))

        # Log expansion map stats
        print(f"[TreeSearch] Expansion map has {len(expansion_map)} entries")

        for idx, (route, distance, _) in enumerate(raw_loops):
            # Only log detail for first route to avoid spam
            verbose = (idx == 0)
            print(f"[TreeSearch]   Route {idx}: {len(route)} simplified nodes, "
                  f"search dist={distance:.0f}m")

            # Count expansion map hits vs misses on the simplified route
            hits = misses = 0
            for i in range(len(route) - 1):
                a, b = route[i], route[i + 1]
                if (a, b) in expansion_map:
                    hits += 1
                else:
                    misses += 1
            print(f"[TreeSearch]   Route {idx}: expansion map: "
                  f"{hits} hits, {misses} misses out of {len(route)-1} edges")

            full_route = _expand_route(route, expansion_map)
            full_route = _restore_original_detail(full_route, graph)
            print(f"[TreeSearch]   Route {idx}: {len(full_route)} nodes after "
                  f"expansion + detail restoration")

            # Gap analysis: find segments with large straight-line jumps
            actual_dist = 0.0
            gaps = []  # (segment_idx, u, v, dist_m)
            missing_nodes = 0
            for seg_i, (u, v) in enumerate(zip(full_route[:-1], full_route[1:])):
                u_in = u in graph.nodes
                v_in = v in graph.nodes
                if not u_in:
                    missing_nodes += 1
                if not v_in and seg_i == len(full_route) - 2:
                    missing_nodes += 1  # last node

                if u_in and v_in:
                    u_lat, u_lon = _node_coords(graph, u)
                    v_lat, v_lon = _node_coords(graph, v)
                    seg_dist = _equirectangular_dist(
                        u_lat, u_lon, v_lat, v_lon, lat_cos_exp,
                    )
                    actual_dist += seg_dist
                    if seg_dist > 200:
                        gaps.append((seg_i, u, v, seg_dist))
                else:
                    # Node not in graph — this is a coordinate lookup failure
                    if verbose:
                        print(f"[TreeSearch]     WARN seg {seg_i}: "
                              f"node(s) not in graph: u={u}({u_in}) v={v}({v_in})")

            print(f"[TreeSearch]   Route {idx}: actual_dist={actual_dist:.0f}m "
                  f"(search said {distance:.0f}m, "
                  f"delta={actual_dist - distance:+.0f}m)")
            if missing_nodes > 0:
                print(f"[TreeSearch]   Route {idx}: {missing_nodes} nodes "
                      f"NOT found in original graph!")

            if gaps:
                gaps.sort(key=lambda x: -x[3])
                print(f"[TreeSearch]   Route {idx}: {len(gaps)} segments > 200m "
                      f"(top 5 largest):")
                for gap_i, (si, u, v, d) in enumerate(gaps[:5]):
                    # Check if u→v has a direct edge in the original graph
                    has_edge = graph.has_edge(u, v) or graph.has_edge(v, u)
                    print(f"[TreeSearch]     #{gap_i}: seg {si}, "
                          f"{u}→{v}, {d:.0f}m, "
                          f"direct_edge={has_edge}")
            else:
                print(f"[TreeSearch]   Route {idx}: all segments ≤ 200m ✓")

            # Compute scenic cost on full route (uses original edge attrs)
            scenic_cost = _route_scenic_cost(
                graph, full_route, weights,
                min_length, max_length, combine_nature,
            )
            expanded_loops.append((full_route, actual_dist, scenic_cost))

        raw_loops = expanded_loops
        print(f"[TreeSearch] Expanded {len(raw_loops)} routes to full detail")

        # ── Convert to LoopCandidates ────────────────────────────────
        max_cost = max(cost for _, _, cost in raw_loops)
        max_cost = max(max_cost, 0.001)

        candidates: List[LoopCandidate] = []
        for route, distance, scenic_cost in raw_loops:
            deviation = abs(distance - target_distance) / target_distance
            quality = calculate_quality_score(
                deviation, scenic_cost, max_scenic_cost=max_cost,
            )

            # Penalise out-and-back routes
            overlap = _path_overlap_ratio(route)
            if overlap > 0.15:
                quality *= max(0.1, 1.0 - overlap)

            # Penalise routes ignoring user's directional preference
            if user_bearing is not None:
                route_bear = _route_dominant_bearing(graph, route, start_node)
                if route_bear is not None:
                    diff = abs(route_bear - user_bearing)
                    if diff > 180:
                        diff = 360 - diff
                    direction_match = 1.0 - (diff / 180.0)
                    quality *= 0.3 + 0.7 * direction_match

            candidates.append(LoopCandidate(
                route=route,
                distance=distance,
                scenic_cost=scenic_cost,
                deviation=deviation,
                quality_score=quality,
                algorithm='tree_search',
                metadata={
                    'directional_bias': directional_bias,
                    'target_distance': target_distance,
                    'path_overlap': round(overlap, 3),
                },
            ))

        # ── Select diverse candidates ────────────────────────────────
        result = select_diverse_candidates(candidates, k=num_candidates)

        elapsed = time.time() - t0
        print(f"[TreeSearch] Returning {len(result)} candidates from "
              f"{len(raw_loops)} raw loops, {elapsed:.1f}s total")

        return result
