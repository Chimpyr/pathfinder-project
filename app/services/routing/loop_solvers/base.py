"""
Loop Solver Base Module

Defines the abstract interface for all loop routing algorithms and the
standardised LoopCandidate data structure for results.

All solvers receive the same input parameters and return a list of
LoopCandidate objects for frontend compatibility.

See 002-loop-route-refactor.md for design rationale.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


# ── Colour palette for multi-loop display ────────────────────────────────────
# Supports up to 10 distinct loop candidates

LOOP_COLOURS = [
    '#3B82F6',   # Blue   - primary / conservative
    '#22C55E',   # Green  - scenic / exploratory
    '#A855F7',   # Purple - directional / alternative
    '#F97316',   # Orange - fallback
    '#EF4444',   # Red    - additional
    '#06B6D4',   # Cyan   - additional
    '#F59E0B',   # Amber  - additional
    '#EC4899',   # Pink   - additional
    '#10B981',   # Emerald - additional
    '#8B5CF6',   # Violet - additional
]

ROLE_LABELS = {
    'best_match': 'Best Match',
    'scenic_alternative': 'Scenic Alternative',
    'diverse_alternative': 'Diverse Alternative',
    'exploration_option': 'Exploration Option',
}

EXTRA_LOOP_LABELS = [
    'Quiet Streets Option',
    'Extended Option',
    'Neighbourhood Option',
    'Panoramic Option',
    'Balanced Option',
    'Fallback Option',
]

LOOP_LABELS = [
    ROLE_LABELS['best_match'],
    ROLE_LABELS['scenic_alternative'],
    ROLE_LABELS['diverse_alternative'],
    ROLE_LABELS['exploration_option'],
    *EXTRA_LOOP_LABELS,
]


def _bearing_to_descriptor(raw_bearing: Any) -> str:
    """Return a short direction descriptor from bearing metadata."""
    if raw_bearing is None:
        return 'Any direction'

    if isinstance(raw_bearing, str):
        token = raw_bearing.strip().lower()
        named = {
            'north': 'Northbound',
            'east': 'Eastbound',
            'south': 'Southbound',
            'west': 'Westbound',
            'none': 'Any direction',
        }
        if token in named:
            return named[token]

    try:
        bearing = float(raw_bearing) % 360.0
    except (TypeError, ValueError):
        return 'Any direction'

    compass = [
        'Northbound',
        'North-east',
        'Eastbound',
        'South-east',
        'Southbound',
        'South-west',
        'Westbound',
        'North-west',
    ]
    idx = int((bearing + 22.5) // 45.0) % len(compass)
    return compass[idx]


def _shape_to_descriptor(meta: Dict[str, Any]) -> str:
    """Return loop-shape wording from solver metadata."""
    loop_type = str(meta.get('type', '') or '').strip().lower()
    if loop_type == 'out-and-back':
        return 'Out-and-back'

    shape_raw = str(meta.get('shape', '') or '').strip().upper()
    if shape_raw.startswith('N='):
        try:
            sides = int(shape_raw.split('=', 1)[1])
        except (TypeError, ValueError):
            sides = None
        side_labels = {
            3: 'Triangle',
            4: 'Quadrilateral',
            5: 'Pentagon',
            6: 'Hexagon',
        }
        if sides in side_labels:
            return side_labels[sides]
        if sides and sides >= 7:
            return 'Polygon'

    return 'Loop'


def _normalise_bias_token(raw_bias: Any) -> str:
    """Return canonical directional bias token for naming metadata."""
    token = str(raw_bias or 'none').strip().lower()
    return token if token in {'north', 'east', 'south', 'west', 'none'} else 'none'


def _assign_role_by_index(selected: List['LoopCandidate']) -> Dict[int, str]:
    """Assign a semantic naming role to each selected candidate index."""
    role_by_index: Dict[int, str] = {}
    if not selected:
        return role_by_index

    role_by_index[0] = 'best_match'
    remaining = list(range(1, len(selected)))

    if remaining:
        scenic_idx = min(
            remaining,
            key=lambda i: (
                selected[i].scenic_cost,
                selected[i].deviation,
                -selected[i].quality_score,
            ),
        )
        role_by_index[scenic_idx] = 'scenic_alternative'
        remaining.remove(scenic_idx)

    if remaining:
        best_route = selected[0].route
        diverse_idx = max(
            remaining,
            key=lambda i: (
                1.0 - route_similarity(selected[i].route, best_route),
                selected[i].quality_score,
            ),
        )
        role_by_index[diverse_idx] = 'diverse_alternative'
        remaining.remove(diverse_idx)

    if remaining:
        exploration_idx = max(
            remaining,
            key=lambda i: (
                sum(
                    1.0 - route_similarity(selected[i].route, other.route)
                    for j, other in enumerate(selected)
                    if j != i
                ) / max(1, len(selected) - 1),
                -selected[i].deviation,
                selected[i].quality_score,
            ),
        )
        role_by_index[exploration_idx] = 'exploration_option'
        remaining.remove(exploration_idx)

    for idx in remaining:
        role_by_index[idx] = 'extra'

    return role_by_index


def _attach_name_explainability(
    candidate: 'LoopCandidate',
    index: int,
    selected: List['LoopCandidate'],
    role: str,
) -> None:
    """Populate metadata fields explaining exactly why a candidate got its label."""
    if candidate.metadata is None:
        candidate.metadata = {}

    direction = _bearing_to_descriptor(candidate.metadata.get('bearing'))
    shape = _shape_to_descriptor(candidate.metadata)
    candidate.metadata['name_subtitle'] = f"{direction} | {shape}"

    scenic_sorted = sorted(selected, key=lambda c: c.scenic_cost)
    scenic_rank = scenic_sorted.index(candidate) + 1
    scenic_total = len(scenic_sorted)

    best = selected[0]
    dissimilarity_best_pct = int(
        round((1.0 - route_similarity(candidate.route, best.route)) * 100)
    )
    avg_dissimilarity_pct = int(
        round(
            (
                sum(
                    1.0 - route_similarity(candidate.route, other.route)
                    for other in selected
                    if other is not candidate
                )
                / max(1, len(selected) - 1)
            ) * 100
        )
    )

    bias_token = _normalise_bias_token(candidate.metadata.get('directional_bias'))
    variety_level = candidate.metadata.get('variety_level')
    try:
        variety_level_int = int(variety_level)
    except (TypeError, ValueError):
        variety_level_int = None

    if role == 'best_match':
        reason = (
            f"Assigned as Best Match: highest combined quality score "
            f"({candidate.quality_score:.3f}) with {candidate.deviation_percent:.1f}% target deviation."
        )
        role_tag = 'Quality leader'
    elif role == 'scenic_alternative':
        reason = (
            "Assigned as Scenic Alternative: lowest scenic cost among alternatives "
            f"(rank {scenic_rank}/{scenic_total}) with {candidate.deviation_percent:.1f}% target deviation."
        )
        role_tag = 'Lowest scenic cost (alt)'
    elif role == 'diverse_alternative':
        reason = (
            "Assigned as Diverse Alternative: highest edge dissimilarity from Best Match "
            f"({dissimilarity_best_pct}%) with {candidate.deviation_percent:.1f}% target deviation."
        )
        role_tag = 'Max edge diversity vs best'
    elif role == 'exploration_option':
        reason = (
            "Assigned as Exploration Option: high cross-route novelty "
            f"(avg {avg_dissimilarity_pct}% different) while staying "
            f"{candidate.deviation_percent:.1f}% from target."
        )
        if variety_level_int and variety_level_int > 0:
            reason += f" Variety level {variety_level_int} expanded bearing/shape exploration."
        role_tag = 'High novelty across options'
    else:
        reason = (
            "Assigned as additional alternative: balanced fallback with "
            f"{candidate.deviation_percent:.1f}% target deviation and scenic rank "
            f"{scenic_rank}/{scenic_total}."
        )
        role_tag = 'Additional alternative'

    tags = [
        role_tag,
        f"Target delta {candidate.deviation_percent:.1f}%",
        f"Scenic rank {scenic_rank}/{scenic_total}",
    ]
    if role != 'best_match':
        tags.append(f"{dissimilarity_best_pct}% different vs best")
    if bias_token != 'none':
        tags.append(f"Bias: {bias_token.title()}")
    if variety_level_int is not None:
        tags.append(f"Variety L{variety_level_int}")
    if candidate.metadata.get('use_smart_bearing'):
        tags.append('Smart bearing')

    candidate.metadata['name_role'] = role
    candidate.metadata['name_reason'] = reason
    candidate.metadata['name_tags'] = tags[:7]
    candidate.metadata['name_strategy'] = 'quality-diversity-geometry'


# ── LoopCandidate data structure ─────────────────────────────────────────────

@dataclass
class LoopCandidate:
    """
    Represents a single loop route candidate.

    All loop solvers return a list of these, enabling uniform frontend
    rendering regardless of which algorithm generated the route.

    Attributes:
        route: Ordered list of OSM node IDs forming the loop.
        distance: Total physical distance in metres.
        scenic_cost: Cumulative WSM scenic cost (lower = more scenic).
        deviation: Absolute fractional deviation from target distance (0-1).
        quality_score: Combined ranking score (higher = better).
        algorithm: Name of the solver that generated this candidate.
        colour: Hex colour code for map rendering.
        label: Human-readable label for the UI.
        metadata: Algorithm-specific extras (iterations, timing, etc.).
    """
    route: List[int]
    distance: float
    scenic_cost: float
    deviation: float
    quality_score: float
    algorithm: str
    colour: str = '#3B82F6'
    label: str = 'Loop'
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def distance_km(self) -> float:
        """Distance in kilometres, rounded to 2 decimal places."""
        return round(self.distance / 1000, 2)

    @property
    def deviation_percent(self) -> float:
        """Deviation as a percentage string-friendly value."""
        return round(self.deviation * 100, 1)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to JSON-serialisable dictionary for API response."""
        return {
            'route': self.route,
            'distance': self.distance,
            'distance_km': self.distance_km,
            'scenic_cost': round(self.scenic_cost, 4),
            'deviation': round(self.deviation, 4),
            'deviation_percent': self.deviation_percent,
            'quality_score': round(self.quality_score, 4),
            'algorithm': self.algorithm,
            'colour': self.colour,
            'label': self.label,
            'metadata': self.metadata,
        }


