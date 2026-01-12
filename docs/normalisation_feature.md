# Normalisation Feature

Scales all scenic cost attributes to a consistent 0.0-1.0 range for use in the WSM A* routing algorithm.

---

## Overview

The normalisation processor runs after all other scenic processors (greenness, water, social, quietness, elevation) and creates unified `norm_*` attributes that can be directly weighted in the A* cost function.

---

## Configuration

```python
# config.py
NORMALISATION_MODE = 'STATIC'  # Options: 'STATIC', 'DYNAMIC'
```

| Mode | Behaviour | Best For |
|------|-----------|----------|
| `STATIC` | Copies raw 0-1 values; only normalises unbounded attrs | Cross-region comparability |
| `DYNAMIC` | Rescales all attributes per-map (best=0, worst=1) | "Best available" within each region |

---

## Normalised Attributes

| Attribute | Source | Interpretation |
|-----------|--------|----------------|
| `norm_green` | `raw_green_cost` | 0 = green, 1 = no green |
| `norm_water` | `raw_water_cost` | 0 = near water, 1 = no water |
| `norm_social` | `raw_social_cost` | 0 = near POIs, 1 = no POIs |
| `norm_quiet` | `noise_factor` | 0 = quiet, 1 = noisy |
| `norm_slope` | `slope_time_cost` | 0 = easy, 1 = steep |

---

## Usage in WSM A*

```python
# Example weighted sum calculation
cost = length * (1.0 
    + w_green * norm_green
    + w_water * norm_water
    + w_quiet * norm_quiet
    + w_slope * norm_slope
)
```

All `norm_*` values are in 0-1 range, so weights are directly comparable.

---

## Static vs Dynamic Mode

### Static Mode (Default)
- Pre-normalised attributes (green, water, social) copied directly
- Only `slope_time_cost` and `noise_factor` actually normalised
- A "0.3 greenness" in Bristol means the same as "0.3 greenness" in Cornwall

### Dynamic Mode
- All attributes rescaled per-map
- Best edge in graph always gets 0.0, worst gets 1.0
- A city with no parks still has a "greenest" route

---

## Performance

| Graph Size | Normalisation Time |
|------------|-------------------|
| 325k edges | ~0.2s |

Single-pass O(n) algorithm - minimal overhead.
