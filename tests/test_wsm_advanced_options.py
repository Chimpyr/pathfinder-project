"""Tests for advanced option modifiers in WSM A* routing."""

import networkx as nx

from app.routes import _resolve_advanced_options
from app.services.routing.astar.wsm_astar import WSMNetworkXAStar


def _add_edge(graph, u, v, length, **attrs):
    graph.add_edge(
        u,
        v,
        0,
        length=length,
        norm_green=0.5,
        norm_water=0.5,
        norm_social=0.5,
        norm_quiet=0.5,
        norm_slope=0.5,
        **attrs,
    )


def _distance_only_weights():
    return {
        'distance': 1.0,
        'greenness': 0.0,
        'water': 0.0,
        'quietness': 0.0,
        'social': 0.0,
        'slope': 0.0,
    }


def _build_surface_choice_graph():
    """Two alternatives: short muddy path vs slightly longer paved path."""
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_node(3, x=0.0, y=0.001)
    graph.add_node(4, x=0.001, y=0.001)

    # Calibration edges to stabilise graph-wide length range.
    graph.add_node(90, x=0.01, y=0.01)
    graph.add_node(91, x=0.011, y=0.01)
    graph.add_node(92, x=0.02, y=0.02)
    graph.add_node(93, x=0.021, y=0.02)
    _add_edge(graph, 90, 91, length=30.0, surface='asphalt')
    _add_edge(graph, 92, 93, length=70.0, surface='asphalt')

    # Path A (shorter, muddy): 1 -> 2 -> 4
    _add_edge(graph, 1, 2, length=45.0, surface='mud')
    _add_edge(graph, 2, 4, length=45.0, surface='mud')

    # Path B (slightly longer, paved): 1 -> 3 -> 4
    _add_edge(graph, 1, 3, length=50.0, surface='asphalt')
    _add_edge(graph, 3, 4, length=50.0, surface='asphalt')

    return graph


def _build_unsafe_choice_graph():
    """Two alternatives: short unsafe primary road vs safer residential path."""
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_node(3, x=0.0, y=0.001)
    graph.add_node(4, x=0.001, y=0.001)

    # Calibration edges to stabilise graph-wide length range.
    graph.add_node(90, x=0.01, y=0.01)
    graph.add_node(91, x=0.011, y=0.01)
    graph.add_node(92, x=0.02, y=0.02)
    graph.add_node(93, x=0.021, y=0.02)
    _add_edge(graph, 90, 91, length=30.0, highway='residential')
    _add_edge(graph, 92, 93, length=70.0, highway='residential')

    # Path A (shorter but unsafe primary with no sidewalk/foot tags).
    _add_edge(graph, 1, 2, length=45.0, highway='primary')
    _add_edge(graph, 2, 4, length=45.0, highway='primary')

    # Path B (slightly longer but safer residential).
    _add_edge(graph, 1, 3, length=50.0, highway='residential')
    _add_edge(graph, 3, 4, length=50.0, highway='residential')

    return graph


def _build_high_speed_unclassified_choice_graph(include_cycleway_signal=False):
    """Short high-speed unclassified road vs slightly longer safer residential option."""
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_node(3, x=0.0, y=0.001)
    graph.add_node(4, x=0.001, y=0.001)

    # Calibration edges to stabilise graph-wide length range.
    graph.add_node(90, x=0.01, y=0.01)
    graph.add_node(91, x=0.011, y=0.01)
    graph.add_node(92, x=0.02, y=0.02)
    graph.add_node(93, x=0.021, y=0.02)
    _add_edge(graph, 90, 91, length=30.0, highway='residential')
    _add_edge(graph, 92, 93, length=80.0, highway='residential')

    # Path A (shorter high-speed unclassified road without foot safety cues).
    unsafe_attrs = {
        'length': 48.0,
        'highway': 'unclassified',
        'surface': 'asphalt',
        'lit': 'no',
        'maxspeed': '60 mph',
        'cycleway:both': 'no',
        'lane_markings': 'no',
    }
    if include_cycleway_signal:
        unsafe_attrs['cycleway'] = 'lane'

    _add_edge(graph, 1, 2, **unsafe_attrs)
    _add_edge(graph, 2, 4, **unsafe_attrs)

    # Path B (slightly longer but safer residential route).
    _add_edge(graph, 1, 3, length=52.0, highway='residential', sidewalk='both', lit='yes')
    _add_edge(graph, 3, 4, length=52.0, highway='residential', sidewalk='both', lit='yes')

    return graph


