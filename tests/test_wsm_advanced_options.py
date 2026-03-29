"""Tests for advanced option modifiers in WSM A* routing."""

import networkx as nx

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
