"""
Test suite for the Social Processor module.

Tests buffer intersection scoring for tourist and social POIs.
Uses mocked NetworkX graphs to verify correctness without loading real PBF data.
"""

import pytest
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, box
from app.services.processors.social import (
    _calculate_social_score_fast,
    _build_spatial_index,
    process_graph_social,
)


class TestCalculateSocialScoreFast:
    """Tests for the _calculate_social_score_fast function."""
    
    def test_no_pois_returns_zero(self):
        """No POIs should return score of 0."""
        midpoint = Point(0, 0)
        result = _calculate_social_score_fast(midpoint, None, [])
        assert result == 0.0
    
    def test_nearby_poi_returns_positive_score(self):
        """POI within buffer should return positive score."""
        midpoint = Point(0, 0)
        
        # POI point very close to midpoint
        poi_point = Point(10, 10)
        poi_gdf = gpd.GeoDataFrame(geometry=[poi_point], crs="EPSG:32630")
        poi_sindex, poi_geoms = _build_spatial_index(poi_gdf)
        
        result = _calculate_social_score_fast(midpoint, poi_sindex, poi_geoms)
        assert result > 0.0
    
    def test_distant_poi_returns_zero(self):
        """POI outside buffer should return 0."""
        midpoint = Point(0, 0)
        
        # POI far from midpoint
        poi_point = Point(500, 500)
        poi_gdf = gpd.GeoDataFrame(geometry=[poi_point], crs="EPSG:32630")
        poi_sindex, poi_geoms = _build_spatial_index(poi_gdf)
        
        result = _calculate_social_score_fast(midpoint, poi_sindex, poi_geoms)
        assert result == 0.0
    
    def test_multiple_pois_higher_score(self):
        """Multiple POIs should result in higher score."""
        midpoint = Point(0, 0)
        
        # Single POI
        single_poi = Point(10, 10)
        single_gdf = gpd.GeoDataFrame(geometry=[single_poi], crs="EPSG:32630")
        single_sindex, single_geoms = _build_spatial_index(single_gdf)
        single_score = _calculate_social_score_fast(midpoint, single_sindex, single_geoms)
        
        # Multiple POIs
        multi_pois = [Point(10, 10), Point(15, 15), Point(20, 0)]
        multi_gdf = gpd.GeoDataFrame(geometry=multi_pois, crs="EPSG:32630")
        multi_sindex, multi_geoms = _build_spatial_index(multi_gdf)
        multi_score = _calculate_social_score_fast(midpoint, multi_sindex, multi_geoms)
        
        assert multi_score >= single_score


class TestProcessGraphSocial:
    """Tests for the process_graph_social function."""
    
    @pytest.fixture
    def mock_graph(self):
        """Creates a mock NetworkX MultiDiGraph."""
        G = nx.MultiDiGraph()
        G.add_node(1, x=-2.58, y=51.45)
        G.add_node(2, x=-2.59, y=51.46)
        G.add_edge(1, 2, 0, highway='residential', length=100.0)
        return G
    
    @pytest.fixture
    def mock_poi_gdf(self):
        """Create mock POIs in projected coordinates."""
        poi_point = Point(360500, 5705000)
        return gpd.GeoDataFrame(geometry=[poi_point], crs="EPSG:32630")
    
    def test_handles_none_graph(self):
        """Should return None when given None graph."""
        result = process_graph_social(None, None)
        assert result is None
    
    def test_handles_empty_poi_gdf(self, mock_graph):
        """Should return graph unchanged with empty POI GeoDataFrame."""
        result = process_graph_social(mock_graph, gpd.GeoDataFrame())
        assert result is mock_graph
    
    def test_assigns_raw_social_cost(self, mock_graph, mock_poi_gdf):
        """All edges should have raw_social_cost attribute after processing."""
        processed = process_graph_social(mock_graph, mock_poi_gdf)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            assert 'raw_social_cost' in data
    
    def test_cost_is_valid_float(self, mock_graph, mock_poi_gdf):
        """raw_social_cost should be valid float between 0 and 1."""
        processed = process_graph_social(mock_graph, mock_poi_gdf)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            cost = data['raw_social_cost']
            assert isinstance(cost, float)
            assert 0.0 <= cost <= 1.0