def _build_unclassified_lane_choice_graph(include_safety_signal=False):
    """Short unclassified lane vs slightly longer safer residential option."""
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_node(3, x=0.0, y=0.001)
    graph.add_node(4, x=0.001, y=0.001)

    # Calibration edges to stabilise graph-wide length range.
    graph.add_node(90, x=0.01, y=0.01)
    graph.add_node(91, x=0.011, y=0.01)
    graph.add_node(92, x=0.02, y=0.02)
    graph.add_node(93, x=0.021, y=0.02)
    _add_edge(graph, 90, 91, length=30.0, highway='residential')
    _add_edge(graph, 92, 93, length=80.0, highway='residential')

    lane_attrs = {
        'length': 48.0,
        'highway': 'unclassified',
        'oneway': 'no',
    }
    if include_safety_signal:
        lane_attrs['foot'] = 'yes'

    _add_edge(graph, 1, 2, **lane_attrs)
    _add_edge(graph, 2, 4, **lane_attrs)

    _add_edge(graph, 1, 3, length=52.0, highway='residential', sidewalk='both')
    _add_edge(graph, 3, 4, length=52.0, highway='residential', sidewalk='both')

    return graph


def _build_cycleway_lighting_choice_graph():
    """Short unknown-lit cycleway vs much longer lit residential detour."""
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_node(3, x=0.0, y=0.001)
    graph.add_node(4, x=0.001, y=0.001)

    # Calibration edges to stabilise graph-wide length range.
    graph.add_node(90, x=0.01, y=0.01)
    graph.add_node(91, x=0.011, y=0.01)
    graph.add_node(92, x=0.02, y=0.02)
    graph.add_node(93, x=0.021, y=0.02)
    _add_edge(graph, 90, 91, length=30.0, highway='residential', lit='yes')
    _add_edge(graph, 92, 93, length=200.0, highway='residential', lit='yes')

    # Path A (short cycleway, no lit tag).
    _add_edge(graph, 1, 2, length=40.0, highway='cycleway')
    _add_edge(graph, 2, 4, length=40.0, highway='cycleway')

    # Path B (much longer residential detour, lit=yes).
    _add_edge(graph, 1, 3, length=80.0, highway='residential', lit='yes')
    _add_edge(graph, 3, 4, length=80.0, highway='residential', lit='yes')

    return graph


def _build_designated_cycleway_choice_graph():
    """Slightly longer designated cycleway should beat plain residential edge."""
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_node(3, x=0.0, y=0.001)
    graph.add_node(4, x=0.001, y=0.001)

    # Calibration edges to stabilise graph-wide length range.
    graph.add_node(90, x=0.01, y=0.01)
    graph.add_node(91, x=0.011, y=0.01)
    graph.add_node(92, x=0.02, y=0.02)
    graph.add_node(93, x=0.021, y=0.02)
    _add_edge(graph, 90, 91, length=30.0, highway='residential', surface='asphalt')
    _add_edge(graph, 92, 93, length=140.0, highway='residential', surface='asphalt')

    # Path A: shortest plain residential option.
    _add_edge(graph, 1, 2, length=50.0, highway='residential', surface='asphalt')
    _add_edge(graph, 2, 4, length=50.0, highway='residential', surface='asphalt')

    # Path B: slightly longer but high-quality shared cycleway.
    _add_edge(
        graph,
        1,
        3,
        length=52.0,
        highway='cycleway',
        surface='asphalt',
        foot='designated',
        bicycle='designated',
        segregated='no',
    )
    _add_edge(
        graph,
        3,
        4,
        length=52.0,
        highway='cycleway',
        surface='asphalt',
        foot='designated',
        bicycle='designated',
        segregated='no',
    )

    return graph


