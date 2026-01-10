"""
Test suite for the Quietness Processor module.

Tests highway tag classification and graph processing.
Uses mocked NetworkX graphs to verify correctness without loading real PBF data.

NOTE: compute_raw_quiet_cost tests are marked as skip until WSM A* implementation.
"""

import pytest
import networkx as nx
from app.services.processors.quietness import (
    classify_highway,
    compute_raw_quiet_cost,
    process_graph_quietness,
    NOISE_FACTOR_NOISY,
    NOISE_FACTOR_QUIET,
    NOISE_FACTOR_DEFAULT,
    NOISY_TAGS,
    QUIET_TAGS,
)


class TestClassifyHighway:
    """Tests for the classify_highway function."""
    
    @pytest.mark.parametrize("highway_tag", list(NOISY_TAGS))
    def test_classify_noisy_highway(self, highway_tag):
        """Noisy highway tags should return NOISE_FACTOR_NOISY (1.0)."""
        result = classify_highway(highway_tag)
        assert result == NOISE_FACTOR_NOISY, f"Expected {NOISE_FACTOR_NOISY} for '{highway_tag}', got {result}"
    
    @pytest.mark.parametrize("highway_tag", list(QUIET_TAGS))
    def test_classify_quiet_highway(self, highway_tag):
        """Quiet highway tags should return NOISE_FACTOR_QUIET (2.0)."""
        result = classify_highway(highway_tag)
        assert result == NOISE_FACTOR_QUIET, f"Expected {NOISE_FACTOR_QUIET} for '{highway_tag}', got {result}"
    
    @pytest.mark.parametrize("highway_tag", ['tertiary', 'unclassified', 'unknown_road_type', 'construction'])
    def test_classify_unknown_highway(self, highway_tag):
        """Unknown/neutral highway tags should return NOISE_FACTOR_DEFAULT (1.5)."""
        result = classify_highway(highway_tag)
        assert result == NOISE_FACTOR_DEFAULT, f"Expected {NOISE_FACTOR_DEFAULT} for '{highway_tag}', got {result}"
    
    def test_classify_none_highway(self):
        """None highway tag should return NOISE_FACTOR_DEFAULT."""
        result = classify_highway(None)
        assert result == NOISE_FACTOR_DEFAULT
    
    def test_classify_case_insensitive(self):
        """Highway classification should be case-insensitive."""
        assert classify_highway('PRIMARY') == NOISE_FACTOR_NOISY
        assert classify_highway('Residential') == NOISE_FACTOR_QUIET
        assert classify_highway('FOOTWAY') == NOISE_FACTOR_QUIET


class TestComputeRawQuietCost:
    """Tests for the compute_raw_quiet_cost function.
    
    NOTE: This function is currently a TODO stub and returns None.
    These tests are skipped until WSM A* implementation is complete.
    """
    
    @pytest.mark.skip(reason="TODO: compute_raw_quiet_cost not implemented until WSM A* integration")
    def test_quiet_road_lower_cost(self):
        """Quiet roads (higher factor) should have lower cost than noisy roads."""
        length = 100.0
        noisy_cost = compute_raw_quiet_cost(length, NOISE_FACTOR_NOISY)
        quiet_cost = compute_raw_quiet_cost(length, NOISE_FACTOR_QUIET)
        
        assert quiet_cost < noisy_cost, "Quiet roads should have lower cost"
        assert noisy_cost == 100.0  # 100 / 1.0
        assert quiet_cost == 50.0   # 100 / 2.0
    
    @pytest.mark.skip(reason="TODO: compute_raw_quiet_cost not implemented until WSM A* integration")
    def test_zero_length(self):
        """Zero-length edges should return zero cost."""
        assert compute_raw_quiet_cost(0.0, NOISE_FACTOR_NOISY) == 0.0
        assert compute_raw_quiet_cost(0.0, NOISE_FACTOR_QUIET) == 0.0
    
    @pytest.mark.skip(reason="TODO: compute_raw_quiet_cost not implemented until WSM A* integration")
    def test_negative_noise_factor_uses_default(self):
        """Invalid (zero or negative) noise factors should use default."""
        result = compute_raw_quiet_cost(100.0, 0)
        expected = 100.0 / NOISE_FACTOR_DEFAULT
        assert result == expected
    
    @pytest.mark.skip(reason="TODO: compute_raw_quiet_cost not implemented until WSM A* integration")
    def test_formula_correctness(self):
        """Verify the formula: raw_quiet_cost = length / noise_factor."""
        assert compute_raw_quiet_cost(150.0, 1.5) == 100.0
        assert compute_raw_quiet_cost(200.0, 2.0) == 100.0


