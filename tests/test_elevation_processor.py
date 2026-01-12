"""
Test suite for the Elevation Processor module.

Tests gradient calculation, Tobler's hiking function, and directional gradients.
Uses mocked NetworkX graphs to verify correctness without making real API calls.

NOTE: API calls and DEM lookups are mocked to avoid network dependencies in unit tests.
"""

import pytest
import math
import networkx as nx
from unittest.mock import patch, MagicMock
from app.services.processors.elevation import (
    calculate_edge_gradient,
    calculate_tobler_cost,
    calculate_directional_gradients,
    process_graph_elevation,
    configure_elevation_api,
    fetch_node_elevations,
    fetch_node_elevations_local,
    MIN_EDGE_LENGTH,
    ACTIVITY_PARAMS,
)


class TestCalculateEdgeGradient:
    """Tests for the calculate_edge_gradient function."""
    
    def test_flat_edge(self):
        """Equal elevations should return zero gradient."""
        result = calculate_edge_gradient(100.0, 50.0, 50.0)
        assert result == 0.0
    
    def test_uphill_gradient(self):
        """10m rise over 100m should return 0.1 (10% grade)."""
        result = calculate_edge_gradient(100.0, 50.0, 60.0)
        assert abs(result - 0.1) < 0.001
    
    def test_downhill_gradient(self):
        """10m drop over 100m should also return 0.1 (absolute value)."""
        result = calculate_edge_gradient(100.0, 60.0, 50.0)
        assert abs(result - 0.1) < 0.001
    
    def test_steep_gradient(self):
        """50m rise over 100m should return 0.5 (50% grade)."""
        result = calculate_edge_gradient(100.0, 0.0, 50.0)
        assert abs(result - 0.5) < 0.001
    
    def test_missing_source_elevation(self):
        """Missing source elevation should return None."""
        result = calculate_edge_gradient(100.0, None, 50.0)
        assert result is None
    
    def test_missing_target_elevation(self):
        """Missing target elevation should return None."""
        result = calculate_edge_gradient(100.0, 50.0, None)
        assert result is None
    
    def test_both_elevations_missing(self):
        """Both elevations missing should return None."""
        result = calculate_edge_gradient(100.0, None, None)
        assert result is None
    
    def test_very_short_edge(self):
        """Edges shorter than MIN_EDGE_LENGTH should return 0.0."""
        result = calculate_edge_gradient(0.5, 0.0, 10.0)  # 0.5m < MIN_EDGE_LENGTH
        assert result == 0.0
    
    def test_zero_length_edge(self):
        """Zero-length edge should return 0.0 (not divide by zero)."""
        result = calculate_edge_gradient(0.0, 0.0, 10.0)
        assert result == 0.0


class TestFetchNodeElevations:
    """Tests for the fetch_node_elevations function."""
    
    def test_handles_none_graph(self):
        """Should return None when given None graph."""
        result = fetch_node_elevations(None)
        assert result is None
    
    @patch('app.services.processors.elevation.ox', None)
    def test_handles_missing_osmnx(self):
        """Should return graph unchanged when osmnx not available."""
        G = nx.MultiDiGraph()
        G.add_node(1, x=-2.587, y=51.454)
        
        result = fetch_node_elevations(G)
        
        assert result is G


