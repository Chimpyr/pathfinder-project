"""
Custom walking network filter for ScenicPathFinder.

Replaces pyrosm's built-in ``network_type="walking"`` filter which
hard-excludes ``highway=cycleway`` regardless of pedestrian access tags.

This filter keeps cycleways and other ways that are legally or explicitly
accessible to pedestrians, while still excluding genuinely unwalkable
infrastructure (motorways, construction, etc.).

It also performs **restricted-access pruning**: edges tagged as private,
military, agricultural, etc. are removed before graph construction,
unless an explicit pedestrian override (``foot=yes``, ``foot=designated``)
is present.  Node-level barriers (locked gates) also cause connected
edges to be dropped.

Design goals
------------
1. **Correct** — include shared-use cycleways tagged ``foot=yes``
   or ``foot=designated``.
2. **Expandable** — adding a new access rule or highway type is a
   one-line change to a clearly-named constant.
3. **Documented** — every exclusion and inclusion rule has a comment
   explaining *why*.
4. **Safe** — remove edges through military zones, private business
   parks, locked gates, and similar non-navigable areas.

See also:
    ``docs/features/custom_walking_filter.md`` for the user-facing
    documentation.
    ``docs/decisions/ADR-010-improvements-to-budget-astar-looper.md §2a``
    for the investigation that motivated this module.
"""

from __future__ import annotations

import logging
from typing import Optional, Set, TYPE_CHECKING

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

# ---------------------------------------------------------------------------
# Restricted-access tag sets  (used by the unified pruning masks)
# ---------------------------------------------------------------------------

# ``access`` values that mean general public access is forbidden.
# Broader than the original {private, no} — covers military, agricultural, etc.
RESTRICTED_ACCESS: set[str] = {
    "private", "no", "military", "customers",
    "agricultural", "forestry", "delivery", "restricted",
}

# ``foot`` values that mean pedestrians are explicitly forbidden or redirected.
RESTRICTED_FOOT: set[str] = {
    "no", "private", "restricted", "use_sidepath",
}

# ``foot`` values that **explicitly allow** pedestrian access.
# Used as an override: an edge with access=private BUT foot=designated is KEPT.
EXPLICIT_ALLOW: set[str] = {
    "yes", "permissive", "designated", "public",
}

# ``service`` sub-tag values indicating private/non-public service roads.
RESTRICTED_SERVICE: set[str] = {
    "driveway", "parking_aisle", "private",
}

# ---------------------------------------------------------------------------
# Legacy aliases  (kept for backward compatibility with existing tests)
# ---------------------------------------------------------------------------
EXCLUDED_FOOT_TAGS: set[str] = RESTRICTED_FOOT
EXCLUDED_ACCESS_TAGS: set[str] = RESTRICTED_ACCESS
EXCLUDED_SERVICE_TAGS: set[str] = RESTRICTED_SERVICE

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
    "barrier",      # gate / bollard / fence (for node-level barrier resolution)
    "locked",       # whether a barrier is locked
    "service",      # service road sub-type (driveway, parking_aisle, etc.)
]


# ---------------------------------------------------------------------------
# Node-level barrier resolution
# ---------------------------------------------------------------------------

