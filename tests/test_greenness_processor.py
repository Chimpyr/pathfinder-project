"""
Test suite for the Greenness Processor module.

Tests buffer intersection (FAST) and isovist (NOVACK) scoring.
Uses mocked NetworkX graphs to verify correctness without loading real PBF data.
"""

import pytest
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, box
from app.services.processors.greenness import (
    _calculate_green_score_fast,
    _build_spatial_index,
    process_graph_greenness_fast,
    MIN_EDGE_LENGTH,
    FAST_BUFFER_RADIUS,
)


class TestCalculateGreenScoreFast:
    """Tests for the _calculate_green_score_fast function."""
    
    def test_no_green_returns_zero(self):
        """No green areas should return score of 0."""
        midpoint = Point(0, 0)
        result = _calculate_green_score_fast(midpoint, None, [])
        assert result == 0.0
    
    def test_full_green_coverage(self):
        """Green area covering entire buffer should approach 1.0."""
        midpoint = Point(0, 0)
        
        # Large green polygon covering entire buffer
        green_poly = box(-100, -100, 100, 100)
        green_gdf = gpd.GeoDataFrame(geometry=[green_poly], crs="EPSG:32630")
        green_sindex, green_geoms = _build_spatial_index(green_gdf)
        
        result = _calculate_green_score_fast(midpoint, green_sindex, green_geoms)
        assert result >= 0.95
    
    def test_partial_green_coverage(self):
        """Partial green coverage should return proportional score."""
        midpoint = Point(0, 0)
        
        # Green polygon covering roughly half the buffer
        green_poly = box(0, -50, 50, 50)
        green_gdf = gpd.GeoDataFrame(geometry=[green_poly], crs="EPSG:32630")
        green_sindex, green_geoms = _build_spatial_index(green_gdf)
        
        result = _calculate_green_score_fast(midpoint, green_sindex, green_geoms)
        assert 0.2 < result < 0.8
    
    def test_distant_green_returns_zero(self):
        """Green area outside buffer should return 0."""
        midpoint = Point(0, 0)
        
        # Green polygon far from midpoint
        green_poly = box(500, 500, 600, 600)
        green_gdf = gpd.GeoDataFrame(geometry=[green_poly], crs="EPSG:32630")
        green_sindex, green_geoms = _build_spatial_index(green_gdf)
        
        result = _calculate_green_score_fast(midpoint, green_sindex, green_geoms)
        assert result == 0.0


class TestProcessGraphGreennessFast:
    """Tests for the process_graph_greenness_fast function."""
    
    @pytest.fixture
    def mock_graph(self):
        """Creates a mock NetworkX MultiDiGraph with realistic edge data."""
        G = nx.MultiDiGraph()
        
        # Add nodes with coordinates (Bristol area)
        G.add_node(1, x=-2.58, y=51.45)
        G.add_node(2, x=-2.59, y=51.46)
        G.add_node(3, x=-2.60, y=51.47)
        
        # Add edges
        G.add_edge(1, 2, 0, highway='residential', length=100.0)
        G.add_edge(2, 3, 0, highway='footway', length=50.0)
        
        return G
    
    @pytest.fixture
    def mock_green_gdf(self):
        """Create mock green areas in projected coordinates."""
        # Green polygon near Bristol (in EPSG:32630)
        green_poly = box(360000, 5700000, 370000, 5710000)
        return gpd.GeoDataFrame(geometry=[green_poly], crs="EPSG:32630")
    
    def test_handles_none_graph(self):
        """Should return None when given None graph."""
        result = process_graph_greenness_fast(None, None)
        assert result is None
    
    def test_handles_empty_green_gdf(self, mock_graph):
        """Should return graph unchanged with empty green GeoDataFrame."""
        result = process_graph_greenness_fast(mock_graph, gpd.GeoDataFrame())
        assert result is mock_graph
    
    def test_assigns_raw_green_cost(self, mock_graph, mock_green_gdf):
        """All edges should have raw_green_cost attribute after processing."""
        processed = process_graph_greenness_fast(mock_graph, mock_green_gdf)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            assert 'raw_green_cost' in data
    
    def test_cost_is_valid_float(self, mock_graph, mock_green_gdf):
        """raw_green_cost should be valid float between 0 and 1."""
        processed = process_graph_greenness_fast(mock_graph, mock_green_gdf)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            cost = data['raw_green_cost']
            assert isinstance(cost, float)
            assert 0.0 <= cost <= 1.0
    
    def test_returns_same_graph_object(self, mock_graph, mock_green_gdf):
        """Should modify graph in-place and return the same object."""
        processed = process_graph_greenness_fast(mock_graph, mock_green_gdf)
        assert processed is mock_graph