def _build_dedicated_pavement_choice_graph():
    """Short primary-road option vs slightly longer dedicated paved corridor."""
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_node(3, x=0.0, y=0.001)
    graph.add_node(4, x=0.001, y=0.001)

    # Calibration edges to stabilise graph-wide length range.
    graph.add_node(90, x=0.01, y=0.01)
    graph.add_node(91, x=0.011, y=0.01)
    graph.add_node(92, x=0.02, y=0.02)
    graph.add_node(93, x=0.021, y=0.02)
    _add_edge(graph, 90, 91, length=30.0, highway='residential', surface='asphalt')
    _add_edge(graph, 92, 93, length=90.0, highway='residential', surface='asphalt')

    # Path A: shortest vehicle-focused option.
    _add_edge(graph, 1, 2, length=48.0, highway='primary', surface='asphalt')
    _add_edge(graph, 2, 4, length=48.0, highway='primary', surface='asphalt')

    # Path B: slightly longer designated cycleway.
    _add_edge(
        graph,
        1,
        3,
        length=52.0,
        highway='cycleway',
        surface='asphalt',
        foot='designated',
        bicycle='designated',
    )
    _add_edge(
        graph,
        3,
        4,
        length=52.0,
        highway='cycleway',
        surface='asphalt',
        foot='designated',
        bicycle='designated',
    )

    return graph


def _build_nature_trail_choice_graph():
    """Short urban paved route vs slightly longer trail-like natural route."""
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_node(3, x=0.0, y=0.001)
    graph.add_node(4, x=0.001, y=0.001)

    # Calibration edges to stabilise graph-wide length range.
    graph.add_node(90, x=0.01, y=0.01)
    graph.add_node(91, x=0.011, y=0.01)
    graph.add_node(92, x=0.02, y=0.02)
    graph.add_node(93, x=0.021, y=0.02)
    _add_edge(graph, 90, 91, length=30.0, highway='residential', surface='asphalt')
    _add_edge(graph, 92, 93, length=90.0, highway='residential', surface='asphalt')

    # Path A: shortest urban paved option.
    _add_edge(graph, 1, 2, length=48.0, highway='residential', surface='asphalt')
    _add_edge(graph, 2, 4, length=48.0, highway='residential', surface='asphalt')

    # Path B: slightly longer nature-trail option.
    _add_edge(graph, 1, 3, length=52.0, highway='path', surface='dirt')
    _add_edge(graph, 3, 4, length=52.0, highway='path', surface='dirt')

    return graph


def _build_segregated_choice_graph(segregated_value='yes'):
    """Two separated options where segregated bonus can tip route choice."""
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_node(3, x=0.0, y=0.001)
    graph.add_node(4, x=0.001, y=0.001)

    graph.add_node(90, x=0.01, y=0.01)
    graph.add_node(91, x=0.011, y=0.01)
    graph.add_node(92, x=0.02, y=0.02)
    graph.add_node(93, x=0.021, y=0.02)
    _add_edge(graph, 90, 91, length=30.0, highway='residential', surface='asphalt')
    _add_edge(graph, 92, 93, length=90.0, highway='residential', surface='asphalt')

    # Baseline winner without segregated bonus.
    _add_edge(graph, 1, 2, length=50.0, highway='cycleway', surface='asphalt', foot='yes')
    _add_edge(graph, 2, 4, length=50.0, highway='cycleway', surface='asphalt', foot='yes')

    attrs = {
        'length': 51.0,
        'highway': 'cycleway',
        'surface': 'asphalt',
        'foot': 'yes',
    }
    if segregated_value is not None:
        attrs['segregated'] = segregated_value

    _add_edge(graph, 1, 3, **attrs)
    _add_edge(graph, 3, 4, **attrs)

    return graph


