"""
WSM A* Implementation

Weighted Sum Model extension of A* for scenic routing.
Uses normalised feature costs combined with configurable weights
to find routes that balance distance with scenic preferences.
"""

from app.services.routing.astar.astar_lib import AStar
from app.services.routing.cost_calculator import (
    compute_wsm_cost,
    find_length_range,
    normalise_length,
    validate_weights,
    get_active_cost_function,
)
from app.services.processors.elevation import calculate_tobler_cost
from math import radians, cos, sin, asin, sqrt
import re
from typing import Dict, Optional


# ── Lit-tag penalty multipliers ──────────────────────────────────────────────
_LIT_PENALTY_BY_CLASS: Dict[str, float] = {
    'lit': 0.85,
    'limited': 1.3,
    'unlit': 1.8,
}
_LIT_DEFAULT: float = 1.2  # Unknown/missing lit tag

# "Heavily avoid unlit" uses much stronger penalties
_LIT_HEAVY_PENALTY_BY_CLASS: Dict[str, float] = {
    'lit': 1.0,
    'limited': 2.5,
    'unlit': 5000.0,
}
_LIT_HEAVY_DEFAULT: float = 500.0  # Unknown/missing → assume unlit

_VALID_LIGHTING_CONTEXTS = frozenset({'daylight', 'twilight', 'night'})

_ALL_NIGHT_REGIME_HINTS = (
    'all night', 'all_night', 'allnight', '24/7', '24h', '24 hour',
    'dusk to dawn', 'dusk-dawn', 'sunset to sunrise',
)
_PART_NIGHT_REGIME_HINTS = (
    'part night', 'part_night', 'partnight',
    'switch off', 'switch_off', 'switchoff',
    'midnight', 'curfew',
)

# Dedicated active-travel corridors often omit ``lit`` tagging.
# Treat unknown lighting on these as neutral rather than street-like risk.
_DEDICATED_PATH_HIGHWAY_TAGS = frozenset({
    'cycleway', 'path', 'footway', 'pedestrian', 'track', 'bridleway', 'steps'
})

# Stronger positive bias for designated paved active-travel corridors.
_ACTIVE_TRAVEL_HARD_SURFACE_TAGS = frozenset({
    'paved', 'asphalt', 'concrete', 'concrete:plates',
    'concrete:lanes', 'paving_stones',
})
_ACTIVE_TRAVEL_QUALITY_MULTIPLIER: Dict[str, float] = {
    'tier_a': 0.82,  # Both foot+bicycle designated
    'tier_b': 0.90,  # One designated marker
    'tier_c': 0.96,  # Generic yes marker
    'none': 1.0,
}

# Surface-type multipliers for "prefer paved surfaces"
_SURFACE_PENALTY: Dict[str, float] = {
    'paved': 1.0, 'asphalt': 1.0, 'concrete': 1.0,
    'concrete:plates': 1.0, 'concrete:lanes': 1.0, 'paving_stones': 1.0,
    'sett': 1.1, 'cobblestone': 1.1, 'cobblestone:flattened': 1.1,
    'metal': 1.1, 'wood': 1.1,
    'compacted': 1.3, 'fine_gravel': 1.3, 'gravel': 1.3,
    'dirt': 2.0, 'earth': 2.0, 'ground': 2.0, 'mud': 2.0,
    'sand': 2.0, 'grass': 2.0, 'grass_paver': 2.0, 'woodchips': 2.0,
}
_SURFACE_DEFAULT: float = 1.2

# Unsafe-road multiplier for "avoid unsafe roads"
_UNSAFE_HIGHWAY_TAGS = frozenset({
    'primary', 'primary_link', 'secondary', 'secondary_link',
    'tertiary', 'tertiary_link',
})
_SAFE_SIDEWALK_VALUES = frozenset({'both', 'left', 'right', 'yes', 'separate'})
_SAFE_FOOT_VALUES = frozenset({'yes', 'designated'})
_SAFE_CYCLEWAY_VALUES = frozenset({
    'lane', 'track', 'separate', 'yes',
    'shared_lane', 'share_busway',
    'opposite_lane', 'opposite_track',
})
_UNSAFE_ROAD_PENALTY: float = 15.0
_HIGH_SPEED_UNCLASSIFIED_THRESHOLD_KMH: float = 50.0
_HIGH_SPEED_UNCLASSIFIED_SEPARATED_PENALTY: float = 8.0
_UNCLASSIFIED_LAST_RESORT_PENALTY: float = 25.0

