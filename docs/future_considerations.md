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
  | **Distance-budget A*** | Integrates with existing WSM A*; admissible heuristics possible | Requires modified goal test (distance reached, not destination) |
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
- **Literature**: Duckham, M. and Kulik, L. (2003) "Simplest" Paths: Automated Route Selection for Navigation. In: Kuhn, W., Worboys, M.F. and Timpf, S., eds. *Spatial Information Theory. Foundations of Geographic Information Science*. Berlin, Heidelberg: Springer Berlin Heidelberg, pp. 169–185.
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

### Asynchronous Graph Build Pipeline

- **Proposed**: Distributed pipeline using Celery and Redis
- **Architecture**:
  - **Graph Worker**: Offline graph construction, normalisation, caching
  - **Routing API**: Lightweight client request handling
  - **Queue**: Celery + Redis for task distribution
- **Benefits**: Decouples graph processing from routing; horizontal scaling; pre-computation
- **Deployment**: Docker containers
- **Complexity**: High

### Multithreaded Graph Building

- **Proposed**: Parallelise graph construction pipeline to utilise available compute
- **Relation to Async Pipeline**: Complements Celery/Redis architecture — workers themselves become multi-threaded
- **Parallelisation Opportunities**:
  - **PBF Parsing**: Chunk-based processing of OSM data
  - **Feature Scoring**: Independent per-edge greenness, water, social scoring
  - **Normalisation**: Per-attribute min-max scaling can run concurrently
  - **Spatial Indexing**: R-tree construction for area lookups
- **Implementation Considerations**:
  - Use `concurrent.futures.ThreadPoolExecutor` or `multiprocessing.Pool`
  - Ensure thread-safe graph mutations (or use immutable intermediate structures)
  - Profile bottlenecks before optimising (I/O vs CPU bound)
- **Refactoring Required**:
  - Clear separation of concerns in Flask app/API layer
  - Modular pipeline stages for independent execution
  - Stateless processing functions for safe parallelism
- **Complexity**: High

---

## Priority Matrix

| Feature                       | Impact | Complexity | Priority |
| ----------------------------- | ------ | ---------- | -------- |
| GPX Export                    | Medium | Low        | 3        |
| Running Mode                  | Medium | Medium     | 3        |
| Multi-Route Visualisation     | High   | Medium     | 2        |
| Turn Minimisation             | Medium | Medium     | 2        |
| Circular/Loop Routes          | Medium | High       | 2        |
| Multithreaded Graph Build     | High   | High       | 1        |
| Async Pipeline (Celery/Redis) | High   | High       | 1        |

---
