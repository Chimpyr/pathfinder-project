# Advanced Routing Options

## Overview

The Advanced Routing Options provide precise, user-directed modifiers that shape how the Weighted Sum Model (WSM) A\* routing engine expands graph nodes. Rather than adding or pruning nodes strictly before search, these options calculate dynamic multiplicative penalties and rewards on edge weights at runtime, directly changing geometrical output in response to subjective preference thresholds.

## Toggles & Multipliers

### Environmental & Surface Types

The system supports strict geometrical and topological deviations by favouring specific classifications of walking structure. These toggles inherently change how the WSM views road classifications (`highway` and `surface` tags) without needing to reload the cached spatial graph.

1. **Prefer Dedicated Pavements (`prefer_dedicated_pavements`)**
   - **Cost Adjustments:**
     - Active transport structures (`cycleway`, `path`, `footway`, `pedestrian`, `track`, `bridleway`, `steps`, `living_street`) receive a **0.78×** reward.
     - Hard paved surfaces (`paved`, `asphalt`, `concrete`, `concrete:plates`, `concrete:lanes`, `paving_stones`) receive a **0.90×** reward.
     - Explicit designations (e.g. `foot=designated` + `bicycle=designated`) receive extra quality tier bonuses (**0.85×** to **0.96×**).
     - Shared vehicular lanes (`motorway`, `trunk`, `primary`, `secondary`, `tertiary` and links) receive a severe **2.8×** penalty.
     - Natural trail surfaces receive a **1.35×** penalty.
   - **Behaviour:** Holistic infrastructure preference. Actively hunts high-quality active-travel corridors while keeping away from major roads and muddy trails. Designed for activities like road running.

2. **Prefer Paved Surfaces (`prefer_paved`)**
   - **Cost Adjustments:** A purely material-based check:
     - Hard surfaces (`paved`, `asphalt`, `concrete`, etc.) = **1.0×** (Neutral)
     - Rough/Cobbled surfaces (`sett`, `cobblestone`, `metal`, `wood`) = **1.1×** penalty.
     - Gravel/Compacted = **1.3×** penalty.
     - Soft surfaces (`dirt`, `grass`, `mud`, `sand`, etc.) = **2.0×** penalty.
     - Unknown surface = **1.2×** penalty.
   - **Behaviour:** Just wants to keep your shoes out of the mud. Ignores road types or traffic risk as long as the ground is paved.

3. **Prefer Nature Trails (`prefer_nature_trails`)**
   - **Cost Adjustments:**
     - Natural surfaces (`dirt`, `grass`, `woodchips`, `mud`, `gravel`, `compacted`, etc.) receive a **0.78×** reward.
     - Nature trail highways (`path`, `track`, `bridleway`, `footway`, `steps`) receive a **0.72×** reward.
     - Hard urban surfaces receive a **1.35×** penalty.
     - Vehicle-focused highways receive a massive **4.0×** penalty.
   - **Behaviour:** Pulls the route away from urban structures and towards off-road, natural terrain.

4. **Prefer Pedestrian (`prefer_pedestrian`)**
   - **Cost Adjustments:**
     - Pedestrian paths (`pedestrian`, `path`, `footway`, `cycleway`, `track`, `living_street`) = **0.2×** reward.
     - Vehicle-focused roads get a **5.0×** penalty.
   - **Behaviour:** Strongly anchors paths to urban pedestrian-only structures.

### Lighting Options

Leverages a blend of OSM `lit=*` tags and council streetlight context, actively calculating lighting contexts (`daylight`, `twilight`, `night`) and regimes (`all_night`, `part_night`). Dedicated active-travel paths with missing lit tags default to 1.0 (neutral), preventing an accidental bias against cycleways at night.

1. **Prefer Lit Streets (`prefer_lit`)**
   - **Cost Adjustments:** Modifies edges with a soft bias pull for night routing:
     - `lit` = **0.85×**
     - `limited` = **1.3×**
     - `unlit` = **1.8×**
     - `unknown` = **1.2×**

2. **Heavily Avoid Unlit (`heavily_avoid_unlit`)**
   - **Cost Adjustments:** Aggressively penalises unlit tags to force routing near light sources:
     - `lit` = **0.70×**
     - `limited` = **2.5×**
     - `unlit` = **5.0×**
     - `unknown` = **3.0×**

### Safety Option

1. **Avoid Unsafe Roads (`avoid_unsafe_roads`)**
   - **Cost Adjustments:** Evaluates high-risk roads (`primary`, `secondary`, `tertiary` and links). If no explicit pedestrian safety tagging exists (e.g., `sidewalk=both`, `foot=designated`), the edge receives a **3.5×** multiplier penalty.
   - **Behaviour:** Reduces risk by aggressively routing away from dangerous roadside walking.

## Implementation Mechanics

The canonical API endpoints parse boolean flags automatically. The main traversal loop in `wsm_astar.py` executes these flags independently by checking explicit tags and dictionaries (like `_ACTIVE_TRAVEL_HARD_SURFACE_TAGS`). During the `distance_between` logic, the baseline WSM cost is incrementally multiplied by every modifier that evaluates to true.

```python
# During calculating the cost of edge n1 -> n2
if self.prefer_paved:
    cost *= _compute_surface_multiplier(data)

if self.prefer_dedicated_pavements:
    cost *= _compute_dedicated_pavements_multiplier(data)

if self.avoid_unsafe_roads:
    cost *= _compute_unsafe_road_multiplier(data)
```

This dynamic runtime approach maintains extremely low latency whilst still radically altering pathfinding geometries.
