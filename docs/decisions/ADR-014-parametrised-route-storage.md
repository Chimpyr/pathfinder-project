# ADR-014: Parametrised Route Storage Strategy

**Status:** Accepted  
**Date:** 2026-02-22

---

## Context

When a user saves a walking route, the system must decide *what* to persist. There are two fundamentally different approaches, each with significant UX and technical trade-offs.

### The Core Question

> If a user saves a route today and retrieves it in 3 months, should they see the **exact same polyline** or a **re-calculated route** using the same preferences?

This distinction matters because the underlying OpenStreetMap data and graph weights can change between save and retrieval — roads close, footpaths are added, and scenic scores shift as new green areas or POIs are mapped.

---

## Decision

**Adopt a hybrid strategy: Parametrised by default (Option A) with optional deterministic geometry (Option B).**

### Option A — Parametrised (Default)

Store only the inputs needed to reproduce the route:

| Column | Purpose |
|--------|---------|
| `start_lat`, `start_lon` | Origin coordinates |
| `end_lat`, `end_lon` | Destination (nullable for loops) |
| `weights_json` | Full slider/preference snapshot |
| `is_loop` | Whether this was a round-trip route |

When the user requests a saved route, the frontend re-submits these parameters to the routing API, which computes a fresh route using the latest graph data.

### Option B — Deterministic Geometry (Optional)

When the user explicitly "pins" a specific route result, the system additionally stores:

| Column | Purpose |
|--------|---------|
| `route_geometry` | JSON array of `[[lat, lon], ...]` coordinate pairs |

This allows the frontend to render the exact polyline without re-routing, immune to underlying graph changes.

### Why Not Node IDs?

The specification mentioned storing OSM node IDs for deterministic recall. This was rejected because:

1. **Node IDs are unstable** — OSM node IDs change when mappers split or merge ways, making stored ID sequences invalid
2. **Node IDs are graph-version-dependent** — Our graph's internal node IDs may differ across cache rebuilds
3. **Coordinate polylines are universal** — Lat/lon pairs can be rendered by any mapping library without needing the routing graph

---

## Consequences

### Positive

- **Always up-to-date** — Parametrised routes benefit from improved OSM data and algorithm updates
- **Storage efficient** — Storing 5 floats + a JSON blob is far smaller than a full multi-hundred-point polyline
- **Determinism when needed** — Optional `route_geometry` satisfies users who want exact recall
- **Loop-compatible** — Loop routes (no end point) are naturally represented with `end_lat=NULL`

### Negative

- **Route drift** — A parametrised route retrieved months later may follow a different physical path if OSM data changed
- **Expectation mismatch** — Users may expect "saved route" to mean "exact same path", not "same parameters"
- **Latency on retrieval** — Parametrised routes require re-computation (A* search), adding ~100ms per retrieval vs instant geometry rendering

### Mitigations

- The `route_geometry` column provides an escape hatch for users who need exact physical recall
- The `distance_km` metadata field lets the UI warn users if a re-routed result differs significantly from the original

---

## Alternatives Considered

1. **Always store full geometry** — Every save includes the polyline. Rejected because it prevents users from benefiting from OSM data improvements, and significantly increases storage requirements.

2. **Store OSM node ID sequences** — Rejected due to node ID instability across OSM edits and graph rebuilds (detailed above).

3. **Store graph edge sequences** — Store `(u, v, key)` tuples. Rejected for the same instability reasons as node IDs, plus tight coupling to the specific graph version.

4. **Versioned graphs with route replay** — Store a graph version hash alongside node IDs, and replay routes against the matching cached graph. Rejected due to extreme storage overhead (keeping every historical graph version) and implementation complexity.

---

## Schema

```python
class SavedRoute(db.Model):
    start_lat  = db.Column(db.Float, nullable=False)
    start_lon  = db.Column(db.Float, nullable=False)
    end_lat    = db.Column(db.Float, nullable=True)   # NULL for loop routes
    end_lon    = db.Column(db.Float, nullable=True)
    weights_json     = db.Column(db.JSON, nullable=True)
    route_geometry   = db.Column(db.JSON, nullable=True)  # Optional
    distance_km      = db.Column(db.Float, nullable=True)
    is_loop          = db.Column(db.Boolean, default=False)
```

---

## Files Modified

| File | Changes |
|------|---------|
| `app/models/saved_route.py` | **[NEW]** SavedRoute model with hybrid storage |
| `.\app\blueprints\user_data.py` | **[NEW]** CRUD endpoints accepting both parametrised and geometry data |

---

## References

- [ADR-012: Dual-Database Segregation](ADR-012-dual-database-segregation.md) — Where saved routes are stored
- [OSM Node ID stability](https://wiki.openstreetmap.org/wiki/Node#Lifecycle) — Why node IDs are unreliable for long-term storage
