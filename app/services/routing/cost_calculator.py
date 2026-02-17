"""
Cost Calculator Module

Provides pluggable cost functions for scenic routing with A*.
All scenic feature values must be normalised to 0.0-1.0 range before use.

Available cost functions (configure via config.py COST_FUNCTION):
    - WSM_ADDITIVE:       Pure Weighted Sum Model (AND semantics)
    - HYBRID_DISJUNCTIVE: Weighted-MIN (OR semantics) [default]

Usage:
    # Use the config-defined cost function (recommended)
    cost = compute_wsm_cost(norm_length, norm_green, ..., weights)
    
    # Or explicitly override for testing
    from cost_calculator import CostFunction, compute_cost
    cost = compute_cost(..., method=CostFunction.WSM_ADDITIVE)

See ADR-001 and ADR-003 for design rationale.
"""

from typing import Dict, Optional


# All normalised scenic values are stored as costs (0=good, 1=bad)
# This simplifies formulas - all features use direct weighting


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
        # Slope can be negative (-5 to 5) to indicate "Prefer Slope" vs "Avoid Slope"
        if key != 'slope' and value < 0:
            raise ValueError(f"Weight for '{key}' cannot be negative: {value}")
        validated[key] = float(value)
    
    return validated


# =============================================================================
# Cost Function Implementations
# =============================================================================
# Each function takes the same parameters for plug-and-play testing.
# All return a float cost value (lower is better).
# Configure which algorithm to use via config.py COST_FUNCTION setting.
# =============================================================================

from enum import Enum


class CostFunction(Enum):
    """Available cost function algorithms for scenic routing."""
    WSM_ADDITIVE = "WSM_ADDITIVE"           # Pure Weighted Sum Model (AND semantics)
    HYBRID_DISJUNCTIVE = "HYBRID_DISJUNCTIVE"  # Weighted-MIN (OR semantics)


def get_active_cost_function() -> CostFunction:
    """
    Get the currently configured cost function from config.
    
    Returns:
        CostFunction enum value based on config.py COST_FUNCTION setting.
    """
    try:
        from config import Config
        config_value = getattr(Config, 'COST_FUNCTION', 'HYBRID_DISJUNCTIVE')
        return CostFunction(config_value)
    except (ImportError, ValueError) as e:
        print(f"[Cost Calculator] Warning: Could not load config, using default: {e}")
        return CostFunction.HYBRID_DISJUNCTIVE


def _calculate_nature_cost(norm_green: float, norm_water: float, weight: float) -> float:
    """
    Combine green and water scores into a single nature score (best of both).
    
    When the user enables "Group Nature", greenery and water are treated as
    interchangeable scenic features. The best (lowest) score is used so that
    an edge near water OR in a green area is equally rewarded.
    
    Args:
        norm_green: Normalised greenness cost (0=green, 1=not green).
        norm_water: Normalised water cost (0=near water, 1=far from water).
        weight: Combined nature weight from the UI slider.
    
    Returns:
        Weighted nature cost contribution.
    """
    # min() selects the best score (lower is better)
    nature_cost = min(norm_green, norm_water)
    return weight * nature_cost


def cost_wsm_additive(
    norm_length: float,
    norm_green: float,
    norm_water: float,
    norm_social: float,
    norm_quiet: float,
    norm_slope: float,
    weights: Dict[str, float],
    combine_nature: bool = False
) -> float:
    """
    Pure Weighted Sum Model (AND semantics).
    
    Formula:
        Cost = w_d×l̂ + w_g×ĝ + w_w×ŵ + w_s×ŝ + w_q×q̂ + w_e×ê
    
    All criteria are summed. Being bad at ANY criterion adds penalty.
    
    Pros:
        - Simple, well-understood in MCDA literature
        - All criteria influence the result proportionally
    
    Cons:
        - Multi-criteria collapse: edges must be good at ALL criteria
        - An edge green but not near water gets penalised for water
    
    Args:
        norm_*: Normalised cost values (0=good, 1=bad)
        weights: Dictionary of feature weights (sum to 1.0)
    
    Returns:
        Combined cost value (lower is better).
    """
    cost = weights['distance'] * norm_length
    
    if combine_nature:
        # User wants "Nature" (best of green/water)
        cost += _calculate_nature_cost(norm_green, norm_water, weights['greenness'])
    else:
        cost += weights['greenness'] * norm_green
        cost += weights['water'] * norm_water
    
    cost += weights['social'] * norm_social
    cost += weights['quietness'] * norm_quiet
    
    # Handle slope preference (signed weight)
    slope_weight = weights['slope']
    if slope_weight >= 0:
        # Avoid Slope (Positive): Penalize high slope
        cost += slope_weight * norm_slope
    else:
        # Prefer Slope (Negative): Penalize LOW slope (flatness)
        # 1.0 - norm_slope means 0=steep (good), 1=flat (bad)
        cost += abs(slope_weight) * (1.0 - norm_slope)
    
    return cost