def _resolve_restricted_nodes(
    nodes: "gpd.GeoDataFrame",
) -> Set[int]:
    """Identify impassable node IDs (locked gates, restricted checkpoints).

    A node is considered impassable when:
    - ``barrier == 'gate'``  **AND**
    - (``locked == 'yes'``  **OR**  ``access ∈ RESTRICTED_ACCESS``)

    Parameters
    ----------
    nodes : GeoDataFrame
        Raw nodes from ``osm.get_network(nodes=True)``.

    Returns
    -------
    set[int]
        Node IDs that should block any edge touching them.
    """
    if nodes is None or nodes.empty:
        return set()

    # Need both 'barrier' and at least one of 'locked'/'access'
    if "barrier" not in nodes.columns:
        return set()

    barrier_lower = nodes["barrier"].astype(str).str.lower()
    is_gate = barrier_lower == "gate"

    if not is_gate.any():
        return set()

    # Check locked status
    if "locked" in nodes.columns:
        is_locked = nodes["locked"].astype(str).str.lower() == "yes"
    else:
        is_locked = pd.Series(False, index=nodes.index)

    # Check access restriction
    if "access" in nodes.columns:
        is_restricted = nodes["access"].astype(str).str.lower().isin(RESTRICTED_ACCESS)
    else:
        is_restricted = pd.Series(False, index=nodes.index)

    blocked = is_gate & (is_locked | is_restricted)

    if not blocked.any():
        return set()

    # Extract the node IDs — pyrosm uses the DataFrame index or an 'id' column
    if "id" in nodes.columns:
        restricted_ids = set(nodes.loc[blocked, "id"])
    else:
        restricted_ids = set(nodes.index[blocked])

    logger.info("Barrier filter: identified %d restricted gate nodes", len(restricted_ids))
    return restricted_ids


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def apply_walking_filter(
    edges: "gpd.GeoDataFrame",
    nodes: Optional["gpd.GeoDataFrame"] = None,
) -> "gpd.GeoDataFrame":
    """Filter a raw ``network_type="all"`` edges GeoDataFrame to walking-suitable ways.

    The logic mirrors pyrosm's built-in walking filter but with key
    improvements:

    1. ``highway=cycleway`` is **kept** when the way has a pedestrian-access
       tag (``foot ∈ {yes, designated, permissive, official}`` or a UK
       ``designation`` confirming foot access).
    2. ``designation`` is available as an edge attribute for downstream
       processors (e.g. ``_road_type_penalty``).
    3. **Restricted-access pruning** — edges through military zones,
       private business parks, locked gates, and similar non-navigable
       areas are removed unless an explicit pedestrian override is present.

    Parameters
    ----------
    edges : GeoDataFrame
        Raw edges from ``osm.get_network(network_type="all", ...)``.
    nodes : GeoDataFrame, optional
        Raw nodes from the same call.  Used for barrier/gate resolution.
        If ``None``, barrier filtering is skipped.

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

    # Pre-compute foot_lower (used by multiple masks below)
    if "foot" in edges.columns:
        foot_lower = edges["foot"].astype(str).str.lower()
    else:
        foot_lower = pd.Series("", index=edges.index)

    # --- Conditional inclusion (cycleway §2a fix) -------------------------
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

    # =====================================================================
    # Restricted-access pruning  (four boolean masks + barrier resolution)
    # =====================================================================

    # Mask A — The Override: explicit pedestrian allow
    is_explicitly_allowed = foot_lower.isin(EXPLICIT_ALLOW)

    # Mask B — Pedestrian restriction (foot tag forbids walking)
    is_foot_restricted = foot_lower.isin(RESTRICTED_FOOT)

    # Mask C — General access restriction (access tag forbids entry)
    if "access" in edges.columns:
        access_lower = edges["access"].astype(str).str.lower()
        is_access_restricted = access_lower.isin(RESTRICTED_ACCESS)
    else:
        is_access_restricted = pd.Series(False, index=edges.index)

    # Mask D — Implicit service-road restriction
    if "service" in edges.columns:
        service_lower = edges["service"].astype(str).str.lower()
        is_private_service = (
            (highway_lower == "service")
            & service_lower.isin(RESTRICTED_SERVICE)
        )
    else:
        is_private_service = pd.Series(False, index=edges.index)

    # --- Node-level barrier resolution ------------------------------------
    restricted_node_ids = _resolve_restricted_nodes(nodes)

    if restricted_node_ids:
        # Flag edges whose source or target vertex is a restricted gate
        if "u" in edges.columns and "v" in edges.columns:
            gate_blocked = (
                edges["u"].isin(restricted_node_ids)
                | edges["v"].isin(restricted_node_ids)
            )
        else:
            gate_blocked = pd.Series(False, index=edges.index)
    else:
        gate_blocked = pd.Series(False, index=edges.index)

    # --- Unified drop mask ------------------------------------------------
    # drop = gate_blocked | B | (C & ~A) | (D & ~A)
    drop_mask = (
        gate_blocked
        | is_foot_restricted
        | (is_access_restricted & ~is_explicitly_allowed)
        | (is_private_service & ~is_explicitly_allowed)
    )

    mask &= ~drop_mask

    filtered = edges[mask].copy()
    removed = initial_count - len(filtered)

    logger.info(
        "Walking filter: kept %d / %d edges (removed %d)",
        len(filtered),
        initial_count,
        removed,
    )

    return filtered
