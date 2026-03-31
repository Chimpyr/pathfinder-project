# ADR-022: Daytime-Aware Lighting Penalties and Designated Active-Travel Priority

**Status:** Proposed
**Date:** 2026-03-29

## Context

Street-lighting multipliers currently apply from `lit` tag values without route-time context. This can over-penalise routes during daytime when lighting is not safety-critical.

Recent route isolation also showed a data-semantics gap:

- Overlay cards can display richer council metadata (for example regime semantics such as "all night").
- Routing edges in the tested cache commonly had no `lighting_regime` values, so regime semantics were not available to the cost function.

In parallel, advanced safety and accessibility options should positively reinforce high-quality active-travel infrastructure. A key fixture is OSM Way `1472097444` with:

- `highway=cycleway`
- `surface=asphalt`
- `bicycle=designated`
- `foot=designated`
- `segregated=no`

This should be considered a high-quality corridor for walking and cycling contexts when relevant advanced options are enabled.

## Decision

### 1. Make lighting penalties time-relevance aware

Lighting penalties will be applied based on a request-scoped lighting context:

- `daylight`
- `twilight`
- `night`

Default mode is automatic context detection from route geography and request time. An optional override is provided for deterministic QA.

Policy:

- In `daylight`, both `prefer_lit` and `heavily_avoid_unlit` are neutralised (effective multiplier `1.0`) unless an explicit override is set.
- In `twilight` and `night`, lighting multipliers apply, with `heavily_avoid_unlit` retaining precedence over `prefer_lit`.

### 2. Add regime-aware effective lighting classification

When council regime metadata is available on routing edges, routing will derive an `effective_lit_class` from both:

- OSM/council `lit` status
- `lighting_regime` semantics for the current context

Fallback behavior:

- If `lighting_regime` is missing, route scoring falls back to current `lit`-based logic.
- If both are missing, existing dedicated-path safeguards for unknown lighting remain in force.

### 3. Add designated active-travel quality bonus

Introduce an explicit positive multiplier for dedicated active-travel corridors when safety/accessibility toggles are enabled.

Eligibility (all required unless noted):

- `highway` in dedicated active-travel classes (`cycleway`, `path`, `footway`, `pedestrian`, `track`, `bridleway`, `steps`)
- hard surface (`asphalt`, `concrete`, `paved`, related paved variants)
- at least one designated access marker: `foot=designated|yes` or `bicycle=designated|yes`

Priority rule:

- Corridors with both `foot=designated` and `bicycle=designated` receive the strongest bonus tier.
- `segregated=no` does not disqualify the corridor from the quality bonus.

### 4. Explainability and diagnostics

Route debug edge payloads will include enough information to explain decisions consistently:

- input lighting tags (`lit`, `lit_source`, `lighting_regime`)
- derived context (`lighting_context`)
- derived class (`effective_lit_class`)
- active-travel quality class and multiplier tier

## Consequences

### Positive

- Reduces daytime detours that were caused by night-focused penalties.
- Uses council regime semantics when present, improving correctness at night.
- Better aligns `prefer_dedicated_pavements` and `avoid_unsafe_roads` with user expectations on designated paved cycleways.
- Improves route explainability for debugging and UX messaging.

### Tradeoffs

- Adds complexity in request-time context calculation and multiplier composition.
- Requires consistent regime value normalization across data sources.
- Introduces a calibration burden for new bonus tiers to avoid over-biasing.

## Alternatives Considered

1. Keep static lighting penalties regardless of time.
   - Rejected: does not reflect real-world relevance and reproduces daytime detours.

2. Apply regime-aware logic only, without time context.
   - Rejected: still penalises daytime routing when lighting is irrelevant.

3. Keep cycleway quality implicit via existing multipliers only.
   - Rejected: does not explicitly reward designated paved active corridors and leaves user expectation mismatch.

4. Penalise `segregated=no` in all contexts.
   - Rejected: this can unfairly downgrade legitimate shared-use infrastructure with designated access.

## Implementation References

- Detailed delivery and test matrix:
  - [implementation-plan-daytime-aware-lighting-and-designated-active-travel-priority.md](implementation-plan-daytime-aware-lighting-and-designated-active-travel-priority.md)
- Related ADRs:
  - [ADR-019: Council-First Street Lighting Integration and Overlay Source Transparency](ADR-019-council-streetlight-data.md)
  - [ADR-021: Advanced Options Activation and Baseline Compare Mode](ADR-021-advanced-options-activation-and-compare-mode.md)
