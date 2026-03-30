# ADR-003: Weighted-MIN Algorithm and 0-5 Slider Scale

**Status:** Accepted  
**Date:** 2026-01-19  
**Supersedes:** Partially updates ADR-001

---

## Context

After implementing MIN-based OR semantics (ADR-001), user testing revealed two issues:

### Issue 1: Abrupt Transitions

With pure MIN, changing a slider from 0→1 caused dramatic route changes, but 1→10 had minimal effect:

| Setting             | Route Result                            |
| ------------------- | --------------------------------------- |
| Green=9, Water=0    | Green route (park)                      |
| Green=9, Water=1    | Suddenly different route (more options) |
| Green=9, Water=2-10 | Same route as Water=1                   |

**Root cause:** Pure MIN ignores weight values - it only checks if weight > 0, then picks the minimum normalized value regardless of weight magnitude.

### Issue 2: Wasted Slider Range

The 0-10 scale had significant "dead space" where increments had no effect, making the UI feel unresponsive.

---

## Decision

### Part A: Implement Weighted-MIN Algorithm

Replace pure MIN with weight-adjusted MIN so that higher weights give proportional advantage:

```python
# Pure MIN (old): weight magnitude ignored
best = min(norm_green, norm_water)

# Weighted-MIN (new): divide by (1 + weight) so higher weights advantage
adjusted_green = norm_green / (1 + weight_green)
adjusted_water = norm_water / (1 + weight_water)
best = min(adjusted_green, adjusted_water)
```

This ensures:

- OR semantics preserved (only best attribute contributes, no cross-penalties)
- Weight priority respected (higher weight = more likely to "win" MIN)
- Gradual transitions (3→4 has noticeable effect)

### Part B: Change Slider Scale from 0-10 to 0-5

Reduce slider granularity to eliminate dead space:

| Old                 | New                 | Rationale                     |
| ------------------- | ------------------- | ----------------------------- |
| 0-10                | 0-5                 | Each increment now meaningful |
| Distance default: 5 | Distance default: 3 | Middle of new range           |

---

## Implementation

### cost_calculator.py Changes

```python
def compute_wsm_cost(...):
    # Collect active scenic criteria
    active = [(val, w) for val, w in scenic_data if w > 0]

    if active:
        # Weighted-MIN: divide by (1 + weight) so higher weights get advantage
        adjusted_values = [(val / (1 + w), w) for val, w in active]
        best_adjusted = min(adj for adj, w in adjusted_values)

        total_scenic_weight = sum(w for val, w in active)
        avg_weight = total_scenic_weight / len(active)
        normalization_factor = 1 + avg_weight

        cost += total_scenic_weight * best_adjusted * normalization_factor

    return cost
```

### UI Changes (index.html)

- All sliders: `max="10"` → `max="5"`
- Distance default: `value="5"` → `value="3"`
- Helper text: Updated to explain OR semantics

---

## Consequences

### Positive

| Benefit                    | Explanation                                    |
| -------------------------- | ---------------------------------------------- |
| **Meaningful increments**  | Each slider step produces visible route change |
| **Weight priority works**  | Green=5, Water=2 actually prefers green more   |
| **Simpler UI**             | Fewer confusing "dead" values                  |
| **OR semantics preserved** | Still no cross-criterion penalties             |

### Negative

| Limitation                   | Explanation                                                     |
| ---------------------------- | --------------------------------------------------------------- |
| **Cache invalidation**       | Existing routes may differ with same slider positions           |
| **Documentation update**     | Need to update any user guides referring to 0-10 scale          |
| **Normalization complexity** | Weighted-MIN requires scaling factor to maintain cost magnitude |

---

## Mathematical Analysis

### Why Weighted-MIN Preserves OR Semantics

With AND semantics:

```
cost = w_g × g + w_w × w    # Bad at either adds penalty
```

With Weighted-MIN:

```
cost = total × min(g/(1+w_g), w/(1+w_w)) × norm_factor
```

**Key difference:** The MIN ensures only ONE term contributes. Bad values for other criteria are completely ignored, not added as penalties.

### Example: Green Edge (g=0.1, w=0.9)

With Greenery=0.4, Water=0.2 (normalized):

| Method           | Calculation                       | Cost      | Water penalty? |
| ---------------- | --------------------------------- | --------- | -------------- |
| **AND**          | 0.4×0.1 + 0.2×0.9                 | **0.22**  | ✗ YES (+0.18)  |
| **Weighted-MIN** | min(0.1/1.4, 0.9/1.2) × 0.6 × 1.3 | **0.056** | ✓ NO           |

The water score (0.9) is completely ignored because green (adjusted: 0.071) beats water (adjusted: 0.75) in the MIN competition.

---

## Testing

### Test Case: UWE → Fishponds

| Setting          | Expected Behavior                               |
| ---------------- | ----------------------------------------------- |
| Green=5, Water=0 | Through Stoke Park (green route)                |
| Green=5, Water=1 | Similar to above (green still dominates)        |
| Green=5, Water=3 | May include water features if encountered       |
| Green=3, Water=5 | Prefers water features over green               |
| Green=5, Water=5 | Both equally weighted, route varies by location |

### Acceptance Criteria

1. Changing slider from 3→4 produces visible route change (not just 0→1)
2. Higher-weighted criterion wins when both are good
3. No cross-criterion penalty for secondary criteria

---

## References

- ADR-001: Original OR semantics decision
- User testing session 2026-01-19
- [WSM Feature Documentation](../features/routing/wsm_feature.md)
