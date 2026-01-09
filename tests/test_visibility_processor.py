"""
Test suite for the Visibility Processor module.

Tests isovist calculation, green visibility scoring, and graph processing.
Uses mocked geometries to verify correctness without loading real PBF data.
"""

import pytest
import math
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, Polygon, box, LineString
from app.services.visibility_processor import (
    discretise_edge,
    calculate_isovist,
    calculate_green_score,
    build_spatial_indices,
    process_graph_greenness,
    transform_coords,
    SEARCH_RADIUS,
    SAMPLE_INTERVAL,
    MAX_VISIBLE_AREA,
    MIN_EDGE_LENGTH,
)


class TestDiscretiseEdge:
    """Tests for the discretise_edge function."""
    
    def test_short_edge_returns_start_only(self):
        """Edges shorter than MIN_EDGE_LENGTH return only start point."""
        start = Point(0, 0)
        end = Point(0.5, 0)
        length = 0.5  # Less than MIN_EDGE_LENGTH (1.0)
        
        result = discretise_edge(start, end, length)
        
        assert len(result) == 1
        assert result[0].equals(start)
    
    def test_medium_edge_returns_start_and_end(self):
        """Edges between MIN_EDGE_LENGTH and SAMPLE_INTERVAL return start and end."""
        start = Point(0, 0)
        end = Point(40, 0)
        length = 40.0  # Less than SAMPLE_INTERVAL (50)
        
        result = discretise_edge(start, end, length)
        
        assert len(result) == 2
        assert result[0].equals(start)
        assert result[1].equals(end)
    
    def test_long_edge_interpolates_points(self):
        """Edges longer than SAMPLE_INTERVAL are discretised at regular intervals."""
        start = Point(0, 0)
        end = Point(150, 0)
        length = 150.0  # 3x SAMPLE_INTERVAL
        
        result = discretise_edge(start, end, length)
        
        # Should have 4 points (0m, 50m, 100m, 150m)
        assert len(result) >= 3
        # First and last should match start/end
        assert abs(result[0].x - start.x) < 0.01
        assert abs(result[-1].x - end.x) < 0.01


class TestCalculateIsovist:
    """Tests for the calculate_isovist function."""
    
    def test_no_buildings_returns_full_circle(self):
        """Without buildings, isovist is full circular buffer."""
        point = Point(0, 0)
        
        result = calculate_isovist(point, None, [], radius=100)
        
        # Should be approximately a circle with area π × 100²
        expected_area = math.pi * 100 * 100
        assert abs(result.area - expected_area) / expected_area < 0.1  # 10% tolerance
    
    def test_building_occludes_sector(self):
        """Building in front of point should reduce visible area."""
        point = Point(0, 0)
        
        # Building directly east of point, 50m away
        building = box(50, -20, 70, 20)
        buildings_gdf = gpd.GeoDataFrame(geometry=[building], crs="EPSG:32630")
        
        green_sindex, buildings_sindex, _, buildings_geoms = \
            build_spatial_indices(None, buildings_gdf)
        
        result = calculate_isovist(point, buildings_sindex, buildings_geoms, radius=100)
        
        # Isovist should be smaller than full circle due to building occlusion
        full_circle_area = math.pi * 100 * 100
        assert result.area < full_circle_area * 0.95  # At least 5% reduction
    
    def test_isovist_contains_origin(self):
        """Isovist polygon should contain the observation point."""
        point = Point(0, 0)
        
        result = calculate_isovist(point, None, [], radius=100)
        
        assert result.contains(point)


class TestCalculateGreenScore:
    """Tests for the calculate_green_score function."""
    
    def test_no_green_returns_zero(self):
        """No green areas should return score of 0."""
        isovist = Point(0, 0).buffer(100)
        
        result = calculate_green_score(isovist, None, [])
        
        assert result == 0.0
    
    def test_full_green_coverage_returns_one(self):
        """Green area covering entire isovist should approach 1.0."""
        isovist = Point(0, 0).buffer(100)
        
        # Large green polygon covering entire isovist
        green_poly = box(-200, -200, 200, 200)
        green_gdf = gpd.GeoDataFrame(geometry=[green_poly], crs="EPSG:32630")
        
        green_sindex, _, green_geoms, _ = build_spatial_indices(green_gdf, None)
        
        result = calculate_green_score(isovist, green_sindex, green_geoms)
        
        assert result >= 0.95  # Should be close to 1.0
    
    def test_partial_green_coverage(self):
        """Partial green coverage should return proportional score."""
        isovist = Point(0, 0).buffer(100)
        
        # Green polygon covering roughly half the isovist
        green_poly = box(0, -150, 150, 150)  # Eastern half only
        green_gdf = gpd.GeoDataFrame(geometry=[green_poly], crs="EPSG:32630")
        
        green_sindex, _, green_geoms, _ = build_spatial_indices(green_gdf, None)
        
        result = calculate_green_score(isovist, green_sindex, green_geoms)
        
        # Should be roughly 0.5 (half coverage)
        assert 0.3 < result < 0.7
    
    def test_score_clamped_to_valid_range(self):
        """Score should always be between 0.0 and 1.0."""
        isovist = Point(0, 0).buffer(100)
        
        # Test with empty isovist
        empty_isovist = Polygon()
        result = calculate_green_score(empty_isovist, None, [])
        assert 0.0 <= result <= 1.0


