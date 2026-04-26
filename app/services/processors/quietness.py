"""
Quietness Processor Module

Assigns noise factors to graph edges based on OSM highway tags.
Based on Wang et al. (2021) research validating road hierarchy as a proxy for traffic noise.

Higher noise_factor = quieter road = lower cost when routing for quiet paths.

Edge attributes added:
- noise_factor: Multi-tier classification (1.0 = very noisy … 5.0 = very quiet)
- raw_quiet_cost: Inverted cost for normalisation (lower = quieter)
"""

from typing import Optional
import networkx as nx

# Multi-tier noise classification (higher value = quieter = more desirable)
# Wider spread (1.0 to 5.0) gives normalisation much more room to
# differentiate road types, making "prefer quiet" routing effective.
NOISE_TIERS: dict = {
    # Tier 1 — Very noisy (dual carriageways, motorways)
    'motorway': 1.0, 'motorway_link': 1.0,
    'trunk': 1.0, 'trunk_link': 1.2,
    # Tier 2 — Noisy (major urban arterials)
    'primary': 1.5, 'primary_link': 1.7,
    # Tier 3 — Moderate (collector roads)
    'secondary': 2.0, 'secondary_link': 2.2,
    # Tier 4 — Calm (local distributor roads)
    'tertiary': 2.8, 'tertiary_link': 2.8,
    'unclassified': 3.0,
    # Tier 5 — Quiet (residential streets)
    'residential': 3.5, 'living_street': 4.0,
    'service': 3.5,
    # Tier 6 — Very quiet (dedicated active-travel paths)
    'cycleway': 4.5, 'pedestrian': 4.5,
    'footway': 5.0, 'path': 5.0,
    'track': 4.8, 'bridleway': 4.8, 'steps': 4.5,
}

NOISE_FACTOR_DEFAULT: float = 2.5  # Unknown roads — assumed moderate


def classify_highway(highway_tag: Optional[str]) -> float:
    """
    Classify a highway tag into a noise factor.
    
    Uses a multi-tier lookup (1.0 = very noisy … 5.0 = very quiet)
    to provide fine-grained differentiation between road types.
    
    Args:
        highway_tag: The OSM highway tag value (e.g., 'residential', 'primary').
                     Can be None if tag is missing.
    
    Returns:
        float: Noise factor (1.0 = very noisy … 5.0 = very quiet)
    """
    if highway_tag is None:
        return NOISE_FACTOR_DEFAULT
    
    # Normalise to lowercase for consistent matching
    tag_lower = highway_tag.lower() if isinstance(highway_tag, str) else str(highway_tag).lower()
    
    return NOISE_TIERS.get(tag_lower, NOISE_FACTOR_DEFAULT)


def process_graph_quietness(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Process all edges in the graph to assign quietness attributes.
    
    Iterates through every edge and assigns:
    - noise_factor: Classification based on highway tag (1.0=noisy, 2.0=quiet, 1.5=neutral)
    - raw_quiet_cost: Inverted value for normalisation (lower = quieter)
    
    Args:
        graph: NetworkX MultiDiGraph with edge attributes including 'highway'.
    
    Returns:
        nx.MultiDiGraph: The same graph object with quietness attributes added.
    """
    if graph is None:
        return graph
    
    edges_processed = 0
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        # Extract highway tag (may be string or list depending on pyrosm output)
        highway_tag = data.get('highway')
        
        # Handle list case (some edges have multiple highway values)
        if isinstance(highway_tag, list):
            highway_tag = highway_tag[0] if highway_tag else None
        
        # Classify and assign noise factor
        noise_factor = classify_highway(highway_tag)
        
        # Update edge attributes in-place
        graph[u][v][key]['noise_factor'] = noise_factor
        
        edges_processed += 1
    
    print(f"[QuietnessProcessor] Processed {edges_processed} edges with noise_factor attribute.")
    
    return graph

