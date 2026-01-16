"""
Tests for Edge Sampling Greenness Processor

Tests the new edge sampling greenness calculation method,
including the strategy pattern factory function.
"""

import pytest
import networkx as nx
import geopandas as gpd
from shapely.geometry import Point, Polygon, LineString

# Import from new package structure
from app.services.processors.greenness import (
    get_processor,
    process_graph,
    GreennessProcessor,
    FastBufferProcessor,
    EdgeSamplingProcessor,
    NovackIsovistProcessor,
)
from app.services.processors.greenness.utils import (
    calculate_point_buffer_score,
    get_edge_geometry,
    get_edge_midpoint,
    build_spatial_index,
)


class TestFactoryFunction:
    """Tests for the greenness processor factory function."""
    
    def test_get_processor_fast(self):
        """Factory returns FastBufferProcessor for FAST mode."""
        processor = get_processor('FAST')
        assert isinstance(processor, FastBufferProcessor)
        assert processor.name == "Fast Buffer"
    
    def test_get_processor_edge_sampling(self):
        """Factory returns EdgeSamplingProcessor for EDGE_SAMPLING mode."""
        processor = get_processor('EDGE_SAMPLING')
        assert isinstance(processor, EdgeSamplingProcessor)
        assert processor.name == "Edge Sampling"
    
    def test_get_processor_novack(self):
        """Factory returns NovackIsovistProcessor for NOVACK mode."""
        processor = get_processor('NOVACK')
        assert isinstance(processor, NovackIsovistProcessor)
        assert processor.name == "Novack Isovist"
    
    def test_get_processor_case_insensitive(self):
        """Factory handles case-insensitive mode names."""
        assert isinstance(get_processor('fast'), FastBufferProcessor)
        assert isinstance(get_processor('FAST'), FastBufferProcessor)
        assert isinstance(get_processor('Fast'), FastBufferProcessor)
    
    def test_get_processor_invalid_mode(self):
        """Factory raises ValueError for unknown modes."""
        with pytest.raises(ValueError) as exc_info:
            get_processor('INVALID_MODE')
        
        assert 'INVALID_MODE' in str(exc_info.value)
        assert 'Available modes' in str(exc_info.value)


class TestEdgeSamplingProcessor:
    """Tests for the EdgeSamplingProcessor class."""
    
    @pytest.fixture
    def simple_graph(self):
        """Create a simple test graph with two nodes."""
        G = nx.MultiDiGraph()
        G.add_node(1, x=-2.54, y=51.50)  # Approx Bristol
        G.add_node(2, x=-2.53, y=51.50)
        G.add_edge(1, 2, length=100.0)
        return G
    
    @pytest.fixture
    def green_gdf(self):
        """Create a GeoDataFrame with a simple green polygon."""
        # Square green space near the test nodes (in WGS84)
        polygon = Polygon([
            (-2.545, 51.499),
            (-2.545, 51.501),
            (-2.535, 51.501),
            (-2.535, 51.499),
        ])
        gdf = gpd.GeoDataFrame(
            {'name': ['Test Park']},
            geometry=[polygon],
            crs="EPSG:4326"
        )
        return gdf
    
    def test_processor_initialisation(self):
        """Processor initialises with correct defaults."""
        processor = EdgeSamplingProcessor()
        assert processor.buffer_radius == 30.0
        assert processor.sample_interval == 20.0
    
    def test_processor_custom_params(self):
        """Processor accepts custom parameters."""
        processor = EdgeSamplingProcessor(buffer_radius=50.0, sample_interval=10.0)
        assert processor.buffer_radius == 50.0
        assert processor.sample_interval == 10.0
    
    def test_process_adds_raw_green_cost(self, simple_graph, green_gdf):
        """Processing adds raw_green_cost attribute to edges."""
        processor = EdgeSamplingProcessor()
        result = processor.process(simple_graph, green_gdf)
        
        for u, v, key, data in result.edges(keys=True, data=True):
            assert 'raw_green_cost' in data
            assert 0.0 <= data['raw_green_cost'] <= 1.0
    
    def test_process_with_no_green_data(self, simple_graph):
        """Processing handles missing green data gracefully."""
        processor = EdgeSamplingProcessor()
        result = processor.process(simple_graph, None)
        
        for u, v, key, data in result.edges(keys=True, data=True):
            assert data['raw_green_cost'] == 1.0  # No green = cost 1.0
    
    def test_process_validates_graph(self):
        """Processing validates graph input."""
        processor = EdgeSamplingProcessor()
        
        with pytest.raises(ValueError):
            processor.process(None, None)


