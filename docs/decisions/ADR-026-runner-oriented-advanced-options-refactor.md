# ADR-026: Runner-Oriented Advanced Options Refactor

## Status

Proposed

## Date

2026-04-04

## Context

Refactor advanced routing options with breaking names/keys allowed, while keeping frontend labels/payloads and docs synchronized in the same delivery. The routing behavior will implement an explicit runner-priority edge ladder and add two targeted toggles: segregated-path bonus and quiet-service fallback.

## Plan

### 1. Phase 1: Lock runner behavior specification

1. Define canonical runner tier ladder (highest to lowest preference):
   - Tier 1: Traffic-separated designated corridors.
     - Examples: `highway=cycleway/path/footway` (or equivalent active-travel types) with strong pedestrian access signals (`foot=designated` preferred; `foot=yes` acceptable).
   - Tier 1.1 bonus: public-right-of-way style hints when present.
     - Examples: `designation/public_footpath/prow` footpath variants.
   - Tier 2: Sidewalk footways that are paved and pedestrian-allowed.
     - Examples: `highway=footway` + `footway=sidewalk` + paved/asphalt/concrete family + `foot=designated/yes`.
   - Tier 3: Paved footways without full designation.
     - Examples: `highway=footway` + paved/asphalt/concrete family.
   - Tier 4: Quiet service fallback.
     - Examples: `highway=service` with low `maxspeed` and positive foot/bicycle access signals.

2. Define segregated rule: `segregated=yes` gives a positive bonus; missing `segregated` is neutral (no penalty).

3. Freeze conflict/precedence rules for all advanced toggles (backend and UI consistent).

### 2. Phase 2: Canonical option taxonomy

1. Finalize new canonical toggle names and labels (breaking rename accepted).
2. Add two new toggles:
   - Prefer Segregated Paths
   - Allow Quiet Service Lanes
3. Publish key map used consistently by parser, solver args, frontend payload, saved-query restore, and docs.

### 3. Phase 3: Backend parser and solver updates (depends on Phase 1 and 2)

1. Update advanced-option canonicalization in routes to parse canonical keys only.
2. Refactor dedicated/path scoring into explicit components:
   - separation/infrastructure preference
   - paved-surface preference
   - unsafe-road gating
3. Implement runner-tier checks using robust tag normalization.
4. Implement quiet-service fallback with robust maxspeed parsing:
   - handle integer, string, and unit suffixed values
   - handle missing/irregular `maxspeed` conservatively
   - define threshold normalization policy (mph/kmh handling documented)
5. Implement segregated bonus as additive preference (bonus-only, no missing-value penalty).
6. Preserve deterministic conflict enforcement when UI constraints are bypassed.

### 4. Phase 4: Frontend synchronization (depends on Phase 2)

1. Update toggle controls, labels, and conflict logic in UI.
2. Update payload assembly to canonical keys.
3. Update saved-query restore/read mapping to canonical keys.
4. Update advanced help modal descriptions to exact tags and multiplier behavior.

### 5. Phase 5: Documentation synchronization (final pass depends on Phase 3 and 4)

1. Update routing advanced options documentation to canonical names and new runner-tier behavior.
2. Update loop/control docs and combination guidance.
3. Add runner-profile examples aligned to the four-tier ladder.
4. Remove stale references to old option names/semantics.

### 6. Phase 6: Tests and acceptance criteria (depends on Phase 3 and 4)

1. Update resolver tests for renamed keys and conflict behavior.
2. Add deterministic route-choice fixtures proving each tier preference order:
   - Tier 1 beats Tier 2/3 at comparable distance.
   - Tier 2 beats Tier 3 when sidewalk+designation conditions are met.
   - Tier 4 (service fallback) is selected when safer separated/paved options are absent.
3. Add segregated bonus tests proving `yes` boosts but missing remains neutral.
4. Add maxspeed parsing tests for multiple formats and units.
5. Keep baseline-vs-advanced regression checks intact.

### 7. Phase 7: Heuristic policy (validation-first, not mandatory rewrite)

1. Keep the current heuristic unchanged initially.
2. Add a targeted heuristic sanity check suite to ensure no unacceptable routing regressions for the new modifiers.
3. Only change heuristic if evidence shows material correctness/performance problems.
4. If strict optimality assurance is required later, evaluate conservative fallback mode (for example, zero heuristic) as a separate follow-up, not part of this refactor.

## Relevant Files

- `app/services/routing/astar/wsm_astar.py` - multiplier logic, runner-tier scoring, cost pipeline.
- `app/routes.py` - advanced-option canonicalization and conflict handling.
- `app/static/js/modules/routing_ui.js` - toggle conflict logic and request payloads.
- `app/static/js/modules/saved_ui.js` - saved query restore mapping.
- `app/templates/index.html` - toggle labels and advanced help modal content.
- `tests/test_wsm_advanced_options.py` - solver option behavior and resolver tests.
- `tests/test_distinct_paths.py` - baseline vs advanced integration assertions.
- `docs/features/routing/advanced_options.md` - canonical advanced option semantics.
- `docs/features/loop_route_controls.md` - combinations and conflict guidance.

## Verification

1. Automated tests for resolver, runner-tier route choice, segregated bonus, and maxspeed parsing.
2. Manual UI checks: conflicts, payload keys, saved-query restore, modal text accuracy.
3. Documentation checks: all renamed/new options reflected; no stale names.
4. Runner acceptance checks: synthetic scenarios match stated preference ordering.

## Decisions

- Included: breaking option key/name changes now (pre-release).
- Included: docs and frontend references updated in same change set.
- Included: two new toggles (segregated bonus, quiet service fallback).
- Included: heuristic validation phase without mandatory heuristic rewrite.
- Excluded: external traffic feeds / real-time data sources.

## Further Considerations

1. Add presets after refactor: Road Running, Pavement-First, Night Safe.
2. Add explainability fields for new toggles in route debug outputs.
3. Evaluate strict-optimality mode in a separate initiative only if needed.
