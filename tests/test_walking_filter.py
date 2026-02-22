"""
Tests for the custom walking network filter.

Tests cover:
    - Hard exclusions (motorway, foot=no, service=private, etc.)
    - Conditional inclusion (highway=cycleway with/without foot access)
    - Designation-based access overrides
    - access=private overridden by foot=yes
    - Expanded restricted-access pruning (military, agricultural, etc.)
    - Node-level barrier/gate resolution
    - Explicit-allow override (foot=yes overrides access=military)
    - Private-service filtering (driveway, parking_aisle)
    - Edge cases (empty DF, missing columns)
"""

import numpy as np
import pandas as pd
import geopandas as gpd
import pytest
from shapely.geometry import LineString, Point

from app.services.core.walking_filter import (
    apply_walking_filter,
    _resolve_restricted_nodes,
    EXCLUDED_HIGHWAY_TAGS,
    EXCLUDED_FOOT_TAGS,
    EXCLUDED_ACCESS_TAGS,
    EXCLUDED_SERVICE_TAGS,
    CONDITIONAL_HIGHWAY_TAGS,
    PEDESTRIAN_FOOT_VALUES,
    PEDESTRIAN_DESIGNATION_VALUES,
    EXTRA_WALKING_ATTRIBUTES,
    RESTRICTED_ACCESS,
    RESTRICTED_FOOT,
    EXPLICIT_ALLOW,
    RESTRICTED_SERVICE,
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


def _make_nodes(**columns) -> gpd.GeoDataFrame:
    """Build a tiny nodes GeoDataFrame with given columns.

    Each keyword arg is a column name mapping to a list of values.
    A ``geometry`` column with dummy points is added automatically.
    If ``id`` is not provided, it defaults to [100, 101, ...].
    """
    n = len(next(iter(columns.values())))
    geom = [Point(0, i) for i in range(n)]
    if "id" not in columns:
        columns["id"] = list(range(100, 100 + n))
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
# Expanded restricted-access tests
# ---------------------------------------------------------------------------

class TestRestrictedAccessExpanded:
    """Edges with broader restricted access tags should be dropped."""

    @pytest.mark.parametrize("access_val", sorted(
        RESTRICTED_ACCESS - {"private", "no"}  # private & no covered above
    ))
    def test_restricted_access_tag_dropped(self, access_val):
        """Each expanded access restriction should cause edge removal."""
        edges = _make_edges(
            highway=["residential", "residential"],
            access=[access_val, "yes"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["access"] == "yes"

    def test_access_military_with_foot_designated_kept(self):
        """foot=designated should override access=military."""
        edges = _make_edges(
            highway=["track"],
            access=["military"],
            foot=["designated"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1, "foot=designated should override access=military"

    def test_access_military_with_foot_public_kept(self):
        """foot=public should override access=military."""
        edges = _make_edges(
            highway=["path"],
            access=["military"],
            foot=["public"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1, "foot=public should override access=military"

    def test_access_customers_without_override_dropped(self):
        """access=customers without a foot override should be dropped."""
        edges = _make_edges(
            highway=["service"],
            access=["customers"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Restricted foot tests
# ---------------------------------------------------------------------------

class TestRestrictedFoot:
    """Edges with expanded foot restriction tags should be dropped."""

    @pytest.mark.parametrize("foot_val", sorted(RESTRICTED_FOOT))
    def test_restricted_foot_tag_dropped(self, foot_val):
        """Each restricted foot tag should cause edge removal."""
        edges = _make_edges(
            highway=["residential", "residential"],
            foot=[foot_val, "yes"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["foot"] == "yes"

    def test_foot_use_sidepath_dropped(self):
        """foot=use_sidepath means 'use the adjacent path instead'."""
        edges = _make_edges(
            highway=["primary"],
            foot=["use_sidepath"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 0


# ---------------------------------------------------------------------------
# Private-service tests
# ---------------------------------------------------------------------------

class TestPrivateService:
    """highway=service + restricted service type should be dropped."""

    @pytest.mark.parametrize("svc", sorted(RESTRICTED_SERVICE))
    def test_restricted_service_dropped(self, svc):
        """highway=service with a restricted sub-type should be removed."""
        edges = _make_edges(
            highway=["service", "footway"],
            service=[svc, ""],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1
        assert result.iloc[0]["highway"] == "footway"

    def test_service_driveway_with_foot_yes_kept(self):
        """service=driveway + foot=yes → explicit allow overrides."""
        edges = _make_edges(
            highway=["service"],
            service=["driveway"],
            foot=["yes"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1, "foot=yes should override service=driveway"

    def test_service_parking_aisle_with_foot_designated_kept(self):
        """service=parking_aisle + foot=designated → explicit allow overrides."""
        edges = _make_edges(
            highway=["service"],
            service=["parking_aisle"],
            foot=["designated"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1

    def test_non_service_highway_with_restricted_service_tag_kept(self):
        """Mask D only applies to highway=service, not other highway types."""
        edges = _make_edges(
            highway=["residential"],
            service=["driveway"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1, "Mask D should only trigger for highway=service"


# ---------------------------------------------------------------------------
# Barrier / gate tests
# ---------------------------------------------------------------------------

class TestBarrierNodes:
    """Node-level barrier resolution for locked gates."""

    def test_locked_gate_drops_connected_edges(self):
        """Edges touching a locked gate node should be removed."""
        nodes = _make_nodes(
            id=[100, 101, 102],
            barrier=["gate", "", ""],
            locked=["yes", "", ""],
        )
        edges = _make_edges(
            highway=["residential", "residential"],
            u=[100, 101],
            v=[101, 102],
        )
        result = apply_walking_filter(edges, nodes=nodes)
        assert len(result) == 1
        assert result.iloc[0]["u"] == 101  # Only the non-gate edge survives

    def test_restricted_access_gate_drops_connected_edges(self):
        """Gate with access=private should block connected edges."""
        nodes = _make_nodes(
            id=[200, 201],
            barrier=["gate", ""],
            access=["private", ""],
        )
        edges = _make_edges(
            highway=["path", "path"],
            u=[200, 201],
            v=[201, 201],
        )
        result = apply_walking_filter(edges, nodes=nodes)
        assert len(result) == 1

    def test_unlocked_gate_passes_through(self):
        """An unlocked, public gate should NOT block edges."""
        nodes = _make_nodes(
            id=[300, 301],
            barrier=["gate", ""],
            locked=["no", ""],
            access=["yes", ""],
        )
        edges = _make_edges(
            highway=["residential", "residential"],
            u=[300, 301],
            v=[301, 301],
        )
        result = apply_walking_filter(edges, nodes=nodes)
        assert len(result) == 2, "Unlocked public gate should not block edges"

    def test_no_nodes_provided_skips_barrier_check(self):
        """When nodes=None, barrier filtering is skipped gracefully."""
        edges = _make_edges(
            highway=["residential", "residential"],
            u=[100, 101],
            v=[101, 102],
        )
        result = apply_walking_filter(edges, nodes=None)
        assert len(result) == 2

    def test_gate_military_access_drops_edge(self):
        """Gate with access=military should block connected edges."""
        nodes = _make_nodes(
            id=[400, 401],
            barrier=["gate", ""],
            access=["military", ""],
        )
        edges = _make_edges(
            highway=["track", "track"],
            u=[400, 401],
            v=[401, 401],
        )
        result = apply_walking_filter(edges, nodes=nodes)
        assert len(result) == 1

    def test_non_gate_barrier_ignored(self):
        """barrier=bollard should NOT cause edge removal (gates only)."""
        nodes = _make_nodes(
            id=[500, 501],
            barrier=["bollard", ""],
            locked=["yes", ""],
        )
        edges = _make_edges(
            highway=["footway", "footway"],
            u=[500, 501],
            v=[501, 501],
        )
        result = apply_walking_filter(edges, nodes=nodes)
        assert len(result) == 2, "Only gates should cause barrier filtering"


# ---------------------------------------------------------------------------
# Explicit-allow override tests
# ---------------------------------------------------------------------------

class TestExplicitAllowOverride:
    """Explicit foot allow tags should rescue edges from access restrictions."""

    @pytest.mark.parametrize("foot_val", sorted(EXPLICIT_ALLOW))
    def test_explicit_allow_overrides_access_restricted(self, foot_val):
        """Each EXPLICIT_ALLOW value should override access=restricted."""
        edges = _make_edges(
            highway=["path"],
            access=["restricted"],
            foot=[foot_val],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1

    def test_private_estate_with_public_footpath(self):
        """Real-world: private estate road with a designated public footpath."""
        edges = _make_edges(
            highway=["track"],
            access=["private"],
            foot=["designated"],
            designation=["public_footpath"],
        )
        result = apply_walking_filter(edges)
        assert len(result) == 1, "Public footpath through private estate should be kept"


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

    def test_barrier_in_extra_attributes(self):
        assert "barrier" in EXTRA_WALKING_ATTRIBUTES

    def test_locked_in_extra_attributes(self):
        assert "locked" in EXTRA_WALKING_ATTRIBUTES

    def test_service_in_extra_attributes(self):
        assert "service" in EXTRA_WALKING_ATTRIBUTES

    def test_cycleway_is_conditional(self):
        assert "cycleway" in CONDITIONAL_HIGHWAY_TAGS

    def test_no_overlap_excluded_conditional(self):
        """Excluded and conditional sets must not overlap."""
        assert EXCLUDED_HIGHWAY_TAGS.isdisjoint(CONDITIONAL_HIGHWAY_TAGS)

    def test_legacy_aliases_match(self):
        """Legacy alias sets should reference the new canonical sets."""
        assert EXCLUDED_FOOT_TAGS is RESTRICTED_FOOT
        assert EXCLUDED_ACCESS_TAGS is RESTRICTED_ACCESS
        assert EXCLUDED_SERVICE_TAGS is RESTRICTED_SERVICE

    def test_explicit_allow_contains_pedestrian_values(self):
        """EXPLICIT_ALLOW should contain the core pedestrian allow values."""
        assert {"yes", "designated", "permissive"}.issubset(EXPLICIT_ALLOW)