# Multiplicative noise penalty — applied when quietness weight is significant.
# Unlike the additive norm_quiet in the WSM formula, this multiplicative
# approach ensures noisy streets are genuinely avoided even on short edges.
_NOISE_MULTIPLIER_BY_HIGHWAY: Dict[str, float] = {
    'motorway': 12.0, 'motorway_link': 12.0,
    'trunk': 10.0, 'trunk_link': 8.0,
    'primary': 6.0, 'primary_link': 5.0,
    'secondary': 5.0, 'secondary_link': 4.0,
    'tertiary': 3.0, 'tertiary_link': 3.0,
    'unclassified': 2.0,
    'residential': 1.0, 'living_street': 1.0,
    'service': 1.0,
    'cycleway': 0.80, 'pedestrian': 0.80,
    'footway': 0.70, 'path': 0.70,
    'track': 0.75, 'bridleway': 0.75, 'steps': 0.85,
}
_NOISE_MULTIPLIER_DEFAULT: float = 1.5  # Unknown roads — assume moderate noise
# Minimum quietness weight (normalised) to activate multiplicative penalty.
_NOISE_MULTIPLIER_WEIGHT_THRESHOLD: float = 0.05

# Highway/surface groupings used by newer intent-led routing toggles.
_VEHICLE_FOCUSED_HIGHWAY_TAGS = frozenset({
    'motorway', 'motorway_link', 'trunk', 'trunk_link',
    'primary', 'primary_link', 'secondary', 'secondary_link',
    'tertiary', 'tertiary_link',
})
_NATURE_TRAIL_HIGHWAY_TAGS = frozenset({
    'path', 'track', 'bridleway', 'footway', 'steps',
})
_NATURE_TRAIL_SURFACE_TAGS = frozenset({
    'dirt', 'earth', 'ground', 'mud', 'sand', 'grass',
    'grass_paver', 'woodchips', 'gravel', 'fine_gravel', 'compacted',
})

# Runner-oriented separated-path tiers (lower multiplier = stronger preference).
_RUNNER_PATH_TIER_MULTIPLIER: Dict[str, float] = {
    'tier_1': 0.70,
    'tier_2': 0.82,
    'tier_3': 0.92,
    'tier_4': 0.97,
    'none': 1.0,
}
_RUNNER_PATH_PROW_BONUS: float = 0.93
_SEGREGATED_PATH_BONUS: float = 0.90

_SIDEWALK_FOOTWAY_VALUES = frozenset({'sidewalk'})
_SERVICE_HIGHWAY_TAGS = frozenset({'service'})
_SERVICE_BICYCLE_VALUES = frozenset({'yes', 'designated'})
_QUIET_SERVICE_LANE_MAX_SPEED_KMH: float = 30.0

_PUBLIC_RIGHT_OF_WAY_HINTS = (
    'designation',
    'public_footpath',
    'public footpath',
    'public_bridleway',
    'public bridleway',
    'public right of way',
    'prow',
)

_MAXSPEED_VALUE_PATTERN = re.compile(r'(\d+(?:\.\d+)?)')


def _primary_tag_value(value):
    """Normalise scalar/list edge tags to a lowercased comparable string."""
    if isinstance(value, list):
        value = value[0] if value else None
    if value is None:
        return None
    return str(value).strip().lower()


def _is_dedicated_path(edge_data: dict) -> bool:
    """True when edge is a non-motor active-travel corridor."""
    highway = _primary_tag_value(edge_data.get('highway'))
    return highway in _DEDICATED_PATH_HIGHWAY_TAGS


def _normalise_lighting_context(value: Optional[str]) -> str:
    """Return a supported lighting context value."""
    context = str(value or 'night').strip().lower()
    if context in _VALID_LIGHTING_CONTEXTS:
        return context
    return 'night'


def _normalise_lighting_regime(value) -> str:
    """Map raw regime tags to coarse classes used for routing decisions."""
    regime_raw = _primary_tag_value(value)
    if not regime_raw:
        return 'unknown'

    for hint in _ALL_NIGHT_REGIME_HINTS:
        if hint in regime_raw:
            return 'all_night'

    for hint in _PART_NIGHT_REGIME_HINTS:
        if hint in regime_raw:
            return 'part_night'

    return 'unknown'


def _base_lit_class(edge_data: dict) -> str:
    """Map raw ``lit`` tags into lit/limited/unlit/unknown classes."""
    lit_value = _primary_tag_value(edge_data.get('lit'))
    if lit_value in {'yes', 'automatic', '24/7'}:
        return 'lit'
    if lit_value in {'limited', 'disused'}:
        return 'limited'
    if lit_value == 'no':
        return 'unlit'
    return 'unknown'


def resolve_effective_lit_class(edge_data: dict, lighting_context: str = 'night') -> str:
    """Resolve the effective lighting class for current context and regime."""
    context = _normalise_lighting_context(lighting_context)

    base_class = _base_lit_class(edge_data)
    regime_class = _normalise_lighting_regime(edge_data.get('lighting_regime'))

    if regime_class == 'unknown':
        return base_class

    if regime_class == 'all_night':
        inferred = 'lit'
    else:
        inferred = 'limited' if context == 'twilight' else 'unlit'

    if base_class == 'unknown':
        return inferred
    if base_class == inferred:
        return base_class

    # Merge conservatively by choosing the riskier class.
    risk_order = {
        'lit': 0,
        'limited': 1,
        'unknown': 2,
        'unlit': 3,
    }
    return base_class if risk_order[base_class] >= risk_order[inferred] else inferred


