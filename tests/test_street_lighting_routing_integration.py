"""Integration tests for routing toggles with council street lighting data.

These tests verify that council point snapping updates graph edge lighting
attributes and that both routing toggles consume those updated attributes.
"""

import geopandas as gpd
import networkx as nx
import pytest
from pyproj import Transformer
from shapely.geometry import Point

from app.services.processors.streetlights import process_graph_streetlights
from app.services.routing.astar.wsm_astar import WSMNetworkXAStar, _compute_lit_multiplier


def _project(lon: float, lat: float) -> tuple[float, float]:
    """Project WGS84 lon/lat into EPSG:32630 coordinates."""
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32630", always_xy=True)
    return transformer.transform(lon, lat)


def _edge_midpoint_projected(graph: nx.MultiDiGraph, u: int, v: int) -> Point:
    """Build a projected midpoint for a directed edge from graph node coords."""
    x1, y1 = _project(float(graph.nodes[u]["x"]), float(graph.nodes[u]["y"]))
    x2, y2 = _project(float(graph.nodes[v]["x"]), float(graph.nodes[v]["y"]))
    return Point((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def _add_test_edge(graph: nx.MultiDiGraph, u: int, v: int, length: float, lit: str = "no") -> None:
    """Add an edge with deterministic attributes for routing-cost comparisons."""
    graph.add_edge(
        u,
        v,
        0,
        length=length,
        lit=lit,
        norm_green=0.5,
        norm_water=0.5,
        norm_social=0.5,
        norm_quiet=0.5,
        norm_slope=0.5,
    )


def _primary(value):
    if isinstance(value, list):
        return value[0] if value else None
    return value


@pytest.fixture
def routing_graph() -> nx.MultiDiGraph:
    """Create two alternative routes between node 1 and node 4.

    Initial state:
    - Path A: 1 -> 2 -> 4 (unlit edges)
    - Path B: 1 -> 3 -> 4 (also unlit until council snapping promotes it)

    Extra disconnected edges (30m and 70m) stabilise graph-wide length
    normalisation so path edges sit at a non-zero midpoint cost.
    """
    graph = nx.MultiDiGraph()

    graph.add_node(1, x=-2.5850, y=51.4540)
    graph.add_node(2, x=-2.5845, y=51.4540)
    graph.add_node(3, x=-2.5850, y=51.4545)
    graph.add_node(4, x=-2.5845, y=51.4545)

    # Disconnected nodes used only to stabilise min/max edge length range.
    graph.add_node(90, x=-2.5800, y=51.4500)
    graph.add_node(91, x=-2.5797, y=51.4500)
    graph.add_node(92, x=-2.5790, y=51.4510)
    graph.add_node(93, x=-2.5780, y=51.4510)

    # Path A (unlit)
    _add_test_edge(graph, 1, 2, length=50.0, lit="no")
    _add_test_edge(graph, 2, 4, length=50.0, lit="no")

    # Path B (will be promoted by council streetlights)
    _add_test_edge(graph, 1, 3, length=50.0, lit="no")
    _add_test_edge(graph, 3, 4, length=50.0, lit="no")

    # Disconnected calibration edges for graph-wide length normalisation.
    _add_test_edge(graph, 90, 91, length=30.0, lit="no")
    _add_test_edge(graph, 92, 93, length=70.0, lit="no")

    return graph


def test_lit_multiplier_accepts_council_promoted_edges() -> None:
    """Council-provenance edges should use lit=yes multipliers."""
    council_edge = {
        "lit": "yes",
        "lit_source": "council",
        "lit_source_detail": "bristol",
    }

    assert _compute_lit_multiplier(council_edge, heavily_avoid=False) == pytest.approx(0.85)
    assert _compute_lit_multiplier(council_edge, heavily_avoid=True) == pytest.approx(0.70)


def test_lighting_penalties_are_neutral_in_daylight() -> None:
    """Daylight context should neutralise both lit preference modes."""
    dark_edge = {'lit': 'no'}

    assert _compute_lit_multiplier(
        dark_edge,
        heavily_avoid=False,
        lighting_context='daylight',
    ) == pytest.approx(1.0)
    assert _compute_lit_multiplier(
        dark_edge,
        heavily_avoid=True,
        lighting_context='daylight',
    ) == pytest.approx(1.0)


def test_all_night_regime_promotes_unknown_lighting_at_night() -> None:
    """Regime metadata should upgrade unknown-lit edges when policy implies all-night lighting."""
    regime_edge = {
        'lit': None,
        'lighting_regime': 'All night',
    }

    assert _compute_lit_multiplier(
        regime_edge,
        heavily_avoid=True,
        lighting_context='night',
    ) == pytest.approx(0.70)


def test_prefer_lit_routes_through_council_promoted_edges(routing_graph: nx.MultiDiGraph) -> None:
    """Prefer-lit mode should favour edges promoted to lit=yes by council data."""
    points = gpd.GeoDataFrame(
        {"source": ["bristol", "bristol"], "lit": ["yes", "yes"]},
        geometry=[
            _edge_midpoint_projected(routing_graph, 1, 3),
            _edge_midpoint_projected(routing_graph, 3, 4),
        ],
        crs="EPSG:32630",
    )

    processed = process_graph_streetlights(routing_graph, points, snap_distance_m=20.0)

    assert processed[1][3][0]["lit"] == "yes"
    assert processed[1][3][0]["lit_source"] == "council"
    assert processed[3][4][0]["lit"] == "yes"
    assert processed[3][4][0]["lit_source"] == "council"

    weights = {
        "distance": 1.0,
        "greenness": 0.0,
        "water": 0.0,
        "quietness": 0.0,
        "social": 0.0,
        "slope": 0.0,
    }
    solver = WSMNetworkXAStar(processed, weights=weights, prefer_lit=True)

    path = list(solver.astar(1, 4))
    assert path == [1, 3, 4]


def test_heavy_avoid_unlit_routes_through_council_promoted_edges(
    routing_graph: nx.MultiDiGraph,
) -> None:
    """Heavy avoid-unlit mode should also favour council-promoted lit edges."""
    points = gpd.GeoDataFrame(
        {"source": ["south_glos", "south_glos"], "lit": ["yes", "yes"]},
        geometry=[
            _edge_midpoint_projected(routing_graph, 1, 3),
            _edge_midpoint_projected(routing_graph, 3, 4),
        ],
        crs="EPSG:32630",
    )

    processed = process_graph_streetlights(routing_graph, points, snap_distance_m=20.0)

    weights = {
        "distance": 1.0,
        "greenness": 0.0,
        "water": 0.0,
        "quietness": 0.0,
        "social": 0.0,
        "slope": 0.0,
    }
    solver = WSMNetworkXAStar(processed, weights=weights, heavily_avoid_unlit=True)

    path = list(solver.astar(1, 4))
    assert path == [1, 3, 4]


def test_way147_all_night_avoids_brief_way135_detour() -> None:
    """Regression: full way-id propagation prevents brief Long Down Avenue detour."""
    graph = nx.MultiDiGraph()

    # Route choice graph: main cycleway with optional short detour via road.
    graph.add_node(1, x=-2.5850, y=51.4540)
    graph.add_node(2, x=-2.5845, y=51.4541)
    graph.add_node(3, x=-2.5843, y=51.4542)
    graph.add_node(4, x=-2.5838, y=51.4544)

    # Calibration edges for length range stability.
    graph.add_node(90, x=-2.5800, y=51.4500)
    graph.add_node(91, x=-2.5798, y=51.4500)
    graph.add_node(92, x=-2.5790, y=51.4510)
    graph.add_node(93, x=-2.5780, y=51.4510)
    _add_test_edge(graph, 90, 91, length=30.0, lit='yes')
    _add_test_edge(graph, 92, 93, length=150.0, lit='yes')

    # Way 1472097444 cycleway path (initially unknown lit).
    graph.add_edge(
        1,
        2,
        0,
        length=40.0,
        osmid=1472097444,
        highway='cycleway',
        surface='asphalt',
        foot='designated',
        bicycle='designated',
        segregated='no',
        lit=None,
        norm_green=0.5,
        norm_water=0.5,
        norm_social=0.5,
        norm_quiet=0.5,
        norm_slope=0.5,
    )
    graph.add_edge(
        2,
        4,
        0,
        length=60.0,
        osmid=1472097444.0,
        highway='cycleway',
        surface='asphalt',
        foot='designated',
        bicycle='designated',
        segregated='no',
        lit=None,
        norm_green=0.5,
        norm_water=0.5,
        norm_social=0.5,
        norm_quiet=0.5,
        norm_slope=0.5,
    )

    # Brief detour branch via Long Down Avenue.
    graph.add_edge(
        2,
        3,
        0,
        length=5.0,
        osmid=999999,
        highway='footway',
        surface='asphalt',
        lit='yes',
        norm_green=0.5,
        norm_water=0.5,
        norm_social=0.5,
        norm_quiet=0.5,
        norm_slope=0.5,
    )
    graph.add_edge(
        3,
        4,
        0,
        length=55.0,
        osmid=1351563140,
        name='Long Down Avenue',
        highway='unclassified',
        surface='asphalt',
        lit='yes',
        norm_green=0.5,
        norm_water=0.5,
        norm_social=0.5,
        norm_quiet=0.5,
        norm_slope=0.5,
    )

    # Match only first edge of way 147; processor should propagate to all 147 edges.
    points = gpd.GeoDataFrame(
        {
            'source': ['south_glos'],
            'lit': ['yes'],
            'lighting_regime': ['all_night'],
            'lighting_regime_text': ['Sunset to sunrise'],
            'lit_tag_type': ['council_times'],
        },
        geometry=[_edge_midpoint_projected(graph, 1, 2)],
        crs='EPSG:32630',
    )

    processed = process_graph_streetlights(graph, points, snap_distance_m=20.0)

    # Ensure way-wide propagation happened on 1472097444.
    assert processed[2][4][0]['lit'] == 'yes'
    assert processed[2][4][0]['lighting_regime'] == 'all_night'

    weights = {
        'distance': 1.0,
        'greenness': 0.0,
        'water': 0.0,
        'quietness': 0.0,
        'social': 0.0,
        'slope': 0.0,
    }

    solver = WSMNetworkXAStar(
        processed,
        weights=weights,
        prefer_paved=True,
        heavily_avoid_unlit=True,
        avoid_unsafe_roads=True,
        lighting_context='night',
    )
    path = list(solver.astar(1, 4))
    assert path == [1, 2, 4]

    # Verify the chosen path does not briefly use Long Down Avenue way id.
    chosen_way_ids = []
    for u, v in zip(path[:-1], path[1:]):
        edge = min(processed.get_edge_data(u, v).values(), key=lambda d: d.get('length', float('inf')))
        chosen_way_ids.append(str(_primary(edge.get('osmid'))))

    assert '1351563140' not in chosen_way_ids
