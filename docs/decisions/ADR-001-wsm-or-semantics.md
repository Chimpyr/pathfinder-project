# ADR-001: WSM OR-Semantics for Multi-Criteria Routing

**Status:** Accepted  
**Date:** 2026-01-19  

---

## Context

The ScenicPathFinder uses a Weighted Sum Model (WSM) to combine multiple scenic criteria (greenery, water proximity, quietness, etc.) with distance into a single cost function for A* pathfinding.

### The Problem

During testing of the UWE Frenchay → Fishponds route, we discovered a critical issue:

- **Single criterion works:** Setting `Greenery=10` produces a scenic route through Stoke Park (4073m, 196 nodes)
- **Single criterion works:** Setting `Water=10` produces a route near water features (3565m, 166 nodes)  
- **Multi-criteria fails:** Setting `Greenery=9, Water=5` produces the **shortest path** (2791m, 114 nodes)

The multi-criteria route showed no scenic preference at all, despite the user explicitly requesting scenic features.

### Root Cause Analysis

Debug output revealed the issue:

```
[WSM Debug] Edge 243812775->9110915569: norm_water=1.000, norm_green=1.000, cost=0.8236
```

All edges near the start had worst-case scores (1.0) for **both** water and greenery. The current WSM uses **additive AND semantics**:

```
cost = w_d × norm_length + w_g × norm_green + w_w × norm_water + ...
```

This means:
- An edge through a park (green=0.1, water=0.9) is penalized for lacking water
- An edge by a river (green=0.9, water=0.1) is penalized for lacking greenery
- The "average mediocre" shortest path often wins because it's not heavily penalized for any single criterion

### User Intent vs Algorithm Behavior

| User Says | User Means | Algorithm Did |
|-----------|------------|---------------|
| "Greenery=9, Water=5" | "Give me a scenic route, prefer green, water is also good" | "Only accept edges good at BOTH green AND water" |

The AND semantics don't match user expectations. Users want **OR semantics**: a route is scenic if it has green features **OR** water features **OR** quiet streets.

---

## Decision

**Replace additive WSM with MIN-based OR semantics for scenic criteria.**

### New Formula

```python
# Current (AND): penalizes edges bad at ANY weighted criterion
cost = w_d × norm_length + w_g × norm_green + w_w × norm_water + w_q × norm_quiet + ...

# New (OR): rewards edges good at ANY weighted criterion
best_scenic = min(norm_green, norm_water, norm_quiet, ...)  # Only for active criteria
cost = w_d × norm_length + (w_g + w_w + w_q + ...) × best_scenic
```

### Implementation

In `cost_calculator.py`, modify `compute_wsm_cost()`:

```python
def compute_wsm_cost(...):
    cost = weights['distance'] * norm_length
    
    scenic_data = [
        (norm_green, weights['greenness']),
        (norm_water, weights['water']),
        (norm_social, weights['social']),
        (norm_quiet, weights['quietness']),
        (norm_slope, weights['slope']),
    ]
    
    active = [(val, w) for val, w in scenic_data if w > 0]
    
    if active:
        best_scenic_value = min(val for val, w in active)
        total_scenic_weight = sum(w for val, w in active)
        cost += total_scenic_weight * best_scenic_value
    
    return cost
```

---

## Consequences

### Positive

| Benefit | Explanation |
|---------|-------------|
| **Fixes multi-criteria collapse** | Routes will now detour for ANY scenic feature |
| **Simple implementation** | ~15 lines of code change |
| **Backwards compatible** | Single-criterion routing unchanged (min of one value = that value) |
| **Intuitive UX** | Matches user mental model of "scenic route" |
| **No UI changes required** | Sliders work as before |

### Negative

| Limitation | Explanation |
|------------|-------------|
| **Loses strict priority ordering** | Green=9, Water=5 won't ALWAYS prefer green over water |
| **Over-rewards single-feature edges** | Edge that's ONLY green scores same as one that's green AND quiet |
| **Weights become "activation thresholds"** | Higher weight means "counts more when good", not "strict priority" |

### Neutral

- A* heuristic remains admissible (still optimistic bound)
- Performance unchanged (same number of operations)
- All test cases for single-criterion routing continue to pass

---

## Alternatives Considered

### Alternative 1: Simple/Advanced UI Toggle

**Proposal:** Add toggle for "Simple" (OR) vs "Advanced" (AND) modes.

**Rejected because:**
- AND mode is actually broken, not "advanced" - it doesn't serve a legitimate use case
- Doubles maintenance burden
- Forces users to understand algorithm internals
- Creates false choice

### Alternative 2: Weighted-MIN with Priority Bonus

**Proposal:** Use MIN but scale contribution by the weight of the winning criterion.

```python
best_val, best_weight = min(scenic_data, key=lambda x: x[0])
scenic_cost = best_weight * best_val + 0.5 * (total_weight - best_weight) * best_val
```

**Deferred:** More complex, may be unnecessary. Can be added later if strict priority ordering proves important.

### Alternative 3: Multiplicative WSM

**Proposal:** Use products instead of sums: `cost = l × (1-w_g×g) × (1-w_w×w) × ...`

**Rejected because:**
- Non-linear, harder to reason about
- Requires complete re-tuning of weights
- Less interpretable for users

### Alternative 4: Path-Dependent Diversity Scoring

**Proposal:** Track scenic features collected along path, reduce weight for already-experienced features.

**Deferred to Phase 2:** This addresses a different user intent ("Scenic Journey" - experience multiple types of scenery). Appropriate for future enhancement via waypoint injection, not core WSM modification.

---

## Validation

### Test Cases

1. **UWE → Fishponds with Green=8, Water=5**
   - Before: Shortest path (2791m)
   - After: Scenic route through Stoke Park OR via River Frome (3500m+)

2. **Single criterion unchanged**
   - Green=10 only → Same route as before (through park)

3. **Monotonicity**
   - Increasing scenic slider never makes route LESS scenic

### Acceptance Criteria

> When a user sets multiple scenic criteria, the algorithm MUST produce a route containing edges scoring well (norm < 0.5) on AT LEAST ONE of the enabled criteria.

---

## References

- Terminal debug logs from 2026-01-19 testing session
- [WSM Feature Documentation](../wsm_feature.md)
- Multi-Criteria Decision Analysis (MCDA) literature on aggregation semantics
