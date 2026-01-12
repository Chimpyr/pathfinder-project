"""
Normalisation Processor Module

Applies min-max normalisation to all scenic and slope cost attributes,
scaling them to a 0.0-1.0 range for consistent weighting in the WSM A* algorithm.

Supports two modes:
- STATIC: Copies pre-normalised values directly (green, water, social already 0-1)
- DYNAMIC: Rescales all attributes per-map so best edge = 0, worst = 1

Edge attributes added:
- norm_green: Normalised greenness cost (0 = green, 1 = no green)
- norm_water: Normalised water proximity cost (0 = water, 1 = no water)
- norm_social: Normalised social/POI cost (0 = POIs, 1 = no POIs)
- norm_quiet: Normalised quietness cost (0 = quiet, 1 = noisy)
- norm_slope: Normalised slope cost (0 = easy, 1 = steep)
"""

from typing import Dict, Optional, Tuple
import networkx as nx

# Attribute mapping: raw attribute -> (normalised attribute, needs_inversion)
# Inversion means higher raw value = lower normalised value
ATTRIBUTE_MAPPING = {
    'raw_green_cost': ('norm_green', False),
    'raw_water_cost': ('norm_water', False),
    'raw_social_cost': ('norm_social', False),
    'noise_factor': ('norm_quiet', True),      # Higher noise_factor = quieter = lower cost
    'slope_time_cost': ('norm_slope', False),
}

# Default values for missing attributes
DEFAULT_NORMALISED_VALUE = 0.5


def find_attribute_range(
    graph: nx.MultiDiGraph, 
    attr_name: str
) -> Tuple[Optional[float], Optional[float]]:
    """
    Find the minimum and maximum values for an attribute across all edges.
    
    Args:
        graph: NetworkX MultiDiGraph with edge attributes.
        attr_name: Name of the attribute to analyse.
    
    Returns:
        Tuple of (min_value, max_value), or (None, None) if attribute not found.
    """
    values = []
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        value = data.get(attr_name)
        if value is not None:
            values.append(value)
    
    if not values:
        return (None, None)
    
    return (min(values), max(values))


def normalise_value(
    value: float,
    min_val: float,
    max_val: float,
    invert: bool = False
) -> float:
    """
    Apply min-max normalisation to a single value.
    
    Formula: norm = (value - min) / (max - min)
    If inverted: norm = (max - value) / (max - min)
    
    Args:
        value: The raw value to normalise.
        min_val: Minimum value in the range.
        max_val: Maximum value in the range.
        invert: If True, higher raw values become lower normalised values.
    
    Returns:
        Normalised value in range 0.0-1.0.
    """
    # Handle edge case where all values are identical
    if max_val == min_val:
        return 0.0
    
    if invert:
        normalised = (max_val - value) / (max_val - min_val)
    else:
        normalised = (value - min_val) / (max_val - min_val)
    
    # Clamp to valid range
    return max(0.0, min(1.0, normalised))


def normalise_attribute(
    graph: nx.MultiDiGraph,
    raw_attr: str,
    norm_attr: str,
    invert: bool = False,
    dynamic: bool = False
) -> int:
    """
    Normalise a single attribute across all edges.
    
    Args:
        graph: NetworkX MultiDiGraph to modify in place.
        raw_attr: Name of the source attribute.
        norm_attr: Name of the target normalised attribute.
        invert: Whether to invert the normalisation.
        dynamic: If True, rescale per-map. If False, copy values directly
                 (for attributes already in 0-1 range).
    
    Returns:
        Number of edges normalised.
    """
    edges_normalised = 0
    
    if dynamic:
        # Find actual range in this graph
        min_val, max_val = find_attribute_range(graph, raw_attr)
        
        if min_val is None:
            # Attribute not present, use default
            for u, v, key in graph.edges(keys=True):
                graph[u][v][key][norm_attr] = DEFAULT_NORMALISED_VALUE
                edges_normalised += 1
            return edges_normalised
    else:
        # For static mode with pre-normalised attributes (0-1 range)
        # We still need range for attributes that need inversion or aren't 0-1
        min_val, max_val = find_attribute_range(graph, raw_attr)
        if min_val is None:
            min_val, max_val = 0.0, 1.0
    
    # Apply normalisation to all edges
    for u, v, key, data in graph.edges(keys=True, data=True):
        raw_value = data.get(raw_attr)
        
        if raw_value is not None:
            if dynamic or invert or raw_attr in ('noise_factor', 'slope_time_cost'):
                # Need to actually normalise
                norm_value = normalise_value(raw_value, min_val, max_val, invert)
            else:
                # Already 0-1, just copy
                norm_value = max(0.0, min(1.0, raw_value))
            
            graph[u][v][key][norm_attr] = norm_value
        else:
            graph[u][v][key][norm_attr] = DEFAULT_NORMALISED_VALUE
        
        edges_normalised += 1
    
    return edges_normalised


def normalise_graph_costs(
    graph: nx.MultiDiGraph,
    mode: str = 'STATIC'
) -> nx.MultiDiGraph:
    """
    Apply min-max normalisation to all scenic and slope cost attributes.
    
    Creates normalised versions of all raw cost attributes, scaling them
    to a consistent 0.0-1.0 range for use in the WSM A* algorithm.
    
    Args:
        graph: NetworkX MultiDiGraph with raw cost attributes.
        mode: Normalisation mode - 'STATIC' or 'DYNAMIC'.
              STATIC: Copies pre-normalised values, only scales unbounded attrs.
              DYNAMIC: Rescales all attributes per-map.
    
    Returns:
        The same graph with norm_* attributes added to all edges.
    """
    if graph is None:
        return graph
    
    dynamic = mode.upper() == 'DYNAMIC'
    
    print(f"[Normalisation] Mode: {mode.upper()}")
    
    stats: Dict[str, int] = {}
    
    for raw_attr, (norm_attr, invert) in ATTRIBUTE_MAPPING.items():
        count = normalise_attribute(graph, raw_attr, norm_attr, invert, dynamic)
        stats[norm_attr] = count
        
        # Log range for debugging
        min_val, max_val = find_attribute_range(graph, raw_attr)
        if min_val is not None:
            print(f"  {raw_attr}: range [{min_val:.3f}, {max_val:.3f}] -> {norm_attr}")
    
    total = sum(stats.values())
    print(f"[Normalisation] Normalised {len(ATTRIBUTE_MAPPING)} attributes across {total // len(ATTRIBUTE_MAPPING)} edges")
    
    return graph
