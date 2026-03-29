"""
Test suite for the Streetlight Processor module.

Validates council point-to-edge snapping and edge lighting augmentation.
"""

import networkx as nx
import geopandas as gpd
import pytest
from pyproj import Transformer
from shapely.geometry import Point

from app.services.processors.streetlights import process_graph_streetlights


def _project(lon: float, lat: float) -> tuple[float, float]:
    """Project WGS84 lon/lat into EPSG:32630."""
    transformer = Transformer.from_crs("EPSG:4326", "EPSG:32630", always_xy=True)
    return transformer.transform(lon, lat)


@pytest.fixture
def mock_graph() -> nx.MultiDiGraph:
    """Create a tiny graph around Bristol coordinates."""
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-2.5850, y=51.4540)
    graph.add_node(2, x=-2.5840, y=51.4545)
    graph.add_edge(1, 2, 0, highway="residential", length=120.0, lit="no")
    return graph


def _edge_midpoint_projected(graph: nx.MultiDiGraph, u: int, v: int) -> Point:
    """Compute projected midpoint of an edge from node lon/lat pairs."""
    x1, y1 = _project(graph.nodes[u]["x"], graph.nodes[u]["y"])
    x2, y2 = _project(graph.nodes[v]["x"], graph.nodes[v]["y"])
    return Point((x1 + x2) / 2.0, (y1 + y2) / 2.0)


def test_handles_none_graph() -> None:
    """Should return None when graph is None."""
    result = process_graph_streetlights(None, None)
    assert result is None


def test_handles_empty_streetlight_gdf(mock_graph: nx.MultiDiGraph) -> None:
    """Should return graph unchanged when no points are provided."""
    result = process_graph_streetlights(mock_graph, gpd.GeoDataFrame())
    assert result is mock_graph
    assert result[1][2][0]["lit"] == "no"


def test_snaps_nearby_point_and_sets_lit(mock_graph: nx.MultiDiGraph) -> None:
    """Nearby streetlight points should promote matched edge to lit='yes'."""
    midpoint = _edge_midpoint_projected(mock_graph, 1, 2)
    points = gpd.GeoDataFrame(
        {"source": ["bristol"], "lit": ["yes"]},
        geometry=[midpoint],
        crs="EPSG:32630",
    )

    processed = process_graph_streetlights(mock_graph, points, snap_distance_m=20.0)

    assert processed[1][2][0]["lit"] == "yes"
    assert processed[1][2][0]["lit_source"] == "council"
    assert processed[1][2][0]["lit_source_detail"] == "bristol"


def test_does_not_snap_distant_point(mock_graph: nx.MultiDiGraph) -> None:
    """Far-away points should not modify edge lighting attributes."""
    midpoint = _edge_midpoint_projected(mock_graph, 1, 2)
    far_point = Point(midpoint.x + 500.0, midpoint.y + 500.0)

    points = gpd.GeoDataFrame(
        {"source": ["south_glos"], "lit": ["yes"]},
        geometry=[far_point],
        crs="EPSG:32630",
    )

    processed = process_graph_streetlights(mock_graph, points, snap_distance_m=10.0)

    assert processed[1][2][0]["lit"] == "no"
    assert "lit_source" not in processed[1][2][0]


def test_way_id_propagates_lighting_and_regime_to_all_edges() -> None:
    """Matching one edge should propagate council fields to all edges of that way id."""
    graph = nx.MultiDiGraph()
    graph.add_node(1, x=-2.5850, y=51.4540)
    graph.add_node(2, x=-2.5845, y=51.4542)
    graph.add_node(3, x=-2.5840, y=51.4544)
    graph.add_node(4, x=-2.5838, y=51.4541)

    # Two edges on the same cycleway way id.
    graph.add_edge(
        1,
        2,
        0,
        osmid=1472097444,
        highway='cycleway',
        surface='asphalt',
        lit='no',
        lighting_regime='part_night',
    )
    graph.add_edge(
        2,
        3,
        0,
        osmid=1472097444.0,
        highway='cycleway',
        surface='asphalt',
        lit=None,
    )

    # Different way id should not be affected by propagation.
    graph.add_edge(
        2,
        4,
        0,
        osmid=1351563140,
        highway='unclassified',
        surface='asphalt',
        lit='no',
    )

    midpoint = _edge_midpoint_projected(graph, 1, 2)
    points = gpd.GeoDataFrame(
        {
            'source': ['south_glos'],
            'lit': ['yes'],
            'lighting_regime': ['all_night'],
            'lighting_regime_text': ['Sunset to sunrise'],
            'lit_tag_type': ['council_times'],
        },
        geometry=[midpoint],
        crs='EPSG:32630',
    )

    processed = process_graph_streetlights(graph, points, snap_distance_m=20.0)

    for u, v in [(1, 2), (2, 3)]:
        edge = processed[u][v][0]
        assert edge['lit'] == 'yes'
        assert edge['lit_source'] == 'council'
        assert edge['lit_source_detail'] == 'south_glos'
        assert edge['lighting_regime'] == 'all_night'
        assert edge['lighting_regime_text'] == 'Sunset to sunrise'
        assert edge['lit_tag_type'] == 'council_times'

    # Different way id remains unchanged.
    other = processed[2][4][0]
    assert other['lit'] == 'no'
    assert 'lighting_regime' not in other