def _compute_lit_multiplier(
    edge_data: dict,
    heavily_avoid: bool = False,
    lighting_context: str = 'night',
) -> float:
    """
    Multiplicative penalty (or bonus) based on the ``lit`` OSM tag.

    Returns < 1.0 for lit streets (bonus), > 1.0 for unlit/unknown.

    Args:
        edge_data: Edge attribute dictionary (may contain ``'lit'`` key).
        heavily_avoid: If True, use the much stronger penalty table.

    Returns:
        Multiplier to apply to edge cost.
    """
    context = _normalise_lighting_context(lighting_context)

    table = _LIT_HEAVY_PENALTY_BY_CLASS if heavily_avoid else _LIT_PENALTY_BY_CLASS
    default = _LIT_HEAVY_DEFAULT if heavily_avoid else _LIT_DEFAULT

    # Unknown lit status on dedicated paths is common.
    # Normally we assume they are safe (1.0), but if the user explicitly wants to
    # *heavily* avoid unlit areas, we must penalize these unknown dark paths too.
    dedicated_path_default = default if heavily_avoid else 1.0

    effective_lit_class = resolve_effective_lit_class(edge_data, lighting_context=context)
    if effective_lit_class in {'not_relevant', 'unknown'}:
        return dedicated_path_default
    return table.get(effective_lit_class, dedicated_path_default)


def _compute_surface_multiplier(edge_data: dict) -> float:
    """Multiplier for surface preference. Lower is better for paved surfaces."""
    surface = _primary_tag_value(edge_data.get('surface'))
    if surface is None:
        return _SURFACE_DEFAULT
    return _SURFACE_PENALTY.get(surface, _SURFACE_DEFAULT)


def _compute_unsafe_road_multiplier(edge_data: dict) -> float:
    """Heavy multiplier for unsafe major roads and high-speed unclassified links."""
    highway = _primary_tag_value(edge_data.get('highway'))
    if _has_pedestrian_safety_signal(edge_data):
        return 1.0

    if highway in _UNSAFE_HIGHWAY_TAGS:
        return _UNSAFE_ROAD_PENALTY

    # Many UK unclassified roads are effectively high-speed connectors.
    # When they lack foot/cycle safety signals, treat them as unsafe too.
    if _is_high_speed_unclassified_without_safety(edge_data):
        return _UNSAFE_ROAD_PENALTY

    return 1.0


def _compute_noise_multiplier(edge_data: dict) -> float:
    """Multiplicative noise penalty based on highway classification.

    Rewards quiet paths (footway, cycleway) with a small bonus and
    heavily penalises major arterial roads.  Works in tandem with the
    additive ``norm_quiet`` term in the WSM formula to ensure noisy
    roads are genuinely avoided, even on short edges where additive
    costs are too small to force rerouting.
    """
    highway = _primary_tag_value(edge_data.get('highway'))
    if highway is None:
        return _NOISE_MULTIPLIER_DEFAULT
    return _NOISE_MULTIPLIER_BY_HIGHWAY.get(highway, _NOISE_MULTIPLIER_DEFAULT)


def _compute_unclassified_lane_multiplier(
    edge_data: dict,
    avoid_unclassified_lanes: bool,
) -> float:
    """Strongly penalize unclassified lanes lacking safety cues (last-resort mode)."""
    if not avoid_unclassified_lanes:
        return 1.0

    if _is_unclassified_without_safety(edge_data):
        return _UNCLASSIFIED_LAST_RESORT_PENALTY

    return 1.0


def _has_pedestrian_safety_signal(edge_data: dict) -> bool:
    """True if edge has explicit sidewalk/foot access safety markers."""
    sidewalk = _primary_tag_value(edge_data.get('sidewalk'))
    if sidewalk in _SAFE_SIDEWALK_VALUES:
        return True

    foot = _primary_tag_value(edge_data.get('foot'))
    if foot in _SAFE_FOOT_VALUES:
        return True

    return False


def _has_cycleway_safety_signal(edge_data: dict) -> bool:
    """True if edge has explicit cycleway infrastructure markers."""
    cycleway = _primary_tag_value(edge_data.get('cycleway'))
    cycleway_both = _primary_tag_value(edge_data.get('cycleway:both'))
    return (
        cycleway in _SAFE_CYCLEWAY_VALUES
        or cycleway_both in _SAFE_CYCLEWAY_VALUES
    )


def _is_high_speed_unclassified_without_safety(edge_data: dict) -> bool:
    """Identify high-speed unclassified roads without foot/cycle safety cues."""
    if not _is_unclassified_without_safety(edge_data):
        return False

    maxspeed_kmh = _parse_maxspeed_kmh(edge_data.get('maxspeed'))
    if maxspeed_kmh is None:
        return False

    return maxspeed_kmh >= _HIGH_SPEED_UNCLASSIFIED_THRESHOLD_KMH