# ── Quality scoring ──────────────────────────────────────────────────────────

def calculate_quality_score(
    deviation: float,
    scenic_cost: float,
    max_scenic_cost: float = 1.0,
    distance_weight: float = 0.6,
    scenic_weight: float = 0.4,
) -> float:
    """
    Calculate a combined quality score for ranking loop candidates.

    Higher score = better candidate.

    Args:
        deviation: Absolute fractional deviation from target (0 = perfect).
        scenic_cost: Total WSM scenic cost (lower = better).
        max_scenic_cost: Maximum possible scenic cost for normalisation.
        distance_weight: Weight given to distance accuracy (0-1).
        scenic_weight: Weight given to scenic quality (0-1).

    Returns:
        Quality score in range [0, 1].
    """
    # Distance accuracy: 1.0 at 0% deviation, 0.0 at >=50% deviation
    distance_score = max(0.0, 1.0 - min(deviation / 0.5, 1.0))

    # Scenic quality: 1.0 at zero cost, 0.0 at max cost
    if max_scenic_cost > 0:
        scenic_score = max(0.0, 1.0 - (scenic_cost / max_scenic_cost))
    else:
        scenic_score = 1.0

    return distance_weight * distance_score + scenic_weight * scenic_score


# ── Diversity selection ──────────────────────────────────────────────────────