def _build_quiet_service_choice_graph(maxspeed='20 mph'):
    """Residential option vs slightly longer service lane fallback option."""
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=0.0, y=0.0)
    graph.add_node(2, x=0.001, y=0.0)
    graph.add_node(3, x=0.0, y=0.001)
    graph.add_node(4, x=0.001, y=0.001)

    graph.add_node(90, x=0.01, y=0.01)
    graph.add_node(91, x=0.011, y=0.01)
    graph.add_node(92, x=0.02, y=0.02)
    graph.add_node(93, x=0.021, y=0.02)
    _add_edge(graph, 90, 91, length=30.0, highway='residential', surface='asphalt')
    _add_edge(graph, 92, 93, length=90.0, highway='residential', surface='asphalt')

    # Baseline option (slightly shorter, no quiet-service bonus).
    _add_edge(graph, 1, 2, length=50.0, highway='residential', surface='asphalt')
    _add_edge(graph, 2, 4, length=50.0, highway='residential', surface='asphalt')

    # Candidate quiet service lane fallback.
    service_attrs = {
        'length': 50.5,
        'highway': 'service',
        'surface': 'asphalt',
        'foot': 'yes',
    }
    if maxspeed is not None:
        service_attrs['maxspeed'] = maxspeed

    _add_edge(graph, 1, 3, **service_attrs)
    _add_edge(graph, 3, 4, **service_attrs)

    return graph


def test_prefer_paved_changes_selected_path():
    graph = _build_surface_choice_graph()
    weights = _distance_only_weights()

    no_surface_pref = WSMNetworkXAStar(graph, weights=weights, prefer_paved=False)
    path_without_pref = list(no_surface_pref.astar(1, 4))

    paved_pref = WSMNetworkXAStar(graph, weights=weights, prefer_paved=True)
    path_with_pref = list(paved_pref.astar(1, 4))

    assert path_without_pref == [1, 2, 4]
    assert path_with_pref == [1, 3, 4]


def test_avoid_unsafe_changes_selected_path():
    graph = _build_unsafe_choice_graph()
    weights = _distance_only_weights()

    no_unsafe_pref = WSMNetworkXAStar(graph, weights=weights, avoid_unsafe_roads=False)
    path_without_pref = list(no_unsafe_pref.astar(1, 4))

    unsafe_pref = WSMNetworkXAStar(graph, weights=weights, avoid_unsafe_roads=True)
    path_with_pref = list(unsafe_pref.astar(1, 4))

    assert path_without_pref == [1, 2, 4]
    assert path_with_pref == [1, 3, 4]


def test_avoid_unsafe_penalises_high_speed_unclassified_without_safety():
    graph = _build_high_speed_unclassified_choice_graph()
    weights = _distance_only_weights()

    default_solver = WSMNetworkXAStar(graph, weights=weights, avoid_unsafe_roads=False)
    path_default = list(default_solver.astar(1, 4))

    unsafe_solver = WSMNetworkXAStar(graph, weights=weights, avoid_unsafe_roads=True)
    path_unsafe = list(unsafe_solver.astar(1, 4))

    assert path_default == [1, 2, 4]
    assert path_unsafe == [1, 3, 4]


def test_avoid_unsafe_does_not_penalise_high_speed_unclassified_with_cycleway_signal():
    graph = _build_high_speed_unclassified_choice_graph(include_cycleway_signal=True)
    weights = _distance_only_weights()

    unsafe_solver = WSMNetworkXAStar(graph, weights=weights, avoid_unsafe_roads=True)

    assert list(unsafe_solver.astar(1, 4)) == [1, 2, 4]