def _is_unclassified_without_safety(edge_data: dict) -> bool:
    """Identify unclassified roads without pedestrian/cycle safety cues."""
    highway = _primary_tag_value(edge_data.get('highway'))
    if highway != 'unclassified':
        return False

    if _has_pedestrian_safety_signal(edge_data) or _has_cycleway_safety_signal(edge_data):
        return False

    return True


def _parse_maxspeed_kmh(value) -> Optional[float]:
    """Parse OSM maxspeed values into km/h, or return None if unknown."""
    raw = _primary_tag_value(value)
    if raw is None:
        return None

    if raw in {'none', 'signals', 'walk', 'implicit', 'national', 'variable'}:
        return None

    match = _MAXSPEED_VALUE_PATTERN.search(raw)
    if not match:
        return None

    try:
        speed = float(match.group(1))
    except (TypeError, ValueError):
        return None

    if 'mph' in raw:
        speed *= 1.60934

    if speed <= 0:
        return None
    return speed


def _has_public_right_of_way_hint(edge_data: dict) -> bool:
    """True when designation-like tags hint at public-right-of-way access."""
    for field_name in ('designation', 'public_footpath', 'prow'):
        raw = _primary_tag_value(edge_data.get(field_name))
        if not raw:
            continue
        if any(hint in raw for hint in _PUBLIC_RIGHT_OF_WAY_HINTS):
            return True
    return False


def _is_quiet_service_lane(edge_data: dict) -> bool:
    """Identify low-speed service lanes with explicit pedestrian-friendly access."""
    highway = _primary_tag_value(edge_data.get('highway'))
    if highway not in _SERVICE_HIGHWAY_TAGS:
        return False

    maxspeed_kmh = _parse_maxspeed_kmh(edge_data.get('maxspeed'))
    if maxspeed_kmh is None or maxspeed_kmh > _QUIET_SERVICE_LANE_MAX_SPEED_KMH:
        return False

    surface = _primary_tag_value(edge_data.get('surface'))
    if surface in _NATURE_TRAIL_SURFACE_TAGS:
        return False

    sidewalk = _primary_tag_value(edge_data.get('sidewalk'))
    foot = _primary_tag_value(edge_data.get('foot'))
    bicycle = _primary_tag_value(edge_data.get('bicycle'))

    has_access_signal = (
        sidewalk in _SAFE_SIDEWALK_VALUES
        or foot in _SAFE_FOOT_VALUES
        or bicycle in _SERVICE_BICYCLE_VALUES
    )
    return has_access_signal


def classify_runner_path_tier(
    edge_data: dict,
    allow_quiet_service_lanes: bool = False,
) -> str:
    """Classify runner-priority tiers for separated-road-running preference."""
    highway = _primary_tag_value(edge_data.get('highway'))
    surface = _primary_tag_value(edge_data.get('surface'))
    foot = _primary_tag_value(edge_data.get('foot'))
    footway = _primary_tag_value(edge_data.get('footway'))

    foot_allowed = foot in _SAFE_FOOT_VALUES or foot in {'permissive'}

    # Tier 1: traffic-separated designated corridors.
    if highway in {'cycleway', 'path', 'pedestrian'} and foot_allowed:
        return 'tier_1'

    if highway == 'footway':
        # Tier 2: paved sidewalk footways with explicit pedestrian allowance.
        if (
            footway in _SIDEWALK_FOOTWAY_VALUES
            and surface in _ACTIVE_TRAVEL_HARD_SURFACE_TAGS
            and foot_allowed
        ):
            return 'tier_2'

        # Tier 3: paved footway without the stronger sidewalk+designation signal.
        if surface in _ACTIVE_TRAVEL_HARD_SURFACE_TAGS:
            return 'tier_3'

        if foot_allowed:
            return 'tier_1'

    # Tier 4: quiet service-lane fallback, gated by explicit toggle.
    if allow_quiet_service_lanes and _is_quiet_service_lane(edge_data):
        return 'tier_4'

    return 'none'


def _compute_dedicated_pavements_multiplier(
    edge_data: dict,
    allow_quiet_service_lanes: bool = False,
) -> float:
    """Bias towards separated runner-friendly corridors using explicit tiers."""
    highway = _primary_tag_value(edge_data.get('highway'))
    surface = _primary_tag_value(edge_data.get('surface'))
    tier = classify_runner_path_tier(
        edge_data,
        allow_quiet_service_lanes=allow_quiet_service_lanes,
    )

    multiplier = 1.0

    if highway in _VEHICLE_FOCUSED_HIGHWAY_TAGS:
        multiplier *= 10.0
    elif _is_high_speed_unclassified_without_safety(edge_data):
        multiplier *= _HIGH_SPEED_UNCLASSIFIED_SEPARATED_PENALTY

    multiplier *= _RUNNER_PATH_TIER_MULTIPLIER.get(tier, 1.0)

    # Keep the separated mode road-running oriented by rewarding paved and
    # discouraging soft trail-like surfaces on relevant tiers.
    if tier in {'tier_1', 'tier_2', 'tier_3'}:
        if surface in _ACTIVE_TRAVEL_HARD_SURFACE_TAGS:
            multiplier *= 0.90
        elif surface in _NATURE_TRAIL_SURFACE_TAGS:
            multiplier *= 1.25

    if tier == 'tier_1' and _has_public_right_of_way_hint(edge_data):
        multiplier *= _RUNNER_PATH_PROW_BONUS

    return multiplier


