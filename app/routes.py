"""
Flask Routes Module

Handles HTTP endpoints for the PathFinder application.
Supports both coordinate-based and address-based routing.
"""

from flask import Blueprint, render_template, request, current_app, jsonify
from flask_login import current_user

from app.services.core.graph_manager import GraphManager
from app.services.movement_preferences import (
    km_to_display,
    pace_text_from_speed,
    resolve_request_movement_context,
    speed_kmh_to_display,
    speed_unit_label,
)
from app.services.routing.lighting_context import resolve_request_lighting_context
from app.services.routing.route_finder import RouteFinder
from app.services.rendering.map_renderer import MapRenderer

main = Blueprint('main', __name__)

# Threshold for showing visual edge features on the map (metres)
VISUAL_DEBUG_THRESHOLD_M = 5000


def _current_authenticated_user():
    """Safely return the logged-in user or None."""
    try:
        if getattr(current_user, 'is_authenticated', False):
            return current_user
    except Exception:
        pass
    return None


def _resolve_movement_context(request_data):
    """Resolve request-time travel profile, unit, and effective speed."""
    return resolve_request_movement_context(
        request_data=request_data or {},
        user=_current_authenticated_user(),
        config_obj=current_app.config,
    )


def _resolve_lighting_context(request_data, start_point, end_point=None):
    """Resolve request-time lighting relevance context for routing modifiers."""
    return resolve_request_lighting_context(
        request_data=request_data or {},
        start_point=start_point,
        end_point=end_point,
    )


