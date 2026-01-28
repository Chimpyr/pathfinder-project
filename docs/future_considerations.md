# Future Considerations

Potential enhancements for the ScenicPathFinder application, organised by category.

---

## Route Mode Enhancements

### Multi-Modal Travel Types

- **Current**: Walking mode implemented
- **Proposed**: Running, cycling, and wheelchair-accessible routing
- **Requires**: Speed calculations, surface preferences, elevation sensitivity adjustments
- **Complexity**: Medium

### Circular/Loop Routes

- **Proposed**: Same start/end point with a target distance
- **Use Case**: Exercise routines, dog walking, exploratory walks
- **Requires**: Distance budget constraint rather than destination node heuristic
- **Complexity**: High

---

## Additional Scenic Criteria

### Route Complexity / Turn Minimisation

- **Proposed**: Slider to favour routes with fewer turns
- **Literature**: Duckham & Kulik (2003) found shortest paths are typically complex in turns. Optimising for legibility increased travel distance by ~16% on average, a worthwhile trade-off.
- **Requires**: Turn angle computation at nodes; penalise sharp/frequent direction changes
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

---

## Priority Matrix

| Feature                       | Impact | Complexity | Priority |
| ----------------------------- | ------ | ---------- | -------- |
| GPX Export                    | Medium | Low        | 3        |
| Running/Cycling Modes         | High   | Medium     | 3        |
| Turn Minimisation             | Medium | Medium     | 2        |
| Circular Routes               | Medium | High       | 2        |
| Async Pipeline (Celery/Redis) | High   | High       | 1        |

---