def test_prefer_separated_paths_penalises_high_speed_unclassified_without_safety():
    graph = _build_high_speed_unclassified_choice_graph()
    weights = _distance_only_weights()

    default_solver = WSMNetworkXAStar(graph, weights=weights)
    path_default = list(default_solver.astar(1, 4))

    separated_solver = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_dedicated_pavements=True,
    )
    path_separated = list(separated_solver.astar(1, 4))

    assert path_default == [1, 2, 4]
    assert path_separated == [1, 3, 4]


def test_avoid_unclassified_lanes_penalises_narrow_unclassified_lanes_without_safety():
    graph = _build_unclassified_lane_choice_graph(include_safety_signal=False)
    weights = _distance_only_weights()

    default_solver = WSMNetworkXAStar(graph, weights=weights)
    path_default = list(default_solver.astar(1, 4))

    lane_avoid_solver = WSMNetworkXAStar(
        graph,
        weights=weights,
        avoid_unclassified_lanes=True,
    )
    path_lane_avoid = list(lane_avoid_solver.astar(1, 4))

    assert path_default == [1, 2, 4]
    assert path_lane_avoid == [1, 3, 4]


def test_avoid_unclassified_lanes_keeps_unclassified_when_explicit_foot_safety_present():
    graph = _build_unclassified_lane_choice_graph(include_safety_signal=True)
    weights = _distance_only_weights()

    lane_avoid_solver = WSMNetworkXAStar(
        graph,
        weights=weights,
        avoid_unclassified_lanes=True,
    )

    assert list(lane_avoid_solver.astar(1, 4)) == [1, 2, 4]


def test_heavy_avoid_unlit_keeps_short_cycleway_when_lighting_unknown():
    """Unknown-lit cycleways should not be treated as unlit streets."""
    graph = _build_cycleway_lighting_choice_graph()
    weights = _distance_only_weights()

    default_solver = WSMNetworkXAStar(graph, weights=weights)
    path_default = list(default_solver.astar(1, 4))

    heavy_unlit_solver = WSMNetworkXAStar(
        graph,
        weights=weights,
        heavily_avoid_unlit=True,
    )
    path_heavy = list(heavy_unlit_solver.astar(1, 4))

    assert path_default == [1, 2, 4]
    assert path_heavy == [1, 2, 4]


def test_designated_paved_cycleway_gets_preference_bonus():
    """Designated paved cycleways should be preferred when safety/accessibility toggles are on."""
    graph = _build_designated_cycleway_choice_graph()
    weights = _distance_only_weights()

    default_solver = WSMNetworkXAStar(graph, weights=weights)
    path_default = list(default_solver.astar(1, 4))

    advanced_solver = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_paved=True,
        avoid_unsafe_roads=True,
    )
    path_advanced = list(advanced_solver.astar(1, 4))

    assert path_default == [1, 2, 4]
    assert path_advanced == [1, 3, 4]


def test_prefer_dedicated_pavements_changes_selected_path():
    graph = _build_dedicated_pavement_choice_graph()
    weights = _distance_only_weights()

    default_solver = WSMNetworkXAStar(graph, weights=weights)
    path_default = list(default_solver.astar(1, 4))

    dedicated_solver = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_dedicated_pavements=True,
    )
    path_dedicated = list(dedicated_solver.astar(1, 4))

    assert path_default == [1, 2, 4]
    assert path_dedicated == [1, 3, 4]


def test_prefer_nature_trails_changes_selected_path():
    graph = _build_nature_trail_choice_graph()
    weights = _distance_only_weights()

    default_solver = WSMNetworkXAStar(graph, weights=weights)
    path_default = list(default_solver.astar(1, 4))

    trail_solver = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_nature_trails=True,
    )
    path_trail = list(trail_solver.astar(1, 4))

    assert path_default == [1, 2, 4]
    assert path_trail == [1, 3, 4]


def test_nature_trails_disables_conflicting_path_surface_modes():
    graph = _build_nature_trail_choice_graph()
    weights = _distance_only_weights()

    solver = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_nature_trails=True,
        prefer_dedicated_pavements=True,
        prefer_paved=True,
    )

    assert solver.prefer_nature_trails is True
    assert solver.prefer_dedicated_pavements is False
    assert solver.prefer_paved is False


