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
                graph = GraphManager.get_graph(city)
                finder = RouteFinder(graph)
                # route: List of graph node IDs representing the path (calculated by A* in RouteFinder).
                # start_point/end_point: (lat, lon) tuples of the geocoded addresses.
                route, start_point, end_point = finder.find_route(start_location, end_location)

                if route:
                    map_html = MapRenderer.render_map(graph, route, start_point, end_point)
                else:
                    error = "Could not find a route between these locations."
            except Exception as e:
                error = f"An error occurred: {str(e)}"
        
        # If it's an AJAX request, return JSON
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            if error:
                return jsonify({'error': error}), 400
            return jsonify({'map_html': map_html})

    # Initial load // show a default map of the city
    if map_html is None:
        # Just show bris city center
        import folium
        # Coordinates for Bristol
        m = folium.Map(location=[51.4545, -2.5879], zoom_start=13)
        map_html = m._repr_html_()

    return render_template('index.html', map_html=map_html)
