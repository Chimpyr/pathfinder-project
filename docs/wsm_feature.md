# WSM Cost Function Feature

Weighted Sum Model (WSM) implementation for scenic routing. Combines distance with normalised scenic feature costs to find routes that balance efficiency with user preferences.

---

## Overview

The WSM A* algorithm extends standard A* pathfinding by replacing the distance-only cost function with a weighted combination of:

| Feature | Attribute | Type | Interpretation |
|---------|-----------|------|----------------|
| Distance | `length` | Cost | Shorter is better |
| Greenness | `norm_green` | Benefit | Parks, trees, vegetation |
| Water | `norm_water` | Benefit | Rivers, canals, lakes |
| Social | `norm_social` | Benefit | Cafes, landmarks, tourist spots |
| Quietness | `norm_quiet` | Cost | 0=quiet, 1=noisy |
| Slope | `norm_slope` | Cost | 0=flat, 1=steep |

---

## Formula

```
Cost = (w_d × l̂) + (w_g × (1-ĝ)) + (w_w × (1-ŵ)) + (w_s × (1-ŝ)) + (w_q × q̂) + (w_e × ê)
```

Where:
- `l̂` = normalised edge length (0-1)
- `ĝ, ŵ, ŝ` = normalised benefit features (inverted: high value = low cost)
- `q̂, ê` = normalised cost features (direct: high value = high cost)
- `w_*` = user-configurable weights

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

### User-Adjustable Weights

UI sliders (0-100) are normalised to sum to 1.0:

```javascript
// Example API request
{
    "start_lat": 51.449,
    "start_lon": -2.580,
    "end_lat": 51.456,
    "end_lon": -2.591,
    "use_wsm": true,
    "weights": {
        "distance": 30,
        "greenness": 80,
        "water": 50,
        "quietness": 50,
        "social": 20,
        "slope": 10
    }
}
```

**Slider semantics**: Higher value = stronger preference for that feature.

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
