# Saved Data — Pins & Routes

This document describes the CRUD API for user-saved map pins and walking routes.

---

## Overview

Authenticated users can save two types of data:

1. **Saved Pins** — Bookmarked map locations (e.g., "My Office", "Favourite Park")
2. **Saved Routes** — Walking route configurations that can be re-loaded and re-routed

All endpoints require authentication via Flask-Login session cookies. Unauthenticated requests return `401 Unauthorized`.

---

## Saved Pins

### Data Model

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | Primary Key |
| `user_id` | FK → User | Cascade delete |
| `label` | String(100) | Max 100 chars, default "Untitled Pin" |
| `latitude` | Float | Standard float (no PostGIS geometry) |
| `longitude` | Float | |
| `created_at` | DateTime | UTC |

### API Endpoints

#### `GET /api/pins`

List all pins for the current user, ordered newest first.

**Response:**
```json
{
  "pins": [
    {
      "id": 1,
      "label": "Clifton Suspension Bridge",
      "latitude": 51.4545,
      "longitude": -2.6279,
      "created_at": "2026-02-22T17:00:00+00:00"
    }
  ]
}
```

#### `POST /api/pins`

Create a new pin.

**Request:**
```json
{
  "label": "Clifton Suspension Bridge",
  "latitude": 51.4545,
  "longitude": -2.6279
}
```

**Responses:** `201` on success, `400` on missing/invalid coordinates.

#### `DELETE /api/pins/<id>`

Delete a pin by ID. Only the owning user can delete.

**Responses:** `200` on success, `404` if not found or not owned.

---

## Saved Routes

### Data Model

| Column | Type | Notes |
|--------|------|-------|
| `id` | Integer | Primary Key |
| `user_id` | FK → User | Cascade delete |
| `name` | String(100) | Max 100 chars |
| `start_lat/lon` | Float | Always required |
| `end_lat/lon` | Float, nullable | Null for loop routes |
| `weights_json` | JSON | Full slider snapshot |
| `route_geometry` | JSON, nullable | Optional `[[lat,lon],...]` polyline |
| `distance_km` | Float, nullable | Approximate distance at time of save |
| `is_loop` | Boolean | `true` for round-trip routes |
| `created_at` | DateTime | UTC |

### Storage Strategy

Routes are stored using a **parametrised** approach by default — only the input parameters are saved (see [ADR-014](../decisions/ADR-014-parametrised-route-storage.md)). When re-loaded, the frontend re-submits these parameters to get a fresh route using the latest graph data.

If the user explicitly "pins" a result, the optional `route_geometry` column stores the exact polyline for deterministic recall.

### API Endpoints

#### `GET /api/routes`

List all saved routes for the current user, ordered newest first.

**Response:**
```json
{
  "routes": [
    {
      "id": 1,
      "name": "Evening Walk",
      "start_lat": 51.454,
      "start_lon": -2.627,
      "end_lat": 51.449,
      "end_lon": -2.580,
      "weights": {"distance": 1, "greenness": 3, "water": 2},
      "has_geometry": false,
      "distance_km": 4.2,
      "is_loop": false,
      "created_at": "2026-02-22T17:00:00+00:00"
    }
  ]
}
```

#### `POST /api/routes`

Save a new route configuration.

**Request:**
```json
{
  "name": "Evening Walk",
  "start_lat": 51.454,
  "start_lon": -2.627,
  "end_lat": 51.449,
  "end_lon": -2.580,
  "weights": {"distance": 1, "greenness": 3},
  "route_geometry": [[51.454, -2.627], [51.452, -2.610], ...],
  "distance_km": 4.2,
  "is_loop": false
}
```

**Required fields:** `start_lat`, `start_lon`  
**Optional fields:** `end_lat/lon` (null for loops), `weights`, `route_geometry`, `distance_km`, `is_loop`

**Responses:** `201` on success, `400` on missing/invalid data.

#### `DELETE /api/routes/<id>`

Delete a saved route. Only the owning user can delete.

**Responses:** `200` on success, `404` if not found or not owned.

---

## Cross-Domain Data Aggregation

SQLAlchemy cannot JOIN across different database binds (`user_db` vs `scenic_tiles`). Any logic that compares user pins against routing spatial data (e.g., "find saved pins near my current route") must be handled in the Python application layer:

```python
# Example: filter user pins within bounding box of current route
user_pins = SavedPin.query.filter_by(user_id=current_user.id).all()
nearby = [p for p in user_pins if route_bbox.contains(p.latitude, p.longitude)]
```

This is documented in [ADR-012](../decisions/ADR-012-dual-database-segregation.md).

---

## Related Documentation

- [User Accounts & Authentication](user_accounts.md)
- [ADR-014: Parametrised Route Storage](../decisions/ADR-014-parametrised-route-storage.md)
- [ADR-012: Dual-Database Segregation](../decisions/ADR-012-dual-database-segregation.md)