def route_similarity(route_a: List[int], route_b: List[int]) -> float:
    """
    Jaccard similarity of two routes based on edge overlap.

    Returns:
        Similarity in [0, 1]. 1.0 = identical edge sets, 0.0 = no overlap.
    """
    if len(route_a) < 2 or len(route_b) < 2:
        return 0.0

    edges_a = set(zip(route_a[:-1], route_a[1:]))
    edges_b = set(zip(route_b[:-1], route_b[1:]))

    overlap = len(edges_a & edges_b)
    union = len(edges_a | edges_b)

    if union == 0:
        return 0.0
    return overlap / union


def select_diverse_candidates(
    candidates: List[LoopCandidate],
    k: int = 3,
) -> List[LoopCandidate]:
    """
    Select K diverse candidates from a larger pool.

    Strategy:
        1. Pick the best candidate by quality_score.
        2. Pick the candidate most dissimilar to selected set.
        3. Repeat until K candidates are selected.

    Args:
        candidates: Pool of candidates to select from.
        k: Number of candidates to select.

    Returns:
        List of K diverse LoopCandidate objects with assigned colours/labels.
    """
    if len(candidates) <= k:
        selected = candidates
    else:
        selected = []
        remaining = list(candidates)

        # Step 1: pick best by quality
        remaining.sort(key=lambda c: c.quality_score, reverse=True)
        selected.append(remaining.pop(0))

        # Steps 2+: pick most dissimilar to current selection
        while len(selected) < k and remaining:
            best_idx = 0
            best_min_dissim = -1.0

            for i, candidate in enumerate(remaining):
                # Min dissimilarity to any selected route
                min_dissim = min(
                    1.0 - route_similarity(candidate.route, s.route)
                    for s in selected
                )
                if min_dissim > best_min_dissim:
                    best_min_dissim = min_dissim
                    best_idx = i

            selected.append(remaining.pop(best_idx))

    # Assign colours and semantic labels with explicit explainability.
    role_by_index = _assign_role_by_index(selected)
    extra_label_idx = 0

    for i, candidate in enumerate(selected):
        candidate.colour = LOOP_COLOURS[i % len(LOOP_COLOURS)]

        role = role_by_index.get(i, 'extra')
        if role in ROLE_LABELS:
            candidate.label = ROLE_LABELS[role]
        else:
            if EXTRA_LOOP_LABELS:
                candidate.label = EXTRA_LOOP_LABELS[extra_label_idx % len(EXTRA_LOOP_LABELS)]
            else:
                candidate.label = f'Alternative {extra_label_idx + 1}'
            extra_label_idx += 1

        _attach_name_explainability(candidate, i, selected, role)

    return selected


