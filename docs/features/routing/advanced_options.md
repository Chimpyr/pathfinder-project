# Advanced Routing Options

## Overview

Advanced options are runtime multipliers in the WSM A\* solver. They do not rebuild the graph; instead they adjust per-edge cost during `distance_between` using OSM tags such as `highway`, `surface`, `lit`, `sidewalk`, `foot`, `bicycle`, `segregated`, and `maxspeed`.

## Canonical Toggle Keys

- `prefer_separated_paths`
- `prefer_nature_trails`
- `prefer_paved_surfaces`
- `prefer_lit_streets`
- `avoid_unlit_streets`
- `avoid_unsafe_roads`
- `avoid_unclassified_lanes`
- `prefer_segregated_paths`
- `allow_quiet_service_lanes`

Legacy keys are still accepted for compatibility:

- `prefer_dedicated_pavements` -> `prefer_separated_paths`
- `prefer_paved` -> `prefer_paved_surfaces`
- `prefer_lit` -> `prefer_lit_streets`
- `heavily_avoid_unlit` -> `avoid_unlit_streets`
- `prefer_pedestrian` -> legacy fallback to separated mode when no newer path-intent toggle is present

## Path and Surface Modifiers

### `prefer_separated_paths`

Runner-oriented tier ladder:

1. Tier 1: `highway=cycleway|path|pedestrian` with `foot=yes|designated|permissive` -> `0.70x`
2. Tier 2: `highway=footway` + `footway=sidewalk` + paved surface + `foot=yes|designated|permissive` -> `0.82x`
3. Tier 3: paved `highway=footway` -> `0.92x`
4. Tier 4: quiet service fallback (only when enabled) -> `0.97x`

Additional effects while enabled:

- `highway=motorway|motorway_link|trunk|trunk_link|primary|primary_link|secondary|secondary_link|tertiary|tertiary_link` -> `2.8x`
- high-speed `highway=unclassified` without sidewalk/foot/cycleway safety cues (maxspeed `>= 50 km/h`) -> `2.2x`
- Tier 1-3 paved surfaces (`paved`, `asphalt`, `concrete`, `concrete:plates`, `concrete:lanes`, `paving_stones`) -> extra `0.90x`
- Tier 1-3 soft trail surfaces (`dirt`, `earth`, `ground`, `mud`, `sand`, `grass`, `grass_paver`, `woodchips`, `gravel`, `fine_gravel`, `compacted`) -> extra `1.25x`
- PROW-like hints in `designation/public_footpath/prow` on Tier 1 links -> extra `0.93x`

### `prefer_segregated_paths`

Bonus-only rule:

- `segregated=yes` -> `0.90x`
- `segregated=no` or missing -> `1.00x` (neutral)

### `allow_quiet_service_lanes`

Allows Tier 4 fallback if all checks pass:

- `highway=service`
- parseable `maxspeed` and `<= 30 km/h` (numeric and `mph` values supported)
- pedestrian-friendly access indicator present:
  - `sidewalk=both|left|right|yes|separate`, or
  - `foot=yes|designated`, or
  - `bicycle=yes|designated`
- soft trail surfaces are excluded

### `prefer_paved_surfaces`

Material-only penalty map:

- hard paved -> `1.0x`
- rough/cobbled (`sett`, `cobblestone`, `cobblestone:flattened`, `metal`, `wood`) -> `1.1x`
- gravel/compacted (`compacted`, `fine_gravel`, `gravel`) -> `1.3x`
- soft (`dirt`, `earth`, `ground`, `mud`, `sand`, `grass`, `grass_paver`, `woodchips`) -> `2.0x`
- unknown/missing -> `1.2x`

### `prefer_nature_trails`

Trail-biased mode:

- trail highways (`path`, `track`, `bridleway`, `footway`, `steps`) -> `0.72x`
- natural surfaces (`dirt`, `earth`, `ground`, `mud`, `sand`, `grass`, `grass_paver`, `woodchips`, `gravel`, `fine_gravel`, `compacted`) -> `0.78x`
- vehicle-focused highways -> `4.0x`
- residential/unclassified/service/living_street -> `1.35x`
- hard paved surfaces -> `1.35x`
- trail highway with missing surface -> extra `0.90x`

Conflict rule: enabling `prefer_nature_trails` disables separated/paved-focused toggles.

## Lighting and Safety

### `prefer_lit_streets`

- lit -> `0.85x`
- limited -> `1.3x`
- unlit -> `1.8x`
- unknown -> `1.2x`

### `avoid_unlit_streets`

- lit -> `0.70x`
- limited -> `2.5x`
- unlit -> `5.0x`
- unknown -> `3.0x`

Precedence rule: `avoid_unlit_streets` overrides `prefer_lit_streets`.

### `avoid_unsafe_roads`

Unsafe candidate classes:

- `highway=primary|primary_link|secondary|secondary_link|tertiary|tertiary_link`
- `highway=unclassified` with parseable `maxspeed >= 50 km/h` and no pedestrian/cycle safety cues

Safety exemptions:

- `sidewalk=both|left|right|yes|separate`
- `foot=yes|designated`
- cycleway infrastructure signals (`cycleway` or `cycleway:both` in `lane|track|separate|yes|shared_lane|share_busway|opposite_lane|opposite_track`)

Unsafe candidate without exemption -> `3.5x`.

### `avoid_unclassified_lanes`

Last-resort lane-avoidance mode:

- targets `highway=unclassified`
- requires missing pedestrian/cycle safety cues:
  - no `sidewalk=both|left|right|yes|separate`
  - no `foot=yes|designated`
  - no `cycleway`/`cycleway:both` safety markers (`lane|track|separate|yes|shared_lane|share_busway|opposite_lane|opposite_track`)
- applies strong penalty `8.0x`

This is a soft-ban design: penalties are finite, so the router can still use these lanes when no practical alternative exists.