def test_prefer_segregated_paths_bonus_changes_selected_path():
    graph = _build_segregated_choice_graph(segregated_value='yes')
    weights = _distance_only_weights()

    no_segregated_bonus = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_dedicated_pavements=True,
    )
    path_without_bonus = list(no_segregated_bonus.astar(1, 4))

    with_segregated_bonus = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_dedicated_pavements=True,
        prefer_segregated_paths=True,
    )
    path_with_bonus = list(with_segregated_bonus.astar(1, 4))

    assert path_without_bonus == [1, 2, 4]
    assert path_with_bonus == [1, 3, 4]


def test_prefer_segregated_paths_missing_tag_is_neutral():
    graph = _build_segregated_choice_graph(segregated_value=None)
    weights = _distance_only_weights()

    solver = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_dedicated_pavements=True,
        prefer_segregated_paths=True,
    )

    assert list(solver.astar(1, 4)) == [1, 2, 4]


def test_quiet_service_lane_fallback_prefers_low_speed_service_edges():
    graph = _build_quiet_service_choice_graph(maxspeed='15 mph')
    weights = _distance_only_weights()

    without_fallback = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_dedicated_pavements=True,
    )
    path_without_fallback = list(without_fallback.astar(1, 4))

    with_fallback = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_dedicated_pavements=True,
        allow_quiet_service_lanes=True,
    )
    path_with_fallback = list(with_fallback.astar(1, 4))

    assert path_without_fallback == [1, 2, 4]
    assert path_with_fallback == [1, 3, 4]


def test_quiet_service_lane_requires_parseable_maxspeed_threshold():
    graph = _build_quiet_service_choice_graph(maxspeed=None)
    weights = _distance_only_weights()

    with_fallback = WSMNetworkXAStar(
        graph,
        weights=weights,
        prefer_dedicated_pavements=True,
        allow_quiet_service_lanes=True,
    )

    assert list(with_fallback.astar(1, 4)) == [1, 2, 4]


def test_resolve_advanced_options_maps_legacy_toggle_to_dedicated_mode():
    options = _resolve_advanced_options(
        {
            'prefer_pedestrian': True,
        }
    )

    assert options['legacy_prefer_pedestrian'] is True
    assert options['prefer_dedicated_pavements'] is True
    assert options['prefer_separated_paths'] is True
    assert options['prefer_nature_trails'] is False
    assert options['prefer_segregated_paths'] is False
    assert options['allow_quiet_service_lanes'] is False
    assert options['avoid_unclassified_lanes'] is False
    assert options['avoid_unclassified'] is False
    assert options['prefer_pedestrian'] is False


def test_resolve_advanced_options_enforces_conflicts_and_aliases():
    options = _resolve_advanced_options(
        {
            'prefer_separated_paths': True,
            'prefer_nature_trails': True,
            'prefer_paved_surfaces': True,
            'prefer_lit_streets': True,
            'avoid_unlit_streets': True,
            'avoid_unsafe': True,
            'avoid_unclassified_lanes': True,
            'prefer_segregated_paths': True,
            'allow_quiet_service_lanes': True,
        }
    )

    assert options['prefer_nature_trails'] is True
    assert options['prefer_separated_paths'] is False
    assert options['prefer_dedicated_pavements'] is False
    assert options['prefer_paved_surfaces'] is False
    assert options['prefer_paved'] is False
    assert options['prefer_lit_streets'] is False
    assert options['prefer_lit'] is False
    assert options['avoid_unlit_streets'] is True
    assert options['heavily_avoid_unlit'] is True
    assert options['avoid_unsafe_roads'] is True
    assert options['avoid_unclassified_lanes'] is True
    assert options['avoid_unclassified'] is True
    assert options['prefer_segregated_paths'] is False
    assert options['allow_quiet_service_lanes'] is False