class TestUtilityFunctions:
    """Tests for shared utility functions."""
    
    def test_calculate_point_buffer_score_no_green(self):
        """Returns 1.0 (no green) when no green polygons nearby."""
        point = Point(0, 0)
        score = calculate_point_buffer_score(point, None, [], 30.0)
        assert score == 1.0
    
    def test_calculate_point_buffer_score_inside_green(self):
        """Returns low cost when point is inside green polygon."""
        point = Point(0, 0)
        green_polygon = Polygon([(-100, -100), (-100, 100), (100, 100), (100, -100)])
        sindex, geoms = build_spatial_index(
            gpd.GeoDataFrame(geometry=[green_polygon])
        )
        
        score = calculate_point_buffer_score(point, sindex, geoms, 30.0)
        
        # Should be very low (lots of green)
        assert score < 0.1
    
    def test_calculate_point_buffer_score_outside_green(self):
        """Returns high cost when point is far from green polygons."""
        point = Point(0, 0)
        green_polygon = Polygon([(1000, 1000), (1000, 1100), (1100, 1100), (1100, 1000)])
        sindex, geoms = build_spatial_index(
            gpd.GeoDataFrame(geometry=[green_polygon])
        )
        
        score = calculate_point_buffer_score(point, sindex, geoms, 30.0)
        
        # Should be 1.0 (no green nearby)
        assert score == 1.0
    
    def test_get_edge_midpoint(self):
        """Correctly calculates edge midpoint."""
        G = nx.MultiDiGraph()
        G.add_node(1, x=-2.5, y=51.5)
        G.add_node(2, x=-2.5, y=51.5)  # Same point for simplicity
        
        midpoint = get_edge_midpoint(G, 1, 2)
        assert midpoint is not None


class TestBaseClass:
    """Tests for the abstract GreennessProcessor base class."""
    
    def test_cannot_instantiate_base_class(self):
        """Base class cannot be instantiated directly."""
        with pytest.raises(TypeError):
            GreennessProcessor()
    
    def test_subclass_must_implement_name(self):
        """Subclass must implement name property."""
        
        class IncompleteProcessor(GreennessProcessor):
            def process(self, graph, green_gdf, **kwargs):
                return graph
        
        with pytest.raises(TypeError):
            IncompleteProcessor()
    
    def test_subclass_must_implement_process(self):
        """Subclass must implement process method."""
        
        class IncompleteProcessor(GreennessProcessor):
            @property
            def name(self):
                return "Incomplete"
        
        with pytest.raises(TypeError):
            IncompleteProcessor()


class TestIntegration:
    """Integration tests for the greenness package."""
    
    def test_process_graph_convenience_function(self):
        """Test the process_graph convenience function."""
        G = nx.MultiDiGraph()
        G.add_node(1, x=-2.54, y=51.50)
        G.add_node(2, x=-2.53, y=51.50)
        G.add_edge(1, 2, length=100.0)
        
        result = process_graph(G, None, mode='FAST')
        
        for u, v, key, data in result.edges(keys=True, data=True):
            assert 'raw_green_cost' in data
    
    def test_all_processors_produce_same_attribute(self):
        """All processors add the same raw_green_cost attribute."""
        G = nx.MultiDiGraph()
        G.add_node(1, x=-2.54, y=51.50)
        G.add_node(2, x=-2.53, y=51.50)
        G.add_edge(1, 2, length=100.0)
        
        for mode in ['FAST', 'EDGE_SAMPLING']:
            G_copy = G.copy()
            processor = get_processor(mode)
            result = processor.process(G_copy, None)
            
            for u, v, key, data in result.edges(keys=True, data=True):
                assert 'raw_green_cost' in data
                assert isinstance(data['raw_green_cost'], float)
