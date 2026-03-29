# Street Lighting Routing Bias

This document covers the routing toggles in Advanced Options:

- Prefer lit streets
- Heavily avoid unlit streets

It explains how these toggles use council-enriched graph lighting data.

---

## Overlay Versus Routing Data Paths

Street lighting has two separate consumers:

- Visual overlay: PostGIS + Martin vector tiles (`street_lighting`, `street_lighting_filtered`)
- Routing penalties: in-memory NetworkX graph attributes used by WSM A\*

The routing toggles do not query PostGIS at runtime.

---

## Routing Lighting Pipeline (Visual)

```
OSM PBF
  -> OSMDataLoader.load_graph(...)
  -> pyrosm get_network(extra_attributes includes 'lit')
  -> base graph edges have OSM lit values when present
  -> Scenic orchestrator (process_scenic_attributes)
  -> loader.extract_streetlights() reads combined_streetlights.gpkg
  -> process_graph_streetlights(...)
     - snaps council points to nearby edges (default 15m)
     - sets edge.lit = 'yes'
     - sets edge.lit_source = 'council'
     - sets edge.lit_source_detail = source name
  -> graph cached/served to RouteFinder
  -> WSMNetworkXAStar._compute_lit_multiplier(edge.lit)
```

Important behaviour:

- Routing decisions key off edge `lit` values.
- Council augmentation changes `lit` to `yes` on matched edges.
- Provenance fields (`lit_source`, `lit_source_detail`) are stored for transparency but are not directly used by cost multipliers.

---

## Lit Multiplier Mechanism

Both toggles apply a multiplicative modifier after base WSM edge cost:

```
edge_cost = wsm_cost(...) * lit_multiplier(edge.lit)
```

This keeps lighting orthogonal to WSM weight sliders.

### Prefer Lit Streets

| `lit` value                | Multiplier |
| -------------------------- | ---------- |
| `yes`, `automatic`, `24/7` | x 0.85     |
| `limited`, `disused`       | x 1.3      |
| `no`                       | x 1.8      |
| unknown or missing         | x 1.2      |

### Heavily Avoid Unlit Streets

| `lit` value                                          | Multiplier |
| ---------------------------------------------------- | ---------- |
| `yes`, `automatic`, `24/7`                           | x 0.70     |
| `limited`, `disused`                                 | x 2.5      |
| `no`                                                 | x 5.0      |
| unknown or missing (street roads)                    | x 3.0      |
| unknown or missing (dedicated path/cycleway/footway) | x 1.0      |

Heavy mode always takes precedence when both booleans are present.

Note: unknown lighting on dedicated active-travel corridors (`cycleway`,
`path`, `footway`, `pedestrian`, `track`, `bridleway`, `steps`) is treated
as neutral to avoid over-penalising unmapped but commonly used paths.

---

## Point-To-Point Flow

```
POST /api/route
  -> app/routes.py parses prefer_lit and heavily_avoid_unlit
  -> RouteFinder.find_route(...)
  -> WSMNetworkXAStar(..., prefer_lit=..., heavily_avoid_unlit=...)
  -> distance_between() applies _compute_lit_multiplier per edge
```

In multi-route mode (`find_distinct_paths`):

- Baseline route intentionally disables lit penalties.
- Extremist and balanced routes forward user lighting toggles.

In advanced compare mode (scenic sliders off + advanced options on):

- Baseline route is computed with all advanced modifiers disabled.
- Advanced route is computed with enabled advanced modifiers (including lighting).
- Response contains `baseline` and `balanced` entries (`extremist` is `null`).

---

## Loop Flow

```
POST /api/loop
  -> app/routes.py parses prefer_lit and heavily_avoid_unlit
  -> RouteFinder.find_loop_route(...)
  -> LoopSolverFactory.create() (default algorithm: GEOMETRIC)
  -> Geometric solver routes each leg via WSMNetworkXAStar(...)
  -> lit multiplier applied per edge inside WSM A*
```

Lighting does not directly choose bearings. It influences routed leg cost,
which can indirectly change geometric feedback outcomes (for example tau
updates when detours increase leg lengths).

---

## Logging

When active, the stack logs mode selection:

```
[WSM A*] Using cost function: wsm_or, lit_mode: prefer_lit
[WSM A*] Using cost function: wsm_or, lit_mode: heavily_avoid_unlit
[GeometricSolver] Lit mode: prefer_lit
[GeometricSolver] Lit mode: heavily_avoid_unlit
```

---

## Test Coverage

Current automated tests relevant to this feature:

- `tests/test_streetlights_processor.py`
- `tests/test_street_lighting_routing_integration.py`
- `tests/test_distinct_paths.py` (baseline route purity for lit and other advanced toggles)

Full testing plan and manual QA scenarios are documented in:

- `docs/testing/street_lighting_test_suite.md`

---

## Implementation Files

| File                                                    | Role                                                                          |
| ------------------------------------------------------- | ----------------------------------------------------------------------------- |
| `app/services/core/data_loader.py`                      | Loads `lit` from OSM and extracts council point dataset                       |
| `app/services/processors/orchestrator.py`               | Enables streetlight processing stage (`STREETLIGHT_MODE`)                     |
| `app/services/processors/streetlights.py`               | Snaps council points and promotes matched edges to `lit='yes'`                |
| `app/services/routing/astar/wsm_astar.py`               | Multiplier tables and `_compute_lit_multiplier` application                   |
| `app/services/routing/route_finder.py`                  | Forwards toggles to A\* and loop solvers                                      |
| `app/services/routing/distinct_paths_runner.py`         | Applies toggle forwarding rules across 3-route strategy                       |
| `app/services/routing/loop_solvers/geometric_solver.py` | Propagates toggle state through loop leg routing                              |
| `app/routes.py`                                         | Parses `prefer_lit` / `heavily_avoid_unlit` from `/api/route` and `/api/loop` |
| `app/static/js/modules/routing_ui.js`                   | Toggle wiring, payload construction, mutual exclusivity in UI                 |
| `app/templates/index.html`                              | Advanced Options toggle controls                                              |
