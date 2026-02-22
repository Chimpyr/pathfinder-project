# ScenicPathFinder - System Architecture

Complete technical documentation of the pedestrian routing engine.

---

## Overview

ScenicPathFinder is a pedestrian routing engine that calculates walking routes with support for weighted multi-criteria pathfinding (quietness, greenness, water proximity, social POIs).

```
User Input → Geocoding → Region Detection → Graph Loading → A* Routing → Map Display
```

---

## Directory Structure

```
ScenicPathFinder/
├── app/
│   ├── services/
│   │   ├── core/                    # Infrastructure
│   │   │   ├── cache_manager.py     # Disk caching (pickle)
│   │   │   ├── data_loader.py       # PBF download + parsing
│   │   │   ├── walking_filter.py    # Custom walking network filter
│   │   │   └── graph_manager.py     # Two-tier cache orchestration
│   │   │
│   │   ├── processors/              # Edge attribute processors
│   │   │   ├── greenness.py         # Green visibility (FAST/NOVACK)
│   │   │   ├── water.py             # Water proximity scoring
│   │   │   ├── social.py            # POI proximity scoring
│   │   │   ├── elevation.py         # Gradient calculation
│   │   │   ├── quietness.py         # Highway noise classification
│   │   │   ├── lighting.py          # Street lighting status
│   │   │   ├── surface.py           # Surface type classification (paved/unpaved)
│   │   │   └── orchestrator.py      # Scenic pipeline coordinator
│   │   │
│   │   ├── routing/                 # Pathfinding
│   │   │   ├── route_finder.py      # A* pathfinding wrapper
│   │   │   ├── astar/               # Custom A* implementation
│   │   │   └── loop_solvers/        # Round-trip route generation algorithms
│   │   │
│   │   └── rendering/               # Map output
│   │       └── map_renderer.py      # Folium map generation
│   │
│   ├── models/                      # SQLAlchemy ORM models
│   │   ├── user.py                  # User accounts (email, hashed password)
│   │   ├── saved_pin.py             # Bookmarked map locations
│   │   └── saved_route.py           # Saved route configurations
│   │
│   ├── blueprints/                  # Modular Flask API endpoints
│   │   ├── auth.py                  # Registration, login, logout
│   │   ├── user_data.py             # CRUD for pins and routes
│   │   ├── admin.py                 # Admin panel / diagnostics
│   │   └── tasks.py                 # Async task polling
│   │
│   ├── extensions.py                # Centralised extension instances
│   ├── routes.py                    # Core routing Flask endpoints
│   ├── templates/                   # HTML templates
│   └── data/                        # Downloaded PBF files + cache
│
├── scripts/
│   ├── db_bootstrap.py              # Auto-creates user_db on PostGIS
│   └── wait-for-postgres.sh         # Container health-check script
│
├── config.py                        # Application settings
├── run.py                           # Entry point
├── tests/                           # Test suite
└── docs/                            # Documentation
```

---

## Request Flow

### 1. User Input

User enters start/end locations (addresses or postcodes).

```
POST /
  start: "Clifton Suspension Bridge"
  end: "Bristol Temple Meads"
```

### 2. Geocoding

`routes.py` uses **osmnx** to convert addresses to coordinates:

```python
start_point = ox.geocode("Clifton Suspension Bridge")  # → (51.454, -2.627)
end_point = ox.geocode("Bristol Temple Meads")  # → (51.449, -2.580)
```

### 3. Bounding Box Calculation

A buffer (~2km) is added around the route endpoints:

```python
bbox = (min_lat - 0.02, min_lon - 0.02, max_lat + 0.02, max_lon + 0.02)
```

### 4. Region Detection

`GraphManager` identifies the correct OSM extract:

```python
region_name = "bristol"  # From Geofabrik index
```

### 5. Graph Loading (Two-Tier Cache)

