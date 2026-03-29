# API Reference

> Complete endpoint documentation for ScenicPathFinder.

---

## Base URL

- **Local**: `http://localhost:5000`
- **Docker**: `http://localhost:5000`

---

## Core Endpoints

### `GET /`

Render the main map interface.

**Response**: HTML page with interactive Leaflet map.

---

### `POST /api/geocode`

Convert an address to coordinates.

**Request Body**:

```json
{
  "address": "Bristol Temple Meads"
}
```

**Response**:

```json
{
  "lat": 51.449,
  "lon": -2.58,
  "display_name": "Bristol Temple Meads, Station Approach, Bristol"
}
```

**Errors**:
| Code | Condition |
|------|-----------|
| 400 | Missing address parameter |
| 404 | Address not found |
| 500 | Geocoding service error |

---

### `POST /api/route`

Calculate a scenic route between two points.

**Request Body** (coordinates):

```json
{
  "start_lat": 51.381,
  "start_lon": -2.359,
  "end_lat": 51.389,
  "end_lon": -2.341
}
```

**Request Body** (addresses):

```json
{
  "start_address": "UWE Bristol",
  "end_address": "Fishponds Road, Bristol"
}
```

**Request Body** (mixed):

```json
{
  "start_lat": 51.381,
  "start_lon": -2.359,
  "end_address": "Fishponds Road, Bristol"
}
```

**Optional Parameters**:

| Parameter                    | Type   | Default         | Description                                                                                |
| ---------------------------- | ------ | --------------- | ------------------------------------------------------------------------------------------ |
| `use_wsm`                    | bool   | `false`         | Enable WSM routing instead of pure shortest path                                           |
| `weights`                    | object | config default  | UI-style scenic weights (`distance`, `greenness`, `water`, `quietness`, `social`, `slope`) |
| `combine_nature`             | bool   | `false`         | Combine water + greenness in nature mode                                                   |
| `scenic_preferences_enabled` | bool   | `false`         | Frontend hint indicating scenic sliders are active                                         |
| `advanced_compare_mode`      | bool   | `false`         | Frontend hint for baseline-vs-advanced compare flow                                        |
| `prefer_pedestrian`          | bool   | `false`         | Prefer paths/trails over vehicle-focused roads                                             |
| `prefer_paved`               | bool   | `false`         | Prefer paved surfaces                                                                      |
| `prefer_lit`                 | bool   | `false`         | Prefer lit streets                                                                         |
| `heavily_avoid_unlit`        | bool   | `false`         | Strongly avoid unlit/unknown-lit streets                                                   |
| `avoid_unsafe_roads`         | bool   | `false`         | Penalize major roads lacking foot safety indicators                                        |
| `travel_profile`             | string | profile default | Movement profile (`walking`, `running_easy`, `running_race`)                               |
| `speed_kmh`                  | float  | profile default | Optional speed override                                                                    |
| `activity`                   | string | derived         | Optional activity override (`walking`/`running`)                                           |

**Success Response** (200, single route):

```json
{
  "success": true,
  "multi_route": false,
  "routes": {
    "balanced": {
      "route_coords": [
        [51.381, -2.359],
        [51.382, -2.355]
      ],
      "stats": {
        "distance_km": "2.34",
        "distance": 2.34,
        "distance_unit": "km",
        "time_min": 28
      },
      "colour": "#3B82F6",
      "route_context": {
        "subtitle": "Advanced options",
        "modifiers": ["Prefer lit streets"]
      }
    }
  },
  "start_point": [51.381, -2.359],
  "end_point": [51.389, -2.341],
  "movement": {
    "travel_profile": "walking",
    "effective_speed_kmh": 5.0,
    "distance_unit": "km"
  }
}
```

**Success Response** (200, full distinct mode):

```json
{
  "success": true,
  "multi_route": true,
  "routes": {
    "baseline": {
      "route_context": { "subtitle": "Shortest route", "modifiers": [] }
    },
    "extremist": {
      "route_context": {
        "subtitle": "Scenic emphasis",
        "modifiers": ["Prefer lit streets"]
      },
      "dominant_feature": "greenness"
    },
    "balanced": {
      "route_context": {
        "subtitle": "Custom mix",
        "modifiers": ["Prefer lit streets"]
      }
    }
  }
}
```

**Success Response** (200, advanced compare mode):

```json
{
  "success": true,
  "multi_route": true,
  "routes": {
    "baseline": {
      "route_context": { "subtitle": "Shortest route", "modifiers": [] }
    },
    "extremist": null,
    "balanced": {
      "route_context": {
        "subtitle": "Advanced options",
        "modifiers": ["Prefer paved surfaces", "Avoid unsafe roads"]
      }
    }
  }
}
```

In advanced compare mode, the baseline route is intentionally computed with all advanced modifiers disabled.

**Async Response** (202):
When `ASYNC_MODE=True` and cache miss:

