# Distinct Paths Feature

Multi-route strategy that approximates the Pareto frontier by running A\* three times per request, providing transparent trade-offs between efficiency and scenic experience.

## Overview

When enabled, the routing API can return route alternatives instead of a single path.

Primary distinct mode returns three routes:

| Route         | Description                           | Colour            |
| ------------- | ------------------------------------- | ----------------- |
| **Baseline**  | Shortest distance (pure efficiency)   | Grey `#808080`    |
| **Extremist** | Maximises user's strongest preference | Feature-dependent |
| **Balanced**  | User's actual weight configuration    | Blue `#3B82F6`    |

Each route entry now includes `route_context` metadata (subtitle + active modifiers) so the UI can explain which preferences shaped the result.

## Configuration

Enable in `config.py`:

```python
MULTI_ROUTE_MODE = True  # Enable distinct paths (default: True)
```

## API Response

When `MULTI_ROUTE_MODE=True` and `use_wsm=True`:

```json
{
  "success": true,
  "multi_route": true,
  "routes": {
    "baseline": {
      "route_coords": [[51.45, -2.58], ...],
      "stats": {"distance_km": "1.23", "time_min": 15},
      "colour": "#808080",
      "route_context": {"subtitle": "Shortest route", "modifiers": []}
    },
    "extremist": {
      "route_coords": [[51.46, -2.57], ...],
      "stats": {"distance_km": "1.89", "time_min": 23},
      "colour": "#22C55E",
      "route_context": {
        "subtitle": "Scenic emphasis",
        "modifiers": ["Prefer lit streets"]
      },
      "dominant_feature": "greenness"
    },
    "balanced": {
      "route_coords": [[51.455, -2.575], ...],
      "stats": {"distance_km": "1.45", "time_min": 18},
      "colour": "#3B82F6",
      "route_context": {
        "subtitle": "Custom mix",
        "modifiers": ["Prefer lit streets"]
      }
    }
  },
  "start_point": [51.45, -2.58],
  "end_point": [51.46, -2.57]
}
```

### Advanced Compare Mode (Scenic Off + Advanced On)

When scenic sliders are disabled but advanced options are enabled, the API returns a focused comparison payload:

```json
{
  "success": true,
  "multi_route": true,
  "routes": {
    "baseline": {
      "route_context": { "subtitle": "Shortest route", "modifiers": [] }
    },
    "extremist": null,
    "balanced": {
      "route_context": {
        "subtitle": "Advanced options",
        "modifiers": ["Prefer paved surfaces", "Avoid unsafe roads"]
      }
    }
  }
}
```

This mode guarantees that advanced options are visible and comparable even without scenic weighting.

## Weight Configurations

### Baseline

```python
{'distance': 1.0, 'greenness': 0, 'water': 0, 'quietness': 0, 'social': 0, 'slope': 0}
```

### Baseline Purity Guarantees

The baseline route intentionally disables all advanced modifiers, including:

- `prefer_lit`
- `heavily_avoid_unlit`
- `prefer_dedicated_pavements`
- `prefer_nature_trails`
- `prefer_paved`
- `avoid_unsafe_roads`

This keeps baseline comparisons stable and interpretable.

### Extremist

Identifies the user's highest scenic weight and maximises it:

```python
{'distance': 0.1, '<dominant_feature>': 1.0, '<others>': 0}
```

**Tie-breaking order:** `greenness > water > quietness > social > slope`

### Balanced

Uses the user's actual weight configuration as provided.

## Colour Coding

| Feature   | Hex Colour         |
| --------- | ------------------ |
| Baseline  | `#808080` (Grey)   |
| Balanced  | `#3B82F6` (Blue)   |
| Greenness | `#22C55E` (Green)  |
| Water     | `#06B6D4` (Cyan)   |
| Quietness | `#A855F7` (Purple) |
| Social    | `#F97316` (Orange) |
| Slope     | `#78716C` (Brown)  |

## Performance

Runs A\* sequentially for each candidate route:

- Full distinct mode: 3 passes (baseline + extremist + balanced)
- Advanced compare mode: 2 passes (baseline + advanced)

Graph building/caching is unchanged.

## Backward Compatibility

When `MULTI_ROUTE_MODE=False` or `use_wsm=False`, the API returns single-route output with `multi_route: false`.
