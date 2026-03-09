"""
Distinct Paths Runner Module

Implements the multi-route strategy that runs A* three times per request,
returning Baseline, Extremist, and Balanced route alternatives.

This approximates the Pareto frontier for multi-criteria routing without
the computational expense of evolutionary algorithms.

Route Types:
    - Baseline: Pure shortest path by distance
    - Extremist: Maximises user's strongest scenic preference
    - Balanced: Uses user's actual weight configuration
"""

from typing import Dict, List, Optional, Tuple, Any
from flask import current_app


# Colour mapping for route visualisation
ROUTE_COLOURS = {
    'baseline': '#808080',      # Grey - neutral shortest path
    'balanced': '#3B82F6',      # Blue - user's balanced choice
    'greenness': '#22C55E',     # Green - nature preference
    'water': '#06B6D4',         # Cyan - water preference
    'quietness': '#A855F7',     # Purple - quietness preference
    'social': '#F97316',        # Orange - social/POI preference
    'slope': '#78716C',         # Brown/stone - flat terrain preference
}

# Priority order for tie-breaking when multiple weights share max value
FEATURE_PRIORITY = ['greenness', 'water', 'quietness', 'social', 'slope']


def generate_baseline_weights() -> Dict[str, float]:
    """
    Generate weights for baseline (shortest distance) route.
    
    Returns:
        Weight dictionary with distance=1.0, all others=0.
    """
    return {
        'distance': 1.0,
        'greenness': 0.0,
        'water': 0.0,
        'quietness': 0.0,
        'social': 0.0,
        'slope': 0.0,
    }


def find_dominant_feature(user_weights: Dict[str, float]) -> str:
    """
    Identify the scenic feature with the highest weight from user input.
    
    Uses priority order for tie-breaking when multiple features share
    the maximum weight value.
    
    Args:
        user_weights: Dictionary of user-provided feature weights.
    
    Returns:
        Name of the dominant scenic feature.
    """
    scenic_weights = {
        k: user_weights.get(k, 0.0) 
        for k in FEATURE_PRIORITY
    }
    
    if not scenic_weights or all(v <= 0 for v in scenic_weights.values()):
        # No scenic weights set - default to greenness
        return 'greenness'
    
    max_weight = max(scenic_weights.values())
    
    # Use priority order for tie-breaking
    for feature in FEATURE_PRIORITY:
        if scenic_weights.get(feature, 0.0) == max_weight:
            return feature
    
    return 'greenness'


def generate_extremist_weights(user_weights: Dict[str, float]) -> Tuple[Dict[str, float], str]:
    """
    Generate weights for extremist route that maximises the user's strongest preference.
    
    Args:
        user_weights: Dictionary of user-provided feature weights.
    
    Returns:
        Tuple of (weight dictionary, dominant feature name).
    """
    dominant = find_dominant_feature(user_weights)
    
    weights = {
        'distance': 0.1,  # Small but non-zero for heuristic admissibility
        'greenness': 0.0,
        'water': 0.0,
        'quietness': 0.0,
        'social': 0.0,
        'slope': 0.0,
    }
    weights[dominant] = 1.0
    
    return weights, dominant


def get_extremist_colour(dominant_feature: str) -> str:
    """
    Get the appropriate colour for an extremist route based on dominant feature.
    
    Args:
        dominant_feature: Name of the maximised scenic feature.
    
    Returns:
        Hex colour code for the route.
    """
    return ROUTE_COLOURS.get(dominant_feature, ROUTE_COLOURS['balanced'])


def find_distinct_paths(
    route_finder,
    start_point: Tuple[float, float],
    end_point: Tuple[float, float],
    user_weights: Dict[str, float],
    verbose: Optional[bool] = None,
    combine_nature: bool = False,
    prefer_lit: bool = False,
    heavily_avoid_unlit: bool = False,
    prefer_pedestrian: bool = False,
) -> Dict[str, Any]:
    """
    Execute three A* runs to find distinct route alternatives.
    
    Args:
        route_finder: Initialised RouteFinder instance with graph.
        start_point: (lat, lon) start coordinates.
        end_point: (lat, lon) end coordinates.
        user_weights: Normalised user weight dictionary.
        verbose: Enable verbose logging. If None, uses Flask config.
    
    Returns:
        Dictionary containing three routes with their stats:
        {
            'baseline': {'route': [...], 'distance': float, 'time': float},
            'extremist': {'route': [...], 'distance': float, 'time': float, 'dominant_feature': str},
            'balanced': {'route': [...], 'distance': float, 'time': float}
        }
    """
    # Determine verbose setting - explicit param takes priority over Flask config
    if verbose is None:
        try:
            verbose = current_app.config.get('VERBOSE_LOGGING', False)
        except RuntimeError:
            # Outside Flask context (e.g. testing)
            verbose = False
    
    if verbose:
        print("[Distinct Paths] Starting multi-route calculation")
    
    result = {}
    
    # Run 1: Baseline (shortest distance)
    baseline_weights = generate_baseline_weights()
    if verbose:
        print(f"[Distinct Paths] Run 1 - Baseline weights: {baseline_weights}")
    
    route_baseline, _, _, dist_baseline, time_baseline = route_finder.find_route(
        start_point, end_point,
        use_wsm=False,
        weights=baseline_weights,
        combine_nature=combine_nature,
        prefer_lit=False,              # Baseline must be pure shortest path
        heavily_avoid_unlit=False,     # No lit modifiers on Direct route
        prefer_pedestrian=False,       # No pedestrian modifiers on Direct route
    )
    
    result['baseline'] = {
        'route': route_baseline,
        'distance': dist_baseline,
        'time_seconds': time_baseline,
        'colour': ROUTE_COLOURS['baseline'],
    }
    
    # Run 2: Extremist (maximise strongest preference)
    extremist_weights, dominant_feature = generate_extremist_weights(user_weights)
    if verbose:
        print(f"[Distinct Paths] Run 2 - Extremist weights: {extremist_weights}")
        print(f"[Distinct Paths] Dominant feature: {dominant_feature}")
    
    route_extremist, _, _, dist_extremist, time_extremist = route_finder.find_route(
        start_point, end_point,
        use_wsm=True,
        weights=extremist_weights,
        combine_nature=combine_nature,
        prefer_lit=prefer_lit,
        heavily_avoid_unlit=heavily_avoid_unlit,
        prefer_pedestrian=prefer_pedestrian,
    )
    
    result['extremist'] = {
        'route': route_extremist,
        'distance': dist_extremist,
        'time_seconds': time_extremist,
        'dominant_feature': dominant_feature,
        'colour': get_extremist_colour(dominant_feature),
    }
    
    # Run 3: Balanced (user's actual configuration)
    if verbose:
        print(f"[Distinct Paths] Run 3 - Balanced weights: {user_weights}")
    
    route_balanced, _, _, dist_balanced, time_balanced = route_finder.find_route(
        start_point, end_point,
        use_wsm=True,
        weights=user_weights,
        combine_nature=combine_nature,
        prefer_lit=prefer_lit,
        heavily_avoid_unlit=heavily_avoid_unlit,
        prefer_pedestrian=prefer_pedestrian,
    )
    
    result['balanced'] = {
        'route': route_balanced,
        'distance': dist_balanced,
        'time_seconds': time_balanced,
        'colour': ROUTE_COLOURS['balanced'],
    }
    
    if verbose:
        print(f"[Distinct Paths] Complete - distances: "
              f"baseline={dist_baseline:.0f}m, "
              f"extremist={dist_extremist:.0f}m, "
              f"balanced={dist_balanced:.0f}m")
    
    return result
