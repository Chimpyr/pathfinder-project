import networkx as nx
import osmnx as ox
import inspect
from flask import current_app
from app.services.routing.astar.astar import OSMNetworkXAStar


class RouteFinder:
    """
    Service to calculate paths between two points.
    
    Supports both standard A* (shortest path by distance) and WSM A*
    (weighted scenic routing) depending on the use_wsm parameter.
    
    Also supports loop (round-trip) routing via find_loop_route().
    """

    def __init__(self, graph):
        """
        Initialise with a graph.

        Args:
            graph (networkx.MultiDiGraph): The street network graph.
        """
        self.graph = graph

    def find_loop_route(
        self, 
        start_point, 
        target_distance_m, 
        use_wsm=True, 
        weights=None, 
        combine_nature=False,
        directional_bias="none",
        variety_level=0,
        prefer_pedestrian=False,
        prefer_dedicated_pavements=False,
        prefer_separated_paths=None,
        prefer_nature_trails=False,
        prefer_paved=False,
        prefer_paved_surfaces=None,
        prefer_lit=False,
        prefer_lit_streets=None,
        avoid_unlit_streets=None,
        avoid_unsafe_roads=False,
        avoid_unclassified_lanes=False,
        prefer_segregated_paths=False,
        allow_quiet_service_lanes=False,
        use_smart_bearing=True,
        heavily_avoid_unlit=False,
        travel_profile='walking',
        speed_kmh=None,
        activity=None,
        lighting_context='night',
        loop_demo_context=None,
    ):
        """
        Finds multiple circular (loop) route candidates.
        
        Uses the plug-and-play loop solver framework. The algorithm is
        selected via config.py LOOP_SOLVER_ALGORITHM.
        
        Returns multiple candidates as LoopCandidate objects for the
        multi-loop display (similar to multi-route mode for standard
        point-to-point routing).
        
        Args:
            start_point (tuple): (lat, lon) start/end location.
            target_distance_m (float): Target loop distance in metres.
            use_wsm (bool): If True, use WSM cost function for scenic routing.
            weights (dict): Feature weights for WSM mode. Uses defaults if None.
            combine_nature (bool): If True, combine greenness and water scores.
            directional_bias (str): Direction preference ("north"/"east"/"south"/"west"/"none").
            variety_level (int): Route variety 0-3 (0 = deterministic).
            prefer_pedestrian (bool): If True, strongly favour footpaths/cycleways.
            prefer_dedicated_pavements (bool): If True, favour dedicated hard-surface active corridors.
            prefer_separated_paths (bool|None): Canonical alias of prefer_dedicated_pavements.
            prefer_nature_trails (bool): If True, favour trail-like roads/surfaces.
            prefer_paved (bool): If True, penalise unpaved/soft surfaces.
            prefer_paved_surfaces (bool|None): Canonical alias of prefer_paved.
            prefer_lit (bool): If True, penalise unlit streets, bonus lit ones.
            prefer_lit_streets (bool|None): Canonical alias of prefer_lit.
            avoid_unlit_streets (bool|None): Canonical alias of heavily_avoid_unlit.
            avoid_unsafe_roads (bool): If True, heavily penalise main roads without sidewalks.
            avoid_unclassified_lanes (bool): If True, strongly penalise unclassified lanes lacking safety cues.
            prefer_segregated_paths (bool): Bonus for segregated=yes when supported.
            allow_quiet_service_lanes (bool): Enable quiet service-lane fallback tier.
            lighting_context (str): Request lighting relevance (`daylight|twilight|night`).
            loop_demo_context (dict|None): Optional mutable dict for loop
                demo frame capture in debug mode.

        Returns:
            list: List of LoopCandidate objects (may be empty if no loops found).
                  Each candidate has .route, .distance, .scenic_cost, etc.
        """
        try:
            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Finding loop route: start={start_point}, "
                      f"target={target_distance_m/1000:.1f}km, bias={directional_bias}")

            if prefer_separated_paths is None:
                prefer_separated_paths = prefer_dedicated_pavements
            if prefer_paved_surfaces is None:
                prefer_paved_surfaces = prefer_paved
            if prefer_lit_streets is None:
                prefer_lit_streets = prefer_lit
            if avoid_unlit_streets is None:
                avoid_unlit_streets = heavily_avoid_unlit

            # Legacy pedal toggle now maps to segregated-path preference.
            prefer_segregated_paths = bool(prefer_segregated_paths or prefer_pedestrian)

            # Find the nearest node in the graph to the start point
            start_node = ox.distance.nearest_nodes(self.graph, start_point[1], start_point[0])

            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Start Node ID: {start_node}")

            # Use provided weights or fall back to config defaults
            if weights is None:
                weights = current_app.config.get('WSM_DEFAULT_WEIGHTS')
            
            # Read loop config
            num_candidates = current_app.config.get('LOOP_NUM_CANDIDATES', 3)
            distance_tolerance = current_app.config.get('LOOP_DISTANCE_TOLERANCE', 0.15)
            min_loop_distance = current_app.config.get('LOOP_MIN_DISTANCE', 1000)
            
            # Adjust search time based on distance — longer loops need
            # proportionally more time.
            if target_distance_m <= 5000:
                max_search_time = 30
            elif target_distance_m <= 10000:
                max_search_time = 45
            elif target_distance_m <= 15000:
                max_search_time = 60
            else:
                max_search_time = 120
            
            # Geometric solver runs multiple independent searches (one per bearing),
            # so it needs significantly more time than the single-pass Budget A*.
            algorithm = current_app.config.get('LOOP_SOLVER_ALGORITHM', 'BUDGET_ASTAR')
            if algorithm == 'GEOMETRIC':
                max_search_time = max(max_search_time * 4, 180)  # Allow at least 3 mins
            
            # Create solver via factory (reads LOOP_SOLVER_ALGORITHM from config)
            from app.services.routing.loop_solvers import LoopSolverFactory
            solver = LoopSolverFactory.create()

            _, resolved_activity = self._resolve_movement_context(
                travel_profile=travel_profile,
                speed_kmh=speed_kmh,
                activity=activity,
            )
            
            if current_app.config.get('VERBOSE_LOGGING'):
                algorithm = current_app.config.get('LOOP_SOLVER_ALGORITHM', 'BUDGET_ASTAR')
                print(f"[VERBOSE] Loop solver: {algorithm}, "
                      f"candidates={num_candidates}, tolerance=±{distance_tolerance*100:.0f}%")
                print(f"[VERBOSE] Weights: {weights}, combine_nature: {combine_nature}")
            
            # Find loop candidates (filter kwargs for solver compatibility).
            loop_kwargs = {
                'graph': self.graph,
                'start_node': start_node,
                'target_distance': target_distance_m,
                'weights': weights,
                'combine_nature': combine_nature,
                'directional_bias': directional_bias,
                'num_candidates': num_candidates,
                'distance_tolerance': distance_tolerance,
                'max_search_time': max_search_time,
                'variety_level': variety_level,
                'prefer_pedestrian': prefer_segregated_paths,
                'prefer_dedicated_pavements': prefer_separated_paths,
                'prefer_separated_paths': prefer_separated_paths,
                'prefer_nature_trails': prefer_nature_trails,
                'prefer_paved': prefer_paved_surfaces,
                'prefer_paved_surfaces': prefer_paved_surfaces,
                'prefer_lit': prefer_lit_streets,
                'prefer_lit_streets': prefer_lit_streets,
                'avoid_unsafe_roads': avoid_unsafe_roads,
                'avoid_unclassified_lanes': avoid_unclassified_lanes,
                'use_smart_bearing': use_smart_bearing,
                'heavily_avoid_unlit': avoid_unlit_streets,
                'avoid_unlit_streets': avoid_unlit_streets,
                'prefer_segregated_paths': prefer_segregated_paths,
                'allow_quiet_service_lanes': allow_quiet_service_lanes,
                'activity': resolved_activity,
                'lighting_context': lighting_context,
                'loop_demo_context': loop_demo_context,
            }

            try:
                params = inspect.signature(solver.find_loops).parameters
                accepts_var_kwargs = any(
                    param.kind == inspect.Parameter.VAR_KEYWORD
                    for param in params.values()
                )
                if not accepts_var_kwargs:
                    loop_kwargs = {k: v for k, v in loop_kwargs.items() if k in params}
            except (TypeError, ValueError):
                pass

            candidates = solver.find_loops(**loop_kwargs)
            
            # Filter out loops below minimum distance
            candidates = [c for c in candidates if c.distance >= min_loop_distance]
            
            if current_app.config.get('VERBOSE_LOGGING'):
                if candidates:
                    print(f"[VERBOSE] Found {len(candidates)} loop candidates:")
                    for i, c in enumerate(candidates):
                        print(f"  [{i}] {c.label}: {c.distance:.0f}m "
                              f"(±{c.deviation*100:.1f}%), quality={c.quality_score:.3f}")
                else:
                    print(f"[VERBOSE] No loop candidates found")

            return candidates
            
        except Exception as e:
            print(f"Error finding loop route: {e}")
            import traceback
            traceback.print_exc()
            return []

    def find_route(
        self,
        start_point,
        end_point,
        use_wsm=False,
        weights=None,
        combine_nature=False,
        prefer_lit=False,
        prefer_lit_streets=None,
        heavily_avoid_unlit=False,
        avoid_unlit_streets=None,
        prefer_pedestrian=False,
        prefer_dedicated_pavements=False,
        prefer_separated_paths=None,
        prefer_nature_trails=False,
        prefer_paved=False,
        prefer_paved_surfaces=None,
        avoid_unsafe_roads=False,
        avoid_unclassified_lanes=False,
        prefer_segregated_paths=False,
        allow_quiet_service_lanes=False,
        travel_profile='walking',
        speed_kmh=None,
        activity=None,
        lighting_context='night',
    ):
        """
        Finds a path between two locations (coordinates).
        
        Supports two routing modes:
        - Standard A*: Uses physical distance only (use_wsm=False)
        - WSM A*: Uses Weighted Sum Model combining distance with scenic features
        
        Args:
            start_point (tuple): (lat, lon) start location.
            end_point (tuple): (lat, lon) end location.
            use_wsm (bool): If True, use WSM cost function for scenic routing.
            weights (dict): Feature weights for WSM mode. Uses defaults if None.
            combine_nature (bool): If True, combine greenness and water into single "nature" score.
            prefer_lit (bool): If True, apply mild multiplicative lit-preference penalty.
            prefer_lit_streets (bool|None): Canonical alias of prefer_lit.
            heavily_avoid_unlit (bool): If True, apply strong multiplicative unlit-avoidance penalty.
            avoid_unlit_streets (bool|None): Canonical alias of heavily_avoid_unlit.
            prefer_pedestrian (bool): If True, apply penalty to primary/secondary roads and bonus to paths.
            prefer_dedicated_pavements (bool): If True, favour designated hard-surface active routes.
            prefer_separated_paths (bool|None): Canonical alias of prefer_dedicated_pavements.
            prefer_nature_trails (bool): If True, favour trail-like roads/surfaces.
            prefer_paved (bool): If True, penalise unpaved/soft surfaces.
            prefer_paved_surfaces (bool|None): Canonical alias of prefer_paved.
            avoid_unsafe_roads (bool): If True, heavily penalise unsafe major roads.
            avoid_unclassified_lanes (bool): If True, strongly penalise unclassified lanes lacking safety cues.
            prefer_segregated_paths (bool): Bonus for segregated=yes when supported.
            allow_quiet_service_lanes (bool): Enable quiet service-lane fallback tier.
            lighting_context (str): Request lighting relevance (`daylight|twilight|night`).

        Returns:
            tuple: (route, start_point, end_point, distance, time_seconds)
                   - route: List of node IDs representing the path.
                   - distance: Total distance in metres.
                   - time_seconds: Estimated walking time.
        """
        try:
            if current_app.config.get('VERBOSE_LOGGING'):
                mode = 'WSM' if use_wsm else 'Standard'
                print(f"[VERBOSE] Finding route ({mode}): {start_point} -> {end_point}")

            if prefer_separated_paths is None:
                prefer_separated_paths = prefer_dedicated_pavements
            if prefer_paved_surfaces is None:
                prefer_paved_surfaces = prefer_paved
            if prefer_lit_streets is None:
                prefer_lit_streets = prefer_lit
            if avoid_unlit_streets is None:
                avoid_unlit_streets = heavily_avoid_unlit

            prefer_segregated_paths = bool(prefer_segregated_paths or prefer_pedestrian)

            # Find the nearest nodes in the graph to these points
            start_node = ox.distance.nearest_nodes(self.graph, start_point[1], start_point[0])
            end_node = ox.distance.nearest_nodes(self.graph, end_point[1], end_point[0])

            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Start Node ID: {start_node}")
                print(f"[VERBOSE] End Node ID: {end_node}")

            resolved_speed_kmh, resolved_activity = self._resolve_movement_context(
                travel_profile=travel_profile,
                speed_kmh=speed_kmh,
                activity=activity,
            )

            # Select A* solver based on mode
            if use_wsm:
                from app.services.routing.astar.wsm_astar import WSMNetworkXAStar
                
                # Use provided weights or fall back to config defaults
                if weights is None:
                    weights = current_app.config.get('WSM_DEFAULT_WEIGHTS')
                
                astar_solver = WSMNetworkXAStar(
                    self.graph, weights, combine_nature=combine_nature,
                    prefer_lit=prefer_lit_streets,
                    heavily_avoid_unlit=avoid_unlit_streets,
                    prefer_pedestrian=prefer_segregated_paths,
                    prefer_dedicated_pavements=prefer_separated_paths,
                    prefer_segregated_paths=prefer_segregated_paths,
                    prefer_nature_trails=prefer_nature_trails,
                    prefer_paved=prefer_paved_surfaces,
                    avoid_unsafe_roads=avoid_unsafe_roads,
                    avoid_unclassified_lanes=avoid_unclassified_lanes,
                    allow_quiet_service_lanes=allow_quiet_service_lanes,
                    activity=resolved_activity,
                    lighting_context=lighting_context,
                )
                
                if current_app.config.get('VERBOSE_LOGGING'):
                    print(f"[VERBOSE] WSM weights: {weights}, combine_nature: {combine_nature}")
            else:
                # Standard A* using distance only
                astar_solver = OSMNetworkXAStar(self.graph)
            
            # Find path
            route_generator = astar_solver.astar(start_node, end_node)
            
            if route_generator is None:
                print(f"No route found between {start_node} and {end_node}")
                return None, None, None, 0, 0
                
            route = list(route_generator)

            if current_app.config.get('VERBOSE_LOGGING'):
                print(f"[VERBOSE] Route found: {len(route)} nodes")
                print(f"[VERBOSE] First 5 nodes: {route[:5]}")

            # Calculate total distance
            distance = self._calculate_total_distance(route)

            # Calculate time
            time_seconds = self._calculate_estimated_time(
                route=route,
                distance=distance,
                travel_profile=travel_profile,
                speed_kmh=resolved_speed_kmh,
                activity=resolved_activity,
            )
            
            # Log total WSM cost if in verbose mode
            if use_wsm and current_app.config.get('VERBOSE_LOGGING'):
                total_wsm_cost = self._calculate_total_wsm_cost(route, weights)
                print(f"[VERBOSE] Total WSM cost: {total_wsm_cost:.2f}")
                print(f"[VERBOSE] Total distance: {distance:.0f}m in {len(route)} edges")

            return route, start_point, end_point, distance, time_seconds
        except Exception as e:
            print(f"Error finding route: {e}")
            import traceback
            traceback.print_exc()
            return None, None, None, 0, 0

    def _calculate_total_distance(self, route):
        """
        Calculates the total distance of the route in meters.
        """
        distance = 0.0
        for u, v in zip(route[:-1], route[1:]):
            try:
                edge_data = self.graph.get_edge_data(u, v)
                # edge_data is a dict keyed by key (0, 1, ...). We want the one with min length.
                lengths = [d.get('length', 0) for d in edge_data.values()]
                distance += min(lengths)
            except Exception:
                pass
        return distance

    def estimate_route_time(self, route, travel_profile='walking', speed_kmh=None, activity=None):
        """Public helper for calculating ETA on an already computed route."""
        distance = self._calculate_total_distance(route)
        return self._calculate_estimated_time(
            route=route,
            distance=distance,
            travel_profile=travel_profile,
            speed_kmh=speed_kmh,
            activity=activity,
        )

    def _calculate_estimated_time(self, route, distance, travel_profile='walking', speed_kmh=None, activity=None):
        """
        Calculates route ETA using profile base speed and Tobler multipliers.
        """
        from app.services.processors.elevation import calculate_tobler_cost

        speed_kmh, activity = self._resolve_movement_context(
            travel_profile=travel_profile,
            speed_kmh=speed_kmh,
            activity=activity,
        )

        speed_ms = speed_kmh * 1000 / 3600
        if speed_ms <= 0:
            return 0

        if not route or len(route) < 2:
            return distance / speed_ms if distance > 0 else 0

        total_time = 0.0
        for u, v in zip(route[:-1], route[1:]):
            edge_data = self.graph.get_edge_data(u, v)
            if not edge_data:
                continue

            # Pick the shortest parallel edge for consistent distance/time accounting.
            best_edge = min(
                edge_data.values(),
                key=lambda item: item.get('length', float('inf')),
            )

            length = float(best_edge.get('length', 0) or 0)
            if length <= 0:
                continue

            uphill = best_edge.get('uphill_gradient')
            downhill = best_edge.get('downhill_gradient')

            if uphill is not None or downhill is not None:
                signed_gradient = float(uphill or 0.0) - float(downhill or 0.0)
                slope_multiplier = calculate_tobler_cost(
                    signed_gradient,
                    activity=activity,
                )
            else:
                slope_multiplier = float(best_edge.get('slope_time_cost', 1.0) or 1.0)

            total_time += (length / speed_ms) * slope_multiplier

        if total_time <= 0 and distance > 0:
            return distance / speed_ms

        return total_time

    def _resolve_movement_context(self, travel_profile='walking', speed_kmh=None, activity=None):
        """Resolve profile speed/activity with backward-compatible defaults."""
        profile = str(travel_profile or 'walking').strip().lower()

        defaults = {
            'walking': float(current_app.config.get(
                'DEFAULT_WALKING_SPEED_KMH',
                current_app.config.get('WALKING_SPEED_KMH', 5.0),
            )),
            'running_easy': float(current_app.config.get('DEFAULT_RUNNING_EASY_SPEED_KMH', 9.5)),
            'running_race': float(current_app.config.get('DEFAULT_RUNNING_RACE_SPEED_KMH', 12.5)),
        }

        resolved_speed = defaults.get(profile, defaults['walking'])
        if speed_kmh is not None:
            try:
                resolved_speed = float(speed_kmh)
            except (TypeError, ValueError):
                pass

        resolved_speed = max(0.1, resolved_speed)
        resolved_activity = activity or ('running' if profile.startswith('running') else 'walking')

        return resolved_speed, resolved_activity
    
    def _calculate_total_wsm_cost(self, route, weights):
        """
        Calculate total WSM cost for a route to verify A* optimality.
        
        Args:
            route: List of node IDs.
            weights: WSM weight dictionary.
        
        Returns:
            Total WSM cost of the route.
        """
        from app.services.routing.cost_calculator import compute_wsm_cost, normalise_length, find_length_range
        
        min_len, max_len = find_length_range(self.graph)
        
        total_cost = 0.0
        water_sum = 0.0
        length_sum = 0.0
        
        for u, v in zip(route[:-1], route[1:]):
            edge_data = self.graph.get_edge_data(u, v)
            if edge_data:
                # Use first edge data
                data = list(edge_data.values())[0]
                
                length = data.get('length', 0)
                norm_length = normalise_length(length, min_len, max_len)
                
                norm_water = data.get('norm_water', 0.5)
                norm_green = data.get('norm_green', 0.5)
                norm_social = data.get('norm_social', 0.5)
                norm_quiet = data.get('norm_quiet', 0.5)
                norm_slope = data.get('norm_slope', 0.5)
                
                cost = compute_wsm_cost(
                    norm_length, norm_green, norm_water,
                    norm_social, norm_quiet, norm_slope, weights
                )
                total_cost += cost
                water_sum += norm_water
                length_sum += length
        
        avg_water = water_sum / max(1, len(route) - 1)
        print(f"[VERBOSE] Avg norm_water on route: {avg_water:.3f}")
        print(f"[VERBOSE] Total length: {length_sum:.0f}m")
        
        return total_cost