class TestProcessGraphQuietness:
    """Tests for the process_graph_quietness function."""
    
    @pytest.fixture
    def mock_graph(self):
        """Creates a mock NetworkX MultiDiGraph with realistic edge data."""
        G = nx.MultiDiGraph()
        
        # Add nodes
        G.add_node(1, x=-2.58, y=51.45)
        G.add_node(2, x=-2.59, y=51.46)
        G.add_node(3, x=-2.60, y=51.47)
        G.add_node(4, x=-2.61, y=51.48)
        
        # Add edges with different highway types
        G.add_edge(1, 2, 0, highway='primary', length=100.0, name='Main Road')
        G.add_edge(2, 3, 0, highway='residential', length=80.0, name='Quiet Street')
        G.add_edge(3, 4, 0, highway='footway', length=50.0, name='Footpath')
        G.add_edge(1, 4, 0, highway='tertiary', length=200.0, name='Unknown Road')
        
        return G
    
    def test_process_assigns_noise_factor(self, mock_graph):
        """All edges should have noise_factor attribute after processing."""
        processed = process_graph_quietness(mock_graph)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            assert 'noise_factor' in data, f"Edge ({u}, {v}, {k}) missing noise_factor"
    
    def test_process_does_not_assign_raw_quiet_cost_yet(self, mock_graph):
        """raw_quiet_cost should NOT be assigned until WSM A* is implemented."""
        processed = process_graph_quietness(mock_graph)
        
        for u, v, k, data in processed.edges(keys=True, data=True):
            assert 'raw_quiet_cost' not in data, f"Edge ({u}, {v}, {k}) should not have raw_quiet_cost yet"
    
    def test_process_correct_classification(self, mock_graph):
        """Edges should be classified correctly based on highway tag."""
        processed = process_graph_quietness(mock_graph)
        
        # Primary road -> noisy
        assert processed[1][2][0]['noise_factor'] == NOISE_FACTOR_NOISY
        
        # Residential -> quiet
        assert processed[2][3][0]['noise_factor'] == NOISE_FACTOR_QUIET
        
        # Footway -> quiet
        assert processed[3][4][0]['noise_factor'] == NOISE_FACTOR_QUIET
        
        # Tertiary -> default (neutral)
        assert processed[1][4][0]['noise_factor'] == NOISE_FACTOR_DEFAULT
    
    def test_process_handles_list_highway_tag(self):
        """Should handle edges where highway tag is a list (pyrosm quirk)."""
        G = nx.MultiDiGraph()
        G.add_node(1)
        G.add_node(2)
        G.add_edge(1, 2, 0, highway=['residential', 'service'], length=100.0)
        
        processed = process_graph_quietness(G)
        
        # Should use first element of list
        assert processed[1][2][0]['noise_factor'] == NOISE_FACTOR_QUIET
    
    def test_process_handles_missing_highway(self):
        """Should handle edges with missing highway tag gracefully."""
        G = nx.MultiDiGraph()
        G.add_node(1)
        G.add_node(2)
        G.add_edge(1, 2, 0, length=100.0)  # No highway tag
        
        processed = process_graph_quietness(G)
        
        assert processed[1][2][0]['noise_factor'] == NOISE_FACTOR_DEFAULT
    
    def test_process_returns_same_graph_object(self, mock_graph):
        """Should modify graph in-place and return the same object."""
        processed = process_graph_quietness(mock_graph)
        assert processed is mock_graph
    
    def test_process_handles_none_graph(self):
        """Should handle None input gracefully."""
        result = process_graph_quietness(None)
        assert result is None
