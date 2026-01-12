"""
Test suite for the Elevation Processor module.

Tests gradient calculation and graph processing for both API and LOCAL modes.
Uses mocked NetworkX graphs to verify correctness without making real API calls.

NOTE: API calls and DEM lookups are mocked to avoid network dependencies in unit tests.
"""

import pytest
import networkx as nx
from unittest.mock import patch, MagicMock
from app.services.processors.elevation import (
    calculate_edge_gradient,
    process_graph_elevation,
    configure_elevation_api,
    fetch_node_elevations,
    fetch_node_elevations_local,
    MIN_EDGE_LENGTH,
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

