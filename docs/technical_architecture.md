# Technical Architecture Summary

## 1. Data Ingestion & Preprocessing

The system does **not** use OSMnx or purely custom scripts for data ingestion. Instead, it leverages high-performance libraries for processing OpenStreetMap Protocol Buffer (PBF) files.

- **Acquisition**:
  - The `OSMDataLoader` class (`app/services/core/data_loader.py`) downloads the **Geofabrik Index** to identify the appropriate PBF file for a requested bounding box (e.g., `bristol-latest.osm.pbf` or fallback to `england-latest.osm.pbf`).
  - Files are downloaded directly from Geofabrik to `app/data`.

- **Processing**:
  - **Primary Library**: **`pyrosm`** (a Python binding for the fast Rust/C++ `rosm` library) is used to parse PBF files and convert them into a NetworkX graph.
  - **Large File Handling**: For PBFs larger than 100MB (like the full England file), **`osmium-tool`** (`subprocess` call) is used to extract a smaller bounding-box clip _before_ loading it into memory with `pyrosm`. This prevents Out-Of-Memory (OOM) errors.
  - **Feature Extraction**: Custom logic extracts specific features (POIs, Green Spaces, Water) into a `GeoDataFrame`, which is attached to the graph object.

- **Caching**:
  - **Mechanism**: The routing graph is **NOT** loaded into Redis. It is cached as **Pickle files on disk** (`app/data/cache/*.pickle`).
  - **In-Memory**: The application maintains an LRU (Least Recently Used) cache of loaded `networkx.MultiDiGraph` objects in memory to serve requests fast.
  - **Role of Redis**: Redis is used strictly as a **Message Broker and Result Backend** for Celery (asynchronous task queue), not for storing the routing graph itself.

## 2. Infrastructure & Orchestration

The application is containerized using Docker Compose.

- **Deployment**: Defined in `docker-compose.yml` with three primary services:
  1.  **`redis`**: (`redis:7-alpine`)
      - Acts as the Celery broker and result backend.
      - Persists data via the `redis_data` volume.
  2.  **`api`**: (`Flask`)
      - Runs the `python run.py` entry point.
      - Mounts `./app/data` to `/app/app/data` to share cached graphs with the worker.
      - Exposes port `5001`.
  3.  **`worker`**: (`Celery`)
      - Executes background graph building tasks (`cached_graph_build`).
      - Mounts the same `./app/data` volume to read/write cache files.

- **Volumes**:
  - Shared volume: `./app/data:/app/app/data` allows the API and Worker to share downloaded PBFs and pickled graph caches.

## 3. Frontend Implementation

- **Map Initialisation**:
  - Uses **Vanilla JavaScript** and **Leaflet.js** (no React-Leaflet or Vue wrappers).
  - Managed by the `MapController` class in `app/static/js/map.js`.
  - Tile Layers: Configurable (OSM, CartoDB Light/Dark, Voyager) via the newly implemented `setTileLayer` method.

- **Route Rendering**:
  - Routes are rendered as standard **Leaflet Polylines** (`L.polyline`).
  - Loop candidates are also rendered as polylines with hover tooltips (`bindTooltip`).
  - Debug visualizations (edges) use color-coded polylines.

- **Event Listeners**:
  - Standard Leaflet events: `click` (place marker), `dragend` (move marker).
  - The `MapController` manages state (`setting_start`, `setting_end`) but does not appear to have complex zoom/pan listeners that would conflict with dynamic tile loading (which is handled natively by Leaflet's tile layer).

## 4. Scale & Environment

- **Geographic Scale**:
  - **Default**: "Bristol, UK" (~15-30km radius).
  - **Capability**: The system is designed to handle region-sized data (e.g., Somerset, England) using the Tiling system.
  - **Tiling**: It breaks large areas into **15km tiles** (`TILE_SIZE_KM = 15` in `config.py`) to manage memory and allow partial loading.

- **Memory Constraints**:
  - **Container Limits**: No hard memory limits (`mem_limit`) are defined in `docker-compose.yml`, so containers can use available host memory.
  - **Application Limits**:
    - `MAX_CACHED_REGIONS = 3`: Only keeps 3 full region graphs in memory.
    - `MAX_CACHED_TILES = 16`: Keeps ~16 tile graphs in memory (approx. 1.5GB usage).
    - `MAX_PYROSM_PBF_SIZE = 100MB`: Threshold to trigger `osmium` extraction to protect against OOM during loading.