def _compute_segregated_bonus_multiplier(
    edge_data: dict,
    prefer_segregated_paths: bool,
) -> float:
    """Apply bonus-only segregated-path preference.

    Missing or non-"yes" segregated tags remain neutral.
    """
    if not prefer_segregated_paths:
        return 1.0

    segregated = _primary_tag_value(edge_data.get('segregated'))
    if segregated == 'yes':
        return _SEGREGATED_PATH_BONUS

    return 1.0


def _compute_nature_trails_multiplier(edge_data: dict) -> float:
    """Bias towards trail-like highways/surfaces and away from vehicle corridors."""
    highway = _primary_tag_value(edge_data.get('highway'))
    surface = _primary_tag_value(edge_data.get('surface'))

    multiplier = 1.0

    if highway in _VEHICLE_FOCUSED_HIGHWAY_TAGS:
        multiplier *= 4.0
    elif highway in {'residential', 'unclassified', 'service', 'living_street'}:
        multiplier *= 1.35
    elif highway in _NATURE_TRAIL_HIGHWAY_TAGS:
        multiplier *= 0.72

    if surface in _NATURE_TRAIL_SURFACE_TAGS:
        multiplier *= 0.78
    elif surface in _ACTIVE_TRAVEL_HARD_SURFACE_TAGS:
        multiplier *= 1.35

    # Generic path tag without detailed surface mapping should still get
    # a moderate trail preference.
    if highway in _NATURE_TRAIL_HIGHWAY_TAGS and surface is None:
        multiplier *= 0.90

    return multiplier


def classify_active_travel_quality_tier(edge_data: dict) -> str:
    """Classify quality tier for dedicated paved active-travel corridors."""
    if not _is_dedicated_path(edge_data):
        return 'none'

    surface = _primary_tag_value(edge_data.get('surface'))
    if surface not in _ACTIVE_TRAVEL_HARD_SURFACE_TAGS:
        return 'none'

    foot = _primary_tag_value(edge_data.get('foot'))
    bicycle = _primary_tag_value(edge_data.get('bicycle'))

    foot_designated = foot == 'designated'
    bicycle_designated = bicycle == 'designated'

    if foot_designated and bicycle_designated:
        return 'tier_a'
    if foot_designated or bicycle_designated:
        return 'tier_b'

    if foot in {'yes'} or bicycle in {'yes'}:
        return 'tier_c'

    return 'none'


def _compute_active_travel_quality_multiplier(
    edge_data: dict,
    prefer_segregated_paths: bool,
    prefer_dedicated_pavements: bool,
    prefer_paved: bool,
    avoid_unsafe_roads: bool,
) -> float:
    """Bonus multiplier for high-quality designated active-travel corridors."""
    if not (
        prefer_segregated_paths
        or prefer_dedicated_pavements
        or prefer_paved
        or avoid_unsafe_roads
    ):
        return 1.0

    tier = classify_active_travel_quality_tier(edge_data)
    return _ACTIVE_TRAVEL_QUALITY_MULTIPLIER.get(tier, 1.0)


def describe_edge_modifier_context(
    edge_data: dict,
    lighting_context: str = 'night',
    prefer_segregated_paths: bool = False,
    prefer_dedicated_pavements: bool = False,
    prefer_paved: bool = False,
    avoid_unsafe_roads: bool = False,
    allow_quiet_service_lanes: bool = False,
    avoid_unclassified_lanes: bool = False,
) -> Dict[str, object]:
    """Return derived modifier metadata for debugging/explainability."""
    resolved_context = _normalise_lighting_context(lighting_context)
    tier = classify_active_travel_quality_tier(edge_data)
    runner_tier = classify_runner_path_tier(
        edge_data,
        allow_quiet_service_lanes=allow_quiet_service_lanes,
    )

    return {
        'lighting_context': resolved_context,
        'effective_lit_class': resolve_effective_lit_class(
            edge_data,
            lighting_context=resolved_context,
        ),
        'active_travel_quality_tier': tier,
        'active_travel_quality_multiplier': _compute_active_travel_quality_multiplier(
            edge_data,
            prefer_segregated_paths=prefer_segregated_paths,
            prefer_dedicated_pavements=prefer_dedicated_pavements,
            prefer_paved=prefer_paved,
            avoid_unsafe_roads=avoid_unsafe_roads,
        ),
        'runner_path_tier': runner_tier,
        'runner_path_multiplier': _compute_dedicated_pavements_multiplier(
            edge_data,
            allow_quiet_service_lanes=allow_quiet_service_lanes,
        ),
        'segregated_bonus_multiplier': _compute_segregated_bonus_multiplier(
            edge_data,
            prefer_segregated_paths=prefer_segregated_paths,
        ),
        'unclassified_lane_multiplier': _compute_unclassified_lane_multiplier(
            edge_data,
            avoid_unclassified_lanes=avoid_unclassified_lanes,
        ),
    }


