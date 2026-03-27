"""
Elevation Processor Module

Fetches elevation data for graph nodes and calculates edge gradients.
Supports two modes:
- API: Remote lookup via Open Topo Data API (slower, no storage needed)
- LOCAL: Fast local lookup from downloaded Copernicus GLO-30 DEM tiles

Edge attributes added:
- raw_slope_cost: Absolute gradient (0.1 = 10% grade)
- uphill_gradient: Positive gradient when going uphill (0 if downhill)
- downhill_gradient: Positive gradient when going downhill (0 if uphill)
- slope_time_cost: Tobler's hiking function cost multiplier (1.0 = flat terrain)

The slope_time_cost uses Tobler's empirically-validated hiking function which
accurately models that mild downhill (~5%) is faster than flat terrain, whilst
steep gradients in either direction are slower.

NOTE: This module pre-computes elevation attributes on graph edges.
The actual cost weighting is applied in the A* WSM algorithm.
"""

from typing import Optional, Tuple
import time
import math
import networkx as nx

try:
    import osmnx as ox
except ImportError:
    ox = None

try:
    from app.services.core.dem_loader import DEMDataLoader, RASTERIO_AVAILABLE
except ImportError:
    DEMDataLoader = None
    RASTERIO_AVAILABLE = False

# Open Topo Data API configuration
# Uses ASTER Global DEM (~30m resolution) - similar to AW3D30
ELEVATION_URL_TEMPLATE = "https://api.opentopodata.org/v1/aster30m?locations={locations}"

# Batch size for API requests (Open Topo Data supports up to 100 per request)
BATCH_SIZE = 100

# Minimum edge length to process (metres) - skip very short edges
MIN_EDGE_LENGTH = 1.0