```json
{
  "status": "processing",
  "task_id": "abc123-def456-...",
  "message": "Graph is being built. Poll for status."
}
```

**Errors**:
| Code | Condition |
|------|-----------|
| 400 | Missing or invalid coordinates |
| 404 | Route not found between points |
| 500 | Internal routing error |

---

## Task Endpoints

Used for async graph building when `ASYNC_MODE=True`.

### `GET /api/task/<task_id>`

Get status of an async graph build task.

**URL Parameters**:
| Parameter | Description |
|-----------|-------------|
| `task_id` | Celery task ID from `/api/route` response |

**Response** (pending):

```json
{
  "status": "pending",
  "task_id": "abc123...",
  "result": null,
  "error": null
}
```

**Response** (building):

```json
{
  "status": "building",
  "task_id": "abc123...",
  "result": {
    "region_name": "somerset",
    "stage": "scoring_greenness",
    "progress": 45
  },
  "error": null
}
```

**Response** (complete):

```json
{
  "status": "complete",
  "task_id": "abc123...",
  "result": {
    "region_name": "somerset",
    "node_count": 62581,
    "edge_count": 85234,
    "total_time": 73.2
  },
  "error": null
}
```

**Response** (failed):

```json
{
  "status": "failed",
  "task_id": "abc123...",
  "result": null,
  "error": "Error message here"
}
```

**Status Values**:
| Status | Meaning |
|--------|---------|
| `pending` | Queued, not yet started |
| `building` | Actively processing |
| `complete` | Finished successfully |
| `failed` | Error occurred |
| `unknown` | Celery unavailable |

---

### `POST /api/task/<task_id>/cancel`

Cancel a running or pending task.

**Response**:

```json
{
  "success": true,
  "task_id": "abc123...",
  "message": "Task cancellation requested"
}
```

---

## Admin Endpoints

Development and monitoring (consider adding auth for production).

### `GET /admin/`

Admin dashboard with system overview.

**Response**: HTML page with configuration, cache, and worker status.

---

### `GET /admin/tasks/active`

Get currently active Celery tasks.

**Response**:

```json
{
  "active": {
    "worker@hostname": [...]
  },
  "reserved": {},
  "scheduled": {}
}
```

---

### `GET /admin/cache`

Get cache statistics.

**Response**:

```json
{
  "memory_cache": {
    "cache_size": 2,
    "max_regions": 3,
    "current_region": "somerset",
    "cached_regions": ["somerset", "bristol"]
  },
  "disk_cache": {
    "cache_directory": "/app/data/cache",
    "cache_files": [
      {
        "filename": "somerset_edge_sampling_local_bbox_99603911_v1.5.0.pickle",
        "size_mb": 98.5,
        "modified": 1706636700.0
      }
    ]
  }
}
```

---

### `DELETE /admin/cache/<filename>`

Delete a specific cache file.

**URL Parameters**:
| Parameter | Description |
|-----------|-------------|
| `filename` | Name of the cache file to delete |

**Response**:

```json
{
  "success": true,
  "deleted": "somerset_edge_sampling_local_bbox_99603911_v1.5.0.pickle"
}
```

---

### `DELETE /admin/cache/all`

Delete all cache files.

**Response**:

```json
{
  "success": true,
  "deleted_count": 3,
  "errors": null
}
```

---

### `GET /admin/scenarios`

Get available test scenarios.

**Response**:

```json
{
  "scenarios": [
    {
      "id": "uwe-fishponds",
      "name": "UWE → Fishponds",
      "description": "Bristol local route through Stoke Park",
      "start_lat": 51.5,
      "start_lon": -2.549,
      "end_lat": 51.476,
      "end_lon": -2.524
    }
  ]
}
```

---

### `GET /admin/workers`

Get Celery worker health information.

**Response**:

```json
{
  "ping": {
    "celery@worker1": { "ok": "pong" }
  },
  "stats": {
    "celery@worker1": {
      "total": { "tasks.build_graph": 15 },
      "pool": { "max-concurrency": 4 }
    }
  },
  "registered": {
    "celery@worker1": ["tasks.build_graph"]
  }
}
```

---

### `GET /admin/config`

Get current application configuration.

**Response**:

```json
{
  "async_mode": true,
  "greenness_mode": "EDGE_SAMPLING",
  "elevation_mode": "LOCAL",
  "water_mode": "FAST",
  "social_mode": "FAST",
  "normalisation_mode": "STATIC",
  "cost_function": "WSM_ADDITIVE",
  "max_cached_regions": 3,
  "task_lock_timeout": 900,
  "celery_broker_url": "redis://redis:6379/0"
}
```

---

## Error Response Format

All errors follow this format:

```json
{
  "success": false,
  "error": "Human-readable error message"
}
```

---

## Rate Limiting

No rate limiting is currently implemented. Consider adding for production use.

---

## See Also

- [Blueprints Overview](blueprints.md) - Flask app structure
- [Docker Testing](../guides/docker_testing.md) - Testing with curl
