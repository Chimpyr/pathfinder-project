# WSM Cost Function Feature

Weighted Sum Model (WSM) implementation for scenic routing. Combines distance with normalised scenic feature costs to find routes that balance efficiency with user preferences.

---

## Overview

The WSM A* algorithm extends standard A* pathfinding by replacing the distance-only cost function with a weighted combination of:

| Feature   | Attribute     | Interpretation                              |
| --------- | ------------- | ------------------------------------------- |
| Distance  | `length`      | Shorter is better                           |
| Greenness | `norm_green`  | 0 = green (good), 1 = no green (bad)        |
| Water     | `norm_water`  | 0 = water nearby (good), 1 = no water (bad) |
| Social    | `norm_social` | 0 = POIs nearby (good), 1 = no POIs (bad)   |
| Quietness | `norm_quiet`  | 0 = quiet (good), 1 = noisy (bad)           |
| Slope     | `norm_slope`  | 0 = flat (good), 1 = steep (bad)            |

All normalised values use **cost semantics** (0 = good, 1 = bad) so the WSM formula doesn't need per-feature inversion.

---

## Formula (Configurable Semantics)

The API supports multiple cost function semantics (configured via COST_FUNCTION in config.py), defaulting to **MIN-based OR semantics** (Hybrid Disjunctive) for scenic criteria: an edge is rewarded if it's good at ANY active criterion.

### Default: Hybrid Disjunctive (OR Semantics)

The engine uses a Weighted-MIN approach where higher weights prioritize their feature. Normalised values are adjusted by `1 + weight` before finding the minimum:

```text
adjusted_value = norm_value / (1 + weight)
best_adjusted = min(active_adjusted_values)
normalization_factor = 1 + average_weight
scenic_cost = total_scenic_weight * best_adjusted * normalization_factor

Cost = (w_d * length_norm) + scenic_cost
```

### Alternative: WSM Additive (AND Semantics)

`	ext
Cost = (w_d * length_norm) + (w_g * norm_green) + (w_w * norm_water) + ...
`

Where:

- length_norm = normalised edge length (0 = short, 1 = long)
- ctive_scenic_values = only normalised costs for criteria with weight > 0
- w\_\* = user-configurable weights (must sum to 1.0)
- **Group Nature**: The engine supports combining water and greenness into a single
  ature_cost = min(norm_green, norm_water).

### Why OR Semantics?

With multiple criteria enabled, an edge good at **ANY** criterion scores well:

| Edge Type    | norm_green | norm_water | With AND (old)      | With OR (new) |
| ------------ | ---------- | ---------- | ------------------- | ------------- |
| Park path    | 0.1        | 0.9        | Penalised for water | Uses 0.1 ✓    |
| River bank   | 0.9        | 0.1        | Penalised for green | Uses 0.1 ✓    |
| Urban street | 0.9        | 0.9        | High cost           | Uses 0.9 ✗    |

This prevents multi-criteria requests from collapsing to shortest path.

See [ADR-001](decisions/ADR-001-wsm-or-semantics.md) for detailed decision rationale.

Lower cost = better path.

---

## Weight Normalisation

UI slider values (0-5) are converted to normalised weights using `normalise_ui_weights()`:

```python
# User sets: greenness=5, distance=3 (default)
ui_weights = {'greenness': 5, 'distance': 3.0, ...}

# After normalisation:
# distance: 3.0 (from user/default)
# greenness: 5 (from user)
# all others: 0 (unused)
# Total = 8

weights = {
    'distance': 3/8 = 0.375,    # 37.5%
    'greenness': 5/8 = 0.625,   # 62.5%
    'water': 0.0,
    'quietness': 0.0,
    'social': 0.0,
    'slope': 0.0
}
```

**Key design decisions:**

- Unused features default to 0. This ensures a user's explicit preferences aren't diluted by implicit defaults.
- Setting one slider to 5 gives that feature meaningful influence.
- Distance defaults to 3.0 (middle of the 0-5 range) and has a hard un-removable minimum `0.1` weight to prevent absurdly long routes natively.
- **Slope:** The slope weight operates differently and can be negative (-5 to 5). Negative values invert the penalty, enabling the users to actively prefer steep paths over flat ones.

---

## Configuration

### Default Weights

