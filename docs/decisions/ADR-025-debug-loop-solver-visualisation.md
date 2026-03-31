# ADR-025: Debug-Gated Loop Solver Visualisation and Playback

## Status

Proposed

## Date

2026-03-31

## Context

The loop-routing endpoint currently returns final loop candidates, but does not expose intermediate geometric solver states to the frontend. This makes it difficult to understand and demonstrate how directional bearings are selected, how skeleton shapes (triangle/quad/pentagon) are projected and snapped, and how clamped tortuosity feedback converges toward target distance.

A development-only demonstration mode is required for debugging and explainability. The feature must be strictly gated by Flask DEBUG mode and must not increase production routing latency when disabled. When enabled, it must remain bounded so payload size and solver overhead are controlled.

## Decision

1. Add a debug-only frontend trigger.

- The Finder panel renders a DEMO button only when `DEBUG` is true.
- DEMO submits loop requests with `demo_visualisation=true`.

2. Add request-level server gating.

- `/api/loop` parses `demo_visualisation` but only enables capture when `current_app.config['DEBUG']` is true.
- When debug is disabled, demo capture is forced off.

3. Add an optional loop demo capture context.

- `RouteFinder.find_loop_route()` accepts optional demo context and forwards it to compatible solvers.
- Geometric solver emits milestone events only, not full per-edge traces.

4. Add a bounded loop-demo response envelope.

- `/api/loop` may include a `loop_demo` object:
  - `enabled`
  - `schema_version`
  - `frame_count`
  - `truncated`
  - `frames`
- Capture is frame-capped and truncation is explicit.

5. Preserve async cold-cache behavior.

- Frontend stores demo intent in shared state and reuses it when `/api/task/<id>` completion triggers a re-submit.

## Consequences

### Positive

- The loop algorithm becomes explainable and demonstrable in developer mode.
- Production requests are unaffected because capture is disabled when `DEBUG` is false.
- The frame cap and compact schema reduce risk of runaway payload growth.

### Negative / Trade-offs

- Adds complexity to the loop request flow and solver interfaces.
- Initial capture support is solver-specific (geometric solver first).
- Frontend still needs a full playback UI module to render all frame types richly.

### Maintenance

- Event schema should remain versioned and backward compatible.
- Performance budgets should be tested for both debug-disabled and debug-enabled modes.
- Docs for API and feature behavior must track schema changes.

## Alternatives Considered

1. Reuse existing `debug_info` only.

- Rejected because it lacks skeleton/bearing/tau progression.

2. Capture full per-edge/per-node internals.

- Rejected due to payload and runtime overhead.

3. Use a separate replay endpoint.

- Deferred for now; single-response integration is simpler for initial delivery.

## Acceptance Criteria

1. DEMO button is visible only when `DEBUG` is true.
2. `/api/loop` ignores `demo_visualisation=true` when debug is off.
3. With debug on and demo enabled, `loop_demo.frames` includes milestone events for bearings, skeleton generation, and tau updates.
4. Async re-submit preserves demo mode.
5. Frame capture has an enforced upper bound and sets `truncated=true` when cap is reached.
6. No functional regression in non-demo loop routing behavior.
