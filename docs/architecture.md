# ScenicPathFinder - System Architecture

Complete technical documentation of the pedestrian routing engine.

---

## Overview

ScenicPathFinder is a pedestrian routing engine that calculates walking routes with support for weighted multi-criteria pathfinding (quietness, greenness, etc.).

```
User Input → Geocoding → Region Detection → Graph Loading → A* Routing → Map Display
```

---

## Directory Structure

```
ScenicPathFinder/
├── app/
│   ├── services/           # Core business logic
│   │   ├── cache_manager.py      # Disk caching (pickle)
│   │   ├── data_loader.py        # PBF download + parsing
│   │   ├── graph_manager.py      # Two-tier cache orchestration
│   │   ├── quietness_processor.py # Highway noise classification
│   │   ├── visibility_processor.py # Green/scenic scoring
│   │   ├── route_finder.py       # A* pathfinding
│   │   └── map_renderer.py       # Folium map generation
│   ├── routes.py           # Flask endpoints
│   ├── templates/          # HTML templates
│   └── data/               # Downloaded PBF files + cache
├── config.py               # Application settings
├── run.py                  # Entry point
└── docs/                   # Documentation
```

---

## Request Flow

### 1. User Input

User enters start/end locations (addresses or postcodes).

```
POST / 
  start: "pl34 0dt"
  end: "Tintagel Castle"
```

### 2. Geocoding

`routes.py` uses **osmnx** to convert addresses to coordinates:

```python
start_point = ox.geocode("pl34 0dt")  # → (50.657, -4.750)
end_point = ox.geocode("Tintagel Castle")  # → (50.669, -4.762)
```

### 3. Bounding Box Calculation

A buffer (~2km) is added around the route endpoints:

```python
bbox = (min_lat - 0.02, min_lon - 0.02, max_lat + 0.02, max_lon + 0.02)
```

### 4. Region Detection

`GraphManager` identifies the correct OSM extract:

```python
region_name = "cornwall"  # From Geofabrik index
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

### OSMDataLoader (`data_loader.py`)

Downloads and parses OpenStreetMap data.

**Key methods:**
- `load_graph(bbox)` - Parse PBF to NetworkX graph
- `extract_green_areas()` - Parks, forests (→ GeoDataFrame)
- `extract_buildings()` - Building polygons for occlusion
- `extract_water()` - Rivers, lakes for scenic scoring

**Data source:** Geofabrik regional extracts (e.g., `cornwall.osm.pbf`)

---

### GraphManager (`graph_manager.py`)

Orchestrates graph loading with two-tier caching.

**Cache hierarchy:**
1. **Memory cache** - LRU with configurable capacity
2. **Disk cache** - Pickle files in `app/data/cache/`

**Key methods:**
- `get_graph(bbox)` - Main entry point
- `clear_cache()` - Invalidate memory cache
- `get_cache_info()` - Cache statistics

---

### CacheManager (`cache_manager.py`)

Handles disk serialisation and cache invalidation.

**Invalidation triggers:**
- `CACHE_VERSION` changes (code update)
- PBF file modified
- `GREENNESS_MODE` changes

---

### QuietnessProcessor (`quietness_processor.py`)

Classifies highway types by expected noise level.

**Edge attribute:** `noise_factor` (1.0 = quiet, 5.0 = noisy)

| Highway Type | Noise Factor |
|--------------|--------------|
| footway, path | 1.0 |
| residential | 2.0 |
| primary, trunk | 5.0 |

---

### VisibilityProcessor (`visibility_processor.py`)

Calculates green/scenic visibility scores.

**Modes:**

| Mode | Algorithm | Edge Attributes |
|------|-----------|-----------------|
| OFF | Skip | (none) |
| FAST | 30m buffer intersection | `scenic_score`, `green_proximity_score`, `water_proximity_score` |
| NOVACK | Isovist ray-casting | `green_visibility_score` |

---

### ElevationProcessor (`elevation_processor.py`)

Fetches elevation data and calculates edge gradients.

**Modes:**

| Mode | Algorithm | Edge Attributes |
|------|-----------|-----------------|
| OFF | Skip | (none) |
| FAST | Open Topo Data API (ASTER30m) | `raw_slope_cost` |

**Formula:** `raw_slope_cost = |elevation_v - elevation_u| / length`

---

### RouteFinder (`route_finder.py`)

A* pathfinding using edge weights.

**Current:** Uses `length` attribute for shortest path.

**Future (WSM A Star):** Will combine multiple criteria:
```python
cost = w1 * length + w2 * noise_factor + w3 * scenic_score
```

---

## Configuration (`config.py`)

```python
class Config:
    DEFAULT_CITY = "Bristol, UK"
    WALKING_SPEED_KMH = 5.0
    VERBOSE_LOGGING = True
    
    # Scenic processing mode
    GREENNESS_MODE = 'FAST'  # OFF | FAST | NOVACK
    
    # Elevation processing mode
    ELEVATION_MODE = 'FAST'  # OFF | FAST
    
    # Cache capacity
    MAX_CACHED_REGIONS = 3
```

---

## Data Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                         USER REQUEST                              │
│                    "pl34 0dt" → "Tintagel"                        │
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
│                   ATTRIBUTE PROCESSORS                            │
│         Quietness (noise_factor) + Visibility (scenic_score)      │
└────────────────────────────┬─────────────────────────────────────┘
                             │
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│                   PROCESSED GRAPH                                 │
│  Nodes: {id, x, y, ...}                                           │
│  Edges: {length, highway, noise_factor, scenic_score, ...}        │
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

```python
edge = G[node_u][node_v][0]

{
    # From OSM
    'length': 45.2,           # metres
    'highway': 'residential',
    'surface': 'asphalt',
    'lit': 'yes',
    
    # From QuietnessProcessor
    'noise_factor': 2.0,      # 1.0-5.0
    
    # From VisibilityProcessor (FAST mode)
    'green_proximity_score': 0.35,   # 0.0-1.0
    'water_proximity_score': 0.10,   # 0.0-1.0
    'scenic_score': 0.28,            # weighted combination
    
    # From ElevationProcessor (FAST mode)
    'raw_slope_cost': 0.05,          # 0.0+ (0.05 = 5% grade)
}
```

---

## Performance Benchmarks

| Operation | Typical Time |
|-----------|--------------|
| Memory cache hit | <1ms |
| Disk cache hit | ~2-5s |
| Full processing (Cornwall, 1.7M edges) | ~355s |
| A* route calculation | <100ms |

---

## Future: WSM A* Integration

The edge attributes (`noise_factor`, `scenic_score`, etc.) are designed for use in a **Weighted Sum Model** A* implementation:

```python
# User sets weights via UI sliders
weights = {
    'distance': 0.5,
    'quietness': 0.3,
    'greenness': 0.2
}

# Edge cost calculation
cost = (weights['distance'] * edge['length'] +
        weights['quietness'] * edge['length'] / edge['noise_factor'] +
        weights['greenness'] * edge['length'] / (edge['scenic_score'] + 0.5))
```

This enables personalised routing: "shortest but avoiding main roads with preference for parks".
