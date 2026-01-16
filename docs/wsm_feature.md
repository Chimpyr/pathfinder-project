# WSM Cost Function Feature

Weighted Sum Model (WSM) implementation for scenic routing. Combines distance with normalised scenic feature costs to find routes that balance efficiency with user preferences.

---

## Overview

The WSM A* algorithm extends standard A* pathfinding by replacing the distance-only cost function with a weighted combination of:

| Feature | Attribute | Interpretation |
|---------|-----------|----------------|
| Distance | `length` | Shorter is better |
| Greenness | `norm_green` | 0 = green (good), 1 = no green (bad) |
| Water | `norm_water` | 0 = water nearby (good), 1 = no water (bad) |
| Social | `norm_social` | 0 = POIs nearby (good), 1 = no POIs (bad) |
| Quietness | `norm_quiet` | 0 = quiet (good), 1 = noisy (bad) |
| Slope | `norm_slope` | 0 = flat (good), 1 = steep (bad) |

All normalised values use **cost semantics** (0 = good, 1 = bad) so the WSM formula doesn't need per-feature inversion.

---

## Formula

```
Cost = (w_d × l̂) + (w_g × ĝ) + (w_w × ŵ) + (w_s × ŝ) + (w_q × q̂) + (w_e × ê)
```

Where:
- `l̂` = normalised edge length (0 = short, 1 = long)
- `ĝ, ŵ, ŝ, q̂, ê` = normalised costs (all use 0 = good, 1 = bad semantics)
- `w_*` = user-configurable weights (must sum to 1.0)

Lower cost = better path.

---

## Weight Normalisation

UI slider values (0-10) are converted to normalised weights using `normalise_ui_weights()`:

```python
# User sets: greenness=10, all others=0
ui_weights = {'greenness': 10, 'distance': 0, ...}

# After normalisation:
# distance: 50 (default, always included)
# greenness: 10 (from user)
# all others: 0 (unused)
# Total = 60

weights = {
    'distance': 50/60 = 0.833,    # 83.3%
    'greenness': 10/60 = 0.167,   # 16.7%
    'water': 0.0,
    'quietness': 0.0,
    'social': 0.0,
    'slope': 0.0
}
```

**Key design decision:** Unused features default to 0, not 50. This ensures:
- User's explicit preferences aren't diluted by implicit defaults
- Setting one slider to 10 gives that feature meaningful influence
- Distance is always considered (defaults to 50) to prevent absurdly long routes

---

## Configuration

### Default Weights

```python
# config.py
WSM_DEFAULT_WEIGHTS = {
    'distance': 0.5,    # Physical distance
    'greenness': 0.15,  # Prefer greener routes
    'water': 0.1,       # Prefer routes near water
    'quietness': 0.1,   # Prefer quieter routes
    'social': 0.1,      # Prefer routes near POIs
    'slope': 0.05,      # Prefer gentler gradients
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
    'weights': {'greenness': 100, 'distance': 50}  # Optional
})
```

### Toggle Between Modes

| Mode | `use_wsm` | Behaviour |
|------|-----------|-----------|
| Shortest Path | `false` | Standard A* (distance only) |
| Scenic Routing | `true` | WSM A* (weighted features) |

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

A* complexity remains O(E log V) where E=edges, V=nodes.
