# ADR-021: Advanced Options Activation and Baseline Compare Mode

**Status:** Accepted
**Date:** 2026-03-29

## Context

Users reported three related issues in standard routing:

1. Advanced options appeared ineffective unless Scenic Preferences (slider-based weights) were enabled.
2. It was unclear which advanced options actually influenced each returned route.
3. There was no explicit baseline route for comparison when users only enabled advanced toggles.

Root cause:

- Frontend request construction only activated WSM reliably when scenic sliders were active.
- Advanced modifiers were not consistently surfaced in response metadata.
- Distinct-route behavior and advanced-only behavior were not aligned around an explicit baseline-vs-modified comparison.

## Decision

### 1. Decouple advanced options from scenic slider activation

Advanced toggles are treated as first-class routing modifiers.

- If scenic sliders are enabled, advanced options are applied on top of scenic weighting.
- If scenic sliders are disabled but advanced options are enabled, backend still executes a WSM path for advanced modifiers.

### 2. Introduce advanced compare mode for scenic-off workflows

When scenic sliders are off and advanced toggles are on, standard route responses use compare semantics:

- `baseline`: shortest route with all advanced modifiers disabled.
- `balanced`: advanced route with selected advanced modifiers applied.
- `extremist`: explicitly `null` in this mode.

This preserves interpretability and always gives users an unmodified reference route.

### 3. Add route-context attribution metadata

Each returned route includes `route_context`:

- `subtitle` (for example `Shortest route`, `Custom mix`, `Advanced options`)
- `modifiers` (human-readable list of active advanced toggles)

Frontend route cards render this metadata so users can see which options contributed to each route.

### 4. Extend WSM advanced modifier coverage

WSM edge-cost multipliers were expanded so advanced options are complete and consistent:

- `prefer_dedicated_pavements` / `prefer_nature_trails`: surface-based penalties for unpaved/soft terrain.
- `avoid_unsafe_roads`: heavy penalties for major roads lacking sidewalk/foot indicators.

To support unsafe-road logic, graph extraction explicitly retains `foot` and `sidewalk` tags.

### 5. Preserve baseline purity guarantees

In multi-route generation, baseline route calls must disable all advanced modifiers:

- `prefer_lit`
- `heavily_avoid_unlit`
- backwards-compatibility legacy alias
- `prefer_dedicated_pavements` / `prefer_nature_trails`
- `avoid_unsafe_roads`

## Consequences

### Positive

- Advanced options are no longer silently gated by scenic slider state.
- Users always get an explicit baseline comparator for advanced-only workflows.
- Route-level explainability improves with visible modifier attribution.
- Advanced behavior is more consistent across standard, distinct, and loop solver paths.

### Tradeoffs

- Additional API/response branching increases route-handler complexity.
- Compare mode introduces extra route computation (two passes vs one).
- More response metadata requires frontend rendering and copy consistency.

## Alternatives Considered

1. Keep advanced options tied to scenic sliders.
   - Rejected: this causes non-obvious behavior and user confusion.

2. Apply advanced options in single-route mode only (no baseline compare).
   - Rejected: lacks a transparent reference route for decision-making.

3. Run full three-route distinct mode for advanced-only scenarios.
   - Rejected: unnecessary complexity and latency when no scenic preference dominates.

## Implementation References

- Frontend payload and compare activation:
  - `app/static/js/modules/routing_ui.js`
- Standard route orchestration and response metadata:
  - `app/routes.py`
- WSM multipliers and edge-cost application:
  - `app/services/routing/astar/wsm_astar.py`
- Route finder propagation:
  - `app/services/routing/route_finder.py`
- Distinct-path baseline purity and fallback compatibility:
  - `app/services/routing/distinct_paths_runner.py`
- Loop leg propagation of advanced flags:
  - `app/services/routing/loop_solvers/geometric_solver.py`
- Required edge attributes for unsafe-road logic:
  - `app/services/core/data_loader.py`
- UI route-card attribution rendering:
  - `app/static/js/modules/results_ui.js`

## Validation

Targeted tests executed after implementation:

- `tests/test_wsm_advanced_options.py` (2 passed)
- `tests/test_distinct_paths.py` (passed)
- `tests/test_street_lighting_routing_integration.py` (passed)

Known unrelated test-suite issues remain in legacy loop-solver test imports and were not introduced by this decision.