# ── Abstract base class ──────────────────────────────────────────────────────

class LoopSolverBase(ABC):
    """
    Abstract base for loop routing algorithms.

    All solvers receive the same input parameters and return
    standardised output format for frontend compatibility.

    Subclasses must implement ``find_loops()``.
    """

    @abstractmethod
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
        prefer_dedicated_pavements: bool = False,
        prefer_nature_trails: bool = False,
        prefer_paved: bool = False,
        prefer_lit: bool = False,
        avoid_unsafe_roads: bool = False,
        heavily_avoid_unlit: bool = False,
    ) -> List[LoopCandidate]:
        """
        Find multiple loop route candidates.

        Args:
            graph: NetworkX MultiDiGraph with OSM data and scenic attributes.
            start_node: OSM node ID for loop start/end.
            target_distance: Target loop distance in metres.
            weights: WSM feature weights dict.
            combine_nature: If True, combine greenness+water into nature.
            directional_bias: Direction preference string.
            num_candidates: Number of candidates to return.
            distance_tolerance: Acceptable deviation fraction (e.g. 0.15 = ±15%).
            max_search_time: Maximum search time in seconds.
            variety_level: Route variety 0-3 (0 = deterministic, 3 = most varied).
            prefer_pedestrian: If True, strongly favour footpaths/cycleways.
            prefer_dedicated_pavements: If True, favour dedicated hard-surface active corridors.
            prefer_nature_trails: If True, favour trail-like roads/surfaces.
            prefer_paved: If True, penalise unpaved/soft surfaces.
            prefer_lit: If True, penalise unlit streets and bonus lit ones.
            avoid_unsafe_roads: If True, heavily penalise main roads without sidewalks.
            heavily_avoid_unlit: If True, apply very strong unlit-avoidance penalties.

        Returns:
            List of LoopCandidate objects sorted by quality score.
            Empty list if no viable loops found.
        """
        pass
