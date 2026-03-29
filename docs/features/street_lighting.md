# Street Lighting Vector Tile Overlay

Adds a live vector tile overlay to the map visualising street lighting provenance and regimes, powered by PostGIS and Martin. OSM remains the base network and council evidence is merged with council-first precedence where available.

---

## Overview

Streets are rendered by `lit_status` with configurable colours, while metadata columns (`lit_source_primary`, `lit_source_detail`, `lighting_regime`) support source/regime splitting in settings. The overlay is served as Mapbox Vector Tiles (MVT / `.pbf`) from Martin and rendered via `Leaflet.VectorGrid`.

---

## Architecture

```
OSM PBF file
    │
    ▼ (one-off seeder container)
osm2pgsql --flex (lighting.lua)
  │
  ├── council GPKG import (optional)
  │      /data/streetlight/combined_streetlights.gpkg
  │
  ▼
merge_council_streetlights.sql
    │
    ▼
PostGIS: scenic_tiles.public.street_lighting
    │
    ▼
Martin tile server  →  /street_lighting/{z}/{x}/{y}.pbf
         or  /street_lighting_filtered/{z}/{x}/{y}.pbf?source_filter=...&regime_filter=...
    │
    ▼
Leaflet.VectorGrid  →  rendered on map
```

| Component      | Technology                                   | Port |
| -------------- | -------------------------------------------- | ---- |
| Database       | PostGIS 16 / PostgreSQL 3.5                  | 5432 |
| Tile server    | Martin v1.3.1                                | 3000 |
| Ingestion tool | osm2pgsql 1.9 (via debian:bookworm-slim apt) | —    |
| Frontend       | Leaflet.VectorGrid (bundled CDN)             | —    |

---

## Prerequisites

- Docker & Docker Compose installed
- `app/data/england-latest.osm.pbf` present (downloaded by the data loader, or place manually)
- A `.env` file at the project root (copy from `.env.example`)

---

## Configuration

Postgres credentials are defined once in `.env`:

```dotenv
POSTGRES_USER=scenic
POSTGRES_PASSWORD=scenic
POSTGRES_DB=scenic_tiles
```

All services (`db`, `tileserver`, `seeder`) read these via Docker Compose variable substitution — no credentials are hardcoded.

---

## Running

### Step 1 — Start core services

```bash
docker compose up -d
```

This starts `db` (PostGIS), `tileserver` (Martin), `redis`, `api`, and `worker`. Martin will be healthy but serve **no sources** until the seeder has run.

### Step 2 — Seed the database (one-off)

```bash
docker compose --profile seed up --build seeder
```

> **Always use `--build`** the first time, or after any changes to `scripts/wait-for-postgres.sh` or `docker/seeder/lighting.lua`. Without it, Docker reuses a cached image layer and will not pick up file changes.

This builds and runs the `seeder` container, which:

1. Waits for PostGIS to be ready via `pg_isready`
2. Runs `osm2pgsql --create --flex` using `docker/seeder/lighting.lua`
3. Imports council canonical GPKG when present (`/data/streetlight/combined_streetlights.gpkg`)
4. Runs `docker/seeder/merge_council_streetlights.sql` to enrich overlay metadata and apply council-first precedence
5. Writes the enriched `street_lighting` table into `public` schema of `scenic_tiles`

> **Expected duration**: 5–20 minutes for `england-latest.osm.pbf` (~1.3 GB), depending on hardware.  
> **Expected output**: `Import finished successfully.`

The `--create` flag is **idempotent** — re-running the seeder wipes and recreates the table, which is safe for re-seeding after a PBF update.

### Step 3 — Verify Martin discovers the table

After the seeder finishes, Martin discovers sources dynamically. Check:

```
http://localhost:3000/catalog
```

Expected response (JSON):

```json
{
  "street_lighting": {
    "content_type": "application/x-protobuf",
    ...
  }
}
```

If `street_lighting` is absent, restart the tileserver container to force re-discovery:

```bash
docker compose restart tileserver
```

### Step 4 — Test tile endpoints

Pick a tile over Bristol at zoom 14:

```
http://localhost:3000/street_lighting/14/8167/5449.pbf
```

A non-empty binary (`.pbf`) response confirms tiles are being served correctly.

Optional filtered endpoint check:

```
http://localhost:3000/street_lighting_filtered/14/8167/5449.pbf?source_filter=council&regime_filter=part_night
```

### Step 5 — Enable the frontend overlay

