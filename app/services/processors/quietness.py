"""
Quietness Processor Module

Assigns noise factors to graph edges based on OSM highway tags.
Based on Wang et al. (2021) research validating road hierarchy as a proxy for traffic noise.

Higher noise_factor = quieter road = lower cost when routing for quiet paths.

Edge attributes added:
- noise_factor: Classification value (1.0=noisy, 2.0=quiet, 1.5=neutral)
- raw_quiet_cost: Inverted cost for normalisation (lower = quieter)
"""

from typing import Optional
import networkx as nx

# Highway tags associated with high traffic/noise
NOISY_TAGS: frozenset = frozenset({
    'motorway', 'motorway_link',
    'trunk', 'trunk_link', 
    'primary', 'primary_link',
    'secondary', 'secondary_link'
})

# Highway tags associated with low traffic/quiet environments
QUIET_TAGS: frozenset = frozenset({
    'residential', 'living_street',
    'footway', 'path', 'pedestrian',
    'cycleway', 'track', 'service',
    'bridleway', 'steps'
})

# Noise factor values (higher = quieter = more desirable for quiet routing)
NOISE_FACTOR_NOISY: float = 1.0
NOISE_FACTOR_QUIET: float = 2.0
NOISE_FACTOR_DEFAULT: float = 1.5  # Unknown/tertiary roads


def classify_highway(highway_tag: Optional[str]) -> float:
    """
    Classify a highway tag into a noise factor.
    
    Args:
        highway_tag: The OSM highway tag value (e.g., 'residential', 'primary').
                     Can be None if tag is missing.
    
    Returns:
        float: Noise factor (1.0=noisy, 2.0=quiet, 1.5=neutral/unknown)
    """
    if highway_tag is None:
        return NOISE_FACTOR_DEFAULT
    
    # Normalise to lowercase for consistent matching
    tag_lower = highway_tag.lower() if isinstance(highway_tag, str) else str(highway_tag).lower()
    
    if tag_lower in NOISY_TAGS:
        return NOISE_FACTOR_NOISY
    elif tag_lower in QUIET_TAGS:
        return NOISE_FACTOR_QUIET
    else:
        return NOISE_FACTOR_DEFAULT


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

