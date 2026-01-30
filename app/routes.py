"""
Flask Routes Module

Handles HTTP endpoints for the PathFinder application.
Supports both coordinate-based and address-based routing.
"""

from flask import Blueprint, render_template, request, current_app, jsonify
from app.services.core.graph_manager import GraphManager
from app.services.routing.route_finder import RouteFinder
from app.services.rendering.map_renderer import MapRenderer

main = Blueprint('main', __name__)

# Threshold for showing visual edge features on the map (metres)
VISUAL_DEBUG_THRESHOLD_M = 5000


def _extract_edge_features(graph, route, max_edges=None):
    """
    Extract feature data for edges in a route.
    
    Extracts coordinate pairs and all scenic/routing feature values
    for each edge (consecutive node pair) in the provided route.
    
    Args:
        graph: NetworkX MultiDiGraph with processed edges.
        route: List of node IDs representing the path.
        max_edges: Optional limit on number of edges to extract.
    
    Returns:
        list: List of dicts containing edge coordinates and feature values.
              Returns empty list if route is None or too short.
    """
    if not route or len(route) < 2:
        return []
    
    edges = []
    edge_pairs = list(zip(route[:-1], route[1:]))
    
    if max_edges:
        edge_pairs = edge_pairs[:max_edges]
    
    for u, v in edge_pairs:
        try:
            u_data = graph.nodes[u]
            v_data = graph.nodes[v]
            edge_data = graph.get_edge_data(u, v)
            
            # Get first edge key's data (for MultiDiGraph)
            if edge_data:
                data = list(edge_data.values())[0]
                
                # Helper to round if value exists (including 0.0)
                def safe_round(val, decimals=3):
                    return round(val, decimals) if val is not None else None
                
                # Build feature dict with all available attributes
                edge_info = {
                    'from_coord': [u_data['y'], u_data['x']],
                    'to_coord': [v_data['y'], v_data['x']],
                    'highway': data.get('highway', 'unknown'),
                    'length_m': round(data.get('length', 0), 1),
                    
                    # Raw attributes
                    'noise_factor': data.get('noise_factor'),
                    'raw_green_cost': data.get('raw_green_cost'),
                    'raw_water_cost': data.get('raw_water_cost'),
                    'raw_social_cost': data.get('raw_social_cost'),
                    'raw_slope_cost': data.get('raw_slope_cost'),
                    
                    # Normalised attributes (0-1 range)
                    'norm_green': safe_round(data.get('norm_green')),
                    'norm_water': safe_round(data.get('norm_water')),
                    'norm_social': safe_round(data.get('norm_social')),
                    'norm_quiet': safe_round(data.get('norm_quiet')),
                    'norm_slope': safe_round(data.get('norm_slope')),
                    
                    # Elevation / slope data
                    'slope_time_cost': safe_round(data.get('slope_time_cost')),
                    'uphill_gradient': round(data.get('uphill_gradient', 0) * 100, 1),
                    'downhill_gradient': round(data.get('downhill_gradient', 0) * 100, 1),
                }
                
                # Add node elevations if available
                edge_info['from_elevation'] = safe_round(u_data.get('elevation'), 1)
                edge_info['to_elevation'] = safe_round(v_data.get('elevation'), 1)
                
                edges.append(edge_info)
        except KeyError:
            continue
    
    return edges


@main.route('/', methods=['GET'])
def index():
    """
    Render the main page with the interactive map.
    
    Returns:
        str: Rendered HTML template.
    """
    return render_template('index.html')


