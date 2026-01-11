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
    
    Request JSON (mixed mode - also valid):
        {
            "start_lat": float,
            "start_lon": float,
            "end_address": str
        }
    
    Response JSON:
        {
            "route_coords": [[lat, lon], ...],
            "start_point": [lat, lon],   // Resolved coordinates
            "end_point": [lat, lon],     // Resolved coordinates
            "stats": {...},
            "debug_info": {...}
        }
    
    Returns:
        Response: JSON response with route data or error message.
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
        buffer_deg = 0.02  # ~2.2km buffer
        min_lat = min(start_point[0], end_point[0]) - buffer_deg
        max_lat = max(start_point[0], end_point[0]) + buffer_deg
        min_lon = min(start_point[1], end_point[1]) - buffer_deg
        max_lon = max(start_point[1], end_point[1]) + buffer_deg
        bbox = (min_lat, min_lon, max_lat, max_lon)
        
        # Get graph for this region
        graph = GraphManager.get_graph(bbox)
        
        # Find route
        finder = RouteFinder(graph)
        route, _, _, distance, time_seconds = finder.find_route(start_point, end_point)
        
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
                'pace_kmh': current_app.config.get('WALKING_SPEED_KMH', 5.0)
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
        
        return jsonify(response_data)
        
    except ValueError as e:
        return jsonify({'error': f'Invalid input values: {str(e)}'}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500
