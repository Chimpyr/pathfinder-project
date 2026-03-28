# ADR-018: Dynamic Movement Speed Profiles and Unit Normalization

**Status:** Proposed
**Date:** 2026-03-28

## Context

ScenicPathFinder currently assumes a single global walking speed (`WALKING_SPEED_KMH`) and renders distance output in kilometers by default. This causes four product and engineering issues:

1. ETA does not reflect user-specific pace differences.
2. Running users cannot select race vs easy effort profiles.
3. Users preferring imperial units do not get consistent miles/mph output.
4. Existing Tobler-based slope multiplier logic is tied to static activity assumptions and must not be made user-mutating on shared graph state.

Current method touchpoints:

- `calculate_tobler_cost`, `calculate_directional_gradients`, `process_graph_elevation` in [app/services/processors/elevation.py](../../app/services/processors/elevation.py)
- `_calculate_estimated_time` and `find_route` in [app/services/routing/route_finder.py](../../app/services/routing/route_finder.py)
- `/api/route` and `/api/loop` response assembly in [app/routes.py](../../app/routes.py)

## Decision

### 1. Canonical Units and Profile Model

- Store and compute all speeds in km/h.
- Keep canonical backend route distance field in km.
- Add three movement profiles:
  - walking
  - running_easy
  - running_race
- Add user preference for display unit: `km` or `mi`.

### 2. Persistence Strategy

- Persist movement preferences in `users` table for long-term account storage.
- Persist the same preferences in browser local storage for low-latency UI hydration.
- On login, apply deterministic merge using `updated_at` timestamps, then write merged state to both storage layers.

### 3. API Contract

- Add authenticated endpoints for movement preferences (`GET` and `PATCH`).
- Extend route/loop request payloads with optional `travel_profile` and `distance_unit`.
- Route/loop responses include profile-aware speed metadata so UI can render Selected Route Details accurately.

### 4. Tobler and ETA Computation Boundary

- Keep shared graph processing static.
- Do not mutate edge costs globally per user.
- Compute profile-aware ETA at request time using:
  - selected profile speed (km/h)
  - edge gradient-derived Tobler multiplier via `calculate_tobler_cost`
- Formula policy:
  - `speed_ms = speed_kmh * 1000 / 3600`
  - `signed_gradient = uphill_gradient - downhill_gradient`
  - `edge_time_seconds = (edge_length_m / speed_ms) * calculate_tobler_cost(signed_gradient, activity)`
  - `route_time_seconds = sum(edge_time_seconds)`

Activity mapping:

- walking profile uses Tobler `walking` activity curve.
- both running profiles use Tobler `running` activity curve; race/easy differ by chosen speed value.

### 5. UX Placement

- Account page is the source of truth for configuring movement preferences.
- Finder view contains travel profile selector above action buttons.
- Finder includes tooltip text directing users to Account settings for speed edits.

## Consequences

Positive:

- ETA aligns with user-specific movement behavior.
- Unit output is consistent and user-controlled.
- Shared graph cache remains safe and reusable under concurrent load.
- Running users gain practical race/easy profile control without requiring separate routing engines.

Negative:

- Additional API and validation complexity.
- Increased UI state management for dual persistence and profile selection.
- More regression surface across route cards, loop cards, and Selected Route Details.

Operational:

- Migration and backward compatibility must be tightly managed.
- Precision and rounding policy must remain consistent between frontend and backend.

## Alternatives Considered

1. Recompute or mutate graph edge costs per user profile.
   - Rejected due to concurrency risk and cache invalidation complexity.

2. Keep only server-side preference storage (no local storage).
   - Rejected due to slower UX hydration and poor offline resilience.

3. Store imperial values natively when user selects miles.
   - Rejected because mixed canonical units increase conversion bugs and API ambiguity.

4. Support only one running speed.
   - Rejected because it does not satisfy race vs easy requirement and limits training use cases.

## Implementation References

- Detailed implementation and test matrix: [implementation-plan-dynamic-movement-speed.md](implementation-plan-dynamic-movement-speed.md)
- Related ADRs:
  - [ADR-012: Dual-Database Segregation](ADR-012-dual-database-segregation.md)
  - [ADR-016: Alembic Migration Safety](ADR-016-alembic-migration-safety.md)
