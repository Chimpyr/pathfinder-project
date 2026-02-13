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
then passes the raw edges through our
[`walking_filter.py`](../../app/services/core/walking_filter.py) module
before building the graph.

The filter applies rules in this order:

### 1. Hard exclusions (same as pyrosm)

| Rule                       | Excluded values                                                                             |
| -------------------------- | ------------------------------------------------------------------------------------------- |
| `area = yes`               | Polygon-like ways that are not walkable paths                                               |
| `highway = ...`            | `motorway`, `motorway_link`, `raceway`, `proposed`, `construction`, `abandoned`, `platform` |
| `foot = no`                | Pedestrians explicitly forbidden                                                            |
| `service = private`        | Private driveways                                                                           |
| `access = private` or `no` | General access blocked (unless `foot` tag overrides)                                        |

### 2. Conditional inclusion (new)

Ways whose `highway` tag is in the **conditional** set (currently just
`cycleway`) are only kept if one of these pedestrian-access indicators is
present:

| Indicator type    | Accepted values                                                                                                                       |
| ----------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `foot` tag        | `yes`, `designated`, `permissive`, `official`                                                                                         |
| `designation` tag | `public_footpath`, `public_bridleway`, `restricted_byway`, `byway_open_to_all_traffic`, `permissive_footpath`, `permissive_bridleway` |

If none of these tags are present on a `highway=cycleway` way, it is
excluded (assumed cyclist-only).

### 3. Everything else

All other ways with a `highway` tag (footway, path, residential, track,
etc.) pass through — same as pyrosm's walking filter.

## How to extend the filter

All rules are defined as constants at the top of
[`walking_filter.py`](../../app/services/core/walking_filter.py):

| Constant                        | Purpose                                        | Example change                                    |
| ------------------------------- | ---------------------------------------------- | ------------------------------------------------- |
| `EXCLUDED_HIGHWAY_TAGS`         | Highway values never walkable                  | Add `"bus_guideway"` to exclude bus-only ways     |
| `EXCLUDED_FOOT_TAGS`            | `foot` values meaning "no pedestrians"         | —                                                 |
| `EXCLUDED_ACCESS_TAGS`          | `access` values meaning "no public access"     | Add `"customers"` for shopping-centre-only        |
| `EXCLUDED_SERVICE_TAGS`         | `service` values meaning "private"             | Add `"parking_aisle"` to drop car park aisles     |
| `CONDITIONAL_HIGHWAY_TAGS`      | Highway tags kept only with foot-access proof  | Add `"busway"` if some have shared pedestrian use |
| `PEDESTRIAN_FOOT_VALUES`        | `foot` values confirming pedestrian access     | —                                                 |
| `PEDESTRIAN_DESIGNATION_VALUES` | UK `designation` values confirming foot access | Add `"core_path"` for Scottish core paths         |
| `EXTRA_WALKING_ATTRIBUTES`      | Extra OSM tags to request from pyrosm          | Add `"horse"` to enable bridleway routing         |

To add a new exclusion or inclusion rule, edit the relevant constant — no
other code changes are needed.

## Impact on graph size

Including shared-use cycleways adds approximately **1–3 %** more edges in
urban areas (parks, canal towpaths, river paths). Rural areas see minimal
change.

Fetching `network_type="all"` initially retrieves more ways (including
motorways), but the filter step removes them before graph construction, so
the final graph size is comparable to pyrosm's walking filter — with the
addition of the shared-use paths.

## Cache invalidation

After this change, **existing tile caches must be rebuilt** so that
shared-use cycleways are included in the graph. Delete the `cache/` folder
or the relevant `.json` cache files to force a rebuild on next request.
