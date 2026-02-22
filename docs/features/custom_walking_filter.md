# Custom Walking Network Filter

ScenicPathFinder uses a **custom walking network filter** instead of
pyrosm's built-in `network_type="walking"` filter. This page explains
why, what the filter does, and how to extend it.

## Why a custom filter?

Pyrosm's walking filter hard-excludes every way tagged `highway=cycleway`,
regardless of whether pedestrians are allowed. This is correct for most
cycleways, but **silently drops shared-use paths** — a common pattern in UK
parks and along rivers where a tarmac cycle path is also a designated public
footpath.

Example of a dropped way (Stoke Park, Bristol):

```
highway=cycleway
designation=public_footpath
foot=designated
surface=asphalt
```

This is the main pedestrian route through the park, but pyrosm's walking
filter never lets it reach the graph.

For the full investigation, see
[ADR-010 §2a](../decisions/ADR-010-improvemetns-to-budget-astar-looper.md).

## How it works

Instead of `osm.get_network(network_type="walking")`, the data loader now
calls `osm.get_network(network_type="all")` to fetch **all** highway ways,
then passes the raw edges (and nodes) through our
[`walking_filter.py`](../../app/services/core/walking_filter.py) module
before building the graph.

The filter applies rules in this order:

### 1. Hard exclusions (same as pyrosm)

| Rule          | Excluded values                                                                             |
| ------------- | ------------------------------------------------------------------------------------------- |
| `area = yes`  | Polygon-like ways that are not walkable paths                                               |
| `highway = …` | `motorway`, `motorway_link`, `raceway`, `proposed`, `construction`, `abandoned`, `platform` |

### 2. Conditional inclusion (cycleway fix)

Ways whose `highway` tag is in the **conditional** set (currently just
`cycleway`) are only kept if one of these pedestrian-access indicators is
present:

| Indicator type    | Accepted values                                                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `foot` tag        | `yes`, `designated`, `permissive`, `official`                                                                                         |
| `designation` tag | `public_footpath`, `public_bridleway`, `restricted_byway`, `byway_open_to_all_traffic`, `permissive_footpath`, `permissive_bridleway` |

If none of these tags are present on a `highway=cycleway` way, it is
excluded (assumed cyclist-only).

### 3. Restricted-access pruning

Four boolean masks identify edges that should be removed. An
**explicit-allow override** (`foot ∈ EXPLICIT_ALLOW`) prevents legitimate
public footpaths on private land from being dropped.

| Mask | Tag(s) | Condition | Override? |
| ---- | ------ | --------- | --------- |
| **Foot restriction** | `foot` | `∈ RESTRICTED_FOOT` (`no`, `private`, `restricted`, `use_sidepath`) | No — always dropped |
| **Access restriction** | `access` | `∈ RESTRICTED_ACCESS` (`private`, `no`, `military`, `customers`, `agricultural`, `forestry`, `delivery`, `restricted`) | Yes — kept if `foot ∈ EXPLICIT_ALLOW` |
| **Service restriction** | `highway` + `service` | `highway = service` AND `service ∈ RESTRICTED_SERVICE` (`driveway`, `parking_aisle`, `private`) | Yes — kept if `foot ∈ EXPLICIT_ALLOW` |
| **Barrier/gate** | node `barrier` + `locked`/`access` | `barrier = gate` AND (`locked = yes` OR `access ∈ RESTRICTED_ACCESS`) | No — always dropped |

The explicit-allow set: `{'yes', 'permissive', 'designated', 'public'}`.

**Drop equation:**
```
drop = gate_blocked | foot_restricted | (access_restricted & ~explicitly_allowed) | (service_restricted & ~explicitly_allowed)
```

For technical details, see
[ADR-011: Restricted-Access Pruning](../decisions/ADR-011-restricted-access-pruning.md).

### 4. Everything else

All other ways with a `highway` tag (footway, path, residential, track,
etc.) pass through — same as pyrosm's walking filter.

## How to extend the filter

All rules are defined as constants at the top of
[`walking_filter.py`](../../app/services/core/walking_filter.py):

| Constant                        | Purpose                                        | Example change                                    |
| ------------------------------- | ---------------------------------------------- | ------------------------------------------------- |
| `EXCLUDED_HIGHWAY_TAGS`         | Highway values never walkable                  | Add `"bus_guideway"` to exclude bus-only ways     |
| `RESTRICTED_FOOT`               | `foot` values that block pedestrian access     | Add `"military"` for foot-specific military ban   |
| `RESTRICTED_ACCESS`             | `access` values that block general public      | Add `"permit"` for permit-only areas              |
| `EXPLICIT_ALLOW`                | `foot` values that override access restrictions | —                                                |
| `RESTRICTED_SERVICE`            | `service` values for private service roads     | Add `"emergency_access"` to drop fire-road ways  |
| `CONDITIONAL_HIGHWAY_TAGS`      | Highway tags kept only with foot-access proof  | Add `"busway"` if some have shared pedestrian use |
| `PEDESTRIAN_FOOT_VALUES`        | `foot` values confirming pedestrian access     | —                                                 |
| `PEDESTRIAN_DESIGNATION_VALUES` | UK `designation` values confirming foot access | Add `"core_path"` for Scottish core paths         |
| `EXTRA_WALKING_ATTRIBUTES`      | Extra OSM tags to request from pyrosm          | Add `"horse"` to enable bridleway routing         |

To add a new exclusion or inclusion rule, edit the relevant constant — no
other code changes are needed.

## Impact on graph size

Including shared-use cycleways adds approximately **1–3 %** more edges in
urban areas (parks, canal towpaths, river paths). The restricted-access
pruning **removes** additional edges (driveways, private roads, military
areas), resulting in a net graph size similar to pyrosm's walking filter
with improved correctness.

Fetching `network_type="all"` initially retrieves more ways (including
motorways), but the filter step removes them before graph construction, so
the final graph size is comparable to pyrosm's walking filter — with the
addition of the shared-use paths and without the restricted areas.

## Cache invalidation

After any changes to the filter constants, **existing tile caches must be
rebuilt** so that the updated rules take effect. Delete the `cache/` folder
or use the admin panel cache clear to force a rebuild on next request.