class WSMNetworkXAStar(AStar):
    """
    A* implementation using Weighted Sum Model cost function.
    
    Extends the base AStar class to use a combined cost that weights
    distance against scenic features (greenness, water, quietness, etc.).
    
    Attributes:
        graph: NetworkX MultiDiGraph with normalised scenic attributes.
        weights: Feature weight dictionary for WSM calculation.
        min_length: Minimum edge length in graph (for normalisation).
        max_length: Maximum edge length in graph (for normalisation).
        prefer_lit: Apply mild lit-preference penalties.
        heavily_avoid_unlit: Apply strong unlit-avoidance penalties.
        prefer_dedicated_pavements: Favour designated hard-surface active routes.
        prefer_nature_trails: Favour trail-like highways and softer surfaces.
        prefer_paved: Prefer paved surfaces by penalising soft/unpaved tags.
        avoid_unsafe_roads: Penalise major roads lacking foot safety indicators.
        lighting_context: Request-scoped context (`daylight|twilight|night`).
    """

    def __init__(
        self, 
        graph, 
        weights: Optional[Dict[str, float]] = None,
        length_range: Optional[tuple[float, float]] = None,
        combine_nature: bool = False,
        prefer_lit: bool = False,
        heavily_avoid_unlit: bool = False,
        prefer_dedicated_pavements: bool = False,
        prefer_nature_trails: bool = False,
        prefer_pedestrian: bool = False,
        prefer_segregated_paths: bool = False,
        allow_quiet_service_lanes: bool = False,
        prefer_paved: bool = False,
        avoid_unsafe_roads: bool = False,
        avoid_unclassified_lanes: bool = False,
        activity: str = 'walking',
        lighting_context: str = 'night',
    ):
        """
        Initialise WSM A* solver.
        
        Args:
            graph: NetworkX MultiDiGraph with norm_* edge attributes.
            weights: Feature weights dictionary. If None, uses equal weights.
            length_range: Pre-computed (min, max) length tuple. If None, computed from graph.
            combine_nature: If True, combine greenness and water into a single "nature" score.
            prefer_lit: If True, apply mild multiplicative lit-preference penalty.
            heavily_avoid_unlit: If True, apply strong multiplicative unlit-avoidance penalty (overrides prefer_lit).
            prefer_dedicated_pavements: If True, favour designated hard-surface active-travel corridors.
            prefer_nature_trails: If True, favour trail-like highways and natural surfaces.
            lighting_context: Lighting relevance context (`daylight`, `twilight`, `night`).
        """
        self.graph = graph
        self.combine_nature = combine_nature
        self.prefer_lit = prefer_lit
        self.heavily_avoid_unlit = heavily_avoid_unlit
        self.prefer_dedicated_pavements = prefer_dedicated_pavements
        self.prefer_nature_trails = prefer_nature_trails
        self.prefer_segregated_paths = bool(prefer_segregated_paths or prefer_pedestrian)
        # Backward-compatible alias used by older call paths/tests.
        self.prefer_pedestrian = self.prefer_segregated_paths
        self.allow_quiet_service_lanes = allow_quiet_service_lanes
        self.prefer_paved = prefer_paved
        self.avoid_unsafe_roads = avoid_unsafe_roads
        self.avoid_unclassified_lanes = avoid_unclassified_lanes
        self.lighting_context = _normalise_lighting_context(lighting_context)
        activity_norm = str(activity or 'walking').strip().lower()
        self.activity = 'running' if activity_norm.startswith('running') else 'walking'

        # Keep solver behavior deterministic and safe even when UI constraints
        # are bypassed by direct API callers.
        if self.heavily_avoid_unlit:
            self.prefer_lit = False
        if self.prefer_nature_trails:
            self.prefer_dedicated_pavements = False
            self.prefer_paved = False
            self.prefer_segregated_paths = False
            self.prefer_pedestrian = False
            self.allow_quiet_service_lanes = False
        if not self.prefer_dedicated_pavements:
            self.allow_quiet_service_lanes = False
        
        # Validate and set weights
        if weights is None:
            weights = {
                'distance': 0.5,
                'greenness': 0.1,
                'water': 0.1,
                'quietness': 0.1,
                'social': 0.1,
                'slope': 0.1,
            }
        self.weights = validate_weights(weights)
        
        # Log which cost function algorithm is being used (once per route)
        cost_func = get_active_cost_function()
        lit_mode = 'heavily_avoid_unlit' if heavily_avoid_unlit else ('prefer_lit' if prefer_lit else 'off')
        print(
            f"[WSM A*] Using cost function: {cost_func.value}, "
            f"lit_mode: {lit_mode}, "
            f"dedicated_mode: {'on' if self.prefer_dedicated_pavements else 'off'}, "
            f"trail_mode: {'on' if self.prefer_nature_trails else 'off'}, "
            f"segregated_mode: {'on' if self.prefer_segregated_paths else 'off'}, "
            f"quiet_service_mode: {'on' if self.allow_quiet_service_lanes else 'off'}, "
            f"paved_mode: {'on' if self.prefer_paved else 'off'}, "
            f"unsafe_mode: {'on' if self.avoid_unsafe_roads else 'off'}, "
            f"unclassified_last_resort_mode: {'on' if self.avoid_unclassified_lanes else 'off'}, "
            f"activity: {self.activity}, "
            f"lighting_context: {self.lighting_context}"
        )
        
        # Get or compute length range for normalisation
        if length_range is not None:
            self.min_length, self.max_length = length_range
        else:
            self.min_length, self.max_length = find_length_range(graph)

        # Walking already matches precomputed norm_slope in graph edges.
        # Running profiles need activity-aware Tobler re-scaling for slope cost.
        self.activity_slope_range = None
        if self.activity != 'walking':
            self.activity_slope_range = self._calculate_activity_slope_range()

    def _calculate_activity_slope_range(self) -> Optional[tuple[float, float]]:
        """Compute graph-wide Tobler slope-cost range for current activity."""
        min_cost = float('inf')
        max_cost = float('-inf')

        for _, _, _, data in self.graph.edges(keys=True, data=True):
            uphill = data.get('uphill_gradient')
            downhill = data.get('downhill_gradient')
            if uphill is None and downhill is None:
                continue

            signed_gradient = float(uphill or 0.0) - float(downhill or 0.0)
            slope_cost = calculate_tobler_cost(signed_gradient, activity=self.activity)
            min_cost = min(min_cost, slope_cost)
            max_cost = max(max_cost, slope_cost)

        if min_cost == float('inf') or max_cost == float('-inf'):
            return None

        return (min_cost, max_cost)

    def _resolve_norm_slope(self, data: dict) -> float:
        """Return edge slope cost normalised for configured activity."""
        default_norm_slope = float(data.get('norm_slope', 0.5))

        if self.activity == 'walking':
            return default_norm_slope

        uphill = data.get('uphill_gradient')
        downhill = data.get('downhill_gradient')
        if uphill is None and downhill is None:
            return default_norm_slope

        if not self.activity_slope_range:
            return default_norm_slope

        min_cost, max_cost = self.activity_slope_range
        if max_cost <= min_cost:
            return default_norm_slope

        signed_gradient = float(uphill or 0.0) - float(downhill or 0.0)
        slope_cost = calculate_tobler_cost(signed_gradient, activity=self.activity)
        norm_slope = (slope_cost - min_cost) / (max_cost - min_cost)
        return max(0.0, min(1.0, norm_slope))

    def neighbors(self, node):
        """
        Returns the list of neighbours for a given node.
        
        Args:
            node: OSM node ID.
        
        Returns:
            List of neighbouring node IDs.
        """
        return list(self.graph.neighbors(node))

    def distance_between(self, n1, n2) -> float:
        """
        Compute the WSM cost between two adjacent nodes.
        
        Uses the Weighted Sum Model formula combining normalised distance
        with normalised scenic features according to configured weights.
        
        Args:
            n1: Source node ID.
            n2: Target node ID.
        
        Returns:
            WSM cost value (lower is better).
        """
        edges = self.graph[n1][n2]
        if not edges:
            return float('inf')
        
        # Get data from the first edge (shortest if multiple)
        # Find edge with minimum length
        best_cost = float('inf')
        
        for data in edges.values():
            length = data.get('length', float('inf'))
            if length == float('inf'):
                continue
            
            # Normalise length to 0-1 range
            norm_length = normalise_length(length, self.min_length, self.max_length)
            
            # Get normalised scenic attributes (default to 0.5 if missing)
            norm_green = data.get('norm_green', 0.5)
            norm_water = data.get('norm_water', 0.5)
            norm_social = data.get('norm_social', 0.5)
            norm_quiet = data.get('norm_quiet', 0.5)
            norm_slope = self._resolve_norm_slope(data)
            
            # Compute WSM cost
            cost = compute_wsm_cost(
                norm_length=norm_length,
                norm_green=norm_green,
                norm_water=norm_water,
                norm_social=norm_social,
                norm_quiet=norm_quiet,
                norm_slope=norm_slope,
                weights=self.weights,
                combine_nature=self.combine_nature
            )
            
            # Apply lit-preference multiplier (if enabled)
            if self.heavily_avoid_unlit or self.prefer_lit:
                cost *= _compute_lit_multiplier(
                    data,
                    heavily_avoid=self.heavily_avoid_unlit,
                    lighting_context=self.lighting_context,
                )
            
            # Prefer dedicated paved active-travel corridors (road running).
            if self.prefer_dedicated_pavements:
                cost *= _compute_dedicated_pavements_multiplier(
                    data,
                    allow_quiet_service_lanes=self.allow_quiet_service_lanes,
                )

            # Prefer trail-like paths and natural surfaces (trail running).
            if self.prefer_nature_trails:
                cost *= _compute_nature_trails_multiplier(data)

            # Apply paved-surface preference multiplier (if enabled)
            if self.prefer_paved:
                cost *= _compute_surface_multiplier(data)

            # Apply unsafe-road avoidance multiplier (if enabled)
            if self.avoid_unsafe_roads:
                cost *= _compute_unsafe_road_multiplier(data)

            # Apply multiplicative noise penalty when quietness is weighted.
            if self.weights.get('quietness', 0) >= _NOISE_MULTIPLIER_WEIGHT_THRESHOLD:
                cost *= _compute_noise_multiplier(data)

            # Last-resort mode for narrow country lanes mapped as unclassified.
            cost *= _compute_unclassified_lane_multiplier(
                data,
                avoid_unclassified_lanes=self.avoid_unclassified_lanes,
            )

            # Apply designated active-travel quality bonus when safety/accessibility
            # toggles are active.
            cost *= _compute_active_travel_quality_multiplier(
                data,
                prefer_segregated_paths=self.prefer_segregated_paths,
                prefer_dedicated_pavements=self.prefer_dedicated_pavements,
                prefer_paved=self.prefer_paved,
                avoid_unsafe_roads=self.avoid_unsafe_roads,
            )

            # Segregated preference is bonus-only; missing tags remain neutral.
            cost *= _compute_segregated_bonus_multiplier(
                data,
                prefer_segregated_paths=self.prefer_segregated_paths,
            )
            
            # Debug logging for first few edges (to see greenness variance)
            if not hasattr(self, '_debug_count'):
                self._debug_count = 0
            if self._debug_count < 10:
                _hw = _primary_tag_value(data.get('highway'))
                _nm = _compute_noise_multiplier(data) if self.weights.get('quietness', 0) >= _NOISE_MULTIPLIER_WEIGHT_THRESHOLD else 1.0
                print(f"[WSM Debug] Edge {n1}->{n2}: hw={_hw}, norm_quiet={norm_quiet:.3f}, noise_mult={_nm:.1f}, norm_length={norm_length:.3f}, cost={cost:.4f}")
                self._debug_count += 1
            
            if cost < best_cost:
                best_cost = cost
        
        return best_cost

    def heuristic_cost_estimate(self, current, goal) -> float:
        """
        Compute the estimated cost to the goal using dual-bound heuristic.
        
        The heuristic must be admissible (never overestimate) to guarantee
        optimal paths. We use:
        - Distance component: straight-line distance normalised by max edge length
        - Scenic components: assumed to be 0 (best case - optimistic bound)
        
        This is admissible because:
        1. Haversine distance ≤ actual path distance (straight line is shortest)
        2. Actual scenic costs ≥ 0 (we assume 0, reality can only be worse)
        
        Formula: h(n) = w_d × (haversine / max_edge_length) + 0
        
        Args:
            current: Current node ID.
            goal: Goal node ID.
        
        Returns:
            Estimated cost to reach goal from current node.
        """
        # Get coordinates from graph nodes
        current_data = self.graph.nodes[current]
        goal_data = self.graph.nodes[goal]
        
        current_lat = current_data.get('y', current_data.get('lat', 0))
        current_lon = current_data.get('x', current_data.get('lon', 0))
        goal_lat = goal_data.get('y', goal_data.get('lat', 0))
        goal_lon = goal_data.get('x', goal_data.get('lon', 0))
        
        # Calculate straight-line distance in metres
        straight_line_distance = self._haversine(current_lat, current_lon, goal_lat, goal_lon)
        
        # Normalise by max edge length (same scale as edge costs)
        # Note: can exceed 1.0 if distance > max_edge, which is valid
        if self.max_length > 0:
            normalised_distance = straight_line_distance / self.max_length
        else:
            normalised_distance = 0.0
        
        # Apply distance weight only; assume scenic costs = 0 (optimistic bound)
        # This guarantees admissibility: h(n) ≤ actual remaining cost
        h = self.weights.get('distance', 0.5) * normalised_distance
        
        return h

    def _haversine(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Calculate great circle distance between two points.
        
        Args:
            lat1, lon1: First point coordinates (decimal degrees).
            lat2, lon2: Second point coordinates (decimal degrees).
        
        Returns:
            Distance in metres.
        """
        lon1, lat1, lon2, lat2 = map(radians, [lon1, lat1, lon2, lat2])
        
        dlon = lon2 - lon1
        dlat = lat2 - lat1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * asin(sqrt(a))
        r = 6371000  # Earth radius in metres
        return c * r
