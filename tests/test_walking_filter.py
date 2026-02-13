"""
Tests for the custom walking network filter.

Tests cover:
    - Hard exclusions (motorway, foot=no, service=private, etc.)
    - Conditional inclusion (highway=cycleway with/without foot access)
    - Designation-based access overrides
    - access=private overridden by foot=yes
    - Edge cases (empty DF, missing columns)
"""

import pandas as pd
import geopandas as gpd
import pytest
from shapely.geometry import LineString

from app.services.core.walking_filter import (
    apply_walking_filter,
    EXCLUDED_HIGHWAY_TAGS,
    EXCLUDED_FOOT_TAGS,
    CONDITIONAL_HIGHWAY_TAGS,
    PEDESTRIAN_FOOT_VALUES,
    PEDESTRIAN_DESIGNATION_VALUES,
    EXTRA_WALKING_ATTRIBUTES,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_edges(**columns) -> gpd.GeoDataFrame:
    """Build a tiny GeoDataFrame with given columns.

    Each keyword arg is a column name mapping to a list of values.
    A ``geometry`` column with dummy linestrings is added automatically.
    """
    n = len(next(iter(columns.values())))
    geom = [LineString([(0, i), (1, i)]) for i in range(n)]
    data = {**columns, "geometry": geom}
    return gpd.GeoDataFrame(data, crs="EPSG:4326")


# ---------------------------------------------------------------------------
# Hard exclusion tests
# ---------------------------------------------------------------------------

class TestHardExclusions:
    """Ways that should always be excluded regardless of other tags."""

    @pytest.mark.parametrize("hw", sorted(EXCLUDED_HIGHWAY_TAGS))
    def test_excluded_highway_tags_removed(self, hw):
        edges = _make_edges(highway=[hw, "footway"])
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["highway"] == "footway"

    def test_foot_no_excluded(self):
        edges = _make_edges(
            highway=["footway", "path"],
            foot=["no", "yes"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["highway"] == "path"

    def test_service_private_excluded(self):
        edges = _make_edges(
            highway=["residential", "service"],
            service=["", "private"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["highway"] == "residential"

    def test_area_yes_excluded(self):
        edges = _make_edges(
            highway=["pedestrian", "residential"],
            area=["yes", "no"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["highway"] == "residential"

    def test_access_private_excluded(self):
        edges = _make_edges(
            highway=["residential", "residential"],
            access=["private", "yes"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["access"] == "yes"

    def test_access_no_excluded(self):
        edges = _make_edges(
            highway=["track", "track"],
            access=["no", "permissive"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["access"] == "permissive"


# ---------------------------------------------------------------------------
# Conditional cycleway tests (the key §2a fix)
# ---------------------------------------------------------------------------

class TestConditionalCycleway:
    """highway=cycleway kept only when foot access is confirmed."""

    def test_cycleway_without_foot_tag_excluded(self):
        """Bare cycleway with no foot tag should be dropped."""
        edges = _make_edges(highway=["cycleway", "footway"])
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["highway"] == "footway"

    @pytest.mark.parametrize("foot_val", sorted(PEDESTRIAN_FOOT_VALUES))
    def test_cycleway_with_foot_access_kept(self, foot_val):
        """Cycleway with an explicit pedestrian foot tag should be kept."""
        edges = _make_edges(
            highway=["cycleway"],
            foot=[foot_val],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["highway"] == "cycleway"

    @pytest.mark.parametrize("desig", sorted(PEDESTRIAN_DESIGNATION_VALUES))
    def test_cycleway_with_designation_kept(self, desig):
        """Cycleway with a UK designation confirming foot access should be kept."""
        edges = _make_edges(
            highway=["cycleway"],
            designation=[desig],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1

    def test_cycleway_foot_no_still_excluded(self):
        """foot=no overrides even cycleway — hard exclusion wins."""
        edges = _make_edges(
            highway=["cycleway"],
            foot=["no"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 0

    def test_stoke_park_shared_use_path(self):
        """Real-world example: shared-use path in Stoke Park, Bristol."""
        edges = _make_edges(
            highway=["cycleway"],
            designation=["public_footpath"],
            foot=["designated"],
            surface=["asphalt"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1, "Stoke Park shared-use path should be kept"


# ---------------------------------------------------------------------------
# Access override tests
# ---------------------------------------------------------------------------

class TestAccessOverride:
    """access=private should be overridden by an explicit foot tag."""

    def test_access_private_with_foot_yes(self):
        edges = _make_edges(
            highway=["path"],
            access=["private"],
            foot=["yes"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1, "foot=yes should override access=private"

    def test_access_private_with_foot_designated(self):
        edges = _make_edges(
            highway=["footway"],
            access=["private"],
            foot=["designated"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1

    def test_access_private_without_foot_excluded(self):
        edges = _make_edges(
            highway=["track"],
            access=["private"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Edge-case tests
# ---------------------------------------------------------------------------

class TestEdgeCases:
    """Empty inputs, missing columns, mixed cases."""

    def test_empty_dataframe(self):
        edges = _make_edges(highway=[])
        result = apply_walking_filter(edges)
        assert len(result) == 0

    def test_none_input(self):
        result = apply_walking_filter(None)
        assert result is None

    def test_missing_highway_column(self):
        edges = _make_edges(surface=["asphalt"])
        result = apply_walking_filter(edges)
        assert len(result) == 0, "No highway column → no valid road data"

    def test_case_insensitive_highway(self):
        edges = _make_edges(highway=["Footway", "MOTORWAY"])
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["highway"] == "Footway"

    def test_case_insensitive_foot(self):
        edges = _make_edges(
            highway=["cycleway"],
            foot=["Designated"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1

    def test_nan_values_treated_as_absent(self):
        """NaN foot tag on cycleway → no foot confirmation → excluded."""
        import numpy as np

        edges = _make_edges(
            highway=["cycleway", "footway"],
            foot=[np.nan, np.nan],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["highway"] == "footway"

    def test_regular_highways_pass_through(self):
        """Normal walking highway types should all pass through."""
        normal_types = [
            "footway", "path", "pedestrian", "residential",
            "living_street", "track", "bridleway", "steps",
            "service", "unclassified", "tertiary", "secondary", "primary",
            "trunk",
        ]
        edges = _make_edges(highway=normal_types)
        result = apply_walking_filter(edges)
        assert len(result) == len(normal_types)


# ---------------------------------------------------------------------------
# Constants / contract tests
# ---------------------------------------------------------------------------

class TestConstants:
    """Verify the filter constants are consistent."""

    def test_designation_in_extra_attributes(self):
        assert "designation" in EXTRA_WALKING_ATTRIBUTES

    def test_cycleway_is_conditional(self):
        assert "cycleway" in CONDITIONAL_HIGHWAY_TAGS

    def test_no_overlap_excluded_conditional(self):
        """Excluded and conditional sets must not overlap."""
        assert EXCLUDED_HIGHWAY_TAGS.isdisjoint(CONDITIONAL_HIGHWAY_TAGS)
