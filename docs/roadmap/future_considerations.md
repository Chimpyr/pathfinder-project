# Future Considerations

Potential extensions to ScenicPathFinder beyond the current implementation. Organised by category.

---

## Routing Enhancements

### Multi-Route Visualisation

Display 2–3 route alternatives simultaneously to help users compare trade-offs between distance efficiency and scenic quality. Baseline, balanced, and extreme routes could be shown with distinct styling.

**Complexity:** Medium | **Dependencies:** Frontend adjustments to Folium rendering

### Distance-Budget Circular Routes (Loop Mode Enhancement)

Extend loop routing to accept tighter distance constraints, allowing users to specify exact target distances (e.g., 4–6 km) rather than fixed targets. Current implementation uses smart bearing heuristics; refinement could improve route diversity.

**Complexity:** Medium | **Dependencies:** Distance-constrained A\* modifications

### Additional Scenic Criteria

- **Route Complexity**: Prefer simpler routes with fewer turns for easier navigation/memorability
- **Turn Minimisation**: Penalise sharp direction changes using Duckham & Kulik (2003) egibility principles

**Complexity:** Medium per criterion | **Dependencies:** Graph preprocessing for turn angles

---

## Travel Mode Extensions

### Running & Cycling Modes

Extend beyond walking to support:

- Running: lighter surfaces, adjusted speed/elevation sensitivity
- Cycling: surface preference, gradient tolerance, intersection frequency

**Complexity:** Medium–High | **Dependencies:** Surface classification, mode-specific scoring

### Accessibility Considerations

Wheelchair-accessible routing with surface smoothness and gradient constraints.

**Complexity:** Medium | **Dependencies:** Surface and gradient data enrichment

---

## Feature Additions

### Route Export (GPX)

Export routes as GPX files for offline navigation or sharing with Strava/Garmin.

**Complexity:** Low | **Impact:** High (user convenience)

### Path Dependency & Diversity

Track scenic features collected along a route; reduce weight for repetitive features to encourage varied exploratory journeys.

**Complexity:** High | **Dependencies:** Waypoint injection, path memory tracking

---

## Architecture & Performance

### Within-Task Parallelism

Parallelise edge scoring (green/water/quiet/social) across multiple processes. Current bounding-box clipping has reduced graphs to ~60K nodes, making parallelisation lower priority. Reconsider if:

- Routes regularly exceed 20 km
- Build time consistently exceeds 2 minutes
- Worker concurrency must be reduced

**Complexity:** High | **Estimated gain:** 20–25 seconds per cold build

---

## Completed Milestones

- ✅ **Asynchronous Graph Building** (Celery + Redis, Jan 2026)
- ✅ **Bounding-Box Clipping** (95% node reduction, 73s build time, Jan 2026)