```python
# Defaults applied if omitted in request (matching UI center)
WSM_DEFAULT_WEIGHTS = {
    'distance': 3.0,    # Physical distance component
    'greenness': 0.0,  # Prefer greener routes
    'water': 0.0,      # Prefer routes near water features
    'quietness': 0.0,  # Prefer quieter routes (low traffic noise)
    'social': 0.0,     # Prefer routes near tourist/social POIs
    'slope': 0.0,      # Prefer gentler gradients (or steeper if negative)
}
```

---

## API Usage

### Enable WSM Routing

Set `use_wsm: true` in the route request:

```python
response = requests.post('/api/route', json={
    'start_lat': 51.449,
    'start_lon': -2.580,
    'end_lat': 51.456,
    'end_lon': -2.591,
    'use_wsm': True,
    'weights': {'greenness': 5, 'distance': 3},  # Optional
    'prefer_pedestrian': True,       # Optional advanced modifiers
    'prefer_paved': False,
    'prefer_lit': False,
    'heavily_avoid_unlit': False,
    'avoid_unsafe_roads': False,
})
```

#### Final Output Multipliers

On top of the general WSM scoring, the engine applies multipliers before finalizing an edge's cost:

- `prefer_lit` / `heavily_avoid_unlit`: Provides a bonus (<1.0) to routes correctly flagged as lit, or massive penalties (up to 5.0x) for unknown or unlit segments.
- `prefer_pedestrian`: Heavily penalizes vehicle-focused roads (trunk, primary - up to 5.0x) and rewards dedicated walking paths (down to 0.2x).
- `prefer_paved`: Penalizes soft and unpaved surfaces (`mud`, `dirt`, `sand`, `grass`) while keeping paved surfaces near baseline.
- `avoid_unsafe_roads`: Applies a heavy penalty to primary/secondary/tertiary roads that lack `sidewalk` and `foot` safety indicators.

Unsafe-road classification depends on edge metadata from OSM extraction (`highway`, `sidewalk`, `foot`), so those tags are explicitly retained in the graph loader.

### Advanced Options Without Scenic Sliders

When scenic sliders are off but one or more advanced options are enabled, the frontend still sends a WSM request with distance-dominant weights and `advanced_compare_mode=true`.

This yields a transparent comparison:

- Baseline shortest route (advanced modifiers off)
- Advanced route (selected advanced modifiers on)

### Toggle Between Modes

| Mode             | `use_wsm` | Behaviour                                                      |
| ---------------- | --------- | -------------------------------------------------------------- |
| Shortest Path    | `false`   | Standard A\* (distance only)                                   |
| Scenic Routing   | `true`    | WSM A\* (weighted features and optional advanced modifiers)    |
| Advanced Compare | `true`    | Distance-dominant WSM advanced route + explicit baseline route |

---

## Architecture

```
┌─────────────────┐
│   routes.py     │  Parses weights from API request
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  route_finder   │  Selects OSMNetworkXAStar or WSMNetworkXAStar
└────────┬────────┘
         │
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────────┐
│ astar │ │ wsm_astar │  A* implementations
└───────┘ └─────┬─────┘
                │
                ▼
        ┌───────────────┐
        │cost_calculator│  WSM formula + weight normalisation
        └───────────────┘
```

---

## Performance

The WSM cost function adds minimal overhead:

- **Length normalisation**: O(1) lookup after initial O(E) scan
- **Cost calculation**: O(1) per edge (6 multiplications + additions)
- **Memory**: One extra `(min_length, max_length)` tuple per solver instance

A\* complexity remains O(E log V) where E=edges, V=nodes.

---

## Heuristic Function

The WSM A\* uses a **dual-bound admissible heuristic** that provides search direction while guaranteeing optimality:

```
h(n) = w_d × (haversine_distance / max_edge_length)
```

### Why not use a simple distance heuristic?

Standard A\* uses straight-line distance as a heuristic. For WSM routing, this doesn't work because:

- We cannot predict scenic quality of unvisited edges
- A greener path might be longer but have lower total cost

### The dual-bound approach

The heuristic assumes:

1. **Distance component**: Use straight-line distance (always underestimates actual path)
2. **Scenic components**: Assume all are 0 (best case - optimistic bound)

This is **admissible** because:

- Haversine distance ≤ actual path distance
- Actual scenic costs ≥ 0 (we assume 0, reality can only be worse)

### Benefits

| Aspect           | h(n) = 0           | Dual-bound heuristic  |
| ---------------- | ------------------ | --------------------- |
| Optimality       | ✅ Guaranteed      | ✅ Guaranteed         |
| Search direction | ❌ None (Dijkstra) | ✅ Guided toward goal |
| Node expansions  | More               | Fewer                 |
