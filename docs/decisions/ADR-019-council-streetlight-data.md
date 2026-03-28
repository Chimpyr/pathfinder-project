# ADR-019: Council Streetlight Data Integration

**Status:** Proposed
**Date:** 2026-03-28

## Context

The application currently relies exclusively on OpenStreetMap (OSM) `lit` tags to inform the Scenic routing engine (e.g., when a user requests to prefer lit areas or heavily avoid unlit areas). Many times, OSM tags for street lighting are incomplete or outdated compared to authoritative local government data.

We have acquired external datasets from local councils, specifically:

- Bristol City Council (Shapefile format)
- South Gloucestershire Council (Excel `.xlsx` format)

Attempting to load and process these disparate file formats directly inside the core graph-generation pipeline (in `app/services/processors/orchestrator.py` or `.data_loader.py`) would have several negative impacts:

1. **Performance Penalties:** Loading Excel files via libraries like `openpyxl` or `pandas` at runtime slows down graph cache instantiation.
2. **Dependency Bloat:** Heavy data parsing dependencies would be required in the production server and Celery workers.
3. **Format Fragility:** Handling multiple nested formats (Shapefiles, GeoJSONs, Excel, CSVs) from different councils creates unmanageable complexity in the core service.

## Decision

To introduce authoritative council street lighting while preserving system performance, we have decided to separate data standardization from graph ingestion.

### 1. Offline Pre-Processing Script

We will create a standalone script (`scripts/process_streetlights.py`) to systematically convert differing council formats (Shapefile, Excel) into a unified and standard spatial schema.

The schema will contain:

- `geometry`: Point (mapped strictly to EPSG:4326 to match our base projection).
- `source`: A string identifier for traceability (e.g., `bristol`, `s_glos`).
- `lit`: A `True`/`yes` boolean indicating the presence of a streetlight.

### 2. Standardized GeoPackage (`.gpkg`)

The pre-processing script will export the combined dataset into a single `combined_streetlights.gpkg` file stationed in `app/data/streetlight/`. This `.gpkg` format acts as our source-of-truth and standard schema. The application will only natively support loading from this standard format.

### 3. Edge-Snapping Processor

We will introduce `app/services/processors/streetlights.py` which will be called by our core orchestrator.

- It will load the unified GeoPackage if it is present.
- Using a spatial join or nearest-neighbor logic (e.g., matching points to edge centroids within a ~15-meter tolerance), it will enrich the nearby graph edges by overriding or explicitly setting the edge's `lit` attribute to `'yes'`.
- It will execute gracefully as a supplementary processor layer inside `app/services/processors/orchestrator.py` after water/natural feature logic and before POI features.

## Consequences

### Positive

- **Extensibility:** When a new council dataset is acquired, we simply add an import/normalization block to the standalone pre-processing script. The main application is deeply shielded from the raw formats.
- **Performance:** Pre-compiled `.gpkg` files are optimized for fast spatial loading with GeoPandas. There is no graph-building latency from decoding Excel sheets.
- **Maintainability:** Minimal impact on the overarching edge weight generation. The existing WSM cost heuristics will seamlessly benefit from the newly asserted `lit=yes` tags.

### Negative

- **Manual Data Refresh:** When the council releases an updated dataset, a developer/maintainer must remember to obtain the raw file and rerun `scripts/process_streetlights.py`.
- **Storage Tradeoff:** Storing the processed `.gpkg` duplicates some spatial disk output (the raw dataset and the processed dataset will live in parallel), but this overhead is negligible for points of street furniture.
