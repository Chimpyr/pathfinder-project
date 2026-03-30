# Future Considerations

Potential enhancements for the ScenicPathFinder application, organised by category.

---

## Visualisation Enhancements

### Multi-Route Visualisation

- **Proposed**: Display three distinct route alternatives simultaneously for comparison
- **Route Variants**:
  1. **Baseline Route**: Weights = `{Distance: 1.0, Others: 0}` — pure shortest path
  2. **Extremist Route**: Weights = `{User_Max_Constraint: 1.0, Distance: 0.1, Others: 0}` — finds the "greenest" (or highest-scored criterion) regardless of length
  3. **Balanced Route**: Weights = `{User Input Values}` — current user-configured preferences
- **Implementation**:
  - Update Folium/Leaflet logic to render three distinct polylines with different colours/styles
  - Return JSON object containing three separate route geometries and their stats
  - Add legend or toggle control to show/hide individual layers
- **Use Case**: Helps users understand trade-offs between efficiency and scenic quality
- **Complexity**: Medium

---

## Route Mode Enhancements

### Multi-Modal Travel Types

- **Current**: Walking mode implemented
- **Proposed**: Running, cycling, and wheelchair-accessible routing
- **Requires**: Speed calculations, surface preferences, elevation sensitivity adjustments
- **Complexity**: Medium

### Running Mode (Priority Extension)

- **Proposed**: Dedicated running travel type as first extension beyond walking
- **Considerations**:
  - **Speed**: Average running pace (5–6 min/km) affects time estimates
  - **Surface Preference**: Runners may prefer softer surfaces (trails, grass) over concrete
  - **Elevation Sensitivity**: Uphill/downhill gradients impact effort differently for running
  - **Safety**: Well-lit paths, pavement condition, crossing frequency
  - **Loop Preference**: Runners often prefer circular routes back to start
- **Requires**: Surface type scoring, adjusted speed calculations, potential safety criteria
- **Complexity**: Medium

### Circular/Loop Routes

- **Proposed**: Same start/end point with a target distance
- **Use Case**: Exercise routines, dog walking, exploratory walks
- **Implementation Considerations**:
  - User selects "Loop Mode" and specifies preferred distance (e.g., 5km)
  - Algorithm finds route satisfying scenic preferences within distance tolerance (e.g., 4–8km)
  - Route may be shorter/longer than target if higher scenic scores justify deviation
  - Sliders continue to influence the balance between distance accuracy and scenic quality
- **Algorithm Options**:
  | Algorithm | Pros | Cons |
  |-----------|------|------|
  | **Christofides TSP variant** | Guarantees return to origin; well-studied | Designed for visiting waypoints, not distance budgets |
  | **Constrained random walk** | Simple; naturally explores area | No optimality guarantees; may miss scenic areas |
  | **Distance-budget A\*** | Integrates with existing WSM A*; admissible heuristics possible | Requires modified goal test (distance reached, not destination) |
  | **Two-phase (outbound + return)** | Reuses existing A*; simpler implementation | May produce suboptimal loops; backtracking risk |
- **Requires**: Distance budget constraint rather than destination node heuristic; modified termination condition
- **Complexity**: High

---

## Additional Scenic Criteria

### Route Complexity / Turn Minimisation

- **Proposed**: Slider (0–9 scale) to control route complexity preference
- **Behaviour**:
  - **0 (Simple)**: Favour routes with fewer turns, straighter roads, cognitively simpler paths (easier to remember/follow)
  - **9 (Complex)**: Ignores complexity weighting; does not penalise turns or direction changes
- **Literature**: Duckham, M. and Kulik, L. (2003) "Simplest" Paths: Automated Route Selection for Navigation. In: Kuhn, W., Worboys, M.F. and Timpf, S., eds. _Spatial Information Theory. Foundations of Geographic Information Science_. Berlin, Heidelberg: Springer Berlin Heidelberg, pp. 169–185.
  - Key Finding: Shortest paths are typically complex in turns; optimising for legibility increased travel distance by ~16% on average — a worthwhile trade-off for navigation clarity
