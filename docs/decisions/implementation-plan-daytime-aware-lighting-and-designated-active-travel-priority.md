# Implementation Plan: Daytime-Aware Lighting and Designated Active-Travel Priority

**Status:** Proposed
**Date:** 2026-03-29
**Owner:** Routing and Data Semantics
**Related ADR:** [ADR-022](ADR-022-daytime-aware-lighting-and-designated-active-travel-priority.md)

## 1. Objective

Implement context-aware lighting penalties so advanced lighting toggles only influence routing when lighting is operationally relevant, and add explicit positive scoring for designated paved active-travel corridors.

This plan includes a route-quality acceptance fixture for OSM Way `1472097444`.

## 2. Scope

In scope:

- Daylight/twilight/night context resolution for route requests.
- Regime-aware effective lighting classification when `lighting_regime` is available.
- Neutral lighting multipliers in daylight for `prefer_lit_streets` and `heavily_avoid_unlit`.
- Dedicated active-travel quality bonus tiers for designated paved corridors.
- API debug metadata for explainability.
- Tests and docs for the new behavior.

Out of scope:

- New user-facing UI toggles for lighting context mode.
- Full historical traffic/safety modeling.
- New map overlays.

## 3. Current Baseline Touchpoints

- Lighting multipliers and advanced modifiers: [app/services/routing/astar/wsm_astar.py](../../app/services/routing/astar/wsm_astar.py)
- Route request parsing and response assembly: [app/routes.py](../../app/routes.py)
- Advanced-option propagation to solvers: [app/services/routing/route_finder.py](../../app/services/routing/route_finder.py)
- Distinct route baseline purity behavior: [app/services/routing/distinct_paths_runner.py](../../app/services/routing/distinct_paths_runner.py)
- Streetlight enrichment pipeline: [app/services/processors/streetlights.py](../../app/services/processors/streetlights.py)
- Existing advanced-option tests: [tests/test_wsm_advanced_options.py](../../tests/test_wsm_advanced_options.py)

## 4. Requirements and Acceptance Criteria

| ID  | Requirement                                              | Acceptance Criteria                                                                                                                                                                                |
| --- | -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| R1  | Route requests resolve a deterministic lighting context  | Each request resolves `lighting_context` as `daylight`, `twilight`, or `night`; optional override can force context for QA.                                                                        |
| R2  | Daylight neutralization for lighting penalties           | With `lighting_context=daylight`, `prefer_lit_streets` and `heavily_avoid_unlit` both result in effective multiplier `1.0` for all edges.                                                          |
| R3  | Twilight/night keeps current safety intent               | In `twilight` and `night`, existing lit preference/penalty direction is preserved; heavy mode remains stronger than mild mode.                                                                     |
| R4  | Regime-aware classification is used when available       | If `lighting_regime` exists, solver derives `effective_lit_class` from regime + context before selecting multiplier tier.                                                                          |
| R5  | Backward compatibility on missing regime                 | If `lighting_regime` is missing, behavior falls back to existing `lit` tag interpretation without runtime errors.                                                                                  |
| R6  | Designated paved active corridors get explicit bonus     | When safety/accessibility toggles are enabled, eligible dedicated paved edges with designated `foot` or `bicycle` receive a bonus multiplier tier (< 1.0).                                         |
| R7  | Both designated tags receive strongest bonus             | Edges with both `foot=designated` and `bicycle=designated` get a stronger bonus tier than single-designated edges.                                                                                 |
| R8  | `segregated=no` does not invalidate quality bonus        | Shared-use designation does not disqualify otherwise eligible corridor edges from bonus tiers.                                                                                                     |
| R9  | Way-specific fixture is preserved under relevant toggles | Fixture route containing OSM Way `1472097444` remains competitive/preferred with `prefer_dedicated_pavements \+ avoid_unsafe_roads`, and is not penalised by lighting toggles in daylight context. |
| R10 | Explainability fields expose derivation                  | Edge debug output includes `lighting_context`, `effective_lit_class`, and active-travel quality tier fields.                                                                                       |
| R11 | Distinct/compare baseline remains pure                   | Baseline route still disables advanced modifiers exactly as defined by ADR-021.                                                                                                                    |
| R12 | Performance regression remains controlled                | P95 route latency impact from context/resolution logic stays within agreed threshold (target <= 10%).                                                                                              |

## 5. Design

### 5.1 Request Context Inputs

Add optional fields to route/loop payload parsing:

```json
{
  "routing_datetime_utc": "2026-03-29T14:30:00Z",
  "lighting_context_override": "auto|daylight|twilight|night"
}
```

Default behavior:

- `routing_datetime_utc`: server current UTC time.
- `lighting_context_override`: `auto`.

### 5.2 Lighting Context Resolver

Introduce a small resolver module (for example `app/services/routing/lighting_context.py`) that:

1. Derives route centroid or midpoint from start/end coordinates.
2. Resolves timezone from coordinates.
3. Computes local solar phase for request datetime.
4. Returns one of `daylight`, `twilight`, `night`.