class TestProcessGraphElevation:
    """Tests for the process_graph_elevation function."""
    
    @pytest.fixture
    def mock_graph(self):
        """Creates a mock NetworkX MultiDiGraph with realistic edge data."""
        G = nx.MultiDiGraph()
        
        # Add nodes with coordinates (Bristol area)
        G.add_node(1, x=-2.58, y=51.45)
        G.add_node(2, x=-2.59, y=51.46)
        G.add_node(3, x=-2.60, y=51.47)
        G.add_node(4, x=-2.61, y=51.48)
        
        # Add edges with different lengths
        G.add_edge(1, 2, 0, highway='residential', length=100.0)
        G.add_edge(2, 3, 0, highway='footway', length=50.0)
        G.add_edge(3, 4, 0, highway='path', length=200.0)
        G.add_edge(1, 4, 0, highway='primary', length=0.5)  # Very short edge
        
        return G
    
    @pytest.fixture
    def mock_graph_with_elevations(self, mock_graph):
        """Adds mock elevation data to nodes."""
        mock_graph.nodes[1]['elevation'] = 10.0
        mock_graph.nodes[2]['elevation'] = 20.0  # 10m rise
        mock_graph.nodes[3]['elevation'] = 15.0  # 5m drop
        mock_graph.nodes[4]['elevation'] = 25.0  # 10m rise
        return mock_graph
    
    def test_handles_none_graph(self):
        """Should return None when given None graph."""
        result = process_graph_elevation(None)
        assert result is None
    
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_assigns_raw_slope_cost(self, mock_fetch, mock_graph_with_elevations):
        """All edges should have raw_slope_cost attribute after processing."""
        # Mock the fetch to return graph with elevations already set
        mock_fetch.return_value = mock_graph_with_elevations
        
        processed = process_graph_elevation(mock_graph_with_elevations)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            assert 'raw_slope_cost' in data, f"Edge ({u}, {v}, {k}) missing raw_slope_cost"
    
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_correct_gradient_calculation(self, mock_fetch, mock_graph_with_elevations):
        """Gradient values should be calculated correctly."""
        mock_fetch.return_value = mock_graph_with_elevations
        
        processed = process_graph_elevation(mock_graph_with_elevations)
        
        # Edge 1->2: 10m rise over 100m = 0.1
        edge_1_2 = processed[1][2][0]
        assert abs(edge_1_2['raw_slope_cost'] - 0.1) < 0.001
        
        # Edge 2->3: 5m drop over 50m = 0.1
        edge_2_3 = processed[2][3][0]
        assert abs(edge_2_3['raw_slope_cost'] - 0.1) < 0.001
        
        # Edge 3->4: 10m rise over 200m = 0.05
        edge_3_4 = processed[3][4][0]
        assert abs(edge_3_4['raw_slope_cost'] - 0.05) < 0.001
    
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_short_edge_gets_zero_gradient(self, mock_fetch, mock_graph_with_elevations):
        """Very short edges should get 0.0 gradient."""
        mock_fetch.return_value = mock_graph_with_elevations
        
        processed = process_graph_elevation(mock_graph_with_elevations)
        
        # Edge 1->4: 0.5m length (below MIN_EDGE_LENGTH)
        edge_1_4 = processed[1][4][0]
        assert edge_1_4['raw_slope_cost'] == 0.0
    
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_missing_elevation_defaults_to_zero(self, mock_fetch, mock_graph):
        """Edges with missing elevation data should default to 0.0 gradient."""
        # No elevation data on nodes
        mock_fetch.return_value = mock_graph
        
        processed = process_graph_elevation(mock_graph)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            assert data['raw_slope_cost'] == 0.0
    
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_returns_same_graph_object(self, mock_fetch, mock_graph_with_elevations):
        """Should modify graph in-place and return the same object."""
        mock_fetch.return_value = mock_graph_with_elevations
        
        processed = process_graph_elevation(mock_graph_with_elevations)
        
        assert processed is mock_graph_with_elevations
    
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_gradient_is_valid_float(self, mock_fetch, mock_graph_with_elevations):
        """Gradient values should be non-negative floats."""
        mock_fetch.return_value = mock_graph_with_elevations
        
        processed = process_graph_elevation(mock_graph_with_elevations)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            gradient = data['raw_slope_cost']
            assert isinstance(gradient, float)
            assert gradient >= 0.0


class TestConfigureElevationApi:
    """Tests for the configure_elevation_api function."""
    
    @patch('app.services.processors.elevation.ox')
    def test_sets_url_template(self, mock_ox):
        """Should set osmnx elevation URL template."""
        mock_ox.settings = MagicMock()
        
        configure_elevation_api()
        
        assert 'opentopodata.org' in mock_ox.settings.elevation_url_template
    
    @patch('app.services.processors.elevation.ox', None)
    def test_handles_missing_osmnx(self):
        """Should not raise when osmnx not available."""
        # Should not raise any exception
        configure_elevation_api()


class TestFetchNodeElevationsLocal:
    """Tests for the fetch_node_elevations_local function."""
    
    @pytest.fixture
    def mock_graph(self):
        """Creates a mock NetworkX MultiDiGraph with node coordinates."""
        G = nx.MultiDiGraph()
        
        # Add nodes with coordinates (Bristol area)
        G.add_node(1, x=-2.58, y=51.45)
        G.add_node(2, x=-2.59, y=51.46)
        G.add_node(3, x=-2.60, y=51.47)
        
        # Add edges
        G.add_edge(1, 2, 0, highway='residential', length=100.0)
        G.add_edge(2, 3, 0, highway='footway', length=50.0)
        
        return G
    
    def test_handles_none_graph(self):
        """Should return None when given None graph."""
        result = fetch_node_elevations_local(None)
        assert result is None
    
    @patch('app.services.processors.elevation.RASTERIO_AVAILABLE', False)
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_falls_back_to_api_without_rasterio(self, mock_api_fetch, mock_graph):
        """Should fall back to API mode when rasterio unavailable."""
        mock_api_fetch.return_value = mock_graph
        
        result = fetch_node_elevations_local(mock_graph)
        
        mock_api_fetch.assert_called_once()
        assert result is mock_graph
    
    @patch('app.services.processors.elevation.DEMDataLoader')
    @patch('app.services.processors.elevation.RASTERIO_AVAILABLE', True)
    def test_uses_dem_loader(self, mock_loader_class, mock_graph):
        """Should use DEMDataLoader for elevation lookups."""
        mock_loader = MagicMock()
        mock_loader_class.return_value = mock_loader
        
        # Mock elevation results
        mock_loader.get_elevations_batch.return_value = {
            (51.45, -2.58): 20.0,
            (51.46, -2.59): 25.0,
            (51.47, -2.60): 30.0
        }
        
        result = fetch_node_elevations_local(mock_graph)
        
        # Verify DEMDataLoader was used
        mock_loader.ensure_tiles_for_bbox.assert_called_once()
        mock_loader.get_elevations_batch.assert_called_once()
        
        # Verify elevations were assigned
        assert result.nodes[1].get('elevation') == 20.0
        assert result.nodes[2].get('elevation') == 25.0
        assert result.nodes[3].get('elevation') == 30.0