Open the app at `http://localhost:5001` and run in the browser console:

```javascript
mapController.addLightingLayer();
```

Gold lines (lit streets) and dark grey lines (unlit streets) will appear on the map.

To remove the overlay:

```javascript
mapController.removeLightingLayer();
```

---

## Data Schema

The `street_lighting` table is created by `docker/seeder/lighting.lua` and enriched by `docker/seeder/merge_council_streetlights.sql`:

| Column                 | Type     | Description                                                            |
| ---------------------- | -------- | ---------------------------------------------------------------------- |
| `osm_id`               | bigint   | OSM way ID                                                             |
| `lit_status`           | text     | `lit`, `unlit`, `unknown`                                              |
| `lit_source_primary`   | text     | `osm` or `council`                                                     |
| `lit_source_detail`    | text     | `osm`, `bristol`, `south_glos`, etc.                                   |
| `lit_tag_type`         | text     | Tag/source class (`osm_lit`, `council_times`, etc.)                    |
| `lighting_regime`      | text     | `all_night`, `part_night`, `timed_window`, `solar`, `unlit`, `unknown` |
| `lighting_regime_text` | text     | Raw descriptive text (for example South Glos `Times`)                  |
| `osm_lit_raw`          | text     | Raw OSM `lit=*` value captured during import                           |
| `council_match_count`  | integer  | Number of council points matched to the segment                        |
| `geom`                 | geometry | Linestring in SRID 3857 (Web Mercator)                                 |

OSM `lit` tag values are normalised to three states:

| OSM tag value                      | `lit_status` | Rendered as                |
| ---------------------------------- | ------------ | -------------------------- |
| `yes`, `true`, `automatic`, `24/7` | `'lit'`      | Gold (configurable)        |
| `no`                               | `'unlit'`    | Near-black `#1a1a1a`       |
| Absent or unrecognised             | `'unknown'`  | Mid grey `#888888` (faint) |

The distinction between `'unlit'` and `'unknown'` is intentional. Additionally, when council points match an OSM segment, council evidence is treated as authoritative and the segment is promoted to `lit` with council provenance metadata.

Source differentiation method:

- Stage 1 (OSM import): all highways are imported with `lit_source_primary='osm'`, `lit_source_detail='osm'`, and raw OSM `lit=*` copied into `osm_lit_raw`.
- Stage 2 (council merge): any segment within `ST_DWithin(..., 15)` of council points is promoted to `lit_source_primary='council'` with authority-specific `lit_source_detail` (for example `bristol`, `south_glos`).
- OSM source filtering keeps rows where source is OSM **or** there is explicit OSM `lit=*` evidence in `osm_lit_raw`, so overlapping OSM-tagged lines are still visible in OSM mode.

## Source And Regime Filters

Street Lighting settings now support overlay filtering by:

- Source: All, Council only, OSM only, Bristol only, South Glos only
- Regime: All, All night, Part night, Timed window, Solar, Unlit, Unknown

When filters are active, the frontend requests the filtered Martin function endpoint for more efficient tile transfer.
`public.street_lighting_filtered` uses the Martin-compatible signature `(z, x, y, query_params json)` and reads `source_filter` / `regime_filter` from query string JSON.

---

## Map Styling

Defined in `MapController.addLightingLayer()` in `app/static/js/map.js`:

| `lit_status` | Colour                        | Weight                  | Opacity | Meaning                |
| ------------ | ----------------------------- | ----------------------- | ------- | ---------------------- |
| `lit`        | `#FFD700` gold (configurable) | litWeight (default 2px) | 0.85    | Confirmed lit street   |
| `unlit`      | `#1a1a1a` near-black          | litWeight − 1           | 0.6     | Confirmed unlit street |
| `unknown`    | `#888888` mid grey            | 1px (fixed)             | 0.25    | No lighting data       |

---

## Updating the Data

To re-import after downloading a newer PBF:

```bash
# 1. Replace the PBF in app/data/
# 2. Re-run the seeder (--create wipes and recreates the table)
docker compose --profile seed up seeder

# 3. Restart Martin to pick up the refreshed table
docker compose restart tileserver
```

---

## Troubleshooting

Issues encountered during initial setup are documented here for reference.

---

### Martin image fails to pull (`no matching manifest for linux/amd64`)

**Symptom:**

```
no matching manifest for linux/amd64 in the manifest list entries
```

