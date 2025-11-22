import folium
import osmnx as ox

class MapRenderer:
    """
    Service to render the map and route using Folium.
    """

    @staticmethod
    def render_map(graph, route, start_point, end_point):
        """
        Generates an HTML map with the route plotted.

        Args:
            graph (networkx.MultiDiGraph): The street network graph.
            route (list): List of node IDs representing the path.
            start_point (tuple): (lat, lon) of the start location.
            end_point (tuple): (lat, lon) of the end location.

        Returns:
            str: HTML string of the map.
        """
        # Create a Folium map centered between the start and end points
        # If no route, center on start or default
        if start_point and end_point:
            mid_lat = (start_point[0] + end_point[0]) / 2
            mid_lon = (start_point[1] + end_point[1]) / 2
            m = folium.Map(location=[mid_lat, mid_lon], zoom_start=14)
        else:
            # Default fallback (shouldn't happen if route exists)
            m = folium.Map(location=[51.4545, -2.5879], zoom_start=13) # Bristol

        # Plot the route if it exists
        if route:
            # Get the coordinates of the route nodes
            route_coords = []
            for node in route:
                point = graph.nodes[node]
                route_coords.append((point['y'], point['x']))
            
            # Draw the polyline
            folium.PolyLine(
                route_coords,
                color="blue",
                weight=5,
                opacity=0.7
            ).add_to(m)

            # Add markers for start and end
            folium.Marker(
                location=start_point,
                popup="Start",
                icon=folium.Icon(color="green", icon="play")
            ).add_to(m)

            folium.Marker(
                location=end_point,
                popup="End",
                icon=folium.Icon(color="red", icon="stop")
            ).add_to(m)

        return m.get_root().render()