def cost_hybrid_disjunctive(
    norm_length: float,
    norm_green: float,
    norm_water: float,
    norm_social: float,
    norm_quiet: float,
    norm_slope: float,
    weights: Dict[str, float],
    combine_nature: bool = False
) -> float:
    """
    Hybrid Additive-Disjunctive with Weighted-MIN (OR semantics).
    
    Formula:
        adjusted_i = norm_i / (1 + weight_i)    # Higher weight = advantage
        best = min(adjusted values)              # Only best contributes
        Cost = w_d×l̂ + total_scenic × best × normalization
    
    Distance is additive; scenic criteria use disjunctive (OR) aggregation.
    Being good at ANY scenic criterion is rewarded; others are ignored.
    
    Pros:
        - No multi-criteria collapse
        - Weights determine priority in MIN competition
        - Slider increments have meaningful effect
    
    Cons:
        - Not pure WSM (academically different)
        - Over-rewards single-attribute edges
    
    Args:
        norm_*: Normalised cost values (0=good, 1=bad)
        weights: Dictionary of feature weights (sum to 1.0)
    
    Returns:
        Combined cost value (lower is better).
    """
    # Distance component always additive
    cost = weights['distance'] * norm_length
    
    # Collect active scenic criteria
    if combine_nature:
        # Combine green and water into a single nature score
        nature_score = min(norm_green, norm_water)
        scenic_data = [
            (nature_score, weights['greenness']),
            (norm_social, weights['social']),
            (norm_quiet, weights['quietness']),
        ]
    else:
        scenic_data = [
            (norm_green, weights['greenness']),
            (norm_water, weights['water']),
            (norm_social, weights['social']),
            (norm_quiet, weights['quietness']),
        ]
    
    # Add slope with signed logic
    slope_w = weights['slope']
    if slope_w >= 0:
        # Avoid Slope: standard penalty
        scenic_data.append((norm_slope, slope_w))
    else:
        # Prefer Slope: Penalize flat
        scenic_data.append((1.0 - norm_slope, abs(slope_w)))
    
    active = [(val, w) for val, w in scenic_data if w > 0]
    
    if active:
        # Weighted-MIN: divide by (1 + weight) so higher weights win
        adjusted_values = [(val / (1 + w), w) for val, w in active]
        best_adjusted = min(adj for adj, w in adjusted_values)
        
        total_scenic_weight = sum(w for val, w in active)
        avg_weight = total_scenic_weight / len(active)
        normalization_factor = 1 + avg_weight
        
        cost += total_scenic_weight * best_adjusted * normalization_factor
    
    return cost


def compute_cost(
    norm_length: float,
    norm_green: float,
    norm_water: float,
    norm_social: float,
    norm_quiet: float,
    norm_slope: float,
    weights: Dict[str, float],
    method: CostFunction = None,
    combine_nature: bool = False
) -> float:
    """
    Dispatcher function - routes to the active cost function.
    
    Args:
        norm_*: Normalised cost values (0=good, 1=bad)
        weights: Dictionary of feature weights
        method: Optional override for cost function (uses config.COST_FUNCTION if None)
        combine_nature: If True, combine greenness and water into a single "nature" score.
    
    Returns:
        Combined cost value (lower is better).
    """
    if method is None:
        method = get_active_cost_function()
    
    if method == CostFunction.WSM_ADDITIVE:
        return cost_wsm_additive(
            norm_length, norm_green, norm_water, 
            norm_social, norm_quiet, norm_slope, weights,
            combine_nature=combine_nature
        )
    elif method == CostFunction.HYBRID_DISJUNCTIVE:
        return cost_hybrid_disjunctive(
            norm_length, norm_green, norm_water,
            norm_social, norm_quiet, norm_slope, weights,
            combine_nature=combine_nature
        )
    else:
        raise ValueError(f"Unknown cost function: {method}")


# Backward compatibility alias
def compute_wsm_cost(
    norm_length: float,
    norm_green: float,
    norm_water: float,
    norm_social: float,
    norm_quiet: float,
    norm_slope: float,
    weights: Dict[str, float],
    combine_nature: bool = False
) -> float:
    """
    Backward-compatible wrapper. Uses the currently active cost function.
    
    See compute_cost(), cost_wsm_additive(), cost_hybrid_disjunctive() 
    for the actual implementations.
    """
    return compute_cost(
        norm_length, norm_green, norm_water,
        norm_social, norm_quiet, norm_slope, weights,
        combine_nature=combine_nature
    )


def normalise_ui_weights(ui_weights: Dict[str, float]) -> Dict[str, float]:
    """
    Convert UI slider values (0-5) to normalised weights.
    
    UI sliders use intuitive semantics where higher = more preference.
    This function converts to weights that sum to 1.0 for consistent
    cost scaling in the WSM formula.
    
    Args:
        ui_weights: Dictionary of feature names to slider values (0-5).
    
    Returns:
        Normalised weights dictionary (values sum to 1.0).
    """
    # All features use 0-5 scale for intuitive proportional weighting.
    # When user sets Greenery=5 and distance uses default 3:
    #   - Distance: 3/(3+5) = 37.5%
    #   - Greenery: 5/(3+5) = 62.5%
    #
    # See ADR-003 for rationale on 0-5 scale choice.
    #
    # Distance defaults to 3 (middle of 0-5 range) so routes aren't absurdly long,
    # but user can reduce it via the UI slider for more scenic freedom.
    defaults = {
        'distance': 3.0,    # Middle of 0-5 range, user can adjust via slider
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
    
    # Sum all values for normalisation (use absolute values)
    total = sum(abs(float(v)) for v in merged.values())
    
    if total == 0:
        # All sliders at zero - fall back to distance-only
        return {k: (1.0 if k == 'distance' else 0.0) for k in defaults}
    
    # Normalise to sum to 1.0 (magnitude)
    # Result preserves sign of original weight
    result = {k: float(v) / total for k, v in merged.items()}
    
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
