# ADR-011: Restricted-Access Edge and Node Pruning

**Status:** Accepted  
**Date:** 2026-02-22

---

## Context

Users reported being routed through military zones, private office footpaths, locked-gate estates, and other non-navigable areas. The existing walking filter (`walking_filter.py`) only rejected a narrow set of access restrictions (`access=private|no`, `foot=no`, `service=private`), leaving many OSM-tagged restricted areas in the graph.

### The Problem

| Tag Combination | Expected | Actual (before fix) |
|-----------------|----------|---------------------|
| `access=military` | Excluded | **Included** ❌ |
| `access=customers` | Excluded | **Included** ❌ |
| `access=agricultural` | Excluded | **Included** ❌ |
| `foot=private` | Excluded | **Included** ❌ |
| `foot=use_sidepath` | Excluded | **Included** ❌ |
| `highway=service` + `service=driveway` | Excluded | **Included** ❌ |
| `highway=service` + `service=parking_aisle` | Excluded | **Included** ❌ |
| `barrier=gate` + `locked=yes` (node) | Block edges | **No effect** ❌ |

Additionally, the filter had no concept of node-level barriers — locked gates in the OSM data were invisible to the edge filter.

---

## Decision

**Expand the walking filter with comprehensive restricted-access tag sets, node-level barrier resolution, and a unified four-mask pruning system.**

The solution operates entirely within the existing `walking_filter.py` module (no new files), at the vectorised DataFrame level before NetworkX graph construction.

### Tag Set Definitions

```python
RESTRICTED_ACCESS = {'private', 'no', 'military', 'customers',
                     'agricultural', 'forestry', 'delivery', 'restricted'}

RESTRICTED_FOOT = {'no', 'private', 'restricted', 'use_sidepath'}

EXPLICIT_ALLOW = {'yes', 'permissive', 'designated', 'public'}

RESTRICTED_SERVICE = {'driveway', 'parking_aisle', 'private'}
```

### Four Boolean Masks

| Mask | Column | Condition |
|------|--------|-----------|
| A — Override | `foot` | `∈ EXPLICIT_ALLOW` |
| B — Foot restriction | `foot` | `∈ RESTRICTED_FOOT` |
| C — Access restriction | `access` | `∈ RESTRICTED_ACCESS` |
| D — Service restriction | `highway` + `service` | `highway == 'service'` AND `service ∈ RESTRICTED_SERVICE` |

### Unified Drop Equation

```
drop = gate_blocked | B | (C & ~A) | (D & ~A)
```

The `~A` (NOT explicitly allowed) term ensures that public footpaths through private estates are preserved when the `foot` tag explicitly permits pedestrian access.

### Node-Level Barrier Resolution

A new `_resolve_restricted_nodes()` function identifies impassable nodes:
- `barrier == 'gate'` AND (`locked == 'yes'` OR `access ∈ RESTRICTED_ACCESS`)

Any edge whose source or target vertex matches a restricted node ID is flagged for removal.

---

## Consequences

### Positive

- **Safety**: Users can no longer be routed through military zones, private business parks, or locked gates
- **Correctness**: Legitimate public footpaths through private land are preserved via the explicit-allow override
- **Backward compatible**: All existing tests pass; the function signature adds an optional `nodes` parameter
- **Minimal overhead**: Boolean masking on vectorised DataFrames adds negligible processing time

### Negative

- **Slightly smaller graphs**: More edges are pruned, which could occasionally remove a useful shortcut if OSM data is incorrectly tagged
- **Cache invalidation required**: Existing cached graphs must be rebuilt to apply the new filter

### Trade-offs Accepted

| Metric | Before | After |
|--------|--------|-------|
| Access tags filtered | 2 (`private`, `no`) | 8 (+ `military`, `customers`, `agricultural`, `forestry`, `delivery`, `restricted`) |
| Foot tags filtered | 1 (`no`) | 4 (+ `private`, `restricted`, `use_sidepath`) |
| Service sub-types filtered | 1 (`private`) | 3 (+ `driveway`, `parking_aisle`) |
| Node barriers | None | Locked/restricted gates |
| Override mechanism | `foot ∈ PEDESTRIAN_FOOT_VALUES` | `foot ∈ EXPLICIT_ALLOW` (superset) |

---

## Alternatives Considered

1. **Post-graph pruning** — Remove edges after NetworkX construction. Rejected because it wastes memory building edges that will be discarded, and risks creating disconnected graph components.

2. **Separate filter module** — Create a new `restricted_filter.py`. Rejected because the logic is tightly coupled with the existing walking filter (same DataFrame, same foot-override semantics), and splitting would require two-pass filtering.

3. **Tag-based edge weighting** — Instead of removing restricted edges, apply very high costs. Rejected because restricted areas should be completely non-navigable, not merely discouraged.

---

## Files Modified

| File | Changes |
|------|---------|
| `walking_filter.py` | Expanded tag sets, added `_resolve_restricted_nodes()`, refactored `apply_walking_filter()` with four-mask pruning |
| `data_loader.py` | Added `barrier`, `locked`, `service` to extra attributes; passes nodes to filter |
| `test_walking_filter.py` | Added 35+ new tests for restricted access, barriers, overrides, and service filtering |

---

## References

- [Custom Walking Filter Feature Doc](../features/custom_walking_filter.md)
- [ADR-010 §2a](./ADR-010-improvements-to-budget-astar-looper.md) — Original walking filter investigation
- [OSM Access Tags Wiki](https://wiki.openstreetmap.org/wiki/Key:access)
- [OSM Barrier Tags Wiki](https://wiki.openstreetmap.org/wiki/Key:barrier)
