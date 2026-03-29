# ADR-019: Council-First Street Lighting Integration and Overlay Source Transparency

**Status:** Accepted
**Date:** 2026-03-29

## Context

ScenicPathFinder uses two lighting consumers:

1. Routing penalties (`prefer_lit` and `heavily_avoid_unlit`) in the in-memory graph.
2. Street Lighting map overlay from PostGIS/Martin.

Historically, overlay and routing have depended primarily on OSM `lit` tags. User requirement now mandates:

- Council evidence is the most trusted and takes precedence.
- Street Lighting overlay settings must let users split visualization by data source.
- Users should be able to understand lighting type/regime (for example, part-night operation) and provenance.

## Verified Data Analysis

The following was verified from project datasets:

- Canonical council dataset (`combined_streetlights.gpkg`, layer `combined_streetlights`):
  - 82,811 rows, CRS EPSG:4326
  - Columns: `source`, `lit`, `geometry`
  - Source split: `bristol` 48,930, `south_glos` 33,881
- Bristol raw shapefile (`Streetlights.shp`):
  - 48,930 rows, CRS EPSG:27700
  - Rich type/provenance fields present: `UNIT_TYPE_`, `OWNER_DESC`, `COLTYPE`, etc.
- South Gloucestershire Excel (`Sheet1`):
  - 33,881 rows
  - Semantic fields include `Times` and unit/lamp descriptors
  - `Times` is fully populated (33,881 non-null) with informative values such as:
    - `Sunset to sunrise` (26,652)
    - `Sunset - 0500` (4,310)
    - `Sunset - 0000 (75%) 0000 - 0500 (50%)` (2,451)
    - `24 hours` (121)
    - `Solar Powered - no details available` (13)

This confirms the data supports both provenance filtering and lighting regime classification.

## Decision

### 1. Council-first precedence

Where council evidence spatially matches an OSM street segment, council wins.

- `lit_status` is set to `lit` from council match.
- This override applies even if OSM tag is `lit=no`.

### 2. Keep offline canonical council normalization

Continue standardizing council sources through `scripts/process_streetlights.py` into one canonical GeoPackage (`combined_streetlights.gpkg`) for runtime/seed consistency.

### 3. Overlay provenance and regime schema

Street lighting overlay table is extended with transparency columns, including:

- `lit_source_primary` (`council` | `osm`)
- `lit_source_detail` (`bristol` | `south_glos` | `osm`)
- `lit_tag_type` (for example `council_times`, `osm_lit`)
- `lighting_regime` (`all_night`, `part_night`, `timed_window`, `solar`, `unlit`, `unknown`)
- `lighting_regime_text` (raw informative text such as South Glos `Times` value)

### 4. Overlay settings source/regime split

Under Map Overlays > Street Lighting settings, add controls to split visualization by:

- Source: all, council only, OSM only, Bristol only, South Glos only
- Regime/type: all-night, part-night, timed-window, solar, unlit, unknown

### 5. Efficient serving strategy

Use server-side filtering over an indexed enriched PostGIS table (Martin SQL function or equivalent filtered source strategy) so source/regime filtering does not require downloading full unfiltered tiles.

## Consequences

### Positive

- Higher trustworthiness: authoritative council evidence dominates where available.
- Better user transparency: overlay can explain both origin and lighting behavior.
- Better usability at night-planning use cases (part-night vs all-night distinction).

### Tradeoffs

- Additional schema/ETL complexity in seeder and merge SQL.
- Slightly longer seed/refresh time due council merge and classification.
- Some free-text `Times` values need deterministic parsing and unknown fallbacks.

## Alternatives Considered

1. OSM-only overlay and routing enrichment.
   - Rejected: does not satisfy trust and transparency requirements.
2. Council overrides only when OSM is unknown.
   - Rejected: user requirement explicitly sets council as highest precedence.
3. Client-side-only filtering by source/regime.
   - Rejected: inefficient for large tile payloads; server-side filtering is preferable.
