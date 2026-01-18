"""
Test suite for the Water Processor module.

Tests minimum distance scoring for water features.
Uses mocked NetworkX graphs to verify correctness without loading real PBF data.
"""

import pytest
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, box
from app.services.processors.water import (
    _calculate_water_score_distance,
    _build_spatial_index,
    process_graph_water,
)


class TestCalculateWaterScoreDistance:
    """Tests for the _calculate_water_score_distance function."""
    
    def test_no_water_returns_one(self):
        """No water features should return score of 1.0 (max cost)."""
        midpoint = Point(0, 0)
        result = _calculate_water_score_distance(midpoint, None, [])
        assert result == 1.0
    
    def test_on_water_returns_near_zero(self):
        """Edge directly on water should return score near 0.0."""
        midpoint = Point(0, 0)
        
        # Large water polygon containing the midpoint
        water_poly = box(-100, -100, 100, 100)
        water_gdf = gpd.GeoDataFrame(geometry=[water_poly], crs="EPSG:32630")
        water_sindex, water_geoms = _build_spatial_index(water_gdf)
        
        result = _calculate_water_score_distance(midpoint, water_sindex, water_geoms)
        assert result <= 0.05  # Should be very close to 0
    
    def test_distant_water_returns_one(self):
        """Water outside max distance should return 1.0."""
        midpoint = Point(0, 0)
        
        # Water polygon far from midpoint (>50m away)
        water_poly = box(500, 500, 600, 600)
        water_gdf = gpd.GeoDataFrame(geometry=[water_poly], crs="EPSG:32630")
        water_sindex, water_geoms = _build_spatial_index(water_gdf)
        
        result = _calculate_water_score_distance(midpoint, water_sindex, water_geoms)
        assert result == 1.0
    
    def test_partial_distance_returns_proportional_score(self):
        """Water at half max distance should return ~0.5."""
        midpoint = Point(0, 0)
        
        # Water polygon exactly 25m away (half of 50m max)
        water_poly = box(25, -10, 50, 10)
        water_gdf = gpd.GeoDataFrame(geometry=[water_poly], crs="EPSG:32630")
        water_sindex, water_geoms = _build_spatial_index(water_gdf)
        
        result = _calculate_water_score_distance(midpoint, water_sindex, water_geoms)
        assert 0.4 < result < 0.6  # Should be approximately 0.5


class TestProcessGraphWater:
    """Tests for the process_graph_water function."""
    
    @pytest.fixture
    def mock_graph(self):
        """Creates a mock NetworkX MultiDiGraph."""
        G = nx.MultiDiGraph()
        G.add_node(1, x=-2.58, y=51.45)
        G.add_node(2, x=-2.59, y=51.46)
        G.add_edge(1, 2, 0, highway='residential', length=100.0)
        return G
    
    @pytest.fixture
    def mock_water_gdf(self):
        """Create mock water areas in projected coordinates."""
        water_poly = box(360000, 5700000, 370000, 5710000)
        return gpd.GeoDataFrame(geometry=[water_poly], crs="EPSG:32630")
    
    def test_handles_none_graph(self):
        """Should return None when given None graph."""
        result = process_graph_water(None, None)
        assert result is None
    
    def test_handles_empty_water_gdf(self, mock_graph):
        """Should return graph unchanged with empty water GeoDataFrame."""
        result = process_graph_water(mock_graph, gpd.GeoDataFrame())
        assert result is mock_graph
    
    def test_assigns_raw_water_cost(self, mock_graph, mock_water_gdf):
        """All edges should have raw_water_cost attribute after processing."""
        processed = process_graph_water(mock_graph, mock_water_gdf)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            assert 'raw_water_cost' in data
    
    def test_cost_is_valid_float(self, mock_graph, mock_water_gdf):
        """raw_water_cost should be valid float between 0 and 1."""
        processed = process_graph_water(mock_graph, mock_water_gdf)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            cost = data['raw_water_cost']
            assert isinstance(cost, float)
            assert 0.0 <= cost <= 1.0
