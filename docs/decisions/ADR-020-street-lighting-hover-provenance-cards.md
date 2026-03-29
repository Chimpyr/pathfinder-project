# ADR-020: Street Lighting Hover Provenance Cards

**Status:** Accepted
**Date:** 2026-03-29

## Context

Street lighting visualisation now combines OSM-tagged data with council evidence (council-first precedence).
Users reported uncertainty about whether displayed segments were OSM-derived, council-derived, or both.

Existing source/regime filters are useful, but they do not explain an individual segment at point-of-use.
A user needs quick per-segment provenance and metadata without leaving the map.

## Decision

### 1. Add a dedicated street-lighting hover info toggle

In `Settings > Map Overlays > Street Lighting`, add `Hover info card` as an explicit toggle.

- Default: ON for first-time users (missing preference key).
- Persisted key: `lightingHoverInfo`.
- Scope: applies only when the street lighting overlay is enabled.

### 2. Show segment metadata on hover (no extra backend call)

When hovering a lighting segment, render a lightweight info card near the cursor using metadata already present in vector tile feature properties.

The card must present evidence in distinct sections:

- Council evidence block (authority, regime, match metadata)
- OSM evidence block (raw `lit=*` and OSM-derived metadata)

When both evidence types exist on the same segment, both sections are shown simultaneously to avoid collapsing provenance into a single merged label.

Fields displayed (when available):

- `lit_status`
- `lit_source_primary`
- `lit_source_detail`
- `lighting_regime`
- `lit_tag_type`
- `osm_lit_raw`
- `lighting_regime_text`
- `council_match_count`
- `osm_id` (shown as absolute way id)

### 3. Keep implementation client-side and non-blocking

- No additional API endpoint or per-hover network request.
- Use existing Martin tile payload and Leaflet vector-grid events.
- Keep card read-only and ephemeral (mouseover/mousemove show, mouseout hide).

### 4. Preserve existing filter semantics

Hover cards report metadata for whichever segments are currently rendered by active source/regime filters.
They do not alter filtering logic.

## Consequences

### Positive

- Improves source transparency at segment level.
- Reduces confusion when council-promoted segments still retain OSM evidence metadata.
- Low operational overhead: no backend changes required.

### Tradeoffs

- Additional UI complexity (another toggle in an already dense settings panel).
- Slight client-side event/render overhead while hovering dense tiles.
- Metadata values come from precomputed tile properties; if schema changes, card labels must stay aligned.

## Alternatives Considered

1. Always-on hover cards without a toggle.
   - Rejected: some users prefer a cleaner map and fewer hover interactions.

2. Click-to-open segment details only.
   - Rejected: slower exploratory workflow and more interaction cost.

3. Fetch full segment details from backend on hover.
   - Rejected: unnecessary network churn and latency for high-frequency pointer movement.

## Implementation References

- UI toggle wiring: `app/templates/index.html`, `app/static/js/modules/settings_ui.js`
- Hover card rendering logic: `app/static/js/map.js`
- Card styling: `app/static/css/style.css`
- Source/regime schema context: `docs/features/street_lighting.md`
- Council-first source precedence decision: `docs/decisions/ADR-019-council-streetlight-data.md`