class TestBuildSpatialIndices:
    """Tests for the build_spatial_indices function."""
    
    def test_empty_inputs_returns_none_indices(self):
        """Empty GeoDataFrames should return None indices."""
        green_sindex, buildings_sindex, green_geoms, buildings_geoms = \
            build_spatial_indices(gpd.GeoDataFrame(), gpd.GeoDataFrame())
        
        assert green_sindex is None
        assert buildings_sindex is None
        assert green_geoms == []
        assert buildings_geoms == []
    
    def test_valid_inputs_returns_indices(self):
        """Valid GeoDataFrames should return working spatial indices."""
        green_poly = box(0, 0, 100, 100)
        building_poly = box(200, 200, 250, 250)
        
        green_gdf = gpd.GeoDataFrame(geometry=[green_poly], crs="EPSG:32630")
        buildings_gdf = gpd.GeoDataFrame(geometry=[building_poly], crs="EPSG:32630")
        
        green_sindex, buildings_sindex, green_geoms, buildings_geoms = \
            build_spatial_indices(green_gdf, buildings_gdf)
        
        assert green_sindex is not None
        assert buildings_sindex is not None
        assert len(green_geoms) == 1
        assert len(buildings_geoms) == 1


class TestTransformCoords:
    """Tests for the transform_coords function."""
    
    def test_bristol_coordinates(self):
        """Bristol coordinates should transform to reasonable UTM values."""
        # Bristol city centre (approximate)
        lon, lat = -2.587, 51.454
        
        x, y = transform_coords(lon, lat)
        
        # UTM zone 30N coordinates for Bristol should be around:
        # X: ~529,000, Y: ~5,703,000
        assert 500000 < x < 600000
        assert 5600000 < y < 5800000


class TestProcessGraphGreenness:
    """Tests for the process_graph_greenness function."""
    
    @pytest.fixture
    def mock_graph(self):
        """Create a mock graph with projected coordinates."""
        G = nx.MultiDiGraph()
        
        # Add nodes with WGS84 coordinates (Bristol area)
        G.add_node(1, x=-2.587, y=51.454)
        G.add_node(2, x=-2.586, y=51.455)
        
        # Add edge
        G.add_edge(1, 2, 0, length=150.0, highway='residential')
        
        return G
    
    @pytest.fixture
    def mock_green_gdf(self):
        """Create mock green areas in projected coordinates."""
        # Green polygon near Bristol (in EPSG:32630)
        green_poly = box(360000, 5700000, 370000, 5710000)
        return gpd.GeoDataFrame(geometry=[green_poly], crs="EPSG:32630")
    
    def test_assigns_green_visibility_score(self, mock_graph, mock_green_gdf):
        """All edges should have green_visibility_score after processing."""
        result = process_graph_greenness(mock_graph, mock_green_gdf, None)
        
        for u, v, k, data in result.edges(keys=True, data=True):
            assert 'green_visibility_score' in data
    
    def test_score_is_valid_float(self, mock_graph, mock_green_gdf):
        """Green visibility scores should be valid floats between 0 and 1."""
        result = process_graph_greenness(mock_graph, mock_green_gdf, None)
        
        for u, v, k, data in result.edges(keys=True, data=True):
            score = data['green_visibility_score']
            assert isinstance(score, float)
            assert 0.0 <= score <= 1.0
    
    def test_handles_none_graph(self):
        """Should handle None graph input gracefully."""
        result = process_graph_greenness(None, None, None)
        assert result is None
    
    def test_handles_empty_green_gdf(self, mock_graph):
        """Should handle empty green GeoDataFrame gracefully."""
        result = process_graph_greenness(mock_graph, gpd.GeoDataFrame(), None)
        
        # Graph should be returned unchanged (no green_visibility_score added)
        assert result is mock_graph
