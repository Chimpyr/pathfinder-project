"""
Test suite for the WSM Cost Calculator module.

Tests the Weighted Sum Model cost calculation, weight validation,
and UI weight normalisation functionality.
"""

import pytest
from app.services.routing.cost_calculator import (
    compute_wsm_cost,
    validate_weights,
    normalise_ui_weights,
    find_length_range,
    normalise_length,
)
import networkx as nx


class TestValidateWeights:
    """Tests for the validate_weights function."""
    
    def test_accepts_valid_weights(self):
        """Should accept a valid weights dictionary."""
        weights = {
            'distance': 0.5,
            'greenness': 0.15,
            'water': 0.1,
            'quietness': 0.1,
            'social': 0.1,
            'slope': 0.05,
        }
        result = validate_weights(weights)
        
        assert result == weights
    
    def test_fills_missing_keys_with_zero(self):
        """Should fill missing keys with 0.0."""
        weights = {'distance': 1.0}
        result = validate_weights(weights)
        
        assert result['distance'] == 1.0
        assert result['greenness'] == 0.0
        assert result['water'] == 0.0
    
    def test_rejects_negative_weights(self):
        """Should raise ValueError for negative weights."""
        weights = {'distance': 0.5, 'greenness': -0.1}
        
        with pytest.raises(ValueError, match="cannot be negative"):
            validate_weights(weights)
    
    def test_converts_to_float(self):
        """Should convert integer weights to float."""
        weights = {'distance': 1, 'greenness': 0}
        result = validate_weights(weights)
        
        assert isinstance(result['distance'], float)
        assert isinstance(result['greenness'], float)


class TestComputeWSMCost:
    """Tests for the compute_wsm_cost function."""
    
    @pytest.fixture
    def equal_weights(self):
        """Returns weights with equal distribution."""
        return {
            'distance': 0.2,
            'greenness': 0.2,
            'water': 0.2,
            'quietness': 0.2,
            'social': 0.1,
            'slope': 0.1,
        }
    
    @pytest.fixture
    def distance_only_weights(self):
        """Returns weights with distance only."""
        return {
            'distance': 1.0,
            'greenness': 0.0,
            'water': 0.0,
            'quietness': 0.0,
            'social': 0.0,
            'slope': 0.0,
        }
    
    def test_distance_only_mode(self, distance_only_weights):
        """With distance=1.0 and others=0.0, cost should equal norm_length."""
        cost = compute_wsm_cost(
            norm_length=0.5,
            norm_green=0.8,  # Should be ignored
            norm_water=0.8,
            norm_social=0.8,
            norm_quiet=0.2,
            norm_slope=0.2,
            weights=distance_only_weights
        )
        
        assert cost == pytest.approx(0.5, abs=0.001)
    
    def test_all_features_use_direct_weighting(self, equal_weights):
        """All normalised features are costs: low value = good = lower cost."""
        # Low cost values (0.0) = good = less cost
        cost_low_values = compute_wsm_cost(
            norm_length=0.5,
            norm_green=0.0,  # Very green (good)
            norm_water=0.0,  # Near water (good)
            norm_social=0.0, # Near POIs (good)
            norm_quiet=0.5,
            norm_slope=0.5,
            weights=equal_weights
        )
        
        # High cost values (1.0) = bad = more cost
        cost_high_values = compute_wsm_cost(
            norm_length=0.5,
            norm_green=1.0,  # No green (bad)
            norm_water=1.0,  # No water (bad)
            norm_social=1.0, # No POIs (bad)
            norm_quiet=0.5,
            norm_slope=0.5,
            weights=equal_weights
        )
        
        assert cost_low_values < cost_high_values
    
    def test_cost_features_direct(self, equal_weights):
        """High quietness/slope costs should increase total cost (not inverted)."""
        # Low cost values (0.0) = good = less cost
        cost_low_cost_features = compute_wsm_cost(
            norm_length=0.5,
            norm_green=0.5,
            norm_water=0.5,
            norm_social=0.5,
            norm_quiet=0.0,  # Quiet
            norm_slope=0.0,  # Flat
            weights=equal_weights
        )
        
        # High cost values (1.0) = bad = more cost
        cost_high_cost_features = compute_wsm_cost(
            norm_length=0.5,
            norm_green=0.5,
            norm_water=0.5,
            norm_social=0.5,
            norm_quiet=1.0,  # Noisy
            norm_slope=1.0,  # Steep
            weights=equal_weights
        )
        
        assert cost_low_cost_features < cost_high_cost_features
    
    def test_zero_weights_excludes_feature(self):
        """Features with zero weight should not affect cost."""
        weights = {
            'distance': 1.0,
            'greenness': 0.0,
            'water': 0.0,
            'quietness': 0.0,
            'social': 0.0,
            'slope': 0.0,
        }
        
        # Changing greenness should have no effect
        cost_green = compute_wsm_cost(
            norm_length=0.5,
            norm_green=1.0,
            norm_water=0.0,
            norm_social=0.0,
            norm_quiet=0.0,
            norm_slope=0.0,
            weights=weights
        )
        
        cost_no_green = compute_wsm_cost(
            norm_length=0.5,
            norm_green=0.0,
            norm_water=0.0,
            norm_social=0.0,
            norm_quiet=0.0,
            norm_slope=0.0,
            weights=weights
        )
        
        assert cost_green == cost_no_green
    
    def test_produces_non_negative_cost(self, equal_weights):
        """Cost should always be non-negative."""
        cost = compute_wsm_cost(
            norm_length=0.0,
            norm_green=1.0,
            norm_water=1.0,
            norm_social=1.0,
            norm_quiet=0.0,
            norm_slope=0.0,
            weights=equal_weights
        )
        
        assert cost >= 0


