"""
Elevation Processor Module

Fetches elevation data for graph nodes and calculates edge gradients.
Uses Open Topo Data API (AW3D30/SRTM datasets) via osmnx integration.

Edge attribute added: raw_slope_cost (absolute gradient as decimal, e.g. 0.1 = 10% grade)

NOTE: This module pre-computes elevation attributes on graph edges.
The actual cost weighting is NOT applied here - it will be integrated
into the modified A* WSM (Weighted Sum Model) algorithm later.
"""

from typing import Optional
import time
import networkx as nx

try:
    import osmnx as ox
except ImportError:
    ox = None

# Open Topo Data API configuration
# Uses ASTER Global DEM (~30m resolution) - similar to AW3D30
ELEVATION_URL_TEMPLATE = "https://api.opentopodata.org/v1/aster30m?locations={locations}"

# Batch size for API requests (Open Topo Data supports up to 100 per request)
BATCH_SIZE = 100

# Minimum edge length to process (metres) - skip very short edges
MIN_EDGE_LENGTH = 1.0


def configure_elevation_api() -> None:
    """
    Configure osmnx to use Open Topo Data API for elevation queries.
    
    Sets the elevation URL template to use the free Open Topo Data service
    which provides ASTER Global DEM data (~30m resolution).
    """
    if ox is None:
        print("[ElevationProcessor] WARNING: osmnx not available, skipping configuration")
        return
    
    ox.settings.elevation_url_template = ELEVATION_URL_TEMPLATE
    print(f"[ElevationProcessor] Configured elevation API: ASTER30m via Open Topo Data")


def fetch_node_elevations(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Fetch elevation data for all nodes in the graph.
    
    Uses osmnx.elevation module to query Open Topo Data API in batches.
    Adds 'elevation' attribute (metres above sea level) to each node.
    
    Args:
        graph: NetworkX MultiDiGraph with nodes containing 'x' (lon) and 'y' (lat).
    
    Returns:
        The same graph with 'elevation' attribute added to nodes.
    """
    if graph is None:
        return graph
    
    if ox is None:
        print("[ElevationProcessor] ERROR: osmnx not installed, cannot fetch elevations")
        return graph
    
    node_count = graph.number_of_nodes()
    print(f"[ElevationProcessor] Fetching elevations for {node_count} nodes...")
    
    # Configure the API before making requests
    configure_elevation_api()
    
    try:
        # osmnx handles batching internally based on settings.max_query_area_size
        # We use add_node_elevations which queries the configured API
        graph = ox.elevation.add_node_elevations(graph, batch_size=BATCH_SIZE)
        
        # Count successfully populated elevations
        elevations_added = sum(1 for _, data in graph.nodes(data=True) 
                               if data.get('elevation') is not None)
        print(f"[ElevationProcessor] Fetched elevations for {elevations_added}/{node_count} nodes")
        
    except Exception as e:
        print(f"[ElevationProcessor] ERROR fetching elevations: {e}")
        print("[ElevationProcessor] Proceeding without elevation data")
    
    return graph


def calculate_edge_gradient(length: float, elevation_u: Optional[float], 
                            elevation_v: Optional[float]) -> Optional[float]:
    """
    Calculate the absolute gradient (slope) for an edge.
    
    Uses absolute value because both uphill and downhill can be undesirable
    for walking routes.
    
    Formula: gradient = |elevation_change| / horizontal_distance
    
    Args:
        length: Edge length in metres (horizontal distance).
        elevation_u: Elevation of source node in metres (can be None).
        elevation_v: Elevation of target node in metres (can be None).
    
    Returns:
        Absolute gradient as a decimal (0.0 = flat, 0.1 = 10% grade).
        Returns None if elevation data is missing or edge too short.
    """
    # Handle missing elevation data
    if elevation_u is None or elevation_v is None:
        return None
    
    # Skip very short edges to avoid division instability
    if length < MIN_EDGE_LENGTH:
        return 0.0
    
    elevation_change = abs(elevation_v - elevation_u)
    gradient = elevation_change / length
    
    return gradient


def process_graph_elevation(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Process all edges to calculate and assign gradient attributes.
    
    Workflow:
    1. Fetch elevation data for all nodes (via Open Topo Data API)
    2. Calculate gradient for each edge using node elevations
    3. Store raw_slope_cost attribute on each edge
    
    The raw_slope_cost can later be used in the WSM A* algorithm:
        cost = w1 * length + w2 * raw_slope_cost * length
    
    Args:
        graph: NetworkX MultiDiGraph with edge 'length' attributes.
    
    Returns:
        The same graph with 'raw_slope_cost' added to edges.
    """
    if graph is None:
        return graph
    
    # Step 1: Fetch node elevations
    t0 = time.perf_counter()
    graph = fetch_node_elevations(graph)
    fetch_time = time.perf_counter() - t0
    print(f"  [Timer] Elevation fetch: {fetch_time:.2f}s")
    
    # Step 2: Calculate gradients for each edge
    edges_processed = 0
    edges_with_gradient = 0
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        # Get node elevations
        u_data = graph.nodes[u]
        v_data = graph.nodes[v]
        
        elevation_u = u_data.get('elevation')
        elevation_v = v_data.get('elevation')
        
        # Get edge length
        length = data.get('length', 0.0)
        
        # Calculate gradient
        gradient = calculate_edge_gradient(length, elevation_u, elevation_v)
        
        # Store on edge
        if gradient is not None:
            graph[u][v][key]['raw_slope_cost'] = gradient
            edges_with_gradient += 1
        else:
            # Default to 0.0 if no elevation data available
            graph[u][v][key]['raw_slope_cost'] = 0.0
        
        edges_processed += 1
    
    print(f"[ElevationProcessor] Processed {edges_processed} edges "
          f"({edges_with_gradient} with gradient data)")
    
    return graph