class TestProcessGraphElevationModes:
    """Tests for process_graph_elevation with different modes."""
    
    @pytest.fixture
    def mock_graph_with_elevations(self):
        """Creates a graph with pre-set elevations."""
        G = nx.MultiDiGraph()
        
        G.add_node(1, x=-2.58, y=51.45, elevation=10.0)
        G.add_node(2, x=-2.59, y=51.46, elevation=20.0)
        
        G.add_edge(1, 2, 0, highway='residential', length=100.0)
        
        return G
    
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_api_mode_uses_fetch_node_elevations(self, mock_fetch, mock_graph_with_elevations):
        """API mode should use the API-based fetch function."""
        mock_fetch.return_value = mock_graph_with_elevations
        
        process_graph_elevation(mock_graph_with_elevations, mode='API')
        
        mock_fetch.assert_called_once()
    
    @patch('app.services.processors.elevation.fetch_node_elevations_local')
    def test_local_mode_uses_local_fetch(self, mock_fetch, mock_graph_with_elevations):
        """LOCAL mode should use the local DEM-based fetch function."""
        mock_fetch.return_value = mock_graph_with_elevations
        
        process_graph_elevation(mock_graph_with_elevations, mode='LOCAL')
        
        mock_fetch.assert_called_once()
    
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_default_mode_is_api(self, mock_fetch, mock_graph_with_elevations):
        """Default mode should be API."""
        mock_fetch.return_value = mock_graph_with_elevations
        
        process_graph_elevation(mock_graph_with_elevations)
        
        mock_fetch.assert_called_once()


class TestToblerHikingFunction:
    """Tests for Tobler's hiking function cost calculation."""
    
    def test_flat_terrain_returns_one(self):
        """Flat terrain (0% grade) should return cost multiplier of 1.0."""
        result = calculate_tobler_cost(0.0)
        assert abs(result - 1.0) < 0.05  # Allow small tolerance
    
    def test_mild_downhill_faster_than_flat(self):
        """Mild downhill (~5%) should be faster than flat (cost < 1.0)."""
        result = calculate_tobler_cost(-0.05)
        assert result < 1.0
    
    def test_uphill_slower_than_flat(self):
        """Any uphill gradient should be slower than flat (cost > 1.0)."""
        result_5_percent = calculate_tobler_cost(0.05)
        result_10_percent = calculate_tobler_cost(0.10)
        result_20_percent = calculate_tobler_cost(0.20)
        
        assert result_5_percent > 1.0
        assert result_10_percent > result_5_percent
        assert result_20_percent > result_10_percent
    
    def test_steep_downhill_slower_than_mild_downhill(self):
        """Steep downhill (>10%) should be slower than mild downhill (~5%)."""
        mild_downhill = calculate_tobler_cost(-0.05)
        steep_downhill = calculate_tobler_cost(-0.20)
        
        assert steep_downhill > mild_downhill
    
    def test_steep_gradients_are_symmetrically_slow(self):
        """Very steep gradients should have similar cost in both directions."""
        steep_uphill = calculate_tobler_cost(0.35)
        steep_downhill = calculate_tobler_cost(-0.35)
        
        # Both should be significantly slower than flat
        assert steep_uphill > 2.0
        assert steep_downhill > 2.0
    
    def test_running_mode_has_different_parameters(self):
        """Running mode should use different parameters than walking."""
        walking_cost = calculate_tobler_cost(0.10, activity='walking')
        running_cost = calculate_tobler_cost(0.10, activity='running')
        
        # Costs should be different due to different parameters
        assert walking_cost != running_cost
    
    def test_invalid_activity_defaults_to_walking(self):
        """Unknown activity mode should default to walking parameters."""
        result = calculate_tobler_cost(0.05, activity='cycling')
        expected = calculate_tobler_cost(0.05, activity='walking')
        
        assert result == expected


