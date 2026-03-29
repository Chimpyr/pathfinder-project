# Street Lighting Quickstart

This guide is the easiest way to understand and use the street-lighting overlay.

## What This Feature Does

The app can draw a street-lighting overlay on top of the map:

- Lit streets are shown in gold.
- Unlit streets are shown in dark/black.
- Unknown streets are shown in grey.
- You can filter by data source (OSM or council) and by lighting regime.

## What Is Used

The feature uses these parts end-to-end:

- OSM road data from a `.osm.pbf` file
- Council street-light point data from `combined_streetlights.gpkg` (if present)
- PostGIS to store and merge results
- Martin to serve vector tiles (`.pbf`)
- Leaflet + Leaflet.VectorGrid to render the overlay in the browser

## Quick Run Checklist

1. Start services:

```bash
docker compose up -d
```

2. Seed/import lighting data:

```bash
docker compose --profile seed up --build seeder
```

3. If needed, restart tile server discovery:

```bash
docker compose restart tileserver
```

4. Open the app and enable `Settings -> Map Overlays -> Street Lighting`.

## How To Use In The App

Once Street Lighting is enabled in Settings:

- Change colours for lit, unlit, unknown categories.
- Adjust line thickness.
- Filter by source (`All`, `Council`, `OSM`, `Bristol`, `South Glos`).
- Filter by regime (`All night`, `Part night`, `Timed window`, etc.).
- Use `Dim basemap` (default ON) to darken background tiles so the lighting overlay is easier to read.
- Use `Hover info card` (default ON) to inspect provenance and metadata on individual segments.

## Data Rules (Simple Version)

- OSM roads are imported first and classified from `lit=*` tags.
- Council points are then merged in.
- If council evidence matches a segment, council metadata is treated as primary.
- OSM-only filter still keeps segments with explicit OSM `lit=*` evidence.

## Key Scripts And Files

- `docker/seeder/lighting.lua`: OSM import rules and initial lighting classification.
- `scripts/wait-for-postgres.sh`: Seeder orchestration and import flow.
- `docker/seeder/merge_council_streetlights.sql`: Council merge + filtered SQL tile function.
- `docker/martin/config.yaml`: Martin auto-publish configuration.
- `app/static/js/map.js`: Overlay rendering and dim-basemap map pane.
- `app/static/js/modules/settings_ui.js`: Settings controls and localStorage persistence.
- `app/templates/index.html`: Street-lighting settings UI.

## Database Objects You Should Know

- Main table: `public.street_lighting`
- Filter function: `public.street_lighting_filtered(z, x, y, query_params json)`

## Read Next (Deeper Technical Detail)

- Full technical feature reference:
  `docs/features/street_lighting.md`
- Decision record (council-first merge):
  `docs/decisions/ADR-019-council-streetlight-data.md`
- System-wide architecture:
  `docs/architecture.md`
- Technical architecture details:
  `docs/technical_architecture.md`
- Docker setup and commands:
  `docs/guides/docker_setup.md`, `docs/guides/docker_commands.md`
