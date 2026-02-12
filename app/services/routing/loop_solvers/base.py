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

LOOP_COLOURS = [
    '#3B82F6',   # Blue   - primary / conservative
    '#22C55E',   # Green  - scenic / exploratory
    '#A855F7',   # Purple - directional / alternative
    '#F97316',   # Orange - fallback
    '#EF4444',   # Red    - additional
    '#06B6D4',   # Cyan   - additional
]

LOOP_LABELS = [
    'Conservative',
    'Scenic',
    'Exploratory',
    'Alternative',
    'Route 5',
    'Route 6',
]


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

    # Assign colours and labels
    for i, candidate in enumerate(selected):
        candidate.colour = LOOP_COLOURS[i % len(LOOP_COLOURS)]
        candidate.label = LOOP_LABELS[i % len(LOOP_LABELS)]

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

        Returns:
            List of LoopCandidate objects sorted by quality score.
            Empty list if no viable loops found.
        """
        pass
