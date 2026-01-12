"""
Test suite for the Normalisation Processor module.

Tests min-max normalisation of scenic cost attributes in both STATIC and DYNAMIC modes.
"""

import pytest
import networkx as nx
from app.services.processors.normalisation import (
    find_attribute_range,
    normalise_value,
    normalise_attribute,
    normalise_graph_costs,
    ATTRIBUTE_MAPPING,
    DEFAULT_NORMALISED_VALUE,
)


@pytest.fixture
def sample_graph():
    """Creates a sample graph with raw cost attributes."""
    G = nx.MultiDiGraph()
    
    G.add_node(1, x=-2.58, y=51.45)
    G.add_node(2, x=-2.59, y=51.46)
    G.add_node(3, x=-2.60, y=51.47)
    
    # Edge 1-2: Very green, near water, quiet, flat
    G.add_edge(1, 2, 0, 
        length=100.0,
        raw_green_cost=0.1,
        raw_water_cost=0.2,
        raw_social_cost=0.3,
        noise_factor=2.0,
        slope_time_cost=1.0
    )
    
    # Edge 2-3: Not green, no water, noisy, steep uphill
    G.add_edge(2, 3, 0,
        length=200.0,
        raw_green_cost=0.9,
        raw_water_cost=0.8,
        raw_social_cost=0.7,
        noise_factor=1.0,
        slope_time_cost=2.5
    )
    
    # Edge 1-3: Medium values
    G.add_edge(1, 3, 0,
        length=150.0,
        raw_green_cost=0.5,
        raw_water_cost=0.5,
        raw_social_cost=0.5,
        noise_factor=1.5,
        slope_time_cost=1.5
    )
    
    return G


class TestFindAttributeRange:
    """Tests for the find_attribute_range function."""
    
    def test_finds_correct_range(self, sample_graph):
        """Should find min and max values across all edges."""
        min_val, max_val = find_attribute_range(sample_graph, 'raw_green_cost')
        
        assert min_val == 0.1
        assert max_val == 0.9
    
    def test_missing_attribute_returns_none(self, sample_graph):
        """Should return (None, None) for missing attribute."""
        min_val, max_val = find_attribute_range(sample_graph, 'nonexistent_attr')
        
        assert min_val is None
        assert max_val is None
    
    def test_noise_factor_range(self, sample_graph):
        """Should correctly find noise_factor range."""
        min_val, max_val = find_attribute_range(sample_graph, 'noise_factor')
        
        assert min_val == 1.0
        assert max_val == 2.0


class TestNormaliseValue:
    """Tests for the normalise_value function."""
    
    def test_normalises_to_zero_one_range(self):
        """Value should be scaled to 0-1 range."""
        result = normalise_value(5.0, min_val=0.0, max_val=10.0)
        assert result == 0.5
    
    def test_min_value_returns_zero(self):
        """Minimum value should return 0.0."""
        result = normalise_value(0.0, min_val=0.0, max_val=10.0)
        assert result == 0.0
    
    def test_max_value_returns_one(self):
        """Maximum value should return 1.0."""
        result = normalise_value(10.0, min_val=0.0, max_val=10.0)
        assert result == 1.0
    
    def test_inverted_normalisation(self):
        """Inverted normalisation should reverse the scale."""
        # High value should become low when inverted
        result = normalise_value(10.0, min_val=0.0, max_val=10.0, invert=True)
        assert result == 0.0
        
        # Low value should become high when inverted
        result = normalise_value(0.0, min_val=0.0, max_val=10.0, invert=True)
        assert result == 1.0
    
    def test_identical_min_max_returns_zero(self):
        """When min equals max, should return 0.0 to avoid division by zero."""
        result = normalise_value(5.0, min_val=5.0, max_val=5.0)
        assert result == 0.0
    
    def test_clamps_to_valid_range(self):
        """Values outside range should be clamped to 0-1."""
        # Should clamp to 1.0
        result = normalise_value(15.0, min_val=0.0, max_val=10.0)
        assert result == 1.0
        
        # Should clamp to 0.0
        result = normalise_value(-5.0, min_val=0.0, max_val=10.0)
        assert result == 0.0