def _build_stats_payload(distance_m, time_seconds, movement_ctx, routing_mode):
    """Build a unit-aware stats payload while preserving legacy keys."""
    distance_km = max(0.0, float(distance_m) / 1000.0)
    distance_unit = movement_ctx['distance_unit']
    speed_kmh = float(movement_ctx['effective_speed_kmh'])

    return {
        'distance_km': f"{distance_km:.2f}",
        'distance': f"{km_to_display(distance_km, distance_unit):.2f}",
        'distance_unit': distance_unit,
        'time_min': int(max(0.0, float(time_seconds)) // 60),
        'assumed_speed_kmh': round(speed_kmh, 2),
        'assumed_speed': round(speed_kmh_to_display(speed_kmh, distance_unit), 2),
        'speed_unit': speed_unit_label(distance_unit),
        'assumed_pace': pace_text_from_speed(speed_kmh, distance_unit),
        'travel_profile': movement_ctx['travel_profile'],
        'routing_mode': routing_mode,

        # Legacy key kept for existing UI paths.
        'pace_kmh': round(speed_kmh, 2),
    }


def _build_movement_payload(movement_ctx):
    """Build common movement metadata returned by route and loop APIs."""
    distance_unit = movement_ctx['distance_unit']
    speed_kmh = float(movement_ctx['effective_speed_kmh'])

    return {
        'travel_profile': movement_ctx['travel_profile'],
        'distance_unit': distance_unit,
        'assumed_speed_kmh': round(speed_kmh, 2),
        'assumed_speed': round(speed_kmh_to_display(speed_kmh, distance_unit), 2),
        'speed_unit': speed_unit_label(distance_unit),
        'assumed_pace': pace_text_from_speed(speed_kmh, distance_unit),
        'preferences_updated_at': movement_ctx['preferences'].get('movement_prefs_updated_at'),
    }


def _resolve_advanced_options(request_data):
    """Parse and canonicalize advanced routing option toggles.

    Canonical keys:
    - prefer_separated_paths
    - prefer_nature_trails
    - prefer_paved_surfaces
    - prefer_lit_streets
    - avoid_unlit_streets
    - avoid_unsafe_roads
    - avoid_unclassified_lanes
    - prefer_segregated_paths
    - allow_quiet_service_lanes

    Legacy keys are still accepted for saved-query compatibility.
    """
    data = request_data or {}

    def _as_bool(value):
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return value != 0
        if isinstance(value, str):
            return value.strip().lower() in {'1', 'true', 'yes', 'on'}
        return bool(value)

    prefer_lit_streets = _as_bool(data.get('prefer_lit_streets', data.get('prefer_lit', False)))
    avoid_unlit_streets = _as_bool(data.get('avoid_unlit_streets', data.get('heavily_avoid_unlit', False)))
    prefer_paved_surfaces = _as_bool(data.get('prefer_paved_surfaces', data.get('prefer_paved', False)))
    avoid_unsafe_roads = _as_bool(data.get('avoid_unsafe_roads', data.get('avoid_unsafe', False)))
    avoid_unclassified_lanes = _as_bool(
        data.get('avoid_unclassified_lanes', data.get('avoid_unclassified', False))
    )
    prefer_separated_paths = _as_bool(
        data.get('prefer_separated_paths', data.get('prefer_dedicated_pavements', False))
    )
    prefer_nature_trails = _as_bool(data.get('prefer_nature_trails', False))
    prefer_segregated_paths = _as_bool(data.get('prefer_segregated_paths', False))
    allow_quiet_service_lanes = _as_bool(data.get('allow_quiet_service_lanes', False))
    legacy_prefer_pedestrian = _as_bool(data.get('prefer_pedestrian', False))
    legacy_only_prefer_pedestrian = legacy_prefer_pedestrian and not (
        prefer_separated_paths or prefer_nature_trails
    )

    # Backward compatibility: map legacy paths/trails toggle to the dedicated
    # pavement intent when no newer intent toggle was provided.
    if legacy_only_prefer_pedestrian:
        prefer_separated_paths = True

    # Existing behavior: heavy mode supersedes the mild lit preference.
    if avoid_unlit_streets:
        prefer_lit_streets = False

    # Trail mode conflicts with paved-focused intents.
    if prefer_nature_trails:
        prefer_separated_paths = False
        prefer_paved_surfaces = False
        prefer_segregated_paths = False
        allow_quiet_service_lanes = False

    if not prefer_separated_paths:
        prefer_segregated_paths = False
        allow_quiet_service_lanes = False

    return {
        # Canonical keys.
        'prefer_lit_streets': prefer_lit_streets,
        'avoid_unlit_streets': avoid_unlit_streets,
        'prefer_separated_paths': prefer_separated_paths,
        'prefer_nature_trails': prefer_nature_trails,
        'prefer_paved_surfaces': prefer_paved_surfaces,
        'avoid_unsafe_roads': avoid_unsafe_roads,
        'avoid_unclassified_lanes': avoid_unclassified_lanes,
        'prefer_segregated_paths': prefer_segregated_paths,
        'allow_quiet_service_lanes': allow_quiet_service_lanes,

        # Legacy aliases preserved for old call paths/tests.
        'prefer_lit': prefer_lit_streets,
        'heavily_avoid_unlit': avoid_unlit_streets,
        'prefer_pedestrian': prefer_segregated_paths,
        'prefer_dedicated_pavements': prefer_separated_paths,
        'prefer_paved': prefer_paved_surfaces,
        'avoid_unclassified': avoid_unclassified_lanes,
        'legacy_prefer_pedestrian': legacy_only_prefer_pedestrian,
    }


def _extract_edge_features(
    graph,
    route,
    max_edges=None,
    lighting_context='night',
    prefer_segregated_paths=False,
    prefer_dedicated_pavements=False,
    allow_quiet_service_lanes=False,
    prefer_paved=False,
    avoid_unsafe_roads=False,
    avoid_unclassified_lanes=False,
):
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

                # Helper to normalise scalar/list OSM tag fields
                def scalar_tag(val):
                    if isinstance(val, list):
                        return val[0] if val else None
                    return val
                
                # Build feature dict with all available attributes
                edge_info = {
                    'from_coord': [u_data['y'], u_data['x']],
                    'to_coord': [v_data['y'], v_data['x']],
                    'highway': data.get('highway', 'unknown'),
                    'length_m': round(data.get('length', 0), 1),

                    # Lighting and access attributes used by advanced modifiers
                    'lit': scalar_tag(data.get('lit')),
                    'lit_source': scalar_tag(data.get('lit_source')),
                    'lit_source_detail': scalar_tag(data.get('lit_source_detail')),
                    'lighting_regime': scalar_tag(data.get('lighting_regime')),
                    'surface': scalar_tag(data.get('surface')),
                    'sidewalk': scalar_tag(data.get('sidewalk')),
                    'foot': scalar_tag(data.get('foot')),
                    'bicycle': scalar_tag(data.get('bicycle')),
                    'segregated': scalar_tag(data.get('segregated')),
                    
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

                from app.services.routing.astar.wsm_astar import describe_edge_modifier_context
                edge_info.update(
                    describe_edge_modifier_context(
                        data,
                        lighting_context=lighting_context,
                        prefer_segregated_paths=prefer_segregated_paths,
                        prefer_dedicated_pavements=prefer_dedicated_pavements,
                        allow_quiet_service_lanes=allow_quiet_service_lanes,
                        prefer_paved=prefer_paved,
                        avoid_unsafe_roads=avoid_unsafe_roads,
                        avoid_unclassified_lanes=avoid_unclassified_lanes,
                    )
                )
                
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
    return render_template(
        'index.html',
        debug_mode=bool(current_app.config.get('DEBUG', False)),
    )


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


@main.route('/api/loop', methods=['POST'])
def calculate_loop_route():
    """
    API endpoint to calculate a circular (loop) route from a single start point.
    
    Accepts a start point and target distance, returns a circular route that
    starts and ends at the same location with approximate target distance.
    
    Request JSON:
        {
            "start_lat": float,
            "start_lon": float,
            "target_distance_km": float (1-30),
            "directional_bias": "north" | "east" | "south" | "west" | "none",
            "use_wsm": bool,
            "weights": {...},
            "combine_nature": bool,
            "variety_level": int (0-3, default 0),
            "prefer_separated_paths": bool (default false),
            "prefer_nature_trails": bool (default false),
            "prefer_paved_surfaces": bool (default false),
            "prefer_lit_streets": bool (default false),
            "avoid_unlit_streets": bool (default false),
            "avoid_unsafe_roads": bool (default false)
            "avoid_unclassified_lanes": bool (default false)
            "prefer_segregated_paths": bool (default false),
            "allow_quiet_service_lanes": bool (default false)
        }
    
    Response JSON (success):
        {
            "success": true,
            "multi_route": false,
            "route_mode": "loop",
            "route_coords": [[lat, lon], ...],
            "start_point": [lat, lon],
            "end_point": [lat, lon],
            "stats": {...},
            "target_distance_km": 5.0,
            "actual_distance_km": 4.8,
            "tiles_required": [...]
        }
    
    Returns:
        Response: JSON response with loop route data or error message.
    """
    try:
        import osmnx as ox
        import math
        
        # Parse request data
        data = request.get_json()
        
        if not data:
            return jsonify({'error': 'No data provided'}), 400

        movement_ctx = _resolve_movement_context(data)

        demo_visualisation_requested = bool(data.get('demo_visualisation', False))
        demo_visualisation_enabled = (
            bool(current_app.config.get('DEBUG', False))
            and demo_visualisation_requested
        )
        loop_demo_context = None
        if demo_visualisation_enabled:
            loop_demo_context = {
                'schema_version': 1,
                'frames': [],
                'max_frames': int(current_app.config.get('LOOP_DEMO_MAX_FRAMES', 400)),
                'truncated': False,
            }
        
        # Validate required fields
        if data.get('start_lat') is None or data.get('start_lon') is None:
            return jsonify({'error': 'Please provide start location coordinates.'}), 400
        
        start_point = (float(data['start_lat']), float(data['start_lon']))
        
        # Validate target distance (1-30 km) - accept both field names
        target_distance_km = float(data.get('distance_km', data.get('target_distance_km', 5.0)))
        if target_distance_km < 1 or target_distance_km > 30:
            return jsonify({'error': 'Target distance must be between 1 and 30 km.'}), 400
        
        target_distance_m = target_distance_km * 1000
        
        # Validate directional bias
        directional_bias = data.get('directional_bias', 'none').lower()
        valid_biases = {'north', 'east', 'south', 'west', 'none'}
        if directional_bias not in valid_biases:
            return jsonify({'error': f'Invalid directional_bias. Must be one of: {valid_biases}'}), 400
        
        # Validate variety level (0-3)
        variety_level = int(data.get('variety_level', 0))
        variety_level = max(0, min(3, variety_level))  # Clamp to [0, 3]
        
        # Parse and canonicalize advanced routing options.
        advanced_options = _resolve_advanced_options(data)
        prefer_separated_paths = advanced_options['prefer_separated_paths']
        prefer_nature_trails = advanced_options['prefer_nature_trails']
        prefer_paved_surfaces = advanced_options['prefer_paved_surfaces']
        prefer_lit_streets = advanced_options['prefer_lit_streets']
        avoid_unlit_streets = advanced_options['avoid_unlit_streets']
        avoid_unsafe_roads = advanced_options['avoid_unsafe_roads']
        avoid_unclassified_lanes = advanced_options['avoid_unclassified_lanes']
        prefer_segregated_paths = advanced_options['prefer_segregated_paths']
        allow_quiet_service_lanes = advanced_options['allow_quiet_service_lanes']
        
        # Smart Bearing Toggle
        use_smart_bearing = bool(data.get('use_smart_bearing', True))
        
        # Log warning for long loops
        if target_distance_km > 15:
            print(f"[API] Long loop requested ({target_distance_km}km), may take longer to calculate")
        
        if current_app.config.get('VERBOSE_LOGGING'):
            print(f"[API] Loop route request: start={start_point}, "
                  f"target={target_distance_km}km, bias={directional_bias}")

        lighting_ctx = _resolve_lighting_context(data, start_point, start_point)
        
        # =====================================================================
        # Calculate tiles needed for loop (radius-based)
        # =====================================================================
        from app.services.core.tile_utils import (
            get_tiles_for_route, get_tile_bbox,
            DEFAULT_TILE_SIZE_KM, DEFAULT_TILE_OVERLAP_KM
        )
        
        tile_size_km = current_app.config.get('TILE_SIZE_KM', DEFAULT_TILE_SIZE_KM)
        tile_overlap_km = current_app.config.get('TILE_OVERLAP_KM', DEFAULT_TILE_OVERLAP_KM)
        
        # Synthesize virtual bounding box around the start point.
        # A loop returns to start, so the relevant area is a circle of
        # radius ≈ target_distance / (2π) for a circular loop, up to
        # ≈ target_distance / 3 for an extremely elongated one.
        # Using 0.35 × target gives generous coverage (with +30% budget
        # tolerance → max displacement ≈ 0.43 × target) while avoiding
        # the old 0.6 multiplier which requested 5 tiles for a 12km loop
        # and caused OOM during merge.
        offset_km = target_distance_km * 0.35
        offset_deg_lat = offset_km / 111.0  # 1 degree latitude ≈ 111 km
        offset_deg_lon = offset_km / (111.0 * math.cos(math.radians(start_point[0])))
        
        # Create virtual corners for tile calculation
        virtual_ne = (start_point[0] + offset_deg_lat, start_point[1] + offset_deg_lon)
        virtual_sw = (start_point[0] - offset_deg_lat, start_point[1] - offset_deg_lon)
        
        # Get tiles for the bounding box
        tile_ids = get_tiles_for_route(virtual_sw, virtual_ne, tile_size_km)

        # ── Tile cap for loop routes ─────────────────────────────────
        # Merging many large tiles is memory-intensive (~300-500MB each).
        # A loop route never needs more than 4 tiles — if more are
        # computed it means the bounding box is too generous or the
        # start sits at a multi-tile junction.  Keep only the tiles
        # closest to the start point.
        MAX_LOOP_TILES = 4
        if len(tile_ids) > MAX_LOOP_TILES:
            print(f"[API] Loop tile cap: reducing {len(tile_ids)} tiles "
                  f"to {MAX_LOOP_TILES} nearest start")
            # Sort tiles by distance from start to tile centre, keep closest
            def _tile_dist(tid):
                parts = tid.split('_')
                t_lat, t_lon = float(parts[0]), float(parts[1])
                return ((t_lat - start_point[0]) ** 2
                        + (t_lon - start_point[1]) ** 2)
            tile_ids = sorted(tile_ids, key=_tile_dist)[:MAX_LOOP_TILES]
        
        if current_app.config.get('VERBOSE_LOGGING'):
            print(f"[API] Loop requires {len(tile_ids)} tiles: {tile_ids}")
        
        # =====================================================================
        # ASYNC MODE: Check tile cache (same pattern as /api/route)
        # =====================================================================
        async_mode = current_app.config.get('ASYNC_MODE', False)
        
        if async_mode:
            from app.services.core.graph_builder import find_region_for_bbox
            from app.services.core.cache_manager import get_cache_manager
            from app.services.core.task_manager import get_task_manager
            
            greenness_mode = current_app.config.get('GREENNESS_MODE', 'FAST')
            elevation_mode = current_app.config.get('ELEVATION_MODE', 'OFF')
            normalisation_mode = current_app.config.get('NORMALISATION_MODE', 'STATIC')
            
            # Get region from first tile
            first_tile_bbox = get_tile_bbox(tile_ids[0], tile_size_km, tile_overlap_km)
            region_name, _ = find_region_for_bbox(first_tile_bbox)
            cache_mgr = get_cache_manager()
            
            # Check for missing tiles
            missing_tiles = []
            for tid in tile_ids:
                is_valid = cache_mgr.is_cache_valid(
                    region_name, greenness_mode, elevation_mode,
                    pbf_path=None, tile_id=tid
                )
                if not is_valid:
                    missing_tiles.append(tid)
            
            if missing_tiles:
                # Enqueue tile build tasks
                task_mgr = get_task_manager()
                task_ids = []
                
                for tile_id in missing_tiles:
                    result = task_mgr.enqueue_tile_build(
                        tile_id=tile_id,
                        region_name=region_name,
                        greenness_mode=greenness_mode,
                        elevation_mode=elevation_mode,
                        normalisation_mode=normalisation_mode,
                        tile_size_km=tile_size_km,
                        tile_overlap_km=tile_overlap_km
                    )
                    if result.get('task_id'):
                        task_ids.append({
                            'tile_id': tile_id,
                            'task_id': result['task_id'],
                            'is_new': result['is_new']
                        })
                
                if task_ids:
                    return jsonify({
                        'status': 'processing',
                        'task_id': task_ids[0]['task_id'],
                        'is_new_task': task_ids[0]['is_new'],
                        'region_name': region_name,
                        'tiles_required': tile_ids,
                        'tiles_building': [t['tile_id'] for t in task_ids],
                        'message': f'Building {len(missing_tiles)} tile(s). Poll /api/task/<task_id> for status.',
                        'start_point': list(start_point),
                        'route_mode': 'loop',
                        'target_distance_km': target_distance_km,
                        'demo_visualisation': demo_visualisation_enabled,
                    }), 202
        
        # =====================================================================
        # SYNC MODE or CACHE HIT: Process immediately
        # =====================================================================
        
        # Get graph using tile-based caching
        # Use virtual corners to ensure we get enough coverage
        graph = GraphManager.get_graph_for_route(virtual_sw, virtual_ne)
        
        # Parse WSM settings
        use_wsm = data.get('use_wsm', True)  # Default to WSM for loop routes
        combine_nature = data.get('combine_nature', False)
        weights = None
        
        if use_wsm:
            ui_weights = data.get('weights', None)
            if ui_weights:
                from app.services.routing.cost_calculator import normalise_ui_weights
                weights = normalise_ui_weights(ui_weights)
            else:
                weights = current_app.config.get('WSM_DEFAULT_WEIGHTS')
            
            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[API] Loop WSM weights: {weights}, combine_nature: {combine_nature}")
        
        # Initialise route finder and find loop candidates
        finder = RouteFinder(graph)
        
        candidates = finder.find_loop_route(
            start_point=start_point,
            target_distance_m=target_distance_m,
            use_wsm=use_wsm,
            weights=weights,
            combine_nature=combine_nature,
            directional_bias=directional_bias,
            variety_level=variety_level,
            prefer_separated_paths=prefer_separated_paths,
            prefer_nature_trails=prefer_nature_trails,
            prefer_paved_surfaces=prefer_paved_surfaces,
            prefer_lit_streets=prefer_lit_streets,
            avoid_unsafe_roads=avoid_unsafe_roads,
            avoid_unclassified_lanes=avoid_unclassified_lanes,
            prefer_segregated_paths=prefer_segregated_paths,
            allow_quiet_service_lanes=allow_quiet_service_lanes,
            use_smart_bearing=use_smart_bearing,
            avoid_unlit_streets=avoid_unlit_streets,
            travel_profile=movement_ctx['travel_profile'],
            speed_kmh=movement_ctx['effective_speed_kmh'],
            activity=movement_ctx['activity'],
            lighting_context=lighting_ctx['lighting_context'],
            loop_demo_context=loop_demo_context,
        )
        
        if not candidates:
            return jsonify({
                'error': 'Could not find a loop route. Try a shorter distance or different start point.'
            }), 404

        # Build multi-loop response with profile-aware ETA and unit-aware stats.
        distance_unit = movement_ctx['distance_unit']
        speed_kmh = float(movement_ctx['effective_speed_kmh'])

        def _slugify_label(value):
            base = ''.join(ch.lower() if ch.isalnum() else '-' for ch in str(value or 'loop'))
            base = '-'.join(part for part in base.split('-') if part)
            return base or 'loop'
        
        loops_json = []
        for idx, candidate in enumerate(candidates, start=1):
            route_coords = MapRenderer.route_to_coords(graph, candidate.route)
            time_seconds = finder.estimate_route_time(
                route=candidate.route,
                travel_profile=movement_ctx['travel_profile'],
                speed_kmh=movement_ctx['effective_speed_kmh'],
                activity=movement_ctx['activity'],
            )
            distance_display = km_to_display(candidate.distance_km, distance_unit)

            label_subtitle = None
            label_reason = None
            label_role = None
            label_tags = None
            if isinstance(candidate.metadata, dict):
                label_subtitle = candidate.metadata.get('name_subtitle')
                label_reason = candidate.metadata.get('name_reason')
                label_role = candidate.metadata.get('name_role')
                raw_tags = candidate.metadata.get('name_tags')
                if isinstance(raw_tags, list):
                    label_tags = [str(tag) for tag in raw_tags]

            loop_id = f"loop-{idx}-{_slugify_label(candidate.label)}"
            
            loops_json.append({
                'id': loop_id,
                'label': candidate.label,
                'label_subtitle': label_subtitle,
                'label_reason': label_reason,
                'label_role': label_role,
                'label_tags': label_tags,
                'colour': candidate.colour,
                'route_coords': route_coords,
                'distance_m': candidate.distance,
                'distance_km': candidate.distance_km,
                'distance': round(distance_display, 2),
                'distance_unit': distance_unit,
                'deviation': round(candidate.deviation, 4),
                'deviation_percent': candidate.deviation_percent,
                'scenic_cost': round(candidate.scenic_cost, 4),
                'quality_score': round(candidate.quality_score, 4),
                'time_seconds': int(time_seconds),
                'time_min': int(time_seconds // 60),
                'travel_profile': movement_ctx['travel_profile'],
                'assumed_speed_kmh': round(speed_kmh, 2),
                'assumed_speed': round(speed_kmh_to_display(speed_kmh, distance_unit), 2),
                'speed_unit': speed_unit_label(distance_unit),
                'assumed_pace': pace_text_from_speed(speed_kmh, distance_unit),
                'algorithm': candidate.algorithm,
                'metadata': candidate.metadata,
            })
        
        # Best candidate for primary stats
        best = candidates[0]
        best_distance = best.distance
        best_time = finder.estimate_route_time(
            route=best.route,
            travel_profile=movement_ctx['travel_profile'],
            speed_kmh=movement_ctx['effective_speed_kmh'],
            activity=movement_ctx['activity'],
        )
        
        # Build warning message
        warning = None
        if target_distance_km > 25:
            warning = "Very long route! Performance may be affected for distances over 25 km."
        elif target_distance_km > 20:
            warning = "Long route. Distances over 20 km may affect calculation accuracy."
        elif target_distance_km > 15:
            warning = "Routes over 15 km may take longer to calculate."
        
        # Check if all candidates have high deviation
        min_deviation = min(c.deviation for c in candidates)
        if min_deviation > 0.20:
            dev_warning = f"Best loop deviates {min_deviation*100:.0f}% from target. Try adjusting distance."
            warning = f"{warning} {dev_warning}" if warning else dev_warning
        
        algorithm = current_app.config.get('LOOP_SOLVER_ALGORITHM', 'BUDGET_ASTAR')
        
        response_data = {
            'success': True,
            'multi_loop': True,
            'route_mode': 'loop',
            'target_distance_km': target_distance_km,
            'algorithm': algorithm,
            'loops': loops_json,
            'start_point': list(start_point),
            'end_point': list(start_point),
            'stats': _build_stats_payload(
                distance_m=best_distance,
                time_seconds=best_time,
                movement_ctx=movement_ctx,
                routing_mode='loop',
            ),
            'movement': _build_movement_payload(movement_ctx),
            'loop_metadata': {
                'target_distance_km': target_distance_km,
                'actual_distance_km': round(best_distance / 1000, 2),
                'actual_distance': round(km_to_display(best_distance / 1000, distance_unit), 2),
                'distance_unit': distance_unit,
                'budget_deviation': round((best_distance - target_distance_m) / target_distance_m, 3),
                'directional_bias': directional_bias,
                'variety_level': variety_level,
                'num_candidates': len(candidates),
                'algorithm': algorithm,
            },
            'tiles_required': tile_ids,
            'warning': warning,
        }

        if demo_visualisation_requested:
            solver_supports_demo = str(algorithm).upper() == 'GEOMETRIC'
            frames = []
            truncated = False
            if loop_demo_context is not None:
                frames = loop_demo_context.get('frames', [])
                truncated = bool(loop_demo_context.get('truncated', False))

            loop_demo_payload = {
                'enabled': bool(demo_visualisation_enabled and solver_supports_demo),
                'schema_version': 1,
                'frame_count': len(frames),
                'truncated': truncated,
                'frames': frames if demo_visualisation_enabled and solver_supports_demo else [],
            }

            if not demo_visualisation_enabled:
                loop_demo_payload['reason'] = 'debug_disabled'
            elif not solver_supports_demo:
                loop_demo_payload['reason'] = 'solver_not_supported'

            response_data['loop_demo'] = loop_demo_payload
        
        # Add debug info if enabled
        if current_app.config.get('VERBOSE_LOGGING') or current_app.config.get('DEBUG'):
            response_data['debug_info'] = {
                'start_coord': start_point,
                'target_distance_m': target_distance_m,
                'actual_distance_m': best_distance,
                'distance_deviation_percent': round((best_distance - target_distance_m) / target_distance_m * 100, 1),
                'node_count': len(best.route),
                'graph_nodes': len(graph.nodes),
                'directional_bias': directional_bias,
                'algorithm': algorithm,
                'num_candidates_returned': len(candidates),
                'lighting_context': lighting_ctx['lighting_context'],
                'lighting_context_source': lighting_ctx['source'],
                'routing_datetime_utc': lighting_ctx['routing_datetime_utc'],
            }
            
            # Edge features for short routes
            if best_distance < VISUAL_DEBUG_THRESHOLD_M:
                all_edges = _extract_edge_features(
                    graph,
                    best.route,
                    lighting_context=lighting_ctx['lighting_context'],
                    prefer_segregated_paths=prefer_segregated_paths,
                    prefer_dedicated_pavements=prefer_separated_paths,
                    allow_quiet_service_lanes=allow_quiet_service_lanes,
                    prefer_paved=prefer_paved_surfaces,
                    avoid_unsafe_roads=avoid_unsafe_roads,
                    avoid_unclassified_lanes=avoid_unclassified_lanes,
                )
                response_data['edge_features'] = all_edges
                response_data['debug_info']['visual_debug_enabled'] = True
        
        return jsonify(response_data)
        
    except ValueError as e:
        return jsonify({'error': f'Invalid input values: {str(e)}'}), 400
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({'error': f'Server error: {str(e)}'}), 500


@main.route('/api/cached-tiles', methods=['GET'])
def get_cached_tiles():
    """
    API endpoint to get all cached tiles for debug visualization.
    
    Returns a list of cached tiles with their bounding boxes for
    displaying on the map as debug overlays.
    
    Response JSON:
        {
            "tiles": [
                {
                    "tile_id": "51.45_-2.55",
                    "bbox": {"min_lat": 51.3, "min_lon": -2.7, "max_lat": 51.6, "max_lon": -2.4},
                    "created": 1707411234.5,
                    "size_mb": 245.2
                },
                ...
            ],
            "tile_size_km": 30
        }
    """
    from app.services.core.cache_manager import get_cache_manager
    from app.services.core.tile_utils import get_tile_bbox
    
    try:
        tile_size_km = current_app.config.get('TILE_SIZE_KM', 30)
        tile_overlap_km = current_app.config.get('TILE_OVERLAP_KM', 2)
        
        cache_mgr = get_cache_manager()
        cache_mgr.refresh_manifest()  # Force reload to see tiles from workers
        manifest = cache_mgr._manifest
        
        tiles = []
        for cache_key, entry in manifest.get("entries", {}).items():
            # Extract tile_id from cache key (format: region_tile_ID_modes_version)
            parts = cache_key.split("_tile_")
            if len(parts) < 2:
                continue
            
            # tile_id is between "_tile_" and the next parts
            rest = parts[1]
            # tile_id format: "51.45_-2.55" - extract lat and lon
            tile_parts = rest.split("_")
            if len(tile_parts) < 2:
                continue
            
            try:
                tile_lat = float(tile_parts[0])
                tile_lon = float(tile_parts[1])
                tile_id = f"{tile_lat:.2f}_{tile_lon:.2f}"
                
                # Calculate bounding box for this tile
                bbox = get_tile_bbox(tile_id, tile_size_km, tile_overlap_km)
                
                tiles.append({
                    "tile_id": tile_id,
                    "bbox": {
                        "min_lat": bbox[0],
                        "min_lon": bbox[1],
                        "max_lat": bbox[2],
                        "max_lon": bbox[3]
                    },
                    "created": entry.get("created"),
                    "size_mb": entry.get("size_mb", 0)
                })
            except (ValueError, IndexError):
                continue
        
        return jsonify({
            "tiles": tiles,
            "tile_size_km": tile_size_km
        })
        
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

        movement_ctx = _resolve_movement_context(data)
        
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

        lighting_ctx = _resolve_lighting_context(data, start_point, end_point)
        
        # Calculate bounding box for region detection (still needed for PBF lookup)
        buffer_deg = 0.02  # ~2.2km buffer for basic bbox
        min_lat = min(start_point[0], end_point[0]) - buffer_deg
        max_lat = max(start_point[0], end_point[0]) + buffer_deg
        min_lon = min(start_point[1], end_point[1]) - buffer_deg
        max_lon = max(start_point[1], end_point[1]) + buffer_deg
        bbox = (min_lat, min_lon, max_lat, max_lon)
        
        # =====================================================================
        # ASYNC MODE: Check tile cache and enqueue tile builds if necessary
        # Uses tile-based caching (ADR-007)
        # =====================================================================
        async_mode = current_app.config.get('ASYNC_MODE', False)
        
        if async_mode:
            from app.services.core.graph_builder import find_region_for_bbox
            from app.services.core.cache_manager import get_cache_manager
            from app.services.core.data_loader import OSMDataLoader
            from app.services.core.task_manager import get_task_manager
            from app.services.core.tile_utils import (
                get_tiles_for_route, get_tile_bbox, 
                DEFAULT_TILE_SIZE_KM, DEFAULT_TILE_OVERLAP_KM
            )
            
            greenness_mode = current_app.config.get('GREENNESS_MODE', 'FAST')
            elevation_mode = current_app.config.get('ELEVATION_MODE', 'OFF')
            normalisation_mode = current_app.config.get('NORMALISATION_MODE', 'STATIC')
            tile_size_km = current_app.config.get('TILE_SIZE_KM', DEFAULT_TILE_SIZE_KM)
            tile_overlap_km = current_app.config.get('TILE_OVERLAP_KM', DEFAULT_TILE_OVERLAP_KM)
            
            # Determine tiles first, then derive region from the TILE bbox
            # so that cache keys match what the worker uses (ADR-007 consistency)
            tile_ids = get_tiles_for_route(start_point, end_point, tile_size_km)
            first_tile_bbox = get_tile_bbox(tile_ids[0], tile_size_km, tile_overlap_km)
            region_name, _ = find_region_for_bbox(first_tile_bbox)
            cache_mgr = get_cache_manager()
            
            print(f"[API] Checking {len(tile_ids)} tiles: {tile_ids}")
            
            # Find missing tiles (check without pbf_path since tiles self-validate)
            missing_tiles = []
            for tid in tile_ids:
                is_valid = cache_mgr.is_cache_valid(
                    region_name, greenness_mode, elevation_mode, 
                    pbf_path=None, tile_id=tid
                )
                print(f"[API] Tile {tid}: {'CACHED' if is_valid else 'MISSING'}")
                if not is_valid:
                    missing_tiles.append(tid)
            
            print(f"[API] Missing tiles: {missing_tiles}")
            
            if missing_tiles:
                # Enqueue tile build tasks for each missing tile
                task_mgr = get_task_manager()
                task_ids = []
                
                for tile_id in missing_tiles:
                    result = task_mgr.enqueue_tile_build(
                        tile_id=tile_id,
                        region_name=region_name,
                        greenness_mode=greenness_mode,
                        elevation_mode=elevation_mode,
                        normalisation_mode=normalisation_mode,
                        tile_size_km=tile_size_km,
                        tile_overlap_km=tile_overlap_km
                    )
                    if result.get('task_id'):
                        task_ids.append({
                            'tile_id': tile_id,
                            'task_id': result['task_id'],
                            'is_new': result['is_new']
                        })
                
                if task_ids:
                    # Return first task ID for polling (tiles will be built in parallel)
                    return jsonify({
                        'status': 'processing',
                        'task_id': task_ids[0]['task_id'],  # Primary task to poll
                        'is_new_task': task_ids[0]['is_new'],
                        'region_name': region_name,
                        'tiles_required': tile_ids,
                        'tiles_building': [t['tile_id'] for t in task_ids],
                        'message': f'Building {len(missing_tiles)} tile(s). Poll /api/task/<task_id> for status.',
                        'start_point': list(start_point),
                        'end_point': list(end_point),
                        'bbox': bbox
                    }), 202  # Accepted
        
        # =====================================================================
        # SYNC MODE or CACHE HIT: Process immediately using tile-based caching
        # =====================================================================
        
        # Get graph using tile-based caching (ADR-007)
        # This builds only missing tiles and merges them
        graph = GraphManager.get_graph_for_route(start_point, end_point)
        
        # Calculate tile_ids for response highlighting
        # Calculate tile_ids for response highlighting
        from app.services.core.tile_utils import get_tiles_for_route, DEFAULT_TILE_SIZE_KM
        tile_size_km = current_app.config.get('TILE_SIZE_KM', DEFAULT_TILE_SIZE_KM)
        tile_ids = get_tiles_for_route(start_point, end_point, tile_size_km)
        
        # Parse routing settings from request
        use_wsm = bool(data.get('use_wsm', False))
        combine_nature = True
        scenic_preferences_enabled = bool(data.get('scenic_preferences_enabled', False))

        advanced_options = _resolve_advanced_options(data)
        prefer_lit_streets = advanced_options['prefer_lit_streets']
        avoid_unlit_streets = advanced_options['avoid_unlit_streets']
        prefer_separated_paths = advanced_options['prefer_separated_paths']
        prefer_nature_trails = advanced_options['prefer_nature_trails']
        prefer_paved_surfaces = advanced_options['prefer_paved_surfaces']
        avoid_unsafe_roads = advanced_options['avoid_unsafe_roads']
        avoid_unclassified_lanes = advanced_options['avoid_unclassified_lanes']
        prefer_segregated_paths = advanced_options['prefer_segregated_paths']
        allow_quiet_service_lanes = advanced_options['allow_quiet_service_lanes']
        advanced_compare_mode = bool(data.get('advanced_compare_mode', False))

        enabled_advanced_modifiers = []
        if prefer_separated_paths:
            enabled_advanced_modifiers.append('Prefer separated paths')
        if prefer_nature_trails:
            enabled_advanced_modifiers.append('Prefer nature trails')
        if (
            prefer_segregated_paths
            and not prefer_separated_paths
            and not prefer_nature_trails
            and advanced_options['legacy_prefer_pedestrian']
        ):
            enabled_advanced_modifiers.append('Prefer paths and trails (legacy)')
        if prefer_paved_surfaces:
            enabled_advanced_modifiers.append('Prefer paved surfaces')
        if prefer_lit_streets:
            enabled_advanced_modifiers.append('Prefer lit streets')
        if avoid_unlit_streets:
            enabled_advanced_modifiers.append('Heavily avoid unlit streets')
        if avoid_unsafe_roads:
            enabled_advanced_modifiers.append('Avoid unsafe roads')
        if avoid_unclassified_lanes:
            enabled_advanced_modifiers.append('Avoid unclassified country lanes')
        if prefer_segregated_paths:
            enabled_advanced_modifiers.append('Prefer segregated paths')
        if allow_quiet_service_lanes:
            enabled_advanced_modifiers.append('Allow quiet service lanes')

        # Advanced compare mode is only meaningful when scenic sliders are off
        # and at least one advanced option is enabled.
        if scenic_preferences_enabled or not enabled_advanced_modifiers:
            advanced_compare_mode = False

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
                print(f"[API] WSM routing enabled with weights: {weights}, combine_nature: {combine_nature}")
        
        # Initialise route finder
        finder = RouteFinder(graph)

        def _route_context(subtitle, modifiers):
            return {
                'subtitle': subtitle,
                'modifiers': modifiers or [],
            }

        def build_route_entry(route_data, graph, context=None):
            """Build JSON entry for a single route."""
            route = route_data.get('route')
            if not route:
                return None

            distance_m = route_data.get('distance', 0)
            time_seconds = route_data.get('time_seconds', 0)

            entry = {
                'route_coords': MapRenderer.route_to_coords(graph, route),
                'stats': _build_stats_payload(
                    distance_m=distance_m,
                    time_seconds=time_seconds,
                    movement_ctx=movement_ctx,
                    routing_mode='standard',
                ),
                'colour': route_data.get('colour', '#808080'),
            }

            if context is not None:
                entry['route_context'] = context

            return entry
        
        # Check for multi-route mode
        multi_route_mode = current_app.config.get('MULTI_ROUTE_MODE', False)
        
        if multi_route_mode and use_wsm and advanced_compare_mode:
            # Compare mode for advanced toggles with scenic sliders OFF:
            # always return an explicit baseline route without modifiers plus
            # the advanced route with modifiers applied.
            baseline_route, _, _, baseline_dist, baseline_time = finder.find_route(
                start_point, end_point,
                use_wsm=False,
                prefer_lit_streets=False,
                avoid_unlit_streets=False,
                prefer_separated_paths=False,
                prefer_nature_trails=False,
                prefer_paved_surfaces=False,
                avoid_unsafe_roads=False,
                avoid_unclassified_lanes=False,
                prefer_segregated_paths=False,
                allow_quiet_service_lanes=False,
                travel_profile=movement_ctx['travel_profile'],
                speed_kmh=movement_ctx['effective_speed_kmh'],
                activity=movement_ctx['activity'],
                lighting_context=lighting_ctx['lighting_context'],
            )

            balanced_route, _, _, balanced_dist, balanced_time = finder.find_route(
                start_point, end_point,
                use_wsm=True,
                weights=weights,
                combine_nature=combine_nature,
                prefer_lit_streets=prefer_lit_streets,
                avoid_unlit_streets=avoid_unlit_streets,
                prefer_separated_paths=prefer_separated_paths,
                prefer_nature_trails=prefer_nature_trails,
                prefer_paved_surfaces=prefer_paved_surfaces,
                avoid_unsafe_roads=avoid_unsafe_roads,
                avoid_unclassified_lanes=avoid_unclassified_lanes,
                prefer_segregated_paths=prefer_segregated_paths,
                allow_quiet_service_lanes=allow_quiet_service_lanes,
                travel_profile=movement_ctx['travel_profile'],
                speed_kmh=movement_ctx['effective_speed_kmh'],
                activity=movement_ctx['activity'],
                lighting_context=lighting_ctx['lighting_context'],
            )

            if not balanced_route:
                return jsonify({
                    'error': 'Could not find a route between these locations.'
                }), 404

            response_data = {
                'success': True,
                'multi_route': True,
                'routes': {
                    'baseline': build_route_entry(
                        {
                            'route': baseline_route,
                            'distance': baseline_dist,
                            'time_seconds': baseline_time,
                            'colour': '#808080',
                        },
                        graph,
                        context=_route_context('Shortest route', []),
                    ) if baseline_route else None,
                    'extremist': None,
                    'balanced': build_route_entry(
                        {
                            'route': balanced_route,
                            'distance': balanced_dist,
                            'time_seconds': balanced_time,
                            'colour': '#3B82F6',
                        },
                        graph,
                        context=_route_context('Advanced options', enabled_advanced_modifiers),
                    ),
                },
                'start_point': list(start_point),
                'end_point': list(end_point),
                'tiles_required': tile_ids if 'tile_ids' in locals() else [],
                'movement': _build_movement_payload(movement_ctx),
            }

            if current_app.config.get('VERBOSE_LOGGING') or current_app.config.get('DEBUG'):
                response_data['debug_info'] = {
                    'start_coord': start_point,
                    'end_coord': end_point,
                    'node_count_balanced': len(balanced_route) if balanced_route else 0,
                    'graph_nodes': len(graph.nodes),
                    'bbox': bbox,
                    'loaded_pbf': GraphManager.get_loaded_file_path(),
                    'multi_route_mode': True,
                    'advanced_compare_mode': True,
                    'advanced_modifiers': enabled_advanced_modifiers,
                    'lighting_context': lighting_ctx['lighting_context'],
                    'lighting_context_source': lighting_ctx['source'],
                    'routing_datetime_utc': lighting_ctx['routing_datetime_utc'],
                }

                if balanced_dist < VISUAL_DEBUG_THRESHOLD_M:
                    all_edges = _extract_edge_features(
                        graph,
                        balanced_route,
                        lighting_context=lighting_ctx['lighting_context'],
                        prefer_segregated_paths=prefer_segregated_paths,
                        prefer_dedicated_pavements=prefer_separated_paths,
                        allow_quiet_service_lanes=allow_quiet_service_lanes,
                        prefer_paved=prefer_paved_surfaces,
                        avoid_unsafe_roads=avoid_unsafe_roads,
                        avoid_unclassified_lanes=avoid_unclassified_lanes,
                    )
                    response_data['edge_features'] = all_edges
                    response_data['debug_info']['visual_debug_enabled'] = True

            return jsonify(response_data)

        if multi_route_mode and use_wsm:
            # Multi-route mode: run three A* passes
            from app.services.routing.distinct_paths_runner import find_distinct_paths
            
            distinct_result = find_distinct_paths(
                finder, start_point, end_point, weights,
                combine_nature=combine_nature,
                prefer_lit_streets=prefer_lit_streets,
                avoid_unlit_streets=avoid_unlit_streets,
                prefer_separated_paths=prefer_separated_paths,
                prefer_nature_trails=prefer_nature_trails,
                prefer_paved_surfaces=prefer_paved_surfaces,
                avoid_unsafe_roads=avoid_unsafe_roads,
                avoid_unclassified_lanes=avoid_unclassified_lanes,
                prefer_segregated_paths=prefer_segregated_paths,
                allow_quiet_service_lanes=allow_quiet_service_lanes,
                travel_profile=movement_ctx['travel_profile'],
                speed_kmh=movement_ctx['effective_speed_kmh'],
                activity=movement_ctx['activity'],
                lighting_context=lighting_ctx['lighting_context'],
            )
            
            # Validate that at least one route was found
            if not distinct_result.get('balanced', {}).get('route'):
                return jsonify({
                    'error': 'Could not find a route between these locations.'
                }), 404
            
            response_data = {
                'success': True,
                'multi_route': True,
                'routes': {
                    'baseline': build_route_entry(
                        distinct_result['baseline'],
                        graph,
                        context=_route_context('Shortest route', []),
                    ),
                    'extremist': {
                        **build_route_entry(
                            distinct_result['extremist'],
                            graph,
                            context=_route_context(
                                'Scenic emphasis',
                                enabled_advanced_modifiers,
                            ),
                        ),
                        'dominant_feature': distinct_result['extremist'].get('dominant_feature'),
                    } if distinct_result.get('extremist', {}).get('route') else None,
                    'balanced': build_route_entry(
                        distinct_result['balanced'],
                        graph,
                        context=_route_context(
                            'Custom mix',
                            enabled_advanced_modifiers,
                        ),
                    ),
                },
                'start_point': list(start_point),
                'end_point': list(end_point),
                'tiles_required': tile_ids if 'tile_ids' in dir() else [],
                'movement': _build_movement_payload(movement_ctx),
            }
            
            # Add debug info if enabled
            if current_app.config.get('VERBOSE_LOGGING') or current_app.config.get('DEBUG'):
                balanced_route = distinct_result['balanced']['route']
                balanced_distance = distinct_result['balanced']['distance']
                
                response_data['debug_info'] = {
                    'start_coord': start_point,
                    'end_coord': end_point,
                    'node_count_balanced': len(balanced_route) if balanced_route else 0,
                    'graph_nodes': len(graph.nodes),
                    'bbox': bbox,
                    'loaded_pbf': GraphManager.get_loaded_file_path(),
                    'multi_route_mode': True,
                    'lighting_context': lighting_ctx['lighting_context'],
                    'lighting_context_source': lighting_ctx['source'],
                    'routing_datetime_utc': lighting_ctx['routing_datetime_utc'],
                }
                
                # Visual debug uses balanced route
                if balanced_distance < VISUAL_DEBUG_THRESHOLD_M:
                    all_edges = _extract_edge_features(
                        graph,
                        balanced_route,
                        lighting_context=lighting_ctx['lighting_context'],
                        prefer_segregated_paths=prefer_segregated_paths,
                        prefer_dedicated_pavements=prefer_separated_paths,
                        allow_quiet_service_lanes=allow_quiet_service_lanes,
                        prefer_paved=prefer_paved_surfaces,
                        avoid_unsafe_roads=avoid_unsafe_roads,
                        avoid_unclassified_lanes=avoid_unclassified_lanes,
                    )
                    response_data['edge_features'] = all_edges
                    response_data['debug_info']['visual_debug_enabled'] = True
            
            return jsonify(response_data)
        
        # Single-route mode (legacy or non-WSM)
        route, _, _, distance, time_seconds = finder.find_route(
            start_point, end_point,
            use_wsm=use_wsm,
            weights=weights,
            combine_nature=combine_nature,
            prefer_lit_streets=prefer_lit_streets,
            avoid_unlit_streets=avoid_unlit_streets,
            prefer_separated_paths=prefer_separated_paths,
            prefer_nature_trails=prefer_nature_trails,
            prefer_paved_surfaces=prefer_paved_surfaces,
            avoid_unsafe_roads=avoid_unsafe_roads,
            avoid_unclassified_lanes=avoid_unclassified_lanes,
            prefer_segregated_paths=prefer_segregated_paths,
            allow_quiet_service_lanes=allow_quiet_service_lanes,
            travel_profile=movement_ctx['travel_profile'],
            speed_kmh=movement_ctx['effective_speed_kmh'],
            activity=movement_ctx['activity'],
            lighting_context=lighting_ctx['lighting_context'],
        )
        
        if not route:
            return jsonify({
                'error': 'Could not find a route between these locations.'
            }), 404
        
        # Build single-route response in multi-route format for frontend compatibility
        route_coords = MapRenderer.route_to_coords(graph, route)
        
        response_data = {
            'success': True,
            'multi_route': False,
            'routes': {
                'balanced': {
                    'route_coords': route_coords,
                    'stats': _build_stats_payload(
                        distance_m=distance,
                        time_seconds=time_seconds,
                        movement_ctx=movement_ctx,
                        routing_mode='standard',
                    ),
                    'colour': '#3B82F6', # Default blue
                    'route_context': _route_context(
                        'Advanced options' if enabled_advanced_modifiers else 'Single route',
                        enabled_advanced_modifiers,
                    ),
                }
            },
            'start_point': list(start_point),
            'end_point': list(end_point),
            'tiles_required': tile_ids if 'tile_ids' in locals() else [],
            'movement': _build_movement_payload(movement_ctx),
            'debug_info': {}
        }
        
        # Add debug info if enabled
        if current_app.config.get('VERBOSE_LOGGING') or current_app.config.get('DEBUG'):
            response_data['debug_info'] = {
                'start_coord': start_point,
                'end_coord': end_point,
                'node_count': len(route),
                'graph_nodes': len(graph.nodes),
                'bbox': bbox,
                'loaded_pbf': GraphManager.get_loaded_file_path(),
                'lighting_context': lighting_ctx['lighting_context'],
                'lighting_context_source': lighting_ctx['source'],
                'routing_datetime_utc': lighting_ctx['routing_datetime_utc'],
            }
            
            # Always include first 5 edges with feature data for debug panel
            first_5_edges = _extract_edge_features(
                graph,
                route,
                max_edges=5,
                lighting_context=lighting_ctx['lighting_context'],
                prefer_segregated_paths=prefer_segregated_paths,
                prefer_dedicated_pavements=prefer_separated_paths,
                allow_quiet_service_lanes=allow_quiet_service_lanes,
                prefer_paved=prefer_paved_surfaces,
                avoid_unsafe_roads=avoid_unsafe_roads,
                avoid_unclassified_lanes=avoid_unclassified_lanes,
            )
            response_data['debug_info']['edge_preview'] = first_5_edges
            
            # For short routes, include ALL edge features for visual map overlay
            if distance < VISUAL_DEBUG_THRESHOLD_M:
                all_edges = _extract_edge_features(
                    graph,
                    route,
                    lighting_context=lighting_ctx['lighting_context'],
                    prefer_segregated_paths=prefer_segregated_paths,
                    prefer_dedicated_pavements=prefer_separated_paths,
                    allow_quiet_service_lanes=allow_quiet_service_lanes,
                    prefer_paved=prefer_paved_surfaces,
                    avoid_unsafe_roads=avoid_unsafe_roads,
                    avoid_unclassified_lanes=avoid_unclassified_lanes,
                )
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

