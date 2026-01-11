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
│   │   │   └── graph_manager.py     # Two-tier cache orchestration
│   │   │
│   │   ├── processors/              # Edge attribute processors
│   │   │   ├── greenness.py         # Green visibility (FAST/NOVACK)
│   │   │   ├── water.py             # Water proximity scoring
│   │   │   ├── social.py            # POI proximity scoring
│   │   │   ├── elevation.py         # Gradient calculation
│   │   │   ├── quietness.py         # Highway noise classification
│   │   │   └── orchestrator.py      # Scenic pipeline coordinator
│   │   │
│   │   ├── routing/                 # Pathfinding
│   │   │   ├── route_finder.py      # A* pathfinding wrapper
│   │   │   └── astar/               # Custom A* implementation
│   │   │
│   │   └── rendering/               # Map output
│   │       └── map_renderer.py      # Folium map generation
│   │
│   ├── routes.py                    # Flask endpoints
│   ├── templates/                   # HTML templates
│   └── data/                        # Downloaded PBF files + cache
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

`RouteFinder` uses A* algorithm to find optimal path:

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

Classifies highway types by expected noise level.

**Edge attribute:** `noise_factor` (1.0 = quiet, 5.0 = noisy)

| Highway Type | Noise Factor |
|--------------|--------------|
| footway, path | 1.0 |
| residential | 2.0 |
| primary, trunk | 5.0 |

---

### GreennessProcessor (`processors/greenness.py`)

Calculates green space proximity/visibility scores.

**Edge attribute:** `raw_green_cost` (0.0 = very green, 1.0 = no green)

| Mode | Algorithm | Speed |
|------|-----------|-------|
| OFF | Skip | Instant |
| FAST | 30m buffer intersection | ~45s |
| NOVACK | Isovist ray-casting | ~10min |

---

### WaterProcessor (`processors/water.py`)

Calculates proximity to water features.

**Edge attribute:** `raw_water_cost` (0.0 = near water, 1.0 = no water)

| Mode | Algorithm | Speed |
|------|-----------|-------|
| OFF | Skip | Instant |
| FAST | 30m buffer intersection | ~26s |

---

### SocialProcessor (`processors/social.py`)

Calculates proximity to tourist and social POIs.

**Edge attribute:** `raw_social_cost` (0.0 = near POIs, 1.0 = no POIs)

**POI categories:**
- `tourism`: attraction, viewpoint, museum, artwork, gallery
- `historic`: castle, monument, memorial, ruins
- `amenity`: cafe, restaurant, pub, theatre, cinema

| Mode | Algorithm | Speed |
|------|-----------|-------|
| OFF | Skip | Instant |
| FAST | 50m buffer intersection | ~13s |

---

### ElevationProcessor (`processors/elevation.py`)

Fetches elevation data and calculates edge gradients.

**Edge attribute:** `raw_slope_cost` (absolute gradient, e.g. 0.05 = 5% grade)

| Mode | Algorithm | Speed |
|------|-----------|-------|
| OFF | Skip | Instant |
| FAST | Open Topo Data API (ASTER30m) | ~25min* |

*Rate-limited by free API tier (1 req/sec)

**Formula:** `raw_slope_cost = |elevation_v - elevation_u| / length`

---

### RouteFinder (`routing/route_finder.py`)

A* pathfinding using edge weights.

**Current:** Uses `length` attribute for shortest path.

**Future (WSM A*):** Will combine multiple criteria with user-configurable weights.

---

## Configuration (`config.py`)

```python
class Config:
    DEFAULT_CITY = "Bristol, UK"
    WALKING_SPEED_KMH = 5.0
    VERBOSE_LOGGING = True
    
    # Greenness processing mode
    GREENNESS_MODE = 'FAST'  # OFF | FAST | NOVACK
    
    # Water processing mode
    WATER_MODE = 'FAST'      # OFF | FAST
    
    # Social POI processing mode
    SOCIAL_MODE = 'FAST'     # OFF | FAST
    
    # Elevation processing mode
    ELEVATION_MODE = 'OFF'   # OFF | FAST
    
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
│         Download PBF → Parse with pyrosm → NetworkX Graph         │
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

| Operation | Typical Time |
|-----------|--------------|
| Memory cache hit | <1ms |
| Disk cache hit | ~2-5s |
| Graph Loading | ~16s |
| Quietness Processing | ~0.4s |
| Greenness Processing (FAST) | ~45s |
| Water Processing (FAST) | ~26s |
| Social Processing (FAST) | ~13s |
| **Total (first load)** | **~110s** |
| A* route calculation | <100ms |

---

## Future: WSM A* Integration

The edge attributes (`noise_factor`, `raw_*_cost`) are designed for use in a **Weighted Sum Model** A* implementation:

```python
# User sets weights via UI sliders
weights = {
    'distance': 0.4,
    'quietness': 0.2,
    'greenness': 0.2,
    'water': 0.1,
    'social': 0.1
}

# Edge cost calculation (lower cost = preferred)
cost = (weights['distance'] * edge['length'] +
        weights['quietness'] * edge['length'] / edge['noise_factor'] +
        weights['greenness'] * edge['length'] * edge['raw_green_cost'] +
        weights['water'] * edge['length'] * edge['raw_water_cost'] +
        weights['social'] * edge['length'] * edge['raw_social_cost'])
```

This enables personalised routing: "shortest but avoiding main roads with preference for parks and waterfront".
