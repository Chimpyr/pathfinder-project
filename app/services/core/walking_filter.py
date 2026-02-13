"""
Custom walking network filter for ScenicPathFinder.

Replaces pyrosm's built-in ``network_type="walking"`` filter which
hard-excludes ``highway=cycleway`` regardless of pedestrian access tags.

This filter keeps cycleways and other ways that are legally or explicitly
accessible to pedestrians, while still excluding genuinely unwalkable
infrastructure (motorways, construction, etc.).

Design goals
------------
1. **Correct** — include shared-use cycleways tagged ``foot=yes``
   or ``foot=designated``.
2. **Expandable** — adding a new access rule or highway type is a
   one-line change to a clearly-named constant.
3. **Documented** — every exclusion and inclusion rule has a comment
   explaining *why*.

See also:
    ``docs/features/custom_walking_filter.md`` for the user-facing
    documentation.
    ``docs/decisions/ADR-010-improvements-to-budget-astar-looper.md §2a``
    for the investigation that motivated this module.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import pandas as pd

if TYPE_CHECKING:
    import geopandas as gpd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants — edit THESE to change what the filter accepts / rejects
# ---------------------------------------------------------------------------

# Highway values that are NEVER walkable, regardless of other tags.
# fmt: off
EXCLUDED_HIGHWAY_TAGS: set[str] = {
    "motorway", "motorway_link",  # illegal/impossible for pedestrians
    "raceway",                     # motor-sport circuits
    "proposed",                    # not yet built
    "construction",                # under construction
    "abandoned",                   # derelict, may not exist physically
    "platform",                    # public-transport platform (not a path)
}
# fmt: on

# ``foot`` values that mean pedestrians are explicitly FORBIDDEN.
EXCLUDED_FOOT_TAGS: set[str] = {"no"}

# ``access`` values that mean general public access is forbidden.
EXCLUDED_ACCESS_TAGS: set[str] = {"private", "no"}

# ``service`` values that indicate private driveways etc.
EXCLUDED_SERVICE_TAGS: set[str] = {"private"}

# Highway values that are ONLY kept when the way has an explicit
# pedestrian-access tag (``foot ∈ PEDESTRIAN_FOOT_VALUES``).
# Without such a tag these ways are assumed cyclist/motor-only.
CONDITIONAL_HIGHWAY_TAGS: set[str] = {
    "cycleway",  # shared-use cycleways — the key fix (§2a)
}

# ``foot`` values that confirm a way is accessible to pedestrians.
PEDESTRIAN_FOOT_VALUES: set[str] = {
    "yes",
    "designated",
    "permissive",
    "official",      # rare synonym for designated
}

# ``designation`` values (UK-specific) that confirm legal pedestrian access.
# These override a missing ``foot`` tag for conditional highway types.
PEDESTRIAN_DESIGNATION_VALUES: set[str] = {
    "public_footpath",
    "public_bridleway",
    "restricted_byway",
    "byway_open_to_all_traffic",
    "permissive_footpath",
    "permissive_bridleway",
}

# Extra OSM attributes to request from pyrosm so they appear as edge columns.
# This list is appended to whatever the caller already requests.
EXTRA_WALKING_ATTRIBUTES: list[str] = [
    "designation",  # UK legal right-of-way status
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_walking_filter(edges: "gpd.GeoDataFrame") -> "gpd.GeoDataFrame":
    """Filter a raw ``network_type="all"`` edges GeoDataFrame to walking-suitable ways.

    The logic mirrors pyrosm's built-in walking filter but with two key
    improvements:

    1. ``highway=cycleway`` is **kept** when the way has a pedestrian-access
       tag (``foot ∈ {yes, designated, permissive, official}`` or a UK
       ``designation`` confirming foot access).
    2. ``designation`` is available as an edge attribute for downstream
       processors (e.g. ``_road_type_penalty``).

    Parameters
    ----------
    edges : GeoDataFrame
        Raw edges from ``osm.get_network(network_type="all", ...)``.

    Returns
    -------
    GeoDataFrame
        Filtered edges suitable for a walking network graph.
    """
    if edges is None or edges.empty:
        return edges

    initial_count = len(edges)
    mask = pd.Series(True, index=edges.index)

    # --- Hard exclusions (same as pyrosm walking filter) ------------------

    # 1. Exclude area=yes (polygon-like ways, not paths)
    if "area" in edges.columns:
        mask &= edges["area"].astype(str).str.lower() != "yes"

    # 2. Exclude unwalkable highway types (motorway, construction, etc.)
    if "highway" in edges.columns:
        highway_lower = edges["highway"].astype(str).str.lower()
        mask &= ~highway_lower.isin(EXCLUDED_HIGHWAY_TAGS)
    else:
        # No highway column means no valid road data — drop everything
        logger.warning("No 'highway' column found in edges — returning empty")
        return edges.iloc[0:0]

    # 3. Exclude foot=no
    if "foot" in edges.columns:
        foot_lower = edges["foot"].astype(str).str.lower()
        mask &= ~foot_lower.isin(EXCLUDED_FOOT_TAGS)
    else:
        foot_lower = pd.Series("", index=edges.index)

    # 4. Exclude service=private
    if "service" in edges.columns:
        mask &= edges["service"].astype(str).str.lower() != "private"

    # 5. Exclude access=private|no (unless foot tag explicitly allows)
    if "access" in edges.columns:
        access_lower = edges["access"].astype(str).str.lower()
        access_blocked = access_lower.isin(EXCLUDED_ACCESS_TAGS)
        # If foot tag is explicitly permissive, override the access block
        foot_overrides = foot_lower.isin(PEDESTRIAN_FOOT_VALUES)
        mask &= ~access_blocked | foot_overrides

    # --- Conditional inclusion (the new bit) ------------------------------
    # Ways whose highway tag is in CONDITIONAL_HIGHWAY_TAGS are only kept
    # if they have a pedestrian-access indicator.

    is_conditional = highway_lower.isin(CONDITIONAL_HIGHWAY_TAGS)

    if is_conditional.any():
        has_foot_access = foot_lower.isin(PEDESTRIAN_FOOT_VALUES)

        # Check designation tag
        if "designation" in edges.columns:
            designation_lower = edges["designation"].astype(str).str.lower()
            has_designation = designation_lower.isin(
                PEDESTRIAN_DESIGNATION_VALUES
            )
        else:
            has_designation = pd.Series(False, index=edges.index)

        pedestrian_confirmed = has_foot_access | has_designation

        # For conditional ways: keep only if pedestrian access is confirmed
        conditional_rejected = is_conditional & ~pedestrian_confirmed
        mask &= ~conditional_rejected

    filtered = edges[mask].copy()
    removed = initial_count - len(filtered)

    logger.info(
        "Walking filter: kept %d / %d edges (removed %d)",
        len(filtered),
        initial_count,
        removed,
    )

    return filtered
