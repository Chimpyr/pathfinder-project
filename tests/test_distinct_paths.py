"""
Test suite for the Distinct Paths Runner.

Tests the multi-route strategy that runs A* three times per request,
returning Baseline, Extremist, and Balanced route alternatives.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestBaselineWeights:
    """Tests for baseline weight generation."""
    
    def test_baseline_weights_distance_only(self):
        """Baseline weights should be distance=1.0, all others=0."""
        from app.services.routing.distinct_paths_runner import generate_baseline_weights
        
        weights = generate_baseline_weights()
        
        assert weights['distance'] == 1.0
        assert weights['greenness'] == 0.0
        assert weights['water'] == 0.0
        assert weights['quietness'] == 0.0
        assert weights['social'] == 0.0
        assert weights['slope'] == 0.0
    
    def test_baseline_weights_sum(self):
        """Baseline weights should sum to 1.0."""
        from app.services.routing.distinct_paths_runner import generate_baseline_weights
        
        weights = generate_baseline_weights()
        total = sum(weights.values())
        
        assert total == 1.0


class TestExtremistWeights:
    """Tests for extremist weight calculation."""
    
    def test_finds_single_max_feature(self):
        """Should identify the feature with highest weight."""
        from app.services.routing.distinct_paths_runner import find_dominant_feature
        
        user_weights = {
            'distance': 0.3,
            'greenness': 0.4,  # Max
            'water': 0.1,
            'quietness': 0.1,
            'social': 0.05,
            'slope': 0.05,
        }
        
        dominant = find_dominant_feature(user_weights)
        
        assert dominant == 'greenness'
    
    def test_tie_breaking_uses_priority_order(self):
        """When multiple features tie, should use priority order."""
        from app.services.routing.distinct_paths_runner import find_dominant_feature, FEATURE_PRIORITY
        
        # All scenic features equal
        user_weights = {
            'distance': 0.5,
            'greenness': 0.1,
            'water': 0.1,
            'quietness': 0.1,
            'social': 0.1,
            'slope': 0.1,
        }
        
        dominant = find_dominant_feature(user_weights)
        
        # Should pick first in priority order
        assert dominant == FEATURE_PRIORITY[0]
    
    def test_extremist_weights_structure(self):
        """Extremist weights should set dominant to 1.0, distance to 0.1, others to 0."""
        from app.services.routing.distinct_paths_runner import generate_extremist_weights
        
        user_weights = {
            'distance': 0.3,
            'greenness': 0.1,
            'water': 0.4,  # Max
            'quietness': 0.1,
            'social': 0.05,
            'slope': 0.05,
        }
        
        weights, dominant = generate_extremist_weights(user_weights)
        
        assert dominant == 'water'
        assert weights['water'] == 1.0
        assert weights['distance'] == 0.1
        assert weights['greenness'] == 0.0
        assert weights['quietness'] == 0.0
        assert weights['social'] == 0.0
        assert weights['slope'] == 0.0
    
    def test_handles_zero_scenic_weights(self):
        """Should default to greenness when all scenic weights are zero."""
        from app.services.routing.distinct_paths_runner import find_dominant_feature
        
        user_weights = {
            'distance': 1.0,
            'greenness': 0.0,
            'water': 0.0,
            'quietness': 0.0,
            'social': 0.0,
            'slope': 0.0,
        }
        
        dominant = find_dominant_feature(user_weights)
        
        assert dominant == 'greenness'


class TestExtremistColour:
    """Tests for extremist route colour mapping."""
    
    def test_greenness_colour(self):
        """Greenness should map to green colour."""
        from app.services.routing.distinct_paths_runner import get_extremist_colour, ROUTE_COLOURS
        
        colour = get_extremist_colour('greenness')
        
        assert colour == ROUTE_COLOURS['greenness']
        assert colour == '#22C55E'
    
    def test_water_colour(self):
        """Water should map to cyan colour."""
        from app.services.routing.distinct_paths_runner import get_extremist_colour, ROUTE_COLOURS
        
        colour = get_extremist_colour('water')
        
        assert colour == ROUTE_COLOURS['water']
        assert colour == '#06B6D4'
    
    def test_unknown_feature_fallback(self):
        """Unknown feature should fall back to balanced colour."""
        from app.services.routing.distinct_paths_runner import get_extremist_colour, ROUTE_COLOURS
        
        colour = get_extremist_colour('unknown_feature')
        
        assert colour == ROUTE_COLOURS['balanced']


class TestDistinctPathsRunner:
    """Integration tests for the full distinct paths runner."""
    
    @pytest.fixture
    def mock_route_finder(self):
        """Create a mock RouteFinder that returns predictable routes."""
        finder = MagicMock()
        
        # Different routes for different weight configurations
        def mock_find_route(start, end, use_wsm=False, weights=None, combine_nature=False,
                            prefer_lit=False, heavily_avoid_unlit=False):
            if weights and weights.get('distance', 0) == 1.0:
                # Baseline: shortest distance
                return ([1, 3], start, end, 100.0, 72.0)
            elif weights and any(weights.get(f, 0) == 1.0 for f in ['greenness', 'water', 'quietness', 'social', 'slope']):
                # Extremist (any scenic feature max): longer scenic route
                return ([1, 2, 3], start, end, 300.0, 216.0)
            else:
                # Balanced: intermediate route
                return ([1, 4, 3], start, end, 200.0, 144.0)
        
        finder.find_route.side_effect = mock_find_route
        return finder
    
    def test_runs_three_times(self, mock_route_finder):
        """Should call find_route exactly three times."""
        from app.services.routing.distinct_paths_runner import find_distinct_paths
        
        user_weights = {
            'distance': 0.4,
            'greenness': 0.3,
            'water': 0.1,
            'quietness': 0.1,
            'social': 0.05,
            'slope': 0.05,
        }
        
        find_distinct_paths(
            mock_route_finder,
            (51.45, -2.58),
            (51.46, -2.57),
            user_weights,
            verbose=False
        )
        
        assert mock_route_finder.find_route.call_count == 3
    
    def test_returns_three_routes(self, mock_route_finder):
        """Should return baseline, extremist, and balanced routes."""
        from app.services.routing.distinct_paths_runner import find_distinct_paths
        
        user_weights = {
            'distance': 0.4,
            'greenness': 0.3,
            'water': 0.1,
            'quietness': 0.1,
            'social': 0.05,
            'slope': 0.05,
        }
        
        result = find_distinct_paths(
            mock_route_finder,
            (51.45, -2.58),
            (51.46, -2.57),
            user_weights,
            verbose=False
        )
        
        assert 'baseline' in result
        assert 'extremist' in result
        assert 'balanced' in result
    
    def test_baseline_has_correct_colour(self, mock_route_finder):
        """Baseline route should have grey colour."""
        from app.services.routing.distinct_paths_runner import find_distinct_paths, ROUTE_COLOURS
        
        user_weights = {'distance': 0.5, 'greenness': 0.5}
        
        result = find_distinct_paths(
            mock_route_finder,
            (51.45, -2.58),
            (51.46, -2.57),
            user_weights,
            verbose=False
        )
        
        assert result['baseline']['colour'] == ROUTE_COLOURS['baseline']
    
    def test_extremist_identifies_dominant_feature(self, mock_route_finder):
        """Extremist route should include dominant feature name."""
        from app.services.routing.distinct_paths_runner import find_distinct_paths
        
        user_weights = {
            'distance': 0.4,
            'greenness': 0.4,  # Max scenic
            'water': 0.1,
            'quietness': 0.05,
            'social': 0.025,
            'slope': 0.025,
        }
        
        result = find_distinct_paths(
            mock_route_finder,
            (51.45, -2.58),
            (51.46, -2.57),
            user_weights,
            verbose=False
        )
        
        assert result['extremist']['dominant_feature'] == 'greenness'


class TestFeaturePriority:
    """Tests for the feature priority ordering."""
    
    def test_priority_order_defined(self):
        """Feature priority order should be defined."""
        from app.services.routing.distinct_paths_runner import FEATURE_PRIORITY
        
        assert len(FEATURE_PRIORITY) == 5
        assert 'greenness' in FEATURE_PRIORITY
        assert 'water' in FEATURE_PRIORITY
        assert 'quietness' in FEATURE_PRIORITY
        assert 'social' in FEATURE_PRIORITY
        assert 'slope' in FEATURE_PRIORITY
    
    def test_greenness_has_highest_priority(self):
        """Greenness should be first in priority order."""
        from app.services.routing.distinct_paths_runner import FEATURE_PRIORITY
        
        assert FEATURE_PRIORITY[0] == 'greenness'


class TestBaselinePurity:
    """Regression tests: baseline must always be pure shortest path."""

    def test_baseline_never_uses_lit_preference(self):
        """Baseline call must not pass prefer_lit=True even when user enables it."""
        from app.services.routing.distinct_paths_runner import find_distinct_paths

        finder = MagicMock()
        finder.find_route.return_value = ([1, 3], (0, 0), (1, 1), 100.0, 72.0)

        user_weights = {'distance': 0.5, 'greenness': 0.3, 'water': 0.2}

        find_distinct_paths(
            finder, (51.45, -2.58), (51.46, -2.57),
            user_weights, verbose=False,
            prefer_lit=True, heavily_avoid_unlit=True,
        )

        # First call is baseline — must have prefer_lit=False, heavily_avoid_unlit=False
        baseline_call = finder.find_route.call_args_list[0]
        assert baseline_call.kwargs.get('prefer_lit') is False, \
            "Baseline (Direct) route must not use prefer_lit"
        assert baseline_call.kwargs.get('heavily_avoid_unlit') is False, \
            "Baseline (Direct) route must not use heavily_avoid_unlit"

        # Balanced (3rd call) should still use user's lit preferences
        balanced_call = finder.find_route.call_args_list[2]
        assert balanced_call.kwargs.get('prefer_lit') is True
        assert balanced_call.kwargs.get('heavily_avoid_unlit') is True

