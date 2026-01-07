from flask import Blueprint, render_template, request, current_app, jsonify
from app.services.graph_manager import GraphManager
from app.services.route_finder import RouteFinder
from app.services.map_renderer import MapRenderer

main = Blueprint('main', __name__)

@main.route('/', methods=['GET', 'POST'])
def index():
    """
    Renders the main page.
    On POST (AJAX), calculates the route and returns the map HTML.
    """
    map_html = None
    error = None

    # Pre-load the graph on first request (or app startup if we moved it)
    # For MVP, we load it here or ensure it's loaded.
    # Ideally, this should be done asynchronously or at startup, 
    # but for MVP we'll do it on demand if not ready.
    city = current_app.config['DEFAULT_CITY']
    
    if request.method == 'POST':
        start_location = request.form.get('start')
        end_location = request.form.get('end')

        if start_location and end_location:
            try:
                import osmnx as ox
                # 1. Geocode locations
                start_point = ox.geocode(start_location) # (lat, lon)
                end_point = ox.geocode(end_location)

                if current_app.config.get('VERBOSE_LOGGING') or True: # Force log for now
                    print(f"[VERBOSE] Start: {start_location} -> {start_point}")
                    print(f"[VERBOSE] End: {end_location} -> {end_point}")

                # 2. Calculate BBox with buffer (e.g. 2000m padding)
                # Simple degree approximation: 1 deg ~ 111km. 1km ~ 0.009 deg.
                # 2km ~ 0.018 deg. Let's start with 0.02 deg padding (~2.2km).
                buffer_deg = 0.02
                
                min_lat = min(start_point[0], end_point[0]) - buffer_deg
                max_lat = max(start_point[0], end_point[0]) + buffer_deg
                min_lon = min(start_point[1], end_point[1]) - buffer_deg
                max_lon = max(start_point[1], end_point[1]) + buffer_deg
                
                bbox = (min_lat, min_lon, max_lat, max_lon)

                # 3. Get Graph for this BBox (Tile Manager handles loading)
                graph = GraphManager.get_graph(bbox)
                
                # 4. Find Route
                finder = RouteFinder(graph)
                # Pass coords directly now!
                route, _, _, distance, time_seconds = finder.find_route(start_point, end_point)

                if route:
                    map_html = MapRenderer.render_map(graph, route, start_point, end_point)
                else:
                    error = "Could not find a route between these locations."
            except Exception as e:
                error = f"An error occurred: {str(e)}"
                import traceback
                traceback.print_exc()
        
        # If it's an AJAX request, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            if error:
                return jsonify({'error': error}), 400
            
            response_data = {
                'map_html': map_html,
                'stats': {
                    'distance_km': f"{distance / 1000:.2f}",
                    'time_min': int(time_seconds // 60),
                    'pace_kmh': current_app.config.get('WALKING_SPEED_KMH', 5.0)
                }
            }

            if current_app.config.get('VERBOSE_LOGGING') or current_app.config.get('DEBUG'):
                response_data['debug_info'] = {
                    'start_coord': start_point,
                    'end_coord': end_point,
                    'node_count': len(route) if route else 0,
                    'graph_nodes': len(graph.nodes) if 'graph' in locals() else 0,
                    'bbox': bbox if 'bbox' in locals() else 'N/A'
                }

            return jsonify(response_data)

    # Initial load // show a default map of the city
    if map_html is None:
        # Just show bris city center
        import folium
        # Coordinates for Bristol
        m = folium.Map(location=[51.4545, -2.5879], zoom_start=13)
        map_html = m._repr_html_()

    return render_template('index.html', map_html=map_html)
