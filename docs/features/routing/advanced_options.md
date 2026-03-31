# Advanced Routing Options

## Overview

The Advanced Routing Options provide precise, user-directed modifiers that shape how the Weighted Sum Model (WSM) A\* routing engine expands graph nodes. Rather than adding or pruning nodes strictly before search, these options calculate dynamic multiplicative penalties and rewards on edge weights at runtime, directly changing geometrical output in response to subjective preference thresholds.

## Toggles & Multipliers

### Environmental Types (Mutually Exclusive)

The system supports strict geometrical and topological deviations by favouring specific classifications of walking structure. These toggles inherently change how the WSM views road classifications (`highway` and `surface` tags) without needing to reload the cached spatial graph.

1. **Prefer Dedicated Pavements (`prefer_dedicated`)**
   - **Cost Adjustments:** Promotes paved areas (`paved`, `asphalt`, `concrete`) and active transport structures (`pedestrian`, `path`, `cycleway`, `footway`). Applies a $0.2 \times$ distance reward to dedicated routes. Also penalises shared vehicular lanes (`residential`, `secondary`, `tertiary`) with a $2.0 \times$ multiplier.
   - **Behaviour:** Safely restricts routes primarily to sidewalks and structured paths.

2. **Prefer Nature Trails (`prefer_nature`)**
   - **Cost Adjustments:** Promotes natural structures (`dirt`, `grass`, `wood`, `earth`, `mud`) and tracks with a $0.4 \times$ multiplier based on positive topological traits. Inversely penalises highly structured areas unsuited for natural walking.
   - **Behaviour:** Routes deviate into parks, woodland trails, and towpaths whenever accessible.

_Note on UI Mutual Exclusivity:_ The web interface categorises these as radio-like interactions. Selecting 'Nature' inherently deselects 'Dedicated' and vice-versa, ensuring the routing engine is never supplied contradictory topology goals.

### Lighting Options (Mutually Exclusive)

Leverages a blend of OSM `lit=*` tags and Council Streetlight datasets (via spatial snapping arrays) to bias routing in low-light contexts.

1. **Prefer Lit Streets (`prefer_lit`)**
   - **Cost Adjustments:** Multiplies explicitly illuminated edge costs by $0.7 \times$. Does not severely punish unlit areas but simply treats them as standard length, acting as a soft-bias pull for urban routes at night.
2. **Heavily Avoid Unlit (`avoid_unlit`)**
   - **Cost Adjustments:** Aggressively penalises unlit tags with a severe $5.0 \times$ metric.
   - **Behaviour:** Effectively pushes the router to only traverse an unlit section if detouring lit streets would force a mathematically absurd geometric detour.

_Note on UI Mutual Exclusivity:_ Like Environmental options, 'Prefer Lit' and 'Heavily Avoid Unlit' disable one another.

### Safety Option

1. **Avoid Unsafe Roads (`avoid_unsafe`)**
   - **Cost Adjustments:** Evaluates high-risk roads (`primary`, `trunk`, `motorway`) explicitly where no pedestrian tagging is available. Applies a $5.0 \times$ multiplier to them.
   - **Behaviour:** Reduces risk by routing away from dangerous roadside walking.

## Implementation Mechanics

The canonical API endpoints (`/api/route` and `/api/loop`) parse these boolean flags automatically. The main traversal loop `calculate_wsm_cost()` in `wsm_astar.py` executes these flags independently. During the main expansion, the baseline distance is modified by whichever advanced settings apply.

```python
if prefer_dedicated:
    if highway in ['pedestrian', 'path', 'cycleway', 'footway'] or surface in ['paved', 'asphalt', 'concrete', 'paving_stones', 'sett']:
        multiplier = 0.2
    if highway in ['residential', 'secondary', 'tertiary', 'primary']:
        multiplier = 2.0
```

This dynamic approach maintains extremely low latency (sub-15 seconds generally) whilst still radically altering pathfinding output geometries.