Implementation note:

- Keep dependencies minimal; if adding a library for solar/timezone calculation, isolate usage behind a single service boundary for easier testing.

### 5.3 Regime Normalization and Effective Lighting Class

Introduce normalized regime classes from source tags, for example:

- `all_night`
- `part_night`
- `switch_off`
- `unknown`

Then derive `effective_lit_class` by context:

- `daylight`: treat as neutral (`not_relevant`).
- `twilight`: `all_night` as lit, `part_night/switch_off` as limited.
- `night`: `all_night` as lit, `part_night/switch_off` as limited or unlit per policy threshold.

When regime is absent, fall back to `lit` tag + existing dedicated-path unknown policy.

### 5.4 Dedicated Active-Travel Quality Multiplier

Add a dedicated quality multiplier function in [app/services/routing/astar/wsm_astar.py](../../app/services/routing/astar/wsm_astar.py), applied only when any of these are enabled:

- backwards-compatibility legacy alias
- `prefer_dedicated_pavements`
- `avoid_unsafe_roads`

Eligibility and tiers:

- Tier A (strong bonus): dedicated active-travel highway + hard paved surface + `foot=designated` and `bicycle=designated`.
- Tier B (medium bonus): dedicated active-travel highway + hard paved surface + one designated access marker.
- Tier C (mild bonus): dedicated active-travel highway + hard paved surface + generic `foot=yes` or `bicycle=yes`.
- No bonus otherwise.

Calibration note:

- Start conservatively and calibrate multipliers against regression fixtures to avoid route over-concentration.

### 5.5 Explainability Payload Extensions

Extend edge feature extraction in [app/routes.py](../../app/routes.py) to include derived fields for debugging:

- `lighting_context`
- `effective_lit_class`
- `active_travel_quality_tier`

## 6. Delivery Sequence

1. Add lighting-context resolver service and unit tests.
2. Add request parsing/plumbing for context inputs in API handlers.
3. Implement regime normalization + effective lighting classification in solver path.
4. Implement designated active-travel quality multiplier tiers.
5. Extend debug edge payloads with derived context/classification fields.
6. Add integration tests for route/loop, distinct baseline purity, and fixture behavior.
7. Update feature docs and ADR index references.

## 7. Test Matrix

| Test ID | Requirements | Layer       | Scenario                                                                                         | Expected Result                                                             |
| ------- | ------------ | ----------- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------- |
| UT-01   | R1           | Unit        | Resolve context at local noon                                                                    | Returns `daylight`.                                                         |
| UT-02   | R1           | Unit        | Resolve context around civil dusk                                                                | Returns `twilight`.                                                         |
| UT-03   | R1           | Unit        | Resolve context after nightfall                                                                  | Returns `night`.                                                            |
| UT-04   | R2           | Unit        | `heavily_avoid_unlit` with forced daylight                                                       | Effective lit multiplier equals `1.0`.                                      |
| UT-05   | R4,R5        | Unit        | Regime present vs missing                                                                        | Regime path uses derived class; missing regime cleanly falls back to `lit`. |
| UT-06   | R6,R7,R8     | Unit        | Dedicated paved cycleway with `foot=designated`, `bicycle=designated`, `segregated=no`           | Strongest quality bonus tier is selected.                                   |
| IT-01   | R3           | Integration | Night request with heavy-unlit                                                                   | Unlit/limited edges are strongly penalised relative to lit edges.           |
| IT-02   | R2           | Integration | Daylight request with heavy-unlit                                                                | Route does not detour due to lighting penalties alone.                      |
| IT-03   | R9           | Integration | Fixture route including Way `1472097444` with `prefer_dedicated_pavements \+ avoid_unsafe_roads` | Route remains competitive/preferred over unsafe or unpaved alternatives.    |
| IT-04   | R10          | Integration | Route API response includes debug fields                                                         | Edge features contain context/class/tier fields with normalized values.     |
| IT-05   | R11          | Integration | Advanced compare mode baseline route                                                             | Baseline still disables all advanced modifiers.                             |
| PERF-01 | R12          | Performance | Compare route P95 before/after                                                                   | Latency regression within threshold target.                                 |

## 8. Risks and Mitigations

- Risk: timezone/solar lookup adds overhead.
  - Mitigation: cache per-request context once and pass into solver; avoid per-edge calculations.

- Risk: regime source values vary by council dataset.
  - Mitigation: explicit normalization map and unknown fallback path.

- Risk: quality bonus overpowers distance and scenic criteria.
  - Mitigation: conservative initial multipliers and fixture-based tuning.

- Risk: behavior drift between route and loop solvers.
  - Mitigation: shared context + multiplier helpers and cross-mode integration tests.

## 9. Definition of Done

- Requirements R1-R12 validated by automated tests.
- ADR-022 and this plan are committed and indexed.
- Daytime requests no longer detour due to lighting penalties alone.
- Designated paved active corridors (including Way `1472097444`) are positively reinforced under relevant advanced options.
- Debug output explains the derived lighting and quality classifications used for scoring.