```
┌─────────────────┐    hit     ┌──────────────┐
│  Memory Cache   │ ─────────→ │ Return Graph │
└────────┬────────┘            └──────────────┘
         │ miss
         ▼
┌─────────────────┐    hit     ┌──────────────┐
│   Disk Cache    │ ─────────→ │ Load Pickle  │
└────────┬────────┘            └──────────────┘
         │ miss
         ▼
┌─────────────────────────────────────────────┐
│           Full Processing Pipeline          │
│  PBF → Graph → Quietness → Scenic → Save    │
└─────────────────────────────────────────────┘
```

### 6. Route Calculation

`RouteFinder` uses A\* algorithm to find optimal path:

```python
route = finder.find_route(start_point, end_point)
# → [node_id_1, node_id_2, ..., node_id_n]
```

### 7. Map Rendering

`MapRenderer` creates Folium map with route overlay:

```python
map_html = MapRenderer.render_map(graph, route, start, end)
```

---

## Core Services

### OSMDataLoader (`core/data_loader.py`)

Downloads and parses OpenStreetMap data.

**Key methods:**

- `load_graph(bbox)` - Parse PBF to NetworkX graph
- `extract_green_areas()` - Parks, forests (→ GeoDataFrame)
- `extract_buildings()` - Building polygons for occlusion
- `extract_water()` - Rivers, lakes for scenic scoring
- `extract_pois()` - Tourist/social POIs for social scoring