**Cause:** The original `ghcr.io/maplibre/martin:v0.14` tag predates proper multi-platform manifest support and has no `linux/amd64` entry.  
**Fix:** Use `v1.3.1` or later. The image is pinned to `ghcr.io/maplibre/martin:v1.3.1` in `docker-compose.yml`.

---

### `services.db.environment.[0]: unexpected type map[string]interface {}`

**Symptom:** `docker compose up` fails to parse the file.  
**Cause:** A YAML formatter converts list-style environment entries from `- KEY=VALUE` to `- KEY: VALUE`, which Docker Compose parses as a map instead of a string.  
**Fix:** Environment variables in list syntax must use `=` with no spaces: `- POSTGRES_USER=${POSTGRES_USER}`.

---

### `FATAL: database "scenic" does not exist` repeating every 5 seconds

**Symptom:** Repeated FATAL errors in `scenic-db` logs from the healthcheck.  
**Cause:** `pg_isready -U scenic` with no `-d` flag defaults to connecting to a database named after the user (`scenic`). The actual database is `scenic_tiles`.  
**Fix:** Healthcheck now uses `pg_isready -U $POSTGRES_USER -d $POSTGRES_DB`.

---

### Martin auto-publishes `tiger.*` tables

**Symptom:** Martin logs show dozens of `tiger.bg`, `tiger.county`, etc. sources being discovered.  
**Cause:** The `postgis/postgis` image includes the US TIGER geocoder extension with geometry tables. Martin's default auto-publish scans all schemas.  
**Fix:** `docker/martin/config.yaml` restricts `auto_publish` to `from_schemas: [public]` only. Ensure this file is mounted into the tileserver container.

---

### Seeder fails — `pull access denied, repository does not exist`

**Symptom:**

```
failed to resolve source metadata for docker.io/osm2pgsql/osm2pgsql:1.10: pull access denied
```

**Cause:** There is no official `osm2pgsql/osm2pgsql` image on Docker Hub.  
**Fix:** The seeder Dockerfile now uses `debian:bookworm-slim` and installs `osm2pgsql` and `postgresql-client` via `apt`.

---

### Seeder fails — `Open failed for '/data/england-latest.osm.pbf': No such file or directory`

**Symptom:** Import fails immediately after `PostGIS is ready!`.  
**Cause:** The PBF filename doesn't match the hardcoded path. Geofabrik downloads may be named `england.osm.pbf` or `england-latest.osm.pbf` depending on source.  
**Fix:** `wait-for-postgres.sh` now probes both filenames and exits with a clear error if neither is found.

---

### Script changes not picked up despite `docker compose down` / `up`

**Symptom:** The seeder runs with old script behaviour even after editing `wait-for-postgres.sh`.  
**Cause:** `docker compose up` reuses the previously built image layer. `docker compose down` does not remove built images.  
**Fix:** Always pass `--build` when the script or Lua file has changed:

```bash
docker compose --profile seed up --build seeder
```

---

### Seeder ignores `if/elif` block — PBF fallback logic never runs

**Symptom:** Build picks up the new script (`COPY scripts/wait-for-postgres.sh` step re-runs), but `Using PBF:` never prints and the old hardcoded path is used.  
**Cause:** Windows saves `.sh` files with CRLF (`\r\n`) line endings. Inside the Linux container the `\r` corrupts variable assignments, causing the `if` block to silently fail.  
**Fix:** The Dockerfile runs `sed -i 's/\r//' /wait-for-postgres.sh` immediately after `COPY` to strip carriage returns before `chmod`.

---

### Build fails — `parent snapshot does not exist: not found`

**Symptom:**

```
failed to prepare extraction snapshot: parent snapshot ... does not exist: not found
```

**Cause:** Docker Desktop's internal BuildKit cache has a corrupted snapshot reference. Unrelated to project code.  
**Fix:**

```bash
docker builder prune -f
docker compose --profile seed up --build seeder
```

---

### `street_lighting` not in Martin `/catalog` after seeder completes

**Cause:** Martin scanned the database at startup before the seeder created the table.  
**Fix:**

```bash
docker compose restart tileserver
```

---

### General slow import / OOM

**Cause:** The England PBF is ~1.3 GB with ~50 million ways. The import takes 10–30 minutes on a typical laptop.  
**Fix:** Increase `--cache` in `wait-for-postgres.sh` if RAM allows (default is `4000` MB). Alternatively use a smaller regional extract from [Geofabrik](https://download.geofabrik.de/europe/great-britain/england.html) (e.g. `bristol-latest.osm.pbf`).