class TestNormaliseGraphCostsStatic:
    """Tests for normalise_graph_costs in STATIC mode."""
    
    def test_static_mode_copies_green_values(self, sample_graph):
        """In static mode, pre-normalised values should be copied."""
        result = normalise_graph_costs(sample_graph, mode='STATIC')
        
        # Green values should match raw values (already 0-1)
        assert result[1][2][0]['norm_green'] == pytest.approx(0.1, abs=0.01)
        assert result[2][3][0]['norm_green'] == pytest.approx(0.9, abs=0.01)
    
    def test_static_mode_normalises_slope(self, sample_graph):
        """Slope should be normalised even in static mode."""
        result = normalise_graph_costs(sample_graph, mode='STATIC')
        
        # Slope ranges from 1.0 to 2.5, should be normalised
        # 1.0 -> 0.0, 2.5 -> 1.0
        assert result[1][2][0]['norm_slope'] == pytest.approx(0.0, abs=0.01)
        assert result[2][3][0]['norm_slope'] == pytest.approx(1.0, abs=0.01)
    
    def test_static_mode_inverts_noise_factor(self, sample_graph):
        """Noise factor should be inverted (higher = quieter = lower cost)."""
        result = normalise_graph_costs(sample_graph, mode='STATIC')
        
        # noise_factor 2.0 (quiet) -> norm_quiet low
        # noise_factor 1.0 (noisy) -> norm_quiet high
        assert result[1][2][0]['norm_quiet'] < result[2][3][0]['norm_quiet']


class TestNormaliseGraphCostsDynamic:
    """Tests for normalise_graph_costs in DYNAMIC mode."""
    
    def test_dynamic_mode_rescales_all_attributes(self, sample_graph):
        """In dynamic mode, all attributes should be rescaled."""
        result = normalise_graph_costs(sample_graph, mode='DYNAMIC')
        
        # Best edge for green (0.1) should become 0.0
        assert result[1][2][0]['norm_green'] == pytest.approx(0.0, abs=0.01)
        # Worst edge for green (0.9) should become 1.0
        assert result[2][3][0]['norm_green'] == pytest.approx(1.0, abs=0.01)
    
    def test_dynamic_mode_all_values_in_range(self, sample_graph):
        """All normalised values should be in 0-1 range."""
        result = normalise_graph_costs(sample_graph, mode='DYNAMIC')
        
        for u, v, key, data in result.edges(keys=True, data=True):
            assert 0.0 <= data['norm_green'] <= 1.0
            assert 0.0 <= data['norm_water'] <= 1.0
            assert 0.0 <= data['norm_social'] <= 1.0
            assert 0.0 <= data['norm_quiet'] <= 1.0
            assert 0.0 <= data['norm_slope'] <= 1.0


class TestEdgeCases:
    """Tests for edge cases in normalisation."""
    
    def test_handles_missing_attributes(self):
        """Should handle missing attributes gracefully."""
        G = nx.MultiDiGraph()
        G.add_node(1, x=0, y=0)
        G.add_node(2, x=1, y=1)
        G.add_edge(1, 2, 0, length=100.0)  # No cost attributes
        
        result = normalise_graph_costs(G, mode='STATIC')
        
        # Should use default values
        assert result[1][2][0]['norm_green'] == DEFAULT_NORMALISED_VALUE
    
    def test_handles_none_graph(self):
        """Should return None if graph is None."""
        result = normalise_graph_costs(None, mode='STATIC')
        assert result is None
    
    def test_all_same_values(self):
        """Should handle case where all values are identical."""
        G = nx.MultiDiGraph()
        G.add_node(1, x=0, y=0)
        G.add_node(2, x=1, y=1)
        G.add_node(3, x=2, y=2)
        
        G.add_edge(1, 2, 0, length=100.0, raw_green_cost=0.5)
        G.add_edge(2, 3, 0, length=100.0, raw_green_cost=0.5)
        
        result = normalise_graph_costs(G, mode='DYNAMIC')
        
        # All values same, should all be 0.0
        assert result[1][2][0]['norm_green'] == 0.0
        assert result[2][3][0]['norm_green'] == 0.0