class TestDirectionalGradients:
    """Tests for directional gradient calculation."""
    
    def test_uphill_edge(self):
        """Uphill edge (u lower than v) should have positive uphill_gradient."""
        uphill, downhill, tobler, raw = calculate_directional_gradients(
            length=100.0,
            elevation_u=50.0,
            elevation_v=60.0
        )
        
        assert uphill == 0.1  # 10m rise over 100m
        assert downhill == 0.0
        assert raw == 0.1
        assert tobler > 1.0  # Slower than flat
    
    def test_downhill_edge(self):
        """Downhill edge (u higher than v) should have positive downhill_gradient."""
        uphill, downhill, tobler, raw = calculate_directional_gradients(
            length=100.0,
            elevation_u=60.0,
            elevation_v=50.0
        )
        
        assert uphill == 0.0
        assert downhill == 0.1
        assert raw == 0.1
    
    def test_flat_edge(self):
        """Flat edge should have zero gradients and tobler cost of 1.0."""
        uphill, downhill, tobler, raw = calculate_directional_gradients(
            length=100.0,
            elevation_u=50.0,
            elevation_v=50.0
        )
        
        assert uphill == 0.0
        assert downhill == 0.0
        assert raw == 0.0
        assert abs(tobler - 1.0) < 0.05
    
    def test_missing_elevation_returns_defaults(self):
        """Missing elevation data should return default values."""
        uphill, downhill, tobler, raw = calculate_directional_gradients(
            length=100.0,
            elevation_u=None,
            elevation_v=60.0
        )
        
        assert uphill == 0.0
        assert downhill == 0.0
        assert tobler == 1.0
        assert raw == 0.0
    
    def test_very_short_edge_returns_defaults(self):
        """Very short edges should return default values."""
        uphill, downhill, tobler, raw = calculate_directional_gradients(
            length=0.5,  # Less than MIN_EDGE_LENGTH
            elevation_u=50.0,
            elevation_v=60.0
        )
        
        assert uphill == 0.0
        assert downhill == 0.0
        assert tobler == 1.0
        assert raw == 0.0
    
    def test_mild_downhill_has_cost_less_than_one(self):
        """Mild downhill edge should have tobler cost less than 1.0."""
        uphill, downhill, tobler, raw = calculate_directional_gradients(
            length=100.0,
            elevation_u=55.0,
            elevation_v=50.0  # 5m drop = 5% downhill
        )
        
        assert tobler < 1.0  # Faster than flat


class TestProcessGraphElevationAttributes:
    """Tests that process_graph_elevation sets all required attributes."""
    
    @pytest.fixture
    def graph_with_elevation_nodes(self):
        """Creates a graph with elevations already set on nodes."""
        G = nx.MultiDiGraph()
        
        # Hill: node 1 is at bottom, node 2 at top
        G.add_node(1, x=-2.58, y=51.45, elevation=10.0)
        G.add_node(2, x=-2.59, y=51.46, elevation=30.0)
        
        # Add bidirectional edges (realistic for walking)
        G.add_edge(1, 2, 0, highway='footway', length=200.0)
        G.add_edge(2, 1, 0, highway='footway', length=200.0)
        
        return G
    
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_sets_all_gradient_attributes(self, mock_fetch, graph_with_elevation_nodes):
        """Should set uphill, downhill, slope_time_cost, and raw_slope_cost."""
        mock_fetch.return_value = graph_with_elevation_nodes
        
        result = process_graph_elevation(graph_with_elevation_nodes, mode='API')
        
        # Check uphill edge (1 -> 2)
        edge_up = result[1][2][0]
        assert 'uphill_gradient' in edge_up
        assert 'downhill_gradient' in edge_up
        assert 'slope_time_cost' in edge_up
        assert 'raw_slope_cost' in edge_up
        
        assert edge_up['uphill_gradient'] == 0.1  # 20m over 200m
        assert edge_up['downhill_gradient'] == 0.0
    
    @patch('app.services.processors.elevation.fetch_node_elevations')
    def test_uphill_and_downhill_edges_have_different_costs(
        self, mock_fetch, graph_with_elevation_nodes
    ):
        """Uphill and downhill edges between same nodes should have different Tobler costs."""
        mock_fetch.return_value = graph_with_elevation_nodes
        
        result = process_graph_elevation(graph_with_elevation_nodes, mode='API')
        
        uphill_edge = result[1][2][0]
        downhill_edge = result[2][1][0]
        
        # Uphill should be slower (higher cost)
        assert uphill_edge['slope_time_cost'] > downhill_edge['slope_time_cost']
        
        # Downhill might even be faster than flat if grade is optimal
        assert downhill_edge['downhill_gradient'] == 0.1
        assert uphill_edge['uphill_gradient'] == 0.1