class TestNormaliseUIWeights:
    """Tests for the normalise_ui_weights function."""
    
    def test_normalises_to_sum_one(self):
        """Normalised weights should sum to 1.0."""
        ui_weights = {
            'distance': 50,
            'greenness': 50,
            'water': 50,
            'quietness': 50,
            'social': 50,
            'slope': 50,
        }
        
        result = normalise_ui_weights(ui_weights)
        total = sum(result.values())
        
        assert total == pytest.approx(1.0, abs=0.001)
    
    def test_handles_unequal_values(self):
        """Should correctly normalise unequal slider values."""
        ui_weights = {
            'distance': 100,
            'greenness': 0,
            'water': 0,
            'quietness': 0,
            'social': 0,
            'slope': 0,
        }
        
        result = normalise_ui_weights(ui_weights)
        
        # Only distance should have weight
        assert result['distance'] > 0
        # Others should be zero
        assert result['greenness'] == 0.0
    
    def test_handles_all_zero_sliders(self):
        """Should default to distance-only when all sliders are zero."""
        ui_weights = {
            'distance': 0,
            'greenness': 0,
            'water': 0,
            'quietness': 0,
            'social': 0,
            'slope': 0,
        }
        
        result = normalise_ui_weights(ui_weights)
        
        assert result['distance'] == 1.0
        assert result['greenness'] == 0.0
    
    def test_fills_missing_keys_with_defaults(self):
        """Should use default values for missing keys."""
        ui_weights = {'distance': 100}
        
        result = normalise_ui_weights(ui_weights)
        
        # Should still have all keys
        assert 'greenness' in result
        assert 'water' in result


class TestFindLengthRange:
    """Tests for the find_length_range function."""
    
    def test_finds_correct_range(self):
        """Should find min and max edge lengths."""
        G = nx.MultiDiGraph()
        G.add_node(1)
        G.add_node(2)
        G.add_node(3)
        G.add_edge(1, 2, 0, length=50.0)
        G.add_edge(2, 3, 0, length=200.0)
        G.add_edge(1, 3, 0, length=100.0)
        
        min_len, max_len = find_length_range(G)
        
        assert min_len == 50.0
        assert max_len == 200.0
    
    def test_empty_graph_returns_defaults(self):
        """Should return (0.0, 1.0) for empty graph."""
        G = nx.MultiDiGraph()
        
        min_len, max_len = find_length_range(G)
        
        assert min_len == 0.0
        assert max_len == 1.0


class TestNormaliseLength:
    """Tests for the normalise_length function."""
    
    def test_normalises_to_zero_one_range(self):
        """Should normalise length to 0-1 range."""
        result = normalise_length(100.0, min_length=50.0, max_length=150.0)
        
        assert result == 0.5
    
    def test_min_returns_zero(self):
        """Minimum length should return 0.0."""
        result = normalise_length(50.0, min_length=50.0, max_length=150.0)
        
        assert result == 0.0
    
    def test_max_returns_one(self):
        """Maximum length should return 1.0."""
        result = normalise_length(150.0, min_length=50.0, max_length=150.0)
        
        assert result == 1.0
    
    def test_identical_min_max_returns_zero(self):
        """When min equals max, should return 0.0."""
        result = normalise_length(100.0, min_length=100.0, max_length=100.0)
        
        assert result == 0.0