@main.route('/api/geocode', methods=['POST'])
def geocode_address():
    """
    API endpoint to geocode an address to coordinates.
    
    Used for instant preview - placing marker as user types.
    
    Request JSON:
        {"address": "Bristol Temple Meads"}
    
    Response JSON:
        {"lat": 51.449, "lon": -2.580, "display_name": "Bristol Temple Meads"}
    
    Returns:
        Response: JSON with coordinates or error message.
    """
    try:
        import osmnx as ox
        
        data = request.get_json()
        
        if not data or not data.get('address'):
            return jsonify({'error': 'No address provided'}), 400
        
        address = data['address'].strip()
        
        if len(address) < 3:
            return jsonify({'error': 'Address too short'}), 400
        
        try:
            coords = ox.geocode(address)
            
            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[Geocode] '{address}' -> {coords}")
            
            return jsonify({
                'lat': coords[0],
                'lon': coords[1],
                'display_name': address
            })
            
        except Exception as e:
            return jsonify({
                'error': f"Could not find location: '{address}'"
            }), 404
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@main.route('/api/route', methods=['POST'])
def calculate_route():
    """
    API endpoint to calculate a route between two points.
    
    Accepts EITHER coordinates OR text addresses for each point.
    Server-side geocoding is performed when addresses are provided.
    
    When ASYNC_MODE is enabled and graph is not cached:
        Returns immediately with {status: 'processing', task_id: '...'}
        Client should poll /api/task/<task_id> for completion.
    
    When ASYNC_MODE is disabled or graph is cached:
        Blocks until route is calculated and returns full result.
    
    Request JSON (coordinates mode):
        {
            "start_lat": float,
            "start_lon": float,
            "end_lat": float,
            "end_lon": float
        }
    
    Request JSON (address mode):
        {
            "start_address": str,
            "end_address": str
        }
    
    Response JSON (sync success):
        {
            "route_coords": [[lat, lon], ...],
            "start_point": [lat, lon],
            "end_point": [lat, lon],
            "stats": {...},
            "debug_info": {...}
        }
    
    Response JSON (async pending):
        {
            "status": "processing",
            "task_id": "...",
            "message": "Graph is being built. Poll for status."
        }
    
    Returns:
        Response: JSON response with route data, task_id, or error message.
    """
    try:
        import osmnx as ox
        
        # Parse request data
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400
        
        start_point = None
        end_point = None
        
        # Resolve start point (coordinates OR address)
        if data.get('start_lat') is not None and data.get('start_lon') is not None:
            start_point = (float(data['start_lat']), float(data['start_lon']))
        elif data.get('start_address'):
            try:
                start_point = ox.geocode(data['start_address'])
                if current_app.config.get('VERBOSE_LOGGING'):
                    print(f"[API] Geocoded start: '{data['start_address']}' -> {start_point}")
            except Exception as e:
                return jsonify({
                    'error': f"Could not find start location: '{data['start_address']}'"
                }), 400
        else:
            return jsonify({
                'error': 'Please provide start location (coordinates or address).'
            }), 400
        
        # Resolve end point (coordinates OR address)
        if data.get('end_lat') is not None and data.get('end_lon') is not None:
            end_point = (float(data['end_lat']), float(data['end_lon']))
        elif data.get('end_address'):
            try:
                end_point = ox.geocode(data['end_address'])
                if current_app.config.get('VERBOSE_LOGGING'):
                    print(f"[API] Geocoded end: '{data['end_address']}' -> {end_point}")
            except Exception as e:
                return jsonify({
                    'error': f"Could not find end location: '{data['end_address']}'"
                }), 400
        else:
            return jsonify({
                'error': 'Please provide end location (coordinates or address).'
            }), 400
        
        if current_app.config.get('VERBOSE_LOGGING'):
            print(f"[API] Route request: {start_point} -> {end_point}")
        
        # Calculate bounding box with buffer
        buffer_deg = 0.02  # ~2.2km buffer for basic bbox
        min_lat = min(start_point[0], end_point[0]) - buffer_deg
        max_lat = max(start_point[0], end_point[0]) + buffer_deg
        min_lon = min(start_point[1], end_point[1]) - buffer_deg
        max_lon = max(start_point[1], end_point[1]) + buffer_deg
        bbox = (min_lat, min_lon, max_lat, max_lon)
        
        # Calculate buffered bbox for clipping (5km buffer, matching GraphBuilder)
        # IMPORTANT: Must calculate from bbox (not raw coords) to match graph_builder.py
        clip_buffer_km = 5
        clip_buffer_deg = clip_buffer_km / 111.0  # ~0.045 degrees per km
        clip_bbox = (
            bbox[0] - clip_buffer_deg,  # min_lat
            bbox[1] - clip_buffer_deg,  # min_lon
            bbox[2] + clip_buffer_deg,  # max_lat
            bbox[3] + clip_buffer_deg   # max_lon
        )
        
        # =====================================================================
        # ASYNC MODE: Check cache and enqueue task if necessary
        # =====================================================================
        async_mode = current_app.config.get('ASYNC_MODE', False)
        
        if async_mode:
            from app.services.core.graph_builder import find_region_for_bbox
            from app.services.core.cache_manager import get_cache_manager
            from app.services.core.data_loader import OSMDataLoader
            from app.services.core.task_manager import get_task_manager
            
            # Determine region for this request
            region_name, _ = find_region_for_bbox(bbox)
            greenness_mode = current_app.config.get('GREENNESS_MODE', 'FAST')
            elevation_mode = current_app.config.get('ELEVATION_MODE', 'OFF')
            normalisation_mode = current_app.config.get('NORMALISATION_MODE', 'STATIC')
            
            # Check cache validity (using clip_bbox for per-route caching)
            cache_mgr = get_cache_manager()
            loader = OSMDataLoader()
            loader.ensure_data_for_bbox(bbox)
            
            cache_hit = cache_mgr.is_cache_valid(
                region_name, greenness_mode, elevation_mode, loader.file_path,
                bbox=clip_bbox  # Use clip_bbox for per-route cache keys
            )
            
            if not cache_hit:
                # Cache miss - enqueue async task
                task_mgr = get_task_manager()
                result = task_mgr.enqueue_graph_build(
                    region_name=region_name,
                    bbox=bbox,
                    greenness_mode=greenness_mode,
                    elevation_mode=elevation_mode,
                    normalisation_mode=normalisation_mode
                )
                
                if result.get('error'):
                    # Failed to enqueue - fall back to sync
                    print(f"[API] Async enqueue failed: {result['error']}, falling back to sync")
                else:
                    # Return task ID for polling
                    return jsonify({
                        'status': 'processing',
                        'task_id': result['task_id'],
                        'is_new_task': result['is_new'],
                        'region_name': region_name,
                        'message': 'Graph is being built. Poll /api/task/<task_id> for status.',
                        'start_point': list(start_point),
                        'end_point': list(end_point),
                        'bbox': bbox
                    }), 202  # Accepted
        
        # =====================================================================
        # SYNC MODE or CACHE HIT: Process immediately
        # =====================================================================
        
        # Get graph for this region (will use cache or build synchronously)
        graph = GraphManager.get_graph(bbox)
        
        # Parse WSM settings from request
        use_wsm = data.get('use_wsm', False)
        weights = None
        
        if use_wsm:
            ui_weights = data.get('weights', None)
            if ui_weights:
                # Convert UI slider values (0-100) to normalised weights
                from app.services.routing.cost_calculator import normalise_ui_weights
                weights = normalise_ui_weights(ui_weights)
            else:
                # Use config defaults
                weights = current_app.config.get('WSM_DEFAULT_WEIGHTS')
            
            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[API] WSM routing enabled with weights: {weights}")
        
        # Find route
        finder = RouteFinder(graph)
        route, _, _, distance, time_seconds = finder.find_route(
            start_point, end_point,
            use_wsm=use_wsm,
            weights=weights
        )
        
        if not route:
            return jsonify({
                'error': 'Could not find a route between these locations.'
            }), 404
        
        # Extract route coordinates for client-side display
        route_coords = MapRenderer.route_to_coords(graph, route)
        
        # Build response with resolved coordinates
        response_data = {
            'route_coords': route_coords,
            'start_point': list(start_point),  # Return resolved coords
            'end_point': list(end_point),      # Return resolved coords
            'stats': {
                'distance_km': f"{distance / 1000:.2f}",
                'time_min': int(time_seconds // 60),
                'pace_kmh': current_app.config.get('WALKING_SPEED_KMH', 5.0),
                'routing_mode': 'scenic' if use_wsm else 'shortest'
            }
        }
        
        # Add debug info if enabled
        if current_app.config.get('VERBOSE_LOGGING') or current_app.config.get('DEBUG'):
            response_data['debug_info'] = {
                'start_coord': start_point,
                'end_coord': end_point,
                'node_count': len(route),
                'graph_nodes': len(graph.nodes),
                'bbox': bbox,
                'loaded_pbf': GraphManager.get_loaded_file_path()
            }
            
            # Always include first 5 edges with feature data for debug panel
            first_5_edges = _extract_edge_features(graph, route, max_edges=5)
            response_data['debug_info']['edge_preview'] = first_5_edges
            
            # For short routes, include ALL edge features for visual map overlay
            if distance < VISUAL_DEBUG_THRESHOLD_M:
                all_edges = _extract_edge_features(graph, route)
                response_data['edge_features'] = all_edges
                response_data['debug_info']['visual_debug_enabled'] = True
            else:
                response_data['debug_info']['visual_debug_enabled'] = False
                response_data['debug_info']['visual_debug_reason'] = (
                    f"Route too long ({distance/1000:.2f}km > 5km threshold)"
                )
        
        return jsonify(response_data)
        
    except ValueError as e:
        return jsonify({'error': f'Invalid input values: {str(e)}'}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500