**Data source:** Geofabrik regional extracts (e.g., `bristol.osm.pbf`)
Originally used Overpass api (https://wiki.openstreetmap.org/wiki/Overpass_API).
I found this was much slower, having to request large chunks via the api.

---

### GraphManager (`core/graph_manager.py`)

Orchestrates graph loading with two-tier caching.

**Cache hierarchy:**

1. **Memory cache** - LRU with configurable capacity
2. **Disk cache** - Pickle files in `app/data/cache/`

**Key methods:**

- `get_graph(bbox)` - Main entry point
- `clear_cache()` - Invalidate memory cache
- `get_cache_info()` - Cache statistics

---

### CacheManager (`core/cache_manager.py`)

Handles disk serialisation and cache invalidation.

**Invalidation triggers:**

- `CACHE_VERSION` changes (code update)
- PBF file modified
- Processing mode changes (GREENNESS_MODE, ELEVATION_MODE, etc.)

---

## Processor Modules

### ScenicOrchestrator (`processors/orchestrator.py`)

Coordinates the scenic processing pipeline based on configuration.

**Responsibilities:**

- Read config modes (GREENNESS_MODE, WATER_MODE, SOCIAL_MODE)
- Call enabled processors in sequence
- Pass timing information to graph_manager

---

### QuietnessProcessor (`processors/quietness.py`)

Classifies highway types by expected noise level based on Wang et al. (2021) research.

**Edge attributes:**

- `noise_factor`: Classification (1.0 = noisy, 2.0 = quiet, 1.5 = neutral)
- `raw_quiet_cost`: Inverted for WSM (lower = quieter = better)

| Highway Type               | Noise Factor  |
| -------------------------- | ------------- |
| primary, trunk, motorway   | 1.0 (noisy)   |
| tertiary, unclassified     | 1.5 (neutral) |
| footway, path, residential | 2.0 (quiet)   |

---

### GreennessProcessor (`processors/greenness/`)

Calculates green space proximity/visibility scores using pluggable strategies.

**Edge attribute:** `raw_green_cost` (0.0 = very green, 1.0 = no green)

| Mode          | Algorithm                            | Speed   |
| ------------- | ------------------------------------ | ------- |
| OFF           | Skip                                 | Instant |
| FAST          | Point buffer at midpoint (30m)       | ~30s    |
| EDGE_SAMPLING | Multi-point sampling (20m intervals) | ~60s    |
| NOVACK        | Isovist ray-casting with occlusion   | ~10min  |

---

### WaterProcessor (`processors/water.py`)

Calculates proximity to water features using minimum distance scoring.

**Edge attribute:** `raw_water_cost` (0.0 = on water, 1.0 = no water within 250m)

**Water sources:** `natural=water/wetland`, `waterway=river/canal/stream`, `landuse=reservoir`

| Mode | Algorithm                    | Speed   |
| ---- | ---------------------------- | ------- |
| OFF  | Skip                         | Instant |
| FAST | Min distance to water (250m) | ~30s    |

---

### SocialProcessor (`processors/social.py`)

Calculates proximity to tourist and social POIs with distance-weighted scoring.

**Edge attribute:** `raw_social_cost` (0.0 = near POIs, 1.0 = no POIs)

**POI categories:**

- `tourism`: attraction, viewpoint, museum, artwork, gallery, picnic_site, zoo
- `historic`: castle, monument, memorial, ruins, archaeological_site, church
- `amenity`: cafe, restaurant, pub, bar, theatre, cinema, library

| Mode | Algorithm                                | Speed   |
| ---- | ---------------------------------------- | ------- |
| OFF  | Skip                                     | Instant |
| FAST | Distance-weighted POI count (50m buffer) | ~13s    |

---

### ElevationProcessor (`processors/elevation.py`)

Fetches elevation data and calculates edge gradients with Tobler's hiking function.

**Edge attributes:**

- `raw_slope_cost`: Absolute gradient (e.g. 0.05 = 5% grade)
- `uphill_gradient`, `downhill_gradient`: Directional slopes
- `tobler_cost`: Walking speed multiplier

| Mode  | Algorithm                         | Speed    |
| ----- | --------------------------------- | -------- |
| OFF   | Skip                              | Instant  |
| API   | Open Topo Data API (ASTER 30m)    | ~25min\* |
| LOCAL | Copernicus GLO-30 DEM tiles (30m) | ~3s      |

\*API rate-limited (1 req/sec); LOCAL downloads tiles once then caches

**Formula:** `raw_slope_cost = |elevation_v - elevation_u| / length`

---

### LightingProcessor (`processors/lighting.py`)

Checks OSM edge attributes for the presence of street lighting, used to penalise unlit streets at night or when user prefers lit paths.

**Edge attribute:** `lit` (string value mapped to boolean or cost)
*   **Values:** 'yes', 'no', 'none', 'disused', etc.

---

### SurfaceProcessor (`processors/surface.py`)

Evaluates edge surface attributes to classify paths as paved or unpaved, allowing routing preferences for solid ground underfoot.

**Edge attribute:** `surface` (string classification)
*   **Paved:** 'asphalt', 'paved', 'concrete', 'cobblestone', 'paving_stones', etc.
*   **Unpaved:** 'unpaved', 'dirt', 'gravel', 'ground', 'mud', 'grass', etc.

---

### RouteFinder (`routing/route_finder.py`)

A\* pathfinding with pluggable cost functions.

**Modes:**

- `use_wsm=False`: Standard A\* using `length` attribute for shortest path
- `use_wsm=True`: WSM A* using normalised scenic features with configurable weights

**Key Classes:**

- `OSMNetworkXAStar`: Distance-only pathfinding
- `WSMNetworkXAStar`: Weighted Sum Model pathfinding

---

### Loop Routing (`routing/loop_solvers/`)

Generates round-trip walking routes starting and ending at the same location without direct backtracking where possible.

**Key Components:**
- Uses internal heuristics to ensure circular variations.
- Integrates with standard RouteFinder for actual path calculation.

---

## Frontend Architecture

The user interface is powered by a modular Vanilla JS frontend using `Leaflet.js`.

**Key Elements:**
- **Navigation Rail**: A vertical, collapsible sidebar providing switching between core contexts (Routes, Admin Panel).
- **Routes Panel**: Divided into *Standard Route* (A to B) and *Round Trip* (Loop generation) tabs.
- **Advanced Options**: Configurable routing overlays and soft-avoidances (prefer lit, paved, avoid unsafe) shared globally.
- **Map Overlays**: Toggleable tile layers (Voyager, CartoDB Light/Dark) and data overlays (Street Lights mapping) integrated directly on top of Leaflet layers.

---

## User Persistence Layer

Server-side user data (accounts, saved pins, saved routes) is stored in a separate PostgreSQL database (`user_db`) on the same PostGIS container that hosts `scenic_tiles`. This isolation ensures OSM data operations cannot affect user state.

### Database Architecture

```
PostGIS Container (scenic-db)
├── scenic_tiles    ← Martin tileserver + osm2pgsql (street lighting)
└── user_db         ← Flask-SQLAlchemy ORM (users, pins, routes)
```

### ORM Models (`app/models/`)

| Model | Table | Key Columns |
|-------|-------|-------------|
| `User` | `users` | `email` (unique), `password_hash`, `created_at` |
| `SavedPin` | `saved_pins` | `user_id` (FK), `label`, `latitude`, `longitude` |
| `SavedRoute` | `saved_routes` | `user_id` (FK), `start/end_lat/lon`, `weights_json`, `route_geometry` (optional) |

### Authentication (`app/blueprints/auth.py`)

Session-based auth via Flask-Login. Passwords hashed with `werkzeug.security` (PBKDF2-SHA256).

Endpoints: `POST /auth/register`, `POST /auth/login`, `POST /auth/logout`, `GET /auth/me`

### Data CRUD (`app/blueprints/user_data.py`)

All endpoints protected by `@login_required`.

Endpoints: `GET/POST/DELETE /api/pins`, `GET/POST/DELETE /api/routes`

### Related Decisions

- [ADR-012: Dual-Database Segregation](decisions/ADR-012-dual-database-segregation.md)
- [ADR-013: Automated Database Bootstrapping](decisions/ADR-013-automated-database-bootstrapping.md)
- [ADR-014: Parametrised Route Storage](decisions/ADR-014-parametrised-route-storage.md)
- [ADR-015: Connection Pool Tuning](decisions/ADR-015-connection-pool-tuning.md)
- [ADR-016: Alembic Migration Safety](decisions/ADR-016-alembic-migration-safety.md)

---

## Configuration (`config.py`)

```python
class Config:
    DEFAULT_CITY = "Bristol, UK"
    WALKING_SPEED_KMH = 5.0
    VERBOSE_LOGGING = True

    # Greenness processing mode
    GREENNESS_MODE = 'EDGE_SAMPLING'  # OFF | FAST | EDGE_SAMPLING | NOVACK

    # Water processing mode
    WATER_MODE = 'FAST'               # OFF | FAST

    # Social POI processing mode
    SOCIAL_MODE = 'FAST'              # OFF | FAST

    # Elevation processing mode
    ELEVATION_MODE = 'LOCAL'          # OFF | API | LOCAL

    # Normalisation mode for scenic cost attributes
    NORMALISATION_MODE = 'DYNAMIC'    # STATIC | DYNAMIC

    # Cost function algorithm for scenic routing
    COST_FUNCTION = 'HYBRID_DISJUNCTIVE'  # WSM_ADDITIVE | HYBRID_DISJUNCTIVE

    # Cache capacity
    MAX_CACHED_REGIONS = 3
```

---

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         USER REQUEST                              │
│             "Clifton Suspension Bridge" → "Temple Meads"          │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                         GEOCODING                                 │
│              osmnx.geocode() → (lat, lon) coords                  │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                      GRAPH MANAGER                                │
│         Memory Cache → Disk Cache → Full Processing               │
└────────────────────────────┬─────────────────────────────────────┘
                             │ if miss
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                      DATA LOADER                                  │
│         Download PBF → Parse with pyrosm → Raw edges + nodes      │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                    WALKING FILTER                                 │
│  Prune restricted access, locked gates, private service roads     │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                   SCENIC ORCHESTRATOR                             │
│    Quietness → Greenness → Water → Social → Elevation             │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                   PROCESSED GRAPH                                 │
│  Nodes: {id, x, y, elevation, ...}                                │
│  Edges: {length, noise_factor, raw_*_cost, ...}                   │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                      ROUTE FINDER                                 │
│              A* algorithm → [node_id_1, ..., node_id_n]           │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                      MAP RENDERER                                 │
│              Folium map with route polyline                       │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                       JSON RESPONSE                               │
│     {map_html, stats: {distance_km, time_min}, debug_info}        │
└──────────────────────────────────────────────────────────────────┘
```

---

## Edge Attributes (After Processing)

All cost attributes use the convention: **lower = better for routing**.

```python
edge = G[node_u][node_v][0]

{
    # From OSM
    'length': 45.2,           # metres
    'highway': 'residential',
    'surface': 'asphalt',
    'lit': 'yes',

    # From QuietnessProcessor
    'noise_factor': 2.0,      # 1.0-5.0 (higher = noisier)

    # From GreennessProcessor (FAST mode)
    'raw_green_cost': 0.35,   # 0.0-1.0 (0 = green, 1 = no green)

    # From WaterProcessor (FAST mode)
    'raw_water_cost': 0.90,   # 0.0-1.0 (0 = water, 1 = no water)

    # From SocialProcessor (FAST mode)
    'raw_social_cost': 0.75,  # 0.0-1.0 (0 = POIs, 1 = no POIs)

    # From ElevationProcessor (FAST mode)
    'raw_slope_cost': 0.05,   # 0.0+ (0.05 = 5% grade)
}
```

---

## Performance Benchmarks (Bristol, 325K edges)

| Operation                   | Typical Time |
| --------------------------- | ------------ |
| Memory cache hit            | <1ms         |
| Disk cache hit              | ~2-5s        |
| Graph Loading               | ~16s         |
| Quietness Processing        | ~0.4s        |
| Greenness Processing (FAST) | ~45s         |
| Water Processing (FAST)     | ~26s         |
| Social Processing (FAST)    | ~13s         |
| **Total (first load)**      | **~110s**    |
| A\* route calculation       | <100ms       |

---

## WSM A\* Implementation

The Weighted Sum Model A\* extends standard pathfinding to incorporate user preferences for scenic features.

### Cost Function Algorithms

Two algorithms are available, configured via `COST_FUNCTION`:

| Algorithm            | Semantics | Formula                           | Use Case                     |
| -------------------- | --------- | --------------------------------- | ---------------------------- |
| `WSM_ADDITIVE`       | AND       | `Σ(wᵢ × normᵢ)`                   | Must be good at ALL criteria |
| `HYBRID_DISJUNCTIVE` | OR        | `w_d×l̂ + Σw_scenic × min(active)` | Good at ANY criterion        |

**Recommendation:** Use `HYBRID_DISJUNCTIVE` (default) to avoid multi-criteria collapse.

### Edge Cost Calculation

```python
# WSM A* distance_between() pseudocode
norm_length = (length - min_length) / (max_length - min_length)

# With HYBRID_DISJUNCTIVE (OR semantics):
active_scenic = [norm_green, norm_water, ...]  # Only where weight > 0
best_scenic = min(active_scenic)
cost = w_distance × norm_length + sum(w_scenic) × best_scenic
```

### Admissible Heuristic

The heuristic guarantees optimal paths:

```
h(n) = w_d × (haversine_distance / max_edge_length)
```

- **Distance bound:** Straight-line ≤ actual path (always underestimates)
- **Scenic bound:** Assumed 0 (best case, optimistic)

### Weight Normalisation

UI sliders (0–5) are converted to weights summing to 1.0:

```python
# Distance always has base weight 50 to prevent absurd detours
normalised = {
    'distance': (50 + ui_distance) / total,
    'greenness': ui_greenness / total,
    'water': ui_water / total,
    # ...
}
```

### Related Documentation

- [WSM Feature Specification](wsm_feature.md)
- [ADR-001: WSM OR-Semantics](decisions/ADR-001-wsm-or-semantics.md)
- [ADR-003: Weighted-MIN and Slider Scale](decisions/ADR-003-weighted-min-and-slider-scale.md)
