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

| Parameter                    | Type   | Default         | Description                                                                                 |
| ---------------------------- | ------ | --------------- | ------------------------------------------------------------------------------------------- |
| `use_wsm`                    | bool   | `false`         | Enable WSM routing instead of pure shortest path                                            |
| `weights`                    | object | config default  | UI-style scenic weights (`distance`, `greenness`, `water`, `quietness`, `social`, `slope`)  |
| `combine_nature`             | bool   | `false`         | Combine water + greenness in nature mode                                                    |
| `scenic_preferences_enabled` | bool   | `false`         | Frontend hint indicating scenic sliders are active                                          |
| `advanced_compare_mode`      | bool   | `false`         | Frontend hint for baseline-vs-advanced compare flow                                         |
| `prefer_separated_paths`     | bool   | `false`         | Prefer runner-oriented separated paths (tier ladder + road-avoidance penalties)             |
| `prefer_nature_trails`       | bool   | `false`         | Prefer trail-like highways and natural surfaces                                             |
| `prefer_paved_surfaces`      | bool   | `false`         | Penalize unpaved/soft surfaces by `surface=*` material class                                |
| `prefer_lit_streets`         | bool   | `false`         | Prefer explicitly lit streets or mapped streetlights                                        |
| `avoid_unlit_streets`        | bool   | `false`         | Strongly avoid unlit/unknown-lit streets ($5 \times$ cost penalty)                          |
| `avoid_unsafe_roads`         | bool   | `false`         | Penalize major roads lacking foot safety indicators                                         |
| `avoid_unclassified_lanes`   | bool   | `false`         | Strongly penalize unclassified lanes lacking foot/cycle safety cues (soft-ban, last resort) |
| `prefer_segregated_paths`    | bool   | `false`         | Bonus-only preference for `segregated=yes` edges                                            |
| `allow_quiet_service_lanes`  | bool   | `false`         | Allow low-speed service-lane fallback tier in separated mode                                |
| `travel_profile`             | string | profile default | Movement profile (`walking`, `running_easy`, `running_race`)                                |
| `speed_kmh`                  | float  | profile default | Optional speed override                                                                     |
| `activity`                   | string | derived         | Optional activity override (`walking`/`running`)                                            |

Legacy aliases accepted for backward compatibility: `prefer_dedicated_pavements`, `prefer_pedestrian`, `prefer_paved`, `prefer_lit`, `heavily_avoid_unlit`, `avoid_unclassified`.

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

### `POST /api/loop`

Calculate multiple loop (round-trip) route candidates from a single start
point.

**Request Body** (minimal):

```json
{
  "start_lat": 51.381,
  "start_lon": -2.359,
  "target_distance": 5.0
}
```

_Note:_ Supports all advanced optional parameters identical to `/api/route` (for example `prefer_separated_paths`/`prefer_nature_trails` and `prefer_lit_streets`/`avoid_unlit_streets`).

**Key Response Fields** (200):

| Field                    | Type        | Description                                                   |
| ------------------------ | ----------- | ------------------------------------------------------------- | --------- |
| `multi_loop`             | bool        | Indicates loop candidate output mode                          |
| `loops[].id`             | string      | Stable per-response id: `loop-<index>-<slug(label)>`          |
| `loops[].label`          | string      | Primary user-facing loop name                                 |
| `loops[].label_role`     | string/null | Naming role token (`best_match`, `diverse_alternative`, etc.) |
| `loops[].label_tags`     | array/null  | Compact tags showing role criteria, metrics, and settings     |
| `loops[].label_subtitle` | string/null | Compact descriptor, e.g. `South-west                          | Triangle` |
| `loops[].label_reason`   | string/null | Explainability sentence with quality/diversity metrics        |
| `loops[].metadata`       | object      | Additional algorithm metadata                                 |

**Success Response** (200, trimmed):

```json
{
  "success": true,
  "multi_loop": true,
  "loops": [
    {
      "id": "loop-1-best-match",
      "label": "Best Match",
      "label_role": "best_match",
      "label_tags": ["Quality leader", "Target delta 3.9%", "Scenic rank 1/4"],
      "label_subtitle": "South-west | Triangle",
      "label_reason": "Assigned as Best Match: highest combined quality score (0.579) with 3.9% target deviation."
    }
  ]
}
```

**Naming Scheme Reference**:

- [Loop Route Naming Scheme](../features/loop_route_naming.md) - Full logic for label assignment, subtitle/reason derivation, and id stability.

### `GET /api/cached-tiles`

Return currently loaded map tiles from cache logic.

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

## Auth Endpoints

Used for user registration and authentication.

### `POST /auth/register`

Register a new user account.

**Request Body**:

```json
{
  "email": "user@example.com",
  "password": "securepassword123"
}
```

**Response** (201):

```json
{
  "message": "Account created",
  "user": {
    "id": 1,
    "email": "user@example.com"
  }
}
```

### `POST /auth/login`

Authenticate and create a session.

**Request Body**:

```json
{
  "email": "user@example.com",
  "password": "securepassword123",
  "remember": true
}
```

**Response** (200):

```json
{
  "message": "Logged in",
  "user": {
    "id": 1,
    "email": "user@example.com"
  }
}
```

### `POST /auth/logout`

Clear the current session (requires authentication).

**Response** (200):

```json
{
  "message": "Logged out"
}
```

### `GET /auth/me`

Return the currently authenticated user's profile.

**Response** (200):

```json
{
  "user": {
    "id": 1,
    "email": "user@example.com"
  }
}
```

---

## User Data Endpoints

Requires authentication. Manages user preferences and saved locations.

### `GET /api/preferences/movement`

Return movement preferences for the currently authenticated user.

**Response** (200):

```json
{
  "preferences": {
    "walking_speed_kmh": 5.0,
    "running_easy_speed_kmh": 10.0,
    "running_race_speed_kmh": 15.0
  }
}
```

### `PATCH /api/preferences/movement`

Update movement preferences. Supports optimistic timestamp reconciliation via optional `client_updated_at`.

**Request Body**:

```json
{
  "walking_speed_kmh": 5.5
}
```

### `GET /api/pins`

List all saved pins for the current user.

**Response** (200):

```json
{
  "pins": [
    {
      "id": 1,
      "label": "Home",
      "latitude": 51.4545,
      "longitude": -2.5879,
      "created_at": "2026-04-02T12:00:00Z"
    }
  ]
}
```

### `POST /api/pins`

Save a new map pin.

**Request Body**:

```json
{
  "label": "Work",
  "latitude": 51.4545,
  "longitude": -2.5879
}
```

### `PATCH /api/pins/<pin_id>`

Update a saved pin's label.

### `DELETE /api/pins/<pin_id>`

Delete a saved pin.

### `GET /api/queries`

List all saved queries (routes) for the current user.

### `POST /api/queries`

Save a routing query.

### `DELETE /api/queries/<query_id>`

Delete a saved query.

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