- **Implementation**:
  - Compute turn angles at graph nodes
  - Penalise sharp turns (>90°) and frequent direction changes
  - Integrate as additional cost component in WSM
- **Complexity**: Medium

---

## Export & Sharing

### GPX Route Export

- **Proposed**: Export routes as GPX files
- **Use Case**: Offline navigation, sharing with Strava/Garmin
- **Requires**: Serialise coordinates with metadata (distance, elevation, scenic scores)
- **Complexity**: Low

---

## Architecture & Scalability

### Asynchronous Graph Build Pipeline ✅

- **Status**: ✅ Implemented (2026-01-30)
- **Architecture**:
  - **Graph Worker**: Celery worker with 4 concurrent processes
  - **Routing API**: Flask API with async polling
  - **Queue**: Redis for task distribution and result backend
- **Benefits**: Decouples graph processing; 4 concurrent builds; non-blocking UI
- **Deployment**: Docker Compose (api, worker, redis containers)
- **Documentation**: [Celery Redis Architecture](../architecture/celery_redis_architecture.md)

### Bounding Box Clipping at Load Time ✅

- **Status**: ✅ Implemented (2026-01-30)
- **Result**: 95% reduction in nodes loaded (1.1M → 62K)
- **Implementation**:
  - 5km buffer around route bbox
  - Bbox hash in cache key for per-route caching
  - 73s build time (was 15 min), ~1GB RAM (was 12GB)
- **Documentation**: [ADR-004](../decisions/ADR-004-bbox-clipping.md), [Performance Strategy](../architecture/performance_strategy.md)

### Within-Task Parallelism (Deferred)

- **Status**: 🔶 Deferred — Low ROI after bbox clipping
- **Proposed**: Parallelise edge scoring (green/water/quiet) across 4 processes
- **Expected Gain**: ~20-25 seconds per cold build (73s → ~50s)
- **Why Deferred**:
  - Bbox clipping reduced graphs to ~60K nodes — scoring is now fast enough
  - Cache hits are 2 seconds — most users don't wait for builds
  - Complexity cost (~100 lines, subprocess management) outweighs benefit
  - 4 concurrent workers already handle throughput well
- **Reconsider If**:
  - Routes regularly exceed 20km (larger graphs)
  - Build time exceeds 2 minutes
  - Worker concurrency must be reduced for memory
- **Parallelisation Opportunities** (if implemented):
  - **Feature Scoring**: Independent per-edge greenness, water, social scoring
  - **Spatial Queries**: Can batch edge lookups to STRtree
- **Implementation Sketch**:

  ```python
  from concurrent.futures import ProcessPoolExecutor

  def score_batch(edges_batch, green_index):
      return {(u,v): calc_greenness(data) for u,v,data in edges_batch}

  with ProcessPoolExecutor(max_workers=4) as executor:
      results = executor.map(score_batch, edge_batches)
  ```

- **Complexity**: High

---

## Priority Matrix

| Feature                       | Impact | Complexity | Priority | Status         |
| ----------------------------- | ------ | ---------- | -------- | -------------- |
| Async Pipeline (Celery/Redis) | High   | High       | 1        | ✅ Implemented |
| Bbox Clipping                 | High   | Medium     | 1        | ✅ Implemented |
| Within-Task Parallelism       | Low    | High       | —        | 🔶 Deferred    |
| Multi-Route Visualisation     | High   | Medium     | 2        | Pending        |
| Turn Minimisation             | Medium | Medium     | 2        | Pending        |
| Circular/Loop Routes          | Medium | High       | 2        | Pending        |
| GPX Export                    | Medium | Low        | 3        | Pending        |
| Running Mode                  | Medium | Medium     | 3        | Pending        |

---