from config import Config
ACTIVITY_PARAMS = Config.ACTIVITY_PARAMS


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
    
    Uses Open Topo Data API directly since osmnx 2.0+ removed the
    generic add_node_elevations function.
    
    Args:
        graph: NetworkX MultiDiGraph with nodes containing 'x' (lon) and 'y' (lat).
    
    Returns:
        The same graph with 'elevation' attribute added to nodes.
    """
    import requests
    
    if graph is None:
        return graph
    
    node_count = graph.number_of_nodes()
    print(f"[ElevationProcessor] Fetching elevations for {node_count} nodes...")
    
    # Collect all node coordinates
    node_ids = list(graph.nodes())
    coords = [(graph.nodes[n].get('y'), graph.nodes[n].get('x')) for n in node_ids]
    
    elevations_added = 0
    
    try:
        # Process in batches
        for i in range(0, len(coords), BATCH_SIZE):
            batch_ids = node_ids[i:i + BATCH_SIZE]
            batch_coords = coords[i:i + BATCH_SIZE]
            
            # Format coordinates for API
            locations = "|".join(f"{lat},{lon}" for lat, lon in batch_coords)
            url = f"https://api.opentopodata.org/v1/aster30m?locations={locations}"
            
            response = requests.get(url, timeout=30)
            
            if response.status_code == 200:
                data = response.json()
                if data.get('status') == 'OK' and 'results' in data:
                    for node_id, result in zip(batch_ids, data['results']):
                        elevation = result.get('elevation')
                        if elevation is not None:
                            graph.nodes[node_id]['elevation'] = float(elevation)
                            elevations_added += 1
            else:
                print(f"[ElevationProcessor] API returned status {response.status_code}")
            
            # Rate limiting - Open Topo Data allows 1 request per second for free tier
            if i + BATCH_SIZE < len(coords):
                time.sleep(1.1)
        
        print(f"[ElevationProcessor] Fetched elevations for {elevations_added}/{node_count} nodes")
        
    except Exception as e:
        print(f"[ElevationProcessor] ERROR fetching elevations: {e}")
        print("[ElevationProcessor] Proceeding without elevation data")
    
    return graph


def fetch_node_elevations_local(graph: nx.MultiDiGraph) -> nx.MultiDiGraph:
    """
    Fetch elevation data using locally downloaded DEM tiles.
    
    Uses Copernicus GLO-30 dataset via DEMDataLoader for fast lookups.
    Tiles are downloaded once and cached for subsequent requests.
    
    Args:
        graph: NetworkX MultiDiGraph with nodes containing 'x' (lon) and 'y' (lat).
    
    Returns:
        The same graph with 'elevation' attribute added to nodes.
    """
    if graph is None:
        return graph
    
    if not RASTERIO_AVAILABLE or DEMDataLoader is None:
        print("[ElevationProcessor] WARNING: rasterio not available, falling back to API mode")
        return fetch_node_elevations(graph)
    
    node_count = graph.number_of_nodes()
    print(f"[ElevationProcessor] LOCAL mode: fetching elevations for {node_count} nodes...")
    
    # Initialise DEM loader
    loader = DEMDataLoader()
    
    # Collect all node coordinates
    node_ids = list(graph.nodes())
    coords = [(graph.nodes[n].get('y'), graph.nodes[n].get('x')) for n in node_ids]
    
    # Calculate bounding box for tile pre-download
    lats = [c[0] for c in coords if c[0] is not None]
    lons = [c[1] for c in coords if c[1] is not None]
    
    if lats and lons:
        bbox = (min(lats), min(lons), max(lats), max(lons))
        loader.ensure_tiles_for_bbox(bbox)
    
    # Batch lookup
    elevations = loader.get_elevations_batch(coords)
    
    # Assign to nodes
    elevations_added = 0
    for node_id, coord in zip(node_ids, coords):
        elevation = elevations.get(coord)
        if elevation is not None:
            graph.nodes[node_id]['elevation'] = elevation
            elevations_added += 1
    
    print(f"[ElevationProcessor] LOCAL mode: assigned {elevations_added}/{node_count} elevations")
    
    # Free memory
    loader.clear_memory_cache()
    
    return graph


def calculate_tobler_cost(gradient: float, activity: str = 'walking') -> float:
    """
    Calculate walking/running cost multiplier using Tobler's hiking function.
    
    Based on empirical data from Swiss military cartographer Eduard Imhof,
    formalised by Waldo Tobler in 1993. The function models the observation
    that maximum walking speed occurs on mild downhill slopes (~5%), not
    on flat terrain.
    
    Formula: speed = max_speed * exp(-decay_rate * |gradient - optimal_grade|)
    
    The cost multiplier is the ratio of flat terrain speed to actual speed,
    meaning values > 1 indicate slower travel (higher cost).
    
    Args:
        gradient: Signed gradient as decimal (positive = uphill, negative = downhill).
        activity: Activity mode - 'walking' or 'running'.
    
    Returns:
        Cost multiplier where 1.0 = flat terrain speed.
        Values < 1 indicate faster travel (mild downhill).
        Values > 1 indicate slower travel (steep terrain).
    
    Example values for walking:
        -5% grade: 0.83 (faster than flat)
         0% grade: 1.00 (baseline)
        +10% grade: 1.85 (nearly twice as slow)
        +20% grade: 3.33 (over three times as slow)
    """
    params = ACTIVITY_PARAMS.get(activity, ACTIVITY_PARAMS['walking'])
    
    # Tobler's formula: speed = max_speed * exp(-decay * |gradient - optimal|)
    speed = params['max_speed'] * math.exp(
        -params['decay_rate'] * abs(gradient - params['optimal_grade'])
    )
    
    # Avoid division by zero for extreme gradients
    speed = max(speed, 0.1)
    
    # Cost is inverse of speed, normalised to flat terrain
    return params['flat_speed'] / speed


def calculate_directional_gradients(
    length: float,
    elevation_u: Optional[float],
    elevation_v: Optional[float],
    activity: str = 'walking'
) -> Tuple[float, float, float, float]:
    """
    Calculate all gradient-related attributes for an edge.
    
    Computes four values:
    - uphill_gradient: Gradient when travelling uphill (0 if downhill)
    - downhill_gradient: Gradient when travelling downhill (0 if uphill)
    - slope_time_cost: Tobler's cost multiplier for this edge direction
    - raw_slope_cost: Absolute gradient (for backwards compatibility)
    
    Args:
        length: Edge length in metres.
        elevation_u: Elevation of source node in metres.
        elevation_v: Elevation of target node in metres.
        activity: Activity mode for Tobler calculation.
    
    Returns:
        Tuple of (uphill_gradient, downhill_gradient, slope_time_cost, raw_slope_cost).
        All values are 0.0 if elevation data is missing.
    """
    # Default values for missing data
    if elevation_u is None or elevation_v is None or length < MIN_EDGE_LENGTH:
        return (0.0, 0.0, 1.0, 0.0)
    
    # Calculate signed gradient (positive = uphill from u to v)
    elevation_change = elevation_v - elevation_u
    signed_gradient = elevation_change / length
    
    # Directional gradients
    uphill_gradient = max(0.0, signed_gradient)
    downhill_gradient = max(0.0, -signed_gradient)
    
    # Tobler's cost multiplier
    slope_time_cost = calculate_tobler_cost(signed_gradient, activity)
    
    # Absolute gradient for backwards compatibility
    raw_slope_cost = abs(signed_gradient)
    
    return (uphill_gradient, downhill_gradient, slope_time_cost, raw_slope_cost)


def calculate_edge_gradient(length: float, elevation_u: Optional[float], 
                            elevation_v: Optional[float]) -> Optional[float]:
    """
    Calculate the absolute gradient (slope) for an edge.
    
    DEPRECATED: Use calculate_directional_gradients() for new code.
    Kept for backwards compatibility with existing tests.
    
    Formula: gradient = |elevation_change| / horizontal_distance
    
    Args:
        length: Edge length in metres (horizontal distance).
        elevation_u: Elevation of source node in metres (can be None).
        elevation_v: Elevation of target node in metres (can be None).
    
    Returns:
        Absolute gradient as a decimal (0.0 = flat, 0.1 = 10% grade).
        Returns None if elevation data is missing or edge too short.
    """
    if elevation_u is None or elevation_v is None:
        return None
    
    if length < MIN_EDGE_LENGTH:
        return 0.0
    
    elevation_change = abs(elevation_v - elevation_u)
    return elevation_change / length


def process_graph_elevation(graph: nx.MultiDiGraph, 
                            mode: str = 'API',
                            activity: str = 'walking') -> nx.MultiDiGraph:
    """
    Process all edges to calculate and assign gradient attributes.
    
    Workflow:
    1. Fetch elevation data for all nodes (via API or LOCAL DEM tiles)
    2. Calculate directional gradients for each edge
    3. Store gradient attributes on each edge
    
    Edge attributes added:
    - uphill_gradient: Gradient when going uphill (0 if downhill)
    - downhill_gradient: Gradient when going downhill (0 if uphill)
    - slope_time_cost: Tobler's cost multiplier (1.0 = flat terrain)
    - raw_slope_cost: Absolute gradient (backwards compatibility)
    
    Args:
        graph: NetworkX MultiDiGraph with edge 'length' attributes.
        mode: Elevation fetch mode - 'API' or 'LOCAL'.
        activity: Activity mode for Tobler calculation - 'walking' or 'running'.
    
    Returns:
        The same graph with gradient attributes added to edges.
    """
    if graph is None:
        return graph
    
    # Step 1: Fetch node elevations based on mode
    t0 = time.perf_counter()
    
    if mode.upper() == 'LOCAL':
        graph = fetch_node_elevations_local(graph)
    else:
        graph = fetch_node_elevations(graph)
    
    fetch_time = time.perf_counter() - t0
    print(f"  [Timer] Elevation fetch ({mode}): {fetch_time:.2f}s")
    
    # Step 2: Calculate directional gradients for each edge
    t0 = time.perf_counter()
    edges_processed = 0
    edges_with_gradient = 0
    
    for u, v, key, data in graph.edges(keys=True, data=True):
        # Get node elevations
        elevation_u = graph.nodes[u].get('elevation')
        elevation_v = graph.nodes[v].get('elevation')
        
        # Get edge length
        length = data.get('length', 0.0)
        
        # Calculate all gradient attributes
        uphill, downhill, tobler_cost, raw_slope = calculate_directional_gradients(
            length, elevation_u, elevation_v, activity
        )
        
        # Store all attributes on edge
        graph[u][v][key]['uphill_gradient'] = uphill
        graph[u][v][key]['downhill_gradient'] = downhill
        graph[u][v][key]['slope_time_cost'] = tobler_cost
        graph[u][v][key]['raw_slope_cost'] = raw_slope
        
        edges_processed += 1
        if elevation_u is not None and elevation_v is not None:
            edges_with_gradient += 1
    
    calc_time = time.perf_counter() - t0
    print(f"[ElevationProcessor] Processed {edges_processed} edges "
          f"({edges_with_gradient} with gradient data) in {calc_time:.2f}s")
    
    return graph

