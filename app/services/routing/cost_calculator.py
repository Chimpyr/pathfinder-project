"""
Cost Calculator Module

Provides the Weighted Sum Model (WSM) cost calculation for scenic routing.
All scenic feature values must be normalised to 0.0-1.0 range before use.

The WSM formula produces a single cost value combining distance and scenic
preferences, suitable for use in A* pathfinding algorithms.
"""

from typing import Dict, Optional


# All normalised scenic values are stored as costs (0=good, 1=bad)
# This simplifies the WSM formula - all features use direct weighting


def validate_weights(weights: Dict[str, float]) -> Dict[str, float]:
    """
    Validate and normalise weights dictionary.
    
    Ensures all required keys are present and weights are non-negative.
    Missing weights default to 0.0 (feature excluded from calculation).
    
    Args:
        weights: Dictionary of feature name to weight value.
    
    Returns:
        Validated weights dictionary with all required keys.
    
    Raises:
        ValueError: If any weight is negative.
    """
    required_keys = {'distance', 'greenness', 'water', 'quietness', 'social', 'slope'}
    
    validated = {}
    for key in required_keys:
        value = weights.get(key, 0.0)
        if value < 0:
            raise ValueError(f"Weight for '{key}' cannot be negative: {value}")
        validated[key] = float(value)
    
    return validated


def compute_wsm_cost(
    norm_length: float,
    norm_green: float,
    norm_water: float,
    norm_social: float,
    norm_quiet: float,
    norm_slope: float,
    weights: Dict[str, float]
) -> float:
    """
    Compute the Weighted Sum Model cost for an edge.
    
    Combines normalised distance with scenic feature costs using weighted sum.
    All normalised values are already in cost format (0=good, 1=bad) from
    the normalisation processor, so NO inversion is performed here.
    
    Formula:
        Cost = (w_d × l̂) + (w_g × ĝ) + (w_w × ŵ) + (w_s × ŝ) + (w_q × q̂) + (w_e × ê) + Penalty
    
    Where:
        - l̂ = normalised length (0=short, 1=long)
        - ĝ = normalised green cost (0=green, 1=no green)
        - ŵ = normalised water cost (0=water, 1=no water)
        - ŝ = normalised social cost (0=POIs, 1=no POIs)
        - q̂ = normalised quietness cost (0=quiet, 1=noisy)
        - ê = normalised slope cost (0=flat, 1=steep)
        - w_* = corresponding weights
    
    Args:
        norm_length: Normalised edge length (0.0-1.0).
        norm_green: Normalised green cost (0=green, 1=no green).
        norm_water: Normalised water cost (0=water, 1=no water).
        norm_social: Normalised social cost (0=POIs, 1=no POIs).
        norm_quiet: Normalised quietness cost (0=quiet, 1=noisy).
        norm_slope: Normalised slope cost (0=flat, 1=steep).
        weights: Dictionary of feature weights.
    
    Returns:
        Combined WSM cost value (lower is better).
    """
    # Distance component (longer is worse)
    cost = weights['distance'] * norm_length
    
    # All normalised values are already costs (0=good, 1=bad)
    # No inversion needed - higher weight means we penalise lack of feature more
    cost += weights['greenness'] * norm_green
    cost += weights['water'] * norm_water
    cost += weights['social'] * norm_social
    cost += weights['quietness'] * norm_quiet
    cost += weights['slope'] * norm_slope
    
    return cost


def normalise_ui_weights(ui_weights: Dict[str, float]) -> Dict[str, float]:
    """
    Convert UI slider values (0-100) to normalised weights.
    
    UI sliders use intuitive semantics where higher = more preference.
    This function converts to weights that sum to 1.0 for consistent
    cost scaling in the WSM formula.
    
    Args:
        ui_weights: Dictionary of feature names to slider values (0-100).
    
    Returns:
        Normalised weights dictionary (values sum to 1.0).
    """
    # All features use the same 0-10 scale for intuitive proportional weighting.
    # When user sets Greenery=10 and distance uses default 5:
    #   - Distance: 5/(5+10) = 33%
    #   - Greenery: 10/(5+10) = 67%
    #
    # With multiple features (e.g., Greenery=5, Quietness=5, Distance=5):
    #   - Each gets 5/15 = 33%
    #
    # Distance defaults to 5 (middle of range) so routes aren't absurdly long,
    # but user can reduce it via the UI slider for more scenic freedom.
    defaults = {
        'distance': 5.0,    # Middle of 0-10 range, user can adjust via slider
        'greenness': 0.0,   # Only if user explicitly wants green routes
        'water': 0.0,       # Only if user explicitly wants water proximity
        'quietness': 0.0,   # Only if user explicitly wants quiet routes
        'social': 0.0,      # Only if user explicitly wants social/POI routes
        'slope': 0.0,       # Only if user explicitly wants flat routes
    }
    
    # Merge with defaults
    merged = {**defaults, **ui_weights}
    
    # Apply minimum distance floor to ensure A* heuristic remains effective
    # Without this, distance=0 would cause weak heuristic and slow exploration
    MIN_DISTANCE_WEIGHT = 0.1  # Ensures ~1% distance influence at minimum
    merged['distance'] = max(MIN_DISTANCE_WEIGHT, merged['distance'])
    
    # Sum all values for normalisation
    total = sum(max(0.0, float(v)) for v in merged.values())
    
    if total == 0:
        # All sliders at zero - fall back to distance-only
        return {k: (1.0 if k == 'distance' else 0.0) for k in defaults}
    
    # Normalise to sum to 1.0
    result = {k: max(0.0, float(v)) / total for k, v in merged.items()}
    
    # Diagnostic logging
    print(f"[WSM Weights] Input: {ui_weights}")
    print(f"[WSM Weights] Merged: {merged}")
    print(f"[WSM Weights] Normalised: {result}")
    
    return result


def find_length_range(graph) -> tuple[float, float]:
    """
    Find the minimum and maximum edge lengths in a graph.
    
    Used to normalise edge lengths to the 0.0-1.0 range for consistent
    weighting against other normalised scenic features.
    
    Args:
        graph: NetworkX MultiDiGraph with 'length' edge attributes.
    
    Returns:
        Tuple of (min_length, max_length) in metres.
    """
    lengths = []
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        length = data.get('length')
        if length is not None and length > 0:
            lengths.append(length)
    
    if not lengths:
        return (0.0, 1.0)
    
    return (min(lengths), max(lengths))


def normalise_length(length: float, min_length: float, max_length: float) -> float:
    """
    Normalise an edge length to the 0.0-1.0 range.
    
    Args:
        length: Raw edge length in metres.
        min_length: Minimum length in the graph.
        max_length: Maximum length in the graph.
    
    Returns:
        Normalised length (0.0-1.0).
    """
    if max_length == min_length:
        return 0.0
    
    normalised = (length - min_length) / (max_length - min_length)
    return max(0.0, min(1.0, normalised))
